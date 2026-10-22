# training_advice 模块 — 前端垂直切片设计

> **模块名称**：`training_advice`
> **前端目录**：`frontend/src/pages/training/advice/` + `frontend/src/pages/training/templates/` + `frontend/src/services/training.ts` + `frontend/src/stores/trainingStore.ts`
> **定位**：训练建议详情页（诊断+建议+训练方法+模板推荐）、训练模板列表页
> **依据**：前端需求与界面设计 v2.0 T2.6 / v1.0 P1.11、API 详细设计 v1.3 §8

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 T2.6（训练建议，引用 v1.0 P1.11）
- [ ] 阅读 v1.0 P1.11（页面结构：诊断短板 → 训练方案 → 训练方法）
- [ ] 阅读本模块的 API 契约（§8.1-8.8，8 个端点，含 §8.7 训练单列表与 §8.8 训练单完成）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：训练建议详情页 + 训练模板列表页 + training Service + trainingStore

---

## 2. API Service 模块

```typescript
// frontend/src/services/training.ts
import request from './request'

/** 诊断项 */
export interface DiagnosisItem {
  problem_id: string
  problem_name: string
  severity: string  // low/medium/high
  trend: string     // improving/stagnant/declining/achieved/new/resolved
  description: string
}

/** 建议项 */
export interface SuggestionItem {
  type: string  // progress_confirm/persistent_warning/new_issue/first_analysis
  text: string
}

/** 训练方法项 */
export interface TrainingMethodItem {
  method_id: string
  name: string
  description: string
}

/** 训练建议响应 */
export interface TrainingAdviceData {
  report_id: number
  is_first_analysis: boolean
  diagnosis: DiagnosisItem[]
  suggestions: SuggestionItem[]
  training_methods: TrainingMethodItem[]
  training_plan_template: string | null
}

/** 模板简要 */
export interface TemplateBrief {
  id: number
  template_code: string
  name: string
  problem_id: string | null
}

/** 模板详情 */
export interface TemplateDetail extends TemplateBrief {
  template_data: {
    goal?: { metric: string; target: number }
    sessions?: Array<{ name: string; reps: number }>
    exercises?: string[]
    metrics?: string[]
  }
}

/** 模板列表响应 */
export interface TemplateListData {
  total: number
  page: number
  page_size: number
  items: TemplateBrief[]
}

/** 调整记录项 */
export interface AdjustmentItem {
  id: number
  version: number
  action: string  // maintain/adjust/escalate/new_goal
  reason: string
  trigger_report_id: number | null
  created_at: string
  changes_summary: string
}

/** 方案调整历史响应 */
export interface PlanAdjustmentsData {
  plan_id: number
  current_version: number
  adjustments: AdjustmentItem[]
}

/** 重新评估响应 */
export interface ReEvaluateData {
  plan_id: number
  action: string
  reason: string
}

// R19-fix: 训练单类型（API §8.7 / §8.8，会员功能）

/** 训练单条目 */
export interface TrainingSessionItem {
  id: number  // R20-P1-1: ? API §8.7 对齐 —— session_id→id（响应字段命名统一）
  plan_id: number
  name: string
  scheduled_date: string
  is_completed: boolean
  completed_at: string | null
  exercises?: string[]
  // R21-P2-1: 补 session_index/reps 与 API §8.7 L2388-2394 对齐
  session_index: number  // 训练单序号（从1开始）
  reps: number           // 建议训练次数
}

/** 训练单列表响应 */
export interface TrainingSessionListData {
  total: number
  page: number
  page_size: number
  items: TrainingSessionItem[]
}

/** 完成训练单响应 */
export interface CompleteSessionData {
  session_id: number
  is_completed: boolean
  plan_progress: number  // 0-100
  points_earned: number
}


/**
 * 基于分析报告的训练建议。
 * @param reportId - 报告 ID
 */
export function getAdviceByReport(reportId: number) {
  return request.get(`/training/advice/${reportId}`)
}

/**
 * 综合训练建议（自动取最新报告）。
 */
export function getContextualAdvice() {
  return request.get('/training/advice/contextual')
}

/**
 * 训练方案模板列表。
 * @param problemId - 按问题筛选（可选）
 * @param page - 页码
 * @param pageSize - 每页条数
 */
export function getTemplates(
  problemId?: string,
  page: number = 1,
  pageSize: number = 20,
) {
  return request.get('/training/templates', {
    problem_id: problemId,
    page,
    page_size: pageSize,
  })
}

/**
 * 模板详情。
 * @param id - 模板 ID
 */
export function getTemplateDetail(id: number) {
  return request.get(`/training/templates/${id}`)
}

/**
 * 训练方案调整历史。
 * @param planId - 方案 ID
 */
export function getPlanAdjustments(planId: number) {
  return request.get(`/training/plans/${planId}/adjustments`)
}

/**
 * 手动触发方案重新评估（会员功能）。
 * @param planId - 方案 ID
 */
export function reEvaluatePlan(planId: number) {
  return request.post(`/training/plans/${planId}/re-evaluate`)
}

/**
 * 训练单列表（API §8.7，会员功能）。
 * 用于查看当前训练方案下的所有训练单（每日训练内容）。
 * @param planId - 方案 ID
 * @param page - 页码（默认 1）
 * @param pageSize - 每页条数（默认 20，最大 50）
 */
export function listTrainingSessions(
  planId: number,
  page: number = 1,
  pageSize: number = 20,
) {
  return request.get(`/training/plans/${planId}/sessions`, {
    page,
    page_size: pageSize,
  })
}

/**
 * 标记训练单完成（API §8.8，会员功能）。
 * 完成后返回训练单状态、方案进度与所得积分。
 * @param planId - 方案 ID
 * @param sessionId - 训练单 ID
 */
export function completeTrainingSession(planId: number, sessionId: number) {
  return request.post(`/training/plans/${planId}/sessions/${sessionId}/complete`)
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/trainingStore.ts
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

  // 模板详情
  currentTemplate: TemplateDetail | null
  templateDetailLoading: boolean

  // 方案调整历史
  adjustments: PlanAdjustmentsData | null
  adjustmentsLoading: boolean

  // 重新评估
  reEvaluating: boolean

  // R19-fix: 训练单（API §8.7 / §8.8，会员功能）
  sessions: TrainingSessionItem[]
  sessionsTotal: number
  sessionsLoading: boolean
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

  currentTemplate: null,
  templateDetailLoading: false,

  adjustments: null,
  adjustmentsLoading: false,

  reEvaluating: false,

  // R19-fix: 训练单状态初始化
  sessions: [],
  sessionsTotal: 0,
  sessionsLoading: false,
  completeSessionLoading: false,


  fetchAdviceByReport: async (reportId: number) => {
    set({ adviceLoading: true, adviceError: null })
    try {
      const res = await trainingApi.getAdviceByReport(reportId)
      set({ advice: res.data.data })
    } catch (err: any) {
      set({ adviceError: err?.message || i18next.t('training.fetchAdviceFailed') })
    } finally {
      set({ adviceLoading: false })
    }
  },

  fetchContextualAdvice: async () => {
    set({ adviceLoading: true, adviceError: null })
    try {
      const res = await trainingApi.getContextualAdvice()
      set({ advice: res.data.data })
    } catch (err: any) {
      set({ adviceError: err?.message || i18next.t('training.fetchAdviceFailed') })
    } finally {
      set({ adviceLoading: false })
    }
  },

  fetchTemplates: async (refresh: boolean = false) => {
    const { templatePage, templatePageSize, templateProblemFilter } = get()
    const page = refresh ? 1 : templatePage
    set({ templateLoading: true })
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
    set({ templateDetailLoading: true })
    try {
      const res = await trainingApi.getTemplateDetail(id)
      set({ currentTemplate: res.data.data })
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
      Taro.showToast({ title: res.data.message || i18next.t('training.planReEvaluated'), icon: 'success' })
      // 刷新调整历史
      await get().fetchPlanAdjustments(planId)
      return data
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('training.reEvaluateFailed'), icon: 'error' })
      return null
    } finally {
      set({ reEvaluating: false })
    }
  },

  // R19-fix: 拉取训练单列表（API §8.7 GET /training/plans/{plan_id}/sessions）
  fetchTrainingSessions: async (planId, page = 1, pageSize = 20) => {
    set({ sessionsLoading: true })
    try {
      const res = await trainingApi.listTrainingSessions(planId, page, pageSize)
      const data: TrainingSessionListData = res.data.data
      set({
        sessions: data.items,
        sessionsTotal: data.total,
      })
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ sessionsLoading: false })
    }
  },

  // R19-fix: 标记训练单完成（API §8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete）
  completeTrainingSession: async (planId, sessionId) => {
    set({ completeSessionLoading: true })
    try {
      const res = await trainingApi.completeTrainingSession(planId, sessionId)
      const data: CompleteSessionData = res.data.data
      Taro.showToast({
        title: i18next.t('training.sessionCompleted', { points: data.points_earned }),
        icon: 'success',
      })
      // 完成后刷新训练单列表
      await get().fetchTrainingSessions(planId)
      return data
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('training.completeFailed'), icon: 'error' })
      return null
    } finally {
      set({ completeSessionLoading: false })
    }
  },

  clearAdvice: () => {
    set({ advice: null, adviceError: null })
  },
}))
```

