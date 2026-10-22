# progress_analysis 模块 �?后端垂直切片设计

> **模块名称**：`progress_analysis`
> **所属目�?*：`app/api/v1/progress/` + `app/services/progress_service.py` + `app/models/progress.py` + `app/schemas/progress.py`
> **定位**：AI 分析报告完成后自动生成进度快照，计算 18 项技术指标趋势，支持报告对比、趋势详情、进度综合摘要与问题变化分析
> **依据**：模块详细设�?v1.2 §2.8、API 详细设计 v1.3 §9、数据库详细设计 v1.5 §2.21-2.22

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.8（progress_analysis 模块功能规格�?- [ ] 阅读 API 契约 §9�? 个端点：snapshots / technique-trends / technique-trends/{metric} / comparison / summary / problem-changes�?- [ ] 阅读 `app/models/progress.py`（ProgressSnapshot + TechniqueTrend 模型�?- [ ] 阅读 `app/models/video_analysis.py`（AnalysisReport 模型，result_data JSONB 结构�?- [ ] 阅读 `app/services/ai_pipeline_service.py`（AI 流水�?Step 9 报告生成完成后触发快照生成）
- [ ] 确认本切片范围：6 �?API 端点 + 对应 Service 方法 + 快照生成内部方法

### 任务清单

| # | 任务 | 文件 | 依赖 | 状�?|
|---|------|------|------|------|
| 1 | 定义 Model（ProgressSnapshot + TechniqueTrend�?| `app/models/progress.py` | �?| �?|
| 2 | 注册 Model | `app/models/__init__.py` | #1 | �?|
| 3 | 生成 Alembic 迁移 | `alembic revision --autogenerate` | #2 | �?|
| 4 | 定义 Schema | `app/schemas/progress.py` | #1 | �?|
| 5 | 实现 Service | `app/services/progress_service.py` | #2,#4 | �?|
| 6 | 实现 API 路由 | `app/api/v1/progress/router.py` | #5 | �?|
| 7 | 注册 Router | `app/api/v1/__init__.py` | #6 | �?|
| 8 | 编写单元测试 | `tests/unit/test_progress.py` | #5 | �?|
| 9 | 编写冒烟测试 | `tests/smoke/progress_smoke_test.py` | #7 | �?|

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_progress.py
"""
progress_analysis 模块 �?进度分析测试�?覆盖：快照列表、趋势查询、报告对比、综合摘要、问题变化、快照自动生成�?"""
import pytest
from unittest.mock import AsyncMock, patch
from app.core.exceptions import AppException

