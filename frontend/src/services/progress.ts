/**
 * progress_analysis 模块 API Service（08-progress_analysis/frontend.md §2）
 * 端点与后端 app/api/v1/progress/router.py 逐字一致（6 个）
 *
 * FS4-P3 契约注记（以后端为准）：
 * - GET /progress/snapshots 另有 status 过滤参数（R4-Progress-11，可选）
 * - GET /progress/comparison：report_a === report_b → 422/42201「两份报告不能相同」；
 *   报告不存在 → 404/40412「报告不存在」
 * - GET /progress/technique-trends/{metric}：无效指标 → 404/40415 ERR_METRIC_NOT_FOUND
 *   （R14-B4-1 由 40420 改号避免与训练方案 40420 双义冲突）；
 *   有效指标无趋势数据时各字段为 null、history=[]
 */
import request from './request'

/** 指标趋势行（后端 get_technique_trends metrics / get_summary metric_trends） */
export interface MetricTrend {
  metric: string
  metric_name: string
  current_value: number | null
  previous_value: number | null
  change_rate: number | null
  trend: string | null
  target: number | null
  target_progress: number | null
  persistence_count: number
}

/** 趋势历史数据点（后端 time_series 元素） */
export interface TrendHistoryPoint {
  date: string
  value: number
}

/** 单项趋势详情（后端 get_technique_trend_detail） */
export interface TrendDetail {
  metric: string
  metric_name: string
  current_value: number | null
  target_value: number | null
  target_progress: number | null
  trend: string | null
  change_rate: number | null
  persistence_count: number | null
  history: TrendHistoryPoint[]
}

/** 快照列表项（后端 list_snapshots items） */
export interface SnapshotItem {
  id: number
  report_id: number
  created_at: string
  metrics_snapshot: Record<string, number | null>
}

export interface SnapshotListData {
  total: number
  page: number
  page_size: number
  items: SnapshotItem[]
}

/** 单维度对比值（technique_stats / landing 行） */
export interface DimComparison {
  a: number
  b: number
  change: number | null
}

/** 问题变化结构化条目（后端 ProblemChangeItem；渲染用 problem_name） */
export interface ProblemChangeItem {
  problem_id: string
  problem_name: string
  first_seen: string | null
  last_seen: string | null
  persistence_count: number | null
}

/** 报告对比 6 维度（后端 get_comparison；FS4-P3：landing 键名为 forehand_pct/backhand_pct/middle_pct） */
export interface ComparisonData {
  report_a: { id: number; created_at: string | null }
  report_b: { id: number; created_at: string | null }
  comparisons: {
    technique_stats: Record<string, DimComparison>
    landing: Record<string, DimComparison>
    rally: {
      avg_length_a: number | null
      avg_length_b: number | null
      max_length_a: number | null
      max_length_b: number | null
      change: number | null
    }
    ball_speed: {
      avg_a: number | null
      avg_b: number | null
      max_a: number | null
      max_b: number | null
      change: number | null
    }
    score_analysis: { win_rate_a: number | null; win_rate_b: number | null; change: number | null }
    problem_changes: { new: string[]; resolved: string[]; persistent: string[] }
  }
}

/** 训练方案状态（后端 get_summary R4-Progress-4；展示层 FS5 训练 Sprint 消费） */
export interface TrainingPlanStatus {
  current_plan_id: string
  plan_version: number
  last_adjustment: string | null
  adjustment_reason: string | null
  goal_completion: Record<string, string>
}

/** 线性回归预测项（后端 _linear_regression_forecast） */
export interface ForecastItem {
  predicted_weeks_to_target: number | null
  confidence: string
  r_squared: number
}

/** 进度综合摘要（后端 get_summary） */
export interface SummaryData {
  /** 取值：no_data / recent / last_3_months */
  summary_period: string
  total_analyses: number
  /** improving / stagnant / declining */
  overall_progress: string
  metric_trends: MetricTrend[]
  problem_changes: { new: string[]; resolved: string[]; persistent: string[] }
  training_plan_status: TrainingPlanStatus | null
  forecast: Record<string, ForecastItem>
}

/**
 * 进度快照列表。
 * @param params - period(month/quarter/year/all) / status(R4-Progress-11 可选) / page / page_size
 */
export function listSnapshots(params?: {
  period?: string
  status?: string
  page?: number
  page_size?: number
}) {
  return request.get<SnapshotListData>('/progress/snapshots', params)
}

/** 全部技术指标趋势（缓存 1h）。响应 { metrics: MetricTrend[] } */
export function getTechniqueTrends() {
  return request.get<{ metrics: MetricTrend[] }>('/progress/technique-trends')
}

/**
 * 单项指标趋势详情（含时间序列）。
 * @param metric - 指标名，如 backhand_ratio（不在 METRIC_DEFINITIONS 时 404/40415）
 */
export function getTechniqueTrendDetail(metric: string) {
  return request.get<TrendDetail>(`/progress/technique-trends/${metric}`)
}

/**
 * 两次分析报告对比（422/42201 相同报告；404/40412 报告不存在）。
 * @param reportA - 报告 A ID
 * @param reportB - 报告 B ID
 */
export function getComparison(reportA: number, reportB: number) {
  return request.get<ComparisonData>('/progress/comparison', {
    report_a: reportA,
    report_b: reportB,
  })
}

/** 进度综合摘要（缓存 5min）。 */
export function getSummary() {
  return request.get<SummaryData>('/progress/summary')
}

/** 问题变化列表（新增/已解决/持续，缓存 1h；item 为结构化对象，渲染用 problem_name）。 */
export function getProblemChanges() {
  return request.get<{ new: ProblemChangeItem[]; resolved: ProblemChangeItem[]; persistent: ProblemChangeItem[] }>(
    '/progress/problem-changes'
  )
}