---

## 4. 页面组件

### 4.1 训练建议详情页

```tsx
// frontend/src/pages/training/advice/index.tsx
import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Button, Skeleton, Toast, Popup, Empty } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useTrainingStore } from '@/stores/trainingStore'
import DiagnosisSection from './components/DiagnosisSection'
import SuggestionSection from './components/SuggestionSection'
import TrainingMethodsSection from './components/TrainingMethodsSection'
import TemplateRecommendSection from './components/TemplateRecommendSection'
import './index.scss'

export default function TrainingAdvicePage() {
  const { t } = useTranslation()
  const router = useRouter()
  const store = useTrainingStore()
  const [showTemplatePopup, setShowTemplatePopup] = useState(false)

  useEffect(() => {
    const { report_id } = router.params
    if (report_id) {
      store.fetchAdviceByReport(Number(report_id))
    } else {
      store.fetchContextualAdvice()
    }
  }, [])

  const handleViewTemplate = () => {
    if (store.advice?.training_plan_template) {
      // 跳转到模板详情页
      Taro.navigateTo({
        url: `/pages/training/templates/detail/index?code=${store.advice.training_plan_template}`,
      })
    } else {
      // 跳转到模板列表页
      Taro.navigateTo({ url: '/pages/training/templates/index' })
    }
  }

  if (store.adviceLoading && !store.advice) {
    return (
      <View className="advice-page">
        <View className="advice-header">
          <Text className="page-title">{t('training.adviceTitle')}</Text>
        </View>
        {[0, 1, 2].map((i) => (
          <View className="advice-skeleton" key={i}>
            <Skeleton width="40%" height="24px" animated />
            <Skeleton width="100%" height="16px" animated />
            <Skeleton width="80%" height="16px" animated />
          </View>
        ))}
      </View>
    )
  }

  if (store.adviceError || !store.advice) {
    return (
      <View className="advice-page">
        <View className="advice-header">
          <Text className="page-title">{t('training.adviceTitle')}</Text>
        </View>
        <Empty
          description={store.adviceError || t('training.noAdvice')}
          renderBottom={
            <Button
              type="primary"
              size="small"
              onClick={() => store.fetchContextualAdvice()}
            >
              {t('common.retry')}
            </Button>
          }
        />
      </View>
    )
  }

  const { advice } = store

  return (
    <View className="advice-page">
      {/* 页面标题 */}
      <View className="advice-header">
        <Text className="page-title">{t('training.adviceTitle')}</Text>
        {advice.is_first_analysis && (
          <Text className="first-analysis-tag">
            {t('training.firstAnalysis')}
          </Text>
        )}
      </View>

      <ScrollView scrollY className="advice-scroll">
        {/* 诊断短板区域 */}
        <DiagnosisSection
          diagnosis={advice.diagnosis}
        />

        {/* 建议区域（进步确认/持续问题/新问题） */}
        <SuggestionSection
          suggestions={advice.suggestions}
        />

        {/* 训练方法区域 */}
        <TrainingMethodsSection
          methods={advice.training_methods}
        />

        {/* 训练方案模板推荐 */}
        <TemplateRecommendSection
          templateCode={advice.training_plan_template}
          onViewTemplate={handleViewTemplate}
        />

        {/* 底部操作按钮 */}
        <View className="advice-actions">
          <Button
            block
            type="primary"
            onClick={() => Taro.navigateBack()}
          >
            {t('common.back')}
          </Button>
        </View>
      </ScrollView>

      <Toast />
    </View>
  )
}
```

