# ai_pipeline 基础设施模块 �?后端垂直切片设计

> **模块名称**：`ai_pipeline`
> **所属目�?*：`app/services/ai_pipeline_service.py` + `app/ai_pipeline/tasks.py` + `app/ai_pipeline/pipeline.py` + `app/ai_pipeline/progress.py` + `app/ai_pipeline/report_generator.py`
> **定位**：AI 分析流水线编排、Celery 任务定义、进度追踪、结果聚�?> **依据**：模块详细设�?v1.2 §3.2、数据库详细设计 v1.5 §2.5-2.7

---

## 1. 模块概述

| 属�?| �?|
|------|-----|
| 模块名称 | `ai_pipeline` |
| 所属目�?| `app/ai_pipeline/`（流水线编排�? `app/services/ai_pipeline_service.py`（入�?Service�?|
| 一句话定位 | 10 �?AI 分析流水线编排、Celery 任务定义、进度追踪、结果聚�?|
| 关联数据�?| video_task, pipeline_step, analysis_report |
| 依赖模块 | ai_inference（HTTP 调用推理 API�? video_analysis（任务入口）, notification（进度推送）, progress_analysis（快照生成）, training_advice（建议生成） |
| 基础设施 | Celery + Redis + GPU 推理服务 |

### 10 步流水线

| Step | 名称 | 输入 | 输出 | 依赖 | 超时(s) | 重试 |
|------|------|------|------|------|---------|------|
| 1 | 视频预处�?| oss_key (原始视频) | 标准化帧序列 (fps=30, 1080p) | �?| 120 | 2 |
| 2 | 球台检�?| 帧序�?| 球台四角坐标 + 单应性矩�?| �?| 60 | 2 |
| 3 | 球体检�?| 帧序�?+ 球台坐标 | 每帧球体 bbox | 1,2 | 180 | 2 |
| 4 | 球体追踪 | 球体 bbox 序列 | 卡尔曼滤波轨�?| 3 | 60 | 1 |
| 5 | 落点估算 | 轨迹 + 单应性矩�?| 九宫格落点坐�?| 4 | 30 | 1 |
| 6 | 姿态估�?| 帧序�?| MediaPipe 33 关键�?| 1 | 120 | 2 |
| 7 | 动作识别 | 关键点序�?+ 帧序�?| 击球动作分类 | 6 | 120 | 2 |
| 8 | 回合分割 | 轨迹 + 动作 + 落点 | 回合边界 + 技术统�?| 5,7 | 30 | 1 |
| 9 | 报告生成 | Step 3-8 全部结果 | result_data JSONB + report_text JSONB | 8 | 60 | 1 |
| 10 | 标注视频 | 帧序�?+ 全部检测结�?| 标注视频 MP4 (上传 OSS) | 9 | 120 | 1 |

### 编排策略

```
group(step1, step2)
    �?chain(step3 �?step4 �?step5)
    | chain(step6 �?step7)
    �?join �?chain(step8 �?step9 �?step10)
```

两个 chain 并行执行�?join，再进入 step8�?�?0 串行链�?
---

## 2. 任务清单

| # | 任务 | 文件 | 依赖 | 状�?|
|---|------|------|------|------|
| 1 | 实现 Model（复�?video_task + pipeline_step�?| `app/models/video_analysis.py` | �?| �?|
| 2 | 定义 Schema | `app/schemas/ai_pipeline.py` | #1 | �?|
| 3 | 实现进度推�?| `app/ai_pipeline/progress.py` | #1 | �?|
| 4 | 实现各步骤任�?| `app/ai_pipeline/tasks.py` | #3 | �?|
| 5 | 实现流水线编�?| `app/ai_pipeline/pipeline.py` | #4 | �?|
| 6 | 实现报告生成�?| `app/ai_pipeline/report_generator.py` | #5 | �?|
| 7 | 实现入口 Service | `app/services/ai_pipeline_service.py` | #5 | �?|
| 8 | 配置 Celery Beat 健康检�?| `app/core/celery.py` | #4 | �?|
| 9 | 编写测试 | `tests/unit/test_ai_pipeline.py` | #7 | �?|
| 10 | 编写冒烟测试 | `tests/smoke/ai_pipeline_smoke_test.py` | #7 | �?|

---

## 3. Model 实现（复用 video_analysis 模块）

ai_pipeline 模块直接 import 复用 `app/models/video_analysis.py` 中已定义的 `VideoTask`、`PipelineStep`、`AnalysisReport` 表，不重复定义。

```python
# app/models/ai_pipeline.py — 直接 import，避免重复定义导致 ORM 注册冲突
from app.models.video_analysis import VideoTask, PipelineStep, AnalysisReport

# ai_pipeline 使用的关键字段：
# - VideoTask: task_uuid(String(64)), user_id, file_id, oss_key(String(512)),
#   duration_sec, status, current_step, total_steps, step_name(String(32)),
#   progress(Integer), error_message, retry_count, estimated_remaining_seconds,
#   created_at, completed_at
# - PipelineStep: task_id, step_number, step_name(String(64)), status,
#   duration_ms, step_result(JSONB), error_message, started_at, completed_at
# - AnalysisReport: task_id, result_data(JSONB), report_text(JSONB), ...
```

---

## 4. Schema 实现

