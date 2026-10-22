"""
tests/unit/test_gamification.py - 游戏化模块单元测试

覆盖：积分查询、打卡日历、每日打卡、徽章列表、积分规则、连续打卡
"""

import pytest
from datetime import date, timedelta

from app.core.database import async_session_factory
from app.models.gamification import BadgeDefinition, CheckInRecord, UserPoints
from app.models.user import User


async def _seed_badges(db):
    """初始化 6 个徽章定义"""
    seeds = [
        {"id": "first_analysis", "name": "首分析", "icon": "📹", "category": "analysis",
         "condition": {"metric": "analysis_count", "operator": ">=", "threshold": 1}, "points_reward": 10},
        {"id": "first_match", "name": "首场比赛", "icon": "🏓", "category": "match",
         "condition": {"metric": "match_count", "operator": ">=", "threshold": 1}, "points_reward": 10},
        {"id": "streak_7", "name": "连续7天", "icon": "🔥", "category": "streak",
         "condition": {"metric": "streak_days", "operator": ">=", "threshold": 7}, "points_reward": 20},
        {"id": "streak_30", "name": "连续30天", "icon": "🌟", "category": "streak",
         "condition": {"metric": "streak_days", "operator": ">=", "threshold": 30}, "points_reward": 100},
        {"id": "analysis_10", "name": "分析10次", "icon": "📊", "category": "analysis",
         "condition": {"metric": "analysis_count", "operator": ">=", "threshold": 10}, "points_reward": 30},
        {"id": "match_50", "name": "百场对决", "icon": "🏆", "category": "match",
         "condition": {"metric": "match_count", "operator": ">=", "threshold": 50}, "points_reward": 50},
    ]
    for s in seeds:
        bd = BadgeDefinition(**s)
        db.add(bd)
    await db.flush()


# =============================================================================
# 积分查询
# =============================================================================

