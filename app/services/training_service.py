"""
app/services/training_service.py - 训练建议业务逻辑层

依据：切片 07-training_advice/backend.md 4
功能：基于报告的训练建议 + 综合建议 + 模板查询 + 方案调整 + 训练单管理
"""

import copy
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.models.knowledge_base import RuleDefinition, TrainingTemplate
from app.models.progress import TechniqueTrend
from app.models.training import PlanAdjustment, TrainingPlan
from app.models.video_analysis import AnalysisReport
from app.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)

STAGNANT_THRESHOLD = 3


class TrainingAdviceService:
    """训练建议业务逻辑层"""

    @staticmethod
    async def get_advice_by_report(user_id: int, report_id: int) -> dict:
        async with async_session_factory() as db:
            report = await db.scalar(
                select(AnalysisReport).where(
                    and_(AnalysisReport.id == report_id, AnalysisReport.user_id == user_id)
                )
            )
            if not report:
                raise AppException("报告不存在", 404, code=40412)

            # 是否首次分析
            count = await db.scalar(
                select(func.count()).select_from(AnalysisReport).where(AnalysisReport.user_id == user_id)
            ) or 0
            is_first = count <= 1

            # 提取指标
            from app.services.progress_service import ProgressService
            metrics = ProgressService._extract_metrics(report.result_data or {})

            # 获取趋势
            trends = await TrainingAdviceService._get_trends(db, user_id)

            # 构建规则上下文
            trend_ctx = {}
            for t in trends:
                trend_ctx[t.metric_name] = {
                    "direction": t.trend or "",
                    "persistence": t.persistence_count,
                    "change_rate": t.change_rate or 0,
                }

            ctx = {"metrics": metrics, "trends": trend_ctx, "current_plan": None}

            # 匹配规则
            matches = await KnowledgeBaseService.match_rules(db, ctx)

            diagnosis = []
            suggestions = []
            training_methods = []
            plan_template = None

            for m in matches:
                diagnosis.append({
                    "problem_id": m["problem_id"],
                    "problem_name": m["problem_name"],
                    "severity": m["severity"],
                    "trend": trend_ctx.get(
                        next(iter([k for k, v in trend_ctx.items() if v.get("direction")]), ""),
                        {}
                    ).get("direction", "new"),
                    "description": m["suggestion"],
                })

                if is_first:
                    sug_type = "first_analysis"
                elif m["rule_type"] == "trend_improving":
                    sug_type = "progress_confirm"
                elif m["rule_type"] == "trend_persistent":
                    sug_type = "persistent_warning"
                else:
                    sug_type = "new_issue"

                suggestions.append({"type": sug_type, "text": m["suggestion"]})

                for method_id in (m.get("training_methods") or []):
                    training_methods.append({
                        "method_id": method_id,
                        "name": method_id,
                        "description": "",
                    })

                if m.get("training_plan_template") and not plan_template:
                    plan_template = m["training_plan_template"]

            if is_first and not suggestions:
                suggestions.append({
                    "type": "first_analysis",
                    "text": "这是您的首次分析，建议关注基本技术动作。",
                })

        return {
            "report_id": report_id,
            "is_first_analysis": is_first,
            "diagnosis": diagnosis,
            "suggestions": suggestions,
            "training_methods": training_methods,
            "training_plan_template": plan_template,
        }

    @staticmethod
    async def get_contextual_advice(user_id: int) -> dict:
        async with async_session_factory() as db:
            latest = await db.scalar(
                select(AnalysisReport)
                .where(AnalysisReport.user_id == user_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(1)
            )
            if not latest:
                raise AppException("暂无分析报告", 404, code=40412)

        return await TrainingAdviceService.get_advice_by_report(user_id, latest.id)

    @staticmethod
    async def _get_trends(db: AsyncSession, user_id: int) -> list[TechniqueTrend]:
        rows = await db.execute(
            select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
        )
        return list(rows.scalars().all())

    @staticmethod
    async def get_templates(problem_id: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        async with async_session_factory() as db:
            qs = select(TrainingTemplate)
            count_qs = select(func.count()).select_from(TrainingTemplate)
            if problem_id:
                qs = qs.where(TrainingTemplate.problem_id == problem_id)
                count_qs = count_qs.where(TrainingTemplate.problem_id == problem_id)

            total = await db.scalar(count_qs) or 0
            qs = qs.order_by(TrainingTemplate.id).offset((page - 1) * page_size).limit(page_size)
            rows = await db.execute(qs)
            items = [
                {"id": r.id, "template_code": r.template_code, "name": r.name, "problem_id": r.problem_id}
                for r in rows.scalars().all()
            ]

        return {"total": total, "page": page, "page_size": page_size, "items": items}

    @staticmethod
    async def get_template_detail(template_id: int) -> Optional[dict]:
        async with async_session_factory() as db:
            row = await db.scalar(
                select(TrainingTemplate).where(TrainingTemplate.id == template_id)
            )
            if not row:
                return None
            return {
                "id": row.id,
                "template_code": row.template_code,
                "name": row.name,
                "problem_id": row.problem_id,
                "template_data": row.template_data,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    @staticmethod
    async def get_plan_adjustments(user_id: int, plan_id: int) -> dict:
        async with async_session_factory() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存在", 404, code=40420)

            rows = await db.execute(
                select(PlanAdjustment)
                .where(PlanAdjustment.training_plan_id == plan_id)
                .order_by(PlanAdjustment.created_at.desc())
            )
            adjustments = [
                {
                    "id": r.id,
                    "version": 0,
                    "action": r.adjustment_action,
                    "reason": r.adjustment_reason,
                    "trigger_report_id": r.trigger_report_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "changes_summary": "",
                }
                for r in rows.scalars().all()
            ]

        return {"plan_id": plan_id, "current_version": plan.version, "adjustments": adjustments}

    @staticmethod
    async def re_evaluate_plan(user_id: int, plan_id: int) -> dict:
        async with async_session_factory() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存在", 404, code=40420)

            trends = await TrainingAdviceService._get_trends(db, user_id)
            goal_metrics = plan.goal_metrics or {}

            action, reason = TrainingAdviceService._evaluate_plan_effectiveness(trends, goal_metrics)

            if action != "maintain":
                old_snapshot = plan.plan_data
                new_plan_data = TrainingAdviceService._generate_new_plan(plan, trends, goal_metrics, action)

                adjustment = PlanAdjustment(
                    training_plan_id=plan_id,
                    trigger_report_id=None,
                    old_plan_snapshot=old_snapshot,
                    new_plan_snapshot=new_plan_data,
                    adjustment_reason=reason,
                    adjustment_action=action,
                )
                db.add(adjustment)
                plan.plan_data = new_plan_data
                plan.version += 1

            await db.commit()

        return {"plan_id": plan_id, "action": action, "reason": reason}

    @staticmethod
    def _evaluate_plan_effectiveness(trends: list, goal_metrics: dict) -> tuple:
        declining = [t for t in trends if t.trend == "declining"]
        achieved = [t for t in trends if t.trend == "achieved"]
        stagnant = [t for t in trends if t.trend == "stagnant" and t.persistence_count >= STAGNANT_THRESHOLD]

        if achieved:
            return "new_goal", "已有指标达成目标，建议设定新目标"
        if declining:
            return "escalate", "指标下降趋势，建议升级训练强度"
        if stagnant:
            return "adjust", "连续多次无改善，建议调整方案"
        return "maintain", "指标改善中，保持当前方案"

    @staticmethod
    def _generate_new_plan(plan: TrainingPlan, trends: list, goal_metrics: dict, action: str) -> dict:
        old_data = plan.plan_data or {}
        new_data = dict(old_data)

        if action == "new_goal":
            goals = new_data.get("goal", {})
            if isinstance(goals, dict):
                for k, v in goals.items():
                    goals[k] = v * 1.1
            new_data["goal"] = goals
        elif action == "adjust":
            sessions = new_data.get("sessions", [])
            for s in sessions:
                if isinstance(s, dict) and "reps" in s:
                    s["reps"] = int(s["reps"] * 1.2)
            new_data["sessions"] = sessions
        elif action == "escalate":
            sessions = new_data.get("sessions", [])
            for s in sessions:
                if isinstance(s, dict) and "reps" in s:
                    s["reps"] = int(s["reps"] * 1.5)
            new_data["sessions"] = sessions

        return new_data

    @staticmethod
    async def list_training_sessions(
        user_id: int, plan_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        async with async_session_factory() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存在", 404, code=40420)

            plan_data = plan.plan_data or {}
            sessions = plan_data.get("sessions", [])
            total = len(sessions)

            offset = (page - 1) * page_size
            page_sessions = sessions[offset:offset + page_size]

            items = []
            for i, s in enumerate(page_sessions):
                if isinstance(s, dict):
                    items.append({
                        "id": offset + i + 1,
                        "plan_id": plan_id,
                        "name": s.get("name", f"训练单{i+1}"),
                        "is_completed": s.get("is_completed", False),
                        "scheduled_date": s.get("scheduled_date"),
                        "completed_at": s.get("completed_at"),
                        "session_index": offset + i,
                        "reps": s.get("reps", 0),
                    })

        return {"plan_id": plan_id, "total": total, "page": page, "page_size": page_size, "items": items}

    @staticmethod
    async def complete_training_session(
        user_id: int, plan_id: int, session_id: int
    ) -> dict:
        async with async_session_factory() as db:
            plan = await db.scalar(
                select(TrainingPlan).where(
                    and_(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
                )
            )
            if not plan:
                raise AppException("训练方案不存在", 404, code=40420)

            plan_data = copy.deepcopy(plan.plan_data or {})
            sessions = plan_data.get("sessions", [])

            if session_id < 1 or session_id > len(sessions):
                raise AppException("训练单不存在", 404, code=40422)

            session = sessions[session_id - 1]
            if not isinstance(session, dict):
                raise AppException("训练单不存在", 404, code=40422)

            if session.get("is_completed"):
                raise AppException("已完成", 409, code=40902)

            session["is_completed"] = True
            session["completed_at"] = datetime.now(timezone.utc).isoformat()

            completed = sum(1 for s in sessions if isinstance(s, dict) and s.get("is_completed"))
            progress = int(completed / len(sessions) * 100) if sessions else 0

            plan.plan_data = plan_data
            flag_modified(plan, "plan_data")

            # 触发积分
            points_earned = 0
            try:
                from app.services.gamification_service import GamificationService
                points_earned = await GamificationService.add_points(db, user_id, "training_session", session_id)
            except Exception as e:
                logger.warning("training_points_failed", extra={"error": str(e)})

            await db.commit()

        return {
            "session_id": session_id,
            "is_completed": True,
            "plan_progress": progress,
            "points_earned": points_earned,
            "completed_at": datetime.now(timezone.utc),
        }
