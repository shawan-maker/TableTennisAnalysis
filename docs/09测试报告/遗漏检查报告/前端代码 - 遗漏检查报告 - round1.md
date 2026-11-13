# 前端代码 - 遗漏检查报告 - Round 1

> 日期：2026-11-11
> 范围：前端设计文档全量对照实现代码的「设计→实现」遗漏审计——13 份模块切片 frontend.md（00-home ~ 12-notification）+ 14-tab-pages 五份（onboarding/settings/community-tab/match-tab/training-tab）+ 00-垂直切片设计总览通用约定六节 + 02界面设计 v2.0 主文档（§一设计系统/§二信息架构/§四-§七 Phase1 页面/§八对照表/§九用户流程/§十降级策略）
> 基线：frontend/src @ main c3fab13（FS1-FS8 已收官：39/39 页注册、Jest 285、E2E 7 spec、a11y 41 页零违规、双 CI 全绿）
> 增补：R-FE-R2（2026-11-12）——批次 B 余量 + 批次 C 大部 41 项落地（工作区待收尾），核查/门禁/收尾与后续计划见 §十
> 方法：11 个并行比对代理（按模块域分组逐项枚举设计承诺→代码验证，每条双证据：设计文档行号+原文 / 实现行号或 grep 零命中）→ 主会话对全部 P0/P1 断言独立抽查实证（grep 复核）→ 跨代理重复项合并去重
> 口径：① 只报「设计承诺但代码未实现」的遗漏，不报代码多余项；② 设计文档中带「注记」「P3 文档同步」「R-FSx-P3」「据实关闭」等明确「设计 X 实际为 Y」的段落属已记录偏差不计遗漏；③ Phase 3/4 功能（社区 Feed/赛事报名/装备/信用分/教练/球馆/约球/排行）不在范围，但切片文档明确承诺的提前项在范围；④ 级别：P0=核心流程不可用级（页面/主链路缺失）/ P1=重要交互或用户可见功能缺失 / P2=次要功能/边界状态缺失 / P3=样式文案打磨

---

## 一、执行摘要

| 事项 | 数量 | 说明 |
|------|------|------|
| 审计覆盖 | 13 模块切片 + 5 Tab 页 + 总览六节 + 主文档全局 | 11 代理全量比对 |
| 遗漏发现合计 | **85 项** | P0×3 / P1×14 / P2×26 / P3×42 |
| 跨代理重复合并 | 3 处 | h5-bridge 双报、报告→训练建议入口双报、占位文案口径双报 |
| 已注记偏差（不计遗漏） | 60+ 项 | 设计文档 R-FSx-P3 注记体系自洽，实现全部按注记落地（§六汇总） |
| P0/P1 主会话实证 | 全部通过 | grep 复核零入口断言、useMembershipGate/42910/局分字段零消费均成立 |
| 页面注册表完整性 | 39/39 ✓ | 主文档 §2.2/§八 Phase 1 页面无缺页；Tab Bar 5 项配置逐字一致 |
| Service/Store/i18n 契约层 | 高保真 | 13 模块端点/状态机/双语键与设计逐项一致，i18n 零缺键 |
| **R-FE-R1 修复进展** | **12 项已修复落地** | 批次 A 全量 + 批次 B 付费转化组：P0×3 + FE-P1-4/5/7/9/10/11/12/13 + FE-P2-25；验证门禁全绿（tsc 0 错 + eslint 0 error + Jest 285 + E2E 7/7 含 axe 零违规 + weapp 1.23MB/H5 双构建）——明细见 §九修复记录 |
| **R-FE-R2 修复进展** | **41 项已落地（工作区待收尾）** | 批次 B 余量 + 批次 C 大部：P1×4 + P2×20 + P3×17 + 附带观察①②（含 FE-P1-6 跨栈——后端 schema 补字段闭环）；门禁 tsc/eslint 0 error/Jest 285/weapp 1.26MB/H5 构建/后端 25 单测全绿，**E2E 适配未完成**（scoring-flow 断言口径实测必败 + a11y 页清单缺 webview 新页）——明细与收尾/后续计划见 §十；遗漏余 32 项（P1×2 / P2×5 含 1 项部分修复 / P3×25） |

**核心结论**：前端本体实现质量高（页面、Service、Store、i18n、WS 链路、样式 token 均严格落地），**遗漏集中在三类结构性缺口**：

1. **「已实现页面零入口」三连（全部 P0）**——设置页、进度分析三页（训练报告）、徽章墙共 5 个已注册页面在全工程范围内无任何导航入口，用户不可达（各一行 `navigateTo` 即可修复，但当前状态下对应功能整体失效）；
2. **「设计承诺的下游消费端未接线」**——useMembershipGate Hook 完整实现却零页面消费、42910 升级引导无处理、report_id 直达参数成死链路、logout/checkConsentStatus/handleExportCompleted 等 action 有定义无调用方、BadgeUnlockPopup 仅挂 3 页而非设计要求的全局；
3. **「上游 v1.0/v2.0 界面设计承诺未被切片设计继承」**——记分牌局分显示、deuce/换边提示、赛后动作三件套（分享/关联视频/看板入口）、报告页节奏曲线/关键帧/落点切换等，切片文档静默裁剪且无注记。

修复总规模预估：批次 A（P0+接线类 P1，约 11 项，1 天）→ 批次 B（P1 功能类 + P2 核心，约 20 项，3 天）→ 批次 C（P2 余量 + P3，约 54 项，3 天）；其中跨栈契约类 4 项需后端配合、产品裁决类 12 项需「补代码 vs 补文档注记」决策。

---

## 二、P0 明细（3 项 —— 已实现页面全工程零入口）

### FE-P0-1 [设置页] 设置页全工程零入口，页面已实现但不可达 —— ✅ 已修复（R-FE-R1）

| 项 | 内容 |
|----|------|
| 设计要求 | `14-tab-pages/settings.md` L19「确认路由：pages/settings/index（非 TabBar 页，**由个人主页 navigateTo 进入**）」+ L532（§反幻觉约束重申同款）；§2.2 IA 树「设置（通知/隐私/账号/关于）」 |
| 实现现状 | `app.config.ts` L53 已注册；grep `pages/settings` 全 src 仅命中注册行与 settings 自身文件，`pages/user/profile/index.tsx` L271-333（快捷宫格/导出/危险区）无设置入口——**通知开关、数据导出、注销冷静期撤销、关于/版本全部功能失效** |
| 修改方案 | `pages/user/profile/index.tsx` quick-actions 区新增入口 Cell（icon ⚙️，`Taro.navigateTo({ url: '/pages/settings/index' })`）；`locales/zh-CN.ts`/`en-US.ts` 补 `user.settingsEntry`（'设置'/'Settings'） |

### FE-P0-2 [进度分析] 训练报告/进度分析三页零入口（summary/comparison/trend-detail） —— ✅ 已修复（R-FE-R1）

| 项 | 内容 |
|----|------|
| 设计要求 | `02界面设计 v2.0` L203-204 我的 Tab 页面树「[P2] 训练报告（月度趋势）」+ L1401 §八 Phase 对照表「我的：徽章成就 + 训练报告」；`08-progress_analysis/frontend.md` L12 定位行「阅读前端设计 v2.0 §2.2 L1（我的 Tab → 训练报告 / 进度分析入口）」 |
| 实现现状 | 三页已注册（`app.config.ts` L39-41）且本体完整实现；grep `pages/progress/` 全 src 仅 1 命中（summary L85 模块内跳 trend-detail）；user/profile 菜单（edit/big-data/rating-history/membership）与 constants/home.ts QUICK_ROUTES 均无 progress 路由——**月度快照、指标趋势、对比分析整模块不可达** |
| 修改方案 | `pages/user/profile/index.tsx` 功能列表区新增「训练报告」入口 → `/pages/progress/summary/index`；comparison 入口可由 summary 页概览卡或 video-analysis/list 补「与上次对比」；i18n 补 `user.progressEntry` 双语 |

### FE-P0-3 [游戏化] 徽章墙零入口（badges 页） —— ✅ 已修复（R-FE-R1）

| 项 | 内容 |
|----|------|
| 设计要求 | `09-gamification/frontend.md` L915-916「// 首页 → 徽章列表 Taro.navigateTo({ url: '/pages/gamification/badges/index' })」；v2.0 L204「[P2] 徽章/成就」 |
| 实现现状 | badges 页已注册（`app.config.ts` L43）且徽章墙本体完整（earned/locked 分组、进度条、空态）；grep `/pages/gamification/badges` 全 src 零命中——home 六区块（TopBar/概览/宫格/打卡/报告/提醒）与 user/profile 均无徽章入口 |
| 修改方案 | 按设计 §6 首页入口优先：`pages/home/components/CheckinCalendar.tsx` 区块底部补「我的徽章」链接，或 `user/profile` 功能列表并行补入口；i18n 补 `home.myBadges` 双语 |

---

## 三、P1 明细（14 项 —— 重要交互/用户可见功能缺失）

### FE-P1-1 [auth] h5-bridge 页未注册，H5 降级中转链路为死代码

- **设计要求**：`01-auth/frontend.md` L566「'pages/auth/h5-bridge/index', // 新增：H5 降级中转页」+ §10 L992「H5 降级：生成 Token → 跳转 H5 → 换取 JWT」；总览 §2 L49 模块范围含「登录页、H5降级页」；架构设计认证透传流（小程序→一次性 H5 Token→H5 换 JWT）
- **实现现状**：页面 `frontend/src/pages/auth/h5-bridge/index.tsx` 完整实现但 `app.config.ts` 39 页注册表不含它（页面自身 L7-8 注释自证「不注册」）；grep `pages/auth/h5-bridge` 全 src 无导航入口；`generateH5Token/exchangeH5Token`（services/auth.ts L55/L62，后端 h5-token/h5-exchange 端点真实存在）除该页外零调用——未注册页双端均不可路由，整链死代码
- **修改方案**：二选一——(a) Phase 1 需保留 H5 中转能力：`app.config.ts` pages 补 `'pages/auth/h5-bridge/index'`（40 页口径）并在登录页/相关流接入调用；(b) 确认 Phase 2+ 才启用：回写 `01-auth/frontend.md` L566 与总览 §2 L49 加「据实关闭」注记。**推荐 (b)**（Phase 1 无 3D 等重功能跳 H5 场景），属产品裁决类

### FE-P1-2 [auth] consent-status 启动恢复链路未接线（token 恢复场景 PIPL 引导缺失） —— ✅ 已修复（R-FE-R2）

- **设计要求**：`01-auth/frontend.md` L100「用于登录后判断是否需要弹出隐私政策同意页（consented=false 时）」、L273-274、§9.1 L789「或 checkConsentStatus 返回 consented=false（API §2.10）时，跳转至此页」
- **实现现状**：`authStore.ts` L24/L47/L173 已实现 checkConsentStatus，但全 src 零调用方；`app.ts` L20-23 启动恢复仅 fetchMe；grep `needs_consent` 仅 store 内部赋值无导航消费——**冷启动/H5 整页重载的已登录未同意用户永不被引导至同意页**，PIPL 同意触发链仅剩登录响应单一路径
- **修改方案**：`app.ts` useLaunch 的 fetchMe().then 回调追加 `checkConsentStatus()`，检查 `user.needs_consent===true` 时 `Taro.navigateTo({ url: '/pages/auth/consent/index' })`；或挂 home onShow（`pages/home/index.tsx` L50-77 triggerOnboarding 同位点）