### 4.2 诊断短板组件

```tsx
// frontend/src/pages/training/advice/components/DiagnosisSection.tsx
import { View, Text } from '@tarojs/components'
import { Tag } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { DiagnosisItem } from '@/services/training'
import './DiagnosisSection.scss'

interface Props {
  diagnosis: DiagnosisItem[]
}

const SEVERITY_MAP = {
  low: { type: 'primary', color: 'var(--color-success)' },
  medium: { type: 'warning', color: 'var(--color-accent)' },
  high: { type: 'danger', color: 'var(--color-primary)' },
}

const TREND_MAP = {
  improving: { icon: '↑', color: 'var(--color-success)', labelKey: 'training.trendImproving' },
  stagnant: { icon: '→', color: 'var(--color-accent)', labelKey: 'training.trendStagnant' },
  declining: { icon: '↓', color: 'var(--color-primary)', labelKey: 'training.trendDeclining' },
  achieved: { icon: '✓', color: 'var(--color-success)', labelKey: 'training.trendAchieved' },
  new: { icon: '★', color: 'var(--color-accent)', labelKey: 'training.trendNew' },
  resolved: { icon: '✓', color: 'var(--color-success)', labelKey: 'training.trendResolved' },
}

export default function DiagnosisSection({ diagnosis }: Props) {
  const { t } = useTranslation()

  if (diagnosis.length === 0) {
    return (
      <View className="diagnosis-section">
        <Text className="section-title">📋 {t('training.diagnosis')}</Text>
        <View className="empty-state">
          <Text>{t('training.noDiagnosis')}</Text>
        </View>
      </View>
    )
  }

  return (
    <View className="diagnosis-section">
      <Text className="section-title">📋 {t('training.diagnosis')}</Text>
      {diagnosis.map((item, i) => {
        const severity = SEVERITY_MAP[item.severity as keyof typeof SEVERITY_MAP] || SEVERITY_MAP.medium
        const trend = TREND_MAP[item.trend as keyof typeof TREND_MAP] || TREND_MAP.new

        return (
          <View className="diagnosis-card" key={i}>
            <View className="diagnosis-header">
              <Text className="diagnosis-name">{item.problem_name}</Text>
              <Tag
                type={severity.type as any}
                style={{ background: severity.color, color: 'var(--color-text-inverse)' }}
              >
                {t(`training.severity.${item.severity}`)}
              </Tag>
            </View>
            <View className="diagnosis-trend">
              <Text className="trend-icon" style={{ color: trend.color }}>
                {trend.icon}
              </Text>
              <Text className="trend-label" style={{ color: trend.color }}>
                {t(trend.labelKey)}
              </Text>
            </View>
            <Text className="diagnosis-desc">{item.description}</Text>
          </View>
        )
      })}
    </View>
  )
}
```

### 4.3 建议区域组件

```tsx
// frontend/src/pages/training/advice/components/SuggestionSection.tsx
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import type { SuggestionItem } from '@/services/training'
import './SuggestionSection.scss'

interface Props {
  suggestions: SuggestionItem[]
}

const SUGGESTION_STYLE_MAP = {
  progress_confirm: { icon: '✅', color: 'var(--color-success)', labelKey: 'training.progressConfirm' },
  persistent_warning: { icon: '⚠️', color: 'var(--color-accent)', labelKey: 'training.persistentWarning' },
  new_issue: { icon: '🔴', color: 'var(--color-primary)', labelKey: 'training.newIssue' },
  first_analysis: { icon: 'ℹ️', color: 'var(--color-secondary)', labelKey: 'training.firstAnalysisHint' },
}

export default function SuggestionSection({ suggestions }: Props) {
  const { t } = useTranslation()

  if (suggestions.length === 0) {
    return (
      <View className="suggestion-section">
        <Text className="section-title">🏋️ {t('training.suggestions')}</Text>
        <View className="empty-state">
          <Text>{t('training.noSuggestions')}</Text>
        </View>
      </View>
    )
  }

  return (
    <View className="suggestion-section">
      <Text className="section-title">🏋️ {t('training.suggestions')}</Text>
      {suggestions.map((item, i) => {
        const style = SUGGESTION_STYLE_MAP[item.type as keyof typeof SUGGESTION_STYLE_MAP]
          || SUGGESTION_STYLE_MAP.new_issue

        return (
          <View
            className="suggestion-card"
            key={i}
            style={{ borderLeftColor: style.color }}
          >
            <View className="suggestion-header">
              <Text className="suggestion-icon">{style.icon}</Text>
              <Text className="suggestion-type" style={{ color: style.color }}>
                {t(style.labelKey)}
              </Text>
            </View>
            <Text className="suggestion-text">{item.text}</Text>
          </View>
        )
      })}
    </View>
  )
}
```

### 4.4 训练方法组件

```tsx
// frontend/src/pages/training/advice/components/TrainingMethodsSection.tsx
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import type { TrainingMethodItem } from '@/services/training'
import './TrainingMethodsSection.scss'

interface Props {
  methods: TrainingMethodItem[]
}

export default function TrainingMethodsSection({ methods }: Props) {
  const { t } = useTranslation()

  if (methods.length === 0) {
    return (
      <View className="methods-section">
        <Text className="section-title">🎯 {t('training.trainingMethods')}</Text>
        <View className="empty-state">
          <Text>{t('training.noMethods')}</Text>
        </View>
      </View>
    )
  }

  return (
    <View className="methods-section">
      <Text className="section-title">🎯 {t('training.trainingMethods')}</Text>
      {methods.map((method, i) => (
        <View className="method-card" key={i}>
          <View className="method-header">
            <Text className="method-index">{i + 1}</Text>
            <Text className="method-name">{method.name}</Text>
          </View>
          {method.description && (
            <Text className="method-desc">{method.description}</Text>
          )}
        </View>
      ))}
    </View>
  )
}
```

