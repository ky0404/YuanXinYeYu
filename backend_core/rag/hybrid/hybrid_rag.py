"""rag/hybrid/hybrid_rag.py
HybridRAG：合并 VectorRAG + GraphRAG 结果，去重排序，取 top_k。
"""
from __future__ import annotations

import logging
from typing import List

from rag.types import RagDoc

logger = logging.getLogger(__name__)

_VECTOR_W = 0.60   # 向量权重
_GRAPH_W  = 0.40   # 图谱权重（危机资源等结构化知识)


def _normalize(docs: List[RagDoc], weight: float) -> List[RagDoc]:
    """归一化分数并乘以权重。"""
    if not docs:
        return docs
    max_s = max(d.score for d in docs) or 1.0
    for d in docs:
        d.score = round(d.score / max_s * weight, 6)
    return docs


def merge_and_rank(
    vector_docs: List[RagDoc],
    graph_docs:  List[RagDoc],
    top_k:       int   = 4,
    vector_w:    float = _VECTOR_W,
    graph_w:     float = _GRAPH_W,
) -> List[RagDoc]:
    """
    合并两路结果：
    1. 分别归一化 + 加权
    2. 按 doc_id 去重（保留较高分）
    3. 降序排列，取 top_k
    """
    _normalize(vector_docs, vector_w)
    _normalize(graph_docs,  graph_w)

    merged: dict[str, RagDoc] = {}
    for doc in vector_docs + graph_docs:
        if doc.doc_id in merged:
            if doc.score > merged[doc.doc_id].score:
                merged[doc.doc_id] = doc
        else:
            merged[doc.doc_id] = doc

    ranked = sorted(merged.values(), key=lambda d: d.score, reverse=True)
    result = ranked[:top_k]

    logger.info(
        "[HybridRAG] vector=%d graph=%d → unique=%d → top%d",
        len(vector_docs), len(graph_docs), len(merged), len(result),
    )
    return result