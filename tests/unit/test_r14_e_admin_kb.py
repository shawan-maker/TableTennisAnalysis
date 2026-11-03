"""
tests/unit/test_r14_e_admin_kb.py — R14 审计认定的 admin / knowledge_base 测试缺口补齐

依据：R14 审计报告 Admin-T1~T5 + KB-1；切片 13-infrastructure/admin.md / knowledge_base.md
覆盖（既有测试未覆盖的分支）：
  Admin-T1  config/category/rule CRUD 审计日志回归（R9-Admin-P2-1：审计在 commit 后写入、
            target_id 为数据库主键 ID）— 既有 test_admin.py 仅断言 HTTP 状态码与响应体
            （L162-212 / L236-281），从未用独立会话断言 AuditLog 落库
  Admin-T2  认证/权限守卫缺口：非 admin 的普通用户 JWT 访问 admin 端点（→ 401，实现为
            Redis session 未命中）；is_active=False 管理员登录（admin_service L59-60 分支，
            既有仅覆盖 401 分支 test_admin.py L79-91）；R12-Admin-1 管理员禁用后存量
            session 立即失效（deps.py L161-172，无既有覆盖）
  Admin-T3  config 读取的 Redis 缓存路径（R4-Admin-7+8：get 缓存回填 / update / delete
            失效缓存）— 既有无任何缓存行为断言
  Admin-T4  审计日志查询端点过滤/分页（action/target_type/admin_id/date + 分页）—
            既有仅断言 total >= 1（test_admin.py L219-229）
  Admin-T5  update/delete 分支审计的 changes {old,new} 语义（R12-Admin-5）+ 失败路径
            （404/409）不产生幽灵审计记录
  KB-1     scripts/init_knowledge_base.py 重入安全（R14-KB-1：无 pop() 突变）—
            既有 test_knowledge_base.py TestInitScriptIdempotency（L499-538）的 _run_init
            每次删除 sys.modules 重新 import（L507-510），模块级常量每次都是新副本，
            无法覆盖「同一模块实例第二次调用」的缺陷模式，故此处补同实例双跑用例

明确跳过（既有覆盖，附证据）：
  - admin 登录成功/密码错误/不存在用户/logout：test_admin.py L71-99
  - 用户 ban/unban 的 404/409 分支与响应结构：test_admin.py L106-155
  - config CRUD 状态码/响应字段：test_admin.py L162-212
  - 知识分类/规则创建与 toggle 状态码：test_admin.py L236-281
  - 无 token 访问 admin 端点 → 401：test_admin.py L288-291
  - content_admin 封禁 → 403：test_admin.py L293-300
  - KB 规则引擎/占位符渲染/CRUD 查询/重导入式幂等双跑：test_knowledge_base.py L56-538
"""

import importlib
import json
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.exceptions import (
    AppException,
    ERR_CONFLICT,
    ERR_FORBIDDEN,
    ERR_NOT_FOUND,
    ERR_UNAUTHORIZED,
)
from app.core.redis import get_redis
from app.core.security import pwd_context
from app.models.admin import AdminUser, AuditLog, SystemConfig
from app.models.knowledge_base import (
    KnowledgeCategory,
    KnowledgeEntry,
    RuleDefinition,
    TrainingTemplate,
)
from app.services.admin_service import ADMIN_SESSION_PREFIX, AdminService


# =============================================================================
# 本地 fixture — 与 test_admin.py 同款（AdminUser 表独立认证体系）。
# 刻意不使用 conftest 的 admin_user/admin_headers（那是微信用户侧
# ADMIN_USER_IDS 提权 fixture，会污染 settings.ADMIN_USER_IDS）。
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def admin_in_db(db_session):
    """在 DB 中创建一个超级管理员用户"""
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


async def _audit_logs(db, **filters):
    """按条件查询 AuditLog（独立会话，按 id 升序返回全部命中行）。"""
    stmt = select(AuditLog)
    for col, val in filters.items():
        if val is not None:
            stmt = stmt.where(getattr(AuditLog, col) == val)
    return (await db.execute(stmt.order_by(AuditLog.id))).scalars().all()


