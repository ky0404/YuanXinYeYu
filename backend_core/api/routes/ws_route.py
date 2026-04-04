"""api/routes/ws_route.py
WebSocket 控制通道 /api/ws

说明：
  - 不破坏现有 SSE /api/emo_analysis_stream
  - feedback 直接写 DB（而非内部 HTTP）：
      原因：避免在同一进程内发起 HTTP 请求到自身（易产生端口冲突/循环依赖），
      同时 DB Session 通过 SessionLocal() 独立管理，生命周期清晰。

消息协议：
  → 客户端发：
      {"type":"pong"}
      {"type":"cancel","session_id":"..."}
      {"type":"feedback","user_input":"...","ai_reply":"...","rating":"like|dislike|regenerate",
       "emotion_mode":"smart","session_id":"...","sentiment_score":7.5,"sentiment_label":"负向"}
  ← 服务端发：
      {"type":"ping"}
      {"type":"cancelled","session_id":"..."}
      {"type":"feedback_ack","data":{"saved":true,"id":123}}
      {"type":"error","msg":"..."}
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 全局会话取消集合（in-memory，进程级）────────────────────────────────
_cancelled_sessions: Set[str] = set()

PING_INTERVAL = 30   # 秒：心跳间隔
PONG_TIMEOUT  = 70   # 秒：超时未收到 pong 则断开


def is_session_cancelled(session_id: str) -> bool:
    """供 SSE/其他路由查询某 session 是否被 WS 取消。"""
    return session_id in _cancelled_sessions


# ── 直接写 DB（不走内部 HTTP）────────────────────────────────────────────

async def _save_feedback_direct(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    直接写 feedback_records 表，绕过 HTTP 层。
    选择原因：避免进程内 HTTP 自调用，DB Session 独立管理生命周期。
    """
    from models.database import SessionLocal  # noqa: PLC0415

    # 延迟导入，避免循环依赖
    try:
        from api.routes.feedback_route import FeedbackRecord  # noqa: PLC0415
    except ImportError:
        from models.feedback import FeedbackRecord  # noqa: PLC0415

    valid_ratings = {"like", "dislike", "regenerate"}
    rating = data.get("rating", "")
    if rating not in valid_ratings:
        raise ValueError(f"rating 必须是 {valid_ratings}，收到: {rating!r}")

    db = SessionLocal()
    try:
        record = FeedbackRecord(
            user_id         = None,   # WS 连接无用户鉴权（扩展时可传 token）
            session_id      = data.get("session_id"),
            user_input      = str(data.get("user_input", ""))[:5000],
            ai_reply        = str(data.get("ai_reply",   ""))[:5000],
            rating          = rating,
            feedback_text   = data.get("feedback_text"),
            emotion_mode    = data.get("emotion_mode", "smart"),
            sentiment_score = data.get("sentiment_score"),
            sentiment_label = data.get("sentiment_label"),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info("[WS] feedback saved id=%d rating=%s", record.id, rating)
        return {"saved": True, "id": record.id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── WebSocket 端点 ────────────────────────────────────────────────────────

@router.websocket("/ws")
async def ws_control(websocket: WebSocket) -> None:
    """
    WebSocket 控制通道：
      - 30s 心跳 ping；70s 无 pong 断开
      - cancel / feedback 消息处理
    """
    await websocket.accept()
    logger.info("[WS] 客户端已连接 | client=%s", websocket.client)

    last_pong_time: list[float] = [time.monotonic()]
    ping_task: Optional[asyncio.Task] = None

    async def _heartbeat() -> None:
        """后台心跳任务：每 PING_INTERVAL 秒发送 ping，检测 pong 超时。"""
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
                logger.debug("[WS] ping 已发送")
            except Exception:
                return  # 连接已断，退出

            if time.monotonic() - last_pong_time[0] > PONG_TIMEOUT:
                logger.warning(
                    "[WS] pong 超时（>%ds），主动断开连接", PONG_TIMEOUT
                )
                try:
                    await websocket.close(code=1001, reason="pong timeout")
                except Exception:
                    pass
                return

    ping_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "msg": "消息格式错误，需要合法 JSON"})
                )
                continue

            msg_type = msg.get("type", "")

            # ── pong ──────────────────────────────────────────────────────
            if msg_type == "pong":
                last_pong_time[0] = time.monotonic()
                logger.debug("[WS] pong 收到")

            # ── cancel ────────────────────────────────────────────────────
            elif msg_type == "cancel":
                session_id = str(msg.get("session_id", "")).strip()
                if session_id:
                    _cancelled_sessions.add(session_id)
                    # 防止无限增长（最多保留 1000 条）
                    if len(_cancelled_sessions) > 1000:
                        _cancelled_sessions.pop()
                    logger.info("[WS] 会话已取消: %s", session_id)
                    await websocket.send_text(
                        json.dumps({"type": "cancelled", "session_id": session_id})
                    )
                else:
                    await websocket.send_text(
                        json.dumps({"type": "error", "msg": "cancel 缺少 session_id"})
                    )

            # ── feedback ──────────────────────────────────────────────────
            elif msg_type == "feedback":
                try:
                    result = await _save_feedback_direct(msg)
                    await websocket.send_text(
                        json.dumps({"type": "feedback_ack", "data": result})
                    )
                except ValueError as exc:
                    await websocket.send_text(
                        json.dumps({"type": "error", "msg": str(exc)})
                    )
                except Exception as exc:
                    logger.error("[WS] feedback 写入失败: %s", exc, exc_info=True)
                    await websocket.send_text(
                        json.dumps({"type": "error", "msg": "反馈保存失败，请稍后重试"})
                    )

            # ── 未知消息类型 ──────────────────────────────────────────────
            else:
                await websocket.send_text(
                    json.dumps({"type": "error", "msg": f"未知消息类型: {msg_type!r}"})
                )

    except WebSocketDisconnect:
        logger.info("[WS] 客户端主动断开")
    except Exception as exc:
        logger.error("[WS] 未预期错误: %s", exc, exc_info=True)
    finally:
        if ping_task and not ping_task.done():
            ping_task.cancel()
        logger.info("[WS] 连接已清理")
