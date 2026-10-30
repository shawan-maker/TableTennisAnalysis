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


# =============================================================================
# R12-Prog-9/10: 趋势计算矩阵直调 + period/认证校验
# =============================================================================

def test_calculate_trend_matrix():
    """R12-Prog-9: _calculate_trend 六种趋势类型 + 双方向 + 阈值边界直调

    设计（07-training_advice/backend.md 趋势类型）：new/resolved/achieved/
    improving/declining/stagnant；improving/declining 需 persistence>=2，
    stagnant 需 len>=4 且 persistence>=3；方向 up/down 分别判定。
    """
    from app.services.progress_service import ProgressService

    calc = ProgressService._calculate_trend

    # --- current 为 None：resolved（历史有值）vs new（无历史） ---
    assert calc(1, "backhand_ratio", None, [0.30, 0.32], 0.35) == {
        "trend": "resolved", "persistence_count": 0,
    }
    assert calc(1, "backhand_ratio", None, [], 0.35) == {
        "trend": "new", "persistence_count": 0,
    }

    # --- 历史不足 2 条 → new ---
    assert calc(1, "backhand_ratio", 0.31, [0.30], 0.35) == {
        "trend": "new", "persistence_count": 0,
    }

    # --- achieved：连续 2 次达标（up: v >= target） ---
    assert calc(1, "backhand_ratio", 0.40, [0.36, 0.38], 0.35) == {
        "trend": "achieved", "persistence_count": 2,
    }

    # --- improving（up 方向）：显著改善 + 连续 2 段上升 ---
    # change_rate = (0.36-0.34)/0.34 ≈ 0.059 > 0.05 阈值
    assert calc(1, "backhand_ratio", 0.36, [0.30, 0.32, 0.34], 0.35) == {
        "trend": "improving", "persistence_count": 2,
    }

    # --- improving（down 方向）：显著下降即改善（forehand_ratio 目标 0.60） ---
    # change_rate = (0.60-0.64)/0.64 ≈ -0.063，|·| > 0.05 显著
    assert calc(1, "forehand_ratio", 0.60, [0.72, 0.68, 0.64], 0.60) == {
        "trend": "improving", "persistence_count": 2,
    }

    # --- declining（up 方向）：显著退步 + 连续 2 段下降 ---
    assert calc(1, "backhand_ratio", 0.28, [0.34, 0.32, 0.30], 0.35) == {
        "trend": "declining", "persistence_count": 2,
    }

    # --- stagnant：变化不显著 + len>=4 + 连续 3 段平稳 ---
    # change_rate = (0.307-0.306)/0.306 ≈ 0.003 < 0.05
    assert calc(1, "backhand_ratio", 0.307, [0.300, 0.302, 0.304, 0.306], 0.35) == {
        "trend": "stagnant", "persistence_count": 3,
    }

    # --- fallback：persistence 不足 2 段时按单次方向标记（R5-Prog-2） ---
    assert calc(1, "backhand_ratio", 0.35, [0.30, 0.32], 0.35) == {
        "trend": "improving", "persistence_count": 1,
    }


@pytest.mark.asyncio
async def test_snapshots_invalid_period_422(client, auth_headers):
    """R12-Prog-10: period 非 month/quarter/year/all → 422（Query pattern 校验）"""
    resp = await client.get(
        "/api/v1/progress/snapshots?period=week", headers=auth_headers,
    )
    assert resp.status_code == 422

    # 对照：合法 period → 200
    resp = await client.get(
        "/api/v1/progress/snapshots?period=month", headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_snapshots_no_auth_401(client):
    """R12-Prog-10: 未认证访问快照列表 → 401（AppException ERR_UNAUTHORIZED）"""
    resp = await client.get("/api/v1/progress/snapshots")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 40100  # ERR_UNAUTHORIZED
    assert body["data"] is None
