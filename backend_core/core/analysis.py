"""情绪分析 + 暖心疏导建议生成核心逻辑 - 完整版（AI回复优先）"""
import logging
import random
from typing import Dict, Any, List, Optional
from service.huawei_nlp import huawei_nlp_service

logger = logging.getLogger(__name__)


class EmotionAnalyzer:
    """情绪分析器 - AI回复优先，模板兜底"""

    # 疏导建议模板库（作为分析卡片的补充建议，非主聊天回复）
    GUIDE_TEMPLATES = {
        1: [  # 正面
            "保持这份好心情，把快乐分享给身边的人吧～",
            "你的积极态度很有感染力！继续发光发热✨",
            "好心情是最好的礼物，愿它一直陪伴你～",
            "今天的你，值得被好好对待！",
        ],
        2: [  # 负面
            "情绪是信使，它在告诉你一些重要的事。先好好休息，等准备好了再慢慢面对～",
            "允许自己难过，不用逼着自己立刻振作。你有权利感受自己的感受。",
            "难过的时候可以找一个信任的人说说话，说出来会轻松一点～",
            "心情沉重的时候，走出去吹吹风、听听音乐，给自己一些喘息的空间。",
            "你已经很努力了，偶尔低落是正常的，不用对自己太苛刻。",
            "今晚好好睡一觉，明天的阳光会不一样。",
        ],
        3: [  # 正负混合
            "复杂的心情说明你在认真感受生活，慢慢来，给自己一些时间梳理～",
            "矛盾的感受很正常，你不需要立刻想清楚，顺其自然也是一种智慧。",
            "接纳自己所有的情绪，喜悦和难过都是真实的你，都值得被看见。",
        ],
        4: [  # 中性
            "平静的心态很难得，愿你继续保持这份从容～",
            "平静也是一种力量，愿岁月待你温柔。",
            "生活就是这样，平淡中有它独特的美。",
        ],
        5: [  # 不相关
            "感谢你的分享，有什么想聊的，随时都可以～",
            "我会一直在这里，有任何感受都可以和我说。",
        ]
    }

    async def analyze(
        self,
        text: str,
        mode: str = "smart",
        history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        执行情绪分析 + 生成结构化结果
        :param text: 用户输入文本
        :param mode: 回复模式 smart/praise/comfort
        :param history: 对话历史
        :return: 完整分析结果（含 AI 回复 + 疏导建议 + 关键词）
        """
        if not text or not text.strip():
            raise ValueError("输入文本不能为空")

        # 调用华为云 NLP（传入模式和历史）
        sentiment_result = await huawei_nlp_service.analyze_sentiment(
            text=text,
            mode=mode,
            history=history or []
        )

        category = sentiment_result["category"]
        score = sentiment_result["score"]

        # AI 生成的回复（主聊天消息，优先级最高）
        ai_reply = sentiment_result.get("reply", "")
        if not ai_reply:
            ai_reply = self._mode_fallback_reply(mode, category)

        # 关键词（来自 AI 提取）
        keywords = sentiment_result.get("keywords", [])

        # 疏导建议（用于分析卡片的补充内容，模板生成）
        guide_text = self._generate_guide(category=category, score=score)

        result = {
            "sentiment_category": category,
            "sentiment_score": score,
            "sentiment_label": sentiment_result.get("label", "中性"),
            "reply": ai_reply,          # AI 生成的暖心回复（主聊天消息）
            "guide": guide_text,        # 模板疏导建议（展示在分析卡片）
            "keywords": keywords,       # AI 提取的情绪关键词
            "mode": mode,
        }

        logger.info(
            f"分析完成 | 类别: {sentiment_result['label']} | "
            f"分数: {score} | 关键词: {keywords} | 模式: {mode}"
        )

        return result

    def _generate_guide(self, category: int, score: float) -> str:
        """生成疏导建议（模板式，作为 AI 回复的补充）"""
        templates = self.GUIDE_TEMPLATES.get(category, self.GUIDE_TEMPLATES[4])

        # 负面情绪极重时使用特殊模板
        if category == 2 and score < 3.0:
            return random.choice([
                "你现在承受的压力真的很大。先照顾好自己的身体，如果感觉很难独自承受，也可以寻求专业帮助——这不是软弱，是勇敢。",
                "感觉撑不住的时候，先停下来，深呼吸几次。你不是一个人，总有人愿意陪你一起面对。"
            ])

        guide = random.choice(templates)
        return guide[:200] + "..." if len(guide) > 200 else guide

    def _mode_fallback_reply(self, mode: str, category: int) -> str:
        """各模式的兜底回复（AI 调用失败时使用）"""
        fallbacks = {
            "smart": {
                1: "你的好心情透过文字都感染到我了！这份积极很珍贵，继续保持～",
                2: "我感受到了你话语里的沉重，这种感受是真实的，不用急着让自己好起来。",
                4: "嗯，我在听。有什么想多说的吗？"
            },
            "praise": {
                1: "哇！你今天状态超棒的，这份快乐是你应得的！💖",
                2: "你愿意说出心里的感受，这本身就很了不起！感知自己的情绪是一种很珍贵的能力 💪",
                4: "光是认真生活这件事，就值得被夸！你每天都在好好存在着，很棒✨"
            },
            "comfort": {
                1: "你开心我也开心，就是这样～",
                2: "我听到了，你现在不太好受...没关系，我就陪着你。",
                4: "嗯，我在这里，你慢慢说..."
            }
        }
        mode_fallback = fallbacks.get(mode, fallbacks["smart"])
        return mode_fallback.get(category, mode_fallback.get(4, "我在这里听你说～"))


# 全局分析器实例
emotion_analyzer = EmotionAnalyzer()

