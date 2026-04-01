from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Date, DateTime, Index
from models.database import Base

class GuestQuota(Base):
    __tablename__ = "guest_quota"

    id = Column(Integer, primary_key=True, index=True)
    # 你可以先用 ip；更强一点可以 ip+ua 哈希，但 ip 已经够用做第一版
    ip = Column(String(64), nullable=False, index=True)

    day = Column(Date, nullable=False, index=True)   # 按自然日统计（简单）
    count = Column(Integer, nullable=False, default=0)

    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_guest_quota_ip_day", "ip", "day", unique=True),
    )
