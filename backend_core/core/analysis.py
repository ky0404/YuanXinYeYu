"""core/analysis.py v2.7
在 v2.4 基础上新增：
  - analyze() 增加可选 user_id 参数，透传给 run_agent()
  - 兼容旧调用方式（不传 user_id = None）
"""
from __future__ import annotations

import logging
import random
import time
from service.profile_service import load_profile
from typing import Any, Dict, List, Optional

from service.huawei_nlp import huawei_nlp_service

logger = logging.getLogger(__name__)


class EmotionAnalyzer:
    """情绪分析器 — AI 回复优先，模板兜底。"""

    _HIGH_RISK_KW = (
        "自伤", "自杀", "轻生", "想死", "不想活",
        "活不下去", "结束生命", "割腕", "跳楼",
    )
    _URGENT_KW = (
        "安眠药", "吃药轻生", "买了刀", "今晚就死",
        "不想活了就在今天", "跳下去", "已经割了",
    )

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
        user_id: Optional[int] = None,   # ✅ v2.7 新增可选参数
    ) -> Dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("输入文本不能为空")

        history = history or []
        t0 = time.monotonic()

        from config.settings import settings  # noqa: PLC0415

        if settings.USE_LANGGRAPH:
            try:
                from agent.graph import run_agent  # noqa: PLC0415
                # ✅ v2.7：透传 user_id（向下兼容，run_agent 默认值为 None）
                sentiment_result = await run_agent(text, mode, history, user_id=user_id)
                elapsed = int((time.monotonic() - t0) * 1000)
                logger.info("[Analysis] LangGraph 链路成功 | mode=%s latency=%dms user_id=%s",
                            mode, elapsed, user_id)
                return self._post_process(text, mode, sentiment_result, user_id=user_id)
            except Exception as exc:
                elapsed = int((time.monotonic() - t0) * 1000)
                logger.warning("[Analysis] LangGraph 失败(%dms)，回退旧链路: %s",
                               elapsed, exc, exc_info=False)

        sentiment_result = await huawei_nlp_service.analyze_sentiment(
            text=text, mode=mode, history=history
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info("[Analysis] 旧链路成功 | mode=%s latency=%dms", mode, elapsed)
        return self._post_process(text, mode, sentiment_result, user_id=user_id)

    def _post_process(
        self,
        text:             str,
        mode:             str,
        sentiment_result: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if any(k in text for k in self._URGENT_KW):
            sentiment_result["category"] = 2
            sentiment_result["label"]    = "负面"
            sentiment_result["score"]    = max(float(sentiment_result.get("score", 9.0)), 9.0)
        elif any(k in text for k in self._HIGH_RISK_KW):
            sentiment_result["category"] = 2
            sentiment_result["label"]    = "负面"
            sentiment_result["score"]    = max(float(sentiment_result.get("score", 8.0)), 8.0)

        category = sentiment_result.get("category", 4)
        score    = float(sentiment_result.get("score", 5.0))
        label    = sentiment_result.get("label", "中性")
        ai_reply = sentiment_result.get("reply", "") or self._mode_fallback_reply(mode, category)
        keywords = sentiment_result.get("keywords", [])
        guide_text = self._generate_guide(category=category, score=score)

        result: Dict[str, Any] = {
            "sentiment_category": category,
            "sentiment_score":    score,
            "sentiment_label":    label,
            "reply":              ai_reply,
            "guide":              guide_text,
            "keywords":           keywords,
            "mode":               mode,
            "category":           category,
            "score":              score,
            "label":              label,
        }

        for ext_key in ("_refs", "_rag_route"):
            if ext_key in sentiment_result:
                result[ext_key] = sentiment_result[ext_key]

        logger.info("分析完成 | label=%s score=%.1f keywords=%s mode=%s",
                    label, score, keywords, mode)
        try:
            from config.settings import settings  # noqa: PLC0415
            if settings.ENABLE_USER_PROFILE and user_id:
                profile = load_profile(user_id)
                if profile and (
                    profile.get("stressors")
                    or profile.get("recent_state")
                    or profile.get("interests")
                    or profile.get("response_hints")
                ):
                    result["_profile"] = profile
        except Exception as exc:
            logger.debug("[Analysis] 读取画像失败（已忽略）| user_id=%s err=%s", user_id, exc)
        logger.info(
            "分析完成 | label=%s score=%.1f keywords=%s mode=%s",
            label, score, keywords, mode,
        )
        return result

    def _generate_guide(self, category: int, score: float) -> str:
        templates = self.GUIDE_TEMPLATES.get(category, self.GUIDE_TEMPLATES[4])
        if category == 2 and score < 3.0:
            return random.choice([
                "你现在承受的压力真的很大。先照顾好自己的身体，如果感觉很难独自承受，"
                "也可以寻求专业帮助——这不是软弱，是勇敢。",
                "感觉撑不住的时候，先停下来，深呼吸几次。"
                "你不是一个人，总有人愿意陪你一起面对。",
            ])
        guide = random.choice(templates)
        return guide[:200] + "..." if len(guide) > 200 else guide

    def _mode_fallback_reply(self, mode: str, category: int) -> str:
        fallbacks = {
            "smart":   {1: "你的好心情透过文字都感染到我了！这份积极很珍贵，继续保持～",
                        2: "我感受到了你话语里的沉重，这种感受是真实的，不用急着让自己好起来。",
                        4: "嗯，我在听。有什么想多说的吗？"},
            "praise":  {1: "哇！你今天状态超棒的，这份快乐是你应得的！💖",
                        2: "你愿意说出心里的感受，这本身就很了不起！感知自己的情绪是一种很珍贵的能力 💪",
                        4: "光是认真生活这件事，就值得被夸！你每天都在好好存在着，很棒✨"},
            "comfort": {1: "你开心我也开心，就是这样～",
                        2: "我听到了，你现在不太好受...没关系，我就陪着你。",
                        4: "嗯，我在这里，你慢慢说..."},
        }
        mode_fallback = fallbacks.get(mode, fallbacks["smart"])
        return mode_fallback.get(category, mode_fallback.get(4, "我在这里听你说～"))


emotion_analyzer = EmotionAnalyzer()
