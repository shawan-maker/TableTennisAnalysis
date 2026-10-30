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
async def test_cache_bust_match_end(client, auth_headers, auth_user, monkeypatch):
    """R12-Dash-1/ND-1: 比赛结束后看板缓存被 bust（match_end 事件范围）"""
    await _create_dashboard_data(client, auth_headers, auth_user)
    user_id = auth_user["user_id"]

    from app.services.dashboard_service import DashboardService
    from app.core.redis import get_redis

    # 填充缓存：overview + winrate 三 period
    await DashboardService.get_overview(user_id)
    for period in ("month", "quarter", "year"):
        await DashboardService.get_win_rate_trend(user_id, period=period)
    # 手动放置 analysis_complete 事件专属 key（technique/heatmap），
    # 用于验证 match_end 的事件范围隔离（不应被误删）
    redis = await get_redis()
    overview_key = f"dashboard:overview:{user_id}"
    technique_key = f"dashboard:technique:{user_id}"
    heatmap_key = f"dashboard:heatmap:{user_id}"
    await redis.set(technique_key, "x", ex=300)
    await redis.set(heatmap_key, "x", ex=300)

    assert await redis.get(overview_key) is not None
    assert await redis.get(f"dashboard:winrate:{user_id}:month") is not None
    assert await redis.get(f"dashboard:winrate:{user_id}:quarter") is not None
    assert await redis.get(f"dashboard:winrate:{user_id}:year") is not None

    # ---- 执行 bust（match_end 事件：service 层直调，主循环内无跨循环风险）----
    # 完整链路分工：
    #   scoring finish_match -> bust_cache_task.delay(user_id, "match_end")
    #   （投递断言见 test_scoring.py SC-1 / test_ai_pipeline.py 级联 spy）
    #   task 体 -> _bust_cache_async -> DashboardService.bust_cache（本测试直调验证）
    await DashboardService.bust_cache(user_id, "match_end")

    # ---- 断言：match_end 事件范围（overview + winrate 三 period 被删）----
    assert await redis.get(overview_key) is None, "overview 缓存应被 bust"
    assert await redis.get(f"dashboard:winrate:{user_id}:month") is None
    assert await redis.get(f"dashboard:winrate:{user_id}:quarter") is None
    assert await redis.get(f"dashboard:winrate:{user_id}:year") is None
    # ---- 断言：事件范围隔离（technique/heatmap 属 analysis_complete，应保留）----
    assert await redis.get(technique_key) is not None, "technique 不属于 match_end 事件范围"
    assert await redis.get(heatmap_key) is not None, "heatmap 不属于 match_end 事件范围"


# =============================================================================
# 落点热图边界分支（R12-Dash-5）
# =============================================================================

async def _create_heatmap_report(user_id: int, result_data, index: int, created_at=None):
    """创建带指定 result_data 的分析报告行（FileRecord + VideoTask + AnalysisReport）"""
    import uuid as _uuid

    async with async_session_factory() as db:
        file_record = FileRecord(
            user_id=user_id,
            oss_key=f"test/heatmap/{user_id}/{index}-{_uuid.uuid4().hex}.mp4",
            original_filename="test.mp4",
            file_size=10 * 1024 * 1024,  # ck_file_size_range 要求 1MB-500MB
            file_type="mp4",
            status="uploaded",
        )
        db.add(file_record)
        await db.flush()

        task = VideoTask(
            user_id=user_id,
            file_id=file_record.id,
            oss_key=file_record.oss_key,
            status="completed",
            task_uuid=f"test-uuid-heatmap-{user_id}-{index}-{_uuid.uuid4().hex}",
            progress=1.0,
            current_step=10,
        )
        db.add(task)
        await db.flush()

        report = AnalysisReport(
            task_id=task.id,
            user_id=user_id,
            report_text={"summary": "s", "issues": [], "suggestions": []},
            result_data=result_data,
        )
        if created_at is not None:
            report.created_at = created_at
        db.add(report)
        await db.commit()
        return report


