"""config/settings.py v2.5
在 v2.4 基础上新增：
  - SMTP 邮件服务配置
  - 邮箱验证码频控配置
  - 微信 OAuth 配置（可选）
"""
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
    APP_VERSION: str = "2.5.0"
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
    JWT_SECRET:      str  = os.getenv("JWT_SECRET", secrets.token_hex(32))
    JWT_EXPIRE_DAYS: int  = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
    COOKIE_SECURE:   bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"

    # ── HTTP 客户端 ───────────────────────────────────────────
    REQUEST_TIMEOUT:  int   = int(os.getenv("REQUEST_TIMEOUT", "10"))
    REQUEST_RETRY:    int   = int(os.getenv("REQUEST_RETRY", "3"))
    RETRY_BASE_DELAY: float = float(os.getenv("RETRY_BASE_DELAY", "1.0"))

    # ── 离线保护 ──────────────────────────────────────────────
    TRANSFORMERS_OFFLINE:    bool = os.getenv("TRANSFORMERS_OFFLINE",    "0") == "1"
    HF_DATASETS_OFFLINE:     bool = os.getenv("HF_DATASETS_OFFLINE",     "0") == "1"
    HUGGINGFACE_HUB_OFFLINE: bool = os.getenv("HUGGINGFACE_HUB_OFFLINE", "0") == "1"

    # ── 日志 ──────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR:   str = os.getenv("LOG_DIR",   "logs")
    LOG_FILE:  str = os.getenv("LOG_FILE",  "emotion_service.log")

    # ── RAG：API Embedding ────────────────────────────────────
    EMBEDDING_API_KEY:  str = os.getenv("EMBEDDING_API_KEY",  "")
    EMBEDDING_API_BASE: str = os.getenv("EMBEDDING_API_BASE", "")
    EMBEDDING_MODEL:    str = os.getenv("EMBEDDING_MODEL",    "text-embedding-3-small")
    EMBEDDING_TIMEOUT:  int = int(os.getenv("EMBEDDING_TIMEOUT", "15"))

    # ── RAG：ChromaDB ─────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
    CHROMA_COLLECTION:  str = os.getenv("CHROMA_COLLECTION",  "psych_kb")

    # ── RAG：知识图谱 SQLite ──────────────────────────────────
    KG_SQLITE_PATH: str = os.getenv("KG_SQLITE_PATH", "./data/kg.sqlite")

    # ── 特性开关 ──────────────────────────────────────────────
    AUTOGEN_ENABLED:    bool = os.getenv("AUTOGEN_ENABLED",    "false").lower() == "true"
    USE_LANGGRAPH:      bool = os.getenv("USE_LANGGRAPH",      "false").lower() == "true"
    LANGFUSE_ENABLED:   bool = os.getenv("LANGFUSE_ENABLED",   "false").lower() == "true"
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST:       str = os.getenv("LANGFUSE_HOST",       "https://cloud.langfuse.com")

    # ── 游客限流 ──────────────────────────────────────────────
    GUEST_DAILY_LIMIT: int = int(os.getenv("GUEST_DAILY_LIMIT", "5"))

    # ── BM25 ─────────────────────────────────────────────────
    ENABLE_BM25:   bool  = os.getenv("ENABLE_BM25",  "false").lower() == "true"
    BM25_WEIGHT:   float = float(os.getenv("BM25_WEIGHT", "0.3"))
    BM25_RRF_K:    int   = int(os.getenv("BM25_RRF_K", "60"))

    # ── RAG 开关 ──────────────────────────────────────────────
    ENABLE_RAG_REFS:    bool = os.getenv("ENABLE_RAG_REFS",    "false").lower() == "true"
    ENABLE_VERBOSE_LOG: bool = os.getenv("ENABLE_VERBOSE_LOG", "false").lower() == "true"

    # ── Eval ──────────────────────────────────────────────────
    EVAL_LLM_JUDGE:       bool = os.getenv("EVAL_LLM_JUDGE", "false").lower() == "true"
    EVAL_NO_CACHE_HEADER: str  = os.getenv("EVAL_NO_CACHE_HEADER", "X-Eval-No-Cache")

    # ── v2.4 配置项 ───────────────────────────────────────────
    STREAM_TOKEN_DELAY_MS:      int   = int(os.getenv("STREAM_TOKEN_DELAY_MS", "28"))
    MAX_HISTORY_TURNS:          int   = int(os.getenv("MAX_HISTORY_TURNS", "500"))
    ENABLE_RESPONSE_TIME_LOG:   bool  = os.getenv("ENABLE_RESPONSE_TIME_LOG", "true").lower() == "true"
    CACHE_SIMILARITY_THRESHOLD: float = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92"))

    # ════════════════════════════════════════════════════════════
    # ✅ v2.5 新增：SMTP 邮件服务配置
    # ════════════════════════════════════════════════════════════
    SMTP_HOST:      str = os.getenv("SMTP_HOST", "")
    SMTP_PORT:      int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER:      str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD:  str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "")
    SMTP_FROM_NAME:  str = os.getenv("SMTP_FROM_NAME", "媛心烨语")

    # ✅ v2.5 新增：验证码频控
    EMAIL_CODE_EXPIRE_MINUTES: int = int(os.getenv("EMAIL_CODE_EXPIRE_MINUTES", "5"))
    EMAIL_CODE_RESEND_SECONDS: int = int(os.getenv("EMAIL_CODE_RESEND_SECONDS", "60"))
    EMAIL_CODE_DAILY_LIMIT:    int = int(os.getenv("EMAIL_CODE_DAILY_LIMIT", "20"))

    # ✅ v2.5 新增：GitHub OAuth
    GITHUB_CLIENT_ID:     str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_REDIRECT_URI:  str = os.getenv("GITHUB_REDIRECT_URI", "")
    GITHUB_SCOPE:         str = os.getenv("GITHUB_SCOPE", "read:user user:email")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://www.dukkha.top")



    # ── CORS ──────────────────────────────────────────────────
    @property
    def CORS_ORIGINS(self) -> List[str]:
        env_val = os.getenv("CORS_ORIGINS", "")
        if env_val:
            return [o.strip() for o in env_val.split(",") if o.strip()]
        if self.ENV == "dev":
            return ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
        return ["https://www.dukkha.top", "https://dukkha.top"]

    SENTIMENT_CATEGORIES: dict = {
        1: "正面", 2: "负面", 3: "正负混合", 4: "中性", 5: "不相关"
    }

    class Config:
        env_file          = ".env"
        env_file_encoding = "utf-8"
        extra             = "ignore"


settings = Settings()
