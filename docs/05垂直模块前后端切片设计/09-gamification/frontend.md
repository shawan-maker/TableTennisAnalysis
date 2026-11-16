# gamification 模块 — 前端垂直切片设计

> **模块名称**：`gamification`
> **前端目录**：`frontend/src/pages/gamification/` + `frontend/src/services/gamification.ts` + `frontend/src/stores/gamificationStore.ts`
> **定位**：训练积分卡片、打卡日历（月度可视化，连续打卡火焰🔥）、徽章列表（已获得/未获得+进度）
> **依据**：前端需求与界面设计 v2.0 §三/§P5.7、API 详细设计 v1.3 §10

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §三 Tab1 首页（训练打卡日历区域）
- [ ] 阅读前端设计 v2.0 §P5.7 徽章/成就页面
- [ ] 阅读本模块的 API 契约（§10.1-10.5，5 个端点——10.5 points-history 为 R2-P2-2 批次H 新增）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：积分卡片 + 打卡日历 + 徽章列表页

---

## 2. API Service 模块（TypeScript）

> **R-FS5-P3 实现注记（前端落地差异，以后端为准）**：
> ① §8 WS badge_unlocked 的 data 为徽章数组（后端 newly_unlocked），弹层逐枚展示，非样例单对象；useWebSocket 真实 API 为 options 传参（`useWebSocket(buildWsUrl(), { onMessage })`），样例 `const { onMessage } = useWebSocket()` 解构形态不存在；
> ② §4.2 打卡日历：todayStr 用本地 y/m/d 构造（toISOString 存在 UTC 跨日偏移，后端按 CST 计日）；409 分支按 request 封装走 err.message（无 err.response.status）；年月标题 i18n 改单 key `checkin.monthTitle`（'{{year}}年{{month}}月' / '{{year}}-{{month}}'，避免空串 key 触发 i18nKeys 守卫测试）；
> ③ §4.1 PointsCard 本 Sprint 嵌入打卡日历页顶部（streak 上下文关联）；「嵌入首页 Dashboard」归 FS7 首页升级消费；
> ④ badges 页省略 NavBar（weapp navigateTo 默认导航栏，config 已设标题）；Toast 样例改 Taro.showToast；
> ⑤ doCheckin 失败向调用方抛出（Error.message 含 40901「今日已打卡」后端文案），成功联动刷新积分与日历。
>
> **R2-P2-1/P2-2（批次H）注记——常量消费接线**：`BADGE_CATEGORY_MAP`（§7）由 badges 页分类 chip 消费（后端 BadgeEarned/BadgeLocked 已透出 `category`，未知分类回退 general 桶）；`POINTS_SOURCE_MAP`（§7）由 PointsCard「最近积分动态」区消费（数据源 `GET /gamification/points-history`，R2-P2-2 批次H 后端新增 PointTransaction 流水表 + 端点，API §10.5；映射外事件 training_session/share/feedback/badge 由 `gamification.sourceOther` 兜底）。两常量原「零消费孤儿」状态已闭合。

