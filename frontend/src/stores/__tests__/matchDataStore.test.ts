/**
 * matchDataStore 单元测试（04-前端实施计划.md §6.2 Store 逻辑覆盖）
 * - fetchRecords 分页（page=1 覆盖 / page>1 append）
 * - createRecord 返回 is_win
 * - fetchDetail / clearDetail / resetList
 */
import * as matchDataApi from '@/services/matchData'
import { useMatchDataStore } from '@/stores/matchDataStore'
import type { MatchRecordListItem, MatchRecordDetailItem } from '@/services/matchData'

jest.mock('@/services/matchData', () => ({
  __esModule: true,
  createRecord: jest.fn(),
  listRecords: jest.fn(),
  getRecord: jest.fn(),
  updateRecord: jest.fn(),
}))

const api = matchDataApi as jest.Mocked<typeof matchDataApi>
const store = useMatchDataStore

const ITEMS_PAGE_1: MatchRecordListItem[] = [
  { id: 1, opponent_name: '张三', my_score: 11, opponent_score: 7, is_win: true, format: 'bo5', match_type: 'friendly', match_date: '2026-11-01T10:00:00Z' },
  { id: 2, opponent_name: '李四', my_score: 5, opponent_score: 11, is_win: false, format: 'bo3', match_type: 'friendly', match_date: '2026-11-02T10:00:00Z' },
]

const ITEMS_PAGE_2: MatchRecordListItem[] = [
  { id: 3, opponent_name: '王五', my_score: 11, opponent_score: 9, is_win: true, format: 'bo7', match_type: 'tournament', match_date: '2026-11-03T10:00:00Z' },
]

const DETAIL: MatchRecordDetailItem = {
  id: 1,
  opponent_name: '张三',
  opponent_rating: 1800,
  my_score: 11,
  opponent_score: 7,
  is_win: true,
  format: 'bo5',
  match_type: 'friendly',
  match_date: '2026-11-01T10:00:00Z',
  match_id: 55,
  is_detailed: true,
  notes: null,
  details: [
    { sequence: 1, scorer: 'user', score_method: 'serve_point', technique_action: 'forehand_loop' },
  ],
}

function resetStore() {
  store.setState({ records: [], total: 0, page: 1, isLoading: false, currentDetail: null })
  jest.clearAllMocks()
}

describe('matchDataStore.fetchRecords', () => {
  beforeEach(resetStore)

  it('page=1：覆盖式写入（重进列表不残留旧数据）', async () => {
    store.setState({ records: ITEMS_PAGE_2, total: 1, page: 2 })
    api.listRecords.mockResolvedValue({ data: { data: { items: ITEMS_PAGE_1, total: 3 } } } as any)

    await store.getState().fetchRecords('all', 1)

    expect(api.listRecords).toHaveBeenCalledWith('all', 1)
    expect(store.getState().records).toEqual(ITEMS_PAGE_1)
    expect(store.getState().total).toBe(3)
    expect(store.getState().page).toBe(1)
    expect(store.getState().isLoading).toBe(false)
  })

  it('page=2：追加模式（上拉加载更多）', async () => {
    store.setState({ records: ITEMS_PAGE_1, total: 3, page: 1 })
    api.listRecords.mockResolvedValue({ data: { data: { items: ITEMS_PAGE_2, total: 3 } } } as any)

    await store.getState().fetchRecords('all', 2)

    expect(store.getState().records).toEqual([...ITEMS_PAGE_1, ...ITEMS_PAGE_2])
    expect(store.getState().total).toBe(3)
    expect(store.getState().page).toBe(2)
  })

  it('win 筛选：result 参数透传 service', async () => {
    api.listRecords.mockResolvedValue({ data: { data: { items: [], total: 0 } } } as any)
    await store.getState().fetchRecords('win', 1)
    expect(api.listRecords).toHaveBeenCalledWith('win', 1)
  })

  it('请求抛错：isLoading 复位且错误向上抛', async () => {
    api.listRecords.mockRejectedValue(new Error('Request failed'))
    await expect(store.getState().fetchRecords('all', 1)).rejects.toThrow('Request failed')
    expect(store.getState().isLoading).toBe(false)
  })
})

describe('matchDataStore.createRecord / fetchDetail', () => {
  beforeEach(resetStore)

  it('createRecord：返回 {id, is_win}（快速录入胜负 Toast 依据）', async () => {
    api.createRecord.mockResolvedValue({ data: { data: { id: 9, is_win: true } } } as any)

    const result = await store.getState().createRecord({
      opponent_name: '张三',
      my_score: 11,
      opponent_score: 7,
      format: 'bo5',
      match_type: 'friendly',
      match_date: '2026-11-04T10:00:00.000Z',
      details: null,
    })

    expect(result).toEqual({ id: 9, is_win: true })
    expect(store.getState().isLoading).toBe(false)
  })

  it('fetchDetail：写入 currentDetail', async () => {
    api.getRecord.mockResolvedValue({ data: { data: DETAIL } } as any)

    await store.getState().fetchDetail(1)

    expect(api.getRecord).toHaveBeenCalledWith(1)
    expect(store.getState().currentDetail).toEqual(DETAIL)
  })

  it('clearDetail：清空详情态', () => {
    store.setState({ currentDetail: DETAIL })
    store.getState().clearDetail()
    expect(store.getState().currentDetail).toBeNull()
  })

  it('resetList：清空列表分页态', () => {
    store.setState({ records: ITEMS_PAGE_1, total: 3, page: 2 })
    store.getState().resetList()
    const s = store.getState()
    expect(s.records).toEqual([])
    expect(s.total).toBe(0)
    expect(s.page).toBe(1)
  })
})
