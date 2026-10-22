# data_dashboard 模块 — 前端垂直切片设计

> **模块名称**：`data_dashboard`
> **前端目录**：`frontend/src/pages/dashboard/` + `frontend/src/services/dashboard.ts` + `frontend/src/stores/dashboardStore.ts`
> **定位**：数据看板首页，聚合展示概览卡片、战绩趋势折线图、技术统计环形图、累计落点热图、比赛记录列表
> **依据**：前端需求与界面设计 v2.0 T2.4 / v1.0 P1.9、API 详细设计 v1.3 §6

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 T2.4（数据看板，引用 v1.0 P1.9）
- [ ] 阅读 v1.0 P1.9（页面结构：时间筛选 + 战绩趋势 + 技术统计 + 落点热图 + 比赛记录）
- [ ] 阅读本模块的 API 契约（§6.1-6.5，5 个端点）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：数据看板首页 + dashboard Service + dashboardStore

---

## 2. API Service 模块

```typescript
// frontend/src/services/dashboard.ts
import request from './request'

/** 响应类型定义 */
export interface AdviceSummary {
  report_id: number
  summary: string
  has_unresolved_issues: boolean
  latest_report_at: string
}

export interface OverviewData {
  win_rate: number
  wins: number
  losses: number
  analysis_count: number
  training_frequency_per_week: number
  streak_days: number
  trend: string  // up/down/flat
  latest_advice_summary: AdviceSummary | null
}

export interface TrendSeries {
  name: string
  data: number[]
}

export interface WinRateTrendData {
  labels: string[]
  series: TrendSeries[]
}

export interface TechniqueItem {
  name: string
  value: number
  color: string
}

export interface TechniqueStatsData {
  technique_distribution: TechniqueItem[]
}

export interface LandingHeatmapData {
  nine_grid: number[][]
  distribution: { forehand: number; backhand: number; middle: number }
  total_rallies: number
  source_reports_count: number
}

export interface MatchRecordItem {
  id: number
  opponent_name: string | null
  opponent_rating: number | null
  my_score: number
  opponent_score: number
  is_win: boolean
  format: string
  match_type: string
  match_date: string
}

export interface MatchRecordsData {
  total: number
  page: number
  page_size: number
  items: MatchRecordItem[]
}

/**
 * 获取概览卡片数据。
 * 缓存 5min（后端 Redis）。
 */
export function getOverview() {
  return request.get('/dashboard/overview')
}

/**
 * 获取战绩趋势折线图数据。
 * @param period - 时间范围：month/quarter/year
 */
export function getWinRateTrend(period: 'month' | 'quarter' | 'year' = 'month') {
  return request.get('/dashboard/win-rate-trend', { period })
}

/**
 * 获取技术统计环形图数据。
 */
export function getTechniqueStats() {
  return request.get('/dashboard/technique-stats')
}

/**
 * 获取累计落点热图数据。
 */
export function getLandingHeatmap() {
  return request.get('/dashboard/landing-heatmap')
}

/**
 * 获取比赛记录列表。
 * @param result - 筛选：win/lose/all
 * @param page - 页码
 * @param pageSize - 每页条数
 */
export function getMatchRecords(
  result: 'win' | 'lose' | 'all' = 'all',
  page: number = 1,
  pageSize: number = 20,
) {
  return request.get('/dashboard/match-records', {
    result,
    page,
    page_size: pageSize,
  })
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/dashboardStore.ts
import { create } from 'zustand'
import * as dashboardApi from '@/services/dashboard'
import type {
  OverviewData,
  WinRateTrendData,
  TechniqueStatsData,
  LandingHeatmapData,
  MatchRecordsData,
  MatchRecordItem,
} from '@/services/dashboard'

type Period = 'month' | 'quarter' | 'year'
type ResultFilter = 'win' | 'lose' | 'all'

interface DashboardState {
  // 概览
  overview: OverviewData | null
  overviewLoading: boolean

  // 战绩趋势
  winRateTrend: WinRateTrendData | null
  trendPeriod: Period
  trendLoading: boolean

  // 技术统计
  techniqueStats: TechniqueStatsData | null
  techniqueLoading: boolean

  // 落点热图
  heatmap: LandingHeatmapData | null
  heatmapLoading: boolean

  // 比赛记录
  matchRecords: MatchRecordItem[]
  matchTotal: number
  matchPage: number
  matchPageSize: number
  matchFilter: ResultFilter
  matchLoading: boolean
  matchHasMore: boolean

  // Actions
  fetchOverview: () => Promise<void>
  fetchWinRateTrend: (period?: Period) => Promise<void>
  fetchTechniqueStats: () => Promise<void>
  fetchLandingHeatmap: () => Promise<void>
  fetchMatchRecords: (refresh?: boolean) => Promise<void>
  setTrendPeriod: (period: Period) => void
  setMatchFilter: (filter: ResultFilter) => void
  loadMoreMatches: () => Promise<void>
  refreshAll: () => Promise<void>
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  overview: null,
  overviewLoading: false,

  winRateTrend: null,
  trendPeriod: 'month',
  trendLoading: false,

  techniqueStats: null,
  techniqueLoading: false,

  heatmap: null,
  heatmapLoading: false,

  matchRecords: [],
  matchTotal: 0,
  matchPage: 1,
  matchPageSize: 20,
  matchFilter: 'all',
  matchLoading: false,
  matchHasMore: false,

  fetchOverview: async () => {
    set({ overviewLoading: true })
    try {
      const res = await dashboardApi.getOverview()
      set({ overview: res.data.data })
    } catch (err) {
      console.error('Failed to fetch overview:', err)
    } finally {
      set({ overviewLoading: false })
    }
  },

  fetchWinRateTrend: async (period?: Period) => {
    const p = period ?? get().trendPeriod
    set({ trendLoading: true })
    try {
      const res = await dashboardApi.getWinRateTrend(p)
      set({ winRateTrend: res.data.data, trendPeriod: p })
    } catch (err) {
      console.error('Failed to fetch win rate trend:', err)
    } finally {
      set({ trendLoading: false })
    }
  },

  fetchTechniqueStats: async () => {
    set({ techniqueLoading: true })
    try {
      const res = await dashboardApi.getTechniqueStats()
      set({ techniqueStats: res.data.data })
    } catch (err) {
      console.error('Failed to fetch technique stats:', err)
    } finally {
      set({ techniqueLoading: false })
    }
  },

  fetchLandingHeatmap: async () => {
    set({ heatmapLoading: true })
    try {
      const res = await dashboardApi.getLandingHeatmap()
      set({ heatmap: res.data.data })
    } catch (err) {
      console.error('Failed to fetch landing heatmap:', err)
    } finally {
      set({ heatmapLoading: false })
    }
  },

  fetchMatchRecords: async (refresh: boolean = false) => {
    const { matchPage, matchPageSize, matchFilter } = get()
    const page = refresh ? 1 : matchPage
    set({ matchLoading: true })
    try {
      const res = await dashboardApi.getMatchRecords(matchFilter, page, matchPageSize)
      const data: MatchRecordsData = res.data.data
      set((state) => ({
        matchRecords: refresh ? data.items : [...state.matchRecords, ...data.items],
        matchTotal: data.total,
        matchPage: page,
        matchHasMore: page * matchPageSize < data.total,
      }))
    } catch (err) {
      console.error('Failed to fetch match records:', err)
    } finally {
      set({ matchLoading: false })
    }
  },

  setTrendPeriod: (period: Period) => {
    set({ trendPeriod: period })
    get().fetchWinRateTrend(period)
  },

  setMatchFilter: (filter: ResultFilter) => {
    set({ matchFilter: filter })
    get().fetchMatchRecords(true)
  },

  loadMoreMatches: async () => {
    const { matchPage, matchHasMore, matchLoading } = get()
    if (!matchHasMore || matchLoading) return
    set({ matchPage: matchPage + 1 })
    await get().fetchMatchRecords(false)
  },

  refreshAll: async () => {
    await Promise.all([
      get().fetchOverview(),
      get().fetchWinRateTrend(),
      get().fetchTechniqueStats(),
      get().fetchLandingHeatmap(),
      get().fetchMatchRecords(true),
    ])
  },
}))
```

