"""Celery tasks — AI 推理健康检查"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.ai_inference_health.check_inference_health")
def check_inference_health():
    """AI 推理服务健康检查（每 5 分钟）"""
    from app.core.config import settings

    logger.info("Running ai_inference_health.check_inference_health")
    # TODO: 调用 inference 健康检查端点，更新 Redis 健康状态
    return {"status": "ok", "mock": settings.AI_INFERENCE_MOCK}