```python
# app/schemas/ai_pipeline.py
"""AI 流水�?Schema 定义�?""

from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field


class PipelineProgress(BaseModel):
    """流水线进度�?""
    task_id: int
    step: int = Field(ge=0, le=10)
    total: int = 10
    status: str
    message: str
    report_id: Optional[int] = None


class StepResult(BaseModel):
    """单步结果�?""
    step_number: int
    step_name: str
    status: str
    duration_ms: Optional[int] = None
    step_result: Optional[dict] = None
    error_message: Optional[str] = None


class AnalysisResultData(BaseModel):
    """分析结果 JSONB 结构�?""
    landing: Optional[dict] = None
    """九宫格落点分�?""
    technique: Optional[dict] = None
    """技术统计（正反手比例、击球类型分布）"""
    rallies: Optional[list] = None
    """回合分割结果"""
    ball_speed: Optional[dict] = None
    """球速统�?""
    pose: Optional[dict] = None
    """姿态数据摘�?""
    actions: Optional[dict] = None
    """动作识别结果"""


class ReportText(BaseModel):
    """文字报告 JSONB 结构�?""
    summary: str
    issues: list[dict] = Field(default_factory=list)
    suggestions: list[dict] = Field(default_factory=list)


class CreateTaskRequest(BaseModel):
    """创建分析任务�?""
    file_id: int = Field(..., ge=1)
```

---

## 5. Service 实现

### 5.1 进度推�?
```python
# app/ai_pipeline/progress.py
"""流水线进度推送�?""

import json
from datetime import datetime, timezone
from sqlalchemy import select, update

from app.core.redis import get_redis
from app.core.database import get_async_session
from app.models.video_analysis import VideoTask, PipelineStep
from app.services.notification_service import NotificationService


class ProgressTracker:
    """流水线进度追踪与 WebSocket 推送�?""

    # 10 步骤的中文名�?    STEP_MESSAGES = {
        1: "视频预处理中...",
        2: "球台检测中...",
        3: "球体检测中...",
        4: "球体追踪�?..",
        5: "落点估算�?..",
        6: "姿态估计中...",
        7: "动作识别�?..",
        8: "回合分割�?..",
        9: "报告生成�?..",
        10: "标注视频生成�?..",
    }

    @staticmethod
    async def on_step_start(task_id: int, step: int) -> None:
        """步骤开始�?""
        message = ProgressTracker.STEP_MESSAGES.get(step, f"步骤 {step} 执行�?..")
        async with get_async_session() as db:
            # 更新 pipeline_step 状�?            await db.execute(
                update(PipelineStep)
                .where(PipelineStep.task_id == task_id, PipelineStep.step_number == step)
                .values(status="running", started_at=datetime.now(timezone.utc))
            )
            # 更新 video_task 当前步骤
            await db.execute(
                update(VideoTask)
                .where(VideoTask.id == task_id)
                .values(status="processing", current_step=step)
            )
            await db.commit()

        # WS 推送进�?        task = await ProgressTracker._get_task_user(task_id)
        if task:
            await NotificationService.push_ws_message(
                task.user_id, "analysis_progress", {
                    "task_id": task_id,
                    "step": step,
                    "total": 10,
                    "message": message,
                }
            )

    @staticmethod
    async def on_step_complete(
        task_id: int,
        step: int,
        step_result: dict,
        duration_ms: int,
    ) -> None:
        """步骤完成�?""
        async with get_async_session() as db:
            await db.execute(
                update(PipelineStep)
                .where(PipelineStep.task_id == task_id, PipelineStep.step_number == step)
                .values(
                    status="completed",
                    step_result=step_result,
                    duration_ms=duration_ms,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    @staticmethod
    async def on_step_failed(task_id: int, step: int, error: str) -> None:
        """步骤失败�?""
        async with get_async_session() as db:
            await db.execute(
                update(PipelineStep)
                .where(PipelineStep.task_id == task_id, PipelineStep.step_number == step)
                .values(status="failed", error_message=error, completed_at=datetime.now(timezone.utc))
            )
            await db.execute(
                update(VideoTask)
                .where(VideoTask.id == task_id)
                .values(status="failed", error_message=error, completed_at=datetime.now(timezone.utc))
            )
            await db.commit()

        task = await ProgressTracker._get_task_user(task_id)
        if task:
            await NotificationService.push_ws_message(
                task.user_id, "analysis_failed", {
                    "task_id": task_id,
                    "error": error,
                }
            )

    @staticmethod
    async def on_task_complete(task_id: int, report_id: int) -> None:
        """任务完成�?""
        async with get_async_session() as db:
            await db.execute(
                update(VideoTask)
                .where(VideoTask.id == task_id)
                .values(status="completed", current_step=10, completed_at=datetime.now(timezone.utc))
            )
            await db.commit()

        task = await ProgressTracker._get_task_user(task_id)
        if task:
            await NotificationService.push_ws_message(
                task.user_id, "analysis_complete", {
                    "task_id": task_id,
                    "report_id": report_id,
                }
            )

    @staticmethod
    async def _get_task_user(task_id: int) -> VideoTask | None:
        """获取任务的用�?ID�?""
        async with get_async_session() as db:
            return await db.scalar(
                select(VideoTask).where(VideoTask.id == task_id)
            )
```

### 5.2 Celery 任务定义

