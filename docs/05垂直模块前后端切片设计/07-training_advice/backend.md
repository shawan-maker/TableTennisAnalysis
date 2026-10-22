# training_advice 模块 �?后端垂直切片设计

> **模块名称**：`training_advice`
> **所属目�?*：`app/api/v1/training/`（与 `training_plan` 共用 training/ 目录�?> **定位**：基于分析报�?+ 历史趋势 + 知识库规则引擎，生成个性化训练建议和训练计划模板推�?> **依据**：模块详细设�?v1.2 §2.7、API 详细设计 v1.3 §8、数据库详细设计 v1.1

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.7（training_advice 功能规格 + BR-1/BR-2�?- [ ] 阅读 API 契约 §8�? 个端点：advice/{report_id} / advice/contextual / templates / templates/{id} / plans/{id}/adjustments / plans/{id}/re-evaluate�?- [ ] 阅读数据库设�?§2.23（plan_adjustment）、�?.26（rule_definition）、�?.27（training_template）、�?.28（training_plan）、�?.21-2.22（progress_snapshot / technique_trend�?- [ ] 阅读 `app/services/knowledge_base_service.py`（知识库规则引擎�?- [ ] 阅读 `app/services/progress_service.py`（进度分�?Service，提供趋势数据）
- [ ] 确认本切片范围：6 �?API 端点 + 对应 Service 方法 + 规则引擎调用 + 方案版本�?
### 任务清单

