"""
tests/unit/test_progress.py - 进度分析模块单元测试

覆盖：快照生成、趋势计算、趋势列表、单项趋势详情、报告对比、综合摘要、问题变化
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.database import async_session_factory
from app.models.progress import ProgressSnapshot, TechniqueTrend
from app.models.user import User
from app.models.video_analysis import AnalysisReport, VideoTask, FileRecord
from app.services.progress_service import ProgressService, METRIC_DEFINITIONS


async def _create_report(db, user_id, idx=0, result_data=None):
    """创建分析报告"""
    if result_data is None:
        result_data = {
            "technique_stats": {"forehand_ratio": 0.50 + idx * 0.05, "backhand_ratio": 0.20, "serve_ratio": 0.10},
            "landing_points": {"distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07}, "dispersion": 2.0},
            "metrics": {"landing_forehand_pct": 0.68, "landing_backhand_pct": 0.25, "landing_middle_pct": 0.07},
            "rally_analysis": {"avg_rally_length": 5.5, "max_rally_length": 12, "rally_frequency": 1.2},
            "ball_speed": {"avg_speed_mps": 18.5, "max_speed_mps": 24.0},
            "score_analysis": {"win_rate": 0.55, "key_point_win_rate": 0.50, "serve_point_win_rate": 0.58, "receive_point_win_rate": 0.45},
            "attack_transition_rate": 0.35,
            "error_rate": 0.12,
        }

    file_record = FileRecord(
        user_id=user_id, oss_key=f"test/key{idx}", file_size=1048576, file_type="mp4", status="uploaded"
    )
    db.add(file_record)
    await db.flush()

    task = VideoTask(
        user_id=user_id, file_id=file_record.id, oss_key=f"test/key{idx}",
        status="completed", task_uuid=f"test-progress-{idx}", progress=100
    )
    db.add(task)
    await db.flush()

    report = AnalysisReport(
        task_id=task.id, user_id=user_id,
        result_data=result_data,
        report_text={
            "summary": f"报告{idx}",
            "issues": [{"problem_id": "P001", "problem_name": "反手偏低"}] if idx == 0 else [],
            "suggestions": [],
        },
        is_llm_generated=False,
        created_at=datetime.now(timezone.utc) - timedelta(days=idx),
    )
    db.add(report)
    await db.flush()
    return report


# =============================================================================
# 快照生成
# =============================================================================

@pytest.mark.asyncio
async def test_generate_snapshot_success(client, auth_headers, auth_user, db_session):
    """快照生成包含 18 项指标"""
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()

    result = await ProgressService.generate_snapshot(auth_user["user_id"], report.id, report.result_data)

    assert result is not None
    assert "metrics_snapshot" in result
    metrics = result["metrics_snapshot"]
    assert len(metrics) == 18
    for key in METRIC_DEFINITIONS:
        assert key in metrics


@pytest.mark.asyncio
async def test_generate_snapshot_idempotent(client, auth_headers, auth_user, db_session):
    """同一报告重复生成快照不重复"""
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()

    await ProgressService.generate_snapshot(auth_user["user_id"], report.id, report.result_data)
    await ProgressService.generate_snapshot(auth_user["user_id"], report.id, report.result_data)

    async with async_session_factory() as db:
        from sqlalchemy import select, func
        count = await db.scalar(
            select(func.count()).select_from(ProgressSnapshot).where(ProgressSnapshot.report_id == report.id)
        )
    assert count == 1


# =============================================================================
# 趋势计算
# =============================================================================

@pytest.mark.asyncio
async def test_trend_new_metric(client, auth_headers, auth_user, db_session):
    """首次分析趋势为 new"""
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()

    await ProgressService.generate_snapshot(auth_user["user_id"], report.id, report.result_data)

    trends = await ProgressService.get_technique_trends(auth_user["user_id"])
    assert len(trends["metrics"]) == 18
    for m in trends["metrics"]:
        assert m["trend"] == "new"
        assert m["current_value"] is not None


@pytest.mark.asyncio
async def test_trend_after_two_snapshots(client, auth_headers, auth_user, db_session):
    """两次快照后趋势计算正确"""
    # 第一次报告
    report1 = await _create_report(db_session, auth_user["user_id"], idx=0)
    await db_session.commit()
    await ProgressService.generate_snapshot(auth_user["user_id"], report1.id, report1.result_data)

    # 第二次报告（指标变化）
    data2 = {
        "technique_stats": {"forehand_ratio": 0.55, "backhand_ratio": 0.25, "serve_ratio": 0.10},
        "landing_points": {"distribution": {"forehand": 0.65, "backhand": 0.28, "middle": 0.07}, "dispersion": 1.8},
        "metrics": {"landing_forehand_pct": 0.65, "landing_backhand_pct": 0.28, "landing_middle_pct": 0.07},
        "rally_analysis": {"avg_rally_length": 6.0, "max_rally_length": 14, "rally_frequency": 1.3},
        "ball_speed": {"avg_speed_mps": 19.5, "max_speed_mps": 25.0},
        "score_analysis": {"win_rate": 0.60, "key_point_win_rate": 0.55, "serve_point_win_rate": 0.60, "receive_point_win_rate": 0.48},
        "attack_transition_rate": 0.38,
        "error_rate": 0.10,
    }
    report2 = await _create_report(db_session, auth_user["user_id"], idx=1, result_data=data2)
    await db_session.commit()
    await ProgressService.generate_snapshot(auth_user["user_id"], report2.id, report2.result_data)

    trends = await ProgressService.get_technique_trends(auth_user["user_id"])
    for m in trends["metrics"]:
        assert m["trend"] is not None
        assert m["trend"] != "new"  # 第二次后不再是 new


# =============================================================================
# 快照列表
# =============================================================================

@pytest.mark.asyncio
async def test_list_snapshots(client, auth_headers, auth_user, db_session):
    """快照列表分页"""
    for i in range(3):
        report = await _create_report(db_session, auth_user["user_id"], idx=i)
        await db_session.commit()
        await ProgressService.generate_snapshot(auth_user["user_id"], report.id, report.result_data)

    resp = await client.get("/api/v1/progress/snapshots", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["page"] == 1


# =============================================================================
# 趋势列表 API
# =============================================================================

@pytest.mark.asyncio
async def test_get_technique_trends_api(client, auth_headers, auth_user, db_session):
    """趋势列表 API"""
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()
    await ProgressService.generate_snapshot(auth_user["user_id"], report.id, report.result_data)

    resp = await client.get("/api/v1/progress/technique-trends", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["metrics"]) == 18
    assert "metric_name" in data["metrics"][0]
    assert "current_value" in data["metrics"][0]


@pytest.mark.asyncio
async def test_get_trend_detail_api(client, auth_headers, auth_user, db_session):
    """单项趋势详情 API"""
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()
    await ProgressService.generate_snapshot(auth_user["user_id"], report.id, report.result_data)

    resp = await client.get("/api/v1/progress/technique-trends/backhand_ratio", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["metric"] == "backhand_ratio"
    assert data["metric_name"] == "反手使用率"
    assert data["trend"] == "new"


@pytest.mark.asyncio
async def test_get_trend_detail_not_found(client, auth_headers):
    """不存在的指标返回 404"""
    resp = await client.get("/api/v1/progress/technique-trends/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


# =============================================================================
# 报告对比
# =============================================================================

@pytest.mark.asyncio
async def test_comparison_success(client, auth_headers, auth_user, db_session):
    """两份报告对比成功"""
    report1 = await _create_report(db_session, auth_user["user_id"], idx=0)
    report2 = await _create_report(db_session, auth_user["user_id"], idx=1)
    await db_session.commit()

    await ProgressService.generate_snapshot(auth_user["user_id"], report1.id, report1.result_data)
    await ProgressService.generate_snapshot(auth_user["user_id"], report2.id, report2.result_data)

    resp = await client.get(
        "/api/v1/progress/comparison",
        params={"report_a": report1.id, "report_b": report2.id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["report_a"]["id"] == report1.id
    assert data["report_b"]["id"] == report2.id
    assert "technique_stats" in data["comparisons"]


@pytest.mark.asyncio
async def test_comparison_same_report(client, auth_headers, auth_user, db_session):
    """相同报告对比返回 422"""
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.get(
        "/api/v1/progress/comparison",
        params={"report_a": report.id, "report_b": report.id},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# =============================================================================
# 综合摘要
# =============================================================================

@pytest.mark.asyncio
async def test_summary_empty_user(client, auth_headers):
    """无数据用户摘要"""
    resp = await client.get("/api/v1/progress/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_analyses"] == 0
    assert data["overall_progress"] == "stagnant"
    assert len(data["metric_trends"]) == 0


@pytest.mark.asyncio
async def test_summary_with_data(client, auth_headers, auth_user, db_session):
    """有数据的摘要"""
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()
    await ProgressService.generate_snapshot(auth_user["user_id"], report.id, report.result_data)

    resp = await client.get("/api/v1/progress/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_analyses"] == 1
    assert len(data["metric_trends"]) == 18


# =============================================================================
# 问题变化
# =============================================================================

@pytest.mark.asyncio
async def test_problem_changes_empty(client, auth_headers):
    """无数据用户问题变化"""
    resp = await client.get("/api/v1/progress/problem-changes", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["new"]) == 0
    assert len(data["resolved"]) == 0
    assert len(data["persistent"]) == 0


@pytest.mark.asyncio
async def test_problem_changes_with_data(client, auth_headers, auth_user, db_session):
    """有报告的问题变化"""
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.get("/api/v1/progress/problem-changes", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["new"]) >= 1  # 首次出现的问题