# =============================================================================
# Admin-T1/T5：config CRUD 审计日志回归（R9-Admin-P2-1）
# =============================================================================

@pytest.mark.asyncio
class TestAdminAuditConfig:
    """config 增删改的审计日志：落库 / target_id / changes 语义 / 无幽灵审计"""

    async def test_create_config_audit_log_after_commit(
        self, client, admin_headers, admin_in_db, db_session
    ):
        """创建配置 → AuditLog 落库，target_id=数据库主键，业务行与审计均经独立会话可见（commit 后写入）"""
        resp = await client.post(
            "/api/v1/admin/configs",
            json={
                "config_key": "r14_audit_cfg",
                "config_value": "v1",
                "description": "审计回归",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200
        config_id = resp.json()["data"]["id"]

        # 业务行已提交（db_session 是独立于服务内部 session 的会话）
        row = await db_session.scalar(
            select(SystemConfig).where(SystemConfig.config_key == "r14_audit_cfg")
        )
        assert row is not None
        assert row.id == config_id

        logs = await _audit_logs(
            db_session,
            action="create",
            target_type="config",
            target_id=config_id,
            admin_id=admin_in_db.id,
        )
        assert len(logs) == 1
        log = logs[0]
        assert log.user_id is None  # admin 操作不关联 user 表
        assert log.changes == {
            "config_key": {"old": None, "new": "r14_audit_cfg"},
            "config_value": {"old": None, "new": "v1"},
        }

    async def test_update_config_audit_changes_semantics(
        self, client, admin_headers, admin_in_db, db_session
    ):
        """更新配置 → update 审计；R12-Admin-5：changes 仅记录 config_value 的 {old,new}"""
        create = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_upd_cfg", "config_value": "old_val", "description": None},
            headers=admin_headers,
        )
        assert create.status_code == 200
        config_id = create.json()["data"]["id"]

        resp = await client.patch(
            "/api/v1/admin/configs/r14_upd_cfg",
            json={"config_value": "new_val", "description": "更新说明"},
            headers=admin_headers,
        )
        assert resp.status_code == 200

        logs = await _audit_logs(
            db_session,
            action="update",
            target_type="config",
            target_id=config_id,
            admin_id=admin_in_db.id,
        )
        assert len(logs) == 1
        # description 变更不入审计（API §19 统一 {old,new} 结构仅 config_value）
        assert logs[0].changes == {"config_value": {"old": "old_val", "new": "new_val"}}

    async def test_delete_config_audit_and_row_removed(
        self, client, admin_headers, admin_in_db, db_session
    ):
        """删除配置 → delete 审计（changes 记录被删值）且业务行已删除"""
        create = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_del_cfg", "config_value": "del_val", "description": None},
            headers=admin_headers,
        )
        assert create.status_code == 200
        config_id = create.json()["data"]["id"]

        resp = await client.delete(
            "/api/v1/admin/configs/r14_del_cfg", headers=admin_headers
        )
        assert resp.status_code == 200

        assert await db_session.scalar(
            select(SystemConfig).where(SystemConfig.config_key == "r14_del_cfg")
        ) is None

        logs = await _audit_logs(
            db_session,
            action="delete",
            target_type="config",
            target_id=config_id,
            admin_id=admin_in_db.id,
        )
        assert len(logs) == 1
        assert logs[0].changes == {
            "config_key": {"old": "r14_del_cfg", "new": None},
            "config_value": {"old": "del_val", "new": None},
        }

    async def test_failed_config_ops_no_ghost_audit(
        self, client, admin_headers, admin_in_db, db_session
    ):
        """失败路径（409 重复创建 / 404 更新不存在 / 404 删除不存在）不写审计（审计仅在 commit 后写入）"""
        create = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_ghost_cfg", "config_value": "v1", "description": None},
            headers=admin_headers,
        )
        assert create.status_code == 200
        config_id = create.json()["data"]["id"]

        dup = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_ghost_cfg", "config_value": "v2", "description": None},
            headers=admin_headers,
        )
        assert dup.status_code == 409
        assert dup.json()["code"] == ERR_CONFLICT

        upd_missing = await client.patch(
            "/api/v1/admin/configs/r14_no_such_key",
            json={"config_value": "x"},
            headers=admin_headers,
        )
        assert upd_missing.status_code == 404
        assert upd_missing.json()["code"] == ERR_NOT_FOUND

        del_missing = await client.delete(
            "/api/v1/admin/configs/r14_no_such_key", headers=admin_headers
        )
        assert del_missing.status_code == 404
        assert del_missing.json()["code"] == ERR_NOT_FOUND

        # 全库仅 1 条审计（成功的那次 create），失败路径零幽灵审计
        all_logs = await _audit_logs(db_session, admin_id=admin_in_db.id)
        assert len(all_logs) == 1
        assert all_logs[0].action == "create"
        assert all_logs[0].target_id == config_id


