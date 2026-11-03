"""
tests/unit/test_r14_f_aip_beat.py — R14 审计缺口补齐（ai_pipeline / circuit breaker / beat）

覆盖目标（R14 审计认定，先核对既有覆盖后确认缺口）：
- R14-AIP-N1（重点）：on_task_complete 状态转换单点收口后，完成通知分支可达 ——
  完整流水线完成 → 离线用户通知落库（回归守卫：修复前 run_pipeline_async
  先行转换使通知分支永不可达）；在线用户 WS 推送；终态二次调用幂等不重复通知。
- AIP-N2：熔断器 half_open 状态机（open 超时→half_open→放行探测→成功 closed /
  失败回 open）。既有覆盖（tests/unit/test_supplements_p1.py L1692-1716）仅
  closed→open 与成功重置，half_open 为缺口。
- R14-Beat-N1（重点）：ai_inference 健康探测标记消费 —— was_unavailable 且无
  available 时报告生成模板回退（fail-open 不阻塞）；available 存在 / 探测未运行
  时放行 LLM。既有覆盖：无（tests/ 全目录 grep was_unavailable/HEALTH_KEY 零命中）。
- Beat-N2：ai_inference_health beat 任务体 eager 直调 —— Mock 模式写可用标记、
  真实模式失败写不可用+告警标记、恢复清除不可用标记（含日志）。
- 调度注册：beat 通用完整性（任务数/字段/Celery 注册表）已有
  tests/integration/test_cascade_chains.py L328-372 覆盖（跳过），
  此处仅补 ai-inference-health-check 条目的任务名映射与 */5 周期增量断言。

测试写法依据既有风格（tests/unit/test_ai_pipeline.py）：
eager 模式、断言具体值、Redis 键直接断言、时间断言用 aware UTC、
独立 session 读取任务最新已提交状态。
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.notification import NotificationRecord
from app.models.video_analysis import AnalysisReport, FileRecord, VideoTask


# =============================================================================
# 辅助
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
        oss_key=f"test/tasks/{user_id}/video.mp4",
        status=status,
        task_uuid=f"uuid-r14-{user_id}-{datetime.now().timestamp()}",
        progress=0.0,
        total_steps=10,
    )
    db.add(task)
    await db.commit()
    return task


async def _get_task_committed(task_id: int) -> VideoTask:
    """独立 session 读取任务最新已提交状态（规避身份映射过期快照）"""
    async with async_session_factory() as db:
        task = await db.get(VideoTask, task_id)
        _ = (task.status, task.error_message, task.completed_at, task.progress, task.current_step)
        return task


async def _reset_ai_inference_breaker(redis=None):
    """清理共享 ai_inference 熔断器三键（生产共享键，R12-AIPipeline-7）"""
    if redis is None:
        redis = await get_redis()
    await redis.delete(
        "ai_pipeline:circuit_breaker:ai_inference:state",
        "ai_pipeline:circuit_breaker:ai_inference:failures",
        "ai_pipeline:circuit_breaker:ai_inference:opened_at",
    )


# =====================================================================
# 级联任务 spy（autouse）— 与 test_ai_pipeline.py 同型
# =====================================================================
# eager 下 .delay() 同步执行任务体（_run_async 新线程 asyncio.run），与
# pytest-asyncio 主循环跨 loop（生产 worker 单线程无此问题）。级联行为
# 已有专项测试，本文件聚焦通知/熔断/健康标记断言，仅隔离不执行。

@pytest.fixture(autouse=True)
def _spy_cascade_tasks(monkeypatch):
    """级联任务 spy 化 — 记录投递参数，不实际执行任务体"""
    import app.tasks.progress as progress_tasks_mod
    import app.tasks.dashboard as dashboard_tasks_mod
    import app.tasks.training as training_tasks_mod

    calls = {"snapshot": [], "bust": [], "advice": []}

    class _Spy:
        def __init__(self, bucket: str):
            self._bucket = bucket

        def delay(self, *args, **kwargs):
            calls[self._bucket].append((args, kwargs))

    monkeypatch.setattr(progress_tasks_mod, "generate_snapshot_task", _Spy("snapshot"))
    monkeypatch.setattr(dashboard_tasks_mod, "bust_cache_task", _Spy("bust"))
    monkeypatch.setattr(training_tasks_mod, "generate_advice_task", _Spy("advice"))
    return calls


# =============================================================================
# R14-AIP-N1：任务完成链路通知可达性（单点状态转换）
# =============================================================================

@pytest.mark.asyncio
class TestR14AIPN1CompletionNotificationReachable:
    """R14-AIP-N1: on_task_complete 单点转换后完成通知可达

    修复前 run_pipeline_async 在 on_task_complete 前先行 transition("completed")，
    on_task_complete 内二次转换被 TASK_TRANSITIONS["completed"]=set() 拒绝 →
    allowed=False 提前 return → 完成通知分支（在线 WS / 离线 DB 落库）不可达。
    既有覆盖（test_ai_pipeline.py test_full_pipeline_completes L91-160）仅断言
    任务/报告/步骤/级联投递，未断言通知行为 —— 本类补齐。
    """

    async def test_pipeline_completion_notifies_offline_user(
        self, db_session, test_user, _spy_cascade_tasks,
    ):
        """完整流水线完成 → 离线用户完成通知落库 + 未读计数（回归守卫）

        修复前先行转换使 on_task_complete 通知分支不可达（0 行通知）；
        单点收口后离线路径 send_notification 落 DB 恰好 1 条。
        """
        from app.ai_pipeline.pipeline import PipelineOrchestrator
        from app.ai_pipeline.progress import transition_task_status
        from app.ai_pipeline.tasks import run_pipeline_async

        redis = await get_redis()
        # 确保离线（无 ws:online 标记）+ 未读计数干净
        await redis.delete(f"ws:online:{test_user.id}", f"notif:unread:{test_user.id}")

        task = await _create_task(db_session, test_user.id)
        await PipelineOrchestrator.init_steps(task.id)
        async with async_session_factory() as db:
            assert await transition_task_status(db, task.id, "processing") is True
            await db.commit()

        await run_pipeline_async(task.id, task.oss_key)

        async with async_session_factory() as db:
            t = await db.get(VideoTask, task.id)
            assert t.status == "completed"
            assert t.completed_at is not None
            completed_at = t.completed_at

            report = await db.get(AnalysisReport, task.id)
            assert report is not None
            report_id = report.id

        # completed_at 为 aware UTC 且接近当前时间
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        assert abs((datetime.now(timezone.utc) - completed_at).total_seconds()) < 60

        # 完成通知落库（离线路径）—— 恰好 1 条 analysis_complete
        async with async_session_factory() as db:
            rows = (await db.execute(
                select(NotificationRecord).where(NotificationRecord.user_id == test_user.id)
            )).scalars().all()
            assert len(rows) == 1, f"离线用户完成通知应恰好落库 1 条，实际 {len(rows)}"
            n = rows[0]
            assert n.type == "analysis_complete"
            assert n.title == "视频分析完成"
            assert n.content == "您的视频分析报告已生成，点击查看分析详情"
            assert n.is_read is False
            assert n.extra_data == {"task_id": task.id, "report_id": report_id}

        # 未读计数 +1（send_notification 离线分支 incr）
        redis = await get_redis()
        assert int(await redis.get(f"notif:unread:{test_user.id}")) == 1

    async def test_on_task_complete_online_user_gets_ws_push(
        self, db_session, test_user, monkeypatch,
    ):
        """在线用户 → analysis_complete WS 推送（不落库、不增未读计数）"""
        from app.ai_pipeline.progress import ProgressTracker
        from app.services.notification_service import NotificationService

        redis = await get_redis()
        await redis.delete(f"ws:online:{test_user.id}", f"notif:unread:{test_user.id}")
        # 标记在线（is_user_online 检查 ws:online:{uid}）
        await redis.setex(f"ws:online:{test_user.id}", 120, "1")

        pushed = []

        async def _spy_push(user_id, event_type, data):
            pushed.append((user_id, event_type, data))

        monkeypatch.setattr(NotificationService, "push_ws_message", staticmethod(_spy_push))

        task = await _create_task(db_session, test_user.id, status="processing")

        await ProgressTracker.on_task_complete(task.id, report_id=777)

        # 单点转换：processing → completed + 进度收口
        t = await _get_task_committed(task.id)
        assert t.status == "completed"
        assert t.progress == 1.0
        assert t.current_step == 10

        # WS 推送 analysis_complete（保留事件契约，携带 report_id）
        assert pushed == [
            (test_user.id, "analysis_complete", {"task_id": task.id, "report_id": 777})
        ]

        # 在线 → 不写 DB 通知 + 不增未读计数
        async with async_session_factory() as db:
            rows = (await db.execute(
                select(NotificationRecord).where(NotificationRecord.user_id == test_user.id)
            )).scalars().all()
            assert rows == []
        redis = await get_redis()
        assert await redis.get(f"notif:unread:{test_user.id}") is None

    async def test_on_task_complete_after_terminal_no_duplicate_notification(
        self, db_session, test_user,
    ):
        """终态二次完成调用被矩阵拒绝 → 不重复通知（幂等守卫）

        该语义正是 R14-AIP-N1 修复前「先行转换」触发的不可达分支；
        单点收口后仅在首次合法转换时通知一次。
        """
        from app.ai_pipeline.progress import ProgressTracker

        redis = await get_redis()
        await redis.delete(f"ws:online:{test_user.id}", f"notif:unread:{test_user.id}")

        task = await _create_task(db_session, test_user.id, status="processing")

        await ProgressTracker.on_task_complete(task.id, report_id=1)
        # 二次调用：completed → completed 被终态空集拒绝 → 提前 return
        await ProgressTracker.on_task_complete(task.id, report_id=1)

        t = await _get_task_committed(task.id)
        assert t.status == "completed"

        async with async_session_factory() as db:
            rows = (await db.execute(
                select(NotificationRecord).where(NotificationRecord.user_id == test_user.id)
            )).scalars().all()
            assert len(rows) == 1, "终态二次完成调用不得重复通知"

        redis = await get_redis()
        assert int(await redis.get(f"notif:unread:{test_user.id}") or 0) == 1


# =============================================================================
# AIP-N2：熔断器 half_open 状态机
# =============================================================================

@pytest.mark.asyncio
class TestCircuitBreakerHalfOpen:
    """AIP-N2: half_open 状态机（open→超时→half_open→探测→closed/回 open）

    既有覆盖（tests/unit/test_supplements_p1.py L1692-1716）：
    5 次失败→open、成功重置计数 —— half_open 全链路为缺口。
    """

    async def test_open_within_recovery_timeout_stays_open(self):
        """open 后未过 60s 恢复窗口 → 保持 OPEN，拒绝请求"""
        from app.ai_pipeline.circuit_breaker import AICircuitBreaker, CircuitState

        redis = await get_redis()
        await _reset_ai_inference_breaker(redis)

        cb = AICircuitBreaker("ai_inference")
        for _ in range(5):
            await cb.record_failure()
        assert await cb.get_state() == CircuitState.OPEN

        # 回拨 opened_at 至 59s 前（未达 RECOVERY_TIMEOUT=60）→ 仍 OPEN
        await redis.set(
            "ai_pipeline:circuit_breaker:ai_inference:opened_at", str(time.time() - 59)
        )
        assert await cb.get_state() == CircuitState.OPEN
        assert await cb.allow_request() is False

        await _reset_ai_inference_breaker(redis)

    async def test_open_after_timeout_transitions_to_half_open(self):
        """open 超过 60s 恢复窗口 → 转半开（Redis 状态键持久化）并放行探测"""
        from app.ai_pipeline.circuit_breaker import AICircuitBreaker, CircuitState

        redis = await get_redis()
        await _reset_ai_inference_breaker(redis)

        cb = AICircuitBreaker("ai_inference")
        for _ in range(5):
            await cb.record_failure()
        assert await cb.get_state() == CircuitState.OPEN

        # 回拨至 61s 前（超过 60s 窗口）→ get_state 顺手转半开
        await redis.set(
            "ai_pipeline:circuit_breaker:ai_inference:opened_at", str(time.time() - 61)
        )
        assert await cb.get_state() == CircuitState.HALF_OPEN
        # 状态键已持久化为 half_open（Redis 键直接断言）
        assert await redis.get("ai_pipeline:circuit_breaker:ai_inference:state") == "half_open"
        # 半开放行探测请求
        assert await cb.allow_request() is True

        await _reset_ai_inference_breaker(redis)

    async def test_half_open_probe_success_closes_breaker(self):
        """半开探测成功 → closed + 失败计数器清除"""
        from app.ai_pipeline.circuit_breaker import AICircuitBreaker, CircuitState

        redis = await get_redis()
        await _reset_ai_inference_breaker(redis)

        cb = AICircuitBreaker("ai_inference")
        for _ in range(5):
            await cb.record_failure()
        await redis.set(
            "ai_pipeline:circuit_breaker:ai_inference:opened_at", str(time.time() - 61)
        )
        assert await cb.get_state() == CircuitState.HALF_OPEN

        # 探测成功 → 关闭熔断器
        await cb.record_success()
        assert await cb.get_state() == CircuitState.CLOSED
        assert await redis.get("ai_pipeline:circuit_breaker:ai_inference:state") == "closed"
        # 失败计数器被删除（record_success → delete failures）
        assert await redis.get("ai_pipeline:circuit_breaker:ai_inference:failures") is None
        assert await cb.allow_request() is True

        await _reset_ai_inference_breaker(redis)

    async def test_half_open_probe_failure_reopens_breaker(self):
        """半开探测失败 → 立即回 OPEN（opened_at 刷新，重新计时 60s）"""
        from app.ai_pipeline.circuit_breaker import AICircuitBreaker, CircuitState

        redis = await get_redis()
        await _reset_ai_inference_breaker(redis)

        cb = AICircuitBreaker("ai_inference")
        for _ in range(5):
            await cb.record_failure()
        await redis.set(
            "ai_pipeline:circuit_breaker:ai_inference:opened_at", str(time.time() - 61)
        )
        assert await cb.get_state() == CircuitState.HALF_OPEN

        # 探测失败 → 回 open（failures 6 ≥ 5 阈值）
        await cb.record_failure()
        assert await redis.get("ai_pipeline:circuit_breaker:ai_inference:state") == "open"
        # opened_at 刷新为当前时间 → 60s 窗口内 get_state 为 OPEN（非半开）
        assert await cb.get_state() == CircuitState.OPEN
        assert await cb.allow_request() is False

        await _reset_ai_inference_breaker(redis)


# =============================================================================
# R14-Beat-N1：健康探测标记消费（报告生成 fail-open 降级）
# =============================================================================

@pytest.mark.asyncio
class TestR14BeatN1HealthMarkingConsumption:
    """R14-Beat-N1: ai_inference 健康标记 → 报告生成降级判断

    消费逻辑（report_generator.py L154-172）：LLM 启用时，was_unavailable
    且 available 缺失 → 直接模板降级（不发起 LLM 调用）；available 存在或
    探测尚未运行（两键皆无）→ 放行（fail-open）。
    既有覆盖：无（was_unavailable 全 tests/ 零命中）。
    """

    async def test_was_unavailable_falls_back_to_template_without_llm_call(self, monkeypatch):
        """was_unavailable 标记且无 available → 模板回退，不发起 LLM 调用"""
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.tasks.ai_inference_health import (
            HEALTH_KEY_AVAILABLE, HEALTH_KEY_WAS_UNAVAILABLE,
        )

        redis = await get_redis()
        await redis.delete(HEALTH_KEY_AVAILABLE, HEALTH_KEY_WAS_UNAVAILABLE)
        await _reset_ai_inference_breaker(redis)
        await redis.set(HEALTH_KEY_WAS_UNAVAILABLE, "1")  # 探测标记不可用

        monkeypatch.setattr(settings, "LLM_ENABLED", True)
        monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.test")

        # 调用记录 spy（抛异常哨兵会被 _generate_report_text 的 except 吞掉，
        # 记录式 spy 才能真实验证"未调用"）
        llm_calls = []

        async def _spy_llm(result_data):
            llm_calls.append(result_data)
            return {"summary": "LLM 摘要", "issues": [], "suggestions": []}

        monkeypatch.setattr(ReportGenerator, "_generate_llm_report", staticmethod(_spy_llm))

        result, used_llm = await ReportGenerator._generate_report_text(
            {"technique_stats": {"forehand_loop": 10, "backhand_block": 2}}, task_id=1
        )

        assert llm_calls == [], "健康探测标记不可用时不得发起 LLM 调用"
        assert used_llm is False
        assert "summary" in result and "issues" in result  # 模板降级产物

    async def test_available_marker_overrides_unhealthy_marker(self, monkeypatch):
        """available 与 was_unavailable 并存（恢复窗口内）→ 放行 LLM 路径"""
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.tasks.ai_inference_health import (
            HEALTH_KEY_AVAILABLE, HEALTH_KEY_WAS_UNAVAILABLE,
        )

        redis = await get_redis()
        await redis.delete(HEALTH_KEY_AVAILABLE, HEALTH_KEY_WAS_UNAVAILABLE)
        await _reset_ai_inference_breaker(redis)
        await redis.set(HEALTH_KEY_WAS_UNAVAILABLE, "1")
        await redis.setex(HEALTH_KEY_AVAILABLE, 120, "1")  # 可用标记仍在

        monkeypatch.setattr(settings, "LLM_ENABLED", True)
        monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.test")

        llm_calls = []

        async def _spy_llm(result_data):
            llm_calls.append(result_data)
            return {"summary": "LLM 摘要", "issues": [], "suggestions": []}

        monkeypatch.setattr(ReportGenerator, "_generate_llm_report", staticmethod(_spy_llm))

        result, used_llm = await ReportGenerator._generate_report_text(
            {"technique_stats": {"forehand_loop": 10}}, task_id=1
        )

        assert len(llm_calls) == 1  # available 存在 → 放行 LLM
        assert used_llm is True
        assert result["summary"] == "LLM 摘要"

    async def test_probe_not_run_fail_open_allows_llm(self, monkeypatch):
        """探测尚未运行（两键皆无）→ fail-open 放行 LLM（被动防护由熔断器承担）"""
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.tasks.ai_inference_health import (
            HEALTH_KEY_AVAILABLE, HEALTH_KEY_WAS_UNAVAILABLE,
        )

        redis = await get_redis()
        await redis.delete(HEALTH_KEY_AVAILABLE, HEALTH_KEY_WAS_UNAVAILABLE)
        await _reset_ai_inference_breaker(redis)

        monkeypatch.setattr(settings, "LLM_ENABLED", True)
        monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.test")

        llm_calls = []

        async def _spy_llm(result_data):
            llm_calls.append(result_data)
            return {"summary": "LLM 摘要", "issues": [], "suggestions": []}

        monkeypatch.setattr(ReportGenerator, "_generate_llm_report", staticmethod(_spy_llm))

        result, used_llm = await ReportGenerator._generate_report_text(
            {"technique_stats": {"forehand_loop": 10}}, task_id=1
        )

        assert len(llm_calls) == 1
        assert used_llm is True

    async def test_generate_with_unhealthy_marker_not_blocked(
        self, db_session, test_user, monkeypatch,
    ):
        """标记 was_unavailable 时 generate() 走模板回退完成报告（不阻塞任务完成）"""
        from app.ai_pipeline.report_generator import ReportGenerator
        from app.tasks.ai_inference_health import HEALTH_KEY_WAS_UNAVAILABLE

        redis = await get_redis()
        await redis.delete(HEALTH_KEY_WAS_UNAVAILABLE)
        await _reset_ai_inference_breaker(redis)
        await redis.set(HEALTH_KEY_WAS_UNAVAILABLE, "1")

        monkeypatch.setattr(settings, "LLM_ENABLED", True)
        monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.test")

        llm_calls = []

        async def _spy_llm(result_data):
            llm_calls.append(result_data)
            return {"summary": "LLM 摘要", "issues": [], "suggestions": []}

        monkeypatch.setattr(ReportGenerator, "_generate_llm_report", staticmethod(_spy_llm))

        task = await _create_task(db_session, test_user.id, status="processing")

        # 不抛异常 —— 报告生成完成（模板回退）
        report_data = await ReportGenerator.generate(task.id, {
            1: {"video_info": {"duration_sec": 60}},
        })

        assert report_data["report_id"] > 0
        assert llm_calls == []
        assert "summary" in report_data["report_text"]  # 模板产物

        report = await db_session.get(AnalysisReport, task.id)
        assert report is not None
        assert report.is_llm_generated is False  # 按实际生成方式记录


# =============================================================================
# Beat-N2：ai_inference_health beat 任务体（eager 直调）
# =============================================================================

@pytest.mark.asyncio
class TestBeatN2InferenceHealthTask:
    """Beat-N2: check_inference_health 任务体直调的标记写入与日志

    任务体为裸 asyncio.run 包装（app/tasks/ai_inference_health.py L75），
    在 pytest-asyncio 测试循环内直调会 RuntimeError —— 经 asyncio.to_thread
    在工作线程新 loop 执行（run_isolated + DB_NULLPOOL 设计支持跨 loop）。
    既有覆盖：无（check_inference_health 全 tests/ 零命中）。
    """

    async def test_mock_mode_marks_available(self, monkeypatch):
        """Mock 模式（Phase 1 默认）→ 写入可用标记（TTL 兜底 120s）"""
        from app.tasks.ai_inference_health import (
            HEALTH_KEY_AVAILABLE, HEALTH_TTL_SECONDS, check_inference_health,
        )

        monkeypatch.setattr(settings, "AI_INFERENCE_MOCK", True)

        redis = await get_redis()
        await redis.delete(HEALTH_KEY_AVAILABLE)

        # beat 任务体 eager 直调（工作线程新 loop）
        result = await asyncio.to_thread(check_inference_health)

        assert result == {
            "status": "ok",
            "health": {"status": "healthy", "mock": True},
        }
        # run_isolated 已关闭任务内池 —— 主循环重建后断言键值
        redis = await get_redis()
        assert await redis.get(HEALTH_KEY_AVAILABLE) == "1"
        ttl = await redis.ttl(HEALTH_KEY_AVAILABLE)
        assert 0 < ttl <= HEALTH_TTL_SECONDS

    async def test_real_mode_unreachable_marks_unhealthy(self, monkeypatch, caplog):
        """真实模式探测失败 → 清可用标记 + 写不可用标记 + 告警标记（含日志）"""
        from app.tasks.ai_inference_health import (
            HEALTH_KEY_AVAILABLE, HEALTH_KEY_WAS_UNAVAILABLE, check_inference_health,
        )

        monkeypatch.setattr(settings, "AI_INFERENCE_MOCK", False)
        # 本机不可达端口 → 连接拒绝（快速失败，避免真实 DNS/超时）
        monkeypatch.setattr(settings, "INFERENCE_BASE_URL", "http://127.0.0.1:9")

        redis = await get_redis()
        await redis.setex(HEALTH_KEY_AVAILABLE, 60, "1")  # 预置旧可用标记（验证被清除）
        await redis.delete(HEALTH_KEY_WAS_UNAVAILABLE, "alert:gpu_health:ai_inference")

        with caplog.at_level(logging.WARNING, logger="app.tasks.ai_inference_health"):
            result = await asyncio.to_thread(check_inference_health)

        assert result == {
            "status": "ok",
            "health": {"status": "unhealthy", "mock": False},
        }
        redis = await get_redis()
        assert await redis.get(HEALTH_KEY_AVAILABLE) is None       # 可用标记清除
        assert await redis.get(HEALTH_KEY_WAS_UNAVAILABLE) == "1"  # 不可用标记写入
        # 告警标记（TD-9）：critical + 1h TTL
        assert await redis.get("alert:gpu_health:ai_inference") == "critical"
        assert 0 < await redis.ttl("alert:gpu_health:ai_inference") <= 3600
        # 降级模式日志
        assert any(
            r.message == "ai_inference_unavailable_degraded_mode" for r in caplog.records
        ), "应记录降级模式告警日志"

    async def test_real_mode_healthy_clears_unavailable_marker(self, monkeypatch, caplog):
        """真实模式探测成功 → 写可用标记 + 清除 was_unavailable（恢复路径，含日志）"""
        import httpx

        from app.tasks.ai_inference_health import (
            HEALTH_KEY_AVAILABLE, HEALTH_KEY_WAS_UNAVAILABLE, check_inference_health,
        )

        monkeypatch.setattr(settings, "AI_INFERENCE_MOCK", False)
        monkeypatch.setattr(settings, "INFERENCE_BASE_URL", "http://inference.test")

        redis = await get_redis()
        await redis.delete(HEALTH_KEY_AVAILABLE)
        await redis.set(HEALTH_KEY_WAS_UNAVAILABLE, "1")  # 模拟此前故障残留
        await redis.delete("alert:gpu_health:ai_inference")

        # 伪 HTTP 客户端：GET {base}/health → 200
        requested_urls = []

        class _FakeResp:
            status_code = 200

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc_info):
                return False

            async def get(self, url, timeout=None):
                requested_urls.append(url)
                return _FakeResp()

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

        with caplog.at_level(logging.INFO, logger="app.tasks.ai_inference_health"):
            result = await asyncio.to_thread(check_inference_health)

        assert result == {
            "status": "ok",
            "health": {"status": "healthy", "mock": False},
        }
        assert requested_urls == ["http://inference.test/health"]  # 探测端点契约
        redis = await get_redis()
        assert await redis.get(HEALTH_KEY_AVAILABLE) == "1"        # 可用标记写入
        assert await redis.get(HEALTH_KEY_WAS_UNAVAILABLE) is None  # 恢复：清除不可用标记
        # 恢复日志
        assert any(r.message == "ai_inference_recovered" for r in caplog.records), (
            "从不可用恢复时应记录 ai_inference_recovered 日志"
        )


# =============================================================================
# 调度注册（增量：健康探测条目周期/任务名映射）
# =============================================================================

@pytest.mark.asyncio
class TestBeatScheduleHealthEntry:
    """ai-inference-health-check 条目注册增量断言

    beat 通用完整性（任务数 ≥10 / 全条目含 schedule 字段 / 全部注册到
    Celery 任务表）已有 tests/integration/test_cascade_chains.py
    L328-372 覆盖 —— 跳过，此处仅补健康探测条目的周期与任务名映射。
    """

    async def test_ai_inference_health_registered_every_5_minutes(self):
        """健康探测注册为每 5 分钟（crontab */5）→ 任务名映射 check_inference_health"""
        from celery.schedules import crontab

        from app.core.celery import celery_app

        beat = celery_app.conf.beat_schedule
        entry = beat.get("ai-inference-health-check")
        assert entry is not None, "beat_schedule 缺少 ai-inference-health-check 条目"
        assert entry["task"] == "app.tasks.ai_inference_health.check_inference_health"
        assert entry["schedule"] == crontab(minute="*/5")
