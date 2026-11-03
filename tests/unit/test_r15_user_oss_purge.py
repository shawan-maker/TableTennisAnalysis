"""
tests/unit/test_r15_user_oss_purge.py — R15-User-N2 锁定测试

R15-A5 发现：软删文件 OSS 物删除断链 —
  * file_management.md §4 契约「status=deleted，24h 后 OSS 物理删除」+
    §5 规范「必须通过 Celery 延迟任务 24h 后物理删除，禁止立即删除」
  * process_account_deletions 注释声称「OSS 物理删除由清理任务承担」，
    但任务与 Beat 注册均不存在 → 软删对象永久留存（PIPL 删除权缺口）

R15 修复：
  * FileService.cleanup_deleted_files：扫描 status='deleted' 且
    updated_at < NOW()-24h → 删 OSS 对象 → 成功置 'purged'（终态）；
    失败保持 deleted 下轮重试（自愈）
  * app/tasks/file_management.py 任务包装 + Beat 注册
    file-management-deleted-cleanup（每小时 :30，queue=infra）
  * FileRecord status 枚举扩展 purged

锁定矩阵：
  a) 软删 25h + Mock 本地文件 → 物理删除（本地文件消失）+ status='purged'
  b) 软删未满 24h → 不处理（文件保留、状态不变）
  c) 幂等：purged 终态不再匹配 → 二次运行 purged_count=0
  d) OSS 对象缺失（404 语义）→ FileNotFoundError 被吸收 → 仍置 purged
  e) Beat 注册：file-management-deleted-cleanup → 任务名 + infra 队列

任务体为裸 asyncio.run 包装（app/tasks/file_management.py 与
cleanup_orphan_files 同模式），pytest-asyncio 循环内直调会 RuntimeError
—— 经 asyncio.to_thread 在工作线程执行（依据 test_r14_f_aip_beat.py
L526-544 先例）。
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.video_analysis import FileRecord
from app.services.file_service import FileService


async def _seed_deleted_file(db, user_id, oss_key, updated_at, save_local=True):
    """种子软删 FileRecord（file_size ≥ 1MB 满足 CHECK）+ Mock 本地文件"""
    record = FileRecord(
        user_id=user_id,
        oss_key=oss_key,
        original_filename="r15.mp4",
        file_size=1048576,
        file_type="mp4",
        status="deleted",
        uploaded_at=updated_at,
        updated_at=updated_at,  # INSERT 显式赋值（onupdate 仅 UPDATE 时生效）
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    if save_local:
        FileService.save_uploaded_file(oss_key, b"r15-oss-purge")
        assert os.path.exists(os.path.join(settings.LOCAL_UPLOAD_DIR, oss_key))
    return record


async def _run_task() -> dict:
    """工作线程执行裸 asyncio.run 任务体（eager 语义等效生产 Beat 调度）"""
    from app.tasks.file_management import cleanup_deleted_files

    return await asyncio.to_thread(cleanup_deleted_files)


async def _get_status(record_id: int) -> str:
    async with async_session_factory() as v:
        rec = (await v.execute(
            select(FileRecord).where(FileRecord.id == record_id)
        )).scalar_one()
        return rec.status


@pytest.mark.asyncio
async def test_a_soft_deleted_purged_after_24h(db_session, test_user):
    """a) 软删 25h → OSS 物理删除 + status='purged'"""
    oss_key = f"test/r15purge/{test_user.id}/a.mp4"
    rec = await _seed_deleted_file(
        db_session, test_user.id, oss_key,
        datetime.now(timezone.utc) - timedelta(hours=25),
    )

    result = await _run_task()
    assert result["status"] == "ok"
    assert result["purged_count"] >= 1

    assert await _get_status(rec.id) == "purged"
    # OSS 对象物理删除（Mock = 本地文件消失）
    assert not os.path.exists(os.path.join(settings.LOCAL_UPLOAD_DIR, oss_key))


@pytest.mark.asyncio
async def test_b_fresh_soft_deleted_untouched(db_session, test_user):
    """b) 软删未满 24h → 文件保留、状态不变（禁止立即删除）"""
    oss_key = f"test/r15purge/{test_user.id}/b.mp4"
    rec = await _seed_deleted_file(
        db_session, test_user.id, oss_key,
        datetime.now(timezone.utc) - timedelta(hours=23),
    )

    await _run_task()

    assert await _get_status(rec.id) == "deleted"
    assert os.path.exists(os.path.join(settings.LOCAL_UPLOAD_DIR, oss_key))


@pytest.mark.asyncio
async def test_c_idempotent_double_run(db_session, test_user):
    """c) 幂等：purged 终态不再匹配 WHERE → 二次运行 purged_count=0"""
    oss_key = f"test/r15purge/{test_user.id}/c.mp4"
    await _seed_deleted_file(
        db_session, test_user.id, oss_key,
        datetime.now(timezone.utc) - timedelta(hours=25),
    )

    first = await _run_task()
    assert first["purged_count"] >= 1

    second = await _run_task()
    assert second["purged_count"] == 0
    assert second["failed_count"] == 0


@pytest.mark.asyncio
async def test_d_missing_oss_object_still_purged(db_session, test_user):
    """d) OSS 对象缺失（404/FileNotFoundError 被吸收）→ 仍置 purged"""
    oss_key = f"test/r15purge/{test_user.id}/d.mp4"
    rec = await _seed_deleted_file(
        db_session, test_user.id, oss_key,
        datetime.now(timezone.utc) - timedelta(hours=25),
        save_local=False,  # OSS 对象从未存在
    )

    result = await _run_task()
    assert result["status"] == "ok"
    assert await _get_status(rec.id) == "purged"


@pytest.mark.asyncio
async def test_e_beat_registration():
    """e) Beat 注册：file-management-deleted-cleanup → 任务名 + infra 队列"""
    from app.core.celery import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "file-management-deleted-cleanup" in schedule
    entry = schedule["file-management-deleted-cleanup"]
    assert entry["task"] == "app.tasks.file_management.cleanup_deleted_files"
    assert entry["options"]["queue"] == "infra"

    # 任务在 Celery 注册表中（.delay 可调度）
    assert "app.tasks.file_management.cleanup_deleted_files" in celery_app.tasks
