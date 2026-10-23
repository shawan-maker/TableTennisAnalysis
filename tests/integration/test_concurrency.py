"""
tests/integration/test_concurrency.py — 并发场景补充测试

覆盖薄弱环节：支付回调幂等性、额度并发递减、比赛序号并发分配
"""

import asyncio
import json
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.core.security import create_access_token, generate_jti
from app.core.database import async_session_factory
from app.models.user import User
from app.models.payment import Order, PaymentRecord
from app.models.membership import MembershipTierConfig, Subscription
from app.services.payment_service import PaymentService
from app.services.video_analysis_service import VideoAnalysisService
from app.core.redis import get_redis
from sqlalchemy import select


def _auth_headers(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id), 'jti': generate_jti()})}"}


@pytest_asyncio.fixture
async def paid_order(db_session, seed_tiers):
    """创建一个已下单但未支付的订单"""
    user = User(openid="conc_user", nickname="并发用户", status="active")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    order = Order(
        user_id=user.id,
        order_no=f"conc_{uuid.uuid4().hex[:16]}",
        product_type="membership",
        amount_cents=1900,
        status="pending",
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return user, order


@pytest.mark.asyncio
class TestPaymentCallbackIdempotency:
    """支付回调幂等性测试"""

    async def test_duplicate_notify_is_idempotent(self, client, paid_order):
        """同一订单的重复回调不会创建多条 PaymentRecord"""
        user, order = paid_order

        callback_body = json.dumps({
            "resource": {
                "out_trade_no": order.order_no,
                "transaction_id": f"wx_conc_{uuid.uuid4().hex[:8]}",
                "trade_state": "SUCCESS",
                "amount": {"total": 1900},
            }
        })
        headers = {
            "Content-Type": "application/json",
            "Wechatpay-Signature": "sig",
            "Wechatpay-Serial": "serial",
            "Wechatpay-Nonce": "nonce",
            "Wechatpay-Timestamp": "1234567890",
        }

        # 第一次回调
        resp1 = await client.post(
            "/api/v1/payment/notify",
            content=callback_body,
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["code"] == "SUCCESS"

        # 第二次重复回调（相同 transaction_id）
        resp2 = await client.post(
            "/api/v1/payment/notify",
            content=callback_body,
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["code"] == "SUCCESS"

        # 验证只有一条 PaymentRecord
        async with async_session_factory() as db:
            result = await db.execute(
                select(PaymentRecord).where(PaymentRecord.order_id == order.id)
            )
            records = result.scalars().all()
            assert len(records) == 1, f"Expected 1 PaymentRecord, got {len(records)}"

    async def test_sequential_notify_different_tx_no_duplicate_subscription(self, client, paid_order):
        """顺序回调（不同 transaction_id，相同 order_no）只创建一条 Subscription"""
        user, order = paid_order

        # 第一次回调
        tx1 = f"wx_seq_a_{uuid.uuid4().hex[:8]}"
        body1 = json.dumps({
            "resource": {
                "out_trade_no": order.order_no,
                "transaction_id": tx1,
                "trade_state": "SUCCESS",
                "amount": {"total": 1900},
            }
        })
        headers = {
            "Content-Type": "application/json",
            "Wechatpay-Signature": "sig",
            "Wechatpay-Serial": "serial",
            "Wechatpay-Nonce": "nonce",
            "Wechatpay-Timestamp": "1234567890",
        }
        resp1 = await client.post("/api/v1/payment/notify", content=body1, headers=headers)
        assert resp1.status_code == 200
        assert resp1.json()["code"] == "SUCCESS"

        # 第二次回调（不同 transaction_id，相同 order_no）— 幂等检查应返回 SUCCESS
        tx2 = f"wx_seq_b_{uuid.uuid4().hex[:8]}"
        body2 = json.dumps({
            "resource": {
                "out_trade_no": order.order_no,
                "transaction_id": tx2,
                "trade_state": "SUCCESS",
                "amount": {"total": 1900},
            }
        })
        resp2 = await client.post("/api/v1/payment/notify", content=body2, headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["code"] == "SUCCESS"

        # 验证 Subscription 只有一条
        async with async_session_factory() as db:
            result = await db.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            )
            subs = result.scalars().all()
            assert len(subs) == 1, f"Expected 1 Subscription, got {len(subs)}"


@pytest.mark.asyncio
class TestQuotaConcurrentDecrement:
    """额度并发递减测试"""

    async def test_free_quota_concurrent_increment(self, db_session):
        """并发调用 _check_free_quota 时，Redis 计数器正确递增"""
        user = User(openid="quota_user", nickname="额度用户", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # 先清理可能残留的 key
        redis = await get_redis()
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"quota:analysis:{user.id}:{today}"
        await redis.delete(key)

        # 并发调用 3 次（假设 FREE_DAILY_LIMIT >= 3）
        from app.core.config import settings
        limit = settings.FREE_DAILY_ANALYSIS_LIMIT

        results = await asyncio.gather(
            *[VideoAnalysisService._check_free_quota(user.id) for _ in range(3)],
            return_exceptions=True,
        )

        # 前 limit 次应成功，超出应抛异常
        success_count = sum(1 for r in results if r is None)
        if limit >= 3:
            assert success_count == 3
        else:
            assert success_count == limit

        # 验证 Redis 计数器值
        count = int(await redis.get(key) or 0)
        assert count == success_count

        # 清理
        await redis.delete(key)


@pytest.mark.asyncio
class TestMatchSequenceConcurrent:
    """比赛序号并发分配测试"""

    async def test_concurrent_score_sequence_unique(self, client, db_session):
        """并发记分时 Redis INCR 序号不重复"""
        from app.models.match import Match, ScoreRecord
        from app.core.redis import get_redis

        user = User(openid="seq_user", nickname="序号用户", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        match = Match(user_id=user.id, opponent_name="并发对手", format="bo1", status="in_progress")
        db_session.add(match)
        await db_session.commit()
        await db_session.refresh(match)

        # 清理 Redis 序号 key
        redis = await get_redis()
        seq_key = f"scoring:match:{match.id}:seq"
        await redis.delete(seq_key)

        # 并发发送 5 次记分
        headers = _auth_headers(user.id)
        tasks = [
            client.post(
                f"/api/v1/scoring/matches/{match.id}/score",
                json={"scorer": "user", "score_method": "serve_point"},
                headers=headers,
            )
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 至少部分应成功
        success_count = sum(
            1 for r in results
            if not isinstance(r, Exception) and r.status_code in (200, 201)
        )

        # 验证 DB 中的 ScoreRecord 序号不重复
        async with async_session_factory() as db:
            result = await db.execute(
                select(ScoreRecord.sequence)
                .where(ScoreRecord.match_id == match.id)
                .order_by(ScoreRecord.sequence)
            )
            sequences = [r[0] for r in result.fetchall()]

        # 序号应唯一
        assert len(sequences) == len(set(sequences)), "Duplicate sequences found"
        # 如果全部成功，序号应为 1,2,3,4,5
        if success_count == 5:
            assert sequences == [1, 2, 3, 4, 5]

        # 清理
        await redis.delete(seq_key)
