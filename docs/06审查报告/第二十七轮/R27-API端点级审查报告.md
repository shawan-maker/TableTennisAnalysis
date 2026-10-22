# R27 — API 端点级 + 前后端契约完整性审查报告

> **审查代理**：第二十七轮 API 端点级 + 前后端契约完整性维度
> **审查日期**：2026-10-20
> **工作目录**：D:\PyProject\TableTennisAnalysis
> **审查基线**：R26-API 端点级审查报告（2026-10-20）+ API 设计 v1.3 + 架构 §5.7（L804-958）+ 12 后端切片 + 13 前端切片 + 13-infrastructure/admin.md
> **目标**：连续第五轮无 P2+（API 维度）— 验证 R22-P1-1 + R21-P3-1 + R25-P3-1 三项修复在 R26 → R27 周期回归稳定性 + 96 端点三方契约完整性 + consent 链路对称性 + §8.7/§8.8 训练单契约 + model_validate/限流/分页参数/错误码/首页聚合 + 复核 R26 §8.1 提出的"切片 03/09 编码损坏范围扩展验证"短近项
> **审查重点**：寻找任何遗漏的 P2+ 问题，验证 API 维度进入"持续稳定期"后的第三轮稳定性；并对照实际 grep 与 R26 报告中各项数值声明（错误码计数、model_validate 计数、consent 链路计数）进行复核

---

## 1. 执行摘要

### 1.1 审查清单（8 项）

| 序号 | 文件 | 用途 |
|------|------|------|
| 1 | `docs/04详细设计/05-API详细设计.md`（v1.3，5200+ 行） | API 设计权威源（§1.2 分页 L45-49、§1.5 限流 L74-89、§1.7 通用错误码 L95-111、§1.8 业务错误码 L113-130、§2.1 wechat-login L137-198、§2.2 phone-login L200-227、§2.9 consent L430-476、§2.10 consent-status L478-511、§8.7 sessions list L2363-2406、§8.8 session complete L2408-2448、§14a 首页聚合 L3412-3423、§19 admin L5064-5300+） |
| 2 | `docs/03系统架构/01-系统架构设计.md` §5.7（L804-958） | Phase 1 核心 API 端点清单（96 端点 = 79 业务 + 17 admin） |
| 3 | `docs/06垂直模块前后端切片设计/01-auth/backend.md`（779 行） | 认证切片后端（LoginResponse L217-222、ConsentResponse L204-207、wechat_login L325-340、phone_login L343-379、check_consent L468-488、record_consent L490-512、路由 L592-680） |
| 4 | `docs/06垂直模块前后端切片设计/01-auth/frontend.md`（970+ 行） | 认证切片前端（wechatLogin L162-185、phoneLogin L187-210、checkConsentStatus L276-286） |
| 5 | `docs/06垂直模块前后端切片设计/07-training_advice/backend.md`（1302 行） | 训练切片后端（TrainingSessionBrief L481-493、TrainingSessionCompleteResponse L506-514、Service L1038-1155、路由 L1208-1301） |
| 6 | `docs/06垂直模块前后端切片设计/07-training_advice/frontend.md`（1830+ 行） | 训练切片前端（TrainingSessionItem L112-123、CompleteSessionData L134-139） |
| 7 | `docs/06垂直模块前后端切片设计/00-home/frontend.md`（1230+ 行） | 首页聚合前端（getOverview L82-84、getCheckinCalendar L89-91、getLatestReport L96-98、getUnreadCount L103-105） |
| 8 | grep `@router\.(get\|post\|put\|patch\|delete)` + `raise AppException\|raise HTTPException` + `model_validate\(\|\.model_validate` + `Query\(default=20, ge=1, le=50\)` + `Query\(default=20, ge=1, le=100\)` + `requires_consent\|consented\|check_consent\|record_consent` + `@limiter\.limit` + `home/dashboard` | 端点计数、错误码、Schema 注入、分页参数、consent 链路、限流装饰器、首页聚合引用一致性 |

### 1.2 执行摘要

本轮审查聚焦 **R26 已达成 API 维度连续第四轮无 P2+ 之后的持续稳定期第三轮验证**（R22-P1-1 phone_login Service requires_consent 计算与注入 + R21-P3-1 §8.7 sessions page_size Query ge=1 约束 + R25-P3-1 §3.1 端点计数偏差叙事修正三项修复在 R26 全部闭环，本轮确认无回退、无副作用）+ 96 端点三方契约完整性 + consent 链路对称性 + §8.7/§8.8 训练单契约 + model_validate/限流/分页参数/错误码/首页聚合 + 复核 R26 §8.1 提出的切片 03/09 编码损坏扩展范围短近项。**所有契约层检查项保持稳定，API 维度正式达成"连续第五轮无 P2+"目标 ✅**：

- **三项修复回归稳定性通过率**：3/3 保持完全闭环 ✅（R22-P1-1 phone_login 补 requires_consent 计算+注入 ✅ 保持稳定；R21-P3-1 §8.7 page_size Query 补 ge=1 ✅ 保持稳定；R25-P3-1 §3.1 端点计数偏差叙事修正 ✅ 保持稳定）
- **新发现**：P0×0 + P1×0 + P2×0 + P3×4 = **4 项新发现**（全部为 P3 叙事/复核类，不影响实质契约内容）
- **新发现归因**：
  - **P2+ 维度**：本轮对 96 端点三方契约、consent 链路、§8.7/§8.8 训练单四方对齐、14 处分页参数、错误码统一性、22 处 model_validate 注入、§14a 首页聚合 4 端点进行全量核查，未发现任何 P2+ 级别新问题。R22-P1-1 + R21-P3-1 + R25-P3-1 三项修复保持完全闭环，96 端点完整性持续维持 100%。
  - **P3 维度（4 项叙事/复核类）**：
    - **R27-P3-1**：R26 §4.4 报告"全切片返回 84 处 raise AppException|raise HTTPException 匹配"，实际计数为 105 处（含 admin.md 21 处）；84 = 105 − 21（admin.md 计数被排除）。R26 §2.1 列出"12 后端切片"范围不含 admin.md，但 §4.4 措辞"全切片"易误导。行为正确（100% AppException + 0% HTTPException），仅数值/措辞需澄清。
    - **R27-P3-2**：R26 §4.7 报告"model_validate 16 处匹配覆盖 8 切片"，实际覆盖 9 切片（03/07/08/05/11/02/04/12/06，admin.md 6 处未计入）；"16 处"匹配数正确，"8 切片"应为"9 切片"，且 admin.md 实际亦使用 model_validate（AdminBrief/UserManageBrief/ConfigBrief），R26 称 13-admin 通过直接构造 Pydantic Schema 注入的描述与实际不符。
    - **R27-P3-3**：API §14a L3421 声称"架构 §5.7 API 清单中声明的 `GET /home/dashboard` 即指此前端聚合模式"，但实际架构 §5.7（L948-956）从未出现"`GET /home/dashboard`"端点声明，仅在 L948 提到"#### 首页聚合（前端多模块聚合，无独立后端端点）"标题。grep `home/dashboard` 在架构文档返回 0 匹配，API 文档对架构的引用不实。
    - **R27-P3-4**：R26 §8.1 短近项"切片 03/09 编码损坏范围"实际超出 R26 所述 — 经 grep 验证损坏扩展至 `01-auth/backend.md`（L195/218/219/225/226/230/517/542/546/550/553/558，含 LoginResponse/RefreshResponse/H5TokenResponse/access_token/refresh_token 字段类型被 `[REDACTED]]]]` 占位）、`04详细设计/05-API详细设计.md`（L57 Authorization Header 行被 `[REDACTED]]]]` 占位）、`13-infrastructure/admin.md`（L880 管理员 session_token 字段示例被 `[REDACTED]]]]` 占位）。损坏为文档级（类型标注被 redact 占位），不影响 grep 准确性（关键字搜索全部有效），不影响契约语义（字段名、Pydantic 默认值、Service 注入行均完整可读）。
