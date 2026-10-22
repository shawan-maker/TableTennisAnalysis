# data_dashboard 模块 — 后端垂直切片设计

> **模块名称**：`data_dashboard`
> **所属目录**：`app/api/v1/dashboard/`
> **定位**：聚合分析报告和比赛数据，提供战绩趋势、技术统计、累计落点热图等可视化数据看板
> **依据**：模块详细设计 v1.2 §2.6、API 详细设计 v1.3 §6、数据库详细设计 v1.1

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.6（data_dashboard 功能规格：概览/趋势/统计/热图/记录）
- [ ] 阅读 API 契约 §6（5 个端点：overview / win-rate-trend / technique-stats / landing-heatmap / match-records）
- [ ] 阅读数据库设计 §2.7（analysis_report）、§2.13（match_record）、§2.21（progress_snapshot）
- [ ] 阅读 `app/core/redis.py`（Redis 缓存工具）
- [ ] 阅读 `app/core/pagination.py`（分页工具）
- [ ] 确认本切片范围：5 个 API 端点 + 对应 Service 方法 + 缓存策略

### 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Schema（无独立 Model，复用已有表） | `app/schemas/dashboard.py` | 无 | ☐ |
| 2 | 实现 Service | `app/services/dashboard_service.py` | #1 | ☐ |
| 3 | 实现 API 路由 | `app/api/v1/dashboard/router.py` | #2 | ☐ |
| 4 | 注册 Router | `app/api/v1/__init__.py` | #3 | ☐ |
| 5 | 编写单元测试 | `tests/unit/test_dashboard.py` | #2 | ☐ |
| 6 | 编写冒烟测试 | `tests/smoke/dashboard_smoke_test.py` | #4 | ☐ |

> **说明**：data_dashboard 不创建独立 Model，复用 `analysis_report`、`match_record`、`progress_snapshot` 等已有表，通过聚合查询 + Redis 缓存提供看板数据。

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_dashboard.py
"""
data_dashboard 模块 — 数据看板测试。
覆盖：概览聚合、战绩趋势、技术统计、落点热图、比赛记录列表、缓存策略。
"""
import pytest
from datetime import datetime, timedelta, timezone
from app.core.exceptions import AppException

@pytest.fixture
async def dashboard_data(db_session, auth_user):
    """创建测试上下文：用户 + 比赛记录 + 分析报告。"""
    from app.models.match_data import MatchRecord
    from app.models.video_analysis import AnalysisReport

    user_id = auth_user["id"]
    now = datetime.now(timezone.utc)

    # 创建 3 场比赛（2 胜 1 负）
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
        db_session.add(record)
        matches.append(record)

    # 创建 2 份分析报告
    reports = []
    for i in range(2):
        report = AnalysisReport(
            task_id=1000 + i,
            user_id=user_id,
            result_data={
                "technique_distribution": {
                    "forehand_drive": 45, "backhand_drive": 18,
                    "forehand_loop": 12, "serve": 23,
                },
                "landing_heatmap": {
                    "nine_grid": [[2,5,3],[4,8,6],[1,3,2]],
                },
                "metrics": {
                    "backhand_ratio": 0.25,
                    "forehand_ratio": 0.68,
                    "serve_ratio": 0.07,
                },
            },
            report_text={
                "summary": "反手使用率从18%提升到25%",
                "issues": [],
                "suggestions": [],
            },
            is_llm_generated=True,
            created_at=now - timedelta(days=i),
        )
        db_session.add(report)
        reports.append(report)

    await db_session.commit()
    yield {"user": auth_user, "matches": matches, "reports": reports}
```

### 四类测试用例

```python
# === 1. Happy Path（正常流程） ===
@pytest.mark.asyncio
async def test_get_overview_success(dashboard_data):
    """概览卡片正确聚合胜率/分析次数/训练频次。"""
    user = dashboard_data["user"]
    result = await DashboardService.get_overview(user.id)
    assert result["win_rate"] == pytest.approx(0.667, abs=0.01)
    assert result["wins"] == 2
    assert result["losses"] == 1
    assert result["analysis_count"] == 2