### FE-P1-3 [video_analysis] 报告页落点热图「我的/对手落点」切换缺失

- **设计要求**：`03-video_analysis/frontend.md` L873-886（§4.3 heatmap-toggle 双按钮 + setLandingView('mine'/'opponent')）+ L1854-1855 i18n 承诺 myLanding/opponentLanding + L2119 验证清单「落点热图可切换」
- **实现现状**：`pages/video-analysis/report/index.tsx` L144-168 heatmap-section 仅九宫格+hint 无 toggle；grep `myLanding|opponentLanding|landingView|heatmap-toggle` 于 frontend/src 零命中；§5.3 L1462-1481 有完整样式设计未落地
- **修改方案**：report 页恢复 landingView state + 双按钮，locales 补 `analysis.myLanding/opponentLanding` 双语，scss 补 .heatmap-toggle 块；**注意**：设计 ReportDetail 契约（L202-206）仅有单一 nine_grid——对手侧数据需后端补字段，或文档注记降级（跨栈类）

### FE-P1-4 [video_analysis] 42910 免费额度耗尽的会员升级引导未实现 —— ✅ 已修复（R-FE-R1）

- **设计要求**：`05-API详细设计.md` L133「42910 \| 429 \| 免费分析额度耗尽」+ L135「前端按 code 做差异化交互（如 42910 → 引导升级会员弹窗）」（经 03 frontend.md L6 依据链进入前端范围）；`04-前端实施计划.md` L518 遗留未勾选「免费额度用尽→会员引导」
- **实现现状**：`pages/video-analysis/upload/index.tsx` L110-113 createTask 失败仅 `showToast(err?.message)`；grep `42910|statusCode === 429` 全 frontend/src **零命中**（主会话实证）；e2e/payment-flow.spec.ts L41-54 以手动 navigateTo 会员页绕过了该缺口——**免费→付费转化关键触发点缺失**
- **修改方案**：upload 页 confirmAndCreateTask catch 中增加 `err.statusCode===429 \|\| err.code===42910` 分支：弹 NutUI Dialog/Popup 升级引导 → `Taro.navigateTo('/pages/membership/index')`；与 FE-P1-10 useMembershipGate 接线配套（request.ts 已透出 code，改造成本低）

### FE-P1-5 [video_analysis] 「我的分析」历史报告列表页零入口 —— ✅ 已修复（R-FE-R1）

- **设计要求**：`02界面设计 v2.0` L188 我的 Tab 页面树「├── 我的分析（历史报告列表）」（未标 [Pn]=Phase 1 核心承诺）
- **实现现状**：video-analysis/list 页已实现（含下拉刷新/上拉加载），grep `video-analysis/list` 全 src 仅 app.config.ts L20 注册行——**报告列表页用户不可达**，历史报告无从查看
- **修改方案**：`pages/user/profile/index.tsx` 菜单新增「我的分析」项 → `/pages/video-analysis/list/index`（i18n 复用 `analysis.myReports`）；与 FE-P0-2 的 profile 菜单改造合并实施

### FE-P1-6 [scoring] 记分牌不显示局分/局数（bo3/bo5 主流程可用性） —— ✅ 已修复（R-FE-R2）

- **设计要求**：v1.0 L509（P1.7 记分牌头部）「← 退出 局1 11:7 **1:0**」——承诺当前局数+局分；v2.0 L406-408 E3.2 经引用纳入 Phase 1；`04-scoring/frontend.md` L150 MatchDetail 接口已声明 current_game 字段
- **实现现状**：`pages/scoring/scoreboard/index.tsx` L159-173 比分区仅渲染分数无局分/局数；grep `current_game|games_won` 于页面零命中（主会话实证仅 store 接口定义）；后端已存 games_won_user/games_won_opp（app/models/match.py L53-54）但 MatchDetail schema 未暴露——**bo3/bo5 局结束清零后用户无从得知大比分与当前第几局**
- **修改方案**：优先后端补齐 MatchDetail 响应字段（games_won_user/games_won_opp）；备选纯前端从 currentMatch.score_sequence 按 game_number 聚合推导，score-display 上方新增 `.game-info` 行（「第 N 局 · 局分 x:y」）

### FE-P1-7 [video_analysis→training] 报告页→训练建议入口断裂（report_id 死链路） —— ✅ 已修复（R-FE-R1）

- **设计要求**：`07-training_advice/frontend.md` L1737「报告 → 查看训练建议 → `/pages/training/advice/index?report_id={id}`」+ L1928 功能验证 + v1.0 L454「训练建议：点击进入训练建议详情页」+ v2.0 L1422 用户旅程「报告 → 训练建议」（合并 03 代理 VA-F-06 与 07 代理 F1 双报）
- **实现现状**：advice 页 report_id 直达参数与 fetchAdviceByReport（advice/index.tsx L31-33）均已实现，但 grep `advice|训练建议` 于 pages/video-analysis 零命中——**全仓无任何携带 report_id 的调用方**（现有入口：训练 Tab/home AdviceBanner/onboarding 均不带参），分析→建议闭环在设计流程 1/3 中的关键一环断裂
- **修改方案**：`pages/video-analysis/report/index.tsx` 反馈区或底部操作区新增「查看训练建议」Button → `/pages/training/advice/index?report_id=${reportId}`；locales 补 `analysis.viewAdvice` 双语（复用 services/training.ts L135 getAdviceByReport 现成能力）

### FE-P1-8 [gamification] BadgeUnlockPopup 未全局挂载，分析场景徽章弹层静默丢失 —— ✅ 已修复（R-FE-R2）

- **设计要求**：`09-gamification/frontend.md` L1039-1040「监听 WebSocket badge_unlocked 事件。**在首页或全局布局中调用**」+ L1111 验证清单
- **实现现状**：BadgeUnlockPopup 仅挂载 3 页（badges/checkin-calendar/training/plans/detail）；video-analysis/processing、report 页无挂载（grep badge_unlocked 于该域零命中）——**AI 分析完成触发「首分析/分析 N 次」类徽章时用户正位于 processing/report 页，弹层不出现**
- **修改方案**：将 `<BadgeUnlockPopup />` 上提到应用级全局布局，或至少补挂 processing 与 report 两页（useBadgeUnlock 为共享单例监听，多页挂载无重复连接风险，useWebSocket.ts L11-15 已注明）

### FE-P1-9 [gamification] PointsCard 积分卡未嵌入首页（注记③承诺的 FS7 消费未兑现） —— ✅ 已修复（R-FE-R1，落地裁决：嵌入首页）

- **设计要求**：`09-gamification/frontend.md` L225「### 4.1 训练积分卡片（**嵌入首页 Dashboard**）」+ L25 注记③「『嵌入首页 Dashboard』归 FS7 首页升级消费」
- **实现现状**：grep `PointsCard` 全 src 仅 checkin-calendar L100 一处消费；home 六区块无积分卡——注记③后半句（归 FS7）未兑现，训练总积分/本月积分首页不可见
- **修改方案**：`pages/home/index.tsx` 在 CheckinCalendar 上方嵌入 `<PointsCard />`；或在 00-home/frontend.md 补 P3 注记明确放弃首页嵌入、仅保留打卡页（产品裁决类）

### FE-P1-10 [membership] useMembershipGate Hook 零页面消费，升级引导双场景未接线 —— ✅ 已修复（R-FE-R1）

- **设计要求**：`10-membership/frontend.md` L1048 反幻觉约束「权益降级 **必须** 使用 useMembershipGate Hook 统一控制功能入口可见性」+ L1028-1029 功能验证「免费用户额度用完后，进入视频分析时显示升级提示」/「到期会员的功能入口被隐藏（如 3D 教学、进度分析）」+ L934 注记②「升级弹层由消费页面渲染」
- **实现现状**：Hook 本体完整实现（`hooks/useMembershipGate.ts` L46-85），但 grep `useMembershipGate|showUpgradePrompt|upgradeVisible` 全工程仅 hook 自身与契约测试命中——**零页面消费**；upload 页仅静态展示额度数字（文件头注释宣称「耗尽引导购买」但无对应代码）；progress 域三页无会员门控；hook 引用的 `membership.upgradeTitle` 等 i18n key 在 locales 零命中
- **修改方案**：① upload 页 `quotaRemaining===0 && bonusRemaining===0` 时调 showUpgradePrompt() 渲染升级弹层（与 FE-P1-4 429 分支互补）；② progress 域三页按 needsMembership 渲染升级引导（复用 training 域 40300→Empty 引导先例）；③ locales 补 upgradeTitle/upgradeDesc/upgradeConfirm/upgradeCancel 双语

### FE-P1-11 [payment] 我的订单页全工程零 UI 入口 —— ✅ 已修复（R-FE-R1）

- **设计要求**：`02界面设计 v2.0` L1272-1305（P5.5 我的订单，属「我的」域用户页面）+ `11-payment/frontend.md` L5「定位：订单创建页…、订单列表页」
- **实现现状**：orders 页已实现（四态筛选/WS 刷新/Empty），grep `pages/payment/orders` 全工程仅注册行+测试构造命中；唯一到达路径为支付成功通知 action_url 间接跳转——**用户无法主动查看订单**
- **修改方案**：`pages/user/profile/index.tsx` quick-actions 新增订单入口卡 → `/pages/payment/orders/index`，i18n 补 `payment.ordersEntry` 双语；或 membership 页当前状态卡加「查看订单」次级链接

### FE-P1-12 [notification] 通知列表下拉刷新配置缺失（weapp 不触发） —— ✅ 已修复（R-FE-R1）

- **设计要求**：`12-notification/frontend.md` L539-543 下拉刷新样例 + L841/L846 验证清单「下拉刷新动画正常」「下拉刷新重置列表」
- **实现现状**：`pages/notification/list/index.tsx` L66-74 已挂 usePullDownRefresh，但 `index.config.ts` 未设 `enablePullDownRefresh: true`——工程先例（home/templates/dashboard/va-list 四页 config L3）均显式设置，weapp 下无此配置下拉刷新不触发
- **修改方案**：`pages/notification/list/index.config.ts` 补 `enablePullDownRefresh: true`（一行）

### FE-P1-13 [notification] ScrollView 固定高度结构致页面级 onReachBottom 分页失效 —— ✅ 已修复（R-FE-R1，方案 b）

- **设计要求**：`12-notification/frontend.md` L545-548 上拉加载样例（useReachBottom）+ L845「通知列表分页加载（20条/页）」；设计样例为页面级滚动
- **实现现状**：list.scss L8-11 `.notification-scroll { flex:1; height: calc(100vh - 88px) }` + index.tsx L138 `<ScrollView scrollY>` 包裹全列表——滚动发生在 ScrollView 内部，页面级 onReachBottom（L77-80）永不触发，**第 2 页起无法加载，列表仅剩首屏 20 条**
- **修改方案**：(a) 移除固定高度改页面级滚动，useReachBottom 自然生效；或 (b) 保留 ScrollView 改由 `onScrollToLower` 驱动 `fetchNotifications(false, filter)`——推荐 (b)（改动小，不破坏骨架布局）

### FE-P1-14 [match_data] 局分语义（my_score=局分）在录入页无体现与前端校验，bo3+ 提交必被后端 422 拒收 —— ✅ 已修复（R-FE-R2）

