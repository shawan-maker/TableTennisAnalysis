"""
tests/e2e/test_smoke.py — Smoke 测试

依据：测试计划 §11 SMOKE-01~04
快速验证核心服务可用性，适用于灰度环境快速验收。
"""

import pytest


@pytest.mark.asyncio
class TestSmoke:
    """Smoke 测试 — 核心端点快速验证"""

    async def test_health_check(self, client):
        """SMOKE-01: 健康检查端点"""
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_openapi_accessible(self, client):
        """SMOKE-02: OpenAPI 文档可访问"""
        resp = await client.get("/docs")
        assert resp.status_code == 200

    async def test_openapi_json(self, client):
        """SMOKE-03: OpenAPI JSON 可访问"""
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data
        assert len(data["paths"]) >= 80  # 81 unique paths (部分路径同 GET+POST)

    async def test_membership_tiers_auth(self, client, auth_headers):
        """SMOKE-04: 会员等级列表可访问（需认证）"""
        resp = await client.get("/api/v1/membership/tiers", headers=auth_headers)
        assert resp.status_code == 200

    async def test_auth_required(self, client):
        """SMOKE-05: 受保护端点需认证"""
        resp = await client.get("/api/v1/notification/list")
        assert resp.status_code == 401

    async def test_admin_auth_required(self, client):
        """SMOKE-06: 管理后台需独立认证"""
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 401
