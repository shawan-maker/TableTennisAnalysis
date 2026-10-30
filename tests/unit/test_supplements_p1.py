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
        # R12-MatchData-D1: URL 补 /records 段 — 原先缺段命中不存在的路由，
        # 404 由路由层返回（假阳性），未真正走到属主校验
        resp = await client.get(f"/api/v1/match-data/records/{record.id}", headers=headers_b)
        assert resp.status_code == 404, f"用户 B 不应访问用户 A 的记录，状态码={resp.status_code}"
        assert resp.json()["code"] == 40413  # ERR_RECORD_NOT_FOUND（属主校验 404）


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

        # R12-Training-D1: 改用带 require_membership 守卫的 /templates 端点 —
        # 原先用的 /advice/contextual 无会员守卫，404（无报告）掩盖了假阳性
        resp = await client.get("/api/v1/training/templates", headers=headers)
        assert resp.status_code == 403, \
            f"免费用户应被会员守卫 403 拒绝，状态码={resp.status_code}"

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

        # 与 403 测试同一守卫端点：会员应 200（空模板列表也算正常访问）
        resp = await client.get("/api/v1/training/templates", headers=headers)
        assert resp.status_code == 200, \
            f"会员用户应正常访问模板列表，状态码={resp.status_code}"


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


# ============================================================================
# R12-Admin-1: 禁用管理员权限绕过修复测试
# ============================================================================

@pytest.mark.asyncio
class TestAdminSessionIsActiveCheck:
    """R12-Admin-1: get_admin_session 每请求校验 is_active"""

    async def test_disabled_admin_session_revoked(self, client, db_session, admin_with_pwd):
        """管理员被禁用后旧 session 立即失效 → 403，且 session 被清除"""
        from app.services.admin_service import AdminService

        # 1. 正常登录获取 session
        data = await AdminService.login("p1_admin", "Admin@123")
        token = data.session_token
        headers = {"Authorization": f"Bearer {token}"}

        # 登录后正常访问（基线验证）
        resp0 = await client.get("/api/v1/admin/configs", headers=headers)
        assert resp0.status_code == 200, f"禁用前应正常访问，状态码={resp0.status_code}"

        # 2. 禁用管理员（不删除 Redis session —— 模拟管理后台直接改 DB）
        admin_with_pwd.is_active = False
        db_session.add(admin_with_pwd)
        await db_session.commit()

        # 3. 旧 session 访问 → 403（禁用立即生效，无需等待 30min TTL 过期）
        resp1 = await client.get("/api/v1/admin/configs", headers=headers)
        assert resp1.status_code == 403, \
            f"禁用管理员旧 session 应返回 403，实际={resp1.status_code}"

        # 4. session 应已被清除 → 再次访问 401
        resp2 = await client.get("/api/v1/admin/configs", headers=headers)
        assert resp2.status_code == 401, \
            f"session 清除后应返回 401，实际={resp2.status_code}"

    async def test_active_admin_session_works(self, client, db_session, admin_with_pwd):
        """活跃管理员 session 正常通过（回归保护）"""
        from app.services.admin_service import AdminService

        data = await AdminService.login("p1_admin", "Admin@123")
        headers = {"Authorization": f"Bearer {data.session_token}"}

        resp = await client.get("/api/v1/admin/configs", headers=headers)
        assert resp.status_code == 200


# ============================================================================
# R12-Auth-2: wechat_login 封禁用户拦截 + Auth-7 wechat-login 覆盖缺口
# ============================================================================

