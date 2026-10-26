"""
tests/unit/test_supplements_p2.py — P2 优先级补充测试

覆盖边界场景、错误码、缓存失效、赛制覆盖、积分规则全量验证。
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from app.core.security import create_access_token, generate_jti, pwd_context
from app.models.user import User
from app.models.membership import Subscription, MembershipTierConfig
from app.models.gamification import UserPoints, BadgeDefinition
from app.models.admin import AdminUser
from sqlalchemy import select


# ============================================================================
# Admin P2 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def admin_with_pwd(db_session):
    admin = AdminUser(
        username="p2_admin",
        password_hash=pwd_context.hash("Admin@123"),
        role="super_admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture(scope="function")
async def admin_headers(admin_with_pwd):
    from app.services.admin_service import AdminService
    data = await AdminService.login("p2_admin", "Admin@123")
    return {"Authorization": f"Bearer {data.session_token}"}


@pytest.mark.asyncio
class TestAdminEdgeCases:
    """Admin 边界场景"""

    async def test_create_config_duplicate_key_409(self, client, db_session, admin_headers):
        """重复 key 创建配置返回 409"""
        # 先创建一个配置
        resp1 = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "p2_dup_key", "config_value": "v1", "description": "P2测试"},
            headers=admin_headers,
        )
        assert resp1.status_code in (200, 201)

        # 重复创建
        resp2 = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "p2_dup_key", "config_value": "v2", "description": "P2重复"},
            headers=admin_headers,
        )
        assert resp2.status_code == 409, f"重复 key 应返回 409，实际 {resp2.status_code}"

    async def test_disabled_admin_login_403(self, db_session):
        """被禁用管理员登录返回 403"""
        from app.services.admin_service import AdminService
        from app.core.exceptions import AppException

        admin = AdminUser(
            username="p2_disabled",
            password_hash=pwd_context.hash("Admin@123"),
            role="super_admin",
            is_active=False,  # 禁用
        )
        db_session.add(admin)
        await db_session.commit()

        with pytest.raises(AppException) as exc_info:
            await AdminService.login("p2_disabled", "Admin@123")
        assert exc_info.value.status_code == 403, \
            f"禁用管理员登录应 403，实际 {exc_info.value.status_code}"

    async def test_unban_not_banned_409(self, client, db_session, admin_headers):
        """解禁未被封禁用户返回 409"""
        user = User(openid="p2_not_banned", nickname="未封禁", status="active")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resp = await client.post(
            f"/api/v1/admin/users/{user.id}/unban",
            headers=admin_headers,
        )
        assert resp.status_code == 409, \
            f"解禁未封禁用户应 409，实际 {resp.status_code}"


# ============================================================================
# Scoring P2 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def seed_tiers_for_p2(db_session):
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


@pytest_asyncio.fixture(scope="function")
async def auth_headers_for_p2(db_session, seed_tiers_for_p2):
    user = User(openid="p2_scoring", nickname="赛制用户", status="active")
    db_session.add(user)
    await db_session.commit()
    token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestScoringFormatCoverage:
    """赛制覆盖 + deuce 规则"""

    @pytest.mark.parametrize("fmt", ["bo1", "bo3", "bo5", "bo7", "custom"])
    async def test_create_match_all_formats(self, client, auth_headers_for_p2, fmt):
        """bo1/bo3/bo5/bo7/custom 五种赛制均可创建比赛"""
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={
                "opponent_name": f"对手_{fmt}",
                "opponent_rating": 1500,
                "format": fmt,
                "match_type": "friendly",
            },
            headers=auth_headers_for_p2,
        )
        assert resp.status_code in (200, 201), \
            f"赛制 {fmt} 创建应成功，实际 {resp.status_code}: {resp.text}"

    async def test_invalid_format_422(self, client, auth_headers_for_p2):
        """无效赛制返回 422"""
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={
                "opponent_name": "对手",
                "opponent_rating": 1500,
                "format": "bo99",  # 无效
                "match_type": "friendly",
            },
            headers=auth_headers_for_p2,
        )
        assert resp.status_code == 422, \
            f"无效赛制应 422，实际 {resp.status_code}"

    async def test_deuce_switch_interval(self, db_session):
        """deuce 后每球换边（switch_interval=1）"""
        from app.services.scoring_service import ScoringService

        # 10-10 时进入 deuce，每球换边
        # 初始 server=user，total_points=20，switch_interval=1，cycle=20，20%2==0 → 返回 initial_server(user)
        # 加 1 球后 total_points=21，cycle=21，21%2==1 → 返回 opponent
        server_at_10_10 = ScoringService._calc_server(10, 10, 11, "user")
        server_at_11_10 = ScoringService._calc_server(11, 10, 11, "user")
        # deuce 后每球换边：server 应不同
        assert server_at_10_10 != server_at_11_10, \
            "deuce 后每球换边，10-10 和 11-10 发球方应不同"

        # 非 deuce 时每 2 球换边
        server_at_5_4 = ScoringService._calc_server(5, 4, 11, "user")
        server_at_6_4 = ScoringService._calc_server(6, 4, 11, "user")
        # 5-4 total=9, cycle=4 (9//2), 4%2==0 → user; 6-4 total=10, cycle=5, 5%2==1 → opponent
        assert server_at_5_4 != server_at_6_4, \
            "非 deuce 每 2 球换边，5-4 和 6-4 发球方应不同"


# ============================================================================
# Video Analysis P2 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def shared_report(db_session, seed_tiers_for_p2):
    """创建已分析报告 + 分享链接"""
    from app.models.video_analysis import AnalysisReport, VideoTask, FileRecord
    from app.models.match import ShareRecord

    user = User(openid="p2_share", nickname="分享用户", status="active")
    db_session.add(user)
    await db_session.flush()

    file_record = FileRecord(
        user_id=user.id, oss_key="p2_oss_key.mp4",
        original_filename="p2.mp4", file_size=10 * 1024 * 1024,
        file_type="mp4", status="uploaded",
    )
    db_session.add(file_record)
    await db_session.flush()

    task = VideoTask(
        user_id=user.id, file_id=file_record.id,
        oss_key=file_record.oss_key, task_uuid="p2_task_uuid",
        status="completed", current_step=10, total_steps=10, progress=1.0,
    )
    db_session.add(task)
    await db_session.flush()

    report = AnalysisReport(
        task_id=task.id, user_id=user.id,
        result_data={"summary": "P2测试报告"},
        report_text="P2测试报告内容",
    )
    db_session.add(report)
    await db_session.flush()

    # 创建已过期分享
    share = ShareRecord(
        report_id=report.id,
        user_id=user.id,
        share_token="p2_expired_token",
        share_scope="public",
        expire_at=datetime.now(timezone.utc) - timedelta(days=1),  # 已过期
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return user, share


@pytest.mark.asyncio
class TestVideoShareExpiry:
    """分享过期访问"""

    async def test_expired_share_access(self, client, shared_report):
        """过期分享 token 访问应返回 410 Gone 或 404"""
        user, share = shared_report
        resp = await client.get(f"/share/{share.share_token}")
        assert resp.status_code in (410, 404), \
            f"过期分享应返回 410/404，实际 {resp.status_code}"


# ============================================================================
# Gamification 积分规则 P2 测试
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def seed_badges_for_p2(db_session):
    """预置徽章"""
    badges = [
        BadgeDefinition(
            id="streak_30", name="连续30天", icon="🌟", category="streak",
            condition={"metric": "streak_days", "operator": ">=", "threshold": 30},
            points_reward=100, sort_order=1, is_active=True,
        ),
    ]
    for b in badges:
        db_session.add(b)
    await db_session.commit()
    return badges


@pytest.mark.asyncio
class TestPointsRulesComplete:
    """积分规则全量验证"""

    async def test_points_rules_values(self):
        """验证 POINTS_RULES 所有关键值"""
        from app.services.gamification_service import POINTS_RULES

        assert POINTS_RULES["analysis"] == 10
        assert POINTS_RULES["match"] == 5
        assert POINTS_RULES["record"] == 3
        assert POINTS_RULES["checkin"] == 2
        assert POINTS_RULES["streak_7"] == 20
        assert POINTS_RULES["streak_30"] == 100
        assert POINTS_RULES["training_session"] == 5
        assert POINTS_RULES["share"] == 2
        assert POINTS_RULES["feedback"] == 1

    async def test_checkin_base_points(self, db_session):
        """打卡基础积分 2 分"""
        from app.services.gamification_service import GamificationService, POINTS_RULES

        user = User(openid="p2_checkin_base", nickname="打卡基础", status="active")
        db_session.add(user)
        await db_session.flush()

        up = UserPoints(user_id=user.id, total_points=0, monthly_points=0, current_streak=1)
        db_session.add(up)
        await db_session.commit()

        result = await GamificationService.checkin(db_session, user.id)
        await db_session.commit()

        assert result["points_earned"] == POINTS_RULES["checkin"], \
            f"打卡基础积分应为 {POINTS_RULES['checkin']}，实际 {result['points_earned']}"

    async def test_streak_30_bonus(self, db_session, seed_badges_for_p2):
        """第 30 天打卡触发 streak_30 奖励 100 分"""
        from app.services.gamification_service import GamificationService, POINTS_RULES
        from app.core.redis import get_redis

        user = User(openid="p2_streak30", nickname="连续30天", status="active")
        db_session.add(user)
        await db_session.flush()

        up = UserPoints(user_id=user.id, total_points=0, monthly_points=0, current_streak=29)
        db_session.add(up)
        await db_session.commit()

        redis = await get_redis()
        await redis.set(f"gamification:streak:user:{user.id}", 29)
        last_date = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        await redis.set(f"gamification:streak:last_date:{user.id}", last_date)

        result = await GamificationService.checkin(db_session, user.id)
        await db_session.commit()

        assert result["current_streak"] == 30
        assert result["bonus"] == POINTS_RULES["streak_30"], \
            f"连续 30 天 bonus 应为 {POINTS_RULES['streak_30']}，实际 {result['bonus']}"


# ============================================================================
# Membership 缓存失效 P2 测试
# ============================================================================

@pytest.mark.asyncio
class TestMembershipCacheInvalidation:
    """等级缓存失效后重新加载"""

    async def test_tier_cache_invalidation_on_update(self, client, db_session, seed_tiers_for_p2, admin_headers):
        """更新配置后缓存失效，重新加载新值"""
        # 先读取配置（缓存写入）
        from app.core.redis import get_redis
        redis = await get_redis()

        # 创建一个配置
        resp = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "p2_cache_key", "config_value": "v1", "description": "缓存测试"},
            headers=admin_headers,
        )
        assert resp.status_code in (200, 201)

        # 读取配置（缓存）
        resp_get = await client.get("/api/v1/admin/configs/p2_cache_key", headers=admin_headers)
        assert resp_get.status_code == 200
        assert resp_get.json()["data"]["config_value"] == "v1"

        # 更新配置
        resp_update = await client.patch(
            "/api/v1/admin/configs/p2_cache_key",
            json={"config_value": "v2", "description": "更新后"},
            headers=admin_headers,
        )
        assert resp_update.status_code == 200

        # 再次读取应得到新值（缓存已失效）
        resp_get2 = await client.get("/api/v1/admin/configs/p2_cache_key", headers=admin_headers)
        assert resp_get2.status_code == 200
        assert resp_get2.json()["data"]["config_value"] == "v2", \
            f"更新后缓存应失效，应得到 v2，实际 {resp_get2.json()['data']['config_value']}"
