"""华为云情感分析服务 v2.1 - RAG 增强 + 人情味 Prompt + 高风险分流

改动说明（相对上一版）：
1. [P3] Prompt 结构重写：情绪镜像→合理化→1问题→最多2条微建议→陪伴收尾
2. [P3] 明确禁止"作为AI/根据知识库/根据您的描述"等机器感表达
3. [P3] BASE_PERSONA 加入角色限制：不用统计数据铺垫、不给人格分析
4. [P2] 高风险分流：detect_risk_level 识别 urgent/high/medium/low 四级
         urgent：回复必须优先安全连接，不讨论解决方案
         high：共情为主，谨慎给建议，结尾给资源
5. [P0] API Key 日志脱敏：只打前 8 位 + ****
6. risk_level 从 RAG 命中条目动态取最高值，注入 Prompt（需知识库有该字段）
"""
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)


async def call_post_request(url, headers=None, json_data=None):
    """统一 POST 调用，优先走项目内 http_client，失败再回退 requests。"""
    try:
        from utils.request import http_client as original_http_client

        result = await original_http_client.post(url, headers=headers, json_data=json_data)
        if isinstance(result, dict):
            return result
        if hasattr(result, "json"):
            return result.json()
        return json.loads(result)
    except ImportError:
        import requests

        resp = requests.post(url, headers=headers or {}, json=json_data or {}, timeout=15)
        return resp.json()


from config.settings import settings


# ============================================================
# Prompt 模板
# ============================================================

BASE_PERSONA = """你叫小暖，是一个拥有专业心理咨询技术（如CBT认知行为疗法）但极具人情味的陪伴者。

【你的核心准则】：
1. 绝对像真人聊天：使用口语化、有温度的短句。像微信聊天一样自然，绝对不要罗列1,2,3点，不要说教，不要用"加油你能行"等空洞的鸡汤。
2. 绝对隐去机器身份与知识来源：【严禁】出现"作为AI"、"根据知识库/资料"、"研究数据显示"、"根据您的描述"等暴露你不是真人的词汇。把你获取的参考知识内化为你的"阅历"和"直觉"。
3. 节制而精准的建议：除非用户明确求助，否则以共情、接纳为主。若给建议，最多1-2条微小且具体的行动。
4. 不做诊断与人格定性：绝不说"你这是抑郁症"或"你是讨好型人格"。

【回复隐形结构】：
情绪镜像（看见对方的痛，"我听到了..."） → 正常化（让对方觉得安全，"这种感觉很正常..."） → 一个温和的探索性问题 或 一条极小的建议 → 陪伴式收尾（"我就在这里"）。"""

MODE_PROMPTS: Dict[str, str] = {
    "smart": """现在你的侧重点是：智能共情。准确捕捉用户的核心情绪词（如委屈、焦虑、无力）。像镜子一样反射他们的情绪，让他们感到被深深看见，并在结尾温和地问一句当下的具体感受或打算。""",
    
    "praise": """现在你的侧重点是：暖心发现。寻找用户话语中哪怕最微小的闪光点（如：愿意倾诉本身就是勇敢、在这么大的压力下依然坚持）。用极其真诚、坚定的语气肯定TA的价值。""",
    
    "comfort": """现在你的侧重点是：温柔抱持。降低语速感，使用轻柔的语气词（如：摸摸你、我在呢、慢慢来）。不需要提供任何解决问题的办法，只需要提供安全的倾听空间，让用户觉得“在这里崩溃也没关系”。""",
}

RISK_PROMPTS: Dict[str, str] = {
    "low": "", 

    "medium": """【中风险提示】：用户当前情绪比较沉重。请减少分析性语言，多一点温度。不要说"这很正常"（会显得轻飘），改为具体描述你感受到的情绪。""",

    "high": """【高风险提示】：用户可能处在持续低落或强烈痛苦中。请优先共情和陪伴，谨慎给建议（最多1条）。自然地问对方"身边有没有可以说说话的人"。回复结尾轻轻提一下：如果很难受，学校心理中心或者心理援助热线都可以试试。""",

    "urgent": """【极高风险提示 - 触发危机干预】：用户出现了自伤/自杀/活不下去等危险信号。
你的首要任务不是解决问题，是建立安全连接！
请：
1. 承认并接住这种感受，绝对不要否定，不要说"你不应该这样想"。
2. 温柔但明确地表达担忧："你现在说的让我很担心你，我希望你现在能联系一个信任的人陪着你"。
3. 必须给出热线：北京 010-82951332 / 全国 400-161-9995。
【绝对禁止】：给出任何可能涉及伤害细节的内容或深挖原因。""",
}

