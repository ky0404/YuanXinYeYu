"""
结构化日志配置 - 放在 config/logging_config.py
支持：控制台彩色输出 + 文件滚动日志 + JSON格式（方便 ELK 接入）
"""
import logging
import logging.handlers
import os
from pythonjsonlogger import jsonlogger
from config.settings import settings


def setup_logging() -> logging.Logger:
    """初始化日志系统，返回根 Logger"""

    log_dir = settings.LOG_DIR
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # ── 1. 控制台处理器（彩色人类可读）────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = ColorFormatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)

    # ── 2. 文件处理器（JSON，方便后续接 ELK/Loki）─────────────
    log_path = os.path.join(log_dir, settings.LOG_FILE)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB 自动滚动
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    json_formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    file_handler.setFormatter(json_formatter)

    # ── 3. 错误专用文件（只记录 ERROR 以上）────────────────────
    error_path = os.path.join(log_dir, "error.log")
    error_handler = logging.handlers.RotatingFileHandler(
        error_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)

    # 清除旧处理器，避免重复添加
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    # 静默第三方库的噪音日志
    for noisy in ("urllib3", "httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root_logger.info("日志系统初始化完成 | 日志目录: %s", log_dir)
    return root_logger


class ColorFormatter(logging.Formatter):
    """控制台彩色日志格式化"""
    COLORS = {
        logging.DEBUG:    "\033[36m",   # 青色
        logging.INFO:     "\033[32m",   # 绿色
        logging.WARNING:  "\033[33m",   # 黄色
        logging.ERROR:    "\033[31m",   # 红色
        logging.CRITICAL: "\033[35m",   # 紫色
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}{record.levelname:<8}{self.RESET}"
        return super().format(record)
