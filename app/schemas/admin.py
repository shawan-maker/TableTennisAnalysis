"""
app/schemas/admin.py — 管理后台 Pydantic Schema

依据：API §19 admin 端点
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- 请求 Schema ---
class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


# R4-Admin-19: 字段名 key/value → config_key/config_value（与 DB 列名/设计一致）
class ConfigCreateRequest(BaseModel):
    config_key: str = Field(..., max_length=64)
    config_value: str | dict = Field(..., description="配置值（字符串或 JSON 对象）")
    description: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    config_value: str | dict = Field(..., description="配置值（字符串或 JSON 对象）")
    description: Optional[str] = None


# R4-Admin-18: BanRequest → UserBanRequest
class UserBanRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# R4-Admin-3: 添加 content 字段
# R4-Admin-18: KnowledgeCategoryCreateRequest → CategoryCreateRequest
class CategoryCreateRequest(BaseModel):
    name: str = Field(..., max_length=64)
    code: str = Field(..., max_length=32)
    content: dict = Field(default_factory=dict, description="分类内容")


# R4-Admin-11: 仅允许 name 和 content 字段（不允许更新 code）
# R4-Admin-18: KnowledgeCategoryUpdateRequest → CategoryUpdateRequest
class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    content: Optional[dict] = Field(default=None, description="分类内容")


# R4-Admin-12: 添加 adjustment_action 字段；training_methods 类型 dict → list
class RuleCreateRequest(BaseModel):
    rule_id: str = Field(..., max_length=64)
    rule_name: str = Field(..., max_length=128)
    rule_type: str = Field(..., max_length=32)
    condition: dict
    diagnosis: dict
    training_methods: Optional[list] = None
    training_plan_template: Optional[str] = None
    adjustment_action: Optional[str] = Field(default=None, max_length=32, description="调整动作 maintain/adjust/escalate/new_goal")


# --- 响应 Schema ---
# R4-Admin-17: AdminBrief 在 AdminLoginResponse 之前定义，直接类型引用而非字符串引用
class AdminBrief(BaseModel):
    id: int
    username: str
    role: str
    model_config = {"from_attributes": True}


class AdminLoginResponse(BaseModel):
    session_token: str
    admin: AdminBrief
    expires_in: int = 1800


# R4-Admin-18: UserBrief → UserManageBrief（与 auth.UserBrief 区分）
class UserManageBrief(BaseModel):
    id: int
    nickname: str
    phone: Optional[str] = None
    openid: Optional[str] = None
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


# R4-Admin-16+19: ConfigBrief 字段名 key/value → config_key/config_value
# R4-Admin-15: 添加 updated_at 字段
class ConfigBrief(BaseModel):
    id: int
    config_key: str
    config_value: str | dict | None = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# R4-Admin-9+10: AuditLogBrief 添加 admin_username；移除 user_id/detail/ip_address（冗余/敏感）
class AuditLogBrief(BaseModel):
    id: int
    admin_id: int
    admin_username: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    changes: Optional[dict] = None
    created_at: datetime
    model_config = {"from_attributes": True}


AdminLoginResponse.model_rebuild()
