"""
app/services/knowledge_base_service.py - 知识库业务逻辑层

依据：切片 13-infrastructure/knowledge_base.md 5
功能：分类/条目/规则/模板查询 + 规则引擎匹配 + 模板参数化
无独立 Router，被 training_advice 和 admin 调用
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import (
    KnowledgeCategory,
    KnowledgeEntry,
    RuleDefinition,
    TrainingTemplate,
)

logger = logging.getLogger(__name__)

# 规则类型优先级：single > trend > stagnant
RULE_TYPE_ORDER = {
    "single": 1,
    "trend_persistent": 2,
    "trend_improving": 3,
    "stagnant": 4,
    "plan_effectiveness": 5,
}


class KnowledgeBaseService:
    """知识库业务逻辑层"""

    @staticmethod
    async def list_categories(db: AsyncSession) -> list[dict]:
        rows = await db.execute(
            select(KnowledgeCategory).order_by(KnowledgeCategory.id)
        )
        return [
            {"id": r.id, "name": r.name, "code": r.code}
            for r in rows.scalars().all()
        ]

    @staticmethod
    async def get_category_by_code(db: AsyncSession, code: str) -> Optional[dict]:
        row = await db.scalar(
            select(KnowledgeCategory).where(KnowledgeCategory.code == code)
        )
        if not row:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "code": row.code,
            "content": row.content,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    async def list_entries(
        db: AsyncSession, category_code: Optional[str] = None, entry_type: Optional[str] = None
    ) -> list[dict]:
        qs = select(KnowledgeEntry)
        if category_code:
            qs = qs.join(KnowledgeCategory).where(KnowledgeCategory.code == category_code)
        if entry_type:
            qs = qs.where(KnowledgeEntry.entry_type == entry_type)
        rows = await db.execute(qs.order_by(KnowledgeEntry.id))
        return [
            {"id": r.id, "category_id": r.category_id, "title": r.title, "entry_type": r.entry_type}
            for r in rows.scalars().all()
        ]

    @staticmethod
    async def get_entry_detail(db: AsyncSession, entry_id: int) -> Optional[dict]:
        row = await db.scalar(
            select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
        )
        if not row:
            return None
        return {
            "id": row.id,
            "category_id": row.category_id,
            "title": row.title,
            "entry_type": row.entry_type,
            "content": row.content,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    async def list_rules(
        db: AsyncSession, rule_type: Optional[str] = None, is_active: bool = True
    ) -> list[dict]:
        qs = select(RuleDefinition).where(RuleDefinition.is_active == is_active)
        if rule_type:
            qs = qs.where(RuleDefinition.rule_type == rule_type)
        rows = await db.execute(qs.order_by(RuleDefinition.id))
        return [
            {
                "id": r.id,
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "rule_type": r.rule_type,
                "is_active": r.is_active,
            }
            for r in rows.scalars().all()
        ]

    @staticmethod
    async def get_rules_by_problem(db: AsyncSession, problem_id: str) -> list[dict]:
        """根据 problem_id 查询相关规则"""
        rows = await db.execute(
            select(RuleDefinition)
            .where(RuleDefinition.is_active == True)
            .order_by(RuleDefinition.id)
        )
        results = []
        for r in rows.scalars().all():
            diag = r.diagnosis or {}
            if diag.get("problem_id") == problem_id:
                results.append({
                    "id": r.id,
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "rule_type": r.rule_type,
                    "is_active": r.is_active,
                    "condition": r.condition,
                    "diagnosis": r.diagnosis,
                    "training_methods": r.training_methods,
                    "training_plan_template": r.training_plan_template,
                    "adjustment_action": r.adjustment_action,
                })
        return results

    @staticmethod
    async def list_templates(
        db: AsyncSession, problem_id: Optional[str] = None
    ) -> list[dict]:
        qs = select(TrainingTemplate)
        if problem_id:
            qs = qs.where(TrainingTemplate.problem_id == problem_id)
        rows = await db.execute(qs.order_by(TrainingTemplate.id))
        return [
            {
                "id": r.id,
                "template_code": r.template_code,
                "name": r.name,
                "problem_id": r.problem_id,
            }
            for r in rows.scalars().all()
        ]

    @staticmethod
    async def get_template_detail(db: AsyncSession, template_code: str) -> Optional[dict]:
        row = await db.scalar(
            select(TrainingTemplate).where(TrainingTemplate.template_code == template_code)
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
    async def match_rules(db: AsyncSession, ctx: dict) -> list[dict]:
        """规则引擎匹配 - 核心方法

        ctx: {metrics: {k: v}, trends: {k: {direction, persistence, change_rate}}, current_plan: Optional[dict]}
        按规则类型顺序匹配：single > trend_persistent/trend_improving > stagnant
        """
        rows = await db.execute(
            select(RuleDefinition)
            .where(RuleDefinition.is_active == True)
            .order_by(RuleDefinition.id)
        )
        all_rules = rows.scalars().all()

        # 按规则类型排序
        sorted_rules = sorted(all_rules, key=lambda r: RULE_TYPE_ORDER.get(r.rule_type, 99))

        results = []
        for rule in sorted_rules:
            try:
                match = KnowledgeBaseService._evaluate_rule(rule, ctx)
                if match:
                    diag = rule.diagnosis or {}
                    results.append({
                        "rule_id": rule.rule_id,
                        "rule_name": rule.rule_name,
                        "rule_type": rule.rule_type,
                        "problem_id": diag.get("problem_id", ""),
                        "problem_name": diag.get("problem_name", ""),
                        "severity": diag.get("severity", "medium"),
                        "suggestion": diag.get("suggestion_template", ""),
                        "adjustment_action": rule.adjustment_action,
                        "training_methods": rule.training_methods,
                        "training_plan_template": rule.training_plan_template,
                    })
            except Exception as e:
                logger.warning("rule_eval_failed", extra={"rule_id": rule.rule_id, "error": str(e)})
                continue

        return results

    @staticmethod
    def _evaluate_rule(rule, ctx: dict) -> bool:
        """评估单条规则是否匹配"""
        cond = rule.condition or {}
        metrics = ctx.get("metrics", {})
        trends = ctx.get("trends", {})
        rule_type = rule.rule_type

        if rule_type == "single":
            # 单次指标阈值比较：{metric, operator, threshold}
            metric = cond.get("metric")
            operator = cond.get("operator", "<")
            threshold = cond.get("threshold")
            value = metrics.get(metric)
            if value is None:
                return False
            return KnowledgeBaseService._compare(value, operator, threshold)

        elif rule_type in ("trend_persistent", "trend_improving"):
            # 趋势类规则：检查 trend direction + persistence
            metric = cond.get("metric")
            direction = cond.get("direction")  # improving/declining/stagnant
            min_persistence = cond.get("min_persistence", 2)
            trend_info = trends.get(metric, {})
            actual_direction = trend_info.get("direction", "")
            persistence = trend_info.get("persistence", 0)
            if direction and actual_direction != direction:
                return False
            if persistence < min_persistence:
                return False
            return True

        elif rule_type == "stagnant":
            # 停滞规则：连续N次变化率<5%
            metric = cond.get("metric")
            min_stagnation = cond.get("min_stagnation", 3)
            trend_info = trends.get(metric, {})
            return trend_info.get("persistence", 0) >= min_stagnation and trend_info.get("direction") == "stagnant"

        elif rule_type == "plan_effectiveness":
            # 方案效果规则：检查 current_plan 的 goal_completion
            current_plan = ctx.get("current_plan")
            if not current_plan:
                return False
            goal_completion = current_plan.get("goal_completion", {})
            metric = cond.get("metric")
            threshold = cond.get("threshold", 0.8)
            value = goal_completion.get(metric, 0)
            return value >= threshold

        return False

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        """比较运算符"""
        if operator in ("<", "lt"):
            return value < threshold
        elif operator in ("<=", "lte"):
            return value <= threshold
        elif operator in (">", "gt"):
            return value > threshold
        elif operator in (">=", "gte"):
            return value >= threshold
        elif operator in ("==", "eq"):
            return value == threshold
        return False

    @staticmethod
    async def render_template(db: AsyncSession, template_code: str, metrics: dict) -> dict:
        """模板参数化 - 用指标值填充占位符"""
        detail = await KnowledgeBaseService.get_template_detail(db, template_code)
        if not detail:
            return {}
        return KnowledgeBaseService._fill_placeholders(detail["template_data"], metrics)

    @staticmethod
    def _fill_placeholders(data: Any, metrics: dict) -> Any:
        """递归填充 {metric_name} 占位符"""
        if isinstance(data, str):
            for key, value in metrics.items():
                data = data.replace("{" + key + "}", str(value))
            return data
        elif isinstance(data, dict):
            return {k: KnowledgeBaseService._fill_placeholders(v, metrics) for k, v in data.items()}
        elif isinstance(data, list):
            return [KnowledgeBaseService._fill_placeholders(item, metrics) for item in data]
        return data
