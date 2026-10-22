"""
app/api/v1/admin/router.py — 管理后台 API 路由

依据：API §19 admin 端点（17 个）
      切片 13-infrastructure/admin.md
Admin 独立认证体系：admin_user 表 + Redis session（admin:session:{token}, TTL 30min）
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_admin_session, require_super_admin, require_content_admin, require_model_admin
from app.core.exceptions import AppException, ERR_UNAUTHORIZED
from app.core.limiter import limiter
from app.core.response import success
from app.schemas.admin import (
    AdminLoginRequest, AdminLoginResponse,
    ConfigCreateRequest, ConfigUpdateRequest,
    BanRequest,
    KnowledgeCategoryCreateRequest, KnowledgeCategoryUpdateRequest,
    RuleCreateRequest,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["管理后台"])


# ==================== Admin 登录/登出 ====================

@limiter.limit("5/minute")
@router.post("/login", summary="管理员登录")
async def admin_login(body: AdminLoginRequest, request: Request):
    """管理员登录（独立认证体系）"""
    data = await AdminService.login(body.username, body.password)
    return success(data=data)


@router.post("/logout", summary="管理员登出")
async def admin_logout(
    request: Request,
    session: dict = Depends(get_admin_session),
):
    """管理员登出"""
    from app.core.deps import bearer_scheme
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "").replace("bearer ", "")
    await AdminService.logout(token)
    return success(message="已登出")


# ==================== 用户管理 ====================

@router.get("/users", summary="用户列表查询")
async def list_users(
    request: Request,
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: dict = Depends(get_admin_session),
):
    """用户列表查询"""
    data = await AdminService.list_users(status, q, page, page_size)
    return success(data=data)


@router.post("/users/{user_id}/ban", summary="封禁用户")
async def ban_user(
    user_id: int,
    body: BanRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """封禁用户（仅超级管理员）"""
    await AdminService.ban_user(user_id, body.reason, session["admin_id"])
    return success(message="用户已封禁")


@router.post("/users/{user_id}/unban", summary="解禁用户")
async def unban_user(
    user_id: int,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """解禁用户（仅超级管理员）"""
    await AdminService.unban_user(user_id, session["admin_id"])
    return success(message="用户已解禁")


# ==================== 系统配置 ====================

@router.get("/configs", summary="配置列表")
async def list_configs(
    request: Request,
    session: dict = Depends(get_admin_session),
):
    """配置列表"""
    data = await AdminService.list_configs()
    return success(data=data)


@router.get("/configs/{key}", summary="获取单个配置")
async def get_config(
    key: str,
    request: Request,
    session: dict = Depends(get_admin_session),
):
    """获取单个配置"""
    data = await AdminService.get_config(key)
    return success(data=data)


@router.post("/configs", summary="创建配置")
async def create_config(
    body: ConfigCreateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """创建配置（仅超级管理员）"""
    data = await AdminService.create_config(body.key, body.value, body.description, session["admin_id"])
    return success(data=data, message="配置已创建")


@router.patch("/configs/{key}", summary="更新配置")
async def update_config(
    key: str,
    body: ConfigUpdateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """更新配置（仅超级管理员）"""
    data = await AdminService.update_config(key, body.value, body.description, session["admin_id"])
    return success(data=data, message="配置已更新")


@router.delete("/configs/{key}", summary="删除配置")
async def delete_config(
    key: str,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """删除配置（仅超级管理员）"""
    await AdminService.delete_config(key, session["admin_id"])
    return success(message="配置已删除")


# ==================== 审计日志 ====================

@router.get("/audit-logs", summary="审计日志查询")
async def list_audit_logs(
    request: Request,
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: dict = Depends(get_admin_session),
):
    """审计日志查询"""
    data = await AdminService.list_audit_logs(action, target_type, page, page_size)
    return success(data=data)


# ==================== 知识库管理 ====================

@router.post("/knowledge/categories", summary="创建知识分类")
async def create_category(
    body: KnowledgeCategoryCreateRequest,
    request: Request,
    session: dict = Depends(require_content_admin),
):
    """创建知识分类（内容管理员）"""
    data = await AdminService.create_category(body.name, body.code, session["admin_id"])
    return success(data=data, message="分类已创建")


@router.patch("/knowledge/categories/{category_id}", summary="更新知识分类")
async def update_category(
    category_id: int,
    body: KnowledgeCategoryUpdateRequest,
    request: Request,
    session: dict = Depends(require_content_admin),
):
    """更新知识分类（内容管理员）"""
    data = await AdminService.update_category(
        category_id, body.name, body.code, session["admin_id"]
    )
    return success(data=data, message="分类已更新")


@router.delete("/knowledge/categories/{category_id}", summary="删除知识分类")
async def delete_category(
    category_id: int,
    request: Request,
    session: dict = Depends(require_content_admin),
):
    """删除知识分类（内容管理员）"""
    await AdminService.delete_category(category_id, session["admin_id"])
    return success(message="分类已删除")


@router.post("/knowledge/rules", summary="创建知识规则")
async def create_rule(
    body: RuleCreateRequest,
    request: Request,
    session: dict = Depends(require_content_admin),
):
    """创建知识规则（内容管理员）"""
    data = await AdminService.create_rule(
        body.rule_id, body.rule_name, body.rule_type,
        body.condition, body.diagnosis,
        body.training_methods, body.training_plan_template,
        session["admin_id"],
    )
    return success(data=data, message="规则已创建")


@router.patch("/knowledge/rules/{rule_id}/toggle", summary="切换知识规则状态")
async def toggle_rule(
    rule_id: str,
    request: Request,
    session: dict = Depends(require_content_admin),
):
    """切换知识规则状态（内容管理员）"""
    data = await AdminService.toggle_rule(rule_id, session["admin_id"])
    return success(data=data, message="规则状态已切换")


# ==================== 模型版本管理 ====================

@router.post("/model-versions/{version_id}/activate", summary="激活模型版本")
async def activate_model_version(
    version_id: str,
    request: Request,
    session: dict = Depends(require_model_admin),
):
    """激活模型版本（模型管理员）"""
    data = await AdminService.activate_model_version(version_id, session["admin_id"])
    return success(data=data, message="模型版本已激活")
