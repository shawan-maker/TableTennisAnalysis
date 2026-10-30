"""
tests/unit/test_knowledge_base.py — knowledge_base 模块单元测试

R12-KB-6: 整文件补齐（round12 测试缺口）。
依据：切片 13-infrastructure/knowledge_base.md §8 测试要点
覆盖：规则引擎匹配（single/trend/stagnant/plan_effectiveness + 优先级）、
      占位符渲染（递归 + {current_value}）、CRUD（分类/条目/规则/模板 + 404）、
      初始化脚本幂等（R12-KB-1 回归）
"""

import pytest

from app.models.knowledge_base import (
    KnowledgeCategory,
    KnowledgeEntry,
    RuleDefinition,
    TrainingTemplate,
)


# =============================================================================
# 辅助：种子规则
# =============================================================================

async def _add_rule(db, rule_id, rule_type, condition, diagnosis, *,
                    rule_name=None, adjustment_action=None,
                    training_plan_template=None, training_methods=None,
                    is_active=True):
    rule = RuleDefinition(
        rule_id=rule_id,
        rule_name=rule_name or f"规则{rule_id}",
        rule_type=rule_type,
        condition=condition,
        diagnosis=diagnosis,
        training_methods=training_methods,
        training_plan_template=training_plan_template,
        adjustment_action=adjustment_action,
        is_active=is_active,
    )
    db.add(rule)
    await db.flush()
    return rule


async def _add_category(db, name, code, content=None):
    cat = KnowledgeCategory(name=name, code=code, content=content or {"subcategories": []})
    db.add(cat)
    await db.flush()
    return cat


# =============================================================================
# 规则引擎 — single 类型
# =============================================================================

