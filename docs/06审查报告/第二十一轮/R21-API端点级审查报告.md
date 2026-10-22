# R21 — API 端点级 + 前后端契约完整性审查报告

> **审查代理**：第二十一轮 API 端点级 + 前后端契约完整性维度
> **审查日期**：2026-10-19
> **工作目录**：D:\PyProject\TableTennisAnalysis
> **审查基线**：R20-API 端点级审查报告（2026-10-19）+ API 设计 v1.3 + 架构 §5.7（L803-957）+ 12 后端切片 + 13 前端切片
> **目标**：连续两轮无 P2+（新第一轮）— 验证 R20 6 项 P2+ 修复回归 + 96 端点三方契约完整性

---

## 1. 审查范围与执行摘要

### 1.1 审查清单（12 项）

| 序号 | 文件 | 用途 |
|------|------|------|
| 1 | `docs/04详细设计/05-API详细设计.md`（5215 行） | API 设计 v1.3，端点权威源 |
| 2 | `docs/03系统架构/01-系统架构设计.md` §5.7（L803-957） | Phase 1 核心 API 端点清单 |
| 3-14 | `docs/06垂直模块前后端切片设计/{01-12}-*/backend.md` | 12 个业务切片 @router 定义 |
| 15 | `docs/06垂直模块前后端切片设计/13-infrastructure/admin.md` | 管理后台切片 @router 定义 |
| 16 | `docs/06垂直模块前后端切片设计/13-infrastructure/ai_inference.md` | AI 推理（HTTPException 检查） |
| 17 | `docs/06垂直模块前后端切片设计/{01-12}-*/frontend.md` | 13 前端切片 request.* 调用 |
| 18 | `docs/07审查报告/第二十轮/R20-API端点级审查报告.md` | R20 基线（6 项 P2+） |
| 19 | `docs/07审查报告/第十八轮/R18-需求覆盖度审查报告.md` | R20-P2-2 闭环验证 |

### 1.2 执行摘要

本轮审查覆盖 **12 项审查清单**（R20 6 项 API 维度 P2+ 修复回归 + 96 端点三方一致性 + Schema/错误码/限流/model_validate/分页参数/安全性 + consent 链路完整性），核心一致性维度大部分维持。**关键结论**：

- **R20 6 项 P2+ 修复回归通过率**：4/6 完全闭环 + 1/6 部分闭环（R20-P1-1 字段名对齐完成但 session_index/reps + plan_progress 类型未对齐）+ 1/6 修复不正确（R20-P1-4 读取错误字段名 `consented`，应读 `requires_consent`）
- **新发现**：P1×1 + P2×2 + P3×1 = **4 项**
- **新发现归因**：1 项为 R20-P1-4 修复不正确（读取错误字段名，将 §2.10 consent-status 的 `consented` 字段误用到 §2.1/§2.2 wechat-login/phone-login 响应，导致所有用户登录后被强制跳转同意页）+ 2 项为 R20-P1-1 修复不完整（缺失 `session_index`/`reps` 字段；`plan_progress` 类型仍为 float vs API 设计 int 0-100）+ 1 项参数校验风格不一致（§8.7 sessions 路由 page_size Query 缺失 `ge=1` 约束）
- **目标达成状态**：⚠️ **API 维度连续第一轮无 P2+ 目标未达成**（R21 含 P1×1 + P2×2 + P3×1 = 4 项新发现）。R20 6 项 P2+ 中 5 项已完全闭环，但 R20-P1-4 修复不正确衍生 R21-P1-1，R20-P1-1 修复不完整衍生 R21-P2-1/P2-2

### 1.3 关键统计

| 审查项 | R20 基线 | R21 现状 | 变化 |
|--------|---------|---------|------|
| 新发现 P0 | 0 | 0 | 持平 |
| 新发现 P1 | 4 | 1 | -3 |
| 新发现 P2 | 2 | 2 | 持平（R20-P1-1 修复不完整衍生） |
| 新发现 P3 | 1 | 1 | 持平 |
| 新发现合计 | 7 | 4 | -3 |
| R20 修复回归通过率 | — | 4/6 完全闭环 + 1/6 部分闭环 + 1/6 修复不正确 | — |
| 连续两轮无 P2+ 目标 | 第一轮未达成 | 第一轮仍未达成（含 P1+P2 新发现） | 持平 |

---

## 2. R20 修复回归验证表（6 项 P2+）

R20-API 端点级报告共 7 项发现（P1×4 + P2×2 + P3×1），本轮聚焦 6 项 P2+（P1×4 + P2×2）回归验证：

| 序号 | R20 编号 | R20 修复项 | R21 状态 | 验证详情 |
|------|---------|-----------|---------|---------|
| 1 | R20-P1-1 | 训练单 §8.7/§8.8 三方契约对齐 | ⚠️ **部分闭环** | **已闭环**：(a) 后端 `TrainingSessionBrief` L480-489 字段名 `id`/`name`/`is_completed: bool`/`completed_at` 与 API §8.7 对齐；(b) `TrainingSessionListResponse` L492-499 字段名 `total`/`page`/`page_size`/`items` 对齐；(c) `TrainingSessionCompleteResponse` L502-509 补 `is_completed`/`points_earned`；(d) Service `list_training_sessions` L1033-1035 补 `page`/`page_size` 参数 + L1064-1067 分页逻辑；(e) Route L1266-1278 补 `page`/`page_size` Query 参数。**未闭环**：(a) Brief 缺失 `session_index` 字段（API §8.7 L2389 要求）；(b) Brief 缺失 `reps` 字段（API §8.7 L2391 要求）；(c) `CompleteResponse.plan_progress` 仍为 `float 0.0-1.0`（API §8.8 L2423 期望 `int 0-100` 百分比，未执行 `int(plan_progress * 100)` 转换）。详见 R21-P2-1 + R21-P2-2 |
| 2 | R20-P1-2 | 前端 `checkConsentStatus` 读取 `consented` 字段（极性反转） | ✅ **已修复** | 前端 `01-auth/frontend.md` L269-277 `checkConsentStatus` action L272 `const consented = !!res.data?.data?.consented`，与 API §2.10 L497 + 后端 `ConsentResponse` L204-207（`consented: bool`）一致；L274 `needs_consent: !consented`（极性反转正确，`consented=true` 表示已同意 → `needs_consent=false`） |
| 3 | R20-P1-3 | consent 同意页 `pages/auth/consent/index` 路由+组件实现 | ✅ **已修复** | (a) 路由配置 L560 `'pages/auth/consent/index'` 已加入 pages 数组；(b) 组件 L785-870 `ConsentPage` 已实现，含 `PrivacyPolicyContent` 子组件（L799-808）+ `handleAgree`（L818-826，调 `recordConsent('privacy_policy', 'v1.0')`，成功 → `Taro.switchTab('/pages/home/index')`，失败 → toast）+ `handleRefuse`（L829-831，toast "需同意隐私政策才能使用"）；(c) i18n 条目 L945-951 zh-CN 全部补充（`privacyConsentTitle`/`privacyPolicyTitle`/`privacyPolicyBody`/`agreeAndContinue`/`refuse`/`consentRequired`/`consentFailed`） |
| 4 | R20-P1-4 | wechatLogin/phoneLogin 成功后检查 consented 跳转同意页 | ❌ **修复不正确** | 跳转逻辑已添加，**但读取错误字段名**：前端 `01-auth/frontend.md` L162 `wechatLogin` 与 L186 `phoneLogin` 均从 `res.data.data` 解构 `consented` 字段。**API §2.1 L171 + §2.2 L219 实际返回 `requires_consent` 字段**（API §2.1 L183 文档明确"新增 `requires_consent` 字段（boolean）...`true` 表示当前用户尚未签署最新版隐私政策"）；后端 `LoginResponse` L222 `requires_consent: bool = False`、L339 `requires_consent=requires_consent` 三方一致。前端读取的 `consented` 在 API 响应中不存在（`undefined`），导致 `!consented = !undefined = true`（恒真），**所有用户登录后均被强制跳转同意页**（即使已同意）。详见 R21-P1-1 |
| 5 | R20-P2-1 | 训练方案详情页 `pages/training/plans/[plan_id]/index` UI 接入 | ✅ **已修复** | (a) 组件实现 `07-training_advice/frontend.md` L1059-1200 `TrainingPlanDetailPage`，含 `useEffect` 调 `store.fetchTrainingSessions(planId)`（L1081）+ `handleCompleteSession` 调 `store.completeTrainingSession(planId, sessionId)`（L1087）+ 渲染 `session.id`/`session.name`/`session.is_completed`/`session.scheduled_date`/`session.completed_at`/`session.exercises`（L1147-1190）+ 进度条 L1137 `Progress percent={progressPercent}`（本地计算 `completedCount / totalCount * 100`，不依赖 API `plan_progress`）；(b) 路由配置 L1700 `'pages/training/plans/[plan_id]/index'` 已加入 pages 数组；(c) 完成回调 L1090 `setToastMsg(t('training.sessionCompleted', { points: result.points_earned }))` 使用 `points_earned` |
| 6 | R20-P2-2 | R18 需求报告 L81/L91 补注 R19 闭环值 | ✅ **已修复** | (a) `R18-需求覆盖度审查报告.md` L81 §2.5 末尾追加 "**R19 闭环注**：R19-P1-1 已修复 R18 综合报告 L6/L215/L259 计数（843→854），跨文档计数一致性问题已闭环。本节描述保留作为历史记录。"；(b) L93 P0-1 描述末尾追加 "**R19 闭环注**：R19-P1-1 已修复，R18 综合报告 L6/L215/L259 已更新为 854。本描述保留 R18 审查时点状态作为修复前对照。"；(c) L387 §7 末尾已有 R18 收尾阶段闭环注（与 L81/L91 互为印证，跨文档闭环说明一致） |

