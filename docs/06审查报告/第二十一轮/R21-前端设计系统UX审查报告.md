# R21 前端设计系统 + UX 状态完整性审查报告

> **审查日期**：2026-10-19
> **审查范围**：13 份 frontend.md（00-home ~ 12-notification）+ 5 份 tab-pages + 总览 §3 + 13-infrastructure + R20 修复影响验证
> **审查方法**：grep 批量搜索 + 逐文件交叉比对 + R20 修复回归验证 + 10 维度一致性矩阵 + UX 状态完整性 11 项清单
> **审查代理**：R21 前端设计系统 + UX 状态完整性审查代理
> **基线**：R20-前端设计系统+UX 审查报告（2026-10-19）+ R20-API 端点级审查报告 + R20-综合审查报告
> **本轮目标**：连续第二轮无 P2+（在 R20 已达成"连续第一轮无 P2+"基线之上）

---

## 0. 审查汇总

### 0.1 总体统计

| 维度 | 项数 | 通过 | 偏差 | 待确认 |
|------|------|------|------|--------|
| R20 前端维度修复影响验证（5 项） | 5 | 3 | 2 | 0 |
| R20 新增组件 CSS 变量化审查（2 组件） | 2 | 1 | 1 | 0 |
| R20 新增组件 i18n 覆盖审查（2 组件） | 2 | 0 | 2 | 0 |
| 设计系统合规（10 维度 A-K） | 10 | 9 | 1（B 字号） | 0 |
| UX 状态完整性（Skeleton/Empty/catch/Toast） | 18 | 18 | 0 | 0 |
| 路由跳转路径匹配 | 32 | 30 | 2（总览未同步） | 0 |
| i18n 资源完整性（zh-CN/en-US） | 18 | 16 | 2（R20 新增缺失） | 0 |
| grep 模式执行（8 组） | 8 | 7 | 1（font-size 违规） | 0 |
| R20 修复编码完整性 | 1 | 0 | 1（§4.8 乱码） | 0 |
| **合计** | **106** | **94** | **12** | **0** |

### 0.2 P0-P3 分级汇总

| 优先级 | 数量 | 编号 | 说明 |
|--------|------|------|------|
| P0（阻断级） | 0 | — | 无阻断级问题 |
| P1（严重级） | 0 | — | 无严重级问题 |
| P2（一般级） | **3** | R21-P2-1 / R21-P2-2 / R21-P2-3 | R20-P1-3 + R20-P2-1 新增组件引入的字号违规 / 编码乱码 / i18n 缺失 |
| P3（建议级） | 2 | R21-P3-1 / R21-P3-2 | consent 页 i18n 文档不完整 + 总览 §3.4 路由表未同步 |

### 0.3 关键结论

> **🎯 前端维度连续第二轮无 P2+ ✗ 未达成**
>
> R21 前端设计系统 + UX 状态完整性审查覆盖 19 份文档、8 组 grep 搜索、10 个维度（A-K）、5 项 R20 修复影响验证、2 项 R20 新增组件专项审查，共 106 个检查点：
> - R20 前端维度 5 项修复中：3 项通过（R20-P1-2 字段重命名 + R20-P1-4 跳转逻辑 + R20-P3-2 后端无影响），2 项引入新问题（R20-P1-3 consent 页 + R20-P2-1 训练方案详情页）
> - **R20-P1-3 consent 同意页**：ConsentPage 组件实现 ✅，但 CSS 字号违规（L908 `16px` + L939 `14px` 不在规范集 {12,13,15,18,24,32}px）
> - **R20-P2-1 训练方案详情页**：TrainingPlanDetailPage 组件实现 ✅，但 §4.8 整段代码注释/说明/i18n 说明全部乱码（UTF-8 编码缺陷），8 个新 i18n keys 在 zh-CN.json/en-US.json 中全部缺失
> - 设计系统 10 维度：9 维度合规（A 色彩 / C 间距 / D 圆角 / E 阴影 / F 组件 / G 路由 / H 状态管理 / I i18n / J 无障碍 / K UX 状态），1 维度偏差（B 字号 — R20 新增组件 2 处违规）
> - UX 状态完整性维持 100%（18/18 切片含 Skeleton/Empty/catch/Toast 之一）
>
> **结论**：R20 报告宣称"连续第一轮无 P2+ ✅"在 R21 验证下未能延续。R20-P1-3 与 R20-P2-1 新增组件引入 3 项 P2 级问题，前端维度连续第二轮无 P2+ 目标**未达成**。

---

## 1. 执行摘要

R21 前端设计系统 + UX 状态完整性审查以 R20 报告为基线展开。R20 报告宣称"前端维度连续第一轮无 P2+ ✅"，新发现 0 项问题。本轮重点验证 R20 5 项修复对前端的影响 + 10 维度一致性维持 + R20 新增组件（consent 页 + 训练方案详情页）的 CSS 变量化与 i18n 覆盖。

**审查发现**：R20 修复虽在 API 维度闭环，但 R20-P1-3（consent 同意页）与 R20-P2-1（训练方案详情页）新增组件在前端维度引入了 3 项 P2 级问题：

