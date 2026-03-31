"""对话历史路由：读取 / 保存 / 清空"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.database import get_db
from models.user import User, ChatHistory
from models.emotion_record import EmotionRecord
from utils.auth import get_current_user, get_optional_user
from utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter()


class SaveHistoryRequest(BaseModel):
    messages: List[dict]
    mode:     Optional[str] = "smart"


@router.get("/history", summary="拉取当前用户对话历史")
async def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(ChatHistory).filter(ChatHistory.user_id == current_user.id).first()
    if not record:
        return success_response(data={"messages": [], "mode": "smart"})
    try:
        messages = json.loads(record.messages)
    except Exception:
        messages = []
    return success_response(data={"messages": messages, "mode": record.mode})


@router.post("/history", summary="保存对话历史（覆盖）")
async def save_history(
    req: SaveHistoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 最多保留最近 60 条
    messages_to_save = req.messages[-60:] if len(req.messages) > 60 else req.messages
    messages_json = json.dumps(messages_to_save, ensure_ascii=False)

    record = db.query(ChatHistory).filter(ChatHistory.user_id == current_user.id).first()
    if record:
        record.messages = messages_json
        record.mode = req.mode
    else:
        record = ChatHistory(user_id=current_user.id, messages=messages_json, mode=req.mode)
        db.add(record)
    db.commit()
    logger.debug(f"保存历史 | user_id={current_user.id} count={len(messages_to_save)}")
    return success_response(data={"saved": True, "count": len(messages_to_save)})


@router.delete("/history", summary="清空当前用户对话历史")
async def clear_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(ChatHistory).filter(ChatHistory.user_id == current_user.id).delete()
    db.commit()
    logger.info(f"清空历史 | user_id={current_user.id}")
    return success_response(data={"cleared": True})


# ============================================================
# 情绪趋势接口（竞赛核心功能）
# ============================================================
from models.emotion_record import EmotionRecord
from typing import Optional
from sqlalchemy import desc


@router.get("/emotion/trends", summary="获取情绪趋势数据")
async def get_emotion_trends(
    limit: int = 14,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    获取最近N条情绪记录，用于前端趋势图
    登录用户：返回该用户数据
    未登录：返回空（保护隐私）
    """
    if not current_user:
        return success_response(data={"records": [], "stats": {}})

    records = (
        db.query(EmotionRecord)
        .filter(EmotionRecord.user_id == current_user.id)
        .order_by(desc(EmotionRecord.created_at))
        .limit(limit)
        .all()
    )

    data = [{
        "id":         r.id,
        "score":      r.emotion_score,
        "label":      r.emotion_label,
        "category":   r.emotion_category,
        "emotion_type": r.emotion_type,
        "is_crisis":  r.is_crisis,
        "created_at": r.created_at.isoformat(),
    } for r in reversed(records)]

    # 统计信息
    if data:
        avg_score = sum(d["score"] for d in data) / len(data)
        crisis_count = sum(1 for d in data if d["is_crisis"])
        negative_count = sum(1 for d in data if d["category"] == 2)
    else:
        avg_score = 5.0
        crisis_count = 0
        negative_count = 0

    return success_response(data={
        "records": data,
        "stats": {
            "avg_score":    round(avg_score, 1),
            "crisis_count": crisis_count,
            "negative_rate": round(negative_count / max(len(data), 1) * 100, 1),
            "total":        len(data),
        }
    })


@router.delete("/emotion/records", summary="一键清空情绪记录（隐私保护）")
async def clear_emotion_records(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户一键清空所有情绪记录，符合数据安全要求"""
    count = db.query(EmotionRecord).filter(
        EmotionRecord.user_id == current_user.id
    ).delete()
    db.commit()
    logger.info(f"清空情绪记录 | user_id={current_user.id} count={count}")
    return success_response(data={"cleared": True, "count": count})
