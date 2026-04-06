"""rag/router.py v3.2
修复：
  1. asyncio.coroutine() 已在 Python 3.11 删除 → 改用 async def _empty()
  2. 新增 BM25 融合路径（ENABLE_BM25=true 时，RRF 合并多路结果）
  3. 新增结构化 verbose 日志（ENABLE_VERBOSE_LOG=true 时输出节点耗时）
  4. 新增引用元数据透传（ENABLE_RAG_REFS=true 时，retrieve_with_refs() 返回 docs 列表）
  5. ✅修复：RRF 融合时不要覆盖 doc.score（否则 check_evidence(min_score=0.06) 会被 RRF 小数误伤）
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from rag.self_rag.self_rag import check_evidence, decide_route
from rag.types import RagDoc

logger = logging.getLogger(__name__)


# ── 工具函数 ──────────────────────────────────────────────────────────────

async def _empty() -> List[RagDoc]:
    """替代已删除的 asyncio.coroutine，返回空列表。"""
    return []


def _format_context(docs: List[RagDoc], query: str) -> str:
    """格式化 RAG 上下文，注入 System Prompt。"""
    if not docs:
        return ""
    parts: List[str] = []
    for i, doc in enumerate(docs[:3], start=1):
        src = {"vector": "心理知识库", "graph": "专业资源图谱", "bm25": "关键词知识库"}.get(
            doc.source, "知识库"
        )
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


def _rrf_merge(
    *result_lists: List[RagDoc],
    k: int = 60,
    top_k: int = 4,
) -> List[RagDoc]:
    """
    Reciprocal Rank Fusion：合并多路检索结果。
    RRF score = Σ 1 / (k + rank_i)，k=60 为业界惯例。

    重要：
      - 返回的 docs 顺序按 RRF 排序
      - 但不覆盖 doc.score（doc.score 继续表示“原始检索分数语义”）
      - 将 rrf_score 写入 doc.metadata["rrf_score"] 供调试/分析
    """
    rrf_scores: Dict[str, float] = {}
    picked: Dict[str, RagDoc] = {}

    for result_list in result_lists:
        for rank, doc in enumerate(result_list):
            base_id = doc.doc_id.removeprefix("bm25_").removeprefix("graph_")
            key = base_id

            if key not in picked:
                picked[key] = doc

            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank + 1)

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    result: List[RagDoc] = []
    for key, rrf_score in ranked:
        d = picked[key]
        # 不覆盖 d.score；只写入 metadata
        try:
            meta = dict(d.metadata or {})
            # 保留原始分数（可选，便于排查）
            meta.setdefault("orig_score", d.score)
            meta["rrf_score"] = round(rrf_score, 6)
            d.metadata = meta
        except Exception:
            # metadata 写入失败不应影响主流程
            pass
        result.append(d)
    return result


def _verbose_log(tag: str, elapsed_ms: float, extra: str = "") -> None:
    """结构化 verbose 日志（仅 ENABLE_VERBOSE_LOG=true 时输出）。"""
    from config.settings import settings  # noqa: PLC0415
    if settings.ENABLE_VERBOSE_LOG:
        logger.info("[RAG|verbose] %-20s elapsed=%.1fms %s", tag, elapsed_ms, extra)


# ── 主路由器 ──────────────────────────────────────────────────────────────

class RagRouter:
    """
    三混合 RAG 路由器（+ 可选 BM25）。
    任何子模块异常均被 catch，不允许向上抛出。
    """

    def __init__(self) -> None:
        self._vector_ok = False
        self._graph_ok = False
        self._probe()

    def _probe(self) -> None:
        from config.settings import settings  # noqa: PLC0415

        try:
            import chromadb  # noqa: F401, PLC0415
            if settings.EMBEDDING_API_KEY and settings.EMBEDDING_API_BASE:
                self._vector_ok = True
                logger.info("[RagRouter] Vector backend: OK (API embedding)")
            else:
                logger.warning("[RagRouter] Vector backend: DISABLED (API 未配置)")
        except ImportError:
            logger.warning("[RagRouter] Vector backend: DISABLED (chromadb 未安装)")

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
        text: str,
        history: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 4,
    ) -> str:
        """
        主检索入口，返回 rag_context 字符串（注入 Prompt 用）。
        当 ENABLE_RAG_REFS=true 时，调用方可通过 retrieve_with_refs() 获取文档列表。
        """
        _, context = await self._retrieve_internal(text, history, top_k)
        return context

    async def retrieve_with_refs(
        self,
        text: str,
        history: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 4,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        返回 (rag_context, refs_list)。
        refs_list 格式：[{doc_id, topic, category, score, source}]
        """
        docs, context = await self._retrieve_internal(text, history, top_k)
        refs = [
            {
                "doc_id": d.doc_id,
                "topic": d.metadata.get("topic", "") if d.metadata else "",
                "category": d.metadata.get("category", "") if d.metadata else "",
                "score": d.score,
                "source": d.source,
                # 可选：把 rrf_score 也带回去，便于你评测/调参（不想暴露可删）
                "rrf_score": (d.metadata.get("rrf_score") if d.metadata else None),
            }
            for d in docs
        ]
        return context, refs

    # ── 内部检索 ──────────────────────────────────────────────────────────

    async def _retrieve_internal(
        self,
        text: str,
        history: Optional[List[Dict[str, Any]]],
        top_k: int,
    ) -> Tuple[List[RagDoc], str]:
        history = history or []
        t0 = time.perf_counter()

        # Step 1: Self-RAG 门控
        decision = decide_route(text, history)
        _verbose_log(
            "self_rag_decide",
            (time.perf_counter() - t0) * 1000,
            f"route={decision.route} need={decision.need_retrieval} reason={decision.reason}",
        )

        logger.info(
            "[RagRouter] route=%s need=%s reason=%s",
            decision.route,
            decision.need_retrieval,
            decision.reason,
        )

        if not decision.need_retrieval or decision.route == "none":
            return [], ""

        # Step 2: 分路检索
        docs: List[RagDoc] = []
        try:
            t1 = time.perf_counter()
            docs = await self._dispatch(text, decision.route, top_k)
            _verbose_log(
                f"dispatch_{decision.route}",
                (time.perf_counter() - t1) * 1000,
                f"hits={len(docs)}",
            )
        except Exception as exc:
            logger.warning("[RagRouter] 检索异常 (route=%s): %s", decision.route, exc)
            return [], ""

        # Step 3: BM25 融合（可选）
        from config.settings import settings  # noqa: PLC0415
        if settings.ENABLE_BM25 and docs:
            try:
                t2 = time.perf_counter()
                docs = await self._fuse_bm25(text, docs, top_k, settings.BM25_RRF_K)
                _verbose_log(
                    "bm25_fuse",
                    (time.perf_counter() - t2) * 1000,
                    f"fused_docs={len(docs)}",
                )
            except Exception as exc:
                logger.warning("[RagRouter] BM25 融合失败，使用原始结果: %s", exc)

        # Step 4: 证据检查（用原始 doc.score 语义判断，不受 RRF 小数影响）
        if not check_evidence(docs, min_score=0.06):
            # 增加一点诊断信息（不含文本内容）
            top_score = docs[0].score if docs else 0
            top_rrf = None
            if docs and docs[0].metadata:
                top_rrf = docs[0].metadata.get("rrf_score")
            logger.info(
                "[RagRouter] 证据不足，降级纯 LLM | docs=%d top_score=%.3f top_rrf=%s route=%s",
                len(docs),
                top_score,
                top_rrf,
                decision.route,
            )
            return [], ""

        logger.info(
            "[RagRouter] 最终 docs=%d top_score=%.3f route=%s",
            len(docs),
            docs[0].score if docs else 0,
            decision.route,
        )
        _verbose_log(
            "total",
            (time.perf_counter() - t0) * 1000,
            f"docs={len(docs)} top={docs[0].doc_id if docs else 'N/A'}",
        )

        return docs, _format_context(docs, text)

    async def _dispatch(self, text: str, route: str, top_k: int) -> List[RagDoc]:
        if route == "graph" and self._graph_ok:
            return await self._graph(text, top_k)
        elif route == "hybrid":
            return await self._hybrid(text, top_k)
        elif route == "self" and self._vector_ok:
            return await self._vector(text, top_k)
        elif self._graph_ok:
            return await self._graph(text, top_k)
        return []

    async def _fuse_bm25(
        self, text: str, base_docs: List[RagDoc], top_k: int, rrf_k: int
    ) -> List[RagDoc]:
        from rag.bm25_retriever import get_bm25_retriever  # noqa: PLC0415

        bm25 = get_bm25_retriever()
        if bm25 is None:
            return base_docs

        bm25_docs = await asyncio.to_thread(bm25.retrieve, text, top_k)
        if not bm25_docs:
            return base_docs

        return _rrf_merge(base_docs, bm25_docs, k=rrf_k, top_k=top_k)

    async def _vector(self, text: str, top_k: int) -> List[RagDoc]:
        from rag.vector_store.chroma_store import query as _q  # noqa: PLC0415
        return await _q(text, top_k=top_k)

    async def _graph(self, text: str, top_k: int) -> List[RagDoc]:
        from rag.graph.graph_rag import query_graph  # noqa: PLC0415
        return await asyncio.to_thread(query_graph, text, top_k)

    async def _hybrid(self, text: str, top_k: int) -> List[RagDoc]:
        from rag.vector_store.chroma_store import query as _vq  # noqa: PLC0415
        from rag.graph.graph_rag import query_graph  # noqa: PLC0415
        from rag.hybrid.hybrid_rag import merge_and_rank  # noqa: PLC0415

        vector_coro = _vq(text, top_k=top_k) if self._vector_ok else _empty()
        graph_coro = (
            asyncio.to_thread(query_graph, text, top_k) if self._graph_ok else _empty()
        )

        results = await asyncio.gather(vector_coro, graph_coro, return_exceptions=True)
        v = results[0] if isinstance(results[0], list) else []
        g = results[1] if isinstance(results[1], list) else []

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
