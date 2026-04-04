"""rag/graph/graph_rag.py
GraphRAG：关键词种子 + 1-hop 扩展，无本地模型，纯 SQLite。
"""
from __future__ import annotations

import logging
from typing import List

from rag.graph.graph_store import get_one_hop_neighbors, search_nodes_by_keywords
from rag.types import RagDoc

logger = logging.getLogger(__name__)

# 情绪/心理领域种子关键词（用于从文本中提取图谱入口）
_SEEDS = [
    "焦虑", "抑郁", "压力", "失眠", "崩溃", "自杀", "伤害", "轻生",
    "孤独", "考试", "宿舍", "恋爱", "家庭", "就业", "迷茫", "空洞",
    "CBT", "认知行为", "心理咨询", "热线", "资源", "援助",
]


def _extract_seed_keywords(text: str) -> List[str]:
    """从输入文本中提取匹配的种子关键词。"""
    return [kw for kw in _SEEDS if kw in text]


def query_graph(text: str, top_k: int = 4) -> List[RagDoc]:
    """
    GraphRAG 检索：
    1. 从 text 提取种子关键词
    2. 在 KG 中查找匹配节点
    3. 1-hop 扩展
    4. 组合文本，返回 List[RagDoc]
    """
    keywords = _extract_seed_keywords(text)
    if not keywords:
        keywords = _SEEDS[:6]   # 无命中时用前 6 个宽泛种子

    seed_nodes = search_nodes_by_keywords(keywords, limit=3)
    if not seed_nodes:
        logger.debug("[GraphRAG] 无种子节点命中 keywords=%s", keywords[:3])
        return []

    seed_ids   = [n["id"] for n in seed_nodes]
    neighbors  = get_one_hop_neighbors(seed_ids, limit=top_k * 2)
    all_nodes  = seed_nodes + neighbors

    # 去重
    seen:   set = set()
    unique: List[dict] = []
    for node in all_nodes:
        if node["id"] not in seen:
            seen.add(node["id"])
            unique.append(node)

    docs: List[RagDoc] = []
    for i, node in enumerate(unique[:top_k]):
        props = node.get("properties", {})
        parts = [
            node.get("embedding_text", ""),
            node.get("name", ""),
            props.get("description", ""),
            props.get("resource", ""),
        ]
        doc_text = " | ".join(p for p in parts if p)
        base_score = node.get("weight", 1.0) if "weight" in node else 1.0
        score = round(base_score / (1 + i * 0.3), 4)

        docs.append(RagDoc(
            doc_id=f"graph_{node['id']}",
            text=doc_text,
            score=score,
            source="graph",
            metadata={
                "type":     node.get("node_type", ""),
                "relation": node.get("relation", ""),
                "name":     node.get("name", ""),
            },
        ))

    logger.info("[GraphRAG] hits=%d seeds=%s", len(docs), keywords[:3])
    return docs