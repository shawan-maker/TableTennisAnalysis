# 乒乓智能分析平台 — API 详细设计文档

> **版本**：v1.3
> **日期**：2026-10-12
> **依据**：系统架构设计 v2.4 第 5 节、模块详细设计 v1.1、数据库详细设计 v1.1
> **技术栈**：FastAPI + Pydantic + SQLAlchemy 2.0 async
> **说明**：本文档对架构设计 5.7 节的 API 端点清单进行细化，覆盖 Phase 1 全部端点的请求/响应契约。参考 `templates/05-api-contract.md` 格式并针对本项目技术栈适配。

---

## 1. 全局规范

### 1.1 统一响应格式

所有端点返回以下 JSON 结构：

```json
{
  "code": 200,
  "message": "success",
  "data": { },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

- 成功：`code=200`, `message="success"` 或自定义消息
- 错误：`code` 为 HTTP 状态码，`message` 为中文错误描述
- 通过 `app/core/response.py` 的 `success()` / `error()` 函数包装

### 1.2 分页格式

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 58,
    "page": 1,
    "page_size": 20,
    "items": [ ]
  }
}
```

- `page` 默认 1，最小 1
- `page_size` 默认 20，最小 1，用户端最大 50，管理端最大 100
- 通过 `app/core/pagination.py` 的 `paginate()` 函数生成

> **page_size 约束统一规范**：用户端列表端点（§2~§17）统一遵循"最小 1，最大 50"约束，超出范围由 `paginate()` 函数自动截断或返回 422 错误。本节为权威规范，所有用户端列表端点参数表统一引用；§5.2 GET /scoring/matches、§8.3 GET /training/templates 等关键端点参数表已显式重复标注以便阅读。管理端列表端点（§19）上限为 100，已在各端点参数表显式标注。

> **R18-P3-14 修复（已在 R18 落地）**：用户端列表端点 page_size 参数描述统一补齐"默认 20，最小 1，最大 50（见 §1.2）"标注，原 R18 推迟原因为"切片已正确实现"，现 API 文档与切片实现（`paginate()` 函数 `min(max(page_size, 1), 50)`）保持一致。已覆盖 §2~§17 全部 16 个用户端列表端点参数表（含 §3.7 反馈列表、§5.2 比赛列表、§8.3 训练模板等），管理端（§19）保持 100 上限。

### 1.3 认证机制

| 认证方式 | 实现 | 适用端点 |
|---------|------|---------|
| JWT Bearer Token | `Authorization: Bearer {access_token}` | 大部分端点 |
| H5 临时 Token | 一次性 Token，5 分钟过期 | H5 降级页面认证 |
| 微信支付签名 | APIv3 证书验签 | 支付回调 |
| 公开访问 | 无需认证 | 分享页、公开内容 |

### 1.4 权限标注

| 契约标注 | 含义 | 实现方式 |
|---------|------|---------|
| `公开` | 无需登录 | — |
| `登录` | 任何已登录用户 | `Depends(get_current_user)` |
| `会员` | 会员版及以上 | Service 层检查 subscription |
| `专业` | 专业版及以上 | Service 层检查 subscription |
| `教练` | 教练版 | Service 层检查 subscription |
| `微信签名` | 微信支付回调 | APIv3 证书验证 |
| `H5 Token` | H5 降级认证 | 一次性 Token 验证 |

### 1.5 限流配置

| 端点类型 | 限流 | 实现 |
|---------|------|------|
| 微信登录 | 10/min | slowapi + Redis |
| 手机号登录 | 5/min | slowapi + Redis |
| 发送短信 | 1/min | slowapi + Redis |
| H5 Token 换 JWT（`POST /auth/h5-exchange`） | 10/min | slowapi + Redis，防止 H5 token 滥用 |
| 隐私政策同意（`POST /auth/consent`） | 10/min | slowapi + Redis，防止同意记录滥用 |
| AI 分析任务创建 | 10/hour + 免费 3/天, 会员无限 | slowapi + Redis 计数器 |
| 报告分享 | 5/天 | slowapi + Redis |
| 全局 | 100 req/min | slowapi + Redis |

> **R18-P3-11 修复（已在 R18 落地）**：h5-exchange 与 consent 端点限流值补充文档化（10/min）。原 R18 推迟原因为"开发阶段补充"，现统一在 §1.5 限流配置表中显式列出，便于 slowapi 装饰器实现时引用。
>
> **R19-P1-5 + R19-P3-1 修复（2026-10-19）**：修正 R18-P3-11 原注释错误声明"§2.8 / §2.9 各端点说明中已有限流：10/min 注释"（实际未落地，仅 §1.5 全局表列出）。本轮同步在 §2.8 `POST /auth/h5-exchange`、§2.9 `POST /auth/consent` 端点描述中补充 `**限流**：10/min` 显式注释，与 §2.1-§2.3 风格统一；同步修正切片 `01-auth/backend.md` L648 h5-exchange 装饰器从 `100/minute` 改为 `10/minute`（原误用全局默认值）。本节限流表与 §2.8（限流：10/min）、§2.9（限流：10/min）端点说明保持一致。

### 1.6 API 路径前缀

所有 REST API 挂载在 `/api/v1` 下。WebSocket 端点为 `/ws`（与 REST 分离）。

### 1.7 全局通用错误码

除非端点另有"错误情况"表注明业务特定错误码，以下通用错误码适用于**所有**端点：
| HTTP | code | 条件 | 消息 |
|------|------|------|------|
| 401 | 40100 | 未携带 JWT 或 JWT 无效 | 请先登录 |
| 401 | 40101 | access_token 已过期 | 登录已过期，请刷新 Token |
| 403 | 40300 | 权限不足（非会员访问会员端点等） | 权限不足，请升级会员 |
| 404 | 40400 | 路径参数 ID 对应的资源不存在 | 资源不存在 |
| 422 | 42200 | 请求参数校验失败（类型/必填/枚举值） | 参数校验失败：{field} {detail} |
| 429 | 42900 | 触发限流 | 请求过于频繁，请稍后重试 |
| 400 | 40000 | 请求参数业务校验失败（通用，端点级特定 code 见 §1.8） | 请求参数不合法或业务校验未通过 |
| 502 | 50200 | 第三方服务不可用（微信 API 调用失败、AI 推理服务不可用等） | 第三方服务暂时不可用，请稍后重试 |
| 500 | 50000 | 服务端内部错误 | 服务暂时不可用，请稍后重试 |

> **404 错误消息规范**：404 的 `message` 字段应指明具体资源类型，格式为 `{资源名}不存在`（如"比赛不存在"、"报告不存在"），而非通用的"资源不存在"。端点级"错误情况"表中已为每个 404 场景定义了具体消息，前端据此展示差异化提示。
> 前端错误处理优先级：先检查 HTTP 401/403 做认证跳转和权限提示，再按业务 code 做差异化展示，最后兜底 500。

### 1.8 端点级业务错误码

以下错误码由具体端点的"错误情况"表引用，前端可据此做差异化提示（如引导升级、引导重试等）。业务 code 采用 `HTTP×100 + 序号` 编码，与全局通用错误码（§1.7）命名空间一致。
| code | HTTP | 条件 | 模块 |
|------|------|------|------|
| 40010 | 400 | 文件尚未上传完成（`upload-complete` 未调用） | 视频分析 |
| 40011 | 400 | 请求参数业务校验失败（枚举值/取值范围，区别于 42200 类型校验） | 通用 |
| 40310 | 403 | 无权操作他人资源（非会员访问会员端点已由全局 40300 覆盖） | 通用 |
| 40410 | 404 | 文件记录不存在 | 视频分析 |
| 40411 | 404 | 比赛不存在 | 记分牌 |
| 40412 | 404 | 分析报告不存在 | 视频分析 |
| 40413 | 404 | 比赛记录不存在或不属于当前用户 | 比赛记录 |
| 40414 | 404 | 分享 Token 无效或已过期 | 分享 |
| 40910 | 409 | 比赛不在进行中（状态机冲突：`setup`/`finished`/`abandoned`） | 记分牌 |
| 40911 | 409 | 比赛记录已关联记分牌，不可直接编辑 | 比赛记录 |
| 42210 | 422 | 比分不符合赛制规则 | 比赛记录 |
| 42910 | 429 | 免费分析额度耗尽（Redis `quota:analysis:{user_id}:{date}` ≥ 3） | 视频分析 |

> 端点错误情况表中标注的 HTTP 状态码对应上述业务 code；前端按 code 做差异化交互（如 42910 → 引导升级会员弹窗，40910 → 提示"比赛已结束"，40414 → 跳转过期页面）。

---

## 2. 认证模块 (`/auth`)

### 2.1 POST /auth/wechat-login

**描述**：微信小程序登录（code → JWT）

**权限**：公开

**限流**：10/min

#### Request Body

```json
{
  "code": "0a3b9c2e-xxxx-xxxx-xxxx",
  "nickname": "Eric",
  "avatar_url": "https://thirdwx.qlogo.cn/..."
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| code | string | Y | wx.login() 返回的 code |
| nickname | string | N | 用户昵称（首次登录时） |
| avatar_url | string | N | 用户头像 URL |

#### Response Body

```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "access_token": "[REDACTED:sha256:4ce9353e2d8d]",
    "refresh_token": "[REDACTED]",
    "expires_in": 7200,
    "requires_consent": false,
    "user": {
      "id": 123,
      "nickname": "Eric",
      "avatar_url": "https://...",
      "has_profile": false
    }
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

> **P2 回写**：新增 `requires_consent` 字段（boolean），表示用户是否需要签署隐私政策同意书。`true` 表示当前用户尚未签署最新版隐私政策（consent_log 表无对应 policy_version 记录），前端应跳转同意页面；`false` 表示已签署或无需签署。

#### 业务规则
1. 调用微信 code2session 获取 openid + session_key
2. 查询 user 表，不存在则创建（openid, nickname, avatar_url）
3. session_key 存入 Redis（TTL 15min），用于后续微信 API 调用
4. 签发 JWT（access_token 120min + refresh_token 7d）
5. 检查 consent_log 表，判断用户是否已签署当前版本隐私政策，设置 `requires_consent`
6. 账号状态拦截（签发 JWT 前校验）：status=banned → 403「您的账号已被封禁」；status=pending_deletion → 403「您的账号正在注销中，请先撤销注销」

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | code 为空 | 登录凭证不能为空 |
| 502 | 微信 API 调用失败 | 微信登录服务暂时不可用 |
| 400 | code 无效 | 登录凭证无效 |
| 403 | 账号状态为 banned | 您的账号已被封禁 |
| 403 | 账号状态为 pending_deletion | 您的账号正在注销中，请先撤销注销 |

### 2.2 POST /auth/phone-login

**描述**：手机号验证码登录（App 端）

**权限**：公开

**限流**：5/min

#### Request Body

```json
{
  "phone": "13800138888",
  "code": "123456"
}
```

#### Response Body

同 2.1 微信登录响应格式（`user.has_profile` 表示是否已填写档案，`requires_consent` 表示是否需要签署隐私政策）

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 手机号格式错误 | 手机号格式不正确 |
| 400 | 验证码错误或已过期 | 验证码错误或已过期 |
| 429 | 验证码尝试次数过多 | 验证码尝试次数过多，请稍后重试 |
| 403 | 账号状态为 banned | 您的账号已被封禁 |
| 403 | 账号状态为 pending_deletion | 您的账号正在注销中，请先撤销注销 |

### 2.3 POST /auth/send-sms

**描述**：发送短信验证码

**权限**：公开

**限流**：1/min

#### Request Body