- **目标达成状态**：✅ **API 维度连续第五轮无 P2+ 正式达成**。R23（连续第一轮）+ R24（连续第二轮）+ R25（连续第三轮）+ R26（连续第四轮）+ R27（连续第五轮）连续五轮零 P2+ 新发现。R22-P1-1 + R21-P3-1 + R25-P3-1 三项修复全部闭环后，96 端点完整性持续维持 100%，consent 链路 phone_login 与 wechat_login 完全对称，分页参数 14/14 全部 `Query(default=20, ge=1, le=50/100)` 一致，错误码 105/105 全部 `raise AppException` + 0 处 `raise HTTPException` 统一，model_validate 注入 22 处覆盖 10 切片（含 admin.md 6 处），首页聚合 4 端点三方一致。R26 §8.1 提出的"切片编码损坏扩展验证"短近项本轮闭环（损坏范围已澄清，影响评估为 P3 文档质量类，无 P2+ 升级）。

### 1.3 关键统计

| 审查项 | R26 现状 | R27 现状 | 变化 |
|--------|---------|---------|------|
| 新发现 P0 | 0 | 0 | 持平 |
| 新发现 P1 | 0 | 0 | 持平 |
| 新发现 P2 | 0 | 0 | 持平 ✅ |
| 新发现 P3 | 0 | 4（叙事/复核类） | +4（均为不影响实质内容的叙事澄清） |
| 新发现 P2+ 合计 | 0 | 0 | 持平 ✅ |
| 三项修复回归稳定性通过率 | 3/3 保持完全闭环 | 3/3 保持完全闭环（100%） | ✅ 无回退 |
| 96 端点三方一致性 | 96/96 | **96/96** | 持平 ✅ |
| consent 链路完整性 | 17 处 backend grep 匹配 | 17 处 backend grep 匹配保持稳定 | 持平 ✅ |
| 分页参数 ge=1 一致性 | 14/14（12 用户端 + 2 admin） | **14/14** | 持平 ✅ |
| 错误码统一性 | 84 处 `raise AppException` + 0 `raise HTTPException`（R26 计数偏差，实际 105） | **105/105** `raise AppException` + 0 `raise HTTPException` | 数值修正（R27-P3-1） |
| model_validate 注入完整性 | 16 处覆盖 8 切片（R26 切片计数偏差，实际 9 切片+admin.md=10 切片共 22 处） | **22 处覆盖 10 切片** | 数值修正（R27-P3-2） |
| 首页聚合 4 端点一致性 | 4/4 | 4/4（API §14a ↔ 架构 §5.7 ↔ 前端 home/frontend.md） | 持平 ✅（§14a L3421 引用偏差不影响端点本身一致性，R27-P3-3） |
| 连续无 P2+ 目标 | 第四轮达成 ✅ | **第五轮达成 ✅（持续稳定期第三轮）** | +1 轮 ✅ |

### 1.4 连续五轮无 P2+ 追踪

| 轮次 | API 维度 P2+ 新发现 | 连续轮次判定 |
|------|------------------|------------|
| R22 | 1（R22-P1-1 phone_login 缺 requires_consent） | 基线（含 P1，未启动连续轮计数） |
| R23 | 0 | 连续第一轮达成 ✅ |
| R24 | 0 | 连续第二轮达成 ✅ |
| R25 | 0 | 连续第三轮达成 ✅（进入"持续稳定期"） |
| R26 | 0 | 连续第四轮达成 ✅（持续稳定期第二轮） |
| R27 | 0 | **连续第五轮达成 ✅（持续稳定期第三轮，复核 R26 §8.1 短近项后确认无 P2+ 升级）** |

---

## 2. 审查范围与方法

### 2.1 审查范围

本轮 API 端点级审查覆盖以下五类基准文档的交叉对比：

1. **API 设计 v1.3**（`docs/04详细设计/05-API详细设计.md`，5200+ 行）：§1 通用规范（分页 L45-49、限流 L74-89、错误码 L95-130）、§2 auth（10 端点）、§3 users（9 端点，§3.7 反馈历史跨模块计 video_analysis）、§4 video-analysis（12 端点含 §3.7）、§5 scoring（10 端点）、§6 dashboard（5 端点）、§7 match-data（4 端点）、§8 training（8 端点含 §8.7/§8.8）、§9 progress（6 端点）、§10 gamification（4 端点）、§11 membership（3 端点）、§12 payment（4 端点）、§13 notification（4 端点）、§14a 首页聚合、§19 admin（17 端点，含 §19.1 认证说明 L5072-5102 + §19.2-§19.6 端点详细 L5106-5300+）
2. **架构 §5.7**（`docs/03系统架构/01-系统架构设计.md` L804-958）：Phase 1 核心 API 端点清单（96 端点 = 79 业务 + 17 admin）+ L948-956 首页聚合段（前端聚合，无独立后端端点）
3. **12 后端切片**（`docs/06垂直模块前后端切片设计/01-auth/backend.md` 等）：@router 装饰器 + Pydantic Schema + Service model_validate + 错误处理
4. **13 前端切片**（`docs/06垂直模块前后端切片设计/01-auth/frontend.md` 等）：API 调用 + TypeScript interface 字段对齐
5. **R26-API 基线报告**（`docs/07审查报告/第二十六轮/R26-API端点级审查报告.md`）：3 项修复闭环状态 + 0 项 P3 新发现 + §8.1 短近项（切片 03/09 编码损坏范围扩展验证）

### 2.2 审查方法

采用 **10 项检查清单 + grep 模式扫描 + 三方交叉对照 + R26 报告数值复核**：

1. **三方一致性**：API §2-§19 ↔ 架构 §5.7 L814-946 ↔ 切片 @router 装饰器
2. **96 端点完整性**：79 业务 + 17 admin = 96（含 1 Phase 2+ 占位）
3. **Schema 字段一致性**：§2.1/§2.2/§2.9/§2.10/§8.7/§8.8 响应字段 vs 后端 Pydantic Schema vs 前端 TypeScript interface
4. **错误码一致性**：API §1.7 通用错误码 + §1.8 业务错误码 vs 切片 `raise AppException`/`raise HTTPException` + 数值复核（R26 报告 84 处 vs 实际 105 处）
5. **限流配置一致性**：API §1.5 限流表 + §19.1 admin 限流表 vs 切片 `@limiter.limit` 装饰器
6. **分页参数 ge=1/le=50/le=100**：14 处 `Query(default=20, ge=1, le=50/100)` 一致性
7. **model_validate 注入完整性**：Schema 字段 vs Service 层 `model_validate` 注入 + 数值复核（R26 报告 16 处覆盖 8 切片 vs 实际 22 处覆盖 10 切片）
8. **§8.7/§8.8 训练单契约**：API §8.7 L2386-2394 ↔ Schema L481-493 ↔ Service L1056-1067 ↔ 前端 interface L112-123
9. **consent 链路 requires_consent vs consented**：API §2.1/§2.2/§2.9/§2.10 ↔ 后端 Service L325-340/L364-378 ↔ 前端 L162-210/L276-286
10. **首页聚合 4 端点 + §14a 引用一致性**：API §14a L3414-3423 ↔ 架构 §5.7 L948-956 ↔ 前端 home/frontend.md L82-105 + grep `home/dashboard` 跨文档复核

---

## 3. 端点计数三方一致性

### 3.1 业务端点分布（79 端点）

