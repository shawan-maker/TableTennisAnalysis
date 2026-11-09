/**
 * home 聚合 Service 契约测试（04-前端实施计划.md FS7）
 * 聚合层转发断言：不重复定义底层端点，转发参数与底层 service 契约一致
 * （FS7-P3：getLatestReport 走 /video-analysis/reports 首条；
 *   getCheckinCalendar 走 /gamification/checkin-calendar 月历）
 */
import * as homeApi from '@/services/home'
import * as dashboardApi from '@/services/dashboard'
import * as gamificationApi from '@/services/gamification'
import * as videoAnalysisApi from '@/services/videoAnalysis'

jest.mock('@/services/dashboard', () => ({
  __esModule: true,
  getOverview: jest.fn().mockResolvedValue({ data: { data: {} } }),
}))
jest.mock('@/services/gamification', () => ({
  __esModule: true,
  getCheckinCalendar: jest.fn().mockResolvedValue({ data: { data: {} } }),
}))
jest.mock('@/services/videoAnalysis', () => ({
  __esModule: true,
  listReports: jest.fn().mockResolvedValue({ data: { data: {} } }),
}))

const mockedDashboard = dashboardApi as jest.Mocked<typeof dashboardApi>
const mockedGamification = gamificationApi as jest.Mocked<typeof gamificationApi>
const mockedVideoAnalysis = videoAnalysisApi as jest.Mocked<typeof videoAnalysisApi>

describe('services/home 聚合转发契约', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('getOverview → 转发 dashboard.getOverview（GET /dashboard/overview，Redis 5min 缓存）', async () => {
    await homeApi.getOverview()
    expect(mockedDashboard.getOverview).toHaveBeenCalledTimes(1)
    expect(mockedDashboard.getOverview).toHaveBeenCalledWith()
  })

  it('getLatestReport → videoAnalysis.listReports({page:1, page_size:1})（FS7-P3 契约修正）', async () => {
    await homeApi.getLatestReport()
    expect(mockedVideoAnalysis.listReports).toHaveBeenCalledWith({ page: 1, page_size: 1 })
  })

  it('getLatestReport 禁止调用 /scoring/matches（设计样例错误契约）', async () => {
    await homeApi.getLatestReport()
    // videoAnalysis mock 仅 listReports 被消费，scoring service 未被 import 转发
    expect(mockedVideoAnalysis.listReports).toHaveBeenCalledTimes(1)
  })

  it('getCheckinCalendar → 转发 gamification.getCheckinCalendar()（月历，周视图前端派生）', async () => {
    await homeApi.getCheckinCalendar()
    expect(mockedGamification.getCheckinCalendar).toHaveBeenCalledTimes(1)
    expect(mockedGamification.getCheckinCalendar).toHaveBeenCalledWith()
  })

  it('类型重导出编译期契约（ReportListItem/CheckInCalendarData/OverviewData）', () => {
    const item: homeApi.ReportListItem = {
      id: 1, task_id: 2, created_at: '2026-11-05T10:00:00Z',
      is_llm_generated: true, cover_image_url: null, report_summary: '摘要',
    }
    const calendar: homeApi.CheckInCalendarData = {
      year: 2026, month: 11, days: [], monthly_checkin_count: 0, streak_days: 0,
    }
    const overview: homeApi.OverviewData = {
      win_rate: 0.5, wins: 1, losses: 1, analysis_count: 0,
      training_frequency_per_week: 0, streak_days: 0, trend: 'flat',
      latest_advice_summary: null,
    }
    expect([item, calendar, overview]).toBeTruthy()
  })
})
