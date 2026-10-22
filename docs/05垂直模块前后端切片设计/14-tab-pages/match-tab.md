# match-tab 模块 — 前端垂直切片设计

> **模块名称**：`match-tab`
> **前端目录**：`frontend/src/pages/match/`
> **定位**：赛事 Tab 入口页，聚合记分牌入口和比赛记录入口，每个入口显示最近一条数据预览
> **依据**：前端需求与界面设计 v2.0 §P1.4 / F-4、API 详细设计 v1.3 §5.4 / §5.6

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §P1.4（赛事 Tab 入口聚合页）
- [ ] 确认 2 个入口跳转路由：
  - 记分牌 → `/pages/scoring/setup/index`
  - 比赛记录 → `/pages/match-data/record-list/index`
- [ ] 阅读本模块涉及的 API 契约：
  - §5.4 GET /match-data（最近 1 条比赛记录，用于预览）
  - §4.x GET /scoring/current（当前进行中的记分牌，用于预览）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：赛事 Tab 入口页 + matchTabStore + 路由配置 + i18n

---

## 2. API Service 模块

```typescript
// frontend/src/services/matchTab.ts
import request from './request'

/** 最近比赛记录预览 */
export interface LatestMatchPreview {
  id: number
  opponent_name: string | null
  my_score: number
  opponent_score: number
  is_win: boolean
  match_date: string
  match_type: string
}

/** 当前进行中的记分牌 */
export interface CurrentScoringPreview {
  id: number
  my_name: string
  opponent_name: string
  my_score: number
  opponent_score: number
  status: string  // ongoing / paused / finished
  started_at: string
}

/**
 * 获取最近 1 条比赛记录（用于赛事 Tab 预览）。
 */
export function getLatestMatch() {
  return request.get('/match-data/records', { page: 1, page_size: 1 })
}

/**
 * 获取当前进行中的记分牌（用于赛事 Tab 预览）。
 * 如无进行中的比赛返回空。
 */
export function getCurrentScoring() {
  return request.get('/scoring/current')
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/matchTabStore.ts
import { create } from 'zustand'
import * as matchTabApi from '@/services/matchTab'
import type { LatestMatchPreview, CurrentScoringPreview } from '@/services/matchTab'

interface MatchTabState {
  latestMatch: LatestMatchPreview | null
  latestMatchLoading: boolean

  currentScoring: CurrentScoringPreview | null
  currentScoringLoading: boolean

  fetchLatestMatch: () => Promise<void>
  fetchCurrentScoring: () => Promise<void>
  refreshAll: () => Promise<void>
}

export const useMatchTabStore = create<MatchTabState>((set, get) => ({
  latestMatch: null,
  latestMatchLoading: false,
  currentScoring: null,
  currentScoringLoading: false,

  fetchLatestMatch: async () => {
    set({ latestMatchLoading: true })
    try {
      const res = await matchTabApi.getLatestMatch()
      const items: LatestMatchPreview[] = res.data.data.items || []
      set({ latestMatch: items.length > 0 ? items[0] : null })
    } catch {
      set({ latestMatch: null })
    } finally {
      set({ latestMatchLoading: false })
    }
  },

  fetchCurrentScoring: async () => {
    set({ currentScoringLoading: true })
    try {
      const res = await matchTabApi.getCurrentScoring()
      set({ currentScoring: res.data.data || null })
    } catch {
      set({ currentScoring: null })
    } finally {
      set({ currentScoringLoading: false })
    }
  },

  refreshAll: async () => {
    await Promise.all([
      get().fetchLatestMatch(),
      get().fetchCurrentScoring(),
    ])
  },
}))
```

---

## 4. 页面组件

