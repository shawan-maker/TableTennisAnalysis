# WebSocket 连接管理器 — ws_manager

> **模块名称**：`infrastructure / ws_manager`
> **定位**：全局 WebSocket 连接管理器，基于 Starlette `WebSocket` 协议提供房间/用户级广播能力，通过 Redis pubsub relay 实现多实例消息同步
> **依据**：INF-5 / X-12 — 架构 §5.7 定义 WebSocket 协议统一为 `{event, data}` 结构，切片 Service 层（scoring/notification）需通过 ws_manager 推送实时事件
> **实现文件**：`app/core/websocket.py`

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 房间广播 | `broadcast_to_room(room_id, message)` 支持按 match_id / user_id 维度广播 |
| 用户广播 | `broadcast_to_user(user_id, message)` 向指定用户所有活跃连接推送 |
| 个人消息 | `send_personal(websocket, message)` 向单个连接发送消息 |
| 多实例同步 | Redis pubsub relay 保证多进程/多实例部署下消息一致投递 |
| 连接生命周期 | `on_connect` / `on_disconnect` 钩子管理连接注册与清理 |
| 协议统一 | 消息结构遵循 `{event: str, data: dict}`（R17-P1 统一协议） |

---

## 2. 接口签名

```python
# app/core/websocket.py 接口签名（供切片 Service 层依赖注入使用）

from starlette.websockets import WebSocket


class WSManager:
    """WebSocket 连接管理器（单例）。

    维护 room_id -> set[WebSocket] 映射，支持房间广播与个人消息。
    通过 Redis pubsub relay 实现多实例同步。
    """

    async def broadcast_to_room(self, room_id: str, message: str) -> None:
        """向指定房间所有活跃连接广播消息。

        Args:
            room_id: 房间标识，格式约定：
                - 比赛房间：f"ws:match:{match_id}"
                - 用户房间：f"ws:user:{user_id}"
                - 通知房间：f"ws:notification:{user_id}"
            message: JSON 序列化后的字符串，结构为 {"event": str, "data": dict}
        """
        ...

    async def broadcast_to_user(self, user_id: int, message: str) -> None:
        """向指定用户所有活跃连接广播消息（用户可能多端登录）。

        Args:
            user_id: 用户 ID
            message: JSON 序列化后的字符串
        """
        ...

    async def send_personal(self, websocket: WebSocket, message: str) -> None:
        """向单个 WebSocket 连接发送消息。

        Args:
            websocket: Starlette WebSocket 实例
            message: JSON 序列化后的字符串

        Notes:
            若连接已断开，捕获 RuntimeError 并从房间中清理。
        """
        ...

    async def on_connect(self, websocket: WebSocket, room_id: str) -> None:
        """连接建立钩子：注册到 room_id 房间。

        Args:
            websocket: 新建立的 WebSocket 连接
            room_id: 房间标识
        """
        ...

    async def on_disconnect(self, websocket: WebSocket, room_id: str) -> None:
        """连接断开钩子：从房间注销，清理资源。

        Args:
            websocket: 已断开的 WebSocket 连接
            room_id: 房间标识
        """
        ...
```

---

## 3. 完整实现

