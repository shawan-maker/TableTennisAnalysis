# R22 — API 端点级 + 前后端契约完整性审查报告

> **审查代理**：第二十二轮 API 端点级 + 前后端契约完整性维度
> **审查日期**：2026-10-19
> **工作目录**：D:\PyProject\TableTennisAnalysis
> **审查基线**：R21-API 端点级审查报告（2026-10-19）+ API 设计 v1.3 + 架构 §5.7（L804-958）+ 12 后端切片 + 13 前端切片
> **目标**：连续两轮无 P2+（新第一轮）— 验证 R21 3 项 API 维度 P2+ 修复回归 + 96 端点三方契约完整性

---

## 1. 审查范围与执行摘要

### 1.1 审查清单（8 项）

| 序号 | 文件 | 用途 |
|------|------|------|
| 1 | `docs/04详细设计/05-API详细设计.md`（5215 行） | API 设计 v1.3，端点权威源 |
| 2 | `docs/03系统架构/01-系统架构设计.md` §5.7（L804-958） | Phase 1 核心 API 端点清单 |
| 3 | `docs/06垂直模块前后端切片设计/01-auth/backend.md` | 认证切片后端（LoginResponse L217-222、wechat_login L325-340、phone_login L343-374、check_consent L463-483、路由 L587-679） |
| 4 | `docs/06垂直模块前后端切片设计/01-auth/frontend.md` | 认证切片前端（wechatLogin L162-185、phoneLogin L187-210、checkConsentStatus L276-286、ConsentPage L785-870） |
| 5 | `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` | 训练切片后端（TrainingSessionBrief L481-493、TrainingSessionCompleteResponse L506-514、Service L1038-1083 + L1085-1155、路由 L1273-1301） |
| 6 | `docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` | 训练切片前端（TrainingSessionItem L112-123、CompleteSessionData L134-139、训练方案详情页 L1101-1210） |
| 7 | `docs/07审查报告/第二十一轮/R21-API端点级审查报告.md` | R21 基线（3 项 P2+：P1×1 + P2×2 + P3×1） |
| 8 | grep `requires_consent|consented|needs_consent` + `session_index|reps` + `plan_progress` | 字段映射与类型一致性 |

### 1.2 执行摘要

本轮审查聚焦 R21 3 项 API 维度 P2+ 修复回归验证（R21-P1-1 / R21-P2-1 / R21-P2-2）+ 96 端点三方契约完整性 + consent 链路 + 训练单契约 + model_validate/限流/分页参数/安全性。**核心一致性维度维持，但发现 1 项新 P1**：

- **R21 3 项 P2+ 修复回归通过率**：3/3 完全闭环 ✅（R21-P1-1 wechatLogin/phoneLogin 字段名 `consented`→`requires_consent` ✅；R21-P2-1 训练单 Brief 补 `session_index`+`reps` ✅；R21-P2-2 `plan_progress` 类型 `float`→`int 0-100` ✅）
- **新发现**：P1×1 + P3×1（遗留）= **1 项 P2+ + 1 项 P3 遗留**
- **新发现归因**：1 项 P1 为 R21-P1-1 修复暴露的 "phone_login 后端 Service 未计算/注入 `requires_consent`" 问题（R21 报告 L324 误判"phone_login 复用 LoginResponse，同样返回 requires_consent"，实际未计算 → 衍生 R22-P1-1）；1 项 P3 为 R21-P3-1（§8.7 sessions 路由 page_size Query 缺 `ge=1`）遗留未修
- **目标达成状态**：⚠️ **API 维度连续第一轮无 P2+ 目标未达成**（R22 含 P1×1 新发现）。R21 3 项 P2+ 全部完全闭环，但 R21-P1-1 修复暴露了 phone_login 后端 Service 缺 `requires_consent` 计算的契约缺口

### 1.3 关键统计

| 审查项 | R21 基线 | R22 现状 | 变化 |
|--------|---------|---------|------|
| 新发现 P0 | 0 | 0 | 持平 |
| 新发现 P1 | 1 | 1 | 持平（R21-P1-1 修复暴露衍生 R22-P1-1） |
| 新发现 P2 | 2 | 0 | -2 ✅ |
| 新发现 P3 | 1 | 1（R21-P3-1 遗留未修） | 持平 |
| 新发现合计 | 4 | 2（1 新 P1 + 1 遗留 P3） | -2 |
| R21 修复回归通过率 | — | 3/3 完全闭环（100%） | — |
| 连续两轮无 P2+ 目标 | 第一轮未达成 | 第一轮仍未达成（含 1 项 P1） | 持平 |

---

## 2. R21 修复回归验证表（3 项 P2+）

R21-API 端点级报告共 4 项发现（P1×1 + P2×2 + P3×1），本轮聚焦 3 项 P2+（P1×1 + P2×2）回归验证：

| 序号 | R21 编号 | R21 修复项 | R22 状态 | 验证详情 |
|------|---------|-----------|---------|---------|
| 1 | R21-P1-1 | wechatLogin/phoneLogin 字段名 `consented` → `requires_consent`（极性 true=需同意） | ✅ **已修复** | (a) **前端 wechatLogin**（`01-auth/frontend.md` L168）：`const { access_token, refresh_token, user, requires_consent } = res.data.data` ✅ 正确读取 `requires_consent`；L174 `user: { ...user, needs_consent: requires_consent }` ✅ 极性一致；L177-180 `if (requires_consent) { Taro.navigateTo('/pages/auth/consent/index'); return }` ✅ 极性正确（true=需同意→跳转）。(b) **前端 phoneLogin**（L193）：同样 `const { ..., requires_consent } = res.data.data` ✅；L199 `needs_consent: requires_consent` ✅；L202-205 `if (requires_consent) { navigateTo consent; return }` ✅。(c) **前端 checkConsentStatus**（L279）：保持读 `consented` 字段（API §2.10 L497 返回 `consented: true`，极性 true=已同意）✅；L281 `needs_consent = !consented` ✅ 极性反转正确。(d) **store 内统一字段** `needs_consent`（L133）：wechatLogin/phoneLogin=requires_consent（同极性）+ checkConsentStatus=!consented（反极性）✅。(e) **L126-132 注释** 明确说明 login 端点返回 requires_consent（true=需同意）、consent-status 端点返回 consented（true=已同意）极性相反但各自正确 ✅。(f) **L568 路由注释** + **L789 触发条件注释** 同步更新，说明 requires_consent=true 时跳转 ✅。**但 R21-P1-1 修复暴露 phone_login 后端 Service 缺 `requires_consent` 计算问题**（详见 R22-P1-1） |
| 2 | R21-P2-1 | 训练单 Brief 补 `session_index` + `reps` 字段（API §8.7 L2389/L2391 对齐） | ✅ **已修复** | (a) **后端 TrainingSessionBrief Schema**（`07-training_advice/backend.md` L491-492）：`session_index: int = Field(..., description="训练单序号（从1开始）")` + `reps: int = Field(..., description="建议训练次数")` ✅；L490 注释 "R21-P2-1: 补 session_index/reps 与 API §8.7 L2388-2394 对齐"。(b) **后端 Service list_training_sessions**（L1065-1066）：`session_index=s.get("session_index", i + 1)`（默认从 1 开始）+ `reps=s.get("reps", 0)` ✅；L1056 注释 "R21-P2-1: 补 session_index/reps 与 API §8.7 对齐"。(c) **前端 TrainingSessionItem interface**（`07-training_advice/frontend.md` L121-122）：`session_index: number  // 训练单序号（从1开始）` + `reps: number  // 建议训练次数` ✅；L120 注释 "R21-P2-1: 补 session_index/reps 与 API §8.7 L2388-2394 对齐"。(d) **前端 UI 渲染**（L1155-1156 + L1168-1171）：`<Text className="session-index">#{session.session_index}</Text>` + `<Text className="session-reps">{t('training.reps')}: {session.reps}</Text>` ✅；L1155/L1168 注释 "R21-P2-1: 显示 session_index/reps"。**四方完全对齐：API §8.7 L2388-2394 ↔ 后端 Schema L491-492 ↔ 后端 Service L1065-1066 ↔ 前端 interface L121-122 ↔ 前端 UI L1156/L1170** ✅ |
| 3 | R21-P2-2 | `plan_progress` 类型 `float 0.0-1.0` → `int 0-100` 百分比（API §8.8 L2423 对齐） | ✅ **已修复** | (a) **后端 TrainingSessionCompleteResponse Schema**（`07-training_advice/backend.md` L511-512）：`# R21-P2-2: plan_progress 类型 int 0-100 与 API §8.8 L2423 对齐` + `plan_progress: int = Field(..., description="计划完成进度（0-100 百分比）")` ✅（原 float 改为 int）。(b) **后端 Service complete_training_session**（L1151-1152）：`# R21-P2-2: plan_progress 类型 int 0-100 与 API §8.8 L2423 对齐（float 0.0-1.0 → int 百分比）` + `plan_progress=int(plan_progress * 100)` ✅（执行 float→int 转换）。(c) **前端 CompleteSessionData interface**（`07-training_advice/frontend.md` L137）：`plan_progress: number  // 0-100` ✅（与 API §8.8 L2423 + 后端 int 类型一致）。**三方完全对齐：API §8.8 L2423 `"plan_progress": 70`（int 0-100）↔ 后端 Schema L512 `int` ↔ 后端 Service L1152 `int(plan_progress * 100)` ↔ 前端 interface L137 `number  // 0-100`** ✅ |