# =============================================================================
# Admin-T1/T5：knowledge category / rule 审计日志回归（R9-Admin-P2-1）
# =============================================================================

@pytest.mark.asyncio
class TestAdminAuditKnowledge:
    """knowledge 增删改审计：target_type 统一为 "knowledge"、target_id=数据库主键"""

    async def test_create_category_audit_log(
        self, client, admin_headers, admin_in_db, db_session
    ):
        """创建知识分类 → create 审计，target_id=分类数据库主键"""
        resp = await client.post(
            "/api/v1/admin/knowledge/categories",
            json={
                "name": "R14分类",
                "code": "r14_cat",
                "content": {"subcategories": ["A"]},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        cat_id = resp.json()["data"]["id"]

        logs = await _audit_logs(
            db_session,
            action="create",
            target_type="knowledge",
            target_id=cat_id,
            admin_id=admin_in_db.id,
        )
        assert len(logs) == 1
        assert logs[0].changes == {
            "name": {"old": None, "new": "R14分类"},
            "code": {"old": None, "new": "r14_cat"},
        }

    async def test_update_delete_category_audit_log(
        self, client, admin_headers, admin_in_db, db_session
    ):
        """更新/删除知识分类 → update 审计记录 name/content 双字段 {old,new}；delete 记录 code"""
        create = await client.post(
            "/api/v1/admin/knowledge/categories",
            json={
                "name": "R14旧名",
                "code": "r14_cat2",
                "content": {"subcategories": ["A"]},
            },
            headers=admin_headers,
        )
        assert create.status_code == 200
        cat_id = create.json()["data"]["id"]

        upd = await client.patch(
            f"/api/v1/admin/knowledge/categories/{cat_id}",
            json={"name": "R14新名", "content": {"subcategories": ["B", "C"]}},
            headers=admin_headers,
        )
        assert upd.status_code == 200
        upd_logs = await _audit_logs(
            db_session,
            action="update",
            target_type="knowledge",
            target_id=cat_id,
            admin_id=admin_in_db.id,
        )
        assert len(upd_logs) == 1
        assert upd_logs[0].changes == {
            "name": {"old": "R14旧名", "new": "R14新名"},
            "content": {"old": {"subcategories": ["A"]}, "new": {"subcategories": ["B", "C"]}},
        }

        dele = await client.delete(
            f"/api/v1/admin/knowledge/categories/{cat_id}", headers=admin_headers
        )
        assert dele.status_code == 200
        assert await db_session.scalar(
            select(KnowledgeCategory).where(KnowledgeCategory.id == cat_id)
        ) is None
        del_logs = await _audit_logs(
            db_session,
            action="delete",
            target_type="knowledge",
            target_id=cat_id,
            admin_id=admin_in_db.id,
        )
        assert len(del_logs) == 1
        assert del_logs[0].changes == {"code": {"old": "r14_cat2", "new": None}}

    async def test_create_rule_and_toggle_audit_log(
        self, client, admin_headers, admin_in_db, db_session
    ):
        """创建规则 → create 审计 target_id=规则数据库主键；toggle → update 审计 is_active {old,new}"""
        create = await client.post(
            "/api/v1/admin/knowledge/rules",
            json={
                "rule_id": "R14_RULE_1",
                "rule_name": "R14规则",
                "rule_type": "single",
                "condition": {"metric": "backhand_ratio", "operator": "<", "threshold": 0.3},
                "diagnosis": {"problem": "反手偏少", "severity": "medium"},
            },
            headers=admin_headers,
        )
        assert create.status_code == 200
        rule_db_id = create.json()["data"]["id"]
        assert create.json()["data"]["rule_id"] == "R14_RULE_1"

        create_logs = await _audit_logs(
            db_session,
            action="create",
            target_type="knowledge",
            target_id=rule_db_id,
            admin_id=admin_in_db.id,
        )
        assert len(create_logs) == 1
        assert create_logs[0].changes == {"rule_id": {"old": None, "new": "R14_RULE_1"}}

        toggle = await client.patch(
            f"/api/v1/admin/knowledge/rules/{rule_db_id}/toggle?is_active=false",
            headers=admin_headers,
        )
        assert toggle.status_code == 200
        assert toggle.json()["data"] == {"id": rule_db_id, "is_active": False}

        toggle_logs = await _audit_logs(
            db_session,
            action="update",
            target_type="knowledge",
            target_id=rule_db_id,
            admin_id=admin_in_db.id,
        )
        assert len(toggle_logs) == 1
        assert toggle_logs[0].changes == {"is_active": {"old": True, "new": False}}


# =============================================================================
# Admin-T5：用户封禁/解禁审计（update 分支）
# =============================================================================

@pytest.mark.asyncio
class TestAdminAuditUser:
    """ban/unban 的 update 审计：status / ban_reason 字段级 {old,new}"""

    async def test_ban_unban_user_audit_log(
        self, client, admin_headers, admin_in_db, test_user, db_session
    ):
        ban = await client.post(
            f"/api/v1/admin/users/{test_user.id}/ban",
            json={"reason": "R14违规"},
            headers=admin_headers,
        )
        assert ban.status_code == 200

        ban_logs = await _audit_logs(
            db_session,
            action="update",
            target_type="user",
            target_id=test_user.id,
            admin_id=admin_in_db.id,
        )
        assert len(ban_logs) == 1
        assert ban_logs[0].changes == {
            "status": {"old": "active", "new": "banned"},
            "ban_reason": {"old": None, "new": "R14违规"},
        }

        unban = await client.post(
            f"/api/v1/admin/users/{test_user.id}/unban", headers=admin_headers
        )
        assert unban.status_code == 200

        unban_logs = await _audit_logs(
            db_session,
            action="update",
            target_type="user",
            target_id=test_user.id,
            admin_id=admin_in_db.id,
        )
        # 两条 update/user 审计：ban + unban（按 id 升序，第 2 条为 unban）
        assert len(unban_logs) == 2
        assert unban_logs[1].changes == {"status": {"old": "banned", "new": "active"}}


# =============================================================================
# Admin-T2：认证/权限守卫
# =============================================================================

@pytest.mark.asyncio
class TestAdminAuthGuards:
    """非 admin token / 禁用管理员登录 / 角色守卫 / 存量 session 失效"""

    async def test_regular_user_jwt_rejected(self, client, auth_headers):
        """普通用户 JWT 访问 admin 端点 → 401（admin session 为独立 Redis 体系，JWT 未命中 session）"""
        resp = await client.get("/api/v1/admin/users", headers=auth_headers)
        assert resp.status_code == 401
        assert resp.json()["code"] == ERR_UNAUTHORIZED

    async def test_inactive_admin_login_rejected(self, db_session):
        """is_active=False 的管理员登录 → 403（admin_service L59-60 分支，既有仅覆盖 401 分支）"""
        admin = AdminUser(
            username="r14_disabled_admin",
            password_hash=pwd_context.hash("Admin@123"),
            role="super_admin",
            is_active=False,
        )
        db_session.add(admin)
        await db_session.commit()

        with pytest.raises(AppException) as exc_info:
            await AdminService.login("r14_disabled_admin", "Admin@123")
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == ERR_FORBIDDEN

    async def test_content_admin_forbidden_on_super_admin_only_endpoints(
        self, client, content_admin_token
    ):
        """content_admin 访问仅超级管理员可用的端点（configs / knowledge）→ 403"""
        headers = {"Authorization": f"Bearer {content_admin_token}"}

        cfg = await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_forbidden_cfg", "config_value": "x"},
            headers=headers,
        )
        assert cfg.status_code == 403
        assert cfg.json()["code"] == ERR_FORBIDDEN

        rule = await client.post(
            "/api/v1/admin/knowledge/rules",
            json={
                "rule_id": "R14_FORBIDDEN",
                "rule_name": "x",
                "rule_type": "single",
                "condition": {},
                "diagnosis": {},
            },
            headers=headers,
        )
        assert rule.status_code == 403
        assert rule.json()["code"] == ERR_FORBIDDEN

    async def test_disabled_admin_session_invalidated_immediately(
        self, client, admin_headers, admin_token, admin_in_db, db_session
    ):
        """R12-Admin-1：管理员禁用后存量 session 立即失效 → 403，且 Redis session 被清除，再次访问 → 401"""
        admin_in_db.is_active = False
        await db_session.commit()

        resp = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == ERR_FORBIDDEN

        # session 已被守卫清除
        redis = await get_redis()
        assert await redis.exists(f"{ADMIN_SESSION_PREFIX}{admin_token}") == 0

        # 同一 token 再次访问 → 401（session 未命中）
        resp2 = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert resp2.status_code == 401
        assert resp2.json()["code"] == ERR_UNAUTHORIZED


# =============================================================================
# Admin-T3：config 读取的 Redis 缓存路径（R4-Admin-7+8）
# =============================================================================

@pytest.mark.asyncio
class TestAdminConfigCache:
    """get 回填缓存 / update 失效缓存 / delete 失效缓存"""

    async def test_get_config_populates_redis_cache(self, client, admin_headers):
        await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_cache_cfg", "config_value": "cv1", "description": None},
            headers=admin_headers,
        )
        resp = await client.get("/api/v1/admin/configs/r14_cache_cfg", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["config_value"] == "cv1"

        redis = await get_redis()
        cache_key = "config:r14_cache_cfg"
        assert await redis.exists(cache_key) == 1
        cached = json.loads(await redis.get(cache_key))
        assert cached["config_key"] == "r14_cache_cfg"
        assert cached["config_value"] == "cv1"
        # TTL 有效（CONFIG_CACHE_TTL=3600）
        assert 0 < await redis.ttl(cache_key) <= 3600

    async def test_update_config_invalidates_cache(self, client, admin_headers):
        """更新配置后缓存失效 → 再读返回新值（不返回旧缓存）"""
        await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_upd_cache", "config_value": "v1", "description": None},
            headers=admin_headers,
        )
        warm = await client.get("/api/v1/admin/configs/r14_upd_cache", headers=admin_headers)
        assert warm.json()["data"]["config_value"] == "v1"

        upd = await client.patch(
            "/api/v1/admin/configs/r14_upd_cache",
            json={"config_value": "v2", "description": None},
            headers=admin_headers,
        )
        assert upd.status_code == 200

        redis = await get_redis()
        assert await redis.exists("config:r14_upd_cache") == 0  # 失效

        after = await client.get("/api/v1/admin/configs/r14_upd_cache", headers=admin_headers)
        assert after.status_code == 200
        assert after.json()["data"]["config_value"] == "v2"  # 非旧缓存值

    async def test_delete_config_invalidates_cache(self, client, admin_headers):
        """删除配置后缓存失效 → 再读 404（不返回旧缓存值）"""
        await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_del_cache", "config_value": "v1", "description": None},
            headers=admin_headers,
        )
        warm = await client.get("/api/v1/admin/configs/r14_del_cache", headers=admin_headers)
        assert warm.status_code == 200

        dele = await client.delete(
            "/api/v1/admin/configs/r14_del_cache", headers=admin_headers
        )
        assert dele.status_code == 200

        after = await client.get("/api/v1/admin/configs/r14_del_cache", headers=admin_headers)
        assert after.status_code == 404  # 缓存已失效 + DB 行已删


