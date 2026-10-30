"""Celery tasks — 游戏化积分"""
import asyncio
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.gamification.reset_monthly_points")
def reset_monthly_points():
    """月度积分重置（每月 1 日 00:00 CST）"""
    logger.info("Running gamification.reset_monthly_points")

    async def _run():
        from app.core.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as db:
            await db.execute(
                text("UPDATE user_points SET monthly_points = 0")
            )
            await db.commit()

    from app.core.redis import run_isolated
    asyncio.run(run_isolated(_run()))
    return {"status": "ok"}
