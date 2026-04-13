"""api/routes/emo_route.py v3.2
优化（v3.2）：
  1. 增加接口响应耗时日志（受 ENABLE_RESPONSE_TIME_LOG 控制）
  2. quota 消耗更健壮，IntegrityError 下仍能继续主流程
  3. 情绪记录写入增加字段防御（防止 None 写入数据库）
  4. 统一 mode 校验逻辑提取为常量
  5. 日志补充 user_id / ip 信息，便于排查
"""
import json
import logging
import time
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.settings import settings
from core.analysis import emotion_analyzer
from models.database import get_db
from models.emotion_record import EmotionRecord
from models.guest_quota import GuestQuota
from models.user import User as UserModel
from service.cache_service import semantic_cache
from utils.auth import get_optional_user
from utils.response import error_response, success_response

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 常量 ─────────────────────────────────────────────────────────────────────
_VALID_MODES = frozenset({"smart", "praise", "comfort"})


# ── 数据结构 ──────────────────────────────────────────────────────────────────

class HistoryItem(BaseModel):
    role:    str
    content: str


class EmotionRequest(BaseModel):
    text:    str                         = Field(..., min_length=1, max_length=5000)
    mode:    str                         = Field(default="smart")
    history: Optional[List[HistoryItem]] = Field(default=[])


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
    return xff.split(",")[0].strip() if xff else (request.client.host or "unknown")


def _get_or_create_quota(db: Session, client_ip: str) -> GuestQuota:
    today = date.today()
    quota = (
        db.query(GuestQuota)
        .filter(GuestQuota.ip == client_ip, GuestQuota.day == today)
        .first()
    )
    if quota is None:
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
    return quota


def _consume_quota(db: Session, quota: Optional[GuestQuota]) -> None:
    """消耗一次游客额度，失败时仅记录日志，不影响主流程。"""
    if quota is None:
        return
    try:
        quota.count     += 1
        quota.updated_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        logger.warning("[emo_route] 配额更新失败（已忽略）: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def _safe_str(val, max_len: int = 50) -> str:
    """将值安全转换为字符串，防止 None 写数据库。"""
    if val is None:
        return ""
    return str(val)[:max_len]


# ── 主路由 ────────────────────────────────────────────────────────────────────

@router.post("/emo_analysis")
@router.post("/mood/process")
async def analyze_emotion(
    payload:      EmotionRequest,
    request:      Request,
    db:           Session              = Depends(get_db),
    current_user: Optional[UserModel]  = Depends(get_optional_user),
):
    """
    主情绪分析接口。
    处理流程：额度前置 → 缓存 → emotion_analyzer → 写缓存 → 写记录
    """
    t0        = time.monotonic()
    client_ip = _get_client_ip(request)
    mode      = payload.mode if payload.mode in _VALID_MODES else "smart"
    user_id   = current_user.id if current_user else None

    # ── 1. 游客额度前置检查 ───────────────────────────────────────────────
    quota: Optional[GuestQuota] = None
    if current_user is None:
        quota = _get_or_create_quota(db, client_ip)
        if quota and quota.count >= settings.GUEST_DAILY_LIMIT:
            logger.info(
                "[emo_route] 游客额度满 | ip=%s count=%d/%d",
                client_ip, quota.count, settings.GUEST_DAILY_LIMIT,
            )
            return error_response(code=401, msg="今日试用额度已达上限，请登录后继续使用")

    # ── 2. 语义缓存查询 ───────────────────────────────────────────────────
    no_cache = request.headers.get(settings.EVAL_NO_CACHE_HEADER, "").strip() == "1"
    if not no_cache:
        cached = semantic_cache.get(payload.text, mode)
        if cached:
            _consume_quota(db, quota)
            elapsed = int((time.monotonic() - t0) * 1000)
            if settings.ENABLE_RESPONSE_TIME_LOG:
                logger.info(
                    "[emo_route] 缓存命中 | mode=%s ip=%s user_id=%s latency=%dms",
                    mode, client_ip, user_id, elapsed,
                )
            return success_response(data={**cached, "_cached": True})

    # ── 3. 调用分析链路 ───────────────────────────────────────────────────
    history = [h.dict() for h in (payload.history or [])[-6:]]
    try:
        result = await emotion_analyzer.analyze(
            text=payload.text,
            mode=mode,
            history=history,
        )

        # ✅ 防御：确保 result 至少是 dict，避免后续 get/写库报错
        if not isinstance(result, dict):
            logger.error("[emo_route] analyze 返回非 dict，已降级为空结果 | user_id=%s", user_id)
            result = {}

        # ✅ 防御：补默认字段，避免下游写库/响应时报 KeyError 或类型异常
        result.setdefault("sentiment_category", 4)
        result.setdefault("sentiment_label", "中性")
        result.setdefault("sentiment_score", 5.0)
        result.setdefault("keywords", [])
        result.setdefault("mode", mode)

        elapsed_analyze = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[emo_route] 分析成功 | mode=%s label=%s user_id=%s latency=%dms",
            mode, result.get("sentiment_label"), user_id, elapsed_analyze,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.error(
            "[emo_route] 分析失败 | mode=%s user_id=%s latency=%dms err=%s",
            mode, user_id, elapsed, exc,
            exc_info=True,
        )
        return error_response(code=500, msg="情绪分析暂时不可用，请稍后重试")

    # ── 4. 写入缓存 ───────────────────────────────────────────────────────
    try:
        semantic_cache.set(payload.text, mode, result)
    except Exception as exc:
        logger.warning("[emo_route] 缓存写入失败（已忽略）: %s", exc)

    # ── 5. 消耗额度 + 写情绪记录 ─────────────────────────────────────────
    _consume_quota(db, quota)
    try:
        record = EmotionRecord(
            user_id          = user_id,
            emotion_category = int(result.get("sentiment_category") or 4),
            emotion_label    = _safe_str(result.get("sentiment_label") or "中性", 50),
            emotion_score    = float(result.get("sentiment_score") or 5.0),
            reply_mode       = mode,
            keywords         = json.dumps(
                result.get("keywords", []), ensure_ascii=False
            ),
        )
        db.add(record)
        db.commit()
    except Exception as exc:
        logger.warning("[emo_route] 情绪记录写入失败（已忽略）: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

    # ── 6. 返回（可选附加 RAG 引用）──────────────────────────────────────
    elapsed_total = int((time.monotonic() - t0) * 1000)
    if settings.ENABLE_RESPONSE_TIME_LOG:
        logger.info(
            "[emo_route] 请求完成 | mode=%s user_id=%s total_latency=%dms",
            mode, user_id, elapsed_total,
        )

    if settings.ENABLE_RAG_REFS and "_refs" in result:
        return success_response(data={**result, "_refs": result["_refs"]})

    return success_response(data=result)


# ── 健康 / 缓存维护 ───────────────────────────────────────────────────────────

@router.get("/cache/stats", summary="缓存统计")
async def cache_stats():
    return success_response(data=semantic_cache.stats())


@router.delete("/cache/clear", summary="清空缓存（管理用）")
async def cache_clear():
    semantic_cache.clear()
    return success_response(data={"cleared": True})


@router.get("/health", summary="健康检查")
async def health_check():
    return success_response(
        data={
            "status":  "healthy",
            "version": settings.APP_VERSION,
            "cache":   semantic_cache.stats(),
        }
    )
