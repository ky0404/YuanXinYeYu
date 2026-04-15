"""models/user_profile.py
用户心理画像模型（v3.0 深度画像增强版）

设计原则：
  - 轻量画像 + 深度画像共存
  - 深度画像使用 JSON 存储推测型结果
  - 游客不创建画像
  - 字段均有默认值
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, Text
from models.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # 轻量画像
    main_stressors = Column(Text, default="[]", nullable=False)
    recent_state   = Column(Text, default="", nullable=False)
    interests      = Column(Text, default="[]", nullable=False)
    response_hints = Column(Text, default="", nullable=False)
    avg_score      = Column(Float, default=5.0, nullable=False)
    recent_crisis_count = Column(Integer, default=0, nullable=False)

    # ✅ 深度画像（JSON）
    deep_profile_json = Column(Text, default="{}", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_user_profile_uid", "user_id"),
    )