1. **R21-P2-1**：consent 同意页 CSS 字号违规（`font-size: 16px` + `14px` 不在规范集 {12,13,15,18,24,32}px）。总览 §3.2 明确"禁止使用 9/14/22/48/56px 等非规范值"，并显式说明"不引入中间字号（如 14/16/20）以避免视觉层级模糊"。
2. **R21-P2-2**：07-training_advice/frontend.md §4.8（L1054-L1300）R20-P2-1 训练方案详情页整段代码注释、说明文本、i18n 条目说明全部为乱码 `????`（UTF-8 编码缺陷），违反"反幻觉"约束。
3. **R21-P2-3**：R20-P2-1 训练方案详情页使用的 8 个新 i18n keys（`training.planDetail`/`noSessions`/`completed`/`pending`/`scheduledDate`/`completedAt`/`markComplete`/`sessionCompleted`）在 zh-CN.json (L1720-L1764) 与 en-US.json (L1771-L1815) 中均未定义，运行时将显示 raw key。

**审查目标达成情况**：

- ❌ 连续第二轮无 P2+：未达成（R20 报告基线为"连续第一轮无 P2+"，R21 发现 3 项 P2 新问题）
- ✅ 10 维度一致性矩阵维持 9/10 合规（B 字号维度因 R20-P1-3 新增组件违规而失守）
- ✅ UX 状态完整性维持 100%（18/18 切片）
- ✅ 路径跳转路径匹配维持 30/32（2 项 P3 级总览 §3.4 路由表未同步）

---

## 2. R20 修复影响验证（5 项）

### 2.1 R20 前端维度修复影响验证表

| 编号 | R20 修复内容 | 验证位置 | 验证结果 | 影响 |
|------|------------|---------|---------|------|
| R20-P1-2 | `01-auth/frontend.md` checkConsentStatus 字段 requires_consent → consented | L101-L105 注释 + L269-L279 `checkConsentStatus` 实现 | ✅ 已落地 | 字段重命名 + 极性反转（`needs_consent = !consented`），store 与 API 一致 |
| R20-P1-3 | `01-auth/frontend.md` 新增 consent 同意页组件 + 路由 | L811 `ConsentPage` 组件 + L560 局部路由注册 | ⚠️ 组件实现 ✅，但 CSS 字号违规（见 R21-P2-1） | 引入 1 项 P2 + 1 项 P3 |
| R20-P1-4 | `01-auth/frontend.md` wechatLogin/phoneLogin 跳转逻辑修改 | L172-L175 wechatLogin + L196-L199 phoneLogin：`if (!consented) { Taro.navigateTo({ url: '/pages/auth/consent/index' }) }` | ✅ 已落地 | 跳转逻辑符合 consented=false 时引导至 consent 页设计 |
| R20-P2-1 | `07-training_advice/frontend.md` 新增训练方案详情页组件 + 路由 | L1069 `TrainingPlanDetailPage` 组件 + L1700 局部路由注册 | ⚠️ 组件实现 ✅，但 §4.8 整段乱码 + i18n 缺失（见 R21-P2-2/P2-3） | 引入 2 项 P2 + 1 项 P3 |
| R20-P3-2 | `03-video_analysis/backend.md` L221/L325 index=True 移除 | 后端维度，前端无影响 | ✅ 无前端影响 | — |

**R20 修复影响验证结论**：5 项中 3 项通过（R20-P1-2/P1-4/P3-2），2 项引入新问题（R20-P1-3 + R20-P2-1）。R20 修复落地时未同步进行前端维度回归审查，导致新增组件违反设计系统字号规范与 i18n 资源完整性约束。

---

## 3. 10 维度一致性矩阵（A-K）

