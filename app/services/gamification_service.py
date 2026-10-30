"""
app/services/gamification_service.py - 游戏化业务逻辑层

依据：切片 09-gamification/backend.md 3-5
功能：积分系统 + 打卡日历 + 徽章系统
积分规则：analysis 10, match 5, record 3, checkin 2, streak_7 20, streak_30 100, training_session 5
"""

import logging
from datetime import date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def _cst_today() -> date:
    """获取 CST（UTC+8）当前日期，避免跨日打卡边界错误"""
    return datetime.now(CST).date()
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.gamification import (
    BadgeDefinition,
    BadgeProgress,
    CheckInRecord,
    UserBadge,
    UserPoints,
)

logger = logging.getLogger(__name__)

POINTS_RULES = {
    "analysis": 10,
    "match": 5,
    "record": 3,
    "checkin": 2,
    "streak_7": 20,
    "streak_30": 100,
    "training_session": 5,
    "share": 2,
    "feedback": 1,
}

BADGE_SEEDS = [
    {"id": "first_analysis", "name": "首分析", "icon": "📹", "category": "analysis",
     "condition": {"metric": "analysis_count", "operator": ">=", "threshold": 1}, "points_reward": 10},
    {"id": "first_match", "name": "首场比赛", "icon": "🏓", "category": "match",
     "condition": {"metric": "match_count", "operator": ">=", "threshold": 1}, "points_reward": 10},
    {"id": "streak_7", "name": "连续7天", "icon": "🔥", "category": "streak",
     "condition": {"metric": "streak_days", "operator": ">=", "threshold": 7}, "points_reward": 20},
    {"id": "streak_30", "name": "连续30天", "icon": "🌟", "category": "streak",
     "condition": {"metric": "streak_days", "operator": ">=", "threshold": 30}, "points_reward": 100},
    {"id": "analysis_10", "name": "分析10次", "icon": "📊", "category": "analysis",
     "condition": {"metric": "analysis_count", "operator": ">=", "threshold": 10}, "points_reward": 30},
    {"id": "match_50", "name": "百场对决", "icon": "🏆", "category": "match",
     "condition": {"metric": "match_count", "operator": ">=", "threshold": 50}, "points_reward": 50},
]


