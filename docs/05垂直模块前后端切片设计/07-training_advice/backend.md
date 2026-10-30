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
| 4 | 实现 Service | `app/services/training_service.py` | #1,#3 | �?|
| 5 | 实现 API 路由 | `app/api/v1/training/router.py` | #4 | �?|
| 6 | 注册 Router | `app/api/v1/__init__.py` | #5 | �?|
| 7 | Alembic 迁移 | `alembic revision --autogenerate` + `upgrade` | #1 | �?|
| 8 | 编写单元测试 | `tests/unit/test_training.py` | #4 | �?|
| 9 | 编写冒烟测试 | `tests/smoke/training_advice_smoke_test.py` | #5 | �?|

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_training.py
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

> **R13-P3 文档同步（2026-10-29）**：本节原样例为初版设计稿（`training_advice_service.py` + `get_async_session()` + Service 内联规则引擎 `_match_rules`/`_compare` + `AppException` 无业务码 + 返回 Pydantic 响应模型），滞后于 R4-R7/R12 修复后的实现。以下代码已按实际实现 `app/services/training_service.py` 原样回写，关键契约差异：
> - 规则引擎委托 `KnowledgeBaseService.match_rules(db, ctx)`（ctx = {metrics, trends, current_plan}），规则类型经 condition 的 `aggregation` 键判定（R2-KB-1），建议文本由知识库 `suggestion_template` 渲染；
> - 业务错误码：40412（报告不存在/暂无分析报告）、40420（训练方案不存在）、40421（模板不存在，路由层抛出）、40422（训练单不存在）、40902（训练单已完成）、40301（非会员重新评估）；
> - 建议 type 按规则类型判定（trend_improving→progress_confirm / trend_persistent→persistent_warning / 其余→new_issue），`first_analysis` 仅作为追加提示、不污染规则建议类型（R12-Training-B2）；
> - `_evaluate_plan_effectiveness` 达标判定方向感知（`METRIC_DEFINITIONS` direction），stagnant 仅按 persistence_count ≥ 3 判定（R5-Prog-4）；
> - `_generate_new_plan`：new_goal 方向感知（up×1.1 / down×0.9，R7-Train-1）；adjust 训练单 reps×1.2；escalate 仅诊断、不改写训练内容（R12-Training-B3）；深拷贝隔离 old/new 快照（R12-Training-D4）；
> - `get_plan_adjustments` 非最新记录 version 取 `new_plan_snapshot.version`（R5-Train-3）；`_diff_snapshot` 含训练单数与 reps 变化（R5-Train-5）；
> - Service 返回 dict（`app/schemas/training.py` 的 Schema 作为响应结构文档，路由以 `success(data=...)` 包装）；
> - `complete_training_session` 深拷贝 + `flag_modified` 强制 JSONB 变更落库、训练单按 id/session_index 双键查找（R5-Train-4）、积分失败仅告警不阻塞。

