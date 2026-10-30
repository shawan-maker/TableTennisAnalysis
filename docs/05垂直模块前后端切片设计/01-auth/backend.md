# auth 模块 �?后端垂直切片设计

> **模块名称**：`auth`
> **所属目�?*：`app/api/v1/auth/`
> **定位**：管理用户认证（微信登录/手机号登录）、JWT Token 签发与刷新、H5 降级认证
> **依据**：模块详细设�?v1.2 §2.1、API 详细设计 v1.3 §2

---

## 1. 切片准备清单

- [ ] 阅读模块详细设计 §2.1（auth 模块功能规格�?- [ ] 阅读 API 契约 §2（认证模�?8 个端点）
- [ ] 阅读 `app/core/security.py`（JWT 工具函数�?- [ ] 阅读 `app/core/deps.py`（认证依赖注入）
- [ ] 确认本切片范围：8 �?API 端点 + 对应 Service 方法

### 任务清单

| # | 任务 | 文件 | 依赖 | 状�?|
|---|------|------|------|------|
| 1 | 定义 Model（复�?user 模块 User 表） | `app/models/user.py` | �?| �?|
| 2 | 定义 Schema | `app/schemas/auth.py` | #1 | �?|
| 3 | 实现 Service | `app/services/auth_service.py` | #1,#2 | �?|
| 4 | 实现 API 路由 | `app/api/v1/auth/router.py` | #3 | �?|
| 5 | 注册 Router | `app/api/v1/__init__.py` | #4 | �?|
| 6 | 编写测试 | `tests/unit/test_auth.py` | #3 | �?|
| 7 | 编写冒烟测试 | `tests/smoke/auth_smoke_test.py` | #5 | �?|

---

## 2. 测试先行

### 测试文件结构

```python
# tests/unit/test_auth.py
"""
auth 模块 �?认证流程测试�?覆盖：微信登录、手机号登录、Token 刷新、H5 降级认证、登出�?"""
import pytest
from unittest.mock import AsyncMock, patch
from app.core.exceptions import AppException

@pytest.fixture
async def db_session():
    """创建测试数据库会话�?""
    # 使用 testclient fixture
    ...

# === 1. Happy Path ===
@pytest.mark.asyncio
async def test_wechat_login_success(client, db_session):
    """微信登录成功，返�?JWT + 用户信息�?""
    with patch('app.services.auth_service.AuthService._call_wechat_code2session',
               new_callable=AsyncMock, return_value={
                   "openid": "test_openid_001",
                   "session_key": "test_session_key"
               }):
        resp = await client.post("/api/v1/auth/wechat-login", json={
            "code": "test_code",
            "nickname": "测试用户",
        })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["nickname"] == "测试用户"
    assert data["user"]["has_profile"] is False

@pytest.mark.asyncio
async def test_token_refresh_success(client, auth_user):
    """Token 刷新成功，返回新 access_token + refresh_token�?""
    resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": auth_user["refresh_token"]
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"] != auth_user["access_token"]
    assert data["refresh_token"] != auth_user["refresh_token"]

# === 2. Validation Failure ===
@pytest.mark.asyncio
async def test_wechat_login_empty_code(client):
    """code 为空时返�?400�?""
    resp = await client.post("/api/v1/auth/wechat-login", json={"code": ""})
    assert resp.status_code == 400
    assert "登录凭证不能为空" in resp.json()["message"]

@pytest.mark.asyncio
async def test_phone_login_invalid_format(client):
    """手机号格式错误返�?400�?""
    resp = await client.post("/api/v1/auth/phone-login", json={
        "phone": "123", "code": "123456"
    })
    assert resp.status_code == 400
    assert "手机号格�? in resp.json()["message"]

# === 3. Permission / Auth Failure ===
@pytest.mark.asyncio
async def test_refresh_with_blacklisted_token(client, auth_user):
    """已撤销�?refresh_token 在黑名单中，返回 401�?""
    # 先登�?    await client.post("/api/v1/auth/logout",
                      headers={"Authorization": f"Bearer {auth_user['access_token']}"})
    # 用旧 refresh_token 刷新
    resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": auth_user["refresh_token"]
    })
    assert resp.status_code == 401

# === 4. Business Rule ===
@pytest.mark.asyncio
async def test_h5_token_one_time_use(client, auth_user):
    """H5 Token 一次性使用，二次使用返回 401�?""
    # 生成 H5 Token
    resp1 = await client.post("/api/v1/auth/h5-token",
                              headers={"Authorization": f"Bearer {auth_user['access_token']}"})
    h5_token = resp1.json()["data"]["token"]
    # 第一次使用（成功�?    resp2 = await client.post("/api/v1/auth/h5-exchange", json={"token": h5_token})
    assert resp2.status_code == 200
    # 第二次使用（失败�?    resp3 = await client.post("/api/v1/auth/h5-exchange", json={"token": h5_token})
    assert resp3.status_code == 401
    assert "Token 已使�? in resp3.json()["message"]
```