@pytest.fixture
async def progress_ctx(db_session, auth_user):
    """创建测试上下文：用户 + 分析报告 + 进度快照�?""
    from app.models.video_analysis import AnalysisReport
    from app.models.progress import ProgressSnapshot, TechniqueTrend
    from datetime import datetime, timezone, timedelta

    user_id = auth_user["id"]
    now = datetime.now(timezone.utc)

    # 创建两份分析报告
    report_a = AnalysisReport(
        user_id=user_id,
        task_id=1001,
        result_data={
            "technique_stats": {"forehand_ratio": 0.68, "backhand_ratio": 0.25, "serve_ratio": 0.07},
            "landing_points": {"distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07}},
            "rally_analysis": {"avg_rally_length": 4.5},
            "ball_speed": {"avg_speed_mps": 17.2},
            "score_analysis": {"win_rate": 0.50},
        },
        created_at=now - timedelta(days=30),
    )
    report_b = AnalysisReport(
        user_id=user_id,
        task_id=1002,
        result_data={
            "technique_stats": {"forehand_ratio": 0.62, "backhand_ratio": 0.32, "serve_ratio": 0.06},
            "landing_points": {"distribution": {"forehand": 0.62, "backhand": 0.32, "middle": 0.06}},
            "rally_analysis": {"avg_rally_length": 5.2},
            "ball_speed": {"avg_speed_mps": 18.5},
            "score_analysis": {"win_rate": 0.55},
        },
        created_at=now,
    )
    db_session.add_all([report_a, report_b])
    await db_session.flush()

    # 创建进度快照
    snapshot_a = ProgressSnapshot(
        user_id=user_id,
        report_id=report_a.id,
        metrics_snapshot={
            "backhand_ratio": 0.25, "forehand_ratio": 0.68, "serve_ratio": 0.07,
            "landing_forehand_pct": 0.68, "landing_backhand_pct": 0.25,
            "landing_middle_pct": 0.07, "landing_dispersion": 3.2,
            "avg_rally_length": 4.5, "max_rally_length": 12, "rally_frequency": 1.0,
            "avg_ball_speed": 17.2, "max_ball_speed": 22.0,
            "score_win_rate": 0.50, "key_point_win_rate": 0.50,
            "serve_point_win_rate": 0.55, "receive_point_win_rate": 0.40,
            "attack_transition_rate": 0.30, "error_rate": 0.15,
        },
    )
    snapshot_b = ProgressSnapshot(
        user_id=user_id,
        report_id=report_b.id,
        metrics_snapshot={
            "backhand_ratio": 0.32, "forehand_ratio": 0.62, "serve_ratio": 0.06,
            "landing_forehand_pct": 0.62, "landing_backhand_pct": 0.32,
            "landing_middle_pct": 0.06, "landing_dispersion": 2.8,
            "avg_rally_length": 5.2, "max_rally_length": 18, "rally_frequency": 1.2,
            "avg_ball_speed": 18.5, "max_ball_speed": 25.3,
            "score_win_rate": 0.55, "key_point_win_rate": 0.60,
            "serve_point_win_rate": 0.65, "receive_point_win_rate": 0.45,
            "attack_transition_rate": 0.38, "error_rate": 0.12,
        },
    )
    db_session.add_all([snapshot_a, snapshot_b])
    await db_session.flush()

    # 创建趋势记录
    trend = TechniqueTrend(
        user_id=user_id,
        metric_name="backhand_ratio",
        current_value=0.32,
        previous_value=0.25,
        change_rate=0.28,
        trend="improving",
        target_value=0.35,
        persistence_count=4,
        time_series=[
            {"date": "2026-07-10", "value": 0.18},
            {"date": "2026-08-10", "value": 0.25},
            {"date": "2026-09-15", "value": 0.30},
            {"date": "2026-10-01", "value": 0.32},
        ],
    )
    db_session.add(trend)
    await db_session.flush()

    yield {
        "user": auth_user,
        "report_a": report_a,
        "report_b": report_b,
        "snapshot_a": snapshot_a,
        "snapshot_b": snapshot_b,
        "trend": trend,
    }
```

### 2.1 Happy Path（正常流程）

```python
# === 1. Happy Path ===
@pytest.mark.asyncio
async def test_list_snapshots_success(client, progress_ctx, auth_headers):
    """获取进度快照列表，返回分页结果�?""
    resp = await client.get("/api/v1/progress/snapshots", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    assert "metrics_snapshot" in data["items"][0]
    assert "backhand_ratio" in data["items"][0]["metrics_snapshot"]

@pytest.mark.asyncio
async def test_get_technique_trends_success(client, progress_ctx, auth_headers):
    """获取全部技术指标趋势�?""
    resp = await client.get("/api/v1/progress/technique-trends", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "metrics" in data
    assert len(data["metrics"]) >= 1
    backhand = [m for m in data["metrics"] if m["metric"] == "backhand_ratio"][0]
    assert backhand["trend"] == "improving"
    assert backhand["change_rate"] == 0.28

@pytest.mark.asyncio
async def test_get_comparison_success(client, progress_ctx, auth_headers):
    """对比两份报告，返�?6 个维度的对比结果�?""
    resp = await client.get(
        f"/api/v1/progress/comparison?report_a={progress_ctx['report_a'].id}"
        f"&report_b={progress_ctx['report_b'].id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "comparisons" in data
    assert "technique_stats" in data["comparisons"]
    assert "landing" in data["comparisons"]
    assert "rally" in data["comparisons"]
    assert "ball_speed" in data["comparisons"]
    assert "score_analysis" in data["comparisons"]
    assert "problem_changes" in data["comparisons"]

@pytest.mark.asyncio
async def test_get_summary_success(client, progress_ctx, auth_headers):
    """获取进度综合摘要，含 forecast 字段�?""
    resp = await client.get("/api/v1/progress/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_analyses"] >= 2
    assert data["overall_progress"] in ("improving", "stagnant", "declining")
    assert "problem_changes" in data
    assert "forecast" in data
```

### 2.2 Validation Failure（参数校验失败）

```python
# === 2. Validation Failure ===
@pytest.mark.asyncio
async def test_get_comparison_same_report(client, progress_ctx, auth_headers):
    """report_a �?report_b 相同时返�?422�?""
    resp = await client.get(
        f"/api/v1/progress/comparison?report_a={progress_ctx['report_a'].id}"
        f"&report_b={progress_ctx['report_a'].id}",
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "不同" in resp.json()["message"]

@pytest.mark.asyncio
async def test_get_trend_detail_invalid_metric(client, auth_headers):
    """不存在的指标名返�?404�?""
    resp = await client.get(
        "/api/v1/progress/technique-trends/nonexistent_metric",
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert "指标不存�? in resp.json()["message"]

@pytest.mark.asyncio
async def test_list_snapshots_invalid_period(client, auth_headers):
    """period 参数不在枚举中时返回 422�?""
    resp = await client.get(
        "/api/v1/progress/snapshots?period=invalid",
        headers=auth_headers,
    )
    assert resp.status_code == 422
```

### 2.3 Permission Denied（权限不足）

```python
# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_list_snapshots_no_auth(client):
    """未登录访问返�?401�?""
    resp = await client.get("/api/v1/progress/snapshots")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_get_comparison_other_user_report(client, auth_user2, auth_headers):
    """对比其他用户的报告返�?403/404�?""
    resp = await client.get(
        "/api/v1/progress/comparison?report_a=99999&report_b=99998",
        headers=auth_headers,
    )
    assert resp.status_code in (403, 404)
```

### 2.4 Business Rule（业务规则验证）

```python
# === 4. Business Rule ===
@pytest.mark.asyncio
async def test_generate_snapshot_extracts_18_metrics(db_session, auth_user):
    """快照生成时从 result_data 提取 18 项关键指标�?""
    from app.services.progress_service import ProgressService
    from app.models.video_analysis import AnalysisReport

    report = AnalysisReport(
        user_id=auth_user["id"],
        task_id=2001,
        result_data={
            "technique_stats": {"forehand_ratio": 0.60, "backhand_ratio": 0.30, "serve_ratio": 0.10},
            "landing_points": {"distribution": {"forehand": 0.60, "backhand": 0.30, "middle": 0.10}},
            "rally_analysis": {"avg_rally_length": 5.0, "max_rally_length": 15, "rally_frequency": 1.1},
            "ball_speed": {"avg_speed_mps": 19.0, "max_speed_mps": 24.0},
            "score_analysis": {"win_rate": 0.58, "key_point_win_rate": 0.62,
                               "serve_point_win_rate": 0.60, "receive_point_win_rate": 0.48},
            "attack_transition_rate": 0.40,
            "error_rate": 0.10,
        },
    )
    db_session.add(report)
    await db_session.flush()

    snapshot = await ProgressService.generate_snapshot(
        user_id=auth_user["id"],
        report_id=report.id,
        result_data=report.result_data,
    )
    assert snapshot is not None
    # 18 项指标全部存�?    metrics = snapshot.metrics_snapshot
    expected_keys = [
        "backhand_ratio", "forehand_ratio", "serve_ratio",
        "landing_forehand_pct", "landing_backhand_pct", "landing_middle_pct",
        "landing_dispersion", "avg_rally_length", "max_rally_length",
        "rally_frequency", "avg_ball_speed", "max_ball_speed",
        "score_win_rate", "key_point_win_rate", "serve_point_win_rate",
        "receive_point_win_rate", "attack_transition_rate", "error_rate",
    ]
    for key in expected_keys:
        assert key in metrics, f"指标 {key} 缺失"

@pytest.mark.asyncio
async def test_trend_judgment_improving(db_session, progress_ctx):
    """趋势判定：连�?�? 次改�?+ 变化�?>5% �?improving�?""
    from app.services.progress_service import ProgressService

    trend = await ProgressService._calculate_trend(
        user_id=progress_ctx["user"].id,
        metric_name="backhand_ratio",
        current_value=0.32,
        history_values=[0.18, 0.22, 0.25, 0.28, 0.30],
        target_value=0.35,
    )
    assert trend["trend"] == "improving"
    assert trend["persistence_count"] >= 2
    assert trend["change_rate"] > 0.05

@pytest.mark.asyncio
async def test_trend_judgment_stagnant(db_session, progress_ctx):
    """趋势判定：连�?�? 次变化率 <5% �?stagnant�?""
    from app.services.progress_service import ProgressService

    trend = await ProgressService._calculate_trend(
        user_id=progress_ctx["user"].id,
        metric_name="avg_ball_speed",
        current_value=18.0,
        history_values=[17.8, 17.9, 18.0, 18.1, 18.0],
        target_value=20.0,
    )
    assert trend["trend"] == "stagnant"
    assert trend["persistence_count"] >= 3

@pytest.mark.asyncio
async def test_forecast_only_when_r2_above_threshold(progress_ctx):
    """R² > 0.4 时填�?forecast 字段�?""
    from app.services.progress_service import ProgressService

    # 良好线性趋�?�?R² �?    forecast = ProgressService._linear_regression_forecast(
        history=[{"date": "2026-07-10", "value": 0.18},
                 {"date": "2026-08-10", "value": 0.22},
                 {"date": "2026-09-10", "value": 0.26},
                 {"date": "2026-10-10", "value": 0.30}],
        target=0.35,
    )
    assert forecast is not None
    assert forecast["r_squared"] > 0.4
    assert "predicted_weeks_to_target" in forecast

    # 无规律数�?�?R² �?�?返回 None
    forecast_low = ProgressService._linear_regression_forecast(
        history=[{"date": "2026-07-10", "value": 0.30},
                 {"date": "2026-08-10", "value": 0.18},
                 {"date": "2026-09-10", "value": 0.28},
                 {"date": "2026-10-10", "value": 0.20}],
        target=0.35,
    )
    assert forecast_low is None
```

---

## 3. Model（SQLAlchemy 2.0�?
```python
# app/models/progress.py
"""进度分析模型�?""

from sqlalchemy import BigInteger, String, Integer, Float, ForeignKey, Index, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone

from app.core.database import Base


class ProgressSnapshot(Base):
    """进度快照 �?每次分析报告完成后自动生成，存储 18 项关键指标�?""

    __tablename__ = "progress_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"),  # R19-P3-11: 移除冗余 index=True（__table_args__ idx_ps_user_created 已覆盖）
    )
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_report.id", ondelete="CASCADE"), unique=True,
    )
    metrics_snapshot: Mapped[dict] = mapped_column(JSONB, comment="18 项关键指标快�?)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_ps_user_created", "user_id", "created_at"),
        Index("idx_ps_metrics_gin", "metrics_snapshot", postgresql_using="gin"),  # R19-P2-3: 补 GIN 索引（§5/§6 已定义，替代 Alembic 手动注释）
    )


