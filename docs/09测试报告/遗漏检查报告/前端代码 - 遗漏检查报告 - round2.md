# 前端代码遗漏检查报告 Round 2

> **复审基线**：HEAD `6d9cb37`（R-FE-R2 批次G 收敛后，2026-11-13）
> **方法学**：同 Round 1 的 11 代理比对——设计文档（13 切片 frontend.md/backend.md + 总览六节 + 界面设计 v2.0 全局章节 + API/DB 设计）↔ 实现（frontend/src + app/）双证据核验，跨代理去重
> **复审重点**（区别于 Round 1 的设计→实现单向扫描）：① 已修复 87 项的断言级回归核验（REG×3）② 批次F 九注记 + 历史注记自洽性双向核对（ANT）③ 批次G 跨栈契约四方一致性（XSTK）④ 修复批次新增代码的设计文档反向同步核验（DOC×3）⑤ 全量遗漏扫描（SWEEP×3，捕捉 Round 1 漏报与修复引入的新遗漏）
> **纪律**：全程只读；显示层脱敏（[REDACTED:sha256:…]）以 tmp/ 探针字节级实证兜底；P1 发现均经主会话独立复现确认

---

## 一、汇总统计

> **修复进展（2026-11-16 批次H 回填，详见 §八）**：P1×1 + P2×11 **全部修复**（工作区未提交态）+ P3 顺带修复 1 项（R2-P3-7）；门禁实证 pytest 53 passed / tsc 0 错 / Jest 285 全绿。P3 余 26 项未动 + 批次H 引入伴生缺口 5 项（P2×3 文档承载缺失 + P3×2 E2E 镜像未闭环），处置见 §8.4。

| 维度 | P0 | P1 | P2 | P3 | 小计 |
|------|----|----|----|----|------|
| 回归核验（REG1-3，87 项基线） | 0 | 1 | 3 | 2 | 6 |
| 注记自洽（ANT，24 条核验） | 0 | 0 | 2 | 1 | 3 |
| 跨栈契约（XSTK，27 个契约点） | 0 | 0 | 0 | 4 | 4 |
| 反向同步（DOC1-3，逐资产） | 0 | 0 | 6 | 17 | 23 |
| 全量扫描（SWEEP1-3，12 切片+全局） | 0 | 0 | 0 | 4 | 4 |
| **合计（去重后）** | **0** | **1** | **11** | **27** | **39** |

**修复回归总账（87 项基线）**：82 项完整在位（94.3%）✅；2 项部分在位 ⚠️（FE-P3-10 排查未尽→JS 残留、FE-P3-1/2/3 scss 清了 JS 没清）；**3 项假修复/承诺面未闭环 ❌**（FE-P1-6 wire 层断裂〔P1，主会话独立实证〕、FE-P3-19 批次G 未兑现、FE-P3-30 修复落点偏移）。

**零遗漏扫描面**：SWEEP 组 12 切片 + 全局 9 维度中，**07/08/09/11/12 + training/user tab + 05/06/00 + match-tab 共 11 个范围零新增遗漏**；01-auth 3 项 P3；02-user 1 项 P3（批次E 引入回归）。i18n 全局门禁 zh/en 各 779 扁平键双向 diff 为空。

---

## 二、P1 发现（1 项，立即修复）

### R2-P1-1｜scoring 局分 wire 层断裂——批次B FE-P1-6「跨栈修复」实际为假修复

**现象**：bo3/bo5/bo7 多局模式下，scoreboard 页大比分区（games_won_user/opp，`?? 0` 兜底）运行时恒显 `0:0`，仅终局 finish_match 按局分正确判胜负。

**根因（三路径全断 + 静态核验盲区）**：
- `get_match_detail` 返回 dict（`app/services/scoring_service.py:207-226`，18 键）**不含 games_won_user/games_won_opp**——初始加载（进入记分页 loadMatch）拿不到局分；
- `score_update` WS 广播 payload（`scoring_service.py:313-324`）仅携带当前局比分，**无局分**；
- `sync_match` 重连同步（`app/api/v1/ws.py:161-169`）复用同一 detail dict 且只挑 status/current_score/score_sequence 三键，**无局分**；
- `schemas/scoring.py:96-99` MatchDetail schema 批次B 已加 games_won 两键，但 scoring 路由 10 端点**全部无 response_model**——schema 是摆设，service 手拼 dict 即线上契约。

**为什么四轮门禁全绿 + REG-2 静态核验 ✅ 仍漏**：E2E mock（scoring-mocks.ts:42-43/82-83/128-129/180-187）喂了 games_won 数据，断言在 mock 数据上通过；静态核验只验「schema 有字段+store 有类型+页面有渲染+mock 有数据」四层存在性，未穿透 service dict。**这是「修复存在性核验」与「修复行为性核验」的结构性差异，Round 2 断言级回归审查的核心价值点。**

**修复方案**：① `get_match_detail` dict 补两键（`games_won_user`/`games_won_opp`，model 已有值）——一处修复同时覆盖 detail 响应与 sync_match；② `score_update` payload 局推进分支补局分（或前端在 game 推进后主动 refresh）；③ E2E 侧：scoreboard 断言「大比分 0:0」当前在 mock 上必然通过——修后端后 mock 断言保持，另补一条「detail 响应含 games_won」的契约断言（integration 层，防 schema/dict 再次漂移）；④ 后端补 HTTP 层测试（当前 `tests/` 仅 Model 层断言 games_won，grep 确认）。

**证据**：设计承诺 `schemas/scoring.py:96-99` 注释「局分暴露——前端需展示大比分」+ `frontend/src/stores/scoringStore.ts:33-36` 声明并注释「后端 MatchDetail schema 已暴露」；实现断裂 `scoring_service.py:207-226`/`313-324`、`ws.py:161-169`；消费点 `frontend/src/pages/scoring/scoreboard/index.tsx:167-192`。

---

## 三、P2 发现（11 项，分批修复）

### 修复承诺面未闭环（3 项——「假修复」型，同 R2-P1-1 谱系）

