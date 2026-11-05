/**
 * video_analysis 模块 API Service（03-video_analysis/frontend.md §2）
 * 端点与后端 app/api/v1/video_analysis/router.py 逐字一致（11 个）
 *
 * FS3-P3 契约修正（与设计样例的差异，以后端为准）：
 * - task_id 为 int（router 路径参数 task_id: int；设计样例 string 为 v0 口径）
 * - createShare 响应字段为 card_image_url（设计样例 share_card_url 为 v0 口径）
 */
import request from './request'

/** 上传凭证响应（后端 VideoAnalysisService.get_upload_token） */
export interface UploadTokenResult {
  file_id: number
  oss_key: string
  sts_credentials: {
    access_key_id: string
    access_key_secret: string
    security_token: string
    expiration: string
    bucket: string
    endpoint: string
  }
  upload_url: string
  expire_at: string
}

/** 创建任务响应（后端 VideoAnalysisService.create_task） */
export interface CreateTaskResult {
  task_id: number
  task_uuid: string
  status: string
  estimated_wait_minutes: number
}

/** 任务列表项（后端 list_tasks items） */
export interface TaskListItem {
  task_id: number
  task_uuid: string
  status: string
  current_step: number | null
  total_steps: number
  progress: number
  created_at: string | null
  report_id: number | null
  cover_image_url: string | null
}

/** 任务详情（后端 get_task_detail） */
export interface TaskDetailResult {
  task_id: number
  task_uuid: string
  status: string
  current_step: number | null
  total_steps: number
  step_name: string | null
  progress: number
  estimated_remaining_seconds: number | null
  error_message: string | null
  created_at: string | null
  report_id: number | null
}

/** 报告列表项（后端 list_reports items） */
export interface ReportListItem {
  id: number
  task_id: number
  created_at: string | null
  is_llm_generated: boolean
  cover_image_url: string | null
  report_summary: string | null
}

/** 分页响应（后端统一形态） */
export interface PagedResult<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

/**
 * 获取 OSS STS 直传凭证 + 对象 Key。
 * @param filename - 文件名（mp4/mov）
 * @param fileSize - 文件大小（字节，1MB ≤ size ≤ 500MB）
 */
export function getUploadToken(filename: string, fileSize: number) {
  return request.post<UploadTokenResult>('/video-analysis/upload-token', {
    filename,
    file_size: fileSize,
  })
}

/**
 * 上传完成确认（后端 HEAD Object 校验）。
 * @param fileId - 文件记录 ID
 */
export function confirmUpload(fileId: number) {
  return request.post('/video-analysis/upload-complete', { file_id: fileId })
}

/**
 * 创建分析任务（免费 3 次/天，会员不限）。
 * @param fileId - 文件记录 ID
 * @param ossKey - OSS 对象 Key（须与 file_record 一致，服务端二次校验）
 */
export function createTask(fileId: number, ossKey: string) {
  return request.post<CreateTaskResult>('/video-analysis/tasks', {
    file_id: fileId,
    oss_key: ossKey,
  })
}

/**
 * 任务列表（分页）。
 * @param params - status / page / page_size
 */
export function listTasks(params?: { status?: string; page?: number; page_size?: number }) {
  return request.get<PagedResult<TaskListItem>>('/video-analysis/tasks', {
    page: 1,
    page_size: 20,
    ...params,
  })
}

/**
 * 任务详情 + 进度（断线 REST 轮询回退用）。
 * @param taskId - 任务 ID（int）
 */
export function getTaskDetail(taskId: number) {
  return request.get<TaskDetailResult>(`/video-analysis/tasks/${taskId}`)
}

/**
 * 分析报告详情。
 * @param reportId - 报告 ID
 */
export function getReportDetail(reportId: number) {
  return request.get(`/video-analysis/reports/${reportId}`)
}

/**
 * 报告列表（分页）。
 */
export function listReports(params?: { page?: number; page_size?: number }) {
  return request.get<PagedResult<ReportListItem>>('/video-analysis/reports', {
    page: 1,
    page_size: 20,
    ...params,
  })
}

/**
 * 提交反馈（对/不对标记，可覆盖）。
 * @param reportId - 报告 ID
 * @param isCorrect - 分析结果是否准确
 * @param comment - 补充说明（不正确时建议填写）
 */
export function submitFeedback(reportId: number, isCorrect: boolean, comment?: string) {
  return request.post(`/video-analysis/reports/${reportId}/feedback`, {
    is_correct: isCorrect,
    comment,
  })
}

/**
 * 反馈历史列表（API §3.7 跨模块端点，数据飞轮闭环）。
 * @param reportId - 报告 ID
 * @param page - 页码（默认 1）
 * @param pageSize - 每页条数（默认 20，最大 50）
 */
export function getFeedbacks(reportId: number, page: number = 1, pageSize: number = 20) {
  return request.get(`/video-analysis/reports/${reportId}/feedbacks`, {
    page,
    page_size: pageSize,
  })
}

/**
 * 标注视频 CDN URL。
 * @param reportId - 报告 ID
 */
export function getAnnotatedVideo(reportId: number) {
  return request.get(`/video-analysis/reports/${reportId}/annotated-video`)
}

/**
 * 生成分享 Token + 链接（7 天有效，每天限 5 次）。
 * 响应：{ share_url, card_image_url, expire_at }（card_image_url 为 FS3-P3 修正字段名）
 */
export function createShare(reportId: number) {
  return request.post<{ share_url: string; card_image_url: string | null; expire_at: string }>(
    `/video-analysis/reports/${reportId}/share`
  )
}
