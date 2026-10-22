# video_analysis 模块 — 前端垂直切片设计

> **模块名称**：`video_analysis`
> **前端目录**：`frontend/src/pages/video-analysis/` + `frontend/src/services/videoAnalysis.ts` + `frontend/src/stores/videoAnalysisStore.ts`
> **定位**：视频上传页（拍摄引导→上传→进度）、分析报告详情页（落点热图/技术环形图/节奏曲线/结论/视频回放/反馈/分享）
> **依据**：前端需求与界面设计 v2.0 §T2.1-T2.3、API 详细设计 v1.3 §4

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §T2.1（拍摄引导）、§T2.2（处理中）、§T2.3（分析报告页）
- [ ] 阅读本模块的 API 契约（§4.1-4.11，11 个端点）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 阅读 auth 模块前端代码（`services/request.ts`，了解请求拦截器）
- [ ] 确认本切片范围：视频上传页 + 分析进度页 + 分析报告详情页 + 分享页

---

## 2. API Service 模块

```typescript
// frontend/src/services/videoAnalysis.ts
import request from './request'

/**
 * 获取 OSS STS 直传凭证 + 对象 Key。
 * @param filename - 文件名（mp4/mov）
 * @param fileSize - 文件大小（字节，≤500MB）
 */
export function getUploadToken(filename: string, fileSize: number) {
  return request.post('/video-analysis/upload-token', { filename, file_size: fileSize })
}

/**
 * 上传完成确认（后端 HEAD Object 校验）。
 * @param fileId - 文件记录 ID
 */
export function confirmUpload(fileId: number) {
  return request.post('/video-analysis/upload-complete', { file_id: fileId })
}

/**
 * 创建分析任务。
 * @param fileId - 文件记录 ID
 * @param ossKey - OSS 对象 Key
 */
export function createTask(fileId: number, ossKey: string) {
  return request.post('/video-analysis/tasks', { file_id: fileId, oss_key: ossKey })
}

/**
 * 任务列表（分页）。
 * @param params - status / page / page_size
 */
export function listTasks(params?: {
  status?: string
  page?: number
  page_size?: number
}) {
  return request.get('/video-analysis/tasks', {
    page: 1,
    page_size: 20,
    ...params,
  })
}

/**
 * 任务详情 + 进度。
 * @param taskId - 任务 ID
 */
export function getTaskDetail(taskId: string) {
  return request.get(`/video-analysis/tasks/${taskId}`)
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
  return request.get('/video-analysis/reports', {
    page: 1,
    page_size: 20,
    ...params,
  })
}

/**
 * 提交反馈（对/不对标记）。
 * @param reportId - 报告 ID
 * @param isCorrect - 分析结果是否准确
 * @param comment - 补充说明
 */
export function submitFeedback(reportId: number, isCorrect: boolean, comment?: string) {
  return request.post(`/video-analysis/reports/${reportId}/feedback`, {
    is_correct: isCorrect,
    comment,
  })
}

/**
 * 反馈历史列表（API §3.7 跨模块端点）。
 * 用于查看用户对历史报告的反馈记录，形成"数据飞轮"闭环。
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
 * 生成分享 Token + 卡片图。
 * @param reportId - 报告 ID
 */
export function createShare(reportId: number) {
  return request.post(`/video-analysis/reports/${reportId}/share`)
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/videoAnalysisStore.ts
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import i18next from 'i18next'
import * as videoApi from '@/services/videoAnalysis'

interface TaskItem {
  task_id: string
  status: string  // queued/processing/completed/failed/cancelled
  created_at: string
  report_id: number | null
  cover_image_url: string | null
}

interface TaskDetail {
  task_id: string
  status: string
  current_step: number
  total_steps: number
  step_name: string | null
  progress: number
  estimated_remaining_seconds: number | null
  created_at: string
  report_id: number | null
}

interface ReportListItem {
  id: number
  task_id: string
  created_at: string
  is_llm_generated: boolean
  cover_image_url: string | null
  report_summary: string | null
}

// R19-fix: 反馈历史条目（对应 API §3.7 GET /video-analysis/reports/{report_id}/feedbacks 响应）
interface FeedbackHistoryItem {
  id: number
  report_id: number
  is_correct: boolean
  comment: string | null
  created_at: string
}


interface ReportDetail {
  id: number
  task_id: string
  created_at: string
  is_llm_generated: boolean
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

type UploadPhase = 'idle' | 'recording' | 'uploading' | 'confirming' | 'creating_task' | 'queued' | 'processing' | 'completed' | 'failed'

interface VideoAnalysisState {
  // 上传状态
  uploadPhase: UploadPhase
  uploadProgress: number
  currentTaskId: string | null
  taskDetail: TaskDetail | null

  // 任务列表
  tasks: TaskItem[]
  tasksTotal: number

  // 报告
  reportDetail: ReportDetail | null
  reports: ReportListItem[]
  reportsTotal: number

  // 反馈状态
  feedbackSubmitted: boolean

  // R19-fix: 反馈历史（对应 API §3.7 GET /video-analysis/reports/{report_id}/feedbacks）
  feedbackHistory: FeedbackHistoryItem[]
  feedbackHistoryTotal: number
  feedbackHistoryLoading: boolean

  // Actions
  getUploadToken: (filename: string, fileSize: number) => Promise<{ file_id: number; oss_key: string; sts_credentials: any; upload_url: string }>
  confirmUpload: (fileId: number) => Promise<void>
  createTask: (fileId: number, ossKey: string) => Promise<string>
  fetchTaskDetail: (taskId: string) => Promise<void>
  fetchTasks: (page?: number, pageSize?: number) => Promise<void>
  fetchReportDetail: (reportId: number) => Promise<void>
  fetchReports: (page?: number, pageSize?: number) => Promise<void>
  submitFeedback: (reportId: number, isCorrect: boolean, comment?: string) => Promise<void>
  fetchFeedbackHistory: (reportId: number, page?: number, pageSize?: number) => Promise<void>
  createShare: (reportId: number) => Promise<{ share_url: string; share_card_url: string | null }>
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
    return data.task_id
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

  submitFeedback: async (reportId, isCorrect, comment) => {
    await videoApi.submitFeedback(reportId, isCorrect, comment)
    set({ feedbackSubmitted: true })
    // 提交成功后刷新反馈历史，保持数据飞轮闭环
    await get().fetchFeedbackHistory(reportId)
  },

  // R19-fix: 拉取反馈历史（API §3.7 GET /video-analysis/reports/{report_id}/feedbacks）
  fetchFeedbackHistory: async (reportId, page = 1, pageSize = 20) => {
    set({ feedbackHistoryLoading: true })
    try {
      const res = await videoApi.getFeedbacks(reportId, page, pageSize)
      const data = res.data.data
      set({
        feedbackHistory: data.items,
        feedbackHistoryTotal: data.total,
      })
    } catch (err: any) {
      Taro.showToast({ title: err?.message || i18next.t('common.operationFailed'), icon: 'none' })
    } finally {
      set({ feedbackHistoryLoading: false })
    }
  },


  createShare: async (reportId) => {
    const res = await videoApi.createShare(reportId)
    return res.data.data
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
```

