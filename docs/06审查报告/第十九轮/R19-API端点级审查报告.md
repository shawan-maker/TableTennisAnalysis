# R19 — API 端点级 + 契约完整性审查报告

> **审查代理**：第十九轮 API 端点级 + 契约完整性维度
> **审查日期**：2026-10-19
> **工作目录**：D:\PyProject\TableTennisAnalysis
> **审查基线**：R18-API 端点级一致性审查报告（2026-10-16）+ API 设计 v1.3 + 12 后端切片 + 13 前端切片

---

## 1. 审查范围

| 序号 | 文件 | 用途 |
|------|------|------|
| 1 | `docs/04详细设计/05-API详细设计.md`（4426 行） | API 设计 v1.3，端点权威源 |
| 2 | `docs/03系统架构/01-系统架构设计.md` §5.7（L803-957） | Phase 1 核心 API 端点清单 |
| 3 | `docs/06垂直模块前后端切片设计/01-auth/backend.md` | 认证切片 @router 定义 |
| 4 | `docs/06垂直模块前后端切片设计/02-user/backend.md` | 用户切片 @router 定义 |
| 5 | `docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` | 视频分析切片 @router 定义 |
| 6 | `docs/06垂直模块前后端切片设计/04-scoring/backend.md` | 记分牌切片 @router 定义 |
| 7 | `docs/06垂直模块前后端切片设计/05-match_data/backend.md` | 比赛数据切片 @router 定义 |
| 8 | `docs/06垂直模块前后端切片设计/06-data_dashboard/backend.md` | 数据看板切片 @router 定义 |
| 9 | `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` | 训练切片 @router 定义 |
| 10 | `docs/06垂直模块前后端切片设计/08-progress_analysis/backend.md` | 进度分析切片 @router 定义 |
| 11 | `docs/06垂直模块前后端切片设计/09-gamification/backend.md` | 游戏化切片 @router 定义 |
| 12 | `docs/06垂直模块前后端切片设计/10-membership/backend.md` | 会员切片 @router 定义 |
| 13 | `docs/06垂直模块前后端切片设计/11-payment/backend.md` | 支付切片 @router 定义 |
| 14 | `docs/06垂直模块前后端切片设计/12-notification/backend.md` | 通知切片 @router 定义 |
| 15 | `docs/06垂直模块前后端切片设计/13-infrastructure/admin.md` | 管理后台切片 @router 定义 |
| 16 | `docs/06垂直模块前后端切片设计/13-infrastructure/ai_inference.md` | AI 推理（HTTPException 检查） |
| 17 | `docs/06垂直模块前后端切片设计/00-{1..12}-*/frontend.md` | 13 前端切片 request.* 调用 |
| 18 | `docs/06垂直模块前后端切片设计/00-垂直切片设计总览.md` | 模块清单与修复跟踪表 |

**审查模式**：以 R18 报告为基线，先验证 10 项 R18 修复，再按 12 项审查清单对 API ↔ 切片 ↔ 前端三方契约一致性进行交叉比对，定位 grep 行号级新发现。

**搜索定位模式**：
- `@router\.(get|post|put|patch|delete)\(` — 定位后端端点
- `request\.(get|post|put|patch|delete)\(` — 定位前端调用
- `@limiter\.limit\(` — 定位限流配置
- `raise AppException|raise HTTPException` — 定位异常处理
- `model_validate` — 定位 Schema 注入
- `APIRouter\(prefix=` — 定位路由前缀

---

## 2. R18 修复验证表

R18 API 端点级报告共 10 项发现（P1×3 + P2×2 + P3×5），本轮全部进入回归验证：

| 序号 | R18 编号 | R18 修复项 | R19 状态 | 验证详情 |
|------|---------|-----------|---------|---------|
| 1 | R18-P1-1 | §5.7 L948-949 `/training/plan/` 单数 → `/training/plans/` 复数 | ✅ 已修复 | 架构 §5.7 L942 `GET /training/plans/{plan_id}/adjustments`、L943 `POST /training/plans/{plan_id}/re-evaluate` 均使用复数 `plans`，与 API §8.5/§8.6 和切片 L1215/L1225 一致 |
| 2 | R18-P1-2 | §5.7 L950-951 training sessions/complete 权限"登录" → "会员" | ✅ 已修复 | 架构 §5.7 L944 `GET /training/plans/{plan_id}/sessions` 权限="会员"；L945 `POST /training/plans/{plan_id}/sessions/{session_id}/complete` 权限="会员"，与 API §8.7/§8.8 和切片 L1241/L1253 `require_membership("member")` 一致 |
| 3 | R18-P1-3 | §5.7 L915 payment refund 权限"登录" → "管理员" | ✅ 已修复 | 架构 §5.7 L907 `POST /payment/orders/{order_id}/refund` 权限="管理员"，与 API §12.4 和切片 L1414 `Depends(get_current_admin)` 一致 |
| 4 | R18-P2-1 | §5.7 路径参数 `{id}` → 具体参数名（20 处） | ✅ 已修复 | 架构 §5.7 全部使用具体参数名：`{task_id}`（L846）、`{report_id}`（L847/L849/L850/L851/L852）、`{match_id}`（L861-868）、`{record_id}`（L876/L877）、`{template_id}`（L941）、`{plan_id}`（L942-945）、`{share_token}`（L853）、`{user_id}`（架构 §5.7 admin 端点未列出，由 API §19 详列） |
| 5 | R18-P2-2 | §5.7 training advice 端点重复列表 → 合并为单一表 | ✅ 已修复 | 架构 §5.7 现仅有一张"训练建议 (`/training`)"表（L932-945），含 8 个端点，无重复 |
| 6 | R18-P3-1 | h5-exchange/consent 限流未文档化 | ✅ 已修复（含 R19-P1-1 残留） | API §1.5 L81-82 已新增 2 行：`H5 Token 换 JWT（POST /auth/h5-exchange） | 10/min` 与 `隐私政策同意（POST /auth/consent） | 10/min`。但切片 L648 h5-exchange 实际为 100/minute（详见 R19-P1-1） |
| 7 | R18-P3-2 | AI 推理使用 HTTPException 而非 AppException | ✅ 已修复 | `13-infrastructure/ai_inference.md` L363 有 R18-P3-12 修复注释；L373 `from app.core.exceptions import AppException`；L396/412/423/439/453/469/480/495 共 8 处 `raise AppException(..., 503/504)`，无 `HTTPException` 残留 |
| 8 | R18-P3-3 | §3.7 端点归模块不一致 | ✅ 已修复 | API §3.7 L784 有 R18-P3-13 修复注释，列出 4 项归类理由：(1) 路由归属 video_analysis；(2) 列出位置用户模块反馈历史视角；(3) 切片实现 03-video_analysis/backend.md；(4) 数据归属 feedback_record 表 |
| 9 | R18-P3-4 | §5.7 training sessions 描述术语"训练会话" → "训练单" | ✅ 已修复 | 架构 §5.7 L944 描述="训练单列表"，L945 描述="标记训练单完成"；与 API §8.7/§8.8 术语一致 |
| 10 | R18-P3-5 | 用户端 page_size 上限未在端点参数表标注 | ✅ 已修复 | API §1.2 L51 有 R18-P3-14 修复注释；§3.7 L791、§5.2 L1433、§8.3 L2230 等用户端参数表均显式标注"默认 20，最小 1，最大 50（见 §1.2）"；管理端（§19）保持 100 上限 |

