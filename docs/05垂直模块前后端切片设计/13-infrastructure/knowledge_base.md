knowledge_base 基础设施模块 — 后端垂直切片设计

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
- **规则定义 CRUD**：单次规则（指标阈值判定）+ 趋势规则（trend_persistent / trend_improving，方向/变化率/持续性判定）+ 停滞规则（stagnant）+ 方案有效性规则（plan_effectiveness）
- **训练方案模板 CRUD**：参数化模板，占位符填充
- **规则引擎匹配**：5 类规则按 RULE_TYPE_ORDER 优先级执行——single → trend_persistent → trend_improving → stagnant → plan_effectiveness（R13-P3 文档同步：原 4 类描述 + order_by(rule_type) 字符串排序无法保证 single 在前，实际为显式优先级映射）
- **初始化脚本**：`scripts/init_knowledge_base.py` 内置 Python 数据常量（CATEGORIES/PROBLEMS/RULES/TEMPLATES）幂等写入 DB（R12-KB-1 补齐；不解析 Markdown 文件）

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
"""知识库业务逻辑层。

R13-P3 文档同步（以实际实现为准）：
- 所有方法第一个参数为 db: AsyncSession（调用方传入，非内部 get_async_session()）
- 返回值为 dict（非 Pydantic Brief/Detail 对象）；match_rules 返回 list[dict]
- 规则类型优先级 RULE_TYPE_ORDER（5 类，含 plan_effectiveness）
- _evaluate_rule 返回 MatchResult dict {matched, severity, suggestion_params}
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.knowledge_base import (
    KnowledgeCategory, KnowledgeEntry, RuleDefinition, TrainingTemplate,
)

logger = logging.getLogger(__name__)

# 规则类型优先级：single > trend_persistent > trend_improving > stagnant > plan_effectiveness
# R13-P3 文档同步: 5 类规则（原文档 4 类；plan_effectiveness 为方案有效性规则）
RULE_TYPE_ORDER = {
    "single": 1,
    "trend_persistent": 2,
    "trend_improving": 3,
    "stagnant": 4,
    "plan_effectiveness": 5,
}


class KnowledgeBaseService:
    """知识库业务逻辑层（无独立 Router，被 training 和 admin 调用）"""

    @staticmethod
    async def list_categories(db: AsyncSession) -> list[dict]:
        """查询所有分类（返回 dict 列表）。"""
        rows = await db.execute(select(KnowledgeCategory).order_by(KnowledgeCategory.id))
        return [{"id": r.id, "name": r.name, "code": r.code} for r in rows.scalars().all()]

    @staticmethod
    async def get_category_by_code(db: AsyncSession, code: str) -> dict:
        """按编码查询分类详情（不存在 404 code=40401）。"""
        ...

    @staticmethod
    async def list_entries(
        db: AsyncSession, category_code: Optional[str] = None, entry_type: Optional[str] = None
    ) -> list[dict]:
        """查询知识条目（category_code 走 JOIN knowledge_category 过滤）。"""
        ...

    @staticmethod
    async def get_entry_detail(db: AsyncSession, entry_id: int) -> dict:
        """获取条目详情（不存在 404 code=40402）。"""
        ...

    @staticmethod
    async def list_rules(
        db: AsyncSession, rule_type: Optional[str] = None, is_active: bool = True
    ) -> list[dict]:
        """查询规则列表（is_active 筛选默认 True）。"""
        ...

    @staticmethod
    async def get_rules_by_problem(db: AsyncSession, problem_id: str) -> list[dict]:
        """按 problem_id 查询关联规则——diagnosis JSONB 路径查询
        （diagnosis["problem_id"].astext == problem_id，利用 GIN 索引）。"""
        ...

    @staticmethod
    async def list_templates(db: AsyncSession, problem_id: Optional[str] = None) -> list[dict]:
        """查询训练方案模板（可按 problem_id 过滤）。"""
        ...

    @staticmethod
    async def get_template_detail(db: AsyncSession, template_code: str) -> dict:
        """获取模板详情（不存在 404 code=40403）。"""
        ...

    @staticmethod
    async def match_rules(db: AsyncSession, ctx: dict) -> list[dict]:
        """规则引擎匹配 - 核心方法（R13-P3 文档同步）

        ctx 为 dict（非 Pydantic RuleContext 对象）:
        {metrics: {k: v}, trends: {k: {direction, persistence, change_rate}}, current_plan: Optional[dict]}
        按 RULE_TYPE_ORDER 优先级排序后逐条评估；单条规则解析失败仅 warning 并跳过。
        """
        rows = await db.execute(
            select(RuleDefinition)
            .where(RuleDefinition.is_active == True)
            .order_by(RuleDefinition.id)
        )
        all_rules = rows.scalars().all()

        # 按规则类型优先级排序（R13-P3 文档同步: 显式 RULE_TYPE_ORDER 映射；
        # 原文档 .order_by(RuleDefinition.rule_type) 字符串排序无法保证 single 在前）
        sorted_rules = sorted(all_rules, key=lambda r: RULE_TYPE_ORDER.get(r.rule_type, 99))

        results = []
        for rule in sorted_rules:
            try:
                match_result = KnowledgeBaseService._evaluate_rule(rule, ctx)
                if match_result and match_result.get("matched"):
                    diag = rule.diagnosis or {}
                    # 用 suggestion_params 填充建议模板（递归占位符渲染）
                    suggestion_template = diag.get("suggestion_template", "")
                    suggestion = (
                        KnowledgeBaseService._fill_placeholders(
                            suggestion_template, match_result.get("suggestion_params", {})
                        )
                        if suggestion_template else ""
                    )
                    results.append({
                        "rule_id": rule.rule_id,
                        "rule_name": rule.rule_name,
                        "rule_type": rule.rule_type,
                        "problem_id": diag.get("problem_id", ""),
                        "problem_name": diag.get("problem_name", ""),
                        # R12-KB-2: severity 取自 diagnosis JSONB（设计规定 severity
                        # 是诊断结论属性），不再从 condition 读取（原恒为 medium 兜底）
                        "severity": diag.get("severity", "medium"),
                        "suggestion": suggestion,
                        "adjustment_action": rule.adjustment_action,
                        "training_methods": rule.training_methods,
                        "training_plan_template": rule.training_plan_template,
                        "field": (rule.condition or {}).get("metric"),
                    })
            except Exception as e:
                logger.warning("rule_eval_failed", extra={"rule_id": rule.rule_id, "error": str(e)})
                continue

        return results

    @staticmethod
    def _evaluate_rule(rule, ctx: dict) -> Optional[dict]:
        """评估单条规则是否匹配 — 返回 MatchResult dict 或 None。

        R13-P3 文档同步: 返回 {matched: True, severity, suggestion_params}
        （非 Pydantic MatchResult 对象）；R2-KB-1: 规则类型从 condition JSONB 的
        aggregation 键读取（而非 rule.rule_type 列）。
        """
        cond = rule.condition or {}
        metrics = ctx.get("metrics", {})
        trends = ctx.get("trends", {})
        rule_type = cond.get("aggregation", "single")
        suggestion_params: dict[str, Any] = {}

        if rule_type == "single":
            metric = cond.get("metric")
            operator = cond.get("operator", "<")
            threshold = cond.get("threshold")
            value = metrics.get(metric)
            if value is None:
                return None
            if KnowledgeBaseService._compare(value, operator, threshold):
                # R2-KB-2: 使用 {current_value} 占位符（而非 {value}）
                suggestion_params.update(
                    {"metric": metric, "current_value": value, "threshold": threshold}
                )
                return {"matched": True, "severity": cond.get("severity", "medium"),
                        "suggestion_params": suggestion_params}
            return None

        elif rule_type in ("trend_persistent", "trend_improving"):
            metric = cond.get("metric")
            direction = cond.get("direction")
            min_persistence = cond.get("min_persistence", 2)
            min_change_rate = cond.get("min_change_rate", 0.0)
            trend_info = trends.get(metric, {})
            actual_direction = trend_info.get("direction", "")
            persistence = trend_info.get("persistence", 0)
            change_rate = trend_info.get("change_rate", 0)
            if direction and actual_direction != direction:
                return None
            if persistence < min_persistence:
                return None
            if abs(change_rate) < min_change_rate:
                return None
            suggestion_params.update({
                "metric": metric, "direction": actual_direction,
                "persistence": persistence, "change_rate": change_rate,
            })
            return {"matched": True, "severity": cond.get("severity", "medium"),
                    "suggestion_params": suggestion_params}

        elif rule_type == "stagnant":
            # R12-KB-3: 条件键统一为 min_persistence（设计 §知识库规则评估），
            # 原先误用 min_stagnation 导致设计种子规则条件键不生效；
            # 要求 direction == "stagnant" 且 persistence >= min_persistence
            metric = cond.get("metric")
            min_persistence = cond.get("min_persistence", 1)
            trend_info = trends.get(metric, {})
            if (trend_info.get("persistence", 0) >= min_persistence
                    and trend_info.get("direction") == "stagnant"):
                suggestion_params.update(
                    {"metric": metric, "persistence": trend_info.get("persistence", 0)}
                )
                return {"matched": True, "severity": cond.get("severity", "medium"),
                        "suggestion_params": suggestion_params}
            return None

        elif rule_type == "plan_effectiveness":
            # R13-P3 文档同步: 方案有效性规则分支（原文档缺失）——
            # current_plan.goal_completion[metric] >= threshold（默认 0.8）
            current_plan = ctx.get("current_plan")
            if not current_plan:
                return None
            goal_completion = current_plan.get("goal_completion", {})
            metric = cond.get("metric")
            threshold = cond.get("threshold", 0.8)
            value = goal_completion.get(metric, 0)
            if value >= threshold:
                suggestion_params.update(
                    {"metric": metric, "completion": value, "threshold": threshold}
                )
                return {"matched": True, "severity": cond.get("severity", "medium"),
                        "suggestion_params": suggestion_params}
            return None

        return None

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        """比较运算符（支持别名 lt/lte/gt/gte/eq）。"""
        if operator in ("<", "lt"):
            return value < threshold
        elif operator in ("<=", "lte"):
            return value <= threshold
        elif operator in (">", "gt"):
            return value > threshold
        elif operator in (">=", "gte"):
            return value >= threshold
        elif operator in ("==", "eq"):
            return abs(value - threshold) < 0.001
        return False

    @staticmethod
    async def render_template(db: AsyncSession, template_code: str, metrics: dict) -> dict:
        """模板参数化 - 用指标值填充占位符（db 由调用方传入）。"""
        detail = await KnowledgeBaseService.get_template_detail(db, template_code)
        if not detail:
            return {}
        return KnowledgeBaseService._fill_placeholders(detail["template_data"], metrics)

    @staticmethod
    def _fill_placeholders(data: Any, metrics: dict) -> Any:
        """递归填充 {metric_name} 占位符（str/dict/list 递归）。"""
        if isinstance(data, str):
            for key, value in metrics.items():
                data = data.replace("{" + key + "}", str(value))
            return data
        elif isinstance(data, dict):
            return {k: KnowledgeBaseService._fill_placeholders(v, metrics)
                    for k, v in data.items()}
        elif isinstance(data, list):
            return [KnowledgeBaseService._fill_placeholders(item, metrics)
                    for item in data]
        return data
```

---

## 6. 调用方式（无独立路由）

knowledge_base 模块**无独立 REST API 路由**，通过 Service 层被以下模块调用：

### 6.1 被 training_advice 调用

```python
# app/services/training_service.py（R13-P3 文档同步: 实际调用方为 training 模块的
# TrainingAdviceService.get_advice_by_report；ctx 为 dict 而非 Pydantic RuleContext 对象）
from app.services.knowledge_base_service import KnowledgeBaseService


class TrainingAdviceService:
    @staticmethod
    async def get_advice_by_report(user_id: int, report_id: int) -> dict:
        """生成训练建议——调用知识库规则引擎。"""
        async with async_session_factory() as db:
            # 1. 提取分析报告指标
            metrics = ProgressService._extract_metrics(report.result_data or {})
            # 2. 获取趋势数据 → {metric_name: {direction, persistence, change_rate}}
            trends = await TrainingAdviceService._get_trends(db, user_id)
            # 3. 构造规则上下文（dict: {metrics, trends, current_plan}）
            ctx = {"metrics": metrics, "trends": trend_ctx, "current_plan": None}
            # 4. 调用知识库规则引擎（db 由调用方传入）
            matches = await KnowledgeBaseService.match_rules(db, ctx)
            # 5. 渲染训练方案模板（field 取趋势值用于建议展示）
            for m in matches:
                if m.get("training_plan_template"):
                    plan = await KnowledgeBaseService.render_template(
                        db, m["training_plan_template"], metrics
                    )
                    ...
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
# R12-KB-1 补齐实现；R13-P3 文档同步: 与实际脚本一致——
# 幂等键：分类按 code、条目按 title+category_id、规则按 rule_id、模板按 template_code；
# 使用 async_session_factory（非 get_async_session）；输出 skipped 统计。
"""知识库初始化脚本（R12-KB-1 补齐）