### 2.1 附加维度验证（R21 P3 项）

| R21 编号 | R21 修复项 | R22 状态 | 验证详情 |
|---------|-----------|---------|---------|
| R21-P3-1 | §8.7 sessions 路由 page_size Query 补 `ge=1` | ❌ **未修复** | `07-training_advice/backend.md` L1278 仍为 `page_size: int = Query(20, le=50)` ✗ 缺 `ge=1`；对比 L1232 §8.3 templates `page_size: int = Query(default=20, ge=1, le=50)` ✅。违反 API §1.2 L46 + L5974 "分页参数 MUST 使用 `Query(default=..., ge=1)` 校验"。P3 级遗留，不影响"无 P2+"目标但需在 R23 跟踪修复 |

**R21 3 项 P2+ 修复通过率**：3/3 完全闭环（100%）✅；**R21 P3 遗留**：1 项未修复

---

## 3. 96 端点完整性（79 业务 + 17 admin）

### 3.1 Phase 1 业务端点（79 个）

#### 认证模块 `/auth`（10 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /auth/wechat-login | POST | L588 | ✅ | ✅ 后端 wechat_login L325-340 正确计算并返回 requires_consent；前端 L168 正确读取 |
| 2 | /auth/phone-login | POST | L594 | ✅ | ❌ 见 R22-P1-1（后端 phone_login L343-374 未计算 requires_consent，恒为 False 默认值） |
| 3 | /auth/send-sms | POST | L600 | ✅ | ✅ |
| 4 | /auth/refresh | POST | L606 | ✅ | ✅ |
| 5 | /auth/logout | POST | L612 | ✅ | ✅ |
| 6 | /auth/me | GET | L626 | ✅ | ✅ |
| 7 | /auth/h5-token | POST | L643 | ✅ | ✅ |
| 8 | /auth/h5-exchange | POST | L649 | ✅ | ✅（R19-P1-1 修复后限流 10/min） |
| 9 | /auth/consent | POST | L656 | ✅ | ✅（R20-P1-3 同意页已实现） |
| 10 | /auth/consent-status | GET | L675 | ✅ | ✅（R20-P1-2 字段映射正确，L279 读 consented） |

#### 用户模块 `/users`（9 端点，不含 §3.7 跨模块）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-9 | §3.1-3.6 + §3.8-3.10 | GET/PATCH/POST/DELETE | L811-841 等 | ✅ | ✅ |

#### 视频分析模块 `/video-analysis`（12 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-12 | §4.1-4.12（含 §3.7 反馈历史跨模块） | GET/POST/DELETE | L1157-1268 | ✅ | ✅ |

#### 记分牌模块 `/scoring`（5 端点 §5.1-5.5 主端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-5 | §5.1-5.5 | GET/POST | L1148-1180 | ✅ | ✅ |

#### 比赛数据模块 `/matches`（5 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-5 | §6.1-6.5 | GET/POST/PUT/DELETE | L927-945 | ✅ | ✅ |

#### 数据看板模块 `/dashboard`（6 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-6 | §7.1-7.6 | GET | L806-825 | ✅ | ✅ |

#### 训练建议模块 `/training`（8 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-6 | §8.1-8.6 | GET/POST | L1185-1232 | ✅ | ✅ |
| 7 | §8.7 GET /training/plans/{plan_id}/sessions | GET | L1273-1287 | ✅ | ⚠️ R21-P2-1 ✅ 修复（session_index/reps 已补），R21-P3-1 ❌ 遗留（page_size 缺 ge=1） |
| 8 | §8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete | POST | L1290-1301 | ✅ | ✅ R21-P2-2 已修复（plan_progress=int 0-100） |

#### 进度分析模块 `/progress`（5 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-5 | §9.1-9.5 | GET | L1368-1390 | ✅ | ✅ |

#### 游戏化模块 `/gamification`（6 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-6 | §10.1-10.6 | GET/POST | L1085-1110 | ✅ | ✅ |

#### 会员模块 `/membership`（3 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-3 | §11.1-11.3 | GET | L801-825 | ✅ | ✅ |

#### 支付模块 `/payment`（4 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-4 | §12.1-12.4 | GET/POST | L1341-1415 | ✅ | ✅（notify 无 @limiter，SEC-006 豁免） |

#### 通知模块 `/notification`（6 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-6 | §13.1-13.6 | GET/POST/PUT | L644-690 | ✅ | ✅ |

### 3.2 管理后台 admin（17 端点）

| # | API 设计路径 | 方法 | 切片路径 | 权限守卫 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-2 | /admin/login、/admin/logout | POST | L872/L878 | — / `get_current_admin` | ✅ |
| 3-4 | /admin/users/ban、/admin/users/unban | POST | L886/L893 | `get_current_admin` | ✅ |
| 5-8 | /admin/configs（GET/POST/PUT/DELETE） | 4 methods | L915-945 | `get_current_admin` | ✅ |
| 9 | /admin/users（列表） | GET | L900 | `get_current_admin` | ✅ |
| 10 | /admin/audit-logs | GET | L990 | `get_current_admin` | ✅ |
| 11-17 | /admin/knowledge/categories（CRUD） + /admin/knowledge/rules（CRUD） | 7 endpoints | L1000-1058 | `require_super_admin` | ✅ |