@pytest.mark.asyncio
class TestWechatLoginBanned:
    """R12-Auth-2: wechat_login 登录入口拦截 banned 用户"""

    def _mock_wx(self, openid):
        """构造 code2session mock 返回指定 openid"""
        mock = AsyncMock()
        mock.return_value = {"openid": openid, "session_key": "sk_test"}
        return mock

    async def test_wechat_login_banned_rejected(self, client, db_session):
        """banned 用户通过 wechat-login 登录 → 403"""
        from app.services.auth_service import AuthService

        # 1. 创建 banned 用户
        user = User(openid="wx_banned_openid", nickname="封禁用户", status="banned")
        db_session.add(user)
        await db_session.commit()

        # 2. mock code2session 返回该用户 openid
        with patch.object(
            AuthService, "_call_wechat_code2session", new=self._mock_wx("wx_banned_openid")
        ):
            resp = await client.post(
                "/api/v1/auth/wechat-login",
                json={"code": "mock_code"},
            )

        assert resp.status_code == 403, \
            f"banned 用户微信登录应返回 403，实际={resp.status_code}"

    async def test_wechat_login_new_user_success(self, client, db_session):
        """Auth-7 缺口补充：新用户微信登录成功 → 200 + token"""
        from app.services.auth_service import AuthService

        with patch.object(
            AuthService, "_call_wechat_code2session", new=self._mock_wx("wx_new_openid_001")
        ):
            resp = await client.post(
                "/api/v1/auth/wechat-login",
                json={"code": "mock_code", "nickname": "新球友"},
            )

        assert resp.status_code == 200, f"新用户微信登录应成功，实际={resp.status_code}"
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["user"]["nickname"] == "新球友"
        # 新用户需同意隐私政策
        assert data["requires_consent"] is True

    async def test_wechat_login_existing_user_no_recreate(self, client, db_session):
        """已有活跃用户重复微信登录不重复建号"""
        from app.services.auth_service import AuthService

        user = User(openid="wx_existing_openid", nickname="老用户", status="active")
        db_session.add(user)
        await db_session.commit()
        uid = user.id

        with patch.object(
            AuthService, "_call_wechat_code2session", new=self._mock_wx("wx_existing_openid")
        ):
            resp = await client.post(
                "/api/v1/auth/wechat-login",
                json={"code": "mock_code"},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["user"]["id"] == uid


# ============================================================================
# R12-Payment-1: 续期订单退款撤销权益修复测试
# ============================================================================

@pytest.mark.asyncio
class TestRenewalOrderSubscriptionId:
    """R12-Payment-1: 续期分支回填 order.subscription_id"""

    async def test_renewal_backfills_subscription_id(self, db_session):
        """续期订单回填 subscription_id → 退款时可撤销权益"""
        from app.services.payment_service import PaymentService
        from app.models.payment import Order
        from app.models.membership import Subscription

        user = User(openid="p1_renew_user", nickname="续费用户", status="active")
        db_session.add(user)
        await db_session.flush()

        # 既有活跃订阅（10 天后到期）
        now = datetime.now(timezone.utc)
        sub = Subscription(
            user_id=user.id, tier="member", status="active",
            start_at=now - timedelta(days=20),
            expire_at=now + timedelta(days=10),
        )
        db_session.add(sub)
        await db_session.flush()

        # 续期订单
        order = Order(
            user_id=user.id,
            order_no="PP20260101RENEW01",
            product_type="membership", amount_cents=1900,
            status="paid", paid_at=now,
            extra_data={"tier": "member", "period_days": 30, "period": "monthly"},
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        await db_session.refresh(sub)

        assert order.subscription_id is None  # 前置：续期订单初始未关联

        # 执行续期
        await PaymentService._create_or_renew_subscription(db_session, order)

        # R12-Payment-1 核心断言：续期分支回填 subscription_id
        assert order.subscription_id == sub.id, \
            "续期订单必须回填 subscription_id，否则退款无法撤销权益"
        # 订阅到期时间延长 30 天（从原到期日起算）
        await db_session.flush()  # _create_or_renew_subscription 仅改内存，需 flush 后 refresh 才能从 DB 读回
        await db_session.refresh(sub)
        expected_expire = (now + timedelta(days=10)) + timedelta(days=30)
        assert abs((sub.expire_at - expected_expire).total_seconds()) < 60, \
            "续期应从原到期时间顺延，而非从当前时间起算"

    async def test_first_purchase_sets_subscription_id(self, db_session):
        """回归保护：首次购买仍正常回填"""
        from app.services.payment_service import PaymentService
        from app.models.payment import Order

        user = User(openid="p1_firstbuy_user", nickname="首购用户", status="active")
        db_session.add(user)
        await db_session.flush()

        order = Order(
            user_id=user.id,
            order_no="PP20260101FIRST01",
            product_type="membership", amount_cents=1900,
            status="paid", paid_at=datetime.now(timezone.utc),
            extra_data={"tier": "member", "period_days": 30, "period": "monthly"},
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        await PaymentService._create_or_renew_subscription(db_session, order)

        assert order.subscription_id is not None, "首购订单应回填新建订阅 ID"


# ============================================================================
# R12-Membership-1: get_quota expired 误报无限额度修复测试
# ============================================================================

@pytest.mark.asyncio
class TestQuotaExpiredMembership:
    """R12-Membership-1: expired 订阅按免费 3 次/日计算额度"""

    async def test_expired_member_quota_is_free_limit(self, db_session):
        """expired 订阅（tier=member）的 get_quota 应返回免费 3 次/日，而非 -1 无限"""
        from app.services.membership_service import MembershipService

        user = User(openid="p1_quota_expired", nickname="过期会员", status="active")
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        sub = Subscription(
            user_id=user.id, tier="member", status="expired",
            start_at=now - timedelta(days=40),
            expire_at=now - timedelta(days=5),  # 已过期 5 天
        )
        db_session.add(sub)
        await db_session.commit()

        quota = await MembershipService.get_quota(db_session, user.id)

        # R12-Membership-1 核心断言：expired 会员不享受无限额度
        assert quota.tier == "free" or quota.daily_limit == 3, \
            f"expired 会员应按免费额度处理，实际 tier={quota.tier} limit={quota.daily_limit}"
        assert quota.daily_limit != -1, \
            f"expired 会员不应返回 -1 无限额度，实际={quota.daily_limit}"

    async def test_active_member_quota_unlimited(self, db_session):
        """回归保护：active 会员仍返回无限额度"""
        from app.services.membership_service import MembershipService

        user = User(openid="p1_quota_active", nickname="活跃会员", status="active")
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        sub = Subscription(
            user_id=user.id, tier="member", status="active",
            start_at=now - timedelta(days=5),
            expire_at=now + timedelta(days=25),
        )
        db_session.add(sub)
        await db_session.commit()

        quota = await MembershipService.get_quota(db_session, user.id)
        assert quota.daily_limit == -1, "active 会员应保持无限额度"


# ============================================================================
# R12-VA-2: 任务状态机校验修复测试
# ============================================================================

@pytest.mark.asyncio
class TestTaskStateMachine:
    """R12-VA-2: TASK_TRANSITIONS 矩阵校验"""

    async def _create_task(self, db_session, status="queued"):
        """创建指定状态的 VideoTask（含真实 FileRecord 满足 FK 约束）"""
        from app.models.video_analysis import VideoTask, FileRecord

        user = User(openid=f"p1_task_{status}_{id(db_session) % 10000}", nickname="任务用户", status="active")
        db_session.add(user)
        await db_session.flush()

        file_record = FileRecord(
            user_id=user.id,
            oss_key=f"videos/test/file_{user.id}.mp4",
            file_size=1048576,  # 1MB（满足 ck_file_size_range 下限）
            file_type="mp4",
            status="uploaded",
        )
        db_session.add(file_record)
        await db_session.flush()

        task = VideoTask(
            task_uuid=f"uuid-{status}-{user.id}",
            user_id=user.id, file_id=file_record.id,
            oss_key=f"videos/test/file_{user.id}.mp4",
            status=status, total_steps=10,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)
        return task

    async def test_valid_transition_queued_to_processing(self, db_session):
        """合法转换 queued → processing"""
        from app.ai_pipeline.progress import transition_task_status

        task = await self._create_task(db_session, "queued")
        assert await transition_task_status(db_session, task.id, "processing") is True
        assert task.status == "processing"

    async def test_valid_chain_queued_processing_completed(self, db_session):
        """合法链 queued → processing → completed"""
        from app.ai_pipeline.progress import transition_task_status

        task = await self._create_task(db_session, "queued")
        assert await transition_task_status(db_session, task.id, "processing") is True
        assert await transition_task_status(db_session, task.id, "completed") is True
        assert task.status == "completed"
        assert task.completed_at is not None

    async def test_invalid_completed_to_failed(self, db_session):
        """非法转换 completed → failed 被拒绝（终态不可翻转）"""
        from app.ai_pipeline.progress import transition_task_status

        task = await self._create_task(db_session, "completed")
        assert await transition_task_status(db_session, task.id, "failed") is False
        assert task.status == "completed", "终态 completed 不应被改写为 failed"

    async def test_invalid_cancelled_to_processing(self, db_session):
        """非法转换 cancelled → processing 被拒绝"""
        from app.ai_pipeline.progress import transition_task_status

        task = await self._create_task(db_session, "cancelled")
        assert await transition_task_status(db_session, task.id, "processing") is False
        assert task.status == "cancelled", "终态 cancelled 不应被改写"

    async def test_invalid_queued_to_completed(self, db_session):
        """非法转换 queued → completed 被拒绝（必须先 processing）"""
        from app.ai_pipeline.progress import transition_task_status

        task = await self._create_task(db_session, "queued")
        assert await transition_task_status(db_session, task.id, "completed") is False
        assert task.status == "queued"

    async def test_failed_can_retry_to_queued(self, db_session):
        """failed → queued 合法（可重试）"""
        from app.ai_pipeline.progress import transition_task_status

        task = await self._create_task(db_session, "failed")
        assert await transition_task_status(db_session, task.id, "queued") is True
        assert task.status == "queued"

    async def test_nonexistent_task_returns_false(self, db_session):
        """不存在的任务返回 False 不抛异常"""
        from app.ai_pipeline.progress import transition_task_status

        assert await transition_task_status(db_session, 999999, "processing") is False


# ============================================================================
# R12-SC-1: 多局赛制推进修复测试
# ============================================================================

@pytest.mark.asyncio
class TestMultiGameProgression:
    """R12-SC-1: bo3/bo5/bo7 达赛制局数自动结束，局间推进正确"""

    async def _create_bo3_match(self, client, headers):
        """创建并开始 bo3 比赛"""
        resp = await client.post(
            "/api/v1/scoring/matches",
            headers=headers,
            json={"opponent_name": "多局对手", "format": "bo3", "target_score": 11},
        )
        assert resp.status_code == 200
        match_id = resp.json()["data"]["match_id"]
        resp = await client.post(f"/api/v1/scoring/matches/{match_id}/start", headers=headers)
        assert resp.status_code == 200
        return match_id

    async def test_bo3_first_game_advances_to_game2(self, client, auth_headers):
        """bo3 赢下第一局 → current_game=2、当前局比分清零"""
        match_id = await self._create_bo3_match(client, auth_headers)

        # 第一局 11:0（11 分即胜，差≥2）
        data = None
        for _ in range(11):
            resp = await client.post(
                f"/api/v1/scoring/matches/{match_id}/score",
                headers=auth_headers,
                json={"scorer": "user", "score_method": "rally_point"},
            )
            assert resp.status_code == 200
            data = resp.json()["data"]

        # R12-SC-1 核心断言：局推进
        assert data["game_number"] == 2, f"赢下第一局后应推进到第 2 局，实际={data['game_number']}"
        assert data["score"] == "0:0", f"新一局比分应清零，实际={data['score']}"
        assert data["match_finished"] is False, "bo3 赢 1 局（需 2 局）不应结束全场"

        # 比赛详情确认局分已累计
        resp = await client.get(f"/api/v1/scoring/matches/{match_id}", headers=auth_headers)
        detail = resp.json()["data"]
        assert detail["current_game"] == 2

    async def test_bo3_two_games_wins_auto_finish(self, client, auth_headers, db_session):
        """bo3 连赢 2 局 → 全场自动结束（status=finished、final_score=2:0、is_win=True）"""
        from app.models.match import Match
        from sqlalchemy import select as sa_select

        match_id = await self._create_bo3_match(client, auth_headers)

        # 第一局 11:0
        for _ in range(11):
            resp = await client.post(
                f"/api/v1/scoring/matches/{match_id}/score",
                headers=auth_headers,
                json={"scorer": "user", "score_method": "rally_point"},
            )
            assert resp.status_code == 200

        # 第二局 11:0 → 达 2 局 → 自动结束
        last_data = None
        for _ in range(11):
            resp = await client.post(
                f"/api/v1/scoring/matches/{match_id}/score",
                headers=auth_headers,
                json={"scorer": "user", "score_method": "rally_point"},
            )
            assert resp.status_code == 200
            last_data = resp.json()["data"]

        # R12-SC-1 核心断言：自动结束
        assert last_data["match_finished"] is True, "bo3 连赢 2 局应自动结束全场"
        assert last_data["match_status"] == "finished"

        # DB 验证：局分判定 + 最终比分
        result = await db_session.execute(sa_select(Match).where(Match.id == match_id))
        match = result.scalar_one()
        assert match.status == "finished"
        assert match.is_win is True
        assert match.final_score == "2:0", f"final_score 应为局分 2:0，实际={match.final_score}"
        assert match.games_won_user == 2
        assert match.games_won_opp == 0

    async def test_cross_game_undo_rejected(self, client, auth_headers):
        """局结束后撤销致胜球 → 400（局分已记录不可跨局撤销）"""
        match_id = await self._create_bo3_match(client, auth_headers)

        # 赢下第一局（11:0）→ 推进到第 2 局
        for _ in range(11):
            resp = await client.post(
                f"/api/v1/scoring/matches/{match_id}/score",
                headers=auth_headers,
                json={"scorer": "user", "score_method": "rally_point"},
            )
            assert resp.status_code == 200

        # 撤销最后一球（第一局致胜球）→ 应被拒绝
        resp = await client.post(
            f"/api/v1/scoring/matches/{match_id}/undo", headers=auth_headers
        )
        assert resp.status_code == 400, \
            f"跨局撤销应返回 400，实际={resp.status_code} {resp.text}"

    async def test_bo1_single_game_auto_finish(self, client, auth_headers, db_session):
        """bo1 单局结束即全场结束（回归保护 bo1 行为）"""
        from app.models.match import Match
        from sqlalchemy import select as sa_select

        resp = await client.post(
            "/api/v1/scoring/matches",
            headers=auth_headers,
            json={"opponent_name": "单局对手", "format": "bo1", "target_score": 11},
        )
        match_id = resp.json()["data"]["match_id"]
        await client.post(f"/api/v1/scoring/matches/{match_id}/start", headers=auth_headers)

        last_data = None
        for _ in range(11):
            resp = await client.post(
                f"/api/v1/scoring/matches/{match_id}/score",
                headers=auth_headers,
                json={"scorer": "user", "score_method": "rally_point"},
            )
            assert resp.status_code == 200
            last_data = resp.json()["data"]

        # bo1：1 局即全场结束
        assert last_data["match_finished"] is True, "bo1 赢 1 局应结束全场"
        assert last_data["match_status"] == "finished"

        result = await db_session.execute(sa_select(Match).where(Match.id == match_id))
        match = result.scalar_one()
        assert match.status == "finished"
        # bo1 局分 1:0（games_won 计 1，final_score 取局分）
        assert match.final_score == "1:0"
        assert match.is_win is True


# ============================================================================
# R12-Prog-2: resolved 趋势类型
# ============================================================================

@pytest.mark.asyncio
class TestTrendResolved:
    """R12-Prog-2: current=None 时趋势判定 — 历史有值→resolved，无历史→new"""

    async def test_resolved_when_history_exists(self, db_session):
        from app.services.progress_service import ProgressService

        result = ProgressService._calculate_trend(
            1, "backhand_ratio", None, [0.2, 0.25], 0.35
        )
        assert result["trend"] == "resolved"
        assert result["persistence_count"] == 0

    async def test_new_when_no_history(self, db_session):
        from app.services.progress_service import ProgressService

        result = ProgressService._calculate_trend(
            1, "backhand_ratio", None, [], 0.35
        )
        assert result["trend"] == "new"

    async def test_normal_value_trend_unchanged(self, db_session):
        """回归：current 非 None 的正常判定路径不受影响"""
        from app.services.progress_service import ProgressService

        result = ProgressService._calculate_trend(
            1, "backhand_ratio", 0.25, [0.2, 0.22], 0.35
        )
        assert result["trend"] == "improving"

    async def test_update_trends_persists_resolved(self, db_session):
        """集成：指标消失后落库 resolved 且 change_rate=None（原 None-float TypeError）"""
        from app.models.video_analysis import AnalysisReport, VideoTask, FileRecord
        from app.models.progress import TechniqueTrend
        from app.services.progress_service import ProgressService
        from sqlalchemy import and_

        user = User(openid="p1_resolved_001", nickname="趋势用户", status="active")
        db_session.add(user)
        await db_session.flush()

        async def _report(idx, result_data):
            file_record = FileRecord(
                user_id=user.id, oss_key=f"resolved/{user.id}/{idx}",
                file_size=1048576, file_type="mp4", status="uploaded",
            )
            db_session.add(file_record)
            await db_session.flush()
            task = VideoTask(
                user_id=user.id, file_id=file_record.id,
                oss_key=f"resolved/{user.id}/{idx}",
                status="completed", task_uuid=f"resolved-{user.id}-{idx}", progress=100,
            )
            db_session.add(task)
            await db_session.flush()
            report = AnalysisReport(
                task_id=task.id, user_id=user.id, result_data=result_data,
                report_text={"summary": f"报告{idx}", "issues": [], "suggestions": []},
                is_llm_generated=False,
            )
            db_session.add(report)
            await db_session.flush()
            return report

        # 快照 1/2：反手比率 0.20 / 0.25；快照 3：反手比率消失（None）
        r1 = await _report(1, {"technique_stats": {"backhand_ratio": 0.20, "forehand_ratio": 0.5}})
        r2 = await _report(2, {"technique_stats": {"backhand_ratio": 0.25, "forehand_ratio": 0.5}})
        r3 = await _report(3, {"technique_stats": {"forehand_ratio": 0.6}})
        await db_session.commit()

        await ProgressService.generate_snapshot(user.id, r1.id, r1.result_data)
        await ProgressService.generate_snapshot(user.id, r2.id, r2.result_data)
        await ProgressService.generate_snapshot(user.id, r3.id, r3.result_data)

        tt = await db_session.scalar(
            select(TechniqueTrend).where(
                and_(
                    TechniqueTrend.user_id == user.id,
                    TechniqueTrend.metric_name == "backhand_ratio",
                )
            )
        )
        assert tt is not None
        assert tt.trend == "resolved"
        assert tt.current_value is None
        assert tt.change_rate is None


# ============================================================================
# R12-KB-2: severity 取自 diagnosis JSONB
# ============================================================================

@pytest.mark.asyncio
class TestKnowledgeSeveritySource:
    """R12-KB-2: 规则引擎 severity 取自 diagnosis JSONB，而非 condition"""

    async def _add_rule(self, db, rule_id, diagnosis, condition_extra=None):
        from app.models.knowledge_base import RuleDefinition

        cond = {"metric": "backhand_ratio", "operator": "<", "threshold": 0.30}
        if condition_extra:
            cond.update(condition_extra)
        rule = RuleDefinition(
            rule_id=rule_id, rule_name=f"规则{rule_id}", rule_type="single",
            condition=cond, diagnosis=diagnosis,
            training_methods=None, training_plan_template=None,
            adjustment_action="adjust", is_active=True,
        )
        db.add(rule)
        await db.flush()
        return rule

    async def test_severity_from_diagnosis_not_condition(self, db_session):
        from app.services.knowledge_base_service import KnowledgeBaseService

        # condition 声明 severity=low，diagnosis 声明 severity=high → 应取 high
        await self._add_rule(
            db_session, "RULE_SEV_HIGH",
            diagnosis={"problem_id": "P_SEV", "problem_name": "测试",
                       "severity": "high", "suggestion_template": "模板"},
            condition_extra={"severity": "low"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"backhand_ratio": 0.2}, "trends": {}}
        )
        assert len(results) == 1
        assert results[0]["severity"] == "high"

    async def test_severity_default_medium_without_diagnosis_key(self, db_session):
        from app.services.knowledge_base_service import KnowledgeBaseService

        await self._add_rule(
            db_session, "RULE_SEV_MED",
            diagnosis={"problem_id": "P_SEV2", "problem_name": "测试2",
                       "suggestion_template": "模板"},
            condition_extra={"severity": "low"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"backhand_ratio": 0.2}, "trends": {}}
        )
        assert len(results) == 1
        assert results[0]["severity"] == "medium"


# ============================================================================
# R12-Admin-2: create_category 重复检查
# ============================================================================

@pytest.mark.asyncio
class TestAdminCreateCategoryConflict:
    """R12-Admin-2: 重复 name/code 创建分类返回 409（原 IntegrityError 500）"""

    @pytest_asyncio.fixture(scope="function")
    async def kb_admin_headers(self, db_session):
        """知识库 admin 端点认证（AdminUser session 体系，非 User JWT）"""
        from app.services.admin_service import AdminService

        admin = AdminUser(
            username="p1_kb_admin",
            password_hash=pwd_context.hash("Admin@123"),
            role="super_admin",
            is_active=True,
        )
        db_session.add(admin)
        await db_session.commit()
        data = await AdminService.login("p1_kb_admin", "Admin@123")
        return {"Authorization": f"Bearer {data.session_token}"}

    async def _create(self, client, kb_admin_headers, name, code):
        return await client.post(
            "/api/v1/admin/knowledge/categories",
            json={"name": name, "code": code},
            headers=kb_admin_headers,
        )

    async def test_duplicate_name_and_code_returns_409(self, client, kb_admin_headers):
        resp = await self._create(client, kb_admin_headers, "重复分类", "dup_code")
        assert resp.status_code == 200

        resp2 = await self._create(client, kb_admin_headers, "重复分类", "dup_code")
        assert resp2.status_code == 409

    async def test_duplicate_name_only_returns_409(self, client, kb_admin_headers):
        await self._create(client, kb_admin_headers, "同名分类", "code_a")
        resp = await self._create(client, kb_admin_headers, "同名分类", "code_b")
        assert resp.status_code == 409

    async def test_duplicate_code_only_returns_409(self, client, kb_admin_headers):
        await self._create(client, kb_admin_headers, "分类甲", "same_code")
        resp = await self._create(client, kb_admin_headers, "分类乙", "same_code")
        assert resp.status_code == 409

    async def test_distinct_category_created_ok(self, client, kb_admin_headers):
        await self._create(client, kb_admin_headers, "分类一", "code_one")
        resp = await self._create(client, kb_admin_headers, "分类二", "code_two")
        assert resp.status_code == 200


# ============================================================================
# R12-Notif-1: 训练提醒候选判定
# ============================================================================

@pytest.mark.asyncio
class TestTrainingReminderCandidates:
    """R12-Notif-1: 候选=3 天内无 AI 分析(completed)/比赛(finished)活动的用户"""

    async def _make_user(self, db, openid):
        u = User(openid=openid, nickname=openid, status="active")
        db.add(u)
        await db.flush()
        return u

    async def test_recent_ai_activity_excluded(self, db_session):
        from app.services.notification_service import NotificationService
        from app.models.video_analysis import VideoTask, FileRecord

        now = datetime.now(timezone.utc)
        user_a = await self._make_user(db_session, "p1_remind_task_user")
        file_record = FileRecord(
            user_id=user_a.id, oss_key=f"remind/{user_a.id}",
            file_size=1048576, file_type="mp4", status="uploaded",
        )
        db_session.add(file_record)
        await db_session.flush()
        task = VideoTask(
            user_id=user_a.id, file_id=file_record.id,
            oss_key=f"remind/{user_a.id}",
            status="completed", task_uuid=f"remind-{user_a.id}",
            created_at=now - timedelta(days=1),
        )
        db_session.add(task)
        idle = await self._make_user(db_session, "p1_remind_idle_user")
        await db_session.commit()

        candidates = await NotificationService.get_training_reminder_candidates(db_session)
        cand_map = dict(candidates)
        assert user_a.id not in cand_map  # 3 天内有 AI 分析 → 排除
        assert idle.id in cand_map

    async def test_recent_match_activity_excluded(self, db_session):
        from app.services.notification_service import NotificationService
        from app.models.match import Match

        now = datetime.now(timezone.utc)
        user_b = await self._make_user(db_session, "p1_remind_match_user")
        db_session.add(Match(
            user_id=user_b.id, status="finished",
            created_at=now - timedelta(days=1),
        ))
        await db_session.commit()

        candidates = await NotificationService.get_training_reminder_candidates(db_session)
        cand_map = dict(candidates)
        assert user_b.id not in cand_map  # 3 天内有比赛 → 排除

    async def test_old_activity_still_candidate(self, db_session):
        """5 天前的 AI 分析不排除用户（>3 天阈值），天数按最近分析时间计算"""
        from app.services.notification_service import NotificationService
        from app.models.video_analysis import VideoTask, FileRecord

        now = datetime.now(timezone.utc)
        user_c = await self._make_user(db_session, "p1_remind_old_user")
        file_record = FileRecord(
            user_id=user_c.id, oss_key=f"remind/old/{user_c.id}",
            file_size=1048576, file_type="mp4", status="uploaded",
        )
        db_session.add(file_record)
        await db_session.flush()
        task = VideoTask(
            user_id=user_c.id, file_id=file_record.id,
            oss_key=f"remind/old/{user_c.id}",
            status="completed", task_uuid=f"remind-old-{user_c.id}",
            created_at=now - timedelta(days=5),
        )
        db_session.add(task)
        await db_session.commit()

        candidates = await NotificationService.get_training_reminder_candidates(db_session)
        cand_map = dict(candidates)
        assert user_c.id in cand_map
        assert cand_map[user_c.id] == 5

    async def test_never_analyzed_days_999(self, db_session):
        from app.services.notification_service import NotificationService

        user = await self._make_user(db_session, "p1_remind_new_user")
        await db_session.commit()

        candidates = await NotificationService.get_training_reminder_candidates(db_session)
        cand_map = dict(candidates)
        assert cand_map[user.id] == 999


# ============================================================================
# R12-Gam-1: 徽章种子预置
# ============================================================================

@pytest.mark.asyncio
class TestBadgeSeedDefinitions:
    """R12-Gam-1: BADGE_SEEDS 幂等预置 6 个基础徽章（原零引用死代码）"""

    async def test_seed_inserts_six_badges(self, db_session):
        from app.services.gamification_service import BadgeService
        from sqlalchemy import func

        result = await BadgeService.seed_badge_definitions(db_session)
        assert result["inserted"] == 6
        assert result["updated"] == 0

        count = await db_session.scalar(
            select(func.count()).select_from(BadgeDefinition)
        )
        assert count == 6

        defs = (
            await db_session.scalars(
                select(BadgeDefinition).order_by(BadgeDefinition.sort_order)
            )
        ).all()
        assert [d.sort_order for d in defs] == list(range(6))
        assert all(d.is_active for d in defs)
        assert {d.id for d in defs} == {
            "first_analysis", "first_match", "streak_7",
            "streak_30", "analysis_10", "match_50",
        }

    async def test_seed_idempotent_and_updates_drift(self, db_session):
        from app.services.gamification_service import BadgeService
        from sqlalchemy import func

        await BadgeService.seed_badge_definitions(db_session)
        # 第二次执行：无变更 → 全部 skipped
        result = await BadgeService.seed_badge_definitions(db_session)
        assert result["inserted"] == 0
        assert result["updated"] == 0
        assert result["skipped"] == 6

        # 人为漂移一个徽章（改 icon + 停用）→ seed 修复回 seed 定义
        badge = await db_session.scalar(
            select(BadgeDefinition).where(BadgeDefinition.id == "streak_7")
        )
        badge.icon = "X"
        badge.is_active = False
        await db_session.flush()

        result = await BadgeService.seed_badge_definitions(db_session)
        assert result["updated"] == 1
        assert badge.icon == "🔥"
        assert badge.is_active is True

        # 表内仍只有 6 条（无重复）
        count = await db_session.scalar(
            select(func.count()).select_from(BadgeDefinition)
        )
        assert count == 6


# ============================================================================
# R12-Auth-8/9: refresh / logout 端点覆盖
# ============================================================================

@pytest.mark.asyncio
class TestAuthRefreshLogout:
    """R12-Auth-8/9: refresh 刷新与 logout 撤销链路（SEC-001）"""

    async def test_refresh_success_and_old_token_revoked(self, client, auth_headers, auth_user):
        """合法 refresh_token 换新 token；旧 refresh_token 进黑名单不可复用"""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": auth_user["refresh_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["refresh_token"] != auth_user["refresh_token"]

        # 旧 refresh_token 已进黑名单 → 再刷 401
        resp2 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": auth_user["refresh_token"]},
        )
        assert resp2.status_code == 401

    async def test_refresh_invalid_token_rejected(self, client):
        """非法字符串做 refresh_token → 401"""
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"}
        )
        assert resp.status_code == 401

    async def test_refresh_access_token_not_accepted(self, client, auth_user):
        """access_token 不能当 refresh_token 用（type 校验）"""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": auth_user["access_token"]},
        )
        assert resp.status_code == 401

    async def test_logout_revokes_both_tokens(self, client, auth_headers, auth_user):
        """logout 后 access_token 与 refresh_token 双双失效（SEC-001）"""
        resp = await client.post(
            "/api/v1/auth/logout",
            headers=auth_headers,
            json={
                "access_token": auth_user["access_token"],
                "refresh_token": auth_user["refresh_token"],
            },
        )
        assert resp.status_code == 200

        # access_token 已撤销 → /me 401
        resp_me = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp_me.status_code == 401

        # refresh_token 已撤销 → 刷新 401
        resp_refresh = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": auth_user["refresh_token"]},
        )
        assert resp_refresh.status_code == 401


