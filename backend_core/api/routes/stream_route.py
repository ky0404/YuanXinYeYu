"""api/routes/stream_route.py v3.2
v3.2 变更：
  ★ BUG FIX：token 延迟从硬编码 0.028 改为读取 settings.STREAM_TOKEN_DELAY_MS
  - 新增 ENABLE_SSE_THINKING：分析前发 thinking 事件（改善等待 UX）
  - 新增 ENABLE_BREATHING_PAUSE：高痛苦时放慢打字节奏
  - 新增 ENABLE_SSE_EMOTION_GUIDE：额外发送 guide 事件
  所有新增事件默认关闭，不处理这些事件的旧前端完全不受影响。
"""
import asyncio
import json
import logging
from datetime import date, datetime
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from config.settings import settings
from core.analysis import emotion_analyzer
from models.database import SessionLocal
from models.emotion_record import EmotionRecord
from models.guest_quota import GuestQuota
from models.user import User as UserModel
from utils.auth import get_optional_user
from service.profile_service import update_profile_from_result, run_deep_profile_refresh

logger = logging.getLogger(__name__)
router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control":     "no-cache",
    "X-Accel-Buffering": "no",
    "Access-Control-Allow-Origin": "*",
}


class StreamRequest(BaseModel):
    text:    str                   = Field(..., min_length=1, max_length=5000)
    mode:    str                   = Field(default="smart")
    history: Optional[List[dict]]  = Field(default=[])

    class Config:
        json_schema_extra = {
            "example": {"text": "最近压力很大，考试快到了", "mode": "comfort", "history": []}
        }


# ── 辅助函数（不变）────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
    return xff.split(",")[0].strip() if xff else (request.client.host or "unknown")


def _check_quota(client_ip: str) -> tuple[Optional[GuestQuota], bool]:
    db = SessionLocal()
    try:
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
        exceeded = quota is not None and quota.count >= settings.GUEST_DAILY_LIMIT
        return quota, exceeded
    finally:
        db.close()


def _consume_quota_standalone(client_ip: str) -> None:
    db = SessionLocal()
    try:
        today = date.today()
        quota = (
            db.query(GuestQuota)
            .filter(GuestQuota.ip == client_ip, GuestQuota.day == today)
            .first()
        )
        if quota:
            quota.count      += 1
            quota.updated_at  = datetime.utcnow()
            db.commit()
    except Exception as exc:
        logger.warning("[stream] 配额更新失败: %s", exc)
        db.rollback()
    finally:
        db.close()


