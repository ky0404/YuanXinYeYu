"""情绪记录数据模型 - 支持时序分析和趋势追踪 / 长期记忆"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from datetime import datetime
from models.database import Base


class EmotionRecord(Base):
    """
    情绪记录表 - 每次对话存储一条情绪数据
    支持：
      - 趋势分析
      - 历史查询
      - 危机预警统计
      - 长期记忆检索
    """
    __tablename__ = "emotion_records"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id       = Column(String(64), nullable=True)

    emotion_category = Column(Integer, nullable=False, default=4)
    emotion_label    = Column(String(20), nullable=False, default="中性")
    emotion_score    = Column(Float, nullable=False, default=5.0)
    emotion_type     = Column(String(20), nullable=True)
    keywords         = Column(String(200), nullable=True)
    reply_mode       = Column(String(20), default="smart")
    is_crisis        = Column(Integer, default=0)

    # ✅ v2.9 新增：长期记忆辅助字段
    memory_importance = Column(Float, nullable=False, default=0.5)   # 0~1，越高越重要
    memory_topic      = Column(String(100), nullable=True)           # 简单主题摘要

    created_at       = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_uid_time", "user_id", "created_at"),
        Index("ix_session_time", "session_id", "created_at"),
        Index("ix_uid_importance", "user_id", "memory_importance"),
    )