### 4.5 模板推荐组件

```tsx
// frontend/src/pages/training/advice/components/TemplateRecommendSection.tsx
import { View, Text } from '@tarojs/components'
import { Button } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import './TemplateRecommendSection.scss'

interface Props {
  templateCode: string | null
  onViewTemplate: () => void
}

export default function TemplateRecommendSection({ templateCode, onViewTemplate }: Props) {
  const { t } = useTranslation()

  return (
    <View className="template-recommend-section">
      <Text className="section-title">📋 {t('training.planTemplate')}</Text>
      <View className="recommend-card">
        {templateCode ? (
          <>
            <Text className="recommend-code">{templateCode}</Text>
            <Text className="recommend-desc">
              {t('training.recommendedTemplateDesc')}
            </Text>
            <Button
              type="primary"
              size="small"
              onClick={onViewTemplate}
            >
              {t('training.viewTemplateDetail')}
            </Button>
          </>
        ) : (
          <>
            <Text className="recommend-desc">
              {t('training.noRecommendedTemplate')}
            </Text>
            <Button
              plain
              type="primary"
              size="small"
              onClick={onViewTemplate}
            >
              {t('training.browseTemplates')}
            </Button>
          </>
        )}
      </View>
    </View>
  )
}
```

### 4.6 训练模板列表页

```tsx
// frontend/src/pages/training/templates/index.tsx
import { useEffect, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Cell, Empty, Skeleton, PullRefresh } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useTrainingStore } from '@/stores/trainingStore'
import './index.scss'

export default function TemplateListPage() {
  const { t } = useTranslation()
  const store = useTrainingStore()

  useEffect(() => {
    store.fetchTemplates(true)
  }, [])

  const handleRefresh = useCallback(async () => {
    await store.fetchTemplates(true)
  }, [store])

  const handleItemClick = (id: number) => {
    Taro.navigateTo({ url: `/pages/training/templates/detail/index?id=${id}` })
  }

  const handleLoadMore = useCallback(() => {
    store.loadMoreTemplates()
  }, [store])

  return (
    <View className="template-list-page">
      <View className="template-header">
        <Text className="page-title">{t('training.templateList')}</Text>
      </View>

      <PullRefresh onRefresh={handleRefresh}>
        <ScrollView scrollY className="template-scroll">
          {store.templateLoading && store.templates.length === 0 ? (
            <View className="template-skeleton-list">
              {[0, 1, 2, 3].map((i) => (
                <View className="template-skeleton-item" key={i}>
                  <Skeleton width="60%" height="20px" animated />
                  <Skeleton width="40%" height="14px" animated />
                </View>
              ))}
            </View>
          ) : store.templates.length === 0 ? (
            <Empty description={t('training.noTemplates')} />
          ) : (
            <View className="template-list">
              {store.templates.map((item) => (
                <Cell
                  key={item.id}
                  className="template-item"
                  onClick={() => handleItemClick(item.id)}
                >
                  <View className="template-card">
                    <Text className="template-name">{item.name}</Text>
                    <Text className="template-code">{item.template_code}</Text>
                    {item.problem_id && (
                      <Text className="template-problem">
                        {t('training.problem')}: {item.problem_id}
                      </Text>
                    )}
                  </View>
                </Cell>
              ))}

              {store.templateHasMore && (
                <View className="load-more" onClick={handleLoadMore}>
                  <Text>
                    {store.templateLoading
                      ? t('common.loading')
                      : t('common.loadMore')}
                  </Text>
                </View>
              )}
            </View>
          )}
        </ScrollView>
      </PullRefresh>
    </View>
  )
}
```

### 4.7 模板详情页

```tsx
// frontend/src/pages/training/templates/detail.tsx
import { useEffect } from 'react'
import { useRouter } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Skeleton, Empty, Button } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useTrainingStore } from '@/stores/trainingStore'
import './detail.scss'

export default function TemplateDetailPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const store = useTrainingStore()

  useEffect(() => {
    const { id } = router.params
    if (id) {
      store.fetchTemplateDetail(Number(id))
    }
  }, [])

  const tmpl = store.currentTemplate

  if (store.templateDetailLoading && !tmpl) {
    return (
      <View className="template-detail-page">
        <View className="detail-header">
          <Text className="page-title">{t('training.templateDetail')}</Text>
        </View>
        <View className="detail-skeleton">
          <Skeleton width="50%" height="24px" animated />
          <Skeleton width="100%" height="60px" animated />
          <Skeleton width="100%" height="60px" animated />
        </View>
      </View>
    )
  }

  if (!tmpl) {
    return (
      <View className="template-detail-page">
        <View className="detail-header">
          <Text className="page-title">{t('training.templateDetail')}</Text>
        </View>
        <Empty description={t('training.templateNotFound')} />
      </View>
    )
  }

  const data = tmpl.template_data

  return (
    <View className="template-detail-page">
      <View className="detail-header">
        <Text className="page-title">{tmpl.name}</Text>
        <Text className="template-code-label">{tmpl.template_code}</Text>
      </View>

      <ScrollView scrollY className="detail-scroll">
        {/* 目标 */}
        {data.goal && (
          <View className="detail-section">
            <Text className="section-title">🎯 {t('training.goal')}</Text>
            <View className="goal-card">
              <Text className="goal-metric">{data.goal.metric}</Text>
              <Text className="goal-target">
                {t('training.targetValue')}: {data.goal.target}
              </Text>
            </View>
          </View>
        )}

        {/* 训练内容 */}
        {data.sessions && data.sessions.length > 0 && (
          <View className="detail-section">
            <Text className="section-title">📋 {t('training.sessions')}</Text>
            {data.sessions.map((session, i) => (
              <View className="session-card" key={i}>
                <Text className="session-name">{i + 1}. {session.name}</Text>
                <Text className="session-reps">
                  {t('training.reps')}: {session.reps}
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* 练习项目 */}
        {data.exercises && data.exercises.length > 0 && (
          <View className="detail-section">
            <Text className="section-title">🏓 {t('training.exercises')}</Text>
            {data.exercises.map((exercise, i) => (
              <View className="exercise-item" key={i}>
                <Text className="exercise-dot">•</Text>
                <Text className="exercise-text">{exercise}</Text>
              </View>
            ))}
          </View>
        )}

        {/* 检验指标 */}
        {data.metrics && data.metrics.length > 0 && (
          <View className="detail-section">
            <Text className="section-title">📊 {t('training.metrics')}</Text>
            <View className="metrics-list">
              {data.metrics.map((metric, i) => (
                <View className="metric-tag" key={i}>
                  <Text>{metric}</Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  )
}
```

