"""
tests/unit/test_r14_d_pay_mbr_notif.py — R14 审计缺口补齐（D 组）

覆盖目标（先读代码核实行为，审计描述与实际不符处以实际为准）：

- R14-Pay-N2（本轮修复的新契约）：退款时间窗口矩阵
    * 24h 内：全额退款成功（reversal_type=full）+ 权益撤销链；部分退款不受 50% 限额
    * 24h-7d 窗口：部分退款 ==50% 成功（reversal_type=partial）；
      部分退款 >50% → 400「24小时至7天退款不可超过50%」；
      全额退款请求 → 400「24小时至7天内仅支持不超过50%的部分退款」（核心新契约，
      payment_service.py L568-574 R14-Pay-N2 注释处实现）
    * 7d 外 → 422 拒绝：既有覆盖 tests/unit/test_payment.py::test_refund_expired_order
      （L388-409：8 天 → 422 +「7天」消息），本文件不重复。
      注：审计描述「7d 外 → 400」与实际不符，实际实现为 422（以实际为准）。
      24h/7d 边界各测一侧：23h+25h（窗口内/外）、1000+1001 分（50% 边界两侧）。

- ND-3：notification Redis 故障降级分支（按实际代码语义，notification_service）：
    * is_user_online Redis 异常 → 降级为离线 → 通知落库且不抛错（L69-73）
    * get_unread_count Redis 异常 → DB 回退读取真实未读数（L236-259）
    * mark_read Redis 计数递减异常 → DB 已提交的已读状态不受影响（L219-229）

- ND-4：SAVEPOINT（db.begin_nested）子事务隔离 — 归属修正：notification_service.py
    全文无 begin_nested；实际模式位于 gamification_service.py（R13-Gam-N1 add_points
    L200 / R6-Gami-1 check_badges L384），按实际代码位置测试：
    * 子操作真实 DB IntegrityError → SAVEPOINT 只回滚子事务写入
      （UserPoints 加分/UserBadge 解锁均不落库），调用方主事务（已 flush 的
      调用方写入）commit 成功、不被 PendingRollbackError 污染
    * 竞态由 patch 模拟（并发窗口无法确定性复现），约束冲突为真实 PG 唯一约束

- Mbr-N3：membership expiring_soon（check_expiry 标记已有覆盖
    test_membership.py::test_membership_expiry_detection L164-189，本文件补增量）：
    * /membership/current 实时兜底标记 expiring_soon（get_current_membership L94-97）
    * expiring_soon 保留会员权益：/membership/quota → daily_limit=-1（L117-119）
    * check_expiry 触发 WS 到期提醒（membership_expiring，独立 Redis 客户端订阅实证）

- Gam-N5：reset_monthly_points 任务体（app/tasks/gamification.py）：
    monthly_points 归零 / total_points 等其余列保留 / 幂等（重复执行结果不变）。
    任务体为裸 asyncio.run 包装（无 _run_async 线程池包装），测试事件循环内直调
    会 RuntimeError: asyncio.run() cannot be called from a running event loop，
    经 asyncio.to_thread 在工作线程新 loop 执行 eager 直调（run_isolated 设计支持）。
"""

import asyncio
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import redis.asyncio as redis_async
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.security import create_access_token, generate_jti


# =============================================================================
# R14-Pay-N2：退款时间窗口矩阵
# =============================================================================

AMOUNT_CENTS = 2000  # 50% 限额边界 = 1000 分