| 维度 | 检查点 | grep/验证结果 | 合规判定 | 备注 |
|------|--------|-------------|----------|------|
| A. 色彩 | 硬编码色值 | G1: 90 处。85 处在总览 :root CSS 变量定义 + 审查跟踪表 + WCAG AA 对比度参考；5 处在视觉验证清单；Taro app.config.ts tabBar 颜色（4 处，Taro 配置要求原始值） | ✅ 合规 | 所有组件代码使用 `var(--color-*)`；R20 新增 consent 页 CSS 全部使用 `var(--color-*)` |
| **B. 字体** | **font-size 值** | **G4: 全切片扫描违规 2 处：`01-auth/frontend.md` L908 `font-size: 16px`（.policy-title，consent 页）+ L939 `font-size: 14px`（.btn-refuse，consent 页），均不在规范集 {12,13,15,18,24,32}px** | **❌ 不合规** | **R20-P1-3 新增 consent 页引入 2 处违规字号（详见 §4.1）。R19 基线 0 处违规，R20 引入 2 处** |
| C. 间距 | var(--spacing-*) 使用 | G10: 100+ 处 var(--spacing-*)；间距属性硬编码 px = 0 处 | ✅ 100% 合规 | R9+R17 共 431 处替换完成。R20 新增组件（consent + 训练方案详情页）全部使用 var(--spacing-*) |
| D. 圆角 | border-radius 值 | G5: `\d+px` 匹配 0 处；12 处 `50%`（圆形）或 `0`（sharp corner）；100+ 处 `var(--radius-md/sm)` | ✅ 100% 合规 | R20 新增 consent 页 L902 `border-radius: var(--radius-md)` + L931/L937 `var(--radius-sm)` 全部变量化 |
| E. 阴影 | box-shadow 值 | G6: 36 处全部 `var(--shadow-card)` + 1 处 `var(--shadow-card-top)`（R19-P3-1）；0 处硬编码 | ✅ 100% 合规 | R20 新增 consent 页 L904 `box-shadow: var(--shadow-card)` + 训练方案详情页 L1610/L1632 `var(--shadow-card)` 全部变量化 |
| F. 组件 | Dialog/Popup 使用 | G11: Dialog 1 文件（user L703 注销确认，合理）；Popup 7 文件；R20 新增 consent 页使用 `Toast` 组件 | ✅ 合规 | R20 新增组件未引入 Dialog/Popup 违规 |
| G. 路由 | navigateTo 路径 | G7: 32 处 navigateTo + 5 处 redirectTo + 8 处 switchTab。逐条与总览 §3.4 L185-L225 路由表交叉验证 | ⚠️ 30/32 | R20 新增 `pages/auth/consent/index`（01-auth L560 局部注册）+ `pages/training/plans/[plan_id]/index`（07-training L1700 局部注册）**总览 §3.4 路由表未同步**（见 R21-P3-2） |
| H. 状态管理 | Zustand 使用 | G8: 18 文件 `create<...>` / `create(...)`：13 frontend.md + match-tab + onboarding；training-tab 显式"不需要独立 Store"；settings/community-tab 复用 useUserStore | ✅ 100% 合规 | R20 新增 consent 页使用 useAuthStore + 训练方案详情页使用 useTrainingStore，符合规范 |
| I. i18n | t('key') 使用 + zh-CN/en-US 资源 | G12: 全部 18 切片含 2 处 i18n 资源文件引用；JSX 硬编码中文 = 0 处。但 R20-P2-1 训练方案详情页 8 个新 i18n keys 在 zh-CN.json/en-US.json 中均未定义（详见 §4.2） | ⚠️ 16/18 | R20 新增 consent 页 7 个新 key 仅文档列出 zh-CN 未列出 en-US（R21-P3-1）；训练方案详情页 8 个新 key 完全缺失（R21-P2-3） |
| J. 无障碍 | aria-label/role/WCAG AA | G9: 5 处全部在总览 §3.8 设计规范中，切片代码 0 处 ARIA 实现（R19-P3-4 已知推迟项） | ✅ 已知推迟项 | R19-P3-4 修复后开发阶段实现清单完整（含 CI 阻塞 @axe-core/playwright / eslint-plugin-jsx-a11y），R20 新增组件未引入新无障碍违规（亦未补齐 ARIA） |
| K. UX 状态完整性 | Skeleton/Empty/catch/Toast | 14/18 切片含 Skeleton；8 切片含 Empty；14 切片含 catch；Toast 在 R20 新增组件中广泛使用（consent + 训练方案详情页） | ✅ 100% 合规 | R20-P1-3 consent 页 L814-L815 使用 Toast + R20-P2-1 训练方案详情页 L1073-L1074 Toast + L1096-L1112 Skeleton + L1121 Empty，UX 状态完整性维持 |

---

## 4. R20 新增组件专项审查

### 4.1 R20-P1-3 consent 同意页审查

**组件位置**：`01-auth/frontend.md` L780-L942

**审查项与结果**：

| 检查项 | 验证位置 | 结果 | 说明 |
|--------|---------|------|------|
| ConsentPage 组件实现 | L811 `export default function ConsentPage()` | ✅ | 函数组件 + TypeScript + useTranslation |
| 路由局部注册 | L560 `'pages/auth/consent/index'` | ✅ | 01-auth/frontend.md §6 局部 app.config.ts 已注册 |
| 路由总览同步 | 总览 §3.4 L185-L225 | ❌ | 总览 §3.4 路由表未注册 `pages/auth/consent/index`（R21-P3-2） |
| CSS 间距变量化 | L882/L883/L895/L896/L903/L911/L923/L926/L932/L937 全部使用 `var(--spacing-*)` | ✅ | 间距属性 0 处硬编码 |
| CSS 圆角变量化 | L902 `var(--radius-md)` + L931/L937 `var(--radius-sm)` | ✅ | 圆角 0 处硬编码 |
| CSS 阴影变量化 | L904 `box-shadow: var(--shadow-card)` | ✅ | 阴影 0 处硬编码 |
| CSS 色彩变量化 | L877/L891/L901/L910/L918/L929/L930/L936 全部使用 `var(--color-*)` | ✅ | 色彩 0 处硬编码 |
| **CSS 字号合规** | **L888 `font-size: 18px` ✅ + L908 `font-size: 16px` ❌ + L916 `font-size: 13px` ✅ + L933 `font-size: 15px` ✅ + L939 `font-size: 14px` ❌** | **❌** | **L908（.policy-title）+ L939（.btn-refuse）2 处违规字号（详见 R21-P2-1）** |
| i18n t('key') 使用 | L803/L804/L823/L830/L836/L851/L859 共 7 处 `t('auth.*')` 调用 | ✅ | 组件代码全部使用 i18n |
| i18n 资源 zh-CN | L944-L951 文档列出 7 个 zh-CN 新 key | ✅ | 文档列出 zh-CN 翻译 |
| **i18n 资源 en-US** | L944-L951 文档**未列出** en-US 对应翻译 | **❌** | **文档覆盖不完整（R21-P3-1）** |
| UX 状态完整性 | L814-L815 Toast + L818-L826 同意/拒绝按钮 | ✅ | 含 Toast 错误提示 |
| 路由跳转路径匹配 | L821 `Taro.switchTab({ url: '/pages/home/index' })` ✅ | ✅ | 路径已注册 |