- **设计要求**：`05-match_data/backend.md` L692-703「_validate_score_by_format … FORMAT_WIN_MAP … bo5→3:x」（局分语义后端强校验）；frontend.md L1326 承诺「前端拦截 + 后端校验」双层
- **实现现状**：`detailed-entry/index.tsx` L59-64 样例照抄设计把 my_score 当逐分累计（每条明细+1）；FORMAT_WIN_MAP 前端零命中；quick/detailed 两页仅有非空+相等校验——**详细录入打 bo5 场次逐分累计后 my_score≈40+，提交必 422**；快捷录入填 11:7 选 bo5 同样 422，前端仅 Toast err.message 无引导
- **修改方案**：① `constants/matchData.ts` 新增前端 FORMAT_WIN_MAP（bo1:1/bo3:2/bo5:3/bo7:4），两页提交前按 format 预校验；② 详细录入明确「逐分明细 vs 局分」换算口径（明细按局分组或提交前确认局分），至少 bo3+ 拦截逐分累计式总分；③ 新增 `matchData.invalidScoreByFormat` 双语提示键

---

## 四、P2 明细（26 项）

### 导航与链路类

| 编号 | 模块 | 设计要求（位置+摘要） | 实现现状（证据） | 修改方案 |
|------|------|----------------------|------------------|----------|
| FE-P2-1 ✅已修复（R-FE-R2） | auth | frontend.md L12 登录入口链「我的 Tab → 个人主页 → 登录引导」（v2.0 §2.2） | grep `pages/auth/login` 仅注册行+request.ts 401 兜底两处；user/profile 无 isAuthenticated 分支——未登录用户只能经 401 reLaunch 到达 | profile 页补未登录分支渲染「点击登录」引导卡 → login 页 |
| FE-P2-2 ✅已修复（R-FE-R2） | auth | frontend.md §10 L991「登出：清除本地 Token → 跳转登录页」 | authStore.logout（L130-136）已实现，全 src 无调用方；settings 页 grep logout 零命中——登出整链无 UI 载体 | settings 页「账号」分组补退出登录 Cell：logout() → `Taro.reLaunch('/pages/auth/login/index')`；与 FE-P0-1 入口修复联动 |
| FE-P2-3 ✅已修复（R-FE-R2） | user | frontend.md L353-359 handleExportCompleted + 「profile 页通过 useWebSocket.onMessage 监听 export_completed 后调用」（WS 即时刷新替代轮询） | userStore L95/L251-253 action 已实现零调用点；useWebSocket.ts L122-125 将 export_completed 作为内置事件消化（return true 不分发）——页面即使挂监听也收不到；轮询上限 5×3s 后导出状态永久停留「处理中」 | useWebSocket 内置分支追加 `useUserStore.getState().handleExportCompleted(msg.data)`（延迟 import 防循环依赖），同步更新 12-notification L219 内置五事件注记（跨模块） |
| FE-P2-4 ✅已修复（R-FE-R2） | home | v2.0 §三 L227-229 概览第三卡「训练频次：每周4次」（frontend.md §4.3 L440-445 改为连续打卡天数但**无注记**） | OverviewCards.tsx L55-60 仅渲染 streak_days；training_frequency_per_week 字段仅 dashboard 页消费 | 二选一：首页第三卡补 `每周 {n} 次`（数据源已备）；或 frontend.md §4.3 补「训练频次并入看板」注记（产品裁决） |
| FE-P2-5 | video_analysis | v2.0 L117/L304 T2.3「节奏曲线」为报告页核心区块承诺；frontend.md L5 定位行亦列「节奏曲线」 | report/index.tsx L113-307 无节奏图区块；grep `节奏|rhythm` 零命中；store result_data 契约无节奏字段 | 跨栈类：后端 result_data 补节奏序列（如 rally_tempo）后前端补 SVG 折线区块；或设计文档注记降级 |
| FE-P2-6 | video_analysis | v2.0 L304 T2.3「视频回放带关键帧标记」 | report 页 L246-256 纯 `<Video controls>` 无 marker/seek；grep keyframe 零命中（result_data.score_analysis.key_points 时间戳字段已在契约） | 若 key_points 含时间戳，video-section 下渲染 marker 列表点击 seek；数据不可得则注记降级 |
| FE-P2-7 ✅已修复（R-FE-R2） | scoring | v1.0 L538「10:10 后显示『需领先2分』提示」 | grep `领先|deuce` 零命中；is_key_point（store L66/后端 ScoreResponse 均已返回）零 UI 消费 | scoreboard 页 score-display 下方条件提示条（双分 ≥ target-1 时渲染），i18n 补 scoring.deuceHint |
| FE-P2-8 ✅已修复（R-FE-R2） | scoring | v1.0 L540「换边：每局结束后自动提示换边」；backend.md L1642「should_change_sides **必须**返回（R-2 修复）」 | grep `should_change_sides` 零命中；doScore（scoringStore L155-167）丢弃 score 响应体 | doScore 捕获响应的 should_change_sides/is_key_point 写入 state；scoreboard 据此弹 Toast/横幅（i18n 补 scoring.changeSides） |
| FE-P2-9 ✅已修复（R-FE-R2） | scoring | v1.0 L580「📤 分享比赛结果」；v2.0 E3.3 经引用纳入 | statistics 页 grep `share|分享` 零命中（分享能力仅 VA 模块有） | statistics 页结果卡下补分享按钮：Phase 1 按 report 页先例 Taro.setClipboardData 复制比分文本，i18n 补 scoring.shareResult |
| FE-P2-10 ✅已修复（R-FE-R2） | scoring | v1.0 L573-574「📹 关联视频分析」；v2.0 L1430 流程 2 尾段「统计 → 数据看板 → 关联视频」 | statistics 页 grep `video|关联视频` 零命中 | statistics 页补「关联视频分析」入口卡 → `/pages/video-analysis/upload/index`（携带 matchId 供后续关联） |
| FE-P2-11 ✅已修复（R-FE-R2） | scoring | v1.0 L577「📊 查看数据看板」；v2.0 L1430「统计 → 数据看板」 | statistics 页 grep `dashboard|看板` 零命中——流程 2 在统计页中断 | statistics 页底部补跳看板按钮（dashboard 页已注册），i18n 补 scoring.viewDashboard |
| FE-P2-12 ✅已修复（R-FE-R2） | scoring | v1.0 L557-558 结果展示「(11-7, 8-11, 11-9, 11-6)」逐局比分明细 | statistics L44 仅渲染 final_score（bo 多局模式为局分 "3:1"）；逐局比分未下发未聚合 | 前端从 score_sequence 按 game_number 分组、各局末记录推算比分，result-score 下补逐局行；或后端补 games_detail（跨栈备选） |
| FE-P2-13 ✅已修复（R-FE-R2） | scoring | v1.0 L478 赛制卡片承诺 21 分制选项；后端契约 target_score 1-21 | setup L40 `target_score: 11` 硬编码，无 11/21 切换 UI | setup 页补「每局目标分」Picker（11/21），i18n 补 scoring.targetScore |
| FE-P2-14 | scoring | v1.0 L487 对手信息「打法：[快攻][弧圈][削球][全面]」 | setup 创建参数无打法字段；后端 MatchCreateRequest 亦无——跨栈缺口 | 后端 MatchCreateRequest/Match 补 opponent_playing_style，前端 setup 补四选项 Picker；或 v2.0 E3.1 增放弃注记（跨栈+裁决） |
| FE-P2-15 ✅已修复（R-FE-R2） | match_data | frontend.md L1322「快速录入 ↔ 详细录入可切换」（双向） | 仅 quick→detailed 单向（quick L166-171）；detailed 页无反向切换入口（grep switchToQuick 零命中） | detailed 页提交按钮后补 entry-switch redirectTo quick 页；i18n 补 matchData.switchToQuick（设计样例与验证清单自身矛盾，同步修订文档口径） |
| FE-P2-16 ✅已修复（R-FE-R2） | dashboard | frontend.md L1460「网络错误显示错误提示」 | dashboardStore 五个 fetch 均 `catch { console.error }` 静默；失败区块永久空白无提示无重试 | store 增加各区块 error 字段，页面渲染错误提示+重试按钮；i18n 补 dashboard.loadFailed |
| FE-P2-17 | training | v1.0 P1.11 L729-733 方案卡「频率：每周3次 / 预期周期：4-6周 / [生成训练单]」 | templates/detail L110-164 仅 goal/sessions/exercises/metrics 四区；grep 生成训练单/printable 零命中 | 字段级：后端 template_data 补 frequency/cycle 则前端补渲染；交互级：progress/summary 方案状态跳转文案升级为「查看训练单」承接意图 + 切片文档注记裁剪（裁决） |
| FE-P2-18 ✅已修复（R-FE-R2） | progress | frontend.md L214-215 等 6 action catch 承诺 `Taro.showToast(...)` | progressStore 六个 action 全部仅 console.error；fetchSummary 失败 → summary=null → 页面静默渲染空态「暂无进度数据」**误导为无数据** | 六个 catch 恢复 showToast（common.operationFailed 键已备）；或页面级 error state |
| FE-P2-19 ✅已修复（R-FE-R2） | progress | R-FS4-P3 契约② max_length_a/b、max_a/b 已声明；comparison 页 L8 注释自证「此处一并展示」 | comparison L137-171 仅渲染 avg 两列，max 字段全文件零引用——注释与代码矛盾，最长回合/最高球速数据丢失 | comparison 维度 3/4 补「最长回合/最高球速」行（复用 comparison-row）；或修正 L8 注释 |
| FE-P2-20 ✅已修复（R-FE-R2） | membership/payment | v2.0 P5.5 订单卡「[管理续费]」/「[查看报告]」+ CurrentMembershipData.auto_renew | orders 页 paid 订单仅静态文案；grep auto_renew 仅类型定义，全工程零 UI 展示（会员页状态卡也未显示） | 短期：membership current-card 展示自动续费状态、orders 卡补标签；中期：管理续费/查看报告依赖后端补 auto-renew 端点与订单关联字段（跨栈） |
| FE-P2-21 ✅已修复（R-FE-R2） | settings | settings.md L524-525「用户协议、隐私政策子页面通过 H5 webview 承载：pages/settings/webview?url=xxx」 | grep `settings/webview` 零命中；两处 onClick 仅 showToast（文档实际打不开） | 新增 pages/settings/webview/index.tsx（web-view 承载 url query）+ 注册 app.config；两处 onClick 改 navigateTo |
| FE-P2-22 ✅已修复（R-FE-R2） | community | community-tab.md L36-57/L76-87/L141-188「即将上线」占位页：预告卡四项（积分排行/球友圈/挑战赛/精彩分享）+ preview-grid 样式 | pages/community 仅 `<PagePlaceholder />` 通用占位；grep preview* 键零命中；目录无 index.scss——设计整段未落地 | 按设计 §2/§3 实现专属占位页（预告卡四项+样式）；或扩展 PagePlaceholder 支持 children |
| FE-P2-23 ✅已修复（R-FE-R2） | community | community-tab.md L227-263 zh/en community 段 12 keys | locales 双文件尾部均无 community 段（测试计划 FE-I18N-06 将其列为必需 18 段之一） | 随 FE-P2-22 落地补 12 keys 双语 |
| FE-P2-24 ✅已修复（R-FE-R2） | payment | frontend.md L194 注记①「定价运行时从 GET /membership/tiers 取」+ L1024「金额正确计算」 | create 页 L80-87 `?? 0` 兜底：fetchTiers 失败时三周期金额全显示 ¥0.00，支付按钮无金额校验可点击，提交必 422 | create 页补 tiers 加载失败分支（Empty+重试）+ pay-button `disabled={... \|\| !amountCents}`；membershipStore 增 tiersError |
| FE-P2-25 ✅已修复（R-FE-R1，随 FE-P1-10 ②） | membership | frontend.md L1028-1029「到期会员的功能入口被隐藏」到期场景 | progress 域到期会员无任何门控表现（useMembershipGate 零消费的到期侧面，随 FE-P1-10 修复） | 随 FE-P1-10 ②实施 |
| FE-P2-26 ◐部分修复（R-FE-R2） | 全局 | 总览 §3.8 L449-460「所有 View onClick 应添加 role="button"+aria-label+accessible」「WS 推送通知 aria-live="polite"」 | grep `role="button"`/`accessible={` 全 src 0 命中（约 105 处 onClick）；NotificationBell L59 无可访问名、角标无 aria-live | NotificationBell 补三属性+角标 aria-live；按 §3.8 清单分页补齐 View onClick；补齐后将 .eslintrc.js 三条 jsx-a11y warn 升 error（联动 FE-P3-40） |