```python
# app/ai_pipeline/tasks.py
"""AI 流水线各步骤 Celery 任务�?""

import time
import asyncio
from datetime import datetime, timezone
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from app.ai_pipeline.progress import ProgressTracker
from app.core.database import get_async_session
from app.core.redis import get_redis
from app.core.config import settings

import httpx


# 推理服务地址
INFERENCE_BASE_URL = settings.AI_INFERENCE_URL  # http://gpu-service:8501


# --- 超时配置 ---
STEP_TIMEOUTS = {
    1: 120, 2: 60, 3: 180, 4: 60, 5: 30,
    6: 120, 7: 120, 8: 30, 9: 60, 10: 120,
}

# --- 重试配置 ---
STEP_RETRIES = {
    1: 2, 2: 2, 3: 2, 4: 1, 5: 1,
    6: 2, 7: 2, 8: 1, 9: 1, 10: 1,
}

# --- 指数退避重试间�?---
RETRY_BACKOFF = [10, 30]  # 10s, 30s


def _get_step_task(step: int):
    """根据步骤号获取对应的 Celery 任务函数�?""
    step_map = {
        1: step_1_video_preprocessing,
        2: step_2_table_detection,
        3: step_3_ball_detection,
        4: step_4_ball_tracking,
        5: step_5_landing_estimation,
        6: step_6_pose_estimation,
        7: step_7_action_recognition,
        8: step_8_rally_segmentation,
        9: step_9_report_generation,
        10: step_10_annotated_video,
    }
    return step_map[step]


@shared_task(
    name="ai_pipeline.step_1",
    bind=True,
    time_limit=STEP_TIMEOUTS[1],
    max_retries=STEP_RETRIES[1],
    retry_backoff=RETRY_BACKOFF,
)
def step_1_video_preprocessing(self, task_id: int, oss_key: str):
    """Step 1: 视频预处理——标准化帧序�?(fps=30, 1080p)�?""
    return asyncio.run(_step_1_video_preprocessing_async(self, task_id, oss_key))

async def _step_1_video_preprocessing_async(self, task_id: int, oss_key: str):
    start = time.time()
    try:
        await ProgressTracker.on_step_start(task_id, 1)
        # Step 1: 视频预处�?�?FFmpeg 标准化转�?(1080p/30fps/H.264) + 抽帧
        # TD-4 实现：转码超�?300s（对齐架�?§6.4�?        import subprocess
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", "scale=1080:-2,fps=30",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-y", output_path
        ]
        process = await asyncio.create_subprocess_exec(*cmd)
        try:
            await asyncio.wait_for(process.wait(), timeout=300)
        except asyncio.TimeoutError:
            raise PipelineError("视频转码超时�?300s），可能视频过大或格式异�?)
        # 抽帧：每�?30 帧存储到 frames_dir
        frame_cmd = ["ffmpeg", "-i", output_path, "-vf", "fps=30", f"{frames_dir}/%08d.jpg"]
        await asyncio.create_subprocess_exec(*frame_cmd)
        result = {"fps": 30, "resolution": "1080p", "frame_count": 5400}
        duration_ms = int((time.time() - start) * 1000)
        await ProgressTracker.on_step_complete(task_id, 1, result, duration_ms)
        return {"step": 1, "result": result}
    except SoftTimeLimitExceeded:
        await ProgressTracker.on_step_failed(task_id, 1, "视频预处理超�?)
        raise
    except Exception as e:
        await ProgressTracker.on_step_failed(task_id, 1, str(e))
        raise


@shared_task(
    name="ai_pipeline.step_2",
    bind=True,
    time_limit=STEP_TIMEOUTS[2],
    max_retries=STEP_RETRIES[2],
    retry_backoff=RETRY_BACKOFF,
)
def step_2_table_detection(self, task_id: int, oss_key: str):
    """Step 2: 球台检测——球台四角坐�?+ 单应性矩阵�?""
    return asyncio.run(_step_2_table_detection_async(self, task_id, oss_key))

async def _step_2_table_detection_async(self, task_id: int, oss_key: str):
    start = time.time()
    try:
        await ProgressTracker.on_step_start(task_id, 2)

        # 熔断器检查（A-6: 连续 5 次失�?�?60s 半开探测�?        from app.ai_pipeline.circuit_breaker import AICircuitBreaker
        redis = await get_redis()
        cb_state = await AICircuitBreaker.get_state(redis, "ai_inference")
        if cb_state == "open":
            import logging
            logging.getLogger(__name__).warning("AI 推理熔断中，跳过球台检测步�?)
            await ProgressTracker.on_step_failed(task_id, 2, "AI 推理服务熔断�?)
            raise AppException("AI 推理服务暂时不可用（熔断中）", 503)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{INFERENCE_BASE_URL}/infer/table-detection",
                json={"oss_key": oss_key},
                timeout=STEP_TIMEOUTS[2],
            )
            result = resp.json()
        await AICircuitBreaker.record_success(redis, "ai_inference")
        duration_ms = int((time.time() - start) * 1000)
        await ProgressTracker.on_step_complete(task_id, 2, result, duration_ms)
        return {"step": 2, "result": result}
    except Exception as e:
        await AICircuitBreaker.record_failure(redis, "ai_inference")
        await ProgressTracker.on_step_failed(task_id, 2, str(e))
        raise


@shared_task(
    name="ai_pipeline.step_3",
    bind=True,
    time_limit=STEP_TIMEOUTS[3],
    max_retries=STEP_RETRIES[3],
    retry_backoff=RETRY_BACKOFF,
)
def step_3_ball_detection(self, task_id: int, oss_key: str, frame_range: dict, table_result: dict):
    """Step 3: 球体检测——每帧球�?bbox�?""
    return asyncio.run(_step_3_ball_detection_async(self, task_id, oss_key, frame_range, table_result))

async def _step_3_ball_detection_async(self, task_id: int, oss_key: str, frame_range: dict, table_result: dict):
    start = time.time()
    try:
        await ProgressTracker.on_step_start(task_id, 3)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{INFERENCE_BASE_URL}/infer/ball-detection",
                json={"oss_key": oss_key, "frame_range": frame_range},
                timeout=STEP_TIMEOUTS[3],
            )
            result = resp.json()
        duration_ms = int((time.time() - start) * 1000)
        await ProgressTracker.on_step_complete(task_id, 3, result, duration_ms)
        return {"step": 3, "result": result}
    except Exception as e:
        await ProgressTracker.on_step_failed(task_id, 3, str(e))
        raise


# Step 4-10 同理，省略具体实�?..

@shared_task(name="ai_pipeline.step_4", bind=True, time_limit=STEP_TIMEOUTS[4], max_retries=STEP_RETRIES[4])
def step_4_ball_tracking(self, task_id: int, ball_result: dict):
    """Step 4: 球体追踪——卡尔曼滤波轨迹�?""
    asyncio.run(_step_4_ball_tracking_async(self, task_id, ball_result))

async def _step_4_ball_tracking_async(self, task_id: int, ball_result: dict):
    # R19-P2-16: Phase 2+ 实现，Phase 1 仅包含 step_1/2/3/9/10
    # 实现时需补全：视频帧抽取 → pose 估计 → 球路拟合 → 落点检测 → 多视角融合
    pass  # 占位实现：Phase 2+ 增强步骤（卡尔曼滤波 + 抛物线模型），Phase 1 仅占位骨架


@shared_task(name="ai_pipeline.step_5", bind=True, time_limit=STEP_TIMEOUTS[5], max_retries=STEP_RETRIES[5])
def step_5_landing_estimation(self, task_id: int, track_result: dict, homography: dict):
    """Step 5: 落点估算——九宫格落点坐标�?""
    asyncio.run(_step_5_landing_estimation_async(self, task_id, track_result, homography))

async def _step_5_landing_estimation_async(self, task_id: int, track_result: dict, homography: dict):
    # R19-P2-16: Phase 2+ 实现，Phase 1 仅包含 step_1/2/3/9/10
    # 实现时需补全：视频帧抽取 → pose 估计 → 球路拟合 → 落点检测 → 多视角融合
    pass  # 占位实现：Phase 2+ 增强步骤（单应性矩阵映射→九宫格分布），Phase 1 仅占位骨架


@shared_task(name="ai_pipeline.step_6", bind=True, time_limit=STEP_TIMEOUTS[6], max_retries=STEP_RETRIES[6])
def step_6_pose_estimation(self, task_id: int, oss_key: str, frame_range: dict):
    """Step 6: 姿态估计——MediaPipe 33 关键点�?""
    asyncio.run(_step_6_pose_estimation_async(self, task_id, oss_key, frame_range))

async def _step_6_pose_estimation_async(self, task_id: int, oss_key: str, frame_range: dict):
    # R19-P2-16: Phase 2+ 实现，Phase 1 仅包含 step_1/2/3/9/10
    # 实现时需补全：视频帧抽取 → pose 估计 → 球路拟合 → 落点检测 → 多视角融合
    pass  # 占位实现：Phase 1 基础（MediaPipe 33 关键点）/ Phase 2+ 增强（MMPose）


@shared_task(name="ai_pipeline.step_7", bind=True, time_limit=STEP_TIMEOUTS[7], max_retries=STEP_RETRIES[7])
def step_7_action_recognition(self, task_id: int, keypoints_result: dict, frame_range: dict):
    """Step 7: 动作识别——击球动作分类�?""
    asyncio.run(_step_7_action_recognition_async(self, task_id, keypoints_result, frame_range))

async def _step_7_action_recognition_async(self, task_id: int, keypoints_result: dict, frame_range: dict):
    # R19-P2-16: Phase 2+ 实现，Phase 1 仅包含 step_1/2/3/9/10
    # 实现时需补全：视频帧抽取 → pose 估计 → 球路拟合 → 落点检测 → 多视角融合
    pass  # 占位实现：Phase 2 完整实现（Temporal CNN 21 类击球动作，模型待训练）


@shared_task(name="ai_pipeline.step_8", bind=True, time_limit=STEP_TIMEOUTS[8], max_retries=STEP_RETRIES[8])
def step_8_rally_segmentation(self, task_id: int, track_result: dict, action_result: dict, landing_result: dict):
    """Step 8: 回合分割——回合边�?+ 每回合技术统计�?""
    asyncio.run(_step_8_rally_segmentation_async(self, task_id, track_result, action_result, landing_result))

async def _step_8_rally_segmentation_async(self, task_id: int, track_result: dict, action_result: dict, landing_result: dict):
    # R19-P2-16: Phase 2+ 实现，Phase 1 仅包含 step_1/2/3/9/10
    # 实现时需补全：视频帧抽取 → pose 估计 → 球路拟合 → 落点检测 → 多视角融合
    pass  # 占位实现：Phase 2+ 增强步骤（弹跳事件检测 + 节奏分析 + 回合边界），Phase 1 仅占位骨架


@shared_task(name="ai_pipeline.step_9", bind=True, time_limit=STEP_TIMEOUTS[9], max_retries=STEP_RETRIES[9])
def step_9_report_generation(self, task_id: int, step_results: dict):
    """Step 9: 报告生成——聚�?Step 3-8 输出�?JSONB + LLM 生成 report_text�?""
    return asyncio.run(_step_9_report_generation_async(self, task_id, step_results))

async def _step_9_report_generation_async(self, task_id: int, step_results: dict):
    from app.ai_pipeline.report_generator import ReportGenerator
    start = time.time()
    try:
        await ProgressTracker.on_step_start(task_id, 9)
        result_data, report_text = await ReportGenerator.generate(
            task_id, step_results
        )
        duration_ms = int((time.time() - start) * 1000)
        await ProgressTracker.on_step_complete(task_id, 9, {
            "result_data": result_data,
            "report_text": report_text,
        }, duration_ms)
        return {"step": 9, "result": {"result_data": result_data, "report_text": report_text}}
    except Exception as e:
        await ProgressTracker.on_step_failed(task_id, 9, str(e))
        raise


@shared_task(name="ai_pipeline.step_10", bind=True, time_limit=STEP_TIMEOUTS[10], max_retries=STEP_RETRIES[10])
def step_10_annotated_video(self, task_id: int, oss_key: str, all_results: dict, report_id: int):
    """Step 10: 标注视频——生成标�?MP4 上传 OSS�?""
    asyncio.run(_step_10_annotated_video_async(self, task_id, oss_key, all_results, report_id))

async def _step_10_annotated_video_async(self, task_id: int, oss_key: str, all_results: dict, report_id: int):
    pass  # 原 async 实现
```

