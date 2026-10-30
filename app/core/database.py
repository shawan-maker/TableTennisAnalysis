"""
app/core/database.py — SQLAlchemy 2.0 async 数据库引擎与会话管理

架构约束：§2.3 后端技术栈 / §5.1 数据库连接
依据：切片 13-infrastructure/docker.md §6.2 数据库连接池配置
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类 — 所有 ORM Model 继承此类"""

    pass


# R13-Test-N3: 跨 event loop 隔离 —— asyncpg 异步连接绑定创建它的 event loop，
# loop 关闭后连接死亡（RuntimeError: Event loop is closed / attached to a
# different loop）。以下场景每次执行都是新 loop，共享队列池必检出死连接：
#   1) pytest-asyncio 每测试独立 loop（tests/conftest.py 顶部置 DB_NULLPOOL=1）
#   2) Celery 任务每任务 asyncio.run（app/core/celery.py 顶部置 DB_NULLPOOL=1）
#   3) DEBUG 开发态（task_always_eager=True 时请求内 .delay 触发任务线程循环）
# 这些场景改用 NullPool（每次 checkout 在当前 loop 新建连接，会话结束即关，
# 不会跨 loop 残留）；生产 Web 主进程（单一常驻 loop、eager 关闭）保留
# 队列池以获得连接复用。
_DB_NULLPOOL = (
    os.environ.get("DB_NULLPOOL", "") not in ("", "0", "false", "False")
    or settings.DEBUG
)

_ENGINE_KWARGS: dict = {
    "echo": settings.DEBUG and settings.ENV == "development",
    "pool_pre_ping": True,  # 连接前检查可用性，防止数据库端断开空闲连接
}
if _DB_NULLPOOL:
    _ENGINE_KWARGS["poolclass"] = NullPool
else:
    _ENGINE_KWARGS.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    **_ENGINE_KWARGS,
)

# 异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入 — 提供数据库会话。

    使用方式：
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_async_session() -> AsyncSession:
    """
    Service 层直接使用的异步会话上下文管理器入口。

    使用方式（Service 层）：
        async with get_async_session() as db:
            ...
    """
    return async_session_factory()
