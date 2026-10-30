"""Celery tasks — 用户管理"""
import asyncio
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 Celery 任务中运行异步协程 — 兼容 eager 模式下的事件循环嵌套

    生产 worker 无运行循环 → 直接 asyncio.run；
    eager/测试环境（运行循环中）→ 线程池内 asyncio.run。
    try 块只包裹探测：业务 RuntimeError 不得被误判为"无循环"后
    对已消费协程再次 asyncio.run（会掩盖原始异常，见 ai_pipeline/tasks.py）。

    R13-Test-N3: 每次执行经 run_isolated 隔离全局 Redis 池（前置 reset + 结束
    在任务自身 loop 上 close），防止跨 loop 死连接检出。
    """
    from app.core.redis import run_isolated
    coro = run_isolated(coro)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


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

    _run_async(_run())
    return {"status": "ok"}


@shared_task(name="app.tasks.user.export_user_data")
def export_user_data(user_id: int, task_id: str):
    """个人数据导出异步任务（R12-User-2 补齐，原 delay() TODO 断链）

    流程（依据 02-user/backend.md §6 export_user_data）：
    1. 查询 ExportTask → 状态 processing
    2. 导出用户数据（Phase 1 简化：生成下载 URL，实际打包上传 OSS 在 S6+）
    3. 更新状态 completed + download_url + expire_at（7 天）
    4. WS 推送 export_completed 通知
    失败：状态置 failed。
    """
    _run_async(_export_user_data_async(user_id, task_id))
    return {"status": "ok", "task_id": task_id}


async def _export_user_data_async(user_id: int, task_id: str) -> None:
    """导出任务异步实现"""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.core.database import async_session_factory
    from app.models.user import ExportTask
    from app.services.notification_service import NotificationService

    async with async_session_factory() as db:
        task = (
            await db.execute(
                select(ExportTask).where(
                    ExportTask.task_id == task_id,
                    ExportTask.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

        if not task:
            logger.warning("export_task_not_found", extra={"task_id": task_id})
            return

        try:
            # 更新状态为处理中
            task.status = "processing"
            await db.commit()

            # Phase 1 简化实现：生成下载 URL（实际导出打包+OSS 上传在 S6+ 接入）
            download_url = f"https://oss.pingpongai.com/exports/{task_id}.zip"
            file_size = 0  # 实际文件大小（S6+ 接入）

            # 更新任务状态为完成
            task.status = "completed"
            task.download_url = download_url
            task.file_size = file_size
            task.expire_at = datetime.now(timezone.utc) + timedelta(days=7)
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()

            # WS 推送导出完成通知（try/except 不阻塞）
            try:
                await NotificationService.push_ws_message(
                    user_id, "export_completed", {"task_id": task.task_id}
                )
            except Exception as ws_err:
                logger.warning(
                    "export_ws_push_failed",
                    extra={"task_id": task_id, "error": str(ws_err)},
                )

        except Exception as e:
            task.status = "failed"
            await db.commit()
            logger.error(
                "export_user_data_failed",
                extra={"user_id": user_id, "task_id": task_id, "error": str(e)},
            )