```typescript
// frontend/src/services/gamification.ts
import request from './request'

/** 训练积分 */
export interface PointsData {
  total_points: number
  monthly_points: number
  current_streak: number
  streak_icon: string
}

/** 单日打卡记录 */
export interface CheckInDay {
  date: string
  checked_in: boolean
  type: string | null
}

/** 打卡日历 */
export interface CheckInCalendarData {
  year: number
  month: number
  days: CheckInDay[]
  monthly_checkin_count: number
  streak_days: number
}

/** 打卡结果 */
export interface CheckInResult {
  points_earned: number
  current_streak: number
  bonus: number | null
}

/** 已获得徽章 */
export interface BadgeEarned {
  badge_id: string
  name: string
  icon: string
  earned_at: string
  /** R2-P2-1（批次H）：徽章分类（后端 badge_definition.category 透出） */
  category?: string | null
}

/** 未获得徽章 */
export interface BadgeLocked {
  badge_id: string
  name: string
  icon: string
  progress: number
  target: number
  /** R2-P2-1（批次H）：同 BadgeEarned */
  category?: string | null
}

/** 徽章列表 */
export interface BadgeListData {
  earned: BadgeEarned[]
  locked: BadgeLocked[]
}

/**
 * 积分流水条目（镜像后端 PointTransactionBrief，R2-P2-2 批次H）。
 * event_type 与 POINTS_SOURCE_MAP 六来源键一致，其余由 sourceOther 兜底。
 */
export interface PointTransactionItem {
  id: number
  event_type: string
  points: number
  ref_id?: number | null
  created_at?: string | null
}

/** 积分流水分页（GET /gamification/points-history，R2-P2-2 批次H） */
export interface PointsHistoryData {
  total: number
  page: number
  page_size: number
  items: PointTransactionItem[]
}

/**
 * 获取训练积分。
 */
export function getPoints() {
  return request.get('/gamification/points')
}

/**
 * 获取打卡日历（月度）。
 * @param year - 年
 * @param month - 月
 */
export function getCheckinCalendar(year?: number, month?: number) {
  const params: Record<string, number> = {}
  if (year) params.year = year
  if (month) params.month = month
  return request.get('/gamification/checkin-calendar', params)
}

/**
 * 手动打卡。
 */
export function checkin() {
  return request.post('/gamification/checkin')
}

/**
 * 获取徽章列表（已获得/未获得）。
 */
export function getBadges() {
  return request.get('/gamification/badges')
}

/**
 * 获取积分流水（分页，时间倒序；R2-P2-2 批次H，API §10.5）。
 * @param page - 页码
 * @param pageSize - 每页条数
 */
export function getPointsHistory(page = 1, pageSize = 20) {
  return request.get('/gamification/points-history', { page, page_size: pageSize })
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/gamificationStore.ts
import { create } from 'zustand'
import * as gamificationApi from '@/services/gamification'
import type {
  PointsData, CheckInCalendarData, CheckInResult, BadgeListData, PointsHistoryData,
} from '@/services/gamification'

interface GamificationState {
  // 训练积分
  points: PointsData | null
  // 打卡日历
  calendar: CheckInCalendarData | null
  // 徽章列表
  badges: BadgeListData | null
  // 积分流水（R2-P2-2 批次H：POINTS_SOURCE_MAP 消费数据源）
  pointsHistory: PointsHistoryData | null
  // 加载状态
  isLoadingPoints: boolean
  isLoadingCalendar: boolean
  isLoadingBadges: boolean
  isLoadingHistory: boolean
  // 打卡中
  isCheckingIn: boolean

  // Actions
  fetchPoints: () => Promise<void>
  fetchCalendar: (year?: number, month?: number) => Promise<void>
  doCheckin: () => Promise<CheckInResult | null>
  fetchBadges: () => Promise<void>
  /** R2-P2-2（批次H）：拉取积分流水（最近动态默认 5 条） */
  fetchPointsHistory: (page?: number, pageSize?: number) => Promise<void>
}

export const useGamificationStore = create<GamificationState>((set, get) => ({
  points: null,
  calendar: null,
  badges: null,
  pointsHistory: null,
  isLoadingPoints: false,
  isLoadingCalendar: false,
  isLoadingBadges: false,
  isLoadingHistory: false,
  isCheckingIn: false,

  fetchPoints: async () => {
    set({ isLoadingPoints: true })
    try {
      const res = await gamificationApi.getPoints()
      set({ points: res.data.data })
    } catch (error) {
      console.error('fetchPoints failed', error)
      throw error
    } finally {
      set({ isLoadingPoints: false })
    }
  },

  fetchCalendar: async (year, month) => {
    set({ isLoadingCalendar: true })
    try {
      const res = await gamificationApi.getCheckinCalendar(year, month)
      set({ calendar: res.data.data })
    } catch (error) {
      console.error('fetchCalendar failed', error)
      throw error
    } finally {
      set({ isLoadingCalendar: false })
    }
  },

  doCheckin: async () => {
    set({ isCheckingIn: true })
    try {
      const res = await gamificationApi.checkin()
      const result: CheckInResult = res.data.data
      // 打卡成功后刷新积分和日历
      await get().fetchPoints()
      await get().fetchCalendar()
      return result
    } catch (error) {
      console.error('doCheckin failed', error)
      throw error
    } finally {
      set({ isCheckingIn: false })
    }
  },

  fetchBadges: async () => {
    set({ isLoadingBadges: true })
    try {
      const res = await gamificationApi.getBadges()
      set({ badges: res.data.data })
    } catch (error) {
      console.error('fetchBadges failed', error)
      throw error
    } finally {
      set({ isLoadingBadges: false })
    }
  },

  /** R2-P2-2（批次H）：拉取积分流水——打卡/记分等动作后由调用方联动刷新 */
  fetchPointsHistory: async (page = 1, pageSize = 20) => {
    set({ isLoadingHistory: true })
    try {
      const res = await gamificationApi.getPointsHistory(page, pageSize)
      set({ pointsHistory: res.data.data })
    } finally {
      set({ isLoadingHistory: false })
    }
  },
}))
```

---

