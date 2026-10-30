"""
scripts/init_knowledge_base.py — 知识库初始化脚本（R12-KB-1 补齐）

依据：切片 13-infrastructure/knowledge_base.md §7 初始化脚本设计。
功能：解析知识库定义数据并幂等写入 DB（已存在的记录跳过，禁止重复写入）。

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
    KnowledgeCategory,
    KnowledgeEntry,
    RuleDefinition,
    TrainingTemplate,
)

# 8 大技术动作分类（设计 knowledge_base.md §7 CATEGORIES）
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

# 常见问题条目（设计 knowledge_base.md §7 PROBLEMS）
PROBLEMS = [
    {"title": "反手使用率不足", "entry_type": "problem", "category_code": "backhand_drive",
     "content": {"description": "反手使用率低于 30%，过度依赖正手"}},
    {"title": "正手拉球弧线过高", "entry_type": "problem", "category_code": "loop",
     "content": {"description": "拉球弧线过高，容易被对手反冲"}},
]

# 规则定义（设计 knowledge_base.md §7 RULES）
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

# 训练方案模板（设计 knowledge_base.md §7 TEMPLATES）
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
    """初始化知识库数据 — 幂等（已存在的记录跳过）。"""
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

        # 2. 写入问题条目（按 title + category 幂等）
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
