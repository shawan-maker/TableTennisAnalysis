"""Celery tasks — 比赛记分"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.scoring.cleanup_abandoned_matches")
def cleanup_abandoned_matches():
    """清理废弃比赛（每小时）"""
    logger.info("Running cleanup_abandoned_matches")
    # TODO: 扫描 match_record 表，删除 status=abandoned 超过 1h 的记录
    return {"status": "ok"}