```python
"""
app/services/training_service.py - 训练建议业务逻辑层

依据：切片 07-training_advice/backend.md 4
功能：基于报告的训练建议 + 综合建议 + 模板查询 + 方案调整 + 训练单管理
"""

import copy
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.models.knowledge_base import RuleDefinition, TrainingTemplate
from app.models.progress import TechniqueTrend
from app.models.training import PlanAdjustment, TrainingPlan
from app.models.video_analysis import AnalysisReport
from app.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)

STAGNANT_THRESHOLD = 3


class TrainingAdviceService:
    """训练建议业务逻辑层"""

    @staticmethod
    async def get_advice_by_report(user_id: int, report_id: int) -> dict:
        async with async_session_factory() as db:
            report = await db.scalar(
                select(AnalysisReport).where(
                    and_(AnalysisReport.id == report_id, AnalysisReport.user_id == user_id)
                )
            )
            if not report:
                raise AppException("报告不存在", 404, code=40412)

            # 是否首次分析
            count = await db.scalar(
                select(func.count()).select_from(AnalysisReport).where(AnalysisReport.user_id == user_id)
            ) or 0
            is_first = count <= 1

            # 提取指标
            from app.services.progress_service import ProgressService
            metrics = ProgressService._extract_metrics(report.result_data or {})

            # 获取趋势
            trends = await TrainingAdviceService._get_trends(db, user_id)

            # 构建规则上下文
            trend_ctx = {}
            for t in trends:
                trend_ctx[t.metric_name] = {
                    "direction": t.trend or "",
                    "persistence": t.persistence_count,
                    "change_rate": t.change_rate or 0,
                }

            ctx = {"metrics": metrics, "trends": trend_ctx, "current_plan": None}

            # 匹配规则
            matches = await KnowledgeBaseService.match_rules(db, ctx)

            diagnosis = []
            suggestions = []
            training_methods = []
            plan_template = None

            for m in matches:
                # R4-Training-3: 基于当前 rule 的 field 从 trend_ctx 取对应趋势
                trend_val = "new"
                field = m.get("field")
                if field and field in trend_ctx:
                    trend_val = trend_ctx[field].get("direction", "new")

                diagnosis.append({
                    "problem_id": m["problem_id"],
                    "problem_name": m["problem_name"],
                    "severity": m["severity"],
                    "trend": trend_val,
                    "description": m["suggestion"],
                })

                # R12-Training-B2: 建议 type 按规则类型判定，首次分析不再批量改写
                # （first_analysis 仅作为追加提示，不污染规则建议的类型语义）
                if m["rule_type"] == "trend_improving":
                    sug_type = "progress_confirm"
                elif m["rule_type"] == "trend_persistent":
                    sug_type = "persistent_warning"
                else:
                    sug_type = "new_issue"

                suggestions.append({"type": sug_type, "text": m["suggestion"]})

                for method_id in (m.get("training_methods") or []):
                    # R4-Training-13: method name 去除 METHOD_ 前缀
                    method_name = (
                        method_id.replace("METHOD_", "", 1)
                        if isinstance(method_id, str) and method_id.startswith("METHOD_")
                        else method_id
                    )
                    training_methods.append({
                        "method_id": method_id,
                        "name": method_name,
                        "description": "",
                    })

                if m.get("training_plan_template") and not plan_template:
                    plan_template = m["training_plan_template"]

            # R4-Training-11: 首次分析建议改为无条件追加
            if is_first:
                suggestions.append({
                    "type": "first_analysis",
                    "text": "这是您的首次分析，建议关注基本技术动作。",
                })

        return {
            "report_id": report_id,
            "is_first_analysis": is_first,
            "diagnosis": diagnosis,
            "suggestions": suggestions,
            "training_methods": training_methods,
            "training_plan_template": plan_template,
        }

    @staticmethod
    async def get_contextual_advice(user_id: int) -> dict:
        async with async_session_factory() as db:
            latest = await db.scalar(
                select(AnalysisReport)
                .where(AnalysisReport.user_id == user_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(1)
            )
            if not latest:
                raise AppException("暂无分析报告", 404, code=40412)

        return await TrainingAdviceService.get_advice_by_report(user_id, latest.id)

    @staticmethod
    async def generate_advice(user_id: int, report_id: int) -> dict:
        """生成训练建议 — 委托给 get_advice_by_report（R4-Training-4）"""
        return await TrainingAdviceService.get_advice_by_report(user_id, report_id)

    @staticmethod
    async def _get_trends(db: AsyncSession, user_id: int) -> list[TechniqueTrend]:
        rows = await db.execute(
            select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
        )
        return list(rows.scalars().all())

    @staticmethod
    async def get_templates(problem_id: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        async with async_session_factory() as db:
            qs = select(TrainingTemplate)
            count_qs = select(func.count()).select_from(TrainingTemplate)
            if problem_id:
                qs = qs.where(TrainingTemplate.problem_id == problem_id)
                count_qs = count_qs.where(TrainingTemplate.problem_id == problem_id)

            total = await db.scalar(count_qs) or 0
            qs = qs.order_by(TrainingTemplate.id).offset((page - 1) * page_size).limit(page_size)
            rows = await db.execute(qs)
            items = [
                {"id": r.id, "template_code": r.template_code, "name": r.name, "problem_id": r.problem_id}
                for r in rows.scalars().all()
            ]

        return {"total": total, "page": page, "page_size": page_size, "items": items}

    @staticmethod
    async def get_template_detail(template_id: int) -> Optional[dict]:
        async with async_session_factory() as db:
            row = await db.scalar(
                select(TrainingTemplate).where(TrainingTemplate.id == template_id)
            )
            if not row:
                return None
            return {
                "id": row.id,
                "template_code": row.template_code,
                "name": row.name,
                "problem_id": row.problem_id,
                "template_data": row.template_data,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    @staticmethod
    async def get_plan_adjustments(user_id: int, plan_id: int) -> dict:
        async with async_session_factory() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存在", 404, code=40420)

            rows = await db.execute(
                select(PlanAdjustment)
                .where(PlanAdjustment.training_plan_id == plan_id)
                .order_by(PlanAdjustment.created_at.desc())
            )
            all_rows = rows.scalars().all()
            adjustments = [
                {
                    "id": r.id,
                    # R5-Train-3: 非最新记录的 version 从 new_plan_snapshot 读取，避免用 r.id 作版本号
                    "version": plan.version if i == 0 else (r.new_plan_snapshot or {}).get("version", r.id),
                    "action": r.adjustment_action,
                    "reason": r.adjustment_reason,
                    "trigger_report_id": r.trigger_report_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "changes_summary": TrainingAdviceService._diff_snapshot(
                        r.old_plan_snapshot, r.new_plan_snapshot
                    ),
                }
                for i, r in enumerate(all_rows)
            ]

        return {"plan_id": plan_id, "current_version": plan.version, "adjustments": adjustments}

    @staticmethod
    def _diff_snapshot(old: dict | None, new: dict) -> str:
        """计算 old/new 快照 diff 摘要"""
        if not old:
            return "初始方案创建"

        changes = []
        # 对比 version
        if old.get("version") != new.get("version"):
            changes.append(f"版本 {old.get('version', 1)} → {new.get('version', 2)}")

        # 对比 goal
        old_goal = old.get("goal", {})
        new_goal = new.get("goal", {})
        for key in set(list(old_goal.keys()) + list(new_goal.keys())):
            old_val = old_goal.get(key)
            new_val = new_goal.get(key)
            if old_val != new_val and old_val is not None and new_val is not None:
                changes.append(f"{key}: {old_val} → {new_val}")

        # R5-Train-5: 对比 plan_data 中的 sessions/reps 变化
        old_pd = old.get("plan_data", {}) or {}
        new_pd = new.get("plan_data", {}) or {}
        old_sessions = old_pd.get("sessions", []) or []
        new_sessions = new_pd.get("sessions", []) or []
        if len(old_sessions) != len(new_sessions):
            changes.append(f"训练单数 {len(old_sessions)} → {len(new_sessions)}")
        for idx in range(min(len(old_sessions), len(new_sessions))):
            old_s = old_sessions[idx] if isinstance(old_sessions[idx], dict) else {}
            new_s = new_sessions[idx] if isinstance(new_sessions[idx], dict) else {}
            old_reps = old_s.get("reps")
            new_reps = new_s.get("reps")
            if old_reps is not None and new_reps is not None and old_reps != new_reps:
                changes.append(f"训练单{idx + 1} reps: {old_reps} → {new_reps}")

        return "; ".join(changes) if changes else "无变化"

    @staticmethod
    async def re_evaluate_plan(user_id: int, plan_id: int) -> dict:
        async with async_session_factory() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存在", 404, code=40420)

            # R4-Training-7: 防御性 MembershipService 校验
            from app.services.membership_service import MembershipService
            membership = await MembershipService.check_membership(db, user_id)
            if not membership.is_member:
                raise AppException("非会员无法重新评估训练方案", 403, code=40301)

            trends = await TrainingAdviceService._get_trends(db, user_id)
            goal_metrics = plan.goal_metrics or {}

            # R5-Train-1: 只保留 goal_metrics 中定义的指标，避免无关趋势影响评估
            trends = [t for t in trends if t.metric_name in goal_metrics]

            action, reason = TrainingAdviceService._evaluate_plan_effectiveness(trends, goal_metrics)

            if action != "maintain":
                # R4-Training-1: old/new snapshot 结构为 {version, goal, plan_data}
                old_snapshot = {
                    "version": plan.version,
                    "goal": goal_metrics,
                    "plan_data": plan.plan_data,
                }
                # R5-Train-2: _generate_new_plan 返回完整 snapshot {version, goal, plan_data}
                new_snapshot = TrainingAdviceService._generate_new_plan(
                    plan, trends, goal_metrics, action
                )

                adjustment = PlanAdjustment(
                    training_plan_id=plan_id,
                    trigger_report_id=None,
                    old_plan_snapshot=old_snapshot,
                    new_plan_snapshot=new_snapshot,
                    adjustment_reason=reason,
                    adjustment_action=action,
                )
                db.add(adjustment)
                plan.plan_data = new_snapshot.get("plan_data", plan.plan_data)
                plan.version += 1
                # R5-Train-2: 用 _generate_new_plan 更新后的 goal 写入 plan.goal_metrics 列
                plan.goal_metrics = new_snapshot.get("goal", goal_metrics)

            await db.commit()

        return {"plan_id": plan_id, "action": action, "reason": reason}

    @staticmethod
    def _evaluate_plan_effectiveness(trends: list, goal_metrics: dict) -> tuple:
        # R4-Training-2: 空 trends 守卫
        if not trends:
            return "maintain", "暂无足够趋势数据"

        # 达标判断基于值：up direction current_value >= target; down direction current_value <= target
        from app.services.progress_service import METRIC_DEFINITIONS
        all_achieved = True
        for trend in trends:
            target = goal_metrics.get(trend.metric_name)
            if target is None or trend.current_value is None:
                all_achieved = False
                break
            direction = METRIC_DEFINITIONS.get(trend.metric_name, {}).get("direction", "up")
            if direction == "up" and trend.current_value < target:
                all_achieved = False
                break
            elif direction == "down" and trend.current_value > target:
                all_achieved = False
                break

        declining = [t for t in trends if t.trend == "declining"]
        # R5-Prog-4: stagnant 判定仅检查 persistence_count >= STAGNANT_THRESHOLD，
        # 不再额外要求 trend == "stagnant"（与设计文档一致）
        stagnant = [t for t in trends if t.persistence_count >= STAGNANT_THRESHOLD]

        if all_achieved:
            return "new_goal", "已有指标达成目标，建议设定新目标"
        if declining:
            return "escalate", "指标下降趋势，建议升级训练强度"
        if len(stagnant) == len(trends):
            return "adjust", "连续多次无改善，建议调整方案"
        return "maintain", "指标改善中，保持当前方案"

    @staticmethod
    def _generate_new_plan(plan: TrainingPlan, trends: list, goal_metrics: dict, action: str) -> dict:
        """根据调整动作生成新方案快照 — 返回 {version, goal, plan_data}（R5-Train-2）

        - new_goal: 提升 goal_metrics 中各目标 10%（而非 plan_data.goal）
        - adjust: 增加 plan_data.sessions 中 reps 20%
        - R12-Training-B3: escalate 按 §8.6 设计为「诊断原因」动作，
          不改写训练内容（设计 _generate_new_plan 无此分支），
          诊断信息经 adjustment_reason 记录于 plan_adjustment
        """
        new_version = plan.version + 1
        # R5-Train-2: new_goal 动作修改 goal_metrics，复制后变更
        new_goal = dict(goal_metrics)
        old_data = plan.plan_data or {}
        # R12-Training-D4: 深拷贝后再变更 — 原先 dict(old_data) 浅拷贝后原地修改共享
        # sessions 列表，committed_state 与 old_plan_snapshot 被同步污染（新旧相等），
        # SQLAlchemy 相等性短路导致 plan_data 不进 UPDATE（reps 增幅不落库），
        # 且调整历史 _diff_snapshot 显示"无变化"。
        new_data = copy.deepcopy(old_data)

        if action == "new_goal":
            # R7-Train-1: 方向感知 — up 指标 *1.1 提升；down 指标 *0.9 降低（更难）
            from app.services.progress_service import METRIC_DEFINITIONS
            for metric, target in new_goal.items():
                if target is not None:
                    direction = METRIC_DEFINITIONS.get(metric, {}).get("direction", "up")
                    if direction == "up":
                        new_goal[metric] = round(target * 1.1, 4)
                    else:
                        new_goal[metric] = round(target * 0.9, 4)
        elif action == "adjust":
            sessions = new_data.get("sessions", [])
            for s in sessions:
                if isinstance(s, dict) and "reps" in s:
                    s["reps"] = int(s["reps"] * 1.2)
            new_data["sessions"] = sessions
        # R12-Training-B3: escalate 无方案改写分支 — 走默认 return（内容不变，
        # 仅 version +1 + adjustment_action/reason 记录诊断）

        return {
            "version": new_version,
            "goal": new_goal,
            "plan_data": new_data,
        }

    @staticmethod
    async def list_training_sessions(
        user_id: int, plan_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        async with async_session_factory() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存在", 404, code=40420)

            plan_data = plan.plan_data or {}
            sessions = plan_data.get("sessions", [])
            total = len(sessions)

            offset = (page - 1) * page_size
            page_sessions = sessions[offset:offset + page_size]

            items = []
            for i, s in enumerate(page_sessions):
                if isinstance(s, dict):
                    # 字段映射：title→name, status→is_completed（对齐 API §8.7）
                    items.append({
                        "id": s.get("id", offset + i + 1),
                        "plan_id": plan_id,
                        "name": s.get("title", s.get("name", f"训练单 {i+1}")),
                        "is_completed": s.get("status") == "completed" or s.get("is_completed", False),
                        "scheduled_date": s.get("scheduled_date"),
                        "completed_at": s.get("completed_at"),
                        "session_index": s.get("session_index", i + 1),
                        "reps": s.get("reps", 0),
                    })

        return {"plan_id": plan_id, "total": total, "page": page, "page_size": page_size, "items": items}

    @staticmethod
    async def complete_training_session(
        user_id: int, plan_id: int, session_id: int
    ) -> dict:
        async with async_session_factory() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存在", 404, code=40420)

            plan_data = copy.deepcopy(plan.plan_data or {})
            sessions = plan_data.get("sessions", [])

            # R5-Train-4: 按 id 或 session_index 查找，兼容无 id 的训练单
            session = next(
                (s for s in sessions if s.get("id") == session_id or s.get("session_index") == session_id),
                None,
            )
            if session is None:
                raise AppException("训练单不存在", 404, code=40422)

            if session.get("status") == "completed":
                raise AppException("已完成", 409, code=40902)

            session["status"] = "completed"
            session["completed_at"] = datetime.now(timezone.utc).isoformat()

            completed = sum(1 for s in sessions if isinstance(s, dict) and s.get("status") == "completed")
            progress = int(completed / len(sessions) * 100) if sessions else 0

            if progress >= 100:
                plan.status = "completed"

            plan.plan_data = plan_data
            flag_modified(plan, "plan_data")

            # 触发积分
            points_earned = 0
            try:
                from app.services.gamification_service import GamificationService
                points_earned = await GamificationService.add_points(db, user_id, "training_session", session_id)
            except Exception as e:
                logger.warning("training_points_failed", extra={"error": str(e)})

            await db.commit()

        return {
            "session_id": session_id,
            "is_completed": True,
            "plan_progress": progress,
            "points_earned": points_earned,
            "completed_at": datetime.now(timezone.utc),
        }
```
---

