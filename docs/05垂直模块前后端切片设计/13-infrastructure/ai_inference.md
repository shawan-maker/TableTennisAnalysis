# ai_inference 基础设施模块 — 后端垂直切片设计

> **模块名称**：`ai_inference`
> **部署方式**：独立部署在 GPU 实例（T4 Spot），通过 HTTP API 供 ai_pipeline 调用
> **定位**：模型加载、推理 API、健康检查、降级策略
> **依据**：模块详细设计 v1.2 §3.3

---

## 1. 模块概述

| 属性 | 值 |
|------|-----|
| 模块名称 | `ai_inference` |
| 部署方式 | 独立 FastAPI 服务，部署在 GPU 实例（T4 Spot） |
| 所属目录 | `gpu_service/`（独立仓库/目录，与主应用分离） |
| 一句话定位 | 模型热加载、4 个推理 API、健康检查、超时降级策略 |
| 依赖模块 | ai_pipeline（调用方） |
| 对外 API | `POST /infer/ball-detection`, `POST /infer/table-detection`, `POST /infer/pose`, `POST /infer/action`, `GET /health` |

### 推理 API 设计

| 端点 | Method | 输入 | 输出 | 超时 |
|------|--------|------|------|------|
| /infer/ball-detection | POST | `{oss_key, frame_range}` | `{frames: [{frame_id, boxes: [{x,y,w,h,conf}]}]}` | 180s |
| /infer/table-detection | POST | `{oss_key}` | `{corners: [{x,y}], homography: [[...]]}` | 60s |
| /infer/pose | POST | `{oss_key, frame_range}` | `{frames: [{frame_id, keypoints: [[x,y,vis]...33]}]}` | 120s |
| /infer/action | POST | `{keypoints_sequence, frame_range}` | `{actions: [{frame_range, label, conf}]}` | 120s |

### 核心特性

- **模型热加载与切换**：运行时异步加载新模型 → 加载完成后原子替换 → 释放旧模型显存
- **健康检查**：Celery Beat 每 5min GET /health，不可用时 ai_pipeline 进入降级模式
- **超时降级策略**：球检测超时 → 返回空结果（流水线标记 failed）；姿态估计超时 → 跳过姿态/动作步骤
- **GPU OOM 恢复**：自动重启服务 + 重新排队任务

---

## 2. 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 实现推理服务入口 | `gpu_service/main.py` | 无 | ☐ |
| 2 | 实现模型管理器 | `gpu_service/model_manager.py` | #1 | ☐ |
| 3 | 实现 4 个推理 API | `gpu_service/api/infer.py` | #2 | ☐ |
| 4 | 实现健康检查 | `gpu_service/api/health.py` | #2 | ☐ |
| 5 | 实现降级策略 | `gpu_service/degradation.py` | #3 | ☐ |
| 6 | 实现 ai_pipeline 侧健康检查 Celery Beat | `app/tasks/ai_inference_health.py` | #4 | ☐ |
| 7 | 编写测试 | `gpu_service/tests/test_inference.py` | #3 | ☐ |
| 8 | 编写冒烟测试 | `tests/smoke/ai_inference_smoke_test.py` | #6 | ☐ |

---

## 3. Model 实现

ai_inference 模块**不使用数据库表**，模型版本信息存储在 Redis 或配置文件中。模型权重文件存储在本地 GPU 实例磁盘。

模型版本管理（Phase 2+ 数据库表，Phase 1 使用配置）：

```python
# gpu_service/config.py
"""推理服务配置。"""

from pydantic_settings import BaseSettings
from pathlib import Path


class InferenceSettings(BaseSettings):
    """推理服务配置。"""

    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8501

    # 模型权重路径
    model_base_dir: Path = Path("/models")

    # 默认模型版本
    default_ball_model: str = "tracknet_v5"
    default_table_model: str = "yolo_pose_v1"
    default_pose_model: str = "mediapipe_v1"
    default_action_model: str = "temporal_cnn_v1"

    # GPU 配置
    device: str = "cuda:0"
    gpu_memory_fraction: float = 0.8

    # 超时配置
    ball_detection_timeout: int = 180
    table_detection_timeout: int = 60
    pose_timeout: int = 120
    action_timeout: int = 120

    # Redis（健康检查状态）
    redis_url: str = "redis://redis:6379/1"

    # OSS 配置（从 OSS 拉取视频帧）
    oss_endpoint: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket: str = ""

    class Config:
        env_prefix = "INFERENCE_"


settings = InferenceSettings()
```

