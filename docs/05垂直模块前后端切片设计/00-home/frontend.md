# home 模块 — 前端垂直切片设计

> **模块名称**：`home`
> **前端目录**：`frontend/src/pages/home/` + `frontend/src/services/home.ts` + `frontend/src/stores/homeStore.ts`
> **定位**：首页 Dashboard 聚合页面，组合顶部用户栏、数据概览卡片、快捷操作宫格、训练打卡日历（周视图）、最近分析报告卡片、训练提醒
> **依据**：前端需求与界面设计 v2.0 §P1.1、API 详细设计 v1.3 §6.1 / §9.4 / §4.4 / §12.2

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §P1.1（首页聚合：顶部栏 + 概览 + 快捷入口 + 打卡 + 最近报告）
- [ ] 阅读本模块涉及的 API 契约：
  - §3.1 GET /users/profile（用户头像/昵称/积分）
  - §5.2 GET /scoring/matches（最近比赛记录）
  - §8.2 GET /training/advice/contextual（训练建议摘要）
  - §9.1 GET /gamification/points（积分信息）
  - §12.1 GET /notification/unread-count（通知未读数）
  - §6.1 GET /dashboard/overview（概览数据，含 latest_advice_summary 字段用于训练提醒卡片，5min 缓存）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：首页聚合页 + home Service（聚合调用） + homeStore
- [ ] 确认首页为 TabBar 首页，进入即加载

---

## 2. API Service 模块

首页聚合多个后端模块的 API，统一封装在 `services/home.ts` 中，内部调用各模块的 service 函数。

```typescript
// frontend/src/services/home.ts
import request from './request'
import * as dashboardApi from './dashboard'
import * as gamificationApi from './gamification'
import * as videoAnalysisApi from './video_analysis'

/** 概览数据（复用 dashboard 模块类型） */
export type { OverviewData } from './dashboard'

/** 训练提醒摘要 */
export interface AdviceSummary {
  report_id: number
  summary: string
  has_unresolved_issues: boolean
  latest_report_at: string
}

/** 打卡日历项 */
export interface CheckinDay {
  date: string           // YYYY-MM-DD
  checked_in: boolean
  exp_earned: number
}

export interface CheckinCalendar {
  week_start: string     // 周一日期
  week_end: string       // 周日日期
  current_streak: number
  days: CheckinDay[]     // 7 天
  today_checked_in: boolean
}

/** 分析报告项（简化，取最近 1 条） */
export interface ReportSummary {
  id: number
  title: string
  status: string
  created_at: string
  thumbnail_url: string | null
  overall_score: number | null
}

/** 未读通知数 */
export interface UnreadCount {
  unread_count: number
}

/**
 * 获取首页数据概览（复用 dashboard service）。
 * 后端 Redis 缓存 5min。
 */
export function getOverview() {
  return dashboardApi.getOverview()
}

/**
 * 获取训练打卡日历（周视图）。
 */
export function getCheckinCalendar() {
  return request.get('/gamification/checkin-calendar')  // R17-P1: 从 /gamification/points 改为正确的打卡日历端点
}

/**
 * 获取最近比赛记录（取 3 条）。
 */
export function getLatestReport() {
  return request.get('/scoring/matches', { params: { page: 1, page_size: 3 } })
}

/**
 * 获取未读通知数。
 */
export function getUnreadCount() {
  return request.get('/notification/unread-count')
}
```

---

## 3. 状态管理（Zustand Store — homeStore）

`homeStore` 聚合首页所有数据，提供 `refreshAll` 并发加载。

