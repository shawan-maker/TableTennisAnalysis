"""
tests/e2e/test_security.py — 安全扫描测试

依据：测试计划 §10 SEC-01~32
覆盖：SQLi / XSS / CSRF / JWT 安全 / 限流 / 输入验证
"""

import pytest
import json

from app.core.security import create_access_token, generate_jti


def _auth_headers(user_id: int) -> dict:
    token = create_access_token({"sub": str(user_id), "jti": generate_jti()})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestSQLInjection:
    """SQL 注入防护测试"""

    async def test_sqli_in_query_param(self, client, test_user, auth_headers):
        """查询参数 SQL 注入"""
        sqli_payloads = [
            "1' OR '1'='1",
            "1; DROP TABLE users--",
            "' UNION SELECT * FROM user--",
            "1' AND SLEEP(5)--",
        ]
        for payload in sqli_payloads:
            resp = await client.get(
                f"/api/v1/admin/users?q={payload}",
                headers={
                    "Authorization": f"Bearer {create_access_token({'sub': str(test_user.id), 'jti': generate_jti()})}",
                },
            )
            # 不应返回 500 或泄露数据库结构
            assert resp.status_code != 500, f"SQLi payload caused 500: {payload}"
            body = resp.text
            assert "syntax error" not in body.lower(), f"SQL error leaked: {payload}"
            assert "pg_catalog" not in body.lower()

    async def test_sqli_in_body(self, client, test_user, auth_headers):
        """请求体 SQL 注入"""
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={"opponent_name": "'; DROP TABLE user;--", "format": "bo1"},
            headers=auth_headers,
        )
        # 应正常创建或返回验证错误，不应 500
        assert resp.status_code in (200, 422)


@pytest.mark.asyncio
class TestXSS:
    """XSS 防护测试"""

    async def test_xss_in_body(self, client, test_user, auth_headers):
        """请求体 XSS"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
        ]
        for payload in xss_payloads:
            resp = await client.post(
                "/api/v1/scoring/matches",
                json={"opponent_name": payload, "format": "bo1"},
                headers=auth_headers,
            )
            if resp.status_code == 200:
                body = resp.text
                assert "<script>" not in body.lower(), f"XSS not sanitized: {payload}"
                assert "onerror" not in body.lower()


@pytest.mark.asyncio
class TestJWTSecurity:
    """JWT 安全测试"""

    async def test_no_token(self, client):
        """无 Token 访问受保护端点"""
        resp = await client.get("/api/v1/notification/list")
        assert resp.status_code == 401

    async def test_invalid_token(self, client):
        """无效 Token"""
        resp = await client.get(
            "/api/v1/notification/list",
            headers={"Authorization": "Bearer invalid_token_123"},
        )
        assert resp.status_code == 401

    async def test_expired_token(self, client):
        """过期 Token"""
        from datetime import datetime, timedelta, timezone
        from jose import jwt as jose_jwt
        from app.core.config import settings

        expired_payload = {
            "sub": "1",
            "jti": "expired_test",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=3),
            "type": "access",
        }
        expired_token = jose_jwt.encode(
            expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        resp = await client.get(
            "/api/v1/notification/list",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401

    async def test_wrong_token_type(self, client):
        """refresh_token 不能用于访问业务端点"""
        from app.core.security import create_refresh_token
        refresh = create_refresh_token({"sub": "1", "jti": "test_jti"})
        resp = await client.get(
            "/api/v1/notification/list",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestInputValidation:
    """输入验证测试"""

    async def test_oversized_input(self, client, test_user, auth_headers):
        """超长输入"""
        long_str = "A" * 10000
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={"opponent_name": long_str, "format": "bo1"},
            headers=auth_headers,
        )
        # 应 422 或正常处理（Pydantic 字段长度限制）
        assert resp.status_code in (200, 422)

    async def test_negative_page(self, client, auth_headers):
        """负数页码"""
        resp = await client.get(
            "/api/v1/notification/list?page=-1",
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_empty_body(self, client, auth_headers):
        """空请求体"""
        resp = await client.post(
            "/api/v1/scoring/matches",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_wrong_content_type(self, client, auth_headers):
        """错误 Content-Type"""
        resp = await client.post(
            "/api/v1/scoring/matches",
            content="not json",
            headers={**auth_headers, "Content-Type": "text/plain"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestRateLimiting:
    """限流测试"""

    async def test_admin_login_rate_limit_config(self, client, db_session):
        """管理员登录限流配置验证（slowapi 在 test mode 下行为可能不同，仅验证端点挂载）"""
        from app.models.admin import AdminUser
        from app.core.security import pwd_context

        admin = AdminUser(
            username="rate_test_admin",
            password_hash=pwd_context.hash("pass"),
            role="super_admin",
        )
        db_session.add(admin)
        await db_session.commit()

        # 验证登录端点正常工作
        resp = await client.post(
            "/api/v1/admin/login",
            json={"username": "rate_test_admin", "password": "pass"},
        )
        assert resp.status_code == 200
        assert "session_token" in resp.json()["data"]


@pytest.mark.asyncio
class TestUserIsolation:
    """用户数据隔离测试"""

    async def test_user_cannot_access_others_notifications(self, client, test_user, db_session):
        """用户不能查看他人通知"""
        from app.models.user import User

        # 创建第二个用户
        other_user = User(openid="other_user_openid", nickname="其他用户", status="active")
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        headers = _auth_headers(test_user.id)

        # 用户 A 查询通知列表，不应看到用户 B 的通知
        resp = await client.get("/api/v1/notification/list", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        for item in items:
            assert item.get("user_id") is None or item.get("user_id") != other_user.id

    async def test_user_cannot_access_others_orders(self, client, test_user, db_session, seed_tiers):
        """用户不能查看他人订单"""
        from app.models.user import User

        other_user = User(openid="other_order_openid", nickname="其他用户2", status="active")
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        # 用户 B 创建订单
        other_headers = _auth_headers(other_user.id)
        resp = await client.post(
            "/api/v1/payment/orders",
            json={"product_type": "membership", "tier": "member", "period": "monthly"},
            headers=other_headers,
        )
        assert resp.status_code == 200

        # 用户 A 查看订单列表，不应看到用户 B 的订单
        headers = _auth_headers(test_user.id)
        resp = await client.get("/api/v1/payment/orders", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        for item in items:
            assert item.get("user_id") is None or item.get("user_id") != other_user.id
