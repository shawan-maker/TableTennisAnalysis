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
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.progress import ProgressSnapshot, TechniqueTrend
from app.models.video_analysis import AnalysisReport, VideoTask

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
            await redis.delete(
                f"progress:summary:{user_id}",
                f"progress:trends:{user_id}",
                f"progress:problems:{user_id}",
            )
            # R7-Prog-3: 清理 trend_detail 缓存（键含 metric 名，需 scan）
            trend_detail_keys = await redis.keys(f"progress:trend_detail:{user_id}:*")
            if trend_detail_keys:
                await redis.delete(*trend_detail_keys)

        return {"id": snapshot.id, "report_id": report_id, "metrics_snapshot": metrics}

    @staticmethod
    def _extract_metrics(result_data: dict) -> dict:
        """从 result_data JSONB 提取 18 项指标 — 直接从 technique_stats 读取比率值"""
        if not result_data:
            return {k: None for k in METRIC_DEFINITIONS}

        tech = result_data.get("technique_stats") or result_data.get("technique_distribution") or {}
        landing = result_data.get("landing_points") or result_data.get("landing_heatmap") or {}
        dist = landing.get("distribution", {})
        rally = result_data.get("rally_analysis", {})
        speed = result_data.get("ball_speed", {})
        score = result_data.get("score_analysis", {})

        return {
            # 技术统计比率 — 直接从 technique_stats 读取
            "backhand_ratio":         tech.get("backhand_ratio"),
            "forehand_ratio":         tech.get("forehand_ratio"),
            "serve_ratio":            tech.get("serve_ratio"),
            # 落点分布
            "landing_forehand_pct":   dist.get("forehand"),
            "landing_backhand_pct":   dist.get("backhand"),
            "landing_middle_pct":     dist.get("middle"),
            "landing_dispersion":     landing.get("dispersion"),
            # 回合分析
            "avg_rally_length":       rally.get("avg_rally_length"),
            "max_rally_length":       rally.get("max_rally_length"),
            "rally_frequency":        rally.get("rally_frequency"),
            # 球速
            "avg_ball_speed":         speed.get("avg_speed_mps"),
            "max_ball_speed":         speed.get("max_speed_mps"),
            # 得分分析
            "score_win_rate":         score.get("win_rate"),
            "key_point_win_rate":     score.get("key_point_win_rate"),
            "serve_point_win_rate":   score.get("serve_point_win_rate"),
            "receive_point_win_rate": score.get("receive_point_win_rate"),
            # 其他
            "attack_transition_rate": result_data.get("attack_transition_rate"),
            "error_rate":             result_data.get("error_rate"),
        }

    @staticmethod
    async def _update_trends(db: AsyncSession, user_id: int, snapshot: ProgressSnapshot) -> None:
        """更新趋势表 - 基于历史快照重算（R4-Progress-1）"""
        # 读取所有历史快照（按时间升序）
        rows = await db.execute(
            select(ProgressSnapshot)
            .where(ProgressSnapshot.user_id == user_id)
            .order_by(ProgressSnapshot.created_at.asc())
        )
        all_snapshots = rows.scalars().all()
        if not all_snapshots:
            return

        metrics = snapshot.metrics_snapshot or {}

        for metric_name, value in metrics.items():
            defn = METRIC_DEFINITIONS.get(metric_name)
            if not defn:
                continue

            # 从完整快照序列提取 values 列表
            history_values: list[float] = []
            time_series = []
            for s in all_snapshots:
                s_metrics = s.metrics_snapshot or {}
                v = s_metrics.get(metric_name)
                if v is not None:
                    history_values.append(v)
                    time_series.append({
                        "date": s.created_at.isoformat() if s.created_at else "",
                        "value": v,
                    })

            if len(history_values) > 20:
                history_values = history_values[-20:]
                time_series = time_series[-20:]

            target = defn["target"]

            # 调用 _calculate_trend（R4-Progress-2 新签名）
            trend_info = ProgressService._calculate_trend(
                user_id, metric_name, value, history_values, target
            )

            # 计算 change_rate 与 previous_value
            # R12-Prog-2: value 为 None（指标消失，trend=resolved）时 change_rate 置 None，
            # 避免 None - float TypeError（_calculate_trend 有早退保护，此处原先没有）
            if value is not None and len(history_values) >= 2 and history_values[-2] != 0:
                change_rate = round((value - history_values[-2]) / abs(history_values[-2]), 4)
            else:
                change_rate = None
            previous_value = history_values[-2] if len(history_values) >= 2 else None

            # UPSERT
            existing = await db.scalar(
                select(TechniqueTrend).where(
                    and_(TechniqueTrend.user_id == user_id, TechniqueTrend.metric_name == metric_name)
                )
            )

            if existing:
                existing.current_value = value
                existing.previous_value = previous_value
                existing.change_rate = change_rate
                existing.trend = trend_info["trend"]
                existing.persistence_count = trend_info["persistence_count"]
                existing.target_value = target
                existing.time_series = time_series
            else:
                tt = TechniqueTrend(
                    user_id=user_id,
                    metric_name=metric_name,
                    current_value=value,
                    previous_value=previous_value,
                    change_rate=change_rate,
                    trend=trend_info["trend"],
                    target_value=target,
                    persistence_count=trend_info["persistence_count"],
                    time_series=time_series,
                )
                db.add(tt)

    @staticmethod
    def _calculate_trend(
        user_id: int, metric_name: str, current_value: float,
        history_values: list[float], target_value: float
    ) -> dict:
        """计算趋势方向 - 基于历史值序列（R4-Progress-2）

        新签名兼容设计测试用例：persistence >= 2 约束加到 improving/declining；
        stagnant 分支死代码已修复。
        """
        # R7-Prog-1 + R12-Prog-2: current_value 为 None 时不再统一返回 new：
        # 历史有值但当前消失 → resolved（问题已解决，设计 6 种趋势类型之一）；
        # 无历史 → new（首次出现，当前值尚缺）
        if current_value is None:
            if history_values:
                return {"trend": "resolved", "persistence_count": 0}
            return {"trend": "new", "persistence_count": 0}
        if len(history_values) < 2:
            return {"trend": "new", "persistence_count": 0}

        defn = METRIC_DEFINITIONS.get(metric_name, {})
        direction = defn.get("direction", "up")

        previous = history_values[-2]
        if previous == 0:
            change_rate = None
        else:
            change_rate = round((current_value - previous) / abs(previous), 4)

        is_improving = (
            (direction == "up" and current_value > previous) or
            (direction == "down" and current_value < previous)
        )
        is_declining = (
            (direction == "up" and current_value < previous) or
            (direction == "down" and current_value > previous)
        )
        is_significant = abs(change_rate or 0) > CHANGE_RATE_THRESHOLD

        # 达标判断 - 基于历史值连续达标次数
        achieved_persistence = 0
        for v in reversed(history_values):
            if (direction == "up" and v >= target_value) or (direction == "down" and v <= target_value):
                achieved_persistence += 1
            else:
                break
        if achieved_persistence >= 2:
            return {"trend": "achieved", "persistence_count": achieved_persistence}

        # improving: 需 persistence >= 2
        if is_improving and is_significant:
            improving_persistence = 0
            for i in range(len(history_values) - 1, 0, -1):
                v_curr = history_values[i]
                v_prev = history_values[i - 1]
                if (direction == "up" and v_curr > v_prev) or (direction == "down" and v_curr < v_prev):
                    improving_persistence += 1
                else:
                    break
            if improving_persistence >= 2:
                return {"trend": "improving", "persistence_count": improving_persistence}

        # declining: 需 persistence >= 2
        if not is_improving and is_significant:
            declining_persistence = 0
            for i in range(len(history_values) - 1, 0, -1):
                v_curr = history_values[i]
                v_prev = history_values[i - 1]
                if (direction == "up" and v_curr < v_prev) or (direction == "down" and v_curr > v_prev):
                    declining_persistence += 1
                else:
                    break
            if declining_persistence >= 2:
                return {"trend": "declining", "persistence_count": declining_persistence}

        # stagnant: not is_significant 且 len>=4 且 persistence>=3
        if not is_significant:
            stagnant_persistence = 0
            for i in range(len(history_values) - 1, 0, -1):
                v_curr = history_values[i]
                v_prev = history_values[i - 1]
                rate = abs((v_curr - v_prev) / abs(v_prev)) if v_prev != 0 else 0
                if rate <= CHANGE_RATE_THRESHOLD:
                    stagnant_persistence += 1
                else:
                    break
            if len(history_values) >= 4 and stagnant_persistence >= 3:
                return {"trend": "stagnant", "persistence_count": stagnant_persistence}

        # R5-Prog-2: fallback - persistence 不足时按单次方向标记 improving/declining，
        # 避免误标单次改善/退步为 stagnant
        if is_improving:
            return {"trend": "improving", "persistence_count": 1}
        if is_declining:
            return {"trend": "declining", "persistence_count": 1}
        return {"trend": "stagnant", "persistence_count": 1}

    @staticmethod
    async def list_snapshots(user_id: int, period: str = "all", status: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
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

            # R5-Prog-1: 按 VideoTask.status 过滤（AnalysisReport 无 status 列，改走 task 关系）
            if status:
                qs = qs.join(AnalysisReport, ProgressSnapshot.report_id == AnalysisReport.id).join(
                    VideoTask, AnalysisReport.task_id == VideoTask.id
                ).where(VideoTask.status == status)
                count_qs = count_qs.join(AnalysisReport, ProgressSnapshot.report_id == AnalysisReport.id).join(
                    VideoTask, AnalysisReport.task_id == VideoTask.id
                ).where(VideoTask.status == status)

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
            direction = defn.get("direction", "up")
            # R7-Prog-2: None 不应被 or 0 强转为 0，down 指标会误判 100%
            if t.current_value is None:
                target_progress = None
            else:
                current = t.current_value
                if direction == "down":
                    target_progress = 100 if current == 0 else (min(100, int(target / current * 100)) if current > 0 else None)
                else:
                    target_progress = min(100, int(current / target * 100)) if target and target > 0 else None

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
        # R6-Prog-2: 仅当指标名不在 METRIC_DEFINITIONS 时返回 404；有效指标无趋势数据返回 null 字段
        if metric not in METRIC_DEFINITIONS:
            raise AppException("指标不存在", 404, code=40420)

        redis = await get_redis()
        cache_key = f"progress:trend_detail:{user_id}:{metric}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        defn = METRIC_DEFINITIONS[metric]
        default_target = defn.get("target", 0)
        direction = defn.get("direction", "up")

        async with async_session_factory() as db:
            t = await db.scalar(
                select(TechniqueTrend).where(
                    and_(TechniqueTrend.user_id == user_id, TechniqueTrend.metric_name == metric)
                )
            )

            if t:
                target = t.target_value or default_target
                # R6-Prog-3: down 指标 current==0 视为 100% 达成
                # R7-Prog-2: None 不应被 or 0 强转为 0，down 指标会误判 100%
                if t.current_value is None:
                    target_progress = None
                else:
                    current = t.current_value
                    if direction == "down":
                        target_progress = 100 if current == 0 else (min(100, int(target / current * 100)) if current > 0 else None)
                    else:
                        target_progress = min(100, int(current / target * 100)) if target > 0 else None

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
            else:
                # R6-Prog-2: 有效指标无趋势数据 — 返回 null 字段而非 None（不缓存空结果）
                result = {
                    "metric": metric,
                    "metric_name": defn.get("name", metric),
                    "current_value": None,
                    "target_value": default_target,
                    "target_progress": None,
                    "trend": None,
                    "change_rate": None,
                    "persistence_count": None,
                    "history": [],
                }

        if t:
            await redis.setex(cache_key, CACHE_TTL_TRENDS, json.dumps(result))
        return result

    @staticmethod
    async def get_comparison(user_id: int, report_a: int, report_b: int) -> Optional[dict]:
        if report_a == report_b:
            return None

        async with async_session_factory() as db:
            ra = await db.scalar(select(AnalysisReport).where(
                AnalysisReport.id == report_a, AnalysisReport.user_id == user_id
            ))
            rb = await db.scalar(select(AnalysisReport).where(
                AnalysisReport.id == report_b, AnalysisReport.user_id == user_id
            ))
            if not ra or not rb:
                return None

            sa = await db.scalar(select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_a))
            sb = await db.scalar(select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_b))

            metrics_a = sa.metrics_snapshot if sa else ProgressService._extract_metrics(ra.result_data or {})
            metrics_b = sb.metrics_snapshot if sb else ProgressService._extract_metrics(rb.result_data or {})

            def _dim(keys: list) -> dict:
                """生成单维度对比 - 支持 (metric_key, output_key) 映射（R4-Progress-8）"""
                result = {}
                for k in keys:
                    if isinstance(k, tuple):
                        metric_key, output_key = k
                    else:
                        metric_key = output_key = k
                    va = metrics_a.get(metric_key, 0)
                    vb = metrics_b.get(metric_key, 0)
                    change = round(vb - va, 4) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
                    result[output_key] = {"a": va, "b": vb, "change": change}
                return result

            # 6 维度对比（对齐设计文档）
            comparisons = {
                # 维度 1: 技术统计
                "technique_stats": _dim(["forehand_ratio", "backhand_ratio", "serve_ratio"]),
                # 维度 2: 落点分布（R4-Progress-8: key 名改为 forehand_pct/backhand_pct/middle_pct）
                "landing": _dim([
                    ("landing_forehand_pct", "forehand_pct"),
                    ("landing_backhand_pct", "backhand_pct"),
                    ("landing_middle_pct", "middle_pct"),
                ]),
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
                target = t.target_value or defn.get("target", 0)
                direction = defn.get("direction", "up")
                # R7-Prog-2: None 不应被 or 0 强转为 0，down 指标会误判 100%
                if t.current_value is None:
                    target_progress = None
                else:
                    current = t.current_value
                    if direction == "down":
                        target_progress = 100 if current == 0 else (min(100, int(target / current * 100)) if current > 0 else None)
                    else:
                        target_progress = min(100, int(current / target * 100)) if target and target > 0 else None
                metric_trends.append({
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

            problem_changes = await ProgressService._get_problem_changes(db, user_id)
            forecast = await ProgressService._linear_regression_forecast(db, user_id)

            # 查询用户当前训练方案状态（R4-Progress-4: 添加 last_adjustment/adjustment_reason/goal_completion）
            from app.models.training import TrainingPlan, PlanAdjustment
            plan = await db.scalar(
                select(TrainingPlan)
                .where(TrainingPlan.user_id == user_id)
                .order_by(TrainingPlan.updated_at.desc())
                .limit(1)
            )
            if plan:
                # 查询最近一次 PlanAdjustment 记录
                adj = await db.scalar(
                    select(PlanAdjustment)
                    .where(PlanAdjustment.training_plan_id == plan.id)
                    .order_by(PlanAdjustment.created_at.desc())
                    .limit(1)
                )
                # R5-Prog-3: 计算 goal_completion — 按 direction 区分计算
                # up: current/target, down: target/current；返回字符串格式如 "91%"
                goal_metrics = plan.goal_metrics or {}
                trends_map = {t.metric_name: t for t in trends}
                goal_completion = {}
                for metric, target in goal_metrics.items():
                    t = trends_map.get(metric)
                    defn = METRIC_DEFINITIONS.get(metric, {})
                    direction = defn.get("direction", "up")
                    if t and t.current_value is not None and target:
                        if direction == "down":
                            progress = 100 if t.current_value == 0 else min(100, int(target / t.current_value * 100))
                        else:
                            progress = min(100, int(t.current_value / target * 100)) if t.current_value > 0 else 0
                        goal_completion[metric] = f"{progress}%"
                    else:
                        goal_completion[metric] = "0%"
                training_plan_status = {
                    "current_plan_id": str(plan.id),
                    "plan_version": plan.version,
                    "last_adjustment": adj.created_at.isoformat() if adj and adj.created_at else None,
                    "adjustment_reason": adj.adjustment_reason if adj else None,
                    "goal_completion": goal_completion,
                }
            else:
                training_plan_status = None

        result = {
            "summary_period": "no_data" if total <= 0 else "recent" if total <= 3 else "last_3_months",
            "total_analyses": total,
            "overall_progress": overall,
            "metric_trends": metric_trends,
            "problem_changes": {
                "new": [p.get("problem_name", str(p)) if isinstance(p, dict) else str(p) for p in problem_changes.get("new", [])],
                "resolved": [p.get("problem_name", str(p)) if isinstance(p, dict) else str(p) for p in problem_changes.get("resolved", [])],
                "persistent": [p.get("problem_name", str(p)) if isinstance(p, dict) else str(p) for p in problem_changes.get("persistent", [])],
            },
            "training_plan_status": training_plan_status,
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

        # R4-Progress-5: API 设计要求 list[str]，返回问题标识列表
        return {
            "new": list(issues_b - issues_a),
            "resolved": list(issues_a - issues_b),
            "persistent": list(issues_a & issues_b),
        }

    @staticmethod
    async def _linear_regression_forecast(db: AsyncSession, user_id: int) -> dict:
        """线性回归预测 — 基于 TechniqueTrend.time_series 预测到达目标周数"""
        trends = await db.execute(
            select(TechniqueTrend).where(TechniqueTrend.user_id == user_id)
        )
        rows = trends.scalars().all()
        if not rows:
            return {}

        forecast = {}
        for t in rows:
            series = t.time_series or []
            # R4-Progress-3: 数据点阈值从 2 改为 3
            if len(series) < 3:
                continue

            # 简单线性回归: y = slope * x + intercept
            n = len(series)
            x_vals = list(range(n))
            y_vals = [float(v["value"]) for v in series if isinstance(v, dict) and v.get("value") is not None]

            # R4-Progress-3: 数据点阈值从 2 改为 3
            if len(y_vals) < 3:
                continue

            m = len(y_vals)
            sum_x = sum(x_vals[:m])
            sum_y = sum(y_vals)
            sum_xy = sum(x * y for x, y in zip(x_vals[:m], y_vals))
            sum_x2 = sum(x * x for x in x_vals[:m])

            denominator = m * sum_x2 - sum_x * sum_x
            if denominator == 0:
                continue

            slope = (m * sum_xy - sum_x * sum_y) / denominator
            intercept = (sum_y - slope * sum_x) / m

            # 计算 R²
            y_mean = sum_y / m
            ss_tot = sum((y - y_mean) ** 2 for y in y_vals)
            ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(x_vals[:m], y_vals))
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            # R² 阈值过滤：低质量数据不预测
            if r_squared < 0.4:
                continue

            # 预测到达目标的周数
            target = t.target_value
            predicted_weeks = None
            # R7-Prog-4: slope 检查改为方向感知
            # up 指标 slope > 0 表示改善；down 指标 slope < 0 表示改善（向目标下降）
            direction = METRIC_DEFINITIONS.get(t.metric_name, {}).get("direction", "up")
            if target and direction == "up" and slope > 0:
                # y = slope * x + intercept → x = (target - intercept) / slope
                weeks_to_target = (target - intercept) / slope
                if weeks_to_target > 0:
                    predicted_weeks = int(weeks_to_target * 2)
            elif target and direction == "down" and slope < 0:
                # down 指标：slope < 0 表示改善（下降），用 abs(slope) 计算周数
                weeks_to_target = (intercept - target) / abs(slope)
                if weeks_to_target > 0:
                    predicted_weeks = int(weeks_to_target * 2)

            confidence = "high" if r_squared > 0.7 else "medium"

            forecast[t.metric_name] = {
                "predicted_weeks_to_target": predicted_weeks,
                "confidence": confidence,
                "r_squared": round(r_squared, 4),
            }

        return forecast