> **P3 文档同步（R12 复验批次 1）**：实际测试文件已演进，与上方先行样例的差异：
> - **R13-P3 文档同步（Auth-P2-N2 已修复）**：`test_wechat_login_empty_code` / `test_phone_login_invalid_format` 样例断言 400 + 中文消息，修复后与实现一致 —— Request Schema 移除 `min_length`/`pattern` 先行约束，改由 Service 层校验返回 400 + 中文 message（wechat-login code 空「登录凭证不能为空」、phone-login/send-sms 手机号「手机号格式不正确」，常量 `PHONE_PATTERN`），对齐 API 设计 §2.1/§2.2/§2.3 错误表。测试锁定：`tests/unit/test_auth.py` `TestAuth400ChineseMessages`（3 测试）
> - h5-exchange 二次使用：样例断言消息「Token 已使用」；实现统一返回「H5 Token 已过期，请重新操作」（401 状态码一致，仅消息文案差异）
> - 实际测试分布：`tests/unit/test_auth.py`（/me、H5 Token 一次性使用 401、consent 流程、send-sms 60s 防刷 429、phone-login 验证码错误 400）；R12 补充测试位于 `tests/unit/test_supplements_p1.py` — `TestAuthRefreshLogout`（refresh 成功 + 旧 token 黑名单 401 / 非法 token 401 / access_token 不能当 refresh 用 / logout 双 token 撤销，L1337）、`TestWechatLogin`（新用户创建 / 复用不覆盖昵称 / banned 403 / pending_deletion 403，L1403）、`TestWechatLoginBanned`（L530）、`TestConsentPolicyVersionValidation`（policy_version 非法 422 且不产生同意记录，L1556）

---

## 3. Model（复�?user 模块�?
auth 模块不独立定�?Model，复�?`app/models/user.py` 中的 `User` 表。关键字段：

```python
# app/models/user.py（已有，无需修改�?class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    openid: Mapped[str | None] = mapped_column(String(128), unique=True)  # R18-P3-2: 移除冗余 index=True（unique 已隐式创建索引）
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)  # R18-P3-2
    nickname: Mapped[str] = mapped_column(String(64))  # R18-P3-1: 移除 default="球友"（§2.1/§5 未定义）
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/pending_deletion/deleted
    # ... 其他字段见 user 模块
```

### 3.1 ConsentLog Model（PIPL-001 修复）

```python
# app/models/user.py（P3 文档同步（R12 复验批次 1）：ConsentLog 实际定义于 user.py 与 User 同文件；
# 代码导入为 from app.models.user import ConsentLog，字段与索引定义同下）
from sqlalchemy import BigInteger, String, ForeignKey, Index, DateTime, Boolean, Text
from datetime import datetime

class ConsentLog(Base):
    """用户同意记录，用于 PIPL 合规审计。"""
    __tablename__ = "consent_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    consent_type: Mapped[str] = mapped_column(String(32), nullable=False)  # privacy_policy / data_processing
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        Index("idx_consent_user_type", "user_id", "consent_type"),
        Index("idx_consent_user_at", "user_id", "consent_at"),
    )

---

## 4. Schema 实现

```python
# app/schemas/auth.py
from pydantic import BaseModel, Field
from typing import Optional

# --- 请求 Schema ---
class WechatLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, description="wx.login() 返回�?code")
    nickname: Optional[str] = Field(default=None, max_length=64)
    avatar_url: Optional[str] = Field(default=None, max_length=512)

