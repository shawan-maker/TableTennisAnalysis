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

    try:
        from app.core.redis import run_isolated
        return asyncio.run(run_isolated(cleanup_old_notifications_impl()))
    except Exception as e:
        logger.exception("cleanup_old_notifications failed: %s", e)
        return {"status": "error", "error": str(e)}


async def cleanup_old_notifications_impl() -> dict:
    """清理逻辑（模块级 async 函数，便于单元测试在既有事件循环内直接调用）"""
    from sqlalchemy import delete
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


@shared_task(name="app.tasks.notification.training_reminder")
def training_reminder():
    """训练提醒推送（每日 19:00 CST）

    查询 >3 天无 AI 分析/记分牌比赛活动的活跃用户（R12-Notif-1：训练活动
    以最近 AI 分析任务或比赛判定，不依赖训练计划），调用
    NotificationService.send_training_reminder 推送 WS + 微信订阅消息。
    频率控制：同一用户每周最多 2 次（由 NotificationService 内部控制）。
    """
    logger.info("Running notification.training_reminder")
    import asyncio

    async def _run():
        from app.core.database import async_session_factory
        from app.services.notification_service import NotificationService

        async with async_session_factory() as db:
            # R12-Notif-1: 候选判定基于 3 天内 AI 分析/比赛活动
            # （原实现基于 TrainingPlan.updated_at，inner join 排除了无计划用户，
            #   且刚完成 AI 分析/比赛的用户被误判为未训练）
            candidates = await NotificationService.get_training_reminder_candidates(db)

        pushed = 0
        for user_id, days_inactive in candidates:
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
            len(candidates), pushed,
        )
        return {
            "status": "ok",
            "candidates": len(candidates),
            "pushed": pushed,
        }

    try:
        from app.core.redis import run_isolated
        return asyncio.run(run_isolated(_run()))
    except Exception as e:
        logger.exception("training_reminder failed: %s", e)
        return {"status": "error", "error": str(e)}