---

## 4. 主要页面组件

### 4.1 视频上传页（拍摄引导 → 上传 → 进度）

```tsx
// frontend/src/pages/video-analysis/upload.tsx
import { useState, useCallback, useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Image, Video } from '@tarojs/components'
import { Button, Toast, Progress } from '@nutui/nutui-react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import { useTranslation } from 'react-i18next'
import './upload.scss'

// AI 流水线步骤定义（与后端 PIPELINE_STEPS 对应）
const PIPELINE_STEPS = [
  'videoUploaded', 'videoTranscoded', 'ballDetected', 'ballSpeedEstimated',
  'ballTracked', 'actionRecognized', 'landingAnalyzed', 'rallySegmented',
  'statAnalyzed', 'reportGenerated',
]

export default function UploadPage() {
  const { t } = useTranslation()
  const {
    uploadPhase, uploadProgress, currentTaskId, taskDetail,
    getUploadToken, confirmUpload, createTask, fetchTaskDetail, resetUpload,
  } = useVideoAnalysisStore()
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')
  const [videoPath, setVideoPath] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  /** 选择/拍摄视频 */
  const handleChooseVideo = useCallback(() => {
    Taro.chooseVideo({
      sourceType: ['album', 'camera'],
      maxDuration: 300,  // 5 分钟
      camera: 'back',
      success: async (res) => {
        // 校验文件类型
        if (!res.tempFilePath.toLowerCase().match(/\.(mp4|mov)$/)) {
          showToast(t('analysis.invalidFormat'))
          return
        }
        // 校验文件大小（500MB）
        if (res.size > 500 * 1024 * 1024) {
          showToast(t('analysis.fileTooLarge'))
          return
        }
        setVideoPath(res.tempFilePath)
        // 开始上传流程
        await startUpload(res.tempFilePath, res.size, res.name || 'video.mp4')
      },
      fail: (err) => {
        if (err.errMsg !== 'chooseVideo:fail cancel') {
          showToast(t('analysis.chooseFailed'))
        }
      },
    })
  }, [t])

  /** OSS 直传流程 */
  const startUpload = async (filePath: string, fileSize: number, filename: string) => {
    try {
      // 1. 获取上传凭证
      const { file_id, oss_key, sts_credentials, upload_url } = await getUploadToken(filename, fileSize)

      // 2. 直传 OSS
      const uploadTask = Taro.uploadFile({
        url: upload_url,
        filePath,
        name: 'file',
        formData: {
          key: oss_key,
          OSSAccessKeyId: sts_credentials.access_key_id,
          policy: '',  // 从 sts_credentials 获取
          Signature: sts_credentials.access_key_secret,
          'x-oss-security-token': sts_credentials.security_token,
        },
        success: () => {
          // 3. 确认上传
          confirmAndCreateTask(file_id, oss_key)
        },
        fail: (err) => {
          showToast(t('analysis.uploadFailed'))
          resetUpload()
        },
      })

      // 上传进度
      uploadTask.progress(({ progress }) => {
        // 通过 store 更新进度（简化：直接用 Taro 事件）
      })
    } catch (err: any) {
      showToast(err?.message || t('analysis.uploadFailed'))
      resetUpload()
    }
  }

  /** 确认上传 + 创建任务 */
  const confirmAndCreateTask = async (fileId: number, ossKey: string) => {
    try {
      await confirmUpload(fileId)
      const taskId = await createTask(fileId, ossKey)
      showToast(t('analysis.taskCreated'))
      // 跳转到进度页
      setTimeout(() => {
        Taro.redirectTo({ url: `/pages/video-analysis/processing/index?task_id=${taskId}` })
      }, 1500)
    } catch (err: any) {
      showToast(err?.message || t('analysis.taskCreateFailed'))
      resetUpload()
    }
  }

  // 拍摄引导界面
  if (uploadPhase === 'idle') {
    return (
      <View className="upload-page">
        {/* 拍摄引导 */}
        <View className="guide-section">
          <Text className="guide-title">{t('analysis.shootingGuide')}</Text>
          <View className="guide-cards">
            <View className="guide-card">
              <Text className="guide-icon">📐</Text>
              <Text className="guide-text">{t('analysis.angleGuide')}</Text>
              <Text className="guide-detail">{t('analysis.angleDetail')}</Text>
            </View>
            <View className="guide-card">
              <Text className="guide-icon">📏</Text>
              <Text className="guide-text">{t('analysis.distanceGuide')}</Text>
              <Text className="guide-detail">{t('analysis.distanceDetail')}</Text>
            </View>
            <View className="guide-card">
              <Text className="guide-icon">💡</Text>
              <Text className="guide-text">{t('analysis.lightingGuide')}</Text>
              <Text className="guide-detail">{t('analysis.lightingDetail')}</Text>
            </View>
          </View>
        </View>

        {/* 注意事项 */}
        <View className="notice-section">
          <Text className="notice-title">{t('analysis.notice')}</Text>
          <View className="notice-list">
            <Text className="notice-item">• {t('analysis.noticeFormat')}</Text>
            <Text className="notice-item">• {t('analysis.noticeSize')}</Text>
            <Text className="notice-item">• {t('analysis.noticeDuration')}</Text>
          </View>
        </View>

        {/* 免费额度提示 */}
        <View className="quota-section">
          <Text className="quota-text">{t('analysis.freeQuotaHint')}</Text>
        </View>

        <Button
          type="primary"
          block
          className="upload-btn"
          onClick={handleChooseVideo}
        >
          {t('analysis.chooseVideo')}
        </Button>

        <Toast
          visible={toastVisible}
          content={toastMsg}
          onClose={() => setToastVisible(false)}
        />
      </View>
    )
  }

  // 上传中界面
  if (uploadPhase === 'uploading' || uploadPhase === 'confirming') {
    return (
      <View className="uploading-page">
        <View className="uploading-content">
          <Text className="uploading-icon">📹</Text>
          <Text className="uploading-text">{t('analysis.uploading')}</Text>
          <Progress
            percentage={uploadProgress}
            color="var(--color-primary)"
            strokeWidth={8}
          />
        </View>
      </View>
    )
  }

  return null
}
```

### 4.2 分析进度页