## 5.5 训练建议生成 Celery Task

> **R13-P3 文档同步（2026-10-29）**：原样例为 `app/tasks/training_advice_beat.py`（`@celery_app.task` 无 bind/无重试 + 裸 `asyncio.run` + `_generate_advice_async` 无 WS 推送实现 + 触发方式写 send_task）。实际实现为 `app/tasks/training.py`，以下代码按实现原样回写：
> - `@shared_task(bind=True, name="training_advice.generate_advice", max_retries=1, default_retry_delay=30)`；
> - `_run_async` 兼容 eager 模式事件循环嵌套（try 仅包裹探测，R12-SUP-2）；
> - 失败路径 `self.retry()`（不传 exc —— Celery 传 exc 时耗尽后重抛原异常而非 MaxRetriesExceededError，R12-SUP-1），耗尽后返回 `{"status": "error"}` 优雅降级；
> - 生成完成后经 `NotificationService.push_ws_message` 推送 `advice_ready`（WS 推送为真实实现，原样例仅 docstring 声明）；
> - 触发链路：`app/ai_pipeline/report_generator.py` L259-264（`_trigger_cascade` 内 `generate_advice_task.delay(user_id, report_id)` 投递，报告生成完成后级联触发，非 send_task）。

```python
"""
app/tasks/training.py — 训练建议生成 Celery 任务

依据：切片 07-training_advice/backend.md §5（generate_advice_task 定义）
R12-Training-B1: 补齐缺失的 Celery 任务，接通"分析报告完成 → 异步生成训练建议 → WS 推送"链路
事件驱动（分析流水线 Step 9 报告生成后触发），无需在 beat_schedule 注册定时触发。
"""

import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 Celery 任务中运行异步协程 — 兼容 eager 模式下的事件循环嵌套"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 无运行中的事件循环，直接 asyncio.run。
        # try 块只包裹探测：业务 RuntimeError 不得被误判为"无循环"后
        # 对已消费协程再次 asyncio.run（会掩盖原始异常，见 ai_pipeline/tasks.py）
        return asyncio.run(coro)
    # 已有运行中的事件循环，在新线程中运行；业务异常经 future.result() 原样重抛
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


@shared_task(bind=True, name="training_advice.generate_advice", max_retries=1, default_retry_delay=30)
def generate_advice_task(self, user_id: int, report_id: int):
    """
    训练建议生成 — 异步调用，分析报告完成后触发。

    逻辑：
    1. 接收 user_id + report_id，调用 TrainingAdviceService.generate_advice()
    2. 基于分析报告 + 历史趋势 + 知识库规则引擎生成个性化训练建议
    3. 生成完成后通过 WS 推送通知用户

    注意：此任务为事件驱动（分析流水线完成后 delay 触发），
    无需在 beat_schedule 中注册定时触发。
    """
    try:
        _run_async(_generate_advice_async(user_id, report_id))
        return {"status": "ok", "user_id": user_id, "report_id": report_id}
    except Exception as exc:
        logger.error(
            "generate_advice_task_failed",
            extra={"user_id": user_id, "report_id": report_id, "error": str(exc)},
        )
        # R12-AIPipeline-1: 失败路径显式重试（max_retries=1）。
        # 注意不传 exc —— Celery 语义：传 exc 时耗尽后重抛原异常而非
        # MaxRetriesExceededError，下方优雅降级分支将不可达。
        try:
            raise self.retry()
        except self.MaxRetriesExceededError:
            return {"status": "error", "error": str(exc)}


async def _generate_advice_async(user_id: int, report_id: int):
    """训练建议生成异步实现 — 生成后 WS 推送通知"""
    from app.services.training_service import TrainingAdviceService
    from app.services.notification_service import NotificationService

    advice = await TrainingAdviceService.generate_advice(user_id=user_id, report_id=report_id)

    # WS 推送：训练建议已生成
    try:
        await NotificationService.push_ws_message(
            user_id,
            "advice_ready",
            {
                "report_id": report_id,
                "is_first_analysis": advice.get("is_first_analysis", False),
                "suggestion_count": len(advice.get("suggestions", [])),
            },
        )
    except Exception as e:
        logger.warning("advice_ready_ws_push_failed: %s", e)
```