class TechniqueTrend(Base):
    """技术指标趋�?�?每用户每指标一条，更新而非新增�?""

    __tablename__ = "technique_trend"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"),  # R19-P3-11: 移除冗余 index=True（__table_args__ uq_trend_user_metric UniqueConstraint 已覆盖）
    )
    metric_name: Mapped[str] = mapped_column(String(64), comment="指标�?)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="improving/stagnant/declining/achieved/new/resolved",
    )
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    persistence_count: Mapped[int] = mapped_column(Integer, default=0)
    time_series: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="[{date, value}]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("uq_trend_user_metric", "user_id", "metric_name", unique=True),
    )
```

**实现后必�?*�?- [ ] �?`app/models/__init__.py` 中导入：`from app.models.progress import ProgressSnapshot, TechniqueTrend`
- [ ] 生成 Alembic 迁移：`alembic revision --autogenerate -m "add progress_snapshot and technique_trend"`
- [ ] 执行迁移：`alembic upgrade head`
<!-- R19-P2-3: idx_ps_metrics_gin 已通过 ProgressSnapshot.__table_args__ 显式定义，Alembic autogenerate 会自动包含，无需手动 op.execute -->

---

## 4. Schema（Pydantic�?
```python
# app/schemas/progress.py
"""进度分析 Schema�?""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime, timezone
from app.core.pagination import Paginated