**R20 6 项 P2+ 修复通过率**：完全闭环 4/6（66.7%）+ 部分闭环 1/6（16.7%）+ 修复不正确 1/6（16.7%）

### 2.1 附加维度验证（R20 P3 项）

| R20 编号 | R20 修复项 | R21 状态 | 验证详情 |
|---------|-----------|---------|---------|
| R20-P3-1 | DB §04 头部说明 L7 VARCHAR(32)→VARCHAR(20) | （本报告 API 维度不验证） | 由 R21-DB 字段级审查报告承接验证 |

---

## 3. 96 端点完整性（79 业务 + 17 admin）

### 3.1 Phase 1 业务端点（79 个）

#### 认证模块 `/auth`（10 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /auth/wechat-login | POST | L587-591 | ✅ | ❌ 见 R21-P1-1（前端读取错误字段名 `consented`，应读 `requires_consent`） |
| 2 | /auth/phone-login | POST | L593-597 | ✅ | ❌ 见 R21-P1-1（同上） |
| 3 | /auth/send-sms | POST | L599-603 | ✅ | ✅ |
| 4 | /auth/refresh | POST | L605-? | ✅ | ✅ |
| 5 | /auth/logout | POST | L607-? | ✅ | ✅ |
| 6 | /auth/me | GET | L609-? | ✅ | ✅ |
| 7 | /auth/h5-token | GET | L611-? | ✅ | ✅ |
| 8 | /auth/h5-exchange | POST | L640-? | ✅ | ✅（R19-P1-1 修复后限流 10/min） |
| 9 | /auth/consent | POST | L655-? | ✅ | ✅（R20-P1-3 同意页已实现） |
| 10 | /auth/consent-status | GET | L675-678 | ✅ | ✅（R20-P1-2 字段映射正确） |

#### 用户模块 `/users`（9 端点，不含 §3.7 跨模块）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-9 | §3.1-3.6 + §3.8-3.10 | GET/PUT/POST/DELETE | L811-841 等 | ✅ | ✅（R19-P1-3 修复后无 deletion-status） |

#### 视频分析模块 `/video-analysis`（12 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-12 | §4.1-4.12（含 §3.7 反馈历史跨模块） | GET/POST/DELETE | L1157-1268 | ✅ | ✅（R19-P2-1 修复后 feedbacks 调用已补齐） |

#### 记分牌模块 `/scoring`（5 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1-5 | §5.1-5.5 | GET/POST/DELETE | L1148-1180 | ✅ | ✅ |

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
| 7 | §8.7 GET /training/plans/{plan_id}/sessions | GET | L1266-1278 | ✅ | ⚠️ 见 R21-P2-1（Brief 缺 session_index/reps）+ R21-P3-1（page_size Query 缺 ge=1） |
| 8 | §8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete | POST | L1283-1292 | ✅ | ⚠️ 见 R21-P2-2（plan_progress 类型分歧） |

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

- **路径/方法/参数/权限/限流三方一致**：93/96 ✅（R20 基线 94/96 ✅，本轮 R20-P1-4 修复不正确使 §2.1/§2.2 由 ✅ 变为 ❌，R20-P1-1 部分闭环使 §8.7/§8.8 仍为 ⚠️）
- **§2.1 / §2.2 登录端点**：2/96 ❌（详见 R21-P1-1，前端读取错误字段名导致登录后所有用户被强制跳转同意页）
- **§8.7 / §8.8 训练单端点**：2/96 ⚠️（详见 R21-P2-1/P2-2，字段名对齐完成但 Brief 缺 session_index/reps + plan_progress 类型分歧）
- **96 端点完整性维持率**：96.9%（93/96 完全一致）

---

## 4. 三方契约一致性

### 4.1 API § vs 架构 §5.7 vs 切片 @router

**结论**：✅ 通过（96 端点路径/方法/权限标注三方一致）

- 架构 §5.7 L803-957 明确列出 Phase 1 全部 96 个端点（79 业务 + 17 admin），与 API 设计 v1.3 和切片 @router 装饰器路径、HTTP 方法、权限守卫完全一致。
- R19-P1-2 修复后，训练 §8.3/§8.4/§8.5/§8.6/§8.7/§8.8 权限"会员"在 API/架构/切片三方一致（架构 L945-946、切片 L1257/L1271/L1287 `require_membership("member")`）。
- R19-P1-1 修复后，`POST /auth/h5-exchange` 限流 10/minute 在 API §1.5 / 切片 L587 一致。

### 4.2 请求参数验证完整性（Pydantic Schema vs API 参数表）

**结论**：⚠️ 部分通过

- 95/96 端点 Pydantic Schema 与 API 参数表完全一致。
- **§8.7 GET /training/plans/{plan_id}/sessions**：API §8.7 L2373-2374 声明 `page` 和 `page_size` 查询参数（默认 20，最小 1，最大 50）。R20-P1-1 修复后切片 L1268-1269 已补 `page: int = Query(1, ge=1)` + `page_size: int = Query(20, le=50)`，但 `page_size` Query **缺失 `ge=1` 约束**，与同切片 L1223 `Query(default=20, ge=1, le=50)` 风格不一致，违反 API §1.2 L46 "page_size 默认 20，最小 1，用户端最大 50" + API L5974 "分页参数 MUST 使用 `Query(default=..., ge=1)` 校验"。详见 R21-P3-1。

