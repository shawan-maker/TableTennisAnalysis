# file_management 基础设施模块 — 后端垂直切片设计

> **模块名称**：`file_management`
> **所属目录**：`app/api/v1/files/`（upload-token/upload-complete 端点由 video_analysis 路由调用 file_service）
> **定位**：STS Token 签发、OSS 直传校验、文件生命周期管理、孤儿文件清理
> **依据**：模块详细设计 v1.2 §3.4、数据库详细设计 v1.5 §2.4

---

## 1. 模块概述

| 属性 | 值 |
|------|-----|
| 模块名称 | `file_management` |
| 所属目录 | `app/api/v1/files/` + `app/services/file_service.py` |
| 一句话定位 | STS Token 发放、OSS 直传校验、文件生命周期管理、孤儿文件清理 |
| 关联数据表 | file_record |
| 依赖模块 | auth, `app/core/oss.py`（OSS 工具） |
| API 调用方 | video_analysis 路由调用 FileService 方法（不暴露独立 REST 端点） |

### 核心功能

- **STS Token 签发**：PutObject 权限，15min 过期，OSS Key: `videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4`
- **上传完成校验**：HEAD Object 确认 + Content-Length 匹配
- **孤儿文件清理**：Celery Beat 每小时扫描 status=uploading 且超 1h → abandoned
- **文件软删除**：status=deleted，24h 后 OSS 物理删除

---

## 2. 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/file_management.py` | 无 | ☐ |
| 2 | 注册 Model | `app/models/__init__.py` | #1 | ☐ |
| 3 | 定义 Schema | `app/schemas/file_management.py` | #1 | ☐ |
| 4 | 实现 Service | `app/services/file_service.py` | #2,#3 | ☐ |
| 5 | 编写 Celery Beat 任务 | `app/tasks/file_cleanup.py` | #4 | ☐ |
| 6 | 编写测试 | `tests/unit/test_file_management.py` | #4 | ☐ |
| 7 | 编写冒烟测试 | `tests/smoke/file_management_smoke_test.py` | #4 | ☐ |

---

## 3. Model 实现

```python
# app/models/file_management.py
"""文件管理数据模型。"""

from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# FileRecord 定义在 app/models/video_analysis.py，此处不再重复定义
# from app.models.video_analysis import FileRecord
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入 `FileRecord`
- [ ] 运行 `alembic revision --autogenerate -m "add file_record"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/file_management.py
"""文件管理 Schema 定义。"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class UploadTokenRequest(BaseModel):
    """获取上传凭证请求。"""
    filename: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., gt=0, le=500 * 1024 * 1024, description="文件大小(bytes)，最大 500MB")


class UploadTokenResponse(BaseModel):
    """上传凭证响应。"""
    file_id: int
    sts_credentials: dict
    """OSS STS Token: {access_key_id, access_key_secret, security_token, expiration, bucket, endpoint}"""
    oss_key: str
    """OSS 对象 Key: videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4"""
    expire_at: str
    """Token 过期时间 ISO 8601"""


class UploadCompleteRequest(BaseModel):
    """上传完成确认请求。"""
    file_id: int = Field(..., ge=1)


class UploadCompleteResponse(BaseModel):
    """上传完成确认响应。"""
    file_id: int
    status: str
    actual_size: int
    oss_etag: str


class FileRecordBrief(BaseModel):
    """文件记录简要。"""
    id: int
    oss_key: str
    original_filename: Optional[str]
    file_size: int
    file_type: str
    status: str
    created_at: datetime
    uploaded_at: Optional[datetime] = None
    model_config = {"from_attributes": True}
```

---

## 5. Service 实现

```python
# app/services/file_service.py
"""文件管理业务逻辑层。"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.database import get_async_session
from app.core.oss import OSSClient
from app.models.file_management import FileRecord
from app.schemas.file_management import (
    UploadTokenRequest, UploadTokenResponse,
    UploadCompleteRequest, UploadCompleteResponse,
)