## 4. 页面组件（React + TSX + NutUI）

### 4.1 训练积分卡片（嵌入首页 Dashboard）

> **R2-P2-2（批次H）注记**：PointsCard 新增「最近积分动态」区——`POINTS_SOURCE_MAP`（§7）首次组件消费，数据源 `GET /gamification/points-history`（默认拉 5 条）。相对时间渲染：同日显示 `HH:mm`，非同日显示 `MM-DD`（本地日期构造，防 UTC 跨日）。下方样例已按实现回写（`components/PointsCard.tsx`）。

```tsx
// frontend/src/pages/gamification/components/PointsCard.tsx
import { useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useGamificationStore } from '@/stores/gamificationStore'
import { useTranslation } from 'react-i18next'
import { POINTS_SOURCE_MAP } from '@/constants/gamification'
import './PointsCard.scss'

/** 积分来源标签文案（六来源映射外的事件由 sourceOther 兜底） */
export function pointsSourceLabel(
  t: (k: string) => string,
  eventType: string
): string {
  return t(POINTS_SOURCE_MAP[eventType] ?? 'gamification.sourceOther')
}

/** 相对时间（今日 HH:mm / 非今日 MM-DD，后端 created_at 为 ISO 墙钟） */
function formatRelativeDate(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  if (sameDay(d, now)) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 最近动态展示条数 */
const RECENT_LIMIT = 5

export default function PointsCard() {
  const { t } = useTranslation()
  const points = useGamificationStore((s) => s.points)
  const isLoadingPoints = useGamificationStore((s) => s.isLoadingPoints)
  const fetchPoints = useGamificationStore((s) => s.fetchPoints)
  const pointsHistory = useGamificationStore((s) => s.pointsHistory)
  const fetchPointsHistory = useGamificationStore((s) => s.fetchPointsHistory)

  useEffect(() => {
    fetchPoints()
    fetchPointsHistory(1, RECENT_LIMIT)
  }, [fetchPoints, fetchPointsHistory])

  if (isLoadingPoints && !points) {
    return (
      <View className="points-card loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const streak = points?.current_streak ?? 0
  const showFlame = streak >= 3
  const recentItems = (pointsHistory?.items ?? []).slice(0, RECENT_LIMIT)

  return (
    <View className="points-card">
      <View className="points-header">
        <Text className="points-title">{t('gamification.trainingPoints')}</Text>
      </View>
      <View className="points-body">
        <View className="points-total">
          <Text className="points-number">{points?.total_points ?? 0}</Text>
          <Text className="points-label">{t('gamification.totalPoints')}</Text>
        </View>
        <View className="points-monthly">
          <Text className="points-monthly-number">{points?.monthly_points ?? 0}</Text>
          <Text className="points-monthly-label">{t('gamification.monthlyPoints')}</Text>
        </View>
        <View className="points-streak">
          {showFlame && <Text className="streak-flame">🔥</Text>}
          <Text className="streak-number">{streak}</Text>
          <Text className="streak-label">{t('gamification.dayStreak')}</Text>
        </View>
      </View>

      {/* R2-P2-2（批次H）：最近积分动态（POINTS_SOURCE_MAP 消费） */}
      {recentItems.length > 0 && (
        <View className="points-recent">
          <Text className="recent-title">{t('gamification.recentActivity')}</Text>
          {recentItems.map((item) => (
            <View key={item.id} className="recent-row">
              <Text className="recent-source">{pointsSourceLabel(t, item.event_type)}</Text>
              <Text className="recent-date">{formatRelativeDate(item.created_at)}</Text>
              <Text className="recent-points">+{item.points}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  )
}
```

**最近动态样式**（`PointsCard.scss` 节选——`--color-divider` 上边线 + success 色积分值）：

```scss
.points-card {
  .points-recent {
    margin-top: var(--spacing-md);
    padding-top: var(--spacing-sm-md);
    border-top: 1px solid var(--color-divider);

    .recent-title {
      display: block;
      font-size: var(--fs-small);
      font-weight: 600;
      color: var(--color-text-secondary);
      margin-bottom: var(--spacing-xs);
    }

    .recent-row {
      display: flex;
      align-items: center;
      padding: var(--spacing-xs) 0;

      .recent-source {
        flex: 1;
        font-size: var(--fs-caption);
        color: var(--color-text-primary);
      }

      .recent-date {
        margin-right: var(--spacing-sm);
        font-size: var(--fs-caption);
        color: var(--color-text-secondary);
      }

      .recent-points {
        font-size: var(--fs-caption);
        font-weight: 600;
        color: var(--color-success);
      }
    }
  }
}
```