---

## 五、P3 明细（42 项）

### 样式规范类（color-mix 回退 / token 漂移 / 双源）

| 编号 | 位置 | 问题 | 修改方案 |
|------|------|------|----------|
| FE-P3-1 | onboarding/profile/index.scss L46 + ActionGuideCard.scss L16 | 设计承诺 color-mix(...10%, transparent)，实现硬编码 rgba(230,57,70,0.1) | 恢复 color-mix 或新增 --color-primary-10 token |
| FE-P3-2 | user/profile L172-173/L278 + edit L45（4 处） | 设计 L1365/L1471/L1668 承诺 color-mix 8%/20%/5%/10%，实现硬编码 rgba(230,57,70,…)——违反反幻觉约束 L1952 | 4 处替换回 color-mix |
| FE-P3-3 | settings/index.scss L40 | 设计 L413 color-mix 6%，实现 rgba(230,57,70,0.06) 硬编码（同场景 list.scss L37 保留了 color-mix，非全局降级） | 替换回 color-mix |
| FE-P3-4 ✅已修复（R-FE-R2） | dashboard/OverviewCards.scss L25-29 | 设计 L993-996 四卡数值各配主色（winrate-primary/analysis-secondary/training-accent/streak-success），实现统一 primary | 补四条分色规则 |
| FE-P3-5 ✅已修复（R-FE-R2） | dashboard/OverviewCards.scss L46-54 | 设计 L1002-1005 advice-banner 橙色左边框+accent 底；实现无 border-left、底色 secondary 10% 无注记 | 补 border-left: 3px solid var(--color-accent)；底色恢复或补注记 |
| FE-P3-6 ✅已修复（R-FE-R2） | dashboard/MatchRecordList.scss | 设计 L1220-1223 承诺胜场绿/负场红 4px 左边框；实现无任何 border-left（L90-92 空规则注释「由结果标签承担」无设计豁免注记） | 补 .record-card 左边框透明基态 + card-win/card-lose 两色规则 |
| FE-P3-7 ✅已修复（R-FE-R2） | dashboard/LandingHeatmap.scss L41-51 | 设计 L1138/1144 cell-value/cell-label text-shadow 提升彩底可读性；实现无；cell-label 用错 token（--color-text-inverse vs 设计的 inverse-secondary） | 补 text-shadow + 改 token |
| FE-P3-8 ✅已修复（R-FE-R2） | dashboard/LandingHeatmap.tsx L82-92 | 设计 L799-809 分布图例三项各带彩色圆点（.dist-dot 8px）；实现仅三 Text 无圆点 | 每项前补 .dist-dot（三色 var()），scss 补样式 |
| FE-P3-9 ✅已修复（R-FE-R2） | dashboard/LandingHeatmap.tsx L94-102 | 设计 L1149-1171 承诺 stat-row 两端对齐统计行+distribution-row 分隔线；实现改单行拼接 | 拆两个 stat-row + 补 border-top |
| FE-P3-10 ✅已修复（R-FE-R2） | dashboard/LandingHeatmap.tsx L51 | `PRIMARY_RGB='230,57,70'` 为 FS8-7 调色前旧值（app.scss --color-primary 已深化为 #C92738）——JS 硬编码色与全站主色漂移 | 改 '201,39,56' 并全局 grep 排查同类硬编码 RGB |
| FE-P3-11 ✅已修复（R-FE-R2） | progress/trend-detail/index.scss L109-110 | 设计 L1096-1098 目标参考线 var(--color-warning) 橙；实现改 --color-secondary 深蓝（与数据线同色系语义混淆）；L102 左轴线丢失 | 改回 --color-warning；补 border-left |
| FE-P3-12 ✅已修复（R-FE-R2） | membership/index.tsx L75 + membership.scss L5-8 | 设计 L257/L456-457 ScrollView 双层（membership-page 包 membership-scroll）；实现单层——嵌套选择器无匹配节点，height/padding 永不生效，**全页贴边无间距** | scss 将 height/padding 平铺进 .membership-page（视觉影响全页，优先修复） |
| FE-P3-13 ✅已修复（R-FE-R2） | scoring/statistics L54-59 | v1.0 L563-565 得分分布承诺计数+占比双展示；实现仅计数 | 以 total_points 为分母渲染 "8 (27%)" 形式 |
| FE-P3-14 | match-data/record-detail L34-40 | 设计验证清单 L1317 要求 48px 大比分；实现 32px（设计 §5.4 样例自身写 32px——文档内部矛盾） | 二选一：改 48px 或修订清单为 32px 并注明（裁决） |
| FE-P3-15 ✅已修复（R-FE-R2） | notification/list.scss L31-85 | 设计 L839「已读通知灰色样式区分」；实现仅定义 .unread 高亮，已读无视觉差异（设计样例同缺——清单与样例矛盾） | 补已读态灰化规则 |

### 常量文件组织类（设计承诺独立常量文件，实现内联）

| 编号 | 范围 | 问题 | 修改方案 |
|------|------|------|----------|
| FE-P3-16 ✅已修复（R-FE-R2） | dashboard | 设计 L1408-1431 承诺 constants/dashboard.ts（PERIOD/RESULT_FILTER/GRID_CELL_LABELS）；三组常量内联在三个组件 | 新建 constants/dashboard.ts 收敛（labelKey 走 i18n），组件改 import |
| FE-P3-17 ✅已修复（R-FE-R2） | training | 设计 §7 L1870-1904 承诺 constants/training.ts 四映射（含 ADJUSTMENT_ACTION_MAP）；实现内联且 ADJUSTMENT_ACTION_MAP 全仓零命中 | 新建 constants/training.ts；调整历史渲染时补第四映射 |
| FE-P3-18 | training-tab | 设计 §7 L289-298 承诺 constants/trainingTab.ts；实现内联 TRAINING_ENTRIES（有同构注释） | 可选：建文件或维持现状（文件组织级偏差） |
| FE-P3-19 | gamification | 设计 §7 L925-945 承诺 constants/gamification.ts（POINTS_SOURCE_MAP/BADGE_CATEGORY_MAP）；零命中，且对应 10 个 i18n 键成为死键 | 补建常量文件供后续消费；或删 10 个死键收敛体积 |

### 交互提示与状态反馈类

| 编号 | 位置 | 问题 | 修改方案 |
|------|------|------|----------|
| FE-P3-20 | home/CheckinCalendar.tsx L42-47 | v2.0 L240-245 周视图承诺「本周已训练5次」计数；实现仅连续打卡 | 补周计数（buildWeekView days 直接可算），i18n 补 key |
| FE-P3-21 | home/AdviceBanner.tsx L47-61 | v2.0 L256-258「[查看训练方案 →]」可见 CTA；实现整卡可点但无 CTA 文本 | banner 底部补 CTA 文本，i18n 补 key |
| FE-P3-22 | home/TopBar.scss L2-7 | 设计 §5 L783-789 承诺 64px 固定高；实现自然撑至 72px | 补 height 或按实际值回写设计样例 |
| FE-P3-23 | 全部 39 页 index.config.ts | frontend.md §8「所有文本有翻译无硬编码」；navigationBarTitleText 硬编码中文且无 setNavigationBarTitle 动态机制（全项目性） | 全项目豁免注记（weapp config 静态限制）或逐页 useDidShow 动态标题（建议豁免+文档注记） |
| FE-P3-24 | home/homeStore | 设计 §3 承诺 adviceLoading 独立字段；实现复用 overviewLoading（行为等价仅字段名不同） | 可不改；逐字对齐则补字段 |
| FE-P3-25 | user/profile L336-346 | 设计 L703 confirmBtnProps={{loading}} 注销弹窗提交中防重；实现无 loading 属性可反复点确认 | Dialog 补 confirmBtnProps（若 NutUI 版本支持）或 handleConfirmDeletion 入口卫语句拦截 |
| FE-P3-26 | video-analysis/report L192 | 设计 §7 technique 文案「正手攻球/反手拨球」；实现顶层 technique 枚举「正手快攻/反手快攻…」（与记分标签共用），报告页图例口径偏差（en 与设计一致仅 zh 偏差） | 报告页专用 analysis.technique.* 子键；或共用枚举+设计注记 |
| FE-P3-27 | scoring/setup | v1.0 L481-482「你的信息：姓名/积分」本人档案展示；实现无 | setup 顶部补只读 Cell（读 userStore 档案） |
| FE-P3-28 ✅已修复（R-FE-R2） | scoring/statistics L79-94 | v1.0 L568-569 关键分聚合「9:9后得分 3/5（60%）」；实现仅逐条列表无聚合行 | key_points 聚合占比一行（纯前端计算） |
| FE-P3-29 | gamification/checkin-calendar L69-73 | 设计 L1108 打卡成功提示承诺「积分+连续天数」；实现仅积分+奖励（current_streak 字段已备未消费） | toast 追加 currentStreak 拼接（键 zh L637 已备） |
| FE-P3-30 | progress/summary L171 | forecast 区 `<Cell title={metric}>` 直显后端英文键名（backhand_ratio），未走 progress.metric.* 映射（同页 L80 趋势行走 mt.metric_name 中文名——页内口径不一；设计样例自身缺陷被复制） | 改 `t(\`progress.metric.${metric}\`)`，forecast 键集超出则补 locales |
| FE-P3-31 | training/advice L90-92 | 设计 §8 L1930+反幻觉 L1955「首次分析显示标签**和提示**」；i18n 键 firstAnalysisHint 已备（zh L577/en L575）但组件零使用——死键 | 首次分析分支补提示行 |
| FE-P3-32 | training/plans/detail | 设计 §2/§3 承诺 getPlanAdjustments 调整历史链路；action 已实现（store L201-209）但页面零渲染——数据拉取后无 UI 出口 | plans/detail 头部补「调整历史」区块消费 store.adjustments（用 FE-P3-17 映射渲染） |
| FE-P3-33 | settings L163-177 | settings.md L620 反幻觉约束「冷静期必须显示倒计时」；实现仅图标+撤销按钮无倒计时（profile 页 L41-61 已有秒级倒计时可复用） | 抽公共 DeletionCoolingBanner 组件两页共用 |
| FE-P3-34 | membership L166-248 | 设计 §9 L1022 空态引导；实现 fetchTiers 失败/空列表仅 section-title+空表，无 Empty 引导 | 补 Empty+重试，i18n 补 key |
| FE-P3-35 | membership | 设计 §7 L813-823 MEMBERSHIP_STATUS_MAP 六状态含 color 字段；实现颜色走 scss statusClass 类——map.color 为死数据双源 | statusClass 改读 map.color 内联，删 scss 状态类；或修订注记「颜色走 scss」 |
| FE-P3-36 ✅已修复（R-FE-R2） | notification/settings | 设计 L1394+§2.2 社区占位承诺「即将上线」；PagePlaceholder 渲染 common.pageInDevelopment「页面建设中」——文案口径不一致（合并 12 代理 N12 与全局代理 F-06 双报） | PagePlaceholder 增加 comingSoon 语义 key 或 community 页改用专属键（随 FE-P2-22 落地） |
| FE-P3-37 ✅已修复（R-FE-R2） | community | 设计 L64-70/L120-124 承诺 CDN 占位图 200×200（community-coming-soon.png）；实现 🏓 emoji 替代 | 随 FE-P2-22 落地 Image（资源上传 CDN 后引用） |
| FE-P3-38 ✅已修复（R-FE-R2） | community | 设计 L89-92/L241/L261 footer「关注公众号第一时间获取上线通知」；实现无 footer | 随 FE-P2-22 落地 footer-section |

