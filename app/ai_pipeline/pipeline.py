"""
app/ai_pipeline/pipeline.py — 流水线编排器

依据：切片 13-infrastructure/ai_pipeline.md §5.6
功能：初始化步骤记录 + 启动 Celery 任务
Phase 1：顺序执行（parallel 优化留 S6）
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import update

from app.core.celery import celery_app
from app.core.database import async_session_factory
from app.models.video_analysis import PipelineStep, VideoTask
from app.ai_pipeline.tasks import run_pipeline, run_pipeline_async

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """流水线编排器"""

    STEP_NAMES = [
        (1, "video_preprocessing"),
        (2, "table_detection"),
        (3, "ball_detection"),
        (4, "ball_tracking"),
        (5, "landing_estimation"),
        (6, "pose_estimation"),
        (7, "action_recognition"),
        (8, "rally_segmentation"),
        (9, "report_generation"),
        (10, "annotated_video"),
    ]

    @staticmethod
    async def init_steps(task_id: int) -> None:
        """初始化 10 条 pipeline_step 记录"""
        async with async_session_factory() as db:
            for step_num, step_name in PipelineOrchestrator.STEP_NAMES:
                step = PipelineStep(
                    task_id=task_id,
                    step_number=step_num,
                    step_name=step_name,
                    status="pending",
                )
                db.add(step)
            await db.commit()

    @staticmethod
    async def build_and_run(task_id: int, oss_key: str) -> str:
        """
        构建并执行流水线。
        Phase 1：顺序执行（run_pipeline_async 单任务内顺序跑 10 步）。
        eager 模式：直接 await 异步函数（避免事件循环嵌套）
        生产模式：apply_async 异步派发
        返回 Celery task id（eager 模式返回 "eager"）
        """
        await PipelineOrchestrator.init_steps(task_id)

        # 更新任务状态为 processing
        async with async_session_factory() as db:
            await db.execute(
                update(VideoTask)
                .where(VideoTask.id == task_id)
                .values(status="processing")
            )
            await db.commit()

        if celery_app.conf.task_always_eager:
            # eager 模式：直接 await（同一事件循环内）
            await run_pipeline_async(task_id, oss_key)
            return "eager"
        else:
            # 生产模式：异步派发 Celery 任务
            result = run_pipeline.apply_async(args=[task_id, oss_key])
            return result.id