---

## 4. 页面组件

### 4.1 数据看板首页

```tsx
// frontend/src/pages/dashboard/index.tsx
import { useEffect, useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Cell, Tabs, Empty, Skeleton, PullRefresh } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useDashboardStore } from '@/stores/dashboardStore'
import OverviewCards from './components/OverviewCards'
import WinRateTrend from './components/WinRateTrend'
import TechniqueStats from './components/TechniqueStats'
import LandingHeatmap from './components/LandingHeatmap'
import MatchRecordList from './components/MatchRecordList'
import './index.scss'

export default function DashboardPage() {
  const { t } = useTranslation()
  const store = useDashboardStore()
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    store.refreshAll()
  }, [])

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await store.refreshAll()
    } catch (err) {
      console.error('Failed to refresh dashboard:', err)
    } finally {
      setRefreshing(false)
    }
  }, [store])

  return (
    <View className="dashboard-page">
      {/* 页面标题 */}
      <View className="dashboard-header">
        <Text className="dashboard-title">{t('dashboard.title')}</Text>
      </View>

      <PullRefresh onRefresh={handleRefresh} refreshing={refreshing}>
        <ScrollView scrollY className="dashboard-scroll">
          {/* 概览卡片 */}
          <OverviewCards
            data={store.overview}
            loading={store.overviewLoading}
          />

          {/* 战绩趋势 */}
          <WinRateTrend
            data={store.winRateTrend}
            period={store.trendPeriod}
            loading={store.trendLoading}
            onPeriodChange={store.setTrendPeriod}
          />

          {/* 技术统计 */}
          <TechniqueStats
            data={store.techniqueStats}
            loading={store.techniqueLoading}
          />

          {/* 累计落点热图 */}
          <LandingHeatmap
            data={store.heatmap}
            loading={store.heatmapLoading}
          />

          {/* 比赛记录列表 */}
          <MatchRecordList
            items={store.matchRecords}
            total={store.matchTotal}
            filter={store.matchFilter}
            loading={store.matchLoading}
            hasMore={store.matchHasMore}
            onFilterChange={store.setMatchFilter}
            onLoadMore={store.loadMoreMatches}
          />
        </ScrollView>
      </PullRefresh>
    </View>
  )
}
```