### 全局基建规范类（历史推迟项到期未兑现）

| 编号 | 来源 | 问题 | 修改方案 |
|------|------|------|----------|
| FE-P3-39 | 总览 §3.9 L485-494 | 图片 lazyLoad + 自定义 ESLint 检测规则零实现（R19-P3-2 推迟项，FS1-FS8 已收尾承诺到期） | 列表场景 Image 补 lazyLoad；.eslintrc.js 补检测规则；或总览注记豁免（数据量级小） |
| FE-P3-40 | 总览 §3.9 L491-492 | VirtualList 虚拟滚动 + debounce/throttle 零命中（同推迟项） | 长列表接入 VirtualList 或注记豁免；输入类补 debounce(300ms) |
| FE-P3-41 | 总览 §3.8 L479 vs .eslintrc.js L82-84 | 设计承诺 jsx-a11y 三交互规则「CI 阻塞」，实现显式降级 warn（降级理由仅存代码注释，设计文档未注记） | 与 FE-P2-26 联动：补齐键盘事件后升 error；或总览回注「交互规则 warn，可达性由 axe+真机覆盖」 |
| FE-P3-42 | v2.0 §十 L1497 vs upload 页 | 主文档承诺 weapp 视频 10MB 受限「引导到 App」；实现全端 500MB（切片契约口径，主文档未同步） | 文档侧优先：§十该行回注切片契约（500MB STS 直传+Phase 1 无 App 可引导）；或 upload 页按 TARO_ENV 补提示分支 |

**附带观察（不计入遗漏）**：① settings/index.tsx L193/L211 appVersion Cell 在「账号信息」「关于」两节重复出现，建议顺手去重；② user/profile/index.scss L23-27 残留 `.header-bell` 死样式（FS7 铃铛迁回首页后未清理）；③ 「训练建议为会员守卫页」的既有认知与代码不符——advice 两端点实为免费（router.py L21-39 仅 get_current_user），守卫页实为模板列表/详情与方案详情 6 个会员端点，不构成遗漏仅校正背景。

> R-FE-R2 处理注记（2026-11-12）：①②已随批次 B 处理（appVersion 重复 Cell 去重 / `.header-bell` 死样式删除）；③背景校正已知悉，无代码动作。

---

## 六、已注记偏差汇总（设计文档自洽性证明，不计遗漏）

审计中确认设计文档 R-FSx-P3 注记体系覆盖良好，以下主要注记均已核实按注记落地（代表性清单）：

- **契约同步类**：01-auth 极性统一（requires_consent→needs_consent）；03-VA task_id int/card_image_url/STS 字段；04-scoring 端点 7→10、WS subscribe 协议；05-match_data PATCH updateRecord 复用口径；06-dashboard is_readonly/固定索引取数；07-training created_at/plan_id 双参；08-progress landing 键名/40415；10-membership price_*_cents/quota_config；12-notification content nullable/markRead 范围
- **WS 协议类**：子协议认证 jwt.{token}、用户频道连接级订阅、内置五事件连接级单次执行（connected/notification/sync/export_completed/membership_downgrade）、pong token_expired 刷新重建、指数退避 [1,2,4,8,16]s×5
- **组件 API 适配类**：NutUI 2.7.14 真实 API 对齐（Empty title、Skeleton rows、Cell extra/description/clickable、Progress percent、Tag background、Swipe rightAction、TextArea）；PullRefresh→页面级下拉；FlatList→ScrollView
- **路由类**：training/plans/detail 静态路径+query 传参（weapp 不支持动态段）；matchTab 三注记（/scoring/current 不存在改 listMatches 首条/进行中徽标恒真/Skeleton rows）
- **架构分工类**：分享页 /share/{token} 归后端 SSR；conftest 契约对齐；tabBar 5 标题硬编码中文（总览 §3.4 契约+weapp 原生限制）
- **调色类**：FS8-7 WCAG AA 深化（#E63946→#C92738 等）注记于主文档 §1.2 L40 + app.scss——但**总览 §3.2/§3.4 契约文本未回写**（见 FE-P3-42 同批处理，架构文档分包注记缺失移交架构审计）
- **页面注册口径**：consent 页注册注记（总览 §3.4 L197）；39 页 vs h5-bridge 的口径冲突归入 FE-P1-1

---

## 七、修改方案汇总与排期建议

### 批次 A：P0 + 一行级接线类 P1（预计 1 天，13 项）—— ✅ 已完成（R-FE-R1）

| 项 | 改动量 | 验证 |
|----|--------|------|
| FE-P0-1/2/3 + FE-P1-5/11 | profile 页菜单/快捷区集中补 5 个入口（设置/训练报告/我的分析/我的订单 + 徽章入口） | tsc + Jest + 手动导航验证 |
| FE-P1-12 | 一行 config | weapp 真机/模拟器下拉验证 |
| FE-P1-7 | report 页一个按钮+一 key | E2E payment/analysis 回归 |
| FE-P1-9 | home 嵌 PointsCard | E2E smoke + a11y 回归 |
| FE-P1-13 | ScrollView onScrollToLower 改造 | 通知列表分页手测 |

### 批次 B：P1 功能类 + P2 核心链路（预计 3 天）

> **状态（2026-11-12 R-FE-R2）**：账号链路组（FE-P1-2 + FE-P2-1/2/3）✅ / 记分可用性组（FE-P1-6 + FE-P2-7/8）✅（FE-P1-6 走「后端 schema 补字段」优先方案闭环）/ 录入正确性组（FE-P1-14 + FE-P2-15）✅ / 其余 P1 中 FE-P1-8 ✅（FE-P1-3 跨栈未动归批次 G）/ P2 链路组（FE-P2-9/10/11/16/18/21/22/23/24）✅——本批次除 FE-P1-3 外全部落地（工作区待收尾，见 §10.2/10.3）。

- **付费转化链路组**：FE-P1-4 + FE-P1-10 + FE-P2-25（42910 分支 + useMembershipGate 接线 + progress 域门控 + upgrade 弹层 i18n）——✅ 已完成（R-FE-R1，优先级最高的商业化闭环先行）；余组未动
- **账号链路组**：FE-P1-2 + FE-P2-1/2/3（consent 启动接线 + 登录入口 + logout + export_completed WS）
- **记分可用性组**：FE-P1-6 + FE-P2-7/8（局分显示 + deuce/换边提示——后端字段零成本消费优先做 FE-P2-8 的 should_change_sides/is_key_point 消费）
- **录入正确性组**：FE-P1-14 + FE-P2-15（FORMAT_WIN_MAP 前端校验 + 双向切换）
- **其余 P1**：FE-P1-3（落点切换，若后端补对手数据）/ FE-P1-8（BadgeUnlockPopup 补挂两页）
- **P2 链路**：FE-P2-9/10/11（统计页三入口按钮）、FE-P2-16/18（错误态）、FE-P2-21/22/23（webview + community 占位 + i18n 12 键）

### 批次 C：P2 余量 + P3（预计 3 天）

> **状态（2026-11-12 R-FE-R2 / 批次F 补充 2026-11-13）**：P2 剩余中 FE-P2-12/13/19/20（短期方案）✅，FE-P2-17 ✅（批次 F 裁剪注记），余 FE-P2-14（跨栈）/FE-P2-20 中期跨栈部分；P3 样式规范组 FE-P3-4~13/15/1/2/3 ✅（color-mix 三项批次 E 修复）、常量组织组 FE-P3-16/17/18/19 ✅、提示状态组 FE-P3-20/21/25/27/28/29/30/31/32/33/34/36/37/38 ✅（批次 E 补齐 11 项）、全局规范组 FE-P3-23/26/35/39/40/41/42 ✅（批次 F：23/39/40/41/42 注记、26/35 代码修复）——余项仅归 §10.5 批次 G。

- P2 剩余（scoring 赛制明细 FE-P2-12/13/14、P2-17/19/20 等）
- P3 按三组并行：样式规范组（FE-P3-1~15：color-mix 回退 7 处 + dashboard 视觉 8 项 + 其他）、常量组织组（FE-P3-16~19）、提示状态组（FE-P3-20~38）
- 全局规范组（FE-P3-39~42 + FE-P2-26）：lazyLoad/VirtualList/ARIA 三属性按「实现 or 注记豁免」逐项裁决

### 跨栈契约类（需后端配合，4 项）

| 项 | 后端缺口 | 前端就绪度 |
|----|----------|-----------|
| FE-P1-6 | MatchDetail 补 games_won_user/opp（字段已在 model L53-54，仅 schema 未暴露——改造成本极低） | score_sequence 聚合兜底方案可先行 |
| FE-P1-3 | ReportDetail 补对手侧 nine_grid | toggle UI 设计已备（§5.3 样式完整） |
| FE-P2-5 | result_data 补节奏序列 | 区块样式可参考 conic 先例 |
| FE-P2-14/20 | opponent_playing_style 字段 / auto-renew 端点 / 订单关联 report | 均可先文档注记降级 |

> **状态（2026-11-12 R-FE-R2）**：FE-P1-6 已闭环（后端 `app/schemas/scoring.py` MatchDetail 补 games_won_user/games_won_opp + 前端 store/scoreboard/E2E mock 全链路，scoring 单测 25 passed）——表中余 3 项 + FE-P2-20 中期部分，归 §10.5 批次 G。

### 产品裁决类（「补代码 vs 补文档注记」二选一，12 项）

