"""Celery tasks — 比赛记分"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.scoring.cleanup_abandoned_matches")
def cleanup_abandoned_matches():
    """
    清理废弃比赛（每小时）。

    扫描 status=abandoned 且 abandoned_at 超过 24h 的比赛：
    - 更新为 status=finished
    - 设置 finished_at / final_score / is_win
    - 创建 MatchStatistic（空统计占位，避免详情接口 404）
    """
    logger.info("Running cleanup_abandoned_matches")
    try:
        from app.core.redis import run_isolated
        return asyncio.run(run_isolated(_cleanup_abandoned_matches_async()))
    except RuntimeError as e:
        # 已在 event loop 中（罕见情况，如 eager + uvicorn 同线程）
        logger.error("cleanup_abandoned_matches_event_loop_error", extra={"error": str(e)})
        return {"status": "error", "error": str(e)}


async def _cleanup_abandoned_matches_async() -> dict:
    """异步实现 — 扫描并清理废弃比赛"""
    from sqlalchemy import select, update

    from app.core.database import async_session_factory
    from app.models.match import Match, MatchStatistic

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cleaned = 0

    async with async_session_factory() as db:
        # 查询需要清理的 abandoned 比赛（abandoned_at < 24h 前）
        result = await db.execute(
            select(Match).where(
                Match.status == "abandoned",
                Match.abandoned_at < cutoff,
            )
        )
        matches = result.scalars().all()

        for match in matches:
            now = datetime.now(timezone.utc)
            final_score = f"{match.current_score_user}:{match.current_score_opp}"
            is_win = match.current_score_user > match.current_score_opp

            # 更新 Match 为 finished
            await db.execute(
                update(Match)
                .where(Match.id == match.id)
                .values(
                    status="finished",
                    finished_at=now,
                    final_score=final_score,
                    is_win=is_win,
                )
            )

            # 创建 MatchStatistic（空统计占位）
            stat = MatchStatistic(
                match_id=match.id,
                stats_data={
                    "score_distribution": {
                        "serve_point": 0,
                        "rally_point": 0,
                        "opponent_error": 0,
                    },
                    "key_points": [],
                    "technique_breakdown": {},
                    "total_points": 0,
                    "auto_finished": True,
                },
            )
            db.add(stat)
            cleaned += 1

        await db.commit()

    logger.info("cleanup_abandoned_matches_done", extra={"cleaned": cleaned})
    return {"status": "ok", "cleaned": cleaned}