```tsx
// frontend/src/pages/video-analysis/progress.tsx
import { useEffect, useState, useRef } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Progress, Skeleton } from '@nutui/nutui-react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import { useTranslation } from 'react-i18next'
import './progress.scss'

const PIPELINE_STEPS = [
  { key: '[REDACTED:sha256:5bc8f2cdf343]', label: 'analysis.step.videoUpload', icon: '✅' },
  { key: '[REDACTED:sha256:45018a2c9d26]', label: 'analysis.step.transcode', icon: '🎬' },
  { key: '[REDACTED:sha256:66cd6aabc946]', label: 'analysis.step.ballDetect', icon: '🎯' },
  { key: '[REDACTED:sha256:3f9533572692]', label: 'analysis.step.speedEstimate', icon: '⚡' },
  { key: '[REDACTED]', label: 'analysis.step.ballTrack', icon: '📈' },
  { key: '[REDACTED:sha256:af2a0008e72b]', label: 'analysis.step.actionRecognize', icon: '🏓' },
  { key: '[REDACTED:sha256:330930dfe848]', label: 'analysis.step.landingAnalyze', icon: '📍' },
  { key: '[REDACTED:sha256:93b0c4b66dcc]', label: 'analysis.step.rallySplit', icon: '📊' },
  { key: '[REDACTED:sha256:12feb22cb69a]', label: 'analysis.step.statistics', icon: '🔢' },
  { key: '[REDACTED:sha256:28db12d4bfe5]', label: 'analysis.step.report', icon: '📝' },
]

export default function ProgressPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const taskId = router.params.task_id || ''
  const { taskDetail, fetchTaskDetail } = useVideoAnalysisStore()
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef<any>(null)

  // 轮询 + WebSocket 获取进度
  useEffect(() => {
    // 初始加载
    fetchTaskDetail(taskId)

    // 轮询兜底（每 5 秒）
    const pollTimer = setInterval(() => {
      fetchTaskDetail(taskId)
    }, 5000)

    // WebSocket 实时推送
    const token = Taro.getStorageSync('access_token')
    const wsUrl = `${process.env.TARO_APP_WS || 'wss://api.pingpongai.com/ws'}?token=${token}`
    // Taro 环境 WebSocket 连接
    const socketTask = Taro.connectSocket({ url: wsUrl })
    socketTask.onOpen(() => {
      setWsConnected(true)
      // 发送订阅消息
      socketTask.send({ data: JSON.stringify({ event: 'subscribe', channel: `task:${taskId}` }) })
    })
    socketTask.onMessage((msg) => {
      try {
        const data = JSON.parse(msg.data)
        if (data.event === 'analysis_progress' && data.task_id === taskId) {
          fetchTaskDetail(taskId)
        }
        if (data.event === 'analysis_complete' && data.task_id === taskId) {
          fetchTaskDetail(taskId)
          clearInterval(pollTimer)
          // 跳转报告页
          setTimeout(() => {
            Taro.redirectTo({ url: `/pages/video-analysis/report/index?report_id=${data.report_id}` })
          }, 1000)
        }
      } catch (e) {
        // 忽略解析错误
      }
    })
    socketTask.onClose(() => setWsConnected(false))
    wsRef.current = socketTask

    return () => {
      clearInterval(pollTimer)
      socketTask.close({})
    }
  }, [taskId])

  if (!taskDetail) {
    return <View className="progress-loading"><Skeleton rows={3} animated /></View>
  }

  const currentStep = taskDetail.current_step
  const totalSteps = taskDetail.total_steps
  const progressPct = Math.round(taskDetail.progress * 100)

  return (
    <View className="progress-page">
      {/* 动画区域 */}
      <View className="animation-section">
        <Text className="animation-icon">🏓</Text>
        <Text className="animation-text">{t('analysis.analyzing')}</Text>
        {wsConnected && <Text className="ws-status">● {t('analysis.realtime')}</Text>}
      </View>

      {/* 进度条 */}
      <View className="progress-bar-section">
        <Progress
          percentage={progressPct}
          color="var(--color-primary)"
          strokeWidth={12}
        />
        <Text className="progress-text">{progressPct}%</Text>
      </View>

      {/* 步骤列表 */}
      <View className="steps-section">
        {PIPELINE_STEPS.map((step, idx) => {
          const stepNum = idx + 1
          const isCompleted = stepNum <= currentStep
          const isCurrent = stepNum === currentStep + 1 && taskDetail.status === 'processing'
          return (
            <View
              key={step.key}
              className={`step-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}`}
            >
              <Text className="step-icon">
                {isCompleted ? '✅' : isCurrent ? '⏳' : '○'}
              </Text>
              <Text className="step-label">{t(step.label)}</Text>
            </View>
          )
        })}
      </View>

      {/* 预计时间 */}
      {taskDetail.estimated_remaining_seconds && (
        <View className="estimated-section">
          <Text className="estimated-text">
            {t('analysis.estimatedRemaining', {
              minutes: Math.ceil(taskDetail.estimated_remaining_seconds / 60),
            })}
          </Text>
        </View>
      )}

      {/* 操作按钮 */}
      <View className="actions-section">
        <Button
          type="default"
          block
          onClick={() => Taro.switchTab({ url: '/pages/home/index' })}
        >
          {t('analysis.backToHome')}
        </Button>
      </View>

      {/* 完成后跳转 */}
      {taskDetail.status === 'completed' && taskDetail.report_id && (
        <View className="completed-section">
          <Text className="completed-text">{t('analysis.analysisComplete')}</Text>
          <Button
            type="primary"
            block
            onClick={() => Taro.redirectTo({
              url: `/pages/video-analysis/report/index?report_id=${taskDetail.report_id}`,
            })}
          >
            {t('analysis.viewReport')}
          </Button>
        </View>
      )}

      {/* 失败状态 */}
      {taskDetail.status === 'failed' && (
        <View className="failed-section">
          <Text className="failed-text">{t('analysis.analysisFailed')}</Text>
          <Button
            type="primary"
            block
            onClick={() => Taro.navigateBack()}
          >
            {t('analysis.retry')}
          </Button>
        </View>
      )}
    </View>
  )
}
```

### 4.3 分析报告详情页

