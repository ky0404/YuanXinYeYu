import logging
import time
from typing import Dict, List
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes.emo_route     import router as emo_router
from api.routes.auth_route    import router as auth_router
from api.routes.history_route import router as history_router
from config.settings import settings

# 日志配置（仅输出到控制台，不包含敏感配置）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 限流存储
rate_limit_store: Dict[str, List[float]] = {}

def create_app() -> FastAPI:
    # 生产环境关闭 docs 交互文档，防止 API 结构泄露
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url=None if settings.ENV == "prod" else "/docs",
        redoc_url=None
    )

    # 1. CORS 严格化
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # 2. 全局异常处理（隐私护盾）
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # 详细错误只记在服务器本地日志里
        logger.error(f"CRITICAL_ERROR | {request.method} {request.url.path} | {str(exc)}", exc_info=True)
        # 返回给浏览器的必须是一句废话，绝不泄露后端逻辑
        return JSONResponse(
            status_code=500,
            content={"code": 500, "msg": "系统繁忙，请稍后再试", "data": None}
        )

    # 3. 注册路由
    app.include_router(emo_router, prefix="/api", tags=["情绪分析"])
    app.include_router(auth_router, prefix="/api", tags=["用户认证"])
    app.include_router(history_router, prefix="/api", tags=["对话历史"])

    @app.on_event("startup")
    async def startup_event():
        try:
            from models.database import init_db
            init_db()
            logger.info("Service initialized successfully.")
        except Exception as e:
            logger.error(f"Database init failed: {e}")

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)