### 4.3 响应 Schema 字段一致性

**结论**：❌ 部分通过（含 R21-P1-1 + R21-P2-1 + R21-P2-2 三处分歧）

- 93/96 端点响应 Schema 字段在 API 设计文档 ↔ 后端切片 Pydantic Response Model ↔ 前端 TypeScript interface 三方一致。
- **§2.1 wechat-login 响应**：API §2.1 L171 返回 `requires_consent: bool`（true = 需同意）；后端 `LoginResponse` L222 `requires_consent: bool = False`；前端 wechatLogin L162 读取 `consented`（不存在字段），三方分歧。详见 R21-P1-1。
- **§2.2 phone-login 响应**：API §2.2 L219 引用 §2.1 格式（`requires_consent`）；后端 `phone_login` 复用 `LoginResponse`；前端 phoneLogin L186 读取 `consented`（不存在字段），三方分歧。详见 R21-P1-1。
- **§8.7 训练单列表响应**：API §8.7 L2388-2394 期望 `id`/`session_index`/`name`/`reps`/`is_completed`/`completed_at`；后端 `TrainingSessionBrief` L480-489 实际 `id`/`plan_id`/`name`/`is_completed`/`scheduled_date`/`completed_at`（缺 `session_index` + `reps`，多 `plan_id` + `scheduled_date`）；前端 `TrainingSessionItem` L112-120 与后端一致但与 API 不一致。详见 R21-P2-1。
- **§8.8 训练单完成响应**：API §8.8 L2421-2424 期望 `session_id`/`is_completed`/`plan_progress: int 0-100`/`points_earned`；后端 `TrainingSessionCompleteResponse` L505-509 实际 `session_id`/`is_completed`/`plan_progress: float 0.0-1.0`/`points_earned`/`completed_at`（类型分歧 + 多 `completed_at`）；前端 `CompleteSessionData` L131-136 `plan_progress: number  // 0-100`（与 API 期望一致，与后端类型不一致）。详见 R21-P2-2。

### 4.4 错误码一致性（通用 + 业务码）

**结论**：✅ 通过

- 通用错误码：API §1.7 列出 8 个通用错误码（400/401/403/404/409/422/429/500），切片统一使用 `AppException(message, status_code)` 抛出，覆盖 71 处 `raise AppException` 调用（含 admin 18 处），grep `raise HTTPException` 全切片 0 匹配（R18-P3-12 修复无回归）。
- 业务错误码：每个端点在 API 设计中显式列出"错误情况"表（HTTP 码 / 条件 / 消息），切片实现一致。
- AI 推理（ai_inference.md）：8 处 `raise AppException(..., 503/504)` 与 API §4.10 错误码表一致。

### 4.5 限流配置一致性（API §1.5 vs 切片 @limiter）

**结论**：✅ 通过

| 端点 | API §1.5 | 切片 | 一致性 |
|------|---------|------|--------|
| POST /auth/wechat-login | 10/min | L587 `10/minute` | ✅ |
| POST /auth/phone-login | 5/min | L593 `5/minute` | ✅ |
| POST /auth/send-sms | 1/min | L599 `1/minute`（key_func=phone） | ✅ |
| POST /auth/h5-exchange | 10/min | L587 `10/minute`（R19-P1-1 修复） | ✅ |
| POST /auth/consent | 10/min | L655 `10/minute` | ✅ |
| POST /video-analysis/tasks | 10/hour | L1160 `10/hour`（key_func=user） | ✅ |
| POST /video-analysis/reports/{id}/share | 5/天 | L1256 `5/day`（key_func=user） | ✅ |
| POST /gamification/checkin | 1/天 | L1092 `1/day`（key_func=user） | ✅ |
| POST /admin/login | 5/min | L872 `5/minute` | ✅ |
| 其他端点 | 100/min | 全部 `100/minute` | ✅ |
| POST /payment/notify | —（微信回调） | 无 limiter（SEC-006） | ✅ |

### 4.6 分页参数一致性（page_size le=50/100）

**结论**：⚠️ 部分通过（含 R21-P3-1 风格不一致）

| 类型 | 切片 | page_size 约束 | 一致性 |
|------|------|--------------|--------|
| 用户端 | video_analysis（3 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | scoring（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | match_data（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | user（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | payment（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | notification（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | progress_analysis（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | training_advice §8.3 templates（1 处，L1223） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | training_advice §8.7 sessions（1 处，L1269） | `Query(20, le=50)` **缺 `ge=1`** | ⚠️ 见 R21-P3-1 |
| 用户端 | data_dashboard（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 管理端 | admin（2 处：list_users、list_audit_logs） | `Query(default=20, ge=1, le=100)` | ✅ |

### 4.7 model_validate 注入完整性

**结论**：✅ 通过

切片对 service 层返回的数据广泛使用 `model_validate` 注入，覆盖 10 个业务切片 + admin：

| 切片 | model_validate 使用情况 | 一致性 |
|------|----------------------|--------|
| 01-auth | —（简单 dict 返回 + ConsentResponse 直接构造） | ✅ |
| 02-user | RatingHistoryItem.model_validate（L527） | ✅ |
| 03-video_analysis | ReportDetailResponse.model_validate（L853） | ✅ |
| 04-scoring | MatchBrief/MatchDetailWithSequence.model_validate（L700/L716） | ✅ |
| 05-match_data | MatchRecordBrief/MatchRecordDetail.model_validate（L820/L844） | ✅ |
| 06-data_dashboard | MatchRecordBrief.model_validate（L692） | ✅ |
| 07-training_advice | TemplateBrief/TemplateDetail.model_validate（L779/L794）+ TrainingSessionBrief 直接构造（L1052-1059，因数据来自 plan_data JSON 不需 model_validate） | ✅ |
| 08-progress_analysis | SnapshotBrief + 4 处 model_validate_json（缓存） | ✅ |
| 09-gamification | —（简单 dict 返回） | ✅ |
| 10-membership | —（简单 dict 返回） | ✅ |
| 11-payment | OrderBrief.model_validate（L919） | ✅ |
| 12-notification | NotificationBrief.model_validate（L500） | ✅ |
| 13-admin | AdminBrief/UserManageBrief/ConfigBrief.model_validate（L396/L457/L523/L549/L579） | ✅ |

### 4.8 首页聚合 4 端点 + admin 17 端点三方一致

**结论**：✅ 通过

**首页聚合三方一致**（API §14a / 架构 §5.7 L947-956 / 前端 `00-home/frontend.md`）：

| 端点 | API §14a | 架构 §5.7 | 前端切片 |
|------|---------|----------|---------|
| GET /dashboard/overview | ✅ L3412 | ✅ L950 | ✅ 06-data_dashboard frontend L96 |
| GET /gamification/checkin-calendar | ✅ L3412 | ✅ L951 | ✅ 09-gamification frontend L96 |
| GET /scoring/matches | ✅ L3412 | ✅ L952 | ✅ 04-scoring frontend L57 |
| GET /notification/unread-count | ✅ L3412 | ✅ L953 | ✅ 12-notification frontend L76 |

**Admin 17 端点一致**：详见 §3.2 表格，路径/方法/参数/权限全部与 API §19 一致。

### 4.9 契约完整性（缺失端点/缺失参数/缺失响应字段）

**结论**：⚠️ 部分通过（含 R21-P1-1 + R21-P2-1 + R21-P2-2 契约缺口）

