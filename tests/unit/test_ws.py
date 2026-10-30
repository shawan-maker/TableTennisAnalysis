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


def test_ws_subscribe_sends_sync_match(ws_setup, monkeypatch):
    """R12-SC-2: subscribe 比赛频道 → 推送 sync_match 全量同步（API §14.2/§14.4）

    get_match_detail 以 monkeypatch 替换（WS 测试遵循仅 Redis+JWT 原则，
    DB 查询路径由 scoring 测试覆盖）
    """
    from app.main import app
    from app.core.security import create_access_token, generate_jti
    from app.services.scoring_service import ScoringService

    fake_detail = {
        "status": "in_progress",
        "current_score": "7:5",
        "score_sequence": [
            {"sequence": 1, "scorer": "user", "score_method": "loop",
             "technique_action": None, "game_number": 1},
            {"sequence": 2, "scorer": "opp", "score_method": "smash",
             "technique_action": None, "game_number": 1},
        ],
    }

    async def _fake_get_match_detail(user_id, match_id):
        return fake_detail

    monkeypatch.setattr(
        ScoringService, "get_match_detail", staticmethod(_fake_get_match_detail)
    )

    token = create_access_token({"sub": "12345", "jti": generate_jti()})

    with TestClient(app) as client:
        with client.websocket_connect("/ws", subprotocols=[f"jwt.{token}"]) as ws:
            connected = ws.receive_json()
            assert connected["event"] == "connected"

            # 订阅比赛频道
            ws.send_json({"event": "subscribe", "match_id": 2001})

            subscribed = ws.receive_json()
            assert subscribed["event"] == "subscribed"
            assert subscribed["data"]["match_id"] == 2001

            # R12-SC-2: 订阅后收到 sync_match 全量同步
            sync = ws.receive_json()
            assert sync["event"] == "sync_match"
            data = sync["data"]
            assert data["match_id"] == 2001
            assert data["status"] == "in_progress"
            assert data["current_score"] == "7:5"
            assert len(data["score_sequence"]) == 2
            assert data["score_sequence"][0]["scorer"] == "user"


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
            # R5-Infra-5: 频道命名统一为 ws:relay:ws:user:{user_id}
            r = sync_redis.from_url(settings.redis_url_computed, decode_responses=True)
            r.publish(
                "ws:relay:ws:user:12345",
                json.dumps(
                    {"event": "test_message", "data": {"msg": "hello world"}}
                ),
            )

            # 接收中继消息
            data = ws.receive_json()
            assert data["event"] == "test_message"
            assert data["data"]["msg"] == "hello world"


# =================================================================
# 比赛房间广播（R12-SC-5）
# =================================================================

def test_ws_match_room_broadcast(ws_setup):
    """R12-SC-5: 订阅比赛频道 → ws_manager.broadcast_to_room 房间广播中继到客户端

    覆盖完整生产链路（R5-Infra-5 频道命名一致性）：
    ScoringService 记分 → ws_manager.broadcast_to_room("ws:match:{id}")
    → Redis ws:relay:ws:match:{id} → 端点 subscribe 中继 → 客户端 score_update。
    """
    from app.main import app
    from app.core.security import create_access_token, generate_jti
    from app.core.websocket import manager as ws_manager
    from app.core import redis as redis_module

    token = create_access_token({"sub": "12345", "jti": generate_jti()})

    with TestClient(app) as client:
        with client.websocket_connect("/ws", subprotocols=[f"jwt.{token}"]) as ws:
            ws.receive_json()  # connected

            # 订阅比赛 3001 频道（用户 12345 无该比赛 → sync_match 404 跳过，
            # 仅有 subscribed 确认，房间广播行为不受影响）
            ws.send_json({"event": "subscribe", "match_id": 3001})
            subscribed = ws.receive_json()
            assert subscribed["event"] == "subscribed"
            assert subscribed["data"]["match_id"] == 3001

            # 等待 pubsub 订阅就绪
            time.sleep(0.5)

            # 用真实生产广播器发布（ScoringService L323 同款调用）。
            # 每次发布前重置 Redis 模块单例：广播器经 get_redis() 取连接，
            # 每次 asyncio.run 使用全新事件循环 —— 需要独立连接池；
            # 发布后同样重置，避免遗留绑定到已关闭循环的连接池。
            # （端点已持有的旧 pubsub/redis 引用不受影响 — Redis 服务端
            # pubsub 投递与发布方连接的事件循环归属无关）
            async def _broadcast(room_id: str, message: str):
                redis_module._redis_client = None
                redis_module._redis_pool = None
                await ws_manager.broadcast_to_room(room_id, message)
                redis_module._redis_client = None
                redis_module._redis_pool = None

            ws_message = json.dumps({
                "event": "score_update",
                "data": {
                    "match_id": 3001,
                    "current_score": "8:5",
                    "scorer": "user",
                    "score_method": "loop",
                },
            })

            asyncio.run(_broadcast("ws:match:3001", ws_message))

            # 客户端收到房间广播中继的 score_update
            data = ws.receive_json()
            assert data["event"] == "score_update"
            assert data["data"]["match_id"] == 3001
            assert data["data"]["current_score"] == "8:5"

            # 未订阅的另一比赛房间广播不被中继（频道隔离）
            asyncio.run(_broadcast(
                "ws:match:9999",
                json.dumps({"event": "score_update", "data": {"match_id": 9999}}),
            ))
            # 留出投递时间窗：若 9999 被错误中继，消息将先于 pong 排队
            time.sleep(0.5)

            ws.send_json({"event": "ping"})
            pong = ws.receive_json()
            assert pong["event"] == "pong"