### 4.2 概览卡片组件

```tsx
// frontend/src/pages/dashboard/components/OverviewCards.tsx
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { OverviewData } from '@/services/dashboard'
import './OverviewCards.scss'

interface Props {
  data: OverviewData | null
  loading: boolean
}

export default function OverviewCards({ data, loading }: Props) {
  const { t } = useTranslation()

  if (loading && !data) {
    return (
      <View className="overview-cards">
        {[0, 1, 2].map((i) => (
          <View className="overview-card" key={i}>
            <Skeleton width="60%" height="32px" animated />
            <Skeleton width="40%" height="20px" animated />
          </View>
        ))}
      </View>
    )
  }

  if (!data) return null

  const trendIcon = data.trend === 'up' ? '↑' : data.trend === 'down' ? '↓' : '→'
  const trendColor = data.trend === 'up' ? 'trend-up' : data.trend === 'down' ? 'trend-down' : 'trend-flat'

  return (
    <View className="overview-cards">
      {/* 胜率卡片 */}
      <View className="overview-card card-winrate">
        <Text className="card-label">{t('dashboard.winRate')}</Text>
        <Text className="card-value">{(data.win_rate * 100).toFixed(0)}%</Text>
        <Text className="card-sub">
          {data.wins}{t('dashboard.wins')} / {data.losses}{t('dashboard.losses')}
          <Text className={`trend-icon ${trendColor}`}>{trendIcon}</Text>
        </Text>
      </View>

      {/* 分析次数卡片 */}
      <View className="overview-card card-analysis">
        <Text className="card-label">{t('dashboard.analysisCount')}</Text>
        <Text className="card-value">{data.analysis_count}</Text>
        <Text className="card-sub">{t('dashboard.times')}</Text>
      </View>

      {/* 训练频次卡片 */}
      <View className="overview-card card-training">
        <Text className="card-label">{t('dashboard.trainingFreq')}</Text>
        <Text className="card-value">{data.training_frequency_per_week}</Text>
        <Text className="card-sub">{t('dashboard.timesPerWeek')}</Text>
      </View>

      {/* 连续天数卡片 */}
      <View className="overview-card card-streak">
        <Text className="card-label">{t('dashboard.streakDays')}</Text>
        <Text className="card-value">{data.streak_days}</Text>
        <Text className="card-sub">{t('dashboard.days')}</Text>
      </View>

      {/* 训练提醒 */}
      {data.latest_advice_summary && (
        <View className="advice-banner">
          <Text className="advice-text">
            {data.latest_advice_summary.summary}
          </Text>
          {data.latest_advice_summary.has_unresolved_issues && (
            <Text className="advice-tag">{t('dashboard.hasIssues')}</Text>
          )}
        </View>
      )}
    </View>
  )
}
```

### 4.3 战绩趋势折线图

