/**
 * match_data 模块 API Service（05-match_data/frontend.md §2）
 * 端点与后端 app/api/v1/match_data/router.py 逐字一致（4 端点）
 *
 * FS2-P3 契约同步：后端在切片文档 3 端点基础上补充 PATCH
 * 编辑端点（R12-MatchData-B1：is_win 禁止前端传入，服务端自动重算）：
 * - POST  /match-data/records        创建比赛记录（快速/详细录入统一入口）
 * - GET   /match-data/records        比赛记录列表
 * - GET   /match-data/records/{id}   比赛记录详情（含逐分明细）
 * - PATCH /match-data/records/{id}   编辑比赛记录
 */
import request from './request'

/** 逐分明细条目（镜像后端 ManualScoreDetailItem） */
export interface ScoreDetailItem {
  sequence: number
  scorer: 'user' | 'opponent'
  score_method: 'serve_point' | 'rally_point' | 'opponent_error'
  technique_action?: string
}

/** 创建比赛记录参数（镜像后端 MatchRecordCreateRequest） */
export interface MatchRecordCreateParams {
  opponent_name: string
  opponent_rating?: number
  my_score: number
  opponent_score: number
  format: 'bo1' | 'bo3' | 'bo5' | 'bo7' | 'custom'
  match_type: 'friendly' | 'tournament' | 'training'
  match_date: string
  details?: ScoreDetailItem[] | null
  match_id?: number
}

/** 编辑比赛记录参数（镜像后端 MatchRecordUpdate；is_win 由服务端自动重算，禁止传入） */
export interface MatchRecordUpdateParams {
  opponent_name?: string
  opponent_rating?: number
  my_score?: number
  opponent_score?: number
  match_date?: string
  match_type?: 'friendly' | 'tournament' | 'training'
  notes?: string
}

/** 比赛记录列表项（镜像后端 MatchRecordBrief） */
export interface MatchRecordListItem {
  id: number
  opponent_name: string
  opponent_rating?: number
  my_score: number
  opponent_score: number
  is_win: boolean
  format: string
  match_type: string
  match_date: string
}

/** 比赛记录详情（镜像后端 MatchRecordDetail） */
export interface MatchRecordDetailItem extends MatchRecordListItem {
  match_id?: number
  is_detailed: boolean
  notes?: string | null
  details: ScoreDetailItem[]
}

/**
 * 创建比赛记录（快速/详细录入统一入口）。
 */
export function createRecord(params: MatchRecordCreateParams) {
  return request.post('/match-data/records', params)
}

/**
 * 获取比赛记录列表。
 * @param result - 胜负筛选: win/lose/all
 * @param page - 页码
 * @param page_size - 每页条数
 */
export function listRecords(result?: string, page = 1, pageSize = 20) {
  return request.get('/match-data/records', { result: result || 'all', page, page_size: pageSize })
}

/**
 * 获取比赛记录详情（含逐分明细）。
 */
export function getRecord(id: number) {
  return request.get(`/match-data/records/${id}`)
}

/**
 * 编辑比赛记录（PATCH 语义，仅限未关联记分牌的记录）。
 * R12-MatchData-B1：is_win 由服务端自动重算，禁止前端传入。
 */
export function updateRecord(id: number, params: MatchRecordUpdateParams) {
  return request.patch(`/match-data/records/${id}`, params)
}
