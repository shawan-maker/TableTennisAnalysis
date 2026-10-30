"""
app/services/file_service.py — 文件管理服务（S3 开发版 Mock 模式）

依据：切片 13-infrastructure/file_management.md / 切片 03-video_analysis/backend.md §5
功能：STS Token 签发 + HEAD Object 校验 + 孤儿清理
Mock 模式：FILE_STORAGE_MOCK=True 时使用本地文件系统替代 OSS
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class FileService:
    """文件管理服务 — 支持 Mock 模式"""

    # OSS Key 模板
    OSS_KEY_TEMPLATE = "videos/raw/{user_id}/{yyyymmdd}/{uuid}.{ext}"

    @staticmethod
    def _is_mock() -> bool:
        return getattr(settings, "FILE_STORAGE_MOCK", True)

    @staticmethod
    def generate_oss_key(user_id: int, filename: str) -> str:
        """生成 OSS Key: videos/raw/{user_id}/{yyyymmdd}/{uuid}.{ext}"""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
        yyyymmdd = datetime.now(timezone.utc).strftime("%Y%m%d")
        return FileService.OSS_KEY_TEMPLATE.format(
            user_id=user_id, yyyymmdd=yyyymmdd, uuid=uuid.uuid4().hex[:12], ext=ext
        )

    @staticmethod
    def generate_sts_token(oss_key: str, permission: str = "PutObject", expire_seconds: int = 900) -> dict:
        """
        生成 STS 临时上传凭证。
        Mock 模式：返回假凭证 + 本地上传路径
        """
        if FileService._is_mock():
            # Mock 模式 — 返回本地路径
            local_dir = os.path.join(settings.LOCAL_UPLOAD_DIR, oss_key.rsplit("/", 1)[0])
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(settings.LOCAL_UPLOAD_DIR, oss_key)
            return {
                "access_key_id": "mock_ak",
                "access_key_secret": "mock_sk",
                "security_token": "mock_token",
                "expiration": (datetime.now(timezone.utc) + timedelta(seconds=expire_seconds)).isoformat(),
                "bucket": "mock-bucket",
                "endpoint": "http://localhost:3000/mock-oss",
                "upload_url": f"http://localhost:3000/mock-oss/{oss_key}",
                "_local_path": local_path,
            }
        else:
            # 真实 OSS — S6+ 实现
            raise NotImplementedError("OSS integration requires oss2 package (S6+)")

    @staticmethod
    def head_object(oss_key: str) -> Optional[dict]:
        """
        HEAD Object 校验 — 确认文件已上传。
        Mock 模式：检查本地文件是否存在
        返回: {content_length, etag, content_type} 或 None
        """
        if FileService._is_mock():
            local_path = os.path.join(settings.LOCAL_UPLOAD_DIR, oss_key)
            if os.path.exists(local_path):
                stat = os.stat(local_path)
                return {
                    "content_length": stat.st_size,
                    "etag": f"mock-{stat.st_size}",
                    "content_type": "video/mp4",
                }
            return None
        else:
            raise NotImplementedError("OSS integration requires oss2 package (S6+)")

    @staticmethod
    def save_uploaded_file(oss_key: str, data: bytes) -> None:
        """Mock 模式 — 保存上传文件到本地"""
        if FileService._is_mock():
            local_path = os.path.join(settings.LOCAL_UPLOAD_DIR, oss_key)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(data)
            logger.info("file_saved_mock", extra={"oss_key": oss_key, "size": len(data)})

    @staticmethod
    def delete_object(oss_key: str) -> None:
        """删除 OSS 对象（Mock 模式删除本地文件）"""
        if FileService._is_mock():
            local_path = os.path.join(settings.LOCAL_UPLOAD_DIR, oss_key)
            try:
                os.remove(local_path)
            except FileNotFoundError:
                pass
        else:
            raise NotImplementedError("OSS integration requires oss2 package (S6+)")

    @staticmethod
    def get_public_url(oss_key: str) -> str:
        """获取公开访问 URL（CDN 或本地）"""
        if FileService._is_mock():
            return f"http://localhost:3000/mock-oss/{oss_key}"
        elif settings.OSS_CDN_DOMAIN:
            return f"https://{settings.OSS_CDN_DOMAIN}/{oss_key}"
        else:
            return f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT}/{oss_key}"

    @staticmethod
    def get_video_duration(oss_key: str) -> Optional[int]:
        """
        获取视频时长（秒）。
        Mock 模式：返回默认 60 秒
        """
        if FileService._is_mock():
            return 60  # mock 默认 60s
        else:
            # S6+ — 使用 ffprobe
            raise NotImplementedError("ffprobe duration check requires ffmpeg (S6+)")

    @staticmethod
    def validate_file_type(filename: str) -> bool:
        """验证文件类型"""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in ("mp4", "mov")

    @staticmethod
    def validate_file_size(file_size: int) -> bool:
        """验证文件大小"""
        return settings.MIN_FILE_SIZE <= file_size <= settings.MAX_FILE_SIZE

    @staticmethod
    async def cleanup_orphan_files() -> dict:
        """
        孤儿文件清理 — R12-BeatTasks-1 实现设计（file_management.md §5）。

        流程：
        1. 查询 file_record WHERE status='uploading' AND created_at < NOW() - 1h
        2. 尝试删除 OSS 对象（忽略 404 / Mock 模式本地文件缺失）
        3. 更新 file_record.status='abandoned'

        幂等：基于 WHERE 条件，重复执行无副作用。
        """
        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.models.video_analysis import FileRecord

        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        cleaned_count = 0

        async with async_session_factory() as db:
            result = await db.execute(
                select(FileRecord).where(
                    FileRecord.status == "uploading",
                    FileRecord.created_at < cutoff,
                )
            )
            orphans = result.scalars().all()

            for record in orphans:
                try:
                    FileService.delete_object(record.oss_key)
                except Exception as e:
                    # OSS 删除失败 → 记录日志，不阻塞状态更新
                    logger.warning(
                        "orphan_oss_delete_failed",
                        extra={"oss_key": record.oss_key, "error": str(e)},
                    )
                record.status = "abandoned"
                cleaned_count += 1

            await db.commit()

        logger.info("orphan_cleanup_done", extra={"cleaned_count": cleaned_count})
        return {"cleaned_count": cleaned_count}