@pytest.mark.asyncio
class TestRuleEngineSingle:
    """single 规则匹配：operator 比较 + 阈值边界"""

    async def test_single_lt_matched(self, db_session):
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
        assert len(results) == 1
        assert results[0]["rule_id"] == "RULE_SINGLE_LT"
        assert results[0]["problem_id"] == "P1"
        # 占位符已渲染（R2-KB-2: {current_value} 而非 {value}）
        assert "{current_value}" not in results[0]["suggestion"]
        assert "0.2" in results[0]["suggestion"]
        assert "0.3" in results[0]["suggestion"]

    async def test_single_threshold_not_reached(self, db_session):
        """指标不满足阈值 → 不匹配（负对照）"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_SINGLE_NEG", "single",
            condition={"metric": "backhand_ratio", "operator": "<", "threshold": 0.30,
                       "aggregation": "single"},
            diagnosis={"problem_id": "P1", "problem_name": "反手不足",
                       "severity": "medium", "suggestion_template": "模板"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"backhand_ratio": 0.35}, "trends": {}}
        )
        assert len(results) == 0

    async def test_single_metric_missing_in_ctx(self, db_session):
        """ctx 中无该指标 → 不匹配"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_SINGLE_MISS", "single",
            condition={"metric": "avg_ball_speed", "operator": ">", "threshold": 20,
                       "aggregation": "single"},
            diagnosis={"problem_id": "P2", "problem_name": "球速",
                       "severity": "low", "suggestion_template": "模板"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"backhand_ratio": 0.2}, "trends": {}}
        )
        assert len(results) == 0

    async def test_single_operators(self, db_session):
        """gt/gte/eq 运算符语义"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_GT", "single",
            condition={"metric": "forehand_ratio", "operator": ">", "threshold": 0.5,
                       "aggregation": "single"},
            diagnosis={"problem_id": "P3", "problem_name": "正手过度",
                       "severity": "high", "suggestion_template": "模板"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"forehand_ratio": 0.6}, "trends": {}}
        )
        assert len(results) == 1
        # 边界：恰好等于不匹配
        results_eq = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"forehand_ratio": 0.5}, "trends": {}}
        )
        assert len(results_eq) == 0


# =============================================================================
# 规则引擎 — trend 类型（improving/stagnant/persistent）
# =============================================================================

@pytest.mark.asyncio
class TestRuleEngineTrend:
    """趋势规则匹配：direction + persistence + change_rate"""

    async def test_trend_improving_matched(self, db_session):
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_TREND_IMP", "trend_improving",
            condition={"metric": "backhand_ratio", "direction": "improving",
                       "min_persistence": 2, "min_change_rate": 0.05,
                       "aggregation": "trend_improving"},
            diagnosis={"problem_id": "P4", "problem_name": "改善中",
                       "severity": "low",
                       "suggestion_template": "持续改善 {change_rate}"},
            adjustment_action="maintain",
        )
        results = await KnowledgeBaseService.match_rules(
            db_session,
            {
                "metrics": {},
                "trends": {"backhand_ratio": {"direction": "improving",
                                               "persistence": 3, "change_rate": 0.08}},
            },
        )
        assert len(results) == 1
        assert results[0]["rule_type"] == "trend_improving"
        assert results[0]["adjustment_action"] == "maintain"

    async def test_trend_persistence_below_threshold(self, db_session):
        """persistence 不足 → 不匹配"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_TREND_P1", "trend_improving",
            condition={"metric": "backhand_ratio", "direction": "improving",
                       "min_persistence": 3, "min_change_rate": 0.05,
                       "aggregation": "trend_improving"},
            diagnosis={"problem_id": "P4", "problem_name": "改善中",
                       "severity": "low", "suggestion_template": "模板"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session,
            {
                "metrics": {},
                "trends": {"backhand_ratio": {"direction": "improving",
                                               "persistence": 2, "change_rate": 0.08}},
            },
        )
        assert len(results) == 0

    async def test_trend_change_rate_below_threshold(self, db_session):
        """|change_rate| < min_change_rate → 不匹配"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_TREND_CR", "trend_improving",
            condition={"metric": "backhand_ratio", "direction": "improving",
                       "min_persistence": 2, "min_change_rate": 0.05,
                       "aggregation": "trend_improving"},
            diagnosis={"problem_id": "P4", "problem_name": "改善中",
                       "severity": "low", "suggestion_template": "模板"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session,
            {
                "metrics": {},
                "trends": {"backhand_ratio": {"direction": "improving",
                                               "persistence": 3, "change_rate": 0.01}},
            },
        )
        assert len(results) == 0

    async def test_stagnant_matched(self, db_session):
        """R12-KB-3 回归：stagnant 规则条件键为 min_persistence（非 min_stagnation）"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_STAG", "stagnant",
            condition={"metric": "backhand_ratio", "direction": "stagnant",
                       "min_persistence": 3, "aggregation": "stagnant"},
            diagnosis={"problem_id": "P5", "problem_name": "停滞",
                       "severity": "high", "suggestion_template": "调整方案"},
            adjustment_action="adjust",
        )
        results = await KnowledgeBaseService.match_rules(
            db_session,
            {
                "metrics": {},
                "trends": {"backhand_ratio": {"direction": "stagnant", "persistence": 3}},
            },
        )
        assert len(results) == 1
        assert results[0]["adjustment_action"] == "adjust"
        # direction 不符 → 不匹配
        results_neg = await KnowledgeBaseService.match_rules(
            db_session,
            {
                "metrics": {},
                "trends": {"backhand_ratio": {"direction": "improving", "persistence": 5}},
            },
        )
        assert len(results_neg) == 0

    async def test_plan_effectiveness_matched(self, db_session):
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_PLAN", "plan_effectiveness",
            condition={"metric": "backhand_ratio", "threshold": 0.8,
                       "aggregation": "plan_effectiveness"},
            diagnosis={"problem_id": "P6", "problem_name": "方案有效",
                       "severity": "low", "suggestion_template": "维持方案"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session,
            {"metrics": {}, "trends": {},
             "current_plan": {"goal_completion": {"backhand_ratio": 0.9}}},
        )
        assert len(results) == 1
        # 无 current_plan → 不匹配
        results_neg = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {}, "trends": {}}
        )
        assert len(results_neg) == 0

    async def test_inactive_rule_not_matched(self, db_session):
        """is_active=False 的规则不参与匹配"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_DISABLED", "single",
            condition={"metric": "backhand_ratio", "operator": "<", "threshold": 0.30,
                       "aggregation": "single"},
            diagnosis={"problem_id": "P1", "problem_name": "反手",
                       "severity": "medium", "suggestion_template": "模板"},
            is_active=False,
        )
        results = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"backhand_ratio": 0.1}, "trends": {}}
        )
        assert len(results) == 0

    async def test_rule_type_priority_order(self, db_session):
        """规则类型优先级：single 结果先于 trend 先于 stagnant（RULE_TYPE_ORDER）"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_PRI_STAG", "stagnant",
            condition={"metric": "backhand_ratio", "direction": "stagnant",
                       "min_persistence": 1, "aggregation": "stagnant"},
            diagnosis={"problem_id": "P5", "problem_name": "停滞",
                       "severity": "high", "suggestion_template": "停滞"},
        )
        await _add_rule(
            db_session, "RULE_PRI_SINGLE", "single",
            condition={"metric": "backhand_ratio", "operator": "<", "threshold": 0.30,
                       "aggregation": "single"},
            diagnosis={"problem_id": "P1", "problem_name": "反手",
                       "severity": "medium", "suggestion_template": "反手"},
        )
        results = await KnowledgeBaseService.match_rules(
            db_session,
            {
                "metrics": {"backhand_ratio": 0.2},
                "trends": {"backhand_ratio": {"direction": "stagnant", "persistence": 2}},
            },
        )
        assert len(results) == 2
        # single 优先输出
        assert results[0]["rule_id"] == "RULE_PRI_SINGLE"
        assert results[1]["rule_id"] == "RULE_PRI_STAG"


