# API 设计 — 切片端点级一致性审查报告（第九轮）

> **审查日期**：2026-10-14
> **审查范围**：API 详细设计 v1.3（§2-§17）vs 垂直切片后端设计 01-12（backend.md）+ 13-infrastructure（admin.md）
> **审查维度**：A. 端点覆盖度 B. 请求参数 C. 响应模式 D. 限流 E. 错误码 F. 认证/权限守卫 G. WebSocket H. 分享路由 I. 跨模块调用 J. 先前修复验证
> **审查类型**：只读审查（未修改任何源文件）
> **基线**：第八轮审查报告（2026-10-12，基于 API v1.2）

---

## 1. 总览

### 1.1 模块级一致性汇总

| # | 模块 | API 设计端点数 | 切片端点数 | 一致性 | 关键偏差 |
|---|------|:---:|:---:|:---:|------|
| 01 | auth | 10 | 10 | ⚠️ | consent 限流 10/min vs API 默认 100/min（P2） |
| 02 | user | 10 | 9 + 1† | ✅ | 无（†§3.7 feedbacks 在 video_analysis 切片中实现） |
| 03 | video_analysis | 12 | 12 | ⚠️ | 免费额度错误码 403→429（P1）；分享限流实现方式差异（P3） |
| 04 | scoring | 10 | 10 | ❌ | score/finish 状态机冲突 409→400（P1）；undo 额外状态校验（P2） |
| 05 | match_data | 4 | 4 | ❌ | PATCH 缺失 409 关联校验（P1）；缺失 updated_fields 响应字段（P2） |
| 06 | data_dashboard | 5 | 5 | ✅ | 无 |
| 07 | training_advice | 8 | 8 | ❌ | templates/adjustments 权限 登录→会员（P1）；re-evaluate 类型错误（P1）；session complete 错误码 400→409（P1）；响应字段不匹配（P2） |
| 08 | progress_analysis | 6 | 6 | ✅ | 无 |
| 09 | gamification | 4 | 4 | ✅ | 无 |
| 10 | membership | 3 | 3 | ✅ | 无 |
| 11 | payment | 4 | 4 | ⚠️ | refund 超 7 天错误码 400→422（P1） |
| 12 | notification | 4 | 5 | ✅ | 无（含 WebSocket /ws） |
| 13 | admin (infra) | 0 | 17 | ⚠️ | 17 个管理端点未在 API 设计中定义（P2） |
| — | websocket (§14) | 1 | 1 | ✅ | Sec-WebSocket-Protocol 认证一致 |
| | **合计** | **80** | **97** | | 核心端点 80=80 完全匹配；admin 17 端点待回写 |

### 1.2 偏差统计

| 偏差类型 | 数量 | 严重程度分布 |
|---------|:---:|------|
| 错误码不一致（HTTP 状态码） | 7 | P1×5, P2×2 |
| 权限守卫不一致 | 4 | P1×3, P2×1 |
| 响应字段不匹配 | 2 | P2×2 |
| 限流不一致 | 2 | P2×1, P3×1 |
| 管理端点未文档化 | 1 | P2×1 |
| 限流实现方式差异 | 1 | P3×1 |

### 1.3 第八轮修复验证

| # | 第八轮偏差 | 当前状态 | 验证结果 |
|---|---------|:---:|------|
| 1 | scoring start/abandon/resume 多余端点 | ✅ 已修复 | API v1.3 §5.8-5.10 已定义，切片 10=10 一致 |
| 2 | auth 限流 wechat 100→10/min, phone 100→5/min | ✅ 已修复 | 切片 wechat-login 10/minute, phone-login 5/minute |
| 3 | video_analysis task_id 类型不一致 | ✅ 已修复 | API v1.3 §4.3 双字段设计 task_id(int)+task_uuid(str)，切片一致 |
| 4 | training sessions 多余端点 | ✅ 已修复 | API v1.3 §8.7-8.8 已定义，切片一致 |
| 5 | match_data PATCH 多余端点 | ✅ 已修复 | API v1.3 §7.4 已定义，切片一致 |
| 6 | progress summary 缓存 1h→5min | ✅ 已修复 | API v1.3 §9.5 缓存标注 5min，切片 300s 一致 |
| 7 | membership 字段名 price_monthly→cents | ✅ 已修复 | API v1.3 §11.1 使用 _cents 后缀，切片一致 |
| 8 | comparison landing 结构不一致 | ✅ 已修复 | API v1.3 §9.4 landing 为结构化 per-metric 格式 |
| 9 | notification unread-count 多余端点 | ✅ 已修复 | API v1.3 §13.4 已定义，切片一致 |
| 10 | share/{token} 缺失端点 | ✅ 已修复 | 切片 share_router GET /share/{share_token} 已实现 |
| 11 | feedbacks 端点归属不清 | ✅ 已修复 | 切片注释标明"API 设计 §3.7"，归属明确 |

