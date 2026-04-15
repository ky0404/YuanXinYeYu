"""service/profile_service.py
用户心理画像服务（v3.0 深度画像最终版）
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)


def _empty_profile() -> Dict[str, Any]:
    return {
        "stressors": [],
        "recent_state": "",
        "interests": [],
        "response_hints": "",
        "avg_score": 5.0,
        "recent_crisis_count": 0,
        "deep_profile": {},
    }


def load_profile(user_id: Optional[int]) -> Dict[str, Any]:
    try:
        from config.settings import settings  # noqa: PLC0415
        if not settings.ENABLE_USER_PROFILE or user_id is None:
            return _empty_profile()

        from models.database import SessionLocal  # noqa: PLC0415
        from models.user_profile import UserProfile  # noqa: PLC0415
        from models.user import User

        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if not profile:
                return _empty_profile()

            deep_profile = _safe_json_loads(profile.deep_profile_json, {})

            return {
                "stressors":           _safe_json_loads(profile.main_stressors, []),
                "recent_state":        profile.recent_state or "",
                "interests":           _safe_json_loads(profile.interests, []),
                "response_hints":      profile.response_hints or "",
                "avg_score":           round(float(profile.avg_score or 5.0), 2),
                "recent_crisis_count": int(profile.recent_crisis_count or 0),
                "deep_profile":        deep_profile,
            }
        finally:
            db.close()

    except Exception as exc:
        logger.warning("[profile] load_profile 失败，返回空画像 | user_id=%s err=%s", user_id, exc)
        return _empty_profile()


def update_profile_from_result(
    user_id: Optional[int],
    result: Dict[str, Any],
    text: str = "",
) -> None:
    """
    轻量实时画像更新
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
        label     = str(result.get("sentiment_label") or "")
        is_crisis = (category == 2 and score >= 7.0)

        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if not profile:
                profile = UserProfile(user_id=user_id)
                db.add(profile)

            existing_stressors: list = _safe_json_loads(profile.main_stressors, [])
            merged = list(dict.fromkeys(existing_stressors + keywords))[:20]
            profile.main_stressors = json.dumps(merged, ensure_ascii=False)

            old_avg = float(profile.avg_score or 5.0)
            profile.avg_score = round(0.3 * score + 0.7 * old_avg, 2)

            if is_crisis:
                profile.recent_crisis_count = int(profile.recent_crisis_count or 0) + 1

            profile.recent_state = f"最近一次情绪：{label}（{score:.1f}/10）"

            existing_interests: list = _safe_json_loads(profile.interests, [])
            merged_interests = list(dict.fromkeys(existing_interests + keywords))[:20]
            profile.interests = json.dumps(merged_interests, ensure_ascii=False)

            db.commit()
            logger.debug(
                "[profile] 轻量画像更新成功 | user_id=%d stressors=%d avg_score=%.1f crisis=%d",
                user_id, len(merged), profile.avg_score, profile.recent_crisis_count,
            )
        finally:
            db.close()

    except Exception as exc:
        logger.warning("[profile] update_profile_from_result 失败（已忽略）| user_id=%s err=%s", user_id, exc)


