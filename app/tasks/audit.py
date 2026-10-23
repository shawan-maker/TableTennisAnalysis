"""Celery tasks — 审计日志"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.audit.cleanup_old_logs")
def cleanup_old_logs():
    """清理过期审计日志（每日 03:00）"""
    logger.info("Running audit.cleanup_old_logs")
    # TODO: 删除 created_at > 180 天的审计日志
    return {"status": "ok"}