> **结论**：第八轮全部 11 项偏差已在 API v1.3 和切片中完成修复。本轮审查未发现修复回退。

---

## 2. P0 — 阻断级偏差

> 无 P0 级偏差。核心端点覆盖度 100%（80/80），无关键功能缺失或安全漏洞。

---

## 3. P1 — 高优先级偏差

### P1-1：scoring score/finish 状态机冲突错误码 409→400

| 项 | 内容 |
|---|---|
| **模块** | 04-scoring |
| **维度** | E. 错误码 |
| **API 设计** | §5.4 score 错误表：`409 | 比赛不在进行中 | 比赛未在进行中`；§5.6 finish 错误表：`409 | 比赛不在进行中 | 比赛未在进行中`；§1.8 业务错误码 40910 定义为"比赛不在进行中（状态机冲突）" |
| **切片实现** | `backend.md:726` `raise AppException("比赛未在进行中", 400)`（score 端点）；`backend.md:904` `raise AppException("比赛未在进行中", 400)`（finish 端点） |
| **影响** | 状态机冲突（setup/finished/abandoned 状态下调用 score 或 finish）应返回 409 Conflict，切片使用 400 Bad Request。前端无法区分"参数错误"与"状态冲突"，无法做差异化提示（如 409→提示"比赛已结束"）。undo 端点也有同样问题（`backend.md:823`）。 |
| **修复建议** | 将 `backend.md` 第 726、823、904 行的 `400` 改为 `409`，与 API 设计 §5.4/§5.5/§5.6 和业务错误码 40910 对齐。 |

### P1-2：video_analysis 免费额度耗尽错误码 403→429

| 项 | 内容 |
|---|---|
| **模块** | 03-video_analysis |
| **维度** | E. 错误码 |
| **API 设计** | §4.3 tasks POST 错误表：`429 | 免费额度用完 | 今日免费分析次数已用完，升级会员可无限分析`；§1.8 业务错误码 42910 定义为"免费分析额度耗尽" |
| **切片实现** | `backend.md:654` `raise AppException("今日免费分析次数已用完，升级会员可无限分析", 403)` |
| **影响** | 免费额度耗尽应返回 429 Too Many Requests，切片使用 403 Forbidden。前端无法触发 429→引导升级会员弹窗的差异化交互，因为 403 通常表示权限不足而非额度限制。 |
| **修复建议** | 将 `backend.md:654` 的 `403` 改为 `429`，与 API 设计 §4.3 和业务错误码 42910 对齐。 |

### P1-3：training_advice session complete 已完成错误码 400→409

| 项 | 内容 |
|---|---|
| **模块** | 07-training_advice |
| **维度** | E. 错误码 |
| **API 设计** | §8.8 错误表：`409 | 训练单已完成 | 该训练单已完成` |
| **切片实现** | `backend.md:1085` `raise AppException("训练单已完成", 400)` |
| **影响** | 重复完成训练单属于冲突状态（资源已处于目标状态），应返回 409 Conflict。切片使用 400 Bad Request，前端无法区分"请求参数错误"与"资源状态冲突"。 |
| **修复建议** | 将 `backend.md:1085` 的 `400` 改为 `409`，与 API 设计 §8.8 对齐。 |

### P1-4：training_advice templates/adjustments 权限 登录→会员