---

## 4. Schema 实现

```python
# gpu_service/schemas.py
"""推理服务 Schema 定义。"""

from typing import Optional
from pydantic import BaseModel, Field


# --- 请求 Schema ---
class BallDetectionRequest(BaseModel):
    oss_key: str = Field(..., description="OSS 对象 Key")
    frame_range: dict = Field(..., description="帧范围 {start: 0, end: 5400, step: 1}")


class TableDetectionRequest(BaseModel):
    oss_key: str = Field(..., description="OSS 对象 Key")


class PoseRequest(BaseModel):
    oss_key: str = Field(...)
    frame_range: dict = Field(...)


class ActionRequest(BaseModel):
    keypoints_sequence: list = Field(..., description="关键点序列")
    frame_range: dict = Field(...)


# --- 响应 Schema ---
class BoundingBox(BaseModel):
    x: float
    y: float
    w: float
    h: float
    conf: float


class BallDetectionFrame(BaseModel):
    frame_id: int
    boxes: list[BoundingBox]


class BallDetectionResponse(BaseModel):
    frames: list[BallDetectionFrame]
    model_version: str
    inference_time_ms: int


class TableCorner(BaseModel):
    x: float
    y: float


class TableDetectionResponse(BaseModel):
    corners: list[TableCorner]
    homography: list[list[float]]
    model_version: str
    inference_time_ms: int


class PoseKeypoint(BaseModel):
    x: float
    y: float
    visibility: float


class PoseFrame(BaseModel):
    frame_id: int
    keypoints: list[PoseKeypoint]  # 33 个关键点


class PoseResponse(BaseModel):
    frames: list[PoseFrame]
    model_version: str
    inference_time_ms: int


class ActionResult(BaseModel):
    frame_range: dict
    label: str
    conf: float


class ActionResponse(BaseModel):
    actions: list[ActionResult]
    model_version: str
    inference_time_ms: int


# --- 健康检查 Schema ---
class HealthResponse(BaseModel):
    status: str = "healthy"
    device: str
    gpu_memory_used_mb: int
    gpu_memory_total_mb: int
    models_loaded: dict[str, str]  # {model_type: version}
    active_inferences: int
```

---

## 5. Service 实现

### 5.1 模型管理器

