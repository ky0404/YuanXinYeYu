"""情绪记录数据模型 - 支持时序分析和趋势追踪"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from models.database import Base


class EmotionRecord(Base):
    """
    情绪记录表 - 每次对话存储一条情绪数据
    支持：趋势分析、历史查询、危机预警统计
    """
    __tablename__ = "emotion_records"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=True)  # 未登录用户为 None
    session_id       = Column(String(64), nullable=True)                       # 匿名用户会话ID
    emotion_category = Column(Integer, nullable=False, default=4)              # 1=正面 2=负面 3=混合 4=中性
    emotion_label    = Column(String(20), nullable=False, default="中性")      # 情绪标签
    emotion_score    = Column(Float, nullable=False, default=5.0)              # 0-10 强度
    emotion_type     = Column(String(20), nullable=True)                       # happy/sad/anxious/angry/calm
    keywords         = Column(String(200), nullable=True)                      # 关键词JSON
    reply_mode       = Column(String(20), default="smart")                    # 回复模式
    is_crisis        = Column(Integer, default=0)                              # 0=正常 1=高危
    created_at       = Column(DateTime, default=datetime.utcnow, index=True)

    # 联合索引：用户+时间，支持快速查询某用户最近N条
    __table_args__ = (
        Index("ix_uid_time", "user_id", "created_at"),
        Index("ix_session_time", "session_id", "created_at"),
    )