@pytest.mark.asyncio
async def test_heatmap_field_name_compatibility(db_session, test_user):
    """R12-Dash-5: landing_heatmap（旧字段名）与 landing_points（新字段名）兼容聚合"""
    from app.services.dashboard_service import DashboardService

    grid_a = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    grid_b = [[9, 8, 7], [6, 5, 4], [3, 2, 1]]
    metrics_a = {"landing_forehand_pct": 60, "landing_backhand_pct": 30, "landing_middle_pct": 10}

    # 旧字段名：landing_heatmap + metrics
    await _create_heatmap_report(
        test_user.id,
        {"landing_heatmap": {"nine_grid": grid_a}, "metrics": metrics_a},
        index=0,
    )
    # 新字段名：landing_points.nine_grid（无 metrics → 分布贡献 0）
    await _create_heatmap_report(
        test_user.id,
        {"landing_points": {"nine_grid": grid_b}},
        index=1,
    )

    data = await DashboardService.get_landing_heatmap(test_user.id)

    # 两种字段名的九宫格均被聚合
    assert data["nine_grid"] == [[10, 10, 10], [10, 10, 10], [10, 10, 10]]
    assert data["source_reports_count"] == 2
    assert data["total_rallies"] == 90
    # 分布归一化：仅 report A 的 metrics 贡献（60/30/10 → 归一化 0.6/0.3/0.1）
    # report B 无 metrics 且无 distribution → 逐份回退后贡献 0
    assert data["distribution"]["forehand"] == 0.6
    assert data["distribution"]["backhand"] == 0.3
    assert data["distribution"]["middle"] == 0.1


@pytest.mark.asyncio
async def test_heatmap_malformed_rows_skipped(db_session, test_user):
    """R12-Dash-5: 畸形行跳过 — nine_grid 长度≠3 / 空 nine_grid / 空 result_data"""
    from app.services.dashboard_service import DashboardService

    # nine_grid 只有 2 行（≠3）→ 跳过
    await _create_heatmap_report(
        test_user.id,
        {"landing_points": {"nine_grid": [[1, 2, 3], [4, 5, 6]]}},
        index=0,
    )
    # nine_grid 为空列表 → 跳过
    await _create_heatmap_report(
        test_user.id,
        {"landing_points": {"nine_grid": []}},
        index=1,
    )
    # result_data 为空 dict（falsy）→ 跳过
    await _create_heatmap_report(test_user.id, {}, index=2)

    # 一份合法报告
    await _create_heatmap_report(
        test_user.id,
        {"landing_points": {"nine_grid": [[1, 1, 1], [1, 1, 1], [1, 1, 1]]}},
        index=3,
    )

    data = await DashboardService.get_landing_heatmap(test_user.id)

    # 仅合法行参与聚合（3 份畸形行全部跳过）
    assert data["source_reports_count"] == 1
    assert data["nine_grid"] == [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
    assert data["total_rallies"] == 9


@pytest.mark.asyncio
async def test_heatmap_distribution_fallback_to_landing_points(db_session, test_user):
    """R12-Dash-5: metrics 缺失时回退 landing_points.distribution 读取分布"""
    from app.services.dashboard_service import DashboardService

    await _create_heatmap_report(
        test_user.id,
        {
            "landing_points": {
                "nine_grid": [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
                "distribution": {"forehand": 50, "backhand": 30, "middle": 20},
            },
        },
        index=0,
    )

    data = await DashboardService.get_landing_heatmap(test_user.id)
    # 归一化：50/100=0.5, 30/100=0.3, 20/100=0.2
    assert data["distribution"]["forehand"] == 0.5
    assert data["distribution"]["backhand"] == 0.3
    assert data["distribution"]["middle"] == 0.2


@pytest.mark.asyncio
async def test_heatmap_zero_distribution_guard(db_session, test_user):
    """R12-Dash-5: 分布全 0 → 除零防护，返回全 0 而非异常"""
    from app.services.dashboard_service import DashboardService

    await _create_heatmap_report(
        test_user.id,
        {"landing_points": {"nine_grid": [[1, 1, 1], [1, 1, 1], [1, 1, 1]]}},
        index=0,
    )

    # 无 metrics 且无 distribution → dist_sum=0，不得触发除零
    data = await DashboardService.get_landing_heatmap(test_user.id)
    assert data["distribution"] == {"forehand": 0, "backhand": 0, "middle": 0}
    assert data["source_reports_count"] == 1


@pytest.mark.asyncio
async def test_heatmap_limits_to_10_newest_reports(db_session, test_user):
    """R12-Dash-5: 报告数截断 — 超过 10 份时仅聚合最新 10 份（created_at 倒序）"""
    from app.services.dashboard_service import DashboardService

    now = datetime.now(timezone.utc)

    # 12 份合法报告：i=0 最新 … i=11 最旧；i>=10 的两份带特征值 100
    for i in range(12):
        if i >= 10:
            grid = [[100, 100, 100], [100, 100, 100], [100, 100, 100]]
        else:
            grid = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
        await _create_heatmap_report(
            test_user.id,
            {"landing_points": {"nine_grid": grid}},
            index=i,
            created_at=now - timedelta(hours=i),
        )

    data = await DashboardService.get_landing_heatmap(test_user.id)

    # 仅最新 10 份参与（最旧两份 100 特征值被排除）
    assert data["source_reports_count"] == 10
    assert data["nine_grid"] == [[10, 10, 10], [10, 10, 10], [10, 10, 10]]
    assert data["total_rallies"] == 90