**R2-P2-1｜gamification BADGE_CATEGORY_MAP 契约未接 + 「归批次G」归因注记失实**
批次E FE-P3-19 注记声称「消费端接线依赖后端 schema 暴露 category/source，归批次G 跨栈协调」（`frontend/src/constants/gamification.ts:5-6`）——**批次G 已交付 4 项不含此项，归因注记失实**。后端数据层就绪（`app/models/gamification.py:85` category 列+索引+种子，`gamification_service.py:50-60`），但 `BadgeEarned/BadgeLocked` schema（`app/schemas/gamification.py:38-55`）不暴露 category/source；前端 BADGE_CATEGORY_MAP 常量全 src 零消费（孤儿），10 个 i18n 键无渲染路径（死键未真正激活）。设计承诺：`09-gamification/frontend.md:938-944` 四分类 + `:1110` 验证清单「徽章列表：已获得/未获得正确分类」。**双轨**：优先后端 schema 补 category/source（数据层就绪，服务层 select 透传即可）+ badges 页消费分组；备选设计文档注记「分类展示 Phase 2+」并修正归因注记。

**R2-P2-2｜POINTS_SOURCE_MAP 设计常量超前于后端能力**
六来源映射常量 + i18n 六键双语就绪（探针实证），全 src 零消费；后端无积分流水表（models 仅 user_points 汇总，`_add_points` 只累加）、无积分历史端点（router 仅 4 端点）——**纯前端备选不可行（无数据源）**。设计承诺：`09-gamification/frontend.md:928-936`。**双轨**：优先后端补 PointTransaction 流水表 + GET points-history 端点（event_type 枚举与 add_points 入参一致可直接落列）；备选文档注记 Phase 2+ 预置并移除失效归因。

**R2-P2-3｜FE-P3-30 forecast 区修复落点偏移 + 「14 键对齐」口径失实**
原发现指认「forecast 区 `<Cell title={metric}>` 直显后端英文键名」——批次E 实际只修了 goal_completion 行（`summary/index.tsx:182`），**forecast 区 `:204` `title={metric}` 零改动仍直显裸键名**；台账表述从「forecast 区」漂移为「goal_completion 行」且标 ✅。另「对齐 METRIC_DEFINITIONS 14 键全集」失实——后端自 S4（bb06698）起即 **18 键**（`progress_service.py:29-46`），serve_point_win_rate 等 4 键无 locales 回退键，goal_metrics/trend 含此 4 键时 t() 仍显示裸键名。证据：`zh-CN.ts:622-638` metric 段 14 键 vs 后端 18 键。

### 注记数字失真（2 项——豁免决策方向成立，论据数字不可复用）

**R2-P2-4｜总览 §3.9 性能豁免注记分页数字失实**（ANT-01）
注记声称「报告 10/页、订单 10/页」——实测报告 **20/页**（`videoAnalysisStore.ts:197-203` + list 页 `PAGE_SIZE=20` + 后端 router default=20）、订单 **50/页**（`paymentStore.ts:43/89`，一次拉满上限）。订单 50/页差 5 倍，弱化「首屏 DOM 数十量级」豁免论据（结论方向仍可维持）。**修正注记数字，防后续虚拟滚动评估误判。**

**R2-P2-5｜总览 §3.8「134 处 View onClick」口径失实**（ANT-02）
134 实为全工程 onClick 出现次数口径（当前 138，含 Text 元素/props/mock/测试）；真实「View 容器 onClick 待补 ARIA」仅 **36 处**（引号感知探针），eslint 三交互规则唯一违规位置 **47 处**（View 38 + Text 9）。豁免决策方向不受影响（实际工作量比声称小 3.7 倍），但该数字不可复用作后续批次工作量估算。**修正注记口径。**

### 反向同步滞后（6 项——文档腐化型，照文档维护会复现已修缺陷）

**R2-P2-6｜03 §4.3 热图样例未随批次G 回写**（DOC1-01）
实现三条件（activeGrid 派生 landing_heatmap 优先/旧报告回落 landing_points.nine_grid/对手视图不渲染正手率 hint，`report/index.tsx:86-91/210-244`）已落地，但 `03-video_analysis/frontend.md:881-917` 样例仍编码修复前行为（无条件 toggle+无条件 hint）——照样例实现会在对手视图渲染「正手使用率」。

**R2-P2-7｜04 frontend.md 统计段 key_points 字段名断点**（DOC2-02）
设计样例 `{seq, scorer, method}`（`:167` 接口 + `:690` `kp.scorer`）vs 后端实际契约 `{seq, score, winner, method, timestamp}`——照文档维护会读 undefined 误显「对手」（实现 `statistics/index.tsx:137-140` 已正确消费 winner/score）。

**R2-P2-8｜04 frontend.md 批次B/C/E 改动零同步零注记**（DOC2-03）
21 分制 Picker、deuce 提示条、lastScoreFlags Toast、game-info 局分区、赛后三件套、逐局比分明细等批次B/C 全部功能在 `frontend.md` 无样例无注记（grep「R-FE-R1/批次B/批次C/批次E/timestamp/21分/TARGET_SCORE」零命中）；§7 i18n 段缺 22 键；§4.1 import 行缺 OPPONENT_STYLE_OPTIONS（样例编译级缺陷——批次G 只同步了自己，没补前账）。

**R2-P2-9｜API 设计 §5 样例滞后族**（DOC2-04）
undo 响应样例仍 `"action": "undo"`（实现 R18-P3 已改 `"type"`）；§5.3 详情缺 target_score/opponent_playing_style/game_number（实现返回且前端消费）；§5.4 score 缺 should_change_sides/match_finished（backend.md 反幻觉约束 L1661 明确要求）；§5.7 缺 total_points。

**R2-P2-10｜04 backend.md 样例滞后族**（DOC2-05）
ScoreRecordBrief 样例仍 `seq`（实现已改 `sequence`）；MatchDetail 样例缺 current_score/games_won 两键；list_matches/get_match_detail 样例 `model_validate` 形态 vs 实现手拼 dict——**「样例路径会带出 schema 字段、手拼路径不会」正是 R2-P1-1 字段丢失的形态根源**；undo WS 广播样例缺 match_id。

