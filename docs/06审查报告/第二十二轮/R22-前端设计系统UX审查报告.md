# R22 前端设计系统 + UX 状态完整性审查报告

> **审查日期**：2026-10-19
> **审查范围**：13 份 frontend.md（00-home ~ 12-notification）+ 5 份 tab-pages + 总览 §3 + 13-infrastructure + R21 修复回归验证
> **审查方法**：grep 批量搜索 + 逐文件交叉比对 + R21 修复回归验证 + 10 维度一致性矩阵 + UX 状态完整性 11 项清单
> **审查代理**：R22 前端设计系统 + UX 状态完整性审查代理
> **基线**：R21-前端设计系统+UX 审查报告（2026-10-19）+ R21-综合审查报告 + R21-API 端点级审查报告
> **本轮目标**：连续两轮无 P2+（在 R21 已识别 3 项 P2 修复落地后的新第一轮基线）

---

## 0. 审查汇总

### 0.1 总体统计

| 维度 | 项数 | 通过 | 偏差 | 待确认 |
|------|------|------|------|--------|
| R21 5 项修复回归验证（3 P2 + 2 P3） | 5 | 5 | 0 | 0 |
| R21 修复引入的新问题排查 | 5 | 3 | 2 | 0 |
| 设计系统合规（10 维度 A-K） | 10 | 9 | 1（B 字号） | 0 |
| UX 状态完整性（Skeleton/Empty/catch/Toast） | 18 | 18 | 0 | 0 |
| 路由跳转路径匹配 | 32 | 32 | 0 | 0 |
| i18n 资源完整性（zh-CN/en-US） | 18 | 17 | 1（sessionCompleted 插值缺失） | 0 |
| grep 模式执行（8 组） | 8 | 7 | 1（font-size 违规） | 0 |
| **合计** | **96** | **91** | **5** | **0** |

### 0.2 P0-P3 分级汇总

| 优先级 | 数量 | 编号 | 说明 |
|--------|------|------|------|
| P0（阻断级） | 0 | — | 无阻断级问题 |
| P1（严重级） | 0 | — | 无严重级问题 |
| P2（一般级） | **2** | R22-P2-1 / R22-P2-2 | R21 修复 UTF-8 乱码 + 补 i18n key 时引入的回归（.session-index 字号违规 + sessionCompleted 缺 {{points}} 插值） |
| P3（建议级） | 0 | — | 无 P3 级新发现 |

### 0.3 关键结论

> **🎯 前端维度连续两轮无 P2+ ✗ 未达成（新第一轮基线即失守）**
>
> R22 前端设计系统 + UX 状态完整性审查覆盖 19 份文档、8 组 grep 搜索、10 个维度（A-K）、5 项 R21 修复回归验证、2 项 R21 修复引入回归专项排查、11 项 UX 状态完整性与性能优化清单，共 96 个检查点：
> - R21 5 项修复（3 P2 + 2 P3）**全部落地** ✅：
>   - R21-P2-1 consent 页 CSS 字号 16px→15px + 14px→13px ✅（L916 + L948）
>   - R21-P2-2 训练方案详情页 §4.8 UTF-8 乱码修复 ✅（L1057 + L1063 + 整段中文恢复）
>   - R21-P2-3 8 个新 i18n keys 双语翻译补充 ✅（zh-CN L1786-L1793 + en-US L1846-L1853）
>   - R21-P3-1 consent 页 en-US 7 个新 key 翻译补充 ✅（L962-L969）
>   - R21-P3-2 总览 §3.4 路由表注册 R20 新增 2 条路由 ✅（L197 + L212）
> - 但 R21 修复本身引入 **2 项新 P2 级回归问题**：
>   - R22-P2-1：07-training_advice/frontend.md L1260 `.session-index { font-size: 14px; }` 不在规范集 {12, 13, 15, 18, 24, 32}px 内（R21-P2-2 修复 UTF-8 乱码时新增/恢复 .session-index 样式时引入的字号违规）
>   - R22-P2-2：07-training_advice/frontend.md zh-CN.json L1793 + en-US.json L1853 `"sessionCompleted"` 缺少 `{{points}}` 插值占位符，与组件代码 L443 + L1093 `t('training.sessionCompleted', { points: result.points_earned })` 契约不一致（R21-P2-3 补充 i18n key 时遗漏插值占位符）
> - 设计系统 10 维度：9 维度合规（A 色彩 / C 间距 / D 圆角 / E 阴影 / F 组件 / G 路由 / H 状态管理 / J 无障碍 / K UX 状态），1 维度偏差（B 字号 — R21 修复引入的 .session-index 14px 违规）
> - UX 状态完整性维持 100%（18/18 切片含 Skeleton/Empty/catch/Toast 之一）
>
> **结论**：R21 5 项修复全部落地，前端维度未引入新的"功能级"问题，但 R21 修复 UTF-8 乱码 + 补 i18n key 时各引入 1 项 P2 级回归问题（字号违规 + i18n 插值缺失）。前端维度连续两轮无 P2+ 目标（新第一轮基线）**未达成**。

---

## 1. 执行摘要

R22 前端设计系统 + UX 状态完整性审查以 R21 报告为基线展开。R21 报告发现 3 项 P2 + 2 项 P3 问题，全部源自 R20-P1-3 consent 同意页与 R20-P2-1 训练方案详情页新增组件。本轮重点验证 R21 5 项修复的落地情况 + R21 修复是否引入新的回归 + 10 维度一致性维持 + UX 状态完整性维持。