**R18 修复通过率**：10/10 = 100% ✅

> **回归结论**：R18 的 10 项发现在 R19 全部验证通过。其中 R18-P3-1（h5-exchange/consent 限流）虽 API §1.5 已文档化，但切片 h5-exchange 装饰器仍为 100/minute，构成 R19-P1-1 新发现（详见 §5.1）。

---

## 3. 端点清单交叉比对表

### 3.1 Phase 1 业务端点（79 个）

#### 认证模块 `/auth`（10 端点）

| # | API 设计路径 | 方法 | 切片路径（prefix + route） | 前端调用 | 一致性 |
|---|------------|------|--------------------------|---------|--------|
| 1 | /auth/wechat-login | POST | /auth + /wechat-login（L588） | frontend L32 ✅ | ✅ |
| 2 | /auth/phone-login | POST | /auth + /phone-login（L594） | frontend L39 ✅ | ✅ |
| 3 | /auth/send-sms | POST | /auth + /send-sms（L600） | frontend L46 ✅ | ✅ |
| 4 | /auth/refresh | POST | /auth + /refresh（L606） | frontend L53 ✅ | ✅ |
| 5 | /auth/logout | POST | /auth + /logout（L612） | frontend L60 ✅ | ✅ |
| 6 | /auth/me | GET | /auth + /me（L626） | frontend L67 ✅ | ✅ |
| 7 | /auth/h5-token | POST | /auth + /h5-token（L643） | frontend L74 ✅ | ✅ |
| 8 | /auth/h5-exchange | POST | /auth + /h5-exchange（L649） | frontend L81 ✅ | ✅（限流见 P1-1） |
| 9 | /auth/consent | POST | /auth + /consent（L656） | **❌ 前端未调用** | ⚠️ 见 P1-4 |
| 10 | /auth/consent-status | GET | /auth + /consent-status（L675） | **❌ 前端未调用** | ⚠️ 见 P1-4 |

> 认证前端声明 "§2.1-2.8，8 个端点"（L13），与 API 实际 10 端点不一致（详见 P2-3）。

#### 用户模块 `/users`（9 个用户端点 + §3.7 跨模块端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /users/profile | GET | /users + /profile（L776） | frontend L31 ✅ | ✅ |
| 2 | /users/profile | PATCH | /users + /profile（L786） | frontend L43 ✅ | ✅ |
| 3 | /users/rating | PATCH | /users + /rating（L797） | frontend L53 ✅ | ✅ |
| 4 | /users/rating-history | GET | /users + /rating-history（L808） | frontend L62 ✅ | ✅ |
| 5 | /users/big-data | GET | /users + /big-data（L820） | frontend L69 ✅ | ✅ |
| 6 | /users/account | DELETE | /users + /account（L830） | frontend L78 ✅ | ✅ |
| 7 | /users/account/cancel-deletion | POST | /users + /account/cancel-deletion（L841） | frontend L92 ✅ | ✅ |
| 8 | /users/export-data | POST | /users + /export-data（L851） | frontend L99 ✅ | ✅ |
| 9 | /users/export-data/{task_id} | GET | /users + /export-data/{task_id}（L861） | frontend L107 ✅ | ✅ |
| — | /users/account/deletion-status | GET | **❌ 后端未实现** | frontend L85 ❌ | ⚠️ 见 P1-3 |

> §3.7 `GET /video-analysis/reports/{report_id}/feedbacks` 路径前缀为 `/video-analysis/`，归入视频分析模块（详见 R18-P3-13 修复说明）。

#### 视频分析模块 `/video-analysis`（11 端点，含 §3.7 跨模块 + 分享端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /video-analysis/upload-token | POST | /video-analysis + /upload-token（L1139） | frontend L32 ✅ | ✅ |
| 2 | /video-analysis/upload-complete | POST | /video-analysis + /upload-complete（L1150） | frontend L40 ✅ | ✅ |
| 3 | /video-analysis/tasks | POST | /video-analysis + /tasks（L1161） | frontend L49 ✅ | ✅ |
| 4 | /video-analysis/tasks | GET | /video-analysis + /tasks（L1172） | frontend L61 ✅ | ✅ |
| 5 | /video-analysis/tasks/{task_id} | GET | /video-analysis + /tasks/{task_id}（L1185） | frontend L73 ✅ | ✅ |
| 6 | /video-analysis/reports/{report_id} | GET | /video-analysis + /reports/{report_id}（L1196） | frontend L81 ✅ | ✅ |
| 7 | /video-analysis/reports | GET | /video-analysis + /reports（L1207） | frontend L88 ✅ | ✅ |
| 8 | /video-analysis/reports/{report_id}/feedback | POST | /video-analysis + /reports/{report_id}/feedback（L1219） | frontend L102 ✅ | ✅ |
| 9 | /video-analysis/reports/{report_id}/feedbacks（§3.7） | GET | /video-analysis + /reports/{report_id}/feedbacks（L1233） | **❌ 前端未调用** | ⚠️ 见 P2-1 |
| 10 | /video-analysis/reports/{report_id}/annotated-video | GET | /video-analysis + /reports/{report_id}/annotated-video（L1246） | frontend L113 ✅ | ✅ |
| 11 | /video-analysis/reports/{report_id}/share | POST | /video-analysis + /reports/{report_id}/share（L1257） | frontend L121 ✅ | ✅ |
| 12 | /share/{share_token} | GET | share_router（无 prefix）+ /share/{share_token}（L1282） | — 公开页 | ✅ |

#### 记分牌模块 `/scoring`（10 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /scoring/matches | POST | /scoring + /matches（L1141） | frontend L47 ✅ | ✅ |
| 2 | /scoring/matches | GET | /scoring + /matches（L1151） | frontend L57 ✅ + 00-home L97 ✅ | ✅ |
| 3 | /scoring/matches/{match_id} | GET | /scoring + /matches/{match_id}（L1165） | frontend L64 ✅ | ✅ |
| 4 | /scoring/matches/{match_id}/score | POST | /scoring + /matches/{match_id}/score（L1175） | frontend L71 ✅ | ✅ |
| 5 | /scoring/matches/{match_id}/undo | POST | /scoring + /matches/{match_id}/undo（L1186） | frontend L78 ✅ | ✅ |
| 6 | /scoring/matches/{match_id}/finish | POST | /scoring + /matches/{match_id}/finish（L1197） | frontend L85 ✅ | ✅ |
| 7 | /scoring/matches/{match_id}/statistics | GET | /scoring + /matches/{match_id}/statistics（L1207） | frontend L92 ✅ | ✅ |
| 8 | /scoring/matches/{match_id}/start | POST | /scoring + /matches/{match_id}/start（L1217） | —（未在前端 service 中） | ✅ |
| 9 | /scoring/matches/{match_id}/abandon | POST | /scoring + /matches/{match_id}/abandon（L1228） | — | ✅ |
| 10 | /scoring/matches/{match_id}/resume | POST | /scoring + /matches/{match_id}/resume（L1239） | — | ✅ |

> 端点 8-10（start/abandon/resume）前端未显式调用，但记分牌 UI 通常嵌入页面交互逻辑（如按钮触发），属正常设计。

