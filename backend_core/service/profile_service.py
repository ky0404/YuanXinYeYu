"""service/profile_service.py
用户心理画像服务（v2.6 新增）

设计原则：
  - ENABLE_USER_PROFILE=false 时所有函数立即返回空结果，零开销
  - 任何异常都被捕获并记录，不影响主流程
  - 游客（user_id=None）自动跳过，兼容未登录用户
  - 使用独立 SessionLocal，不依赖 FastAPI 依赖注入 Session
  - 仅 Phase 1 显式 summary：keywords 累积 + EMA 均分 + 危机计数
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── 空画像（降级返回值）─────────────────────────────────────────────────────

def _empty_profile() -> Dict[str, Any]:
    return {
        "stressors":           [],
        "recent_state":        "",
        "interests":           [],
        "response_hints":      "",
        "avg_score":           5.0,
        "recent_crisis_count": 0,
    }


# ── 读取画像 ─────────────────────────────────────────────────────────────────

def load_profile(user_id: Optional[int]) -> Dict[str, Any]:
    """
    读取用户画像。
    - user_id=None 或 ENABLE_USER_PROFILE=false → 立即返回空画像
    - 任何异常 → 记录日志，返回空画像
    """
    try:
        from config.settings import settings  # noqa: PLC0415
        if not settings.ENABLE_USER_PROFILE or user_id is None:
            return _empty_profile()

        from models.database import SessionLocal  # noqa: PLC0415
        from models.user_profile import UserProfile  # noqa: PLC0415

        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if not profile:
                return _empty_profile()
            return {
                "stressors":           _safe_json_loads(profile.main_stressors, []),
                "recent_state":        profile.recent_state or "",
                "interests":           _safe_json_loads(profile.interests, []),
                "response_hints":      profile.response_hints or "",
                "avg_score":           round(float(profile.avg_score or 5.0), 2),
                "recent_crisis_count": int(profile.recent_crisis_count or 0),
            }
        finally:
            db.close()

    except Exception as exc:
        logger.warning("[profile] load_profile 失败，返回空画像 | user_id=%s err=%s", user_id, exc)
        return _empty_profile()


# ── 异步更新画像（在主回复成功后调用，失败不影响用户）─────────────────────

def update_profile_from_result(
    user_id: Optional[int],
    result:  Dict[str, Any],
    text:    str = "",
) -> None:
    """
    基于最新对话结果更新用户画像（同步执行，建议在 asyncio.create_task 或线程中调用）。

    调用示例（emo_route.py 中，在 success_response 之前）：
        if current_user and settings.ENABLE_USER_PROFILE:
            asyncio.create_task(
                asyncio.to_thread(update_profile_from_result, user_id, result)
            )

    - user_id=None 或 ENABLE_USER_PROFILE=false → 立即跳过
    - 任何异常 → 记录日志并静默退出
    """
    try:
        from config.settings import settings  # noqa: PLC0415
        if not settings.ENABLE_USER_PROFILE or user_id is None:
            return

        from models.database import SessionLocal  # noqa: PLC0415
        from models.user_profile import UserProfile  # noqa: PLC0415

        keywords  = result.get("keywords", []) or []
        score     = float(result.get("sentiment_score") or 5.0)
        category  = int(result.get("sentiment_category") or 4)
        is_crisis = (category == 2 and score >= 7.0)

        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if not profile:
                profile = UserProfile(user_id=user_id)
                db.add(profile)

            # 1. 关键词累积（去重，最多保留 15 条）
            existing_stressors: list = _safe_json_loads(profile.main_stressors, [])
            merged = list(dict.fromkeys(existing_stressors + keywords))[:15]
            profile.main_stressors = json.dumps(merged, ensure_ascii=False)

            # 2. EMA 情绪均分（α=0.3，新数据权重 30%）
            old_avg = float(profile.avg_score or 5.0)
            profile.avg_score = round(0.3 * score + 0.7 * old_avg, 2)

            # 3. 危机计数（只增不减，便于后续随访判断）
            if is_crisis:
                profile.recent_crisis_count = int(profile.recent_crisis_count or 0) + 1

            db.commit()
            logger.debug(
                "[profile] 更新成功 | user_id=%d stressors=%d avg_score=%.1f crisis=%d",
                user_id, len(merged), profile.avg_score, profile.recent_crisis_count,
            )
        finally:
            db.close()

    except Exception as exc:
        logger.warning("[profile] update_profile_from_result 失败（已忽略）| user_id=%s err=%s", user_id, exc)


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _safe_json_loads(val: Optional[str], default: Any) -> Any:
    """安全解析 JSON，失败返回 default。"""
    if not val:
        return default
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default