**Admin 17 端点 page_size 约束**：`Query(default=20, ge=1, le=100)` ✅（L900 / L990）

### 3.3 端点完整性结论

- **路径/方法/参数/权限/限流三方一致**：95/96 ✅（R21 基线 93/96 ✅ → R22 95/96 ✅，R21-P1-1 + R21-P2-1 + R21-P2-2 修复后端点契约对齐，§2.1 wechat-login + §8.7/§8.8 训练单由 ⚠️/❌ 变为 ✅；但 §2.2 phone-login 因 R22-P1-1 新发现变为 ❌）
- **§2.2 phone-login 端点**：1/96 ❌（详见 R22-P1-1，后端 Service 未计算 requires_consent）
- **§8.7 sessions 端点**：1/96 ⚠️（R21-P3-1 遗留 page_size 缺 ge=1，P3 级）
- **96 端点完整性维持率**：98.9%（95/96 完全一致，含 §8.7 仅 P3 级风格不一致则为 96.9%）

---

## 4. 三方契约一致性

### 4.1 API § vs 架构 §5.7 vs 切片 @router

**结论**：✅ 通过（96 端点路径/方法/权限标注三方一致）

- 架构 §5.7 L804-958 明确列出 Phase 1 全部 96 个端点（79 业务 + 17 admin），与 API 设计 v1.3 和切片 @router 装饰器路径、HTTP 方法、权限守卫完全一致。
- 认证模块 10 端点：架构 L814-823 ↔ 切片 L588-675 ↔ API §2.1-2.10 一致 ✅
- 训练模块 8 端点：架构 L939-946 ↔ 切片 L1208-1301 ↔ API §8.1-8.8 一致 ✅
- R19-P1-1 修复后 `POST /auth/h5-exchange` 限流 10/minute 在 API §1.5 / 切片 L648 一致。

### 4.2 请求参数验证完整性（Pydantic Schema vs API 参数表）

**结论**：⚠️ 部分通过（含 R21-P3-1 遗留）

- 95/96 端点 Pydantic Schema 与 API 参数表完全一致。
- **§8.7 GET /training/plans/{plan_id}/sessions**：API §8.7 L2373-2374 声明 `page` 和 `page_size` 查询参数（默认 20，最小 1，最大 50）。R21-P1-1 修复后切片 L1277-1278 已补 `page: int = Query(1, ge=1)` + `page_size: int = Query(20, le=50)`，但 `page_size` Query **缺失 `ge=1` 约束**（R21-P3-1 遗留），与同切片 L1232 `Query(default=20, ge=1, le=50)` 风格不一致。

### 4.3 响应 Schema 字段一致性

**结论**：⚠️ 部分通过（含 R22-P1-1 新发现）

- 94/96 端点响应 Schema 字段在 API 设计文档 ↔ 后端切片 Pydantic Response Model ↔ 前端 TypeScript interface 三方一致。
- **§2.1 wechat-login 响应**：API §2.1 L171 返回 `requires_consent: bool`；后端 `LoginResponse` L222 `requires_consent: bool = False`；后端 `wechat_login` Service L325-339 正确计算并注入；前端 wechatLogin L168 正确读取 ✅ 三方一致（R21-P1-1 修复后闭环）
- **§2.2 phone-login 响应**：API §2.2 L219 引用 §2.1 格式（`requires_consent`）；后端 `LoginResponse` Schema L222 含此字段；但后端 `phone_login` Service L343-374 **未调用 check_consent、未计算 requires_consent、未注入到 LoginResponse**，运行时返回 `requires_consent=False`（默认值）；前端 phoneLogin L193 正确读取但读到错误值（恒为 False）。三方分歧。详见 R22-P1-1。
- **§8.7 训练单列表响应**：R21-P2-1 修复后 ✅ 四方完全对齐（API §8.7 L2388-2394 ↔ 后端 Schema L491-492 ↔ 后端 Service L1065-1066 ↔ 前端 interface L121-122 ↔ 前端 UI L1156/L1170）
- **§8.8 训练单完成响应**：R21-P2-2 修复后 ✅ 三方完全对齐（API §8.8 L2423 ↔ 后端 Schema L512 ↔ 后端 Service L1152 ↔ 前端 interface L137）

### 4.4 错误码一致性（通用 + 业务码）

**结论**：✅ 通过

- 通用错误码：API §1.7 列出 8 个通用错误码（400/401/403/404/409/422/429/500），切片统一使用 `AppException(message, status_code)` 抛出。
- 业务错误码：每个端点在 API 设计中显式列出"错误情况"表（HTTP 码 / 条件 / 消息），切片实现一致。
- AI 推理：8 处 `raise AppException(..., 503/504)` 与 API §4.10 错误码表一致。

### 4.5 限流配置一致性（API §1.5 vs 切片 @limiter）

**结论**：✅ 通过

| 端点 | API §1.5 | 切片 | 一致性 |
|------|---------|------|--------|
| POST /auth/wechat-login | 10/min | L587 `10/minute` | ✅ |
| POST /auth/phone-login | 5/min | L593 `5/minute` | ✅ |
| POST /auth/send-sms | 1/min | L599 `1/minute`（key_func=phone） | ✅ |
| POST /auth/h5-exchange | 10/min | L648 `10/minute`（R19-P1-1 修复） | ✅ |
| POST /auth/consent | 10/min | L655 `10/minute` | ✅ |
| POST /video-analysis/tasks | 10/hour | L1160 `10/hour`（key_func=user） | ✅ |
| POST /video-analysis/reports/{id}/share | 5/天 | L1256 `5/day`（key_func=user） | ✅ |
| POST /gamification/checkin | 1/天 | L1092 `1/day`（key_func=user） | ✅ |
| POST /admin/login | 5/min | L872 `5/minute` | ✅ |
| 其他端点 | 100/min | 全部 `100/minute` | ✅ |
| POST /payment/notify | —（微信回调） | 无 limiter（SEC-006） | ✅ |

### 4.6 分页参数一致性（page_size le=50/100）

**结论**：⚠️ 部分通过（含 R21-P3-1 遗留）

| 类型 | 切片 | page_size 约束 | 一致性 |
|------|------|--------------|--------|
| 用户端 | video_analysis（3 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | scoring（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | match_data（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | user（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | payment（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | notification（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | progress_analysis（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | training_advice §8.3 templates（1 处，L1232） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | training_advice §8.7 sessions（1 处，L1278） | `Query(20, le=50)` **缺 `ge=1`** | ⚠️ R21-P3-1 遗留 |
| 用户端 | data_dashboard（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 管理端 | admin（2 处：list_users、list_audit_logs） | `Query(default=20, ge=1, le=100)` | ✅ |

### 4.7 model_validate 注入完整性

**结论**：✅ 通过

切片对 service 层返回的数据广泛使用 `model_validate` 注入，覆盖 10 个业务切片 + admin（与 R21 基线一致，无回归）：