**审查发现**：R21 5 项修复全部落地，但 R21 修复本身引入 2 项 P2 级回归问题：

1. **R22-P2-1**：07-training_advice/frontend.md L1260 `.session-index { font-size: 14px; }` 字号违规。R21-P2-2 修复 UTF-8 乱码时，恢复了 .session-index 样式定义（带 `font-size: 14px`）。`14px` 不在规范集 {12, 13, 15, 18, 24, 32}px 内。总览 §3.2 明确"禁止使用 9/14/22/48/56px 等非规范值"。
2. **R22-P2-2**：07-training_advice/frontend.md zh-CN.json L1793 `"sessionCompleted": "训练单已完成"` + en-US.json L1853 `"sessionCompleted": "Session completed"` 均缺少 `{{points}}` 插值占位符。组件代码 L443 + L1093 使用 `t('training.sessionCompleted', { points: result.points_earned })`，期望显示"训练单已完成，获得 X 积分"。文档说明 L1321 是 `"训练单已完成，获得 {{points}} 积分"`，但实际资源文件未包含 `{{points}}` 占位符。运行时 `points_earned` 参数将被忽略，用户只能看到"训练单已完成"，看不到积分数。

**审查目标达成情况**：

- ❌ 连续两轮无 P2+（新第一轮基线）：未达成（R21 修复引入 2 项 P2 回归）
- ✅ R21 5 项修复全部落地验证通过
- ✅ 10 维度一致性矩阵维持 9/10 合规（B 字号维度因 R22-P2-1 新增 .session-index 违规而失守）
- ✅ UX 状态完整性维持 100%（18/18 切片）
- ✅ 路径跳转路径匹配维持 32/32（R21-P3-2 修复后总览 §3.4 路由表与切片局部完全一致）

---

## 2. R21 修复回归验证（3 P2 + 2 P3 重点）

### 2.1 R21 修复验证表

| 编号 | R21 修复内容 | 验证位置 | 验证结果 | 影响 |
|------|------------|---------|---------|------|
| R21-P2-1 | consent 同意页 CSS 字号 16px→15px + 14px→13px | `01-auth/frontend.md` L916 `font-size: var(--fs-body); /* 15px */` + L948 `font-size: var(--fs-small); /* 13px */` | ✅ 已落地 | consent 页 2 处字号全部对齐规范集 {12, 13, 15, 18, 24, 32}px，且使用 var(--fs-*) 变量 |
| R21-P2-2 | 训练方案详情页 §4.8 UTF-8 编码乱码修复（15 处） | `07-training_advice/frontend.md` L1057 `## 4.8 训练方案详情页（R20-P2-1 新增训练单 UI + 标记完成）` + L1063 `// R20-P2-1: 训练方案详情页 UI 组件（R21-P2-2: 修复 UTF-8 编码乱码）` + grep `\?\?\?` 无匹配 | ✅ 已落地 | §4.8 整段中文恢复，标题/注释/说明/i18n 条目说明全部可读 |
| R21-P2-3 | 8 个新 i18n keys 双语翻译补充 | `07-training_advice/frontend.md` zh-CN.json L1786-L1793（planDetail/noSessions/completed/pending/scheduledDate/completedAt/markComplete/sessionCompleted）+ en-US.json L1846-L1853（同 8 key） | ✅ 已落地（**但 sessionCompleted 缺 {{points}} 插值，见 R22-P2-2**） | 8 个 i18n key 双语均已定义，但 sessionCompleted 资源与组件代码契约不一致 |
| R21-P3-1 | consent 页 en-US 7 个新 key 翻译补充 | `01-auth/frontend.md` L962-L969（privacyConsentTitle/privacyPolicyTitle/privacyPolicyBody/agreeAndContinue/refuse/consentRequired/consentFailed） | ✅ 已落地 | consent 页 7 个新 key en-US 翻译已补充 |
| R21-P3-2 | 总览 §3.4 路由表注册 R20 新增 2 条路由 | `00-垂直切片设计总览.md` L197 `'pages/auth/consent/index',` + L212 `'pages/training/plans/[plan_id]/index',` | ✅ 已落地 | 总览 §3.4 路由表已同步注册 R20 新增 2 条路由 |

**R21 修复验证结论**：5 项修复全部落地 ✅，其中 R21-P2-3 修复存在局部回归（8 个 key 已补充但 sessionCompleted 缺少 {{points}} 插值，详见 §6 R22-P2-2）。

### 2.2 R21 修复引入的回归问题（2 项 P2）

| 编号 | 回归源 | 引入位置 | 违规类型 | 优先级 |
|------|--------|---------|---------|--------|
| R22-P2-1 | R21-P2-2（UTF-8 乱码修复） | `07-training_advice/frontend.md` L1260 | 字号违规（.session-index 14px 不在规范集） | P2 |
| R22-P2-2 | R21-P2-3（i18n key 双语补充） | `07-training_advice/frontend.md` L1793 + L1853 | i18n 插值占位符缺失（sessionCompleted 缺 {{points}}） | P2 |

**R21 修复回归根因**：
1. R21-P2-2 修复 UTF-8 乱码时，整段 §4.8 重写。重写过程中恢复了 .session-index 样式定义（带 `font-size: 14px`），但未同步进行字号规范集合规审查。
2. R21-P2-3 补充 8 个 i18n key 双语翻译时，将文档说明（L1321 含 {{points}}）与实际资源文件定义（L1793/L1853 不含 {{points}}）不一致。这是 i18n 资源完整性审查未覆盖插值占位符匹配的盲区。

---

## 3. 10 维度一致性矩阵（A-K）

