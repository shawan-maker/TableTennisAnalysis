"""
app/tasks/dashboard.py — 看板缓存失效 Celery 任务

依据：切片 13-infrastructure/ai_pipeline.md §5.4 级联第 3 步
（dashboard.bust_cache，send_task 异步投递）
R13-AIP-1: 级联"必须异步触发"约束修复 — 原 R12-Dash-1 修复采用内联 await，
本轮按设计反幻觉约束（ai_pipeline.md L103"级联链必须异步触发，禁止同步
阻塞流水线"）改为 Celery 投递，与 generate_advice_task 模式一致。
事件驱动（分析完成/比赛结束触发），无需 beat 注册。
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


@shared_task(bind=True, name="dashboard.bust_cache", max_retries=1, default_retry_delay=10)
def bust_cache_task(self, user_id: int, event: str):
    """
    看板缓存失效 — 异步调用，分析完成/比赛结束时触发。

    event 取值：analysis_complete（删 overview/technique/heatmap）/
    match_end（删 overview + winrate 三 period）。
    失败不阻塞业务（级联容错语义），重试间隔短（Redis 删键幂等）。
    """
    try:
        _run_async(_bust_cache_async(user_id, event))
        return {"status": "ok", "user_id": user_id, "event": event}
    except Exception as exc:
        logger.error(
            "bust_cache_task_failed",
            extra={"user_id": user_id, "event": event, "error": str(exc)},
        )
        try:
            raise self.retry()
        except self.MaxRetriesExceededError:
            return {"status": "error", "error": str(exc)}


async def _bust_cache_async(user_id: int, event: str):
    """看板缓存失效异步实现"""
    from app.services.dashboard_service import DashboardService

    await DashboardService.bust_cache(user_id, event)
