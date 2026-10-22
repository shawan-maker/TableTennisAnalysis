# API 详细设计与后端垂直切片端点一致性审查报告

> **审查范围**：API 详细设计 v1.3（§2–§13 Phase 1 + §14 WebSocket）与 12 个后端垂直切片的端点级一致性
> **审查维度**：端点路径、HTTP 方法、路径参数命名、请求/响应 Schema 字段差异
> **审查日期**：2026-10-13
> **审查基准**：`docs/04详细设计/05-API详细设计.md` v1.3 为契约源
> **切片目录**：`docs/06垂直模块前后端切片设计/01-auth` 至 `12-notification`

---

## 一、总览统计

### 1.1 端点数量对比

| 模块 | API 设计端点数（REST） | 后端切片端点数（REST） | 匹配 | 切片额外 | 匹配率 |
|------|----------------------|----------------------|------|---------|--------|
| §2 auth | 8 | 10 | 8 | 2 | 100% |
| §3 user | 9* | 8 | 8 | 0 | 89%¹ |
| §4 video_analysis | 11* | 12 | 12 | 0 | 100%² |
| §5 scoring | 10 | 10 | 10 | 0 | 100% |
| §6 data_dashboard | 5 | 5 | 5 | 0 | 100% |
| §7 match_data | 4 | 4 | 4 | 0 | 100% |
| §8 training_advice | 8 | 8 | 8 | 0 | 100% |
| §9 progress_analysis | 6 | 6 | 6 | 0 | 100% |
| §10 gamification | 4 | 4 | 4 | 0 | 100% |
| §11 membership | 3 | 3 | 3 | 0 | 100% |
| §12 payment | 4 | 4 | 4 | 0 | 100% |
| §13 notification | 4 | 4 | 4 | 0 | 100% |
| §14 WebSocket | 1 | 1 | 1³ | 0 | 100%³ |
| **合计** | **77** | **79** | **77** | **2** | — |

> ¹ §3.7 `GET /video-analysis/reports/{id}/feedbacks` 在 API 设计中列于 §3 User 模块下，但实际路由注册在 video_analysis 切片中（API 设计 §3.7 注释已说明模块归属），因此 user 切片仅实现 8/9，video_analysis 切片实现 12 个（11 from §4 + 1 from §3.7），两端合计无遗漏。
> ² 含 §3.7 端点，video_analysis 切片共 12 个端点。
> ³ WebSocket 端点路径一致（`/ws`），但认证方式存在差异（详见第二节第 5 项）。

### 1.2 总体结论

- **Phase 1 全部 76 个 REST 端点 + 1 个 WebSocket 端点均已在后端切片中实现**，端点路径与 HTTP 方法 100% 覆盖。
- **2 个切片额外端点**（`POST /auth/consent`、`GET /auth/consent-status`）未回写 API 设计文档。
- **1 个 API 设计提及但未正式定义的端点**（`POST /users/account/cancel-deletion`）在前后端均未实现/未正式定义。
- **6 类字段/参数级别差异**，主要集中在安全合规修复（SEC-001、SEC-002、PIPL-001）导致的 Schema 增强。

---

## 二、不一致详情表

### 2.1 路径参数命名不一致

API 设计统一使用泛化路径参数名 `{id}`、`{token}`，后端切片使用领域语义化参数名。此差异**不影响功能**（FastAPI 路由匹配仅关心参数位置，不关心名称），但会导致 OpenAPI 文档中参数名不一致，影响前端对接和 API 文档一致性。

