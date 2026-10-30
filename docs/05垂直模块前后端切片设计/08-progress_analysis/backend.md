# progress_analysis 模块 �?后端垂直切片设计

> **模块名称**：`progress_analysis`
> **所属目�?*：`app/api/v1/progress/` + `app/services/progress_service.py` + `app/models/progress.py` + `app/schemas/progress.py`
> **定位**：AI 分析报告完成后自动生成进度快照，计算 18 项技术指标趋势，支持报告对比、趋势详情、进度综合摘要与问题变化分析
> **依据**：模块详细设�?v1.2 §2.8、API 详细设计 v1.3 §9、数据库详细设计 v1.5 §2.21-2.22

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.8（progress_analysis 模块功能规格�?- [ ] 阅读 API 契约 §9�? 个端点：snapshots / technique-trends / technique-trends/{metric} / comparison / summary / problem-changes�?- [ ] 阅读 `app/models/progress.py`（ProgressSnapshot + TechniqueTrend 模型�?- [ ] 阅读 `app/models/video_analysis.py`（AnalysisReport 模型，result_data JSONB 结构�?- [ ] 阅读 `app/ai_pipeline/report_generator.py`（AI 流水�?Step 9 报告生成完成后触发快照生成）
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
# R13-P3 文档同步：对齐实际实现签名 —— _calculate_trend 为同步方法
# （R4-Progress-2 位置参数签名，返回 dict 仅含 trend/persistence_count）；
# generate_snapshot 返回 dict（幂等重入）；_linear_regression_forecast 为
# async(db, user_id)（与 R12-Prog-7 测试 TestForecastRSquaredFilter 同款）。
@pytest.mark.asyncio
async def test_generate_snapshot_extracts_18_metrics(db_session, auth_user):
    """快照生成时从 result_data 提取 18 项关键指标。"""
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

    # R13-P3 文档同步：generate_snapshot 返回 dict（非 ORM 对象；
    # 幂等：report_id 已存在时直接返回既有快照信息）
    snapshot = await ProgressService.generate_snapshot(
        user_id=auth_user["id"],
        report_id=report.id,
        result_data=report.result_data,
    )
    assert snapshot is not None
    metrics = snapshot["metrics_snapshot"]
    expected_keys = [
        "backhand_ratio", "forehand_ratio", "serve_ratio",
        "landing_forehand_pct", "landing_backhand_pct", "landing_middle_pct",
        "landing_dispersion", "avg_rally_length", "max_rally_length",
        "rally_frequency", "avg_ball_speed", "max_ball_speed",
        "score_win_rate", "key_point_win_rate", "serve_point_win_rate",
        "receive_point_win_rate", "attack_transition_rate", "error_rate",
    ]
    for k in expected_keys:
        assert k in metrics, f"指标 {k} 缺失"

@pytest.mark.asyncio
async def test_trend_judgment_improving():
    """趋势判定：连续 >=2 次向目标改善 + 变化率 >5% -> improving。"""
    from app.services.progress_service import ProgressService

    # R13-P3 文档同步：同步方法、位置参数（R4-Progress-2 签名），
    # 返回 dict 仅含 trend/persistence_count（无 change_rate 键）
    trend = ProgressService._calculate_trend(
        1, "backhand_ratio", 0.32,
        [0.18, 0.22, 0.25, 0.28, 0.30], 0.35,
    )
    assert trend["trend"] == "improving"
    assert trend["persistence_count"] >= 2

@pytest.mark.asyncio
async def test_trend_judgment_stagnant():
    """趋势判定：连续 >=3 次变化率 <5% 且数据 >=4 条 -> stagnant。"""
    from app.services.progress_service import ProgressService

    trend = ProgressService._calculate_trend(
        1, "avg_ball_speed", 18.0,
        [17.8, 17.9, 18.0, 18.1, 18.0], 20.0,
    )
    assert trend["trend"] == "stagnant"
    assert trend["persistence_count"] >= 3

@pytest.mark.asyncio
async def test_trend_judgment_resolved_and_new():
    """R12-Prog-2：历史有值但当前消失 -> resolved；无历史 -> new。"""
    from app.services.progress_service import ProgressService

    resolved = ProgressService._calculate_trend(
        1, "backhand_ratio", None, [0.2, 0.25], 0.35
    )
    assert resolved["trend"] == "resolved"

    first_seen = ProgressService._calculate_trend(
        1, "backhand_ratio", None, [], 0.35
    )
    assert first_seen["trend"] == "new"

@pytest.mark.asyncio
async def test_forecast_only_when_r2_above_threshold(db_session):
    """R^2 > 0.4 的时间序列产生预测；低 R^2 序列被过滤（R12-Prog-7）。"""
    from app.models.user import User
    from app.models.progress import TechniqueTrend
    from app.services.progress_service import ProgressService

    user = User(openid="progress_r2_user", nickname="预测质量用户", status="active")
    db_session.add(user)
    await db_session.flush()

    # 高 R^2：严格线性递增（backhand_ratio，up 方向，目标 0.35）
    db_session.add(TechniqueTrend(
        user_id=user.id,
        metric_name="backhand_ratio",
        current_value=0.31,
        target_value=0.35,
        time_series=[
            {"value": 0.25}, {"value": 0.27}, {"value": 0.29}, {"value": 0.31},
        ],
    ))
    # 低 R^2：锯齿序列（R^2 约 0.196 < 0.4）
    db_session.add(TechniqueTrend(
        user_id=user.id,
        metric_name="avg_rally_length",
        current_value=6.5,
        target_value=6.0,
        time_series=[
            {"value": 3.0}, {"value": 7.0}, {"value": 3.5}, {"value": 6.5},
        ],
    ))
    await db_session.commit()

    # R13-P3 文档同步：实际签名 async _linear_regression_forecast(db, user_id)，
    # 按用户全部 TechniqueTrend.time_series 计算（非单条 history 入参）
    forecast = await ProgressService._linear_regression_forecast(
        db_session, user.id
    )

    assert "backhand_ratio" in forecast
    entry = forecast["backhand_ratio"]
    assert entry["r_squared"] > 0.4
    assert entry["confidence"] == "high"
    assert "predicted_weeks_to_target" in entry

    # 低 R^2 序列被阈值过滤，不进入预测
    assert "avg_rally_length" not in forecast
