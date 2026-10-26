"""
tests/integration/test_ws_channels.py — WebSocket 通道补充测试

覆盖薄弱环节：WS 消息推送机制、重连补偿、在线状态管理
"""

import json
import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.core.security import create_access_token, generate_jti
from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.user import User
from app.models.notification import NotificationRecord
from app.services.notification_service import NotificationService
from sqlalchemy import select


def _make_token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id), "jti": generate_jti()})


@pytest_asyncio.fixture
async def ws_user(db_session):
    """创建测试用户"""
    user = User(openid="ws_user", nickname="WS用户", status="active")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
class TestWSMessagePush:
    """WS 消息推送测试"""

    async def test_push_ws_message_publishes_to_channel(self, ws_user):
        """push_ws_message 应向 Redis 频道发布消息"""
        redis = await get_redis()
        user_id = ws_user.id
        # R5-Infra-5: 频道命名统一为 ws:relay:ws:user:{user_id}
        channel = f"ws:relay:ws:user:{user_id}"

        # 订阅频道
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        await asyncio.sleep(0.3)  # 等待订阅完全生效

        # 消费订阅确认消息
        while True:
            msg = await pubsub.get_message()
            if msg is None:
                break

        # 推送消息
        await NotificationService.push_ws_message(
            user_id, "test_event", {"key": "value"}
        )

        # 等待消息到达
        msg = None
        for _ in range(10):
            msg = await asyncio.wait_for(
                pubsub.get_message(ignore_subscribe_messages=True),
                timeout=2.0,
            )
            if msg and msg["type"] == "message":
                break
            await asyncio.sleep(0.1)

        await pubsub.unsubscribe(channel)
        await pubsub.close()

        assert msg is not None
        assert msg["type"] == "message"
        data = json.loads(msg["data"])
        assert data["event"] == "test_event"
        assert data["data"]["key"] == "value"

    async def test_push_ws_message_different_users_isolated(self, db_session):
        """不同用户频道的消息互不干扰"""
        user_a = User(openid="ws_a", nickname="WS用户A", status="active")
        user_b = User(openid="ws_b", nickname="WS用户B", status="active")
        db_session.add_all([user_a, user_b])
        await db_session.commit()
        await db_session.refresh(user_a)
        await db_session.refresh(user_b)

        redis = await get_redis()
        # R5-Infra-5: 频道命名统一为 ws:relay:ws:user:{user_id}
        channel_a = f"ws:relay:ws:user:{user_a.id}"
        channel_b = f"ws:relay:ws:user:{user_b.id}"

        pubsub_a = redis.pubsub()
        await pubsub_a.subscribe(channel_a)
        await asyncio.sleep(0.1)

        # 向 B 推送消息
        await NotificationService.push_ws_message(user_b.id, "b_event", {"msg": "for B"})

        # A 的频道不应收到消息
        try:
            msg = await asyncio.wait_for(
                pubsub_a.get_message(ignore_subscribe_messages=True),
                timeout=1.0,
            )
            # 如果有消息，应该是空或者不属于 B 的事件
            if msg and msg["type"] == "message":
                data = json.loads(msg["data"])
                assert data["event"] != "b_event"
        except asyncio.TimeoutError:
            pass  # 预期：A 没收到消息

        await pubsub_a.unsubscribe(channel_a)
        await pubsub_a.close()

        # 清理
        await redis.delete(f"ws:online:{user_a.id}")
        await redis.delete(f"ws:online:{user_b.id}")


@pytest.mark.asyncio
class TestWSOnlineStatus:
    """WS 在线状态管理测试"""

    async def test_is_user_online_after_set(self, ws_user):
        """设置在线状态后 is_user_online 返回 True"""
        redis = await get_redis()
        user_id = ws_user.id
        key = f"ws:online:{user_id}"

        # 确保清理
        await redis.delete(key)

        # 设置在线
        await redis.setex(key, 120, "1")
        online = await NotificationService.is_user_online(user_id)
        assert online is True

        # 清理
        await redis.delete(key)

    async def test_is_user_offline_when_no_key(self, ws_user):
        """无在线标记时 is_user_online 返回 False"""
        redis = await get_redis()
        user_id = ws_user.id
        key = f"ws:online:{user_id}"

        await redis.delete(key)
        online = await NotificationService.is_user_online(user_id)
        assert online is False