| 项 | 内容 |
|---|---|
| **模块** | 07-training_advice |
| **维度** | F. 认证/权限守卫 |
| **API 设计** | §8.3 GET /training/templates 权限：**登录**；§8.4 GET /training/templates/{template_id} 权限：**登录**；§8.5 GET /training/plans/{plan_id}/adjustments 权限：**登录** |
| **切片实现** | `backend.md:1160-1161` templates 同时使用 `get_current_user` + `require_membership("member")`；`backend.md:1172-1173` templates/{id} 同上；`backend.md:1182-1183` adjustments 同上 |
| **影响** | API 设计标记这三个端点为"登录"权限（普通用户可访问），但切片额外添加了 `require_membership("member")` 会员守卫（SEC-003 修复）。非会员用户无法访问模板列表、模板详情和调整历史，与 API 契约不符。 |
| **修复建议** | 方案 A（推荐）：更新 API 设计 §8.3-8.5 权限标注为"会员"，与切片的 SEC-003 安全策略对齐。方案 B：移除切片中这三个端点的 `require_membership("member")` 守卫，仅保留 `get_current_user`，与 API 设计"登录"权限对齐。 |

### P1-5：training_advice re-evaluate 类型不匹配

| 项 | 内容 |
|---|---|
| **模块** | 07-training_advice |
| **维度** | F. 认证/权限守卫 |
| **API 设计** | §8.6 POST /training/plans/{plan_id}/re-evaluate 权限：会员 |
| **切片实现** | `backend.md:1192` `user: User = Depends(require_membership("member"))` |
| **影响** | `require_membership("member")` 返回的是权限守卫依赖（通常返回 None 或布尔值），而非 `User` 对象。将其赋值给 `user: User` 类型注解会导致类型不匹配，运行时 `user.id` 调用将失败（AttributeError）。该端点随后调用 `TrainingAdviceService.re_evaluate_plan(user.id, plan_id)` 依赖 `user.id`，将直接崩溃。 |
| **修复建议** | 改为与其他会员端点一致的模式：`user: User = Depends(get_current_user)` + `_membership = Depends(require_membership("member"))`（参见 `backend.md:1203-1204` 的正确写法）。 |

### P1-6：match_data PATCH 缺失 409 关联记分牌校验

| 项 | 内容 |
|---|---|
| **模块** | 05-match_data |
| **维度** | E. 错误码 + B. 请求参数 |
| **API 设计** | §7.4 业务规则 3："若比赛记录关联了记分牌比赛（match_id 不为空），返回 409 禁止编辑"；错误表：`409 | 比赛记录已关联记分牌，不可编辑 | 关联记分牌的记录不可直接编辑`；§1.8 业务错误码 40911 定义为"比赛记录已关联记分牌，不可直接编辑" |
| **切片实现** | `backend.md:831-867` `update_record` 方法仅校验记录存在性（404）和空更新（422），**未校验** `record.match_id is not None` |
| **影响** | 用户可以编辑已关联记分牌的比赛记录，导致记分牌数据与比赛记录数据不一致。违反 API 设计的安全约束。 |
| **修复建议** | 在 `backend.md:847` 之后、`backend.md:849` 之前添加：`if record.match_id is not None: raise AppException("关联记分牌的记录不可直接编辑", 409)` |

### P1-7：payment refund 超 7 天错误码 400→422

| 项 | 内容 |
|---|---|
| **模块** | 11-payment |
| **维度** | E. 错误码 |
| **API 设计** | §12.4 业务规则："下单 7d 后：不支持退款，返回 422"；§1.8 业务错误码定义 422 为"请求参数业务校验失败" |
| **切片实现** | `backend.md:1203` `raise AppException("超过7天的订单不可退款", 400)` |
| **影响** | 超 7 天退款限制属于业务规则校验（非类型校验），应返回 422 Unprocessable Entity。切片使用 400 Bad Request。前端无法区分"参数格式错误"与"业务规则不允许"。注意：API 设计 §12.4 错误表中未显式列出此 422（仅在业务规则文字中提及），API 设计本身存在不一致。 |
| **修复建议** | ① 将 `backend.md:1203` 的 `400` 改为 `422`。② 在 API 设计 §12.4 错误情况表中补充 `422 | 下单超过 7d，不支持退款 | 超过7天的订单不可退款`。 |

---

## 4. P2 — 中优先级偏差

### P2-1：training_advice session complete 响应字段不匹配