```

---

## 3. Model（SQLAlchemy 2.0�?
```python
# app/models/progress.py
"""进度分析模型�?""

from sqlalchemy import BigInteger, String, Integer, Float, ForeignKey, Index, DateTime, UniqueConstraint
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
        # R13-P3 文档同步：实现为 UniqueConstraint（app/models/progress.py）
        UniqueConstraint("user_id", "metric_name", name="uq_trend_user_metric"),
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
# R13-P3 文档同步：以下为实际实现原文回写（app/services/progress_service.py）。
# 相对原样例的关键差异：async_session_factory 取代 get_async_session；快照幂等
# 重入（report_id 已存在直接返回 dict）；_calculate_trend 为同步方法且含
# resolved/new 早退分支（R12-Prog-2）；down 指标 target_progress None 防御
# （R7-Prog-2）；trend_detail 缓存 scan 清理（R7-Prog-3）；comparison 返回
# None 由路由层抛 422/404；_linear_regression_forecast 为 async(db, user_id)
# 且 slope 方向感知（R7-Prog-4）。
"""
app/services/progress_service.py - 进度分析业务逻辑层

依据：切片 08-progress_analysis/backend.md 4
功能：快照生成 + 趋势计算 + 报告对比 + 综合摘要 + 问题变化
缓存：summary 5min / trends+trend_detail+problems 1h
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.progress import ProgressSnapshot, TechniqueTrend
from app.models.video_analysis import AnalysisReport, VideoTask

logger = logging.getLogger(__name__)

CHANGE_RATE_THRESHOLD = 0.05
R_SQUARED_THRESHOLD = 0.4

METRIC_DEFINITIONS = {
    "backhand_ratio": {"name": "反手使用率", "target": 0.35, "direction": "up"},
    "forehand_ratio": {"name": "正手使用率", "target": 0.60, "direction": "down"},
    "serve_ratio": {"name": "发球使用率", "target": 0.05, "direction": "down"},
    "landing_forehand_pct": {"name": "正手区落点率", "target": 0.55, "direction": "down"},
    "landing_backhand_pct": {"name": "反手区落点率", "target": 0.30, "direction": "up"},
    "landing_middle_pct": {"name": "中路落点率", "target": 0.15, "direction": "up"},
    "landing_dispersion": {"name": "落点分散度", "target": 2.5, "direction": "down"},
    "avg_rally_length": {"name": "平均回合长度", "target": 6.0, "direction": "up"},
    "max_rally_length": {"name": "最长回合长度", "target": 15.0, "direction": "up"},
    "rally_frequency": {"name": "回合频率", "target": 1.5, "direction": "up"},
    "avg_ball_speed": {"name": "平均球速", "target": 20.0, "direction": "up"},
    "max_ball_speed": {"name": "最大球速", "target": 26.0, "direction": "up"},
    "score_win_rate": {"name": "胜率", "target": 0.60, "direction": "up"},
    "key_point_win_rate": {"name": "关键分胜率", "target": 0.55, "direction": "up"},
    "serve_point_win_rate": {"name": "发球得分率", "target": 0.60, "direction": "up"},
    "receive_point_win_rate": {"name": "接发球得分率", "target": 0.50, "direction": "up"},
    "attack_transition_rate": {"name": "攻防转换率", "target": 0.40, "direction": "up"},
    "error_rate": {"name": "失误率", "target": 0.08, "direction": "down"},
}

CACHE_TTL_SUMMARY = 300
CACHE_TTL_TRENDS = 3600
CACHE_TTL_PROBLEMS = 3600


