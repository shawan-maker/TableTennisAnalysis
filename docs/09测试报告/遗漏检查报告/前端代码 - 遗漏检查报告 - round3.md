# 前端代码遗漏检查报告 Round 3

> **复审基线**：HEAD `581e61d`（Round 4 收敛复审后，2026-11-17，连续两轮零 P2+ 已达成、转入常规 CI 门禁态）
> **方法学**：9 代理并行——REG×2（批次H/I/J/R3/R4 修复断言级回归核验，42 项基线）+ XSTK×3（E2E mock 数据契约全量对齐〔helpers 37 块 + 7 spec 内联 12 处，**首次作为独立维度**〕+ 两项 Round 2 范围外遗留正式定性）+ DOC×1（批次H~R4 新增资产设计文档反向同步，12 资产）+ SWEEP×4（13 切片 + 14-tab-pages 5 文档 + 全局基建 9 维度全量遗漏扫描）
> **与 Round 1/2 的区别**：Round 1 单向设计→实现扫描；Round 2 断言级回归 + 反向同步；Round 3 聚焦**测试基建可信度**——「E2E mock 数据与后端契约全量对齐」首次全量执行（Round 2 仅在两处抽点暴露臆造键），系统清点 mock 谱系缺陷
> **纪律**：全程只读（git status 零改动）；P1 发现经主会话独立实证（证据链亲读闭合）；跨代理发现已去重、统一重编号

---

## 一、汇总统计

| 维度 | P0 | P1 | P2 | P3 | 小计 |
|------|----|----|----|----|------|
| 回归核验（REG×2，42 项基线） | 0 | 0 | 0 | 1 | 1 |
| 跨栈契约（XSTK×3，mock 49 块 + 遗留 2 项） | 0 | 1 | 5 | 12 | 18 |
| 反向同步（DOC，12 资产） | 0 | 0 | 0 | 3 | 3 |
| 全量扫描（SWEEP×4，13 切片 383 项 + 全局 9 维度） | 0 | 0 | 1 | 1 | 2 |
| **合计（去重后）** | **0** | **1** | **6** | **17** | **24** |

**回归核验总账（42 项基线）**：批次H 13/13 ✅ 完整在位（含 4 个新测试断言真实性核验——WS pubsub 断言经真实 Redis 订阅实收、非 mock 自证）；批次I/J+R3/R4 29 项中 28 项 ✅、1 项 ⚠️ 部分（R2-P3-14 同谱系第二处漏网，非修复回归，归因审计引用面遗漏）。**零假修复、零修复引入的行为级回归。**

**全量扫描零遗漏面**：13 切片共核对 383 项（SWEEP-1 四切片 134 项 + SWEEP-2 六切片 41 项 + SWEEP-3 四切片 109 项 + 全局 9 维度），**12 切片 + 全局 8/9 维度零新增「设计承诺未实现」遗漏**——设计→实现契约面经三轮修复后高度收敛。

**新暴露谱系**：E2E mock 数据契约全量对齐扫描 49 个 mock 数据块/内联点，**16 项不对齐**（P1×1 + P2×3 + P3×12）——「臆造键/臆造枚举值/缺键」三次复发谱系（technique_stats → comparison → 本轮 loop_success_rate/created_at 等）首次被系统清点。**核心风险形态：E2E 全绿建立在 mock 自设数据上，部分断言覆盖生产不可达分支（「E2E 绿、生产死」）。**

---

## 二、P1 发现（1 项，立即修复）

### R3-P1-1｜E2E_USER.created_at 臆造键——前端 onboarding 门控依赖后端从未下发的字段，生产新用户引导整链死路径

**现象（主会话独立实证）**：生产环境登录后首次进入首页，新用户引导（onboarding）**永不触发**——`pages/home/index.tsx:53-54` `const createdAt = user?.created_at; if (!createdAt) return` 恒短路；而 E2E（analysis-flow.spec:162 引导流、a11y 双态、onboarding.spec）全绿。

