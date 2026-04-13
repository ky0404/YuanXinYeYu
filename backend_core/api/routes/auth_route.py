"""用户认证路由 v2.5
原有接口（完全不动）：
  POST /auth/register
  POST /auth/login
  POST /auth/logout
  GET  /auth/me

新增接口：
  POST /auth/send-email-code   发送邮箱验证码
  POST /auth/email-login       验证码登录/自动注册
  POST /auth/reset-password    找回密码
  GET  /auth/github/login      获取 GitHub 授权 URL
  GET  /auth/github/callback   GitHub OAuth 回调（修复版）
"""
from __future__ import annotations

import logging
import re
import secrets
import requests
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from config.settings import settings
from models.database import get_db
from models.email_verification_code import EmailVerificationCode
from models.user import User
from service.email_service import (
    generate_email_code,
    send_verification_email,
    smtp_is_configured,
)
from utils.auth import (
    _set_cookie_options,
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from utils.response import error_response, success_response

logger = logging.getLogger(__name__)
router = APIRouter()

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


# ════════════════════════════════════════════════════════════════════════════════
# 原有接口（完全保留，一字不改）
# ════════════════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    email:    str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6, max_length=100)
    username: Optional[str] = Field(default=None, max_length=50)


class LoginRequest(BaseModel):
    email:    str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


@router.post("/auth/register", summary="密码注册")
async def register(req: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        return error_response(code=400, msg="该邮箱已注册，请直接登录")

    user = User(
        email=email,
        username=req.username or email.split("@")[0],
        hashed_password=hash_password(req.password),
        login_type="password",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    response.set_cookie(value=token, **_set_cookie_options())
    logger.info("新用户密码注册 | id=%d email=%s", user.id, email)
    return success_response(data={"id": user.id, "email": user.email, "username": user.username})


@router.post("/auth/login", summary="密码登录")
async def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    user  = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        return error_response(code=401, msg="邮箱或密码错误")

    token = create_token(user.id)
    response.set_cookie(value=token, **_set_cookie_options())
    logger.info("用户密码登录 | id=%d email=%s", user.id, email)
    return success_response(data={"id": user.id, "email": user.email, "username": user.username})


@router.post("/auth/logout", summary="登出")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return success_response(data={"msg": "已退出登录"})


@router.get("/auth/me", summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    return success_response(data={
        "id":             current_user.id,
        "email":          current_user.email,
        "username":       current_user.username,
        "created_at":     current_user.created_at.isoformat(),
        "login_type":     getattr(current_user, "login_type", "password"),
        "email_verified": getattr(current_user, "email_verified", 0),
    })


# ════════════════════════════════════════════════════════════════════════════════
# 发送邮箱验证码
# ════════════════════════════════════════════════════════════════════════════════

class SendEmailCodeRequest(BaseModel):
    email:   str = Field(..., min_length=5, max_length=255)
    purpose: str = Field(..., description="login 或 reset_password")


@router.post("/auth/send-email-code", summary="发送邮箱验证码")
async def send_email_code(
    req:     SendEmailCodeRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    email   = req.email.lower().strip()
    purpose = req.purpose

    if not _validate_email(email):
        return error_response(code=400, msg="邮箱格式不正确")

    if purpose not in ("login", "reset_password"):
        return error_response(code=400, msg="purpose 参数错误")

    if not smtp_is_configured():
        return error_response(code=503, msg="邮件服务暂未配置，请联系管理员或使用密码登录")

    if purpose == "reset_password":
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return error_response(code=404, msg="该邮箱尚未注册，请先注册")

    resend_window = datetime.utcnow() - timedelta(seconds=settings.EMAIL_CODE_RESEND_SECONDS)
    recent = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email      == email,
            EmailVerificationCode.purpose    == purpose,
            EmailVerificationCode.created_at >= resend_window,
        )
        .first()
    )
    if recent:
        return error_response(
            code=429,
            msg=f"发送太频繁，请 {settings.EMAIL_CODE_RESEND_SECONDS} 秒后再试",
        )

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email      == email,
            EmailVerificationCode.created_at >= today_start,
        )
        .count()
    )
    if today_count >= settings.EMAIL_CODE_DAILY_LIMIT:
        return error_response(code=429, msg="今日验证码发送次数已达上限，请明天再试")

    code       = generate_email_code()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.EMAIL_CODE_EXPIRE_MINUTES)
    client_ip  = request.client.host if request.client else None

    evc = EmailVerificationCode(
        email      = email,
        code       = code,
        purpose    = purpose,
        send_ip    = client_ip,
        expires_at = expires_at,
        used       = False,
    )
    db.add(evc)
    db.commit()

    ok = send_verification_email(email, code, purpose)
    if not ok:
        return error_response(code=500, msg="邮件发送失败，请稍后重试或使用密码登录")

    logger.info("验证码已发送 | email=%s purpose=%s ip=%s", email, purpose, client_ip)
    return success_response(data={
        "msg":     "验证码已发送，请查收邮件",
        "expires": settings.EMAIL_CODE_EXPIRE_MINUTES,
    })