```tsx
// frontend/src/pages/match/index.tsx
import { useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useMatchTabStore } from '@/stores/matchTabStore'
import './index.scss'

/** 赛事入口项 */
interface MatchEntry {
  icon: string
  titleKey: string
  descKey: string
  route: string
  color: string
}

const MATCH_ENTRIES: MatchEntry[] = [
  {
    icon: '🏓',
    titleKey: 'matchTab.scoreboard',
    descKey: 'matchTab.scoreboardDesc',
    route: '/pages/scoring/setup/index',
    color: 'var(--color-primary)',
  },
  {
    icon: '📋',
    titleKey: 'matchTab.matchRecords',
    descKey: 'matchTab.matchRecordsDesc',
    route: '/pages/match-data/record-list/index',
    color: 'var(--color-secondary)',
  },
]

export default function MatchTabPage() {
  const { t } = useTranslation()
  const {
    latestMatch,
    latestMatchLoading,
    currentScoring,
    currentScoringLoading,
    refreshAll,
  } = useMatchTabStore()

  useEffect(() => {
    refreshAll()
  }, [])

  /** 记分牌预览内容 */
  const scoringPreview = () => {
    if (currentScoringLoading) {
      return <Skeleton width="80%" height="16px" animated />
    }
    if (currentScoring) {
      return (
        <View className="preview-row">
          <Text className="preview-score">
            {currentScoring.my_score} - {currentScoring.opponent_score}
          </Text>
          {currentScoring.status === 'ongoing' && (
            <Text className="preview-badge ongoing">
              {t('matchTab.ongoing')}
            </Text>
          )}
        </View>
      )
    }
    return <Text className="preview-empty">{t('matchTab.noScoring')}</Text>
  }

  /** 比赛记录预览内容 */
  const matchPreview = () => {
    if (latestMatchLoading) {
      return <Skeleton width="80%" height="16px" animated />
    }
    if (latestMatch) {
      return (
        <View className="preview-row">
          <Text className="preview-score">
            {latestMatch.my_score} - {latestMatch.opponent_score}
          </Text>
          <Text className={`preview-result ${latestMatch.is_win ? 'win' : 'lose'}`}>
            {latestMatch.is_win ? t('matchTab.win') : t('matchTab.lose')}
          </Text>
        </View>
      )
    }
    return <Text className="preview-empty">{t('matchTab.noMatch')}</Text>
  }

  const handleNavigate = (entry: MatchEntry) => {
    Taro.navigateTo({ url: entry.route })
  }

  return (
    <View className="match-tab-page">
      {/* 页面标题 */}
      <View className="page-header">
        <Text className="page-title">{t('matchTab.title')}</Text>
        <Text className="page-subtitle">{t('matchTab.subtitle')}</Text>
      </View>

      {/* 记分牌入口 */}
      <View
        className="entry-card"
        onClick={() => handleNavigate(MATCH_ENTRIES[0])}
      >
        <View
          className="entry-icon-wrapper"
          style={{ background: 'var(--color-primary)15' }}
        >
          <Text className="entry-icon" style={{ color: 'var(--color-primary)' }}>
            {MATCH_ENTRIES[0].icon}
          </Text>
        </View>
        <View className="entry-content">
          <Text className="entry-title">{t(MATCH_ENTRIES[0].titleKey)}</Text>
          <Text className="entry-desc">{t(MATCH_ENTRIES[0].descKey)}</Text>
          <View className="entry-preview">{scoringPreview()}</View>
        </View>
        <Text className="entry-arrow">›</Text>
      </View>

      {/* 比赛记录入口 */}
      <View
        className="entry-card"
        onClick={() => handleNavigate(MATCH_ENTRIES[1])}
      >
        <View
          className="entry-icon-wrapper"
          style={{ background: 'var(--color-secondary)15' }}
        >
          <Text className="entry-icon" style={{ color: 'var(--color-secondary)' }}>
            {MATCH_ENTRIES[1].icon}
          </Text>
        </View>
        <View className="entry-content">
          <Text className="entry-title">{t(MATCH_ENTRIES[1].titleKey)}</Text>
          <Text className="entry-desc">{t(MATCH_ENTRIES[1].descKey)}</Text>
          <View className="entry-preview">{matchPreview()}</View>
        </View>
        <Text className="entry-arrow">›</Text>
      </View>
    </View>
  )
}
```