| 维度 | 检查点 | grep/验证结果 | 合规判定 | 备注 |
|------|--------|-------------|----------|------|
| A. 色彩 | 硬编码色值 | G1: 100 处。全部在总览 :root CSS 变量定义 + 审查跟踪表 + WCAG AA 对比度参考 + 视觉验证清单 + Taro app.config.ts tabBar 颜色（4 处，Taro 配置要求原始值）+ 注释中标注（如 `// #E63946`）；组件代码 0 处硬编码 | ✅ 合规 | R21 修复未引入新色彩违规；consent 页 + 训练方案详情页 CSS 全部使用 `var(--color-*)` |
| **B. 字体** | **font-size 值** | **G4: 全切片扫描违规 1 处：`07-training_advice/frontend.md` L1260 `.session-index { font-size: 14px; }`（训练方案详情页，R21-P2-2 修复 UTF-8 乱码时新增/恢复的样式），不在规范集 {12, 13, 15, 18, 24, 32}px** | **❌ 不合规** | **R21-P2-1 修复 consent 页 2 处字号违规 ✅，但 R21-P2-2 修复 UTF-8 乱码时引入 1 处新违规（.session-index 14px）。R21 基线 2 处违规 → R22 1 处违规（违规数减少但仍有残留）** |
| C. 间距 | var(--spacing-*) 使用 | G10: 100+ 处 var(--spacing-*)；间距属性硬编码 px（padding/margin/gap）= 0 处 | ✅ 100% 合规 | R21 修复未引入新间距违规；consent 页 + 训练方案详情页 .session-index 等新增样式全部使用 var(--spacing-xs/sm/md/lg) |
| D. 圆角 | border-radius 值 | G5: `\d+px` 匹配 0 处；12 处 `50%`（圆形）或 `0`（sharp corner）；100+ 处 `var(--radius-md/sm)` | ✅ 100% 合规 | R21 修复未引入新圆角违规 |
| E. 阴影 | box-shadow 值 | G6: 36 处全部 `var(--shadow-card)` + 1 处 `var(--shadow-card-top)`（R19-P3-1）；0 处硬编码 | ✅ 100% 合规 | R21 修复未引入新阴影违规 |
| F. 组件 | Dialog/Popup 使用 | G11: Dialog 1 文件（user L693 注销确认，合理）；Popup 7 文件（03-video_analysis L1025 反馈 + 02-user L730 导出 + 04-scoring L530/L550 比赛结束 + 05-match_data L537 得分方式 + 14-tab-pages/settings L263/L309 + 14-tab-pages/onboarding L272 引导步骤 + 07-training_advice L474 模板选择 + 10-membership L957 升级提示 + 09-gamification L1051 徽章解锁） | ✅ 合规 | R21 修复未引入 Dialog/Popup 违规 |
| G. 路由 | navigateTo 路径 | G7: 32 处 navigateTo + 5 处 redirectTo + 8 处 switchTab + 1 处 reLaunch。逐条与总览 §3.4 L185-L227 路由表交叉验证 | ✅ 32/32 | R21-P3-2 修复后总览 §3.4 路由表已同步注册 R20 新增 2 条路由（L197 + L212），路由表局部与全局完全一致 |
| H. 状态管理 | Zustand 使用 | G8: 16 文件 `create<...>` / `create(...)`：13 frontend.md + match-tab + onboarding + home（00-home/frontend.md L1 处 useGlobalStore）+ user（settings 复用 useUserStore）；training-tab 显式"不需要独立 Store" | ✅ 100% 合规 | R21 修复未引入新状态管理违规；consent 页使用 useAuthStore + 训练方案详情页使用 useTrainingStore，符合规范 |
| I. i18n | t('key') 使用 + zh-CN/en-US 资源 | G12: 全部 18 切片含 2 处 i18n 资源文件引用；JSX 硬编码中文 = 0 处。但 R21-P2-3 修复引入 1 处插值占位符缺失：sessionCompleted zh-CN.json L1793 + en-US.json L1853 缺 `{{points}}` 插值，与组件代码 L443 + L1093 契约不一致（详见 R22-P2-2） | ⚠️ 17/18 | R21-P2-3 修复 8 个 key 双语补充 ✅，R21-P3-1 修复 consent 页 7 个 key en-US 翻译补充 ✅；但 R21-P2-3 引入 1 处插值契约不一致（R22-P2-2） |
| J. 无障碍 | aria-label/role/WCAG AA | G9: 总览 §3.8 L449-L477 规范已定义（5 处 aria-label/role 指导 + 4 处 aria-live/aria-modal 指导）；切片代码 0 处 ARIA 实现（R19-P3-4 已知推迟项） | ✅ 已知推迟项 | R19-P3-4 修复后开发阶段实现清单完整（含 CI 阻塞 @axe-core/playwright / eslint-plugin-jsx-a11y），R21 修复未引入新无障碍违规（亦未补齐 ARIA） |
| K. UX 状态完整性 | Skeleton/Empty/catch/Toast | 14/18 切片含 Skeleton；8 切片含 Empty；14 切片含 catch；Toast 在所有切片中广泛使用（含 R21 修复的 consent 页 + 训练方案详情页） | ✅ 100% 合规 | R21 修复维持 consent 页 L814 Toast + 训练方案详情页 L1096 Skeleton + L1121 Empty + L1093 Toast，UX 状态完整性维持 |

---

## 4. R21 新增组件审查

### 4.1 R20-P1-3 consent 同意页审查（R21 修复后状态）