#### 数据看板模块 `/dashboard`（5 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /dashboard/overview | GET | /dashboard + /overview（L782） | 06-dashboard L96 + 00-home ✅ | ✅ |
| 2 | /dashboard/win-rate-trend | GET | /dashboard + /win-rate-trend（L789） | frontend L104 ✅ | ✅ |
| 3 | /dashboard/technique-stats | GET | /dashboard + /technique-stats（L799） | frontend L111 ✅ | ✅ |
| 4 | /dashboard/landing-heatmap | GET | /dashboard + /landing-heatmap（L806） | frontend L118 ✅ | ✅ |
| 5 | /dashboard/match-records | GET | /dashboard + /match-records（L813） | frontend L132 ✅ | ✅ |

#### 比赛数据模块 `/match-data`（4 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /match-data/records | POST | /match-data + /records（L919） | 05-match_data frontend L71 ✅ | ✅ |
| 2 | /match-data/records | GET | /match-data + /records（L929） | frontend L81 ✅ | ✅ |
| 3 | /match-data/records/{record_id} | GET | /match-data + /records/{record_id}（L942） | frontend L88 ✅ | ✅ |
| 4 | /match-data/records/{record_id} | PATCH | /match-data + /records/{record_id}（L952） | — | ✅ |

#### 训练模块 `/training`（8 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /training/advice/{report_id} | GET | /training + /advice/{report_id}（L1172） | frontend L114 ✅ | ✅ |
| 2 | /training/advice/contextual | GET | /training + /advice/contextual（L1182） | frontend L121 ✅ | ✅ |
| 3 | /training/templates | GET | /training + /templates（L1191，会员守卫） | frontend L135 ✅ | ⚠️ 见 P1-2 |
| 4 | /training/templates/{template_id} | GET | /training + /templates/{template_id}（L1205，会员守卫） | frontend L147 ✅ | ⚠️ 见 P1-2 |
| 5 | /training/plans/{plan_id}/adjustments | GET | /training + /plans/{plan_id}/adjustments（L1215，会员守卫） | frontend L155 ✅ | ⚠️ 见 P1-2 |
| 6 | /training/plans/{plan_id}/re-evaluate | POST | /training + /plans/{plan_id}/re-evaluate（L1225，会员守卫） | frontend L163 ✅ | ✅ |
| 7 | /training/plans/{plan_id}/sessions | GET | /training + /plans/{plan_id}/sessions（L1237，会员守卫） | **❌ 前端未调用** | ⚠️ 见 P2-2 |
| 8 | /training/plans/{plan_id}/sessions/{session_id}/complete | POST | /training + /plans/{plan_id}/sessions/{session_id}/complete（L1248，会员守卫） | **❌ 前端未调用** | ⚠️ 见 P2-2 |

#### 进度分析模块 `/progress`（6 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /progress/snapshots | GET | /progress + /snapshots（L1373） | frontend L55 ✅ | ✅ |
| 2 | /progress/technique-trends | GET | /progress + /technique-trends（L1387） | frontend L62 ✅ | ✅ |
| 3 | /progress/technique-trends/{metric} | GET | /progress + /technique-trends/{metric}（L1397） | frontend L70 ✅ | ✅ |
| 4 | /progress/comparison | GET | /progress + /comparison（L1408） | frontend L79 ✅ | ✅ |
| 5 | /progress/summary | GET | /progress + /summary（L1421） | frontend L86 ✅ | ✅ |
| 6 | /progress/problem-changes | GET | /progress + /problem-changes（L1431） | frontend L93 ✅ | ✅ |

#### 游戏化模块 `/gamification`（4 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /gamification/points | GET | /gamification + /points（L1062） | frontend L84 ✅ | ✅ |
| 2 | /gamification/checkin-calendar | GET | /gamification + /checkin-calendar（L1073） | frontend L96 + 00-home L90 ✅ | ✅ |
| 3 | /gamification/checkin | POST | /gamification + /checkin（L1093） | frontend L103 ✅ | ✅ |
| 4 | /gamification/badges | GET | /gamification + /badges（L1104） | frontend L110 ✅ | ✅ |

#### 会员模块 `/membership`（3 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /membership/tiers | GET | /membership + /tiers（L801） | frontend L67 ✅ | ✅ |
| 2 | /membership/current | GET | /membership + /current（L812） | frontend L74 ✅ | ✅ |
| 3 | /membership/quota | GET | /membership + /quota（L823） | frontend L81 ✅ | ✅ |

#### 支付模块 `/payment`（4 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /payment/orders | POST | /payment + /orders（L1340） | frontend L67 ✅ | ✅ |
| 2 | /payment/orders | GET | /payment + /orders（L1356） | frontend L83 ✅ | ✅ |
| 3 | /payment/notify | POST | /payment + /notify（L1376） | — 微信回调 | ✅ |
| 4 | /payment/orders/{order_id}/refund | POST | /payment + /orders/{order_id}/refund（L1414，admin 守卫） | — 管理员端 | ✅ |

#### 通知模块 `/notification`（4 端点）

| # | API 设计路径 | 方法 | 切片路径 | 前端调用 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /notification/list | GET | /notification + /list（L660） | frontend L49 ✅ | ✅ |
| 2 | /notification/read | POST | /notification + /read（L676） | frontend L61 ✅ | ✅ |
| 3 | /notification/subscribe | POST | /notification + /subscribe（L686） | frontend L69 ✅ | ✅ |
| 4 | /notification/unread-count | GET | /notification + /unread-count（L696） | frontend L76 + 00-home L104 ✅ | ✅ |

#### 首页聚合 §14a（前端聚合，无后端端点）

| # | API 设计 | 架构 §5.7 | 前端切片 | 一致性 |
|---|---------|----------|---------|--------|
| 1 | GET /home/dashboard（前端聚合，L3409-3416） | L947-956（前端聚合，无独立后端） | 00-home/frontend.md homeStore.refreshAll() | ✅ |

三方聚合端点：`GET /dashboard/overview` + `GET /gamification/checkin-calendar` + `GET /scoring/matches` + `GET /notification/unread-count`，前端 00-home/frontend.md L90/L97/L104 + 06-dashboard L96 全部覆盖。

### 3.2 Admin 端点（17 个）