# =============================================================================
# Admin-T4：审计日志查询端点过滤/分页
# =============================================================================

@pytest.mark.asyncio
class TestAuditLogQuery:
    """/admin/audit-logs 过滤（action/target_type/admin_id/日期）与分页"""

    async def _seed_logs(self, client, admin_headers, test_user):
        """产生 4 条已知审计：2×create/config + 1×update/user(ban) + 1×create/knowledge"""
        await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_q_cfg_a", "config_value": "a", "description": None},
            headers=admin_headers,
        )
        await client.post(
            "/api/v1/admin/configs",
            json={"config_key": "r14_q_cfg_b", "config_value": "b", "description": None},
            headers=admin_headers,
        )
        await client.post(
            f"/api/v1/admin/users/{test_user.id}/ban",
            json={"reason": "r14筛选"},
            headers=admin_headers,
        )
        await client.post(
            "/api/v1/admin/knowledge/categories",
            json={"name": "R14查询分类", "code": "r14_q_cat"},
            headers=admin_headers,
        )

    async def test_audit_log_filters(
        self, client, admin_headers, admin_in_db, test_user
    ):
        await self._seed_logs(client, admin_headers, test_user)

        async def query(**params):
            resp = await client.get(
                "/api/v1/admin/audit-logs", params=params, headers=admin_headers
            )
            assert resp.status_code == 200
            return resp.json()["data"]

        # action 过滤
        assert (await query(action="create"))["total"] == 3
        assert (await query(action="update"))["total"] == 1
        # action + target_type 组合
        data = await query(action="create", target_type="config")
        assert data["total"] == 2
        assert all(it["target_type"] == "config" for it in data["items"])
        # target_type 过滤
        assert (await query(target_type="user"))["total"] == 1
        assert (await query(target_type="knowledge"))["total"] == 1
        # admin_id 过滤 + JOIN admin_username
        mine = await query(admin_id=admin_in_db.id)
        assert mine["total"] == 4
        assert all(it["admin_username"] == "test_admin" for it in mine["items"])
        assert (await query(admin_id=999999))["total"] == 0
        # 日期过滤（宽边界命中 / 历史边界排除）
        assert (await query(start_date="2000-01-01"))["total"] == 4
        assert (await query(end_date="2099-01-01"))["total"] == 4
        assert (await query(end_date="2000-01-01"))["total"] == 0

    async def test_audit_log_pagination(
        self, client, admin_headers, admin_in_db, test_user
    ):
        await self._seed_logs(client, admin_headers, test_user)

        full = await client.get(
            "/api/v1/admin/audit-logs",
            params={"page": 1, "page_size": 100},
            headers=admin_headers,
        )
        assert full.status_code == 200
        full_data = full.json()["data"]
        assert full_data["total"] == 4
        assert len(full_data["items"]) == 4
        all_ids = {it["id"] for it in full_data["items"]}

        p1 = await client.get(
            "/api/v1/admin/audit-logs",
            params={"page": 1, "page_size": 2},
            headers=admin_headers,
        )
        p1_data = p1.json()["data"]
        assert p1_data["total"] == 4
        assert p1_data["page"] == 1
        assert p1_data["page_size"] == 2
        assert len(p1_data["items"]) == 2

        p2 = await client.get(
            "/api/v1/admin/audit-logs",
            params={"page": 2, "page_size": 2},
            headers=admin_headers,
        )
        p2_data = p2.json()["data"]
        assert len(p2_data["items"]) == 2

        ids1 = {it["id"] for it in p1_data["items"]}
        ids2 = {it["id"] for it in p2_data["items"]}
        assert ids1 & ids2 == set()
        assert ids1 | ids2 == all_ids

        # 第 3 页为空
        p3 = await client.get(
            "/api/v1/admin/audit-logs",
            params={"page": 3, "page_size": 2},
            headers=admin_headers,
        )
        assert p3.json()["data"]["items"] == []

        # 页内按 created_at 降序
        stamps = [datetime.fromisoformat(it["created_at"]) for it in p1_data["items"]]
        assert stamps[0] >= stamps[1]


