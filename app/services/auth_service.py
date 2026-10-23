"""
app/services/auth_service.py — 认证业务逻辑层

依据：切片 01-auth/backend.md §5
规范：Service 方法使用 @staticmethod，禁止创建实例
功能：微信登录/Token 刷新/登出/H5 降级/consent 链路
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, ERR_BAD_REQUEST, ERR_THIRD_PARTY, ERR_UNAUTHORIZED
from app.core.redis import get_redis
from app.core.security import create_access_token, create_refresh_token, decode_token, decode_refresh_token, generate_jti
from app.core.database import async_session_factory
from app.models.user import ConsentLog, User
from app.schemas.auth import (
    ConsentRequest,
    ConsentResponse,
    H5ExchangeRequest,
    LoginResponse,
    PhoneLoginRequest,
    RefreshResponse,
    SendSmsRequest,
    UserBrief,
    WechatLoginRequest,
)


class AuthService:
    """认证业务逻辑层"""

    ACCESS_TOKEN_EXPIRE_MINUTES = 120    # 2 小时
    REFRESH_TOKEN_EXPIRE_DAYS = 7        # 7 天
    H5_TOKEN_TTL = 300                   # 5 分钟
    SESSION_KEY_TTL = 900                # 15 分钟
    SMS_CODE_TTL = 300                   # 5 分钟
    CURRENT_POLICY_VERSION = "1.0"       # 隐私政策版本号

    # =================================================================
    # 微信登录
    # =================================================================

    @staticmethod
    async def _call_wechat_code2session(code: str) -> dict:
        """调用微信 code2session 接口"""
        url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": settings.WECHAT_APPID,
            "secret": settings.WECHAT_APP_SECRET,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10)

        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            raise AppException("登录凭证无效", 400, code=ERR_BAD_REQUEST)
        if "openid" not in data:
            raise AppException("微信登录服务暂时不可用", 502, code=ERR_THIRD_PARTY)
        return data

    @staticmethod
    async def wechat_login(req: WechatLoginRequest) -> LoginResponse:
        """微信小程序登录"""
        # 1. 调用微信 code2session
        wx_data = await AuthService._call_wechat_code2session(req.code)
        openid = wx_data["openid"]
        session_key = wx_data.get("session_key", "")

        # 2. 查询或创建用户
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.openid == openid))
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    openid=openid,
                    nickname=req.nickname or "球友",
                    avatar_url=req.avatar_url,
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
            elif user.status == "pending_deletion":
                raise AppException("您的账号正在注销中，请先撤销注销", 403)

            # 3. 存储 session_key 到 Redis
            redis = await get_redis()
            await redis.setex(
                f"wx:session_key:{openid}", AuthService.SESSION_KEY_TTL, session_key
            )

            # 4. 签发 JWT
            access_token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
            refresh_token = create_refresh_token({"sub": str(user.id), "jti": generate_jti()})

            # 5. PIPL-001：检查用户是否已同意当前版本隐私政策
            consent = await AuthService.check_consent(user.id)
            requires_consent = not consent["consented"]

            return LoginResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                user=UserBrief(
                    id=user.id,
                    nickname=user.nickname,
                    avatar_url=user.avatar_url,
                    has_profile=user.kqs_rating is not None,
                ),
                requires_consent=requires_consent,
            )

    # =================================================================
    # 手机号验证码登录
    # =================================================================

    @staticmethod
    async def send_sms(req: SendSmsRequest) -> dict:
        """发送短信验证码（5 分钟有效）"""
        import random

        redis = await get_redis()

        # 防刷限制：同一手机号 60 秒内只能发一次
        rate_key = f"sms:rate:{req.phone}"
        rate = await redis.get(rate_key)
        if rate:
            raise AppException("验证码发送过于频繁，请 60 秒后重试", 429)

        # 生成 6 位验证码
        code = f"{random.randint(0, 999999):06d}"

        # 存入 Redis，5 分钟有效
        code_key = f"sms:code:{req.phone}"
        await redis.setex(code_key, AuthService.SMS_CODE_TTL, code)

        # 设置防刷标记，60 秒
        await redis.setex(rate_key, 60, "1")

        # 发送短信
        if settings.SMS_MOCK:
            # Mock 模式：日志输出验证码（开发环境）
            import logging
            logging.getLogger(__name__).info(
                "SMS mock mode: phone=%s code=%s", req.phone, code
            )
        else:
            await AuthService._send_aliyun_sms(req.phone, code)

        return {"expire_seconds": AuthService.SMS_CODE_TTL}

    @staticmethod
    async def _send_aliyun_sms(phone: str, code: str) -> None:
        """调用阿里云短信 API 发送验证码"""
        # 阿里云 SMS API 调用（生产环境使用）
        # 当前为框架代码，实际接入时替换为阿里云 SDK 调用
        import logging
        logging.getLogger(__name__).warning(
            "Aliyun SMS not configured. phone=%s code=%s", phone, code
        )
        # TODO: 接入阿里云 SMS SDK
        # from aliyunsdkcore.client import AcsClient
        # from aliyunsdkcore.request import CommonRequest
        # client = AcsClient(settings.ALIYUN_SMS_ACCESS_KEY, settings.ALIYUN_SMS_SECRET, "cn-hangzhou")
        # request = CommonRequest()
        # request.set_method("POST")
        # request.set_domain("dysmsapi.aliyuncs.com")
        # request.set_version("2017-05-25")
        # request.set_action_name("SendSms")
        # request.add_query_param("PhoneNumbers", phone)
        # request.add_query_param("SignName", settings.ALIYUN_SMS_SIGN_NAME)
        # request.add_query_param("TemplateCode", settings.ALIYUN_SMS_TEMPLATE_CODE)
        # request.add_query_param("TemplateParam", json.dumps({"code": code}))
        # response = client.do_action_with_exception(request)
        # if response["Code"] != "OK":
        #     raise AppException("短信发送失败", 502, code=ERR_THIRD_PARTY)

    @staticmethod
    async def phone_login(req: PhoneLoginRequest) -> LoginResponse:
        """手机号验证码登录"""
        redis = await get_redis()

        # 验证码校验
        code_key = f"sms:code:{req.phone}"
        stored_code = await redis.get(code_key)
        if not stored_code:
            raise AppException("验证码已过期，请重新获取", 400, code=ERR_BAD_REQUEST)
        if stored_code != req.code:
            raise AppException("验证码错误", 400, code=ERR_BAD_REQUEST)

        # 验证通过，删除验证码（一次性使用）
        await redis.delete(code_key)

        # 查询或创建用户
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.phone == req.phone))
            user = result.scalar_one_or_none()

            if user is None:
                # 新用户注册
                user = User(
                    phone=req.phone,
                    nickname=f"球友{req.phone[-4:]}",
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
            elif user.status == "pending_deletion":
                raise AppException("您的账号正在注销中，请先撤销注销", 403)
            elif user.status == "banned":
                raise AppException("您的账号已被封禁", 403)

            # 签发 JWT
            access_token = create_access_token({"sub": str(user.id), "jti": generate_jti()})
            refresh_token = create_refresh_token({"sub": str(user.id), "jti": generate_jti()})

            # PIPL-001：检查用户是否已同意当前版本隐私政策
            consent = await AuthService.check_consent(user.id)
            requires_consent = not consent["consented"]

            return LoginResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                user=UserBrief(
                    id=user.id,
                    nickname=user.nickname,
                    avatar_url=user.avatar_url,
                    has_profile=user.kqs_rating is not None,
                ),
                requires_consent=requires_consent,
            )

    # =================================================================
    # Token 刷新
    # =================================================================

    @staticmethod
    async def refresh_token(refresh_token: str) -> RefreshResponse:
        """刷新 access_token"""
        payload = decode_refresh_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise AppException("请重新登录", 401, code=ERR_UNAUTHORIZED)

        jti = payload.get("jti")
        user_id = payload.get("sub")
        redis = await get_redis()

        # 检查黑名单
        blacklisted = await redis.get(f"jwt:blacklist:{jti}")
        if blacklisted:
            raise AppException("Token 已撤销，请重新登录", 401, code=ERR_UNAUTHORIZED)

        # 签发新 token
        new_access = create_access_token({"sub": user_id, "jti": generate_jti()})
        new_refresh = create_refresh_token({"sub": user_id, "jti": generate_jti()})

        # 旧 refresh_token 加入黑名单
        await redis.setex(
            f"jwt:blacklist:{jti}",
            AuthService.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            "1",
        )

        return RefreshResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # =================================================================
    # 登出
    # =================================================================

    @staticmethod
    async def logout(user_id: int, access_token: str, refresh_token: Optional[str] = None) -> None:
        """
        登出：access_token + refresh_token 的 jti 均加入 Redis 黑名单。
        SEC-001 修复：防止 logout 后 refresh token 仍可刷新。
        """
        redis = await get_redis()

        # 撤销 access token
        payload = decode_token(access_token)
        if payload:
            jti = payload.get("jti")
            if jti:
                await redis.setex(
                    f"jwt:blacklist:{jti}",
                    AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    "1",
                )

        # 撤销 refresh token
        if refresh_token:
            rt_payload = decode_refresh_token(refresh_token)
            if rt_payload and rt_payload.get("type") == "refresh":
                rt_jti = rt_payload.get("jti")
                if rt_jti:
                    await redis.setex(
                        f"jwt:blacklist:{rt_jti}",
                        AuthService.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                        "1",
                    )

    # =================================================================
    # H5 降级认证
    # =================================================================

    @staticmethod
    async def generate_h5_token(user_id: int) -> dict:
        """生成 H5 降级临时 Token"""
        token = str(uuid.uuid4())
        redis = await get_redis()
        expire_at = datetime.now(timezone.utc) + timedelta(seconds=AuthService.H5_TOKEN_TTL)
        await redis.setex(f"h5:token:{token}", AuthService.H5_TOKEN_TTL, str(user_id))
        return {"token": token, "expire_at": expire_at.isoformat()}

    @staticmethod
    async def exchange_h5_token(token: str) -> RefreshResponse:
        """H5 Token 换 JWT（一次性使用）"""
        redis = await get_redis()
        user_id = await redis.get(f"h5:token:{token}")
        if not user_id:
            raise AppException("H5 Token 已过期，请重新操作", 401, code=ERR_UNAUTHORIZED)

        # 删除 Token（一次性使用）
        await redis.delete(f"h5:token:{token}")

        # 签发 JWT
        new_access = create_access_token({"sub": user_id, "jti": generate_jti()})
        new_refresh = create_refresh_token({"sub": user_id, "jti": generate_jti()})

        return RefreshResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # =================================================================
    # PIPL 合规 — consent 链路
    # =================================================================

    @staticmethod
    async def check_consent(user_id: int) -> dict:
        """检查用户是否已同意当前版本隐私政策"""
        async with async_session_factory() as db:
            result = await db.execute(
                select(ConsentLog)
                .where(
                    ConsentLog.user_id == user_id,
                    ConsentLog.consent_type == "privacy_policy",
                    ConsentLog.policy_version == AuthService.CURRENT_POLICY_VERSION,
                    ConsentLog.withdrawn_at.is_(None),
                )
                .order_by(ConsentLog.consent_at.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
            if record:
                return {
                    "consented": True,
                    "consent_at": record.consent_at.isoformat(),
                    "policy_version": record.policy_version,
                }
            return {"consented": False, "consent_at": None, "policy_version": None}

    @staticmethod
    async def record_consent(
        user_id: int,
        consent_type: str,
        policy_version: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        """记录用户同意隐私政策（PIPL 第 14 条合规）"""
        async with async_session_factory() as db:
            record = ConsentLog(
                user_id=user_id,
                consent_type=consent_type,
                policy_version=policy_version,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            return {
                "consented": True,
                "consent_at": record.consent_at.isoformat(),
                "policy_version": record.policy_version,
            }
