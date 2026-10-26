"""
tests/unit/test_membership.py — 会员模块测试

覆盖：等级权益、当前状态、免费额度、到期检测、权限守卫。
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.core.security import create_access_token, generate_jti


# === 1. Happy Path ===

@pytest.mark.asyncio
async def test_get_tiers_success(client, auth_headers, seed_tiers):
    """查询会员等级权益对比成功"""
    resp = await client.get("/api/v1/membership/tiers", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "tiers" in data
    assert len(data["tiers"]) >= 4
    free_tier = next(t for t in data["tiers"] if t["tier"] == "free")
    assert free_tier["price_monthly_cents"] == 0
    member_tier = next(t for t in data["tiers"] if t["tier"] == "member")
    assert member_tier["price_monthly_cents"] == 1900


@pytest.mark.asyncio
async def test_get_current_free_user(client, auth_headers, seed_tiers):
    """免费用户查询当前会员状态，tier 返回 free"""
    resp = await client.get("/api/v1/membership/current", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "free"
    assert data["status"] == "none"


@pytest.mark.asyncio
async def test_get_current_member_user(client, db_session, seed_tiers):
    """会员用户查询当前状态返回 active"""
    from app.models.user import User
    from app.models.membership import Subscription

    user = User(openid="test_member_001", nickname="会员用户", status="active")
    db_session.add(user)
    await db_session.flush()

    sub = Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=datetime.now(timezone.utc),
        expire_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/membership/current", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "member"
    assert data["status"] == "active"
    assert data["days_remaining"] > 0


@pytest.mark.asyncio
async def test_get_quota_free_user(client, auth_headers, seed_tiers):
    """免费用户查询今日剩余免费分析次数"""
    resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "free"
    assert data["daily_limit"] == 3
    assert data["remaining"] == 3


# === 2. Permission / Auth Failure ===

@pytest.mark.asyncio
async def test_get_tiers_without_token(client):
    """未携带 JWT 返回 401"""
    resp = await client.get("/api/v1/membership/tiers")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_current_without_token(client):
    """未携带 JWT 返回 401"""
    resp = await client.get("/api/v1/membership/current")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_quota_without_token(client):
    """未携带 JWT 返回 401"""
    resp = await client.get("/api/v1/membership/quota")
    assert resp.status_code == 401


# === 3. Business Rule ===

@pytest.mark.asyncio
async def test_quota_decrement_on_analysis(client, auth_headers, seed_tiers, test_user):
    """免费用户分析一次后，剩余额度减1"""
    from app.services.membership_service import MembershipService
    consumed = await MembershipService.consume_analysis_quota(test_user.id)
    assert consumed is True

    resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
    data = resp.json()["data"]
    assert data["used_today"] == 1
    assert data["remaining"] == 2


@pytest.mark.asyncio
async def test_quota_exhausted(client, auth_headers, seed_tiers, test_user):
    """免费用户额度用完后，消耗额度返回 False"""
    from app.services.membership_service import MembershipService
    for _ in range(3):
        await MembershipService.consume_analysis_quota(test_user.id)

    consumed = await MembershipService.consume_analysis_quota(test_user.id)
    assert consumed is False

    resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
    data = resp.json()["data"]
    assert data["remaining"] == 0


@pytest.mark.asyncio
async def test_member_unlimited_quota(client, db_session, seed_tiers):
    """会员用户不消耗免费额度"""
    from app.models.user import User
    from app.models.membership import Subscription
    from app.services.membership_service import MembershipService

    user = User(openid="test_member_quota", nickname="会员", status="active")
    db_session.add(user)
    await db_session.flush()

    sub = Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=datetime.now(timezone.utc),
        expire_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()

    consumed = await MembershipService.consume_analysis_quota(user.id)
    assert consumed is True  # 会员直接返回 True

    token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/api/v1/membership/quota", headers=headers)
    data = resp.json()["data"]
    assert data["tier"] == "member"
    assert data["daily_limit"] == -1
    assert data["remaining"] == -1


@pytest.mark.asyncio
async def test_membership_expiry_detection(db_session, seed_tiers):
    """到期检测：到期 3 天标记 expiring_soon"""
    from app.models.user import User
    from app.models.membership import Subscription
    from app.services.membership_service import MembershipService

    user = User(openid="test_expiry_001", nickname="到期用户", status="active")
    db_session.add(user)
    await db_session.flush()

    sub = Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=datetime.now(timezone.utc) - timedelta(days=28),
        expire_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add(sub)
    await db_session.commit()

    await MembershipService.check_expiry(db_session)

    from sqlalchemy import select
    result = await db_session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    updated = result.scalar_one()
    assert updated.status == "expiring_soon"


@pytest.mark.asyncio
async def test_membership_expired_detection(db_session, seed_tiers):
    """到期检测：超过宽限期(7天)标记 expired"""
    from app.models.user import User
    from app.models.membership import Subscription
    from app.services.membership_service import MembershipService

    user = User(openid="test_expired_001", nickname="已过期用户", status="active")
    db_session.add(user)
    await db_session.flush()

    # 过期 8 天（超过 GRACE_PERIOD_DAYS=7 宽限期，应直接标记 expired）
    sub = Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=datetime.now(timezone.utc) - timedelta(days=38),
        expire_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    db_session.add(sub)
    await db_session.commit()

    await MembershipService.check_expiry(db_session)

    from sqlalchemy import select
    result = await db_session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    updated = result.scalar_one()
    assert updated.status == "expired"


@pytest.mark.asyncio
async def test_membership_grace_period_detection(db_session, seed_tiers):
    """到期检测：刚过期(宽限期内)标记 grace_period，保留权益"""
    from app.models.user import User
    from app.models.membership import Subscription
    from app.services.membership_service import MembershipService

    user = User(openid="test_grace_001", nickname="宽限期用户", status="active")
    db_session.add(user)
    await db_session.flush()

    # 过期 3 天（在 GRACE_PERIOD_DAYS=7 宽限期内，应标记 grace_period）
    sub = Subscription(
        user_id=user.id, tier="member", status="active",
        start_at=datetime.now(timezone.utc) - timedelta(days=33),
        expire_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(sub)
    await db_session.commit()

    await MembershipService.check_expiry(db_session)

    from sqlalchemy import select
    result = await db_session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    updated = result.scalar_one()
    assert updated.status == "grace_period"


@pytest.mark.asyncio
async def test_tier_cache(client, auth_headers, seed_tiers, db_session):
    """等级列表缓存命中：第二次请求从 Redis 读取"""
    # 第一次请求（填充缓存）
    resp1 = await client.get("/api/v1/membership/tiers", headers=auth_headers)
    assert resp1.status_code == 200
    data1 = resp1.json()["data"]
    assert len(data1["tiers"]) == 4

    # 第二次请求（应命中缓存）
    resp2 = await client.get("/api/v1/membership/tiers", headers=auth_headers)
    assert resp2.status_code == 200
    data2 = resp2.json()["data"]
    assert len(data2["tiers"]) == 4
