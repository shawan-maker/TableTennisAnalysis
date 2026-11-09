/**
 * matchTabStore 单元测试（14-tab-pages/match-tab.md §3，FS7）
 * - 最近记录/进行中记分牌 预览落位（首条）
 * - 空态 → null
 * - 单个失败静默不阻塞另一预览
 * - refreshAll 并发两 fetch
 */
import * as matchTabApi from '@/services/matchTab'
import { useMatchTabStore } from '@/stores/matchTabStore'

jest.mock('@/services/matchTab', () => ({
  __esModule: true,
  getLatestMatch: jest.fn(),
  getCurrentScoring: jest.fn(),
}))

const api = matchTabApi as jest.Mocked<typeof matchTabApi>
const store = useMatchTabStore

const LATEST = {
  id: 5, opponent_name: '对手', opponent_rating: 1500,
  my_score: 11, opponent_score: 7, is_win: true,
  format: 'bo5', match_type: 'friendly', match_date: '2026-11-05T10:00:00Z',
}

const CURRENT = {
  id: 3, opponent_name: '对手', format: 'bo5', match_type: 'friendly',
  status: 'in_progress', current_score_user: 7, current_score_opp: 5,
  is_win: null, created_at: null,
}

const resetStore = () =>
  store.setState({
    latestMatch: null, latestMatchLoading: false,
    currentScoring: null, currentScoringLoading: false,
  })

describe('matchTabStore', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
  })

  it('fetchLatestMatch → items[0] 落位', async () => {
    api.getLatestMatch.mockResolvedValue({ data: { data: { items: [LATEST], total: 1 } } } as any)
    await store.getState().fetchLatestMatch()
    expect(store.getState().latestMatch).toEqual(LATEST)
    expect(store.getState().latestMatchLoading).toBe(false)
  })

  it('fetchLatestMatch 空列表 → null', async () => {
    api.getLatestMatch.mockResolvedValue({ data: { data: { items: [], total: 0 } } } as any)
    await store.getState().fetchLatestMatch()
    expect(store.getState().latestMatch).toBeNull()
  })

  it('fetchLatestMatch 失败 → null 不抛错', async () => {
    api.getLatestMatch.mockRejectedValue(new Error('network') as any)
    await expect(store.getState().fetchLatestMatch()).resolves.toBeUndefined()
    expect(store.getState().latestMatch).toBeNull()
    expect(store.getState().latestMatchLoading).toBe(false)
  })

  it('fetchCurrentScoring → in_progress 首条落位', async () => {
    api.getCurrentScoring.mockResolvedValue({ data: { data: { items: [CURRENT], total: 1 } } } as any)
    await store.getState().fetchCurrentScoring()
    expect(store.getState().currentScoring).toEqual(CURRENT)
  })

  it('fetchCurrentScoring 空列表 → null（无进行中比赛）', async () => {
    api.getCurrentScoring.mockResolvedValue({ data: { data: { items: [], total: 0 } } } as any)
    await store.getState().fetchCurrentScoring()
    expect(store.getState().currentScoring).toBeNull()
  })

  it('fetchCurrentScoring 失败 → null 不抛错', async () => {
    api.getCurrentScoring.mockRejectedValue(new Error('network') as any)
    await expect(store.getState().fetchCurrentScoring()).resolves.toBeUndefined()
    expect(store.getState().currentScoring).toBeNull()
  })

  it('refreshAll → 两 fetch 并发各 1 次', async () => {
    api.getLatestMatch.mockResolvedValue({ data: { data: { items: [LATEST] } } } as any)
    api.getCurrentScoring.mockResolvedValue({ data: { data: { items: [CURRENT] } } } as any)
    await store.getState().refreshAll()
    expect(api.getLatestMatch).toHaveBeenCalledTimes(1)
    expect(api.getCurrentScoring).toHaveBeenCalledTimes(1)
    expect(store.getState().latestMatch).toEqual(LATEST)
    expect(store.getState().currentScoring).toEqual(CURRENT)
  })

  it('refreshAll 单预览失败 → 另一预览仍落位（不阻塞）', async () => {
    api.getLatestMatch.mockRejectedValue(new Error('fail-latest') as any)
    api.getCurrentScoring.mockResolvedValue({ data: { data: { items: [CURRENT] } } } as any)
    await expect(store.getState().refreshAll()).resolves.toBeUndefined()
    expect(store.getState().latestMatch).toBeNull()
    expect(store.getState().currentScoring).toEqual(CURRENT)
  })
})
