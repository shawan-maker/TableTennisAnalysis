# payment 模块 �?后端垂直切片设计

> **模块名称**：`payment`
> **所属目�?*：`app/api/v1/payment/` + `app/services/payment_service.py` + `app/models/payment.py` + `app/schemas/payment.py`
> **定位**：微信支付集成、订单管理、支付回调（APIv3 验签+解密）、退款、支付成功业务触�?
> **依据**：模块详细设�?v1.2 §2.11、API 详细设计 v1.3 §12、数据库详细设计 v1.5 §2.17-2.19

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.11（payment 模块功能规格�?
- [ ] 阅读 API 契约 §12�? 个端点：orders 创建/orders 列表/notify 回调/orders/{id}/refund 退款）
- [ ] 阅读 `app/models/payment.py`（Order + PaymentRecord + RefundRecord 模型�?
- [ ] 阅读 `app/models/membership.py`（Subscription 模型，支付成功后创建/续期�?
- [ ] 阅读 `app/core/config.py`（微信支付配置：WECHAT_MCH_ID / WECHAT_API_V3_KEY / WECHAT_CERT_SERIAL�?
- [ ] 确认本切片范围：4 �?API 端点 + 对应 Service 方法 + 微信支付 SDK 集成

### 任务清单

| # | 任务 | 文件 | 依赖 | 状�?|
|---|------|------|------|------|
| 1 | 定义 Model（Order + PaymentRecord + RefundRecord�?| `app/models/payment.py` | �?| �?|
| 2 | 注册 Model | `app/models/__init__.py` | #1 | �?|
| 3 | 生成 Alembic 迁移 | `alembic revision --autogenerate` | #2 | �?|
| 4 | 定义 Schema | `app/schemas/payment.py` | #1 | �?|
| 5 | 实现 Service | `app/services/payment_service.py` | #2,#4 | �?|
| 6 | 实现 API 路由 | `app/api/v1/payment/router.py` | #5 | �?|
| 7 | 注册 Router | `app/api/v1/__init__.py` | #6 | �?|
| 8 | 编写单元测试 | `tests/unit/test_payment.py` | #5 | �?|
| 9 | 编写冒烟测试 | `tests/smoke/payment_smoke_test.py` | #7 | �?|

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_payment.py
"""
payment 模块 �?支付流程测试�?
覆盖：订单创建、订单列表、微信回调验签解密、幂等处理、退款�?
"""
import pytest
import json
import uuid
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from app.core.exceptions import AppException

