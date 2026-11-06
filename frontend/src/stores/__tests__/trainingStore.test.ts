/**
 * trainingStore 状态机测试（04-前端实施计划.md FS5）
 * 覆盖：advice 成败、模板分页/加载更多、会员守卫 40300、
 * 训练单列表、标记完成 Toast+刷新、重新评估
 */
import Taro from '@tarojs/taro'
import * as trainingApi from '@/services/training'
import { useTrainingStore, isMembershipError, MEMBERSHIP_ERROR_CODE } from '@/stores/trainingStore'

jest.mock('@/services/training', () => ({
  __esModule: true,
  getAdviceByReport: jest.fn(),
  getContextualAdvice: jest.fn(),
  getTemplates: jest.fn(),
  getTemplateDetail: jest.fn(),
  getPlanAdjustments: jest.fn(),
  reEvaluatePlan: jest.fn(),
  listTrainingSessions: jest.fn(),
  completeTrainingSession: jest.fn(),
}))

const getTemplates = trainingApi.getTemplates as jest.Mock
const getContextualAdvice = trainingApi.getContextualAdvice as jest.Mock
const getAdviceByReport = trainingApi.getAdviceByReport as jest.Mock
const getTemplateDetail = trainingApi.getTemplateDetail as jest.Mock
const listTrainingSessions = trainingApi.listTrainingSessions as jest.Mock
const completeTrainingSession = trainingApi.completeTrainingSession as jest.Mock
const reEvaluatePlan = trainingApi.reEvaluatePlan as jest.Mock

const ADVICE = {
  report_id: 7,
  is_first_analysis: true,
  diagnosis: [],
  suggestions: [],
  training_methods: [],
  training_plan_template: 'TPL_A',
}

const TPL_PAGE = (page: number) => ({
  data: {
    data: {
      total: 50,
      page,
      page_size: 20,
      items: Array.from({ length: 20 }, (_, i) => ({
        id: (page - 1) * 20 + i + 1,
        template_code: `TPL_${(page - 1) * 20 + i + 1}`,
        name: `模板${(page - 1) * 20 + i + 1}`,
        problem_id: null,
      })),
    },
  },
})

