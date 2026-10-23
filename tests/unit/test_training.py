"""
tests/unit/test_training.py - 训练建议模块单元测试

覆盖：训练建议生成、综合建议、模板列表、模板详情、方案调整历史、重新评估、训练单列表/完成
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from app.core.database import async_session_factory
from app.models.knowledge_base import KnowledgeCategory, KnowledgeEntry, RuleDefinition, TrainingTemplate
from app.models.membership import Subscription
from app.models.training import TrainingPlan
from app.models.user import User
from app.models.video_analysis import AnalysisReport, VideoTask, FileRecord
from app.services.training_service import TrainingAdviceService


@pytest_asyncio.fixture(scope="function")
async def member_sub(db_session, auth_user):
    """为测试用户创建有效会员订阅（训练端点需要 require_membership）"""
    sub = Subscription(
        user_id=auth_user["user_id"],
        tier="member",
        status="active",
        start_at=datetime.now(timezone.utc),
        expire_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()
    return sub


async def _seed_knowledge_base(db):
    """初始化知识库数据"""
    # 分类
    cat = KnowledgeCategory(name="反手技术", code="backhand_drive", content={"description": "反手技术"})
    db.add(cat)
    await db.flush()

    # 条目
    entry = KnowledgeEntry(
        category_id=cat.id, title="反手推球", content={"description": "基础反手"},
        entry_type="method",
    )
    db.add(entry)

    # 规则
    rule1 = RuleDefinition(
        rule_id="RULE_001", rule_name="反手使用率偏低", rule_type="single",
        condition={"metric": "backhand_ratio", "operator": "<", "threshold": 0.30},
        diagnosis={"problem_id": "P001", "problem_name": "反手使用率偏低", "severity": "medium", "suggestion_template": "建议增加反手练习"},
        training_methods=["METHOD_001"],
        training_plan_template="TPL_BACKHAND_IMPROVE",
        adjustment_action="adjust",
        is_active=True,
    )
    db.add(rule1)

    rule2 = RuleDefinition(
        rule_id="RULE_TREND_001", rule_name="反手趋势改善", rule_type="trend_improving",
        condition={"metric": "backhand_ratio", "direction": "improving", "min_persistence": 2},
        diagnosis={"problem_id": "P001", "problem_name": "反手使用率偏低", "severity": "low", "suggestion_template": "反手使用率正在改善"},
        training_methods=None,
        training_plan_template=None,
        adjustment_action="maintain",
        is_active=True,
    )
    db.add(rule2)

    # 模板
    tpl = TrainingTemplate(
        template_code="TPL_BACKHAND_IMPROVE", name="反手提升训练", category="backhand_drive",
        difficulty="intermediate", problem_id="P001",
        template_data={
            "goal": {"backhand_ratio": 0.35},
            "sessions": [
                {"name": "反手推球", "reps": 50},
                {"name": "反手拉球", "reps": 30},
            ],
            "exercises": [],
            "metrics": ["backhand_ratio"],
        },
        template_config={},
    )
    db.add(tpl)
    await db.flush()
    return {"category": cat, "template": tpl, "rules": [rule1, rule2]}


async def _create_report(db, user_id, idx=0, result_data=None):
    """创建分析报告"""
    if result_data is None:
        result_data = {
            "technique_stats": {"forehand_drive": 50, "backhand_drive": 15, "serve": 10},
            "landing_points": {"distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07}},
            "metrics": {"landing_forehand_pct": 0.68, "landing_backhand_pct": 0.25, "landing_middle_pct": 0.07},
            "rally_analysis": {"avg_rally_length": 5.5, "max_rally_length": 12},
            "ball_speed": {"avg_speed_mps": 18.5, "max_speed_mps": 24.0},
            "score_analysis": {"win_rate": 0.55, "key_point_win_rate": 0.50},
        }

    file_record = FileRecord(
        user_id=user_id, oss_key=f"test/key{idx}", file_size=1048576, file_type="mp4", status="uploaded"
    )
    db.add(file_record)
    await db.flush()

    task = VideoTask(
        user_id=user_id, file_id=file_record.id, oss_key=f"test/key{idx}",
        status="completed", task_uuid=f"test-training-{idx}", progress=100
    )
    db.add(task)
    await db.flush()

    report = AnalysisReport(
        task_id=task.id, user_id=user_id,
        result_data=result_data,
        report_text={
            "summary": f"报告{idx}",
            "issues": [{"problem_id": "P001", "problem_name": "反手偏低"}],
            "suggestions": ["增加反手练习"],
        },
        is_llm_generated=False,
    )
    db.add(report)
    await db.flush()
    return report


async def _create_plan(db, user_id):
    """创建训练方案"""
    plan = TrainingPlan(
        user_id=user_id,
        status="active",
        version=1,
        plan_data={
            "goal": {"backhand_ratio": 0.35},
            "sessions": [
                {"id": 1, "name": "反手推球", "reps": 50, "status": "pending"},
                {"id": 2, "name": "反手拉球", "reps": 30, "status": "pending"},
            ],
        },
        goal_metrics={"backhand_ratio": 0.35},
    )
    db.add(plan)
    await db.flush()
    return plan


# =============================================================================
# 训练建议
# =============================================================================

@pytest.mark.asyncio
async def test_get_advice_by_report(client, auth_headers, auth_user, db_session, member_sub):
    """基于报告的训练建议"""
    await _seed_knowledge_base(db_session)
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.get(f"/api/v1/training/advice/{report.id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["report_id"] == report.id
    assert data["is_first_analysis"] is True
    assert len(data["diagnosis"]) >= 1
    assert len(data["suggestions"]) >= 1
    assert data["suggestions"][0]["type"] == "first_analysis"


@pytest.mark.asyncio
async def test_get_advice_report_not_found(client, auth_headers, member_sub):
    """不存在的报告返回 404"""
    resp = await client.get("/api/v1/training/advice/99999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_contextual_advice(client, auth_headers, auth_user, db_session, member_sub):
    """综合训练建议（自动使用最新报告）"""
    await _seed_knowledge_base(db_session)
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.get("/api/v1/training/advice/contextual", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["report_id"] == report.id


@pytest.mark.asyncio
async def test_get_contextual_advice_no_report(client, auth_headers, member_sub):
    """无报告时返回 404"""
    resp = await client.get("/api/v1/training/advice/contextual", headers=auth_headers)
    assert resp.status_code == 404


# =============================================================================
# 模板列表
# =============================================================================

@pytest.mark.asyncio
async def test_get_templates(client, auth_headers, auth_user, db_session, member_sub):
    """模板列表"""
    await _seed_knowledge_base(db_session)
    await db_session.commit()

    resp = await client.get("/api/v1/training/templates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["template_code"] == "TPL_BACKHAND_IMPROVE"


@pytest.mark.asyncio
async def test_get_templates_by_problem(client, auth_headers, auth_user, db_session, member_sub):
    """按问题 ID 过滤模板"""
    await _seed_knowledge_base(db_session)
    await db_session.commit()

    resp = await client.get("/api/v1/training/templates", params={"problem_id": "P001"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1

    resp2 = await client.get("/api/v1/training/templates", params={"problem_id": "P999"}, headers=auth_headers)
    assert resp2.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_get_template_detail(client, auth_headers, auth_user, db_session, member_sub):
    """模板详情"""
    seeds = await _seed_knowledge_base(db_session)
    await db_session.commit()
    template_id = seeds["template"].id

    resp = await client.get(f"/api/v1/training/templates/{template_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["template_code"] == "TPL_BACKHAND_IMPROVE"
    assert "template_data" in data
    assert "goal" in data["template_data"]


@pytest.mark.asyncio
async def test_get_template_detail_not_found(client, auth_headers, member_sub):
    """不存在的模板返回 404"""
    resp = await client.get("/api/v1/training/templates/99999", headers=auth_headers)
    assert resp.status_code == 404


# =============================================================================
# 方案调整历史
# =============================================================================

@pytest.mark.asyncio
async def test_get_plan_adjustments_empty(client, auth_headers, auth_user, db_session, member_sub):
    """空调整历史"""
    plan = await _create_plan(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.get(f"/api/v1/training/plans/{plan.id}/adjustments", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["plan_id"] == plan.id
    assert data["current_version"] == 1
    assert len(data["adjustments"]) == 0


@pytest.mark.asyncio
async def test_get_plan_adjustments_not_found(client, auth_headers, member_sub):
    """不存在的方案返回 404"""
    resp = await client.get("/api/v1/training/plans/99999/adjustments", headers=auth_headers)
    assert resp.status_code == 404


# =============================================================================
# 重新评估方案
# =============================================================================

@pytest.mark.asyncio
async def test_re_evaluate_plan(client, auth_headers, auth_user, db_session, member_sub):
    """重新评估方案"""
    plan = await _create_plan(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.post(f"/api/v1/training/plans/{plan.id}/re-evaluate", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["plan_id"] == plan.id
    assert data["action"] in ("maintain", "adjust", "escalate", "new_goal")
    assert "reason" in data


@pytest.mark.asyncio
async def test_re_evaluate_plan_not_found(client, auth_headers, member_sub):
    """不存在的方案返回 404"""
    resp = await client.post("/api/v1/training/plans/99999/re-evaluate", headers=auth_headers)
    assert resp.status_code == 404


# =============================================================================
# 训练单列表
# =============================================================================

@pytest.mark.asyncio
async def test_list_training_sessions(client, auth_headers, auth_user, db_session, member_sub):
    """训练单列表"""
    plan = await _create_plan(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.get(f"/api/v1/training/plans/{plan.id}/sessions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["plan_id"] == plan.id
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["name"] == "反手推球"
    assert data["items"][0]["reps"] == 50
    assert data["items"][0]["is_completed"] is False


@pytest.mark.asyncio
async def test_list_training_sessions_not_found(client, auth_headers, member_sub):
    """不存在的方案返回 404"""
    resp = await client.get("/api/v1/training/plans/99999/sessions", headers=auth_headers)
    assert resp.status_code == 404


# =============================================================================
# 完成训练单
# =============================================================================

@pytest.mark.asyncio
async def test_complete_training_session(client, auth_headers, auth_user, db_session, member_sub):
    """完成训练单"""
    plan = await _create_plan(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/training/plans/{plan.id}/sessions/1/complete", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == 1
    assert data["is_completed"] is True
    assert data["plan_progress"] == 50  # 1/2 = 50%
    assert data["points_earned"] == 5  # training_session = 5 points


@pytest.mark.asyncio
async def test_complete_training_session_duplicate(client, auth_headers, auth_user, db_session, member_sub):
    """重复完成训练单返回 409"""
    plan = await _create_plan(db_session, auth_user["user_id"])
    await db_session.commit()

    resp1 = await client.post(
        f"/api/v1/training/plans/{plan.id}/sessions/1/complete", headers=auth_headers
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        f"/api/v1/training/plans/{plan.id}/sessions/1/complete", headers=auth_headers
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_complete_all_sessions(client, auth_headers, auth_user, db_session, member_sub):
    """完成所有训练单进度 100%"""
    plan = await _create_plan(db_session, auth_user["user_id"])
    await db_session.commit()

    resp1 = await client.post(
        f"/api/v1/training/plans/{plan.id}/sessions/1/complete", headers=auth_headers
    )
    assert resp1.status_code == 200
    assert resp1.json()["data"]["plan_progress"] == 50

    resp2 = await client.post(
        f"/api/v1/training/plans/{plan.id}/sessions/2/complete", headers=auth_headers
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["plan_progress"] == 100