**R2-P2-11｜10-membership 页面样例保留旧 statusClass 四类**（DOC3-03）
批次F FE-P3-35 已修复的双源漂移源头样例（`status-active/warning/danger/default` 四类，`10-membership/frontend.md:243-274`）未同步为 statusColor 内联形态；报告 L315 承诺「裁决后统一以 R-FE-P3 注记格式回写设计文档」未兑现于该文档——照旧样例重构会重新引入已修复的双源缺陷模式。

---

## 四、P3 发现（27 项）

### 代码级（5 项）

| 编号 | 描述 | 证据 |
|------|------|------|
| R2-P3-1 | report 页 JS 内联旧主色残留族（FS3 时点漏网，非批次E/F/G 回归）：`PRIMARY_RGB='230,57,70'`（#E63946）九宫格热图深浅 + `:171` conic 首色 `#E63946` + `:93` 注释旧称——同页图例消费 `var(--color-primary)`=#C92738，同页双源色值漂移；其切片设计样例（`03 frontend.md:836-837`）同为旧值，**文档+代码双点同步** | `report/index.tsx:93-99/171` vs `dashboard LandingHeatmap.tsx:46`（'201,39,56'）；git 归因仅 FS3 初始提交命中 |
| R2-P3-2 | DeletionCoolingBanner 配色回归（**批次E FE-P3-33 组件下沉时静默引入**）：组件 scss 用 `color-mix(var(--color-warning) 10%)` 琥珀底，设计承诺红色系（`02-user/frontend.md:1365-1413` primary 8% 底+20% 边框）；git 证据 fb89a96 下沉前 profile 横幅为 rgba(230,57,70,0.08/0.2) 红底与设计一致——同批次明言「消旧主色残留」却反向 warning 化且不在恢复名单 | `components/DeletionCoolingBanner/index.scss:6/21/47` vs 设计 L1365-1413/L1915 |
| R2-P3-3 | feedback「准确」按钮未清空 feedbackComment——弹窗输入说明后取消再点「准确」，残留 comment 随 is_correct=true 提交（设计样例 `:1055-1059` 有清空承诺） | `report/index.tsx:396-398/52` |
| R2-P3-4 | E2E technique_stats mock 键集偏离 API §4.6 契约（loop/smash/push/block vs forehand_drive 等），`loop` 无双语键→图例回退渲染键名 | `analysis-flow.spec.ts:125` vs `05-API详细设计.md:1253` |
| R2-P3-5 | OverviewCards.tsx 批次标记笔误：「R-FE-R1 批次C」应为「R-FE-R2 批次B/C」（fb89a96 落地）；行为无缺陷 | `OverviewCards.tsx:56` vs `00-home/frontend.md:440-441` |

### 跨栈契约细节（3 项）

| 编号 | 描述 | 证据 |
|------|------|------|
| R2-P3-6 | opponent_playing_style 回显字段全工程无页面渲染消费（创建后仅取 match_id 即跳转）——存储/返回链完整，定性前向交付字段；backend.md 注释「setup 页创建(后立即)消费」与实际不符 | `scoring_service.py:135-136` 注释 vs `setup/index.tsx:43-53` |
| R2-P3-7 | statistics key_points.timestamp 前端零消费：后端返回+双文档注记「前端按场景区分消费」，statistics 页无展示承诺（按排除规则不构成缺口）；仅 store KeyPointItem 镜像类型缺 timestamp（类型注释声称「镜像 _generate_statistics」）——类型面与 videoAnalysisStore.KeyPoint 双语义显式注释不对称 | `scoringStore.ts:44-50` |
| R2-P3-8 | FE-P2-20 批次归属表述出入：报告收敛口径称「批次 D 铺垫」、代码注记与批次表均为批次C——痕迹级；auto-renew 端点后端确不存在（grep 3 处只读链），「归后端排期」口径与实际一致 | `round1.md:504` vs `:395`、`membership/index.tsx:113` |

### 反向同步文档滞后（13 项）

| 编号 | 描述 | 证据 |
|------|------|------|
| R2-P3-9 | 03 样例缺批次G 派生逻辑定义（tempoPts/tempoSegments/keyPoints/seekTo/formatTime 引用未定义） | `03 frontend.md:1000-1045` vs `report/index.tsx:102-153` |
| R2-P3-10 | 03 §5.3 选择器列表缺 `.tempo-section`；keypoint-chip 缺子样式；tempo-segment 缺 border-radius:1px | `03 frontend.md:1490-1513` vs `report/index.scss:69-75/152/186-206` |
| R2-P3-11 | 03 i18n 文档键集滞后：缺 quotaRemaining/bonusRemaining/confirming/creatingTask/viewAdvice 五键 + technique 段缺 flip/smash（viewAdvice 跨切片注记在 07，03 未同步） | `03 frontend.md:1924-2008` vs `zh-CN.ts:447-455/502/174-176` |
| R2-P3-12 | 03 §9 清单区块顺序「技术统计→节奏曲线→球速」与样例/实现「球速→节奏曲线」不一致 | `03 frontend.md:2232` vs `report/index.tsx:289-327` |
| R2-P3-13 | 03 §9「节奏曲线点数=回合数」验收口径与 mock 不自洽：total_rallies=23 但 rally_tempo 20 值（演示数据下验收必误判失败） | `03 frontend.md:2225` vs `report_generator.py:111-123` |
| R2-P3-14 | 03 样例 NutUI API 偏移族：环形图 clipPath polygon（实现 conic-gradient+donut-hole）/ percentage/Textarea 1.x 命名——仅实现侧有 FS3-P3 注记，文档无对应注记 | `03 frontend.md:925-937/568/771` vs `report/index.tsx:155-176` |
| R2-P3-15 | 03 §3 契约缺 TaskDetail.error_message/ReportDetail.is_readonly/task_uuid（backend.md R13-P3 与 API §4.6 均已注记，frontend.md 未跟）；§4.2 缺失败分支 error 展示 | `03 frontend.md:164-231` vs `videoAnalysisStore.ts:24-28` |
| R2-P3-16 | 04 frontend 样例 NutUI API 偏移族：Cell children 形态（实为 extra prop）/Skeleton width/height（无此 props）/Popup onConfirm（无该回调）/maxlength 小写 | `04 frontend.md:346-362/831/594-600` |
| R2-P3-17 | 04 样例导航 navigateTo vs 实现 redirectTo（setup/scoreboard 两处，防页面栈残留——合理实现选择未注记） | `04 frontend.md:332/496` vs `setup:53`、`scoreboard:74/128` |
| R2-P3-18 | 00-home 切片样例未承载批次A/E 资产：积分卡区块（跨文档由 09 §4.1 承载）、周计数行、AdviceBanner CTA——首页权威布局三处未回写 | `00-home/frontend.md:262-320/547-594/706-749` |
| R2-P3-19 | webviewFallback 键未入 settings.md §5 i18n 清单 + H5 降级分支无设计侧说明（v2.0 §十 仅含 App→小程序维度，不冲突但未承载） | `settings.md:550-576` vs `webview/index.tsx:32-37`、zh:278 |
| R2-P3-20 | community-tab.md Phase 1 TabBar 禁止约束过时：「禁止将社区 Tab 加入 TabBar」vs 实际 5-Tab 已含 community（总览 §3.4 权威口径 + 用户可达性成立）——照 L277 约束会误判现行实现违规 | `community-tab.md:08/218/277` vs `app.config.ts:68` |
| R2-P3-21 | DeletionCoolingBanner 公共组件抽取形态未回写任一设计文档（02-user X-23 与 settings L197 仍为页内内联形态样例）；倒计时契约语义完整兑现 | 02-user:660/1949、settings:197 vs `components/DeletionCoolingBanner/index.tsx` |