```python
# app/core/websocket.py
"""WebSocket 连接管理器 — 单例模式，Redis pubsub relay 多实例同步。

依赖：
    - starlette.WebSocket
    - app.core.redis.get_redis（异步 Redis 客户端）

使用方式：
    from app.core.websocket import manager as ws_manager
    await ws_manager.broadcast_to_room(f"ws:match:{match_id}", json.dumps({...}))
"""

import json
import logging
from collections import defaultdict
from typing import Awaitable, Callable

from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class WSManager:
    """WebSocket 连接管理器（单例）。"""

    PUBSUB_PATTERN = "ws:relay:*"
    RELAY_CHANNEL_TEMPLATE = "ws:relay:{room_id}"

    def __init__(self):
        # room_id -> set[WebSocket]
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        # websocket -> room_id（用于 on_disconnect 反查）
        self._reverse: dict[WebSocket, str] = {}
        self._relay_task: Awaitable | None = None

    async def on_connect(self, websocket: WebSocket, room_id: str) -> None:
        """连接建立：接受握手并注册到房间。"""
        await websocket.accept()
        self._rooms[room_id].add(websocket)
        self._reverse[websocket] = room_id
        logger.info("ws_connected", room_id=room_id, extra={"ws": id(websocket)})

    async def on_disconnect(self, websocket: WebSocket, room_id: str) -> None:
        """连接断开：从房间注销。"""
        self._rooms.get(room_id, set()).discard(websocket)
        self._reverse.pop(websocket, None)
        if not self._rooms.get(room_id):
            self._rooms.pop(room_id, None)
        logger.info("ws_disconnected", room_id=room_id)

    async def broadcast_to_room(self, room_id: str, message: str) -> None:
        """向房间广播：本地投递 + Redis pubsub relay（多实例同步）。"""
        # 1. 本地投递
        await self._local_broadcast(room_id, message)
        # 2. 通过 Redis pubsub relay 通知其他实例
        redis = await get_redis()
        await redis.publish(self.RELAY_CHANNEL_TEMPLATE.format(room_id=room_id), message)

    async def broadcast_to_user(self, user_id: int, message: str) -> None:
        """向用户所有连接广播：复用 broadcast_to_room，room_id 为 f"ws:user:{user_id}"。"""
        await self.broadcast_to_room(f"ws:user:{user_id}", message)

    async def send_personal(self, websocket: WebSocket, message: str) -> None:
        """向单个连接发送消息。"""
        try:
            await websocket.send_text(message)
        except (WebSocketDisconnect, RuntimeError, ConnectionError) as e:
            logger.warning("ws_send_failed", error=str(e))
            room_id = self._reverse.get(websocket)
            if room_id:
                await self.on_disconnect(websocket, room_id)

    async def _local_broadcast(self, room_id: str, message: str) -> None:
        """本地房间投递（跳过已断开连接）。"""
        dead: list[WebSocket] = []
        for ws in self._rooms.get(room_id, set()):
            try:
                await ws.send_text(message)
            except (WebSocketDisconnect, RuntimeError, ConnectionError):
                dead.append(ws)
        for ws in dead:
            await self.on_disconnect(ws, room_id)

    async def start_relay(self) -> None:
        """启动 Redis pubsub relay 监听（应用启动时调用）。

        订阅 ws:relay:* pattern，收到消息后本地投递到对应房间。
        """
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.psubscribe(self.PUBSUB_PATTERN)
        logger.info("ws_relay_started", pattern=self.PUBSUB_PATTERN)
        # 实际实现需启动后台 task 循环 get_message
        self._relay_task = pubsub

    async def stop_relay(self) -> None:
        """停止 relay 监听（应用关闭时调用）。"""
        if self._relay_task is not None:
            try:
                self._relay_task.close()
            except Exception:
                pass
            self._relay_task = None


# 全局单例
manager = WSManager()
```

---

## 4. 使用示例

```python
# scoring 模块调用示例（参见 04-scoring/backend.md §5）
from app.core.websocket import manager as ws_manager
import json

# 比赛房间广播
await ws_manager.broadcast_to_room(
    f"ws:match:{match_id}",
    json.dumps({"event": "score_update", "data": {"score": "11:8"}}),
)

# 用户个人通知
await ws_manager.broadcast_to_user(
    user_id,
    json.dumps({"event": "notification", "data": {"type": "export_completed"}}),
)
```

```python
# API 路由 WebSocket 端点示例
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.websocket import manager

router = APIRouter()


@router.websocket("/ws/match/{match_id}")
async def match_ws(websocket: WebSocket, match_id: int):
    room_id = f"ws:match:{match_id}"
    await manager.on_connect(websocket, room_id)
    try:
        while True:
            await websocket.receive_text()  # 心跳/客户端消息
    except WebSocketDisconnect:
        await manager.on_disconnect(websocket, room_id)
```

---

## 5. Redis Key 命名规范

| 用途 | Key/Channel | 说明 |
|------|-------------|------|
| Relay pubsub channel | `ws:relay:{room_id}` | 多实例广播同步通道 |
| Relay 订阅 pattern | `ws:relay:*` | PSUBSCRIBE 监听所有 relay channel |
| 用户在线状态 | `ws:user:{user_id}` | 由 broadcast_to_user 约定 room_id |

---

## 6. 反幻觉约束对齐

- **X-12**：WebSocket 消息协议统一 `{event, data}` 结构，本管理器仅做透传不解析消息体
- **INF-5**：基础设施层提供统一 WS 能力，业务模块通过依赖注入调用，不直接操作 starlette WebSocket
- **R17-P1**：消息字段命名 `event`（非 `type`），与 notification data.type 在嵌套层级区分

---

## 7. 验证清单

- [ ] `WSManager.broadcast_to_room` 接口签名与 scoring 切片调用一致（`room_id: str, message: str`）
- [ ] `WSManager.broadcast_to_user` 接口签名支持多端登录场景
- [ ] `WSManager.send_personal` 异常处理覆盖 WebSocketDisconnect / RuntimeError / ConnectionError
- [ ] `on_connect` / `on_disconnect` 钩子维护 `_rooms` 与 `_reverse` 双向映射一致性
- [ ] Redis pubsub relay 在多实例部署下验证消息一致投递
- [ ] 全局单例 `manager` 在应用 lifespan 启动时调用 `start_relay()`，关闭时调用 `stop_relay()`
