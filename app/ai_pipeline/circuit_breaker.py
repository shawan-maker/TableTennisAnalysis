"""
app/ai_pipeline/circuit_breaker.py — AI 服务熔断器

依据：架构 §6.5 / 切片 13-infrastructure/ai_pipeline.md §5.3
功能：5 次连续失败 → 熔断 60s → 半开探针
"""

import logging
import time
from enum import Enum

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AICircuitBreaker:
    """
    AI 服务熔断器 — Redis 状态存储。

    用法：
        cb = AICircuitBreaker("table_detection")
        if cb.allow_request():
            try:
                result = call_ai_service()
                cb.record_success()
            except Exception:
                cb.record_failure()
        else:
            # 熔断中，走降级逻辑
            ...
    """

    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 60  # 秒

    def __init__(self, service_name: str):
        self.service_name = service_name
        self._state_key = f"ai_pipeline:circuit_breaker:{service_name}:state"
        self._failures_key = f"ai_pipeline:circuit_breaker:{service_name}:failures"
        self._opened_at_key = f"ai_pipeline:circuit_breaker:{service_name}:opened_at"

    async def get_state(self) -> CircuitState:
        """获取当前熔断状态"""
        redis = await get_redis()
        state = await redis.get(self._state_key)
        if state is None:
            return CircuitState.CLOSED

        if state == CircuitState.OPEN.value:
            # 检查是否已过恢复时间
            opened_at = await redis.get(self._opened_at_key)
            if opened_at and time.time() - float(opened_at) >= self.RECOVERY_TIMEOUT:
                # 转半开
                await redis.set(self._state_key, CircuitState.HALF_OPEN.value)
                return CircuitState.HALF_OPEN
            return CircuitState.OPEN

        return CircuitState(state)

    async def allow_request(self) -> bool:
        """是否允许请求"""
        state = await self.get_state()
        return state != CircuitState.OPEN

    async def record_success(self) -> None:
        """记录成功 — 重置计数器"""
        redis = await get_redis()
        await redis.delete(self._failures_key)
        await redis.set(self._state_key, CircuitState.CLOSED.value)

    async def record_failure(self) -> None:
        """记录失败 — 达到阈值则熔断"""
        redis = await get_redis()
        failures = await redis.incr(self._failures_key)

        if failures == 1:
            # 首次失败，设置 TTL（300s）避免计数器永久残留
            await redis.expire(self._failures_key, 300)

        if failures >= self.FAILURE_THRESHOLD:
            await redis.set(self._state_key, CircuitState.OPEN.value)
            await redis.set(self._opened_at_key, str(time.time()))
            logger.warning(
                "circuit_breaker_opened",
                extra={"service": self.service_name, "failures": failures},
            )