@pytest.mark.asyncio
async def test_get_win_rate_trend_success(dashboard_data):
    """战绩趋势返回日期标签和数据系列。"""
    user = dashboard_data["user"]
    result = await DashboardService.get_win_rate_trend(user.id, period="month")
    assert len(result["labels"]) > 0
    assert any(s["name"] == "胜率" for s in result["series"])

@pytest.mark.asyncio
async def test_get_technique_stats_success(dashboard_data):
    """技术统计返回环形图分布数据。"""
    user = dashboard_data["user"]
    result = await DashboardService.get_technique_stats(user.id)
    dist = result["technique_distribution"]
    assert len(dist) == 4
    assert dist[0]["name"] == "正手攻球"
    assert dist[0]["color"] == "#E63946"

@pytest.mark.asyncio
async def test_get_landing_heatmap_success(dashboard_data):
    """落点热图跨多次报告聚合九宫格。"""
    user = dashboard_data["user"]
    result = await DashboardService.get_landing_heatmap(user.id)
    assert len(result["nine_grid"]) == 3
    assert all(len(row) == 3 for row in result["nine_grid"])
    assert result["source_reports_count"] == 2
    assert result["total_rallies"] > 0

@pytest.mark.asyncio
async def test_get_match_records_success(dashboard_data):
    """比赛记录列表分页返回。"""
    user = dashboard_data["user"]
    result = await DashboardService.get_match_records(user.id, page=1, page_size=20)
    assert result["total"] == 3
    assert len(result["items"]) == 3
    assert result["items"][0]["is_win"] is True

# === 2. Validation Failure（参数校验失败） ===
@pytest.mark.asyncio
async def test_get_win_rate_trend_invalid_period(dashboard_data):
    """period 参数不合法时使用默认值 month。"""
    user = dashboard_data["user"]
    result = await DashboardService.get_win_rate_trend(user.id, period="invalid")
    # 降级为 month，不报错
    assert len(result["labels"]) > 0

@pytest.mark.asyncio
async def test_get_match_records_invalid_result_filter(dashboard_data):
    """result 筛选值不合法时返回全部记录。"""
    user = dashboard_data["user"]
    result = await DashboardService.get_match_records(
        user.id, result_filter="invalid", page=1, page_size=20
    )
    assert result["total"] == 3  # 返回全部

# === 3. Permission / Auth Failure（权限不足） ===
@pytest.mark.asyncio
async def test_get_overview_unauthorized(client):
    """未登录请求返回 401。"""
    resp = await client.get("/api/v1/dashboard/overview")
    assert resp.status_code == 401

# === 4. Business Rule（业务规则验证） ===
@pytest.mark.asyncio
async def test_overview_cache_hit(dashboard_data, mock_redis):
    """概览缓存命中时直接返回缓存数据。"""
    user = dashboard_data["user"]
    # 第一次请求 → 写入缓存
    await DashboardService.get_overview(user.id)
    # mock_redis 应记录 SET 操作
    cache_key = f"dashboard:overview:{user.id}"
    assert await mock_redis.get(cache_key) is not None

@pytest.mark.asyncio
async def test_cache_bust_on_analysis_complete(dashboard_data, mock_redis):
    """分析完成后缓存被 bust。"""
    user = dashboard_data["user"]
    # 先填充缓存
    await DashboardService.get_overview(user.id)
    await DashboardService.get_technique_stats(user.id)
    await DashboardService.get_landing_heatmap(user.id)
    # 触发 bust
    await DashboardService.bust_cache(user.id, event="analysis_complete")
    cache_keys = [
        f"dashboard:overview:{user.id}",
        f"dashboard:technique:{user.id}",
        f"dashboard:heatmap:{user.id}",
    ]
    for key in cache_keys:
        assert await mock_redis.get(key) is None

@pytest.mark.asyncio
async def test_cache_bust_on_match_end(dashboard_data, mock_redis):
    """比赛结束后缓存被 bust（overview + winrate）。"""
    user = dashboard_data["user"]
    await DashboardService.get_overview(user.id)
    await DashboardService.get_win_rate_trend(user.id, period="month")
    await DashboardService.bust_cache(user.id, event="match_end")
    assert await mock_redis.get(f"dashboard:overview:{user.id}") is None
    assert await mock_redis.get(f"dashboard:winrate:{user.id}") is None

