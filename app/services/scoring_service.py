"""
app/services/scoring_service.py — 记分牌业务逻辑层

依据：切片 04-scoring/backend.md §3-§5
规范：Service 方法使用 @staticmethod，禁止创建实例
功能：状态机 + Redis INCR 序号 + 多设备同步 + 统计
架构约束：§15 约束 #31 比赛状态机 + Redis INCR
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import (
    AppException,
    ERR_BAD_REQUEST,
    ERR_MATCH_NOT_FOUND,
    ERR_MATCH_STATE_CONFLICT,
)
from app.core.redis import get_redis
from app.models.match import Match, MatchStatistic, ScoreRecord
from app.schemas.scoring import (
    MatchCreateRequest,
    ScoreRequest,
    UndoRequest,
)

logger = logging.getLogger(__name__)


class ScoringService:
    """记分牌业务逻辑层 — 状态机 + Redis INCR + 统计"""

    # Redis key 模板
    _SEQ_KEY = "scoring:match:{match_id}:seq"
    _SCORE_KEY = "scoring:match:{match_id}:current_score"
    _SERVER_KEY = "scoring:match:{match_id}:server"
    _STATUS_KEY = "scoring:match:{match_id}:status"

    # =================================================================
    # 辅助方法
    # =================================================================

    @staticmethod
    async def _get_match_or_404(match_id: int, user_id: int, db: AsyncSession) -> Match:
        """获取比赛或抛出 404"""
        result = await db.execute(
            select(Match).where(Match.id == match_id, Match.user_id == user_id)
        )
        match = result.scalar_one_or_none()
        if match is None:
            raise AppException("比赛不存在", 404, code=ERR_MATCH_NOT_FOUND)
        return match

    @staticmethod
    def _calc_server(score_user: int, score_opp: int, target_score: int, initial_server: str = "user") -> str:
        """
        计算当前发球方（11 分制规则）。
        正常情况下每 2 球轮换；10:10 后每 1 球轮换。
        """
        total_points = score_user + score_opp
        if score_user >= target_score - 1 and score_opp >= target_score - 1:
            switch_interval = 1  # deuce
        else:
            switch_interval = 2
        cycle = total_points // switch_interval
        if cycle % 2 == 0:
            return initial_server
        return "opponent" if initial_server == "user" else "user"

    @staticmethod
    def _is_key_point(score_user: int, score_opp: int, target_score: int) -> bool:
        """是否关键分（10:10 后或局点/赛点）"""
        if score_user >= target_score - 1 and score_opp >= target_score - 1:
            return True
        if score_user == target_score - 1 or score_opp == target_score - 1:
            return True
        return False

    @staticmethod
    def _should_change_sides(score_user: int, score_opp: int, target_score: int, game_ended: bool) -> bool:
        """是否应该换边"""
        if game_ended:
            return True
        if score_user >= target_score - 1 and score_opp >= target_score - 1:
            return True  # deuce 后每球换边
        return False

    # =================================================================
    # CRUD + 状态机
    # =================================================================

    @staticmethod
    async def create_match(user_id: int, req: MatchCreateRequest) -> dict:
        """创建比赛（状态 setup）"""
        async with async_session_factory() as db:
            match = Match(
                user_id=user_id,
                opponent_name=req.opponent_name,
                opponent_rating=req.opponent_rating,
                format=req.format,
                match_type=req.match_type,
                target_score=req.target_score,
                status="setup",
                current_score_user=0,
                current_score_opp=0,
                current_game=1,
                current_server="user",
            )
            db.add(match)
            await db.commit()
            await db.refresh(match)

            # Redis 初始化
            redis = await get_redis()
            await redis.set(ScoringService._STATUS_KEY.format(match_id=match.id), "setup")
            await redis.hset(
                ScoringService._SCORE_KEY.format(match_id=match.id),
                mapping={"user": 0, "opp": 0},
            )

            return {
                "match_id": match.id,
                "status": "setup",
                "current_server": "user",
            }

    @staticmethod
    async def list_matches(user_id: int, status: str | None, page: int, page_size: int) -> dict:
        """比赛列表（分页）"""
        async with async_session_factory() as db:
            qs = select(Match).where(Match.user_id == user_id)
            if status:
                qs = qs.where(Match.status == status)
            qs = qs.order_by(Match.created_at.desc())

            # 计数
            from sqlalchemy import func as sql_func
            count_qs = select(sql_func.count()).select_from(Match).where(Match.user_id == user_id)
            if status:
                count_qs = count_qs.where(Match.status == status)

            count_result = await db.execute(count_qs)
            total = count_result.scalar() or 0

            result = await db.execute(qs.offset((page - 1) * page_size).limit(page_size))
            matches = result.scalars().all()

            items = [
                {
                    "id": m.id,
                    "opponent_name": m.opponent_name,
                    "format": m.format,
                    "match_type": m.match_type,
                    "status": m.status,
                    "current_score_user": m.current_score_user,
                    "current_score_opp": m.current_score_opp,
                    "is_win": m.is_win,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in matches
            ]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
            }

    @staticmethod
    async def get_match_detail(user_id: int, match_id: int) -> dict:
        """比赛详情（含比分序列）"""
        async with async_session_factory() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)

            # 查询得分序列
            result = await db.execute(
                select(ScoreRecord)
                .where(ScoreRecord.match_id == match_id)
                .order_by(ScoreRecord.sequence)
            )
            records = result.scalars().all()

            score_sequence = [
                {
                    "seq": r.sequence,
                    "scorer": r.scorer,
                    "score_method": r.score_method,
                    "technique_action": r.technique_action,
                    "game_number": r.game_number,
                }
                for r in records
            ]

            return {
                "id": match.id,
                "opponent_name": match.opponent_name,
                "opponent_rating": match.opponent_rating,
                "format": match.format,
                "match_type": match.match_type,
                "target_score": match.target_score,
                "status": match.status,
                "current_score_user": match.current_score_user,
                "current_score_opp": match.current_score_opp,
                "current_score": f"{match.current_score_user}:{match.current_score_opp}",
                "current_server": match.current_server,
                "current_game": match.current_game,
                "is_win": match.is_win,
                "final_score": match.final_score,
                "score_sequence": score_sequence,
                "created_at": match.created_at.isoformat() if match.created_at else None,
                "finished_at": match.finished_at.isoformat() if match.finished_at else None,
            }

    @staticmethod
    async def score(user_id: int, match_id: int, req: ScoreRequest) -> dict:
        """记分 — Redis INCR 序号 + 更新比分 + WS 推送"""
        async with async_session_factory() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "in_progress":
                raise AppException("比赛未在进行中", 409, code=ERR_MATCH_STATE_CONFLICT)

            redis = await get_redis()

            # 1. Redis INCR 获取序号
            seq = await redis.incr(ScoringService._SEQ_KEY.format(match_id=match_id))

            # 2. 获取当前比分
            scores = await redis.hgetall(ScoringService._SCORE_KEY.format(match_id=match_id))
            score_user = int(scores.get("user", 0))
            score_opp = int(scores.get("opp", 0))

            # 3. 更新比分
            if req.scorer == "user":
                score_user += 1
            else:
                score_opp += 1

            # 4. 计算发球方 + 关键分 + 局结束
            current_server = ScoringService._calc_server(score_user, score_opp, match.target_score)
            is_key_point = ScoringService._is_key_point(score_user, score_opp, match.target_score)
            game_ended = (
                (score_user >= match.target_score and score_user - score_opp >= 2)
                or (score_opp >= match.target_score and score_opp - score_user >= 2)
            )
            should_change_sides = ScoringService._should_change_sides(
                score_user, score_opp, match.target_score, game_ended
            )

            # 5. 写入 ScoreRecord
            record = ScoreRecord(
                match_id=match_id,
                sequence=seq,
                scorer=req.scorer,
                score_method=req.score_method,
                technique_action=req.technique_action,
                game_number=match.current_game,
                is_key_point=is_key_point,
            )
            db.add(record)

            # 6. 更新 Redis
            await redis.hset(
                ScoringService._SCORE_KEY.format(match_id=match_id),
                mapping={"user": score_user, "opp": score_opp},
            )
            await redis.set(ScoringService._SERVER_KEY.format(match_id=match_id), current_server)

            # 7. 更新 Match 表冗余字段
            match.current_score_user = score_user
            match.current_score_opp = score_opp
            match.current_server = current_server

            await db.commit()

            # 8. WS 广播 score_update
            ws_message = json.dumps({
                "event": "score_update",
                "data": {
                    "match_id": match_id,
                    "sequence": seq,
                    "score": f"{score_user}:{score_opp}",
                    "scorer": req.scorer,
                    "score_method": req.score_method,
                    "current_server": current_server,
                    "is_key_point": is_key_point,
                },
            })
            try:
                from app.core.websocket import manager as ws_manager
                await ws_manager.broadcast_to_room(f"ws:match:{match_id}", ws_message)
            except Exception as e:
                logger.warning("scoring_ws_broadcast_failed", extra={"error": str(e)})

            return {
                "sequence": seq,
                "score": f"{score_user}:{score_opp}",
                "current_server": current_server,
                "game_number": match.current_game,
                "is_key_point": is_key_point,
                "match_status": match.status,
                "should_change_sides": should_change_sides,
            }

    @staticmethod
    async def undo(user_id: int, match_id: int, req: UndoRequest | None = None) -> dict:
        """撤销最近一球"""
        async with async_session_factory() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "in_progress":
                raise AppException("比赛未在进行中", 409, code=ERR_MATCH_STATE_CONFLICT)

            redis = await get_redis()

            # 获取当前最大序号
            max_seq_str = await redis.get(ScoringService._SEQ_KEY.format(match_id=match_id))
            if not max_seq_str or int(max_seq_str) == 0:
                raise AppException("没有可撤销的记录", 400, code=ERR_BAD_REQUEST)
            max_seq = int(max_seq_str)

            # 乐观并发检查
            if req and req.expected_seq is not None and req.expected_seq != max_seq:
                raise AppException("比分已更新，请确认后撤销", 409, code=ERR_MATCH_STATE_CONFLICT)

            # 查询最近一条记录
            result = await db.execute(
                select(ScoreRecord).where(
                    ScoreRecord.match_id == match_id, ScoreRecord.sequence == max_seq
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise AppException("没有可撤销的记录", 400, code=ERR_BAD_REQUEST)

            # 回滚比分
            scores = await redis.hgetall(ScoringService._SCORE_KEY.format(match_id=match_id))
            score_user = int(scores.get("user", 0))
            score_opp = int(scores.get("opp", 0))
            if record.scorer == "user":
                score_user = max(0, score_user - 1)
            else:
                score_opp = max(0, score_opp - 1)

            # 删除记录
            await db.delete(record)

            # Redis pipeline 原子操作
            pipe = redis.pipeline()
            pipe.decr(ScoringService._SEQ_KEY.format(match_id=match_id))
            pipe.hset(
                ScoringService._SCORE_KEY.format(match_id=match_id),
                mapping={"user": score_user, "opp": score_opp},
            )
            await pipe.execute()

            # 重算发球方
            current_server = ScoringService._calc_server(score_user, score_opp, match.target_score)
            await redis.set(ScoringService._SERVER_KEY.format(match_id=match_id), current_server)

            # 更新 Match 表
            match.current_score_user = score_user
            match.current_score_opp = score_opp
            match.current_server = current_server

            await db.commit()

            # WS 广播 undo
            ws_message = json.dumps({
                "event": "score_update",
                "data": {
                    "type": "undo",
                    "match_id": match_id,
                    "sequence": max_seq - 1,
                    "score": f"{score_user}:{score_opp}",
                    "current_server": current_server,
                },
            })
            try:
                from app.core.websocket import manager as ws_manager
                await ws_manager.broadcast_to_room(f"ws:match:{match_id}", ws_message)
            except Exception as e:
                logger.warning("scoring_ws_undo_broadcast_failed", extra={"error": str(e)})

            return {
                "sequence": max_seq - 1,
                "score": f"{score_user}:{score_opp}",
                "type": "undo",
            }

    @staticmethod
    async def start_match(user_id: int, match_id: int) -> dict:
        """开始比赛（setup -> in_progress）"""
        async with async_session_factory() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "setup":
                raise AppException("比赛已开始或已结束", 400, code=ERR_BAD_REQUEST)

            now = datetime.now(timezone.utc)
            match.status = "in_progress"
            match.started_at = now
            await db.commit()

            redis = await get_redis()
            await redis.set(ScoringService._STATUS_KEY.format(match_id=match_id), "in_progress")

            return {
                "match_id": match_id,
                "status": "in_progress",
                "started_at": now.isoformat(),
            }

    @staticmethod
    async def finish_match(user_id: int, match_id: int) -> dict:
        """结束比赛 -> 生成统计 + 级联创建记录"""
        async with async_session_factory() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "in_progress":
                raise AppException("比赛未在进行中", 409, code=ERR_MATCH_STATE_CONFLICT)

            score_user = match.current_score_user
            score_opp = match.current_score_opp
            is_win = score_user > score_opp
            final_score = f"{score_user}:{score_opp}"

            match.status = "finished"
            match.is_win = is_win
            match.final_score = final_score
            match.finished_at = datetime.now(timezone.utc)

            # 生成统计
            stats = await ScoringService._generate_statistics(match_id, db)
            statistic = MatchStatistic(match_id=match_id, stats_data=stats)
            db.add(statistic)

            # Redis 清理
            redis = await get_redis()
            await redis.delete(
                ScoringService._SEQ_KEY.format(match_id=match_id),
                ScoringService._SCORE_KEY.format(match_id=match_id),
                ScoringService._SERVER_KEY.format(match_id=match_id),
            )

            await db.commit()
            await db.refresh(statistic)

            # 级联：创建 match_record（trigger_points=False 避免重复积分）
            try:
                from app.services.match_data_service import MatchDataService
                await MatchDataService.create_record_from_scoring(
                    db, match_id=match.id, user_id=match.user_id, trigger_points=False
                )
            except Exception as e:
                logger.error("scoring_cascade_create_record_failed", extra={
                    "error": str(e), "match_id": match_id
                })

            # 游戏化积分（try/except 不阻塞）
            try:
                from app.services.gamification_service import GamificationService
                await GamificationService.add_points(
                    db, user_id=match.user_id, event_type="match", ref_id=match.id
                )
            except Exception as e:
                logger.error("gamification_add_points_match_failed", extra={
                    "error": str(e), "match_id": match_id
                })

            # WS 推送 match_finished
            try:
                from app.services.notification_service import NotificationService
                await NotificationService.push_ws_message(
                    match.user_id, "match_finished",
                    {"match_id": match.id, "final_score": final_score},
                )
            except Exception as e:
                logger.warning("scoring_ws_finish_push_failed", extra={"error": str(e)})

            return {
                "match_id": match_id,
                "final_score": final_score,
                "is_win": is_win,
                "statistic_id": statistic.id,
            }

    @staticmethod
    async def abandon_match(user_id: int, match_id: int) -> dict:
        """放弃比赛（in_progress -> abandoned）"""
        async with async_session_factory() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "in_progress":
                raise AppException("仅进行中的比赛可放弃", 400, code=ERR_BAD_REQUEST)

            now = datetime.now(timezone.utc)
            match.status = "abandoned"
            match.abandoned_at = now
            await db.commit()

            redis = await get_redis()
            await redis.set(ScoringService._STATUS_KEY.format(match_id=match_id), "abandoned")

            return {
                "match_id": match_id,
                "status": "abandoned",
                "abandoned_at": now.isoformat(),
            }

    @staticmethod
    async def resume_match(user_id: int, match_id: int) -> dict:
        """恢复放弃的比赛（abandoned -> in_progress，24h 内）"""
        async with async_session_factory() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "abandoned":
                raise AppException("仅放弃的比赛可恢复", 400, code=ERR_BAD_REQUEST)

            if match.abandoned_at is None:
                raise AppException("比赛放弃时间缺失", 400, code=ERR_BAD_REQUEST)

            elapsed = datetime.now(timezone.utc) - match.abandoned_at
            if elapsed > timedelta(hours=24):
                raise AppException("放弃超过 24h，比赛已自动结束", 400, code=ERR_BAD_REQUEST)

            match.status = "in_progress"
            match.abandoned_at = None
            await db.commit()

            redis = await get_redis()
            await redis.set(ScoringService._STATUS_KEY.format(match_id=match_id), "in_progress")

            return {
                "match_id": match_id,
                "status": "in_progress",
                "resumed_at": datetime.now(timezone.utc).isoformat(),
            }

    @staticmethod
    async def get_statistics(user_id: int, match_id: int) -> dict:
        """获取比赛统计"""
        async with async_session_factory() as db:
            match = await ScoringService._get_match_or_404(match_id, user_id, db)
            if match.status != "finished":
                raise AppException("比赛尚未结束", 400, code=ERR_BAD_REQUEST)

            result = await db.execute(
                select(MatchStatistic).where(MatchStatistic.match_id == match_id)
            )
            stat = result.scalar_one_or_none()
            if stat is None:
                raise AppException("比赛尚未结束", 400, code=ERR_BAD_REQUEST)

            return {
                "match_id": match_id,
                "stats_data": stat.stats_data,
            }

    @staticmethod
    async def _generate_statistics(match_id: int, db: AsyncSession) -> dict:
        """生成比赛统计 JSONB"""
        result = await db.execute(
            select(ScoreRecord)
            .where(ScoreRecord.match_id == match_id)
            .order_by(ScoreRecord.sequence)
        )
        records = result.scalars().all()

        score_distribution = {"serve_point": 0, "rally_point": 0, "opponent_error": 0}
        technique_breakdown: dict[str, int] = {}
        key_points: list[dict] = []

        for r in records:
            if r.score_method:
                score_distribution[r.score_method] = score_distribution.get(r.score_method, 0) + 1
            if r.technique_action:
                technique_breakdown[r.technique_action] = technique_breakdown.get(r.technique_action, 0) + 1
            if r.is_key_point:
                key_points.append({
                    "seq": r.sequence,
                    "scorer": r.scorer,
                    "score_method": r.score_method,
                })

        return {
            "score_distribution": score_distribution,
            "key_points": key_points,
            "technique_breakdown": technique_breakdown,
            "total_points": len(records),
        }