```python
# gpu_service/model_manager.py
"""模型加载、热切换、显存管理。"""

import asyncio
import importlib
from typing import Optional
import logging

from gpu_service.config import settings

logger = logging.getLogger(__name__)


class ModelManager:
    """模型管理器——负责模型的加载、热切换、显存管理。

    线程安全设计：
    - _models 字典存储当前活跃模型
    - 热切换时异步加载新模型 → 原子替换 → 释放旧模型
    """

    _models: dict[str, object] = {}  # {model_type: model_instance}
    _versions: dict[str, str] = {}   # {model_type: version_string}
    _lock = asyncio.Lock()
    _active_inferences = 0

    # 模型类型 → 默认版本
    MODEL_DEFAULTS = {
        "ball": "tracknet_v5",
        "table": "yolo_pose_v1",
        "pose": "mediapipe_v1",
        "action": "temporal_cnn_v1",
    }

    @classmethod
    async def load_all(cls) -> None:
        """启动时加载所有默认模型。"""
        for model_type, version in cls.MODEL_DEFAULTS.items():
            try:
                await cls._load_model(model_type, version)
                logger.info(f"Loaded {model_type} model: {version}")
            except Exception as e:
                logger.error(f"Failed to load {model_type} model: {e}")
                # 启动时加载失败不阻塞，后续可热加载

    @classmethod
    async def _load_model(cls, model_type: str, version: str) -> object:
        """加载单个模型到 GPU 显存。"""
        model_path = settings.model_base_dir / f"{model_type}_{version}.pt"
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        # TD-5 实现：模型加载（按 model_type 选择推理引擎）
        import torch
        import threading
        if model_type.startswith("yolo"):
            from ultralytics import YOLO
            model = YOLO(str(model_path))
        elif model_type.startswith("ttnet") or model_type.startswith("tracknet"):
            model = torch.jit.load(str(model_path), map_location=settings.device)
        elif model_type.startswith("mediapipe"):
            import mediapipe as mp
            model = mp.solutions.pose.Pose(
                static_image_mode=False, model_complexity=1, min_detection_confidence=0.5
            )
        elif model_type.startswith("temporal_cnn"):
            model = torch.jit.load(str(model_path), map_location=settings.device)
        else:
            raise ValueError(f"未知模型类型: {model_type}")
        if not hasattr(cls, "_model_locks"):
            cls._model_locks = {}
        cls._model_locks[model_type] = threading.Lock()
        logger.info("model_loaded", model_type=model_type, device=str(settings.device))

        async with cls._lock:
            cls._models[model_type] = model
            cls._versions[model_type] = version

        return model

    @classmethod
    async def hot_swap(cls, model_type: str, new_version: str) -> bool:
        """热加载新模型 → 原子替换 → 释放旧模型。

        切换时异步加载新模型 → 加载完成后原子替换 → 释放旧模型显存。
        新模型加载失败 → 保持旧模型运行，记录错误日志。
        """
        try:
            # 异步加载新模型（不影响正在执行的推理）
            new_model = await cls._load_model(model_type, new_version)

            async with cls._lock:
                old_model = cls._models.get(model_type)
                cls._models[model_type] = new_model
                cls._versions[model_type] = new_version

            # 释放旧模型显存
            if old_model:
                del old_model
                torch.cuda.empty_cache()
                logger.info(f"Released old {model_type} model, GPU memory cleared")

            logger.info(f"Hot-swapped {model_type} to {new_version}")
            return True
        except Exception as e:
            logger.error(f"Hot-swap failed for {model_type}: {e}")
            return False

    @classmethod
    def get_model(cls, model_type: str) -> Optional[object]:
        """获取当前活跃模型。"""
        return cls._models.get(model_type)

    @classmethod
    def get_version(cls, model_type: str) -> Optional[str]:
        """获取当前模型版本。"""
        return cls._versions.get(model_type)

    @classmethod
    def get_all_versions(cls) -> dict[str, str]:
        """获取所有已加载模型版本。"""
        return dict(cls._versions)

    @classmethod
    async def acquire_inference(cls) -> None:
        """占用推理槽位（并发计数）。"""
        async with cls._lock:
            cls._active_inferences += 1

    @classmethod
    async def release_inference(cls) -> None:
        """释放推理槽位。"""
        async with cls._lock:
            cls._active_inferences = max(0, cls._active_inferences - 1)

    @classmethod
    def get_active_count(cls) -> int:
        """获取当前活跃推理数量。"""
        return cls._active_inferences
```

### 5.2 推理 API 实现

> **R18-P3-12 修复（已在 R18 落地）**：本节所有推理端点（ball-detection / table-detection / pose / action）的错误响应统一改用 `app.core.exceptions.AppException`，不再使用 `fastapi.HTTPException`。原 R18 推迟原因为"Phase 2+ 模块豁免"，但 `AppException` 已通过 `app.core.exceptions` 全局异常处理器统一返回 `{code, message, data}` 结构，与 API §1.7 通用错误码格式一致，且便于在事务边界统一回滚。Phase 2+ 模块豁免仅适用于未来 `gpu_service` 独立部署后的边缘场景，当前共享应用进程内的推理路由必须遵循全局异常规范。

