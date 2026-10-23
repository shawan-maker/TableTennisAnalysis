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


class ConfigCreateRequest(BaseModel):
    key: str = Field(..., max_length=64)
    value: str | dict = Field(..., description="配置值（字符串或 JSON 对象）")
    description: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    value: str | dict = Field(..., description="配置值（字符串或 JSON 对象）")
    description: Optional[str] = None


class BanRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class KnowledgeCategoryCreateRequest(BaseModel):
    name: str = Field(..., max_length=64)
    code: str = Field(..., max_length=32)


class KnowledgeCategoryUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    code: Optional[str] = Field(default=None, max_length=32)


class RuleCreateRequest(BaseModel):
    rule_id: str = Field(..., max_length=64)
    rule_name: str = Field(..., max_length=128)
    rule_type: str = Field(..., max_length=32)
    condition: dict
    diagnosis: dict
    training_methods: Optional[dict] = None
    training_plan_template: Optional[str] = None


# --- 响应 Schema ---
class AdminLoginResponse(BaseModel):
    session_token: str
    admin: "AdminBrief"
    expires_in: int = 1800


class AdminBrief(BaseModel):
    id: int
    username: str
    role: str
    model_config = {"from_attributes": True}


class UserBrief(BaseModel):
    id: int
    nickname: str
    phone: Optional[str] = None
    openid: Optional[str] = None
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ConfigBrief(BaseModel):
    id: int
    key: str
    value: str | dict | None = None
    description: Optional[str] = None
    model_config = {"from_attributes": True}


class AuditLogBrief(BaseModel):
    id: int
    admin_id: int
    user_id: Optional[int] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    changes: Optional[dict] = None
    detail: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


AdminLoginResponse.model_rebuild()