class ProgressService:
    """进度分析业务逻辑层"""

    @staticmethod
    async def generate_snapshot(user_id: int, report_id: int, result_data: dict) -> Optional[dict]:
        """从分析报告 result_data 提取 18 项指标，生成快照"""
        metrics = ProgressService._extract_metrics(result_data)

        async with async_session_factory() as db:
            existing = await db.scalar(
                select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_id)
            )
            if existing:
                return {"id": existing.id, "report_id": report_id, "metrics_snapshot": metrics}

            snapshot = ProgressSnapshot(
                user_id=user_id,
                report_id=report_id,
                metrics_snapshot=metrics,
            )
            db.add(snapshot)
            await db.flush()

            await ProgressService._update_trends(db, user_id, snapshot)

            await db.commit()

            # 清理缓存
            redis = await get_redis()
            await redis.delete(
                f"progress:summary:{user_id}",
                f"progress:trends:{user_id}",
                f"progress:problems:{user_id}",
            )
            # R7-Prog-3: 清理 trend_detail 缓存（键含 metric 名，需 scan）
            trend_detail_keys = await redis.keys(f"progress:trend_detail:{user_id}:*")
            if trend_detail_keys:
                await redis.delete(*trend_detail_keys)

        return {"id": snapshot.id, "report_id": report_id, "metrics_snapshot": metrics}

    @staticmethod
    def _extract_metrics(result_data: dict) -> dict:
        """从 result_data JSONB 提取 18 项指标 — 直接从 technique_stats 读取比率值"""
        if not result_data:
            return {k: None for k in METRIC_DEFINITIONS}

        tech = result_data.get("technique_stats") or result_data.get("technique_distribution") or {}
        landing = result_data.get("landing_points") or result_data.get("landing_heatmap") or {}
        dist = landing.get("distribution", {})
        rally = result_data.get("rally_analysis", {})
        speed = result_data.get("ball_speed", {})
        score = result_data.get("score_analysis", {})

        return {
            # 技术统计比率 — 直接从 technique_stats 读取
            "backhand_ratio":         tech.get("backhand_ratio"),
            "forehand_ratio":         tech.get("forehand_ratio"),
            "serve_ratio":            tech.get("serve_ratio"),
            # 落点分布
            "landing_forehand_pct":   dist.get("forehand"),
            "landing_backhand_pct":   dist.get("backhand"),
            "landing_middle_pct":     dist.get("middle"),
            "landing_dispersion":     landing.get("dispersion"),
            # 回合分析
            "avg_rally_length":       rally.get("avg_rally_length"),
            "max_rally_length":       rally.get("max_rally_length"),
            "rally_frequency":        rally.get("rally_frequency"),
            # 球速
            "avg_ball_speed":         speed.get("avg_speed_mps"),
            "max_ball_speed":         speed.get("max_speed_mps"),
            # 得分分析
            "score_win_rate":         score.get("win_rate"),
            "key_point_win_rate":     score.get("key_point_win_rate"),
            "serve_point_win_rate":   score.get("serve_point_win_rate"),
            "receive_point_win_rate": score.get("receive_point_win_rate"),
            # 其他
            "attack_transition_rate": result_data.get("attack_transition_rate"),
            "error_rate":             result_data.get("error_rate"),
        }

    @staticmethod
    async def _update_trends(db: AsyncSession, user_id: int, snapshot: ProgressSnapshot) -> None:
        """更新趋势表 - 基于历史快照重算（R4-Progress-1）"""
        # 读取所有历史快照（按时间升序）
        rows = await db.execute(
            select(ProgressSnapshot)
            .where(ProgressSnapshot.user_id == user_id)
            .order_by(ProgressSnapshot.created_at.asc())
        )
        all_snapshots = rows.scalars().all()
        if not all_snapshots:
            return

        metrics = snapshot.metrics_snapshot or {}

        for metric_name, value in metrics.items():
            defn = METRIC_DEFINITIONS.get(metric_name)
            if not defn:
                continue

            # 从完整快照序列提取 values 列表
            history_values: list[float] = []
            time_series = []
            for s in all_snapshots:
                s_metrics = s.metrics_snapshot or {}
                v = s_metrics.get(metric_name)
                if v is not None:
                    history_values.append(v)
                    time_series.append({
                        "date": s.created_at.isoformat() if s.created_at else "",
                        "value": v,
                    })

            if len(history_values) > 20:
                history_values = history_values[-20:]
                time_series = time_series[-20:]

            target = defn["target"]

            # 调用 _calculate_trend（R4-Progress-2 新签名）
            trend_info = ProgressService._calculate_trend(
                user_id, metric_name, value, history_values, target
            )

            # 计算 change_rate 与 previous_value
            # R12-Prog-2: value 为 None（指标消失，trend=resolved）时 change_rate 置 None，
            # 避免 None - float TypeError（_calculate_trend 有早退保护，此处原先没有）
            if value is not None and len(history_values) >= 2 and history_values[-2] != 0:
                change_rate = round((value - history_values[-2]) / abs(history_values[-2]), 4)
            else:
                change_rate = None
            previous_value = history_values[-2] if len(history_values) >= 2 else None

            # UPSERT
            existing = await db.scalar(
                select(TechniqueTrend).where(
                    and_(TechniqueTrend.user_id == user_id, TechniqueTrend.metric_name == metric_name)
                )
            )

            if existing:
                existing.current_value = value
                existing.previous_value = previous_value
                existing.change_rate = change_rate
                existing.trend = trend_info["trend"]
                existing.persistence_count = trend_info["persistence_count"]
                existing.target_value = target
                existing.time_series = time_series
            else:
                tt = TechniqueTrend(
                    user_id=user_id,
                    metric_name=metric_name,
                    current_value=value,
                    previous_value=previous_value,
                    change_rate=change_rate,
                    trend=trend_info["trend"],
                    target_value=target,
                    persistence_count=trend_info["persistence_count"],
                    time_series=time_series,
                )
                db.add(tt)

    @staticmethod
    def _calculate_trend(
        user_id: int, metric_name: str, current_value: float,
        history_values: list[float], target_value: float
    ) -> dict:
        """计算趋势方向 - 基于历史值序列（R4-Progress-2）

        新签名兼容设计测试用例：persistence >= 2 约束加到 improving/declining；
        stagnant 分支死代码已修复。
        """
        # R7-Prog-1 + R12-Prog-2: current_value 为 None 时不再统一返回 new：
        # 历史有值但当前消失 → resolved（问题已解决，设计 6 种趋势类型之一）；
        # 无历史 → new（首次出现，当前值尚缺）
        if current_value is None:
            if history_values:
                return {"trend": "resolved", "persistence_count": 0}
            return {"trend": "new", "persistence_count": 0}
        if len(history_values) < 2:
            return {"trend": "new", "persistence_count": 0}

        defn = METRIC_DEFINITIONS.get(metric_name, {})
        direction = defn.get("direction", "up")

        previous = history_values[-2]
        if previous == 0:
            change_rate = None
        else:
            change_rate = round((current_value - previous) / abs(previous), 4)

        is_improving = (
            (direction == "up" and current_value > previous) or
            (direction == "down" and current_value < previous)
        )
        is_declining = (
            (direction == "up" and current_value < previous) or
            (direction == "down" and current_value > previous)
        )
        is_significant = abs(change_rate or 0) > CHANGE_RATE_THRESHOLD

        # 达标判断 - 基于历史值连续达标次数
        achieved_persistence = 0
        for v in reversed(history_values):
            if (direction == "up" and v >= target_value) or (direction == "down" and v <= target_value):
                achieved_persistence += 1
            else:
                break
        if achieved_persistence >= 2:
            return {"trend": "achieved", "persistence_count": achieved_persistence}

        # improving: 需 persistence >= 2
        if is_improving and is_significant:
            improving_persistence = 0
            for i in range(len(history_values) - 1, 0, -1):
                v_curr = history_values[i]
                v_prev = history_values[i - 1]
                if (direction == "up" and v_curr > v_prev) or (direction == "down" and v_curr < v_prev):
                    improving_persistence += 1
                else:
                    break
            if improving_persistence >= 2:
                return {"trend": "improving", "persistence_count": improving_persistence}

        # declining: 需 persistence >= 2
        if not is_improving and is_significant:
            declining_persistence = 0
            for i in range(len(history_values) - 1, 0, -1):
                v_curr = history_values[i]
                v_prev = history_values[i - 1]
                if (direction == "up" and v_curr < v_prev) or (direction == "down" and v_curr > v_prev):
                    declining_persistence += 1
                else:
                    break
            if declining_persistence >= 2:
                return {"trend": "declining", "persistence_count": declining_persistence}

        # stagnant: not is_significant 且 len>=4 且 persistence>=3
        if not is_significant:
            stagnant_persistence = 0
            for i in range(len(history_values) - 1, 0, -1):
                v_curr = history_values[i]
                v_prev = history_values[i - 1]
                rate = abs((v_curr - v_prev) / abs(v_prev)) if v_prev != 0 else 0
                if rate <= CHANGE_RATE_THRESHOLD:
                    stagnant_persistence += 1
                else:
                    break
            if len(history_values) >= 4 and stagnant_persistence >= 3:
                return {"trend": "stagnant", "persistence_count": stagnant_persistence}

        # R5-Prog-2: fallback - persistence 不足时按单次方向标记 improving/declining，
        # 避免误标单次改善/退步为 stagnant
        if is_improving:
            return {"trend": "improving", "persistence_count": 1}
        if is_declining:
            return {"trend": "declining", "persistence_count": 1}
        return {"trend": "stagnant", "persistence_count": 1}

    @staticmethod
    async def list_snapshots(user_id: int, period: str = "all", status: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        async with async_session_factory() as db:
            qs = select(ProgressSnapshot).where(ProgressSnapshot.user_id == user_id)
            count_qs = select(func.count()).select_from(ProgressSnapshot).where(
                ProgressSnapshot.user_id == user_id
            )

            if period != "all":
                now = datetime.now(timezone.utc)
                days = {"month": 30, "quarter": 90, "year": 365}.get(period, 30)
                start = now - timedelta(days=days)
                qs = qs.where(ProgressSnapshot.created_at >= start)
                count_qs = count_qs.where(ProgressSnapshot.created_at >= start)

            # R5-Prog-1: 按 VideoTask.status 过滤（AnalysisReport 无 status 列，改走 task 关系）
            if status:
                qs = qs.join(AnalysisReport, ProgressSnapshot.report_id == AnalysisReport.id).join(
                    VideoTask, AnalysisReport.task_id == VideoTask.id
                ).where(VideoTask.status == status)
                count_qs = count_qs.join(AnalysisReport, ProgressSnapshot.report_id == AnalysisReport.id).join(
                    VideoTask, AnalysisReport.task_id == VideoTask.id
                ).where(VideoTask.status == status)

            total = await db.scalar(count_qs) or 0
            qs = qs.order_by(ProgressSnapshot.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            rows = await db.execute(qs)
            items = [
                {
                    "id": r.id,
                    "report_id": r.report_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "metrics_snapshot": r.metrics_snapshot,
                }
                for r in rows.scalars().all()
            ]

        return {"total": total, "page": page, "page_size": page_size, "items": items}

    @staticmethod
    async def get_technique_trends(user_id: int) -> dict:
        redis = await get_redis()
        cache_key = f"progress:trends:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            rows = await db.execute(
                select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
            )
            trends = rows.scalars().all()

        metrics = []
        for t in trends:
            defn = METRIC_DEFINITIONS.get(t.metric_name, {})
            target = t.target_value or defn.get("target")
            direction = defn.get("direction", "up")
            # R7-Prog-2: None 不应被 or 0 强转为 0，down 指标会误判 100%
            if t.current_value is None:
                target_progress = None
            else:
                current = t.current_value
                if direction == "down":
                    target_progress = 100 if current == 0 else (min(100, int(target / current * 100)) if current > 0 else None)
                else:
                    target_progress = min(100, int(current / target * 100)) if target and target > 0 else None

            metrics.append({
                "metric": t.metric_name,
                "metric_name": defn.get("name", t.metric_name),
                "current_value": t.current_value,
                "previous_value": t.previous_value,
                "change_rate": t.change_rate,
                "trend": t.trend,
                "target": target,
                "target_progress": target_progress,
                "persistence_count": t.persistence_count,
            })

        result = {"metrics": metrics}
        await redis.setex(cache_key, CACHE_TTL_TRENDS, json.dumps(result))
        return result

    @staticmethod
    async def get_technique_trend_detail(user_id: int, metric: str) -> Optional[dict]:
        # R6-Prog-2: 仅当指标名不在 METRIC_DEFINITIONS 时返回 404；有效指标无趋势数据返回 null 字段
        if metric not in METRIC_DEFINITIONS:
            raise AppException("指标不存在", 404, code=40420)

        redis = await get_redis()
        cache_key = f"progress:trend_detail:{user_id}:{metric}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        defn = METRIC_DEFINITIONS[metric]
        default_target = defn.get("target", 0)
        direction = defn.get("direction", "up")

        async with async_session_factory() as db:
            t = await db.scalar(
                select(TechniqueTrend).where(
                    and_(TechniqueTrend.user_id == user_id, TechniqueTrend.metric_name == metric)
                )
            )

            if t:
                target = t.target_value or default_target
                # R6-Prog-3: down 指标 current==0 视为 100% 达成
                # R7-Prog-2: None 不应被 or 0 强转为 0，down 指标会误判 100%
                if t.current_value is None:
                    target_progress = None
                else:
                    current = t.current_value
                    if direction == "down":
                        target_progress = 100 if current == 0 else (min(100, int(target / current * 100)) if current > 0 else None)
                    else:
                        target_progress = min(100, int(current / target * 100)) if target > 0 else None

                result = {
                    "metric": metric,
                    "metric_name": defn.get("name", metric),
                    "current_value": t.current_value,
                    "target_value": target,
                    "target_progress": target_progress,
                    "trend": t.trend,
                    "change_rate": t.change_rate,
                    "persistence_count": t.persistence_count,
                    "history": t.time_series or [],
                }
            else:
                # R6-Prog-2: 有效指标无趋势数据 — 返回 null 字段而非 None（不缓存空结果）
                result = {
                    "metric": metric,
                    "metric_name": defn.get("name", metric),
                    "current_value": None,
                    "target_value": default_target,
                    "target_progress": None,
                    "trend": None,
                    "change_rate": None,
                    "persistence_count": None,
                    "history": [],
                }

        if t:
            await redis.setex(cache_key, CACHE_TTL_TRENDS, json.dumps(result))
        return result

    @staticmethod
    async def get_comparison(user_id: int, report_a: int, report_b: int) -> Optional[dict]:
        if report_a == report_b:
            return None

        async with async_session_factory() as db:
            ra = await db.scalar(select(AnalysisReport).where(
                AnalysisReport.id == report_a, AnalysisReport.user_id == user_id
            ))
            rb = await db.scalar(select(AnalysisReport).where(
                AnalysisReport.id == report_b, AnalysisReport.user_id == user_id
            ))
            if not ra or not rb:
                return None

            sa = await db.scalar(select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_a))
            sb = await db.scalar(select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_b))

            metrics_a = sa.metrics_snapshot if sa else ProgressService._extract_metrics(ra.result_data or {})
            metrics_b = sb.metrics_snapshot if sb else ProgressService._extract_metrics(rb.result_data or {})

            def _dim(keys: list) -> dict:
                """生成单维度对比 - 支持 (metric_key, output_key) 映射（R4-Progress-8）"""
                result = {}
                for k in keys:
                    if isinstance(k, tuple):
                        metric_key, output_key = k
                    else:
                        metric_key = output_key = k
                    va = metrics_a.get(metric_key, 0)
                    vb = metrics_b.get(metric_key, 0)
                    change = round(vb - va, 4) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
                    result[output_key] = {"a": va, "b": vb, "change": change}
                return result

            # 6 维度对比（对齐设计文档）
            comparisons = {
                # 维度 1: 技术统计
                "technique_stats": _dim(["forehand_ratio", "backhand_ratio", "serve_ratio"]),
                # 维度 2: 落点分布（R4-Progress-8: key 名改为 forehand_pct/backhand_pct/middle_pct）
                "landing": _dim([
                    ("landing_forehand_pct", "forehand_pct"),
                    ("landing_backhand_pct", "backhand_pct"),
                    ("landing_middle_pct", "middle_pct"),
                ]),
                # 维度 3: 回合分析
                "rally": {
                    "avg_length_a": metrics_a.get("avg_rally_length"),
                    "avg_length_b": metrics_b.get("avg_rally_length"),
                    "max_length_a": metrics_a.get("max_rally_length"),
                    "max_length_b": metrics_b.get("max_rally_length"),
                    "change": round(
                        (metrics_b.get("avg_rally_length", 0) - metrics_a.get("avg_rally_length", 0)), 2
                    ) if metrics_a.get("avg_rally_length") is not None and metrics_b.get("avg_rally_length") is not None else None,
                },
                # 维度 4: 球速
                "ball_speed": {
                    "avg_a": metrics_a.get("avg_ball_speed"),
                    "avg_b": metrics_b.get("avg_ball_speed"),
                    "max_a": metrics_a.get("max_ball_speed"),
                    "max_b": metrics_b.get("max_ball_speed"),
                    "change": round(
                        (metrics_b.get("avg_ball_speed", 0) - metrics_a.get("avg_ball_speed", 0)), 2
                    ) if metrics_a.get("avg_ball_speed") is not None and metrics_b.get("avg_ball_speed") is not None else None,
                },
                # 维度 5: 得分分析
                "score_analysis": {
                    "win_rate_a": metrics_a.get("score_win_rate"),
                    "win_rate_b": metrics_b.get("score_win_rate"),
                    "change": round(
                        (metrics_b.get("score_win_rate", 0) - metrics_a.get("score_win_rate", 0)), 4
                    ) if metrics_a.get("score_win_rate") is not None and metrics_b.get("score_win_rate") is not None else None,
                },
                # 维度 6: 问题变化
                "problem_changes": await ProgressService._compute_problem_changes(db, user_id, ra, rb),
            }

        return {
            "report_a": {"id": report_a, "created_at": ra.created_at.isoformat() if ra.created_at else None},
            "report_b": {"id": report_b, "created_at": rb.created_at.isoformat() if rb.created_at else None},
            "comparisons": comparisons,
        }

    @staticmethod
    async def get_summary(user_id: int) -> dict:
        redis = await get_redis()
        cache_key = f"progress:summary:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            total = await db.scalar(
                select(func.count()).select_from(ProgressSnapshot).where(ProgressSnapshot.user_id == user_id)
            ) or 0

            trends_rows = await db.execute(
                select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
            )
            trends = trends_rows.scalars().all()

            improving = sum(1 for t in trends if t.trend == "improving")
            declining = sum(1 for t in trends if t.trend == "declining")
            if improving > declining:
                overall = "improving"
            elif declining > improving:
                overall = "declining"
            else:
                overall = "stagnant"

            metric_trends = []
            for t in trends:
                defn = METRIC_DEFINITIONS.get(t.metric_name, {})
                target = t.target_value or defn.get("target", 0)
                direction = defn.get("direction", "up")
                # R7-Prog-2: None 不应被 or 0 强转为 0，down 指标会误判 100%
                if t.current_value is None:
                    target_progress = None
                else:
                    current = t.current_value
                    if direction == "down":
                        target_progress = 100 if current == 0 else (min(100, int(target / current * 100)) if current > 0 else None)
                    else:
                        target_progress = min(100, int(current / target * 100)) if target and target > 0 else None
                metric_trends.append({
                    "metric": t.metric_name,
                    "metric_name": defn.get("name", t.metric_name),
                    "current_value": t.current_value,
                    "previous_value": t.previous_value,
                    "change_rate": t.change_rate,
                    "trend": t.trend,
                    "target": target,
                    "target_progress": target_progress,
                    "persistence_count": t.persistence_count,
                })

            problem_changes = await ProgressService._get_problem_changes(db, user_id)
            forecast = await ProgressService._linear_regression_forecast(db, user_id)

            # 查询用户当前训练方案状态（R4-Progress-4: 添加 last_adjustment/adjustment_reason/goal_completion）
            from app.models.training import TrainingPlan, PlanAdjustment
            plan = await db.scalar(
                select(TrainingPlan)
                .where(TrainingPlan.user_id == user_id)
                .order_by(TrainingPlan.updated_at.desc())
                .limit(1)
            )
            if plan:
                # 查询最近一次 PlanAdjustment 记录
                adj = await db.scalar(
                    select(PlanAdjustment)
                    .where(PlanAdjustment.training_plan_id == plan.id)
                    .order_by(PlanAdjustment.created_at.desc())
                    .limit(1)
                )
                # R5-Prog-3: 计算 goal_completion — 按 direction 区分计算
                # up: current/target, down: target/current；返回字符串格式如 "91%"
                goal_metrics = plan.goal_metrics or {}
                trends_map = {t.metric_name: t for t in trends}
                goal_completion = {}
                for metric, target in goal_metrics.items():
                    t = trends_map.get(metric)
                    defn = METRIC_DEFINITIONS.get(metric, {})
                    direction = defn.get("direction", "up")
                    if t and t.current_value is not None and target:
                        if direction == "down":
                            progress = 100 if t.current_value == 0 else min(100, int(target / t.current_value * 100))
                        else:
                            progress = min(100, int(t.current_value / target * 100)) if t.current_value > 0 else 0
                        goal_completion[metric] = f"{progress}%"
                    else:
                        goal_completion[metric] = "0%"
                training_plan_status = {
                    "current_plan_id": str(plan.id),
                    "plan_version": plan.version,
                    "last_adjustment": adj.created_at.isoformat() if adj and adj.created_at else None,
                    "adjustment_reason": adj.adjustment_reason if adj else None,
                    "goal_completion": goal_completion,
                }
            else:
                training_plan_status = None

        result = {
            "summary_period": "no_data" if total <= 0 else "recent" if total <= 3 else "last_3_months",
            "total_analyses": total,
            "overall_progress": overall,
            "metric_trends": metric_trends,
            "problem_changes": {
                "new": [p.get("problem_name", str(p)) if isinstance(p, dict) else str(p) for p in problem_changes.get("new", [])],
                "resolved": [p.get("problem_name", str(p)) if isinstance(p, dict) else str(p) for p in problem_changes.get("resolved", [])],
                "persistent": [p.get("problem_name", str(p)) if isinstance(p, dict) else str(p) for p in problem_changes.get("persistent", [])],
            },
            "training_plan_status": training_plan_status,
            "forecast": forecast,
        }

        await redis.setex(cache_key, CACHE_TTL_SUMMARY, json.dumps(result))
        return result

    @staticmethod
    async def get_problem_changes(user_id: int) -> dict:
        redis = await get_redis()
        cache_key = f"progress:problems:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            result = await ProgressService._get_problem_changes(db, user_id)

        await redis.setex(cache_key, CACHE_TTL_PROBLEMS, json.dumps(result))
        return result

    @staticmethod
    async def _get_problem_changes(db: AsyncSession, user_id: int) -> dict:
        """计算问题变化 — 返回 ProblemChangeItem 结构化对象"""
        reports = await db.execute(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user_id)
            .order_by(AnalysisReport.created_at.desc())
            .limit(10)
        )
        all_reports = reports.scalars().all()
        if not all_reports:
            return {"new": [], "resolved": [], "persistent": []}

        # 提取每份报告的问题列表
        all_issues = []
        for r in all_reports:
            report_text = r.report_text or {}
            if isinstance(report_text, str):
                try:
                    report_text = json.loads(report_text)
                except (json.JSONDecodeError, TypeError):
                    report_text = {}
            raw_issues = report_text.get("issues", []) if report_text else []
            # 提取问题标识（处理 dict 和 str 两种情况）
            issue_items = []
            for p in raw_issues:
                if isinstance(p, dict):
                    issue_items.append({
                        "id": p.get("problem_id", str(p.get("problem_name", p))),
                        "name": str(p.get("problem_name", p.get("problem_id", p))),
                    })
                else:
                    issue_items.append({"id": str(p), "name": str(p)})
            all_issues.append({
                "report_id": r.id,
                "created_at": r.created_at,
                "issues": issue_items,
            })

        # 只有 1 份报告时，所有问题视为首次出现
        if len(all_issues) == 1:
            first_report = all_issues[0]
            new_items = [
                {
                    "problem_id": f"PROBLEM_NEW_{i}",
                    "problem_name": item["name"],
                    "first_seen": first_report["created_at"].strftime("%Y-%m-%d") if first_report["created_at"] else None,
                    "last_seen": None,
                    "persistence_count": None,
                }
                for i, item in enumerate(first_report["issues"])
            ]
            return {"new": new_items, "resolved": [], "persistent": []}

        # 2+ 份报告：最新 vs 历史对比
        latest_issue_ids = set(i["id"] for i in all_issues[0]["issues"])
        previous_issue_ids = set()
        for a in all_issues[1:]:
            previous_issue_ids.update(i["id"] for i in a["issues"])

        new_ids = latest_issue_ids - previous_issue_ids
        resolved_ids = previous_issue_ids - latest_issue_ids
        persistent_ids = latest_issue_ids & previous_issue_ids

        # 构建 name 映射
        id_to_name = {}
        for a in all_issues:
            for i in a["issues"]:
                if i["id"] not in id_to_name:
                    id_to_name[i["id"]] = i["name"]

        # 构建 ProblemChangeItem 结构化对象
        new_items = [
            {
                "problem_id": f"PROBLEM_NEW_{i}",
                "problem_name": id_to_name.get(pid, str(pid)),
                "first_seen": all_issues[0]["created_at"].strftime("%Y-%m-%d") if all_issues[0]["created_at"] else None,
                "last_seen": None,
                "persistence_count": None,
            }
            for i, pid in enumerate(new_ids)
        ]
        resolved_items = [
            {
                "problem_id": f"PROBLEM_RESOLVED_{i}",
                "problem_name": id_to_name.get(pid, str(pid)),
                "first_seen": None,
                "last_seen": all_issues[1]["created_at"].strftime("%Y-%m-%d") if len(all_issues) > 1 and all_issues[1]["created_at"] else None,
                "persistence_count": None,
            }
            for i, pid in enumerate(resolved_ids)
        ]
        persistent_items = [
            {
                "problem_id": f"PROBLEM_PERSIST_{i}",
                "problem_name": id_to_name.get(pid, str(pid)),
                "first_seen": None,
                "last_seen": all_issues[0]["created_at"].strftime("%Y-%m-%d") if all_issues[0]["created_at"] else None,
                "persistence_count": sum(1 for a in all_issues if pid in set(i["id"] for i in a["issues"])),
            }
            for i, pid in enumerate(persistent_ids)
        ]

        return {
            "new": new_items,
            "resolved": resolved_items,
            "persistent": persistent_items,
        }

    @staticmethod
    async def _compute_problem_changes(
        db: AsyncSession, user_id: int, report_a: AnalysisReport, report_b: AnalysisReport
    ) -> dict:
        """两次报告对比的问题变化（get_comparison 维度 6）"""
        def _extract_issues(report: AnalysisReport) -> set:
            rt = report.report_text or {}
            if isinstance(rt, str):
                try:
                    rt = json.loads(rt)
                except (json.JSONDecodeError, TypeError):
                    rt = {}
            raw_issues = rt.get("issues", []) if rt else []
            # 处理 issues 为 dict 或 str 的情况
            ids = set()
            for p in raw_issues:
                if isinstance(p, dict):
                    ids.add(p.get("problem_id", str(p.get("problem_name", p))))
                else:
                    ids.add(str(p))
            return ids

        issues_a = _extract_issues(report_a)
        issues_b = _extract_issues(report_b)

        # R4-Progress-5: API 设计要求 list[str]，返回问题标识列表
        return {
            "new": list(issues_b - issues_a),
            "resolved": list(issues_a - issues_b),
            "persistent": list(issues_a & issues_b),
        }

    @staticmethod
    async def _linear_regression_forecast(db: AsyncSession, user_id: int) -> dict:
        """线性回归预测 — 基于 TechniqueTrend.time_series 预测到达目标周数"""
        trends = await db.execute(
            select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
        )
        rows = trends.scalars().all()
        if not rows:
            return {}

        forecast = {}
        for t in rows:
            series = t.time_series or []
            # R4-Progress-3: 数据点阈值从 2 改为 3
            if len(series) < 3:
                continue

            # 简单线性回归: y = slope * x + intercept
            n = len(series)
            x_vals = list(range(n))
            y_vals = [float(v["value"]) for v in series if isinstance(v, dict) and v.get("value") is not None]

            # R4-Progress-3: 数据点阈值从 2 改为 3
            if len(y_vals) < 3:
                continue

            m = len(y_vals)
            sum_x = sum(x_vals[:m])
            sum_y = sum(y_vals)
            sum_xy = sum(x * y for x, y in zip(x_vals[:m], y_vals))
            sum_x2 = sum(x * x for x in x_vals[:m])

            denominator = m * sum_x2 - sum_x * sum_x
            if denominator == 0:
                continue

            slope = (m * sum_xy - sum_x * sum_y) / denominator
            intercept = (sum_y - slope * sum_x) / m

            # 计算 R²
            y_mean = sum_y / m
            ss_tot = sum((y - y_mean) ** 2 for y in y_vals)
            ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(x_vals[:m], y_vals))
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            # R² 阈值过滤：低质量数据不预测
            if r_squared < 0.4:
                continue

            # 预测到达目标的周数
            target = t.target_value
            predicted_weeks = None
            # R7-Prog-4: slope 检查改为方向感知
            # up 指标 slope > 0 表示改善；down 指标 slope < 0 表示改善（向目标下降）
            direction = METRIC_DEFINITIONS.get(t.metric_name, {}).get("direction", "up")
            if target and direction == "up" and slope > 0:
                # y = slope * x + intercept → x = (target - intercept) / slope
                weeks_to_target = (target - intercept) / slope
                if weeks_to_target > 0:
                    predicted_weeks = int(weeks_to_target * 2)
            elif target and direction == "down" and slope < 0:
                # down 指标：slope < 0 表示改善（下降），用 abs(slope) 计算周数
                weeks_to_target = (intercept - target) / abs(slope)
                if weeks_to_target > 0:
                    predicted_weeks = int(weeks_to_target * 2)

            confidence = "high" if r_squared > 0.7 else "medium"

            forecast[t.metric_name] = {
                "predicted_weeks_to_target": predicted_weeks,
                "confidence": confidence,
                "r_squared": round(r_squared, 4),
            }

        return forecast