# 允许的文件类型
ALLOWED_FILE_TYPES = {"mp4", "mov"}
# 最大文件大小
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
# STS Token 有效期
STS_TOKEN_TTL = 900  # 15 分钟


class FileService:
    """文件管理业务逻辑层。"""

    @staticmethod
    async def generate_upload_token(
        user_id: int,
        req: UploadTokenRequest,
    ) -> UploadTokenResponse:
        """签发 STS Token——PutObject 权限，15min 过期。

        流程：
        1. 校验文件类型（mp4/mov）+ 大小（≤500MB）
        2. 生成 OSS Key: videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4
        3. 请求 STS Token（PutObject 权限，15min 过期）
        4. 创建 file_record（status=uploading）
        """
        # 1. 校验文件类型
        ext = req.filename.rsplit(".", 1)[-1].lower() if "." in req.filename else ""
        if ext not in ALLOWED_FILE_TYPES:
            raise AppException(
                f"仅支持 MP4/MOV 格式，不支持 {ext}", 400
            )

        # 2. 校验文件大小
        if req.file_size > MAX_FILE_SIZE:
            raise AppException(
                f"视频文件不能超过 500MB，当前 {req.file_size / 1024 / 1024:.0f}MB", 400
            )

        # 3. 生成 OSS Key
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_uuid = str(uuid.uuid4())
        oss_key = f"videos/raw/{user_id}/{today}/{file_uuid}.{ext}"

        # 4. 请求 STS Token
        oss_client = OSSClient()
        sts_credentials = await oss_client.generate_sts_token(
            oss_key=oss_key,
            permission="PutObject",
            ttl=STS_TOKEN_TTL,
        )

        expire_at = (datetime.now(timezone.utc) + timedelta(seconds=STS_TOKEN_TTL)).isoformat()

        # 5. 创建 file_record
        async with get_async_session() as db:
            record = FileRecord(
                user_id=user_id,
                oss_key=oss_key,
                original_filename=req.filename,
                file_size=req.file_size,
                file_type=ext,
                status="uploading",
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            file_id = record.id

        return UploadTokenResponse(
            file_id=file_id,
            sts_credentials=sts_credentials,
            oss_key=oss_key,
            expire_at=expire_at,
        )

    @staticmethod
    async def confirm_upload(
        user_id: int,
        req: UploadCompleteRequest,
    ) -> UploadCompleteResponse:
        """上传完成校验——HEAD Object 确认 + Content-Length 匹配。

        流程：
        1. HEAD Object 获取文件元数据
        2. 校验 Content-Length 与 file_record.file_size 一致
        3. 更新 file_record（status=uploaded, oss_etag, actual_size, uploaded_at）
        """
        async with get_async_session() as db:
            record = await db.scalar(
                select(FileRecord).where(
                    FileRecord.id == req.file_id,
                    FileRecord.user_id == user_id,
                )
            )
            if not record:
                raise AppException("文件记录不存在", 404)
            if record.status != "uploading":
                raise AppException(
                    f"文件状态不允许确认上传: {record.status}", 400
                )

            # HEAD Object 校验
            oss_client = OSSClient()
            try:
                metadata = await oss_client.head_object(record.oss_key)
            except Exception:
                raise AppException(
                    "未检测到上传的文件，请重新上传", 404
                )

            if not metadata or not metadata.get("content_length"):
                raise AppException(
                    "未检测到上传的文件，请重新上传", 404
                )

            actual_size = int(metadata["content_length"])

            # 校验大小匹配
            if actual_size != record.file_size:
                raise AppException(
                    f"上传文件大小({actual_size} bytes)与声明({record.file_size} bytes)不符", 400
                )

            # 更新记录
            record.status = "uploaded"
            record.actual_size = actual_size
            record.oss_etag = metadata.get("etag", "")
            record.uploaded_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(record)

            return UploadCompleteResponse(
                file_id=record.id,
                status=record.status,
                actual_size=actual_size,
                oss_etag=record.oss_etag or "",
            )

    @staticmethod
    async def get_file_record(file_id: int, user_id: int) -> Optional[FileRecord]:
        """获取文件记录。"""
        async with get_async_session() as db:
            return await db.scalar(
                select(FileRecord).where(
                    FileRecord.id == file_id,
                    FileRecord.user_id == user_id,
                )
            )

    @staticmethod
    async def soft_delete(file_id: int, user_id: int) -> None:
        """文件软删除——status=deleted，24h 后 OSS 物理删除。

        触发：分析报告删除 / 用户注销
        """
        async with get_async_session() as db:
            record = await db.scalar(
                select(FileRecord).where(
                    FileRecord.id == file_id,
                    FileRecord.user_id == user_id,
                )
            )
            if not record:
                raise AppException("文件记录不存在", 404)

            record.status = "deleted"
            record.deleted_at = datetime.now(timezone.utc)
            await db.commit()

        # 触发 24h 延迟物理删除任务
        from app.core.celery import celery_app
        celery_app.send_task(
            "file_management.physical_delete",
            args=[file_id, record.oss_key],
            countdown=24 * 3600,  # 24h 后执行
        )

    @staticmethod
    async def cleanup_orphan_files() -> dict:
        """孤儿文件清理——每小时扫描 status=uploading 且超 1h 的记录。

        流程：
        1. 查询 file_record WHERE status='uploading' AND created_at < NOW() - 1h
        2. 尝试删除 OSS 对象（忽略 404）
        3. 更新 file_record.status='abandoned'
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        cleaned_count = 0

        async with get_async_session() as db:
            orphans = await db.scalars(
                select(FileRecord).where(
                    FileRecord.status == "uploading",
                    FileRecord.created_at < cutoff,
                )
            )

            oss_client = OSSClient()
            for record in orphans:
                try:
                    # 尝试删除 OSS 对象（忽略 404）
                    await oss_client.delete_object(record.oss_key)
                except Exception as e:
                    # OSS 删除失败 → 记录日志，不阻塞状态更新
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Failed to delete OSS object {record.oss_key}: {e}"
                    )

                record.status = "abandoned"
                cleaned_count += 1

            await db.commit()

        return {"cleaned_count": cleaned_count}

    @staticmethod
    async def physical_delete_oss_object(file_id: int, oss_key: str) -> None:
        """物理删除 OSS 对象（24h 延迟任务）。

        由 soft_delete 触发的 Celery 延迟任务。
        """
        oss_client = OSSClient()
        try:
            await oss_client.delete_object(oss_key)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Physical delete OSS object {oss_key} failed: {e}"
            )
```

    @staticmethod
    async def archive_for_training(report_id: int, task_id: int) -> str:
        """数据飞轮归档 — 将视频+AI分析结果复制到 OSS annotations/ 目录。

        当用户反馈 is_correct=true 时由 video_analysis Service 调用。
        文件名使用 report_id（不含 user_id），符合隐私保护约束（架构 §8.3）。

        Args:
            report_id: 分析报告 ID（用作归档目录名）
            task_id: VideoTask ID（用于查找原始视频 oss_key）

        Returns:
            annotation_path: 归档路径（如 annotations/v1/{report_id}/）

        归档内容：
        - video.mp4: 原始视频副本（从 task.oss_key 复制）
        - analysis.json: AI 分析结果 JSON（从 report.result_data 导出）
        - manifest.json: 标注元数据（report_id, task_id, archived_at, dataset_version）
        """
        from app.models.video_analysis import VideoTask, AnalysisReport  # R17-P2: 修正导入路径 app.models.video→app.models.video_analysis
        from datetime import datetime, timezone

        oss_client = OSSClient()
        dataset_version = "v1"  # Phase 1 固定版本号，Phase 2+ 支持多版本

        # 1. 查询原始视频路径和分析结果
        async with get_async_session() as db:  # R17-P2: async_db_session→get_async_session（模块导入的函数名）
            task = await db.get(VideoTask, task_id)
            if not task:
                raise ValueError(f"VideoTask {task_id} not found")

            report = await db.execute(
                select(AnalysisReport).where(AnalysisReport.id == report_id)
            )
            report = report.scalar_one_or_none()
            if not report:
                raise ValueError(f"AnalysisReport {report_id} not found")

            base_path = f"annotations/{dataset_version}/{report_id}"

            # 2. 复制原始视频到归档目录（OSS 内部复制）
            video_dest = f"{base_path}/video.mp4"
            await oss_client.copy_object(
                source_bucket=settings.OSS_BUCKET,
                source_key=task.oss_key,
                dest_bucket=settings.OSS_BUCKET,
                dest_key=video_dest,
            )

            # 3. 导出 AI 分析结果 JSON
            analysis_dest = f"{base_path}/analysis.json"
            analysis_data = report.result_data or {}
            await oss_client.put_object(
                bucket=settings.OSS_BUCKET,
                key=analysis_dest,
                content=json.dumps(analysis_data, ensure_ascii=False).encode(),
            )

            # 4. 生成标注元数据 Manifest
            manifest = {
                "report_id": report_id,
                "task_id": task_id,
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "dataset_version": dataset_version,
                "video_key": video_dest,
                "analysis_key": analysis_dest,
                "feedback_source": "auto_archive",  # is_correct=true 自动归档
            }
            manifest_dest = f"{base_path}/manifest.json"
            await oss_client.put_object(
                bucket=settings.OSS_BUCKET,
                key=manifest_dest,
                content=json.dumps(manifest, ensure_ascii=False).encode(),
            )

        return base_path
```

---

## 6. 调用方式

### 6.1 被 video_analysis 路由调用

```python
# app/api/v1/video_analysis/router.py（调用方示例）
from app.services.file_service import FileService
from app.schemas.file_management import UploadTokenRequest, UploadCompleteRequest

@router.post("/upload-token", summary="获取 OSS 上传凭证")
async def get_upload_token(
    body: UploadTokenRequest,
    user: User = Depends(get_current_user),
):
    """获取 STS Token + OSS Key，客户端直传 OSS。"""
    data = await FileService.generate_upload_token(user.id, body)
    return success(data=data)

@router.post("/upload-complete", summary="上传完成确认")
async def confirm_upload(
    body: UploadCompleteRequest,
    user: User = Depends(get_current_user),
):
    """HEAD Object 校验上传完整性。"""
    data = await FileService.confirm_upload(user.id, body)
    return success(data=data)
```

### 6.2 被 Celery Beat 调用（孤儿清理）

```python
# app/tasks/file_cleanup.py
"""文件清理定时任务。"""

from app.core.celery import celery_app
from app.services.file_service import FileService


@celery_app.task(name="file_management.cleanup_orphans")
def cleanup_orphan_files():
    """每小时清理孤儿文件。

    扫描 status=uploading 且 created_at 超过 1 小时的记录，
    删除 OSS 对象（忽略 404），更新状态为 abandoned。

    注意：Celery worker 默认不支持 async def task，使用 asyncio.run() 驱动异步逻辑。
    """
    import asyncio
    result = asyncio.run(FileService.cleanup_orphan_files())
    import logging
    logging.getLogger(__name__).info(
        f"Orphan file cleanup: {result['cleaned_count']} files cleaned"
    )
    return result


@celery_app.task(name="file_management.physical_delete")
def physical_delete_task(file_id: int, oss_key: str):
    """24h 延迟物理删除 OSS 对象。"""
    import asyncio
    asyncio.run(FileService.physical_delete_oss_object(file_id, oss_key))

# R17-P1: async def -> def + asyncio.run() (Celery worker 默认不支持 async def task)
```

**Celery Beat 配置**（`app/core/celery.py`）：
```python
beat_schedule = {
    # ...
    "file-cleanup-orphans": {
        "task": "file_management.cleanup_orphans",
        "schedule": 3600.0,  # 每小时
    },
}
```

---

## 7. 测试要点

```python
# tests/unit/test_file_management.py
"""file_management 模块测试。覆盖：STS 签发、上传校验、孤儿清理、软删除。"""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.file_service import FileService
from app.schemas.file_management import UploadTokenRequest, UploadCompleteRequest
from app.core.exceptions import AppException


# === 1. STS Token 签发 ===
@pytest.mark.asyncio
async def test_generate_upload_token_success(db_session, mock_oss):
    """成功签发 STS Token + 创建 file_record。"""
    req = UploadTokenRequest(filename="test.mp4", file_size=100 * 1024 * 1024)
    with patch("app.services.file_service.OSSClient") as mock_oss_class:
        mock_oss_class.return_value.generate_sts_token = AsyncMock(return_value={
            "access_key_id": "test_ak",
            "access_key_secret": "test_sk",
            "security_token": "test_token",
            "expiration": "2026-10-10T13:00:00Z",
        })
        result = await FileService.generate_upload_token(user_id=1, req=req)
    assert result.file_id > 0
    assert result.oss_key.startswith("videos/raw/1/")
    assert result.oss_key.endswith(".mp4")
    assert "sts_credentials" in result.model_dump()


@pytest.mark.asyncio
async def test_generate_upload_token_invalid_type(db_session):
    """不支持的文件类型返回 400。"""
    req = UploadTokenRequest(filename="test.avi", file_size=100 * 1024)
    with pytest.raises(AppException) as exc:
        await FileService.generate_upload_token(user_id=1, req=req)
    assert exc.value.code == 400
    assert "MP4/MOV" in exc.value.message


@pytest.mark.asyncio
async def test_generate_upload_token_too_large(db_session):
    """文件超过 500MB 返回 400。"""
    req = UploadTokenRequest(
        filename="test.mp4",
        file_size=501 * 1024 * 1024,  # 501MB
    )
    with pytest.raises(AppException) as exc:
        await FileService.generate_upload_token(user_id=1, req=req)
    assert exc.value.code == 400
    assert "500MB" in exc.value.message


@pytest.mark.asyncio
async def test_oss_key_format(db_session, mock_oss):
    """OSS Key 格式正确: videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4。"""
    req = UploadTokenRequest(filename="test.mp4", file_size=1024)
    with patch("app.services.file_service.OSSClient") as mock_oss_class:
        mock_oss_class.return_value.generate_sts_token = AsyncMock(return_value={})
        result = await FileService.generate_upload_token(user_id=42, req=req)
    # 验证 Key 格式
    parts = result.oss_key.split("/")
    assert parts[0] == "videos"
    assert parts[1] == "raw"
    assert parts[2] == "42"  # user_id
    assert len(parts[3]) == 8  # yyyymmdd
    assert len(parts[4]) > 0  # uuid.mp4


# === 2. 上传完成校验 ===
@pytest.mark.asyncio
async def test_confirm_upload_success(db_session, mock_oss):
    """HEAD Object 校验成功。"""
    # 先创建 uploading 记录
    from app.models.file_management import FileRecord
    record = FileRecord(
        user_id=1, oss_key="videos/raw/1/20260101/test.mp4",
        file_size=1024, file_type="mp4", status="uploading",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    with patch("app.services.file_service.OSSClient") as mock_oss_class:
        mock_oss_class.return_value.head_object = AsyncMock(return_value={
            "content_length": 1024,
            "etag": "abc123",
        })
        result = await FileService.confirm_upload(
            user_id=1,
            req=UploadCompleteRequest(file_id=record.id),
        )
    assert result.status == "uploaded"
    assert result.actual_size == 1024


@pytest.mark.asyncio
async def test_confirm_upload_not_found_in_oss(db_session):
    """OSS 文件不存在返回 404。"""
    from app.models.file_management import FileRecord
    record = FileRecord(
        user_id=1, oss_key="videos/raw/1/20260101/test.mp4",
        file_size=1024, file_type="mp4", status="uploading",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    with patch("app.services.file_service.OSSClient") as mock_oss_class:
        mock_oss_class.return_value.head_object = AsyncMock(side_effect=Exception("Not Found"))
        with pytest.raises(AppException) as exc:
            await FileService.confirm_upload(
                user_id=1,
                req=UploadCompleteRequest(file_id=record.id),
            )
        assert exc.value.code == 404


@pytest.mark.asyncio
async def test_confirm_upload_size_mismatch(db_session, mock_oss):
    """大小不匹配返回 400。"""
    from app.models.file_management import FileRecord
    record = FileRecord(
        user_id=1, oss_key="videos/raw/1/20260101/test.mp4",
        file_size=2048, file_type="mp4", status="uploading",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    with patch("app.services.file_service.OSSClient") as mock_oss_class:
        mock_oss_class.return_value.head_object = AsyncMock(return_value={
            "content_length": 1024,  # 声明 2048，实际 1024
            "etag": "abc",
        })
        with pytest.raises(AppException) as exc:
            await FileService.confirm_upload(
                user_id=1,
                req=UploadCompleteRequest(file_id=record.id),
            )
        assert exc.value.code == 400
        assert "不符" in exc.value.message


# === 3. 孤儿文件清理 ===
@pytest.mark.asyncio
async def test_cleanup_orphans(db_session, mock_oss):
    """清理超 1h 的 uploading 记录。"""
    from app.models.file_management import FileRecord
    from datetime import datetime, timedelta, timezone

    # 创建超时记录
    old_record = FileRecord(
        user_id=1, oss_key="videos/raw/1/20260101/old.mp4",
        file_size=1024, file_type="mp4", status="uploading",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    # 创建未超时记录
    new_record = FileRecord(
        user_id=1, oss_key="videos/raw/1/20260101/new.mp4",
        file_size=1024, file_type="mp4", status="uploading",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    db_session.add_all([old_record, new_record])
    await db_session.commit()

    with patch("app.services.file_service.OSSClient") as mock_oss_class:
        mock_oss_class.return_value.delete_object = AsyncMock()
        result = await FileService.cleanup_orphan_files()

    assert result["cleaned_count"] == 1
    await db_session.refresh(old_record)
    assert old_record.status == "abandoned"
    await db_session.refresh(new_record)
    assert new_record.status == "uploading"  # 未超时不变


# === 4. 软删除 ===
@pytest.mark.asyncio
async def test_soft_delete(db_session, mock_oss):
    """软删除标记 status=deleted。"""
    from app.models.file_management import FileRecord
    record = FileRecord(
        user_id=1, oss_key="videos/raw/1/20260101/test.mp4",
        file_size=1024, file_type="mp4", status="uploaded",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    with patch("app.core.celery.celery_app.send_task") as mock_send:
        await FileService.soft_delete(record.id, user_id=1)

    await db_session.refresh(record)
    assert record.status == "deleted"
    assert record.deleted_at is not None
    # 验证延迟删除任务被触发
    mock_send.assert_called_once()
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_file_management.py -v`
- [ ] STS Token 可成功直传 OSS（PutObject 权限）
- [ ] HEAD Object 校验正确拒绝不存在的文件
- [ ] HEAD Object 校验正确检测大小不匹配
- [ ] 孤儿文件清理正确执行（uploading + 1h 超时 → abandoned）
- [ ] 软删除后 24h 内 OSS 对象被物理删除
- [ ] OSS Key 命名遵循 `videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4` 规范
- [ ] 文件类型校验正确（仅 mp4/mov）
- [ ] 文件大小校验正确（≤500MB）
- [ ] Celery Beat 孤儿清理每小时执行
- [ ] Model 已在 `app/models/__init__.py` 中导入
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- OSS Key **必须** 遵循 `videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4` 格式，**禁止** 自定义路径
- STS Token **必须** 设置 15min 过期，**禁止** 永不过期
- 上传完成 **必须** 执行 HEAD Object 校验，**禁止** 仅信任客户端
- 孤儿文件清理 **必须** 忽略 OSS 404 错误，**禁止** 因 OSS 对象不存在而阻塞
- 软删除 **必须** 通过 Celery 延迟任务 24h 后物理删除，**禁止** 立即删除
- 文件类型校验 **必须** 拒绝非 mp4/mov 格式，**禁止** 接受任意类型