| 项 | 内容 |
|---|---|
| **模块** | 07-training_advice |
| **维度** | C. 响应模式 |
| **API 设计** | §8.8 响应：`{"session_id": 1, "is_completed": true, "plan_progress": 70, "points_earned": 5}` |
| **切片实现** | `backend.md:1112-1117` 返回 `TrainingSessionCompleteResponse(session_id, status="completed", completed_at, plan_progress: float)` |
| **差异** | ① 缺失 `is_completed` (bool)，切片使用 `status` (str "completed") — 字段名和类型均不同；② 缺失 `points_earned` (int) — API 设计包含积分奖励反馈；③ 多出 `completed_at` (datetime) — API 设计未定义；④ `plan_progress` 类型不一致 — 切片 float 0.0-1.0，API 设计 int 百分比（如 70） |
| **修复建议** | ① 将 `TrainingSessionCompleteResponse` 的 `status: str` 改为 `is_completed: bool`；② 添加 `points_earned: int` 字段（从 gamification add_points 返回值获取）；③ 移除 `completed_at` 或回写 API 设计；④ 将 `plan_progress` 从 float 改为 int 百分比（`int(plan_progress * 100)`）。 |

### P2-2：match_data PATCH 缺失 updated_fields 响应字段

| 项 | 内容 |
|---|---|
| **模块** | 05-match_data |
| **维度** | C. 响应模式 |
| **API 设计** | §7.4 响应：`{"id": 5001, "is_win": true, "updated_fields": ["opponent_name", "opponent_rating", "notes"]}` |
| **切片实现** | `backend.md:867` 返回 `{"id": record.id, "is_win": record.is_win}` |
| **差异** | 缺失 `updated_fields` 数组字段 — 前端无法得知哪些字段被实际更新，无法做精准 UI 刷新。 |
| **修复建议** | 在 `backend.md:849` 获取 `update_data = data.model_dump(exclude_unset=True)` 后，将 `list(update_data.keys())` 作为 `updated_fields` 加入返回值。 |

### P2-3：auth consent 限流 10/min vs API 默认 100/min

| 项 | 内容 |
|---|---|
| **模块** | 01-auth |
| **维度** | D. 限流 |
| **API 设计** | §2.9 POST /auth/consent 未标注"限流"字段，按 §1.5 全局默认 100 req/min |
| **切片实现** | `backend.md:655` `@limiter.limit("10/minute")` |
| **影响** | 切片限流（10/min）比 API 设计默认（100/min）严格 10 倍。虽然更严格的安全性是合理的，但与 API 契约不一致，高并发场景下可能导致正常用户被限流。 |
| **修复建议** | 方案 A（推荐）：在 API 设计 §2.9 补充"限流：10/min"标注，与切片对齐（consent 涉及隐私政策签署，严格限流合理）。方案 B：将切片限流改为 `100/minute`，与 API 设计全局默认对齐。 |

### P2-4：scoring undo 额外状态校验 + 错误码

| 项 | 内容 |
|---|---|
| **模块** | 04-scoring |
| **维度** | E. 错误码 |
| **API 设计** | §5.5 undo 错误表仅列：409（比分已更新）+ 400（无可撤销记录）。未列出"比赛未在进行中"错误。 |
| **切片实现** | `backend.md:822-823` 额外添加 `if match.status not in ("in_progress"): raise AppException("比赛未在进行中", 400)` |
| **影响** | 切片添加了 API 设计未定义的状态校验，使用 400 而非 409（§1.8 业务错误码 40910 适用于所有状态机冲突）。虽属合理防御性编程，但 API 契约未覆盖此场景。 |
| **修复建议** | ① 在 API 设计 §5.5 undo 错误表中补充 `409 | 比赛不在进行中 | 比赛未在进行中`；② 将 `backend.md:823` 的 `400` 改为 `409`，与业务错误码 40910 对齐。 |

### P2-5：admin 17 个管理端点未在 API 设计中定义

| 项 | 内容 |
|---|---|
| **模块** | 13-infrastructure |
| **维度** | A. 端点覆盖度 |
| **API 设计** | §2-§17 未包含管理后台 API 端点定义 |
| **切片实现** | `admin.md` 实现 17 个端点：POST /admin/login, POST /admin/logout, GET /admin/users, POST /admin/users/{id}/ban, POST /admin/users/{id}/unban, GET/POST /admin/configs, GET/PATCH/DELETE /admin/configs/{key}, GET /admin/audit-logs, POST/PATCH/DELETE /admin/knowledge/categories, POST /admin/knowledge/rules, PATCH /admin/knowledge/rules/{id}/toggle |
| **影响** | 管理后台 API 契约缺失，前端管理端无法依据 API 设计文档开发。17 个端点的请求/响应结构、错误码、限流规则仅在切片中定义。 |
| **修复建议** | 在 API 设计文档中新增 §14A 管理后台模块，定义所有 17 个端点的请求/响应/错误码/限流。或单独编写管理后台 API 设计文档。 |