---

## 6. API 路由实现

> **R13-P3 文档同步（2026-10-29）**：原样例为 `advice_router.py`，以下按实际 `app/api/v1/training/router.py` 原样回写。原样例与实现的偏差（以实现为准）：
> ① 装饰器顺序：路由装饰器在上、`@limiter.limit("100/minute")` 在下（slowapi 限流真实生效顺序，R12-Gam-13），原样例顺序相反（限流为死代码）；
> ② 路由注册顺序：`/advice/contextual` 必须先于 `/advice/{report_id}` 注册，否则 `contextual` 被路径参数捕获返回 422，原样例注册顺序相反；
> ③ `require_membership` 为 `app/core/deps.py` 无参异步依赖（用法 `Depends(require_membership)`，非会员 403 / code 40300），原样例 `require_membership("member")` 工厂签名不存在；
> ④ 限流端点需 `request: Request` 参数（slowapi 要求）；
> ⑤ `get_template_detail` 的 404（code 40421）在路由层抛出，Service 返回 None。

```python
"""
app/api/v1/training/router.py - 训练建议 API 路由

依据：API 8 / 切片 07-training_advice/backend.md 6
8 个端点：advice/{report_id} / advice/contextual / templates / templates/{id}
          / plans/{id}/adjustments / plans/{id}/re-evaluate / plans/{id}/sessions / plans/{id}/sessions/{sid}/complete
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user, require_membership
from app.core.exceptions import AppException
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.services.training_service import TrainingAdviceService

router = APIRouter(prefix="/training", tags=["训练建议"])


@router.get("/advice/contextual", summary="综合训练建议")
@limiter.limit("100/minute")
async def get_contextual_advice(
    request: Request,
    user: User = Depends(get_current_user),
):
    data = await TrainingAdviceService.get_contextual_advice(user.id)
    return success(data=data)


@router.get("/advice/{report_id}", summary="基于报告的训练建议")
@limiter.limit("100/minute")
async def get_advice_by_report(
    request: Request,
    report_id: int,
    user: User = Depends(get_current_user),
):
    data = await TrainingAdviceService.get_advice_by_report(user.id, report_id)
    return success(data=data)


@router.get("/templates", summary="训练模板列表")
@limiter.limit("100/minute")
async def get_templates(
    request: Request,
    problem_id: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.get_templates(problem_id=problem_id, page=page, page_size=page_size)
    return success(data=data)


@router.get("/templates/{template_id}", summary="训练模板详情")
@limiter.limit("100/minute")
async def get_template_detail(
    request: Request,
    template_id: int,
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.get_template_detail(template_id)
    if not data:
        raise AppException("模板不存在", 404, code=40421)
    return success(data=data)


@router.get("/plans/{plan_id}/adjustments", summary="方案调整历史")
@limiter.limit("100/minute")
async def get_plan_adjustments(
    request: Request,
    plan_id: int,
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.get_plan_adjustments(user.id, plan_id)
    return success(data=data)


@router.post("/plans/{plan_id}/re-evaluate", summary="重新评估方案")
@limiter.limit("100/minute")
async def re_evaluate_plan(
    request: Request,
    plan_id: int,
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.re_evaluate_plan(user.id, plan_id)
    return success(data=data)


@router.get("/plans/{plan_id}/sessions", summary="训练单列表")
@limiter.limit("100/minute")
async def get_training_sessions(
    request: Request,
    plan_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.list_training_sessions(user.id, plan_id, page=page, page_size=page_size)
    return success(data=data)


@router.post("/plans/{plan_id}/sessions/{session_id}/complete", summary="完成训练单")
@limiter.limit("100/minute")
async def complete_training_session(
    request: Request,
    plan_id: int,
    session_id: int,
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.complete_training_session(user.id, plan_id, session_id)
    return success(data=data)
```

