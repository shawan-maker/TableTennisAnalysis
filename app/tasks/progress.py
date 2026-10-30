"""
app/tasks/progress.py — 进度快照生成 Celery 任务

依据：切片 13-infrastructure/ai_pipeline.md §5.4 级联第 2 步
（progress_analysis.generate_snapshot，send_task 异步投递）
R13-AIP-1: 级联"必须异步触发"约束修复 — 原 R12-Prog-1 修复采用内联 await，
本轮按设计反幻觉约束（ai_pipeline.md L103"级联链必须异步触发，禁止同步
阻塞流水线"）改为 Celery 投递，与 generate_advice_task 模式一致。
事件驱动（分析流水线 Step 9 报告生成后触发），无需 beat 注册。
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
        # try 块只包裹探测（SUP-2 模式）：业务 RuntimeError 不得被误判
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


@shared_task(bind=True, name="progress_analysis.generate_snapshot", max_retries=1, default_retry_delay=30)
def generate_snapshot_task(self, user_id: int, report_id: int, result_data: dict | None = None):
    """
    进度快照生成 — 异步调用，分析报告完成后触发。

    逻辑：调用 ProgressService.generate_snapshot 写入 ProgressSnapshot
    （18 项指标快照，供趋势分析与跨报告对比）。
    失败不阻塞流水线（级联容错语义）。
    """
    try:
        _run_async(_generate_snapshot_async(user_id, report_id, result_data or {}))
        return {"status": "ok", "user_id": user_id, "report_id": report_id}
    except Exception as exc:
        logger.error(
            "generate_snapshot_task_failed",
            extra={"user_id": user_id, "report_id": report_id, "error": str(exc)},
        )
        try:
            raise self.retry()
        except self.MaxRetriesExceededError:
            return {"status": "error", "error": str(exc)}


async def _generate_snapshot_async(user_id: int, report_id: int, result_data: dict):
    """进度快照生成异步实现"""
    from app.services.progress_service import ProgressService

    await ProgressService.generate_snapshot(
        user_id=user_id, report_id=report_id, result_data=result_data,
    )