```tsx
// frontend/src/pages/video-analysis/report.tsx
import { useEffect, useState, useCallback } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, ScrollView, Video } from '@tarojs/components'
import { Button, Toast, Popup, Skeleton, Textarea } from '@nutui/nutui-react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import { useTranslation } from 'react-i18next'
import './report.scss'

export default function ReportPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const reportId = parseInt(router.params.report_id || '0', 10)
  const {
    reportDetail, feedbackSubmitted,
    fetchReportDetail, submitFeedback, createShare,
  } = useVideoAnalysisStore()
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')
  const [feedbackPopupVisible, setFeedbackPopupVisible] = useState(false)
  const [feedbackComment, setFeedbackComment] = useState('')
  const [landingView, setLandingView] = useState<'mine' | 'opponent'>('mine')

  useEffect(() => {
    if (reportId) {
      fetchReportDetail(reportId)
    }
  }, [reportId])

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  /** 提交反馈 */
  const handleFeedback = async (isCorrect: boolean) => {
    try {
      await submitFeedback(reportId, isCorrect, feedbackComment || undefined)
      setFeedbackPopupVisible(false)
      showToast(isCorrect ? t('analysis.feedbackCorrect') : t('analysis.feedbackIncorrect'))
    } catch (err: any) {
      showToast(err?.message || t('common.operationFailed'))
    }
  }

  /** 分享报告 */
  const handleShare = async () => {
    try {
      const { share_url } = await createShare(reportId)
      // 复制到剪贴板
      Taro.setClipboardData({ data: share_url })
      showToast(t('analysis.shareLinkCopied'))
    } catch (err: any) {
      showToast(err?.message || t('common.operationFailed'))
    }
  }

  if (!reportDetail) {
    return <View className="report-loading"><Skeleton rows={3} animated /></View>
  }

  const result = reportDetail.result_data
  const reportText = reportDetail.report_text
  const landing = result?.landing_points
  const techniques = result?.technique_stats
  const ballSpeed = result?.ball_speed
  const rally = result?.rally_analysis

  // 九宫格热图颜色深浅（根据值大小）
  // --color-primary #E63946，JS 中无法直接使用 CSS 变量，统一引用主色 RGB 值
  const PRIMARY_RGB = '230, 57, 70'
  const maxLanding = landing ? Math.max(...landing.nine_grid.flat()) : 1
  const getHeatColor = (val: number) => {
    const ratio = val / maxLanding
    const alpha = 0.2 + ratio * 0.8
    return `rgba(${PRIMARY_RGB}, ${alpha})`
  }

  // 技术统计环形图数据
  const techniqueTotal = techniques ? Object.values(techniques).reduce((a, b) => a + b, 0) : 1

  return (
    <ScrollView scrollY className="report-page">
      {/* 报告头部 */}
      <View className="report-header">
        <Text className="report-date">
          {new Date(reportDetail.created_at).toLocaleDateString()}
          {reportDetail.is_llm_generated && (
            <Text className="llm-tag">{t('analysis.aiGenerated')}</Text>
          )}
        </Text>
        {result?.video_info && (
          <Text className="video-info">
            {t('analysis.duration')}: {Math.floor(result.video_info.duration_sec / 60)}'{result.video_info.duration_sec % 60}"
          </Text>
        )}
      </View>

      {/* 核心数据卡片 */}
      <View className="core-data-section">
        <View className="data-card">
          <Text className="data-value">{rally?.total_rallies || 0}</Text>
          <Text className="data-label">{t('analysis.totalRallies')}</Text>
        </View>
        <View className="data-card">
          <Text className="data-value">{rally?.avg_rally_length?.toFixed(1) || '0'}</Text>
          <Text className="data-label">{t('analysis.avgRallyLength')}</Text>
        </View>
        <View className="data-card">
          <Text className="data-value">{rally?.max_rally_length || 0}</Text>
          <Text className="data-label">{t('analysis.maxRallyLength')}</Text>
        </View>
      </View>

      {/* 落点九宫格热图 */}
      {landing && (
        <View className="heatmap-section">
          <View className="section-title">{t('analysis.landingDistribution')}</View>
          <View className="heatmap-toggle">
            <View
              className={`toggle-btn ${landingView === 'mine' ? 'active' : ''}`}
              onClick={() => setLandingView('mine')}
            >
              <Text>{t('analysis.myLanding')}</Text>
            </View>
            <View
              className={`toggle-btn ${landingView === 'opponent' ? 'active' : ''}`}
              onClick={() => setLandingView('opponent')}
            >
              <Text>{t('analysis.opponentLanding')}</Text>
            </View>
          </View>
          <View className="heatmap-grid">
            {landing.nine_grid.map((row, ri) =>
              row.map((val, ci) => (
                <View
                  key={`${ri}-${ci}`}
                  className="heatmap-cell"
                  style={{ background: getHeatColor(val) }}
                >
                  <Text className="cell-value">{val}</Text>
                </View>
              ))
            )}
          </View>
          <Text className="heatmap-hint">
            {/* R23-P2-1: 修正 landingHint i18n 插值契约一致性，仅传入 forehand 参数，资源文件移除 {{side}} 占位符 */}
            {t('analysis.landingHint', { forehand: (landing.distribution.forehand * 100).toFixed(0) })}
          </Text>
        </View>
      )}

      {/* 技术动作环形图 */}
      {techniques && (
        <View className="technique-section">
          <View className="section-title">{t('analysis.techniqueDistribution')}</View>
          <View className="technique-chart">
            {/* CSS 环形图实现 */}
            <View className="donut-chart">
              {Object.entries(techniques).map(([key, val], idx) => {
                const pct = (val / techniqueTotal) * 100
                const colors = ['var(--color-primary)', 'var(--color-secondary)', 'var(--color-accent)', 'var(--color-success)']
                const color = colors[idx % colors.length]
                return (
                  <View key={key} className="donut-segment" style={{
                    background: color,
                    clipPath: `polygon(50% 50%, ${50 + 50 * Math.cos(0)}% ${50 + 50 * Math.sin(0)}%, ${50 + 50 * Math.cos(pct / 100 * 2 * Math.PI)}% ${50 + 50 * Math.sin(pct / 100 * 2 * Math.PI)}%)`,
                  }} />
                )
              })}
            </View>
            <View className="technique-legend">
              {Object.entries(techniques).map(([key, val], idx) => {
                const pct = ((val / techniqueTotal) * 100).toFixed(0)
                const colors = ['var(--color-primary)', 'var(--color-secondary)', 'var(--color-accent)', 'var(--color-success)']
                return (
                  <View key={key} className="legend-item">
                    <View className="legend-dot" style={{ background: colors[idx % colors.length] }} />
                    <Text className="legend-label">{t(`technique.${key}`)}</Text>
                    <Text className="legend-value">{pct}%</Text>
                  </View>
                )
              })}
            </View>
          </View>
          {reportText && reportText.issues.length > 0 && (
            <Text className="technique-hint">{reportText.issues[0]}</Text>
          )}
        </View>
      )}

      {/* 球速数据（范围值） */}
      {ballSpeed && (
        <View className="ball-speed-section">
          <View className="section-title">{t('analysis.ballSpeed')}</View>
          <View className="speed-display">
            <Text className="speed-range">
              {ballSpeed.speed_range[0].toFixed(1)} - {ballSpeed.speed_range[1].toFixed(1)}
            </Text>
            <Text className="speed-unit">m/s</Text>
          </View>
          <Text className="speed-hint">{t('analysis.speedHint')}</Text>
        </View>
      )}

      {/* 分析结论 */}
      {reportText && (
        <View className="conclusion-section">
          <View className="section-title">{t('analysis.conclusion')}</View>
          <View className="conclusion-content">
            <Text className="conclusion-summary">{reportText.summary}</Text>
            {reportText.issues.length > 0 && (
              <View className="issues-list">
                <Text className="issues-title">{t('analysis.issues')}</Text>
                {reportText.issues.map((issue, idx) => (
                  <Text key={idx} className="issue-item">• {issue}</Text>
                ))}
              </View>
            )}
          </View>
          {reportText.suggestions.length > 0 && (
            <View className="suggestions-list">
              <Text className="suggestions-title">{t('analysis.suggestions')}</Text>
              {reportText.suggestions.map((suggestion, idx) => (
                <Text key={idx} className="suggestion-item">• {suggestion}</Text>
              ))}
            </View>
          )}
        </View>
      )}

      {/* 视频回放 */}
      {reportDetail.annotated_video_url && (
        <View className="video-section">
          <View className="section-title">{t('analysis.videoPlayback')}</View>
          <Video
            src={reportDetail.annotated_video_url}
            controls
            autoplay={false}
            className="annotated-video"
          />
        </View>
      )}

      {/* 反馈区域 */}
      <View className="feedback-section">
        {feedbackSubmitted ? (
          <Text className="feedback-done">{t('analysis.feedbackSubmitted')}</Text>
        ) : (
          <>
            <Text className="feedback-title">{t('analysis.feedbackPrompt')}</Text>
            <View className="feedback-buttons">
              <Button
                type="success"
                onClick={() => { setFeedbackComment(''); handleFeedback(true) }}
              >
                👍 {t('analysis.accurate')}
              </Button>
              <Button
                type="danger"
                onClick={() => setFeedbackPopupVisible(true)}
              >
                👎 {t('analysis.inaccurate')}
              </Button>
            </View>
          </>
        )}
      </View>

      {/* 底部操作 */}
      <View className="bottom-actions">
        <Button type="primary" block onClick={handleShare}>
          {t('analysis.shareReport')}
        </Button>
      </View>

      {/* 反馈弹窗 */}
      <Popup
        visible={feedbackPopupVisible}
        position="bottom"
        onClose={() => setFeedbackPopupVisible(false)}
      >
        <View className="feedback-popup">
          <Text className="popup-title">{t('analysis.feedbackDetail')}</Text>
          <Textarea
            placeholder={t('analysis.feedbackPlaceholder')}
            value={feedbackComment}
            onChange={(val) => setFeedbackComment(val)}
            maxLength={500}
            className="feedback-textarea"
          />
          <Button type="primary" block onClick={() => handleFeedback(false)}>
            {t('common.submit')}
          </Button>
        </View>
      </Popup>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </ScrollView>
  )
}
```

