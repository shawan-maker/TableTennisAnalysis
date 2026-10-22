# knowledge_base 基础设施模块 — 后端垂直切片设计

> **模块名称**：`knowledge_base`
> **所属目录**：`app/services/knowledge_base_service.py`（无独立路由，供 training_advice 调用）
> **定位**：乒乓球专业知识库结构化存储、规则引擎、训练方案模板
> **依据**：模块详细设计 v1.2 §3.1、数据库详细设计 v1.5 §2.24-2.27

---

## 1. 模块概述

| 属性 | 值 |
|------|-----|
| 模块名称 | `knowledge_base` |
| 所属目录 | `app/services/knowledge_base_service.py` |
| 一句话定位 | 无独立路由，供 training_advice 调用——技术动作分类树、常见问题库、规则引擎、训练方案模板 |
| 关联数据表 | knowledge_category, knowledge_entry, rule_definition, training_template |
| 依赖模块 | admin (CRUD 管理), training_advice (调用规则引擎) |
| 前置依赖 | auth, progress_analysis（提供趋势数据） |

### 核心能力

- **技术动作分类树管理**：8 大类（发球、正手攻、反手攻、搓球、拉球、推挡、步法、战术），JSONB 结构化存储
- **常见问题库 CRUD**：10+ 乒乓球常见问题，按分类组织
- **规则定义 CRUD**：单次规则（指标阈值判定）+ 趋势规则（方向/变化率/持续性判定）
- **训练方案模板 CRUD**：参数化模板，占位符填充
- **规则引擎匹配**：4 类规则按顺序执行——单次规则 → 趋势规则 → 改善规则 → 停滞规则
- **初始化脚本**：`scripts/init_knowledge_base.py` 解析 Markdown 知识库文件写入 DB

---

## 2. 任务清单

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `app/models/knowledge_base.py` | 无 | ☐ |
| 2 | 注册 Model | `app/models/__init__.py` | #1 | ☐ |
| 3 | 定义 Schema | `app/schemas/knowledge_base.py` | #1 | ☐ |
| 4 | 实现 Service | `app/services/knowledge_base_service.py` | #2,#3 | ☐ |
| 5 | 编写初始化脚本 | `scripts/init_knowledge_base.py` | #4 | ☐ |
| 6 | 编写测试 | `tests/unit/test_knowledge_base.py` | #4 | ☐ |
| 7 | 编写冒烟测试 | `tests/smoke/knowledge_base_smoke_test.py` | #5 | ☐ |

---

## 3. Model 实现

> **模型归属说明（A-3）**：`RuleDefinition` 和 `TrainingTemplate` 模型由 `knowledge_base` 模块统一定义（`app/models/knowledge_base.py`），其他模块（如 `training_advice`）通过 import 引用，不重复定义。