```python
# gpu_service/api/infer.py
"""推理 API 路由。"""

import time
import asyncio
from fastapi import APIRouter

from app.core.exceptions import AppException
from gpu_service.config import settings
from gpu_service.model_manager import ModelManager
from gpu_service.schemas import (
    BallDetectionRequest, BallDetectionResponse,
    TableDetectionRequest, TableDetectionResponse,
    PoseRequest, PoseResponse,
    ActionRequest, ActionResponse,
)
from gpu_service.degradation import DegradationHandler

router = APIRouter(prefix="/infer", tags=["推理"])


@router.post("/ball-detection", response_model=BallDetectionResponse)
async def ball_detection(req: BallDetectionRequest):
    """球体检测推理——TTNet/TrackNetV5。

    超时降级：超时后返回空结果（流水线标记 failed）。
    """
    start = time.time()
    model = ModelManager.get_model("ball")
    if not model:
        raise AppException("Ball detection model not loaded", 503)

    await ModelManager.acquire_inference()
    try:
        result = await asyncio.wait_for(
            _run_ball_detection(model, req),
            timeout=settings.ball_detection_timeout,
        )
        duration = int((time.time() - start) * 1000)
        return BallDetectionResponse(
            frames=result,
            model_version=ModelManager.get_version("ball"),
            inference_time_ms=duration,
        )
    except asyncio.TimeoutError:
        DegradationHandler.on_ball_detection_timeout()
        raise AppException("Ball detection timeout", 504)
    finally:
        await ModelManager.release_inference()


@router.post("/table-detection", response_model=TableDetectionResponse)
async def table_detection(req: TableDetectionRequest):
    """球台检测推理——YOLO-pose。"""
    start = time.time()
    model = ModelManager.get_model("table")
    if not model:
        raise AppException("Table detection model not loaded", 503)

    await ModelManager.acquire_inference()
    try:
        result = await asyncio.wait_for(
            _run_table_detection(model, req),
            timeout=settings.table_detection_timeout,
        )
        duration = int((time.time() - start) * 1000)
        return TableDetectionResponse(
            corners=result["corners"],
            homography=result["homography"],
            model_version=ModelManager.get_version("table"),
            inference_time_ms=duration,
        )
    except asyncio.TimeoutError:
        raise AppException("Table detection timeout", 504)
    finally:
        await ModelManager.release_inference()


@router.post("/pose", response_model=PoseResponse)
async def pose_estimation(req: PoseRequest):
    """姿态估计推理——MediaPipe 33 关键点。

    超时降级：跳过姿态/动作步骤（报告标注"未含动作分析"）。
    """
    start = time.time()
    model = ModelManager.get_model("pose")
    if not model:
        raise AppException("Pose model not loaded", 503)

    await ModelManager.acquire_inference()
    try:
        result = await asyncio.wait_for(
            _run_pose_estimation(model, req),
            timeout=settings.pose_timeout,
        )
        duration = int((time.time() - start) * 1000)
        return PoseResponse(
            frames=result,
            model_version=ModelManager.get_version("pose"),
            inference_time_ms=duration,
        )
    except asyncio.TimeoutError:
        DegradationHandler.on_pose_timeout()
        raise AppException("Pose estimation timeout", 504)
    finally:
        await ModelManager.release_inference()


@router.post("/action", response_model=ActionResponse)
async def action_recognition(req: ActionRequest):
    """动作识别推理——Temporal CNN。"""
    start = time.time()
    model = ModelManager.get_model("action")
    if not model:
        raise AppException("Action model not loaded", 503)

    await ModelManager.acquire_inference()
    try:
        result = await asyncio.wait_for(
            _run_action_recognition(model, req),
            timeout=settings.action_timeout,
        )
        duration = int((time.time() - start) * 1000)
        return ActionResponse(
            actions=result,
            model_version=ModelManager.get_version("action"),
            inference_time_ms=duration,
        )
    except asyncio.TimeoutError:
        raise AppException("Action recognition timeout", 504)
    finally:
        await ModelManager.release_inference()


# --- 实际推理逻辑 ---
# Phase 1: 球体检测已实现完整流水线（OSS 拉帧→预处理→批量推理→后处理）
# Phase 2: 球台检测/姿态估计/动作识别补充完整推理逻辑（当前为简化实现）
async def _run_ball_detection(model, req: BallDetectionRequest):
    """执行球体检测推理。"""
    import torch
    # TD-6 实现：球体检测推理流水线
    # 1. 从 OSS 拉取帧序列
    frames = await _fetch_frames_from_oss(req.oss_key, req.frame_range)
    # 2. 预处理：归一化 + resize 到模型输入尺寸
    processed = [_preprocess_frame(f, (640, 384)) for f in frames]
    # 3. 模型推理（批量）
    with ModelManager._model_locks["ball"]:
        detections = []
        for frame_tensor in processed:
            with torch.no_grad():
                output = model(frame_tensor.unsqueeze(0).to(settings.device))
            detections.append(_parse_detection_output(output))
    # 4. 后处理：NMS + 坐标映射回原图
    results = [_postprocess_detection(d, frames[0].shape[:2]) for d in detections]
    return results

async def _run_table_detection(model, req: TableDetectionRequest):
    """执行球台检测推理。"""
    return {"corners": [{"x": 0, "y": 0}], "homography": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}

async def _run_pose_estimation(model, req: PoseRequest):
    """执行姿态估计推理。"""
    return [{"frame_id": 0, "keypoints": [{"x": 0, "y": 0, "visibility": 0} for _ in range(33)]}]

async def _run_action_recognition(model, req: ActionRequest):
    """执行动作识别推理。"""
    return [{"frame_range": {"start": 0, "end": 30}, "label": "forehand_drive", "conf": 0.85}]
```