- **API ↔ 后端切片**：⚠️ §8.7 训练单 Brief 缺 `session_index` + `reps` 字段；§8.8 CompleteResponse.plan_progress 类型分歧（float vs int）
- **后端切片 ↔ 前端切片**：⚠️ 2 处契约缺口：
  - §2.1/§2.2 wechat-login/phone-login：前端读取 `consented` 字段，后端返回 `requires_consent`（R21-P1-1）
  - §8.8 训练单完成：前端 `CompleteSessionData.plan_progress: number  // 0-100`（与 API 一致），后端返回 float 0.0-1.0（与 API 不一致）（R21-P2-2）

### 4.10 安全性（输入验证/SQL 注入防护/CSRF）

**结论**：✅ 通过

- **输入验证**：全部端点使用 Pydantic Schema 注入（如 ConsentRequest、RefundRequest、AdminLoginRequest 等），自动校验类型/必填/枚举值/最大长度（如 `consent_type: str = Field(..., max_length=32)`、`policy_version: str = Field(..., max_length=16)`）。
- **SQL 注入防护**：全部切片使用 SQLAlchemy 2.0 ORM `select()` / `update()` 语句，无字符串拼接 SQL；grep `execute\(` + `f".*SELECT"` 无裸 SQL 残留。
- **CSRF**：JWT Bearer Token + H5 一次性 Token 认证（无 Cookie session），架构层面免疫 CSRF；管理员后台使用 session + 同源策略。
- **权限守卫**：`get_current_user`（登录端点）/ `require_membership("member")`（会员端点）/ `get_current_admin`（admin）/ `require_super_admin`（super admin）/ 微信支付回调 APIv3 证书验签 — 五层守卫完整。
- **限流**：100% 端点覆盖 `@limiter.limit()`（除 `POST /payment/notify` 微信回调豁免，SEC-006）。

---

## 5. consent 链路完整性（API → 后端 → 前端 service → store → UI → 跳转）

**结论**：❌ 链路中断（R21-P1-1 导致登录后强制跳转同意页）

### 5.1 链路全链路追踪

| 环节 | 状态 | 验证详情 |
|------|------|---------|
| API §2.9 POST /auth/consent | ✅ | API §2.9 L449-470 定义，Pydantic Schema `ConsentRequest` L201-202 校验 `consent_type`/`policy_version` |
| API §2.10 GET /auth/consent-status | ✅ | API §2.10 L485-510 定义，返回 `consented: bool`（true = 已同意） |
| API §2.1 POST /auth/wechat-login | ✅ | API §2.1 L171 返回 `requires_consent: bool`（true = 需同意，极性相反） |
| API §2.2 POST /auth/phone-login | ✅ | API §2.2 L219 引用 §2.1 格式（`requires_consent`） |
| 后端 ConsentResponse L204-207 | ✅ | `consented: bool` / `consent_at` / `policy_version`，与 API §2.10 一致 |
| 后端 LoginResponse L222 | ✅ | `requires_consent: bool = False`，与 API §2.1/§2.2 一致 |
| 后端 check_consent L463-483 | ✅ | 返回 `{"consented": bool, "consent_at": str, "policy_version": str}`，与 API 一致 |
| 后端 wechat_login L326-340 | ✅ | L327 `requires_consent = not consent["consented"]`（极性反转正确），L339 `requires_consent=requires_consent` |
| 后端 phone_login | ✅ | 复用 `LoginResponse`，同样返回 `requires_consent` |
| 后端 Route L588-591 wechat-login | ✅ | `data = await AuthService.wechat_login(body)`，返回 `LoginResponse` |
| 后端 Route L676-678 consent-status | ✅ | `data = await AuthService.check_consent(user.id)`，返回 `ConsentResponse` |
| 前端 service recordConsent L90-94 | ✅ | `request.post('/auth/consent', {...})` |
| 前端 service getConsentStatus L104 | ✅ | `request.get('/auth/consent-status')` |
| 前端 store recordConsent L247-264 | ✅ | 调 `authApi.recordConsent`，成功置 `needs_consent: false` |
| 前端 store checkConsentStatus L269-277 | ✅ | L272 `consented = !!res.data?.data?.consented`（与 API §2.10 一致），L274 `needs_consent = !consented`（极性反转正确） |
| 前端 store wechatLogin L157-179 | ❌ | L162 `const { ..., consented } = res.data.data`（**错误**：API §2.1 返回 `requires_consent` 非 `consented`），L168 `needs_consent: !consented`（`!undefined = true` 恒真），L172 `if (!consented) navigateTo consent`（恒真，所有用户都跳转） |
| 前端 store phoneLogin L181-203 | ❌ | L186 同 wechatLogin 错误 |
| 前端 consent 页面 L785-870 | ✅ | R20-P1-3 修复，组件完整，handleAgree 调 recordConsent 成功跳首页 |
| 前端 路由配置 L560 | ✅ | R20-P1-3 修复，`'pages/auth/consent/index'` 已加入 pages 数组 |

### 5.2 链路中断点

**中断点**：前端 wechatLogin/phoneLogin 与 API 契约层（§2.1/§2.2 响应字段）

- API §2.1/§2.2 响应字段名：`requires_consent: bool`（true = 需同意）
- 前端 wechatLogin/phoneLogin 读取字段名：`consented`（API 不返回此字段）
- 运行时行为：`consented = undefined`，`!consented = true`，所有用户登录后均被强制跳转 `/pages/auth/consent/index`
- 用户已同意场景：用户首次登录 → 跳转同意页 → 同意 → 跳转首页 → 退出登录 → 重新登录 → **再次跳转同意页**（即使已同意，因前端读取错误字段）
- 影响：PIPL 合规同意流程在"最后一公里"（登录跳转判断）中断，用户每次登录都被强制同意，违反 PIPL 第 14 条"已取得用户同意后不应重复要求"

详见 R21-P1-1。

---

## 6. 新发现 P0-P3 分级

### P0（阻断级） — 0 项

无。

### P1（严重级 — 影响契约一致性 / PIPL 合规 / 功能可用性） — 1 项

#### R21-P1-1：wechatLogin/phoneLogin 读取错误字段名 `consented`（应读 `requires_consent`，R20-P1-4 修复不正确）

- **位置**：
  - `docs/04详细设计/05-API详细设计.md` §2.1 L171（API 响应定义）、L183（API 字段说明）；§2.2 L219（API 响应引用 §2.1）
  - `docs/06垂直模块前后端切片设计/01-auth/backend.md` L222（`LoginResponse.requires_consent`）、L326-340（wechat_login 返回 requires_consent）、L343-?（phone_login 复用 LoginResponse）
  - `docs/06垂直模块前后端切片设计/01-auth/frontend.md` L162（wechatLogin 解构 consented）、L168（设置 needs_consent: !consented）、L172（if !consented navigateTo consent）、L186（phoneLogin 同样错误）、L192（同样设置）、L196（同样跳转）
- **现象**：API §2.1 wechat-login Response Body 实际返回字段名为 `requires_consent`（API §2.1 L171 `"requires_consent": false,` + L183 文档说明"新增 `requires_consent` 字段（boolean），表示用户是否需要签署隐私政策同意书"），后端 `LoginResponse` L222 同样定义 `requires_consent: bool = False`，L327-339 服务层逻辑 `requires_consent = not consent["consented"]` + `requires_consent=requires_consent` 返回此字段。

  但前端 R20-P1-4 修复时，**误用 §2.10 consent-status 的 `consented` 字段名**（极性相反字段）于 §2.1/§2.2 wechat-login/phone-login 响应解析：