| # | API 设计端点 | API 参数名 | 切片参数名 | 影响模块 | 严重度 |
|---|------------|-----------|-----------|---------|--------|
| 1 | `GET /video-analysis/tasks/{id}` | `{id}` | `{task_id}` | video_analysis | P3 |
| 2 | `GET /video-analysis/reports/{id}` | `{id}` | `{report_id}` | video_analysis | P3 |
| 3 | `POST /video-analysis/reports/{id}/feedback` | `{id}` | `{report_id}` | video_analysis | P3 |
| 4 | `GET /video-analysis/reports/{id}/feedbacks` (§3.7) | `{id}` | `{report_id}` | video_analysis | P3 |
| 5 | `GET /video-analysis/reports/{id}/annotated-video` | `{id}` | `{report_id}` | video_analysis | P3 |
| 6 | `POST /video-analysis/reports/{id}/share` | `{id}` | `{report_id}` | video_analysis | P3 |
| 7 | `GET /share/{token}` (§4.11) | `{token}` | `{share_token}` | video_analysis | P3 |
| 8 | `GET /scoring/matches/{id}` (§5.3) | `{id}` | `{match_id}` | scoring | P3 |
| 9 | `POST /scoring/matches/{id}/score` (§5.4) | `{id}` | `{match_id}` | scoring | P3 |
| 10 | `POST /scoring/matches/{id}/undo` (§5.5) | `{id}` | `{match_id}` | scoring | P3 |
| 11 | `POST /scoring/matches/{id}/finish` (§5.6) | `{id}` | `{match_id}` | scoring | P3 |
| 12 | `GET /scoring/matches/{id}/statistics` (§5.7) | `{id}` | `{match_id}` | scoring | P3 |
| 13 | `POST /scoring/matches/{id}/start` (§5.8) | `{id}` | `{match_id}` | scoring | P3 |
| 14 | `POST /scoring/matches/{id}/abandon` (§5.9) | `{id}` | `{match_id}` | scoring | P3 |
| 15 | `POST /scoring/matches/{id}/resume` (§5.10) | `{id}` | `{match_id}` | scoring | P3 |
| 16 | `GET /match-data/records/{id}` (§7.3) | `{id}` | `{record_id}` | match_data | P3 |
| 17 | `PATCH /match-data/records/{id}` (§7.4) | `{id}` | `{record_id}` | match_data | P3 |
| 18 | `GET /training/templates/{id}` (§8.4) | `{id}` | `{template_id}` | training_advice | P3 |
| 19 | `GET /training/plans/{id}/adjustments` (§8.5) | `{id}` | `{plan_id}` | training_advice | P3 |
| 20 | `POST /training/plans/{id}/re-evaluate` (§8.6) | `{id}` | `{plan_id}` | training_advice | P3 |
| 21 | `POST /payment/orders/{id}/refund` (§12.4) | `{id}` | `{order_id}` | payment | P3 |

> **备注**：以下端点参数名已与 API 设计一致，无需修改：
> - `GET /training/advice/{report_id}` (§8.1) — 双方均用 `{report_id}`
> - `GET /training/plans/{plan_id}/sessions` (§8.7) — 双方均用 `{plan_id}`
> - `POST /training/plans/{plan_id}/sessions/{session_id}/complete` (§8.8) — 双方均用 `{plan_id}` + `{session_id}`
> - `GET /progress/technique-trends/{metric}` (§9.3) — 双方均用 `{metric}`

> **P3 说明**：路径参数名差异不影响路由匹配和功能正确性，但影响 OpenAPI 文档和前端对接的参数名一致性。建议统一命名风格。

---

### 2.2 LoginResponse Schema 字段差异（PIPL-001 修复）

| 项目 | API 设计 §2.1/§2.2 | auth 切片 | 差异类型 | 严重度 |
|------|-------------------|---------|---------|--------|
| `access_token` | ✅ | ✅ | — | — |
| `refresh_token` | ✅ | ✅ | — | — |
| `expires_in` | ✅ | ✅ | — | — |
| `user` (UserBrief) | ✅ | ✅ | — | — |
| `requires_consent` | ❌ 未定义 | ✅ `bool = False` | **切片新增字段** | P2 |

**详情**：auth 切片 `LoginResponse` 新增 `requires_consent: bool = False` 字段（PIPL-001 修复），用于前端判断是否需要弹出隐私政策同意弹窗。登录时检查 Redis 中用户是否已同意当前版本隐私政策，未同意则返回 `requires_consent=true`。

**影响**：前端需适配此字段；API 设计文档需回写此 Schema 变更。

---

### 2.3 Logout 请求体差异（SEC-001 修复）