**consent 页审查结论**：12 项检查中 9 项通过，3 项偏差（1 P2 字号 + 1 P3 i18n en-US 文档 + 1 P3 路由总览同步）。

### 4.2 R20-P2-1 训练方案详情页审查

**组件位置**：`07-training_advice/frontend.md` §4.8 L1054-L1300

**审查项与结果**：

| 检查项 | 验证位置 | 结果 | 说明 |
|--------|---------|------|------|
| TrainingPlanDetailPage 组件实现 | L1069 `export default function TrainingPlanDetailPage()` | ✅ | 函数组件 + TypeScript + useTranslation |
| 路由局部注册 | L1700 `'pages/training/plans/[plan_id]/index'` | ✅ | 07-training_advice/frontend.md §6 局部 app.config.ts 已注册 |
| 路由总览同步 | 总览 §3.4 L185-L225 | ❌ | 总览 §3.4 路由表未注册 `pages/training/plans/[plan_id]/index`（R21-P3-2） |
| **代码注释/说明编码完整性** | **§4.8 L1054-L1300 整段：标题 `## 4.8 ????????R20-P2-1??????? + ?????`、注释 `**????**`、L1292-L1300 i18n 说明全部乱码** | **❌** | **整段 UTF-8 编码缺陷（R21-P2-2）** |
| CSS 间距变量化 | L1211/L1213/L1220/L1226/L1237/L1241/L1258/L1268/L1273/L1278/L1284/L1287 全部 `var(--spacing-*)` | ✅ | 间距属性 0 处硬编码 |
| CSS 圆角变量化 | L1242 `var(--radius-md) !important` | ✅ | 圆角 0 处硬编码 |
| CSS 色彩变量化 | L1207/L1212/L1219/L1230/L1253/L1263/L1272 全部 `var(--color-*)` | ✅ | 色彩 0 处硬编码 |
| CSS 字号合规 | L1217 `18px` ✅ + L1229 `12px` ✅ + L1251 `15px` ✅ + L1262 `12px` ✅ + L1271 `13px` ✅ | ✅ | 字号全部在规范集内 |
| i18n t('key') 使用 | L1100/L1119/L1121/L1135/L1154/L1156/L1161/L1165/L1185/L1090 共 10 处 `t('training.*')` 调用 | ✅ | 组件代码全部使用 i18n |
| **i18n 资源 zh-CN 定义** | **zh-CN.json L1720-L1764 中 `training` 对象未定义 8 个新 key（`planDetail`/`noSessions`/`completed`/`pending`/`scheduledDate`/`completedAt`/`markComplete`/`sessionCompleted`）** | **❌** | **8 个 i18n key 完全缺失（R21-P2-3）** |
| **i18n 资源 en-US 定义** | **en-US.json L1771-L1815 中 `training` 对象同样未定义 8 个新 key** | **❌** | **8 个 i18n key 完全缺失（R21-P2-3）** |
| UX 状态完整性 | L1073-L1074 Toast + L1096-L1112 Skeleton + L1115-L1124 Empty | ✅ | UX 状态完整 |
| store action 集成 | L1081 `store.fetchTrainingSessions(planId)` + L1087 `store.completeTrainingSession(planId, sessionId)` | ✅ | store 集成正确 |
| API §8.7 / §8.8 端点对应 | L208 `listTrainingSessions` → `/training/plans/${planId}/sessions` + L221 `completeTrainingSession` → `/training/plans/${planId}/sessions/${sessionId}/complete` | ✅ | API 契约一致 |

**训练方案详情页审查结论**：13 项检查中 9 项通过，4 项偏差（1 P2 编码乱码 + 1 P2 i18n zh-CN 缺失 + 1 P2 i18n en-US 缺失 + 1 P3 路由总览同步）。

---

## 5. UX 状态完整性

### 5.1 18 切片 UX 状态完整性矩阵

| 切片 | Skeleton | Empty | catch | Toast | 备注 |
|------|---------|-------|-------|-------|------|
| 00-home | ✅ | ✅ | ✅ | ✅ | L633 navigateTo 参数 `?report_id=` 一致（R19-P1-1 修复维持） |
| 01-auth | — | — | ✅ | ✅ | R20 新增 consent 页 L814 Toast ✅；L818-L826 同意/拒绝按钮 |
| 02-user | ✅ | ✅ | ✅ | ✅ | rating-history Empty（R19-P2-1 修复维持） |
| 03-video_analysis | ✅ | ✅ | ✅ | ✅ | report-list Empty（R19-P2-2 修复维持） + L1644 顶部阴影 `var(--shadow-card-top)`（R19-P3-1 修复维持） |
| 04-scoring | ✅ | — | ✅ | ✅ | — |
| 05-match_data | ✅ | — | ✅ | ✅ | — |
| 06-data_dashboard | ✅ | — | ✅ | ✅ | — |
| 07-training_advice | ✅ | ✅ | ✅ | ✅ | R20 新增训练方案详情页 L1096 Skeleton + L1121 Empty + L1073 Toast（注：§4.8 注释乱码不影响代码本身合规） |
| 08-progress_analysis | ✅ | — | ✅ | ✅ | 6 个 store 方法 catch 块（R19-P1-3 修复维持） |
| 09-gamification | ✅ | ✅ | ✅ | ✅ | badges Empty（R19-P2-3 修复维持） |
| 10-membership | ✅ | — | ✅ | ✅ | — |
| 11-payment | ✅ | — | ✅ | ✅ | — |
| 12-notification | ✅ | — | ✅ | ✅ | — |
| 13-infrastructure | — | — | — | — | 后端切片，无前端 UX 状态 |
| 14a training-tab | ✅ | — | ✅ | ✅ | — |
| 14b match-tab | ✅ | — | ✅ | ✅ | — |
| 14c community-tab | — | ✅ | — | — | Phase 2+ 占位页 |
| 14d onboarding | ✅ | — | ✅ | ✅ | — |
| 14e settings | — | — | ✅ | ✅ | 复用 useUserStore |

