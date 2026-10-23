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
        """从 result_data JSONB 提取 18 项指标 — 直接从 technique_stats 读取比率值"""
        if not result_data:
            return {k: 0.0 for k in METRIC_DEFINITIONS}

        tech = result_data.get("technique_stats") or result_data.get("technique_distribution") or {}
        landing = result_data.get("landing_points") or result_data.get("landing_heatmap") or {}
        dist = landing.get("distribution", {})
        rally = result_data.get("rally_analysis", {})
        speed = result_data.get("ball_speed", {})
        score = result_data.get("score_analysis", {})

        return {
            # 技术统计比率 — 直接从 technique_stats 读取
            "backhand_ratio":         tech.get("backhand_ratio", tech.get("backhand_drive", 0) or 0),
            "forehand_ratio":         tech.get("forehand_ratio", tech.get("forehand_drive", 0) or 0),
            "serve_ratio":            tech.get("serve_ratio", tech.get("serve", 0) or 0),
            # 落点分布
            "landing_forehand_pct":   dist.get("forehand", 0) or 0,
            "landing_backhand_pct":   dist.get("backhand", 0) or 0,
            "landing_middle_pct":     dist.get("middle", 0) or 0,
            "landing_dispersion":     landing.get("dispersion", 2.0),
            # 回合分析
            "avg_rally_length":       rally.get("avg_rally_length", 0) or 0,
            "max_rally_length":       rally.get("max_rally_length", 0) or 0,
            "rally_frequency":        rally.get("rally_frequency", 0) or 0,
            # 球速
            "avg_ball_speed":         speed.get("avg_speed_mps", 0) or 0,
            "max_ball_speed":         speed.get("max_speed_mps", 0) or 0,
            # 得分分析
            "score_win_rate":         score.get("win_rate", 0) or 0,
            "key_point_win_rate":     score.get("key_point_win_rate", 0) or 0,
            "serve_point_win_rate":   score.get("serve_point_win_rate", 0) or 0,
            "receive_point_win_rate": score.get("receive_point_win_rate", 0) or 0,
            # 其他
            "attack_transition_rate": result_data.get("attack_transition_rate", 0) or 0,
            "error_rate":             result_data.get("error_rate", 0) or 0,
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
            # 设计要求：len(history)>=4 且 change_rate<5% 才判定为停滞
            if len(history) >= 4 and persistence >= 3:
                return {"trend": "stagnant", "persistence_count": persistence}
            return {"trend": "stable", "persistence_count": persistence}
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

            def _dim(keys: list[str]) -> dict:
                """生成单维度对比"""
                result = {}
                for k in keys:
                    va = metrics_a.get(k, 0)
                    vb = metrics_b.get(k, 0)
                    change = round(vb - va, 4) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
                    result[k] = {"a": va, "b": vb, "change": change}
                return result

            # 6 维度对比（对齐设计文档）
            comparisons = {
                # 维度 1: 技术统计
                "technique_stats": _dim(["forehand_ratio", "backhand_ratio", "serve_ratio"]),
                # 维度 2: 落点分布
                "landing": _dim(["landing_forehand_pct", "landing_backhand_pct", "landing_middle_pct"]),
                # 维度 3: 回合分析
                "rally": {
                    "avg_length_a": metrics_a.get("avg_rally_length"),
                    "avg_length_b": metrics_b.get("avg_rally_length"),
                    "max_length_a": metrics_a.get("max_rally_length"),
                    "max_length_b": metrics_b.get("max_rally_length"),
                    "change": round(
                        (metrics_b.get("avg_rally_length", 0) - metrics_a.get("avg_rally_length", 0)), 2
                    ) if metrics_a.get("avg_rally_length") is not None and metrics_b.get("avg_rally_length") is not None else None,
                },
                # 维度 4: 球速
                "ball_speed": {
                    "avg_a": metrics_a.get("avg_ball_speed"),
                    "avg_b": metrics_b.get("avg_ball_speed"),
                    "max_a": metrics_a.get("max_ball_speed"),
                    "max_b": metrics_b.get("max_ball_speed"),
                    "change": round(
                        (metrics_b.get("avg_ball_speed", 0) - metrics_a.get("avg_ball_speed", 0)), 2
                    ) if metrics_a.get("avg_ball_speed") is not None and metrics_b.get("avg_ball_speed") is not None else None,
                },
                # 维度 5: 得分分析
                "score_analysis": {
                    "win_rate_a": metrics_a.get("score_win_rate"),
                    "win_rate_b": metrics_b.get("score_win_rate"),
                    "change": round(
                        (metrics_b.get("score_win_rate", 0) - metrics_a.get("score_win_rate", 0)), 4
                    ) if metrics_a.get("score_win_rate") is not None and metrics_b.get("score_win_rate") is not None else None,
                },
                # 维度 6: 问题变化
                "problem_changes": await ProgressService._compute_problem_changes(db, user_id, ra, rb),
            }

        return {
            "report_a": {"id": report_a, "created_at": ra.created_at.isoformat() if ra.created_at else None},
            "report_b": {"id": report_b, "created_at": rb.created_at.isoformat() if rb.created_at else None},
            "comparisons": comparisons,
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
        """计算问题变化 — 返回 ProblemChangeItem 结构化对象"""
        reports = await db.execute(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user_id)
            .order_by(AnalysisReport.created_at.desc())
            .limit(10)
        )
        all_reports = reports.scalars().all()
        if not all_reports:
            return {"new": [], "resolved": [], "persistent": []}

        # 提取每份报告的问题列表
        all_issues = []
        for r in all_reports:
            report_text = r.report_text or {}
            if isinstance(report_text, str):
                try:
                    report_text = json.loads(report_text)
                except (json.JSONDecodeError, TypeError):
                    report_text = {}
            raw_issues = report_text.get("issues", []) if report_text else []
            # 提取问题标识（处理 dict 和 str 两种情况）
            issue_items = []
            for p in raw_issues:
                if isinstance(p, dict):
                    issue_items.append({
                        "id": p.get("problem_id", str(p.get("problem_name", p))),
                        "name": str(p.get("problem_name", p.get("problem_id", p))),
                    })
                else:
                    issue_items.append({"id": str(p), "name": str(p)})
            all_issues.append({
                "report_id": r.id,
                "created_at": r.created_at,
                "issues": issue_items,
            })

        # 只有 1 份报告时，所有问题视为首次出现
        if len(all_issues) == 1:
            first_report = all_issues[0]
            new_items = [
                {
                    "problem_id": f"PROBLEM_NEW_{i}",
                    "problem_name": item["name"],
                    "first_seen": first_report["created_at"].strftime("%Y-%m-%d") if first_report["created_at"] else None,
                    "last_seen": None,
                    "persistence_count": None,
                }
                for i, item in enumerate(first_report["issues"])
            ]
            return {"new": new_items, "resolved": [], "persistent": []}

        # 2+ 份报告：最新 vs 历史对比
        latest_issue_ids = set(i["id"] for i in all_issues[0]["issues"])
        previous_issue_ids = set()
        for a in all_issues[1:]:
            previous_issue_ids.update(i["id"] for i in a["issues"])

        new_ids = latest_issue_ids - previous_issue_ids
        resolved_ids = previous_issue_ids - latest_issue_ids
        persistent_ids = latest_issue_ids & previous_issue_ids

        # 构建 name 映射
        id_to_name = {}
        for a in all_issues:
            for i in a["issues"]:
                if i["id"] not in id_to_name:
                    id_to_name[i["id"]] = i["name"]

        # 构建 ProblemChangeItem 结构化对象
        new_items = [
            {
                "problem_id": f"PROBLEM_NEW_{i}",
                "problem_name": id_to_name.get(pid, str(pid)),
                "first_seen": all_issues[0]["created_at"].strftime("%Y-%m-%d") if all_issues[0]["created_at"] else None,
                "last_seen": None,
                "persistence_count": None,
            }
            for i, pid in enumerate(new_ids)
        ]
        resolved_items = [
            {
                "problem_id": f"PROBLEM_RESOLVED_{i}",
                "problem_name": id_to_name.get(pid, str(pid)),
                "first_seen": None,
                "last_seen": all_issues[1]["created_at"].strftime("%Y-%m-%d") if len(all_issues) > 1 and all_issues[1]["created_at"] else None,
                "persistence_count": None,
            }
            for i, pid in enumerate(resolved_ids)
        ]
        persistent_items = [
            {
                "problem_id": f"PROBLEM_PERSIST_{i}",
                "problem_name": id_to_name.get(pid, str(pid)),
                "first_seen": None,
                "last_seen": all_issues[0]["created_at"].strftime("%Y-%m-%d") if all_issues[0]["created_at"] else None,
                "persistence_count": sum(1 for a in all_issues if pid in set(i["id"] for i in a["issues"])),
            }
            for i, pid in enumerate(persistent_ids)
        ]

        return {
            "new": new_items,
            "resolved": resolved_items,
            "persistent": persistent_items,
        }

    @staticmethod
    async def _compute_problem_changes(
        db: AsyncSession, user_id: int, report_a: AnalysisReport, report_b: AnalysisReport
    ) -> dict:
        """两次报告对比的问题变化（get_comparison 维度 6）"""
        def _extract_issues(report: AnalysisReport) -> set:
            rt = report.report_text or {}
            if isinstance(rt, str):
                try:
                    rt = json.loads(rt)
                except (json.JSONDecodeError, TypeError):
                    rt = {}
            raw_issues = rt.get("issues", []) if rt else []
            # 处理 issues 为 dict 或 str 的情况
            ids = set()
            for p in raw_issues:
                if isinstance(p, dict):
                    ids.add(p.get("problem_id", str(p.get("problem_name", p))))
                else:
                    ids.add(str(p))
            return ids

        issues_a = _extract_issues(report_a)
        issues_b = _extract_issues(report_b)

        new_ids = issues_b - issues_a
        resolved_ids = issues_a - issues_b
        persistent_ids = issues_a & issues_b

        return {
            "new": [{"problem_id": f"NEW_{i}", "problem_name": str(p)} for i, p in enumerate(new_ids)],
            "resolved": [{"problem_id": f"RESOLVED_{i}", "problem_name": str(p)} for i, p in enumerate(resolved_ids)],
            "persistent": [{"problem_id": f"PERSIST_{i}", "problem_name": str(p)} for i, p in enumerate(persistent_ids)],
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