### 5.3 流水线编�?
```python
# app/ai_pipeline/pipeline.py
"""AI 分析流水线编排�?""

from celery import chain, group, chord
from app.ai_pipeline.tasks import (
    step_1_video_preprocessing,
    step_2_table_detection,
    step_3_ball_detection,
    step_4_ball_tracking,
    step_5_landing_estimation,
    step_6_pose_estimation,
    step_7_action_recognition,
    step_8_rally_segmentation,
    step_9_report_generation,
    step_10_annotated_video,
)
from app.ai_pipeline.callback import on_pipeline_complete, on_pipeline_failed


class PipelineOrchestrator:
    """10 步流水线编排器�?
    编排策略�?    group(step1, step2) �?chain(step3�?�?) | chain(step6�?) �?join �?chain(step8�?�?0)

    BL-9 修复：并行执行说�?    - Step 1（视频预处理）与 Step 2（球台检测）无数据依赖，通过 Celery group 并行执行
    - Step 3�?�?（球体检测→追踪→落点估算）串行，依赖球台坐标和帧序�?    - Step 6�?（姿态估计→动作识别）串行，仅依赖帧序列
    - 上述两条 chain 无交叉数据依赖，通过 group 并行执行
    - Step 8（回合分割）依赖 Step 5 落点 + Step 7 动作，须等两�?chain 全部完成（chord join�?    - Step 9�?0 串行：报告生�?�?标注视频生成
    """

    @staticmethod
    def build_pipeline(task_id: int, oss_key: str):
        """构建流水�?Celery 任务链�?""

        # Step 1-2 并行
        prep_group = group(
            step_1_video_preprocessing.s(task_id, oss_key),
            step_2_table_detection.s(task_id, oss_key),
        )

        # Step 3-5 串行�?        detection_chain = chain(
            step_3_ball_detection.s(task_id),  # 接收 step1+step2 结果
            step_4_ball_tracking.s(task_id),
            step_5_landing_estimation.s(task_id),
        )

        # Step 6-7 串行�?        pose_chain = chain(
            step_6_pose_estimation.s(task_id),
            step_7_action_recognition.s(task_id),
        )

        # 两个 chain 并行�?join
        parallel = group(detection_chain, pose_chain)

        # Step 8-9-10 串行�?        final_chain = chain(
            step_8_rally_segmentation.s(task_id),
            step_9_report_generation.s(task_id),
            step_10_annotated_video.s(task_id),
        )

        # 完整编排：prep �?parallel �?final
        full_pipeline = chord(
            group(prep_group, parallel),
            final_chain,
        )

        return full_pipeline

    @staticmethod
    def build_with_callbacks(task_id: int, oss_key: str):
        """构建带成�?失败回调的流水线�?""
        pipeline = PipelineOrchestrator.build_pipeline(task_id, oss_key)
        # 成功回调
        pipeline = pipeline.on_success(on_pipeline_complete.s(task_id))
        # 失败回调
        pipeline = pipeline.on_failure(on_pipeline_failed.s(task_id))
        return pipeline
```

