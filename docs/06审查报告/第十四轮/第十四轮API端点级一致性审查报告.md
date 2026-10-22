# 第十四轮 API 端点级一致性审查报告

> **审查代理**：第十四轮审查代理（API 端点维度）
> **审查日期**：2026-10-15
> **前序基线**：第十三轮 API 端点级一致性审查（1 项 P2 待修复：总览 L92 首页聚合描述）
> **审查范围**：第十三轮修复验证（1 项）+ 12 项深层检查（错误码表/统一响应格式/分页参数/认证依赖/请求体 Schema/响应 Schema/Admin 端点完整性/限流装饰器/HTMLResponse/路径命名/嵌套路由参数）
> **审查方法**：读取 API 设计 v1.3 全文 + 12 模块 backend.md 端点抽样 + 总览 §3.5 限流配置 + admin.md 17 端点 + video_analysis share_router + data_dashboard 5 端点，使用 grep 逐项交叉验证

---

## 第十三轮修复验证

| 编号 | 修复内容 | 验证结果 | 验证详情 |
|------|----------|----------|----------|
| R13-P2-1 | 总览 L92 首页聚合端点描述修正（"BFF 模式"→"前端聚合，无独立后端端点"） | ✅ 通过 | `00-垂直切片设计总览.md` L92：`首页 Dashboard 数据由前端并发请求多个已有 Phase 1 端点聚合而成（services/home.ts），无独立后端端点` — 未出现"BFF 模式"字样。API 设计 §14a（L3389）同步标注"前端聚合，无独立后端 API"，一致。 |

> **验证结论**：第十三轮 1 项修复通过，无回归。

---

## 深层检查结果