```typescript
// frontend/src/stores/homeStore.ts
import { create } from 'zustand'
import * as homeApi from '@/services/home'
import type {
  OverviewData,
  CheckinCalendar,
  ReportSummary,
  AdviceSummary,
} from '@/services/home'

interface HomeState {
  // 顶部栏（用户信息从 authStore 获取，此处仅存通知数）
  unreadCount: number

  // 数据概览
  overview: OverviewData | null
  overviewLoading: boolean

  // 打卡日历
  checkinCalendar: CheckinCalendar | null
  checkinLoading: boolean

  // 最近分析报告
  latestReport: ReportSummary | null
  reportLoading: boolean

  // 训练提醒
  adviceSummary: AdviceSummary | null
  adviceLoading: boolean

  // 全局加载
  refreshing: boolean

  // Actions
  fetchUnreadCount: () => Promise<void>
  fetchOverview: () => Promise<void>
  fetchCheckinCalendar: () => Promise<void>
  fetchLatestReport: () => Promise<void>
  refreshAll: () => Promise<void>
}

export const useHomeStore = create<HomeState>((set, get) => ({
  unreadCount: 0,
  overview: null,
  overviewLoading: false,
  checkinCalendar: null,
  checkinLoading: false,
  latestReport: null,
  reportLoading: false,
  adviceSummary: null,
  adviceLoading: false,
  refreshing: false,

  fetchUnreadCount: async () => {
    try {
      const res = await homeApi.getUnreadCount()
      set({ unreadCount: res.data.data.unread_count })
    } catch {
      // 通知数失败不阻塞首页
    }
  },

  fetchOverview: async () => {
    set({ overviewLoading: true, adviceLoading: true })
    try {
      const res = await homeApi.getOverview()
      const data = res.data.data
      set({
        overview: data,
        adviceSummary: data.latest_advice_summary ?? null,
      })
    } catch (error) {
      console.error('fetchOverview failed', error)
      throw error
    } finally {
      set({ overviewLoading: false, adviceLoading: false })
    }
  },

  fetchCheckinCalendar: async () => {
    set({ checkinLoading: true })
    try {
      const res = await homeApi.getCheckinCalendar()
      set({ checkinCalendar: res.data.data })
    } catch (error) {
      console.error('fetchCheckinCalendar failed', error)
      throw error
    } finally {
      set({ checkinLoading: false })
    }
  },

  fetchLatestReport: async () => {
    set({ reportLoading: true })
    try {
      const res = await homeApi.getLatestReport()
      const items: ReportSummary[] = res.data.data.items || []
      set({ latestReport: items.length > 0 ? items[0] : null })
    } catch {
      set({ latestReport: null })
    } finally {
      set({ reportLoading: false })
    }
  },

  refreshAll: async () => {
    set({ refreshing: true })
    try {
      await Promise.all([
        get().fetchUnreadCount(),
        get().fetchOverview(),
        get().fetchCheckinCalendar(),
        get().fetchLatestReport(),
      ])
    } catch (error) {
      console.error('refreshAll failed', error)
      throw error
    } finally {
      set({ refreshing: false })
    }
  },
}))
```

---

## 4. 页面组件

### 4.1 首页主页面

```tsx
// frontend/src/pages/home/index.tsx
import { useEffect, useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, ScrollView } from '@tarojs/components'
import { PullRefresh } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useHomeStore } from '@/stores/homeStore'
import { useAuthStore } from '@/stores/authStore'
import TopBar from './components/TopBar'
import OverviewCards from './components/OverviewCards'
import QuickGrid from './components/QuickGrid'
import CheckinCalendar from './components/CheckinCalendar'
import LatestReportCard from './components/LatestReportCard'
import AdviceBanner from './components/AdviceBanner'
import './index.scss'

export default function HomePage() {
  const { t } = useTranslation()
  const homeStore = useHomeStore()
  const { user } = useAuthStore()
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    homeStore.refreshAll()
  }, [])

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await homeStore.refreshAll()
    } finally {
      setRefreshing(false)
    }
  }, [homeStore])

  return (
    <View className="home-page">
      {/* 顶部栏：头像 + 昵称 + 积分 + 通知 */}
      <TopBar
        nickname={user?.nickname || ''}
        avatarUrl={user?.avatar_url || null}
        rating={user?.profile?.kqs_rating ?? null}
        unreadCount={homeStore.unreadCount}
      />

      <PullRefresh onRefresh={handleRefresh} refreshing={refreshing}>
        <ScrollView scrollY className="home-scroll">
          {/* 数据概览卡片 */}
          <OverviewCards
            data={homeStore.overview}
            loading={homeStore.overviewLoading}
          />

          {/* 快捷操作宫格 */}
          <QuickGrid />

          {/* 训练打卡日历（周视图） */}
          <CheckinCalendar
            data={homeStore.checkinCalendar}
            loading={homeStore.checkinLoading}
          />

          {/* 最近分析报告 */}
          <LatestReportCard
            report={homeStore.latestReport}
            loading={homeStore.reportLoading}
          />

          {/* 训练提醒 */}
          <AdviceBanner
            advice={homeStore.adviceSummary}
            loading={homeStore.adviceLoading}
          />
        </ScrollView>
      </PullRefresh>
    </View>
  )
}
```

