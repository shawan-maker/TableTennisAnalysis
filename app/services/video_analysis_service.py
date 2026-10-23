"""
app/services/video_analysis_service.py — 视频分析业务逻辑层

依据：切片 03-video_analysis/backend.md §5
功能：上传凭证/确认/任务创建/列表/详情/报告/反馈/分享
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import (
    AppException,
    ERR_BAD_REQUEST,
    ERR_FILE_NOT_FOUND,
    ERR_FILE_NOT_UPLOADED,
    ERR_QUOTA_EXHAUSTED,
    ERR_REPORT_NOT_FOUND,
    ERR_SHARE_TOKEN_INVALID,
)
from app.core.redis import get_redis
from app.models.user import User
from app.models.match import ShareRecord
from app.models.video_analysis import (
    AnalysisReport,
    FeedbackRecord,
    FileRecord,
    PipelineStep,
    VideoTask,
)
from app.schemas.video_analysis import (
    CreateTaskRequest,
    FeedbackRequest,
    UploadCompleteRequest,
    UploadTokenRequest,
)
from app.services.file_service import FileService

logger = logging.getLogger(__name__)


class VideoAnalysisService:
    """视频分析业务逻辑层"""

    FREE_DAILY_LIMIT = settings.FREE_DAILY_ANALYSIS_LIMIT
    SHARE_DAILY_LIMIT = settings.SHARE_DAILY_LIMIT
    SHARE_EXPIRE_DAYS = settings.SHARE_EXPIRE_DAYS

    # =================================================================
    # 上传凭证
    # =================================================================

    @staticmethod
    async def get_upload_token(user_id: int, req: UploadTokenRequest) -> dict:
        """获取 OSS 直传凭证"""
        # 1. 验证文件类型
        if not FileService.validate_file_type(req.filename):
            raise AppException("仅支持 MP4/MOV 格式", 422, code=ERR_BAD_REQUEST)

        # 2. 验证文件大小
        if not FileService.validate_file_size(req.file_size):
            raise AppException("文件大小需在 1MB-500MB 之间", 422, code=ERR_BAD_REQUEST)

        # 3. 生成 OSS Key
        oss_key = FileService.generate_oss_key(user_id, req.filename)

        # 4. 签发 STS Token
        sts = FileService.generate_sts_token(oss_key)

        # 5. 创建 file_record
        ext = req.filename.rsplit(".", 1)[-1].lower() if "." in req.filename else "mp4"
        async with async_session_factory() as db:
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

        return {
            "file_id": record.id,
            "oss_key": oss_key,
            "sts_credentials": {
                "access_key_id": sts["access_key_id"],
                "access_key_secret": sts["access_key_secret"],
                "security_token": sts["security_token"],
                "expiration": sts["expiration"],
                "bucket": sts["bucket"],
                "endpoint": sts["endpoint"],
            },
            "upload_url": sts["upload_url"],
            "expire_at": sts["expiration"],
        }

    # =================================================================
    # 上传完成确认
    # =================================================================

    @staticmethod
    async def confirm_upload(user_id: int, req: UploadCompleteRequest) -> dict:
        """上传完成确认 — HEAD Object 校验"""
        async with async_session_factory() as db:
            record = await VideoAnalysisService._get_file_record(req.file_id, user_id, db)
            if record.status != "uploading":
                raise AppException("文件已确认或已废弃", 400, code=ERR_BAD_REQUEST)

            # HEAD Object 校验
            head = FileService.head_object(record.oss_key)
            if not head:
                raise AppException("文件未上传完成", 400, code=ERR_FILE_NOT_UPLOADED)

            # 获取视频时长
            duration_sec = FileService.get_video_duration(record.oss_key)

            # 时长校验（5s ~ 600s）
            if duration_sec and (duration_sec < settings.MIN_VIDEO_DURATION or duration_sec > settings.MAX_VIDEO_DURATION):
                raise AppException(
                    f"视频时长需在 {settings.MIN_VIDEO_DURATION}s ~ {settings.MAX_VIDEO_DURATION}s 之间",
                    422,
                    code=ERR_BAD_REQUEST,
                )

            # 更新 file_record
            record.status = "uploaded"
            record.oss_etag = head["etag"]
            record.actual_size = head["content_length"]
            record.uploaded_at = datetime.now(timezone.utc)
            await db.commit()

            return {
                "file_id": record.id,
                "ready": True,
                "actual_size": head["content_length"],
                "duration_sec": duration_sec,
            }

    # =================================================================
    # 任务创建
    # =================================================================

    @staticmethod
    async def create_task(user_id: int, req: CreateTaskRequest) -> dict:
        """创建分析任务"""
        async with async_session_factory() as db:
            record = await VideoAnalysisService._get_file_record(req.file_id, user_id, db)
            if record.status != "uploaded":
                raise AppException("文件尚未上传完成", 400, code=ERR_FILE_NOT_UPLOADED)

            # 免费配额检查（会员跳过 — S5 实现）
            await VideoAnalysisService._check_free_quota(user_id)

            # 创建 VideoTask
            task_uuid = str(uuid.uuid4())
            duration_sec = FileService.get_video_duration(record.oss_key) or 60
            task = VideoTask(
                user_id=user_id,
                file_id=req.file_id,
                oss_key=record.oss_key,
                duration_sec=duration_sec,
                status="queued",
                task_uuid=task_uuid,
                total_steps=10,
                progress=0,
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)

        # 启动 Celery 流水线
        try:
            from app.ai_pipeline.pipeline import PipelineOrchestrator
            await PipelineOrchestrator.build_and_run(task.id, record.oss_key)
        except Exception as e:
            logger.error("pipeline_start_failed", extra={
                "error": str(e), "task_id": task.id
            })
            # 标记任务失败
            async with async_session_factory() as db:
                await db.execute(
                    update(VideoTask)
                    .where(VideoTask.id == task.id)
                    .values(status="failed", error_message=f"流水线启动失败: {e}")
                )
                await db.commit()

        return {
            "task_id": task.id,
            "task_uuid": task_uuid,
            "status": "queued",
            "estimated_wait_minutes": 3,
        }

    # =================================================================
    # 任务列表/详情
    # =================================================================

    @staticmethod
    async def list_tasks(
        user_id: int, status: str | None, page: int, page_size: int
    ) -> dict:
        """任务列表（分页）"""
        async with async_session_factory() as db:
            qs = select(VideoTask).where(VideoTask.user_id == user_id)
            count_qs = select(func.count()).select_from(VideoTask).where(
                VideoTask.user_id == user_id
            )

            if status:
                qs = qs.where(VideoTask.status == status)
                count_qs = count_qs.where(VideoTask.status == status)

            qs = qs.order_by(VideoTask.created_at.desc())

            count_result = await db.execute(count_qs)
            total = count_result.scalar() or 0

            result = await db.execute(qs.offset((page - 1) * page_size).limit(page_size))
            tasks = result.scalars().all()

            # 批量查询关联报告（避免 N+1）
            task_ids = [t.id for t in tasks]
            if task_ids:
                report_result = await db.execute(
                    select(AnalysisReport.task_id, AnalysisReport.id).where(
                        AnalysisReport.task_id.in_(task_ids)
                    )
                )
                report_map = {row[0]: row[1] for row in report_result}
            else:
                report_map = {}

            items = [
                {
                    "id": t.id,
                    "task_uuid": t.task_uuid,
                    "status": t.status,
                    "current_step": t.current_step,
                    "total_steps": t.total_steps,
                    "progress": t.progress,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "report_id": report_map.get(t.id),
                }
                for t in tasks
            ]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
            }

    @staticmethod
    async def get_task_detail(user_id: int, task_id: int) -> dict:
        """任务详情"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(VideoTask).where(
                    VideoTask.id == task_id, VideoTask.user_id == user_id
                )
            )
            task = result.scalar_one_or_none()
            if task is None:
                raise AppException("任务不存在", 404, code=ERR_FILE_NOT_FOUND)

            # 查询关联报告
            report_id = None
            if task.status == "completed":
                report_result = await db.execute(
                    select(AnalysisReport.id).where(AnalysisReport.task_id == task_id)
                )
                report = report_result.scalar_one_or_none()
                if report:
                    report_id = report

            return {
                "id": task.id,
                "task_uuid": task.task_uuid,
                "status": task.status,
                "current_step": task.current_step,
                "total_steps": task.total_steps,
                "step_name": task.step_name,
                "progress": task.progress,
                "estimated_remaining_seconds": task.estimated_remaining_seconds,
                "error_message": task.error_message,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "report_id": report_id,
            }

    # =================================================================
    # 报告
    # =================================================================

    @staticmethod
    async def list_reports(user_id: int, page: int, page_size: int) -> dict:
        """报告列表（分页）"""
        async with async_session_factory() as db:
            qs = select(AnalysisReport).where(AnalysisReport.user_id == user_id)
            count_qs = select(func.count()).select_from(AnalysisReport).where(
                AnalysisReport.user_id == user_id
            )
            qs = qs.order_by(AnalysisReport.created_at.desc())

            count_result = await db.execute(count_qs)
            total = count_result.scalar() or 0

            result = await db.execute(qs.offset((page - 1) * page_size).limit(page_size))
            reports = result.scalars().all()

            items = [
                {
                    "id": r.id,
                    "task_id": r.task_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "is_llm_generated": r.is_llm_generated,
                    "cover_image_url": r.cover_image_url,
                }
                for r in reports
            ]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
            }

    @staticmethod
    async def get_report_detail(user_id: int, report_id: int) -> dict:
        """报告详情"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.user_id == user_id,
                )
            )
            report = result.scalar_one_or_none()
            if report is None:
                raise AppException("分析报告不存在", 404, code=ERR_REPORT_NOT_FOUND)

            # 查询关联 task_uuid
            task_result = await db.execute(
                select(VideoTask.task_uuid).where(VideoTask.id == report.task_id)
            )
            task_uuid = task_result.scalar_one_or_none()

            return {
                "id": report.id,
                "task_id": report.task_id,
                "task_uuid": task_uuid,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "is_llm_generated": report.is_llm_generated,
                "is_readonly": report.is_anonymized,
                "result_data": report.result_data,
                "report_text": report.report_text,
                "annotated_video_url": report.annotated_video_url,
                "cover_image_url": report.cover_image_url,
                "report_images": report.report_images,
            }

    # =================================================================
    # 反馈
    # =================================================================

    @staticmethod
    async def submit_feedback(
        user_id: int, report_id: int, req: FeedbackRequest
    ) -> dict:
        """提交反馈（可覆盖）"""
        async with async_session_factory() as db:
            # 验证报告存在
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.user_id == user_id,
                )
            )
            report = result.scalar_one_or_none()
            if report is None:
                raise AppException("分析报告不存在", 404, code=ERR_REPORT_NOT_FOUND)

            # 查找已有反馈
            existing_result = await db.execute(
                select(FeedbackRecord).where(
                    FeedbackRecord.report_id == report_id,
                    FeedbackRecord.user_id == user_id,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                # 更新
                existing.is_correct = req.is_correct
                existing.comment = req.comment
                existing.status = "archived" if req.is_correct else "manual_review"
                await db.commit()
                await db.refresh(existing)
                feedback_id = existing.id
            else:
                # 新建
                feedback = FeedbackRecord(
                    report_id=report_id,
                    user_id=user_id,
                    is_correct=req.is_correct,
                    comment=req.comment,
                    status="archived" if req.is_correct else "manual_review",
                )
                db.add(feedback)
                await db.commit()
                await db.refresh(feedback)
                feedback_id = feedback.id

            return {
                "feedback_id": feedback_id,
                "is_correct": req.is_correct,
                "data_flywheel_action": "archived" if req.is_correct else "manual_review",
            }

    # =================================================================
    # 标注视频
    # =================================================================

    @staticmethod
    async def get_annotated_video(user_id: int, report_id: int) -> dict:
        """获取标注视频 URL"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.user_id == user_id,
                )
            )
            report = result.scalar_one_or_none()
            if report is None:
                raise AppException("分析报告不存在", 404, code=ERR_REPORT_NOT_FOUND)

            if not report.annotated_video_url:
                raise AppException("标注视频尚未生成", 404, code=ERR_REPORT_NOT_FOUND)

            # 查询时长
            task_result = await db.execute(
                select(VideoTask.duration_sec).where(VideoTask.id == report.task_id)
            )
            duration = task_result.scalar_one_or_none()

            return {
                "annotated_video_url": report.annotated_video_url,
                "duration_sec": duration,
            }

    # =================================================================
    # 分享
    # =================================================================

    @staticmethod
    async def create_share(user_id: int, report_id: int) -> dict:
        """创建分享"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.user_id == user_id,
                )
            )
            report = result.scalar_one_or_none()
            if report is None:
                raise AppException("分析报告不存在", 404, code=ERR_REPORT_NOT_FOUND)

            # 分享次数限制
            await VideoAnalysisService._check_share_limit(user_id)

            # 创建分享记录
            share_token = uuid.uuid4().hex
            now = datetime.now(timezone.utc)
            share = ShareRecord(
                report_id=report_id,
                user_id=user_id,
                share_token=share_token,
                share_scope="public",
                expire_at=now + timedelta(days=VideoAnalysisService.SHARE_EXPIRE_DAYS),
            )
            db.add(share)
            await db.commit()
            await db.refresh(share)

            share_url = f"/share/{share_token}"

            return {
                "share_url": share_url,
                "card_image_url": report.cover_image_url,
                "expire_at": share.expire_at.isoformat(),
            }

    @staticmethod
    async def get_shared_report(share_token: str) -> dict:
        """获取公开分享报告摘要"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(ShareRecord).where(ShareRecord.share_token == share_token)
            )
            share = result.scalar_one_or_none()
            if share is None:
                raise AppException("分享链接无效或已过期", 404, code=ERR_SHARE_TOKEN_INVALID)

            # 检查过期
            if share.expire_at < datetime.now(timezone.utc):
                raise AppException("分享链接已过期", 404, code=ERR_SHARE_TOKEN_INVALID)

            # 查询报告
            report_result = await db.execute(
                select(AnalysisReport).where(AnalysisReport.id == share.report_id)
            )
            report = report_result.scalar_one_or_none()
            if report is None:
                raise AppException("报告不存在", 404, code=ERR_REPORT_NOT_FOUND)

            # 更新浏览数
            await db.execute(
                update(ShareRecord)
                .where(ShareRecord.id == share.id)
                .values(view_count=ShareRecord.view_count + 1)
            )
            await db.commit()

            # 返回安全字段（不含训练建议/趋势/个人信息）
            report_text = report.report_text or {}
            safe_text = {
                "summary": report_text.get("summary", ""),
                "issues": report_text.get("issues", [])[:2],
            }

            return {
                "report_id": report.id,
                "cover_image_url": report.cover_image_url,
                "annotated_video_url": report.annotated_video_url,
                "result_data": report.result_data,
                "report_text": safe_text,
                "created_at": report.created_at.isoformat() if report.created_at else None,
            }

    # =================================================================
    # 辅助方法
    # =================================================================

    @staticmethod
    async def _get_file_record(file_id: int, user_id: int, db: AsyncSession) -> FileRecord:
        """获取文件记录或 404"""
        result = await db.execute(
            select(FileRecord).where(
                FileRecord.id == file_id, FileRecord.user_id == user_id
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise AppException("文件记录不存在", 404, code=ERR_FILE_NOT_FOUND)
        return record

    @staticmethod
    async def _check_free_quota(user_id: int) -> None:
        """
        免费配额检查 — Redis INCR。
        会员跳过（S5 实现）。
        """
        redis = await get_redis()
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"quota:analysis:{user_id}:{today}"
        count = await redis.incr(key)

        if count == 1:
            # 当天第一次，设置 TTL 到当天结束
            import calendar
            now = datetime.now(timezone.utc)
            end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=timezone.utc)
            ttl = int((end_of_day - now).total_seconds()) + 3600  # +1h buffer
            await redis.expire(key, ttl)

        if count > VideoAnalysisService.FREE_DAILY_LIMIT:
            # 超额回滚
            await redis.decr(key)
            raise AppException(
                "今日免费分析次数已用完",
                429,
                code=ERR_QUOTA_EXHAUSTED,
            )

    @staticmethod
    async def _check_share_limit(user_id: int) -> None:
        """分享次数限制"""
        redis = await get_redis()
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"share:count:{user_id}:{today}"
        count = await redis.incr(key)

        if count == 1:
            now = datetime.now(timezone.utc)
            end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=timezone.utc)
            ttl = int((end_of_day - now).total_seconds()) + 3600
            await redis.expire(key, ttl)

        if count > VideoAnalysisService.SHARE_DAILY_LIMIT:
            await redis.decr(key)
            raise AppException(
                "今日分享次数已用完",
                429,
                code=ERR_QUOTA_EXHAUSTED,
            )
