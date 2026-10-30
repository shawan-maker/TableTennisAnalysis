# notification 模块 — 后端垂直切片设计

> **模块名称**：`notification`
> **所属目录**：`app/api/v1/notification/` + `app/services/notification_service.py` + `app/api/v1/ws.py`
> **定位**：WebSocket 实时推送、微信订阅消息、训练提醒、离线消息补偿
> **依据**：模块详细设计 v1.3 §2.12、API 详细设计 v1.3 §13-14

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.12（notification 模块功能规格）
- [ ] 阅读 API 契约 §13（4 个 REST 端点，含切片新增 unread-count，见文末回写说明）+ §14（WebSocket 端点）
- [ ] 阅读 `app/core/redis.py`（Redis 连接管理）
- [ ] 阅读 `app/models/notification.py`（NotificationRecord 表定义）
- [ ] 确认本切片范围：4 个 REST API + WS 端点 + Celery 任务（训练提醒 + 旧通知清理）+ 离线补偿

### 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/notification.py` | 无 | ☐ |
| 2 | 注册 Model | `app/models/__init__.py` | #1 | ☐ |
| 3 | 定义 Schema | `app/schemas/notification.py` | #1 | ☐ |
| 4 | 实现 Service | `app/services/notification_service.py` | #2,#3 | ☐ |
| 5 | 实现 WebSocket 端点 | `app/api/v1/ws.py` | #4 | ☐ |
| 6 | 实现 API 路由 | `app/api/v1/notification/router.py` | #4 | ☐ |
| 7 | 注册 Router | `app/api/v1/__init__.py` | #6 | ☐ |
| 8 | 实现 Celery 任务（训练提醒 + 旧通知清理） | `app/tasks/notification.py` | #4 | ☐ |
| 9 | 编写测试 | `tests/unit/test_notification.py` | #4 | ☐ |
| 10 | 编写冒烟测试 | `tests/smoke/notification_smoke_test.py` | #7 | ☐ |

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_notification.py
"""
notification 模块 — 通知推送与离线补偿测试。
覆盖：通知列表、标记已读、通道选择、离线补偿、训练提醒频率控制。
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.core.exceptions import AppException


@pytest.fixture
async def notif_ctx(client, db_session):
    """创建测试上下文：用户 + 已发送的通知。"""
    from app.services.notification_service import NotificationService
    from app.models.notification import NotificationRecord

    # 创建 3 条通知：2 未读 + 1 已读
    records = []
    for i in range(3):
        rec = NotificationRecord(
            user_id=1,
            type="analysis_complete" if i < 2 else "payment_success",
            title=f"测试通知{i}",
            content=f"内容{i}",
            is_read=(i == 2),
            extra_data={"task_id": f"task_{i}"},
        )
        db_session.add(rec)
        records.append(rec)
    await db_session.commit()
    yield {"records": records}
    # 清理
    for rec in records:
        await db_session.delete(rec)
    await db_session.commit()


# === 1. Happy Path ===
@pytest.mark.asyncio
async def test_list_notifications(client, auth_headers, notif_ctx):
    """查询通知列表，返回分页结果。"""
    resp = await client.get(
        "/api/v1/notification/list?page=1&page_size=20",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 3
    assert len(data["items"]) >= 3
    assert "is_read" in data["items"][0]


@pytest.mark.asyncio
async def test_list_unread_only(client, auth_headers, notif_ctx):
    """is_read=false 过滤只返回未读通知。"""
    resp = await client.get(
        "/api/v1/notification/list?is_read=false",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(item["is_read"] is False for item in data["items"])


@pytest.mark.asyncio
async def test_mark_read_success(client, auth_headers, notif_ctx):
    """标记多条通知为已读。"""
    ids = [r.id for r in notif_ctx["records"][:2]]
    resp = await client.post(
        "/api/v1/notification/read",
        json={"notification_ids": ids},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["updated_count"] == 2


# === 2. Validation Failure ===
@pytest.mark.asyncio
async def test_mark_read_empty_ids(client, auth_headers):
    """空 ID 列表返回 422。"""
    resp = await client.post(
        "/api/v1/notification/read",
        json={"notification_ids": []},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_mark_read_too_many_ids(client, auth_headers):
    """超过 100 条 ID 返回 422。"""
    resp = await client.post(
        "/api/v1/notification/read",
        json={"notification_ids": list(range(101))},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_subscribe_empty_templates(client, auth_headers):
    """空模板列表返回 422。"""
    resp = await client.post(
        "/api/v1/notification/subscribe",
        json={"template_ids": []},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_list_without_token(client):
    """未携带 Token 返回 401。"""
    resp = await client.get("/api/v1/notification/list")
    assert resp.status_code == 401


# === 4. Business Rule ===
@pytest.mark.asyncio
async def test_online_user_gets_ws_push(client, db_session):
    """用户在线时走 WS 推送，不写 DB。"""
    from app.services.notification_service import NotificationService
    with patch.object(
        NotificationService, "is_user_online",
        new_callable=AsyncMock, return_value=True,
    ), patch.object(
        NotificationService, "_push_ws",
        new_callable=AsyncMock,
    ) as mock_push:
        await NotificationService.send_notification(
            user_id=1,
            notif_type="analysis_complete",
            title="分析完成",
            content="您的视频分析已完成",
            extra_data={"task_id": "task_1", "report_id": 1},
        )
        mock_push.assert_called_once()


@pytest.mark.asyncio
async def test_offline_user_writes_db(client, db_session):
    """用户离线时写 DB + 发微信订阅消息。"""
    from app.services.notification_service import NotificationService
    with patch.object(
        NotificationService, "is_user_online",
        new_callable=AsyncMock, return_value=False,
    ), patch.object(
        NotificationService, "_send_wechat_subscribe",
        new_callable=AsyncMock,
    ) as mock_wx:
        await NotificationService.send_notification(
            user_id=999,  # 不存在的用户确保 DB 写入
            notif_type="training_reminder",
            title="训练提醒",
            content="您已 3 天未训练，快去练球吧！",
            # R13-P3 文档同步：实现仅在传入 wechat_template 时才发送微信订阅消息
            wechat_template="training_reminder",
        )
        mock_wx.assert_called_once()


@pytest.mark.asyncio
async def test_training_reminder_frequency_control(db_session):
    """同一用户每周最多 2 次训练提醒。"""
    from app.services.notification_service import NotificationService
    from app.core.redis import get_redis

    redis = await get_redis()
    # 第一次：允许
    can1 = await NotificationService._check_reminder_frequency(1, redis)
    assert can1 is True
    await redis.incr(f"notif:reminder:count:{1}:week")
    # 第二次：允许
    can2 = await NotificationService._check_reminder_frequency(1, redis)
    assert can2 is True
    await redis.incr(f"notif:reminder:count:{1}:week")
    # 第三次：拒绝
    can3 = await NotificationService._check_reminder_frequency(1, redis)
    assert can3 is False
```

---

## 3. Model 实现

```python
# app/models/notification.py
"""通知数据模型。"""

from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, Text, Boolean, ForeignKey, Index, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class NotificationRecord(Base):
    """通知记录。"""
    __tablename__ = "notification_record"
    # 注意：notification_record 表应按月分区（PARTITION BY RANGE (created_at)）
    # 90 天前已读通知通过 Celery Beat 统一清理（见 beat_schedule.py 的 notification-old-cleanup 任务）
    # Alembic 迁移时需要手动创建分区表 DDL，不能使用默认 CREATE TABLE

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(32))
    """通知类型：analysis_complete / payment_success / training_reminder / score_update / ..."""

    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """附加数据：{task_id, report_id, action_url, match_id, ...}"""

    # R13-P3 文档同步：实现采用 DB 端默认值（app/models/notification.py）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_notif_user_unread", "user_id", "is_read", "created_at"),
    )
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入 `NotificationRecord`
- [ ] 运行 `alembic revision --autogenerate -m "add notification_record"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/notification.py
"""通知 Schema 定义。"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from app.core.pagination import Paginated