### 4.2 顶部栏组件

```tsx
// frontend/src/pages/home/components/TopBar.tsx
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Badge } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import './TopBar.scss'

interface Props {
  nickname: string
  avatarUrl: string | null
  rating: number | null
  unreadCount: number
}

export default function TopBar({ nickname, avatarUrl, rating, unreadCount }: Props) {
  const { t } = useTranslation()

  const handleNotification = () => {
    Taro.navigateTo({ url: '/pages/notification/list/index' })
  }

  const handleAvatar = () => {
    Taro.switchTab({ url: '/pages/user/profile/index' })
  }

  return (
    <View className="home-topbar">
      <View className="topbar-user" onClick={handleAvatar}>
        <Image
          className="user-avatar"
          src={avatarUrl || 'https://cdn.pingpongai.com/images/default-avatar.png'}
          mode="aspectFill"
        />
        <View className="user-info">
          <Text className="user-nickname">{nickname || t('home.guest')}</Text>
          <View className="user-rating-row">
            <Text className="rating-label">{t('home.rating')}</Text>
            <Text className="rating-value">{rating ?? '--'}</Text>
          </View>
        </View>
      </View>

      <View className="topbar-bell" onClick={handleNotification}>
        <Badge value={unreadCount > 99 ? '99+' : unreadCount} showZero={false}>
          <Text className="bell-icon">🔔</Text>
        </Badge>
      </View>
    </View>
  )
}
```

### 4.3 数据概览卡片组件

```tsx
// frontend/src/pages/home/components/OverviewCards.tsx
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { OverviewData } from '@/services/home'
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
  const trendCls = data.trend === 'up' ? 'trend-up' : data.trend === 'down' ? 'trend-down' : 'trend-flat'

  return (
    <View className="overview-cards">
      {/* 胜率 */}
      <View className="overview-card card-winrate">
        <Text className="card-label">{t('home.winRate')}</Text>
        <Text className="card-value">{(data.win_rate * 100).toFixed(0)}%</Text>
        <Text className={`card-sub ${trendCls}`}>
          {data.wins}{t('home.wins')} / {data.losses}{t('home.losses')} {trendIcon}
        </Text>
      </View>

      {/* 分析次数 */}
      <View className="overview-card card-analysis">
        <Text className="card-label">{t('home.analysisCount')}</Text>
        <Text className="card-value">{data.analysis_count}</Text>
        <Text className="card-sub">{t('home.times')}</Text>
      </View>

      {/* 连续打卡天数 */}
      <View className="overview-card card-streak">
        <Text className="card-label">{t('home.streakDays')}</Text>
        <Text className="card-value">{data.streak_days}</Text>
        <Text className="card-sub">{t('home.days')}</Text>
      </View>
    </View>
  )
}
```

### 4.4 快捷操作宫格组件