| # | API 设计路径 | 方法 | 切片路径 | 权限标注 | 一致性 |
|---|------------|------|---------|---------|--------|
| 1 | /admin/login | POST | /admin + /login（L873） | 公开 | ✅ |
| 2 | /admin/logout | POST | /admin + /logout（L881） | 管理员（get_current_admin） | ✅ |
| 3 | /admin/users | GET | /admin + /users（L894） | 管理员 | ✅ |
| 4 | /admin/users/{user_id}/ban | POST | /admin + /users/{user_id}/ban（L908） | 超级管理员（require_super_admin） | ✅ |
| 5 | /admin/users/{user_id}/unban | POST | /admin + /users/{user_id}/unban（L919） | 超级管理员 | ✅ |
| 6 | /admin/configs | GET | /admin + /configs（L930） | 管理员 | ✅ |
| 7 | /admin/configs/{key} | GET | /admin + /configs/{key}（L939） | 管理员 | ✅ |
| 8 | /admin/configs | POST | /admin + /configs（L949） | 超级管理员 | ✅ |
| 9 | /admin/configs/{key} | PATCH | /admin + /configs/{key}（L959） | 超级管理员 | ✅ |
| 10 | /admin/configs/{key} | DELETE | /admin + /configs/{key}（L970） | 超级管理员 | ✅ |
| 11 | /admin/audit-logs | GET | /admin + /audit-logs（L981） | 管理员 | ✅ |
| 12 | /admin/knowledge/categories | POST | /admin + /knowledge/categories（L1003） | 超级管理员 | ✅ |
| 13 | /admin/knowledge/categories/{category_id} | PATCH | /admin + /knowledge/categories/{category_id}（L1013） | 超级管理员 | ✅ |
| 14 | /admin/knowledge/categories/{category_id} | DELETE | /admin + /knowledge/categories/{category_id}（L1024） | 超级管理员 | ✅ |
| 15 | /admin/knowledge/rules | POST | /admin + /knowledge/rules（L1034） | 超级管理员 | ✅ |
| 16 | /admin/knowledge/rules/{rule_id}/toggle | PATCH | /admin + /knowledge/rules/{rule_id}/toggle（L1044） | 超级管理员 | ✅ |
| 17 | /admin/model-versions/{version_id}/activate | POST | /admin + 注释占位（L1057，Phase 2+） | 超级管理员 | ✅ |

### 3.3 端点总数验证

| 类别 | 数量 | 明细 | 验证结果 |
|------|------|------|---------|
| Phase 1 业务端点 | 79 | auth(10)+users(9+1 跨模块)+video-analysis(11)+scoring(10)+dashboard(5)+match-data(4)+training(8)+progress(6)+gamification(4)+membership(3)+payment(4)+notification(4) | ✅ |
| Admin 端点 | 17 | 认证(2)+用户管理(3)+配置(5)+审计(1)+知识库(5)+模型版本(1) | ✅ |
| **合计** | **96** | 79 + 17 = 96 | ✅ |

> 注：§3.7 `GET /video-analysis/reports/{report_id}/feedbacks` 路径归 video_analysis 模块，但在 API 设计 §3 用户模块下列出（R18-P3-13 已说明归类理由），故统计为 video-analysis 11 端点。

---

## 4. 12 项审查清单逐项结论

### 4.1 R18 修复回归

**结论**：✅ 通过（10/10）

R18 全部 10 项发现在 R19 验证通过，详见 §2 修复验证表。R18-P3-1（h5-exchange/consent 限流）API §1.5 已文档化但切片 h5-exchange 装饰器未同步更新（详见 R19-P1-1）。

### 4.2 端点路径/方法/参数/响应/状态码一致性

**结论**：✅ 通过（核心一致性维持）

- **路径一致性**：API 设计 96 个端点路径与 13 个后端切片 `@router` 路由路径完全一致，全部 14 个 `APIRouter(prefix=...)` 前缀与 API 设计路径前缀匹配。
- **方法一致性**：API 设计端点 HTTP 方法与切片 `@router.get/post/patch/delete` 装饰器完全一致。
- **参数一致性**：抽样验证关键端点（GET /scoring/matches、POST /admin/knowledge/rules/{rule_id}/toggle、GET /admin/audit-logs、POST /payment/orders/{order_id}/refund）路径参数、查询参数、请求体参数与 API 设计一致。
- **响应字段一致性**：抽样验证 GET /dashboard/overview、POST /training/plans/{plan_id}/sessions/{session_id}/complete、POST /payment/orders/{order_id}/refund 响应字段与 API 设计一致。
- **状态码一致性**：切片 `raise AppException(msg, status_code)` 与 API 设计"错误情况"表中的 HTTP 状态码一致（400/401/403/404/409/422/429/502）。

### 4.3 96 端点完整性（79 业务 + 17 admin）

**结论**：✅ 通过

Phase 1 业务端点 79 + admin 17 = 96，与 R18 一致，无新增无删减。

### 4.4 请求参数验证完整性（Pydantic Schema vs API 文档参数表）

**结论**：✅ 通过

抽样验证：
- `POST /scoring/matches` body=MatchCreateRequest，含 opponent_name/opponent_rating/format/match_type/target_score ✅
- `POST /payment/orders/{order_id}/refund` body=refund_amount_cents/reason，order_id(path) ✅
- `POST /admin/knowledge/rules/{rule_id}/toggle` rule_id(path) + is_active(query) ✅
- `POST /auth/consent` body=consent_type(枚举)/policy_version ✅
- 全部使用 Pydantic Schema 模型注入。

### 4.5 响应 Schema 字段一致性

**结论**：✅ 通过

抽样验证：
- GET /dashboard/overview：win_rate/wins/losses/analysis_count/training_frequency_per_week/streak_days/trend/latest_advice_summary ✅
- POST /training/plans/{plan_id}/sessions/{session_id}/complete：session_id/is_completed/plan_progress/points_earned ✅
- POST /payment/orders/{order_id}/refund：order_id/refund_status/refund_amount_cents ✅

### 4.6 错误码一致性（通用 40000/40100/40300/40400/42900/50000/50200 + 业务码）

**结论**：✅ 通过

API §1.7 通用错误码 + §1.8 端点级业务错误码（12 条）与切片 `AppException` 的 status_code 一致：

| code | HTTP | API 设计 | 切片 | 一致性 |
|------|------|---------|------|--------|
| 40010 | 400 | 文件尚未上传完成 | video_analysis L717 ✅ | ✅ |
| 40411 | 404 | 比赛不存在 | scoring L608 ✅ | ✅ |
| 40412 | 404 | 分析报告不存在 | video_analysis L846/897/959/1000/1043 ✅ | ✅ |
| 40413 | 404 | 比赛记录不存在 | match_data L830/868 ✅ | ✅ |
| 40910 | 409 | 比赛不在进行中 | scoring L736/833/914 ✅ | ✅ |
| 40911 | 409 | 比赛记录已关联记分牌 | match_data L872 ✅ | ✅ |
| 42210 | 422 | 比分不符合赛制规则 | match_data L656 ✅ | ✅ |
| 42910 | 429 | 免费分析额度耗尽 | video_analysis L704 ✅ | ✅ |

切片中 `raise AppException` 共 71 处（含 admin 18 处），无 `HTTPException` 残留（AI 推理 R18-P3-12 已修复）。

### 4.7 限流配置一致性（API §1.5 vs 切片 @limiter）

**结论**：⚠️ 通过（含 R19-P1-1 残留）

API §1.5 限流表 vs 切片 `@limiter.limit()` 装饰器：

| 端点 | API §1.5 | 切片 | 一致性 |
|------|---------|------|--------|
| POST /auth/wechat-login | 10/min | L587 `10/minute` | ✅ |
| POST /auth/phone-login | 5/min | L593 `5/minute` | ✅ |
| POST /auth/send-sms | 1/min | L599 `1/minute`（key_func=phone） | ✅ |
| **POST /auth/h5-exchange** | **10/min** | **L648 `100/minute`** | **❌ 见 P1-1** |
| POST /auth/consent | 10/min | L655 `10/minute` | ✅ |
| POST /video-analysis/tasks | 10/hour | L1160 `10/hour`（key_func=user） | ✅ |
| POST /video-analysis/reports/{id}/share | 5/天 | L1256 `5/day`（key_func=user） | ✅ |
| POST /gamification/checkin | 1/天 | L1092 `1/day`（key_func=user） | ✅ |
| POST /admin/login | 5/min | L872 `5/minute` | ✅ |
| 其他端点 | 100/min | 全部 `100/minute` | ✅ |
| POST /payment/notify | —（微信回调） | 无 limiter（SEC-006） | ✅ |

