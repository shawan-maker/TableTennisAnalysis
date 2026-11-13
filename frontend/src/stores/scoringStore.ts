/**
 * scoring 状态管理（04-scoring/frontend.md §3）
 * FS2 扩展：start / abandon / resume 动作（后端 X-21 / X-26 状态机）+ WS 乐观更新
 */
import { create } from 'zustand'
import * as scoringApi from '@/services/scoring'

/** 单条得分记录（镜像后端 ScoreRecordBrief：字段名 sequence，R6-Scoring-1） */
export interface ScoreRecordItem {
  sequence: number
  scorer: 'user' | 'opponent'
  score_method?: string | null
  technique_action?: string | null
  game_number: number
}

/** 比赛详情（镜像后端 MatchDetailWithSequence） */
export interface MatchDetail {
  id: number
  opponent_name: string | null
  opponent_rating?: number | null
  /** R-FE-R2 批次G（FE-P2-14）：对手打法回显（后端 MatchDetail 已暴露） */
  opponent_playing_style?: string | null
  format: string
  match_type: string
  target_score: number
  status: 'setup' | 'in_progress' | 'finished' | 'abandoned'
  current_score_user: number
  current_score_opp: number
  current_score?: string | null
  current_server?: 'user' | 'opponent' | null
  current_game: number
  // R-FE-R1 批次B（FE-P1-6 跨栈）：局分（后端 MatchDetail schema 已暴露，
  // app/schemas/scoring.py 镜像 model games_won_user/opp——bo3/bo5 大比分）
  games_won_user?: number
  games_won_opp?: number
  is_win?: boolean | null
  final_score?: string | null
  created_at?: string | null
  finished_at?: string | null
  score_sequence: ScoreRecordItem[]
}

/** 关键分（镜像后端 _generate_statistics：{seq, score, winner, method}） */
export interface KeyPointItem {
  seq: number
  score: string
  winner: 'user' | 'opponent'
  method: string | null
}

/** 比赛统计（镜像后端 MatchStatisticResponse） */
export interface MatchStatistics {
  match_id: number
  stats_data: {
    score_distribution: Record<string, number>
    key_points: KeyPointItem[]
    technique_breakdown: Record<string, number>
    total_points: number
  }
}

/** WS score_update 消息 data（镜像后端 ScoringService.score 广播体） */
export interface WsScoreUpdateData {
  match_id?: number
  sequence?: number
  /** "11:7" 形式的当前比分 */
  score?: string
  scorer?: 'user' | 'opponent'
  score_method?: string
  current_server?: 'user' | 'opponent'
  is_key_point?: boolean
  /** undo 广播时携带 type: 'undo' */
  type?: string
}

/**
 * 解析后端比分字符串（"{user}:{opp}"，如 "11:7"）。
 * 非法输入返回 null（由调用方跳过乐观更新，等待 fetchMatch 对账）。
 */
export function parseScore(score: string | null | undefined): { user: number; opp: number } | null {
  if (!score) return null
  const parts = score.split(':')
  if (parts.length !== 2) return null
  const user = parseInt(parts[0], 10)
  const opp = parseInt(parts[1], 10)
  if (isNaN(user) || isNaN(opp)) return null
  return { user, opp }
}

interface ScoringState {
  // 当前比赛
  currentMatch: MatchDetail | null
  currentStatistics: MatchStatistics | null
  isLoading: boolean
  isScoring: boolean
  // R-FE-R1 批次B（FE-P2-8）：doScore 响应的 should_change_sides/is_key_point
  // 消费缺口——修复前响应体被丢弃，换边/关键分提示全链路不可达
  //（后端 ScoreResponse L115-117 早已返回，backend.md L1642「must 返回」）
  lastScoreFlags: { should_change_sides: boolean; is_key_point: boolean } | null

  // Actions
  createMatch: (params: scoringApi.MatchCreateParams) => Promise<number>
  fetchMatch: (id: number) => Promise<void>
  startMatch: (id: number) => Promise<void>
  doScore: (matchId: number, params: scoringApi.ScoreParams) => Promise<void>
  doUndo: (matchId: number) => Promise<void>
  finishMatch: (matchId: number) => Promise<void>
  abandonMatch: (matchId: number) => Promise<void>
  resumeMatch: (matchId: number) => Promise<void>
  fetchStatistics: (matchId: number) => Promise<void>
  /** WS score_update 乐观更新（随后由 fetchMatch 对账，双路径不冲突） */
  applyWsScoreUpdate: (matchId: number, data: WsScoreUpdateData) => void
  /** R-FE-R1 批次B（FE-P2-8）：消费 score 响应提示标记（页面弹 Toast 后调用清空） */
  consumeScoreFlags: () => void
  clearCurrent: () => void
}

