"""
app/schemas/training.py - 训练建议 Schema
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DiagnosisItem(BaseModel):
    problem_id: str
    problem_name: str
    severity: str  # low/medium/high
    trend: str  # improving/stagnant/declining/achieved/new/resolved
    description: str


class SuggestionItem(BaseModel):
    type: str  # progress_confirm/persistent_warning/new_issue/first_analysis
    text: str


class TrainingMethodItem(BaseModel):
    method_id: str
    name: str
    description: str


class TrainingAdviceResponse(BaseModel):
    report_id: int
    is_first_analysis: bool
    diagnosis: list[DiagnosisItem] = []
    suggestions: list[SuggestionItem] = []
    training_methods: list[TrainingMethodItem] = []
    training_plan_template: Optional[str] = None


class TemplateBrief(BaseModel):
    id: int
    template_code: str
    name: str
    problem_id: Optional[str] = None

    model_config = {"from_attributes": True}


class TemplateDetail(TemplateBrief):
    template_data: dict = {}
    created_at: Optional[datetime] = None


class TemplateListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[TemplateBrief] = []


class AdjustmentItem(BaseModel):
    id: int
    version: int
    action: str
    reason: str
    trigger_report_id: Optional[int] = None
    created_at: Optional[datetime] = None
    changes_summary: str = ""

    model_config = {"from_attributes": True}


class PlanAdjustmentsResponse(BaseModel):
    plan_id: int
    current_version: int
    adjustments: list[AdjustmentItem] = []


class ReEvaluateResponse(BaseModel):
    plan_id: int
    action: str
    reason: str


class TrainingSessionBrief(BaseModel):
    id: int
    plan_id: int
    name: str
    is_completed: bool = False
    scheduled_date: Optional[str] = None
    completed_at: Optional[datetime] = None
    session_index: int = Field(...)
    reps: int = Field(...)

    model_config = {"from_attributes": True}


class TrainingSessionListResponse(BaseModel):
    plan_id: int
    total: int
    page: int
    page_size: int
    items: list[TrainingSessionBrief] = []


class TrainingSessionCompleteResponse(BaseModel):
    session_id: int
    is_completed: bool = True
    plan_progress: int = 0
    points_earned: int = 0
    completed_at: Optional[datetime] = None
