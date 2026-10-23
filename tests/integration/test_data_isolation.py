"""
tests/integration/test_data_isolation.py — 数据隔离补充测试

覆盖薄弱环节：用户 A 不能访问/操作用户 B 的比赛、分析报告、训练计划、进度快照、游戏化数据
"""

import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.core.security import create_access_token, generate_jti
from app.core.database import async_session_factory
from app.models.user import User
from app.models.match import Match, MatchRecord
from app.models.video_analysis import AnalysisReport, VideoTask, FileRecord
from app.models.training import TrainingPlan
from app.models.progress import ProgressSnapshot
from app.models.gamification import UserPoints, BadgeDefinition, UserBadge
from app.models.notification import NotificationRecord
from sqlalchemy import select


def _auth_headers(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id), 'jti': generate_jti()})}"}


def _unique_oss_key(prefix: str = "test") -> str:
    return f"{prefix}/{uuid.uuid4().hex}.mp4"


@pytest_asyncio.fixture
async def two_users(db_session):
    """创建两个测试用户"""
    user_a = User(openid="iso_user_a", nickname="用户A", status="active")
    user_b = User(openid="iso_user_b", nickname="用户B", status="active")
    db_session.add_all([user_a, user_b])
    await db_session.commit()
    await db_session.refresh(user_a)
    await db_session.refresh(user_b)
    return user_a, user_b


async def _create_report_chain(db_session, user_id: int, oss_key: str = None):
    """创建完整 FileRecord → VideoTask → AnalysisReport 链"""
    key = oss_key or _unique_oss_key()
    file = FileRecord(user_id=user_id, oss_key=key, file_size=1048576, file_type="mp4", status="uploaded")
    db_session.add(file)
    await db_session.flush()
    task = VideoTask(user_id=user_id, file_id=file.id, oss_key=key, task_uuid=uuid.uuid4().hex, status="completed")
    db_session.add(task)
    await db_session.flush()
    report = AnalysisReport(
        task_id=task.id, user_id=user_id,
        result_data={"summary": "test"}, report_text={"summary": "test", "issues": [], "suggestions": []},
    )
    db_session.add(report)
    await db_session.flush()
    return file, task, report