---
## 4.8 训练方案详情页（R20-P2-1 新增训练单 UI + 标记完成）

> **职责**：调用 trainingStore 的 `fetchTrainingSessions` / `completeTrainingSession` actions 渲染训练单列表，支持"标记完成"操作并触发积分提示。从训练方案列表或 Tab 跳转。

```tsx
// frontend/src/pages/training/plans/[plan_id]/index.tsx
// R20-P2-1: 训练方案详情页 UI 组件（R21-P2-2: 修复 UTF-8 编码乱码）
import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Cell, Button, Skeleton, Toast, Empty, Tag, Progress } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useTrainingStore } from '@/stores/trainingStore'
import './index.scss'

export default function TrainingPlanDetailPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const store = useTrainingStore()
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const planId = Number(router.params.plan_id || 0)

  // R20-P2-1: 拉取训练单列表，调用 API §8.7 GET /training/plans/{plan_id}/sessions
  useEffect(() => {
    if (planId) {
      store.fetchTrainingSessions(planId)
    }
  }, [planId])

  // R20-P2-1: 标记完成训练单，调用 API §8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete
  const handleCompleteSession = async (sessionId: number) => {
    const result = await store.completeTrainingSession(planId, sessionId)
    if (result) {
      // 触发完成提示
      setToastMsg(t('training.sessionCompleted', { points: result.points_earned }))
      setToastVisible(true)
    }
  }

  // Loading 状态
  if (store.sessionsLoading && store.sessions.length === 0) {
    return (
      <View className="plan-detail-page">
        <View className="plan-header">
          <Text className="page-title">{t('training.planDetail')}</Text>
        </View>
        <View className="plan-skeleton">
          {[0, 1, 2, 3].map((i) => (
            <View className="skeleton-item" key={i}>
              <Skeleton width="60%" height="20px" animated />
              <Skeleton width="40%" height="14px" animated />
            </View>
          ))}
        </View>
      </View>
    )
  }

  // 空状态
  if (store.sessions.length === 0) {
    return (
      <View className="plan-detail-page">
        <View className="plan-header">
          <Text className="page-title">{t('training.planDetail')}</Text>
        </View>
        <Empty description={t('training.noSessions')} />
      </View>
    )
  }

  // R20-P2-1: 计算已完成训练单数 / 总数
  const completedCount = store.sessions.filter((s) => s.is_completed).length
  const totalCount = store.sessionsTotal || store.sessions.length
  const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0

  return (
    <View className="plan-detail-page">
      {/* 头部区域 */}
      <View className="plan-header">
        <Text className="page-title">{t('training.planDetail')}</Text>
        <View className="plan-progress">
          <Progress percent={progressPercent} />
          <Text className="progress-text">
            {completedCount} / {totalCount}  // R20-P2-1: is_completed 计数
          </Text>
        </View>
      </View>

      <ScrollView scrollY className="sessions-scroll">
        {store.sessions.map((session) => (
          <Cell
            key={session.id}  // R20-P2-1: API §8.7 返回 id，命名 session_id
            className="session-item"
          >
            <View className="session-card">
              <View className="session-header">
                {/* R21-P2-1: 显示 session_index（训练单序号） */}
                <Text className="session-index">#{session.session_index}</Text>
                <Text className="session-name">{session.name}</Text>
                {session.is_completed ? (
                  <Tag type="success">{t('training.completed')}</Tag>
                ) : (
                  <Tag type="primary">{t('training.pending')}</Tag>
                )}
              </View>
              <View className="session-info">
                <Text className="session-date">
                  {t('training.scheduledDate')}: {session.scheduled_date || '-'}
                </Text>
                {/* R21-P2-1: 显示 reps（建议训练次数） */}
                <Text className="session-reps">
                  {t('training.reps')}: {session.reps}
                </Text>
                {session.completed_at && (
                  <Text className="session-completed-at">
                    {t('training.completedAt')}: {session.completed_at}
                  </Text>
                )}
              </View>
              {session.exercises && session.exercises.length > 0 && (
                <View className="session-exercises">
                  {session.exercises.map((exercise, i) => (
                    <Text key={i} className="exercise-text">· {exercise}</Text>
                  ))}
                </View>
              )}
              {/* R20-P2-1: 未完成训练单可点击调用 completeTrainingSession action */}
              {!session.is_completed && (
                <Button
                  type="primary"
                  size="small"
                  loading={store.completeSessionLoading}
                  onClick={() => handleCompleteSession(session.id)}
                  className="btn-complete"
                >
                  {t('training.markComplete')}
                </Button>
              )}
            </View>
          </Cell>
        ))}
      </ScrollView>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

```scss
// frontend/src/pages/training/plans/[plan_id]/index.scss
.plan-detail-page {
  min-height: 100vh;
  background: var(--color-background);
}

.plan-header {
  padding: var(--spacing-md);
  background: var(--color-card);
  border-bottom: 1px solid var(--color-divider);

  .page-title {
    display: block;
    font-size: 18px;
    font-weight: bold;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm);
  }

  .plan-progress {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);

    .progress-text {
      font-size: 12px;
      color: var(--color-text-secondary);
    }
  }
}

