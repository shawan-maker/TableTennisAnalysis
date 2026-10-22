"""
app/ai_pipeline/progress.py — 流水线进度追踪

依据：切片 13-infrastructure/ai_pipeline.md §5.4
功能：步骤开始/完成/失败 → 更新 DB + WS 推送
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.video_analysis import PipelineStep, VideoTask
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


# 步骤中文名 — 用于 WS 推送
STEP_MESSAGES = {
    1: "视频预处理中",
    2: "球台检测中",
    3: "球体检测中",
    4: "球体追踪中",
    5: "落点估算中",
    6: "姿态估计中",
    7: "动作识别中",
    8: "回合分割中",
    9: "报告生成中",
    10: "标注视频生成中",
}

# 步骤权重（用于进度计算）
STEP_WEIGHTS = {1: 10, 2: 5, 3: 15, 4: 10, 5: 5, 6: 10, 7: 10, 8: 5, 9: 20, 10: 10}


class ProgressTracker:
    """流水线进度追踪器"""

    @staticmethod
    async def on_step_start(task_id: int, step: int, db: AsyncSession) -> None:
        """步骤开始 — 更新状态 + WS 推送"""
        now = datetime.now(timezone.utc)

        # 更新 pipeline_step
        await db.execute(
            update(PipelineStep)
            .where(PipelineStep.task_id == task_id, PipelineStep.step_number == step)
            .values(status="running", started_at=now)
        )

        # 更新 video_task
        await db.execute(
            update(VideoTask)
            .where(VideoTask.id == task_id)
            .values(
                current_step=step,
                step_name=STEP_MESSAGES.get(step, f"step_{step}"),
            )
        )
        await db.commit()

        # WS 推送
        task = await db.get(VideoTask, task_id)
        if task:
            await NotificationService.push_ws_message(
                task.user_id,
                "analysis_progress",
                {
                    "task_id": task_id,
                    "step": step,
                    "step_name": STEP_MESSAGES.get(step, f"step_{step}"),
                    "progress": ProgressTracker._calc_progress(step, 0),
                },
            )

    @staticmethod
    async def on_step_complete(
        task_id: int, step: int, step_result: dict, duration_ms: int
    ) -> None:
        """步骤完成"""
        now = datetime.now(timezone.utc)
        async with async_session_factory() as db:
            await db.execute(
                update(PipelineStep)
                .where(PipelineStep.task_id == task_id, PipelineStep.step_number == step)
                .values(
                    status="completed",
                    step_result=step_result,
                    duration_ms=duration_ms,
                    completed_at=now,
                )
            )

            progress = ProgressTracker._calc_progress(step, 100)
            await db.execute(
                update(VideoTask)
                .where(VideoTask.id == task_id)
                .values(progress=progress)
            )
            await db.commit()

            # WS 推送
            task = await db.get(VideoTask, task_id)
            if task:
                await NotificationService.push_ws_message(
                    task.user_id,
                    "analysis_progress",
                    {
                        "task_id": task_id,
                        "step": step,
                        "step_name": STEP_MESSAGES.get(step, f"step_{step}"),
                        "progress": progress,
                        "completed": True,
                    },
                )

    @staticmethod
    async def on_step_failed(task_id: int, step: int, error: str) -> None:
        """步骤失败"""
        now = datetime.now(timezone.utc)
        async with async_session_factory() as db:
            await db.execute(
                update(PipelineStep)
                .where(PipelineStep.task_id == task_id, PipelineStep.step_number == step)
                .values(status="failed", error_message=error, completed_at=now)
            )
            await db.execute(
                update(VideoTask)
                .where(VideoTask.id == task_id)
                .values(status="failed", error_message=error)
            )
            await db.commit()

            # WS 推送
            task = await db.get(VideoTask, task_id)
            if task:
                await NotificationService.push_ws_message(
                    task.user_id,
                    "analysis_failed",
                    {"task_id": task_id, "step": step, "error": error},
                )

    @staticmethod
    async def on_task_complete(task_id: int, report_id: int) -> None:
        """任务完成"""
        now = datetime.now(timezone.utc)
        async with async_session_factory() as db:
            await db.execute(
                update(VideoTask)
                .where(VideoTask.id == task_id)
                .values(
                    status="completed",
                    progress=100,
                    current_step=10,
                    completed_at=now,
                )
            )
            await db.commit()

            # WS 推送
            task = await db.get(VideoTask, task_id)
            if task:
                await NotificationService.push_ws_message(
                    task.user_id,
                    "analysis_complete",
                    {"task_id": task_id, "report_id": report_id},
                )

    @staticmethod
    def _calc_progress(step: int, step_progress: int) -> int:
        """计算总进度（0-100）"""
        completed_weight = sum(STEP_WEIGHTS.get(i, 0) for i in range(1, step))
        current_weight = STEP_WEIGHTS.get(step, 0) * step_progress / 100
        return min(100, int(completed_weight + current_weight))
