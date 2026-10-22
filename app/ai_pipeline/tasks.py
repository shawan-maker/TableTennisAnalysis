"""
app/ai_pipeline/tasks.py — 10 步 AI 推理流水线 Celery 任务

依据：切片 13-infrastructure/ai_pipeline.md §5.2
Phase 1：Step 4/5/8 为 placeholder，Step 7 为 Phase 2
Mock 模式：AI_INFERENCE_MOCK=True 时返回模拟数据
"""

import asyncio
import concurrent.futures
import logging
import time
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import update

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.video_analysis import AnalysisReport, PipelineStep, VideoTask
from app.ai_pipeline.progress import ProgressTracker
from app.ai_pipeline.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 Celery 任务中运行异步协程 — 兼容 eager 模式下的事件循环嵌套"""
    try:
        asyncio.get_running_loop()
        # 已有运行中的事件循环（pytest-asyncio / uvicorn eager），在新线程中运行
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # 无运行中的事件循环，直接 asyncio.run
        return asyncio.run(coro)


async def run_pipeline_async(task_id: int, oss_key: str) -> None:
    """
    流水线异步执行 — Phase 1 顺序执行 10 步。
    每步更新 pipeline_step 状态 + video_task 进度 + WS 推送。
    """
    step_results = {}

    # Step 1: 视频预处理
    await _exec_step(task_id, 1, "video_preprocessing",
                     lambda: _mock_step_1(oss_key=oss_key), step_results)

    # Step 2: 球台检测
    await _exec_step(task_id, 2, "table_detection",
                     lambda: _mock_step_2(oss_key=oss_key), step_results)

    # Step 3: 球体检测
    await _exec_step(task_id, 3, "ball_detection",
                     lambda: _mock_step_3(oss_key=oss_key), step_results)

    # Step 4: 球体追踪 (Phase 1 placeholder)
    await _exec_step(task_id, 4, "ball_tracking",
                     lambda: _mock_step_4(), step_results)

    # Step 5: 落点估算 (Phase 1 placeholder)
    await _exec_step(task_id, 5, "landing_estimation",
                     lambda: _mock_step_5(), step_results)

    # Step 6: 姿态估计 (Phase 1 basic)
    await _exec_step(task_id, 6, "pose_estimation",
                     lambda: _mock_step_6(oss_key=oss_key), step_results)

    # Step 7: 动作识别 (Phase 2)
    await _exec_step(task_id, 7, "action_recognition",
                     lambda: _mock_step_7(), step_results)

    # Step 8: 回合分割 (Phase 1 placeholder)
    await _exec_step(task_id, 8, "rally_segmentation",
                     lambda: _mock_step_8(), step_results)

    # Step 9: 报告生成
    await _exec_step(task_id, 9, "report_generation", None, step_results)
    report_data = await ReportGenerator.generate(task_id, step_results)
    report_id = report_data["report_id"]
    step_results[9] = report_data

    # Step 10: 标注视频生成
    await _exec_step(task_id, 10, "annotated_video",
                     lambda: _mock_step_10(oss_key=oss_key), step_results)

    # 更新报告标注视频 URL + 任务完成
    async with async_session_factory() as db:
        mock_url = step_results.get(10, {}).get("annotated_video_url", "")
        await db.execute(
            update(AnalysisReport)
            .where(AnalysisReport.task_id == task_id)
            .values(annotated_video_url=mock_url)
        )
        await db.execute(
            update(VideoTask)
            .where(VideoTask.id == task_id)
            .values(
                status="completed",
                progress=100,
                current_step=10,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    # WS 推送完成
    await ProgressTracker.on_task_complete(task_id, report_id)


@shared_task(bind=True, name="ai_pipeline.run_pipeline", max_retries=1, default_retry_delay=30)
def run_pipeline(self, task_id: int, oss_key: str):
    """Celery 任务入口 — 非生产环境通过 _run_async 运行异步逻辑"""
    try:
        _run_async(run_pipeline_async(task_id, oss_key))
    except Exception as e:
        logger.error("pipeline_failed", extra={"task_id": task_id, "error": str(e)})
        _run_async(_mark_task_failed(task_id, str(e)))
        raise


async def _mark_task_failed(task_id: int, error: str):
    """标记任务失败"""
    async with async_session_factory() as db:
        await db.execute(
            update(VideoTask)
            .where(VideoTask.id == task_id)
            .values(status="failed", error_message=error)
        )
        await db.commit()


async def _exec_step(task_id: int, step: int, step_name: str, mock_fn, step_results: dict):
    """执行单步：更新状态 -> 执行 -> 记录结果"""
    start = time.time()

    async with async_session_factory() as db:
        await ProgressTracker.on_step_start(task_id, step, db)

    try:
        if mock_fn:
            result = mock_fn()
        else:
            result = {}
        step_results[step] = result
    except Exception as e:
        await ProgressTracker.on_step_failed(task_id, step, str(e))
        raise

    duration_ms = int((time.time() - start) * 1000)
    await ProgressTracker.on_step_complete(task_id, step, result, duration_ms)


# =============================================================================
# Mock 数据生成函数
# =============================================================================

def _mock_step_1(oss_key: str = "", **kw):
    return {
        "video_info": {"duration_sec": 60, "fps": 30, "resolution": "1920x1080"},
        "cover_image_url": f"http://localhost:3000/mock-oss/covers/{oss_key.split('/')[-1]}.jpg",
    }


def _mock_step_2(oss_key: str = "", **kw):
    return {
        "corners": [{"x": 100, "y": 200}, {"x": 1800, "y": 200}, {"x": 1800, "y": 900}, {"x": 100, "y": 900}],
        "homography": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    }


def _mock_step_3(oss_key: str = "", **kw):
    return {
        "frames": [{"frame_id": i, "boxes": [{"x": 960, "y": 540, "w": 10, "h": 10, "conf": 0.95}]} for i in range(0, 1800, 30)],
    }


def _mock_step_4(**kw):
    return {
        "trajectory": [{"frame": i, "x": 960 + i * 0.5, "y": 540 - i * 0.3} for i in range(0, 60, 2)],
        "ball_speed": {"avg_speed_mps": 18.5, "max_speed_mps": 25.3, "speed_range": [15.2, 22.1]},
    }


def _mock_step_5(**kw):
    return {
        "landing_points": {
            "nine_grid": [[2, 5, 3], [4, 8, 6], [1, 3, 2]],
            "distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07},
            "heatmap_data": [[0]*9]*6,
        },
    }


def _mock_step_6(oss_key: str = "", **kw):
    return {
        "keypoints": [{"frame_id": i, "keypoints": [[320, 240, 0.9]] * 33} for i in range(0, 1800, 60)],
    }


def _mock_step_7(**kw):
    return {
        "actions": [
            {"frame_range": [0, 600], "label": "forehand_drive", "conf": 0.92},
            {"frame_range": [600, 1200], "label": "backhand_drive", "conf": 0.88},
            {"frame_range": [1200, 1800], "label": "serve", "conf": 0.95},
        ],
        "technique_stats": {"forehand_drive": 45, "backhand_drive": 18, "forehand_loop": 12, "serve": 23},
    }


def _mock_step_8(**kw):
    return {
        "rally_analysis": {"total_rallies": 23, "avg_rally_length": 5.2, "max_rally_length": 18},
        "rallies": [{"start_frame": 0, "end_frame": 180, "length": 6}],
    }


def _mock_step_10(oss_key: str = "", **kw):
    return {
        "annotated_video_url": f"http://localhost:3000/mock-oss/annotated/{oss_key.split('/')[-1]}",
    }