.sessions-scroll {
  height: calc(100vh - 140px);
  padding: 0 var(--spacing-md);
}

.session-item {
  margin-bottom: var(--spacing-sm);
  border-radius: var(--radius-md) !important;

  .session-card {
    .session-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      .session-index {  // R21-P2-1: session_index 样式
        font-size: var(--fs-small); /* 13px, R22-P2-1: 字号对齐规范集 */
        font-weight: bold;
        color: var(--color-primary);
        margin-right: var(--spacing-xs);
      }

      .session-name {
        font-size: 15px;
        font-weight: 500;
        color: var(--color-text-primary);
      }
    }

    .session-info {
      margin-top: var(--spacing-xs);

      .session-date, .session-completed-at, .session-reps {  // R21-P2-1: 新增 session-reps
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
      }

      .session-reps {  // R21-P2-1: reps 样式
        color: var(--color-primary);
        font-weight: 500;
      }
    }

    .session-exercises {
      margin-top: var(--spacing-sm);
      .exercise-text {
        display: block;
        font-size: 13px;
        color: var(--color-text-primary);
        margin-top: var(--spacing-xs);
      }
    }

    .btn-complete {
      margin-top: var(--spacing-sm);
    }
  }
}

.plan-skeleton {
  padding: 0 var(--spacing-md);

  .skeleton-item {
    margin-top: var(--spacing-sm);
  }
}
```

> **i18n 新增条目**：
> - zh-CN: `training.planDetail` = "训练方案详情"
> - zh-CN: `training.noSessions` = "暂无训练单"
> - zh-CN: `training.completed` = "已完成"
> - zh-CN: `training.pending` = "待完成"
> - zh-CN: `training.scheduledDate` = "计划日期"
> - zh-CN: `training.completedAt` = "完成时间"
> - zh-CN: `training.markComplete` = "标记完成"
> - zh-CN: `training.sessionCompleted` = "训练单已完成，获得 {{points}} 积分"



## 5. 样式（SCSS + CSS 变量）

```scss
// frontend/src/pages/training/advice/index.scss

// CSS 变量已在全局 app.scss 中定义，模块级不重复定义。
// 全局 :root 变量清单见总览 §3.2「前端通用约定 — 全局 CSS 变量」。

.advice-page {
  min-height: 100vh;
  background: var(--color-background);
}

.advice-header {
  padding: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);

  .page-title {
    font-size: 18px;
    font-weight: bold;
    color: var(--color-text-primary);
  }

  .first-analysis-tag {
    background: color-mix(in srgb, var(--color-secondary) 10%, transparent);
    color: var(--color-secondary);
    font-size: 12px;
    padding: var(--spacing-xs) var(--spacing-sm);
    border-radius: var(--radius-md);
  }
}

.advice-scroll {
  height: calc(100vh - 56px);
  padding-bottom: var(--spacing-lg);
}

.section-title {
  display: block;
  font-size: 15px;
  font-weight: bold;
  color: var(--color-text-primary);
  padding: var(--spacing-md) var(--spacing-md) var(--spacing-sm);
}

// 诊断卡片
.diagnosis-section {
  .diagnosis-card {
    margin: 0 var(--spacing-md) var(--spacing-sm);
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);

    .diagnosis-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      .diagnosis-name {
        font-size: 15px;
        font-weight: 500;
        color: var(--color-text-primary);
      }
    }

    .diagnosis-trend {
      display: flex;
      align-items: center;
      gap: var(--spacing-xs);
      margin-top: var(--spacing-sm);

      .trend-icon {
        font-size: 15px;
        font-weight: bold;
      }

      .trend-label {
        font-size: 13px;
      }
    }

    .diagnosis-desc {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-sm);
      line-height: 1.5;
    }
  }
}

// 建议卡片
.suggestion-section {
  .suggestion-card {
    margin: 0 var(--spacing-md) var(--spacing-sm);
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    border-left: 3px solid transparent;
    box-shadow: var(--shadow-card);

    .suggestion-header {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);

      .suggestion-icon {
        font-size: 15px;
      }

      .suggestion-type {
        font-size: 12px;
        font-weight: 500;
      }
    }

    .suggestion-text {
      display: block;
      font-size: 13px;
      color: var(--color-text-primary);
      margin-top: var(--spacing-sm);
      line-height: 1.6;
    }
  }
}

// 训练方法
.methods-section {
  .method-card {
    margin: 0 var(--spacing-md) var(--spacing-sm);
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    box-shadow: var(--shadow-card);

    .method-header {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);

      .method-index {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: var(--color-primary);
        color: var(--color-text-inverse);
        font-size: 12px;
        text-align: center;
        line-height: 24px;
        flex-shrink: 0;
      }

      .method-name {
        font-size: 15px;
        font-weight: 500;
        color: var(--color-text-primary);
      }
    }

    .method-desc {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-sm);
      padding-left: var(--spacing-xl);
      line-height: 1.5;
    }
  }
}

// 模板推荐
.template-recommend-section {
  .recommend-card {
    margin: 0 var(--spacing-md) var(--spacing-md);
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md);
    text-align: center;
    box-shadow: var(--shadow-card);

    .recommend-code {
      display: block;
      font-size: 15px;
      font-weight: bold;
      color: var(--color-primary);
      margin-bottom: var(--spacing-sm);
    }

    .recommend-desc {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-bottom: var(--spacing-md);
    }
  }
}

.advice-actions {
  padding: var(--spacing-md) var(--spacing-lg);
}

.advice-skeleton {
  margin: 0 var(--spacing-md) var(--spacing-sm);
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
}