### 测试基建与全局（6 项）

| 编号 | 描述 | 证据 |
|------|------|------|
| R2-P3-22 | a11y-mocks 报告载荷缺 score_analysis 段（annotated_video_url=null 使 video-section 不渲染）→ 关键分 marker chip 区块未入 axe 覆盖；头注释「E2E-01 同源载荷」声明过时——**与 annotated_video_url 差异不同属 a11y 特性继承，可低风险补 score_analysis（不含 video）** | `a11y-mocks.ts:74-115` vs `analysis-flow.spec.ts:128-134` |
| R2-P3-23 | annotated_video_url 差异口径仅 a11y-mocks 单侧注释留痕（null 防 video-caption），analysis-flow 真 URL 处无对称留痕 | `a11y-mocks.ts:98-99` vs `analysis-flow.spec.ts:141` |
| R2-P3-24 | i18nKeys.test 显式域断言未扩批次E/F/G 新键（结构守卫已拦截单侧缺失，仅弱化回归定位速度，不构成缺口） | `i18nKeys.test.ts:19-41` |
| R2-P3-25 | 01-auth i18n 样例使用 `.json` 格式 vs 实际 `.ts`（总览 §3.7 权威方案）；切片样例格式滞后 | `01-auth/frontend.md:585-609` |
| R2-P3-26 | 01-auth 登录契约变更未同步：§3 `Promise<void>`+无条件 switchTab vs 实现返回 needsConsent boolean 条件跳转（FS8-P1-1 已修 P1 缺陷）——**按设计文档重实现会复现已修 P1 缺陷**（实施计划 L381 已记录，切片文档未跟） | `01-auth/frontend.md:144-145/324/363` vs `authStore.ts:39-40/75/101` |
| R2-P3-27 | 界面设计 vs 总览背景/分割线双基准漂移：界面设计 `#F1FAEE`/`#DEE2E6` vs 总览+app.scss `#F8F9FA`/`#E9ECEF`——R-FS8-10-P3 兜底句「以 app.scss 为准」可覆盖但逐项清单仅列 4 token，background/divider 不在列 | `界面设计:33/37` vs `总览:131/138`、`app.scss:26/33`；另 h5-bridge 页头注记「39 页口径」应为 40（`h5-bridge/index.tsx:7`） |

---

## 五、回归核验台账汇总（87 项基线）

| 批次域 | 项数 | ✅完整 | ⚠️部分 | ❌未闭环 |
|--------|------|--------|---------|----------|
| 批次A（9）+ 批次B付费组（3） | 12 | 12 | 0 | 0 |
| 批次B/C（41）+ 批次D收尾（3） | 44 | 42 | 1（FE-P3-10） | 1（FE-P1-6 → R2-P1-1） |
| 批次E（16） | 16 | 14 | 1（FE-P3-1/2/3 scss✅JS残留） | 1（FE-P3-19 → R2-P2-1/2） |
| 批次F（11） | 11 | 11 | 0 | 0 |
| 批次G（4+配套） | 4 | 4 | 0 | 0 |
| **合计** | **87** | **83** | **2** | **2** + 1 项假修复（FE-P3-30 → R2-P2-3，REG-3 台账内计为❌2 含 FE-P1-6，口径对齐后见明细） |

> 台账口径说明：REG-3 原报「❌2 = FE-P3-19 + FE-P3-30」；FE-P1-6 由 DOC-2 深挖从 REG-2 的静态 ✅ 改判 ❌（主会话独立实证）。**修复存在性核验 ≠ 修复行为性核验**——FE-P1-6 四层证据（schema/store/页面/mock）全在位仍为 wire 层断裂，是本轮方法论沉淀：静态回归必须穿透到「数据实际到达路径」（service return dict / WS payload / mock 是否喂了后端不会给的数据）。

**批次F 九注记自洽性**：7/9 完全自洽（h5-bridge/P2-17/P3-14/P3-18/P3-23/P3-42 + P3-26/P3-35 代码修复）；2/9 数字失真（R2-P2-4/P2-5）。批次G 四项跨栈契约全链一致（枚举四方逐字、rally_tempo 20 值三方探针逐字、opponent_nine_grid 四方网格一致、timestamp 双语义分层三处注记齐全防混用成立）；设计文档 6 处同步与代码零偏差。

