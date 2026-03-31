import os
import secrets
import logging
from typing import List
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 加载 .env 文件
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

class Settings(BaseSettings):
    """项目配置类 - 严格匹配原代码引用"""

    # 环境标识
    ENV: str = os.getenv("ENV", "prod")

    # 服务配置
    APP_NAME:    str = "情绪分析心理疏导服务"
    APP_VERSION: str = "2.0.0"
    HOST:        str = os.getenv("HOST", "127.0.0.1")
    PORT:        int = int(os.getenv("PORT", "8000"))

    # 华为云配置
    HUAWEI_API_KEY:  str = os.getenv("HUAWEI_API_KEY", "")
    HUAWEI_API_BASE: str = os.getenv("HUAWEI_API_BASE", "https://api.modelarts-maas.com/openai/v1")
    HUAWEI_MODEL:    str = os.getenv("HUAWEI_MODEL", "deepseek-v3.2")

    # 数据库配置
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./emotion.db")

    # JWT 安全配置
    JWT_SECRET:    str = os.getenv("JWT_SECRET", secrets.token_hex(32))
    JWT_EXPIRE_DAYS: int = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

    # Cookie 安全
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"

    # 【核心修复】补齐原代码中 request.py 调用的变量
    REQUEST_TIMEOUT:  int   = int(os.getenv("REQUEST_TIMEOUT", "10"))
    REQUEST_RETRY:    int   = int(os.getenv("REQUEST_RETRY", "3"))
    RETRY_BASE_DELAY: float = float(os.getenv("RETRY_BASE_DELAY", "1.0"))

    # 离线配置
    TRANSFORMERS_OFFLINE: bool = os.getenv("TRANSFORMERS_OFFLINE", "0") == "1"
    HF_DATASETS_OFFLINE: bool = os.getenv("HF_DATASETS_OFFLINE", "0") == "1"
    HUGGINGFACE_HUB_OFFLINE: bool = os.getenv("HUGGINGFACE_HUB_OFFLINE", "0") == "1"

    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR:   str = os.getenv("LOG_DIR", "logs")
    LOG_FILE:  str = os.getenv("LOG_FILE", "emotion_service.log")

    @property
    def CORS_ORIGINS(self) -> List[str]:
        if self.ENV == "dev":
            return ["http://localhost:5173", "http://127.0.0.1:5173"]
        return ["https://www.dukkha.top", "https://dukkha.top"]

    # 情绪分类配置
    SENTIMENT_CATEGORIES: dict = {
        1: "正面", 2: "负面", 3: "正负混合", 4: "中性", 5: "不相关"
    }

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
# 绝对不打印 settings 内容，保护 API Key