```tsx
// frontend/src/pages/home/components/QuickGrid.tsx
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import './QuickGrid.scss'

interface QuickItem {
  icon: string
  titleKey: string
  descKey: string
  route: string
  isTab?: boolean
}

export default function QuickGrid() {
  const { t } = useTranslation()

  const items: QuickItem[] = [
    {
      icon: '🤖',
      titleKey: 'home.aiAnalysis',
      descKey: 'home.aiAnalysisDesc',
      route: '/pages/video-analysis/upload/index',
    },
    {
      icon: '📝',
      titleKey: 'home.manualEntry',
      descKey: 'home.manualEntryDesc',
      route: '/pages/match-data/quick-entry/index',
    },
    {
      icon: '🏓',
      titleKey: 'home.scoreboard',
      descKey: 'home.scoreboardDesc',
      route: '/pages/scoring/setup/index',
    },
    {
      icon: '📊',
      titleKey: 'home.dataBoard',
      descKey: 'home.dataBoardDesc',
      route: '/pages/dashboard/index',
    },
  ]

  const handleNavigate = (item: QuickItem) => {
    if (item.isTab) {
      Taro.switchTab({ url: item.route })
    } else {
      Taro.navigateTo({ url: item.route })
    }
  }

  return (
    <View className="quick-grid">
      <Text className="section-title">{t('home.quickActions')}</Text>
      <View className="grid-container">
        {items.map((item, i) => (
          <View
            className="grid-item"
            key={i}
            onClick={() => handleNavigate(item)}
          >
            <Text className="item-icon">{item.icon}</Text>
            <Text className="item-title">{t(item.titleKey)}</Text>
            <Text className="item-desc">{t(item.descKey)}</Text>
          </View>
        ))}
      </View>
    </View>
  )
}
```

### 4.5 训练打卡日历（周视图）

```tsx
// frontend/src/pages/home/components/CheckinCalendar.tsx
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { CheckinCalendar as CheckinCalendarData } from '@/services/home'
import './CheckinCalendar.scss'

interface Props {
  data: CheckinCalendarData | null
  loading: boolean
}

const WEEKDAY_KEYS = [
  'home.weekMon',
  'home.weekTue',
  'home.weekWed',
  'home.weekThu',
  'home.weekFri',
  'home.weekSat',
  'home.weekSun',
]

export default function CheckinCalendar({ data, loading }: Props) {
  const { t } = useTranslation()

  const handleCheckin = () => {
    if (data?.today_checked_in) return
    Taro.navigateTo({ url: '/pages/gamification/checkin-calendar/index' })
  }

  if (loading || !data) {
    return (
      <View className="checkin-calendar">
        <Text className="section-title">📅 {t('home.checkinCalendar')}</Text>
        <View className="loading-placeholder">
          <Skeleton animated />
        </View>
      </View>
    )
  }

  return (
    <View className="checkin-calendar">
      <View className="section-header">
        <Text className="section-title">📅 {t('home.checkinCalendar')}</Text>
        <Text className="streak-badge">
          🔥 {data.current_streak} {t('home.days')}
        </Text>
      </View>

      <View className="week-row">
        {data.days.map((day, i) => {
          const dayDate = new Date(day.date)
          const isToday = day.date === new Date().toISOString().slice(0, 10)
          return (
            <View
              className={`day-cell ${day.checked_in ? 'checked' : ''} ${isToday ? 'today' : ''}`}
              key={i}
            >
              <Text className="day-weekday">{t(WEEKDAY_KEYS[i])}</Text>
              <Text className="day-date">{dayDate.getDate()}</Text>
              <View className="day-status">
                {day.checked_in ? (
                  <Text className="check-icon">✓</Text>
                ) : (
                  <Text className="check-placeholder">·</Text>
                )}
              </View>
            </View>
          )
        })}
      </View>

      <View
        className={`checkin-btn ${data.today_checked_in ? 'done' : ''}`}
        onClick={handleCheckin}
      >
        <Text>
          {data.today_checked_in ? t('home.todayCheckedIn') : t('home.checkinNow')}
        </Text>
      </View>
    </View>
  )
}
```

### 4.6 最近分析报告卡片