# ════════════════════════════════════════════════════════════════════════════════
# 邮箱验证码登录 / 自动注册
# ════════════════════════════════════════════════════════════════════════════════

class EmailLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    code:  str = Field(..., min_length=6, max_length=6)


@router.post("/auth/email-login", summary="验证码登录（不存在则自动注册）")
async def email_login(
    req:      EmailLoginRequest,
    response: Response,
    db:       Session = Depends(get_db),
):
    email = req.email.lower().strip()

    if not _validate_email(email):
        return error_response(code=400, msg="邮箱格式不正确")

    evc = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email      == email,
            EmailVerificationCode.purpose    == "login",
            EmailVerificationCode.used       == False,   # noqa: E712
            EmailVerificationCode.expires_at >= datetime.utcnow(),
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .first()
    )

    if not evc:
        return error_response(code=400, msg="验证码不存在或已过期，请重新发送")

    if evc.code != req.code:
        return error_response(code=400, msg="验证码错误，请重新输入")

    evc.used = True
    db.commit()

    user   = db.query(User).filter(User.email == email).first()
    is_new = False

    if not user:
        random_pwd = secrets.token_urlsafe(24)
        user = User(
            email           = email,
            username        = email.split("@")[0],
            hashed_password = hash_password(random_pwd),
            email_verified  = 1,
            login_type      = "email_code",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        is_new = True
        logger.info("验证码自动注册 | id=%d email=%s", user.id, email)
    else:
        user.email_verified = 1
        db.commit()
        logger.info("验证码登录老用户 | id=%d email=%s", user.id, email)

    token = create_token(user.id)
    response.set_cookie(value=token, **_set_cookie_options())

    return success_response(data={
        "id":       user.id,
        "email":    user.email,
        "username": user.username,
        "is_new":   is_new,
    })


# ════════════════════════════════════════════════════════════════════════════════
# 找回密码
# ════════════════════════════════════════════════════════════════════════════════

class ResetPasswordRequest(BaseModel):
    email:            str = Field(..., min_length=5,  max_length=255)
    code:             str = Field(..., min_length=6,  max_length=6)
    new_password:     str = Field(..., min_length=6,  max_length=100)
    confirm_password: str = Field(..., min_length=6,  max_length=100)

    @validator("confirm_password")
    def passwords_match(cls, v, values):
        if "new_password" in values and v != values["new_password"]:
            raise ValueError("两次密码不一致")
        return v


@router.post("/auth/reset-password", summary="找回密码")
async def reset_password(
    req: ResetPasswordRequest,
    db:  Session = Depends(get_db),
):
    email = req.email.lower().strip()

    if not _validate_email(email):
        return error_response(code=400, msg="邮箱格式不正确")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        return error_response(code=404, msg="该邮箱未注册")

    evc = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email      == email,
            EmailVerificationCode.purpose    == "reset_password",
            EmailVerificationCode.used       == False,   # noqa: E712
            EmailVerificationCode.expires_at >= datetime.utcnow(),
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .first()
    )

    if not evc:
        return error_response(code=400, msg="验证码不存在或已过期，请重新发送")

    if evc.code != req.code:
        return error_response(code=400, msg="验证码错误")

    evc.used             = True
    user.hashed_password = hash_password(req.new_password)
    user.email_verified  = 1
    db.commit()

    logger.info("密码重置成功 | id=%d email=%s", user.id, email)
    return success_response(data={"msg": "密码重置成功，请使用新密码登录"})