**组件位置**：`01-auth/frontend.md` L780-L951（R20-P1-3 新增 + R21-P2-1 + R21-P3-1 修复）

**审查项与结果**：

| 检查项 | 验证位置 | 结果 | 说明 |
|--------|---------|------|------|
| ConsentPage 组件实现 | L818 `export default function ConsentPage()` | ✅ | 函数组件 + TypeScript + useTranslation |
| 路由局部注册 | L567 `'pages/auth/consent/index'` | ✅ | 01-auth/frontend.md §6 局部 app.config.ts 已注册 |
| 路由总览同步 | 总览 §3.4 L197 | ✅ | R21-P3-2 修复后总览 §3.4 路由表已注册 |
| CSS 间距变量化 | L882/L883/L895/L896/L903/L911/L923/L926/L932/L937 全部使用 `var(--spacing-*)` | ✅ | 间距属性 0 处硬编码 |
| CSS 圆角变量化 | L909 `var(--radius-md)` + L939/L945 `var(--radius-sm)` | ✅ | 圆角 0 处硬编码 |
| CSS 阴影变量化 | L911 `box-shadow: var(--shadow-card)` | ✅ | 阴影 0 处硬编码 |
| CSS 色彩变量化 | L877/L891/L901/L910/L918/L929/L930/L936 全部使用 `var(--color-*)` | ✅ | 色彩 0 处硬编码 |
| **CSS 字号合规** | **L895 `font-size: 18px` ✅ + L916 `font-size: var(--fs-body); /* 15px */` ✅（R21-P2-1 修复）+ L924 `font-size: 13px` ✅ + L941 `font-size: 15px` ✅ + L948 `font-size: var(--fs-small); /* 13px */` ✅（R21-P2-1 修复）** | **✅** | **R21-P2-1 修复后 5 处字号全部在规范集 {12, 13, 15, 18, 24, 32}px 内** |
| i18n t('key') 使用 | L803/L804/L823/L830/L836/L851/L859 共 7 处 `t('auth.*')` 调用 | ✅ | 组件代码全部使用 i18n |
| i18n 资源 zh-CN | L954-L960 文档列出 7 个 zh-CN 新 key | ✅ | 文档列出 zh-CN 翻译 |
| **i18n 资源 en-US** | **L962-L969 文档列出 7 个 en-US 新 key（R21-P3-1 修复）** | **✅** | **R21-P3-1 修复后 en-US 翻译已补充** |
| UX 状态完整性 | L814-L815 Toast + L818-L826 同意/拒绝按钮 | ✅ | 含 Toast 错误提示 |
| 路由跳转路径匹配 | L821 `Taro.switchTab({ url: '/pages/home/index' })` ✅ | ✅ | 路径已注册 |

**consent 页审查结论**：13 项检查中 13 项全部通过 ✅。R21-P2-1 + R21-P3-1 + R21-P3-2 修复后 consent 页设计系统合规性 100%。

### 4.2 R20-P2-1 训练方案详情页审查（R21 修复后状态）

**组件位置**：`07-training_advice/frontend.md` §4.8 L1054-L1311（R20-P2-1 新增 + R21-P2-2 + R21-P2-3 + R21-P3-2 修复）

**审查项与结果**：

| 检查项 | 验证位置 | 结果 | 说明 |
|--------|---------|------|------|
| TrainingPlanDetailPage 组件实现 | L1072 `export default function TrainingPlanDetailPage()` | ✅ | 函数组件 + TypeScript + useTranslation |
| 路由局部注册 | L1721 `'pages/training/plans/[plan_id]/index'` | ✅ | 07-training_advice/frontend.md §6 局部 app.config.ts 已注册 |
| 路由总览同步 | 总览 §3.4 L212 | ✅ | R21-P3-2 修复后总览 §3.4 路由表已注册 |
| **代码注释/说明编码完整性** | **§4.8 L1054-L1311 整段：L1057 标题 `## 4.8 训练方案详情页（R20-P2-1 新增训练单 UI + 标记完成）` + L1063 注释 `// R20-P2-1: 训练方案详情页 UI 组件（R21-P2-2: 修复 UTF-8 编码乱码）` + grep `\?\?\?` 无匹配** | **✅** | **R21-P2-2 修复后整段中文恢复，UTF-8 编码缺陷已清除** |
| CSS 间距变量化 | L1211/L1213/L1220/L1226/L1237/L1241/L1258/L1268/L1273/L1278/L1284/L1287 全部 `var(--spacing-*)` | ✅ | 间距属性 0 处硬编码 |
| CSS 圆角变量化 | L1242 `var(--radius-md) !important` | ✅ | 圆角 0 处硬编码 |
| CSS 色彩变量化 | L1207/L1212/L1219/L1230/L1253/L1263/L1272/L1283 全部 `var(--color-*)` | ✅ | 色彩 0 处硬编码 |
| **CSS 字号合规** | **L1224 `18px` ✅ + L1238 `12px` ✅ + L1260 `14px` ❌（R21-P2-2 修复时引入的违规）+ L1267 `15px` ✅ + L1278 `12px` ✅ + L1292 `13px` ✅** | **❌** | **R21-P2-2 修复 UTF-8 乱码时新增/恢复 .session-index 样式（L1259-L1264），其中 L1260 `font-size: 14px` 不在规范集（详见 R22-P2-1）** |
| i18n t('key') 使用 | L1093/L1103/L1122/L1124/L1138/L1159/L1161/L1166/L1170/L1174/L1194 共 11 处 `t('training.*')` 调用 | ✅ | 组件代码全部使用 i18n |
| **i18n 资源 zh-CN 定义** | **zh-CN.json L1786-L1793 中 8 个新 key 全部定义 ✅，但 L1793 `"sessionCompleted": "训练单已完成"` 缺 `{{points}}` 插值（R21-P2-3 引入的回归）** | **⚠️** | **R21-P2-3 修复后 8 个 key 已定义，但 sessionCompleted 缺插值占位符（详见 R22-P2-2）** |
| **i18n 资源 en-US 定义** | **en-US.json L1846-L1853 中 8 个新 key 全部定义 ✅，但 L1853 `"sessionCompleted": "Session completed"` 缺 `{{points}}` 插值（R21-P2-3 引入的回归）** | **⚠️** | **R21-P2-3 修复后 8 个 key 已定义，但 sessionCompleted 缺插值占位符（详见 R22-P2-2）** |
| UX 状态完整性 | L1093 Toast + L1099-L1112 Skeleton + L1118-L1124 Empty | ✅ | UX 状态完整 |
| store action 集成 | L1081 `store.fetchTrainingSessions(planId)` + L1087 `store.completeTrainingSession(planId, sessionId)` | ✅ | store 集成正确 |
| API §8.7 / §8.8 端点对应 | L208 `listTrainingSessions` → `/training/plans/${planId}/sessions` + L221 `completeTrainingSession` → `/training/plans/${planId}/sessions/${sessionId}/complete` | ✅ | API 契约一致 |

