/**
 * scoringStore 单元测试（04-前端实施计划.md §6.2 Store 逻辑覆盖）
 * - createMatch / fetchMatch / doScore / doUndo / finishMatch 状态流转
 * - parseScore / applyWsScoreUpdate（WS score_update 乐观更新，多设备同步）
 */
import * as scoringApi from '@/services/scoring'
import { useScoringStore, parseScore, type MatchDetail } from '@/stores/scoringStore'

jest.mock('@/services/scoring', () => ({
  __esModule: true,
  createMatch: jest.fn(),
  listMatches: jest.fn(),
  getMatch: jest.fn(),
  startMatch: jest.fn(),
  score: jest.fn(),
  undo: jest.fn(),
  finishMatch: jest.fn(),
  getStatistics: jest.fn(),
  abandonMatch: jest.fn(),
  resumeMatch: jest.fn(),
}))

const api = scoringApi as jest.Mocked<typeof scoringApi>
const store = useScoringStore

const DETAIL: MatchDetail = {
  id: 42,
  opponent_name: '张三',
  opponent_rating: 1800,
  format: 'bo5',
  match_type: 'friendly',
  target_score: 11,
  status: 'in_progress',
  current_score_user: 5,
  current_score_opp: 3,
  current_score: '5:3',
  current_server: 'user',
  current_game: 1,
  is_win: null,
  final_score: null,
  created_at: '2026-11-04T09:00:00Z',
  finished_at: null,
  score_sequence: [{ sequence: 1, scorer: 'user', score_method: 'serve_point', game_number: 1 }],
}

/** 每个用例前重置 store 状态与 mock */
function resetStore() {
  store.setState({
    currentMatch: null,
    currentStatistics: null,
    isLoading: false,
    isScoring: false,
  })
  jest.clearAllMocks()
}

describe('parseScore（后端比分字符串解析）', () => {
  it('"11:7" → {user: 11, opp: 7}', () => {
    expect(parseScore('11:7')).toEqual({ user: 11, opp: 7 })
  })

  it('"0:0" → {user: 0, opp: 0}', () => {
    expect(parseScore('0:0')).toEqual({ user: 0, opp: 0 })
  })

  it('空值 / 非法格式 / NaN → null', () => {
    expect(parseScore(undefined)).toBeNull()
    expect(parseScore(null)).toBeNull()
    expect(parseScore('')).toBeNull()
    expect(parseScore('11-7')).toBeNull()
    expect(parseScore('a:b')).toBeNull()
    expect(parseScore('1:2:3')).toBeNull()
  })
})

describe('scoringStore.createMatch', () => {
  beforeEach(resetStore)

  it('创建成功：返回 match_id 并拉取详情（isLoading 先后置位/复位）', async () => {
    api.createMatch.mockResolvedValue({ data: { data: { match_id: 42 } } } as any)
    api.getMatch.mockResolvedValue({ data: { data: DETAIL } } as any)

    const matchId = await store.getState().createMatch({
      opponent_name: '张三',
      format: 'bo5',
      match_type: 'friendly',
      target_score: 11,
    })

    expect(matchId).toBe(42)
    expect(api.createMatch).toHaveBeenCalledTimes(1)
    expect(api.getMatch).toHaveBeenCalledWith(42)
    expect(store.getState().currentMatch).toEqual(DETAIL)
    expect(store.getState().isLoading).toBe(false)
  })

  it('创建失败：抛出错误且 currentMatch 保持 null', async () => {
    api.createMatch.mockRejectedValue(new Error('创建比赛失败'))
    await expect(
      store.getState().createMatch({
        opponent_name: '张三',
        format: 'bo5',
        match_type: 'friendly',
        target_score: 11,
      })
    ).rejects.toThrow('创建比赛失败')
    expect(store.getState().currentMatch).toBeNull()
    expect(store.getState().isLoading).toBe(false)
  })
})