FE-P1-1（h5-bridge 注册或据实关闭）、~~FE-P1-9（PointsCard 首页嵌入或注记）~~（✅ R-FE-R1 已按「嵌入首页」落地）、FE-P2-4（训练频次卡口径）、FE-P2-13（21 分制）、FE-P2-14（对手打法）、FE-P2-17（生成训练单）、FE-P3-14（48px 大比分）、FE-P3-23（导航标题硬编码豁免）、FE-P3-26（technique 文案口径）、FE-P3-35（状态色双源）、FE-P3-39/40（性能规范豁免）、FE-P3-42（10MB 降级口径）——裁决后统一以「R-FE-P3 注记」格式回写设计文档。

> **状态（2026-11-12 R-FE-R2 / 批次F 补充 2026-11-13）**：FE-P2-4（训练频次）已按补代码落地、FE-P2-13（21 分制）已实现、FE-P1-9 前轮已裁决、FE-P1-1/FE-P2-17/FE-P3-14/18/23/26/35/39/40/41/42 全部 ✅（批次 F 2026-11-13 用户拍板：9 注记 + 2 代码修复，见 §10.5 批次 F 表）——裁决类清零，余项仅批次 G 跨栈 4 项。

### 修复验证纪律（每批次完成后全量执行）

Jest 30 套件 285 用例（--maxWorkers=2）+ tsc 零错误 + eslint 零 error + E2E 7 spec（含 a11y 41 页门禁）+ weapp/H5 双端构建 + bundle ≤8MB 门控；i18n 改动过 i18nKeys.test；入口/导航类改动须同步 app.config 与 constants 路由表核对；修复后本报告标记「已修复」并按惯例提交 push 确认双 CI 绿。

---

## 八、结论

本轮为前端阶段首次全量「设计→实现」遗漏审计（对照后端 15 轮同类审计惯例记 Round 1）。**85 项遗漏中无一项涉及页面本体缺失或主流程崩溃**——39 页、13 模块 Service/Store、i18n、WS 链路的切片内契约全部严格落地，已注记偏差（60+ 项）实现一致率高。风险集中在：

1. **5 个已实现页面的用户可达性为零（P0×3）**——一行入口代码级修复，但不修则功能整体失效，属最高优先；
2. **商业化闭环断点**——42910 升级引导 + useMembershipGate 零消费 + 订单页零入口三处叠加，免费→付费转化触发链当前仅剩 E2E 测试里的手动导航；
3. **上游主设计文档（v1.0/v2.0）承诺与切片设计的继承断层**——约 30 项（scoring 系列为主）因切片文档未继承且未注记 descoped 而悬空，需按「补代码 or 补注记」逐项裁决收敛设计-实现契约面。

建议排期：批次 A 立即执行（1 天修复 13 项核心接线）→ 批次 B/C 随后 6 天收敛全部 P1/P2 与可实施 P3 → 跨栈 4 项与后端排期协调 → 裁决 12 项回写设计文档注记后，前端设计-实现契约面可宣告收敛。

---

## 九、R-FE-R1 修复记录（2026-11-11，批次 A 全量 + 批次 B 付费转化组，12 项）

> 修复范围（用户裁决）：批次 A 全量（P0×3 + FE-P1-5/7/9/11/12/13）+ 批次 B 付费转化组（FE-P1-4/10 + FE-P2-25）。完成后全量遗漏余 **73 项**（P1×6 / P2×25 / P3×42，其中含产品裁决 11 项、跨栈 4 项待协调）。

### 9.1 实现要点

| 项 | 落地点 |
|----|--------|
| FE-P0-1/2 + FE-P1-5/11 | `user/profile` 新增 feature-section 功能入口区：我的分析（→video-analysis/list）/ 训练报告（→progress/summary）/ 我的订单（→payment/orders）/ 我的徽章（→gamification/badges）/ 设置（→settings）——5 页全部恢复可达 |
| FE-P0-3 + FE-P1-9 注记兑现 | home `CheckinCalendar` 底部补「我的徽章」badges-link（设计 §6 首页入口优先位）；`PointsCard` 嵌入 home QuickGrid 与打卡日历之间（注记③「归 FS7」承诺兑现） |
| FE-P1-12/13 | notification list `index.config.ts` 补 `enablePullDownRefresh: true`；分页改 ScrollView `onScrollToLower` 驱动（方案 b，保留骨架布局），移除页面级 useReachBottom |
| FE-P1-7 | report 页 bottom-actions 新增「查看训练建议」→ `training/advice?report_id=${reportId}`，fetchAdviceByReport 死链路激活 |
| FE-P1-4 + FE-P1-10①② + FE-P2-25 | upload 页接线 `useMembershipGate('analysis_reports')`：①进入页免费态额度耗尽主动弹升级层（autoPromptDismissed 粘性守卫防重弹，「暂不升级」后本次停留不自动再弹）；②`confirmAndCreateTask` catch `statusCode===429 \|\| code===42910` 分支 Toast 透传后端消息 + 弹升级层；progress 三页（summary/comparison/trend-detail）按 canAccess 渲染 Empty 升级引导（到期会员功能入口隐藏场景随接）；弹层文案 `membership.upgrade*` 四键双语补齐 |
| i18n | 新增 10 键双语（user.settingsEntry/progressEntry、analysis.viewAdvice、progress.membershipRequired/upgradeMembership、membership.upgradeTitle/upgradeDesc/upgradeConfirm/upgradeCancel、payment.ordersEntry）+ home.myBadges |

### 9.2 E2E 口径变更注记

- **payment-flow.spec 改走真实弹层转化路径**（取代原手动 `gotoPage` 旁路）：自动弹层（额度耗尽）→ 暂不升级 → 429 再弹 → 立即升级 → membership——九步付费链路与产品行为一致；
- **弹层「不弹」断言由 `toHaveCount(0)` 改 `toBeHidden()`**：NutUI 2.7.14 Popup `unmountOnExit: destroyOnClose`（默认 false）——弹层关闭后内容以隐藏 DOM 留存；且 `gotoPage` 为同文档 hash 导航（Taro 页栈复用原 upload 实例），隐藏弹层 DOM 恒在，count 断言结构性不可能通过。`toBeHidden` 保留守卫语义（误弹为可见态时仍失败）；
- **analysis-flow/smoke 断言收紧 exact**：新增可见文本（「查看训练建议」「训练积分/总积分」）与既有子串断言在 Taro H5 页栈 DOM 驻留下构成 strict mode violation，跨页存活断言一律 `exact: true`；
- **a11y-mocks** /membership/current 覆盖 member/active（防 progress 三页被门控替换为 Empty 引导，保真页面内容扫描；会员页扫描态随之变 member 属可接受取舍）。

### 9.3 验证门禁（全绿）

tsc 零错误 ✓ | eslint 0 error / 93 warning（≤200 预算，较基线 +2 为 badges-link View onClick 同既有模式，ARIA 治理归批次 C FE-P2-26）✓ | Jest 30 套件 285 用例全过 ✓ | E2E 7 spec 全绿（a11y 41 页 critical/serious 零违规 + E2E-01/02/03/04/05 + smoke）✓ | weapp 构建 1.23MB + H5 构建 ✓（bundle ≤8MB 门控通过）

> 注：E2E 排障过程实证两条基建陷阱——① src 改动后须重建 H5 产物再跑 E2E（spec 改动即时生效但 src 走 dist 缓存，首修复轮因未重建导致旧弹层循环复现）；② Playwright 需 Node 20+，本机默认 node 18.14 不可用，以 MobileClaw 内置 Node v22.14 驱动。




---

## 十、R-FE-R2 修复记录（2026-11-12，批次 B 余量 + 批次 C 大部，41 项）

> 修复范围：批次 B 余量（账号链路/记分可用性/录入正确性/错误态四组 + P2 链路类）+ 批次 C 大部（看板视觉 + 常量收敛 + 提示状态类）。合计 P1×4 + P2×20 + P3×17 + 附带观察①②，含跨栈 1 项（FE-P1-6 后端 schema 补字段）。**批次 D 收尾已完成（2026-11-12）：E2E 两处适配（含 technique 分布口径回退）+ 2 处 axe serious contrast 回归修复 + P3-17 常量接线迁移 + ADJUSTMENT_ACTION_MAP 双语 4 键补齐（批次 D 增量，见 §10.4 末注）——E2E 7 spec 全绿（2.1m）/ 后端 integration+e2e 84 passed / Jest 285 全绿 / tsc 零错误；6 处设计文档 P3 注记与 39→40 页口径同步完成（04-前端实施计划 v1.4 changelog 在案）。批次 E 已完成（2026-11-12，15 项代码修复 + 1 项文档修订 FE-P3-22 按实现回写设计样例，见 §10.5 批次 E 表）——门禁全绿（E2E 7 spec 2.4m / Jest 285 / tsc 零错 / weapp 1.27MB）。批次 F 已完成（2026-11-13 用户拍板，9 项文档注记 + 2 项代码修复 FE-P3-26/35，见 §10.5 批次 F 表）——门禁全绿（E2E 7 spec 2.6m / Jest 285 / tsc 零错 / weapp 1.27MB）。** 修复后全量遗漏余 4 项（批次 G 跨栈类 + FE-P2-20 中期部分，均依赖后端排期）。

### 10.1 实现要点

