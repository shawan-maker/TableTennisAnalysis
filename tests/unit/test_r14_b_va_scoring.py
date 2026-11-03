"""
tests/unit/test_r14_b_va_scoring.py — R14 审计缺口补齐（第二轮）

覆盖（R14 审计认定缺口；仅在既有套件未真实覆盖时新增）：
- R14-VA-3  分析报告用户隔离：跨用户 task detail / feedback / annotated-video /
            share → 404（report list / detail / task list 已由
            tests/integration/test_data_isolation.py L133-179 覆盖，本文件
            经真实 eager 流水线产出报告复核 + 补未覆盖端点）
- R14-VA-4  流水线启动失败编排：create_task 后启动失败 / 首步失败 →
            task.status=failed + error_message 落库 + 免费额度退还联动
            （服务级 _mark_task_failed / _refund_free_quota 语义已由
            tests/unit/test_ai_pipeline.py L234-372 覆盖，本文件补
            create_task 端到端编排路径）
- R14-SC-1  评分记录用户隔离：跨用户 start / undo / abandon / resume /
            statistics → 404（detail / score / finish / list 已由
            test_data_isolation.py L66-126 覆盖）
- R14-Pay-N1 消费链（本轮修复新契约）：
    a) 免费日额度耗尽 → 自动消耗 quota:bonus:{uid}（付费分析包额度）
    b) quota:src:{task_id} 消耗来源标记（free/bonus，24h TTL）
    c) 任务失败按来源退还（bonus → INCR quota:bonus；free → 回退日额度）
    d) 标记幂等（标记即删，重复退还不得双退）
    e) 免费与 bonus 双耗尽 → 429（42910）+ 原子回补不漂移

既有覆盖对照（避免重复）：
- 429 触发（仅状态码）：test_video_analysis.py::test_quota_limit L596-636
- consume_analysis_quota 耗尽返回 False：test_membership.py::
  test_quota_exhausted L118-129（本文件补 bonus 回退 / 计数回滚契约）
- 支付侧写入 quota:bonus（INCR + 90d TTL）：test_supplements_p2.py
  Payment-3 L94-182（本文件覆盖消费 / 退还侧）
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.video_analysis import AnalysisReport, PipelineStep, VideoTask
from app.services.file_service import FileService

# 与 service 预扣/回退同口径的 CST（UTC+8）日期
TZ_CST = timezone(timedelta(hours=8))
# 2MB（> 1MB 校验下限；避免大文件 IO 拖慢单文件运行）
FILE_SIZE = 2 * 1024 * 1024


# =============================================================================
# 辅助函数
# =============================================================================

def _cst_today() -> str:
    """CST（UTC+8）yyyymmdd —— 与 _check_free_quota 预扣键一致"""
    return datetime.now(TZ_CST).strftime("%Y%m%d")


def _daily_key(user_id: int) -> str:
    return f"quota:analysis:{user_id}:{_cst_today()}"


def _bonus_key(user_id: int) -> str:
    return f"quota:bonus:{user_id}"


async def _upload_file(client, headers) -> tuple[int, str]:
    """完整上传流程：获取凭证 → 保存 mock 文件 → 确认上传"""
    resp = await client.post(
        "/api/v1/video-analysis/upload-token",
        json={"filename": "r14b.mp4", "file_size": FILE_SIZE},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    FileService.save_uploaded_file(data["oss_key"], b"\x00" * FILE_SIZE)
    resp = await client.post(
        "/api/v1/video-analysis/upload-complete",
        json={"file_id": data["file_id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    return data["file_id"], data["oss_key"]


async def _create_task(client, headers, file_id: int, oss_key: str):
    """创建分析任务（eager 模式下流水线同步执行）"""
    return await client.post(
        "/api/v1/video-analysis/tasks",
        json={"file_id": file_id, "oss_key": oss_key},
        headers=headers,
    )


async def _create_other_user(db_session):
    """创建用户 B（数据隔离对照方）→ (user, auth_headers)"""
    from app.core.security import create_access_token, generate_jti
    from app.models.user import User

    user_b = User(openid="r14b_user_b", nickname="用户B", status="active")
    db_session.add(user_b)
    await db_session.commit()
    await db_session.refresh(user_b)
    token = create_access_token({"sub": str(user_b.id), "jti": generate_jti()})
    return user_b, {"Authorization": f"Bearer {token}"}


# =============================================================================
# R14-Pay-N1 a)/b)：免费日额度耗尽 → bonus 回退 + 来源标记
# =============================================================================

@pytest.mark.asyncio
async def test_pay_n1_bonus_fallback_via_create_task(client, auth_headers, auth_user):
    """a) 免费日额度耗尽 → 自动消耗 quota:bonus，任务正常创建并完成

    预置：日额度计数 = 3（FREE_DAILY_LIMIT，已耗尽）、quota:bonus = 5。
    期望：create_task 走 bonus 回退（bonus 5→4），日计数回滚至 3
    （bonus 消耗不计入免费额度），quota:src 标记 = "bonus"。
    """
    redis = await get_redis()
    uid = auth_user["user_id"]
    await redis.set(_daily_key(uid), 3)
    await redis.set(_bonus_key(uid), 5)

    file_id, oss_key = await _upload_file(client, auth_headers)
    resp = await _create_task(client, auth_headers, file_id, oss_key)
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    # b) 消耗来源标记：bonus，24h TTL（覆盖流水线重试窗口）
    assert await redis.get(f"quota:src:{task_id}") == "bonus"
    ttl = await redis.ttl(f"quota:src:{task_id}")
    assert 0 < ttl <= 86400, f"quota:src TTL 应在 (0, 24h]，实际 {ttl}"

    # a) bonus 计数消耗 1；日额度计数回滚（bonus 不占免费额度）
    assert int(await redis.get(_bonus_key(uid))) == 4
    assert int(await redis.get(_daily_key(uid))) == 3

    # 任务经真实 eager 流水线完成
    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        assert task.status == "completed"


@pytest.mark.asyncio
async def test_pay_n1_quota_src_marker_free_source(client, auth_headers, auth_user):
    """b) free 来源标记 + 24h TTL；任务成功后标记保留（退款仅失败触发）"""
    redis = await get_redis()
    uid = auth_user["user_id"]

    file_id, oss_key = await _upload_file(client, auth_headers)
    resp = await _create_task(client, auth_headers, file_id, oss_key)
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    # 首次分析走免费日额度：计数 1
    assert int(await redis.get(_daily_key(uid))) == 1
    # 标记记录来源 free，TTL ≤ 24h
    assert await redis.get(f"quota:src:{task_id}") == "free"
    ttl = await redis.ttl(f"quota:src:{task_id}")
    assert 0 < ttl <= 86400, f"quota:src TTL 应在 (0, 24h]，实际 {ttl}"

    # 任务成功 → 不退款，标记保留（设计语义：24h 覆盖流水线重试窗口）
    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        assert task.status == "completed"
    assert await redis.get(f"quota:src:{task_id}") == "free"


@pytest.mark.asyncio
async def test_pay_n1_both_exhausted_429(client, auth_headers, auth_user):
    """e) 免费与 bonus 双耗尽 → 429（42910）+ 原子回补（计数不漂移/不负数）

    既有 test_quota_limit（test_video_analysis.py L596-636）仅断言 429
    状态码；本用例补错误码 / 消息 / 计数回补 / 无任务残留契约。
    """
    from app.core.exceptions import ERR_QUOTA_EXHAUSTED

    redis = await get_redis()
    uid = auth_user["user_id"]
    await redis.set(_daily_key(uid), 3)  # 免费耗尽；bonus 未购买（key 不存在）

    file_id, oss_key = await _upload_file(client, auth_headers)
    resp = await _create_task(client, auth_headers, file_id, oss_key)
    assert resp.status_code == 429
    body = resp.json()
    assert body["code"] == ERR_QUOTA_EXHAUSTED  # 42910
    assert "今日免费分析次数已用完" in body["message"]

    # 原子回补：日计数回滚至 3（尝试的 INCR 不残留）
    assert int(await redis.get(_daily_key(uid))) == 3, "日计数应回滚（不得漂移到 4）"
    # bonus：DECR 得 -1 → 回补 0（不得残留负数）
    assert int(await redis.get(_bonus_key(uid)) or 0) == 0, "bonus 应回补为 0（不得为 -1）"

    # 额度拒绝先于任务创建：无 VideoTask 残留、无来源标记
    async with async_session_factory() as db:
        count = (
            await db.execute(
                select(func.count()).select_from(VideoTask).where(VideoTask.user_id == uid)
            )
        ).scalar()
    assert count == 0
    assert await redis.keys("quota:src:*") == []


@pytest.mark.asyncio
async def test_pay_n1_membership_consume_bonus_fallback(db_session, test_user):
    """a) membership_service.consume_analysis_quota 同契约：免费耗尽 → bonus 回退

    既有 test_quota_exhausted（test_membership.py L118-129）仅覆盖无 bonus
    时返回 False；本用例锁定 bonus 回退 + 日计数回滚。
    """
    from app.services.membership_service import MembershipService

    redis = await get_redis()
    uid = test_user.id

    for _ in range(3):
        assert await MembershipService.consume_analysis_quota(uid) is True
    assert int(await redis.get(_daily_key(uid))) == 3

    # 购买分析包（支付回调等效写入 quota:bonus）
    await redis.set(_bonus_key(uid), 5)
    assert await MembershipService.consume_analysis_quota(uid) is True
    assert int(await redis.get(_bonus_key(uid))) == 4, "第 4 次消耗应扣减 bonus"
    assert int(await redis.get(_daily_key(uid))) == 3, "bonus 消耗不计入免费日额度"


@pytest.mark.asyncio
async def test_pay_n1_membership_consume_rollback_no_negative(db_session, test_user):
    """e) consume_analysis_quota 双耗尽 → False + 计数回补（不漂移/不负数）"""
    from app.services.membership_service import MembershipService

    redis = await get_redis()
    uid = test_user.id

    for _ in range(3):
        await MembershipService.consume_analysis_quota(uid)

    # 第 4 次：bonus 不存在 → DECR 得 -1 → 回补 0 + 日计数回滚 → False
    assert await MembershipService.consume_analysis_quota(uid) is False
    assert int(await redis.get(_daily_key(uid))) == 3, "日计数应回滚（不得漂移到 4）"
    assert int(await redis.get(_bonus_key(uid)) or 0) == 0, "bonus 回补为 0（不得为 -1）"


# =============================================================================
# R14-VA-4：流水线启动失败编排（failed + 错误落库 + 额度退还联动）
# =============================================================================

@pytest.mark.asyncio
async def test_va4_startup_failure_marks_failed_and_refunds_free(
    client, auth_headers, auth_user, monkeypatch,
):
    """启动失败（编排器抛错）→ task failed + error_message 落库 + 免费额度退还

    服务级退额度语义已由 test_ai_pipeline.py L234-372 覆盖；本用例补
    create_task 端到端编排路径（R12 复验-VA-2 旁路收口 + R14-Pay-N1
    c) free 来源退还）。失败被编排层收口，接口仍返回 200。
    """
    redis = await get_redis()
    uid = auth_user["user_id"]

    async def _boom(task_id, oss_key):
        raise RuntimeError("编排器启动失败")

    monkeypatch.setattr(
        "app.ai_pipeline.pipeline.PipelineOrchestrator.build_and_run", _boom
    )

    file_id, oss_key = await _upload_file(client, auth_headers)
    resp = await _create_task(client, auth_headers, file_id, oss_key)
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        assert task.status == "failed"
        assert task.error_message == "流水线启动失败: 编排器启动失败"
        assert task.completed_at is not None

        # 编排器整体失败：未初始化任何步骤、未生成报告
        steps = (
            await db.execute(
                select(PipelineStep).where(PipelineStep.task_id == task_id)
            )
        ).scalars().all()
        assert steps == []
        report = (
            await db.execute(
                select(AnalysisReport).where(AnalysisReport.task_id == task_id)
            )
        ).scalar_one_or_none()
        assert report is None

    # c) free 来源退还：预扣 1 → 退回 0；标记改写为墓碑 "refunded"（R14-Pay-N1-d1 幂等）
    assert int(await redis.get(_daily_key(uid)) or 0) == 0
    assert await redis.get(f"quota:src:{task_id}") == "refunded"


@pytest.mark.asyncio
async def test_va4_first_step_failure_marks_failed_and_refunds(
    client, auth_headers, auth_user, monkeypatch,
):
    """首步失败 → task failed（processing→failed）+ 首步错误落库 + 额度退还

    错误信息保持 on_step_failed 写入的步骤错误 —— 启动失败分支的
    failed→failed 转换被状态矩阵拒绝，不得覆盖步骤错误信息。
    """

    def _boom_step1(oss_key: str = "", **kw):
        raise RuntimeError("step1 推理失败")

    monkeypatch.setattr("app.ai_pipeline.tasks._mock_step_1", _boom_step1)

    redis = await get_redis()
    uid = auth_user["user_id"]

    file_id, oss_key = await _upload_file(client, auth_headers)
    resp = await _create_task(client, auth_headers, file_id, oss_key)
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        assert task.status == "failed"
        assert task.error_message == "step1 推理失败"
        assert task.current_step == 1

        steps = (
            await db.execute(
                select(PipelineStep)
                .where(PipelineStep.task_id == task_id)
                .order_by(PipelineStep.step_number)
            )
        ).scalars().all()
        assert len(steps) == 10
        assert steps[0].status == "failed"
        assert steps[0].error_message == "step1 推理失败"
        assert all(s.status == "pending" for s in steps[1:])

    # c) free 来源退还：预扣 1 → 退回 0；标记改写为墓碑 "refunded"（R14-Pay-N1-d1 幂等）
    assert int(await redis.get(_daily_key(uid)) or 0) == 0
    assert await redis.get(f"quota:src:{task_id}") == "refunded"


# =============================================================================
# R14-Pay-N1 c)：任务失败按来源退还（bonus / free）
# =============================================================================

@pytest.mark.asyncio
async def test_pay_n1_refund_bonus_source_on_failure(
    client, auth_headers, auth_user, monkeypatch,
):
    """c) bonus 来源任务失败 → INCR 回 quota:bonus（非回退日额度）

    预置：日额度耗尽（3）、bonus=5。创建任务消耗 bonus（5→4），
    首步失败退款 → bonus 回到 5；日额度计数保持 3 不动。
    """

    def _boom_step1(oss_key: str = "", **kw):
        raise RuntimeError("step1 推理失败")

    monkeypatch.setattr("app.ai_pipeline.tasks._mock_step_1", _boom_step1)

    redis = await get_redis()
    uid = auth_user["user_id"]
    await redis.set(_daily_key(uid), 3)
    await redis.set(_bonus_key(uid), 5)

    file_id, oss_key = await _upload_file(client, auth_headers)
    resp = await _create_task(client, auth_headers, file_id, oss_key)
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        assert task.status == "failed"

    # bonus 退还：4 → 5；日额度不受影响（bonus 消耗与免费额度无关）
    assert int(await redis.get(_bonus_key(uid))) == 5
    assert int(await redis.get(_daily_key(uid))) == 3
    # 墓碑标记（退款已按来源完成，防跨池双退）
    assert await redis.get(f"quota:src:{task_id}") == "refunded"


# =============================================================================
# R14-Pay-N1 d)：标记幂等（墓碑 refunded，重复退还不得双退）
# =============================================================================

@pytest.mark.asyncio
async def test_pay_n1_refund_marker_idempotent_free(db_session, test_user):
    """d) 标记幂等（free 来源）：墓碑标记 + 重复退还不双退（不出现负计数）"""
    from app.ai_pipeline.tasks import _refund_free_quota

    redis = await get_redis()
    uid = test_user.id
    marker_key = "quota:src:987001"

    await redis.set(marker_key, "free")
    await redis.set(_daily_key(uid), 1)  # 模拟本任务预扣 1

    await _refund_free_quota(uid, task_id=987001)
    assert await redis.get(marker_key) == "refunded", "首次退还后标记应改写为墓碑 refunded（R14-Pay-N1-d1）"
    assert int(await redis.get(_daily_key(uid))) == 0

    # 重复退还：无标记 + 计数已为 0 → 不再扣减（禁止负计数/双退）
    await _refund_free_quota(uid, task_id=987001)
    assert int(await redis.get(_daily_key(uid)) or 0) == 0


@pytest.mark.asyncio
async def test_pay_n1_refund_marker_idempotent_bonus(db_session, test_user):
    """d) 标记幂等（bonus 来源）：重复退还不得双退

    墓碑标记（refunded）保证 bonus 池不被二次 INCR；同时第二次调用命中
    墓碑直接返回，不得扣减日额度计数 —— bonus 消耗任务的重复退还若将
    日额度 3→2，用户凭一次消耗获得两次额度恢复（双退）。
    """
    from app.ai_pipeline.tasks import _refund_free_quota

    redis = await get_redis()
    uid = test_user.id
    marker_key = "quota:src:987002"

    await redis.set(marker_key, "bonus")
    await redis.set(_daily_key(uid), 3)  # 免费日额度已耗尽（bonus 消耗前提）
    await redis.set(_bonus_key(uid), 4)  # 购买 5，本任务已扣 1

    await _refund_free_quota(uid, task_id=987002)
    assert await redis.get(marker_key) == "refunded"
    assert int(await redis.get(_bonus_key(uid))) == 5, "首次退还应 INCR 回 bonus"

    # 重复退还：bonus 不得二次 INCR；日额度不得被误扣
    await _refund_free_quota(uid, task_id=987002)
    assert int(await redis.get(_bonus_key(uid))) == 5, "重复退还不得二次 INCR bonus"
    assert int(await redis.get(_daily_key(uid)) or 0) == 3, (
        "无标记回退 free 路径不得扣减日额度 —— bonus 任务的重复退还将 3→2，"
        "使用户多获得一次未消耗的免费额度（双退）"
    )


# =============================================================================
# R14-VA-3：分析报告用户隔离（经真实流水线产出报告）
# =============================================================================

@pytest.mark.asyncio
async def test_va3_report_cross_user_isolation(client, auth_headers, db_session):
    """跨用户 report → 404（40412）；未覆盖端点：task detail / feedback /
    annotated-video / share

    report list / detail / task list 已由 test_data_isolation.py L133-179
    （种子直插）覆盖 —— 本用例经真实 eager 流水线产出报告复核，
    并补齐四个未覆盖端点的跨用户 404。
    """
    from app.core.exceptions import ERR_REPORT_NOT_FOUND

    user_b, headers_b = await _create_other_user(db_session)

    # 用户 A 经真实流水线产出报告
    file_id, oss_key = await _upload_file(client, auth_headers)
    resp = await _create_task(client, auth_headers, file_id, oss_key)
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]
    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}", headers=auth_headers
    )
    report_id = resp.json()["data"]["report_id"]
    assert report_id is not None

    # 正向对照：A 可读自己的报告
    resp = await client.get(
        f"/api/v1/video-analysis/reports/{report_id}", headers=auth_headers
    )
    assert resp.status_code == 200

    # 跨用户报告详情 → 404（ERR_REPORT_NOT_FOUND=40412）
    resp = await client.get(
        f"/api/v1/video-analysis/reports/{report_id}", headers=headers_b
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == ERR_REPORT_NOT_FOUND

    # 跨用户报告列表 → 空
    resp = await client.get("/api/v1/video-analysis/reports", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0

    # 跨用户任务详情 → 404
    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}", headers=headers_b
    )
    assert resp.status_code == 404

    # 跨用户反馈提交 → 404
    resp = await client.post(
        f"/api/v1/video-analysis/reports/{report_id}/feedback",
        json={"is_correct": True, "comment": "越权反馈"},
        headers=headers_b,
    )
    assert resp.status_code == 404

    # 跨用户标注视频 → 404
    resp = await client.get(
        f"/api/v1/video-analysis/reports/{report_id}/annotated-video",
        headers=headers_b,
    )
    assert resp.status_code == 404

    # 跨用户分享创建 → 404
    resp = await client.post(
        f"/api/v1/video-analysis/reports/{report_id}/share",
        headers=headers_b,
    )
    assert resp.status_code == 404


# =============================================================================
# R14-SC-1：评分记录用户隔离
# =============================================================================

@pytest.mark.asyncio
async def test_sc1_match_cross_user_isolation(client, auth_headers, db_session):
    """跨用户 match 状态机操作 → 404：start / undo / abandon / resume / statistics

    detail / score / finish / list 已由 test_data_isolation.py L66-126
    覆盖 —— 本用例补齐剩余状态机端点 + 统计端点的跨用户 404。
    """
    from app.core.exceptions import ERR_MATCH_NOT_FOUND

    user_b, headers_b = await _create_other_user(db_session)

    # 用户 A 创建比赛（setup 状态）
    resp = await client.post(
        "/api/v1/scoring/matches",
        json={"opponent_name": "R14B对手"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    match_id = resp.json()["data"]["match_id"]

    # 正向对照：A 可读自己的比赛
    resp = await client.get(
        f"/api/v1/scoring/matches/{match_id}", headers=auth_headers
    )
    assert resp.status_code == 200

    # 跨用户详情 → 404（ERR_MATCH_NOT_FOUND=40411）
    resp = await client.get(
        f"/api/v1/scoring/matches/{match_id}", headers=headers_b
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == ERR_MATCH_NOT_FOUND

    # 跨用户状态机操作全部 404（属主过滤先于状态校验，不得出现 409/400 泄露存在性）
    resp = await client.post(
        f"/api/v1/scoring/matches/{match_id}/start", headers=headers_b
    )
    assert resp.status_code == 404
    resp = await client.post(
        f"/api/v1/scoring/matches/{match_id}/undo", headers=headers_b
    )
    assert resp.status_code == 404
    resp = await client.post(
        f"/api/v1/scoring/matches/{match_id}/abandon", headers=headers_b
    )
    assert resp.status_code == 404
    resp = await client.post(
        f"/api/v1/scoring/matches/{match_id}/resume", headers=headers_b
    )
    assert resp.status_code == 404
    resp = await client.get(
        f"/api/v1/scoring/matches/{match_id}/statistics", headers=headers_b
    )
    assert resp.status_code == 404

    # 跨用户列表 → 空
    resp = await client.get("/api/v1/scoring/matches", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


# =============================================================================
# R15-Test-N1（补 R14 报告声称但实际缺失的守卫）：
# R14-Gam-N1 feedback/share 侧积分持久化 — round14 报告 §三声称
# 「test_r14_b/c（跨模块积分链断言）」锁定 4 调用方 commit 收口，但
# test_r14_c 仅覆盖 match_data record/scoring match 调用方（L452-526）；
# va feedback / va share 两个调用方（video_analysis_service.py L523/L670）
# 无 UserPoints 断言（A1 复验：既有 feedback/share 测试仅断言响应字段，
# test_video_analysis.py L369-416 / L536+ 零积分断言）。本节补齐。
# =============================================================================

async def _points_total(user_id: int) -> int:
    """独立会话读取用户总积分（无行 → 0）"""
    from app.models.gamification import UserPoints

    async with async_session_factory() as v:
        up = (
            await v.execute(
                select(UserPoints).where(UserPoints.user_id == user_id)
            )
        ).scalar_one_or_none()
        return up.total_points if up else 0


async def _create_report(client, auth_headers) -> int:
    """经真实 eager 流水线产出报告 → report_id"""
    file_id, oss_key = await _upload_file(client, auth_headers)
    resp = await _create_task(client, auth_headers, file_id, oss_key)
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]
    resp = await client.get(
        f"/api/v1/video-analysis/tasks/{task_id}", headers=auth_headers
    )
    report_id = resp.json()["data"]["report_id"]
    assert report_id is not None
    return report_id


@pytest.mark.asyncio
async def test_gam_n1_feedback_points_persisted(client, auth_headers, auth_user):
    """R15-Test-N1: 反馈提交 → feedback +1 UserPoints 持久化（va 调用方 commit 收口）

    期望基线：eager 流水线完成 award analysis +10 + auto_checkin +2 = 12
    （无 BadgeDefinition 种子 → check_badges 无解锁加成）；
    提交反馈后 +1（POINTS_RULES["feedback"]=1，不触发自动打卡）。
    """
    report_id = await _create_report(client, auth_headers)
    uid = auth_user["user_id"]

    baseline = await _points_total(uid)
    assert baseline == 12, (
        f"流水线完成后基线应 12（analysis+10/checkin+2），实际 {baseline}"
    )

    resp = await client.post(
        f"/api/v1/video-analysis/reports/{report_id}/feedback",
        json={"is_correct": True, "comment": "R15积分守卫"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["data_flywheel_action"] == "archived"

    # 跨 API 边界独立会话：积分经调用方 commit 收口真正持久化
    assert await _points_total(uid) == 13, "反馈提交应 +1（feedback 事件积分持久化）"


@pytest.mark.asyncio
async def test_gam_n1_share_points_persisted(client, auth_headers, auth_user):
    """R15-Test-N1: 分享创建 → share +2 UserPoints 持久化（va 调用方 commit 收口）

    期望基线 12 同上；创建分享后 +2（POINTS_RULES["share"]=2）。
    """
    report_id = await _create_report(client, auth_headers)
    uid = auth_user["user_id"]

    baseline = await _points_total(uid)
    assert baseline == 12

    resp = await client.post(
        f"/api/v1/video-analysis/reports/{report_id}/share",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "share_url" in resp.json()["data"]

    assert await _points_total(uid) == 14, "分享创建应 +2（share 事件积分持久化）"