---

## 5. P3 — 低优先级偏差

### P3-1：video_analysis share 限流实现方式差异

| 项 | 内容 |
|---|---|
| **模块** | 03-video_analysis |
| **维度** | D. 限流 |
| **API 设计** | §4.10 "限流：5/天"；§1.5 "报告分享：5/天 slowapi + Redis" |
| **切片实现** | `backend.md:1189` `@limiter.limit("100/minute")` + 服务层 Redis 日计数器 `backend.md:972` `raise AppException("今日分享次数已用完", 429)` |
| **影响** | 每日 5 次限制通过服务层 Redis 计数器实现而非 slowapi 装饰器。行为等效（达到 5 次/天后返回 429），但实现方式与 API 设计 §1.5 标注的 "slowapi + Redis" 不完全一致。 |
| **修复建议** | 当前实现合理（slowapi 不擅长跨天计数），建议更新 API 设计 §1.5 标注为"服务层 Redis 计数器"，与切片对齐。无需修改切片。 |

### P3-2：admin login 限流 API 设计未定义

| 项 | 内容 |
|---|---|
| **模块** | 13-infrastructure |
| **维度** | D. 限流 |
| **API 设计** | §1.5 限流表未列出管理员登录的限流规则 |
| **切片实现** | `admin.md:831` `@limiter.limit("5/minute")`（管理员登录），其余 16 个端点 100/minute |
| **影响** | 管理员登录 5/minute 的严格限流是合理的安全措施，但 API 设计未定义。 |
| **修复建议** | 在 API 设计 §1.5 限流表中补充"管理员登录：5/min slowapi + Redis"，与切片对齐。 |

### P3-3：video_analysis share 额外 429 错误未在 API 设计中定义

| 项 | 内容 |
|---|---|
| **模块** | 03-video_analysis |
| **维度** | E. 错误码 |
| **API 设计** | §4.10 share 错误表：仅列 404（报告不存在）|
| **切片实现** | `backend.md:972` `raise AppException("今日分享次数已用完", 429)` |
| **影响** | 切片实现了分享次数限制的 429 错误，但 API 设计 §4.10 错误表未列出此场景。 |
| **修复建议** | 在 API 设计 §4.10 错误表中补充 `429 | 今日分享次数已用完 | 今日分享次数已用完`。 |

---

## 6. 已对齐项汇总

以下模块/维度完全一致，无偏差：

| # | 模块 | 端点数 | 一致项 |
|---|------|:---:|------|
| 1 | user | 9+1 | 端点路径、HTTP 方法（PATCH /profile, PATCH /rating, DELETE /account）、参数、响应结构完全一致 |
| 2 | data_dashboard | 5/5 | 端点路径、缓存策略（overview 5min）、参数完全一致 |
| 3 | progress_analysis | 6/6 | 端点路径、缓存策略（summary 5min）、comparison landing 结构化格式一致 |
| 4 | gamification | 4/4 | 端点路径、限流（checkin 1/day）、参数、响应结构完全一致 |
| 5 | membership | 3/3 | 端点路径、字段名（_cents 后缀）、权限完全一致 |
| 6 | payment（除 refund 7d 外） | 4/4 | 端点路径、权限（notify 无 JWT, refund 需 admin）、参数一致 |
| 7 | notification | 4+1 | 端点路径、WebSocket /ws Sec-WebSocket-Protocol 认证、事件类型完全一致 |
| 8 | video_analysis（除 free quota 外） | 12/12 | 端点路径、双字段 task_id+task_uuid、share_router 实现一致 |
| 9 | auth（除 consent 限流外） | 10/10 | 端点路径、限流（wechat 10/min, phone 5/min, sms 1/min）、参数一致 |
| 10 | scoring（除状态码外） | 10/10 | 端点路径、状态机端点（start/abandon/resume）完全一致 |

### 跨模块调用一致性

