"""config/settings.py v2.6
在 v2.5 基础上新增（全部默认关闭）：
  - SSE 增强功能开关：thinking / breathing / guide
  - Prompt 增强功能开关：grounding / vulnerability_probe / emotion_mirror
  - 用户画像功能开关：user_profile / followup_task
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
    APP_VERSION: str = "2.6.0"
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
    AUTOGEN_ENABLED:     bool = os.getenv("AUTOGEN_ENABLED",    "false").lower() == "true"
    USE_LANGGRAPH:       bool = os.getenv("USE_LANGGRAPH",      "false").lower() == "true"
    LANGFUSE_ENABLED:    bool = os.getenv("LANGFUSE_ENABLED",   "false").lower() == "true"
    LANGFUSE_PUBLIC_KEY: str  = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str  = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST:       str  = os.getenv("LANGFUSE_HOST",       "https://cloud.langfuse.com")

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

    # ── v2.5 配置项 ───────────────────────────────────────────
    SMTP_HOST:      str = os.getenv("SMTP_HOST", "")
    SMTP_PORT:      int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER:      str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD:  str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "")
    SMTP_FROM_NAME:  str = os.getenv("SMTP_FROM_NAME", "媛心烨语")

    EMAIL_CODE_EXPIRE_MINUTES: int = int(os.getenv("EMAIL_CODE_EXPIRE_MINUTES", "5"))
    EMAIL_CODE_RESEND_SECONDS: int = int(os.getenv("EMAIL_CODE_RESEND_SECONDS", "60"))
    EMAIL_CODE_DAILY_LIMIT:    int = int(os.getenv("EMAIL_CODE_DAILY_LIMIT", "20"))

    GITHUB_CLIENT_ID:     str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_REDIRECT_URI:  str = os.getenv("GITHUB_REDIRECT_URI", "")
    GITHUB_SCOPE:         str = os.getenv("GITHUB_SCOPE", "read:user user:email")
    FRONTEND_URL:         str = os.getenv("FRONTEND_URL", "https://www.dukkha.top")

    # ════════════════════════════════════════════════════════════
    # ✅ v2.6 新增：SSE 增强功能开关（全部默认关闭）
    # ════════════════════════════════════════════════════════════

    # SSE thinking 事件：分析前先推送"正在感受..."改善等待 UX
    # 开启方式：ENABLE_SSE_THINKING=true
    # 回滚方式：ENABLE_SSE_THINKING=false（或删除该配置）
    ENABLE_SSE_THINKING: bool = os.getenv("ENABLE_SSE_THINKING", "false").lower() == "true"

    # 呼吸节奏输出：高痛苦状态下放慢打字速度，营造陪伴感
    # 触发条件：sentiment_category==2 且 score >= BREATHING_SCORE_THRESHOLD
    ENABLE_BREATHING_PAUSE:      bool  = os.getenv("ENABLE_BREATHING_PAUSE",      "false").lower() == "true"
    BREATHING_TOKEN_DELAY_MS:    int   = int(os.getenv("BREATHING_TOKEN_DELAY_MS",    "45"))   # 高痛苦时每字间隔 ms
    BREATHING_SCORE_THRESHOLD:   float = float(os.getenv("BREATHING_SCORE_THRESHOLD", "7.0"))  # 触发分数阈值

    # SSE guide 事件：在 analysis 事件后额外推送引导语，前端可单独展示
    ENABLE_SSE_EMOTION_GUIDE: bool = os.getenv("ENABLE_SSE_EMOTION_GUIDE", "false").lower() == "true"

    # ════════════════════════════════════════════════════════════
    # ✅ v2.6 新增：Prompt 增强功能开关（全部默认关闭）
    # 均通过在 rag_context 末尾追加约束/引导文字实现，不修改 huawei_nlp.py
    # 回滚方式：将对应开关设为 false 即刻生效
    # ════════════════════════════════════════════════════════════

    # RAG 防幻觉约束：有 RAG 上下文时追加"不得捏造"约束
    ENABLE_RAG_GROUNDING: bool = os.getenv("ENABLE_RAG_GROUNDING", "false").lower() == "true"

    # 脆弱信号主动引导：medium/high 风险时追加温和开放式问题引导
    ENABLE_VULNERABILITY_PROBE: bool = os.getenv("ENABLE_VULNERABILITY_PROBE", "false").lower() == "true"

    # 情绪镜像风格匹配：根据 risk_level 追加回复语气要求
    ENABLE_EMOTION_MIRROR: bool = os.getenv("ENABLE_EMOTION_MIRROR", "false").lower() == "true"

    # ════════════════════════════════════════════════════════════
    # ✅ v2.6 新增：用户画像功能开关（默认关闭，需先 init_db 建表）
    # ════════════════════════════════════════════════════════════

    # 用户画像：登录用户可用，游客自动跳过，失败返回空画像
    ENABLE_USER_PROFILE: bool = os.getenv("ENABLE_USER_PROFILE", "false").lower() == "true"

    # 72小时危机随访任务（预留，功能待实现）
    ENABLE_FOLLOWUP_TASK: bool = os.getenv("ENABLE_FOLLOWUP_TASK", "false").lower() == "true"

    # 深度画像 Agent（低频异步）
    ENABLE_DEEP_PROFILE: bool = os.getenv("ENABLE_DEEP_PROFILE", "false").lower() == "true"
    DEEP_PROFILE_REFRESH_EVERY: int = int(os.getenv("DEEP_PROFILE_REFRESH_EVERY", "10"))


    # ════════════════════════════════════════════════════════════════
    # ✅ v2.7 新增：PersonalRAG / 情绪关联记忆（默认关闭）
    # ════════════════════════════════════════════════════════════════

    # PersonalRAG：读取用户近期情绪关键词，增强 RAG 检索相关性
    # 开启条件：USE_LANGGRAPH=true + ENABLE_PERSONAL_RAG=true + 用户已登录
    # 开启方式：ENABLE_PERSONAL_RAG=true
    # 回滚方式：ENABLE_PERSONAL_RAG=false
    ENABLE_PERSONAL_RAG: bool = os.getenv("ENABLE_PERSONAL_RAG", "false").lower() == "true"

    # PersonalRAG 参数：读取最近 N 条情绪记录的关键词
    PERSONAL_RAG_HISTORY_N: int = int(os.getenv("PERSONAL_RAG_HISTORY_N", "10"))

    # 情绪关联记忆：将近期情绪趋势摘要注入 Prompt（需 ENABLE_USER_PROFILE=true 同时开启）
    ENABLE_EMOTION_CONTEXT: bool = os.getenv("ENABLE_EMOTION_CONTEXT", "false").lower() == "true"
    
    # PersonalRAG 有效案例增强：结合 feedback like 召回更有效的历史回应
    ENABLE_EFFECTIVE_CASE_MEMORY: bool = os.getenv("ENABLE_EFFECTIVE_CASE_MEMORY", "true").lower() == "true"

    # PersonalRAG 仪式感模板增强：允许注入“第 N 次提到类似感受”等线索
    ENABLE_RITUAL_MEMORY_TEMPLATE: bool = os.getenv("ENABLE_RITUAL_MEMORY_TEMPLATE", "true").lower() == "true"

    # 长期记忆：每次按需取最近 N 条
    LONG_TERM_MEMORY_RECENT_N: int = int(os.getenv("LONG_TERM_MEMORY_RECENT_N", "10"))

    # 深度画像：低频异步刷新开关
    ENABLE_DEEP_PROFILE: bool = os.getenv("ENABLE_DEEP_PROFILE", "false").lower() == "true"

    # 深度画像：每累计多少条记录刷新一次
    DEEP_PROFILE_REFRESH_EVERY: int = int(os.getenv("DEEP_PROFILE_REFRESH_EVERY", "10"))


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