| # | 检查项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | §1.7/§1.8 错误码表完整性 | ✅ 基本完整 | 全局 7 条（40100/40101/40300/40400/42200/42900/50000）+ 业务 12 条（40010-42910），覆盖主要模块。部分端点 400/502 错误未分配对应业务 code，详见 P3-1。 |
| 2 | §1.8 统一响应格式一致性 | ✅ 一致 | 所有 JSON 端点使用 `{code, message, data, timestamp}` 格式。两个例外已显式标注：① `POST /payment/notify` 返回微信协议格式（§12.3 F7-1 说明）；② `GET /share/{share_token}` 返回 HTMLResponse（§4.11 "返回 HTML 渲染页面，非 JSON API"）。 |
| 3 | 分页参数 page/page_size 统一命名 | ✅ 一致 | 全部 14 个分页端点统一使用 `page`/`page_size`，无 `offset`/`limit` 混用。page_size 上限值：用户端切片 `le=50`（P1-API1 修复），admin 切片 `le=100`。API §1.2 已修正为"用户端最大 50，管理端最大 100"。 |
| 4 | 认证端点 Depends(get_current_user) | ✅ 一致 | 所有需认证端点均注入 `Depends(get_current_user)`。公开端点（auth 登录/发送短信/分享页/支付回调）无认证依赖。Admin 端点使用 `Depends(get_current_admin)` / `Depends(require_super_admin)`，与普通用户 JWT 体系隔离。 |
| 5 | POST/PUT/PATCH 端点请求体 Schema | ✅ 一致 | 所有变更类端点均有 Request Body 定义或显式标注无 body（如 undo/finish/start/abandon/resume/checkin/cancel-deletion/export-data/re-evaluate/session-complete）。POST /payment/notify 接收微信 V3 回调原始结构（非项目 Schema），已说明。 |
| 6 | 响应 Schema 字段一致性 | ✅ 一致 | 抽检关键端点：① video_analysis 任务响应双字段 `task_id`(int) + `task_uuid`(str) 与 §4.3-4.5 一致；② scoring 比赛详情 `score_sequence`/`current_score`/`current_server` 与 §5.3 一致；③ membership tiers 四级定价 `price_monthly/quarterly/yearly_cents` 与 §11.1 一致；④ admin 用户列表 `UserManageBrief` 字段与 §19.2.3 一致。 |
| 7 | Admin API §19 共 17 个端点在 admin.md 中的实现 | ✅ 完整 | API 设计 §19 列出 17 个端点（§19.2.1-19.2.5 认证+用户 5 个，§19.3.1-19.3.5 配置 5 个，§19.4.1 审计 1 个，§19.5.1-19.5.5 知识库 5 个，§19.6.1 模型版本 1 个）。admin.md 实现 16 个 Phase 1 端点（L873-L1051），第 17 个 `POST /admin/model-versions/{version_id}/activate` 注释为 Phase 2+ 占位（L1056-1065），与 API 设计 §19.6 "Phase 2+ 仅预留设计占位"一致。 |
| 8 | API 设计标注 @limiter.limit() 但切片缺失或值不一致 | ❌ → ✅ 已修复 | 发现 P1-1：`POST /video-analysis/reports/{report_id}/share` 实现为 `@limiter.limit("100/minute")`，与 API §1.5/§4.10 规定的"5/天"不一致。同类特殊限流已正确实现：AI 分析 `10/hour`（L1109 ✅），打卡 `1/day`（gamification L1074 ✅），短信 `1/minute`（auth L599 ✅）。**已修复**：改为 `@limiter.limit("5/day", key_func=lambda r: r.state.user)`。 |
| 9 | share_router GET /share/{share_token} HTMLResponse 在 API 设计中说明 | ✅ 已说明 | API 设计 §4.11（L1340-1361）显式标注"返回 HTML 渲染页面（非 JSON API）"并列出页面内容。切片 L1231 实现 `@share_router.get("/share/{share_token}", response_class=HTMLResponse)` 返回 `HTMLResponse(content=html)`，且 share_router 不挂载 `/api/v1` 前缀（L1252-1253），与公开访问设计一致。 |
| 10 | 端点路径复数/单数命名统一 | ✅ 基本一致 | 模块前缀命名规范：集合用复数（`/users`、`/matches`、`/tasks`、`/reports`、`/records`、`/orders`、`/configs`、`/badges`、`/tiers`），单资源用单数（`/auth`、`/dashboard`、`/training`、`/progress`、`/gamification`、`/membership`、`/payment`、`/notification`、`/admin`）。模块内路径命名风格统一。 |
| 11 | 嵌套路由路径参数命名一致性 | ✅ 一致 | 全部嵌套路由统一使用 `{resource}_id` 模式：`{match_id}`、`{report_id}`、`{task_id}`、`{record_id}`、`{order_id}`、`{plan_id}`、`{session_id}`、`{user_id}`、`{category_id}`、`{rule_id}`。字符串主键使用语义名：`{key}`、`{share_token}`、`{template_id}`、`{metric}`。无不一致。 |
| 12 | API 设计 §14a 首页聚合端点路径引用与实际 API 路径匹配 | ❌ → ✅ 已修复 | 发现 P2-1：§14a L3394 引用 4/5 处路径与实际 API 定义不匹配（`/user/profile`→`/users/profile`、`/scoring/matches/recent`→`/scoring/matches`、`/training/advice/active`→`/training/advice/contextual`、`/gamification/points/balance`→`/gamification/points`）。**已修复**：修正为实际 API 路径。 |

---

## 新发现问题

### P1-1: 报告分享端点限流装饰器与 API 设计不一致 ✅ 已修复

**级别**：P1

**位置**：`docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` L1205

**问题描述**：
API 设计 §1.5 限流配置表（L78）明确规定"报告分享 5/天 slowapi + Redis"，§4.10 端点定义（L1316）标注"限流：5/天"。但切片实现为 `@limiter.limit("100/minute")`，远超 5/天上限，存在被刷量风险。同类特殊限流端点（AI 分析 10/hour、打卡 1/day、短信 1/minute）均已正确实现，唯独分享端点遗漏。

**修复内容**：将 `@limiter.limit("100/minute")` 改为 `@limiter.limit("5/day", key_func=lambda r: r.state.user)`，与 gamification 打卡端点 `@limiter.limit("1/day", key_func=lambda r: r.state.user)` 保持模式一致。同时更新末尾限流说明注释（L1409）补充分享 5/day 例外。

---