| 切片 | model_validate 使用情况 | 一致性 |
|------|----------------------|--------|
| 01-auth | —（简单 dict 返回 + ConsentResponse 直接构造） | ✅ |
| 02-user | RatingHistoryItem.model_validate（L527） | ✅ |
| 03-video_analysis | ReportDetailResponse.model_validate（L853） | ✅ |
| 04-scoring | MatchBrief/MatchDetailWithSequence.model_validate（L700/L716） | ✅ |
| 05-match_data | MatchRecordBrief/MatchRecordDetail.model_validate（L820/L844） | ✅ |
| 06-data_dashboard | MatchRecordBrief.model_validate（L692） | ✅ |
| 07-training_advice | TemplateBrief/TemplateDetail.model_validate（L779/L794）+ TrainingSessionBrief 直接构造（L1058-1067，R21-P2-1 修复后含 session_index/reps） | ✅ |
| 08-progress_analysis | SnapshotBrief + 4 处 model_validate_json（缓存） | ✅ |
| 09-gamification | —（简单 dict 返回） | ✅ |
| 10-membership | —（简单 dict 返回） | ✅ |
| 11-payment | OrderBrief.model_validate（L919） | ✅ |
| 12-notification | NotificationBrief.model_validate（L500） | ✅ |
| 13-admin | AdminBrief/UserManageBrief/ConfigBrief.model_validate（L396/L457/L523/L549/L579） | ✅ |

### 4.8 首页聚合 4 端点 + admin 17 端点三方一致

**结论**：✅ 通过

**首页聚合三方一致**（API §14a / 架构 §5.7 L948-956 / 前端 `00-home/frontend.md`）：

| 端点 | API §14a | 架构 §5.7 | 前端切片 |
|------|---------|----------|---------|
| GET /dashboard/overview | ✅ | ✅ L950 | ✅ 06-data_dashboard frontend L96 |
| GET /gamification/checkin-calendar | ✅ | ✅ L951 | ✅ 09-gamification frontend L96 |
| GET /scoring/matches | ✅ | ✅ L952 | ✅ 04-scoring frontend L57 |
| GET /notification/unread-count | ✅ | ✅ L953 | ✅ 12-notification frontend L76 |

**Admin 17 端点一致**：详见 §3.2 表格，路径/方法/参数/权限全部与 API §19 一致。

### 4.9 契约完整性（缺失端点/缺失参数/缺失响应字段）

**结论**：⚠️ 部分通过（含 R22-P1-1 契约缺口）

- **API ↔ 后端切片**：⚠️ §2.2 phone-login 后端 Service 未计算 requires_consent（R22-P1-1）
- **后端切片 ↔ 前端切片**：⚠️ 1 处契约缺口：
  - §2.2 phone-login：前端 phoneLogin L193 正确读取 `requires_consent`，但后端 phone_login Service L343-374 不计算此字段（运行时恒为 False），导致前端读到的值与用户实际 consent 状态不符（R22-P1-1）

### 4.10 安全性（输入验证/SQL 注入防护/CSRF）

**结论**：✅ 通过

- **输入验证**：全部端点使用 Pydantic Schema 注入（如 ConsentRequest、RefundRequest、AdminLoginRequest 等），自动校验类型/必填/枚举值/最大长度（如 `consent_type: str = Field(..., max_length=32)`、`policy_version: str = Field(..., max_length=16)`）。
- **SQL 注入防护**：全部切片使用 SQLAlchemy 2.0 ORM `select()` / `update()` 语句，无字符串拼接 SQL；无裸 SQL 残留。
- **CSRF**：JWT Bearer Token + H5 一次性 Token 认证（无 Cookie session），架构层面免疫 CSRF；管理员后台使用 session + 同源策略。
- **权限守卫**：`get_current_user`（登录端点）/ `require_membership("member")`（会员端点）/ `get_current_admin`（admin）/ `require_super_admin`（super admin）/ 微信支付回调 APIv3 证书验签 — 五层守卫完整。
- **限流**：100% 端点覆盖 `@limiter.limit()`（除 `POST /payment/notify` 微信回调豁免，SEC-006）。

---

## 5. consent 链路完整性（API → 后端 → 前端 service → store → UI → 跳转）

**结论**：❌ 链路在 phone-login 环节中断（R22-P1-1 导致 phone-login 用户登录后永不跳转同意页）

### 5.1 链路全链路追踪

| 环节 | 状态 | 验证详情 |
|------|------|---------|
| API §2.9 POST /auth/consent | ✅ | API §2.9 L449-470 定义，Pydantic Schema `ConsentRequest` L201-202 校验 `consent_type`/`policy_version` |
| API §2.10 GET /auth/consent-status | ✅ | API §2.10 L485-510 定义，返回 `consented: bool`（true = 已同意） |
| API §2.1 POST /auth/wechat-login | ✅ | API §2.1 L171 返回 `requires_consent: bool`（true = 需同意，极性相反） |
| API §2.2 POST /auth/phone-login | ✅ | API §2.2 L219 引用 §2.1 格式（`requires_consent` 表示是否需要签署隐私政策） |
| 后端 ConsentResponse L204-207 | ✅ | `consented: bool` / `consent_at` / `policy_version`，与 API §2.10 一致 |
| 后端 LoginResponse L222 | ✅ | `requires_consent: bool = False`，与 API §2.1/§2.2 一致 |
| 后端 check_consent L463-483 | ✅ | 返回 `{"consented": bool, "consent_at": str, "policy_version": str}`，与 API 一致 |
| 后端 wechat_login L325-340 | ✅ | L325-326 `consent = await AuthService.check_consent(user.id)`，L327 `requires_consent = not consent["consented"]`（极性反转正确），L339 `requires_consent=requires_consent` |
| 后端 phone_login L343-374 | ❌ | **R22-P1-1**：L343-374 Service 实现未调用 `AuthService.check_consent(user.id)`，未计算 `requires_consent`，L364-374 LoginResponse 构造时不传 `requires_consent`，运行时恒为默认值 `False`（即使未同意用户也返回 False） |
| 后端 Route L588-591 wechat-login | ✅ | `data = await AuthService.wechat_login(body)`，返回 `LoginResponse`（含 requires_consent） |
| 后端 Route L594-597 phone-login | ⚠️ | `data = await AuthService.phone_login(body)`，返回 `LoginResponse` 但 requires_consent 恒为 False |
| 前端 service recordConsent L90-94 | ✅ | `request.post('/auth/consent', {...})` |
| 前端 service getConsentStatus L104 | ✅ | `request.get('/auth/consent-status')` |
| 前端 store recordConsent L254-271 | ✅ | 调 `authApi.recordConsent`，成功置 `needs_consent: false` |
| 前端 store checkConsentStatus L276-286 | ✅ | L279 `consented = !!res.data?.data?.consented`（与 API §2.10 一致），L281 `needs_consent = !consented`（极性反转正确） |
| 前端 store wechatLogin L162-185 | ✅ | L168 `const { ..., requires_consent } = res.data.data`（R21-P1-1 修复后正确读取），L174 `needs_consent: requires_consent`，L177-180 `if (requires_consent) navigateTo consent` |
| 前端 store phoneLogin L187-210 | ⚠️ | L193 `const { ..., requires_consent } = res.data.data`（R21-P1-1 修复后正确读取），L199/L202-205 同 wechatLogin 逻辑正确，**但因后端 phone_login Service 恒返回 requires_consent=False，phone-login 用户即使未同意也不会跳转同意页**（详见 R22-P1-1） |
| 前端 consent 页面 L785-870 | ✅ | R20-P1-3 修复，组件完整，handleAgree 调 recordConsent 成功跳首页 |
| 前端 路由配置 L560 | ✅ | R20-P1-3 修复，`'pages/auth/consent/index'` 已加入 pages 数组 |

