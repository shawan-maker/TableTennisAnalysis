# training-tab 模块 — 前端垂直切片设计

> **模块名称**：`training-tab`
> **前端目录**：`frontend/src/pages/training/`
> **定位**：训练 Tab 入口页，聚合 AI 视频分析、数据看板、比赛数据录入、训练建议 4 个入口
> **依据**：前端需求与界面设计 v2.0 §P1.3 / F-3、API 详细设计 v1.3 §4 / §5 / §6 / §7

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §P1.3（训练 Tab 入口聚合页）
- [ ] 确认 4 个入口跳转路由：
  - AI 视频分析 → `/pages/video-analysis/upload/index`
  - 数据看板 → `/pages/dashboard/index`
  - 比赛数据录入 → `/pages/match-data/quick-entry/index`
  - 训练建议 → `/pages/training/advice/index`
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：训练 Tab 入口页 + 路由配置 + i18n

---

## 2. API Service 模块

训练 Tab 入口页为纯导航聚合页，**不调用任何 API**。各入口的详细数据加载在目标页面中完成。

> 如需显示入口最近一条数据预览（如最近分析报告状态），可复用 `services/home.ts` 中的 `getLatestReport()`。本切片默认不加载，保持页面轻量。

---

## 3. 状态管理（Zustand Store）

训练 Tab 入口页为纯导航页，**不需要独立 Store**。如后续需缓存入口预览数据，可扩展 `homeStore` 或新建 `trainingTabStore`。

---

## 4. 页面组件

```tsx
// frontend/src/pages/training/index.tsx
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import './index.scss'

/** 训练入口项定义 */
interface TrainingEntry {
  icon: string
  titleKey: string
  descKey: string
  route: string
  color: string
}

/** 4 个训练入口 */
const TRAINING_ENTRIES: TrainingEntry[] = [
  {
    icon: '🤖',
    titleKey: 'trainingTab.aiAnalysis',
    descKey: 'trainingTab.aiAnalysisDesc',
    route: '/pages/video-analysis/upload/index',
    color: 'var(--color-primary)',
  },
  {
    icon: '📊',
    titleKey: 'trainingTab.dataBoard',
    descKey: 'trainingTab.dataBoardDesc',
    route: '/pages/dashboard/index',
    color: 'var(--color-secondary)',
  },
  {
    icon: '📝',
    titleKey: 'trainingTab.matchEntry',
    descKey: 'trainingTab.matchEntryDesc',
    route: '/pages/match-data/quick-entry/index',
    color: 'var(--color-accent)',
  },
  {
    icon: '💡',
    titleKey: 'trainingTab.advice',
    descKey: 'trainingTab.adviceDesc',
    route: '/pages/training/advice/index',
    color: 'var(--color-success)',
  },
]

export default function TrainingTabPage() {
  const { t } = useTranslation()

  const handleNavigate = (entry: TrainingEntry) => {
    Taro.navigateTo({ url: entry.route })
  }

  return (
    <View className="training-tab-page">
      {/* 页面标题 */}
      <View className="page-header">
        <Text className="page-title">{t('trainingTab.title')}</Text>
        <Text className="page-subtitle">{t('trainingTab.subtitle')}</Text>
      </View>

      {/* 入口列表 */}
      <View className="entry-list">
        {TRAINING_ENTRIES.map((entry, idx) => (
          <View
            className="entry-card"
            key={idx}
            onClick={() => handleNavigate(entry)}
          >
            <View
              className="entry-icon-wrapper"
              style={{ background: `${entry.color}15` }}
            >
              <Text className="entry-icon" style={{ color: entry.color }}>
                {entry.icon}
              </Text>
            </View>
            <View className="entry-content">
              <Text className="entry-title">{t(entry.titleKey)}</Text>
              <Text className="entry-desc">{t(entry.descKey)}</Text>
            </View>
            <Text className="entry-arrow">›</Text>
          </View>
        ))}
      </View>
    </View>
  )
}
```

---

## 5. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/training/index.scss

.training-tab-page {
  min-height: 100vh;
  background: var(--color-background);
  padding: var(--spacing-md);
}