---

## 六、分级处置建议

**立即修复（P1，1 项）**：R2-P1-1 scoring 局分 wire 层——后端 dict 补两键 + WS payload + HTTP 层测试 + E2E 契约断言。修复量小（一处 dict + 广播分支），但必须补「穿透 mock」的测试防复发。

**分批修复（P2，11 项）**：
- **跨栈组（3 项）**：R2-P2-1（后端 schema 补 category/source + badges 页消费——批次G 欠账）、R2-P2-2（流水表+端点或注记降级）、R2-P2-3（forecast 区 t() + 4 键 locales 补齐）——建议归入「批次 H 跨栈收尾」；
- **注记修正组（2 项）**：R2-P2-4/P2-5 纯文档数字修正，5 分钟工作量，可顺手修；
- **文档同步组（6 项）**：R2-P2-6/7/8/9/10/11——批次B/C/E 前账 + 批次G 欠账的设计文档回写，其中 **R2-P2-10 的 model_validate→手拼 dict 形态根源修正可与 R2-P1-1 修复联动**（文档样例改回手拼 dict 形态并补 games_won，或推动路由补 response_model 一劳永逸）。

**P3（27 项）**：按惯例可分「代码顺手修」（R2-P3-1/2/3/4/5，其中 R2-P3-2 DeletionCoolingBanner 配色回归建议随批次H 一起修——组件色回设计口径）与「文档注记/回写」（R2-P3-6~27）。R2-P3-22 a11y-mocks 补 score_analysis 段建议优先（低成本扩大 axe 覆盖面）；R2-P3-26 登录契约样例建议同步（防按文档重实现复现 P1 缺陷）。

---

## 七、收敛判定

- **零 P0**：Round 1 的三项 P0（页面可达性）修复全部经受住了六轮修复批次的交互面回归；
- **11/12 扫描范围零新增遗漏**：设计→实现契约面高度收敛，Round 1 修复质量整体 94%+；
- **发现谱系**：39 项中 37 项为 P2/P3 文档滞后与细节，仅 2 项（P1×1 + P2 谱系中 3 项假修复）是真正的行为级缺陷——且全部集中于「修复存在性 ≠ 行为性」与「注记归因失实」两个谱系；
- **方法论沉淀**：①静态回归核验必须穿透 mock 到达路径；②「归批次G」类跨批注记在批次关闭时必须核销（批次G 交付清单未含 gamification 接线）；③注记数字必须可复现（134 处/10 每页均失真）；
- **后续**：建议按 P1 → 批次H 跨栈收尾（P2-1/2/3）→ 文档同步批 → P3 顺手修顺序推进；完成后可启动 Round 3 轻量复审（聚焦批次H 回归 + 本轮 P2 闭环验证）。

---

*报告生成：2026-11-13 ｜ 11 代理并行审查（REG-1/2/3 + ANT-1 + XSTK-1 + DOC-1/2/3 + SWEEP-1/2/3）｜ 全程只读，git status 零改动 ｜ P1 发现经主会话独立实证（scoring_service.py:207-226 / ws.py:161-169 亲读确认）*

---

## 八、批次H 修复核验与回填（2026-11-16）

> **核验基线**：HEAD 仍为 `6d9cb37`（零新提交），**批次H 修复位于工作区未提交态**（31 文件 +1068/-124 + 新增迁移 1 件）——只看 git log 会漏掉整轮修复，本次核验以 `git diff` 工作区逐项映射回报告编号，凭代码内「R2-Pn-x（批次H）」注记锚定。
> **核验纪律**：核验全程只读（不动批次H 修复代码）；探针脚本仅做 [REDACTED] 三态判定后清理；动态门禁三项实跑（后端受影响域 pytest / tsc / Jest 全量）。

### 8.1 修复状态总账（39 项 → 13 修复 / 26 未动）