@pytest.mark.asyncio
class TestMatchIsolation:
    """比赛数据隔离"""

    async def test_user_cannot_get_others_match(self, client, two_users, db_session):
        """用户 A 不能查看用户 B 的比赛详情"""
        user_a, user_b = two_users
        match = Match(user_id=user_b.id, opponent_name="B的对手", format="bo1", status="setup")
        db_session.add(match)
        await db_session.commit()
        await db_session.refresh(match)

        resp = await client.get(
            f"/api/v1/scoring/matches/{match.id}",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code in (403, 404)

    async def test_user_cannot_score_others_match(self, client, two_users, db_session):
        """用户 A 不能给用户 B 的比赛记分"""
        user_a, user_b = two_users
        match = Match(user_id=user_b.id, opponent_name="B的比赛", format="bo1", status="in_progress")
        db_session.add(match)
        await db_session.commit()
        await db_session.refresh(match)

        resp = await client.post(
            f"/api/v1/scoring/matches/{match.id}/score",
            json={"scorer": "user", "score_method": "serve_point"},
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code in (403, 404)

    async def test_user_cannot_finish_others_match(self, client, two_users, db_session):
        """用户 A 不能结束用户 B 的比赛"""
        user_a, user_b = two_users
        match = Match(user_id=user_b.id, opponent_name="B的比赛", format="bo1", status="in_progress")
        db_session.add(match)
        await db_session.commit()
        await db_session.refresh(match)

        resp = await client.post(
            f"/api/v1/scoring/matches/{match.id}/finish",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code in (403, 404)

    async def test_match_list_only_own(self, client, two_users, db_session):
        """比赛列表只返回自己的"""
        user_a, user_b = two_users
        match_a = Match(user_id=user_a.id, opponent_name="A的比赛", format="bo1", status="setup")
        match_b = Match(user_id=user_b.id, opponent_name="B的比赛", format="bo1", status="setup")
        db_session.add_all([match_a, match_b])
        await db_session.commit()

        resp = await client.get(
            "/api/v1/scoring/matches",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        items = data.get("items", data) if isinstance(data, dict) else data
        # API 响应不含 user_id，通过 opponent_name 验证隔离
        for item in items:
            assert item.get("opponent_name") == "A的比赛"


@pytest.mark.asyncio
class TestReportIsolation:
    """分析报告隔离"""

    async def test_report_list_only_own(self, client, two_users, db_session):
        """报告列表只返回自己的"""
        user_a, user_b = two_users
        # 用户 B 创建报告
        await _create_report_chain(db_session, user_b.id, oss_key=_unique_oss_key("b"))
        await db_session.commit()

        # 用户 A 查看报告列表
        resp = await client.get(
            "/api/v1/video-analysis/reports",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        items = data.get("items", data) if isinstance(data, dict) else data
        for item in items:
            assert item.get("user_id") != user_b.id

    async def test_report_detail_isolation(self, client, two_users, db_session):
        """用户 A 不能查看用户 B 的报告详情"""
        user_a, user_b = two_users
        _, _, report_b = await _create_report_chain(db_session, user_b.id, oss_key=_unique_oss_key("b2"))
        await db_session.commit()
        await db_session.refresh(report_b)

        resp = await client.get(
            f"/api/v1/video-analysis/reports/{report_b.id}",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code in (403, 404)

    async def test_task_list_only_own(self, client, two_users, db_session):
        """任务列表只返回自己的"""
        user_a, user_b = two_users
        await _create_report_chain(db_session, user_a.id, oss_key=_unique_oss_key("a"))
        await _create_report_chain(db_session, user_b.id, oss_key=_unique_oss_key("b3"))
        await db_session.commit()

        resp = await client.get(
            "/api/v1/video-analysis/tasks",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        items = data.get("items", data) if isinstance(data, dict) else data
        # API 响应不含 user_id/oss_key，验证列表只返回用户 A 的任务（1 条，不含 B 的）
        assert len(items) == 1, f"Expected 1 task for user A, got {len(items)}"


@pytest.mark.asyncio
class TestProgressIsolation:
    """进度快照隔离"""

    async def test_snapshot_list_only_own(self, client, two_users, db_session):
        """进度快照列表只返回自己的"""
        user_a, user_b = two_users
        # 为用户 B 创建完整链 + 快照
        _, _, report_b = await _create_report_chain(db_session, user_b.id, oss_key=_unique_oss_key("snap"))
        snap_b = ProgressSnapshot(
            user_id=user_b.id, report_id=report_b.id,
            metrics_snapshot={"forehand_rate": 0.3},
        )
        db_session.add(snap_b)
        await db_session.commit()

        resp = await client.get(
            "/api/v1/progress/snapshots",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        items = data if isinstance(data, list) else data.get("items", [])
        for item in items:
            assert item.get("user_id") != user_b.id


@pytest.mark.asyncio
class TestGamificationIsolation:
    """游戏化数据隔离"""

    async def test_points_isolation(self, client, two_users, db_session):
        """用户 A 的积分不包含用户 B 的"""
        user_a, user_b = two_users
        points_b = UserPoints(user_id=user_b.id, total_points=999, monthly_points=999)
        db_session.add(points_b)
        await db_session.commit()

        resp = await client.get(
            "/api/v1/gamification/points",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        total = data.get("total_points", 0)
        assert total != 999

    async def test_badges_isolation(self, client, two_users, db_session):
        """用户 A 的徽章不包含用户 B 的"""
        user_a, user_b = two_users
        badge = BadgeDefinition(
            id="test_iso_badge", name="隔离测试徽章",
            icon="🏆", condition={"type": "test"},
        )
        db_session.add(badge)
        await db_session.flush()
        user_badge_b = UserBadge(user_id=user_b.id, badge_id="test_iso_badge")
        db_session.add(user_badge_b)
        await db_session.commit()

        resp = await client.get(
            "/api/v1/gamification/badges",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        badges = data if isinstance(data, list) else data.get("items", data.get("badges", []))
        for b in badges:
            if isinstance(b, dict):
                assert b.get("badge_id") != "test_iso_badge" or b.get("unlocked") is False


@pytest.mark.asyncio
class TestNotificationIsolation:
    """通知数据隔离"""

    async def test_notification_list_only_own(self, client, two_users, db_session):
        """通知列表只返回自己的"""
        user_a, user_b = two_users
        notif_b = NotificationRecord(
            user_id=user_b.id, type="payment_success",
            title="B的通知", content="B的内容",
        )
        db_session.add(notif_b)
        await db_session.commit()

        resp = await client.get(
            "/api/v1/notification/list",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        items = data.get("items", data) if isinstance(data, dict) else data
        for item in items:
            assert item.get("user_id") != user_b.id

    async def test_unread_count_isolation(self, client, two_users, db_session):
        """未读数不包含其他用户的"""
        user_a, user_b = two_users
        # 给 B 创建 3 条未读通知
        for i in range(3):
            notif = NotificationRecord(
                user_id=user_b.id, type="system",
                title=f"B的通知{i}", content="B的内容",
            )
            db_session.add(notif)
        await db_session.commit()

        resp = await client.get(
            "/api/v1/notification/unread-count",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        count = data.get("unread_count", data.get("count", 0)) if isinstance(data, dict) else 0
        assert count < 3  # 用户 A 的未读数不应包含 B 的 3 条


@pytest.mark.asyncio
class TestTrainingIsolation:
    """训练计划隔离"""

    async def test_plan_adjustments_isolation(self, client, two_users, db_session):
        """用户 A 不能查看用户 B 的训练计划调整"""
        user_a, user_b = two_users
        plan_b = TrainingPlan(
            user_id=user_b.id,
            plan_data={"exercises": ["forehand"]},
        )
        db_session.add(plan_b)
        await db_session.commit()
        await db_session.refresh(plan_b)

        resp = await client.get(
            f"/api/v1/training/plans/{plan_b.id}/adjustments",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code in (403, 404)

    async def test_plan_sessions_isolation(self, client, two_users, db_session):
        """用户 A 不能查看用户 B 的训练单"""
        user_a, user_b = two_users
        plan_b = TrainingPlan(
            user_id=user_b.id,
            plan_data={"exercises": ["backhand"]},
        )
        db_session.add(plan_b)
        await db_session.commit()
        await db_session.refresh(plan_b)

        resp = await client.get(
            f"/api/v1/training/plans/{plan_b.id}/sessions",
            headers=_auth_headers(user_a.id),
        )
        assert resp.status_code in (403, 404)