### 4.2 打卡日历组件

```tsx
// frontend/src/pages/gamification/CheckinCalendar.tsx
import { useEffect, useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Toast, Skeleton } from '@nutui/nutui-react'
import { useGamificationStore } from '@/stores/gamificationStore'
import { useTranslation } from 'react-i18next'
import './gamification.scss'

export default function CheckinCalendar() {
  const { t } = useTranslation()
  const {
    calendar, isLoadingCalendar, isCheckingIn,
    fetchCalendar, doCheckin,
  } = useGamificationStore()

  const [currentYear, setCurrentYear] = useState(() => new Date().getFullYear())
  const [currentMonth, setCurrentMonth] = useState(() => new Date().getMonth() + 1)
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  useEffect(() => {
    fetchCalendar(currentYear, currentMonth)
  }, [fetchCalendar, currentYear, currentMonth])

  if (isLoadingCalendar && !calendar) {
    return (
      <View className="checkin-calendar loading">
        <Skeleton rows={4} loading={isLoadingCalendar} />
      </View>
    )
  }

  /** 上个月 */
  const handlePrevMonth = useCallback(() => {
    if (currentMonth === 1) {
      setCurrentMonth(12)
      setCurrentYear((y) => y - 1)
    } else {
      setCurrentMonth((m) => m - 1)
    }
  }, [currentMonth, currentYear])

  /** 下个月 */
  const handleNextMonth = useCallback(() => {
    if (currentMonth === 12) {
      setCurrentMonth(1)
      setCurrentYear((y) => y + 1)
    } else {
      setCurrentMonth((m) => m + 1)
    }
  }, [currentMonth, currentYear])

  /** 手动打卡 */
  const handleCheckin = useCallback(async () => {
    try {
      const result = await doCheckin()
      if (result) {
        let msg = t('gamification.checkinSuccess', { points: result.points_earned })
        if (result.bonus) {
          msg += t('gamification.streakBonus', { bonus: result.bonus })
        }
        showToast(msg)
      }
    } catch (err: any) {
      const code = err?.response?.status
      if (code === 409) {
        showToast(t('gamification.alreadyCheckedIn'))
      } else {
        showToast(err?.message || t('gamification.checkinFailed'))
      }
    }
  }, [doCheckin, t])

  // 计算日历网格
  const weekdays = [
    t('common.mon'), t('common.tue'), t('common.wed'),
    t('common.thu'), t('common.fri'), t('common.sat'), t('common.sun'),
  ]
  const today = new Date()
  const todayStr = today.toISOString().slice(0, 10)
  const days = calendar?.days ?? []
  const firstDay = days.length > 0 ? new Date(days[0].date).getDay() : 0
  // 周日=0，调整为周一开始
  const emptyCells = firstDay === 0 ? 6 : firstDay - 1

  return (
    <View className="checkin-calendar">
      {/* 月份导航 */}
      <View className="calendar-header">
        <View className="month-nav prev" onClick={handlePrevMonth}>
          <Text>‹</Text>
        </View>
        <Text className="month-title">{currentYear}{t('gamification.checkin.year')}{currentMonth}{t('gamification.checkin.month')}</Text>
        <View className="month-nav next" onClick={handleNextMonth}>
          <Text>›</Text>
        </View>
      </View>

      {/* 连续打卡提示 */}
      <View className="calendar-streak">
        <Text className="streak-text">
          {t('gamification.currentStreak', { days: calendar?.streak_days ?? 0 })}
        </Text>
        {(calendar?.streak_days ?? 0) >= 3 && <Text className="streak-flame">🔥</Text>}
      </View>

      {/* 星期表头 */}
      <View className="calendar-weekdays">
        {weekdays.map((day) => (
          <View key={day} className="weekday-cell">
            <Text className="weekday-text">{day}</Text>
          </View>
        ))}
      </View>

      {/* 日历网格 */}
      <View className="calendar-grid">
        {Array.from({ length: emptyCells }).map((_, i) => (
          <View key={`empty-${i}`} className="calendar-cell empty" />
        ))}
        {days.map((day) => (
          <View
            key={day.date}
            className={`calendar-cell ${day.checked_in ? 'checked' : ''} ${
              day.date === todayStr ? 'today' : ''
            }`}
          >
            <Text className="cell-date">{parseInt(day.date.slice(8))}</Text>
            {day.checked_in && <Text className="cell-dot">●</Text>}
          </View>
        ))}
      </View>

      {/* 月度统计 */}
      <View className="calendar-summary">
        <Text className="summary-text">
          {t('gamification.monthlyCheckins', {
            count: calendar?.monthly_checkin_count ?? 0,
          })}
        </Text>
      </View>

      {/* 打卡按钮 */}
      <Button
        type="primary"
        block
        loading={isCheckingIn}
        onClick={handleCheckin}
        className="checkin-btn"
      >
        {t('gamification.doCheckin')}
      </Button>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

### 4.3 徽章列表页

> **R2-P2-1（批次H）注记**：徽章条目新增分类标签 chip——`BADGE_CATEGORY_MAP`（§7）首次组件消费，后端 BadgeEarned/BadgeLocked 已透出 `category`（未知分类回退 general 桶）。`badgeCategoryLabel` 为实现导出函数（badges 页消费）。下方样例已按实现回写（`badges/index.tsx`，NavBar 省略见 §2 注记④）。

```tsx
// frontend/src/pages/gamification/badges/index.tsx
import { useEffect } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { Skeleton, Empty } from '@nutui/nutui-react'
import { useGamificationStore } from '@/stores/gamificationStore'
import { useTranslation } from 'react-i18next'
import { BADGE_CATEGORY_MAP } from '@/constants/gamification'
import './index.scss'

