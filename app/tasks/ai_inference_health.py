"""Celery tasks — AI 推理健康检查

R12-BeatTasks-1: 补齐实现（原 TODO 空壳）。
依据：切片 13-infrastructure/ai_inference.md §6.2 —
GET {INFERENCE_BASE_URL}/health → 200 则 Redis 标记可用（60s TTL）；
超时/5xx → 清除可用标记 + 写入告警标记，恢复后自动清除 was_unavailable。
Mock 模式（AI_INFERENCE_MOCK=True，Phase 1 默认）：本地模拟推理服务恒可用，
直接写入可用标记，不发真实 HTTP 请求。
"""
import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Redis 健康状态键（设计 ai_inference.md §6.2）
HEALTH_KEY_AVAILABLE = "ai_inference:available"
HEALTH_KEY_WAS_UNAVAILABLE = "ai_inference:was_unavailable"
HEALTH_TTL_SECONDS = 60 * 2  # 检测周期 5min 的 2 倍兜底


async def _check_inference_health_async() -> dict:
    """健康检查异步实现 — Mock 直写可用标记；真实模式 GET /health"""
    from app.core.config import settings
    from app.core.redis import get_redis

    redis = await get_redis()

    if settings.AI_INFERENCE_MOCK:
        # Phase 1 Mock 模式：模拟推理服务恒可用
        await redis.setex(HEALTH_KEY_AVAILABLE, HEALTH_TTL_SECONDS, "1")
        return {"status": "healthy", "mock": True}

    import httpx

    inference_url = settings.INFERENCE_BASE_URL
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{inference_url}/health", timeout=10)
            if resp.status_code == 200:
                await redis.setex(HEALTH_KEY_AVAILABLE, HEALTH_TTL_SECONDS, "1")
                # 检查是否从不可用恢复
                was_unavailable = await redis.get(HEALTH_KEY_WAS_UNAVAILABLE)
                if was_unavailable:
                    await redis.delete(HEALTH_KEY_WAS_UNAVAILABLE)
                    logger.info("ai_inference_recovered", extra={"url": inference_url})
                return {"status": "healthy", "mock": False}
    except Exception as e:
        logger.warning(
            "ai_inference_health_check_failed",
            extra={"url": inference_url, "error": str(e)},
        )

    # 标记不可用 → ai_pipeline 进入降级模式
    await redis.delete(HEALTH_KEY_AVAILABLE)
    await redis.set(HEALTH_KEY_WAS_UNAVAILABLE, "1")
    # 告警标记（TD-9 健康检查告警：Redis 标记，管理告警通道接入在 S6+）
    await redis.setex("alert:gpu_health:ai_inference", 3600, "critical")
    logger.error(
        "ai_inference_unavailable_degraded_mode",
        extra={"url": inference_url},
    )
    return {"status": "unhealthy", "mock": False}


@shared_task(name="app.tasks.ai_inference_health.check_inference_health")
def check_inference_health():
    """AI 推理服务健康探测（每 5 分钟）

    更新 Redis 健康状态，供 ai_pipeline 降级判断与告警使用。
    """
    logger.info("Running ai_inference_health.check_inference_health")
    from app.core.redis import run_isolated
    result = asyncio.run(run_isolated(_check_inference_health_async()))
    return {"status": "ok", "health": result}