**证据链（亲读闭合）**：
- mock 自设：`frontend/e2e/helpers/base-mocks.ts:16` `created_at: iso(0), // 注册即当下 → 新用户（onboarding 判定 <24h）`——注释自认判定语义，经 `/auth/me`（:201）与 phone-login user 块（:196）下发；
- 后端契约无此键：`/auth/me` 返回 6 键 dict（`app/api/v1/auth/router.py:96-105`：id/nickname/avatar_url/has_profile/…，**无 created_at**）；`LoginResponse.user` = UserBrief 4 键（`app/schemas/auth.py:84-92`，**无 created_at**）；`app/schemas/user.py` 全文件（UserProfileResponse 等 13 个 schema）**零 created_at**——profile 契约亦无，前端无任何真实来源；
- 前端消费链：`authStore.ts:69/:95`（login 填充）+ `:127`（/auth/me 填充）→ `home/index.tsx:53`（首页门控）+ `onboarding/index.tsx:45-57`（引导页同源依赖）+ `userStore.ts:58`（类型声明仅前端单侧）。

**为什么六轮门禁 + Round 2 断言级复审仍漏**：E2E mock 喂了后端不会给的字段（与 R2-P1-1「mock 喂 games_won」同构，但方向相反——那次是后端已修 mock 未测真实，这次是**前端门控设计本身就建立在契约外字段上**，mock 让它全绿）。onboarding 触发链无任何单元测试穿透 mock（home/index.tsx 用例断言走 mock user）。

**双轨修复方案**：
- **优先（后端补键，最小改动）**：`/auth/me` dict + `UserBrief` 各补 `created_at: user.created_at`（model 已有列，仅透出一行 + schema 一行），同步 API 设计 §3.2 与 01-auth/backend.md 样例；后端补一条「me 响应含 created_at」契约断言测试（防再次漂移）；mock 保持现值即与契约一致。顺带收口（XSTK-A1 指出）：base-mocks.ts login user 块中 `membership_tier/membership_expire_at` 对 UserBrief 亦为多键，mock 同步对齐。
- 备选（前端改判定信号）：has_profile 承载不了「注册 <24h」语义、profile 无 created_at（已实证），**该轨道不可行**——故本项修复必须动后端，归跨栈批次。

---

## 三、P2 发现（6 项，分批修复）

### E2E mock 契约偏离（4 项——「E2E 绿、生产死/门禁假绿」谱系）

**R3-P2-1｜loop_success_rate 臆造指标键——臆造键谱系第三次复发，a11y trend-detail 断言覆盖生产不可达分支**（XSTK-A1）
mock 四处（`a11y-mocks.ts:273/290/292/331`）+ `a11y.spec.ts:62` `?metric=loop_success_rate` 驱动 trend-detail 页扫描——后端 METRIC_DEFINITIONS 18 键无此键（`progress_service.py:28-47` 全文件零命中），`get_technique_trend_detail:409-410` 对未知 metric 必抛 404/40415。影响：① 生产该 URL 永远走 40415 错误分支，a11y 40 页扫描的 trend-detail 页**断言的是生产不可达的成功分支**（40415 错误分支零 axe 覆盖）；② summary 页 forecast/goal_completion 经 `t('progress.metric.${metric}')` 渲染（summary/index.tsx:182/204），locales 无该键 → E2E 中渲染裸键名，门禁假绿。修复：四处 mock + spec 参数全部改真实键（如 `backhand_ratio`），40415 错误分支另补 a11y 覆盖。

**R3-P2-2｜upload-complete mock 臆造键 status + 缺三真键**（XSTK-A2）
`analysis-flow.spec.ts:43` mock `{file_id, status:'uploaded'}`——后端实为 `{file_id, ready:True, actual_size, duration_sec}`（`video_analysis_service.py:159-164` + `UploadCompleteResponse`，actual_size 为 required）。前端 confirmUpload 当前零消费响应体故无行为破坏，但 mock 固化了错误形状，掩盖未来消费 ready 时的回归风险。修复：mock 改真键集。

