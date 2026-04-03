"""SSE 流式输出路由 - POST /api/emo_analysis_stream

实现原理：
  后端调用华为云 NLP 拿到完整回复后，
  通过 SSE 协议逐字推送给前端，产生打字机效果。
  不依赖上游 API 支持流式，自行控制推送节奏。

SSE 消息格式：
  data: {"type":"token","content":"我"}\n\n    ← 逐字推送
  data: {"type":"analysis","data":{...}}\n\n   ← 最终分析数据
  data: {"type":"done"}\n\n                    ← 结束信号
"""
import asyncio
import json
import logging
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.analysis import emotion_analyzer
from utils.response import error_response

logger = logging.getLogger(__name__)
router = APIRouter()


class StreamRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    mode: str = Field(default="smart")
    history: Optional[List[dict]] = Field(default=[])

    class Config:
        json_schema_extra = {
            "example": {
                "text": "最近压力很大，考试快到了",
                "mode": "comfort",
                "history": []
            }
        }


async def _token_generator(request: StreamRequest) -> AsyncGenerator[str, None]:
    """核心生成器：分析完成后逐字推送，最后推送完整分析数据。"""
    try:
        valid_modes = {"smart", "praise", "comfort"}
        mode = request.mode if request.mode in valid_modes else "smart"
        history = [
            {"role": item["role"], "content": item["content"]}
            for item in (request.history or [])[-6:]
            if "role" in item and "content" in item
        ]

        # 调用现有分析逻辑（完全复用，不改动核心代码）
        result = await emotion_analyzer.analyze(
            text=request.text,
            mode=mode,
            history=history,
        )

        reply: str = result.get("reply", "") or "我在这里，慢慢说。"
        # 去掉前缀 emoji（前端会自己加）
        reply = reply.lstrip("✨💖☕ 　")

        # ── 逐字推送（每字间隔 28ms，接近真实打字速度）──
        for char in reply:
            payload = json.dumps({"type": "token", "content": char}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.028)

        # ── 推送完整分析数据（前端用于更新情绪卡片）──
        analysis_payload = json.dumps(
            {
                "type": "analysis",
                "data": {
                    "sentiment_category": result.get("sentiment_category"),
                    "sentiment_score":    result.get("sentiment_score"),
                    "sentiment_label":    result.get("sentiment_label"),
                    "guide":              result.get("guide"),
                    "keywords":           result.get("keywords", []),
                    "mode":               mode,
                },
            },
            ensure_ascii=False,
        )
        yield f"data: {analysis_payload}\n\n"

        # ── 结束信号 ──
        yield 'data: {"type":"done"}\n\n'

    except ValueError as exc:
        err = json.dumps({"type": "error", "msg": f"参数错误: {exc}"}, ensure_ascii=False)
        yield f"data: {err}\n\n"
    except Exception as exc:
        logger.error("[stream] 分析失败: %s", exc, exc_info=True)
        err = json.dumps({"type": "error", "msg": "服务暂时不可用，请稍后重试"}, ensure_ascii=False)
        yield f"data: {err}\n\n"
        yield 'data: {"type":"done"}\n\n'


@router.post(
    "/emo_analysis_stream",
    summary="SSE 流式情绪分析",
    response_class=StreamingResponse,
)
async def analyze_emotion_stream(request: StreamRequest):
    """
    流式版情绪分析接口，返回 SSE 事件流。
    前端用 fetch + ReadableStream 消费，产生打字机效果。
    """
    logger.info("[stream] 收到流式请求 | mode=%s | len=%d", request.mode, len(request.text))
    return StreamingResponse(
        _token_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",   # 关闭 Nginx 缓冲，保证实时性
            "Access-Control-Allow-Origin": "*",
        },
    )