# --- 请求 Schema ---
class MarkReadRequest(BaseModel):
    notification_ids: list[int] = Field(..., min_length=1, max_length=100)


class SubscribeRequest(BaseModel):
    template_ids: list[str] = Field(..., min_length=1)
    """微信订阅消息模板 ID 列表"""


# --- 响应 Schema ---
class NotificationBrief(BaseModel):
    id: int
    type: str
    title: str
    content: str
    is_read: bool
    extra_data: Optional[dict] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class MarkReadResponse(BaseModel):
    updated_count: int


class SubscribeResponse(BaseModel):
    subscribed_templates: list[str]


# --- 查询 Schema ---
class NotificationListQuery(BaseModel):
    is_read: Optional[bool] = None
    type: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


# --- 分页包装 ---
PaginatedNotifications = Paginated[NotificationBrief]
```

---

## 5. Service 实现

```python
# app/services/notification_service.py
"""通知业务逻辑层。"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.database import get_async_session
from app.core.pagination import paginate
from app.models.notification import NotificationRecord
from app.models.user import User
from app.schemas.notification import (
    NotificationBrief,
    NotificationListQuery,
    PaginatedNotifications,
    MarkReadResponse,
    SubscribeResponse,
)
import httpx

logger = logging.getLogger(__name__)


class NotificationService:
    """通知业务逻辑层。"""

    # WebSocket 在线标记 TTL
    WS_ONLINE_TTL = 120  # 2 分钟
    # 训练提醒频率控制：每周最多 2 次
    REMINDER_WEEKLY_LIMIT = 2
    # 未训练阈值天数
    REMINDER_INACTIVE_DAYS = 3

    @staticmethod
    async def is_user_online(user_id: int) -> bool:
        # R13-P3 文档同步：实现为公开方法 is_user_online（ws.py 与测试直接调用），
        # Redis 异常时返回 False 防御连接抖动
        """检查用户是否在线（Redis ws:online:{user_id} 是否存在）。"""
        try:
            redis = await get_redis()
            return await redis.exists(f"ws:online:{user_id}") > 0
        except Exception:
            return False

    @staticmethod
    async def _push_ws(user_id: int, event: str, data: dict) -> None:
        """通过 WebSocket 推送消息到用户频道。

        通过 Redis pub/sub 发布消息，WS 网关订阅后推送到客户端。
        """
        redis = await get_redis()
        # R13-P3 文档同步（R5-Infra-5）：发布频道与 WSManager 统一为
        # ws:relay:{room_id}（room_id="ws:user:{user_id}"），两套推送机制互通
        channel = f"ws:relay:ws:user:{user_id}"
        message = json.dumps({"event": event, "data": data})
        await redis.publish(channel, message)

    @staticmethod
    async def push_ws_message(user_id: int, event_type: str, data: dict) -> None:
        """公开方法：通过 WebSocket 推送消息（供 payment 等外部模块调用）。

        包装内部 _push_ws 方法，提供稳定的公开接口。
        """
        await NotificationService._push_ws(user_id, event_type, data)

    @staticmethod
    async def _send_wechat_subscribe(user_id: int, notification: dict) -> bool:
        """发送微信订阅消息。

        R12-Notif-2（Phase 2 外联边界确认）：微信订阅消息 API 接入属 Phase 2
        范围。Phase 1 行为——`SMS_MOCK=true` 或 `WECHAT_PAY_MOCK=true`（默认）
        时打 mock 日志直接返回 True；否则构造 template_msg 供日志审计（结构
        与 Phase 2 真实调用一致）并打 prepared 日志，真实发送在 Phase 2 接入
        `app.core.wechat.WechatClient` 后启用。模板字段 thing1/thing2 取
        title/content 前 20 字符（微信 thing 类型长度限制）。
        """
        from app.core.config import settings

        if settings.SMS_MOCK or settings.WECHAT_PAY_MOCK:
            logger.info(
                "wechat subscribe mock: user_id=%s type=%s",
                user_id, notification.get("type"),
            )
            return True

        # Phase 2 外联边界：接入微信订阅消息 API 后取消下方注释并配置 client
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
        # result = await client.send_subscribe_message(template_msg)
        # return result.get("errcode") == 0
        return True

    @staticmethod
    async def send_notification(
        user_id: int,
        notif_type: str,
        title: str,
        content: str,
        extra_data: Optional[dict] = None,
        wechat_template: Optional[str] = None,
    ) -> Optional[NotificationRecord]:
        """发送通知——核心通道选择逻辑。

        通道选择矩阵：
        - 用户在线 → WS 实时推送（不写 DB）
        - 用户离线 → 写 DB notification_record + 微信订阅消息（如需）
        """
        is_online = await NotificationService.is_user_online(user_id)

        if is_online:
            # 在线：WS 推送
            await NotificationService.push_ws_message(
                user_id, "notification", {
                    "type": notif_type,
                    "title": title,
                    "content": content,
                    "extra_data": extra_data or {},
                }
            )
            return None
        else:
            # 离线：写 DB + 可选微信订阅消息
            async with get_async_session() as db:
                record = NotificationRecord(
                    user_id=user_id,
                    type=notif_type,
                    title=title,
                    content=content,
                    is_read=False,
                    extra_data=extra_data,
                )
                db.add(record)
                await db.commit()
                await db.refresh(record)

                # 未读计数 +1
                redis = await get_redis()
                await redis.incr(f"notif:unread:{user_id}")

                # 发送微信订阅消息（如指定模板且用户已订阅）
                if wechat_template:
                    await NotificationService._send_wechat_subscribe(
                        user_id, {"title": title, "content": content}
                    )

                return record

    @staticmethod
    async def list_notifications(
        user_id: int,
        query: NotificationListQuery,
    ) -> PaginatedNotifications:
        """查询通知列表。"""
        async with get_async_session() as db:
            stmt = select(NotificationRecord).where(
                NotificationRecord.user_id == user_id
            )
            if query.is_read is not None:
                stmt = stmt.where(NotificationRecord.is_read == query.is_read)
            if query.type:
                stmt = stmt.where(NotificationRecord.type == query.type)
            stmt = stmt.order_by(NotificationRecord.created_at.desc())

            total, items = await paginate(db, stmt, query.page, query.page_size)
            return PaginatedNotifications(
                total=total,
                page=query.page,
                page_size=query.page_size,
                items=[NotificationBrief.model_validate(r) for r in items],
            )

    @staticmethod
    async def mark_read(
        user_id: int,
        notification_ids: list[int],
    ) -> MarkReadResponse:
        """批量标记已读。"""
        async with get_async_session() as db:
            stmt = (
                update(NotificationRecord)
                .where(
                    NotificationRecord.id.in_(notification_ids),
                    NotificationRecord.user_id == user_id,
                    NotificationRecord.is_read == False,
                )
                .values(is_read=True)
                .returning(NotificationRecord.id)
            )
            result = await db.execute(stmt)
            updated_ids = result.scalars().all()
            await db.commit()
            # R13-P3 文档同步：asyncpg 下 UPDATE rowcount 不可靠，
            # 实现改用 RETURNING 收集实际更新 id
            updated = len(updated_ids)

            # 更新未读计数缓存
            if updated > 0:
                redis = await get_redis()
                await redis.decrby(f"notif:unread:{user_id}", updated)
                # 防止负数
                current = int(await redis.get(f"notif:unread:{user_id}") or 0)
                if current < 0:
                    await redis.set(f"notif:unread:{user_id}", 0)

            return MarkReadResponse(updated_count=updated)

    @staticmethod
    async def get_unread_count(user_id: int) -> int:
        """获取未读通知数量（Redis 缓存优先，未命中时查 DB）。"""
        redis = await get_redis()
        cached = await redis.get(f"notif:unread:{user_id}")
        if cached is not None:
            return int(cached)
        # 缓存未命中，查 DB
        async with get_async_session() as db:
            count = await db.scalar(
                select(func.count(NotificationRecord.id)).where(
                    NotificationRecord.user_id == user_id,
                    NotificationRecord.is_read == False,
                )
            )
            count = count or 0
            # R13-P3 文档同步：回填缓存带 300s TTL，避免未读数长期陈旧
            await redis.set(f"notif:unread:{user_id}", count, ex=300)
            return count

    @staticmethod
    async def subscribe_templates(
        user_id: int,
        template_ids: list[str],
    ) -> SubscribeResponse:
        """微信订阅消息授权。"""
        # R13-P3 文档同步（R6-Notif-2 设计偏差，R12 测试已固定现契约）：
        # 无效模板 ID 静默过滤（API §13.3 的 422 行为属 Phase 2+ 文档同步项）；
        # 重新订阅为覆盖语义 —— 先删旧集合再写新集合，返回过滤后的列表
        valid_templates = {"analysis_complete", "payment_success", "training_reminder"}
        valid_ids = [t for t in template_ids if t in valid_templates]

        redis = await get_redis()
        key = f"notif:subscribed:{user_id}"
        # 清除旧订阅，设置新订阅（覆盖语义）
        await redis.delete(key)
        if valid_ids:
            await redis.sadd(key, *valid_ids)

        return SubscribeResponse(subscribed_templates=valid_ids)

    @staticmethod
    async def _check_reminder_frequency(
        user_id: int,
        redis,
    ) -> bool:
        """训练提醒频率控制：同一用户每周最多 2 次。"""
        key = f"notif:reminder:count:{user_id}:week"
        current = int(await redis.get(key) or 0)
        return current < NotificationService.REMINDER_WEEKLY_LIMIT

    @staticmethod
    async def send_training_reminder(
        user_id: int,
        last_training_days: int,
    ) -> None:
        """发送训练提醒（Celery Beat 调用）。

        规则：
        - >3 天未训练才发送
        - 同一用户每周最多 2 次
        """
        if last_training_days < NotificationService.REMINDER_INACTIVE_DAYS:
            return

        redis = await get_redis()
        if not await NotificationService._check_reminder_frequency(user_id, redis):
            return

        # R13-P3 文档同步：文案对齐实现（不含 extra_data 深链，前端按 type 路由）
        await NotificationService.send_notification(
            user_id=user_id,
            notif_type="training_reminder",
            title="训练提醒",
            content=f"您已经{last_training_days}天没有训练了，快来练习吧！",
            wechat_template="training_reminder",
        )

        # 递增本周计数 — TTL 按自然周对齐（到本周日 23:59:59）
        # R13-P3 文档同步：实现按自然周末计算 TTL（非固定 7 天），
        # 且以 incr 返回值判断是否首次设置
        key = f"notif:reminder:count:{user_id}:week"
        new_count = await redis.incr(key)
        if new_count == 1:
            now = datetime.now(timezone.utc)
            # 计算到本周日 23:59:59 的秒数（周一为一周起始）
            days_until_sunday = (6 - now.weekday()) % 7 or 7
            end_of_week = now.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=days_until_sunday)
            ttl_seconds = int((end_of_week - now).total_seconds())
            await redis.expire(key, max(ttl_seconds, 3600))  # 至少 1 小时

    @staticmethod
    async def on_ws_reconnect(user_id: int) -> None:
        """WebSocket 重连后的离线消息补偿。

        1. 拉取断连期间的未读通知（直查 DB —— Redis 缓存有 300s TTL，
           重连时刻需准确计数；R13-P3 文档同步）
        2. 通过 WS 推送 sync 事件
        """
        async with get_async_session() as db:
            count_result = await db.execute(
                select(func.count()).select_from(NotificationRecord).where(
                    NotificationRecord.user_id == user_id,
                    NotificationRecord.is_read == False,  # noqa: E712
                )
            )
            unread = count_result.scalar() or 0
        if unread > 0:
            await NotificationService.push_ws_message(
                user_id, "sync", {
                    "type": "notification",
                    "unread_count": unread,
                    "message": f"您有 {unread} 条未读通知",
                }
            )
```

---

## 6. API 路由实现

### 6.1 REST API 路由

```python
# app/api/v1/notification/router.py
# R13-P3 文档同步：装饰器顺序为 @router.* 在上、@limiter.limit 在下
# （slowapi 要求限流装饰器位于路由装饰器下方，否则路由表注册的是原始
# 函数、限流不生效），且端点签名必须含 request: Request 参数。
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.schemas.notification import (
    MarkReadRequest, SubscribeRequest, NotificationListQuery,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notification", tags=["通知"])


@router.get("/list", summary="通知列表")
@limiter.limit("100/minute")
async def list_notifications(
    request: Request,
    is_read: Optional[bool] = Query(default=None),
    type: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """查询通知列表（分页）"""
    query = NotificationListQuery(
        is_read=is_read, type=type, page=page, page_size=page_size,
    )
    data = await NotificationService.list_notifications(user.id, query)
    return success(data=data)


@router.post("/read", summary="标记已读")
@limiter.limit("100/minute")
async def mark_read(
    body: MarkReadRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """批量标记通知为已读"""
    data = await NotificationService.mark_read(user.id, body.notification_ids)
    return success(data=data, message="已标记为已读")


@router.post("/subscribe", summary="微信订阅消息授权")
@limiter.limit("100/minute")
async def subscribe(
    body: SubscribeRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """微信订阅消息授权"""
    data = await NotificationService.subscribe_templates(user.id, body.template_ids)
    return success(data=data, message="订阅已更新")


@router.get("/unread-count", summary="未读通知数量")
@limiter.limit("100/minute")
async def unread_count(
    request: Request,
    user: User = Depends(get_current_user),
):
    """获取未读通知数量"""
    count = await NotificationService.get_unread_count(user.id)
    return success(data={"unread_count": count})
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.notification.router import router as notification_router
api_router.include_router(notification_router)
```

### 6.2 WebSocket 端点

```python
# app/api/v1/ws.py
"""WebSocket 端点。"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis import get_redis
from app.core.security import decode_token
from app.services.notification_service import NotificationService
from app.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 主端点 — 通过 Sec-WebSocket-Protocol 传递 JWT。

    认证流程（R13-P3 文档同步，对齐 app/api/v1/ws.py 现实现）：
    1. 从 sec-websocket-protocol 提取 jwt.{token}（SEC-002：子协议传 token
       避免 URL query 泄露）
    2. 解码 JWT 获取 user_id，accept 时回传选定子协议
    3. 订阅 Redis ws:relay:ws:user:{user_id} 频道（R5-Infra-5：与
       WSManager.broadcast_to_user / broadcast_to_room 的 relay 频道统一）
    4. 重连补偿：subscribe 之后再调用 on_ws_reconnect（R6-Notif-1：Redis
       pubsub 不缓存未订阅期间的消息，先 publish 后 subscribe 会丢 sync 事件）
    5. 三个并行协程：relay_messages + heartbeat + receive_loop
    6. 断连时清理 Redis 状态（在线标记 + pubsub）
    """
    # Step 0: 提取 token
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    token = ""
    if protocols:
        for proto in protocols.split(","):
            proto = proto.strip()
            if proto.startswith("jwt."):
                token = proto[5:]  # strip "jwt." prefix
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

    # Step 2: 接受连接（回传选定的子协议）
    await websocket.accept(subprotocol=f"jwt.{token}")

    redis = await get_redis()
    pubsub = redis.pubsub()
    # R5-Infra-5：频道命名与 WSManager 统一
    await pubsub.subscribe(f"ws:relay:ws:user:{user_id}")

    # Step 2.5: WS 重连补偿 — 推送离线期间未读通知（R4-Notif-3）
    # R6-Notif-1：在 subscribe 之后调用，确保 sync 消息能被 relay 接收
    try:
        await NotificationService.on_ws_reconnect(user_id)
    except Exception as e:
        logger.warning("ws_on_reconnect failed: %s", e)

    # Step 3: 发送 connected 事件
    await websocket.send_json({
        "event": "connected",
        "data": {"user_id": user_id},
    })

    # Step 4: 设置在线状态（TTL 120s，heartbeat 每 30s 续期）
    await redis.setex(f"ws:online:{user_id}", NotificationService.WS_ONLINE_TTL, "1")

    async def relay_messages():
        """Redis pubsub -> WS 消息中继"""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # redis-py asyncio 返回 str，直接 send_text（无需 decode）
                    await websocket.send_text(message["data"])
        except WebSocketDisconnect:
            return

    async def heartbeat():
        """在线状态续期 — 每 30s 更新 Redis TTL"""
        try:
            while True:
                await redis.setex(
                    f"ws:online:{user_id}",
                    NotificationService.WS_ONLINE_TTL, "1",
                )
                await asyncio.sleep(30)
        except WebSocketDisconnect:
            return

    async def receive_loop():
        """接收客户端消息（ping/pong + 比赛频道订阅）"""
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
                        # R5-Infra-5：与 broadcast_to_room 频道命名统一
                        await pubsub.subscribe(f"ws:relay:ws:match:{match_id}")
                        subscribed_matches.add(match_id)
                        await websocket.send_json({
                            "event": "subscribed",
                            "data": {"match_id": match_id},
                        })
                        # R12-SC-2：订阅后推送 sync_match 全量同步
                        # （当前比分状态 + 得分序列；非属主订阅 get_match_detail
                        #   404 时跳过 sync，保持房间广播行为）
                        try:
                            detail = await ScoringService.get_match_detail(user_id, match_id)
                            await websocket.send_json({
                                "event": "sync_match",
                                "data": {
                                    "match_id": match_id,
                                    "status": detail["status"],
                                    "current_score": detail["current_score"],
                                    "score_sequence": detail["score_sequence"],
                                },
                            })
                        except Exception:
                            pass
        except WebSocketDisconnect:
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
    await redis.delete(f"ws:online:{user_id}")
    await pubsub.unsubscribe(f"ws:relay:ws:user:{user_id}")
    await pubsub.close()
```

### 6.3 训练提醒 Celery Beat

```python
# app/tasks/notification.py
"""Celery tasks — 通知管理