```json
{
  "phone": "13800138888"
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "验证码已发送",
  "data": {
    "expire_seconds": 300
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 6 位随机数字验证码，存入 Redis（key: `sms:code:{phone}`，TTL 5min）

2. 发送短信：`SMS_MOCK=true`（Phase 1 默认）时模拟通道（记录日志不实际发送，`_send_aliyun_sms` 为 TODO 桩，真实 SDK 在 Phase 2 接入）；`SMS_MOCK=false` 时调用阿里云短信服务发送

3. 服务层同手机号 60 秒防刷（Redis 发送间隔标记，与 slowapi 端点限流相互独立，见 §1.5）

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 手机号格式错误 | 手机号格式不正确 |
| 429 | 60 秒内同手机号已发送过 | 验证码发送过于频繁，请 60 秒后重试 |

### 2.4 POST /auth/refresh

**描述**：刷新 access_token

**权限**：refresh_token

#### Request Body

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiJ9..."
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiJ9...",
    "expires_in": 7200
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 验证 refresh_token 有效性 + jti 不在 Redis 黑名单

2. 签发新 access_token + 新 refresh_token

3. 旧 refresh_token 的 jti 加入 Redis 黑名单

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 401 | refresh_token 无效或已过期 | 请重新登录 |
| 401 | refresh_token 的 jti 在黑名单中 | Token 已撤销，请重新登录 |

### 2.5 POST /auth/logout

**描述**：登出（撤销 token）
**权限**：登录

#### Request Body

> **P2 回写**：新增 LogoutRequest 请求体，支持客户端主动传递需撤销的 token，服务端不再依赖请求头解析。

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| access_token | string | Y | 当前 access_token，加入 Redis 黑名单 |
| refresh_token | string | N | refresh_token，如有则一并撤销 |

#### Response Body

```json
{
  "code": 200,
  "message": "登出成功",
  "data": null,
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 2.6 GET /auth/me

**描述**：获取当前登录用户信息

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 123,
    "nickname": "Eric",
    "avatar_url": "https://...",
    "has_profile": true,
    "membership_tier": "member",
    "membership_expire_at": "2026-11-10T12:00:00Z"
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 2.7 POST /auth/h5-token

**描述**：生成 H5 降级临时 Token（5 分钟过期，一次性使用）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "token": "a1b2c3d4-e5f6",
    "expire_at": "2026-10-10T12:05:00Z"
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 2.8 POST /auth/h5-exchange

**描述**：H5 Token 换 JWT（web-view 降级页认证）

**权限**：H5 Token（一次性使用）

**限流**：10/min（见 §1.5，R19-P3-1 补充）

#### Request Body

```json
{
  "token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

#### Response Body

同 2.4 刷新 token 响应格式

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 401 | Token 过期/不存在 | H5 Token 已过期，请重新操作 |
| 401 | Token 已被使用 | Token 已使用 |

### 2.9 POST /auth/consent

> **P2 回写**：新增用户隐私政策同意端点。用户登录后若 `requires_consent=true`，前端展示隐私政策页面并收集用户同意。
**描述**：提交隐私政策同意
**权限**：登录
**限流**：10/min（见 §1.5，R19-P3-1 补充）

#### Request Body

```json
{
  "consent_type": "privacy_policy",
  "policy_version": "v1.0"
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| consent_type | string | Y | 同意类型，枚举：`privacy_policy` / `user_agreement` / `data_processing` |
| policy_version | string | Y | 政策版本号，如 `v1.0` |

#### Response Body

```json
{
  "code": 200,
  "message": "同意已记录",
  "data": {
    "consented": true,
    "consent_at": "2026-10-10T12:00:00Z",
    "policy_version": "v1.0"
  },
  "timestamp": "..."
}
```

#### 业务规则
1. 记录到 consent_log 表（user_id, consent_type, policy_version, consent_at, ip_address, user_agent）
2. 同一 policy_version 重复同意时更新 consent_at 时间戳，不新增记录
3. 同意后后续登录 `requires_consent` 返回 false
4. policy_version 版本校验：必须等于服务端 `CURRENT_POLICY_VERSION`（当前 `v1.0`），否则拒绝写入（防止无效版本写入导致 consent-status 误判）

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | consent_type 不在枚举值内 | 同意类型不正确 |
| 422 | policy_version 非当前版本（含空值，`CURRENT_POLICY_VERSION=v1.0`） | 政策版本不正确，请同意最新版隐私政策 |

### 2.10 GET /auth/consent-status

> **P2 回写**：新增同意状态查询端点，供前端检查用户是否已签署最新版隐私政策。
**描述**：查询用户同意状态
**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| consent_type | query | string | N | 同意类型，不传则返回所有类型状态 |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "consented": true,
    "consent_at": "2026-10-10T12:00:00Z",
    "policy_version": "v1.0"
  },
  "timestamp": "..."
}
```

#### 业务规则
1. 查询 consent_log 表当前用户最新一条记录
2. 若用户未签署过任何版本，`consented=false`，`consent_at=null`，`policy_version=null`

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

## 3. 用户模块 (`/users`)

### 3.1 GET /users/profile

**描述**：获取个人档案

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 123,
    "nickname": "Eric",
    "avatar_url": "https://...",
    "profile": {
      "kqs_rating": 1550,
      "kqs_username": "eric_tt",
      "playing_style": "loop",
      "self_assessed_level": null,
      "equipment_config": {
        "blade": {"brand": "蝴蝶", "model": "Viscaria"},
        "rubber_fh": {"brand": "红双喜", "model": "狂飙3"},
        "rubber_bh": {"brand": "蝴蝶", "model": "T05"}
      },
      "profile_completeness": 80
    }
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 3.2 PATCH /users/profile

**描述**：更新个人档案（打法/装备/自评水平），仅更新传入字段

**权限**：登录

#### Request Body

```json
{
  "playing_style": "loop",
  "self_assessed_level": "intermediate",
  "equipment_config": {
    "blade": {"brand": "蝴蝶", "model": "Viscaria"},
    "rubber_fh": {"brand": "红双喜", "model": "狂飙3", "hardness": "39°"},
    "rubber_bh": {"brand": "蝴蝶", "model": "T05"},
    "shoes": "美津浓 Wave-Up"
  }
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "档案已更新",
  "data": {
    "id": 123,
    "profile_completeness": 80,
    "updated_fields": ["playing_style", "self_assessed_level", "equipment_config"]
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 更新后重新计算 profile_completeness

2. 仅更新传入的字段（PATCH 语义），未传入字段保持不变

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | playing_style 值不在枚举中 | 打法类型不合法 |
| 422 | equipment_config 格式错误 | 装备配置格式不正确 |

### 3.3 PATCH /users/rating

**描述**：更新开球网积分（手动填写/ID），仅更新积分相关字段

**权限**：登录

#### Request Body

```json
{
  "rating": 1550,
  "kqs_username": "eric_tt",
  "source": "manual"
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "积分已更新",
  "data": {
    "id": 123,
    "old_rating": 1500,
    "new_rating": 1550,
    "history_id": 6
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 读取当前 kqs_rating

2. 创建 rating_history 记录（旧积分 + source）

3. 更新 user.kqs_rating

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 积分超出范围 | 积分值不在合理范围内（500-3000） |

### 3.4 GET /users/rating-history

**描述**：积分历史记录

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| page | query | int | N | 页码，默认 1 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 5,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 1,
        "rating": 1550,
        "source": "manual",
        "recorded_at": "2026-10-10T12:00:00Z"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。
> **P3-7 确认**：响应 items 中每条记录包含 `recorded_at`（时间戳）和 `rating`（积分值），可直接用于前端折线图 x/y 轴数据绑定。`source` 字段标识积分来源（manual/kqs_sync），可用于区分颜色标记。

### 3.5 GET /users/big-data

**描述**：乒乓大数据（趣味统计）

**权限**：登录

**缓存**：24h

> **响应结构说明**：data 字段包含 8 项趣味统计卡片数据，前端按卡片逐项渲染：
> - `highest_win_rating`：战胜的最高积分对手（数字，无对手显示 null）
> - `win_streak`：当前连胜场次数（数字，0 表示无连胜）
> - `match_cities`：比赛覆盖城市数（数字）
> - `total_opponents`：累计交手人数（数字）
> - `indirect_wins`：间接战胜的知名球员列表（数组，空则 `[]`）
> - `total_matches`：累计比赛场次（数字）
> - `win_rate`：总胜率（浮点 0-1）
> - `favorite_shot`：最常用技术动作（字符串，如 `forehand_loop`）

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "highest_win_rating": 1780,
    "win_streak": 8,
    "match_cities": 5,
    "total_opponents": 32,
    "indirect_wins": ["马龙", "孙颖莎"],
    "total_matches": 45,
    "win_rate": 0.62,
    "favorite_shot": "forehand_loop"
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 3.6 DELETE /users/account

**描述**：用户注销（72h 冷静期，到期后永久删除个人信息）

**权限**：登录

#### Request Body

```json
{
  "reason": "不再使用",
  "confirmation": "DELETE_ACCOUNT_CONFIRM"
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "注销申请已提交，72 小时内可撤销",
  "data": {
    "scheduled_deletion_at": "2026-10-13T12:00:00Z",
    "can_cancel_before": "2026-10-13T12:00:00Z"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 用户提交注销 → `user.status = 'pending_deletion'`，设置 `scheduled_deletion_at = NOW() + 72h`

2. 72h 内用户可登录撤销注销（`POST /users/account/cancel-deletion`）

3. 72h 后 Celery 定时任务执行永久删除：
   - `user.nickname = '已注销用户'`，`user.avatar_url = null`，`user.phone = null`，`user.openid = null`
   - `user.status = 'deleted'`
   - 关联视频 `file_record.status = 'deleted'`（24h 后 OSS 物理删除）
   - 分析报告 `analysis_report.user_id` 保留但 `is_anonymized = true`（匿名归档，用于模型训练数据）
   - 比赛记录 `match_record.user_id` 保留（对手的比赛数据不受影响）
   - 订阅 `subscription.status = 'cancelled'`
4. 注销不可恢复（72h 后）

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | confirmation != "DELETE_ACCOUNT_CONFIRM" | 请输入确认文字以完成注销 |
| 409 | 已有待执行的注销申请 | 您已提交注销申请 |

### 3.7 GET /video-analysis/reports/{report_id}/feedbacks

**描述**：查询用户对分析报告的反馈历史

**权限**：登录

> **模块归属说明（R18-P3-13 已修复）**：此端点路径以 `/video-analysis/` 开头，路由注册在 video_analysis 模块下（`app/api/v1/video_analysis/router.py`），逻辑上归属视频分析模块。在用户模块 §3 中列出是因为其数据与用户档案关联（用户视角的反馈历史）。原 R18 推迟原因为"已知设计决策"，现显式标注归类理由：(1) 路由归属——video_analysis 模块；(2) 列出位置——用户模块 §3 反馈历史视角；(3) 切片实现——`03-video_analysis/backend.md` 中 `feedback_router` 挂载于 `/video-analysis/reports/{report_id}/feedbacks` 路径，与 §3.7 路径一致；(4) 数据归属——`feedback_record` 表由 video_analysis 模块定义（详见 DB §2.13）。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| page | query | int | N | 页码，默认 1 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 3,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 1,
        "report_id": 1001,
        "report_title": "2026-10-10 训练分析",
        "is_correct": false,
        "comment": "落点分析不太准确",
        "status": "reviewed",
        "created_at": "2026-10-10T14:00:00Z"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 3.8 POST /users/export-data

**描述**：发起个人数据导出（PIPL 数据可携带权）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "导出任务已创建，完成后将通过通知告知您",
  "data": {
    "task_id": "export_20261010_001",
    "status": "pending"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 异步处理：创建导出任务后立即返回 task_id

2. Celery 异步聚合用户档案、比赛记录、分析报告摘要、训练方案、积分记录（任务 `app.tasks.user.export_user_data`）

3. Phase 1 简化实现：任务内直接构造 `download_url`（`https://oss.pingpongai.com/exports/{task_id}.zip`）并置 `completed`；真实数据打包 + OSS 上传（7 天有效）在 S6+ 接入

4. 完成后 WS 推送 `export_completed` 事件通知（推送失败不影响任务状态）

5. 每用户每月限 1 次导出：Redis Key `export:count:{user_id}:{YYYYMM}` 原子 INCR（首次计数设置 TTL 至月末），超过 1 次返回 429

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 429 | 本月已导出过 | 本月已导出过，请下月再试 |

### 3.9 GET /users/export-data/{task_id}

**描述**：查询导出状态 + 下载链接

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "task_id": "export_20261010_001",
    "status": "completed",
    "download_url": "https://cdn.pingpongai.com/exports/user_123_20261010.json",
    "expire_at": "2026-10-17T12:00:00Z",
    "file_size": 256000
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 任务不存在或不属于当前用户（跨用户访问按 404 处理，code 40400，不泄露存在性） | 导出任务不存在 |
| 409 | 任务仍在处理中（status 为 pending/processing） | 导出任务处理中，请稍后查询 |

> `status=completed` 时返回 200 及 `download_url`；`status=failed` 同样返回 200（前端按 status 展示失败态）。

### 3.10 POST /users/account/cancel-deletion

> **P1 回写**：新增撤销注销端点。§3.6 DELETE /users/account 业务规则第 2 条引用了此端点，但 API 设计中缺失定义。
**描述**：撤销用户注销申请（72h 冷静期内）
**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "注销已撤销，账号恢复正常",
  "data": {
    "status": "active",
    "cancelled_at": "2026-10-11T10:00:00Z"
  },
  "timestamp": "..."
}
```

#### 业务规则
1. 校验当前 `user.status == 'pending_deletion'`，否则返回 409
2. 恢复 `user.status = 'active'`，清除 `scheduled_deletion_at`
3. 记录撤销操作审计日志

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 用户未处于注销待执行状态 | 无待执行的注销申请 |

### 3.11 GET /users/quota

> **P3 文档同步（源自 R6-User-2，R12 归档为文档不同步类）**：本端点在 R6 审查时已由代码实现（`app/api/v1/users/router.py`）但未记录于 API 设计文档，属"代码实现先行、文档滞后"。本节按当前实现补齐契约。

**描述**：获取当前用户的免费视频分析额度状态

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "daily_limit": 3,
    "used_today": 1,
    "remaining": 2,
    "reset_at": "2026-10-11T00:00:00+08:00"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 读取 Redis Key `quota:analysis:{user_id}:{date}`（`date` 为 Asia/Shanghai CST 当日日期），统计当日已用免费分析次数
2. `daily_limit`：免费用户每日免费分析次数（3 次）
3. `reset_at`：额度重置时间，为次日 00:00（CST，Asia/Shanghai 时区）

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

## 4. 视频分析模块 (`/video-analysis`)

> **任务 ID 双字段设计说明**：视频分析任务的 API 响应同时返回两个字段：
> - `task_id`（`int`）：数据库自增主键，用于内部关联和数据库查询。
> - `task_uuid`（`str`，格式如 `"task_a1b2c3d4-e5f6"`）：外部 UUID，用于对外暴露（分享链接、CDN 路径、WebSocket 推送等），避免暴露内部自增 ID。
> 前端在引用任务时应使用 `task_uuid`，在需要精确查询时使用 `task_id`。

### 4.1 POST /video-analysis/upload-token

**描述**：获取 OSS STS 直传凭证 + 对象 Key

**权限**：登录

#### Request Body

```json
{
  "filename": "training_video.mp4",
  "file_size": 104857600
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "file_id": 1001,
    "oss_key": "videos/raw/123/20261010/a1b2c3d4.mp4",
    "sts_credentials": {
      "access_key_id": "STS.xxx",
      "access_key_secret": "xxx",
      "security_token": "xxx",
      "expiration": "2026-10-10T12:15:00Z"
    },
    "upload_url": "https://pingpong-ai-prod.oss-cn-beijing.aliyuncs.com",
    "expire_at": "2026-10-10T12:15:00Z"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 校验文件类型（mp4/mov）+ 大小（1MB ≤ file_size ≤ 500MB）

2. 生成 OSS Key：`videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4`

3. 请求 STS Token（PutObject 权限，15min 过期）

4. 创建 file_record（status=uploading）

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 文件类型不支持 | 仅支持 MP4/MOV 格式 |
| 400 | 文件过大 | 视频文件不能超过 500MB |
| 422 | 文件过小 | 视频文件不能小于 1MB |

### 4.2 POST /video-analysis/upload-complete

**描述**：上传完成确认（后端 HEAD Object 校验）

**权限**：登录

#### Request Body

```json
{
  "file_id": 1001
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "file_id": 1001,
    "ready": true,
    "actual_size": 104857600
  },
  "timestamp": "..."
}
```

#### 业务规则

1. HEAD Object 确认文件存在 + Content-Length 匹配

2. ffprobe 检查视频时长：5s ≤ duration ≤ 600s（PIPL 最小必要原则 + R32 测试审查修复）

3. 更新 file_record（status=uploaded, oss_etag, actual_size）— R12-VA-6 同步：duration_sec 不入 file_record（DB 设计 §2.4 无此列），在响应中返回，create_task 时写入 video_task.duration_sec（ai_pipeline 读取源）

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | OSS 文件不存在 | 未检测到上传的文件，请重新上传 |
| 400 | 文件大小不匹配 | 上传文件大小与声明不符 |
| 422 | 视频过短 | 视频时长不足5秒，无法进行分析 |
| 422 | 视频过长 | 视频时长超过10分钟限制 |

### 4.3 POST /video-analysis/tasks

**描述**：创建分析任务

**权限**：登录

**限流**：免费 3/天，会员无限

#### Request Body

```json
{
  "file_id": 1001,
  "oss_key": "videos/raw/123/20261010/a1b2c3d4.mp4"
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "任务已创建",
  "data": {
    "task_id": 1001,
    "task_uuid": "task_a1b2c3d4-e5f6",
    "status": "queued",
    "estimated_wait_minutes": 5
  },
  "timestamp": "..."
}
```

> **estimated_wait_minutes 说明**：该字段为基于当前队列深度的估算值（非精确等待时间），仅供前端展示排队参考。实际等待时间受 GPU 资源占用、视频时长、前序任务重试等因素影响。

#### 业务规则

1. 检查会员状态：会员 → 直接入队；免费 → Redis INCR `quota:analysis:{user_id}:{date}`，超 3 → DECR 回退 → 429

2. 创建 VideoTask（status=queued）

3. 入队 Celery 分析任务

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 429 | 免费额度用完 | 今日免费分析次数已用完，升级会员可无限分析 |
| 404 | 文件不存在 | 文件记录不存在 |
| 400 | 文件未上传完成 | 文件尚未上传完成 |

### 4.4 GET /video-analysis/tasks

**描述**：任务列表（分页）

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| status | query | string | N | 状态过滤 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 15,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "task_id": 1001,
        "task_uuid": "task_a1b2c3d4-e5f6",
        "status": "completed",
        "created_at": "2026-10-10T12:00:00Z",
        "report_id": 1,
        "cover_image_url": "https://cdn.pingpongai.com/images/covers/task_a1b2c3d4-e5f6/cover.jpg"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 4.5 GET /video-analysis/tasks/{task_id}

**描述**：任务详情 + 进度

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "task_id": 1001,
    "task_uuid": "task_a1b2c3d4-e5f6",
    "status": "processing",
    "current_step": 5,
    "total_steps": 10,
    "step_name": "球体追踪",
    "progress": 0.5,
    "estimated_remaining_seconds": 120,
    "created_at": "2026-10-10T12:00:00Z",
    "report_id": null
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 任务不存在或不属于当前用户 | 任务不存在 |

### 4.6 GET /video-analysis/reports/{report_id}

**描述**：分析报告详情

**权限**：登录

> **字段说明**：`task_id` 为任务整数主键，`task_uuid` 为任务唯一标识（字符串，VARCHAR(64)），两者并存。前端引用任务时使用 `task_uuid`，列表/详情展示中使用 `task_id`。

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "task_id": 1001,
    "task_uuid": "task_a1b2c3d4-e5f6",
    "created_at": "2026-10-10T12:05:00Z",
    "is_llm_generated": true,
    "result_data": {
      "video_info": {"duration_sec": 180, "fps": 30, "resolution": "1920x1080"},
      "rally_analysis": {"total_rallies": 23, "avg_rally_length": 5.2, "max_rally_length": 18},
      "landing_points": {
        "nine_grid": [[2,5,3],[4,8,6],[1,3,2]],
        "distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07}
      },
      "technique_stats": {"forehand_drive": 45, "backhand_drive": 18, "forehand_loop": 12, "serve": 23},
      "ball_speed": {"avg_speed_mps": 18.5, "max_speed_mps": 25.3, "speed_range": [15.2, 22.1]},
      "score_analysis": {"final_score": "11:8", "key_points": [...]}
    },
    "report_text": {
      "summary": "本局正手使用率 68%，落点偏反手区域...",
      "issues": ["反手使用率偏低(25%)", "落点变化不足"],
      "suggestions": ["增加反手拉球练习", "提升落点控制能力"]
    },
    "annotated_video_url": "https://cdn.pingpongai.com/videos/annotated/task_xxx/annotated.mp4",
    "cover_image_url": "https://cdn.pingpongai.com/images/covers/task_xxx/cover.jpg",
    "report_images": {
      "heatmap": "https://cdn.pingpongai.com/images/reports/task_xxx/heatmap.png",
      "technique_chart": "https://cdn.pingpongai.com/images/reports/task_xxx/technique.png"
    },
    "is_readonly": false
  },
  "timestamp": "..."
}
```

> **is_readonly 字段说明**（R15-P3-3 修复）：布尔值，表示当前用户是否处于降级只读状态。当用户会员到期降级后，查看历史分析报告时 `is_readonly=true`，前端据此隐藏交互入口（如反馈、分享按钮）。正常状态下为 `false`。

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 报告不存在或不属于当前用户 | 报告不存在 |

### 4.7 GET /video-analysis/reports

**描述**：报告列表（分页）

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 8,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 1,
        "task_id": 12345,
        "created_at": "2026-10-10T12:05:00Z",
        "is_llm_generated": true,
        "cover_image_url": "https://cdn.pingpongai.com/images/covers/task_xxx/cover.jpg",
        "report_summary": "本局正手使用率 68%，落点偏反手区域..."
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 4.8 POST /video-analysis/reports/{report_id}/feedback

**描述**：提交反馈（对/不对标记）

**权限**：登录

#### Request Body

```json
{
  "is_correct": false,
  "comment": "落点分析不太准确，实际偏正手多一些"
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "反馈已提交",
  "data": {
    "feedback_id": 1,
    "is_correct": false,
    "data_flywheel_action": "manual_review"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 每用户每报告一条反馈（可更新覆盖）

2. is_correct=true → 视频标记为标注候选（数据飞轮）

3. is_correct=false → 进入人工审核队列

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 报告不存在或不属于当前用户 | 报告不存在 |
| 422 | is_correct 字段缺失 | 请选择反馈结果 |

### 4.9 GET /video-analysis/reports/{report_id}/annotated-video

**描述**：标注视频 CDN URL

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "url": "https://cdn.pingpongai.com/videos/annotated/task_xxx/annotated.mp4",
    "quality_options": ["1080p", "720p", "480p"],
    "duration_sec": 180
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 报告不存在或不属于当前用户 | 报告不存在 |

### 4.10 POST /video-analysis/reports/{report_id}/share

**描述**：生成分享 Token + 卡片图

**权限**：登录

**限流**：5/天

#### Response Body

```json
{
  "code": 200,
  "message": "分享链接已生成",
  "data": {
    "share_url": "https://api.pingpongai.com/share/a1b2c3d4-e5f6",
    "card_image_url": "https://cdn.pingpongai.com/images/share-cards/1/card.jpg",
    "expire_at": "2026-10-17T12:00:00Z"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 报告不存在或不属于当前用户 | 报告不存在 |
| 429 | 超过每日分享限制（5 次/天） | 今日分享次数已用完 |

### 4.11 GET /share/{share_token}

**描述**：分享报告摘要页（只读，7 天有效）

**权限**：公开

#### Response Body

返回 HTML 渲染页面（非 JSON API），包含：
- 视频封面图 + 标注视频
- 技术统计环形图
- 落点热图
- 报告文字摘要（summary + top 2 issues）
- 球速数据（范围值）
- 不含训练建议/历史趋势/用户个人信息

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 分享 Token 不存在 | 分享不存在或已过期 |

---

## 5. 记分牌模块 (`/scoring`)

### 5.1 POST /scoring/matches

**描述**：创建比赛（赛制/对手/类型）

**权限**：登录

#### Request Body

```json
{
  "opponent_name": "张某",
  "opponent_rating": 1480,
  "format": "bo5",
  "match_type": "friendly",
  "target_score": 11
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "比赛已创建",
  "data": {
    "match_id": 2001,
    "status": "setup",
    "current_server": "user"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | format 值不在枚举中 | 赛制不合法 |
| 422 | target_score 不在合理范围 | 目标分不合法 |

### 5.2 GET /scoring/matches

**描述**：比赛列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| status | query | string | N | 状态过滤 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 12,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 2001,
        "opponent_name": "张某",
        "format": "bo5",
        "match_type": "friendly",
        "status": "finished",
        "current_score_user": 3,
        "current_score_opp": 1,
        "is_win": true,
        "created_at": "2026-10-10T14:00:00Z"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 5.3 GET /scoring/matches/{match_id}

**描述**：比赛详情

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 2001,
    "opponent_name": "张某",
    "opponent_rating": 1480,
    "format": "bo5",
    "match_type": "friendly",
    "status": "in_progress",
    "current_score_user": 8,
    "current_score_opp": 5,
    "current_score": "8:5",
    "current_server": "user",
    "current_game": 1,
    "score_sequence": [
      {"sequence": 1, "scorer": "user", "score_method": "serve_point", "technique_action": "forehand_drive"},
      {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"}
    ],
    "created_at": "2026-10-10T14:00:00Z",
    "finished_at": null
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 比赛不存在或不属于当前用户 | 比赛不存在 |

### 5.4 POST /scoring/matches/{match_id}/score

**描述**：记分（得分方 + 得分方式）

**权限**：登录

#### Request Body

```json
{
  "scorer": "user",
  "score_method": "rally_point",
  "technique_action": "forehand_loop"
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "sequence": 13,
    "score": "8:5",
    "current_server": "user",
    "game_number": 1,
    "is_key_point": false,
    "match_status": "in_progress"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. Redis INCR `match:{match_id}:seq` 获取全局序号

2. 写入 score_record

3. 更新 match current_score + current_server（自动轮换发球）

4. WS push `score_update` 到 `ws:match:{match_id}` 房间

5. 如果达到赛制要求 → 自动触发 finish

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 比赛不在进行中 | 比赛未在进行中 |
| 404 | 比赛不存在 | 比赛不存在 |

### 5.5 POST /scoring/matches/{match_id}/undo

**描述**：撤销最近一球

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "sequence": 12,
    "score": "7:5",
    "action": "undo"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 比分已被其他设备更新 | 比分已更新，请确认后撤销 |
| 400 | 没有可撤销的记录 | 没有可撤销的记录 |

### 5.6 POST /scoring/matches/{match_id}/finish

**描述**：结束比赛 → 生成统计

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "比赛已结束",
  "data": {
    "match_id": 2001,
    "final_score": "3:1",
    "is_win": true,
    "statistic_id": 3001
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 比赛不在进行中 | 比赛未在进行中 |
| 404 | 比赛不存在 | 比赛不存在 |

### 5.7 GET /scoring/matches/{match_id}/statistics

**描述**：比赛统计

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "match_id": 2001,
    "stats_data": {
      "score_distribution": {"serve_point": 15, "rally_point": 20, "opponent_error": 8},
      "key_points": [{"seq": 20, "score": "10:10", "winner": "user", "method": "rally_point"}],
      "technique_breakdown": {"forehand_drive": 25, "backhand_drive": 10, "forehand_loop": 8}
    }
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 比赛不存在或不属于当前用户 | 比赛不存在 |
| 400 | 比赛尚未结束，无统计数据 | 比赛尚未结束 |

### 5.8 POST /scoring/matches/{match_id}/start

**描述**：开始比赛（状态机转换：setup → in_progress）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "比赛已开始",
  "data": {
    "match_id": 2001,
    "status": "in_progress",
    "started_at": "2026-10-10T14:00:00Z"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 校验比赛当前状态为 `setup`，否则返回 400

2. 更新 `match.status = 'in_progress'`，记录 `started_at`

3. 同步 Redis `scoring:match:{match_id}:status` 为 `in_progress`

4. 进入 `in_progress` 后才允许记分操作（§5.4）

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 比赛不在 setup 状态（已开始或已结束） | 比赛已开始或已结束 |
| 404 | 比赛不存在或不属于当前用户 | 比赛不存在 |

### 5.9 POST /scoring/matches/{match_id}/abandon

**描述**：放弃比赛（状态机转换：in_progress → abandoned）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "比赛已放弃",
  "data": {
    "match_id": 2001,
    "status": "abandoned",
    "abandoned_at": "2026-10-10T14:30:00Z"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 校验比赛当前状态为 `in_progress`，否则返回 400

2. 更新 `match.status = 'abandoned'`，记录 `abandoned_at`

3. 同步 Redis `scoring:match:{match_id}:status` 为 `abandoned`

4. 24h 内可通过 §5.10 resume 恢复；超过 24h 由 Celery Beat 定时任务自动转为 `finished`

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 比赛不在 in_progress 状态 | 仅进行中的比赛可放弃 |
| 404 | 比赛不存在或不属于当前用户 | 比赛不存在 |

### 5.10 POST /scoring/matches/{match_id}/resume

**描述**：恢复放弃的比赛（状态机转换：abandoned → in_progress）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "比赛已恢复",
  "data": {
    "match_id": 2001,
    "status": "in_progress",
    "resumed_at": "2026-10-10T15:00:00Z"
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 校验比赛当前状态为 `abandoned`，否则返回 400

2. 校验 `abandoned_at` 距当前时间不超过 24h，否则返回 400（超时的比赛已由定时任务转为 `finished`）

3. 更新 `match.status = 'in_progress'`，清空 `abandoned_at`

4. 同步 Redis `scoring:match:{match_id}:status` 为 `in_progress`

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 比赛不在 abandoned 状态 | 仅放弃的比赛可恢复 |
| 400 | 放弃超过 24h | 放弃超过 24h，比赛已自动结束 |
| 404 | 比赛不存在或不属于当前用户 | 比赛不存在 |

---

## 6. 数据看板模块 (`/dashboard`)

### 6.1 GET /dashboard/overview

**描述**：概览卡片（胜率/分析次数/训练频次）

**权限**：登录

**缓存**：5min

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "win_rate": 0.70,
    "wins": 12,
    "losses": 5,
    "analysis_count": 8,
    "training_frequency_per_week": 4,
    "streak_days": 7,
    "trend": "up",
    "latest_advice_summary": {
      "report_id": 1001,
      "summary": "反手使用率从18%提升到25%，进步明显；正手落点集中问题已持续2次分析未改善",
      "has_unresolved_issues": true,
      "latest_report_at": "2026-10-09T14:00:00Z"
    }
  },
  "timestamp": "..."
}
```

> **latest_advice_summary 字段说明**（P2-5 修复）：前端首页 H1.1 训练提醒卡片数据来源。取最近一次分析报告的训练建议摘要，无分析记录时为 `null`。

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 6.2 GET /dashboard/win-rate-trend

**描述**：战绩趋势

**权限**：登录

**缓存**：1h

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| period | query | string | N | 时间范围：month/quarter/year，默认 month |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "labels": ["10/01", "10/02", "10/03", "..."],
    "series": [
      {"name": "胜率", "data": [0.6, 0.7, 0.65, "..."]},
      {"name": "比赛场次", "data": [2, 3, 2, "..."]}
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 6.3 GET /dashboard/technique-stats

**描述**：技术统计

**权限**：登录

**缓存**：1h

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "technique_distribution": [
      {"name": "正手攻球", "value": 45, "color": "#E63946"},
      {"name": "反手拨球", "value": 18, "color": "#1D3557"},
      {"name": "正手拉球", "value": 12, "color": "#F4A261"},
      {"name": "发球", "value": 23, "color": "#2A9D8F"}
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 6.4 GET /dashboard/landing-heatmap

**描述**：累计落点热图

**权限**：登录

**缓存**：1h

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "nine_grid": [[2,5,3],[4,8,6],[1,3,2]],
    "distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07},
    "total_rallies": 120,
    "source_reports_count": 8
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 6.5 GET /dashboard/match-records

**描述**：比赛记录列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| result | query | string | N | win/lose/all |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 17,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 5001,
        "opponent_name": "张某",
        "opponent_rating": 1480,
        "my_score": 3,
        "opponent_score": 1,
        "is_win": true,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": "2026-10-10T14:00:00Z"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

## 7. 比赛数据模块 (`/match-data`)

### 7.1 POST /match-data/records

**描述**：创建比赛记录（快速/详细录入）

**权限**：登录

#### Request Body（快速录入）

```json
{
  "opponent_name": "张某",
  "opponent_rating": 1480,
  "my_score": 3,
  "opponent_score": 1,
  "format": "bo5",
  "match_type": "friendly",
  "match_date": "2026-10-10T14:00:00Z",
  "details": null
}
```

#### Request Body（详细录入）

```json
{
  "opponent_name": "张某",
  "opponent_rating": 1480,
  "my_score": 11,
  "opponent_score": 8,
  "format": "custom",
  "match_type": "friendly",
  "match_date": "2026-10-10T14:00:00Z",
  "details": [
    {"sequence": 1, "scorer": "user", "score_method": "serve_point", "technique_action": "forehand_drive"},
    {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"}
  ]
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "比赛记录已创建",
  "data": {
    "id": 5001,
    "match_id": 2001,
    "is_win": true
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | 比分不符合赛制规则 | 比分不符合赛制规则 |
| 422 | match_date 在未来 | 比赛日期不能晚于当前时间 |

### 7.2 GET /match-data/records

**描述**：比赛记录列表（分页）

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| result | query | string | N | win/lose/all |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 17,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 5001,
        "opponent_name": "张某",
        "opponent_rating": 1480,
        "my_score": 3,
        "opponent_score": 1,
        "is_win": true,
        "format": "bo5",
        "match_type": "friendly",
        "match_date": "2026-10-10T14:00:00Z"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 7.3 GET /match-data/records/{record_id}

**描述**：比赛记录详情（含得分明细）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 5001,
    "opponent_name": "张某",
    "opponent_rating": 1480,
    "my_score": 3,
    "opponent_score": 1,
    "is_win": true,
    "format": "bo5",
    "match_type": "friendly",
    "match_date": "2026-10-10T14:00:00Z",
    "details": [
      {"sequence": 1, "scorer": "user", "score_method": "serve_point", "technique_action": "forehand_drive"},
      {"sequence": 2, "scorer": "opponent", "score_method": "rally_point"}
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 比赛记录不存在或不属于当前用户 | 比赛记录不存在 |

### 7.4 PATCH /match-data/records/{record_id}

**描述**：编辑比赛记录（仅更新传入字段，仅限未关联记分牌的记录）

**权限**：登录

#### Request Body

```json
{
  "opponent_name": "张某",
  "opponent_rating": 1500,
  "my_score": 3,
  "opponent_score": 1,
  "notes": "反手表现不错"
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| opponent_name | string | N | 对手姓名 |
| opponent_rating | int | N | 对手积分（500-3000） |
| my_score | int | N | 我方得分 |
| opponent_score | int | N | 对手得分 |
| match_date | string(datetime) | N | 比赛日期时间（不能晚于当前时间） |
| match_type | string | N | 比赛类型（friendly/tournament/training） |
| notes | string | N | 比赛备注 |

#### Response Body

```json
{
  "code": 200,
  "message": "比赛记录已更新",
  "data": {
    "id": 5001,
    "is_win": true,
    "updated_fields": ["opponent_name", "opponent_rating", "notes"]
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 仅更新传入的字段（PATCH 语义），未传入字段保持不变

2. 任一比分字段（`my_score` / `opponent_score`）发生变更即自动重新计算 `is_win`；`is_win` 由服务端自动计算，**禁止前端传入**（R13-P3 文档同步：对齐 R12-MatchData-B1/B2 修复后实现——Update Schema 不含 is_win，未知字段被忽略；重算条件为 OR 语义，非"同时传入两比分"）

3. 若比赛记录关联了记分牌比赛（`match_id` 不为空），返回 409 禁止编辑（应通过记分牌修改）

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 比赛记录不存在或不属于当前用户 | 比赛记录不存在 |
| 409 | 比赛记录已关联记分牌，不可编辑 | 关联记分牌的记录不可直接编辑 |
| 422 | 比分不符合赛制规则 | 比分不符合赛制规则 |

---

## 8. 训练模块 (`/training`)

### 8.1 GET /training/advice/{report_id}

**描述**：基于分析报告的训练建议（增强：含历史趋势对比）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "report_id": 1,
    "is_first_analysis": false,
    "diagnosis": [
      {
        "problem_id": "PROBLEM_003",
        "problem_name": "反手使用率不足",
        "severity": "medium",
        "trend": "improving",
        "description": "反手使用率 25%，低于推荐值 30%，但已从 18% 提升至 25%，趋势向好"
      }
    ],
    "suggestions": [
      {"type": "progress_confirm", "text": "你的反手使用率从 18% 提升到 25%，进步明显"},
      {"type": "persistent_warning", "text": "正手落点集中问题已持续 3 次分析未改善，建议调整训练方法"},
      {"type": "new_issue", "text": "本次分析发现反手拉球引拍过大，历史报告中未出现过"}
    ],
    "training_methods": [
      {"method_id": "METHOD_012", "name": "反手多球练习", "description": "..."},
      {"method_id": "METHOD_015", "name": "反手拉球定点练习", "description": "..."}
    ],
    "training_plan_template": "TPL_BACKHAND_IMPROVE"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 报告不存在或不属于当前用户 | 报告不存在 |

### 8.2 GET /training/advice/contextual

**描述**：基于最新报告 + 历史趋势的综合建议（自动取最新报告）

**权限**：登录

#### Response Body

同 8.1，但 report_id 自动取用户最新完成的分析报告。

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 用户尚无已完成的分析报告 | 暂无分析报告，请先上传视频分析 |

### 8.3 GET /training/templates

**描述**：训练方案模板列表

**权限**：会员（R19-P1-2 修复：与切片 `require_membership("member")` 保持一致，原标注"登录"）

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| problem_id | query | string | N | 按问题筛选 |
| page | query | int | N | 页码，默认 1 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 5,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 1,
        "template_code": "TPL_BACKHAND_IMPROVE",
        "name": "反手提升训练方案",
        "problem_id": "PROBLEM_003"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 8.4 GET /training/templates/{template_id}

**描述**：模板详情

**权限**：会员（R19-P1-2 修复：与切片 `require_membership("member")` 保持一致，原标注"登录"）

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "template_code": "TPL_BACKHAND_IMPROVE",
    "name": "反手提升训练方案",
    "problem_id": "PROBLEM_003",
    "template_data": {
      "goal": {"metric": "backhand_ratio", "target": 0.35},
      "sessions": [{"name": "反手多球练习", "reps": 50}],
      "exercises": ["反手定点拉球", "反手一正一反"],
      "metrics": ["backhand_ratio", "landing_backhand_pct"]
    }
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 模板不存在 | 模板不存在 |

### 8.5 GET /training/plans/{plan_id}/adjustments

**描述**：训练方案调整历史（版本化记录）

**权限**：会员（R19-P1-2 修复：与切片 `require_membership("member")` 保持一致，原标注"登录"）

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "plan_id": 100,
    "current_version": 3,
    "adjustments": [
      {
        "id": 1,
        "version": 2,
        "action": "adjust",
        "reason": "反手训练连续 3 次分析改善，维持当前方案",
        "trigger_report_id": 5,
        "created_at": "2026-09-15T10:00:00Z",
        "changes_summary": "训练量增加 20%"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 训练方案不存在或不属于当前用户 | 训练方案不存在 |

### 8.6 POST /training/plans/{plan_id}/re-evaluate

**描述**：手动触发方案重新评估

**权限**：会员

#### Response Body

```json
{
  "code": 200,
  "message": "方案已重新评估",
  "data": {
    "plan_id": 100,
    "action": "maintain",
    "reason": "当前方案有效，反手使用率持续改善"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 训练方案不存在或不属于当前用户 | 训练方案不存在 |
| 403 | 非会员用户 | 此功能需要会员及以上等级 |

### 8.7 GET /training/plans/{plan_id}/sessions

**描述**：训练方案下的训练单列表（每次训练的具体内容清单）

**权限**：会员

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| page | query | int | N | 页码，默认 1 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 10,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 1,
        "session_index": 1,
        "name": "反手多球练习",
        "reps": 50,
        "is_completed": true,
        "completed_at": "2026-10-01T10:00:00Z"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 训练方案不存在或不属于当前用户 | 训练方案不存在 |
| 403 | 非会员用户 | 此功能需要会员及以上等级 |

### 8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete

**描述**：标记训练单为已完成

**权限**：会员

#### Response Body

```json
{
  "code": 200,
  "message": "训练单已完成",
  "data": {
    "session_id": 1,
    "is_completed": true,
    "plan_progress": 70,
    "points_earned": 5
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 校验 session 属于指定 plan 且属于当前用户

2. 更新 `session.is_completed = true`，记录 `completed_at`

3. 重新计算方案整体进度 `plan_progress`

4. 触发 gamification 积分（+5）

5. 若 session 已完成，返回 409

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 训练单不存在 | 训练单不存在 |
| 409 | 训练单已完成 | 该训练单已完成 |
| 403 | 非会员用户 | 此功能需要会员及以上等级 |

---

## 9. 进度分析模块 (`/progress`)

### 9.1 GET /progress/snapshots

**描述**：进度快照列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| status | query | string | N | 状态过滤 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 8,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 1,
        "report_id": 1,
        "created_at": "2026-07-10T12:00:00Z",
        "metrics_snapshot": {
          "backhand_ratio": 0.18,
          "forehand_ratio": 0.72,
          "avg_ball_speed": 16.5
        }
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 9.2 GET /progress/technique-trends

**描述**：全部技术指标趋势

**权限**：登录

**缓存**：1h

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "metrics": [
      {
        "metric": "backhand_ratio",
        "metric_name": "反手使用率",
        "current_value": 0.32,
        "previous_value": 0.25,
        "change_rate": 0.28,
        "trend": "improving",
        "target": 0.35,
        "target_progress": 91,
        "persistence_count": 4
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 9.3 GET /progress/technique-trends/{metric}

**描述**：单项指标趋势详情（含时间序列数据）

**权限**：登录

**缓存**：1h

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "metric": "backhand_ratio",
    "metric_name": "反手使用率",
    "current_value": 0.32,
    "target_value": 0.35,
    "target_progress": 91,
    "trend": "improving",
    "change_rate": 0.28,
    "persistence_count": 4,
    "history": [
      {"date": "2026-07-10", "value": 0.18},
      {"date": "2026-07-25", "value": 0.22},
      {"date": "2026-08-10", "value": 0.25},
      {"date": "2026-08-28", "value": 0.28},
      {"date": "2026-09-15", "value": 0.30},
      {"date": "2026-10-01", "value": 0.32}
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 指标名不存在 | 指标不存在 |

### 9.4 GET /progress/comparison

**描述**：两次分析报告对比

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| report_a | query | int | Y | 报告 A ID |
| report_b | query | int | Y | 报告 B ID |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "report_a": {"id": 1, "created_at": "2026-09-01T12:00:00Z"},
    "report_b": {"id": 5, "created_at": "2026-10-01T12:00:00Z"},
    "comparisons": {
      "technique_stats": {
        "forehand_ratio": {"a": 0.68, "b": 0.62, "change": -0.06},
        "backhand_ratio": {"a": 0.25, "b": 0.32, "change": 0.07}
      },
      "landing": {
        "forehand_pct": {"a": 0.68, "b": 0.62, "change": -0.06},
        "backhand_pct": {"a": 0.25, "b": 0.32, "change": 0.07},
        "middle_pct": {"a": 0.07, "b": 0.06, "change": -0.01}
      },
      "rally": {"avg_length_a": 4.5, "avg_length_b": 5.2, "change": 0.7},
      "ball_speed": {"avg_a": 17.2, "avg_b": 18.5, "change": 1.3},
      "score_analysis": {"win_rate_a": 0.50, "win_rate_b": 0.55, "change": 0.05},
      "problem_changes": {
        "new": ["反手拉球引拍过大"],
        "resolved": ["发球落点单一"],
        "persistent": ["正手落点偏集中"]
      }
    }
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 报告 A 或 B 不存在 | 报告不存在 |
| 422 | report_a 和 report_b 相同 | 请选择两份不同的报告 |

### 9.5 GET /progress/summary

**描述**：进度综合摘要

**权限**：登录

**缓存**：5min

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "summary_period": "last_3_months",
    "total_analyses": 8,
    "overall_progress": "improving",
    "metric_trends": [ ],
    "problem_changes": {
      "resolved": ["发球落点单一"],
      "new": ["反手拉球引拍过大"],
      "persistent": ["正手落点偏集中"]
    },
    "training_plan_status": {
      "current_plan_id": "plan_xxx",
      "plan_version": 3,
      "last_adjustment": "2026-09-15",
      "adjustment_reason": "反手训练连续 3 次分析改善，维持当前方案",
      "goal_completion": {"backhand_ratio": "91%"}
    },
    "forecast": {
      "backhand_ratio": {
        "predicted_weeks_to_target": 2,
        "confidence": "high",
        "r_squared": 0.82
      }
    }
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 9.6 GET /progress/problem-changes

**描述**：问题变化列表（新增/已解决/持续）

**权限**：登录

**缓存**：1h

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "new": [
      {"problem_id": "PROBLEM_005", "problem_name": "反手拉球引拍过大", "first_seen": "2026-10-01"}
    ],
    "resolved": [
      {"problem_id": "PROBLEM_001", "problem_name": "发球落点单一", "last_seen": "2026-09-01"}
    ],
    "persistent": [
      {"problem_id": "PROBLEM_002", "problem_name": "正手落点偏集中", "persistence_count": 5}
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

## 10. 游戏化模块 (`/gamification`)

### 10.1 GET /gamification/points

**描述**：训练积分

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total_points": 580,
    "monthly_points": 120,
    "current_streak": 7,
    "streak_icon": "🔥"
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 10.2 GET /gamification/checkin-calendar

**描述**：打卡日历（月度）

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| year | query | int | N | 年，默认当前年 |
| month | query | int | N | 月，默认当前月 |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "year": 2026,
    "month": 10,
    "days": [
      {"date": "2026-10-01", "checked_in": true, "type": "analysis"},
      {"date": "2026-10-02", "checked_in": true, "type": "match"},
      {"date": "2026-10-03", "checked_in": false, "type": null}
    ],
    "monthly_checkin_count": 18,
    "streak_days": 7
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 10.3 POST /gamification/checkin

**描述**：手动打卡

**权限**：登录

**限流**：1/天

#### Response Body

```json
{
  "code": 200,
  "message": "打卡成功",
  "data": {
    "points_earned": 2,
    "current_streak": 7,
    "bonus": null
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 今日已打卡 | 今日已打卡 |

### 10.4 GET /gamification/badges

**描述**：徽章列表（已获得/未获得）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "earned": [
      {"badge_id": "first_analysis", "name": "首分析", "icon": "📹", "earned_at": "2026-07-10"},
      {"badge_id": "streak_7", "name": "连续7天", "icon": "🔥", "earned_at": "2026-07-17"}
    ],
    "locked": [
      {"badge_id": "streak_30", "name": "连续30天", "icon": "🌟", "progress": 7, "target": 30}
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

## 11. 会员模块 (`/membership`)

### 11.1 GET /membership/tiers

**描述**：会员等级与权益对比

**权限**：登录

**缓存**：1h

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "tiers": [
      {
        "tier": "free",
        "name": "免费版",
        "price_monthly_cents": 0,
        "price_quarterly_cents": 0,
        "price_yearly_cents": 0,
        "benefits": ["每日 3 次分析", "记分牌", "数据看板", "社区浏览"],
        "quota_config": {"daily_analysis_limit": 3}
      },
      {
        "tier": "member",
        "name": "会员版",
        "price_monthly_cents": 1900,
        "price_quarterly_cents": 4900,
        "price_yearly_cents": 16800,
        "benefits": ["无限分析", "训练方案", "训练单", "3D 教学", "历史对比"],
        "quota_config": {"daily_analysis_limit": -1}
      },
      {
        "tier": "pro",
        "name": "专业版",
        "price_monthly_cents": 3900,
        "price_quarterly_cents": 9900,
        "price_yearly_cents": 35800,
        "benefits": ["无限分析", "高级分析", "对手建模", "月度报告", "训练方案"],
        "quota_config": {"daily_analysis_limit": -1}
      },
      {
        "tier": "coach",
        "name": "教练版",
        "price_monthly_cents": 9900,
        "price_quarterly_cents": 26900,
        "price_yearly_cents": 89900,
        "benefits": ["学员管理", "批量分析", "教练工具", "专业版全部权益"],
        "quota_config": {"daily_analysis_limit": -1}
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 11.2 GET /membership/current

**描述**：当前会员状态

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "tier": "member",
    "status": "active",
    "start_at": "2026-10-01T00:00:00Z",
    "expire_at": "2026-11-01T00:00:00Z",
    "days_remaining": 22,
    "auto_renew": false
  },
  "timestamp": "..."
}
```

> **字段说明**：`status` 枚举值为 `active`（有效）| `expired`（已过期）| `grace_period`（宽限期内）

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 11.3 GET /membership/quota

**描述**：今日剩余免费分析次数

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "tier": "free",
    "daily_limit": 3,
    "used_today": 1,
    "remaining": 2,
    "reset_at": "2026-10-11T00:00:00+08:00"
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

## 12. 支付模块 (`/payment`)

### 12.1 POST /payment/orders

**描述**：创建订单（会员订阅/分析次数包）

**权限**：登录

#### Request Body

```json
{
  "product_type": "membership",
  "tier": "member",
  "period": "monthly",
  "payment_method": "wechat_jsapi"
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "订单已创建",
  "data": {
    "order_id": 8001,
    "order_no": "PP202610010001",
    "amount_cents": 1900,
    "payment_params": {
      "prepay_id": "wx001xxx",
      "pay_sign": "xxx",
      "timestamp": "202610010001",
      "nonce_str": "xxx"
    }
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 创建 order（status=pending）

2. 调用微信统一下单（JSAPI/APP）

3. 返回支付参数

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | product_type 不在枚举中 | 产品类型不合法 |
| 422 | tier 不在枚举中或 period 缺失 | 会员等级或周期参数不合法 |
| 502 | 微信统一下单失败 | 支付服务暂时不可用 |

### 12.2 GET /payment/orders

**描述**：订单列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| status | query | string | N | 状态过滤 |
| product_type | query | string | N | 产品类型过滤 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 5,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 8001,
        "order_no": "PP202610010001",
        "product_type": "membership",
        "amount_cents": 1900,
        "status": "paid",
        "created_at": "2026-10-01T12:00:00Z",
        "paid_at": "2026-10-01T12:01:00Z"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 12.3 POST /payment/notify

**描述**：微信支付异步回调（V3 APIv3）

**权限**：微信签名（APIv3 证书验证）

#### Request Headers

| Header | 必填 | 描述 |
|--------|------|------|
| Wechatpay-Signature | Y | 微信支付签名（Base64） |
| Wechatpay-Serial | Y | 微信支付平台证书序列号 |
| Wechatpay-Nonce | Y | 随机字符串 |
| Wechatpay-Timestamp | Y | 时间戳（秒） |
| Content-Type | Y | `application/json` |

#### Request Body（微信 V3 回调原始结构）

```json
{
  "id": "EV-2018022511223320883",
  "create_time": "2026-10-10T12:01:00+08:00",
  "resource_type": "encrypt-resource",
  "event_type": "TRANSACTION.SUCCESS",
  "resource": {
    "algorithm": "AEAD_AES_256_GCM",
    "ciphertext": "base64_encoded_encrypted_data",
    "nonce": "5K8264ILTKCH16CQ2502SI8ZNMTM67VS",
    "associated_data": "transaction"
  }
}
```

#### 验签与解密流程

1. **验签**：用微信支付平台证书（通过 `Wechatpay-Serial` 查找本地缓存的平台证书）验证 `Wechatpay-Signature`，签名内容为 `timestamp\nnonce\nbody\n`

2. **解密**：用商户 APIv3 密钥（32 字节）作为 AES-256-GCM 密钥，`resource.nonce` 作为 GCM nonce，`resource.associated_data` 作为 AD，解密 `resource.ciphertext`

3. **解析**：解密后得到支付结果 JSON，包含 `transaction_id`、`out_trade_no`、`trade_state`、`amount.total` 等字段

#### Response Body

成功处理（微信要求返回 HTTP 200 + 以下 JSON，非本项目统一响应格式）：

```json
{
  "code": "SUCCESS",
  "message": "成功"
}
```

失败处理（返回 HTTP 4xx/5xx + 以下 JSON，微信会重试）：

```json
{
  "code": "FAIL",
  "message": "签名验证失败"
}
```

> **F7-1 响应格式说明**：支付回调端点 `POST /payment/notify` 的响应格式为**微信支付 V3 协议要求格式**（`{"code": "SUCCESS/FAIL", "message": "..."}`），**非本项目统一响应格式**（`{"code": 200, "message": "...", "data": ..., "timestamp": "..."}`）。这是因为微信支付服务器只识别 `code=SUCCESS`（HTTP 200）或 `code=FAIL`（HTTP 4xx/5xx），不支持自定义响应结构。

#### 业务规则

1. **验签**：验证 `Wechatpay-Signature`，签名校验失败 → 返回 400 `{"code": "FAIL", "message": "签名验证失败"}`

2. **解密**：解密 `resource.ciphertext`，解密失败 → 返回 400 `{"code": "FAIL", "message": "解密失败"}`

3. **查找订单**：通过解密后的 `out_trade_no` 查找 order 记录

4. **幂等处理**：检查 order.status，若已为 `paid` → 直接返回 200 `{"code": "SUCCESS", "message": "成功"}`（幂等 ACK，不重复处理）

5. **更新订单**：order.status='paid', order.paid_at=NOW()

6. **创建 payment_record**：记录 transaction_id、payment_method、amount_cents、callback_raw（验签后的明文 JSON）

7. **触发业务逻辑**：
   - membership → 创建/续期 subscription（start_at=NOW(), expire_at=start_at+period）
   - analysis_pack → 增加额外额度（Redis INCR quota:bonus:{user_id}）
   - equipment → 创建发货单（Phase 4）
8. **WS 推送**：向 `ws:user:{user_id}` 推送 `payment_success {order_id, product_type}`

9. **返回 ACK**：200 `{"code": "SUCCESS", "message": "成功"}`

#### 错误情况

| HTTP | code | 条件 | 消息 |
|------|------|------|------|
| 400 | FAIL | 签名验证失败 | 签名验证失败 |
| 400 | FAIL | 解密失败 | 解密失败 |
| 404 | FAIL | out_trade_no 对应的订单不存在 | 订单不存在 |
| 500 | FAIL | 业务处理异常（DB 事务回滚等） | 服务内部错误 |

> **幂等说明**：微信支付可能对同一笔交易发送多次回调（重试机制）。本端点通过检查 `order.status` 实现幂等：已处理的订单直接返回 SUCCESS，不重复执行业务逻辑。callback_raw 仅在首次处理时写入。

### 12.4 POST /payment/orders/{order_id}/refund

**描述**：申请退款（管理员操作）

**权限**：管理员（AdminUser session）

#### Request Body

```json
{
  "refund_amount_cents": 1900,
  "reason": "用户投诉，申请全额退款"
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| refund_amount_cents | int | Y | 退款金额（分），≤订单金额 |
| reason | string | Y | 退款原因 |

**业务规则**：
- 下单 24h 内：支持全额退款（refund_amount_cents = order.amount_cents）
- 下单 24h~7d：支持部分退款（refund_amount_cents ≤ order.amount_cents * 50%），需管理员审核
- 下单 7d 后：不支持退款，返回 422
- 退款成功后同步撤销订阅（subscription.status → closed, subscription.cancelled_at = now）

#### Response Body

```json
{
  "code": 200,
  "message": "退款申请已提交",
  "data": {
    "order_id": 8001,
    "refund_status": "pending",
    "refund_amount_cents": 1900
  },
  "timestamp": "..."
}
```

#### 业务规则

1. 校验订单状态为 `paid`

2. 调用微信支付退款 API（需要商户证书）

3. 创建 refund_record（order_id, refund_amount, reason, status=pending）

4. 退款成功回调（微信异步通知）→ 更新 refund_record.status=success → 更新 order.status=refunded → 撤销会员权益（如适用）

5. 退款失败 → refund_record.status=failed → 返回失败原因

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 订单不存在 | 订单不存在 |
| 400 | 订单状态非 paid | 仅已支付订单可退款 |
| 400 | 退款金额超出订单金额 | 退款金额不能超过订单金额 |
| 422 | 下单超过 7 天 | 超过7天的订单不可退款 |
| 502 | 微信退款 API 失败 | 退款服务暂时不可用 |

> **Phase 标注**：退款为 Phase 1+ 功能，Phase 1 可通过人工后台处理（直接调用微信支付商户平台退款），Phase 1 第二迭代补充 API 化退款端点。

---

## 13. 通知模块 (`/notification`)

### 13.1 GET /notification/list

**描述**：通知列表（分页）

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| is_read | query | bool | N | 已读过滤 |
| type | query | string | N | 类型过滤 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 12,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 1,
        "type": "analysis_complete",
        "title": "分析完成",
        "content": "您的视频分析已完成，点击查看报告",
        "is_read": false,
        "extra_data": {"task_id": "task_xxx", "report_id": 1},
        "created_at": "2026-10-10T12:05:00Z"
      }
    ]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 13.2 POST /notification/read

**描述**：标记已读

**权限**：登录

#### Request Body

```json
{
  "notification_ids": [1, 2, 3]
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "已标记为已读",
  "data": {
    "updated_count": 3
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | notification_ids 为空或超过 100 条 | 请选择要标记的通知 |

### 13.3 POST /notification/subscribe

**描述**：微信订阅消息授权

**权限**：登录

#### Request Body

```json
{
  "template_ids": ["analysis_complete", "payment_success"]
}
```

#### Response Body

```json
{
  "code": 200,
  "message": "订阅已更新",
  "data": {
    "subscribed_templates": ["analysis_complete", "payment_success"]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | template_ids 为空 | 请选择订阅模板 |
| 422 | template_ids 包含不存在的模板 ID | 订阅模板 ID 不合法 |

### 13.4 GET /notification/unread-count

**描述**：未读通知数量（用于底部 Tab 红点显示）

**权限**：登录

#### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "unread_count": 3
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

## 14. WebSocket 端点 (`/ws`)

### 14.1 连接方式

**认证方式**：Sec-WebSocket-Protocol 子协议认证（P2 安全合规修改）

连接时通过 WebSocket 子协议传递 JWT Token，而非 URL Query 参数，避免 Token 泄露到服务器日志和代理缓存中。

```
wss://api.pingpongai.com/ws
Sec-WebSocket-Protocol: jwt.{access_token}
```

> **P2 修改说明**：原认证方式为 URL Query `?token=xxx`，已改为 Sec-WebSocket-Protocol 子协议 `['jwt.{token}']`，提升安全性（Token 不出现在 URL 中，避免被日志/代理缓存/Referer 泄露）。

### 14.2 事件类型

| event | 方向 | data | 说明 |
|-------|------|------|------|
| `connected` | S→C | `{user_id}` | 连接成功 |
| `analysis_progress` | S→C | `{task_id, step, total, message}` | AI 分析进度 |
| `analysis_complete` | S→C | `{task_id, report_id}` | 分析完成 |
| `analysis_failed` | S→C | `{task_id, error}` | 分析失败 |
| `score_update` | S→C | `{match_id, sequence, score, scorer, method}` | 比分更新 |
| `score_update` (undo) | S→C | `{match_id, sequence, action: "undo", score}` | 撤销比分 |
| `sync_match` | S→C | `{match_id, status, current_score, score_sequence}` | 全量同步 |
| `sync_analysis` | S→C | `{task_id, status, step, total, report_id?}` | 分析进度全量同步（重连后） |
| `notification` | S→C | `{type, title, content}` | 系统通知 |
| `payment_success` | S→C | `{order_id, product_type}` | 支付成功 |
| `ping` | C→S | — | 心跳 |
| `pong` | S→C | `{token_expired: boolean}` | 心跳响应，token_expired=true 时前端需刷新 Token |

### 14.3 频道管理

| 频道 | Key | 加入时机 |
|------|-----|---------|
| 用户频道 | `ws:user:{user_id}` | 连接时自动加入 |
| 比赛房间 | `ws:match:{match_id}` | 进入记分牌页面时加入，离开时退出 |

### 14.4 重连策略

- 指数退避：1s → 2s → 4s → 8s → 16s
- 最大重试 5 次
- 重连后触发 `sync_match` / `sync_analysis` 全量同步

---

## 14a. 首页聚合端点说明（前端聚合，无后端 API）

### GET /home/dashboard
首页聚合数据（并发调用多个已有端点，前端聚合，无独立后端端点）

> **注意**：此端点为前端聚合页面，前端 `services/home.ts` 并发调用多个已有端点（`GET /dashboard/overview`（含用户信息+训练建议摘要），`GET /gamification/checkin-calendar`（打卡日历），`GET /scoring/matches`（最近比赛），`GET /notification/unread-count`（未读通知数）），无独立后端 API。
> **缓存策略**：前端 Zustand homeStore `staleTime=30s`，无服务端缓存
> **认证**：需要 Bearer Token

> **设计说明**：首页 Dashboard 数据由前端并发请求多个已有 Phase 1 端点聚合而成，不创建独立后端 BFF 端点。前端使用 Zustand homeStore 管理并发请求与缓存，各子请求复用已有端点的缓存策略。用户信息从 authStore 获取（无需独立调用 /users/profile），训练建议摘要从 /dashboard/overview 响应体的 latest_advice_summary 字段获取。此设计避免后端引入额外的聚合 Service 层，保持 API 粒度一致。架构 §5.7 L948-956 已说明首页聚合采用前端多模块并发模式（无独立后端 API 端点），本 §14a 的 `GET /home/dashboard` 标题仅作前端聚合模式命名，并非独立后端路由。

---

## 15. Phase 2 API 端点详细设计

### 15.1 GET /advanced-analysis/reports/{id}

**描述**：高级分析报告详情（球速/弧度/动作细节/攻防转换）

**权限**：专业

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "report_id": 1,
    "ball_speed_data": {"by_action": {"forehand_loop": {"avg": 22.5, "max": 28.0, "range": [18, 28]}}, "overall": {"avg": 18.5, "max": 25.3}},
    "action_detail": {"total_shots": 156, "by_type": {"forehand_drive": {"count": 45, "success_rate": 0.72}}},
    "arc_data": {"avg_arc_height": 0.35, "by_action": {"forehand_loop": {"height": 0.42, "angle": 35}}},
    "transition_timeline": [{"time": "00:15", "from": "serve", "to": "rally", "duration": 2.3}]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 报告不存在或不属于当前用户 | 报告不存在 |
| 403 | 非专业版用户 | 此功能需要专业版及以上等级 |

### 15.2 GET /opponent-analysis/profiles

**描述**：对手列表

**权限**：专业

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 8, "page": 1, "page_size": 20,
    "items": [{"id": 1, "opponent_name": "张某", "match_count": 5, "win_rate": 0.40, "last_played": "2026-10-01T14:00:00Z"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 15.3 GET /opponent-analysis/profiles/{id}

**描述**：对手 Scout 报告

**权限**：专业

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "opponent_name": "张某", "match_count": 5,
    "playing_style": "shakehand_attack",
    "landing_preference": {"nine_grid": [[3,4,2],[5,7,3],[2,3,1]], "favorite_zones": ["反手位长球"]},
    "serve_preference": {"variations": 3, "favorite_serve": "正手短球", "success_rate": 0.65},
    "weakness_zones": ["正手位短球", "中间位半台"],
    "pre_match_advice": "对手正手较强，建议多发反手长球限制其侧身"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 对手档案不存在 | 对手档案不存在 |
| 403 | 非专业版用户 | 此功能需要专业版及以上等级 |

### 15.4 GET /3d-teaching/models

**描述**：3D 模型列表

**权限**：会员

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| category | query | string | N | 分类筛选 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 12, "page": 1, "page_size": 20,
    "items": [{"id": 1, "name": "正手攻球标准动作", "category": "FOREHAND", "status": "published", "thumbnail_url": "https://cdn.../thumbnail.jpg"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 15.5 GET /3d-teaching/models/{id}

**描述**：模型详情 + CDN URL

**权限**：会员

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "name": "正手攻球标准动作", "category": "FOREHAND",
    "model_url": "https://cdn.pingpongai.com/3d/models/1/model.glb",
    "description": "标准正手攻球动作，含引拍、击球、随挥三个阶段",
    "duration_sec": 3.5, "model_version": "v1.0"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 模型不存在或未发布 | 模型不存在 |
| 403 | 非会员用户 | 此功能需要会员及以上等级 |

### 15.6 GET /3d-teaching/models/{id}/annotations

**描述**：关节标注数据

**权限**：会员

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "model_id": 1,
    "annotations": [{"frame": 0, "joints": [{"name": "right_shoulder", "x": 0.3, "y": 0.5, "z": 0.2, "angle": 45}], "notes": "引拍阶段，肩关节角度45°"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 15.7 GET /3d-teaching/models/{id}/key-poses

**描述**：关键姿势数据

**权限**：会员

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "model_id": 1,
    "key_poses": [{"pose_name": "引拍", "frame": 0, "description": "球拍后引至身体右侧", "key_angles": {"shoulder": 45, "elbow": 90, "hip": 30}}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 15.8 POST /3d-teaching/compare

**描述**：用户视频 vs 3D 标准动作对比

**权限**：会员

#### Request Body

```json
{"file_id": 1001, "model_id": 1, "compare_mode": "side_by_side"}
```

#### Response Body

```json
{
  "code": 200, "message": "对比分析完成",
  "data": {
    "comparison_id": 1, "model_id": 1,
    "differences": [{"joint": "right_shoulder", "user_angle": 35, "standard_angle": 45, "diff": -10, "severity": "medium"}],
    "overall_score": 78, "suggestions": ["引拍幅度不足，建议增加肩关节旋转角度"]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 文件或模型不存在 | 资源不存在 |
| 400 | 视频无法识别人体姿态 | 视频无法识别人体姿态，请更换拍摄角度 |

### 15.9 GET /training/plans

**描述**：训练方案列表

**权限**：会员

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 3, "page": 1, "page_size": 20,
    "items": [{"id": 100, "name": "反手提升方案", "status": "active", "version": 3, "progress": 65, "created_at": "2026-09-01T00:00:00Z"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 15.10 GET /training/plans/{id}

**描述**：方案详情

**权限**：会员

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 100, "name": "反手提升方案", "status": "active", "version": 3,
    "goal": {"metric": "backhand_ratio", "target": 0.35, "current": 0.25},
    "sessions": [{"id": 1, "name": "反手多球练习", "reps": 50, "is_completed": true, "completed_at": "2026-10-01T10:00:00Z"}],
    "progress": 65
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 方案不存在 | 训练方案不存在 |
| 403 | 非会员用户 | 此功能需要会员及以上等级 |

### 15.11~15.12 训练单端点（Phase 1 已定义）

> **P2-IMP-01 修复**：训练单列表（`GET /training/plans/{id}/sessions`）和完成训练单（`POST /training/plans/{id}/sessions/{sid}/complete`）端点已在 Phase 1 训练模块中定义，见 §8.7-8.8（Phase 1）。此处不再重复定义。

### 15.13 GET /monthly-report/current

**描述**：当月报告

**权限**：专业

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 5, "month": "2026-10",
    "overview": {"analysis_count": 8, "match_count": 12, "win_rate": 0.65, "training_days": 18},
    "trend_data": {"improving_metrics": ["backhand_ratio"], "declining_metrics": [], "stable_metrics": ["serve_variation"]},
    "achievements": {"badges_earned": ["streak_7"], "milestones": ["累计分析50次"]},
    "training_load": {"frequency_per_week": 4, "trend": "up", "correlation_r": 0.52, "advice": "训练量与积分提升呈中等正相关，维持当前节奏"},
    "forecast": {"backhand_ratio": {"predicted_weeks": 2, "confidence": "high", "r_squared": 0.82}},
    "advice": ["继续加强反手练习", "增加落点变化训练"]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 当月无报告 | 本月暂无报告 |

### 15.14 GET /monthly-report/{id}

**描述**：报告详情

**权限**：专业

#### Response Body

同 15.13

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 报告不存在 | 报告不存在 |

### 15.15 POST /monthly-report/{id}/export

**描述**：导出 PDF

**权限**：专业

#### Response Body

```json
{
  "code": 200, "message": "PDF 已生成",
  "data": {"download_url": "https://cdn.pingpongai.com/reports/pdf/5.pdf", "expire_at": "2026-10-10T13:00:00Z"},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 500 | PDF 生成失败 | PDF 生成失败，请稍后重试 |

### 15.16 GET /badges

**描述**：完整徽章列表

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "earned": [{"badge_id": "first_analysis", "name": "首分析", "icon": "📹", "category": "analysis", "earned_at": "2026-07-10"}],
    "locked": [{"badge_id": "streak_30", "name": "连续30天", "icon": "🌟", "category": "streak", "progress": 7, "target": 30, "condition": "连续打卡30天"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 15.17 GET /badges/progress

**描述**：徽章进度

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total_badges": 20, "earned_count": 5,
    "in_progress": [{"badge_id": "streak_30", "progress": 7, "target": 30, "percentage": 23}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

## 16. Phase 3 API 端点详细设计

### 16.1 GET /community/feed

**描述**：社区信息流（推荐/关注）

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| type | query | string | N | recommend/following，默认 recommend |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 50, "page": 1, "page_size": 20,
    "items": [{"id": 1, "type": "text", "title": "今天的训练心得", "author": {"id": 123, "nickname": "Eric", "avatar_url": "..."}, "like_count": 15, "comment_count": 3, "created_at": "2026-10-10T12:00:00Z"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.2 GET /community/posts/{id}

**描述**：帖子详情

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "type": "text", "title": "今天的训练心得",
    "content": {"text": "反手练习了50个多球...", "images": ["https://cdn.../img1.jpg"]},
    "tags": ["反手", "训练"],
    "author": {"id": 123, "nickname": "Eric", "avatar_url": "..."},
    "like_count": 15, "comment_count": 3, "view_count": 120,
    "is_liked": false, "is_collected": false,
    "created_at": "2026-10-10T12:00:00Z"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 帖子不存在 | 帖子不存在 |

### 16.3 POST /community/posts

**描述**：发布动态

**权限**：登录

#### Request Body

```json
{"type": "text", "title": "训练心得", "content": {"text": "...", "images": ["url"]}, "tags": ["反手"]}
```

#### Response Body

```json
{
  "code": 200, "message": "发布成功",
  "data": {"id": 1, "status": "pending"},
  "timestamp": "..."
}
```

#### 业务规则

1. 帖子发布后进入审核队列（自动审核 + 人工审核）

2. 敏感词命中 → 自动拒绝

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | 标题或内容为空 | 请填写帖子内容 |
| 400 | 敏感词命中 | 内容包含敏感词汇，请修改 |

### 16.4 POST /community/posts/{id}/like

**描述**：点赞/取消点赞

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {"is_liked": true, "like_count": 16},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 帖子不存在 | 帖子不存在 |

### 16.5 POST /community/posts/{id}/comments

**描述**：评论

**权限**：登录

#### Request Body

```json
{"content": "说得好！", "parent_id": null}
```

#### Response Body

```json
{
  "code": 200, "message": "评论成功",
  "data": {"id": 10, "content": "说得好！", "created_at": "2026-10-10T12:05:00Z"},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 帖子不存在 | 帖子不存在 |
| 422 | 内容为空 | 请填写评论内容 |

### 16.6 GET /community/questions

**描述**：问答列表

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 20, "page": 1, "page_size": 20,
    "items": [{"id": 1, "title": "反手拉球总是下网怎么办？", "answer_count": 3, "best_answer_id": 5, "view_count": 80, "created_at": "..."}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.7 POST /community/questions

**描述**：提问

**权限**：登录

#### Request Body

```json
{"title": "反手拉球总是下网怎么办？", "content": "引拍幅度...", "tags": ["反手", "拉球"]}
```

#### Response Body

```json
{
  "code": 200, "message": "提问成功",
  "data": {"id": 1},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | 标题为空 | 请填写问题标题 |

### 16.8 POST /community/questions/{id}/answers

**描述**：回答

**权限**：登录

#### Request Body

```json
{"content": "可能是引拍幅度不够..."}
```

#### Response Body

```json
{
  "code": 200, "message": "回答成功",
  "data": {"id": 5},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 问题不存在 | 问题不存在 |

### 16.9 POST /community/answers/{id}/accept

**描述**：采纳答案

**权限**：提问者

#### Response Body

```json
{
  "code": 200, "message": "已采纳",
  "data": {"answer_id": 5, "points_earned": 5},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 403 | 非提问者 | 只有提问者可以采纳答案 |
| 409 | 已有采纳答案 | 该问题已采纳答案 |

### 16.10 GET /learning-videos

**描述**：学习视频列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| category | query | string | N | 分类 |
| video_type | query | string | N | embed/authorized/ugc |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 15, "page": 1, "page_size": 20,
    "items": [{"id": 1, "title": "正手攻球教学", "video_type": "authorized", "duration": 180, "view_count": 500, "creator": {"id": 1, "name": "官方教学"}}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.11 GET /learning-videos/{id}

**描述**：视频详情

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "title": "正手攻球教学", "video_type": "authorized",
    "video_url": "https://cdn.../video.mp4", "duration": 180,
    "description": "...", "view_count": 500,
    "creator": {"id": 1, "name": "官方教学", "avatar_url": "..."}
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 视频不存在 | 视频不存在 |

### 16.12 GET /creator-center/overview

**描述**：创作者数据概览

**权限**：创作者

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total_revenue_cents": 50000, "available_balance_cents": 35000,
    "frozen_balance_cents": 5000, "total_views": 2000, "total_followers": 120,
    "video_count": 8
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 403 | 非创作者 | 请先申请成为创作者 |

### 16.13 POST /creator-center/videos

**描述**：上传视频

**权限**：创作者

#### Request Body

```json
{"title": "反手拉球进阶教学", "description": "...", "category": "BACKHAND", "price_cents": 500, "oss_key": "videos/ugc/..."}
```

#### Response Body

```json
{
  "code": 200, "message": "视频已提交，等待审核",
  "data": {"id": 10, "status": "pending"},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | 标题或 oss_key 为空 | 请填写视频信息 |

### 16.14 GET /creator-center/revenue

**描述**：收益记录

**权限**：创作者

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 20, "page": 1, "page_size": 20,
    "items": [{"id": 1, "video_id": 10, "amount_cents": 375, "type": "video_sale", "status": "settled", "created_at": "..."}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.15 POST /creator-center/withdrawals

**描述**：提现

**权限**：创作者

#### Request Body

```json
{"amount_cents": 10000}
```

#### Response Body

```json
{
  "code": 200, "message": "提现申请已提交",
  "data": {"id": 1, "amount_cents": 10000, "status": "processing"},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 提现金额 < 10000 | 最低提现金额为 100 元 |
| 400 | 余额不足 | 可用余额不足 |

### 16.16 GET /circles

**描述**：圈子列表

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 10, "page": 1, "page_size": 20,
    "items": [{"id": 1, "name": "反手技术交流圈", "member_count": 120, "icon_url": "...", "is_joined": false}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.17 POST /circles/{id}/join

**描述**：加入圈子

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "已加入圈子",
  "data": {"circle_id": 1, "member_count": 121},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 已加入 | 已加入该圈子 |

### 16.18 GET /leaderboard

**描述**：排行榜

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| type | query | string | Y | training/analysis/community |
| period | query | string | Y | weekly/monthly/all |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "type": "training", "period": "weekly",
    "rankings": [{"rank": 1, "user_id": 123, "nickname": "Eric", "avatar_url": "...", "score": 580, "change": 2}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.19 GET /coaches

**描述**：教练列表

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 5, "page": 1, "page_size": 20,
    "items": [{"id": 1, "name": "王教练", "qualification": "国家二级", "rating": 4.8, "student_count": 30, "services": [{"type": "online", "price_cents": 9900}]}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.20 GET /coaches/{id}

**描述**：教练详情

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "name": "王教练", "qualification": "国家二级", "teaching_years": 10,
    "rating": 4.8, "student_count": 30, "bio": "...",
    "services": [{"type": "online", "name": "线上指导", "price_cents": 9900, "description": "..."}],
    "reviews": [{"user_id": 123, "rating": 5, "content": "讲解很细致", "created_at": "..."}]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 教练不存在 | 教练不存在 |

### 16.21 POST /coaches/{id}/booking

**描述**：预约教练

**权限**：登录

#### Request Body

```json
{"service_type": "online", "preferred_time": "2026-10-15T10:00:00Z"}
```

#### Response Body

```json
{
  "code": 200, "message": "预约已创建",
  "data": {"order_id": 9001, "status": "pending", "price_cents": 9900},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 教练不存在 | 教练不存在 |

### 16.22 GET /play-dates

**描述**：约球列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| lat | query | float | N | 纬度 |
| lng | query | float | N | 经度 |
| radius_km | query | int | N | 搜索半径，默认 10 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 5, "page": 1, "page_size": 20,
    "items": [{"id": 1, "venue_name": "阳光球馆", "start_time": "2026-10-15T14:00:00Z", "end_time": "2026-10-15T16:00:00Z", "current_count": 3, "max_players": 4, "fee_cents": 0, "distance_km": 2.5, "organizer": {"id": 123, "nickname": "Eric"}}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.23 POST /play-dates

**描述**：发布约球

**权限**：登录

#### Request Body

```json
{"venue_id": 1, "start_time": "2026-10-15T14:00:00Z", "end_time": "2026-10-15T16:00:00Z", "max_players": 4, "rating_min": 1400, "rating_max": 1800, "fee_cents": 0, "note": "水平相近的来"}
```

#### Response Body

```json
{
  "code": 200, "message": "约球已发布",
  "data": {"id": 1, "status": "open", "current_count": 1},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | 时间为空或结束早于开始 | 请填写有效的约球时间 |

### 16.24 POST /play-dates/{id}/register

**描述**：报名约球

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "报名成功",
  "data": {"play_date_id": 1, "current_count": 4, "status": "full"},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 名额已满 | 约球名额已满 |

### 16.25 GET /venues

**描述**：球馆列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| lat | query | float | N | 纬度 |
| lng | query | float | N | 经度 |
| keyword | query | string | N | 关键词搜索 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 8, "page": 1, "page_size": 20,
    "items": [{"id": 1, "name": "阳光球馆", "address": "朝阳区...", "distance_km": 2.5, "price_hourly_cents": 5000, "table_count": 10, "rating": 4.5, "facilities": ["空调", "停车位"]}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 16.26 GET /venues/{id}

**描述**：球馆详情

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "name": "阳光球馆", "address": "朝阳区...", "phone": "010-12345678",
    "location": {"lat": 39.9, "lng": 116.4}, "price_hourly_cents": 5000, "table_count": 10,
    "rating": 4.5, "facilities": ["空调", "停车位", "淋浴"],
    "reviews": [{"user_id": 123, "rating": 5, "content": "环境很好", "created_at": "..."}]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 球馆不存在 | 球馆不存在 |

### 16.27 POST /venues/{id}/reviews

**描述**：球馆评价

**权限**：登录

#### Request Body

```json
{"rating": 5, "content": "环境很好，推荐"}
```

#### Response Body

```json
{
  "code": 200, "message": "评价已提交",
  "data": {"id": 1, "venue_rating_updated": 4.6},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | 评分为空或不在 1-5 | 请选择评分 |

---

## 17. Phase 4 API 端点详细设计

### 17.1 GET /tournaments

**描述**：赛事列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| level | query | string | N | 级别筛选 |
| status | query | string | N | 状态筛选 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 5, "page": 1, "page_size": 20,
    "items": [{"id": 1, "name": "2026秋季公开赛", "start_date": "2026-11-01", "end_date": "2026-11-03", "level": "city", "format": "knockout", "capacity": 64, "registered_count": 32, "status": "open", "fee_cents": 10000}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 17.2 GET /tournaments/{id}

**描述**：赛事详情

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "name": "2026秋季公开赛", "organizer": "朝阳区乒协",
    "venue": {"id": 1, "name": "阳光球馆", "address": "..."},
    "start_date": "2026-11-01", "end_date": "2026-11-03",
    "format": "knockout", "level": "city", "fee_cents": 10000,
    "capacity": 64, "registered_count": 32, "status": "open",
    "rules": "单败淘汰，每场 5 局 3 胜...",
    "kqs_event_id": "KQS_2026_001"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 赛事不存在 | 赛事不存在 |

### 17.3 POST /tournaments/{id}/register

**描述**：赛事报名

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "报名成功",
  "data": {"registration_id": 1, "status": "pending", "fee_cents": 10000, "order_id": 8001},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 名额已满 | 赛事名额已满 |
| 409 | 已报名 | 您已报名该赛事 |
| 403 | 信用分不足 | 信用分不足，无法报名赛事 |

### 17.4 GET /tournaments/{id}/results

**描述**：成绩查看

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "tournament_id": 1,
    "results": [{"user_id": 123, "nickname": "Eric", "rank": 1, "wins": 6, "losses": 0, "points_gained": 50}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 17.5 GET /rankings

**描述**：排名列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| scope | query | string | Y | national/provincial/city |
| gender | query | string | N | male/female |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "scope": "national", "period": "2026-W41",
    "rankings": [{"rank": 1, "user_id": 123, "nickname": "Eric", "rating": 1850, "change": 2}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 17.6 GET /rankings/me

**描述**：我的排名

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "national_rank": 150, "provincial_rank": 20, "city_rank": 5,
    "rating": 1550, "rating_change": 10
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 无排名数据 | 暂无排名数据 |

### 17.7 GET /activities

**描述**：活动列表

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 5, "page": 1, "page_size": 20,
    "items": [{"id": 1, "name": "周末球友聚会", "type": "casual", "venue_name": "阳光球馆", "start_time": "2026-10-15T14:00:00Z", "max_participants": 16, "current_count": 8, "team_mode": "snake", "status": "open"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 17.8 POST /activities

**描述**：创建活动

**权限**：登录

#### Request Body

```json
{"name": "周末球友聚会", "type": "casual", "venue_id": 1, "start_time": "2026-10-15T14:00:00Z", "end_time": "2026-10-15T18:00:00Z", "max_participants": 16, "fee_cents": 2000, "team_mode": "snake", "description": "蛇形分组赛后单败淘汰"}
```

#### Response Body

```json
{
  "code": 200, "message": "活动已创建",
  "data": {"id": 1, "status": "open"},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | 必填字段缺失 | 请填写活动信息 |

### 17.9 POST /activities/{id}/team-assignment

**描述**：智能组队

**权限**：活动创建者

#### Response Body

```json
{
  "code": 200, "message": "组队完成",
  "data": {
    "teams": [
      {"team_number": 1, "members": [{"user_id": 123, "nickname": "Eric", "rating": 1800}, {"user_id": 124, "nickname": "张三", "rating": 1500}]},
      {"team_number": 2, "members": [{"user_id": 125, "nickname": "李四", "rating": 1750}, {"user_id": 126, "nickname": "王五", "rating": 1550}]}
    ],
    "algorithm": "snake_assignment"
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 403 | 非创建者 | 只有活动创建者可以分组 |
| 400 | 报名人数不足 | 报名人数不足以分组 |

### 17.10 GET /equipment

**描述**：装备列表

**权限**：登录

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| category | query | string | N | blade/rubber/shoes/etc |
| brand | query | string | N | 品牌筛选 |
| page | query | int | N | 页码 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 50（见 §1.2） |

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 20, "page": 1, "page_size": 20,
    "items": [{"id": 1, "name": "蝴蝶 Viscaria", "brand": "蝴蝶", "category": "blade", "rating": 4.8, "review_count": 35, "suitable_styles": ["loop", "attack"]}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 17.11 GET /equipment/{id}

**描述**：装备详情

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "id": 1, "name": "蝴蝶 Viscaria", "brand": "蝴蝶", "category": "blade",
    "specs": {"composition": "ALC", "weight": 88, "thickness": 5.7},
    "price_cents": 128000, "image_url": "https://cdn.../viscaria.jpg",
    "suitable_styles": ["loop", "attack"], "rating": 4.8, "review_count": 35,
    "reviews": [{"user_id": 123, "rating": 5, "content": "控球很好", "created_at": "..."}]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 装备不存在 | 装备不存在 |

### 17.12 POST /equipment/{id}/reviews

**描述**：装备评测

**权限**：登录

#### Request Body

```json
{"rating": 5, "content": "控球很好，正手拉球稳定"}
```

#### Response Body

```json
{
  "code": 200, "message": "评测已提交",
  "data": {"id": 36, "equipment_rating_updated": 4.8},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 422 | 评分为空 | 请选择评分 |

### 17.13 GET /products

**描述**：商品列表

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 15, "page": 1, "page_size": 20,
    "items": [{"id": 1, "equipment_id": 1, "name": "蝴蝶 Viscaria 底板", "price_cents": 128000, "stock": 10, "status": "available", "sku": "BT-VIS-01"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 17.14 POST /orders

**描述**：创建商品订单

**权限**：登录

#### Request Body

```json
{"product_id": 1, "quantity": 1, "address": "北京市朝阳区..."}
```

#### Response Body

```json
{
  "code": 200, "message": "订单已创建",
  "data": {"order_id": 8010, "order_no": "PP202610100010", "amount_cents": 128000, "payment_params": {"prepay_id": "wx001", "pay_sign": "xxx"}},
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 库存不足 | 商品库存不足 |
| 404 | 商品不存在 | 商品不存在 |

### 17.15 GET /orders/{id}/shipment

**描述**：物流追踪

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "order_id": 8010, "tracking_no": "SF1234567890", "carrier": "顺丰速运",
    "status": "in_transit", "shipped_at": "2026-10-10T10:00:00Z",
    "estimated_delivery": "2026-10-12T18:00:00Z",
    "tracking_history": [{"time": "2026-10-10T10:00:00Z", "location": "北京", "status": "已发货"}, {"time": "2026-10-11T08:00:00Z", "location": "上海中转", "status": "运输中"}]
  },
  "timestamp": "..."
}
```

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 订单不存在 | 订单不存在 |
| 400 | 订单未发货 | 订单尚未发货 |

### 17.16 GET /credit-score

**描述**：信用分

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {"score": 85, "level": "良好", "rank_text": "信用良好，可正常参加赛事"},
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 17.17 GET /credit-score/records

**描述**：信用记录

**权限**：登录

#### Response Body

```json
{
  "code": 200, "message": "success",
  "data": {
    "total": 10, "page": 1, "page_size": 20,
    "items": [{"id": 1, "delta": 2, "reason": "按时参加赛事", "tournament_id": 1, "created_at": "..."}]
  },
  "timestamp": "..."
}
```

#### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

### 17.18 POST /users/kqs/bind

**描述**：绑定开球网

**权限**：登录

#### Request Body

```json
{"kqs_username": "eric_tt", "kqs_password": "xxx"}
```

#### Response Body

```json
{
  "code": 200, "message": "绑定成功",
  "data": {"kqs_username": "eric_tt", "kqs_rating": 1550},
  "timestamp": "..."
}
```

#### 业务规则

1. 调用开球网 API 验证账号

2. 验证成功 → 写入 user 表（含 kqs_rating 字段）+ kqs_rating_cache

3. 失败 → 降级为手动填写积分

#### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 400 | 开球网账号验证失败 | 开球网账号或密码错误 |
| 409 | 已绑定其他开球网账号 | 已绑定开球网账号，请先解绑 |
| 502 | 开球网 API 不可用 | 开球网服务暂时不可用，请稍后重试或手动填写 |

---

## 19. 管理后台 API (`/admin`)

> **来源**：admin 基础设施模块后端切片设计（`06垂直模块前后端切片设计/13-infrastructure/admin.md`）
> **Phase**：Phase 1 正式设计（架构 §4.1 已对齐，RBAC 角色守卫替代 Phase 守卫）
> **路由前缀**：`/api/v1/admin`
> **认证体系**：管理员独立认证，不复用普通用户 JWT
> **依据**：模块详细设计 v1.2 §3.5、数据库详细设计 v1.5 §2.31

### 19.1 认证说明

管理后台采用**独立认证体系**，与普通用户 JWT 体系完全隔离：

| 属性 | 说明 |
|------|------|
| 认证表 | `admin_user`（用户名 + bcrypt 密码哈希，`password_hash` 字段存储） |
| Session 存储 | Redis，Key 格式 `admin:session:{token}`，TTL 30 分钟（1800 秒） |
| 请求头格式 | `Authorization: Admin {session_token}` |
| Session 续期 | 每次请求命中 `get_current_admin` 时自动续期 30 分钟 |
| 认证依赖 | `get_current_admin`（所有管理端点） / `require_super_admin`（敏感操作） |
| 角色体系 | `super_admin`（超级管理员）/ `content_admin`（内容管理员）/ `model_admin`（模型管理员） |

> **不使用 JWT**：管理员 session 是随机生成的 opaque token（`secrets.token_urlsafe(32)`），存储在 Redis 中。与 JWT 的无状态特性不同，管理员 session 可随时主动失效（登出/禁用），适合管理后台低并发、高安全场景。

#### 管理后台权限标注

| 契约标注 | 含义 | 实现方式 |
|---------|------|---------|
| `管理员` | 任何已认证管理员 | `Depends(get_current_admin)` |
| `超级管理员` | super_admin 角色 | `Depends(require_super_admin)` |
| `公开` | 无需认证（仅 login 端点） | — |

#### 管理后台限流配置

| 端点 | 限流 | 说明 |
|------|------|------|
| POST /admin/login | 5/min | 登录端点严格限流，防暴力破解 |
| 其他管理端点 | 100/min | 统一管理后台限流 |

> 所有管理端点 **必须** 添加 `@limiter.limit()` 限流装饰器，且装饰器顺序 **必须** 为 `@router.xxx()` 在上、`@limiter.limit()` 紧随其下（slowapi 要求限流装饰器贴近路由函数；若 `@limiter.limit()` 放在 `@router.xxx()` 上方，路由表注册的将是未限流的原始函数，限流不生效——R12 已按此统一全 app 95 个端点的装饰器顺序）。

---

### 19.2 用户管理端点

#### 19.2.1 POST /admin/login

**描述**：管理员登录（用户名 + 密码，签发 Redis session，不使用 JWT）

**权限**：公开

**限流**：5/min

##### Request Body

```json
{
  "username": "admin",
  "password": "admin123"
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| username | string | Y | 管理员用户名（1-64 字符） |
| password | string | Y | 管理员密码（1-128 字符） |

##### Response Body

```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "session_token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
    "admin": {
      "id": 1,
      "username": "admin",
      "role": "super_admin"
    },
    "expires_in": 1800
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 查询 `admin_user` 表，校验用户名存在且 `is_active=true`
2. bcrypt 验证密码哈希（`bcrypt.checkpw`）
3. 生成随机 session token（`secrets.token_urlsafe(32)`），写入 Redis `admin:session:{token}` → `admin_id`，TTL 30min
4. 返回 session_token + 管理员信息（AdminBrief）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 401 | 用户名或密码错误 | 用户名或密码错误 |
| 403 | 管理员账号已禁用 | 管理员账号已禁用 |

#### 19.2.2 POST /admin/logout

**描述**：管理员登出（删除 Redis session）

**权限**：管理员

**限流**：100/min

##### Request Header

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| Authorization | header | string | Y | `Admin {session_token}` |

##### Response Body

```json
{
  "code": 200,
  "message": "登出成功",
  "data": null,
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 从 Authorization header 提取 session token（去掉 `Admin ` 前缀）
2. 删除 Redis `admin:session:{token}`

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 401 | session 已过期或无效 | 管理员 session 已过期，请重新登录 |
| 401 | 未携带 Admin 前缀 | 管理员认证失败 |

#### 19.2.3 GET /admin/users

**描述**：用户列表查询（支持状态筛选和关键词搜索）

**权限**：管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| status | query | string | N | 状态筛选（active / banned） |
| q | query | string | N | 关键词搜索（昵称 / 手机号模糊匹配） |
| page | query | int | N | 页码，默认 1，最小 1 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 100 |

##### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 58,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 123,
        "nickname": "Eric",
        "phone": "13800138888",
        "openid": "oXXXXXXXX",
        "status": "active",
        "created_at": "2026-07-10T10:00:00Z"
      }
    ]
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 按 `status` 筛选（可选），按 `q` 关键词模糊匹配 `nickname` / `phone`（可选）
2. 按 `created_at DESC` 排序
3. 分页返回 UserManageBrief 列表

##### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

#### 19.2.4 POST /admin/users/{user_id}/ban

**描述**：封禁用户（更新 user.status='banned'，写入审计日志）

**权限**：超级管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| user_id | path | int | Y | 用户 ID |

##### Request Body

```json
{
  "reason": "违规操作"
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| reason | string | Y | 封禁原因（1-500 字符） |

##### Response Body

```json
{
  "code": 200,
  "message": "用户已封禁",
  "data": {
    "user_id": 123,
    "status": "banned",
    "reason": "违规操作"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验用户存在且当前状态为 `active`（非 banned）
2. 更新 `user.status='banned'`
3. 写入 `audit_log`（action=update, target_type=user, target_id=user_id, changes={status:{old:active,new:banned}, ban_reason:{old:null,new:reason}}）
4. 审计日志写入失败不阻塞主操作（记录错误日志后继续）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 用户不存在 | 用户不存在 |
| 409 | 用户已被封禁 | 用户已被封禁 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

#### 19.2.5 POST /admin/users/{user_id}/unban

**描述**：解禁用户（更新 user.status='active'，写入审计日志）

**权限**：超级管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| user_id | path | int | Y | 用户 ID |

##### Response Body

```json
{
  "code": 200,
  "message": "用户已解禁",
  "data": {
    "user_id": 123,
    "status": "active"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验用户存在且当前状态为 `banned`
2. 更新 `user.status='active'`
3. 写入 `audit_log`（action=update, target_type=user, target_id=user_id, changes={status:{old:banned,new:active}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 用户不存在 | 用户不存在 |
| 409 | 用户未被封禁 | 用户未被封禁 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

---

### 19.3 系统配置端点

#### 19.3.1 GET /admin/configs

**描述**：查询所有系统配置（按 config_key 排序）

**权限**：管理员

**限流**：100/min

##### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 1,
      "config_key": "analysis_free_daily_limit",
      "config_value": 3,
      "description": "免费分析每日额度",
      "updated_at": "2026-10-01T00:00:00Z"
    }
  ],
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

#### 19.3.2 GET /admin/configs/{key}

**描述**：查询单个配置（Redis 缓存优先，未命中回填）

**权限**：管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| key | path | string | Y | 配置键名 |

##### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "config_key": "analysis_free_daily_limit",
    "config_value": 3,
    "description": "免费分析每日额度",
    "updated_at": "2026-10-01T00:00:00Z"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 先查 Redis 缓存 `config:{key}`，命中则直接返回（id=0 占位，description=null）
2. 未命中查 `system_config` 表，回填 Redis 缓存（TTL 3600s / 1h）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 配置不存在 | 配置 {key} 不存在 |

#### 19.3.3 POST /admin/configs

**描述**：创建系统配置

**权限**：超级管理员

**限流**：100/min

##### Request Body

```json
{
  "config_key": "max_upload_size_mb",
  "config_value": 500,
  "description": "最大上传视频大小（MB）"
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| config_key | string | Y | 配置键名（1-64 字符，唯一） |
| config_value | any | Y | 配置值（JSONB 格式，支持任意类型） |
| description | string | N | 配置描述 |

##### Response Body

```json
{
  "code": 200,
  "message": "配置已创建",
  "data": {
    "id": 2,
    "config_key": "max_upload_size_mb",
    "config_value": 500,
    "description": "最大上传视频大小（MB）",
    "updated_at": "2026-10-10T12:00:00.000000Z"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验 config_key 不重复
2. 写入 `system_config` 表
3. 写入 `audit_log`（action=create, target_type=config, changes={config_key:{old:null,new:key}, config_value:{old:null,new:value}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 配置键已存在 | 配置 {config_key} 已存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

#### 19.3.4 PATCH /admin/configs/{key}

**描述**：更新系统配置（修改后清除 Redis 缓存实现热更新）

**权限**：超级管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| key | path | string | Y | 配置键名 |

##### Request Body

```json
{
  "config_value": 5,
  "description": "免费分析每日额度（已调整）"
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| config_value | any | Y | 新配置值 |
| description | string | N | 新描述（不传则不修改） |

##### Response Body

```json
{
  "code": 200,
  "message": "配置已更新，缓存已刷新",
  "data": {
    "id": 1,
    "config_key": "analysis_free_daily_limit",
    "config_value": 5,
    "description": "免费分析每日额度（已调整）",
    "updated_at": "2026-10-10T12:00:00.000000Z"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验配置存在
2. 更新 `system_config.config_value` 和 `description`（可选，传入才修改）
3. 清除 Redis 缓存 `DEL config:{key}` 实现热更新
4. 写入 `audit_log`（action=update, target_type=config, changes={config_value:{old,new}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 配置不存在 | 配置 {key} 不存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

#### 19.3.5 DELETE /admin/configs/{key}

**描述**：删除系统配置

**权限**：超级管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| key | path | string | Y | 配置键名 |

##### Response Body

```json
{
  "code": 200,
  "message": "配置已删除",
  "data": null,
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验配置存在
2. 删除 `system_config` 记录
3. 清除 Redis 缓存 `DEL config:{key}`
4. 写入 `audit_log`（action=delete, target_type=config, changes={config_key:{old:key,new:null}, config_value:{old:value,new:null}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 配置不存在 | 配置 {key} 不存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

---

### 19.4 审计日志端点

#### 19.4.1 GET /admin/audit-logs

**描述**：审计日志查询（按管理员 / 操作类型 / 目标类型 / 时间范围筛选）

**权限**：管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| admin_id | query | int | N | 管理员 ID 筛选 |
| action | query | string | N | 操作类型筛选（create / update / delete / publish / reject / payment_order_created / payment_callback_processed / payment_refunded / subscription_created_or_renewed） |
| target_type | query | string | N | 目标类型筛选（user / report / video / model / config / knowledge / order / subscription） |
| start_date | query | string | N | 起始日期（YYYY-MM-DD） |
| end_date | query | string | N | 结束日期（YYYY-MM-DD） |
| page | query | int | N | 页码，默认 1，最小 1 |
| page_size | query | int | N | 每页条数，默认 20，最小 1，最大 100 |

##### Response Body

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 30,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "id": 1,
        "admin_id": 1,
        "admin_username": "admin",
        "action": "update",
        "target_type": "user",
        "target_id": 123,
        "changes": {
          "status": {"old": "active", "new": "banned"},
          "ban_reason": {"old": null, "new": "违规操作"}
        },
        "created_at": "2026-10-10T12:00:00Z"
      }
    ]
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 按筛选条件分页查询 `audit_log` 表，按 `created_at DESC` 排序
2. 关联查询 `admin_user` 表批量填充 `admin_username` 字段（避免 N+1 查询）
3. 审计日志自动清理：Celery Beat 定时任务（`audit.cleanup_old_logs`）每日 03:00 执行，清理 3 年前的记录（PIPL 合规保留 3 年），幂等设计基于 WHERE 条件删除

##### 错误情况

> 通用错误码见 §1.7，无额外业务错误码。

---

### 19.5 知识库管理端点

#### 19.5.1 POST /admin/knowledge/categories

**描述**：创建知识库分类

**权限**：超级管理员

**限流**：100/min

##### Request Body

```json
{
  "name": "正手技术",
  "code": "forehand",
  "content": {"description": "正手相关技术知识"}
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| name | string | Y | 分类名称（1-64 字符） |
| code | string | Y | 分类编码（1-32 字符，唯一） |
| content | object | Y | 分类内容（JSONB 格式） |

##### Response Body

```json
{
  "code": 200,
  "message": "分类已创建",
  "data": {
    "id": 1,
    "name": "正手技术",
    "code": "forehand"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验 code 不重复
2. 写入 `knowledge_category` 表
3. 写入 `audit_log`（action=create, target_type=knowledge, changes={code:{old:null,new:code}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 分类编码已存在 | 分类编码 {code} 已存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

#### 19.5.2 PATCH /admin/knowledge/categories/{category_id}

**描述**：更新知识库分类

**权限**：超级管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| category_id | path | int | Y | 分类 ID |

##### Request Body

```json
{
  "name": "正手技术（更新）",
  "content": {"description": "更新后的描述"}
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| name | string | N | 新分类名称（1-64 字符，不传则不修改） |
| content | object | N | 新分类内容（JSONB 格式，不传则不修改） |

##### Response Body

```json
{
  "code": 200,
  "message": "分类已更新",
  "data": {
    "id": 1,
    "name": "正手技术（更新）",
    "code": "forehand"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验分类存在
2. 按传入字段部分更新（name / content 可选，仅传入字段才修改）
3. 写入 `audit_log`（action=update, target_type=knowledge, changes=实际修改字段的 {old,new} 字典）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 分类不存在 | 分类不存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

#### 19.5.3 DELETE /admin/knowledge/categories/{category_id}

**描述**：删除知识库分类（级联删除关联条目）

**权限**：超级管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| category_id | path | int | Y | 分类 ID |

##### Response Body

```json
{
  "code": 200,
  "message": "分类已删除",
  "data": null,
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验分类存在
2. 删除分类记录（级联删除关联的知识条目）
3. 写入 `audit_log`（action=delete, target_type=knowledge, changes={code:{old:code,new:null}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 分类不存在 | 分类不存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

#### 19.5.4 POST /admin/knowledge/rules

**描述**：创建规则定义（诊断规则 + 训练方法 + 训练计划模板）

**权限**：超级管理员

**限流**：100/min

##### Request Body

```json
{
  "rule_id": "R001",
  "rule_name": "正手拉球成功率低",
  "rule_type": "technique",
  "condition": {"metric": "forehand_drive_success_rate", "operator": "<", "threshold": 0.5},
  "diagnosis": {"summary": "正手拉球成功率低于50%", "severity": "medium"},
  "training_methods": ["多球练习", "慢动作分解"],
  "training_plan_template": "反手提升方案模板",
  "adjustment_action": "increase_forehand_training"
}
```

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| rule_id | string | Y | 规则 ID（1-64 字符，唯一） |
| rule_name | string | Y | 规则名称（1-128 字符） |
| rule_type | string | Y | 规则类型（1-32 字符） |
| condition | object | Y | 触发条件（JSONB 格式，含 metric/operator/threshold） |
| diagnosis | object | Y | 诊断结论（JSONB 格式，含 summary/severity） |
| training_methods | array | N | 训练方法列表 |
| training_plan_template | string | N | 训练计划模板引用 |
| adjustment_action | string | N | 调整动作标识 |

##### Response Body

```json
{
  "code": 200,
  "message": "规则已创建",
  "data": {
    "id": 1,
    "rule_id": "R001"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验 rule_id 不重复
2. 写入 `rule_definition` 表（含 condition / diagnosis / training_methods / training_plan_template / adjustment_action 字段）
3. 写入 `audit_log`（action=create, target_type=knowledge, changes={rule_id:{old:null,new:rule_id}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 409 | 规则 ID 已存在 | 规则 {rule_id} 已存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

#### 19.5.5 PATCH /admin/knowledge/rules/{rule_id}/toggle

**描述**：启用 / 禁用规则

**权限**：超级管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| rule_id | path | int | Y | 规则数据库 ID |
| is_active | query | boolean | Y | 目标状态（true=启用，false=禁用） |

##### Response Body

```json
{
  "code": 200,
  "message": "规则状态已更新",
  "data": {
    "id": 1,
    "is_active": false
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验规则存在（按数据库 ID 查询）
2. 更新 `rule_definition.is_active` 字段
3. 写入 `audit_log`（action=update, target_type=knowledge, changes={is_active:{old,new}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 规则不存在 | 规则不存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

---

### 19.6 模型版本管理端点（Phase 2+）

> Phase 2+ 模型版本切换功能，Phase 1 仅预留设计占位，不实现端点代码。admin 切片中已声明"模型版本管理：Phase 2+ 模型版本切换"为预留功能。

#### 19.6.1 POST /admin/model-versions/{version_id}/activate

**描述**：激活指定 AI 模型版本（切换线上推理使用的模型版本）

**权限**：超级管理员

**限流**：100/min

##### 请求参数

| 参数 | 位置 | 类型 | 必填 | 描述 |
|------|------|------|------|------|
| version_id | path | int | Y | 模型版本 ID |

##### Response Body

```json
{
  "code": 200,
  "message": "模型版本已激活",
  "data": {
    "version_id": 2,
    "model_name": "pingpong-analysis-v2",
    "status": "active",
    "activated_at": "2026-10-10T12:00:00Z"
  },
  "timestamp": "2026-10-10T12:00:00.000000Z"
}
```

##### 业务规则

1. 校验模型版本存在
2. 将当前活跃版本状态改为 `archived`，目标版本状态改为 `active`
3. 清除推理服务模型缓存，触发热加载
4. 写入 `audit_log`（action=update, target_type=model, changes={status:{old,new}}）

##### 错误情况

| HTTP | 条件 | 消息 |
|------|------|------|
| 404 | 模型版本不存在 | 模型版本不存在 |
| 403 | 非超级管理员 | 需要超级管理员权限 |

---

## 20. 跨文档偏差说明

> 以下为详细设计与架构 v2.4 之间的已知偏差，已在详细设计中做了合理修正，架构文档应在后续同步更新。
| 编号 | 偏差项 | 架构 v2.4 | 详细设计 v1.2 | 修正理由 |
|------|--------|----------|-------------|---------|
| D-1 | 用户更新 HTTP 方法 | §5.7 列 `PUT /users/profile` 和 `PUT /users/rating` | 改为 `PATCH /users/profile` 和 `PATCH /users/rating` | PATCH 语义为部分更新，更符合实际场景（用户可能只修改昵称或积分，非全量替换） |
| D-2 | match_data 端点 | §5.7 API 清单未列出 match_data 的 3 个端点 | 详细设计有 3 个端点：POST /match-data/records, GET /match-data/records, GET /match-data/records/{id} | match_data 是架构 §4.1 定义的独立 Phase 1 模块，API 清单遗漏需补充 |
| D-3 | 用户注销端点 | §11.4 PIPL 合规表提到"注销 72h 删个人信息" | 新增 DELETE /users/account + 72h 冷静期 + 数据级联处理 | 架构描述了规则但未定义 API 端点，详细设计补全 |
| D-4 | 反馈历史端点 | 无 | 新增 GET /video-analysis/reports/{id}/feedbacks | 前端需展示用户已提交的反馈历史 |
| D-5 | 首页训练建议摘要 | 无 | GET /dashboard/overview 增加 latest_advice_summary 字段 | 前端 H1.1 首页训练提醒卡片需要数据来源 |
| D-6 | training 路径命名统一 | 无 | Phase 1 和 Phase 2 统一使用复数 `/training/plans/` | 原 Phase 1 用单数 plan，Phase 2 用复数 plans，统一为复数 |
| D-7 | 数据导出 API 契约 | 架构 §11.4 描述 PIPL 数据可携带权 | 新增 POST /users/export-data + GET /users/export-data/{task_id} | 架构描述了规则但未定义 API 端点，详细设计补全 |

---

## 18. 反幻觉约束

### 响应约束

- ALL 端点返回值 MUST 通过 `success()` 包装，NEVER 返回裸 dict/list
- ALL 列表端点 MUST 使用分页结构 `{total, page, page_size, items}`
- NEVER 手动构造 `{code, message}` 错误响应，使用 `raise AppException()`

### 参数约束

- ALL 变更类端点（POST/PUT/PATCH/DELETE）MUST 接受 `user: User = Depends(get_current_user)`
- 分页参数 MUST 使用 `Query(default=..., ge=1)` 校验
- NEVER 在路由函数中直接操作数据库，ALL 业务逻辑委托给 Service 层

### 权限约束

- 权限校验 MUST 在 Service 层完成
- 路由层只注入 `get_current_user`
- NEVER 跳过权限检查

### HTTP 方法约束

- GET = 读取，NEVER 有副作用
- POST = 创建 / 批量操作 / 状态流转
- PATCH = 部分更新
- PUT = 全量替换
- DELETE = 删除
- NEVER 用 GET 执行写操作

### 导入约束

- API 文件只导入：`fastapi`, `deps`, `response.success`, Schemas, Service, `User` model
- NEVER 在 api.py 中导入 SQLAlchemy Model 进行直接查询
- NEVER 在 api.py 中定义 Pydantic Schema（放 schemas.py）
- NEVER 在 api.py 中编写业务逻辑（放 *_service.py）

### 路由注册约束

- 每个子模块使用 `APIRouter(prefix="/xxx", tags=["中文标签"])`
- 聚合路由在 `app/api/v1/__init__.py` 中通过 `include_router` 挂载
- 所有路由最终挂载到 `/api/v1` 前缀下