| 模块 | API § | 架构 §5.7 行号 | 切片 @router 行号 | 计数 | 一致性 |
|------|-------|---------------|-----------------|------|--------|
| auth | §2 | L814-823 | 01-auth/backend.md L593, 599, 605, 611, 617, 631, 648, 654, 661, 680 | 10 | ✅ |
| users | §3 | L829-837 | 02-user/backend.md L776, 786, 797, 808, 820, 830, 841, 851, 861 | 9 | ✅ |
| video-analysis | §4 | L843-854 | 03-video_analysis/backend.md L1140, 1151, 1162, 1173, 1186, 1197, 1208, 1220, 1234, 1247, 1258, 1283(@share_router) | 12 | ✅ |
| scoring | §5 | L860-869 | 04-scoring/backend.md L1144, 1154, 1168, 1178, 1189, 1200, 1210, 1220, 1231, 1242 | 10 | ✅ |
| match-data | §7 | L875-878 | 05-match_data/backend.md L923, 933, 946, 956 | 4 | ✅ |
| dashboard | §6 | L884-888 | 06-data_dashboard/backend.md L782, 789, 799, 806, 813 | 5 | ✅ |
| training | §8 | L939-946 | 07-training_advice/backend.md L1209, 1219, 1228, 1242, 1252, 1262, 1274, 1291 | 8 | ✅ |
| progress | §9 | L926-931 | 08-progress_analysis/backend.md L1373, 1387, 1397, 1408, 1421, 1431 | 6 | ✅ |
| gamification | §10 | L894-897 | 09-gamification/backend.md L1063, 1074, 1094, 1105 | 4 | ✅ |
| membership | §11 | L903-905 | 10-membership/backend.md L801, 812, 823 | 3 | ✅ |
| payment | §12 | L906-909 | 11-payment/backend.md L1341, 1357, 1377, 1415 | 4 | ✅ |
| notification | §13 | L915-918 | 12-notification/backend.md L660, 676, 686, 696 | 4 | ✅ |
| **合计** | — | — | — | **79** | ✅ |

### 3.2 admin 端点分布（17 端点）

| API §19.2-§19.6 | 架构 §5.7（admin 段未显式列出，统一归 §19） | 切片 @router 行号 | 计数 | 一致性 |
|-----------------|----------------------------------------|-----------------|------|--------|
| §19.2.1 POST /admin/login | — | 13-infrastructure/admin.md L874 | 1 | ✅ |
| §19.2.2 POST /admin/logout | — | L882 | 1 | ✅ |
| §19.2.3 GET /admin/users | — | L895（page_size=100 at L900） | 1 | ✅ |
| §19.2.4 POST /admin/users/{user_id}/ban | — | L909 | 1 | ✅ |
| §19.2.5 POST /admin/users/{user_id}/unban | — | L920 | 1 | ✅ |
| §19.3.1 GET /admin/configs | — | L931 | 1 | ✅ |
| §19.3.2 GET /admin/configs/{key} | — | L940 | 1 | ✅ |
| §19.3.3 POST /admin/configs | — | L950 | 1 | ✅ |
| §19.3.4 PATCH /admin/configs/{key} | — | L960 | 1 | ✅ |
| §19.3.5 DELETE /admin/configs/{key} | — | L971 | 1 | ✅ |
| §19.4.1 GET /admin/audit-logs | — | L982（page_size=100 at L990） | 1 | ✅ |
| §19.5.1 POST /admin/knowledge/categories | — | L1004 | 1 | ✅ |
| §19.5.2 PATCH /admin/knowledge/categories/{category_id} | — | L1014 | 1 | ✅ |
| §19.5.3 DELETE /admin/knowledge/categories/{category_id} | — | L1025 | 1 | ✅ |
| §19.5.4 POST /admin/knowledge/rules | — | L1035 | 1 | ✅ |
| §19.5.5 PATCH /admin/knowledge/rules/{rule_id}/toggle | — | L1045 | 1 | ✅ |
| §19.6.1 POST /admin/model-versions/{version_id}/activate（Phase 2+ 占位） | — | L1058（注释标记 Phase 2+） | 1 | ✅ |
| **合计** | — | — | **17** | ✅ |

### 3.3 总计

| 维度 | API 设计 | 架构 §5.7 | 切片实现 | 一致性 |
|------|---------|----------|---------|--------|
| 业务端点 | 79 | 79（L814-946） | 79（含 1 @share_router） | ✅ 100% |
| admin 端点 | 17 | 17（§19 引用） | 17（16 active + 1 Phase 2+ 占位） | ✅ 100% |
| **总计** | **96** | **96** | **96** | ✅ 100% |

**R25-P3-1 §3.1 端点计数偏差已在 R25 落地修正，R27 验证保持稳定，无残留** ✅

---

## 4. 10 项检查清单结果

### 4.1 检查清单 1：三方一致性 ✅

- **API §2-§19 ↔ 架构 §5.7 L814-946 ↔ 切片 @router**：96 端点路径/HTTP 方法/权限标注三方完全一致
- **首页聚合 §14a**：API L3414-3423 + 架构 §5.7 L948-956 + 前端 home/frontend.md L82-105 三方一致（注：§14a L3421 对架构 §5.7 引用措辞不实，详见 §6.3 R27-P3-3，但 4 个聚合端点本身三方一致）
- **跨模块 §3.7 反馈历史**：API §4.8 `/video-analysis/reports/{report_id}/feedbacks` + 架构 L851 + 切片 03 L1234 三方一致

### 4.2 检查清单 2：96 端点完整性 ✅

- 业务端点 79 + admin 端点 17 = 96 ✅
- 含 1 @share_router（03-video_analysis L1283）+ 1 Phase 2+ 占位（admin L1058）

### 4.3 检查清单 3：Schema 字段一致性 ✅

#### §2.1 wechat-login + §2.2 phone-login 响应
| API 字段 | 后端 Schema | 前端读取 | 一致性 |
|---------|------------|---------|--------|
| access_token | LoginResponse L218 ✅ | wechatLogin L168 / phoneLogin L193 ✅ | ✅ |
| refresh_token | LoginResponse L219 ✅ | wechatLogin L168 / phoneLogin L193 ✅ | ✅ |
| expires_in | LoginResponse L220 ✅ | — | ✅ |
| requires_consent | LoginResponse L222 ✅（R22-P1-1 注入） | wechatLogin L168 / phoneLogin L193 ✅ | ✅ |
| user{id, nickname, avatar_url, has_profile} | LoginResponse L221 + UserBrief L210-215 ✅ | wechatLogin L168 / phoneLogin L193 ✅ | ✅ |

#### §2.9 consent + §2.10 consent-status 响应
| API 字段 | 后端 Schema | 前端读取 | 一致性 |
|---------|------------|---------|--------|
| consented | ConsentResponse L205 ✅ | checkConsentStatus L279 ✅ | ✅ |
| consent_at | ConsentResponse L206 ✅ | — | ✅ |
| policy_version | ConsentResponse L207 ✅ | — | ✅ |

#### §8.7 training sessions list + §8.8 session complete 响应
| API 字段 | 后端 Schema | 前端 interface | 一致性 |
|---------|------------|---------------|--------|
| id | TrainingSessionBrief L484 ✅ | TrainingSessionItem L113 ✅ | ✅ |
| session_index | L491 ✅（R21-P2-1） | L121 ✅ | ✅ |
| name | L486 ✅ | L115 ✅ | ✅ |
| reps | L492 ✅（R21-P2-1） | L122 ✅ | ✅ |
| is_completed | L487 ✅ | L117 ✅ | ✅ |
| completed_at | L489 ✅ | L118 ✅ | ✅ |
| plan_id（additive） | L485 ✅（additive） | L114 ✅ | ✅（R26 已确认 additive，前端在路由 `/pages/training/plans/[plan_id]/index` 使用，API §8.7 响应 JSON 未显式列出） |
| scheduled_date（additive） | L488 ✅（additive） | L116 ✅ | ✅（R26 已确认 additive，前端在 L1166 `{session.scheduled_date \|\| '-'}` 显示，API §8.7 响应 JSON 未显式列出） |
| session_id | TrainingSessionCompleteResponse L509 ✅ | CompleteSessionData L135 ✅ | ✅ |
| is_completed | L510 ✅ | L136 ✅ | ✅ |
| plan_progress (int 0-100) | L512 ✅（R21-P2-2） | L137 ✅ | ✅ |
| points_earned | L513 ✅ | L138 ✅ | ✅ |
| completed_at（additive） | L514 ✅（additive） | — | ✅ |

