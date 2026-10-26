"""
app/schemas/auth.py — 认证模块 Pydantic Schema

依据：API §2 auth 端点契约 / 切片 01-auth/backend.md §4
规范：{Entity}Request / {Entity}Response 命名
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# 请求 Schema
# =============================================================================

class WechatLoginRequest(BaseModel):
    """微信小程序登录请求"""

    code: str = Field(..., min_length=1, description="wx.login() 返回的 code")
    nickname: Optional[str] = Field(default=None, max_length=64)
    avatar_url: Optional[str] = Field(default=None, max_length=512)


class PhoneLoginRequest(BaseModel):
    """手机号验证码登录请求"""

    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    code: str = Field(..., pattern=r"^\d{6}$", description="6 位验证码")


class SendSmsRequest(BaseModel):
    """发送短信验证码请求"""

    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求"""

    refresh_token: str = Field(..., min_length=1)


class H5ExchangeRequest(BaseModel):
    """H5 Token 换 JWT 请求"""

    token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """登出请求 — 同时携带 access_token 和 refresh_token"""

    access_token: str = Field(..., min_length=1, description="当前 access_token")
    refresh_token: Optional[str] = Field(default=None, description="当前 refresh_token")


class ConsentRequest(BaseModel):
    """用户同意隐私政策请求"""

    consent_type: Literal["privacy_policy", "user_agreement", "data_processing"] = Field(
        ..., description="同意类型"
    )
    policy_version: str = Field(..., max_length=16, description="政策版本号")


# =============================================================================
# 响应 Schema
# =============================================================================

class UserBrief(BaseModel):
    """用户简要信息"""

    id: int
    nickname: str
    avatar_url: Optional[str] = None
    has_profile: bool = False

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """登录响应"""

    access_token: str
    refresh_token: str
    expires_in: int = 7200  # 120 分钟
    user: UserBrief
    requires_consent: bool = False  # PIPL-001：是否需要用户同意当前版本隐私政策


class RefreshResponse(BaseModel):
    """Token 刷新响应"""

    access_token: str
    refresh_token: str
    expires_in: int = 7200


class H5TokenResponse(BaseModel):
    """H5 Token 生成响应"""

    token: str
    expire_at: str


class CurrentUserResponse(BaseModel):
    """当前用户信息响应"""

    id: int
    nickname: str
    avatar_url: Optional[str] = None
    has_profile: bool = False
    membership_tier: Optional[str] = None
    membership_expire_at: Optional[str] = None


class ConsentResponse(BaseModel):
    """同意状态响应"""

    consented: bool
    consent_at: Optional[str] = None
    policy_version: Optional[str] = None


class SendSmsResponse(BaseModel):
    """发送短信验证码响应"""

    expire_seconds: int = 300