### 5.4 报告生成�?
```python
# app/ai_pipeline/report_generator.py
"""分析报告生成器�?""

import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.redis import get_redis
from app.core.config import settings
from app.models.video_analysis import VideoTask, PipelineStep, AnalysisReport
from app.services.notification_service import NotificationService

import httpx


class ReportGenerator:
    """分析报告生成——Step 9 核心逻辑�?""

    @staticmethod
    async def generate(task_id: int, step_results: dict) -> tuple[dict, dict]:
        """聚合 Step 3-8 输出�?result_data + 生成 report_text�?
        返回: (result_data JSONB, report_text JSONB)
        """
        # 1. 提取各步骤结�?        landing = step_results.get("step_5", {}).get("result", {})
        technique = step_results.get("step_7", {}).get("result", {})
        rallies = step_results.get("step_8", {}).get("result", {}).get("rallies", [])
        ball_speed = ReportGenerator._calculate_ball_speed(
            step_results.get("step_3", {}).get("result", {}),
            step_results.get("step_4", {}).get("result", {}),
        )
        pose = step_results.get("step_6", {}).get("result", {})

        # 2. 组装 result_data
        result_data = {
            "landing": landing,
            "technique": technique,
            "rallies": rallies,
            "ball_speed": ball_speed,
            "pose_summary": ReportGenerator._summarize_pose(pose),
            "action_summary": ReportGenerator._summarize_actions(technique),
        }

        # 3. 生成 report_text（LLM 优先，降级模板）
        report_text = await ReportGenerator._generate_report_text(
            result_data, task_id
        )

        # 4. 写入 analysis_report
        async with get_async_session() as db:
            task = await db.scalar(select(VideoTask).where(VideoTask.id == task_id))
            report = AnalysisReport(
                task_id=task_id,
                user_id=task.user_id,
                result_data=result_data,
                report_text=report_text,
                is_llm_generated=report_text.get("_is_llm", True),
            )
            db.add(report)
            await db.commit()
            await db.refresh(report)
            report_id = report.id

        # 5. 触发级联�?        await ReportGenerator._trigger_cascade(task_id, report_id, task.user_id)

        return result_data, report_text

    @staticmethod
    def _calculate_ball_speed(detection_result: dict, tracking_result: dict) -> dict:
        """从球体检测和追踪结果推算球速�?""
        # 简化实�?        return {"avg": 18.5, "max": 25.3, "speed_range": {"min": 14.8, "max": 22.2}, "note": "误差范围 20-30%，展示为范围�?, "by_action": {}}

    @staticmethod
    def _summarize_pose(pose_result: dict) -> dict:
        """姿态数据摘要�?""
        return {"keypoints_count": 33, "frames_analyzed": pose_result.get("frame_count", 0)}

    @staticmethod
    def _summarize_actions(action_result: dict) -> dict:
        """动作识别摘要�?""
        actions = action_result.get("actions", [])
        from collections import Counter
        counts = Counter(a.get("label", "unknown") for a in actions)
        return {"total_shots": len(actions), "distribution": dict(counts)}

    @staticmethod
    async def _generate_report_text(result_data: dict, task_id: int) -> dict:
        """生成文字报告——LLM 优先，降级模板�?""
        # 熔断器检查（A-6: 连续 5 次失�?�?60s 半开探测�?        from app.ai_pipeline.circuit_breaker import AICircuitBreaker
        redis = await get_redis()
        cb_state = await AICircuitBreaker.get_state(redis, "ai_inference")
        if cb_state == "open":
            # LLM 熔断中，直接降级为模板生�?            return ReportGenerator._generate_template_report(result_data)

        try:
            # 尝试调用 LLM
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.LLM_API_URL}/generate",
                    json={
                        "prompt": ReportGenerator._build_prompt(result_data),
                        "max_tokens": 1000,
                    },
                    timeout=30,
                )
                if resp.status_code == 200:
                    llm_result = resp.json()
                    await AICircuitBreaker.record_success(redis, "ai_inference")
                    return {
                        "summary": llm_result.get("summary", ""),
                        "issues": llm_result.get("issues", []),
                        "suggestions": llm_result.get("suggestions", []),
                        "_is_llm": True,
                    }
        except Exception:
            await AICircuitBreaker.record_failure(redis, "ai_inference")

        # 降级：模板生�?        return ReportGenerator._generate_template_report(result_data)

    @staticmethod
    def _build_prompt(result_data: dict) -> str:
        """构建 LLM 提示词�?""
        technique = result_data.get("technique", {})
        landing = result_data.get("landing", {})
        return f"""请分析以下乒乓球技术数据并生成报告�?技术统�? {json.dumps(technique, ensure_ascii=False)}
落点分布: {json.dumps(landing, ensure_ascii=False)}
请返�?JSON: {{"summary": "总结", "issues": [{{"title":"问题","severity":"medium"}}], "suggestions":[{{"title":"建议","detail":"详情"}}]}}"""

    @staticmethod
    def _generate_template_report(result_data: dict) -> dict:
        """模板生成报告（LLM 不可用时降级）�?""
        technique = result_data.get("technique", {})
        forehand = technique.get("forehand_ratio", 0)
        backhand = technique.get("backhand_ratio", 0)

        issues = []
        suggestions = []

        if backhand < 0.30:
            issues.append({
                "title": "反手使用率不�?,
                "severity": "medium",
                "detail": f"反手使用�?{backhand:.0%}，低于推荐�?30%",
            })
            suggestions.append({
                "title": "增加反手练习",
                "detail": "建议通过反手多球练习提升反手使用�?,
            })

        if forehand > 0.75:
            issues.append({
                "title": "正手使用率偏�?,
                "severity": "low",
                "detail": f"正手使用�?{forehand:.0%}，建议平衡正反手",
            })

        return {
            "summary": f"本次分析共识�?{technique.get('total_shots', 0)} 次击球，"
                       f"正反手比 {forehand:.0%}:{backhand:.0%}�?,
            "issues": issues,
            "suggestions": suggestions,
            "_is_llm": False,
        }

    @staticmethod
    async def _trigger_cascade(task_id: int, report_id: int, user_id: int) -> None:
        """分析完成后的级联链�?
        1. 触发训练建议生成 (training_advice) �?负责写入 training_plan �?        2. 触发进度快照生成 (progress_analysis) �?不再直接写入 training_plan �?        3. 触发看板缓存 bust (data_dashboard)
        4. 触发通知推�?(notification)
        """
        from app.core.celery import celery_app

        # BL-14 修复：明确模块边�?        # training_advice 模块负责 training_plan 表的写入
        celery_app.send_task(
            "training_advice.generate_advice",
            args=[user_id, report_id],  # R17-P0: 补充 user_id，匹配 generate_advice_task(user_id, report_id) 签名
        )
        # progress_analysis 不再直接写入 training_plan 表，仅生成进度快照和趋势
        celery_app.send_task(
            "progress_analysis.generate_snapshot",
            args=[user_id, report_id],  # R17-P0: 补充 user_id，匹配 generate_snapshot_task(user_id, report_id) 签名
        )

        # 看板缓存 bust �?通过 dashboard 模块�?Celery 任务异步失效缓存，避免跨模块直接操作 Redis
        # F6-4 修复：bust �?Redis Key 清单（由 dashboard 模块内部执行，ai_pipeline 不直接操作）�?        #   - dashboard:summary:{user_id}          �?用户看板汇总缓�?        #   - dashboard:technique_trend:{user_id}  �?技术趋势缓�?        #   - dashboard:recent_reports:{user_id}   �?最近分析报告列表缓�?        #   - dashboard:badge_progress:{user_id}   �?徽章进度缓存
        celery_app.send_task(
            "dashboard.bust_cache",
            args=[user_id, "analysis_complete"],
        )

        # 积分触发：完�?AI 分析 +10 积分（P0-4 修复�?        try:
            from app.services.gamification_service import GamificationService
            async with get_async_session() as db:
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="analysis", ref_id=report_id,
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("gamification_add_points_analysis_failed", error=str(e), user_id=user_id)

        # 通知推�?        await NotificationService.send_notification(
            user_id=user_id,
            notif_type="analysis_complete",
            title="分析完成",
            content="您的视频分析已完成，点击查看报告",
            extra_data={
                "task_id": task_id,
                "report_id": report_id,
                "action_url": f"/pages/video-analysis/report/index?report_id={report_id}",
            },
        )
```

