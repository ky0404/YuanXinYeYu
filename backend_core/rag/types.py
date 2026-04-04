"""rag/types.py — 共享数据类型"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class RagDoc:
    """单条检索结果。"""
    doc_id: str
    text:   str
    score:  float = 0.0
    source: str   = "unknown"   # "vector" | "graph"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteDecision:
    """Self-RAG 路由决策。"""
    need_retrieval: bool
    route:  str    # "self" | "graph" | "hybrid" | "none"
    reason: str = ""