| 项目 | API 设计 §2.5 | auth 切片 | 差异类型 | 严重度 |
|------|-------------|---------|---------|--------|
| Request Body | ❌ 未定义 | ✅ `LogoutRequest` | **切片新增请求体** | P2 |
| `access_token` | — | `str` (必填) | 新增 | P2 |
| `refresh_token` | — | `str` (可选) | 新增 | P2 |
| Response Body | `data: null` | `data: null` | — | — |

**详情**：API 设计 §2.5 logout 端点仅定义了响应体（`data: null`），未定义请求体。auth 切片新增 `LogoutRequest` 请求体（SEC-001 修复），要求客户端同时提交 `access_token`（必填）和 `refresh_token`（可选），服务端同时撤销两个 Token，防止 logout 后 refresh_token 仍可刷新。

**影响**：前端需适配请求体；API 设计文档需回写此 Schema 变更。

---

### 2.4 WebSocket 认证方式差异（SEC-002 修复）

| 项目 | API 设计 §14.1 | notification 切片 | 差异类型 | 严重度 |
|------|--------------|-----------------|---------|--------|
| 端点路径 | `/ws` | `/ws` | — | — |
| Token 传递方式 | URL Query: `?token=...` | Sec-WebSocket-Protocol 子协议: `['jwt.{token}']` | **认证方式变更** | P2 |
| 事件类型 | 12 种（connected/analysis_progress/...） | 同 API 设计 12 种 | — | — |
| 频道管理 | `ws:user:{user_id}`, `ws:match:{match_id}` | 同 API 设计 | — | — |

**详情**：API 设计 §14.1 规定 WebSocket 连接方式为 `wss://api.pingpongai.com/ws?token=...`（URL Query 参数传递 JWT）。notification 切片改为使用 `Sec-WebSocket-Protocol` 子协议传递 Token（SEC-002 修复），客户端连接方式为 `new WebSocket(url, ['jwt.' + token])`，从 WebSocket 子协议头提取 JWT，避免 URL 日志泄露 Token。

**影响**：前端 WebSocket 连接方式需适配；API 设计 §14.1 需回写认证方式变更。

---

### 2.5 POST /users/account/cancel-deletion 端点缺失

| 项目 | API 设计 | 模块详细设计 | user 前端切片 | user 后端切片 | 严重度 |
|------|---------|------------|-------------|-------------|--------|
| 端点定义 | ❌ 仅在 §3.6 业务规则中提及（line 622），**无正式端点定义**（无 `###` 标题） | ✅ 在行为描述中提及 | ✅ 前端调用 `request.post('/users/account/cancel-deletion')` | ❌ **未实现** | P1 |

**详情**：API 设计 §3.6 `DELETE /users/account` 的业务规则第 2 条提到"72h 内用户可登录撤销注销（`POST /users/account/cancel-deletion`）"，但该端点从未作为正式 API 端点定义（缺少 `###` 标题、请求/响应 Schema、错误码等）。模块详细设计（03-模块详细设计.md line 175）同样提及。user 前端切片已调用此端点，但 user 后端切片未实现该路由。

**影响**：
- **P1 功能缺失**：前端已调用但后端未实现，注销撤销功能不可用。
- API 设计文档需补充正式端点定义（请求/响应 Schema、错误码等）。
- user 后端切片需补充实现此端点。

---

## 三、切片额外端点（API 设计未定义）

以下端点在后端切片中已实现，但 API 设计文档中未定义。需回写 API 设计文档。

| # | 端点 | 所属切片 | 修复编号 | 用途 | 回写状态 | 严重度 |
|---|------|---------|---------|------|---------|--------|
| 1 | `POST /auth/consent` | 01-auth | PIPL-001 | 记录用户对当前版本隐私政策的同意（PIPL 第 14 条合规）。请求体 `ConsentRequest` 含 `consent_type` + `policy_version`，响应 `ConsentResponse` 含 `consented` + `consent_at` + `policy_version`。 | ❌ 未回写 | P2 |
| 2 | `GET /auth/consent-status` | 01-auth | PIPL-001 | 查询当前用户是否已同意最新版隐私政策。响应同 `ConsentResponse`。 | ❌ 未回写 | P2 |

**建议**：在 API 设计 §2 中新增 §2.9 和 §2.10 端点定义，回写请求/响应 Schema、错误码、业务规则。

