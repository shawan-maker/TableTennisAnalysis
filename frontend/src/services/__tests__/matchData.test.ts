/**
 * matchData Service 契约测试（04-前端实施计划.md §6.2）
 * 断言每个函数的 HTTP 方法 + URL + 参数与后端 app/api/v1/match_data/router.py 逐字一致
 */
import request from '@/services/request'
import * as matchDataApi from '@/services/matchData'

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
const patch = request.patch as jest.Mock

describe('services/matchData 契约（4 端点）', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('createRecord → POST /match-data/records（快速录入 details=null）', async () => {
    const params: matchDataApi.MatchRecordCreateParams = {
      opponent_name: '李四',
      my_score: 11,
      opponent_score: 7,
      format: 'bo5',
      match_type: 'friendly',
      match_date: '2026-11-04T10:00:00.000Z',
      details: null,
    }
    await matchDataApi.createRecord(params)
    expect(post).toHaveBeenCalledWith('/match-data/records', params)
  })

  it('createRecord → 详细录入 details 透传', async () => {
    const params: matchDataApi.MatchRecordCreateParams = {
      opponent_name: '李四',
      my_score: 2,
      opponent_score: 1,
      format: 'custom',
      match_type: 'training',
      match_date: '2026-11-04T10:00:00.000Z',
      details: [
        {
          sequence: 1,
          scorer: 'user',
          score_method: 'rally_point',
          technique_action: 'forehand_drive',
        },
      ],
    }
    await matchDataApi.createRecord(params)
    expect(post).toHaveBeenCalledWith('/match-data/records', params)
  })

  it('listRecords → GET /match-data/records（result 缺省补 all）', async () => {
    await matchDataApi.listRecords()
    expect(get).toHaveBeenCalledWith('/match-data/records', {
      result: 'all',
      page: 1,
      page_size: 20,
    })
  })

  it('listRecords → GET /match-data/records（win 筛选 + 分页）', async () => {
    await matchDataApi.listRecords('win', 3, 50)
    expect(get).toHaveBeenCalledWith('/match-data/records', {
      result: 'win',
      page: 3,
      page_size: 50,
    })
  })

  it('getRecord → GET /match-data/records/{id}', async () => {
    await matchDataApi.getRecord(99)
    expect(get).toHaveBeenCalledWith('/match-data/records/99')
  })

  it('updateRecord → PATCH /match-data/records/{id}（is_win 不在参数面，R12-MatchData-B1）', async () => {
    const params: matchDataApi.MatchRecordUpdateParams = {
      opponent_name: '王五',
      my_score: 9,
      opponent_score: 11,
      notes: '手感不佳',
    }
    await matchDataApi.updateRecord(99, params)
    expect(patch).toHaveBeenCalledWith('/match-data/records/99', params)
    expect(params as any).not.toHaveProperty('is_win')
  })
})
