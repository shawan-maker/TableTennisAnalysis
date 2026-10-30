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

from celery import shared_task
from sqlalchemy import update

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.video_analysis import AnalysisReport, PipelineStep, VideoTask
from app.ai_pipeline.circuit_breaker import AICircuitBreaker
from app.ai_pipeline.progress import ProgressTracker
from app.ai_pipeline.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 Celery 任务中运行异步协程 — 兼容 eager 模式下的事件循环嵌套

    R13-Test-N3: 每次执行经 run_isolated 隔离全局 Redis 池（前置 reset + 结束
    在任务自身 loop 上 close）—— 异步连接绑定创建 loop，loop 关闭后连接死亡
    （RuntimeError: Event loop is closed），跨 loop 复用全局池会检出上一个
    已关闭 loop 的连接（测试每测试一 loop + eager/生产 worker 每任务新 loop
    均命中，见 round13 报告 R13-Test-N2/N3）。
    """
    from app.core.redis import run_isolated
    coro = run_isolated(coro)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 无运行中的事件循环，直接 asyncio.run。
        # 注意：try 块必须只包裹 get_running_loop 探测 —— 若把 future.result()
        # 也纳入捕获范围，业务代码抛出的 RuntimeError 会被误判为"无事件循环"
        # 走 fallback 分支，对已消费协程再次 asyncio.run（运行循环中必炸），
        # 用 asyncio 环境错误掩盖原始业务异常（R12-AIPipeline-1 测试实证）。
        return asyncio.run(coro)
    # 已有运行中的事件循环（pytest-asyncio / uvicorn eager），在新线程中运行；
    # 协程内的业务异常经 future.result() 原样重抛，不进入上方探测分支
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


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
    # R12-AIPipeline-11: 先执行报告生成再标记步骤完成 —
    # 原 _exec_step(9, mock_fn=None) 会先 on_step_complete 再执行 ReportGenerator.generate，
    # 生成失败时步骤状态已完成（状态失真）。此处手工编排：start → 生成 → complete/failed
    step9_start = time.time()
    async with async_session_factory() as db:
        await ProgressTracker.on_step_start(task_id, 9, db)
    try:
        report_data = await ReportGenerator.generate(task_id, step_results)
        report_id = report_data["report_id"]
        step_results[9] = report_data
        duration_ms = int((time.time() - step9_start) * 1000)
        await ProgressTracker.on_step_complete(task_id, 9, report_data, duration_ms)
    except Exception as e:
        await ProgressTracker.on_step_failed(task_id, 9, str(e))
        raise

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
        # R12-VA-2: processing → completed 需状态机校验
        from app.ai_pipeline.progress import transition_task_status
        await transition_task_status(db, task_id, "completed")
        await db.commit()

    # WS 推送完成
    await ProgressTracker.on_task_complete(task_id, report_id)


@shared_task(bind=True, name="ai_pipeline.run_pipeline", max_retries=1, default_retry_delay=30)
def run_pipeline(self, task_id: int, oss_key: str):
    """Celery 任务入口 — 非生产环境通过 _run_async 运行异步逻辑

    R12-AIPipeline-1: 失败重试机制（设计 ai_pipeline.md 验证清单 —
    "超时正确触发重试（指数退避）、重试次数耗尽后标记 task.status=failed"）。
    重试耗尽后：标记最终失败 + 退还免费额度（R12-AIPipeline-2，设计 §refund_free_quota —
    "失败后免费额度必须退还（Redis DECR），禁止不退"）。
    """
    from celery.exceptions import MaxRetriesExceededError

    try:
        _run_async(run_pipeline_async(task_id, oss_key))
    except Exception as e:
        logger.error("pipeline_failed", extra={"task_id": task_id, "error": str(e)})
        try:
            # 未达重试上限：投递重试（指数退避，30s 起）。
            # 注意不传 exc —— Celery 语义（celery/app/task.py retry L732-741）：
            # 传 exc 时重试耗尽后"重抛原异常"而非 MaxRetriesExceededError，
            # 下方耗尽兜底分支将永远不可达 → 任务卡 processing + 免费额度不退。
            raise self.retry()
        except MaxRetriesExceededError:
            # 重试耗尽：标记最终失败 + 退还免费额度
            _run_async(_mark_task_failed(task_id, str(e), user_id=None))
            raise


async def _refund_free_quota(user_id: int) -> None:
    """
    R12-AIPipeline-2: 退还免费额度（分析最终失败时调用）——Redis DECR。

    设计 ai_pipeline.md §refund_free_quota：current > 0 才 DECR，防止负计数。
    使用 CST（UTC+8）日期 key，与 _check_free_quota 预扣键一致。
    """
    from datetime import datetime, timedelta, timezone

    from app.core.redis import get_redis

    redis = await get_redis()
    tz_cst = timezone(timedelta(hours=8))
    today = datetime.now(tz_cst).strftime("%Y%m%d")
    key = f"quota:analysis:{user_id}:{today}"
    current = int(await redis.get(key) or 0)
    if current > 0:
        await redis.decr(key)
        logger.info("free_quota_refunded", extra={"user_id": user_id, "key": key})


async def _mark_task_failed(task_id: int, error: str, user_id: int | None = None):
    """标记任务失败 + 退还免费额度（幂等）

    R12-AIPipeline-2: 失败退还额度（设计反幻觉约束 —
    "失败后必须退还免费额度（Redis DECR），禁止不退"）。
    幂等防护：仅当状态转换成功（allowed）时退额度 —
    eager 重试链中本函数可能被内层重跑与外层各调用一次，
    第二次 transition 已 failed→failed 被矩阵拒绝，不会重复退额度。
    user_id 由调用方传入；未传时从任务记录查询。
    """
    async with async_session_factory() as db:
        # R12-VA-2: processing → failed 需状态机校验（终态任务不再翻转）
        from app.ai_pipeline.progress import transition_task_status
        allowed = await transition_task_status(db, task_id, "failed")
        if allowed:
            task = await db.get(VideoTask, task_id)
            if task:
                task.error_message = error
                if user_id is None:
                    user_id = task.user_id
                await db.flush()
        await db.commit()

    # 退还免费额度：仅在本次实际完成状态转换时执行（防重复退还）
    if allowed and user_id is not None:
        try:
            await _refund_free_quota(user_id)
        except Exception as quota_err:
            # 退额度失败不阻塞失败标记流程（记日志便于补偿）
            logger.error(
                "free_quota_refund_failed",
                extra={"task_id": task_id, "user_id": user_id, "error": str(quota_err)},
            )


async def _exec_step(task_id: int, step: int, step_name: str, mock_fn, step_results: dict):
    """执行单步：更新状态 -> 熔断器检查 -> 执行 -> 记录结果"""
    start = time.time()

    async with async_session_factory() as db:
        await ProgressTracker.on_step_start(task_id, step, db)

    # AI 熔断器：包裹每个 AI 步骤调用
    # R12-AIPipeline-7: 共享 "ai_inference" 服务级熔断器（设计 §5.6 {service_name}=model_name，
    # 样例统一使用 "ai_inference"）— 原按 step_name 独立实例化会稀释保护语义：
    # 推理服务故障分散到 10 个独立计数器，单个永不达 5 次阈值，熔断失效
    cb = AICircuitBreaker("ai_inference")
    allowed = await cb.allow_request()

    if not allowed:
        # 熔断中，走降级逻辑（使用 mock 数据）
        logger.warning("circuit_breaker_tripped", extra={
            "task_id": task_id, "step": step, "service": step_name,
        })
        if mock_fn:
            result = mock_fn()
        else:
            result = {}
        step_results[step] = result
        duration_ms = int((time.time() - start) * 1000)
        await ProgressTracker.on_step_complete(task_id, step, result, duration_ms)
        return

    try:
        if mock_fn:
            result = mock_fn()
        else:
            result = {}
        step_results[step] = result
        await cb.record_success()
    except Exception as e:
        await cb.record_failure()
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