**R3-P2-3｜POST /auth/consent mock 响应键偏离**（XSTK-A1）
`base-mocks.ts:203` `{consent_type, policy_version, consented_at}` vs 后端 `{consented, consent_at, policy_version}`（`auth_service.py:484-488`）——多臆造键 consent_type、键名错 consented_at、缺 consented。前端 recordConsent 忽略响应体无即时影响，但 mock 固化错误形状。修复：mock 改 `{consented, consent_at, policy_version}`。

**R3-P2-4｜通知 type 臆造值 analysis_completed**（XSTK-A1）
`base-mocks.ts:141` makeNotifications `type:'analysis_completed'`——后端产生源仅 `analysis_complete`/`analysis_failed`/`training_reminder`（`ai_pipeline/progress.py:257/264` + `notification_service.py:356`）。前端 getNotifIcon 与 i18n types 键集均按 `analysis_complete` 设计 → mock 项恒走默认图标分支，真实图标/i18n 标签分支 E2E 零覆盖。修复：改 `'analysis_complete'`；第二类建议改 `'training_reminder'`（'system' 仅前端 WS 合成兜底，后端不落库）。

### 跨栈数据契约（1 项——Round 2 范围外遗留正式定性）

**R3-P2-5｜dashboard TECHNIQUE_COLORS 跨栈色值漂移**（XSTK-B）
后端 `dashboard_service.py:32-37` 硬编码 FS8-7 调色前旧色板（forehand_drive #E63946 / forehand_loop #F4A261 / serve #2A9D8F，仅 backhand_drive #1D3557 为现值），经 GET /dashboard/technique-stats 下发，前端 TechniqueStats **直接渲染**（`TechniqueStats.tsx:49` conic-gradient `${item.color}` + `:77` 图例圆点 style）——四技术色中 3 项滞后设计系统现值（#C92738/#9C5618/#1F7A6D）。契约文档本身含旧值（API §6.3 样例 L1954 + 06 切片 backend.md:340/139 + frontend.md:1446-1447），属**契约即漂移**非超契约下发。测试无硬编码断言（test_dashboard 仅断言 startswith("#")），改值零破坏。修复（双轨择优后端轨）：色值对齐 FS8-7 现值 + 三处文档同步 + Redis 键 `dashboard:technique:{user_id}` 自然过期（TTL 1h）。

### 后端能力缺位（1 项）

**R3-P2-6｜fetchDeletionStatus 预查询——设计承诺「重启后冷静期横幅可见」后端端点缺位，PIPL 注销撤销权 UI 断链**（SWEEP-3）
设计承诺 `settings.md:15`（注销 → requestDeletion + fetchDeletionStatus）+ `:93`（初始化「fetchDeletionStatus() 查询注销状态（如有冷静期内状态则显示）」）；实现侧 R19-fix 已移除该方法（`settings/index.tsx:5-6` + `userStore.ts:193-196` 注记自证「GET /users/account/deletion-status 端点未在后端 API 契约中定义」），后端 `app/api/v1/` 全域 grep `deletion-status` **零命中**；settings.md 无对应裁决注记。**行为后果：注销冷静期内重启小程序，deletionState（内存态）丢失 → 倒计时横幅与撤销入口不再显示，用户无法经 UI 撤销注销**（PIPL 注销撤回权可达性缺口）。修复双轨：①优先后端补 GET /users/account/deletion-status（02-user 切片，返回 status/requested_at/expires_at）+ 前端恢复挂载预查询；②备选 settings.md 补「据实关闭/R19-fix」P3 文档同步注记收口（接受重启丢横幅的产品裁定）。

---

## 四、P3 发现（17 项）

### E2E mock 键集/枚举偏离（12 项——零消费/零断言依赖，行为无损，mock 保真清点）

