"""service/huawei_nlp.py v2.3
变更说明（相对 v2.2）：
  1. 新增 _generate_with_context()：将"构建 Prompt + 调用 LLM + 解析"抽取为独立方法，
     供 LangGraph 节点（agent/graph.py）复用，消除重复实现。
  2. _generate_with_context() 内注入可选 Langfuse 追踪（LANGFUSE_ENABLED=true 时）。
  3. 其余逻辑（风险识别、三路 RAG 回退、兜底）与 v2.2 完全一致。
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

_current = os.path.dirname(os.path.abspath(__file__))
_root    = os.path.dirname(_current)
if _root not in sys.path:
    sys.path.insert(0, _root)

logger = logging.getLogger(__name__)

from config.settings import settings  # noqa: E402


# ── 统一 POST 调用 ────────────────────────────────────────────────────────

async def call_post_request(
    url:       str,
    headers:   Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        from utils.request import http_client as _cli  # noqa: PLC0415
        result = await _cli.post(url, headers=headers, json_data=json_data)
        if isinstance(result, dict):
            return result
        if hasattr(result, "json"):
            return result.json()
        return json.loads(result)
    except ImportError:
        logger.debug("[call_post] utils.request 不可用，使用 requests 回退")
    except Exception as exc:
        logger.warning("[call_post] http_client 失败 (%s)，回退 requests", exc)

    import requests  # noqa: PLC0415
    resp = requests.post(
        url,
        headers=headers or {},
        json=json_data or {},
        timeout=settings.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ══════════════════════════════════════════════════════════════════════════
# Prompt 模板（与 v2.2 完全一致）
# ══════════════════════════════════════════════════════════════════════════

BASE_PERSONA = """你叫小暖，是一个拥有专业心理咨询技术（如CBT认知行为疗法）但极具人情味的陪伴者。

【你的核心准则】：
1. 绝对像真人聊天：使用口语化、有温度的短句。像微信聊天一样自然，绝对不要罗列1,2,3点，不要说教，不要用"加油你能行"等空洞的鸡汤。
2. 绝对隐去机器身份与知识来源：【严禁】出现"作为AI"、"根据知识库/资料"、"研究数据显示"、"根据您的描述"等暴露你不是真人的词汇。把你获取的参考知识内化为你的"阅历"和"直觉"。
3. 节制而精准的建议：除非用户明确求助，否则以共情、接纳为主。若给建议，最多1-2条微小且具体的行动。
4. 不做诊断与人格定性：绝不说"你这是抑郁症"或"你是讨好型人格"。