```

---

## 5.5 进度快照生成集成（report_generator 直调）

> **R13-P3 文档同步**：原设计为 `app/tasks/progress_analysis_beat.py` Celery 任务
> （`progress_analysis.generate_snapshot`，由分析流水线 `send_task` 事件驱动触发）。
> 实际实现**无此 Celery 任务** —— 快照生成由报告生成器 `_trigger_cascade` 级联链
> 中**直接 await** 调用（R12-Prog-1）：`result_data` 直传免二次读取、失败不阻塞
> 报告主流程、无需 beat_schedule 注册。训练建议仍走 Celery
> （`generate_advice_task.delay`）。

```python
# app/ai_pipeline/report_generator.py（节选 — 实际集成点，完整实现见源文件）
class ReportGenerator:

    @staticmethod
    async def generate(task_id: int, step_results: dict) -> dict:
        ...
        # 4. 触发级联（try/except 不阻塞）
        await ReportGenerator._trigger_cascade(
            task_id, report_id, task.user_id, result_data
        )
        ...

    @staticmethod
    async def _trigger_cascade(
        task_id: int, report_id: int, user_id: int, result_data: dict | None = None,
    ) -> None:
        """级联触发（try/except 不阻塞）：
        游戏化积分 -> 训练建议（Celery）-> 进度快照 -> 看板缓存失效
        """
        # 游戏化积分
        try:
            from app.services.gamification_service import GamificationService
            async with async_session_factory() as db:
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="analysis", ref_id=report_id
                )
        except Exception as e:
            logger.error("cascade_gamification_failed", extra={"error": str(e)})

        # R12-Training-B1: 训练建议异步生成（eager 模式同步执行，生产模式投递队列）
        try:
            from app.tasks.training import generate_advice_task
            generate_advice_task.delay(user_id, report_id)
        except Exception as e:
            logger.error("cascade_generate_advice_failed", extra={"error": str(e)})

        # R12-Prog-1: 进度快照生成 — 报告完成后自动写入 ProgressSnapshot
        try:
            from app.services.progress_service import ProgressService
            await ProgressService.generate_snapshot(
                user_id=user_id, report_id=report_id,
                result_data=result_data or {},
            )
        except Exception as e:
            logger.error("cascade_generate_snapshot_failed", extra={"error": str(e)})

        # R12-Dash-1: 看板缓存失效 — 分析完成后清除该用户 dashboard 缓存
        try:
            from app.services.dashboard_service import DashboardService
            await DashboardService.bust_cache(user_id, "analysis_complete")
        except Exception as e:
            logger.error("cascade_bust_cache_failed", extra={"error": str(e)})
