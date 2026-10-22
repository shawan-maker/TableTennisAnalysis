# 共享测试 Fixture �?conftest.py

> **模块名称**：`infrastructure / conftest`
> **定位**：所有垂直切片测试的公共 fixture �?setup/teardown 逻辑
> **依据**：INF-3 �?统一测试基础设施，消除各切片重复定义�?fixture

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 统一 fixture | 所有切片测试共�?`client`、`auth_user`、`db_session`、`mock_redis`、`admin_user` |
| 异步支持 | 基于 `pytest-asyncio`，所�?async fixture 自动注入事件循环 |
| 隔离�?| 每个测试用例独立数据库会�?+ 独立 Redis mock，互不污�?|
| 快速回�?| 使用内存 SQLite + fakeredis，无需外部依赖 |

---

## 2. 完整实现

```python
# tests/conftest.py
"""共享测试 fixture �?所有垂直切片测试公共基础设施�?
依赖�?  - pytest-asyncio
  - httpx (用于 AsyncClient)
  - fakeredis
  - factory-boy (可选，生成测试数据)
"""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# 1. 事件循环（全局，避免每个测试新建循环）
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """会话级事件循环，所�?async fixture 共享�?""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# 2. 应用实例（每次测试新建，保证隔离�?# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def app():
    """创建 FastAPI 应用实例，覆盖依赖项�?""
    # 延迟导入，避免在收集阶段加载
    from app.main import create_app

    application = create_app()

    # 覆盖 get_redis �?mock_redis
    mock_redis = MockRedis()
    application.dependency_overrides = _build_override_map(mock_redis)

    yield application

    # teardown：清理覆�?    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """异步 HTTP 测试客户端�?
    用法::

        async def test_something(client):
            resp = await client.get("/api/v1/matches")
            assert resp.status_code == 200
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# 3. 模拟已认证用户（普通用户）
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def auth_user():
    """模拟已认证普通用户�?
    返回 UserDTO，含 id=1001, role=user, tier=pro�?    """
    return {
        "id": 1001,
        "username": "test_user",
        "email": "test_user@example.com",
        "role": "user",
        "tier": "pro",
        "is_active": True,
        "access_token": "mock_access_token_1001",
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }


@pytest_asyncio.fixture
async def auth_headers(auth_user):
    """携带普通用�?JWT 的请求头�?""
    from app.core.security import create_access_token
    token = create_access_token({"sub": str(auth_user["id"]), "role": auth_user["role"]})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 4. 模拟管理员用�?# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def admin_user():
    """模拟已认证管理员用户�?
    返回 UserDTO，含 id=1, role=admin, tier=pro�?    """
    return {
        "id": 1,
        "username": "admin",
        "email": "admin@example.com",
        "role": "admin",
        "tier": "pro",
        "is_active": True,
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }


@pytest_asyncio.fixture
async def admin_headers(admin_user):
    """携带管理�?JWT 的请求头�?""
    from app.core.security import create_access_token
    token = create_access_token({"sub": str(admin_user["id"]), "role": admin_user["role"]})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 5. 模拟数据库会话（内存 SQLite，事务回滚隔离）
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """模拟数据库会话�?
    - 使用内存 SQLite，表结构�?alembic 迁移�?metadata.create_all 创建
    - 每个测试结束后事务回滚，保证数据隔离
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    from app.models.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        # 注入到依赖覆�?        with patch("app.core.database.get_async_session", return_value=_async_gen(session)):
            yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# 6. 模拟 Redis（fakeredis，异步兼容）
# ---------------------------------------------------------------------------

class MockRedis:
    """轻量 Redis mock，支�?get/set/setex/delete/exists 等常用操作�?""

    def __init__(self):
        self._store: dict[bytes, bytes] = {}
        self._expiry: dict = {}  # TTL 跟踪: key -> expiry_timestamp

    async def get(self, key: str):
        import time
        k = key.encode() if isinstance(key, str) else key
        # Check TTL expiry
        if k in self._expiry:
            if time.time() > self._expiry[k]:
                self._store.pop(k, None)
                del self._expiry[k]
                return None
        return self._store.get(k)

    async def set(self, key: str, value: str, ex: int | None = None):
        k = key.encode() if isinstance(key, str) else key
        self._store[k] = value.encode() if isinstance(value, str) else value
        if ex:
            import time
            self._expiry[k] = time.time() + ex
        return True

    async def setex(self, key: str, seconds: int, value: str):
        import time
        await self.set(key, value)
        k = key.encode() if isinstance(key, str) else key
        self._expiry[k] = time.time() + seconds
    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            k = key.encode() if isinstance(key, str) else key
            if self._store.pop(k, None) is not None:
                deleted += 1
            self._expiry.pop(k, None)  # Clean expiry entry
        return deleted

    async def exists(self, key: str):
        k = key.encode() if isinstance(key, str) else key
        return 1 if k in self._store else 0

    async def expire(self, key: str, seconds: int):
        import time
        k = key.encode() if isinstance(key, str) else key
        self._expiry[k] = time.time() + seconds
        return True

    async def ttl(self, key: str):
        import time
        k = key.encode() if isinstance(key, str) else key
        if k not in self._expiry:
            return -1
        remaining = int(self._expiry[k] - time.time())
        return max(0, remaining)

    async def incr(self, key: str):
        k = key.encode() if isinstance(key, str) else key
        val = int(self._store.get(k, b"0")) + 1
        self._store[k] = str(val).encode()
        return val

    async def hset(self, name: str, key=None, value=None, mapping=None):
        """支持单字�?(key, value) 和批�?mapping={field: val} 两种形式�?""
        count = 0
        if mapping:
            for field, val in mapping.items():
                k = f"{name}:{field}"
                self._store[k.encode() if isinstance(k, str) else k] = val.encode() if isinstance(val, str) else val
                count += 1
        if key is not None and value is not None:
            k = f"{name}:{key}"
            self._store[k.encode() if isinstance(k, str) else k] = value.encode() if isinstance(value, str) else value
            count += 1
        return count

    async def hget(self, name: str, key: str):
        k = f"{name}:{key}"
        return self._store.get(k.encode() if isinstance(k, str) else k)

    async def hgetall(self, name: str):
        prefix = f"{name}:"
        result = {}
        for k, v in self._store.items():
            k_str = k.decode() if isinstance(k, bytes) else k
            if k_str.startswith(prefix):
                field = k_str[len(prefix):]
                v_str = v.decode() if isinstance(v, bytes) else v
                result[field] = v_str
        return result

    async def decr(self, key: str) -> int:
        k = key.encode() if isinstance(key, str) else key
        val = int(self._store.get(k, b"0")) - 1
        self._store[k] = str(val).encode()
        return val

    async def incrby(self, name: str, amount: int = 1) -> int:
        """增量操作——支持指定增量值。"""
        k = name.encode() if isinstance(name, str) else name
        val = int(self._store.get(k, b"0")) + amount
        self._store[k] = str(val).encode()
        return val

    async def decrby(self, name: str, amount: int = 1) -> int:
        """减量操作——支持指定减量值。"""
        k = name.encode() if isinstance(name, str) else name
        val = int(self._store.get(k, b"0")) - amount
        self._store[k] = str(val).encode()
        return val

    async def publish(self, channel: str, message: str) -> int:
        """发布消息到频道——Mock 实现仅返回订阅者数 0。"""
        # MockRedis 不维护真实 pub/sub，返回 0 表示无订阅者
        return 0

    async def sadd(self, name: str, *values) -> int:
        """集合添加——返回新增成员数。"""
        k = name.encode() if isinstance(name, str) else name
        set_key = f"_set:{k.decode() if isinstance(k, bytes) else k}"
        if set_key not in self._store:
            self._store[set_key.encode()] = b""
            existing = set()
        else:
            raw = self._store[set_key.encode()]
            existing = set(raw.split(b"\n")) if raw else set()

        added = 0
        for v in values:
            v_bytes = v.encode() if isinstance(v, str) else v
            if v_bytes not in existing:
                existing.add(v_bytes)
                added += 1

        self._store[set_key.encode()] = b"\n".join(existing)
        return added

    async def close(self):
        pass

    # R19-P3-G: 补 pubsub() 支持 notification WS 端点测试
    def pubsub(self):
        """返回 MockPubSub 实例，支持 psubscribe/get_message 接口。"""
        return MockPubSub()


class MockPubSub:
    """轻量 pubsub mock，支持 psubscribe/get_message/close 接口。
    供 notification WS 端点测试使用（WSManager 通过 Redis pubsub relay 消费消息）。"""

    def __init__(self):
        self._subscriptions: dict[str, bool] = {}

    def psubscribe(self, pattern):
        """订阅指定 pattern（如 'ws:user:*' / 'ws:match:*'）。"""
        self._subscriptions[pattern] = True

    def subscribe(self, channel):
        """订阅指定 channel（精确匹配）。"""
        self._subscriptions[channel] = True

    async def get_message(self):
        """获取消息——Mock 实现返回 None，不阻塞事件循环。"""
        import asyncio
        await asyncio.sleep(0.01)
        return None

    def close(self):
        """清理订阅。"""
        self._subscriptions.clear()


@pytest_asyncio.fixture
async def mock_redis():
    """模拟 Redis 客户端�?
    每个测试获取独立实例，互不污染�?    """
    redis = MockRedis()
    yield redis
    redis._store.clear()


# ---------------------------------------------------------------------------
# 7. setup / teardown 钩子
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """全局 setup：在测试收集完成后、执行前运行�?""
    # 标记 async 测试模式
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "slow: marks slow tests")


def pytest_sessionstart(session):
    """会话开始时初始化�?""
    # 可在此处加载 .env.test 环境变量
    import os
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


def pytest_sessionfinish(session, exitstatus):
    """会话结束时清理�?""
    pass


async def _async_gen(session):
    """将同�?session 包装为异步生成器（兼�?FastAPI Depends）�?""
    yield session


def _build_override_map(mock_redis: "MockRedis") -> dict:
    """构建 FastAPI 依赖覆盖映射�?""
    from app.core.database import get_async_session
    from app.core.redis import get_redis

    async def _override_redis():
        yield mock_redis

    return {
        get_redis: _override_redis,
    }
```

