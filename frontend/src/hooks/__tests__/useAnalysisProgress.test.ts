/**
 * useAnalysisProgress 协议测试（03-video_analysis/frontend.md §8）
 * 断言事件归属判定与后端 app/ai_pipeline/progress.py push_ws_message payload 契约一致
 */
import { isAnalysisWsEvent, ANALYSIS_WS_EVENTS } from '@/hooks/useAnalysisProgress'

jest.mock('@/services/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { data: {} } }),
    post: jest.fn().mockResolvedValue({ data: { data: {} } }),
    patch: jest.fn().mockResolvedValue({ data: { data: {} } }),
    delete: jest.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

describe('ANALYSIS_WS_EVENTS 常量', () => {
  it('恰为 progress / complete / failed 三个事件', () => {
    expect([...ANALYSIS_WS_EVENTS]).toEqual(['analysis_progress', 'analysis_complete', 'analysis_failed'])
  })
})

describe('isAnalysisWsEvent（事件名 + payload.task_id 双匹配）', () => {
  it('analysis_progress 且 task_id 匹配 → true（payload 含 step/step_name/progress）', () => {
    expect(
      isAnalysisWsEvent(
        { event: 'analysis_progress', data: { task_id: 42, step: 3, step_name: '球体检测中', progress: 0.32 } },
        42
      )
    ).toBe(true)
  })

  it('analysis_progress 但 task_id 不匹配 → false（多任务事件防护）', () => {
    expect(
      isAnalysisWsEvent({ event: 'analysis_progress', data: { task_id: 99, progress: 0.5 } }, 42)
    ).toBe(false)
  })

  it('analysis_complete 且 task_id 匹配 → true（payload 含 report_id）', () => {
    expect(
      isAnalysisWsEvent({ event: 'analysis_complete', data: { task_id: 42, report_id: 7 } }, 42)
    ).toBe(true)
  })

  it('analysis_failed 且 task_id 匹配 → true（payload 含 step/error）', () => {
    expect(
      isAnalysisWsEvent({ event: 'analysis_failed', data: { task_id: 42, step: 3, error: 'x' } }, 42)
    ).toBe(true)
  })

  it('非本域事件（score_update/sync_match/match_finished/connected）→ false', () => {
    expect(isAnalysisWsEvent({ event: 'score_update', data: { match_id: 42 } }, 42)).toBe(false)
    expect(isAnalysisWsEvent({ event: 'connected', data: { user_id: 1 } }, 42)).toBe(false)
    expect(isAnalysisWsEvent({ event: 'notification', data: { task_id: 42 } }, 42)).toBe(false)
  })

  it('无 event / 无 data → false', () => {
    expect(isAnalysisWsEvent({ raw: 'x' }, 42)).toBe(false)
    expect(isAnalysisWsEvent({ event: 'analysis_progress' }, 42)).toBe(false)
    expect(isAnalysisWsEvent({} as any, 42)).toBe(false)
  })
})