**UX 状态完整性结论**：18 切片 UX 状态完整性维持 100% 合规。R20 新增 consent 页 + 训练方案详情页均正确实现 Skeleton/Empty/Toast，未引入 UX 状态回归。

### 5.2 11 项 UX 状态完整性与性能优化清单

| # | 检查项 | 验证结果 | 备注 |
|---|--------|----------|------|
| 1 | Skeleton 加载占位 | 14/18 切片 ✅ | R20 新增训练方案详情页 L1096 Skeleton ✅ |
| 2 | Empty 空状态组件 | 8 切片 ✅ | R20 新增训练方案详情页 L1121 Empty ✅ |
| 3 | catch 错误捕获 | 14 切片 ✅ | R20 新增 consent 页 store L255 catch ✅ + 训练方案详情页 store L426/L446 catch ✅ |
| 4 | Toast 反馈 | 18 切片 ✅ | R20 新增 consent 页 L863 Toast + 训练方案详情页 L1193 Toast ✅ |
| 5 | 图片 lazy-load | 切片代码 0 处实现 | R19-P3-2 推迟项（开发阶段实现清单已闭环） |
| 6 | IntersectionObserver | 切片代码 0 处实现 | R19-P3-2 推迟项 |
| 7 | virtualList 长列表 | 切片代码 0 处实现 | R19-P3-2 推迟项 |
| 8 | debounce/throttle | 切片代码 0 处实现 | R19-P3-2 推迟项 |
| 9 | ARIA 属性 | 切片代码 0 处实现 | R19-P3-4 推迟项（开发阶段 CI 阻塞已闭环） |
| 10 | WCAG 2.2 SC 2.5.8 触摸目标 | 总览 §3.8 规范已定义 | 切片代码未显式实现，由 NutUI 组件库默认满足 |
| 11 | 反幻觉约束 | 18 切片 ✅ | 用户可见文本全部 `t('key')`（注：07-training_advice §4.8 注释乱码属文档编码缺陷，非反幻觉违规） |

---

## 6. 新发现 P0-P3 分级

### 6.1 P0 级（阻断级）

**无 P0 级问题。**

### 6.2 P1 级（严重级）

**无 P1 级问题。**

### 6.3 P2 级（一般级）

#### R21-P2-1：R20-P1-3 consent 同意页 CSS 字号违规

- **位置**：`docs/06垂直模块前后端切片设计/01-auth/frontend.md` L908 + L939
- **现象**：
  - L908 `.policy-title { font-size: 16px; }`（consent 同意页隐私政策标题）
  - L939 `.btn-refuse { font-size: 14px; }`（consent 同意页"拒绝"按钮）
- **违规依据**：总览 §3.2 :root L145-L150 定义 6 级 `--fs-*` 变量为 `{12, 13, 15, 18, 24, 32}px`，并显式说明"不引入中间字号（如 14/16/20）以避免视觉层级模糊"。`16px` 与 `14px` 均不在规范集内。
- **影响**：R20 报告 G4 grep 宣称"364 处全部使用规范集"，R20-P1-3 修复时新增 2 处违规字号，使 R19 基线 0 处违规退化为 R20+R21 2 处违规。设计系统字号规范在 R20-P1-3 修复中被破坏。
- **修复方案**：
  - L908：`font-size: 16px;` → `font-size: 15px;`（或 `font-size: var(--fs-body);`）
  - L939：`font-size: 14px;` → `font-size: 13px;`（或 `font-size: var(--fs-small);`）
- **优先级理由**：违反设计系统硬约束（字号规范集），但仅影响新增 consent 页视觉层级，不影响功能，定为 P2。

#### R21-P2-2：R20-P2-1 训练方案详情页 §4.8 整段乱码

- **位置**：`docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` §4.8 L1054-L1300
- **现象**：
  - L1054 章节标题：`## 4.8 ????????R20-P2-1??????? + ?????`
  - L1056 章节说明：`> **????**??? trainingStore ? ...`
  - L1060 组件注释：`// R20-P2-1: ??????? UI ??`
  - L1078/L1085/L1089/L1090/L1126/L1133/L1139/L1147/L1150/L1176/L1292-L1300 等多处中文注释/字符串说明全部为 `?` 字符
  - L1292-L1300 i18n 新增条目说明：`> - zh-CN: training.planDetail = "??????"` 等 8 条全部乱码