### 5.2 链路中断点

**中断点**：后端 `phone_login` Service（L343-374）未计算/注入 `requires_consent`

- **API §2.2 L219 契约**：phone-login 响应格式同 §2.1 wechat-login，应包含 `requires_consent: bool`（true = 需同意）
- **后端 wechat_login 实现（L325-339）**：✅ 正确调用 `check_consent`、计算 `requires_consent = not consent["consented"]`、注入 LoginResponse
- **后端 phone_login 实现（L343-374）**：❌ 未调用 `check_consent`、未计算 `requires_consent`、LoginResponse 构造时不传此参数（Pydantic 默认 `False`）
- **运行时行为分析**：
  - **wechat-login 未同意用户**：API 响应 `requires_consent=true` → 前端 L168 读取 `requires_consent=true` → L178 判断 `if (true)` → 跳转同意页 ✅
  - **wechat-login 已同意用户**：API 响应 `requires_consent=false` → 前端 L168 读取 `requires_consent=false` → L178 判断 `if (false)` → 不跳转，进入首页 ✅
  - **phone-login 未同意用户**：API 响应 `requires_consent=false`（后端默认值，错误！）→ 前端 L193 读取 `requires_consent=false` → L203 判断 `if (false)` → 不跳转（应跳转而未跳转）❌ **PIPL 合规违反**
  - **phone-login 已同意用户**：API 响应 `requires_consent=false`（默认值）→ 前端不跳转 ✅（巧合正确）
- **影响**：
  1. **PIPL 合规违反**：phone-login 用户即使未同意隐私政策，登录后也不会被引导至同意页，违反 PIPL 第 14 条"处理个人信息前应取得个人同意"
  2. **wechat-login 与 phone-login 行为不对称**：wechat-login 用户正确引导同意流程，phone-login 用户跳过同意流程
  3. **R21-P1-1 修复暴露衍生**：R21-P1-1 修复前，前端错误读取 `consented`（不存在的字段）→ 两种 login 都恒为 undefined → 所有用户都被强制跳转（过包容，但 PIPL 合规）。R21-P1-1 修复后，前端正确读取 `requires_consent`，但暴露了 phone_login 后端 Service 未计算此字段的契约缺口（欠包容，PIPL 违反）

详见 R22-P1-1。

### 5.3 与 R21 基线对比

| 环节 | R21 状态 | R22 状态 | 变化 |
|------|---------|---------|------|
| 后端 phone_login Service | ✅（R21 报告 L324 误判"复用 LoginResponse，同样返回 requires_consent"） | ❌（R22-P1-1 实际未计算） | R21 误判 → R22 修正 |
| 前端 wechatLogin 字段映射 | ❌（读 consented 不存在字段） | ✅（读 requires_consent 正确） | R21-P1-1 修复闭环 |
| 前端 phoneLogin 字段映射 | ❌（读 consented 不存在字段） | ⚠️（前端代码修复正确，但后端返回值错误） | R21-P1-1 修复暴露后端问题 |
| consent 链路完整性 | ❌ 中断（所有用户强制跳转） | ❌ 中断（phone-login 用户永不跳转） | 中断点迁移但未消除 |

---

## 6. 训练单端点契约完整性（§8.7 / §8.8）

**结论**：✅ 完全对齐（R21-P2-1 + R21-P2-2 修复后四方闭环）

### 6.1 §8.7 训练单列表 GET /training/plans/{plan_id}/sessions

**API §8.7 L2388-2394 Response Body**：

```json
{
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
}
```

**四方字段对齐表（R21-P2-1 修复后）**：

| 字段 | API §8.7 L2388-2394 | 后端 TrainingSessionBrief L481-493 | 后端 Service L1058-1067 | 前端 TrainingSessionItem L112-123 | 一致性 |
|------|---------------------|------------------------------------|------------------------|-----------------------------------|--------|
| `id` | ✅ L2388 | ✅ L484 | ✅ L1059 `id=s.get("id", i+1)` | ✅ L113 | ✅ |
| `session_index` | ✅ L2389 | ✅ L491 `int Field(...)` | ✅ L1065 `session_index=s.get("session_index", i+1)` | ✅ L121 `session_index: number` | ✅ R21-P2-1 |
| `name` | ✅ L2390 | ✅ L486 | ✅ L1061 `name=s.get("title", s.get("name", ...))` | ✅ L115 | ✅ |
| `reps` | ✅ L2391 | ✅ L492 `int Field(...)` | ✅ L1066 `reps=s.get("reps", 0)` | ✅ L122 `reps: number` | ✅ R21-P2-1 |
| `is_completed` | ✅ L2392 | ✅ L487 `bool` | ✅ L1062 `is_completed=s.get("status")=="completed" or s.get("is_completed", False)` | ✅ L117 | ✅ |
| `completed_at` | ✅ L2393 | ✅ L489 `Optional[datetime]` | ✅ L1064 `completed_at=s.get("completed_at")` | ✅ L118 | ✅ |
| `plan_id` | ❌ 不在 API | ✅ L485（额外 additive） | ✅ L1060 | ✅ L114（额外） | ⚠️ additive |
| `scheduled_date` | ❌ 不在 API | ✅ L488（额外 additive） | ✅ L1063 | ✅ L116（额外） | ⚠️ additive |
| `exercises` | ❌ 不在 API | ❌ 缺失 | ❌ 缺失 | ✅ L119（optional） | ⚠️ frontend only |

**前端 UI 渲染（L1101-1210）**：
- L1155-1156: `{/* R21-P2-1: 显示 session_index（训练单序号） */}` + `<Text className="session-index">#{session.session_index}</Text>` ✅
- L1168-1171: `{/* R21-P2-1: 显示 reps（建议训练次数） */}` + `<Text className="session-reps">{t('training.reps')}: {session.reps}</Text>` ✅

**§8.7 端点契约结论**：✅ 四方完全对齐（除 additive 字段 plan_id/scheduled_date/exercises 不在 API 但不破坏契约）

### 6.2 §8.8 训练单完成 POST /training/plans/{plan_id}/sessions/{session_id}/complete

**API §8.8 L2421-2424 Response Body**：

```json
{
  "session_id": 1,
  "is_completed": true,
  "plan_progress": 70,
  "points_earned": 5
}
```

**四方字段对齐表（R21-P2-2 修复后）**：

| 字段 | API §8.8 L2421-2424 | 后端 CompleteResponse L506-514 | 后端 Service L1148-1155 | 前端 CompleteSessionData L134-139 | 一致性 |
|------|---------------------|--------------------------------|-------------------------|-----------------------------------|--------|
| `session_id` | ✅ L2421 | ✅ L509 | ✅ L1149 `session_id=session_id` | ✅ L135 | ✅ |
| `is_completed` | ✅ L2422 | ✅ L510 `bool = True` | ✅ L1150 `is_completed=True` | ✅ L136 | ✅ |
| `plan_progress` | ✅ L2423 `int 70` | ✅ L512 `int Field(..., 0-100)` | ✅ L1152 `int(plan_progress * 100)` | ✅ L137 `number  // 0-100` | ✅ R21-P2-2 |
| `points_earned` | ✅ L2424 | ✅ L513 `int` | ✅ L1153 `points_earned=points_earned` | ✅ L138 | ✅ |
| `completed_at` | ❌ 不在 API | ✅ L514 `Optional[datetime]`（额外 additive） | ✅ L1154 `completed_at=now` | ❌ 不在前端 | ⚠️ additive |

