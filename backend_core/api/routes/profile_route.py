"""api/routes/profile_route.py
用户心理画像查询接口（v2.7 新增）

接口：
  GET  /profile          获取当前用户画像（ENABLE_USER_PROFILE=true 时有数据）
  DELETE /profile/reset  重置画像（隐私保护）
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.settings import settings
from models.database import get_db
from models.user import User
from utils.auth import get_current_user
from utils.response import error_response, success_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/profile", summary="获取当前用户心理画像")
async def get_profile(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    返回当前用户的心理画像数据。
    ENABLE_USER_PROFILE=false 时返回空画像（不报错）。
    """
    if not settings.ENABLE_USER_PROFILE:
        return success_response(
            data={
                "enabled": False,
                "msg": "用户画像功能未启用",
                "stressors": [],
                "recent_state": "",
                "interests": [],
                "response_hints": "",
                "avg_score": 5.0,
                "recent_crisis_count": 0,
            }
        )

    try:
        from service.profile_service import load_profile  # noqa: PLC0415
        profile = load_profile(current_user.id)
        return success_response(data={
            "enabled": True,
            "user_id": current_user.id,
            **profile,
        })
    except Exception as exc:
        logger.warning("[profile_route] 读取画像失败 | user_id=%d err=%s",
                       current_user.id, exc)
        return success_response(data={
            "enabled": True,
            "user_id": current_user.id,
            "stressors": [],
            "recent_state": "",
            "interests": [],
            "response_hints": "",
            "avg_score": 5.0,
            "recent_crisis_count": 0,
            "_error": "画像加载失败，显示默认值",
        })


@router.delete("/profile/reset", summary="重置用户心理画像（隐私保护）")
async def reset_profile(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    一键清空用户画像数据（不删除情绪记录）。
    符合隐私保护要求。
    """
    if not settings.ENABLE_USER_PROFILE:
        return success_response(data={"cleared": False, "msg": "用户画像功能未启用"})

    try:
        from models.user_profile import UserProfile  # noqa: PLC0415

        profile = db.query(UserProfile).filter(
            UserProfile.user_id == current_user.id
        ).first()

        if profile:
            profile.main_stressors      = "[]"
            profile.recent_state        = ""
            profile.interests           = "[]"
            profile.response_hints      = ""
            profile.avg_score           = 5.0
            profile.recent_crisis_count = 0
            profile.deep_profile_json = "{}"
            db.commit()
            logger.info("[profile_route] 画像已重置 | user_id=%d", current_user.id)
            return success_response(data={"cleared": True, "user_id": current_user.id})
        else:
            return success_response(data={"cleared": False, "msg": "画像记录不存在"})

    except Exception as exc:
        logger.warning("[profile_route] 画像重置失败 | user_id=%d err=%s",
                       current_user.id, exc)
        db.rollback()
        return error_response(code=500, msg="画像重置失败，请稍后重试")