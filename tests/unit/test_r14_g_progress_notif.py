"""
tests/unit/test_r14_g_progress_notif.py — R14 审计缺口补齐（G 组：progress / notification）

覆盖目标（审计原文不可用，按编号候选方向逐一 grep 既有覆盖后确认缺口）：

progress（Prog-6b-5/6/7/8 候选）：
- Prog-6b-5 快照生成落库字段：既有 test_progress.py::test_generate_snapshot_success
  （L65-77）仅断言返回 dict 含 18 个指标键、test_generate_snapshot_idempotent
  （L81-94）仅断言 COUNT==1 —— DB 行字段值（user_id/report_id 绑定、
  _extract_metrics 取值映射、缺失指标 None 透传）与幂等重入返回语义为缺口。
- Prog-6b-6 趋势计算数值：_calculate_trend 六类型矩阵已有直调覆盖
  （test_progress.py L304-359）；resolved 落库已有覆盖（test_supplements_p1.py
  L1010-1065）。缺口：_update_trends 落库数值字段（current/previous/
  change_rate/target/time_series）与 20 点历史窗口截断
  （progress_service.py L168-170）。
- Prog-6b-7 缓存失效/回填：progress:* 四类 Redis key 全 tests/ 零命中
  （grep progress:summary|trends|problems|trend_detail → 0）——
  generate_snapshot 失效链（progress_service.py L82-91，含 trend_detail
  KEYS scan 与按 user 作用域）与读接口回填 TTL（summary 300 / trends /
  problems / trend_detail 3600，含缓存命中短路、R6-Prog-2 无数据不缓存
  分支）全部为缺口。
- Prog-6b-8 时间窗边界：list_snapshots period 滚动窗口（month=30 /
  quarter=90 / year=365，UTC now 起点）仅有 422 参数校验覆盖
  （test_progress.py L363-374），窗口两侧（窗内/窗外）与 CST 时区表示的
  绝对时刻比较为缺口。
- 快照触发链（分析完成→级联→快照，Celery 投递 spy）：已有
  test_ai_pipeline.py L149-160（R13-AIP-1 投递断言）+ L468-489
  （autouse spy fixture）覆盖，跳过不重复。

notification（6a-N5/N6 候选）：
- 6a-N5 未读计数：incr 递增已有间接覆盖（test_r14_f L187 断言 ==1、
  test_supplements_p2 L1173 断言 =="1"）；Redis 故障回退已有覆盖
  （test_r14_d L241-300，ND-3）。缺口：mark_read decr 递减 → 清零全生命
  周期、幂等重标不再递减、负数修正分支（notification_service.py L223-227）、
  get_unread_count 缓存命中短路 + DB 回填 TTL=300（L234-261 正向路径）。
- 6a-N6 列表分页/标记已读：既有仅 page=1（test_notification.py L39-55）与
  单条标记（L78-89）。缺口：多页翻页 + created_at 降序排序 + 单次调用批量
  标记多条。is_read/type 过滤已有覆盖（L57-76 / L175-208），跳过。
- 多渠道 stub：邮件/短信渠道实现不存在（notification_service 全文无 email/
  sms 渠道发送）；微信订阅消息 stub（_send_wechat_subscribe，
  notification_service.py L129-168）为已实现渠道，补 mock 分支断言。
- 通知偏好/设置（免打扰/渠道开关）：实现不存在（grep 免打扰|dnd|mute|
  notification_pref → app/ 零命中；notif:subscribed:{uid} 仅写无消费方）→ 跳过。
- consent 相关通知分支：consent 仅存在于 auth 模块登录链路
  （auth_service.py L120/L392-481），notification 侧无实现 → 跳过。
- 通知三态断言（离线落库/在线 WS 推送/终态幂等）：已由 test_r14_f
  L133-261 与 test_supplements_p2 L1143-1175 覆盖，禁止重复。

环境说明：conftest 不清理 notif:* 键（清理模式清单无 notif:*），且 schema
每测试 DROP/CREATE 使用户 id 从 1 重新计数 —— 通知用例在测试首尾显式清理
notif:unread / ws:online / notif:reminder:count / notif:subscribed 键。
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.core.redis import get_redis
from app.models.notification import NotificationRecord
from app.models.progress import ProgressSnapshot, TechniqueTrend
from app.models.user import User
from app.models.video_analysis import AnalysisReport, FileRecord, VideoTask
from app.schemas.notification import NotificationListQuery
from app.services.notification_service import NotificationService
from app.services.progress_service import (
    CACHE_TTL_PROBLEMS,
    CACHE_TTL_SUMMARY,
    CACHE_TTL_TRENDS,
    ProgressService,
)

TZ_CST = timezone(timedelta(hours=8))


# =============================================================================
# 辅助
# =============================================================================

async def _make_report(db, user_id: int, idx, result_data: dict) -> AnalysisReport:
    """FileRecord + VideoTask + AnalysisReport（oss_key/task_uuid 按 idx 唯一）"""
    file_record = FileRecord(
        user_id=user_id,
        oss_key=f"r14g/{user_id}/{idx}",
        file_size=1048576,
        file_type="mp4",
        status="uploaded",
    )
    db.add(file_record)
    await db.flush()

    task = VideoTask(
        user_id=user_id,
        file_id=file_record.id,
        oss_key=f"r14g/t/{user_id}/{idx}",
        status="completed",
        task_uuid=f"r14g-{user_id}-{idx}",
        progress=100,
    )
    db.add(task)
    await db.flush()

    report = AnalysisReport(
        task_id=task.id,
        user_id=user_id,
        result_data=result_data,
        report_text={"summary": "r14g", "issues": [], "suggestions": []},
        is_llm_generated=False,
    )
    db.add(report)
    await db.flush()
    return report


async def _snapshot_row(report_id: int) -> ProgressSnapshot:
    """独立会话读取快照行（规避身份映射旧值）"""
    async with async_session_factory() as db:
        return await db.scalar(
            select(ProgressSnapshot).where(ProgressSnapshot.report_id == report_id)
        )


async def _trend_row(user_id: int, metric: str) -> TechniqueTrend:
    """独立会话读取趋势行"""
    async with async_session_factory() as db:
        return await db.scalar(
            select(TechniqueTrend).where(
                TechniqueTrend.user_id == user_id,
                TechniqueTrend.metric_name == metric,
            )
        )


async def _clean_notif_keys(user_id: int) -> None:
    """清理通知相关 Redis 键（conftest 清理清单不含 notif:*，用户 id 跨测试复用）"""
    redis = await get_redis()
    await redis.delete(
        f"notif:unread:{user_id}",
        f"ws:online:{user_id}",
        f"notif:reminder:count:{user_id}:week",
        f"notif:subscribed:{user_id}",
    )


# =============================================================================
# Prog-6b-5：快照生成落库字段 + 幂等重入语义
# =============================================================================

@pytest.mark.asyncio
class TestProgSnapshotFields:

    async def test_snapshot_db_row_fields_and_extraction(self, db_session, test_user):
        """快照落库字段：user_id/report_id 绑定 + 18 项指标提取映射 + 缺失 None 透传

        既有覆盖仅断言返回 dict 的 18 个键名（test_progress.py L65-77），
        未验证 DB 行字段值与 _extract_metrics 各源字段映射
        （progress_service.py L96-133）。
        """
        uid = test_user.id
        result_data = {
            "technique_stats": {
                "backhand_ratio": 0.27, "forehand_ratio": 0.55, "serve_ratio": 0.08,
            },
            "landing_points": {
                "distribution": {"forehand": 0.55, "backhand": 0.30, "middle": 0.15},
                "dispersion": 2.2,
            },
            "rally_analysis": {
                "avg_rally_length": 6.5, "max_rally_length": 14, "rally_frequency": 1.4,
            },
            "ball_speed": {"avg_speed_mps": 19.5, "max_speed_mps": 25.5},
            "score_analysis": {
                "win_rate": 0.58, "key_point_win_rate": 0.52,
                "serve_point_win_rate": 0.61, "receive_point_win_rate": 0.49,
            },
            "error_rate": 0.11,
            # attack_transition_rate 故意缺失 → 快照中应为 None
        }
        report = await _make_report(db_session, uid, "p1", result_data)
        await db_session.commit()

        result = await ProgressService.generate_snapshot(uid, report.id, result_data)

        row = await _snapshot_row(report.id)
        assert row is not None
        assert row.id == result["id"]
        assert row.user_id == uid
        assert row.report_id == report.id
        assert row.created_at is not None

        m = row.metrics_snapshot
        assert len(m) == 18
        # 技术统计（technique_stats 直读）
        assert m["backhand_ratio"] == 0.27
        assert m["forehand_ratio"] == 0.55
        assert m["serve_ratio"] == 0.08
        # 落点分布（landing_points.distribution 映射）
        assert m["landing_forehand_pct"] == 0.55
        assert m["landing_backhand_pct"] == 0.30
        assert m["landing_middle_pct"] == 0.15
        assert m["landing_dispersion"] == 2.2
        # 回合分析
        assert m["avg_rally_length"] == 6.5
        assert m["max_rally_length"] == 14
        assert m["rally_frequency"] == 1.4
        # 球速（ball_speed.avg_speed_mps → avg_ball_speed 字段名映射）
        assert m["avg_ball_speed"] == 19.5
        assert m["max_ball_speed"] == 25.5
        # 得分分析
        assert m["score_win_rate"] == 0.58
        assert m["key_point_win_rate"] == 0.52
        assert m["serve_point_win_rate"] == 0.61
        assert m["receive_point_win_rate"] == 0.49
        # 顶层直读 + 缺失指标 None 透传
        assert m["error_rate"] == 0.11
        assert m["attack_transition_rate"] is None

    async def test_snapshot_idempotent_reentry_keeps_db_row(self, db_session, test_user):
        """幂等重入：同 report 二次生成（result_data 变化）→ 不新增行、DB 保持首版

        实现语义（progress_service.py L63-67）：重入早退返回当前提取值
        （不写库、不重算趋势）；幂等以 DB 行为准。既有覆盖
        （test_progress.py L81-94）仅断言 COUNT==1，未覆盖重入返回语义与
        DB 行不被二次数据覆盖。
        """
        uid = test_user.id
        data_v1 = {"technique_stats": {"backhand_ratio": 0.27}}
        report = await _make_report(db_session, uid, "p1b", data_v1)
        await db_session.commit()

        res1 = await ProgressService.generate_snapshot(uid, report.id, data_v1)

        data_v2 = {"technique_stats": {"backhand_ratio": 0.99}}
        res2 = await ProgressService.generate_snapshot(uid, report.id, data_v2)

        # 重入返回同一 id + 当前调用提取值（不落库）
        assert res2["id"] == res1["id"]
        assert res2["metrics_snapshot"]["backhand_ratio"] == 0.99

        # DB 行保持首版数据（独立会话 + COUNT 聚合规避身份映射旧值）
        async with async_session_factory() as v:
            cnt = await v.scalar(
                select(func.count()).select_from(ProgressSnapshot).where(
                    ProgressSnapshot.report_id == report.id
                )
            )
        assert cnt == 1
        row = await _snapshot_row(report.id)
        assert row.metrics_snapshot["backhand_ratio"] == 0.27


# =============================================================================
# Prog-6b-6：趋势落库数值字段 + 20 点历史窗口截断
# =============================================================================

@pytest.mark.asyncio
class TestProgTrendValues:

    async def test_trend_numeric_fields_after_two_snapshots(self, db_session, test_user):
        """两次快照后 TechniqueTrend 落库数值字段精确值

        backhand_ratio 0.20 → 0.25（up 方向）：change_rate = (0.25-0.20)/0.20
        = 0.25（显著 >0.05），但仅 1 段上升 → R5-Prog-2 fallback
        improving/persistence_count=1；target 0.35 落库；time_series 2 点。
        既有覆盖（test_progress.py L117-142）仅断言 trend != "new"。
        """
        uid = test_user.id
        r1 = await _make_report(
            db_session, uid, "p2-1", {"technique_stats": {"backhand_ratio": 0.20}}
        )
        await db_session.commit()
        await ProgressService.generate_snapshot(uid, r1.id, r1.result_data)

        # 间隔 20ms 确保两快照 created_at 严格递增（趋势按时间升序全量重算）
        await asyncio.sleep(0.02)

        r2 = await _make_report(
            db_session, uid, "p2-2", {"technique_stats": {"backhand_ratio": 0.25}}
        )
        await db_session.commit()
        await ProgressService.generate_snapshot(uid, r2.id, r2.result_data)

        tt = await _trend_row(uid, "backhand_ratio")
        assert tt is not None
        assert tt.current_value == 0.25
        assert tt.previous_value == 0.20
        assert tt.change_rate == 0.25
        assert tt.target_value == 0.35  # METRIC_DEFINITIONS 目标值落库
        assert tt.trend == "improving"
        assert tt.persistence_count == 1
        assert tt.time_series is not None
        assert len(tt.time_series) == 2
        assert [p["value"] for p in tt.time_series] == [0.20, 0.25]
        assert all(p["date"] for p in tt.time_series)  # date 为非空 isoformat 字符串

    async def test_trend_history_window_caps_at_20(self, db_session, test_user):
        """20 点历史窗口截断（progress_service.py L168-170）

        22 个快照 → history_values / time_series 仅保留最近 20 点
        （丢弃最早 2 点）；previous_value 取窗口内倒数第 2 点。
        既有覆盖：无（全 tests/ 无 20 点窗口用例）。
        """
        uid = test_user.id
        now = datetime.now(timezone.utc)

        # 22 份报告：0..20 直接落快照（0.10..0.30），第 22 份经 service 生成（0.40）
        reports = []
        for i in range(22):
            value = 0.40 if i == 21 else round(0.10 + i * 0.01, 2)
            reports.append(await _make_report(
                db_session, uid, f"p3-{i}",
                {"technique_stats": {"backhand_ratio": value}},
            ))
        await db_session.commit()

        # 21 个直接落库快照：显式 created_at 严格递增（now-21d .. now-1d）
        for i in range(21):
            db_session.add(ProgressSnapshot(
                user_id=uid,
                report_id=reports[i].id,
                metrics_snapshot={"backhand_ratio": round(0.10 + i * 0.01, 2)},
                created_at=now - timedelta(days=21 - i),
            ))
        await db_session.commit()

        await ProgressService.generate_snapshot(
            uid, reports[21].id, reports[21].result_data
        )

        tt = await _trend_row(uid, "backhand_ratio")
        assert tt is not None
        # 窗口截断：22 点 → 20 点（丢弃 0.10 / 0.11 两个最早点）
        assert len(tt.time_series) == 20
        assert [p["value"] for p in tt.time_series] == (
            [round(0.10 + i * 0.01, 2) for i in range(2, 21)] + [0.40]
        )
        # previous 取窗口内倒数第 2 点（0.30，即第 21 个快照）
        assert tt.previous_value == 0.30
        assert tt.current_value == 0.40
        assert tt.change_rate == 0.3333  # round((0.40-0.30)/0.30, 4)
        # 窗口内 19 段连续上升 + 末段显著（+33.3% > 5%）→ improving / persistence 19
        assert tt.trend == "improving"
        assert tt.persistence_count == 19


# =============================================================================
# Prog-6b-7：Redis 缓存失效 / 回填（progress:* 全 tests/ 零覆盖）
# =============================================================================

@pytest.mark.asyncio
class TestProgCacheInvalidationAndBackfill:

    async def test_snapshot_generation_invalidates_progress_cache(
        self, db_session, test_user
    ):
        """快照生成清缓存：3 固定键 + trend_detail KEYS scan（R7-Prog-3）

        progress_service.py L82-91：删除 summary/trends/problems 三键 +
        scan 删除 trend_detail:{uid}:*（键含 metric 名）；删除按 user 作用域，
        其他用户键不受影响。既有覆盖：无。
        """
        uid = test_user.id
        redis = await get_redis()
        stale_keys = [
            f"progress:summary:{uid}",
            f"progress:trends:{uid}",
            f"progress:problems:{uid}",
            f"progress:trend_detail:{uid}:backhand_ratio",
            f"progress:trend_detail:{uid}:serve_ratio",
        ]
        for k in stale_keys:
            await redis.setex(k, 120, "stale")
        # 其他用户的键不受影响（按 user 作用域删除）
        foreign_key = "progress:summary:424242"
        await redis.setex(foreign_key, 120, "stale")

        report = await _make_report(
            db_session, uid, "p4", {"technique_stats": {"backhand_ratio": 0.27}}
        )
        await db_session.commit()
        await ProgressService.generate_snapshot(uid, report.id, report.result_data)

        for k in stale_keys:
            assert await redis.get(k) is None, f"快照生成后应清除缓存键 {k}"
        assert await redis.get(foreign_key) == "stale"

    async def test_read_apis_backfill_cache_ttl_and_short_circuit(
        self, db_session, test_user
    ):
        """读接口回填缓存 + TTL（设计 §8 验证清单：summary 5min / trend 类 1h）

        - get_summary → progress:summary TTL ≤ 300（A-4）
        - get_technique_trends / get_problem_changes / get_technique_trend_detail
          → TTL ≤ 3600
        - 缓存命中短路：预置哨兵值直接返回（不查 DB）
        - R6-Prog-2：有效指标无趋势数据 → null 字段结果且不缓存空结果
        既有覆盖：无（progress:* 缓存键全 tests/ 零命中）。
        """
        uid = test_user.id
        redis = await get_redis()
        data = {"technique_stats": {"backhand_ratio": 0.27}}
        report = await _make_report(db_session, uid, "p5", data)
        await db_session.commit()
        await ProgressService.generate_snapshot(uid, report.id, data)

        # summary：回填 TTL ≤ 300（CACHE_TTL_SUMMARY）
        summary = await ProgressService.get_summary(uid)
        assert summary["total_analyses"] == 1
        k_summary = f"progress:summary:{uid}"
        assert await redis.get(k_summary) is not None
        assert 0 < await redis.ttl(k_summary) <= CACHE_TTL_SUMMARY

        # trends：回填 TTL ≤ 3600
        trends = await ProgressService.get_technique_trends(uid)
        assert len(trends["metrics"]) == 18
        k_trends = f"progress:trends:{uid}"
        assert 0 < await redis.ttl(k_trends) <= CACHE_TTL_TRENDS

        # problems：回填 TTL ≤ 3600
        await ProgressService.get_problem_changes(uid)
        k_problems = f"progress:problems:{uid}"
        assert 0 < await redis.ttl(k_problems) <= CACHE_TTL_PROBLEMS

        # trend_detail：有趋势数据 → 回填 TTL ≤ 3600
        detail = await ProgressService.get_technique_trend_detail(uid, "backhand_ratio")
        assert detail["current_value"] == 0.27
        k_detail = f"progress:trend_detail:{uid}:backhand_ratio"
        assert 0 < await redis.ttl(k_detail) <= CACHE_TTL_TRENDS

        # 缓存命中短路：预置哨兵 → 直接返回缓存值（不查 DB）
        await redis.setex(k_trends, 60, json.dumps({"sentinel": True}))
        assert await ProgressService.get_technique_trends(uid) == {"sentinel": True}

        # R6-Prog-2：有效指标无趋势数据（无快照用户）→ null 字段且不缓存
        user2 = User(openid="r14g_p5_user2", nickname="无趋势用户", status="active")
        db_session.add(user2)
        await db_session.commit()
        d2 = await ProgressService.get_technique_trend_detail(user2.id, "backhand_ratio")
        assert d2["metric"] == "backhand_ratio"
        assert d2["current_value"] is None
        assert d2["trend"] is None
        assert d2["target_value"] == 0.35  # METRIC_DEFINITIONS 默认目标
        assert d2["history"] == []
        assert await redis.get(f"progress:trend_detail:{user2.id}:backhand_ratio") is None


# =============================================================================
# Prog-6b-8：list_snapshots period 时间窗边界（UTC / CST 两侧）
# =============================================================================

@pytest.mark.asyncio
class TestProgPeriodWindow:

    async def test_snapshot_period_window_boundary_utc_cst(self, db_session, test_user):
        """period 滚动窗口两侧：month=30 / quarter=90 / year=365 天（UTC 起点）

        - 窗内 29d（UTC 表示）与同一绝对时刻的 CST 表示（+08:00）均命中 ——
          created_at 比较 timestamptz 绝对时刻语义，与时区表示无关（CST 一侧）；
        - 窗外 31d / 91d / 366d 排除（UTC 一侧）；period=all 返回全部。
        既有覆盖仅 period 参数 422 校验（test_progress.py L363-374）。
        """
        uid = test_user.id
        now = datetime.now(timezone.utc)

        spec = [
            ("in_utc_29d", now - timedelta(days=29)),                      # 月窗内（UTC 表示）
            ("in_cst_29d", (now - timedelta(days=29)).astimezone(TZ_CST)),  # 同一时刻 CST 表示
            ("out_utc_31d", now - timedelta(days=31)),                      # 月窗外（季/年窗内）
            ("in_utc_89d", now - timedelta(days=89)),                       # 季窗内
            ("out_utc_91d", now - timedelta(days=91)),                      # 季窗外（年窗内）
            ("in_utc_364d", now - timedelta(days=364)),                     # 年窗内
            ("out_utc_366d", now - timedelta(days=366)),                    # 年窗外（仅 all 可见）
        ]
        rows = []
        for tag, created_at in spec:
            report = await _make_report(
                db_session, uid, f"p6-{tag}",
                {"technique_stats": {"backhand_ratio": 0.5}},
            )
            snap = ProgressSnapshot(
                user_id=uid,
                report_id=report.id,
                metrics_snapshot={"backhand_ratio": 0.5},
                created_at=created_at,
            )
            db_session.add(snap)
            rows.append((tag, snap))
        await db_session.commit()
        ids = {tag: snap.id for tag, snap in rows}

        # month（30 天窗）：两个 29d 快照（UTC + CST 表示）均命中，31d 排除
        res = await ProgressService.list_snapshots(uid, period="month")
        assert res["total"] == 2
        assert {it["id"] for it in res["items"]} == {ids["in_utc_29d"], ids["in_cst_29d"]}

        # quarter（90 天窗）：嵌套包含月窗内快照 + 31d + 89d，91d 排除
        res = await ProgressService.list_snapshots(uid, period="quarter")
        assert res["total"] == 4
        assert {it["id"] for it in res["items"]} == {
            ids["in_utc_29d"], ids["in_cst_29d"],
            ids["out_utc_31d"], ids["in_utc_89d"],
        }

        # year（365 天窗）：+ 91d + 364d，366d 排除
        res = await ProgressService.list_snapshots(uid, period="year")
        assert res["total"] == 6
        assert {it["id"] for it in res["items"]} == {
            ids["in_utc_29d"], ids["in_cst_29d"], ids["out_utc_31d"],
            ids["in_utc_89d"], ids["out_utc_91d"], ids["in_utc_364d"],
        }

        # all：全部 7 条
        res = await ProgressService.list_snapshots(uid, period="all")
        assert res["total"] == 7
        assert {it["id"] for it in res["items"]} == set(ids.values())


# =============================================================================
# 6a-N5：未读计数生命周期（incr → decr → 清零 / 负数修正 / 缓存优先回填）
# =============================================================================

@pytest.mark.asyncio
class TestNotifUnreadCounter:

    async def test_unread_counter_lifecycle(self, db_session, test_user):
        """未读计数全生命周期：3 次离线通知 incr → "3"；mark_read decr → "1" → "0"

        幂等重标已读 → updated_count=0 且计数不再递减（is_read==False 过滤，
        notification_service.py L207-210）。既有覆盖仅 incr 单点断言
        （test_r14_f L187 / test_supplements_p2 L1173），decr/清零/幂等为缺口。
        """
        uid = test_user.id
        redis = await get_redis()
        await _clean_notif_keys(uid)
        key = f"notif:unread:{uid}"

        records = []
        for i in range(3):
            r = await NotificationService.send_notification(
                user_id=uid, notif_type="n5_cycle",
                title=f"通知{i}", content="内容",
            )
            assert r is not None
            records.append(r)
        assert await redis.get(key) == "3"

        # 批量标记 2 条 → 计数原子递减 2
        res = await NotificationService.mark_read(uid, [records[0].id, records[1].id])
        assert res.updated_count == 2
        assert await redis.get(key) == "1"

        # 标记最后 1 条 → 清零
        res = await NotificationService.mark_read(uid, [records[2].id])
        assert res.updated_count == 1
        assert await redis.get(key) == "0"

        # 幂等：重复标记已读 → 0 条更新、计数不再递减
        res = await NotificationService.mark_read(uid, [records[0].id])
        assert res.updated_count == 0
        assert await redis.get(key) == "0"

        # DB 终态：3 条全部已读（独立会话 COUNT 聚合规避身份映射旧值）
        async with async_session_factory() as v:
            unread = await v.scalar(
                select(func.count()).select_from(NotificationRecord).where(
                    NotificationRecord.user_id == uid,
                    NotificationRecord.is_read == False,  # noqa: E712
                )
            )
        assert unread == 0
        await _clean_notif_keys(uid)

    async def test_unread_counter_negative_correction(self, db_session, test_user):
        """负数修正分支（notification_service.py L223-227）

        Redis 计数漂移（DB 2 条未读、缓存仅记 1）→ decrby 2 得 -1 → 修正为 0，
        不残留负数计数。既有覆盖：无。
        """
        uid = test_user.id
        redis = await get_redis()
        await _clean_notif_keys(uid)

        n1 = NotificationRecord(
            user_id=uid, type="n5_neg", title="未读1", content="", is_read=False,
        )
        n2 = NotificationRecord(
            user_id=uid, type="n5_neg", title="未读2", content="", is_read=False,
        )
        db_session.add_all([n1, n2])
        await db_session.flush()
        ids = [n1.id, n2.id]
        await db_session.commit()

        # 模拟计数漂移：DB 2 条未读，Redis 仅记 1
        await redis.set(f"notif:unread:{uid}", "1")

        res = await NotificationService.mark_read(uid, ids)
        assert res.updated_count == 2
        # decrby 2 → -1 → 负数修正为 0
        assert await redis.get(f"notif:unread:{uid}") == "0"
        await _clean_notif_keys(uid)

    async def test_unread_count_cache_priority_and_backfill(self, db_session, test_user):
        """get_unread_count（notification_service.py L234-261 正向路径）

        缓存命中短路（预置 7 直接返回，不查 DB）；未命中 → DB 聚合 →
        回填缓存 TTL=300s。Redis 故障回退已有覆盖（test_r14_d L277-300，
        ND-3），此处补正向路径。既有正向覆盖（test_notification.py
        L103-118）仅弱断言 count>=3，无 Redis 键/TTL/短路断言。
        """
        uid = test_user.id
        redis = await get_redis()
        await _clean_notif_keys(uid)
        key = f"notif:unread:{uid}"

        # 1) 缓存命中短路：DB 实际 0 条未读，仍返回缓存值 7
        await redis.set(key, "7", ex=60)
        assert await NotificationService.get_unread_count(uid) == 7

        # 2) 缓存未命中 → DB 聚合（2 未读 + 1 已读 → 2）→ 回填 TTL=300
        await redis.delete(key)
        db_session.add_all([
            NotificationRecord(
                user_id=uid, type="n5_cache", title="未读1", content="", is_read=False,
            ),
            NotificationRecord(
                user_id=uid, type="n5_cache", title="未读2", content="", is_read=False,
            ),
            NotificationRecord(
                user_id=uid, type="n5_cache", title="已读", content="", is_read=True,
            ),
        ])
        await db_session.commit()

        assert await NotificationService.get_unread_count(uid) == 2
        assert await redis.get(key) == "2"
        assert 0 < await redis.ttl(key) <= 300  # 回填 TTL（实现内联 300s）
        await _clean_notif_keys(uid)


# =============================================================================
# 6a-N6：通知列表分页/排序 + 单次批量标记已读
# =============================================================================

@pytest.mark.asyncio
class TestNotifListPagination:

    async def test_list_pagination_ordering_and_batch_mark_read(
        self, db_session, test_user
    ):
        """多页翻页 + created_at 降序排序 + 单次调用批量标记 3 条

        既有覆盖仅 page=1（test_notification.py L39-55）与单条标记
        （L78-89）；is_read/type 过滤已有覆盖（L57-76 / L175-208），跳过。
        """
        uid = test_user.id
        base = datetime.now(timezone.utc) - timedelta(minutes=5)
        recs = []
        for i in range(5):
            recs.append(NotificationRecord(
                user_id=uid, type="n6_page", title=f"通知{i}", content="",
                created_at=base + timedelta(minutes=i),
            ))
        db_session.add_all(recs)
        await db_session.flush()
        ids = [r.id for r in recs]
        await db_session.commit()

        # page=1：最新 2 条（created_at 降序）
        res = await NotificationService.list_notifications(
            uid, NotificationListQuery(page=1, page_size=2)
        )
        assert res["total"] == 5
        assert [it.id for it in res["items"]] == [ids[4], ids[3]]

        # page=2：中间 2 条
        res = await NotificationService.list_notifications(
            uid, NotificationListQuery(page=2, page_size=2)
        )
        assert res["total"] == 5
        assert [it.id for it in res["items"]] == [ids[2], ids[1]]

        # page=3：末页余 1 条
        res = await NotificationService.list_notifications(
            uid, NotificationListQuery(page=3, page_size=2)
        )
        assert res["total"] == 5
        assert [it.id for it in res["items"]] == [ids[0]]

        # 越界页：空 items、total 不变
        res = await NotificationService.list_notifications(
            uid, NotificationListQuery(page=4, page_size=2)
        )
        assert res["total"] == 5
        assert res["items"] == []

        # 单次调用批量标记 3 条（IN + is_read==False 过滤）
        m = await NotificationService.mark_read(uid, [ids[0], ids[1], ids[2]])
        assert m.updated_count == 3
        await _clean_notif_keys(uid)


# =============================================================================
# 6a-N6（多渠道 stub）：微信订阅消息 stub mock 分支
# 注：邮件/短信渠道在 notification_service 中实现不存在（全文仅有微信订阅
# 消息 _send_wechat_subscribe，L129-168）—— 按「实现不存在，跳过」原则
# 只补已实现渠道的 stub 行为。
# =============================================================================

@pytest.mark.asyncio
class TestNotifWechatStub:

    async def test_wechat_subscribe_stub_mock_branch(
        self, db_session, test_user, caplog
    ):
        """离线通知携带 wechat_template → _send_wechat_subscribe mock 分支

        测试环境 SMS_MOCK=true（.env）→ mock 分支记录审计日志
        （wechat subscribe mock: user_id=... type=...）并返回 True，
        不阻塞通知落库（级联容错语义）。既有覆盖：无
        （_send_wechat_subscribe 全 tests/ 零命中）。
        """
        from app.core.config import settings

        uid = test_user.id
        await _clean_notif_keys(uid)

        with caplog.at_level(
            logging.INFO, logger="app.services.notification_service"
        ):
            record = await NotificationService.send_notification(
                user_id=uid,
                notif_type="training_reminder",
                title="训练提醒",
                content="您已经5天没有训练了，快来练习吧！",
                wechat_template="training_reminder",
            )

        assert record is not None
        assert record.type == "training_reminder"

        # mock 分支审计日志（生产 mock 关闭时走 template_msg 准备分支，不在此断言）
        if settings.SMS_MOCK or settings.WECHAT_PAY_MOCK:
            assert any(
                "wechat subscribe mock: user_id=" in r.getMessage()
                for r in caplog.records
            ), "微信订阅消息 stub mock 分支应记录审计日志"

        # stub 不阻塞主通道：通知正常落库（独立会话 COUNT）
        async with async_session_factory() as v:
            cnt = await v.scalar(
                select(func.count()).select_from(NotificationRecord).where(
                    NotificationRecord.user_id == uid
                )
            )
        assert cnt == 1
        await _clean_notif_keys(uid)