### 4.4 检查清单 4：错误码一致性 ✅ + R26 计数偏差修正（R27-P3-1）

- **统一使用 AppException**：grep `raise AppException|raise HTTPException` 全切片返回 **105 处匹配**（R26 报告 84 处偏差，详见 §6.1 R27-P3-1），**100% 使用 `raise AppException`，0 处 `raise HTTPException`** ✅

  各切片分布（rg --count-matches 复核）：

  | 切片 | raise AppException 数 | raise HTTPException 数 | 一致性 |
  |------|----------------------|------------------------|--------|
  | 01-auth/backend.md | 9 | 0 | ✅ |
  | 02-user/backend.md | 5 | 0 | ✅ |
  | 03-video_analysis/backend.md | 19 | 0 | ✅ |
  | 04-scoring/backend.md | 14 | 0 | ✅ |
  | 05-match_data/backend.md | 6 | 0 | ✅ |
  | 06-data_dashboard/backend.md | 0 | 0 | ✅（该切片通过 success() 包装，无业务异常抛出） |
  | 07-training_advice/backend.md | 10 | 0 | ✅ |
  | 08-progress_analysis/backend.md | 4 | 0 | ✅ |
  | 09-gamification/backend.md | 1 | 0 | ✅ |
  | 10-membership/backend.md | 0 | 0 | ✅（该切片通过 success() 包装，无业务异常抛出） |
  | 11-payment/backend.md | 15 | 0 | ✅ |
  | 12-notification/backend.md | 1 | 0 | ✅ |
  | 13-infrastructure/admin.md | 21 | 0 | ✅ |
  | **合计** | **105** | **0** | ✅ 统一 |

- **HTTP 标准码符合 §1.7**：400（业务校验）/401（认证）/403（权限）/404（资源不存在）/409（冲突）/422（参数校验）/429（限流）/502（第三方服务）分布与 §1.7 全局通用错误码表一致
- **错误消息规范**：404 错误消息遵循 `{资源名}不存在` 格式（如"报告不存在"、"比赛不存在"、"订单不存在"），符合 §1.7 404 错误消息规范

### 4.5 检查清单 5：限流配置一致性 ✅

| API §1.5 限流表 + §19.1 admin 限流表 | 切片 @limiter.limit | 一致性 |
|--------------|-------------------|--------|
| 微信登录 10/min（§1.5） | 01-auth/backend.md L592 `@limiter.limit("10/minute")` ✅ | ✅ |
| 手机号登录 5/min（§1.5） | L598 `@limiter.limit("5/minute")` ✅ | ✅ |
| 发送短信 1/min（§1.5） | L604 `@limiter.limit("1/minute", key_func=...)` ✅ | ✅ |
| H5 Token 换 JWT 10/min（§1.5，R19-P1-5 + R19-P3-1 修复） | L653 `@limiter.limit("10/minute")` ✅（R19-P1-1 修复保持闭环） | ✅ |
| 隐私政策同意 10/min（§1.5） | L660 `@limiter.limit("10/minute")` ✅ | ✅ |
| AI 分析任务创建 10/hour + 免费 3/天（§1.5） | 03-video_analysis/backend.md L1161 `@limiter.limit("10/hour", key_func=...)` ✅ | ✅ |
| 报告分享 5/天（§1.5） | L1257 `@limiter.limit("5/day", key_func=...)` ✅ | ✅ |
| 全局 100 req/min（§1.5） | 所有其他业务端点 `@limiter.limit("100/minute")` ✅ | ✅ |
| gamification checkin 1/天（§10.3） | 09-gamification/backend.md L1093 `@limiter.limit("1/day", key_func=...)` ✅ | ✅ |
| POST /admin/login 5/min（§19.1 + §19.2.1） | 13-infrastructure/admin.md L873 `@limiter.limit("5/minute")` ✅（防暴力破解） | ✅ |
| 其他管理端点 100/min（§19.1） | admin.md L881-1057 全部 `@limiter.limit("100/minute")` ✅ | ✅ |

### 4.6 检查清单 6：分页参数 ge=1/le=50/le=100 ✅

- **用户端 12 处** `Query(default=20, ge=1, le=50)`：
  - 03-video_analysis L1177, L1211, L1238（3 处）
  - 04-scoring L1158（1 处）
  - 05-match_data L937（1 处）
  - 07-training_advice L1232, L1278（2 处，L1278 为 R21-P3-1 修复保持闭环）
  - 08-progress_analysis L1377（1 处）
  - 02-user L811（1 处）
  - 11-payment L1362（1 处）
  - 12-notification L665（1 处）
  - 06-data_dashboard L817（1 处）
- **admin 2 处** `Query(default=20, ge=1, le=100)`：
  - 13-infrastructure/admin.md L900（/admin/users）+ L990（/admin/audit-logs）
- **grep `Query\(20, le=50\)|Query\(default=20, le=50\)|Query\(default=20, le=100\)|Query\(default=20, ge=1, le=100\)|Query\(20, le=100\)|Query\(20\)` 零匹配**（R21-P3-1 修复保持闭环，无非标准分页参数残留） ✅

### 4.7 检查清单 7：model_validate 注入完整性 ✅ + R26 切片计数偏差修正（R27-P3-2）

grep `model_validate\(|\.model_validate` 返回 **22 处匹配覆盖 10 切片**（R26 报告"16 处覆盖 8 切片"偏差，详见 §6.2 R27-P3-2）：

| 切片 | 行号 | 注入对象 | 一致性 |
|------|------|---------|--------|
| 02-user | L527 | RatingHistoryItem.model_validate(r)（列表推导） | ✅ |
| 03-video_analysis | L854 | ReportDetailResponse.model_validate(report) | ✅ |
| 04-scoring | L700 | MatchBrief.model_validate(m)（列表推导） | ✅ |
| 04-scoring | L716 | MatchDetailWithSequence.model_validate(match) | ✅ |
| 05-match_data | L820 | MatchRecordBrief.model_validate(r)（列表推导） | ✅ |
| 05-match_data | L844 | MatchRecordDetail.model_validate(record) | ✅ |
| 06-data_dashboard | L692 | MatchRecordBrief.model_validate(r)（列表推导） | ✅ |
| 07-training_advice | L791 | TemplateBrief.model_validate(t)（列表推导） | ✅ |
| 07-training_advice | L806 | TemplateDetail.model_validate(template) | ✅ |
| 08-progress_analysis | L915 | SnapshotBrief.model_validate(s)（列表推导） | ✅ |
| 08-progress_analysis | L925/972/1105/1199 | model_validate_json(cached)（缓存反序列化，4 处） | ✅ |
| 11-payment | L919 | OrderBrief.model_validate(o)（列表推导） | ✅ |
| 12-notification | L500 | NotificationBrief.model_validate(r)（列表推导） | ✅ |
| 13-infrastructure/admin.md | L397 | AdminBrief.model_validate(admin)（管理员信息） | ✅ |
| 13-infrastructure/admin.md | L458 | UserManageBrief.model_validate(u) for u in items（列表推导） | ✅ |
| 13-infrastructure/admin.md | L524 | ConfigBrief.model_validate(c) for c in result（列表推导） | ✅ |
| 13-infrastructure/admin.md | L550 | ConfigBrief.model_validate(config)（单条详情） | ✅ |
| 13-infrastructure/admin.md | L580 | ConfigBrief.model_validate(config)（更新后返回） | ✅ |
| 13-infrastructure/admin.md | L613 | ConfigBrief.model_validate(config)（创建后返回） | ✅ |

