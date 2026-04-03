"""用户反馈路由 - RLHF 数据飞轮基建

接口：
  POST /api/feedback        提交反馈（👍/👎/重新生成）
  GET  /api/feedback/stats  反馈统计（需登录）

简历话术：
  "构建了基于人类反馈的数据采集基建，实现了用户偏好数据的结构化存储，
   为后续 DPO/RLHF 微调提供数据基础，已累积 XX 条高质量对齐样本。"
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Session

from models.database import Base, get_db
from utils.auth import get_optional_user
from utils.response import error_response, success_response

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 数据模型 ──────────────────────────────────────────────────────────────

class FeedbackRecord(Base):
    """反馈记录表（首次启动时自动建表）"""
    __tablename__ = "feedback_records"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, nullable=True)        # 未登录用户为 None
    session_id      = Column(String(64), nullable=True)     # 前端生成的会话 ID
    user_input      = Column(Text, nullable=False)          # 用户输入
    ai_reply        = Column(Text, nullable=False)          # AI 回复
    rating          = Column(String(20), nullable=False)    # like / dislike / regenerate
    feedback_text   = Column(Text, nullable=True)           # 可选文字反馈
    emotion_mode    = Column(String(20), default="smart")
    sentiment_score = Column(Float, nullable=True)
    sentiment_label = Column(String(20), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow, index=True)


# ── 请求/响应模型 ──────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    user_input:      str   = Field(..., max_length=5000)
    ai_reply:        str   = Field(..., max_length=5000)
    rating:          str   = Field(..., description="like | dislike | regenerate")
    feedback_text:   Optional[str] = Field(default=None, max_length=500)
    emotion_mode:    str   = Field(default="smart")
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str]   = None
    session_id:      Optional[str]   = Field(default=None, max_length=64)

    class Config:
        json_schema_extra = {
            "example": {
                "user_input":   "最近压力很大",
                "ai_reply":     "听起来你现在承受了很多...",
                "rating":       "like",
                "emotion_mode": "comfort",
            }
        }


# ── 路由 ──────────────────────────────────────────────────────────────────

@router.post("/feedback", summary="提交 AI 回复反馈")
async def submit_feedback(
    req: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    valid_ratings = {"like", "dislike", "regenerate"}
    if req.rating not in valid_ratings:
        return error_response(code=400, msg=f"rating 只能是 {valid_ratings}")

    record = FeedbackRecord(
        user_id         = current_user.id if current_user else None,
        session_id      = req.session_id,
        user_input      = req.user_input,
        ai_reply        = req.ai_reply,
        rating          = req.rating,
        feedback_text   = req.feedback_text,
        emotion_mode    = req.emotion_mode,
        sentiment_score = req.sentiment_score,
        sentiment_label = req.sentiment_label,
    )
    db.add(record)
    db.commit()

    logger.info(
        "[feedback] rating=%s mode=%s uid=%s",
        req.rating,
        req.emotion_mode,
        current_user.id if current_user else "guest",
    )
    return success_response(data={"saved": True, "id": record.id})


@router.get("/feedback/stats", summary="反馈统计（需登录）")
async def feedback_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """
    返回整体反馈统计，供管理员或开发者查看数据质量。
    未登录也可查看（公开统计，不含用户隐私）。
    """
    from sqlalchemy import func

    stats = (
        db.query(
            FeedbackRecord.rating,
            func.count(FeedbackRecord.id).label("count"),
        )
        .group_by(FeedbackRecord.rating)
        .all()
    )

    total = sum(s.count for s in stats)
    breakdown = {s.rating: s.count for s in stats}

    # 正样本（like）数量
    positive = breakdown.get("like", 0)
    # 负样本（dislike + regenerate）数量  
    negative = breakdown.get("dislike", 0) + breakdown.get("regenerate", 0)

    return success_response(data={
        "total":     total,
        "breakdown": breakdown,
        "positive":  positive,
        "negative":  negative,
        "quality_rate": round(positive / total * 100, 1) if total > 0 else 0,
        "note": "正样本可直接用于 DPO/RLHF 微调数据集",
    })