```tsx
// frontend/src/pages/dashboard/components/WinRateTrend.tsx
import { View, Text } from '@tarojs/components'
import { Tabs, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { WinRateTrendData } from '@/services/dashboard'
import './WinRateTrend.scss'

interface Props {
  data: WinRateTrendData | null
  period: 'month' | 'quarter' | 'year'
  loading: boolean
  onPeriodChange: (period: 'month' | 'quarter' | 'year') => void
}

export default function WinRateTrend({ data, period, loading, onPeriodChange }: Props) {
  const { t } = useTranslation()

  const periodOptions: Array<{ key: 'month' | 'quarter' | 'year'; label: string }> = [
    { key: 'month', label: t('dashboard.month') },
    { key: 'quarter', label: t('dashboard.quarter') },
    { key: 'year', label: t('dashboard.year') },
  ]

  return (
    <View className="win-rate-trend">
      <View className="section-header">
        <Text className="section-title">📈 {t('dashboard.winRateTrend')}</Text>
      </View>

      <Tabs
        value={period}
        onChange={(val) => onPeriodChange(val as 'month' | 'quarter' | 'year')}
      >
        {periodOptions.map((opt) => (
          <Tabs.TabPane key={opt.key} title={opt.label} value={opt.key} />
        ))}
      </Tabs>

      {loading || !data ? (
        <Skeleton rows={3} animated />
      ) : data.labels.length === 0 ? (
        <View className="chart-empty">
          <Text>{t('dashboard.noMatchData')}</Text>
        </View>
      ) : (
        <View className="chart-container">
          {/* 折线图：使用 ECharts Taro 封装或自定义 Canvas 绘制 */}
          <TrendChart data={data} />
        </View>
      )}
    </View>
  )
}

/** 简易折线图组件（实际可用 echarts-taro3 或自绘 Canvas） */
function TrendChart({ data }: { data: WinRateTrendData }) {
  const { t } = useTranslation()
  const winRateSeries = data.series.find((s) => s.name === t('dashboard.winRate'))
  const winRates = winRateSeries?.data ?? []
  const maxRate = Math.max(...winRates, 1)
  const chartHeight = 160
  const chartWidth = 320
  const stepX = data.labels.length > 1 ? chartWidth / (data.labels.length - 1) : chartWidth

  const points = winRates.map((rate, i) => ({
    x: i * stepX,
    y: chartHeight - (rate / maxRate) * chartHeight,
  }))

  const pathStr = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

  return (
    <View className="trend-chart">
      {/* 跨端兼容说明：H5 端使用原生 SVG，小程序端需替换为 Canvas 或 echarts-taro3 */}
      {/* 开发阶段根据 TARO_ENV 条件编译选择渲染方案 */}
      <svg viewBox={`0 0 ${chartWidth} ${chartHeight + 30}`} className="chart-svg">
        {/* 折线 */}
        <path d={pathStr} fill="none" stroke="var(--color-primary)" strokeWidth="2" />
        {/* 数据点 */}
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="var(--color-primary)" />
        ))}
        {/* X 轴标签 */}
        {data.labels.map((label, i) => (
          <text key={i} x={i * stepX} y={chartHeight + 15} fontSize="12" fill="var(--color-text-secondary)" textAnchor="middle">
            {label}
          </text>
        ))}
      </svg>
    </View>
  )
}
```

### 4.4 技术统计环形图

```tsx
// frontend/src/pages/dashboard/components/TechniqueStats.tsx
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { TechniqueStatsData } from '@/services/dashboard'
import './TechniqueStats.scss'

interface Props {
  data: TechniqueStatsData | null
  loading: boolean
}

export default function TechniqueStats({ data, loading }: Props) {
  const { t } = useTranslation()

  if (loading || !data) {
    return (
      <View className="technique-stats">
        <Text className="section-title">🏓 {t('dashboard.techniqueStats')}</Text>
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const items = data.technique_distribution
  const total = items.reduce((sum, item) => sum + item.value, 0)

  if (total === 0) {
    return (
      <View className="technique-stats">
        <Text className="section-title">🏓 {t('dashboard.techniqueStats')}</Text>
        <View className="empty-state">
          <Text>{t('dashboard.noTechniqueData')}</Text>
        </View>
      </View>
    )
  }

  // 计算环形图 SVG 弧线参数
  const radius = 60
  const circumference = 2 * Math.PI * radius
  let offset = 0
  const arcs = items.map((item) => {
    const percentage = item.value / total
    const arc = {
      ...item,
      percentage,
      dashArray: `${percentage * circumference} ${circumference}`,
      dashOffset: -offset * circumference,
    }
    offset += percentage
    return arc
  })

  return (
    <View className="technique-stats">
      <Text className="section-title">🏓 {t('dashboard.techniqueStats')}</Text>
      <View className="technique-content">
        {/* 环形图 SVG */}
        <View className="donut-chart">
          <svg viewBox="0 0 160 160" className="donut-svg">
            {arcs.map((arc, i) => (
              <circle
                key={i}
                cx="80" cy="80" r={radius}
                fill="none"
                stroke={arc.color}
                strokeWidth="20"
                strokeDasharray={arc.dashArray}
                strokeDashoffset={arc.dashOffset}
                transform="rotate(-90 80 80)"
              />
            ))}
            <text x="80" y="78" textAnchor="middle" fontSize="13" fill="var(--color-secondary)" fontWeight="bold">
              {t('dashboard.total')}
            </text>
            <text x="80" y="95" textAnchor="middle" fontSize="18" fill="var(--color-secondary)" fontWeight="bold">
              {total}
            </text>
          </svg>
        </View>

        {/* 图例 */}
        <View className="legend-list">
          {arcs.map((arc, i) => (
            <View className="legend-item" key={i}>
              <View className="legend-dot" style={{ background: arc.color }} />
              <Text className="legend-name">{arc.name}</Text>
              <Text className="legend-value">
                {arc.value} ({(arc.percentage * 100).toFixed(0)}%)
              </Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  )
}
```