```python
# app/models/knowledge_base.py
"""知识库数据模型。"""

from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, Boolean, ForeignKey, Text, DateTime, Index  # R19-P2-5: 补 Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class KnowledgeCategory(Base):
    """技术动作分类。"""
    __tablename__ = "knowledge_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    """分类名：发球、正手攻球、反手攻球、搓球、拉球、推挡、步法、战术"""
    code: Mapped[str] = mapped_column(String(32), unique=True)
    """分类编码：serve / forehand_drive / backhand_drive / ..."""
    content: Mapped[dict] = mapped_column(JSONB)
    """分类内容（结构化数据：子分类列表、说明等）"""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entries: Mapped[list["KnowledgeEntry"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class KnowledgeEntry(Base):
    """知识条目。"""
    __tablename__ = "knowledge_entry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_category.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[dict] = mapped_column(JSONB)
    """条目内容（描述、要点、图片引用等）"""
    entry_type: Mapped[str] = mapped_column(String(32))
    """条目类型：action / problem / method / style / template"""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_knowledge_entry_content_gin", "content", postgresql_using="gin"),  # R19-P2-5: 补 GIN 索引（§6.2 L3019/§2.25 已定义）
    )

    category: Mapped["KnowledgeCategory"] = relationship(back_populates="entries")


class RuleDefinition(Base):
    """规则定义。"""
    __tablename__ = "rule_definition"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(64), unique=True)
    """规则编码：RULE_001 / RULE_TREND_001"""
    rule_name: Mapped[str] = mapped_column(String(128))
    rule_type: Mapped[str] = mapped_column(String(32))
    """规则类型：single / trend_persistent / trend_improving / stagnant / plan_effectiveness"""
    condition: Mapped[dict] = mapped_column(JSONB)
    """条件 JSONB: {metric, operator, threshold, aggregation}"""
    diagnosis: Mapped[dict] = mapped_column(JSONB)
    """诊断 JSONB: {problem_id, problem_name, severity, suggestion_template}"""
    training_methods: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    """训练方法 ID 列表: ["METHOD_012", ...]"""
    training_plan_template: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """训练方案模板编码"""
    adjustment_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """方案调整动作：maintain / adjust / escalate / new_goal"""
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TrainingTemplate(Base):
    """训练方案模板。"""
    __tablename__ = "training_template"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_code: Mapped[str] = mapped_column(String(64), unique=True)
    """模板编码：TPL_BACKHAND_IMPROVE"""
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    """模板分类"""
    difficulty: Mapped[str] = mapped_column(String(16), default="intermediate")
    """难度等级：beginner/intermediate/advanced"""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    """模板描述"""
    problem_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """关联问题 ID"""
    template_data: Mapped[dict] = mapped_column(JSONB)
    """模板数据: {goal, sessions[], exercises[], metrics[]}"""
    template_config: Mapped[dict] = mapped_column(JSONB)
    """模板配置"""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

**实现后必须**：
- [ ] 在 `app/models/__init__.py` 中导入 4 个 Model
- [ ] 运行 `alembic revision --autogenerate -m "add knowledge_base tables"`
- [ ] 运行 `alembic upgrade head`

---

## 4. Schema 实现

```python
# app/schemas/knowledge_base.py
"""知识库 Schema 定义。"""

from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field


class CategoryBrief(BaseModel):
    id: int
    name: str
    code: str
    model_config = {"from_attributes": True}


class CategoryDetail(CategoryBrief):
    content: dict
    created_at: datetime


class EntryBrief(BaseModel):
    id: int
    category_id: int
    title: str
    entry_type: str
    model_config = {"from_attributes": True}


class EntryDetail(EntryBrief):
    content: dict
    created_at: datetime


class RuleBrief(BaseModel):
    id: int
    rule_id: str
    rule_name: str
    rule_type: str
    is_active: bool
    model_config = {"from_attributes": True}


class RuleDetail(RuleBrief):
    condition: dict
    diagnosis: dict
    training_methods: Optional[list] = None
    training_plan_template: Optional[str] = None
    adjustment_action: Optional[str] = None


class TemplateBrief(BaseModel):
    id: int
    template_code: str
    name: str
    problem_id: Optional[str] = None
    model_config = {"from_attributes": True}


class TemplateDetail(TemplateBrief):
    template_data: dict
    created_at: datetime


class MatchResult(BaseModel):
    """规则引擎匹配结果。"""
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
    """规则引擎上下文——传入分析报告指标 + 趋势数据。"""
    metrics: dict[str, Any] = Field(default_factory=dict)
    """当前报告指标: {backhand_ratio: 0.18, forehand_ratio: 0.72, ...}"""
    trends: dict[str, dict] = Field(default_factory=dict)
    """趋势数据: {backhand_ratio: {direction: "improving", change_rate: 0.08, persistence: 2}, ...}"""
    current_plan: Optional[dict] = None
    """当前训练方案快照"""
```

---

## 5. Service 实现

```python
# app/services/knowledge_base_service.py
"""知识库业务逻辑层。"""

import re
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.database import get_async_session
from app.models.knowledge_base import (
    KnowledgeCategory,
    KnowledgeEntry,
    RuleDefinition,
    TrainingTemplate,
)
from app.schemas.knowledge_base import (
    CategoryBrief, CategoryDetail, EntryBrief, EntryDetail,
    RuleBrief, RuleDetail, TemplateBrief, TemplateDetail,
    MatchResult, RuleContext,
)


