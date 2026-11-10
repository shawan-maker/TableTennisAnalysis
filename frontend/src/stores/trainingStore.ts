/**
 * training_advice 状态管理（07-training_advice/frontend.md §3）
 * 训练建议 + 模板列表（分页）+ 模板详情 + 方案调整 + 训练单（完成→积分）
 *
 * FS5 会员守卫：后端 training 6 端点 require_membership（403 + code 40300），
 * fetch 侧捕获后置 needsMembership 标志，页面渲染升级引导而非错误文案。
 */
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import i18next from 'i18next'
import * as trainingApi from '@/services/training'
import type {
  TrainingAdviceData,
  TemplateBrief,
  TemplateDetail,
  TemplateListData,
  PlanAdjustmentsData,
  ReEvaluateData,
  TrainingSessionItem,
  TrainingSessionListData,
  CompleteSessionData,
} from '@/services/training'

/** 后端 ERR_FORBIDDEN（app/core/exceptions.py：403 + 40300 = 此功能需要会员） */
export const MEMBERSHIP_ERROR_CODE = 40300

/** 判定请求错误是否为会员守卫拦截 */
export function isMembershipError(err: unknown): boolean {
  return (err as { code?: number })?.code === MEMBERSHIP_ERROR_CODE
}

interface TrainingState {
  // 训练建议
  advice: TrainingAdviceData | null
  adviceLoading: boolean
  adviceError: string | null

  // 模板列表
  templates: TemplateBrief[]
  templateTotal: number
  templatePage: number
  templatePageSize: number
  templateProblemFilter: string | null
  templateLoading: boolean
  templateHasMore: boolean
  templateError: string | null
  templateNeedsMembership: boolean

  // 模板详情
  currentTemplate: TemplateDetail | null
  templateDetailLoading: boolean
  templateDetailError: string | null
  templateDetailNeedsMembership: boolean

  // 方案调整历史
  adjustments: PlanAdjustmentsData | null
  adjustmentsLoading: boolean

  // 重新评估
  reEvaluating: boolean

  // 训练单
  sessions: TrainingSessionItem[]
  sessionsTotal: number
  sessionsLoading: boolean
  sessionsError: string | null
  sessionsNeedsMembership: boolean
  completeSessionLoading: boolean

  // Actions
  fetchAdviceByReport: (reportId: number) => Promise<void>
  fetchContextualAdvice: () => Promise<void>
  fetchTemplates: (refresh?: boolean) => Promise<void>
  setTemplateFilter: (problemId: string | null) => void
  loadMoreTemplates: () => Promise<void>
  fetchTemplateDetail: (id: number) => Promise<void>
  fetchPlanAdjustments: (planId: number) => Promise<void>
  reEvaluatePlan: (planId: number) => Promise<ReEvaluateData | null>
  fetchTrainingSessions: (planId: number, page?: number, pageSize?: number) => Promise<void>
  completeTrainingSession: (planId: number, sessionId: number) => Promise<CompleteSessionData | null>
  clearAdvice: () => void
}

