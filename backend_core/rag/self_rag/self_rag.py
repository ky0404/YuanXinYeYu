"""rag/self_rag/self_rag.py
Self-RAG 最小门控：基于启发式规则决定是否检索及走哪条路由。
2G 内存限制下，不额外调用 LLM 做决策，用关键词规则代替。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from rag.types import RagDoc, RouteDecision

logger = logging.getLogger(__name__)

# 触发图谱检索的危机词（需要危机资源/热线）
_CRISIS_KW: frozenset = frozenset([
    "自杀", "不想活", "活不下去", "结束生命", "伤害自己",
    "轻生", "想死", "去死", "割腕", "跳楼", "轻生",
])

# 触发混合检索的知识求助词
_KNOWLEDGE_KW: frozenset = frozenset([
    "怎么办", "如何", "方法", "建议", "资源", "热线", "推荐",
    "什么是", "为什么", "CBT", "心理咨询", "帮助", "技巧",
    "应对", "策略", "怎样", "心理援助",
])

# 纯宣泄词（短文本 + 无知识求助 → 跳过检索，纯 LLM 共情更自然）
_SHORT_VENT_MAX = 18   # 字符阈值


def decide_route(
    text:    str,
    history: Optional[List[dict]] = None,   # 保留参数，未来可用上下文
) -> RouteDecision:
    """
    路由决策（纯启发式，O(1) 内存，无 LLM 调用）：
    - urgent/crisis → graph（图谱存有热线+资源节点）
    - knowledge-seeking + emotion → hybrid
    - knowledge-seeking only → self（向量）
    - short pure venting → none
    - default → self（向量）
    """
    # 1. 危机词 → 一定要图谱（热线资源）
    if any(kw in text for kw in _CRISIS_KW):
        return RouteDecision(
            need_retrieval=True, route="graph", reason="crisis_keywords"
        )

    has_knowledge = any(kw in text for kw in _KNOWLEDGE_KW)
    text_len = len(text.strip())

    # 2. 知识求助 + 情感内容（长文本）→ hybrid
    if has_knowledge and text_len > 20:
        return RouteDecision(
            need_retrieval=True, route="hybrid", reason="knowledge_and_emotion"
        )

    # 3. 纯知识求助（短）→ 向量
    if has_knowledge:
        return RouteDecision(
            need_retrieval=True, route="self", reason="knowledge_seeking"
        )

    # 4. 非常短的纯宣泄 → 不检索，LLM 直接共情效果更好
    if text_len <= _SHORT_VENT_MAX:
        return RouteDecision(
            need_retrieval=False, route="none", reason="short_pure_venting"
        )

    # 5. 默认：向量检索丰富情感语境
    return RouteDecision(
        need_retrieval=True, route="self", reason="default_emotional"
    )


def check_evidence(docs: List[RagDoc], min_score: float = 0.08) -> bool:
    """
    证据充分性检查：
    最高分 < min_score 时认为检索结果无效，降级为不注入 RAG 上下文。
    """
    if not docs:
        return False
    return max(d.score for d in docs) >= min_score