def run_deep_profile_refresh(user_id: Optional[int], max_records: int = 50) -> None:
    """
    深度画像 Agent（最终 debug 版）：
    - 基于最近 max_records 条长期记录
    - 调大模型做推测型画像
    - 用原生 SQL 更新 user_profiles，避免 ORM 外键注册问题
    - 打全链路日志，便于你最终定位
    """
    try:
        from config.settings import settings  # noqa: PLC0415
        if not settings.ENABLE_USER_PROFILE or not settings.ENABLE_DEEP_PROFILE or user_id is None:
            logger.info(
                "[profile] 深度画像跳过 | user_id=%s enable_user_profile=%s enable_deep_profile=%s",
                user_id, settings.ENABLE_USER_PROFILE, settings.ENABLE_DEEP_PROFILE
            )
            return

        from models.database import SessionLocal  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415
        import requests  # noqa: PLC0415

        db = SessionLocal()
        try:
            # ── 1. 读取最近情绪记录（纯 SQL）────────────────────────────
            rows = db.execute(
                text(
                    """
                    SELECT emotion_label, emotion_score, memory_topic, keywords, created_at
                    FROM emotion_records
                    WHERE user_id = :uid
                    ORDER BY created_at DESC
                    LIMIT :lim
                    """
                ),
                {"uid": user_id, "lim": max_records},
            ).fetchall()

            logger.info("[profile] 深度画像读取样本 | user_id=%s rows=%d", user_id, len(rows))

            if len(rows) < 5:
                logger.info("[profile] 深度画像跳过 | user_id=%s 样本不足=%d", user_id, len(rows))
                return

            memory_samples = []
            for r in reversed(rows):
                emotion_label = r[0] or ""
                emotion_score = float(r[1] or 5.0)
                memory_topic = r[2] or ""
                keywords = r[3] or ""
                memory_samples.append(
                    f"情绪={emotion_label}|分数={emotion_score:.1f}|主题={memory_topic}|关键词={keywords}"
                )

            logger.info(
                "[profile] 深度画像构造样本成功 | user_id=%s sample_preview=%s",
                user_id,
                memory_samples[-1][:200] if memory_samples else "",
            )

            profile_prompt = f"""
你是一个“长期用户画像分析 Agent”。

任务：
根据用户长期对话与情绪样本，输出一份“推测型画像”。

注意：
1. 不允许医学诊断
2. 不允许绝对判断
3. 只能使用“可能 / 也许 / 倾向于 / 看起来”这类措辞
4. 重点分析：
   - interaction_style：交流风格
   - support_preference：支持偏好
   - likely_traits：可能的人格倾向（推测）
   - stress_triggers：常见压力触发点
   - effective_approach：更适合的回应方式
   - profile_summary：给系统内部使用的摘要
   - user_visible_insight：可以温和展示给用户的一句话，必须用推测语气

长期样本如下：
{chr(10).join(memory_samples)}

严格输出 JSON，不要解释：
{{
  "interaction_style": "...",
  "support_preference": "...",
  "likely_traits": ["...", "..."],
  "stress_triggers": ["...", "..."],
  "effective_approach": ["...", "..."],
  "profile_summary": "...",
  "user_visible_insight": "..."
}}
""".strip()

            payload = {
                "model": settings.HUAWEI_MODEL,
                "messages": [
                    {"role": "system", "content": "你是一个只输出 JSON 的长期画像分析器。"},
                    {"role": "user", "content": profile_prompt},
                ],
                "temperature": 0.2,
            }

            headers = {
                "Authorization": f"Bearer {settings.HUAWEI_API_KEY}",
                "Content-Type": "application/json",
            }

            logger.info("[profile] 深度画像开始调用模型 | user_id=%s", user_id)

            resp = requests.post(
                f"{settings.HUAWEI_API_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()

            logger.info("[profile] 深度画像模型调用成功 | user_id=%s", user_id)

            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "{}")
            )

            logger.info(
                "[profile] 深度画像原始输出 | user_id=%s content=%s",
                user_id,
                str(content)[:1000],
            )

            # 尝试清洗 markdown 代码块
            content = str(content).strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if len(lines) >= 3:
                    content = "\n".join(lines[1:-1]).strip()
                content = content.removeprefix("json").strip()

            deep_profile = _safe_json_loads(content, {})

            logger.info(
                "[profile] 深度画像解析结果 | user_id=%s is_dict=%s keys=%s",
                user_id,
                isinstance(deep_profile, dict),
                list(deep_profile.keys()) if isinstance(deep_profile, dict) else [],
            )

            if not isinstance(deep_profile, dict):
                logger.warning("[profile] 深度画像返回非 dict，已忽略 | user_id=%s", user_id)
                return

            if not deep_profile:
                logger.warning("[profile] 深度画像解析后为空 dict | user_id=%s", user_id)
                return

            deep_profile_json = json.dumps(deep_profile, ensure_ascii=False)
            response_hints = str(deep_profile.get("profile_summary", ""))[:500]

            logger.info(
                "[profile] 准备写入深度画像 | user_id=%s response_hints_len=%d dp_len=%d",
                user_id,
                len(response_hints or ""),
                len(deep_profile_json or ""),
            )

            db.execute(
                text(
                    """
                    UPDATE user_profiles
                    SET deep_profile_json = :dp,
                        response_hints = :rh,
                        updated_at = NOW()
                    WHERE user_id = :uid
                    """
                ),
                {
                    "dp": deep_profile_json,
                    "rh": response_hints,
                    "uid": user_id,
                },
            )
            db.commit()

            logger.info("[profile] 深度画像刷新成功 | user_id=%s sampled=%d", user_id, len(rows))

        finally:
            db.close()

    except Exception as exc:
        logger.warning("[profile] run_deep_profile_refresh 失败（已忽略）| user_id=%s err=%s", user_id, exc)


def _safe_json_loads(val: Optional[str], default: Any) -> Any:
    if not val:
        return default
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default