class KnowledgeBaseService:
    """知识库业务逻辑层——无独立路由，供 training_advice 调用。"""

    # --- 分类树管理 ---

    @staticmethod
    async def list_categories() -> list[CategoryBrief]:
        """查询所有分类。"""
        async with get_async_session() as db:
            result = await db.execute(
                select(KnowledgeCategory).order_by(KnowledgeCategory.id)
            )
            return [CategoryBrief.model_validate(c) for c in result.scalars()]

    @staticmethod
    async def get_category_by_code(code: str) -> CategoryDetail:
        """按编码查询分类详情。"""
        async with get_async_session() as db:
            cat = await db.scalar(
                select(KnowledgeCategory).where(KnowledgeCategory.code == code)
            )
            if not cat:
                raise AppException(f"分类 {code} 不存在", 404)
            return CategoryDetail.model_validate(cat)

    # --- 条目管理 ---

    @staticmethod
    async def list_entries(
        category_code: Optional[str] = None,
        entry_type: Optional[str] = None,
    ) -> list[EntryBrief]:
        """查询知识条目。"""
        async with get_async_session() as db:
            stmt = select(KnowledgeEntry)
            if category_code:
                stmt = stmt.join(KnowledgeCategory).where(
                    KnowledgeCategory.code == category_code
                )
            if entry_type:
                stmt = stmt.where(KnowledgeEntry.entry_type == entry_type)
            result = await db.execute(stmt.order_by(KnowledgeEntry.id))
            return [EntryBrief.model_validate(e) for e in result.scalars()]

    @staticmethod
    async def get_entry_detail(entry_id: int) -> EntryDetail:
        """获取条目详情。"""
        async with get_async_session() as db:
            entry = await db.get(KnowledgeEntry, entry_id)
            if not entry:
                raise AppException("知识条目不存在", 404)
            return EntryDetail.model_validate(entry)

    # --- 规则管理 ---

    @staticmethod
    async def list_rules(
        rule_type: Optional[str] = None,
        is_active: bool = True,
    ) -> list[RuleBrief]:
        """查询规则列表。"""
        async with get_async_session() as db:
            stmt = select(RuleDefinition).where(
                RuleDefinition.is_active == is_active
            )
            if rule_type:
                stmt = stmt.where(RuleDefinition.rule_type == rule_type)
            result = await db.execute(stmt.order_by(RuleDefinition.id))
            return [RuleBrief.model_validate(r) for r in result.scalars()]

    @staticmethod
    async def get_rules_by_problem(problem_id: str) -> list[RuleDetail]:
        """按问题 ID 查询关联规则。"""
        async with get_async_session() as db:
            result = await db.execute(
                select(RuleDefinition).where(
                    RuleDefinition.diagnosis["problem_id"].astext == problem_id,
                    RuleDefinition.is_active == True,
                )
            )
            return [RuleDetail.model_validate(r) for r in result.scalars()]

    # --- 模板管理 ---

    @staticmethod
    async def list_templates(problem_id: Optional[str] = None) -> list[TemplateBrief]:
        """查询训练方案模板。"""
        async with get_async_session() as db:
            stmt = select(TrainingTemplate)
            if problem_id:
                stmt = stmt.where(TrainingTemplate.problem_id == problem_id)
            result = await db.execute(stmt.order_by(TrainingTemplate.id))
            return [TemplateBrief.model_validate(t) for t in result.scalars()]

    @staticmethod
    async def get_template_detail(template_code: str) -> TemplateDetail:
        """获取模板详情。"""
        async with get_async_session() as db:
            tpl = await db.scalar(
                select(TrainingTemplate).where(
                    TrainingTemplate.template_code == template_code
                )
            )
            if not tpl:
                raise AppException(f"模板 {template_code} 不存在", 404)
            return TemplateDetail.model_validate(tpl)

    # --- 规则引擎核心 ---

    @staticmethod
    async def match_rules(ctx: RuleContext) -> list[MatchResult]:
        """规则引擎匹配——核心方法。

        匹配流程（按优先级顺序）：
        1. 单次规则（single）：检查当前报告指标是否触发阈值
        2. 趋势规则（trend_persistent / trend_improving / stagnant）：检查趋势方向
        3. 改善规则：指标连续改善 ≥2 次 → 进步确认
        4. 停滞规则：指标连续停滞 ≥3 次 → 停滞警告 + 方案调整
        """
        results: list[MatchResult] = []
        async with get_async_session() as db:
            all_rules = await db.execute(
                select(RuleDefinition)
                .where(RuleDefinition.is_active == True)
                .order_by(RuleDefinition.rule_type)  # single 在前
            )
            rules = all_rules.scalars().all()

            for rule in rules:
                try:
                    match = KnowledgeBaseService._evaluate_rule(rule, ctx)
                    if match:
                        results.append(match)
                except Exception as e:
                    # 规则解析失败 → 跳过，记录日志
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Rule {rule.rule_id} evaluation failed: {e}"
                    )
                    continue

            return results

    @staticmethod
    def _evaluate_rule(rule: RuleDefinition, ctx: RuleContext) -> Optional[MatchResult]:
        """评估单条规则是否匹配。"""
        cond = rule.condition
        metric = cond.get("metric")
        operator = cond.get("operator")
        threshold = cond.get("threshold")
        aggregation = cond.get("aggregation", "single")

        if aggregation == "single":
            # 单次规则：直接比较当前指标值
            current_value = ctx.metrics.get(metric)
            if current_value is None:
                return None
            if not KnowledgeBaseService._compare(current_value, operator, threshold):
                return None
        elif aggregation in ("trend_persistent", "trend_improving", "stagnant"):
            # 趋势规则：检查趋势方向和持续性
            trend = ctx.trends.get(metric)
            if not trend:
                return None
            direction = trend.get("direction")
            persistence = trend.get("persistence", 0)
            change_rate = trend.get("change_rate", 0)

            required_direction = cond.get("direction")
            min_persistence = cond.get("min_persistence", 1)
            min_change_rate = cond.get("min_change_rate", 0.0)

            if required_direction and direction != required_direction:
                return None
            if persistence < min_persistence:
                return None
            if abs(change_rate) < min_change_rate:
                return None

        # 规则匹配，生成诊断
        diagnosis = rule.diagnosis
        suggestion_template = diagnosis.get("suggestion_template", "")

        # 填充模板占位符
        suggestion = suggestion_template
        if metric and metric in ctx.metrics:
            suggestion = suggestion.replace(
                "{current_value}", str(ctx.metrics[metric])
            )
        suggestion = suggestion.replace("{threshold}", str(threshold))

        return MatchResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            rule_type=rule.rule_type,
            problem_id=diagnosis.get("problem_id", ""),
            problem_name=diagnosis.get("problem_name", ""),
            severity=diagnosis.get("severity", "medium"),
            suggestion=suggestion,
            adjustment_action=rule.adjustment_action,
            training_methods=rule.training_methods,
            training_plan_template=rule.training_plan_template,
        )

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        """比较运算符判断。"""
        if operator == "<":
            return value < threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == ">":
            return value > threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "==":
            return abs(value - threshold) < 0.001
        return False

    @staticmethod
    async def render_template(
        template_code: str,
        metrics: dict,
    ) -> dict:
        """渲染训练方案模板——用当前指标值替换占位符。

        模板中的占位符格式为 {metric_name}，根据用户当前指标值填充。
        """
        async with get_async_session() as db:
            tpl = await db.scalar(
                select(TrainingTemplate).where(
                    TrainingTemplate.template_code == template_code
                )
            )
            if not tpl:
                raise AppException(f"模板 {template_code} 不存在", 404)

            template_data = tpl.template_data
            rendered = KnowledgeBaseService._fill_placeholders(
                template_data, metrics
            )
            return rendered

    @staticmethod
    def _fill_placeholders(data, metrics: dict):
        """递归填充模板占位符。"""
        if isinstance(data, str):
            for key, value in metrics.items():
                data = data.replace(f"{{{key}}}", str(value))
            return data
        elif isinstance(data, dict):
            return {
                k: KnowledgeBaseService._fill_placeholders(v, metrics)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [
                KnowledgeBaseService._fill_placeholders(item, metrics)
                for item in data
            ]
        return data
```

---

## 6. 调用方式（无独立路由）

knowledge_base 模块**无独立 REST API 路由**，通过 Service 层被以下模块调用：

### 6.1 被 training_advice 调用

```python
# app/services/training_advice_service.py（调用方示例）
from app.services.knowledge_base_service import KnowledgeBaseService
from app.schemas.knowledge_base import RuleContext

class TrainingAdviceService:
    @staticmethod
    async def generate_advice(report_id: int, user_id: int):
        """生成训练建议——调用知识库规则引擎。"""
        # 1. 读取分析报告指标
        metrics = await TrainingAdviceService._extract_metrics(report_id)
        # 2. 读取趋势数据
        trends = await TrainingAdviceService._get_trends(user_id)
        # 3. 构造规则上下文
        ctx = RuleContext(metrics=metrics, trends=trends)
        # 4. 调用知识库规则引擎
        match_results = await KnowledgeBaseService.match_rules(ctx)
        # 5. 渲染训练方案模板
        for result in match_results:
            if result.training_plan_template:
                plan = await KnowledgeBaseService.render_template(
                    result.training_plan_template, metrics
                )
                # 生成训练建议记录...
```

### 6.2 被 admin 调用（CRUD 管理）

```python
# app/services/admin_service.py（调用方示例）
# 管理员通过 admin 模块的 Service 方法间接管理知识库 CRUD
# admin_service.py 中直接操作 KnowledgeCategory / KnowledgeEntry / RuleDefinition / TrainingTemplate
```

---

## 7. 初始化脚本

```python
# scripts/init_knowledge_base.py
"""知识库初始化脚本——解析知识库定义文件并写入 DB。

用法: python scripts/init_knowledge_base.py
"""

import asyncio
import json
from pathlib import Path

from app.core.database import get_async_session
from app.models.knowledge_base import (
    KnowledgeCategory, KnowledgeEntry,
    RuleDefinition, TrainingTemplate,
)


# 8 大技术动作分类
CATEGORIES = [
    {"name": "发球", "code": "serve", "content": {"subcategories": ["下旋发球", "侧旋发球", "不转发球"]}},
    {"name": "正手攻球", "code": "forehand_drive", "content": {"subcategories": ["正手快攻", "正手拉球", "正手扣杀"]}},
    {"name": "反手攻球", "code": "backhand_drive", "content": {"subcategories": ["反手快拨", "反手拉球", "反手弹击"]}},
    {"name": "搓球", "code": "push", "content": {"subcategories": ["慢搓", "快搓", "摆短"]}},
    {"name": "拉球", "code": "loop", "content": {"subcategories": ["高吊弧圈", "前冲弧圈", "反拉"]}},
    {"name": "推挡", "code": "block", "content": {"subcategories": ["快推", "加力推", "减力挡"]}},
    {"name": "步法", "code": "footwork", "content": {"subcategories": ["单步", "跨步", "并步", "交叉步"]}},
    {"name": "战术", "code": "tactics", "content": {"subcategories": ["发抢战术", "相持战术", "防守反击"]}},
]

# 常见问题
PROBLEMS = [
    {"title": "反手使用率不足", "entry_type": "problem", "category_code": "backhand_drive",
     "content": {"description": "反手使用率低于 30%，过度依赖正手"}},
    {"title": "正手拉球弧线过高", "entry_type": "problem", "category_code": "loop",
     "content": {"description": "拉球弧线过高，容易被对手反冲"}},
    # ... 更多问题
]

# 规则定义
RULES = [
    {
        "rule_id": "RULE_001",
        "rule_name": "反手使用率不足",
        "rule_type": "single",
        "condition": {"metric": "backhand_ratio", "operator": "<", "threshold": 0.30, "aggregation": "single"},
        "diagnosis": {
            "problem_id": "PROBLEM_003",
            "problem_name": "反手使用率不足",
            "severity": "medium",
            "suggestion_template": "反手使用率 {current_value}，低于推荐值 {threshold}，建议增加反手练习",
        },
        "training_methods": ["METHOD_012", "METHOD_013"],
        "training_plan_template": "TPL_BACKHAND_IMPROVE",
        "adjustment_action": None,
    },
    {
        "rule_id": "RULE_TREND_001",
        "rule_name": "反手使用率持续改善",
        "rule_type": "trend_improving",
        "condition": {"metric": "backhand_ratio", "direction": "improving",
                      "min_persistence": 2, "min_change_rate": 0.05,
                      "aggregation": "trend_improving"},
        "diagnosis": {
            "problem_id": "PROBLEM_003",
            "problem_name": "反手使用率改善中",
            "severity": "low",
            "suggestion_template": "反手使用率持续改善，当前 {current_value}，建议维持当前训练方案",
        },
        "adjustment_action": "maintain",
    },
    {
        "rule_id": "RULE_TREND_002",
        "rule_name": "反手使用率停滞",
        "rule_type": "stagnant",
        "condition": {"metric": "backhand_ratio", "direction": "stagnant",
                      "min_persistence": 3, "min_change_rate": 0.0,
                      "aggregation": "stagnant"},
        "diagnosis": {
            "problem_id": "PROBLEM_003",
            "problem_name": "反手使用率停滞",
            "severity": "high",
            "suggestion_template": "反手使用率连续 3 次分析无改善，建议调整训练方案",
        },
        "adjustment_action": "adjust",
    },
]

# 训练方案模板
TEMPLATES = [
    {
        "template_code": "TPL_BACKHAND_IMPROVE",
        "name": "反手提升训练方案",
        "problem_id": "PROBLEM_003",
        "template_data": {
            "goal": {"metric": "backhand_ratio", "target": 0.35},
            "sessions": [
                {"name": "反手多球练习", "reps": 50, "duration_min": 15},
                {"name": "反手定点拉球", "reps": 30, "duration_min": 10},
            ],
            "exercises": ["反手定点拉球", "反手一正一反", "反手发力拉球"],
            "metrics": ["backhand_ratio", "landing_backhand_pct"],
        },
    },
]


async def init_knowledge_base():
    """初始化知识库数据。"""
    async with get_async_session() as db:
        # 1. 写入分类
        for cat_data in CATEGORIES:
            existing = await db.scalar(
                KnowledgeCategory.__table__.select().where(
                    KnowledgeCategory.code == cat_data["code"]
                )
            )
            if not existing:
                cat = KnowledgeCategory(**cat_data)
                db.add(cat)
        await db.flush()

        # 2. 写入问题条目
        for prob_data in PROBLEMS:
            cat = await db.scalar(
                select(KnowledgeCategory).where(
                    KnowledgeCategory.code == prob_data.pop("category_code")
                )
            )
            if cat:
                entry = KnowledgeEntry(category_id=cat.id, **prob_data)
                db.add(entry)

        # 3. 写入规则
        for rule_data in RULES:
            existing = await db.scalar(
                select(RuleDefinition).where(
                    RuleDefinition.rule_id == rule_data["rule_id"]
                )
            )
            if not existing:
                rule = RuleDefinition(**rule_data)
                db.add(rule)

        # 4. 写入模板
        for tpl_data in TEMPLATES:
            existing = await db.scalar(
                select(TrainingTemplate).where(
                    TrainingTemplate.template_code == tpl_data["template_code"]
                )
            )
            if not existing:
                tpl = TrainingTemplate(**tpl_data)
                db.add(tpl)

        await db.commit()
        print(f"Knowledge base initialized: {len(CATEGORIES)} categories, "
              f"{len(PROBLEMS)} entries, {len(RULES)} rules, "
              f"{len(TEMPLATES)} templates")


if __name__ == "__main__":
    asyncio.run(init_knowledge_base())
```

---

## 8. 测试要点

```python
# tests/unit/test_knowledge_base.py
"""knowledge_base 模块测试。覆盖：规则引擎匹配、模板渲染、CRUD。"""
import pytest
from app.services.knowledge_base_service import KnowledgeBaseService
from app.schemas.knowledge_base import RuleContext


# === 1. 规则引擎匹配 ===
@pytest.mark.asyncio
async def test_single_rule_match(db_session):
    """单次规则：backhand_ratio < 0.30 → 匹配。"""
    ctx = RuleContext(
        metrics={"backhand_ratio": 0.18, "forehand_ratio": 0.72},
        trends={},
    )
    results = await KnowledgeBaseService.match_rules(ctx)
    # 应匹配 RULE_001（反手使用率不足）
    assert any(r.rule_id == "RULE_001" for r in results)
    matched = next(r for r in results if r.rule_id == "RULE_001")
    assert "反手使用率" in matched.suggestion
    assert "0.18" in matched.suggestion


@pytest.mark.asyncio
async def test_single_rule_no_match(db_session):
    """单次规则：backhand_ratio >= 0.30 → 不匹配。"""
    ctx = RuleContext(
        metrics={"backhand_ratio": 0.40, "forehand_ratio": 0.60},
        trends={},
    )
    results = await KnowledgeBaseService.match_rules(ctx)
    assert not any(r.rule_id == "RULE_001" for r in results)


@pytest.mark.asyncio
async def test_trend_improving_rule(db_session):
    """趋势规则：改善中 → 匹配进步确认。"""
    ctx = RuleContext(
        metrics={"backhand_ratio": 0.25},
        trends={
            "backhand_ratio": {
                "direction": "improving",
                "persistence": 2,
                "change_rate": 0.08,
            }
        },
    )
    results = await KnowledgeBaseService.match_rules(ctx)
    assert any(r.rule_id == "RULE_TREND_001" for r in results)


@pytest.mark.asyncio
async def test_stagnant_rule(db_session):
    """停滞规则：连续 3 次无改善 → 匹配停滞警告。"""
    ctx = RuleContext(
        metrics={"backhand_ratio": 0.22},
        trends={
            "backhand_ratio": {
                "direction": "stagnant",
                "persistence": 3,
                "change_rate": 0.01,
            }
        },
    )
    results = await KnowledgeBaseService.match_rules(ctx)
    assert any(r.rule_id == "RULE_TREND_002" for r in results)


# === 2. 模板渲染 ===
@pytest.mark.asyncio
async def test_template_render(db_session):
    """模板占位符填充正确。"""
    rendered = await KnowledgeBaseService.render_template(
        "TPL_BACKHAND_IMPROVE",
        {"backhand_ratio": 0.18, "landing_backhand_pct": 0.35},
    )
    assert rendered["goal"]["target"] == 0.35
    assert len(rendered["sessions"]) == 2
    assert "反手多球练习" in rendered["sessions"][0]["name"]


# === 3. 查询 ===
@pytest.mark.asyncio
async def test_list_categories(db_session):
    """查询 8 大分类。"""
    categories = await KnowledgeBaseService.list_categories()
    assert len(categories) == 8
    assert any(c.code == "serve" for c in categories)
```

---

## 9. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_knowledge_base.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.knowledge_base_smoke_test`
- [ ] 4 个 Model 已在 `app/models/__init__.py` 中导入
- [ ] 数据库迁移已生成并执行
- [ ] 初始化脚本可成功执行：`python scripts/init_knowledge_base.py`
- [ ] 8 大技术动作分类树正确存储和查询
- [ ] 规则引擎正确执行 4 类匹配（单次/趋势/改善/停滞）
- [ ] 训练方案模板占位符正确填充
- [ ] 规则解析失败时正确跳过并记录日志
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@staticmethod`，**禁止** 创建实例
- **无独立路由**，所有调用通过 Service 层方法，**禁止** 创建 APIRouter
- 规则引擎 condition JSONB 解析失败 **必须** 跳过并记录日志，**禁止** 抛出异常中断匹配
- 模板占位符 **必须** 使用 `{metric_name}` 格式，**禁止** 自定义占位符语法
- 初始化脚本 **必须** 幂等（已存在的记录跳过），**禁止** 重复写入
- 规则匹配顺序 **必须** 为 single → trend → stagnant，**禁止** 随意调整顺序

> **覆盖度修复说明（A-3）**：已确认 `RuleDefinition` 和 `TrainingTemplate` 模型在 `knowledge_base` 切片 §3 中定义（`app/models/knowledge_base.py`），并添加归属说明注释。
> 其他模块（如 `training_advice`）通过 `from app.models.knowledge_base import RuleDefinition, TrainingTemplate` 引用，不重复定义。
