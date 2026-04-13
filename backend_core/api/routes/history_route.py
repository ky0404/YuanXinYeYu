"""对话历史路由：读取 / 保存 / 清空

v2.4 优化：
  - 修复 logger.warning 误用（原为debug信息却用WARNING级别）
  - MAX_HISTORY 改为读 settings.MAX_HISTORY_TURNS，统一配置
  - 增加保存耗时日志
  - emotion_trend 统计增加 positive_rate
"""
import json
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config.settings import settings
from models.database import get_db
from models.emotion_record import EmotionRecord
from models.user import User, ChatHistory
from utils.auth import get_current_user, get_optional_user
from utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter()


class SaveHistoryRequest(BaseModel):
    messages: List[dict]
    mode:     Optional[str] = "smart"


@router.get("/history", summary="拉取当前用户对话历史")
async def get_history(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    record = (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == current_user.id)
        .first()
    )
    if not record:
        return success_response(data={"messages": [], "mode": "smart"})
    try:
        messages = json.loads(record.messages)
    except Exception:
        messages = []
    return success_response(data={"messages": messages, "mode": record.mode})


@router.post("/history", summary="保存对话历史（覆盖）")
async def save_history(
    req:          SaveHistoryRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    t0 = time.monotonic()

    # ✅ 使用配置项控制最大保留条数
    max_turns = settings.MAX_HISTORY_TURNS
    messages_to_save = (
        req.messages[-max_turns:] if len(req.messages) > max_turns else req.messages
    )
    messages_json = json.dumps(messages_to_save, ensure_ascii=False)

    record = (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == current_user.id)
        .first()
    )
    if record:
        record.messages = messages_json
        record.mode     = req.mode
    else:
        record = ChatHistory(
            user_id  = current_user.id,
            messages = messages_json,
            mode     = req.mode,
        )
        db.add(record)
    db.commit()

    elapsed = int((time.monotonic() - t0) * 1000)
    # ✅ 修复：原来用 logger.warning 记录 DEBUG 信息，改为 logger.debug
    logger.debug(
        "保存历史 | user_id=%d count=%d latency=%dms",
        current_user.id, len(messages_to_save), elapsed,
    )
    return success_response(data={"saved": True, "count": len(messages_to_save)})


@router.delete("/history", summary="清空当前用户对话历史")
async def clear_history(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    db.query(ChatHistory).filter(ChatHistory.user_id == current_user.id).delete()
    db.commit()
    logger.info("清空历史 | user_id=%d", current_user.id)
    return success_response(data={"cleared": True})


# ── 情绪趋势接口 ──────────────────────────────────────────────────────────────

@router.get("/emotion/trends", summary="获取情绪趋势数据")
async def get_emotion_trends(
    limit:        int             = 14,
    current_user: Optional[User]  = Depends(get_optional_user),
    db:           Session         = Depends(get_db),
):
    """
    获取最近 N 条情绪记录用于前端趋势图。
    未登录返回空（保护隐私）。
    """
    if not current_user:
        return success_response(data={"records": [], "stats": {}})

    # limit 上限保护，防止查询过大
    limit = max(1, min(limit, 100))

    records = (
        db.query(EmotionRecord)
        .filter(EmotionRecord.user_id == current_user.id)
        .order_by(desc(EmotionRecord.created_at))
        .limit(limit)
        .all()
    )

    data = [
        {
            "id":           r.id,
            "score":        r.emotion_score,
            "label":        r.emotion_label,
            "category":     r.emotion_category,
            "emotion_type": r.emotion_type,
            "is_crisis":    r.is_crisis,
            "created_at":   r.created_at.isoformat(),
        }
        for r in reversed(records)
    ]

    # ✅ 统计信息（增加 positive_rate）
    total = len(data)
    if total:
        avg_score      = sum(d["score"] for d in data) / total
        crisis_count   = sum(1 for d in data if d["is_crisis"])
        negative_count = sum(1 for d in data if d["category"] == 2)
        positive_count = sum(1 for d in data if d["category"] == 1)
    else:
        avg_score = 5.0
        crisis_count = negative_count = positive_count = 0

    return success_response(data={
        "records": data,
        "stats": {
            "avg_score":     round(avg_score, 1),
            "crisis_count":  crisis_count,
            "negative_rate": round(negative_count / max(total, 1) * 100, 1),
            "positive_rate": round(positive_count / max(total, 1) * 100, 1),
            "total":         total,
        },
    })


@router.delete("/emotion/records", summary="一键清空情绪记录（隐私保护）")
async def clear_emotion_records(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    count = (
        db.query(EmotionRecord)
        .filter(EmotionRecord.user_id == current_user.id)
        .delete()
    )
    db.commit()
    logger.info("清空情绪记录 | user_id=%d count=%d", current_user.id, count)
    return success_response(data={"cleared": True, "count": count})
