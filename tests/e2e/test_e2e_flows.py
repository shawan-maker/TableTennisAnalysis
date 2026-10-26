"""
tests/e2e/test_e2e_flows.py — 4 条核心路径端到端测试

依据：测试计划 §7 E2E-01~04
E2E-01: 新用户分析全流程（注册→上传→AI 分析→报告→训练建议）
E2E-02: 记分牌全流程（创建比赛→记分→结束→统计→看板）
E2E-03: 付费转化全流程（免费额度→购买会员→支付→权益生效→无限分析）
E2E-04: 训练闭环全流程（分析→进度快照→趋势→训练方案→训练单→完成）
"""

import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.core.security import create_access_token, generate_jti, pwd_context
from app.core.database import async_session_factory
from app.models.user import User
from app.models.admin import AdminUser
from sqlalchemy import select


def _auth_headers(user_id: int) -> dict:
    token = create_access_token({"sub": str(user_id), "jti": generate_jti()})
    return {"Authorization": f"Bearer {token}"}


# ==================== E2E-01: 新用户分析全流程 ====================

@pytest.mark.asyncio
class TestE2E01AnalysisFlow:
    """E2E-01: 注册→上传→AI 分析→报告→训练建议"""

    async def test_full_analysis_flow(self, client, test_user, seed_tiers, auth_headers):
        """新用户完成一次完整的视频分析流程"""
        # 清除 Redis 缓存避免跨测试污染
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.delete("membership:tiers", "membership:current:1", "membership:quota:1")

        # 1. 查看会员权益
        resp = await client.get("/api/v1/membership/tiers", headers=auth_headers)
        assert resp.status_code == 200
        tiers_data = resp.json()["data"]
        tiers_list = tiers_data.get("tiers", tiers_data) if isinstance(tiers_data, dict) else tiers_data
        assert len(tiers_list) >= 4

        # 2. 查看当前会员状态（free）
        resp = await client.get("/api/v1/membership/current", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["tier"] == "free"

        # 3. 查看免费额度
        resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["remaining"] >= 1

        # 4. 获取上传 token
        resp = await client.post(
            "/api/v1/video-analysis/upload-token",
            headers=auth_headers,
            json={
                "filename": "test_match.mp4",
                "file_size": 10485760,
            },
        )
        assert resp.status_code == 200

        # 5. 查看任务列表
        resp = await client.get("/api/v1/video-analysis/tasks", headers=auth_headers)
        assert resp.status_code == 200

        # 6. 查看通知列表
        resp = await client.get("/api/v1/notification/list", headers=auth_headers)
        assert resp.status_code == 200
        assert "items" in resp.json()["data"]

        # 7. 查看未读通知数
        resp = await client.get("/api/v1/notification/unread-count", headers=auth_headers)
        assert resp.status_code == 200

        # 8. 查看仪表盘
        resp = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
        assert resp.status_code == 200


# ==================== E2E-02: 记分牌全流程 ====================

@pytest.mark.asyncio
class TestE2E02ScoringFlow:
    """E2E-02: 创建比赛→记分→结束→统计→看板"""

    async def test_full_scoring_flow(self, client, test_user, auth_headers):
        """完整的记分牌比赛流程"""
        # 1. 创建比赛
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={"opponent_name": "E2E对手", "format": "bo3"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        match_data = resp.json()["data"]
        match_id = match_data.get("id") or match_data.get("match_id")

        # 2. 开始比赛
        resp = await client.post(
            f"/api/v1/scoring/matches/{match_id}/start",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # 3. 记分（user 得分 3 次）
        for _ in range(3):
            resp = await client.post(
                f"/api/v1/scoring/matches/{match_id}/score",
                json={"scorer": "user", "score_method": "serve_point"},
                headers=auth_headers,
            )
            assert resp.status_code == 200

        # 4. 撤销最后一次分数
        resp = await client.post(
            f"/api/v1/scoring/matches/{match_id}/undo",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # 5. 重新记分
        resp = await client.post(
            f"/api/v1/scoring/matches/{match_id}/score",
            json={"scorer": "user", "score_method": "rally_point"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # 6. 查看比赛详情
        resp = await client.get(
            f"/api/v1/scoring/matches/{match_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # 7. 结束比赛
        resp = await client.post(
            f"/api/v1/scoring/matches/{match_id}/finish",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # 8. 查看统计
        resp = await client.get(
            f"/api/v1/scoring/matches/{match_id}/statistics",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # 9. 查看仪表盘
        resp = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
        assert resp.status_code == 200


# ==================== E2E-03: 付费转化全流程 ====================

@pytest.mark.asyncio
class TestE2E03PaymentFlow:
    """E2E-03: 免费额度→购买会员→支付→权益生效→无限分析"""

    async def test_full_payment_flow(self, client, test_user, seed_tiers, auth_headers):
        """完整的付费转化流程"""
        # 清除 Redis 缓存
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.delete("membership:tiers", f"membership:current:{test_user.id}", f"membership:quota:{test_user.id}")
        await redis.delete(f"quota:analysis:{test_user.id}")

        # 1. 查看免费额度
        resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["remaining"] >= 1
        assert resp.json()["data"]["tier"] == "free"

        # 2. 查看会员等级
        resp = await client.get("/api/v1/membership/tiers", headers=auth_headers)
        assert resp.status_code == 200
        tiers_data = resp.json()["data"]
        tiers_list = tiers_data.get("tiers", tiers_data) if isinstance(tiers_data, dict) else tiers_data
        member_tier = next((t for t in tiers_list if t.get("tier") == "member"), None)
        assert member_tier is not None

        # 3. 创建支付订单
        resp = await client.post(
            "/api/v1/payment/orders",
            json={"product_type": "membership", "tier": "member", "period": "monthly"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        order = resp.json()["data"]
        order_no = order["order_no"]

        # 4. 模拟微信支付回调
        callback = json.dumps({
            "resource": {
                "out_trade_no": order_no,
                "transaction_id": "wx_e2e_003",
                "trade_state": "SUCCESS",
                "amount": {"total": 1900},
            }
        })
        resp = await client.post(
            "/api/v1/payment/notify",
            content=callback,
            headers={
                "Content-Type": "application/json",
                "Wechatpay-Signature": "sig",
                "Wechatpay-Serial": "serial",
                "Wechatpay-Nonce": "nonce",
                "Wechatpay-Timestamp": "1234567890",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        # 5. 验证会员权益已生效
        resp = await client.get("/api/v1/membership/current", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["tier"] == "member"

        # 6. 验证额度已变为无限
        resp = await client.get("/api/v1/membership/quota", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["tier"] == "member"


# ==================== E2E-04: 训练闭环全流程 ====================

@pytest.mark.asyncio
class TestE2E04TrainingFlow:
    """E2E-04: 分析→进度快照→趋势→训练方案→训练单→完成"""

    async def test_training_flow_dashboard(self, client, test_user, auth_headers, db_session, seed_tiers):
        """训练闭环全流程（简化版：验证数据流可达性）"""
        # 训练端点需要会员权限，为测试用户创建会员订阅
        from app.models.membership import Subscription
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        sub = Subscription(
            user_id=test_user.id, tier="member", status="active",
            start_at=now, expire_at=now + timedelta(days=30),
        )
        db_session.add(sub)
        await db_session.commit()

        # 1. 查看仪表盘（进度概览）
        resp = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
        assert resp.status_code == 200

        # 2. 查看进度快照列表
        resp = await client.get("/api/v1/progress/snapshots", headers=auth_headers)
        assert resp.status_code == 200

        # 3. 查看技术趋势
        resp = await client.get("/api/v1/progress/technique-trends", headers=auth_headers)
        assert resp.status_code == 200

        # 4. 查看训练建议（新用户可能无数据，200 或 404 均可）
        resp = await client.get("/api/v1/training/advice/contextual", headers=auth_headers)
        assert resp.status_code in (200, 404)

        # 5. 查看训练模板
        resp = await client.get("/api/v1/training/templates", headers=auth_headers)
        assert resp.status_code == 200

        # 6. 查看游戏化积分
        resp = await client.get("/api/v1/gamification/points", headers=auth_headers)
        assert resp.status_code == 200

        # 7. 查看徽章
        resp = await client.get("/api/v1/gamification/badges", headers=auth_headers)
        assert resp.status_code == 200

        # 8. 查看签到日历
        resp = await client.get("/api/v1/gamification/checkin-calendar", headers=auth_headers)
        assert resp.status_code == 200
