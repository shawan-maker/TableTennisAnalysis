"""
tests/unit/test_payment.py — 支付模块测试

覆盖：订单创建（mock 微信下单）、订单列表、回调验签+幂等、退款、权限。
开发模式：WECHAT_PAY_MOCK=True，跳过真实微信 API 调用。
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import create_access_token, generate_jti


@pytest.fixture
async def payment_ctx(db_session, seed_tiers, test_user):
    """创建测试上下文：用户 + 订阅 + 已支付订单"""
    from app.models.payment import Order, PaymentRecord
    from app.models.membership import Subscription

    user_id = test_user.id
    now = datetime.now(timezone.utc)

    sub = Subscription(
        user_id=user_id, tier="free", status="active",
        start_at=now, expire_at=now,
    )
    db_session.add(sub)
    await db_session.flush()

    paid_order = Order(
        user_id=user_id, subscription_id=sub.id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0001",
        product_type="membership", amount_cents=1900,
        status="paid", paid_at=now,
    )
    db_session.add(paid_order)
    await db_session.flush()

    payment = PaymentRecord(
        order_id=paid_order.id,
        transaction_id=f"wx_{uuid.uuid4().hex[:16]}",
        payment_method="wechat_jsapi", amount_cents=1900,
        callback_raw={"transaction_id": "wx_test_001", "trade_state": "SUCCESS"},
        paid_at=now,
    )
    db_session.add(payment)
    await db_session.commit()

    return {
        "user": test_user, "subscription": sub,
        "paid_order": paid_order, "payment": payment,
    }


# === 1. Happy Path ===

@pytest.mark.asyncio
async def test_create_order_membership(client, auth_headers, seed_tiers):
    """创建会员订单成功，返回 mock 支付参数"""
    resp = await client.post("/api/v1/payment/orders", json={
        "product_type": "membership",
        "tier": "member", "period": "monthly",
        "payment_method": "wechat_jsapi",
    }, headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["order_id"] > 0
    assert "PP" in data["order_no"]
    assert data["amount_cents"] == 1900
    assert "prepay_id" in data["payment_params"]
    assert "pay_sign" in data["payment_params"]


@pytest.mark.asyncio
async def test_create_order_analysis_pack(client, auth_headers):
    """创建分析次数包订单"""
    resp = await client.post("/api/v1/payment/orders", json={
        "product_type": "analysis_pack",
        "quantity": 3,
        "payment_method": "wechat_jsapi",
    }, headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["amount_cents"] == 3900


@pytest.mark.asyncio
async def test_list_orders_success(client, payment_ctx, auth_headers):
    """获取订单列表，返回分页结果"""
    resp = await client.get("/api/v1/payment/orders", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["status"] == "paid"


@pytest.mark.asyncio
async def test_list_orders_filter_by_status(client, payment_ctx, auth_headers):
    """按状态过滤订单列表"""
    resp = await client.get(
        "/api/v1/payment/orders?status=paid", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(item["status"] == "paid" for item in data["items"])


@pytest.mark.asyncio
async def test_payment_notify_success(client, payment_ctx, db_session):
    """微信支付回调：验签通过 → 更新订单 → 触发业务逻辑"""
    from app.models.payment import Order

    # 创建 pending 订单
    pending_order = Order(
        user_id=payment_ctx["user"].id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0099",
        product_type="membership", amount_cents=1900,
        status="pending",
        extra_data={"tier": "member", "period_days": 30, "period": "monthly"},
    )
    db_session.add(pending_order)
    await db_session.commit()
    await db_session.refresh(pending_order)

    callback_body = json.dumps({
        "id": "EV-TEST-001",
        "create_time": datetime.now(timezone.utc).isoformat(),
        "resource_type": "encrypt-resource",
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "out_trade_no": pending_order.order_no,
            "transaction_id": "wx_notify_001",
            "trade_state": "SUCCESS",
            "amount": {"total": 1900},
        },
    })

    resp = await client.post(
        "/api/v1/payment/notify",
        content=callback_body,
        headers={
            "Content-Type": "application/json",
            "Wechatpay-Signature": "test_sig",
            "Wechatpay-Serial": "test_serial",
            "Wechatpay-Nonce": "test_nonce",
            "Wechatpay-Timestamp": "1234567890",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["code"] == "SUCCESS"

    # 验证订单已更新（新 session 查询避免缓存）
    from app.core.database import async_session_factory
    from sqlalchemy import select as sa_select
    from app.models.payment import Order as OrderModel
    async with async_session_factory() as verify_session:
        result = await verify_session.execute(
            sa_select(OrderModel).where(OrderModel.id == pending_order.id)
        )
        updated = result.scalar_one()
        assert updated.status == "paid"
        assert updated.paid_at is not None


# === 2. Validation Failure ===

@pytest.mark.asyncio
async def test_create_order_invalid_product_type(client, auth_headers):
    """product_type 不在枚举中时返回 422"""
    resp = await client.post("/api/v1/payment/orders", json={
        "product_type": "invalid_type",
        "tier": "member", "period": "monthly",
        "payment_method": "wechat_jsapi",
    }, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_order_missing_period_for_membership(client, auth_headers, seed_tiers):
    """membership 类型缺少 period 参数返回 422"""
    resp = await client.post("/api/v1/payment/orders", json={
        "product_type": "membership",
        "tier": "member",
        "payment_method": "wechat_jsapi",
    }, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_refund_amount_exceeds_order(client, payment_ctx, admin_headers):
    """退款金额超出订单金额返回 400"""
    resp = await client.post(
        f"/api/v1/payment/orders/{payment_ctx['paid_order'].id}/refund",
        json={"refund_amount_cents": 999999, "reason": "测试"},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "不能超过" in resp.json()["message"]


# === 3. Permission / Auth Failure ===

@pytest.mark.asyncio
async def test_create_order_no_auth(client):
    """未登录创建订单返回 401"""
    resp = await client.post("/api/v1/payment/orders", json={
        "product_type": "membership",
        "tier": "member", "period": "monthly",
        "payment_method": "wechat_jsapi",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refund_non_admin(client, payment_ctx, auth_headers):
    """非管理员退款返回 403"""
    resp = await client.post(
        f"/api/v1/payment/orders/{payment_ctx['paid_order'].id}/refund",
        json={"refund_amount_cents": 1900, "reason": "测试退款"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_orders_user_isolation(client, payment_ctx, db_session):
    """用户只能看到自己的订单"""
    from app.models.user import User

    user2 = User(openid="test_user2_openid", nickname="用户2", status="active")
    db_session.add(user2)
    await db_session.commit()

    token2 = create_access_token({"sub": str(user2.id), "jti": generate_jti()})
    headers2 = {"Authorization": f"Bearer {token2}"}

    resp = await client.get("/api/v1/payment/orders", headers=headers2)
    assert resp.status_code == 200
    data = resp.json()["data"]
    order_ids = [item["id"] for item in data["items"]]
    assert payment_ctx["paid_order"].id not in order_ids


# === 4. Business Rule ===

@pytest.mark.asyncio
async def test_notify_idempotent(client, payment_ctx):
    """重复回调幂等处理：已 paid 的订单直接返回 SUCCESS"""
    order = payment_ctx["paid_order"]
    callback_body = json.dumps({
        "resource": {
            "out_trade_no": order.order_no,
            "transaction_id": "wx_idempotent_001",
            "trade_state": "SUCCESS",
            "amount": {"total": 1900},
        },
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
    assert resp.status_code == 200
    assert resp.json()["code"] == "SUCCESS"


@pytest.mark.asyncio
async def test_notify_order_not_found(client):
    """回调对应的订单不存在返回 404 FAIL"""
    callback_body = json.dumps({
        "resource": {
            "out_trade_no": "NONEXISTENT_ORDER",
            "transaction_id": "wx_not_found",
            "trade_state": "SUCCESS",
            "amount": {"total": 1900},
        },
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
    assert resp.status_code == 400
    assert resp.json()["code"] == "FAIL"


@pytest.mark.asyncio
async def test_notify_trade_state_not_success(client, payment_ctx, db_session):
    """回调 trade_state 非 SUCCESS 返回 FAIL"""
    from app.models.payment import Order

    pending_order = Order(
        user_id=payment_ctx["user"].id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0088",
        product_type="membership", amount_cents=1900,
        status="pending",
    )
    db_session.add(pending_order)
    await db_session.commit()
    await db_session.refresh(pending_order)

    callback_body = json.dumps({
        "resource": {
            "out_trade_no": pending_order.order_no,
            "transaction_id": "wx_not_success",
            "trade_state": "NOTPAY",
            "amount": {"total": 1900},
        },
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
    assert resp.json()["code"] == "FAIL"


@pytest.mark.asyncio
async def test_refund_only_paid_order(client, payment_ctx, db_session, admin_headers):
    """仅已支付订单可退款"""
    from app.models.payment import Order

    pending_order = Order(
        user_id=payment_ctx["user"].id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0080",
        product_type="membership", amount_cents=1900,
        status="pending",
    )
    db_session.add(pending_order)
    await db_session.commit()
    await db_session.refresh(pending_order)

    resp = await client.post(
        f"/api/v1/payment/orders/{pending_order.id}/refund",
        json={"refund_amount_cents": 1900, "reason": "测试"},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "已支付" in resp.json()["message"]


@pytest.mark.asyncio
async def test_refund_success(client, payment_ctx, admin_headers, db_session):
    """管理员退款成功"""
    resp = await client.post(
        f"/api/v1/payment/orders/{payment_ctx['paid_order'].id}/refund",
        json={"refund_amount_cents": 1900, "reason": "测试退款"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["refund_status"] == "pending"
    assert data["refund_amount_cents"] == 1900

    await db_session.refresh(payment_ctx["paid_order"])
    assert payment_ctx["paid_order"].status == "refunded"


@pytest.mark.asyncio
async def test_refund_expired_order(client, payment_ctx, db_session, admin_headers):
    """超过 7 天的订单不可退款"""
    from app.models.payment import Order

    old_order = Order(
        user_id=payment_ctx["user"].id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0077",
        product_type="membership", amount_cents=1900,
        status="paid",
        paid_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    db_session.add(old_order)
    await db_session.commit()
    await db_session.refresh(old_order)

    resp = await client.post(
        f"/api/v1/payment/orders/{old_order.id}/refund",
        json={"refund_amount_cents": 1900, "reason": "过期退款"},
        headers=admin_headers,
    )
    assert resp.status_code == 422
    assert "7天" in resp.json()["message"]


@pytest.mark.asyncio
async def test_payment_success_triggers_subscription(client, payment_ctx, db_session):
    """支付成功后创建 subscription"""
    from app.models.payment import Order
    from app.models.membership import Subscription
    from sqlalchemy import select

    pending_order = Order(
        user_id=payment_ctx["user"].id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0050",
        product_type="membership", amount_cents=1900,
        status="pending",
        extra_data={"tier": "member", "period_days": 30, "period": "monthly"},
    )
    db_session.add(pending_order)
    await db_session.commit()
    await db_session.refresh(pending_order)

    callback_body = json.dumps({
        "resource": {
            "out_trade_no": pending_order.order_no,
            "transaction_id": "wx_membership_001",
            "trade_state": "SUCCESS",
            "amount": {"total": 1900},
        },
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
    assert resp.status_code == 200
    assert resp.json()["code"] == "SUCCESS"

    # 验证 subscription 已创建
    from app.core.database import async_session_factory
    async with async_session_factory() as verify_session:
        result = await verify_session.execute(
        select(Subscription).where(Subscription.user_id == payment_ctx["user"].id)
    )
    subs = result.scalars().all()
    member_subs = [s for s in subs if s.tier == "member"]
    assert len(member_subs) >= 1
    assert member_subs[0].status == "active"