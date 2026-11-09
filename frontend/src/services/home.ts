/**
 * home 模块 API Service（00-home/frontend.md §2）
 * 首页聚合 Service——内部复用各业务模块 service，不重复定义底层端点
 * （反幻觉约束：Service 与后端 router 逐字一致，聚合仅做转发与类型重导出）。
 *
 * FS7-P3 契约同步（与设计样例的差异，以后端实际契约为准）：
 * - 「最近分析报告」改调 GET /video-analysis/reports（ReportListItem：
 *   report_summary / cover_image_url，无 title/status/thumbnail_url/overall_score
 *   ——设计样例误用 /scoring/matches 且字段为臆造）；
 * - 「打卡周视图」数据源为 GET /gamification/checkin-calendar 月历结构
 *   （year/month/days/monthly_checkin_count/streak_days），周视图由
 *   utils/weekView.ts buildWeekView 纯函数前端派生（设计样例的
 *   week_start/exp_earned 为臆造字段）；
 * - 「概览 + 训练提醒」复用 dashboard.getOverview（OverviewData 含
 *   latest_advice_summary: AdviceSummary | null）。
 */
import * as dashboardApi from './dashboard'
import * as gamificationApi from './gamification'
import * as videoAnalysisApi from './videoAnalysis'

/** 概览数据（复用 dashboard 模块类型） */
export type { OverviewData, AdviceSummary } from './dashboard'
/** 最近分析报告条目（复用 videoAnalysis 模块类型） */
export type { ReportListItem } from './videoAnalysis'
/** 打卡月历（复用 gamification 模块类型） */
export type { CheckInCalendarData } from './gamification'

/**
 * 获取首页数据概览（复用 dashboard service，后端 Redis 缓存 5min）。
 * 响应 latest_advice_summary 即训练提醒卡片数据。
 */
export function getOverview() {
  return dashboardApi.getOverview()
}

/**
 * 获取最近 1 条分析报告（FS7-P3：改调 /video-analysis/reports，
 * 设计样例 /scoring/matches 为错误契约）。
 */
export function getLatestReport() {
  return videoAnalysisApi.listReports({ page: 1, page_size: 1 })
}

/**
 * 获取打卡月历（当月，周视图由 utils/weekView.buildWeekView 前端派生）。
 */
export function getCheckinCalendar() {
  return gamificationApi.getCheckinCalendar()
}
