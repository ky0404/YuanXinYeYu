"""JWT 鉴权 + bcrypt 密码工具"""
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends, Cookie
from sqlalchemy.orm import Session

from models.database import get_db
from models.user import User
from config.settings import settings

# bcrypt 密码上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto",bcrypt__truncate_error=False)


# ──────────────────────────────────────────
# 密码工具
# ──────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ──────────────────────────────────────────
# JWT 工具
# ──────────────────────────────────────────

def create_token(user_id: int, expire_days: int = 7) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=expire_days),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 无效或已过期，请重新登录")


# ──────────────────────────────────────────
# FastAPI 依赖：必须登录
# ──────────────────────────────────────────

def _set_cookie_options() -> dict:
    """统一 Cookie 参数"""
    return dict(
        key="access_token",
        httponly=True,          # JS 无法读取，防 XSS
        max_age=7 * 24 * 3600,
        samesite="lax",
        secure=settings.COOKIE_SECURE,   # 生产 HTTPS 时改 True
    )


async def get_current_user(
    access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = _decode_token(access_token)
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Token 格式错误")
    user = db.query(User).filter(User.id == int(uid)).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


# ──────────────────────────────────────────
# FastAPI 依赖：可选登录（未登录返回 None）
# ──────────────────────────────────────────

async def get_optional_user(
    access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not access_token:
        return None
    try:
        payload = _decode_token(access_token)
        uid = payload.get("sub")
        if not uid:
            return None
        return db.query(User).filter(User.id == int(uid)).first()
    except Exception:
        return None
