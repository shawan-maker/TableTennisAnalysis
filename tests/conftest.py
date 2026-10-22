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
    同时清理 Redis 缓存，确保 S2 scoring 模块的 Redis INCR 序号不跨测试污染。
    使用真实的 PostgreSQL 数据库（通过 Docker Compose 启动）。
    """
    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 清理 Redis（scoring 模块在测试间残留的序号/比分等）
    try:
        redis = await get_redis()
        # 删除所有 scoring:match:* 和 ws:* 相关的 key
        for pattern in ["scoring:match:*", "ws:online:*", "ws:relay:*", "ws:user:*", "quota:analysis:*", "share:count:*", "ai_pipeline:circuit_breaker:*", "dashboard:*", "gamification:*", "progress:*", "membership:*", "payment:*", "quota:bonus:*", "downgrade:*"]:
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
    except Exception:
        pass  # Redis 未连接时不影响测试

    yield

    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # 清理 Redis
    try:
        redis = await get_redis()
        for pattern in ["scoring:match:*", "ws:online:*", "ws:relay:*", "ws:user:*", "quota:analysis:*", "share:count:*", "ai_pipeline:circuit_breaker:*", "dashboard:*", "gamification:*", "progress:*", "membership:*", "payment:*", "quota:bonus:*", "downgrade:*"]:
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
    except Exception:
        pass


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


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session) -> User:
    """创建管理员测试用户"""
    from app.core.config import settings
    user = User(
        openid="test_admin_openid",
        nickname="管理员",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    # 动态将管理员 ID 加入配置
    settings.ADMIN_USER_IDS = str(user.id)
    return user


@pytest_asyncio.fixture(scope="function")
async def admin_auth(admin_user) -> dict:
    """管理员认证信息"""
    access_token = create_access_token(
        {"sub": str(admin_user.id), "jti": generate_jti()})
    return {
        "access_token": access_token,
        "user_id": admin_user.id,
        "user": admin_user,
    }


@pytest_asyncio.fixture(scope="function")
async def admin_headers(admin_auth) -> dict:
    """管理员认证请求头"""
    return {"Authorization": f"Bearer {admin_auth['access_token']}"}


@pytest_asyncio.fixture(scope="function")
async def seed_tiers(db_session):
    """预置会员等级配置数据"""
    from app.models.membership import MembershipTierConfig

    tiers = [
        MembershipTierConfig(
            tier="free", name="免费",
            price_monthly_cents=0, price_quarterly_cents=0, price_yearly_cents=0,
            benefits=["每日3次分析", "记分牌", "数据看板", "社区浏览"],
            quota_config={"daily_analysis_limit": 3},
            sort_order=0,
        ),
        MembershipTierConfig(
            tier="member", name="会员",
            price_monthly_cents=1900, price_quarterly_cents=4900, price_yearly_cents=16800,
            benefits=["无限分析", "训练方案", "训练单", "3D教学", "历史对比"],
            quota_config={"daily_analysis_limit": -1},
            sort_order=1,
        ),
        MembershipTierConfig(
            tier="pro", name="专业",
            price_monthly_cents=3900, price_quarterly_cents=9900, price_yearly_cents=35800,
            benefits=["无限分析", "高级分析", "对手建模", "月度报告", "训练方案"],
            quota_config={"daily_analysis_limit": -1},
            sort_order=2,
        ),
        MembershipTierConfig(
            tier="coach", name="教练",
            price_monthly_cents=9900, price_quarterly_cents=26900, price_yearly_cents=89900,
            benefits=["学员管理", "批量分析", "教练工具", "专业版全部权益"],
            quota_config={"daily_analysis_limit": -1},
            sort_order=3,
        ),
    ]
    for t in tiers:
        db_session.add(t)
    await db_session.commit()
    return tiers
