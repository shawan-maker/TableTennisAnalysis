"""
app/schemas/progress.py - 进度分析 Schema
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SnapshotListQuery(BaseModel):
    period: str = Field(default="all", pattern="^(month|quarter|year|all)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class ComparisonQuery(BaseModel):
    report_a: int = Field(ge=1)
    report_b: int = Field(ge=1)


class SnapshotBrief(BaseModel):
    id: int
    report_id: int
    created_at: Optional[datetime] = None
    metrics_snapshot: dict

    model_config = {"from_attributes": True}


class MetricTrendBrief(BaseModel):
    metric: str
    metric_name: str
    current_value: Optional[float] = None
    previous_value: Optional[float] = None
    change_rate: Optional[float] = None
    trend: Optional[str] = None
    target: Optional[float] = None
    target_progress: Optional[int] = None
    persistence_count: int = 0


class TechniqueTrendsResponse(BaseModel):
    metrics: list[MetricTrendBrief] = []


class TrendHistoryPoint(BaseModel):
    date: str
    value: float


class TechniqueTrendDetail(BaseModel):
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
    a: Optional[Any] = None
    b: Optional[Any] = None
    change: Optional[float] = None


class ProblemChanges(BaseModel):
    new: list[str] = []
    resolved: list[str] = []
    persistent: list[str] = []


class ComparisonResponse(BaseModel):
    report_a: dict
    report_b: dict
    comparisons: dict


class ForecastItem(BaseModel):
    predicted_weeks_to_target: Optional[int] = None
    confidence: str
    r_squared: float


class ProblemChanges(BaseModel):
    new: list[str] = []
    resolved: list[str] = []
    persistent: list[str] = []


class TrainingPlanStatus(BaseModel):
    current_plan_id: Optional[str] = None
    plan_version: Optional[int] = None
    last_adjustment: Optional[str] = None
    adjustment_reason: Optional[str] = None
    goal_completion: dict = {}


class SummaryResponse(BaseModel):
    summary_period: str
    total_analyses: int
    overall_progress: str
    metric_trends: list[MetricTrendBrief] = []
    problem_changes: ProblemChanges
    training_plan_status: Optional[TrainingPlanStatus] = None
    forecast: dict = {}


class ProblemChangeItem(BaseModel):
    problem_id: str
    problem_name: str
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    persistence_count: Optional[int] = None


class ProblemChangesResponse(BaseModel):
    new: list[ProblemChangeItem] = []
    resolved: list[ProblemChangeItem] = []
    persistent: list[ProblemChangeItem] = []
