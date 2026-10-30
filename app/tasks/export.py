"""Celery tasks — 数据导出

R12-BeatTasks-1: 补齐实现（原 TODO 空壳 + 保留期口径不一致）。
依据：切片 02-user/backend.md §6 cleanup_old_export_tasks —
清理 90 天前 status in (completed, failed) 的导出任务记录（DB 记录；OSS 临时文件接入在 S6+）。
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task

logger = logging.getLogger(__name__)

# 导出任务记录保留期：90 天（设计 02-user/backend.md §6）
EXPORT_TASK_RETENTION_DAYS = 90


@shared_task(name="app.tasks.export.cleanup_old_tasks")
def cleanup_old_tasks():
    """清理过期导出任务（每日 03:00）

    删除 created_at > 90 天且 status in (completed, failed) 的导出任务 DB 记录。
    （download_url 指向的 OSS 临时导出文件删除在 S6+ OSS 接入时补充。）
    幂等：基于 WHERE 条件，重复执行无副作用。
    """
    logger.info("Running export.cleanup_old_tasks")

    async def _run():
        from sqlalchemy import delete

        from app.core.database import async_session_factory
        from app.models.user import ExportTask

        cutoff = datetime.now(timezone.utc) - timedelta(days=EXPORT_TASK_RETENTION_DAYS)
        async with async_session_factory() as db:
            result = await db.execute(
                delete(ExportTask).where(
                    ExportTask.status.in_(["completed", "failed"]),
                    ExportTask.created_at < cutoff,
                )
            )
            await db.commit()
            return result.rowcount or 0

    from app.core.redis import run_isolated
    deleted = asyncio.run(run_isolated(_run()))
    logger.info(
        "export_tasks_cleaned",
        extra={"deleted": deleted, "retention_days": EXPORT_TASK_RETENTION_DAYS},
    )
    return {"status": "ok", "deleted": deleted, "retention_days": EXPORT_TASK_RETENTION_DAYS}
