"""agent/graph.py
LangGraph 有状态工作流（USE_LANGGRAPH=true 时才会被导入）

工作流节点（线性 Pipeline）：
  risk_detect  → 四级风险识别
  rag_retrieve → 三混合 RAG 检索（复用 rag.router.RagRouter）
  llm_generate → 调用华为云 LLM（复用 huawei_nlp 内部方法）
  safety_check → urgent/high 场景安全后处理

优化（v2.4）：
  - AgentState 新增 rag_route 字段，便于日志/Langfuse 可观测
  - safety_check 补充 high 级别软提示（urgent 强制热线，high 建议专业资源）
  - 各节点日志更丰富，方便线上排查
  - 所有节点 state 返回改用 dict 解包，避免引用污染
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore[no-redef]


# ─────────────────────────────────────────────────────────────────────────────
# 全局状态定义
# ─────────────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """LangGraph 全局状态，在各节点间流转。"""
    text:        str
    mode:        str
    history:     List[Dict[str, Any]]
    risk_level:  str                   # low | medium | high | urgent
    rag_context: str                   # 注入 Prompt 的 RAG 上下文
    rag_route:   str                   # ✅ v2.4 RAG 路由类型（vector/graph/hybrid/none）
    rag_refs:    List[Dict[str, Any]]  # RAG 引用元数据（用于返回/落库）
    result:      Dict[str, Any]        # 最终分析结果
    _start_time: float                 # ✅ v2.4 请求开始时间戳（用于耗时统计）


# ─────────────────────────────────────────────────────────────────────────────
# 节点 1：风险识别
# ─────────────────────────────────────────────────────────────────────────────

async def node_risk_detect(state: AgentState) -> AgentState:
    """节点 1：四级风险识别（low / medium / high / urgent）。"""
    t0 = time.monotonic()
    try:
        from service.huawei_nlp import detect_risk_level  # noqa: PLC0415
        risk = detect_risk_level(state["text"], state.get("history", []))
    except Exception as exc:
        logger.warning("[LG] node_risk_detect 异常，降级 low: %s", exc)
        risk = "low"

    elapsed = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[LG] risk_detect | risk=%s text_len=%d latency=%dms",
        risk, len(state["text"]), elapsed,
    )
    return {**state, "risk_level": risk}


# ─────────────────────────────────────────────────────────────────────────────
# 节点 2：RAG 检索
# ─────────────────────────────────────────────────────────────────────────────

async def node_rag_retrieve(state: AgentState) -> AgentState:
    """
    节点 2：三混合 RAG 检索。
    失败时 rag_context 置空、rag_refs 置空（不阻断流程）。
    """
    rag_context: str = ""
    rag_refs: List[Dict[str, Any]] = []
    rag_route: str = "none"
    t0 = time.monotonic()

    try:
        from config.settings import settings  # noqa: PLC0415
        from rag.router import get_rag_router  # noqa: PLC0415

        router = get_rag_router()

        if settings.ENABLE_RAG_REFS:
            rag_context, rag_refs = await router.retrieve_with_refs(
                text=state["text"],
                history=state.get("history", []),
                top_k=4,
            )
        else:
            rag_context = await router.retrieve(
                text=state["text"],
                history=state.get("history", []),
                top_k=4,
            )

        # ✅ 尝试从 router 获取实际路由类型（如果 router 支持）
        rag_route = getattr(router, "_last_route", None) or "unknown"

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[LG] rag_retrieve | route=%s context_len=%d refs=%d latency=%dms",
            rag_route, len(rag_context), len(rag_refs), elapsed,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.warning("[LG] node_rag_retrieve 异常，跳过 RAG: %s (latency=%dms)", exc, elapsed)

    return {
        **state,
        "rag_context": rag_context,
        "rag_refs":    rag_refs,
        "rag_route":   rag_route,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 节点 3：LLM 生成
# ─────────────────────────────────────────────────────────────────────────────

async def node_llm_generate(state: AgentState) -> AgentState:
    """节点 3：调用华为云 LLM 生成回复，并注入 Langfuse 追踪。"""
    from service.huawei_nlp import (  # noqa: PLC0415
        huawei_nlp_service,
        build_system_prompt,
    )
    from config.settings import settings  # noqa: PLC0415

    mode        = state["mode"]
    rag_context = state.get("rag_context", "")
    risk_level  = state.get("risk_level", "low")
    t0          = time.monotonic()

    system_prompt = build_system_prompt(
        mode=mode,
        rag_context=rag_context,
        risk_level=risk_level,
    )

    if settings.LANGFUSE_ENABLED:
        from agent.langfuse_client import LangfuseTrace  # noqa: PLC0415
        trace_ctx = LangfuseTrace(
            name="lg_llm_generate",
            input_kv={
                "text":       state["text"][:200],
                "mode":       mode,
                "risk":       risk_level,
                "rag_route":  state.get("rag_route", "unknown"),
            },
            metadata={"route": "langgraph"},
        )
    else:
        trace_ctx = _NullContext()

    with trace_ctx as trace:
        trace.start_llm(
            model=settings.HUAWEI_MODEL,
            prompt=system_prompt,
            mode=mode,
        )
        result = await huawei_nlp_service._generate_with_context(
            text=state["text"],
            mode=mode,
            history=state.get("history", []),
            rag_context=rag_context,
            risk_level=risk_level,
        )
        trace.end_llm(output=result)
        trace.set_output({
            "category":  result.get("category"),
            "score":     result.get("score"),
            "rag_route": state.get("rag_route", "unknown"),
        })

    elapsed = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[LG] llm_generate | category=%s score=%.1f reply_len=%d latency=%dms",
        result.get("category"),
        result.get("score", 0),
        len(result.get("reply", "")),
        elapsed,
    )
    return {**state, "result": result}


# ─────────────────────────────────────────────────────────────────────────────
# 节点 4：安全后处理
# ─────────────────────────────────────────────────────────────────────────────

_URGENT_HOTLINE = (
    " 如果现在很难受，请拨打心理援助热线 400-161-9995，"
    "或者让身边的人陪着你。"
)

_HIGH_SOFT_HINT = (
    " 如果持续感到困扰，建议与专业心理咨询师聊聊，"
    "学校心理中心和公益热线都可以提供帮助。"
)

async def node_safety_check(state: AgentState) -> AgentState:
    """
    节点 4：安全后处理。
    - urgent：强制追加心理援助热线（400-161-9995）
    - high：追加专业咨询软提示（如果回复中没有）
    """
    result     = dict(state.get("result", {}))
    risk_level = state.get("risk_level", "low")
    reply      = result.get("reply", "")
    action     = "none"

    if risk_level == "urgent":
        if reply and "400-161-9995" not in reply:
            result["reply"] = reply + _URGENT_HOTLINE
            action = "hotline_appended"
        elif not reply:
            result["reply"] = _URGENT_HOTLINE.strip()
            action = "hotline_only"

        elif risk_level == "high":
        # 软提示：如果回复中已经包含咨询/热线/心理中心等内容则跳过，避免重复
            if reply and all(k not in reply for k in ("心理咨询", "咨询", "心理中心", "热线", "专业帮助")):
                result["reply"] = reply + _HIGH_SOFT_HINT
                action = "soft_hint_appended"

    # ✅ 总耗时统计（从 AgentState._start_time 算起）
    start_time = state.get("_start_time", 0)
    total_ms   = int((time.monotonic() - start_time) * 1000) if start_time else 0

    logger.info(
        "[LG] safety_check | risk=%s action=%s total_latency=%dms",
        risk_level, action, total_ms,
    )
    return {**state, "result": result}


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：空 Langfuse 上下文
# ─────────────────────────────────────────────────────────────────────────────

class _NullContext:
    """Langfuse 不可用时的 noop 上下文管理器。"""
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def start_llm(self, **_): pass
    def end_llm(self, **_): pass
    def set_output(self, **_): pass


# ─────────────────────────────────────────────────────────────────────────────
# 图编译（懒加载单例）
# ─────────────────────────────────────────────────────────────────────────────

_compiled_graph: Any = None


def _build_and_compile():
    from langgraph.graph import END, StateGraph  # noqa: PLC0415

    builder = StateGraph(AgentState)

    builder.add_node("risk_detect",  node_risk_detect)
    builder.add_node("rag_retrieve", node_rag_retrieve)
    builder.add_node("llm_generate", node_llm_generate)
    builder.add_node("safety_check", node_safety_check)

    builder.set_entry_point("risk_detect")
    builder.add_edge("risk_detect",  "rag_retrieve")
    builder.add_edge("rag_retrieve", "llm_generate")
    builder.add_edge("llm_generate", "safety_check")
    builder.add_edge("safety_check", END)

    compiled = builder.compile()
    logger.info("[LG] Graph 编译完成 | nodes=4 (risk→rag→llm→safety)")
    return compiled


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_and_compile()
    return _compiled_graph


# ─────────────────────────────────────────────────────────────────────────────
# 对外入口
# ─────────────────────────────────────────────────────────────────────────────

async def run_agent(
    text: str,
    mode: str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    运行 LangGraph Agent，返回结果字典（与 huawei_nlp_service.analyze_sentiment 格式一致）。
    """
    graph = _get_graph()

    initial_state: AgentState = {
        "text":        text,
        "mode":        mode,
        "history":     history,
        "risk_level":  "low",
        "rag_context": "",
        "rag_route":   "none",
        "rag_refs":    [],
        "result":      {},
        "_start_time": time.monotonic(),
    }

    logger.info(
        "[LG] run_agent START | mode=%s text_len=%d history=%d",
        mode, len(text), len(history),
    )

    final_state = await graph.ainvoke(initial_state)
    result      = final_state.get("result", {})

    if not result or "category" not in result:
        raise ValueError(
            f"[LG] Agent 返回无效结果: {list(result.keys()) if result else 'empty'}"
        )

    # ✅ 把 refs 和 rag_route 挂回 result，让上层统一后处理
    result = dict(result)
    rag_refs = final_state.get("rag_refs", []) or []
    if rag_refs:
        result["_refs"] = rag_refs

    rag_route = final_state.get("rag_route", "")
    if rag_route:
        result["_rag_route"] = rag_route

    start_time = initial_state["_start_time"]
    total_ms   = int((time.monotonic() - start_time) * 1000)

    logger.info(
        "[LG] run_agent END | category=%s score=%.1f refs=%d rag_route=%s total=%dms",
        result.get("category"),
        result.get("score", 0),
        len(rag_refs),
        rag_route,
        total_ms,
    )
    return result
