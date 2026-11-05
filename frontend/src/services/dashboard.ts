/**
 * data_dashboard 模块 API Service（06-data_dashboard/frontend.md §2）
 * 端点与后端 app/api/v1/dashboard/router.py 逐字一致（5 个）
 */
import request from './request'

/** 最近训练建议摘要（后端 _get_latest_advice_summary） */
export interface AdviceSummary {
  report_id: number
  summary: string
  has_unresolved_issues: boolean
  latest_report_at: string
}

/** 概览卡片（后端 get_overview；win_rate 为 0-1 浮点） */
export interface OverviewData {
  win_rate: number
  wins: number
  losses: number
  analysis_count: number
  training_frequency_per_week: number
  streak_days: number
  trend: string // up/down/flat
  latest_advice_summary: AdviceSummary | null
  /** R12-Dash-2：降级用户简化看板标记（会员到期）——展示分支 FS6 会员 Sprint 消费 */
  is_readonly?: boolean
}

export interface TrendSeries {
  name: string
  data: number[]
}

/** 战绩趋势（后端 get_win_rate_trend；series[0]=胜率(0-1)、series[1]=比赛场次） */
export interface WinRateTrendData {
  labels: string[]
  series: TrendSeries[]
}

export interface TechniqueItem {
  name: string
  value: number
  color: string
}

/** 技术统计（后端 get_technique_stats，聚合最近 10 份报告） */
export interface TechniqueStatsData {
  technique_distribution: TechniqueItem[]
}

/** 累计落点热图（后端 get_landing_heatmap；distribution 为 0-1 占比） */
export interface LandingHeatmapData {
  nine_grid: number[][]
  distribution: { forehand: number; backhand: number; middle: number }
  total_rallies: number
  source_reports_count: number
}

export interface MatchRecordItem {
  id: number
  opponent_name: string | null
  opponent_rating: number | null
  my_score: number
  opponent_score: number
  is_win: boolean
  format: string
  match_type: string
  match_date: string
}

export interface MatchRecordsData {
  total: number
  page: number
  page_size: number
  items: MatchRecordItem[]
}

export type TrendPeriod = 'month' | 'quarter' | 'year'
export type ResultFilter = 'win' | 'lose' | 'all'

/** 概览卡片（Redis 缓存 5min） */
export function getOverview() {
  return request.get<OverviewData>('/dashboard/overview')
}

/**
 * 战绩趋势折线图数据（缓存 1h）。
 * @param period - 时间范围：month/quarter/year
 */
export function getWinRateTrend(period: TrendPeriod = 'month') {
  return request.get<WinRateTrendData>('/dashboard/win-rate-trend', { period })
}

/** 技术统计环形图数据（缓存 1h）。 */
export function getTechniqueStats() {
  return request.get<TechniqueStatsData>('/dashboard/technique-stats')
}

/** 累计落点热图数据（缓存 1h）。 */
export function getLandingHeatmap() {
  return request.get<LandingHeatmapData>('/dashboard/landing-heatmap')
}

/**
 * 比赛记录列表（实时查询，不缓存）。
 * @param result - 筛选：win/lose/all
 * @param page - 页码
 * @param pageSize - 每页条数
 */
export function getMatchRecords(
  result: ResultFilter = 'all',
  page: number = 1,
  pageSize: number = 20
) {
  return request.get<MatchRecordsData>('/dashboard/match-records', {
    result,
    page,
    page_size: pageSize,
  })
}