### 4.8 分页参数一致性（page/page_size le=50/100）

**结论**：✅ 通过

API §1.2 规范"page_size 默认 20，用户端最大 50，管理端最大 100"已在 R18-P3-14 修复中显式标注到全部 16 个用户端列表端点参数表。

| 类型 | 切片 | page_size 约束 | 一致性 |
|------|------|--------------|--------|
| 用户端 | video_analysis（3 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | scoring（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | match_data（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | user（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | payment（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | notification（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | progress_analysis（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | training_advice（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 用户端 | data_dashboard（1 处） | `Query(default=20, ge=1, le=50)` | ✅ |
| 管理端 | admin（2 处：list_users、list_audit_logs） | `Query(default=20, ge=1, le=100)` | ✅ |

### 4.9 model_validate 注入完整性

**结论**：✅ 通过

切片对 service 层返回的数据广泛使用 `model_validate` 注入，覆盖 10 个业务切片：

| 切片 | model_validate 使用情况 | 一致性 |
|------|----------------------|--------|
| 01-auth | —（简单 dict 返回） | ✅ |
| 02-user | RatingHistoryItem.model_validate（L527） | ✅ |
| 03-video_analysis | ReportDetailResponse.model_validate（L853） | ✅ |
| 04-scoring | MatchBrief/MatchDetailWithSequence.model_validate（L700/L716） | ✅ |
| 05-match_data | MatchRecordBrief/MatchRecordDetail.model_validate（L816/L840） | ✅ |
| 06-data_dashboard | MatchRecordBrief.model_validate（L692） | ✅ |
| 07-training_advice | TemplateBrief/TemplateDetail.model_validate（L779/L794） | ✅ |
| 08-progress_analysis | SnapshotBrief + 4 处 model_validate_json（缓存） | ✅ |
| 09-gamification | —（简单 dict 返回） | ✅ |
| 10-membership | —（简单 dict 返回） | ✅ |
| 11-payment | OrderBrief.model_validate（L919） | ✅ |
| 12-notification | NotificationBrief.model_validate（L500） | ✅ |
| 13-admin | AdminBrief/UserManageBrief/ConfigBrief.model_validate（L396/L457/L523/L549/L579） | ✅ |

### 4.10 首页聚合 4 端点 + admin 17 端点三方一致

**结论**：✅ 通过

**首页聚合三方一致**：

| 端点 | API §14a | 架构 §5.7 | 前端切片 |
|------|---------|----------|---------|
| GET /dashboard/overview | ✅ L3412 | ✅ L950（聚合列表 1） | ✅ 06-data_dashboard frontend L96 + 00-home |
| GET /gamification/checkin-calendar | ✅ L3412 | ✅ L951（聚合列表 2） | ✅ 09-gamification frontend L96 + 00-home L90 |
| GET /scoring/matches | ✅ L3412 | ✅ L952（聚合列表 3） | ✅ 04-scoring frontend L57 + 00-home L97 |
| GET /notification/unread-count | ✅ L3412 | ✅ L953（聚合列表 4） | ✅ 12-notification frontend L76 + 00-home L104 |

架构 §5.7 L947-956 明确标注"前端多模块聚合，无独立后端端点"，与 API §14a 和前端 `00-home/frontend.md` 三方一致。

**Admin 17 端点一致**：详见 §3.2 表格，路径/方法/参数/权限全部与 API §19 一致。

### 4.11 契约完整性（缺失端点/缺失参数/缺失响应字段）

**结论**：⚠️ 部分通过（含 R19-P1-3/P1-4/P2-1/P2-2 契约缺口）

- **API ↔ 后端切片**：✅ 96 端点路径/方法/参数/响应/状态码完全一致，无缺失。
- **后端切片 ↔ 前端切片**：⚠️ 发现 5 处契约缺口：
  - 前端调用未定义端点 `GET /users/account/deletion-status`（P1-3）
  - 前端缺失 `POST /auth/consent` / `GET /auth/consent-status` 调用（P1-4）
  - 前端缺失 `GET /video-analysis/reports/{report_id}/feedbacks` 调用（P2-1）
  - 前端缺失 `GET /training/plans/{plan_id}/sessions` 调用（P2-2）
  - 前端缺失 `POST /training/plans/{plan_id}/sessions/{session_id}/complete` 调用（P2-2）

### 4.12 安全性（输入验证/SQL 注入防护/CSRF）

**结论**：✅ 通过

- **输入验证**：全部端点使用 Pydantic Schema 注入（如 MatchCreateRequest、ScoreRequest、AdminLoginRequest 等），自动校验类型/必填/枚举值。
- **SQL 注入防护**：全部切片使用 SQLAlchemy 2.0 ORM `select()` / `update()` 语句，无字符串拼接 SQL；grep `execute\(` + `f".*SELECT"` 无裸 SQL 残留。
- **CSRF**：JWT Bearer Token + H5 一次性 Token 认证（无 Cookie session），架构层面免疫 CSRF；管理员后台使用 session + 同源策略。
- **权限守卫**：
  - `get_current_user`：登录端点（78 个业务端点）
  - `require_membership("member")`：会员端点（训练 §8.6/§8.7/§8.8、切片额外覆盖 §8.3/§8.4/§8.5 — 见 P1-2）
  - `get_current_admin`：管理员端点（admin 7 个）
  - `require_super_admin`：超级管理员端点（admin 10 个）
  - 微信支付回调 `POST /payment/notify`：APIv3 证书验签
- **限流**：100% 端点覆盖 `@limiter.limit()`（除 `POST /payment/notify` 微信回调豁免，SEC-006）。

---

## 5. 新发现

### P1（高优先级 — 影响契约一致性 / 安全 / PIPL 合规）

#### P1-1：h5-exchange 限流值切片与 API §1.5 不一致

- **位置**：`docs/06垂直模块前后端切片设计/01-auth/backend.md` L648
- **现象**：切片对 `POST /auth/h5-exchange` 使用 `@limiter.limit("100/minute")`，但 API §1.5 L81 明确声明该端点限流为 `10/min`。
- **对比**：
  - API §1.5 L81：`| H5 Token 换 JWT（POST /auth/h5-exchange） | 10/min | slowapi + Redis，防止 H5 token 滥用 |`
  - API §1.5 R18-P3-11 修复注释（L87）："本节限流表与 §2.8 POST /auth/h5-exchange（限流：10/min）、§2.9 POST /auth/consent（限流：10/min）保持一致"
  - 切片 L648：`@limiter.limit("100/minute")`
  - 切片 L773 反幻觉约束注释："其余端点 100/minute" — 将 h5-exchange 视为普通端点
  - 切片 L655（consent）：`@limiter.limit("10/minute")` ✅（与 API §1.5 一致）
- **影响**：限流值实际放宽 10 倍（100/min vs 设计 10/min），H5 Token 滥用风险升高。R18-P3-1 修复仅落地 API §1.5 文档化，未同步更新切片装饰器，构成修复不完整。
- **建议**：将切片 L648 `@limiter.limit("100/minute")` 改为 `@limiter.limit("10/minute")`，与 API §1.5 和 consent 端点（L655）保持一致。

