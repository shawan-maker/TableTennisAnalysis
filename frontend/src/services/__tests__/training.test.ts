/**
 * training Service 契约测试（04-前端实施计划.md FS5）
 * 断言每个函数的 HTTP 方法 + URL + 参数与后端 app/api/v1/training/router.py
 * 逐字一致（8 端点）
 */
import request from '@/services/request'
import * as trainingApi from '@/services/training'

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
const post = request.post as jest.Mock

describe('services/training 契约（8 端点）', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('getContextualAdvice → GET /training/advice/contextual（无参数）', async () => {
    await trainingApi.getContextualAdvice()
    expect(get).toHaveBeenCalledWith('/training/advice/contextual')
  })

  it('getAdviceByReport(7) → GET /training/advice/7', async () => {
    await trainingApi.getAdviceByReport(7)
    expect(get).toHaveBeenCalledWith('/training/advice/7')
  })

  it('getTemplates 缺省 → GET /training/templates（不含 problem_id 键）', async () => {
    await trainingApi.getTemplates()
    expect(get).toHaveBeenCalledWith('/training/templates', { page: 1, page_size: 20 })
  })

  it('getTemplates(problemId, 2, 50) → problem_id 筛选 + 分页透传', async () => {
    await trainingApi.getTemplates('BACKHAND', 2, 50)
    expect(get).toHaveBeenCalledWith('/training/templates', {
      problem_id: 'BACKHAND',
      page: 2,
      page_size: 50,
    })
  })

  it('getTemplateDetail(3) → GET /training/templates/3', async () => {
    await trainingApi.getTemplateDetail(3)
    expect(get).toHaveBeenCalledWith('/training/templates/3')
  })

  it('getPlanAdjustments(11) → GET /training/plans/11/adjustments', async () => {
    await trainingApi.getPlanAdjustments(11)
    expect(get).toHaveBeenCalledWith('/training/plans/11/adjustments')
  })

  it('reEvaluatePlan(11) → POST /training/plans/11/re-evaluate', async () => {
    await trainingApi.reEvaluatePlan(11)
    expect(post).toHaveBeenCalledWith('/training/plans/11/re-evaluate')
  })

  it('listTrainingSessions 缺省 → GET /training/plans/11/sessions {page:1, page_size:20}', async () => {
    await trainingApi.listTrainingSessions(11)
    expect(get).toHaveBeenCalledWith('/training/plans/11/sessions', {
      page: 1,
      page_size: 20,
    })
  })

  it('listTrainingSessions(11, 3, 50) → 分页透传', async () => {
    await trainingApi.listTrainingSessions(11, 3, 50)
    expect(get).toHaveBeenCalledWith('/training/plans/11/sessions', {
      page: 3,
      page_size: 50,
    })
  })

  it('completeTrainingSession(11, 4) → POST /training/plans/11/sessions/4/complete', async () => {
    await trainingApi.completeTrainingSession(11, 4)
    expect(post).toHaveBeenCalledWith('/training/plans/11/sessions/4/complete')
  })

  it('响应类型与后端字段对齐（P3 契约同步 3 字段）', () => {
    // 编译期契约：FS5-P3 补充字段（后端返回）
    const detail: trainingApi.TemplateDetail = {
      id: 1,
      template_code: 'TPL_A',
      name: '模板A',
      problem_id: null,
      template_data: { goal: { metric: 'backhand_ratio', target: 0.4 } },
      created_at: '2026-11-06T00:00:00',
    }
    expect(detail.created_at).toBe('2026-11-06T00:00:00')

    const list: trainingApi.TrainingSessionListData = {
      plan_id: 11,
      total: 4,
      page: 1,
      page_size: 20,
      items: [],
    }
    expect(list.plan_id).toBe(11)

    const complete: trainingApi.CompleteSessionData = {
      session_id: 4,
      is_completed: true,
      plan_progress: 50,
      points_earned: 5,
      completed_at: '2026-11-06T08:00:00',
    }
    expect(complete.completed_at).toBe('2026-11-06T08:00:00')
  })
})