@pytest.mark.asyncio
async def test_points_empty_user(client, auth_headers):
    """无积分用户返回全零"""
    resp = await client.get("/api/v1/gamification/points", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_points"] == 0
    assert data["monthly_points"] == 0
    assert data["current_streak"] == 0


@pytest.mark.asyncio
async def test_points_after_checkin(client, auth_headers, auth_user):
    """打卡后积分增加"""
    resp = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["points_earned"] == 2
    assert data["current_streak"] == 1

    resp2 = await client.get("/api/v1/gamification/points", headers=auth_headers)
    assert resp2.status_code == 200
    points = resp2.json()["data"]
    assert points["total_points"] == 2
    assert points["current_streak"] == 1


# =============================================================================
# 打卡日历
# =============================================================================

@pytest.mark.asyncio
async def test_checkin_calendar_empty(client, auth_headers):
    """无打卡记录的日历"""
    today = date.today()
    resp = await client.get(
        "/api/v1/gamification/checkin-calendar",
        params={"year": today.year, "month": today.month},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["year"] == today.year
    assert data["month"] == today.month
    assert data["monthly_checkin_count"] == 0
    assert data["streak_days"] == 0


@pytest.mark.asyncio
async def test_checkin_calendar_with_records(client, auth_headers, auth_user):
    """有打卡记录的日历"""
    # 打卡
    await client.post("/api/v1/gamification/checkin", headers=auth_headers)

    today = date.today()
    resp = await client.get(
        "/api/v1/gamification/checkin-calendar",
        params={"year": today.year, "month": today.month},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["monthly_checkin_count"] == 1
    today_str = today.isoformat()
    today_day = next(d for d in data["days"] if d["date"] == today_str)
    assert today_day["checked_in"] is True
    assert today_day["type"] == "manual"


# =============================================================================
# 每日打卡
# =============================================================================

@pytest.mark.asyncio
async def test_checkin_success(client, auth_headers):
    """首次打卡成功"""
    resp = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["points_earned"] == 2
    assert data["current_streak"] == 1


@pytest.mark.asyncio
async def test_checkin_duplicate(client, auth_headers):
    """同日重复打卡返回 409"""
    resp1 = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp1.status_code == 200

    resp2 = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
    assert resp2.status_code == 409


# =============================================================================
# 徽章列表
# =============================================================================

@pytest.mark.asyncio
async def test_badges_empty(client, auth_headers, auth_user, db_session):
    """无徽章用户返回全部 locked"""
    await _seed_badges(db_session)
    await db_session.commit()

    resp = await client.get("/api/v1/gamification/badges", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["earned"]) == 0
    assert len(data["locked"]) == 6
    for b in data["locked"]:
        assert b["progress"] == 0


@pytest.mark.asyncio
async def test_badges_after_analysis(client, auth_headers, auth_user, db_session):
    """分析后解锁 first_analysis 徽章"""
    from app.models.video_analysis import AnalysisReport, VideoTask, FileRecord
    from app.services.gamification_service import GamificationService

    await _seed_badges(db_session)

    # 创建分析报告
    file_record = FileRecord(
        user_id=auth_user["user_id"], oss_key="test/key", file_size=1048576, file_type="mp4", status="uploaded"
    )
    db_session.add(file_record)
    await db_session.flush()

    task = VideoTask(
        user_id=auth_user["user_id"], file_id=file_record.id, oss_key="test/key",
        status="completed", task_uuid="test-badge-uuid", progress=100
    )
    db_session.add(task)
    await db_session.flush()

    report = AnalysisReport(
        task_id=task.id, user_id=auth_user["user_id"],
        result_data={"technique_stats": {"forehand_drive": 50}},
        report_text={"summary": "test", "issues": [], "suggestions": []},
        is_llm_generated=False,
    )
    db_session.add(report)
    await db_session.commit()

    # 触发积分
    async with async_session_factory() as db:
        await GamificationService.add_points(db, auth_user["user_id"], "analysis")
        await db.commit()

    resp = await client.get("/api/v1/gamification/badges", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    earned_ids = [b["badge_id"] for b in data["earned"]]
    assert "first_analysis" in earned_ids
    assert len(data["earned"]) == 1


# =============================================================================
# 积分规则验证
# =============================================================================

@pytest.mark.asyncio
async def test_add_points_analysis(client, auth_headers, auth_user, db_session):
    """analysis 事件 +10 积分"""
    from app.services.gamification_service import GamificationService

    async with async_session_factory() as db:
        points = await GamificationService.add_points(db, auth_user["user_id"], "analysis")
        await db.commit()
    assert points == 10

    resp = await client.get("/api/v1/gamification/points", headers=auth_headers)
    assert resp.json()["data"]["total_points"] == 10


@pytest.mark.asyncio
async def test_add_points_training_session(client, auth_headers, auth_user, db_session):
    """training_session 事件 +5 积分"""
    from app.services.gamification_service import GamificationService

    async with async_session_factory() as db:
        points = await GamificationService.add_points(db, auth_user["user_id"], "training_session")
        await db.commit()
    assert points == 5

    resp = await client.get("/api/v1/gamification/points", headers=auth_headers)
    assert resp.json()["data"]["total_points"] == 5


@pytest.mark.asyncio
async def test_add_points_nonexistent_event(client, auth_headers, auth_user):
    """未知事件类型返回 0 积分"""
    from app.services.gamification_service import GamificationService

    async with async_session_factory() as db:
        points = await GamificationService.add_points(db, auth_user["user_id"], "unknown_event")
        await db.commit()
    assert points == 0


# =============================================================================
# 连续打卡验证
# =============================================================================

@pytest.mark.asyncio
async def test_streak_after_two_checkins(client, auth_headers, auth_user, db_session):
    """模拟两天打卡验证连续天数"""
    from app.services.gamification_service import GamificationService

    # 今日打卡
    today = date.today()
    cr1 = CheckInRecord(user_id=auth_user["user_id"], checkin_date=today, checkin_type="manual", points_earned=2)
    db_session.add(cr1)

    # 昨天补一条打卡记录
    yesterday = today - timedelta(days=1)
    cr0 = CheckInRecord(user_id=auth_user["user_id"], checkin_date=yesterday, checkin_type="manual", points_earned=2)
    db_session.add(cr0)

    up = UserPoints(user_id=auth_user["user_id"], total_points=4, monthly_points=4, current_streak=2, last_checkin_date=today)
    db_session.add(up)
    await db_session.commit()

    resp = await client.get("/api/v1/gamification/points", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["current_streak"] == 2
    assert data["total_points"] == 4
