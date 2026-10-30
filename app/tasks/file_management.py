"""Celery tasks — 文件管理

R12-BeatTasks-1: 补齐实现（原 TODO 空壳）。
依据：切片 13-infrastructure/file_management.md §5/§6.2 —
扫描 status=uploading 且超 1h 的记录 → 删除 OSS 对象（忽略 404）→ 标记 abandoned。
"""
import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.file_management.cleanup_orphan_files")
def cleanup_orphan_files():
    """清理 OSS 孤立文件（每小时）

    扫描 file_record 中 status='uploading' 且 created_at 超过 1h 的记录，
    删除 OSS 对象（Mock 模式下为本地文件，忽略不存在），更新状态为 abandoned。
    幂等：WHERE 条件清理，重复执行无副作用。
    """
    logger.info("Running cleanup_orphan_files")

    async def _run():
        from app.services.file_service import FileService
        return await FileService.cleanup_orphan_files()

    from app.core.redis import run_isolated
    result = asyncio.run(run_isolated(_run()))
    return {"status": "ok", **result}