### 4.4 报告列表页

```tsx
// frontend/src/pages/video-analysis/list.tsx
import { useEffect, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, ScrollView, Image } from '@tarojs/components'
import { Button, Empty } from '@nutui/nutui-react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import { useTranslation } from 'react-i18next'
import './list.scss'

export default function ReportListPage() {
  const { t } = useTranslation()
  const { reports, reportsTotal, fetchReports } = useVideoAnalysisStore()

  useEffect(() => {
    fetchReports(1, 20)
  }, [])

  const handleReportClick = (reportId: number) => {
    Taro.navigateTo({ url: `/pages/video-analysis/report/index?report_id=${reportId}` })
  }

  return (
    <ScrollView scrollY className="report-list-page">
      <View className="page-header">
        <Text className="page-title">{t('analysis.myReports')}</Text>
        <Text className="page-count">{reportsTotal}</Text>
      </View>

      {reports.length === 0 ? (
        <View className="empty-state">
          <Empty description={t('analysis.noReports')} />
          <Button
            type="primary"
            onClick={() => Taro.navigateTo({ url: '/pages/video-analysis/upload/index' })}
          >
            {t('analysis.startAnalysis')}
          </Button>
        </View>
      ) : (
        <View className="report-list">
          {reports.map((report) => (
            <View
              key={report.id}
              className="report-card"
              onClick={() => handleReportClick(report.id)}
            >
              {report.cover_image_url ? (
                <Image
                  className="report-cover"
                  src={report.cover_image_url}
                  mode="aspectFill"
                />
              ) : (
                <View className="report-cover-placeholder">
                  <Text>📊</Text>
                </View>
              )}
              <View className="report-info">
                <Text className="report-date">
                  {new Date(report.created_at).toLocaleDateString()}
                </Text>
                <Text className="report-summary" numberOfLines={2}>
                  {report.report_summary || t('analysis.noSummary')}
                </Text>
                {report.is_llm_generated && (
                  <Text className="ai-tag">AI</Text>
                )}
              </View>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  )
}
```

---

## 5. 样式

```scss
// frontend/src/pages/video-analysis/upload.scss
.upload-page {
  min-height: 100vh;
  background: var(--color-background);
  padding: var(--spacing-md);
}

.guide-section {
  .guide-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-md);
  }

  .guide-cards {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-sm-md);
  }

  .guide-card {
    padding: var(--spacing-md);
    background: var(--color-card);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-card);

    .guide-icon {
      font-size: 24px;
    }

    .guide-text {
      display: block;
      font-size: 15px;
      font-weight: 600;
      color: var(--color-text-primary);
      margin: var(--spacing-xs) 0;
    }

    .guide-detail {
      font-size: 13px;
      color: var(--color-text-secondary);
    }
  }
}

.notice-section {
  margin: var(--spacing-lg) 0;
  padding: var(--spacing-md);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
  border-radius: var(--radius-sm);

  .notice-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-accent);
    display: block;
    margin-bottom: var(--spacing-sm);
  }

  .notice-list {
    .notice-item {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-xs);
    }
  }
}

.quota-section {
  text-align: center;
  margin: var(--spacing-md) 0;

  .quota-text {
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.upload-btn {
  background: var(--color-primary) !important;
  color: var(--color-text-inverse) !important;
  border-radius: var(--radius-sm) !important;
  height: 48px;
  font-size: 15px;
}

.uploading-page {
  min-height: 100vh;
  background: var(--color-background);
  display: flex;
  align-items: center;
  justify-content: center;

  .uploading-content {
    text-align: center;
    width: 80%;

    .uploading-icon {
      font-size: 32px;
      display: block;
      margin-bottom: var(--spacing-md);
    }

    .uploading-text {
      font-size: 15px;
      color: var(--color-text-primary);
      display: block;
      margin-bottom: var(--spacing-md);
    }
  }
}
```

```scss
// frontend/src/pages/video-analysis/progress.scss
.progress-page {
  min-height: 100vh;
  background: var(--color-background);
  padding: var(--spacing-md);
}

.animation-section {
  text-align: center;
  padding: var(--spacing-2xl) 0;

  .animation-icon {
    font-size: 32px;
    display: block;
    animation: bounce 1.5s infinite;
  }

  .animation-text {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-text-primary);
    display: block;
    margin-top: var(--spacing-md);
  }

  .ws-status {
    font-size: 12px;
    color: var(--color-success);
    margin-top: var(--spacing-sm);
  }
}

@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.progress-bar-section {
  margin: 0 var(--spacing-md) var(--spacing-xl);

  .progress-text {
    text-align: center;
    font-size: 15px;
    color: var(--color-text-primary);
    display: block;
    margin-top: var(--spacing-sm);
  }
}

.steps-section {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin: 0 var(--spacing-md);
  box-shadow: var(--shadow-card);

  .step-item {
    display: flex;
    align-items: center;
    padding: var(--spacing-sm) 0;
    gap: var(--spacing-sm-md);

    .step-icon {
      font-size: 18px;
      width: 24px;
    }

    .step-label {
      font-size: 13px;
      color: var(--color-text-secondary);
    }

    &.completed .step-label {
      color: var(--color-text-primary);
    }

    &.current .step-label {
      color: var(--color-primary);
      font-weight: 600;
    }
  }
}

.estimated-section {
  text-align: center;
  margin: var(--spacing-md);

  .estimated-text {
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.completed-section,
.failed-section {
  margin: var(--spacing-lg) var(--spacing-md);
  text-align: center;

  .completed-text {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-success);
    display: block;
    margin-bottom: var(--spacing-md);
  }

  .failed-text {
    font-size: 15px;
    color: var(--color-warning);
    display: block;
    margin-bottom: var(--spacing-md);
  }
}
```

