/**
 * progress Service 契约测试（04-前端实施计划.md FS4）
 * 断言每个函数的 HTTP 方法 + URL + 参数与后端 app/api/v1/progress/router.py 逐字一致（6 端点）
 */
import request from '@/services/request'
import * as progressApi from '@/services/progress'

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

describe('services/progress 契约（6 端点）', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('listSnapshots 缺省 → GET /progress/snapshots（无参数）', async () => {
    await progressApi.listSnapshots()
    expect(get).toHaveBeenCalledWith('/progress/snapshots', undefined)
  })

  it('listSnapshots({period, page, page_size}) → 参数透传（status 可选）', async () => {
    await progressApi.listSnapshots({ period: 'quarter', page: 2, page_size: 50 })
    expect(get).toHaveBeenCalledWith('/progress/snapshots', {
      period: 'quarter',
      page: 2,
      page_size: 50,
    })
  })

  it('getTechniqueTrends → GET /progress/technique-trends（无参数）', async () => {
    await progressApi.getTechniqueTrends()
    expect(get).toHaveBeenCalledWith('/progress/technique-trends')
  })

  it('getTechniqueTrendDetail → GET /progress/technique-trends/{metric}（路径参数拼接）', async () => {
    await progressApi.getTechniqueTrendDetail('backhand_ratio')
    expect(get).toHaveBeenCalledWith('/progress/technique-trends/backhand_ratio')
  })

  it('getComparison → GET /progress/comparison {report_a, report_b}', async () => {
    await progressApi.getComparison(7, 12)
    expect(get).toHaveBeenCalledWith('/progress/comparison', { report_a: 7, report_b: 12 })
  })

  it('getSummary → GET /progress/summary（无参数）', async () => {
    await progressApi.getSummary()
    expect(get).toHaveBeenCalledWith('/progress/summary')
  })

  it('getProblemChanges → GET /progress/problem-changes（无参数）', async () => {
    await progressApi.getProblemChanges()
    expect(get).toHaveBeenCalledWith('/progress/problem-changes')
  })

  it('响应类型契约：ComparisonData landing 键名为 forehand_pct（R4-Progress-8）', () => {
    const data: progressApi.ComparisonData = {
      report_a: { id: 7, created_at: '2026-11-04T09:10:00' },
      report_b: { id: 12, created_at: '2026-11-05T09:10:00' },
      comparisons: {
        technique_stats: {
          forehand_ratio: { a: 0.5, b: 0.55, change: 0.05 },
          backhand_ratio: { a: 0.35, b: 0.3, change: -0.05 },
          serve_ratio: { a: 0.15, b: 0.15, change: 0 },
        },
        landing: {
          forehand_pct: { a: 0.4, b: 0.45, change: 0.05 },
          backhand_pct: { a: 0.4, b: 0.35, change: -0.05 },
          middle_pct: { a: 0.2, b: 0.2, change: 0 },
        },
        rally: { avg_length_a: 5.2, avg_length_b: 6.1, max_length_a: 12, max_length_b: 14, change: 0.9 },
        ball_speed: { avg_a: 18.2, avg_b: 19.0, max_a: 24, max_b: 25, change: 0.8 },
        score_analysis: { win_rate_a: 0.5, win_rate_b: 0.6, change: 0.1 },
        problem_changes: { new: ['反手弱'], resolved: [], persistent: [] },
      },
    }
    expect(Object.keys(data.comparisons.landing)).toEqual([
      'forehand_pct',
      'backhand_pct',
      'middle_pct',
    ])
  })

  it('响应类型契约：ProblemChangeItem 为结构化对象（渲染用 problem_name）', () => {
    const item: progressApi.ProblemChangeItem = {
      problem_id: 'PROBLEM_NEW_0',
      problem_name: '反手连续性差',
      first_seen: '2026-11-05',
      last_seen: null,
      persistence_count: null,
    }
    expect(item.problem_name).toBe('反手连续性差')
  })

  it('响应类型契约：SummaryData 含 training_plan_status（R4-Progress-4，可空）', () => {
    const summary: progressApi.SummaryData = {
      summary_period: 'recent',
      total_analyses: 2,
      overall_progress: 'improving',
      metric_trends: [],
      problem_changes: { new: [], resolved: [], persistent: [] },
      training_plan_status: {
        current_plan_id: '3',
        plan_version: 1,
        last_adjustment: null,
        adjustment_reason: null,
        goal_completion: { backhand_ratio: '91%' },
      },
      forecast: {},
    }
    expect(summary.training_plan_status?.goal_completion.backhand_ratio).toBe('91%')
  })
})
