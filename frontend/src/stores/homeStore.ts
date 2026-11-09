/**
 * home 模块状态管理（00-home/frontend.md §3）
 * 首页聚合：概览（含训练提醒）/ 打卡周视图 / 最近报告 / 未读数，
 * refreshAll 并发加载（反幻觉约束：禁止串行请求）；
 * 单区域失败静默（不阻塞其他区域渲染）。
 *
 * FS7-P3：
 * - 打卡周视图由月历前端派生（utils/weekView.buildWeekView），checkin 状态
 *   存月历原始数据 + weekView 派生结果双份（派生在 fetch 后同步计算）；
 * - 训练提醒（adviceSummary）从 overview.latest_advice_summary 提取（设计 §3 同构）；
 * - 未读数复用 notificationStore（FS6 单例，铃铛/角标共用），本 store 不重复持有
 *   ——改为从 notificationStore 读取，fetch 委托 notificationStore.fetchUnreadCount。
 */
import { create } from 'zustand'
import * as homeApi from '@/services/home'
import type {
  OverviewData, AdviceSummary, ReportListItem, CheckInCalendarData,
} from '@/services/home'
import { buildWeekView } from '@/utils/weekView'
import type { WeekView } from '@/utils/weekView'
import { useNotificationStore } from '@/stores/notificationStore'

interface HomeState {
  // 数据概览（FS4 OverviewData，含 latest_advice_summary）
  overview: OverviewData | null
  overviewLoading: boolean

  // 打卡月历（原始）+ 周视图（派生）
  checkinCalendar: CheckInCalendarData | null
  weekView: WeekView | null
  checkinLoading: boolean

  // 最近分析报告（FS7-P3：ReportListItem，非设计样例的 title/overall_score）
  latestReport: ReportListItem | null
  reportLoading: boolean

  // 训练提醒（overview 提取）
  adviceSummary: AdviceSummary | null

  // 全局加载
  refreshing: boolean

  // Actions
  fetchOverview: () => Promise<void>
  fetchCheckinCalendar: () => Promise<void>
  fetchLatestReport: () => Promise<void>
  refreshAll: () => Promise<void>
}

export const useHomeStore = create<HomeState>((set) => ({
  overview: null,
  overviewLoading: false,
  checkinCalendar: null,
  weekView: null,
  checkinLoading: false,
  latestReport: null,
  reportLoading: false,
  adviceSummary: null,
  refreshing: false,

  fetchOverview: async () => {
    set({ overviewLoading: true })
    try {
      const res = await homeApi.getOverview()
      const data = res.data.data
      set({
        overview: data,
        // 训练提醒从概览响应提取（设计 §3 同构）
        adviceSummary: data.latest_advice_summary ?? null,
      })
    } catch (error) {
      // 单区域失败静默（反幻觉约束：不得阻塞其他模块渲染）
      console.error('fetchOverview failed', error)
    } finally {
      set({ overviewLoading: false })
    }
  },

  fetchCheckinCalendar: async () => {
    set({ checkinLoading: true })
    try {
      const res = await homeApi.getCheckinCalendar()
      const calendar = res.data.data
      set({ checkinCalendar: calendar, weekView: buildWeekView(calendar) })
    } catch (error) {
      console.error('fetchCheckinCalendar failed', error)
    } finally {
      set({ checkinLoading: false })
    }
  },

  fetchLatestReport: async () => {
    set({ reportLoading: true })
    try {
      const res = await homeApi.getLatestReport()
      const items: ReportListItem[] = res.data.data.items || []
      set({ latestReport: items.length > 0 ? items[0] : null })
    } catch {
      set({ latestReport: null })
    } finally {
      set({ reportLoading: false })
    }
  },

  refreshAll: async () => {
    set({ refreshing: true })
    // 并发加载（未读数委托 notificationStore，FS6 单例共用；失败静默）
    await Promise.all([
      useNotificationStore.getState().fetchUnreadCount().catch(() => {}),
      useHomeStore.getState().fetchOverview(),
      useHomeStore.getState().fetchCheckinCalendar(),
      useHomeStore.getState().fetchLatestReport(),
    ])
    set({ refreshing: false })
  },
}))