**训练方案详情页审查结论**：13 项检查中 11 项通过，2 项偏差（1 P2 字号违规 R22-P2-1 + 1 P2 i18n 插值缺失 R22-P2-2）。R21-P2-2 + R21-P2-3 修复后编码与 i18n key 已落地，但修复本身引入 2 项 P2 级回归。

---

## 5. UX 状态完整性

### 5.1 18 切片 UX 状态完整性矩阵

| 切片 | Skeleton | Empty | catch | Toast | 备注 |
|------|---------|-------|-------|-------|------|
| 00-home | ✅ | ✅ | ✅ | ✅ | L633 navigateTo 参数 `?report_id=` 一致（R19-P1-1 修复维持） |
| 01-auth | — | — | ✅ | ✅ | R21 修复后 consent 页 L814 Toast ✅；L818-L826 同意/拒绝按钮；字号规范集合规 |
| 02-user | ✅ | ✅ | ✅ | ✅ | rating-history Empty（R19-P2-1 修复维持） |
| 03-video_analysis | ✅ | ✅ | ✅ | ✅ | report-list Empty（R19-P2-2 修复维持） + L1644 顶部阴影 `var(--shadow-card-top)`（R19-P3-1 修复维持） |
| 04-scoring | ✅ | — | ✅ | ✅ | — |
| 05-match_data | ✅ | — | ✅ | ✅ | — |
| 06-data_dashboard | ✅ | — | ✅ | ✅ | — |
| 07-training_advice | ✅ | ✅ | ✅ | ✅ | R21 修复后训练方案详情页 L1099 Skeleton + L1121 Empty + L1093 Toast（编码已恢复，但 L1260 .session-index 字号违规见 R22-P2-1，L1093 sessionCompleted 插值缺失见 R22-P2-2） |
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

**UX 状态完整性结论**：18 切片 UX 状态完整性维持 100% 合规。R21 修复未引入 UX 状态回归。R22-P2-1（字号违规）与 R22-P2-2（i18n 插值缺失）不影响 UX 状态完整性（Skeleton/Empty/catch/Toast 四件套均完整）。

### 5.2 11 项 UX 状态完整性与性能优化清单

| # | 检查项 | 验证结果 | 备注 |
|---|--------|----------|------|
| 1 | Skeleton 加载占位 | 14/18 切片 ✅ | R21 修复维持训练方案详情页 L1099 Skeleton ✅ |
| 2 | Empty 空状态组件 | 8 切片 ✅ | R21 修复维持训练方案详情页 L1121 Empty ✅ |
| 3 | catch 错误捕获 | 14 切片 ✅ | R21 修复维持 consent 页 store L255 catch + 训练方案详情页 store catch ✅ |
| 4 | Toast 反馈 | 18 切片 ✅ | R21 修复维持 consent 页 L814 Toast + 训练方案详情页 L1093 Toast ✅（注：L1093 Toast 文案 sessionCompleted 缺 {{points}} 插值，影响文案但不影响 Toast 机制本身） |
| 5 | 图片 lazy-load | 切片代码 0 处实现 | R19-P3-2 推迟项（开发阶段实现清单已闭环） |
| 6 | IntersectionObserver | 切片代码 0 处实现 | R19-P3-2 推迟项 |
| 7 | virtualList 长列表 | 切片代码 0 处实现 | R19-P3-2 推迟项 |
| 8 | debounce/throttle | 切片代码 0 处实现 | R19-P3-2 推迟项 |
| 9 | ARIA 属性 | 切片代码 0 处实现 | R19-P3-4 推迟项（开发阶段 CI 阻塞已闭环） |
| 10 | WCAG 2.2 SC 2.5.8 触摸目标 | 总览 §3.8 规范已定义 | 切片代码未显式实现，由 NutUI 组件库默认满足 |
| 11 | 反幻觉约束 | 18 切片 ✅ | 用户可见文本全部 `t('key')`；R21 修复后 §4.8 整段中文恢复，反幻觉约束维持 |

---

## 6. 新发现 P0-P3 分级

### 6.1 P0 级（阻断级）

**无 P0 级问题。**

