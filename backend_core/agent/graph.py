"""agent/graph.py v2.6
LangGraph 有状态工作流（USE_LANGGRAPH=true 时才会被导入）

v2.6 变更：
  ★ BUG FIX：node_safety_check 中 "high" 分支缩进错误（嵌套在 urgent 内）→ 已修复
  - 新增 _apply_prompt_enhancements()：可选 Prompt 增强（RAG 防幻觉/脆弱引导/情绪镜像）
  - node_llm_generate 调用增强函数，所有增强默认关闭，出问题直接关开关回滚
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
# 全局状态定义（不变）
# ─────────────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """LangGraph 全局状态，在各节点间流转。"""
    text:        str
    mode:        str
    history:     List[Dict[str, Any]]
    risk_level:  str
    rag_context: str
    rag_route:   str
    rag_refs:    List[Dict[str, Any]]
    result:      Dict[str, Any]
    _start_time: float


# ─────────────────────────────────────────────────────────────────────────────
# ✅ v2.6 新增：Prompt 增强辅助函数（纯函数，不影响任何现有逻辑）
# ─────────────────────────────────────────────────────────────────────────────

def _apply_prompt_enhancements(rag_context: str, risk_level: str) -> str:
    """
    根据 feature flags 对 rag_context 追加约束/引导指令。

    设计思路：
    - 这些指令随 rag_context 一同注入 build_system_prompt，无需修改 huawei_nlp.py
    - 每项增强都有独立开关，出问题单独关闭，互不影响
    - 纯字符串追加，任何异常都有 try/except 保护

    当 USE_LANGGRAPH=false 时，此函数不会被调用，旧链路完全不受影响。
    """
    try:
        from config.settings import settings  # noqa: PLC0415

        enhanced = rag_context

        # ── 1. RAG 防幻觉约束（ENABLE_RAG_GROUNDING）──────────────────────
        # 只有在有 RAG 上下文时才追加，无上下文时追加无意义
        if settings.ENABLE_RAG_GROUNDING and enhanced:
            enhanced += (
                "\n\n[严格约束] 你的回复必须基于上方专业知识，"
                "不得捏造任何未在上文中提及的热线号码、机构名称或具体资源。"
                "若上文未提供相关资源，可温和建议用户向学校心理中心或专业机构寻求帮助。"
            )

        # ── 2. 脆弱信号主动引导（ENABLE_VULNERABILITY_PROBE）─────────────
        # medium/high 时追加温和开放式问题引导，营造被接纳的空间
        if settings.ENABLE_VULNERABILITY_PROBE and risk_level in ("medium", "high", "urgent"):
            enhanced += (
                "\n\n[引导策略] 当用户出现压抑或回避迹象时，可用温和的开放式问题引导，"
                "如'这种感觉持续多久了？'或'能多跟我说说发生了什么吗？'"
                "目的是创造被接纳的空间，不要急于给出方案，先让对方感到被看见。"
            )

        # ── 3. 情绪镜像风格匹配（ENABLE_EMOTION_MIRROR）─────────────────
        # 根据 risk_level 给出语气风格要求
        if settings.ENABLE_EMOTION_MIRROR:
            _mirror_map = {
                "urgent": "请用极度温柔、缓慢而有力量的语气回应，先让对方感到被接住，不要急于给建议。",
                "high":   "请用充分共情的语气，先承认并反映对方的情绪，再温和引导。",
                "medium": "请用温暖稳定的语气，适当融入具体的关心与陪伴。",
                "low":    "保持自然亲切的语气即可。",
            }
            style_hint = _mirror_map.get(risk_level, _mirror_map["low"])
            enhanced += f"\n\n[回复风格] {style_hint}"

        return enhanced

    except Exception as exc:
        # 增强失败不影响主流程，返回原始 rag_context
        logger.warning("[LG] _apply_prompt_enhancements 失败，使用原始 context: %s", exc)
        return rag_context


# ─────────────────────────────────────────────────────────────────────────────
# 节点 1：风险识别（不变）
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
# 节点 2：RAG 检索（不变）
# ─────────────────────────────────────────────────────────────────────────────

async def node_rag_retrieve(state: AgentState) -> AgentState:
    """节点 2：三混合 RAG 检索，失败时置空不阻断流程。"""
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
# 节点 3：LLM 生成（新增 prompt 增强调用）
# ─────────────────────────────────────────────────────────────────────────────

async def node_llm_generate(state: AgentState) -> AgentState:
    """节点 3：调用华为云 LLM 生成回复，并注入 Langfuse 追踪。"""
    from service.huawei_nlp import (  # noqa: PLC0415
        huawei_nlp_service,
        build_system_prompt,
    )
    from config.settings import settings  # noqa: PLC0415

    mode       = state["mode"]
    risk_level = state.get("risk_level", "low")
    t0         = time.monotonic()

    # ✅ v2.6：可选 Prompt 增强（对 rag_context 追加约束/引导）
    # 所有增强默认关闭，失败自动回退原始 context，零侵入
    raw_rag_context = state.get("rag_context", "")
    effective_rag_context = _apply_prompt_enhancements(raw_rag_context, risk_level)

    system_prompt = build_system_prompt(
        mode=mode,
        rag_context=effective_rag_context,
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
            rag_context=effective_rag_context,  # 使用增强后的 context
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
# 节点 4：安全后处理（★ BUG FIX：修复 "high" 分支永远不执行的缩进 bug）
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
    ★ BUG FIX v2.6：原代码 'elif risk_level == "high"' 错误缩进在 urgent 的内层
    if/elif 链中，导致 high 分支永远不执行。本次修复将其提升到与 urgent 同级。
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
        # ★ 修复：此处原为错误缩进（在 urgent 的 elif 内），已修正为与 urgent 同级
        # 软提示：如果回复中已包含咨询/热线/专业帮助相关内容则跳过，避免重复
        _soft_hint_keywords = ("心理咨询", "咨询", "心理中心", "热线", "专业帮助", "心理援助")
        if reply and all(k not in reply for k in _soft_hint_keywords):
            result["reply"] = reply + _HIGH_SOFT_HINT
            action = "soft_hint_appended"

    start_time = state.get("_start_time", 0)
    total_ms   = int((time.monotonic() - start_time) * 1000) if start_time else 0

    logger.info(
        "[LG] safety_check | risk=%s action=%s total_latency=%dms",
        risk_level, action, total_ms,
    )
    return {**state, "result": result}


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：空 Langfuse 上下文（不变）
# ─────────────────────────────────────────────────────────────────────────────

class _NullContext:
    """Langfuse 不可用时的 noop 上下文管理器。"""
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def start_llm(self, **_): pass
    def end_llm(self, **_): pass
    def set_output(self, **_): pass


# ─────────────────────────────────────────────────────────────────────────────
# 图编译（懒加载单例，不变）
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
# 对外入口（签名不变，完全兼容现有调用）
# ─────────────────────────────────────────────────────────────────────────────

async def run_agent(
    text: str,
    mode: str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    运行 LangGraph Agent，返回结果字典（与 huawei_nlp_service.analyze_sentiment 格式一致）。
    函数签名不变，完全兼容现有 analysis.py 调用。
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

    result    = dict(result)
    rag_refs  = final_state.get("rag_refs", []) or []
    rag_route = final_state.get("rag_route", "")

    if rag_refs:
        result["_refs"] = rag_refs
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