**§8.8 端点契约结论**：✅ 四方完全对齐（除 additive 字段 completed_at 不在 API 但不破坏契约）

---

## 7. 新发现 P0-P3 分级

### P0（阻断级） — 0 项

无。

### P1（严重级 — 影响契约一致性 / PIPL 合规 / 功能可用性） — 1 项

#### R22-P1-1：phone_login 后端 Service 未计算/注入 `requires_consent`（R21-P1-1 修复暴露的衍生问题）

- **位置**：
  - `docs/04详细设计/05-API详细设计.md` §2.2 L219（API 响应引用 §2.1 格式，应包含 `requires_consent`）
  - `docs/06垂直模块前后端切片设计/01-auth/backend.md` L222（`LoginResponse.requires_consent: bool = False` Schema 定义）、L325-340（wechat_login Service 正确实现）、L343-374（**phone_login Service 缺失 requires_consent 计算**）、L595-597（phone-login 路由调用）
- **现象**：API §2.2 L219 明确规定 phone-login 响应格式同 §2.1 wechat-login，应返回 `requires_consent: bool`（true = 需同意）。后端 `LoginResponse` Schema L222 定义 `requires_consent: bool = False`，`wechat_login` Service L325-340 正确实现：
  - L325-326：`consent = await AuthService.check_consent(user.id)`
  - L327：`requires_consent = not consent["consented"]`（极性反转正确）
  - L339：`requires_consent=requires_consent`（注入 LoginResponse）

  但 `phone_login` Service L343-374 实现缺失此逻辑：

  ```python
  # L343-374 phone_login Service
  @staticmethod
  async def phone_login(req: PhoneLoginRequest) -> LoginResponse:
      """手机号验证码登录。"""
      redis = await get_redis()
      cached_code = await redis.get(f"sms:code:{req.phone}")
      if not cached_code or cached_code != req.code:
          raise AppException("验证码错误或已过期", 400)

      # 查询或创建用户
      from sqlalchemy import select
      from app.core.database import get_async_session
      async with get_async_session() as db:
          result = await db.execute(select(User).where(User.phone == req.phone))
          user = result.scalar_one_or_none()
          if user is None:
              user = User(phone=req.phone, nickname="球友")
              db.add(user)
              await db.commit()
              await db.refresh(user)

          access_token = create_access_token(...)
          refresh_token = create_refresh_token(...)

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
              # ❌ 缺失：consent = await AuthService.check_consent(user.id)
              # ❌ 缺失：requires_consent = not consent["consented"]
              # ❌ 缺失：requires_consent=requires_consent,
          )
  ```

- **API/后端/前端三方字段对比**：

  | 维度 | API §2.2 L219 | 后端 LoginResponse Schema L222 | 后端 phone_login Service L364-374 | 前端 phoneLogin L193 | 一致性 |
  |------|---------------|-------------------------------|-----------------------------------|----------------------|--------|
  | 字段定义 | ✅ 应返回 requires_consent | ✅ `requires_consent: bool = False` | ❌ 不传此参数（默认 False） | ✅ 解构读取 requires_consent | ❌ |
  | 字段值（未同意用户） | 应为 `true` | — | 实际为 `False`（默认值） | 读取为 `false`（错误） | ❌ |
  | 字段值（已同意用户） | 应为 `false` | — | 实际为 `False`（默认值） | 读取为 `false`（巧合正确） | ⚠️ 巧合 |
  | check_consent 调用 | — | — | ❌ 未调用 | — | ❌ |

- **运行时行为分析**：
  - **场景 A：phone-login 用户首次登录（未同意）**
    - 后端 phone_login Service：不调用 check_consent，不计算 requires_consent，LoginResponse 构造时不传此参数 → Pydantic 使用默认值 `requires_consent=False`
    - API 响应：`{ "access_token": "...", "refresh_token": "...", "requires_consent": false, "user": {...} }`（false 错误，应为 true）
    - 前端 phoneLogin L193：`const { ..., requires_consent } = res.data.data` → `requires_consent = false`
    - 前端 L199：`needs_consent: requires_consent` → `needs_consent = false`（错误置为"无需同意"）
    - 前端 L203-205：`if (requires_consent) { navigateTo consent; return }` → `if (false)` → 不跳转（应跳转而未跳转）
    - **结果**：用户直接进入首页，未签同意书，**PIPL 合规违反**
  - **场景 B：phone-login 用户已同意后再次登录**
    - 后端 phone_login Service：同样不调用 check_consent，requires_consent=False
    - 前端：同样不跳转
    - **结果**：用户直接进入首页（巧合正确，但逻辑错误）
  - **结论**：phone-login 用户两种场景下 `requires_consent` 均为 `False`，前端无法区分，**所有 phone-login 用户登录后均不跳转同意页**（即使未同意）

- **影响**：
  1. **PIPL 合规违反**：phone-login 用户即使未同意隐私政策，登录后不会被引导至同意页，违反 PIPL 第 14 条"处理个人信息前应取得个人同意"+ 第 17 条"个人信息处理者不得以个人不同意处理个人信息或者撤回同意为由，拒绝提供产品或者服务"（但需先取得同意）
  2. **wechat-login vs phone-login 行为不对称**：wechat-login 用户正确引导同意流程（L325-339 实现完整），phone-login 用户跳过同意流程（L343-374 实现缺失）
  3. **R21-P1-1 修复暴露衍生**：R21 报告 §5.1 L324 误判"phone_login 复用 LoginResponse，同样返回 requires_consent"——实际仅"复用 LoginResponse 类"但"未同样返回 requires_consent 字段值"（Pydantic 默认值 False）。R21-P1-1 修复前，前端错误读取 `consented`（不存在字段）→ 所有用户都强制跳转（过包容，PIPL 合规安全）；R21-P1-1 修复后，前端正确读取 `requires_consent`，但暴露了 phone_login 后端 Service 缺失此字段计算的契约缺口（欠包容，PIPL 违反）
  4. **API 契约破坏**：API §2.2 L219 明确引用 §2.1 格式含 `requires_consent`，但后端 phone_login Service 实际不返回有效值，API 契约破坏

