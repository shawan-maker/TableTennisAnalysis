/**
 * homeStore 单元测试（00-home/frontend.md §3，FS7）
 * - 概览落位 + adviceSummary 从 latest_advice_summary 提取
 * - 月历落位 + weekView 同步派生（7 天/今日打卡标记）
 * - 最近报告 items[0] 落位 / 空 → null / 失败 → null
 * - refreshAll 并发四调用（unread 委托 notificationStore + 三 fetch）
 * - 单区域失败静默不抛错
 */
import * as homeApi from '@/services/home'
import { useHomeStore } from '@/stores/homeStore'

/** 共享 mock：getState() 每次返回同一 mockFn，断言才能命中调用记录 */
const mockFetchUnreadCount = jest.fn().mockResolvedValue(0)
jest.mock('@/services/home', () => ({
  __esModule: true,
  getOverview: jest.fn(),
  getLatestReport: jest.fn(),
  getCheckinCalendar: jest.fn(),
}))
jest.mock('@/stores/notificationStore', () => ({
  useNotificationStore: { getState: () => ({ fetchUnreadCount: mockFetchUnreadCount }) },
}))

const api = homeApi as jest.Mocked<typeof homeApi>
const store = useHomeStore

const OVERVIEW = {
  win_rate: 0.62, wins: 6, losses: 4, analysis_count: 3,
  training_frequency_per_week: 2, streak_days: 3, trend: 'up',
  latest_advice_summary: {
    report_id: 9, summary: '加强正手拉冲', has_unresolved_issues: true,
    latest_report_at: '2026-11-05T10:00:00Z',
  },
}

const CALENDAR = {
  year: 2026, month: 11,
  days: ['2026-11-02', '2026-11-03', '2026-11-04'].map((d) => ({
    date: d, checked_in: d === '2026-11-04', type: null,
  })),
  monthly_checkin_count: 1, streak_days: 1,
}

const REPORT = {
  id: 7, task_id: 3, created_at: '2026-11-05T10:00:00Z',
  is_llm_generated: true, cover_image_url: null, report_summary: '分析完成',
}

const resetStore = () =>
  store.setState({
    overview: null, overviewLoading: false,
    checkinCalendar: null, weekView: null, checkinLoading: false,
    latestReport: null, reportLoading: false,
    adviceSummary: null, refreshing: false,
  })

describe('homeStore 概览', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('fetchOverview → overview 落位 + adviceSummary 从 latest_advice_summary 提取', async () => {
    api.getOverview.mockResolvedValue({ data: { data: OVERVIEW } } as any)
    await store.getState().fetchOverview()
    expect(store.getState().overview).toEqual(OVERVIEW)
    expect(store.getState().adviceSummary).toEqual(OVERVIEW.latest_advice_summary)
    expect(store.getState().overviewLoading).toBe(false)
  })

  it('fetchOverview latest_advice_summary=null → adviceSummary=null（空态横幅）', async () => {
    api.getOverview.mockResolvedValue({ data: { data: { ...OVERVIEW, latest_advice_summary: null } } } as any)
    await store.getState().fetchOverview()
    expect(store.getState().adviceSummary).toBeNull()
  })

  it('fetchOverview 失败 → 静默不抛错，overview 保持 null', async () => {
    api.getOverview.mockRejectedValue(new Error('network') as any)
    await expect(store.getState().fetchOverview()).resolves.toBeUndefined()
    expect(store.getState().overview).toBeNull()
    expect(store.getState().overviewLoading).toBe(false)
  })
})

describe('homeStore 打卡周视图', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('fetchCheckinCalendar → 月历落位 + weekView 派生 7 天', async () => {
    api.getCheckinCalendar.mockResolvedValue({ data: { data: CALENDAR } } as any)
    await store.getState().fetchCheckinCalendar()
    expect(store.getState().checkinCalendar).toEqual(CALENDAR)
    const wv = store.getState().weekView
    expect(wv).not.toBeNull()
    expect(wv!.days).toHaveLength(7)
    expect(wv!.todayCheckedIn).toBeDefined()
    expect(store.getState().checkinLoading).toBe(false)
  })

  it('fetchCheckinCalendar 失败 → 静默不抛错，weekView 保持 null', async () => {
    api.getCheckinCalendar.mockRejectedValue(new Error('network') as any)
    await expect(store.getState().fetchCheckinCalendar()).resolves.toBeUndefined()
    expect(store.getState().weekView).toBeNull()
  })
})

describe('homeStore 最近报告', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('fetchLatestReport → items[0] 落位', async () => {
    api.getLatestReport.mockResolvedValue({ data: { data: { items: [REPORT], total: 1, page: 1, page_size: 1 } } } as any)
    await store.getState().fetchLatestReport()
    expect(store.getState().latestReport).toEqual(REPORT)
  })

  it('fetchLatestReport items 空 → null', async () => {
    api.getLatestReport.mockResolvedValue({ data: { data: { items: [], total: 0, page: 1, page_size: 1 } } } as any)
    await store.getState().fetchLatestReport()
    expect(store.getState().latestReport).toBeNull()
  })

  it('fetchLatestReport 失败 → null + loading 收敛', async () => {
    api.getLatestReport.mockRejectedValue(new Error('network') as any)
    await store.getState().fetchLatestReport()
    expect(store.getState().latestReport).toBeNull()
    expect(store.getState().reportLoading).toBe(false)
  })
})

describe('homeStore refreshAll 并发', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('refreshAll → 四调用各 1 次（unread 委托 + 三 fetch），refreshing 收敛', async () => {
    api.getOverview.mockResolvedValue({ data: { data: OVERVIEW } } as any)
    api.getCheckinCalendar.mockResolvedValue({ data: { data: CALENDAR } } as any)
    api.getLatestReport.mockResolvedValue({ data: { data: { items: [REPORT] } } } as any)
    await store.getState().refreshAll()
    expect(mockFetchUnreadCount).toHaveBeenCalledTimes(1)
    expect(api.getOverview).toHaveBeenCalledTimes(1)
    expect(api.getCheckinCalendar).toHaveBeenCalledTimes(1)
    expect(api.getLatestReport).toHaveBeenCalledTimes(1)
    expect(store.getState().refreshing).toBe(false)
  })

  it('refreshAll 单区域失败 → 不阻塞其余调用（全部仍各 1 次）', async () => {
    api.getOverview.mockRejectedValue(new Error('fail-overview') as any)
    api.getCheckinCalendar.mockResolvedValue({ data: { data: CALENDAR } } as any)
    api.getLatestReport.mockResolvedValue({ data: { data: { items: [] } } } as any)
    await expect(store.getState().refreshAll()).resolves.toBeUndefined()
    expect(api.getCheckinCalendar).toHaveBeenCalledTimes(1)
    expect(api.getLatestReport).toHaveBeenCalledTimes(1)
    expect(store.getState().overview).toBeNull()
    expect(store.getState().refreshing).toBe(false)
  })
})
