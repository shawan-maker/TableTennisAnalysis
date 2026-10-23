"""Celery tasks — 用户管理"""
import asyncio
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.user.process_account_deletions")
def process_account_deletions():
    """处理到期账号注销（每小时）"""
    logger.info("Running user.process_account_deletions")

    async def _run():
        from app.core.database import async_session_factory
        from sqlalchemy import select, text
        from app.models.user import User
        from datetime import datetime, timezone, timedelta

        async with async_session_factory() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
            result = await db.execute(
                select(User).where(
                    User.status == "pending_deletion",
                    User.updated_at < cutoff,
                )
            )
            users = result.scalars().all()
            for user in users:
                user.status = "deleted"
                logger.info("Account deleted: user_id=%s", user.id)
            await db.commit()

    asyncio.run(_run())
    return {"status": "ok"}