def _sse_json(data: dict) -> str:
    """格式化单条 SSE 数据行。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── SSE 生成器（含可选增强事件）──────────────────────────────────────────────
async def _token_generator(
    request: StreamRequest,
    client_ip: str,
    is_guest: bool,
    current_user: Optional[UserModel] = None,
) -> AsyncGenerator[str, None]:
    """
    核心 SSE 生成器。
    事件顺序：
      [thinking]? → analyze() → token* → analysis → [guide]? → done
    """
    # ── 1. 游客额度检查 ──────────────────────────────────────────────────
    if is_guest:
        _, exceeded = _check_quota(client_ip)
        if exceeded:
            logger.info("[stream] 游客 %s 额度已满", client_ip)
            yield _sse_json({
                "type": "error",
                "code": 401,
                "msg": "今日试用额度已达上限，请登录后继续使用",
            })
            yield 'data: {"type":"done"}\n\n'
            return

    # ── 2. thinking 事件 ────────────────────────────────────────────────
    if settings.ENABLE_SSE_THINKING:
        yield _sse_json({
            "type": "thinking",
            "msg": "正在感受你分享的内容，稍等片刻...",
        })

    # ── 3. 调用分析链路 ──────────────────────────────────────────────────
    try:
        valid_modes = {"smart", "praise", "comfort"}
        mode = request.mode if request.mode in valid_modes else "smart"

        history = [
            {"role": item["role"], "content": item["content"]}
            for item in (request.history or [])[-6:]
            if "role" in item and "content" in item
        ]

        result = await emotion_analyzer.analyze(
            text=request.text,
            mode=mode,
            history=history,
            user_id=current_user.id if current_user else None,
        )

        # ── 4. 成功后消耗额度 ────────────────────────────────────────────
        if is_guest:
            _consume_quota_standalone(client_ip)

        # ── 4.5 写入情绪记录（供 PersonalRAG / 用户画像使用）────────────
        try:
            db = SessionLocal()
            try:
                score_val = float(result.get("sentiment_score") or 5.0)
                kw_list = result.get("keywords", []) or []

                importance = 0.5
                if score_val >= 8.5:
                    importance = 0.95
                elif score_val >= 7.0:
                    importance = 0.8
                elif kw_list:
                    importance = 0.65

                memory_topic = (
                    " / ".join([str(x) for x in kw_list[:3]])
                    if kw_list else str(result.get("sentiment_label") or "普通对话")
                )

                record = EmotionRecord(
                    user_id=current_user.id if current_user else None,
                    emotion_category=int(result.get("sentiment_category") or 4),
                    emotion_label=str(result.get("sentiment_label") or "中性")[:50],
                    emotion_score=score_val,
                    emotion_type=(
                        str(result.get("emotion_type"))[:20]
                        if result.get("emotion_type")
                        else None
                    ),
                    keywords=json.dumps(kw_list, ensure_ascii=False),
                    reply_mode=mode,
                    is_crisis=1 if score_val >= 8.5 else 0,
                    memory_importance=importance,
                    memory_topic=memory_topic[:100],
                )
                db.add(record)
                db.commit()

                logger.info(
                    "[stream] 情绪记录已写入 | user_id=%s record_id=%s",
                    current_user.id if current_user else None,
                    record.id,
                )

                user_record_count = None
                if current_user:
                    user_record_count = (
                        db.query(EmotionRecord)
                        .filter(EmotionRecord.user_id == current_user.id)
                        .count()
                    )
            finally:
                db.close()
        except Exception as exc:
            logger.warning("[stream] 情绪记录写入失败（已忽略）: %s", exc)
            user_record_count = None

        # ── 4.6 异步更新用户画像──────────────────────────────
        try:
            if current_user and settings.ENABLE_USER_PROFILE:
                asyncio.create_task(
                    asyncio.to_thread(
                        update_profile_from_result,
                        current_user.id,
                        result,
                        request.text,
                    )
                )

                # ✅ 深度画像：低频异步刷新，不阻塞主流程
                if settings.ENABLE_DEEP_PROFILE:
                    user_record_count = None
                    db2 = SessionLocal()
                    try:
                        user_record_count = (
                            db2.query(EmotionRecord)
                            .filter(EmotionRecord.user_id == current_user.id)
                            .count()
                        )
                    finally:
                        db2.close()

                    if (
                        user_record_count
                        and user_record_count > 0
                        and user_record_count % settings.DEEP_PROFILE_REFRESH_EVERY == 0
                    ):
                        asyncio.create_task(
                            asyncio.to_thread(
                                run_deep_profile_refresh,
                                current_user.id,
                            )
                        )
        except Exception as exc:
            logger.warning("[stream] 画像更新任务创建失败（已忽略）: %s", exc)

        reply: str = result.get("reply", "") or "我在这里，慢慢说。"
        reply = reply.lstrip("✨💖☕ \u3000")

        # ── 5. 呼吸节奏判断 ─────────────────────────────────────────────
        base_delay_s = settings.STREAM_TOKEN_DELAY_MS / 1000.0

        use_breathing = (
            settings.ENABLE_BREATHING_PAUSE
            and result.get("sentiment_category") == 2
            and float(result.get("sentiment_score", 0)) >= settings.BREATHING_SCORE_THRESHOLD
        )
        token_delay_s = (
            settings.BREATHING_TOKEN_DELAY_MS / 1000.0
            if use_breathing
            else base_delay_s
        )

        if use_breathing:
            logger.info(
                "[stream] 呼吸节奏模式 | score=%.1f delay=%.0fms",
                result.get("sentiment_score", 0),
                token_delay_s * 1000,
            )

        # ── 6. 逐字推送 ──────────────────────────────────────────────────
        for char in reply:
            yield _sse_json({"type": "token", "content": char})
            await asyncio.sleep(token_delay_s)

        # ── 7. analysis 事件 ────────────────────────────────────────────
        yield _sse_json({
            "type": "analysis",
            "data": {
                "sentiment_category": result.get("sentiment_category"),
                "sentiment_score":    result.get("sentiment_score"),
                "sentiment_label":    result.get("sentiment_label"),
                "guide":              result.get("guide"),
                "keywords":           result.get("keywords", []),
                "mode":               mode,
                "_rag_route":         result.get("_rag_route"),
                "_refs":              result.get("_refs", []),
                "_profile":           result.get("_profile", {}),
            },
        })

        # ── 8. guide 事件 ───────────────────────────────────────────────
        if settings.ENABLE_SSE_EMOTION_GUIDE:
            guide_text = result.get("guide", "")
            if guide_text:
                yield _sse_json({
                    "type":  "guide",
                    "text":  guide_text,
                    "score": result.get("sentiment_score", 5.0),
                })

        # ── 9. done ─────────────────────────────────────────────────────
        yield 'data: {"type":"done"}\n\n'

    except ValueError as exc:
        yield _sse_json({"type": "error", "msg": f"参数错误: {exc}"})
        yield 'data: {"type":"done"}\n\n'

    except Exception as exc:
        logger.error("[stream] 分析失败: %s", exc, exc_info=True)
        yield _sse_json({"type": "error", "msg": "服务暂时不可用，请稍后重试"})
        yield 'data: {"type":"done"}\n\n'


# ── 路由端点（不变）──────────────────────────────────────────────────────────

@router.post("/emo_analysis_stream", summary="SSE 流式情绪分析", response_class=StreamingResponse)
async def analyze_emotion_stream(
    request:      StreamRequest,
    http_request: Request,
    current_user: Optional[UserModel] = Depends(get_optional_user),
):
    """
    流式版情绪分析：返回 SSE 事件流（打字机效果）。
    新增事件（ENABLE_SSE_THINKING / ENABLE_SSE_EMOTION_GUIDE）默认关闭，
    旧前端遇到未知 type 字段时安全忽略，不影响现有功能。
    """
    client_ip = _get_client_ip(http_request)
    is_guest  = current_user is None
    logger.info(
        "[stream] 请求 | mode=%s len=%d ip=%s guest=%s",
        request.mode, len(request.text), client_ip, is_guest,
    )

    return StreamingResponse(
        _token_generator(
            request,
            client_ip=client_ip,
            is_guest=is_guest,
            current_user=current_user,
        ),   
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