describe('scoringStore.doScore / doUndo / finishMatch / startMatch', () => {
  beforeEach(resetStore)

  it('doScore：调 score 后重新拉详情，isScoring 复位', async () => {
    api.score.mockResolvedValue({ data: { data: { sequence: 2 } } } as any)
    api.getMatch.mockResolvedValue({ data: { data: { ...DETAIL, current_score_user: 6 } } } as any)

    await store.getState().doScore(42, { scorer: 'user', score_method: 'serve_point' })

    expect(api.score).toHaveBeenCalledWith(42, { scorer: 'user', score_method: 'serve_point' })
    expect(api.getMatch).toHaveBeenCalledWith(42)
    expect(store.getState().currentMatch?.current_score_user).toBe(6)
    expect(store.getState().isScoring).toBe(false)
  })

  it('doUndo：调 undo 后重新拉详情', async () => {
    api.undo.mockResolvedValue({ data: { data: { sequence: 1, type: 'undo' } } } as any)
    api.getMatch.mockResolvedValue({ data: { data: { ...DETAIL, current_score_user: 4 } } } as any)

    await store.getState().doUndo(42)

    expect(api.undo).toHaveBeenCalledWith(42)
    expect(store.getState().currentMatch?.current_score_user).toBe(4)
  })

  it('finishMatch：调 finish 后重新拉详情', async () => {
    api.finishMatch.mockResolvedValue({ data: { data: { match_id: 42, final_score: '11:7', is_win: true, statistic_id: 9 } } } as any)
    api.getMatch.mockResolvedValue({ data: { data: { ...DETAIL, status: 'finished', is_win: true, final_score: '11:7' } } } as any)

    await store.getState().finishMatch(42)

    expect(api.finishMatch).toHaveBeenCalledWith(42)
    expect(store.getState().currentMatch?.status).toBe('finished')
  })

  it('startMatch（X-21）：调 start 后重新拉详情', async () => {
    api.startMatch.mockResolvedValue({ data: { data: { match_id: 42, status: 'in_progress' } } } as any)
    api.getMatch.mockResolvedValue({ data: { data: { ...DETAIL, status: 'in_progress' } } } as any)

    await store.getState().startMatch(42)

    expect(api.startMatch).toHaveBeenCalledWith(42)
    expect(store.getState().currentMatch?.status).toBe('in_progress')
  })

  it('doScore 失败：错误向上抛，isScoring 复位', async () => {
    api.score.mockRejectedValue(new Error('记分失败'))
    await expect(
      store.getState().doScore(42, { scorer: 'user', score_method: 'rally_point' })
    ).rejects.toThrow('记分失败')
    expect(store.getState().isScoring).toBe(false)
  })
})

describe('scoringStore.fetchStatistics / applyWsScoreUpdate / clearCurrent', () => {
  beforeEach(resetStore)

  it('fetchStatistics：写入 currentStatistics', async () => {
    const stats = {
      match_id: 42,
      stats_data: {
        score_distribution: { serve_point: 2, rally_point: 1, opponent_error: 0 },
        key_points: [],
        technique_breakdown: { forehand_loop: 1 },
        total_points: 3,
      },
    }
    api.getStatistics.mockResolvedValue({ data: { data: stats } } as any)

    await store.getState().fetchStatistics(42)

    expect(api.getStatistics).toHaveBeenCalledWith(42)
    expect(store.getState().currentStatistics).toEqual(stats)
  })

  it('applyWsScoreUpdate：score "11:7" 乐观更新当前比分与服务方', () => {
    store.setState({ currentMatch: { ...DETAIL } })

    store.getState().applyWsScoreUpdate(42, {
      match_id: 42,
      sequence: 19,
      score: '11:7',
      scorer: 'user',
      score_method: 'rally_point',
      current_server: 'opponent',
    })

    const m = store.getState().currentMatch
    expect(m?.current_score_user).toBe(11)
    expect(m?.current_score_opp).toBe(7)
    expect(m?.current_score).toBe('11:7')
    expect(m?.current_server).toBe('opponent')
    // 状态不由此路径变更（由 fetchMatch / match_finished 对账）
    expect(m?.status).toBe('in_progress')
  })

  it('applyWsScoreUpdate：match_id 不匹配时忽略（多页面/多比赛防护）', () => {
    store.setState({ currentMatch: { ...DETAIL } })
    store.getState().applyWsScoreUpdate(99, { match_id: 99, score: '8:8' })
    expect(store.getState().currentMatch?.current_score_user).toBe(5)
  })

  it('applyWsScoreUpdate：非法 score 字符串时跳过（等待 fetchMatch 对账）', () => {
    store.setState({ currentMatch: { ...DETAIL } })
    store.getState().applyWsScoreUpdate(42, { match_id: 42, score: 'garbage' })
    expect(store.getState().currentMatch?.current_score_user).toBe(5)
  })

  it('applyWsScoreUpdate：无 currentMatch 时安全返回', () => {
    expect(() =>
      store.getState().applyWsScoreUpdate(42, { match_id: 42, score: '1:0' })
    ).not.toThrow()
  })

  it('clearCurrent：清空比赛与统计', () => {
    store.setState({ currentMatch: { ...DETAIL }, currentStatistics: { match_id: 42, stats_data: {} as any } })
    store.getState().clearCurrent()
    expect(store.getState().currentMatch).toBeNull()
    expect(store.getState().currentStatistics).toBeNull()
  })
})
