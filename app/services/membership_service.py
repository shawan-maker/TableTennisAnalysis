"""
app/services/membership_service.py — 会员等级、权益、额度、到期检测

依据：切片 10-membership/backend.md §5
      模块详细设计 §2.10
"""

import json
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.membership import MembershipTierConfig, Subscription
from app.schemas.membership import (
    TierListResponse, TierBrief,
    CurrentMembershipResponse, QuotaResponse, MembershipCheckResult,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class MembershipService:
    """membership 业务逻辑层"""

    TIER_CACHE_KEY = "membership:tiers"
    TIER_CACHE_TTL = 3600  # 1 小时
    FREE_DAILY_LIMIT = 3
    GRACE_PERIOD_DAYS = 7
    EXPIRING_SOON_DAYS = 3

    # ===================== 公开方法（API 调用）=====================

    @staticmethod
    async def get_tiers(db: AsyncSession) -> TierListResponse:
        """查询会员等级权益对比（缓存1h）"""
        redis = await get_redis()
        cached = await redis.get(MembershipService.TIER_CACHE_KEY)
        if cached:
            data = json.loads(cached)
            return TierListResponse(**data)

        result = await db.execute(
            select(MembershipTierConfig)
            .where(MembershipTierConfig.is_active == True)  # noqa: E712
            .order_by(MembershipTierConfig.sort_order)
        )
        tiers = result.scalars().all()
        tier_list = [
            TierBrief(
                tier=t.tier, name=t.name,
                price_monthly_cents=t.price_monthly_cents or 0,
                price_quarterly_cents=t.price_quarterly_cents or 0,
                price_yearly_cents=t.price_yearly_cents or 0,
                benefits=t.benefits if isinstance(t.benefits, list) else list(t.benefits),
                quota_config=t.quota_config if isinstance(t.quota_config, dict) else dict(t.quota_config),
            )
            for t in tiers
        ]
        response = TierListResponse(tiers=tier_list)

        await redis.setex(
            MembershipService.TIER_CACHE_KEY,
            MembershipService.TIER_CACHE_TTL,
            response.model_dump_json(),
        )

        return response

    @staticmethod
    async def get_current_membership(db: AsyncSession, user_id: int) -> CurrentMembershipResponse:
        """查询当前会员状态"""
        subscription = await MembershipService._get_active_subscription(db, user_id)

        if subscription is None:
            return CurrentMembershipResponse(
                tier="free", status="none", days_remaining=0,
            )

        now = datetime.now(timezone.utc)

        # 实时兜底：到期但状态未更新
        if subscription.status == "active" and subscription.expire_at < now:
            await MembershipService._handle_expiry(db, subscription)
            await db.commit()

        if subscription.status == "active" and \
           subscription.expire_at < now + timedelta(days=MembershipService.EXPIRING_SOON_DAYS):
            subscription.status = "expiring_soon"
            await db.commit()

        days_remaining = max(0, (subscription.expire_at - now).days)

        return CurrentMembershipResponse(
            tier=subscription.tier,
            status=subscription.status,
            start_at=subscription.start_at.isoformat() if subscription.start_at else None,
            expire_at=subscription.expire_at.isoformat(),
            days_remaining=days_remaining,
            auto_renew=subscription.auto_renew,
        )

    @staticmethod
    async def get_quota(db: AsyncSession, user_id: int) -> QuotaResponse:
        """查询今日剩余免费分析次数"""
        membership = await MembershipService.get_current_membership(db, user_id)

        if membership.tier != "free":
            return QuotaResponse(
                tier=membership.tier,
                daily_limit=-1, used_today=0, remaining=-1, reset_at="",
            )

        today = MembershipService._get_today_cst()
        used_today = await MembershipService._get_used_count(user_id, today)
        remaining = max(0, MembershipService.FREE_DAILY_LIMIT - used_today)
        reset_at = MembershipService._get_reset_time(today)

        return QuotaResponse(
            tier="free",
            daily_limit=MembershipService.FREE_DAILY_LIMIT,
            used_today=used_today, remaining=remaining,
            reset_at=reset_at.isoformat(),
        )

    # ===================== 供其他模块调用 =====================

    @staticmethod
    async def check_membership(db: AsyncSession, user_id: int) -> MembershipCheckResult:
        """检查用户会员状态（供 video_analysis 等模块调用）"""
        subscription = await MembershipService._get_active_subscription(db, user_id)

        if subscription is None:
            today = MembershipService._get_today_cst()
            used_today = await MembershipService._get_used_count(user_id, today)
            remaining = max(0, MembershipService.FREE_DAILY_LIMIT - used_today)
            return MembershipCheckResult(
                tier="free", is_member=False, has_quota=remaining > 0,
                daily_limit=MembershipService.FREE_DAILY_LIMIT,
                used_today=used_today, remaining=remaining,
            )

        return MembershipCheckResult(
            tier=subscription.tier, is_member=True, has_quota=True,
            daily_limit=-1, used_today=0, remaining=-1,
        )

    @staticmethod
    async def consume_analysis_quota(user_id: int) -> bool:
        """消耗一次分析额度（Redis 原子操作）。会员直接返回 True。"""
        async with async_session_factory() as db:
            membership = await MembershipService.check_membership(db, user_id)

        if membership.is_member:
            return True

        if not membership.has_quota:
            return False

        today = MembershipService._get_today_cst()
        redis = await get_redis()
        key = f"quota:analysis:{user_id}:{today.isoformat()}"

        new_count = await redis.incr(key)

        if new_count == 1:
            ttl = MembershipService._seconds_until_reset(today)
            await redis.expire(key, ttl)

        if new_count > MembershipService.FREE_DAILY_LIMIT:
            await redis.decr(key)
            return False

        return True

    # ===================== 到期检测（Celery Beat 调用）=====================

    @staticmethod
    async def check_expiry(db: AsyncSession) -> None:
        """到期检测：Celery Beat 每日 00:30 执行。"""
        now = datetime.now(timezone.utc)

        # 1. 标记即将到期（3 天内）
        expiring_soon_threshold = now + timedelta(days=MembershipService.EXPIRING_SOON_DAYS)
        result = await db.execute(
            select(Subscription).where(and_(
                Subscription.status == "active",
                Subscription.expire_at < expiring_soon_threshold,
                Subscription.expire_at >= now,
            ))
        )
        for sub in result.scalars().all():
            sub.status = "expiring_soon"
            await MembershipService._send_expiry_notification(sub)

        # 2. 标记已到期
        result = await db.execute(
            select(Subscription).where(and_(
                Subscription.status.in_(["active", "expiring_soon"]),
                Subscription.expire_at < now,
            ))
        )
        for sub in result.scalars().all():
            sub.status = "expired"
            await MembershipService._handle_downgrade(db, sub)

        # 3. 标记已关闭（到期 7 天后）
        closed_threshold = now - timedelta(days=MembershipService.GRACE_PERIOD_DAYS)
        result = await db.execute(
            select(Subscription).where(and_(
                Subscription.status == "expired",
                Subscription.expire_at < closed_threshold,
            ))
        )
        for sub in result.scalars().all():
            sub.status = "closed"

        await db.commit()

    # ===================== 内部方法 =====================

    @staticmethod
    async def _get_active_subscription(
        db: AsyncSession, user_id: int,
    ) -> Optional[Subscription]:
        """获取用户当前有效订阅"""
        result = await db.execute(
            select(Subscription).where(and_(
                Subscription.user_id == user_id,
                Subscription.status.in_(["active", "expiring_soon", "expired", "grace_period"]),
            )).order_by(Subscription.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _get_today_cst() -> date:
        """获取中国标准时间今天的日期"""
        shanghai_tz = timezone(timedelta(hours=8))
        return datetime.now(shanghai_tz).date()

    @staticmethod
    async def _get_used_count(user_id: int, today: date) -> int:
        """从 Redis 获取今日已用分析次数"""
        redis = await get_redis()
        key = f"quota:analysis:{user_id}:{today.isoformat()}"
        count = await redis.get(key)
        return int(count) if count else 0

    @staticmethod
    def _get_reset_time(today: date) -> datetime:
        """获取额度重置时间（次日 00:00 CST）"""
        tomorrow = today + timedelta(days=1)
        shanghai_tz = timezone(timedelta(hours=8))
        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=shanghai_tz)

    @staticmethod
    def _seconds_until_reset(today: date) -> int:
        """计算到次日 00:00 的秒数（Redis TTL）"""
        reset_at = MembershipService._get_reset_time(today)
        now = datetime.now(reset_at.tzinfo)
        return int((reset_at - now).total_seconds()) + 3600

    @staticmethod
    async def _handle_expiry(db: AsyncSession, subscription: Subscription) -> None:
        """处理到期逻辑（实时兜底）"""
        subscription.status = "expired"
        await MembershipService._handle_downgrade(db, subscription)

    @staticmethod
    async def apply_downgrade_policy(db: AsyncSession, subscription: Subscription) -> None:
        """实现 BR-3 权益降级策略"""
        redis = await get_redis()
        user_id = subscription.user_id

        # 1. 历史报告只读
        await redis.set(
            f"downgrade:report:readonly:{user_id}",
            json.dumps({"readonly": True}),
        )

        # 2. 标注视频保留 30 天后清理
        await redis.setex(
            f"downgrade:video:cleanup:{user_id}",
            int(30 * 24 * 3600),
            json.dumps({"retain_days": 30}),
        )

        # 3-5. 3D 教学/进度分析/数据看板：前端根据 tier 判断

        # 推送降级事件
        try:
            await NotificationService.push_ws_message(user_id, "membership_downgrade", {
                "user_id": user_id,
                "old_tier": subscription.tier,
                "new_tier": "free",
            })
        except Exception as e:
            logger.warning("push downgrade ws failed: %s", e)

    @staticmethod
    async def _handle_downgrade(db: AsyncSession, subscription: Subscription) -> None:
        """权益降级处理"""
        await MembershipService.apply_downgrade_policy(db, subscription)

    @staticmethod
    async def revoke_subscription(db: AsyncSession, subscription_id: int) -> None:
        """退款后撤销会员权益"""
        result = await db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            return
        subscription.status = "closed"
        subscription.cancelled_at = datetime.now(timezone.utc)
        await db.flush()
        await MembershipService.apply_downgrade_policy(db, subscription)
        await db.commit()

    @staticmethod
    async def _send_expiry_notification(subscription: Subscription) -> None:
        """发送到期续费提醒"""
        days_remaining = max(0, (subscription.expire_at - datetime.now(timezone.utc)).days)
        try:
            await NotificationService.push_ws_message(subscription.user_id, "notification", {
                "type": "membership_expiring",
                "title": "会员即将到期",
                "content": f"您的{subscription.tier}会员将在{days_remaining}天后到期，请及时续费",
                "user_id": subscription.user_id,
            })
        except Exception as e:
            logger.warning("push expiry notification failed: %s", e)
