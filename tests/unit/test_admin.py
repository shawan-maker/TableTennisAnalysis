"""
tests/unit/test_admin.py — 管理后台单元测试

依据：API §19 admin 端点（17 个）
      切片 13-infrastructure/admin.md
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.core.security import pwd_context
from app.services.admin_service import AdminService, ADMIN_SESSION_PREFIX
from app.models.admin import AdminUser


@pytest_asyncio.fixture(scope="function")
async def admin_in_db(db_session):
    """在 DB 中创建一个管理员用户"""
    admin = AdminUser(
        username="test_admin",
        password_hash=pwd_context.hash("Admin@123"),
        role="super_admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture(scope="function")
async def admin_token(admin_in_db):
    """获取 admin session token"""
    data = await AdminService.login("test_admin", "Admin@123")
    return data.session_token


@pytest_asyncio.fixture(scope="function")
async def admin_headers(admin_token):
    """admin 认证 headers"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture(scope="function")
async def content_admin_in_db(db_session):
    """创建内容管理员"""
    admin = AdminUser(
        username="content_admin",
        password_hash=pwd_context.hash("Admin@123"),
        role="content_admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture(scope="function")
async def content_admin_token(content_admin_in_db):
    """获取 content_admin session token"""
    data = await AdminService.login("content_admin", "Admin@123")
    return data.session_token


@pytest.mark.asyncio
class TestAdminAuth:
    """管理员认证测试"""

    async def test_login_success(self, admin_in_db):
        """管理员登录成功"""
        data = await AdminService.login("test_admin", "Admin@123")
        assert data.session_token
        assert data.admin.username == "test_admin"
        assert data.admin.role == "super_admin"
        assert data.expires_in == 1800

    async def test_login_wrong_password(self, admin_in_db):
        """密码错误"""
        from app.core.exceptions import AppException
        with pytest.raises(AppException) as exc_info:
            await AdminService.login("test_admin", "wrong_password")
        assert exc_info.value.status_code == 401

    async def test_login_nonexistent(self, db_session):
        """不存在的管理员"""
        from app.core.exceptions import AppException
        with pytest.raises(AppException) as exc_info:
            await AdminService.login("nonexistent", "password")
        assert exc_info.value.status_code == 401

    async def test_logout(self, admin_token):
        """登出后 session 失效"""
        from app.core.redis import get_redis
        await AdminService.logout(admin_token)
        redis = await get_redis()
        exists = await redis.exists(f"{ADMIN_SESSION_PREFIX}{admin_token}")
        assert exists == 0


@pytest.mark.asyncio
class TestAdminUserManagement:
    """用户管理测试"""

    async def test_list_users(self, client, admin_headers, test_user):
        """用户列表"""
        resp = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    async def test_ban_user(self, client, admin_headers, test_user):
        """封禁用户"""
        resp = await client.post(
            f"/api/v1/admin/users/{test_user.id}/ban",
            json={"reason": "违规操作"},
            headers=admin_headers,
        )
        assert resp.status_code == 200

    async def test_ban_nonexistent(self, client, admin_headers):
        """封禁不存在的用户"""
        resp = await client.post(
            "/api/v1/admin/users/999999/ban",
            json={"reason": "测试"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    async def test_ban_already_banned(self, client, admin_headers, test_user):
        """重复封禁"""
        await client.post(
            f"/api/v1/admin/users/{test_user.id}/ban",
            json={"reason": "第一次封禁"},
            headers=admin_headers,
        )
        resp = await client.post(
            f"/api/v1/admin/users/{test_user.id}/ban",
            json={"reason": "第二次封禁"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    async def test_unban(self, client, admin_headers, test_user):
        """解禁用户"""
        await client.post(
            f"/api/v1/admin/users/{test_user.id}/ban",
            json={"reason": "封禁"},
            headers=admin_headers,
        )
        resp = await client.post(
            f"/api/v1/admin/users/{test_user.id}/unban",
            headers=admin_headers,
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAdminConfig:
    """系统配置测试"""

    async def test_create_config(self, client, admin_headers):
        """创建配置"""
        # R4-Admin-19: 字段名 key/value → config_key/config_value
        resp = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "test_key", "config_value": "test_value", "description": "测试配置"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["config_key"] == "test_key"

    async def test_get_config(self, client, admin_headers):
        """获取单个配置"""
        await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "get_test", "config_value": "val", "description": None},
            headers=admin_headers,
        )
        resp = await client.get("/api/v1/admin/configs/get_test", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["config_value"] == "val"

    async def test_update_config(self, client, admin_headers):
        """更新配置"""
        await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "update_test", "config_value": "old_val", "description": None},
            headers=admin_headers,
        )
        resp = await client.patch(
            "/api/v1/admin/configs/update_test",
            json={"config_value": "new_val", "description": "更新后"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["config_value"] == "new_val"

    async def test_delete_config(self, client, admin_headers):
        """删除配置"""
        await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "del_test", "config_value": "val", "description": None},
            headers=admin_headers,
        )
        resp = await client.delete("/api/v1/admin/configs/del_test", headers=admin_headers)
        assert resp.status_code == 200

    async def test_get_nonexistent_config(self, client, admin_headers):
        """获取不存在的配置"""
        resp = await client.get("/api/v1/admin/configs/nonexistent", headers=admin_headers)
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestAdminAuditLog:
    """审计日志测试"""

    async def test_list_audit_logs(self, client, admin_headers, test_user):
        """查询审计日志"""
        # 先产生一些审计日志
        await client.post(
            f"/api/v1/admin/users/{test_user.id}/ban",
            json={"reason": "产生审计日志"},
            headers=admin_headers,
        )
        resp = await client.get("/api/v1/admin/audit-logs", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1


@pytest.mark.asyncio
class TestAdminKnowledge:
    """知识库管理测试"""

    async def test_create_category(self, client, admin_headers):
        """创建知识分类"""
        resp = await client.post(
            "/api/v1/admin/knowledge/categories",
            json={"name": "正手技术", "code": "forehand"},
            headers=admin_headers,
        )
        assert resp.status_code == 200

    async def test_create_rule(self, client, admin_headers):
        """创建知识规则"""
        resp = await client.post(
            "/api/v1/admin/knowledge/rules",
            json={
                "rule_id": "test_rule_001",
                "rule_name": "测试规则",
                "rule_type": "single",
                "condition": {"metric": "forehand_rate", "threshold": 0.3},
                "diagnosis": {"problem": "正手偏少", "severity": "medium"},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200

    async def test_toggle_rule(self, client, admin_headers):
        """切换规则状态"""
        create_resp = await client.post(
            "/api/v1/admin/knowledge/rules",
            json={
                "rule_id": "toggle_test",
                "rule_name": "切换测试",
                "rule_type": "single",
                "condition": {},
                "diagnosis": {},
            },
            headers=admin_headers,
        )
        rule_db_id = create_resp.json()["data"]["id"]
        # R4-Admin-13: toggle_rule 接受 is_active 显式参数
        # R12-Admin-4: rule_id 为 int 数据库 ID（对齐 API §19.5.5）
        resp = await client.patch(
            f"/api/v1/admin/knowledge/rules/{rule_db_id}/toggle?is_active=false",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == {"id": rule_db_id, "is_active": False}


@pytest.mark.asyncio
class TestAdminPermission:
    """权限控制测试"""

    async def test_admin_endpoints_without_token(self, client):
        """无 token 访问 admin 端点"""
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 401

    async def test_content_admin_cannot_ban(self, client, content_admin_token, test_user):
        """内容管理员不能封禁用户（仅超级管理员）"""
        resp = await client.post(
            f"/api/v1/admin/users/{test_user.id}/ban",
            json={"reason": "尝试封禁"},
            headers={"Authorization": f"Bearer {content_admin_token}"},
        )
        assert resp.status_code == 403

    # R4-Admin-23: activate_model_version 端点已注释（Phase 2 占位）
    # 测试相应跳过；S7+ 模型管理实现后恢复。
    @pytest.mark.skip(reason="R4-Admin-23: activate_model_version 端点注释（Phase 2 占位）")
    async def test_model_activate(self, client, admin_headers):
        """激活模型版本"""
        resp = await client.post(
            "/api/v1/admin/model-versions/v1.0.0/activate",
            headers=admin_headers,
        )
        assert resp.status_code == 200