---

## 3. 各切片使用示�?
```python
# tests/test_match_scoring.py
"""比赛记分切片测试 �?使用共享 fixture�?""

import pytest

pytestmark = pytest.mark.asyncio


class TestMatchScoring:
    """比赛记分 API 测试�?""

    async def test_create_match(self, client, auth_headers, db_session):
        """创建比赛 �?返回 201 + match_id�?""
        resp = await client.post(
            "/api/v1/matches",
            json={"opponent": "player_b", "score": "11:7"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert "match_id" in resp.json()

    async def test_get_overview_readonly(
        self, client, auth_headers, mock_redis
    ):
        """降级用户只读检�?(TD-2) �?设置降级标记后返回简化数据�?""
        await mock_redis.set("downgrade:report:readonly:1001", "1")
        resp = await client.get(
            "/api/v1/dashboard/overview",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json().get("is_readonly") is True
```

---

## 4. 依赖说明

| 依赖 | 版本 | 用�?|
|------|------|------|
| pytest | >=7.4 | 测试框架 |
| pytest-asyncio | >=0.23 | 异步测试支持 |
| httpx | >=0.27 | AsyncClient 测试 HTTP |
| aiosqlite | >=0.19 | 异步 SQLite 驱动 |
| fakeredis | >=2.21 | （可选）更完整的 Redis mock |

---

## 5. 约定

1. **所有切片测试统一 import**：`from tests.conftest import *`（可选）
2. **fixture 命名**：保�?`client`、`auth_user`、`auth_headers`、`admin_user`、`admin_headers`、`db_session`、`mock_redis` 不可�?3. **新增 fixture**：切片级 fixture 放各切片 `conftest.py`，公�?fixture 放此文件
4. **禁止**在切片测试中重复定义上述 5 个公�?fixture
