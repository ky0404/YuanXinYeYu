"""models/user_profile.py
用户心理画像模型（v2.6 新增，ENABLE_USER_PROFILE=true 时启用）

设计原则：
  - Phase 1 MVP：只记录显式可观测信息，不做复杂人格推断
  - 游客（user_id=None）不创建画像
  - 字段均有默认值，init_db 建表后即可使用
  - 失败不影响主流程（profile_service 内保证）
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from models.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # 近期主要压力源（JSON list，如 ["学业压力", "人际关系"]，取自对话 keywords 累积）
    main_stressors = Column(Text, default="[]", nullable=False)

    # 近期情绪状态摘要（纯文字，规则生成，不做 LLM 推断）
    recent_state = Column(Text, default="", nullable=False)

    # 常提兴趣/话题（JSON list，从 keywords 提取）
    interests = Column(Text, default="[]", nullable=False)

    # AI 回应偏好提示（预留字段，如"用户喜欢直接建议"）
    response_hints = Column(Text, default="", nullable=False)

    # 近期情绪均分（简单 EMA，α=0.3）
    avg_score = Column(Float, default=5.0, nullable=False)

    # 近期高危记录计数（sentiment_category==2 且 score>=7）
    recent_crisis_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_user_profile_uid", "user_id"),
    )