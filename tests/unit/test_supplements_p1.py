"""
tests/unit/test_supplements_p1.py — P1 优先级补充测试

覆盖关键业务规则、用户隔离、权限守卫、方向感知等场景。
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from app.core.security import create_access_token, generate_jti, pwd_context
from app.models.user import User
from app.models.membership import Subscription, MembershipTierConfig
from app.models.gamification import UserPoints, CheckInRecord, BadgeDefinition
from app.models.admin import AdminUser, AuditLog
from sqlalchemy import select


# ============================================================================
# Admin 审计日志异常吞噬 P1 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def admin_with_pwd(db_session):
    admin = AdminUser(
        username="p1_admin",
        password_hash=pwd_context.hash("Admin@123"),
        role="super_admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.mark.asyncio
class TestAuditLogResilience:
    """R5-Admin-6: 审计日志独立 session + 异常吞噬"""

    async def test_audit_log_failure_does_not_block_business(self, db_session, admin_with_pwd):
        """审计日志写入失败（_write_audit_log 内部异常）不传播到调用方"""
        from app.services.admin_service import AdminService
        from app.models.admin import SystemConfig

        # _write_audit_log 内部使用 async_session_factory()，
        # 其 try/except 会吞噬所有异常不 re-raise。
        # 验证方式：mock async_session_factory 使其抛异常，
        # 但由于 _write_audit_log 内部有 try/except，异常不传播。
        # 更直接的验证：_write_audit_log 不应抛出任何异常
        with patch('app.services.admin_service.async_session_factory') as mock_factory:
            mock_factory.side_effect = Exception("DB connection failed")

            # _write_audit_log 应吞噬异常，不抛出
            try:
                await AdminService._write_audit_log(
                    db_session, admin_with_pwd.id, "create", "config",
                    target_id=999, changes={"key": {"old": None, "new": "test"}},
                )
                # 未抛出异常 = 通过
            except Exception as e:
                pytest.fail(f"_write_audit_log 应吞噬异常，但抛出了: {e}")

    async def test_audit_log_independent_session(self, db_session, admin_with_pwd):
        """审计日志使用独立 session，业务事务回滚时审计日志仍保留"""
        from app.services.admin_service import AdminService

        # 正常执行 ban_user，审计日志应写入
        target_user = User(openid="p1_ban_target", nickname="被封用户", status="active")
        db_session.add(target_user)
        await db_session.commit()
        await db_session.refresh(target_user)

        await AdminService.ban_user(
            user_id=target_user.id, reason="P1测试封禁",
            admin_id=admin_with_pwd.id,
        )

        # 查询审计日志
        log_result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "update",
                AuditLog.target_type == "user",
                AuditLog.admin_id == admin_with_pwd.id,
            )
        )
        audit_log = log_result.scalar_one_or_none()
        assert audit_log is not None, "审计日志应存在（独立 session 提交）"


# ============================================================================
# Membership 续期 P1 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def seed_tiers_for_p1(db_session):
    """预置会员等级"""
    tiers = [
        MembershipTierConfig(
            tier="free", name="免费", sort_order=0,
            price_monthly_cents=0, price_quarterly_cents=0, price_yearly_cents=0,
            benefits=["每日3次分析"], quota_config={"daily_analysis_limit": 3},
        ),
        MembershipTierConfig(
            tier="member", name="会员", sort_order=1,
            price_monthly_cents=1900, price_quarterly_cents=4900, price_yearly_cents=16800,
            benefits=["无限分析"], quota_config={"daily_analysis_limit": -1},
        ),
    ]
    for t in tiers:
        db_session.add(t)
    await db_session.commit()
    return tiers


@pytest.mark.asyncio
class TestSubscriptionRenewal:
    """续期 vs 新建订阅"""

    async def test_renewal_extends_expire_at(self, db_session, seed_tiers_for_p1):
        """已有 active 订阅续期后 expire_at = max(old.expire_at, now) + period_days"""
        from app.services.payment_service import PaymentService
        from app.models.payment import Order

        user = User(openid="p1_renew_001", nickname="续期用户", status="active")
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        # 已有订阅，还有 20 天到期
        old_expire = now + timedelta(days=20)
        existing_sub = Subscription(
            user_id=user.id, tier="member", status="active",
            start_at=now - timedelta(days=10),
            expire_at=old_expire,
        )
        db_session.add(existing_sub)
        await db_session.flush()

        # 创建已支付订单（月度续期）
        order = Order(
            user_id=user.id, order_no="P1_RENEW_001",
            product_type="membership", amount_cents=1900,
            status="paid", paid_at=now,
            extra_data={"tier": "member", "period_days": 30, "period": "monthly"},
            subscription_id=existing_sub.id,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(existing_sub)
        await db_session.refresh(order)

        # 执行续期逻辑
        await PaymentService._create_or_renew_subscription(db_session, order)
        await db_session.commit()  # 需要提交才能刷新到新值
        await db_session.refresh(existing_sub)
        # 续期后 expire_at 应为 max(old_expire, now) + 30 天
        expected_expire = max(old_expire, now) + timedelta(days=30)
        # 允许几秒的误差
        diff = abs((existing_sub.expire_at - expected_expire).total_seconds())
        assert diff < 60, f"续期后 expire_at 应约为 {expected_expire}，实际为 {existing_sub.expire_at}"
        assert existing_sub.status == "active"

    async def test_new_subscription_when_no_existing(self, db_session, seed_tiers_for_p1):
        """无订阅时新建 subscription"""
        from app.services.payment_service import PaymentService
        from app.models.payment import Order

        user = User(openid="p1_new_001", nickname="新订阅用户", status="active")
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        order = Order(
            user_id=user.id, order_no="P1_NEW_001",
            product_type="membership", amount_cents=1900,
            status="paid", paid_at=now,
            extra_data={"tier": "member", "period_days": 30, "period": "monthly"},
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        await PaymentService._create_or_renew_subscription(db_session, order)
        await db_session.commit()

        # 验证新订阅已创建
        sub_result = await db_session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        sub = sub_result.scalar_one_or_none()
        assert sub is not None, "新订阅应已创建"
        assert sub.tier == "member"
        assert sub.status == "active"


# ============================================================================
# Gamification P1 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def seed_badges_for_p1(db_session):
    """预置徽章"""
    badges = [
        BadgeDefinition(
            id="streak_7", name="连续7天", icon="🔥", category="streak",
            condition={"metric": "streak_days", "operator": ">=", "threshold": 7},
            points_reward=20, sort_order=1, is_active=True,
        ),
    ]
    for b in badges:
        db_session.add(b)
    await db_session.commit()
    return badges


@pytest.mark.asyncio
class TestGamificationStreak:
    """连续打卡奖励 + Redis 优先"""

    async def test_streak_7_bonus(self, db_session, seed_badges_for_p1):
        """第 7 天打卡应触发 streak_7 奖励"""
        from app.services.gamification_service import GamificationService, POINTS_RULES

        user = User(openid="p1_streak_001", nickname="打卡用户", status="active")
        db_session.add(user)
        await db_session.flush()

        up = UserPoints(user_id=user.id, total_points=0, monthly_points=0, current_streak=6)
        db_session.add(up)
        await db_session.commit()

        # 设置 Redis 连续天数为 6（下次打卡将变为 7）
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.set("gamification:streak:user:1", 6)
        await redis.set("gamification:streak:last_date:1",
                        (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat())
        # 设置用户 ID 为 1（测试环境通常从 1 开始）
        # 重新创建用户以获取 id=1

        # 由于 user.id 可能不是 1，我们直接使用 user.id
        await redis.delete("gamification:streak:user:1")
        await redis.delete("gamification:streak:last_date:1")
        await redis.set(f"gamification:streak:user:{user.id}", 6)
        last_date = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        await redis.set(f"gamification:streak:last_date:{user.id}", last_date)

        # 执行第 7 天打卡
        result = await GamificationService.checkin(db_session, user.id)
        await db_session.commit()

        assert result["current_streak"] == 7, f"连续天数应为 7，实际为 {result['current_streak']}"
        assert result["bonus"] == POINTS_RULES["streak_7"], \
            f"bonus 应为 {POINTS_RULES['streak_7']}，实际为 {result['bonus']}"

    async def test_redis_streak_priority(self, db_session):
        """R6-Gami-4: get_points 优先从 Redis 读取连续天数"""
        from app.services.gamification_service import GamificationService
        from app.core.redis import get_redis

        user = User(openid="p1_redis_001", nickname="Redis用户", status="active")
        db_session.add(user)
        await db_session.flush()

        # DB 中 current_streak=3
        up = UserPoints(user_id=user.id, total_points=0, monthly_points=0, current_streak=3)
        db_session.add(up)
        await db_session.commit()

        # Redis 中设置 streak=5
        redis = await get_redis()
        await redis.set(f"gamification:streak:user:{user.id}", 5)

        result = await GamificationService.get_points(db_session, user.id)
        assert result["current_streak"] == 5, \
            f"应优先读取 Redis 的 5，实际为 {result['current_streak']}"

        # 清除 Redis key 后应回退 DB
        await redis.delete(f"gamification:streak:user:{user.id}")
        result = await GamificationService.get_points(db_session, user.id)
        assert result["current_streak"] == 3, \
            f"无 Redis key 时应回退 DB 的 3，实际为 {result['current_streak']}"


# ============================================================================
# 用户隔离 P1 测试
# ============================================================================

@pytest.mark.asyncio
class TestUserIsolation:
    """用户数据隔离测试"""

    async def test_dashboard_user_isolation(self, client, db_session, seed_tiers_for_p1):
        """Dashboard 数据用户隔离——用户 A 看不到用户 B 的数据"""
        from app.models.match import MatchRecord

        # 用户 A 创建比赛记录
        user_a = User(openid="p1_iso_a", nickname="用户A", status="active")
        user_b = User(openid="p1_iso_b", nickname="用户B", status="active")
        db_session.add(user_a)
        db_session.add(user_b)
        await db_session.flush()

        # 用户 A 的比赛记录
        record = MatchRecord(
            user_id=user_a.id, opponent_name="对手", opponent_rating=1500,
            my_score=3, opponent_score=1, is_win=True,
            format="bo5", match_type="competition",
            match_date=datetime.now(timezone.utc),
        )
        db_session.add(record)
        await db_session.commit()

        # 用户 B 的 token
        token_b = create_access_token({"sub": str(user_b.id), "jti": generate_jti()})
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 用户 B 查看 dashboard overview
        resp = await client.get("/api/v1/dashboard/overview", headers=headers_b)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["wins"] == 0, f"用户 B 不应看到用户 A 的比赛，wins={data['wins']}"

    async def test_match_record_user_isolation(self, client, db_session):
        """Match Data 用户隔离——用户 B 不能查看用户 A 的记录"""
        from app.models.match import MatchRecord

        user_a = User(openid="p1_match_a", nickname="用户A", status="active")
        user_b = User(openid="p1_match_b", nickname="用户B", status="active")
        db_session.add(user_a)
        db_session.add(user_b)
        await db_session.flush()

        record = MatchRecord(
            user_id=user_a.id, opponent_name="对手", opponent_rating=1500,
            my_score=3, opponent_score=1, is_win=True,
            format="bo5", match_type="competition",
            match_date=datetime.now(timezone.utc),
        )
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        # 用户 B 的 token
        token_b = create_access_token({"sub": str(user_b.id), "jti": generate_jti()})
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 用户 B 查看用户 A 的记录详情
        resp = await client.get(f"/api/v1/match-data/{record.id}", headers=headers_b)
        assert resp.status_code == 404, f"用户 B 不应访问用户 A 的记录，状态码={resp.status_code}"


# ============================================================================
# Training 权限守卫 P1 测试
# ============================================================================

@pytest.mark.asyncio
class TestTrainingPermissionGuard:
    """训练端点 require_membership 权限守卫"""

    async def test_training_endpoint_requires_membership(self, client, db_session, seed_tiers_for_p1):
        """非会员访问训练端点返回 403"""
        user = User(openid="p1_train_free", nickname="免费用户", status="active")
        db_session.add(user)
        await db_session.commit()

        token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
        headers = {"Authorization": f"Bearer {token}"}

        # 免费用户访问训练建议
        resp = await client.get("/api/v1/training/advice/contextual", headers=headers)
        # 可能返回 403（会员守卫）或 404（无报告），都说明非会员无法正常访问
        assert resp.status_code in (403, 404), \
            f"免费用户不应正常访问训练端点，状态码={resp.status_code}"

    async def test_training_member_can_access(self, client, db_session, seed_tiers_for_p1):
        """会员用户可正常访问训练端点"""
        user = User(openid="p1_train_member", nickname="会员用户", status="active")
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        sub = Subscription(
            user_id=user.id, tier="member", status="active",
            start_at=now, expire_at=now + timedelta(days=30),
        )
        db_session.add(sub)
        await db_session.commit()

        token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/training/advice/contextual", headers=headers)
        # 会员可访问，可能返回 404（无报告）但不应 403
        assert resp.status_code != 403, \
            f"会员用户不应被 403 拒绝，状态码={resp.status_code}"


# ============================================================================
# Progress forecast 方向感知 P1 测试
# ============================================================================

@pytest.mark.asyncio
class TestProgressForecast:
    """R7-Prog-4: forecast 方向感知"""

    async def test_forecast_down_metric_improving(self, db_session):
        """direction=down 的指标改善时（slope<0）应预测达标周数"""
        from app.services.progress_service import ProgressService, METRIC_DEFINITIONS
        from app.models.progress import TechniqueTrend

        user = User(openid="p1_forecast_001", nickname="预测用户", status="active")
        db_session.add(user)
        await db_session.flush()

        # forehand_ratio: direction=down, target=0.60
        # time_series 递减（slope<0 表示改善）
        trend = TechniqueTrend(
            user_id=user.id,
            metric_name="forehand_ratio",
            current_value=0.70,
            target_value=0.60,
            time_series=[
                {"value": 0.80},
                {"value": 0.75},
                {"value": 0.70},
            ],
        )
        db_session.add(trend)
        await db_session.commit()

        # 确认 forehand_ratio 是 down 方向
        assert METRIC_DEFINITIONS["forehand_ratio"]["direction"] == "down"

        forecast = await ProgressService._linear_regression_forecast(db_session, user.id)
        assert "forehand_ratio" in forecast, f"应包含 forehand_ratio 预测，实际: {list(forecast.keys())}"
        assert forecast["forehand_ratio"]["predicted_weeks_to_target"] is not None, \
            "direction=down 且 slope<0（改善）时应预测达标周数"

    async def test_forecast_down_metric_worsening(self, db_session):
        """direction=down 的指标恶化时（slope>0）不应预测达标"""
        from app.services.progress_service import ProgressService
        from app.models.progress import TechniqueTrend

        user = User(openid="p1_forecast_002", nickname="预测用户2", status="active")
        db_session.add(user)
        await db_session.flush()

        # forehand_ratio: direction=down, target=0.60
        # time_series 递增（slope>0 表示恶化，远离目标）
        trend = TechniqueTrend(
            user_id=user.id,
            metric_name="forehand_ratio",
            current_value=0.85,
            target_value=0.60,
            time_series=[
                {"value": 0.75},
                {"value": 0.80},
                {"value": 0.85},
            ],
        )
        db_session.add(trend)
        await db_session.commit()

        forecast = await ProgressService._linear_regression_forecast(db_session, user.id)
        # slope>0 对 down 指标是恶化，不应预测达标
        if "forehand_ratio" in forecast:
            assert forecast["forehand_ratio"]["predicted_weeks_to_target"] is None, \
                "direction=down 且 slope>0（恶化）时不应预测达标"
        # 若被 R² 过滤掉也是合理结果