| 分组 | 编号 | 状态 | 修复证据（工作区 diff） |
|------|------|------|------|
| **P1** | R2-P1-1 | ✅ 已修复 | **三路径 + 第四路径全补**：① `get_match_detail` dict 补 `games_won_user/opp`（scoring_service.py:218-226，带 FE-P1-6 假修复收口注记）② `score_update` WS payload 补局分（:316-331，含 applyWsScoreUpdate 即时消费注记）③ `sync_match` 重连同步补两键（ws.py:165-171）④ score 响应 dict 补两键（:347-357，doScore 后无需 fetchMatch）。**根治性加固**：scoring 路由 10 端点全量 `response_model` + 路由内显式 `model_validate(...).model_dump()`（router.py 头注记「schema 即契约」——统一信封 success() 返回 JSONResponse 时 FastAPI 跳过自动过滤，故显式校验；schema 加键而 service 漏给时立即 ValidationError，消除「schema 是摆设、手拼 dict 即线上契约」形态根源，即本报告 §六建议的「推动路由补 response_model 一劳永逸」选项落地）；schema 补 `ScoreResponse.match_finished/games_won_*` + 新建 `MatchCreateResponse/MatchListResponse`。测试 4 个新增（test_scoring.py:779-947：detail/score 契约穿透断言 + WS payload **Redis pubsub 实收断言**〔11 条广播致胜球携带局分 1:0，穿透 mock 的行为性守卫〕+ create/list 键面契约 + test_ws.py sync_match 局分断言）。前端：services/scoring.ts 补 `ScoreResponse` 镜像类型 + score() 泛型化；scoringStore `WsScoreUpdateData` 补两键 + `applyWsScoreUpdate` 局分乐观更新（:260-290）。 |
| P2 | R2-P2-1 | ✅ 已修复 | 优先轨落地（后端 schema 补透出）：`BadgeEarned/BadgeLocked` 补 `category: Optional[str]`（schemas/gamification.py:40-58）+ BadgeService earned/locked 两分支 select 透传 `d.category or "general"`（gamification_service.py:376-391）；badges 页 `BADGE_CATEGORY_MAP` 首次组件消费（badgeCategoryLabel 导出函数 + earned/locked 两处 badge-category chip + scss chip 样式 color-mix 10% 底）；constants/gamification.ts **失实归因注记修正**（「归批次G」→ 如实记录批次H 交付）；测试断言 locked/earned 分类契约（test_gamification.py:145-203）。10 个死键全部激活渲染路径。 |
| P2 | R2-P2-2 | ✅ 已修复 | 优先轨落地（流水表 + 端点）：`PointTransaction` model（user_id/event_type/points/ref_id/created_at + 2 索引）+ alembic 迁移 `d8e9f0a1b2c3`（链 head `c7d8e9f0a1b2`→本件，downgrade 无损 drop）+ `__init__.py` 导出；`_add_points` 落流水（gamification_service.py:242-248）+ `get_points_history` 分页 service（时间倒序）；`GET /gamification/points-history` 端点（router.py:75-89，response_model 校验同 scoring 口径）；前端 PointsCard **最近积分动态区**（POINTS_SOURCE_MAP 首次消费：pointsSourceLabel 导出 + sourceOther 兜底 + 5 条 limit + formatRelativeDate + scss recent 样式）+ services 补 `getPointsHistory` + store 补 `fetchPointsHistory`；i18n 双语 `sourceOther/recentActivity` 两键；测试 2 个（落账 analysis+checkin 两笔 + 分页契约 + 手动打卡路径）。E2E 侧 base-mocks.ts 补 `POINTS_HISTORY` 数据工厂 + 收尾已注册路由闭环（✅ 见 §8.3 N-P3-1 收尾状态）。 |
| P2 | R2-P2-3 | ✅ 已修复 | forecast 区 `title={metric}` → `title={t(\`progress.metric.${metric}\`)}`（summary/index.tsx:204 + 批次H 注记）；locales 补 4 键 `serve_point_win_rate/receive_point_win_rate/attack_transition_rate/error_rate`（zh/en 双侧）——METRIC_DEFINITIONS **18 键全集**对齐（progress_service.py:29-46）；zh-CN.ts 注记口径同步修正（「14 键」→「后端自 S4 起为 18 键，补齐缺失 4 键」），台账口径失实一并纠正。 |
| P2 | R2-P2-4 | ✅ 已修复 | 总览 §3.9 分页数字实测修正：报告 **20/页**（后端 router default=20，videoAnalysisStore 与 list 页 PAGE_SIZE 同口径）、订单 **50/页**（paymentStore page_size=50 一次拉满）+ 「订单 50/页已顶满 le=50 上限，后续若放宽分页上限须复评本豁免口径」前瞻注记。 |
| P2 | R2-P2-5 | ✅ 已修复 | 总览 §3.8 口径修正：View 容器 onClick 待补 ARIA 实为 **36 处**（引号感知探针）、eslint 三交互规则违规位置 **47 处**（View 38 + Text 9），原「约 134 处」标注为全工程 onClick 出现次数口径（含 Text/props/mock/测试），不可复用为工作量估算。 |
| P2 | R2-P2-6 | ✅ 已修复 | 03 §4.3 热图样例随批次G 回写：activeGrid 派生规则注记（landing_heatmap 优先/旧报告回落 nine_grid）+ oppGrid 条件渲染 toggle + `landingView === 'mine' && landing` 条件 hint（对手视图不再渲染正手率）。 |
| P2 | R2-P2-7 | ✅ 已修复 | 04 frontend.md 统计段 key_points 契约对齐：`{seq, scorer, method}` → `{seq, score, winner, method, timestamp}`（:170-180 + 注记「旧 scorer 为文档臆造名」+ timestamp 墙钟 ISO 语义）；statistics 样例消费行同步 winner/score。 |
| P2 | R2-P2-8 | ✅ 已修复 | 04 frontend.md 批次B/C/E 前账全量补齐（259 行）：setup 页 21 分制 Picker（TARGET_SCORE_OPTIONS）/import 行补 OPPONENT_STYLE_OPTIONS + TARGET_SCORE_OPTIONS（编译级缺陷闭合）；scoreboard 页 game-info 局分区/deuce 提示条/lastScoreFlags 换边关键分 Toast/放弃恢复双 Popup；statistics 页逐局比分明细（gamesDetail 聚合）/关键分 winner/score 行/胜率汇总/赛后三件套（分享/关联视频/看板）；§7 i18n 补齐 23 键（zh/en 双侧，.json→.ts 格式修正 + 「键面以实现为准」节选注记）。 |
| P2 | R2-P2-9 | ✅ 已修复 | API 设计 §5 样例族全修（4 处注记锚定）：§5.3 详情补 `target_score/opponent_playing_style/games_won_user/opp` + `score_sequence[].game_number`；§5.4 score 响应补 `should_change_sides/match_finished/games_won_user/opp`；§5.5 undo `action`→`type`（R18-P3）+ WS 广播 match_id 注记；§5.7 statistics 补 `total_points`。 |
| P2 | R2-P2-10 | ✅ 已修复 | 04 backend.md 样例族全修：`ScoreRecordBrief.seq`→`sequence`；MatchDetail 样例补 `current_score/games_won_user/opp`（created_at 转 Optional）；get_match_detail 样例改 model_validate 形态 + **形态根源注记**（「手拼 dict 形态已废弃：schema 未声明字段无法经 response_model 流出——这正是 R2-P1-1 局分丢失的形态根源」）；undo WS 广播样例补 `match_id`（多比赛并存按 match 过滤）。**与 R2-P1-1 路由 response_model 加固联动闭环。** |
| P2 | R2-P2-11 | ✅ 已修复 | 10-membership §4.1 状态 chip 样例改 statusColor 内联形态（statusClass 四类删除），同步承载批次F FE-P3-35 的修复注记（双源漂移修复语义 + grace_period/closed 色值闭合 + FS8-7 对比度口径保持）——报告 L315 承诺「以 R-FE-P3 注记格式回写」兑现。 |
| **P3** | R2-P3-7 | ✅ 顺带修复 | scoringStore `KeyPointItem` 补 `timestamp: string \| null`（批次G FE-P2-6 墙钟 ISO 注记）+ 类型注释对齐 `_generate_statistics` 五键契约——类型面与 videoAnalysisStore.KeyPoint 双语义注释不对称闭合。 |
| P3 | R2-P3-1~6/22/23/24 | ✅ 已修复（批次I 2026-11-16） | 九项全落地：**P3-1** report 页旧主色收敛——`PRIMARY_RGB '230,57,70'→'201,39,56'`（#C92738，与 dashboard LandingHeatmap 同源派生）+ conic 首色 `#E63946→#C92738` + 03 文档 4 处同步（§4 样例 2 处 + §9 验收清单 2 处改 var 现值口径）；**P3-2** DeletionCoolingBanner 配色回归设计口径（warning 10% 琥珀底→primary 8% 底 + 20% 边框 + title/countdown-value 回 primary——批次E 下沉时误 warning 化收口）；**P3-3** feedback「准确」提交前清空 feedbackComment（按钮侧 `setFeedbackComment('')` 镜像设计样例 + handleFeedback 行为级兜底 `is_correct=true` 一律不带 comment——setFeedbackComment 异步更新不阻断当次闭包读值，仅按钮侧清空属假修复）；**P3-4** E2E technique_stats mock 键集对齐 API §4.6（analysis-flow + a11y-mocks 两处 `loop/smash/push/block→forehand_drive/backhand_drive/forehand_loop/serve`，图例不再回退渲染键名）；**P3-5** OverviewCards 批次标记笔误（R-FE-R1 批次C→R-FE-R2 批次B/C）；**P3-6** scoring_service opponent_playing_style 注释修正（「setup 页消费」→「创建后回显、当前无页面渲染消费、前向交付字段」）；**P3-22** a11y-mocks 补 score_analysis 段（E2E-01 同源数据）+ 头注「同源载荷」声明更新为如实差异口径（video-section/marker chips 仍为已知盲区，交互正确性由 E2E-01 覆盖——chips 渲染在 annotated_video_url 门控内，补数据不触 axe video-caption）；**P3-23** annotated_video_url 差异口径双侧留痕对称（analysis-flow 真 URL 侧补注）；**P3-24** i18nKeys.test 新增批次E/F/G/H 九组显式域断言（`expectBatchKeys` zh/en 双侧同断，progress.metric 18 键全集入断言）。批次I 门禁：tsc 0 错 / Jest **294**（+9 域断言）/ E2E 7 spec 2.5m（axe 40 页零违规）/ weapp 1.28MB / 后端 test_scoring 30 passed。 |
| P3 | R2-P3-8~21/25~27 | ⬜ 未修复（17 项） | 批次J 纯文档注记/回写组，逐项清单见 §8.4 批次J 段（原「16 项」口径以逐项列举为准校正为 17）。 |

