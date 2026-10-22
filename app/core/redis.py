"""
app/core/redis.py — Redis 异步连接管理

架构约束：§2.3 后端技术栈 / §8 Redis Key 命名规范
依据：切片各模块 Redis Key 使用模式
"""

from typing import Optional

import redis.asyncio as redis

from app.core.config import settings

# 全局 Redis 连接池
_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


def _create_redis_pool() -> redis.ConnectionPool:
    """创建 Redis 连接池"""
    return redis.ConnectionPool.from_url(
        settings.redis_url_computed,
        max_connections=50,
        retry_on_timeout=True,
        retry_on_error=[redis.ConnectionError, redis.TimeoutError],
        health_check_interval=30,
        decode_responses=True,
    )


async def get_redis() -> redis.Redis:
    """
    获取 Redis 客户端 — 全局单例连接池。

    使用方式（Service 层）：
        redis_client = await get_redis()
        await redis_client.setex("key", 300, "value")

    使用方式（FastAPI 依赖注入）：
        @router.get("/")
        async def handler(redis_client: redis.Redis = Depends(get_redis)):
            ...
    """
    global _redis_pool, _redis_client

    if _redis_client is None:
        _redis_pool = _create_redis_pool()
        _redis_client = redis.Redis(connection_pool=_redis_pool)

    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接 — 应用关闭时调用"""
    global _redis_client, _redis_pool

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None

    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
