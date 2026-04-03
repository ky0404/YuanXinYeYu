"""api/main.py v2 - 新增 GZip压缩 + 流式路由 + 反馈路由

改动说明：
1. GzipMiddleware：3行代码，响应体积降 30-50%，对 2G 服务器完全友好
2. 注册 stream_router（SSE 流式输出）
3. 注册 feedback_router（RLHF 数据飞轮）
4. 其余逻辑完全不变
"""
import logging
import time
from typing import Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from api.routes.emo_route     import router as emo_router
from api.routes.auth_route    import router as auth_router
from api.routes.history_route import router as history_router
from api.routes.stream_route  import router as stream_router    # ← 新增
from api.routes.feedback_route import router as feedback_router  # ← 新增
from utils.response import error_response
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

rate_limit_store:       Dict[str, List[float]] = {}
user_rate_limit_store:  Dict[str, List[float]] = {}
RATE_LIMIT_COUNT       = 10
USER_RATE_LIMIT_COUNT  = 5
RATE_LIMIT_WINDOW      = 60

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    PROMETHEUS_ENABLED = True
except ImportError:
    logger.warning("未安装 prometheus-fastapi-instrumentator，监控功能禁用")
    PROMETHEUS_ENABLED = False


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="基于华为云大模型的情绪分析服务（含用户系统）",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── 1. GZip 压缩（新增，3行代码，响应体积降 30-50%）──────────────────
    # minimum_size=500：小于 500 字节的响应不压缩（避免反效果）
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # ── 2. CORS ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 3. Prometheus（必须在中间件之前注册）──────────────────────────────
    if PROMETHEUS_ENABLED:
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        logger.info("Prometheus 监控已启用: /metrics")

    # ── 4. 限流中间件 ──────────────────────────────────────────────────────
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if "emo_analysis" in request.url.path:
            client_ip = request.client.host
            now = time.time()

            ip_history = rate_limit_store.get(client_ip, [])
            ip_history = [t for t in ip_history if now - t < RATE_LIMIT_WINDOW]
            if len(ip_history) >= RATE_LIMIT_COUNT:
                return JSONResponse(
                    status_code=429,
                    content={"code": 429, "msg": "请求太频繁，请休息一分钟再试", "data": None},
                )
            try:
                user_id = None
                if request.method == "POST":
                    body = await request.json()
                    user_id = body.get("user_id") or body.get("uid")
                if not user_id:
                    user_id = request.headers.get("X-User-ID")
                if user_id:
                    user_history = user_rate_limit_store.get(user_id, [])
                    user_history = [t for t in user_history if now - t < RATE_LIMIT_WINDOW]
                    if len(user_history) >= USER_RATE_LIMIT_COUNT:
                        return JSONResponse(
                            status_code=429,
                            content={"code": 429, "msg": "单个用户请求太频繁，请稍候", "data": None},
                        )
                    user_history.append(now)
                    user_rate_limit_store[user_id] = user_history
            except Exception as e:
                logger.debug("用户ID限流解析失败: %s", e)
            ip_history.append(now)
            rate_limit_store[client_ip] = ip_history
        return await call_next(request)

    # ── 5. 注册路由 ────────────────────────────────────────────────────────
    app.include_router(emo_router,      prefix="/api", tags=["情绪分析"])
    app.include_router(emo_router,                     tags=["情绪分析兼容"])
    app.include_router(stream_router,   prefix="/api", tags=["流式输出"])     # ← 新增
    app.include_router(feedback_router, prefix="/api", tags=["用户反馈"])     # ← 新增
    app.include_router(auth_router,     prefix="/api", tags=["用户认证"])
    app.include_router(history_router,  prefix="/api", tags=["对话历史"])

    @app.get("/", tags=["健康检查"])
    async def root():
        return {"status": "online", "version": settings.APP_VERSION}

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("未捕获异常 | %s | %s", request.url.path, str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content=error_response(code=500, msg=f"服务器内部错误: {str(exc)}"),
        )

    @app.on_event("startup")
    async def startup_event():
        try:
            from models.database import init_db
            init_db()
            logger.info("数据库表初始化完成 ✅")
        except Exception as e:
            logger.error("数据库初始化失败: %s", e, exc_info=True)

        logger.info("%s 启动成功 | 版本: %s", settings.APP_NAME, settings.APP_VERSION)

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("%s 已关闭", settings.APP_NAME)
        rate_limit_store.clear()
        user_rate_limit_store.clear()

    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000, workers=1)