### 5.3 降级策略

```python
# gpu_service/degradation.py
"""推理超时降级策略。"""

import logging
from gpu_service.model_manager import ModelManager

logger = logging.getLogger(__name__)


class DegradationHandler:
    """推理超时降级处理。

    - 球检测超时 → 返回空结果（流水线标记 failed）
    - 姿态估计超时 → 跳过姿态/动作步骤（报告标注"未含动作分析"）
    - GPU OOM → 重启服务 + 重新排队任务
    """

    @staticmethod
    def on_ball_detection_timeout() -> None:
        """球检测超时——流水线将标记 failed。"""
        logger.error("Ball detection timeout - pipeline will be marked as failed")

    @staticmethod
    def on_pose_timeout() -> None:
        """姿态估计超时——跳过姿态/动作步骤。"""
        logger.warning("Pose estimation timeout - skipping pose/action steps")
        # ai_pipeline 会收到 504 响应，跳过 step 6-7
        # 报告中标注 is_pose_included=false

    @staticmethod
    async def on_gpu_oom() -> None:
        """GPU OOM——重启推理服务 + 重新排队任务。"""
        logger.critical("GPU OOM detected - initiating service restart")
        # TD-7 实现：GPU OOM 恢复
        import gc
        logger.error("gpu_oom_detected")
        # 清理所有缓存
        torch.cuda.empty_cache()
        gc.collect()
        torch.cuda.empty_cache()
        # 清理模型引用，强制重新加载
        ModelManager._models.clear()
        if hasattr(ModelManager, "_model_locks"):
            ModelManager._model_locks.clear()
        await ModelManager.load_all()
        logger.info("gpu_oom_recovered")
        # 重新排队中断的任务由 ai_pipeline 侧处理
```

### 5.4 健康检查 API

```python
# gpu_service/api/health.py
"""健康检查 API。"""

import torch
from fastapi import APIRouter

from gpu_service.config import settings
from gpu_service.model_manager import ModelManager
from gpu_service.schemas import HealthResponse

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """推理服务健康检查。

    Celery Beat 每 5min 调用此端点。
    返回 200 → 标记可用；超时/5xx → 标记不可用 + 告警。
    """
    gpu_memory_used = 0
    gpu_memory_total = 0

    if torch.cuda.is_available():
        gpu_memory_used = torch.cuda.memory_allocated() // (1024 * 1024)
        gpu_memory_total = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)

    return HealthResponse(
        status="healthy",
        device=settings.device,
        gpu_memory_used_mb=gpu_memory_used,
        gpu_memory_total_mb=gpu_memory_total,
        models_loaded=ModelManager.get_all_versions(),
        active_inferences=ModelManager.get_active_count(),
    )
```

### 5.5 推理服务入口

```python
# gpu_service/main.py
"""AI 推理服务入口——独立部署在 GPU 实例。"""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from gpu_service.api.infer import router as infer_router
from gpu_service.api.health import router as health_router
from gpu_service.model_manager import ModelManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务生命周期——启动时加载所有模型。"""
    # 启动时加载所有默认模型
    await ModelManager.load_all()
    yield
    # 关闭时清理（释放显存）
    # TD-8 实现：推理完成后清理显存
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        allocated = torch.cuda.memory_allocated() / 1024**3
        logger.debug("gpu_memory_after_cleanup", allocated_gb=f"{allocated:.2f}")


app = FastAPI(
    title="PingPongAI Inference Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(infer_router, prefix="/infer")
app.include_router(health_router)
```