| 调用方 | 被调方 | 签名 | 状态 |
|--------|--------|------|:---:|
| training_advice | gamification | `add_points(db, user_id=, event_type="training_session", ref_id=)` | ✅ 关键字参数 |
| video_analysis | gamification | `add_points(event_type="analysis")` | ✅ 关键字参数 |
| payment | notification | `push_ws_message(user_id, event_type, data)` | ✅ 统一接口 |
| training_advice | notification | `push_ws_message(user_id, event_type, data)` | ✅ 统一接口 |

---

## 7. 修复建议优先级排序

| 优先级 | 修复项 | 动作类型 | 目标文档 |
|:---:|------|---------|---------|
| P1 | scoring score/finish/undo 状态机 400→409 | 修改切片 | 04-scoring/backend.md L726,823,904 |
| P1 | video_analysis 免费额度 403→429 | 修改切片 | 03-video_analysis/backend.md L654 |
| P1 | training session complete 400→409 | 修改切片 | 07-training_advice/backend.md L1085 |
| P1 | training templates/adjustments 权限对齐 | 更新 API 设计或切片 | 05-API详细设计.md §8.3-8.5 或 07-training_advice/backend.md L1161,1173,1183 |
| P1 | training re-evaluate 类型修复 | 修改切片 | 07-training_advice/backend.md L1192 |
| P1 | match_data PATCH 补 409 校验 | 修改切片 | 05-match_data/backend.md L847 后 |
| P1 | payment refund 7d 错误码 400→422 | 修改切片 + 更新 API | 11-payment/backend.md L1203 + 05-API详细设计.md §12.4 |
| P2 | training session complete 响应字段对齐 | 修改切片 | 07-training_advice/backend.md L497-502,1112-1117 |
| P2 | match_data PATCH 补 updated_fields | 修改切片 | 05-match_data/backend.md L867 |
| P2 | auth consent 限流对齐 | 更新 API 设计或切片 | 05-API详细设计.md §2.9 或 01-auth/backend.md L655 |
| P2 | scoring undo 补 API 错误表 + 400→409 | 更新 API + 修改切片 | 05-API详细设计.md §5.5 + 04-scoring/backend.md L823 |
| P2 | admin 17 端点回写 API 设计 | 回写 API 设计 | 05-API详细设计.md 新增 §14A |
| P3 | share 限流标注更新 | 更新 API 设计 | 05-API详细设计.md §1.5 |
| P3 | admin login 限流回写 | 更新 API 设计 | 05-API详细设计.md §1.5 |
| P3 | share 429 错误表补充 | 更新 API 设计 | 05-API详细设计.md §4.10 |

---

## 8. 端点级逐模块对比明细

### 8.1 auth 模块（10/10 一致，限流⚠️）

| # | API 设计 | 切片 | 方法 | 路径 | 权限 | 限流 | 状态 |
|---|---------|------|------|------|------|------|:---:|
| 1 | §2.1 | L587 | POST | /auth/wechat-login | 公开 | 10/min=10/min | ✅ |
| 2 | §2.2 | L593 | POST | /auth/phone-login | 公开 | 5/min=5/min | ✅ |
| 3 | §2.3 | L599 | POST | /auth/send-sms | 公开 | 1/min=1/min | ✅ |
| 4 | §2.4 | L605 | POST | /auth/refresh | refresh_token | 100/min | ✅ |
| 5 | §2.5 | L611 | POST | /auth/logout | 登录 | 100/min | ✅ |
| 6 | §2.6 | L625 | GET | /auth/me | 登录 | 100/min | ✅ |
| 7 | §2.7 | L642 | POST | /auth/h5-token | 登录 | 100/min | ✅ |
| 8 | §2.8 | L648 | POST | /auth/h5-exchange | H5 Token | 100/min | ✅ |
| 9 | §2.9 | L655 | POST | /auth/consent | 登录 | 100/min→10/min | ⚠️ P2-3 |
| 10 | §2.10 | L674 | GET | /auth/consent-status | 登录 | 100/min | ✅ |

### 8.2 user 模块（9+1/10 一致）

