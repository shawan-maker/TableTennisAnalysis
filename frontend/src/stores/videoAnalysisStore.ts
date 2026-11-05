/**
 * video_analysis 状态管理（03-video_analysis/frontend.md §3）
 * FS3-P3 契约修正（以后端为准）：
 * - task_id 为 number（设计样例 string 为 v0 口径）
 * - createShare 响应 card_image_url（设计样例 share_card_url 为 v0 口径）
 * - WS analysis_progress payload.progress 为 0.0-1.0 浮点（后端 _calc_progress，
 *   设计注记 R18-P3-17 所写 0~100 为口径偏差），applyWsProgress 统一 ×100 转百分比
 */
import { create } from 'zustand'
import * as videoApi from '@/services/videoAnalysis'
import type {
  UploadTokenResult,
  CreateTaskResult,
  TaskListItem,
  TaskDetailResult,
  ReportListItem,
} from '@/services/videoAnalysis'

export type { UploadTokenResult, CreateTaskResult, TaskListItem, TaskDetailResult, ReportListItem }

export interface ReportDetail {
  id: number
  task_id: number
  task_uuid: string | null
  created_at: string | null
  is_llm_generated: boolean
  /** 会员到期权限降级标记（R15，Redis downgrade:report:readonly:{uid}）——展示层 FS6 会员 Sprint 消费 */
  is_readonly: boolean
  result_data: {
    video_info?: { duration_sec: number; fps: number; resolution: string }
    rally_analysis?: { total_rallies: number; avg_rally_length: number; max_rally_length: number }
    landing_points?: {
      nine_grid: number[][]
      distribution: { forehand: number; backhand: number; middle: number }
    }
    technique_stats?: Record<string, number>
    ball_speed?: { avg_speed_mps: number; max_speed_mps: number; speed_range: [number, number] }
    score_analysis?: { final_score: string; key_points: any[] }
  } | null
  report_text: {
    summary: string
    issues: string[]
    suggestions: string[]
  } | null
  annotated_video_url: string | null
  cover_image_url: string | null
  report_images: { heatmap: string; technique_chart: string } | null
}

/** 反馈历史条目（API §3.7 GET /video-analysis/reports/{report_id}/feedbacks） */
export interface FeedbackHistoryItem {
  id: number
  report_id: number
  is_correct: boolean
  comment: string | null
  created_at: string
}

/** 上传/分析阶段（与后端 task.status 对齐：queued/processing/completed/failed/cancelled） */
type UploadPhase =
  | 'idle'
  | 'recording'
  | 'uploading'
  | 'confirming'
  | 'creating_task'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'

interface VideoAnalysisState {
  // 上传状态
  uploadPhase: UploadPhase
  uploadProgress: number
  currentTaskId: number | null
  taskDetail: TaskDetailResult | null

  // 任务列表
  tasks: TaskListItem[]
  tasksTotal: number

  // 报告
  reportDetail: ReportDetail | null
  reports: ReportListItem[]
  reportsTotal: number

  // 反馈状态
  feedbackSubmitted: boolean

  // 反馈历史（数据飞轮闭环）
  feedbackHistory: FeedbackHistoryItem[]
  feedbackHistoryTotal: number
  feedbackHistoryLoading: boolean

  // Actions
  getUploadToken: (
    filename: string,
    fileSize: number
  ) => Promise<UploadTokenResult>
  setUploadProgress: (progress: number) => void
  confirmUpload: (fileId: number) => Promise<void>
  createTask: (fileId: number, ossKey: string) => Promise<CreateTaskResult>
  fetchTaskDetail: (taskId: number) => Promise<void>
  fetchTasks: (page?: number, pageSize?: number) => Promise<void>
  fetchReportDetail: (reportId: number) => Promise<void>
  fetchReports: (page?: number, pageSize?: number) => Promise<void>
  appendReports: (page?: number, pageSize?: number) => Promise<void>
  submitFeedback: (reportId: number, isCorrect: boolean, comment?: string) => Promise<void>
  fetchFeedbackHistory: (reportId: number, page?: number, pageSize?: number) => Promise<void>
  createShare: (
    reportId: number
  ) => Promise<{ share_url: string; card_image_url: string | null; expire_at: string }>
  applyWsProgress: (taskId: number, progress: number) => void
  resetUpload: () => void
}

