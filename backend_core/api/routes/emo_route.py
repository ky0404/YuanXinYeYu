"""
情绪分析路由 - 华为NLP+语义缓存+降级兜底版
----------------------------------------------------
功能特性：
1. 优先调用华为云 NLP API 进行情绪识别和回复生成
2. 内置语义缓存（缓存命中时直接返回，降低成本）
3. 网络/超时自动降级到本地 emotion_analyzer.analyze()
4. 游客限流 + 数据库存储逻辑与原版保持一致
"""

import json
import logging
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from models.database import get_db
from models.user import User as UserModel
from models.emotion_record import EmotionRecord
from models.guest_quota import GuestQuota

from utils.response import success_response, error_response
from utils.auth import get_optional_user

# 载入AI分析层
from core.analysis import emotion_analyzer
from service.huawei_nlp import analyze_sentiment   # ✅ 华为NLP接口
from service.cache_service import semantic_cache   # ✅ 语义缓存层

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== 数据结构定义 ==========
class HistoryItem(BaseModel):
    role: str
    content: str


class EmotionRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    mode: str = Field(default="smart")
    history: Optional[List[HistoryItem]] = Field(default=[])


# ========== 主逻辑路由 ==========
@router.post("/emo_analysis")
@router.post("/mood/process")
async def analyze_emotion(
    payload: EmotionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_optional_user),
):
    """主情绪分析接口：缓存 → 华为NLP → 本地兜底"""
    # 1️⃣ 获取真实IP
    xff = request.headers.get("x-forwarded-for")
    client_ip = xff.split(",")[0].strip() if xff else request.client.host

    # 2️⃣ 游客限流
    if current_user is None:
        today = date.today()
        quota = (
            db.query(GuestQuota)
            .filter(GuestQuota.ip == client_ip, GuestQuota.day == today)
            .first()
        )
        if not quota:
            quota = GuestQuota(ip=client_ip, day=today, count=0)
            db.add(quota)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                quota = (
                    db.query(GuestQuota)
                    .filter(GuestQuota.ip == client_ip, GuestQuota.day == today)
                    .first()
                )

        if quota and quota.count >= 5:
            return error_response(code=401, msg="今日试用额度已达上限，请登录后继续使用")

    # 3️⃣ 缓存查询（命中后直接返回）
    cache = semantic_cache
    mode = payload.mode or "smart"
    cached = cache.get(payload.text, mode)
    if cached:
        logger.info("[emo_route] 缓存命中 | mode=%s", mode)
        return success_response(data={**cached, "_cached": True})

    # 4️⃣ 尝试调用华为NLP接口 （核心）
    history = [h.dict() for h in (payload.history or [])[-6:]]
    try:
        result = await analyze_sentiment(
            text=payload.text,
            mode=mode,
            history=history,
        )
        logger.info("[emo_route] 华为NLP调用成功 | mode=%s", mode)
    except Exception as e:
        # 失败则自动降级本地分析
        logger.warning("[emo_route] NLP调用失败，降级本地分析: %s", e)
        try:
            result = await emotion_analyzer.analyze(
                text=payload.text,
                mode=mode,
                history=history,
            )
        except Exception as e2:
            logger.error("[emo_route] 本地分析也失败: %s", e2, exc_info=True)
            return error_response(code=500, msg="情绪分析暂时不可用")

    # 5️⃣ 结果写入缓存
    cache.set(payload.text, mode, result)

    # 6️⃣ 异步保存到数据库（失败不阻断主流程）
    try:
        record = EmotionRecord(
            user_id=current_user.id if current_user else None,
            emotion_category=result.get("category", 4),
            emotion_label=result.get("label", "中性"),
            emotion_score=result.get("score", 5.0),
            reply_mode=mode,
            keywords=json.dumps(result.get("keywords", []), ensure_ascii=False),
        )
        db.add(record)
        if current_user is None and quota is not None:
            quota.count += 1
            quota.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.warning("[emo_route] 保存记录失败: %s", e)
        db.rollback()

    # ✅ 正常返回
    return success_response(data=result)


# ========== 健康/缓存维护 ==========
@router.get("/cache/stats", summary="缓存统计")
async def cache_stats():
    return success_response(data=semantic_cache.stats())


@router.delete("/cache/clear", summary="清空缓存")
async def cache_clear():
    semantic_cache.clear()
    return success_response(data={"cleared": True})


@router.get("/health", summary="健康检查")
async def health_check():
    return success_response(
        data={"status": "healthy", "cache": semantic_cache.stats(), "version": "3.0"}
    )
# === 文件最后添加新导出函数 ===

async def analyze_sentiment(text: str, mode: str = "smart", history=None):
    """
    模块级兼容函数，用于旧代码直接 import。
    内部调用 huawei_nlp_service.analyze_sentiment()
    """
    return await huawei_nlp_service.analyze_sentiment(
        text=text,
        mode=mode,
        history=history,
    )
