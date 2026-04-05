"""agent/graph.py
LangGraph 有状态工作流（USE_LANGGRAPH=true 时才会被导入）

工作流节点（线性 Pipeline）：
  risk_detect  → 四级风险识别
  rag_retrieve → 三混合 RAG 检索（复用 rag.router.RagRouter）
  llm_generate → 调用华为云 LLM（复用 huawei_nlp 内部方法）
  safety_check → urgent 场景强制追加热线

设计原则：
  - langgraph 包仅在此文件内导入，模块级不影响 FastAPI 启动
  - _compiled_graph 懒加载，第一次 run_agent() 时才编译
  - 节点间通过 AgentState TypedDict 传递状态，无副作用
  - Langfuse 追踪在 llm_generate 节点内可选注入

调用方：core/analysis.py 的 EmotionAnalyzer.analyze()（当 USE_LANGGRAPH=true）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# State 定义
# ══════════════════════════════════════════════════════════════════════════

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore[no-redef]


class AgentState(TypedDict):
    """LangGraph 全局状态，在各节点间流转。"""
    text:        str
    mode:        str
    history:     List[Dict[str, Any]]
    risk_level:  str                   # low | medium | high | urgent
    rag_context: str                   # 注入 Prompt 的 RAG 上下文
    result:      Dict[str, Any]        # 最终分析结果（与 analyze_sentiment 格式一致）


# ══════════════════════════════════════════════════════════════════════════
# 节点函数
# ══════════════════════════════════════════════════════════════════════════

async def node_risk_detect(state: AgentState) -> AgentState:
    """
    节点 1：四级风险识别。
    直接复用 service.huawei_nlp.detect_risk_level，无重复实现。
    """
    try:
        from service.huawei_nlp import detect_risk_level  # noqa: PLC0415
        risk = detect_risk_level(state["text"], state.get("history", []))
    except Exception as exc:
        logger.warning("[LG] node_risk_detect 异常，降级 low: %s", exc)
        risk = "low"

    logger.info("[LG] risk_detect | risk=%s text_len=%d", risk, len(state["text"]))
    return {**state, "risk_level": risk}


async def node_rag_retrieve(state: AgentState) -> AgentState:
    """
    节点 2：三混合 RAG 检索。
    复用 rag.router.RagRouter，失败时 rag_context 置空（不阻断流程）。
    """
    rag_context = ""
    try:
        from rag.router import get_rag_router  # noqa: PLC0415
        router  = get_rag_router()
        rag_context = await router.retrieve(
            text=state["text"],
            history=state.get("history", []),
            top_k=4,
        )
        logger.info("[LG] rag_retrieve | context_len=%d", len(rag_context))
    except Exception as exc:
        logger.warning("[LG] node_rag_retrieve 异常，跳过 RAG: %s", exc)

    return {**state, "rag_context": rag_context}


async def node_llm_generate(state: AgentState) -> AgentState:
    """
    节点 3：调用华为云 LLM 生成回复。
    复用 HuaweiNLPService._generate_with_context()，保持解析逻辑唯一。
    可选注入 Langfuse 追踪。
    """
    from service.huawei_nlp import (  # noqa: PLC0415
        huawei_nlp_service,
        build_system_prompt,
    )
    from config.settings import settings  # noqa: PLC0415

    mode        = state["mode"]
    rag_context = state.get("rag_context", "")
    risk_level  = state.get("risk_level",  "low")

    system_prompt = build_system_prompt(
        mode=mode,
        rag_context=rag_context,
        risk_level=risk_level,
    )

    # ── 可选 Langfuse 追踪 ─────────────────────────────────────────────
    if settings.LANGFUSE_ENABLED:
        from agent.langfuse_client import LangfuseTrace  # noqa: PLC0415
        trace_ctx = LangfuseTrace(
            name="lg_llm_generate",
            input_kv={"text": state["text"][:200], "mode": mode, "risk": risk_level},
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
        # 调用 HuaweiNLPService 内部方法，避免重复 RAG 检索
        result = await huawei_nlp_service._generate_with_context(
            text=state["text"],
            mode=mode,
            history=state.get("history", []),
            rag_context=rag_context,
            risk_level=risk_level,
        )
        trace.end_llm(output=result)
        trace.set_output({"category": result.get("category"), "score": result.get("score")})

    logger.info(
        "[LG] llm_generate | category=%s score=%.1f reply_len=%d",
        result.get("category"), result.get("score", 0), len(result.get("reply", "")),
    )
    return {**state, "result": result}


async def node_safety_check(state: AgentState) -> AgentState:
    """
    节点 4：安全后处理。
    urgent 场景强制追加热线（防止 LLM 遗漏）。
    """
    result     = dict(state.get("result", {}))
    risk_level = state.get("risk_level", "low")

    if (
        risk_level == "urgent"
        and result.get("reply")
        and "400-161-9995" not in result["reply"]
    ):
        result["reply"] += (
            " 如果现在很难受，请拨打心理援助热线 400-161-9995，"
            "或者让身边的人陪着你。"
        )
        logger.info("[LG] safety_check | 已追加热线（urgent）")

    return {**state, "result": result}


# ── 空上下文管理器（Langfuse 关闭时使用）────────────────────────────────

class _NullContext:
    """Langfuse 不可用时的 noop 上下文管理器。"""
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def start_llm(self, **_): pass
    def end_llm(self, **_):   pass
    def set_output(self, **_): pass


# ══════════════════════════════════════════════════════════════════════════
# 图编译（懒加载）
# ══════════════════════════════════════════════════════════════════════════

_compiled_graph: Any = None   # CompiledGraph or None


def _build_and_compile():
    """编译 LangGraph 状态机（仅调用一次）。"""
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


# ══════════════════════════════════════════════════════════════════════════
# 公共入口
# ══════════════════════════════════════════════════════════════════════════

async def run_agent(
    text:    str,
    mode:    str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    运行 LangGraph Agent，返回与 huawei_nlp_service.analyze_sentiment() 相同格式的字典。

    任何异常均向上抛出，由 core/analysis.py 的调用方捕获并 fallback 到旧链路。
    """
    graph = _get_graph()

    initial_state: AgentState = {
        "text":        text,
        "mode":        mode,
        "history":     history,
        "risk_level":  "low",
        "rag_context": "",
        "result":      {},
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

    logger.info(
        "[LG] run_agent END | category=%s score=%.1f",
        result.get("category"), result.get("score", 0),
    )
    return result