class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机�?)
    code: str = Field(..., pattern=r"^\d{6}$", description="6 位验证码")

class SendSmsRequest(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)

class H5ExchangeRequest(BaseModel):
    token: str = Field(..., min_length=1)

# --- SEC-001 修复：登出请求 ---
class LogoutRequest(BaseModel):
    """登出请求，同时携带 access_token 和 refresh_token。"""
    access_token: str = Field(..., min_length=1, description="当前 access_token")
    refresh_token: Optional[str] = Field(default=None, description="当前 refresh_token，撤销后不可再刷新")

# --- PIPL-001 修复：用户同意记录 ---
class ConsentRequest(BaseModel):
    """用户同意隐私政策请求。"""
    # P3 文档同步（R12）：实现为 Literal 枚举约束（app/schemas/auth.py，非法值 422）
    consent_type: Literal["privacy_policy", "user_agreement", "data_processing"] = Field(..., description="同意类型")
    policy_version: str = Field(..., max_length=16, description="政策版本号")

class ConsentResponse(BaseModel):
    consented: bool
    consent_at: Optional[str] = None
    policy_version: Optional[str] = None

# --- 响应 Schema ---
class UserBrief(BaseModel):
    id: int
    nickname: str
    avatar_url: Optional[str] = None
    has_profile: bool = False
    model_config = {"from_attributes": True}

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int = 7200  # 120 分钟
    user: UserBrief
    requires_consent: bool = False  # PIPL-001：是否需要用户同意当前版本隐私政策

class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int = 7200

class H5TokenResponse(BaseModel):
    token: str
    expire_at: str

class CurrentUserResponse(BaseModel):
    id: int
    nickname: str
    avatar_url: Optional[str] = None
    has_profile: bool = False
    membership_tier: Optional[str] = None
    membership_expire_at: Optional[str] = None
```

---

## 5. Service 实现

> **P3 文档同步（R12 复验批次 1）**：以下样例与实际实现（`app/services/auth_service.py`）存在 4 处 API 命名级差异，以实现为准：
> 1. 会话工厂：样例 `get_async_session()` → 实际 `async_session_factory()`（`from app.core.database import async_session_factory`）
> 2. refresh token 解码：样例 `decode_token(refresh_token)` → 实际 `decode_refresh_token(refresh_token)`（refresh 专用解码器；`refresh_token` 与 `logout` 两处均已使用，logout 处样例保留旧写法未逐一回改，见实现 auth_service.py L256/L311）
> 3. jti 生成：样例 `str(uuid.uuid4())` → 实际 `generate_jti()`（`app.core.security` 统一函数）
> 4. ConsentLog 导入：样例 `from app.models.consent_log import ConsentLog` → 实际 `from app.models.user import ConsentLog`

```python
# app/services/auth_service.py
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.exceptions import AppException
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.auth import (
    WechatLoginRequest, PhoneLoginRequest, LoginResponse,
    RefreshResponse, UserBrief,
)
import httpx