---

## 6. 调用方式

### 6.1 被 ai_pipeline 调用

ai_pipeline 通过 HTTP 调用推理 API（见 `app/ai_pipeline/tasks.py`）：

```python
# app/ai_pipeline/tasks.py 中的调用示例
import httpx
from app.core.config import settings

INFERENCE_BASE_URL = settings.AI_INFERENCE_URL  # http://gpu-service:8501

# 球台检测
async with httpx.AsyncClient() as client:
    resp = await client.post(
        f"{INFERENCE_BASE_URL}/infer/table-detection",
        json={"oss_key": oss_key},
        timeout=60,
    )
    result = resp.json()
```

### 6.2 主应用侧健康检查 Celery Beat

```python
# app/tasks/ai_inference_health.py
"""推理服务健康检查——主应用侧 Celery Beat 任务。"""

import httpx
import logging
from app.core.celery import celery_app
from app.core.redis import get_redis
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="ai_inference.health_check")
def check_inference_health():
    """每 5min 检查推理服务可用性。

    - GET /health → 200 则标记可用
    - 超时/5xx → 标记不可用 + 告警
    - 恢复后自动标记可用

    注意：Celery worker 默认不支持 async def task，使用 asyncio.run() 驱动异步逻辑。
    """
    import asyncio
    asyncio.run(_check_inference_health_async())


async def _check_inference_health_async():
    """health_check 的异步实现。"""
    redis = await get_redis()
    inference_url = settings.AI_INFERENCE_URL

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{inference_url}/health",
                timeout=10,
            )
            if resp.status_code == 200:
                await redis.setex("ai_inference:available", 60, "1")
                # 检查是否从不可用恢复
                was_unavailable = await redis.get("ai_inference:was_unavailable")
                if was_unavailable:
                    await redis.delete("ai_inference:was_unavailable")
                    logger.info("AI inference service recovered")
                return
    except Exception as e:
        logger.warning(f"AI inference health check failed: {e}")

    # 标记不可用
    await redis.delete("ai_inference:available")
    await redis.set("ai_inference:was_unavailable", "1")
    logger.error("AI inference service unavailable - entering degraded mode")
    # TD-9 实现：健康检查告警
    from app.services.notification_service import NotificationService
    await NotificationService.send_admin_alert(
        title="GPU 服务健康检查异常",
        content=f"推理服务: {settings.AI_INFERENCE_URL}, 状态: unavailable",
        severity="critical"
    )
    # 同时写入 Redis 告警标记
    await redis.setex("alert:gpu_health:ai_inference", 3600, "critical")


@celery_app.task(name="ai_inference.check_available")
def is_inference_available() -> bool:
    """检查推理服务是否可用——供 ai_pipeline 调用。

    注意：Celery worker 默认不支持 async def task，使用 asyncio.run() 驱动异步逻辑。
    """
    import asyncio
    return asyncio.run(_is_inference_available_async())


async def _is_inference_available_async() -> bool:
    """is_inference_available 的异步实现。"""
    redis = await get_redis()
    return await redis.exists("ai_inference:available") > 0
```

**Celery Beat 配置**：统一由 `beat_schedule.py` 管理（见 `beat_schedule.py.md`）：
```python
# beat_schedule.py.md 中的配置（权威源）
# R18-P3: 统一为 crontab(minute="*/5")，与 beat_schedule.py.md 一致
"ai-inference-health-check": {
    "task": "ai_inference.health_check",
    "schedule": crontab(minute="*/5"),  # 每 5 分钟
},
```

### 6.3 ai_pipeline 降级模式

