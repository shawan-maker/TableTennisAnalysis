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
from app.models.user import ExportTask, RatingHistory, User
from app.schemas.user import (
    AccountDeletionRequest,
    AccountDeletionResponse,
    BigDataResponse,
    ExportCreateResponse,
    ExportStatusResponse,
    PaginatedRatingHistory,
    UserProfileResponse,
    QuotaResponse,
    RatingHistoryItem,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    RatingUpdateRequest,
    RatingUpdateResponse,
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
    DELETION_COOLDOWN_HOURS = 72  # 注销冷静期 72 小时
    BIG_DATA_CACHE_TTL = 86400  # 乒乓大数据缓存 24 小时
    EXPORT_LINK_TTL_DAYS = 7  # 导出链接 7 天有效
    EXPORT_MONTHLY_LIMIT = 1  # 每月限 1 次导出

    @staticmethod
    def _calculate_completeness(user: User) -> int:
        """计算档案完整度 = 已填字段数 / 应填字段数 × 100%"""
        filled = sum(1 for f in PROFILE_REQUIRED_FIELDS if getattr(user, f, None) is not None)
        return int(filled / len(PROFILE_REQUIRED_FIELDS) * 100)

    # =================================================================
    # 个人档案
    # =================================================================

    @staticmethod
    async def get_profile(user: User, db: AsyncSession) -> UserProfileResponse:
        """获取个人档案 — 返回嵌套结构"""
        user.profile_completeness = UserService._calculate_completeness(user)

        return UserProfileResponse(
            id=user.id,
            nickname=user.nickname,
            avatar_url=user.avatar_url,
            profile={
                "kqs_rating": user.kqs_rating,
                "kqs_username": user.kqs_username,
                "playing_style": user.playing_style,
                "self_assessed_level": user.self_assessed_level,
                "equipment_config": user.equipment_config,
                "profile_completeness": user.profile_completeness,
            },
        )

    @staticmethod
    async def update_profile(
        user: User, req: ProfileUpdateRequest, db: AsyncSession
    ) -> ProfileUpdateResponse:
        """更新个人档案（PATCH 语义，仅更新传入字段）"""
        updated_fields: list[str] = []

        if req.playing_style is not None:
            # R4-User-2: Schema 已通过 @field_validator 校验，service 层不再重复校验
            user.playing_style = req.playing_style
            updated_fields.append("playing_style")

        if req.self_assessed_level is not None:
            user.self_assessed_level = req.self_assessed_level
            updated_fields.append("self_assessed_level")

        if req.equipment_config is not None:
            user.equipment_config = req.equipment_config
            updated_fields.append("equipment_config")

        # R4-User-3: 不再处理 kqs_rating/kqs_username/nickname/avatar_url
        # 这些字段通过 /users/rating 或 /users/profile 单独端点更新

        await db.commit()
        await db.refresh(user)

        completeness = UserService._calculate_completeness(user)
        user.profile_completeness = completeness
        await db.commit()

        return ProfileUpdateResponse(
            id=user.id,
            profile_completeness=completeness,
            updated_fields=updated_fields,
        )

    # =================================================================
    # 积分管理
    # =================================================================

    @staticmethod
    async def update_rating(
        user: User, req: RatingUpdateRequest, db: AsyncSession
    ) -> RatingUpdateResponse:
        """更新开球网积分，旧积分自动写入历史记录"""
        # R12-User-3: 此分支为设计要求的唯一范围校验（API §3.3: 400 超范围），
        # Schema 已移除 ge/le 避免先行 422 拦截
        if req.rating < 500 or req.rating > 3000:
            raise AppException("积分值不在合理范围内（500-3000）", 400, code=ERR_BAD_REQUEST)

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
        if req.kqs_username:
            user.kqs_username = req.kqs_username
        await db.commit()
        await db.refresh(user)

        return RatingUpdateResponse(
            id=user.id,
            old_rating=old_rating,
            new_rating=req.rating,
            history_id=history_id,
        )

    # R4-User-7: get_rating_history 返回 PaginatedRatingHistory Schema 对象而非 dict
    @staticmethod
    async def get_rating_history(
        user: User, page: int, page_size: int, db: AsyncSession
    ) -> PaginatedRatingHistory:
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

        return PaginatedRatingHistory(
            total=total,
            page=page,
            page_size=page_size,
            items=[RatingHistoryItem.model_validate(r) for r in rows],
        )

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
        redis = await get_redis()
        # R5-User-1: today 改用 CST 日期，与 reset_at 时区一致
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date().strftime('%Y%m%d')
        quota_key = f"quota:analysis:{user.id}:{today}"

        used_today = int(await redis.get(quota_key) or 0)
        remaining = max(0, UserService.DAILY_FREE_LIMIT - used_today)

        # 计算重置时间（次日 00:00 CST = UTC+8）
        # R6-User-1: reset_at 显示值使用 CST 时区，而非 UTC 偏移
        cst_tz = timezone(timedelta(hours=8))
        now_cst = datetime.now(cst_tz)
        tomorrow = (now_cst + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        reset_at = tomorrow.isoformat()

        return QuotaResponse(
            daily_limit=UserService.DAILY_FREE_LIMIT,
            used_today=used_today,
            remaining=remaining,
            reset_at=reset_at,
        )

    # =================================================================
    # 乒乓大数据（趣味统计）
    # =================================================================

    @staticmethod
    async def get_big_data(user: User, db: AsyncSession) -> BigDataResponse:
        """乒乓大数据（间接胜利算法，24h 缓存）"""
        import json

        redis = await get_redis()
        cache_key = f"big_data:user:{user.id}"

        # 尝试读取缓存
        cached = await redis.get(cache_key)
        if cached:
            return BigDataResponse(**json.loads(cached))

        # 缓存未命中 → 实时计算
        from app.models.match import MatchRecord
        from sqlalchemy import cast, Integer

        # 统计总比赛数和胜率
        match_count_stmt = select(
            func.count().label("total"),
            func.sum(cast(MatchRecord.is_win, Integer)).label("wins"),
        ).where(MatchRecord.user_id == user.id)
        match_stats = (await db.execute(match_count_stmt)).one()
        total_matches = match_stats.total or 0
        wins = match_stats.wins or 0
        win_rate = wins / total_matches if total_matches > 0 else 0.0

        # 统计对手人数
        opp_stmt = select(func.count(func.distinct(MatchRecord.opponent_name))).where(
            MatchRecord.user_id == user.id
        )
        total_opponents = (await db.execute(opp_stmt)).scalar() or 0

        # 战胜的最高积分对手
        highest_stmt = select(func.max(MatchRecord.opponent_rating)).where(
            MatchRecord.user_id == user.id, MatchRecord.is_win.is_(True)
        )
        highest_win_rating = (await db.execute(highest_stmt)).scalar()

        # 连胜场次数
        recent_stmt = (
            select(MatchRecord.is_win)
            .where(MatchRecord.user_id == user.id)
            .order_by(MatchRecord.match_date.desc())
            .limit(100)
        )
        recent_results = [r[0] for r in (await db.execute(recent_stmt)).all()]
        win_streak = 0
        for r in recent_results:
            if r:
                win_streak += 1
            else:
                break

        # 间接胜利算法（BFS，最大 4 层）
        indirect_wins = await UserService._compute_indirect_wins(user.id, db)

        result = BigDataResponse(
            highest_win_rating=highest_win_rating,
            win_streak=win_streak,
            match_cities=0,  # TODO: 需要从 match_record.match_city 聚合
            total_opponents=total_opponents,
            indirect_wins=indirect_wins,
            total_matches=total_matches,
            win_rate=round(win_rate, 2),
            favorite_shot=None,  # TODO: 从 analysis_report.result_data 聚合
        )

        # 回填缓存
        await redis.setex(cache_key, UserService.BIG_DATA_CACHE_TTL, json.dumps(result.model_dump()))
        return result

    @staticmethod
    async def _compute_indirect_wins(user_id: int, db: AsyncSession) -> list[str]:
        """
        间接胜利算法：从用户出发沿胜利边 BFS（最大 4 层），匹配预置名人列表。

        当前实现：MatchRecord.opponent_user_id 为空时无法遍历图结构，
        返回空列表。未来当 opponent_user_id 普遍填充后启用 BFS 遍历。
        """
        from collections import deque
        from app.models.match import MatchRecord

        # 预置名人 ID 列表（实际从配置读取）
        CELEBRITY_IDS = [1, 2, 3, 4, 5]

        visited: set[int] = set()
        queue: deque[tuple[int, int]] = deque([(user_id, 0)])
        visited.add(user_id)
        celebrity_names: list[str] = []

        while queue:
            current_uid, depth = queue.popleft()
            if depth >= 4:
                continue

            # 查询 current_uid 战胜的对手
            stmt = (
                select(MatchRecord.opponent_name, MatchRecord.opponent_user_id)
                .where(
                    MatchRecord.user_id == current_uid,
                    MatchRecord.is_win.is_(True),
                    MatchRecord.opponent_user_id.isnot(None),
                )
                .limit(50)
            )
            opponents = (await db.execute(stmt)).all()

            for opp_name, opp_uid in opponents:
                if opp_uid and opp_uid in CELEBRITY_IDS and opp_name not in celebrity_names:
                    celebrity_names.append(opp_name)
                if opp_uid and opp_uid not in visited:
                    visited.add(opp_uid)
                    queue.append((opp_uid, depth + 1))

        return celebrity_names

    # =================================================================
    # 用户注销（PIPL 合规）
    # =================================================================

    @staticmethod
    async def delete_account(
        user: User, req: AccountDeletionRequest, db: AsyncSession
    ) -> AccountDeletionResponse:
        """用户注销（72h 冷静期）"""
        if user.status == "pending_deletion":
            raise AppException("您已提交注销申请，请勿重复操作", 409)

        # 校验 confirmation
        if req.confirmation != "DELETE_ACCOUNT_CONFIRM":
            raise AppException("确认口令不正确，请输入 DELETE_ACCOUNT_CONFIRM", 422)

        now = datetime.now(timezone.utc)
        scheduled_at = now + timedelta(hours=UserService.DELETION_COOLDOWN_HOURS)

        user.status = "pending_deletion"
        user.scheduled_deletion_at = scheduled_at
        user.deletion_reason = req.reason
        await db.commit()

        # TODO: 投递 Celery 延迟任务（72h 后执行永久删除）
        # from app.tasks.user_tasks import process_account_deletions
        # process_account_deletions.apply_async(args=[user.id], eta=scheduled_at)

        return AccountDeletionResponse(
            scheduled_deletion_at=scheduled_at,
            can_cancel_before=scheduled_at,
        )

    @staticmethod
    async def cancel_deletion(user: User, db: AsyncSession) -> dict:
        """撤销用户注销申请（72h 冷静期内）"""
        if user.status != "pending_deletion":
            raise AppException("无待执行的注销申请", 409)

        user.status = "active"
        user.scheduled_deletion_at = None
        user.deletion_reason = None
        await db.commit()

        return {
            "status": "active",
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
        }

    # =================================================================
    # 数据导出（PIPL 数据可携带权）
    # =================================================================

    @staticmethod
    async def export_data(user: User, db: AsyncSession) -> ExportCreateResponse:
        """发起个人数据导出（PIPL 数据可携带权）"""
        import uuid
        import calendar

        redis = await get_redis()

        # R5-User-2: 先 INCR 再检查（原子操作，避免竞态条件）
        now = datetime.now(timezone.utc)
        month_key = f"export:count:{user.id}:{now.year}{now.month:02d}"
        count = await redis.incr(month_key)
        if count == 1:
            # 首次计数，设置 TTL 到月末
            last_day = calendar.monthrange(now.year, now.month)[1]
            end_of_month = now.replace(day=last_day, hour=23, minute=59, second=59)
            ttl = int((end_of_month - now).total_seconds())
            await redis.expire(month_key, ttl)
        if count > UserService.EXPORT_MONTHLY_LIMIT:
            raise AppException("本月已导出过，请下月再试", 429)

        # 创建导出任务
        task_id = f"export_{now.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        export_task = ExportTask(
            user_id=user.id,
            task_id=task_id,
            status="pending",
        )
        db.add(export_task)
        await db.commit()

        # R12-User-2: 投递 Celery 异步导出任务（原 TODO 断链，任务永远 pending）
        from app.tasks.user import export_user_data
        export_user_data.delay(user.id, task_id)

        return ExportCreateResponse(task_id=task_id, status="pending")

    @staticmethod
    async def get_export_status(
        user: User, task_id: str, db: AsyncSession
    ) -> ExportStatusResponse:
        """查询导出任务状态"""
        stmt = select(ExportTask).where(
            ExportTask.task_id == task_id,
            ExportTask.user_id == user.id,
        )
        task = (await db.execute(stmt)).scalar_one_or_none()
        if not task:
            raise AppException("导出任务不存在", 404)

        if task.status in ("pending", "processing"):
            raise AppException("导出任务处理中，请稍后查询", 409)

        return ExportStatusResponse(
            task_id=task.task_id,
            status=task.status,
            download_url=task.download_url,
            expire_at=task.expire_at,
            file_size=task.file_size,
        )
