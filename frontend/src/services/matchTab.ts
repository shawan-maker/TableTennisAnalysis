/**
 * matchTab 模块 API Service（14-tab-pages/match-tab.md §2）
 * 赛事 Tab 入口页预览数据（最近 1 条比赛记录 + 进行中记分牌）。
 *
 * FS7-P3 契约同步（与设计样例的差异，以后端实际契约为准）：
 * - 设计样例的 GET /scoring/current 端点后端不存在（scoring router 仅 14 个
 *   /scoring/matches* 端点）——「进行中记分牌」改调 GET /scoring/matches?status=in_progress
 *   取第一条（MatchBrief：status / current_score_user / current_score_opp，
 *   样例的 my_name / my_score 字段名为臆造）；
 * - GET /match-data/records 契约一致（MatchRecordListItem 镜像后端 MatchRecordBrief）。
 */
import * as matchDataApi from './matchData'
import * as scoringApi from './scoring'
import type { MatchRecordListItem } from './matchData'
import type { MatchBrief } from './scoring'

/** 最近比赛记录预览（镜像后端 MatchRecordBrief） */
export type LatestMatchPreview = MatchRecordListItem

/** 进行中记分牌预览（镜像后端 MatchBrief，status='in_progress'） */
export type CurrentScoringPreview = MatchBrief

export type { MatchRecordListItem } from './matchData'
export type { MatchBrief } from './scoring'

/**
 * 获取最近 1 条比赛记录（用于赛事 Tab 预览）。
 */
export function getLatestMatch() {
  return matchDataApi.listRecords('all', 1, 1)
}

/**
 * 获取当前进行中的记分牌（用于赛事 Tab 预览）。
 * FS7-P3：后端无 /scoring/current 端点，改按状态筛选列表取第一条；
 * 无进行中比赛时 items 为空数组。
 */
export function getCurrentScoring() {
  return scoringApi.listMatches('in_progress', 1, 1)
}
