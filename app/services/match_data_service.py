"""
app/services/match_data_service.py — 比赛数据业务逻辑层

依据：切片 05-match_data/backend.md §3-§5
规范：Service 方法使用 @staticmethod，禁止创建实例
功能：手动录入 + 列表/详情 + 编辑 + 记分牌级联
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import (
    AppException,
    ERR_BAD_REQUEST,
    ERR_MATCH_NOT_FOUND,
    ERR_RECORD_NOT_FOUND,
    ERR_RECORD_LINKED,
    ERR_SCORE_INVALID,
)
from app.models.match import (
    ManualScoreDetail,
    Match,
    MatchRecord,
    ScoreRecord,
)
from app.schemas.match_data import (
    ManualScoreDetailItem,
    MatchRecordCreateRequest,
    MatchRecordUpdate,
)

logger = logging.getLogger(__name__)


class MatchDataService:
    """比赛数据业务逻辑层"""

    FORMAT_WIN_MAP = {
        "bo1": 1,
        "bo3": 2,
        "bo5": 3,
        "bo7": 4,
    }

    # =================================================================
    # 辅助方法
    # =================================================================

    @staticmethod
    def _validate_score_by_format(my_score: int, opp_score: int, fmt: str) -> bool:
        """验证比分是否符合赛制规则"""
        if fmt == "custom":
            return my_score != opp_score
        win_needed = MatchDataService.FORMAT_WIN_MAP.get(fmt)
        if win_needed is None:
            return False
        if my_score == win_needed:
            return opp_score < win_needed
        if opp_score == win_needed:
            return my_score < win_needed
        return False

    @staticmethod
    async def _trigger_gamification(user_id: int, record_id: int) -> None:
        """触发游戏化积分（try/except 不阻塞）"""
        try:
            from app.services.gamification_service import GamificationService
            async with async_session_factory() as db:
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="record", ref_id=record_id
                )
        except Exception as e:
            logger.error("match_data_trigger_gamification_failed", extra={
                "error": str(e), "record_id": record_id
            })

    # =================================================================
    # CRUD
    # =================================================================

    @staticmethod
    async def create_record(user_id: int, req: MatchRecordCreateRequest) -> dict:
        """创建比赛记录（快速/详细录入）"""
        # 1. 比分验证
        if not MatchDataService._validate_score_by_format(
            req.my_score, req.opponent_score, req.format
        ):
            raise AppException("比分不符合赛制规则", 422, code=ERR_SCORE_INVALID)

        # 2. is_win 自动计算
        is_win = req.my_score > req.opponent_score

        # 3. is_detailed 检测
        is_detailed = req.details is not None and len(req.details) > 0

        async with async_session_factory() as db:
            # 4. 可选 match_id 验证
            match_id = req.match_id
            if match_id is not None:
                result = await db.execute(
                    select(Match).where(Match.id == match_id, Match.user_id == user_id)
                )
                if result.scalar_one_or_none() is None:
                    match_id = None  # 静默忽略不存在的 match_id

            # 5. 创建 MatchRecord
            record = MatchRecord(
                user_id=user_id,
                opponent_name=req.opponent_name,
                opponent_rating=req.opponent_rating,
                my_score=req.my_score,
                opponent_score=req.opponent_score,
                is_win=is_win,
                format=req.format,
                match_type=req.match_type,
                match_date=req.match_date,
                match_id=match_id,
                is_detailed=is_detailed,
            )
            db.add(record)
            await db.flush()

            # 6. 详细录入 -> 创建 ManualScoreDetail
            if is_detailed and req.details:
                for item in req.details:
                    detail = ManualScoreDetail(
                        match_record_id=record.id,
                        sequence=item.sequence,
                        scorer=item.scorer,
                        score_method=item.score_method,
                        technique_action=item.technique_action,
                    )
                    db.add(detail)

            await db.commit()
            await db.refresh(record)

        # 7. 触发游戏化积分（不阻塞）
        await MatchDataService._trigger_gamification(user_id, record.id)

        return {"id": record.id, "is_win": is_win, "match_id": record.match_id}

    @staticmethod
    async def create_record_from_scoring(
        db: AsyncSession, match_id: int, user_id: int, trigger_points: bool = True
    ) -> dict:
        """
        记分牌结束比赛时级联创建记录。
        接收调用方的 db session，不创建新 session。
        trigger_points=False 时跳过积分触发（避免与 finish_match 重复）。
        """
        # 1. 查询 Match
        result = await db.execute(
            select(Match).where(Match.id == match_id, Match.user_id == user_id)
        )
        match = result.scalar_one_or_none()
        if match is None:
            raise AppException("记分牌比赛不存在", 404, code=ERR_MATCH_NOT_FOUND)

        # 2. 解析最终比分
        if match.final_score and ":" in match.final_score:
            parts = match.final_score.split(":")
            my_score = int(parts[0].strip())
            opponent_score = int(parts[1].strip())
        else:
            my_score = match.current_score_user or 0
            opponent_score = match.current_score_opp or 0

        # 3. 查询得分记录
        result = await db.execute(
            select(ScoreRecord)
            .where(ScoreRecord.match_id == match_id)
            .order_by(ScoreRecord.sequence)
        )
        score_records = result.scalars().all()
        is_detailed = len(score_records) > 0

        # 4. 创建 MatchRecord
        # 使用 CST（UTC+8）作为默认 match_date，避免跨日边界错误
        tz_cst = timezone(timedelta(hours=8))
        match_date = match.finished_at if match.finished_at else datetime.now(tz_cst)

        record = MatchRecord(
            user_id=user_id,
            opponent_name=match.opponent_name,
            opponent_rating=match.opponent_rating,
            my_score=my_score,
            opponent_score=opponent_score,
            is_win=match.is_win if match.is_win is not None else (my_score > opponent_score),
            format=match.format,
            match_type=match.match_type,
            match_date=match_date,
            match_id=match_id,
            is_detailed=is_detailed,
        )
        db.add(record)
        await db.flush()

        # 5. 创建 ManualScoreDetail
        if is_detailed:
            for sr in score_records:
                detail = ManualScoreDetail(
                    match_record_id=record.id,
                    sequence=sr.sequence,
                    scorer=sr.scorer,
                    score_method=sr.score_method,
                    technique_action=sr.technique_action,
                )
                db.add(detail)

        await db.commit()
        await db.refresh(record)

        # 6. 条件触发游戏化积分
        if trigger_points:
            await MatchDataService._trigger_gamification(user_id, record.id)

        return {"id": record.id, "is_win": record.is_win}

    @staticmethod
    async def list_records(
        user_id: int, result_filter: str | None, page: int, page_size: int
    ) -> dict:
        """比赛记录列表（分页）"""
        async with async_session_factory() as db:
            qs = select(MatchRecord).where(MatchRecord.user_id == user_id)
            count_qs = select(func.count()).select_from(MatchRecord).where(
                MatchRecord.user_id == user_id
            )

            if result_filter and result_filter != "all":
                is_win_filter = result_filter == "win"
                qs = qs.where(MatchRecord.is_win == is_win_filter)
                count_qs = count_qs.where(MatchRecord.is_win == is_win_filter)

            qs = qs.order_by(MatchRecord.match_date.desc())

            # 计数
            count_result = await db.execute(count_qs)
            total = count_result.scalar() or 0

            # 分页查询
            result = await db.execute(qs.offset((page - 1) * page_size).limit(page_size))
            records = result.scalars().all()

            items = [
                {
                    "id": r.id,
                    "opponent_name": r.opponent_name,
                    "opponent_rating": r.opponent_rating,
                    "my_score": r.my_score,
                    "opponent_score": r.opponent_score,
                    "is_win": r.is_win,
                    "format": r.format,
                    "match_type": r.match_type,
                    "match_date": r.match_date.isoformat() if r.match_date else None,
                }
                for r in records
            ]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
            }

    @staticmethod
    async def get_detail(user_id: int, record_id: int) -> dict:
        """比赛记录详情（含得分明细）"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(MatchRecord).where(
                    MatchRecord.id == record_id, MatchRecord.user_id == user_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise AppException("比赛记录不存在", 404, code=ERR_RECORD_NOT_FOUND)

            # 查询得分明细
            result = await db.execute(
                select(ManualScoreDetail)
                .where(ManualScoreDetail.match_record_id == record_id)
                .order_by(ManualScoreDetail.sequence)
            )
            details = result.scalars().all()

            return {
                "id": record.id,
                "opponent_name": record.opponent_name,
                "opponent_rating": record.opponent_rating,
                "my_score": record.my_score,
                "opponent_score": record.opponent_score,
                "is_win": record.is_win,
                "format": record.format,
                "match_type": record.match_type,
                "match_date": record.match_date.isoformat() if record.match_date else None,
                "match_id": record.match_id,
                "is_detailed": record.is_detailed,
                "notes": record.notes,
                "details": [
                    {
                        "sequence": d.sequence,
                        "scorer": d.scorer,
                        "score_method": d.score_method,
                        "technique_action": d.technique_action,
                    }
                    for d in details
                ],
            }

    @staticmethod
    async def update_record(
        user_id: int, record_id: int, data: MatchRecordUpdate
    ) -> dict:
        """编辑比赛记录（PATCH 语义）"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(MatchRecord).where(
                    MatchRecord.id == record_id, MatchRecord.user_id == user_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise AppException("比赛记录不存在", 404, code=ERR_RECORD_NOT_FOUND)

            # 关联记分牌的记录不可编辑
            if record.match_id is not None:
                raise AppException(
                    "比赛记录已关联记分牌，不可编辑", 409, code=ERR_RECORD_LINKED
                )

            update_data = data.model_dump(exclude_unset=True)
            if not update_data:
                raise AppException("未提供任何更新字段", 422, code=ERR_BAD_REQUEST)

            # 记录实际更新的字段名（排除 is_win —— 由后续逻辑决定）
            updated_fields = [k for k in update_data.keys() if k != "is_win"]

            for field, value in update_data.items():
                if hasattr(record, field):
                    setattr(record, field, value)

            # is_win 处理：
            # - 用户显式传入 is_win 时优先使用用户值
            # - 否则仅当同时传入 my_score 和 opponent_score 时才重算
            if data.is_win is not None:
                record.is_win = data.is_win
            elif data.my_score is not None and data.opponent_score is not None:
                record.is_win = record.my_score > record.opponent_score

            await db.commit()
            await db.refresh(record)

            return {
                "id": record.id,
                "is_win": record.is_win,
                "updated_fields": updated_fields,
            }