@pytest.fixture
async def refund_seed(db_session, test_user):
    """退款测试种子工厂：构造指定支付时距（paid_ago）的已支付订单 + 关联订阅"""
    from app.models.membership import Subscription
    from app.models.payment import Order

    user = test_user
    now = datetime.now(timezone.utc)

    async def _make(paid_ago: timedelta, suffix: str = "01"):
        sub = Subscription(
            user_id=user.id, tier="member", status="active",
            start_at=now - timedelta(days=30),
            expire_at=now + timedelta(days=30),
        )
        db_session.add(sub)
        await db_session.flush()

        order = Order(
            user_id=user.id, subscription_id=sub.id,
            order_no=f"PPR14{now.strftime('%Y%m%d')}{suffix}{uuid.uuid4().hex[:8].upper()}",
            product_type="membership", amount_cents=AMOUNT_CENTS,
            status="paid", paid_at=now - paid_ago,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        return order, sub

    return _make


@pytest.mark.asyncio
async def test_r14_pay_n2_full_refund_within_24h(client, refund_seed, admin_headers):
    """R14-Pay-N2: 24h 内（2h）全额退款成功 — reversal_type=full + 订单/订阅状态联动"""
    order, sub = await refund_seed(timedelta(hours=2), suffix="01")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": AMOUNT_CENTS, "reason": "24h内全额退款"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["refund_status"] == "pending"
    assert data["refund_amount_cents"] == AMOUNT_CENTS

    # 独立会话验证（规避身份映射旧值）：退款记录类型 + 订单终态 + 权益撤销链
    from app.models.membership import Subscription
    from app.models.payment import Order, RefundRecord

    async with async_session_factory() as v:
        rr = (await v.execute(
            select(RefundRecord).where(RefundRecord.order_id == order.id)
        )).scalar_one()
        assert rr.reversal_type == "full"
        assert rr.status == "pending"
        assert rr.refund_amount_cents == AMOUNT_CENTS

        o = (await v.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert o.status == "refunded"

        s = (await v.execute(
            select(Subscription).where(Subscription.id == sub.id)
        )).scalar_one()
        assert s.status == "closed"  # 退款后撤销会员权益


@pytest.mark.asyncio
async def test_r14_pay_n2_partial_over_50pct_within_24h_allowed(client, refund_seed, admin_headers):
    """R14-Pay-N2: 24h 内（2h）部分退款超 50% 不受限 — reversal_type=partial（窗口边界内侧）"""
    order, _ = await refund_seed(timedelta(hours=2), suffix="02")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": 1200, "reason": "24h内部分退款"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["refund_amount_cents"] == 1200

    from app.models.payment import RefundRecord

    async with async_session_factory() as v:
        rr = (await v.execute(
            select(RefundRecord).where(RefundRecord.order_id == order.id)
        )).scalar_one()
        assert rr.reversal_type == "partial"


@pytest.mark.asyncio
async def test_r14_pay_n2_partial_at_50pct_between_24h_7d_allowed(client, refund_seed, admin_headers):
    """R14-Pay-N2: 24h-7d 窗口（25h）部分退款恰为 50%（1000 分）→ 放行（限额边界含等于）"""
    order, _ = await refund_seed(timedelta(hours=25), suffix="03")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": 1000, "reason": "窗口内50%边界退款"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["refund_amount_cents"] == 1000

    from app.models.payment import RefundRecord

    async with async_session_factory() as v:
        rr = (await v.execute(
            select(RefundRecord).where(RefundRecord.order_id == order.id)
        )).scalar_one()
        assert rr.reversal_type == "partial"


@pytest.mark.asyncio
async def test_r14_pay_n2_partial_over_50pct_between_24h_7d_rejected(client, refund_seed, admin_headers):
    """R14-Pay-N2: 24h-7d 窗口（25h）部分退款 >50%（1001 分）→ 400（R4-Pay-2 限额）"""
    order, _ = await refund_seed(timedelta(hours=25), suffix="04")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": 1001, "reason": "窗口内超额部分退款"},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 40000
    assert body["message"] == "24小时至7天内退款不可超过50%"

    # 拒绝路径不产生退款记录、订单状态不变
    from app.models.payment import Order, RefundRecord

    async with async_session_factory() as v:
        cnt = (await v.execute(
            select(func.count()).select_from(RefundRecord).where(RefundRecord.order_id == order.id)
        )).scalar_one()
        assert cnt == 0
        o = (await v.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert o.status == "paid"


@pytest.mark.asyncio
async def test_r14_pay_n2_full_refund_between_24h_7d_rejected(client, refund_seed, admin_headers):
    """R14-Pay-N2（核心新契约）: 24h-7d 窗口（25h）全额退款请求 → 400 拒绝

    payment_service.py L568-574：该窗口仅允许 ≤50% 的部分退款，
    全额退款不得绕过限额（原 full_reversal 分支直接放行的缺陷已修复）。
    """
    order, _ = await refund_seed(timedelta(hours=25), suffix="05")

    resp = await client.post(
        f"/api/v1/payment/orders/{order.id}/refund",
        json={"refund_amount_cents": AMOUNT_CENTS, "reason": "窗口内全额退款"},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 40000
    assert body["message"] == "24小时至7天内仅支持不超过50%的部分退款"

    # 拒绝路径不产生退款记录、订单状态不变（无绕过）
    from app.models.payment import Order, RefundRecord

    async with async_session_factory() as v:
        cnt = (await v.execute(
            select(func.count()).select_from(RefundRecord).where(RefundRecord.order_id == order.id)
        )).scalar_one()
        assert cnt == 0
        o = (await v.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert o.status == "paid"


# =============================================================================
# ND-3：notification Redis 故障降级分支（readonly/回退语义，按实际代码）
# =============================================================================

@pytest.mark.asyncio
async def test_nd3_send_notification_redis_failure_degrades_to_offline_db_write(db_session, test_user):
    """ND-3: Redis 故障时 is_user_online 降级为离线 → 通知落库、incr 失败仅告警不抛错

    notification_service.py L69-73：is_user_online 捕获 Redis 异常按离线处理；
    L100-126：离线路径写 DB；L114-118：未读计数 incr 失败仅记日志。
    """
    from app.models.notification import NotificationRecord
    from app.services.notification_service import NotificationService

    uid = test_user.id

    with patch(
        "app.services.notification_service.get_redis",
        side_effect=RuntimeError("redis unavailable"),
    ):
        record = await NotificationService.send_notification(
            user_id=uid, notif_type="nd3_degrade",
            title="降级通知", content="Redis 故障降级测试",
        )

    # 降级为离线路径：返回落库记录（而非在线路径的 None）
    assert record is not None
    assert record.title == "降级通知"
    assert record.type == "nd3_degrade"
    assert record.is_read is False

    # DB 确实落库（COUNT 聚合不经过身份映射）
    cnt = await db_session.scalar(
        select(func.count()).select_from(NotificationRecord).where(
            NotificationRecord.user_id == uid
        )
    )
    assert cnt == 1


@pytest.mark.asyncio
async def test_nd3_get_unread_count_redis_failure_falls_back_to_db(db_session, test_user):
    """ND-3: get_unread_count Redis 异常 → 只读回退到 DB 聚合并返回真实未读数

    notification_service.py L236-259：缓存读取异常 → except pass → DB 查询；
    回填缓存的 set 失败同样静默。降级路径计数与 DB 一致。
    """
    from app.models.notification import NotificationRecord
    from app.services.notification_service import NotificationService

    uid = test_user.id
    db_session.add_all([
        NotificationRecord(user_id=uid, type="nd3", title="未读1", is_read=False),
        NotificationRecord(user_id=uid, type="nd3", title="未读2", is_read=False),
        NotificationRecord(user_id=uid, type="nd3", title="已读", is_read=True),
    ])
    await db_session.commit()

    with patch(
        "app.services.notification_service.get_redis",
        side_effect=RuntimeError("redis unavailable"),
    ):
        count = await NotificationService.get_unread_count(uid)

    assert count == 2  # Redis 挂掉不影响未读数正确性（DB 回退）


@pytest.mark.asyncio
async def test_nd3_mark_read_redis_failure_keeps_db_commit(db_session, test_user):
    """ND-3: mark_read Redis 计数递减异常 → DB 已提交的已读状态不受影响、不抛错

    notification_service.py L219-229：decrby 失败仅记日志，updated_count 正常返回。
    """
    from app.models.notification import NotificationRecord
    from app.services.notification_service import NotificationService

    uid = test_user.id
    notif = NotificationRecord(
        user_id=uid, type="nd3", title="标记已读降级", is_read=False,
    )
    db_session.add(notif)
    await db_session.commit()

    with patch(
        "app.services.notification_service.get_redis",
        side_effect=RuntimeError("redis unavailable"),
    ):
        result = await NotificationService.mark_read(uid, [notif.id])

    assert result.updated_count == 1

    # 独立会话验证 DB 已读状态已提交
    async with async_session_factory() as v:
        row = (await v.execute(
            select(NotificationRecord).where(NotificationRecord.id == notif.id)
        )).scalar_one()
        assert row.is_read is True


# =============================================================================
# ND-4：SAVEPOINT（begin_nested）子事务隔离
# 注：审计标注 notification，实际 begin_nested 位于 gamification_service
# （R13-Gam-N1 add_points / R6-Gami-1 check_badges），按实际代码位置测试
# =============================================================================

@pytest.mark.asyncio
async def test_nd4_add_points_savepoint_isolates_integrity_error(db_session, test_user):
    """ND-4: add_points 子操作 IntegrityError → 仅 SAVEPOINT 回滚，调用方主事务存活

    gamification_service.py L188-212（R13-Gam-N1）：并发首次打卡竞态（另一会话
    抢先提交当日 checkin_record，uq_checkin_user_date 冲突）触发 flush IntegrityError。
    竞态由 patch _auto_checkin 模拟（并发窗口无法确定性复现），冲突为真实 PG
    唯一约束，SAVEPOINT 回滚为真实行为。预期：
      - add_points 返回 0（积分失败不阻塞业务，不向调用方抛错）
      - SAVEPOINT 内写入全部撤销（UserPoints 加分不落库、重复打卡不入库）
      - 调用方主事务（savepoint 前已 flush 的写入）commit 成功并持久化
        （修复前 session 进入 invalid → PendingRollbackError → 业务接口 500）
    """
    from app.models.gamification import CheckInRecord, UserPoints
    from app.models.notification import NotificationRecord
    from app.services.gamification_service import GamificationService, _cst_today

    uid = test_user.id

    # 种子：调用方主事务已有的持久状态（已提交的 UserPoints）
    db_session.add(UserPoints(user_id=uid, total_points=10, monthly_points=10, bonus_points=0))
    await db_session.commit()

    # 调用方主事务写入：显式 flush 落入外层事务（先于 SAVEPOINT）
    db_session.add(NotificationRecord(
        user_id=uid, type="nd4_caller", title="调用方主事务写入", content="",
    ))
    await db_session.flush()

    today = _cst_today()

    async def _race_auto_checkin(db, user_id, source):
        # 模拟并发竞态：另一会话抢先提交当日打卡（冲突源，真实唯一约束）
        async with async_session_factory() as other:
            other.add(CheckInRecord(
                user_id=user_id, checkin_date=today,
                checkin_type=source, points_earned=2,
            ))
            await other.commit()
        # 本会话（SAVEPOINT 内）重复插入 → flush 触发 IntegrityError
        db.add(CheckInRecord(
            user_id=user_id, checkin_date=today,
            checkin_type=source, points_earned=2,
        ))

    with patch.object(GamificationService, "_auto_checkin", _race_auto_checkin):
        points = await GamificationService.add_points(db_session, uid, "analysis")

    # 子操作失败不阻塞：吞掉异常返回 0
    assert points == 0

    # 调用方主事务未被污染：commit 成功（污染时此处抛 PendingRollbackError）
    await db_session.commit()

    # 独立会话验证最终状态
    async with async_session_factory() as v:
        up = (await v.execute(
            select(UserPoints).where(UserPoints.user_id == uid)
        )).scalar_one()
        # SAVEPOINT 内的加分已回滚（analysis +10 未生效）
        assert up.total_points == 10
        assert up.monthly_points == 10

        # 重复打卡的 INSERT 已回滚；并发获胜方的记录保留（各 1 条）
        checkins = (await v.execute(
            select(func.count()).select_from(CheckInRecord).where(CheckInRecord.user_id == uid)
        )).scalar_one()
        assert checkins == 1

        # 调用方主事务写入持久化
        notif_cnt = (await v.execute(
            select(func.count()).select_from(NotificationRecord).where(
                NotificationRecord.user_id == uid
            )
        )).scalar_one()
        assert notif_cnt == 1


@pytest.mark.asyncio
async def test_nd4_check_badges_savepoint_isolates_integrity_error(db_session, test_user):
    """ND-4: check_badges 解锁竞态 IntegrityError → 仅 SAVEPOINT 回滚，主事务存活

    gamification_service.py L379-427（R6-Gami-1）：并发解锁竞态（另一会话抢先
    提交同一 user_badge，uq_user_badge 冲突）。竞态由 patch _get_user_metrics 模拟
    （其调用点 L377 位于 earned_ids 查询 L372 之后、SAVEPOINT flush L423 之前，
    恰为竞态窗口），冲突为真实 PG 唯一约束。预期：
      - check_badges 静默返回（不向调用方抛 IntegrityError）
      - SAVEPOINT 内写入撤销（徽章奖励 +20 分不落库，重复解锁不入库）
      - 调用方主事务 commit 成功且调用方写入持久化
    """
    from app.models.gamification import BadgeDefinition, UserBadge, UserPoints
    from app.models.notification import NotificationRecord
    from app.services.gamification_service import BadgeService

    uid = test_user.id

    # 种子：streak_7 徽章（streak_days >= 7 可解锁，奖励 20 分）+ UserPoints
    db_session.add(BadgeDefinition(
        id="streak_7", name="连续7天", icon="🔥", category="streak",
        condition={"metric": "streak_days", "operator": ">=", "threshold": 7},
        points_reward=20, is_active=True,
    ))
    db_session.add(UserPoints(user_id=uid, total_points=30, monthly_points=30, bonus_points=0))
    await db_session.commit()

    # 调用方主事务写入：显式 flush 落入外层事务（先于 SAVEPOINT）
    db_session.add(NotificationRecord(
        user_id=uid, type="nd4_caller_badge", title="调用方主事务写入", content="",
    ))
    await db_session.flush()

    async def _race_metrics(db, user_id):
        # 模拟并发竞态：另一会话抢先解锁同一徽章（冲突源，真实唯一约束）
        async with async_session_factory() as other:
            other.add(UserBadge(user_id=user_id, badge_id="streak_7"))
            await other.commit()
        return {"analysis_count": 0, "match_count": 0, "checkin_count": 0, "streak_days": 7}

    with patch.object(BadgeService, "_get_user_metrics", _race_metrics):
        await BadgeService.check_badges(db_session, uid)  # 静默返回，不抛错

    # 调用方主事务未被污染：commit 成功
    await db_session.commit()

    # 独立会话验证最终状态
    async with async_session_factory() as v:
        # SAVEPOINT 内的解锁与奖励分均回滚；DB 中仅并发获胜方那 1 条
        badge_cnt = (await v.execute(
            select(func.count()).select_from(UserBadge).where(UserBadge.user_id == uid)
        )).scalar_one()
        assert badge_cnt == 1

        up = (await v.execute(
            select(UserPoints).where(UserPoints.user_id == uid)
        )).scalar_one()
        assert up.total_points == 30  # 徽章奖励 +20 已回滚
        assert up.monthly_points == 30

        # 调用方主事务写入持久化
        notif_cnt = (await v.execute(
            select(func.count()).select_from(NotificationRecord).where(
                NotificationRecord.user_id == uid
            )
        )).scalar_one()
        assert notif_cnt == 1


# =============================================================================
# Mbr-N3：membership expiring_soon（增量：实时标记 / 权益保留 / WS 到期提醒）
# 注：check_expiry 状态机标记已有覆盖 test_membership.py::test_membership_expiry_detection
# （L164-189）；本节补 /current 实时路径、权益保留与到期提醒推送
# =============================================================================

@pytest.mark.asyncio
async def test_mbr_n3_current_realtime_expiring_soon(client, db_session):
    """Mbr-N3: /membership/current 实时兜底 — active 且 3 天内到期 → expiring_soon"""
    from app.models.membership import Subscription
    from app.models.user import User

    user = User(openid="test_mbr_n3_current", nickname="临期会员", status="active")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add(Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=now - timedelta(days=28), expire_at=now + timedelta(days=2),
    ))
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/membership/current", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "member"
    assert data["status"] == "expiring_soon"  # 实时标记（get_current_membership L94-97）
    assert 1 <= data["days_remaining"] <= 2


@pytest.mark.asyncio
async def test_mbr_n3_expiring_soon_retains_member_quota(client, db_session):
    """Mbr-N3: expiring_soon 保留会员权益 — /membership/quota 返回无限额度"""
    from app.models.membership import Subscription
    from app.models.user import User

    user = User(openid="test_mbr_n3_quota", nickname="临期额度", status="active")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add(Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=now - timedelta(days=28), expire_at=now + timedelta(days=2),
    ))
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/membership/quota", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "member"
    assert data["daily_limit"] == -1  # expiring_soon 仍享受会员无限额度（L117-119）
    assert data["remaining"] == -1
    assert data["used_today"] == 0


@pytest.mark.asyncio
async def test_mbr_n3_check_expiry_sends_expiry_ws_notification(db_session):
    """Mbr-N3: check_expiry 标记 expiring_soon 并推送 WS 到期提醒（membership_expiring）

    订阅端使用独立 Redis 客户端（不走全局池，参照 test_r14_c B4-4 模式）；
    redis-py 7.1 subscribe() 不消费 SUBSCRIBE 确认 → 循环消费直到真正的 message。
    """
    from app.models.membership import Subscription
    from app.models.user import User
    from app.services.membership_service import MembershipService

    user = User(openid="test_mbr_n3_ws", nickname="到期提醒", status="active")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=now - timedelta(days=28), expire_at=now + timedelta(days=2),
    )
    db_session.add(sub)
    await db_session.commit()
    uid = user.id

    channel = f"ws:relay:ws:user:{uid}"
    sub_client = redis_async.Redis.from_url(
        settings.redis_url_computed, decode_responses=True,
    )
    pubsub = sub_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        await MembershipService.check_expiry(db_session)

        # 消费 WS 推送：_send_expiry_notification → push_ws_message → publish
        msg = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            m = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0,
            )
            if m is not None and m.get("type") == "message":
                msg = m
                break
        assert msg is not None, "未收到会员到期 WS 提醒推送"

        payload = json.loads(msg["data"])
        assert payload["event"] == "notification"
        ws_data = payload["data"]
        assert ws_data["type"] == "membership_expiring"
        assert ws_data["user_id"] == uid
        assert "member" in ws_data["content"]
        assert "天后到期" in ws_data["content"]

        # 状态标记同步生效（与通知同一次 check_expiry 内）
        await db_session.refresh(sub)
        assert sub.status == "expiring_soon"
    finally:
        await pubsub.aclose()
        await sub_client.aclose()


# =============================================================================
# Gam-N5：reset_monthly_points 月度积分重置任务体（eager 直调）
# =============================================================================

@pytest.mark.asyncio
async def test_gam_n5_reset_monthly_points(db_session, test_user):
    """Gam-N5: reset_monthly_points — monthly 归零、其余列保留、全表生效、幂等

    任务体（app/tasks/gamification.py）执行 `UPDATE user_points SET monthly_points = 0`。
    裸 asyncio.run 包装 → 经 asyncio.to_thread 在工作线程新 loop 执行
    （run_isolated 前置 reset + 收尾 close 隔离全局 Redis 池，engine 为 NullPool
    每次检出新连接，跨 loop 安全）。
    """
    from app.models.gamification import UserPoints
    from app.models.user import User
    from app.tasks.gamification import reset_monthly_points

    user2 = User(openid="test_gam_n5_user2", nickname="重置用户2", status="active")
    db_session.add(user2)
    await db_session.flush()

    today = date.today()
    db_session.add_all([
        UserPoints(
            user_id=test_user.id, total_points=100, monthly_points=40,
            bonus_points=7, current_streak=5, last_checkin_date=today,
        ),
        UserPoints(
            user_id=user2.id, total_points=50, monthly_points=25,
            bonus_points=0, current_streak=2,
        ),
    ])
    await db_session.commit()
    uid1, uid2 = test_user.id, user2.id

    async def _assert_state():
        async with async_session_factory() as v:
            for uid, total in ((uid1, 100), (uid2, 50)):
                up = (await v.execute(
                    select(UserPoints).where(UserPoints.user_id == uid)
                )).scalar_one()
                assert up.monthly_points == 0, (
                    f"user {uid}: monthly_points 应归零，实际 {up.monthly_points}"
                )
                assert up.total_points == total, (
                    f"user {uid}: total_points 应保留 {total}，实际 {up.total_points}"
                )
                assert up.bonus_points in (7, 0)  # 非目标列不动
                assert up.current_streak in (5, 2)
            # last_checkin_date 仅用户 1 有值且保留
            up1 = (await v.execute(
                select(UserPoints).where(UserPoints.user_id == uid1)
            )).scalar_one()
            assert up1.last_checkin_date == today

    # 第一次执行：全表 monthly 归零
    result = await asyncio.to_thread(reset_monthly_points)
    assert result == {"status": "ok"}
    await _assert_state()

    # 幂等：重复执行结果不变（monthly 保持 0，其余列不被误清零）
    result2 = await asyncio.to_thread(reset_monthly_points)
    assert result2 == {"status": "ok"}
    await _assert_state()
