"""用户认证路由：注册 / 登录 / 登出 / 当前用户"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.database import get_db
from models.user import User
from utils.auth import hash_password, verify_password, create_token, get_current_user, _set_cookie_options
from utils.response import success_response, error_response

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────
# 请求模型
# ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:    str = Field(..., min_length=5,  max_length=255)
    password: str = Field(..., min_length=6,  max_length=100)
    username: Optional[str] = Field(default=None, max_length=50)


class LoginRequest(BaseModel):
    email:    str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


# ──────────────────────────────────────────
# 路由
# ──────────────────────────────────────────

@router.post("/auth/register", summary="注册")
async def register(req: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        return error_response(code=400, msg="该邮箱已注册，请直接登录")

    user = User(
        email=email,
        username=req.username or email.split("@")[0],
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    response.set_cookie(value=token, **_set_cookie_options())
    logger.info(f"新用户注册 | id={user.id} email={email}")
    return success_response(data={"id": user.id, "email": user.email, "username": user.username})


@router.post("/auth/login", summary="登录")
async def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        return error_response(code=401, msg="邮箱或密码错误")

    token = create_token(user.id)
    response.set_cookie(value=token, **_set_cookie_options())
    logger.info(f"用户登录 | id={user.id} email={email}")
    return success_response(data={"id": user.id, "email": user.email, "username": user.username})


@router.post("/auth/logout", summary="登出")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return success_response(data={"msg": "已退出登录"})


@router.get("/auth/me", summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    return success_response(data={
        "id":         current_user.id,
        "email":      current_user.email,
        "username":   current_user.username,
        "created_at": current_user.created_at.isoformat(),
    })