# ════════════════════════════════════════════════════════════════════════════════
# ✅ GitHub OAuth（修复版）
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/auth/github/login", summary="获取 GitHub 授权 URL")
async def github_login(response: Response):
    """返回 GitHub OAuth 授权 URL，前端用于打开授权页。"""
    if not settings.GITHUB_CLIENT_ID:
        return error_response(code=503, msg="GitHub 登录暂未开放")

    # redirect_uri 必须与 GitHub OAuth App 配置完全一致
    redirect_uri = f"{settings.FRONTEND_URL}/api/auth/github/callback"
    state        = secrets.token_urlsafe(24)

    response.set_cookie(
        key="github_oauth_state",
        value=state,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        max_age=600,  # 10 分钟有效期
        samesite="lax",
        path="/"
    )

    auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user:email"
        f"&state={state}"
    )
    logger.info("[GitHub] 生成授权 URL | state=%s", state)
    return success_response(data={"auth_url": auth_url, "state": state})


@router.get("/auth/github/callback", summary="GitHub OAuth 回调（修复版）")
async def github_callback(
    code:     str,
    state:    str              = "",
    response: Response         = None,
    request:  Request          = None,
    db:       Session          = Depends(get_db),
):
    """
    GitHub 授权成功后跳转至此。
    修复要点：
    1. 设置 Cookie 后返回 HTML 页面
    2. HTML 同时兼容「弹窗模式（桌面）」和「整页跳转模式（手机）」
    3. 桌面：postMessage → 主页面刷新用户态 → 弹窗关闭
    4. 手机：直接跳回主页并附带 ?github_login=1，主页检测后刷新用户态
    """
    import httpx  # httpx 在 requirements.txt 中已存在

    frontend_url = settings.FRONTEND_URL  # e.g. https://www.dukkha.top

    stored_state = request.cookies.get("github_oauth_state") if request else None
    if not stored_state or stored_state != state:
        logger.warning("[GitHub] state 验证失败 | stored=%s | received=%s", stored_state, state)
        return _github_error_html(frontend_url, "安全验证失败，请重新登录")

    # ── 1. 用 code 换 access_token ────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_res = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id":     settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code":          code,
                    "redirect_uri":  f"{frontend_url}/api/auth/github/callback",
                },
                headers={"Accept": "application/json"},
            )
        token_data = token_res.json()
    except Exception as exc:
        logger.error("[GitHub] 换取 token 失败: %s", exc)
        return _github_error_html(frontend_url, "GitHub 服务连接失败，请稍后重试")

    if "error" in token_data or "access_token" not in token_data:
        error_desc = token_data.get("error_description", "授权失败")
        logger.warning("[GitHub] token 响应错误: %s", token_data)
        return _github_error_html(frontend_url, f"GitHub 授权失败：{error_desc}")

    access_token = token_data["access_token"]

    # ── 2. 获取 GitHub 用户信息 ───────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            user_res = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept":        "application/vnd.github+json",
                },
            )
        github_user = user_res.json()
    except Exception as exc:
        logger.error("[GitHub] 获取用户信息失败: %s", exc)
        return _github_error_html(frontend_url, "获取 GitHub 用户信息失败")

    github_id = str(github_user.get("id", ""))
    if not github_id:
        return _github_error_html(frontend_url, "GitHub 用户信息不完整")

    # ── 3. 获取邮箱（可能需要单独请求）──────────────────────────────────
    email = github_user.get("email") or ""
    if not email:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                emails_res = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept":        "application/vnd.github+json",
                    },
                )
            emails = emails_res.json()
            # 取第一个 primary + verified 的邮箱
            for em in emails:
                if isinstance(em, dict) and em.get("primary") and em.get("verified"):
                    email = em.get("email", "")
                    break
            # 若没有 primary，取第一个 verified
            if not email:
                for em in emails:
                    if isinstance(em, dict) and em.get("verified"):
                        email = em.get("email", "")
                        break
        except Exception:
            pass

    # 无邮箱时使用虚拟邮箱（GitHub id 作唯一标识）
    if not email:
        email = f"gh_{github_id}@github.dukkha.top"

    login      = github_user.get("login", f"github_{github_id}")
    avatar_url = github_user.get("avatar_url", "")

    # ── 4. 查找或创建用户 ─────────────────────────────────────────────────
    user = db.query(User).filter(User.email == email).first()
    if not user:
        random_pwd = secrets.token_urlsafe(24)
        user = User(
            email           = email,
            username        = login,
            hashed_password = hash_password(random_pwd),
            email_verified  = 1,
            login_type      = "github",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("[GitHub] 新用户注册 | id=%d login=%s email=%s", user.id, login, email)
    else:
        # 更新用户名（如果还是默认值）
        if user.username == email.split("@")[0] and login:
            user.username       = login
            user.email_verified = 1
        db.commit()
        logger.info("[GitHub] 老用户登录 | id=%d email=%s", user.id, email)

    # ── 5. 设置登录 Cookie ────────────────────────────────────────────────
    token = create_token(user.id)
    if response:
        # 注意：GitHub OAuth 回调是跨站跳转，SameSite=Lax 在顶级导航下是允许 Set-Cookie 的
        response.set_cookie(value=token, **_set_cookie_options())

    # ── 6. 返回兼容 HTML（桌面弹窗 + 手机整页跳转）──────────────────────
    return HTMLResponse(
        content=_github_success_html(frontend_url),
        headers={
            # 同样在 header 里设置 cookie，确保在 HTML 响应里也能生效
            "Set-Cookie": (
                f"access_token={token}; "
                f"Path=/; "
                f"Max-Age={7 * 24 * 3600}; "
                f"HttpOnly; "
                f"SameSite=Lax"
                + ("; Secure" if settings.COOKIE_SECURE else "")
            ),
        },
    )


# ── 辅助：生成回调 HTML ───────────────────────────────────────────────────────

def _github_success_html(frontend_url: str) -> str:
    """
    GitHub 登录成功后的过渡页 HTML。
    兼容两种场景：
    - 桌面弹窗：window.opener.postMessage → 主页面收到消息后刷新用户态 → 弹窗关闭
    - 手机/无弹窗：直接跳转到首页并附带 ?github_login=1 → 主页面检测参数后刷新用户态
    """
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>登录成功 · 媛心烨语</title>
  <style>
    body {{
      margin: 0; display: flex; align-items: center; justify-content: center;
      min-height: 100vh; background: linear-gradient(135deg,#667eea,#764ba2);
      font-family: 'Microsoft YaHei', sans-serif;
    }}
    .card {{
      background: rgba(255,255,255,.92); border-radius: 16px; padding: 40px 48px;
      text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,.15);
    }}
    .icon {{ font-size: 48px; margin-bottom: 12px; }}
    .title {{ font-size: 20px; font-weight: 700; color: #4a3f6b; margin-bottom: 8px; }}
    .sub {{ font-size: 14px; color: #888; }}
    .bar {{ width: 60px; height: 4px; background: linear-gradient(90deg,#667eea,#764ba2);
             border-radius: 2px; margin: 20px auto 0; animation: grow 1s ease-in-out; }}
    @keyframes grow {{ from {{ width: 0 }} to {{ width: 60px }} }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <div class="title">GitHub 登录成功</div>
    <div class="sub">正在跳转，请稍候...</div>
    <div class="bar"></div>
  </div>
  <script>
  (function() {{
    var ORIGIN = '{frontend_url}';

    function notifyAndClose() {{
      try {{
        if (window.opener && !window.opener.closed) {{
          // 桌面弹窗模式：通知主页面
          window.opener.postMessage({{ type: 'github_login_success' }}, ORIGIN);
          setTimeout(function() {{ window.close(); }}, 800);
          return;
        }}
      }} catch(e) {{ /* 跨域阻止时忽略 */ }}

      // 手机 / 无 opener 模式：直接跳回主页，附带标记让主页刷新登录态
      window.location.replace(ORIGIN + '/?github_login=1&_t=' + Date.now());
    }}

    // 稍作延迟，确保 cookie 已写入
    setTimeout(notifyAndClose, 300);
  }})();
  </script>
</body>
</html>"""


def _github_error_html(frontend_url: str, msg: str) -> HTMLResponse:
    """GitHub 授权失败时显示错误并跳回首页。"""
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"><title>登录失败</title>
  <style>
    body {{ margin:0; display:flex; align-items:center; justify-content:center;
           min-height:100vh; background:#f5f5f5; font-family:sans-serif; }}
    .card {{ background:#fff; border-radius:12px; padding:32px 40px; text-align:center;
             box-shadow:0 4px 16px rgba(0,0,0,.1); }}
    .icon {{ font-size:40px; margin-bottom:12px; }}
    .msg {{ color:#d32f2f; margin-bottom:20px; }}
    a {{ color:#764ba2; text-decoration:none; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">❌</div>
    <div class="msg">{msg}</div>
    <a href="{frontend_url}">← 返回首页</a>
  </div>
  <script>setTimeout(function(){{ window.location.replace('{frontend_url}'); }}, 3000);</script>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)