```tsx
// frontend/src/pages/home/components/LatestReportCard.tsx
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Empty, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { ReportSummary } from '@/services/home'
import './LatestReportCard.scss'

interface Props {
  report: ReportSummary | null
  loading: boolean
}

export default function LatestReportCard({ report, loading }: Props) {
  const { t } = useTranslation()

  const handleClick = () => {
    if (report) {
      Taro.navigateTo({ url: `/pages/video-analysis/report/index?report_id=${report.id}` })
    }
  }

  const handleUpload = () => {
    Taro.navigateTo({ url: '/pages/video-analysis/upload/index' })
  }

  return (
    <View className="latest-report">
      <Text className="section-title">🎬 {t('home.latestReport')}</Text>

      {loading ? (
        <View className="card-placeholder">
          <Skeleton animated />
        </View>
      ) : report ? (
        <View className="report-card" onClick={handleClick}>
          <Image
            className="report-thumbnail"
            src={report.thumbnail_url || 'https://cdn.pingpongai.com/images/report-default.png'}
            mode="aspectFill"
          />
          <View className="report-info">
            <Text className="report-title">{report.title}</Text>
            <Text className="report-date">
              {new Date(report.created_at).toLocaleDateString()}
            </Text>
            {report.overall_score !== null && (
              <View className="report-score-row">
                <Text className="score-label">{t('home.overallScore')}</Text>
                <Text className="score-value">{report.overall_score}</Text>
              </View>
            )}
          </View>
          <Text className="report-arrow">›</Text>
        </View>
      ) : (
        <View className="empty-report" onClick={handleUpload}>
          <Empty description={t('home.noReportYet')} />
          <Text className="upload-hint">{t('home.uploadFirst')}</Text>
        </View>
      )}
    </View>
  )
}
```

### 4.7 训练提醒组件

```tsx
// frontend/src/pages/home/components/AdviceBanner.tsx
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { AdviceSummary } from '@/services/home'
import './AdviceBanner.scss'

interface Props {
  advice: AdviceSummary | null
  loading: boolean
}

export default function AdviceBanner({ advice, loading }: Props) {
  const { t } = useTranslation()

  const handleClick = () => {
    if (advice) {
      Taro.navigateTo({ url: '/pages/training/advice/index' })
    }
  }

  if (loading) {
    return (
      <View className="advice-banner">
        <Text className="banner-title">💡 {t('home.trainingAdvice')}</Text>
        <View className="banner-placeholder">
          <Skeleton animated />
        </View>
      </View>
    )
  }

  if (!advice) {
    return (
      <View className="advice-banner" onClick={handleClick}>
        <Text className="banner-title">💡 {t('home.trainingAdvice')}</Text>
        <Text className="banner-empty">{t('home.noAdviceYet')}</Text>
      </View>
    )
  }

  return (
    <View className="advice-banner" onClick={handleClick}>
      <View className="banner-header">
        <Text className="banner-title">💡 {t('home.trainingAdvice')}</Text>
        {advice.has_unresolved_issues && (
          <Text className="issue-tag">{t('home.hasIssues')}</Text>
        )}
      </View>
      <Text className="banner-summary">{advice.summary}</Text>
      <Text className="banner-time">
        {new Date(advice.latest_report_at).toLocaleDateString()}
      </Text>
    </View>
  )
}
```

---

## 5. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/home/index.scss

.home-page {
  min-height: 100vh;
  background: var(--color-background);
}

.home-scroll {
  height: calc(100vh - 64px);
}

.section-title {
  display: block;
  font-size: 15px;
  font-weight: bold;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-sm);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-sm);
}
```

```scss
// frontend/src/pages/home/components/TopBar.scss

.home-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-md);
  background: var(--color-secondary);
  height: 64px;

  .topbar-user {
    display: flex;
    align-items: center;
    flex: 1;

    .user-avatar {
      width: 40px; /* P3-fix: avatar dimension, not 8px grid spacing */
      height: 40px; /* P3-fix: avatar dimension, not 8px grid spacing */
      border-radius: 50%;
      margin-right: var(--spacing-sm);
      border: 2px solid var(--color-text-inverse-tertiary);
    }

    .user-info {
      flex: 1;

      .user-nickname {
        display: block;
        font-size: 15px;
        font-weight: bold;
        color: var(--color-text-inverse);
      }

      .user-rating-row {
        display: flex;
        align-items: center;
        gap: var(--spacing-xs);
        margin-top: var(--spacing-xs);

        .rating-label {
          font-size: 12px;
          color: var(--color-text-inverse-secondary);
        }

        .rating-value {
          font-size: 13px;
          font-weight: bold;
          color: var(--color-accent);
        }
      }
    }
  }

  .topbar-bell {
    padding: var(--spacing-sm);

    .bell-icon {
      font-size: 24px;
      color: var(--color-text-inverse);
    }
  }
}
```

```scss
// frontend/src/pages/home/components/OverviewCards.scss

