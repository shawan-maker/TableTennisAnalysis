"""
app/api/v1/admin/router.py — 管理后台 API 路由

依据：API §19 admin 端点（17 个）
      切片 13-infrastructure/admin.md
Admin 独立认证体系：admin_user 表 + Redis session（admin:session:{token}, TTL 30min）
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_admin_session, require_super_admin, require_model_admin
from app.core.exceptions import AppException, ERR_UNAUTHORIZED
from app.core.limiter import RateLimits, limiter
from app.core.response import success
# R4-Admin-18: Schema 重命名
from app.schemas.admin import (
    AdminLoginRequest, AdminLoginResponse,
    ConfigCreateRequest, ConfigUpdateRequest,
    UserBanRequest,
    CategoryCreateRequest, CategoryUpdateRequest,
    RuleCreateRequest,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["管理后台"])
def _client_ip(request: Request) -> str | None:
    """R13-Admin-1: 提取客户端 IP（敏感管理操作审计溯源用，PIPL）"""
    return request.client.host if request.client else None




# ==================== Admin 登录/登出 ====================

@router.post("/login", summary="管理员登录")
@limiter.limit("5/minute")
async def admin_login(body: AdminLoginRequest, request: Request):
    """管理员登录（独立认证体系）"""
    data = await AdminService.login(body.username, body.password)
    return success(data=data)


# R4-Admin-1: 所有 admin 端点添加 @limiter.limit(RateLimits.DEFAULT)
@router.post("/logout", summary="管理员登出")
@limiter.limit(RateLimits.DEFAULT)
async def admin_logout(
    request: Request,
    session: dict = Depends(get_admin_session),
):
    """管理员登出"""
    auth = request.headers.get("authorization", "")
    # R5-Admin-4: 支持 "Admin xxx" 和 "Bearer xxx" 两种前缀
    parts = auth.split(" ", 1)
    token = parts[1] if len(parts) == 2 and parts[0] in ("Admin", "Bearer") else auth
    await AdminService.logout(token)
    return success(message="已登出")


# ==================== 用户管理 ====================

@router.get("/users", summary="用户列表查询")
@limiter.limit(RateLimits.DEFAULT)
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


# R4-Admin-18: BanRequest → UserBanRequest
@router.post("/users/{user_id}/ban", summary="封禁用户")
@limiter.limit(RateLimits.DEFAULT)
async def ban_user(
    user_id: int,
    body: UserBanRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """封禁用户（仅超级管理员）"""
    # R4-Admin-5: 返回 data 字段
    data = await AdminService.ban_user(
        user_id, body.reason, session["admin_id"], ip_address=_client_ip(request)
    )
    return success(data=data, message="用户已封禁")


@router.post("/users/{user_id}/unban", summary="解禁用户")
@limiter.limit(RateLimits.DEFAULT)
async def unban_user(
    user_id: int,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """解禁用户（仅超级管理员）"""
    # R4-Admin-5: 返回 data 字段
    data = await AdminService.unban_user(
        user_id, session["admin_id"], ip_address=_client_ip(request)
    )
    return success(data=data, message="用户已解禁")


# ==================== 系统配置 ====================

@router.get("/configs", summary="配置列表")
@limiter.limit(RateLimits.DEFAULT)
async def list_configs(
    request: Request,
    session: dict = Depends(get_admin_session),
):
    """配置列表"""
    data = await AdminService.list_configs()
    return success(data=data)


@router.get("/configs/{key}", summary="获取单个配置")
@limiter.limit(RateLimits.DEFAULT)
async def get_config(
    key: str,
    request: Request,
    session: dict = Depends(get_admin_session),
):
    """获取单个配置"""
    data = await AdminService.get_config(key)
    return success(data=data)


@router.post("/configs", summary="创建配置")
@limiter.limit(RateLimits.DEFAULT)
async def create_config(
    body: ConfigCreateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """创建配置（仅超级管理员）"""
    # R4-Admin-19: body.key → body.config_key, body.value → body.config_value
    data = await AdminService.create_config(
        body.config_key, body.config_value, body.description, session["admin_id"],
        ip_address=_client_ip(request),
    )
    return success(data=data, message="配置已创建")


@router.patch("/configs/{key}", summary="更新配置")
@limiter.limit(RateLimits.DEFAULT)
async def update_config(
    key: str,
    body: ConfigUpdateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """更新配置（仅超级管理员）"""
    # R4-Admin-19: body.value → body.config_value
    data = await AdminService.update_config(
        key, body.config_value, body.description, session["admin_id"],
        ip_address=_client_ip(request),
    )
    return success(data=data, message="配置已更新")


@router.delete("/configs/{key}", summary="删除配置")
@limiter.limit(RateLimits.DEFAULT)
async def delete_config(
    key: str,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """删除配置（仅超级管理员）"""
    await AdminService.delete_config(
        key, session["admin_id"], ip_address=_client_ip(request)
    )
    return success(message="配置已删除")


# ==================== 审计日志 ====================

@router.get("/audit-logs", summary="审计日志查询")
@limiter.limit(RateLimits.DEFAULT)
async def list_audit_logs(
    request: Request,
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    admin_id: int | None = Query(default=None, description="按管理员 ID 筛选"),
    start_date: str | None = Query(default=None, description="起始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: dict = Depends(get_admin_session),
):
    """审计日志查询（支持管理员/时间段筛选）"""
    from datetime import datetime, timezone
    from datetime import time as dt_time
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        except ValueError:
            start_dt = None
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date).replace(
                tzinfo=timezone.utc, hour=23, minute=59, second=59,
            )
        except ValueError:
            end_dt = None
    data = await AdminService.list_audit_logs(
        action, target_type, admin_id, start_dt, end_dt, page, page_size,
    )
    return success(data=data)


# ==================== 知识库管理 ====================

# R4-Admin-18: KnowledgeCategoryCreateRequest → CategoryCreateRequest
@router.post("/knowledge/categories", summary="创建知识分类")
@limiter.limit(RateLimits.DEFAULT)
async def create_category(
    body: CategoryCreateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """创建知识分类（超级管理员）"""
    # R4-Admin-3: 传递 content
    data = await AdminService.create_category(
        body.name, body.code, session["admin_id"], body.content, ip_address=_client_ip(request),
    )
    return success(data=data, message="分类已创建")


# R4-Admin-11: 仅允许更新 name 和 content（不允许更新 code）
# R4-Admin-18: KnowledgeCategoryUpdateRequest → CategoryUpdateRequest
@router.patch("/knowledge/categories/{category_id}", summary="更新知识分类")
@limiter.limit(RateLimits.DEFAULT)
async def update_category(
    category_id: int,
    body: CategoryUpdateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """更新知识分类（超级管理员，仅 name/content 可改）"""
    data = await AdminService.update_category(
        category_id, body.name, body.content, session["admin_id"],
        ip_address=_client_ip(request),
    )
    return success(data=data, message="分类已更新")


@router.delete("/knowledge/categories/{category_id}", summary="删除知识分类")
@limiter.limit(RateLimits.DEFAULT)
async def delete_category(
    category_id: int,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """删除知识分类（超级管理员）"""
    await AdminService.delete_category(
        category_id, session["admin_id"], ip_address=_client_ip(request)
    )
    return success(message="分类已删除")


@router.post("/knowledge/rules", summary="创建知识规则")
@limiter.limit(RateLimits.DEFAULT)
async def create_rule(
    body: RuleCreateRequest,
    request: Request,
    session: dict = Depends(require_super_admin),
):
    """创建知识规则（超级管理员）"""
    data = await AdminService.create_rule(
        body.rule_id, body.rule_name, body.rule_type,
        body.condition, body.diagnosis,
        body.training_methods, body.training_plan_template,
        body.adjustment_action,
        session["admin_id"],
        ip_address=_client_ip(request),
    )
    return success(data=data, message="规则已创建")


# R4-Admin-13: toggle_rule 接受 is_active 显式参数而非 toggle
# R12-Admin-4: rule_id 为 int 数据库 ID（对齐 API §19.5.5 参数表）
@router.patch("/knowledge/rules/{rule_id}/toggle", summary="设置知识规则状态")
@limiter.limit(RateLimits.DEFAULT)
async def toggle_rule(
    rule_id: int,
    request: Request,
    is_active: bool = Query(..., description="目标状态 true=启用/false=禁用"),
    session: dict = Depends(require_super_admin),
):
    """设置知识规则状态（超级管理员，显式 is_active 参数）"""
    data = await AdminService.toggle_rule(
        rule_id, is_active, session["admin_id"], ip_address=_client_ip(request)
    )
    return success(data=data, message="规则状态已更新")


# ==================== 模型版本管理 ====================

# R4-Admin-23: activate_model_version 注释掉（Phase 2 占位）
# @limiter.limit(RateLimits.DEFAULT)
# @router.post("/model-versions/{version_id}/activate", summary="激活模型版本")
# async def activate_model_version(
#     version_id: str,
#     request: Request,
#     session: dict = Depends(require_model_admin),
# ):
#     """激活模型版本（模型管理员）— Phase 2 占位，S7+ 实现"""
#     data = await AdminService.activate_model_version(version_id, session["admin_id"])
#     return success(data=data, message="模型版本已激活")
