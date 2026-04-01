"""用户 & 对话记录数据模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from models.database import Base


class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String(255), unique=True, index=True, nullable=False)
    username       = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow)

    histories = relationship(
        "ChatHistory", back_populates="user", cascade="all, delete-orphan"
    )


class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    messages   = Column(Text, nullable=False, default="[]")   # JSON 序列化的消息数组
    mode       = Column(String(20), default="smart")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="histories")
