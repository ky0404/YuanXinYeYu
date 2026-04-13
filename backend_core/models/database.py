"""数据库连接与会话管理。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import settings

_connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：为每次请求提供独立 Session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表（幂等，可重复执行）。"""
    from models.user import User, ChatHistory                      # noqa: F401
    from models.emotion_record import EmotionRecord                # noqa: F401
    from models.guest_quota import GuestQuota                      # noqa: F401
    from models.email_verification_code import EmailVerificationCode  # noqa: F401 ✅ v2.5

    Base.metadata.create_all(bind=engine)