> **注意（R13-P3 文档同步）**：`require_membership` 是 `app/core/deps.py` 中的无参异步依赖（内部调用 `MembershipService.check_membership`，非会员抛 403 / code 40300），用法 `user: User = Depends(require_membership)`。受会员守卫端点共 **6 个**：GET /templates、GET /templates/{id}、GET /plans/{id}/adjustments、POST /plans/{id}/re-evaluate、GET /plans/{id}/sessions、POST /plans/{id}/sessions/{sid}/complete（原说明误计 5 个、遗漏 re-evaluate 自身；re-evaluate 另有 Service 层二次校验 403/40301，R4-Training-7 防御性双保险）。仅 GET /advice/{report_id} 与 GET /advice/contextual 保持 `get_current_user`（登录即可，与 API 设计 §8.1/§8.2 一致）。
**Router 注册**（`app/api/v1/__init__.py`，R13-P3 文档同步 —— 实际文件名为 `router.py` 而非 `advice_router.py`）：
```python
from app.api.v1.training.router import router as training_router
api_router.include_router(training_router)
```

> **说明（R13-P3 文档同步）**：training_advice 与 training_plan 共用 `/training` 前缀；实际实现将全部 8 个端点（/advice/{report_id}、/advice/contextual、/templates、/templates/{id}、/plans/{id}/adjustments、/plans/{id}/re-evaluate、/plans/{id}/sessions、/plans/{id}/sessions/{sid}/complete）统一收敛于单一 `app/api/v1/training/router.py`，原"Phase 1 仅注册 advice_router、Phase 2 追加 plan_router"的拆分说明已过时。advice 端点路径含 `/advice`、模板端点含 `/templates`、方案/训练单端点含 `/plans`，路由互不冲突；`/advice/contextual` 先于 `/advice/{report_id}` 注册（避免路径参数吞掉 contextual 返回 422）。
---

## 7. 冒烟测试脚本
> **R13-P3 文档同步（2026-10-29）**：冒烟脚本 `tests/smoke/training_advice_smoke_test.py` 尚未实现（`tests/smoke/` 当前仅含 `__init__.py`，全项目冒烟测试均未落地），以下脚本保留为设计参考。单元层验收以 `pytest tests/unit/test_training.py`（17 测试）+ `tests/unit/test_supplements_p1.py::TestTrainingPermissionGuard`（D1 权限守卫）+ `tests/unit/test_supplements_p2.py`（D2 趋势建议 / D3 方案版本化与动作分支）为准。

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

- [ ] 单元测试全部通过：`pytest tests/unit/test_training.py -v`（R13-P3 文档同步：实际测试文件为 test_training.py；权限守卫/趋势建议/方案版本化补充测试见 test_supplements_p1.py、test_supplements_p2.py）
- [ ] 冒烟测试通过：`python -m tests.smoke.training_advice_smoke_test`（R13-P3 文档同步：脚本尚未实现，见 §7 注记）
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