| 编号 | 描述 | 证据 |
|------|------|------|
| R3-P3-1 | /users/quota mock 多出 tier 键（后端 5 键无 tier；消费面仅读 remaining/bonus_remaining） | base-mocks.ts:205 vs user_service.py:232-238 |
| R3-P3-2 | checkin-calendar `type:'training'` 不在后端取值空间（checkin_type ∈ manual/analysis/match/record；前端只消费 checked_in） | base-mocks.ts:98 vs gamification_service.py:161/208 |
| R3-P3-3 | training_plan_template code `'quick_improvement'` 非后端种子值（唯一种子 TPL_BACKHAND_IMPROVE；前端仅原样渲染 code 零分支） | base-mocks.ts:180 vs scripts/init_knowledge_base.py:60/98 |
| R3-P3-4 | /auth/consent-status mock 仅 {consented}，后端 3 键（+consent_at/policy_version）；前端只读 consented | base-mocks.ts:202 vs auth_service.py:427-432 |
| R3-P3-5 | phone-login/refresh mock 缺 expires_in（后端 LoginResponse/RefreshResponse 均含；前端仅消费两 token） | base-mocks.ts:193-200 vs schemas/auth.py:100/110 |
| R3-P3-6 | a11y scoring 详情 mock 缺 opponent_playing_style（批次 G 字段；前端 detail 渲染零消费，前向交付） | a11y-mocks.ts:216-240 vs schemas/scoring.py:86 |
| R3-P3-7 | a11y 报告详情 result_data 缺 dashboard 兼容键 technique_distribution/metrics（后端聚合兼容下发；报告页不消费） | a11y-mocks.ts:88-121 vs report_generator.py:155-160 |
| R3-P3-8 | analysis-flow 创建任务 mock `status:'processing'`，后端创建时刻实为 `queued`（processing 由轮询首查返回，语义链本应正确） | analysis-flow.spec.ts:48 vs video_analysis_service.py:198 |
| R3-P3-9 | scoring-flow score_update 广播 mock 缺 games_won_user/opp 两键——**R2-P1-1 即时刷新分支 E2E 未覆盖**（spec 注释自述走 fetchMatch 对账路径） | scoring-flow.spec.ts:113-124 vs scoring_service.py:323-335 |
| R3-P3-10 | scoring-flow undo 广播 mock 缺 current_server 键 | scoring-flow.spec.ts:134-137 vs scoring_service.py:438-447 |
| R3-P3-11 | notification-flow export_completed 推送 mock `data:{}`，后端实为 `{task_id}`；前端 set({exportTask:data}) 空对象弱化空态 | notification-flow.spec.ts:43 vs tasks/user.py:216 |

### 文档承载与口径（6 项）

| 编号 | 描述 | 证据 |
|------|------|------|
| R3-P3-12 | 03 frontend.md 进度页样例第二处 Progress 仍 `percentage`/`strokeWidth={12}` 裸数字/无 aria 族（上传页样例已按 2.x 回写，同文件自相矛盾；实现 processing/index.tsx:83-92 为 percent/"12px"/progressbar+aria 全套）——**R2-P3-14 审计引用面遗漏的漏网同谱系**（批次 J 按引用修复无执行遗漏，基线 a636649 即有双 percentage） | 03 frontend.md:696-700 vs processing/index.tsx:83-92 |
| R3-P3-13 | DB 设计 §4.2 标题「前端枚举同步 (src/constants/enums.ts)」指向不存在文件；实际分散承载于 constants/ 9 个 .ts（labelKey+CSS 变量形态）；样例含 FS8-7 前旧色板 hex + 硬编码中文 label——照文执行会误导（复活旧色板/绕过 i18n/双源冲突）；TASK_STATUS_MAP/TREND_DIRECTION_MAP 前端全域零定义（由 locales+store 内联承载） | 04-数据库详细设计.md:2224-2257 vs constants/scoring.ts:84-96、membership.ts:11-25 |
| R3-P3-14 | API 设计全文档缺「路由 response_model + model_validate 契约形态」全局说明（R2-P1-1 根治形态仅切片承载，切片间「与 scoring 同口径」引用传递而权威源缺位——照 API 文档实现新端点者手拼 dict 无契约层警示） | 04-scoring/backend.md:785-789 vs 05-API详细设计.md §1.1 |
| R3-P3-15 | 「96 端点」计数口径 17 处（6 份文档）未随批次 H 新增 points-history 更新（实际 97）——批次 H 对 DB 表数做了 39→40 显式口径说明而端点数未做同等处理 | 总览:1400/1422/1424、01 路线图:6/22/594/650、04 前端实施计划:5/621、03 执行方案:157/716、02 测试计划:7/52/516/1448/1471 |
| R3-P3-16 | 实施计划/路线图进展基线零回填批次 E~R4：04-前端实施计划最后记录 v1.4（批次 B-D），「余 32 项」活引用已失实（32 项全部修复、Round 1/2 两轮收敛里程碑 + R3/R4 转常规 CI 门禁态均未记）；Jest 基线 285→294 漂移 | 04-前端实施计划.md:577-585、01-实施计划与路线图.md:22 |
| R3-P3-17 | 总览 §3.2 :root 样例块 + §3.4 tabBar 样例（#999999/#E63946）未同步 FS8-7 深化现值（app.scss:17-33 实际 #C92738/#9C5618/#1F7A6D/#5A636B 且多 accent-inverse token；app.config.ts:60-61 已是新值）；app.scss:15 注释声称「设计文档 §3.2 调色板已同步」**失实**（总览侧零注记——R-FS8-10-P3 注记仅落界面设计 §1.2，其「本表」范围不含总览样例块）；后续切片照总览样例取色将回退旧亮色、击穿 axe contrast 门禁 | 总览:124-137/230-231 vs app.scss:15-33、app.config.ts:60-61、界面设计 §1.2 |


