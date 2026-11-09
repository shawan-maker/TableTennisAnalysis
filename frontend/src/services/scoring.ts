/**
 * scoring 模块 API Service（04-scoring/frontend.md §2）
 * 端点与后端 app/api/v1/scoring/router.py 逐字一致（10 端点）
 *
 * FS2-P3 契约同步：后端在切片文档 7 端点基础上补充
 * start / abandon / resume 3 端点（X-21 / X-26 变更），本文件全量镜像：
 * - POST /scoring/matches                       创建比赛
 * - GET  /scoring/matches                       比赛列表
 * - GET  /scoring/matches/{id}                  比赛详情（含比分序列）
 * - POST /scoring/matches/{id}/start            开始比赛（setup → in_progress）
 * - POST /scoring/matches/{id}/score            记分
 * - POST /scoring/matches/{id}/undo             撤销最近一球
 * - POST /scoring/matches/{id}/finish           结束比赛
 * - GET  /scoring/matches/{id}/statistics       比赛统计
 * - POST /scoring/matches/{id}/abandon          放弃比赛
 * - POST /scoring/matches/{id}/resume           恢复比赛（24h 内）
 */
import request from './request'

/** 比赛创建参数（镜像后端 MatchCreateRequest） */
export interface MatchCreateParams {
  opponent_name: string
  opponent_rating?: number
  format: 'bo1' | 'bo3' | 'bo5' | 'bo7' | 'custom'
  match_type: 'friendly' | 'tournament' | 'training'
  target_score: number
}

/** 记分参数（镜像后端 ScoreRequest） */
export interface ScoreParams {
  scorer: 'user' | 'opponent'
  score_method: 'serve_point' | 'rally_point' | 'opponent_error'
  technique_action?: string
}

/** 比赛简要信息（镜像后端 app/schemas/scoring.py MatchBrief，FS7 首页/赛事 Tab 消费） */
export interface MatchBrief {
  id: number
  opponent_name: string | null
  format: string
  match_type: string
  status: string // setup / in_progress / finished / abandoned（X-21 状态机）
  current_score_user: number
  current_score_opp: number
  is_win: boolean | null
  created_at: string | null
}

/** 分页响应（后端统一形态 Paginated） */
export interface MatchListData {
  total: number
  page: number
  page_size: number
  items: MatchBrief[]
}

/**
 * 创建比赛。
 */
export function createMatch(params: MatchCreateParams) {
  return request.post('/scoring/matches', params)
}

/**
 * 获取比赛列表。
 * @param status - 状态筛选
 * @param page - 页码
 * @param page_size - 每页条数
 */
export function listMatches(status?: string, page = 1, pageSize = 20) {
  return request.get<MatchListData>('/scoring/matches', { status, page, page_size: pageSize })
}

/**
 * 获取比赛详情（含比分序列）。
 */
export function getMatch(id: number) {
  return request.get(`/scoring/matches/${id}`)
}

/**
 * 开始比赛（状态机：setup → in_progress，X-21）。
 * 后端 score 要求 match.status === 'in_progress'，记分页进入时必须先调用。
 */
export function startMatch(id: number) {
  return request.post(`/scoring/matches/${id}/start`)
}

/**
 * 记分（得分方 + 得分方式）。
 */
export function score(matchId: number, params: ScoreParams) {
  return request.post(`/scoring/matches/${matchId}/score`, params)
}

/**
 * 撤销最近一球（可选 expected_seq 乐观并发控制）。
 */
export function undo(matchId: number, expectedSeq?: number) {
  return request.post(`/scoring/matches/${matchId}/undo`, expectedSeq ? { expected_seq: expectedSeq } : null)
}

/**
 * 结束比赛 → 生成统计。
 */
export function finishMatch(matchId: number) {
  return request.post(`/scoring/matches/${matchId}/finish`)
}

/**
 * 获取比赛统计。
 */
export function getStatistics(matchId: number) {
  return request.get(`/scoring/matches/${matchId}/statistics`)
}

/**
 * 放弃比赛（状态机：in_progress → abandoned，X-26）。
 */
export function abandonMatch(matchId: number) {
  return request.post(`/scoring/matches/${matchId}/abandon`)
}

/**
 * 恢复放弃的比赛（状态机：abandoned → in_progress，24h 内，X-26）。
 */
export function resumeMatch(matchId: number) {
  return request.post(`/scoring/matches/${matchId}/resume`)
}
