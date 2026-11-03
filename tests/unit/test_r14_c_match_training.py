"""
tests/unit/test_r14_c_match_training.py — R14 审计缺口补齐（第三轮：match_data / training）

覆盖（R14 审计认定缺口；先读代码确认行为真实存在，与审计描述不符处以实际实现为准）：
- B4-2  比赛记录 POST/PATCH 校验失败 → 422（Pydantic schema 层：枚举/类型/范围约束）
- B4-3  记录创建对客户端提供 match_id 的处理（服务端校验语义：不存在/非本人 →
        静默忽略；本人有效 match → 关联落库）
- B4-4  training advice 生成 Celery 任务体（eager 直调：返回契约 + advice_ready
        WS 推送内容与实际生成建议一致 + 失败路径重试语义）
- B4-5  比赛记录创建 → gamification record 事件 +3 落库（R14-Gam-N1 修复验证
        重点：积分经调用方 commit 真正持久化，断言 user_points 表 / checkin_record /
        Redis streak 计数的最终值）
- B4-6  40422 错误码分支（代码定位语义：训练单不存在，training_service.py L462）
- B4-11 bo1/bo3/bo7 赛制比分合法性（FORMAT_WIN_MAP 1/2/4；非法 → 422 code=42210）

审计描述与实际实现的差异（以实际为准）：
- B4-4「建议落库」：训练建议不落库（无 advice 表，get_advice_by_report 按报告 +
  知识库规则按需计算，training_service.py L34-132 无写路径）；任务体的可观测持久
  化效果为 Redis pubsub advice_ready WS 推送（app/tasks/training.py L80-91 →
  notification_service.py L59-61）。本文件按实际行为断言任务返回契约 + WS 推送。

既有覆盖对照（部分跳过 + 增量补齐）：
- B4-2 schema 校验器分支（平局 test_match_data.py L94-107 / 未来日期 L109-123）与
  服务层 422（bo5 赛制 L77-90 / is_win 忽略 L287-311 / 空更新体 L418-433）已覆盖
  —— 本文件补 Pydantic 类型/枚举/范围分支 + PATCH 校验器分支
- B4-4 服务层 advice 字段完整性已由 test_training.py L157-173（API 路径）覆盖；
  级联投递 spy 已由 test_ai_pipeline.py L100-109 覆盖 —— 本文件补任务体本体
  （eager 直调执行 + 返回契约 + WS 推送内容）
- B4-5 scoring finish 的 match 事件 +5 已由 tests/integration/test_cascade_chains.py
  L199-218 覆盖（同为 R14-Gam-N1 修复验证模式）—— 本文件补 record 事件 +3
- B4-11 match-data 域既有测试仅用 bo5/custom（test_match_data.py 全文件）；scoring
  域 bo1-bo7 枚举（test_cascade_chains.py L407-422）非本域录入路径 —— 均需增量
- B4-6 全套件 grep 40422 无命中 —— 无既有覆盖
"""

import json
import time
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import redis.asyncio as redis_async
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.gamification import CheckInRecord, UserPoints
from app.models.knowledge_base import (
    KnowledgeCategory,
    KnowledgeEntry,
    RuleDefinition,
    TrainingTemplate,
)
from app.models.match import Match, MatchRecord
from app.models.membership import Subscription
from app.models.training import TrainingPlan
from app.models.user import User
from app.models.video_analysis import AnalysisReport, FileRecord, VideoTask
from app.services.training_service import TrainingAdviceService
from app.tasks.training import generate_advice_task


# =============================================================================
# 辅助（与 tests/unit/test_training.py 同构，自包含避免跨测试模块导入）
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def member_sub(db_session, auth_user):
    """为测试用户创建有效会员订阅（training 端点 require_membership）"""
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
    """初始化知识库数据（规则 RULE_001 命中 backhand_ratio < 0.30）"""
    cat = KnowledgeCategory(name="反手技术", code="backhand_drive", content={"description": "反手技术"})
    db.add(cat)
    await db.flush()

    entry = KnowledgeEntry(
        category_id=cat.id, title="反手推球", content={"description": "基础反手"},
        entry_type="method",
    )
    db.add(entry)

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