describe('trainingStore', () => {
  beforeEach(() => {
    // resetAllMocks：清 implementation + Once 队列（clearAllMocks 不清 once 队列，
    // 上一测试未消费的 mockResolvedValueOnce 会泄漏给下一测试）
    jest.resetAllMocks()
    useTrainingStore.setState({
      advice: null,
      adviceLoading: false,
      adviceError: null,
      templates: [],
      templateTotal: 0,
      templatePage: 1,
      templateProblemFilter: null,
      templateLoading: false,
      templateHasMore: false,
      templateError: null,
      templateNeedsMembership: false,
      currentTemplate: null,
      templateDetailLoading: false,
      templateDetailError: null,
      templateDetailNeedsMembership: false,
      adjustments: null,
      adjustmentsLoading: false,
      reEvaluating: false,
      sessions: [],
      sessionsTotal: 0,
      sessionsLoading: false,
      sessionsError: null,
      sessionsNeedsMembership: false,
      completeSessionLoading: false,
    })
  })

  describe('advice', () => {
    it('fetchContextualAdvice 成功 → advice 落库', async () => {
      getContextualAdvice.mockResolvedValue({ data: { data: ADVICE } })
      await useTrainingStore.getState().fetchContextualAdvice()
      const s = useTrainingStore.getState()
      expect(s.advice).toEqual(ADVICE)
      expect(s.adviceLoading).toBe(false)
      expect(s.adviceError).toBeNull()
    })

    it('fetchContextualAdvice 失败（404/40412）→ adviceError=后端 message', async () => {
      getContextualAdvice.mockRejectedValue(new Error('暂无分析报告'))
      await useTrainingStore.getState().fetchContextualAdvice()
      const s = useTrainingStore.getState()
      expect(s.advice).toBeNull()
      expect(s.adviceError).toBe('暂无分析报告')
    })

    it('fetchAdviceByReport(7) → 调用对应 service', async () => {
      getAdviceByReport.mockResolvedValue({ data: { data: ADVICE } })
      await useTrainingStore.getState().fetchAdviceByReport(7)
      expect(getAdviceByReport).toHaveBeenCalledWith(7)
      expect(useTrainingStore.getState().advice).toEqual(ADVICE)
    })
  })

  describe('templates 分页', () => {
    it('fetchTemplates(true) 首页 → 追加 items + hasMore 计算', async () => {
      getTemplates.mockResolvedValue(TPL_PAGE(1))
      await useTrainingStore.getState().fetchTemplates(true)
      const s = useTrainingStore.getState()
      expect(getTemplates).toHaveBeenCalledWith(undefined, 1, 20)
      expect(s.templates).toHaveLength(20)
      expect(s.templateTotal).toBe(50)
      expect(s.templateHasMore).toBe(true) // 1*20 < 50
    })

    it('loadMoreTemplates → 翻页追加且不重复', async () => {
      getTemplates.mockResolvedValueOnce(TPL_PAGE(1))
      await useTrainingStore.getState().fetchTemplates(true)
      getTemplates.mockResolvedValueOnce(TPL_PAGE(2))
      await useTrainingStore.getState().loadMoreTemplates()
      const s = useTrainingStore.getState()
      expect(getTemplates).toHaveBeenLastCalledWith(undefined, 2, 20)
      expect(s.templates).toHaveLength(40)
      expect(s.templateHasMore).toBe(true) // 2*20 < 50
      expect(s.templates[39].id).toBe(40)
    })

    it('会员守卫 40300 → needsMembership=true 且清空列表', async () => {
      const err = new Error('此功能需要会员') as Error & { code?: number }
      err.code = MEMBERSHIP_ERROR_CODE
      getTemplates.mockRejectedValue(err)
      useTrainingStore.setState({ templates: [{ id: 1, template_code: 'x', name: 'x', problem_id: null }] })
      await useTrainingStore.getState().fetchTemplates(true)
      const s = useTrainingStore.getState()
      expect(s.templateNeedsMembership).toBe(true)
      expect(s.templates).toHaveLength(0)
      expect(s.templateError).toBeNull()
    })

    it('isMembershipError：code=40300 判真，其它判假', () => {
      const e40300 = Object.assign(new Error('x'), { code: 40300 })
      const e40901 = Object.assign(new Error('x'), { code: 40901 })
      expect(isMembershipError(e40300)).toBe(true)
      expect(isMembershipError(e40901)).toBe(false)
      expect(isMembershipError(new Error('x'))).toBe(false)
    })
  })

  describe('模板详情', () => {
    it('成功 → currentTemplate', async () => {
      const detail = {
        id: 3,
        template_code: 'TPL_A',
        name: 'A',
        problem_id: null,
        template_data: {},
      }
      getTemplateDetail.mockResolvedValue({ data: { data: detail } })
      await useTrainingStore.getState().fetchTemplateDetail(3)
      expect(useTrainingStore.getState().currentTemplate).toEqual(detail)
    })

    it('404/40421 → templateDetailError 而非 needsMembership', async () => {
      getTemplateDetail.mockRejectedValue(new Error('模板不存在'))
      await useTrainingStore.getState().fetchTemplateDetail(99)
      const s = useTrainingStore.getState()
      expect(s.templateDetailError).toBe('模板不存在')
      expect(s.templateDetailNeedsMembership).toBe(false)
    })
  })

  describe('训练单', () => {
    const SESSIONS = {
      plan_id: 11,
      total: 4,
      page: 1,
      page_size: 20,
      items: [
        { id: 1, plan_id: 11, name: '正手攻球', scheduled_date: '2026-11-06', is_completed: false, completed_at: null, session_index: 1, reps: 100 },
        { id: 2, plan_id: 11, name: '反手拨球', scheduled_date: null, is_completed: true, completed_at: '2026-11-05T08:00:00', session_index: 2, reps: 80 },
      ],
    }

    it('fetchTrainingSessions 成功 → sessions/total', async () => {
      listTrainingSessions.mockResolvedValue({ data: { data: SESSIONS } })
      await useTrainingStore.getState().fetchTrainingSessions(11)
      const s = useTrainingStore.getState()
      expect(listTrainingSessions).toHaveBeenCalledWith(11, 1, 20)
      expect(s.sessions).toHaveLength(2)
      expect(s.sessionsTotal).toBe(4)
    })

    it('会员守卫 → sessionsNeedsMembership', async () => {
      const err = Object.assign(new Error('此功能需要会员'), { code: 40300 })
      listTrainingSessions.mockRejectedValue(err)
      await useTrainingStore.getState().fetchTrainingSessions(11)
      expect(useTrainingStore.getState().sessionsNeedsMembership).toBe(true)
    })

    it('completeTrainingSession 成功 → Toast 积分 + 刷新列表', async () => {
      const complete = { session_id: 1, is_completed: true, plan_progress: 50, points_earned: 5 }
      completeTrainingSession.mockResolvedValue({ data: { data: complete } })
      listTrainingSessions.mockResolvedValue({ data: { data: SESSIONS } })
      const result = await useTrainingStore.getState().completeTrainingSession(11, 1)
      expect(completeTrainingSession).toHaveBeenCalledWith(11, 1)
      expect(result).toEqual(complete)
      expect(Taro.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ icon: 'success' })
      )
      expect(listTrainingSessions).toHaveBeenLastCalledWith(11, 1, 20)
    })

    it('completeTrainingSession 失败（409/40902 已完成）→ Toast err.message', async () => {
      completeTrainingSession.mockRejectedValue(new Error('训练单已完成'))
      const result = await useTrainingStore.getState().completeTrainingSession(11, 2)
      expect(result).toBeNull()
      expect(Taro.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '训练单已完成', icon: 'none' })
      )
    })
  })

  describe('重新评估', () => {
    it('成功 → Toast + 返回结果', async () => {
      reEvaluatePlan.mockResolvedValue({ data: { data: { plan_id: 11, action: 'adjust', reason: '目标已达成' } } })
      // reEvaluatePlan 成功后联动 fetchPlanAdjustments（真实现），须给 mock 返回值
      ;(trainingApi.getPlanAdjustments as jest.Mock).mockResolvedValue({ data: { data: {} } })
      const result = await useTrainingStore.getState().reEvaluatePlan(11)
      expect(reEvaluatePlan).toHaveBeenCalledWith(11)
      expect(result).toEqual({ plan_id: 11, action: 'adjust', reason: '目标已达成' })
      expect(Taro.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ icon: 'success' })
      )
    })

    it('失败 → Toast err.message 且返回 null', async () => {
      reEvaluatePlan.mockRejectedValue(new Error('此功能需要会员'))
      const result = await useTrainingStore.getState().reEvaluatePlan(11)
      expect(result).toBeNull()
      expect(Taro.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '此功能需要会员', icon: 'none' })
      )
    })
  })
})
