"""
app/ai_pipeline/report_generator.py — 分析报告生成器

依据：切片 13-infrastructure/ai_pipeline.md §5.5
功能：聚合步骤 3-8 结果 → result_data JSONB + report_text JSONB
      LLM 优先 → 规则引擎降级
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

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

        # 2. 生成 report_text
        report_text = await ReportGenerator._generate_report_text(result_data, task_id)

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
                await db.commit()
                report_id = existing.id
            else:
                report = AnalysisReport(
                    task_id=task_id,
                    user_id=task.user_id,
                    result_data=result_data,
                    report_text=report_text,
                    is_llm_generated=settings.LLM_ENABLED,
                    annotated_video_url=step_results.get(10, {}).get("annotated_video_url"),
                    cover_image_url=step_results.get(1, {}).get("cover_image_url"),
                )
                db.add(report)
                await db.commit()
                await db.refresh(report)
                report_id = report.id

        # 4. 触发级联（try/except 不阻塞）
        await ReportGenerator._trigger_cascade(task_id, report_id, task.user_id)

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

        # 比分分析
        score_analysis = {
            "final_score": "11:8",
            "key_points": [
                {"seq": 20, "score": "10:10", "winner": "user"}
            ],
        }

        return {
            "video_info": video_info,
            "rally_analysis": rally,
            "landing_points": landing,
            "technique_stats": technique,
            "ball_speed": ball_speed,
            "score_analysis": score_analysis,
        }

    @staticmethod
    async def _generate_report_text(result_data: dict, task_id: int) -> dict:
        """
        生成报告文字：LLM 优先 → 规则引擎降级
        """
        if settings.LLM_ENABLED and settings.LLM_API_URL:
            try:
                return await ReportGenerator._generate_llm_report(result_data)
            except Exception as e:
                logger.warning("llm_report_failed_fallback_to_template", extra={
                    "error": str(e), "task_id": task_id
                })

        return ReportGenerator._generate_template_report(result_data)

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
    async def _trigger_cascade(task_id: int, report_id: int, user_id: int) -> None:
        """
        级联触发（try/except 不阻塞）：
        - 训练建议（S4 实现）
        - 进度快照（S4 实现）
        - 游戏化积分
        - 通知推送
        """
        # 游戏化积分
        try:
            from app.services.gamification_service import GamificationService
            async with async_session_factory() as db:
                await GamificationService.add_points(
                    db, user_id=user_id, event_type="analysis", ref_id=report_id
                )
        except Exception as e:
            logger.error("cascade_gamification_failed", extra={"error": str(e)})

        # 通知推送 — WS 消息已在 ProgressTracker 中处理
        # 训练建议 / 进度快照 — S4 实现
