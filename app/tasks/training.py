"""
app/tasks/training.py — 训练建议生成 Celery 任务

依据：切片 07-training_advice/backend.md §5（generate_advice_task 定义）
R12-Training-B1: 补齐缺失的 Celery 任务，接通"分析报告完成 → 异步生成训练建议 → WS 推送"链路
事件驱动（分析流水线 Step 9 报告生成后触发），无需在 beat_schedule 注册定时触发。
"""

import asyncio
import logging

from celery import shared_task

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
        # try 块只包裹探测：业务 RuntimeError 不得被误判为"无循环"后
        # 对已消费协程再次 asyncio.run（会掩盖原始异常，见 ai_pipeline/tasks.py）
        return asyncio.run(coro)
    # 已有运行中的事件循环，在新线程中运行；业务异常经 future.result() 原样重抛
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


@shared_task(bind=True, name="training_advice.generate_advice", max_retries=1, default_retry_delay=30)
def generate_advice_task(self, user_id: int, report_id: int):
    """
    训练建议生成 — 异步调用，分析报告完成后触发。

    逻辑：
    1. 接收 user_id + report_id，调用 TrainingAdviceService.generate_advice()
    2. 基于分析报告 + 历史趋势 + 知识库规则引擎生成个性化训练建议
    3. 生成完成后通过 WS 推送通知用户

    注意：此任务为事件驱动（分析流水线完成后 delay 触发），
    无需在 beat_schedule 中注册定时触发。
    """
    try:
        _run_async(_generate_advice_async(user_id, report_id))
        return {"status": "ok", "user_id": user_id, "report_id": report_id}
    except Exception as exc:
        logger.error(
            "generate_advice_task_failed",
            extra={"user_id": user_id, "report_id": report_id, "error": str(exc)},
        )
        # R12-AIPipeline-1: 失败路径显式重试（max_retries=1）。
        # 注意不传 exc —— Celery 语义：传 exc 时耗尽后重抛原异常而非
        # MaxRetriesExceededError，下方优雅降级分支将不可达。
        try:
            raise self.retry()
        except self.MaxRetriesExceededError:
            return {"status": "error", "error": str(exc)}


async def _generate_advice_async(user_id: int, report_id: int):
    """训练建议生成异步实现 — 生成后 WS 推送通知"""
    from app.services.training_service import TrainingAdviceService
    from app.services.notification_service import NotificationService

    advice = await TrainingAdviceService.generate_advice(user_id=user_id, report_id=report_id)

    # WS 推送：训练建议已生成
    try:
        await NotificationService.push_ws_message(
            user_id,
            "advice_ready",
            {
                "report_id": report_id,
                "is_first_analysis": advice.get("is_first_analysis", False),
                "suggestion_count": len(advice.get("suggestions", [])),
            },
        )
    except Exception as e:
        logger.warning("advice_ready_ws_push_failed: %s", e)
