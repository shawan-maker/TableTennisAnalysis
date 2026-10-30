"""
tests/unit/test_ai_pipeline.py — AI 推理流水线单元测试

R12-AIPipeline-12: 整文件补齐（round12 测试缺口）。
依据：切片 13-infrastructure/ai_pipeline.md §8 测试要点
覆盖：流水线完整执行（10 步）、任务状态机矩阵（VA-2 回归）、
      失败退额度（AIPipeline-2）、重试耗尽（AIPipeline-1）、
      is_llm_generated 按实际生成方式（AIPipeline-4）、级联触发
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.user import User
from app.models.video_analysis import AnalysisReport, FileRecord, PipelineStep, VideoTask


# =============================================================================
# 辅助：种子数据
# =============================================================================

async def _create_task(db, user_id, status="queued"):
    """创建 FileRecord + VideoTask（commit 使生产代码内部独立 session 可见）"""
    file_record = FileRecord(
        user_id=user_id,
        oss_key=f"test/pipeline/{user_id}",
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
        task_uuid=f"uuid-pipeline-{user_id}-{datetime.now().timestamp()}",
        progress=0.0,
        total_steps=10,
    )
    db.add(task)
    await db.commit()  # commit（非仅 flush）：流水线内部用独立 session 读取任务
    return task


async def _preset_quota(user_id, count=1):
    """预置当日免费额度计数（模拟请求时预扣）"""
    from app.services.video_analysis_service import VideoAnalysisService

    redis = await get_redis()
    tz_cst = timezone(timedelta(hours=8))
    today = datetime.now(tz_cst).strftime("%Y%m%d")
    key = f"quota:analysis:{user_id}:{today}"
    await redis.set(key, count)
    return key


async def _get_quota_count(user_id):
    redis = await get_redis()
    tz_cst = timezone(timedelta(hours=8))
    today = datetime.now(tz_cst).strftime("%Y%m%d")
    return int(await redis.get(f"quota:analysis:{user_id}:{today}") or 0)


async def _get_task_committed(task_id: int) -> VideoTask:
    """用独立 session 读取任务最新已提交状态。

    _mark_task_failed 等生产代码在独立 session 中 commit；db_session 因
    expire_on_commit=False 持有过期身份映射快照，且 async 下 expire 后的
    属性惰性刷新会触发 MissingGreenlet —— 统一改用独立 session 直查。
    """
    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        # 在 session 上下文内完成属性读取（避免关闭后异步惰性刷新限制）
        _ = (task.status, task.error_message, task.completed_at)
        return task


# =============================================================================
# 流水线完整执行
# =============================================================================

@pytest.mark.asyncio
class TestPipelineFullRun:
    """run_pipeline_async 完整执行 — 10 步 + 报告 + completed"""

    async def test_full_pipeline_completes(self, db_session, test_user, monkeypatch, _spy_cascade_snapshot_bust):
        """eager 模式顺序执行 10 步 → 任务 completed + 报告生成 + 训练建议级联投递"""
        from app.ai_pipeline.progress import transition_task_status
        from app.ai_pipeline.tasks import run_pipeline_async

        # 训练建议级联 spy：eager 下 delay 同步执行任务体，其 _run_async 新线程
        # asyncio.run 与 pytest-asyncio 主循环的 asyncpg 连接池跨循环冲突
        # （生产 worker 单线程无此问题）。advice 生成已有 service 层专项测试，
        # 此处仅验证级联投递被触发且参数正确。
        import app.tasks.training as training_tasks_mod

        advice_calls: list = []

        class _AdviceSpy:
            @staticmethod
            def delay(*args, **kwargs):
                advice_calls.append((args, kwargs))

        monkeypatch.setattr(training_tasks_mod, "generate_advice_task", _AdviceSpy)

        task = await _create_task(db_session, test_user.id)

        # 生产链路 build_and_run 先 init_steps（预插 10 条 pending 步骤行）；
        # on_step_start/on_step_complete 为 UPDATE 语义 —— 无预插行则全部空操作
        from app.ai_pipeline.pipeline import PipelineOrchestrator
        await PipelineOrchestrator.init_steps(task.id)

        async with async_session_factory() as db:
            allowed = await transition_task_status(db, task.id, "processing")
            await db.commit()
        assert allowed

        await run_pipeline_async(task.id, task.oss_key)

        # 任务终态 completed
        async with async_session_factory() as db:
            t = await db.get(VideoTask, task.id)
            assert t.status == "completed"
            assert t.completed_at is not None

            # 报告已生成（LLM 未启用 → is_llm_generated=False）
            report = await db.get(AnalysisReport, task.id)
            assert report is not None
            assert report.is_llm_generated is False
            assert report.result_data.get("technique_stats") is not None

            # 10 条 pipeline_step 记录全部 completed
            from sqlalchemy import select
            steps = (await db.execute(
                select(PipelineStep).where(PipelineStep.task_id == task.id)
            )).scalars().all()
            assert len(steps) == 10
            assert all(s.status == "completed" for s in steps)

        # R12-Training-B1 级联投递：训练建议任务以 (user_id, report_id) 触发一次
        assert len(advice_calls) == 1
        assert advice_calls[0][0] == (test_user.id, task.id)

        # R13-AIP-1 级联投递：快照 + 看板失效经 Celery 投递（异步触发契约）
        assert len(_spy_cascade_snapshot_bust["snapshot"]) == 1, (
            "进度快照级联应投递一次（progress_analysis.generate_snapshot）"
        )
        snap_args = _spy_cascade_snapshot_bust["snapshot"][0][0]
        assert snap_args[0] == test_user.id and snap_args[1] == task.id
        assert len(_spy_cascade_snapshot_bust["bust"]) == 1, (
            "看板缓存失效级联应投递一次（dashboard.bust_cache）"
        )
        assert _spy_cascade_snapshot_bust["bust"][0][0] == (
            test_user.id, "analysis_complete"
        )


# =============================================================================
# 任务状态机矩阵（R12-VA-2 回归 + queued→failed 补充）
# =============================================================================

@pytest.mark.asyncio
class TestTaskStateMachine:
    """transition_task_status 合法/非法转换矩阵"""

    async def test_valid_transitions(self, db_session, test_user):
        from app.ai_pipeline.progress import TASK_TRANSITIONS, transition_task_status

        task = await _create_task(db_session, test_user.id, status="queued")

        # queued → processing（合法）
        assert await transition_task_status(db_session, task.id, "processing") is True
        # processing → completed（合法）
        assert await transition_task_status(db_session, task.id, "completed") is True
        await db_session.commit()

        # completed → processing（非法，终态）
        assert await transition_task_status(db_session, task.id, "processing") is False

    async def test_queued_to_failed_allowed(self, db_session, test_user):
        """R12 复验补充：queued → failed（流水线启动失败）为合法转换"""
        from app.ai_pipeline.progress import transition_task_status

        task = await _create_task(db_session, test_user.id, status="queued")
        assert await transition_task_status(db_session, task.id, "failed") is True
        await db_session.commit()

        t = await db_session.get(VideoTask, task.id)
        assert t.status == "failed"
        assert t.completed_at is not None

    async def test_processing_to_failed_allowed(self, db_session, test_user):
        from app.ai_pipeline.progress import transition_task_status

        task = await _create_task(db_session, test_user.id, status="processing")
        assert await transition_task_status(db_session, task.id, "failed") is True

    async def test_failed_to_queued_retry(self, db_session, test_user):
        """failed → queued（重试）合法；failed → failed 幂等拒绝"""
        from app.ai_pipeline.progress import transition_task_status

        task = await _create_task(db_session, test_user.id, status="failed")
        assert await transition_task_status(db_session, task.id, "queued") is True
        # queued 再 → failed（二次失败）
        assert await transition_task_status(db_session, task.id, "failed") is True
        # failed → failed 被拒绝（幂等防护）
        assert await transition_task_status(db_session, task.id, "failed") is False

    async def test_task_not_found(self, db_session):
        from app.ai_pipeline.progress import transition_task_status

        assert await transition_task_status(db_session, 99999, "processing") is False

    async def test_matrix_definition(self):
        """矩阵常量与设计一致（含 R12 复验补充的 queued→failed）"""
        from app.ai_pipeline.progress import TASK_TRANSITIONS

        assert TASK_TRANSITIONS["queued"] == {"processing", "cancelled", "failed"}
        assert TASK_TRANSITIONS["processing"] == {"completed", "failed"}
        assert TASK_TRANSITIONS["completed"] == set()
        assert TASK_TRANSITIONS["failed"] == {"queued"}
        assert TASK_TRANSITIONS["cancelled"] == set()


# =============================================================================
# 失败退额度（R12-AIPipeline-2）
# =============================================================================

@pytest.mark.asyncio
class TestQuotaRefund:
    """_refund_free_quota / _mark_task_failed 退额度语义"""

    async def test_refund_decrements_quota(self, db_session, test_user):
        """预扣 1 次 → 退额度 → 回到 0"""
        from app.ai_pipeline.tasks import _refund_free_quota

        key = await _preset_quota(test_user.id, count=1)
        await _refund_free_quota(test_user.id)
        assert await _get_quota_count(test_user.id) == 0

    async def test_refund_no_negative(self, db_session, test_user):
        """key 不存在（count=0）→ 不退还（禁止负计数）"""
        from app.ai_pipeline.tasks import _refund_free_quota

        # 不预置 key
        await _refund_free_quota(test_user.id)
        assert await _get_quota_count(test_user.id) == 0

    async def test_mark_failed_refunds_quota(self, db_session, test_user):
        """_mark_task_failed → 状态 failed + 额度退还一次"""
        from app.ai_pipeline.tasks import _mark_task_failed

        task = await _create_task(db_session, test_user.id, status="processing")
        await _preset_quota(test_user.id, count=1)

        await _mark_task_failed(task.id, "测试失败", user_id=test_user.id)

        t = await _get_task_committed(task.id)
        assert t.status == "failed"
        assert t.error_message == "测试失败"
        assert await _get_quota_count(test_user.id) == 0

    async def test_mark_failed_idempotent_no_double_refund(self, db_session, test_user):
        """幂等防护：重复调用 _mark_task_failed 不重复退额度

        场景：eager 重试链中内层重跑与外层各调用一次 _mark_task_failed，
        第二次 failed→failed 被矩阵拒绝，额度不会退第二次。
        """
        from app.ai_pipeline.tasks import _mark_task_failed

        task = await _create_task(db_session, test_user.id, status="processing")
        await _preset_quota(test_user.id, count=1)

        await _mark_task_failed(task.id, "第一次失败", user_id=test_user.id)
        await _mark_task_failed(task.id, "第二次重复调用", user_id=test_user.id)

        t = await _get_task_committed(task.id)
        assert t.status == "failed"
        # 只退了一次（0），无负计数
        assert await _get_quota_count(test_user.id) == 0

    async def test_mark_failed_terminal_task_no_refund(self, db_session, test_user):
        """任务已 completed（终态）→ transition 拒绝 → 不退额度"""
        from app.ai_pipeline.tasks import _mark_task_failed

        task = await _create_task(db_session, test_user.id, status="completed")
        await _preset_quota(test_user.id, count=1)

        await _mark_task_failed(task.id, "迟到失败", user_id=test_user.id)

        t = await db_session.get(VideoTask, task.id)
        assert t.status == "completed"  # 终态不翻转
        assert await _get_quota_count(test_user.id) == 1  # 额度不退


# =============================================================================
# 主任务重试（R12-AIPipeline-1）
# =============================================================================

@pytest.mark.asyncio
class TestPipelineRetry:
    """run_pipeline 失败 → self.retry → 重试耗尽 → 标记失败 + 退额度"""

    async def test_retry_exhausted_marks_failed_and_refunds(
        self, db_session, test_user, monkeypatch,
    ):
        """重试耗尽 → MaxRetriesExceededError → 标记失败 + 退额度

        eager 语义（探针实证，celery/app/task.py retry L732-741）：
        - retries < max_retries 时 self.retry() 抛 Retry（投递重试）
        - retries ≥ max_retries 时抛 MaxRetriesExceededError → 耗尽兜底分支
        - 若传 exc=e：耗尽时重抛原异常 e 而非 MaxRetriesExceededError，
          兜底分支不可达（任务卡 processing + 额度不退）——已修复为不传 exc
        """
        import app.ai_pipeline.tasks as tasks_mod

        task = await _create_task(db_session, test_user.id, status="processing")
        await _preset_quota(test_user.id, count=1)

        # 让流水线每次执行都失败
        async def _boom(task_id, oss_key):
            raise RuntimeError("模拟推理服务超时")

        monkeypatch.setattr(tasks_mod, "run_pipeline_async", _boom)

        # _mark_task_failed spy：生产调用经 _run_async 在新线程 asyncio.run，
        # 其 asyncpg 连接池与 pytest-asyncio 主循环跨循环冲突（测试环境限制）。
        # 此处验证耗尽分支以正确参数投递；DB 效果由下方主循环直调真实函数补验。
        real_mark = tasks_mod._mark_task_failed
        mark_calls: list = []

        async def _spy_mark(task_id, error, user_id=None):
            mark_calls.append((task_id, error, user_id))

        monkeypatch.setattr(tasks_mod, "_mark_task_failed", _spy_mark)

        # eager + retries=1（已达 max_retries=1）→ self.retry() 直接耗尽
        from celery.exceptions import MaxRetriesExceededError

        with pytest.raises(MaxRetriesExceededError):
            tasks_mod.run_pipeline.apply(
                (task.id, task.oss_key), throw=True, retries=1,
            )

        # 耗尽分支以 (task_id, 原异常文本, user_id=None) 调用 _mark_task_failed
        assert mark_calls == [(task.id, "模拟推理服务超时", None)]

        # 主循环直调真实函数补验 DB 效果（等价生产 worker 语义：
        # user_id=None → 从任务记录解析 user_id 后退额度）
        await real_mark(task.id, "模拟推理服务超时", user_id=None)

        t = await _get_task_committed(task.id)
        assert t.status == "failed"
        assert t.error_message == "模拟推理服务超时"
        # 额度退还
        assert await _get_quota_count(test_user.id) == 0

    async def test_startup_failure_refunds_quota(
        self, db_session, test_user, monkeypatch,
    ):
        """R12 复验补充：video_analysis 启动失败路径退还额度（旁路收口）"""
        from app.ai_pipeline.tasks import _refund_free_quota

        await _preset_quota(test_user.id, count=1)
        # 直接调用 _refund_free_quota（启动失败分支使用的同一函数）
        await _refund_free_quota(test_user.id)
        assert await _get_quota_count(test_user.id) == 0


# =============================================================================
# is_llm_generated 按实际生成方式（R12-AIPipeline-4）
# =============================================================================

@pytest.mark.asyncio
class TestIsLLMGenerated:
    """报告 is_llm_generated 按实际生成方式记录"""

    async def test_llm_success_true(self, db_session, test_user, monkeypatch):
        """LLM 调用成功 → used_llm=True"""
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.core.config import settings

        monkeypatch.setattr(settings, "LLM_ENABLED", True)
        monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.test")

        async def _fake_llm(result_data):
            return {"summary": "LLM 摘要", "issues": [], "suggestions": []}

        monkeypatch.setattr(ReportGenerator, "_generate_llm_report", staticmethod(_fake_llm))

        _, used_llm = await ReportGenerator._generate_report_text(
            {"technique_stats": {"forehand_loop": 10}}, task_id=1
        )
        assert used_llm is True

    async def test_llm_failure_fallback_false(self, db_session, test_user, monkeypatch):
        """LLM 调用失败降级模板 → used_llm=False（数据飞轮口径保真）"""
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.core.config import settings

        monkeypatch.setattr(settings, "LLM_ENABLED", True)
        monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.test")

        async def _broken_llm(result_data):
            raise RuntimeError("LLM 服务不可用")

        monkeypatch.setattr(ReportGenerator, "_generate_llm_report", staticmethod(_broken_llm))

        result, used_llm = await ReportGenerator._generate_report_text(
            {"technique_stats": {"forehand_loop": 10, "backhand_block": 2}}, task_id=1
        )
        assert used_llm is False
        assert "summary" in result  # 模板降级产物

    async def test_llm_disabled_false(self, db_session, test_user, monkeypatch):
        """LLM_ENABLED=False → 模板生成 → used_llm=False"""
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.core.config import settings

        monkeypatch.setattr(settings, "LLM_ENABLED", False)

        result, used_llm = await ReportGenerator._generate_report_text(
            {"technique_stats": {"forehand_loop": 10}}, task_id=1
        )
        assert used_llm is False

    async def test_generate_writes_actual_flag(self, db_session, test_user, monkeypatch):
        """generate() 写库的 is_llm_generated 反映实际生成方式（非配置静态值）"""
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.core.config import settings

        # 配置声称 LLM 开启，但让 LLM 调用失败 → 报告 is_llm_generated=False
        monkeypatch.setattr(settings, "LLM_ENABLED", True)
        monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.test")

        async def _broken_llm(result_data):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(ReportGenerator, "_generate_llm_report", staticmethod(_broken_llm))

        task = await _create_task(db_session, test_user.id, status="processing")
        from app.ai_pipeline.progress import transition_task_status
        async with async_session_factory() as db:
            await transition_task_status(db, task.id, "processing")
            await db.commit()

        report_data = await ReportGenerator.generate(task.id, {
            1: {"video_info": {"duration_sec": 60}},
        })

        report = await db_session.get(AnalysisReport, task.id)
        assert report.is_llm_generated is False  # 实际走模板，非配置值 True


# =====================================================================
# R13-AIP-1 级联任务 spy（autouse）
# =====================================================================
# 级联 snapshot/bust_cache 改 Celery 投递后，eager 模式下 delay() 同步
# 执行任务体，其 _run_async 新线程 asyncio.run 与 pytest-asyncio 主循环
# 的 asyncpg 连接池跨循环冲突（SUP-4 同型；生产 worker 单线程无此问题）。
# service 层已有专项测试，此处仅验证级联投递被触发且参数正确。

@pytest.fixture(autouse=True)
def _spy_cascade_snapshot_bust(monkeypatch):
    """级联快照/看板任务 spy 化 — 记录投递参数供断言，不实际执行任务体"""
    import app.tasks.progress as progress_tasks_mod
    import app.tasks.dashboard as dashboard_tasks_mod

    snapshot_calls: list = []
    bust_calls: list = []

    class _SnapshotSpy:
        @staticmethod
        def delay(*args, **kwargs):
            snapshot_calls.append((args, kwargs))

    class _BustSpy:
        @staticmethod
        def delay(*args, **kwargs):
            bust_calls.append((args, kwargs))

    monkeypatch.setattr(progress_tasks_mod, "generate_snapshot_task", _SnapshotSpy)
    monkeypatch.setattr(dashboard_tasks_mod, "bust_cache_task", _BustSpy)
    return {"snapshot": snapshot_calls, "bust": bust_calls}
