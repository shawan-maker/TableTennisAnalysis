"""
tests/unit/test_ws.py — WebSocket 端点测试

依据：API §14 WebSocket / 切片 12-notification/backend.md §6.2
覆盖：认证/无token/无效token/ping-pong/在线状态/断连清理/消息中继

注意：WebSocket 端点仅使用 Redis + JWT，不访问数据库。
     使用 starlette.testclient.TestClient（同步）测试 WebSocket。
"""

import asyncio
import json
import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture(scope="function")
def ws_setup():
    """WebSocket 测试前清理 Redis + 重置 Redis 单例"""
    from app.core.config import settings
    from app.core import redis as redis_module
    import redis.asyncio as aioredis

    async def _clean():
        r = aioredis.from_url(settings.redis_url_computed, decode_responses=True)
        for pattern in ["scoring:match:*", "ws:online:*", "ws:relay:*", "ws:user:*"]:
            keys = await r.keys(pattern)
            if keys:
                await r.delete(*keys)
        await r.aclose()

    # 重置 Redis 全局单例（避免跨事件循环失效）
    redis_module._redis_client = None
    redis_module._redis_pool = None

    asyncio.run(_clean())
    yield
    # 重置 + 清理
    redis_module._redis_client = None
    redis_module._redis_pool = None
    asyncio.run(_clean())


# =================================================================
# 认证
# =================================================================

def test_ws_connect_with_valid_token(ws_setup):
    """有效 JWT → 接收 connected 事件"""
    from app.main import app
    from app.core.security import create_access_token, generate_jti

    token = create_access_token({"sub": "12345", "jti": generate_jti()})

    with TestClient(app) as client:
        with client.websocket_connect("/ws", subprotocols=[f"jwt.{token}"]) as ws:
            data = ws.receive_json()
            assert data["event"] == "connected"
            assert data["data"]["user_id"] == 12345


def test_ws_connect_without_token(ws_setup):
    """无 token → 关闭 4001"""
    from app.main import app

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
        assert exc_info.value.code == 4001


def test_ws_connect_with_invalid_token(ws_setup):
    """无效 token → 关闭 4001"""
    from app.main import app

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/ws", subprotocols=["jwt.invalid_garbage_token"]
            ) as ws:
                ws.receive_json()
        assert exc_info.value.code == 4001


# =================================================================
# 心跳
# =================================================================

def test_ws_ping_pong(ws_setup):
    """发送 ping → 接收 pong"""
    from app.main import app
    from app.core.security import create_access_token, generate_jti

    token = create_access_token({"sub": "12345", "jti": generate_jti()})

    with TestClient(app) as client:
        with client.websocket_connect("/ws", subprotocols=[f"jwt.{token}"]) as ws:
            # 先接收 connected 事件
            connected = ws.receive_json()
            assert connected["event"] == "connected"

            # 发送 ping
            ws.send_json({"event": "ping"})

            # 接收 pong
            pong = ws.receive_json()
            assert pong["event"] == "pong"
            assert pong["data"]["token_expired"] is False


# =================================================================
# 在线状态
# =================================================================

def test_ws_online_status(ws_setup):
    """连接后 Redis 在线状态存在"""
    from app.main import app
    from app.core.config import settings
    from app.core.security import create_access_token, generate_jti
    import redis.asyncio as aioredis

    token = create_access_token({"sub": "12345", "jti": generate_jti()})

    with TestClient(app) as client:
        with client.websocket_connect("/ws", subprotocols=[f"jwt.{token}"]) as ws:
            ws.receive_json()  # connected

            # 等待 endpoint 完成 setex（connected 事件先于 setex 发送）
            time.sleep(0.5)

            # 检查 Redis 在线标记
            async def _check():
                r = aioredis.from_url(
                    settings.redis_url_computed, decode_responses=True
                )
                exists = await r.exists("ws:online:12345")
                await r.aclose()
                return exists

            exists = asyncio.run(_check())
            assert exists > 0


def test_ws_disconnect_cleanup(ws_setup):
    """断连后 Redis 在线状态清除"""
    from app.main import app
    from app.core.config import settings
    from app.core.security import create_access_token, generate_jti
    import redis.asyncio as aioredis

    token = create_access_token({"sub": "12345", "jti": generate_jti()})

    with TestClient(app) as client:
        with client.websocket_connect("/ws", subprotocols=[f"jwt.{token}"]) as ws:
            ws.receive_json()  # connected

    # 等待清理完成
    time.sleep(1.0)

    async def _check():
        r = aioredis.from_url(settings.redis_url_computed, decode_responses=True)
        exists = await r.exists("ws:online:12345")
        await r.aclose()
        return exists

    exists = asyncio.run(_check())
    assert exists == 0


# =================================================================
# Redis pubsub 消息中继
# =================================================================

def test_ws_relay_message(ws_setup):
    """Redis pubsub 消息中继 → 客户端接收"""
    from app.main import app
    from app.core.config import settings
    from app.core.security import create_access_token, generate_jti
    import redis as sync_redis

    token = create_access_token({"sub": "12345", "jti": generate_jti()})

    with TestClient(app) as client:
        with client.websocket_connect("/ws", subprotocols=[f"jwt.{token}"]) as ws:
            ws.receive_json()  # connected

            # 等待 pubsub 订阅就绪
            time.sleep(0.5)

            # 通过同步 Redis 客户端发布消息
            r = sync_redis.from_url(settings.redis_url_computed, decode_responses=True)
            r.publish(
                "ws:user:12345",
                json.dumps(
                    {"event": "test_message", "data": {"msg": "hello world"}}
                ),
            )

            # 接收中继消息
            data = ws.receive_json()
            assert data["event"] == "test_message"
            assert data["data"]["msg"] == "hello world"
