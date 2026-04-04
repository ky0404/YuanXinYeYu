"""service/huawei_nlp.py v2.2
修复：
  1. 底部 huawei_nlp_service 只实例化一次
  2. call_post_request：捕获网络/超时异常并回退 requests
  3. analyze_sentiment：优先走 RagRouter，失败回退旧 rag_service，再失败 rag_context=""
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# ── 路径保护（兼容直接运行场景）─────────────────────────────────────────
_current = os.path.dirname(os.path.abspath(__file__))
_root    = os.path.dirname(_current)
if _root not in sys.path:
    sys.path.insert(0, _root)

logger = logging.getLogger(__name__)

from config.settings import settings  # noqa: E402


# ── 统一 POST 调用（修复：捕获网络/超时异常）────────────────────────────

async def call_post_request(
    url:       str,
    headers:   Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    优先使用 utils.http_client（带重试），任何异常回退到 requests 同步调用。
    捕获 ImportError 和网络/超时异常，保证不因 http_client 问题导致整体失败。
    """
    # 尝试异步 http_client
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

    # 同步 requests 回退
    import requests  # noqa: PLC0415

    resp = requests.post(
        url,
        headers=headers or {},
        json=json_data or {},
        timeout=settings.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════════

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
        "自然地问对方'身边有没有可以说说话的人'。结尾轻轻提：如果很难受，学校心理中心或心理援助热线都可以试试。"
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

# ── 风险识别 ──────────────────────────────────────────────────────────────

_URGENT_KW: frozenset = frozenset([
    "自杀", "不想活", "活不下去", "结束生命", "伤害自己",
    "轻生", "想死", "去死", "割腕", "跳楼",
])
_HIGH_KW: frozenset = frozenset([
    "绝望", "崩溃", "撑不住", "没意义", "很痛苦",
    "想消失", "活得好累", "熬不住", "没有出路", "死心了",
])
_MEDIUM_KW: frozenset = frozenset([
    "很难受", "好难过", "焦虑", "担心", "害怕",
    "睡不着", "压力太大", "快撑不住了", "心好累",
])


def detect_risk_level(text: str, history: Optional[List[Dict[str, Any]]] = None) -> str:
    history = history or []
    combined = " ".join([
        *(h.get("content", "") for h in history[-4:] if h.get("role") == "user"),
        text,
    ])
    if any(kw in combined for kw in _URGENT_KW):
        return "urgent"
    high_hits = sum(1 for kw in _HIGH_KW if kw in combined)
    if high_hits >= 2:
        return "high"
    if high_hits == 1:
        return "medium"
    if any(kw in combined for kw in _MEDIUM_KW):
        return "medium"
    return "low"


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
    rag_context:  str  = "",
    risk_level:   str  = "low",
    audience:     str  = "",
    emotion_type: str  = "",
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


# ═══════════════════════════════════════════════════════════════════════════
# 主服务类
# ═══════════════════════════════════════════════════════════════════════════

class HuaweiNLPService:
    """华为云 NLP 服务：三混合 RAG 增强 + 四级风险分流。"""

    def __init__(self) -> None:
        self.api_key  = settings.HUAWEI_API_KEY
        self.api_base = settings.HUAWEI_API_BASE
        self.model    = settings.HUAWEI_MODEL

        # 旧 RAG（sentence_transformers，作为 RagRouter 失败时的回退）
        self._old_rag = None

        if not self.api_key or self.api_key in ("已有", ""):
            logger.warning("[NLP] HUAWEI_API_KEY 未配置")
        else:
            logger.info("[NLP] API Key 已加载: %s****", self.api_key[:8])

    # ── RAG 懒加载 ────────────────────────────────────────────────────────

    def _get_old_rag(self):
        """懒加载旧 rag_service（sentence_transformers）。"""
        if self._old_rag is None:
            try:
                from service.rag_service import rag_service  # noqa: PLC0415
                self._old_rag = rag_service
                logger.info("[NLP] 旧 RAG 服务加载成功（回退用）")
            except Exception as exc:
                logger.warning("[NLP] 旧 RAG 加载失败: %s", exc)
                self._old_rag = False
        return self._old_rag if self._old_rag is not False else None

    # ── 核心分析 ──────────────────────────────────────────────────────────

    async def analyze_sentiment(
        self,
        text:    str,
        mode:    str = "smart",
        history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
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

        # 2a. 尝试新 RagRouter
        try:
            from rag.router import get_rag_router  # noqa: PLC0415
            router = get_rag_router()
            rag_context = await router.retrieve(text, history=history, top_k=4)
            if rag_context:
                logger.info("[NLP] RagRouter 返回 context_len=%d", len(rag_context))
        except Exception as exc:
            logger.warning("[NLP] RagRouter 失败，尝试旧 rag_service: %s", exc)

            # 2b. 回退到旧 rag_service
            try:
                old_rag = self._get_old_rag()
                if old_rag:
                    old_entries = old_rag.retrieve(text, top_k=4, history=history)
                    if old_entries:
                        rag_context  = old_rag.format_context(old_entries, text)
                        audience     = old_entries[0].get("audience", "")
                        emotion_type = old_entries[0].get("emotion_type", "")

                        kb_risk = _max_risk_from_entries(old_entries)
                        order   = {"urgent": 3, "high": 2, "medium": 1, "low": 0}
                        if order.get(kb_risk, 0) > order.get(risk_level, 0):
                            risk_level = kb_risk

                        logger.info(
                            "[NLP] 旧 RAG hits=%d risk=%s aud=%s",
                            len(old_entries), risk_level, audience,
                        )
            except Exception as exc2:
                logger.warning("[NLP] 旧 RAG 也失败，无 RAG 上下文: %s", exc2)
                rag_context = ""

        # Step 3: 构建 Prompt
        system_prompt = build_system_prompt(
            mode, rag_context, risk_level, audience, emotion_type
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

        try:
            resp   = await call_post_request(url, headers=headers, json_data=payload)
            result = self._parse(resp, mode)

            # urgent 场景强制追加热线（防模型遗漏）
            if risk_level == "urgent" and "400-161-9995" not in result["reply"]:
                result["reply"] += (
                    " 如果现在很难受，请拨打心理援助热线 400-161-9995，"
                    "或者让身边的人陪着你。"
                )
            return result

        except Exception as exc:
            logger.error("[NLP] API 调用失败: %s", exc, exc_info=True)
            return self._fallback(self._mode_fallback(mode), str(exc))

    # ── 内部方法 ──────────────────────────────────────────────────────────

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

            # 清理可能的 markdown 代码块
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


# ── 全局单例（只允许一个）───────────────────────────────────────────────
huawei_nlp_service = HuaweiNLPService()


# ── 模块级兼容函数（供其他模块 from service.huawei_nlp import analyze_sentiment）
async def analyze_sentiment(
    text:    str,
    mode:    str = "smart",
    history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    return await huawei_nlp_service.analyze_sentiment(text=text, mode=mode, history=history)


__all__ = ["HuaweiNLPService", "huawei_nlp_service", "analyze_sentiment"]