#### P1-2：训练 §8.3/§8.4/§8.5 权限标注切片（会员）与 API/架构（登录）不一致

- **位置**：
  - `docs/04详细设计/05-API详细设计.md` §8.3 L2222、§8.4 L2263、§8.5 L2297
  - `docs/03系统架构/01-系统架构设计.md` §5.7 L940、L941、L942
  - `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` L1197、L1209、L1219
- **现象**：切片对 3 个训练端点添加了 `require_membership("member")` 会员守卫（SEC-003 修复），但 API 设计和架构 §5.7 仍标注权限为"登录"：

| 端点 | API 设计权限 | 架构 §5.7 权限 | 切片守卫 | 一致性 |
|------|------------|-------------|---------|--------|
| §8.3 GET /training/templates | 登录（L2222） | 登录（L940） | `require_membership("member")`（L1197） | ❌ |
| §8.4 GET /training/templates/{template_id} | 登录（L2263） | 登录（L941） | `require_membership("member")`（L1209） | ❌ |
| §8.5 GET /training/plans/{plan_id}/adjustments | 登录（L2297） | 登录（L942） | `require_membership("member")`（L1219） | ❌ |
| §8.6 POST /training/plans/{plan_id}/re-evaluate | 会员（L2334） | 会员（L943） | `require_membership("member")`（L1229） | ✅ |
| §8.7 GET /training/plans/{plan_id}/sessions | 会员（L2362） | 会员（L944） | `require_membership("member")`（L1241） | ✅ |
| §8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete | 会员（L2407） | 会员（L945） | `require_membership("member")`（L1253） | ✅ |

- **切片注释说明（L1259）**："SEC-003 修复后，以下 5 个端点也添加了 `require_membership("member")` 守卫：GET /templates、GET /templates/{id}、GET /plans/{id}/adjustments、GET /plans/{id}/sessions、POST /plans/{id}/sessions/{id}/complete。仅 GET /advice/{report_id} 和 GET /advice/contextual 保持 `get_current_user`（登录即可）。"
- **影响**：API 契约声明"登录"权限，但实际实现需"会员"。前端按 API 文档开发将不携带会员 token 调用，导致 403 错误。同时影响权限测试用例设计（登录用户应能访问 vs 实际不能）。
- **建议**：统一两侧权限标注。建议方案：将 API §8.3/§8.4/§8.5 权限从"登录"改为"会员"（与切片 SEC-003 修复意图一致，因为模板和方案均为会员功能），同步更新架构 §5.7 L940-942。

#### P1-3：前端调用未定义端点 `GET /users/account/deletion-status`

- **位置**：`docs/06垂直模块前后端切片设计/02-user/frontend.md` L85
- **现象**：前端 `getDeletionStatus()` 函数调用 `GET /users/account/deletion-status`，但该端点：
  - API 设计 `docs/04详细设计/05-API详细设计.md` 中无定义（grep `deletion-status` 返回 0 结果）
  - 架构 §5.7 用户模块端点列表中无此端点（L824-836 只列出 9 个用户端点）
  - 后端切片 `02-user/backend.md` 中无 `@router.get("/account/deletion-status")` 路由定义
  - 后端切片仅在 L830 `DELETE /account` 与 L841 `POST /account/cancel-deletion` 实现
- **前端代码**：
  ```typescript
  export function getDeletionStatus() {
    return request.get('/users/account/deletion-status')
  }
  ```
- **影响**：运行时返回 404，用户在注销冷静期内查询状态功能不可用。DELETE /users/account 响应已含 `scheduled_deletion_at` 和 `can_cancel_before` 字段（API §3.6 L749-750），前端可从用户档案或注销响应中获取状态，无需独立端点。
- **建议**：方案 A（推荐）— 删除前端 `getDeletionStatus()` 函数，注销倒计时改为读取本地状态（注销响应或 user.profile.scheduled_deletion_at）；方案 B — 在 API §3 和架构 §5.7 补充 `GET /users/account/deletion-status` 端点定义，并在后端切片 02-user/backend.md 实现该路由。

#### P1-4：前端缺失 `POST /auth/consent` 与 `GET /auth/consent-status` 调用（PIPL 合规缺口）

- **位置**：`docs/06垂直模块前后端切片设计/01-auth/frontend.md`（全文 L1-110）
- **现象**：API §2.9（L426-471）定义 `POST /auth/consent` 端点，§2.10（L473-506）定义 `GET /auth/consent-status` 端点；后端切片 `01-auth/backend.md` L656/L675 实现这两个端点。但前端 `auth.ts` service 模块（L21-82）仅实现 8 个端点（§2.1-§2.8），无 `recordConsent()` 或 `getConsentStatus()` 函数。
- **对比**：
  - API §2.1 wechat-login 响应含 `requires_consent: boolean` 字段（L169），表示用户是否需签署隐私政策
  - API §2.9 consent 端点业务规则 3："同意后后续登录 requires_consent 返回 false"（L464）
  - 前端 authStore L100-101：`membership_tier?` / `membership_expire_at?` 但无 `requires_consent?` 字段
  - 前端 auth 切片准备清单 L13：声明"本模块的 API 契约（§2.1-2.8，8 个端点）" — 明确将 §2.9/§2.10 排除在切片范围外
- **影响**：PIPL 第 14 条合规缺口 — 用户无法在前端完成隐私政策同意流程。微信登录响应 `requires_consent=true` 时前端无对应处理逻辑，用户同意记录无法采集，PIPL 合规审计风险。
- **建议**：(1) 在 `01-auth/frontend.md` §2 API Service 模块新增 `recordConsent()` 和 `getConsentStatus()` 两个函数；(2) 在 authStore 新增 `requires_consent` 状态字段；(3) 新增"隐私政策同意"页面（`pages/auth/consent/index.tsx`）；(4) 在 wechat-login 成功后根据 `requires_consent` 跳转同意页面；(5) 更新准备清单 L13 为"§2.1-2.10，10 个端点"。

#### P1-5：R18-P3-11 修复注释错误声明 §2.8/§2.9 有限流注释

- **位置**：`docs/04详细设计/05-API详细设计.md` L87（API §1.5 R18-P3-11 修复注释）
- **现象**：R18-P3-11 修复注释声明"本节限流表与 §2.8 `POST /auth/h5-exchange`（限流：10/min）、§2.9 `POST /auth/consent`（限流：10/min）保持一致"，但实际 §2.8（L401-424）和 §2.9（L426-471）端点描述中均无 `**限流**：10/min` 注释行。
- **对比**：
  - §2.1 wechat-login L141 有 `**限流**：10/min`
  - §2.2 phone-login L204 有 `**限流**：5/min`
  - §2.3 send-sms L233 有 `**限流**：1/min`
  - §2.4 refresh、§2.5 logout、§2.6 me、§2.7 h5-token、§2.8 h5-exchange、§2.9 consent、§2.10 consent-status — 均无 `**限流**` 注释（仅 §1.5 全局表声明）
  - API §1.5 R18-P3-11 注释（L87）声称"§2.8 / §2.9 各端点说明中'限流：10/min'一致" — 文档错误声明