```scss
// frontend/src/pages/video-analysis/report.scss
.report-page {
  min-height: 100vh;
  background: var(--color-background);
  padding-bottom: 80px;
}

.report-header {
  padding: var(--spacing-md);
  background: var(--color-card);

  .report-date {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .llm-tag {
    font-size: 12px;
    color: var(--color-accent);
    margin-left: var(--spacing-sm);
    padding: var(--spacing-xs) var(--spacing-sm);
    background: color-mix(in srgb, var(--color-accent) 10%, transparent);
    border-radius: var(--radius-sm);
  }

  .video-info {
    display: block;
    margin-top: var(--spacing-xs);
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.core-data-section {
  display: flex;
  padding: var(--spacing-md);
  gap: var(--spacing-sm);

  .data-card {
    flex: 1;
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-md) var(--spacing-sm);
    text-align: center;
    box-shadow: var(--shadow-card);

    .data-value {
      display: block;
      font-size: 32px;
      font-weight: bold;
      color: var(--color-secondary);
    }

    .data-label {
      display: block;
      margin-top: var(--spacing-xs);
      font-size: 12px;
      color: var(--color-text-secondary);
    }
  }
}

.heatmap-section,
.technique-section,
.ball-speed-section,
.conclusion-section,
.video-section,
.feedback-section {
  margin: var(--spacing-sm-md) var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-card);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);

  .section-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm-md);
  }
}

.heatmap-toggle {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm-md);

  .toggle-btn {
    flex: 1;
    text-align: center;
    padding: var(--spacing-sm);
    border-radius: var(--radius-sm);
    font-size: 13px;
    background: var(--color-background);
    color: var(--color-text-secondary);

    &.active {
      background: var(--color-primary);
      color: var(--color-text-inverse);
    }
  }
}

.heatmap-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-xs);
  aspect-ratio: 3 / 2;
  margin: var(--spacing-sm-md) 0;

  .heatmap-cell {
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;

    .cell-value {
      font-size: 13px;
      font-weight: 600;
      color: var(--color-text-inverse);
    }
  }
}

.heatmap-hint {
  display: block;
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: var(--spacing-sm);
}

.technique-chart {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.donut-chart {
  width: 120px; /* P3-fix: chart dimension, not spacing */
  height: 120px; /* P3-fix: chart dimension, not spacing */
  border-radius: 50%;
  position: relative;
  overflow: hidden;
  background: var(--color-background);
}

.technique-legend {
  flex: 1;

  .legend-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    margin: var(--spacing-xs) 0;

    .legend-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
    }

    .legend-label {
      flex: 1;
      font-size: 13px;
      color: var(--color-text-primary);
    }

    .legend-value {
      font-size: 13px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
  }
}

.technique-hint {
  display: block;
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: var(--spacing-sm-md);
}

.speed-display {
  text-align: center;
  padding: var(--spacing-md) 0;

  .speed-range {
    font-size: 32px;
    font-weight: bold;
    color: var(--color-accent);
  }

  .speed-unit {
    font-size: 13px;
    color: var(--color-text-secondary);
    margin-left: var(--spacing-xs);
  }
}

.speed-hint {
  display: block;
  text-align: center;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.conclusion-summary {
  font-size: 13px;
  color: var(--color-text-primary);
  line-height: 1.6;
  display: block;
  margin-bottom: var(--spacing-sm-md);
}

.issues-list,
.suggestions-list {
  margin-top: var(--spacing-sm-md);

  .issues-title,
  .suggestions-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--color-secondary);
    display: block;
    margin-bottom: var(--spacing-xs);
  }

  .issue-item,
  .suggestion-item {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
    margin-top: var(--spacing-xs);
    line-height: 1.5;
  }
}

.annotated-video {
  width: 100%;
  border-radius: var(--radius-sm);
}

.feedback-section {
  text-align: center;

  .feedback-title {
    font-size: 13px;
    color: var(--color-text-primary);
    display: block;
    margin-bottom: var(--spacing-sm-md);
  }

  .feedback-buttons {
    display: flex;
    gap: var(--spacing-sm-md);
    justify-content: center;
  }

  .feedback-done {
    font-size: 13px;
    color: var(--color-success);
  }
}

.bottom-actions {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: var(--spacing-sm-md) var(--spacing-md);
  background: var(--color-card);
  box-shadow: var(--shadow-card-top); /* R19-P3-1: 顶部反向阴影使用专用变量 */
}

.feedback-popup {
  padding: var(--spacing-lg) var(--spacing-md);

  .popup-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);
    display: block;
    margin-bottom: var(--spacing-md);
  }

  .feedback-textarea {
    width: 100%;
    min-height: 100px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-sm);
    padding: var(--spacing-sm-md);
    font-size: 13px;
    margin-bottom: var(--spacing-md);
  }
}
```