class GamificationService:
    """游戏化业务逻辑层"""

    @staticmethod
    async def _get_streak(user_id: int, db_streak: int = 0) -> int:
        """连续打卡天数 — Redis 实时值优先，DB 回退（R12-Gam-3 统一数据源）

        Redis key 由 _update_streak 写入：gamification:streak:user:{user_id}
        （R6-Gami-4）get_points 与 get_checkin_calendar 共用，日历不再只读 DB。
        """
        try:
            redis = await get_redis()
            redis_streak = await redis.get(f"gamification:streak:user:{user_id}")
            if redis_streak is not None:
                return int(redis_streak)
        except Exception as e:
            logger.debug("get_streak_redis_fallback", extra={"error": str(e)})
        return db_streak

    @staticmethod
    async def get_points(db: AsyncSession, user_id: int) -> dict:
        up = await db.scalar(select(UserPoints).where(UserPoints.user_id == user_id))
        if not up:
            return {"total_points": 0, "monthly_points": 0, "current_streak": 0, "streak_icon": ""}
        streak = await GamificationService._get_streak(user_id, db_streak=up.current_streak)

        # R12-Gam-2: streak icon 按设计阈值 3（原 7/30 双档与设计不符，STREAK_ICONS 死常量移除）
        icon = "🔥" if streak >= 3 else ""
        return {
            "total_points": up.total_points,
            "monthly_points": up.monthly_points,
            "current_streak": streak,
            "streak_icon": icon,
        }

    @staticmethod
    async def get_checkin_calendar(
        db: AsyncSession, user_id: int, year: int, month: int
    ) -> dict:
        import calendar as cal
        _, last_day = cal.monthrange(year, month)
        records = await db.execute(
            select(CheckInRecord).where(
                and_(
                    CheckInRecord.user_id == user_id,
                    func.extract("year", CheckInRecord.checkin_date) == year,
                    func.extract("month", CheckInRecord.checkin_date) == month,
                )
            )
        )
        checkin_map = {r.checkin_date: r for r in records.scalars().all()}

        days = []
        for d in range(1, last_day + 1):
            dt = date(year, month, d)
            rec = checkin_map.get(dt)
            days.append({
                "date": dt.isoformat(),
                "checked_in": rec is not None,
                "type": rec.checkin_type if rec else None,
            })

        up = await db.scalar(select(UserPoints).where(UserPoints.user_id == user_id))
        # R12-Gam-3: 日历 streak 改用 _get_streak（Redis 实时值优先，与 get_points 一致）
        db_streak = up.current_streak if up else 0
        streak = await GamificationService._get_streak(user_id, db_streak=db_streak)

        return {
            "year": year,
            "month": month,
            "days": days,
            "monthly_checkin_count": len(checkin_map),
            "streak_days": streak,
        }

    @staticmethod
    async def checkin(db: AsyncSession, user_id: int) -> dict:
        today = _cst_today()
        existing = await db.scalar(
            select(CheckInRecord).where(
                and_(CheckInRecord.user_id == user_id, CheckInRecord.checkin_date == today)
            )
        )
        if existing:
            raise AppException("今日已打卡", 409, code=40901)

        streak = await GamificationService._update_streak(user_id)
        # 连续打卡奖励（使用配置常量，非硬编码）
        streak_bonus_map = {7: POINTS_RULES["streak_7"], 30: POINTS_RULES["streak_30"]}
        bonus = streak_bonus_map.get(streak, 0)
        points = POINTS_RULES["checkin"] + bonus

        record = CheckInRecord(
            user_id=user_id,
            checkin_date=today,
            checkin_type="manual",
            points_earned=POINTS_RULES["checkin"],
            bonus_points=bonus,
        )
        db.add(record)
        await GamificationService._add_points(db, user_id, "checkin", points, None)

        await GamificationService._auto_update_streak(db, user_id, streak)

        await db.flush()

        try:
            await BadgeService.check_badges(db, user_id)
        except Exception as e:
            logger.warning("badge_check_after_checkin_failed", extra={"error": str(e)})

        # R6-Gami-2: 设计要求 bonus 在无奖励时返回 null（而非 0）
        return {
            "points_earned": POINTS_RULES["checkin"],
            "current_streak": streak,
            "bonus": bonus if bonus > 0 else None,
        }

    @staticmethod
    async def add_points(
        db: AsyncSession, user_id: int, event_type: str, ref_id: Optional[int] = None
    ) -> int:
        """公开 API - 供其他模块调用，try/except 不阻塞

        R13-Gam-N1: DB 写入段用 SAVEPOINT（begin_nested）隔离 — 原实现
        except 仅记日志 + return 0，若 _add_points/_auto_checkin 的 flush 抛
        IntegrityError（如并发首次创建 UserPoints 行触发 unique 冲突），
        session 进入 invalid 状态，调用方（video_analysis/scoring/match_data
        完成链路）后续 commit 将抛 PendingRollbackError → 业务接口 500。
        SAVEPOINT 回滚仅撤销本段写入，调用方事务不受污染（"积分失败不
        阻塞业务"设计意图），与 check_badges 的 R6-Gami-1 模式一致。
        """
        points = POINTS_RULES.get(event_type, 0)
        if points <= 0:
            return 0
        try:
            async with db.begin_nested():
                await GamificationService._add_points(
                    db, user_id, event_type, points, ref_id
                )

                # 自动打卡（analysis/match/record 事件触发）
                if event_type in ("analysis", "match", "record"):
                    await GamificationService._auto_checkin(db, user_id, event_type)

                await db.flush()
        except Exception as e:
            logger.warning("add_points_failed", extra={"user_id": user_id, "event": event_type, "error": str(e)})
            return 0

        try:
            await BadgeService.check_badges(db, user_id)
        except Exception as e:
            logger.warning("badge_check_failed", extra={"error": str(e)})

        return points

    @staticmethod
    async def grant_badge_points(
        db: AsyncSession, user_id: int, points: int, badge_id: str
    ) -> None:
        """徽章解锁奖励积分 - 不触发 check_badges 避免递归"""
        try:
            await GamificationService._add_points(db, user_id, "badge", points, None)
            await db.flush()
        except Exception as e:
            logger.warning("grant_badge_points_failed", extra={"error": str(e)})

    @staticmethod
    async def _add_points(
        db: AsyncSession, user_id: int, event_type: str, points: int, ref_id: Optional[int]
    ) -> None:
        up = await db.scalar(select(UserPoints).where(UserPoints.user_id == user_id))
        if not up:
            up = UserPoints(user_id=user_id, total_points=0, monthly_points=0, bonus_points=0)
            db.add(up)
            await db.flush()
        up.total_points += points
        up.monthly_points += points

    @staticmethod
    async def _auto_checkin(db: AsyncSession, user_id: int, source: str) -> None:
        """自动签到 — 分析/比赛/记录事件触发，逻辑与手动签到一致"""
        today = _cst_today()
        existing = await db.scalar(
            select(CheckInRecord).where(
                and_(CheckInRecord.user_id == user_id, CheckInRecord.checkin_date == today)
            )
        )
        if existing:
            return

        # 更新连续签到天数（Redis）
        streak = await GamificationService._update_streak(user_id)

        # 计算奖励（使用配置常量，非硬编码）
        streak_bonus_map = {7: POINTS_RULES["streak_7"], 30: POINTS_RULES["streak_30"]}
        bonus = streak_bonus_map.get(streak, 0)
        points = POINTS_RULES["checkin"] + bonus

        # 插入签到记录
        record = CheckInRecord(
            user_id=user_id,
            checkin_date=today,
            checkin_type=source,
            points_earned=POINTS_RULES["checkin"],
            bonus_points=bonus,
        )
        db.add(record)
        await GamificationService._add_points(db, user_id, "checkin", points, None)

        # 持久化连续签到天数
        await GamificationService._auto_update_streak(db, user_id, streak)

        # R2-Gam-3: 不在此处调用 check_badges，避免与 add_points 中的调用重复执行

    @staticmethod
    async def _update_streak(user_id: int) -> int:
        redis = await get_redis()
        streak_key = f"gamification:streak:user:{user_id}"
        last_key = f"gamification:streak:last_date:{user_id}"
        last_date_str = await redis.get(last_key)
        today = _cst_today()

        if last_date_str:
            last_date = date.fromisoformat(last_date_str)
            gap = (today - last_date).days
            if gap == 1:
                streak = await redis.incr(streak_key)
            elif gap == 0:
                streak = int(await redis.get(streak_key) or 0)
            else:
                await redis.set(streak_key, 1)
                streak = 1
        else:
            await redis.set(streak_key, 1)
            streak = 1

        await redis.set(last_key, today.isoformat())
        return streak

    @staticmethod
    async def _auto_update_streak(db: AsyncSession, user_id: int, streak: int) -> None:
        up = await db.scalar(select(UserPoints).where(UserPoints.user_id == user_id))
        if not up:
            up = UserPoints(user_id=user_id)
            db.add(up)
            await db.flush()
        up.current_streak = streak
        up.last_checkin_date = _cst_today()


