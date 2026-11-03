"""
tests/unit/test_r15_state_retry.py — R15-State-N1 状态机重试链回归守卫

背景：R15 审计 P1 — on_step_failed 先行 processing→failed 终态转换，使
Celery 重试链（max_retries=1）出现两类不可达：
① 重试成功 → on_task_complete 的 failed→completed 被矩阵拒绝 → 任务永久
   failed + 完成通知不可达；
② 重试再失败 → _mark_task_failed 的 failed→failed 被拒 → allowed=False →
   退额度分支不可达（生产路径退款断裂，eager 下被 va 启动失败分支掩盖）。
修复：终态转换单点收口（_mark_task_failed / on_task_complete / va 启动分支），
失败通知随终态触发（notify_task_failed），级联 SETNX 幂等防重。

覆盖：
- 步骤失败不转终态（processing 保持 + 无提前通知）
- 重试成功 → completed + error 清除 + 完成通知可达（离线落库）
- 重试耗尽（_mark_task_failed）→ 退款可达 + 通知可达 + 步骤错误保留
- _trigger_cascade 幂等（同 report_id 二次触发积分不双发）
- 在线用户失败通知走 WS（notify_task_failed 在线分支）
"""

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.gamification import UserPoints
from app.models.notification import NotificationRecord
from app.models.video_analysis import AnalysisReport, FileRecord, PipelineStep, VideoTask


# =====================================================================
# 级联任务 spy（autouse）— 与 test_ai_pipeline.py / test_r14_f 同型：
# eager 下 delay() 同步执行任务体，其 _run_async 新线程 asyncio.run 与
# pytest-asyncio 主循环的 asyncpg 连接池跨循环冲突（生产 worker 无此问题）。
# service 层已有专项测试，此处仅保证级联投递不阻塞本文件主流程断言。
# =====================================================================