---

## 5. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/match/index.scss

.match-tab-page {
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

.entry-card {
  display: flex;
  align-items: center;
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
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
      margin-bottom: var(--spacing-xs);
    }

    .entry-preview {
      .preview-row {
        display: flex;
        align-items: center;
        gap: var(--spacing-sm);
      }

      .preview-score {
        font-size: 13px;
        font-weight: bold;
        color: var(--color-text-primary);
      }

      .preview-badge {
        font-size: 12px;
        padding: var(--spacing-xs) var(--spacing-xs); /* P3-fix: 2px→var(--spacing-xs) */
        border-radius: var(--radius-sm);

        &.ongoing {
          background: var(--color-success);
          color: var(--color-text-inverse);
        }
      }

      .preview-result {
        font-size: 12px;

        &.win { color: var(--color-success); }
        &.lose { color: var(--color-primary); }
      }

      .preview-empty {
        font-size: 12px;
        color: var(--color-text-secondary);
      }
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
// frontend/src/app.config.ts（新增 match tab 入口页）
export default {
  pages: [
    'pages/home/index',
    'pages/match/index',         // 新增：赛事 Tab 入口页
    'pages/scoring/setup/index',
    'pages/match-data/record-list/index',
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增 matchTab 段）
{
  "matchTab": {
    "title": "赛事",
    "subtitle": "记分与比赛记录管理",
    "scoreboard": "记分牌",
    "scoreboardDesc": "实时比赛记分，支持多局制",
    "matchRecords": "比赛记录",
    "matchRecordsDesc": "查看所有比赛数据与历史",
    "ongoing": "进行中",
    "win": "胜",
    "lose": "负",
    "noScoring": "暂无进行中的比赛",
    "noMatch": "暂无比赛记录"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增 matchTab 段）
{
  "matchTab": {
    "title": "Matches",
    "subtitle": "Scoring and match records",
    "scoreboard": "Scoreboard",
    "scoreboardDesc": "Live match scoring, multi-game support",
    "matchRecords": "Match Records",
    "matchRecordsDesc": "View all match data and history",
    "ongoing": "Ongoing",
    "win": "Win",
    "lose": "Loss",
    "noScoring": "No ongoing match",
    "noMatch": "No match records yet"
  }
}
```

### 常量定义

```typescript
// frontend/src/constants/matchTab.ts

/** 赛事入口路由映射 */
export const MATCH_ROUTES = {
  scoreboard: '/pages/scoring/setup/index',
  matchRecords: '/pages/match-data/record-list/index',
} as const
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 页面标题 "赛事" + 副标题
- [ ] 记分牌入口红色图标背景（#E63946）
- [ ] 比赛记录入口深蓝图标背景（#1D3557）
- [ ] 每个入口卡片底部显示预览数据
- [ ] 进行中比赛显示 "进行中" 绿色标签
- [ ] 比赛结果显示胜绿色 / 负红色
- [ ] 无数据时显示引导文字
- [ ] 加载中显示 Skeleton
- [ ] 卡片圆角 12px，8px 间距

### 功能验证
- [ ] 页面加载时并发请求 2 个 API（latestMatch + currentScoring）
- [ ] 单个 API 失败不阻塞另一个预览
- [ ] 点击记分牌入口跳转到 setup 页
- [ ] 点击比赛记录入口跳转到 list 页
- [ ] 有进行中比赛时显示当前比分

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 9. 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/matchTab.ts` 封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 颜色使用 CSS 变量，**禁止** 硬编码颜色值（emoji 除外）
- **ALL** 预览数据加载失败**不得**阻塞入口卡片渲染（catch 后显示空状态）
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **禁止** 在入口页做完整列表加载（仅取最近 1 条预览）