```typescript
// 01-auth/frontend.md L157-179 wechatLogin
wechatLogin: async (code, nickname, avatarUrl) => {
  set({ isLoading: true })
  try {
    const res = await authApi.wechatLogin(code, nickname, avatarUrl)
    // R20-P1-4: 检查 consented 字段，未同意则跳转同意页（API §2.1 wechat-login 响应）
    const { access_token, refresh_token, user, consented } = res.data.data  // ❌ API 实际返回 requires_consent
    Taro.setStorageSync('access_token', access_token)
    Taro.setStorageSync('refresh_token', refresh_token)
    set({
      accessToken: ...,
      refreshToken: ...,
      user: { ...user, needs_consent: !consented },  // ❌ !undefined = true (恒真)
      isAuthenticated: true,
    })
    // R20-P1-4: consented=false 时跳转同意页，不进入首页
    if (!consented) {  // ❌ !undefined = true (恒真，所有用户都跳转)
      Taro.navigateTo({ url: '/pages/auth/consent/index' })
      return
    }
  } finally {
    set({ isLoading: false })
  }
},
```

phoneLogin（L181-203）存在相同错误。

- **API/后端/前端三方字段对比**：

| 字段 | API §2.1/§2.2（L171/L219） | 后端 LoginResponse（L222） | 后端 wechat_login 返回（L339） | 前端 wechatLogin 解构（L162） | 极性 |
|------|---------------------------|---------------------------|--------------------------------|------------------------------|------|
| `requires_consent` | ✅ bool（true=需同意） | ✅ bool = False | ✅ `requires_consent=requires_consent` | ❌ 未读取 | 一致 |
| `consented` | ❌ 不返回 | ❌ LoginResponse 无此字段 | ❌ 不返回 | ✅ 解构（实际为 undefined） | — |

- **运行时行为分析**：
  - 用户已同意场景（`requires_consent: false`）：
    - API 响应：`{ ..., "requires_consent": false, "user": {...} }`，**不含 `consented` 字段**
    - 前端解构：`const { ..., consented } = res.data.data` → `consented = undefined`
    - 设置 `needs_consent: !consented = !undefined = true`（错误置为"需同意"）
    - 判断 `if (!consented) = if (!undefined) = if (true)` → **强制跳转同意页**（错误，应进入首页）
  - 用户未同意场景（`requires_consent: true`）：
    - API 响应：`{ ..., "requires_consent": true, "user": {...} }`
    - 前端解构：`consented = undefined`
    - 设置 `needs_consent: !consented = true`（正确置为"需同意"）
    - 判断 `if (!consented) = if (true)` → 跳转同意页（行为正确但逻辑错误）
  - **结论**：两种场景下 `consented` 均为 `undefined`，前端无法区分，**所有用户登录后均被强制跳转同意页**

- **影响**：
  1. **PIPL 合规倒退**：已同意用户每次登录都被强制同意，违反 PIPL 第 14 条"已取得用户同意后不应重复要求"
  2. **用户体验严重退化**：用户每次登录需点击"同意并继续"按钮才能进入主页，严重影响登录流畅度
  3. **同意流程链路看似闭合但实际错误**：R20-P1-3 同意页 + R20-P1-2 checkConsentStatus 字段映射均正确，但 R20-P1-4 wechatLogin/phoneLogin 字段映射错误，导致同意流程"最后一公里"中所有用户都被错误路由至同意页
  4. **R20-P1-4 修复不正确**：R20-P1-4 建议第 (1) 项"在 wechatLogin action 中检查 `requires_consent` 跳转同意页面"未正确实现，实际读取了 §2.10 consent-status 的 `consented` 字段（极性相反字段）

- **建议**：
  - **修复方案 A（推荐，前端对齐 API）**：修改 wechatLogin（L162）+ phoneLogin（L186）字段解构：
    ```typescript
    // wechatLogin L162
    const { access_token, refresh_token, user, requires_consent } = res.data.data
    // ...
    user: { ...user, needs_consent: requires_consent },  // 直接赋值，极性一致
    // ...
    if (requires_consent) {  // true = 需同意
      Taro.navigateTo({ url: '/pages/auth/consent/index' })
      return
    }
    ```
    - phoneLogin L186 同步修改
    - 同步修改 L168 注释（"R20-P1-4"→"R21-P1-1 修复"）
  - **修复方案 B（不推荐，修改 API 设计为返回 `consented`）**：修改 API §2.1/§2.2 响应字段 `requires_consent` → `consented`（极性反转），后端 LoginResponse L222 同步修改 — **不推荐**，因为 API 设计是契约权威源，且 §2.1/§2.2 与 §2.10 字段语义不同（前者用于登录后立即判断、后者用于后续状态查询），保留 `requires_consent` 更符合 PIPL "需同意"语义
  - **附加修复**：L561 路由注释 "需 requires_consent=true 时由 wechatLogin/phoneLogin/checkConsentStatus 跳转至此页" 应同步更新为 "需 needs_consent=true 时由 wechatLogin/phoneLogin/checkConsentStatus 跳转至此页"（与 R20-P1-2 字段重命名保持一致）

### P2（中优先级 — 契约字段缺口 / 类型分歧，R20-P1-1 修复不完整） — 2 项

#### R21-P2-1：训练单 §8.7 Brief 缺失 `session_index` + `reps` 字段（R20-P1-1 修复不完整）

- **位置**：
  - `docs/04详细设计/05-API详细设计.md` §8.7 L2388-2394（API 响应示例，含 `session_index: 1` + `reps: 50`）
  - `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` L480-489（`TrainingSessionBrief` Pydantic Model 定义，缺 `session_index` + `reps`）
  - `docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` L112-120（`TrainingSessionItem` TypeScript interface 定义，缺 `session_index` + `reps`）
- **现象**：R20-P1-1 修复已对齐核心字段名（`session_id→id` / `title→name` / `status→is_completed` / `sessions→items`），但 **API §8.7 L2388-2394 明确要求返回 `session_index`（int，训练单序号）和 `reps`（int，次数）字段**，后端 `TrainingSessionBrief` 和前端 `TrainingSessionItem` 均未定义这两个字段。

  **API §8.7 Response Body L2386-2394 三方字段对比**：

  | 字段 | API §8.7 L2388-2394 | 后端 TrainingSessionBrief L480-489 | 前端 TrainingSessionItem L112-120 | 一致性 |
  |------|---------------------|------------------------------------|-----------------------------------|--------|
  | `id` | ✅ L2388 | ✅ L483 | ✅ L113 | ✅ |
  | `session_index` | ✅ L2389 | ❌ 缺失 | ❌ 缺失 | ❌ |
  | `name` | ✅ L2390 | ✅ L485 | ✅ L115 | ✅ |
  | `reps` | ✅ L2391 | ❌ 缺失 | ❌ 缺失 | ❌ |
  | `is_completed` | ✅ L2392 | ✅ L486 | ✅ L117 | ✅ |
  | `completed_at` | ✅ L2393 | ✅ L488 | ✅ L118 | ✅ |
  | `plan_id` | ❌ 不在 API | ✅ L484（额外） | ✅ L114（额外） | ⚠️ additive |
  | `scheduled_date` | ❌ 不在 API | ✅ L487（额外） | ✅ L116（额外） | ⚠️ additive |
  | `exercises` | ❌ 不在 API | ❌ 缺失 | ✅ L119（optional） | ⚠️ frontend only |

- **后端 Service 实现 L1051-1060**：

