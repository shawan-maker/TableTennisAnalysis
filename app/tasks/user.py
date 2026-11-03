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
    """处理到期账号注销（每小时）

    R14-User-1: 补齐 API 详细设计 §3.6 业务规则 3 / 02-user 切片 §9 BR-4 七步级联。
    原实现仅置 status="deleted"：PII（phone/openid/nickname）永久留存，且
    phone/openid 继续占据部分唯一索引 → 已注销手机号/微信号无法重新注册。
    级联步骤（BR-4）：
    1. 查询 status='pending_deletion' 且 updated_at < NOW()-72h 的用户
    2. 匿名化个人数据（nickname='已注销用户'/avatar_url=null/phone=null/openid=null）
    3. 关联视频标记删除（file_record.status='deleted'，OSS 物理删除由清理任务承担）
    4. 分析报告匿名化（analysis_report.is_anonymized=true，user_id 保留供训练数据）
    5. 取消订阅（subscription.status='cancelled'，仅非终态订阅）
    6. 更新 status='deleted'
    7. 清理 Redis 缓存（big_data:user:{uid} / notif:unread:{uid}）
    8. 记录审计日志（用户侧操作，admin_id 为空）
    """
    logger.info("Running user.process_account_deletions")

    async def _run():
        from app.core.database import async_session_factory
        from sqlalchemy import select, update
        from app.models.user import User
        from app.models.admin import AuditLog
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
            deleted_ids = []
            for user in users:
                # 2. 匿名化个人数据（PIPL）— phone/openid 置空同时释放部分唯一
                #    索引占用（idx_user_phone/idx_user_openid 均为 IS NOT NULL 部分索引），
                #    已注销手机号/微信号可重新注册
                user.nickname = "已注销用户"
                user.avatar_url = None
                user.phone = None
                user.openid = None
                # R15-User-N1: 补齐画像字段匿名化 — kqs_username/playing_style/
                # self_assessed_level 为可识别/偏好 PII，equipment_config 含
                # 器材偏好（底板/胶皮等），kqs_rating 为外部平台关联数据。
                # 原实现仅清 4 基础字段，画像字段永久留存 → PIPL 删除权不完整。
                user.kqs_rating = None
                user.kqs_username = None
                user.playing_style = None
                user.equipment_config = None
                user.self_assessed_level = None
                # 6. 状态置 deleted + 清空注销标记字段
                user.status = "deleted"
                user.scheduled_deletion_at = None
                user.deletion_reason = None
                deleted_ids.append(user.id)

                # 3. 关联视频标记删除
                from app.models.video_analysis import FileRecord
                await db.execute(
                    update(FileRecord)
                    .where(FileRecord.user_id == user.id)
                    .values(status="deleted")
                )

                # 4. 分析报告匿名化保留（user_id 保留，匿名归档用于模型训练数据）
                from app.models.video_analysis import AnalysisReport
                await db.execute(
                    update(AnalysisReport)
                    .where(AnalysisReport.user_id == user.id)
                    .values(is_anonymized=True)
                )

                # 5. 取消订阅（仅非终态：active/expiring_soon/grace_period；
                #    expired/closed 已为终态，不做状态回退）
                from app.models.membership import Subscription
                await db.execute(
                    update(Subscription)
                    .where(
                        Subscription.user_id == user.id,
                        Subscription.status.in_(
                            ("active", "expiring_soon", "grace_period")
                        ),
                    )
                    .values(
                        status="cancelled",
                        cancelled_at=datetime.now(timezone.utc),
                    )
                )

                # 8. 审计日志（用户侧操作：admin_id 为空、user_id 记录被操作用户）
                db.add(
                    AuditLog(
                        user_id=user.id,
                        action="account_deleted",
                        target_type="user",
                        target_id=user.id,
                        detail="账号注销冷静期到期，个人数据已按 BR-4 级联匿名化",
                    )
                )

                logger.info("Account deleted: user_id=%s", user.id)
            await db.commit()

        # 7. 清理 Redis 缓存（独立于 DB 事务：清理失败不回滚匿名化结果）
        if deleted_ids:
            try:
                from app.core.redis import get_redis
                redis = await get_redis()
                for uid in deleted_ids:
                    await redis.delete(
                        f"big_data:user:{uid}", f"notif:unread:{uid}"
                    )
            except Exception as e:
                logger.warning(
                    "account_deletion_redis_cleanup_failed",
                    extra={"error": str(e), "user_ids": deleted_ids},
                )

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