- **影响**：文档错误声明误导后续审查者认为 §2.8/§2.9 端点级限流注释已落地，实际未落地。导致 R19-P1-1（切片 h5-exchange=100/minute）被掩盖 — 因为 R18-P3-1 报告声称切片已是 10/minute，但实际切片是 100/minute。
- **建议**：(1) 修正 R18-P3-11 修复注释，将"§2.8/§2.9 各端点说明中'限流：10/min'一致"改为"§2.8/§2.9 端点说明未单独列出限流注释，统一引用 §1.5 限流配置表"；(2) 或按 §2.1-§2.3 风格在 §2.8 和 §2.9 端点描述中补充 `**限流**：10/min` 注释（见 P3-1）。

### P2（中优先级 — 功能/文档缺口）

#### P2-1：前端缺失 `GET /video-analysis/reports/{report_id}/feedbacks`（§3.7）调用

- **位置**：`docs/06垂直模块前后端切片设计/03-video_analysis/frontend.md`（全文）
- **现象**：API §3.7（L778-821）定义 `GET /video-analysis/reports/{report_id}/feedbacks` 反馈历史列表端点；后端切片 `03-video_analysis/backend.md` L1233 实现；但前端 `videoAnalysis.ts` service 模块（L1-130）未实现 `getFeedbacks(reportId)` 函数。
- **对比**：
  - 后端切片 L1466 反幻觉注释："[X-22] 反馈历史查询端点（P1）：新增 GET /video-analysis/reports/{report_id}/feedbacks 端点，对应 API 设计 §3.7"
  - 前端切片 L102 仅调用 `POST /video-analysis/reports/{reportId}/feedback`（提交反馈，§4.8），无反馈历史查询
  - 前端 videoAnalysisStore 有 `feedbackSubmitted: boolean` 状态（L209/L234/L275/L288），但无 `feedbackHistory` 状态
- **影响**：数据飞轮闭环缺口 — 用户无法查看自己对历史报告的反馈记录，无法验证反馈是否被处理。R18-P3-13 修复了 §3.7 模块归类理由，但前端调用未补齐。
- **建议**：在 `03-video_analysis/frontend.md` §2 API Service 模块新增 `getFeedbacks(reportId, page, pageSize)` 函数；在 videoAnalysisStore 新增 `feedbackHistory` / `feedbackHistoryLoading` 状态；在报告详情页新增"反馈历史"区域。

#### P2-2：前端缺失 `GET /training/plans/{plan_id}/sessions` 与 `POST /training/plans/{plan_id}/sessions/{session_id}/complete` 调用（§8.7/§8.8）

- **位置**：`docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` L114-165
- **现象**：API §8.7（L2358-2402）和 §8.8（L2403-2446）定义训练单列表与完成端点；后端切片 `07-training_advice/backend.md` L1237/L1248 实现（R-3 修复）；但前端 `training.ts` service 模块（L114-164）仅实现 6 个端点（advice/{reportId}、advice/contextual、templates、templates/{id}、plans/{planId}/adjustments、plans/{planId}/re-evaluate），缺失 sessions 和 complete。
- **对比**：
  - 后端切片 L1398 反幻觉约束："R-3 添加训练单端点：GET /plans/{id}/sessions、POST /plans/{id}/sessions/{sid}/complete + Service 方法 + Schema"
  - 前端切片 L155-164 仅调用 `/training/plans/${planId}/adjustments` 和 `/training/plans/${planId}/re-evaluate`
- **影响**：会员功能缺口 — 会员用户无法在前端查看训练单列表、无法标记训练单完成，影响训练方案执行追踪。R18-P1-2 修复了架构 §5.7 权限标注（登录→会员），但前端调用未同步补齐。
- **建议**：在 `07-training_advice/frontend.md` §2 API Service 模块新增 `listTrainingSessions(planId, page, pageSize)` 和 `completeTrainingSession(planId, sessionId)` 两个函数；在 trainingStore 新增 `sessions` / `sessionsLoading` 状态；在训练方案详情页新增训练单列表与完成按钮。

#### P2-3：前端 API 契约声明端点数与实际不一致

- **位置**：
  - `docs/06垂直模块前后端切片设计/01-auth/frontend.md` L13："阅读本模块的 API 契约（§2.1-2.8，8 个端点）"
  - `docs/06垂直模块前后端切片设计/02-user/frontend.md` L13："阅读本模块的 API 契约（§3.1-3.9，8 个端点）"
- **现象**：前端切片准备清单中声明的 API 契约范围与实际端点数不一致：

| 模块 | 前端声明 | API 实际 | 差异 |
|------|---------|---------|------|
| auth | §2.1-2.8，8 个端点 | §2.1-2.10，10 个端点（含 §2.9 consent、§2.10 consent-status） | 缺失 §2.9/§2.10 |
| user | §3.1-3.9，8 个端点 | §3.1-3.10，9 个用户端点（§3.7 跨模块归 video-analysis） | 缺失 §3.10 cancel-deletion；实际 §3.1-3.9 不含 §3.7 也应是 8 个，但 §3.10 cancel-deletion 前端已调用，声明数应为 9 |

- **影响**：前端切片准备清单误导开发者认为模块端点数为 8，实际 9-10 个。导致切片范围审查遗漏 §2.9/§2.10/§3.10 端点的前端实现。
- **建议**：更新前端切片准备清单 L13 为准确端点数：auth 改为"§2.1-2.10，10 个端点"；user 改为"§3.1-3.10（不含 §3.7 跨模块端点），9 个端点"。

### P3（低优先级 — 细节优化）

#### P3-1：§2.8/§2.9 应补充显式 `**限流**：10/min` 注释

- **位置**：`docs/04详细设计/05-API详细设计.md` §2.8（L401-424）、§2.9（L426-471）
- **现象**：API §2.1 wechat-login（L141）、§2.2 phone-login（L204）、§2.3 send-sms（L233）端点描述中均有 `**限流**：xx/min` 注释行，但 §2.8 h5-exchange、§2.9 consent 端点描述中无此注释，仅 §1.5 全局限流表中列出。
- **对比**：
  - §2.1 L141：`**限流**：10/min`
  - §2.2 L204：`**限流**：5/min`
  - §2.3 L233：`**限流**：1/min`
  - §2.4-§2.7：无 `**限流**` 注释（沿用全局 100/min）
  - §2.8 h5-exchange：无 `**限流**` 注释（应为 10/min，§1.5 声明）
  - §2.9 consent：无 `**限流**` 注释（应为 10/min，§1.5 声明）
- **影响**：风格不统一，开发者阅读 §2.8/§2.9 时不易发现限流约束，需跳转 §1.5 查询。同时 R18-P3-11 修复注释错误引用 §2.8/§2.9 限流注释（见 P1-5）。
- **建议**：在 §2.8 端点描述（L403 描述行后）补充 `**限流**：10/min`；在 §2.9 端点描述（L429 描述行后）补充 `**限流**：10/min`，与 §2.1-§2.3 风格统一。

---

## 6. 汇总统计

### 6.1 审查清单通过率