```python
# app/ai_pipeline/tasks.py 中的降级逻辑
# R18-P2: 修正示例代码，与 ai_pipeline.md 实际实现保持一致：
#   1. Celery 任务使用 def（非 async def），内部用 asyncio.run() 调用协程
#   2. is_inference_available() 返回 bool（非协程），直接同步调用
@shared_task(name="ai_pipeline.step_6", bind=True, ...)
def step_6_pose_estimation(self, task_id, oss_key, frame_range):
    # 检查推理服务是否可用（同步调用，返回 bool）
    from app.tasks.ai_inference_health import is_inference_available
    available = is_inference_available()
    if not available:
        # 降级模式：跳过姿态/动作步骤
        asyncio.run(ProgressTracker.on_step_complete(
            task_id, 6, {"skipped": True, "reason": "inference_unavailable"}, 0
        ))
        # Step 7 也跳过
        return {"step": 6, "result": {"skipped": True}}
    # 正常执行...
```

---

## 7. 测试要点

```python
# gpu_service/tests/test_inference.py
"""ai_inference 推理服务测试。"""
import pytest
from httpx import AsyncClient, ASGITransport
from gpu_service.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# === 1. 健康检查 ===
@pytest.mark.asyncio
async def test_health_check(client):
    """GET /health 返回 200 + GPU 信息。"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "models_loaded" in data
    assert "active_inferences" in data


# === 2. 推理 API ===
@pytest.mark.asyncio
async def test_table_detection(client):
    """POST /infer/table-detection 返回球台坐标。"""
    resp = await client.post("/infer/table-detection", json={
        "oss_key": "videos/raw/1/20260101/test.mp4"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "corners" in data
    assert "homography" in data
    assert "model_version" in data


@pytest.mark.asyncio
async def test_ball_detection_timeout(client):
    """球检测超时返回 504。"""
    # 模拟超时（实际测试需要 mock 超时场景）
    pass


# === 3. 模型热切换 ===
@pytest.mark.asyncio
async def test_hot_swap(db_session):
    """模型热加载切换不影响正在执行的推理。"""
    from gpu_service.model_manager import ModelManager
    # 加载默认模型
    await ModelManager.load_all()
    # 热切换
    success = await ModelManager.hot_swap("ball", "tracknet_v6")
    assert success is True
    assert ModelManager.get_version("ball") == "tracknet_v6"


# === 主应用侧测试 ===
# tests/unit/test_ai_inference_health.py
@pytest.mark.asyncio
async def test_health_check_marks_available(mock_redis):
    """健康检查成功时标记可用。"""
    mock_redis.exists.return_value = 1
    # ... 验证 Redis 标记逻辑


@pytest.mark.asyncio
async def test_inference_unavailable_triggers_degradation(mock_redis):
    """推理服务不可用时 ai_pipeline 进入降级模式。"""
    mock_redis.exists.return_value = 0
    from app.tasks.ai_inference_health import is_inference_available
    available = await is_inference_available()
    assert available is False
```

---

## 8. 验证清单

- [ ] 推理服务可独立启动：`uvicorn gpu_service.main:app --host 0.0.0.0 --port 8501`
- [ ] 4 个推理 API 端点正确返回检测结果
- [ ] `GET /health` 返回 200 + GPU 信息
- [ ] 模型启动时加载到 GPU 显存
- [ ] 模型热加载切换不影响正在执行的推理任务
- [ ] 热切换失败时保持旧模型运行
- [ ] 球检测超时返回 504
- [ ] 姿态估计超时触发降级（跳过姿态/动作步骤）
- [ ] 健康检查 Celery Beat 每 5min 执行
- [ ] 推理服务不可用时 ai_pipeline 进入降级模式
- [ ] 恢复后自动标记可用
- [ ] GPU OOM 触发服务重启
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- 推理服务 **必须** 独立部署在 GPU 实例，**禁止** 与主应用混部
- 推理 API **必须** 设置超时（asyncio.wait_for），**禁止** 无限等待
- 模型热切换 **必须** 异步加载 → 原子替换，**禁止** 同步阻塞
- 新模型加载失败 **必须** 保持旧模型运行，**禁止** 直接替换为 None
- 健康检查 **必须** 每 5min 执行，**禁止** 依赖人工监控
- 推理服务不可用时 ai_pipeline **必须** 进入降级模式，**禁止** 无限排队
- GPU OOM **必须** 自动恢复（重启+重新加载），**禁止** 手动干预
- 模型版本信息 **必须** 通过 /health 返回，**禁止** 隐藏版本号