.overview-cards {
  display: flex;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);

  .overview-card {
    flex: 1;
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

    .trend-up { color: var(--color-success); }
    .trend-down { color: var(--color-primary); }
    .trend-flat { color: var(--color-text-secondary); }
  }

  .card-winrate .card-value { color: var(--color-primary); }
  .card-analysis .card-value { color: var(--color-secondary); }
  .card-streak .card-value { color: var(--color-accent); }
}
```

```scss
// frontend/src/pages/home/components/QuickGrid.scss

.quick-grid {
  padding: 0 var(--spacing-md) var(--spacing-md);

  .grid-container {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--spacing-sm);
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);
  }

  .grid-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: var(--spacing-md) var(--spacing-sm);
    border-radius: var(--radius-sm);
    transition: background 0.2s;

    &:active {
      background: color-mix(in srgb, var(--color-primary) 5%, transparent);
    }

    .item-icon {
      font-size: 32px;
      margin-bottom: var(--spacing-xs);
    }

    .item-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--color-text-primary);
      margin-bottom: var(--spacing-xs);
    }

    .item-desc {
      font-size: 12px;
      color: var(--color-text-secondary);
      text-align: center;
    }
  }
}
```

```scss
// frontend/src/pages/home/components/CheckinCalendar.scss

.checkin-calendar {
  padding: 0 var(--spacing-md) var(--spacing-md);

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--spacing-sm);

    .streak-badge {
      font-size: 12px;
      color: var(--color-accent);
      background: color-mix(in srgb, var(--color-accent) 10%, transparent);
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--radius-md);
    }
  }

  .week-row {
    display: flex;
    gap: var(--spacing-xs);
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);
  }

  .day-cell {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: var(--spacing-xs) 0;
    border-radius: var(--radius-sm);

    &.checked {
      background: color-mix(in srgb, var(--color-success) 10%, transparent);

      .check-icon {
        color: var(--color-success);
        font-size: 15px;
        font-weight: bold;
      }
    }

    &.today {
      border: 1px solid var(--color-primary);

      .day-date {
        color: var(--color-primary);
        font-weight: bold;
      }
    }

    .day-weekday {
      font-size: 12px;
      color: var(--color-text-secondary);
    }

    .day-date {
      font-size: 13px;
      font-weight: 500;
      color: var(--color-text-primary);
      margin: var(--spacing-xs) 0;
    }

    .day-status {
      height: 16px;
      display: flex;
      align-items: center;

      .check-placeholder {
        color: var(--color-divider);
        font-size: 15px;
      }
    }
  }

  .checkin-btn {
    margin-top: var(--spacing-sm);
    text-align: center;
    padding: var(--spacing-sm);
    background: var(--color-primary);
    color: var(--color-text-inverse);
    border-radius: var(--radius-md);
    font-size: 13px;
    font-weight: 600;

    &.done {
      background: var(--color-success);
      opacity: 0.7;
    }

    &:active {
      opacity: 0.85;
    }
  }

  .loading-placeholder {
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-2xl) 0;
    text-align: center;
    color: var(--color-text-secondary);
  }
}
```

```scss
// frontend/src/pages/home/components/LatestReportCard.scss