- **违规依据**：违反反幻觉约束"ALL 用户可见文本必须使用 t('key')"与文档可读性要求。UTF-8 编码错误导致整段中文丢失，无法验证 i18n 设计意图。
- **影响**：
  1. §4.8 章节标题、说明、注释无法阅读，影响审查与维护
  2. i18n 新增条目说明（L1292-L1300）全部乱码，无法验证 zh-CN 翻译内容是否合理
  3. 代码字符串中的中文（如 L1139 `// R20-P2-1: is_completed ????`）乱码，影响代码可读性
- **修复方案**：将 `07-training_advice/frontend.md` §4.8（L1054-L1300）整段以 UTF-8 编码重新写入，恢复以下内容：
  - L1054 标题：`## 4.8 训练方案详情页（R20-P2-1 新增组件） + 样式`
  - L1056 说明：`> **定位**：trainingStore 的 fetchTrainingSessions / completeTrainingSession actions 的 UI 层落地，展示"训练单列表"+ 完成按钮 + 进度 Tab 顶部`
  - L1060 注释：`// R20-P2-1: 训练方案详情页 UI 组件`
  - L1292-L1300 i18n 条目：恢复 8 条 zh-CN 翻译（`planDetail`="训练方案详情"、`noSessions`="暂无训练单" 等）
- **优先级理由**：整段乱码导致文档不可读 + i18n 设计意图无法验证，但组件代码本身（TSX/SCSS）功能完整，定为 P2。

#### R21-P2-3：R20-P2-1 训练方案详情页 8 个 i18n keys 在资源文件中缺失

- **位置**：
  - 组件引用：`docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` L440/L1090/L1100/L1119/L1121/L1135/L1154/L1156/L1161/L1165/L1185（共 10 处 `t('training.*')` 调用）
  - 资源缺失：`zh-CN.json` L1720-L1764 `training` 对象 + `en-US.json` L1771-L1815 `training` 对象
- **现象**：R20-P2-1 训练方案详情页代码使用 8 个新 i18n keys，但 zh-CN.json/en-US.json 中 `training` 对象未定义这些 keys：
  | i18n key | 代码引用位置 | zh-CN.json 定义 | en-US.json 定义 |
  |----------|------------|----------------|-----------------|
  | `training.planDetail` | L1100/L1119/L1135 | ❌ 未定义 | ❌ 未定义 |
  | `training.noSessions` | L1121 | ❌ 未定义 | ❌ 未定义 |
  | `training.completed` | L1154 | ❌ 未定义 | ❌ 未定义 |
  | `training.pending` | L1156 | ❌ 未定义 | ❌ 未定义 |
  | `training.scheduledDate` | L1161 | ❌ 未定义 | ❌ 未定义 |
  | `training.completedAt` | L1165 | ❌ 未定义 | ❌ 未定义 |
  | `training.markComplete` | L1185 | ❌ 未定义 | ❌ 未定义 |
  | `training.sessionCompleted` | L440/L1090 | ❌ 未定义 | ❌ 未定义 |
- **违规依据**：违反反幻觉约束"ALL 用户可见文本必须使用 t('key')，禁止硬编码字符串"——i18n key 已使用但资源未定义，运行时 react-i18next 将显示 raw key（如 `training.planDetail`）而非翻译文本。
- **影响**：训练方案详情页所有用户可见文本（页面标题、空状态、完成标签、待完成标签、计划日期、完成时间、标记完成按钮、完成 Toast）在运行时全部显示为 raw key，严重影响用户体验。
- **修复方案**：在 `07-training_advice/frontend.md` §7 i18n 条目（zh-CN.json L1720-L1764 + en-US.json L1771-L1815）的 `training` 对象内补充 8 个新 key 双语翻译：

  zh-CN.json（在 L1763 `"reEvaluateFailed": "重新评估失败"` 后追加）：
  ```json
  "planDetail": "训练方案详情",
  "noSessions": "暂无训练单",
  "completed": "已完成",
  "pending": "待完成",
  "scheduledDate": "计划日期",
  "completedAt": "完成时间",
  "markComplete": "标记完成",
  "sessionCompleted": "训练单已完成，获得 {{points}} 积分",
  ```

  en-US.json（在 L1814 `"reEvaluateFailed": "Re-evaluation failed"` 后追加）：
  ```json
  "planDetail": "Training Plan Detail",
  "noSessions": "No training sessions",
  "completed": "Completed",
  "pending": "Pending",
  "scheduledDate": "Scheduled Date",
  "completedAt": "Completed At",
  "markComplete": "Mark Complete",
  "sessionCompleted": "Session completed, earned {{points}} points",
  ```
- **优先级理由**：i18n 资源缺失导致运行时显示 raw key，影响 8 个用户可见文本，但仅限 R20-P2-1 新增组件，不影响存量功能，定为 P2。

### 6.4 P3 级（建议级）

#### R21-P3-1：R20-P1-3 consent 页 i18n 文档未列出 en-US 翻译

