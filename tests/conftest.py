"""
tests/conftest.py — 共享测试 Fixture

依据：切片 13-infrastructure/conftest.py.md
功能：client / auth_user / db_session

依赖说明（R4-Infra-5）：
  本测试套件依赖外部真实 PostgreSQL + Redis 服务（通过 Docker Compose 启动），
  不使用内存 SQLite + fakeredis。原因：测试覆盖 PostgreSQL 特有特性（JSONB、
  复合类型、分区表、ON CONFLICT 等）以及 Redis pubsub/INCR 原子操作行为，
  内存替代品无法保证等价性。

  当 PostgreSQL/Redis 不可用时，测试将在 fixture 层报错（而非跳过），
  以便及早暴露环境问题。
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

# R13-Test-N3: 测试进程启用 DB NullPool —— pytest-asyncio 每测试独立 event loop
# （R13-Test-N1），共享连接池会检出上一个已关闭 loop 的 asyncpg 连接
# （RuntimeError: Event loop is closed），Celery 任务线程循环同理。
# 必须在下方 app.core.* 导入（最终导入 app.core.database）之前设置。
os.environ.setdefault("DB_NULLPOOL", "1")

from app.core.config import settings
from app.core.database import Base, async_session_factory, engine
from app.core.redis import get_redis
from app.core.security import create_access_token, create_refresh_token, generate_jti
from app.models.user import ConsentLog, User

# 测试环境强制 Celery eager 模式 — pipeline 同步执行，确保任务状态在测试内完成
from app.core.celery import celery_app
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

# R12-Gam-13: 测试环境默认禁用 API 限流 —
# 装饰器顺序修复（router 在上/limiter 在下）后限流真实生效，
# 大量测试请求（同一 client IP）会触发 429 污染测试断言。
# 限流专项测试（test_gamification TestRateLimit*）临时 limiter.enabled = True。
from app.core.limiter import limiter
limiter.enabled = False

# 测试环境禁用 SQL echo（减少输出噪音，DEBUG=True 用于保持 eager 模式）
engine.echo = False
import logging as _logging
_logging.getLogger("sqlalchemy.engine.Engine").setLevel(_logging.WARNING)


# R13-Test-N1: 移除自定义 session-scope event_loop fixture ——
# pytest-asyncio 0.24 中该模式已废弃（行为未定义，与 function-scope
# async fixture 生命周期竞态导致间歇性 "relation user does not exist"）。
# 循环作用域改由 pytest.ini 的 asyncio_default_fixture_loop_scope=function 管理。


@pytest_asyncio.fixture(scope="function", autouse=True)
async def _redis_pool_per_loop():
    """R13-Test-N2: 每测试独立 event loop 与全局 Redis 池的跨 loop 复用隔离。

    根因（py-spy + 探针实证）：pytest-asyncio 0.24 每个测试函数使用独立事件循环，
    而 get_redis() 的全局连接池跨测试复用 —— 上一测试（loop 已关闭）归还的连接
    仍满足 is_connected（reader/writer 非 None），被本测试检出后首个命令抛
    RuntimeError: Event loop is closed。该错误被 db_setup 清理分支 / 服务层
    except 分支静默吞掉，引发行为级污染（见 test_send_notification_online_no_db_write
    在多测试组合下离线路径误触发）。

    修复：测试前置丢弃全局引用 + 后置在当前 loop 上正常关闭连接池，
    确保每个测试在自身 loop 上重建连接池。生产环境单 loop 生命周期不受影响。
    """
    import app.core.redis as _redis_mod

    _redis_mod._redis_client = None
    _redis_mod._redis_pool = None
    yield
    try:
        await _redis_mod.close_redis()
    except Exception:
        # 防御：池中若残留旧 loop 死连接，disconnect 可能抛错 — 忽略并强制丢弃引用
        _redis_mod._redis_client = None
        _redis_mod._redis_pool = None


@pytest_asyncio.fixture(scope="function")
async def db_setup():
    """
    创建数据库表（测试前）+ 清理（测试后）。
    同时清理 Redis 缓存，确保 S2 scoring 模块的 Redis INCR 序号不跨测试污染。
    使用真实的 PostgreSQL 数据库（通过 Docker Compose 启动）。

    依赖外部 PostgreSQL + Redis（R4-Infra-5）：
    若不可用，fixture 将跳过（pytest 在 fixture 层 skip 依赖此结果的测试）。

    R13-Test-N1: 重建 schema 前 engine.dispose() 清空连接池 ——
    asyncpg 连接池中的空闲连接持有旧 schema 的 prepared statement 缓存，
    DROP/CREATE SCHEMA 后池内连接若复用会命中失效语句缓存，引发
    "relation user does not exist" 间歇性失败；dispose 强制全部重建。
    """
    # R13-Test-N1: 丢弃旧连接（避免 asyncpg 语句缓存与 schema 重建竞态）
    await engine.dispose()

    # 创建所有表（先清理 schema 以避免 PostgreSQL 复合类型残留）
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    # 清理 Redis（scoring 模块在测试间残留的序号/比分等）
    try:
        redis = await get_redis()
        # 删除所有 scoring:match:* 和 ws:* 相关的 key
        # R4-Auth-4: sms:rate:* → sms:sent:*（保留两者兼容旧测试缓存）
        # R12-Gam-13: LIMITER* — slowapi/limits Redis 存储 key（限流计数）
        for pattern in ["scoring:match:*", "ws:online:*", "ws:relay:*", "ws:user:*", "quota:analysis:*", "share:count:*", "ai_pipeline:circuit_breaker:*", "dashboard:*", "gamification:*", "progress:*", "membership:*", "payment:*", "quota:bonus:*", "downgrade:*", "export:count:*", "big_data:user:*", "sms:code:*", "sms:rate:*", "sms:sent:*", "config:*", "LIMITER*"]:
                keys = await redis.keys(pattern)
                if keys:
                    await redis.delete(*keys)
    except Exception:
        pass  # Redis 未连接时不影响测试

    yield

    # 清理（R13-Test-N1: 同样先 dispose 清空连接池再重建 schema）
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))

    # 清理 Redis
    try:
        redis = await get_redis()
        for pattern in ["scoring:match:*", "ws:online:*", "ws:relay:*", "ws:user:*", "quota:analysis:*", "share:count:*", "ai_pipeline:circuit_breaker:*", "dashboard:*", "gamification:*", "progress:*", "membership:*", "payment:*", "quota:bonus:*", "downgrade:*", "export:count:*", "big_data:user:*", "sms:code:*", "sms:rate:*", "sms:sent:*", "config:*", "LIMITER*"]:
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
