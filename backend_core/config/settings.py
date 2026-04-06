"""config/settings.py v2.3 — 新增游客限流、BM25、RAG引用、Verbose日志开关"""
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
    APP_VERSION: str = "2.3.0"
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

    # ── 离线保护（旧 RAG 遗留）──────────────────────────────
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

    # ── AutoGen 预留开关 ──────────────────────────────────────
    AUTOGEN_ENABLED: bool = os.getenv("AUTOGEN_ENABLED", "false").lower() == "true"

    # ── LangGraph 特性开关（默认 false）──────────────────────
    USE_LANGGRAPH: bool = os.getenv("USE_LANGGRAPH", "false").lower() == "true"

    # ── Langfuse 可观测性（默认 false）───────────────────────
    LANGFUSE_ENABLED:    bool = os.getenv("LANGFUSE_ENABLED",    "false").lower() == "true"
    LANGFUSE_PUBLIC_KEY: str  = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str  = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST:       str  = os.getenv("LANGFUSE_HOST",       "https://cloud.langfuse.com")

    # ════════════════════════════════════════════════════════════
    # 新增 v2.3
    # ════════════════════════════════════════════════════════════

    # ── 游客每日额度上限（默认 5 次，可调整）────────────────
    GUEST_DAILY_LIMIT: int = int(os.getenv("GUEST_DAILY_LIMIT", "5"))

    # ── BM25 检索开关（P1，默认关闭）────────────────────────
    ENABLE_BM25:   bool  = os.getenv("ENABLE_BM25",  "false").lower() == "true"
    BM25_WEIGHT:   float = float(os.getenv("BM25_WEIGHT", "0.3"))
    # RRF k 参数（Reciprocal Rank Fusion），60 是业界惯例
    BM25_RRF_K:    int   = int(os.getenv("BM25_RRF_K", "60"))

    # ── RAG 引用溯源（P1，默认关闭）─────────────────────────
    # true 时在 data._refs 返回检索来源（前端不强依赖此字段）
    ENABLE_RAG_REFS: bool = os.getenv("ENABLE_RAG_REFS", "false").lower() == "true"

    # ── 节点状态详细日志（P1，默认关闭）─────────────────────
    ENABLE_VERBOSE_LOG: bool = os.getenv("ENABLE_VERBOSE_LOG", "false").lower() == "true"

    # ── Eval LLM-as-judge（P0.3，默认关闭）──────────────────
    EVAL_LLM_JUDGE: bool = os.getenv("EVAL_LLM_JUDGE", "false").lower() == "true"

    # ── Eval 跳过缓存的特殊请求头（内部用，无需对外文档）───
    EVAL_NO_CACHE_HEADER: str = os.getenv("EVAL_NO_CACHE_HEADER", "X-Eval-No-Cache")

    # ── CORS ──────────────────────────────────────────────────
    @property
    def CORS_ORIGINS(self) -> List[str]:
        env_val = os.getenv("CORS_ORIGINS", "")
        if env_val:
            return [o.strip() for o in env_val.split(",") if o.strip()]
        if self.ENV == "dev":
            return ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
        return ["https://www.dukkha.top", "https://dukkha.top"]

    # ── 情绪分类映射 ──────────────────────────────────────────
    SENTIMENT_CATEGORIES: dict = {
        1: "正面", 2: "负面", 3: "正负混合", 4: "中性", 5: "不相关"
    }

    class Config:
        env_file          = ".env"
        env_file_encoding = "utf-8"
        extra             = "ignore"


settings = Settings()