@pytest.fixture(autouse=True)
def _spy_cascade_tasks(monkeypatch):
    import app.tasks.progress as progress_tasks_mod
    import app.tasks.dashboard as dashboard_tasks_mod
    import app.tasks.training as training_tasks_mod

    class _Spy:
        def __init__(self, name):
            self.calls = []
            self.name = name

        def delay(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    snap, bust, advice = _Spy("snapshot"), _Spy("bust"), _Spy("advice")
    monkeypatch.setattr(progress_tasks_mod, "generate_snapshot_task", snap)
    monkeypatch.setattr(dashboard_tasks_mod, "bust_cache_task", bust)
    monkeypatch.setattr(training_tasks_mod, "generate_advice_task", advice)
    return {"snapshot": snap, "bust": bust, "advice": advice}


# =====================================================================
# 辅助
# =====================================================================

async def _create_task(db, user_id, status="queued"):
    """创建 FileRecord + VideoTask（commit 使生产代码独立 session 可见）"""
    file_record = FileRecord(
        user_id=user_id,
        oss_key=f"test/r15/{user_id}",
        file_size=10 * 1024 * 1024,
        file_type="mp4",
        status="uploaded",
    )
    db.add(file_record)
    await db.flush()

    task = VideoTask(
        user_id=user_id,
        file_id=file_record.id,
        oss_key=file_record.oss_key,
        status=status,
        task_uuid=f"uuid-r15-{user_id}-{datetime.now().timestamp()}",
        progress=0.0,
        total_steps=10,
    )
    db.add(task)
    await db.commit()
    return task


async def _daily_key(user_id: int) -> str:
    tz_cst = timezone(timedelta(hours=8))
    today = datetime.now(tz_cst).strftime("%Y%m%d")
    return f"quota:analysis:{user_id}:{today}"


async def _get_task_committed(task_id: int) -> VideoTask:
    """独立 session 读取最新已提交状态（db_session 身份映射快照过期问题）"""
    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        _ = (task.status, task.error_message, task.completed_at, task.current_step)
        return task


async def _to_processing(task_id: int) -> None:
    """queued → processing（模拟 PipelineOrchestrator.build_and_run 启动转换）"""
    from app.ai_pipeline.progress import transition_task_status
    from app.ai_pipeline.pipeline import PipelineOrchestrator

    await PipelineOrchestrator.init_steps(task_id)
    async with async_session_factory() as db:
        assert await transition_task_status(db, task_id, "processing") is True
        await db.commit()


async def _count_notifications(user_id: int) -> list[NotificationRecord]:
    async with async_session_factory() as db:
        return (await db.execute(
            select(NotificationRecord).where(NotificationRecord.user_id == user_id)
        )).scalars().all()


# =====================================================================
# 1. 步骤失败：任务保持 processing（不先行终态转换）
# =====================================================================

@pytest.mark.asyncio
class TestStepFailureKeepsProcessing:
    """R15-State-N1 核心：可重试失败不固化为终态"""

    async def test_on_step_failed_no_terminal_transition_no_notify(
        self, db_session, test_user,
    ):
        """步骤失败 → 任务保持 processing + 步骤级错误落库 + 不提前推送失败通知"""
        from app.ai_pipeline.progress import ProgressTracker

        redis = await get_redis()
        await redis.delete(f"ws:online:{test_user.id}", f"notif:unread:{test_user.id}")

        task = await _create_task(db_session, test_user.id)
        await _to_processing(task.id)

        await ProgressTracker.on_step_failed(task.id, 3, "球体检测超时")

        t = await _get_task_committed(task.id)
        assert t.status == "processing", "可重试失败不得先行进入终态"
        assert t.error_message == "球体检测超时"
        assert t.completed_at is None

        async with async_session_factory() as db:
            steps = (await db.execute(
                select(PipelineStep).where(PipelineStep.task_id == task.id)
            )).scalars().all()
            failed = [s for s in steps if s.status == "failed"]
            assert len(failed) == 1
            assert failed[0].step_number == 3
            assert failed[0].error_message == "球体检测超时"

        # 通知仅在最终失败触发 — 可重试失败不落库/不推送
        rows = await _count_notifications(test_user.id)
        assert rows == [], f"可重试失败不应提前推送通知，实际 {len(rows)} 条"
        assert int(await redis.get(f"notif:unread:{test_user.id}") or 0) == 0


# =====================================================================
# 2. 重试成功：completed + 错误清除 + 完成通知可达
# =====================================================================

@pytest.mark.asyncio
class TestRetrySuccessCompletes:
    """失败 → 重试 → 成功：任务 completed，通知分支可达（P1 症状①回归守卫）"""

    async def test_retry_success_completes_and_notifies(
        self, db_session, test_user, monkeypatch,
    ):
        import app.ai_pipeline.tasks as tasks_mod
        from app.ai_pipeline.tasks import run_pipeline_async

        redis = await get_redis()
        await redis.delete(f"ws:online:{test_user.id}", f"notif:unread:{test_user.id}")
        # 预扣 1 次免费额度 + 写来源标记（模拟 create_task 预检）
        await redis.set(await _daily_key(test_user.id), 1)

        task = await _create_task(db_session, test_user.id)
        await redis.set(f"quota:src:{task.id}", "free", ex=86400)
        await _to_processing(task.id)

        # 第一次执行：Step 1 失败（重试链首次失败）
        def _boom_step1(oss_key: str = "", **kw):
            raise RuntimeError("step1 瞬时故障")

        monkeypatch.setattr(tasks_mod, "_mock_step_1", _boom_step1)
        with pytest.raises(RuntimeError, match="step1 瞬时故障"):
            await run_pipeline_async(task.id, task.oss_key)

        t = await _get_task_committed(task.id)
        assert t.status == "processing", "首次失败后应保持 processing（重试窗口）"
        assert t.error_message == "step1 瞬时故障"
        # 额度不退（任务未终局——退款仅在最终失败）
        assert int(await redis.get(await _daily_key(test_user.id))) == 1
        assert await redis.get(f"quota:src:{task.id}") == "free"

        # 第二次执行（重试）：恢复 Step 1 → 全流程成功
        monkeypatch.setattr(tasks_mod, "_mock_step_1", lambda oss_key="", **kw: {
            "video_info": {"duration_sec": 60, "fps": 30, "resolution": "1920x1080"},
            "cover_image_url": f"http://localhost:3000/mock-oss/covers/x.jpg",
        })
        await run_pipeline_async(task.id, task.oss_key)

        t = await _get_task_committed(task.id)
        assert t.status == "completed", "重试成功后 processing→completed 必须可达"
        assert t.completed_at is not None
        assert t.error_message is None, "成功终态应清除重试窗口内的步骤错误"
        assert t.progress == 1.0

        # 成功 = 额度已消耗（不退）：日计数保持 1
        assert int(await redis.get(await _daily_key(test_user.id))) == 1

        # 完成通知可达（离线用户 → DB 落库恰好 1 条 analysis_complete）
        rows = await _count_notifications(test_user.id)
        assert len(rows) == 1, f"重试成功后完成通知应恰好 1 条，实际 {len(rows)} 条"
        assert rows[0].type == "analysis_complete"
        assert int(await redis.get(f"notif:unread:{test_user.id}")) == 1


# =====================================================================
# 3. 重试耗尽：_mark_task_failed 退款可达 + 通知可达 + 步骤错误保留
# =====================================================================

@pytest.mark.asyncio
class TestRetryExhaustedRefundAndNotify:
    """失败 → 重试再失败 → 耗尽：退款分支可达（P1 症状②回归守卫）"""

    async def test_mark_failed_refunds_notifies_preserves_step_error(
        self, db_session, test_user,
    ):
        from app.ai_pipeline.tasks import _mark_task_failed

        redis = await get_redis()
        await redis.delete(f"ws:online:{test_user.id}", f"notif:unread:{test_user.id}")
        await redis.set(await _daily_key(test_user.id), 1)

        task = await _create_task(db_session, test_user.id)
        await redis.set(f"quota:src:{task.id}", "free", ex=86400)
        await _to_processing(task.id)

        # 模拟 on_step_failed 已写入的步骤级错误（重试链内真实顺序）
        async with async_session_factory() as db:
            t = await db.get(VideoTask, task.id)
            t.error_message = "step3 球体检测超时"
            await db.commit()

        # 重试耗尽（生产路径 MaxRetriesExceeded → _mark_task_failed）
        await _mark_task_failed(task.id, "MaxRetriesExceededError", user_id=test_user.id)

        t = await _get_task_committed(task.id)
        assert t.status == "failed"
        assert t.completed_at is not None
        # 步骤级错误保留（不被底层异常文本覆盖）
        assert t.error_message == "step3 球体检测超时"

        # 退款可达（原 P1：failed→failed 被拒时 allowed=False 此分支不可达）
        assert int(await redis.get(await _daily_key(test_user.id))) == 0
        assert await redis.get(f"quota:src:{task.id}") == "refunded"

        # 最终失败通知可达（离线落库恰好 1 条 analysis_failed）
        rows = await _count_notifications(test_user.id)
        assert len(rows) == 1, f"最终失败通知应恰好 1 条，实际 {len(rows)} 条"
        assert rows[0].type == "analysis_failed"
        assert rows[0].title == "视频分析失败"
        assert int(await redis.get(f"notif:unread:{test_user.id}")) == 1

    async def test_mark_failed_overwrites_empty_error(
        self, db_session, test_user,
    ):
        """无既有步骤错误（如启动即失败的旁路场景）→ 写入调用方错误文本"""
        from app.ai_pipeline.tasks import _mark_task_failed

        task = await _create_task(db_session, test_user.id)
        await _to_processing(task.id)

        await _mark_task_failed(task.id, "流水线启动失败", user_id=test_user.id)

        t = await _get_task_committed(task.id)
        assert t.status == "failed"
        assert t.error_message == "流水线启动失败"


# =====================================================================
# 4. notify_task_failed 在线分支（WS 推送，不落库）
# =====================================================================

@pytest.mark.asyncio
class TestNotifyTaskFailedOnline:
    async def test_online_user_failure_uses_ws_push(
        self, db_session, test_user, monkeypatch,
    ):
        from app.ai_pipeline.progress import ProgressTracker
        from app.services.notification_service import NotificationService

        pushed: list = []

        async def _spy_push(user_id, event_type, data):
            pushed.append((user_id, event_type, data))

        monkeypatch.setattr(NotificationService, "push_ws_message", staticmethod(_spy_push))

        redis = await get_redis()
        await redis.delete(f"notif:unread:{test_user.id}")
        await redis.set(f"ws:online:{test_user.id}", "1")  # 标记在线

        task = await _create_task(db_session, test_user.id)
        await _to_processing(task.id)
        async with async_session_factory() as db:
            t = await db.get(VideoTask, task.id)
            t.error_message = "step2 失败"
            t.current_step = 2
            await db.commit()

        await ProgressTracker.notify_task_failed(task.id)

        assert len(pushed) == 1
        assert pushed[0][0] == test_user.id
        assert pushed[0][1] == "analysis_failed"
        assert pushed[0][2]["task_id"] == task.id
        assert pushed[0][2]["step"] == 2
        assert pushed[0][2]["error"] == "step2 失败"

        # 在线：不落库、不增未读计数
        rows = await _count_notifications(test_user.id)
        assert rows == []
        assert int(await redis.get(f"notif:unread:{test_user.id}") or 0) == 0


# =====================================================================
# 5. _trigger_cascade 幂等（积分不双发）
# =====================================================================

@pytest.mark.asyncio
class TestTriggerCascadeIdempotency:
    """R15-State-N1 伴生：Step 10 失败重试成功场景级联二次触发 → SETNX 防重"""

    async def test_cascade_fires_once_per_report(
        self, db_session, test_user, _spy_cascade_tasks,
    ):
        from app.ai_pipeline.report_generator import ReportGenerator

        task = await _create_task(db_session, test_user.id)
        report_id = 424242  # 任意 id（级联下游任务已 spy 化）

        await ReportGenerator._trigger_cascade(
            task.id, report_id, test_user.id, result_data={}
        )
        # 第一次：analysis +10 落账（_auto_checkin 可能另加签到分 — 记录基线值）
        # + 级联投递发生
        async with async_session_factory() as db:
            up = await db.scalar(
                select(UserPoints).where(UserPoints.user_id == test_user.id)
            )
            assert up is not None
            assert up.total_points >= 10, "首次级联应至少落账 analysis +10"
            first_total = up.total_points
        assert len(_spy_cascade_tasks["snapshot"].calls) == 1
        assert len(_spy_cascade_tasks["advice"].calls) == 1
        assert len(_spy_cascade_tasks["bust"].calls) == 1

        # 第二次（同 report_id — 重试链二次执行场景）：幂等跳过
        await ReportGenerator._trigger_cascade(
            task.id, report_id, test_user.id, result_data={}
        )
        async with async_session_factory() as db:
            up = await db.scalar(
                select(UserPoints).where(UserPoints.user_id == test_user.id)
            )
            assert up.total_points == first_total, "级联幂等防重：积分不得双发"
        assert len(_spy_cascade_tasks["snapshot"].calls) == 1
        assert len(_spy_cascade_tasks["advice"].calls) == 1
        assert len(_spy_cascade_tasks["bust"].calls) == 1

        # 第三次（不同 report_id — 正常新报告）：照常触发（analysis +10；
        # 签到当日已存在 → _auto_checkin 幂等跳过，不再加签到分）
        await ReportGenerator._trigger_cascade(
            task.id, report_id + 1, test_user.id, result_data={}
        )
        async with async_session_factory() as db:
            up = await db.scalar(
                select(UserPoints).where(UserPoints.user_id == test_user.id)
            )
            assert up.total_points == first_total + 10
        assert len(_spy_cascade_tasks["snapshot"].calls) == 2
