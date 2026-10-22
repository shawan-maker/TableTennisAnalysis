"""
tests/unit/test_dashboard.py — data_dashboard 模块单元测试

覆盖：概览聚合、战绩趋势、技术统计、落点热图、比赛记录列表、缓存策略
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.database import async_session_factory
from app.models.match import MatchRecord
from app.models.user import User
from app.models.video_analysis import AnalysisReport, VideoTask, FileRecord


# =============================================================================
# 辅助：创建测试数据
# =============================================================================

async def _create_dashboard_data(client, auth_headers, auth_user):
    """创建 3 场比赛 + 2 份分析报告"""
    user_id = auth_user["user_id"]
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        # 3 场比赛（2 胜 1 负）
        matches = []
        for i, (my, opp, is_win) in enumerate([(3, 1, True), (3, 0, True), (1, 3, False)]):
            record = MatchRecord(
                user_id=user_id,
                opponent_name=f"对手{i+1}",
                opponent_rating=1500 + i,
                my_score=my,
                opponent_score=opp,
                is_win=is_win,
                format="bo5",
                match_type="friendly",
                match_date=now - timedelta(days=i),
            )
            db.add(record)
            matches.append(record)

        # 创建 FileRecord + VideoTask + AnalysisReport
        for i in range(2):
            file_record = FileRecord(
                user_id=user_id,
                oss_key=f"test/key{i}",
                file_size=10 * 1024 * 1024,
                file_type="mp4",
                status="uploaded",
            )
            db.add(file_record)
            await db.flush()

            task = VideoTask(
                user_id=user_id,
                file_id=file_record.id,
                oss_key=f"test/key{i}",
                status="completed",
                task_uuid=f"test-uuid-dashboard-{i}",
                progress=100,
            )
            db.add(task)
            await db.flush()

            report = AnalysisReport(
                task_id=task.id,
                user_id=user_id,
                result_data={
                    "technique_distribution": {
                        "forehand_drive": 45 + i * 5,
                        "backhand_drive": 18 + i * 3,
                        "forehand_loop": 12,
                        "serve": 23,
                    },
                    "technique_stats": {  # 兼容字段
                        "forehand_drive": 45 + i * 5,
                        "backhand_drive": 18 + i * 3,
                        "forehand_loop": 12,
                        "serve": 23,
                    },
                    "landing_heatmap": {
                        "nine_grid": [[2+i, 5, 3], [4, 8, 6], [1, 3, 2+i]],
                    },
                    "landing_points": {
                        "nine_grid": [[2+i, 5, 3], [4, 8, 6], [1, 3, 2+i]],
                        "distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07},
                    },
                    "metrics": {
                        "landing_forehand_pct": 0.68,
                        "landing_backhand_pct": 0.25,
                        "landing_middle_pct": 0.07,
                    },
                },
                report_text={
                    "summary": f"第{i+1}份报告摘要",
                    "issues": ["反手使用率偏低"] if i == 0 else [],
                    "suggestions": ["增加反手练习"],
                },
                is_llm_generated=False,
                created_at=now - timedelta(days=i),
            )
            db.add(report)

        await db.commit()

    return {"user_id": user_id, "match_count": 3, "report_count": 2}


# =============================================================================
# 概览测试
# =============================================================================

@pytest.mark.asyncio
async def test_overview_success(client, auth_headers, auth_user):
    """概览卡片正确聚合胜率/分析次数"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["wins"] == 2
    assert data["losses"] == 1
    assert data["analysis_count"] == 2
    assert abs(data["win_rate"] - 0.67) < 0.01
    assert data["training_frequency_per_week"] >= 2
    assert data["streak_days"] == 0  # UserPoints S4 才有
    assert data["trend"] in ("up", "down", "flat")
    assert data["latest_advice_summary"] is not None
    assert data["latest_advice_summary"]["report_id"] is not None


@pytest.mark.asyncio
async def test_overview_empty_user(client, auth_headers):
    """无数据的用户概览返回全零"""
    resp = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["win_rate"] == 0
    assert data["wins"] == 0
    assert data["losses"] == 0
    assert data["analysis_count"] == 0
    assert data["training_frequency_per_week"] == 0
    assert data["latest_advice_summary"] is None


@pytest.mark.asyncio
async def test_overview_unauthorized(client):
    """未登录请求返回 401"""
    resp = await client.get("/api/v1/dashboard/overview")
    assert resp.status_code == 401


# =============================================================================
# 战绩趋势测试
# =============================================================================

@pytest.mark.asyncio
async def test_win_rate_trend_success(client, auth_headers, auth_user):
    """战绩趋势返回日期标签和数据系列"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp = await client.get(
        "/api/v1/dashboard/win-rate-trend?period=month",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["labels"]) > 0
    assert len(data["series"]) == 2
    assert data["series"][0]["name"] == "胜率"
    assert data["series"][1]["name"] == "比赛场次"


@pytest.mark.asyncio
async def test_win_rate_trend_quarter(client, auth_headers, auth_user):
    """季度周期查询"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp = await client.get(
        "/api/v1/dashboard/win-rate-trend?period=quarter",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["labels"]) > 0


