"""config/settings.py — 项目配置，增量新增 RAG 相关字段"""
import os
import secrets
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)


class Settings(BaseSettings):
    # ── 环境 ──────────────────────────────────────────────────
    ENV: str = os.getenv("ENV", "prod")

    # ── 服务 ──────────────────────────────────────────────────
    APP_NAME:    str = "情绪分析心理疏导服务"
    APP_VERSION: str = "2.1.0"
    HOST:        str = os.getenv("HOST", "127.0.0.1")
    PORT:        int = int(os.getenv("PORT", "8000"))

    # ── 华为云 LLM ────────────────────────────────────────────
    HUAWEI_API_KEY:  str = os.getenv("HUAWEI_API_KEY", "")
    HUAWEI_API_BASE: str = os.getenv(
        "HUAWEI_API_BASE", "https://api.modelarts-maas.com/openai/v1"
    )
    HUAWEI_MODEL: str = os.getenv("HUAWEI_MODEL", "deepseek-v3.2")

    # ── 数据库 ────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./emotion.db")

    # ── JWT ───────────────────────────────────────────────────
    JWT_SECRET:      str = os.getenv("JWT_SECRET", secrets.token_hex(32))
    JWT_EXPIRE_DAYS: int = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
    COOKIE_SECURE:   bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"

    # ── HTTP 客户端 ───────────────────────────────────────────
    REQUEST_TIMEOUT:  int   = int(os.getenv("REQUEST_TIMEOUT", "10"))
    REQUEST_RETRY:    int   = int(os.getenv("REQUEST_RETRY", "3"))
    RETRY_BASE_DELAY: float = float(os.getenv("RETRY_BASE_DELAY", "1.0"))

    # ── 离线保护（旧 RAG 遗留，保持兼容）────────────────────
    TRANSFORMERS_OFFLINE:   bool = os.getenv("TRANSFORMERS_OFFLINE", "0") == "1"
    HF_DATASETS_OFFLINE:    bool = os.getenv("HF_DATASETS_OFFLINE", "0") == "1"
    HUGGINGFACE_HUB_OFFLINE: bool = os.getenv("HUGGINGFACE_HUB_OFFLINE", "0") == "1"

    # ── 日志 ──────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR:   str = os.getenv("LOG_DIR", "logs")
    LOG_FILE:  str = os.getenv("LOG_FILE", "emotion_service.log")

    # ── 新增：API Embedding（三混合 RAG 专用，禁本地模型）────
    EMBEDDING_API_KEY:  str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_API_BASE: str = os.getenv("EMBEDDING_API_BASE", "")
    EMBEDDING_MODEL:    str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_TIMEOUT:  int = int(os.getenv("EMBEDDING_TIMEOUT", "15"))

    # ── 新增：ChromaDB（向量存储）────────────────────────────
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
    CHROMA_COLLECTION:  str = os.getenv("CHROMA_COLLECTION", "psych_kb")

    # ── 新增：知识图谱 SQLite────────────────────────────────
    KG_SQLITE_PATH: str = os.getenv("KG_SQLITE_PATH", "./data/kg.sqlite")

    # ── 新增：AutoGen 开关（预留，默认关闭）─────────────────
    AUTOGEN_ENABLED: bool = os.getenv("AUTOGEN_ENABLED", "false").lower() == "true"

    # ── CORS ──────────────────────────────────────────────────
    @property
    def CORS_ORIGINS(self) -> List[str]:
        env_val = os.getenv("CORS_ORIGINS", "")
        if env_val:
            return [o.strip() for o in env_val.split(",") if o.strip()]
        if self.ENV == "dev":
            return [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
            ]
        return ["https://www.dukkha.top", "https://dukkha.top"]

    # ── 情绪分类 ──────────────────────────────────────────────
    SENTIMENT_CATEGORIES: dict = {
        1: "正面", 2: "负面", 3: "正负混合", 4: "中性", 5: "不相关"
    }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"          # 保持原有，忽略 .env 中多余字段


settings = Settings()
