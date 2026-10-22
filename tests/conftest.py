"""
tests/conftest.py — 共享测试 Fixture

依据：切片 13-infrastructure/conftest.py.md
功能：client / auth_user / db_session / mock_redis
"""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, async_session_factory, engine
from app.core.redis import get_redis
from app.core.security import create_access_token, create_refresh_token, generate_jti
from app.models.user import ConsentLog, User


@pytest.fixture(scope="session")
def event_loop():
    """全局事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_setup():
    """
    创建数据库表（测试前）+ 清理（测试后）。

    使用真实的 PostgreSQL 数据库（通过 Docker Compose 启动）。
    """
    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session(db_setup) -> AsyncGenerator:
    """提供数据库会话"""
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_setup) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP 测试客户端 — 使用 ASGI transport 直接调用 FastAPI 应用。
    """
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session) -> User:
    """创建测试用户"""
    user = User(
        openid="test_openid_001",
        nickname="测试用户",
        avatar_url="https://example.com/avatar.png",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def auth_user(test_user) -> dict:
    """
    创建已认证用户 — 返回 access_token + refresh_token + user_id。
    """
    access_token = create_access_token({"sub": str(test_user.id), "jti": generate_jti()})
    refresh_token = create_refresh_token({"sub": str(test_user.id), "jti": generate_jti()})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": test_user.id,
        "user": test_user,
    }


@pytest_asyncio.fixture(scope="function")
async def auth_headers(auth_user) -> dict:
    """认证请求头"""
    return {"Authorization": f"Bearer {auth_user['access_token']}"}
