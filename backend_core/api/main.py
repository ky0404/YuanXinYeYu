"""api/main.py v2.3 — shutdown 时 flush Langfuse 数据"""
from __future__ import annotations

import ipaddress
import json
import logging
import time
from typing import Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from api.routes.emo_route import router as emo_router
from api.routes.auth_route import router as auth_router
from api.routes.history_route import router as history_router
from api.routes.stream_route import router as stream_router
from api.routes.feedback_route import router as feedback_router
from api.routes.ws_route import router as ws_router
from utils.response import error_response
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
# 降噪：Chroma/PostHog telemetry 报错不影响功能
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("posthog").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)

rate_limit_store: Dict[str, List[float]] = {}
user_rate_limit_store: Dict[str, List[float]] = {}
RATE_LIMIT_COUNT = 10
USER_RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW = 60

try:
    from prometheus_fastapi_instrumentator import Instrumentator

    PROMETHEUS_ENABLED = True
except ImportError:
    logger.warning("未安装 prometheus-fastapi-instrumentator，监控功能禁用")
    PROMETHEUS_ENABLED = False


def _is_local_or_private_ip(ip_str: str) -> bool:
    """
    仅允许本机/内网 IP 才能使用评测绕过 header，避免被外网滥用。
    - loopback: 127.0.0.1 / ::1
    - private: 10.0.0.0/8, 172.16/12, 192.168/16
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return bool(ip_obj.is_loopback or ip_obj.is_private)
    except ValueError:
        return False


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="基于华为云大模型的情绪分析服务（含用户系统）",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if PROMETHEUS_ENABLED:
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        logger.info("Prometheus 监控已启用: /metrics")

    # ─────────────────────────────────────────────────────────────
    # 统一异常封装：避免 {"detail": "..."} 泄露到前端
    # ─────────────────────────────────────────────────────────────

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_response(code=422, msg="参数错误", data=exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # 统一封装 401/403/404/405 等 HTTPException
        msg = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(code=exc.status_code, msg=msg),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("未捕获异常 | %s | %s", request.url.path, str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content=error_response(code=500, msg=f"服务器内部错误: {str(exc)}"),
        )

    # ─────────────────────────────────────────────────────────────
    # 限流中间件（修复：SSE 被限流时也要返回 SSE）
    # ─────────────────────────────────────────────────────────────

    def _rate_limit_json(msg: str) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"code": 429, "msg": msg, "data": None},
        )

    def _rate_limit_sse(msg: str) -> StreamingResponse:
        async def gen():
            payload = json.dumps(
                {"type": "error", "code": 429, "msg": msg},
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
            yield 'data: {"type":"done"}\n\n'

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        # ── 评测专用绕过（更安全）：必须同时满足 ───────────────────────
        # 1) header: X-Eval-Run=1
        # 2) 来源 IP 为 loopback/内网（127.0.0.1/::1/10.*/172.16-31.*/192.168.*）
        if request.headers.get("X-Eval-Run") == "1":
            src_ip = request.client.host if request.client else ""
            if _is_local_or_private_ip(src_ip):
                return await call_next(request)
            logger.warning("[rate_limit] 拒绝外网使用 X-Eval-Run 绕过 | src=%s", src_ip)

        # 只限制情绪分析相关接口
        if "emo_analysis" in request.url.path:
            client_ip = request.client.host
            now = time.time()

            ip_history = rate_limit_store.get(client_ip, [])
            ip_history = [t for t in ip_history if now - t < RATE_LIMIT_WINDOW]

            if len(ip_history) >= RATE_LIMIT_COUNT:
                logger.warning("IP %s 请求超限", client_ip)
                msg = "请求太频繁，请休息一分钟再试"
                if "emo_analysis_stream" in request.url.path:
                    return _rate_limit_sse(msg)
                return _rate_limit_json(msg)

            # 可选：用户ID限流（尽量不影响主流程）
            try:
                user_id: object = None
                if request.method == "POST":
                    try:
                        body = await request.json()
                        user_id = body.get("user_id") or body.get("uid")
                    except Exception:
                        user_id = None

                if not user_id:
                    user_id = request.headers.get("X-User-ID")

                if user_id:
                    user_history = user_rate_limit_store.get(str(user_id), [])
                    user_history = [t for t in user_history if now - t < RATE_LIMIT_WINDOW]
                    if len(user_history) >= USER_RATE_LIMIT_COUNT:
                        msg = "单个用户请求太频繁，请稍候"
                        if "emo_analysis_stream" in request.url.path:
                            return _rate_limit_sse(msg)
                        return _rate_limit_json(msg)

                    user_history.append(now)
                    user_rate_limit_store[str(user_id)] = user_history

            except Exception as exc:
                logger.debug("用户ID限流解析失败: %s", exc)

            ip_history.append(now)
            rate_limit_store[client_ip] = ip_history

        return await call_next(request)

    # ─────────────────────────────────────────────────────────────
    # 路由注册
    # ─────────────────────────────────────────────────────────────

    app.include_router(emo_router, prefix="/api", tags=["情绪分析"])
    app.include_router(emo_router, tags=["情绪分析兼容"])
    app.include_router(stream_router, prefix="/api", tags=["流式输出"])
    app.include_router(feedback_router, prefix="/api", tags=["用户反馈"])
    app.include_router(auth_router, prefix="/api", tags=["用户认证"])
    app.include_router(history_router, prefix="/api", tags=["对话历史"])
    app.include_router(ws_router, prefix="/api", tags=["WebSocket"])

    @app.get("/", tags=["健康检查"])
    async def root():
        return {"status": "online", "version": settings.APP_VERSION}

    @app.on_event("startup")
    async def startup_event():
        try:
            from models.database import init_db  # noqa: PLC0415

            init_db()
            logger.info("数据库表初始化完成 ✅")
        except Exception as exc:
            logger.error("数据库初始化失败: %s", exc, exc_info=True)

        logger.info(
            "%s 启动成功 | v%s | USE_LANGGRAPH=%s | LANGFUSE_ENABLED=%s",
            settings.APP_NAME,
            settings.APP_VERSION,
            settings.USE_LANGGRAPH,
            settings.LANGFUSE_ENABLED,
        )

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("%s 正在关闭...", settings.APP_NAME)
        try:
            from agent.langfuse_client import flush  # noqa: PLC0415

            flush()
        except Exception:
            pass
        rate_limit_store.clear()
        user_rate_limit_store.clear()
        logger.info("%s 已关闭", settings.APP_NAME)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000, workers=1)
