"""
app/core/database.py — SQLAlchemy 2.0 async 数据库引擎与会话管理

架构约束：§2.3 后端技术栈 / §5.1 数据库连接
依据：切片 13-infrastructure/docker.md §6.2 数据库连接池配置
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类 — 所有 ORM Model 继承此类"""

    pass


# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    echo=settings.DEBUG and settings.ENV == "development",
    pool_pre_ping=True,  # 连接前检查可用性，防止数据库端断开空闲连接
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
