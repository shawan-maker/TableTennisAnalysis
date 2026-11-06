/**
 * 训练方案详情页（07-training_advice/frontend.md §4.8，R20-P2-1）
 * 训练单列表 + 进度 + 标记完成（API §8.8，完成后积分提示）
 * + 重新评估（API §8.6，i18n planReEvaluated/reEvaluateFailed 设计内含）
 * 挂载 BadgeUnlockPopup（完成训练单可解锁徽章，WS badge_unlocked）
 *
 * FS5-P3：plan_id 经页面 query 传递（weapp 路径不支持 [plan_id] 段，
 * 注册表记法 pages/training/plans/[plan_id]/index → 实际注册 plans/detail/index）；
 * 受控 Toast 样例改 store 内 Taro.showToast（FS4 先例）；
 * 会员守卫（403/40300）渲染升级引导。
 */
import { useEffect } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Cell, Button, Skeleton, Empty, Tag, Progress } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useTrainingStore } from '@/stores/trainingStore'
import BadgeUnlockPopup from '@/components/BadgeUnlockPopup'
import './index.scss'

export default function TrainingPlanDetailPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const sessions = useTrainingStore((s) => s.sessions)
  const sessionsTotal = useTrainingStore((s) => s.sessionsTotal)
  const sessionsLoading = useTrainingStore((s) => s.sessionsLoading)
  const sessionsError = useTrainingStore((s) => s.sessionsError)
  const sessionsNeedsMembership = useTrainingStore((s) => s.sessionsNeedsMembership)
  const completeSessionLoading = useTrainingStore((s) => s.completeSessionLoading)
  const reEvaluating = useTrainingStore((s) => s.reEvaluating)
  const fetchTrainingSessions = useTrainingStore((s) => s.fetchTrainingSessions)
  const completeTrainingSession = useTrainingStore((s) => s.completeTrainingSession)
  const reEvaluatePlan = useTrainingStore((s) => s.reEvaluatePlan)

  const planId = Number(router.params.plan_id || 0)

  // 拉取训练单列表（API §8.7）
  useEffect(() => {
    if (planId) {
      fetchTrainingSessions(planId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId])

  // 标记完成训练单（API §8.8），完成后 store 内 Toast 积分提示并刷新列表
  const handleCompleteSession = (sessionId: number) => {
    completeTrainingSession(planId, sessionId)
  }

  // 重新评估方案（API §8.6，会员功能）
  const handleReEvaluate = () => {
    reEvaluatePlan(planId)
  }

  const handleUpgrade = () => {
    Taro.navigateTo({ url: '/pages/membership/index' })
  }

  // 会员守卫：升级引导
  if (sessionsNeedsMembership) {
    return (
      <View className="plan-detail-page">
        <View className="plan-header">
          <Text className="page-title">{t('training.planDetail')}</Text>
        </View>
        <View className="plan-error">
          <Empty
            title={t('training.membershipRequired')}
            actions={[
              { text: t('training.upgradeMembership'), type: 'primary', size: 'small', onClick: handleUpgrade },
            ]}
          />
        </View>
      </View>
    )
  }

  // Loading 状态
  if (sessionsLoading && sessions.length === 0) {
    return (
      <View className="plan-detail-page">
        <View className="plan-header">
          <Text className="page-title">{t('training.planDetail')}</Text>
        </View>
        <View className="plan-skeleton">
          {[0, 1, 2, 3].map((i) => (
            <View className="skeleton-item" key={i}>
              <Skeleton rows={2} animated />
            </View>
          ))}
        </View>
      </View>
    )
  }

  // 错误状态（404/40420 训练方案不存在等）
  if (sessionsError && sessions.length === 0) {
    return (
      <View className="plan-detail-page">
        <View className="plan-header">
          <Text className="page-title">{t('training.planDetail')}</Text>
        </View>
        <View className="plan-error">
          <Empty
            title={sessionsError}
            actions={[
              { text: t('common.retry'), type: 'primary', size: 'small', onClick: () => fetchTrainingSessions(planId) },
            ]}
          />
        </View>
      </View>
    )
  }

  // 空状态
  if (sessions.length === 0) {
    return (
      <View className="plan-detail-page">
        <View className="plan-header">
          <Text className="page-title">{t('training.planDetail')}</Text>
        </View>
        <View className="plan-error">
          <Empty title={t('training.noSessions')} />
        </View>
      </View>
    )
  }

  // 已完成训练单数 / 总数
  const completedCount = sessions.filter((s) => s.is_completed).length
  const totalCount = sessionsTotal || sessions.length
  const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0

  return (
    <View className="plan-detail-page">
      {/* 头部区域 */}
      <View className="plan-header">
        <Text className="page-title">{t('training.planDetail')}</Text>
        <View className="plan-progress">
          <Progress percent={progressPercent} strokeWidth="8px" />
          <Text className="progress-text">
            {completedCount} / {totalCount}
          </Text>
        </View>
        {/* 重新评估（API §8.6 会员功能） */}
        <View className="plan-actions">
          <Button
            plain
            type="primary"
            size="small"
            loading={reEvaluating}
            onClick={handleReEvaluate}
          >
            {t('training.reEvaluate')}
          </Button>
        </View>
      </View>

      <ScrollView scrollY className="sessions-scroll">
        {sessions.map((session) => (
          <Cell key={session.id} className="session-item">
            <View className="session-card">
              <View className="session-header">
                <Text className="session-index">#{session.session_index}</Text>
                <Text className="session-name">{session.name}</Text>
                {session.is_completed ? (
                  <Tag background="var(--color-success)" color="var(--color-text-inverse)">
                    {t('training.completed')}
                  </Tag>
                ) : (
                  <Tag background="var(--color-accent)" color="var(--color-text-inverse)">
                    {t('training.pending')}
                  </Tag>
                )}
              </View>
              <View className="session-info">
                <Text className="session-date">
                  {t('training.scheduledDate')}: {session.scheduled_date || '-'}
                </Text>
                <Text className="session-reps">
                  {t('training.reps')}: {session.reps}
                </Text>
                {session.completed_at && (
                  <Text className="session-completed-at">
                    {t('training.completedAt')}: {session.completed_at}
                  </Text>
                )}
              </View>
              {session.exercises && session.exercises.length > 0 && (
                <View className="session-exercises">
                  {session.exercises.map((exercise, i) => (
                    <Text key={`${exercise}-${i}`} className="exercise-text">
                      · {exercise}
                    </Text>
                  ))}
                </View>
              )}
              {/* 未完成训练单可点击标记完成（API §8.8） */}
              {!session.is_completed && (
                <Button
                  type="primary"
                  size="small"
                  loading={completeSessionLoading}
                  onClick={() => handleCompleteSession(session.id)}
                  className="btn-complete"
                >
                  {t('training.markComplete')}
                </Button>
              )}
            </View>
          </Cell>
        ))}
      </ScrollView>

      {/* 徽章解锁弹层（完成训练单触发） */}
      <BadgeUnlockPopup />
    </View>
  )
}