### 6.2 P1 级（严重级）

**无 P1 级问题。**

### 6.3 P2 级（一般级）

#### R22-P2-1：R21-P2-2 修复 UTF-8 乱码时引入 .session-index 字号违规

- **位置**：`docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` L1259-L1264
- **现象**：
  ```scss
  .session-index {  // R21-P2-1: session_index 样式（注：实际为 R21-P2-2 修复 UTF-8 乱码时新增/恢复的样式）
    font-size: 14px;  // ❌ 不在规范集 {12, 13, 15, 18, 24, 32}px
    font-weight: bold;
    color: var(--color-primary);
    margin-right: var(--spacing-xs);
  }
  ```
  - L1260 `font-size: 14px;`（训练方案详情页 .session-index 样式，用于显示训练单序号 `#1`/`#2`/`#3`）
- **违规依据**：总览 §3.2 :root L145-L150 定义 6 级 `--fs-*` 变量为 `{12, 13, 15, 18, 24, 32}px`，并显式说明"不引入中间字号（如 14/16/20）以避免视觉层级模糊"。`14px` 不在规范集内。
- **影响**：
  1. R21-P2-2 修复 UTF-8 乱码时，整段 §4.8 重写。重写过程中恢复了 .session-index 样式定义（带 `font-size: 14px`），但未同步进行字号规范集合规审查。
  2. R21 报告 §4.2 检查项中列出了 L1217/L1229/L1251/L1262/L1271 字号检查（全部 ✅），但未覆盖 L1260（.session-index）。原因是 R21 报告书写时 §4.8 整段乱码，无法识别 .session-index 样式；R21-P2-2 修复后才暴露该违规。
  3. R20+R21 基线 2 处字号违规（consent 页 L908 16px + L939 14px）经 R21-P2-1 修复后清零，但 R21-P2-2 修复 UTF-8 乱码时引入新的 1 处违规（.session-index 14px），使字号规范集合规性从 R21 基线 2 处违规退化为 R22 1 处违规（违规数减少但仍有残留）。
- **修复方案**：
  - L1260：`font-size: 14px;` → `font-size: 13px;`（或 `font-size: var(--fs-small);`，与 .session-reps L1278 一致使用 12px 亦可，但考虑序号需要稍大字号强调，建议使用 13px）
- **优先级理由**：违反设计系统硬约束（字号规范集），但仅影响训练单序号（#1/#2/#3）视觉层级，不影响功能，定为 P2。

#### R22-P2-2：R21-P2-3 补充 i18n key 时 sessionCompleted 缺 {{points}} 插值占位符

- **位置**：
  - 组件代码引用：`docs/06垂直模块前后端切片设计/07-training_advice/frontend.md` L443 `i18next.t('training.sessionCompleted', { points: data.points_earned })` + L1093 `setToastMsg(t('training.sessionCompleted', { points: result.points_earned }))`
  - 文档说明：`07-training_advice/frontend.md` L1321 `> - zh-CN: training.sessionCompleted = "训练单已完成，获得 {{points}} 积分"`
  - zh-CN.json 定义：`07-training_advice/frontend.md` L1793 `"sessionCompleted": "训练单已完成"` ← **缺 `{{points}}` 插值**
  - en-US.json 定义：`07-training_advice/frontend.md` L1853 `"sessionCompleted": "Session completed"` ← **缺 `{{points}}` 插值**
- **现象**：
  - 组件代码 L443 + L1093 使用 `t('training.sessionCompleted', { points: result.points_earned })`，期望显示"训练单已完成，获得 X 积分"
  - 文档说明 L1321 是 `"训练单已完成，获得 {{points}} 积分"`，包含 `{{points}}` 插值占位符
  - zh-CN.json L1793 实际定义 = `"训练单已完成"` ← **缺少 `{{points}}` 插值占位符**
  - en-US.json L1853 实际定义 = `"Session completed"` ← **缺少 `{{points}}` 插值占位符**
- **违规依据**：违反反幻觉约束 + i18n 资源完整性约束。组件代码传入 `points` 参数，但资源文件无对应占位符，运行时 react-i18next 将忽略 `points_earned` 参数，用户只能看到"训练单已完成"，看不到获得的积分数。
- **影响**：
  1. 用户完成训练单时（L1087 `handleCompleteSession` → L1090 `store.completeTrainingSession` → L1093 Toast），Toast 只显示"训练单已完成"，不显示获得的积分数（如"训练单已完成，获得 50 积分"）。
  2. 同样影响 L443（store.completeTrainingSession 内部 i18next.t 调用）— 该处可能用于通知系统或日志，影响范围与 L1093 一致。
  3. 文档说明（L1321）与实际资源文件（L1793/L1853）契约不一致，违反文档与代码一致性约束。
- **修复方案**：
  - zh-CN.json L1793：
    ```diff
    - "sessionCompleted": "训练单已完成"
    + "sessionCompleted": "训练单已完成，获得 {{points}} 积分"
    ```
  - en-US.json L1853：
    ```diff
    - "sessionCompleted": "Session completed"
    + "sessionCompleted": "Session completed, earned {{points}} points"
    ```
- **优先级理由**：i18n 资源与组件代码契约不一致，影响 1 处用户可见反馈文本（训练单完成 Toast），但仅限 R21-P2-3 修复引入的回归，不影响存量功能，定为 P2。

### 6.4 P3 级（建议级）

**无 P3 级新发现。**

R21-P3-1（consent 页 i18n 文档补充 en-US 翻译）+ R21-P3-2（总览 §3.4 路由表同步注册 R20 新增 2 条路由）已全部修复落地，本轮无新 P3 级问题。

