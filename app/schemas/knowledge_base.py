"""
app/schemas/knowledge_base.py - 知识库 Schema
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class CategoryBrief(BaseModel):
    id: int
    name: str
    code: str


class CategoryDetail(CategoryBrief):
    content: dict = {}
    created_at: Optional[datetime] = None


class EntryBrief(BaseModel):
    id: int
    category_id: int
    title: str
    entry_type: str


class EntryDetail(EntryBrief):
    content: dict = {}
    created_at: Optional[datetime] = None


class RuleBrief(BaseModel):
    id: int
    rule_id: str
    rule_name: str
    rule_type: str
    is_active: bool = True


class RuleDetail(RuleBrief):
    condition: dict = {}
    diagnosis: dict = {}
    training_methods: Optional[list] = None
    training_plan_template: Optional[str] = None
    adjustment_action: Optional[str] = None


class TemplateBriefSchema(BaseModel):
    id: int
    template_code: str
    name: str
    problem_id: Optional[str] = None


class TemplateDetailSchema(TemplateBriefSchema):
    template_data: dict = {}
    created_at: Optional[datetime] = None


class MatchResult(BaseModel):
    rule_id: str
    rule_name: str
    rule_type: str
    problem_id: str
    problem_name: str
    severity: str
    suggestion: str
    adjustment_action: Optional[str] = None
    training_methods: Optional[list[str]] = None
    training_plan_template: Optional[str] = None


class RuleContext(BaseModel):
    metrics: dict[str, Any] = {}
    trends: dict[str, dict] = {}
    current_plan: Optional[dict] = None
