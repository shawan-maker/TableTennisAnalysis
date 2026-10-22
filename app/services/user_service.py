"""
app/services/user_service.py — 用户业务逻辑层

依据：切片 02-user/backend.md §5
规范：Service 方法使用 @staticmethod，禁止创建实例
S1 范围：get_profile / update_profile / get_quota / update_rating
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ERR_BAD_REQUEST
from app.core.redis import get_redis
from app.models.user import RatingHistory, User
from app.schemas.user import (
    ProfileResponse,
    QuotaResponse,
    RatingHistoryItem,
    UpdateProfileRequest,
    UpdateProfileResponse,
    UpdateRatingRequest,
    UpdateRatingResponse,
)

# 应填字段（用于计算档案完整度）
PROFILE_REQUIRED_FIELDS = [
    "nickname",
    "avatar_url",
    "kqs_rating",
    "playing_style",
    "equipment_config",
]

# 打法类型枚举
PLAYING_STYLES = {"loop", "fast_attack", "chop", "all_round"}

# 自评水平枚举
SELF_ASSESSED_LEVELS = {"beginner", "intermediate", "advanced"}


class UserService:
    """用户业务逻辑层"""

    DAILY_FREE_LIMIT = 3  # 免费分析额度：3 次/天

    @staticmethod
    def _calculate_completeness(user: User) -> int:
        """计算档案完整度 = 已填字段数 / 应填字段数 × 100%"""
        filled = sum(1 for f in PROFILE_REQUIRED_FIELDS if getattr(user, f, None) is not None)
        return int(filled / len(PROFILE_REQUIRED_FIELDS) * 100)

    # =================================================================
    # 个人档案
    # =================================================================

    @staticmethod
    async def get_profile(user: User, db: AsyncSession) -> ProfileResponse:
        """获取个人档案"""
        # 确保 profile_completeness 是最新计算的
        user.profile_completeness = UserService._calculate_completeness(user)

        return ProfileResponse.model_validate(user)

    @staticmethod
    async def update_profile(
        user: User, req: UpdateProfileRequest, db: AsyncSession
    ) -> UpdateProfileResponse:
        """更新个人档案（PATCH 语义，仅更新传入字段）"""
        updated_fields: list[str] = []

        if req.playing_style is not None:
            if req.playing_style not in PLAYING_STYLES:
                raise AppException(
                    f"打法类型不合法，可选值: {', '.join(PLAYING_STYLES)}",
                    422,
                )
            user.playing_style = req.playing_style
            updated_fields.append("playing_style")

        if req.self_assessed_level is not None:
            if req.self_assessed_level not in SELF_ASSESSED_LEVELS:
                raise AppException(
                    f"自评水平不合法，可选值: {', '.join(SELF_ASSESSED_LEVELS)}",
                    422,
                )
            user.self_assessed_level = req.self_assessed_level
            updated_fields.append("self_assessed_level")

        if req.equipment_config is not None:
            user.equipment_config = req.equipment_config
            updated_fields.append("equipment_config")

        if req.kqs_rating is not None:
            user.kqs_rating = req.kqs_rating
            updated_fields.append("kqs_rating")

        if req.kqs_username is not None:
            user.kqs_username = req.kqs_username
            updated_fields.append("kqs_username")

        if req.nickname is not None:
            user.nickname = req.nickname
            updated_fields.append("nickname")

        if req.avatar_url is not None:
            user.avatar_url = req.avatar_url
            updated_fields.append("avatar_url")

        await db.commit()
        await db.refresh(user)

        completeness = UserService._calculate_completeness(user)
        user.profile_completeness = completeness
        await db.commit()

        return UpdateProfileResponse(
            profile_completeness=completeness,
            updated_fields=updated_fields,
        )

    # =================================================================
    # 积分管理
    # =================================================================

    @staticmethod
    async def update_rating(
        user: User, req: UpdateRatingRequest, db: AsyncSession
    ) -> UpdateRatingResponse:
        """更新开球网积分，旧积分自动写入历史记录"""
        if req.rating < 500 or req.rating > 3000:
            raise AppException("积分值应在 500-3000 合理范围内", 400, code=ERR_BAD_REQUEST)

        old_rating = user.kqs_rating

        # 创建历史记录
        history_id = 0
        if old_rating is not None:
            history = RatingHistory(
                user_id=user.id,
                rating=old_rating,
                source=req.source,
            )
            db.add(history)
            await db.flush()
            history_id = history.id

        # 更新积分
        user.kqs_rating = req.rating
        await db.commit()
        await db.refresh(user)

        return UpdateRatingResponse(
            old_rating=old_rating,
            new_rating=req.rating,
            history_id=history_id,
        )

    @staticmethod
    async def get_rating_history(
        user: User, page: int, page_size: int, db: AsyncSession
    ) -> dict:
        """积分历史记录分页查询"""
        offset = (page - 1) * page_size

        # 查询总数
        count_stmt = select(func.count()).select_from(RatingHistory).where(
            RatingHistory.user_id == user.id
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        # 查询列表
        list_stmt = (
            select(RatingHistory)
            .where(RatingHistory.user_id == user.id)
            .order_by(RatingHistory.recorded_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await db.execute(list_stmt)).scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [RatingHistoryItem.model_validate(r).model_dump() for r in rows],
        }

    # =================================================================
    # 免费额度
    # =================================================================

    @staticmethod
    async def get_quota(user: User) -> QuotaResponse:
        """
        获取免费分析额度状态。

        Redis Key: quota:analysis:{user_id}:{date}
        TTL: 到当日 23:59:59 + 1 小时（Asia/Shanghai）
        """
        from datetime import date

        redis = await get_redis()
        today = date.today().isoformat()
        quota_key = f"quota:analysis:{user.id}:{today}"

        used_today = int(await redis.get(quota_key) or 0)
        remaining = max(0, UserService.DAILY_FREE_LIMIT - used_today)

        # 计算重置时间（次日 00:00 CST = UTC+8）
        now_cst = datetime.now(timezone.utc) + timedelta(hours=8)
        tomorrow = (now_cst + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        reset_at = tomorrow.isoformat()

        return QuotaResponse(
            daily_limit=UserService.DAILY_FREE_LIMIT,
            used_today=used_today,
            remaining=remaining,
            reset_at=reset_at,
        )