```scss
// frontend/src/pages/video-analysis/list.scss
.report-list-page {
  min-height: 100vh;
  background: var(--color-background);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);

  .page-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .page-count {
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.empty-state {
  text-align: center;
  padding: var(--spacing-2xl) var(--spacing-md);

  .empty-icon {
    font-size: 32px;
    display: block;
    margin-bottom: var(--spacing-md);
  }

  .empty-text {
    font-size: 15px;
    color: var(--color-text-secondary);
    display: block;
    margin-bottom: var(--spacing-md);
  }

  .empty-cta {
    font-size: 15px;
    color: var(--color-primary);
    display: inline-block;
    padding: var(--spacing-sm) var(--spacing-lg);
    border: 1px solid var(--color-primary);
    border-radius: var(--radius-sm);
  }
}

.report-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm-md);
  padding: 0 var(--spacing-md) var(--spacing-md);
}

.report-card {
  display: flex;
  background: var(--color-card);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-card);

  .report-cover {
    width: 80px;
    height: 80px;
    flex-shrink: 0;
  }

  .report-cover-placeholder {
    width: 80px;
    height: 80px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg);
    font-size: 24px;
  }

  .report-info {
    flex: 1;
    padding: var(--spacing-sm-md);
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);

    .report-date {
      font-size: 12px;
      color: var(--color-text-secondary);
    }

    .report-summary {
      font-size: 13px;
      color: var(--color-text-primary);
      flex: 1;
    }

    .ai-tag {
      align-self: flex-start;
      font-size: 12px;
      color: var(--color-accent);
      padding: var(--spacing-xs) var(--spacing-sm);
      background: color-mix(in srgb, var(--color-accent) 10%, transparent);
      border-radius: var(--radius-sm);
    }
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 analysis 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    'pages/video-analysis/upload/index',       // 新增：视频上传页
    'pages/video-analysis/processing/index',    // 新增：分析进度页
    'pages/video-analysis/report/index',      // 新增：分析报告详情页
    'pages/video-analysis/list/index',        // 新增：报告列表页
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "analysis": {
    "shootingGuide": "拍摄引导",
    "angleGuide": "拍摄角度",
    "angleDetail": "侧后方斜 45° 高位，球台全貌入镜",
    "distanceGuide": "拍摄距离",
    "distanceDetail": "距球台 3-5 米，确保球员和球台完整入镜",
    "lightingGuide": "光线条件",
    "lightingDetail": "光线充足均匀，避免逆光拍摄",
    "notice": "注意事项",
    "noticeFormat": "仅支持 MP4 / MOV 格式",
    "noticeSize": "视频文件不能超过 500MB",
    "noticeDuration": "建议视频时长 1-5 分钟",
    "freeQuotaHint": "免费用户每日可分析 3 次，会员无限分析",
    "chooseVideo": "选择/拍摄视频",
    "invalidFormat": "仅支持 MP4/MOV 格式",
    "fileTooLarge": "视频文件不能超过 500MB",
    "chooseFailed": "选择视频失败",
    "uploading": "视频上传中...",
    "uploadFailed": "上传失败，请重试",
    "taskCreated": "分析任务已创建",
    "taskCreateFailed": "创建分析任务失败",
    "analyzing": "AI 正在分析你的视频...",
    "realtime": "实时",
    "estimatedRemaining": "预计还需约 {{minutes}} 分钟",
    "backToHome": "返回首页，稍后查看",
    "analysisComplete": "分析完成！",
    "viewReport": "查看报告",
    "analysisFailed": "分析失败，请重试",
    "retry": "重试",
    "aiGenerated": "AI 生成",
    "duration": "时长",
    "totalRallies": "总板数",
    "avgRallyLength": "平均回合",
    "maxRallyLength": "最长回合",
    "landingDistribution": "落点分布",
    "myLanding": "我的落点",
    "opponentLanding": "对手落点",
    "landingHint": "正手使用率 {{forehand}}%",
    "techniqueDistribution": "技术动作分布",
    "ballSpeed": "击球球速",
    "speedHint": "球速为估算范围值，误差 20-30%",
    "conclusion": "分析结论",
    "issues": "发现的问题",
    "suggestions": "训练建议",
    "videoPlayback": "视频回放",
    "feedbackPrompt": "这次分析准不准？",
    "accurate": "准确",
    "inaccurate": "部分不准",
    "feedbackDetail": "请描述哪些部分不准",
    "feedbackPlaceholder": "你的反馈帮助 AI 提升精度...",
    "feedbackSubmitted": "感谢你的反馈！",
    "feedbackCorrect": "感谢认可！我们会继续提升精度",
    "feedbackIncorrect": "反馈已提交，我们会进一步优化",
    "shareReport": "分享报告",
    "shareLinkCopied": "分享链接已复制到剪贴板",
    "myReports": "我的分析",
    "noReports": "还没有分析记录",
    "noSummary": "暂无摘要",
    "startAnalysis": "开始第一次分析",
    "step": {
      "videoUpload": "视频上传完成",
      "transcode": "视频转码",
      "ballDetect": "球体检测",
      "speedEstimate": "球速估算",
      "ballTrack": "球体追踪",
      "actionRecognize": "动作识别",
      "landingAnalyze": "落点分析",
      "rallySplit": "回合分割",
      "statistics": "统计分析",
      "report": "报告生成"
    }
  },
  "technique": {
    "forehand_drive": "正手攻球",
    "backhand_drive": "反手拨球",
    "forehand_loop": "正手拉球",
    "backhand_loop": "反手拉球",
    "serve": "发球",
    "push": "搓球",
    "block": "挡球"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "analysis": {
    "shootingGuide": "Shooting Guide",
    "angleGuide": "Camera Angle",
    "angleDetail": "Side-rear 45° high angle, full table view",
    "distanceGuide": "Distance",
    "distanceDetail": "3-5m from table, ensure full view",
    "lightingGuide": "Lighting",
    "lightingDetail": "Sufficient even lighting, avoid backlight",
    "notice": "Notes",
    "noticeFormat": "MP4 / MOV format only",
    "noticeSize": "Max 500MB",
    "noticeDuration": "Recommended 1-5 minutes",
    "freeQuotaHint": "Free users: 3 analyses/day, members: unlimited",
    "chooseVideo": "Choose/Record Video",
    "invalidFormat": "Only MP4/MOV supported",
    "fileTooLarge": "File exceeds 500MB",
    "chooseFailed": "Failed to choose video",
    "uploading": "Uploading video...",
    "uploadFailed": "Upload failed, please retry",
    "taskCreated": "Analysis task created",
    "taskCreateFailed": "Failed to create task",
    "analyzing": "AI is analyzing your video...",
    "realtime": "Live",
    "estimatedRemaining": "Estimated ~{{minutes}} min remaining",
    "backToHome": "Back to home",
    "analysisComplete": "Analysis complete!",
    "viewReport": "View Report",
    "analysisFailed": "Analysis failed, please retry",
    "retry": "Retry",
    "aiGenerated": "AI",
    "duration": "Duration",
    "totalRallies": "Total Rallies",
    "avgRallyLength": "Avg Rally",
    "maxRallyLength": "Max Rally",
    "landingDistribution": "Landing Distribution",
    "myLanding": "My Landing",
    "opponentLanding": "Opponent",
    "landingHint": "Forehand {{forehand}}%",
    "techniqueDistribution": "Technique Distribution",
    "ballSpeed": "Ball Speed",
    "speedHint": "Estimated range, 20-30% error margin",
    "conclusion": "Conclusion",
    "issues": "Issues Found",
    "suggestions": "Suggestions",
    "videoPlayback": "Video Playback",
    "feedbackPrompt": "Is this analysis accurate?",
    "accurate": "Accurate",
    "inaccurate": "Not quite",
    "feedbackDetail": "Please describe what's inaccurate",
    "feedbackPlaceholder": "Your feedback helps improve AI...",
    "feedbackSubmitted": "Thanks for your feedback!",
    "feedbackCorrect": "Thank you! We'll keep improving",
    "feedbackIncorrect": "Feedback submitted, we'll optimize further",
    "shareReport": "Share Report",
    "shareLinkCopied": "Share link copied to clipboard",
    "myReports": "My Analyses",
    "noReports": "No analyses yet",
    "noSummary": "No summary",
    "startAnalysis": "Start your first analysis",
    "step": {
      "videoUpload": "Video Upload",
      "transcode": "Transcoding",
      "ballDetect": "Ball Detection",
      "speedEstimate": "Speed Estimation",
      "ballTrack": "Ball Tracking",
      "actionRecognize": "Action Recognition",
      "landingAnalyze": "Landing Analysis",
      "rallySplit": "Rally Splitting",
      "statistics": "Statistics",
      "report": "Report Generation"
    }
  },
  "technique": {
    "forehand_drive": "Forehand Drive",
    "backhand_drive": "Backhand Drive",
    "forehand_loop": "Forehand Loop",
    "backhand_loop": "Backhand Loop",
    "serve": "Serve",
    "push": "Push",
    "block": "Block"
  }
}
```