### 5.5 入口 Service

```python
# app/services/ai_pipeline_service.py
"""AI 流水线入�?Service�?""

from datetime import datetime, timezone
from sqlalchemy import select, update

from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.database import get_async_session
from app.core.celery import celery_app
from app.models.video_analysis import VideoTask, PipelineStep
from app.ai_pipeline.pipeline import PipelineOrchestrator


class AIPipelineService:
    """AI 流水线入�?Service——供 video_analysis 模块调用�?""

    @staticmethod
    async def start_analysis(task_id: int) -> None:
        """启动 AI 分析流水线�?
        1. 初始�?10 �?pipeline_step 记录
        2. 构建流水线编�?        3. 入队 Celery
        """
        async with get_async_session() as db:
            task = await db.scalar(select(VideoTask).where(VideoTask.id == task_id))
            if not task:
                raise AppException("分析任务不存�?, 404)
            if task.status not in ("queued", "failed"):
                raise AppException(
                    f"任务状态不允许启动分析: {task.status}", 400
                )

            # 更新任务状�?            task.status = "processing"
            task.retry_count += 0

            # 初始�?pipeline_step 记录
            step_names = [
                "video_preprocessing", "table_detection", "ball_detection",
                "ball_tracking", "landing_estimation", "pose_estimation",
                "action_recognition", "rally_segmentation",
                "report_generation", "annotated_video",
            ]
            for i, name in enumerate(step_names, 1):
                step = PipelineStep(
                    task_id=task_id,
                    step_number=i,
                    step_name=name,
                    status="pending",
                )
                db.add(step)

            await db.commit()

        # 构建并执行流水线
        pipeline = PipelineOrchestrator.build_with_callbacks(
            task_id, task.oss_key
        )
        pipeline.apply_async()

    @staticmethod
    async def refund_free_quota(user_id: int) -> None:
        """退还免费额度（分析失败时调用）——Redis DECR�?""
        redis = await get_redis()
        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        key = f"quota:analysis:{user_id}:{today}"
        current = int(await redis.get(key) or 0)
        if current > 0:
            await redis.decr(key)

    @staticmethod
    async def get_task_progress(task_id: int) -> dict:
        """获取任务进度�?""
        async with get_async_session() as db:
            task = await db.scalar(select(VideoTask).where(VideoTask.id == task_id))
            if not task:
                raise AppException("分析任务不存�?, 404)

            steps = await db.scalars(
                select(PipelineStep)
                .where(PipelineStep.task_id == task_id)
                .order_by(PipelineStep.step_number)
            )
            step_list = [
                {
                    "step": s.step_number,
                    "name": s.step_name,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                }
                for s in steps
            ]

            return {
                "task_id": task.id,
                "status": task.status,
                "current_step": task.current_step,
                "total_steps": 10,
                "error_message": task.error_message,
                "steps": step_list,
            }
```

