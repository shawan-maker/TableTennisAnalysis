"""
tests/unit/test_supplements_p0.py — P0 优先级补充测试

覆盖 R8-R11 审查发现的关键修复项：
- R9-Admin-P2-1: create 操作审计日志 target_id
- R6-Mbr-1: expired/closed 按免费用户处理
- R5-Mbr-1: 实时兜底 grace_period
- R6-Gami-1: SAVEPOINT 隔离并发徽章解锁
- R4-Pay-2: 24h-7d 部分退款 50% 限额
- 退款后撤销会员权益级联
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from app.core.security import create_access_token, generate_jti, pwd_context
from app.models.admin import AdminUser, AuditLog
from app.models.user import User
from app.models.membership import Subscription, MembershipTierConfig
from app.models.payment import Order, PaymentRecord
from app.models.gamification import UserPoints, CheckInRecord, BadgeDefinition


# ============================================================================
# Admin 审计日志 P0 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def admin_in_db(db_session):
    """在 DB 中创建管理员"""
    admin = AdminUser(
        username="sup_admin",
        password_hash=pwd_context.hash("Admin@123"),
        role="super_admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.mark.asyncio
class TestAdminAuditLogTargetId:
    """R9-Admin-P2-1: create 操作审计日志 target_id 验证"""

    async def test_create_config_audit_log_target_id(self, db_session, admin_in_db):
        """create_config 审计日志 target_id 应为新建配置的 id（非 None）"""
        from app.services.admin_service import AdminService
        from sqlalchemy import select

        result = await AdminService.create_config(
            key="test_p0_key", value="test_value",
            description="P0测试", admin_id=admin_in_db.id,
        )

        # 查询审计日志
        log_result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "create",
                AuditLog.target_type == "config",
                AuditLog.admin_id == admin_in_db.id,
            ).order_by(AuditLog.id.desc()).limit(1)
        )
        audit_log = log_result.scalar_one_or_none()

        assert audit_log is not None, "审计日志应存在"
        assert audit_log.target_id == result.id, f"target_id 应为 {result.id}，实际为 {audit_log.target_id}"
        assert audit_log.changes is not None, "changes 字段不应为 None"
        assert "config_key" in audit_log.changes, "changes 应包含 config_key"

    async def test_create_category_audit_log_target_id(self, db_session, admin_in_db):
        """create_category 审计日志 target_id 应为新建分类的 id"""
        from app.services.admin_service import AdminService
        from sqlalchemy import select

        result = await AdminService.create_category(
            name="P0测试分类", code="p0_cat",
            admin_id=admin_in_db.id,
        )

        log_result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "create",
                AuditLog.target_type == "knowledge",
                AuditLog.admin_id == admin_in_db.id,
            ).order_by(AuditLog.id.desc()).limit(1)
        )
        audit_log = log_result.scalar_one_or_none()

        assert audit_log is not None, "审计日志应存在"
        assert audit_log.target_id == result["id"], f"target_id 应为 {result['id']}，实际为 {audit_log.target_id}"

    async def test_create_rule_audit_log_target_id(self, db_session, admin_in_db):
        """create_rule 审计日志 target_id 应为新建规则的 id"""
        from app.services.admin_service import AdminService
        from sqlalchemy import select

        result = await AdminService.create_rule(
            rule_id="p0_rule_001", rule_name="P0测试规则", rule_type="single",
            condition={"metric": "forehand_ratio", "operator": "<", "threshold": 0.4},
            diagnosis={"problem_id": "p0_prob", "problem_name": "P0问题", "severity": "medium"},
            admin_id=admin_in_db.id,
        )

        log_result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "create",
                AuditLog.target_type == "knowledge",
                AuditLog.admin_id == admin_in_db.id,
            ).order_by(AuditLog.id.desc()).limit(1)
        )
        audit_log = log_result.scalar_one_or_none()

        assert audit_log is not None, "审计日志应存在"
        assert audit_log.target_id == result["id"], f"target_id 应为 {result['id']}，实际为 {audit_log.target_id}"


# ============================================================================
# Membership 状态机 P0 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def member_user_with_subscription(db_session):
    """创建会员用户 + active 订阅"""
    user = User(openid="p0_member_001", nickname="P0会员", status="active")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=now - timedelta(days=20),
        expire_at=now + timedelta(days=10),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(sub)
    return user, sub


@pytest.mark.asyncio
class TestMembershipStateMachine:
    """会员状态机五态完整性测试"""

    async def test_closed_state_detection(self, db_session, member_user_with_subscription):
        """到期 14 天后（宽限 7 + 过期 7）从 expired 标记为 closed"""
        from app.services.membership_service import MembershipService

        user, sub = member_user_with_subscription
        # 设置过期 15 天（超过宽限 7 + 过期 7 = 14 天）
        sub.expire_at = datetime.now(timezone.utc) - timedelta(days=15)
        sub.status = "expired"
        await db_session.commit()

        await MembershipService.check_expiry(db_session)

        await db_session.refresh(sub)
        assert sub.status == "closed", f"到期 15 天后应为 closed，实际为 {sub.status}"

    async def test_check_membership_expired_as_free(self, db_session, member_user_with_subscription):
        """R6-Mbr-1: expired 状态按免费用户处理"""
        from app.services.membership_service import MembershipService

        user, sub = member_user_with_subscription
        sub.status = "expired"
        await db_session.commit()

        result = await MembershipService.check_membership(db_session, user.id)
        assert result.is_member == False, "expired 状态不应享受会员权益"
        assert result.tier == "free", f"应为 free，实际为 {result.tier}"

    async def test_check_membership_closed_as_free(self, db_session, member_user_with_subscription):
        """R6-Mbr-1: closed 状态按免费用户处理"""
        from app.services.membership_service import MembershipService

        user, sub = member_user_with_subscription
        sub.status = "closed"
        await db_session.commit()

        result = await MembershipService.check_membership(db_session, user.id)
        assert result.is_member == False, "closed 状态不应享受会员权益"
        assert result.tier == "free"

    async def test_realtime_expiry_grace_period(self, db_session, member_user_with_subscription):
        """R5-Mbr-1: 实时兜底检测到期时先判断宽限期，跳过 grace_period"""
        from app.services.membership_service import MembershipService

        user, sub = member_user_with_subscription
        # 刚过期 3 天（宽限期内）
        sub.expire_at = datetime.now(timezone.utc) - timedelta(days=3)
        sub.status = "active"
        await db_session.commit()

        result = await MembershipService.get_current_membership(db_session, user.id)
        assert result.status == "grace_period", f"宽限期内应为 grace_period，实际为 {result.status}"

    async def test_realtime_expiry_expired(self, db_session, member_user_with_subscription):
        """R5-Mbr-1: 超过宽限期的实时兜底直接 expired"""
        from app.services.membership_service import MembershipService

        user, sub = member_user_with_subscription
        # 过期 10 天（超过宽限期 7 天）
        sub.expire_at = datetime.now(timezone.utc) - timedelta(days=10)
        sub.status = "active"
        await db_session.commit()

        result = await MembershipService.get_current_membership(db_session, user.id)
        assert result.status == "expired", f"超过宽限期应为 expired，实际为 {result.status}"


# ============================================================================
# Gamification SAVEPOINT 隔离 P0 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def seed_badge_definitions(db_session):
    """预置徽章定义"""
    badges = [
        BadgeDefinition(
            id="first_analysis", name="首分析", icon="📹", category="analysis",
            condition={"metric": "analysis_count", "operator": ">=", "threshold": 1},
            points_reward=10, sort_order=1, is_active=True,
        ),
        BadgeDefinition(
            id="streak_7", name="连续7天", icon="🔥", category="streak",
            condition={"metric": "streak_days", "operator": ">=", "threshold": 7},
            points_reward=20, sort_order=2, is_active=True,
        ),
    ]
    for b in badges:
        db_session.add(b)
    await db_session.commit()
    return badges


@pytest.mark.asyncio
class TestGamificationSavepoint:
    """R6-Gami-1: SAVEPOINT 隔离并发徽章解锁"""

    async def test_savepoint_isolation_on_integrity_error(
        self, db_session, seed_badge_definitions
    ):
        """IntegrityError 时仅 SAVEPOINT 回滚，调用方事务保留"""
        from app.services.gamification_service import GamificationService, BadgeService
        from app.models.gamification import UserBadge
        from sqlalchemy import select

        # 创建用户 + 积分
        user = User(openid="p0_gami_001", nickname="P0打卡", status="active")
        db_session.add(user)
        await db_session.flush()

        up = UserPoints(user_id=user.id, total_points=50, monthly_points=50, current_streak=1)
        db_session.add(up)

        # 预先解锁 first_analysis 徽章（模拟并发竞态）
        existing_badge = UserBadge(user_id=user.id, badge_id="first_analysis")
        db_session.add(existing_badge)
        await db_session.commit()

        # 设置用户 metrics 满足 first_analysis 条件
        # 由于 first_analysis 已解锁，check_badges 应跳过它
        # 测试 SAVEPOINT 隔离：即使 check_badges 内部出错，外层事务不受影响

        # 执行打卡（会触发 check_badges）
        result = await GamificationService.checkin(db_session, user.id)
        await db_session.commit()

        # 验证打卡记录已提交保留
        checkin_result = await db_session.execute(
            select(CheckInRecord).where(CheckInRecord.user_id == user.id)
        )
        checkins = checkin_result.scalars().all()
        assert len(checkins) > 0, "打卡记录应保留（SAVEPOINT 隔离）"

        # 验证积分已更新
        up_result = await db_session.execute(
            select(UserPoints).where(UserPoints.user_id == user.id)
        )
        up_refreshed = up_result.scalar_one()
        assert up_refreshed.total_points > 50, "积分应已更新保留"


# ============================================================================
# Payment 退款 P0 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def paid_order(db_session):
    """创建已支付订单"""
    user = User(openid="p0_pay_001", nickname="P0支付", status="active")
    db_session.add(user)
    await db_session.flush()

    order = Order(
        user_id=user.id,
        order_no="P0_ORDER_001",
        product_type="membership",
        amount_cents=1900,
        status="paid",
        paid_at=datetime.now(timezone.utc) - timedelta(days=3),
        extra_data={"tier": "member", "period_days": 30, "period": "monthly"},
    )
    db_session.add(order)
    await db_session.flush()  # 先 flush 获取 order.id

    payment = PaymentRecord(
        order_id=order.id,
        transaction_id="p0_txn_001",
        payment_method="wechat_jsapi",
        amount_cents=1900,
        paid_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(order)
    return user, order


@pytest.mark.asyncio
class TestPaymentRefundRules:
    """R4-Pay-2: 退款时间窗口 + 50% 限额 + 撤销权益"""

    async def test_refund_partial_50pct_limit_24h_to_7d(self, db_session, paid_order):
        """24h-7d 内部分退款不可超过 50%"""
        from app.services.payment_service import PaymentService
        from app.core.exceptions import AppException

        user, order = paid_order
        # 订单已支付 3 天（在 24h-7d 窗口内）
        # 申请 60% 退款（超过 50% 限额）
        with pytest.raises(AppException) as exc_info:
            await PaymentService.refund(
                order_id=order.id,
                refund_amount_cents=int(order.amount_cents * 0.6),
                reason="P0测试超额退款",
                operator_id=user.id,
            )
        assert "50%" in str(exc_info.value.detail) or "50%" in str(exc_info.value), \
            f"应提示 50% 限额，实际: {exc_info.value}"

    async def test_refund_partial_40pct_allowed_24h_to_7d(self, db_session, paid_order):
        """24h-7d 内 40% 部分退款允许"""
        from app.services.payment_service import PaymentService

        user, order = paid_order
        result = await PaymentService.refund(
            order_id=order.id,
            refund_amount_cents=int(order.amount_cents * 0.4),
            reason="P0测试合法退款",
            operator_id=user.id,
        )
        assert result.refund_amount_cents == int(order.amount_cents * 0.4)

    async def test_refund_revokes_subscription(self, db_session, paid_order):
        """退款后撤销会员权益——订阅状态变 closed"""
        from app.services.payment_service import PaymentService
        from app.services.membership_service import MembershipService

        user, order = paid_order
        # 创建关联订阅
        sub = Subscription(
            user_id=user.id, tier="member", status="active",
            start_at=datetime.now(timezone.utc) - timedelta(days=3),
            expire_at=datetime.now(timezone.utc) + timedelta(days=27),
        )
        db_session.add(sub)
        await db_session.flush()
        order.subscription_id = sub.id
        # 全额退款（24h 内可全额）
        order.paid_at = datetime.now(timezone.utc) - timedelta(hours=2)
        await db_session.commit()
        await db_session.refresh(sub)
        await db_session.refresh(order)

        result = await PaymentService.refund(
            order_id=order.id,
            refund_amount_cents=order.amount_cents,
            reason="P0测试全额退款撤销权益",
            operator_id=user.id,
        )

        # 验证订阅已撤销
        await db_session.refresh(sub)
        assert sub.status == "closed", f"退款后订阅应为 closed，实际为 {sub.status}"
        assert sub.cancelled_at is not None, "cancelled_at 应有值"
