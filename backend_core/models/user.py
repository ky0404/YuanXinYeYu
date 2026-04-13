"""用户 & 对话记录数据模型
v2.5 变更：
  - User 新增 email_verified（邮箱验证标记）、login_type（注册方式）
  - 两个新字段均有默认值，完全兼容旧数据，不需要迁移脚本
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, SmallInteger
from sqlalchemy.orm import relationship
from models.database import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String(255), unique=True, index=True, nullable=False)
    username        = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

    # ✅ v2.5 新增字段（有默认值，兼容旧数据）
    # 0=未验证  1=已验证（密码注册默认0，邮箱验证码登录后置1）
    email_verified  = Column(SmallInteger, default=0, nullable=False)
    # password=密码注册  email_code=验证码自动注册  wechat=微信
    login_type      = Column(String(30), default="password", nullable=False)

    histories = relationship(
        "ChatHistory", back_populates="user", cascade="all, delete-orphan"
    )


class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    messages   = Column(Text, nullable=False, default="[]")
    mode       = Column(String(20), default="smart")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="histories")
