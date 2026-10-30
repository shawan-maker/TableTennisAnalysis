"""
tests/unit/test_auth.py — auth 模块单元测试

依据：切片 01-auth/backend.md §2 测试先行
覆盖：微信登录、Token 刷新、登出、consent 链路
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.core.exceptions import AppException
from app.core.security import create_access_token, decode_token, generate_jti
from app.models.user import User


# =================================================================
# 健康检查测试
# =================================================================

@pytest.mark.asyncio
async def test_health_check(client):
    """健康检查端点正常响应"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


# =================================================================
# 认证测试
# =================================================================

@pytest.mark.asyncio
async def test_get_profile_without_token(client):
    """未携带 JWT 返回 401"""
    resp = await client.get("/api/v1/users/profile")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_profile_with_token(client, auth_headers, test_user):
    """携带有效 JWT 获取个人档案"""
    resp = await client.get("/api/v1/users/profile", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == test_user.id
    assert data["nickname"] == "测试用户"
    assert "profile_completeness" in data["profile"]


@pytest.mark.asyncio
async def test_update_profile(client, auth_headers):
    """更新个人档案"""
    resp = await client.patch(
        "/api/v1/users/profile",
        headers=auth_headers,
        json={
            "playing_style": "loop",
            "self_assessed_level": "intermediate",
            "equipment_config": {
                "blade": {"brand": "蝴蝶", "model": "Viscaria"},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "profile_completeness" in data
    assert "playing_style" in data["updated_fields"]


@pytest.mark.asyncio
async def test_update_profile_invalid_style(client, auth_headers):
    """打法类型不在枚举中返回 422"""
    resp = await client.patch(
        "/api/v1/users/profile",
        headers=auth_headers,
        json={"playing_style": "invalid_style"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_quota(client, auth_headers):
    """获取免费分析额度"""
    resp = await client.get("/api/v1/users/quota", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["daily_limit"] == 3
    assert data["remaining"] == 3
    assert "reset_at" in data


@pytest.mark.asyncio
async def test_get_me(client, auth_headers, test_user):
    """获取当前用户信息"""
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == test_user.id
    assert data["nickname"] == "测试用户"


@pytest.mark.asyncio
async def test_h5_token_flow(client, auth_headers):
    """H5 Token 生成和交换流程"""
    # 生成 H5 Token
    resp1 = await client.post("/api/v1/auth/h5-token", headers=auth_headers)
    assert resp1.status_code == 200
    h5_token = resp1.json()["data"]["token"]

    # 第一次交换（成功）
    resp2 = await client.post("/api/v1/auth/h5-exchange", json={"token": h5_token})
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()["data"]

    # 第二次交换（失败 - 一次性使用）
    resp3 = await client.post("/api/v1/auth/h5-exchange", json={"token": h5_token})
    assert resp3.status_code == 401


@pytest.mark.asyncio
async def test_consent_flow(client, auth_headers):
    """consent 链路 — 记录同意 + 查询状态"""
    # 查询初始状态（未同意）
    resp1 = await client.get("/api/v1/auth/consent-status", headers=auth_headers)
    assert resp1.status_code == 200
    assert resp1.json()["data"]["consented"] is False

    # 记录同意
    resp2 = await client.post(
        "/api/v1/auth/consent",
        headers=auth_headers,
        json={"consent_type": "privacy_policy", "policy_version": "v1.0"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["consented"] is True

    # 查询已同意状态
    resp3 = await client.get("/api/v1/auth/consent-status", headers=auth_headers)
    assert resp3.status_code == 200
    assert resp3.json()["data"]["consented"] is True


# =================================================================
# 手机号验证码登录测试
# =================================================================

@pytest.mark.asyncio
async def test_send_sms_success(client):
    """发送短信验证码成功"""
    resp = await client.post(
        "/api/v1/auth/send-sms",
        json={"phone": "13800138000"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["expire_seconds"] == 300


@pytest.mark.asyncio
async def test_send_sms_rate_limit(client):
    """60 秒内重复发送返回 429"""
    resp1 = await client.post(
        "/api/v1/auth/send-sms",
        json={"phone": "13900139000"},
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/api/v1/auth/send-sms",
        json={"phone": "13900139000"},
    )
    assert resp2.status_code == 429


@pytest.mark.asyncio
async def test_send_sms_invalid_phone(client):
    """非法手机号返回 400（R13-Auth-N2: Schema pattern 移除，service 层校验
    返回 400 + 中文消息，对齐 API §2.3 契约）"""
    resp = await client.post(
        "/api/v1/auth/send-sms",
        json={"phone": "12345"},
    )
    assert resp.status_code == 400
    assert resp.json()["message"] == "手机号格式不正确"


@pytest.mark.asyncio
async def test_phone_login_success(client, db_session):
    """手机号验证码登录成功（新用户自动注册）"""
    # 先发送验证码
    await client.post(
        "/api/v1/auth/send-sms",
        json={"phone": "13700137000"},
    )

    # 从 Redis 读取验证码（测试环境 SMS_MOCK=true）
    from app.core.redis import get_redis
    redis = await get_redis()
    code = await redis.get("sms:code:13700137000")
    assert code is not None

    # 使用验证码登录
    resp = await client.post(
        "/api/v1/auth/phone-login",
        json={"phone": "13700137000", "code": code},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["nickname"].startswith("球友")


@pytest.mark.asyncio
async def test_phone_login_wrong_code(client):
    """验证码错误返回 400"""
    # 先发送验证码
    await client.post(
        "/api/v1/auth/send-sms",
        json={"phone": "13600136000"},
    )

    # 使用错误验证码登录
    resp = await client.post(
        "/api/v1/auth/phone-login",
        json={"phone": "13600136000", "code": "000000"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_phone_login_expired_code(client):
    """验证码过期返回 400"""
    # 未发送验证码直接登录
    resp = await client.post(
        "/api/v1/auth/phone-login",
        json={"phone": "13500135000", "code": "123456"},
    )
    assert resp.status_code == 400


# =====================================================================
# R13-Auth-N1 / R13-Auth-N2: 验证码尝试限制 + 400 中文消息契约
# =====================================================================

class TestPhoneLoginAttemptLimit:
    """R13-Auth-N1: 验证码错误尝试次数限制（API §2.2 契约 429）"""

    async def test_attempt_limit_429_after_5_failures(self, client):
        """5 次错误验证码后第 6 次尝试（即使验证码正确）返回 429"""
        from app.core.redis import get_redis

        phone = "13800138001"
        # 发送验证码并读取
        await client.post("/api/v1/auth/send-sms", json={"phone": phone})
        redis = await get_redis()
        code = await redis.get("sms:code:" + phone)
        assert code is not None

        # 5 次错误尝试（每次 400）
        for i in range(5):
            resp = await client.post(
                "/api/v1/auth/phone-login",
                json={"phone": phone, "code": "999999"},
            )
            assert resp.status_code == 400, f"第 {i + 1} 次错误尝试应返回 400"

        # 第 6 次（携带正确验证码）→ 429（锁定）
        resp = await client.post(
            "/api/v1/auth/phone-login",
            json={"phone": phone, "code": code},
        )
        assert resp.status_code == 429
        assert resp.json()["message"] == "验证码尝试次数过多，请稍后重试"

        # 清理锁定键
        await redis.delete("sms:attempts:" + phone)

    async def test_success_login_clears_attempt_counter(self, client):
        """验证码正确登录后尝试计数被清除（新验证码重新计数）"""
        from app.core.redis import get_redis

        phone = "13800138002"
        await client.post("/api/v1/auth/send-sms", json={"phone": phone})
        redis = await get_redis()
        code = await redis.get("sms:code:" + phone)

        # 1 次错误 + 1 次正确
        resp_err = await client.post(
            "/api/v1/auth/phone-login",
            json={"phone": phone, "code": "999999"},
        )
        assert resp_err.status_code == 400
        attempts_after_err = await redis.get("sms:attempts:" + phone)
        assert attempts_after_err is not None, "错误尝试后应有计数"

        resp_ok = await client.post(
            "/api/v1/auth/phone-login",
            json={"phone": phone, "code": code},
        )
        assert resp_ok.status_code == 200
        attempts_after_ok = await redis.get("sms:attempts:" + phone)
        assert attempts_after_ok is None, "登录成功后尝试计数应被清除"


class TestAuth400ChineseMessages:
    """R13-Auth-N2: 三端点 400 中文消息契约（API §2.1/§2.2/§2.3）"""

    async def test_wechat_login_empty_code_400(self, client):
        """wechat-login code 为空 → 400 + "登录凭证不能为空"（API §2.1）"""
        resp = await client.post(
            "/api/v1/auth/wechat-login",
            json={"code": ""},
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "登录凭证不能为空"

    async def test_phone_login_invalid_phone_400(self, client):
        """phone-login 非法手机号 → 400 + "手机号格式不正确"（API §2.2）"""
        resp = await client.post(
            "/api/v1/auth/phone-login",
            json={"phone": "12345", "code": "123456"},
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "手机号格式不正确"

    async def test_phone_login_non_digit_code_400(self, client):
        """phone-login 非 6 位数字验证码 → 400 "验证码错误或已过期"
        （Schema pattern 移除后归入验证码错误语义）"""
        resp = await client.post(
            "/api/v1/auth/phone-login",
            json={"phone": "13900139000", "code": "abc123"},
        )
        assert resp.status_code == 400
        assert resp.json()["message"] == "验证码错误或已过期"