### 4.5 累计落点热图

```tsx
// frontend/src/pages/dashboard/components/LandingHeatmap.tsx
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { LandingHeatmapData } from '@/services/dashboard'
import './LandingHeatmap.scss'

interface Props {
  data: LandingHeatmapData | null
  loading: boolean
}

export default function LandingHeatmap({ data, loading }: Props) {
  const { t } = useTranslation()

  if (loading || !data) {
    return (
      <View className="landing-heatmap">
        <Text className="section-title">🎯 {t('dashboard.landingHeatmap')}</Text>
        <Skeleton rows={3} animated />
      </View>
    )
  }

  if (data.total_rallies === 0) {
    return (
      <View className="landing-heatmap">
        <Text className="section-title">🎯 {t('dashboard.landingHeatmap')}</Text>
        <View className="empty-state">
          <Text>{t('dashboard.noHeatmapData')}</Text>
        </View>
      </View>
    )
  }

  const grid = data.nine_grid
  const flatValues = grid.flat()
  const maxVal = Math.max(...flatValues)

  // 根据值计算颜色深浅（红→浅红→白）
  // --color-primary #E63946，JS 中无法直接使用 CSS 变量，统一引用主色 RGB 值
  const PRIMARY_RGB = '230, 57, 70'
  const getCellColor = (val: number) => {
    if (maxVal === 0) return `rgba(${PRIMARY_RGB}, 0)`
    const intensity = val / maxVal
    return `rgba(${PRIMARY_RGB}, ${0.15 + intensity * 0.85})`
  }

  const cellLabels = [
    'dashboard.cell.leftShort', 'dashboard.cell.midShort', 'dashboard.cell.rightShort',
    'dashboard.cell.leftMid', 'dashboard.cell.midMid', 'dashboard.cell.rightMid',
    'dashboard.cell.leftLong', 'dashboard.cell.midLong', 'dashboard.cell.rightLong',
  ]

  return (
    <View className="landing-heatmap">
      <Text className="section-title">🎯 {t('dashboard.landingHeatmap')}</Text>
      <View className="heatmap-content">
        {/* 九宫格热图 */}
        <View className="nine-grid">
          {grid.map((row, i) =>
            row.map((val, j) => {
              const idx = i * 3 + j
              return (
                <View
                  className="grid-cell"
                  key={idx}
                  style={{ background: getCellColor(val) }}
                >
                  <Text className="cell-value">{val}</Text>
                  <Text className="cell-label">{t(cellLabels[idx])}</Text>
                </View>
              )
            })
          )}
        </View>

        {/* 统计信息 */}
        <View className="heatmap-stats">
          <View className="stat-row">
            <Text className="stat-label">{t('dashboard.totalRallies')}</Text>
            <Text className="stat-value">{data.total_rallies}</Text>
          </View>
          <View className="stat-row">
            <Text className="stat-label">{t('dashboard.sourceReports')}</Text>
            <Text className="stat-value">{data.source_reports_count}</Text>
          </View>
          <View className="distribution-row">
            <View className="dist-item">
              <View className="dist-dot" style={{ background: 'var(--color-primary)' }} />
              <Text>{t('dashboard.forehand')} {(data.distribution.forehand * 100).toFixed(0)}%</Text>
            </View>
            <View className="dist-item">
              <View className="dist-dot" style={{ background: 'var(--color-secondary)' }} />
              <Text>{t('dashboard.backhand')} {(data.distribution.backhand * 100).toFixed(0)}%</Text>
            </View>
            <View className="dist-item">
              <View className="dist-dot" style={{ background: 'var(--color-success)' }} />
              <Text>{t('dashboard.middle')} {(data.distribution.middle * 100).toFixed(0)}%</Text>
            </View>
        </View>
      </View>
    </View>
  )
}
```

### 4.6 比赛记录列表

