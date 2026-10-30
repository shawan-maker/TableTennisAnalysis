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
    ERR_NOT_FOUND,
    ERR_QUOTA_EXHAUSTED,
    ERR_REPORT_NOT_FOUND,
    ERR_SHARE_TOKEN_INVALID,
    ERR_VALIDATION,
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
from app.services.membership_service import MembershipService

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
        # R12-VA-4: API §4.1 错误表 — 类型不支持/文件过大均为 400，文件过小为 422
        if not FileService.validate_file_type(req.filename):
            raise AppException("仅支持 MP4/MOV 格式", 400, code=ERR_BAD_REQUEST)

        # 2. 验证文件大小 — 过大 400 / 过小 422（消息对齐 API §4.1）
        if req.file_size > settings.MAX_FILE_SIZE:
            raise AppException("视频文件不能超过 500MB", 400, code=ERR_BAD_REQUEST)
        if req.file_size < settings.MIN_FILE_SIZE:
            raise AppException("视频文件不能小于 1MB", 422, code=ERR_VALIDATION)

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
                # R12-VA-5: API §4.2 错误表 — OSS 文件不存在为 404（原 400 偏差）
                raise AppException("未检测到上传的文件，请重新上传", 404, code=ERR_NOT_FOUND)

            # 文件大小校验 — 实际大小必须与声明一致
            actual_size = head.get("content_length", 0)
            if actual_size != record.file_size:
                raise AppException("上传文件大小与声明不符", 400, code=ERR_BAD_REQUEST)

            # 获取视频时长
            duration_sec = FileService.get_video_duration(record.oss_key)

            # 时长校验（5s ~ 600s）— duration_sec 为 None 或 0 时拒绝确认
            # R6-Video-1: 使用两条独立错误消息 + code=42200 (ERR_VALIDATION)
            if not duration_sec or duration_sec < settings.MIN_VIDEO_DURATION:
                raise AppException(
                    f"视频时长过短，需至少 {settings.MIN_VIDEO_DURATION}s",
                    422,
                    code=ERR_VALIDATION,
                )
            if duration_sec > settings.MAX_VIDEO_DURATION:
                raise AppException(
                    f"视频时长过长，不能超过 {settings.MAX_VIDEO_DURATION}s",
                    422,
                    code=ERR_VALIDATION,
                )

            # 更新 file_record
            # R12-VA-6: duration_sec 不入 file_record（DB 设计 §2.4/切片模型均无此列），
            # 在响应中返回，create_task 时写入 video_task.duration_sec（ai_pipeline 读取源）
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

            # oss_key 二次校验
            if req.oss_key != record.oss_key:
                raise AppException("oss_key 与文件记录不匹配", 400, code=ERR_BAD_REQUEST)

            # 会员状态检查 + 免费配额检查（会员跳过）
            membership = await MembershipService.check_membership(db, user_id)
            if not membership.is_member:
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
                progress=0.0,
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
            # R12 复验-VA-2 旁路收口：改走 transition_task_status 状态矩阵校验
            # （queued→failed 已补充为合法转换），不再直接 update 绕过校验
            async with async_session_factory() as db:
                from app.ai_pipeline.progress import transition_task_status
                allowed = await transition_task_status(db, task.id, "failed")
                if allowed:
                    failed_task = await db.get(VideoTask, task.id)
                    if failed_task:
                        failed_task.error_message = f"流水线启动失败: {e}"
                        await db.flush()
                await db.commit()

            # R12-AIPipeline-2: 启动失败同样退还免费额度（额度已在请求时预扣，
            # 任务未进入 Celery 重试流程，需在此直接退还）
            try:
                from app.ai_pipeline.tasks import _refund_free_quota
                await _refund_free_quota(user_id)
            except Exception as quota_err:
                logger.error(
                    "startup_refund_quota_failed",
                    extra={"user_id": user_id, "error": str(quota_err)},
                )

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
                    select(
                        AnalysisReport.task_id,
                        AnalysisReport.id,
                        AnalysisReport.cover_image_url,
                    ).where(AnalysisReport.task_id.in_(task_ids))
                )
                report_map = {
                    row[0]: {"report_id": row[1], "cover_image_url": row[2]}
                    for row in report_result
                }
            else:
                report_map = {}

            items = [
                {
                    "task_id": t.id,
                    "task_uuid": t.task_uuid,
                    "status": t.status,
                    "current_step": t.current_step,
                    "total_steps": t.total_steps,
                    "progress": t.progress,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "report_id": report_map.get(t.id, {}).get("report_id"),
                    "cover_image_url": report_map.get(t.id, {}).get("cover_image_url"),
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
                "task_id": task.id,
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
                    "report_summary": (
                        r.report_text.get("summary")
                        if isinstance(r.report_text, dict) else None
                    ),
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

            # is_readonly 通过 Redis 降级标记判断（会员到期权限降级）
            redis = await get_redis()
            readonly = await redis.get(f"downgrade:report:readonly:{user_id}")
            is_readonly = readonly is not None

            return {
                "id": report.id,
                "task_id": report.task_id,
                "task_uuid": task_uuid,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "is_llm_generated": report.is_llm_generated,
                "is_readonly": is_readonly,
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

            # 数据飞轮：is_correct=True 时归档样本用于训练
            if req.is_correct:
                try:
                    await FileService.archive_for_training(report_id, report.task_id)
                except AttributeError:
                    # FileService 尚未实现 archive_for_training 方法
                    # TODO: S6+ 实现 FileService.archive_for_training 后移除此分支
                    logger.warning("FileService.archive_for_training not implemented")
                except Exception as e:
                    logger.error("archive_for_training_failed", extra={
                        "error": str(e), "report_id": report_id
                    })

            # 游戏化积分（try/except 不阻塞主流程）
            try:
                from app.services.gamification_service import GamificationService
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="feedback", ref_id=feedback_id
                )
            except Exception as e:
                logger.warning("feedback_add_points_failed", extra={
                    "error": str(e), "feedback_id": feedback_id
                })

            return {
                "feedback_id": feedback_id,
                "is_correct": req.is_correct,
                "data_flywheel_action": "archived" if req.is_correct else "manual_review",
            }

    @staticmethod
    async def list_feedbacks(
        user_id: int, report_id: int, page: int, page_size: int
    ) -> dict:
        """获取报告的反馈历史（分页）"""
        async with async_session_factory() as db:
            # 验证报告存在且属于当前用户
            report_result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.user_id == user_id,
                )
            )
            report = report_result.scalar_one_or_none()
            if report is None:
                raise AppException("分析报告不存在", 404, code=ERR_REPORT_NOT_FOUND)

            # 计数
            count_qs = select(func.count()).select_from(FeedbackRecord).where(
                FeedbackRecord.report_id == report_id
            )
            count_result = await db.execute(count_qs)
            total = count_result.scalar() or 0

            # 分页查询反馈记录
            fb_result = await db.execute(
                select(FeedbackRecord)
                .where(FeedbackRecord.report_id == report_id)
                .order_by(FeedbackRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            feedbacks = fb_result.scalars().all()

            # 获取报告标题
            report_text = report.report_text or {}
            report_title = report_text.get("summary", "") if isinstance(report_text, dict) else ""

            items = [
                {
                    "id": fb.id,
                    "report_id": fb.report_id,
                    "report_title": report_title,
                    "is_correct": fb.is_correct,
                    "comment": fb.comment,
                    "status": fb.status,
                    "created_at": fb.created_at.isoformat() if fb.created_at else None,
                }
                for fb in feedbacks
            ]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
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
                "url": report.annotated_video_url,
                "duration_sec": duration,
                "quality_options": ["480p", "720p", "1080p"],
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

            share_url = f"{settings.API_BASE_URL}/share/{share_token}"

            # 游戏化积分（try/except 不阻塞主流程）
            try:
                from app.services.gamification_service import GamificationService
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="share", ref_id=share.id
                )
            except Exception as e:
                logger.warning("share_add_points_failed", extra={
                    "error": str(e), "share_id": share.id
                })

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

            # result_data 仅返回安全子集（不含个人信息/训练建议）
            safe_keys = ("technique_stats", "landing_points", "ball_speed")
            safe_result_data = {
                k: report.result_data.get(k)
                for k in safe_keys
                if report.result_data and k in report.result_data
            }

            return {
                "report_id": report.id,
                "cover_image_url": report.cover_image_url,
                "annotated_video_url": report.annotated_video_url,
                "result_data": safe_result_data,
                "report_text": safe_text,  # 向后兼容
                "report_summary": safe_text.get("summary", ""),
                "top_issues": safe_text.get("issues", []),
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
        使用 CST（UTC+8）日期作为 key，避免跨日边界错误。
        """
        redis = await get_redis()
        tz_cst = timezone(timedelta(hours=8))
        today = datetime.now(tz_cst).strftime("%Y%m%d")
        key = f"quota:analysis:{user_id}:{today}"
        count = await redis.incr(key)

        if count == 1:
            # 当天第一次，设置 TTL 到当天结束
            now = datetime.now(tz_cst)
            end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=tz_cst)
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
        """分享次数限制 — 使用 CST 日期作为 key"""
        redis = await get_redis()
        tz_cst = timezone(timedelta(hours=8))
        today = datetime.now(tz_cst).strftime("%Y%m%d")
        key = f"share:count:{user_id}:{today}"
        count = await redis.incr(key)

        if count == 1:
            now = datetime.now(tz_cst)
            end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=tz_cst)
            ttl = int((end_of_day - now).total_seconds()) + 3600
            await redis.expire(key, ttl)

        if count > VideoAnalysisService.SHARE_DAILY_LIMIT:
            await redis.decr(key)
            raise AppException(
                "今日分享次数已用完",
                429,
                code=ERR_QUOTA_EXHAUSTED,
            )
