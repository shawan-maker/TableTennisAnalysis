/**
 * scoring Service 契约测试（04-前端实施计划.md §6.2）
 * 断言每个函数的 HTTP 方法 + URL + 参数与后端 app/api/v1/scoring/router.py 逐字一致
 */
import request from '@/services/request'
import * as scoringApi from '@/services/scoring'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
    patch: jest.fn().mockResolvedValue({ data: { data: {} } }),
    delete: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

const post = request.post as jest.Mock
const get = request.get as jest.Mock

describe('services/scoring 契约（10 端点）', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('createMatch → POST /scoring/matches（全参数透传）', async () => {
    const params: scoringApi.MatchCreateParams = {
      opponent_name: '张三',
      opponent_rating: 1800,
      format: 'bo5',
      match_type: 'friendly',
      target_score: 11,
    }
    await scoringApi.createMatch(params)
    expect(post).toHaveBeenCalledWith('/scoring/matches', params)
  })

  it('listMatches → GET /scoring/matches（status/page/page_size）', async () => {
    await scoringApi.listMatches('in_progress', 2, 50)
    expect(get).toHaveBeenCalledWith('/scoring/matches', {
      status: 'in_progress',
      page: 2,
      page_size: 50,
    })
  })

  it('listMatches 无 status → status 透传 undefined', async () => {
    await scoringApi.listMatches()
    expect(get).toHaveBeenCalledWith('/scoring/matches', {
      status: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('getMatch → GET /scoring/matches/{id}', async () => {
    await scoringApi.getMatch(42)
    expect(get).toHaveBeenCalledWith('/scoring/matches/42')
  })

  it('startMatch → POST /scoring/matches/{id}/start（X-21）', async () => {
    await scoringApi.startMatch(42)
    expect(post).toHaveBeenCalledWith('/scoring/matches/42/start')
  })

  it('score → POST /scoring/matches/{id}/score', async () => {
    const params: scoringApi.ScoreParams = {
      scorer: 'user',
      score_method: 'serve_point',
      technique_action: 'forehand_loop',
    }
    await scoringApi.score(42, params)
    expect(post).toHaveBeenCalledWith('/scoring/matches/42/score', params)
  })

  it('undo → POST /scoring/matches/{id}/undo（无 expected_seq 时 body 为 null）', async () => {
    await scoringApi.undo(42)
    expect(post).toHaveBeenCalledWith('/scoring/matches/42/undo', null)
  })

  it('undo → POST /scoring/matches/{id}/undo（expected_seq 乐观并发控制）', async () => {
    await scoringApi.undo(42, 7)
    expect(post).toHaveBeenCalledWith('/scoring/matches/42/undo', { expected_seq: 7 })
  })

  it('finishMatch → POST /scoring/matches/{id}/finish', async () => {
    await scoringApi.finishMatch(42)
    expect(post).toHaveBeenCalledWith('/scoring/matches/42/finish')
  })

  it('getStatistics → GET /scoring/matches/{id}/statistics', async () => {
    await scoringApi.getStatistics(42)
    expect(get).toHaveBeenCalledWith('/scoring/matches/42/statistics')
  })

  it('abandonMatch → POST /scoring/matches/{id}/abandon（X-26）', async () => {
    await scoringApi.abandonMatch(42)
    expect(post).toHaveBeenCalledWith('/scoring/matches/42/abandon')
  })

  it('resumeMatch → POST /scoring/matches/{id}/resume（X-26）', async () => {
    await scoringApi.resumeMatch(42)
    expect(post).toHaveBeenCalledWith('/scoring/matches/42/resume')
  })
})