/** 徽章分类标签文案（未知分类回退 general 桶） */
export function badgeCategoryLabel(t: (k: string) => string, category?: string | null): string {
  const key = BADGE_CATEGORY_MAP[category ?? 'general'] ?? BADGE_CATEGORY_MAP.general
  return t(key)
}

export default function BadgesPage() {
  const { t } = useTranslation()
  const { badges, isLoadingBadges, fetchBadges } = useGamificationStore()

  useEffect(() => {
    fetchBadges()
  }, [fetchBadges])

  if (isLoadingBadges && !badges) {
    return (
      <View className="badges-page">
        <NavBar title={t('gamification.myBadges')} onBack={() => Taro.navigateBack()} />
        <View className="badges-loading">
          <Skeleton rows={4} animated />
        </View>
      </View>
    )
  }

  const earned = badges?.earned ?? []
  const locked = badges?.locked ?? []
  const total = earned.length + locked.length

  return (
    <View className="badges-page">
      <NavBar
        title={t('gamification.myBadges')}
        onBack={() => Taro.navigateBack()}
      />

      <ScrollView scrollY className="badges-scroll">
        {/* 已获得徽章 */}
        <View className="badges-section">
          <View className="section-header">
            <Text className="section-title">{t('gamification.earned')}</Text>
            <Text className="section-count">
              ({earned.length}/{total})
            </Text>
          </View>
          <View className="badges-grid">
            {earned.map((badge) => (
              <View key={badge.badge_id} className="badge-item earned">
                <Text className="badge-icon">{badge.icon}</Text>
                <Text className="badge-name">{badge.name}</Text>
                {/* R2-P2-1（批次H）：分类标签（BADGE_CATEGORY_MAP 消费） */}
                <Text className="badge-category">{badgeCategoryLabel(t, badge.category)}</Text>
                <Text className="badge-status">{t('gamification.earnedStatus')}</Text>
                <Text className="badge-date">{badge.earned_at}</Text>
              </View>
            ))}
            {earned.length === 0 && (
              <Empty description={t('gamification.noBadgesYet')} />
            )}
          </View>
            ))}
            {earned.length === 0 && (
              <Empty description={t('gamification.noBadgesYet')} />
            )}
          </View>
        </View>

        {/* 未获得徽章 */}
        <View className="badges-section">
          <View className="section-header">
            <Text className="section-title">{t('gamification.locked')}</Text>
            <Text className="section-count">
              ({locked.length}/{total})
            </Text>
          </View>
          <View className="badges-grid">
            {locked.map((badge) => (
              <View key={badge.badge_id} className="badge-item locked">
                <Text className="badge-icon locked-icon">{badge.icon}</Text>
                <Text className="badge-name">{badge.name}</Text>
                {/* R2-P2-1（批次H）：分类标签（BADGE_CATEGORY_MAP 消费） */}
                <Text className="badge-category">{badgeCategoryLabel(t, badge.category)}</Text>
                <View className="badge-progress">
                  <View
                    className="progress-bar"
                    style={{
                      width: `${Math.min(
                        (badge.progress / badge.target) * 100, 100
                      )}%`,
                    }}
                  />
                </View>
                <Text className="badge-progress-text">
                  {badge.progress}/{badge.target}
                </Text>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>
    </View>
  )
}
```

---

## 5. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/gamification/gamification.scss

// === 积分卡片 ===
.points-card {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  box-shadow: var(--shadow-card);

  &.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100px;
    color: var(--color-text-secondary);
  }

  .points-header {
    margin-bottom: var(--spacing-sm-md);

    .points-title {
      font-size: 18px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
  }

  .points-body {
    display: flex;
    justify-content: space-around;
    align-items: center;

    .points-total {
      text-align: center;

      .points-number {
        display: block;
        font-size: 32px;
        font-weight: bold;
        color: var(--color-primary); // #E63946
      }

      .points-label {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
        margin-top: var(--spacing-xs);
      }
    }

    .points-monthly {
      text-align: center;

      .points-monthly-number {
        display: block;
        font-size: 24px;
        font-weight: bold;
        color: var(--color-accent); // #F4A261
      }

      .points-monthly-label {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
        margin-top: var(--spacing-xs);
      }
    }

    .points-streak {
      text-align: center;

      .streak-flame {
        font-size: 18px;
      }

      .streak-number {
        display: block;
        font-size: 24px;
        font-weight: bold;
        color: var(--color-success); // #2A9D8F
      }

      .streak-label {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
        margin-top: var(--spacing-xs);
      }
    }
  }
}

// === 打卡日历 ===
.checkin-calendar {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  box-shadow: var(--shadow-card);

  .calendar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--spacing-sm-md);

    .month-nav {
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      color: var(--color-text-secondary);
      cursor: pointer;
    }

    .month-title {
      font-size: 18px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
  }

  .calendar-streak {
    text-align: center;
    margin-bottom: var(--spacing-md);

    .streak-text {
      font-size: 13px;
      color: var(--color-text-primary);
    }

    .streak-flame {
      margin-left: var(--spacing-sm);
      font-size: 18px;
    }
  }

  .calendar-weekdays {
    display: flex;
    margin-bottom: var(--spacing-sm);

    .weekday-cell {
      flex: 1;
      text-align: center;

      .weekday-text {
        font-size: 12px;
        color: var(--color-text-secondary);
      }
    }
  }

  .calendar-grid {
    display: flex;
    flex-wrap: wrap;

    .calendar-cell {
      flex: 0 0 calc(100% / 7);
      aspect-ratio: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      position: relative;

      &.empty {
        background: transparent;
      }

      &.checked {
        .cell-dot {
          color: var(--color-success); // #2A9D8F
          font-size: 12px;
          margin-top: var(--spacing-xs);
        }

        .cell-date {
          color: var(--color-text-primary);
          font-weight: 600;
        }
      }

      &.today {
        .cell-date {
          color: var(--color-primary); // #E63946
          font-weight: bold;
        }
      }

      .cell-date {
        font-size: 13px;
        color: var(--color-text-secondary);
      }
    }
  }

  .calendar-summary {
    text-align: center;
    margin: var(--spacing-sm-md) 0 var(--spacing-md);

    .summary-text {
      font-size: 13px;
      color: var(--color-text-secondary);
    }
  }

  .checkin-btn {
    background: var(--color-primary) !important; // #E63946
    border-radius: var(--radius-md);
    height: 44px;
    font-size: 15px;
  }
}

// === 徽章列表 ===
.badges-page {
  min-height: 100vh;
  background: var(--color-background); // #F8F9FA

  .badges-scroll {
    height: calc(100vh - 44px);
  }

  .badges-section {
    padding: var(--spacing-md);

    .section-header {
      display: flex;
      align-items: center;
      margin-bottom: var(--spacing-sm-md);

      .section-title {
        font-size: 18px;
        font-weight: 600;
        color: var(--color-text-primary);
      }

      .section-count {
        margin-left: var(--spacing-sm);
        font-size: 13px;
        color: var(--color-text-secondary);
      }
    }

    .badges-grid {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-sm-md);
    }

    .badge-item {
      flex: 0 0 calc(33.333% - 8px);
      background: var(--color-card);
      border-radius: var(--radius-md);
      padding: var(--spacing-md) var(--spacing-sm);
      text-align: center;
      box-shadow: var(--shadow-card);

      &.earned {
        .badge-icon {
          font-size: 32px;
        }

        .badge-status {
          display: block;
          font-size: 12px;
          color: var(--color-success);
          margin-top: var(--spacing-xs);
        }

        .badge-date {
          display: block;
          font-size: 12px;
          color: var(--color-text-secondary);
        }
      }

      &.locked {
        opacity: 0.7;

        .locked-icon {
          filter: grayscale(100%);
        }

        .badge-icon {
          font-size: 32px;
        }

        .badge-progress {
          width: 100%;
          height: 4px;
          background: var(--color-divider);
          border-radius: var(--radius-sm);
          margin: var(--spacing-sm) 0 var(--spacing-xs);
          overflow: hidden;

          .progress-bar {
            height: 100%;
            background: var(--color-accent); // #F4A261
            border-radius: var(--radius-sm);
            transition: width 0.3s;
          }
        }

        .badge-progress-text {
          font-size: 12px;
          color: var(--color-text-secondary);
        }
      }

      .badge-name {
        display: block;
        font-size: 12px;
        color: var(--color-text-primary);
        margin-top: var(--spacing-sm);
        font-weight: 500;
      }

      /* R2-P2-1（批次H）：分类标签 chip（BADGE_CATEGORY_MAP 消费） */
      .badge-category {
        display: inline-block;
        margin-top: var(--spacing-xs);
        padding: 2px var(--spacing-sm);
        font-size: var(--fs-caption);
        color: var(--color-primary);
        background: color-mix(in srgb, var(--color-primary) 10%, transparent);
        border-radius: var(--radius-sm);
        line-height: 1.6;
      }
    }

    .empty-state {
      width: 100%;
      text-align: center;
      padding: var(--spacing-2xl) 0; /* P3-fix: 40px→48px (--spacing-2xl) */

      .empty-text {
        font-size: 13px;
        color: var(--color-text-secondary);
      }
    }
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 gamification 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    // ... 其他页面
    'pages/gamification/badges/index',    // 新增：徽章列表页
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

**页面跳转**：
```typescript
// 首页积分卡片 → 打卡日历
Taro.navigateTo({ url: '/pages/gamification/checkin-calendar/index' })

// 首页 → 徽章列表
Taro.navigateTo({ url: '/pages/gamification/badges/index' })
```

---

## 7. 常量与 i18n

### 常量

```typescript
// frontend/src/constants/gamification.ts

/**
 * 积分来源标签映射。
 * R2-P2-2（批次H）消费接线：PointsCard「最近积分动态」区消费
 * （pointsSourceLabel，数据源 GET /gamification/points-history）；
 * 映射外事件（training_session/share/feedback/badge）由 sourceOther 兜底。
 */
export const POINTS_SOURCE_MAP: Record<string, string> = {
  analysis: 'gamification.sourceAnalysis',
  match: 'gamification.sourceMatch',
  record: 'gamification.sourceRecord',
  checkin: 'gamification.sourceCheckin',
  streak_7: 'gamification.sourceStreak7',
  streak_30: 'gamification.sourceStreak30',
}

/**
 * 徽章分类映射。
 * R2-P2-1（批次H）消费接线：badges 页分类 chip 消费（badgeCategoryLabel，
 * 后端 BadgeEarned/BadgeLocked.category 透出；未知分类回退 general 桶）。
 */
export const BADGE_CATEGORY_MAP: Record<string, string> = {
  analysis: 'gamification.categoryAnalysis',
  match: 'gamification.categoryMatch',
  streak: 'gamification.categoryStreak',
  general: 'gamification.categoryGeneral',
}
```

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "gamification": {
    "trainingPoints": "训练积分",
    "totalPoints": "总积分",
    "monthlyPoints": "本月积分",
    "dayStreak": "连续天数",
    "currentStreak": "连续打卡 {{days}} 天",
    "doCheckin": "立即打卡",
    "checkinSuccess": "打卡成功 +{{points}} 积分",
    "streakBonus": "连续打卡奖励 +{{bonus}} 积分",
    "alreadyCheckedIn": "今日已打卡",
    "checkinFailed": "打卡失败，请重试",
    "monthlyCheckins": "本月已打卡 {{count}} 次",
    "myBadges": "我的徽章",
    "earned": "已获得",
    "locked": "未获得",
    "earnedStatus": "已获得",
    "noBadgesYet": "暂无徽章，快去训练获取吧",
    "sourceAnalysis": "AI 分析",
    "sourceMatch": "记分牌比赛",
    "sourceRecord": "手动录入",
    "sourceCheckin": "每日打卡",
    "sourceStreak7": "连续7天奖励",
    "sourceStreak30": "连续30天奖励",
    "sourceOther": "其他",
    "recentActivity": "最近动态",
    "categoryAnalysis": "分析类",
    "categoryMatch": "比赛类",
    "categoryStreak": "坚持类",
    "categoryGeneral": "通用类",
    "checkin": {
      "year": "年",
      "month": "月"
    }
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "gamification": {
    "trainingPoints": "Training Points",
    "totalPoints": "Total",
    "monthlyPoints": "This Month",
    "dayStreak": "Day Streak",
    "currentStreak": "{{days}} day streak",
    "doCheckin": "Check In",
    "checkinSuccess": "Checked in +{{points}} points",
    "streakBonus": "Streak bonus +{{bonus}} points",
    "alreadyCheckedIn": "Already checked in today",
    "checkinFailed": "Check-in failed, please try again",
    "monthlyCheckins": "{{count}} check-ins this month",
    "myBadges": "My Badges",
    "earned": "Earned",
    "locked": "Locked",
    "earnedStatus": "Earned",
    "noBadgesYet": "No badges yet. Start training to earn some!",
    "sourceAnalysis": "AI Analysis",
    "sourceMatch": "Scoring Match",
    "sourceRecord": "Manual Record",
    "sourceCheckin": "Daily Check-in",
    "sourceStreak7": "7-Day Streak Bonus",
    "sourceStreak30": "30-Day Streak Bonus",
    "sourceOther": "Other",
    "recentActivity": "Recent Activity",
    "categoryAnalysis": "Analysis",
    "categoryMatch": "Match",
    "categoryStreak": "Streak",
    "categoryGeneral": "General",
    "checkin": {
      "year": "-",
      "month": ""
    }
  }
}
```

---

## 8. WebSocket 徽章解锁监听

```typescript
// frontend/src/hooks/useBadgeUnlock.ts
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { useGamificationStore } from '@/stores/gamificationStore'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useTranslation } from 'react-i18next'

/**
 * 监听 WebSocket badge_unlocked 事件。
 * 在首页或全局布局中调用。
 */
export function useBadgeUnlock() {
  const { t } = useTranslation()
  const { fetchBadges } = useGamificationStore()
  const { onMessage } = useWebSocket()
  const [badgePopupVisible, setBadgePopupVisible] = useState(false)
  const [unlockedBadge, setUnlockedBadge] = useState<{ icon: string; name: string } | null>(null)

  useEffect(() => {
    // 监听 WebSocket badge_unlocked 事件
    const handler = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data)
        // badge_unlocked 事件由 useBadgeUnlock Hook 处理（弹窗展示），
        // 同时 push_ws_message 会推送 notification 类型通知。
        // 两者独立处理，不冲突。
        if (data.event === 'badge_unlocked') {
          const badge = data.data
          // 弹出徽章解锁弹窗（使用 NutUI Popup position="bottom"）
          setUnlockedBadge(badge)
          setBadgePopupVisible(true)
          // 刷新徽章列表
          fetchBadges()
        }
      } catch {
        // 非 JSON 数据忽略
      }
    }

    // 通过 useWebSocket Hook 注册消息监听
    const removeListener = onMessage(handler)

    return () => {
      removeListener()
    }
  }, [fetchBadges, onMessage])

  /** 关闭徽章解锁弹窗 */
  const handleBadgePopupClose = () => {
    setBadgePopupVisible(false)
    setUnlockedBadge(null)
  }

  return { badgePopupVisible, unlockedBadge, handleBadgePopupClose }
}
```

---

## 9. 验证清单

### 构建验证
```bash
cd frontend && npm run build:weapp
```

### 视觉验证
- [ ] 积分卡片：总积分（红色 #E63946）+ 月度积分（橙色 #F4A261）+ 连续天数（绿色 #2A9D8F）
- [ ] 连续打卡 ≥3 天时显示火焰🔥图标
- [ ] 打卡日历：月度网格，已打卡日期标记绿色圆点，今日高亮红色
- [ ] 月份导航按钮可切换前后月
- [ ] 徽章列表：已获得徽章彩色显示 + 获得日期；未获得徽章灰度显示 + 进度条
- [ ] 进度条颜色为橙色（#F4A261）
- [ ] 空状态正确显示引导文字

### 功能验证
- [ ] 积分查询：进入首页自动加载积分数据
- [ ] 打卡日历：进入页面加载当月打卡记录
- [ ] 手动打卡：点击按钮 → 成功提示积分+连续天数 → 刷新积分和日历
- [ ] 重复打卡：弹出"今日已打卡"提示
- [ ] 徽章列表：已获得/未获得正确分类 + 进度条正确显示
- [ ] WebSocket 徽章解锁：收到 badge_unlocked 事件 → 弹窗 + 刷新列表

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 颜色使用 CSS 变量（`--color-primary` / `--color-accent` / `--color-success` 等），**禁止** 硬编码色值
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **禁止** 在组件中直接操作 DOM，使用 Taro API
- 打卡日历 **必须** 支持月度切换（上/下月导航）
- 徽章进度条 **必须** 实时计算（progress/target × 100%）