---

## 四、API 设计缺失端点（提及但未正式定义/前端已调用但后端未实现）

| # | 端点 | 提及位置 | 前端调用 | 后端实现 | 正式定义 | 严重度 |
|---|------|---------|---------|---------|---------|--------|
| 1 | `POST /users/account/cancel-deletion` | API §3.6 业务规则 line 622；模块详细设计 line 175 | ✅ user frontend line 92 | ❌ user backend 未实现 | ❌ API 设计无 `###` 标题定义 | **P1** |

**建议**：
1. API 设计补充 `### 3.10 POST /users/account/cancel-deletion` 正式端点定义（请求/响应 Schema、错误码、业务规则）。
2. user 后端切片补充实现此端点（路由 `@router.post("/account/cancel-deletion")` + Service 方法 `cancel_account_deletion` + Schema `CancelDeletionResponse`）。

---

## 五、模块逐项对比详情

### 5.1 auth 模块（§2 ↔ 01-auth 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §2.1 POST /auth/wechat-login | `@router.post("/wechat-login")` | ✅ | ✅ | — | LoginResponse 新增 `requires_consent` |
| §2.2 POST /auth/phone-login | `@router.post("/phone-login")` | ✅ | ✅ | — | LoginResponse 新增 `requires_consent` |
| §2.3 POST /auth/send-sms | `@router.post("/send-sms")` | ✅ | ✅ | — | — |
| §2.4 POST /auth/refresh | `@router.post("/refresh")` | ✅ | ✅ | — | — |
| §2.5 POST /auth/logout | `@router.post("/logout")` | ✅ | ✅ | — | 新增 LogoutRequest 请求体 |
| §2.6 GET /auth/me | `@router.get("/me")` | ✅ | ✅ | — | — |
| §2.7 POST /auth/h5-token | `@router.post("/h5-token")` | ✅ | ✅ | — | — |
| §2.8 POST /auth/h5-exchange | `@router.post("/h5-exchange")` | ✅ | ✅ | — | — |
| — | `@router.post("/consent")` | 切片额外 | — | — | PIPL-001，API 未定义 |
| — | `@router.get("/consent-status")` | 切片额外 | — | — | PIPL-001，API 未定义 |

### 5.2 user 模块（§3 ↔ 02-user 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §3.1 GET /users/profile | `@router.get("/profile")` | ✅ | ✅ | — | — |
| §3.2 PATCH /users/profile | `@router.patch("/profile")` | ✅ | ✅ | — | — |
| §3.3 PATCH /users/rating | `@router.patch("/rating")` | ✅ | ✅ | — | — |
| §3.4 GET /users/rating-history | `@router.get("/rating-history")` | ✅ | ✅ | — | — |
| §3.5 GET /users/big-data | `@router.get("/big-data")` | ✅ | ✅ | — | — |
| §3.6 DELETE /users/account | `@router.delete("/account")` | ✅ | ✅ | — | cancel-deletion 端点未实现 |
| §3.8 POST /users/export-data | `@router.post("/export-data")` | ✅ | ✅ | — | — |
| §3.9 GET /users/export-data/{task_id} | `@router.get("/export-data/{task_id}")` | ✅ | ✅ | ✅ `task_id` 一致 | — |

> §3.7 `GET /video-analysis/reports/{id}/feedbacks` 在 video_analysis 切片中实现，见 5.3。

