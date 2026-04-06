"""rag/bm25_retriever.py
BM25 关键词检索器（P1，ENABLE_BM25=true 时启用）

设计：
  - 使用 rank-bm25 包，pip install rank-bm25
  - 中文采用字符 + 双字节 bigram 分词（无需外部分词工具）
  - 启动时从 KNOWLEDGE_BASE 构建内存索引（workers=1 下安全）
  - 返回 List[RagDoc]，与 vector/graph 路径接口一致
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from rag.types import RagDoc

logger = logging.getLogger(__name__)

_bm25_instance: Optional["BM25Retriever"] = None


def _tokenize(text: str) -> List[str]:
    """
    轻量中文分词：
    1. 提取所有汉字、英文词、数字
    2. 对汉字序列额外生成 bigram
    """
    tokens: List[str] = []
    # 英文/数字词
    tokens.extend(re.findall(r"[a-zA-Z0-9]+", text))
    # 汉字序列
    han_sequences = re.findall(r"[\u4e00-\u9fff]+", text)
    for seq in han_sequences:
        # unigrams
        tokens.extend(list(seq))
        # bigrams
        for i in range(len(seq) - 1):
            tokens.append(seq[i : i + 2])
    return [t.lower() for t in tokens if t]


class BM25Retriever:
    """
    BM25 检索器，从 KNOWLEDGE_BASE 构建索引。
    索引在进程生命周期内驻留内存（约 1-2MB）。
    """

    def __init__(self) -> None:
        self._docs:      List[Dict[str, Any]] = []
        self._tokenized: List[List[str]]      = []
        self._bm25      = None
        self._ready      = False
        self._build_index()

    def _build_index(self) -> None:
        try:
            from rank_bm25 import BM25Okapi  # noqa: PLC0415
            from knowledge.emotion_knowledge import KNOWLEDGE_BASE  # noqa: PLC0415
        except ImportError as exc:
            logger.warning("[BM25] rank-bm25 未安装，BM25 检索不可用: %s", exc)
            return
        except Exception as exc:
            logger.warning("[BM25] 知识库加载失败: %s", exc)
            return

        for entry in KNOWLEDGE_BASE:
            # 构建用于索引的文本（拼接 keywords + topic + content）
            doc_text = " ".join([
                " ".join(entry.get("keywords", [])),
                entry.get("topic",    ""),
                entry.get("category", ""),
                entry.get("content",  "")[:300],
                entry.get("advice",   "")[:200],
            ])
            self._docs.append(entry)
            self._tokenized.append(_tokenize(doc_text))

        if not self._tokenized:
            logger.warning("[BM25] 没有可索引的文档")
            return

        try:
            self._bm25  = BM25Okapi(self._tokenized)
            self._ready = True
            logger.info("[BM25] 索引构建完成 | docs=%d", len(self._docs))
        except Exception as exc:
            logger.warning("[BM25] 索引构建失败: %s", exc)

    def retrieve(self, query: str, top_k: int = 4) -> List[RagDoc]:
        """
        BM25 检索，返回 List[RagDoc]（score 为归一化 BM25 分）。
        """
        if not self._ready or self._bm25 is None:
            return []
        if not query.strip():
            return []

        try:
            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            raw_scores = self._bm25.get_scores(query_tokens)
            max_score  = max(raw_scores) if max(raw_scores) > 0 else 1.0

            # 取 top_k
            indexed = sorted(
                enumerate(raw_scores),
                key=lambda x: x[1],
                reverse=True,
            )[:top_k]

            docs: List[RagDoc] = []
            for idx, score in indexed:
                if score <= 0:
                    continue
                entry     = self._docs[idx]
                norm_score = round(score / max_score, 6)
                docs.append(RagDoc(
                    doc_id   = f"bm25_{entry['id']}",
                    text     = entry.get("content", "")[:300],
                    score    = norm_score,
                    source   = "bm25",
                    metadata = {
                        "kb_id":       entry.get("id", ""),
                        "category":    entry.get("category", ""),
                        "topic":       entry.get("topic", ""),
                        "scene_tags":  entry.get("scene_tags", []),
                        "risk_level":  entry.get("risk_level", "low"),
                        "source_name": "emotion_knowledge_kb",
                    },
                ))

            logger.debug("[BM25] query=%r hits=%d top_score=%.3f",
                         query[:30], len(docs), docs[0].score if docs else 0)
            return docs

        except Exception as exc:
            logger.warning("[BM25] 检索失败: %s", exc)
            return []


def get_bm25_retriever() -> Optional[BM25Retriever]:
    """懒加载单例。"""
    global _bm25_instance
    if _bm25_instance is None:
        _bm25_instance = BM25Retriever()
    return _bm25_instance if _bm25_instance._ready else None