# =============================================================================
# 技术统计测试
# =============================================================================

@pytest.mark.asyncio
async def test_technique_stats_success(client, auth_headers, auth_user):
    """技术统计返回环形图分布数据"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp = await client.get("/api/v1/dashboard/technique-stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["technique_distribution"]) == 4
    # 检查色彩映射
    names = [item["name"] for item in data["technique_distribution"]]
    assert "正手攻球" in names
    assert "发球" in names
    # 检查颜色
    for item in data["technique_distribution"]:
        assert item["color"].startswith("#")


@pytest.mark.asyncio
async def test_technique_stats_empty(client, auth_headers):
    """无报告的技术统计返回空列表"""
    resp = await client.get("/api/v1/dashboard/technique-stats", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["technique_distribution"]) == 0


# =============================================================================
# 落点热图测试
# =============================================================================

@pytest.mark.asyncio
async def test_landing_heatmap_success(client, auth_headers, auth_user):
    """落点热图跨多次报告聚合九宫格"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp = await client.get("/api/v1/dashboard/landing-heatmap", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["nine_grid"]) == 3
    assert all(len(row) == 3 for row in data["nine_grid"])
    assert data["source_reports_count"] == 2
    assert data["total_rallies"] > 0
    assert "forehand" in data["distribution"]
    assert "backhand" in data["distribution"]
    assert "middle" in data["distribution"]


@pytest.mark.asyncio
async def test_landing_heatmap_empty(client, auth_headers):
    """无报告的落点热图返回全零"""
    resp = await client.get("/api/v1/dashboard/landing-heatmap", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source_reports_count"] == 0
    assert data["total_rallies"] == 0


# =============================================================================
# 比赛记录列表测试
# =============================================================================

@pytest.mark.asyncio
async def test_match_records_success(client, auth_headers, auth_user):
    """比赛记录列表分页返回"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp = await client.get(
        "/api/v1/dashboard/match-records?page=1&page_size=20",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 3
    # 按日期倒序，最近一场在最前面
    assert data["items"][0]["is_win"] is True


@pytest.mark.asyncio
async def test_match_records_filter_win(client, auth_headers, auth_user):
    """筛选胜利比赛"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp = await client.get(
        "/api/v1/dashboard/match-records?result=win",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert all(item["is_win"] is True for item in data["items"])


@pytest.mark.asyncio
async def test_match_records_filter_lose(client, auth_headers, auth_user):
    """筛选失败比赛"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp = await client.get(
        "/api/v1/dashboard/match-records?result=lose",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert all(item["is_win"] is False for item in data["items"])


# =============================================================================
# 缓存策略测试
# =============================================================================

@pytest.mark.asyncio
async def test_cache_hit(client, auth_headers, auth_user):
    """概览缓存命中 — 第二次请求返回相同数据"""
    await _create_dashboard_data(client, auth_headers, auth_user)

    resp1 = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
    resp2 = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["data"] == resp2.json()["data"]


@pytest.mark.asyncio
async def test_cache_bust_analysis(client, auth_headers, auth_user):
    """分析完成后缓存被 bust"""
    await _create_dashboard_data(client, auth_headers, auth_user)
    user_id = auth_user["user_id"]

    from app.services.dashboard_service import DashboardService
    from app.core.redis import get_redis

    # 填充缓存
    await DashboardService.get_overview(user_id)
    await DashboardService.get_technique_stats(user_id)
    await DashboardService.get_landing_heatmap(user_id)

    # 验证缓存存在
    redis = await get_redis()
    assert await redis.get(f"dashboard:overview:{user_id}") is not None
    assert await redis.get(f"dashboard:technique:{user_id}") is not None
    assert await redis.get(f"dashboard:heatmap:{user_id}") is not None

    # bust
    await DashboardService.bust_cache(user_id, event="analysis_complete")

    # 验证缓存已清除
    assert await redis.get(f"dashboard:overview:{user_id}") is None
    assert await redis.get(f"dashboard:technique:{user_id}") is None
    assert await redis.get(f"dashboard:heatmap:{user_id}") is None


@pytest.mark.asyncio
async def test_cache_bust_match_end(client, auth_headers, auth_user):
    """比赛结束后缓存被 bust"""
    await _create_dashboard_data(client, auth_headers, auth_user)
    user_id = auth_user["user_id"]

    from app.services.dashboard_service import DashboardService
    from app.core.redis import get_redis

    # 填充缓存
    await DashboardService.get_overview(user_id)
    await DashboardService.get_win_rate_trend(user_id, period="month")

    redis = await get_redis()
    assert await redis.get(f"dashboard:overview:{user_id}") is not None
    assert await redis.get(f"dashboard:winrate:{user_id}:month") is not None

    # bust
    await DashboardService.bust_cache(user_id, event="match_end")

    assert await redis.get(f"dashboard:overview:{user_id}") is None
    assert await redis.get(f"dashboard:winrate:{user_id}:month") is None
