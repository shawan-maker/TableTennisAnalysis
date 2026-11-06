/**
 * training_advice 模块 API Service（07-training_advice/frontend.md §2）
 * 端点与后端 app/api/v1/training/router.py 逐字一致（8 个）。
 *
 * FS5-P3 契约同步（与设计文档 §2 接口定义的差异，以后端为准）：
 * - TemplateDetail 补 created_at（后端 get_template_detail 返回该字段）
 * - TrainingSessionListData 顶层含 plan_id（后端 list_training_sessions 返回）
 * - CompleteSessionData 补 completed_at（后端 complete_training_session 返回）
 * - 模板详情页同时支持 id / code 查询（设计样例 advice 页跳 ?code= 而详情页读 id，
 *   两处样例自相矛盾；detail 页兼容双参）
 */
import request from './request'

/** 诊断项 */
export interface DiagnosisItem {
  problem_id: string
  problem_name: string
  severity: string // low/medium/high
  trend: string // improving/stagnant/declining/achieved/new/resolved
  description: string
}

/** 建议项 */
export interface SuggestionItem {
  type: string // progress_confirm/persistent_warning/new_issue/first_analysis
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

/** 模板详情（FS5-P3：含 created_at） */
export interface TemplateDetail extends TemplateBrief {
  template_data: {
    goal?: { metric: string; target: number }
    sessions?: Array<{ name: string; reps: number }>
    exercises?: string[]
    metrics?: string[]
  }
  created_at?: string | null
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
  action: string // maintain/adjust/escalate/new_goal
  reason: string
  trigger_report_id: number | null
  created_at: string | null
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

/** 训练单条目（R20-P1-1：session_id→id 命名统一；R21-P2-1：含 session_index/reps） */
export interface TrainingSessionItem {
  id: number
  plan_id: number
  name: string
  scheduled_date: string | null
  is_completed: boolean
  completed_at: string | null
  exercises?: string[]
  session_index: number
  reps: number
}

/** 训练单列表响应（FS5-P3：顶层含 plan_id） */
export interface TrainingSessionListData {
  plan_id: number
  total: number
  page: number
  page_size: number
  items: TrainingSessionItem[]
}

/** 完成训练单响应（FS5-P3：含 completed_at） */
export interface CompleteSessionData {
  session_id: number
  is_completed: boolean
  plan_progress: number // 0-100
  points_earned: number
  completed_at?: string
}

/**
 * 基于分析报告的训练建议（API §8.2）。
 * 404/40412 报告不存在。
 * @param reportId - 报告 ID
 */
export function getAdviceByReport(reportId: number) {
  return request.get<TrainingAdviceData>(`/training/advice/${reportId}`)
}

/**
 * 综合训练建议（自动取最新报告，API §8.1）。
 * 404/40412 暂无分析报告。
 */
export function getContextualAdvice() {
  return request.get<TrainingAdviceData>('/training/advice/contextual')
}

/**
 * 训练方案模板列表（API §8.3，会员功能）。
 * @param problemId - 按问题筛选（可选）
 * @param page - 页码
 * @param pageSize - 每页条数（后端上限 50）
 */
export function getTemplates(problemId?: string, page: number = 1, pageSize: number = 20) {
  return request.get<TemplateListData>('/training/templates', {
    ...(problemId ? { problem_id: problemId } : {}),
    page,
    page_size: pageSize,
  })
}

/**
 * 模板详情（API §8.4，会员功能）。
 * 404/40421 模板不存在。
 * @param id - 模板 ID
 */
export function getTemplateDetail(id: number) {
  return request.get<TemplateDetail>(`/training/templates/${id}`)
}

/**
 * 训练方案调整历史（API §8.5，会员功能）。
 * 404/40420 训练方案不存在。
 * @param planId - 方案 ID
 */
export function getPlanAdjustments(planId: number) {
  return request.get<PlanAdjustmentsData>(`/training/plans/${planId}/adjustments`)
}

/**
 * 手动触发方案重新评估（API §8.6，会员功能）。
 * @param planId - 方案 ID
 */
export function reEvaluatePlan(planId: number) {
  return request.post<ReEvaluateData>(`/training/plans/${planId}/re-evaluate`)
}

/**
 * 训练单列表（API §8.7，会员功能）。
 * 404/40420 训练方案不存在。
 * @param planId - 方案 ID
 * @param page - 页码（默认 1）
 * @param pageSize - 每页条数（默认 20，最大 50）
 */
export function listTrainingSessions(planId: number, page: number = 1, pageSize: number = 20) {
  return request.get<TrainingSessionListData>(`/training/plans/${planId}/sessions`, {
    page,
    page_size: pageSize,
  })
}

/**
 * 标记训练单完成（API §8.8，会员功能）。
 * 404/40422 训练单不存在；409/40902 已完成。
 * @param planId - 方案 ID
 * @param sessionId - 训练单 ID
 */
export function completeTrainingSession(planId: number, sessionId: number) {
  return request.post<CompleteSessionData>(`/training/plans/${planId}/sessions/${sessionId}/complete`)
}
