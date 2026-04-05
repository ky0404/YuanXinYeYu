"""core/analysis.py
情绪分析核心逻辑。

v2.3 变更：
  - 在 analyze() 方法开头新增 LangGraph 可选路径（USE_LANGGRAPH=true 时启用）
  - LangGraph 任何异常 → 立即 fallback 到原有链路，行为不变
  - 高危纠偏逻辑、guide 生成、模板兜底等全部保留不变
"""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional

from service.huawei_nlp import huawei_nlp_service

logger = logging.getLogger(__name__)


class EmotionAnalyzer:
    """情绪分析器 — AI 回复优先，模板兜底。"""

    GUIDE_TEMPLATES = {
        1: [
            "保持这份好心情，把快乐分享给身边的人吧～",
            "你的积极态度很有感染力！继续发光发热✨",
            "好心情是最好的礼物，愿它一直陪伴你～",
            "今天的你，值得被好好对待！",
        ],
        2: [
            "情绪是信使，它在告诉你一些重要的事。先好好休息，等准备好了再慢慢面对～",
            "允许自己难过，不用逼着自己立刻振作。你有权利感受自己的感受。",
            "难过的时候可以找一个信任的人说说话，说出来会轻松一点～",
            "心情沉重的时候，走出去吹吹风、听听音乐，给自己一些喘息的空间。",
            "你已经很努力了，偶尔低落是正常的，不用对自己太苛刻。",
            "今晚好好睡一觉，明天的阳光会不一样。",
        ],
        3: [
            "复杂的心情说明你在认真感受生活，慢慢来，给自己一些时间梳理～",
            "矛盾的感受很正常，你不需要立刻想清楚，顺其自然也是一种智慧。",
            "接纳自己所有的情绪，喜悦和难过都是真实的你，都值得被看见。",
        ],
        4: [
            "平静的心态很难得，愿你继续保持这份从容～",
            "平静也是一种力量，愿岁月待你温柔。",
            "生活就是这样，平淡中有它独特的美。",
        ],
        5: [
            "感谢你的分享，有什么想聊的，随时都可以～",
            "我会一直在这里，有任何感受都可以和我说。",
        ],
    }

    async def analyze(
        self,
        text:    str,
        mode:    str = "smart",
        history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("输入文本不能为空")

        history = history or []

        # ════════════════════════════════════════════════════════════════
        # 可选路径：LangGraph 有状态工作流
        # 默认 USE_LANGGRAPH=false，完全不影响现有链路。
        # 开启后：任何异常立即 fallback 到下方旧链路，行为对外不变。
        # ════════════════════════════════════════════════════════════════
        from config.settings import settings  # noqa: PLC0415（避免循环导入）

        if settings.USE_LANGGRAPH:
            try:
                from agent.graph import run_agent  # noqa: PLC0415
                sentiment_result = await run_agent(text, mode, history)
                logger.info("[Analysis] LangGraph 链路成功 | mode=%s", mode)
                # 复用下方的后处理逻辑（高危纠偏 + guide 生成）
                return self._post_process(text, mode, sentiment_result)
            except Exception as exc:
                logger.warning(
                    "[Analysis] LangGraph 失败，回退旧链路: %s",
                    exc,
                    exc_info=False,   # 不打完整 traceback，避免日志洪水
                )
                # ↓ 继续执行旧链路（fall through）

        # ════════════════════════════════════════════════════════════════
        # 旧链路（原有逻辑，完全不变）
        # ════════════════════════════════════════════════════════════════
        sentiment_result = await huawei_nlp_service.analyze_sentiment(
            text=text, mode=mode, history=history
        )
        return self._post_process(text, mode, sentiment_result)

    def _post_process(
        self,
        text:             str,
        mode:             str,
        sentiment_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        通用后处理（两条链路共用）：
          1. 高危文本纠偏（强制负面 + 高强度）
          2. guide 生成
          3. 组装最终结果字典
        """
        # ── 高危文本纠偏：避免模型把自伤话题判为"不相关" ───────────────
        _high_risk_kw = (
            "自伤","自杀","轻生","想死","不想活",
            "活不下去","结束生命","割腕","跳楼",
        )
        if any(k in text for k in _high_risk_kw):
            sentiment_result["category"] = 2
            sentiment_result["label"]    = "负面"
            sentiment_result["score"]    = max(
                float(sentiment_result.get("score", 8.0)), 8.0
            )

        category = sentiment_result["category"]
        score    = sentiment_result["score"]

        ai_reply = sentiment_result.get("reply", "")
        if not ai_reply:
            ai_reply = self._mode_fallback_reply(mode, category)

        keywords   = sentiment_result.get("keywords", [])
        guide_text = self._generate_guide(category=category, score=score)

        result = {
            "sentiment_category": category,
            "sentiment_score":    score,
            "sentiment_label":    sentiment_result.get("label", "中性"),
            "reply":              ai_reply,
            "guide":              guide_text,
            "keywords":           keywords,
            "mode":               mode,
        }

        logger.info(
            "分析完成 | label=%s score=%.1f keywords=%s mode=%s",
            result["sentiment_label"], score, keywords, mode,
        )
        return result

    def _generate_guide(self, category: int, score: float) -> str:
        templates = self.GUIDE_TEMPLATES.get(category, self.GUIDE_TEMPLATES[4])
        if category == 2 and score < 3.0:
            return random.choice([
                "你现在承受的压力真的很大。先照顾好自己的身体，如果感觉很难独自承受，也可以寻求专业帮助——这不是软弱，是勇敢。",
                "感觉撑不住的时候，先停下来，深呼吸几次。你不是一个人，总有人愿意陪你一起面对。",
            ])
        guide = random.choice(templates)
        return guide[:200] + "..." if len(guide) > 200 else guide

    def _mode_fallback_reply(self, mode: str, category: int) -> str:
        fallbacks = {
            "smart": {
                1: "你的好心情透过文字都感染到我了！这份积极很珍贵，继续保持～",
                2: "我感受到了你话语里的沉重，这种感受是真实的，不用急着让自己好起来。",
                4: "嗯，我在听。有什么想多说的吗？",
            },
            "praise": {
                1: "哇！你今天状态超棒的，这份快乐是你应得的！💖",
                2: "你愿意说出心里的感受，这本身就很了不起！感知自己的情绪是一种很珍贵的能力 💪",
                4: "光是认真生活这件事，就值得被夸！你每天都在好好存在着，很棒✨",
            },
            "comfort": {
                1: "你开心我也开心，就是这样～",
                2: "我听到了，你现在不太好受...没关系，我就陪着你。",
                4: "嗯，我在这里，你慢慢说...",
            },
        }
        mode_fallback = fallbacks.get(mode, fallbacks["smart"])
        return mode_fallback.get(category, mode_fallback.get(4, "我在这里听你说～"))


# 全局分析器实例
emotion_analyzer = EmotionAnalyzer()
