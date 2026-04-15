"""agent/graph.py
LangGraph 有状态工作流（USE_LANGGRAPH=true 时才会被导入）

工作流节点（线性 Pipeline）：
  risk_detect  → 四级风险识别
  rag_retrieve → 三混合 RAG 检索（复用 rag.router.RagRouter）
  llm_generate → 调用华为云 LLM（复用 huawei_nlp 内部方法）
  safety_check → urgent/high 场景安全后处理

优化（v2.7）：
  - AgentState 新增 user_id 字段，支持 PersonalRAG
  - rag_retrieve 新增 PersonalRAG 最小版：使用用户历史关键词增强检索 query
  - safety_check 保留 high 级别软提示逻辑
  - 所有新增能力默认可通过 settings 开关控制
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List,Tuple

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
    user_id:     int                   # ✅ v2.7 新增：登录用户 ID，游客为 0
    risk_level:  str                   # low | medium | high | urgent
    rag_context: str                   # 注入 Prompt 的 RAG 上下文
    rag_route:   str                   # RAG 路由类型（vector/graph/hybrid/none）
    rag_refs:    List[Dict[str, Any]]  # RAG 引用元数据（用于返回/落库）
    result:      Dict[str, Any]        # 最终分析结果
    _start_time: float                 # 请求开始时间戳（用于耗时统计）


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
# PersonalRAG：辅助函数
# ─────────────────────────────────────────────────────────────────────────────
async def _get_personal_rag_context(
    user_id: int,
    current_text: str,
    top_n: int = 10,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    长期记忆最终版（轻量生产级）：
    - 长期存储全部 emotion_records
    - 每次只按需提取：
        1. 最近记录
        2. 类似情绪
        3. 重要记忆
        4. 历史有效案例
    - 返回：
        enrichment_text, personal_refs
    """
    try:
        from models.database import SessionLocal  # noqa: PLC0415
        from models.emotion_record import EmotionRecord  # noqa: PLC0415
        from api.routes.feedback_route import FeedbackRecord  # noqa: PLC0415
        from sqlalchemy import desc  # noqa: PLC0415
        import json as _json

        db = SessionLocal()
        try:
            # 最近记录
            recent_records = (
                db.query(EmotionRecord)
                .filter(EmotionRecord.user_id == user_id)
                .order_by(desc(EmotionRecord.created_at))
                .limit(top_n)
                .all()
            )

            if not recent_records:
                return "", []

            latest_label = recent_records[0].emotion_label if recent_records else None

            # 类似情绪记录
            similar_records = (
                db.query(EmotionRecord)
                .filter(
                    EmotionRecord.user_id == user_id,
                    EmotionRecord.emotion_label == latest_label if latest_label else True,
                )
                .order_by(desc(EmotionRecord.created_at))
                .limit(5)
                .all()
            )

            # 重要记忆（importance 高）
            important_records = (
                db.query(EmotionRecord)
                .filter(
                    EmotionRecord.user_id == user_id,
                    EmotionRecord.memory_importance >= 0.7,
                )
                .order_by(desc(EmotionRecord.memory_importance), desc(EmotionRecord.created_at))
                .limit(5)
                .all()
            )

            # 历史有效案例（用户点赞）
            liked_feedbacks = (
                db.query(FeedbackRecord)
                .filter(
                    FeedbackRecord.user_id == user_id,
                    FeedbackRecord.rating == "like",
                )
                .order_by(desc(FeedbackRecord.created_at))
                .limit(5)
                .all()
            )

            all_keywords: List[str] = []
            refs: List[Dict[str, Any]] = []
            same_label_count = 0

            for r in recent_records:
                if r.keywords:
                    try:
                        parsed = _json.loads(r.keywords)
                        if isinstance(parsed, list):
                            all_keywords.extend([str(x) for x in parsed if x])
                    except Exception:
                        pass
                if latest_label and r.emotion_label == latest_label:
                    same_label_count += 1

            # refs：类似情绪 + 重要记忆
            merged_records = []
            seen_ids = set()
            for r in similar_records + important_records:
                if r.id not in seen_ids:
                    merged_records.append(r)
                    seen_ids.add(r.id)

            for r in merged_records[:5]:
                refs.append({
                    "doc_id": f"personal_{r.id}",
                    "topic": r.memory_topic or r.emotion_label or "个人记忆",
                    "category": "personal_memory",
                    "score": round(float(r.memory_importance or 0.5), 3),
                    "source": "personal",
                    "rrf_score": None,
                    "memory_type": "long_term_memory",
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                })

            effective_cases: List[str] = []
            for f in liked_feedbacks:
                if f.feedback_text:
                    effective_cases.append(str(f.feedback_text).strip()[:80])
                elif f.ai_reply:
                    effective_cases.append(str(f.ai_reply).strip()[:80])

            effective_cases = list(dict.fromkeys([x for x in effective_cases if x]))[:3]
            unique_keywords = list(dict.fromkeys(all_keywords))[:12]

            enrichment_parts: List[str] = []

            if unique_keywords:
                enrichment_parts.append(" ".join(unique_keywords))

            if latest_label and same_label_count >= 2:
                enrichment_parts.append(f"最近你已经第{same_label_count}次提到类似的{latest_label}感受")

            if effective_cases:
                enrichment_parts.append("过去对你更有效的回应线索：" + "；".join(effective_cases[:2]))

            enrichment_text = " ".join([p for p in enrichment_parts if p]).strip()

            return enrichment_text, refs[:6]

        finally:
            db.close()

    except Exception as exc:
        logger.debug("[PersonalRAG] _get_personal_rag_context 失败: %s", exc)
        return "", []