# =============================================================================
# 占位符渲染
# =============================================================================

@pytest.mark.asyncio
class TestTemplateRender:
    """模板参数化：递归占位符填充"""

    async def _add_template(self, db, code, template_data):
        tpl = TrainingTemplate(
            template_code=code, name=f"模板{code}", category="loop",
            difficulty="intermediate", template_data=template_data,
        )
        db.add(tpl)
        await db.flush()
        return tpl

    async def test_render_template_recursive(self, db_session):
        """嵌套 dict/list 中占位符递归填充"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await self._add_template(
            db_session, "TPL_RENDER",
            {
                "goal": {"metric": "backhand_ratio", "target": "{target}"},
                "sessions": [{"name": "{session_name}", "reps": 50}],
                "note": "当前 {backhand_ratio}",
            },
        )
        rendered = await KnowledgeBaseService.render_template(
            db_session, "TPL_RENDER",
            {"target": 0.35, "session_name": "反手多球", "backhand_ratio": 0.2},
        )
        assert rendered["goal"]["target"] == "0.35"
        assert rendered["sessions"][0]["name"] == "反手多球"
        assert rendered["note"] == "当前 0.2"

    async def test_render_template_not_found(self, db_session):
        """模板不存在 → render_template 与 get_template_detail 均抛 404"""
        import pytest as _pytest

        from app.core.exceptions import AppException
        from app.services.knowledge_base_service import KnowledgeBaseService

        with _pytest.raises(AppException) as render_exc:
            await KnowledgeBaseService.render_template(db_session, "TPL_NOT_EXIST", {})
        assert render_exc.value.status_code == 404

        with _pytest.raises(AppException) as exc:
            await KnowledgeBaseService.get_template_detail(db_session, "TPL_NOT_EXIST")
        assert exc.value.status_code == 404


# =============================================================================
# CRUD 查询
# =============================================================================

@pytest.mark.asyncio
class TestKnowledgeCRUD:
    """分类/条目/规则/模板查询 + 404"""

    async def test_list_categories(self, db_session):
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_category(db_session, "正手攻球", "forehand_drive")
        await _add_category(db_session, "反手攻球", "backhand_drive")

        cats = await KnowledgeBaseService.list_categories(db_session)
        assert len(cats) == 2
        assert {c["code"] for c in cats} == {"forehand_drive", "backhand_drive"}

    async def test_get_category_by_code_404(self, db_session):
        import pytest as _pytest

        from app.core.exceptions import AppException
        from app.services.knowledge_base_service import KnowledgeBaseService

        with _pytest.raises(AppException) as exc:
            await KnowledgeBaseService.get_category_by_code(db_session, "not_exist")
        assert exc.value.status_code == 404

    async def test_list_entries_filter(self, db_session):
        """按分类筛选条目"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        cat1 = await _add_category(db_session, "反手攻球", "backhand_drive")
        cat2 = await _add_category(db_session, "拉球", "loop")

        db_session.add(KnowledgeEntry(
            category_id=cat1.id, title="反手问题A", entry_type="problem",
            content={"description": "d"},
        ))
        db_session.add(KnowledgeEntry(
            category_id=cat2.id, title="拉球方法B", entry_type="method",
            content={"description": "d"},
        ))
        await db_session.flush()

        all_entries = await KnowledgeBaseService.list_entries(db_session)
        assert len(all_entries) == 2
        backhand = await KnowledgeBaseService.list_entries(
            db_session, category_code="backhand_drive"
        )
        assert len(backhand) == 1
        assert backhand[0]["title"] == "反手问题A"
        methods = await KnowledgeBaseService.list_entries(
            db_session, entry_type="method"
        )
        assert len(methods) == 1

    async def test_get_entry_detail_404(self, db_session):
        import pytest as _pytest

        from app.core.exceptions import AppException
        from app.services.knowledge_base_service import KnowledgeBaseService

        with _pytest.raises(AppException) as exc:
            await KnowledgeBaseService.get_entry_detail(db_session, 99999)
        assert exc.value.status_code == 404

    async def test_get_rules_by_problem_jsonb_query(self, db_session):
        """按 diagnosis.problem_id JSONB 路径查询（利用 GIN 索引）"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_BY_PROB", "single",
            condition={"metric": "x", "operator": "<", "threshold": 1,
                       "aggregation": "single"},
            diagnosis={"problem_id": "PROB_X", "problem_name": "问题X",
                       "severity": "medium", "suggestion_template": "模板"},
        )
        rules = await KnowledgeBaseService.get_rules_by_problem(db_session, "PROB_X")
        assert len(rules) == 1
        assert rules[0]["rule_id"] == "RULE_BY_PROB"
        assert rules[0]["diagnosis"]["problem_id"] == "PROB_X"

        empty = await KnowledgeBaseService.get_rules_by_problem(db_session, "PROB_NONE")
        assert empty == []

    async def test_list_templates_by_problem(self, db_session):
        from app.services.knowledge_base_service import KnowledgeBaseService

        db_session.add(TrainingTemplate(
            template_code="TPL_A", name="模板A", category="loop",
            difficulty="intermediate", problem_id="PROB_A", template_data={},
        ))
        db_session.add(TrainingTemplate(
            template_code="TPL_B", name="模板B", category="loop",
            difficulty="intermediate", problem_id="PROB_B", template_data={},
        ))
        await db_session.flush()

        tpls = await KnowledgeBaseService.list_templates(db_session, problem_id="PROB_A")
        assert len(tpls) == 1
        assert tpls[0]["template_code"] == "TPL_A"

    async def test_list_rules_filter_inactive(self, db_session):
        from app.services.knowledge_base_service import KnowledgeBaseService

        await _add_rule(
            db_session, "RULE_ACTIVE", "single",
            condition={"metric": "x", "operator": "<", "threshold": 1,
                       "aggregation": "single"},
            diagnosis={"problem_id": "P", "problem_name": "p",
                       "severity": "medium", "suggestion_template": "t"},
            is_active=True,
        )
        await _add_rule(
            db_session, "RULE_INACTIVE", "single",
            condition={"metric": "x", "operator": "<", "threshold": 1,
                       "aggregation": "single"},
            diagnosis={"problem_id": "P", "problem_name": "p",
                       "severity": "medium", "suggestion_template": "t"},
            is_active=False,
        )
        active = await KnowledgeBaseService.list_rules(db_session, is_active=True)
        assert {r["rule_id"] for r in active} == {"RULE_ACTIVE"}
        inactive = await KnowledgeBaseService.list_rules(db_session, is_active=False)
        assert {r["rule_id"] for r in inactive} == {"RULE_INACTIVE"}


# =============================================================================
# 初始化脚本幂等（R12-KB-1 回归）
# =============================================================================

@pytest.mark.asyncio
class TestInitScriptIdempotency:
    """scripts/init_knowledge_base.py 幂等灌入 — 重复执行不重复写入"""

    async def _run_init(self):
        import importlib
        import sys

        mod_path = "scripts.init_knowledge_base"
        if mod_path in sys.modules:
            del sys.modules[mod_path]
        mod = importlib.import_module(mod_path)
        return await mod.init_knowledge_base()

    async def test_init_idempotent_double_run(self, db_session):
        """连续执行两次：第一次全量灌入，第二次全部跳过"""
        from sqlalchemy import func, select

        stats1 = await self._run_init()
        assert stats1["categories"] == 8
        assert stats1["rules"] == 3
        assert stats1["templates"] == 1
        assert stats1["entries"] == 2

        stats2 = await self._run_init()
        assert stats2["categories"] == 0
        assert stats2["entries"] == 0
        assert stats2["rules"] == 0
        assert stats2["templates"] == 0
        assert stats2["skipped"] == 14  # 8 分类 + 2 条目 + 3 规则 + 1 模板

        # DB 计数不翻倍
        cat_count = await db_session.scalar(select(func.count()).select_from(KnowledgeCategory))
        rule_count = await db_session.scalar(select(func.count()).select_from(RuleDefinition))
        entry_count = await db_session.scalar(select(func.count()).select_from(KnowledgeEntry))
        tpl_count = await db_session.scalar(select(func.count()).select_from(TrainingTemplate))
        assert cat_count == 8
        assert rule_count == 3
        assert entry_count == 2
        assert tpl_count == 1

    async def test_init_seeded_rules_matchable(self, db_session):
        """灌入后的种子规则可被规则引擎命中（RULE_001 backhand_ratio < 0.30）"""
        from app.services.knowledge_base_service import KnowledgeBaseService

        await self._run_init()
        results = await KnowledgeBaseService.match_rules(
            db_session, {"metrics": {"backhand_ratio": 0.2}, "trends": {}}
        )
        assert any(r["rule_id"] == "RULE_001" for r in results)
