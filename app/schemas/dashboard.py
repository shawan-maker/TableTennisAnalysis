"""
app/schemas/dashboard.py — 数据看板 Pydantic Schema

依据：切片 06-data_dashboard/backend.md §4
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AdviceSummaryBrief(BaseModel):
    """最近训练建议摘要"""
    report_id: int
    summary: str = ""
    has_unresolved_issues: bool = False
    latest_report_at: Optional[datetime] = None


class OverviewResponse(BaseModel):
    """概览卡片"""
    win_rate: float = 0.0
    wins: int = 0
    losses: int = 0
    analysis_count: int = 0
    training_frequency_per_week: int = 0
    streak_days: int = 0
    trend: str = "flat"  # up/down/flat
    latest_advice_summary: Optional[AdviceSummaryBrief] = None


class TrendSeries(BaseModel):
    """趋势数据系列"""
    name: str
    data: list[float | int]


class WinRateTrendResponse(BaseModel):
    """战绩趋势"""
    labels: list[str]
    series: list[TrendSeries]


class TechniqueItem(BaseModel):
    """技术统计项"""
    name: str
    value: int
    color: str


class TechniqueStatsResponse(BaseModel):
    """技术统计"""
    technique_distribution: list[TechniqueItem]


class LandingHeatmapResponse(BaseModel):
    """落点热图"""
    nine_grid: list[list[int]]
    distribution: dict
    total_rallies: int
    source_reports_count: int


class MatchRecordBrief(BaseModel):
    """比赛记录摘要"""
    id: int
    opponent_name: Optional[str] = None
    my_score: int
    opponent_score: int
    is_win: bool
    format: str = "bo5"
    match_type: str = "friendly"
    match_date: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MatchRecordsResponse(BaseModel):
    """比赛记录列表分页响应"""
    total: int
    page: int
    page_size: int
    items: list[MatchRecordBrief]