**01-auth/09-gamification/10-membership 通过直接构造 Pydantic Schema 对象注入**（如 `LoginResponse(access_token=..., requires_consent=..., user=...)`、`PointsResponse(...)`、`MembershipTierBrief(...)`），与 `model_validate` 等效，注入完整性保持。

**R26 §4.7 称 13-admin 通过直接构造 Pydantic Schema 注入的描述与实际不符**：admin.md 实际使用 6 处 `model_validate`（AdminBrief/UserManageBrief/ConfigBrief），与直接构造并存，R27-P3-2 已修正。

### 4.8 检查清单 8：§8.7/§8.8 训练单契约四方对齐 ✅

**§8.7 TrainingSessionBrief 四方对齐**（R21-P2-1 session_index/reps 修复保持闭环）：
- API §8.7 L2386-2394 响应 JSON 示例：id, session_index, name, reps, is_completed, completed_at（6 字段）
- Schema L481-493：8 字段全部对齐（含 plan_id/scheduled_date additive，R26 已确认）✅
- Service L1056-1067：`TrainingSessionBrief(id=..., session_index=s.get("session_index", i+1), reps=s.get("reps", 0), ...)` ✅
- 前端 interface L112-123：8 字段全部对齐 ✅

**注**：API §8.7 响应 JSON 示例仅列 6 字段，Schema/前端有 8 字段（plan_id/scheduled_date 为 additive）。R26 §4.8 表格已标记为"（additive）✅"，R27 维持此判定 — additive 字段不破坏向前兼容性，前端确实使用这两个字段（plan_id 用于路由参数、scheduled_date 在 L1166 显示），属于 API 文档未完整列出但实际返回的向前兼容字段，无 P2+ 升级必要。

**§8.8 TrainingSessionCompleteResponse 四方对齐**（R21-P2-2 plan_progress int 0-100 修复保持闭环）：
- API §8.8 L2423：session_id, is_completed, plan_progress (int 0-100), points_earned
- Schema L506-514：4 字段全部对齐，plan_progress `int = Field(..., description="计划完成进度（0-100 百分比）")` ✅
- Service L1148-1154：`plan_progress=int(plan_progress * 100)`（float 0.0-1.0 → int 百分比）✅
- 前端 interface L134-139：4 字段全部对齐，plan_progress 注释 `// 0-100` ✅

### 4.9 检查清单 9：consent 链路 requires_consent vs consented ✅

grep `requires_consent|consented|check_consent|record_consent`：
- `01-auth/backend.md`：17 行匹配（22 处匹配，与 R26 §4.9 报告的 17 处一致，R26 统计为行数非匹配数，无差异）
- `01-auth/frontend.md`：27 行匹配（41 处匹配）

后端 consent 链路（17 行 grep 匹配）：

| 位置 | 行号 | 用途 | 一致性 |
|------|------|------|--------|
| ConsentResponse Schema | L205 | `consented: bool` 字段定义 | ✅ |
| LoginResponse Schema | L222 | `requires_consent: bool = False` 字段定义（R22-P1-1） | ✅ |
| wechat_login Service | L326 | `consent = await AuthService.check_consent(user.id)` 调用 | ✅ |
| wechat_login Service | L327 | `requires_consent = not consent["consented"]` 计算 | ✅ |
| wechat_login Service | L339 | `requires_consent=requires_consent` 注入 | ✅ |
| phone_login Service | L364 | R22-P1-1 注释（与 wechat_login L325-L327 对称） | ✅ |
| phone_login Service | L365 | `consent = await AuthService.check_consent(user.id)` 调用（R22-P1-1） | ✅ |
| phone_login Service | L366 | `requires_consent = not consent["consented"]` 计算（R22-P1-1） | ✅ |
| phone_login Service | L378 | `requires_consent=requires_consent` 注入（R22-P1-1，与 wechat_login L339 对称） | ✅ |
| check_consent 方法 | L468 | `async def check_consent(user_id: int) -> dict:` 签名 | ✅ |
| check_consent 方法 | L487 | `return {"consented": True, ...}` | ✅ |
| check_consent 方法 | L488 | `return {"consented": False, ...}` | ✅ |
| record_consent 方法 | L491 | `async def record_consent(...)` 签名 | ✅ |
| record_consent 方法 | L512 | `return {"consented": True, ...}` | ✅ |
| consent 路由 | L662 | `async def record_consent(...)` 路由函数 | ✅ |
| consent 路由 | L670 | `data = await AuthService.record_consent(...)` 调用 | ✅ |
| consent-status 路由 | L683 | `data = await AuthService.check_consent(user.id)` 调用 | ✅ |

**前端 consent 链路**：
- wechatLogin L168：`const { access_token, refresh_token, user, requires_consent } = res.data.data` ✅
- wechatLogin L174：`user: { ...user, needs_consent: requires_consent }`（极性对齐，store 统一字段）✅
- wechatLogin L178-180：`if (requires_consent) { Taro.navigateTo({ url: '/pages/auth/consent/index' })` ✅
- phoneLogin L193：`const { access_token, refresh_token, user, requires_consent } = res.data.data` ✅
- phoneLogin L199：`user: { ...user, needs_consent: requires_consent }` ✅
- phoneLogin L203-205：`if (requires_consent) { Taro.navigateTo({ url: '/pages/auth/consent/index' })` ✅
- checkConsentStatus L279：`const consented = !!res.data?.data?.consented` ✅
- checkConsentStatus L281：`needs_consent: !consented`（极性反转）✅

**R22-P1-1 phone_login Service 补 requires_consent 计算与注入修复在 R26 → R27 周期保持完全闭环，与 wechat_login L325-340 完全对称，无回退** ✅

### 4.10 检查清单 10：首页聚合 4 端点三方一致性 ✅ + §14a 引用一致性偏差（R27-P3-3）

**API §14a L3414-3423**：首页聚合为前端聚合模式，无独立后端端点，前端 `services/home.ts` 并发调用 4 个已有端点：
1. `GET /dashboard/overview`（含 latest_advice_summary 字段）
2. `GET /gamification/checkin-calendar`
3. `GET /scoring/matches`（最近比赛）
4. `GET /notification/unread-count`

**架构 §5.7 L948-956**：`#### 首页聚合（前端多模块聚合，无独立后端端点）`，列出 4 个端点引用（L950-953）：
- `GET /dashboard/overview`（用户栏+训练建议摘要）
- `GET /gamification/checkin-calendar`（打卡日历）
- `GET /scoring/matches`（最近比赛记录）
- `GET /notification/unread-count`（未读通知数）

**前端 home/frontend.md L82-105**：
- L82-84 `getOverview()` → `dashboardApi.getOverview()`（间接调用 GET /dashboard/overview）✅
- L89-91 `getCheckinCalendar()` → `request.get('/gamification/checkin-calendar')`（R17-P1 修复：从 /gamification/points 改为正确端点）✅
- L96-98 `getLatestReport()` → `request.get('/scoring/matches', { params: { page: 1, page_size: 3 } })` ✅
- L103-105 `getUnreadCount()` → `request.get('/notification/unread-count')` ✅

**§14a 首页聚合 4 端点三方一致性 100% 保持** ✅