# =============================================================================
# KB-1（R14-KB-1）：scripts/init_knowledge_base.py 同模块实例重入安全
# =============================================================================

@pytest.mark.asyncio
class TestInitScriptReentry:
    """同一模块实例上连续调用 init_knowledge_base()：不重复插入、不丢失条目、常量无突变

    与既有 test_knowledge_base.py TestInitScriptIdempotency 的区别：既有 _run_init
    （L507-510）每次删除 sys.modules 重新 import，模块级 PROBLEMS 常量每次都是新副本，
    无法覆盖 R14-KB-1 修复的缺陷模式（旧实现 pop("category_code") 突变模块常量，
    同实例第二次调用在跳过逻辑之前抛 KeyError）。
    """

    @staticmethod
    def _load_module():
        # 刻意不删除 sys.modules 缓存 —— 跨调用复用同一模块实例
        return importlib.import_module("scripts.init_knowledge_base")

    async def test_reentry_same_module_double_run_no_dup_no_loss(self, db_session):
        mod = self._load_module()

        stats1 = await mod.init_knowledge_base()
        assert stats1 == {"categories": 8, "entries": 2, "rules": 3, "templates": 1, "skipped": 0}

        # 同一实例第二次调用（旧实现此处 KeyError，幂等性失效）
        stats2 = await mod.init_knowledge_base()
        assert stats2 == {"categories": 0, "entries": 0, "rules": 0, "templates": 0, "skipped": 14}

        # 模块级常量未被突变（R14-KB-1：无 pop() 破坏）
        assert len(mod.CATEGORIES) == 8
        assert len(mod.PROBLEMS) == 2
        assert all("category_code" in p for p in mod.PROBLEMS)
        assert all("title" in p and "entry_type" in p for p in mod.PROBLEMS)
        assert len(mod.RULES) == 3
        assert len(mod.TEMPLATES) == 1

        # DB 计数不翻倍、不丢失
        assert await db_session.scalar(
            select(func.count()).select_from(KnowledgeCategory)
        ) == 8
        assert await db_session.scalar(
            select(func.count()).select_from(KnowledgeEntry)
        ) == 2
        assert await db_session.scalar(
            select(func.count()).select_from(RuleDefinition)
        ) == 3
        assert await db_session.scalar(
            select(func.count()).select_from(TrainingTemplate)
        ) == 1

    async def test_reentry_restores_missing_entry_without_duplicates(self, db_session):
        """部分数据丢失后重跑：仅补回缺失条目，其余跳过，无重复"""
        mod = self._load_module()
        await mod.init_knowledge_base()

        # 删除一条条目模拟部分丢失
        entry = await db_session.scalar(
            select(KnowledgeEntry).where(KnowledgeEntry.title == "正手拉球弧线过高")
        )
        assert entry is not None
        await db_session.delete(entry)
        await db_session.commit()

        stats = await mod.init_knowledge_base()
        assert stats["categories"] == 0
        assert stats["entries"] == 1  # 仅补回被删条目
        assert stats["rules"] == 0
        assert stats["templates"] == 0
        assert stats["skipped"] == 13  # 8 分类 + 1 剩余条目 + 3 规则 + 1 模板

        # 数据恢复完整且无重复
        assert await db_session.scalar(
            select(func.count()).select_from(KnowledgeEntry)
        ) == 2
        titles = {
            t
            for (t,) in await db_session.execute(
                select(KnowledgeEntry.title).order_by(KnowledgeEntry.id)
            )
        }
        assert titles == {"反手使用率不足", "正手拉球弧线过高"}