```tsx
// frontend/src/pages/dashboard/components/MatchRecordList.tsx
import { View, Text } from '@tarojs/components'
import { Tabs, Empty } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import Taro from '@tarojs/taro'
import type { MatchRecordItem } from '@/services/dashboard'
import './MatchRecordList.scss'

interface Props {
  items: MatchRecordItem[]
  total: number
  filter: 'win' | 'lose' | 'all'
  loading: boolean
  hasMore: boolean
  onFilterChange: (filter: 'win' | 'lose' | 'all') => void
  onLoadMore: () => void
}

export default function MatchRecordList({
  items, total, filter, loading, hasMore, onFilterChange, onLoadMore,
}: Props) {
  const { t } = useTranslation()

  const filterOptions: Array<{ key: 'win' | 'lose' | 'all'; label: string }> = [
    { key: 'all', label: t('dashboard.allMatches') },
    { key: 'win', label: t('dashboard.winsOnly') },
    { key: 'lose', label: t('dashboard.lossesOnly') },
  ]

  const handleItemClick = (item: MatchRecordItem) => {
    // 跳转到比赛详情页（如有关联分析报告）
    Taro.navigateTo({
      url: `/pages/match-data/record-detail/index?id=${item.id}`,
    })
  }

  return (
    <View className="match-record-list">
      <View className="section-header">
        <Text className="section-title">📋 {t('dashboard.matchRecords')}</Text>
        <Text className="section-count">{t('dashboard.totalMatches', { count: total })}</Text>
      </View>

      <Tabs
        value={filter}
        onChange={(val) => onFilterChange(val as 'win' | 'lose' | 'all')}
      >
        {filterOptions.map((opt) => (
          <Tabs.TabPane key={opt.key} title={opt.label} value={opt.key} />
        ))}
      </Tabs>

      {items.length === 0 && !loading ? (
        <Empty description={t('dashboard.noMatchRecords')} />
      ) : (
        <View className="record-list">
          {items.map((item) => (
            <View
              className={`record-card ${item.is_win ? 'card-win' : 'card-lose'}`}
              key={item.id}
              onClick={() => handleItemClick(item)}
            >
              <View className="record-left">
                <Text className="record-date">
                  {new Date(item.match_date).toLocaleDateString()}
                </Text>
                <Text className="record-opponent">
                  vs {item.opponent_name || t('dashboard.unknownOpponent')}
                </Text>
                {item.opponent_rating && (
                  <Text className="record-rating">
                    {t('dashboard.rating')}: {item.opponent_rating}
                  </Text>
                )}
              </View>
              <View className="record-right">
                <Text className="record-score">
                  {item.my_score} - {item.opponent_score}
                </Text>
                <Text className={`record-result ${item.is_win ? 'win' : 'lose'}`}>
                  {item.is_win ? t('dashboard.win') : t('dashboard.lose')}
                </Text>
              </View>
            </View>
          ))}

          {/* 上拉加载更多 */}
          {hasMore && (
            <View className="load-more" onClick={onLoadMore}>
              <Text>{loading ? t('common.loading') : t('common.loadMore')}</Text>
            </View>
          )}
        </View>
      )}
    </View>
  )
}
```

---

## 5. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/dashboard/index.scss

// CSS 变量已在全局 app.scss 中定义，模块级不重复定义。
// 全局 :root 变量清单见总览 §3.2「前端通用约定 — 全局 CSS 变量」。

.dashboard-page {
  min-height: 100vh;
  background: var(--color-background);
}

.dashboard-header {
  padding: var(--spacing-md) var(--spacing-md) var(--spacing-sm);

  .dashboard-title {
    font-size: 18px;
    font-weight: bold;
    color: var(--color-text-primary);
  }
}

.dashboard-scroll {
  height: calc(100vh - 56px);
}

.section-title {
  display: block;
  font-size: 15px;
  font-weight: bold;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-sm);
}

// 概览卡片
.overview-cards {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  padding: 0 var(--spacing-md) var(--spacing-md);

  .overview-card {
    flex: 1 1 calc(50% - 4px);
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    text-align: center;
    box-shadow: var(--shadow-card);

    .card-label {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
      margin-bottom: var(--spacing-xs);
    }

    .card-value {
      display: block;
      font-size: 24px;
      font-weight: bold;
      color: var(--color-primary);
    }

    .card-sub {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-xs);
    }
  }

  .card-winrate .card-value { color: var(--color-primary); }
  .card-analysis .card-value { color: var(--color-secondary); }
  .card-training .card-value { color: var(--color-accent); }
  .card-streak .card-value { color: var(--color-success); }

  .trend-up { color: var(--color-success); margin-left: 4px; }
  .trend-down { color: var(--color-primary); margin-left: 4px; }
  .trend-flat { color: var(--color-text-secondary); margin-left: 4px; }

  .advice-banner {
    flex: 1 1 100%;
    background: color-mix(in srgb, var(--color-accent) 10%, transparent);
    border-left: 3px solid var(--color-accent);
    border-radius: var(--radius-sm);
    padding: var(--spacing-sm) var(--spacing-md);
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);

    .advice-text {
      flex: 1;
      font-size: 13px;
      color: var(--color-text-primary);
    }

    .advice-tag {
      background: var(--color-primary);
      color: var(--color-text-inverse);
      font-size: 12px;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--radius-md);
    }
  }
}