// 模板列表页
.template-list-page {
  min-height: 100vh;
  background: var(--color-background);

  .template-header {
    padding: var(--spacing-md);

    .page-title {
      font-size: 18px;
      font-weight: bold;
      color: var(--color-text-primary);
    }
  }

  .template-scroll {
    height: calc(100vh - 56px);
  }

  .template-list {
    padding: 0 var(--spacing-md);
  }

  .template-item {
    margin-bottom: var(--spacing-sm);
    border-radius: var(--radius-md) !important;

    .template-card {
      .template-name {
        display: block;
        font-size: 15px;
        font-weight: 500;
        color: var(--color-text-primary);
      }

      .template-code {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
        margin-top: var(--spacing-xs);
      }

      .template-problem {
        display: block;
        font-size: 12px;
        color: var(--color-success);
        margin-top: var(--spacing-xs);
      }
    }
  }

  .load-more {
    text-align: center;
    padding: var(--spacing-md);
    color: var(--color-text-secondary);
    font-size: 13px;
  }
}

// 模板详情页
.template-detail-page {
  min-height: 100vh;
  background: var(--color-background);

  .detail-header {
    padding: var(--spacing-md);
    background: var(--color-card);
    border-bottom: 1px solid var(--color-divider);

    .page-title {
      display: block;
      font-size: 18px;
      font-weight: bold;
      color: var(--color-text-primary);
    }

    .template-code-label {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-xs);
    }
  }

  .detail-scroll {
    height: calc(100vh - 100px);
  }

  .detail-section {
    padding: 0 var(--spacing-md) var(--spacing-md);

    .goal-card {
      background: var(--color-card);
      border-radius: var(--radius-md);
      padding: var(--spacing-md);
      box-shadow: var(--shadow-card);

      .goal-metric {
        display: block;
        font-size: 15px;
        font-weight: 500;
        color: var(--color-text-primary);
      }

      .goal-target {
        display: block;
        font-size: 13px;
        color: var(--color-primary);
        margin-top: var(--spacing-xs);
      }
    }

    .session-card {
      background: var(--color-card);
      border-radius: var(--radius-md);
      padding: var(--spacing-md);
      margin-bottom: var(--spacing-sm);
      box-shadow: var(--shadow-card);

      .session-name {
        display: block;
        font-size: 13px;
        color: var(--color-text-primary);
      }

      .session-reps {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
        margin-top: var(--spacing-xs);
      }
    }

    .exercise-item {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
      background: var(--color-card);
      border-radius: var(--radius-sm);
      padding: var(--spacing-sm) var(--spacing-md);
      margin-bottom: var(--spacing-xs);

      .exercise-dot {
        color: var(--color-primary);
        font-size: 15px;
      }

      .exercise-text {
        font-size: 13px;
        color: var(--color-text-primary);
      }
    }

    .metrics-list {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-sm);

      .metric-tag {
        background: color-mix(in srgb, var(--color-success) 10%, transparent);
        color: var(--color-success);
        font-size: 12px;
        padding: var(--spacing-xs) var(--spacing-sm-md);
        border-radius: var(--radius-md);
      }
    }
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 training 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    'pages/dashboard/index',
    // ... 其他已有页面
    'pages/training/advice/index',       // 新增：训练建议详情页
    'pages/training/templates/index',    // 新增：训练模板列表页
    'pages/training/templates/detail/index',   // 新增：训练模板详情页
    'pages/training/plans/[plan_id]/index',  // R20-P2-1: 新增：训练方案详情页（含训练单列表 + 完成按钮）
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