---

## 7. 修复跟踪表与累计计数

### 7.1 R22 修复跟踪表

| 编号 | 优先级 | 修复内容 | 修复位置 | 状态 |
|------|--------|----------|---------|------|
| R22-P2-1 | P2 | .session-index 字号 14px→13px | `07-training_advice/frontend.md` L1260 | ⏳ 待修复 |
| R22-P2-2 | P2 | sessionCompleted 补 {{points}} 插值占位符（zh-CN + en-US 双语） | `07-training_advice/frontend.md` L1793 + L1853 | ⏳ 待修复 |

### 7.2 R21 修复落地状态跟踪

| 编号 | R21 修复内容 | R22 验证结果 | 落地状态 |
|------|------------|-------------|---------|
| R21-P2-1 | consent 页 CSS 字号 16px→15px + 14px→13px | ✅ L916 + L948 全部对齐规范集 + 使用 var(--fs-*) 变量 | ✅ 已落地 |
| R21-P2-2 | 训练方案详情页 §4.8 UTF-8 乱码修复 | ✅ L1057 + L1063 + grep `\?\?\?` 无匹配 | ✅ 已落地（但引入 R22-P2-1） |
| R21-P2-3 | 8 个新 i18n keys 双语翻译补充 | ✅ zh-CN L1786-L1793 + en-US L1846-L1853 全部定义 | ✅ 已落地（但引入 R22-P2-2） |
| R21-P3-1 | consent 页 en-US 7 个新 key 翻译补充 | ✅ L962-L969 全部补充 | ✅ 已落地 |
| R21-P3-2 | 总览 §3.4 路由表注册 R20 新增 2 条路由 | ✅ L197 + L212 全部注册 | ✅ 已落地 |

### 7.3 累计修复计数

| 轮次 | 本轮修复 | 累计修复 | 说明 |
|------|---------|---------|------|
| 第一轮~第二十轮 | 880 | 880 | — |
| 第二十一轮（前端线） | 5（R21-P2×3 + P3×2） | 885 | R21 5 项修复落地 |
| **第二十二轮（本轮，前端线）** | **2（待修复，R22-P2×2）** | **887（待修复后）** | R22 新发现 2 项 P2，均为 R21 修复引入的回归问题 |

> **说明**：R22 前端线新发现 2 项 P2 问题（R22-P2-1 + R22-P2-2），全部源自 R21 修复本身（R21-P2-2 修复 UTF-8 乱码 + R21-P2-3 补充 i18n key）。R21 5 项修复虽全部落地，但修复时未充分进行设计系统字号规范集合规审查 + i18n 插值占位符契约一致性审查，导致修复本身引入 2 项 P2 级回归。前端维度连续两轮无 P2+ 目标（新第一轮基线）**未达成**。

### 7.4 R21 修复回归分析

| R21 修复项 | R21 报告状态 | R22 验证结果 | 回归原因 |
|-----------|-------------|-------------|---------|
| R21-P2-1（consent 页字号 16px/14px→15px/13px） | ✅ 已修复 | ✅ 维持 | — |
| R21-P2-2（§4.8 UTF-8 乱码修复） | ✅ 已修复 | ⚠️ 引入 R22-P2-1 | R21-P2-2 修复时整段重写 §4.8，恢复 .session-index 样式时未同步进行字号规范集合规审查 |
| R21-P2-3（8 个 i18n key 双语补充） | ✅ 已修复 | ⚠️ 引入 R22-P2-2 | R21-P2-3 补充 i18n key 时，将文档说明（含 {{points}}）与实际资源文件定义（不含 {{points}}）不一致，i18n 资源完整性审查未覆盖插值占位符匹配 |
| R21-P3-1（consent 页 en-US 翻译补充） | ✅ 已修复 | ✅ 维持 | — |
| R21-P3-2（总览 §3.4 路由表同步） | ✅ 已修复 | ✅ 维持 | — |

**R21 修复回归根因**：
1. R21-P2-2 修复 UTF-8 乱码时，整段 §4.8 重写。重写过程中恢复了 .session-index 样式定义（带 `font-size: 14px`），但未同步进行字号规范集合规审查。
2. R21-P2-3 补充 8 个 i18n key 双语翻译时，将文档说明（L1321 含 {{points}}）与实际资源文件定义（L1793/L1853 不含 {{points}}）不一致。这是 i18n 资源完整性审查未覆盖插值占位符匹配的盲区。

**改进建议**：
1. 后续修复涉及新增/恢复 CSS 样式时，必须同步执行 grep `font-size:\s*(9|14|16|20|22|28|36|48|56)px` 检查字号规范集合规性。
2. 后续修复涉及 i18n key 补充时，必须同步校验组件代码 `t('key', { param })` 中的插值参数与资源文件中 `{{param}}` 占位符的契约一致性。

---

## 8. grep 执行结果汇总（8 组）

