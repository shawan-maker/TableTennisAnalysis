"""Celery tasks — 会员管理"""
import asyncio
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.membership.check_expiry")
def check_expiry():
    """会员到期检查（每日 00:30 CST）"""
    from app.services.membership_service import MembershipService

    logger.info("Running membership.check_expiry")

    async def _run():
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await MembershipService.check_expiry(db)

    asyncio.run(_run())
    return {"status": "ok"}