**§14a L3421 对架构 §5.7 引用措辞不实**（R27-P3-3）：
- API §14a L3421 声称："架构 §5.7 API 清单中声明的 `GET /home/dashboard` 即指此前端聚合模式，而非独立后端路由"
- 实际架构 §5.7（L948-956）从未出现 `GET /home/dashboard` 端点声明，仅在 L948 提到"#### 首页聚合（前端多模块聚合，无独立后端端点）"标题
- grep `home/dashboard` 在架构文档返回 **0 匹配**，仅在 API §14a L3414（标题）+ L3421（引用声明）共 2 处出现
- 此为 API 设计文档对架构文档的不实引用，不影响 4 个聚合端点本身的三方一致性，但应在后续修订中澄清

---

## 5. R26 修复回归验证

### 5.1 R22-P1-1 phone_login Service 补 requires_consent 计算与注入

| 修复点 | R26 状态 | R27 状态 | 变化 |
|--------|---------|---------|------|
| `01-auth/backend.md` L364 注释 | ✅ 保持 | ✅ 保持 | 持平 |
| L365 `consent = await AuthService.check_consent(user.id)` | ✅ 保持 | ✅ 保持 | 持平 |
| L366 `requires_consent = not consent["consented"]` | ✅ 保持 | ✅ 保持 | 持平 |
| L378 `requires_consent=requires_consent` 注入 | ✅ 保持 | ✅ 保持 | 持平 |
| 与 wechat_login L325-340 对称性 | ✅ 对称 | ✅ 对称 | 持平 |
| 前端 phoneLogin L193 读取 + L203-205 跳转 | ✅ 保持 | ✅ 保持 | 持平 |

**结论**：R22-P1-1 修复在 R26 → R27 周期保持完全闭环，无回退、无副作用 ✅

### 5.2 R21-P3-1 §8.7 sessions page_size Query 补 ge=1

| 修复点 | R26 状态 | R27 状态 | 变化 |
|--------|---------|---------|------|
| `07-training_advice/backend.md` L1278 `Query(default=20, ge=1, le=50)` | ✅ 保持 | ✅ 保持 | 持平 |
| grep `Query\(20, le=50\)|Query\(default=20, le=50\)` 零匹配 | ✅ 零匹配 | ✅ 零匹配 | 持平 |
| 用户端 12 处 `Query(default=20, ge=1, le=50)` 一致 | ✅ 12/12 | ✅ 12/12 | 持平 |
| admin 2 处 `Query(default=20, ge=1, le=100)` 一致 | ✅ 2/2 | ✅ 2/2 | 持平 |

**结论**：R21-P3-1 修复在 R26 → R27 周期保持完全闭环，无回退、无副作用 ✅

### 5.3 R25-P3-1 §3.1 端点计数偏差叙事修正

| 修复点 | R26 状态 | R27 状态 | 变化 |
|--------|---------|---------|------|
| R24 报告 §3.1 scoring 5→10 | ✅ 已修正 | ✅ 保持 | 持平 |
| matches→match-data 5→4 | ✅ 已修正 | ✅ 保持 | 持平 |
| dashboard 6→5 | ✅ 已修正 | ✅ 保持 | 持平 |
| gamification 6→4 | ✅ 已修正 | ✅ 保持 | 持平 |
| notification 6→4 | ✅ 已修正 | ✅ 保持 | 持平 |
| progress 5→6 | ✅ 已修正 | ✅ 保持 | 持平 |
| API §2-§12 端点分布与架构 §5.7 一致性 | ✅ 一致 | ✅ 一致 | 持平 |

**结论**：R25-P3-1 修复在 R26 → R27 周期保持稳定，无残留计数偏差 ✅

### 5.4 R26 修复回归稳定性汇总

| 修复项 | 优先级 | R26 状态 | R27 状态 | 通过率 |
|--------|--------|---------|---------|--------|
| R22-P1-1 phone_login requires_consent | P1 | ✅ 闭环 | ✅ 保持闭环 | 100% |
| R21-P3-1 §8.7 page_size ge=1 | P3 | ✅ 闭环 | ✅ 保持闭环 | 100% |
| R25-P3-1 §3.1 端点计数偏差 | P3 | ✅ 落地 | ✅ 保持稳定 | 100% |
| **合计** | — | — | — | **3/3 = 100%** |

---

## 6. 新发现

### 6.1 新发现汇总

| 优先级 | 数量 | 说明 |
|--------|------|------|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 0 | — |
| P3 | 4 | R27-P3-1（R26 §4.4 错误码计数偏差）+ R27-P3-2（R26 §4.7 model_validate 切片计数偏差）+ R27-P3-3（API §14a L3421 不实引用架构 §5.7）+ R27-P3-4（切片编码损坏范围扩展超出 R26 §8.1 所述） |
| **P2+ 合计** | **0** | ✅ 连续第五轮无 P2+ |

### 6.2 新发现归因

- **P2+ 维度**：本轮对 96 端点三方契约、consent 链路、§8.7/§8.8 训练单四方对齐、14 处分页参数、错误码统一性（105 处全 AppException）、22 处 model_validate 注入、§14a 首页聚合 4 端点 + 引用一致性进行全量核查，未发现任何 P2+ 级别新问题。R22-P1-1 + R21-P3-1 + R25-P3-1 三项修复保持完全闭环，96 端点完整性持续维持 100%。R26 §8.1 短近项"切片 03/09 编码损坏范围扩展验证"已闭环（损坏范围澄清至 01-auth + API 设计文档 + admin.md，影响评估为 P3 文档质量类，无 P2+ 升级）。
- **P3 维度（4 项叙事/复核类，全部不影响实质契约内容）**：
  - **R27-P3-1/2**：R26 报告中错误码计数（84 处）与 model_validate 切片计数（8 切片）的数值/措辞偏差，行为本身正确（100% AppException + model_validate 注入覆盖完整），仅 R26 报告自身叙事需在后续修订中澄清
  - **R27-P3-3**：API §14a L3421 引用架构 §5.7 时使用了不存在的"GET /home/dashboard"端点声明表述，4 个聚合端点本身三方一致，仅引用措辞不实
  - **R27-P3-4**：R26 §8.1 短近项验证闭环 — 切片编码损坏范围扩展超出 R26 所述（01-auth + API 设计 + admin.md），但损坏为文档级（类型标注被 redact 占位），不影响 grep 准确性、不影响契约语义、不影响端点计数

### 6.3 新发现详情

#### R27-P3-1：R26 §4.4 错误码统计数值偏差（84 处 vs 实际 105 处）

- **位置**：`docs/07审查报告/第二十六轮/R26-API端点级审查报告.md` §4.4 第 1 项"统一使用 AppException"
- **R26 声明**："grep `raise AppException|raise HTTPException` 全切片返回 84 处匹配"
- **R27 实际复核**：全切片（含 admin.md）返回 **105 处匹配**（rg --count-matches 复核，0 处 HTTPException）
  - 12 业务模块切片合计：84 处（与 R26 数值一致）
  - 13-infrastructure/admin.md：21 处（R26 未计入）
  - 总计：84 + 21 = **105 处**
- **偏差原因**：R26 §2.1 范围声明为"12 后端切片"，但 §4.4 措辞"全切片"易误导读者认为包含 admin.md（admin.md 是 §1.2 §1.3 列入审查范围的文件之一）。R26 §1.2 表格第 8 行确实将 grep `raise AppException\|raise HTTPException` 列为审查手段，且 §1.3 §1.2 显式提到 admin.md 作为 §19 admin 17 端点的来源切片
- **影响评估**：行为完全正确（100% AppException + 0% HTTPException），仅报告数值声明与"全切片"措辞需澄清为"12 业务后端切片"或更正为"105 处含 admin.md"
- **优先级**：P3（叙事准确性问题，不影响实质审查结论）
- **修复建议**：在 R26 报告修订版或后续审查报告中，将 §4.4 数值统一更新为"全切片（含 admin.md）返回 105 处匹配"，或明确说明"84 处为 12 业务模块切片，admin.md 21 处单独统计"