.latest-report {
  padding: 0 var(--spacing-md) var(--spacing-md);

  .card-placeholder,
  .empty-report {
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    text-align: center;
    box-shadow: var(--shadow-card);
  }

  .report-card {
    display: flex;
    align-items: center;
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);

    &:active {
      opacity: 0.9;
    }

    .report-thumbnail {
      width: 64px;
      height: 64px;
      border-radius: var(--radius-sm);
      margin-right: var(--spacing-md);
      flex-shrink: 0;
    }

    .report-info {
      flex: 1;

      .report-title {
        display: block;
        font-size: 15px;
        font-weight: 600;
        color: var(--color-text-primary);
        margin-bottom: var(--spacing-xs);
      }

      .report-date {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
      }

      .report-score-row {
        display: flex;
        align-items: center;
        gap: var(--spacing-xs);
        margin-top: var(--spacing-xs);

        .score-label {
          font-size: 12px;
          color: var(--color-text-secondary);
        }

        .score-value {
          font-size: 13px;
          font-weight: bold;
          color: var(--color-primary);
        }
      }
    }

    .report-arrow {
      font-size: 24px;
      color: var(--color-text-secondary);
      flex-shrink: 0;
    }
  }

  .upload-hint {
    display: block;
    margin-top: var(--spacing-sm);
    font-size: 13px;
    color: var(--color-primary);
  }
}
```

```scss
// frontend/src/pages/home/components/AdviceBanner.scss