class AuthService:
    """认证业务逻辑层�?""

    ACCESS_TOKEN_EXPIRE_MINUTES = 120   # 2 小时
    REFRESH_TOKEN_EXPIRE_DAYS = 7       # 7 �?    H5_TOKEN_TTL = 300                  # 5 分钟
    SESSION_KEY_TTL = 900               # 15 分钟
    SMS_CODE_TTL = 300                  # 5 分钟

    @staticmethod
    async def _call_wechat_code2session(code: str) -> dict:
        """调用微信 code2session 接口�?""
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
            raise AppException("登录凭证无效", 400)
        if "openid" not in data:
            raise AppException("微信登录服务暂时不可�?, 502)
        return data

    @staticmethod
    async def wechat_login(req: WechatLoginRequest) -> LoginResponse:
        """微信小程序登录�?""
        # 1. 调用微信 code2session
        wx_data = await AuthService._call_wechat_code2session(req.code)
        openid = wx_data["openid"]
        session_key = wx_data.get("session_key", "")

        # 2. 查询或创建用�?        from sqlalchemy import select
        from app.core.database import get_async_session
        async with get_async_session() as db:
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
                raise AppException("您的账号已被封禁", 403)

            # 3. 存储 session_key �?Redis
            redis = await get_redis()
            await redis.setex(
                # R13-P3文档同步：键参数按 REDIS-I 键表与实现为 {openid}，原样例 {user.id} 为笔误
                f"wx:session_key:{openid}", AuthService.SESSION_KEY_TTL, session_key
            )

            # 4. 签发 JWT
            access_token = create_access_token({"sub": str(user.id), "jti": str(uuid.uuid4())})
            refresh_token = create_refresh_token({"sub": str(user.id), "jti": str(uuid.uuid4())})

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

    @staticmethod
    async def phone_login(req: PhoneLoginRequest) -> LoginResponse:
        """手机号验证码登录�?""
        redis = await get_redis()
        cached_code = await redis.get(f"sms:code:{req.phone}")
        if not cached_code or cached_code != req.code:
            raise AppException("验证码错误或已过�?, 400)

        # 查询或创建用�?        from sqlalchemy import select
        from app.core.database import get_async_session
        async with get_async_session() as db:
            result = await db.execute(select(User).where(User.phone == req.phone))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(phone=req.phone, nickname="球友")
                db.add(user)
                await db.commit()
                await db.refresh(user)
            elif user.status == "pending_deletion":
                raise AppException("您的账号正在注销中，请先撤销注销", 403)
            elif user.status == "banned":
                raise AppException("您的账号已被封禁", 403)

            access_token = create_access_token({"sub": str(user.id), "jti": str(uuid.uuid4())})
            refresh_token = create_refresh_token({"sub": str(user.id), "jti": str(uuid.uuid4())})

            # R22-P1-1: phone_login 补 requires_consent 计算（与 wechat_login L325-L327 对称）
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
                requires_consent=requires_consent,  # R22-P1-1: phone_login 补 requires_consent（与 wechat_login L339 对称）
            )

    @staticmethod
    async def send_sms(phone: str) -> dict:
        """发送短信验证码�?""
        import random
        code = f"{random.randint(0, 999999):06d}"
        redis = await get_redis()
        # 防刷限制：同一手机号 60 秒内只能发一次（key: sms:sent:{phone}，60 秒 TTL）
        last_sent = await redis.get(f"sms:sent:{phone}")
        if last_sent:
            raise AppException("验证码发送过于频繁，请 60 秒后重试", 429)
        # 存储验证码（5 分钟有效）
        await redis.setex(f"sms:code:{phone}", AuthService.SMS_CODE_TTL, code)
        await redis.setex(f"sms:sent:{phone}", 60, "1")  # 60 秒防刷标记
        # 发送短信：SMS_MOCK=true（Phase 1 默认）日志输出验证码；false 时走阿里云通道（Phase 2 接入）
        if settings.SMS_MOCK:
            import logging
            logging.getLogger(__name__).info("SMS mock mode: phone=%s code=%s", phone, code)
        else:
            await AuthService._send_aliyun_sms(phone, code)
        return {"expire_seconds": AuthService.SMS_CODE_TTL}
    @staticmethod
    async def _send_aliyun_sms(phone: str, code: str) -> None:
        """调用阿里云短信 API 发送验证码"""
        # P3 文档同步（R12）：文档原为完整 alibabacloud SDK 实现；实际实现为框架桩
        # （logging.warning 占位），真实 SDK 接入在 Phase 2；且仅在 SMS_MOCK=false 时被调用
        import logging
        logging.getLogger(__name__).warning(
            "Aliyun SMS not configured. phone=%s code=%s", phone, code
        )
        # R12-Auth-1（Phase 2 外联边界确认）：阿里云 SMS SDK 接入属 Phase 2 范围，
        # Phase 1 保持告警日志桩，接入 SDK 后取消下方注释并实现 502 错误码
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
    async def refresh_token(refresh_token: str) -> RefreshResponse:
        """刷新 access_token�?""
        # P3 文档同步（R12）：实现使用 decode_refresh_token（refresh 专用解码器）
        payload = decode_refresh_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise AppException("请重新登�?, 401)

        jti = payload.get("jti")
        user_id = payload.get("sub")
        redis = await get_redis()
        blacklisted = await redis.get(f"jwt:blacklist:{jti}")
        if blacklisted:
            raise AppException("Token 已撤销，请重新登录", 401)

        # 签发�?token
        new_access = create_access_token({"sub": user_id, "jti": str(uuid.uuid4())})
        new_refresh = create_refresh_token({"sub": user_id, "jti": str(uuid.uuid4())})

        # �?refresh_token 加入黑名�?
        await redis.setex(
            f"jwt:blacklist:{jti}",
            AuthService.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            "1"
        )
        return RefreshResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


    # --- PIPL-001 修复：用户同意记录 ---

    # R12-Auth-3: 版本号统一为 "v1.0"（与 API 设计 §2.9/§2.10 示例、前端切片 PRIVACY_POLICY_VERSION 一致）
    CURRENT_POLICY_VERSION = "v1.0"  # 隐私政策版本号

    @staticmethod
        async def check_consent(user_id: int, consent_type: Optional[str] = "privacy_policy") -> dict:
        """检查用户是否已同意当前版本隐私政策。

        R4-Auth-2/R5-Auth-4: 接受 consent_type 参数（默认 "privacy_policy"，登录流程只检查隐私政策）；
        consent_type=None 时不限类型，返回任意类型的最新同意记录。
        """
        from sqlalchemy import select
        from app.core.database import async_session_factory
        from app.models.consent_log import ConsentLog
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
                return {"consented": True, "consent_at": record.consent_at.isoformat(), "policy_version": record.policy_version}
            return {"consented": False, "consent_at": None, "policy_version": None}

    @staticmethod
    async def record_consent(
        user_id: int,
        consent_type: str,
        policy_version: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        """记录用户同意隐私政策（PIPL 第 14 条合规）。

        R5-Auth-3: upsert — 同 user_id + consent_type + policy_version 的未撤回记录
        存在则更新 consent_at，不存在才新建。
        R12-Auth-4: policy_version 合法性校验 — 仅接受当前政策版本（CURRENT_POLICY_VERSION），
        防止无效版本写入导致 check_consent 永远无法命中（requires_consent 循环）。
        """
        if policy_version != AuthService.CURRENT_POLICY_VERSION:
            raise AppException("政策版本不正确，请同意最新版隐私政策", 422, code=ERR_VALIDATION)

        from sqlalchemy import select
        from app.core.database import async_session_factory
        from app.models.consent_log import ConsentLog
        async with async_session_factory() as db:
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
            return {"consented": True, "consent_at": record.consent_at.isoformat(), "policy_version": record.policy_version}



    @staticmethod
    async def logout(user_id: int, access_token: str, refresh_token: Optional[str] = None) -> None:
        """登出：access_token + refresh_token �?jti 均加�?Redis 黑名单�?""
        redis = await get_redis()
        # 撤销 access token
        payload = decode_token(access_token)
        if payload:
            jti = payload.get("jti")
            await redis.setex(
                f"jwt:blacklist:{jti}",
                AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "1"
            )
        # 撤销 refresh token（SEC-001 修复：防�?logout �?refresh token 仍可刷新�?
        if refresh_token:
            rt_payload = decode_token(refresh_token)
            if rt_payload and rt_payload.get("type") == "refresh":
                rt_jti = rt_payload.get("jti")
                await redis.setex(
                    f"jwt:blacklist:{rt_jti}",
                    AuthService.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                    "1"
                )

    @staticmethod
    async def generate_h5_token(user_id: int) -> dict:
        """生成 H5 降级临时 Token�?""
        token = str(uuid.uuid4())
        redis = await get_redis()
        expire_at = datetime.now(timezone.utc) + timedelta(seconds=AuthService.H5_TOKEN_TTL)
        await redis.setex(f"h5:token:{token}", AuthService.H5_TOKEN_TTL, str(user_id))
        return {"token": token, "expire_at": expire_at.isoformat()}

    @staticmethod
    async def exchange_h5_token(token: str) -> RefreshResponse:
        """H5 Token �?JWT（一次性使用）�?""
        redis = await get_redis()
        user_id = await redis.get(f"h5:token:{token}")
        if not user_id:
            raise AppException("H5 Token 已过期，请重新操�?, 401)

        # 删除 Token（一次性使用）
        await redis.delete(f"h5:token:{token}")

        # 签发 JWT
        new_access = create_access_token({"sub": user_id, "jti": str(uuid.uuid4())})
        new_refresh = create_refresh_token({"sub": user_id, "jti": str(uuid.uuid4())})

        return RefreshResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
```

---

## 6. 认证依赖注入（app/core/deps.py）

> `get_current_user` 是全局认证依赖，所有业务模块通过 `from app.core.deps import get_current_user` + `Depends(get_current_user)` 注入（共 33 处）。

### 6.1 get_current_user 增强：用户状态检查

**背景**：R32 测试计划第二轮审查发现设计盲区 — pending_deletion/banned 状态用户仍可执行上传/记分/支付等业务操作。PIPL 合规要求注销冷静期内用户不可产生新数据。

**增强逻辑**：`get_current_user` 在解码 JWT + 查询 User 后，增加 `user.status` 检查：

```python
# app/core/deps.py
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """全局认证依赖：解码 JWT → 查询 User → 状态检查 → JWT 黑名单检查 → 返回 User。"""
    if credentials is None:
        raise AppException("请先登录", 401, code=ERR_UNAUTHORIZED)
    payload = decode_access_token(credentials.credentials)
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppException("用户不存在", 401, code=ERR_UNAUTHORIZED)

    # 用户状态检查（PIPL 合规：deleted/banned/pending_deletion 状态拒绝业务操作）
    # R6-Auth-1: pending_deletion 用户拒绝业务操作（注销冷静期内仅允许撤销注销端点）
    if user.status == "deleted":
        raise AppException("用户不存在", 401, code=ERR_UNAUTHORIZED)
    if user.status == "banned":
        raise AppException("您的账号已被封禁", 403, code=ERR_FORBIDDEN)
    if user.status == "pending_deletion":
        raise AppException("账号已申请注销，请撤销注销后操作", 403, code=ERR_FORBIDDEN)

    # 检查 JWT 黑名单（Redis）
    redis_client = await get_redis()
    jti = payload.get("jti")
    if jti:
        blacklisted = await redis_client.get(f"jwt:blacklist:{jti}")
        if blacklisted:
            raise AppException("登录已过期，请重新登录", 401, code=ERR_UNAUTHORIZED)

    return user


# R6-Auth-1：注销撤销专用依赖 — deleted/banned 拒绝，pending_deletion 放行
async def get_current_user_allow_pending(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """与 get_current_user 相同，但允许 pending_deletion 状态用户通过。

    注销撤销端点（/users/account/cancel-deletion）和重复注销检测端点（/users/account）
    需要此依赖以允许 pending_deletion 用户访问。
    """
    # ...（deleted/banned 拒绝逻辑与 get_current_user 相同，跳过 pending_deletion 检查）
```

**覆盖范围**：以下 33 处 `Depends(get_current_user)` 自动生效，无需逐模块修改：
- 03-video_analysis：11 处（upload-token/upload-complete/tasks/tasks-list/tasks-detail/reports/reports-list/feedback/feedbacks/annotated-video/share）
- 04-scoring：10 处（matches 全部端点）
- 09-gamification：4 处（points/checkin-calendar/checkin/badges）
- 11-payment：2 处（orders/refund）
- 01-auth 自身：5 处（logout/me/h5-token/consent/consent-status）
- 02-user：1 处（profile 等端点）

**例外**：auth 的 `wechat-login` 和 `phone-login` 不经过 `get_current_user`（它们是登录入口），其 pending_deletion/banned 检查已在 AuthService.wechat_login / phone_login 登录链路实现（403，见 §5 样例）。

---

## 7. API 路由实现

```python
# app/api/v1/auth/router.py
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.response import success
from app.core.limiter import limiter, RateLimits
from app.models.user import User
from app.schemas.auth import (
    WechatLoginRequest, PhoneLoginRequest, SendSmsRequest,
    RefreshTokenRequest, H5ExchangeRequest, LogoutRequest, ConsentRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])

# P3 文档同步（R12）：装饰器顺序约束 — @router.post 在上、@limiter.limit 紧随其下；
# 顺序颠倒时路由表注册的是未包装原函数，限流永不生效（slowapi 死代码）。
# 限流值经 app/core/limiter.py 的 RateLimits 常量统一管理；slowapi 默认按 IP（get_remote_address）限流。

@router.post("/wechat-login", summary="微信小程序登录")
@limiter.limit(RateLimits.WECHAT_LOGIN)          # 10/minute
async def wechat_login(body: WechatLoginRequest, request: Request):
    data = await AuthService.wechat_login(body)
    return success(data=data, message="登录成功")

@router.post("/phone-login", summary="手机号验证码登录")
@limiter.limit(RateLimits.PHONE_LOGIN)           # 5/minute
async def phone_login(body: PhoneLoginRequest, request: Request):
    data = await AuthService.phone_login(body)
    return success(data=data, message="登录成功")

# 端点层按 IP 限流 1/minute；同手机号 60s 防刷在 Service 层 Redis（见 §5 send_sms）

# R13-Auth-N1: phone-login 验证码尝试限制 — 5 次错误/5 分钟窗口（sms:attempts:{phone}）
# 达到上限返回 429 ERR_RATE_LIMITED（「验证码错误次数过多，请 5 分钟后再试」）；
# 验证码校验成功/过期后计数清零。常量 SMS_CODE_MAX_ATTEMPTS=5（auth_service.py）
@router.post("/send-sms", summary="发送短信验证码")
@limiter.limit(RateLimits.SEND_SMS)
async def send_sms(body: SendSmsRequest, request: Request):
    data = await AuthService.send_sms(body.phone)
    return success(data=data, message="验证码已发送")

@router.post("/refresh", summary="刷新 access_token")
@limiter.limit(RateLimits.DEFAULT)               # 100/minute
async def refresh_token(body: RefreshTokenRequest, request: Request):
    data = await AuthService.refresh_token(body.refresh_token)
    return success(data=data)

@router.post("/logout", summary="登出")
@limiter.limit(RateLimits.DEFAULT)
async def logout(
    user: User = Depends(get_current_user),
    request: Request = None,
    body: LogoutRequest | None = None,
):
    """登出：同时撤销 access_token 和 refresh_token（SEC-001 修复）。"""
    await AuthService.logout(
        user.id,
        body.access_token if body else "",
        body.refresh_token if body else None,
    )
    return success(message="登出成功")

@router.get("/me", summary="获取当前登录用户信息")
@limiter.limit(RateLimits.DEFAULT)
async def get_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    from app.services.membership_service import MembershipService
    membership = await MembershipService.get_current_membership(db, user.id)
    return success(data={
        "id": user.id,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "has_profile": user.kqs_rating is not None,
        # P3 文档同步（R12）：实现为 None 保护（无订阅时返回 null，防止 AttributeError）
        "membership_tier": membership.tier if membership else None,
        "membership_expire_at": membership.expire_at if membership else None,
    })

@router.post("/h5-token", summary="生成 H5 降级临时 Token")
@limiter.limit(RateLimits.DEFAULT)
async def generate_h5_token(user: User = Depends(get_current_user), request: Request = None):
    data = await AuthService.generate_h5_token(user.id)
    return success(data=data)

@router.post("/h5-exchange", summary="H5 Token 换 JWT")
@limiter.limit(RateLimits.H5_EXCHANGE)           # 10/minute（R19-P1-1）
async def exchange_h5_token(body: H5ExchangeRequest, request: Request):
    data = await AuthService.exchange_h5_token(body.token)
    return success(data=data)

# --- PIPL-001：用户同意隐私政策 ---
@router.post("/consent", summary="记录用户同意隐私政策")
@limiter.limit(RateLimits.CONSENT)               # 10/minute
async def record_consent(
    user: User = Depends(get_current_user),
    body: ConsentRequest = None,
    request: Request = None,
):
    """记录用户对当前版本隐私政策的同意（PIPL 第 14 条合规）。"""
    ip = request.client.host if request else None
    ua = request.headers.get("user-agent") if request else None
    data = await AuthService.record_consent(
        user_id=user.id,
        consent_type=body.consent_type,
        policy_version=body.policy_version,
        ip_address=ip,
        user_agent=ua,
    )
    return success(data=data, message="同意已记录")

@router.get("/consent-status", summary="查询用户同意状态")
@limiter.limit(RateLimits.DEFAULT)
# P3 文档同步（R12）：实际签名含 consent_type Query 参数（R4-Auth-2，API §2.10），request 为必填首位参数
async def get_consent_status(
    request: Request,
    consent_type: Optional[str] = Query(default=None, description="同意类型，如 privacy_policy"),
    user: User = Depends(get_current_user),
):
    """查询当前用户是否已同意最新版隐私政策。"""
    data = await AuthService.check_consent(user.id, consent_type)
    return success(data=data)
```

**Router 注册**（`app/api/v1/__init__.py`）：
```python
from app.api.v1.auth.router import router as auth_router
api_router.include_router(auth_router)
```

---

## 7. 冒烟测试脚本

```python
# tests/smoke/auth_smoke_test.py
"""
auth 模块冒烟测试�?用法: python -m tests.smoke.auth_smoke_test
"""
import httpx
import asyncio

BASE_URL = "http://localhost:8000/api/v1"

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 微信登录（使�?mock code�?        print("1. Testing wechat-login...")
        resp = await client.post("/auth/wechat-login", json={
            "code": "SMOKE_TEST_CODE",
            "nickname": "冒烟测试",
        })
        if resp.status_code == 200:
            tokens = resp.json()["data"]
            access_token = tokens["access_token"]
            refresh_token = tokens["refresh_token"]
            print(f"   �?Login success, user_id={tokens['user']['id']}")
        else:
            print(f"   �?Login failed (expected in smoke test without real wx code): {resp.status_code}")
            return

        headers = {"Authorization": f"Bearer {access_token}"}

        # 2. 获取当前用户
        print("2. Testing /auth/me...")
        resp = await client.get("/auth/me", headers=headers)
        assert resp.status_code == 200, f"Get me failed: {resp.text}"
        print(f"   �?Current user: {resp.json()['data']['nickname']}")

        # 3. 刷新 Token
        print("3. Testing /auth/refresh...")
        resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200, f"Refresh failed: {resp.text}"
        new_tokens = resp.json()["data"]
        print(f"   �?Token refreshed")

        # 4. H5 Token
        print("4. Testing /auth/h5-token...")
        resp = await client.post("/auth/h5-token", headers=headers)
        assert resp.status_code == 200, f"H5 token failed: {resp.text}"
        h5_token = resp.json()["data"]["token"]
        print(f"   �?H5 token generated")

        # 5. H5 Exchange
        print("5. Testing /auth/h5-exchange...")
        resp = await client.post("/auth/h5-exchange", json={"token": h5_token})
        assert resp.status_code == 200, f"H5 exchange failed: {resp.text}"
        print(f"   �?H5 token exchanged for JWT")

        # 6. 登出
        print("6. Testing /auth/logout...")
        resp = await client.post("/auth/logout", headers=headers)
        assert resp.status_code == 200, f"Logout failed: {resp.text}"
        print(f"   �?Logout success")

    print("\nauth_smoke_test: ALL PASSED �?)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/unit/test_auth.py -v`
- [ ] 冒烟测试通过：`python -m tests.smoke.auth_smoke_test`
- [ ] Model 已在 `app/models/__init__.py` 中导�?- [ ] Router 已在 `app/api/v1/__init__.py` 中注�?- [ ] Redis 连接正确（session_key / jwt blacklist / sms code / h5 token�?- [ ] 微信 code2session 调用正确（生产环境使用真�?AppID�?- [ ] 限流配置生效（wechat-login: 10/min, phone-login: 5/min, send-sms: 1/min�?- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释�?- [ ] 无废话注释、无注释掉的死代�?
---

## 反幻觉约�?
- Service 方法 **必须** 使用 `@staticmethod`�?*禁止** 创建实例
- Schema **必须** 遵循命名：`{Entity}Request`、`{Entity}Response`
- **禁止** �?API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- 微信 API 调用 **必须** 设置超时�?0s�?- session_key / H5 Token **必须** 设置 Redis TTL
- refresh_token �?jti **必须** 加入 Redis 黑名�?- ALL API 端点已添�?`@limiter.limit()` 限流装饰器，wechat-login 10/minute，phone-login 5/minute，send-sms 1/minute，h5-exchange 10/minute（R19-P1-1 修复），consent 10/minute，其余端点 100/minute