### 5.3 video_analysis 模块（§4 + §3.7 ↔ 03-video_analysis 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §4.1 POST /video-analysis/upload-token | `@router.post("/upload-token")` | ✅ | ✅ | — | — |
| §4.2 POST /video-analysis/upload-complete | `@router.post("/upload-complete")` | ✅ | ✅ | — | — |
| §4.3 POST /video-analysis/tasks | `@router.post("/tasks")` | ✅ | ✅ | — | — |
| §4.4 GET /video-analysis/tasks | `@router.get("/tasks")` | ✅ | ✅ | — | — |
| §4.5 GET /video-analysis/tasks/{id} | `@router.get("/tasks/{task_id}")` | ✅ | ✅ | ⚠ `{task_id}` ≠ `{id}` | — |
| §4.6 GET /video-analysis/reports/{id} | `@router.get("/reports/{report_id}")` | ✅ | ✅ | ⚠ `{report_id}` ≠ `{id}` | — |
| §4.7 GET /video-analysis/reports | `@router.get("/reports")` | ✅ | ✅ | — | — |
| §4.8 POST /video-analysis/reports/{id}/feedback | `@router.post("/reports/{report_id}/feedback")` | ✅ | ✅ | ⚠ `{report_id}` ≠ `{id}` | — |
| §3.7 GET /video-analysis/reports/{id}/feedbacks | `@router.get("/reports/{report_id}/feedbacks")` | ✅ | ✅ | ⚠ `{report_id}` ≠ `{id}` | — |
| §4.9 GET /video-analysis/reports/{id}/annotated-video | `@router.get("/reports/{report_id}/annotated-video")` | ✅ | ✅ | ⚠ `{report_id}` ≠ `{id}` | — |
| §4.10 POST /video-analysis/reports/{id}/share | `@router.post("/reports/{report_id}/share")` | ✅ | ✅ | ⚠ `{report_id}` ≠ `{id}` | — |
| §4.11 GET /share/{token} | `@share_router.get("/share/{share_token}")` | ✅ | ✅ | ⚠ `{share_token}` ≠ `{token}` | — |

### 5.4 scoring 模块（§5 ↔ 04-scoring 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §5.1 POST /scoring/matches | `@router.post("/matches")` | ✅ | ✅ | — | — |
| §5.2 GET /scoring/matches | `@router.get("/matches")` | ✅ | ✅ | — | — |
| §5.3 GET /scoring/matches/{id} | `@router.get("/matches/{match_id}")` | ✅ | ✅ | ⚠ `{match_id}` ≠ `{id}` | — |
| §5.4 POST /scoring/matches/{id}/score | `@router.post("/matches/{match_id}/score")` | ✅ | ✅ | ⚠ `{match_id}` ≠ `{id}` | — |
| §5.5 POST /scoring/matches/{id}/undo | `@router.post("/matches/{match_id}/undo")` | ✅ | ✅ | ⚠ `{match_id}` ≠ `{id}` | — |
| §5.6 POST /scoring/matches/{id}/finish | `@router.post("/matches/{match_id}/finish")` | ✅ | ✅ | ⚠ `{match_id}` ≠ `{id}` | — |
| §5.7 GET /scoring/matches/{id}/statistics | `@router.get("/matches/{match_id}/statistics")` | ✅ | ✅ | ⚠ `{match_id}` ≠ `{id}` | — |
| §5.8 POST /scoring/matches/{id}/start | `@router.post("/matches/{match_id}/start")` | ✅ | ✅ | ⚠ `{match_id}` ≠ `{id}` | — |
| §5.9 POST /scoring/matches/{id}/abandon | `@router.post("/matches/{match_id}/abandon")` | ✅ | ✅ | ⚠ `{match_id}` ≠ `{id}` | — |
| §5.10 POST /scoring/matches/{id}/resume | `@router.post("/matches/{match_id}/resume")` | ✅ | ✅ | ⚠ `{match_id}` ≠ `{id}` | — |

### 5.5 data_dashboard 模块（§6 ↔ 06-data_dashboard 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §6.1 GET /dashboard/overview | `@router.get("/overview")` | ✅ | ✅ | — | — |
| §6.2 GET /dashboard/win-rate-trend | `@router.get("/win-rate-trend")` | ✅ | ✅ | — | — |
| §6.3 GET /dashboard/technique-stats | `@router.get("/technique-stats")` | ✅ | ✅ | — | — |
| §6.4 GET /dashboard/landing-heatmap | `@router.get("/landing-heatmap")` | ✅ | ✅ | — | — |
| §6.5 GET /dashboard/match-records | `@router.get("/match-records")` | ✅ | ✅ | — | — |

> **完全一致，无差异。**

