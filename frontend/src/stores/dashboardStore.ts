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

  // 战绩趋势
  winRateTrend: WinRateTrendData | null
  trendPeriod: TrendPeriod
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

  fetchWinRateTrend: async (period?: TrendPeriod) => {
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