export const useScoringStore = create<ScoringState>((set, get) => ({
  currentMatch: null,
  currentStatistics: null,
  isLoading: false,
  isScoring: false,
  lastScoreFlags: null,

  createMatch: async (params) => {
    set({ isLoading: true })
    try {
      const res = await scoringApi.createMatch(params)
      const matchId = res.data.data.match_id
      await get().fetchMatch(matchId)
      return matchId
    } catch (error) {
      console.error('createMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  fetchMatch: async (id) => {
    set({ isLoading: true })
    try {
      const res = await scoringApi.getMatch(id)
      set({ currentMatch: res.data.data })
    } catch (error) {
      console.error('fetchMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  // X-21: score 端点要求 in_progress，创建后（setup）必须先开始
  startMatch: async (id) => {
    set({ isLoading: true })
    try {
      await scoringApi.startMatch(id)
      await get().fetchMatch(id)
    } catch (error) {
      console.error('startMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  doScore: async (matchId, params) => {
    set({ isScoring: true })
    try {
      // R-FE-R1 批次B（FE-P2-8）：捕获 ScoreResponse 的 should_change_sides /
      // is_key_point（修复前直接丢弃，全链路零消费）
      const res: any = await scoringApi.score(matchId, params)
      const data = res?.data?.data
      if (data && (data.should_change_sides || data.is_key_point)) {
        set({
          lastScoreFlags: {
            should_change_sides: !!data.should_change_sides,
            is_key_point: !!data.is_key_point,
          },
        })
      }
      // 重新拉取比赛详情
      await get().fetchMatch(matchId)
    } catch (error) {
      console.error('doScore failed', error)
      throw error
    } finally {
      set({ isScoring: false })
    }
  },

  doUndo: async (matchId) => {
    set({ isScoring: true })
    try {
      await scoringApi.undo(matchId)
      await get().fetchMatch(matchId)
    } catch (error) {
      console.error('doUndo failed', error)
      throw error
    } finally {
      set({ isScoring: false })
    }
  },

  finishMatch: async (matchId) => {
    set({ isLoading: true })
    try {
      await scoringApi.finishMatch(matchId)
      await get().fetchMatch(matchId)
    } catch (error) {
      console.error('finishMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  // X-26: in_progress → abandoned
  abandonMatch: async (matchId) => {
    set({ isLoading: true })
    try {
      await scoringApi.abandonMatch(matchId)
      await get().fetchMatch(matchId)
    } catch (error) {
      console.error('abandonMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  // X-26: abandoned → in_progress（24h 内）
  resumeMatch: async (matchId) => {
    set({ isLoading: true })
    try {
      await scoringApi.resumeMatch(matchId)
      await get().fetchMatch(matchId)
    } catch (error) {
      console.error('resumeMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  fetchStatistics: async (matchId) => {
    set({ isLoading: true })
    try {
      const res = await scoringApi.getStatistics(matchId)
      set({ currentStatistics: res.data.data })
    } catch (error) {
      console.error('fetchStatistics failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  /**
   * WS score_update 乐观更新：立即把广播的比分渲染到 UI，
   * 随后调用方会用 fetchMatch 对账（双路径不冲突，eventCenter 走跨模块通知）。
   */
  applyWsScoreUpdate: (matchId, data) => {
    const { currentMatch } = get()
    if (!currentMatch || currentMatch.id !== matchId) return
    const parsed = parseScore(data?.score)
    if (!parsed) return
    set({
      currentMatch: {
        ...currentMatch,
        current_score_user: parsed.user,
        current_score_opp: parsed.opp,
        current_score: data?.score || currentMatch.current_score || null,
        current_server: data?.current_server || currentMatch.current_server,
        status: currentMatch.status, // 状态变化统一由 fetchMatch / match_finished 事件对账
      },
    })
  },

  /** R-FE-R1 批次B（FE-P2-8）：页面消费提示标记后清空（防重复弹 Toast） */
  consumeScoreFlags: () => {
    set({ lastScoreFlags: null })
  },

  clearCurrent: () => {
    set({ currentMatch: null, currentStatistics: null })
  },
}))