# ─────────────────────────────────────────────────────────────────────────────
# 节点 2：RAG 检索
# ─────────────────────────────────────────────────────────────────────────────

async def node_rag_retrieve(state: AgentState) -> AgentState:
    """
    节点 2：三混合 RAG 检索。
    v2.9 最终增强：
      - 独立 Personal source
      - Personal refs 返回
      - 类似情绪历史召回
      - 历史有效案例优先提示
      - 最小仪式感模板增强
    """
    rag_context: str = ""
    rag_refs: List[Dict[str, Any]] = []
    rag_route: str = "none"
    t0 = time.monotonic()

    retrieval_text = state["text"]
    personal_refs: List[Dict[str, Any]] = []
    personal_ctx: str = ""

    # ✅ PersonalRAG：默认关闭，登录用户生效
    try:
        from config.settings import settings as _s  # noqa: PLC0415

        if getattr(_s, "ENABLE_PERSONAL_RAG", False) and state.get("user_id", 0):
            top_n = getattr(_s, "PERSONAL_RAG_HISTORY_N", 10)
            personal_ctx, personal_refs = await _get_personal_rag_context(
                state["user_id"],
                state["text"],
                top_n,
            )
            if personal_ctx:
                retrieval_text = f'{state["text"]} {personal_ctx}'
                logger.debug(
                    "[LG] PersonalRAG enriched | user_id=%s added=%s",
                    state["user_id"],
                    personal_ctx[:150],
                )
    except Exception as _exc:
        logger.debug("[LG] PersonalRAG 增强失败，使用原始文本: %s", _exc)
        personal_ctx = ""
        personal_refs = []

    try:
        from config.settings import settings  # noqa: PLC0415
        from rag.router import get_rag_router  # noqa: PLC0415

        router = get_rag_router()

        if settings.ENABLE_RAG_REFS:
            rag_context, rag_refs = await router.retrieve_with_refs(
                text=retrieval_text,
                history=state.get("history", []),
                top_k=4,
            )
        else:
            rag_context = await router.retrieve(
                text=retrieval_text,
                history=state.get("history", []),
                top_k=4,
            )

        # ✅ 拼接 personal refs（保留现有 refs 兼容性）
        if personal_refs:
            rag_refs = personal_refs + rag_refs

        # ✅ 明确 route 标识
        rag_route = getattr(router, "_last_route", None) or "unknown"
        if personal_refs and rag_route != "none":
            rag_route = f"{rag_route}+personal"
        elif personal_refs:
            rag_route = "personal"

        # ✅ 把 personal_ctx 变成一个隐式 expert_context 补充（不破坏原 RAG）
        if personal_ctx:
            ritual_block = (
                "\n<personal_memory_context>\n"
                "以下是与该用户近期情绪与有效回应方式相关的个人化记忆线索"
                "（请自然融入回复，不要直接说你记忆了这些信息）：\n"
                f"{personal_ctx[:300]}\n"
                "</personal_memory_context>\n"
            )
            rag_context = (rag_context or "") + ritual_block

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[LG] rag_retrieve | route=%s context_len=%d refs=%d latency=%dms user_id=%s personal=%s",
            rag_route,
            len(rag_context),
            len(rag_refs),
            elapsed,
            state.get("user_id", 0),
            "yes" if personal_refs else "no",
        )

    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "[LG] node_rag_retrieve 异常，跳过 RAG: %s (latency=%dms)",
            exc,
            elapsed,
        )

    return {
        **state,
        "rag_context": rag_context,
        "rag_refs": rag_refs,
        "rag_route": rag_route,
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

        # ✅ v3.0 深度画像注入（默认关闭，失败不影响主流程）
    try:
        from config.settings import settings as _s  # noqa: PLC0415
        if _s.ENABLE_USER_PROFILE and state.get("user_id", 0):
            from service.profile_service import load_profile  # noqa: PLC0415
            profile = load_profile(state["user_id"])
            deep_profile = profile.get("deep_profile", {}) if profile else {}

            profile_parts = []

            if profile.get("stressors"):
                profile_parts.append(f"用户近期压力源：{', '.join(profile['stressors'][:5])}")
            if profile.get("recent_state"):
                profile_parts.append(f"用户近期状态：{profile['recent_state']}")
            if profile.get("response_hints"):
                profile_parts.append(f"用户画像摘要：{profile['response_hints']}")

            if isinstance(deep_profile, dict):
                if deep_profile.get("interaction_style"):
                    profile_parts.append(f"推测交流风格：{deep_profile['interaction_style']}")
                if deep_profile.get("support_preference"):
                    profile_parts.append(f"推测支持偏好：{deep_profile['support_preference']}")
                if deep_profile.get("effective_approach"):
                    profile_parts.append(
                        "更适合的回应方式：" + "、".join(deep_profile.get("effective_approach", [])[:3])
                    )
                if deep_profile.get("stress_triggers"):
                    profile_parts.append(
                        "常见压力触发点：" + "、".join(deep_profile.get("stress_triggers", [])[:3])
                    )

            if profile_parts:
                system_prompt += (
                    "\n\n【用户长期画像线索】\n"
                    "以下内容是基于长期互动形成的推测型画像，只能作为温和参考，"
                    "不可当作绝对判断，不可直接下结论式地贴标签：\n"
                    + "\n".join(f"- {x}" for x in profile_parts[:8])
                    + "\n请把这些线索自然融入回复风格中，避免机械复述。"
                )
    except Exception as exc:
        logger.debug("[LG] 深度画像注入失败（已忽略）: %s", exc)
    
    logger.info(
    "[LG] profile_injected | user_id=%s stressors=%d deep_profile=%s",
    state.get("user_id", 0),
    len(profile.get("stressors", [])) if profile else 0,
    "yes" if profile.get("deep_profile") else "no",
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
                "user_id":    state.get("user_id", 0),
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
        if reply and all(k not in reply for k in ("心理咨询", "咨询", "心理中心", "热线", "专业帮助")):
            result["reply"] = reply + _HIGH_SOFT_HINT
            action = "soft_hint_appended"

    start_time = state.get("_start_time", 0)
    total_ms   = int((time.monotonic() - start_time) * 1000) if start_time else 0

        # ✅ v2.8：高风险时创建 72h 随访任务（默认关闭，失败不影响主流程）
    try:
        from config.settings import settings as _s  # noqa: PLC0415
        if _s.ENABLE_FOLLOWUP_TASK and state.get("user_id", 0) and risk_level in ("high", "urgent"):
            from service.followup_service import schedule_followup  # noqa: PLC0415
            schedule_followup(
                user_id=state["user_id"],
                risk_level=risk_level,
                result=result,
                trigger_text=state.get("text", ""),
            )
    except Exception as exc:
        logger.warning("[LG] followup task 创建失败（已忽略）: %s", exc)

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
    user_id: int | None = None,
) -> Dict[str, Any]:
    """
    运行 LangGraph Agent，返回结果字典（与 huawei_nlp_service.analyze_sentiment 格式一致）。
    v2.7 新增：
      - 可选 user_id，用于 PersonalRAG / 用户画像等长期能力
      - 游客 user_id 自动降级为 0
    """
    graph = _get_graph()

    initial_state: AgentState = {
        "text":        text,
        "mode":        mode,
        "history":     history,
        "user_id":     int(user_id or 0),
        "risk_level":  "low",
        "rag_context": "",
        "rag_route":   "none",
        "rag_refs":    [],
        "result":      {},
        "_start_time": time.monotonic(),
    }

    logger.info(
        "[LG] run_agent START | mode=%s text_len=%d history=%d user_id=%s",
        mode, len(text), len(history), initial_state["user_id"],
    )

    final_state = await graph.ainvoke(initial_state)
    result      = final_state.get("result", {})

    if not result or "category" not in result:
        raise ValueError(
            f"[LG] Agent 返回无效结果: {list(result.keys()) if result else 'empty'}"
        )

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
        "[LG] run_agent END | category=%s score=%.1f refs=%d rag_route=%s total=%dms user_id=%s",
        result.get("category"),
        result.get("score", 0),
        len(rag_refs),
        rag_route,
        total_ms,
        initial_state["user_id"],
    )
    return result
