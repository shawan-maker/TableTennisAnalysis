/**
 * data_dashboard 状态管理（06-data_dashboard/frontend.md §3）
 * 五区独立 loading + 分页比赛记录 + 全量刷新
 */
import { create } from 'zustand'
import * as dashboardApi from '@/services/dashboard'
import type {
  OverviewData,
  WinRateTrendData,
  TechniqueStatsData,
  LandingHeatmapData,
  MatchRecordItem,
  MatchRecordsData,
  TrendPeriod,
  ResultFilter,
} from '@/services/dashboard'

export type { TrendPeriod, ResultFilter }

interface DashboardState {
  // 概览
  overview: OverviewData | null
  overviewLoading: boolean
  // R-FE-R1 批次B（FE-P2-16）：区块错误态（frontend.md L1460「网络错误显示错误提示」
  // ——修复前五 fetch 均 catch 静默，失败区块永久空白无提示无重试）
  overviewError: boolean

  // 战绩趋势
  winRateTrend: WinRateTrendData | null
  trendPeriod: TrendPeriod
  trendLoading: boolean
  trendError: boolean

  // 技术统计
  techniqueStats: TechniqueStatsData | null
  techniqueLoading: boolean
  techniqueError: boolean

  // 落点热图
  heatmap: LandingHeatmapData | null
  heatmapLoading: boolean
  heatmapError: boolean

  // 比赛记录
  matchRecords: MatchRecordItem[]
  matchTotal: number
  matchPage: number
  matchPageSize: number
  matchFilter: ResultFilter
  matchLoading: boolean
  matchHasMore: boolean
  matchError: boolean

  // Actions
  fetchOverview: () => Promise<void>
  fetchWinRateTrend: (period?: TrendPeriod) => Promise<void>
  fetchTechniqueStats: () => Promise<void>
  fetchLandingHeatmap: () => Promise<void>
  fetchMatchRecords: (refresh?: boolean) => Promise<void>
  setTrendPeriod: (period: TrendPeriod) => void
  setMatchFilter: (filter: ResultFilter) => void
  loadMoreMatches: () => Promise<void>
  refreshAll: () => Promise<void>
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  overview: null,
  overviewLoading: false,
  overviewError: false,

  winRateTrend: null,
  trendPeriod: 'month',
  trendLoading: false,
  trendError: false,

  techniqueStats: null,
  techniqueLoading: false,
  techniqueError: false,

  heatmap: null,
  heatmapLoading: false,
  heatmapError: false,

  matchRecords: [],
  matchTotal: 0,
  matchPage: 1,
  matchPageSize: 20,
  matchFilter: 'all',
  matchLoading: false,
  matchHasMore: false,
  matchError: false,

  fetchOverview: async () => {
    set({ overviewLoading: true, overviewError: false })
    try {
      const res = await dashboardApi.getOverview()
      set({ overview: res.data.data })
    } catch (err) {
      console.error('Failed to fetch overview:', err)
      set({ overviewError: true })
    } finally {
      set({ overviewLoading: false })
    }
  },

  fetchWinRateTrend: async (period?: TrendPeriod) => {
    const p = period ?? get().trendPeriod
    set({ trendLoading: true, trendError: false })
    try {
      const res = await dashboardApi.getWinRateTrend(p)
      set({ winRateTrend: res.data.data, trendPeriod: p })
    } catch (err) {
      console.error('Failed to fetch win rate trend:', err)
      set({ trendError: true })
    } finally {
      set({ trendLoading: false })
    }
  },

  fetchTechniqueStats: async () => {
    set({ techniqueLoading: true, techniqueError: false })
    try {
      const res = await dashboardApi.getTechniqueStats()
      set({ techniqueStats: res.data.data })
    } catch (err) {
      console.error('Failed to fetch technique stats:', err)
      set({ techniqueError: true })
    } finally {
      set({ techniqueLoading: false })
    }
  },

  fetchLandingHeatmap: async () => {
    set({ heatmapLoading: true, heatmapError: false })
    try {
      const res = await dashboardApi.getLandingHeatmap()
      set({ heatmap: res.data.data })
    } catch (err) {
      console.error('Failed to fetch landing heatmap:', err)
      set({ heatmapError: true })
    } finally {
      set({ heatmapLoading: false })
    }
  },

  fetchMatchRecords: async (refresh: boolean = false) => {
    const { matchPage, matchPageSize, matchFilter } = get()
    const page = refresh ? 1 : matchPage
    set({ matchLoading: true, matchError: false })
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
      set({ matchError: true })
    } finally {
      set({ matchLoading: false })
    }
  },

  setTrendPeriod: (period: TrendPeriod) => {
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