| 项 | 落地点 |
|----|--------|
| FE-P1-2 | app.ts 启动恢复链：fetchMe → checkConsentStatus → `needs_consent` 时 navigateTo consent 页（token 恢复场景 PIPL 引导接通，修复前 checkConsentStatus 全 src 零调用） |
| FE-P1-6（跨栈） | 后端 `app/schemas/scoring.py` MatchDetail 补 `games_won_user/games_won_opp`（model 字段暴露，默认 0）；前端 scoringStore 契约扩展 + scoreboard 新增 game-info 行（「第 N 局 · 局分 x:y」，aria-live）；E2E scoring-mocks 同步补字段 |
| FE-P1-8 | BadgeUnlockPopup 补挂 processing 与 report 两页（useBadgeUnlock 共享单例监听，多页挂载无重复连接风险） |
| FE-P1-14 | 新建 `constants/matchData.ts`：FORMAT_WIN_MAP + validateScoreByFormat 逐字镜像后端 `_validate_score_by_format`；quick/detailed 两页提交前预校验 + invalidScoreByFormat 双语提示 |
| FE-P2-1 | profile 页未登录分支渲染登录引导卡（avatar+文案+点击 login），fetchProfile 前置鉴权守卫 |
| FE-P2-2 | settings「账号」组补退出登录 Cell：showModal 确认 → logout() → reLaunch 登录页 |
| FE-P2-3 | useWebSocket export_completed 内置分支追加 `useUserStore.getState().handleExportCompleted(msg.data)`（WS 即时刷新导出状态；userStore 仅依赖 services/user，静态 import 无循环依赖）；文件头五事件注记同步 |
| FE-P2-4 | home 第三卡 card-sub 恢复训练频次（training_frequency_per_week 字段复用 dashboard OverviewData），streak 主数值保留——按补代码落地，待 00-home frontend.md §4.3 同步注记 |
| FE-P2-7 | scoreboard deuce 提示条：双分均 ≥ target-1 时渲染「需领先 2 分」（aria-live） |
| FE-P2-8 | scoringStore.doScore 捕获 ScoreResponse 写入 lastScoreFlags（should_change_sides/is_key_point），scoreboard useEffect 消费弹 Toast（换边优先于关键分）+ consumeScoreFlags 清空防重复 |
| FE-P2-9/10/11 | statistics 页 post-match-actions 三按钮：分享（剪贴板复制比分文本，report 页先例）/ 关联视频分析（携 matchId 跳 upload）/ 去数据看板 |
| FE-P2-12 | statistics 逐局比分明细：score_sequence 按 game_number 分组计数还原（多局模式显示「(11-7, 8-11, …)」） |
| FE-P2-13 | setup 页「每局目标分」Picker（TARGET_SCORE_OPTIONS 11/21 分制，替代硬编码 11） |
| FE-P2-15 | detailed 页补 entry-switch 反向切换（redirectTo quick 页），双向切换达成——05-match_data 设计样例与验证清单自相矛盾处待文档侧修订 |
| FE-P2-16 | dashboardStore 五 fetch 补区块 error 标志；页面 SectionError 错误卡 + 重试按钮（错误态替代渲染） |
| FE-P2-18 | progressStore 五 action catch 恢复 Taro.showToast（common.operationFailed；trendDetail 保留页面级 error state 分工不变） |
| FE-P2-19 | comparison 维度 3/4 补最长回合/最高球速行（max_length_a/b、max_a/b 契约字段消费，R-FS4-P3 契约②兑现） |
| FE-P2-20（短期） | membership current-card 补自动续费状态行（auto_renew 字段消费）；orders paid 卡补「管理续费」入口（短期跳会员中心；auto-renew 操作端点与订单关联 report 属中期跨栈） |
| FE-P2-21 | 新增 pages/settings/webview/index.tsx（weapp WebView 承载 / H5 降级提示分支）+ app.config 注册（40 页口径）+ constants/settings.ts URL 常量（example.com 占位，部署期配置入业务域名白名单）；settings 两处 onClick 改 openWebview；附带观察① appVersion 重复 Cell 去重 |
| FE-P2-22/23 | community 专属预告占位页：占位图区 + 四功能预告卡（preview-grid）+ footer（PagePlaceholder 组件删除——全工程最后引用者）；community 域 12 key 双语 |
| FE-P2-24 | membershipStore 补 tiersError；payment/create 失败空态（Empty）+ pay-button `disabled={… || !amountCents}` + handlePay 兜底校验（防 0 元订单提交） |
| FE-P2-26（部分） | NotificationBell 补 ariaRole="button"/ariaLabel（Taro A11yProps camelCase 形态，含未读数插值；accessible 无对应 prop 平台差异由 ariaRole 承载）；a11y-h5 运行时补丁为 .notif-bell-badge 注入 aria-live=polite（WS 推送播报）；约 105 处 View onClick 全量补齐与 eslint 三规则升 error 归后续批次 |
| FE-P3-4/5/6/7/8/9/10 | dashboard 视觉七项：四卡分色 / advice-banner 橙色左边框+accent 底 / 胜负 4px 左边框 / cell text-shadow + inverse-secondary token / 图例三色圆点 dist-dot / stat-row 两端对齐+分隔线 / PRIMARY_RGB 更新为深化后主色 #C92738（'201, 39, 56'） |
| FE-P3-11 | trend-detail 目标参考线改 --color-warning 橙（语义混淆修复）+ 补左轴线 |
| FE-P3-12 | membership.scss 单层结构平铺 height/padding（嵌套选择器无匹配节点致全页贴边的修复） |
| FE-P3-13 | 得分分布计数+占比（「10 (91%)」形式，total_points 为分母） |
| FE-P3-15 | notification 已读态灰化（标题降色降权重 + 正文/时间降不透明度） |
| FE-P3-16/17 | 新建 constants/dashboard.ts（PERIOD/RESULT_FILTER/GRID_CELL_LABELS 三组收敛，labelKey 走 i18n）+ constants/training.ts（SEVERITY/TREND/SUGGESTION_TYPE/ADJUSTMENT_ACTION 四映射；ADJUSTMENT_ACTION_MAP 设计样例复用 TREND 键系语义不通，按动作语义新增 training.action* 专用键——R-FE-R2 偏差注记） |
| FE-P3-28 | 关键分聚合行（「关键分我方拿下 n/m（p%）」纯前端计算） |
| FE-P3-36/37/38 | 随 FE-P2-22：community 专属 comingSoon 键（文案口径统一）/ CDN 占位图 Image（占位 URL 真机验收时替换）/ footer 公众号提示 |
| 附带观察② | user/profile/index.scss `.header-bell` 死样式删除（FS7 铃铛迁首页后残留） |
| i18n | 新增 52 行/侧双语：auth 4（loginPrompt 等）+ home 2 + settings 1 + scoring 13 + matchData 2 + dashboard 1 + progress 2 + membership 3 + payment 2 + notification 1 + community 12 +（common.retry 为既有键复用） |

### 10.2 验证门禁（E2E 除外全绿）

| 门禁 | 结果 |
|------|------|
| tsc --noEmit | 零错误 ✅ |
| eslint src | 0 error / 100 warning（≤200 预算，较基线 93 +7：新增 View onClick 同既有 a11y 模式）✅ |
| Jest --maxWorkers=2 | 30 套件 285 用例全绿 ✅（含 i18nKeys 双语零缺键守卫） |
| weapp 构建 + bundle 门禁 | 构建成功（webview 新页入产物），bundle 1.26 MB ≤ 8 MB ✅ |
| H5 生产构建 | webpack 5.91.0 compiled（2 warnings 无 error）✅ |
| 后端 tests/unit/test_scoring.py | 25 passed ✅（schemas/scoring.py +2 默认值字段无回归） |
| **E2E** | **7 spec 全绿 ✅（批次 D 适配后实跑 2.1m；a11y 40 页 + onboarding 双态 42 扫描 critical/serious 零违规）** |

> 注：Jest 用例数与基线持平（285），本轮修复未新增单测（新增逻辑以既有契约测试域外的 UI 行为主）；断言级覆盖由 E2E 回归承担（收尾项）。

### 10.3 E2E 两处适配缺口（批次 D 已收尾 ✅）

1. **scoring-flow.spec L155-160 断言口径冲突（实测必败）**：FE-P3-13 修复后 `.dist-count` 文本由「10」变为「10 (91%)」，而断言为 `filter({ hasText: /^10$/ })` 全等正则——2026-11-12 以 MobileClaw 内置 Node v22.14 实跑 E2E-02，失败于 L155（element(s) not found）。适配方案：三处（L155/157/160）正则同步改为 `/^10 \(\d+%\)$/` 形式；**✅ 收尾实况：L155/157 已改 `/^10 \(\d+%\)$/`；L160 实测回退 `/^9$/`——FE-P3-13 百分比仅落得分分布（distribution-list），技术动作分解（technique-list）保持纯计数，首轮回归实测该处带占比断言必败**；
2. **a11y.spec PAGES 清单缺新页**：39 页硬编码清单未纳入 `/pages/settings/webview/index`（不影响现有断言但门禁覆盖缺口）——补入后扫描计数（PAGES.length + 2）与测试名「39 页」同步更新为 40 页口径（含 onboarding 双态共 42 扫描）。**✅ 收尾实况：webview 页已补入（携 url/title query 参数，H5 走降级提示分支），4 处「39 页」口径同步为 40 页，40 页实扫零违规**。

### 10.4 收尾清单（批次 D 全部完成 ✅ 2026-11-12）

1. **E2E 两处适配**（§10.3）→ 全量 E2E 7 spec 回归 **✅ 7 passed（2.1m）**（a11y 门禁与 payment-flow 真实弹层转化路径均含——membership 页 auto-renew 行、statistics 页 post-match-actions 按钮区扫描零新增违规）；
2. **后端 integration 契约测试复跑** **✅ tests/integration + tests/e2e 共 84 passed（3:46）**（MatchDetail 响应新增 2 可选字段无严格 schema 断言受影响；unit 25 已过）；
3. **设计文档同步注记 6 处 ✅**：① 02-user frontend.md X-24 注记改内置分支直调口径（profile 页免挂监听 + 轮询降级兜底说明）；② 12-notification 内置五事件注记补 handleExportCompleted 消费；③ 07-training §7 ADJUSTMENT_ACTION_MAP 偏差注记（TREND 键系复制痕迹 → training.action* 专用平铺键，以实现为准）；④ 05-match_data 双向切换修订（detailed 样例补 entry-switch 反向切换块 + L1322 验证清单自相矛盾处注记）；⑤ 00-home frontend.md §4.3 第三卡样例镜像实现（card-sub 恢复训练频次，撤销「无注记」悬空态）；⑥ 04-前端实施计划 §10 changelog v1.4 条目；另 app.config 40 页口径同步——总览 §3.4 注册表补 webview 行 + 04 头部/定位行/指标行 + 01-路线图 §11 索引行与进度基线活引用；
4. **提交 push → 双 CI 绿确认**（Frontend CI 六步 + 后端 Pipeline；本机 47+8 文件待提交）。

> **批次 D 收尾增量修复（3 项，随收尾实测发现）**：
> ① **axe serious color-contrast ×2**——community preview-card 整卡 `opacity: 0.7` 与 notification 已读态 desc/time `opacity: 0.7` 均将 text-secondary 压至 3.2:1 触发 40 页全量首扫（PAGES 补页后社区页/通知页进入扫描暴露，FE-P3-15 引入回归）；修复：前者改 dashed 边框表达预告态、后者已读区分仅保留标题降色降字重（正文/时间不加 opacity）；
> ② **ADJUSTMENT_ACTION_MAP 双语 4 键缺失**（FE-P3-16 隐性缺口）——constants/training.ts 引用的 `training.actionMaintain/actionAdjust/actionEscalate/actionNewGoal` 双语均未落（组件零消费故运行时未暴露、双语对照守卫不拦引用侧），补齐 zh/en 共 8 行；
> ③ **FE-P3-17 接线补全**——DiagnosisSection/SuggestionSection 两组件内联映射副本迁移至 `import { … } from '@/constants/training'`（severity 消费改 StyleMeta.color/labelKey 结构，SEVERITY_MAP 设计样例纯色值已升级为同构 StyleMeta），孤儿常量文件消除。

### 10.5 后续修复计划（余 32 项分层排期）

**批次 D：R-FE-R2 收尾**（§10.4）——**✅ 已完成（2026-11-12）**，累计 53 项完整修复闭环（R1×12 + R2×41）+ 收尾增量 3 项（contrast×2 / 双语 4 键 / P3-17 接线补全，见 §10.4 末注）。

**批次 E：纯实现类 16 项——✅ 已完成（2026-11-12，15 项代码修复 + 1 项文档修订）**

