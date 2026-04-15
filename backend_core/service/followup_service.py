"""service/followup_service.py
72 小时危机随访任务服务（v2.7 新增）

Phase 1：只做任务创建 + 数据库落库，不发真实通知
Phase 2：扫表发送邮件（后续迭代接入，此文件预留 send_followup_notification 空函数）

触发条件（全部满足）：
  - ENABLE_FOLLOWUP_TASK=true
  - user_id 非 None（登录用户）
  - risk_level in ("high", "urgent")
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from service.email_service import send_verification_email, smtp_is_configured

logger = logging.getLogger(__name__)

# ── 建表（幂等，首次调用时自动创建）─────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS followup_tasks (
    id              INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id         INTEGER NOT NULL,
    risk_level      VARCHAR(20) NOT NULL,
    trigger_text    TEXT,
    emotion_score   FLOAT,
    scheduled_at    DATETIME NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    notified_at     DATETIME,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_followup_user (user_id),
    INDEX ix_followup_status (status, scheduled_at)
)
"""

# SQLite 版本（AUTO_INCREMENT → AUTOINCREMENT，去掉 INDEX 行内定义）
_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS followup_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    risk_level      VARCHAR(20) NOT NULL,
    trigger_text    TEXT,
    emotion_score   REAL,
    scheduled_at    DATETIME NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    notified_at     DATETIME,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_table_ready: bool = False


def _ensure_table() -> bool:
    try:
        from models.database import engine  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415

        is_sqlite = "sqlite" in str(engine.url)
        ddl = _DDL_SQLITE if is_sqlite else _DDL

        with engine.connect() as conn:
            conn.execute(text(ddl))
            if not is_sqlite:
                # MySQL: 单独创建索引（幂等）
                for idx_sql in [
                    "CREATE INDEX IF NOT EXISTS ix_followup_user ON followup_tasks(user_id)",
                    "CREATE INDEX IF NOT EXISTS ix_followup_status ON followup_tasks(status, scheduled_at)",
                ]:
                    try:
                        conn.execute(text(idx_sql))
                    except Exception:
                        pass  # 索引已存在时 MySQL 会报错，忽略
            conn.commit()
        logger.info("[followup] followup_tasks 表已就绪")
        return True
    except Exception as exc:
        logger.warning("[followup] 建表失败（已忽略）: %s", exc)
        return False


# ── 核心：创建随访任务 ────────────────────────────────────────────────────────

def schedule_followup(
    user_id:      Optional[int],
    risk_level:   str,
    result:       Dict[str, Any],
    trigger_text: str = "",
) -> None:
    """
    创建 72h 危机随访任务记录。
    调用方式（fire-and-forget）：
        import asyncio
        asyncio.create_task(asyncio.to_thread(
            schedule_followup, user_id, risk_level, result, payload.text
        ))
    """
    global _table_ready

    try:
        from config.settings import settings  # noqa: PLC0415

        # ── 前置条件检查 ──────────────────────────────────────────────────
        if not settings.ENABLE_FOLLOWUP_TASK:
            return
        if not user_id:
            return
        if risk_level not in ("high", "urgent"):
            return

        # ── 确保表存在 ────────────────────────────────────────────────────
        if not _table_ready:
            _table_ready = _ensure_table()
        if not _table_ready:
            return

        from models.database import SessionLocal  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415

        emotion_score = float(result.get("sentiment_score") or 5.0)
        scheduled_at  = datetime.utcnow() + timedelta(hours=72)

        db = SessionLocal()
        try:
            # 幂等：同一用户同一天的 urgent 不重复创建（避免刷屏）
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            existing = db.execute(
                text(
                    "SELECT COUNT(*) FROM followup_tasks "
                    "WHERE user_id=:uid AND risk_level=:risk AND created_at>=:today"
                ),
                {"uid": user_id, "risk": risk_level, "today": today_start},
            ).scalar()

            if existing and existing >= 3:
                # 每天最多创建 3 条，防止高频刷入
                logger.debug("[followup] 今日随访任务已达上限 | user_id=%d risk=%s",
                             user_id, risk_level)
                return

            db.execute(
                text(
                    "INSERT INTO followup_tasks "
                    "(user_id, risk_level, trigger_text, emotion_score, scheduled_at, status) "
                    "VALUES (:uid, :risk, :text, :score, :sched, 'pending')"
                ),
                {
                    "uid":   user_id,
                    "risk":  risk_level,
                    "text":  (trigger_text or "")[:500],
                    "score": emotion_score,
                    "sched": scheduled_at,
                },
            )
            db.commit()
            logger.info(
                "[followup] 随访任务已创建 | user_id=%d risk=%s score=%.1f scheduled=%s",
                user_id, risk_level, emotion_score,
                scheduled_at.strftime("%Y-%m-%d %H:%M"),
            )
        finally:
            db.close()

    except Exception as exc:
        logger.warning("[followup] schedule_followup 失败（已忽略）| user_id=%s err=%s",
                       user_id, exc)