---

## 五、回归核验台账（42 项基线：批次 H 13 + 批次 I 9 + 批次 J 18 + R3/R4 复审顺手修 2）

| 批次域 | 项数 | ✅完整 | ⚠️部分 | ❌回归 |
|--------|------|--------|---------|----------|
| 批次 H（P1×1+P2×11+P3×1，R2-P1-1 根治含 response_model 加固） | 13 | 13 | 0 | 0 |
| 批次 I（R2-P3-1~6/22/23/24） | 9 | 9 | 0 | 0 |
| 批次 J（R2-P3-8~21/25~27 + conic 首色补齐 + NotificationBell） | 18 | 17 | 1（R2-P3-14 进度页第二处漏网→R3-P3-12） | 0 |
| R3/R4 复审顺手修（5 处 scss 注释 + comparison mock） | 2 | 2 | 0 | 0 |
| **合计** | **42** | **41** | **1** | **0** |

**断言真实性专项**：批次 H 四新测试均行为级——detail/score 契约穿透断言经真实 HTTP client 解包；WS payload 断言经独立 Redis 客户端订阅 `ws:relay` 实收广播体（含 redis-py 7.1 subscribe-ack 循环消费陷阱处理），非 mock 自证；gamification 落账/分页断言经真实端点响应。批次 I 曾出现的「声称已改实际漏执行」假修复模式本轮未再现（REG-2 逐项 grep 实体内容）。**唯一 ⚠️（R3-P3-12）经 git 归因为原审计引用面遗漏（基线 a636649 即含双 percentage），非修复回归。**

**交互面回归核验**：git diff 7e70863..HEAD 锁定批次 H 修复的 19 关键文件——仅 scoring_service.py 被批次 I 触碰（+3/-1 纯注释），其余 18 文件零后续改动。

---

## 六、零遗漏扫描面与门禁可信度评估

**设计→实现契约面（SWEEP×4）**：13 切片共核对 383 项承诺元素 + 全局 9 维度——**除 R3-P2-6（settings 预查询，后端能力缺位型）与 R3-P3-17（总览样例块，文档同步型）外，全部零新增遗漏**。三轮累计：设计承诺未实现类缺陷已从 Round 1 的主旋律收敛为本轮 2 项（其中 1 项归后端排期）。i18n 全局门禁（zh/en 扁平键双向 diff）维持零缺失。

**E2E mock 契约可信度（XSTK 首次全量清点）**：49 个 mock 数据块/内联点中 33 个完全对齐（含全部核心业务流 mock——payment 订单体逐字、scoring 请求枚举全对、TaskDetail 11 键、ReportDetail result_data 六段、comparison 六维、points-history、badges 种子）；**16 个不对齐**，其中 2 项致「断言假通过/生产死路径」（P1×1 + P2×1 的 loop_success_rate 与 created_at——前者 a11y 扫的是生产不可达分支、后者 mock 让生产死路径全绿）。**谱系判定：technique_stats（Round 2 P3-4）→ comparison（Round 4）→ 本轮 16 项，「mock 臆造键」不是孤立事件而是系统性欠账——此前每轮只修复当轮抽点暴露的个案，本轮首次全量清点后可一次闭合。**