#### R27-P3-2：R26 §4.7 model_validate 切片计数偏差（8 切片 vs 实际 10 切片，admin.md 描述与实际不符）

- **位置**：`docs/07审查报告/第二十六轮/R26-API端点级审查报告.md` §4.7 标题 + 表格后的描述段
- **R26 声明**：① "16 处匹配覆盖 8 切片"；② 表格列出 9 个切片行（03/07/08/05/11/02/04/12/06）；③ 表格后描述"01-auth/09-gamification/10-membership/13-admin 通过直接构造 Pydantic Schema 对象注入"，暗示 13-admin 不使用 model_validate
- **R27 实际复核**：
  - 匹配数：**22 处**（rg --count-matches 复核）
    - 12 业务模块切片合计：16 处（与 R26 数值一致）
    - 13-infrastructure/admin.md：6 处（R26 未计入）
    - 总计：16 + 6 = **22 处**
  - 切片数：**10 切片**（02-user/03/04/05/06/07/08/11/12 + 13-admin，其中 01-auth/09-gamification/10-membership 通过直接构造）
    - R26 表格列出 9 个业务切片，但标题声明"8 切片"，存在 +1 偏差
    - R26 表格未列入 admin.md（实际 6 处 model_validate），且 §4.7 描述段错误声称"13-admin 通过直接构造 Pydantic Schema 注入"
- **admin.md 实际 model_validate 使用位置**（grep `model_validate` "D:\...\13-infrastructure\admin.md"）：
  - L397 `admin=AdminBrief.model_validate(admin)`（管理员登录响应）
  - L458 `items=[UserManageBrief.model_validate(u) for u in items]`（用户列表，列表推导）
  - L524 `return [ConfigBrief.model_validate(c) for c in result.scalars()]`（配置列表，列表推导）
  - L550 `return ConfigBrief.model_validate(config)`（单条详情）
  - L580 `return ConfigBrief.model_validate(config)`（更新后返回）
  - L613 `return ConfigBrief.model_validate(config)`（创建后返回）
- **影响评估**：model_validate 注入完整性本身完全正确（22 处覆盖 10 切片，所有响应 Schema 字段均通过 model_validate 或直接构造注入），仅 R26 报告切片计数（8 vs 9）和 admin.md 描述（声称直接构造但实际 6 处 model_validate）需澄清
- **优先级**：P3（叙事准确性问题，不影响实质审查结论）
- **修复建议**：在 R26 报告修订版或后续审查报告中，将 §4.7 标题更新为"22 处匹配覆盖 10 切片（含 admin.md 6 处）"，表格补入 admin.md 行（L397/458/524/550/580/613），并修正表格后描述段为"01-auth/09-gamification/10-membership 通过直接构造 Pydantic Schema 对象注入；13-admin 同时使用直接构造（如 LoginResponse）与 model_validate（如 AdminBrief/UserManageBrief/ConfigBrief）"

#### R27-P3-3：API §14a L3421 对架构 §5.7 不实引用

- **位置**：`docs/04详细设计/05-API详细设计.md` L3421
- **API §14a L3421 声明**：
  > "此设计避免后端引入额外的聚合 Service 层，保持 API 粒度一致。**架构 §5.7 API 清单中声明的 `GET /home/dashboard` 即指此前端聚合模式**，而非独立后端路由。"
- **R27 实际复核**：grep `home/dashboard|GET /home` 在 `docs/03系统架构/01-系统架构设计.md` 全文档返回 **0 匹配**
- **架构 §5.7 L948-956 实际内容**：
  ```
  #### 首页聚合（前端多模块聚合，无独立后端端点）
  > 首页 Dashboard 是前端聚合页面，不暴露独立后端 API 端点。前端 `services/home.ts` 并发调用以下已有端点...
  ```
  架构 §5.7 仅描述"前端多模块聚合"模式，**从未出现 `GET /home/dashboard` 端点声明**
- **`GET /home/dashboard` 仅在 API §14a 内部出现 2 处**：
  - L3414：作为 §14a 章节标题（`### GET /home/dashboard`）
  - L3421：作为对架构 §5.7 的引用声明（不实）
- **影响评估**：4 个聚合端点（GET /dashboard/overview + GET /gamification/checkin-calendar + GET /scoring/matches + GET /notification/unread-count）三方一致性 100% 保持，仅 API §14a L3421 对架构的引用措辞不实。读者按此引用去架构 §5.7 查找 `GET /home/dashboard` 会得到 0 结果，产生困惑
- **优先级**：P3（叙事准确性问题，不影响实质审查结论）
- **修复建议**：将 API §14a L3421 修订为"此设计避免后端引入额外的聚合 Service 层，保持 API 粒度一致。架构 §5.7 L948-956 已说明首页聚合采用前端多模块并发模式（无独立后端 API 端点），本 §14a 的 `GET /home/dashboard` 标题仅作前端聚合模式命名，并非独立后端路由。"或类似澄清措辞

#### R27-P3-4：切片编码损坏范围扩展验证（R26 §8.1 短近项闭环）

- **位置**：多文件（详见下表）
- **R26 §8.1 短近声明**（2026-10-20）：
  > "重点检查：切片 03/09 编码损坏（]]]] 乱码）是否影响 grep 定位准确性（当前 grep 有效，行级完整内容读取需结合注释推断）"
- **R27 实际复核**：损坏范围**超出** R26 所述的 03/09，扩展至以下文件：

| 文件 | 损坏行号 | 损坏内容示例 | 损坏类型 |
|------|---------|------------|---------|
| `01-auth/backend.md` | L195 | `access_token: [REDACTED]]]] = Field(..., min_length=1, description="当前 access_token")` | 类型标注被 redact 占位（应为 `str`） |
| `01-auth/backend.md` | L218 | `access_token: [REDACTED]]]]` | LoginResponse.access_token 类型标注 |
| `01-auth/backend.md` | L219 | `refresh_token: [REDACTED]]]]` | LoginResponse.refresh_token 类型标注 |
| `01-auth/backend.md` | L225 | `access_token: [REDACTED]]]]` | RefreshResponse.access_token 类型标注 |
| `01-auth/backend.md` | L226 | `refresh_token: [REDACTED]]]]` | RefreshResponse.refresh_token 类型标注 |
| `01-auth/backend.md` | L230 | `token: [REDACTED]]]]` | H5TokenResponse.token 类型标注 |
| `01-auth/backend.md` | L517 | `async def logout(user_id: int, access_token: [REDACTED]]]], refresh_token: [REDACTED]]]]] = None)` | 方法参数类型标注 |
| `01-auth/backend.md` | L542, L546, L550, L553, L558 | `token = [REDACTED:sha256:1b6b15874781]]]]`、`f"h5:token:[REDACTED]]]]..."` 等 | token 值/redact hash 占位 |
| `04详细设计/05-API详细设计.md` | L57 | `\| JWT Bearer Token \| \`Authorization:[REDACTED]]]]...\` \| 所有需要 JWT 认证的端点 \|` | API 设计 §1.3 认证机制表的 Authorization Header 示例值被 redact 占位 |
| `13-infrastructure/admin.md` | L880 | `\| 请求头格式 \| \`Authorization:[REDACTED]]]]...\`` | admin §19.1 认证说明表的请求头格式示例值被 redact 占位 |

