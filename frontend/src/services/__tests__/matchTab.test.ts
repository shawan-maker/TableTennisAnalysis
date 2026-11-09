/**
 * matchTab Service 契约测试（14-tab-pages/match-tab.md §2，FS7）
 * FS7-P3 契约修正断言：
 * - getCurrentScoring 走 GET /scoring/matches?status=in_progress 首条
 *   （后端无 /scoring/current 端点）
 * - getLatestMatch 走 GET /match-data/records 首条（page 1/page_size 1）
 */
import * as matchTabApi from '@/services/matchTab'
import * as matchDataApi from '@/services/matchData'
import * as scoringApi from '@/services/scoring'

jest.mock('@/services/matchData', () => ({
  __esModule: true,
  listRecords: jest.fn().mockResolvedValue({ data: { data: {} } }),
}))
jest.mock('@/services/scoring', () => ({
  __esModule: true,
  listMatches: jest.fn().mockResolvedValue({ data: { data: {} } }),
}))

const mockedMatchData = matchDataApi as jest.Mocked<typeof matchDataApi>
const mockedScoring = scoringApi as jest.Mocked<typeof scoringApi>

describe('services/matchTab 聚合转发契约', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('getLatestMatch → matchData.listRecords("all", 1, 1)', async () => {
    await matchTabApi.getLatestMatch()
    expect(mockedMatchData.listRecords).toHaveBeenCalledTimes(1)
    expect(mockedMatchData.listRecords).toHaveBeenCalledWith('all', 1, 1)
  })

  it('getCurrentScoring → scoring.listMatches("in_progress", 1, 1)（FS7-P3 契约修正）', async () => {
    await matchTabApi.getCurrentScoring()
    expect(mockedScoring.listMatches).toHaveBeenCalledTimes(1)
    expect(mockedScoring.listMatches).toHaveBeenCalledWith('in_progress', 1, 1)
  })

  it('getCurrentScoring 参数组合与后端状态机一致（status=in_progress 为唯一入口筛选）', async () => {
    await matchTabApi.getCurrentScoring()
    const [status, page, pageSize] = mockedScoring.listMatches.mock.calls[0]
    expect(status).toBe('in_progress')
    expect(page).toBe(1)
    expect(pageSize).toBe(1)
  })

  it('类型重导出编译期契约（CurrentScoringPreview=MatchBrief 实际字段）', () => {
    const brief: matchTabApi.CurrentScoringPreview = {
      id: 3,
      opponent_name: '对手',
      format: 'bo5',
      match_type: 'friendly',
      status: 'in_progress',
      current_score_user: 7,
      current_score_opp: 5,
      is_win: null,
      created_at: null,
    }
    const record: matchTabApi.LatestMatchPreview = {
      id: 1, opponent_name: '对手', opponent_rating: 1500,
      my_score: 11, opponent_score: 7, is_win: true,
      format: 'bo5', match_type: 'friendly', match_date: '2026-11-05T10:00:00Z',
    }
    expect([brief, record]).toBeTruthy()
  })
})