# ── Phase 2 预留：通知发送（当前为 noop）────────────────────────────────────

def send_followup_notification(task_id: int) -> bool:
    """
    Phase 2：读取 task_id 对应记录，向用户发送随访邮件。
    返回 True=成功，False=跳过/失败。
    """
    try:
        from config.settings import settings  # noqa: PLC0415
        if not settings.ENABLE_FOLLOWUP_TASK:
            return False

        from models.database import SessionLocal  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415
        from email.mime.text import MIMEText  # noqa: PLC0415
        from email.mime.multipart import MIMEMultipart  # noqa: PLC0415
        from email.header import Header  # noqa: PLC0415
        from email.utils import formataddr  # noqa: PLC0415
        import smtplib  # noqa: PLC0415

        db = SessionLocal()
        try:
            task = db.execute(
                text(
                    "SELECT ft.id, ft.user_id, ft.risk_level, ft.trigger_text, ft.emotion_score, "
                    "u.email, u.username "
                    "FROM followup_tasks ft "
                    "JOIN users u ON ft.user_id = u.id "
                    "WHERE ft.id=:tid AND ft.status='pending'"
                ),
                {"tid": task_id},
            ).mappings().first()

            if not task:
                logger.debug("[followup] 任务不存在或已处理 | task_id=%d", task_id)
                return False

            if not task["email"]:
                logger.warning("[followup] 用户无邮箱，跳过随访 | task_id=%d", task_id)
                return False

            if not smtp_is_configured():
                logger.warning("[followup] SMTP 未配置，跳过邮件发送 | task_id=%d", task_id)
                return False

            subject = "【媛心烨语】想起了你，来看看你现在还好吗"
            body = f"""
你好，{task["username"] or "朋友"}：

这是来自媛心烨语的一封随访邮件。
之前你提到过：

“{(task["trigger_text"] or "")[:120]}”

我想轻轻问一句，你现在还好吗？

如果你依然觉得很难受，请不要独自承受：
- 全国心理援助热线：400-161-9995
- 或联系你信任的人 / 学校心理中心

这封邮件只是一个温柔提醒，不需要立刻回复。
希望你正在慢慢好一点。

—— 媛心烨语
""".strip()

            msg = MIMEMultipart()
            msg["Subject"] = Header(subject, "utf-8")
            msg["From"] = formataddr((str(Header(settings.SMTP_FROM_NAME or "媛心烨语", "utf-8")), settings.SMTP_FROM_EMAIL or settings.SMTP_USER))
            msg["To"] = task["email"]
            msg.attach(MIMEText(body, "plain", "utf-8"))

            if settings.SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
                server.starttls()

            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL or settings.SMTP_USER, [task["email"]], msg.as_string())
            server.quit()

            db.execute(
                text(
                    "UPDATE followup_tasks "
                    "SET status='sent', notified_at=:now "
                    "WHERE id=:tid"
                ),
                {"tid": task_id, "now": datetime.utcnow()},
            )
            db.commit()

            logger.info("[followup] 随访邮件发送成功 | task_id=%d user_id=%d", task_id, task["user_id"])
            return True

        finally:
            db.close()

    except Exception as exc:
        logger.warning("[followup] send_followup_notification 失败 | task_id=%s err=%s", task_id, exc)
        return False

def run_due_followups(limit: int = 20) -> int:
    """
    扫描到期 pending 任务并尝试发送邮件。
    返回成功处理数量。
    可由 cron / 手工命令 / 后续 APScheduler 调用。
    """
    try:
        from models.database import SessionLocal  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415

        db = SessionLocal()
        try:
            # ✅ 先不用 LIMIT 参数化，避免 MySQL / SQLAlchemy 兼容问题
            sql = (
                "SELECT id, scheduled_at, status "
                "FROM followup_tasks "
                "WHERE status='pending' AND scheduled_at <= :now "
                "ORDER BY scheduled_at ASC "
                f"LIMIT {int(limit)}"
            )
            rows = db.execute(
                text(sql),
                {"now": datetime.utcnow()},
            ).fetchall()

            logger.info("[followup] 到期待发送任务数=%d", len(rows))
        finally:
            db.close()

        success = 0
        for row in rows:
            task_id = row[0]
            logger.info("[followup] 尝试发送 task_id=%d", task_id)
            if send_followup_notification(task_id):
                success += 1

        logger.info("[followup] 本轮成功发送 %d 封随访邮件", success)
        return success

    except Exception as exc:
        logger.warning("[followup] run_due_followups 失败: %s", exc)
        return 0