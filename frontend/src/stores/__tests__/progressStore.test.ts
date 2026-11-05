/**
 * progressStore 单元测试（08-progress_analysis/frontend.md §3）
 * - 五 fetch 数据落位 + loading 收敛
 * - fetchTrendDetail 404/40415 错误分支（trendDetailError 承载，trendDetail 保持 null）
 * - 失败不抛错（页面靠 console + 空态兜底）
 */
import * as progressApi from '@/services/progress'
import { useProgressStore } from '@/stores/progressStore'

jest.mock('@/services/progress', () => ({
  __esModule: true,
  listSnapshots: jest.fn(),
  getTechniqueTrends: jest.fn(),
  getTechniqueTrendDetail: jest.fn(),
  getComparison: jest.fn(),
  getSummary: jest.fn(),
  getProblemChanges: jest.fn(),
}))

const api = progressApi as jest.Mocked<typeof progressApi>
const store = useProgressStore

const resetStore = () =>
  store.setState({
    snapshots: [],
    snapshotTotal: 0,
    trends: [],
    trendDetail: null,
    trendDetailError: null,
    comparison: null,
    summary: null,
    problemChanges: null,
    loading: false,
  })

describe('progressStore 五 fetch 落位', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('fetchSnapshots → snapshots/total 落位（page_size=50 固定）', async () => {
    api.listSnapshots.mockResolvedValue({
      data: {
        data: {
          total: 2,
          page: 1,
          page_size: 50,
          items: [
            { id: 1, report_id: 7, created_at: '2026-11-04T09:10:00', metrics_snapshot: {} },
            { id: 2, report_id: 12, created_at: '2026-11-05T09:10:00', metrics_snapshot: {} },
          ],
        },
      },
    } as any)
    await store.getState().fetchSnapshots()
    expect(api.listSnapshots).toHaveBeenCalledWith({ period: undefined, page: 1, page_size: 50 })
    expect(store.getState().snapshots).toHaveLength(2)
    expect(store.getState().snapshotTotal).toBe(2)
  })

  it('fetchTrends → 后端 {metrics} 包装解包', async () => {
    api.getTechniqueTrends.mockResolvedValue({
      data: { data: { metrics: [{ metric: 'backhand_ratio', metric_name: '反手使用率' }] } },
    } as any)
    await store.getState().fetchTrends()
    expect(store.getState().trends).toHaveLength(1)
    expect(store.getState().trends[0].metric).toBe('backhand_ratio')
  })

  it('fetchTrendDetail 成功 → trendDetail 落位 + error 清空', async () => {
    const detail = {
      metric: 'backhand_ratio',
      metric_name: '反手使用率',
      current_value: 0.32,
      target_value: 0.35,
      target_progress: 91,
      trend: 'improving',
      change_rate: 0.05,
      persistence_count: 2,
      history: [
        { date: '2026-11-04T09:10:00', value: 0.3 },
        { date: '2026-11-05T09:10:00', value: 0.32 },
      ],
    }
    api.getTechniqueTrendDetail.mockResolvedValue({ data: { data: detail } } as any)
    await store.getState().fetchTrendDetail('backhand_ratio')
    expect(store.getState().trendDetail).toEqual(detail)
    expect(store.getState().trendDetailError).toBeNull()
  })

  it('fetchTrendDetail 404/40415 无效指标 → trendDetailError 承载错误信息', async () => {
    api.getTechniqueTrendDetail.mockRejectedValue({ message: '指标不存在' } as any)
    await store.getState().fetchTrendDetail('not_a_metric')
    expect(store.getState().trendDetail).toBeNull()
    expect(store.getState().trendDetailError).toBe('指标不存在')
    expect(store.getState().loading).toBe(false)
  })

  it('fetchComparison → comparison 落位', async () => {
    api.getComparison.mockResolvedValue({
      data: {
        data: {
          report_a: { id: 7, created_at: '2026-11-04T09:10:00' },
          report_b: { id: 12, created_at: '2026-11-05T09:10:00' },
          comparisons: {
            technique_stats: {},
            landing: {},
            rally: { avg_length_a: 5, avg_length_b: 6, max_length_a: 10, max_length_b: 12, change: 1 },
            ball_speed: { avg_a: 18, avg_b: 19, max_a: 24, max_b: 25, change: 1 },
            score_analysis: { win_rate_a: 0.5, win_rate_b: 0.6, change: 0.1 },
            problem_changes: { new: [], resolved: [], persistent: [] },
          },
        },
      },
    } as any)
    await store.getState().fetchComparison(7, 12)
    expect(api.getComparison).toHaveBeenCalledWith(7, 12)
    expect(store.getState().comparison?.report_b.id).toBe(12)
  })

  it('fetchSummary → summary 落位（training_plan_status 透传）', async () => {
    const summary = {
      summary_period: 'recent',
      total_analyses: 2,
      overall_progress: 'improving',
      metric_trends: [],
      problem_changes: { new: [], resolved: [], persistent: [] },
      training_plan_status: null,
      forecast: {},
    }
    api.getSummary.mockResolvedValue({ data: { data: summary } } as any)
    await store.getState().fetchSummary()
    expect(store.getState().summary).toEqual(summary)
  })

  it('fetchProblemChanges → 结构化对象数组落位（渲染用 problem_name）', async () => {
    api.getProblemChanges.mockResolvedValue({
      data: {
        data: {
          new: [{ problem_id: 'PROBLEM_NEW_0', problem_name: '反手弱', first_seen: '2026-11-05', last_seen: null, persistence_count: null }],
          resolved: [],
          persistent: [],
        },
      },
    } as any)
    await store.getState().fetchProblemChanges()
    expect(store.getState().problemChanges?.new[0].problem_name).toBe('反手弱')
  })

  it('任一 fetch 失败 → 不抛错 + loading 收敛', async () => {
    api.getSummary.mockRejectedValue(new Error('network') as any)
    await expect(store.getState().fetchSummary()).resolves.toBeUndefined()
    expect(store.getState().summary).toBeNull()
    expect(store.getState().loading).toBe(false)
  })
})