依据：切片 13-infrastructure/knowledge_base.md §7 初始化脚本设计。
功能：内置 Python 数据常量并幂等写入 DB（已存在的记录跳过，禁止重复写入）。

用法: python scripts/init_knowledge_base.py
"""
import asyncio
import sys
from pathlib import Path

# 支持从项目根目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.models.knowledge_base import (  # noqa: E402
    KnowledgeCategory, KnowledgeEntry, RuleDefinition, TrainingTemplate,
)

# 8 大技术动作分类（种子数据与设计一致）
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

# 常见问题条目
PROBLEMS = [
    {"title": "反手使用率不足", "entry_type": "problem", "category_code": "backhand_drive",
     "content": {"description": "反手使用率低于 30%，过度依赖正手"}},
    {"title": "正手拉球弧线过高", "entry_type": "problem", "category_code": "loop",
     "content": {"description": "拉球弧线过高，容易被对手反冲"}},
]

# 规则定义（3 条种子规则，condition 含 aggregation 键 —— R2-KB-1）
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

# 训练方案模板（R13-P3 文档同步: 含 category/difficulty/description 字段，
# 与 training_template 表定义一致）
TEMPLATES = [
    {
        "template_code": "TPL_BACKHAND_IMPROVE",
        "name": "反手提升训练方案",
        "category": "backhand_drive",
        "difficulty": "intermediate",
        "description": "针对反手使用率不足的提升训练方案",
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
    """初始化知识库数据 — 幂等（已存在的记录跳过）。

    R13-P3 文档同步: 原文档样例问题条目缺幂等检查（直接 add），实际实现
    按 title + category_id 幂等；全部写入走 stats 统计 + skipped 计数。
    """
    async with async_session_factory() as db:
        stats = {"categories": 0, "entries": 0, "rules": 0, "templates": 0, "skipped": 0}

        # 1. 写入分类（按 code 幂等）
        for cat_data in CATEGORIES:
            existing = await db.scalar(
                select(KnowledgeCategory).where(
                    KnowledgeCategory.code == cat_data["code"]
                )
            )
            if not existing:
                db.add(KnowledgeCategory(**cat_data))
                stats["categories"] += 1
            else:
                stats["skipped"] += 1
        await db.flush()

        # 2. 写入问题条目（按 title + category_id 幂等，R12-KB-1）
        for prob_data in PROBLEMS:
            category_code = prob_data.pop("category_code")
            cat = await db.scalar(
                select(KnowledgeCategory).where(
                    KnowledgeCategory.code == category_code
                )
            )
            if not cat:
                continue
            existing = await db.scalar(
                select(KnowledgeEntry).where(
                    KnowledgeEntry.title == prob_data["title"],
                    KnowledgeEntry.category_id == cat.id,
                )
            )
            if not existing:
                db.add(KnowledgeEntry(category_id=cat.id, **prob_data))
                stats["entries"] += 1
            else:
                stats["skipped"] += 1

        # 3. 写入规则（按 rule_id 幂等）
        for rule_data in RULES:
            existing = await db.scalar(
                select(RuleDefinition).where(
                    RuleDefinition.rule_id == rule_data["rule_id"]
                )
            )
            if not existing:
                db.add(RuleDefinition(**rule_data))
                stats["rules"] += 1
            else:
                stats["skipped"] += 1

        # 4. 写入模板（按 template_code 幂等）
        for tpl_data in TEMPLATES:
            existing = await db.scalar(
                select(TrainingTemplate).where(
                    TrainingTemplate.template_code == tpl_data["template_code"]
                )
            )
            if not existing:
                db.add(TrainingTemplate(**tpl_data))
                stats["templates"] += 1
            else:
                stats["skipped"] += 1

        await db.commit()
        print(
            f"Knowledge base initialized: +{stats['categories']} categories, "
            f"+{stats['entries']} entries, +{stats['rules']} rules, "
            f"+{stats['templates']} templates (skipped {stats['skipped']} existing)"
        )
        return stats


if __name__ == "__main__":
    asyncio.run(init_knowledge_base())
```

---

## 8. 测试要点

```python
# tests/unit/test_knowledge_base.py
# R12-KB-6: 整文件补齐（22 个测试）。R13-P3 文档同步: 样例与实际测试一致——
# Service 调用带 db_session 参数、ctx 为 dict（非 RuleContext 对象）。
"""knowledge_base 模块测试。覆盖：规则引擎匹配（single/trend/stagnant/plan_effectiveness + 优先级）、
占位符渲染（递归 + {current_value}）、CRUD（分类/条目/规则/模板 + 404）、初始化脚本幂等。"""
import pytest

from app.models.knowledge_base import (
    KnowledgeCategory, KnowledgeEntry, RuleDefinition, TrainingTemplate,
)


async def _add_rule(db, rule_id, rule_type, condition, diagnosis, **kwargs):
    """种子规则辅助（flush 后返回 rule）。"""
    ...


# === 1. 规则引擎 — single 类型（4 个测试）===
@pytest.mark.asyncio
class TestRuleEngineSingle:
    async def test_single_lt_matched(self, db_session):
        """single 规则命中 + 占位符渲染（{current_value}/{threshold}，R2-KB-2）。"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_SINGLE_LT", "single",
            condition={"metric": "backhand_ratio", "operator": "<", "threshold": 0.30,
                       "aggregation": "single"},
            diagnosis={"problem_id": "P1", "problem_name": "反手不足",
                       "severity": "medium",
                       "suggestion_template": "当前 {current_value}，低于 {threshold}"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"backhand_ratio": 0.2}, "trends": {}}
        )
        assert results[0]["rule_id"] == "RULE_SINGLE_LT"
        assert "{current_value}" not in results[0]["suggestion"]
        assert "0.2" in results[0]["suggestion"]
        assert "0.3" in results[0]["suggestion"]

    # 另有 3 个测试：阈值不达（负对照）、ctx 缺指标、gt/gte/eq 运算符语义与边界


