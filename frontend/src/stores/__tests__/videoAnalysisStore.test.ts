/**
 * videoAnalysisStore 单元测试（03-video_analysis/frontend.md §3）
 * - 上传 phase 状态机（uploading → confirming → creating_task → queued）
 * - setUploadProgress / applyWsProgress（0.0-1.0 → 百分比 + task_id 守卫）
 * - 分页 fetch/append（page=1 覆盖 / page>1 追加）
 * - 反馈闭环（submitFeedback → feedbackSubmitted + 反馈历史刷新）
 */
import * as videoApi from '@/services/videoAnalysis'
import { useVideoAnalysisStore, type ReportDetail } from '@/stores/videoAnalysisStore'
import type { UploadTokenResult, TaskDetailResult, ReportListItem } from '@/services/videoAnalysis'

jest.mock('@/services/videoAnalysis', () => ({
  __esModule: true,
  getUploadToken: jest.fn(),
  confirmUpload: jest.fn(),
  createTask: jest.fn(),
  listTasks: jest.fn(),
  getTaskDetail: jest.fn(),
  getReportDetail: jest.fn(),
  listReports: jest.fn(),
  submitFeedback: jest.fn(),
  getFeedbacks: jest.fn(),
  getAnnotatedVideo: jest.fn(),
  createShare: jest.fn(),
}))

const api = videoApi as jest.Mocked<typeof videoApi>
const store = useVideoAnalysisStore

const TOKEN: UploadTokenResult = {
  file_id: 9,
  oss_key: 'videos/1/abc.mp4',
  sts_credentials: {
    access_key_id: 'mock_ak',
    access_key_secret: 'mock_sk',
    security_token: 'mock_token',
    expiration: '2026-11-05T00:00:00Z',
    bucket: 'mock-bucket',
    endpoint: 'http://localhost:3000/mock-oss',
  },
  upload_url: 'http://localhost:3000/mock-oss/videos/1/abc.mp4',
  expire_at: '2026-11-05T00:00:00Z',
}

const DETAIL: TaskDetailResult = {
  task_id: 42,
  task_uuid: 'uuid-42',
  status: 'processing',
  current_step: 3,
  total_steps: 10,
  step_name: '球体检测中',
  progress: 0.32,
  estimated_remaining_seconds: 120,
  error_message: null,
  created_at: '2026-11-04T09:00:00',
  report_id: null,
}

const REPORT: ReportDetail = {
  id: 7,
  task_id: 42,
  task_uuid: 'uuid-42',
  created_at: '2026-11-04T09:10:00',
  is_llm_generated: true,
  is_readonly: false,
  result_data: {
    rally_analysis: { total_rallies: 24, avg_rally_length: 5.2, max_rally_length: 12 },
    landing_points: {
      nine_grid: [
        [3, 1, 0],
        [2, 5, 1],
        [0, 2, 4],
      ],
      distribution: { forehand: 0.6, backhand: 0.3, middle: 0.1 },
    },
    technique_stats: { forehand_drive: 10, backhand_drive: 5, serve: 3 },
  },
  report_text: {
    summary: '正手进攻积极，落点集中',
    issues: ['反手位防守薄弱'],
    suggestions: ['加强反手拨球训练'],
  },
  annotated_video_url: 'http://cdn/annotated.mp4',
  cover_image_url: 'http://cdn/cover.jpg',
  report_images: null,
}

function resetStore() {
  store.setState({
    uploadPhase: 'idle',
    uploadProgress: 0,
    currentTaskId: null,
    taskDetail: null,
    tasks: [],
    tasksTotal: 0,
    reportDetail: null,
    reports: [],
    reportsTotal: 0,
    feedbackSubmitted: false,
    feedbackHistory: [],
    feedbackHistoryTotal: 0,
    feedbackHistoryLoading: false,
  })
  jest.clearAllMocks()
}

describe('videoAnalysisStore 上传 phase 状态机', () => {
  beforeEach(resetStore)

  it('getUploadToken：置 uploading + progress=0 并返回凭证', async () => {
    api.getUploadToken.mockResolvedValue({ data: { data: TOKEN } } as any)

    const result = await store.getState().getUploadToken('abc.mp4', 1048576)

    expect(result).toEqual(TOKEN)
    expect(store.getState().uploadPhase).toBe('uploading')
    expect(store.getState().uploadProgress).toBe(0)
  })

  it('setUploadProgress：百分比钳制 0-100', () => {
    store.getState().setUploadProgress(46.7)
    expect(store.getState().uploadProgress).toBe(47)
    store.getState().setUploadProgress(150)
    expect(store.getState().uploadProgress).toBe(100)
    store.getState().setUploadProgress(-5)
    expect(store.getState().uploadProgress).toBe(0)
  })

  it('confirmUpload：置 confirming', async () => {
    api.confirmUpload.mockResolvedValue({ data: { data: { file_id: 9 } } } as any)
    await store.getState().confirmUpload(9)
    expect(store.getState().uploadPhase).toBe('confirming')
  })

  it('createTask：置 creating_task → queued + currentTaskId（int，FS3-P3）', async () => {
    api.createTask.mockResolvedValue({
      data: { data: { task_id: 42, task_uuid: 'uuid-42', status: 'queued', estimated_wait_minutes: 3 } },
    } as any)

    const result = await store.getState().createTask(9, 'videos/1/abc.mp4')

    expect(result.task_id).toBe(42)
    expect(store.getState().currentTaskId).toBe(42)
    expect(store.getState().uploadPhase).toBe('queued')
  })

  it('fetchTaskDetail：写 taskDetail + phase 联动 status', async () => {
    api.getTaskDetail.mockResolvedValue({ data: { data: DETAIL } } as any)

    await store.getState().fetchTaskDetail(42)

    expect(store.getState().taskDetail).toEqual(DETAIL)
    expect(store.getState().uploadPhase).toBe('processing')
  })

  it('resetUpload：清空上传态', () => {
    store.setState({ uploadPhase: 'failed', uploadProgress: 88, currentTaskId: 42, taskDetail: DETAIL })
    store.getState().resetUpload()
    const s = store.getState()
    expect(s.uploadPhase).toBe('idle')
    expect(s.uploadProgress).toBe(0)
    expect(s.currentTaskId).toBeNull()
    expect(s.taskDetail).toBeNull()
  })
})

