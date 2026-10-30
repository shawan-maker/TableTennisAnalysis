"""
tests/unit/test_supplements_p2.py — R12 第三批测试缺口补充（P2 测试缺口类）

覆盖：MatchData-D2（PATCH 跨用户隔离）/ Payment-3（analysis_pack 额度 INCR）/
VA-8（分享限流 429）/ SC-3（target_score 越界）/ SC-4（未结束统计 400）/
Gam-5/6/7/8（打卡链路）/ Dash-3/4（看板冒烟 + period 校验）/
Training-D2（趋势对比建议）/ Training-D3（方案调整版本化 + 重新评估动作分支）/
Notif-3/4/5/6（订阅过滤 / 归档策略 / 通道选择 / 提醒频率控制）
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token, generate_jti
from app.models.user import User


# =============================================================================
# MatchData-D2: PATCH 跨用户隔离零覆盖
# =============================================================================

@pytest.mark.asyncio
class TestMatchRecordPatchIsolation:
    """R12-MatchData-D2: 其他用户 PATCH 我的比赛记录 → 404，数据不被篡改"""

    async def _create_record(self, client, headers):
        resp = await client.post(
            "/api/v1/match-data/records",
            json={"opponent_name": "赵某", "my_score": 3, "opponent_score": 1},
            headers=headers,
        )
        assert resp.status_code == 200
        return resp.json()["data"]["id"]

    async def test_patch_by_other_user_returns_404(
        self, client, auth_headers, db_session
    ):
        # 用户 A 创建记录
        record_id = await self._create_record(client, auth_headers)

        # 用户 B 尝试篡改
        user_b = User(openid="p2_user_b", nickname="用户B", status="active")
        db_session.add(user_b)
        await db_session.commit()
        token_b = create_access_token({"sub": str(user_b.id), "jti": generate_jti()})
        headers_b = {"Authorization": f"Bearer {token_b}"}

        resp = await client.patch(
            f"/api/v1/match-data/records/{record_id}",
            json={"notes": "被篡改", "opponent_name": "篡改者"},
            headers=headers_b,
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == 40413

        # 用户 A 的记录未被改动
        resp = await client.get(
            f"/api/v1/match-data/records/{record_id}", headers=auth_headers
        )
        data = resp.json()["data"]
        assert data["opponent_name"] == "赵某"
        assert data.get("notes") is None

    async def test_patch_by_owner_succeeds(self, client, auth_headers):
        """对照：属主 PATCH 正常更新（PATCH 语义，仅更新传入字段）"""
        record_id = await self._create_record(client, auth_headers)
        resp = await client.patch(
            f"/api/v1/match-data/records/{record_id}",
            json={"notes": "反手表现不错"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # API §7.4 响应：{id, is_win, updated_fields}
        assert data["id"] == record_id
        assert data["updated_fields"] == ["notes"]
        # 未传入字段保持不变 + 新值生效（经 GET 验证）
        check = await client.get(
            f"/api/v1/match-data/records/{record_id}", headers=auth_headers
        )
        record = check.json()["data"]
        assert record["notes"] == "反手表现不错"
        assert record["opponent_name"] == "赵某"


# =============================================================================
# Payment-3: analysis_pack 支付触发额度 INCR 无测试
# =============================================================================

@pytest.mark.asyncio
class TestAnalysisPackQuotaIncrement:
    """R12-Payment-3: analysis_pack 支付成功 → quota:bonus:{user_id} INCR quantity

    通知回调为公开端点，无需用户 token — 自建用户 + 订单即可。
    """

    async def _setup_pending_order(self, db_session, order_no, quantity):
        from app.models.payment import Order

        user = User(openid=f"p2_pay_{order_no}", nickname="支付用户", status="active")
        db_session.add(user)
        await db_session.flush()

        order = Order(
            user_id=user.id,
            order_no=order_no,
            product_type="analysis_pack", amount_cents=990,
            status="pending",
            extra_data={"quantity": quantity},
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        return user, order

    async def _post_notify(self, client, order):
        callback_body = json.dumps({
            "id": f"EV-{order.order_no}",
            "create_time": datetime.now(timezone.utc).isoformat(),
            "resource_type": "encrypt-resource",
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "out_trade_no": order.order_no,
                "transaction_id": f"wx_{order.order_no}",
                "trade_state": "SUCCESS",
                "amount": {"total": order.amount_cents},
            },
        })
        return await client.post(
            "/api/v1/payment/notify",
            content=callback_body,
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "test_sig",
                "Wechatpay-Serial": "test_serial",
                "Wechatpay-Nonce": "test_nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )

    async def test_notify_analysis_pack_increments_bonus_quota(
        self, client, db_session
    ):
        from app.core.redis import get_redis

        user, order = await self._setup_pending_order(
            db_session, f"PPAP{datetime.now(timezone.utc).strftime('%H%M%S')}1", 10
        )
        redis = await get_redis()
        await redis.delete(f"quota:bonus:{user.id}")

        resp = await self._post_notify(client, order)
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        # 额度 INCR 生效
        bonus = await redis.get(f"quota:bonus:{user.id}")
        assert bonus == "10"
        await redis.delete(f"quota:bonus:{user.id}")

    async def test_notify_analysis_pack_idempotent_no_double_increment(
        self, client, db_session
    ):
        """同一订单重复回调 → 额度只加一次（幂等）"""
        from app.core.redis import get_redis

        user, order = await self._setup_pending_order(
            db_session, f"PPAP{datetime.now(timezone.utc).strftime('%H%M%S')}2", 5
        )
        redis = await get_redis()
        await redis.delete(f"quota:bonus:{user.id}")

        first = await self._post_notify(client, order)
        assert first.status_code == 200
        duplicate = await self._post_notify(client, order)
        assert duplicate.status_code == 200

        bonus = await redis.get(f"quota:bonus:{user.id}")
        assert bonus == "5"
        await redis.delete(f"quota:bonus:{user.id}")


# =============================================================================
# VA-8: 分享限流 429 无测试
# =============================================================================

@pytest.mark.asyncio
class TestShareDailyLimit:
    """R12-VA-8: 每日分享超 5 次 → 429"""

    async def test_share_limit_exceeded_returns_429(self, client, auth_headers, db_session):
        """预置计数器至上限 → 第 6 次分享 429"""
        from app.core.redis import get_redis
        from app.models.video_analysis import AnalysisReport, VideoTask

        me = await client.get("/api/v1/users/profile", headers=auth_headers)
        user_id = me.json()["data"]["id"]

        redis = await get_redis()
        tz_cst = timezone(timedelta(hours=8))
        today = datetime.now(tz_cst).strftime("%Y%m%d")

        key = f"share:count:{user_id}:{today}"
        await redis.set(key, 5)

        # 需要一份报告才能走到限流检查：file_record → video_task → analysis_report
        from app.models.video_analysis import AnalysisReport, FileRecord, VideoTask
        import uuid as _uuid

        file_record = FileRecord(
            user_id=user_id, oss_key=f"videos/raw/{user_id}/test-{_uuid.uuid4().hex}.mp4",
            original_filename="test.mp4", file_size=10 * 1024 * 1024,
            file_type="mp4", status="uploaded",
        )
        db_session.add(file_record)
        await db_session.flush()
        task = VideoTask(
            user_id=user_id, file_id=file_record.id, oss_key=file_record.oss_key,
            status="completed", progress=1.0, current_step=10,
            task_uuid=_uuid.uuid4().hex,
        )
        db_session.add(task)
        await db_session.flush()
        report = AnalysisReport(
            task_id=task.id, user_id=user_id,
            report_text={"summary": "s", "issues": []}, result_data={},
        )
        db_session.add(report)
        await db_session.commit()
        await db_session.refresh(report)

        resp = await client.post(
            f"/api/v1/video-analysis/reports/{report.id}/share",
            headers=auth_headers,
        )
        assert resp.status_code == 429
        assert "分享次数" in resp.json()["message"]

        await redis.delete(key)

    async def test_share_within_limit_succeeds(self, client, auth_headers, db_session):
        """对照：计数 4/5 时第 5 次分享成功"""
        from app.core.redis import get_redis
        from app.models.video_analysis import AnalysisReport, FileRecord, VideoTask
        import uuid as _uuid

        me = await client.get("/api/v1/users/profile", headers=auth_headers)
        user_id = me.json()["data"]["id"]

        redis = await get_redis()
        tz_cst = timezone(timedelta(hours=8))
        today = datetime.now(tz_cst).strftime("%Y%m%d")
        key = f"share:count:{user_id}:{today}"
        await redis.set(key, 4)

        file_record = FileRecord(
            user_id=user_id, oss_key=f"videos/raw/{user_id}/test-{_uuid.uuid4().hex}.mp4",
            original_filename="test.mp4", file_size=10 * 1024 * 1024,
            file_type="mp4", status="uploaded",
        )
        db_session.add(file_record)
        await db_session.flush()
        task = VideoTask(
            user_id=user_id, file_id=file_record.id, oss_key=file_record.oss_key,
            status="completed", progress=1.0, current_step=10,
            task_uuid=_uuid.uuid4().hex,
        )
        db_session.add(task)
        await db_session.flush()
        report = AnalysisReport(
            task_id=task.id, user_id=user_id,
            report_text={"summary": "s", "issues": []}, result_data={},
        )
        db_session.add(report)
        await db_session.commit()
        await db_session.refresh(report)

        resp = await client.post(
            f"/api/v1/video-analysis/reports/{report.id}/share",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await redis.delete(key)


# =============================================================================
# SC-3: target_score 越界
# =============================================================================

@pytest.mark.asyncio
class TestScoringTargetScoreValidation:
    """R12-SC-3: target_score 越界 → 422（API §5.1 错误表）"""

    @pytest.mark.parametrize("bad_score", [0, 22, 100])
    async def test_target_score_out_of_range_422(self, client, auth_headers, bad_score):
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={
                "opponent_name": "钱某",
                "format": "bo3",
                "match_type": "friendly",
                "target_score": bad_score,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_target_score_boundaries_accepted(self, client, auth_headers):
        """边界值 1/21 合法（合法路径走 setup 状态机）"""
        for good in (1, 21):
            resp = await client.post(
                "/api/v1/scoring/matches",
                json={
                    "opponent_name": "钱某",
                    "format": "bo3",
                    "match_type": "friendly",
                    "target_score": good,
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["status"] == "setup"


# =============================================================================
# SC-4: 未结束比赛统计 400
# =============================================================================

@pytest.mark.asyncio
class TestScoringStatisticsGuard:
    """R12-SC-4: 未结束比赛请求统计 → 400「比赛尚未结束」"""

    async def test_statistics_before_finish_400(self, client, auth_headers):
        create = await client.post(
            "/api/v1/scoring/matches",
            json={"opponent_name": "孙某", "format": "bo1", "match_type": "friendly"},
            headers=auth_headers,
        )
        match_id = create.json()["data"]["match_id"]

        resp = await client.get(
            f"/api/v1/scoring/matches/{match_id}/statistics",
            headers=auth_headers,
        )
        # setup/in_progress 状态均无统计
        assert resp.status_code == 400
        assert "尚未结束" in resp.json()["message"]


# =============================================================================
# Gam-5/6/7/8: 打卡链路测试缺口
# =============================================================================

@pytest.mark.asyncio
class TestCheckinFlow:
    """R12-Gam-5/6/7/8: 401 / 冒烟 / 断签重置 / 徽章解锁端到端"""

    async def test_checkin_without_token_401(self, client):
        """R12-Gam-7: 未认证打卡 → 401"""
        resp = await client.post("/api/v1/gamification/checkin")
        assert resp.status_code == 401

    async def test_checkin_smoke_and_same_day_conflict(
        self, client, auth_headers, db_session
    ):
        """R12-Gam-8: 打卡冒烟 — 首日 200（streak=1），同日重复 409"""
        from app.core.redis import get_redis

        me = await client.get("/api/v1/users/profile", headers=auth_headers)
        user_id = me.json()["data"]["id"]
        redis = await get_redis()
        await redis.delete(f"gamification:streak:user:{user_id}")
        await redis.delete(f"gamification:streak:last_date:{user_id}")

        resp = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["current_streak"] == 1
        assert data["points_earned"] == 2  # POINTS_RULES["checkin"]

        # 同日重复打卡 → 409
        again = await client.post("/api/v1/gamification/checkin", headers=auth_headers)
        assert again.status_code == 409

    async def test_streak_resets_after_gap(
        self, client, db_session
    ):
        """R12-Gam-5: 断签（间隔 >1 天）→ streak 重置为 1"""
        from app.core.redis import get_redis
        from datetime import date as _date, timedelta as _td

        user = User(openid="p2_gap_user", nickname="断签用户", status="active")
        db_session.add(user)
        await db_session.commit()
        token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
        headers = {"Authorization": f"Bearer {token}"}

        redis = await get_redis()
        # 预置：streak=6，上次打卡在 3 天前（gap>1）
        await redis.set(f"gamification:streak:user:{user.id}", 6)
        await redis.set(
            f"gamification:streak:last_date:{user.id}",
            (_date.today() - _td(days=3)).isoformat(),
        )

        resp = await client.post("/api/v1/gamification/checkin", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["current_streak"] == 1  # 断签重置

    async def test_streak_continues_on_consecutive_day(
        self, client, db_session
    ):
        """对照：昨日打卡（gap=1）→ streak 递增"""
        from app.core.redis import get_redis
        from datetime import date as _date, timedelta as _td

        user = User(openid="p2_cont_user", nickname="连续用户", status="active")
        db_session.add(user)
        await db_session.commit()
        token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
        headers = {"Authorization": f"Bearer {token}"}

        redis = await get_redis()
        await redis.set(f"gamification:streak:user:{user.id}", 6)
        await redis.set(
            f"gamification:streak:last_date:{user.id}",
            (_date.today() - _td(days=1)).isoformat(),
        )

        resp = await client.post("/api/v1/gamification/checkin", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["current_streak"] == 7

    async def test_badge_unlock_end_to_end(self, client, db_session):
        """R12-Gam-6: streak=7 → streak_7 徽章解锁（含 seed → 打卡 → 徽章列表）"""
        from app.core.redis import get_redis
        from datetime import date as _date, timedelta as _td
        from app.services.gamification_service import BadgeService

        user = User(openid="p2_badge_user", nickname="徽章用户", status="active")
        db_session.add(user)
        await db_session.commit()
        token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
        headers = {"Authorization": f"Bearer {token}"}

        # 预置徽章定义（幂等 seed）
        await BadgeService.seed_badge_definitions(db_session)
        await db_session.commit()

        # 预置 streak=6 + 昨日打卡 → 打卡后 streak=7 达成 streak_7
        redis = await get_redis()
        await redis.set(f"gamification:streak:user:{user.id}", 6)
        await redis.set(
            f"gamification:streak:last_date:{user.id}",
            (_date.today() - _td(days=1)).isoformat(),
        )

        resp = await client.post("/api/v1/gamification/checkin", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["current_streak"] == 7

        badges = await client.get("/api/v1/gamification/badges", headers=headers)
        assert badges.status_code == 200
        data = badges.json()["data"]
        earned_ids = {b["badge_id"] for b in data["earned"]}
        assert "streak_7" in earned_ids, f"streak_7 未解锁: {data}"


# =============================================================================
# Dash-3/4: 看板 period 降级 / 冒烟
# =============================================================================

@pytest.mark.asyncio
class TestDashboardSmoke:
    """R12-Dash-3/4: overview 冒烟 + period 非法值降级为 month"""

    async def test_overview_smoke(self, client, auth_headers):
        """R12-Dash-4: 概览卡片冒烟（字段以 dashboard_service.get_overview 为准）"""
        resp = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        for key in (
            "win_rate",
            "wins",
            "losses",
            "analysis_count",
            "training_frequency_per_week",
            "streak_days",
            "trend",
            "latest_advice_summary",
        ):
            assert key in data, f"概览缺字段: {key}"

    async def test_win_rate_trend_invalid_period_422(self, client, auth_headers):
        """R12-Dash-3: period=非法值 → 422（API §6.2 通用参数校验；路由 pattern 生效）

        注：service 层 valid_periods.get 兜底为防御性代码，路由 pattern 校验在前，
        非法值永远到不了 service——API 设计文档无"降级为 month"的契约。
        """
        bad = await client.get(
            "/api/v1/dashboard/win-rate-trend?period=century",
            headers=auth_headers,
        )
        assert bad.status_code == 422

        good = await client.get(
            "/api/v1/dashboard/win-rate-trend?period=month",
            headers=auth_headers,
        )
        assert good.status_code == 200
        assert "labels" in good.json()["data"]


# =============================================================================
# Training-D2/D3 公共夹具
# =============================================================================

async def _p2_create_member(db_session, openid, nickname):
    """创建会员用户（/training/plans 端点 require_membership + service 二次校验）"""
    from app.models.membership import Subscription

    user = User(openid=openid, nickname=nickname, status="active")
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(
        Subscription(
            user_id=user.id,
            tier="member",
            status="active",
            start_at=now,
            expire_at=now + timedelta(days=30),
        )
    )
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _p2_seed_report(db_session, user_id):
    """file_record → video_task → analysis_report 数据链"""
    import uuid as _uuid
    from app.models.video_analysis import AnalysisReport, FileRecord, VideoTask

    file_record = FileRecord(
        user_id=user_id,
        oss_key=f"videos/raw/{user_id}/tr-{_uuid.uuid4().hex}.mp4",
        original_filename="test.mp4",
        file_size=10 * 1024 * 1024,
        file_type="mp4",
        status="uploaded",
    )
    db_session.add(file_record)
    await db_session.flush()
    task = VideoTask(
        user_id=user_id,
        file_id=file_record.id,
        oss_key=file_record.oss_key,
        status="completed",
        progress=1.0,
        current_step=10,
        task_uuid=_uuid.uuid4().hex,
    )
    db_session.add(task)
    await db_session.flush()
    report = AnalysisReport(
        task_id=task.id,
        user_id=user_id,
        report_text={"summary": "s", "issues": []},
        result_data={},
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    return report


# =============================================================================
# Training-D2: 趋势对比建议（improving/stagnant 规则端到端）
# =============================================================================

@pytest.mark.asyncio
class TestTrendComparisonAdvice:
    """R12-Training-D2: 趋势对比建议零覆盖

    现有种子规则 condition 无 aggregation 键 → _evaluate_rule 按 single 评估，
    趋势分支从未真正命中。此处用带 aggregation 键的规则 + TechniqueTrend 打通
    improving → progress_confirm / 持续未改善(stagnant) → persistent_warning 链路。
    """

    async def test_trend_rules_produce_typed_suggestions(
        self, client, auth_headers, db_session
    ):
        from app.models.knowledge_base import RuleDefinition
        from app.models.progress import TechniqueTrend

        me = await client.get("/api/v1/users/profile", headers=auth_headers)
        user_id = me.json()["data"]["id"]
        report = await _p2_seed_report(db_session, user_id)

        db_session.add_all(
            [
                TechniqueTrend(
                    user_id=user_id,
                    metric_name="backhand_ratio",
                    trend="improving",
                    persistence_count=3,
                    change_rate=0.15,
                    current_value=0.32,
                ),
                TechniqueTrend(
                    user_id=user_id,
                    metric_name="error_rate",
                    trend="stagnant",
                    persistence_count=4,
                    change_rate=0.03,
                    current_value=0.09,
                ),
                TechniqueTrend(
                    user_id=user_id,
                    metric_name="forehand_ratio",
                    trend="improving",
                    persistence_count=2,
                    change_rate=0.05,
                    current_value=0.55,
                ),
            ]
        )
        db_session.add_all(
            [
                RuleDefinition(
                    rule_id="P2_RULE_IMP",
                    rule_name="反手使用率改善中",
                    rule_type="trend_improving",
                    condition={
                        "aggregation": "trend_improving",
                        "metric": "backhand_ratio",
                        "direction": "improving",
                        "min_persistence": 2,
                    },
                    diagnosis={
                        "problem_id": "P2_IMP",
                        "problem_name": "反手使用率偏低",
                        "severity": "low",
                        "suggestion_template": "反手使用率正在改善，保持当前训练节奏",
                    },
                    is_active=True,
                ),
                RuleDefinition(
                    rule_id="P2_RULE_PERSIST",
                    rule_name="失误率持续未改善",
                    rule_type="trend_persistent",
                    condition={
                        "aggregation": "trend_persistent",
                        "metric": "error_rate",
                        "direction": "stagnant",
                        "min_persistence": 2,
                    },
                    diagnosis={
                        "problem_id": "P2_PERSIST",
                        "problem_name": "失误率偏高",
                        "severity": "high",
                        "suggestion_template": "失误率连续多轮未改善，建议专项纠错训练",
                    },
                    is_active=True,
                ),
                RuleDefinition(
                    rule_id="P2_RULE_NOMATCH",
                    rule_name="正手使用率退步（负对照）",
                    rule_type="trend_improving",
                    condition={
                        "aggregation": "trend_improving",
                        "metric": "forehand_ratio",
                        "direction": "declining",
                        "min_persistence": 2,
                    },
                    diagnosis={
                        "problem_id": "P2_NOMATCH",
                        "problem_name": "正手使用率异常",
                        "severity": "medium",
                        "suggestion_template": "不应出现",
                    },
                    is_active=True,
                ),
            ]
        )
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/training/advice/{report.id}", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]

        # 诊断 trend 字段来自趋势上下文方向（R4-Training-3）
        problems = {d["problem_id"]: d for d in data["diagnosis"]}
        assert "P2_IMP" in problems, f"improving 规则未命中: {data['diagnosis']}"
        assert problems["P2_IMP"]["trend"] == "improving"
        assert "P2_PERSIST" in problems, f"persistent 规则未命中: {data['diagnosis']}"
        assert problems["P2_PERSIST"]["trend"] == "stagnant"
        # 负对照：趋势方向不匹配的规则不出现
        assert "P2_NOMATCH" not in problems

        # 建议类型按规则类型判定（R12-Training-B2）
        sug_types = [s["type"] for s in data["suggestions"]]
        assert "progress_confirm" in sug_types, f"建议类型: {sug_types}"
        assert "persistent_warning" in sug_types, f"建议类型: {sug_types}"


# =============================================================================
# Training-D3: 方案调整版本化 / 重新评估动作分支
# =============================================================================

@pytest.mark.asyncio
class TestPlanAdjustmentVersioning:
    """R12-Training-D3: 调整历史 version 语义

    最新记录（i==0）用 plan.version；非最新记录从 new_plan_snapshot.version 读取
    （R5-Train-3，避免用 r.id 当版本号）。
    """

    async def test_adjustment_history_version_semantics(
        self, client, db_session
    ):
        from app.models.training import PlanAdjustment, TrainingPlan

        member = await _p2_create_member(db_session, "p2_adj_member", "调整历史会员")
        headers = {"Authorization": f"Bearer {create_access_token({'sub': str(member.id), 'jti': generate_jti()})}"}

        plan = TrainingPlan(
            user_id=member.id,
            version=3,
            plan_data={"sessions": [{"name": "反手推球", "reps": 60}]},
            goal_metrics={"backhand_ratio": 0.40},
        )
        db_session.add(plan)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        db_session.add_all(
            [
                PlanAdjustment(
                    training_plan_id=plan.id,
                    old_plan_snapshot={
                        "version": 1,
                        "goal": {"backhand_ratio": 0.30},
                        "plan_data": {"sessions": [{"name": "反手推球", "reps": 40}]},
                    },
                    new_plan_snapshot={
                        "version": 2,
                        "goal": {"backhand_ratio": 0.35},
                        "plan_data": {"sessions": [{"name": "反手推球", "reps": 50}]},
                    },
                    adjustment_action="adjust",
                    adjustment_reason="连续多次无改善，建议调整方案",
                    created_at=now - timedelta(hours=2),
                ),
                PlanAdjustment(
                    training_plan_id=plan.id,
                    old_plan_snapshot={
                        "version": 2,
                        "goal": {"backhand_ratio": 0.35},
                        "plan_data": {"sessions": [{"name": "反手推球", "reps": 50}]},
                    },
                    new_plan_snapshot={
                        "version": 3,
                        "goal": {"backhand_ratio": 0.40},
                        "plan_data": {"sessions": [{"name": "反手推球", "reps": 60}]},
                    },
                    adjustment_action="new_goal",
                    adjustment_reason="已有指标达成目标，建议设定新目标",
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/training/plans/{plan.id}/adjustments", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["current_version"] == 3
        assert len(data["adjustments"]) == 2

        # created_at desc：[0]=最新（new_goal），[1]=较旧（adjust）
        latest, older = data["adjustments"]
        assert latest["action"] == "new_goal"
        assert latest["version"] == 3  # i==0 → plan.version
        assert older["action"] == "adjust"
        assert older["version"] == 2  # 非最新 → new_plan_snapshot.version
        # changes_summary 含版本 diff
        assert "版本 1 → 2" in older["changes_summary"]
        assert "版本 2 → 3" in latest["changes_summary"]


@pytest.mark.asyncio
class TestPlanReEvaluateActions:
    """R12-Training-D3: 重新评估动作分支（new_goal/adjust/escalate/maintain）"""

    async def _create_plan(self, db_session, user_id, goal_metrics, reps=50):
        from app.models.training import TrainingPlan

        plan = TrainingPlan(
            user_id=user_id,
            version=1,
            plan_data={"sessions": [{"name": "反手推球", "reps": reps}]},
            goal_metrics=goal_metrics,
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)
        return plan

    async def _refresh_plan(self, db_session, plan_id):
        from sqlalchemy import select
        from app.models.training import TrainingPlan

        await db_session.rollback()
        db_session.expire_all()
        return await db_session.scalar(
            select(TrainingPlan).where(TrainingPlan.id == plan_id)
        )

    async def test_new_goal_raises_target_by_10_percent(
        self, client, db_session
    ):
        """up 指标全部达标 → new_goal：目标 *1.1，版本 +1，写入调整记录"""
        from app.models.progress import TechniqueTrend

        member = await _p2_create_member(db_session, "p2_reval_goal", "新目标会员")
        headers = {"Authorization": f"Bearer {create_access_token({'sub': str(member.id), 'jti': generate_jti()})}"}
        plan = await self._create_plan(db_session, member.id, {"backhand_ratio": 0.35})

        db_session.add(
            TechniqueTrend(
                user_id=member.id,
                metric_name="backhand_ratio",
                trend="improving",
                persistence_count=3,
                current_value=0.40,  # up 方向：0.40 >= 0.35 → 达标
                change_rate=0.10,
            )
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/training/plans/{plan.id}/re-evaluate", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["action"] == "new_goal"
        assert "新目标" in resp.json()["data"]["reason"]

        fresh = await self._refresh_plan(db_session, plan.id)
        assert fresh.version == 2
        assert fresh.goal_metrics["backhand_ratio"] == pytest.approx(0.385)  # 0.35*1.1

        # 调整历史已记录 new_goal 动作
        history = await client.get(
            f"/api/v1/training/plans/{plan.id}/adjustments", headers=headers
        )
        assert history.status_code == 200
        assert history.json()["data"]["adjustments"][0]["action"] == "new_goal"

    async def test_adjust_raises_reps_by_20_percent(self, client, db_session):
        """全部指标停滞（persistence ≥ 3）且未达标 → adjust：训练单 reps *1.2"""
        from app.models.progress import TechniqueTrend

        member = await _p2_create_member(db_session, "p2_reval_adj", "调整会员")
        headers = {"Authorization": f"Bearer {create_access_token({'sub': str(member.id), 'jti': generate_jti()})}"}
        plan = await self._create_plan(db_session, member.id, {"error_rate": 0.08})

        db_session.add(
            TechniqueTrend(
                user_id=member.id,
                metric_name="error_rate",
                trend="stagnant",
                persistence_count=5,  # ≥ STAGNANT_THRESHOLD(3)
                current_value=0.10,  # down 方向：0.10 > 0.08 → 未达标
                change_rate=0.01,
            )
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/training/plans/{plan.id}/re-evaluate", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["action"] == "adjust"

        fresh = await self._refresh_plan(db_session, plan.id)
        assert fresh.version == 2
        assert fresh.plan_data["sessions"][0]["reps"] == 60  # 50 * 1.2

        # R12-Training-D4 回归：调整历史 diff 如实记录 reps 变化
        # （浅拷贝污染 bug 曾导致此处显示"无变化"且 DB 不更新）
        history = await client.get(
            f"/api/v1/training/plans/{plan.id}/adjustments", headers=headers
        )
        summary = history.json()["data"]["adjustments"][0]["changes_summary"]
        assert "训练单1 reps: 50 → 60" in summary, f"diff 失真: {summary}"

    async def test_escalate_diagnoses_without_rewriting_plan(
        self, client, db_session
    ):
        """指标 declining → escalate：仅诊断，不改写训练内容（R12-Training-B3 回归）"""
        from app.models.progress import TechniqueTrend

        member = await _p2_create_member(db_session, "p2_reval_esc", "升级会员")
        headers = {"Authorization": f"Bearer {create_access_token({'sub': str(member.id), 'jti': generate_jti()})}"}
        plan = await self._create_plan(db_session, member.id, {"backhand_ratio": 0.35})

        db_session.add(
            TechniqueTrend(
                user_id=member.id,
                metric_name="backhand_ratio",
                trend="declining",
                persistence_count=2,
                current_value=0.20,  # up 方向：0.20 < 0.35 → 未达标
                change_rate=-0.12,
            )
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/training/plans/{plan.id}/re-evaluate", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["action"] == "escalate"
        assert "升级" in resp.json()["data"]["reason"]

        fresh = await self._refresh_plan(db_session, plan.id)
        # 版本仍 +1（记录诊断型调整），但训练内容不变
        assert fresh.version == 2
        assert fresh.plan_data["sessions"][0]["reps"] == 50

    async def test_maintain_without_trends_no_adjustment(
        self, client, db_session
    ):
        """无趋势数据 → maintain：版本不变，不写调整记录"""
        member = await _p2_create_member(db_session, "p2_reval_keep", "保持会员")
        headers = {"Authorization": f"Bearer {create_access_token({'sub': str(member.id), 'jti': generate_jti()})}"}
        plan = await self._create_plan(db_session, member.id, {"backhand_ratio": 0.35})

        resp = await client.post(
            f"/api/v1/training/plans/{plan.id}/re-evaluate", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["action"] == "maintain"
        assert "暂无足够趋势数据" in resp.json()["data"]["reason"]

        fresh = await self._refresh_plan(db_session, plan.id)
        assert fresh.version == 1
        history = await client.get(
            f"/api/v1/training/plans/{plan.id}/adjustments", headers=headers
        )
        assert len(history.json()["data"]["adjustments"]) == 0

    async def test_re_evaluate_cross_user_404(self, client, db_session):
        """用户 B 重新评估用户 A 的方案 → 404（属主隔离）"""
        member_a = await _p2_create_member(db_session, "p2_reval_a", "属主A")
        member_b = await _p2_create_member(db_session, "p2_reval_b", "越权B")
        plan = await self._create_plan(db_session, member_a.id, {"backhand_ratio": 0.35})

        headers_b = {"Authorization": f"Bearer {create_access_token({'sub': str(member_b.id), 'jti': generate_jti()})}"}
        resp = await client.post(
            f"/api/v1/training/plans/{plan.id}/re-evaluate", headers=headers_b
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == 40420

        # A 的方案版本未被改动
        fresh = await self._refresh_plan(db_session, plan.id)
        assert fresh.version == 1


# =============================================================================
# Notif-3: 订阅模板静默过滤（当前契约）
# =============================================================================

@pytest.mark.asyncio
class TestNotificationSubscribeFilter:
    """R12-Notif-3: 无效模板处理

    当前契约为静默过滤（R6-Notif-2 已文档化的设计偏差）；
    API §13.3 的 422 行为属 Phase 2+ 文档同步项，此处固定现有契约。
    """

    async def test_subscribe_filters_invalid_templates(
        self, client, auth_headers
    ):
        from app.core.redis import get_redis

        me = await client.get("/api/v1/users/profile", headers=auth_headers)
        user_id = me.json()["data"]["id"]
        redis = await get_redis()
        await redis.delete(f"notif:subscribed:{user_id}")

        resp = await client.post(
            "/api/v1/notification/subscribe",
            json={
                "template_ids": [
                    "analysis_complete",
                    "not_a_template",
                    "payment_success",
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data["subscribed_templates"]) == {
            "analysis_complete",
            "payment_success",
        }

        members = await redis.smembers(f"notif:subscribed:{user_id}")
        assert set(members) == {"analysis_complete", "payment_success"}
        await redis.delete(f"notif:subscribed:{user_id}")

    async def test_subscribe_replaces_previous_subscription(
        self, client, auth_headers
    ):
        """重新订阅是覆盖语义（清除旧订阅再写入）"""
        from app.core.redis import get_redis

        me = await client.get("/api/v1/users/profile", headers=auth_headers)
        user_id = me.json()["data"]["id"]
        redis = await get_redis()
        await redis.delete(f"notif:subscribed:{user_id}")

        first = await client.post(
            "/api/v1/notification/subscribe",
            json={"template_ids": ["analysis_complete", "training_reminder"]},
            headers=auth_headers,
        )
        assert first.status_code == 200

        second = await client.post(
            "/api/v1/notification/subscribe",
            json={"template_ids": ["payment_success"]},
            headers=auth_headers,
        )
        assert second.status_code == 200
        assert second.json()["data"]["subscribed_templates"] == ["payment_success"]

        members = await redis.smembers(f"notif:subscribed:{user_id}")
        assert set(members) == {"payment_success"}
        await redis.delete(f"notif:subscribed:{user_id}")


# =============================================================================
# Notif-4: 归档策略（已读 90 天删除 / 未读 180 天归档删除）
# =============================================================================

@pytest.mark.asyncio
class TestNotificationArchive:
    """R12-Notif-4: cleanup_old_notifications 归档策略"""

    async def test_cleanup_old_read_and_old_unread(
        self, client, db_session
    ):
        from sqlalchemy import select
        from app.models.notification import NotificationRecord
        from app.tasks.notification import (
            READ_RETENTION_DAYS,
            UNREAD_RETENTION_DAYS,
            cleanup_old_notifications_impl,
        )

        user = User(openid="p2_notif_arch", nickname="归档用户", status="active")
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        db_session.add_all(
            [
                NotificationRecord(
                    user_id=user.id, type="analysis_complete",
                    title="旧已读", is_read=True,
                    created_at=now - timedelta(days=READ_RETENTION_DAYS + 10),
                ),
                NotificationRecord(
                    user_id=user.id, type="analysis_complete",
                    title="新已读", is_read=True,
                    created_at=now - timedelta(days=10),
                ),
                NotificationRecord(
                    user_id=user.id, type="training_reminder",
                    title="旧未读", is_read=False,
                    created_at=now - timedelta(days=UNREAD_RETENTION_DAYS + 20),
                ),
                NotificationRecord(
                    user_id=user.id, type="training_reminder",
                    title="新未读", is_read=False,
                    created_at=now - timedelta(days=10),
                ),
            ]
        )
        await db_session.commit()

        # 直接调用模块级 async 实现（任务体仅做 asyncio.run 包装，
        # 在测试事件循环内运行会破坏共享 asyncpg 连接池）
        result = await cleanup_old_notifications_impl()

        assert result["status"] == "ok"
        assert result["read_deleted"] == 1
        assert result["unread_deleted"] == 1

        # 新事务的 SELECT 直接看到删除后的最新状态（无需 expire：
        # 被删行不会出现在结果集中，剩余行属性未被修改）
        remaining = (
            await db_session.scalars(
                select(NotificationRecord).where(
                    NotificationRecord.user_id == user.id
                )
            )
        ).all()
        assert {r.title for r in remaining} == {"新已读", "新未读"}


# =============================================================================
# Notif-5: 通道选择（在线 WS 推送 / 离线落库）
# =============================================================================

@pytest.mark.asyncio
class TestNotificationChannelSelection:
    """R12-Notif-5: send_notification 在线→WS 不落库；离线→落库 + 未读 INCR"""

    async def _record_count(self, db_session, user_id):
        """COUNT 聚合不经过身份映射，新事务直接看到最新已提交数据"""
        from sqlalchemy import func, select
        from app.models.notification import NotificationRecord

        return await db_session.scalar(
            select(func.count())
            .select_from(NotificationRecord)
            .where(NotificationRecord.user_id == user_id)
        )

    async def test_online_skips_db_offline_writes_db(
        self, client, db_session
    ):
        from app.core.redis import get_redis
        from app.services.notification_service import NotificationService

        user = User(openid="p2_notif_chan", nickname="通道用户", status="active")
        db_session.add(user)
        await db_session.commit()
        user_id = user.id  # 提前捕获，避免 ORM 对象后续访问

        redis = await get_redis()
        for key in (f"ws:online:{user_id}", f"notif:unread:{user_id}"):
            await redis.delete(key)

        # 在线 → WS 推送：返回 None，不写 DB
        await redis.set(f"ws:online:{user_id}", "1", ex=120)
        online_result = await NotificationService.send_notification(
            user_id, "training_reminder", "在线提醒", "内容"
        )
        assert online_result is None
        assert await self._record_count(db_session, user_id) == 0

        # 离线 → 落库 + 未读计数 INCR
        await redis.delete(f"ws:online:{user_id}")
        offline_result = await NotificationService.send_notification(
            user_id, "training_reminder", "离线提醒", "内容"
        )
        assert offline_result is not None
        assert await self._record_count(db_session, user_id) == 1
        assert await redis.get(f"notif:unread:{user_id}") == "1"

        await redis.delete(f"notif:unread:{user_id}")


# =============================================================================
# Notif-6: 训练提醒频率控制（每周 2 次 + 3 天阈值）
# =============================================================================

@pytest.mark.asyncio
class TestTrainingReminderFrequency:
    """R12-Notif-6: send_training_reminder 频率控制与阈值"""

    async def _record_count(self, db_session, user_id):
        """COUNT 聚合不经过身份映射，新事务直接看到最新已提交数据"""
        from sqlalchemy import func, select
        from app.models.notification import NotificationRecord

        return await db_session.scalar(
            select(func.count())
            .select_from(NotificationRecord)
            .where(NotificationRecord.user_id == user_id)
        )

    async def test_reminder_frequency_and_daily_threshold(
        self, client, db_session
    ):
        from app.core.redis import get_redis
        from app.services.notification_service import NotificationService

        user = User(openid="p2_notif_freq", nickname="频率用户", status="active")
        db_session.add(user)
        await db_session.commit()
        user_id = user.id  # 提前捕获，避免 ORM 对象后续访问

        redis = await get_redis()
        week_key = f"notif:reminder:count:{user_id}:week"
        for key in (week_key, f"ws:online:{user_id}", f"notif:unread:{user_id}"):
            await redis.delete(key)

        # 1) 未满 3 天 → 不提醒、不计频
        await NotificationService.send_training_reminder(
            user_id, last_training_days=2
        )
        assert await self._record_count(db_session, user_id) == 0
        assert await redis.get(week_key) is None

        # 2) ≥3 天且未达周上限 → 提醒 + 计数 INCR
        await NotificationService.send_training_reminder(
            user_id, last_training_days=5
        )
        assert await self._record_count(db_session, user_id) == 1
        assert await redis.get(week_key) == "1"

        # 3) 达到周上限（REMINDER_WEEKLY_LIMIT）→ 不再提醒
        await redis.set(week_key, NotificationService.REMINDER_WEEKLY_LIMIT)
        await NotificationService.send_training_reminder(
            user_id, last_training_days=5
        )
        assert await self._record_count(db_session, user_id) == 1  # 无新增

        await redis.delete(week_key)
        await redis.delete(f"notif:unread:{user_id}")


# =============================================================================
# Prog-7: forecast R² 阈值过滤
# =============================================================================

@pytest.mark.asyncio
class TestForecastRSquaredFilter:
    """R12-Prog-7: R² < 0.4 的时间序列不产生预测；高 R² 给出 high 置信度

    对照设计：低质量数据不预测（progress_service._linear_regression_forecast）。
    """

    async def test_low_r2_filtered_high_r2_forecasted(self, db_session):
        from app.models.progress import TechniqueTrend
        from app.services.progress_service import ProgressService

        user = User(openid="p2_prog_r2", nickname="预测质量用户", status="active")
        db_session.add(user)
        await db_session.flush()

        # backhand_ratio（up, 目标 0.35）：严格线性序列 → R²≈1.0
        db_session.add(
            TechniqueTrend(
                user_id=user.id,
                metric_name="backhand_ratio",
                current_value=0.31,
                target_value=0.35,
                time_series=[
                    {"value": 0.25},
                    {"value": 0.27},
                    {"value": 0.29},
                    {"value": 0.31},
                ],
            )
        )
        # avg_rally_length（up, 目标 6.0）：锯齿序列 → R²≈0.196 < 0.4 被过滤
        db_session.add(
            TechniqueTrend(
                user_id=user.id,
                metric_name="avg_rally_length",
                current_value=6.5,
                target_value=6.0,
                time_series=[
                    {"value": 3.0},
                    {"value": 7.0},
                    {"value": 3.5},
                    {"value": 6.5},
                ],
            )
        )
        await db_session.commit()

        forecast = await ProgressService._linear_regression_forecast(
            db_session, user.id
        )

        # 高 R² 指标：进入预测，置信度 high，达标周数可计算
        assert "backhand_ratio" in forecast, f"高 R² 应产生预测: {forecast}"
        entry = forecast["backhand_ratio"]
        assert entry["r_squared"] == pytest.approx(1.0, abs=1e-6)
        assert entry["confidence"] == "high"
        # slope=0.02, intercept=0.25 → (0.35-0.25)/0.02=5 → int(5*2)=10
        assert entry["predicted_weeks_to_target"] == 10

        # 低 R² 指标：被阈值过滤，不进入预测
        assert "avg_rally_length" not in forecast, \
            f"R²≈0.196 < 0.4 的锯齿序列不应产生预测: {forecast}"


# =============================================================================
# Prog-8: 报告对比跨用户隔离
# =============================================================================

@pytest.mark.asyncio
class TestReportComparisonIsolation:
    """R12-Prog-8: comparison 端点 — 属主成功 / 跨用户 404 / 同报告 422"""

    async def test_comparison_owner_cross_user_and_same_report(
        self, client, auth_headers, db_session
    ):
        me = await client.get("/api/v1/users/profile", headers=auth_headers)
        user_id = me.json()["data"]["id"]

        # 属主两份报告
        report_a = await _p2_seed_report(db_session, user_id)
        report_b = await _p2_seed_report(db_session, user_id)

        # 1) 属主对比 → 200
        ok = await client.get(
            "/api/v1/progress/comparison",
            params={"report_a": report_a.id, "report_b": report_b.id},
            headers=auth_headers,
        )
        assert ok.status_code == 200
        data = ok.json()["data"]
        assert data["report_a"]["id"] == report_a.id
        assert data["report_b"]["id"] == report_b.id

        # 2) 同报告 → 422（路由守卫，code 42201）
        same = await client.get(
            "/api/v1/progress/comparison",
            params={"report_a": report_a.id, "report_b": report_a.id},
            headers=auth_headers,
        )
        assert same.status_code == 422
        assert same.json()["code"] == 42201

        # 3) 用户 B 对比 A 的报告 → 404（属主校验）
        other = User(openid="p2_prog_other", nickname="越权用户", status="active")
        db_session.add(other)
        await db_session.commit()
        headers_b = {
            "Authorization": f"Bearer {create_access_token({'sub': str(other.id), 'jti': generate_jti()})}"
        }
        cross = await client.get(
            "/api/v1/progress/comparison",
            params={"report_a": report_a.id, "report_b": report_b.id},
            headers=headers_b,
        )
        assert cross.status_code == 404
        assert cross.json()["code"] == 40412

        # 4) B 用自己的报告混搭 A 的报告 → 404
        report_c = await _p2_seed_report(db_session, other.id)
        mixed = await client.get(
            "/api/v1/progress/comparison",
            params={"report_a": report_c.id, "report_b": report_a.id},
            headers=headers_b,
        )
        assert mixed.status_code == 404


# =============================================================================
# Admin-12/13: 审计筛选参数 / session 滑动续期
# =============================================================================

async def _p2_login_admin(client, db_session, username, role="super_admin"):
    """创建管理员并登录，返回 (admin, headers)"""
    from app.core.security import pwd_context
    from app.models.admin import AdminUser
    from app.services.admin_service import AdminService

    admin = AdminUser(
        username=username,
        password_hash=pwd_context.hash("Admin@123"),
        role=role,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    data = await AdminService.login(username, "Admin@123")
    return admin, {"Authorization": f"Bearer {data.session_token}"}, data.session_token


@pytest.mark.asyncio
class TestAdminAuditLogFilters:
    """R12-Admin-12: 审计日志筛选参数（action/target_type/admin_id/时间段/分页）"""

    async def _seed_logs(self, db_session, admin1, admin2):
        from app.models.admin import AuditLog

        # R13-Admin-Test-1: created_at 锚定日历边界固定钟点 —— 相对 now 的偏移
        # （now-4h）在 UTC 早间（<04:00，上海中午前）运行时会落进“昨天”，
        # 使 end_date=昨日 23:59:59 的筛选失效（全量回归 4==3 失败根因）
        from datetime import time as dtime

        today = datetime.now(timezone.utc).date()

        def _at(day_offset: int) -> datetime:
            return datetime.combine(
                today + timedelta(days=day_offset), dtime(12, 0), tzinfo=timezone.utc
            )

        logs = [
            AuditLog(
                admin_id=admin1.id, action="ban_user", target_type="user",
                target_id=101, created_at=_at(-3),
            ),
            AuditLog(
                admin_id=admin1.id, action="unban_user", target_type="user",
                target_id=101, created_at=_at(-2),
            ),
            AuditLog(
                admin_id=admin2.id, action="create_config", target_type="config",
                target_id=201, created_at=_at(-1),
            ),
            AuditLog(
                admin_id=admin1.id, action="toggle_rule", target_type="rule",
                target_id=301, created_at=_at(0),
            ),
        ]
        db_session.add_all(logs)
        await db_session.commit()
        return logs

    async def test_audit_log_filters(self, client, db_session):
        admin1, headers, _ = await _p2_login_admin(client, db_session, "p2_audit_admin")
        admin2, _, _ = await _p2_login_admin(client, db_session, "p2_audit_admin2")
        await self._seed_logs(db_session, admin1, admin2)

        base = "/api/v1/admin/audit-logs"

        # 1) 无筛选：全量 + created_at 倒序
        all_logs = await client.get(base, headers=headers)
        assert all_logs.status_code == 200
        data = all_logs.json()["data"]
        assert data["total"] == 4
        actions = [i["action"] for i in data["items"]]
        assert actions == ["toggle_rule", "create_config", "unban_user", "ban_user"]

        # 2) action 筛选
        by_action = await client.get(base, params={"action": "ban_user"}, headers=headers)
        assert by_action.status_code == 200
        assert by_action.json()["data"]["total"] == 1
        assert by_action.json()["data"]["items"][0]["action"] == "ban_user"

        # 3) target_type 筛选
        by_target = await client.get(base, params={"target_type": "user"}, headers=headers)
        assert by_target.json()["data"]["total"] == 2
        assert all(i["target_type"] == "user" for i in by_target.json()["data"]["items"])

        # 4) admin_id 筛选 + JOIN admin_username
        by_admin = await client.get(
            base, params={"admin_id": admin2.id}, headers=headers
        )
        data_b = by_admin.json()["data"]
        assert data_b["total"] == 1
        assert data_b["items"][0]["admin_username"] == "p2_audit_admin2"

        # 5) 时间段筛选：start_date=昨天 → 只含 log3/log4（created_at 倒序）
        start = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        by_start = await client.get(base, params={"start_date": start}, headers=headers)
        assert by_start.json()["data"]["total"] == 2
        assert [i["action"] for i in by_start.json()["data"]["items"]] == [
            "toggle_rule", "create_config",
        ]

        # 6) end_date=昨天 23:59:59 → 排除今日正午的 log4
        end = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        by_end = await client.get(base, params={"end_date": end}, headers=headers)
        assert by_end.json()["data"]["total"] == 3

        # 7) 分页：page_size=2
        page1 = await client.get(
            base, params={"page": 1, "page_size": 2}, headers=headers
        )
        assert page1.json()["data"]["total"] == 4
        assert len(page1.json()["data"]["items"]) == 2
        page2 = await client.get(
            base, params={"page": 2, "page_size": 2}, headers=headers
        )
        assert len(page2.json()["data"]["items"]) == 2
        # 两页合并 = 全量且不重叠
        p1_ids = {i["id"] for i in page1.json()["data"]["items"]}
        p2_ids = {i["id"] for i in page2.json()["data"]["items"]}
        assert not (p1_ids & p2_ids)
        assert len(p1_ids | p2_ids) == 4


@pytest.mark.asyncio
class TestAdminSessionRenewal:
    """R12-Admin-13: session 滑动续期 — 每次认证请求刷新 TTL 至 30 分钟"""

    async def test_authenticated_request_renews_ttl(self, client, db_session):
        from app.core.redis import get_redis
        from app.services.admin_service import ADMIN_SESSION_PREFIX

        _, headers, token = await _p2_login_admin(client, db_session, "p2_session_admin")

        redis = await get_redis()
        key = f"{ADMIN_SESSION_PREFIX}{token}"

        # 登录后 TTL 接近 1800
        ttl_after_login = await redis.ttl(key)
        assert 1790 <= ttl_after_login <= 1800

        # 人为压缩 TTL → 发起认证请求 → 滑动续期回 1800
        await redis.expire(key, 10)
        assert await redis.ttl(key) <= 10

        resp = await client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 200

        ttl_renewed = await redis.ttl(key)
        assert ttl_renewed > 1700, f"认证请求应刷新 session TTL，实际: {ttl_renewed}"

        # 登出后 session 删除 → 再访问 401
        from app.services.admin_service import AdminService
        await AdminService.logout(token)
        expired = await client.get("/api/v1/admin/users", headers=headers)
        assert expired.status_code == 401


# =============================================================================
# Auth-7: wechat-login 端点
# =============================================================================

@pytest.mark.asyncio
class TestWechatLogin:
    """R12-Auth-7: wechat-login 零覆盖 — monkeypatch code2session 外呼"""

    async def _mock_code2session(self, monkeypatch, openid, session_key="sk_test"):
        from app.services.auth_service import AuthService

        async def fake(code: str) -> dict:
            return {"openid": openid, "session_key": session_key}

        monkeypatch.setattr(AuthService, "_call_wechat_code2session", fake)

    async def test_new_user_wechat_login_creates_user(
        self, client, db_session, monkeypatch
    ):
        from sqlalchemy import select
        from app.core.redis import get_redis
        from app.models.user import User

        await self._mock_code2session(monkeypatch, "p2_wx_new_001")

        resp = await client.post(
            "/api/v1/auth/wechat-login", json={"code": "mock_code"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["user"]["nickname"] == "球友"  # 未传 nickname 走默认
        assert data["requires_consent"] is True  # 新用户未签同意

        # 用户落库
        user_id = data["user"]["id"]
        user = await db_session.scalar(select(User).where(User.id == user_id))
        assert user is not None
        assert user.openid == "p2_wx_new_001"

        # session_key 已存 Redis —— REDIS-I 键表：键参数为 openid（与实现一致；
        # R13-Auth-N3：原断言误用 user_id，与 01-auth 样例笔误同源）
        redis = await get_redis()
        assert await redis.get("wx:session_key:p2_wx_new_001") == "sk_test"

    async def test_existing_user_wechat_login_reuses_account(
        self, client, db_session, monkeypatch
    ):
        from sqlalchemy import func, select
        from app.models.user import User

        user = User(openid="p2_wx_exist_001", nickname="老昵称", status="active")
        db_session.add(user)
        await db_session.commit()

        await self._mock_code2session(monkeypatch, "p2_wx_exist_001")
        resp = await client.post("/api/v1/auth/wechat-login", json={"code": "mock"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user"]["id"] == user.id
        assert data["user"]["nickname"] == "老昵称"

        # 不新增用户
        total = await db_session.scalar(select(func.count()).select_from(User))
        assert total == 1

    async def test_banned_user_wechat_login_403(
        self, client, db_session, monkeypatch
    ):
        user = User(openid="p2_wx_banned_001", nickname="封禁用户", status="banned")
        db_session.add(user)
        await db_session.commit()

        await self._mock_code2session(monkeypatch, "p2_wx_banned_001")
        resp = await client.post("/api/v1/auth/wechat-login", json={"code": "mock"})
        assert resp.status_code == 403
        assert "封禁" in resp.json()["message"]

    async def test_pending_deletion_user_wechat_login_403(
        self, client, db_session, monkeypatch
    ):
        user = User(
            openid="p2_wx_pd_001", nickname="注销中", status="pending_deletion"
        )
        db_session.add(user)
        await db_session.commit()

        await self._mock_code2session(monkeypatch, "p2_wx_pd_001")
        resp = await client.post("/api/v1/auth/wechat-login", json={"code": "mock"})
        assert resp.status_code == 403
        assert "注销" in resp.json()["message"]
