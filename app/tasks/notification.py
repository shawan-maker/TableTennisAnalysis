"""Celery tasks — 通知管理"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.notification.cleanup_old_notifications")
def cleanup_old_notifications():
    """清理过期通知（每月 1 日 02:00）"""
    logger.info("Running notification.cleanup_old_notifications")
    # TODO: 删除 created_at > 90 天且 read_status=True 的通知记录
    return {"status": "ok"}


@shared_task(name="app.tasks.notification.training_reminder")
def training_reminder():
    """训练提醒推送（每日 19:00 CST）"""
    logger.info("Running notification.training_reminder")
    # TODO: 查询有活跃训练计划但 3 天未完成训练单的用户，推送 WS + 订阅消息
    return {"status": "ok"}