### 5.6 match_data 模块（§7 ↔ 05-match_data 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §7.1 POST /match-data/records | `@router.post("/records")` | ✅ | ✅ | — | — |
| §7.2 GET /match-data/records | `@router.get("/records")` | ✅ | ✅ | — | — |
| §7.3 GET /match-data/records/{id} | `@router.get("/records/{record_id}")` | ✅ | ✅ | ⚠ `{record_id}` ≠ `{id}` | — |
| §7.4 PATCH /match-data/records/{id} | `@router.patch("/records/{record_id}")` | ✅ | ✅ | ⚠ `{record_id}` ≠ `{id}` | — |

### 5.7 training_advice 模块（§8 ↔ 07-training_advice 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §8.1 GET /training/advice/{report_id} | `@router.get("/advice/{report_id}")` | ✅ | ✅ | ✅ 一致 | — |
| §8.2 GET /training/advice/contextual | `@router.get("/advice/contextual")` | ✅ | ✅ | — | — |
| §8.3 GET /training/templates | `@router.get("/templates")` | ✅ | ✅ | — | — |
| §8.4 GET /training/templates/{id} | `@router.get("/templates/{template_id}")` | ✅ | ✅ | ⚠ `{template_id}` ≠ `{id}` | — |
| §8.5 GET /training/plans/{id}/adjustments | `@router.get("/plans/{plan_id}/adjustments")` | ✅ | ✅ | ⚠ `{plan_id}` ≠ `{id}` | — |
| §8.6 POST /training/plans/{id}/re-evaluate | `@router.post("/plans/{plan_id}/re-evaluate")` | ✅ | ✅ | ⚠ `{plan_id}` ≠ `{id}` | — |
| §8.7 GET /training/plans/{plan_id}/sessions | `@router.get("/plans/{plan_id}/sessions")` | ✅ | ✅ | ✅ 一致 | — |
| §8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete | `@router.post("/plans/{plan_id}/sessions/{session_id}/complete")` | ✅ | ✅ | ✅ 一致 | — |

### 5.8 progress_analysis 模块（§9 ↔ 08-progress_analysis 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §9.1 GET /progress/snapshots | `@router.get("/snapshots")` | ✅ | ✅ | — | — |
| §9.2 GET /progress/technique-trends | `@router.get("/technique-trends")` | ✅ | ✅ | — | — |
| §9.3 GET /progress/technique-trends/{metric} | `@router.get("/technique-trends/{metric}")` | ✅ | ✅ | ✅ 一致 | — |
| §9.4 GET /progress/comparison | `@router.get("/comparison")` | ✅ | ✅ | — | — |
| §9.5 GET /progress/summary | `@router.get("/summary")` | ✅ | ✅ | — | — |
| §9.6 GET /progress/problem-changes | `@router.get("/problem-changes")` | ✅ | ✅ | — | — |

> **完全一致，无差异。**

### 5.9 gamification 模块（§10 ↔ 09-gamification 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §10.1 GET /gamification/points | `@router.get("/points")` | ✅ | ✅ | — | — |
| §10.2 GET /gamification/checkin-calendar | `@router.get("/checkin-calendar")` | ✅ | ✅ | — | — |
| §10.3 POST /gamification/checkin | `@router.post("/checkin")` | ✅ | ✅ | — | — |
| §10.4 GET /gamification/badges | `@router.get("/badges")` | ✅ | ✅ | — | — |

> **完全一致，无差异。**

### 5.10 membership 模块（§11 ↔ 10-membership 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §11.1 GET /membership/tiers | `@router.get("/tiers")` | ✅ | ✅ | — | — |
| §11.2 GET /membership/current | `@router.get("/current")` | ✅ | ✅ | — | — |
| §11.3 GET /membership/quota | `@router.get("/quota")` | ✅ | ✅ | — | — |

> **完全一致，无差异。**

### 5.11 payment 模块（§12 ↔ 11-payment 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §12.1 POST /payment/orders | `@router.post("/orders")` | ✅ | ✅ | — | — |
| §12.2 GET /payment/orders | `@router.get("/orders")` | ✅ | ✅ | — | — |
| §12.3 POST /payment/notify | `@router.post("/notify")` | ✅ | ✅ | — | — |
| §12.4 POST /payment/orders/{id}/refund | `@router.post("/orders/{order_id}/refund")` | ✅ | ✅ | ⚠ `{order_id}` ≠ `{id}` | — |