**已知豁免注记自洽**：批次 F 九注记 + 总览 §3.8/§3.9 豁免 + h5-bridge 据实关闭 + 40 页口径 + R2-P2-4/5 数字修正——全部在位未回滚（SWEEP-4 逐项确认）。

---

## 七、分级处置建议

**立即修复（P1，1 项）**：R3-P1-1 created_at——后端 /auth/me + UserBrief 补键（一行透出 + 一行 schema）+ 契约断言测试 + API/01-auth 样例同步。这是 onboarding 整链的生产可达性修复，改动极小但必须跨栈。

**分批修复（P2，6 项）**：
- **mock 契约对齐批（4 项，纯 E2E mock 改动零后端）**：R3-P2-1（loop_success_rate 四处+spec 参数，顺带补 40415 错误分支 a11y 覆盖）+ R3-P2-2/2-3/2-4（upload-complete/consent/通知 type）+ 顺带 R3-P3-1~11 的 mock 项（同谱系一次闭合，约 11 处 mock 行改动）；
- **跨栈批（2 项，需后端）**：R3-P2-5 TECHNIQUE_COLORS 色值对齐（后端 3 行 + 文档 3 处）+ R3-P2-6 deletion-status 端点（后端新增 + 前端恢复预查询；或产品裁定走文档注记收口）。

**P3（17 项）**：文档回写批（R3-P3-12 进度页样例/13 enums.ts 系谱/14 API 形态注记/15 端点口径/16 实施计划回填/17 总览样例块）+ mock 保真补齐（P3-1~11 中未随 P2 批顺带的项）。

**建议修复顺序**：跨栈批（P1+P2-5/6，动后端需联调）→ mock 契约对齐批（纯前端，门禁可信度一次闭合）→ 文档回写批（纯文档）。完成后 Round 4 复审聚焦「mock 契约对齐回归 + 本轮 P2 闭环」。

---

## 八、收敛判定

- **修复质量**：Round 2 三批次 42 项修复 41 项完整在位（97.6%），零假修复、零行为级回归——前两轮修复经受住全量复审检验；
- **契约面**：设计→实现遗漏扫描连续第二轮基本清零（本轮仅 2 项，其中 1 项归后端）；
- **新维度暴露**：E2E mock 契约可信度首次全量清点即暴露 16 项不对齐（含 1 项 P1 生产死路径）——**这不是修复回归，而是测试基建的存量欠账首次被系统性看见**；此前「连续两轮零 P2+」的收敛判定在设计→实现维度成立，在 mock 契约维度不适用（该维度此前未全量扫描）；
- **谱系方法论沉淀**：①「E2E 全绿」的可信度以「mock 数据与后端契约逐字对齐」为前提，mock 臆造键应作为常规审查维度固化（建议进 XSTK 常设检查项）；②前端消费后端字段前必须先核后端契约是否真有该字段（R3-P1-1 的教训：类型声明仅前端单侧即易误信）；
- **下一步**：按 §七 顺序执行修复批次；跨栈批完成后重跑受影响域 pytest + E2E；全部完成后执行 Round 4 轻量复审（聚焦 mock 契约回归 + P2 闭环），若连续两轮零 P2+ 则再次确认常规 CI 门禁态。

---

*报告生成：2026-11-17 ｜ 9 代理并行审查（REG-1/2 + XSTK-A1/A2/B + DOC + SWEEP-1/2/3/4）｜ 全程只读，git status 零改动 ｜ P1 发现经主会话独立实证（progress_service.py:409-410 / auth/router.py:96-105 / schemas/auth.py:84-92 / schemas/user.py 全文件 / home/index.tsx:53-54 / authStore.ts:69-127 亲读确认）*
