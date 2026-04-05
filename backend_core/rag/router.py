"""rag/router.py
RagRouter：三混合 RAG 统一入口。
优先级：新 RagRouter → 旧 rag_service → rag_context=""（不允许 500）
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from rag.self_rag.self_rag import check_evidence, decide_route
from rag.types import RagDoc

logger = logging.getLogger(__name__)


def _format_context(docs: List[RagDoc], query: str) -> str:
    """将 RagDoc 列表格式化为注入 System Prompt 的上下文字符串。"""
    if not docs:
        return ""

    parts: List[str] = []
    for i, doc in enumerate(docs[:3], start=1):   # 最多 3 条，控制 token
        src = "心理知识库" if doc.source == "vector" else "专业资源图谱"
        parts.append(
            f"<ref_{i} source='{src}' rel='{doc.score:.2f}'>\n"
            f"{doc.text[:280]}\n"
            f"</ref_{i}>"
        )

    return (
        "\n<expert_context>\n"
        "以下是你对此类情境的内化专业认知"
        "（融入回复中，绝对不要提及你参考了以下信息）：\n"
        + "\n".join(parts)
        + "\n</expert_context>\n"
    )


class RagRouter:
    """
    三混合 RAG 路由器：Self-RAG 门控 → GraphRAG / VectorRAG / HybridRAG。
    任何子模块异常均被 catch，保证调用方拿到字符串（空或非空）。
    """

    def __init__(self) -> None:
        self._vector_ok = False
        self._graph_ok  = False
        self._probe()

    def _probe(self) -> None:
        """探测各后端是否可用（不抛出异常）。"""
        from config.settings import settings  # noqa: PLC0415

        # 向量后端：chromadb 可导入 + Embedding API 已配置
        try:
            import chromadb  # noqa: F401, PLC0415
            if settings.EMBEDDING_API_KEY and settings.EMBEDDING_API_BASE:
                self._vector_ok = True
                logger.info("[RagRouter] Vector backend: OK (API embedding)")
            else:
                logger.warning(
                    "[RagRouter] Vector backend: DISABLED "
                    "(EMBEDDING_API_KEY 或 EMBEDDING_API_BASE 未配置)"
                )
        except ImportError:
            logger.warning("[RagRouter] Vector backend: DISABLED (chromadb 未安装)")

        # 图谱后端：SQLite 始终可用（无需额外依赖）
        try:
            from rag.graph.graph_store import get_node_count  # noqa: PLC0415
            count = get_node_count()
            self._graph_ok = True
            logger.info("[RagRouter] Graph backend: OK (SQLite nodes=%d)", count)
        except Exception as exc:
            logger.warning("[RagRouter] Graph backend: DISABLED — %s", exc)

    # ── 公共接口 ──────────────────────────────────────────────────────────

    async def retrieve(
        self,
        text:    str,
        history: Optional[List[Dict[str, Any]]] = None,
        top_k:   int = 4,
    ) -> str:
        """
        主检索入口，返回 rag_context 字符串。
        任何异常均回退为空字符串，不允许抛出异常。
        """
        history = history or []

        # ── Step 1: Self-RAG 门控 ────────────────────────────────────────
        decision = decide_route(text, history)
        logger.info(
            "[RagRouter] route=%s need=%s reason=%s",
            decision.route, decision.need_retrieval, decision.reason,
        )

        if not decision.need_retrieval or decision.route == "none":
            return ""

        # ── Step 2: 分路检索 ─────────────────────────────────────────────
        docs: List[RagDoc] = []
        try:
            if decision.route == "graph" and self._graph_ok:
                docs = await self._graph(text, top_k)

            elif decision.route == "hybrid":
                docs = await self._hybrid(text, top_k)

            elif decision.route == "self" and self._vector_ok:
                docs = await self._vector(text, top_k)

            elif self._graph_ok:
                # 降级：无向量时用图谱
                docs = await self._graph(text, top_k)

        except Exception as exc:
            logger.warning("[RagRouter] 检索异常 (route=%s): %s", decision.route, exc)
            return ""

        # ── Step 3: 证据检查 ─────────────────────────────────────────────
        if not check_evidence(docs, min_score=0.06):
            logger.info("[RagRouter] 证据不足，降级为纯 LLM")
            return ""

        logger.info(
            "[RagRouter] 最终 docs=%d top_score=%.3f route=%s",
            len(docs), docs[0].score if docs else 0, decision.route,
        )
        return _format_context(docs, text)

    # ── 私有检索方法 ──────────────────────────────────────────────────────

    async def _vector(self, text: str, top_k: int) -> List[RagDoc]:
        from rag.vector_store.chroma_store import query as _q  # noqa: PLC0415
        return await _q(text, top_k=top_k)

    async def _graph(self, text: str, top_k: int) -> List[RagDoc]:
        from rag.graph.graph_rag import query_graph  # noqa: PLC0415
        return await asyncio.to_thread(query_graph, text, top_k)

    async def _hybrid(self, text: str, top_k: int) -> List[RagDoc]:
        from rag.vector_store.chroma_store import query as _vq  # noqa: PLC0415
        from rag.graph.graph_rag import query_graph              # noqa: PLC0415
        from rag.hybrid.hybrid_rag import merge_and_rank         # noqa: PLC0415

        vector_docs, graph_docs = await asyncio.gather(
            _vq(text, top_k=top_k) if self._vector_ok else asyncio.coroutine(lambda: [])(),
            asyncio.to_thread(query_graph, text, top_k) if self._graph_ok else asyncio.coroutine(lambda: [])(),
            return_exceptions=True,
        )

        v = vector_docs if isinstance(vector_docs, list) else []
        g = graph_docs  if isinstance(graph_docs,  list) else []

        # 如果两路都空，至少返回其中有效的
        if not v and not g:
            return []
        if not v:
            return g[:top_k]
        if not g:
            return v[:top_k]

        return merge_and_rank(v, g, top_k=top_k)


# ── 单例 ──────────────────────────────────────────────────────────────────
_router_instance: Optional[RagRouter] = None


def get_rag_router() -> RagRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = RagRouter()
    return _router_instance
