"""
app/api/v1/auth/router.py — 认证模块 API 路由

依据：API §2 auth 端点契约 / 切片 01-auth/backend.md §7
规范：路由只调用 Service，禁止在路由中写业务逻辑
S1 实现：wechat-login / refresh / logout / me / h5-token / h5-exchange / consent / consent-status
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import RateLimits, limiter
from app.core.response import success
from app.models.user import User
from app.schemas.auth import (
    ConsentRequest,
    H5ExchangeRequest,
    LogoutRequest,
    RefreshTokenRequest,
    WechatLoginRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@limiter.limit(RateLimits.WECHAT_LOGIN)
@router.post("/wechat-login", summary="微信小程序登录")
async def wechat_login(body: WechatLoginRequest, request: Request):
    """微信小程序登录（code → JWT）"""
    data = await AuthService.wechat_login(body)
    return success(data=data.model_dump(), message="登录成功")


@limiter.limit(RateLimits.DEFAULT)
@router.post("/refresh", summary="刷新 access_token")
async def refresh_token(body: RefreshTokenRequest, request: Request):
    """使用 refresh_token 获取新的 access_token"""
    data = await AuthService.refresh_token(body.refresh_token)
    return success(data=data.model_dump())


@limiter.limit(RateLimits.DEFAULT)
@router.post("/logout", summary="登出")
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    body: LogoutRequest | None = None,
):
    """登出：同时撤销 access_token 和 refresh_token（SEC-001 修复）"""
    await AuthService.logout(
        user.id,
        body.access_token if body else "",
        body.refresh_token if body else None,
    )
    return success(message="登出成功")


@limiter.limit(RateLimits.DEFAULT)
@router.get("/me", summary="获取当前登录用户信息")
async def get_me(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前登录用户信息（含会员状态）"""
    # TODO S5: 集成 MembershipService.get_current_membership 获取会员信息
    return success(
        data={
            "id": user.id,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "has_profile": user.kqs_rating is not None,
            "membership_tier": None,  # S5 补充
            "membership_expire_at": None,  # S5 补充
        }
    )


@limiter.limit(RateLimits.DEFAULT)
@router.post("/h5-token", summary="生成 H5 降级临时 Token")
async def generate_h5_token(
    request: Request,
    user: User = Depends(get_current_user),
):
    """生成 H5 降级临时 Token（5 分钟有效，一次性使用）"""
    data = await AuthService.generate_h5_token(user.id)
    return success(data=data)


@limiter.limit(RateLimits.H5_EXCHANGE)
@router.post("/h5-exchange", summary="H5 Token 换 JWT")
async def exchange_h5_token(body: H5ExchangeRequest, request: Request):
    """H5 Token 换 JWT（一次性使用）"""
    data = await AuthService.exchange_h5_token(body.token)
    return success(data=data.model_dump())


# --- PIPL-001：用户同意隐私政策 ---

@limiter.limit(RateLimits.CONSENT)
@router.post("/consent", summary="记录用户同意隐私政策")
async def record_consent(
    body: ConsentRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """记录用户对当前版本隐私政策的同意（PIPL 第 14 条合规）"""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent") if request.headers else None
    data = await AuthService.record_consent(
        user_id=user.id,
        consent_type=body.consent_type,
        policy_version=body.policy_version,
        ip_address=ip,
        user_agent=ua,
    )
    return success(data=data, message="同意已记录")


@limiter.limit(RateLimits.DEFAULT)
@router.get("/consent-status", summary="查询用户同意状态")
async def get_consent_status(
    request: Request,
    user: User = Depends(get_current_user),
):
    """查询当前用户是否已同意最新版隐私政策"""
    data = await AuthService.check_consent(user.id)
    return success(data=data)
