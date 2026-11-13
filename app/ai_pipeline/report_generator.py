"""
app/ai_pipeline/report_generator.py — 分析报告生成器

依据：切片 13-infrastructure/ai_pipeline.md §5.5
功能：聚合步骤 3-8 结果 → result_data JSONB + report_text JSONB
      LLM 优先 → 规则引擎降级
"""

import logging

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.video_analysis import AnalysisReport, VideoTask

logger = logging.getLogger(__name__)


class ReportGenerator:
    """分析报告生成器"""

    @staticmethod
    async def generate(task_id: int, step_results: dict) -> dict:
        """
        聚合步骤结果 → 生成报告。

        step_results: {1: {...}, 2: {...}, ..., 8: {...}}
        返回: {report_id, result_data, report_text}
        """
        # 1. 聚合 result_data
        result_data = ReportGenerator._aggregate_result_data(step_results)

        # 2. 生成 report_text（R12-AIPipeline-4: 返回值携带实际生成方式标志）
        report_text, used_llm = await ReportGenerator._generate_report_text(result_data, task_id)

        # 3. 写入 AnalysisReport
        async with async_session_factory() as db:
            task = await db.get(VideoTask, task_id)
            if not task:
                raise ValueError(f"VideoTask {task_id} not found")

            # 检查是否已有报告
            existing = await db.get(AnalysisReport, task_id)  # one-to-one via task_id unique
            if existing:
                # 更新
                existing.result_data = result_data
                existing.report_text = report_text
                # R12-AIPipeline-4: 重新生成时同样按实际生成方式记录
                existing.is_llm_generated = used_llm
                await db.commit()
                report_id = existing.id
            else:
                report = AnalysisReport(
                    task_id=task_id,
                    user_id=task.user_id,
                    result_data=result_data,
                    report_text=report_text,
                    # R12-AIPipeline-4: is_llm_generated 按实际生成方式记录 —
                    # LLM 调用成功为 True；失败降级模板/熔断降级/LLM 未启用为 False。
                    # 原实现直接写 settings.LLM_ENABLED 配置静态值，
                    # LLM_ENABLED=True 但 LLM 故障降级模板时数据飞轮口径失真
                    is_llm_generated=used_llm,
                    annotated_video_url=step_results.get(10, {}).get("annotated_video_url"),
                    cover_image_url=step_results.get(1, {}).get("cover_image_url"),
                )
                db.add(report)
                await db.commit()
                await db.refresh(report)
                report_id = report.id

        # 4. 触发级联（try/except 不阻塞）
        await ReportGenerator._trigger_cascade(task_id, report_id, task.user_id, result_data)

        return {
            "report_id": report_id,
            "result_data": result_data,
            "report_text": report_text,
        }

    @staticmethod
    def _aggregate_result_data(step_results: dict) -> dict:
        """聚合步骤 1-8 结果为 result_data JSONB"""
        # 视频信息
        video_info = step_results.get(1, {}).get("video_info", {
            "duration_sec": 60,
            "fps": 30,
            "resolution": "1920x1080",
        })

        # 落点
        landing = step_results.get(5, {}).get("landing_points", {
            "nine_grid": [[2, 5, 3], [4, 8, 6], [1, 3, 2]],
            "distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07},
        })

        # 技术统计
        technique = step_results.get(7, {}).get("technique_stats", {
            "forehand_drive": 45,
            "backhand_drive": 18,
            "forehand_loop": 12,
            "serve": 23,
        })

        # 球速
        ball_speed = step_results.get(4, {}).get("ball_speed", {
            "avg_speed_mps": 18.5,
            "max_speed_mps": 25.3,
            "speed_range": [15.2, 22.1],
        })

        # 回合分析
        rally = step_results.get(8, {}).get("rally_analysis", {
            "total_rallies": 23,
            "avg_rally_length": 5.2,
            "max_rally_length": 18,
        })
        # R-FE-R2 批次G（FE-P2-5）：节奏序列——每回合时长（秒），报告页节奏曲线
        # 消费（v2.0 T2.3 承诺）；真实流水线 step 8 可下发同名字段覆盖 mock。
        if "rally_tempo" not in rally:
            rally = {
                **rally,
                "rally_tempo": [8.2, 12.1, 6.4, 15.3, 9.8, 11.2, 7.5, 13.6, 10.4, 8.9,
                                12.8, 9.1, 14.2, 6.8, 11.5, 10.2, 7.9, 13.1, 9.6, 8.4],
            }

        # 比分分析
        # R-FE-R2 批次G（FE-P2-6）：key_points 补 timestamp（视频相对秒），
        # 报告页视频回放 marker 点击 seek 消费（v2.0 T2.3「视频回放带关键帧标记」）。
        score_analysis = {
            "final_score": "11:8",
            "key_points": [
                {"seq": 20, "score": "10:10", "winner": "user", "timestamp": 95.4},
                {"seq": 23, "score": "11:10", "winner": "opponent", "timestamp": 112.8},
                {"seq": 26, "score": "11:11", "winner": "user", "timestamp": 128.6},
                {"seq": 29, "score": "12:11", "winner": "user", "timestamp": 143.2},
            ],
        }

        # R-FE-R2 批次G（FE-P1-3）：落点热图补对手侧九宫格——mine/opponent 双侧
        # 数据（报告页「我的/对手落点」toggle 消费，03 frontend.md §4.3 承诺）。
        # 真实流水线 step 5 可下发 opponent_nine_grid，缺省回落 mock。
        nine_grid = landing.get("nine_grid", [[2, 5, 3], [4, 8, 6], [1, 3, 2]])
        opponent_nine_grid = landing.get(
            "opponent_nine_grid", [[3, 1, 2], [5, 2, 4], [2, 6, 1]]
        )

        return {
            "video_info": video_info,
            "rally_analysis": rally,
            "landing_points": landing,
            "landing_heatmap": {
                "nine_grid": nine_grid,
                "opponent_nine_grid": opponent_nine_grid,
            },
            "technique_stats": technique,
            "technique_distribution": technique,  # dashboard 兼容字段
            "metrics": {  # dashboard 兼容字段
                "landing_forehand_pct": landing.get("distribution", {}).get("forehand", 0),
                "landing_backhand_pct": landing.get("distribution", {}).get("backhand", 0),
                "landing_middle_pct": landing.get("distribution", {}).get("middle", 0),
            },
            "ball_speed": ball_speed,
            "score_analysis": score_analysis,
        }

    @staticmethod
    async def _generate_report_text(result_data: dict, task_id: int) -> tuple[dict, bool]:
        """
        生成报告文字：LLM 优先 → 规则引擎降级。

        R12-AIPipeline-4: 返回 (report_text, used_llm) —
        used_llm 按实际生成方式记录（LLM 成功 True / 降级模板 False），
        供 generate() 写入 is_llm_generated 字段，数据飞轮口径保真。
        """
        if settings.LLM_ENABLED and settings.LLM_API_URL:
            # R14-Beat-N1: AI 推理健康探测降级判断（设计 beat_schedule.py.md §3
            # / ai_inference.md §6.2 — "ai_inference:available 供 ai_pipeline
            # 降级判断"，原实现仅写入方无消费方）：健康任务标记 was_unavailable
            # 且 available 标记缺失时直接走模板降级，不发起 LLM 调用；
            # available 标记存在或探测尚未运行（两键皆无）时放行（fail-open，
            # 被动防护仍由熔断器承担）。
            from app.core.redis import get_redis
            from app.tasks.ai_inference_health import (
                HEALTH_KEY_AVAILABLE,
                HEALTH_KEY_WAS_UNAVAILABLE,
            )
            _redis = await get_redis()
            _unhealthy = await _redis.get(HEALTH_KEY_WAS_UNAVAILABLE)
            if _unhealthy and not await _redis.get(HEALTH_KEY_AVAILABLE):
                logger.warning(
                    "llm_inference_unhealthy_fallback_to_template",
                    extra={"task_id": task_id},
                )
                return ReportGenerator._generate_template_report(result_data), False

            # R12-AIPipeline-8: LLM 路径前置熔断检查（设计 §5.5 _generate_report_text 样例）—
            # 熔断中直接降级模板生成，不调用 LLM；成功/失败计入共享 ai_inference 熔断器
            from app.ai_pipeline.circuit_breaker import AICircuitBreaker

            cb = AICircuitBreaker("ai_inference")
            if not await cb.allow_request():
                logger.warning("llm_circuit_open_fallback_to_template", extra={
                    "task_id": task_id,
                })
                return ReportGenerator._generate_template_report(result_data), False
            try:
                llm_result = await ReportGenerator._generate_llm_report(result_data)
                await cb.record_success()
                return llm_result, True
            except Exception as e:
                await cb.record_failure()
                logger.warning("llm_report_failed_fallback_to_template", extra={
                    "error": str(e), "task_id": task_id
                })

        return ReportGenerator._generate_template_report(result_data), False

    @staticmethod
    async def _generate_llm_report(result_data: dict) -> dict:
        """LLM 生成报告文字 — S6+ 实现"""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.LLM_API_URL}/generate",
                json={"result_data": result_data},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _generate_template_report(result_data: dict) -> dict:
        """规则引擎模板生成报告文字"""
        technique = result_data.get("technique_stats", {})
        landing = result_data.get("landing_points", {})
        distribution = landing.get("distribution", {})

        total_techniques = sum(technique.values()) or 1
        forehand_ratio = sum(
            v for k, v in technique.items() if "forehand" in k.lower()
        ) / total_techniques
        backhand_ratio = sum(
            v for k, v in technique.items() if "backhand" in k.lower()
        ) / total_techniques

        issues = []
        suggestions = []

        if backhand_ratio < 0.30:
            issues.append(f"反手使用率偏低({backhand_ratio:.0%})")
            suggestions.append("增加反手拉球练习，提升反手技术稳定性")
        if forehand_ratio > 0.75:
            issues.append(f"正手使用率过高({forehand_ratio:.0%})")
            suggestions.append("增加落点变化，避免过度依赖正手")

        landing_forehand = distribution.get("forehand", 0)
        if landing_forehand > 0.70:
            issues.append("落点偏正手区域，变化不足")
            suggestions.append("提升落点控制能力，增加反手区域落点")

        if not issues:
            issues.append("技术使用较均衡")
        if not suggestions:
            suggestions.append("保持当前技术特点，持续提升稳定性")

        summary = (
            f"本局正手使用率 {forehand_ratio:.0%}，反手使用率 {backhand_ratio:.0%}。"
            f"落点分布：正手 {distribution.get('forehand', 0):.0%}，"
            f"反手 {distribution.get('backhand', 0):.0%}，"
            f"中路 {distribution.get('middle', 0):.0%}。"
        )

        return {
            "summary": summary,
            "issues": issues,
            "suggestions": suggestions,
        }

    @staticmethod
    async def _trigger_cascade(
        task_id: int, report_id: int, user_id: int, result_data: dict | None = None,
    ) -> None:
        """
        级联触发（try/except 不阻塞）：
        - 训练建议（R12-Training-B1: Celery 异步生成 + WS 推送）
        - 进度快照（R12-Prog-1: 报告完成后自动生成 ProgressSnapshot）
        - 游戏化积分
        - 看板缓存失效（R12-Dash-1: 分析完成后清除 dashboard 缓存）
        - 通知推送（WS 消息已在 ProgressTracker 中处理）

        R15-State-N1 伴生：SETNX 幂等防重 — Celery 重试链中"Step 10 失败
        → 重试成功"场景下 generate 幂等更新报告后本函数会二次执行
        （积分双发 +10 / 训练建议 / 快照 / 缓存失效全链重复）。以
        cascade:done:{report_id} 标记（7d TTL）保证一次触发；
        Redis 不可用时放行（fail-open — 重复级联可容忍，阻塞不可）。
        """
        # 幂等防重（R15-State-N1）
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            first = await redis.set(f"cascade:done:{report_id}", "1", nx=True, ex=7 * 86400)
            if not first:
                logger.info(
                    "cascade_already_triggered",
                    extra={"task_id": task_id, "report_id": report_id},
                )
                return
        except Exception as e:
            logger.warning("cascade_idempotency_check_failed", extra={"error": str(e)})
        # 游戏化积分
        try:
            from app.services.gamification_service import GamificationService
            async with async_session_factory() as db:
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="analysis", ref_id=report_id
                )
                # R14-Gam-N1: add_points 契约仅 flush（切片 §5 注记 2 —
                # "commit 由调用方收口"），缺此收口则积分/自动打卡/徽章在
                # session close 时整体回滚（analysis +10 丢失）
                await db.commit()
        except Exception as e:
            logger.error("cascade_gamification_failed", extra={"error": str(e)})

        # R12-Training-B1: 训练建议异步生成（eager 模式同步执行，生产模式投递队列）
        try:
            from app.tasks.training import generate_advice_task
            generate_advice_task.delay(user_id, report_id)
        except Exception as e:
            logger.error("cascade_generate_advice_failed", extra={"error": str(e)})

        # R12-Prog-1 → R13-AIP-1: 进度快照生成 — 按 ai_pipeline.md 反幻觉约束
        # （"级联链必须异步触发，禁止同步阻塞流水线"）改 Celery 投递
        # （progress_analysis.generate_snapshot，设计 §5.4 第 2 步）
        try:
            from app.tasks.progress import generate_snapshot_task
            generate_snapshot_task.delay(user_id, report_id, result_data or {})
        except Exception as e:
            logger.error("cascade_generate_snapshot_failed", extra={"error": str(e)})

        # R12-Dash-1 → R13-AIP-1: 看板缓存失效 — 同上改 Celery 投递
        # （dashboard.bust_cache，设计 §5.4 第 3 步）
        try:
            from app.tasks.dashboard import bust_cache_task
            bust_cache_task.delay(user_id, "analysis_complete")
        except Exception as e:
            logger.error("cascade_bust_cache_failed", extra={"error": str(e)})