- **建议**：
  - **修复方案（推荐，后端对齐 wechat_login）**：在 phone_login Service L343-374 中补 consent 检查逻辑，与 wechat_login L325-340 对称：
    ```python
    @staticmethod
    async def phone_login(req: PhoneLoginRequest) -> LoginResponse:
        """手机号验证码登录。"""
        redis = await get_redis()
        cached_code = await redis.get(f"sms:code:{req.phone}")
        if not cached_code or cached_code != req.code:
            raise AppException("验证码错误或已过期", 400)

        # 查询或创建用户
        from sqlalchemy import select
        from app.core.database import get_async_session
        async with get_async_session() as db:
            result = await db.execute(select(User).where(User.phone == req.phone))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(phone=req.phone, nickname="球友")
                db.add(user)
                await db.commit()
                await db.refresh(user)

            access_token = create_access_token({"sub": str(user.id), "jti": str(uuid.uuid4())})
            refresh_token = create_refresh_token({"sub": str(user.id), "jti": str(uuid.uuid4())})

            # R22-P1-1: 补 consent 检查逻辑（与 wechat_login L325-327 对称）
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
                requires_consent=requires_consent,  # R22-P1-1: 注入 requires_consent
            )
    ```
  - **修复优先级**：P1 立即修复，3 行代码新增（调用 check_consent + 计算 requires_consent + 注入 LoginResponse）
  - **验证方法**：R23 grep `requires_consent` 在 phone_login Service 应出现 2 次（L327 计算行 + L339 注入行），目前仅 0 次

### P2（中优先级 — 契约字段缺口 / 类型分歧） — 0 项

无。R21-P2-1 + R21-P2-2 均已完全修复闭环。

### P3（低优先级 — 参数校验风格不一致） — 1 项（R21 遗留）

#### R21-P3-1（遗留未修）：§8.7 sessions 路由 page_size Query 缺失 `ge=1` 约束

- **位置**：
  - `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` L1278（`page_size: int = Query(20, le=50)`，缺 `ge=1`）
  - 对比：L1232（§8.3 templates）`page_size: int = Query(default=20, ge=1, le=50)` ✅
  - 对比：API §1.2 L46 "page_size 默认 20，最小 1，用户端最大 50"
  - 对比：API §1.2 L5974 "分页参数 MUST 使用 `Query(default=..., ge=1)` 校验"
- **现象**：R21-P3-1 在 R22 仍未修复，`page_size` Query 参数仍写为 `Query(20, le=50)`，**缺失 `ge=1` 约束**，与同切片 L1232 风格不一致，违反 API §1.2 L46 + L5974 强制要求。

  ```python
  # L1232 §8.3 templates（正确风格）
  page_size: int = Query(default=20, ge=1, le=50),

  # L1278 §8.7 sessions（错误风格，缺 ge=1，R21-P3-1 遗留）
  page_size: int = Query(20, le=50),
  ```

- **运行时影响**：
  - 用户传 `page_size=0` 或 `page_size=-1` 不会被 FastAPI 拒绝
  - Service L1073-1075 分页逻辑：`page_start = (page - 1) * page_size` → 若 page_size=0 则 page_start=0；`page_end = page_start + page_size` → page_end=0；`items = all_items[0:0]` = 空列表（行为异常）
  - 用户传 `page_size=-1` 时 `all_items[0:-1]` 返回除最后一个外的所有项（行为异常）

- **建议**：修改 L1278：
  ```python
  page_size: int = Query(default=20, ge=1, le=50),  # R21-P3-1（R22 遗留）: 补 ge=1，与 L1232 + API §1.2 一致
  ```

---

## 8. 修复跟踪表

### 8.1 R22 新发现修复跟踪

| 编号 | 优先级 | 修复项 | 涉及文件 | 状态 |
|------|--------|--------|---------|------|
| R22-P1-1 | P1 | phone_login Service 补 check_consent 调用 + requires_consent 计算与注入 | 后端 `01-auth/backend.md` L343-374（Service）| 待修复 |
| R21-P3-1（遗留） | P3 | §8.7 sessions 路由 page_size Query 补 `ge=1` | 后端 `07-training_advice/backend.md` L1278 | 待修复（R21→R22 遗留） |

### 8.2 R21 修复回归通过率汇总

| R21 编号 | 修复项 | R22 验证结果 |
|---------|--------|------------|
| R21-P1-1 | wechatLogin/phoneLogin 字段名 `consented` → `requires_consent` + 极性逻辑修正 | ✅ **完全闭环**（前端 wechatLogin/phoneLogin/checkConsentStatus 字段映射全部正确，store 内 needs_consent 统一）。**但修复暴露 phone_login 后端 Service 缺 requires_consent 计算 → 衍生 R22-P1-1** |
| R21-P2-1 | 训练单 Brief 补 `session_index` + `reps` 字段 | ✅ **完全闭环**（后端 Schema L491-492 + Service L1065-1066 + 前端 interface L121-122 + UI L1156/L1170 四方对齐） |
| R21-P2-2 | CompleteResponse.plan_progress 类型 `float 0.0-1.0` → `int 0-100` | ✅ **完全闭环**（后端 Schema L512 `int` + Service L1152 `int(plan_progress * 100)` + 前端 interface L137 `number  // 0-100` 三方对齐） |
| R21-P3-1 | §8.7 sessions 路由 page_size Query 补 `ge=1` | ❌ **未修复**（L1278 仍为 `Query(20, le=50)`，P3 级遗留） |

**R21 3 项 P2+ 修复回归通过率**：3/3 完全闭环（100%）✅
**R21 1 项 P3 修复回归通过率**：0/1 修复（0%）❌ 遗留

### 8.3 累计修复统计

| 维度 | R21 累计 | R22 新增 | R22 累计 |
|------|---------|---------|---------|
| API 维度新发现（P2+） | 3（P1×1 + P2×2） | 1（P1×1） | 1（P22-P1-1） |
| API 维度新发现（P3） | 1（R21-P3-1） | 0 新增（1 遗留） | 1（R21-P3-1 遗留） |
| 全维度累计修复 | 待定 | 待定 | 待 R22 全维度汇总 |

### 8.4 连续两轮无 P2+ 进度跟踪

| 目标 | 状态 | 说明 |
|------|------|------|
| 连续两轮无 P2+（API 维度） | **第一轮仍未达成** | R22 API 维度新发现 P1×1（R22-P1-1：phone_login 后端 Service 缺 requires_consent 计算），未达到"零 P2+"状态。R21-P1-1 修复暴露衍生 R22-P1-1。需先修复 R22-P1-1 共 1 项 P2+，再进入 R23 第一轮验证 |
| 连续两轮无 P2+（DB 维度） | 第一轮完成（R20-DB 报告） | DB 维度零 P2+ 新发现 |
| 连续两轮无 P2+（后端跨模块安全维度） | 第一轮完成（R20-后端报告） | 后端维度零 P0-P3 新发现 |
| 连续两轮无 P2+（架构维度） | 第一轮完成（R20-架构报告） | 架构维度零 P2+ 新发现 |
| 连续两轮无 P2+（前端 UX 维度） | 由 R22-前端设计系统 UX 审查报告承接 | — |

---

## 9. 审查结论

### 9.1 整体评价

本轮审查覆盖 8 项审查清单，**R21 3 项 P2+ 修复全部完全闭环**（R21-P1-1 wechatLogin/phoneLogin 字段名修正 ✅ + R21-P2-1 训练单 Brief 补 session_index/reps ✅ + R21-P2-2 plan_progress 类型 float→int ✅），但发现 **1 项新 P1**（R22-P1-1：R21-P1-1 修复暴露 phone_login 后端 Service 缺 requires_consent 计算的契约缺口）+ **1 项 P3 遗留**（R21-P3-1 §8.7 page_size Query 缺 ge=1 未修复）。

### 9.2 关键结论