### P2-1: §14a 首页聚合端点路径引用与实际 API 路径不匹配 ✅ 已修复

**级别**：P2

**位置**：`docs/04详细设计/05-API详细设计.md` L3394

**问题描述**：
API 设计 §14a（L3394）描述首页聚合调用的端点列表，但引用的路径与实际定义的 API 路径不一致：

| §14a 修正前引用路径 | 实际 API 路径 | 偏差 |
|--------------|-------------|------|
| `GET /user/profile` | `GET /users/profile`（§3.1） | 单数→复数 |
| `GET /scoring/matches/recent` | `GET /scoring/matches`（§5.2） | 多余 `/recent` 后缀 |
| `GET /training/advice/active` | `GET /training/advice/contextual`（§8.2） | `active`→`contextual` |
| `GET /gamification/points/balance` | `GET /gamification/points`（§10.1） | 多余 `/balance` 后缀 |
| `GET /notification/unread-count` | `GET /notification/unread-count`（§13.4） | ✅ 一致 |

**修复内容**：将 §14a L3394 的路径引用修正为实际 API 路径。

---

### P3-1: 部分端点 400/502 错误缺少业务错误码

**级别**：P3

**位置**：`docs/04详细设计/05-API详细设计.md` §1.7（L86-96）、§1.8（L101-118）

**问题描述**：
全局错误码表（§1.7）覆盖 401/403/404/422/429/500，业务错误码表（§1.8）覆盖 40010/40011/40310/40410-40414/40910/40911/42210/42910。但以下端点的 400/502 错误未在两张表中分配对应业务 code：

| 模块 | 端点 | HTTP | 条件 |
|------|------|------|------|
| Auth | §2.1 wechat-login | 400 | code 为空 |
| Auth | §2.1 wechat-login | 400 | code 无效 |
| Auth | §2.1 wechat-login | 502 | 微信 API 失败 |
| Auth | §2.2 phone-login | 400 | 手机号格式错误 |
| Auth | §2.2 phone-login | 400 | 验证码错误 |
| Scoring | §5.5 undo | 400 | 没有可撤销的记录 |
| Scoring | §5.8 start | 400 | 比赛不在 setup 状态 |
| Payment | §12.4 refund | 400 | 退款金额超出订单金额 |
| Payment | §12.4 refund | 400 | 订单状态非 paid |

**影响**：低。当前前端可通过 HTTP 状态码 + message 文本做基础处理，但无法按 code 做精细化错误分流。

**修复建议**：可为 400 类错误补充通用业务码 `40000`（通用业务错误）或扩展现有 `40011`（业务校验失败）覆盖范围，并在端点错误表中标注引用。502 可补充 `50200`（上游服务调用失败）。

---

### P3-2: API 设计 §1.2 分页 page_size 上限与切片实现不一致 ✅ 已修复

**级别**：P3

**位置**：`docs/04详细设计/05-API详细设计.md` §1.2（L46）

**问题描述**：
API 设计 §1.2 全局分页规范（L46）写"page_size 默认 20，最大 100"。第四轮 P1-API1 修复将 8 个用户端模块的切片实现从 `le=100` 改为 `le=50`（14 处），但未同步更新 API 设计 §1.2。

**修复内容**：将 §1.2 L46 改为"page_size 默认 20，用户端最大 50，管理端最大 100"。

---

## 结论

本轮审查覆盖 12 项深层检查 + 1 项第十三轮修复验证，全部通过。

新发现 4 个问题：
- **P1×1**：报告分享端点 `@limiter.limit("100/minute")` 应为 `@limiter.limit("5/day")` — ✅ 已修复
- **P2×1**：§14a 首页聚合端点路径引用 4 处不匹配实际 API 路径 — ✅ 已修复
- **P3×2**：部分 400/502 错误缺业务 code（未修复，低优先级）+ API §1.2 page_size 上限未同步更新 — ✅ 已修复 1 项

前十三轮累计修复 644 项，本轮修复 3 项（P1-1 + P2-1 + P3-2），累计 647 项。P3-1 留待后续处理。本轮未发现前序修复回归问题。