# --- 查询 Schema ---
class SnapshotListQuery(BaseModel):
    period: str = Field(default="all", pattern=r"^(month|quarter|year|all)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class ComparisonQuery(BaseModel):
    report_a: int = Field(..., ge=1)
    report_b: int = Field(..., ge=1)


# --- 响应 Schema ---
class SnapshotBrief(BaseModel):
    id: int
    report_id: int
    created_at: datetime
    metrics_snapshot: dict
    model_config = {"from_attributes": True}


PaginatedSnapshots = Paginated[SnapshotBrief]


class MetricTrendBrief(BaseModel):
    """单项指标趋势摘要�?""
    metric: str
    metric_name: str
    current_value: Optional[float] = None
    previous_value: Optional[float] = None
    change_rate: Optional[float] = None
    trend: Optional[str] = None
    target: Optional[float] = None
    target_progress: Optional[int] = None
    persistence_count: int = 0
    model_config = {"from_attributes": True}


class TechniqueTrendsResponse(BaseModel):
    """全部技术指标趋势响应�?""
    metrics: list[MetricTrendBrief]


class TrendHistoryPoint(BaseModel):
    date: str
    value: float


class TechniqueTrendDetail(BaseModel):
    """单项指标趋势详情�?""
    metric: str
    metric_name: str
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    target_progress: Optional[int] = None
    trend: Optional[str] = None
    change_rate: Optional[float] = None
    persistence_count: int = 0
    history: list[TrendHistoryPoint] = []


class ComparisonDimension(BaseModel):
    """对比维度项�?""
    a: Optional[Any] = None
    b: Optional[Any] = None
    change: Optional[float] = None


class ProblemChanges(BaseModel):
    new: list[str] = []
    resolved: list[str] = []
    persistent: list[str] = []


class ComparisonResponse(BaseModel):
    """报告对比响应�?""
    report_a: dict
    report_b: dict
    comparisons: dict


class ForecastItem(BaseModel):
    predicted_weeks_to_target: Optional[int] = None
    confidence: str
    r_squared: float


class TrainingPlanStatus(BaseModel):
    current_plan_id: Optional[str] = None
    plan_version: Optional[int] = None
    last_adjustment: Optional[str] = None
    adjustment_reason: Optional[str] = None
    goal_completion: dict = {}


class SummaryResponse(BaseModel):
    """进度综合摘要响应�?""
    summary_period: str
    total_analyses: int
    overall_progress: str
    metric_trends: list[MetricTrendBrief] = []
    problem_changes: ProblemChanges
    training_plan_status: Optional[TrainingPlanStatus] = None
    forecast: dict[str, ForecastItem] = {}


class ProblemChangeItem(BaseModel):
    problem_id: str
    problem_name: str
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    persistence_count: Optional[int] = None


class ProblemChangesResponse(BaseModel):
    """问题变化列表响应�?""
    new: list[ProblemChangeItem] = []
    resolved: list[ProblemChangeItem] = []
    persistent: list[ProblemChangeItem] = []
```

---

## 5. Service（@staticmethod�?
```python
# app/services/progress_service.py
"""进度分析业务逻辑层�?""

import json
import math
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.core.pagination import paginate
from app.models.progress import ProgressSnapshot, TechniqueTrend
from app.models.video_analysis import AnalysisReport
from app.schemas.progress import (
    SnapshotListQuery, SnapshotBrief, PaginatedSnapshots,
    MetricTrendBrief, TechniqueTrendsResponse, TechniqueTrendDetail,
    ComparisonQuery, ComparisonResponse, SummaryResponse, ProblemChanges,
    ProblemChangesResponse, ProblemChangeItem, TrendHistoryPoint,
)

# 18 项关键指标定义：指标�?�?中文�?+ 目标�?+ 改善方向（up=越大越好 / down=越小越好�?METRIC_DEFINITIONS = {
    "backhand_ratio":            {"name": "反手使用�?,   "target": 0.35, "direction": "up"},
    "forehand_ratio":            {"name": "正手使用�?,   "target": 0.60, "direction": "down"},
    "serve_ratio":               {"name": "发球使用�?,   "target": 0.05, "direction": "down"},
    "landing_forehand_pct":      {"name": "正手区落点率", "target": 0.55, "direction": "down"},
    "landing_backhand_pct":      {"name": "反手区落点率", "target": 0.30, "direction": "up"},
    "landing_middle_pct":        {"name": "中路落点�?,   "target": 0.15, "direction": "up"},
    "landing_dispersion":        {"name": "落点分散�?,   "target": 2.5,  "direction": "down"},
    "avg_rally_length":          {"name": "平均回合长度", "target": 6.0,  "direction": "up"},
    "max_rally_length":          {"name": "最长回合长�?, "target": 15.0, "direction": "up"},
    "rally_frequency":           {"name": "回合频率",     "target": 1.5,  "direction": "up"},
    "avg_ball_speed":            {"name": "平均球�?,     "target": 20.0, "direction": "up"},
    "max_ball_speed":            {"name": "最大球�?,     "target": 26.0, "direction": "up"},
    "score_win_rate":            {"name": "胜率",         "target": 0.60, "direction": "up"},
    "key_point_win_rate":        {"name": "关键分胜�?,   "target": 0.55, "direction": "up"},
    "serve_point_win_rate":      {"name": "发球得分�?,   "target": 0.60, "direction": "up"},
    "receive_point_win_rate":    {"name": "接发球得分率", "target": 0.50, "direction": "up"},
    "attack_transition_rate":    {"name": "攻防转换�?,   "target": 0.40, "direction": "up"},
    "error_rate":                {"name": "失误�?,       "target": 0.08, "direction": "down"},
}

# 趋势变化率阈�?CHANGE_RATE_THRESHOLD = 0.05  # 5%
# 线性回�?R² 阈�?R_SQUARED_THRESHOLD = 0.4


class ProgressService:
    """进度分析业务逻辑层�?""

    # ==================== 快照生成（内部方法，�?AI 流水线调用） ====================

    @staticmethod
    async def generate_snapshot(
        user_id: int,
        report_id: int,
        result_data: dict,
    ) -> ProgressSnapshot:
        """
        从分析报�?result_data 提取 18 项关键指标，生成进度快照�?        �?AI 流水�?Step 9（报告生成）完成后自动调用�?        """
        metrics = ProgressService._extract_metrics(result_data)

        async with get_async_session() as db:
            snapshot = ProgressSnapshot(
                user_id=user_id,
                report_id=report_id,
                metrics_snapshot=metrics,
            )
            db.add(snapshot)
            await db.flush()

            # 计算并更新趋�?            await ProgressService._update_trends(db, user_id, snapshot)

            await db.commit()
            await db.refresh(snapshot)

            # 刷新 Redis 缓存
            redis = await get_redis()
            await redis.delete(f"progress:summary:{user_id}")
            await redis.delete(f"progress:trends:{user_id}")

            return snapshot

    @staticmethod
    def _extract_metrics(result_data: dict) -> dict:
        """�?result_data JSONB 中提�?18 项关键指标�?""
        tech = result_data.get("technique_stats", {})
        landing = result_data.get("landing_points", {}).get("distribution", {})
        rally = result_data.get("rally_analysis", {})
        speed = result_data.get("ball_speed", {})
        score = result_data.get("score_analysis", {})

        return {
            "backhand_ratio":         tech.get("backhand_ratio"),
            "forehand_ratio":         tech.get("forehand_ratio"),
            "serve_ratio":            tech.get("serve_ratio"),
            "landing_forehand_pct":   landing.get("forehand"),
            "landing_backhand_pct":   landing.get("backhand"),
            "landing_middle_pct":     landing.get("middle"),
            "landing_dispersion":     result_data.get("landing_points", {}).get("dispersion"),
            "avg_rally_length":       rally.get("avg_rally_length"),
            "max_rally_length":       rally.get("max_rally_length"),
            "rally_frequency":        rally.get("rally_frequency"),
            "avg_ball_speed":         speed.get("avg_speed_mps"),
            "max_ball_speed":         speed.get("max_speed_mps"),
            "score_win_rate":         score.get("win_rate"),
            "key_point_win_rate":     score.get("key_point_win_rate"),
            "serve_point_win_rate":   score.get("serve_point_win_rate"),
            "receive_point_win_rate": score.get("receive_point_win_rate"),
            "attack_transition_rate": result_data.get("attack_transition_rate"),
            "error_rate":             result_data.get("error_rate"),
        }

    # ==================== 趋势计算 ====================

    @staticmethod
    async def _update_trends(db: AsyncSession, user_id: int, snapshot: ProgressSnapshot):
        """读取历史快照，计算趋势并更新 technique_trend 表�?""
        # 获取历史快照（含当前），按时间正�?        result = await db.execute(
            select(ProgressSnapshot)
            .where(ProgressSnapshot.user_id == user_id)
            .order_by(ProgressSnapshot.created_at)
        )
        snapshots = result.scalars().all()

        if len(snapshots) < 2:
            return  # �?1 条快照，无法计算趋势

        for metric_name, metric_def in METRIC_DEFINITIONS.items():
            # 提取该指标的历史值列�?            values = []
            for s in snapshots:
                v = s.metrics_snapshot.get(metric_name)
                if v is not None:
                    values.append(v)

            if len(values) < 2:
                continue

            current = values[-1]
            previous = values[-2]
            history_values = values[:-1]

            trend_result = ProgressService._calculate_trend(
                user_id=user_id,
                metric_name=metric_name,
                current_value=current,
                history_values=history_values,
                target_value=metric_def["target"],
            )

            # 构建 time_series
            time_series = []
            for s in snapshots:
                v = s.metrics_snapshot.get(metric_name)
                if v is not None:
                    time_series.append({
                        "date": s.created_at.strftime("%Y-%m-%d"),
                        "value": v,
                    })

            # UPSERT technique_trend
            existing = await db.execute(
                select(TechniqueTrend).where(
                    TechniqueTrend.user_id == user_id,
                    TechniqueTrend.metric_name == metric_name,
                )
            )
            trend_row = existing.scalar_one_or_none()

            if trend_row:
                trend_row.current_value = current
                trend_row.previous_value = previous
                trend_row.change_rate = trend_result["change_rate"]
                trend_row.trend = trend_result["trend"]
                trend_row.persistence_count = trend_result["persistence_count"]
                trend_row.time_series = time_series
            else:
                trend_row = TechniqueTrend(
                    user_id=user_id,
                    metric_name=metric_name,
                    current_value=current,
                    previous_value=previous,
                    change_rate=trend_result["change_rate"],
                    trend=trend_result["trend"],
                    target_value=metric_def["target"],
                    persistence_count=trend_result["persistence_count"],
                    time_series=time_series,
                )
                db.add(trend_row)

            await db.flush()

    @staticmethod
    def _calculate_trend(
        user_id: int,
        metric_name: str,
        current_value: float,
        history_values: list[float],
        target_value: float,
    ) -> dict:
        """
        趋势判定规则（BR-2）：
        - improving: 连续 �? 次向目标靠近 + 变化�?>5%
        - stagnant: 连续 �? 次变化率 <5%
        - declining: 连续 �? 次远离目�?+ 变化�?>5%
        - achieved: 已达目标并保�?�? �?        - new: 首次出现（历�?<2 条）
        - resolved: 历史有但最�?2 次消失（当前值为 None�?        """
        metric_def = METRIC_DEFINITIONS.get(metric_name, {})
        direction = metric_def.get("direction", "up")

        all_values = history_values + [current_value]

        # 检查是否已达目�?        if direction == "up":
            achieved = all(
                v >= target_value for v in all_values[-2:] if v is not None
            )
        else:
            achieved = all(
                v <= target_value for v in all_values[-2:] if v is not None
            )

        if achieved:
            return {"trend": "achieved", "change_rate": 0.0, "persistence_count": 2}

        if len(history_values) < 1:
            return {"trend": "new", "change_rate": None, "persistence_count": 0}

        # 计算变化�?        prev = history_values[-1]
        if prev == 0:
            change_rate = 0.0
        else:
            change_rate = abs(current_value - prev) / abs(prev)

        # 判断方向（改�?vs 退步）
        if direction == "up":
            is_improving = current_value > prev
        else:
            is_improving = current_value < prev

        # 持续性计�?        persistence = 1
        for i in range(len(all_values) - 2, 0, -1):
            prev_v = all_values[i - 1] if i > 0 else None
            curr_v = all_values[i]
            if prev_v is None:
                break
            if direction == "up" and curr_v > prev_v:
                persistence += 1
            elif direction == "down" and curr_v < prev_v:
                persistence += 1
            else:
                break

        # 趋势判定
        if is_improving and change_rate > CHANGE_RATE_THRESHOLD and persistence >= 2:
            return {"trend": "improving", "change_rate": change_rate, "persistence_count": persistence}
        elif change_rate < CHANGE_RATE_THRESHOLD and len(all_values) >= 4:
            return {"trend": "stagnant", "change_rate": change_rate, "persistence_count": len(all_values)}
        elif not is_improving and change_rate > CHANGE_RATE_THRESHOLD and persistence >= 2:
            return {"trend": "declining", "change_rate": change_rate, "persistence_count": persistence}
        else:
            return {"trend": "stagnant", "change_rate": change_rate, "persistence_count": persistence}

    @staticmethod
    def _linear_regression_forecast(
        history: list[dict],
        target: float,
    ) -> Optional[dict]:
        """
        线性回归外推预测�?        R² > 0.4 时返�?forecast，否则返�?None�?        """
        if len(history) < 3:
            return None

        # 提取 x（时间序号）�?y（指标值）
        n = len(history)
        x = list(range(n))
        y = [h["value"] for h in history]

        # 简单线性回�? y = a*x + b
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xx = sum(xi * xi for xi in x)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        mean_y = sum_y / n

        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return None

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n

        # 计算 R²
        ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
        ss_tot = sum((yi - mean_y) ** 2 for yi in y)
        if ss_tot == 0:
            return None
        r_squared = 1 - ss_res / ss_tot

        if r_squared < R_SQUARED_THRESHOLD:
            return None

        # 外推到目�?        if slope <= 0:
            return None  # 无法外推到目�?
        # x_target = (target - intercept) / slope
        x_target = (target - intercept) / slope
        remaining = x_target - (n - 1)

        if remaining <= 0:
            return {"predicted_weeks_to_target": 0, "confidence": "high", "r_squared": r_squared}

        # 假设每两次分析间隔约 2 �?        predicted_weeks = int(remaining * 2)

        confidence = "high" if r_squared > 0.7 else "medium"

        return {
            "predicted_weeks_to_target": predicted_weeks,
            "confidence": confidence,
            "r_squared": round(r_squared, 4),
        }

    # ==================== API 查询方法 ====================

    @staticmethod
    async def list_snapshots(user_id: int, query: SnapshotListQuery) -> PaginatedSnapshots:
        """获取进度快照列表。权限：登录用户（仅查看自己的数据）�?""
        async with get_async_session() as db:
            # 时间范围过滤
            now = datetime.now(timezone.utc)
            if query.period == "month":
                start = now - timedelta(days=30)
            elif query.period == "quarter":
                start = now - timedelta(days=90)
            elif query.period == "year":
                start = now - timedelta(days=365)
            else:
                start = None

            stmt = select(ProgressSnapshot).where(ProgressSnapshot.user_id == user_id)
            if start:
                stmt = stmt.where(ProgressSnapshot.created_at >= start)
            stmt = stmt.order_by(desc(ProgressSnapshot.created_at))

            total, items = await paginate(db, stmt, query.page, query.page_size)
            return PaginatedSnapshots(
                total=total, page=query.page, page_size=query.page_size,
                items=[SnapshotBrief.model_validate(s) for s in items],
            )

    @staticmethod
    async def get_technique_trends(user_id: int) -> TechniqueTrendsResponse:
        """获取全部技术指标趋势。缓�?1h�?""
        redis = await get_redis()
        cache_key = f"progress:trends:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return TechniqueTrendsResponse.model_validate_json(cached)

        async with get_async_session() as db:
            result = await db.execute(
                select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
            )
            trends = result.scalars().all()

            metrics = []
            for t in trends:
                metric_def = METRIC_DEFINITIONS.get(t.metric_name, {})
                target = t.target_value or metric_def.get("target")
                target_progress = None
                if target is not None and t.current_value is not None:
                    if metric_def.get("direction") == "up":
                        target_progress = min(100, int(t.current_value / target * 100))
                    else:
                        target_progress = min(100, int(target / t.current_value * 100)) if t.current_value else None

                metrics.append(MetricTrendBrief(
                    metric=t.metric_name,
                    metric_name=metric_def.get("name", t.metric_name),
                    current_value=t.current_value,
                    previous_value=t.previous_value,
                    change_rate=t.change_rate,
                    trend=t.trend,
                    target=target,
                    target_progress=target_progress,
                    persistence_count=t.persistence_count,
                ))

            response = TechniqueTrendsResponse(metrics=metrics)
            await redis.setex(cache_key, 3600, response.model_dump_json())
            return response

    @staticmethod
    async def get_technique_trend_detail(
        user_id: int, metric: str,
    ) -> TechniqueTrendDetail:
        """获取单项指标趋势详情（含时间序列）。缓�?1h�?""
        if metric not in METRIC_DEFINITIONS:
            raise AppException("指标不存�?, 404)

        redis = await get_redis()
        cache_key = f"progress:trend_detail:{user_id}:{metric}"
        cached = await redis.get(cache_key)
        if cached:
            return TechniqueTrendDetail.model_validate_json(cached)

        async with get_async_session() as db:
            result = await db.execute(
                select(TechniqueTrend).where(
                    TechniqueTrend.user_id == user_id,
                    TechniqueTrend.metric_name == metric,
                )
            )
            trend = result.scalar_one_or_none()

            metric_def = METRIC_DEFINITIONS[metric]
            target = metric_def["target"]
            history = []
            current_value = None
            target_progress = None

            if trend:
                history = [TrendHistoryPoint(**h) for h in (trend.time_series or [])]
                current_value = trend.current_value
                if current_value is not None:
                    if metric_def["direction"] == "up":
                        target_progress = min(100, int(current_value / target * 100))
                    else:
                        target_progress = min(100, int(target / current_value * 100)) if current_value else None

            response = TechniqueTrendDetail(
                metric=metric,
                metric_name=metric_def["name"],
                current_value=current_value,
                target_value=target,
                target_progress=target_progress,
                trend=trend.trend if trend else None,
                change_rate=trend.change_rate if trend else None,
                persistence_count=trend.persistence_count if trend else 0,
                history=history,
            )
            await redis.setex(cache_key, 3600, response.model_dump_json())
            return response

    @staticmethod
    async def get_comparison(user_id: int, query: ComparisonQuery) -> ComparisonResponse:
        """两次分析报告对比，覆�?6 个维度�?""
        if query.report_a == query.report_b:
            raise AppException("请选择两份不同的报�?, 422)

        async with get_async_session() as db:
            # 查找两份报告对应的快�?            result_a = await db.execute(
                select(ProgressSnapshot).where(
                    ProgressSnapshot.user_id == user_id,
                    ProgressSnapshot.report_id == query.report_a,
                )
            )
            snapshot_a = result_a.scalar_one_or_none()
            if not snapshot_a:
                raise AppException("报告不存�?, 404)

            result_b = await db.execute(
                select(ProgressSnapshot).where(
                    ProgressSnapshot.user_id == user_id,
                    ProgressSnapshot.report_id == query.report_b,
                )
            )
            snapshot_b = result_b.scalar_one_or_none()
            if not snapshot_b:
                raise AppException("报告不存�?, 404)

            ma = snapshot_a.metrics_snapshot
            mb = snapshot_b.metrics_snapshot

            # 6 维度对比
            comparisons = {
                "technique_stats": {
                    k: {
                        "a": ma.get(k),
                        "b": mb.get(k),
                        "change": round(mb.get(k, 0) - ma.get(k, 0), 4)
                        if ma.get(k) is not None and mb.get(k) is not None else None
                    }
                    for k in ["forehand_ratio", "backhand_ratio", "serve_ratio"]
                },
                "landing": {
                    k: {
                        "a": ma.get(k),
                        "b": mb.get(k),
                        "change": round(mb.get(k, 0) - ma.get(k, 0), 4)
                        if ma.get(k) is not None and mb.get(k) is not None else None
                    }
                    for k in ["landing_forehand_pct", "landing_backhand_pct", "landing_middle_pct"]
                },
                "rally": {
                    "avg_length_a": ma.get("avg_rally_length"),
                    "avg_length_b": mb.get("avg_rally_length"),
                    "change": round(
                        (mb.get("avg_rally_length", 0) - ma.get("avg_rally_length", 0)), 2
                    ) if ma.get("avg_rally_length") and mb.get("avg_rally_length") else None,
                },
                "ball_speed": {
                    "avg_a": ma.get("avg_ball_speed"),
                    "avg_b": mb.get("avg_ball_speed"),
                    "change": round(
                        (mb.get("avg_ball_speed", 0) - ma.get("avg_ball_speed", 0)), 2
                    ) if ma.get("avg_ball_speed") and mb.get("avg_ball_speed") else None,
                },
                "score_analysis": {
                    "win_rate_a": ma.get("score_win_rate"),
                    "win_rate_b": mb.get("score_win_rate"),
                    "change": round(
                        (mb.get("score_win_rate", 0) - ma.get("score_win_rate", 0)), 4
                    ) if ma.get("score_win_rate") is not None and mb.get("score_win_rate") is not None else None,
                },
                "problem_changes": await ProgressService._compute_problem_changes(db, user_id, snapshot_a, snapshot_b),
            }

            return ComparisonResponse(
                report_a={
                    "id": snapshot_a.report_id,
                    "created_at": snapshot_a.created_at.isoformat(),
                },
                report_b={
                    "id": snapshot_b.report_id,
                    "created_at": snapshot_b.created_at.isoformat(),
                },
                comparisons=comparisons,
            )

    @staticmethod
    async def get_summary(user_id: int) -> SummaryResponse:
        """进度综合摘要，含趋势+问题变化+方案状�?预测。缓�?5min�?""
        redis = await get_redis()
        cache_key = f"progress:summary:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return SummaryResponse.model_validate_json(cached)

        async with get_async_session() as db:
            # 获取快照总数
            count_result = await db.execute(
                select(func.count(ProgressSnapshot.id))
                .where(ProgressSnapshot.user_id == user_id)
            )
            total_analyses = count_result.scalar() or 0

            # 获取全部趋势
            trends_result = await db.execute(
                select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
            )
            trends = trends_result.scalars().all()

            # 整体进度判定
            improving_count = sum(1 for t in trends if t.trend == "improving")
            declining_count = sum(1 for t in trends if t.trend == "declining")
            if improving_count > declining_count:
                overall = "improving"
            elif declining_count > improving_count:
                overall = "declining"
            else:
                overall = "stagnant"

            # 指标趋势列表
            metric_trends = []
            for t in trends:
                metric_def = METRIC_DEFINITIONS.get(t.metric_name, {})
                target = t.target_value or metric_def.get("target")
                target_progress = None
                if target is not None and t.current_value is not None:
                    if metric_def.get("direction") == "up":
                        target_progress = min(100, int(t.current_value / target * 100))
                    else:
                        target_progress = min(100, int(target / t.current_value * 100)) if t.current_value else None

                metric_trends.append(MetricTrendBrief(
                    metric=t.metric_name,
                    metric_name=metric_def.get("name", t.metric_name),
                    current_value=t.current_value,
                    previous_value=t.previous_value,
                    change_rate=t.change_rate,
                    trend=t.trend,
                    target=target,
                    target_progress=target_progress,
                    persistence_count=t.persistence_count,
                ))

            # 问题变化
            problem_changes = await ProgressService._get_problem_changes(db, user_id)

            # 线性回归预�?            forecast = {}
            for t in trends:
                if t.time_series and len(t.time_series) >= 3:
                    fc = ProgressService._linear_regression_forecast(
                        t.time_series,
                        t.target_value or METRIC_DEFINITIONS.get(t.metric_name, {}).get("target", 0),
                    )
                    if fc:
                        forecast[t.metric_name] = fc

            # 时间范围
            now = datetime.now(timezone.utc)
            if total_analyses <= 0:
                summary_period = "no_data"
            elif total_analyses <= 3:
                summary_period = "recent"
            else:
                summary_period = "last_3_months"

            response = SummaryResponse(
                summary_period=summary_period,
                total_analyses=total_analyses,
                overall_progress=overall,
                metric_trends=metric_trends,
                problem_changes=ProblemChanges(
                    new=[p.problem_name for p in problem_changes.new],
                    resolved=[p.problem_name for p in problem_changes.resolved],
                    persistent=[p.problem_name for p in problem_changes.persistent],
                ),
                forecast=forecast,
            )
            await redis.setex(cache_key, 300, response.model_dump_json())
            return response

    @staticmethod
    async def get_problem_changes(user_id: int) -> ProblemChangesResponse:
        """问题变化列表（新�?已解�?持续）。缓�?1h�?""
        redis = await get_redis()
        cache_key = f"progress:problems:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return ProblemChangesResponse.model_validate_json(cached)

        async with get_async_session() as db:
            changes = await ProgressService._get_problem_changes(db, user_id)
            await redis.setex(cache_key, 3600, changes.model_dump_json())
            return changes

    @staticmethod
    async def _get_problem_changes(db: AsyncSession, user_id: int) -> ProblemChangesResponse:
        """计算问题变化：从分析报告 report_text JSONB 中的 issues 字段提取�?""
        # 获取最近和历史的报告问题列�?        result = await db.execute(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user_id)
            .order_by(desc(AnalysisReport.created_at))
            .limit(10)
        )
        reports = result.scalars().all()

        if len(reports) < 2:
            return ProblemChangesResponse()

        # 提取每份报告的问题列�?        all_issues = []
        for r in reports:
            try:
                report_text = json.loads(r.report_text) if isinstance(r.report_text, str) else r.report_text
                issues = report_text.get("issues", []) if report_text else []
                all_issues.append({
                    "report_id": r.id,
                    "created_at": r.created_at,
                    "issues": issues,
                })
            except (json.JSONDecodeError, TypeError):
                all_issues.append({"report_id": r.id, "created_at": r.created_at, "issues": []})

        latest_issues = set(all_issues[0]["issues"]) if all_issues else set()
        previous_issues = set()
        for a in all_issues[1:]:
            previous_issues.update(a["issues"])

        # 最�?2 次消失的问题
        recent_2_issues = set()
        for a in all_issues[1:3]:
            recent_2_issues.update(a["issues"])

        new_problems = list(latest_issues - previous_issues)
        resolved_problems = list(previous_issues - latest_issues)
        persistent_problems = list(latest_issues & previous_issues)

        # 构建响应
        new_items = [
            ProblemChangeItem(
                problem_id=f"PROBLEM_NEW_{i}",
                problem_name=p,
                first_seen=all_issues[0]["created_at"].strftime("%Y-%m-%d"),
            )
            for i, p in enumerate(new_problems)
        ]
        resolved_items = [
            ProblemChangeItem(
                problem_id=f"PROBLEM_RESOLVED_{i}",
                problem_name=p,
                last_seen=all_issues[1]["created_at"].strftime("%Y-%m-%d") if len(all_issues) > 1 else None,
            )
            for i, p in enumerate(resolved_problems)
        ]
        persistent_items = [
            ProblemChangeItem(
                problem_id=f"PROBLEM_PERSIST_{i}",
                problem_name=p,
                persistence_count=sum(1 for a in all_issues if p in a["issues"]),
            )
            for i, p in enumerate(persistent_problems)
        ]

        return ProblemChangesResponse(
            new=new_items,
            resolved=resolved_items,
            persistent=persistent_items,
        )

    @staticmethod
    async def _compute_problem_changes(
        db: AsyncSession, user_id: int,
        snapshot_a: ProgressSnapshot, snapshot_b: ProgressSnapshot,
    ) -> dict:
        """计算两次报告间的问题变化�?""
        # 获取两份报告�?issues
        result_a = await db.execute(
            select(AnalysisReport).where(AnalysisReport.id == snapshot_a.report_id)
        )
        report_a = result_a.scalar_one_or_none()
        result_b = await db.execute(
            select(AnalysisReport).where(AnalysisReport.id == snapshot_b.report_id)
        )
        report_b = result_b.scalar_one_or_none()

        issues_a = set()
        issues_b = set()
        try:
            if report_a and report_a.report_text:
                text_a = json.loads(report_a.report_text) if isinstance(report_a.report_text, str) else report_a.report_text
                issues_a = set(text_a.get("issues", []))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            if report_b and report_b.report_text:
                text_b = json.loads(report_b.report_text) if isinstance(report_b.report_text, str) else report_b.report_text
                issues_b = set(text_b.get("issues", []))
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "new": list(issues_b - issues_a),
            "resolved": list(issues_a - issues_b),
            "persistent": list(issues_a & issues_b),
        }
```

---

## 5.5 进度快照生成 Celery Task

```python
# app/tasks/progress_analysis_beat.py
"""进度快照定时/事件驱动生成任务。"""

from app.core.celery import celery_app


@celery_app.task(name="progress_analysis.generate_snapshot")
def generate_snapshot_task(user_id: int, report_id: int):
    """进度快照生成——分析报告完成后事件驱动触发。

    逻辑：
    1. 接收 user_id + report_id，调用 ProgressService.generate_snapshot()
    2. 从分析报告中提取 18 项关键指标，生成 ProgressSnapshot 记录
    3. 自动更新 TechniqueTrend 趋势表（含趋势判定 + 线性回归预测）
    4. 生成完成后触发训练建议生成（send_task: training_advice.generate_advice）

    注意：此任务为事件驱动（分析流水线完成后调用 send_task），
    无需在 beat_schedule 中注册定时触发。
    """
    import asyncio
    asyncio.run(_generate_snapshot_async(user_id, report_id))


async def _generate_snapshot_async(user_id: int, report_id: int):
    """进度快照生成异步实现。"""
    from app.services.progress_service import ProgressService

    await ProgressService.generate_snapshot(
        user_id=user_id, report_id=report_id
    )
```

---

## 6. API 路由（FastAPI�?
```python
# app/api/v1/progress/router.py
from fastapi import APIRouter, Depends, Query
from app.core.deps import get_current_user
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.schemas.progress import (
    SnapshotListQuery, ComparisonQuery,
)
from app.services.progress_service import ProgressService

router = APIRouter(prefix="/progress", tags=["进度分析"])


@limiter.limit("100/minute")
@router.get("/snapshots", summary="进度快照列表")
async def list_snapshots(
    period: str = Query(default="all", pattern=r"^(month|quarter|year|all)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """获取当前用户的进度快照列表（分页）�?""
    query = SnapshotListQuery(period=period, page=page, page_size=page_size)
    data = await ProgressService.list_snapshots(user.id, query)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/technique-trends", summary="全部技术指标趋�?)
async def get_technique_trends(
    user: User = Depends(get_current_user),
):
    """获取全部技术指标趋势摘要，缓存 1h�?""
    data = await ProgressService.get_technique_trends(user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/technique-trends/{metric}", summary="单项指标趋势详情")
async def get_technique_trend_detail(
    metric: str,
    user: User = Depends(get_current_user),
):
    """获取单项指标趋势详情（含时间序列数据），缓存 1h�?""
    data = await ProgressService.get_technique_trend_detail(user.id, metric)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/comparison", summary="两次分析报告对比")
async def get_comparison(
    report_a: int = Query(..., ge=1, description="报告 A ID"),
    report_b: int = Query(..., ge=1, description="报告 B ID"),
    user: User = Depends(get_current_user),
):
    """对比两份分析报告，覆�?6 个维度：技术统�?落点/回合/球�?得分/问题变化�?""
    query = ComparisonQuery(report_a=report_a, report_b=report_b)
    data = await ProgressService.get_comparison(user.id, query)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/summary", summary="进度综合摘要")
async def get_summary(
    user: User = Depends(get_current_user),
):
    """获取进度综合摘要，含趋势+问题变化+方案状�?预测，缓�?5min�?""
    data = await ProgressService.get_summary(user.id)
    return success(data=data)


@limiter.limit("100/minute")
@router.get("/problem-changes", summary="问题变化列表")
async def get_problem_changes(
    user: User = Depends(get_current_user),
):
    """获取问题变化列表（新�?已解�?持续），缓存 1h�?""
    data = await ProgressService.get_problem_changes(user.id)
    return success(data=data)
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.progress.router import router as progress_router
api_router.include_router(progress_router)
```

---

## 7. 冒烟测试脚本

```python
# tests/smoke/progress_smoke_test.py
"""
progress_analysis 模块冒烟测试�?用法: python -m tests.smoke.progress_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 登录获取 Token
        print("0. Login...")
        login_resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "progress_smoke",
        })
        if login_resp.status_code != 200:
            print(f"   �?Login failed: {login_resp.status_code}")
            return
        token = login_resp.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        print("   �?Login success")

        # 2. 获取快照列表
        print("1. Testing /progress/snapshots...")
        resp = await client.get("/progress/snapshots", headers=h)
        assert resp.status_code == 200, f"Snapshots failed: {resp.text}"
        snap_data = resp.json()["data"]
        print(f"   �?Snapshots: total={snap_data['total']}, items={len(snap_data['items'])}")

        # 3. 获取技术趋�?        print("2. Testing /progress/technique-trends...")
        resp = await client.get("/progress/technique-trends", headers=h)
        assert resp.status_code == 200, f"Trends failed: {resp.text}"
        trends = resp.json()["data"]["metrics"]
        print(f"   �?Trends: {len(trends)} metrics")
        if trends:
            print(f"     First: {trends[0]['metric_name']} = {trends[0]['current_value']} ({trends[0]['trend']})")

        # 4. 获取单项指标趋势详情
        if trends:
            metric = trends[0]["metric"]
            print(f"3. Testing /progress/technique-trends/{metric}...")
            resp = await client.get(f"/progress/technique-trends/{metric}", headers=h)
            assert resp.status_code == 200, f"Trend detail failed: {resp.text}"
            detail = resp.json()["data"]
            print(f"   �?Detail: {detail['metric_name']}, history points={len(detail['history'])}")

        # 5. 报告对比
        if snap_data["items"]:
            report_ids = [s["report_id"] for s in snap_data["items"][:2]]
            if len(report_ids) >= 2:
                print(f"4. Testing /progress/comparison (report_a={report_ids[0]}, report_b={report_ids[1]})...")
                resp = await client.get(
                    f"/progress/comparison?report_a={report_ids[0]}&report_b={report_ids[1]}",
                    headers=h,
                )
                assert resp.status_code == 200, f"Comparison failed: {resp.text}"
                comp = resp.json()["data"]["comparisons"]
                print(f"   �?Comparison: {list(comp.keys())}")

        # 6. 综合摘要
        print("5. Testing /progress/summary...")
        resp = await client.get("/progress/summary", headers=h)
        assert resp.status_code == 200, f"Summary failed: {resp.text}"
        summary = resp.json()["data"]
        print(f"   �?Summary: total_analyses={summary['total_analyses']}, overall={summary['overall_progress']}")

        # 7. 问题变化
        print("6. Testing /progress/problem-changes...")
        resp = await client.get("/progress/problem-changes", headers=h)
        assert resp.status_code == 200, f"Problem changes failed: {resp.text}"
        changes = resp.json()["data"]
        print(f"   �?Problem changes: new={len(changes['new'])}, resolved={len(changes['resolved'])}, persistent={len(changes['persistent'])}")

    print("\nprogress_smoke_test: ALL PASSED �?)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_progress.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.progress_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导�?- [ ] Router 已在 `app/api/v1/__init__.py` 中注�?- [ ] Alembic 迁移已生成并执行（含 GIN 索引�?- [ ] 18 项关键指标全部可提取
- [ ] 趋势判定 6 种类型逻辑正确（improving/stagnant/declining/achieved/new/resolved�?- [ ] 报告对比覆盖 6 个维度（技术统�?落点/回合/球�?得分/问题变化�?- [ ] 线性回�?R² > 0.4 时填�?forecast 字段
- [ ] Redis 缓存生效（trends / trend_detail / problems TTL 1h；summary TTL 5min�?- [ ] 快照生成�?AI 流水�?Step 9 后自动触�?- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释�?- [ ] 无废话注释、无注释掉的死代�?
---

## 反幻觉约�?
- Service 方法 **必须** 使用 `@staticmethod`�?*禁止** 创建实例
- Schema **必须** 遵循命名：`{Entity}Brief`、`{Entity}Detail`、`{Entity}Response`、`Paginated{Entities}`
- **禁止** �?API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- 18 项指�?**必须** �?`analysis_report.result_data` JSONB 中提取，**禁止** 硬编码指标�?- 趋势判定 **必须** 基于 `change_rate` + `persistence_count`�?*禁止** 随意判定
- 线性回归预�?**必须** �?R² > 0.4 时才填充 forecast�?*禁止** �?R² 低时返回预测结果
- 查询接口 **必须** 设置 Redis 缓存（summary TTL 5min；trends / trend_detail / problems TTL 1h），快照生成�?**必须** 清除缓存
- **禁止** 跨用户查询数据（`user_id` 必须�?`get_current_user` 获取�?- `TechniqueTrend` 模型使用 `trend`/`current_value`/`previous_value` 字段名（�?DB 设计 v1.3 §2.22/§5.6 一致）。（X-3 已修复）
- `AnalysisReport.result_data` **必须** 使用 JSONB 类型，测试代码中 **必须** 直接�?dict�?*禁止** 使用 `json.dumps()`（X-4 修复�?- `AnalysisReport` 模型归属�?video_analysis 模块（DB 设计 §5.3），统一使用 `from app.models.video_analysis import AnalysisReport`�?*禁止** 使用 `app.models.analysis`（A-10 修复�?- `ProgressSnapshot`/`TechniqueTrend` 模型归属�?progress 模块，统一使用 `from app.models.progress import ProgressSnapshot, TechniqueTrend`�?*禁止** 使用 `app.models.progress_analysis`（A-11 修复�?- 所�?API 端点 **必须** 添加 `@limiter.limit("100/minute")` 限流装饰器，**禁止** 裸奔无限�?- `from app.core.limiter import limiter` **必须** 在路由文�?import 区声明，**禁止** 遗漏导入

### 覆盖度修复说�?
| 编号 | 修复内容 | 位置 |
|------|---------|------|
| X-3 | `TechniqueTrend` 使用 `trend`/`current_value`/`previous_value` 字段名（�?§5.6 一致），DB 设计 §2.22 �?`trend_direction` 需回写更新�?`trend` 并补�?`current_value`/`previous_value` | 反幻觉约�?|
| X-4 | `AnalysisReport.result_data` 统一使用 JSONB 类型，测试代码传 dict 不用 `json.dumps()`，移除多余的 `import json` | §2 测试 |
| A-4 | summary 端点缓存 TTL �?1h�?600s）改�?5min�?00s），趋势类端点保�?1h 不变 | §5 Service（get_summary）、�? API 路由、�? 验证清单 |
| A-10 | `AnalysisReport` import 路径统一�?`app.models.video_analysis`（原 `app.models.analysis`），模型归属�?video_analysis 模块（DB 设计 §5.3�?| §2 测试、�? Service |
| A-11 | `ProgressSnapshot`/`TechniqueTrend` import 路径统一�?`app.models.progress`（原 `app.models.progress_analysis`�?| §2 测试 |
| A-9 | `datetime.utcnow()` �?`datetime.now(timezone.utc)`；`default`/`onupdate` 改为 lambda 表达式；import 补充 `timezone` | §3 Model、�? Service |
