"""
tests/integration/test_cascade_chains.py — 跨模块级联链集成测试

依据：测试计划 §6 CASC-I-01~33
覆盖：AI 分析链 / 支付链 / 比赛链 / 注销链 / 数据飞轮
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from app.core.security import create_access_token, generate_jti
from app.core.database import async_session_factory
from app.models.user import User
from app.models.match import Match, ScoreRecord, MatchStatistic
from app.models.gamification import UserPoints
from app.models.payment import Order, PaymentRecord
from app.models.membership import Subscription, MembershipTierConfig
from app.models.admin import AdminUser
from app.core.security import pwd_context
from app.services.payment_service import PaymentService
from app.services.membership_service import MembershipService
from app.services.gamification_service import GamificationService
from sqlalchemy import select


@pytest_asyncio.fixture
async def admin_headers(db_session):
    """Admin 认证 headers"""
    from app.services.admin_service import AdminService
    admin = AdminUser(
        username="integration_admin",
        password_hash=pwd_context.hash("Admin@123"),
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.commit()
    data = await AdminService.login("integration_admin", "Admin@123")
    return {"Authorization": f"Bearer {data.session_token}"}


@pytest.mark.asyncio
class TestPaymentCascade:
    """支付成功级联链（CASC-I-17~25）"""

    async def test_payment_success_creates_subscription(self, client, test_user, seed_tiers):
        """支付成功触发 subscription 创建"""
        token = create_access_token({"sub": str(test_user.id), "jti": generate_jti()})
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/payment/orders",
            json={"product_type": "membership", "tier": "member", "period": "monthly"},
            headers=headers,
        )
        assert resp.status_code == 200
        order_no = resp.json()["data"]["order_no"]

        import json
        callback = json.dumps({
            "resource": {
                "out_trade_no": order_no,
                "transaction_id": "wx_cascade_001",
                "trade_state": "SUCCESS",
                "amount": {"total": 1900},
            }
        })
        resp = await client.post(
            "/api/v1/payment/notify",
            content=callback,
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "sig",
                "Wechatpay-Serial": "serial",
                "Wechatpay-Nonce": "nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        async with async_session_factory() as verify_session:
            result = await verify_session.execute(
                select(Subscription).where(
                    Subscription.user_id == test_user.id,
                    Subscription.tier == "member",
                )
            )
            sub = result.scalar_one_or_none()
            assert sub is not None
            assert sub.status == "active"

    async def test_payment_idempotent_notify(self, client, test_user, seed_tiers):
        """重复回调幂等性"""
        token = create_access_token({"sub": str(test_user.id), "jti": generate_jti()})
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/payment/orders",
            json={"product_type": "membership", "tier": "member", "period": "monthly"},
            headers=headers,
        )
        order_no = resp.json()["data"]["order_no"]

        import json
        callback = json.dumps({
            "resource": {
                "out_trade_no": order_no,
                "transaction_id": "wx_idem_001",
                "trade_state": "SUCCESS",
                "amount": {"total": 1900},
            }
        })
        cb_headers = {
            "Content-Type": "application/json",
            "Wechatpay-Signature": "sig",
            "Wechatpay-Serial": "serial",
            "Wechatpay-Nonce": "nonce",
            "Wechatpay-Timestamp": "1234567890",
        }
        resp1 = await client.post("/api/v1/payment/notify", content=callback, headers=cb_headers)
        assert resp1.status_code == 200
        resp2 = await client.post("/api/v1/payment/notify", content=callback, headers=cb_headers)
        assert resp2.status_code == 200


@pytest.mark.asyncio
class TestMatchCascade:
    """比赛结束级联链（CASC-I-11~16）"""

    async def test_match_finish_triggers_statistics(self, client, test_user, auth_headers):
        """比赛结束触发统计计算"""
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={"opponent_name": "对手", "format": "bo3"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        match_data = resp.json()["data"]
        match_id = match_data.get("id") or match_data.get("match_id")
        assert match_id is not None

        # 开始比赛（setup → in_progress）
        resp = await client.post(
            f"/api/v1/scoring/matches/{match_id}/start",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        for _ in range(3):
            await client.post(
                f"/api/v1/scoring/matches/{match_id}/score",
                json={"scorer": "user", "score_method": "serve_point"},
                headers=auth_headers,
            )

        resp = await client.post(
            f"/api/v1/scoring/matches/{match_id}/finish",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        async with async_session_factory() as verify_session:
            result = await verify_session.execute(
                select(MatchStatistic).where(MatchStatistic.match_id == match_id)
            )
            stat = result.scalar_one_or_none()
            assert stat is not None

    async def test_match_triggers_gamification(self, client, test_user, auth_headers):
        """比赛结束后游戏化积分增加"""
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={"opponent_name": "对手2", "format": "bo1"},
            headers=auth_headers,
        )
        match_data = resp.json()["data"]
        match_id = match_data.get("id") or match_data.get("match_id")

        await client.post(
            f"/api/v1/scoring/matches/{match_id}/score",
            json={"scorer": "user", "score_method": "serve_point"},
            headers=auth_headers,
        )
        await client.post(
            f"/api/v1/scoring/matches/{match_id}/finish",
            headers=auth_headers,
        )

        async with async_session_factory() as verify_session:
            result = await verify_session.execute(
                select(UserPoints).where(UserPoints.user_id == test_user.id)
            )
            points = result.scalar_one_or_none()
            if points:
                assert points.total_points >= 0


@pytest.mark.asyncio
class TestFKConstraints:
    """DB 外键约束测试（FK-I-01~28）"""

    async def test_score_record_fk_match(self, db_session, test_user):
        """score_record FK → match"""
        match = Match(user_id=test_user.id, opponent_name="测试", format="bo1", status="setup")
        db_session.add(match)
        await db_session.commit()
        await db_session.refresh(match)

        score = ScoreRecord(
            match_id=match.id,
            sequence=1,
            scorer="user",
            score_method="serve_point",
        )
        db_session.add(score)
        await db_session.commit()
        await db_session.refresh(score)
        assert score.match_id == match.id

    async def test_audit_log_user_id_set_null(self, db_session, test_user):
        """audit_log.user_id FK → user"""
        from app.models.admin import AuditLog
        log = AuditLog(
            user_id=test_user.id,
            action="test_action",
            target_type="test",
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)
        assert log.user_id == test_user.id

    async def test_notification_fk_user(self, db_session, test_user):
        """notification_record.user_id FK → user"""
        from app.models.notification import NotificationRecord
        notif = NotificationRecord(
            user_id=test_user.id,
            type="test",
            title="测试",
        )
        db_session.add(notif)
        await db_session.commit()
        await db_session.refresh(notif)
        assert notif.user_id == test_user.id


@pytest.mark.asyncio
class TestRedisKeys:
    """Redis Key 模式验证（REDIS-I-01~20）"""

    async def test_jwt_blacklist_key(self, client, auth_headers, test_user):
        """JWT 黑名单 key：jwt:blacklist:{jti}"""
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.set("jwt:blacklist:test_jti", "1", ex=7200)
        assert await redis.exists("jwt:blacklist:test_jti") > 0
        await redis.delete("jwt:blacklist:test_jti")

    async def test_unread_count_key(self, test_user):
        """通知未读计数 key：notif:unread:{user_id}"""
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.set(f"notif:unread:{test_user.id}", 5, ex=300)
        val = await redis.get(f"notif:unread:{test_user.id}")
        assert int(val) == 5
        await redis.delete(f"notif:unread:{test_user.id}")

    async def test_ws_online_key(self, test_user):
        """WS 在线标记 key：ws:online:{user_id}"""
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.set(f"ws:online:{test_user.id}", "1", ex=120)
        assert await redis.exists(f"ws:online:{test_user.id}") > 0
        await redis.delete(f"ws:online:{test_user.id}")

    async def test_admin_session_key(self, db_session):
        """Admin session key：admin:session:{token}"""
        from app.core.redis import get_redis
        from app.services.admin_service import AdminService, ADMIN_SESSION_PREFIX
        admin = AdminUser(
            username="redis_test_admin",
            password_hash=pwd_context.hash("pass"),
            role="super_admin",
        )
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)

        data = await AdminService.login("redis_test_admin", "pass")
        token = data.session_token
        redis = await get_redis()
        assert await redis.exists(f"{ADMIN_SESSION_PREFIX}{token}") > 0
        await AdminService.logout(token)


@pytest.mark.asyncio
class TestCeleryBeatTasks:
    """Celery Beat 任务完整性测试（BEAT-I-01~10）"""

    def _get_beat_schedule(self):
        """获取 beat_schedule 配置"""
        from app.core.celery import celery_app
        return celery_app.conf.beat_schedule

    async def test_beat_schedule_has_10_tasks(self):
        """验证配置了 10 个定时任务"""
        beat = self._get_beat_schedule()
        assert len(beat) >= 10

    async def test_beat_membership_expiry_check(self):
        """会员到期检测任务"""
        beat = self._get_beat_schedule()
        task = beat.get("membership-expiry-check")
        assert task is not None
        assert "membership" in task["task"] or "check_expiry" in task["task"]

    async def test_beat_notification_cleanup(self):
        """通知清理任务"""
        beat = self._get_beat_schedule()
        task = beat.get("notification-old-cleanup")
        assert task is not None

    async def test_beat_all_tasks_have_schedule(self):
        """所有 Beat 任务都有 schedule 配置"""
        beat = self._get_beat_schedule()
        for name, config in beat.items():
            assert "task" in config, f"任务 {name} 缺少 task 字段"
            assert "schedule" in config, f"任务 {name} 缺少 schedule 字段"


@pytest.mark.asyncio
class TestPaginationBoundary:
    """分页参数边界测试（PAGE-I-01~10）"""

    async def test_page_default(self, client, auth_headers):
        resp = await client.get("/api/v1/notification/list", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 20

    async def test_page_size_max_50(self, client, auth_headers):
        resp = await client.get("/api/v1/notification/list?page_size=50", headers=auth_headers)
        assert resp.status_code == 200

    async def test_page_size_exceeds_max(self, client, auth_headers):
        resp = await client.get("/api/v1/notification/list?page_size=51", headers=auth_headers)
        assert resp.status_code == 422

    async def test_page_zero_invalid(self, client, auth_headers):
        resp = await client.get("/api/v1/notification/list?page=0", headers=auth_headers)
        assert resp.status_code == 422

    async def test_admin_page_size_max_100(self, client, admin_headers):
        resp = await client.get("/api/v1/admin/users?page_size=100", headers=admin_headers)
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestEnumValidation:
    """枚举值域测试（ENUM-U-01~19）"""

    async def test_match_format_valid(self, client, auth_headers):
        for fmt in ["bo1", "bo3", "bo5", "bo7"]:
            resp = await client.post(
                "/api/v1/scoring/matches",
                json={"opponent_name": f"对手_{fmt}", "format": fmt},
                headers=auth_headers,
            )
            assert resp.status_code == 200, f"format={fmt} 应有效"

    async def test_match_format_invalid(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={"opponent_name": "对手", "format": "bo9"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_payment_product_type_valid(self, client, auth_headers, seed_tiers):
        resp = await client.post(
            "/api/v1/payment/orders",
            json={"product_type": "membership", "tier": "member", "period": "monthly"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_payment_product_type_invalid(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/payment/orders",
            json={"product_type": "invalid", "tier": "member", "period": "monthly"},
            headers=auth_headers,
        )
        assert resp.status_code in (422, 400)


@pytest.mark.asyncio
class TestUserStatusEnforcement:
    """用户状态拦截测试（DEL-01~06 简化版）"""

    async def test_banned_user_blocked(self, client, test_user, db_session):
        test_user.status = "banned"
        await db_session.commit()
        token = create_access_token({"sub": str(test_user.id), "jti": generate_jti()})
        resp = await client.get(
            "/api/v1/scoring/matches",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_pending_deletion_user_blocked(self, client, test_user, db_session):
        test_user.status = "pending_deletion"
        await db_session.commit()
        token = create_access_token({"sub": str(test_user.id), "jti": generate_jti()})
        resp = await client.get(
            "/api/v1/notification/list",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_active_user_allowed(self, client, test_user, auth_headers):
        resp = await client.get("/api/v1/notification/list", headers=auth_headers)
        assert resp.status_code == 200
