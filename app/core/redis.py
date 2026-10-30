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


def reset_redis_client() -> None:
    """丢弃全局客户端/池引用（不主动关闭连接）— 跨 event loop 隔离用。

    R13-Test-N3: 异步连接绑定创建它的 event loop，loop 关闭后连接即死亡
    （首条命令抛 RuntimeError: Event loop is closed）。全局单例池在"每次
    执行一个新 loop"场景（pytest-asyncio 每测试独立 loop；Celery 任务经
    _run_async/asyncio.run 每任务新 loop）下，会检出上一个已关闭 loop 归还
    的连接。调用本函数强制下一次 get_redis() 在当前 loop 重建连接池。
    """
    global _redis_pool, _redis_client
    _redis_client = None
    _redis_pool = None


async def run_isolated(coro):
    """跨 event loop 隔离执行协程 — Celery 任务体标准包装（R13-Test-N3）。

    前置 reset_redis_client() 丢弃调用方 loop 的池引用，任务体 get_redis()
    在自身 loop 上重建；结束后在任务 loop 上 close_redis() 清理本任务连接
    （loop 即将随 asyncio.run 关闭，事前清理避免 socket 悬挂），异常时兜底
    reset。eager 测试（主循环内 .delay → 新线程 loop）与生产 worker（每任务
    asyncio.run 新 loop）均适用；eager 模式 .delay 同步阻塞调用方，无并发
    使用全局池的竞态。
    """
    reset_redis_client()
    try:
        return await coro
    finally:
        try:
            await close_redis()
        except Exception:
            reset_redis_client()