### 5.12 notification 模块（§13+§14 ↔ 12-notification 切片）

| API 端点 | 切片路由 | 方法 | 路径 | 参数 | Schema 差异 |
|---------|---------|------|------|------|------------|
| §13.1 GET /notification/list | `@router.get("/list")` | ✅ | ✅ | — | — |
| §13.2 POST /notification/read | `@router.post("/read")` | ✅ | ✅ | — | — |
| §13.3 POST /notification/subscribe | `@router.post("/subscribe")` | ✅ | ✅ | — | — |
| §13.4 GET /notification/unread-count | `@router.get("/unread-count")` | ✅ | ✅ | — | — |
| §14 WebSocket /ws | `@ws_router.websocket("/ws")` | ✅ | ✅ | — | ⚠ Token 传递方式不同（SEC-002） |

---

## 六、修复优先级汇总

| 优先级 | 编号 | 问题 | 修复建议 | 影响范围 |
|--------|------|------|---------|---------|
| **P1** | #1 | `POST /users/account/cancel-deletion` 端点：API 设计仅文字提及但无正式定义，前端已调用但后端未实现 | ①API 设计补充正式端点定义；②user 后端切片补充实现 | API 设计、user 后端切片 |
| **P2** | #2 | `LoginResponse.requires_consent` 字段：切片新增但 API 设计未定义 | API 设计 §2.1/§2.2 回写 `requires_consent` 字段 | API 设计 |
| **P2** | #3 | `LogoutRequest` 请求体：切片新增但 API 设计 §2.5 未定义请求体 | API 设计 §2.5 回写 `LogoutRequest` Schema | API 设计 |
| **P2** | #4 | WebSocket Token 传递方式：切片改用子协议（SEC-002），API 设计仍为 URL Query | API 设计 §14.1 回写认证方式变更 | API 设计 |
| **P2** | #5 | `POST /auth/consent` 端点：切片新增但 API 设计未定义 | API 设计 §2 新增 §2.9 端点定义 | API 设计 |
| **P2** | #6 | `GET /auth/consent-status` 端点：切片新增但 API 设计未定义 | API 设计 §2 新增 §2.10 端点定义 | API 设计 |
| **P3** | #7 | 路径参数命名不一致：21 个端点使用领域语义化参数名，API 设计统一用 `{id}`/`{token}` | 统一参数命名风格（建议 API 设计改用语义化名称，或切片改用 `{id}`） | API 设计 + 全部切片 |

---

## 七、结论

### 7.1 一致性总体评价

Phase 1 共 77 个 API 设计端点（76 REST + 1 WS）在后端切片中**全部实现**，端点路径和 HTTP 方法覆盖率 **100%**。存在的不一致均为**安全合规增强**（SEC-001/002、PIPL-001 修复）导致的 Schema 扩展和 1 个功能缺失（cancel-deletion 端点），不影响已实现端点的功能正确性。

### 7.2 需要回写 API 设计文档的变更

1. §2.1/§2.2 LoginResponse 新增 `requires_consent` 字段
2. §2.5 logout 新增 `LogoutRequest` 请求体（`access_token` 必填 + `refresh_token` 可选）
3. §14.1 WebSocket 认证方式从 URL Query 改为 Sec-WebSocket-Protocol 子协议
4. §2 新增 §2.9 `POST /auth/consent` 端点定义
5. §2 新增 §2.10 `GET /auth/consent-status` 端点定义
6. §3 新增 `POST /users/account/cancel-deletion` 正式端点定义

### 7.3 需要补充实现的后端切片

1. user 后端切片补充 `POST /users/account/cancel-deletion` 端点实现

### 7.4 路径参数命名风格统一建议

21 个端点存在路径参数名差异（`{id}` vs `{task_id}`/`{match_id}`/`{record_id}` 等）。建议统一为**领域语义化命名**（即 API 设计文档向切片靠拢），理由：
- 语义化命名更清晰（`match_id` 比 `{id}` 更具自文档性）
- 多参数端点避免歧义（如 `POST /training/plans/{plan_id}/sessions/{session_id}/complete` 两个参数必须语义化）
- FastAPI OpenAPI 文档直接使用路由参数名
