/**
 * 分析进度页（03-video_analysis/frontend.md §4.2）
 * WS analysis_progress 实时步骤条 + 断线 REST 轮询兜底（useAnalysisProgress 内置 5s 对账）
 *
 * FS3-P3 契约修正：进度页 WS 接入统一 useAnalysisProgress Hook
 * （子协议认证 + 用户频道广播 + task_id 过滤，设计样例的 channel 订阅为假想协议）
 */
import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Progress, Skeleton } from '@nutui/nutui-react'
import { useVideoAnalysisStore } from '@/stores/videoAnalysisStore'
import { useAnalysisProgress } from '@/hooks/useAnalysisProgress'
import { useTranslation } from 'react-i18next'
import './index.scss'

/** 流水线步骤定义（与后端 ai_pipeline STEP_WEIGHTS 10 步对应，文案键 §7 analysis.step.*） */
const PIPELINE_STEPS = [
  { label: 'analysis.step.videoUpload', icon: '✅' },
  { label: 'analysis.step.transcode', icon: '🎬' },
  { label: 'analysis.step.ballDetect', icon: '🎯' },
  { label: 'analysis.step.speedEstimate', icon: '⚡' },
  { label: 'analysis.step.ballTrack', icon: '📈' },
  { label: 'analysis.step.actionRecognize', icon: '🏓' },
  { label: 'analysis.step.landingAnalyze', icon: '📍' },
  { label: 'analysis.step.rallySplit', icon: '📊' },
  { label: 'analysis.step.statistics', icon: '🔢' },
  { label: 'analysis.step.report', icon: '📝' },
]

export default function ProgressPage() {
  const { t } = useTranslation()
  const router = useRouter()
  // FS3-P3：task_id 为 int（设计样例 string 为 v0 口径）
  const taskId = parseInt((router.params.task_id || '0') as string, 10)
  const taskDetail = useVideoAnalysisStore((s) => s.taskDetail)
  const [, setUiProgress] = useState(0)

  // 实时进度（WS + 轮询兜底；connected 断开时轮询对账仍推进进度条）
  const { connected } = useAnalysisProgress({
    taskId,
    onProgress: (pct) => setUiProgress(pct),
    onComplete: () => {
      // 完成跳转交由下方 completed 分支按钮（避免 WS 抖动重复跳转，fetchTaskDetail 对账为准）
    },
  })

  // 完成态自动跳转报告页（status=completed 且 report_id 就绪）
  useEffect(() => {
    if (taskDetail?.status === 'completed' && taskDetail.report_id) {
      const timer = setTimeout(() => {
        Taro.redirectTo({
          url: `/pages/video-analysis/report/index?report_id=${taskDetail.report_id}`,
        })
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [taskDetail?.status, taskDetail?.report_id])

  if (!taskDetail || taskDetail.task_id !== taskId) {
    return (
      <View className="progress-loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const currentStep = taskDetail.current_step || 0
  const progressPct = Math.round((taskDetail.progress || 0) * 100)

  return (
    <View className="progress-page">
      {/* 动画区域 */}
      <View className="animation-section">
        <Text className="animation-icon" aria-hidden="true">🏓</Text>
        <Text className="animation-text">{t('analysis.analyzing')}</Text>
        {connected && <Text className="ws-status">● {t('analysis.realtime')}</Text>}
      </View>

      {/* 进度条 */}
      <View className="progress-bar-section" aria-live="polite">
        <Progress
          percent={progressPct}
          color="var(--color-primary)"
          strokeWidth="12px"
          role="progressbar"
          aria-label={`${progressPct}%`}
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
        <Text className="progress-text">{progressPct}%</Text>
      </View>

      {/* 步骤列表（aria 有序） */}
      <View className="steps-section">
        {PIPELINE_STEPS.map((step, idx) => {
          const stepNum = idx + 1
          const isCompleted = stepNum <= currentStep
          const isCurrent = stepNum === currentStep + 1 && taskDetail.status === 'processing'
          return (
            <View
              key={step.label}
              className={`step-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}`}
            >
              <Text className="step-icon" aria-hidden="true">
                {isCompleted ? '✅' : isCurrent ? '⏳' : '○'}
              </Text>
              <Text className="step-label">{t(step.label)}</Text>
            </View>
          )
        })}
      </View>

      {/* 预计时间 */}
      {taskDetail.estimated_remaining_seconds != null && taskDetail.status === 'processing' && (
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
        <Button type="default" block onClick={() => Taro.switchTab({ url: '/pages/home/index' })}>
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
            onClick={() =>
              Taro.redirectTo({
                url: `/pages/video-analysis/report/index?report_id=${taskDetail.report_id}`,
              })
            }
          >
            {t('analysis.viewReport')}
          </Button>
        </View>
      )}

      {/* 失败状态 */}
      {taskDetail.status === 'failed' && (
        <View className="failed-section">
          <Text className="failed-text">{t('analysis.analysisFailed')}</Text>
          {taskDetail.error_message && (
            <Text className="failed-error">{taskDetail.error_message}</Text>
          )}
          <Button type="primary" block onClick={() => Taro.navigateBack()}>
            {t('analysis.retry')}
          </Button>
        </View>
      )}
    </View>
  )
}