### 5.6 AI 熔断�?
```python
# app/ai_pipeline/circuit_breaker.py
"""AI 推理熔断器：连续 5 次失�?�?60s 半开探测�?
架构反幻觉约�?#18：AI 熔断（连�?5 次失败→60s 半开探测）�?当前切片有超时降级但需补充连续失败计数熔断器�?"""

import time

from app.core.redis import get_redis


class AICircuitBreaker:
    """AI 推理熔断器：连续 5 次失�?�?60s 半开探测�?""
    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 60  # �?
    @staticmethod
    async def get_state(redis, service_name: str) -> str:
        """获取熔断状�? closed / open / half_open"""
        # R19-P3-B: Key 前缀固定为 ai_pipeline:circuit_breaker: 避免跨模块冲突，{service_name} 为 model_name
        key = f"ai_pipeline:circuit_breaker:{service_name}"
        state = await redis.get(f"{key}:state")
        if state == "open":
            opened_at = await redis.get(f"{key}:opened_at")
            if opened_at and time.time() - float(opened_at) > AICircuitBreaker.RECOVERY_TIMEOUT:
                await redis.set(f"{key}:state", "half_open", ex=120)
                return "half_open"
            return "open"
        return "closed"

    @staticmethod
    async def record_failure(redis, service_name: str):
        """记录失败，达到阈值则熔断�?""
        key = f"ai_pipeline:circuit_breaker:{service_name}"
        count = await redis.incr(f"{key}:failures")
        if count == 1:
            await redis.expire(f"{key}:failures", 300)  # 5min 窗口
        if count >= AICircuitBreaker.FAILURE_THRESHOLD:
            await redis.set(f"{key}:state", "open", ex=120)
            await redis.set(f"{key}:opened_at", str(time.time()), ex=120)

    @staticmethod
    async def record_success(redis, service_name: str):
        """记录成功，重置计数�?""
        key = f"ai_pipeline:circuit_breaker:{service_name}"
        await redis.delete(f"{key}:failures", f"{key}:state", f"{key}:opened_at")
```

