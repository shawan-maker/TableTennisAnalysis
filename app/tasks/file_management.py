"""Celery tasks — 文件管理"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.file_management.cleanup_orphan_files")
def cleanup_orphan_files():
    """清理 OSS 孤立文件（每小时）"""
    logger.info("Running cleanup_orphan_files")
    # TODO: 扫描 file_record 表，删除 status=abandoned 超过 24h 的 OSS 对象
    return {"status": "ok"}