### 8.2 动态门禁实证（核验态实跑）

| 门禁 | 结果 | 说明 |
|------|------|------|
| 后端受影响域 pytest（test_scoring + test_gamification + test_ws） | **53 passed**（143.95s） | 含 R2-P1-1 四新测试 + R2-P2-1/2 三新测试全部通过；子集运行 `--no-cov` 避开门控误杀 |
| 前端 tsc --noEmit | **零错误** | |
| 前端 Jest 全量（--maxWorkers=2） | **30 套件 285 用例全绿** | 与批次G 基线持平（285）；i18n 双语守卫通过（新增键双侧对仗） |
| E2E 7 spec（收尾实跑） | **7 passed（2.9m）** | H5 dist 重建后全量回归：a11y 40 页 + onboarding 双态 critical/serious **零违规**；PointsCard 最近动态区真实渲染（points-history 已注册）、badge-category chip 非空入 axe 覆盖均通过；training-flow 徽章弹层不受非空 badges mock 影响 |
| weapp 构建（收尾实跑） | **产物就绪 1.28MB** | 门控内（批次G 基线 1.27MB），dist/app.js 时间戳 2026-11-16 16:59 |

### 8.3 新发现：批次H 修复引入的伴生缺口（5 项）

> 谱系：与本报告 DOC-1/2/3 维度批判的模式同构——批次H 修复了前批次的文档欠账，但**本批次新增资产自身的设计文档反向同步与 E2E 三方镜像未闭环**。

| 编号 | 级别 | 描述 | 证据 |
|------|------|------|------|
| N-P2-1 | P2 | **API 设计缺 §10.5**：新增端点 `GET /gamification/points-history` 在 `05-API详细设计.md` §10 无定义（现仅 10.1~10.4 四端点）——前端 services/gamification.ts:121 注释引用「API §10.5」**悬空引用**；请求参数（page/page_size le=50）/响应四键（total/page/page_size/items）/错误情况无契约承载，照文档维护会认为端点不存在 | API 设计 :2804-2899 四端点 vs router.py:75-89 |
| N-P2-2 | P2 | **DB 设计缺 point_transaction 表**：`04-数据库详细设计.md` §2 仅 2.15 user_points/2.16 checkin_record，新表无 §2.1x 定义、§6 索引清单缺 `idx_point_txn_user_created/idx_point_txn_user_event` 两条——迁移已落 alembic（d8e9f0a1b2c3）但 DB 契约文档零承载 | DB 设计 §2.15/2.16 + :2989-2995 索引清单 vs models/gamification.py:141-171 |
| N-P2-3 | P2 | **09-gamification 切片设计零同步**：backend.md 缺 PointTransaction schema/model/get_points_history 样例 + 端点清单仍为 4 端点；frontend.md §4.1 PointsCard 样例缺「最近积分动态」区块（新 UI 无设计承载）、§2 端点清单 5 端点、§7 缺 sourceOther/recentActivity 键、badges 页分类 chip 样例未跟——grep `points-history\|PointTransaction\|point_transaction` 全目录零命中 | 09-gamification/ 全目录 vs 实现五件 |
| N-P3-1 | P3 | **E2E mock 三方镜像未闭环**：base-mocks.ts 加了 `POINTS_HISTORY` 数据工厂但 mock-api.ts 注册表未注册 `GET /gamification/points-history` 路由（现仅 points/checkin-calendar/badges 三条）——常量成 E2E 死数据；a11y 扫描中 PointsCard 最近动态区因 404 恒渲染空态（a11y.spec 头注记「专有端点 404 兜底态纳入扫描」，不阻塞但**新 UI 区未入 axe 实渲染覆盖**）；badges mock 为空数组致 badge-category chip 同样未入覆盖。属 R2-P2-1/2 修复的 E2E 镜像半途 | base-mocks.ts:61-74 vs :207-209；a11y.spec.ts:63-64 |
| N-P3-2 | P3 | constants/gamification.ts:11 注记写「前端 **history 页**消费」——实际消费为 PointsCard **最近动态区**（工程无独立 history 页），注记与实现微偏 | constants/gamification.ts vs PointsCard.tsx:30-99 |