R13-P3 文档同步：实际任务文件为 app/tasks/notification.py（原
notification_beat.py），任务名带 app.tasks.notification. 前缀（与
beat_schedule.py 注册条目一致）；训练提醒候选判定已提取为
NotificationService.get_training_reminder_candidates（R12-Notif-1）。
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.notification.training_reminder")
def training_reminder():
    """训练提醒——每日 19:00 执行。

    规则：
    1. 查找 >3 天无 AI 分析任务（completed）或记分牌比赛（finished）
       活动的 active 用户（R12-Notif-1：判定不依赖 TrainingPlan）
    2. 同一用户每周最多 2 次训练提醒（NotificationService 内部控制）
    3. 在线用户 WS 推送；离线用户写 DB + 微信订阅消息

    注意：Celery worker 默认不支持 async def task，使用 asyncio.run() 驱动。
    """
    import asyncio

    async def _run():
        from app.core.database import async_session_factory
        from app.services.notification_service import NotificationService

        async with async_session_factory() as db:
            # R12-Notif-1: 候选判定基于 3 天内 AI 分析/比赛活动
            # （原实现基于 TrainingPlan.updated_at，inner join 排除了
            #   无计划用户，且刚完成 AI 分析/比赛的用户被误判为未训练）
            candidates = await NotificationService.get_training_reminder_candidates(db)

        pushed = 0
        for user_id, days_inactive in candidates:
            try:
                await NotificationService.send_training_reminder(
                    user_id=user_id,
                    last_training_days=days_inactive,
                )
                pushed += 1
            except Exception as e:
                logger.warning(
                    "training_reminder push failed user_id=%s: %s", user_id, e,
                )
        return {
            "status": "ok",
            "candidates": len(candidates),
            "pushed": pushed,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.exception("training_reminder failed: %s", e)
        return {"status": "error", "error": str(e)}
```

**Celery Beat 配置**：已在统一调度表 `beat_schedule.py` 中注册（见 `notification-training-reminder` 任务，每日 19:00 触发）。无需在模块内单独定义 beat_schedule。

### 6.4 旧通知清理 Celery Task

```python
# app/tasks/notification.py（续）
# R13-P3 文档同步：NotificationRecord 无 status 列，"归档"落地为直接删除
# 180 天前未读记录（控制表体积）；任务体 asyncio.run 包装 + 模块级 async
# impl（R12 测试重构：单测在既有事件循环内直调 impl，规避共享连接池冲突）。

# 清理策略阈值（与设计 §6.1 / beat_schedule 一致）
READ_RETENTION_DAYS = 90     # 已读通知保留 90 天
UNREAD_RETENTION_DAYS = 180  # 未读通知删除阈值（180 天）


@shared_task(name="app.tasks.notification.cleanup_old_notifications")
def cleanup_old_notifications():
    """清理过期通知（每月 1 日 02:00）

    策略：
    - 已读通知：删除 created_at 早于 90 天前的记录（bulk DELETE）
    - 未读通知：删除 created_at 早于 180 天前的记录（原设计为归档，
      无独立归档表且模型无 status 列，直接删除以控制表体积）
    - 幂等：基于 WHERE 条件清理，重复执行无副作用
    """
    import asyncio

    try:
        return asyncio.run(cleanup_old_notifications_impl())
    except Exception as e:
        logger.exception("cleanup_old_notifications failed: %s", e)
        return {"status": "error", "error": str(e)}


async def cleanup_old_notifications_impl() -> dict:
    """清理逻辑（模块级 async 函数，便于单元测试在既有事件循环内直接调用）"""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import delete
    from app.core.database import async_session_factory
    from app.models.notification import NotificationRecord

    now = datetime.now(timezone.utc)
    read_threshold = now - timedelta(days=READ_RETENTION_DAYS)
    unread_threshold = now - timedelta(days=UNREAD_RETENTION_DAYS)

    async with async_session_factory() as db:
        # 1. 删除 90 天前已读通知
        read_result = await db.execute(
            delete(NotificationRecord).where(
                NotificationRecord.is_read == True,  # noqa: E712
                NotificationRecord.created_at < read_threshold,
            )
        )
        read_deleted = read_result.rowcount or 0

        # 2. 删除 180 天前未读通知
        unread_result = await db.execute(
            delete(NotificationRecord).where(
                NotificationRecord.is_read == False,  # noqa: E712
                NotificationRecord.created_at < unread_threshold,
            )
        )
        unread_deleted = unread_result.rowcount or 0

        await db.commit()

    logger.info(
        "cleanup_old_notifications done: read_deleted=%s unread_deleted=%s",
        read_deleted, unread_deleted,
    )
    return {
        "status": "ok",
        "read_deleted": read_deleted,
        "unread_deleted": unread_deleted,
    }
```

**Celery Beat 配置**：已在统一调度表 `beat_schedule.py` 中注册（见 `notification-old-cleanup` 任务，每月 1 日 02:00 触发）。

---

## 7. 冒烟测试脚本

```python
# tests/smoke/notification_smoke_test.py
"""
notification 模块冒烟测试。
用法: python -m tests.smoke.notification_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 登录获取 Token
        print("1. Logging in...")
        login_resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "冒烟测试",
        })
        if login_resp.status_code != 200:
            print(f"   ✗ Login failed: {login_resp.status_code}")
            return
        token = login_resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("   ✓ Login success")

        # 2. 查询通知列表
        print("2. Testing GET /notification/list...")
        resp = await client.get("/notification/list", headers=headers)
        assert resp.status_code == 200, f"List failed: {resp.text}"
        items = resp.json()["data"]["items"]
        print(f"   ✓ List returned {len(items)} items")

        # 3. 查询未读数量
        print("3. Testing GET /notification/unread-count...")
        resp = await client.get("/notification/unread-count", headers=headers)
        assert resp.status_code == 200
        count = resp.json()["data"]["unread_count"]
        print(f"   ✓ Unread count: {count}")

        # 4. 标记已读（如有未读通知）
        if items:
            ids = [item["id"] for item in items[:2]]
            print(f"4. Testing POST /notification/read (ids={ids})...")
            resp = await client.post(
                "/notification/read",
                json={"notification_ids": ids},
                headers=headers,
            )
            assert resp.status_code == 200
            print(f"   ✓ Marked {resp.json()['data']['updated_count']} as read")

        # 5. 订阅模板
        print("5. Testing POST /notification/subscribe...")
        resp = await client.post(
            "/notification/subscribe",
            json={"template_ids": ["analysis_complete"]},
            headers=headers,
        )
        assert resp.status_code == 200
        print("   ✓ Subscribe success")

    print("\nnotification_smoke_test: ALL PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_notification.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.notification_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导入
- [ ] Router 已在 `app/api/v1/__init__.py` 中注册
- [ ] WebSocket 端点 `/ws` 可正常连接（带 token）
- [ ] Redis 在线标记 TTL 正确（120s 续期）
- [ ] 通道选择矩阵正确（在线→WS，离线→DB+微信）
- [ ] 离线消息补偿：断连期间消息写入 DB，重连后 sync 事件推送
- [ ] 训练提醒 Celery Beat 每日 19:00 执行
- [ ] 训练提醒频率控制（>3 天未训练，每周最多 2 次）
- [ ] WebSocket 事件类型正确（connected/subscribed/sync_match/sync/notification/analysis_progress/score_update/payment_success/ping/pong）
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- Schema **必须** 遵循命名：`NotificationBrief`、`MarkReadRequest`、`PaginatedNotifications`
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- WebSocket 端点 **必须** 校验 JWT token 后才 accept
- 用户在线标记 **必须** 设置 Redis TTL，**禁止** 永不过期
- 离线消息 **必须** 写入 DB notification_record，**禁止** 仅依赖 Redis
- 训练提醒 **必须** 执行频率控制（每周 2 次上限），**禁止** 无限发送
- WebSocket 消息推送 **必须** 通过 Redis pub/sub 解耦，**禁止** 在 WS 端点直接调用 Service
- 所有 REST API 端点 **必须** 添加 `@limiter.limit("100/minute")` 限流装饰器，**禁止** 裸奔无限流
- WebSocket 端点（`@ws_router.websocket("/ws")`）**不需要** slowapi 限流装饰器，连接级限流由 WS 层处理
- `from app.core.limiter import limiter` **必须** 在 REST 路由文件 import 区声明，**禁止** 遗漏导入

### 覆盖度修复说明

- **[X-14] 实现 _send_wechat_subscribe（P2）**：将 `pass` 占位实现替换为完整的微信订阅消息推送逻辑，通过 `wechat_client.send_subscribe_message` 发送，使用 `settings.WECHAT_SUBSCRIBE_TEMPLATE_ID` 模板 ID。方法签名从 `(user_id, template_id, data) -> None` 改为 `(user_id, notification: dict) -> bool`，调用站点同步更新
- **[X-15] 分区策略说明（P2）**：notification_record 表应按月分区（PARTITION BY RANGE (created_at)），pg_cron 管理 3 个月分区生命周期（drop 旧分区）。已读通知记录 90 天前由 Celery Beat 清理（见 `beat_schedule.py` 的 `notification-old-cleanup` 任务）。Alembic 迁移仅创建父表，子分区由 pg_cron 或运维脚本管理。已在 Model 定义中添加分区策略注释
- **[X-18] content 字段约束修复（P3）**：`content` 字段从 `Mapped[str]`（NOT NULL）改为 `Mapped[str | None]`（nullable=True），与 DB 设计 §2.20 中 `content TEXT NULL` 对齐
- **GET /notification/unread-count 回写说明（P3）**：GET /notification/unread-count 为切片新增端点，API 设计 v1.3 §13 中未定义。属于合理增强（前端需要未读计数），需回写 API 设计文档
- **覆盖度修复**：已根据覆盖度分析报告修复 A-9（`datetime.utcnow()` naive → timezone-aware，`default`/`onupdate` 改为 lambda 表达式，import 补充 `timezone`）

### R13-P3 文档同步（Round 13 复验，Notification 模块）

以实现为准回写，涉及 §1/§2/§3/§5/§6/§8（`_send_wechat_subscribe` 段已含 R12-Notif-2 Phase 2 边界声明，本轮未改动）：

| # | 差异 | 修改位置 |
|---|------|---------|
| N1 | 任务文件 `notification_beat.py` → `app/tasks/notification.py`（训练提醒 + 旧通知清理两任务，任务名带 `app.tasks.notification.` 前缀） | §1 任务清单、§6.3、§6.4 |
| N2 | `_is_user_online` → 公开方法 `is_user_online`（含 Redis 异常防御） | §2 测试样例、§5 |
| N3 | WS 频道 `ws:user:{id}` → `ws:relay:ws:user:{id}`（R5-Infra-5 与 WSManager 统一） | §5 `_push_ws`、§6.2 |
| N4 | `subscribe_templates` 无效模板 422 → 静默过滤 + 覆盖语义（R6-Notif-2 偏差，R12 测试已固定现契约；API §13.3 的 422 属 Phase 2+ 文档同步项） | §5 |
| N5 | 训练提醒周计数 TTL 固定 7 天 → 自然周末对齐（incr 返回值判首次）；提醒文案/extra_data 对齐实现 | §5 `send_training_reminder` |
| N6 | `get_unread_count` 缓存回填补 300s TTL；`mark_read` rowcount → RETURNING（asyncpg rowcount 不可靠）；`on_ws_reconnect` 直查 DB（重连时刻需准确计数） | §5 |
| N7 | 路由样例装饰器顺序（`@router.*` 在上、`@limiter.limit` 在下，slowapi 生效要求）+ `request: Request` 参数 | §6.1 |
| N8 | WS 样例：subscribe 先于 `on_ws_reconnect`（R6-Notif-1）、比赛频道订阅 + `subscribed`/`sync_match` 事件（R12-SC-2）、`send_text` 直传 str | §6.2 |
| N9 | 训练提醒候选判定提取为 `NotificationService.get_training_reminder_candidates`（R12-Notif-1），Match 导入自 `app.models.match` | §6.3 |
| N10 | 清理任务"归档 status=archived" → 直接删除（`NotificationRecord` 无 status 列）+ 模块级 async impl | §6.4 |
| N11 | Model `created_at` Python default → `server_default=func.now()` | §3 |
| N12 | REST 端点数 3 → 4（unread-count 为切片新增，见文末回写说明） | §1、§8 |

