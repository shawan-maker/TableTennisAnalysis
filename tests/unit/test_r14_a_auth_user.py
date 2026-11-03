"""
tests/unit/test_r14_a_auth_user.py — R14 审计 auth+user 测试缺口补齐

覆盖目标（R14 审计认定的缺口，逐项对应）：
  R14-Auth-T1  phone_login 对 banned / pending_deletion 用户的拒绝分支（登录入口状态机）
  R14-Auth-T2  deps 状态机守卫（get_current_user 对 banned/deleted/pending_deletion
               用户的 401/403 分支 + get_current_user_allow_pending 放行对照）
  R14-Auth-T3  code2session 错误分支（errcode 非零 → 400 / 缺 openid → 502）。
               实现为真实 httpx 调用微信接口（非 dev stub），测试以 mock httpx
               响应确定性驱动分支，避免外网依赖。
  R14-Auth-T4  consent upsert（同 user+type+version 未撤回记录更新而非重复插入）
  R14-User-T1  用户乒乓大数据 Redis 缓存（未命中回填 + 24h TTL + 命中直接返回缓存值）
  R14-User-T2  process_account_deletions 任务体（R14-User-1 七步级联验证）

时间断言规范：全链路使用 aware UTC datetime（列均为 timestamptz），
与任务内 cutoff = now(utc) - 72h 同基准，不引入 UTC/CST 混淆。
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.exceptions import (
    AppException,
    ERR_BAD_REQUEST,
    ERR_THIRD_PARTY,
)
from app.core.security import create_access_token, generate_jti
from app.models.user import ConsentLog, User
from app.services.auth_service import AuthService


def _bearer(user: User) -> dict:
    """为指定用户生成 Bearer 认证头（直签 token，不走登录流程）"""
    return {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'jti': generate_jti()})}"
    }


# =================================================================
# R14-Auth-T1: phone_login 状态机拒绝分支
# =================================================================


class TestPhoneLoginStatusGuard:
    """phone_login 对 banned / pending_deletion 用户返回 403（auth_service 状态分支）"""

    async def test_phone_login_banned_user_403(self, client, db_session):
        """封禁用户验证码登录 → 403 + ERR_FORBIDDEN 消息（R12-Auth-2 登录入口拦截）"""
        db_session.add(User(phone="13811112222", nickname="封禁用户", status="banned"))
        await db_session.commit()

        await client.post("/api/v1/auth/send-sms", json={"phone": "13811112222"})
        from app.core.redis import get_redis

        code = await (await get_redis()).get("sms:code:13811112222")
        assert code is not None, "测试环境 SMS_MOCK=true 应写入验证码"

        resp = await client.post(
            "/api/v1/auth/phone-login",
            json={"phone": "13811112222", "code": code},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["message"] == "您的账号已被封禁"
        assert body["code"] == 40300  # AppException 默认 code = status_code * 100

    async def test_phone_login_pending_deletion_user_403(self, client, db_session):
        """注销冷静期用户验证码登录 → 403 + 引导撤销注销消息"""
        db_session.add(
            User(phone="13811113333", nickname="注销中用户", status="pending_deletion")
        )
        await db_session.commit()

        await client.post("/api/v1/auth/send-sms", json={"phone": "13811113333"})
        from app.core.redis import get_redis

        code = await (await get_redis()).get("sms:code:13811113333")
        assert code is not None

        resp = await client.post(
            "/api/v1/auth/phone-login",
            json={"phone": "13811113333", "code": code},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["message"] == "您的账号正在注销中，请先撤销注销"
        assert body["code"] == 40300


# =================================================================
# R14-Auth-T2: deps 状态机守卫
# =================================================================


class TestDepsStatusGuard:
    """get_current_user 状态机守卫 — token 携带者处于异常状态时的 401/403 分支"""

    async def test_guard_banned_user_403(self, client, db_session):
        """banned 用户 token → 403 + 封禁消息 + 40300"""
        user = User(openid="r14_guard_banned", nickname="守卫B", status="banned")
        db_session.add(user)
        await db_session.commit()

        resp = await client.get("/api/v1/users/profile", headers=_bearer(user))
        assert resp.status_code == 403
        body = resp.json()
        assert body["message"] == "您的账号已被封禁"
        assert body["code"] == 40300

    async def test_guard_deleted_user_401(self, client, db_session):
        """deleted 用户 token → 401（语义为'用户不存在'，不暴露注销状态）"""
        user = User(openid="r14_guard_deleted", nickname="守卫D", status="deleted")
        db_session.add(user)
        await db_session.commit()

        resp = await client.get("/api/v1/users/profile", headers=_bearer(user))
        assert resp.status_code == 401
        body = resp.json()
        assert body["message"] == "用户不存在"
        assert body["code"] == 40100

    async def test_guard_pending_deletion_user_403(self, client, db_session):
        """pending_deletion 用户 token → 403 + 撤销注销引导消息（R6-Auth-1）"""
        user = User(openid="r14_guard_pd", nickname="守卫P", status="pending_deletion")
        db_session.add(user)
        await db_session.commit()

        resp = await client.get("/api/v1/users/profile", headers=_bearer(user))
        assert resp.status_code == 403
        body = resp.json()
        assert body["message"] == "账号已申请注销，请撤销注销后操作"
        assert body["code"] == 40300

    async def test_guard_nonexistent_user_401(self, client):
        """token sub 指向不存在用户 → 401 + '用户不存在'"""
        headers = {
            "Authorization": f"Bearer {create_access_token({'sub': '999999', 'jti': generate_jti()})}"
        }
        resp = await client.get("/api/v1/users/profile", headers=headers)
        assert resp.status_code == 401
        body = resp.json()
        assert body["message"] == "用户不存在"
        assert body["code"] == 40100

    async def test_pending_deletion_allowed_on_cancel_endpoint(self, client, db_session):
        """对照：get_current_user_allow_pending 放行撤销注销端点；撤销后恢复访问

        同时验证 R14-User-2 撤销注销审计日志（action=account_deletion_cancelled）。
        """
        from app.models.admin import AuditLog

        user = User(openid="r14_guard_pd_cancel", nickname="守卫PC", status="pending_deletion")
        db_session.add(user)
        await db_session.commit()
        headers = _bearer(user)

        # 常规端点被守卫拒绝（对照）
        resp_blocked = await client.get("/api/v1/users/profile", headers=headers)
        assert resp_blocked.status_code == 403

        # 撤销注销端点放行（allow_pending 依赖）
        resp = await client.post(
            "/api/v1/users/account/cancel-deletion", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "active"

        # 撤销后同 token 恢复常规端点访问
        resp_after = await client.get("/api/v1/users/profile", headers=headers)
        assert resp_after.status_code == 200

        # R14-User-2: 撤销注销审计日志（用户侧操作，admin_id 为空）
        async with async_session_factory() as v:
            logs = (
                await v.execute(select(AuditLog).where(AuditLog.user_id == user.id))
            ).scalars().all()
        assert len(logs) == 1
        assert logs[0].action == "account_deletion_cancelled"
        assert logs[0].target_type == "user"
        assert logs[0].target_id == user.id
        assert logs[0].admin_id is None


# =================================================================
# R14-Auth-T3: code2session 错误分支
# =================================================================


class TestCode2SessionBranches:
    """_call_wechat_code2session 错误处理（httpx mock 驱动，确定性验证）"""

    @staticmethod
    def _fake_response(payload: dict) -> MagicMock:
        fake = MagicMock()
        fake.json.return_value = payload
        return fake

    async def test_errcode_nonzero_raises_400(self):
        """微信返回 errcode（如 40029 无效 code）→ AppException 400 '登录凭证无效'"""
        fake = self._fake_response({"errcode": 40029, "errmsg": "invalid code"})
        with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake)):
            with pytest.raises(AppException) as exc_info:
                await AuthService._call_wechat_code2session("bad-code")

        assert exc_info.value.status_code == 400
        assert exc_info.value.message == "登录凭证无效"
        assert exc_info.value.code == ERR_BAD_REQUEST

    async def test_missing_openid_raises_502(self):
        """响应无 openid（第三方异常）→ AppException 502 第三方服务不可用"""
        fake = self._fake_response({"errcode": 0, "session_key": "sk_only"})
        with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake)):
            with pytest.raises(AppException) as exc_info:
                await AuthService._call_wechat_code2session("any-code")

        assert exc_info.value.status_code == 502
        assert exc_info.value.message == "微信登录服务暂时不可用"
        assert exc_info.value.code == ERR_THIRD_PARTY

    async def test_success_returns_payload(self):
        """正常响应（errcode=0 + openid）→ 原样返回 payload"""
        fake = self._fake_response(
            {"errcode": 0, "openid": "r14_openid_ok", "session_key": "r14_sk"}
        )
        with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake)):
            data = await AuthService._call_wechat_code2session("ok-code")

        assert data["openid"] == "r14_openid_ok"
        assert data["session_key"] == "r14_sk"

    async def test_wechat_login_endpoint_maps_third_party_error(self, client):
        """端点层：code2session 抛 502 AppException → 全局处理器映射为 HTTP 502"""
        err = AppException("微信登录服务暂时不可用", 502, code=ERR_THIRD_PARTY)
        with patch.object(
            AuthService, "_call_wechat_code2session", new=AsyncMock(side_effect=err)
        ):
            resp = await client.post("/api/v1/auth/wechat-login", json={"code": "any"})
        assert resp.status_code == 502
        body = resp.json()
        assert body["message"] == "微信登录服务暂时不可用"
        assert body["code"] == 50200


# =================================================================
# R14-Auth-T4: consent upsert
# =================================================================


class TestConsentUpsert:
    """record_consent upsert 语义 — 重复授权更新既有记录而非重复插入"""

    async def test_repeat_consent_updates_same_row(self, client, auth_headers, auth_user):
        """同 user+type+version 重复同意 → 单行更新（consent_at/上下文刷新）"""
        uid = auth_user["user_id"]

        async def _rows():
            # 用独立会话读取，规避 db_session 身份映射缓存（expire_on_commit=False
            # 会让同对象二次查询返回旧值）
            async with async_session_factory() as v:
                return (
                    await v.execute(select(ConsentLog).where(ConsentLog.user_id == uid))
                ).scalars().all()

        resp1 = await client.post(
            "/api/v1/auth/consent",
            headers={**auth_headers, "user-agent": "R14-Consent-UA-1"},
            json={"consent_type": "privacy_policy", "policy_version": "v1.0"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["data"]["consented"] is True

        rows1 = await _rows()
        assert len(rows1) == 1
        first_id, first_at = rows1[0].id, rows1[0].consent_at

        # 间隔 50ms：timestamptz 微秒精度下保证 consent_at 严格推进
        await asyncio.sleep(0.05)

        resp2 = await client.post(
            "/api/v1/auth/consent",
            headers={**auth_headers, "user-agent": "R14-Consent-UA-2"},
            json={"consent_type": "privacy_policy", "policy_version": "v1.0"},
        )
        assert resp2.status_code == 200

        rows2 = await _rows()
        assert len(rows2) == 1, "重复同意不应插入新行（upsert 语义）"
        record = rows2[0]
        assert record.id == first_id, "应更新同一行而非新建"
        assert record.consent_at > first_at, "consent_at 应被刷新"
        assert record.user_agent == "R14-Consent-UA-2", "授权上下文（UA）应被更新"
        assert record.ip_address is not None
        assert record.withdrawn_at is None

    async def test_consent_different_type_inserts_new_row(self, client, auth_headers, auth_user):
        """不同 consent_type 是独立 upsert 键 → 各自插入一行"""
        for ctype in ("privacy_policy", "data_processing"):
            resp = await client.post(
                "/api/v1/auth/consent",
                headers=auth_headers,
                json={"consent_type": ctype, "policy_version": "v1.0"},
            )
            assert resp.status_code == 200

        async with async_session_factory() as v:
            rows = (
                await v.execute(
                    select(ConsentLog).where(ConsentLog.user_id == auth_user["user_id"])
                )
            ).scalars().all()
        assert {r.consent_type for r in rows} == {"privacy_policy", "data_processing"}

    async def test_consent_invalid_version_422_no_write(self, client, auth_headers, auth_user):
        """R12-Auth-4：非当前政策版本 → 422 且不落库（防 requires_consent 死循环）"""
        resp = await client.post(
            "/api/v1/auth/consent",
            headers=auth_headers,
            json={"consent_type": "privacy_policy", "policy_version": "v9.9"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["message"] == "政策版本不正确，请同意最新版隐私政策"
        assert body["code"] == 42200

        async with async_session_factory() as v:
            rows = (
                await v.execute(
                    select(ConsentLog).where(ConsentLog.user_id == auth_user["user_id"])
                )
            ).scalars().all()
        assert rows == [], "无效版本不应写入同意记录"


# =================================================================
# R14-User-T1: 用户数据 Redis 缓存（命中 + TTL）
# =================================================================


class TestBigDataRedisCache:
    """get_big_data 缓存链路 — 未命中回填（24h TTL）+ 命中直接返回缓存值"""

    async def test_cache_miss_backfill_then_hit(self, client, auth_headers, auth_user):
        from app.core.redis import get_redis

        uid = auth_user["user_id"]
        cache_key = f"big_data:user:{uid}"
        redis = await get_redis()
        assert await redis.get(cache_key) is None, "前置：无缓存"

        # 首次请求：缓存未命中 → 实时计算（无比赛记录 → 全零）→ 回填缓存
        resp1 = await client.get("/api/v1/users/big-data", headers=auth_headers)
        assert resp1.status_code == 200
        assert resp1.json()["data"]["total_matches"] == 0

        cached = await redis.get(cache_key)
        assert cached is not None, "首次请求后应回填缓存"
        ttl = await redis.ttl(cache_key)
        assert 0 < ttl <= 86400, "缓存 TTL 应为 24h（BIG_DATA_CACHE_TTL=86400）"

        # 篡改缓存内容 → 第二次请求应命中缓存直接返回（非实时计算）
        payload = json.loads(cached)
        payload["total_matches"] = 999
        payload["win_rate"] = 0.42
        await redis.set(cache_key, json.dumps(payload))

        resp2 = await client.get("/api/v1/users/big-data", headers=auth_headers)
        assert resp2.status_code == 200
        data2 = resp2.json()["data"]
        assert data2["total_matches"] == 999, "第二次请求应命中缓存（返回篡改值）"
        assert data2["win_rate"] == 0.42


# =================================================================
# R14-User-T2: process_account_deletions 七步级联（R14-User-1）
# =================================================================


class TestProcessAccountDeletionsCascade:
    """任务体验证：BR-4 七步级联（匿名化/软删/匿名归档/退订/终态/Redis 清理/审计）"""

    async def test_full_br4_cascade(self, db_session):
        from app.models.admin import AuditLog
        from app.models.membership import Subscription
        from app.models.video_analysis import AnalysisReport, FileRecord, VideoTask

        now = datetime.now(timezone.utc)
        expired_at = now - timedelta(hours=73)  # 越过 72h 冷静期

        # --- 种子：到期待注销用户（PII 齐备）+ 冷静期内对照用户 ---
        victim = User(
            openid="r14_del_openid",
            phone="13800009999",
            nickname="待注销用户",
            avatar_url="https://example.com/avatar.png",
            status="pending_deletion",
            deletion_reason="不再使用",
            scheduled_deletion_at=now - timedelta(hours=1),
            updated_at=expired_at,  # INSERT 显式赋值（onupdate 仅 UPDATE 时生效）
        )
        fresh = User(
            openid="r14_del_fresh",
            phone="13800008888",
            nickname="冷静期内用户",
            status="pending_deletion",  # updated_at 为当前时间 → 未满 72h
        )
        db_session.add_all([victim, fresh])
        await db_session.commit()
        await db_session.refresh(victim)
        victim_id, fresh_id = victim.id, fresh.id

        # 前置：确保种子 updated_at 已越过任务 cutoff（now(utc) - 72h）
        assert victim.updated_at < now - timedelta(hours=72, minutes=1)

        # --- 关联数据：视频（file_size 下限 1MB 满足 CHECK）/ 报告 / 订阅 ---
        file_rec = FileRecord(
            user_id=victim_id,
            oss_key=f"r14test/{victim_id}/backhand.mp4",
            original_filename="backhand.mp4",
            file_size=1048576,
            file_type="mp4",
            status="uploaded",
        )
        db_session.add(file_rec)
        await db_session.flush()

        video_task = VideoTask(
            user_id=victim_id,
            file_id=file_rec.id,
            oss_key=file_rec.oss_key,
            status="completed",
            task_uuid=f"r14-task-{victim_id}",
        )
        db_session.add(video_task)
        await db_session.flush()

        db_session.add(
            AnalysisReport(
                task_id=video_task.id,
                user_id=victim_id,
                result_data={"summary": "r14-seed"},
                report_text={"summary": "r14-seed", "issues": [], "suggestions": []},
                is_anonymized=False,
            )
        )
        db_session.add_all(
            [
                Subscription(
                    user_id=victim_id,
                    tier="member",
                    status="active",  # 非终态 → 应被取消
                    start_at=now - timedelta(days=30),
                    expire_at=now + timedelta(days=30),
                ),
                Subscription(
                    user_id=victim_id,
                    tier="member",
                    status="expired",  # 终态 → 不应回退
                    start_at=now - timedelta(days=400),
                    expire_at=now - timedelta(days=340),
                ),
            ]
        )
        await db_session.commit()

        # --- Redis 侧缓存种子（步骤 7 清理对象） ---
        from app.core.redis import get_redis

        redis = await get_redis()
        await redis.set(f"big_data:user:{victim_id}", json.dumps({"total_matches": 1}))
        await redis.set(f"notif:unread:{victim_id}", "5")
        t0 = datetime.now(timezone.utc)

        # --- 执行任务（eager 内联；_run_async + run_isolated 线程池隔离执行） ---
        from app.tasks.user import process_account_deletions

        result = process_account_deletions.delay()
        assert result.get() == {"status": "ok"}

        # --- 步骤 2/6：用户匿名化 + 状态终态（独立会话验证，规避身份映射旧值） ---
        async with async_session_factory() as v:
            u = (await v.execute(select(User).where(User.id == victim_id))).scalar_one()
            assert u.status == "deleted"
            assert u.nickname == "已注销用户"
            assert u.avatar_url is None
            assert u.phone is None
            assert u.openid is None
            assert u.scheduled_deletion_at is None
            assert u.deletion_reason is None

            # --- 步骤 3：关联视频软删 ---
            fr = (
                await v.execute(select(FileRecord).where(FileRecord.user_id == victim_id))
            ).scalar_one()
            assert fr.status == "deleted"

            # --- 步骤 4：分析报告匿名化（user_id 保留供训练数据） ---
            rep = (
                await v.execute(
                    select(AnalysisReport).where(AnalysisReport.user_id == victim_id)
                )
            ).scalar_one()
            assert rep.is_anonymized is True
            assert rep.user_id == victim_id

            # --- 步骤 5：订阅取消（非终态）+ 终态不回退 ---
            subs = (
                await v.execute(
                    select(Subscription).where(Subscription.user_id == victim_id)
                )
            ).scalars().all()
            statuses = {s.status for s in subs}
            assert "cancelled" in statuses, "非终态订阅应被取消"
            assert "active" not in statuses
            assert "expired" in statuses
            cancelled = next(s for s in subs if s.status == "cancelled")
            assert cancelled.cancelled_at is not None
            assert cancelled.cancelled_at >= t0  # 取消时间在本测试执行期内
            expired_sub = next(s for s in subs if s.status == "expired")
            assert expired_sub.cancelled_at is None, "终态订阅不应被回退"

            # --- 步骤 8：AuditLog 写入 account_deleted ---
            logs = (
                await v.execute(select(AuditLog).where(AuditLog.user_id == victim_id))
            ).scalars().all()
            assert len(logs) == 1
            log = logs[0]
            assert log.action == "account_deleted"
            assert log.target_type == "user"
            assert log.target_id == victim_id
            assert log.admin_id is None, "用户侧操作 admin_id 应为空"

            # --- 对照：冷静期内用户未被处理 ---
            fu = (await v.execute(select(User).where(User.id == fresh_id))).scalar_one()
            assert fu.status == "pending_deletion"
            assert fu.phone == "13800008888"
            flogs = (
                await v.execute(select(AuditLog).where(AuditLog.user_id == fresh_id))
            ).scalars().all()
            assert flogs == []

        # --- 步骤 7：Redis 缓存清理（run_isolated 已重置全局池，重新获取客户端） ---
        redis2 = await get_redis()
        assert await redis2.get(f"big_data:user:{victim_id}") is None
        assert await redis2.get(f"notif:unread:{victim_id}") is None

        # --- R14-User-1 核心收益：phone 置空释放部分唯一索引 → 同手机号可重新注册 ---
        async with async_session_factory() as v2:
            reborn = User(phone="13800009999", nickname="重新注册用户", status="active")
            v2.add(reborn)
            await v2.commit()  # 若 phone 未置空将触发唯一索引冲突
            assert reborn.id is not None
            assert reborn.id != victim_id