> **收尾状态（2026-11-16 批次H 提交前，5/5 全闭环）**：N-P2-1 ✅（API 设计补 §10.5 完整契约 + §10.4 补 category 字段说明）；N-P2-2 ✅（DB 设计新增 §2.35 point_transaction 表定义 + §6 索引两条 + §2 表数口径 39→40 + §5.7 补 PointTransaction model 样例）；N-P2-3 ✅（09-gamification backend.md 七处 + frontend.md 八处反向同步，端点清单 4→5、PointsCard 最近动态区样例、badges 分类 chip、i18n 双键、§9 验证清单 2 项）；N-P3-1 ✅（base-mocks 注册 `GET /gamification/points-history` + badges mock 改非空——4 徽章取后端种子实际 id/category〔first_analysis/analysis、streak_7/streak、match_50/match、analysis_10/analysis〕，chip 入 axe 覆盖零违规）；N-P3-2 ✅（constants 注记改「PointsCard 最近动态区」并如实标注原注记失实）。

### 8.4 后续修复计划

**批次H 收尾（提交前必做，预计 0.5 天）——✅ 2026-11-16 全部完成（1-4 落地；门禁全绿：tsc 0 错 / Jest 285 / E2E 7 spec 2.9m + axe 40 页零违规 / weapp 1.28MB / 后端 pytest 53 passed）**：
1. **新增资产设计文档反向同步**（N-P2-1/2/3，一次性闭合）：API 设计补 §10.5 端点契约（参数/响应四键/错误情况，样例镜像 PointsHistoryResponse）；DB 设计补 §2.1x point_transaction 表定义 + §6 索引两条 + §2.15 关联说明；09-gamification frontend.md（§2 端点清单 +1/§4.1 PointsCard 最近动态区块样例/§4.4 badges 分类 chip/§7 补 2 键）+ backend.md（schema/model/service/端点样例四段）。
2. **E2E 三方镜像闭环**（N-P3-1）：mock-api.ts 注册 `GET /gamification/points-history → POINTS_HISTORY`；badges mock 补含 category 的非空数据使 badge-category chip 入 axe 覆盖；training-flow 打卡流程（经 checkin-calendar 页）可选补最近动态 3 行断言。
3. constants 注记「history 页」→「PointsCard 最近动态区」（N-P3-2，1 行）。
4. **H5 dist 重建 + E2E 7 spec 全量回归 + weapp 构建门禁**（src 已改而 dist 陈旧，E2E 必须重建后跑）→ 提交批次H。

**批次I（P3 代码顺手修 + 测试基建，预计 1 天）——✅ 2026-11-16 完成（9/9，修复明细见 §8.1 批次I 行；门禁：tsc 0 错 / Jest 294 / E2E 7 spec 2.5m axe 零违规 / weapp 1.28MB / 后端 test_scoring 30 passed）**：
- R2-P3-1 report 页旧主色残留（`PRIMARY_RGB='230,57,70'` 九宫格深浅 + conic 首色 → `var(--color-primary)` 派生，同页图例已用 var——双源色值收敛；文档 03:836-837 同步）；
- R2-P3-2 DeletionCoolingBanner 配色回归（color-mix warning 琥珀底 → 设计口径 primary 8% 底 + 20% 边框，02-user:1365-1413）；
- R2-P3-3 feedback「准确」按钮提交前清空 feedbackComment（report/index.tsx:396-398）；
- R2-P3-4 E2E technique_stats mock 键集对齐 API §4.6（loop/smash/push/block → forehand_drive 等真键）；
- R2-P3-5 OverviewCards.tsx:56 批次标记笔误（批次C → 批次B/C）；
- R2-P3-6 scoring_service.py:135-136 注释修正（opponent_playing_style「setup 页消费」→「创建后回显、当前无页面渲染消费，前向交付字段」）；
- R2-P3-22 a11y-mocks 补 score_analysis 段（低成本扩大 axe 覆盖，报告建议优先项）；
- R2-P3-23 annotated_video_url 差异口径双侧留痕（analysis-flow 侧补对称注释）；
- R2-P3-24 i18nKeys.test 显式域断言扩批次E/F/G/H 新键。

**批次J（纯文档注记/回写批量，预计 0.5 天）**：R2-P3-8~21、25~27 共 16 项——03 时序组 7 项（tempo 派生定义/选择器/i18n 键集/清单顺序/验收口径自洽/NutUI 偏移注记/契约缺键）、04 组 2 项（NutUI 偏移族/redirectTo 注记）、00-home 资产承载、settings webviewFallback 键、community-tab TabBar 约束过时、DeletionCoolingBanner 公共组件回写（02-user/settings 两处）、01-auth 组 2 项（.json 样例格式/登录契约 needsConsent——防按文档重实现复现 P1 缺陷，报告建议优先）、界面设计 vs 总览背景/分割线双基准 + h5-bridge 39→40 口径、round1 报告批次归属表述（R2-P3-8）。

**收敛路径**：批次H 收尾提交 → 批次I → 批次J → **Round 3 轻量复审**（聚焦：批次H/G/H 收尾回归 + 本轮 P2 全量闭环验证 + N 系缺口清零核验；按 §七 建议 Round 3 后若两轮零 P2+ 可转入常规 CI 门禁态）。
