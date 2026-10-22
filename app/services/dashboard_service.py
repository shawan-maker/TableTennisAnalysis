"""
app/services/dashboard_service.py — 数据看板业务逻辑层

依据：切片 06-data_dashboard/backend.md §5
功能：概览/战绩趋势/技术统计/落点热图/比赛记录列表 + Redis 缓存
缓存策略：overview 5min / trend+technique+heatmap 1h / match-records 不缓存
缓存 bust：分析完成 → overview/technique/heatmap；比赛结束 → overview/winrate
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, select, case, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.match import MatchRecord
from app.models.video_analysis import AnalysisReport
from app.schemas.dashboard import (
    AdviceSummaryBrief,
    LandingHeatmapResponse,
    MatchRecordBrief,
    MatchRecordsResponse,
    OverviewResponse,
    TechniqueItem,
    TechniqueStatsResponse,
    TrendSeries,
    WinRateTrendResponse,
)

logger = logging.getLogger(__name__)

# 缓存 TTL
CACHE_TTL_OVERVIEW = 300
CACHE_TTL_TREND = 3600
CACHE_TTL_TECHNIQUE = 3600
CACHE_TTL_HEATMAP = 3600

# 技术统计色彩映射
TECHNIQUE_COLORS = {
    "forehand_drive": ("正手攻球", "#E63946"),
    "backhand_drive": ("反手拨球", "#1D3557"),
    "forehand_loop": ("正手拉球", "#F4A261"),
    "serve": ("发球", "#2A9D8F"),
}


class DashboardService:
    """数据看板业务逻辑层"""

    # ========== 概览 ==========

    @staticmethod
    async def get_overview(user_id: int) -> dict:
        """概览卡片：胜率/分析次数/训练频次/连续天数/趋势。缓存 5min。"""
        redis = await get_redis()
        cache_key = f"dashboard:overview:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            # 比赛统计
            wins = await db.scalar(
                select(func.count()).select_from(MatchRecord).where(
                    and_(MatchRecord.user_id == user_id, MatchRecord.is_win.is_(True))
                )
            ) or 0
            losses = await db.scalar(
                select(func.count()).select_from(MatchRecord).where(
                    and_(MatchRecord.user_id == user_id, MatchRecord.is_win.is_(False))
                )
            ) or 0
            total_matches = wins + losses
            win_rate = round(wins / total_matches, 2) if total_matches > 0 else 0.0

            # 分析次数
            analysis_count = await db.scalar(
                select(func.count()).select_from(AnalysisReport).where(
                    AnalysisReport.user_id == user_id
                )
            ) or 0

            # 训练频次（最近 7 天比赛+分析）
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            week_matches = await db.scalar(
                select(func.count()).select_from(MatchRecord).where(
                    and_(MatchRecord.user_id == user_id, MatchRecord.match_date >= week_ago)
                )
            ) or 0
            week_reports = await db.scalar(
                select(func.count()).select_from(AnalysisReport).where(
                    and_(AnalysisReport.user_id == user_id, AnalysisReport.created_at >= week_ago)
                )
            ) or 0
            training_freq = week_matches + week_reports

            # 连续天数 — UserPoints 表 S4 才创建，当前返回 0
            streak_days = await DashboardService._get_streak_days(db, user_id)

            # 趋势
            trend = await DashboardService._calc_trend(db, user_id)

            # 最近训练建议摘要
            latest_advice = await DashboardService._get_latest_advice_summary(db, user_id)

        result = {
            "win_rate": win_rate,
            "wins": wins,
            "losses": losses,
            "analysis_count": analysis_count,
            "training_frequency_per_week": training_freq,
            "streak_days": streak_days,
            "trend": trend,
            "latest_advice_summary": latest_advice,
        }

        await redis.setex(cache_key, CACHE_TTL_OVERVIEW, json.dumps(result, default=str))
        return result

    # ========== 战绩趋势 ==========

    @staticmethod
    async def get_win_rate_trend(user_id: int, period: str = "month") -> dict:
        """战绩趋势折线图数据。缓存 1h。"""
        valid_periods = {"month": 30, "quarter": 90, "year": 365}
        days = valid_periods.get(period, valid_periods["month"])

        redis = await get_redis()
        cache_key = f"dashboard:winrate:{user_id}:{period}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)
            start_date = now - timedelta(days=days)

            stmt = (
                select(
                    func.date_trunc("day", MatchRecord.match_date).label("day"),
                    func.count().label("total"),
                    func.sum(
                        case((MatchRecord.is_win.is_(True), 1), else_=0)
                    ).label("wins"),
                )
                .where(and_(MatchRecord.user_id == user_id, MatchRecord.match_date >= start_date))
                .group_by("day")
                .order_by("day")
            )
            result = await db.execute(stmt)
            rows = result.all()

        labels = []
        win_rates = []
        match_counts = []
        for row in rows:
            day_str = row.day.strftime("%m/%d") if row.day else ""
            total = row.total or 0
            wins = int(row.wins or 0)
            rate = round(wins / total, 2) if total > 0 else 0
            labels.append(day_str)
            win_rates.append(rate)
            match_counts.append(total)

        result_data = {
            "labels": labels,
            "series": [
                {"name": "胜率", "data": win_rates},
                {"name": "比赛场次", "data": match_counts},
            ],
        }

        await redis.setex(cache_key, CACHE_TTL_TREND, json.dumps(result_data))
        return result_data

    # ========== 技术统计 ==========

    @staticmethod
    async def get_technique_stats(user_id: int) -> dict:
        """技术统计环形图数据（聚合最近 10 份报告）。缓存 1h。"""
        redis = await get_redis()
        cache_key = f"dashboard:technique:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            stmt = (
                select(AnalysisReport.result_data)
                .where(AnalysisReport.user_id == user_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(10)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

        # 聚合技术分布 — 兼容 technique_stats 和 technique_distribution 两种字段名
        totals = {}
        for raw in rows:
            if not raw:
                continue
            dist = raw.get("technique_distribution") or raw.get("technique_stats") or {}
            for tech, count in dist.items():
                totals[tech] = totals.get(tech, 0) + count

        items = []
        for tech_key, count in totals.items():
            name, color = TECHNIQUE_COLORS.get(tech_key, (tech_key, "#1D3557"))
            items.append({"name": name, "value": count, "color": color})

        result_data = {"technique_distribution": items}
        await redis.setex(cache_key, CACHE_TTL_TECHNIQUE, json.dumps(result_data))
        return result_data

    # ========== 落点热图 ==========

    @staticmethod
    async def get_landing_heatmap(user_id: int) -> dict:
        """累计落点热图（跨多次报告聚合九宫格）。缓存 1h。"""
        redis = await get_redis()
        cache_key = f"dashboard:heatmap:{user_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with async_session_factory() as db:
            stmt = (
                select(AnalysisReport.result_data)
                .where(AnalysisReport.user_id == user_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(10)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

        grid = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        forehand_total = 0.0
        backhand_total = 0.0
        middle_total = 0.0
        total_rallies = 0
        source_count = 0

        for raw in rows:
            if not raw:
                continue

            # 兼容 landing_heatmap 和 landing_points 两种字段名
            heatmap = raw.get("landing_heatmap") or raw.get("landing_points") or {}
            nine_grid = heatmap.get("nine_grid")
            if not nine_grid or len(nine_grid) != 3:
                continue
            source_count += 1
            for i in range(min(3, len(nine_grid))):
                for j in range(min(3, len(nine_grid[i]))):
                    grid[i][j] += nine_grid[i][j]
                    total_rallies += nine_grid[i][j]

            # 兼容 metrics 和 landing_points.distribution 两种字段名
            metrics = raw.get("metrics", {})
            dist = raw.get("landing_points", {}).get("distribution", {})
            forehand_total += metrics.get("landing_forehand_pct", 0) or dist.get("forehand", 0) or 0
            backhand_total += metrics.get("landing_backhand_pct", 0) or dist.get("backhand", 0) or 0
            middle_total += metrics.get("landing_middle_pct", 0) or dist.get("middle", 0) or 0

        dist_sum = forehand_total + backhand_total + middle_total
        if dist_sum > 0:
            distribution = {
                "forehand": round(forehand_total / dist_sum, 2),
                "backhand": round(backhand_total / dist_sum, 2),
                "middle": round(middle_total / dist_sum, 2),
            }
        else:
            distribution = {"forehand": 0, "backhand": 0, "middle": 0}

        result_data = {
            "nine_grid": grid,
            "distribution": distribution,
            "total_rallies": total_rallies,
            "source_reports_count": source_count,
        }

        await redis.setex(cache_key, CACHE_TTL_HEATMAP, json.dumps(result_data))
        return result_data

    # ========== 比赛记录列表 ==========

    @staticmethod
    async def get_match_records(
        user_id: int, result_filter: str = "all", page: int = 1, page_size: int = 20
    ) -> dict:
        """比赛记录列表（实时查询，不缓存）。"""
        if result_filter not in ("win", "lose", "all"):
            result_filter = "all"

        async with async_session_factory() as db:
            qs = select(MatchRecord).where(MatchRecord.user_id == user_id)
            count_qs = select(func.count()).select_from(MatchRecord).where(
                MatchRecord.user_id == user_id
            )

            if result_filter == "win":
                qs = qs.where(MatchRecord.is_win.is_(True))
                count_qs = count_qs.where(MatchRecord.is_win.is_(True))
            elif result_filter == "lose":
                qs = qs.where(MatchRecord.is_win.is_(False))
                count_qs = count_qs.where(MatchRecord.is_win.is_(False))

            total = await db.scalar(count_qs) or 0

            qs = qs.order_by(MatchRecord.match_date.desc()).offset((page - 1) * page_size).limit(page_size)
            result = await db.execute(qs)
            records = result.scalars().all()

        items = [
            {
                "id": r.id,
                "opponent_name": r.opponent_name,
                "my_score": r.my_score,
                "opponent_score": r.opponent_score,
                "is_win": r.is_win,
                "format": r.format,
                "match_type": r.match_type,
                "match_date": r.match_date.isoformat() if r.match_date else None,
            }
            for r in records
        ]

        return {"total": total, "page": page, "page_size": page_size, "items": items}

    # ========== 缓存 bust ==========

    @staticmethod
    async def bust_cache(user_id: int, event: str) -> None:
        """缓存失效。event=analysis_complete/match_end"""
        redis = await get_redis()
        if event == "analysis_complete":
            keys = [
                f"dashboard:overview:{user_id}",
                f"dashboard:technique:{user_id}",
                f"dashboard:heatmap:{user_id}",
            ]
        elif event == "match_end":
            keys = [f"dashboard:overview:{user_id}"]
            for period in ("month", "quarter", "year"):
                keys.append(f"dashboard:winrate:{user_id}:{period}")
        else:
            return

        if keys:
            await redis.delete(*keys)

    # ========== 辅助方法 ==========

    @staticmethod
    async def _get_streak_days(db: AsyncSession, user_id: int) -> int:
        """获取连续天数 — UserPoints 表 S4 才创建，当前返回 0"""
        try:
            from app.models.gamification import UserPoints
            up = await db.scalar(
                select(UserPoints).where(UserPoints.user_id == user_id)
            )
            return up.current_streak if up else 0
        except ImportError:
            return 0

    @staticmethod
    async def _calc_trend(db: AsyncSession, user_id: int) -> str:
        """计算胜率趋势：up/down/flat"""
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        recent_wins = await db.scalar(
            select(func.count()).select_from(MatchRecord).where(
                and_(MatchRecord.user_id == user_id, MatchRecord.is_win.is_(True),
                     MatchRecord.match_date >= week_ago)
            )
        ) or 0
        recent_total = await db.scalar(
            select(func.count()).select_from(MatchRecord).where(
                and_(MatchRecord.user_id == user_id, MatchRecord.match_date >= week_ago)
            )
        ) or 0

        prev_wins = await db.scalar(
            select(func.count()).select_from(MatchRecord).where(
                and_(MatchRecord.user_id == user_id, MatchRecord.is_win.is_(True),
                     MatchRecord.match_date >= two_weeks_ago,
                     MatchRecord.match_date < week_ago)
            )
        ) or 0
        prev_total = await db.scalar(
            select(func.count()).select_from(MatchRecord).where(
                and_(MatchRecord.user_id == user_id,
                     MatchRecord.match_date >= two_weeks_ago,
                     MatchRecord.match_date < week_ago)
            )
        ) or 0

        recent_rate = recent_wins / recent_total if recent_total > 0 else 0
        prev_rate = prev_wins / prev_total if prev_total > 0 else 0

        if recent_total == 0 and prev_total == 0:
            return "flat"
        if recent_rate > prev_rate + 0.05:
            return "up"
        if recent_rate < prev_rate - 0.05:
            return "down"
        return "flat"

    @staticmethod
    async def _get_latest_advice_summary(db: AsyncSession, user_id: int) -> Optional[dict]:
        """获取最近一次分析报告的训练建议摘要"""
        report = await db.scalar(
            select(AnalysisReport).where(AnalysisReport.user_id == user_id)
            .order_by(AnalysisReport.created_at.desc()).limit(1)
        )
        if not report:
            return None

        report_text = report.report_text or {}
        return {
            "report_id": report.id,
            "summary": report_text.get("summary", ""),
            "has_unresolved_issues": len(report_text.get("issues", [])) > 0,
            "latest_report_at": report.created_at.isoformat() if report.created_at else None,
        }