| # | API 设计 | 切片 | 方法 | 路径 | 权限 | 状态 |
|---|---------|------|------|------|------|:---:|
| 1 | §3.1 | user L765 | GET | /users/profile | 登录 | ✅ |
| 2 | §3.2 | user L775 | PATCH | /users/profile | 登录 | ✅ |
| 3 | §3.3 | user L786 | PATCH | /users/rating | 登录 | ✅ |
| 4 | §3.4 | user L797 | GET | /users/rating-history | 登录 | ✅ |
| 5 | §3.5 | user L809 | GET | /users/big-data | 登录 | ✅ |
| 6 | §3.6 | user L819 | DELETE | /users/account | 登录 | ✅ |
| 7 | §3.7 | video_analysis L1166 | GET | /video-analysis/reports/{id}/feedbacks | 登录 | ✅ |
| 8 | §3.8 | user L840 | POST | /users/export-data | 登录 | ✅ |
| 9 | §3.9 | user L850 | GET | /users/export-data/{task_id} | 登录 | ✅ |
| 10 | §3.10 | user L830 | POST | /users/account/cancel-deletion | 登录 | ✅ |

### 8.3 video_analysis 模块（12/12，错误码⚠️）

| # | API 设计 | 切片 | 方法 | 路径 | 权限 | 限流 | 状态 |
|---|---------|------|------|------|------|------|:---:|
| 1 | §4.1 | L1072 | POST | /video-analysis/upload-token | 登录 | 100/min | ✅ |
| 2 | §4.2 | L1083 | POST | /video-analysis/upload-complete | 登录 | 100/min | ✅ |
| 3 | §4.3 | L1094 | POST | /video-analysis/tasks | 登录 | 10/hour | ✅ |
| — | — | L654 | — | 免费额度错误 | — | 403→429 | ❌ P1-2 |
| 4 | §4.4 | L1105 | GET | /video-analysis/tasks | 登录 | 100/min | ✅ |
| 5 | §4.5 | L1118 | GET | /video-analysis/tasks/{task_id} | 登录 | 100/min | ✅ |
| 6 | §4.6 | L1129 | GET | /video-analysis/reports/{report_id} | 登录 | 100/min | ✅ |
| 7 | §4.7 | L1140 | GET | /video-analysis/reports | 登录 | 100/min | ✅ |
| 8 | §4.8 | L1152 | POST | /video-analysis/reports/{id}/feedback | 登录 | 100/min | ✅ |
| 9 | §4.9 | L1179 | GET | /video-analysis/reports/{id}/annotated-video | 登录 | 100/min | ✅ |
| 10 | §4.10 | L1190 | POST | /video-analysis/reports/{id}/share | 登录 | 5/天 | ⚠️ P3-1 |
| — | — | L972 | — | 分享超限错误 | — | 429 未在 API 定义 | ⚠️ P3-3 |
| 11 | §4.11 | share_router L1215 | GET | /share/{share_token} | 公开 | — | ✅ |

### 8.4 scoring 模块（10/10，错误码❌）

| # | API 设计 | 切片 | 方法 | 路径 | 权限 | 限流 | 状态 |
|---|---------|------|------|------|------|------|:---:|
| 1 | §5.1 | L1119 | POST | /scoring/matches | 登录 | 100/min | ✅ |
| 2 | §5.2 | L1129 | GET | /scoring/matches | 登录 | 100/min | ✅ |
| 3 | §5.3 | L1143 | GET | /scoring/matches/{match_id} | 登录 | 100/min | ✅ |
| 4 | §5.4 | L1153 | POST | /scoring/matches/{id}/score | 登录 | 100/min | ✅ |
| — | §5.4 | L726 | — | 状态冲突错误 | — | 409→400 | ❌ P1-1 |
| 5 | §5.5 | L1164 | POST | /scoring/matches/{id}/undo | 登录 | 100/min | ✅ |
| — | — | L823 | — | 额外状态校验 | — | 400→409 | ⚠️ P2-4 |
| 6 | §5.6 | L1175 | POST | /scoring/matches/{id}/finish | 登录 | 100/min | ✅ |
| — | §5.6 | L904 | — | 状态冲突错误 | — | 409→400 | ❌ P1-1 |
| 7 | §5.7 | L1185 | GET | /scoring/matches/{id}/statistics | 登录 | 100/min | ✅ |
| 8 | §5.8 | L1195 | POST | /scoring/matches/{id}/start | 登录 | 100/min | ✅ |
| 9 | §5.9 | L1206 | POST | /scoring/matches/{id}/abandon | 登录 | 100/min | ✅ |
| 10 | §5.10 | L1217 | POST | /scoring/matches/{id}/resume | 登录 | 100/min | ✅ |