@pytest.mark.asyncio
class TestWSReconnectCompensation:
    """WS 重连补偿测试"""

    async def test_reconnect_pushes_unread_notifications(self, db_session):
        """重连时推送未读通知"""
        user = User(openid="reconnect_user", nickname="重连用户", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # 创建多条未读通知
        for i in range(5):
            notif = NotificationRecord(
                user_id=user.id,
                type="system",
                title=f"离线通知{i}",
                content=f"离线内容{i}",
            )
            db_session.add(notif)
        await db_session.commit()

        # 订阅用户频道以捕获补偿推送
        redis = await get_redis()
        # R5-Infra-5: 频道命名统一为 ws:relay:ws:user:{user_id}
        channel = f"ws:relay:ws:user:{user.id}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        await asyncio.sleep(0.3)

        # 消费订阅确认消息
        while True:
            msg = await pubsub.get_message()
            if msg is None:
                break

        # 触发重连补偿
        await NotificationService.on_ws_reconnect(user.id)
        await asyncio.sleep(0.3)

        # 收集推送的消息
        messages = []
        try:
            while len(messages) < 5:
                msg = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=2.0,
                )
                if msg and msg["type"] == "message":
                    messages.append(json.loads(msg["data"]))
        except asyncio.TimeoutError:
            pass

        await pubsub.unsubscribe(channel)
        await pubsub.close()

        # 应至少推送了部分未读通知
        assert len(messages) > 0
        # 推送的事件类型应为通知相关
        for msg in messages:
            assert "event" in msg

    async def test_reconnect_no_unread_no_push(self, ws_user):
        """无未读通知时重连不推送"""
        redis = await get_redis()
        # R5-Infra-5: 频道命名统一为 ws:relay:ws:user:{user_id}
        channel = f"ws:relay:ws:user:{ws_user.id}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        await asyncio.sleep(0.1)

        # 确保没有未读通知
        async with async_session_factory() as db:
            result = await db.execute(
                select(NotificationRecord).where(
                    NotificationRecord.user_id == ws_user.id,
                    NotificationRecord.is_read == False,
                )
            )
            unread = result.scalars().all()
            assert len(unread) == 0

        # 触发重连补偿
        await NotificationService.on_ws_reconnect(ws_user.id)

        # 应无消息推送
        try:
            msg = await asyncio.wait_for(
                pubsub.get_message(ignore_subscribe_messages=True),
                timeout=1.0,
            )
            if msg and msg["type"] == "message":
                # 如果有消息，不应是通知推送
                data = json.loads(msg["data"])
                assert data.get("event") not in ("notification", "system_notification")
        except asyncio.TimeoutError:
            pass  # 预期：无消息

        await pubsub.unsubscribe(channel)
        await pubsub.close()


@pytest.mark.asyncio
class TestWSSendNotificationChannel:
    """通知发送通道选择测试"""

    async def test_send_notification_offline_writes_db(self, db_session):
        """用户离线时 send_notification 写入 DB"""
        user = User(openid="offline_user", nickname="离线用户", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # 确保用户不在线
        redis = await get_redis()
        await redis.delete(f"ws:online:{user.id}")

        result = await NotificationService.send_notification(
            user.id, "test_offline", "离线测试标题", "离线测试内容"
        )

        assert result is not None
        # 验证 DB 中有记录
        async with async_session_factory() as db:
            res = await db.execute(
                select(NotificationRecord).where(
                    NotificationRecord.user_id == user.id,
                    NotificationRecord.type == "test_offline",
                )
            )
            records = res.scalars().all()
            assert len(records) >= 1

    async def test_send_notification_online_no_db_write(self, db_session):
        """用户在线时 send_notification 通过 WS 推送，不写 DB"""
        user = User(openid="online_user", nickname="在线用户", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # 设置用户在线
        redis = await get_redis()
        await redis.setex(f"ws:online:{user.id}", 120, "1")

        # 订阅频道
        # R5-Infra-5: 频道命名统一为 ws:relay:ws:user:{user_id}
        channel = f"ws:relay:ws:user:{user.id}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        await asyncio.sleep(0.3)

        # 消费订阅确认消息
        while True:
            msg = await pubsub.get_message()
            if msg is None:
                break

        result = await NotificationService.send_notification(
            user.id, "test_online", "在线测试标题", "在线测试内容"
        )

        # 应收到 WS 消息
        msg = None
        for _ in range(10):
            msg = await asyncio.wait_for(
                pubsub.get_message(ignore_subscribe_messages=True),
                timeout=2.0,
            )
            if msg and msg["type"] == "message":
                break
            await asyncio.sleep(0.1)

        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.delete(f"ws:online:{user.id}")

        assert msg is not None
        data = json.loads(msg["data"])
        # send_notification 在线时推送事件名为 "notification"
        assert data["event"] == "notification"
        assert data["data"]["type"] == "test_online"

        # 验证 DB 中无记录（在线时不写 DB）
        async with async_session_factory() as db:
            res = await db.execute(
                select(NotificationRecord).where(
                    NotificationRecord.user_id == user.id,
                    NotificationRecord.type == "test_online",
                )
            )
            records = res.scalars().all()
            assert len(records) == 0