.page-header {
  padding: var(--spacing-lg) 0 var(--spacing-md);

  .page-title {
    display: block;
    font-size: 24px;
    font-weight: bold;
    color: var(--color-text-primary);
  }

  .page-subtitle {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
    margin-top: var(--spacing-xs);
  }
}

.entry-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.entry-card {
  display: flex;
  align-items: center;
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  box-shadow: var(--shadow-card);

  &:active {
    opacity: 0.9;
    transform: scale(0.99);
  }

  .entry-icon-wrapper {
    width: 48px;
    height: 48px;
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-right: var(--spacing-md);

    .entry-icon {
      font-size: 24px;
    }
  }

  .entry-content {
    flex: 1;

    .entry-title {
      display: block;
      font-size: 18px;
      font-weight: 600;
      color: var(--color-text-primary);
      margin-bottom: var(--spacing-xs);
    }

    .entry-desc {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
  }

  .entry-arrow {
    font-size: 24px;
    color: var(--color-text-secondary);
    flex-shrink: 0;
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 training tab 入口页）
export default {
  pages: [
    'pages/home/index',
    'pages/training/index',        // 新增：训练 Tab 入口页
    'pages/training/advice/index', // 训练建议页
    'pages/video-analysis/upload/index',
    'pages/dashboard/index',
    'pages/match-data/quick-entry/index',
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增 trainingTab 段）
{
  "trainingTab": {
    "title": "训练",
    "subtitle": "选择训练方式，提升你的球技",
    "aiAnalysis": "AI 视频分析",
    "aiAnalysisDesc": "上传比赛视频，AI 智能分析技术动作与战术",
    "dataBoard": "数据看板",
    "dataBoardDesc": "查看战绩趋势、技术统计、落点热图",
    "matchEntry": "比赛数据录入",
    "matchEntryDesc": "手动录入比赛结果，积累数据资产",
    "advice": "训练建议",
    "adviceDesc": "基于数据分析的个性化训练指导"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增 trainingTab 段）
{
  "trainingTab": {
    "title": "Training",
    "subtitle": "Choose your training method",
    "aiAnalysis": "AI Video Analysis",
    "aiAnalysisDesc": "Upload match video for AI analysis of technique and tactics",
    "dataBoard": "Data Dashboard",
    "dataBoardDesc": "View win rate trends, technique stats, landing heatmap",
    "matchEntry": "Match Data Entry",
    "matchEntryDesc": "Manually record match results to build data assets",
    "advice": "Training Advice",
    "adviceDesc": "Personalized training guidance based on data analysis"
  }
}
```

### 常量定义

```typescript
// frontend/src/constants/trainingTab.ts

/** 训练入口路由映射 */
export const TRAINING_ROUTES = {
  aiAnalysis: '/pages/video-analysis/upload/index',
  dataBoard: '/pages/dashboard/index',
  matchEntry: '/pages/match-data/quick-entry/index',
  advice: '/pages/training/advice/index',
} as const
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 页面标题 "训练" + 副标题
- [ ] 4 个入口卡片纵向排列，每个有独立颜色图标背景
- [ ] AI 分析入口图标红色背景（#E63946）
- [ ] 数据看板入口图标深蓝背景（#1D3557）
- [ ] 比赛录入入口图标橙黄背景（#F4A261）
- [ ] 训练建议入口图标绿色背景（#2A9D8F）
- [ ] 每个入口卡片有右侧箭头
- [ ] 点击有缩放反馈动画
- [ ] 卡片圆角 12px，8px 间距

### 功能验证
- [ ] 点击 AI 视频分析跳转到 upload 页
- [ ] 点击数据看板跳转到 dashboard 页
- [ ] 点击比赛数据录入跳转到 create 页
- [ ] 点击训练建议跳转到 advice 页
- [ ] 页面无 API 调用，纯静态导航

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 9. 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 入口路由通过常量定义，**禁止** 在组件中硬编码路由字符串
- **ALL** 颜色使用 CSS 变量，**禁止** 硬编码颜色值（emoji 除外）
- **ALL** 图标背景色使用对应入口色的 15% 透明度（`${color}15`）
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **禁止** 在入口页做 API 调用（纯导航页）
- **禁止** 在入口页做数据处理逻辑