// 战绩趋势
.win-rate-trend {
  padding: 0 var(--spacing-md) var(--spacing-md);

  .section-header {
    margin-bottom: var(--spacing-sm);
  }

  .chart-container {
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);
  }

  .chart-placeholder, .chart-empty {
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-2xl) 0;
    text-align: center;
    color: var(--color-text-secondary);
  }
}

// 技术统计
.technique-stats {
  padding: 0 var(--spacing-md) var(--spacing-md);

  .technique-content {
    display: flex;
    gap: var(--spacing-md);
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);
  }

  .donut-chart {
    flex-shrink: 0;
    width: 160px;
    height: 160px;

    .donut-svg {
      width: 100%;
      height: 100%;
    }
  }

  .legend-list {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-sm);
    justify-content: center;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);

    .legend-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .legend-name {
      font-size: 13px;
      color: var(--color-text-primary);
      flex: 1;
    }

    .legend-value {
      font-size: 13px;
      color: var(--color-text-secondary);
    }
  }
}

// 落点热图
.landing-heatmap {
  padding: 0 var(--spacing-md) var(--spacing-md);

  .heatmap-content {
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);
  }

  .nine-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--spacing-xs);
    margin-bottom: var(--spacing-md);

    .grid-cell {
      aspect-ratio: 1;
      border-radius: var(--radius-sm);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;

      .cell-value {
        font-size: 18px;
        font-weight: bold;
        color: var(--color-text-inverse);
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.06); /* P3-fix: text-shadow for legibility on colored bg, aligns with DS-017 shadow spec */
      }

      .cell-label {
        font-size: 12px;
        color: var(--color-text-inverse-secondary);
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.06); /* P3-fix: text-shadow for legibility on colored bg, aligns with DS-017 shadow spec */
      }
    }
  }

  .heatmap-stats {
    .stat-row {
      display: flex;
      justify-content: space-between;
      padding: var(--spacing-xs) 0;

      .stat-label {
        font-size: 13px;
        color: var(--color-text-secondary);
      }
      .stat-value {
        font-size: 13px;
        font-weight: bold;
        color: var(--color-text-primary);
      }
    }

    .distribution-row {
      display: flex;
      gap: var(--spacing-md);
      margin-top: var(--spacing-sm);
      padding-top: var(--spacing-sm);
      border-top: 1px solid var(--color-divider);

      .dist-item {
        display: flex;
        align-items: center;
        gap: var(--spacing-xs);
        font-size: 12px;
        color: var(--color-text-secondary);

        .dist-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
      }
    }
  }
}