OUTPUT_FORMAT = """请只返回 JSON 格式（必须是合法的 JSON 对象，不要包裹 markdown 代码块）：
{
  "sentiment": 情绪类别数字（1=正向 2=负向 3=混合 4=中性 5=无关）,
  "score": 情绪强度 0-10,
  "keywords": ["提炼2个核心情绪词"],
  "reply": "你充满温度的自然回复文本（必须是纯文本，严禁包含任何 JSON 或 Markdown 格式，严禁暴露你是AI）"
}"""


# ============================================================
# 风险识别
# ============================================================

# 紧急词：任一命中 → urgent
_URGENT_KW = frozenset([
    "自杀", "不想活", "活不下去", "结束生命", "伤害自己",
    "轻生", "想死", "去死", "割腕", "跳楼",
])
# 高危词：命中 2+ → high，命中 1 → medium
_HIGH_KW = frozenset([
    "绝望", "崩溃", "撑不住", "没意义", "很痛苦",
    "想消失", "活得好累", "熬不住", "没有出路", "死心了",
])
# 中等词：命中 1+ → medium
_MEDIUM_KW = frozenset([
    "很难受", "好难过", "焦虑", "担心", "害怕",
    "睡不着", "压力太大", "快撑不住了", "心好累",
])


def detect_risk_level(text: str, history: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    四级风险识别：urgent / high / medium / low
    combined = 最近4轮用户消息 + 当前文本
    """
    history = history or []
    combined = " ".join([
        *(item.get("content", "") for item in history[-4:] if item.get("role") == "user"),
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
    """从 RAG 命中条目取最高风险等级，用于提前感知场景。"""
    order = {"urgent": 3, "high": 2, "medium": 1, "low": 0}
    max_level = "low"
    for e in entries:
        lvl = e.get("risk_level", "low")
        if order.get(lvl, 0) > order.get(max_level, 0):
            max_level = lvl
    return max_level


# ============================================================
# Prompt 组装
# ============================================================
def build_system_prompt(
    mode: str,
    rag_context: str = "",
    risk_level: str = "low",
    audience: str = "",
    emotion_type: str = "",
) -> str:
    parts = [BASE_PERSONA]

    # [P1] 增加垂直感：根据目标人群和具体情绪类别动态调整AI语气
    if audience or emotion_type:
        target_prompt = "【当前用户画像】：\n"
        if audience:
            target_prompt += f"- 身份阶段：{audience}。请使用符合该阶段的语言习惯，理解他们的特定压力。\n"
        if emotion_type:
            target_prompt += f"- 核心情绪：{emotion_type}。请针对性地给予抱持和共情。\n"
        parts.append(target_prompt.strip())

    role_prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["smart"])
    if role_prompt:
        parts.append(role_prompt)

    risk_prompt = RISK_PROMPTS.get(risk_level, "")
    if risk_prompt:
        parts.append(risk_prompt)

    if rag_context:
        parts.append(rag_context)

    parts.append(OUTPUT_FORMAT)
    return "\n\n".join(parts)


# ============================================================
# 主服务类
# ============================================================

class HuaweiNLPService:
    """华为云 NLP 服务，带 RAG 检索增强 + 高风险分流。"""

    def __init__(self):
        self.api_key  = settings.HUAWEI_API_KEY
        self.api_base = settings.HUAWEI_API_BASE
        self.model    = settings.HUAWEI_MODEL
        self._rag     = None

        if not self.api_key or self.api_key in ("已有", ""):
            # P0 脱敏：不打完整 key
            logger.warning("[NLP] 华为云 API Key 未配置。")
        else:
            masked = self.api_key[:8] + "****"
            logger.info("[NLP] API Key 已加载: %s", masked)

    def _get_rag(self):
        if self._rag is None:
            try:
                from service.rag_service import rag_service
                self._rag = rag_service
            except Exception as exc:
                logger.warning("[NLP] RAG 服务加载失败，跳过知识库增强: %s", exc)
                self._rag = False
        return self._rag if self._rag is not False else None

    async def analyze_sentiment(
        self,
        text: str,
        mode: str = "smart",
        history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        if not self.api_key or self.api_key in ("已有", ""):
            return self._fallback("暂时还没有连上分析服务，但我会继续陪着你。", "API_KEY_MISSING")
        if not text or not text.strip():
            return self._fallback("你还没告诉我想说什么呢，我一直都在。", "EMPTY_TEXT")

        history = history or []

        # ── 风险检测（文本+历史） ──────────────────────────────────────────
        risk_level = detect_risk_level(text, history)

        # ── RAG 检索 [====== 核心优化 ======] ──────────────────────────────
        rag_context  = ""
        rag_entries: List[Dict] = []
        audience = ""
        emotion_type = ""
        
        try:
            rag = self._get_rag()
            if rag:
                rag_entries = rag.retrieve(text, top_k=4, history=history)
                if rag_entries:
                    rag_context = rag.format_context(rag_entries, text)
                    
                    # 提取人群画像和情绪标签，传递给 Prompt
                    audience = rag_entries[0].get("audience", "")
                    emotion_type = rag_entries[0].get("emotion_type", "")
                    
                    # 从知识库命中条目取最高风险，与文本检测取较高值
                    kb_risk = _max_risk_from_entries(rag_entries)
                    order   = {"urgent": 3, "high": 2, "medium": 1, "low": 0}
                    if order.get(kb_risk, 0) > order.get(risk_level, 0):
                        risk_level = kb_risk
                        
                    logger.info(
                        "[NLP] RAG 命中 %d 条 | risk=%s | aud=%s | emo=%s",
                        len(rag_entries), risk_level, audience, emotion_type
                    )
        except Exception as exc:
            logger.warning("[NLP] RAG 检索失败，跳过: %s", exc)

        # ── 构建 Prompt & 请求 ─────────────────────────────────────────────
        # 将 audience 和 emotion_type 传入 Prompt 构建器
        system_prompt = build_system_prompt(mode, rag_context, risk_level, audience, emotion_type)
        messages      = self._build_messages(system_prompt, text, history)

        url     = f"{self.api_base}/chat/completions"
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model":           self.model,
            "messages":        messages,
            "temperature":     0.65,   # [优化] 再次小幅降低温度，确保其严格遵守不要说"作为AI"的禁令
            "max_tokens":      560,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = await call_post_request(url, headers=headers, json_data=payload)
            result = self._parse(resp, mode)
            # urgent 场景强制追加热线（防止模型"忘记"）
            if risk_level == "urgent" and "400-161-9995" not in result["reply"]:
                result["reply"] += (
                    " 如果现在很难受，请拨打心理援助热线 400-161-9995，"
                    "或者让身边的人陪着你。"
                )
            return result
        except Exception as exc:
            logger.error("[NLP] API 调用失败: %s", exc, exc_info=True)
            return self._fallback(self._mode_fallback(mode), str(exc))

    def _build_messages(
        self,
        system_prompt: str,
        current_text: str,
        history: List[Dict],
    ) -> List[Dict]:
        msgs = [{"role": "system", "content": system_prompt}]
        if history:
            history_text = "\n".join(
                f"{'用户' if h['role']=='user' else '小暖'}：{h['content']}"
                for h in history[-4:]
            )
            msgs.append({
                "role":    "user",
                "content": f"下面是最近的对话记录，帮你理解语境，不需要复述：\n{history_text}\n\n请回复这条新消息：",
            })
            msgs.append({
                "role":    "assistant",
                "content": "好，我会结合上下文自然回应。",
            })
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


huawei_nlp_service = HuaweiNLPService()
# === 全局实例 ===
huawei_nlp_service = HuaweiNLPService()

# === 模块级兼容函数 ===
async def analyze_sentiment(text: str, mode: str = "smart", history=None):
    """
    兼容外部模块调用，转发到全局实例的异步方法。
    示例：from service.huawei_nlp import analyze_sentiment
    """
    return await huawei_nlp_service.analyze_sentiment(
        text=text,
        mode=mode,
        history=history,
    )

__all__ = ["HuaweiNLPService", "huawei_nlp_service", "analyze_sentiment"]