| 项 | 落地方式 |
|----|------|
| FE-P3-1/2/3 ✅ | color-mix 恢复 7 处：`rgba(230,57,70, N%)` 全部改 `color-mix(in srgb, var(--color-primary) N%, transparent)`（6%/8%/20%/5%/10%×3），同时修正「格式漂移 + 旧主色 #E63946 残留」双重问题；写后全局 rg 验证 rgba(230 残留 = 0 |
| FE-P3-19 ✅ | 新建 constants/gamification.ts（POINTS_SOURCE_MAP 6 源 + BADGE_CATEGORY_MAP 4 类，逐字镜像设计 §7 L925-945）——选「补建激活」而非删键：10 个 i18n 死键转常量引用；**消费端接线依赖后端 schema 暴露 category/source（模型层已有、BadgeResponse 未暴露），归批次 G 跨栈协调** |
| FE-P3-20 ✅ | CheckinCalendar week-row 下方补周计数行（`data.days.filter(d.checked_in).length` 直算），i18n 补 home.weeklyCount 双语 |
| FE-P3-21 ✅ | AdviceBanner 补 .banner-cta 可见 CTA 文本（accent 色 + 600 字重），i18n 补 home.viewPlan 双语 |
| FE-P3-22 ✅ | **按实际撑高值回写设计样例**（方案二）：00-home frontend.md TopBar 样例 `height: 64px` 删改为注记——64px 与样例自身参数矛盾（avatar 40px + padding 16px×2 = 自然高 72px，固定 64 会裁切 avatar），实现按内容自然撑高落地，代码不动 |
| FE-P3-25 ✅ | handleConfirmDeletion 入口卫语句 `if (deletionLoading) return`（本地核实 NutUI 2.7.14 Dialog 无 confirmBtnProps 属性——node_modules 类型定义零命中，方案一不可行），行为等价设计意图 |
| FE-P3-27 ✅ | setup 顶部补「你的信息」只读行（读 userStore.profile 缓存，未加载不渲染）；tsc 暴露契约修正：积分字段为 `profile.kqs_rating`（非顶层 rating），null 时显示 '-' |
| FE-P3-29 ✅ | 打卡 Toast 追加 `currentStreak` 拼接（current_streak>1 时拼「连续打卡 N 天」，键 zh/en 已备） |
| FE-P3-30 ✅ | forecast goal_completion 行改 `t(\`progress.metric.${metric}\`)` 映射 + **locales 补 8 键对齐后端 METRIC_DEFINITIONS 全集 14 键**（原仅 6 键：landing_dispersion/avg_rally_length/max_rally_length/rally_frequency/avg_ball_speed/max_ball_speed/score_win_rate/key_point_win_rate）；调整空对象兜底 noData 分支 |
| FE-P3-31 ✅ | advice 页首次分析分支补提示行（firstAnalysisHint 死键激活，is_first_analysis 双处消费：标签+提示行） |
| FE-P3-32 ✅ | plans/detail 头部补「调整历史」区块：fetchPlanAdjustments 挂载接线 + adjustments 区块渲染（version/action Tag/reason/changes_summary）；**ADJUSTMENT_ACTION_MAP 批次 D 补双语键后的首次组件消费落地** |
| FE-P3-33 ✅ | 抽公共 components/DeletionCoolingBanner（秒级倒计时逻辑下沉组件内），profile 页删本地倒计时 effect+死样式、settings 页接入获倒计时（settings.md L620 反幻觉约束兑现）+删死样式 |
| FE-P3-34 ✅ | membership tiers 失败/空列表分支：tiersError（批次 B FE-P2-24 已备标志）或空列表渲染 Empty + 重试按钮，i18n 补 tiersEmpty 双语 |
| i18n | 批次 E 新增 14 键/侧（home 2 + scoring 2 + metric 8 + training 1 + membership 1） |

> **批次 E 验证门禁（全绿 ✅ 2026-11-12）**：tsc --noEmit 零错误 / eslint 0 error 100 warning（与批次 D 基线持平，新增代码零新增 warn）/ Jest --maxWorkers=2 30 套件 285 用例全绿 / H5 生产构建成功（E2E 前重建 dist）/ **E2E 7 spec 全过（2.4m，a11y 40 页 + onboarding 双态 critical/serious 零违规）**/ weapp 构建 bundle 1.27MB ≤ 8MB 门控（较批次 D +0.01MB，新组件合理增量）/ 后端零改动（批次 E 纯前端，无需复跑后端套件）。

> **批次 E 过程注记（3 项）**：
> ① **CheckinCalendar edit 污染事故**——周计数块插入时 edit 工具报成功但写入被破坏（key 表达式被替换为字面占位符 + map 闭合块重复追加），tsc 首跑 12 错暴露（TS1145/1382 parsing error）；全局 rg 排查其余文件零污染（仅此 1 文件）；修复后 tsc 零错。呼应既有教训：**edit 成功 ≠ 改动符合预期，批量 edit 后必须 tsc/全局 rg 核对**；
> ② Jest 默认 worker 数在本机触发 Zone Allocation OOM（7 suite 假失败、209 用例未跑），`--maxWorkers=2` 复跑 285 全绿——环境限制非代码回归，复验时一律带该参数；
> ③ setup 档案行积分字段契约：userStore UserProfile 无顶层 rating，实为 `profile.kqs_rating: number \| null`（开球网积分）——消费前先核类型定义，勿凭 v1.0 线框字面命名推断。

**批次 F：产品裁决类 11 项——✅ 已完成（2026-11-13 用户拍板「按推荐执行」，9 项文档注记 + 2 项代码修复）**

| 项 | 裁决结果与落地方式 |
|----|------|
| FE-P1-1 ✅ | **(b) 据实关闭**：01-auth/frontend.md L566 注册表行改注记（Phase 1 无 3D 等重功能跳 H5 场景不注册，h5-token/h5-exchange 端点与 service 契约保留待 Phase 2+ 启用接线）+ 总览 §2 模块表 auth 行同步注记 |
| FE-P2-17 ✅ | **裁剪口径注记**：07-training §4.7 模板详情页节头注记——v1.0 P1.11 方案卡「频率/预期周期/生成训练单（可打印）」三项裁剪：template_data 契约无 frequency/cycle 字段（字段级补齐需后端扩展 Phase 1 不做）；生成训练单意图实际承接链路 = progress/summary 方案状态卡 → plans/detail 训练单列表页；「可打印」weapp 无承载删裁 |
| FE-P3-14 ✅ | **修订验证清单为 32px**：05-match_data L1326 清单行原 48px 与本档 §5.4 样例 `font-size: 32px` 自相矛盾（实现即 var(--fs-h1)=32px），以样例与实现为准 |
| FE-P3-18 ✅ | **维持现状 + 注记**：training-tab.md §7 节头注记——独立常量文件未建，入口常量内联 pages/training/index.tsx（唯一消费方无跨页共享需求，内联处注释自证同构），文件组织级偏差无行为差异 |
| FE-P3-23 ✅ | **豁免 + weapp config 静态限制注记**：总览 §3.7 权威段注记——navigationBarTitleText 为编译期静态配置非运行时渲染，setNavigationBarTitle 动态机制需逐页挂接且语言切换后页面栈存量页不回刷，Phase 1 全项目豁免；页面内文本仍守 t('key') 约束 |
| FE-P3-26 ✅ | **代码修复（核实后从「报告页专用子键 or 共用枚举+注记」二选一改判为纯文案修正）**：zh 顶层 technique 段值原装记分枚举语义（正手快攻/正手弧圈/拧拉…），en 侧与 03 设计 §7 样例均为分析语义——修正 zh 值对齐设计（正手拉球/反手拉球/正手攻球/反手拨球…）；核实报告页 technique_stats 图例与 big-data favorite_shot 双消费方均走本段分析语境，记分语境独立走 scoring.method.*/scoring.technique.* 段无交叉（04-scoring 设计 scoring.technique 段与实现一字不差不受影响） |
| FE-P3-35 ✅ | **代码修复（statusClass 改读 map.color）**：membership 页 statusClass 四类硬编码删除，改 statusColor() 读 MEMBERSHIP_STATUS_MAP.color 内联 style 注入（六态唯一权威源，未登记状态兜底 secondary）；membership.scss 四个状态类删除——核实双源已实际漂移（grace_period 落 default 灰而映射 accent 橙、closed 落 danger 红而映射 secondary 灰），修复后顺带闭合两处色值漂移 |
| FE-P3-39/40 ✅ | **总览 §3.9 豁免注记**：lazyLoad/VirtualList/debounce 与 Image lazyLoad ESLint 检测规则 Phase 1 豁免（列表均为服务端分页上限 20/页内、Image 集中于头像与单报告配图、输入类表单单点提交无连续触发场景）；Lighthouse 审计随真机验收阶段（FS8-11）再评估 |
| FE-P3-41 + FE-P2-26 余量 ✅ | **注记维持 warn**：总览 §3.8 回注——三交互规则 weapp 平台 View 无键盘焦点语义按 error 会成死规则；View onClick ARIA 实测 134 处（原估 105）分层覆盖：axe 可检测项（铃铛 ariaRole/aria-live、SVG role="img"）已落地且 40 页扫描 CI 门禁强制零违规，剩余容器 role/aria-label 需逐处语义判断列独立后续批次（补齐后升 error），Phase 1 不铺量防形式化假可达标签 |
| FE-P3-42 ✅ | **文档侧回注切片契约**：v2.0 §十 L1497 视频上传降级行注记——「受限 10MB 引导到 App」为 v1.0 早期口径，实施以 03-video_analysis 切片契约为准（STS 直传 OSS 上限 500MB，Phase 1 无 App 端可引导，不做 10MB 限制与降级提示） |

> **批次 F 验证门禁（全绿 ✅ 2026-11-13）**：tsc 零错误 / eslint 0 error 100 warning（基线持平）/ Jest --maxWorkers=2 30 套件 285 用例全绿 / H5 重建 + **E2E 7 spec 全过（2.6m，a11y 40 页零违规——membership 状态 chip 改内联色与 report 页 technique 图例改文案后复扫无回归）** / weapp 1.27MB 门控内 / 后端零改动无需复跑。

> **批次 F 过程注记**：P3-26/P3-35 两项在逐字核实（消费方 grep + 设计样例比对 + 后端键集对照）后从「注记类」改判为小代码修复——P3-26 是 zh 侧真实文案偏差（en 已正确）、P3-35 双源已产生实际色值漂移（grace_period/closed 两态），注记会掩盖已发生的行为缺陷；核实型审计的价值点：**裁决前先查消费方与双源是否已漂移，再决定「注记 vs 修码」**。

**批次 G：跨栈契约类 4 项（依赖后端排期协调，前端就绪度高）**

| 项 | 后端缺口 | 前端就绪度 |
|----|----------|-----------|
| FE-P1-3 | ReportDetail 补对手侧 nine_grid | toggle 双按钮 + §5.3 样式设计已备 |
| FE-P2-5 | result_data 补节奏序列（如 rally_tempo） | 区块样式可参考 conic 先例 |
| FE-P2-6 | **先核验 key_points 是否已含时间戳**——含则纯前端可实现（marker 点击 seek），不含则后端补 | Video seek 能力待真机验证 |
| FE-P2-14 | MatchCreateRequest/Match 补 opponent_playing_style | 四选项 Picker 设计已备 |

> FE-P2-20 中期部分（auto-renew 操作端点 + 订单关联报告字段）同批协调。四项均可先文档注记降级。

**收敛口径**：批次 D/E/F 已完成（累计 83 项：批次 D 闭环 53 + 收尾增量 3 + 批次 E 16 + 批次 F 11），余批次 G 跨栈类 4 项（+ FE-P2-20 中期部分，依赖后端排期协调；四项均可先文档注记降级）；批次 G 完成后前端设计→实现契约面宣告收敛；届时按惯例执行 **Round 2 全量遗漏复审**（方法学同本轮 11 代理比对，重点：已修复 83 项的断言级回归 + 新增注记自洽性——尤其批次 F 九处注记与实现的双向核对 + 本轮新增代码（webview 页/community 页/常量文件/DeletionCoolingBanner 公共组件/membership statusColor 内联色）的设计文档反向同步）。