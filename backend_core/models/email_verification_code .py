"""邮箱验证码模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from models.database import Base


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id         = Column(Integer, primary_key=True, index=True)
    email      = Column(String(255), nullable=False, index=True)
    code       = Column(String(10), nullable=False)
    # purpose: login | reset_password
    purpose    = Column(String(30), nullable=False)
    send_ip    = Column(String(50), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 联合索引：查询某邮箱+用途的最新未使用验证码
    __table_args__ = (
        Index("ix_evc_email_purpose_used", "email", "purpose", "used"),
    )
