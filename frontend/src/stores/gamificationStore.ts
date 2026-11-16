/**
 * gamification 状态管理（09-gamification/frontend.md §3）
 * 积分 + 打卡日历 + 徽章列表 + 积分流水（R2-P2-2 批次H）；
 * doCheckin 成功后联动刷新积分与日历
 */
import { create } from 'zustand'
import * as gamificationApi from '@/services/gamification'
import type {
  PointsData,
  CheckInCalendarData,
  CheckInResult,
  BadgeListData,
  PointsHistoryData,
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
    } finally {
      set({ isLoadingPoints: false })
    }
  },

  fetchCalendar: async (year, month) => {
    set({ isLoadingCalendar: true })
    try {
      const res = await gamificationApi.getCheckinCalendar(year, month)
      set({ calendar: res.data.data })
    } finally {
      set({ isLoadingCalendar: false })
    }
  },

  /**
   * 手动打卡 — 成功后刷新积分与日历；失败向调用方抛出（请求层已把后端
   * message 放入 Error.message，页面 catch 后展示，40901 文案为「今日已打卡」）。
   */
  doCheckin: async () => {
    set({ isCheckingIn: true })
    try {
      const res = await gamificationApi.checkin()
      const result: CheckInResult = res.data.data
      // 打卡成功后刷新积分和日历
      await get().fetchPoints()
      await get().fetchCalendar()
      return result
    } finally {
      set({ isCheckingIn: false })
    }
  },

  fetchBadges: async () => {
    set({ isLoadingBadges: true })
    try {
      const res = await gamificationApi.getBadges()
      set({ badges: res.data.data })
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
