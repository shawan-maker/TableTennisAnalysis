"""
tests/unit/test_r15_va_bonus_display.py — R15-VA-N1 锁定测试

R15-A5 发现：R14-Pay-N1 打通付费分析包额度（quota:bonus:{uid}）消费链后，
展示层未适配 —
  * GET /users/quota（UserService.get_quota）不返回付费包余额
  * GET /membership/quota（MembershipService.get_quota）不返回付费包余额
  * MembershipService.check_membership 免费分支 has_quota 仅看日额度，
    日额度耗尽但付费包有余额时误报 False（实际可创建任务 —
    _check_free_quota 回退消耗 quota:bonus）

R15 修复：QuotaResponse（user/membership 两处 Schema）新增
bonus_remaining 字段；MembershipCheckResult 新增 bonus_remaining 且
免费分支 has_quota = remaining > 0 or bonus_remaining > 0；
MembershipService._get_bonus_remaining 统一读取（Redis 异常降级 0、
防御性 clamp 负值、键缺失 → 0）。

锁定矩阵：
  a) /users/quota 付费包有余额 → bonus_remaining 如实返回，免费字段互不干扰
  b) /users/quota 未购买（键缺失）→ bonus_remaining=0
  c) /membership/quota 免费用户 + 付费包余额 → tier=free + bonus_remaining
  d) /membership/quota 会员 + 付费包余额 → daily_limit=-1 + bonus_remaining（信息性）
  e) check_membership 日额度耗尽 + 付费包余额 1 → has_quota=True（核心语义修正）
  f) check_membership 日额度耗尽 + 无付费包 → has_quota=False（原语义保持）
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.redis import get_redis


def _today_cst() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y%m%d")


async def _set_bonus(user_id: int, value: int | None):
    redis = await get_redis()
    key = f"quota:bonus:{user_id}"
    if value is None:
        await redis.delete(key)
    else:
        await redis.set(key, str(value))


@pytest.mark.asyncio
async def test_a_users_quota_with_bonus(client, test_user, auth_headers):
    """a) /users/quota：付费包余额 5 → bonus_remaining=5，免费额度字段独立"""
    redis = await get_redis()
    await redis.delete(f"quota:analysis:{test_user.id}:{_today_cst()}")
    await _set_bonus(test_user.id, 5)

    resp = await client.get("/api/v1/users/quota", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["bonus_remaining"] == 5
    # 免费额度字段不受付费包影响（互不串扰）
    assert data["daily_limit"] == 3
    assert data["used_today"] == 0
    assert data["remaining"] == 3


@pytest.mark.asyncio
async def test_b_users_quota_no_bonus(client, test_user, auth_headers):
    """b) /users/quota：未购买/键缺失 → bonus_remaining=0"""
    await _set_bonus(test_user.id, None)

    resp = await client.get("/api/v1/users/quota", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["bonus_remaining"] == 0


@pytest.mark.asyncio
async def test_c_membership_quota_free_with_bonus(client, test_user, auth_headers):
    """c) /membership/quota：免费用户 + 付费包余额 2 → tier=free + bonus_remaining=2"""
    redis = await get_redis()
    await redis.delete(f"quota:analysis:{test_user.id}:{_today_cst()}")
    await _set_bonus(test_user.id, 2)

    resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "free"
    assert data["bonus_remaining"] == 2
    assert data["daily_limit"] == 3


@pytest.mark.asyncio
async def test_d_membership_quota_member_with_bonus(client, test_user, auth_headers, db_session):
    """d) /membership/quota：会员 + 付费包余额 3 → daily_limit=-1 + bonus_remaining=3"""
    from app.models.membership import Subscription

    now = datetime.now(timezone.utc)
    db_session.add(Subscription(
        user_id=test_user.id, tier="member", status="active",
        start_at=now - timedelta(days=5), expire_at=now + timedelta(days=25),
    ))
    await db_session.commit()
    await _set_bonus(test_user.id, 3)

    resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "member"
    assert data["daily_limit"] == -1
    assert data["remaining"] == -1
    # 会员期内不消耗付费包（consume 直接放行），余额信息性展示
    assert data["bonus_remaining"] == 3


@pytest.mark.asyncio
async def test_e_check_quota_true_when_bonus_available(db_session, test_user):
    """e) 核心语义修正：日额度耗尽（used=3）+ 付费包余额 1 → has_quota=True"""
    from app.services.membership_service import MembershipService

    redis = await get_redis()
    await redis.set(f"quota:analysis:{test_user.id}:{_today_cst()}", "3")
    await _set_bonus(test_user.id, 1)

    result = await MembershipService.check_membership(db_session, test_user.id)
    assert result.is_member is False
    assert result.remaining == 0
    assert result.bonus_remaining == 1
    assert result.has_quota is True  # 付费包余额支撑可用额度


@pytest.mark.asyncio
async def test_f_check_quota_false_when_all_exhausted(db_session, test_user):
    """f) 原语义保持：日额度耗尽 + 无付费包 → has_quota=False"""
    from app.services.membership_service import MembershipService

    redis = await get_redis()
    await redis.set(f"quota:analysis:{test_user.id}:{_today_cst()}", "3")
    await _set_bonus(test_user.id, None)

    result = await MembershipService.check_membership(db_session, test_user.id)
    assert result.remaining == 0
    assert result.bonus_remaining == 0
    assert result.has_quota is False
