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

from app.core.exceptions import AppException
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
    async def get_category_by_code(db: AsyncSession, code: str) -> dict:
        row = await db.scalar(
            select(KnowledgeCategory).where(KnowledgeCategory.code == code)
        )
        if not row:
            raise AppException(f"分类 {code} 不存在", 404, code=40401)
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
    async def get_entry_detail(db: AsyncSession, entry_id: int) -> dict:
        row = await db.scalar(
            select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
        )
        if not row:
            raise AppException("知识条目不存在", 404, code=40402)
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
        """根据 problem_id 查询相关规则 — 使用 JSONB 路径查询（利用 GIN 索引）"""
        rows = await db.execute(
            select(RuleDefinition)
            .where(
                RuleDefinition.is_active == True,
                RuleDefinition.diagnosis["problem_id"].astext == problem_id,
            )
            .order_by(RuleDefinition.id)
        )
        results = []
        for r in rows.scalars().all():
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
    async def get_template_detail(db: AsyncSession, template_code: str) -> dict:
        row = await db.scalar(
            select(TrainingTemplate).where(TrainingTemplate.template_code == template_code)
        )
        if not row:
            raise AppException(f"模板 {template_code} 不存在", 404, code=40403)
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
                match_result = KnowledgeBaseService._evaluate_rule(rule, ctx)
                if match_result and match_result.get("matched"):
                    diag = rule.diagnosis or {}
                    # 用 suggestion_params 填充建议模板
                    suggestion_template = diag.get("suggestion_template", "")
                    suggestion = KnowledgeBaseService._fill_placeholders(suggestion_template, match_result.get("suggestion_params", {})) if suggestion_template else ""
                    results.append({
                        "rule_id": rule.rule_id,
                        "rule_name": rule.rule_name,
                        "rule_type": rule.rule_type,
                        "problem_id": diag.get("problem_id", ""),
                        "problem_name": diag.get("problem_name", ""),
                        # R12-KB-2: severity 取自 diagnosis JSONB（设计规定 severity 是
                        # 诊断结论属性），不再从 condition 读取（原先恒为 medium 兜底）
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
        """评估单条规则是否匹配 — 返回 MatchResult dict 或 None

        MatchResult 包含：matched=True + severity + suggestion_params（从 ctx 提取供模板渲染）
        """
        cond = rule.condition or {}
        metrics = ctx.get("metrics", {})
        trends = ctx.get("trends", {})
        # R2-KB-1: 从 condition JSONB 的 aggregation 键读取规则类型，而非 rule.rule_type 列
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
                suggestion_params.update({"metric": metric, "current_value": value, "threshold": threshold})
                return {"matched": True, "severity": cond.get("severity", "medium"), "suggestion_params": suggestion_params}
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
                "metric": metric,
                "direction": actual_direction,
                "persistence": persistence,
                "change_rate": change_rate,
            })
            return {"matched": True, "severity": cond.get("severity", "medium"), "suggestion_params": suggestion_params}

        elif rule_type == "stagnant":
            metric = cond.get("metric")
            # R12-KB-3: 条件键统一为 min_persistence（设计 §知识库规则评估），
            # 原先误用 min_stagnation 导致设计种子规则条件键不生效
            min_persistence = cond.get("min_persistence", 1)
            trend_info = trends.get(metric, {})
            if trend_info.get("persistence", 0) >= min_persistence and trend_info.get("direction") == "stagnant":
                suggestion_params.update({"metric": metric, "persistence": trend_info.get("persistence", 0)})
                return {"matched": True, "severity": cond.get("severity", "medium"), "suggestion_params": suggestion_params}
            return None

        elif rule_type == "plan_effectiveness":
            current_plan = ctx.get("current_plan")
            if not current_plan:
                return None
            goal_completion = current_plan.get("goal_completion", {})
            metric = cond.get("metric")
            threshold = cond.get("threshold", 0.8)
            value = goal_completion.get(metric, 0)
            if value >= threshold:
                suggestion_params.update({"metric": metric, "completion": value, "threshold": threshold})
                return {"matched": True, "severity": cond.get("severity", "medium"), "suggestion_params": suggestion_params}
            return None

        return None

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
            return abs(value - threshold) < 0.001
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