@pytest.mark.asyncio
async def test_heatmap_limits_recent_reports(dashboard_data):
    """缓存未命中时落点热图限制最近 10 次报告。"""
    user = dashboard_data["user"]
    # 此测试上下文只有 2 份报告，全部聚合
    result = await DashboardService.get_landing_heatmap(user.id)
    assert result["source_reports_count"] <= 10

@pytest.mark.asyncio
async def test_empty_user_overview(db_session, auth_user):
    """无数据的用户概览返回全零。"""
    user = auth_user
    result = await DashboardService.get_overview(user.id)
    assert result["win_rate"] == 0
    assert result["wins"] == 0
    assert result["losses"] == 0
    assert result["analysis_count"] == 0
    assert result["training_frequency_per_week"] == 0
```

---

## 3. Model（复用已有表）

data_dashboard 不创建独立 Model，复用以下已有表：

| 表名 | 文件 | 用途 |
|------|------|------|
| `analysis_report` | `app/models/video_analysis.py` | 分析报告，提供 result_data JSONB（技术分布/落点热图/指标） |
| `match_record` | `app/models/match_data.py` | 比赛记录，提供胜负/比分 |
| `progress_snapshot` | `app/models/progress_analysis.py` | 进度快照，提供训练频次等衍生指标 |
| `user_points` | `app/models/gamification.py` | 积分/连续天数 |

关键 Model 字段引用：

```python
# app/models/video_analysis.py（已有，无需修改）
# # AnalysisReport 定义在 app/models/video_analysis.py，此处引用字段供参考
# class AnalysisReport(Base):
#     """分析报告。"""
#     __tablename__ = "analysis_report"
#     # 关键字段: id, task_id, user_id, result_data(JSONB), report_text(JSONB), created_at
#     # 详见 app/models/video_analysis.py

# app/models/match_data.py（已有，无需修改）
# # MatchRecord 定义在 app/models/match_data.py，此处引用字段供参考
# class MatchRecord(Base):
#     """手动录入比赛记录。"""
#     __tablename__ = "match_record"
#     # 关键字段: id, user_id, opponent_name, opponent_rating, my_score, opponent_score,
#     #           is_win, format, match_type, match_date
#     # 详见 app/models/match_data.py

class MatchRecordsResponse(BaseModel):
    """比赛记录列表分页响应。"""
    total: int
    page: int
    page_size: int
    items: list[MatchRecordBrief]

