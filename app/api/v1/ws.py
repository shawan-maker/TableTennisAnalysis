"""
app/api/v1/ws.py — WebSocket 端点

依据：API §14 WebSocket / 切片 12-notification/backend.md §6.2
功能：Sec-WebSocket-Protocol 认证 + Redis pubsub 中继 + 心跳 + 断连清理
架构约束：§5.6 WebSocket / §15 约束 #30 重连

TODO(R4-Infra-7)：本端点当前绕过 app.core.websocket.WSManager，直接操作 Redis
pubsub 与在线状态。原因：WSManager.on_connect 内部调用 websocket.accept()
不带 subprotocol，与本端点所需的 Sec-WebSocket-Protocol JWT 认证流程冲突；
且 WSManager 使用 ws:relay:* 频道中继，与本端点的 ws:user:{id} 频道不同。
后续应重构 WSManager 支持 subprotocol accept + 频道统一，再由本端点改用
ws_manager.on_connect / on_disconnect 统一管理连接生命周期。
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis import get_redis
from app.core.security import decode_token
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 主端点 — 通过 Sec-WebSocket-Protocol 传递 JWT。

    认证流程：
    1. 从 sec-websocket-protocol 提取 jwt.{token}
    2. 解码 JWT 获取 user_id
    3. accept 后订阅 Redis ws:user:{user_id} 频道
    4. 三个并行协程：relay_messages + heartbeat + receive_loop
    5. 断连时清理 Redis 状态
    """
    # Step 0: 提取 token
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    token = ""
    if protocols:
        for proto in protocols.split(","):
            proto = proto.strip()
            if proto.startswith("jwt."):
                token = proto[4:]  # strip "jwt." prefix
                break

    if not token:
        await websocket.close(code=4001)
        return

    # Step 1: 验证 JWT
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = int(payload.get("sub", 0))
    if not user_id:
        await websocket.close(code=4001)
        return

    # Step 2: 接受连接
    await websocket.accept(subprotocol=f"jwt.{token}")

    # Step 2.5: WS 重连补偿 — 推送离线期间未读通知（R4-Notif-3）
    try:
        await NotificationService.on_ws_reconnect(user_id)
    except Exception as e:
        logger.warning("ws_on_reconnect failed: %s", e)

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"ws:user:{user_id}")

    # Step 3: 发送 connected 事件
    await websocket.send_json({
        "event": "connected",
        "data": {"user_id": user_id},
    })

    # Step 4: 设置在线状态
    await redis.setex(f"ws:online:{user_id}", NotificationService.WS_ONLINE_TTL, "1")

    async def relay_messages():
        """Redis pubsub -> WS 消息中继"""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except WebSocketDisconnect:
            return
        except Exception as e:
            logger.warning("ws_relay_error", extra={"error": str(e)})

    async def heartbeat():
        """在线状态续期 — 每 30s 更新 Redis TTL"""
        try:
            while True:
                await redis.setex(
                    f"ws:online:{user_id}",
                    NotificationService.WS_ONLINE_TTL,
                    "1",
                )
                await asyncio.sleep(30)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    async def receive_loop():
        """接收客户端消息（ping/pong + subscribe）"""
        subscribed_matches: set[int] = set()
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue

                if msg.get("event") == "ping":
                    await websocket.send_json({
                        "event": "pong",
                        "data": {"token_expired": False},
                    })
                elif msg.get("event") == "subscribe" and msg.get("match_id"):
                    # 客户端订阅比赛频道 — 接收该比赛的实时比分推送
                    try:
                        match_id = int(msg["match_id"])
                    except (TypeError, ValueError):
                        continue
                    if match_id not in subscribed_matches:
                        await pubsub.subscribe(f"ws:match:{match_id}")
                        subscribed_matches.add(match_id)
                        await websocket.send_json({
                            "event": "subscribed",
                            "data": {"match_id": match_id},
                        })
        except WebSocketDisconnect:
            return
        except Exception:
            return

    # Step 5: 三个并行协程
    tasks = [
        asyncio.create_task(relay_messages()),
        asyncio.create_task(heartbeat()),
        asyncio.create_task(receive_loop()),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    # Step 6: 断连清理
    try:
        await redis.delete(f"ws:online:{user_id}")
    except Exception:
        pass
    try:
        await pubsub.unsubscribe(f"ws:user:{user_id}")
        await pubsub.close()
    except Exception:
        pass

    logger.info("ws_disconnected", extra={"user_id": user_id})
