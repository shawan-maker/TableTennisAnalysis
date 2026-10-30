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

# R12-VA-2: 任务状态机合法转换矩阵（设计文档 03-video_analysis/backend.md）
# queued→failed：流水线启动失败（Celery 入队异常）为合法转换（R12 复验补充，
# 消除 video_analysis_service 启动失败旁路直写 status 绕过矩阵校验）
TASK_TRANSITIONS = {
    "queued":     {"processing", "cancelled", "failed"},
    "processing": {"completed", "failed"},
    "completed":  set(),  # 终态
    "failed":     {"queued"},  # 可重试
    "cancelled":  set(),  # 终态
}


async def transition_task_status(db: AsyncSession, task_id: int, target: str) -> bool:
    """
    R12-VA-2: 任务状态机转换校验。

    校验 current → target 是否合法：
    - 合法：更新 status（completed/failed 同时写 completed_at），flush 后返回 True
    - 非法（含任务不存在）：记录警告日志，不改状态，返回 False

    调用方根据返回值决定后续动作（推送 WS / 中止流水线等）。
    """
    task = await db.get(VideoTask, task_id)
    if task is None:
        logger.warning("transition_task_status: task %s not found", task_id)
        return False
    current = task.status
    if target not in TASK_TRANSITIONS.get(current, set()):
        logger.warning(
            "invalid task status transition skipped: task=%s %s -> %s",
            task_id, current, target,
        )
        return False
    task.status = target
    if target in ("completed", "failed"):
        task.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return True


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
            # R12-VA-2: processing → failed 需状态机校验（终态任务不再翻转）
            allowed = await transition_task_status(db, task_id, "failed")
            if allowed:
                task = await db.get(VideoTask, task_id)
                if task:
                    task.error_message = error
                    await db.flush()
            await db.commit()

            if not allowed:
                return

            # WS 推送 + 离线兜底（R13-AIP-2 同型修复：失败通知离线用户落 DB）
            task = await db.get(VideoTask, task_id)
            if task:
                if await NotificationService.is_user_online(task.user_id):
                    await NotificationService.push_ws_message(
                        task.user_id,
                        "analysis_failed",
                        {"task_id": task_id, "step": step, "error": error},
                    )
                else:
                    try:
                        await NotificationService.send_notification(
                            task.user_id,
                            "analysis_failed",
                            "视频分析失败",
                            "很抱歉，您的视频分析未成功完成，分析额度已退还",
                            extra_data={"task_id": task_id, "step": step},
                        )
                    except Exception as e:
                        logger.warning("analysis_failed_offline_notify_failed", extra={
                            "task_id": task_id, "user_id": task.user_id, "error": str(e),
                        })

    @staticmethod
    async def on_task_complete(task_id: int, report_id: int) -> None:
        """任务完成"""
        async with async_session_factory() as db:
            # R12-VA-2: processing → completed 需状态机校验（终态任务不再翻转）
            allowed = await transition_task_status(db, task_id, "completed")
            if allowed:
                task = await db.get(VideoTask, task_id)
                if task:
                    task.progress = 1.0
                    task.current_step = 10
                    await db.flush()
            await db.commit()

            if not allowed:
                return

            # WS 推送 + 离线兜底（R13-AIP-2: 设计 §5.4 级联第 4 步 —
            # 在线 → WS 实时推送（保留 analysis_complete 事件契约）；
            # 离线 → NotificationService.send_notification 落 DB + 未读计数
            # + 微信订阅消息，用户下次打开小程序经通知列表触达）
            task = await db.get(VideoTask, task_id)
            if task:
                if await NotificationService.is_user_online(task.user_id):
                    await NotificationService.push_ws_message(
                        task.user_id,
                        "analysis_complete",
                        {"task_id": task_id, "report_id": report_id},
                    )
                else:
                    try:
                        await NotificationService.send_notification(
                            task.user_id,
                            "analysis_complete",
                            "视频分析完成",
                            "您的视频分析报告已生成，点击查看分析详情",
                            extra_data={"task_id": task_id, "report_id": report_id},
                        )
                    except Exception as e:
                        logger.warning("analysis_complete_offline_notify_failed", extra={
                            "task_id": task_id, "user_id": task.user_id, "error": str(e),
                        })

    @staticmethod
    def _calc_progress(step: int, step_progress: int) -> float:
        """计算总进度（0.0-1.0）"""
        total_weight = sum(STEP_WEIGHTS.values())
        if total_weight <= 0:
            return 0.0
        completed_weight = sum(STEP_WEIGHTS.get(i, 0) for i in range(1, step))
        current_weight = STEP_WEIGHTS.get(step, 0) * step_progress / 100
        return min(1.0, round((completed_weight + current_weight) / total_weight, 2))