> **入口说明**：
> - 训练建议详情页从分析报告详情页进入（报告 → 查看训练建议 → `/pages/training/advice/index?report_id={id}`）
> - 也可从首页训练提醒卡片进入（`/pages/training/advice/index` 自动取最新报告）
> - 训练模板列表页从训练建议页"浏览模板"按钮进入，或从训练 Tab 入口进入

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
// R21-P2-3: 补 8 个 i18n key 双语翻译（planDetail/noSessions/completed/pending/scheduledDate/completedAt/markComplete/sessionCompleted）
{
  "training": {
    "adviceTitle": "训练建议",
    "firstAnalysis": "首次分析",
    "firstAnalysisHint": "首次分析提示",
    "diagnosis": "诊断",
    "noDiagnosis": "暂无诊断数据",
    "suggestions": "建议",
    "noSuggestions": "暂无建议",
    "progressConfirm": "进步确认",
    "persistentWarning": "持续问题",
    "newIssue": "新发现问题",
    "trainingMethods": "训练方法",
    "noMethods": "暂无训练方法",
    "planTemplate": "训练方案模板",
    "recommendedTemplateDesc": "基于诊断结果推荐的训练方案模板",
    "viewTemplateDetail": "查看模板详情",
    "noRecommendedTemplate": "暂无推荐模板",
    "browseTemplates": "浏览模板列表",
    "noAdvice": "暂无训练建议，请先上传视频分析",
    "templateList": "训练模板",
    "noTemplates": "暂无训练模板",
    "templateDetail": "模板详情",
    "templateNotFound": "模板不存在",
    "problem": "关联问题",
    "goal": "训练目标",
    "targetValue": "目标值",
    "sessions": "训练内容",
    "reps": "次数",
    "exercises": "练习项目",
    "metrics": "检验指标",
    "severity": {
      "low": "轻微",
      "medium": "中等",
      "high": "严重"
    },
    "trendImproving": "改善中",
    "trendStagnant": "停滞",
    "trendDeclining": "退步",
    "trendAchieved": "已达标",
    "trendNew": "新发现",
    "trendResolved": "已解决",
    "fetchAdviceFailed": "获取训练建议失败",
    "planReEvaluated": "方案已重新评估",
    "reEvaluateFailed": "重新评估失败",
    "planDetail": "训练方案详情",
    "noSessions": "暂无训练单",
    "completed": "已完成",
    "pending": "待完成",
    "scheduledDate": "计划日期",
    "completedAt": "完成时间",
    "markComplete": "标记完成",
    "sessionCompleted": "训练单已完成，获得 {{points}} 积分"  // R22-P2-2: 补 {{points}} 插值占位符
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
// R21-P2-3: 补 8 个 i18n key 双语翻译（planDetail/noSessions/completed/pending/scheduledDate/completedAt/markComplete/sessionCompleted）
{
  "training": {
    "adviceTitle": "Training Advice",
    "firstAnalysis": "First Analysis",
    "firstAnalysisHint": "First Analysis",
    "diagnosis": "Diagnosis",
    "noDiagnosis": "No diagnosis data",
    "suggestions": "Suggestions",
    "noSuggestions": "No suggestions",
    "progressConfirm": "Progress Confirmed",
    "persistentWarning": "Persistent Issue",
    "newIssue": "New Issue",
    "trainingMethods": "Training Methods",
    "noMethods": "No training methods",
    "planTemplate": "Training Plan Template",
    "recommendedTemplateDesc": "Recommended template based on diagnosis",
    "viewTemplateDetail": "View Template Detail",
    "noRecommendedTemplate": "No recommended template",
    "browseTemplates": "Browse Templates",
    "noAdvice": "No advice yet, please upload a video for analysis",
    "templateList": "Training Templates",
    "noTemplates": "No templates available",
    "templateDetail": "Template Detail",
    "templateNotFound": "Template not found",
    "problem": "Problem",
    "goal": "Goal",
    "targetValue": "Target",
    "sessions": "Sessions",
    "reps": "Reps",
    "exercises": "Exercises",
    "metrics": "Metrics",
    "severity": {
      "low": "Low",
      "medium": "Medium",
      "high": "High"
    },
    "trendImproving": "Improving",
    "trendStagnant": "Stagnant",
    "trendDeclining": "Declining",
    "trendAchieved": "Achieved",
    "trendNew": "New",
    "trendResolved": "Resolved",
    "fetchAdviceFailed": "Failed to get training advice",
    "planReEvaluated": "Plan re-evaluated",
    "reEvaluateFailed": "Re-evaluation failed",
    "planDetail": "Training Plan Detail",
    "noSessions": "No training sessions",
    "completed": "Completed",
    "pending": "Pending",
    "scheduledDate": "Scheduled Date",
    "completedAt": "Completed At",
    "markComplete": "Mark Complete",
    "sessionCompleted": "Session completed, earned {{points}} points"  // R22-P2-2: 补 {{points}} 插值占位符
  }
}
```

### 常量定义

```typescript
// frontend/src/constants/training.ts

/** 严重程度映射 */
export const SEVERITY_MAP = {
  low: { type: 'primary', color: 'var(--color-success)', labelKey: 'training.severity.low' },
  medium: { type: 'warning', color: 'var(--color-accent)', labelKey: 'training.severity.medium' },
  high: { type: 'danger', color: 'var(--color-primary)', labelKey: 'training.severity.high' },
} as const

/** 趋势映射 */
export const TREND_MAP = {
  improving: { icon: '↑', color: 'var(--color-success)', labelKey: 'training.trendImproving' },
  stagnant: { icon: '→', color: 'var(--color-accent)', labelKey: 'training.trendStagnant' },
  declining: { icon: '↓', color: 'var(--color-primary)', labelKey: 'training.trendDeclining' },
  achieved: { icon: '✓', color: 'var(--color-success)', labelKey: 'training.trendAchieved' },
  new: { icon: '★', color: 'var(--color-accent)', labelKey: 'training.trendNew' },
  resolved: { icon: '✓', color: 'var(--color-success)', labelKey: 'training.trendResolved' },
} as const

/** 建议类型映射 */
export const SUGGESTION_TYPE_MAP = {
  progress_confirm: { icon: '✅', color: 'var(--color-success)', labelKey: 'training.progressConfirm' },
  persistent_warning: { icon: '⚠️', color: 'var(--color-accent)', labelKey: 'training.persistentWarning' },
  new_issue: { icon: '🔴', color: 'var(--color-primary)', labelKey: 'training.newIssue' },
  first_analysis: { icon: 'ℹ️', color: 'var(--color-secondary)', labelKey: 'training.firstAnalysisHint' },
} as const

/** 方案调整动作映射 */
export const ADJUSTMENT_ACTION_MAP = {
  maintain: { color: 'var(--color-success)', labelKey: 'training.trendImproving' },
  adjust: { color: 'var(--color-accent)', labelKey: 'training.trendStagnant' },
  escalate: { color: 'var(--color-primary)', labelKey: 'training.trendDeclining' },
  new_goal: { color: 'var(--color-secondary)', labelKey: 'training.trendAchieved' },
} as const
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 训练建议详情页布局：标题 + 首次分析标签 + 诊断 + 建议 + 方法 + 模板推荐
- [ ] 诊断卡片显示问题名 + 严重程度 Tag + 趋势图标 + 描述
- [ ] 严重程度颜色正确（低=绿色 / 中=橙色 / 高=红色）
- [ ] 建议卡片左边框颜色与类型匹配（进步=绿 / 持续=橙 / 新问题=红 / 首次=深蓝）
- [ ] 训练方法列表有序号编号，主色背景圆形序号
- [ ] 模板推荐区域有推荐模板编码或无推荐时显示浏览入口
- [ ] 模板列表页支持下拉刷新 + 上拉加载
- [ ] 模板详情页分区展示（目标 / 内容 / 练习 / 指标）
- [ ] 空状态正确显示引导文字
- [ ] 加载中显示 Skeleton 占位

### 功能验证
- [ ] 从分析报告进入训练建议（携带 report_id）
- [ ] 从首页训练提醒进入训练建议（自动取最新报告）
- [ ] 首次分析显示"首次分析"标签和提示
- [ ] 诊断项的 trend 字段正确显示趋势图标
- [ ] 建议项按类型显示不同样式
- [ ] 点击"查看模板详情"跳转到模板详情页
- [ ] 点击"浏览模板列表"跳转到模板列表页
- [ ] 模板列表上拉加载更多
- [ ] 模板详情正确展示 template_data 结构
- [ ] 网络错误显示重试按钮

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 颜色使用 CSS 变量或常量映射，**禁止** 硬编码颜色值
- **禁止** 使用 class 组件
- **禁止** 安装新的 npm 包
- **必须** 训练建议详情页显示诊断趋势（improving/stagnant/declining 等）
- **必须** 首次分析显示标签和提示
- **必须** 模板列表页支持下拉刷新 + 上拉加载
