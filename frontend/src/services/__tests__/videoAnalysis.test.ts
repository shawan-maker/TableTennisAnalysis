/**
 * videoAnalysis Service 契约测试（03-video_analysis/frontend.md §2）
 * 断言每个函数的 HTTP 方法 + URL + 参数与后端 app/api/v1/video_analysis/router.py 逐字一致
 */
import request from '@/services/request'
import * as videoApi from '@/services/videoAnalysis'

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

describe('services/videoAnalysis 契约（11 端点）', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('getUploadToken → POST /video-analysis/upload-token（filename + file_size）', async () => {
    await videoApi.getUploadToken('match.mp4', 1024 * 1024)
    expect(post).toHaveBeenCalledWith('/video-analysis/upload-token', {
      filename: 'match.mp4',
      file_size: 1048576,
    })
  })

  it('confirmUpload → POST /video-analysis/upload-complete（file_id）', async () => {
    await videoApi.confirmUpload(9)
    expect(post).toHaveBeenCalledWith('/video-analysis/upload-complete', { file_id: 9 })
  })

  it('createTask → POST /video-analysis/tasks（file_id + oss_key）', async () => {
    await videoApi.createTask(9, 'videos/1/abc.mp4')
    expect(post).toHaveBeenCalledWith('/video-analysis/tasks', {
      file_id: 9,
      oss_key: 'videos/1/abc.mp4',
    })
  })

  it('listTasks → GET /video-analysis/tasks（缺省补 page=1/page_size=20）', async () => {
    await videoApi.listTasks()
    expect(get).toHaveBeenCalledWith('/video-analysis/tasks', { page: 1, page_size: 20 })
  })

  it('listTasks → status 筛选 + 分页透传', async () => {
    await videoApi.listTasks({ status: 'processing', page: 2, page_size: 50 })
    expect(get).toHaveBeenCalledWith('/video-analysis/tasks', {
      page: 2,
      page_size: 50,
      status: 'processing',
    })
  })

  it('getTaskDetail → GET /video-analysis/tasks/{task_id}（int 路径参数，FS3-P3）', async () => {
    await videoApi.getTaskDetail(42)
    expect(get).toHaveBeenCalledWith('/video-analysis/tasks/42')
  })

  it('getReportDetail → GET /video-analysis/reports/{report_id}', async () => {
    await videoApi.getReportDetail(7)
    expect(get).toHaveBeenCalledWith('/video-analysis/reports/7')
  })

  it('listReports → GET /video-analysis/reports（分页）', async () => {
    await videoApi.listReports({ page: 3, page_size: 10 })
    expect(get).toHaveBeenCalledWith('/video-analysis/reports', { page: 3, page_size: 10 })
  })

  it('submitFeedback → POST /video-analysis/reports/{id}/feedback（is_correct + comment）', async () => {
    await videoApi.submitFeedback(7, false, '落点不准')
    expect(post).toHaveBeenCalledWith('/video-analysis/reports/7/feedback', {
      is_correct: false,
      comment: '落点不准',
    })
  })

  it('getFeedbacks → GET /video-analysis/reports/{id}/feedbacks（page + page_size）', async () => {
    await videoApi.getFeedbacks(7, 2, 50)
    expect(get).toHaveBeenCalledWith('/video-analysis/reports/7/feedbacks', {
      page: 2,
      page_size: 50,
    })
  })

  it('getAnnotatedVideo → GET /video-analysis/reports/{id}/annotated-video', async () => {
    await videoApi.getAnnotatedVideo(7)
    expect(get).toHaveBeenCalledWith('/video-analysis/reports/7/annotated-video')
  })

  it('createShare → POST /video-analysis/reports/{id}/share', async () => {
    await videoApi.createShare(7)
    expect(post).toHaveBeenCalledWith('/video-analysis/reports/7/share')
  })
})