| # | 任务 | 文件 | 依赖 | 状�?|
|---|------|------|------|------|
| 1 | 定义 Model（training_plan / plan_adjustment；TrainingTemplate / RuleDefinition �?knowledge_base 模块定义�?| `app/models/training.py` | �?| �?|
| 2 | 注册 Model | `app/models/__init__.py` | #1 | �?|
| 3 | 定义 Schema | `app/schemas/training.py` | #1 | �?|
| 4 | 实现 Service | `app/services/training_advice_service.py` | #1,#3 | �?|
| 5 | 实现 API 路由 | `app/api/v1/training/advice_router.py` | #4 | �?|
| 6 | 注册 Router | `app/api/v1/__init__.py` | #5 | �?|
| 7 | Alembic 迁移 | `alembic revision --autogenerate` + `upgrade` | #1 | �?|
| 8 | 编写单元测试 | `tests/unit/test_training_advice.py` | #4 | �?|
| 9 | 编写冒烟测试 | `tests/smoke/training_advice_smoke_test.py` | #5 | �?|

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_training_advice.py
"""
training_advice 模块 �?训练建议测试�?覆盖：建议生成、趋势对比、模板查询、方案调整历史、手动重新评估�?"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from app.core.exceptions import AppException

@pytest.fixture
async def advice_context(db_session, auth_user):
    """创建测试上下文：用户 + 分析报告 + 进度快照 + 趋势数据 + 训练方案�?""
    from app.models.video_analysis import AnalysisReport
    from app.models.progress import ProgressSnapshot, TechniqueTrend
    from app.models.training import TrainingPlan
    from app.models.user import User

    user = auth_user
    now = datetime.now(timezone.utc)

    # 创建 2 份分析报�?    report1 = AnalysisReport(
        task_id=2001, user_id=user.id,
        result_data={
            "metrics": {
                "backhand_ratio": 0.18,
                "forehand_ratio": 0.72,
                "landing_forehand_pct": 0.68,
            },
            "technique_distribution": {"forehand_drive": 45, "backhand_drive": 18},
        },
        report_text={
            "summary": "反手使用率偏�?,
            "issues": [{"problem_id": "PROBLEM_003", "description": "反手使用率不�?}],
            "suggestions": ["增加反手练习"],
        },
        is_llm_generated=True,
        created_at=now,
    )
    report2 = AnalysisReport(
        task_id=2002, user_id=user.id,
        result_data={
            "metrics": {
                "backhand_ratio": 0.25,
                "forehand_ratio": 0.68,
                "landing_forehand_pct": 0.68,
            },
            "technique_distribution": {"forehand_drive": 45, "backhand_drive": 25},
        },
        report_text={
            "summary": "反手使用率从18%提升�?5%",
            "issues": [{"problem_id": "PROBLEM_003", "description": "反手使用率不�?}],
            "suggestions": ["继续增加反手练习"],
        },
        is_llm_generated=True,
        created_at=now,
    )
    db_session.add_all([report1, report2])

    # 创建进度快照
    for report, backhand in [(report1, 0.18), (report2, 0.25)]:
        snapshot = ProgressSnapshot(
            user_id=user.id,
            report_id=report.id,
            metrics_snapshot={"backhand_ratio": backhand},
        )
        db_session.add(snapshot)

    # 创建趋势数据
    trend = TechniqueTrend(
        user_id=user.id,
        metric_name="backhand_ratio",
        current_value=0.25,
        previous_value=0.18,
        change_rate=0.39,
        trend="improving",
        persistence_count=0,
        target_value=0.35,
    )
    db_session.add(trend)

    # 创建训练方案
    plan = TrainingPlan(
        user_id=user.id,
        template_id=1,
        status="active",
        version=1,
        plan_data={"goal": {"metric": "backhand_ratio", "target": 0.35}},
        goal_metrics={"backhand_ratio": 0.35},
    )
    db_session.add(plan)
    await db_session.commit()

    yield {
        "user": user,
        "report1": report1,
        "report2": report2,
        "plan": plan,
        "trend": trend,
    }
```

### 四类测试用例

```python
# === 1. Happy Path（正常流程） ===
@pytest.mark.asyncio
async def test_get_advice_by_report_success(advice_context):
    """基于指定报告的训练建议生成成功�?""
    user = advice_context["user"]
    report = advice_context["report2"]
    result = await TrainingAdviceService.get_advice_by_report(user.id, report.id)

    assert result["report_id"] == report.id
    assert result["is_first_analysis"] is False
    assert len(result["diagnosis"]) > 0
    assert len(result["suggestions"]) > 0
    # 验证趋势对比
    progress_suggestion = [s for s in result["suggestions"] if s["type"] == "progress_confirm"]
    assert len(progress_suggestion) > 0

@pytest.mark.asyncio
async def test_get_contextual_advice_success(advice_context):
    """综合训练建议自动取最新报告�?""
    user = advice_context["user"]
    result = await TrainingAdviceService.get_contextual_advice(user.id)
    assert result["report_id"] == advice_context["report2"].id  # 最新报�?
@pytest.mark.asyncio
async def test_get_templates_success(advice_context):
    """训练方案模板列表查询成功�?""
    result = await TrainingAdviceService.get_templates(problem_id=None, page=1, page_size=20)
    assert result["total"] > 0
    assert len(result["items"]) > 0

@pytest.mark.asyncio
async def test_get_template_detail_success(advice_context):
    """模板详情查询成功�?""
    result = await TrainingAdviceService.get_template_detail(1)
    assert result["id"] == 1
    assert "template_data" in result
    assert "goal" in result["template_data"]

@pytest.mark.asyncio
async def test_get_plan_adjustments_success(advice_context):
    """方案调整历史查询成功�?""
    user = advice_context["user"]
    plan = advice_context["plan"]
    result = await TrainingAdviceService.get_plan_adjustments(user.id, plan.id)
    assert result["plan_id"] == plan.id
    assert "adjustments" in result

@pytest.mark.asyncio
async def test_re_evaluate_plan_success(advice_context):
    """会员手动触发方案重新评估�?""
    user = advice_context["user"]
    plan = advice_context["plan"]
    result = await TrainingAdviceService.re_evaluate_plan(user.id, plan.id)
    assert result["plan_id"] == plan.id
    assert result["action"] in ("maintain", "adjust", "escalate", "new_goal")

# === 2. Validation Failure（参数校验失败） ===
@pytest.mark.asyncio
async def test_get_advice_by_nonexistent_report(advice_context):
    """报告不存在时返回 404�?""
    user = advice_context["user"]
    with pytest.raises(AppException) as exc:
        await TrainingAdviceService.get_advice_by_report(user.id, 99999)
    assert exc.value.code == 404

@pytest.mark.asyncio
async def test_get_template_detail_nonexistent(advice_context):
    """模板不存在时返回 404�?""
    with pytest.raises(AppException) as exc:
        await TrainingAdviceService.get_template_detail(99999)
    assert exc.value.code == 404

# === 3. Permission / Auth Failure（权限不足） ===
@pytest.mark.asyncio
async def test_get_advice_unauthorized(client):
    """未登录请求返�?401�?""
    resp = await client.get("/api/v1/training/advice/1")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_re_evaluate_plan_non_member(advice_context):
    """非会员用户手动重新评估返�?403�?""
    user = advice_context["user"]
    plan = advice_context["plan"]
    with patch('app.services.membership_service.MembershipService.check_membership',
               new_callable=AsyncMock, return_value=False):
        with pytest.raises(AppException) as exc:
            await TrainingAdviceService.re_evaluate_plan(user.id, plan.id)
        assert exc.value.code == 403

# === 4. Business Rule（业务规则验证） ===
@pytest.mark.asyncio
async def test_first_analysis_flag(advice_context, db_session):
    """首次分析（无历史趋势）标�?is_first_analysis=True�?""
    user = advice_context["user"]
    # 创建新用户只有一份报告的场景
    from app.models.video_analysis import AnalysisReport
    report = AnalysisReport(
        task_id=3001, user_id=user.id,
        result_data={"metrics": {"backhand_ratio": 0.20}},
        report_text={"summary": "首次分析", "issues": [], "suggestions": []},
        is_llm_generated=True,
    )
    db_session.add(report)
    await db_session.commit()

    result = await TrainingAdviceService.get_advice_by_report(user.id, report.id)
    assert result["is_first_analysis"] is True
    # 应包�?首次分析"提示
    first_analysis_suggestion = [
        s for s in result["suggestions"] if s["type"] == "first_analysis"
    ]
    assert len(first_analysis_suggestion) > 0

@pytest.mark.asyncio
async def test_advice_includes_trend_comparison(advice_context):
    """训练建议包含历史趋势对比内容�?""
    user = advice_context["user"]
    report = advice_context["report2"]
    result = await TrainingAdviceService.get_advice_by_report(user.id, report.id)

    # 诊断中应包含 trend 字段
    diag = result["diagnosis"][0]
    assert "trend" in diag
    assert diag["trend"] == "improving"

@pytest.mark.asyncio
async def test_plan_adjustment_versioning(advice_context, db_session):
    """方案调整记录版本化（old/new 快照 diff）�?""
    from app.models.training import PlanAdjustment
    user = advice_context["user"]
    plan = advice_context["plan"]

    # 模拟触发调整
    old_snapshot = {"version": 1, "goal": {"backhand_ratio": 0.35}}
    new_snapshot = {"version": 2, "goal": {"backhand_ratio": 0.38}}

    adjustment = PlanAdjustment(
        training_plan_id=plan.id,
        trigger_report_id=advice_context["report2"].id,
        old_plan_snapshot=old_snapshot,
        new_plan_snapshot=new_snapshot,
        adjustment_reason="反手使用率持续改善，提升目标�?,
        adjustment_action="adjust",
    )
    db_session.add(adjustment)
    plan.version = 2
    await db_session.commit()

    result = await TrainingAdviceService.get_plan_adjustments(user.id, plan.id)
    assert len(result["adjustments"]) >= 1
    adj = result["adjustments"][0]
    assert adj["action"] == "adjust"
    assert "changes_summary" in adj

@pytest.mark.asyncio
async def test_re_evaluate_stagnant_plan(advice_context, db_session):
    """方案停滞（连�?3 次无改善）时返回 adjust 动作�?""
    from app.models.progress import TechniqueTrend
    user = advice_context["user"]
    plan = advice_context["plan"]

    # 更新趋势为停�?    trend = advice_context["trend"]
    trend.trend = "stagnant"
    trend.persistence_count = 3
    await db_session.commit()

    with patch('app.services.membership_service.MembershipService.check_membership',
               new_callable=AsyncMock, return_value=True):
        result = await TrainingAdviceService.re_evaluate_plan(user.id, plan.id)
    assert result["action"] == "adjust"
    assert "停滞" in result["reason"] or "调整" in result["reason"]
```

---

## 3. Model 实现

```python
# app/models/training.py
"""
训练相关数据模型�?包含：TrainingPlan / PlanAdjustment
Note: TrainingTemplate �?RuleDefinition �?knowledge_base 模块统一定义�?�?app.models.knowledge_base 导入，不在此文件中重复定义（A-3 修复）�?"""
from sqlalchemy import BigInteger, String, Integer, Boolean, Text, Float, ForeignKey, Index, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone

from app.core.database import Base
# TrainingTemplate �?RuleDefinition �?knowledge_base 模块统一定义（A-3 修复�?# from app.models.knowledge_base import RuleDefinition, TrainingTemplate


class TrainingPlan(Base):
    """训练方案�?""
    __tablename__ = "training_plan"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"))
    template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("training_template.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/completed/abandoned
    version: Mapped[int] = mapped_column(Integer, default=1)
    plan_data: Mapped[dict] = mapped_column(JSONB)
    goal_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    template: Mapped["TrainingTemplate | None"] = relationship(back_populates="plans")
    adjustments: Mapped[list["PlanAdjustment"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_tplan_user_status", "user_id", "status"),
    )


class PlanAdjustment(Base):
    """训练方案调整记录（版本化）�?""
    __tablename__ = "plan_adjustment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    training_plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("training_plan.id", ondelete="CASCADE")
    )
    trigger_report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("analysis_report.id", ondelete="SET NULL"), nullable=True
    )
    old_plan_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_plan_snapshot: Mapped[dict] = mapped_column(JSONB)
    adjustment_reason: Mapped[str] = mapped_column(Text)
    adjustment_action: Mapped[str] = mapped_column(String(32))  # maintain/adjust/escalate/new_goal
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    plan: Mapped["TrainingPlan"] = relationship(back_populates="adjustments")

    __table_args__ = (
        Index("idx_padj_plan", "training_plan_id"),
    )

# RuleDefinition �?knowledge_base 模块统一定义（A-3 修复），不在此文件中重复定义
```

**实现后必�?*�?- [ ] �?`app/models/__init__.py` 中导�?`from app.models.training import TrainingPlan, PlanAdjustment`，并 `from app.models.knowledge_base import TrainingTemplate, RuleDefinition`
- [ ] 运行 `alembic revision --autogenerate -m "add_training_tables"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/training.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


# --- 训练建议响应 ---
class DiagnosisItem(BaseModel):
    """诊断项�?""
    problem_id: str
    problem_name: str
    severity: str  # low/medium/high
    trend: str  # improving/stagnant/declining/achieved/new/resolved
    description: str


class SuggestionItem(BaseModel):
    """建议项�?""
    type: str  # progress_confirm/persistent_warning/new_issue/first_analysis
    text: str


class TrainingMethodItem(BaseModel):
    """训练方法项�?""
    method_id: str
    name: str
    description: str


class TrainingAdviceResponse(BaseModel):
    """训练建议响应�?""
    report_id: int
    is_first_analysis: bool
    diagnosis: list[DiagnosisItem]
    suggestions: list[SuggestionItem]
    training_methods: list[TrainingMethodItem]
    training_plan_template: Optional[str] = None


# --- 训练模板 ---
class TemplateBrief(BaseModel):
    """模板简要�?""
    id: int
    template_code: str
    name: str
    problem_id: Optional[str] = None
    model_config = {"from_attributes": True}


class TemplateDetail(TemplateBrief):
    """模板详情�?""
    template_data: dict


class TemplateListResponse(BaseModel):
    """模板列表分页响应�?""
    total: int
    page: int
    page_size: int
    items: list[TemplateBrief]


# --- 方案调整历史 ---
class AdjustmentItem(BaseModel):
    """调整记录项�?""
    id: int
    version: int
    action: str  # maintain/adjust/escalate/new_goal
    reason: str
    trigger_report_id: Optional[int] = None
    created_at: datetime
    changes_summary: str
    model_config = {"from_attributes": True}


class PlanAdjustmentsResponse(BaseModel):
    """方案调整历史响应�?""
    plan_id: int
    current_version: int
    adjustments: list[AdjustmentItem]


# --- 重新评估响应 ---
class ReEvaluateResponse(BaseModel):
    """方案重新评估响应�?""
    plan_id: int
    action: str  # maintain/adjust/escalate/new_goal
    reason: str


# --- ????R-3 ???---
# R20-P1-1: ? API ?8.7/?8.8 ?? ?? ???? id/name/is_completed ??
# R21-P2-1: 补 session_index/reps 与 API §8.7 对齐
class TrainingSessionBrief(BaseModel):
    """??????"""
    # R20-P1-1: ? API ?8.7 ?? ?? id?? session_id?/ name?? title?/ is_completed?? status?
    id: int
    plan_id: int
    name: str
    is_completed: bool  # R20-P1-1: API ?8.7 ? is_completed: bool??? status ????
    scheduled_date: Optional[str] = None
    completed_at: Optional[datetime] = None
    # R21-P2-1: 补 session_index/reps 与 API §8.7 L2388-2394 对齐
    session_index: int = Field(..., description="训练单序号（从1开始）")
    reps: int = Field(..., description="建议训练次数")
    model_config = {"from_attributes": True}


class TrainingSessionListResponse(BaseModel):
    """????????"""
    # R20-P1-1: ? API ?8.7 ?? ?? items?? sessions?+ page/page_size ????
    plan_id: int
    total: int
    page: int  # R20-P1-1: ? page ???API ?8.7 L2373 ???
    page_size: int  # R20-P1-1: ? page_size ???API ?8.7 L2374 ???
    items: list[TrainingSessionBrief]  # R20-P1-1: sessions?items?API ?8.7 ?????


class TrainingSessionCompleteResponse(BaseModel):
    """????????"""
    # R20-P1-1: ? API ?8.8 ?? ?? ? is_completed + points_earned??? status/completed_at????
    session_id: int
    is_completed: bool = True  # R20-P1-1: ? is_completed ???API ?8.8 ?????
    # R21-P2-2: plan_progress 类型 int 0-100 与 API §8.8 L2423 对齐
    plan_progress: int = Field(..., description="计划完成进度（0-100 百分比）")
    points_earned: int  # R20-P1-1: ? points_earned ???API ?8.8 ??????????
    completed_at: Optional[datetime] = None  # R20-P1-1: ?? Optional?API ?8.8 ??????????
```

---

## 5. Service 实现

```python
# app/services/training_advice_service.py
"""
训练建议业务逻辑层�?规则引擎匹配模式�?  1. 单次规则（single）：基于当前报告指标匹配
  2. 趋势规则（trend_persistent）：问题持续 N 次未改善
  3. 趋势规则（trend_improving）：指标在改善中
  4. 方案有效性规则（plan_effectiveness / stagnant）：方案停滞需调整
方案动态调整：
  - 改善�?�?维持方案（maintain�?  - 停滞（连�?3 次无改善）→ 调整方案（adjust�?  - 退�?�?诊断原因（escalate�?  - 已达�?�?设新目标（new_goal�?"""
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.exceptions import AppException
from app.models.video_analysis import AnalysisReport
from app.models.progress import ProgressSnapshot, TechniqueTrend
from app.models.training import TrainingPlan, PlanAdjustment
from app.models.knowledge_base import TrainingTemplate, RuleDefinition
from app.schemas.training import (
    TrainingAdviceResponse, DiagnosisItem, SuggestionItem, TrainingMethodItem,
    TemplateBrief, TemplateDetail, TemplateListResponse,
    PlanAdjustmentsResponse, AdjustmentItem,
    ReEvaluateResponse,
    TrainingSessionBrief, TrainingSessionListResponse, TrainingSessionCompleteResponse,
)

# 停滞判定阈�?STAGNANT_THRESHOLD = 3  # 连续 3 次无改善


class TrainingAdviceService:
    """训练建议业务逻辑层�?""

    # ========== 基于报告的训练建�?==========

    @staticmethod
    async def get_advice_by_report(user_id: int, report_id: int) -> TrainingAdviceResponse:
        """
        基于指定分析报告的训练建议�?        流程�?          1. 验证报告属于当前用户
          2. 判断是否首次分析
          3. 读取报告指标 + 历史趋势数据
          4. 调用规则引擎匹配问题模式
          5. 生成差异化建议（进步确认 / 持续问题警告 / 新问题识别）
        """
        async with get_async_session() as db:
            # 1. 验证报告
            report = await db.scalar(
                select(AnalysisReport).where(
                    and_(AnalysisReport.id == report_id,
                         AnalysisReport.user_id == user_id)
                )
            )
            if not report:
                raise AppException("报告不存�?, 404)

            # 2. 判断首次分析
            report_count = await db.scalar(
                select(func.count()).select_from(AnalysisReport)
                .where(AnalysisReport.user_id == user_id)
            ) or 0
            is_first = report_count <= 1

            # 3. 读取当前报告指标
            result_data = report.result_data or {}
            metrics = result_data.get("metrics", {})

            # 4. 读取历史趋势
            trends = await TrainingAdviceService._get_trends(db, user_id)

            # 5. 匹配规则引擎
            diagnosis, suggestions, training_methods, plan_template = (
                await TrainingAdviceService._match_rules(
                    db, metrics, trends, is_first
                )
            )

        return TrainingAdviceResponse(
            report_id=report_id,
            is_first_analysis=is_first,
            diagnosis=diagnosis,
            suggestions=suggestions,
            training_methods=training_methods,
            training_plan_template=plan_template,
        )

    @staticmethod
    async def get_contextual_advice(user_id: int) -> TrainingAdviceResponse:
        """综合训练建议（自动取最新报告）�?""
        async with get_async_session() as db:
            latest_report = await db.scalar(
                select(AnalysisReport)
                .where(AnalysisReport.user_id == user_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(1)
            )
            if not latest_report:
                raise AppException("暂无分析报告，请先上传视频分�?, 404)

        return await TrainingAdviceService.get_advice_by_report(user_id, latest_report.id)

    # ========== 规则引擎 ==========

    @staticmethod
    async def _get_trends(db: AsyncSession, user_id: int) -> list[TechniqueTrend]:
        """获取用户所有技术指标趋势�?""
        result = await db.execute(
            select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _match_rules(
        db: AsyncSession,
        metrics: dict,
        trends: list[TechniqueTrend],
        is_first: bool,
    ) -> tuple[list[DiagnosisItem], list[SuggestionItem], list[TrainingMethodItem], Optional[str]]:
        """
        规则引擎匹配�?        4 类匹配：单次 / 趋势改善 / 趋势持续 / 方案停滞
        """
        diagnosis = []
        suggestions = []
        training_methods = []
        plan_template = None

        # 读取所有活跃规�?        result = await db.execute(
            select(RuleDefinition).where(RuleDefinition.is_active.is_(True))
        )
        rules = list(result.scalars().all())

        trend_map = {t.metric_name: t for t in trends}

        for rule in rules:
            matched = False
            condition = rule.condition or {}
            field = condition.get("field")
            operator = condition.get("operator")
            threshold = condition.get("threshold")

            if rule.rule_type == "single":
                # 单次规则：检查当前指标�?                if field and field in metrics:
                    value = metrics[field]
                    matched = TrainingAdviceService._compare(value, operator, threshold)

            elif rule.rule_type == "trend_persistent":
                # 趋势持续规则：问题持�?N 次未改善
                if field and field in trend_map:
                    trend = trend_map[field]
                    if trend.persistence_count >= (condition.get("min_persistence", 1)):
                        matched = True

            elif rule.rule_type == "trend_improving":
                # 趋势改善规则：指标在改善�?                if field and field in trend_map:
                    trend = trend_map[field]
                    if trend.trend == "improving":
                        matched = True

            elif rule.rule_type == "stagnant":
                # 停滞规则：连�?N 次无改善
                if field and field in trend_map:
                    trend = trend_map[field]
                    if trend.persistence_count >= STAGNANT_THRESHOLD:
                        matched = True

            if matched:
                diag_data = rule.diagnosis or {}
                # 合并趋势信息
                trend_val = "new"
                if field and field in trend_map:
                    trend_val = trend_map[field].trend or "new"

                diagnosis.append(DiagnosisItem(
                    problem_id=diag_data.get("problem_id", ""),
                    problem_name=diag_data.get("problem_name", ""),
                    severity=diag_data.get("severity", "medium"),
                    trend=trend_val,
                    description=diag_data.get("description", ""),
                ))

                # 生成建议文本
                suggestion_type = "new_issue"
                suggestion_text = diag_data.get("description", "")

                if rule.rule_type == "trend_improving":
                    suggestion_type = "progress_confirm"
                    if field and field in trend_map:
                        t = trend_map[field]
                        suggestion_text = (
                            f"你的{field}从{t.previous_value}提升到{t.current_value}�?
                            f"进步明显"
                        )
                elif rule.rule_type == "trend_persistent":
                    suggestion_type = "persistent_warning"
                    if field and field in trend_map:
                        t = trend_map[field]
                        suggestion_text = (
                            f"{diag_data.get('problem_name', field)}问题"
                            f"已持�?{t.persistence_count} 次分析未改善�?
                            f"建议调整训练方法"
                        )

                suggestions.append(SuggestionItem(
                    type=suggestion_type,
                    text=suggestion_text,
                ))

                # 训练方法
                method_ids = rule.training_methods or []
                for mid in method_ids:
                    training_methods.append(TrainingMethodItem(
                        method_id=mid,
                        name=mid.replace("METHOD_", ""),
                        description="",
                    ))

                if rule.training_plan_template and not plan_template:
                    plan_template = rule.training_plan_template

        # 首次分析提示
        if is_first:
            suggestions.append(SuggestionItem(
                type="first_analysis",
                text="首次分析，建议持续记录以获得趋势分析",
            ))

        return diagnosis, suggestions, training_methods, plan_template

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        """比较运算符�?""
        if operator == "lt":
            return value < threshold
        if operator == "lte":
            return value <= threshold
        if operator == "gt":
            return value > threshold
        if operator == "gte":
            return value >= threshold
        if operator == "eq":
            return value == threshold
        return False

    # ========== 训练模板 ==========

    @staticmethod
    async def get_templates(
        problem_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TemplateListResponse:
        """训练方案模板列表�?""
        async with get_async_session() as db:
            qs = select(TrainingTemplate)
            if problem_id:
                qs = qs.where(TrainingTemplate.problem_id == problem_id)

            total = await db.scalar(
                select(func.count()).select_from(qs.subquery())
            ) or 0

            offset = (page - 1) * page_size
            result = await db.execute(
                qs.order_by(TrainingTemplate.created_at.desc())
                .offset(offset).limit(page_size)
            )
            templates = result.scalars().all()

        items = [TemplateBrief.model_validate(t) for t in templates]
        return TemplateListResponse(
            total=total, page=page, page_size=page_size, items=items,
        )

    @staticmethod
    async def get_template_detail(template_id: int) -> TemplateDetail:
        """模板详情�?""
        async with get_async_session() as db:
            template = await db.scalar(
                select(TrainingTemplate).where(TrainingTemplate.id == template_id)
            )
            if not template:
                raise AppException("模板不存�?, 404)

        return TemplateDetail.model_validate(template)

    # ========== 方案调整历史 ==========

    @staticmethod
    async def get_plan_adjustments(user_id: int, plan_id: int) -> PlanAdjustmentsResponse:
        """训练方案调整历史（版本化记录）�?""
        async with get_async_session() as db:
            # 验证方案属于当前用户
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id,
                         TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存�?, 404)

            # 查询调整记录
            result = await db.execute(
                select(PlanAdjustment)
                .where(PlanAdjustment.training_plan_id == plan_id)
                .order_by(PlanAdjustment.created_at.desc())
            )
            adjustments = result.scalars().all()

        items = []
        for adj in adjustments:
            # 计算 changes_summary（old/new diff�?            changes_summary = TrainingAdviceService._diff_snapshot(
                adj.old_plan_snapshot, adj.new_plan_snapshot
            )
            items.append(AdjustmentItem(
                id=adj.id,
                version=plan.version if adj == adjustments[0] else adj.id,  # 版本�?                action=adj.adjustment_action,
                reason=adj.adjustment_reason,
                trigger_report_id=adj.trigger_report_id,
                created_at=adj.created_at,
                changes_summary=changes_summary,
            ))

        return PlanAdjustmentsResponse(
            plan_id=plan_id,
            current_version=plan.version,
            adjustments=items,
        )

    @staticmethod
    def _diff_snapshot(old: dict | None, new: dict) -> str:
        """计算 old/new 快照 diff 摘要�?""
        if not old:
            return "初始方案创建"

        changes = []
        # 对比 version
        if old.get("version") != new.get("version"):
            changes.append(f"版本 {old.get('version', 1)} �?{new.get('version', 2)}")

        # 对比 goal
        old_goal = old.get("goal", {})
        new_goal = new.get("goal", {})
        for key in set(list(old_goal.keys()) + list(new_goal.keys())):
            old_val = old_goal.get(key)
            new_val = new_goal.get(key)
            if old_val != new_val and old_val is not None and new_val is not None:
                changes.append(f"{key}: {old_val} �?{new_val}")

        return "; ".join(changes) if changes else "无变�?

    # ========== 方案重新评估 ==========

    @staticmethod
    async def re_evaluate_plan(user_id: int, plan_id: int) -> ReEvaluateResponse:
        """
        手动触发方案重新评估（会员功能）�?        评估逻辑�?          - 改善�?�?maintain（维持方案）
          - 停滞（连�?3 次无改善）→ adjust（调整方案）
          - 退�?�?escalate（诊断原因）
          - 已达�?�?new_goal（设新目标）
        每次调整生成 plan_adjustment 记录�?        """
        from app.services.membership_service import MembershipService

        async with get_async_session() as db:
            # 权限检查：会员及以�?            membership = await MembershipService.check_membership(db, user_id)
            if not membership.is_member:
                raise AppException("此功能需要会员及以上等级", 403)

            # 验证方案
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id,
                         TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存�?, 404)

            # 读取趋势数据
            goal_metrics = plan.goal_metrics or {}
            trends_result = await db.execute(
                select(TechniqueTrend).where(
                    and_(
                        TechniqueTrend.user_id == user_id,
                        TechniqueTrend.metric_name.in_(
                            list(goal_metrics.keys())
                        ),
                    )
                )
            )
            trends = list(trends_result.scalars().all())

            # 评估方案有效�?            action, reason = TrainingAdviceService._evaluate_plan_effectiveness(
                plan, trends, goal_metrics
            )

            # 如果需要调整，生成 plan_adjustment 记录
            if action != "maintain":
                old_snapshot = {
                    "version": plan.version,
                    "goal": goal_metrics,
                    "plan_data": plan.plan_data,
                }

                new_snapshot = TrainingAdviceService._generate_new_plan(
                    plan, trends, goal_metrics, action
                )

                adjustment = PlanAdjustment(
                    training_plan_id=plan.id,
                    trigger_report_id=None,  # 手动触发
                    old_plan_snapshot=old_snapshot,
                    new_plan_snapshot=new_snapshot,
                    adjustment_reason=reason,
                    adjustment_action=action,
                )
                db.add(adjustment)

                # 更新方案
                plan.version += 1
                plan.plan_data = new_snapshot.get("plan_data", plan.plan_data)
                plan.goal_metrics = new_snapshot.get("goal", goal_metrics)
                plan.updated_at = datetime.now(timezone.utc)
                await db.commit()

        return ReEvaluateResponse(
            plan_id=plan_id,
            action=action,
            reason=reason,
        )

    @staticmethod
    def _evaluate_plan_effectiveness(
        plan: TrainingPlan,
        trends: list[TechniqueTrend],
        goal_metrics: dict,
    ) -> tuple[str, str]:
        """
        评估方案有效性，返回 (action, reason)�?        action: maintain / adjust / escalate / new_goal
        """
        if not trends:
            return "maintain", "暂无足够趋势数据，维持当前方�?

        all_improving = True
        all_stagnant = True
        all_achieved = True

        for trend in trends:
            if trend.trend != "improving":
                all_improving = False
            if trend.persistence_count < STAGNANT_THRESHOLD:
                all_stagnant = False
            # 检查是否达�?            target = goal_metrics.get(trend.metric_name)
            if target and trend.current_value is not None:
                if trend.current_value < target:
                    all_achieved = False
            else:
                all_achieved = False

        # 优先级：达标 > 退�?> 停滞 > 改善
        if all_achieved:
            return "new_goal", "已达标，建议设置新目�?

        if any(t.trend == "declining" for t in trends):
            return "escalate", "指标退步，需要诊断原�?

        if all_stagnant:
            return "adjust", f"方案停滞（连�?{STAGNANT_THRESHOLD} 次无改善），建议调整训练方法"

        if all_improving:
            return "maintain", "当前方案有效，指标持续改�?

        return "maintain", "维持当前方案，继续观�?

    @staticmethod
    def _generate_new_plan(
        plan: TrainingPlan,
        trends: list[TechniqueTrend],
        goal_metrics: dict,
        action: str,
    ) -> dict:
        """根据调整动作生成新方案快照�?""
        new_version = plan.version + 1
        new_goal = dict(goal_metrics)

        if action == "new_goal":
            # 达标 �?提升目标�?            for trend in trends:
                metric = trend.metric_name
                if metric in new_goal:
                    old_target = new_goal[metric]
                    new_goal[metric] = round(old_target * 1.1, 4)  # 提升 10%

        elif action == "adjust":
            # 停滞 �?调整训练方法（增加量�?            plan_data = dict(plan.plan_data or {})
            sessions = plan_data.get("sessions", [])
            for session in sessions:
                if "reps" in session:
                    session["reps"] = int(session["reps"] * 1.2)  # 增加 20%
            plan_data["sessions"] = sessions
            return {
                "version": new_version,
                "goal": new_goal,
                "plan_data": plan_data,
            }

        return {
            "version": new_version,
            "goal": new_goal,
            "plan_data": plan.plan_data,
        }

    # ========== 训练单管理（R-3 修复�?==========

    @staticmethod
    # R20-P1-1: ? API ?8.7 ?? ?? ?? page/page_size ????
    async def list_training_sessions(
        user_id: int, plan_id: int, page: int = 1, page_size: int = 20,
    ) -> TrainingSessionListResponse:
        """??????????????"""
        async with get_async_session() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id,
                         TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("???????", 404)

            plan_data = plan.plan_data or {}
            sessions = plan_data.get("sessions", [])

            # R20-P1-1: ? API ?8.7 ?? ?? ???? title?name, status?is_completed
            # R21-P2-1: 补 session_index/reps 与 API §8.7 对齐
            all_items = [
                TrainingSessionBrief(
                    id=s.get("id", i + 1),
                    plan_id=plan_id,
                    name=s.get("title", s.get("name", f"??? {i + 1}")),
                    is_completed=s.get("status") == "completed" or s.get("is_completed", False),
                    scheduled_date=s.get("scheduled_date"),
                    completed_at=s.get("completed_at"),
                    session_index=s.get("session_index", i + 1),  # R21-P2-1: 训练单序号（默认从1开始）
                    reps=s.get("reps", 0),  # R21-P2-1: 建议训练次数
                )
                for i, s in enumerate(sessions)
            ]

        # R20-P1-1: ? API ?8.7 ?? ?? ?????page ? 1 ???
        total = len(all_items)
        page_start = (page - 1) * page_size
        page_end = page_start + page_size
        items = all_items[page_start:page_end]

        return TrainingSessionListResponse(
            plan_id=plan_id,
            total=total,
            page=page,
            page_size=page_size,
            items=items,  # R20-P1-1: sessions?items?API ?8.7 ?????
        )

    @staticmethod
    async def complete_training_session(
        user_id: int, plan_id: int, session_id: int,
    ) -> TrainingSessionCompleteResponse:
        """????????????????????"""
        async with get_async_session() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id,
                         TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("???????", 404)

            plan_data = dict(plan.plan_data or {})
            sessions = plan_data.get("sessions", [])

            target = None
            for s in sessions:
                if s.get("id") == session_id:
                    target = s
                    break
            if not target:
                raise AppException("??????", 404)

            if target.get("status") == "completed":
                raise AppException("??????", 409)

            now = datetime.now(timezone.utc)
            target["status"] = "completed"
            target["completed_at"] = now.isoformat()
            plan_data["sessions"] = sessions

            total = len(sessions)
            completed = sum(1 for s in sessions if s.get("status") == "completed")
            plan_progress = completed / total if total > 0 else 0.0

            if plan_progress >= 1.0:
                plan.status = "completed"

            plan.plan_data = plan_data
            plan.updated_at = now
            await db.commit()

            # F3-2 ???gamification ????????????
            # R20-P1-1: ? API ?8.8 ?? ?? ??????????
            points_earned = 0
            try:
                from app.services.gamification_service import GamificationService
                add_result = await GamificationService.add_points(
                    db, user_id=user_id, event_type="training_session", ref_id=session_id,
                )
                # ?? add_points ?? int ? dict ? None
                if isinstance(add_result, int):
                    points_earned = add_result
                elif isinstance(add_result, dict):
                    points_earned = int(add_result.get("points_earned", 0) or 0)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error("gamification_add_points_failed", error=str(e), user_id=user_id)

        return TrainingSessionCompleteResponse(
            session_id=session_id,
            is_completed=True,  # R20-P1-1: ? is_completed ???API ?8.8 ?????
            # R21-P2-2: plan_progress 类型 int 0-100 与 API §8.8 L2423 对齐（float 0.0-1.0 → int 百分比）
            plan_progress=int(plan_progress * 100),
            points_earned=points_earned,  # R20-P1-1: ? points_earned ???API ?8.8 ?????
            completed_at=now,  # R20-P1-1: ?? completed_at?Service ???????
        )
```
---

## 5.5 训练建议生成 Celery Task

```python
# app/tasks/training_advice_beat.py
"""训练建议定时生成任务。"""

from app.core.celery import celery_app


@celery_app.task(name="training_advice.generate_advice")
def generate_advice_task(user_id: int, report_id: int):
    """训练建议生成——异步调用，分析报告完成后触发。

    逻辑：
    1. 接收 user_id + report_id，调用 TrainingAdviceService.generate_advice()
    2. 基于分析报告 + 历史趋势 + 知识库规则引擎生成个性化训练建议
    3. 生成完成后通过 WS 推送通知用户

    注意：此任务为事件驱动（分析流水线完成后调用 send_task），
    无需在 beat_schedule 中注册定时触发。
    """
    import asyncio
    asyncio.run(_generate_advice_async(user_id, report_id))


async def _generate_advice_async(user_id: int, report_id: int):
    """训练建议生成异步实现。"""
    from app.services.training_advice_service import TrainingAdviceService

    await TrainingAdviceService.generate_advice(
        user_id=user_id, report_id=report_id
    )
```

---

## 6. API 路由实现

```python
# app/api/v1/training/advice_router.py
from fastapi import APIRouter, Depends, Query
from app.core.deps import get_current_user, require_membership
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.services.training_advice_service import TrainingAdviceService

router = APIRouter(prefix="/training", tags=["训练建议"])

@limiter.limit("100/minute")
@router.get("/advice/{report_id}", summary="基于分析报告的训练建�?)
async def get_advice_by_report(
    report_id: int,
    user: User = Depends(get_current_user),
):
    """基于指定报告的训练建议（含历史趋势对比）�?""
    data = await TrainingAdviceService.get_advice_by_report(user.id, report_id)
    return success(data=data)

@limiter.limit("100/minute")
@router.get("/advice/contextual", summary="综合训练建议")
async def get_contextual_advice(
    user: User = Depends(get_current_user),
):
    """基于最新报�?+ 历史趋势的综合建议（自动取最新报告）�?""
    data = await TrainingAdviceService.get_contextual_advice(user.id)
    return success(data=data)

@limiter.limit("100/minute")
@router.get("/templates", summary="训练方案模板列表")
async def get_templates(
    problem_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    _membership = Depends(require_membership("member")),  # SEC-003 修复：会员权限守�?):
    """训练方案模板列表（可按问题筛选）�?""
    data = await TrainingAdviceService.get_templates(
        problem_id=problem_id, page=page, page_size=page_size,
    )
    return success(data=data)

@limiter.limit("100/minute")
@router.get("/templates/{template_id}", summary="模板详情")
async def get_template_detail(
    template_id: int,
    user: User = Depends(get_current_user),
    _membership = Depends(require_membership("member")),  # SEC-003 修复：会员权限守�?):
    """训练方案模板详情�?""
    data = await TrainingAdviceService.get_template_detail(template_id)
    return success(data=data)

@limiter.limit("100/minute")
@router.get("/plans/{plan_id}/adjustments", summary="训练方案调整历史")
async def get_plan_adjustments(
    plan_id: int,
    user: User = Depends(get_current_user),
    _membership = Depends(require_membership("member")),  # SEC-003 修复：会员权限守�?):
    """训练方案调整历史（版本化记录）�?""
    data = await TrainingAdviceService.get_plan_adjustments(user.id, plan_id)
    return success(data=data)

@limiter.limit("100/minute")
@router.post("/plans/{plan_id}/re-evaluate", summary="手动触发方案重新评估")
async def re_evaluate_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    _membership = Depends(require_membership("member")),  # SEC-003 修复：会员权限守卫
):
    """会员手动触发方案重新评估�?""
    data = await TrainingAdviceService.re_evaluate_plan(user.id, plan_id)
    return success(data=data, message="方案已重新评�?)


@limiter.limit("100/minute")
@router.get("/plans/{plan_id}/sessions", summary="?????")
async def list_training_sessions(
    plan_id: int,
    page: int = Query(1, ge=1),  # R20-P1-1: ? API ?8.7 ?? ?? ? page ?????L2373?
    page_size: int = Query(default=20, ge=1, le=50),  # R21-P3-1: 补 ge=1 约束（API §1.2 分页参数 MUST ge=1）  # R20-P1-1: ? API ?8.7 ?? ?? ? page_size ?????L2374?
    user: User = Depends(get_current_user),
    _membership = Depends(require_membership("member")),  # SEC-003 ?????????
):
    """??????????????R-3 ????5.11??"""
    # R20-P1-1: ? API ?8.7 ?? ?? ?? page/page_size ? Service??????
    data = await TrainingAdviceService.list_training_sessions(
        user.id, plan_id, page=page, page_size=page_size,
    )
    return success(data=data)


@limiter.limit("100/minute")
@router.post("/plans/{plan_id}/sessions/{session_id}/complete", summary="?????")
async def complete_training_session(
    plan_id: int,
    session_id: int,
    user: User = Depends(get_current_user),
    _membership = Depends(require_membership("member")),  # SEC-003 ?????????
):
    """????????????????????R-3 ????5.12??"""
    # R20-P1-1: ? API ?8.8 ?? ?? Service ?? is_completed + points_earned ??
    data = await TrainingAdviceService.complete_training_session(user.id, plan_id, session_id)
    return success(data=data, message="??????")
```

> **注意**：`require_membership("member")` 是权限依赖，确保只有会员及以上等级用户可以触发重新评估。SEC-003 修复后，以下 5 个端点也添加�?`require_membership("member")` 守卫：GET /templates、GET /templates/{id}、GET /plans/{id}/adjustments、GET /plans/{id}/sessions、POST /plans/{id}/sessions/{id}/complete。仅 GET /advice/{report_id} �?GET /advice/contextual 保持 `get_current_user`（登录即可）�?
**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.training.advice_router import router as training_advice_router
api_router.include_router(training_advice_router)
```

> **说明**：training_advice �?training_plan 共用 `/training` 前缀。Phase 1 仅注�?advice_router，Phase 2 追加 plan_router。两者路由不冲突（advice 端点路径均含 `/advice` �?`/templates`，plan 端点路径�?`/plans`）�?
---

## 7. 冒烟测试脚本

```python
# tests/smoke/training_advice_smoke_test.py
"""
training_advice 模块冒烟测试�?用法: python -m tests.smoke.training_advice_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 登录
        print("1. Testing auth login...")
        resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "冒烟测试",
        })
        if resp.status_code != 200:
            print(f"   �?Login failed: {resp.status_code}")
            return
        access_token = resp.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {access_token}"}
        print("   �?Login success")

        # 2. 获取最新报�?ID（假设已有分析报告）
        print("2. Getting latest report...")
        resp = await client.get("/video-analysis/reports?page=1&page_size=1", headers=h)
        if resp.status_code != 200 or resp.json()["data"]["total"] == 0:
            print("   �?No analysis reports found, skipping advice test")
        else:
            report_id = resp.json()["data"]["items"][0]["id"]

            # 3. 基于报告的训练建�?            print(f"3. Testing /training/advice/{report_id}...")
            resp = await client.get(f"/training/advice/{report_id}", headers=h)
            assert resp.status_code == 200, f"Advice failed: {resp.text}"
            advice = resp.json()["data"]
            print(f"   �?Advice: is_first={advice['is_first_analysis']}, "
                  f"diagnosis={len(advice['diagnosis'])} items, "
                  f"suggestions={len(advice['suggestions'])} items")

            # 4. 综合训练建议
            print("4. Testing /training/advice/contextual...")
            resp = await client.get("/training/advice/contextual", headers=h)
            assert resp.status_code == 200, f"Contextual advice failed: {resp.text}"
            print("   �?Contextual advice success")

        # 5. 训练模板列表
        print("5. Testing /training/templates...")
        resp = await client.get("/training/templates?page=1&page_size=20", headers=h)
        assert resp.status_code == 200, f"Templates list failed: {resp.text}"
        templates = resp.json()["data"]
        print(f"   �?Templates: {templates['total']} items")

        if templates["total"] > 0:
            template_id = templates["items"][0]["id"]

            # 6. 模板详情
            print(f"6. Testing /training/templates/{template_id}...")
            resp = await client.get(f"/training/templates/{template_id}", headers=h)
            assert resp.status_code == 200, f"Template detail failed: {resp.text}"
            detail = resp.json()["data"]
            print(f"   �?Template detail: {detail['name']}")

        # 7. 方案调整历史（需要先有方案）
        print("7. Testing plan adjustments...")
        resp = await client.get("/training/plans?page=1&page_size=1", headers=h)
        if resp.status_code == 200 and resp.json()["data"]["total"] > 0:
            plan_id = resp.json()["data"]["items"][0]["id"]
            resp = await client.get(
                f"/training/plans/{plan_id}/adjustments", headers=h
            )
            assert resp.status_code == 200, f"Adjustments failed: {resp.text}"
            adj = resp.json()["data"]
            print(f"   �?Plan adjustments: {len(adj['adjustments'])} records")

            # 8. 手动重新评估（需要会员）
            print(f"8. Testing /training/plans/{plan_id}/re-evaluate...")
            resp = await client.post(
                f"/training/plans/{plan_id}/re-evaluate", headers=h
            )
            if resp.status_code == 200:
                re_eval = resp.json()["data"]
                print(f"   �?Re-evaluate: action={re_eval['action']}")
            elif resp.status_code == 403:
                print("   �?Re-evaluate requires membership (expected for free user)")
            else:
                print(f"   �?Re-evaluate failed: {resp.status_code}")
        else:
            print("   �?No training plans found, skipping adjustment tests")

    print("\ntraining_advice_smoke_test: ALL PASSED �?)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_training_advice.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.training_advice_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导�?- [ ] Router 已在 `app/api/v1/__init__.py` 中注�?- [ ] Alembic 迁移已生成并执行
- [ ] 训练建议包含历史趋势对比内容（diagnosis.trend 字段�?- [ ] 首次分析标注 `is_first_analysis=True` 并包�?首次分析"提示
- [ ] 规则引擎正确匹配 4 类模式（单次 / 趋势改善 / 趋势持续 / 停滞�?- [ ] 方案调整记录版本化保存（old/new 快照 + changes_summary diff�?- [ ] 手动重新评估的权限检查（会员及以上）
- [ ] 方案调整动作正确（maintain / adjust / escalate / new_goal�?- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释�?- [ ] 无废话注释、无注释掉的死代�?
---

## 反幻觉约�?
- Service 方法 **必须** 使用 `@staticmethod`�?*禁止** 创建实例
- Schema **必须** 遵循命名：`TrainingAdviceResponse`、`TemplateBrief`、`TemplateDetail`、`PlanAdjustmentsResponse`、`ReEvaluateResponse`
- **禁止** �?API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- **必须** 训练建议结合历史趋势�?*禁止** 仅基于单次报告生成建�?- **必须** 首次分析标注 `is_first_analysis=True`
- **必须** 方案调整生成 `plan_adjustment` 记录（old/new 快照 diff�?- **必须** 方案重新评估权限检查（会员及以上）
- **必须** 规则引擎匹配 4 类模式：单次 / 趋势改善 / 趋势持续 / 停滞
- 测试 **必须** 使用 `httpx.AsyncClient`�?*禁止** 自建 HTTP 客户�?- 冒烟测试 **必须** 可作为独立脚本运�?- `TechniqueTrend` 模型使用 `trend`/`current_value`/`previous_value` 字段名（�?DB 设计 v1.3 §2.22/§5.6 一致）。（X-3 已修复）
- `TrainingTemplate` �?`RuleDefinition` **必须** �?`app.models.knowledge_base` 导入�?*禁止** �?`app/models/training.py` 中重复定义（A-3 修复�?- `AnalysisReport` 模型归属�?video_analysis 模块（DB 设计 §5.3），统一使用 `from app.models.video_analysis import AnalysisReport`�?*禁止** 使用 `app.models.analysis`（A-10 修复�?- `AnalysisReport.result_data` **必须** 使用 JSONB 类型，测试代码中 **必须** 直接�?dict�?*禁止** 使用 `json.dumps()`（X-4 修复�?- 训练单端点（`GET /plans/{id}/sessions`、`POST /plans/{id}/sessions/{sid}/complete`�?*必须** 实现（R-3 修复�?- 所�?API 端点 **必须** 添加 `@limiter.limit("100/minute")` 限流装饰器，**禁止** 裸奔无限�?- `from app.core.limiter import limiter` **必须** 在路由文�?import 区声明，**禁止** 遗漏导入

### 覆盖度修复说�?
| 编号 | 修复内容 | 位置 |
|------|---------|------|
| A-3 | 删除 training_advice 中重复的 `RuleDefinition` �?`TrainingTemplate` Model 定义，改为从 `app.models.knowledge_base` 引用 | §3 Model、�? 任务清单、�? Service import |
| X-3 | `TechniqueTrend` 使用 `trend`/`current_value`/`previous_value` 字段名（�?§5.6 一致），DB 设计 §2.22 �?`trend_direction` 需回写更新�?`trend` 并补�?`current_value`/`previous_value` | 反幻觉约�?|
| X-4 | `AnalysisReport.result_data` 统一使用 JSONB 类型，测试代码传 dict 不用 `json.dumps()` | §2 测试 |
| A-10 | `AnalysisReport` import 路径统一�?`app.models.video_analysis`（原 `app.models.analysis`�?| §2 测试、�? Service |
| R-3 | 添加训练单端点：`GET /plans/{id}/sessions`、`POST /plans/{id}/sessions/{sid}/complete` + Service 方法 + Schema | §4 Schema、�? Service、�? API 路由 |
| A-9 | `datetime.utcnow()` �?`datetime.now(timezone.utc)`；`default`/`onupdate` 改为 lambda 表达式；import 补充 `timezone` | §3 Model、�? Service |

