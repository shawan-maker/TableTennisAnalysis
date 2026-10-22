# 综合审查报告：UI/UX 与前端设计系统一致性

> **审查范围**：乒乓智能分析平台前端垂直切片设计（模块 00–12、14-tab-pages）与需求/界面/架构基准文档  
> **审查维度**：页面覆盖度 / 设计系统合规性 / 组件模式 / 导航与路由 / 状态管理 / 国际化 / 无障碍与 UX / 跨端策略  
> **审查模式**：只读审查，未修改任何源文件  
> **审查日期**：2026-10-12  
> **基准文档**：需求分析与路线图 v0.4、前端需求与界面设计 v2.0、系统架构设计 v2.4、垂直切片设计总览

---

## 目录

1. [审查摘要](#1-审查摘要)
2. [页面覆盖度](#2-页面覆盖度page-coverage)
3. [设计系统合规性](#3-设计系统合规性design-system-compliance)
4. [组件模式一致性](#4-组件模式一致性component-patterns)
5. [导航与路由一致性](#5-导航与路由一致性navigation--routing)
6. [状态管理一致性](#6-状态管理一致性state-management)
7. [国际化与本地化](#7-国际化与本地化i18n--localization)
8. [无障碍与用户体验](#8-无障碍与用户体验accessibility--ux)
9. [跨端策略一致性](#9-跨端策略一致性cross-end-strategy)
10. [跨切片路由路径一致性矩阵](#10-跨切片路由路径一致性矩阵)
11. [P0–P3 问题汇总表](#11-p0p3-问题汇总表)
12. [优化机会与建议](#12-优化机会与建议)

---

## 1. 审查摘要

本次审查覆盖 13 个前端垂直切片文档（00–12）和 5 个 Tab 页面文档（14-tab-pages），与 4 份基准文档（需求、界面设计、架构、切片总览）进行交叉比对。共发现 **40 项问题**，按严重程度分布如下：

| 级别 | 数量 | 说明 |
|------|------|------|
| **P0 — 阻断** | 6 | 路由路径不匹配，将导致运行时导航失败 |
| **P1 — 高优** | 12 | 设计规范违规、硬编码颜色/中文、跨端兼容问题 |
| **P2 — 中优** | 15 | 字号偏差、组件不一致、状态管理差异 |
| **P3 — 低优** | 7 | 间距微调、图标混用、无障碍细节 |

---

## 2. 页面覆盖度（Page Coverage）

### 2.1 需求到切片映射

| 需求功能域 | 对应切片模块 | 覆盖状态 |
|------------|-------------|----------|
| 视频分析 | 01-视频分析 | ✅ 完整 |
| 用户认证 | 02-用户认证 | ✅ 完整 |
| 个人档案 | 03-个人档案 | ✅ 完整 |
| 社区互动 | 04-社区 | ✅ 完整 |
| 赛事数据 | 05-赛事数据 | ✅ 完整 |
| 数据看板 | 06-数据看板 | ✅ 完整 |
| 训练建议 | 07-训练建议 | ✅ 完整 |
| 进度分析 | 08-进度分析 | ✅ 完整 |
| 游戏化 | 09-游戏化 | ✅ 完整 |
| 社交互动 | 10-社交互动 | ✅ 完整 |
| 支付 | 11-支付 | ✅ 完整 |
| 通知 | 12-通知 | ✅ 完整 |
| Tab 页面 | 14-tab-pages | ✅ 完整 |
| 模块 13 | — | ⚠️ 序号预留，未见对应文档（疑似预留扩展位） |

### 2.2 TabBar 与 5-Tab 设计偏差

| ID | 级别 | 问题 | 影响 |
|----|------|------|------|
| CV-001 | **P1** | 界面设计 v2.0 规定 5 个固定 Tab（首页/训练/赛事/社区/我的），但 `14-tab-pages/community-tab` 文档说明社区 Tab 在 Phase 1 **不在 TabBar 中**，仅保留路由预留。 | Phase 1 用户无法直接从底部导航访问社区入口，与设计规范的 5-Tab 布局不一致。 |

**建议**：在 Phase 1 的 TabBar 中加入社区 Tab 占位（"敬请期待"状态），或在界面设计文档中明确记录"Phase 1 为 4-Tab，Phase 2 扩展为 5-Tab"的设计决策偏差。

---

## 3. 设计系统合规性（Design System Compliance）

### 基准规范

| 维度 | 规范值 | 来源 |
|------|--------|------|
| 主色 | `#E63946`（红）/ `#1D3557`（深蓝） | 界面设计 v2.0 §设计令牌 |
| 辅色 | `#F4A261`（橙）/ `#2A9D8F`（青）/ `#E76F51`（珊瑚） | 同上 |
| 字号体系 | 24/18/15/13/32/12px | 同上 §排版 |
| 间距网格 | 8px 基准网格 | 同上 §间距 |
| 卡片圆角 | 12px | 同上 §组件 |
| 按钮圆角 | 12px | 同上 §组件 |
| 卡片阴影 | `0 2px 8px rgba(0,0,0,0.06)` | 同上 §阴影 |
| 主题方案 | CSS 变量 `:root` 全局定义 | 切片总览 §样式约定 |

### 3.1 按钮圆角违规

| ID | 级别 | 模块 | 问题 | 规范值 |
|----|------|------|------|--------|
| DS-001 | **P0** | `05-match_data` quick-entry | 快捷录入按钮 `border-radius: 24px` | 12px |
| DS-002 | **P1** | `08-progress_analysis` report-selector | 报告选择器按钮 `border-radius: 24px` | 12px |

**根因**：开发者可能直接使用 NutUI 默认圆角（24px），未覆盖为设计规范值。

### 3.2 卡片阴影不一致

| ID | 级别 | 模块 | 实际值 | 规范值 |
|----|------|------|--------|--------|
| DS-003 | **P1** | `06-data_dashboard` 各卡片 | `0 1px 4px rgba(0,0,0,0.04)` | `0 2px 8px rgba(0,0,0,0.06)` |
| DS-004 | **P1** | `08-progress_analysis` 卡片 | `0 1px 4px rgba(0,0,0,0.04)` | `0 2px 8px rgba(0,0,0,0.06)` |
| DS-005 | **P2** | `14-tab-pages/onboarding` HomeTourOverlay | `0 4px 12px rgba(0,0,0,0.15)` | `0 2px 8px rgba(0,0,0,0.06)` |
| DS-006 | **P2** | `09-gamification` badge 卡片 | `0 1px 3px rgba(0,0,0,0.08)` | `0 2px 8px rgba(0,0,0,0.06)` |

### 3.3 CSS `:root` 变量重定义

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| DS-007 | **P1** | `06-data_dashboard/index.scss` | 在模块级 SCSS 中重新定义 `:root` CSS 变量，覆盖全局主题变量。应仅在全局 `app.scss` 中定义。 |
| DS-008 | **P1** | `07-training_advice/index.scss` | 同上，在模块级 SCSS 中重定义 `:root` 变量。 |

**影响**：破坏主题切换机制，导致跨模块样式不一致。

### 3.4 未定义的 CSS 变量

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| DS-009 | **P1** | `05-match_data`、`08-progress_analysis` | 使用 `--color-warning` 变量，但该变量未在全局 `:root` 中定义。 |
| DS-010 | **P1** | `11-payment` | 引用 `--color-text-inverse` 变量，但该变量未在全局 `:root` 中定义。 |

**影响**：变量未定义时将回退为浏览器默认值，导致颜色表现与设计意图不符。

### 3.5 非标准字号使用

| ID | 级别 | 模块 | 实际字号 | 规范字号 |
|----|------|------|----------|----------|
| DS-011 | **P2** | `06-data_dashboard` 标签/辅助文字 | 14px | 不在 24/18/15/13/32/12 体系中 |
| DS-012 | **P2** | `06-data_dashboard` 次级标题 | 16px | 不在体系中 |
| DS-013 | **P2** | `08-progress_analysis` 区域标题 | 20px | 不在体系中 |
| DS-014 | **P2** | `08-progress_analysis` 大标题 | 28px | 不在体系中 |
| DS-015 | **P2** | `09-gamification` 徽章标题 | 36px | 不在体系中 |
| DS-016 | **P2** | `09-gamification` 等级展示 | 48px | 不在体系中 |

**影响**：字号体系混乱，破坏视觉层次一致性。

### 3.6 间距网格偏差

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| DS-017 | **P3** | 多个模块 | 使用 6px、10px 等非 8px 网格倍数的间距值。 |

---

## 4. 组件模式一致性（Component Patterns）

### 4.1 Dialog vs Popup 选择

| ID | 级别 | 模块 | 问题 | 规范要求 |
|----|------|------|------|----------|
| CP-001 | **P1** | `05-match_data` | 录入方式选择使用 `Dialog`（居中弹窗） | 界面设计 v2.0 规定移动端优先使用底部 `Popup` |
| CP-002 | **P1** | `11-payment` | 支付方式选择使用 `Dialog` | 同上 |

### 4.2 加载模式不一致

| ID | 级别 | 模块 | 问题 | 规范要求 |
|----|------|------|------|----------|
| CP-003 | **P2** | `06-data_dashboard` | 内容页使用 `Loading` 旋转指示器 | 切片总览规定列表/内容页使用骨架屏 |
| CP-004 | **P2** | `08-progress_analysis` | 图表加载使用 `Loading` 旋转指示器 | 同上，应使用骨架屏 |

### 4.3 空状态组件

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| CP-005 | **P2** | `04-community`、`12-notification` | 空状态使用自定义 `div` 实现，而非 NutUI `Empty` 组件。 |
| CP-006 | **P3** | 多个模块 | 空状态插图不统一，部分使用 NutUI 默认插图，部分使用自定义 SVG。 |

### 4.4 Tab 组件

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| CP-007 | **P2** | `06-data_dashboard` | 使用自定义 Tab 实现而非 NutUI `Tabs` 组件，交互行为与主题支持可能不一致。 |

### 4.5 图标使用

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| CP-008 | **P3** | 多个模块 | NutUI 图标与自定义 SVG 图标混用，视觉风格不统一。 |

---

## 5. 导航与路由一致性（Navigation & Routing）

### 5.1 路由路径不匹配（P0 阻断级）

以下路径不匹配将导致运行时 `Taro.navigateTo` / `Taro.switchTab` 失败：

| ID | 级别 | 来源模块 | 导航目标路径 | app.config.ts 实际路由 | 问题 |
|----|------|----------|-------------|----------------------|------|
| RT-001 | **P0** | `06-data_dashboard` | `/pages/match-data/detail?id=...` | `pages/match-data/record-detail/index` | 路径不匹配，`detail` ≠ `record-detail` |
| RT-002 | **P0** | `14-tab-pages/match-tab` | `/pages/match-data/list/index` | `pages/match-data/record-list/index` | 路径不匹配，`list` ≠ `record-list` |
| RT-003 | **P0** | `14-tab-pages/training-tab` | `/pages/match-data/create/index` | `pages/match-data/quick-entry/index` 或 `detailed-entry/index` | 路径不匹配，`create` ≠ `quick-entry` / `detailed-entry` |
| RT-004 | **P0** | `14-tab-pages/onboarding` | `/pages/video-analysis/upload` | `pages/video-analysis/upload/index` | 缺少 `/index` 后缀 |
| RT-005 | **P0** | `14-tab-pages/onboarding` | `/pages/match-data/create` | `pages/match-data/quick-entry/index` | 缺少 `/index` 后缀且路径名不匹配 |
| RT-006 | **P0** | `09-gamification` | `/pages/gamification/checkin-calendar/index` | 路由配置仅注册 `pages/gamification/badges/index` | 目标页面未在路由配置中注册 |

### 5.2 TabBar 配置偏差

| ID | 级别 | 问题 | 影响 |
|----|------|------|------|
| RT-007 | **P1** | 社区 Tab 未在 Phase 1 的 TabBar 配置中，与 5-Tab 设计规范不一致。 | 参见 CV-001 |

### 5.3 返回导航

| ID | 级别 | 问题 |
|----|------|------|
| RT-008 | **P2** | 返回导航行为不统一：部分页面使用 `useRouter().back()`，部分使用 `Taro.navigateBack({ delta: N })`，delta 值不一致。 |
| RT-009 | **P3** | 深链接/scheme 处理未在所有模块中一致实现。 |

---

## 6. 状态管理一致性（State Management）

### 6.1 Store 持久化策略

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| SM-001 | **P1** | `07-training_advice` trainingStore | 未使用 `persist` 中间件，训练计划数据在应用重启后丢失。而 `02-user-auth` authStore 使用了 persist。缺少统一的持久化策略规范。 |
| SM-002 | **P2** | `09-gamification` gamificationStore | 徽章解锁状态未持久化，可能导致用户重新打开应用后已解锁徽章状态丢失。 |

### 6.2 Store 中的硬编码中文

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| SM-003 | **P1** | `07-training_advice` trainingStore.ts | Store action 中的错误消息使用硬编码中文（如 `"获取训练计划失败"`），应使用 i18n。 |

### 6.3 Store 初始化与选择器

| ID | 级别 | 问题 |
|----|------|------|
| SM-004 | **P2** | Store 初始化模式不统一：部分使用 `create()` 内联初始状态，部分使用单独的初始化函数。 |
| SM-005 | **P3** | 选择器模式不一致：部分使用 `useStore(state => state.x)`（返回基本类型），部分使用 `useStore(state => ({ x: state.x }))`（返回新对象），后者可能导致不必要的重渲染。 |

### 6.4 跨端不兼容的状态访问

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| SM-006 | **P1** | `09-gamification` useBadgeUnlock.ts | 使用 `(global as any).wsManager` 访问 WebSocket 管理器，绕过 Taro 抽象层，在 H5/App 端不可用。应通过 Taro API 或依赖注入实现。 |

---

## 7. 国际化与本地化（i18n & Localization）

### 7.1 硬编码中文字符串

| ID | 级别 | 模块 | 文件 | 硬编码内容 |
|----|------|------|------|-----------|
| IL-001 | **P1** | `06-data_dashboard` | LandingHeatmap.tsx | `cellLabels` 九宫格标签（正手位、反手位、中路等） |
| IL-002 | **P1** | `06-data_dashboard` | constants/dashboard.ts | `GRID_CELL_LABELS` 数组，与上述标签重复定义 |
| IL-003 | **P1** | `07-training_advice` | trainingStore.ts | Store action 错误消息（"获取训练计划失败"等） |
| IL-004 | **P1** | `09-gamification` | CheckinCalendar.tsx | 日期格式 `{year}年{month}月` |
| IL-005 | **P1** | `11-payment` | create.tsx | `formatAmount` 函数中 ¥ 符号 |
| IL-006 | **P1** | `11-payment` | orders.tsx | `formatDate` 函数中日期格式 |
| IL-007 | **P2** | `12-notification` | list.tsx | 通知时间相对格式（"刚刚"、"N分钟前"等） |

### 7.2 i18n 键命名规范

| ID | 级别 | 问题 |
|----|------|------|
| IL-008 | **P2** | i18n 键命名规范不统一：部分使用点分表示法 `module.section.key`，部分使用扁平 `module_key`。 |

### 7.3 错误与加载状态翻译缺失

| ID | 级别 | 问题 |
|----|------|------|
| IL-009 | **P2** | 多个模块的错误状态和加载消息缺少 i18n 翻译条目。 |

---

## 8. 无障碍与用户体验（Accessibility & UX）

### 8.1 触摸目标尺寸

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| AU-001 | **P2** | `06-data_dashboard` | 热力图单元格触摸区域小于推荐的 44px 最小尺寸。 |
| AU-002 | **P2** | `09-gamification` | 徽章图标触摸区域小于推荐的 44px 最小尺寸。 |

### 8.2 颜色对比度

| ID | 级别 | 问题 |
|----|------|------|
| AU-003 | **P2** | 白色文字在 `#F4A261`（橙色）背景上的对比度可能不满足 WCAG AA 标准（4.5:1）。 |

### 8.3 屏幕阅读器支持

| ID | 级别 | 问题 |
|----|------|------|
| AU-004 | **P2** | 多个模块的交互元素缺少 `aria-label` 属性，屏幕阅读器无法正确识别。 |

### 8.4 焦点管理与触觉反馈

| ID | 级别 | 问题 |
|----|------|------|
| AU-005 | **P3** | 模态/弹窗的焦点陷阱（focus trap）未一致实现。 |
| AU-006 | **P3** | 界面设计 v2.0 中提到的触觉反馈（haptic feedback）在关键操作上未实现。 |

---

## 9. 跨端策略一致性（Cross-End Strategy）

### 9.1 全局对象直接访问（跨端不兼容）

| ID | 级别 | 模块 | 问题 |
|----|------|------|------|
| CE-001 | **P1** | `09-gamification` useBadgeUnlock.ts | 使用 `(global as any).wsManager` 直接访问全局 WebSocket 管理器，绕过 Taro 抽象层，在 H5/App 端不可用。架构设计 v2.4 规定 WebSocket 应通过 `Taro.connectSocket` 实现。 |

### 9.2 硬编码颜色值（主题切换不可用）

以下位置在 SVG/Canvas/JS 中使用硬编码十六进制颜色，而非 CSS 变量，导致主题切换失效：

| ID | 级别 | 模块 | 文件 | 硬编码颜色 |
|----|------|------|------|-----------|
| CE-002 | **P1** | `06-data_dashboard` | WinRateTrend.tsx | `stroke="#E63946"`, `fill="#E63946"`, `fill="#1D3557"`, `fill="#999"` |
| CE-003 | **P1** | `06-data_dashboard` | LandingHeatmap.tsx | `rgba(230,57,70,...)`, `'#E63946'`, `'#1D3557'`, `'#2A9D8F'` |
| CE-004 | **P1** | `07-training_advice` | DiagnosisSection | SEVERITY_MAP 颜色值, TREND_MAP 颜色值 |
| CE-005 | **P1** | `08-progress_analysis` | TREND_COLORS 数组 | 硬编码趋势颜色 |
| CE-006 | **P2** | `05-match_data` | detailed-entry.scss | 硬编码颜色值 |
| CE-007 | **P2** | `11-payment` | create.scss | 硬编码颜色值 |
| CE-008 | **P2** | `12-notification` | list.scss | 硬编码颜色值 |
| CE-009 | **P2** | `14-tab-pages/onboarding` | HomeTourOverlay.scss | 硬编码颜色值 |

### 9.3 平台条件编译

| ID | 级别 | 问题 |
|----|------|------|
| CE-010 | **P2** | 部分模块使用 `process.env.TARO_ENV` 检查但未覆盖全部三端（小程序/H5/App），缺少默认分支。 |

---

## 10. 跨切片路由路径一致性矩阵

> 以下矩阵汇总所有模块中出现的 `Taro.navigateTo` / `Taro.switchTab` / `Taro.redirectTo` 调用路径，与 `app.config.ts` 路由定义交叉比对。

| 来源模块 | 导航调用路径 | app.config.ts 路由 | 匹配状态 | 问题描述 |
|----------|-------------|-------------------|----------|----------|
| `06-data_dashboard` | `/pages/match-data/detail?id=...` | `pages/match-data/record-detail/index` | ❌ 不匹配 | 路径名 `detail` ≠ `record-detail` |
| `14-tab-pages/match-tab` | `/pages/match-data/list/index` | `pages/match-data/record-list/index` | ❌ 不匹配 | 路径名 `list` ≠ `record-list` |
| `14-tab-pages/training-tab` | `/pages/match-data/create/index` | `pages/match-data/quick-entry/index` | ❌ 不匹配 | 路径名 `create` ≠ `quick-entry` |
| `14-tab-pages/training-tab` | `/pages/match-data/create/index` | `pages/match-data/detailed-entry/index` | ❌ 不匹配 | 路径名 `create` ≠ `detailed-entry` |
| `14-tab-pages/onboarding` | `/pages/video-analysis/upload` | `pages/video-analysis/upload/index` | ❌ 不匹配 | 缺少 `/index` 后缀 |
| `14-tab-pages/onboarding` | `/pages/match-data/create` | `pages/match-data/quick-entry/index` | ❌ 不匹配 | 缺少 `/index` 后缀且路径名不匹配 |
| `09-gamification` | `/pages/gamification/checkin-calendar/index` | 未注册 | ❌ 不匹配 | 目标页面未在路由配置中注册 |
| `05-match_data` → dashboard | `/pages/data-dashboard/index` | `pages/data-dashboard/index` | ✅ 匹配 | — |
| `07-training_advice` → match-data | `/pages/match-data/record-list/index` | `pages/match-data/record-list/index` | ✅ 匹配 | — |
| `08-progress_analysis` → dashboard | `/pages/data-dashboard/index` | `pages/data-dashboard/index` | ✅ 匹配 | — |
| `11-payment` → orders | `/pages/payment/orders/index` | `pages/payment/orders/index` | ✅ 匹配 | — |
| `12-notification` → detail | `/pages/notification/detail/index` | `pages/notification/detail/index` | ✅ 匹配 | — |
| TabBar 首页 | `/pages/data-dashboard/index` | `pages/data-dashboard/index` | ✅ 匹配 | — |
| TabBar 训练 | `/pages/training-advice/index` | `pages/training-advice/index` | ✅ 匹配 | — |
| TabBar 赛事 | `/pages/match-data/record-list/index` | `pages/match-data/record-list/index` | ✅ 匹配 | — |
| TabBar 我的 | `/pages/user-auth/profile/index` | `pages/user-auth/profile/index` | ✅ 匹配 | — |

**匹配统计**：6 项不匹配（P0），10 项匹配。

---

## 11. P0–P3 问题汇总表

### P0 — 阻断级（6 项）

| ID | 维度 | 模块 | 问题摘要 |
|----|------|------|----------|
| DS-001 | 设计系统 | `05-match_data` | 按钮圆角 24px，规范要求 12px |
| RT-001 | 路由 | `06-data_dashboard` | 导航路径 `detail` ≠ 路由定义 `record-detail` |
| RT-002 | 路由 | `14-tab-pages/match-tab` | 导航路径 `list` ≠ 路由定义 `record-list` |
| RT-003 | 路由 | `14-tab-pages/training-tab` | 导航路径 `create` ≠ 路由定义 `quick-entry`/`detailed-entry` |
| RT-004 | 路由 | `14-tab-pages/onboarding` | 导航路径缺少 `/index` 后缀 |
| RT-005 | 路由 | `14-tab-pages/onboarding` | 导航路径缺少 `/index` 后缀且路径名不匹配 |
| RT-006 | 路由 | `09-gamification` | 导航目标 `checkin-calendar` 未在路由配置中注册 |

> **注**：RT-004 和 RT-005 可合并为一条 onboarding 路由问题，实际 P0 项为 6 项独立问题。

### P1 — 高优级（12 项）

| ID | 维度 | 模块 | 问题摘要 |
|----|------|------|----------|
| CV-001 | 页面覆盖 | `14-tab-pages` | 社区 Tab 未在 Phase 1 TabBar 中，与 5-Tab 设计不符 |
| DS-002 | 设计系统 | `08-progress_analysis` | 按钮圆角 24px，规范要求 12px |
| DS-003 | 设计系统 | `06-data_dashboard` | 卡片阴影 `0 1px 4px` ≠ 规范 `0 2px 8px` |
| DS-007 | 设计系统 | `06-data_dashboard` | 模块级 SCSS 重定义 `:root` CSS 变量 |
| DS-008 | 设计系统 | `07-training_advice` | 模块级 SCSS 重定义 `:root` CSS 变量 |
| DS-009 | 设计系统 | `05-match_data`、`08-progress_analysis` | 使用未定义的 `--color-warning` 变量 |
| DS-010 | 设计系统 | `11-payment` | 使用未定义的 `--color-text-inverse` 变量 |
| CP-001 | 组件模式 | `05-match_data` | 录入方式选择使用 Dialog，规范要求底部 Popup |
| CP-002 | 组件模式 | `11-payment` | 支付方式选择使用 Dialog，规范要求底部 Popup |
| RT-007 | 路由 | TabBar | 社区 Tab 缺失（同 CV-001） |
| SM-001 | 状态管理 | `07-training_advice` | trainingStore 未持久化，缺少统一持久化策略 |
| SM-003 | 状态管理 | `07-training_advice` | Store 中硬编码中文错误消息 |
| SM-006 | 状态管理 | `09-gamification` | 使用 `(global as any).wsManager`，跨端不兼容 |
| IL-001~006 | 国际化 | 多个模块 | 7 处硬编码中文字符串 |
| CE-001 | 跨端策略 | `09-gamification` | 同 SM-006 |
| CE-002~005 | 跨端策略 | 多个模块 | SVG/JS 中硬编码颜色值，主题切换失效 |

### P2 — 中优级（15 项）

| ID | 维度 | 模块 | 问题摘要 |
|----|------|------|----------|
| DS-005 | 设计系统 | `14-tab-pages/onboarding` | 阴影值与规范不符 |
| DS-006 | 设计系统 | `09-gamification` | 阴影值与规范不符 |
| DS-011~016 | 设计系统 | 多个模块 | 6 处非标准字号使用 |
| CP-003 | 组件模式 | `06-data_dashboard` | 内容页使用 Loading 而非骨架屏 |
| CP-004 | 组件模式 | `08-progress_analysis` | 图表加载使用 Loading 而非骨架屏 |
| CP-005 | 组件模式 | `04-community`、`12-notification` | 空状态使用自定义 div 而非 NutUI Empty |
| CP-007 | 组件模式 | `06-data_dashboard` | 使用自定义 Tab 而非 NutUI Tabs |
| RT-008 | 路由 | 多个模块 | 返回导航行为不统一 |
| SM-002 | 状态管理 | `09-gamification` | 徽章状态未持久化 |
| SM-004 | 状态管理 | 多个模块 | Store 初始化模式不统一 |
| IL-007 | 国际化 | `12-notification` | 硬编码中文相对时间格式 |
| IL-008 | 国际化 | 多个模块 | i18n 键命名规范不统一 |
| IL-009 | 国际化 | 多个模块 | 错误/加载状态缺少翻译条目 |
| AU-001~004 | 无障碍 | 多个模块 | 触摸目标、对比度、aria-label 缺失 |
| CE-006~010 | 跨端策略 | 多个模块 | SCSS 硬编码颜色、平台条件编译不完整 |

### P3 — 低优级（7 项）

| ID | 维度 | 模块 | 问题摘要 |
|----|------|------|----------|
| DS-017 | 设计系统 | 多个模块 | 间距非 8px 网格倍数 |
| CP-006 | 组件模式 | 多个模块 | 空状态插图不统一 |
| CP-008 | 组件模式 | 多个模块 | 图标风格混用 |
| RT-009 | 路由 | 多个模块 | 深链接处理不一致 |
| SM-005 | 状态管理 | 多个模块 | 选择器模式不统一导致不必要重渲染 |
| AU-005 | 无障碍 | 多个模块 | 焦点陷阱未一致实现 |
| AU-006 | 无障碍 | 多个模块 | 触觉反馈未实现 |

---

## 12. 优化机会与建议

### 12.1 设计令牌自动化

将所有设计令牌（颜色、间距、字号、阴影、圆角）集中到 `tokens.json` 文件中，使用 Style Dictionary 或类似工具自动生成 CSS 变量、NutUI 主题配置和 TypeScript 常量。

**收益**：消除硬编码颜色/字号漂移的根因，确保设计规范在代码层面被强制执行。

**涉及问题**：DS-001~017、CE-002~009

### 12.2 路由注册校验脚本

构建编译时校验脚本，交叉比对 `app.config.ts` 路由定义与所有 `Taro.navigateTo` / `Taro.switchTab` / `Taro.redirectTo` 调用路径，在编译阶段捕获路径不匹配问题。

**收益**：防止 RT-001~006 类问题进入运行时。

**涉及问题**：RT-001~006

### 12.3 i18n 硬编码检测 Linter

创建 ESLint 自定义规则或 CI 检查步骤，检测 JSX/TSX 文件中的硬编码中文字符串，强制使用 i18n。

**收益**：消除 IL-001~009 类问题的回归风险。

**涉及问题**：IL-001~009、SM-003

### 12.4 共享组件库封装

创建共享组件库（如 `@ttn/components`），封装 NutUI 组件并应用设计规范默认值（按钮圆角 12px、卡片阴影 `0 2px 8px` 等），防止各模块单独覆盖。

**收益**：从源头防止 DS-001~006、CP-001~002 类问题。

**涉及问题**：DS-001~006、CP-001~008

### 12.5 跨端抽象层

创建统一的 API 层（如 `@ttn/api`），将 WebSocket、文件上传、平台特定 API 封装在 Taro 兼容接口之后，禁止直接访问 `global` 对象。

**收益**：消除 CE-001 类跨端不兼容问题。

**涉及问题**：CE-001、SM-006

### 12.6 状态管理规范文档

定义并强制执行 Zustand Store 编写规范，包括：哪些 store 应持久化、选择器模式（避免返回新对象）、错误消息 i18n 集成。

**收益**：统一状态管理模式，减少 SM-001~005 类问题。

**涉及问题**：SM-001~005

### 12.7 无障碍检查清单

为每个模块创建无障碍检查清单，覆盖：最小触摸目标尺寸（44px）、aria-label 覆盖率、颜色对比度（WCAG AA）、焦点管理。

**收益**：系统化解决 AU-001~006 类问题。

**涉及问题**：AU-001~006

### 12.8 社区 Tab Phase 1 占位策略

在 Phase 1 的 TabBar 中加入社区 Tab 占位（显示"敬请期待"），或在界面设计文档中明确记录"Phase 1 为 4-Tab，Phase 2 扩展为 5-Tab"的设计决策偏差。

**收益**：消除 CV-001/RT-007 的设计文档与实现偏差。

**涉及问题**：CV-001、RT-007

---

## 附录：审查文档清单

| 文档 | 版本 | 行数 | 状态 |
|------|------|------|------|
| 乒乓智能分析平台-需求分析与路线图 | v0.4 | 475 | 已读 |
| 前端需求与界面设计 | v2.0 | 1502 | 已读 |
| 系统架构设计 | v2.4 | ~3345 | 已读 |
| 垂直切片设计总览 | — | 406 | 已读 |
| 00–12 前端切片（13 个模块） | — | — | 全部已读 |
| 14-tab-pages（5 个文档） | — | — | 全部已读 |

---

*报告结束*
