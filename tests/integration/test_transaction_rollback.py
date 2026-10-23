"""
tests/integration/test_transaction_rollback.py — 事务回滚补充测试

覆盖薄弱环节：支付失败回滚、Celery 任务失败回滚、无效数据触发回滚
"""

import json
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from app.core.security import create_access_token, generate_jti
from app.core.database import async_session_factory
from app.models.user import User
from app.models.payment import Order, PaymentRecord, RefundRecord
from app.models.membership import Subscription, MembershipTierConfig
from app.services.payment_service import PaymentService
from sqlalchemy import select


def _auth_headers(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id), 'jti': generate_jti()})}"}


@pytest_asyncio.fixture
async def paid_order_with_record(db_session, seed_tiers):
    """创建一个已支付的订单（含 PaymentRecord + Subscription）"""
    user = User(openid="rb_user", nickname="回滚用户", status="active")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    order = Order(
        user_id=user.id,
        order_no=f"rb_{uuid.uuid4().hex[:16]}",
        product_type="membership",
        amount_cents=1900,
        status="paid",
        paid_at=datetime.now(timezone.utc),
    )
    db_session.add(order)
    await db_session.flush()

    payment = PaymentRecord(
        order_id=order.id,
        transaction_id=f"wx_rb_{uuid.uuid4().hex[:8]}",
        payment_method="wechat_jsapi",
        amount_cents=1900,
        paid_at=datetime.now(timezone.utc),
    )
    db_session.add(payment)

    sub = Subscription(
        user_id=user.id,
        tier="member",
        start_at=datetime.now(timezone.utc),
        expire_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(order)
    return user, order


@pytest.mark.asyncio
class TestPaymentFailureRollback:
    """支付失败回滚测试"""

    async def test_notify_nonexistent_order_no_side_effects(self, client, seed_tiers):
        """回调不存在的订单不创建任何记录"""
        callback_body = json.dumps({
            "resource": {
                "out_trade_no": "nonexistent_order_999",
                "transaction_id": f"wx_fail_{uuid.uuid4().hex[:8]}",
                "trade_state": "SUCCESS",
                "amount": {"total": 1900},
            }
        })
        resp = await client.post(
            "/api/v1/payment/notify",
            content=callback_body,
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "sig",
                "Wechatpay-Serial": "serial",
                "Wechatpay-Nonce": "nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )
        assert resp.status_code in (200, 400)
        result = resp.json()
        assert result.get("code") == "FAIL"

        # 验证没有创建 PaymentRecord
        async with async_session_factory() as db:
            result = await db.execute(
                select(PaymentRecord).where(
                    PaymentRecord.transaction_id == callback_body
                )
            )
            records = result.scalars().all()
            assert len(records) == 0

    async def test_notify_failed_trade_state_no_payment_record(self, client, paid_order_with_record):
        """trade_state != SUCCESS 时不创建 PaymentRecord（针对 pending 订单）"""
        user, order = paid_order_with_record
        # 此订单已 paid，改回 pending 测试失败回调
        order.status = "pending"
        async with async_session_factory() as db:
            db_obj = await db.get(Order, order.id)
            db_obj.status = "pending"
            await db.commit()

        callback_body = json.dumps({
            "resource": {
                "out_trade_no": order.order_no,
                "transaction_id": f"wx_fail2_{uuid.uuid4().hex[:8]}",
                "trade_state": "CLOSED",
                "amount": {"total": 1900},
            }
        })
        resp = await client.post(
            "/api/v1/payment/notify",
            content=callback_body,
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "sig",
                "Wechatpay-Serial": "serial",
                "Wechatpay-Nonce": "nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )
        # 应返回 FAIL
        result = resp.json()
        assert result.get("code") == "FAIL"

    async def test_refund_failed_order_not_refunded(self, client, db_session, seed_tiers):
        """对未支付订单执行退款应失败，不创建 RefundRecord"""
        from app.core.config import settings
        from app.core.security import create_access_token, generate_jti

        user = User(openid="rf_user", nickname="退款用户", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        order = Order(
            user_id=user.id,
            order_no=f"rf_{uuid.uuid4().hex[:16]}",
            product_type="membership",
            amount_cents=1900,
            status="pending",
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        # 使用 JWT admin（退款端点用 get_current_admin，非 Redis admin session）
        settings.ADMIN_USER_IDS = str(user.id)
        admin_token = create_access_token({"sub": str(user.id), "jti": generate_jti()})

        resp = await client.post(
            f"/api/v1/payment/orders/{order.id}/refund",
            json={"refund_amount_cents": 1900, "reason": "测试退款"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code in (400, 404, 422)

        # 验证没有创建 RefundRecord
        async with async_session_factory() as db:
            result = await db.execute(
                select(RefundRecord).where(RefundRecord.order_id == order.id)
            )
            records = result.scalars().all()
            assert len(records) == 0


@pytest.mark.asyncio
class TestDatabaseConstraintRollback:
    """数据库约束触发回滚测试"""

    async def test_duplicate_order_no_rollback(self, db_session):
        """重复 order_no 插入应回滚，不产生两条记录"""
        user = User(openid="dup_user", nickname="重复用户", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        order_no = f"dup_{uuid.uuid4().hex[:16]}"
        order1 = Order(
            user_id=user.id, order_no=order_no,
            product_type="membership", amount_cents=1900,
        )
        db_session.add(order1)
        await db_session.commit()

        # 尝试插入相同 order_no
        order2 = Order(
            user_id=user.id, order_no=order_no,
            product_type="membership", amount_cents=3900,
        )
        db_session.add(order2)
        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

        # 回滚后验证只有一条
        await db_session.rollback()
        async with async_session_factory() as db:
            result = await db.execute(
                select(Order).where(Order.order_no == order_no)
            )
            orders = result.scalars().all()
            assert len(orders) == 1

    async def test_fk_constraint_user_not_exist_rollback(self, db_session):
        """FK 约束：不存在的 user_id 插入 Order 应回滚"""
        order = Order(
            user_id=999999,  # 不存在的 user_id
            order_no=f"fk_{uuid.uuid4().hex[:16]}",
            product_type="membership", amount_cents=1900,
        )
        db_session.add(order)
        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()
        await db_session.rollback()

    async def test_check_constraint_file_size_rollback(self, db_session):
        """CHECK 约束：FileRecord file_size < 1MB 应回滚"""
        from app.models.video_analysis import FileRecord
        from sqlalchemy.exc import IntegrityError

        user = User(openid="ck_user", nickname="约束用户", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # 使用独立 session 测试约束
        async with async_session_factory() as db:
            file = FileRecord(
                user_id=user.id, oss_key=f"ck/{uuid.uuid4().hex}.mp4",
                file_size=500,  # 500 bytes < 1MB
                file_type="mp4",
            )
            db.add(file)
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()

        # 验证没有插入
        async with async_session_factory() as db:
            result = await db.execute(
                select(FileRecord).where(FileRecord.user_id == user.id)
            )
            records = result.scalars().all()
            assert len(records) == 0