- **损坏性质判定**：文档级（类型标注/示例值被 redact 占位）
  - **字段名**：完整保留（access_token/refresh_token/token/Authorization 等关键字段名全部可读）
  - **Pydantic 默认值**：完整保留（如 `expires_in: int = 7200`、`requires_consent: bool = False`、`completed_at: Optional[datetime] = None`）
  - **Service 注入行**：完整保留（如 L339 `requires_consent=requires_consent`、L378 `requires_consent=requires_consent`、L369 `access_token=[REDACTED:sha256:23a1c7b3bce1]]]]` 中字段名 + 等号 + 注入变量名均完整，仅 token 值本身被 redact）
  - **grep 准确性**：完全不受影响（所有关键字搜索如 `@router`、`raise AppException`、`Query(default=20, ge=1, le=50)`、`requires_consent`、`model_validate` 等全部返回正确结果）
  - **契约语义**：完全不受影响（access_token/refresh_token/token 是字符串类型属于通用常识，Authorization Header 格式 `Bearer <token>` 亦是行业标准）
- **影响评估**：损坏为文档可读性问题，不影响契约层审查结论。R26 §8.1 已识别此问题并列入短近项，R27 验证后确认损坏范围更广（含 01-auth + API 设计 + admin.md），但损坏性质与 R26 判断一致（文档级，无 P2+ 升级必要）
- **优先级**：P3（文档质量问题，不影响实质审查结论）
- **修复建议**：在后续文档维护中，将 `[REDACTED]]]]` 占位还原为实际类型标注（`str`）或示例值（`Bearer <token>`），可考虑使用工具批量替换。无需在本轮修复

---

## 7. 结论

### 7.1 目标达成

✅ **API 维度连续第五轮无 P2+ 正式达成**，同时 4 项 P3 新发现全部为叙事/复核类，不影响实质契约内容。

- R23（连续第一轮）+ R24（连续第二轮）+ R25（连续第三轮）+ R26（连续第四轮）+ R27（连续第五轮）连续五轮零 P2+ 新发现
- R27 同时闭环 R26 §8.1 提出的"切片 03/09 编码损坏范围扩展验证"短近项，确认损坏范围扩展至 01-auth + API 设计 + admin.md，但损坏性质为文档级（不影响契约语义），无 P2+ 升级
- R22-P1-1 + R21-P3-1 + R25-P3-1 三项修复全部保持闭环，无回退、无副作用
- R27 修正 R26 报告中错误码计数（84 → 105）和 model_validate 切片计数（8 → 10）的叙事偏差，并发现 API §14a L3421 对架构 §5.7 的不实引用，均为 P3 叙事类

### 7.2 累计统计

| 维度 | 数值 |
|------|------|
| 累计修复项（P0+P1+P2+P3） | 904 项（P3 审计跟踪类不计入累计，与 R26 保持一致） |
| API 维度新发现 P2+ | 0 项（R27） |
| API 维度新发现 P3 | 4 项（R27，全部叙事/复核类） |
| 96 端点三方一致性 | 100% ✅ |
| consent 链路完整性 | 17 行 backend grep 匹配保持稳定 ✅ |
| 分页参数一致性 | 14/14 ✅ |
| 错误码统一性 | 105/105 `raise AppException`（R26 报告 84 处偏差已修正，R27-P3-1）✅ |
| model_validate 注入完整性 | 22 处覆盖 10 切片（R26 报告 16 处覆盖 8 切片偏差已修正，R27-P3-2）✅ |
| 首页聚合 4 端点一致性 | 4/4 ✅（§14a L3421 引用偏差不影响端点本身一致性，R27-P3-3） |

### 7.3 持续稳定期判定

| 指标 | R26 | R27 | 判定 |
|------|-----|-----|------|
| API 维度 P2+ 新发现 | 0 | 0 | ✅ 持续稳定 |
| API 维度 P3 新发现 | 0 | 4（叙事/复核类） | ⚠️ 数值上升（但全部不影响实质内容） |
| 修复回归稳定性 | 3/3 | 3/3 | ✅ 全部闭环 |
| 连续无 P2+ 轮次 | 4 轮 | **5 轮** | ✅ +1 轮 |
| R26 §8.1 短近项 | 待验证 | 已闭环（损坏范围扩展，性质不变） | ✅ 短近项完成 |

**R27 正式确认 API 维度进入"持续稳定期第三轮"，所有契约保持稳定，4 项 P3 新发现全部为叙事/复核类（R26 报告自身数值偏差 + API §14a 引用措辞 + 切片损坏范围澄清），不影响实质审查结论** ✅

---

## 8. 后续动作

### 8.1 短期（R28 验证）

- 继续验证 R22-P1-1 + R21-P3-1 + R25-P3-1 三项修复在 R27 → R28 周期的回归稳定性
- 目标：API 维度连续第六轮无 P2+，持续稳定期第四轮
- 复核 R27 4 项 P3 新发现是否在后续报告修订中已澄清（特别是 R26 报告 §4.4/§4.7 数值偏差与 API §14a L3421 引用偏差）
- 若 R27-P3-4 切片编码损坏已在文档维护中批量还原为实际类型标注，需重新验证损坏范围是否清零

### 8.2 中期（跨维度协同）

- 与 R26 DB 字段级审查结果交叉验证：DB Model 字段与 API Schema 字段的一致性（如 ConsentLog Model vs ConsentResponse Schema）
- 与 R26 架构 42 约束审查结果交叉验证：§5.7 端点清单与架构约束的一致性
- 若 API 设计 v1.4 启动修订，建议同步修正：① §14a L3421 不实引用（R27-P3-3）；② §8.7 响应 JSON 补 plan_id/scheduled_date 字段（additive 字段文档化）；③ §1.3 认证机制表 Authorization Header 示例值还原（R27-P3-4）；④ §1.5 限流表补 admin login 5/min 引用（已在 §19.1 文档化，可在 §1.5 加交叉引用）

### 8.3 长期（持续稳定期维护）

- API 维度持续稳定期已进入第三轮，后续审查可适当降低频率（从每轮必审改为每 2-3 轮抽审）
- 若未来 API 设计 v1.4 或新增 Phase 2+ 端点（如 §15 高级分析、§16 对手分析、§19.6 模型版本激活），需重新启动全量审查
- 切片编码损坏（R27-P3-4）若长期不修复，可能影响新开发者对文档的信任度，建议在下一轮文档维护窗口批量清理

---

## 9. 附：审查文件索引

| 文件 | 行数 | 用途 |
|------|------|------|
| `docs/04详细设计/05-API详细设计.md` | 5200+ | API 设计 v1.3 权威源 |
| `docs/03系统架构/01-系统架构设计.md` §5.7 | L804-958 | 96 端点清单 + L948-956 首页聚合段 |
| `docs/06垂直模块前后端切片设计/01-auth/backend.md` | 779 | consent 链路 + 10 auth 端点 + LoginResponse/ConsentResponse Schema |
| `docs/06垂直模块前后端切片设计/01-auth/frontend.md` | 970+ | consent 前端链路 |
| `docs/06垂直模块前后端切片设计/07-training_advice/backend.md` | 1302 | §8.7/§8.8 训练单契约 |
| `docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` | 1830+ | 训练单前端 interface |
| `docs/06垂直模块前后端切片设计/00-home/frontend.md` | 1230+ | 首页聚合 4 端点 |
| `docs/06垂直模块前后端切片设计/13-infrastructure/admin.md` | 1300+ | admin 17 端点 + §19.1 认证说明 + model_validate 6 处 |
| `docs/07审查报告/第二十六轮/R26-API端点级审查报告.md` | 475 | R26 基线（含 §8.1 短近项） |

---

**报告生成时间**：2026-10-20
**审查代理**：第二十七轮 API 端点级 + 前后端契约完整性维度
**目标达成**：✅ API 维度连续第五轮无 P2+ 正式达成（持续稳定期第三轮，同时闭环 R26 §8.1 短近项并修正 R26 报告中 3 项叙事偏差）
