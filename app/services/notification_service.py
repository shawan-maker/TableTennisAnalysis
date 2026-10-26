"""
app/services/notification_service.py — 通知服务（S6 完整版）

依据：切片 12-notification/backend.md §5
S2 实现 WS 推送，S6 扩展完整通知 CRUD + 模板订阅 + 频率控制。
规范：在线→WS推送（不写DB）；离线→写DB+微信订阅消息
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, desc, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.pagination import paginate, PaginationParams
from app.models.notification import NotificationRecord
from app.schemas.notification import (
    NotificationBrief, NotificationListQuery,
    MarkReadResponse, SubscribeResponse,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """通知服务 — S6 完整实现"""

    WS_ONLINE_TTL = 120  # 在线状态 TTL（秒）
    REMINDER_WEEKLY_LIMIT = 2  # 训练提醒每周上限
    REMINDER_INACTIVE_DAYS = 3  # 未训练阈值天数

    # ==================== WS 推送（S2 已有，保留兼容）====================

    @staticmethod
    async def _push_ws(user_id: int, event: str, data: dict) -> None:
        """通过 Redis pubsub 推送 WS 消息到用户频道"""
        try:
            redis = await get_redis()
            channel = f"ws:user:{user_id}"
            message = json.dumps({"event": event, "data": data})
            await redis.publish(channel, message)
        except Exception as e:
            logger.warning("notification_push_ws_failed: %s", e)

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

    # ==================== 通知发送（核心通道选择）====================

    @staticmethod
    async def send_notification(
        user_id: int,
        notif_type: str,
        title: str,
        content: str,
        extra_data: Optional[dict] = None,
        wechat_template: Optional[str] = None,
    ) -> Optional[NotificationRecord]:
        """
        发送通知——核心通道选择逻辑。
        在线→WS推送（不写DB）；离线→写DB+微信订阅消息。
        """
        # 在线用户：直接 WS 推送，不写 DB
        if await NotificationService.is_user_online(user_id):
            await NotificationService._push_ws(user_id, "notification", {
                "type": notif_type,
                "title": title,
                "content": content,
                "extra_data": extra_data,
            })
            return None

        # 离线用户：写 DB + 更新未读计数 + 微信订阅消息
        async with async_session_factory() as db:
            record = NotificationRecord(
                user_id=user_id,
                type=notif_type,
                title=title,
                content=content,
                extra_data=extra_data,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

        # 更新 Redis 未读计数
        try:
            redis = await get_redis()
            await redis.incr(f"notif:unread:{user_id}")
        except Exception as e:
            logger.warning("incr unread count failed: %s", e)

        # 微信订阅消息（可选）
        if wechat_template:
            await NotificationService._send_wechat_subscribe(user_id, {
                "type": notif_type, "title": title, "content": content,
            })

        return record

    @staticmethod
    async def _send_wechat_subscribe(user_id: int, notification: dict) -> bool:
        """发送微信订阅消息（生产环境调用微信订阅消息 API）"""
        from app.core.config import settings

        if settings.SMS_MOCK or settings.WECHAT_PAY_MOCK:
            logger.info(
                "wechat subscribe mock: user_id=%s type=%s",
                user_id, notification.get("type"),
            )
            return True

        # TODO: 接入微信订阅消息 API（生产环境取消注释并配置 client）
        # 构造 template_msg 结构，便于日志审计与后续接入
        template_msg = {
            "template_id": settings.WECHAT_SUBSCRIBE_TEMPLATE_ID
            if hasattr(settings, "WECHAT_SUBSCRIBE_TEMPLATE_ID")
            else notification.get("type", "notification"),
            "page": "pages/notification/list",
            "data": {
                "thing1": {"value": notification.get("title", "")[:20]},
                "thing2": {"value": notification.get("content", "")[:20]},
            },
            "miniprogram_state": "formal" if settings.is_production else "developer",
            "lang": "zh_CN",
        }
        logger.info(
            "wechat subscribe message prepared: user_id=%s type=%s template_id=%s",
            user_id, notification.get("type"), template_msg["template_id"],
        )
        # from app.core.wechat import WeChatClient
        # client = WeChatClient()
        # await client.send_subscribe_message(
        #     user_id=user_id,
        #     template_id=template_msg["template_id"],
        #     page=template_msg["page"],
        #     data=template_msg["data"],
        # )
        return True

    # ==================== 通知列表 / 已读 / 未读数 ====================

    @staticmethod
    async def list_notifications(
        user_id: int,
        query: NotificationListQuery,
    ) -> dict:
        """查询通知列表（分页）"""
        async with async_session_factory() as db:
            stmt = select(NotificationRecord).where(
                NotificationRecord.user_id == user_id
            )
            if query.is_read is not None:
                stmt = stmt.where(NotificationRecord.is_read == query.is_read)
            if query.type:
                stmt = stmt.where(NotificationRecord.type == query.type)
            stmt = stmt.order_by(desc(NotificationRecord.created_at))

            pagination = PaginationParams(page=query.page, page_size=query.page_size)
            result = await paginate(db, stmt, pagination)

            return {
                "total": result["total"],
                "page": query.page,
                "page_size": query.page_size,
                "items": [NotificationBrief.model_validate(n) for n in result["items"]],
            }

    @staticmethod
    async def mark_read(
        user_id: int,
        notification_ids: list[int],
    ) -> MarkReadResponse:
        """批量标记已读"""
        async with async_session_factory() as db:
            result = await db.execute(
                update(NotificationRecord)
                .where(
                    NotificationRecord.user_id == user_id,
                    NotificationRecord.id.in_(notification_ids),
                    NotificationRecord.is_read == False,  # noqa: E712
                )
                .values(is_read=True)
                .returning(NotificationRecord.id)
            )
            updated_ids = result.scalars().all()
            await db.commit()

        # 更新 Redis 未读计数（原子递减）
        if updated_ids:
            try:
                redis = await get_redis()
                key = f"notif:unread:{user_id}"
                await redis.decrby(key, len(updated_ids))
                # 检查负数修正
                v = await redis.get(key)
                if v and int(v) < 0:
                    await redis.set(key, 0)
            except Exception as e:
                logger.warning("decr unread count failed: %s", e)

        return MarkReadResponse(updated_count=len(updated_ids))

    @staticmethod
    async def get_unread_count(user_id: int) -> int:
        """获取未读通知数量（Redis 缓存优先）"""
        try:
            redis = await get_redis()
            cached = await redis.get(f"notif:unread:{user_id}")
            if cached is not None:
                return int(cached)
        except Exception:
            pass

        # 未命中缓存，查 DB
        async with async_session_factory() as db:
            result = await db.execute(
                select(func.count()).select_from(NotificationRecord).where(
                    NotificationRecord.user_id == user_id,
                    NotificationRecord.is_read == False,  # noqa: E712
                )
            )
            count = result.scalar() or 0

        # 回填缓存
        try:
            redis = await get_redis()
            await redis.set(f"notif:unread:{user_id}", count, ex=300)
        except Exception:
            pass

        return count

    # ==================== 微信订阅消息授权 ====================

    @staticmethod
    async def subscribe_templates(
        user_id: int,
        template_ids: list[str],
    ) -> SubscribeResponse:
        """微信订阅消息授权（静默过滤无效模板 ID）"""
        valid_templates = {"analysis_complete", "payment_success", "training_reminder"}
        valid_ids = [t for t in template_ids if t in valid_templates]

        redis = await get_redis()
        key = f"notif:subscribed:{user_id}"
        # 清除旧订阅，设置新订阅
        await redis.delete(key)
        if valid_ids:
            await redis.sadd(key, *valid_ids)

        return SubscribeResponse(subscribed_templates=valid_ids)

    # ==================== 训练提醒 ====================

    @staticmethod
    async def _check_reminder_frequency(user_id: int, redis) -> bool:
        """训练提醒频率控制：同一用户每周最多 2 次"""
        key = f"notif:reminder:count:{user_id}:week"
        count = await redis.get(key)
        if count and int(count) >= NotificationService.REMINDER_WEEKLY_LIMIT:
            return False
        return True

    @staticmethod
    async def send_training_reminder(
        user_id: int,
        last_training_days: int,
    ) -> None:
        """发送训练提醒（Celery Beat 调用）"""
        if last_training_days < NotificationService.REMINDER_INACTIVE_DAYS:
            return  # 最近有训练，不提醒

        redis = await get_redis()
        if not await NotificationService._check_reminder_frequency(user_id, redis):
            return  # 本周已达上限

        await NotificationService.send_notification(
            user_id=user_id,
            notif_type="training_reminder",
            title="训练提醒",
            content=f"您已经{last_training_days}天没有训练了，快来练习吧！",
            wechat_template="training_reminder",
        )

        # 增加本周提醒计数 — TTL 按自然周对齐（到本周日 23:59:59）
        key = f"notif:reminder:count:{user_id}:week"
        new_count = await redis.incr(key)
        if new_count == 1:
            from datetime import timezone as tz
            now = datetime.now(tz.utc)
            # 计算到本周日 23:59:59 的秒数（周一为一周起始）
            days_until_sunday = (6 - now.weekday()) % 7 or 7
            end_of_week = now.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=days_until_sunday)
            ttl_seconds = int((end_of_week - now).total_seconds())
            await redis.expire(key, max(ttl_seconds, 3600))  # 至少 1 小时

    # ==================== WS 重连补偿 ====================

    @staticmethod
    async def on_ws_reconnect(user_id: int) -> None:
        """WebSocket 重连后的离线消息补偿 — 推送 sync 事件 + unread_count"""
        async with async_session_factory() as db:
            # 查询未读通知数
            count_result = await db.execute(
                select(func.count()).select_from(NotificationRecord).where(
                    NotificationRecord.user_id == user_id,
                    NotificationRecord.is_read == False,  # noqa: E712
                )
            )
            unread_count = count_result.scalar() or 0

        if unread_count > 0:
            await NotificationService._push_ws(user_id, "sync", {
                "type": "notification",
                "unread_count": unread_count,
                "message": f"您有 {unread_count} 条未读通知",
            })