@pytest.fixture
async def payment_ctx(db_session, auth_user):
    """创建测试上下文：用户 + 订阅 + 订单�?""
    from app.models.payment import Order, PaymentRecord, RefundRecord
    from app.models.membership import Subscription

    user_id = auth_user["id"]
    now = datetime.now(timezone.utc)

    # 创建订阅
    subscription = Subscription(
        user_id=user_id,
        tier="free",
        status="active",
        start_at=now,
        expire_at=now,
    )
    db_session.add(subscription)
    await db_session.flush()

    # 创建已支付订单（用于测试列表和退款）
    paid_order = Order(
        user_id=user_id,
        subscription_id=subscription.id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0001",
        product_type="membership",
        amount_cents=1900,
        status="paid",
        paid_at=now,
    )
    db_session.add(paid_order)
    await db_session.flush()

    # 创建支付记录
    payment = PaymentRecord(
        order_id=paid_order.id,
        transaction_id=f"wx_{uuid.uuid4().hex[:16]}",
        payment_method="wechat_jsapi",
        amount_cents=1900,
        callback_raw={"transaction_id": "wx_test_001", "trade_state": "SUCCESS"},
    )
    db_session.add(payment)
    await db_session.flush()

    yield {
        "user": auth_user,
        "subscription": subscription,
        "paid_order": paid_order,
        "payment": payment,
    }
```

### 2.1 Happy Path（正常流程）

> **P3 文档同步（R12）**：下方为切片设计期的测试样例骨架。实际落地 `tests/unit/test_payment.py` 依赖全局 `WECHAT_PAY_MOCK=True` 开发模式（conftest）——验签/解密/微信下单走 Service 内 MOCK 短路，无需样例中的 `_verify_signature` / `_decrypt_callback` / `_call_wechat_unified_order` patch；`payment_ctx` fixture 基于 conftest 的 `test_user` + `seed_tiers`（样例中的 `auth_user` dict fixture 未落地）。覆盖面扩展：analysis_pack 下单、订单状态过滤、trade_state 非 SUCCESS、退款成功 / 超 7 天 422 等（18 测试全绿）；验签失败安全场景（R12-Payment-2）与 analysis_pack 额度 INCR + 幂等（R12-Payment-3）分别位于 `tests/unit/test_supplements_p1.py` / `tests/unit/test_supplements_p2.py`。

```python
# === 1. Happy Path ===
@pytest.mark.asyncio
async def test_create_order_success(client, auth_headers):
    """创建会员订单成功，返回支付参数�?""
    with patch('app.services.payment_service.PaymentService._call_wechat_unified_order',
               new_callable=AsyncMock, return_value={
                   "prepay_id": "wx_test_prepay_001",
                   "pay_sign": "test_sign",
                   "timestamp": "1234567890",
                   "nonce_str": "test_nonce",
               }):
        resp = await client.post("/api/v1/payment/orders", json={
            "product_type": "membership",
            "tier": "member",
            "period": "monthly",
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
async def test_list_orders_success(client, payment_ctx, auth_headers):
    """获取订单列表，返回分页结果�?""
    resp = await client.get("/api/v1/payment/orders", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["status"] == "paid"

@pytest.mark.asyncio
async def test_payment_notify_success(client, payment_ctx, db_session):
    """微信支付回调：验签通过 �?更新订单状�?�?触发业务逻辑�?""
    # 创建一�?pending 订单
    from app.models.payment import Order
    pending_order = Order(
        user_id=payment_ctx["user"].id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0099",
        product_type="membership",
        amount_cents=1900,
        status="pending",
    )
    db_session.add(pending_order)
    await db_session.flush()

    # 模拟微信回调请求
    callback_body = json.dumps({
        "id": "EV-TEST-001",
        "create_time": datetime.now(timezone.utc).isoformat(),
        "resource_type": "encrypt-resource",
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": "encrypted_data_placeholder",
            "nonce": "test_nonce_123",
            "associated_data": "transaction",
        },
    })

    # Mock 验签和解�?
    with patch('app.services.payment_service.PaymentService._verify_signature', return_value=True), \
         patch('app.services.payment_service.PaymentService._decrypt_callback', return_value={
             "transaction_id": "wx_notify_001",
             "out_trade_no": pending_order.order_no,
             "trade_state": "SUCCESS",
             "amount": {"total": 1900},
         }):
        resp = await client.post(
            "/api/v1/payment/notify",
            content=callback_body,
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "test_signature",
                "Wechatpay-Serial": "test_serial",
                "Wechatpay-Nonce": "test_nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["code"] == "SUCCESS"

    # 验证订单已更�?
    await db_session.refresh(pending_order)
    assert pending_order.status == "paid"
    assert pending_order.paid_at is not None
```

### 2.2 Validation Failure（参数校验失败）

```python
# === 2. Validation Failure ===
@pytest.mark.asyncio
async def test_create_order_invalid_product_type(client, auth_headers):
    """product_type 不在枚举中时返回 422�?""
    resp = await client.post("/api/v1/payment/orders", json={
        "product_type": "invalid_type",
        "tier": "member",
        "period": "monthly",
        "payment_method": "wechat_jsapi",
    }, headers=auth_headers)
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_create_order_missing_period_for_membership(client, auth_headers):
    """membership 类型缺少 period 参数返回 422�?""
    resp = await client.post("/api/v1/payment/orders", json={
        "product_type": "membership",
        "tier": "member",
        "payment_method": "wechat_jsapi",
    }, headers=auth_headers)
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_refund_amount_exceeds_order(client, payment_ctx, auth_headers, admin_headers):
    """退款金额超出订单金额返�?400�?""
    resp = await client.post(
        f"/api/v1/payment/orders/{payment_ctx['paid_order'].id}/refund",
        json={"refund_amount_cents": 999999, "reason": "测试"},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "不能超过" in resp.json()["message"]
```

### 2.3 Permission Denied（权限不足）

```python
# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_create_order_no_auth(client):
    """未登录创建订单返�?401�?""
    resp = await client.post("/api/v1/payment/orders", json={
        "product_type": "membership",
        "tier": "member",
        "period": "monthly",
        "payment_method": "wechat_jsapi",
    })
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_refund_non_admin(client, payment_ctx, auth_headers):
    """非管理员退款返�?403�?""
    resp = await client.post(
        f"/api/v1/payment/orders/{payment_ctx['paid_order'].id}/refund",
        json={"refund_amount_cents": 1900, "reason": "测试退�?},
        headers=auth_headers,
    )
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_list_orders_other_user(client, payment_ctx, auth_user2_headers):
    """用户只能看到自己的订单�?""
    resp = await client.get("/api/v1/payment/orders", headers=auth_user2_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 其他用户的订单列表不包含 payment_ctx 中的订单
    order_ids = [item["id"] for item in data["items"]]
    assert payment_ctx["paid_order"].id not in order_ids
```

### 2.4 Business Rule（业务规则验证）

```python
# === 4. Business Rule ===
@pytest.mark.asyncio
async def test_notify_idempotent(client, payment_ctx, db_session):
    """重复回调幂等处理：已 paid 的订单直接返�?SUCCESS�?""
    order = payment_ctx["paid_order"]
    callback_body = json.dumps({
        "id": "EV-TEST-IDEMPOTENT",
        "create_time": datetime.now(timezone.utc).isoformat(),
        "resource_type": "encrypt-resource",
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": "encrypted",
            "nonce": "nonce",
            "associated_data": "transaction",
        },
    })

    with patch('app.services.payment_service.PaymentService._verify_signature', return_value=True), \
         patch('app.services.payment_service.PaymentService._decrypt_callback', return_value={
             "transaction_id": "wx_idempotent_001",
             "out_trade_no": order.order_no,
             "trade_state": "SUCCESS",
             "amount": {"total": 1900},
         }):
        # 第一次回调（�?paid �?幂等返回�?
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
    # 订单状态不�?
    await db_session.refresh(order)
    assert order.status == "paid"

@pytest.mark.asyncio
async def test_notify_signature_failure(client):
    """验签失败返回 400 FAIL�?""
    with patch('app.services.payment_service.PaymentService._verify_signature', return_value=False):
        resp = await client.post(
            "/api/v1/payment/notify",
            content=json.dumps({"resource": {"ciphertext": "data"}}),
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "bad_sig",
                "Wechatpay-Serial": "serial",
                "Wechatpay-Nonce": "nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "FAIL"
    assert "签名" in resp.json()["message"]

@pytest.mark.asyncio
async def test_notify_order_not_found(client):
    """回调对应的订单不存在返回 400 FAIL（P3 文档同步（R12）：notify 端点 FAIL 统一 400）�?""
    with patch('app.services.payment_service.PaymentService._verify_signature', return_value=True), \
         patch('app.services.payment_service.PaymentService._decrypt_callback', return_value={
             "transaction_id": "wx_not_found",
             "out_trade_no": "NONEXISTENT_ORDER",
             "trade_state": "SUCCESS",
             "amount": {"total": 1900},
         }):
        resp = await client.post(
            "/api/v1/payment/notify",
            content=json.dumps({"resource": {"ciphertext": "data"}}),
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "sig",
                "Wechatpay-Serial": "serial",
                "Wechatpay-Nonce": "nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )
    # P3 文档同步（R12）：断言对齐实现 — notify 端点所有 FAIL 统一映射 400
    #（§6 路由样例 status_code = 200 if SUCCESS else 400；refund 端点的
    # 订单不存在才是 404 AppException）
    assert resp.status_code == 400
    assert resp.json()["code"] == "FAIL"

@pytest.mark.asyncio
async def test_payment_success_triggers_membership(client, payment_ctx, db_session):
    """支付成功后创�?续期 subscription�?""
    from app.models.payment import Order
    from app.models.membership import Subscription

    pending_order = Order(
        user_id=payment_ctx["user"].id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0050",
        product_type="membership",
        amount_cents=1900,
        status="pending",
    )
    db_session.add(pending_order)
    await db_session.flush()

    with patch('app.services.payment_service.PaymentService._verify_signature', return_value=True), \
         patch('app.services.payment_service.PaymentService._decrypt_callback', return_value={
             "transaction_id": "wx_membership_001",
             "out_trade_no": pending_order.order_no,
             "trade_state": "SUCCESS",
             "amount": {"total": 1900},
         }), \
         patch('app.services.payment_service.PaymentService._trigger_business_logic',
               new_callable=AsyncMock) as mock_trigger:
        await client.post(
            "/api/v1/payment/notify",
            content=json.dumps({"resource": {"ciphertext": "data"}}),
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "sig",
                "Wechatpay-Serial": "serial",
                "Wechatpay-Nonce": "nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )

    # 验证业务逻辑被触�?
    mock_trigger.assert_called_once()

@pytest.mark.asyncio
async def test_refund_only_paid_order(client, payment_ctx, db_session, admin_headers):
    """仅已支付订单可退款�?""
    from app.models.payment import Order

    pending_order = Order(
        user_id=payment_ctx["user"].id,
        order_no=f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}0080",
        product_type="membership",
        amount_cents=1900,
        status="pending",
    )
    db_session.add(pending_order)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/payment/orders/{pending_order.id}/refund",
        json={"refund_amount_cents": 1900, "reason": "测试"},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "已支�? in resp.json()["message"]
```

---

## 3. Model（SQLAlchemy 2.0�?

```python
# app/models/payment.py
"""订单与支付记录模型�?""

from sqlalchemy import BigInteger, String, Integer, ForeignKey, Index, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone

from app.core.database import Base


class Order(Base):
    """订单�?""

    __tablename__ = "order"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"),  # R19-P3-5: 移除冗余 index=True（__table_args__ idx_order_user_created 已覆盖）
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subscription.id", ondelete="SET NULL"), nullable=True,
    )
    order_no: Mapped[str] = mapped_column(String(64), unique=True, comment="订单�?)
    product_type: Mapped[str] = mapped_column(
        String(32), comment="membership/analysis_pack/equipment/tournament",  # R18-P3-4: 补充 tournament（§2.18 已定义）
    )
    product_ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, comment="金额(�?")
    status: Mapped[str] = mapped_column(
        String(20), default="pending",
        comment="pending/paid/refunded/cancelled",
    )
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    subscription: Mapped["Subscription | None"] = relationship(back_populates="orders")
    payments: Mapped[list["PaymentRecord"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_order_user_created", "user_id", "created_at"),
        Index("idx_order_status", "status"),
    )


class PaymentRecord(Base):
    """支付记录�?""

    __tablename__ = "payment_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("order.id", ondelete="CASCADE"),  # R19-P3-5: 移除冗余 index=True（__table_args__ idx_payment_order 已覆盖）
    )
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, comment="微信支付交易�?)
    payment_method: Mapped[str] = mapped_column(
        String(20), comment="wechat_jsapi/wechat_app",
    )
    amount_cents: Mapped[int] = mapped_column(Integer, comment="支付金额(�?")
    callback_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="验签后的回调明文")
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    order: Mapped["Order"] = relationship(back_populates="payments")

    __table_args__ = (
        Index("idx_payment_order", "order_id"),
    )


class RefundRecord(Base):
    """退款记录�?""

    __tablename__ = "refund_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("order.id", ondelete="CASCADE"))
    refund_no: Mapped[str] = mapped_column(String(64), unique=True)
    refund_amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reversal_type: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="退款类�? full/full_reversal/partial")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    callback_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_refund_order", "order_id"),  # R18-P2-7: 索引命名对齐 §5/§6
    )
```

**实现后必�?*�?
- [ ] �?`app/models/__init__.py` 中导入：`from app.models.payment import Order, PaymentRecord, RefundRecord`
- [ ] 生成 Alembic 迁移：`alembic revision --autogenerate -m "add order, payment_record and refund_record"`
- [ ] 执行迁移：`alembic upgrade head`

---

## 4. Schema（Pydantic�?

```python
# app/schemas/payment.py
"""支付模块 Schema�?""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime, timezone
from app.core.pagination import Paginated


# --- 请求 Schema ---
class OrderCreateRequest(BaseModel):
    """创建订单请求�?""
    product_type: Literal["membership", "analysis_pack"] = Field(
        ..., description="产品类型",
    )
    tier: Optional[str] = Field(default=None, description="会员等级：member/pro/coach")
    period: Optional[str] = Field(
        default=None, description="订阅周期：monthly/quarterly/yearly",
    )
    quantity: Optional[int] = Field(default=1, ge=1, description="分析次数包数�?)
    payment_method: Literal["wechat_jsapi", "wechat_app"] = Field(
        default="wechat_jsapi", description="支付方式",
    )


class RefundRequest(BaseModel):
    """退款请求�?""
    refund_amount_cents: int = Field(..., gt=0, description="退款金额（分）")
    reason: str = Field(..., min_length=1, max_length=500, description="退款原�?)


# --- 响应 Schema ---
class PaymentParams(BaseModel):
    """微信支付参数�?""
    prepay_id: str
    pay_sign: str
    timestamp: str
    nonce_str: str


class OrderCreateResponse(BaseModel):
    """创建订单响应�?""
    order_id: int
    order_no: str
    amount_cents: int
    payment_params: PaymentParams
    model_config = {"from_attributes": True}


class OrderBrief(BaseModel):
    """订单摘要�?""
    id: int
    order_no: str
    product_type: str
    amount_cents: int
    status: str
    created_at: datetime
    paid_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


PaginatedOrders = Paginated[OrderBrief]


class RefundResponse(BaseModel):
    """退款响应�?""
    order_id: int
    refund_status: str
    refund_amount_cents: int


# --- 微信回调相关 ---
class WechatNotifyResponse(BaseModel):
    """微信回调响应（非统一响应格式）�?""
    code: str = "SUCCESS"
    message: str = "成功"
```

---

## 5. Service（@staticmethod�?

```python
# app/services/payment_service.py
"""支付业务逻辑层�?""

import uuid
import json
import logging
import time
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# P3 文档同步（R12）：import 对齐实现 — 移除未使用的 hmac/hashlib，
# 补 logging / time（WECHAT_PAY_MOCK 开发模式短路分支使用）

logger = logging.getLogger(__name__)

import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.pagination import paginate
from app.models.payment import Order, PaymentRecord, RefundRecord
from app.models.membership import Subscription
from app.models.admin import AuditLog
from app.schemas.payment import (
    OrderCreateRequest, OrderCreateResponse, OrderBrief, PaginatedOrders,
    PaymentParams, RefundRequest, RefundResponse,
)

# 会员定价从 DB MembershipTierConfig 表动态查询，不再硬编码

# 分析次数包定�?
ANALYSIS_PACK_PRICING = {1: 1500, 3: 3900, 10: 9900}

# 订阅周期映射
PERIOD_DELTA = {
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=90),
    "yearly": timedelta(days=365),
}


class PaymentService:
    """支付业务逻辑层�?""

    WECHAT_UNIFIED_ORDER_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"
    WECHAT_REFUND_URL = "https://api.mch.weixin.qq.com/v3/refund/domestic/refunds"

    # ==================== 订单创建 ====================

    @staticmethod
    async def create_order(
        user_id: int, req: OrderCreateRequest,
        ip_address: str | None = None, user_agent: str | None = None,
    ) -> OrderCreateResponse:
        """
        创建订单 �?调用微信统一下单 �?返回支付参数�?
        权限：登录用户�?
        """
        # 生成订单号
        order_no = f"PP{datetime.now(timezone.utc).strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"

        async with async_session_factory() as db:
            # 计算金额（从 DB MembershipTierConfig 查询定价）
            amount_cents = await PaymentService._calculate_amount(db, req)
            # 构建订单 extra_data（供支付成功后业务逻辑使用，避免硬编码�?
            if req.product_type == "membership":
                period_days = int(PERIOD_DELTA.get(req.period, timedelta(days=30)).total_seconds() // 86400)
                extra_data = {"tier": req.tier, "period_days": period_days, "period": req.period}
            elif req.product_type == "analysis_pack":
                extra_data = {"quantity": req.quantity or 1}
            else:
                extra_data = None

            order = Order(
                user_id=user_id,
                order_no=order_no,
                product_type=req.product_type,
                amount_cents=amount_cents,
                status="pending",
                extra_data=extra_data,
            )
            db.add(order)
            await db.flush()

            # 调用微信统一下单
            try:
                wx_params = await PaymentService._call_wechat_unified_order(
                    order_no=order_no,
                    amount_cents=amount_cents,
                    description=PaymentService._get_product_description(req),
                    user_id=user_id,
                    payment_method=req.payment_method,
                )
            except AppException:
                await db.delete(order)
                await db.commit()
                raise
            except Exception as e:
                await db.delete(order)
                await db.commit()
                raise AppException(f"支付服务暂时不可�? {str(e)}", 502)

            # 审计日志：记录订单创建
            audit_entry = AuditLog(
                user_id=user_id,
                action="payment_order_created",
                target_type="order",
                target_id=order.id,
                detail=json.dumps({
                    "amount": amount_cents,
                    "product_type": req.product_type,
                    "tier": req.tier,
                    "user_agent": user_agent,
                }),
                ip_address=ip_address,
            )
            db.add(audit_entry)

            await db.commit()
            await db.refresh(order)

            return OrderCreateResponse(
                order_id=order.id,
                order_no=order.order_no,
                amount_cents=order.amount_cents,
                payment_params=PaymentParams(
                    prepay_id=wx_params["prepay_id"],
                    pay_sign=wx_params["pay_sign"],
                    timestamp=wx_params["timestamp"],
                    nonce_str=wx_params["nonce_str"],
                ),
            )

    @staticmethod
    async def _calculate_amount(db, req: OrderCreateRequest) -> int:
        """根据产品类型计算金额（分），会员定价从 DB MembershipTierConfig 查询。"""
        if req.product_type == "membership":
            if not req.tier or not req.period:
                raise AppException("会员等级或周期参数不合法", 422)
            from app.models.membership import MembershipTierConfig
            from sqlalchemy import select
            result = await db.execute(
                select(MembershipTierConfig).where(MembershipTierConfig.tier == req.tier)
            )
            tier_config = result.scalar_one_or_none()
            if not tier_config:
                raise AppException("会员等级或周期参数不合法", 422)
            price_map = {
                "monthly": tier_config.price_monthly_cents,
                "quarterly": tier_config.price_quarterly_cents,
                "yearly": tier_config.price_yearly_cents,
            }
            amount = price_map.get(req.period)
            if not amount:
                raise AppException("会员等级或周期参数不合法", 422)
            return amount

        elif req.product_type == "analysis_pack":
            qty = req.quantity or 1
            amount = ANALYSIS_PACK_PRICING.get(qty)
            if not amount:
                raise AppException("分析次数包数量不合法", 422)
            return amount

        else:
            raise AppException("产品类型不合�?, 422)

    @staticmethod
    def _get_product_description(req: OrderCreateRequest) -> str:
        """生成产品描述�?""
        if req.product_type == "membership":
            return f"乒乓智能分析-{req.tier}会员-{req.period}"
        elif req.product_type == "analysis_pack":
            return f"乒乓智能分析-分析次数包x{req.quantity}"
        return "乒乓智能分析"

    @staticmethod
    async def _call_wechat_unified_order(
        order_no: str,
        amount_cents: int,
        description: str,
        user_id: int,
        payment_method: str,
    ) -> dict:
        """
        调用微信统一下单 API（V3）。
        返回 {prepay_id, pay_sign, timestamp, nonce_str}。
        MOCK 模式返回模拟参数（开发模式，见文件头声明）。
        """
        # P3 文档同步（R12）：WECHAT_PAY_MOCK 开发模式短路（与实现一致）
        if settings.WECHAT_PAY_MOCK:
            logger.info("MOCK wechat unified order: order_no=%s", order_no)
            return {
                "prepay_id": f"mock_prepay_{uuid.uuid4().hex[:16]}",
                "pay_sign": "mock_sign_" + uuid.uuid4().hex[:16],
                "timestamp": str(int(time.time())),
                "nonce_str": uuid.uuid4().hex,
            }

        # 获取用户 openid（从 user 表）
        from app.models.user import User
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user or not user.openid:
                raise AppException("用户信息不完整，无法发起支付", 400)

        # 构建微信下单请求
        payload = {
            "appid": settings.WECHAT_APPID,
            "mchid": settings.WECHAT_MCH_ID,
            "description": description,
            "out_trade_no": order_no,
            "notify_url": settings.WECHAT_NOTIFY_URL,
            "amount": {"total": amount_cents, "currency": "CNY"},
            "payer": {"openid": user.openid},
        }

        headers = PaymentService._build_wechat_headers("POST", "/v3/pay/transactions/jsapi")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                PaymentService.WECHAT_UNIFIED_ORDER_URL,
                json=payload,
                headers=headers,
                timeout=15,
            )

        if resp.status_code != 200:
            error_data = resp.json()
            raise AppException(
                f"微信统一下单失败: {error_data.get('message', 'unknown')}",
                502,
            )

        data = resp.json()
        prepay_id = data.get("prepay_id")
        if not prepay_id:
            raise AppException("微信下单返回异常", 502)

        # 生成小程序支付签�?
        import time
        # P3 文档同步（R12）：移除未使用的 import random（time 已在顶部导入）
        timestamp = str(int(time.time()))
        nonce_str = uuid.uuid4().hex
        package = f"prepay_id={prepay_id}"

        # 签名: RSA-SHA256(appid\ntimestamp\nnonce_str\npackage\n)
        sign_str = f"{settings.WECHAT_APPID}\n{timestamp}\n{nonce_str}\n{package}\n"
        pay_sign = PaymentService._rsa_sign(sign_str)

        return {
            "prepay_id": prepay_id,
            "pay_sign": pay_sign,
            "timestamp": timestamp,
            "nonce_str": nonce_str,
        }

    @staticmethod
    def _build_wechat_headers(method: str, url: str) -> dict:
        """构建微信 API 请求头（含签名）�?""
        import time
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        # 签名�? method\nurl\ntimestamp\nnonce\nbody\n
        sign_str = f"{method}\n{url}\n{timestamp}\n{nonce}\n\n"
        signature = PaymentService._rsa_sign(sign_str)
        auth = f'WECHATPAY2-SHA256-RSA2048 mchid="{settings.WECHAT_MCH_ID}",nonce_str="{nonce}",timestamp="{timestamp}",serial_no="{settings.WECHAT_CERT_SERIAL}",signature="{signature}"'
        return {
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _rsa_sign(data: str) -> str:
        """RSA-SHA256 签名�?""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        private_key_pem = settings.WECHAT_PRIVATE_KEY.encode()
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
        signature = private_key.sign(
            data.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()

    # ==================== 订单列表 ====================

    @staticmethod
    async def list_orders(
        user_id: int,
        status: Optional[str] = None,
        product_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedOrders:
        """获取当前用户订单列表。权限：登录用户（仅查看自己的订单）�?""
        async with async_session_factory() as db:
            stmt = select(Order).where(Order.user_id == user_id)
            if status:
                stmt = stmt.where(Order.status == status)
            if product_type:
                stmt = stmt.where(Order.product_type == product_type)
            stmt = stmt.order_by(desc(Order.created_at))

            total, items = await paginate(db, stmt, page, page_size)
            return PaginatedOrders(
                total=total, page=page, page_size=page_size,
                items=[OrderBrief.model_validate(o) for o in items],
            )

    # ==================== 微信支付回调 ====================

    @staticmethod
    async def handle_notify(
        signature: str,
        serial: str,
        nonce: str,
        timestamp: str,
        body: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """
        微信支付异步回调处理（V3 APIv3）�?
        权限：微信签名（APIv3 证书验证）�?
        返回微信要求的响应格式（非统一响应格式）�?
        """
        # 1. 验签
        if not await PaymentService._verify_signature(signature, serial, nonce, timestamp, body):
            return {"code": "FAIL", "message": "签名验证失败"}

        # 2. 解析回调 body
        try:
            callback = json.loads(body)
        except json.JSONDecodeError:
            return {"code": "FAIL", "message": "回调数据格式错误"}

        # 3. 解密
        resource = callback.get("resource", {})
        try:
            decrypted = PaymentService._decrypt_callback(resource)
        except Exception:
            return {"code": "FAIL", "message": "解密失败"}

        # 4. 查找订单
        out_trade_no = decrypted.get("out_trade_no")
        trade_state = decrypted.get("trade_state")
        transaction_id = decrypted.get("transaction_id")
        amount_total = decrypted.get("amount", {}).get("total")

        async with async_session_factory() as db:
            result = await db.execute(
                select(Order).where(Order.order_no == out_trade_no)
            )
            order = result.scalar_one_or_none()

            if not order:
                return {"code": "FAIL", "message": "订单不存�?}

            # 5. 幂等处理：已 paid �?直接返回 SUCCESS
            if order.status == "paid":
                return {"code": "SUCCESS", "message": "成功"}

            # 6. 验证交易状�?
            if trade_state != "SUCCESS":
                return {"code": "FAIL", "message": f"交易状态异�? {trade_state}"}

            # 7. 更新订单状�?
            order.status = "paid"
            order.paid_at = datetime.now(timezone.utc)

            # 8. 创建支付记录
            # P3 文档同步（R12）：补 paid_at=datetime.now(timezone.utc) —
            # PaymentRecord.paid_at 为非 nullable 字段（§3 模型定义），缺失时插入必失败
            payment = PaymentRecord(
                order_id=order.id,
                transaction_id=transaction_id,
                payment_method="wechat_jsapi",
                amount_cents=amount_total or order.amount_cents,
                callback_raw=decrypted,
                paid_at=datetime.now(timezone.utc),
            )
            db.add(payment)

            # 9. 触发业务逻辑
            await PaymentService._trigger_business_logic(db, order, ip_address=ip_address)

            # 审计日志：记录支付回调处理
            audit_entry = AuditLog(
                user_id=order.user_id,
                action="payment_callback_processed",
                target_type="order",
                target_id=order.id,
                detail=json.dumps({
                    "transaction_id": transaction_id,
                    "amount": amount_total or order.amount_cents,
                    "status": order.status,
                    "user_agent": user_agent,
                }),
                ip_address=ip_address,
            )
            db.add(audit_entry)

            await db.commit()

            # 10. 显式调用通知模块推送支付成功通知
            # F6-2 修复：通知调用路径 handle_notify �?_push_payment_success_ws �?NotificationService.push_ws_message
            # P3 文档同步（R12）：推送包裹 try/except — 通知失败仅记录日志，
            # 不影响回调成功返回（微信要求 200 SUCCESS），与注释语义对齐
            try:
                await PaymentService._push_payment_success_ws(order.user_id, order.id, order.product_type)
            except Exception as e:
                logger.warning("push payment success ws failed: %s", e)

            return {"code": "SUCCESS", "message": "成功"}

    @staticmethod
    async def _verify_signature(
        signature: str, serial: str, nonce: str, timestamp: str, body: str,
    ) -> bool:
        """
        验证微信支付回调签名�?
        用微信支付平台证书验�?Wechatpay-Signature�?
        签名内容: timestamp\nnonce\nbody\n
        MOCK 模式直接返回 True（开发模式，见文件头声明）。
        """
        # P3 文档同步（R12）：WECHAT_PAY_MOCK 开发模式短路（与实现一致）
        if settings.WECHAT_PAY_MOCK:
            return True

        # 构建签名内容
        sign_str = f"{timestamp}\n{nonce}\n{body}\n"

        # 获取平台证书公钥（通过 serial 查找本地缓存的平台证书）
        # 实际实现中：�?Redis 或本地文件读取平台证书公�?
        cert_pubkey = PaymentService.await PaymentService._get_wechat_platform_cert(serial)
        if not cert_pubkey:
            return False

        # RSA-SHA256 验签
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.serialization import load_pem_public_key

            pub_key = load_pem_public_key(cert_pubkey.encode())
            signature_bytes = base64.b64decode(signature)
            pub_key.verify(
                signature_bytes,
                sign_str.encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    @staticmethod
    async def _get_wechat_platform_cert(serial: str) -> Optional[str]:
        """�?Redis 获取微信平台证书公钥（PEM 格式）�?""
        try:
            redis = await get_redis()
            return await redis.get(f"wechat:platform_cert:{serial}")
        except Exception:
            return None

    # R19-P3-D: WECHAT_API_V3_KEY 来源于 app/core/config.py pydantic-settings 加载（环境变量 WECHAT_API_V3_KEY），密钥轮换流程见架构 §14.2（180天轮换）
    @staticmethod
    def _decrypt_callback(resource: dict) -> dict:
        """
        解密微信回调 ciphertext�?
        使用商户 APIv3 密钥�?2 字节）作�?AES-256-GCM 密钥�?
        """
        # P3 文档同步（R12）：WECHAT_PAY_MOCK 开发模式短路（与实现一致）
        # MOCK 模式：resource 本身就是明文，直接返回
        if settings.WECHAT_PAY_MOCK:
            return resource

        ciphertext = resource.get("ciphertext", "")
        nonce = resource.get("nonce", "")
        associated_data = resource.get("associated_data", "")

        # Base64 解码 ciphertext
        ciphertext_bytes = base64.b64decode(ciphertext)

        # AES-256-GCM 解密
        api_v3_key = settings.WECHAT_API_V3_KEY.encode()  # 32 字节密钥
        aesgcm = AESGCM(api_v3_key)
        decrypted = aesgcm.decrypt(
            nonce=nonce.encode(),
            data=ciphertext_bytes,
            associated_data=associated_data.encode() if associated_data else None,
        )
        return json.loads(decrypted.decode())

    @staticmethod
    async def _trigger_business_logic(db: AsyncSession, order: Order, ip_address: str | None = None):
        """支付成功后根据订单类型触发对应业务逻辑�?""
        # F4-1 修复：order 更新 + payment_record + subscription 创建在同一事务�?        # WS 推送在事务提交后执行，失败时仅记录日志
        # 补偿机制：Celery Beat 定时扫描 status=paid 但无 subscription �?order，重试业务逻辑
        if order.product_type == "membership":
            # 创建/续期 subscription
            # 获取订单�?extra_data（tier/period�?
            # �?order �?product_type 和关联数据推�?
            # 实际实现中需要从 order 创建时的参数获取
            await PaymentService._create_or_renew_subscription(db, order, ip_address=ip_address)

        elif order.product_type == "analysis_pack":
            # 增加额外额度（Redis INCR�?
            redis = await get_redis()
            extra = order.extra_data or {}
            bonus_qty = extra.get("quantity", 1)
            await redis.incrby(f"quota:bonus:{order.user_id}", bonus_qty)
            # 设置 90 �?TTL，避�?bonus 额度永久驻留 Redis
            await redis.expire(f"quota:bonus:{order.user_id}", 7776000)  # 90 days = 90 * 24 * 3600

    @staticmethod
    async def _create_or_renew_subscription(db: AsyncSession, order: Order, ip_address: str | None = None):
        """创建或续期会员订阅�?""
        # �?order.extra_data 获取 tier �?period_days（避免硬编码�?
        extra = order.extra_data or {}
        tier = extra.get("tier", "member")
        period_days = extra.get("period_days", 30)

        # 查找用户当前活跃订阅
        # P3 文档同步（R12）：查询条件加入 grace_period（R6-Pay-1：宽限期内
        # 续费应续期既有订阅而非新建重复订阅）；取数改为 order_by created_at
        # desc + limit(1) + scalars().first() —— scalar_one_or_none 在用户存在
        # 多条历史订阅时会抛 MultipleResultsFound
        result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == order.user_id,
                # R6-Pay-1: 加入 grace_period，避免用户在宽限期内续费时创建重复订阅
                Subscription.status.in_(["active", "expiring_soon", "grace_period"]),
            ).order_by(Subscription.created_at.desc()).limit(1)
        )
        existing = result.scalars().first()

        now = datetime.now(timezone.utc)

        if existing:
            # 续期：从当前到期时间或现在开始续期
            start = max(existing.expire_at, now) if existing.expire_at else now
            existing.expire_at = start + timedelta(days=period_days)
            existing.status = "active"
            existing.tier = tier  # P3 文档同步（R12）：更新等级（可能从 free 升级为 member）
            # R12-Payment-1: 续期分支回填 order.subscription_id（退款撤销权益依赖）
            order.subscription_id = existing.id
            subscription_id = existing.id
        else:
            # 新建订阅
            sub = Subscription(
                user_id=order.user_id,
                tier=tier,
                status="active",
                start_at=now,
                expire_at=now + timedelta(days=period_days),
            )
            db.add(sub)
            await db.flush()
            order.subscription_id = sub.id
            subscription_id = sub.id

        # 审计日志：记录订阅创建或续期
        # P3 文档同步（R12）：detail 字段对齐实现 — 仅 tier / period 两键
        #（原样例的 sub_start / sub_expire 临时变量已移除）
        audit_entry = AuditLog(
            user_id=order.user_id,
            action="subscription_created_or_renewed",
            target_type="subscription",
            target_id=subscription_id,
            detail=json.dumps({
                "tier": tier,
                "period": extra.get("period", "monthly"),
            }),
            ip_address=ip_address,
        )
        db.add(audit_entry)

    @staticmethod
    async def _push_payment_success_ws(
        user_id: int, order_id: int, product_type: str,
    ):
        """通过 WebSocket 推送支付成功通知�?""
        from app.services.notification_service import NotificationService
        await NotificationService.push_ws_message(
            user_id=user_id,
            event_type="payment_success",
            data={"order_id": order_id, "product_type": product_type},
        )

    # ==================== 退�?====================

    @staticmethod
    async def refund(
        order_id: int, refund_amount_cents: int, reason: str,
        operator_id: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RefundResponse:
        """申请退款（管理员操作）"""
        async with async_session_factory() as db:
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()

            if not order:
                raise AppException("订单不存�?, 404)

            if order.status != "paid":
                raise AppException("仅已支付订单可退�?, 400)

            if refund_amount_cents > order.amount_cents:
                raise AppException("退款金额不能超过订单金�?, 400)

            # 退款时间窗口校验
            if order.paid_at:
                elapsed = datetime.now(timezone.utc) - order.paid_at
                if elapsed > timedelta(days=7):
                    raise AppException("超过7天的订单不可退款", 422)
                # 24h 内可全额退款；24h-7d 仅支持部分退款且不可超过订单金额 50%
                if refund_amount_cents < order.amount_cents:
                    reversal_type = "partial"
                    # R4-Pay-2: 24h-7d 部分退款限额校验
                    if elapsed > timedelta(hours=24):
                        if refund_amount_cents > order.amount_cents * 0.5:
                            raise AppException(
                                "24小时至7天内退款不可超过50%", 400,
                            )
                elif elapsed <= timedelta(hours=24):
                    reversal_type = "full"
                else:
                    reversal_type = "full_reversal"
            else:
                reversal_type = "full"

            refund_no = f"RF{datetime.now(timezone.utc).strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"

            # 调用微信退�?API
            try:
                wx_resp = await PaymentService._call_wechat_refund(
                    order_no=order.order_no,
                    refund_no=refund_no,
                    refund_amount_cents=refund_amount_cents,
                    total_amount_cents=order.amount_cents,
                    reason=reason,
                )
            except AppException:
                raise
            except Exception as e:
                raise AppException(f"退款服务暂时不可用: {str(e)}", 502)

            # 创建退款记�?
            refund_record = RefundRecord(
                order_id=order.id,
                refund_no=refund_no,
                refund_amount_cents=refund_amount_cents,
                reason=reason,
                status="pending",
                reversal_type=reversal_type,
                operator_id=operator_id,
                callback_raw=wx_resp,
            )
            db.add(refund_record)

            order.status = "refunded"
            audit_entry = AuditLog(
                admin_id=None,  # JWT 管理员无 AdminUser 记录，admin_id 留空
                user_id=operator_id,  # 操作者 user_id（JWT 认证用户）
                action="refund",
                target_type="order",
                target_id=order.id,
                detail=json.dumps({
                    "refund_amount": refund_amount_cents,
                    "operator_id": operator_id,
                    "reason": reason,
                    "user_agent": user_agent,
                }),
                ip_address=ip_address,
            )
            db.add(audit_entry)

            await db.commit()
            # 退款后撤销会员权益
            # R6-Pay-2: refund 已提交，revoke 跨事务调用，失败时仅记录日志
            # TODO: 增加补偿机制（如投递重试队列），确保退款后权益撤销最终一致
            try:
                if order.product_type == "membership":
                    from app.services.membership_service import MembershipService
                    if order.subscription_id:
                        await MembershipService.revoke_subscription(db, order.subscription_id)
                    else:
                        # R12 复验补充：续期回填（R12-Payment-1）生效前的历史订单
                        # subscription_id 为空，退款后无法定位订阅 — 记告警日志便于人工补偿
                        logger.error(
                            "refund_membership_order_missing_subscription_id: "
                            "order_id=%s user_id=%s — 历史订单（回填修复前创建），"
                            "权益撤销被跳过，需人工核实会员状态",
                            order.id, order.user_id,
                        )
            except Exception as e:
                logger.error(
                    "Failed to revoke subscription %s after refund: %s",
                    order.subscription_id, e,
                )
            return RefundResponse(
                order_id=order.id,
                refund_status="pending",
                refund_amount_cents=refund_amount_cents,
            )

    @staticmethod
    async def _call_wechat_refund(
        order_no: str,
        refund_no: str,
        refund_amount_cents: int,
        total_amount_cents: int,
        reason: str,
    ) -> dict:
        """调用微信退款 API。MOCK 模式返回模拟响应。"""
        if settings.WECHAT_PAY_MOCK:
            logger.info("MOCK wechat refund: refund_no=%s", refund_no)
            return {
                "refund_id": f"mock_refund_{uuid.uuid4().hex[:16]}",
                "status": "PROCESSING",
            }
        payload = {
            "transaction_id": "",  # �?out_trade_no
            "out_trade_no": order_no,
            "out_refund_no": refund_no,
            "reason": reason,
            "amount": {
                "refund": refund_amount_cents,
                "total": total_amount_cents,
                "currency": "CNY",
            },
        }

        headers = PaymentService._build_wechat_headers("POST", "/v3/refund/domestic/refunds")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                PaymentService.WECHAT_REFUND_URL,
                json=payload,
                headers=headers,
                timeout=15,
            )

        if resp.status_code != 200:
            error_data = resp.json()
            raise AppException(
                f"微信退款失�? {error_data.get('message', 'unknown')}",
                502,
            )

        return resp.json()
```

---

## 6. API 路由（FastAPI�?

```python
# app/api/v1/payment/router.py
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.deps import get_current_user, get_current_admin
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.schemas.payment import (
    OrderCreateRequest, RefundRequest,
)
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payment", tags=["支付"])


@router.post("/orders", summary="创建订单")
@limiter.limit("100/minute")
async def create_order(
    body: OrderCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """创建订单（会员订阅/分析次数包），返回微信支付参数"""
    data = await PaymentService.create_order(
        user.id, body,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return success(data=data, message="订单已创建")


@router.get("/orders", summary="订单列表")
@limiter.limit("100/minute")
async def list_orders(
    request: Request,
    status: str | None = Query(default=None, description="状态过滤"),
    product_type: str | None = Query(default=None, description="产品类型过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """获取当前用户订单列表（分页）"""
    data = await PaymentService.list_orders(
        user_id=user.id,
        status=status,
        product_type=product_type,
        page=page,
        page_size=page_size,
    )
    return success(data=data)


# SEC-006: 微信回调不被限流（微信服务器需要立即收到响应）
@router.post("/notify", summary="微信支付回调")
async def payment_notify(
    request: Request,
):
    """
    微信支付异步回调（V3 APIv3）。
    权限：微信签名验证（无需 JWT）。
    返回微信要求的响应格式（非统一响应格式）。
    """
    signature = request.headers.get("Wechatpay-Signature", "")
    serial = request.headers.get("Wechatpay-Serial", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    timestamp = request.headers.get("Wechatpay-Timestamp", "")

    body = (await request.body()).decode()

    result = await PaymentService.handle_notify(
        signature=signature,
        serial=serial,
        nonce=nonce,
        timestamp=timestamp,
        body=body,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    status_code = 200 if result.get("code") == "SUCCESS" else 400
    return JSONResponse(
        status_code=status_code,
        content=result,
    )


@router.post("/orders/{order_id}/refund", summary="申请退款")
@limiter.limit("100/minute")
async def refund_order(
    order_id: int,
    body: RefundRequest,
    request: Request,
    user: User = Depends(get_current_admin),
):
    """申请退款（管理员操作 — JWT 认证）"""
    data = await PaymentService.refund(
        order_id=order_id,
        refund_amount_cents=body.refund_amount_cents,
        reason=body.reason,
        operator_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return success(data=data, message="退款申请已提交")
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.payment.router import router as payment_router
api_router.include_router(payment_router)
```

---

## 7. 冒烟测试脚本

```python
# tests/smoke/payment_smoke_test.py
"""
payment 模块冒烟测试�?
用法: python -m tests.smoke.payment_smoke_test
"""
import httpx
import asyncio
import json

BASE_URL = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 登录获取 Token
        print("0. Login...")
        login_resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "payment_smoke",
        })
        if login_resp.status_code != 200:
            print(f"   �?Login failed: {login_resp.status_code}")
            return
        token = login_resp.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        print("   �?Login success")

        # 2. 创建订单（会员月卡）
        print("1. Testing POST /payment/orders (membership)...")
        resp = await client.post("/payment/orders", json={
            "product_type": "membership",
            "tier": "member",
            "period": "monthly",
            "payment_method": "wechat_jsapi",
        }, headers=h)
        # 微信下单在测试环境可能失败（502），但订单创建逻辑应正�?
        if resp.status_code == 200:
            order_data = resp.json()["data"]
            print(f"   �?Order created: id={order_data['order_id']}, no={order_data['order_no']}")
            assert order_data["amount_cents"] == 1900
        elif resp.status_code == 502:
            print(f"   ~ Order created but WeChat API unavailable (expected in smoke test)")
        else:
            print(f"   �?Order creation failed: {resp.status_code} - {resp.text}")
            return

        # 3. 获取订单列表
        print("2. Testing GET /payment/orders...")
        resp = await client.get("/payment/orders", headers=h)
        assert resp.status_code == 200, f"List orders failed: {resp.text}"
        order_list = resp.json()["data"]
        print(f"   �?Orders: total={order_list['total']}, items={len(order_list['items'])}")

        # 4. 按状态筛�?
        print("3. Testing GET /payment/orders?status=pending...")
        resp = await client.get("/payment/orders?status=pending", headers=h)
        assert resp.status_code == 200
        print(f"   �?Pending orders: {resp.json()['data']['total']}")

        # 5. 测试回调端点（不验签，预期返�?FAIL�?
        print("4. Testing POST /payment/notify (bad signature)...")
        callback_body = json.dumps({
            "id": "EV-SMOKE-001",
            "resource": {"ciphertext": "test", "nonce": "test", "associated_data": "transaction"},
        })
        resp = await client.post(
            "/payment/notify",
            content=callback_body,
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "bad_signature",
                "Wechatpay-Serial": "bad_serial",
                "Wechatpay-Nonce": "test_nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )
        # 验签失败应返�?400 + FAIL
        assert resp.status_code == 400, f"Notify expected 400, got {resp.status_code}"
        assert resp.json()["code"] == "FAIL"
        print(f"   �?Notify rejected (signature verification failed as expected)")

        # 6. 测试退款权限（非管理员�?
        print("5. Testing POST /payment/orders/{id}/refund (non-admin)...")
        if order_list["items"]:
            order_id = order_list["items"][0]["id"]
            resp = await client.post(
                f"/payment/orders/{order_id}/refund",
                json={"refund_amount_cents": 100, "reason": "smoke test"},
                headers=h,
            )
            # 非管理员应返�?403
            assert resp.status_code == 403, f"Refund expected 403, got {resp.status_code}"
            print(f"   �?Refund rejected (non-admin as expected)")

    print("\npayment_smoke_test: ALL PASSED �?)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_payment.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.payment_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导入（�?`Order`、`PaymentRecord`、`RefundRecord`�?- [ ] Router 已在 `app/api/v1/__init__.py` 中注�?- [ ] Alembic 迁移已生成并执行
- [ ] 微信支付配置正确（WECHAT_APPID / WECHAT_MCH_ID / WECHAT_API_V3_KEY / WECHAT_CERT_SERIAL / WECHAT_PRIVATE_KEY�?- [ ] 回调端点 `/payment/notify` 不需�?JWT 鉴权（微信直接调用）
- [ ] 回调响应格式为微信要求格式（`{code, message}`，非统一响应格式�?
- [ ] 回调验签正确（APIv3 证书验证 + RSA-SHA256�?
- [ ] 回调解密正确（AEAD_AES_256_GCM + APIv3 密钥�?
- [ ] 重复回调幂等处理（检�?order.status �?paid �?直接返回 SUCCESS�?
- [ ] 支付成功后业务逻辑触发（membership �?创建/续期 subscription，analysis_pack �?Redis INCR�?
- [ ] WS 推�?payment_success 通知
- [ ] 退款权限：仅管理员可操作（`get_current_admin`�?
- [ ] 退款校验：订单状态为 paid + 退款金额 ≤ 订单金额 + 7 天窗口（24h 内全额、24h-7d 仅部分退款且 ≤ 50%、超 7 天拒绝 — R4-Pay-2）
- [ ] 退款创�?RefundRecord 记录（refund_no / refund_amount_cents / reason / status / operator_id�?
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释�?
- [ ] 无废话注释、无注释掉的死代�?

---

## 反幻觉约�?

- Service 方法 **必须** 使用 `@staticmethod`�?*禁止** 创建实例
- Schema **必须** 遵循命名：`OrderCreateRequest`、`OrderBrief`、`OrderCreateResponse`、`PaginatedOrders`
- **禁止** �?API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- 微信 API 调用 **必须** 设置超时�?5s�?
- 回调验签 **必须** 使用微信支付平台证书（通过 `Wechatpay-Serial` 查找），**禁止** 跳过验签
- 回调解密 **必须** 使用 AEAD_AES_256_GCM + 商户 APIv3 密钥
- 重复回调 **必须** 幂等处理（检�?`order.status` �?paid �?直接返回 SUCCESS�?
- 回调响应 **必须** 返回微信要求格式（`{"code": "SUCCESS/FAIL", "message": "..."}`），**禁止** 使用统一响应格式
- 退�?**必须** 验证管理员权限（`get_current_admin`），**禁止** 普通用户退�?
- 订单列表 **必须** �?`user_id` 过滤�?*禁止** 跨用户查�?
- **覆盖度修�?*：已根据覆盖度分析报告修�?A-9（`datetime.utcnow()` naive �?timezone-aware，`default`/`onupdate` 改为 lambda 表达式，import 补充 `timezone`�?
- **覆盖度修�?X-7**：Order 模型新增 `extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)`（对�?DB 设计 §2.18）、`product_ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)`（对�?§2.18）；`product_type` �?`String(20)` 改为 `String(32)`（对�?§2.18）；`paid_at` 字段已存在无需修改
- **覆盖度修�?X-8**：PaymentRecord 模型新增 `paid_at: Mapped[datetime] = mapped_column()`（对�?DB 设计 §2.19，非 nullable，必填字段）
- **覆盖度修�?X-9**：新�?`RefundRecord` 模型（对齐退款流程，�?refund_no/refund_amount_cents/reason/status/operator_id/callback_raw 等字段）；`refund` Service 方法签名新增 `operator_id` 参数，退款时除了更新 `order.status` 还创�?`RefundRecord` 记录；`_call_wechat_refund` 方法签名新增 `refund_no` 参数（由 refund 方法生成并传入），返回微信退款响应用�?`RefundRecord.callback_raw`；Router 退款端点传�?`operator_id=admin.id`；Model import 补充 `Text`（RefundRecord.reason 字段使用�?
- **覆盖度修�?X-13**：`_create_or_renew_subscription` 方法删除 tier 硬编�?`"member"` �?period 硬编�?`30` 天，改为�?`order.extra_data` 获取 `tier` �?`period_days`（`extra = order.extra_data or {}; tier = extra.get("tier", "member"); period_days = extra.get("period_days", 30)`）；`create_order` 方法新增构建 `extra_data` 逻辑（membership �?tier/period_days/period，analysis_pack �?quantity）；`_trigger_business_logic` �?analysis_pack 分支�?`order.extra_data` 获取 quantity（替换硬编码 `bonus_qty = 1`�?
- 所有 API 端点应添加 `@limiter.limit()` 装饰器（例外：`POST /payment/notify` 微信回调不添加 `@limiter`，SEC-006 修复：微信服务器需要立即收到响应）
- `from app.core.limiter import limiter` **必须** 在路由文�?import 区声明，**禁止** 遗漏导入