// 比赛记录
.match-record-list {
  padding: 0 var(--spacing-md) var(--spacing-lg);

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--spacing-sm);

    .section-count {
      font-size: 12px;
      color: var(--color-text-secondary);
    }
  }

  .record-list {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-sm);
  }

  .record-card {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);
    border-left: 4px solid transparent;

    &.card-win { border-left-color: var(--color-success); }
    &.card-lose { border-left-color: var(--color-primary); }

    .record-left {
      .record-date {
        display: block;
        font-size: 13px;
        font-weight: 500;
        color: var(--color-text-primary);
      }
      .record-opponent {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
        margin-top: var(--spacing-xs);
      }
      .record-rating {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
      }
    }

    .record-right {
      text-align: right;

      .record-score {
        display: block;
        font-size: 18px;
        font-weight: bold;
        color: var(--color-text-primary);
      }
      .record-result {
        font-size: 12px;
        &.win { color: var(--color-success); }
        &.lose { color: var(--color-primary); }
      }
    }
  }

  .load-more {
    text-align: center;
    padding: var(--spacing-md);
    color: var(--color-text-secondary);
    font-size: 13px;
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 dashboard 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    // ... 其他已有页面
    'pages/dashboard/index',    // 新增：数据看板
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

> 数据看板不是独立 Tab 页，从首页快捷入口或训练 Tab "我的数据"入口进入。

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "dashboard": {
    "title": "数据看板",
    "winRate": "胜率",
    "wins": "胜",
    "losses": "负",
    "analysisCount": "分析次数",
    "trainingFreq": "训练频次",
    "timesPerWeek": "次/周",
    "streakDays": "连续天数",
    "days": "天",
    "times": "次",
    "winRateTrend": "战绩趋势",
    "month": "本月",
    "quarter": "本季",
    "year": "全年",
    "techniqueStats": "技术统计",
    "landingHeatmap": "落点热图",
    "matchRecords": "比赛记录",
    "totalMatches": "共 {{count}} 场",
    "allMatches": "全部",
    "winsOnly": "仅胜场",
    "lossesOnly": "仅负场",
    "win": "胜",
    "lose": "负",
    "total": "总计",
    "totalRallies": "总回合数",
    "sourceReports": "来源报告数",
    "forehand": "正手",
    "backhand": "反手",
    "middle": "中路",
    "hasIssues": "有未解决问题",
    "noMatchData": "暂无比赛数据",
    "noTechniqueData": "暂无技术统计数据",
    "noHeatmapData": "暂无落点数据",
    "noMatchRecords": "暂无比赛记录",
    "unknownOpponent": "未知对手",
    "rating": "积分",
    "cell": {
      "leftShort": "左短",
      "midShort": "中短",
      "rightShort": "右短",
      "leftMid": "左中",
      "midMid": "中中",
      "rightMid": "右中",
      "leftLong": "左长",
      "midLong": "中长",
      "rightLong": "右长"
    }
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "dashboard": {
    "title": "Dashboard",
    "winRate": "Win Rate",
    "wins": "W",
    "losses": "L",
    "analysisCount": "Analyses",
    "trainingFreq": "Training",
    "timesPerWeek": "/week",
    "streakDays": "Streak",
    "days": "days",
    "times": "times",
    "winRateTrend": "Win Rate Trend",
    "month": "Month",
    "quarter": "Quarter",
    "year": "Year",
    "techniqueStats": "Technique Stats",
    "landingHeatmap": "Landing Heatmap",
    "matchRecords": "Match Records",
    "totalMatches": "{{count}} matches",
    "allMatches": "All",
    "winsOnly": "Wins",
    "lossesOnly": "Losses",
    "win": "Win",
    "lose": "Loss",
    "total": "Total",
    "totalRallies": "Total Rallies",
    "sourceReports": "Source Reports",
    "forehand": "Forehand",
    "backhand": "Backhand",
    "middle": "Middle",
    "hasIssues": "Unresolved Issues",
    "noMatchData": "No match data yet",
    "noTechniqueData": "No technique data yet",
    "noHeatmapData": "No landing data yet",
    "noMatchRecords": "No match records yet",
    "unknownOpponent": "Unknown",
    "rating": "Rating",
    "cell": {
      "leftShort": "Left Short",
      "midShort": "Mid Short",
      "rightShort": "Right Short",
      "leftMid": "Left Mid",
      "midMid": "Mid Mid",
      "rightMid": "Right Mid",
      "leftLong": "Left Long",
      "midLong": "Mid Long",
      "rightLong": "Right Long"
    }
  }
}
```

### 常量定义

```typescript
// frontend/src/constants/dashboard.ts

/** 时间范围选项 */
export const PERIOD_OPTIONS = [
  { key: 'month' as const, labelKey: 'dashboard.month' },
  { key: 'quarter' as const, labelKey: 'dashboard.quarter' },
  { key: 'year' as const, labelKey: 'dashboard.year' },
]

/** 比赛结果筛选选项 */
export const RESULT_FILTER_OPTIONS = [
  { key: 'all' as const, labelKey: 'dashboard.allMatches' },
  { key: 'win' as const, labelKey: 'dashboard.winsOnly' },
  { key: 'lose' as const, labelKey: 'dashboard.lossesOnly' },
]

/** 九宫格标签 */
export const GRID_CELL_LABELS = [
  'dashboard.cell.leftShort', 'dashboard.cell.midShort', 'dashboard.cell.rightShort',
  'dashboard.cell.leftMid', 'dashboard.cell.midMid', 'dashboard.cell.rightMid',
  'dashboard.cell.leftLong', 'dashboard.cell.midLong', 'dashboard.cell.rightLong',
]
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 概览卡片布局为 2×2 网格，每个卡片有独立主色
- [ ] 胜率卡片显示趋势箭头（↑ 绿色 / ↓ 红色 / → 灰色）
- [ ] 训练提醒横幅显示在卡片区域底部，橙色左边框
- [ ] 战绩趋势折线图使用主色 `#E63946`，支持时间范围切换
- [ ] 技术统计环形图色彩与 API 返回的 color 字段一致
- [ ] 落点热图九宫格颜色深浅正确反映数值大小
- [ ] 比赛记录列表胜场左边框绿色、负场红色
- [ ] 空状态正确显示引导文字
- [ ] 下拉刷新功能正常

### 功能验证
- [ ] 页面加载时并发请求 5 个 API
- [ ] 时间范围切换后重新加载战绩趋势
- [ ] 比赛记录筛选切换后重新加载列表
- [ ] 比赛记录上拉加载更多正常
- [ ] 下拉刷新重新加载所有数据
- [ ] 数据加载中显示 Skeleton/Loading 状态
- [ ] 网络错误显示错误提示

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 颜色使用 CSS 变量或 API 返回的 color 字段，**禁止** 硬编码颜色值
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **必须** 支持下拉刷新
- **必须** 在比赛记录列表支持下拉刷新 + 上拉加载
