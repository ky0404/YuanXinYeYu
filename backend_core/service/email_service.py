"""邮件发送服务
- 使用标准库 smtplib，不引入第三方依赖
- SMTP 未配置时所有函数安全降级，不崩溃
- 支持 QQ/网易/Gmail 等 SMTP 服务商
"""
from __future__ import annotations
from email.utils import formataddr

import logging
import random
import smtplib
import string
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# ── 延迟导入 settings，避免循环依赖 ─────────────────────────────────────────

def _get_settings():
    from config.settings import settings  # noqa: PLC0415
    return settings


# ── 公共工具 ──────────────────────────────────────────────────────────────────

def smtp_is_configured() -> bool:
    """返回 True 表示 SMTP 配置完整，可以发信。"""
    s = _get_settings()
    return bool(s.SMTP_HOST and s.SMTP_USER and s.SMTP_PASSWORD)


def generate_email_code(length: int = 6) -> str:
    """生成纯数字验证码。"""
    return "".join(random.choices(string.digits, k=length))


# ── 邮件模板 ──────────────────────────────────────────────────────────────────

def _build_email_html(title: str, code: str, expire_minutes: int, purpose_text: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: 'Microsoft YaHei', Arial, sans-serif; background:#f5f5f5; padding:30px;">
  <div style="max-width:480px; margin:0 auto; background:#fff; border-radius:12px;
              box-shadow:0 4px 20px rgba(0,0,0,.08); overflow:hidden;">
    <div style="background:linear-gradient(135deg,#667eea,#764ba2); padding:28px 32px;">
      <h1 style="color:#fff; margin:0; font-size:22px;">🌸 媛心烨语</h1>
      <p style="color:rgba(255,255,255,.85); margin:6px 0 0; font-size:14px;">{title}</p>
    </div>
    <div style="padding:32px;">
      <p style="color:#333; font-size:15px; margin:0 0 20px;">您正在{purpose_text}，验证码为：</p>
      <div style="background:#f0f4ff; border:2px dashed #764ba2; border-radius:8px;
                  text-align:center; padding:18px; margin:0 0 20px;">
        <span style="font-size:36px; font-weight:700; letter-spacing:10px;
                     color:#764ba2; font-family:monospace;">{code}</span>
      </div>
      <p style="color:#888; font-size:13px; margin:0;">
        ⏱ 验证码 <strong>{expire_minutes} 分钟</strong>内有效，请勿泄露给他人。<br>
        如非本人操作，请忽略此邮件。
      </p>
    </div>
    <div style="background:#fafafa; padding:16px 32px; border-top:1px solid #eee;">
      <p style="color:#bbb; font-size:12px; margin:0; text-align:center;">
        此邮件由系统自动发送，请勿直接回复 · 媛心烨语团队
      </p>
    </div>
  </div>
</body>
</html>
"""


_PURPOSE_SUBJECT = {
    "login":          "【媛心烨语】邮箱验证码",
    "reset_password": "【媛心烨语】重置密码验证码",
}

_PURPOSE_TEXT = {
    "login":          "登录 / 注册账号",
    "reset_password": "重置密码",
}


# ── 核心发信函数 ──────────────────────────────────────────────────────────────

def send_verification_email(to_email: str, code: str, purpose: str) -> bool:
    """
    发送验证码邮件。
    返回 True=成功，False=失败（调用方根据返回值决定是否返回错误给用户）。
    SMTP 未配置时直接返回 False，不抛异常。
    """
    if not smtp_is_configured():
        logger.warning("[email] SMTP 未配置，跳过发信 | to=%s purpose=%s code=%s",
                       to_email, purpose, code)
        return False

    s       = _get_settings()
    subject = _PURPOSE_SUBJECT.get(purpose, "【媛心烨语】验证码")
    p_text  = _PURPOSE_TEXT.get(purpose, "操作")
    html    = _build_email_html(subject, code, s.EMAIL_CODE_EXPIRE_MINUTES, p_text)
    from_name = s.SMTP_FROM_NAME or "媛心烨语"
    from_addr = s.SMTP_FROM_EMAIL or s.SMTP_USER

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = formataddr((str(Header(from_name, "utf-8")), from_addr))
    msg["To"]      = to_email

    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if s.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(s.SMTP_HOST, s.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=10)
            server.starttls()

        server.login(s.SMTP_USER, s.SMTP_PASSWORD)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        logger.info("[email] 发信成功 | to=%s purpose=%s", to_email, purpose)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("[email] SMTP 认证失败，请检查账号/授权码")
    except smtplib.SMTPException as exc:
        logger.error("[email] SMTP 发信异常: %s", exc)
    except Exception as exc:
        logger.error("[email] 发信未知异常: %s", exc)
    return False