| 搜索组 | 匹配数 | R22 关键发现 |
|--------|--------|--------------|
| G1 硬编码色值（hex/rgba） | 100 | 全部在 :root 定义/注释/验证清单/Taro 配置中，组件代码 0 处 ✅ |
| G2 border-radius px | 0 | 圆角硬编码 0 处，全部 50% 或 var(--radius-*) ✅ |
| G3 box-shadow 非 var | 0 | 阴影硬编码 0 处，全部 var(--shadow-card) 或 var(--shadow-card-top) ✅ |
| **G4 font-size 违规值（9/14/16/20/22/28/36/48/56）px** | **1** | **`07-training_advice/frontend.md` L1260 `.session-index { font-size: 14px; }`（R21-P2-2 修复 UTF-8 乱码时引入的违规）❌** |
| G5 navigateTo 路径 | 32 | 32 处路径全部在总览 §3.4 注册 ✅（R21-P3-2 修复后路由表完全一致） |
| G6 Zustand create | 16 文件 | 全部使用 `create` from 'zustand' ✅ |
| G7 aria/role | 13 | 全部在总览 §3.8 规范中（9 处）+ admin.md（1 处 role="super_admin"）+ conftest.py.md（2 处 role 注释），切片代码 0 处 ARIA 实现（R19-P3-4 已知推迟项） |
| G8 i18n key 资源覆盖 | 1 插值缺失 | R21-P2-3 修复后 8 个 key 双语已定义，但 sessionCompleted 缺 {{points}} 插值（R22-P2-2）❌ |

**grep 执行补充**：
- 间距硬编码检查（padding/margin/gap 数字 px）：0 处违规 ✅
- UTF-8 乱码检查（`\?\?\?` 模式）：0 处匹配 ✅（R21-P2-2 修复后乱码完全清除）
- 路由表交叉验证：总览 §3.4 L185-L227 路由表 + 01-auth/frontend.md §6 局部路由 + 07-training_advice/frontend.md §6 局部路由，三方一致 ✅（R21-P3-2 修复后）

---

## 9. 审查结论

R22 前端设计系统 + UX 状态完整性审查覆盖 19 份文档、8 组 grep 搜索、10 个维度（A-K）、5 项 R21 修复回归验证、2 项 R21 修复引入回归专项排查、11 项 UX 状态完整性与性能优化清单，共 96 个检查点中 91 个通过、5 个偏差（含 2 项 P2，无 P3）。

**R21 修复回归验证结论**：R21 5 项修复（3 P2 + 2 P3）全部落地 ✅，但 R21-P2-2（UTF-8 乱码修复）+ R21-P2-3（i18n key 双语补充）各引入 1 项 P2 级回归问题。

**新发现 P0/P1/P2/P3 问题**：
- P0×0 + P1×0 + **P2×2** + P3×0
- 2 项 P2 问题全部源自 R21 修复本身：
  - R22-P2-1：R21-P2-2 修复 UTF-8 乱码时新增/恢复的 .session-index 样式 L1260 `font-size: 14px` 违规（不在规范集 {12, 13, 15, 18, 24, 32}px）
  - R22-P2-2：R21-P2-3 补充 8 个 i18n key 时 sessionCompleted zh-CN.json L1793 + en-US.json L1853 缺 `{{points}}` 插值占位符，与组件代码 L443 + L1093 契约不一致
- 无 P3 级新发现（R21-P3-1 + R21-P3-2 已全部修复落地）

**前端维度连续两轮无 P2+ 目标（新第一轮基线）**：**未达成** ❌

R21 报告发现 3 项 P2 + 2 项 P3 问题并完成修复。R22 验证 R21 5 项修复全部落地，但 R21 修复本身引入 2 项 P2 级回归问题（.session-index 字号违规 + sessionCompleted 插值缺失）。前端维度连续两轮无 P2+ 目标（新第一轮基线）**未达成**。

**设计系统 10 维度状态**：
- 9 维度维持合规（A 色彩 / C 间距 / D 圆角 / E 阴影 / F 组件 / G 路由 / H 状态管理 / J 无障碍 / K UX 状态）
  - G 路由维度从 R21 基线 30/32 提升至 32/32（R21-P3-2 修复后总览 §3.4 路由表完全一致）
  - I i18n 维度从 R21 基线 16/18 提升至 17/18（R21-P2-3 + R21-P3-1 修复后 i18n key 双语均已定义，但 sessionCompleted 插值缺失）
- 1 维度失守（B 字号 — R21-P2-2 修复 UTF-8 乱码时引入的 .session-index 14px 违规）

**R21 修复回归根因**：
1. R21-P2-2 修复 UTF-8 乱码时，整段 §4.8 重写。重写过程中恢复了 .session-index 样式定义（带 `font-size: 14px`），但未同步进行字号规范集合规审查。
2. R21-P2-3 补充 8 个 i18n key 双语翻译时，将文档说明（含 {{points}}）与实际资源文件定义（不含 {{points}}）不一致。i18n 资源完整性审查未覆盖插值占位符匹配的盲区。

**修复建议优先级**：
1. 立即修复 R22-P2-1（.session-index 字号 14px→13px，1 行修改）+ R22-P2-2（sessionCompleted 补 {{points}} 插值，zh-CN + en-US 双语 2 行修改）
2. 后续 R23 验证重点：
   - R22-P2-1 修复后 .session-index 字号合规性回归
   - R22-P2-2 修复后 sessionCompleted 插值占位符与组件代码契约一致性
   - 全切片再次扫描 font-size 违规值，确保 0 处残留
   - 全切片再次扫描 i18n key 插值占位符与组件代码 t('key', { param }) 契约一致性

**R23 验证重点**：
1. R22-P2-1 修复后 .session-index 字号合规性回归
2. R22-P2-2 修复后 sessionCompleted 双语资源包含 {{points}} 插值
3. 全切片 i18n 插值占位符契约一致性扫描（新增检查项）
4. 10 维度一致性维持
5. UX 状态完整性维持

---

*审查完成。报告归档路径：`docs/07审查报告/第二十二轮/R22-前端设计系统UX审查报告.md`*
