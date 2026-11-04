/**
 * useMatchSync 协议测试（04-scoring/frontend.md §8）
 * 断言订阅消息体与事件归属判定与后端 ws.py receive_loop / API §14.2 一致
 */
import { buildSubscribeMessage, isMatchWsEvent, MATCH_WS_EVENTS } from '@/hooks/useMatchSync'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
    patch: jest.fn().mockResolvedValue({ data: { data: {} } }),
    delete: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

describe('buildSubscribeMessage（后端 ws.py subscribe 协议）', () => {
  it('构造 {event:"subscribe", match_id}', () => {
    expect(buildSubscribeMessage(42)).toEqual({ event: 'subscribe', match_id: 42 })
  })
})

describe('isMatchWsEvent（两级分发：event → match_id）', () => {
  it('score_update 且 match_id 匹配 → true', () => {
    expect(
      isMatchWsEvent({ event: 'score_update', data: { match_id: 42, score: '11:7' } }, 42)
    ).toBe(true)
  })

  it('score_update 但 match_id 不匹配 → false（多比赛防护）', () => {
    expect(
      isMatchWsEvent({ event: 'score_update', data: { match_id: 99, score: '3:3' } }, 42)
    ).toBe(false)
  })

  it('sync_match 且 match_id 匹配 → true', () => {
    expect(
      isMatchWsEvent(
        { event: 'sync_match', data: { match_id: 42, status: 'in_progress', current_score: '5:3', score_sequence: [] } },
        42
      )
    ).toBe(true)
  })

  it('match_finished（用户频道广播，无 match_id 匹配要求）→ true', () => {
    expect(
      isMatchWsEvent({ event: 'match_finished', data: { match_id: 42, final_score: '11:7' } }, 42)
    ).toBe(true)
  })

  it('match_finished 但属于其他比赛 → false（data.match_id 不匹配）', () => {
    expect(
      isMatchWsEvent({ event: 'match_finished', data: { match_id: 99, final_score: '11:7' } }, 42)
    ).toBe(false)
  })

  it('连接控制消息（connected / subscribed / pong）→ false', () => {
    expect(isMatchWsEvent({ event: 'connected', data: { user_id: 1 } }, 42)).toBe(false)
    expect(isMatchWsEvent({ event: 'subscribed', data: { match_id: 42 } }, 42)).toBe(false)
    expect(isMatchWsEvent({ event: 'pong', data: { token_expired: false } }, 42)).toBe(false)
  })

  it('无 event 字段 / 非 JSON 消息 → false', () => {
    expect(isMatchWsEvent({ raw: 'text-frame' }, 42)).toBe(false)
    expect(isMatchWsEvent({} as any, 42)).toBe(false)
  })

  it('MATCH_WS_EVENTS 恰为 score_update / sync_match / match_finished', () => {
    expect([...MATCH_WS_EVENTS]).toEqual(['score_update', 'sync_match', 'match_finished'])
  })
})