describe('videoAnalysisStore.applyWsProgress（analysis_progress 乐观更新）', () => {
  beforeEach(resetStore)

  it('匹配 task_id：0.32 更新 progress（0.0-1.0 语义，不换算）', () => {
    store.setState({ taskDetail: { ...DETAIL } })
    store.getState().applyWsProgress(42, 0.45)
    expect(store.getState().taskDetail?.progress).toBe(0.45)
  })

  it('越界钳制 0-1', () => {
    store.setState({ taskDetail: { ...DETAIL } })
    store.getState().applyWsProgress(42, 1.5)
    expect(store.getState().taskDetail?.progress).toBe(1)
    store.getState().applyWsProgress(42, -1)
    expect(store.getState().taskDetail?.progress).toBe(0)
  })

  it('task_id 不匹配时忽略（多任务事件防护）', () => {
    store.setState({ taskDetail: { ...DETAIL } })
    store.getState().applyWsProgress(99, 0.9)
    expect(store.getState().taskDetail?.progress).toBe(0.32)
  })

  it('无 taskDetail 时安全返回', () => {
    expect(() => store.getState().applyWsProgress(42, 0.5)).not.toThrow()
  })
})

describe('videoAnalysisStore 报告/反馈', () => {
  beforeEach(resetStore)

  it('fetchReportDetail：写 reportDetail 且 feedbackSubmitted 复位', async () => {
    store.setState({ feedbackSubmitted: true })
    api.getReportDetail.mockResolvedValue({ data: { data: REPORT } } as any)

    await store.getState().fetchReportDetail(7)

    expect(store.getState().reportDetail).toEqual(REPORT)
    expect(store.getState().feedbackSubmitted).toBe(false)
  })

  it('appendReports：page=1 覆盖式写入', async () => {
    const p1: ReportListItem[] = [
      { id: 1, task_id: 42, created_at: '2026-11-01', is_llm_generated: true, cover_image_url: null, report_summary: 'a' },
    ]
    store.setState({ reports: p1, reportsTotal: 3 })
    api.listReports.mockResolvedValue({
      data: { data: { total: 5, page: 1, page_size: 20, items: [...p1, { id: 2, task_id: 43, created_at: '2026-11-02', is_llm_generated: false, cover_image_url: null, report_summary: 'b' }] } },
    } as any)

    await store.getState().appendReports(1, 20)

    expect(store.getState().reports).toHaveLength(2)
    expect(store.getState().reportsTotal).toBe(5)
  })

  it('appendReports：page>1 追加模式（上拉加载更多）', async () => {
    const p1: ReportListItem[] = [
      { id: 1, task_id: 42, created_at: '2026-11-01', is_llm_generated: true, cover_image_url: null, report_summary: 'a' },
    ]
    const p2: ReportListItem[] = [
      { id: 2, task_id: 43, created_at: '2026-11-02', is_llm_generated: false, cover_image_url: null, report_summary: 'b' },
    ]
    store.setState({ reports: p1, reportsTotal: 2 })
    api.listReports.mockResolvedValue({
      data: { data: { total: 2, page: 2, page_size: 1, items: p2 } },
    } as any)

    await store.getState().appendReports(2, 1)

    expect(store.getState().reports).toEqual([...p1, ...p2])
  })

  it('submitFeedback：置 feedbackSubmitted 并刷新反馈历史（数据飞轮闭环）', async () => {
    api.submitFeedback.mockResolvedValue({ data: { data: { id: 5 } } } as any)
    api.getFeedbacks.mockResolvedValue({
      data: {
        data: {
          total: 1,
          page: 1,
          page_size: 20,
          items: [{ id: 5, report_id: 7, is_correct: false, comment: '落点不准', created_at: '2026-11-04T10:00:00' }],
        },
      },
    } as any)

    await store.getState().submitFeedback(7, false, '落点不准')

    expect(api.submitFeedback).toHaveBeenCalledWith(7, false, '落点不准')
    expect(api.getFeedbacks).toHaveBeenCalledWith(7, 1, 20)
    expect(store.getState().feedbackSubmitted).toBe(true)
    expect(store.getState().feedbackHistory).toHaveLength(1)
    expect(store.getState().feedbackHistoryLoading).toBe(false)
  })

  it('createShare：返回 share_url + card_image_url（FS3-P3 字段名）', async () => {
    api.createShare.mockResolvedValue({
      data: { data: { share_url: 'http://api/share/tok', card_image_url: 'http://cdn/cover.jpg', expire_at: '2026-11-12T00:00:00' } },
    } as any)

    const result = await store.getState().createShare(7)

    expect(result.share_url).toBe('http://api/share/tok')
    expect(result.card_image_url).toBe('http://cdn/cover.jpg')
  })
})
