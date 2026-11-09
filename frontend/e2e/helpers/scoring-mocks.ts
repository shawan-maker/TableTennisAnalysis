/**
 * E2E-02 记分牌 mock 状态机（docs/07实施计划/02-测试计划.md §7.2）
 *
 * 以内存状态镜像后端 ScoringService（app/services/scoring_service.py）语义：
 * - POST /scoring/matches            创建（status=setup，Redis 序号/比分初值）
 * - GET  /scoring/matches/{id}       MatchDetailWithSequence（current_score "u:o"）
 * - POST /scoring/matches/{id}/start 状态机 setup → in_progress（X-21）
 * - POST /scoring/matches/{id}/score Redis INCR 序号 + 比分 + boN 局推进
 *                                    （game_ended：达 target 且净胜 2；达赛制局数自动全场结束）
 * - POST /scoring/matches/{id}/undo  pop 最近一球 + 当前局比分重算（序号回退）
 * - POST /scoring/matches/{id}/finish 局分判定 is_win/final_score（bo3 的 "1:0"）
 * - GET  /scoring/matches/{id}/statistics  _generate_statistics：
 *                                    score_distribution / technique_breakdown / total_points
 * - GET  /dashboard/match-records    finished 后动态插入一条（E2E-02 步骤 9 看板联动）
 *
 * 响应字段与 app/schemas/scoring.py（MatchCreateResponse/ScoreResponse/
 * UndoResponse/FinishResponse/MatchStatisticResponse）及前端 service 镜像
 * 类型（stores/scoringStore.ts MatchDetail）逐字一致。
 */
import type { MockRoute } from './mock-api'

interface ScoreRecord {
  sequence: number
  scorer: 'user' | 'opponent'
  score_method: string
  technique_action: string | null
  game_number: number
}

interface MatchState {
  id: number
  opponent_name: string
  opponent_rating: number | null
  format: string
  match_type: string
  target_score: number
  status: 'setup' | 'in_progress' | 'finished' | 'abandoned'
  score_user: number
  score_opp: number
  current_game: number
  current_server: 'user' | 'opponent'
  games_won_user: number
  games_won_opp: number
  is_win: boolean | null
  final_score: string | null
  records: ScoreRecord[]
  seq: number
}

/** 赛制 → 需胜局数（镜像后端 GAMES_TO_WIN） */
const GAMES_TO_WIN: Record<string, number> = { bo1: 1, bo3: 2, bo5: 3, bo7: 4, custom: 1 }

/** 简化发球轮换：11 分制每 2 球换发（10:10 后每 1 球的后端细节不参与断言） */
function calcServer(totalBalls: number, scoreUser: number, scoreOpp: number, target: number) {
  if (scoreUser >= target - 1 && scoreOpp >= target - 1) {
    return totalBalls % 2 === 0 ? 'user' : 'opponent'
  }
  return Math.floor(totalBalls / 2) % 2 === 0 ? 'user' : 'opponent'
}

/** 当前局比分重算（undo 后从记录累计；镜像后端 Redis hash 回退语义） */
function recountCurrentGame(m: MatchState) {
  m.score_user = m.records.filter((r) => r.game_number === m.current_game && r.scorer === 'user').length
  m.score_opp = m.records.filter((r) => r.game_number === m.current_game && r.scorer === 'opponent').length
}

function matchDetail(m: MatchState) {
  return {
    id: m.id,
    opponent_name: m.opponent_name,
    opponent_rating: m.opponent_rating,
    format: m.format,
    match_type: m.match_type,
    target_score: m.target_score,
    status: m.status,
    current_score_user: m.score_user,
    current_score_opp: m.score_opp,
    current_score: `${m.score_user}:${m.score_opp}`,
    current_server: m.current_server,
    current_game: m.current_game,
    is_win: m.is_win,
    final_score: m.final_score,
    created_at: new Date().toISOString(),
    finished_at: m.status === 'finished' ? new Date().toISOString() : null,
    score_sequence: m.records.map((r) => ({ ...r })),
  }
}

/**
 * 构建记分牌 mock 路由（闭包共享 matchState——多设备两 page 各自安装
 * 同一份 routes，REST 状态天然一致）。
 * 返回 { routes, state }：state 供测试侧读取（推送 WS 广播载荷）。
 */