- **位置**：`docs/06垂直模块前后端切片设计/01-auth/frontend.md` L944-L951
- **现象**：R20-P1-3 consent 同意页 i18n 新增条目说明仅列出 zh-CN 7 个新 key（`privacyConsentTitle`/`privacyPolicyTitle`/`privacyPolicyBody`/`agreeAndContinue`/`refuse`/`consentRequired`/`consentFailed`），未列出 en-US 对应翻译。
- **违规依据**：与 01-auth/frontend.md §7 i18n 条目（L574-L618 zh-CN + en-US 双语对照）不一致，consent 页 i18n 说明缺乏 en-US 部分。
- **修复方案**：在 L951 后补充 en-US 7 个新 key 对应翻译：
  ```
  > - en-US: `auth.privacyConsentTitle` = "Privacy Consent"
  > - en-US: `auth.privacyPolicyTitle` = "Privacy Policy"
  > - en-US: `auth.privacyPolicyBody` = "(Privacy policy content)"
  > - en-US: `auth.agreeAndContinue` = "Agree and Continue"
  > - en-US: `auth.refuse` = "Refuse"
  > - en-US: `auth.consentRequired` = "You must agree to the privacy policy to continue"
  > - en-US: `auth.consentFailed` = "Failed to record consent, please try again"
  ```
- **优先级理由**：文档完整性问题，不影响运行时（实际项目应将翻译写入 en-US.json），定为 P3。

#### R21-P3-2：总览 §3.4 路由表未同步注册 R20 新增 2 条路由

- **位置**：`docs/06垂直模块前后端切片设计/00-垂直切片设计总览.md` §3.4 L185-L225
- **现象**：总览 §3.4 app.config.ts 路由表未注册 R20 新增的 2 条路由：
  - `pages/auth/consent/index`（R20-P1-3 consent 同意页，01-auth/frontend.md L560 局部已注册）
  - `pages/training/plans/[plan_id]/index`（R20-P2-1 训练方案详情页，07-training_advice/frontend.md L1700 局部已注册）
- **违规依据**：总览 §3.4 L182 明确"所有切片的 Tab Bar 配置必须以以下 app.config.ts 为准，**不允许** 各模块自行定义 `tabBar.list`"，路由表应统一在总览 §3.4 维护。
- **影响**：路由在切片局部已注册，不影响运行；但总览 §3.4 路由表与切片局部不一致，违反"统一路由表"原则，影响后续审查与维护。
- **修复方案**：
  - 总览 §3.4 L196 `'pages/auth/login/index',` 后追加：`'pages/auth/consent/index',   // R20-P1-3: 隐私政策同意页`
  - 总览 §3.4 L212 `'pages/training/templates/detail/index',` 后追加：`'pages/training/plans/[plan_id]/index',  // R20-P2-1: 训练方案详情页`
- **优先级理由**：路由表局部与全局不同步，但运行时无影响（局部已注册），定为 P3。

---

## 7. 修复跟踪表与累计计数

### 7.1 R21 修复跟踪表

| 编号 | 优先级 | 修复内容 | 修复位置 | 状态 |
|------|--------|----------|---------|------|
| R21-P2-1 | P2 | consent 页 CSS 字号 16px→15px + 14px→13px | `01-auth/frontend.md` L908 + L939 | ⏳ 待修复 |
| R21-P2-2 | P2 | 训练方案详情页 §4.8 整段 UTF-8 重写 | `07-training_advice/frontend.md` L1054-L1300 | ⏳ 待修复 |
| R21-P2-3 | P2 | 训练方案详情页 8 个新 i18n key 双语补充 | `07-training_advice/frontend.md` zh-CN.json L1763 后 + en-US.json L1814 后 | ⏳ 待修复 |
| R21-P3-1 | P3 | consent 页 i18n 文档补充 en-US 翻译 | `01-auth/frontend.md` L951 后 | ⏳ 待修复 |
| R21-P3-2 | P3 | 总览 §3.4 路由表同步注册 R20 新增 2 条路由 | `00-垂直切片设计总览.md` L196 后 + L212 后 | ⏳ 待修复 |

### 7.2 累计修复计数

| 轮次 | 本轮修复 | 累计修复 | 说明 |
|------|---------|---------|------|
| 第一轮~第十七轮 | 705 | 705 | — |
| 第十八轮 | 44 + 11 推迟项闭环 | 854 | — |
| 第十九轮（前端线） | 5（新发现修复） | 880（含其他维度） | P1×3 + P2×3 + P3×4 中修复 5 项 |
| 第二十轮（前端线） | 0（R19 修复落地） | 880 | R19-P1-1~3 + P2-1~3 + P3-1~4 全部修复落地 |
| **第二十一轮（本轮，前端线）** | **5（待修复）** | **885（待修复后）** | R21-P2×3 + P3×2，均为 R20 新增组件引入的回归问题 |

> **说明**：R21 前端线新发现 5 项问题（P2×3 + P3×2），全部源自 R20-P1-3 consent 同意页与 R20-P2-1 训练方案详情页新增组件。R20 报告宣称"连续第一轮无 P2+ ✅"在 R21 验证下未能延续，前端维度连续第二轮无 P2+ 目标**未达成**。

### 7.3 R20 修复回归分析