```

---

## 6. API 路由（FastAPI�?
```python
# app/api/v1/progress/router.py
# R13-P3 文档同步：以下为实际实现原文回写。装饰器顺序 @router.* 在上、
# @limiter.limit 在下（slowapi 生效要求）且端点含 request: Request 参数；
# comparison 同报告 422(code 42201)/报告不存在 404(code 40412) 路由守卫；
# snapshots 含 status 过滤参数（R4-Progress-11）。
"""
app/api/v1/progress/router.py - 进度分析 API 路由

依据：API 9 / 切片 08-progress_analysis/backend.md 6
6 个端点：snapshots / technique-trends / technique-trends/{metric} / comparison / summary / problem-changes
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.exceptions import AppException
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.services.progress_service import ProgressService
from typing import Optional

router = APIRouter(prefix="/progress", tags=["进度分析"])


@router.get("/snapshots", summary="快照列表")
@limiter.limit("100/minute")
async def list_snapshots(
    request: Request,
    period: str = Query(default="all", pattern="^(month|quarter|year|all)$"),
    # R4-Progress-11: 添加 status 过滤参数
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    data = await ProgressService.list_snapshots(user.id, period=period, status=status, page=page, page_size=page_size)
    return success(data=data)


@router.get("/technique-trends", summary="技术趋势")
@limiter.limit("100/minute")
async def get_technique_trends(
    request: Request,
    user: User = Depends(get_current_user),
):
    data = await ProgressService.get_technique_trends(user.id)
    return success(data=data)


@router.get("/technique-trends/{metric}", summary="单项趋势详情")
@limiter.limit("100/minute")
async def get_technique_trend_detail(
    request: Request,
    metric: str,
    user: User = Depends(get_current_user),
):
    data = await ProgressService.get_technique_trend_detail(user.id, metric)
    return success(data=data)


@router.get("/comparison", summary="报告对比")
@limiter.limit("100/minute")
async def get_comparison(
    request: Request,
    report_a: int = Query(ge=1),
    report_b: int = Query(ge=1),
    user: User = Depends(get_current_user),
):
    if report_a == report_b:
        raise AppException("两份报告不能相同", 422, code=42201)
    data = await ProgressService.get_comparison(user.id, report_a, report_b)
    if not data:
        raise AppException("报告不存在", 404, code=40412)
    return success(data=data)


@router.get("/summary", summary="综合摘要")
@limiter.limit("100/minute")
async def get_summary(
    request: Request,
    user: User = Depends(get_current_user),
):
    data = await ProgressService.get_summary(user.id)
    return success(data=data)


@router.get("/problem-changes", summary="问题变化")
@limiter.limit("100/minute")
async def get_problem_changes(
    request: Request,
    user: User = Depends(get_current_user),
):
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

### R13-P3 文档同步（Round 13 复验，Progress 模块）

以实现为准回写，涉及 §1/§2.4/§3/§5/§5.5/§6。注：本文档部分行含历史 mojibake
损坏（注释与代码挤在同一物理行）；本轮回写的 §2.4/§5/§5.5/§6 块均为干净文本。

| # | 差异 | 修改位置 |
|---|------|---------|
| P1 | §1 阅读清单 `app/services/ai_pipeline_service.py` -> `app/ai_pipeline/report_generator.py`（实际集成点所在文件） | §1 |
| P2 | §2.4 测试样例对齐实际签名：`_calculate_trend` 同步方法（位置参数，返回 dict 仅含 trend/persistence_count，无 change_rate 键）；`generate_snapshot` 返回 dict（`snapshot["metrics_snapshot"]` 访问）；`_linear_regression_forecast` 实为 async(db, user_id) 按用户全量趋势计算；补 resolved/new 判定用例（R12-Prog-2） | §2.4 |
| P3 | `Index("uq_trend_user_metric", ..., unique=True)` -> `UniqueConstraint("user_id", "metric_name", name="uq_trend_user_metric")`（对齐 app/models/progress.py） | §3 |
| P4 | §5 样例整块以实际实现原文回写：`async_session_factory`、快照幂等重入、`_calculate_trend` 同步新签名含 resolved 分支、down 指标 target_progress None 防御、trend_detail 缓存 scan 清理、comparison 返回 None 由路由守卫、summary 含 training_plan_status/goal_completion、forecast 方向感知 slope | §5 |
| P5 | §5.5 原 Celery 任务（progress_analysis_beat.py + send_task 事件驱动）-> `report_generator._trigger_cascade` 直接 await `generate_snapshot`（R12-Prog-1，result_data 直传免二次读取） | §5.5 |
| P6 | §6 路由样例以实际实现回写：装饰器顺序（@router.* 在上、@limiter.limit 在下）+ request: Request 参数；comparison 422/404 路由守卫；snapshots status 过滤（R4-Progress-11） | §6 |