# === 2. 规则引擎 — trend/stagnant/plan_effectiveness/优先级（7 个测试）===
@pytest.mark.asyncio
class TestRuleEngineTrend:
    async def test_trend_improving_matched(self, db_session):
        """趋势改善规则命中（direction/persistence/change_rate 三条件齐备）。"""
        ...

    async def test_trend_persistence_below_threshold(self, db_session):
        """persistence 不足 → 不匹配（负对照）。"""
        ...

    async def test_trend_change_rate_below_threshold(self, db_session):
        """change_rate 不足 → 不匹配（负对照）。"""
        ...

    async def test_stagnant_matched(self, db_session):
        """停滞规则命中（R12-KB-3: min_persistence 条件键 + direction=stagnant）。"""
        ...

    async def test_plan_effectiveness_matched(self, db_session):
        """方案有效性规则命中（current_plan.goal_completion ≥ threshold，
        R13-P3 文档同步: 原文档缺失此规则类型测试）。"""
        ...

    async def test_inactive_rule_not_matched(self, db_session):
        """is_active=False 的规则不参与匹配。"""
        ...

    async def test_rule_type_priority_order(self, db_session):
        """规则类型优先级 single > trend_persistent > trend_improving > stagnant
        > plan_effectiveness（RULE_TYPE_ORDER 显式映射）。"""
        ...