| R20 修复项 | R20 报告状态 | R21 验证结果 | 回归原因 |
|-----------|-------------|-------------|---------|
| R20-P1-2（requires_consent → consented） | ✅ 已修复 | ✅ 维持 | — |
| R20-P1-3（consent 同意页组件 + 路由） | ✅ 已修复 | ⚠️ 引入 R21-P2-1 + R21-P3-1 + R21-P3-2 | R20 修复时未同步进行 CSS 字号合规审查 + i18n 文档完整性审查 + 总览路由表同步 |
| R20-P1-4（wechatLogin/phoneLogin 跳转逻辑） | ✅ 已修复 | ✅ 维持 | — |
| R20-P2-1（训练方案详情页组件 + 路由） | ✅ 已修复 | ⚠️ 引入 R21-P2-2 + R21-P2-3 + R21-P3-2 | R20 修复时存在 UTF-8 编码缺陷 + 未同步补充 i18n 资源 + 未同步总览路由表 |
| R20-P3-2（video_analysis index=True 移除） | ✅ 已修复 | ✅ 无前端影响 | — |

**R20 修复回归根因**：R20 修复时仅关注 API 契约一致性（R20-API 端点级审查报告视角），未同步进行前端设计系统 + UX 状态完整性回归审查。R20 前端报告虽宣称"0 项新发现"，但实际未覆盖 R20-P1-3/P2-1 新增组件的 CSS 字号合规、i18n 资源完整性、文档编码完整性三项检查。

---

## 8. grep 执行结果汇总（8 组）

| 搜索组 | 匹配数 | R21 关键发现 |
|--------|--------|--------------|
| G1 硬编码色值 | 90 | 全部在定义/注释/验证清单中，组件代码 0 处 ✅ |
| G2 border-radius px | 0 | 圆角硬编码 0 处，全部 50% 或 var(--radius-*) ✅ |
| G3 box-shadow 非 var | 0 | 阴影硬编码 0 处，全部 var(--shadow-card) 或 var(--shadow-card-top) ✅ |
| **G4 font-size 违规值（9/14/16/20/22/28/36/48/56）px** | **2** | **`01-auth/frontend.md` L908 `16px` + L939 `14px`（R20-P1-3 consent 页违规）❌** |
| G5 navigateTo 路径 | 32 | 30 处路径在总览 §3.4 注册 ✅；2 处 R20 新增路径总览未同步（R21-P3-2） |
| G6 Zustand create | 18 文件 | 全部使用 `create` from 'zustand' ✅ |
| G7 aria/role | 5 | 全部在总览 §3.8 规范中，切片 0 处（R19-P3-4 已知推迟项） |
| G8 i18n key 资源覆盖 | 8 缺失 | R20-P2-1 训练方案详情页 8 个新 key 在 zh-CN.json/en-US.json 中均未定义（R21-P2-3）❌ |

---

## 9. 审查结论

R21 前端设计系统 + UX 状态完整性审查覆盖 19 份文档、8 组 grep 搜索、10 个维度（A-K）、5 项 R20 修复影响验证、2 项 R20 新增组件专项审查、11 项 UX 状态完整性与性能优化清单，共 106 个检查点中 94 个通过、12 个偏差（含 3 项 P2 + 2 项 P3）。

**R20 修复影响验证结论**：5 项 R20 修复中 3 项维持（R20-P1-2/P1-4/P3-2），2 项引入新问题（R20-P1-3 + R20-P2-1）。

**新发现 P0/P1/P2/P3 问题**：
- P0×0 + P1×0 + **P2×3** + P3×2
- 3 项 P2 问题全部源自 R20 新增组件：
  - R21-P2-1：consent 页 CSS 字号 16px/14px 违规（不在规范集 {12,13,15,18,24,32}px）
  - R21-P2-2：训练方案详情页 §4.8 整段 UTF-8 编码乱码
  - R21-P2-3：训练方案详情页 8 个新 i18n keys 在 zh-CN.json/en-US.json 中完全缺失
- 2 项 P3 问题：
  - R21-P3-1：consent 页 i18n 文档未列出 en-US 翻译
  - R21-P3-2：总览 §3.4 路由表未同步注册 R20 新增 2 条路由

**前端维度连续第二轮无 P2+ 目标**：**未达成** ❌

R20 报告宣称"前端维度连续第一轮无 P2+ ✅"（R19 基线 P2×3 → R20 P2=0），但 R20 修复时未同步进行前端设计系统 + UX 状态完整性回归审查，导致 R20-P1-3 + R20-P2-1 新增组件引入 3 项 P2 级回归问题。前端维度连续第二轮无 P2+ 目标在 R21 验证下**未能延续**。

**设计系统 10 维度状态**：
- 9 维度维持合规（A 色彩 / C 间距 / D 圆角 / E 阴影 / F 组件 / G 路由 / H 状态管理 / I i18n / J 无障碍 / K UX 状态）
- 1 维度失守（B 字号 — R20-P1-3 consent 页 2 处违规字号）

**修复建议优先级**：
1. 立即修复 R21-P2-3（i18n 资源缺失，影响运行时显示）+ R21-P2-2（编码乱码，影响文档可读性）
2. 同步修复 R21-P2-1（字号违规，影响设计系统合规性）
3. 后续修复 R21-P3-1 + R21-P3-2（文档完整性与路由表同步）

**R22 验证重点**：
1. R21-P2-1 修复后 consent 页 CSS 字号合规性回归
2. R21-P2-2 修复后 §4.8 整段中文恢复
3. R21-P2-3 修复后 8 个 i18n key 双语资源定义
4. R21-P3-2 修复后总览 §3.4 路由表与切片局部一致性

---

*审查完成。报告归档路径：`docs/07审查报告/第二十一轮/R21-前端设计系统UX审查报告.md`*