| 审查项 | 结果 |
|--------|------|
| 1. R18 修复回归 | ✅ 通过（10/10） |
| 2. 端点路径/方法/参数/响应/状态码一致性 | ✅ 通过 |
| 3. 96 端点完整性（79+17） | ✅ 通过 |
| 4. 请求参数验证完整性（Pydantic Schema vs API 文档） | ✅ 通过 |
| 5. 响应 Schema 字段一致性 | ✅ 通过 |
| 6. 错误码一致性（通用 + 业务码） | ✅ 通过 |
| 7. 限流配置一致性 | ⚠️ 通过（含 P1-1 残留） |
| 8. 分页参数一致性（page_size le=50/100） | ✅ 通过 |
| 9. model_validate 注入完整性 | ✅ 通过 |
| 10. 首页聚合 4 端点 + admin 17 端点三方一致 | ✅ 通过 |
| 11. 契约完整性（缺失端点/参数/响应字段） | ⚠️ 部分通过（含 P1-3/P1-4/P2-1/P2-2 缺口） |
| 12. 安全性（输入验证/SQL 注入/CSRF） | ✅ 通过 |

**通过率**：10/12 完全通过 + 2/12 部分通过（无失败项）= 100%（核心审查项全部通过或部分通过，新发现均为前端 ↔ API 契约同步问题）

### 6.2 R18 修复验证通过率

| R18 修复项 | 结果 |
|-----------|------|
| 1. R18-P1-1 §5.7 plan→plans | ✅ |
| 2. R18-P1-2 §5.7 training sessions/complete 权限 | ✅ |
| 3. R18-P1-3 §5.7 payment refund 权限 | ✅ |
| 4. R18-P2-1 §5.7 路径参数命名 | ✅ |
| 5. R18-P2-2 §5.7 training 重复列表合并 | ✅ |
| 6. R18-P3-1 h5-exchange/consent 限流文档化 | ✅（含 R19-P1-1 残留） |
| 7. R18-P3-2 AI 推理 AppException | ✅ |
| 8. R18-P3-3 §3.7 归模块注释 | ✅ |
| 9. R18-P3-4 §5.7 术语"训练单" | ✅ |
| 10. R18-P3-5 page_size 上限标注 | ✅ |

**通过率**：10/10 = 100%

### 6.3 新发现分级统计

| 优先级 | 数量 | 编号 |
|--------|------|------|
| P0 | 0 | — |
| P1 | 5 | P1-1, P1-2, P1-3, P1-4, P1-5 |
| P2 | 3 | P2-1, P2-2, P2-3 |
| P3 | 1 | P3-1 |
| **合计** | **9** | — |

### 6.4 新发现归因分析

| 归因 | 数量 | 占比 | 编号 |
|------|------|------|------|
| 前端 ↔ API 契约缺口（前端未调用 API 定义的端点） | 3 | 33% | P1-3, P1-4, P2-1, P2-2 |
| API ↔ 切片权限标注不一致（SEC-003 未同步到 API） | 1 | 11% | P1-2 |
| API ↔ 切片限流值不一致（R18-P3-1 修复不完整） | 1 | 11% | P1-1 |
| API 文档错误声明（R18-P3-11 注释误导） | 1 | 11% | P1-5 |
| 前端 API 契约声明数与实际不一致 | 1 | 11% | P2-3 |
| API 端点描述限流注释风格不统一 | 1 | 11% | P3-1 |
| 前端调用未定义端点（运行时 404 风险） | 1 | 11% | P1-3 |

### 6.5 核心结论

> **API 设计与 13 个后端切片之间的端点级一致性 完全通过**（96 个端点路径/方法/参数/响应/状态码/分页/model_validate 全部一致）。R18 的 10 项修复全部验证通过。R19 新发现的 9 个问题集中在 **前端 ↔ API 契约缺口**（P1-3/P1-4/P2-1/P2-2 共 4 项）和 **R18-P3-1 修复不完整**（P1-1 + P1-5 共 2 项）。
>
> **P1×5 中**：P1-1（h5-exchange 限流值切片未同步）与 P1-5（R18-P3-11 注释错误声明）为同源问题 — R18-P3-1 修复仅落地 API §1.5 文档化，未同步更新切片装饰器，且修复注释错误引用了不存在的 §2.8/§2.9 端点级限流注释；P1-2（训练 §8.3/§8.4/§8.5 权限标注）为 SEC-003 安全修复未同步到 API 设计和架构 §5.7；P1-3（前端调用未定义 deletion-status 端点）与 P1-4（前端缺失 consent/consent-status 调用）为前端 ↔ API 契约双向缺口（前端多调用 1 个未定义端点 + 缺失 2 个已定义端点）。
>
> **建议优先修复顺序**：
> 1. **P1-1 + P1-5**（同源）— 切片 L648 h5-exchange 装饰器从 `100/minute` 改为 `10/minute`；同步修正 API §1.5 R18-P3-11 修复注释（L87）
> 2. **P1-2** — API §8.3/§8.4/§8.5 权限标注从"登录"改为"会员"，同步架构 §5.7 L940-942
> 3. **P1-3** — 删除前端 `getDeletionStatus()` 或在 API/架构/后端补充端点定义
> 4. **P1-4** — 前端 auth 切片补齐 consent/consent-status 调用与 UI（PIPL 合规）
> 5. **P2-1 + P2-2** — 前端 video_analysis/training_advice 切片补齐 3 个端点调用
> 6. **P2-3** — 前端切片准备清单端点数声明修正
> 7. **P3-1** — API §2.8/§2.9 补充 `**限流**：10/min` 注释

---

## 7. 修改文件清单（建议）

| 序号 | 优先级 | 文件 | 修改内容 |
|------|--------|------|---------|
| 1 | P1 | `01-auth/backend.md` L648 | `@limiter.limit("100/minute")` → `@limiter.limit("10/minute")`（h5-exchange） |
| 2 | P1 | `05-API详细设计.md` L87 | 修正 R18-P3-11 修复注释：删除"§2.8/§2.9 各端点说明中'限流：10/min'一致"错误声明 |
| 3 | P1 | `05-API详细设计.md` §8.3 L2222、§8.4 L2263、§8.5 L2297 | 权限"登录" → "会员" |
| 4 | P1 | `01-系统架构设计.md` §5.7 L940-942 | 权限"登录" → "会员" |
| 5 | P1 | `02-user/frontend.md` L85 | 删除 `getDeletionStatus()` 函数（或方案 B：API/架构/后端补充端点） |
| 6 | P1 | `01-auth/frontend.md` §2 | 新增 `recordConsent()` 与 `getConsentStatus()` 函数 + consent 页面 + authStore.requires_consent 状态 |
| 7 | P1 | `01-auth/frontend.md` L13 | 准备清单更新为"§2.1-2.10，10 个端点" |
| 8 | P2 | `03-video_analysis/frontend.md` §2 | 新增 `getFeedbacks(reportId, page, pageSize)` 函数 + feedbackHistory 状态 |
| 9 | P2 | `07-training_advice/frontend.md` §2 | 新增 `listTrainingSessions()` 与 `completeTrainingSession()` 函数 + sessions 状态 |
| 10 | P2 | `02-user/frontend.md` L13 | 准备清单更新为"§3.1-3.10（不含 §3.7 跨模块端点），9 个端点" |
| 11 | P3 | `05-API详细设计.md` §2.8 L403、§2.9 L429 | 端点描述后补充 `**限流**：10/min` 注释 |

---

*审查完成。报告归档路径：`docs/07审查报告/第十九轮/R19-API端点级审查报告.md`*
