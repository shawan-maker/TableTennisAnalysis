/**
 * dashboard Service 契约测试（04-前端实施计划.md FS4）
 * 断言每个函数的 HTTP 方法 + URL + 参数与后端 app/api/v1/dashboard/router.py 逐字一致（5 端点）
 */
import request from '@/services/request'
import * as dashboardApi from '@/services/dashboard'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
    patch: jest.fn().mockResolvedValue({ data: { data: {} } }),
    delete: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

const get = request.get as jest.Mock

describe('services/dashboard 契约（5 端点）', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('getOverview → GET /dashboard/overview（无参数）', async () => {
    await dashboardApi.getOverview()
    expect(get).toHaveBeenCalledWith('/dashboard/overview')
  })

  it('getWinRateTrend 缺省 → GET /dashboard/win-rate-trend {period:month}', async () => {
    await dashboardApi.getWinRateTrend()
    expect(get).toHaveBeenCalledWith('/dashboard/win-rate-trend', { period: 'month' })
  })

  it.each(['quarter', 'year'] as const)(
    'getWinRateTrend(%s) → GET /dashboard/win-rate-trend',
    async (period) => {
      await dashboardApi.getWinRateTrend(period)
      expect(get).toHaveBeenCalledWith('/dashboard/win-rate-trend', { period })
    }
  )

  it('getTechniqueStats → GET /dashboard/technique-stats（无参数）', async () => {
    await dashboardApi.getTechniqueStats()
    expect(get).toHaveBeenCalledWith('/dashboard/technique-stats')
  })

  it('getLandingHeatmap → GET /dashboard/landing-heatmap（无参数）', async () => {
    await dashboardApi.getLandingHeatmap()
    expect(get).toHaveBeenCalledWith('/dashboard/landing-heatmap')
  })

  it('getMatchRecords 缺省 → GET /dashboard/match-records {result:all, page:1, page_size:20}', async () => {
    await dashboardApi.getMatchRecords()
    expect(get).toHaveBeenCalledWith('/dashboard/match-records', {
      result: 'all',
      page: 1,
      page_size: 20,
    })
  })

  it('getMatchRecords(win, 2, 50) → 胜场筛选 + 分页参数透传', async () => {
    await dashboardApi.getMatchRecords('win', 2, 50)
    expect(get).toHaveBeenCalledWith('/dashboard/match-records', {
      result: 'win',
      page: 2,
      page_size: 50,
    })
  })

  it('响应类型与后端字段对齐（OverviewData 含 is_readonly 可选字段）', () => {
    // 编译期契约：is_readonly 为可选（R12-Dash-2 降级标记）
    const overview: dashboardApi.OverviewData = {
      win_rate: 0.56,
      wins: 5,
      losses: 4,
      analysis_count: 7,
      training_frequency_per_week: 3,
      streak_days: 2,
      trend: 'up',
      latest_advice_summary: {
        report_id: 7,
        summary: '加强反手',
        has_unresolved_issues: true,
        latest_report_at: '2026-11-04T09:10:00',
      },
    }
    const readonlyOverview: dashboardApi.OverviewData = { ...overview, is_readonly: true }
    expect(readonlyOverview.is_readonly).toBe(true)
  })
})