```python
all_items = [
    TrainingSessionBrief(
        id=s.get("id", i + 1),
        plan_id=plan_id,
        name=s.get("title", s.get("name", f"训练单 {i + 1}")),
        is_completed=s.get("status") == "completed" or s.get("is_completed", False),
        scheduled_date=s.get("scheduled_date"),
        completed_at=s.get("completed_at"),
        # ❌ 缺失：session_index=s.get("session_index", i + 1),
        # ❌ 缺失：reps=s.get("reps", 0),
    )
    for i, s in enumerate(sessions)
]
```

  Service 从 `plan_data.sessions` JSON 读取数据时也未读取 `session_index` / `reps` 字段（即使数据源可能包含这些字段，Service 也不会传递给 Brief）。

- **影响**：
  1. **API 契约缺失字段**：API §8.7 明确要求返回 `session_index` 和 `reps`，但后端实际响应不含这两个字段，前端 TypeScript interface 也不期望这两个字段，三方契约对 `session_index` / `reps` 字段全部分歧
  2. **训练单 UI 信息不完整**：训练方案详情页 L1144-1190 渲染 session 时仅显示 `name` / `is_completed` / `scheduled_date` / `completed_at`，**无法显示训练单序号（"第 N 次"）和次数（"50 次"）**，与模板详情页 L1013-1014 显示 `session.reps` 的行为不一致
  3. **R20-P1-1 修复不完整**：R20-P1-1 建议方案 A 第 (1) 项"后端 `TrainingSessionBrief` 改字段名为 `id` / `session_index` / `name` / `reps` / `is_completed: bool` / `completed_at`，与 API §8.7 完全对齐"，但实际修复仅对齐 `id` / `name` / `is_completed` / `completed_at`，**遗漏 `session_index` + `reps` 两个 API 设计明确要求的字段**

- **建议**：
  - **后端 TrainingSessionBrief 补字段**：
    ```python
    class TrainingSessionBrief(BaseModel):
        id: int
        session_index: int  # R21-P2-1: 补 API §8.7 L2389 字段
        plan_id: int  # 保留（additive）
        name: str
        reps: int  # R21-P2-1: 补 API §8.7 L2391 字段
        is_completed: bool
        scheduled_date: Optional[str] = None  # 保留（additive）
        completed_at: Optional[datetime] = None
        model_config = {"from_attributes": True}
    ```
  - **Service list_training_sessions 补字段读取**：
    ```python
    all_items = [
        TrainingSessionBrief(
            id=s.get("id", i + 1),
            session_index=s.get("session_index", i + 1),  # R21-P2-1
            plan_id=plan_id,
            name=s.get("title", s.get("name", f"训练单 {i + 1}")),
            reps=s.get("reps", 0),  # R21-P2-1
            is_completed=s.get("status") == "completed" or s.get("is_completed", False),
            scheduled_date=s.get("scheduled_date"),
            completed_at=s.get("completed_at"),
        )
        for i, s in enumerate(sessions)
    ]
    ```
  - **前端 TrainingSessionItem 补字段**：
    ```typescript
    export interface TrainingSessionItem {
      id: number
      session_index: number  // R21-P2-1: 补 API §8.7 字段
      plan_id: number
      name: string
      reps: number  // R21-P2-1: 补 API §8.7 字段
      scheduled_date: string
      is_completed: boolean
      completed_at: string | null
      exercises?: string[]
    }
    ```
  - **训练方案详情页 L1144-1190 补渲染**：在 session 卡片内补显示 `session.session_index`（如 "第 {session_index} 次"）+ `session.reps`（如 "次数：{reps}"），与模板详情页 L1013-1014 风格一致

#### R21-P2-2：训练单 §8.8 CompleteResponse.plan_progress 类型分歧（int 0-100 vs float 0.0-1.0，R20-P1-1 修复不完整）

- **位置**：
  - `docs/04详细设计/05-API详细设计.md` §8.8 L2423（API 响应示例 `"plan_progress": 70`，int 0-100 百分比）
  - `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` L507（`plan_progress: float  # 取值范围 0.0-1.0`，float 0-1 比例）
  - `docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` L134（`plan_progress: number  // 0-100`，与 API 一致）
  - `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` L1113（Service 实现 `plan_progress = completed / total`，float 0.0-1.0）
  - `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` L1143（`TrainingSessionCompleteResponse(plan_progress=plan_progress)` 直接返回 float）
- **现象**：R20-P1-1 修复已对齐 CompleteResponse 主要字段（`session_id` / `is_completed` / `points_earned`），但 **`plan_progress` 类型三方分歧**：

  | 维度 | API §8.8 L2423 | 后端 CompleteResponse L507 | 前端 CompleteSessionData L134 | 后端 Service 返回 L1113/L1143 | 一致性 |
  |------|---------------|---------------------------|-------------------------------|-------------------------------|--------|
  | 类型 | `int` | `float` | `number` | `float`（`completed/total`） | ❌ |
  | 取值范围 | 0-100（百分比） | 0.0-1.0（比例） | 0-100（百分比，注释明确） | 0.0-1.0 | ❌ |
  | 示例值 | `70` | `0.7` | `70` | `0.7` | ❌ |

  - 后端 `TrainingSessionCompleteResponse.plan_progress: float` L507 注释 "取值范围 0.0-1.0"
  - 后端 Service L1113 `plan_progress = completed / total if total > 0 else 0.0`（float 0.0-1.0）
  - 后端 L1143 `TrainingSessionCompleteResponse(plan_progress=plan_progress)` 直接返回 float（未执行 `int(plan_progress * 100)` 转换）
  - 前端 `CompleteSessionData.plan_progress: number  // 0-100` 注释期望 0-100 整数百分比，与 API §8.8 一致，但与后端实际返回类型不一致

- **运行时行为分析**：
  - 后端实际返回：`{ "session_id": 1, "is_completed": true, "plan_progress": 0.7, "points_earned": 5, "completed_at": "..." }`（float 0.7）
  - 前端 TypeScript 类型期望：`plan_progress: number  // 0-100`（int 0-100）
  - 当前训练方案详情页 L1137 `Progress percent={progressPercent}` 使用本地计算的 `progressPercent`（L1129 `Math.round((completedCount / totalCount) * 100)`），**不使用 API 返回的 plan_progress**，所以 UI 显示正确
  - 但若后续 UI 修改为直接显示 `result.plan_progress`（如 toast 显示 "方案进度 70%"），将显示为 "方案进度 0.7%"（错误）

- **影响**：
  1. **API 契约类型分歧**：API §8.8 设计期望 int 0-100，后端实际返回 float 0.0-1.0，三方（API/后端/前端）类型与取值范围不一致
  2. **未来 UI 接入风险**：当前 UI 不依赖 API 返回的 plan_progress（使用本地计算），但若后续 UI 修改为直接渲染 `result.plan_progress`，将显示错误数值
  3. **R20-P1-1 修复不完整**：R20-P1-1 建议方案 A 第 (3) 项"`TrainingSessionCompleteResponse` 字段改为 `session_id` / `is_completed: bool` / `plan_progress: int` / `points_earned: int`" + 第 (7) 项"`plan_progress` 统一返回 int 百分比（`int(plan_progress * 100)`）"，但实际修复仍保留 `float 0.0-1.0`，**未执行类型转换**

