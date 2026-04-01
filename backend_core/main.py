"""项目启动入口"""
import sys
import uvicorn
from config.logging_config import setup_logging
from config.settings import settings
from api.main import create_app


def main():
    """启动服务"""
    # 初始化日志
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info(f"正在启动 {settings.APP_NAME}...")
    logger.info("=" * 60)

    # 创建FastAPI应用
    app = create_app()

    # 启动服务
    try:
        uvicorn.run(
            app,
            host=settings.HOST,
            port=settings.PORT,
            log_level=settings.LOG_LEVEL.lower(),
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("服务已手动停止")
        sys.exit(0)
    except Exception as e:
        logger.error(f"服务启动失败: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

# ============================================
# systemd服务入口 (修复添加)
# ============================================
app = create_app()