async def _create_report(db, user_id, idx=0):
    """创建分析报告（technique_stats.backhand_ratio=0.15 → 命中 RULE_001）"""
    result_data = {
        "technique_stats": {"backhand_ratio": 0.15, "forehand_ratio": 0.50, "serve_ratio": 0.10},
        "landing_points": {"distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07}},
        "metrics": {"landing_forehand_pct": 0.68, "landing_backhand_pct": 0.25, "landing_middle_pct": 0.07},
        "rally_analysis": {"avg_rally_length": 5.5, "max_rally_length": 12},
        "ball_speed": {"avg_speed_mps": 18.5, "max_speed_mps": 24.0},
        "score_analysis": {"win_rate": 0.55, "key_point_win_rate": 0.50},
    }

    file_record = FileRecord(
        user_id=user_id, oss_key=f"r14c/test/key{idx}", file_size=1048576, file_type="mp4", status="uploaded"
    )
    db.add(file_record)
    await db.flush()

    task = VideoTask(
        user_id=user_id, file_id=file_record.id, oss_key=f"r14c/test/key{idx}",
        status="completed", task_uuid=f"test-r14c-{idx}", progress=100
    )
    db.add(task)
    await db.flush()

    report = AnalysisReport(
        task_id=task.id, user_id=user_id,
        result_data=result_data,
        report_text={
            "summary": f"R14C报告{idx}",
            "issues": [{"problem_id": "P001", "problem_name": "反手偏低"}],
            "suggestions": ["增加反手练习"],
        },
        is_llm_generated=False,
    )
    db.add(report)
    await db.flush()
    return report


async def _create_plan(db, user_id):
    """创建训练方案（2 个训练单 id=1/2）"""
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
# B4-2：POST/PATCH schema 层校验失败 → 422
# =============================================================================

@pytest.mark.asyncio
async def test_b4_2_post_schema_validation_rejected(client, auth_headers):
    """POST 非法枚举/类型/范围 → 422（FastAPI Pydantic 层），且不落库任何记录

    既有覆盖为 schema 校验器分支（平局/未来日期）与服务层 422，本用例补
    Literal 枚举 / 字段类型 / ge-le 范围 / 嵌套 details 校验分支。
    """
    invalid_payloads = [
        ("format 枚举非法", {"format": "bo9"}),
        ("my_score 类型非法", {"my_score": "abc"}),
        ("opponent_name 空串", {"opponent_name": ""}),
        ("opponent_rating 低于下限", {"opponent_rating": 100}),
        ("match_id 低于下限", {"match_id": 0}),
        (
            "details scorer 枚举非法",
            {"details": [{"sequence": 1, "scorer": "referee", "score_method": "serve_point"}]},
        ),
        (
            "details sequence 低于下限",
            {"details": [{"sequence": 0, "scorer": "user", "score_method": "rally_point"}]},
        ),
    ]
    for desc, override in invalid_payloads:
        payload = {"opponent_name": "校验对手", "my_score": 3, "opponent_score": 1, "format": "bo5"}
        payload.update(override)
        resp = await client.post("/api/v1/match-data/records", headers=auth_headers, json=payload)
        assert resp.status_code == 422, f"{desc} 应返回 422，实际 {resp.status_code}: {resp.text}"
        assert "detail" in resp.json(), f"{desc} 应为 FastAPI 校验错误响应格式"

    # 全部校验失败 → 不落库（跨 API 边界验证）
    resp = await client.get("/api/v1/match-data/records", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_b4_2_patch_schema_validation_rejected(client, auth_headers):
    """PATCH 非法枚举/范围/同时平局比分 → 422，原记录不被部分更新污染"""
    resp1 = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={"opponent_name": "补丁对手", "my_score": 3, "opponent_score": 1, "format": "bo5"},
    )
    assert resp1.status_code == 200
    record_id = resp1.json()["data"]["id"]

    invalid_updates = [
        ("match_type 枚举非法", {"match_type": "casual"}),
        ("opponent_rating 超上限", {"opponent_rating": 99999}),
        ("同时传入平局比分", {"my_score": 3, "opponent_score": 3}),
        ("notes 超长", {"notes": "x" * 501}),
    ]
    for desc, body in invalid_updates:
        resp = await client.patch(
            f"/api/v1/match-data/records/{record_id}", headers=auth_headers, json=body
        )
        assert resp.status_code == 422, f"{desc} 应返回 422，实际 {resp.status_code}: {resp.text}"
        assert "detail" in resp.json(), f"{desc} 应为 FastAPI 校验错误响应格式"

    # 原记录保持初始值（校验失败的更新不得部分写入）
    resp2 = await client.get(f"/api/v1/match-data/records/{record_id}", headers=auth_headers)
    assert resp2.status_code == 200
    data = resp2.json()["data"]
    assert data["opponent_name"] == "补丁对手"
    assert data["my_score"] == 3
    assert data["opponent_score"] == 1
    assert data["is_win"] is True
    assert data["notes"] is None
    assert data["match_type"] == "friendly"


# =============================================================================
# B4-3：客户端提供 match_id 的服务端处理语义
# =============================================================================

@pytest.mark.asyncio
async def test_b4_3_match_id_nonexistent_ignored(client, auth_headers):
    """B4-3: 提供不存在的 match_id → 服务端静默忽略（落库 NULL，请求成功）"""
    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "孤儿对手",
            "my_score": 3,
            "opponent_score": 1,
            "format": "bo5",
            "match_id": 999999,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["match_id"] is None

    # 跨 API 边界验证 DB 落库 match_id 为 NULL
    record_id = data["id"]
    async with async_session_factory() as v:
        rec = (
            await v.execute(select(MatchRecord).where(MatchRecord.id == record_id))
        ).scalar_one()
        assert rec.match_id is None

    # 详情回读一致
    resp2 = await client.get(f"/api/v1/match-data/records/{record_id}", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["match_id"] is None


@pytest.mark.asyncio
async def test_b4_3_match_id_other_user_match_ignored(client, auth_headers, db_session):
    """B4-3: 提供他人 match_id → 属主过滤（Match.user_id == user_id）后静默忽略"""
    user_b = User(openid="r14c_user_b", nickname="用户B", status="active")
    db_session.add(user_b)
    await db_session.flush()
    match_b = Match(user_id=user_b.id, opponent_name="B的比赛", format="bo1", status="setup")
    db_session.add(match_b)
    await db_session.commit()
    await db_session.refresh(match_b)

    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "越权对手",
            "my_score": 3,
            "opponent_score": 1,
            "format": "bo5",
            "match_id": match_b.id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["match_id"] is None, "他人记分牌比赛不应被关联"

    async with async_session_factory() as v:
        rec = (
            await v.execute(select(MatchRecord).where(MatchRecord.id == data["id"]))
        ).scalar_one()
        assert rec.match_id is None


@pytest.mark.asyncio
async def test_b4_3_match_id_own_match_linked(client, auth_headers):
    """B4-3: 提供本人有效 match_id → 关联落库，PATCH 随即被 409 拒绝（code=40911）"""
    resp_m = await client.post(
        "/api/v1/scoring/matches",
        headers=auth_headers,
        json={"opponent_name": "联动记分牌"},
    )
    assert resp_m.status_code == 200
    match_id = resp_m.json()["data"]["match_id"]

    resp = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={
            "opponent_name": "联动对手",
            "my_score": 3,
            "opponent_score": 1,
            "format": "bo5",
            "match_id": match_id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["match_id"] == match_id

    # DB 落库关联
    async with async_session_factory() as v:
        rec = (
            await v.execute(select(MatchRecord).where(MatchRecord.id == data["id"]))
        ).scalar_one()
        assert rec.match_id == match_id

    # 关联后不可编辑（PATCH → 409 ERR_RECORD_LINKED=40911）
    resp2 = await client.patch(
        f"/api/v1/match-data/records/{data['id']}",
        headers=auth_headers,
        json={"opponent_name": "改名"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == 40911


# =============================================================================
# B4-4：training advice 生成 Celery 任务体（eager 直调）
# =============================================================================

@pytest.mark.asyncio
async def test_b4_4_generate_advice_task_eager(auth_user, db_session):
    """B4-4: advice 生成任务体 eager 直调 — 返回契约 + advice_ready WS 推送字段完整性

    订阅端使用独立 Redis 客户端（不走全局池）：任务体 run_isolated 收尾
    close_redis() 会断开全局池内连接（含 pubsub 占用连接），独立客户端不受影响。
    """
    await _seed_knowledge_base(db_session)
    report = await _create_report(db_session, auth_user["user_id"])
    await db_session.commit()

    uid = auth_user["user_id"]
    channel = f"ws:relay:ws:user:{uid}"
    sub_client = redis_async.Redis.from_url(settings.redis_url_computed, decode_responses=True)
    pubsub = sub_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        result = generate_advice_task.delay(uid, report.id)

        # 任务返回契约（成功路径）
        assert result.get() == {"status": "ok", "user_id": uid, "report_id": report.id}

        # WS 推送 advice_ready（任务体 _generate_advice_async 的推送分支）
        # redis-py 7.1：subscribe() 不消费 SUBSCRIBE 确认，首个 get_message 读到
        # ack（ignore 返回 None）—— 循环消费直到真正的 message
        msg = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if m is not None and m.get("type") == "message":
                msg = m
                break
        assert msg is not None, "未收到 advice_ready WS 推送"
        payload = json.loads(msg["data"])
        assert payload["event"] == "advice_ready"
        ws_data = payload["data"]
        assert ws_data["report_id"] == report.id
        assert ws_data["is_first_analysis"] is True

        # 推送内容与实际生成的建议一致（字段完整性：suggestion_count 与服务层输出一致）
        advice = await TrainingAdviceService.generate_advice(user_id=uid, report_id=report.id)
        assert ws_data["suggestion_count"] == len(advice["suggestions"])
        assert ws_data["suggestion_count"] >= 1
    finally:
        await pubsub.aclose()
        await sub_client.aclose()


@pytest.mark.asyncio
async def test_b4_4_generate_advice_task_report_not_found(auth_user):
    """B4-4 失败路径：报告不存在 → 任务体重试（eager + task_eager_propagates → Retry 抛出）

    generate_advice_task(self, ...) except 分支 raise self.retry()（max_retries=1
    未耗尽 → celery.exceptions.Retry 向 eager 调用方传播）。
    """
    from celery.exceptions import Retry

    with pytest.raises(Retry):
        generate_advice_task.delay(auth_user["user_id"], 99999)


# =============================================================================
# B4-5：记录创建 → gamification record 事件 +3 持久化（R14-Gam-N1 修复验证）
# =============================================================================

@pytest.mark.asyncio
async def test_b4_5_record_creation_points_persisted(client, auth_headers, auth_user):
    """B4-5: 记录创建 → record +3 经调用方 commit 真正持久化（R14-Gam-N1）

    期望值（POINTS_RULES，gamification_service.py L36-46）：
    - 第 1 条记录：record +3 + 自动打卡 checkin +2（record 事件触发 _auto_checkin，
      streak=1 无奖励）→ total=monthly=5、current_streak=1、checkin_record 1 条
    - 第 2 条记录：仅 record +3（当日已打卡 → _auto_checkin 幂等跳过）
      → total=8、checkin_record 仍 1 条 —— 隔离出「每条记录 +3」增量
    - Redis streak 计数 gamification:streak:user:{uid} = "1"
    """
    uid = auth_user["user_id"]

    resp1 = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={"opponent_name": "积分对手1", "my_score": 3, "opponent_score": 1, "format": "bo5"},
    )
    assert resp1.status_code == 200

    # 请求返回后跨 API 边界查库（独立会话）—— R14-Gam-N1：积分经
    # _trigger_gamification 的调用方 commit 收口真正持久化
    async with async_session_factory() as v:
        up = (
            await v.execute(select(UserPoints).where(UserPoints.user_id == uid))
        ).scalar_one_or_none()
        assert up is not None, (
            "记录创建后应存在 UserPoints 行 — add_points 调用方缺 commit 收口"
            "（R14-Gam-N1）或积分级聤断裂"
        )
        assert up.total_points == 5, (
            f"首条记录应得 record+3 与 auto_checkin+2，实际 {up.total_points}"
        )
        assert up.monthly_points == 5
        assert up.bonus_points == 0
        assert up.current_streak == 1

        checkin_count = (
            await v.execute(
                select(func.count()).select_from(CheckInRecord).where(CheckInRecord.user_id == uid)
            )
        ).scalar_one()
        assert checkin_count == 1

        checkin = (
            await v.execute(select(CheckInRecord).where(CheckInRecord.user_id == uid))
        ).scalar_one()
        assert checkin.checkin_type == "record"

    # Redis 计数最终值（streak 由 _update_streak 写入）
    redis = await get_redis()
    assert await redis.get(f"gamification:streak:user:{uid}") == "1"

    # 第 2 条记录：仅 +3（同日自动打卡幂等）→ 隔离 record 事件增量
    resp2 = await client.post(
        "/api/v1/match-data/records",
        headers=auth_headers,
        json={"opponent_name": "积分对手2", "my_score": 1, "opponent_score": 3, "format": "bo5"},
    )
    assert resp2.status_code == 200

    async with async_session_factory() as v:
        up = (
            await v.execute(select(UserPoints).where(UserPoints.user_id == uid))
        ).scalar_one()
        assert up.total_points == 8, (
            f"第 2 条记录仅 +3（打卡幂等不重复），实际 {up.total_points}"
        )
        assert up.monthly_points == 8

        checkin_count = (
            await v.execute(
                select(func.count()).select_from(CheckInRecord).where(CheckInRecord.user_id == uid)
            )
        ).scalar_one()
        assert checkin_count == 1, "同日自动打卡应幂等（不重复加分/插记录）"


# =============================================================================
# B4-6：40422 错误码分支（训练单不存在）
# =============================================================================

@pytest.mark.asyncio
async def test_b4_6_complete_session_not_found_40422(
    client, auth_headers, auth_user, db_session, member_sub
):
    """B4-6: 完成不存在的训练单 → 404 + code=40422（training_service.py L462）"""
    plan = await _create_plan(db_session, auth_user["user_id"])
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/training/plans/{plan.id}/sessions/999/complete",
        headers=auth_headers,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 40422, f"应为 40422（训练单不存在），实际 {body.get('code')}"
    assert body["message"] == "训练单不存在"


# =============================================================================
# B4-11：bo1/bo3/bo7 赛制比分合法性
# =============================================================================

@pytest.mark.asyncio
async def test_b4_11_bo_formats_valid(client, auth_headers):
    """B4-11: bo1/bo3/bo7 合法比分（win_needed=1/2/4）→ 200 + is_win 正确 + 落库 format 正确"""
    cases = [
        ("bo1", 1, 0, True),
        ("bo1", 0, 1, False),
        ("bo3", 2, 1, True),
        ("bo3", 1, 2, False),
        ("bo7", 4, 2, True),
        ("bo7", 2, 4, False),
    ]
    for fmt, my, opp, is_win in cases:
        resp = await client.post(
            "/api/v1/match-data/records",
            headers=auth_headers,
            json={
                "opponent_name": f"{fmt}对手",
                "my_score": my,
                "opponent_score": opp,
                "format": fmt,
            },
        )
        assert resp.status_code == 200, f"{fmt} {my}:{opp} 应合法: {resp.text}"
        data = resp.json()["data"]
        assert data["is_win"] is is_win, f"{fmt} {my}:{opp} is_win 期望 {is_win}"

    # 落库 format 值核对（跨 API 边界：列表回读）
    resp = await client.get("/api/v1/match-data/records", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 6
    assert {item["format"] for item in data["items"]} == {"bo1", "bo3", "bo7"}


@pytest.mark.asyncio
async def test_b4_11_bo_formats_invalid_score(client, auth_headers):
    """B4-11: bo1/bo3/bo7 非法定局比分 → 422 + code=42210（ERR_SCORE_INVALID）且不落库

    覆盖三类非法形态：超胜局数（bo1 2:0 / bo3 3:1）、未达胜局数（bo7 3:2）、
    胜方达局数但负方不小于上限（bo7 4:5）。
    """
    cases = [
        ("bo1", 2, 0),
        ("bo3", 3, 1),
        ("bo7", 3, 2),
        ("bo7", 4, 5),
    ]
    for fmt, my, opp in cases:
        resp = await client.post(
            "/api/v1/match-data/records",
            headers=auth_headers,
            json={
                "opponent_name": f"非法{fmt}",
                "my_score": my,
                "opponent_score": opp,
                "format": fmt,
            },
        )
        assert resp.status_code == 422, f"{fmt} {my}:{opp} 应非法: {resp.text}"
        body = resp.json()
        assert body["code"] == 42210, (
            f"{fmt} {my}:{opp} 应为 ERR_SCORE_INVALID(42210)，实际 {body.get('code')}"
        )
        assert "赛制规则" in body["message"]

    # 非法请求不落库
    resp = await client.get("/api/v1/match-data/records", headers=auth_headers)
    assert resp.json()["data"]["total"] == 0
