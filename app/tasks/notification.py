"""Celery tasks — 通知管理

依据：切片 12-notification/backend.md §6 / beat_schedule.py
- cleanup_old_notifications：每月 1 日 02:00，删除 90 天前已读 + 归档 180 天前未读
- training_reminder：每日 19:00 CST，查询 >3 天未训练用户并推送训练提醒
"""
import logging
from datetime import datetime, timezone, timedelta

from celery import shared_task

logger = logging.getLogger(__name__)

# 清理策略阈值（与设计 §6.1 / beat_schedule 一致）
READ_RETENTION_DAYS = 90  # 已读通知保留 90 天
UNREAD_RETENTION_DAYS = 180  # 未读通知归档阈值（180 天）


@shared_task(name="app.tasks.notification.cleanup_old_notifications")
def cleanup_old_notifications():
    """清理过期通知（每月 1 日 02:00）

    策略：
    - 已读通知：删除 created_at 早于 90 天前的记录
    - 未读通知：归档（标记删除/物理删除）created_at 早于 180 天前的记录
      未读通知保留更久以防用户错过重要信息。
    """
    logger.info("Running notification.cleanup_old_notifications")
    import asyncio

    async def _run():
        from sqlalchemy import delete, select, func
        from app.core.database import async_session_factory
        from app.models.notification import NotificationRecord

        now = datetime.now(timezone.utc)
        read_threshold = now - timedelta(days=READ_RETENTION_DAYS)
        unread_threshold = now - timedelta(days=UNREAD_RETENTION_DAYS)

        async with async_session_factory() as db:
            # 1. 删除 90 天前已读通知
            read_result = await db.execute(
                delete(NotificationRecord).where(
                    NotificationRecord.is_read == True,  # noqa: E712
                    NotificationRecord.created_at < read_threshold,
                )
            )
            read_deleted = read_result.rowcount or 0

            # 2. 归档（删除）180 天前未读通知
            #    设计为归档；当前无独立归档表，直接删除以控制 notification_record 体积
            unread_result = await db.execute(
                delete(NotificationRecord).where(
                    NotificationRecord.is_read == False,  # noqa: E712
                    NotificationRecord.created_at < unread_threshold,
                )
            )
            unread_deleted = unread_result.rowcount or 0

            await db.commit()

        logger.info(
            "cleanup_old_notifications done: read_deleted=%s unread_deleted=%s",
            read_deleted, unread_deleted,
        )
        return {
            "status": "ok",
            "read_deleted": read_deleted,
            "unread_deleted": unread_deleted,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.exception("cleanup_old_notifications failed: %s", e)
        return {"status": "error", "error": str(e)}


@shared_task(name="app.tasks.notification.training_reminder")
def training_reminder():
    """训练提醒推送（每日 19:00 CST）

    查询 >3 天未训练（无新训练记录）的活跃用户，调用
    NotificationService.send_training_reminder 推送 WS + 微信订阅消息。
    频率控制：同一用户每周最多 2 次（由 NotificationService 内部控制）。
    """
    logger.info("Running notification.training_reminder")
    import asyncio

    async def _run():
        from sqlalchemy import select, func
        from app.core.database import async_session_factory
        from app.models.user import User
        from app.models.training import TrainingPlan
        from app.services.notification_service import NotificationService

        now = datetime.now(timezone.utc)
        inactive_threshold = now - timedelta(
            days=NotificationService.REMINDER_INACTIVE_DAYS,
        )

        async with async_session_factory() as db:
            # 查询有活跃训练计划但 >3 天未更新训练单的用户
            # 取每个用户最近一次训练计划 updated_at，筛选超过阈值的
            latest_plan_subq = (
                select(
                    TrainingPlan.user_id.label("uid"),
                    func.max(TrainingPlan.updated_at).label("last_active"),
                )
                .group_by(TrainingPlan.user_id)
                .subquery()
            )

            result = await db.execute(
                select(User.id, latest_plan_subq.c.last_active)
                .join(latest_plan_subq, latest_plan_subq.c.uid == User.id)
                .where(User.status == "active")
                .where(
                    (latest_plan_subq.c.last_active < inactive_threshold)
                    | (latest_plan_subq.c.last_active.is_(None))
                )
            )
            rows = result.all()

        pushed = 0
        for user_id, last_active in rows:
            # 计算未训练天数（last_active 为空时给一个大数以触发提醒）
            if last_active is None:
                days_inactive = NotificationService.REMINDER_INACTIVE_DAYS + 1
            else:
                # 确保 last_active 带时区后计算
                la = last_active if last_active.tzinfo else last_active.replace(
                    tzinfo=timezone.utc,
                )
                days_inactive = (now - la).days

            try:
                await NotificationService.send_training_reminder(
                    user_id=user_id,
                    last_training_days=days_inactive,
                )
                pushed += 1
            except Exception as e:
                logger.warning(
                    "training_reminder push failed user_id=%s: %s",
                    user_id, e,
                )

        logger.info(
            "training_reminder done: candidates=%s pushed=%s",
            len(rows), pushed,
        )
        return {
            "status": "ok",
            "candidates": len(rows),
            "pushed": pushed,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.exception("training_reminder failed: %s", e)
        return {"status": "error", "error": str(e)}

