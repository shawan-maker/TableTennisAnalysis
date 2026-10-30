"""
tests/unit/test_notification.py — 通知模块单元测试

依据：切片 12-notification/backend.md §7
      API §13 notification 端点
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.services.notification_service import NotificationService


@pytest.mark.asyncio
class TestNotificationService:
    """通知服务单元测试"""

    async def test_is_user_online_false(self, db_session):
        """未设置在线标记的用户应返回 False"""
        result = await NotificationService.is_user_online(999999)
        assert result is False

    async def test_send_notification_offline(self, db_session, test_user):
        """离线用户发送通知应写入 DB"""
        result = await NotificationService.send_notification(
            user_id=test_user.id,
            notif_type="test_type",
            title="测试通知",
            content="测试内容",
            extra_data={"key": "value"},
        )
        assert result is not None
        assert result.title == "测试通知"
        assert result.type == "test_type"
        assert result.is_read is False
        assert result.extra_data == {"key": "value"}

    async def test_list_notifications(self, db_session, test_user):
        """查询通知列表"""
        # 先创建几条通知
        for i in range(3):
            await NotificationService.send_notification(
                user_id=test_user.id,
                notif_type="test_type",
                title=f"通知 {i}",
                content=f"内容 {i}",
            )

        from app.schemas.notification import NotificationListQuery
        result = await NotificationService.list_notifications(
            test_user.id, NotificationListQuery(page=1, page_size=10)
        )
        assert result["total"] >= 3
        assert len(result["items"]) >= 3

    async def test_list_notifications_filter_type(self, db_session, test_user):
        """按类型过滤通知列表"""
        await NotificationService.send_notification(
            user_id=test_user.id,
            notif_type="analysis_complete",
            title="分析完成",
            content="",
        )
        await NotificationService.send_notification(
            user_id=test_user.id,
            notif_type="payment_success",
            title="支付成功",
            content="",
        )

        from app.schemas.notification import NotificationListQuery
        result = await NotificationService.list_notifications(
            test_user.id, NotificationListQuery(type="analysis_complete")
        )
        assert all(item.type == "analysis_complete" for item in result["items"])

    async def test_mark_read(self, db_session, test_user):
        """批量标记已读"""
        notif = await NotificationService.send_notification(
            user_id=test_user.id,
            notif_type="test_type",
            title="测试",
            content="内容",
        )
        assert notif is not None

        result = await NotificationService.mark_read(test_user.id, [notif.id])
        assert result.updated_count == 1

    async def test_mark_read_user_isolation(self, db_session, test_user):
        """标记已读用户隔离"""
        notif = await NotificationService.send_notification(
            user_id=test_user.id,
            notif_type="test_type",
            title="测试",
            content="内容",
        )
        # 另一用户尝试标记应不生效
        result = await NotificationService.mark_read(999999, [notif.id])
        assert result.updated_count == 0

    async def test_get_unread_count(self, db_session, test_user):
        """获取未读通知数量"""
        # 清除可能的缓存
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.delete(f"notif:unread:{test_user.id}")

        for i in range(3):
            await NotificationService.send_notification(
                user_id=test_user.id,
                notif_type="test_type",
                title=f"通知 {i}",
                content="内容",
            )
        count = await NotificationService.get_unread_count(test_user.id)
        assert count >= 3

    async def test_subscribe_templates(self, db_session, test_user):
        """订阅模板"""
        from app.schemas.notification import SubscribeResponse
        result = await NotificationService.subscribe_templates(
            test_user.id, ["analysis_complete", "payment_success", "invalid_template"]
        )
        assert isinstance(result, SubscribeResponse)
        assert "analysis_complete" in result.subscribed_templates
        assert "payment_success" in result.subscribed_templates
        assert "invalid_template" not in result.subscribed_templates


@pytest.mark.asyncio
class TestNotificationRouter:
    """通知路由接口测试"""

    async def test_list_without_token(self, client):
        """未登录访问通知列表"""
        resp = await client.get("/api/v1/notification/list")
        assert resp.status_code == 401

    async def test_list_with_token(self, client, auth_headers):
        """已登录访问通知列表"""
        resp = await client.get("/api/v1/notification/list", headers=auth_headers)
        assert resp.status_code == 200
        assert "data" in resp.json()

    async def test_unread_count(self, client, auth_headers):
        """获取未读数量"""
        resp = await client.get("/api/v1/notification/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert "unread_count" in resp.json()["data"]

    async def test_mark_read_empty_ids(self, client, auth_headers):
        """空 ID 列表应 422"""
        resp = await client.post(
            "/api/v1/notification/read",
            json={"notification_ids": []},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_subscribe(self, client, auth_headers):
        """订阅模板"""
        resp = await client.post(
            "/api/v1/notification/subscribe",
            json={"template_ids": ["analysis_complete"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    # -------------------------------------------------------------
    # R12-Notif-7/8/9: is_read 过滤 + 批量已读/订阅参数校验
    # -------------------------------------------------------------

    async def test_list_is_read_filter(self, client, auth_headers, test_user):
        """R12-Notif-7: is_read=true/false 精确过滤已读/未读通知"""
        # 种子：3 条未读，第 1 条标记已读 → 2 未读 + 1 已读
        ids = []
        for i in range(3):
            result = await NotificationService.send_notification(
                user_id=test_user.id,
                notif_type="filter_test",
                title=f"过滤测试 {i}",
                content="内容",
            )
            ids.append(result.id)
        await NotificationService.mark_read(test_user.id, [ids[0]])

        # is_read=true → 仅已读那条
        resp = await client.get(
            "/api/v1/notification/list?is_read=true&page=1&page_size=20",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["id"] == ids[0]
        assert data["items"][0]["is_read"] is True

        # is_read=false → 剩余未读两条
        resp = await client.get(
            "/api/v1/notification/list?is_read=false&page=1&page_size=20",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert all(item["is_read"] is False for item in data["items"])

    async def test_mark_read_over_100_ids_422(self, client, auth_headers):
        """R12-Notif-8: notification_ids 超 100（max_length=100）→ 422"""
        resp = await client.post(
            "/api/v1/notification/read",
            json={"notification_ids": list(range(1, 102))},
            headers=auth_headers,
        )
        assert resp.status_code == 422

        # 对照：恰好 100 个 → 通过校验进入业务层（标记 0 条，正常 200）
        resp = await client.post(
            "/api/v1/notification/read",
            json={"notification_ids": list(range(1, 101))},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_subscribe_empty_template_ids_422(self, client, auth_headers):
        """R12-Notif-9: template_ids 空列表（min_length=1）→ 422"""
        resp = await client.post(
            "/api/v1/notification/subscribe",
            json={"template_ids": []},
            headers=auth_headers,
        )
        assert resp.status_code == 422