export function createScoringMocks(startMatchId = 4001) {
  const state: { match: MatchState | null; nextMatchId: number } = {
    match: null,
    nextMatchId: startMatchId,
  }

  const getMatch = (params: string[]) => {
    const m = state.match
    if (!m || m.id !== Number(params[0])) throw new Error('match not found')
    return m
  }

  const routes: MockRoute[] = [
    // POST /scoring/matches（MatchCreateResponse：{match_id, status}）
    {
      method: 'POST',
      pattern: '/scoring/matches',
      dynamic: ({ body }) => {
        const id = state.nextMatchId++
        state.match = {
          id,
          opponent_name: body?.opponent_name ?? '对手',
          opponent_rating: body?.opponent_rating ?? null,
          format: body?.format ?? 'bo3',
          match_type: body?.match_type ?? 'friendly',
          target_score: body?.target_score ?? 11,
          status: 'setup',
          score_user: 0,
          score_opp: 0,
          current_game: 1,
          current_server: 'user',
          games_won_user: 0,
          games_won_opp: 0,
          is_win: null,
          final_score: null,
          records: [],
          seq: 0,
        }
        return { match_id: id, status: 'setup' }
      },
    },
    // GET /scoring/matches/{id}（MatchDetailWithSequence）
    {
      method: 'GET',
      pattern: '/scoring/matches/*',
      dynamic: ({ params }) => matchDetail(getMatch(params)),
    },
    // POST /scoring/matches/{id}/start（X-21：setup → in_progress）
    {
      method: 'POST',
      pattern: '/scoring/matches/*/start',
      dynamic: ({ params }) => {
        const m = getMatch(params)
        m.status = 'in_progress'
        return { match_id: m.id, status: 'in_progress' }
      },
    },
    // POST /scoring/matches/{id}/score（ScoreResponse；boN 局推进镜像 R12-SC-1）
    {
      method: 'POST',
      pattern: '/scoring/matches/*/score',
      dynamic: ({ params, body }) => {
        const m = getMatch(params)
        // 40910（比赛未在进行中）分支不参与 E2E-02 主流程（记分总在 in_progress），
        // 契约行为由 Jest service 契约测试锁定
        const seq = m.seq + 1
        m.seq = seq
        if (body?.scorer === 'user') m.score_user += 1
        else m.score_opp += 1
        const t = m.target_score
        const gameEnded =
          (m.score_user >= t && m.score_user - m.score_opp >= 2) ||
          (m.score_opp >= t && m.score_opp - m.score_user >= 2)
        const recordGameNumber = m.current_game
        m.records.push({
          sequence: seq,
          scorer: body?.scorer ?? 'user',
          score_method: body?.score_method ?? 'rally_point',
          technique_action: body?.technique_action ?? null,
          game_number: recordGameNumber,
        })
        let matchStatus = 'in_progress'
        if (gameEnded) {
          if (m.score_user > m.score_opp) m.games_won_user += 1
          else m.games_won_opp += 1
          const need = GAMES_TO_WIN[m.format] ?? 1
          if (m.games_won_user >= need || m.games_won_opp >= need) {
            // 全场自动结束（R12-SC-1：多局累计达赛制局数）
            m.status = 'finished'
            m.is_win = m.games_won_user > m.games_won_opp
            m.final_score = `${m.games_won_user}:${m.games_won_opp}`
            matchStatus = 'finished'
          } else {
            // 进入下一局（比分清零、局数+1）
            m.score_user = 0
            m.score_opp = 0
            m.current_game += 1
          }
        }
        m.current_server = calcServer(seq, m.score_user, m.score_opp, t) as 'user' | 'opponent'
        return {
          sequence: seq,
          score: `${m.score_user}:${m.score_opp}`,
          current_server: m.current_server,
          game_number: recordGameNumber,
          is_key_point: false,
          match_status: matchStatus,
          should_change_sides: false,
        }
      },
    },
    // POST /scoring/matches/{id}/undo（UndoResponse：pop 最近一球 + 序号回退）
    {
      method: 'POST',
      pattern: '/scoring/matches/*/undo',
      dynamic: ({ params }) => {
        const m = getMatch(params)
        m.records.pop()
        m.seq = Math.max(0, m.seq - 1)
        recountCurrentGame(m)
        return {
          sequence: m.seq,
          score: `${m.score_user}:${m.score_opp}`,
          type: 'undo',
        }
      },
    },
    // POST /scoring/matches/{id}/finish（FinishResponse；局分判定镜像后端）
    {
      method: 'POST',
      pattern: '/scoring/matches/*/finish',
      dynamic: ({ params }) => {
        const m = getMatch(params)
        if (m.games_won_user > 0 || m.games_won_opp > 0) {
          m.is_win = m.games_won_user > m.games_won_opp
          m.final_score = `${m.games_won_user}:${m.games_won_opp}`
        } else {
          m.is_win = m.score_user > m.score_opp
          m.final_score = `${m.score_user}:${m.score_opp}`
        }
        m.status = 'finished'
        return {
          match_id: m.id,
          final_score: m.final_score,
          is_win: m.is_win,
          statistic_id: 5001,
        }
      },
    },
    // GET /scoring/matches/{id}/statistics（MatchStatisticResponse）
    {
      method: 'GET',
      pattern: '/scoring/matches/*/statistics',
      dynamic: ({ params }) => {
        const m = getMatch(params)
        const scoreDistribution: Record<string, number> = {
          serve_point: 0,
          rally_point: 0,
          opponent_error: 0,
        }
        const techniqueBreakdown: Record<string, number> = {}
        for (const r of m.records) {
          scoreDistribution[r.score_method] = (scoreDistribution[r.score_method] ?? 0) + 1
          if (r.technique_action) {
            techniqueBreakdown[r.technique_action] = (techniqueBreakdown[r.technique_action] ?? 0) + 1
          }
        }
        return {
          match_id: m.id,
          stats_data: {
            score_distribution: scoreDistribution,
            key_points: [],
            technique_breakdown: techniqueBreakdown,
            total_points: m.records.length,
          },
        }
      },
    },
    // GET /dashboard/match-records（E2E-02 步骤 9/10：finished 后看板记录联动，
    // 字段镜像 services/dashboard.ts MatchRecordItem）
    {
      method: 'GET',
      pattern: '/dashboard/match-records',
      dynamic: () => {
        const m = state.match
        const items =
          m && m.status === 'finished'
            ? [
                {
                  id: m.id,
                  opponent_name: m.opponent_name,
                  opponent_rating: m.opponent_rating,
                  my_score: m.games_won_user,
                  opponent_score: m.games_won_opp,
                  is_win: !!m.is_win,
                  format: m.format,
                  match_type: m.match_type,
                  match_date: new Date().toISOString(),
                },
              ]
            : []
        return { items, total: items.length, page: 1, page_size: 20 }
      },
    },
  ]

  return { routes, state }
}
