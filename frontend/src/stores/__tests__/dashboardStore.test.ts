/**
 * dashboardStore 单元测试（06-data_dashboard/frontend.md §3）
 * - 五区独立 loading + 数据落位
 * - 战绩趋势 period 切换（setTrendPeriod 触发重新拉取）
 * - 比赛记录分页（refresh 覆盖 / loadMore 追加 + hasMore 边界）
 * - refreshAll 并发五请求
 */
import * as dashboardApi from '@/services/dashboard'
import { useDashboardStore } from '@/stores/dashboardStore'

jest.mock('@/services/dashboard', () => ({
  __esModule: true,
  getOverview: jest.fn(),
  getWinRateTrend: jest.fn(),
  getTechniqueStats: jest.fn(),
  getLandingHeatmap: jest.fn(),
  getMatchRecords: jest.fn(),
}))

const api = dashboardApi as jest.Mocked<typeof dashboardApi>
const store = useDashboardStore

const OVERVIEW = {
  win_rate: 0.56,
  wins: 5,
  losses: 4,
  analysis_count: 7,
  training_frequency_per_week: 3,
  streak_days: 2,
  trend: 'up',
  latest_advice_summary: null,
}

const TREND = {
  labels: ['11/01', '11/02'],
  series: [
    { name: '胜率', data: [0.5, 0.6] },
    { name: '比赛场次', data: [2, 5] },
  ],
}

const PAGE_1 = {
  total: 25,
  page: 1,
  page_size: 20,
  items: Array.from({ length: 20 }, (_, i) => ({
    id: i + 1,
    opponent_name: `对手${i}`,
    opponent_rating: 1500,
    my_score: 11,
    opponent_score: 7,
    is_win: true,
    format: 'bo5',
    match_type: 'friendly',
    match_date: '2026-11-04',
  })),
}

const resetStore = () =>
  store.setState({
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
  })

describe('dashboardStore 概览/趋势/技术/热图', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('fetchOverview → overview 落位 + loading 收敛', async () => {
    api.getOverview.mockResolvedValue({ data: { data: OVERVIEW } } as any)
    await store.getState().fetchOverview()
    expect(api.getOverview).toHaveBeenCalled()
    expect(store.getState().overview).toEqual(OVERVIEW)
    expect(store.getState().overviewLoading).toBe(false)
  })

  it('fetchOverview 失败 → 数据保持 null 不抛错', async () => {
    api.getOverview.mockRejectedValue(new Error('network') as any)
    await store.getState().fetchOverview()
    expect(store.getState().overview).toBeNull()
    expect(store.getState().overviewLoading).toBe(false)
  })

  it('setTrendPeriod(quarter) → period 更新 + 以新 period 拉取', async () => {
    api.getWinRateTrend.mockResolvedValue({ data: { data: TREND } } as any)
    store.getState().setTrendPeriod('quarter')
    expect(store.getState().trendPeriod).toBe('quarter')
    await new Promise((r) => setTimeout(r, 0))
    expect(api.getWinRateTrend).toHaveBeenCalledWith('quarter')
  })

  it('fetchWinRateTrend() 无参 → 使用当前 trendPeriod', async () => {
    store.setState({ trendPeriod: 'year' })
    api.getWinRateTrend.mockResolvedValue({ data: { data: TREND } } as any)
    await store.getState().fetchWinRateTrend()
    expect(api.getWinRateTrend).toHaveBeenCalledWith('year')
    expect(store.getState().winRateTrend).toEqual(TREND)
  })

  it('fetchLandingHeatmap → heatmap 落位', async () => {
    const heatmap = {
      nine_grid: [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
      distribution: { forehand: 0.4, backhand: 0.4, middle: 0.2 },
      total_rallies: 45,
      source_reports_count: 3,
    }
    api.getLandingHeatmap.mockResolvedValue({ data: { data: heatmap } } as any)
    await store.getState().fetchLandingHeatmap()
    expect(store.getState().heatmap).toEqual(heatmap)
  })
})

describe('dashboardStore 比赛记录分页', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('fetchMatchRecords(true) → 首页覆盖 + hasMore=true（total>page*size）', async () => {
    api.getMatchRecords.mockResolvedValue({ data: { data: PAGE_1 } } as any)
    await store.getState().fetchMatchRecords(true)
    expect(api.getMatchRecords).toHaveBeenCalledWith('all', 1, 20)
    expect(store.getState().matchRecords).toHaveLength(20)
    expect(store.getState().matchHasMore).toBe(true)
  })

  it('setMatchFilter(win) → filter 更新 + refresh 首页', async () => {
    const winPage = { ...PAGE_1, total: 5, items: PAGE_1.items.slice(0, 5) }
    api.getMatchRecords.mockResolvedValue({ data: { data: winPage } } as any)
    store.getState().setMatchFilter('win')
    await new Promise((r) => setTimeout(r, 0))
    expect(store.getState().matchFilter).toBe('win')
    expect(api.getMatchRecords).toHaveBeenCalledWith('win', 1, 20)
    expect(store.getState().matchRecords).toHaveLength(5)
    expect(store.getState().matchHasMore).toBe(false)
  })

  it('loadMoreMatches → page+1 追加（refresh=false）', async () => {
    api.getMatchRecords.mockResolvedValue({ data: { data: PAGE_1 } } as any)
    await store.getState().fetchMatchRecords(true)
    const page2 = {
      ...PAGE_1,
      page: 2,
      items: PAGE_1.items.map((it) => ({ ...it, id: it.id + 100 })),
    }
    api.getMatchRecords.mockResolvedValue({ data: { data: page2 } } as any)
    await store.getState().loadMoreMatches()
    expect(api.getMatchRecords).toHaveBeenLastCalledWith('all', 2, 20)
    expect(store.getState().matchRecords).toHaveLength(40)
    expect(store.getState().matchPage).toBe(2)
  })

  it('loadMoreMatches 在 matchHasMore=false 时不再请求', async () => {
    store.setState({ matchHasMore: false, matchLoading: false })
    await store.getState().loadMoreMatches()
    expect(api.getMatchRecords).not.toHaveBeenCalled()
  })

  it('loadMoreMatches 在 loading 中不再并发请求', async () => {
    store.setState({ matchHasMore: true, matchLoading: true })
    await store.getState().loadMoreMatches()
    expect(api.getMatchRecords).not.toHaveBeenCalled()
  })
})

describe('dashboardStore.refreshAll 并发刷新', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('refreshAll → 五请求并发发出', async () => {
    api.getOverview.mockResolvedValue({ data: { data: OVERVIEW } } as any)
    api.getWinRateTrend.mockResolvedValue({ data: { data: TREND } } as any)
    api.getTechniqueStats.mockResolvedValue({ data: { data: { technique_distribution: [] } } } as any)
    api.getLandingHeatmap.mockResolvedValue({ data: { data: {} } } as any)
    api.getMatchRecords.mockResolvedValue({ data: { data: PAGE_1 } } as any)

    await store.getState().refreshAll()

    expect(api.getOverview).toHaveBeenCalledTimes(1)
    expect(api.getWinRateTrend).toHaveBeenCalledTimes(1)
    expect(api.getTechniqueStats).toHaveBeenCalledTimes(1)
    expect(api.getLandingHeatmap).toHaveBeenCalledTimes(1)
    expect(api.getMatchRecords).toHaveBeenCalledWith('all', 1, 20)
  })
})