export const useTrainingStore = create<TrainingState>((set, get) => ({
  advice: null,
  adviceLoading: false,
  adviceError: null,

  templates: [],
  templateTotal: 0,
  templatePage: 1,
  templatePageSize: 20,
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

  fetchAdviceByReport: async (reportId: number) => {
    set({ adviceLoading: true, adviceError: null, advice: null })
    try {
      const res = await trainingApi.getAdviceByReport(reportId)
      set({ advice: res.data.data })
    } catch (err: any) {
      set({ adviceError: err?.message || 'Failed to fetch advice' })
    } finally {
      set({ adviceLoading: false })
    }
  },

  fetchContextualAdvice: async () => {
    set({ adviceLoading: true, adviceError: null, advice: null })
    try {
      const res = await trainingApi.getContextualAdvice()
      set({ advice: res.data.data })
    } catch (err: any) {
      set({ adviceError: err?.message || 'Failed to fetch advice' })
    } finally {
      set({ adviceLoading: false })
    }
  },

  fetchTemplates: async (refresh: boolean = false) => {
    const { templatePage, templatePageSize, templateProblemFilter } = get()
    const page = refresh ? 1 : templatePage
    set({ templateLoading: true, templateError: null, templateNeedsMembership: false })
    try {
      const res = await trainingApi.getTemplates(
        templateProblemFilter ?? undefined,
        page,
        templatePageSize,
      )
      const data: TemplateListData = res.data.data
      set((state) => ({
        templates: refresh ? data.items : [...state.templates, ...data.items],
        templateTotal: data.total,
        templatePage: page,
        templateHasMore: page * templatePageSize < data.total,
      }))
    } catch (err: any) {
      if (isMembershipError(err)) {
        set({ templateNeedsMembership: true, templates: [], templateTotal: 0 })
      } else {
        set({ templateError: err?.message || 'Operation failed' })
      }
    } finally {
      set({ templateLoading: false })
    }
  },

  setTemplateFilter: (problemId: string | null) => {
    set({ templateProblemFilter: problemId })
    get().fetchTemplates(true)
  },

  loadMoreTemplates: async () => {
    const { templatePage, templateHasMore, templateLoading } = get()
    if (!templateHasMore || templateLoading) return
    set({ templatePage: templatePage + 1 })
    await get().fetchTemplates(false)
  },

  fetchTemplateDetail: async (id: number) => {
    set({
      templateDetailLoading: true,
      templateDetailError: null,
      templateDetailNeedsMembership: false,
      currentTemplate: null,
    })
    try {
      const res = await trainingApi.getTemplateDetail(id)
      set({ currentTemplate: res.data.data })
    } catch (err: any) {
      if (isMembershipError(err)) {
        set({ templateDetailNeedsMembership: true })
      } else {
        set({ templateDetailError: err?.message || 'Template not found' })
      }
    } finally {
      set({ templateDetailLoading: false })
    }
  },

  fetchPlanAdjustments: async (planId: number) => {
    set({ adjustmentsLoading: true })
    try {
      const res = await trainingApi.getPlanAdjustments(planId)
      set({ adjustments: res.data.data })
    } finally {
      set({ adjustmentsLoading: false })
    }
  },

  reEvaluatePlan: async (planId: number) => {
    set({ reEvaluating: true })
    try {
      const res = await trainingApi.reEvaluatePlan(planId)
      const data: ReEvaluateData = res.data.data
      Taro.showToast({ title: res.data.message || 'Plan re-evaluated', icon: 'success' })
      // 刷新调整历史
      await get().fetchPlanAdjustments(planId)
      return data
    } catch (err: any) {
      Taro.showToast({
        title: err?.message || 'Re-evaluation failed',
        icon: 'none',
      })
      return null
    } finally {
      set({ reEvaluating: false })
    }
  },

  // API §8.7 GET /training/plans/{plan_id}/sessions
  fetchTrainingSessions: async (planId, page = 1, pageSize = 20) => {
    set({ sessionsLoading: true, sessionsError: null, sessionsNeedsMembership: false })
    try {
      const res = await trainingApi.listTrainingSessions(planId, page, pageSize)
      const data: TrainingSessionListData = res.data.data
      set({
        sessions: data.items,
        sessionsTotal: data.total,
      })
    } catch (err: any) {
      if (isMembershipError(err)) {
        set({ sessionsNeedsMembership: true, sessions: [], sessionsTotal: 0 })
      } else {
        set({ sessionsError: err?.message || 'Operation failed' })
      }
    } finally {
      set({ sessionsLoading: false })
    }
  },

  // API §8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete
  completeTrainingSession: async (planId, sessionId) => {
    set({ completeSessionLoading: true })
    try {
      const res = await trainingApi.completeTrainingSession(planId, sessionId)
      const data: CompleteSessionData = res.data.data
      // FS8-5：修复硬编码英文 Toast——training.sessionCompleted key（zh/en）此前已定义未使用
      Taro.showToast({
        title: i18next.t('training.sessionCompleted', { points: data.points_earned }),
        icon: 'success',
      })
      // 完成后刷新训练单列表
      await get().fetchTrainingSessions(planId)
      return data
    } catch (err: any) {
      Taro.showToast({ title: err?.message || 'Operation failed', icon: 'none' })
      return null
    } finally {
      set({ completeSessionLoading: false })
    }
  },

  clearAdvice: () => {
    set({ advice: null, adviceError: null })
  },
}))