class BadgeService:
    """徽章服务"""

    @staticmethod
    async def get_badges(db: AsyncSession, user_id: int) -> dict:
        all_defs = await db.execute(
            select(BadgeDefinition)
            .where(BadgeDefinition.is_active == True)
            .order_by(BadgeDefinition.sort_order)
        )
        defs = all_defs.scalars().all()

        earned_rows = await db.execute(
            select(UserBadge).where(UserBadge.user_id == user_id)
        )
        earned_map = {r.badge_id: r for r in earned_rows.scalars().all()}

        progress_rows = await db.execute(
            select(BadgeProgress).where(BadgeProgress.user_id == user_id)
        )
        progress_map = {r.badge_id: r for r in progress_rows.scalars().all()}

        user_metrics = await BadgeService._get_user_metrics(db, user_id)

        earned = []
        locked = []
        for d in defs:
            if d.id in earned_map:
                earned.append({
                    "badge_id": d.id,
                    "name": d.name,
                    "icon": d.icon,
                    "earned_at": earned_map[d.id].earned_at.date().isoformat() if earned_map[d.id].earned_at else "",
                })
            else:
                cond = d.condition or {}
                current = BadgeService._evaluate_condition(cond, user_metrics)
                target = cond.get("threshold", 1)
                progress = min(100, int(current / target * 100)) if target > 0 else 0
                locked.append({
                    "badge_id": d.id,
                    "name": d.name,
                    "icon": d.icon,
                    "progress": current,
                    "target": target,
                })

        return {"earned": earned, "locked": locked}

    @staticmethod
    async def check_badges(db: AsyncSession, user_id: int) -> None:
        all_defs = await db.execute(
            select(BadgeDefinition).where(BadgeDefinition.is_active == True)
        )
        defs = all_defs.scalars().all()

        earned_rows = await db.execute(
            select(UserBadge).where(UserBadge.user_id == user_id)
        )
        earned_ids = {r.badge_id for r in earned_rows.scalars().all()}

        user_metrics = await BadgeService._get_user_metrics(db, user_id)

        # R6-Gami-1: 使用 SAVEPOINT (begin_nested) 隔离徽章解锁逻辑
        # 若 IntegrityError 发生（并发竞态导致重复解锁），仅 SAVEPOINT 回滚，
        # 调用方事务（打卡记录/积分/连续天数）得以保留，而非整体回滚。
        newly_unlocked = []
        try:
            async with db.begin_nested():
                for d in defs:
                    if d.id in earned_ids:
                        continue
                    cond = d.condition or {}
                    current = BadgeService._evaluate_condition(cond, user_metrics)
                    target = cond.get("threshold", 1)
                    if current >= target:
                        ub = UserBadge(user_id=user_id, badge_id=d.id)
                        db.add(ub)
                        if d.points_reward > 0:
                            # 直接调用 _add_points 而非 grant_badge_points，
                            # 避免其内部 try/except 吞掉 IntegrityError 导致
                            # SAVEPOINT 无法正确捕获；flush 统一在块末执行。
                            await GamificationService._add_points(
                                db, user_id, "badge", d.points_reward, None
                            )
                        newly_unlocked.append({
                            "badge_id": d.id,
                            "name": d.name,
                            "icon": d.icon,
                        })
                    else:
                        # Update progress
                        progress = min(100, int(current / target * 100)) if target > 0 else 0
                        existing_p = await db.scalar(
                            select(BadgeProgress).where(
                                and_(BadgeProgress.user_id == user_id, BadgeProgress.badge_id == d.id)
                            )
                        )
                        if existing_p:
                            existing_p.current_value = current
                            existing_p.progress_pct = progress
                        else:
                            bp = BadgeProgress(
                                user_id=user_id, badge_id=d.id,
                                current_value=current, target_value=target, progress_pct=progress,
                            )
                            db.add(bp)
                await db.flush()
        except IntegrityError:
            # 并发徽章解锁竞态：徽章已被另一请求解锁
            # SAVEPOINT 已回滚，调用方事务保留
            return

        if newly_unlocked:
            try:
                from app.services.notification_service import NotificationService
                await NotificationService.push_ws_message(user_id, "badge_unlocked", newly_unlocked)
            except Exception as e:
                logger.warning("badge_push_failed", extra={"error": str(e)})

    @staticmethod
    async def _get_user_metrics(db: AsyncSession, user_id: int) -> dict:
        # R12-Gam-4: 按设计以 CheckInRecord.checkin_type 为统计源 —
        # match_count 含 "record"（手动录入比赛记录），原 Match 表计数漏掉手动录入；
        # streak_days 与 get_points/_get_streak 统一（Redis 实时值优先）
        analysis_count = await db.scalar(
            select(func.count()).select_from(CheckInRecord).where(
                and_(
                    CheckInRecord.user_id == user_id,
                    CheckInRecord.checkin_type == "analysis",
                )
            )
        ) or 0

        match_count = await db.scalar(
            select(func.count()).select_from(CheckInRecord).where(
                and_(
                    CheckInRecord.user_id == user_id,
                    CheckInRecord.checkin_type.in_(["match", "record"]),
                )
            )
        ) or 0

        checkin_count = await db.scalar(
            select(func.count()).select_from(CheckInRecord).where(
                CheckInRecord.user_id == user_id
            )
        ) or 0

        up = await db.scalar(select(UserPoints).where(UserPoints.user_id == user_id))
        db_streak = up.current_streak if up else 0
        streak_days = await GamificationService._get_streak(user_id, db_streak=db_streak)

        return {
            "analysis_count": analysis_count,
            "match_count": match_count,
            "checkin_count": checkin_count,
            "streak_days": streak_days,
        }

    @staticmethod
    def _evaluate_condition(condition: dict, metrics: dict) -> int:
        metric = condition.get("metric", "")
        return int(metrics.get(metric, 0))

    @staticmethod
    async def seed_badge_definitions(db: AsyncSession) -> dict:
        """预置 6 个基础徽章定义（幂等 upsert）— R12-Gam-1

        依据：切片 09-gamification/backend.md「预置徽章数据（通过 Alembic data
        migration 或 seed 脚本）」。原 BADGE_SEEDS 零引用为死代码，生产
        badge_definition 恒空导致徽章功能不可用。

        幂等：已存在的徽章按 seed 更新定义字段并重置 is_active，不存在的插入；
        可重复执行（seed 脚本 scripts/seed_badges.py 或 Alembic data migration 调用）。
        只 flush 不 commit，由调用方控制事务。
        """
        inserted = updated = skipped = 0
        for sort_order, s in enumerate(BADGE_SEEDS):
            existing = await db.scalar(
                select(BadgeDefinition).where(BadgeDefinition.id == s["id"])
            )
            if existing is None:
                db.add(BadgeDefinition(
                    id=s["id"], name=s["name"], icon=s["icon"], category=s["category"],
                    condition=s["condition"], points_reward=s["points_reward"],
                    sort_order=sort_order, is_active=True,
                ))
                inserted += 1
            else:
                if (
                    existing.name != s["name"]
                    or existing.icon != s["icon"]
                    or existing.category != s["category"]
                    or existing.condition != s["condition"]
                    or existing.points_reward != s["points_reward"]
                    or existing.sort_order != sort_order
                    or existing.is_active is not True
                ):
                    existing.name = s["name"]
                    existing.icon = s["icon"]
                    existing.category = s["category"]
                    existing.condition = s["condition"]
                    existing.points_reward = s["points_reward"]
                    existing.sort_order = sort_order
                    existing.is_active = True
                    updated += 1
                else:
                    skipped += 1
        await db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": skipped}
