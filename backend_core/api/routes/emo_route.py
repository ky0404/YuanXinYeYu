import logging
import json
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.analysis import emotion_analyzer
from models.database import get_db
from models.user import User as UserModel
from models.emotion_record import EmotionRecord
from models.guest_quota import GuestQuota
from utils.auth import get_optional_user
from utils.response import success_response, error_response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

class HistoryItem(BaseModel):
    role: str
    content: str

class EmotionRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    mode: str = Field(default="smart")
    history: Optional[List[HistoryItem]] = Field(default=[])

@router.post("/emo_analysis")
@router.post("/mood/process")
async def analyze_emotion(
    payload: EmotionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_optional_user),
):
    # 1. 安全提取真实 IP
    xff = request.headers.get("x-forwarded-for")
    client_ip = xff.split(",")[0].strip() if xff else request.client.host

    # 2. 游客限流检查
    if current_user is None:
        today = date.today()
        quota = db.query(GuestQuota).filter(GuestQuota.ip == client_ip, GuestQuota.day == today).first()
        if not quota:
            quota = GuestQuota(ip=client_ip, day=today, count=0)
            db.add(quota)
            try: db.commit()
            except IntegrityError: db.rollback(); quota = db.query(GuestQuota).filter(GuestQuota.ip == client_ip, GuestQuota.day == today).first()
        
        if quota.count >= 5:
            return error_response(code=401, msg="今日试用额度已达上限，请登录后继续使用")

    # 3. 核心业务（不改变原逻辑）
    result = await emotion_analyzer.analyze(
        text=payload.text,
        mode=payload.mode,
        history=[item.dict() for item in (payload.history or [])[-6:]]
    )

    # 4. 异步保存记录（即便失败也不阻断返回）
    try:
        record = EmotionRecord(
            user_id=current_user.id if current_user else None,
            emotion_category=result.get("category", 4),
            emotion_label=result.get("label", "中性"),
            emotion_score=result.get("score", 5.0),
            reply_mode=payload.mode,
            keywords=json.dumps(result.get("keywords", []), ensure_ascii=False)
        )
        db.add(record)
        if current_user is None:
            quota.count += 1
            quota.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Record save failed: {e}")

    return success_response(data=result)