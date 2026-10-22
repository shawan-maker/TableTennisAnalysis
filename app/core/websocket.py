"""
app/core/websocket.py — WebSocket 连接管理器

依据：切片 13-infrastructure/ws_manager.md §3
功能：房间管理 + Redis pubsub 中继 + 多实例广播
架构约束：§5.6 WebSocket / §15 约束 #30 重连
规范：基础设施层提供统一 WS 能力，业务模块不直接操作 WebSocket
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class WSManager:
    """
    WebSocket 连接管理器 — 单例模式。
    维护 _rooms（room_id -> set[WebSocket]）和 _reverse（WebSocket -> room_id）双向映射。
    Redis pubsub 中继支持多实例广播。
    """

    PUBSUB_PATTERN = "ws:relay:*"
    RELAY_CHANNEL_TEMPLATE = "ws:relay:{room_id}"

    def __init__(self):
        self._rooms: dict[str, set[WebSocket]] = {}
        self._reverse: dict[WebSocket, str] = {}
        self._relay_pubsub = None

    async def on_connect(self, websocket: WebSocket, room_id: str) -> None:
        """接受连接并加入房间"""
        await websocket.accept()
        if room_id not in self._rooms:
            self._rooms[room_id] = set()
        self._rooms[room_id].add(websocket)
        self._reverse[websocket] = room_id
        logger.info("ws_connected", extra={"room_id": room_id})

    async def on_disconnect(self, websocket: WebSocket, room_id: str) -> None:
        """从房间移除连接"""
        if room_id in self._rooms:
            self._rooms[room_id].discard(websocket)
            if not self._rooms[room_id]:
                del self._rooms[room_id]
        self._reverse.pop(websocket, None)
        logger.info("ws_disconnected", extra={"room_id": room_id})

    async def broadcast_to_room(self, room_id: str, message: str) -> None:
        """广播到房间 — 本地 + Redis 中继"""
        await self._local_broadcast(room_id, message)
        # Redis pubsub 中继到其他实例
        try:
            redis = await get_redis()
            await redis.publish(
                self.RELAY_CHANNEL_TEMPLATE.format(room_id=room_id), message
            )
        except Exception as e:
            logger.warning("ws_relay_publish_failed", extra={"error": str(e)})

    async def broadcast_to_user(self, user_id: int, message: str) -> None:
        """广播到用户频道"""
        await self.broadcast_to_room(f"ws:user:{user_id}", message)

    async def send_personal(self, websocket: WebSocket, message: str) -> None:
        """发送给单个连接"""
        try:
            await websocket.send_text(message)
        except (WebSocketDisconnect, RuntimeError, ConnectionError) as e:
            logger.warning("ws_send_failed", extra={"error": str(e)})
            room_id = self._reverse.get(websocket)
            if room_id:
                await self.on_disconnect(websocket, room_id)

    async def _local_broadcast(self, room_id: str, message: str) -> None:
        """本地广播 — 跳过死连接"""
        dead: list[WebSocket] = []
        for ws in self._rooms.get(room_id, set()):
            try:
                await ws.send_text(message)
            except (WebSocketDisconnect, RuntimeError, ConnectionError):
                dead.append(ws)
        for ws in dead:
            await self.on_disconnect(ws, self._reverse.get(ws, room_id))

    async def start_relay(self) -> None:
        """启动 Redis pubsub 中继监听 — 应用启动时调用"""
        try:
            redis = await get_redis()
            self._relay_pubsub = redis.pubsub()
            await self._relay_pubsub.psubscribe(self.PUBSUB_PATTERN)
            logger.info("ws_relay_started")
        except Exception as e:
            logger.warning("ws_relay_start_failed", extra={"error": str(e)})

    async def stop_relay(self) -> None:
        """停止 Redis pubsub 中继 — 应用关闭时调用"""
        if self._relay_pubsub is not None:
            try:
                await self._relay_pubsub.punsubscribe(self.PUBSUB_PATTERN)
                await self._relay_pubsub.close()
            except Exception:
                pass
            self._relay_pubsub = None
            logger.info("ws_relay_stopped")


# 全局单例
manager = WSManager()