# === 3. 模板渲染（2 个测试）===
@pytest.mark.asyncio
class TestTemplateRender:
    async def test_render_template_recursive(self, db_session):
        """递归填充 str/dict/list 占位符。"""
        ...

    async def test_render_template_not_found(self, db_session):
        """模板不存在 → 404。"""
        ...


# === 4. CRUD 查询（7 个测试）===
@pytest.mark.asyncio
class TestKnowledgeCRUD:
    # list_categories / get_category_by_code 404 / list_entries 筛（category_code+entry_type）/
    # get_entry_detail 404 / get_rules_by_problem JSONB 查询 / list_templates_by_problem /
    # list_rules is_active=False 筛选
    ...


# === 5. 初始化脚本幂等（2 个测试，R12-KB-1 回归）===
@pytest.mark.asyncio
class TestInitScriptIdempotency:
    async def test_init_idempotent_double_run(self, db_session):
        """init_knowledge_base() 双次执行：第二次全部 skipped、无重复写入。"""
        ...

    async def test_init_seeded_rules_matchable(self, db_session):
        """初始化后的种子规则可被规则引擎匹配（端到端）。"""
        ...
```

**R12 修复回归测试位置**（R13-P3 文档同步汇总）：
- KB-1（初始化脚本幂等）：本文件 TestInitScriptIdempotency
- KB-2（severity 取 diagnosis）：本文件各匹配测试断言 `results[0]["severity"]`
- KB-3（min_persistence 条件键）：本文件 test_stagnant_matched
- KB-6（22 个测试）：`tests/unit/test_knowledge_base.py` 全文件

---

## 9. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_knowledge_base.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.knowledge_base_smoke_test`
- [ ] 4 个 Model 已在 `app/models/__init__.py` 中导入
- [ ] 数据库迁移已生成并执行
- [ ] 初始化脚本可成功执行：`python scripts/init_knowledge_base.py`
- [ ] 8 大技术动作分类树正确存储和查询
- [ ] 规则引擎正确执行 5 类匹配（single / trend_persistent / trend_improving / stagnant / plan_effectiveness，R13-P3 文档同步）
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
- 规则匹配顺序 **必须** 为 single → trend_persistent → trend_improving → stagnant → plan_effectiveness（RULE_TYPE_ORDER 显式优先级映射，R13-P3 文档同步），**禁止** 随意调整顺序

> **覆盖度修复说明（A-3）**：已确认 `RuleDefinition` 和 `TrainingTemplate` 模型在 `knowledge_base` 切片 §3 中定义（`app/models/knowledge_base.py`），并添加归属说明注释。
> 其他模块（如 `training_advice`）通过 `from app.models.knowledge_base import RuleDefinition, TrainingTemplate` 引用，不重复定义。