### 8.5 match_data 模块（4/4，校验+响应❌）

| # | API 设计 | 切片 | 方法 | 路径 | 权限 | 状态 |
|---|---------|------|------|------|------|:---:|
| 1 | §7.1 | L894 | POST | /match-data/records | 登录 | ✅ |
| 2 | §7.2 | L904 | GET | /match-data/records | 登录 | ✅ |
| 3 | §7.3 | L917 | GET | /match-data/records/{record_id} | 登录 | ✅ |
| 4 | §7.4 | L927 | PATCH | /match-data/records/{record_id} | 登录 | ❌ |
| — | §7.4 | L847 | — | 缺失 409 关联校验 | — | ❌ P1-6 |
| — | §7.4 | L867 | — | 缺失 updated_fields | — | ⚠️ P2-2 |

### 8.6 training_advice 模块（8/8，权限+错误码+响应❌）

| # | API 设计 | 切片 | 方法 | 路径 | API 权限 | 切片权限 | 状态 |
|---|---------|------|------|------|---------|---------|:---:|
| 1 | §8.1 | L1139 | GET | /training/advice/{report_id} | 登录 | get_current_user | ✅ |
| 2 | §8.2 | L1148 | GET | /training/advice/contextual | 登录 | get_current_user | ✅ |
| 3 | §8.3 | L1160 | GET | /training/templates | 登录 | 会员 | ❌ P1-4 |
| 4 | §8.4 | L1172 | GET | /training/templates/{template_id} | 登录 | 会员 | ❌ P1-4 |
| 5 | §8.5 | L1182 | GET | /training/plans/{id}/adjustments | 登录 | 会员 | ❌ P1-4 |
| 6 | §8.6 | L1192 | POST | /training/plans/{id}/re-evaluate | 会员 | 会员（类型错误） | ❌ P1-5 |
| 7 | §8.7 | L1200 | GET | /training/plans/{id}/sessions | 会员 | 会员 | ✅ |
| 8 | §8.8 | L1211 | POST | /training/plans/{id}/sessions/{sid}/complete | 会员 | 会员 | ✅ |
| — | §8.8 | L1085 | — | 已完成错误 400→409 | — | — | ❌ P1-3 |
| — | §8.8 | L1112 | — | 响应字段不匹配 | — | — | ⚠️ P2-1 |

### 8.7 其余模块

| 模块 | API 端点数 | 切片端点数 | 一致性 | 说明 |
|------|:---:|:---:|:---:|------|
| data_dashboard (§6) | 5 | 5 | ✅ | 全部一致 |
| progress_analysis (§9) | 6 | 6 | ✅ | 全部一致 |
| gamification (§10) | 4 | 4 | ✅ | 全部一致（checkin 1/day） |
| membership (§11) | 3 | 3 | ✅ | 全部一致（_cents 字段名） |
| payment (§12) | 4 | 4 | ⚠️ | refund 超 7 天错误码 P1-7 |
| notification (§13) | 4 | 4+1 WS | ✅ | 全部一致 |
| admin (未编号) | 0 | 17 | ⚠️ | P2-5 未文档化 |

---

## 9. 审查方法说明

- **数据提取**：使用 ripgrep 提取 API 设计 `### X.Y METHOD /path` 标题行（120+ 端点）和切片 `@router.(get|post|patch|put|delete|websocket)(` 装饰器（97 端点）
- **限流对比**：提取 `@limiter.limit(` 配置（97 匹配）与 API 设计 §1.5 限流表 + 各端点"限流"标注
- **错误码对比**：提取 `raise (HTTPException|AppException)` 模式（100+ 匹配）与 API 设计 §1.7 通用错误码 + §1.8 业务错误码 + 各端点"错误情况"表
- **权限对比**：提取 API 设计 `**权限**：XXX` 标注（100+ 匹配）与切片 `Depends(get_current_user/require_membership/get_current_admin)` 依赖注入
- **跨模块调用**：提取 `add_points/push_ws_message/check_membership` 调用签名（92 匹配）
- **先前修复验证**：逐项对比第八轮报告偏差项与 API v1.3 + 切片当前状态
- **审查类型**：只读审查，未修改任何源文件