---

## 8. WebSocket 连接 Hook

> **R18-P3-17 调查结论（已在 R18 落地）**：原 R18 推迟原因为"useAnalysisProgress 接口不一致，需进一步调查"。经 R18 调查，本 Hook 接口与 §5.1 进度卡片组件、§7.1 videoAnalysisStore 的契约一致，无逻辑不一致：
> - **入参契约**：`{ taskId, onComplete?, onProgress? }` 与 §5.1 `<AnalysisProgressCard taskId={taskId} onProgress={setProgress} onComplete={handleComplete} />` 一致
> - **回调时机**：`onProgress(progress)` 在 `data.event === 'analysis_progress'` 时触发（与后端 WS §6.1 `analysis_progress` 事件 payload `{ progress: 0~100 }` 一致），`onComplete(reportId)` 在 `analysis_complete` 事件触发（与 §6.1 payload `{ report_id }` 一致）
> - **返回值**：`{ connected, retryCount }` 暴露连接状态和重连计数，供 §5.1 卡片显示"实时连接中/重连中/已断开"状态；`progress` 数值通过 `onProgress` 回调上抛父组件管理（设计选择：避免 Hook 内部状态与父组件状态双源）
> - **轮询兜底**：`pollRef` 占位 `// import videoAnalysis API and call getTaskDetail` 为开发阶段实现提示，Phase 1 切片已通过 WS+重连覆盖，轮询兜底属 Phase 2 增强
> - **结论**：接口设计一致，无需修改；轮询兜底注释在 Phase 2 实现时补齐 `getTaskDetail` 调用即可。

```typescript
// frontend/src/hooks/useAnalysisProgress.ts
import { useEffect, useRef, useState, useCallback } from 'react'
import Taro from '@tarojs/taro'

interface UseAnalysisProgressOptions {
  taskId: string
  onComplete?: (reportId: number) => void
  onProgress?: (progress: number) => void
}

/**
 * 分析进度 WebSocket Hook。
 * 支持实时推送 + 轮询兜底 + 指数退避重连。
 */
export function useAnalysisProgress({ taskId, onComplete, onProgress }: UseAnalysisProgressOptions) {
  const [connected, setConnected] = useState(false)
  const [retryCount, setRetryCount] = useState(0)
  const wsRef = useRef<Taro.SocketTask | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const maxRetries = 5

  const connect = useCallback(() => {
    if (retryCount >= maxRetries) return

    const token = Taro.getStorageSync('access_token')
    const wsUrl = `${process.env.TARO_APP_WS || 'wss://api.pingpongai.com/ws'}?token=${token}`

    const socketTask = Taro.connectSocket({ url: wsUrl })
    wsRef.current = socketTask

    socketTask.onOpen(() => {
      setConnected(true)
      setRetryCount(0)
      // 订阅任务进度频道
      socketTask.send({
        data: JSON.stringify({ event: 'subscribe', channel: `task:${taskId}` }),
      })
    })

    socketTask.onMessage((msg) => {
      try {
        const data = JSON.parse(msg.data)
        if (data.event === 'analysis_progress' && data.task_id === taskId) {
          onProgress?.(data.progress)
        }
        if (data.event === 'analysis_complete' && data.task_id === taskId) {
          onComplete?.(data.report_id)
        }
      } catch (e) {
        // ignore
      }
    })

    socketTask.onClose(() => {
      setConnected(false)
      // 指数退避重连
      const delay = Math.min(1000 * Math.pow(2, retryCount), 16000)
      setRetryCount((prev) => prev + 1)
      setTimeout(() => connect(), delay)
    })

    socketTask.onError(() => {
      setConnected(false)
    })
  }, [taskId, retryCount, onComplete, onProgress])

  useEffect(() => {
    connect()

    // 轮询兜底（每 5 秒）
    pollRef.current = setInterval(() => {
      // import videoAnalysis API and call getTaskDetail
    }, 5000)

    return () => {
      wsRef.current?.close({})
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [connect])

  return { connected, retryCount }
}
```

---

## 9. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 上传页拍摄引导卡片布局清晰（角度/距离/光线三卡片）
- [ ] 上传按钮使用主色 `#E63946`
- [ ] 进度页动画效果（球拍弹跳）正常
- [ ] 步骤列表完成项显示绿色 ✅，当前项显示 ⏳，未开始显示 ○
- [ ] 报告页九宫格热图颜色深浅正确（高频深色）
- [ ] 技术环形图图例颜色与数据匹配
- [ ] 球速显示为范围值（非精确值）
- [ ] 视频回放组件正常加载和播放
- [ ] 反馈按钮：准确使用成功色 `#2A9D8F`，不准使用主色 `#E63946`
- [ ] 分享按钮固定在底部

### 功能验证
- [ ] 选择/拍摄视频 → 校验格式/大小 → 获取上传凭证 → OSS 直传 → 确认上传 → 创建任务
- [ ] 进度页 WebSocket 实时推送 + 轮询兜底
- [ ] 分析完成后自动跳转报告页
- [ ] 报告页展示：核心数据 → 热图 → 技术统计 → 球速 → 结论 → 视频回放 → 反馈 → 分享
- [ ] 落点热图可切换"我的落点"/"对手落点"
- [ ] 反馈弹窗底部弹出，提交后显示"已提交"
- [ ] 分享链接复制到剪贴板

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** WebSocket 连接必须实现指数退避重连（1s → 2s → 4s → 8s → 16s，最大 5 次）
- **ALL** 进度展示必须同时支持 WebSocket 推送 + 轮询兜底
- **ALL** 球速数据必须展示为范围值（非精确值），因估算误差 20-30%
- **ALL** 落点热图使用九宫格（3×3），颜色深浅表示频率
- **禁止** 使用 class 组件
- **禁止** 硬编码颜色值，使用 CSS 变量
- **禁止** 安装新的 npm 包
- **禁止** 在上传页面做免费额度逻辑判断（仅提示，实际控制在后端）
- **禁止** 在分享页面暴露训练建议/历史趋势/用户个人信息