# ============================================================================
# R12-Auth-7: wechat-login 端点覆盖（code2session mock）
# ============================================================================

@pytest.mark.asyncio
class TestWechatLogin:
    """R12-Auth-7: 微信小程序登录 — 新用户创建/复用 + 封禁/注销中拦截（R12-Auth-2）"""

    @staticmethod
    def _mock_code2session(openid: str):
        async def _mock(code: str) -> dict:
            return {"openid": openid, "session_key": "test-session-key"}
        return _mock

    async def test_wechat_login_creates_new_user(self, client, monkeypatch, db_session):
        from app.services.auth_service import AuthService

        monkeypatch.setattr(
            AuthService, "_call_wechat_code2session",
            self._mock_code2session("wx-openid-new-001"),
        )
        resp = await client.post(
            "/api/v1/auth/wechat-login", json={"code": "any-code"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        # 未传 nickname → 默认"球友"
        assert data["user"]["nickname"] == "球友"

        # DB 验证：openid 用户已创建且状态正常
        user = (
            await db_session.execute(
                select(User).where(User.openid == "wx-openid-new-001")
            )
        ).scalar_one_or_none()
        assert user is not None
        assert user.status == "active"

    async def test_wechat_login_existing_user_not_duplicated(
        self, client, monkeypatch, db_session
    ):
        from app.services.auth_service import AuthService

        existing = User(
            openid="wx-openid-exist-001", nickname="老球友", status="active"
        )
        db_session.add(existing)
        await db_session.commit()

        monkeypatch.setattr(
            AuthService, "_call_wechat_code2session",
            self._mock_code2session("wx-openid-exist-001"),
        )
        resp = await client.post(
            "/api/v1/auth/wechat-login",
            json={"code": "any-code", "nickname": "新昵称"},
        )
        assert resp.status_code == 200
        # 已存在用户不重复创建，昵称不被请求参数覆盖
        data = resp.json()["data"]
        assert data["user"]["nickname"] == "老球友"

    async def test_wechat_login_banned_403(self, client, monkeypatch, db_session):
        """R12-Auth-2: 登录入口拦截封禁用户（与 phone_login 一致）"""
        from app.services.auth_service import AuthService

        banned = User(
            openid="wx-openid-banned-001", nickname="封禁用户", status="banned"
        )
        db_session.add(banned)
        await db_session.commit()

        monkeypatch.setattr(
            AuthService, "_call_wechat_code2session",
            self._mock_code2session("wx-openid-banned-001"),
        )
        resp = await client.post("/api/v1/auth/wechat-login", json={"code": "any"})
        assert resp.status_code == 403

    async def test_wechat_login_pending_deletion_403(
        self, client, monkeypatch, db_session
    ):
        from app.services.auth_service import AuthService

        pending = User(
            openid="wx-openid-pending-001", nickname="注销中", status="pending_deletion"
        )
        db_session.add(pending)
        await db_session.commit()

        monkeypatch.setattr(
            AuthService, "_call_wechat_code2session",
            self._mock_code2session("wx-openid-pending-001"),
        )
        resp = await client.post("/api/v1/auth/wechat-login", json={"code": "any"})
        assert resp.status_code == 403


# ============================================================================
# R12-Payment-2: 支付回调验签失败（安全关键）
# ============================================================================

@pytest.mark.asyncio
class TestPaymentNotifySignature:
    """R12-Payment-2: 回调验签失败 → 400 FAIL，订单不被误处理"""

    async def test_invalid_signature_returns_fail_and_skips_processing(
        self, client, db_session, monkeypatch
    ):
        import json as _json

        from app.core.config import settings
        from app.models.payment import Order

        # 关闭 MOCK：走真实验签路径（Redis 无平台证书 → 验签必失败）
        monkeypatch.setattr(settings, "WECHAT_PAY_MOCK", False)

        user = User(openid="p1_notify_user", nickname="回调用户", status="active")
        db_session.add(user)
        await db_session.flush()
        order = Order(
            user_id=user.id, order_no="R12SIG0001",
            product_type="membership", amount_cents=1900, status="pending",
        )
        db_session.add(order)
        await db_session.commit()

        body = _json.dumps({
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "out_trade_no": "R12SIG0001",
                "transaction_id": "wx_bad_sig_001",
                "trade_state": "SUCCESS",
                "amount": {"total": 1900},
            },
        })
        resp = await client.post(
            "/api/v1/payment/notify",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "invalid-signature",
                "Wechatpay-Serial": "INVALID_SERIAL",
                "Wechatpay-Nonce": "test_nonce",
                "Wechatpay-Timestamp": "1700000000",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "FAIL"

        # 验签失败：订单保持 pending（未被误标记为已支付）
        await db_session.refresh(order)
        assert order.status == "pending"
        assert order.paid_at is None


@pytest.mark.asyncio
class TestConsentPolicyVersionValidation:
    """R12-Auth-4: policy_version 合法性校验 — 非当前版本 422，不产生无效同意记录"""

    async def test_invalid_policy_version_rejected_422(self, client, auth_headers):
        """非当前政策版本 → 422，且不产生同意记录"""
        resp = await client.post(
            "/api/v1/auth/consent",
            json={"consent_type": "privacy_policy", "policy_version": "0.9"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == 42200

        # 无效版本不产生同意记录：consent-status 保持未同意
        status = await client.get(
            "/api/v1/auth/consent-status", headers=auth_headers
        )
        assert status.json()["data"]["consented"] is False

    async def test_invalid_policy_version_writes_no_consent_log(
        self, client, auth_headers
    ):
        """无效版本 POST 后 consent_log 无记录（防无效同意记录入库）"""
        resp = await client.post(
            "/api/v1/auth/consent",
            json={"consent_type": "privacy_policy", "policy_version": "9.9.9"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

        # 库中无记录：consent-status 保持未同意且版本为 null
        status = await client.get(
            "/api/v1/auth/consent-status", headers=auth_headers
        )
        data = status.json()["data"]
        assert data["consented"] is False and data["policy_version"] is None

    async def test_valid_policy_version_accepted_and_matches_status(
        self, client, auth_headers
    ):
        """当前版本 v1.0 → 200，consent-status 翻转为已同意（check_consent 可命中）"""
        resp = await client.post(
            "/api/v1/auth/consent",
            json={"consent_type": "privacy_policy", "policy_version": "v1.0"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["consented"] is True

        status = await client.get(
            "/api/v1/auth/consent-status", headers=auth_headers
        )
        data = status.json()["data"]
        assert data["consented"] is True
        assert data["policy_version"] == "v1.0"


@pytest.mark.asyncio
class TestRatingRangeValidation:
    """R12-User-3/4: rating 超范围 → 400（API §3.3 错误表），非 Schema 422"""

    @pytest.mark.parametrize("bad_rating", [499, 3001, 0, 99999])
    async def test_rating_out_of_range_returns_400(self, client, auth_headers, bad_rating):
        resp = await client.patch(
            "/api/v1/users/rating",
            headers=auth_headers,
            json={"rating": bad_rating, "source": "manual"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == 40000
        assert "500-3000" in body["message"]

    @pytest.mark.parametrize("good_rating", [500, 3000])
    async def test_rating_boundary_values_accepted(self, client, auth_headers, good_rating):
        """边界值 500/3000 合法"""
        resp = await client.patch(
            "/api/v1/users/rating",
            headers=auth_headers,
            json={"rating": good_rating, "source": "manual"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["new_rating"] == good_rating


class TestEscalateActionNoRewrite:
    """R12-Training-B3: escalate 为「诊断原因」动作，不改写训练内容（设计 §8.6 无此分支）"""

    @staticmethod
    def _make_plan():
        from app.models.training import TrainingPlan

        plan = TrainingPlan(user_id=1, template_id=None)
        plan.version = 1
        plan.plan_data = {
            "sessions": [{"name": "正手攻球", "reps": 10}, {"name": "反手拨球", "reps": 20}],
            "goal": {"forehand_consistency": 0.7},
        }
        return plan

    def test_escalate_keeps_sessions_unchanged(self):
        from app.services.training_service import TrainingAdviceService

        plan = self._make_plan()
        goal_metrics = {"forehand_consistency": 0.7}
        result = TrainingAdviceService._generate_new_plan(plan, [], goal_metrics, "escalate")
        # escalate 不改写训练内容：reps 原样
        assert result["plan_data"]["sessions"][0]["reps"] == 10
        assert result["plan_data"]["sessions"][1]["reps"] == 20
        # 仅版本递增 + 诊断由 adjustment_reason 承载
        assert result["version"] == 2
        assert result["goal"] == goal_metrics

    def test_adjust_still_increases_reps(self):
        """对照：adjust 仍按设计 reps*1.2"""
        from app.services.training_service import TrainingAdviceService

        plan = self._make_plan()
        result = TrainingAdviceService._generate_new_plan(
            plan, [], {"forehand_consistency": 0.7}, "adjust"
        )
        assert result["plan_data"]["sessions"][0]["reps"] == 12
        assert result["plan_data"]["sessions"][1]["reps"] == 24


@pytest.mark.asyncio
class TestAIPipelineCircuitBreaker:
    """R12-AIPipeline-7/8/11: 共享 ai_inference 熔断器 + LLM 降级 + Step 9 时序"""

    async def test_five_failures_open_shared_breaker(self):
        """连续 5 次失败 → open（共享键 ai_inference）"""
        from app.ai_pipeline.circuit_breaker import AICircuitBreaker, CircuitState

        cb = AICircuitBreaker("ai_inference")
        for _ in range(5):
            await cb.record_failure()
        assert await cb.get_state() == CircuitState.OPEN
        assert await cb.allow_request() is False
        await cb.record_success()  # 清理，恢复 closed

    async def test_success_resets_failure_counter(self):
        """成功一次即重置计数"""
        from app.ai_pipeline.circuit_breaker import AICircuitBreaker, CircuitState

        cb = AICircuitBreaker("ai_inference")
        for _ in range(3):
            await cb.record_failure()
        await cb.record_success()
        assert await cb.get_state() == CircuitState.CLOSED
        # 计数清零：再 4 次失败不熔断
        for _ in range(4):
            await cb.record_failure()
        assert await cb.get_state() == CircuitState.CLOSED
        await cb.record_success()

    async def test_llm_open_breaker_falls_back_to_template(self, monkeypatch):
        """R12-AIPipeline-8: 熔断 open → 直接模板生成，不调用 LLM"""
        from app.ai_pipeline.circuit_breaker import AICircuitBreaker
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.core.config import settings

        cb = AICircuitBreaker("ai_inference")
        for _ in range(5):
            await cb.record_failure()

        monkeypatch.setattr(settings, "LLM_ENABLED", True)
        monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.test")

        async def _must_not_call(result_data):
            raise AssertionError("熔断 open 时不得调用 LLM")

        monkeypatch.setattr(ReportGenerator, "_generate_llm_report", staticmethod(_must_not_call))

        result, used_llm = await ReportGenerator._generate_report_text(
            {"technique_stats": {"forehand_loop": 10, "backhand_block": 2}}, task_id=1
        )
        # 模板降级产物
        assert "summary" in result and "issues" in result
        # R12-AIPipeline-4: 熔断降级模板 → used_llm=False（按实际生成方式记录）
        assert used_llm is False
        await cb.record_success()  # 清理

    async def test_exec_step_uses_shared_ai_inference_name(self, monkeypatch):
        """R12-AIPipeline-7: _exec_step 实例化共享 ai_inference 熔断器（非 step_name）"""
        import contextlib

        import app.ai_pipeline.tasks as tasks_mod

        seen_names = []
        real_init = tasks_mod.AICircuitBreaker.__init__

        def _spy_init(self, service_name):
            seen_names.append(service_name)
            real_init(self, service_name)

        monkeypatch.setattr(tasks_mod.AICircuitBreaker, "__init__", _spy_init)

        async def _noop(*args, **kwargs):
            return None

        monkeypatch.setattr(tasks_mod.ProgressTracker, "on_step_start", staticmethod(_noop))
        monkeypatch.setattr(tasks_mod.ProgressTracker, "on_step_complete", staticmethod(_noop))
        monkeypatch.setattr(tasks_mod.ProgressTracker, "on_step_failed", staticmethod(_noop))

        @contextlib.asynccontextmanager
        async def _fake_factory(*args, **kwargs):
            yield None

        monkeypatch.setattr(tasks_mod, "async_session_factory", _fake_factory)

        step_results = {}
        await tasks_mod._exec_step(
            1, 1, "video_preprocessing", lambda: {"ok": True}, step_results
        )
        assert seen_names == ["ai_inference"]
        assert step_results[1] == {"ok": True}