- **建议**：
  - **方案 A（推荐，后端对齐 API）**：
    ```python
    class TrainingSessionCompleteResponse(BaseModel):
        session_id: int
        is_completed: bool = True
        plan_progress: int  # R21-P2-2: float→int，对齐 API §8.8 L2423
        points_earned: int
        completed_at: Optional[datetime] = None

    # Service L1143 修改
    return TrainingSessionCompleteResponse(
        session_id=session_id,
        is_completed=True,
        plan_progress=int(plan_progress * 100),  # R21-P2-2: float→int 百分比
        points_earned=points_earned,
        completed_at=now,
    )
    ```
  - **方案 B（不推荐，修改 API 设计为 float）**：修改 API §8.8 L2423 `"plan_progress": 0.7` + L2436 "重新计算方案整体进度 `plan_progress`（float 0.0-1.0）"，前端同步修改 L134 注释 — **不推荐**，因为 API 设计是契约权威源，且 int 百分比更符合人类阅读习惯

### P3（低优先级 — 参数校验风格不一致） — 1 项

#### R21-P3-1：§8.7 sessions 路由 page_size Query 缺失 `ge=1` 约束（R20-P1-1 修复风格不一致）

- **位置**：
  - `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` L1269（`page_size: int = Query(20, le=50)`，缺 `ge=1`）
  - 对比：L1223（§8.3 templates）`page_size: int = Query(default=20, ge=1, le=50)` ✅
  - 对比：API §1.2 L46 "page_size 默认 20，最小 1，用户端最大 50"
  - 对比：API §1.2 L5974 "分页参数 MUST 使用 `Query(default=..., ge=1)` 校验"
- **现象**：R20-P1-1 修复 §8.7 sessions 路由时，`page_size` Query 参数写为 `Query(20, le=50)`，**缺失 `ge=1` 约束**，与同切片 L1223 `Query(default=20, ge=1, le=50)` 风格不一致，违反 API §1.2 L46 + L5974 强制要求。

  ```python
  # L1223 §8.3 templates（正确风格）
  page_size: int = Query(default=20, ge=1, le=50),

  # L1268-1269 §8.7 sessions（错误风格，缺 ge=1）
  page: int = Query(1, ge=1),  # ✅ 有 ge=1
  page_size: int = Query(20, le=50),  # ❌ 缺 ge=1
  ```

- **运行时影响**：
  - 用户传 `page_size=0` 或 `page_size=-1` 不会被 FastAPI 拒绝
  - Service L1065-1067 分页逻辑：
    ```python
    page_start = (page - 1) * page_size  # 若 page_size=0，则 page_start = (page-1)*0 = 0
    page_end = page_start + page_size  # page_end = 0
    items = all_items[page_start:page_end]  # all_items[0:0] = []（空列表）
    ```
  - 用户传 `page_size=-1` 时 `all_items[0:-1]` 返回除最后一个外的所有项（行为异常）

- **影响**：
  1. **API §1.2 强制规范违反**：L5974 "分页参数 MUST 使用 `Query(default=..., ge=1)` 校验" 为 MUST 级强制要求，L1269 缺 `ge=1` 违反此规范
  2. **风格不一致**：同切片内 L1223 与 L1269 风格不统一，影响代码可维护性
  3. **参数校验漏洞**：允许 `page_size=0` 或负数，导致分页行为异常（空列表或异常切片）

- **建议**：
  - 修改 L1269：
    ```python
    page_size: int = Query(default=20, ge=1, le=50),  # R21-P3-1: 补 ge=1，与 L1223 + API §1.2 一致
    ```

---

## 7. 修复跟踪表

### 7.1 R21 新发现修复跟踪

| 编号 | 优先级 | 修复项 | 涉及文件 | 状态 |
|------|--------|--------|---------|------|
| R21-P1-1 | P1 | wechatLogin/phoneLogin 字段名 `consented` → `requires_consent` + 极性逻辑修正 | 前端 `01-auth/frontend.md` L162/L168/L172（wechatLogin）+ L186/L192/L196（phoneLogin）+ L561 注释 | 待修复 |
| R21-P2-1 | P2 | 训练单 Brief 补 `session_index` + `reps` 字段 | 后端 `07-training_advice/backend.md` L480-489（Schema）+ L1051-1060（Service 构造）+ 前端 `07-training_advice/frontend.md` L112-120（interface）+ L1144-1190（UI 渲染） | 待修复 |
| R21-P2-2 | P2 | CompleteResponse.plan_progress 类型 `float 0.0-1.0` → `int 0-100` | 后端 `07-training_advice/backend.md` L507（Schema）+ L1113（Service 计算）+ L1143（Service 返回） | 待修复 |
| R21-P3-1 | P3 | §8.7 sessions 路由 page_size Query 补 `ge=1` | 后端 `07-training_advice/backend.md` L1269 | 待修复 |

### 7.2 R20 修复回归通过率汇总

| R20 编号 | 修复项 | R21 验证结果 |
|---------|--------|------------|
| R20-P1-1 | 训练单 §8.7/§8.8 三方契约对齐 | ⚠️ 部分闭环（核心字段名 + 分页参数 + Complete Response 主字段已对齐，但 Brief 缺 `session_index`/`reps` + plan_progress 类型仍 float → 衍生 R21-P2-1 + R21-P2-2） |
| R20-P1-2 | checkConsentStatus 读取 `consented` 字段（极性反转） | ✅ 完全闭环 |
| R20-P1-3 | consent 同意页 + 路由配置 | ✅ 完全闭环 |
| R20-P1-4 | wechatLogin/phoneLogin 跳转同意页 | ❌ 修复不正确（读取错误字段名 `consented`，应读 `requires_consent` → 衍生 R21-P1-1） |
| R20-P2-1 | 训练方案详情页 UI 接入 | ✅ 完全闭环 |
| R20-P2-2 | R18 需求报告 L81/L91 闭环注 | ✅ 完全闭环 |

**R20 6 项 P2+ 修复回归通过率**：4/6 完全闭环（66.7%）+ 1/6 部分闭环（16.7%）+ 1/6 修复不正确（16.7%）

### 7.3 累计修复统计

| 维度 | R20 累计 | R21 新增 | R21 累计 |
|------|---------|---------|---------|
| API 维度新发现 | 7 | 4 | 4（R20 6 项中 4 闭环 + 1 部分闭环 + 1 修复不正确，新发现 4 项） |
| 全维度累计修复（R19→R20） | — | 待定 | 待 R21 全维度汇总 |

### 7.4 连续两轮无 P2+ 进度跟踪

| 目标 | 状态 | 说明 |
|------|------|------|
| 连续两轮无 P2+（API 维度） | **第一轮仍未达成** | R21 API 维度新发现 P1×1 + P2×2 + P3×1，未达到"零 P2+"状态。R20-P1-4 修复不正确衍生 R21-P1-1，R20-P1-1 部分闭环衍生 R21-P2-1/P2-2。需先修复 R21-P1-1 + R21-P2-1/P2-2 共 3 项 P2+，再进入 R22 第一轮验证 |
| 连续两轮无 P2+（DB 维度） | 第一轮完成（R20-DB 报告） | DB 维度零 P2+ 新发现 |
| 连续两轮无 P2+（后端跨模块安全维度） | 第一轮完成（R20-后端报告） | 后端维度零 P0-P3 新发现 |
| 连续两轮无 P2+（架构维度） | 第一轮完成（R20-架构报告） | 架构维度零 P2+ 新发现 |
| 连续两轮无 P2+（前端 UX 维度） | 由 R21-前端设计系统 UX 审查报告承接 | — |

---

## 8. 审查结论

### 8.1 整体评价

