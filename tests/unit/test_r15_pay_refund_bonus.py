"""
tests/unit/test_r15_pay_refund_bonus.py — R15-Pay-N1 锁定测试

R15 审计发现（A5 主报 + A1 佐证，R14-Pay-N1 打通 bonus 消费链后的对称缺口）：
analysis_pack 订单退款不回收 quota:bonus，退款后已购额度继续可用 → 资损。

写入对称面：支付回调 _trigger_business_logic（payment_service.py L457-462）
INCR quota:bonus:{uid} quantity + 90d TTL。

R15 修复（refund 后置块 analysis_pack 分支，独立 try/except）：
  * 全额退款（reversal_type=full）→ 回收全部 quantity
  * 部分退款 → bonus_qty * refund_amount_cents // order.amount_cents（向下取整）
  * clamp 至当前余额（已消耗部分不追回 — 预付池语义）；键 90d TTL 已过期
    → 余额 0 → 无操作（不产生负余额键）
  * 回收失败仅记日志，不影响退款主流程（退款已 commit）

锁定语义矩阵：
  a) 全额退款 → 全量回收 → 余额归 0
  b) 部分退款 50% → 比例回收（4 * 1000 // 2000 = 2）
  c) 已部分消耗 → 回收被 clamp 至当前余额（不追回已消耗）
  d) 键不存在/已过期 → 无操作且不落负余额键
  e) 部分退款比例过小 → 回收向下取整为 0 → 无回收（3 * 500 // 2000 = 0）
  f) membership 订单退款 → 不触碰 quota:bonus（分支隔离）
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.redis import get_redis

AMOUNT_CENTS = 2000


def _bonus_key(user_id: int) -> str:
    return f"quota:bonus:{user_id}"


@pytest.fixture
async def pack_seed(db_session, test_user):
    """analysis_pack 退款测试种子工厂：已支付 2h（24h 窗口内，全额退款合法）"""
    from app.models.payment import Order

    user = test_user
    now = datetime.now(timezone.utc)

    async def _make(quantity: int, product_type: str = "analysis_pack",
                    extra: dict | None = None, suffix: str = "01"):
        if product_type == "membership":
            from app.models.membership import Subscription
            sub = Subscription(
                user_id=user.id, tier="member", status="active",
                start_at=now - timedelta(days=30),
                expire_at=now + timedelta(days=30),
            )
            db_session.add(sub)
            await db_session.flush()
            sub_id = sub.id
        else:
            sub_id = None

        order = Order(
            user_id=user.id, subscription_id=sub_id,
            order_no=f"PPR15{now.strftime('%Y%m%d')}{suffix}"
                     f"{uuid.uuid4().hex[:8].upper()}",
            product_type=product_type, amount_cents=AMOUNT_CENTS,
            status="paid", paid_at=now - timedelta(hours=2),
            extra_data=extra if extra is not None else {"quantity": quantity},
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        return order

    return _make


async def _assert_bonus(user_id: int, expected: int | None):
    """断言 quota:bonus 余额；None 表示键不存在（未落负余额键）"""
    redis = await get_redis()
    val = await redis.get(_bonus_key(user_id))
    if expected is None:
        assert val is None, f"键应不存在，实际: {val}"
    else:
        assert val is not None, "键应存在，实际缺失"
        assert int(val) == expected, f"期望余额 {expected}，实际 {int(val)}"


@pytest.mark.asyncio
async def test_a_full_refund_recovers_all_bonus(client, pack_seed, admin_headers, test_user):
    """a) 全额退款 → 全量回收：quota:bonus 5 → 0"""
    redis = await get_redis()
    await redis.set(_bonus_key(test_user.id), "5")
    order = await pack_seed(quantity=5, suffix="01")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": AMOUNT_CENTS, "reason": "R15全额退款回收"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["refund_status"] == "pending"

    await _assert_bonus(test_user.id, 0)

    # 独立会话验证：RefundRecord reversal_type=full（全量回收的前提分支）
    from app.models.payment import RefundRecord
    async with async_session_factory() as v:
        rr = (await v.execute(
            select(RefundRecord).where(RefundRecord.order_id == order.id)
        )).scalar_one()
        assert rr.reversal_type == "full"


@pytest.mark.asyncio
async def test_b_partial_refund_recovers_proportional(client, pack_seed, admin_headers, test_user):
    """b) 部分退款 50% → 比例回收：quantity=4, 退 1000/2000 → 回收 2，余额 4 → 2"""
    redis = await get_redis()
    await redis.set(_bonus_key(test_user.id), "4")
    order = await pack_seed(quantity=4, suffix="02")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": 1000, "reason": "R15部分退款比例回收"},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    await _assert_bonus(test_user.id, 2)  # 4 - 4*1000//2000 = 4 - 2


@pytest.mark.asyncio
async def test_c_full_refund_clamped_when_consumed(client, pack_seed, admin_headers, test_user):
    """c) 已部分消耗 → 回收 clamp 至当前余额：quantity=4 已耗 3（余额 1）→ 全额退款仅回收 1 → 0"""
    redis = await get_redis()
    await redis.set(_bonus_key(test_user.id), "1")
    order = await pack_seed(quantity=4, suffix="03")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": AMOUNT_CENTS, "reason": "R15已消耗clamp"},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    # 请求回收 4，实际回收 1（clamp）— 不追回已消耗部分，余额精确归 0
    await _assert_bonus(test_user.id, 0)


@pytest.mark.asyncio
async def test_d_absent_or_expired_key_noop(client, pack_seed, admin_headers, test_user):
    """d) 键不存在（90d TTL 已过期语义）→ 无操作：不落键、不产生负余额"""
    redis = await get_redis()
    await redis.delete(_bonus_key(test_user.id))
    order = await pack_seed(quantity=5, suffix="04")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": AMOUNT_CENTS, "reason": "R15键过期无操作"},
        headers=admin_headers,
    )
    assert resp.status_code == 200  # 回收失败不影响退款主流程

    await _assert_bonus(test_user.id, None)  # 键保持缺失，绝非 -5


@pytest.mark.asyncio
async def test_e_partial_floor_zero_no_recovery(client, pack_seed, admin_headers, test_user):
    """e) 比例回收向下取整为 0 → 无回收：quantity=3, 退 500/2000 → 3*500//2000=0，余额不变"""
    redis = await get_redis()
    await redis.set(_bonus_key(test_user.id), "3")
    order = await pack_seed(quantity=3, suffix="05")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": 500, "reason": "R15比例取整为0"},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    await _assert_bonus(test_user.id, 3)  # 3 - 0 = 3


@pytest.mark.asyncio
async def test_f_membership_refund_untouched_bonus(client, pack_seed, admin_headers, test_user):
    """f) membership 订单退款 → quota:bonus 不受影响（analysis_pack 分支隔离）"""
    redis = await get_redis()
    await redis.set(_bonus_key(test_user.id), "3")
    order = await pack_seed(quantity=0, product_type="membership", suffix="06")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": AMOUNT_CENTS, "reason": "R15会员退款不触碰bonus"},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    await _assert_bonus(test_user.id, 3)  # 会员退款不回收分析包额度