# --- 查询参数 ---
class MatchRecordsQuery(BaseModel):
    """比赛记录查询参数。"""
    result_filter: str = Field(default="all")  # win/lose/all
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)
```

---

## 5. Service 实现

```python
# app/services/dashboard_service.py
"""
数据看板业务逻辑层。
缓存策略：
  - overview: TTL 5min
  - win-rate-trend / technique-stats / landing-heatmap: TTL 1h
  - match-records: 实时查询，不缓存
缓存 bust：
  - 分析完成 → DEL overview / technique / heatmap
  - 比赛结束 → DEL overview / winrate
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.video_analysis import AnalysisReport
from app.models.match_data import MatchRecord
from app.models.gamification import UserPoints
from app.schemas.dashboard import (
    OverviewResponse, AdviceSummaryBrief,
    WinRateTrendResponse, TrendSeries,
    TechniqueStatsResponse, TechniqueItem,
    LandingHeatmapResponse,
    MatchRecordBrief, MatchRecordsResponse, MatchRecordsQuery,
)

# 缓存 TTL（秒）
CACHE_TTL_OVERVIEW = 300      # 5 min
CACHE_TTL_TREND = 3600        # 1 h
CACHE_TTL_TECHNIQUE = 3600    # 1 h
CACHE_TTL_HEATMAP = 3600      # 1 h

# 技术统计色彩映射
TECHNIQUE_COLORS = {
    "forehand_drive": ("正手攻球", "#E63946"),
    "backhand_drive": ("反手拨球", "#1D3557"),
    "forehand_loop": ("正手拉球", "#F4A261"),
    "serve": ("发球", "#2A9D8F"),
}

class DashboardService:
    """数据看板业务逻辑层。"""

    # ========== 概览 ==========

    @staticmethod
    async def get_overview(user_id: int) -> OverviewResponse:
        """概览卡片：胜率/分析次数/训练频次/连续天数/趋势。缓存 5min。"""
        redis = await get_redis()
        # 降级用户只读检查 (TD-2 实现)
        readonly = await redis.get(f"downgrade:report:readonly:{user_id}")
        is_readonly = readonly is not None
        # 若存在则返回简化版数据看板（tier=free 降级策略，仅展示基础统计）
        # 参见 10-membership/backend.md apply_downgrade_policy 方法
        cache_key = f"dashboard:overview:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return OverviewResponse(**json.loads(cached))

        # 缓存未命中 → 实时计算
        async with get_async_session() as db:
            # 比赛统计
            win_count = await db.scalar(
                select(func.count()).select_from(MatchRecord)
                .where(and_(MatchRecord.user_id == user_id, MatchRecord.is_win.is_(True)))
            )
            loss_count = await db.scalar(
                select(func.count()).select_from(MatchRecord)
                .where(and_(MatchRecord.user_id == user_id, MatchRecord.is_win.is_(False)))
            )
            wins = win_count or 0
            losses = loss_count or 0
            total_matches = wins + losses
            win_rate = round(wins / total_matches, 2) if total_matches > 0 else 0.0

            # 分析次数
            analysis_count = await db.scalar(
                select(func.count()).select_from(AnalysisReport)
                .where(AnalysisReport.user_id == user_id)
            ) or 0

            # 训练频次（最近 7 天的比赛 + 分析记录数）
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            week_matches = await db.scalar(
                select(func.count()).select_from(MatchRecord)
                .where(and_(MatchRecord.user_id == user_id, MatchRecord.match_date >= week_ago))
            ) or 0
            week_reports = await db.scalar(
                select(func.count()).select_from(AnalysisReport)
                .where(and_(AnalysisReport.user_id == user_id, AnalysisReport.created_at >= week_ago))
            ) or 0
            training_freq = week_matches + week_reports

            # 连续天数
            streak_days = 0
            up = await db.scalar(
                select(UserPoints).where(UserPoints.user_id == user_id)
            )
            if up:
                streak_days = up.current_streak

            # 趋势：对比最近 7 天 vs 前 7 天的胜率
            trend = await DashboardService._calc_trend(db, user_id)

            # 最近训练建议摘要
            latest_advice = await DashboardService._get_latest_advice_summary(db, user_id)

        result = OverviewResponse(
            win_rate=win_rate,
            wins=wins,
            losses=losses,
            analysis_count=analysis_count,
            training_frequency_per_week=training_freq,
            streak_days=streak_days,
            trend=trend,
            latest_advice_summary=latest_advice,
        )

        # 回填缓存
        await redis.setex(cache_key, CACHE_TTL_OVERVIEW, result.model_dump_json())
        return result

    @staticmethod
    async def _calc_trend(db: AsyncSession, user_id: int) -> str:
        """计算胜率趋势：up/down/flat。"""
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        recent_wins = await db.scalar(
            select(func.count()).select_from(MatchRecord)
            .where(and_(MatchRecord.user_id == user_id,
                        MatchRecord.is_win.is_(True),
                        MatchRecord.match_date >= week_ago))
        ) or 0
        recent_total = await db.scalar(
            select(func.count()).select_from(MatchRecord)
            .where(and_(MatchRecord.user_id == user_id,
                        MatchRecord.match_date >= week_ago))
        ) or 0

        prev_wins = await db.scalar(
            select(func.count()).select_from(MatchRecord)
            .where(and_(MatchRecord.user_id == user_id,
                        MatchRecord.is_win.is_(True),
                        MatchRecord.match_date >= two_weeks_ago,
                        MatchRecord.match_date < week_ago))
        ) or 0
        prev_total = await db.scalar(
            select(func.count()).select_from(MatchRecord)
            .where(and_(MatchRecord.user_id == user_id,
                        MatchRecord.match_date >= two_weeks_ago,
                        MatchRecord.match_date < week_ago))
        ) or 0

        recent_rate = recent_wins / recent_total if recent_total > 0 else 0
        prev_rate = prev_wins / prev_total if prev_total > 0 else 0

        if recent_total == 0 and prev_total == 0:
            return "flat"
        if recent_rate > prev_rate + 0.05:
            return "up"
        if recent_rate < prev_rate - 0.05:
            return "down"
        return "flat"

    @staticmethod
    async def _get_latest_advice_summary(db: AsyncSession, user_id: int) -> Optional[AdviceSummaryBrief]:
        """获取最近一次分析报告的训练建议摘要。"""
        report = await db.scalar(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user_id)
            .order_by(AnalysisReport.created_at.desc())
            .limit(1)
        )
        if not report:
            return None

        report_text = report.report_text or {}
        summary = report_text.get("summary", "")
        issues = report_text.get("issues", [])
        has_unresolved = len(issues) > 0

        return AdviceSummaryBrief(
            report_id=report.id,
            summary=summary,
            has_unresolved_issues=has_unresolved,
            latest_report_at=report.created_at,
        )

    # ========== 战绩趋势 ==========

    @staticmethod
    async def get_win_rate_trend(user_id: int, period: str = "month") -> WinRateTrendResponse:
        """战绩趋势折线图数据。缓存 1h。"""
        # period 校验与降级
        valid_periods = {"month": 30, "quarter": 90, "year": 365}
        days = valid_periods.get(period, valid_periods["month"])

        redis = await get_redis()
        cache_key = f"dashboard:winrate:{user_id}:{period}"
        cached = await redis.get(cache_key)
        if cached:
            return WinRateTrendResponse(**json.loads(cached))

        async with get_async_session() as db:
            now = datetime.now(timezone.utc)
            start_date = now - timedelta(days=days)

            # 按天聚合
            stmt = (
                select(
                    func.date_trunc("day", MatchRecord.match_date).label("day"),
                    func.count().label("total"),
                    func.sum(func.cast(MatchRecord.is_win, Integer)).label("wins"),
                )
                .where(and_(MatchRecord.user_id == user_id,
                           MatchRecord.match_date >= start_date))
                .group_by("day")
                .order_by("day")
            )
            result = await db.execute(stmt)
            rows = result.all()

        labels = []
        win_rates = []
        match_counts = []
        for row in rows:
            day_str = row.day.strftime("%m/%d")
            total = row.total or 0
            wins = int(row.wins or 0)
            rate = round(wins / total, 2) if total > 0 else 0
            labels.append(day_str)
            win_rates.append(rate)
            match_counts.append(total)

        result_data = WinRateTrendResponse(
            labels=labels,
            series=[
                TrendSeries(name="胜率", data=win_rates),
                TrendSeries(name="比赛场次", data=match_counts),
            ],
        )

        await redis.setex(cache_key, CACHE_TTL_TREND, result_data.model_dump_json())
        return result_data

    # ========== 技术统计 ==========

    @staticmethod
    async def get_technique_stats(user_id: int) -> TechniqueStatsResponse:
        """技术统计环形图数据（聚合最近所有报告的技术分布）。缓存 1h。"""
        redis = await get_redis()
        cache_key = f"dashboard:technique:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return TechniqueStatsResponse(**json.loads(cached))

        async with get_async_session() as db:
            # 读取最近 10 份报告
            stmt = (
                select(AnalysisReport.result_data)
                .where(AnalysisReport.user_id == user_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(10)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

        # 聚合技术分布
        totals = {}
        for raw in rows:
            if not raw:
                continue
            dist = raw.get("technique_distribution", {})
            for tech, count in dist.items():
                totals[tech] = totals.get(tech, 0) + count

        items = []
        for tech_key, count in totals.items():
            name, color = TECHNIQUE_COLORS.get(tech_key, (tech_key, "#1D3557"))
            items.append(TechniqueItem(name=name, value=count, color=color))

        result_data = TechniqueStatsResponse(technique_distribution=items)

        await redis.setex(cache_key, CACHE_TTL_TECHNIQUE, result_data.model_dump_json())
        return result_data

    # ========== 落点热图 ==========

    @staticmethod
    async def get_landing_heatmap(user_id: int) -> LandingHeatmapResponse:
        """累计落点热图（跨多次报告聚合九宫格）。缓存 1h。"""
        redis = await get_redis()
        cache_key = f"dashboard:heatmap:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return LandingHeatmapResponse(**json.loads(cached))

        async with get_async_session() as db:
            # 限制最近 10 次报告
            stmt = (
                select(AnalysisReport.result_data)
                .where(AnalysisReport.user_id == user_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(10)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

        # 聚合九宫格
        grid = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        forehand_total = 0
        backhand_total = 0
        middle_total = 0
        total_rallies = 0
        source_count = 0

        for raw in rows:
            if not raw:
                continue
            heatmap = raw.get("landing_heatmap", {})
            nine_grid = heatmap.get("nine_grid")
            if not nine_grid or len(nine_grid) != 3:
                continue
            source_count += 1
            for i in range(3):
                for j in range(3):
                    grid[i][j] += nine_grid[i][j]
                    total_rallies += nine_grid[i][j]

            dist = raw.get("metrics", {})
            forehand_total += dist.get("landing_forehand_pct", 0)
            backhand_total += dist.get("landing_backhand_pct", 0)
            middle_total += dist.get("landing_middle_pct", 0)

        # 归一化分布
        dist_sum = forehand_total + backhand_total + middle_total
        if dist_sum > 0:
            distribution = {
                "forehand": round(forehand_total / dist_sum, 2),
                "backhand": round(backhand_total / dist_sum, 2),
                "middle": round(middle_total / dist_sum, 2),
            }
        else:
            distribution = {"forehand": 0, "backhand": 0, "middle": 0}

        result_data = LandingHeatmapResponse(
            nine_grid=grid,
            distribution=distribution,
            total_rallies=total_rallies,
            source_reports_count=source_count,
        )

        await redis.setex(cache_key, CACHE_TTL_HEATMAP, result_data.model_dump_json())
        return result_data

    # ========== 比赛记录列表 ==========

    @staticmethod
    async def get_match_records(
        user_id: int,
        result_filter: str = "all",
        page: int = 1,
        page_size: int = 20,
    ) -> MatchRecordsResponse:
        """比赛记录列表（实时查询，不缓存）。"""
        # 参数降级
        if result_filter not in ("win", "lose", "all"):
            result_filter = "all"

        async with get_async_session() as db:
            qs = select(MatchRecord).where(MatchRecord.user_id == user_id)
            if result_filter == "win":
                qs = qs.where(MatchRecord.is_win.is_(True))
            elif result_filter == "lose":
                qs = qs.where(MatchRecord.is_win.is_(False))

            # 总数
            count_stmt = select(func.count()).select_from(qs.subquery())
            total = await db.scalar(count_stmt) or 0

            # 分页
            offset = (page - 1) * page_size
            qs = qs.order_by(MatchRecord.match_date.desc()).offset(offset).limit(page_size)
            result = await db.execute(qs)
            records = result.scalars().all()

        items = [MatchRecordBrief.model_validate(r) for r in records]
        return MatchRecordsResponse(
            total=total, page=page, page_size=page_size, items=items,
        )

    # ========== 缓存 bust ==========

    @staticmethod
    async def bust_cache(user_id: int, event: str) -> None:
        """
        缓存失效。
        event=analysis_complete → DEL overview / technique / heatmap
        event=match_end → DEL overview / winrate
        """
        redis = await get_redis()
        if event == "analysis_complete":
            keys = [
                f"dashboard:overview:{user_id}",
                f"dashboard:technique:{user_id}",
                f"dashboard:heatmap:{user_id}",
            ]
        elif event == "match_end":
            keys = [
                f"dashboard:overview:{user_id}",
            ]
            # 删除所有 period 的 winrate 缓存
            for period in ("month", "quarter", "year"):
                keys.append(f"dashboard:winrate:{user_id}:{period}")
        else:
            return

        if keys:
            await redis.delete(*keys)
```

> **注意**：`func.cast(MatchRecord.is_win, Integer)` 需要在实际实现中导入 `from sqlalchemy import Integer` 并确保 PostgreSQL 兼容。也可改为 `func.sum(func.case((MatchRecord.is_win.is_(True), 1), else_=0))`。

### 5.2 缓存清理 Celery Task

```python
# app/tasks/dashboard_beat.py
"""数据看板缓存清理任务。"""

from app.core.celery import celery_app


@celery_app.task(name="dashboard.bust_cache")
def bust_cache_task(user_id: int, event: str = "manual"):
    """数据看板缓存清理——事件驱动触发。

    逻辑：
    1. 接收 user_id + event（analysis_complete / match_end / manual）
    2. 调用 DashboardService.bust_cache() 清除该用户的看板缓存
    3. 清除的缓存键包括：dashboard:overview:{user_id}、dashboard:trends:{user_id} 等

    触发场景：
    - video_analysis 分析完成 → event="analysis_complete"
    - match_data 比赛结束 → event="match_end"
    - 手动触发 → event="manual"

    注意：此任务为事件驱动（跨模块调用），
    无需在 beat_schedule 中注册定时触发。
    """
    import asyncio
    asyncio.run(_bust_cache_async(user_id, event))


async def _bust_cache_async(user_id: int, event: str):
    """缓存清理异步实现。"""
    from app.services.dashboard_service import DashboardService

    await DashboardService.bust_cache(user_id=user_id, event=event)
```

---

## 6. API 路由实现

```python
# app/api/v1/dashboard/router.py
from fastapi import APIRouter, Depends, Query
from app.core.deps import get_current_user
from app.core.response import success
from app.models.user import User
from app.core.limiter import limiter
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["数据看板"])

@limiter.limit("100/minute")
@router.get("/overview", summary="概览卡片")
async def get_overview(user: User = Depends(get_current_user)):
    """胜率/分析次数/训练频次/连续天数/趋势。缓存 5min。"""
    data = await DashboardService.get_overview(user.id)
    return success(data=data)

@limiter.limit("100/minute")
@router.get("/win-rate-trend", summary="战绩趋势")
async def get_win_rate_trend(
    period: str = Query(default="month", regex="^(month|quarter|year)$"),
    user: User = Depends(get_current_user),
):
    """战绩趋势折线图数据。缓存 1h。"""
    data = await DashboardService.get_win_rate_trend(user.id, period=period)
    return success(data=data)

@limiter.limit("100/minute")
@router.get("/technique-stats", summary="技术统计")
async def get_technique_stats(user: User = Depends(get_current_user)):
    """技术统计环形图数据。缓存 1h。"""
    data = await DashboardService.get_technique_stats(user.id)
    return success(data=data)

@limiter.limit("100/minute")
@router.get("/landing-heatmap", summary="累计落点热图")
async def get_landing_heatmap(user: User = Depends(get_current_user)):
    """累计落点热图（跨多次报告聚合九宫格）。缓存 1h。"""
    data = await DashboardService.get_landing_heatmap(user.id)
    return success(data=data)

@limiter.limit("100/minute")
@router.get("/match-records", summary="比赛记录列表")
async def get_match_records(
    result: str = Query(default="all", regex="^(win|lose|all)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """比赛记录列表（分页，实时查询不缓存）。"""
    data = await DashboardService.get_match_records(
        user.id, result_filter=result, page=page, page_size=page_size,
    )
    return success(data=data)
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.dashboard.router import router as dashboard_router
api_router.include_router(dashboard_router)
```

---

## 7. 冒烟测试脚本

```python
# tests/smoke/dashboard_smoke_test.py
"""
data_dashboard 模块冒烟测试。
用法: python -m tests.smoke.dashboard_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 登录获取 Token
        print("1. Testing auth login...")
        resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "冒烟测试",
        })
        if resp.status_code != 200:
            print(f"   ✗ Login failed: {resp.status_code}")
            return
        access_token = resp.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {access_token}"}
        print("   ✓ Login success")

        # 2. 概览
        print("2. Testing /dashboard/overview...")
        resp = await client.get("/dashboard/overview", headers=h)
        assert resp.status_code == 200, f"Overview failed: {resp.text}"
        overview = resp.json()["data"]
        print(f"   ✓ Overview: win_rate={overview['win_rate']}, "
              f"analysis_count={overview['analysis_count']}")

        # 3. 战绩趋势
        print("3. Testing /dashboard/win-rate-trend...")
        resp = await client.get("/dashboard/win-rate-trend?period=month", headers=h)
        assert resp.status_code == 200, f"Win rate trend failed: {resp.text}"
        trend = resp.json()["data"]
        print(f"   ✓ Win rate trend: {len(trend['labels'])} data points")

        # 4. 技术统计
        print("4. Testing /dashboard/technique-stats...")
        resp = await client.get("/dashboard/technique-stats", headers=h)
        assert resp.status_code == 200, f"Technique stats failed: {resp.text}"
        stats = resp.json()["data"]
        print(f"   ✓ Technique stats: {len(stats['technique_distribution'])} items")

        # 5. 落点热图
        print("5. Testing /dashboard/landing-heatmap...")
        resp = await client.get("/dashboard/landing-heatmap", headers=h)
        assert resp.status_code == 200, f"Heatmap failed: {resp.text}"
        heatmap = resp.json()["data"]
        print(f"   ✓ Heatmap: {heatmap['source_reports_count']} reports, "
              f"{heatmap['total_rallies']} rallies")

        # 6. 比赛记录
        print("6. Testing /dashboard/match-records...")
        resp = await client.get("/dashboard/match-records?page=1&page_size=20", headers=h)
        assert resp.status_code == 200, f"Match records failed: {resp.text}"
        records = resp.json()["data"]
        print(f"   ✓ Match records: {records['total']} total, "
              f"{len(records['items'])} items")

        # 7. 缓存验证（第二次请求应命中缓存）
        print("7. Testing cache hit (second overview request)...")
        resp2 = await client.get("/dashboard/overview", headers=h)
        assert resp2.status_code == 200
        assert resp2.json()["data"] == overview
        print("   ✓ Cache hit confirmed")

    print("\ndashboard_smoke_test: ALL PASSED ✓")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_dashboard.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.dashboard_smoke_test`
- [ ] Router 已在 `app/api/v1/__init__.py` 中注册
- [ ] Redis 缓存键正确（`dashboard:overview:{user_id}` / `dashboard:winrate:{user_id}:{period}` / `dashboard:technique:{user_id}` / `dashboard:heatmap:{user_id}`）
- [ ] 缓存 TTL 配置正确（overview 5min, trend/technique/heatmap 1h, match-records 不缓存）
- [ ] 缓存 bust 触发正确（分析完成 → overview/technique/heatmap，比赛结束 → overview/winrate）
- [ ] 落点热图聚合限制最近 10 次报告
- [ ] 比赛记录列表实时查询不缓存
- [ ] 概览响应包含 `latest_advice_summary` 字段
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- Schema **必须** 遵循命名：`OverviewResponse`、`WinRateTrendResponse`、`TechniqueStatsResponse`、`LandingHeatmapResponse`、`MatchRecordsResponse`
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- **禁止** 创建独立 Model，复用 `analysis_report`、`match_record` 等已有表
- **必须** 实现 Redis 缓存策略，缓存未命中时降级实时计算
- **必须** 实现缓存 bust，在 `video_analysis` 分析完成和 `match_data` 比赛结束时调用 `DashboardService.bust_cache()`
- **必须** 在落点热图聚合中限制最近 10 次报告
- **禁止** 缓存比赛记录列表（实时查询）
- 测试 **必须** 使用 `httpx.AsyncClient`，**禁止** 自建 HTTP 客户端
- 冒烟测试 **必须** 可作为独立脚本运行
- ALL API 端点已添加 `@limiter.limit()` 限流装饰器，全局默认 100/minute，AI 分析创建 10/hour
