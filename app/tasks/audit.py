"""Celery tasks — 审计日志

R12-Admin-3/BeatTasks-2: 补齐实现（原 TODO 空壳 + 保留期口径错误）。
依据：数据库详细设计 §审计日志保留策略 — PIPL 合规保留期 3 年（1095 天），
超期记录由 Celery Beat 定期清理（原 TODO 写 180 天口径错误，已按设计修正为 3 年）。
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task

logger = logging.getLogger(__name__)

# PIPL 合规保留期：3 年
AUDIT_LOG_RETENTION_DAYS = 365 * 3


@shared_task(name="app.tasks.audit.cleanup_old_logs")
def cleanup_old_logs():
    """清理超期审计日志（每日 03:00）

    保留策略：PIPL 审计日志保留不少于 3 年（1095 天），超期记录删除。
    幂等：基于 WHERE created_at < cutoff 条件，重复执行无副作用。
    """
    logger.info("Running audit.cleanup_old_logs")

    async def _run():
        from sqlalchemy import delete

        from app.core.database import async_session_factory
        from app.models.admin import AuditLog

        cutoff = datetime.now(timezone.utc) - timedelta(days=AUDIT_LOG_RETENTION_DAYS)
        async with async_session_factory() as db:
            result = await db.execute(
                delete(AuditLog).where(AuditLog.created_at < cutoff)
            )
            await db.commit()
            return result.rowcount or 0

    from app.core.redis import run_isolated
    deleted = asyncio.run(run_isolated(_run()))
    logger.info(
        "audit_logs_cleaned",
        extra={"deleted": deleted, "retention_days": AUDIT_LOG_RETENTION_DAYS},
    )
    return {"status": "ok", "deleted": deleted, "retention_days": AUDIT_LOG_RETENTION_DAYS}
