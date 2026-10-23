"""Celery tasks — 数据导出"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.export.cleanup_old_tasks")
def cleanup_old_tasks():
    """清理过期导出任务（每日 03:00）"""
    logger.info("Running export.cleanup_old_tasks")
    # TODO: 删除 created_at > 30 天且 status in (completed, failed) 的导出任务
    return {"status": "ok"}
