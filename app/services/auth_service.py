"""
app/services/auth_service.py — 认证业务逻辑层

依据：切片 01-auth/backend.md §5
规范：Service 方法使用 @staticmethod，禁止创建实例
功能：微信登录/Token 刷新/登出/H5 降级/consent 链路
"""

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, ERR_BAD_REQUEST, ERR_RATE_LIMITED, ERR_THIRD_PARTY, ERR_UNAUTHORIZED, ERR_VALIDATION
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
    # R13-Auth-N1: 验证码错误尝试上限（5 分钟窗口内超过 5 次 → 429，
    # 防 6 位验证码在 TTL 窗口内被暴力枚举）
    SMS_CODE_MAX_ATTEMPTS = 5
    # R13-Auth-N2: 手机号格式（大陆手机号，service 层 400 校验用）
    PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
    CURRENT_POLICY_VERSION = "v1.0"      # 隐私政策版本号

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
        # R13-Auth-N2: code 为空校验移入 service（API §2.1 契约 400 + 中文消息，
        # 原 Schema min_length=1 先行 422 导致设计 400 分支死代码）
        if not req.code or not req.code.strip():
            raise AppException("登录凭证不能为空", 400, code=ERR_BAD_REQUEST)

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
            elif user.status == "banned":
                # R12-Auth-2: 登录入口拦截封禁用户（与 phone_login 一致）
                raise AppException("您的账号已被封禁", 403)

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

    # R4-Auth-3: send_sms 签名 phone: str 而非 req: SendSmsRequest
    @staticmethod
    async def send_sms(phone: str) -> dict:
        """发送短信验证码（5 分钟有效）"""
        import random

        # R13-Auth-N2: 手机号格式校验移入 service（API §2.3 契约 400 + 中文消息，
        # 原 Schema pattern 先行 422 导致设计 400 分支死代码）
        if not phone or not AuthService.PHONE_PATTERN.match(phone):
            raise AppException("手机号格式不正确", 400, code=ERR_BAD_REQUEST)

        redis = await get_redis()

        # 防刷限制：同一手机号 60 秒内只能发一次
        # R4-Auth-4: Redis key sms:rate:{phone} → sms:sent:{phone}（与设计一致）
        rate_key = f"sms:sent:{phone}"
        rate = await redis.get(rate_key)
        if rate:
            raise AppException("验证码发送过于频繁，请 60 秒后重试", 429)

        # 生成 6 位验证码
        code = f"{random.randint(0, 999999):06d}"

        # 存入 Redis，5 分钟有效
        code_key = f"sms:code:{phone}"
        await redis.setex(code_key, AuthService.SMS_CODE_TTL, code)

        # 设置防刷标记，60 秒
        await redis.setex(rate_key, 60, "1")

        # 发送短信
        if settings.SMS_MOCK:
            # Mock 模式：日志输出验证码（开发环境）
            import logging
            logging.getLogger(__name__).info(
                "SMS mock mode: phone=%s code=%s", phone, code
            )
        else:
            await AuthService._send_aliyun_sms(phone, code)

        return {"expire_seconds": AuthService.SMS_CODE_TTL}

    @staticmethod
    async def _send_aliyun_sms(phone: str, code: str) -> None:
        """调用阿里云短信 API 发送验证码"""
        # 阿里云 SMS API 调用（生产环境使用）
        # R12-Auth-1（Phase 2 外联边界，设计文档已确认）：阿里云 SMS SDK 接入
        # 属 Phase 2 范围 —— Phase 1 仅 SMS_MOCK=false 时打告警日志（不发送），
        # Phase 2 接入 SDK 后取消下方注释并实现 502 错误码。
        import logging
        logging.getLogger(__name__).warning(
            "Aliyun SMS not configured. phone=%s code=%s", phone, code
        )
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

        # R13-Auth-N2: 手机号格式校验移入 service（API §2.2 契约 400 + 中文消息）
        if not req.phone or not AuthService.PHONE_PATTERN.match(req.phone):
            raise AppException("手机号格式不正确", 400, code=ERR_BAD_REQUEST)

        # 验证码校验
        code_key = f"sms:code:{req.phone}"

        # R13-Auth-N1: 验证码尝试次数限制（API §2.2 契约 429 —
        # "验证码尝试次数过多，请稍后重试"）。5 分钟窗口内最多 5 次错误尝试，
        # 超限后即使验证码正确也拒绝（防 6 位验证码暴力枚举）
        attempts_key = f"sms:attempts:{req.phone}"
        attempts = int(await redis.get(attempts_key) or 0)
        if attempts >= AuthService.SMS_CODE_MAX_ATTEMPTS:
            raise AppException(
                "验证码尝试次数过多，请稍后重试", 429, code=ERR_RATE_LIMITED
            )

        stored_code = await redis.get(code_key)
        # R4-Auth-6: 合并验证码错误消息为 "验证码错误或已过期"
        if not stored_code or stored_code != req.code:
            # R13-Auth-N1: 错误尝试计数（TTL 与验证码窗口对齐，首次设置）
            new_attempts = await redis.incr(attempts_key)
            if new_attempts == 1:
                await redis.expire(attempts_key, AuthService.SMS_CODE_TTL)
            raise AppException("验证码错误或已过期", 400, code=ERR_BAD_REQUEST)

        # 验证通过，删除验证码（一次性使用）+ 清除尝试计数
        await redis.delete(code_key)
        await redis.delete(attempts_key)

        # 查询或创建用户
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.phone == req.phone))
            user = result.scalar_one_or_none()

            if user is None:
                # 新用户注册
                # R4-Auth-5: 昵称 f"球友{req.phone[-4:]}" → "球友"（避免泄漏手机号尾号）
                user = User(
                    phone=req.phone,
                    nickname="球友",
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

    # R4-Auth-2: check_consent 接受 consent_type 参数，None 时返回所有类型
    # R5-Auth-4: 默认 consent_type="privacy_policy"，登录流程只检查隐私政策同意
    @staticmethod
    async def check_consent(user_id: int, consent_type: Optional[str] = "privacy_policy") -> dict:
        """
        检查用户是否已同意当前版本隐私政策。

        默认 consent_type="privacy_policy"，登录流程检查隐私政策同意。
        consent_type=None: 不限类型，返回任意类型的最新同意记录
        consent_type 指定: 仅查询该类型的最新同意记录
        """
        async with async_session_factory() as db:
            stmt = (
                select(ConsentLog)
                .where(
                    ConsentLog.user_id == user_id,
                    ConsentLog.policy_version == AuthService.CURRENT_POLICY_VERSION,
                    ConsentLog.withdrawn_at.is_(None),
                )
                .order_by(ConsentLog.consent_at.desc())
                .limit(1)
            )
            if consent_type is not None:
                stmt = stmt.where(ConsentLog.consent_type == consent_type)
            result = await db.execute(stmt)
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
        """记录用户同意隐私政策（PIPL 第 14 条合规）

        R5-Auth-3: upsert 逻辑 — 同 user_id + consent_type + policy_version 的
        未撤回记录存在则更新 consent_at，不存在才新建。

        R12-Auth-4: policy_version 合法性校验 — 仅接受当前政策版本，
        防止无效版本写入产生 check_consent（按 CURRENT_POLICY_VERSION 匹配）
        永远无法命中的无效同意记录（用户将陷入 requires_consent 循环）。
        """
        if policy_version != AuthService.CURRENT_POLICY_VERSION:
            raise AppException("政策版本不正确，请同意最新版隐私政策", 422, code=ERR_VALIDATION)

        async with async_session_factory() as db:
            # 查询是否存在同 user_id + consent_type + policy_version 的未撤回记录
            result = await db.execute(
                select(ConsentLog).where(
                    ConsentLog.user_id == user_id,
                    ConsentLog.consent_type == consent_type,
                    ConsentLog.policy_version == policy_version,
                    ConsentLog.withdrawn_at.is_(None),
                )
            )
            record = result.scalar_one_or_none()

            if record is not None:
                # 存在则更新 consent_at 及上下文信息
                record.consent_at = datetime.now(timezone.utc)
                record.ip_address = ip_address
                record.user_agent = user_agent
            else:
                # 不存在才新建
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