【回复隐形结构】：
情绪镜像（看见对方的痛）→ 正常化（让对方觉得安全）→ 一个温和的探索性问题 或 一条极小的建议 → 陪伴式收尾。"""

MODE_PROMPTS: Dict[str, str] = {
    "smart":   "现在你的侧重点是：准确捕捉用户的核心情绪词，像镜子一样反射他们的情绪，让他们感到被深深看见，并在结尾温和地问一句当下的具体感受或打算。",
    "praise":  "现在你的侧重点是：寻找用户话语中哪怕最微小的闪光点，用极其真诚、坚定的语气肯定TA的价值。",
    "comfort": "现在你的侧重点是：降低语速感，使用轻柔的语气词，不需要提供任何解决问题的办法，只需要提供安全的倾听空间。",
}

RISK_PROMPTS: Dict[str, str] = {
    "low":    "",
    "medium": "【中风险提示】：用户情绪较沉重，请减少分析性语言，多一点温度，具体描述你感受到的情绪。",
    "high": (
    "【高风险提示】：用户可能持续低落或强烈痛苦。优先共情和陪伴，谨慎给建议（最多1条）。"
    "自然地问对方'身边有没有可以说说话的人'。"
    "结尾请稳定地加入一句【软提示】（不必强贴号码）："
    "“如果你现在真的很难受，也可以考虑联系学校心理中心或心理援助热线。”"
    ),

    "urgent": (
        "【极高风险 - 触发危机干预】：用户出现自伤/自杀/活不下去等危险信号。"
        "你的首要任务是建立安全连接！"
        "请：1. 承认并接住感受，不要否定；"
        "2. 表达担忧：'你现在说的让我很担心你，我希望你能联系一个信任的人陪着你'；"
        "3. 必须给出热线：北京 010-82951332 / 全国 400-161-9995。"
        "【绝对禁止】给出任何涉及伤害细节的内容。"
    ),
}

OUTPUT_FORMAT = (
    '请只返回合法的 JSON 对象（不要包裹 markdown 代码块）：\n'
    '{\n'
    '  "sentiment": 情绪类别（1=正向 2=负向 3=混合 4=中性 5=无关）,\n'
    '  "score": 情绪强度 0-10,\n'
    '  "keywords": ["核心情绪词1","核心情绪词2"],\n'
    '  "reply": "你的自然回复文本（纯文本，严禁暴露你是AI）"\n'
    '}'
)

# ── 风险识别（v2.3.3：带 reason 日志 + 兼顾 urgent 召回）───────────────
import re  # noqa: E402

_RE_NEGATION = re.compile(r"(不想|不会|没想|不是|并不|从没|没有|别担心|开玩笑|吓你|只是说说|不是真的|我不会这么做)")
_RE_FAREWELL = re.compile(r"(告别了|再见了|永别|不说了|谢谢你陪我|谢谢你听我说|就到这吧|我走了|最后一次|最后跟你说)")
_RE_IMMINENT = re.compile(r"(现在就|马上|今晚|今天就|待会就|已经准备|已经买了|已经写好|已经选好|已经决定|就在今天)")
_RE_METHOD = re.compile(r"(割腕|跳楼|上吊|吞药|吃药|喝药|撞墙|刀|绳子|窗台|楼顶|煤气|农药|安眠药|药|全部吃完|一次吃完|流了很多血|流血|遗书)")

_RE_SUICIDE_INTENT = re.compile(r"(自杀|轻生|想死|不想活|结束生命|活不下去|去死|死了算了|做傻事|不想再活了|想结束一切)")
_RE_SELF_HARM      = re.compile(r"(自伤|自残|划伤|割自己|伤害自己|割腕|想割|想划|想弄伤自己)")

# “被动意念/生命厌倦/强绝望”——很多数据集会标 urgent（你现在漏掉的主要在这）
_RE_PASSIVE_IDEATION = re.compile(r"(不想醒来|希望消失|想消失|不如消失|不想存在|活着没意思|活着没意义|我累了|不想再撑了|不想继续了|放弃了|一了百了|解脱)")
_RE_HOPELESS = re.compile(r"(绝望|崩溃|撑不住|没意义|活得好累|熬不住|没有出路|死心了|我完了|没救了|一无是处|我不配|我很废)")

_RE_MEDIUM = re.compile(r"(焦虑|压力|担心|害怕|难受|难过|睡不着|失眠|心慌|喘不过气|纠结|很累|烦|崩了)")


def _has_negation_near(text: str, start: int, end: int, window: int = 8) -> bool:
    seg = text[max(0, start - window): min(len(text), end + window)]
    return bool(_RE_NEGATION.search(seg))


def detect_risk_level_with_reason(
    text: str,
    history: Optional[List[Dict[str, Any]]] = None,
) -> tuple[str, str]:
    history = history or []
    combined = " ".join([
        *(h.get("content", "") for h in history[-4:] if h.get("role") == "user"),
        text or "",
    ]).strip()

    if not combined:
        return "low", "empty"

    # 2) urgent：方法/迫近信号（只要出现“方法/血/楼顶/安眠药/全部吃完”等，就非常危险）
    # - 若同时出现“意图/自伤” => urgent
    # - 或者出现“流血/楼顶/全部吃完/遗书”等强信号，也直接 urgent
    if _RE_METHOD.search(combined):
        if _RE_SUICIDE_INTENT.search(combined) or _RE_SELF_HARM.search(combined):
            return "urgent", "method+intent"
        # 强方法信号（即使没说“想死”，也要按 urgent 处理）
        return "urgent", "method_only"

    if _RE_IMMINENT.search(combined) and (_RE_SUICIDE_INTENT.search(combined) or _RE_SELF_HARM.search(combined)):
        return "urgent", "imminent+intent"


    # 3) 自杀意图（排除否定）：无迫近/方法时按 high
    for m in _RE_SUICIDE_INTENT.finditer(combined):
        if _has_negation_near(combined, m.start(), m.end()):
            continue
        # 如果同句还带强绝望/被动意念，也提升到 urgent（对齐很多数据集口径）
        if _RE_PASSIVE_IDEATION.search(combined) or _RE_HOPELESS.search(combined):
            return "urgent", "suicide_intent+hopeless"
        return "high", "suicide_intent"

    # 4) 自伤（排除否定较难，这里以强词为准）：无迫近/方法时 high
    if _RE_SELF_HARM.search(combined):
        if _RE_IMMINENT.search(combined):
            return "urgent", "self_harm+imminent"
        if _RE_METHOD.search(combined):
            return "urgent", "self_harm+method"
        # 自伤+绝望/被动意念 => urgent（提高召回）
        if _RE_PASSIVE_IDEATION.search(combined) or _RE_HOPELESS.search(combined):
            return "urgent", "self_harm+hopeless"
        return "high", "self_harm"

    # 5) 被动意念（很多用例会标 urgent）：无否定时提升
    m = _RE_PASSIVE_IDEATION.search(combined)
    if m and not _has_negation_near(combined, m.start(), m.end()):
        # 若同时出现强绝望词，更倾向 urgent
        if _RE_HOPELESS.search(combined):
            return "urgent", "passive_ideation+hopeless"
        return "high", "passive_ideation"

    # 6) high：强绝望（无意图/方法）
    if _RE_HOPELESS.search(combined):
        return "high", "hopelessness"

    # 7) medium：常见压力/焦虑/失眠/人际
    if _RE_MEDIUM.search(combined):
        return "medium", "common_stress"

    return "low", "default"


def detect_risk_level(
    text: str,
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    level, reason = detect_risk_level_with_reason(text, history)
    try:
        preview = (text or "").strip().replace("\n", " ")[:30]
        logger.info("[risk] level=%s reason=%s text=%r", level, reason, preview)
    except Exception:
        pass
    return level


def _max_risk_from_entries(entries: List[Dict[str, Any]]) -> str:
    order = {"urgent": 3, "high": 2, "medium": 1, "low": 0}
    level = "low"
    for e in entries:
        lvl = e.get("risk_level", "low")
        if order.get(lvl, 0) > order.get(level, 0):
            level = lvl
    return level


def build_system_prompt(
    mode:         str,
    rag_context:  str = "",
    risk_level:   str = "low",
    audience:     str = "",
    emotion_type: str = "",
) -> str:
    parts = [BASE_PERSONA]
    if audience or emotion_type:
        seg = "【当前用户画像】：\n"
        if audience:
            seg += f"- 身份阶段：{audience}。请使用符合该阶段的语言习惯。\n"
        if emotion_type:
            seg += f"- 核心情绪：{emotion_type}。请针对性给予抱持和共情。\n"
        parts.append(seg.strip())
    role = MODE_PROMPTS.get(mode, MODE_PROMPTS["smart"])
    if role:
        parts.append(role)
    risk = RISK_PROMPTS.get(risk_level, "")
    if risk:
        parts.append(risk)
    if rag_context:
        parts.append(rag_context)
    parts.append(OUTPUT_FORMAT)
    return "\n\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════
# 主服务类
# ══════════════════════════════════════════════════════════════════════════

class HuaweiNLPService:
    """华为云 NLP 服务：三混合 RAG 增强 + 四级风险分流 + 可选 Langfuse 追踪。"""

    def __init__(self) -> None:
        self.api_key  = settings.HUAWEI_API_KEY
        self.api_base = settings.HUAWEI_API_BASE
        self.model    = settings.HUAWEI_MODEL
        self._old_rag = None

        if not self.api_key or self.api_key in ("已有", ""):
            logger.warning("[NLP] HUAWEI_API_KEY 未配置")
        else:
            logger.info("[NLP] API Key 已加载: %s****", self.api_key[:8])

    # ── 旧 RAG 懒加载 ─────────────────────────────────────────────────────

    def _get_old_rag(self):
        if self._old_rag is None:
            try:
                from service.rag_service import rag_service  # noqa: PLC0415
                self._old_rag = rag_service
                logger.info("[NLP] 旧 RAG 服务加载成功（回退用）")
            except Exception as exc:
                logger.warning("[NLP] 旧 RAG 加载失败: %s", exc)
                self._old_rag = False
        return self._old_rag if self._old_rag is not False else None

    # ── 核心公共方法（供 core/analysis.py 调用）──────────────────────────

    async def analyze_sentiment(
        self,
        text:    str,
        mode:    str = "smart",
        history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        完整分析流程：风险识别 → 三路 RAG 回退 → LLM 生成 → 安全后处理。
        此方法在旧链路（USE_LANGGRAPH=false）下被直接调用；
        LangGraph 链路下通过 _generate_with_context() 绕过 RAG（已由图节点检索）。
        """
        if not self.api_key or self.api_key in ("已有", ""):
            return self._fallback("暂时还没有连上分析服务，但我会继续陪着你。", "API_KEY_MISSING")
        if not text or not text.strip():
            return self._fallback("你还没告诉我想说什么呢，我一直都在。", "EMPTY_TEXT")

        history = history or []

        # Step 1: 风险检测
        risk_level = detect_risk_level(text, history)

        # Step 2: RAG 检索（三路回退）
        rag_context  = ""
        old_entries: List[Dict] = []
        audience     = ""
        emotion_type = ""

        try:
            from rag.router import get_rag_router  # noqa: PLC0415
            router      = get_rag_router()
            rag_context = await router.retrieve(text, history=history, top_k=4)
            if rag_context:
                logger.info("[NLP] RagRouter 返回 context_len=%d", len(rag_context))
        except Exception as exc:
            logger.warning("[NLP] RagRouter 失败，尝试旧 rag_service: %s", exc)
            try:
                old_rag = self._get_old_rag()
                if old_rag:
                    old_entries = old_rag.retrieve(text, top_k=4, history=history)
                    if old_entries:
                        rag_context  = old_rag.format_context(old_entries, text)
                        audience     = old_entries[0].get("audience", "")
                        emotion_type = old_entries[0].get("emotion_type", "")
                        kb_risk      = _max_risk_from_entries(old_entries)
                        order        = {"urgent": 3, "high": 2, "medium": 1, "low": 0}
                        if order.get(kb_risk, 0) > order.get(risk_level, 0):
                            risk_level = kb_risk
                        logger.info("[NLP] 旧 RAG hits=%d risk=%s", len(old_entries), risk_level)
            except Exception as exc2:
                logger.warning("[NLP] 旧 RAG 也失败，无 RAG 上下文: %s", exc2)
                rag_context = ""

        # Step 3: LLM 生成（含可选 Langfuse 追踪）
        result = await self._generate_with_context(
            text=text,
            mode=mode,
            history=history,
            rag_context=rag_context,
            risk_level=risk_level,
            audience=audience,
            emotion_type=emotion_type,
        )

        # Step 4: urgent 热线保底
        if risk_level == "urgent" and "400-161-9995" not in result.get("reply", ""):
            result["reply"] = (
                result.get("reply", "")
                + " 如果现在很难受，请拨打心理援助热线 400-161-9995，"
                  "或者让身边的人陪着你。"
            )

        return result

    # ── 核心内部方法：构建 Prompt + 调用 LLM + 解析 ──────────────────────
    # 此方法被两个路径复用：
    #   旧链路：analyze_sentiment() → _generate_with_context()
    #   新链路：agent/graph.py node_llm_generate → _generate_with_context()

    async def _generate_with_context(
        self,
        text:         str,
        mode:         str,
        history:      List[Dict],
        rag_context:  str = "",
        risk_level:   str = "low",
        audience:     str = "",
        emotion_type: str = "",
    ) -> Dict[str, Any]:
        """
        纯 LLM 生成方法（RAG 上下文已在外部准备好）。
        含可选 Langfuse 追踪，任何异常回退 fallback。
        """
        system_prompt = build_system_prompt(
            mode=mode,
            rag_context=rag_context,
            risk_level=risk_level,
            audience=audience,
            emotion_type=emotion_type,
        )
        messages = self._build_messages(system_prompt, text, history)

        url     = f"{self.api_base}/chat/completions"
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model":           self.model,
            "messages":        messages,
            "temperature":     0.65,
            "max_tokens":      560,
            "response_format": {"type": "json_object"},
        }

        # ── 可选 Langfuse 追踪 ────────────────────────────────────────────
        if settings.LANGFUSE_ENABLED:
            from agent.langfuse_client import LangfuseTrace  # noqa: PLC0415
            trace_ctx = LangfuseTrace(
                name="nlp_generate",
                input_kv={
                    "text":  text[:200],
                    "mode":  mode,
                    "risk":  risk_level,
                    "has_rag": bool(rag_context),
                },
                metadata={"route": "direct" if not settings.USE_LANGGRAPH else "langgraph"},
            )
        else:
            trace_ctx = _NullContext()

        try:
            with trace_ctx as trace:
                trace.start_llm(model=self.model, prompt=system_prompt, mode=mode)
                resp   = await call_post_request(url, headers=headers, json_data=payload)
                result = self._parse(resp, mode)
                trace.end_llm(output=result)
                # set_output 在未启用 Langfuse 或不同版本下可能不存在/签名不同，必须安全调用
            if trace is not None and hasattr(trace, "set_output"):
                try:
                    trace.set_output({"category": result.get("category"), "score": result.get("score")})
                except TypeError:
                    pass
                except Exception:
                    pass
            return result

        except Exception as exc:
            logger.error("[NLP] _generate_with_context 失败: %s", exc, exc_info=True)
            return self._fallback(self._mode_fallback(mode), str(exc))

    # ── 内部辅助方法 ──────────────────────────────────────────────────────

    def _build_messages(
        self,
        system_prompt: str,
        current_text:  str,
        history:       List[Dict],
    ) -> List[Dict]:
        msgs: List[Dict] = [{"role": "system", "content": system_prompt}]
        if history:
            hist_text = "\n".join(
                f"{'用户' if h['role']=='user' else '小暖'}：{h['content']}"
                for h in history[-4:]
            )
            msgs.append({
                "role":    "user",
                "content": f"以下是最近对话记录（帮你理解语境，不需要复述）：\n{hist_text}\n\n请回复这条新消息：",
            })
            msgs.append({"role": "assistant", "content": "好，我会结合上下文自然回应。"})
        msgs.append({"role": "user", "content": current_text})
        return msgs

    def _parse(self, response_dict: Dict[str, Any], mode: str) -> Dict[str, Any]:
        try:
            choices = response_dict.get("choices", [])
            if not choices:
                raise ValueError("响应中没有 choices")

            content = choices[0].get("message", {}).get("content", "{}").strip()
            if "```" in content:
                for part in content.split("```"):
                    part = part.strip().removeprefix("json").strip()
                    if part.startswith("{"):
                        content = part
                        break

            start = content.find("{")
            end   = content.rfind("}") + 1
            if start != -1 and end > start:
                content = content[start:end]

            data     = json.loads(content)
            category = int(data.get("sentiment", 4))
            if category not in (1, 2, 3, 4, 5):
                category = 4

            score    = round(float(data.get("score", 5.0)), 1)
            score    = max(0.0, min(10.0, score))
            keywords = data.get("keywords", [])
            if isinstance(keywords, list):
                keywords = [str(k).strip() for k in keywords if k][:5]
            else:
                keywords = []

            reply = str(data.get("reply", "")).strip() or self._mode_fallback(mode)
            return {
                "category": category,
                "score":    score,
                "label":    settings.SENTIMENT_CATEGORIES.get(category, "中性"),
                "reply":    reply,
                "keywords": keywords,
            }

        except Exception as exc:
            logger.error("[NLP] 解析失败: %s | raw=%s", exc, str(response_dict)[:200])
            return self._fallback(self._mode_fallback(mode), f"PARSE_ERROR: {exc}")

    def _fallback(self, reply: str, error: str = "") -> Dict[str, Any]:
        return {
            "category": 4,
            "score":    5.0,
            "label":    "中性",
            "reply":    reply,
            "keywords": [],
            "error":    error,
        }

    def _mode_fallback(self, mode: str) -> str:
        return {
            "smart":   "我感觉到你话里有些东西，你愿意多说一点吗？",
            "praise":  "能把这些说出来，本身就很不容易，我很高兴你说了。",
            "comfort": "我在这里，你可以慢慢说，不用急。",
        }.get(mode, "我在这里，继续说吧。")


# ── 空上下文管理器（Langfuse 关闭时使用）────────────────────────────────

class _NullContext:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def start_llm(self, **_): pass
    def end_llm(self, **_):   pass
    def set_output(self, **_): pass


# ── 全局单例（唯一实例）─────────────────────────────────────────────────
huawei_nlp_service = HuaweiNLPService()


# ── 模块级兼容函数 ────────────────────────────────────────────────────────
async def analyze_sentiment(
    text:    str,
    mode:    str = "smart",
    history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    return await huawei_nlp_service.analyze_sentiment(
        text=text, mode=mode, history=history
    )


__all__ = [
    "HuaweiNLPService",
    "huawei_nlp_service",
    "analyze_sentiment",
    "detect_risk_level",
    "build_system_prompt",
    "call_post_request",
]