1. **R21 3 项 P2+ 修复回归通过率 100%（3/3 完全闭环）**，相比 R20→R21 回归（66.7%）显著提升。R21-P1-1 字段映射修复 + R21-P2-1 session_index/reps 字段补齐 + R21-P2-2 plan_progress 类型对齐 三方契约完全闭环。
2. **R21-P1-1 修复暴露衍生 R22-P1-1**：R21-P1-1 前端修复正确，但暴露了 phone_login 后端 Service（L343-374）从未实现 `requires_consent` 计算逻辑的契约缺口——R21 报告 §5.1 L324 误判"phone_login 复用 LoginResponse，同样返回 requires_consent"，实际仅复用 LoginResponse Schema 类但未注入字段值（Pydantic 默认值 False）。R21-P1-1 修复前，前端错误读取 `consented`（不存在字段）→ 所有用户强制跳转（过包容，PIPL 合规安全）；R21-P1-1 修复后，前端正确读取 `requires_consent`，但暴露 phone_login 后端 Service 缺此字段计算 → phone-login 用户永不跳转同意页（欠包容，PIPL 违反）。
3. **§8.7/§8.8 训练单端点四方完全对齐**（R21-P2-1 + R21-P2-2 修复后）：API ↔ 后端 Schema ↔ 后端 Service ↔ 前端 interface/UI 字段、类型、取值范围四方一致，含 UI 渲染补 session_index/reps 显示。
4. **API 维度连续第一轮无 P2+ 目标未达成**，需先修复 R22-P1-1 共 1 项 P2+ 问题，再进入 R23 第一轮验证。R21-P3-1（P3 级）遗留不影响"无 P2+"目标但建议同步修复。

### 9.3 待跟踪项

| 编号 | 类别 | 跟踪点 | 验证方式 |
|------|------|--------|---------|
| R22-P1-1 | 字段映射 | phone_login Service 包含 `requires_consent` 计算与注入 | R23 grep `requires_consent` 在 `01-auth/backend.md` phone_login Service 段（L343-374），应出现 2 次（计算行 + 注入行），目前 0 次 |
| R21-P3-1（遗留） | 参数校验 | §8.7 sessions 路由 page_size Query 含 `ge=1` | R23 grep `Query\(20, le=50\)` 在 `07-training_advice/backend.md` L1278（应改为 `Query(default=20, ge=1, le=50)`） |

### 9.4 下一轮建议

1. **R23 验证目标**：修复 R22-P1-1 + R21-P3-1 共 2 项问题后，进入 R23 第一轮"零 P2+"验证。若 R23 也达到零 P2+，则 API 维度正式达成"连续两轮无 P2+"目标。
2. **修复优先级建议**：
   - **第一批（P1，立即修复）**：R22-P1-1（phone_login Service 补 check_consent 调用 + requires_consent 计算与注入，3 行代码新增）— 与 wechat_login L325-339 实现对称，闭合同意流程"最后一公里"路由
   - **第二批（P3，后续修复）**：R21-P3-1（page_size Query 补 ge=1，1 行代码修改）— 参数校验风格统一
3. **审查方法改进建议**：R22 检出的 R22-P1-1 为 R21-P1-1 修复暴露的衍生问题，R21 审查时验证了前端字段映射正确性，但未深入验证后端 Service 实现是否与 wechat_login 对称。建议 R23 审查时**对涉及多端点共享概念（如 consent 状态在 §2.1/§2.2/§2.10 三个端点）的契约，必须按端点逐一核对 API 设计文档响应字段定义、后端 Pydantic Model 字段、后端 Service 实现（含 check_consent 调用与字段注入）、前端 service 解构字段四方一致**，避免"Schema 类复用但 Service 实现不对称"的伪闭环（如 R21 报告 §5.1 L324 误判 phone_login 复用 LoginResponse 同样返回 requires_consent，实际仅复用类未注入值）。

---

## 10. 附录：审查证据文件索引

| 文件 | 用途 | 关键行号 |
|------|------|---------|
| `docs/04详细设计/05-API详细设计.md` | API 设计 v1.3 端点权威源 | §2.1 L137-199（wechat-login）、§2.2 L200-228（phone-login）、§2.9 L437-484（consent）、§2.10 L485-512（consent-status）、§8.7 L2363-2407（sessions list）、§8.8 L2408-2449（session complete）、§1.2 L46/L49/L5974（page_size 规范） |
| `docs/03系统架构/01-系统架构设计.md` §5.7 | Phase 1 端点清单 | L804-958（96 端点完整列表） |
| `docs/06垂直模块前后端切片设计/01-auth/backend.md` | 认证切片后端实现 | L201-202（ConsentRequest）、L204-207（ConsentResponse）、L217-222（LoginResponse.requires_consent）、L325-340（wechat_login 服务，✅ 正确实现）、L343-374（phone_login 服务，❌ R22-P1-1 缺 requires_consent）、L463-483（check_consent）、L588-591（wechat-login 路由）、L594-597（phone-login 路由）、L676-678（consent-status 路由） |
| `docs/06垂直模块前后端切片设计/01-auth/frontend.md` | 认证切片前端实现 | L118-148（AuthUser/AuthState interface + actions）、L162-185（wechatLogin action，R21-P1-1 修复）、L187-210（phoneLogin action，R21-P1-1 修复）、L254-271（recordConsent action）、L276-286（checkConsentStatus action）、L556-563（pages 路由数组，含 consent）、L785-870（ConsentPage 组件）、L945-951（i18n 条目） |
| `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` | 训练切片后端实现 | L481-493（TrainingSessionBrief Schema，R21-P2-1 修复含 session_index/reps）、L496-503（TrainingSessionListResponse）、L506-514（TrainingSessionCompleteResponse Schema，R21-P2-2 修复 plan_progress: int）、L1038-1083（list_training_sessions service，R21-P2-1 修复含 session_index/reps 注入）、L1085-1155（complete_training_session service，R21-P2-2 修复 int(plan_progress*100)）、L1273-1287（§8.7 sessions 路由，R21-P3-1 遗留 page_size 缺 ge=1）、L1290-1301（§8.8 complete 路由） |
| `docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` | 训练切片前端实现 | L70（template sessions）、L112-123（TrainingSessionItem interface，R21-P2-1 修复含 session_index/reps）、L126-131（TrainingSessionListData interface）、L134-139（CompleteSessionData interface，plan_progress: number  // 0-100）、L274-289（store state + actions）、L417-444（actions 实现）、L1101-1210（训练方案详情页组件，R21-P2-1 修复含 session_index/reps UI 渲染）、L1692-1700（pages 路由数组） |
| `docs/07审查报告/第二十一轮/R21-API端点级审查报告.md` | R21 基线 | 全文 3 项 P2+ + 1 项 P3，§5.1 L324 误判 phone_login 复用 LoginResponse 同样返回 requires_consent |

---

**报告生成完成时间**：2026-10-19
**审查覆盖范围**：8 项审查清单 + 96 端点完整性 + consent 链路全链路追踪 + 训练单 §8.7/§8.8 四方契约验证
**关键发现**：P1×1 + P0×0 + P2×0 + P3×1（R21-P3-1 遗留）= 2 项新发现/遗留
**目标达成状态**：⚠️ API 维度连续第一轮无 P2+ 目标**未达成**（含 1 项 P1 新发现 R22-P1-1）
**R21 3 项 P2+ 修复回归通过率**：3/3 完全闭环（100%）✅