.advice-banner {
  margin: 0 var(--spacing-md) var(--spacing-lg);
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  box-shadow: var(--shadow-card);
  border-left: 3px solid var(--color-accent);

  &:active {
    opacity: 0.9;
  }

  .banner-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--spacing-sm);

    .banner-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--color-text-primary);
    }

    .issue-tag {
      background: var(--color-primary);
      color: var(--color-text-inverse);
      font-size: 12px;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--radius-md);
    }
  }

  .banner-summary {
    display: block;
    font-size: 13px;
    color: var(--color-text-primary);
    line-height: 1.5;
  }

  .banner-time {
    display: block;
    margin-top: var(--spacing-xs);
    font-size: 12px;
    color: var(--color-text-secondary);
  }

  .banner-empty {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
    margin-top: var(--spacing-xs);
  }

  .banner-placeholder {
    padding: var(--spacing-sm) 0;
    text-align: center;
    color: var(--color-text-secondary);
    font-size: 13px;
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（首页已在路由中，确认配置）
export default {
  pages: [
    'pages/home/index',          // 首页 Dashboard 聚合
    'pages/auth/login/index',
    'pages/dashboard/index',
    'pages/video-analysis/upload/index',
    'pages/scoring/setup/index',
    'pages/match-data/quick-entry/index',
    'pages/training/advice/index',
    'pages/gamification/checkin-calendar/index',
    'pages/notification/list/index',
    'pages/user/profile/index',
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

> 首页是 TabBar 第一个 Tab，进入 App 默认加载。

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增 home 段）
{
  "home": {
    "guest": "游客",
    "rating": "积分",
    "winRate": "胜率",
    "wins": "胜",
    "losses": "负",
    "analysisCount": "分析次数",
    "streakDays": "连续打卡",
    "days": "天",
    "times": "次",
    "quickActions": "快捷操作",
    "aiAnalysis": "AI分析",
    "aiAnalysisDesc": "上传视频智能分析",
    "manualEntry": "手动录入",
    "manualEntryDesc": "录入比赛数据",
    "scoreboard": "记分牌",
    "scoreboardDesc": "实时比赛记分",
    "dataBoard": "数据看板",
    "dataBoardDesc": "查看训练数据",
    "checkinCalendar": "打卡日历",
    "checkinNow": "立即打卡",
    "todayCheckedIn": "今日已打卡",
    "weekMon": "一",
    "weekTue": "二",
    "weekWed": "三",
    "weekThu": "四",
    "weekFri": "五",
    "weekSat": "六",
    "weekSun": "日",
    "latestReport": "最近分析",
    "noReportYet": "还没有分析报告",
    "uploadFirst": "上传第一个视频开始分析 →",
    "overallScore": "综合评分",
    "trainingAdvice": "训练提醒",
    "hasIssues": "有待解决",
    "noAdviceYet": "暂无训练建议，完成分析后查看"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增 home 段）
{
  "home": {
    "guest": "Guest",
    "rating": "Rating",
    "winRate": "Win Rate",
    "wins": "W",
    "losses": "L",
    "analysisCount": "Analyses",
    "streakDays": "Streak",
    "days": "days",
    "times": "times",
    "quickActions": "Quick Actions",
    "aiAnalysis": "AI Analysis",
    "aiAnalysisDesc": "Upload video for analysis",
    "manualEntry": "Manual Entry",
    "manualEntryDesc": "Record match data",
    "scoreboard": "Scoreboard",
    "scoreboardDesc": "Live match scoring",
    "dataBoard": "Dashboard",
    "dataBoardDesc": "View training data",
    "checkinCalendar": "Check-in Calendar",
    "checkinNow": "Check in now",
    "todayCheckedIn": "Checked in today",
    "weekMon": "Mon",
    "weekTue": "Tue",
    "weekWed": "Wed",
    "weekThu": "Thu",
    "weekFri": "Fri",
    "weekSat": "Sat",
    "weekSun": "Sun",
    "latestReport": "Latest Report",
    "noReportYet": "No analysis report yet",
    "uploadFirst": "Upload your first video →",
    "overallScore": "Overall Score",
    "trainingAdvice": "Training Advice",
    "hasIssues": "Unresolved",
    "noAdviceYet": "No advice yet, complete an analysis first"
  }
}
```

### 常量定义

```typescript
// frontend/src/constants/home.ts

/** 快捷操作路由映射 */
export const QUICK_ROUTES = {
  aiAnalysis: '/pages/video-analysis/upload/index',
  manualEntry: '/pages/match-data/quick-entry/index',
  scoreboard: '/pages/scoring/setup/index',
  dataBoard: '/pages/dashboard/index',
} as const

/** 打卡日历周几 key */
export const WEEKDAY_KEYS = [
  'home.weekMon',
  'home.weekTue',
  'home.weekWed',
  'home.weekThu',
  'home.weekFri',
  'home.weekSat',
  'home.weekSun',
] as const

/** 默认头像 */
export const DEFAULT_AVATAR = 'https://cdn.pingpongai.com/images/default-avatar.png'

/** 默认报告缩略图 */
export const DEFAULT_REPORT_THUMBNAIL = 'https://cdn.pingpongai.com/images/report-default.png'
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 顶部栏深蓝背景（#1D3557），头像 + 昵称 + 积分 + 通知铃铛
- [ ] 通知数大于 0 时显示红色 Badge，超过 99 显示 "99+"
- [ ] 数据概览卡片横向排列 3 个，每个独立主色
- [ ] 胜率卡片显示趋势箭头（↑ 绿色 / ↓ 红色 / → 灰色）
- [ ] 快捷操作宫格 2×2 布局，点击有高亮反馈
- [ ] 打卡日历周视图 7 天横排，已打卡绿色 ✓，今日红色边框
- [ ] 打卡按钮未打卡红色，已打卡绿色
- [ ] 最近报告卡片显示缩略图 + 标题 + 日期 + 综合评分
- [ ] 无报告时显示空状态 + 上传引导
- [ ] 训练提醒横幅橙色左边框，有未解决问题显示红色标签
- [ ] 所有卡片圆角 12px，8px 网格间距

### 功能验证
- [ ] 页面加载时并发请求 4 个 API（overview / checkin / report / unread），训练提醒从 overview 响应中提取
- [ ] 单个 API 失败不阻塞其他区域渲染
- [ ] 下拉刷新重新加载所有数据
- [ ] 点击头像跳转到个人主页 Tab
- [ ] 点击通知铃铛跳转到通知页
- [ ] 点击快捷宫格跳转到对应页面
- [ ] 点击打卡按钮跳转到打卡页
- [ ] 点击最近报告卡片跳转到报告详情
- [ ] 点击训练提醒跳转到训练建议页

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串
- [ ] 周几缩写正确显示

---

## 9. 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/home.ts` 封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 颜色使用 CSS 变量，**禁止** 硬编码颜色值（emoji 除外）
- **ALL** 首页数据通过 `homeStore.refreshAll()` 并发加载，**禁止** 串行请求
- **ALL** 单个 API 失败**不得**阻塞其他模块渲染（catch 后静默处理）
- **ALL** 通知数失败时默认为 0，**不得** 显示错误状态
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **禁止** 在首页做数据处理逻辑（仅展示，处理在对应模块页面）
- **必须** 支持下拉刷新
- **必须** 快捷宫格每个入口有独立路由