本轮审查覆盖 12 项审查清单，核心一致性维度（路径/方法/权限/限流/分页参数/model_validate/安全性/错误码）大部分维持，但发现 R20 6 项 P2+ 修复中 1 项（R20-P1-4 wechatLogin/phoneLogin 跳转逻辑）存在**字段名错误**——前端读取 §2.10 consent-status 的 `consented` 字段名（极性相反字段）误用于 §2.1/§2.2 wechat-login/phone-login 响应解析，导致所有用户登录后均被强制跳转同意页。同时 R20-P1-1 训练单三方契约对齐**修复不完整**——核心字段名已对齐但 Brief 缺失 `session_index`/`reps` 字段、`plan_progress` 类型仍为 float 与 API §8.8 期望 int 0-100 分歧。

### 8.2 关键结论

1. **R20 6 项 P2+ 修复回归通过率 66.7%（4/6 完全闭环）**，相比 R19→R20 回归（77.8% 完全闭环 + 22.2% 部分闭环）有所下降，主要原因为 R20-P1-4 修复在字段映射时混淆了 §2.1/§2.2 的 `requires_consent` 与 §2.10 的 `consented` 两个极性相反字段，未充分对照 API 设计的响应字段定义。
2. **§2.1/§2.2 wechat-login/phone-login 响应字段三方分歧为新检出问题**（R21-P1-1），API/后端均返回 `requires_consent`，前端读取 `consented`（不存在字段），运行时将导致所有用户登录后被强制跳转同意页，**PIPL 合规同意流程"最后一公里"路由错误**。
3. **§8.7/§8.8 训练单端点三方契约部分分歧**（R21-P2-1 + R21-P2-2）：核心字段名已对齐（R20-P1-1 修复完成部分），但 Brief 缺 `session_index`/`reps` 字段、`plan_progress` 类型仍为 float vs API int 0-100 分歧，需进一步对齐 API §8.7/§8.8 完整字段定义。
4. **API 维度连续第一轮无 P2+ 目标未达成**，需先修复 R21-P1-1 + R21-P2-1 + R21-P2-2 共 3 项 P2+ 问题，再进入 R22 第一轮验证。

### 8.3 待跟踪项

| 编号 | 类别 | 跟踪点 | 验证方式 |
|------|------|--------|---------|
| R21-P1-1 | 字段映射 | wechatLogin/phoneLogin 读取 `requires_consent` 字段 | R22 grep `requires_consent` / `consented` 在 frontend.md L162/L186，验证字段名正确 |
| R21-P2-1 | 契约对齐 | TrainingSessionBrief 包含 `session_index` + `reps` 字段 | R22 grep `session_index` / `reps` 在 backend.md L480-489 + frontend.md L112-120 |
| R21-P2-2 | 类型对齐 | CompleteResponse.plan_progress 为 `int 0-100` | R22 grep `plan_progress` 在 backend.md L507（应为 `int`）+ L1143（应为 `int(plan_progress * 100)`） |
| R21-P3-1 | 参数校验 | §8.7 sessions 路由 page_size Query 含 `ge=1` | R22 grep `Query\(20, le=50\)` 在 backend.md L1269（应改为 `Query(default=20, ge=1, le=50)`） |

### 8.4 下一轮建议

1. **R22 验证目标**：修复 R21-P1-1 + R21-P2-1 + R21-P2-2 + R21-P3-1 共 4 项问题后，进入 R22 第一轮"零 P2+"验证。若 R22 也达到零 P2+，则 API 维度正式达成"连续两轮无 P2+"目标。
2. **修复优先级建议**：
   - **第一批（P1，立即修复）**：R21-P1-1（wechatLogin/phoneLogin 字段名修正，2 处 action 各 3 行代码修改）— PIPL 合规同意流程"最后一公里"路由修正，一次性闭合同意流程
   - **第二批（P2，立即修复）**：R21-P2-1（训练单 Brief 补 `session_index`/`reps` 字段，三方联动：后端 Schema + Service + 前端 interface + UI 渲染）+ R21-P2-2（CompleteResponse.plan_progress 类型转换 `float → int`，后端 Schema + Service 计算）— 训练单 §8.7/§8.8 三方契约完整对齐，与 R20-P1-1 残留问题联动修复
   - **第三批（P3，后续修复）**：R21-P3-1（page_size Query 补 `ge=1`，1 行代码修改）— 参数校验风格统一
3. **审查方法改进建议**：R21 检出的 R21-P1-1 为 R20-P1-4 修复不正确衍生问题，R20 审查时验证了跳转逻辑的存在性，但未核对响应字段映射一致性。建议 R22 审查时**对涉及多端点共享概念（如 consent 状态在 §2.1/§2.2/§2.10 三个端点）的字段映射，必须按端点逐一核对 API 设计文档响应字段定义、后端 Pydantic Model 字段、前端 service 解构字段三方一致**，避免字段名混淆（特别是极性相反字段如 `requires_consent` vs `consented`）。

---

## 9. 附录：审查证据文件索引

| 文件 | 用途 | 关键行号 |
|------|------|---------|
| `docs/04详细设计/05-API详细设计.md` | API 设计 v1.3 端点权威源 | §2.1 L137-199（wechat-login）、§2.2 L200-228（phone-login）、§2.9 L437-484（consent）、§2.10 L485-512（consent-status）、§8.7 L2363-2407（sessions list）、§8.8 L2408-2449（session complete）、§1.2 L46/L49/L5974（page_size 规范） |
| `docs/03系统架构/01-系统架构设计.md` §5.7 | Phase 1 端点清单 | L803-957（96 端点完整列表） |
| `docs/06垂直模块前后端切片设计/01-auth/backend.md` | 认证切片后端实现 | L201-202（ConsentRequest）、L204-207（ConsentResponse）、L218-222（LoginResponse.requires_consent）、L326-340（wechat_login 服务）、L343-?（phone_login 服务）、L463-483（check_consent）、L588-591（wechat-login 路由）、L676-678（consent-status 路由） |
| `docs/06垂直模块前后端切片设计/01-auth/frontend.md` | 认证切片前端实现 | L118-148（AuthUser/AuthState interface + actions）、L157-179（wechatLogin action）、L181-203（phoneLogin action）、L245-264（recordConsent action）、L269-277（checkConsentStatus action）、L556-563（pages 路由数组，含 consent）、L785-870（ConsentPage 组件）、L945-951（i18n 条目） |
| `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` | 训练切片后端实现 | L480-509（TrainingSessionBrief/ListResponse/CompleteResponse Schema）、L1031-1076（list_training_sessions service）、L1078-1146（complete_training_session service）、L1264-1278（§8.7 sessions 路由）、L1281-1292（§8.8 complete 路由） |
| `docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` | 训练切片前端实现 | L70（template sessions）、L112-128（TrainingSessionItem/ListData interface）、L131-136（CompleteSessionData interface）、L274-289（store state + actions）、L417-444（actions 实现）、L1059-1200（训练方案详情页组件）、L1692-1700（pages 路由数组） |
| `docs/07审查报告/第二十轮/R20-API端点级审查报告.md` | R20 基线 | 全文 6 项 P2+ + 1 项 P3 |
| `docs/07审查报告/第十八轮/R18-需求覆盖度审查报告.md` | R20-P2-2 闭环验证 | L81（§2.5 末尾，含 R19 闭环注）、L93（P0-1 描述，含 R19 闭环注）、L387（§7 末尾闭环注） |

---

**报告生成完成时间**：2026-10-19
**审查覆盖范围**：12 项审查清单 + 96 端点完整性 + consent 链路全链路追踪
**关键发现**：P1×1 + P2×2 + P3×1 = 4 项新发现
**目标达成状态**：⚠️ API 维度连续第一轮无 P2+ 目标**未达成**（含 P1+P2 新发现）
