"""
app/services/notification_service.py — 通知服务（S2 最小版）

依据：切片 12-notification/backend.md §5
S2 仅实现 WS 推送（push_ws_message），完整通知系统（列表/已读/未读数）在 S6。
规范：通过 Redis pubsub 推送到 ws:user:{user_id} 频道
"""

import json
import logging

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class NotificationService:
    """
    通知服务 — S2 最小实现。
    完整通知 CRUD + 模板订阅 + 微信订阅消息在 S6 实现。
    """

    WS_ONLINE_TTL = 120  # 在线状态 TTL（秒）

    @staticmethod
    async def _push_ws(user_id: int, event: str, data: dict) -> None:
        """通过 Redis pubsub 推送 WS 消息到用户频道"""
        try:
            redis = await get_redis()
            channel = f"ws:user:{user_id}"
            message = json.dumps({"event": event, "data": data})
            await redis.publish(channel, message)
        except Exception as e:
            logger.warning("notification_push_ws_failed", extra={
                "error": str(e), "user_id": user_id, "event": event
            })

    @staticmethod
    async def push_ws_message(user_id: int, event_type: str, data: dict) -> None:
        """推送 WS 消息（公开接口）"""
        await NotificationService._push_ws(user_id, event_type, data)

    @staticmethod
    async def is_user_online(user_id: int) -> bool:
        """检查用户是否在线（Redis ws:online 标记）"""
        try:
            redis = await get_redis()
            return await redis.exists(f"ws:online:{user_id}") > 0
        except Exception:
            return False