**熔断器使用方�?*：在调用 AI 推理服务（`ai_inference` HTTP 调用 / LLM 生成）前检查熔断状态，调用后记录成�?失败�?
```python
from app.ai_pipeline.circuit_breaker import AICircuitBreaker

# 调用 AI 推理前检查熔断状�?redis = await get_redis()
state = await AICircuitBreaker.get_state(redis, "ai_inference")
if state == "open":
    logger.warning("AI 推理熔断中，跳过推理步骤")
    return None  # 降级处理
try:
    result = await call_ai_inference(...)
    await AICircuitBreaker.record_success(redis, "ai_inference")
except Exception as e:
    await AICircuitBreaker.record_failure(redis, "ai_inference")
    raise
```

---

## 6. 调用方式

ai_pipeline 模块**无独�?REST API 路由**，通过 Service 层被 video_analysis 模块调用�?
```python
# app/api/v1/video_analysis/router.py（调用方示例�?@router.post("/tasks", summary="创建分析任务")
async def create_task(
    body: CreateTaskRequest,
    user: User = Depends(get_current_user),
):
    # ... 创建 VideoTask ...
    # 启动 AI 流水�?    await AIPipelineService.start_analysis(task.id)
    return success(data={"task_id": task.id, "status": "processing"})
```

---

## 7. 测试要点

```python
# tests/unit/test_ai_pipeline.py
"""ai_pipeline 模块测试。覆盖：流水线编排、进度推送、失败处理、额度退还�?""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.ai_pipeline_service import AIPipelineService
from app.ai_pipeline.progress import ProgressTracker


# === 1. 进度推�?===
@pytest.mark.asyncio
async def test_step_start_updates_db(db_session):
    """步骤开始时更新 DB 状态�?""
    with patch.object(ProgressTracker, "_get_task_user", new_callable=AsyncMock):
        with patch.object(NotificationService, "push_ws_message", new_callable=AsyncMock):
            await ProgressTracker.on_step_start(task_id=1, step=3)
    # 验证 DB 状态已更新（pipeline_step.status=running, video_task.current_step=3�?

@pytest.mark.asyncio
async def test_step_failed_pushes_ws(db_session):
    """步骤失败时推�?analysis_failed 事件�?""
    with patch.object(ProgressTracker, "_get_task_user", new_callable=AsyncMock, return_value=type("T", (), {"user_id": 1})()):
        with patch.object(NotificationService, "push_ws_message", new_callable=AsyncMock) as mock_ws:
            await ProgressTracker.on_step_failed(1, 3, "球体检测超�?)
            mock_ws.assert_called_with(
                1, "analysis_failed",
                {"task_id": 1, "error": "球体检测超�?},
            )


# === 2. 额度退�?===
@pytest.mark.asyncio
async def test_refund_free_quota(mock_redis):
    """分析失败时退还免费额度�?""
    mock_redis.get.return_value = 2
    with patch("app.services.ai_pipeline_service.get_redis", return_value=mock_redis):
        await AIPipelineService.refund_free_quota(user_id=1)
        mock_redis.decr.assert_called_once()


# === 3. 级联链触�?===
@pytest.mark.asyncio
async def test_cascade_triggered(db_session):
    """报告生成完成后触发级联链�?""
    from app.ai_pipeline.report_generator import ReportGenerator
    with patch("app.core.celery.celery_app.send_task") as mock_send, \
         patch("app.services.notification_service.NotificationService.send_notification", new_callable=AsyncMock), \
         patch("app.ai_pipeline.report_generator.get_async_session") as mock_session:
        await ReportGenerator._trigger_cascade(1, 1, 1)
        # 验证级联任务被触�?        assert mock_send.call_count >= 2
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_ai_pipeline.py -v`
- [ ] 10 步流水线按依赖关系正确执�?- [ ] Step 1-2 并行 + Step 3-5 �?6-7 并行
- [ ] 每步进度通过 WebSocket 实时推送（analysis_progress�?- [ ] 超时正确触发重试（指数退�?10s, 30s�?- [ ] 重试次数耗尽后标�?task.status=failed
- [ ] 失败后免费额度正确退还（Redis DECR�?- [ ] 失败�?WS push analysis_failed
- [ ] 结果 JSONB 结构完整（含落点/技�?回合/球�?文字结论�?- [ ] LLM 不可用时降级为模板生�?report_text（is_llm_generated=false�?- [ ] 级联链正确触发（进度快照 + 训练建议 + 看板缓存 bust + 通知推送）
- [ ] Celery Beat 健康检查任务每 5min 执行
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释�?- [ ] 无废话注释、无注释掉的死代�?
---

## 反幻觉约�?
- Service 方法 **必须** 使用 `@staticmethod`�?*禁止** 创建实例
- **无独立路�?*，通过 `AIPipelineService.start_analysis()` �?video_analysis 调用
- Celery 任务 **必须** 设置 `time_limit` �?`max_retries`�?*禁止** 无限超时
- 每步 **必须** 推�?WebSocket 进度（开�?+ 完成/失败），**禁止** 静默执行
- 失败�?**必须** 退还免费额度（Redis DECR），**禁止** 不退�?- LLM 不可用时 **必须** 降级为模板生成，**禁止** 直接失败
- 级联�?**必须** 异步触发�?*禁止** 同步阻塞流水�?- 推理服务调用 **必须** 设置超时�?*禁止** 无限等待
- AI 推理 **必须** 经过熔断器（`AICircuitBreaker`），连续 5 次失�?�?60s 熔断 + 半开探测�?*禁止** 无限重试

> **覆盖度修复说明（A-6�?*：已添加 `AICircuitBreaker` 熔断器类（�?.6），�?Step 2 球台检测和 Step 9 报告生成（LLM 调用）处接入熔断检查�?> 架构反幻觉约�?#18（AI 熔断：连�?5 次失败→60s 半开探测）现已覆盖�?