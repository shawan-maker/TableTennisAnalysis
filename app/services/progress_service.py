"""
app/services/progress_service.py - 进度分析业务逻辑层

依据：切片 08-progress_analysis/backend.md 4
功能：快照生成 + 趋势计算 + 报告对比 + 综合摘要 + 问题变化
缓存：summary 5min / trends+trend_detail+problems 1h
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.progress import ProgressSnapshot, TechniqueTrend
from app.models.video_analysis import AnalysisReport

logger = logging.getLogger(__name__)

CHANGE_RATE_THRESHOLD = 0.05
R_SQUARED_THRESHOLD = 0.4

METRIC_DEFINITIONS = {
    "backhand_ratio": {"name": "反手使用率", "target": 0.35, "direction": "up"},
    "forehand_ratio": {"name": "正手使用率", "target": 0.60, "direction": "down"},
    "serve_ratio": {"name": "发球使用率", "target": 0.05, "direction": "down"},
    "landing_forehand_pct": {"name": "正手区落点率", "target": 0.55, "direction": "down"},
    "landing_backhand_pct": {"name": "反手区落点率", "target": 0.30, "direction": "up"},
    "landing_middle_pct": {"name": "中路落点率", "target": 0.15, "direction": "up"},
    "landing_dispersion": {"name": "落点分散度", "target": 2.5, "direction": "down"},
    "avg_rally_length": {"name": "平均回合长度", "target": 6.0, "direction": "up"},
    "max_rally_length": {"name": "最长回合长度", "target": 15.0, "direction": "up"},
    "rally_frequency": {"name": "回合频率", "target": 1.5, "direction": "up"},
    "avg_ball_speed": {"name": "平均球速", "target": 20.0, "direction": "up"},
    "max_ball_speed": {"name": "最大球速", "target": 26.0, "direction": "up"},
    "score_win_rate": {"name": "胜率", "target": 0.60, "direction": "up"},
    "key_point_win_rate": {"name": "关键分胜率", "target": 0.55, "direction": "up"},
    "serve_point_win_rate": {"name": "发球得分率", "target": 0.60, "direction": "up"},
    "receive_point_win_rate": {"name": "接发球得分率", "target": 0.50, "direction": "up"},
    "attack_transition_rate": {"name": "攻防转换率", "target": 0.40, "direction": "up"},
    "error_rate": {"name": "失误率", "target": 0.08, "direction": "down"},
}

CACHE_TTL_SUMMARY = 300
CACHE_TTL_TRENDS = 3600
CACHE_TTL_PROBLEMS = 3600


class ProgressService:
    """进度分析业务逻辑层"""

    @staticmethod
    async def generate_snapshot(user_id: int, report_id: int, result_data: dict) -> Optional[dict]:
        """从分析报告 result_data 提取 18 项指标，生成快照"""
        metrics = ProgressService._extract_metrics(result_data)

        async with async_session_factory() as db:
            existing = await db.scalar(
                select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_id)
            )
            if existing:
                return {"id": existing.id, "report_id": report_id, "metrics_snapshot": metrics}

            snapshot = ProgressSnapshot(
                user_id=user_id,
                report_id=report_id,
                metrics_snapshot=metrics,
            )
            db.add(snapshot)
            await db.flush()

            await ProgressService._update_trends(db, user_id, snapshot)

            await db.commit()

            # 清理缓存
            redis = await get_redis()
            await redis.delete(f"progress:summary:{user_id}", f"progress:trends:{user_id}")

        return {"id": snapshot.id, "report_id": report_id, "metrics_snapshot": metrics}

    @staticmethod
    def _extract_metrics(result_data: dict) -> dict:
        """从 result_data JSONB 提取 18 项指标"""
        if not result_data:
            return {k: 0.0 for k in METRIC_DEFINITIONS}

        technique = result_data.get("technique_stats") or result_data.get("technique_distribution") or {}
        total_tech = sum(technique.values()) or 1
        landing = result_data.get("landing_points") or result_data.get("landing_heatmap") or {}
        dist = landing.get("distribution", {})
        metrics_data = result_data.get("metrics", {})
        rally = result_data.get("rally_analysis", {})
        ball_speed = result_data.get("ball_speed", {})
        score = result_data.get("score_analysis", {})

        return {
            "backhand_ratio": round(technique.get("backhand_drive", 0) / total_tech, 4) if total_tech else 0.0,
            "forehand_ratio": round(technique.get("forehand_drive", 0) / total_tech, 4) if total_tech else 0.0,
            "serve_ratio": round(technique.get("serve", 0) / total_tech, 4) if total_tech else 0.0,
            "landing_forehand_pct": dist.get("forehand", metrics_data.get("landing_forehand_pct", 0)) or 0,
            "landing_backhand_pct": dist.get("backhand", metrics_data.get("landing_backhand_pct", 0)) or 0,
            "landing_middle_pct": dist.get("middle", metrics_data.get("landing_middle_pct", 0)) or 0,
            "landing_dispersion": metrics_data.get("landing_dispersion", 2.0),
            "avg_rally_length": rally.get("avg_rally_length", 0) or 0,
            "max_rally_length": rally.get("max_rally_length", 0) or 0,
            "rally_frequency": rally.get("rally_frequency", metrics_data.get("rally_frequency", 0)) or 0,
            "avg_ball_speed": ball_speed.get("avg_speed_mps", 0) or 0,
            "max_ball_speed": ball_speed.get("max_speed_mps", 0) or 0,
            "score_win_rate": score.get("win_rate", metrics_data.get("score_win_rate", 0)) or 0,
            "key_point_win_rate": score.get("key_point_win_rate", metrics_data.get("key_point_win_rate", 0)) or 0,
            "serve_point_win_rate": score.get("serve_point_win_rate", metrics_data.get("serve_point_win_rate", 0)) or 0,
            "receive_point_win_rate": score.get("receive_point_win_rate", metrics_data.get("receive_point_win_rate", 0)) or 0,
            "attack_transition_rate": metrics_data.get("attack_transition_rate", 0) or 0,
            "error_rate": metrics_data.get("error_rate", 0) or 0,
        }

    @staticmethod
    async def _update_trends(db: AsyncSession, user_id: int, snapshot: ProgressSnapshot) -> None:
        """更新趋势表 - UPSERT"""
        metrics = snapshot.metrics_snapshot or {}

        for metric_name, value in metrics.items():
            defn = METRIC_DEFINITIONS.get(metric_name)
            if not defn:
                continue

            existing = await db.scalar(
                select(TechniqueTrend).where(
                    and_(TechniqueTrend.user_id == user_id, TechniqueTrend.metric_name == metric_name)
                )
            )

            if existing:
                existing.previous_value = existing.current_value
                existing.current_value = value
                if existing.previous_value and existing.previous_value != 0:
                    existing.change_rate = round((value - existing.previous_value) / abs(existing.previous_value), 4)
                else:
                    existing.change_rate = None

                # 计算趋势
                history = existing.time_series or []
                history.append({"date": snapshot.created_at.isoformat() if snapshot.created_at else "", "value": value})
                if len(history) > 20:
                    history = history[-20:]

                trend_info = ProgressService._calculate_trend(
                    value, existing.previous_value, existing.change_rate,
                    history, defn["target"], defn["direction"], existing.persistence_count
                )
                existing.trend = trend_info["trend"]
                existing.persistence_count = trend_info["persistence_count"]
                existing.target_value = defn["target"]
                existing.time_series = history
            else:
                tt = TechniqueTrend(
                    user_id=user_id,
                    metric_name=metric_name,
                    current_value=value,
                    previous_value=None,
                    change_rate=None,
                    trend="new",
                    target_value=defn["target"],
                    persistence_count=0,
                    time_series=[{"date": snapshot.created_at.isoformat() if snapshot.created_at else "", "value": value}],
                )
                db.add(tt)

    @staticmethod
    def _calculate_trend(
        current: float, previous: Optional[float], change_rate: Optional[float],
        history: list, target: float, direction: str, current_persistence: int
    ) -> dict:
        """计算趋势方向"""
        if previous is None:
            return {"trend": "new", "persistence_count": 0}

        is_improving = (
            (direction == "up" and current > previous) or
            (direction == "down" and current < previous)
        )
        is_significant = abs(change_rate or 0) > CHANGE_RATE_THRESHOLD

        if direction == "up" and current >= target:
            persistence = current_persistence + 1
            if persistence >= 2:
                return {"trend": "achieved", "persistence_count": persistence}
        elif direction == "down" and current <= target:
            persistence = current_persistence + 1
            if persistence >= 2:
                return {"trend": "achieved", "persistence_count": persistence}

        if is_improving and is_significant:
            persistence = current_persistence + 1
            return {"trend": "improving", "persistence_count": persistence}
        elif not is_significant:
            persistence = current_persistence + 1
            if persistence >= 3:
                return {"trend": "stagnant", "persistence_count": persistence}
            return {"trend": "stagnant", "persistence_count": persistence}
        else:
            persistence = current_persistence + 1
            return {"trend": "declining", "persistence_count": persistence}

    @staticmethod
    async def list_snapshots(user_id: int, period: str = "all", page: int = 1, page_size: int = 20) -> dict:
        async with async_session_factory() as db:
            qs = select(ProgressSnapshot).where(ProgressSnapshot.user_id == user_id)
            count_qs = select(func.count()).select_from(ProgressSnapshot).where(
                ProgressSnapshot.user_id == user_id
            )

            if period != "all":
                now = datetime.now(timezone.utc)
                days = {"month": 30, "quarter": 90, "year": 365}.get(period, 30)
                start = now - timedelta(days=days)
                qs = qs.where(ProgressSnapshot.created_at >= start)
                count_qs = count_qs.where(ProgressSnapshot.created_at >= start)

            total = await db.scalar(count_qs) or 0
            qs = qs.order_by(ProgressSnapshot.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            rows = await db.execute(qs)
            items = [
                {
                    "id": r.id,
                    "report_id": r.report_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "metrics_snapshot": r.metrics_snapshot,
                }
                for r in rows.scalars().all()
            ]

        return {"total": total, "page": page, "page_size": page_size, "items": items}

    @staticmethod
    async def get_technique_trends(user_id: int) -> dict:
        redis = await get_redis()
        cache_key = f"progress:trends:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            rows = await db.execute(
                select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
            )
            trends = rows.scalars().all()

        metrics = []
        for t in trends:
            defn = METRIC_DEFINITIONS.get(t.metric_name, {})
            target = t.target_value or defn.get("target")
            current = t.current_value or 0
            target_progress = min(100, int(current / target * 100)) if target and target > 0 else 0

            metrics.append({
                "metric": t.metric_name,
                "metric_name": defn.get("name", t.metric_name),
                "current_value": t.current_value,
                "previous_value": t.previous_value,
                "change_rate": t.change_rate,
                "trend": t.trend,
                "target": target,
                "target_progress": target_progress,
                "persistence_count": t.persistence_count,
            })

        result = {"metrics": metrics}
        await redis.setex(cache_key, CACHE_TTL_TRENDS, json.dumps(result))
        return result

    @staticmethod
    async def get_technique_trend_detail(user_id: int, metric: str) -> Optional[dict]:
        redis = await get_redis()
        cache_key = f"progress:trend_detail:{user_id}:{metric}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            t = await db.scalar(
                select(TechniqueTrend).where(
                    and_(TechniqueTrend.user_id == user_id, TechniqueTrend.metric_name == metric)
                )
            )
            if not t:
                return None

            defn = METRIC_DEFINITIONS.get(metric, {})
            target = t.target_value or defn.get("target", 0)
            current = t.current_value or 0
            target_progress = min(100, int(current / target * 100)) if target > 0 else 0

            result = {
                "metric": metric,
                "metric_name": defn.get("name", metric),
                "current_value": t.current_value,
                "target_value": target,
                "target_progress": target_progress,
                "trend": t.trend,
                "change_rate": t.change_rate,
                "persistence_count": t.persistence_count,
                "history": t.time_series or [],
            }

        await redis.setex(cache_key, CACHE_TTL_TRENDS, json.dumps(result))
        return result

    @staticmethod
    async def get_comparison(user_id: int, report_a: int, report_b: int) -> Optional[dict]:
        if report_a == report_b:
            return None

        async with async_session_factory() as db:
            ra = await db.scalar(select(AnalysisReport).where(AnalysisReport.id == report_a))
            rb = await db.scalar(select(AnalysisReport).where(AnalysisReport.id == report_b))
            if not ra or not rb:
                return None

            sa = await db.scalar(select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_a))
            sb = await db.scalar(select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_b))

            metrics_a = sa.metrics_snapshot if sa else ProgressService._extract_metrics(ra.result_data or {})
            metrics_b = sb.metrics_snapshot if sb else ProgressService._extract_metrics(rb.result_data or {})

            technique_stats = {}
            for k in metrics_a:
                va = metrics_a.get(k, 0)
                vb = metrics_b.get(k, 0)
                change = round(vb - va, 4) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
                technique_stats[k] = {"a": va, "b": vb, "change": change}

            problems_a = (ra.report_text or {}).get("issues", [])
            problems_b = (rb.report_text or {}).get("issues", [])
            problems_a_ids = {p.get("problem_id", p) if isinstance(p, dict) else p for p in problems_a}
            problems_b_ids = {p.get("problem_id", p) if isinstance(p, dict) else p for p in problems_b}

            new = list(problems_b_ids - problems_a_ids)
            resolved = list(problems_a_ids - problems_b_ids)
            persistent = list(problems_a_ids & problems_b_ids)

        return {
            "report_a": {"id": report_a, "created_at": ra.created_at.isoformat() if ra.created_at else None},
            "report_b": {"id": report_b, "created_at": rb.created_at.isoformat() if rb.created_at else None},
            "comparisons": {
                "technique_stats": technique_stats,
                "problem_changes": {"new": new, "resolved": resolved, "persistent": persistent},
            },
        }

    @staticmethod
    async def get_summary(user_id: int) -> dict:
        redis = await get_redis()
        cache_key = f"progress:summary:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            total = await db.scalar(
                select(func.count()).select_from(ProgressSnapshot).where(ProgressSnapshot.user_id == user_id)
            ) or 0

            trends_rows = await db.execute(
                select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
            )
            trends = trends_rows.scalars().all()

            improving = sum(1 for t in trends if t.trend == "improving")
            declining = sum(1 for t in trends if t.trend == "declining")
            if improving > declining:
                overall = "improving"
            elif declining > improving:
                overall = "declining"
            else:
                overall = "stagnant"

            metric_trends = []
            for t in trends:
                defn = METRIC_DEFINITIONS.get(t.metric_name, {})
                metric_trends.append({
                    "metric": t.metric_name,
                    "metric_name": defn.get("name", t.metric_name),
                    "current_value": t.current_value,
                    "previous_value": t.previous_value,
                    "change_rate": t.change_rate,
                    "trend": t.trend,
                    "target": t.target_value,
                    "target_progress": 0,
                    "persistence_count": t.persistence_count,
                })

            problem_changes = await ProgressService._get_problem_changes(db, user_id)
            forecast = await ProgressService._linear_regression_forecast(db, user_id)

        result = {
            "summary_period": "all",
            "total_analyses": total,
            "overall_progress": overall,
            "metric_trends": metric_trends,
            "problem_changes": problem_changes,
            "training_plan_status": None,
            "forecast": forecast,
        }

        await redis.setex(cache_key, CACHE_TTL_SUMMARY, json.dumps(result))
        return result

    @staticmethod
    async def get_problem_changes(user_id: int) -> dict:
        redis = await get_redis()
        cache_key = f"progress:problems:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            result = await ProgressService._get_problem_changes(db, user_id)

        await redis.setex(cache_key, CACHE_TTL_PROBLEMS, json.dumps(result))
        return result

    @staticmethod
    async def _get_problem_changes(db: AsyncSession, user_id: int) -> dict:
        reports = await db.execute(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user_id)
            .order_by(AnalysisReport.created_at.desc())
            .limit(20)
        )
        all_reports = reports.scalars().all()
        if not all_reports:
            return {"new": [], "resolved": [], "persistent": []}

        latest_issues = set()
        older_issues = set()

        for i, r in enumerate(all_reports):
            issues = (r.report_text or {}).get("issues", [])
            issue_ids = {p.get("problem_id", p) if isinstance(p, dict) else p for p in issues}
            if i < 2:
                latest_issues |= issue_ids
            else:
                older_issues |= issue_ids

        new_ids = latest_issues - older_issues
        resolved_ids = older_issues - latest_issues
        persistent_ids = latest_issues & older_issues

        return {
            "new": list(new_ids),
            "resolved": list(resolved_ids),
            "persistent": list(persistent_ids),
        }

    @staticmethod
    async def _linear_regression_forecast(db: AsyncSession, user_id: int) -> dict:
        """线性回归预测 — 基于 TechniqueTrend.time_series 预测未来 7 天指标趋势"""
        trends = await db.execute(
            select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
        )
        rows = trends.scalars().all()
        if not rows:
            return {}

        forecast = {}
        for t in rows:
            series = t.time_series or []
            if len(series) < 2:
                continue

            # 简单线性回归: y = slope * x + intercept
            n = len(series)
            x_vals = list(range(n))
            y_vals = [float(v) for v in series if v is not None]

            if len(y_vals) < 2:
                continue

            sum_x = sum(x_vals[:len(y_vals)])
            sum_y = sum(y_vals)
            sum_xy = sum(x * y for x, y in zip(x_vals[:len(y_vals)], y_vals))
            sum_x2 = sum(x * x for x in x_vals[:len(y_vals)])

            denominator = n * sum_x2 - sum_x * sum_x
            if denominator == 0:
                continue

            slope = (n * sum_xy - sum_x * sum_y) / denominator
            intercept = (sum_y - slope * sum_x) / n

            # 预测未来 7 个时间点
            forecast_x = n + 7
            predicted = slope * forecast_x + intercept

            # 趋势方向判断
            if slope > 0.01:
                direction = "improving"
            elif slope < -0.01:
                direction = "declining"
            else:
                direction = "stable"

            forecast[t.metric_name] = {
                "current": t.current_value,
                "predicted_7d": round(predicted, 2),
                "slope": round(slope, 4),
                "direction": direction,
                "confidence": "low" if len(y_vals) < 5 else "medium" if len(y_vals) < 10 else "high",
            }

        return forecast