export const useVideoAnalysisStore = create<VideoAnalysisState>((set, get) => ({
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

  getUploadToken: async (filename, fileSize) => {
    const res = await videoApi.getUploadToken(filename, fileSize)
    const data = res.data.data
    set({ uploadPhase: 'uploading', uploadProgress: 0 })
    return data
  },

  setUploadProgress: (progress) => {
    set({ uploadProgress: Math.min(100, Math.max(0, Math.round(progress))) })
  },

  confirmUpload: async (fileId) => {
    set({ uploadPhase: 'confirming' })
    await videoApi.confirmUpload(fileId)
  },

  createTask: async (fileId, ossKey) => {
    set({ uploadPhase: 'creating_task' })
    const res = await videoApi.createTask(fileId, ossKey)
    const data = res.data.data
    set({
      currentTaskId: data.task_id,
      uploadPhase: data.status as UploadPhase,
    })
    return data
  },

  fetchTaskDetail: async (taskId) => {
    const res = await videoApi.getTaskDetail(taskId)
    const data = res.data.data
    set({
      taskDetail: data,
      uploadPhase: data.status as UploadPhase,
    })
  },

  fetchTasks: async (page = 1, pageSize = 20) => {
    const res = await videoApi.listTasks({ page, page_size: pageSize })
    const data = res.data.data
    set({ tasks: data.items, tasksTotal: data.total })
  },

  fetchReportDetail: async (reportId) => {
    set({ feedbackSubmitted: false })
    const res = await videoApi.getReportDetail(reportId)
    set({ reportDetail: res.data.data })
  },

  fetchReports: async (page = 1, pageSize = 20) => {
    const res = await videoApi.listReports({ page, page_size: pageSize })
    const data = res.data.data
    set({ reports: data.items, reportsTotal: data.total })
  },

  appendReports: async (page = 1, pageSize = 20) => {
    const res = await videoApi.listReports({ page, page_size: pageSize })
    const data = res.data.data
    // 追加模式（上拉加载更多）；首页（page=1）覆盖，避免筛选/刷新残留
    set((state) => ({
      reports: page === 1 ? data.items : [...state.reports, ...data.items],
      reportsTotal: data.total,
    }))
  },

  submitFeedback: async (reportId, isCorrect, comment) => {
    await videoApi.submitFeedback(reportId, isCorrect, comment)
    set({ feedbackSubmitted: true })
    // 提交成功后刷新反馈历史，保持数据飞轮闭环
    await get().fetchFeedbackHistory(reportId)
  },

  fetchFeedbackHistory: async (reportId, page = 1, pageSize = 20) => {
    set({ feedbackHistoryLoading: true })
    try {
      const res = await videoApi.getFeedbacks(reportId, page, pageSize)
      const data = res.data.data
      set({
        feedbackHistory: data.items,
        feedbackHistoryTotal: data.total,
      })
    } finally {
      set({ feedbackHistoryLoading: false })
    }
  },

  createShare: async (reportId) => {
    const res = await videoApi.createShare(reportId)
    return res.data.data
  },

  /**
   * WS analysis_progress 乐观更新（0.0-1.0 → 0-100 百分比）。
   * 不变更 phase（由 fetchTaskDetail 对账路径统一驱动，避免 WS 丢包时状态卡死）。
   */
  applyWsProgress: (taskId, progress) => {
    const detail = get().taskDetail
    if (detail && detail.task_id === taskId) {
      set({
        taskDetail: {
          ...detail,
          progress: Math.min(1, Math.max(0, progress)),
        },
      })
    }
  },

  resetUpload: () => {
    set({
      uploadPhase: 'idle',
      uploadProgress: 0,
      currentTaskId: null,
      taskDetail: null,
    })
  },
}))
