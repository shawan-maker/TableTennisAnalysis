/**
 * 进度综合摘要页（08-progress_analysis/frontend.md §4.1）
 * 概览 + 指标趋势列表（跳 trend-detail）+ 问题变化三组 + 线性回归预测
 *
 * FS4-P3：NutUI Progress 为 percent（样例 percentage 为 2.x 旧口径）+ strokeWidth '8px'；
 * summary 含 training_plan_status（R4-Progress-4）——FS5 已消费：当前训练方案
 * 区块展示版本/调整原因/目标达成度，点击跳训练方案详情（plans/detail?plan_id=）。
 *
 * R-FE-R1 批次B（FE-P1-10② + FE-P2-25）：会员门控——progress_analysis 在
 * EXPIRED_ACCESS_MAP 中为 hidden（10-membership §8 useMembershipGate 统一控制），
 * 免费/到期/闭户用户渲染升级引导（training 域 40300 Empty 先例）。
 */
import { useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Tag, Progress, Skeleton, Empty } from '@nutui/nutui-react'
import { useProgressStore } from '@/stores/progressStore'
import { useMembershipGate } from '@/hooks/useMembershipGate'
import { useTranslation } from 'react-i18next'
import './index.scss'

/** 趋势标签颜色映射（§4.1 TREND_COLORS） */
const TREND_COLORS: Record<string, string> = {
  improving: 'var(--color-success)',
  stagnant: 'var(--color-accent)',
  declining: 'var(--color-primary)',
  achieved: 'var(--color-secondary)',
  new: 'var(--color-primary)',
  resolved: 'var(--color-success)',
}

export default function ProgressSummary() {
  const { t } = useTranslation()
  const summary = useProgressStore((s) => s.summary)
  const loading = useProgressStore((s) => s.loading)
  const fetchSummary = useProgressStore((s) => s.fetchSummary)
  // R-FE-R1 批次B（FE-P1-10②）：progress_analysis 会员门控
  const { canAccess } = useMembershipGate('progress_analysis')

  useEffect(() => {
    fetchSummary()
  }, [fetchSummary])

  // 会员门控：免费/到期/闭户 → 升级引导（10-membership §8 功能验证：
  // 「到期会员的功能入口被隐藏（如 3D 教学、进度分析）」）
  if (!canAccess) {
    return (
      <View className="progress-summary">
        <View className="membership-guard">
          <Empty
            title={t('progress.membershipRequired')}
            actions={[
              {
                text: t('progress.upgradeMembership'),
                type: 'primary',
                size: 'small',
                onClick: () => Taro.navigateTo({ url: '/pages/membership/index' }),
              },
            ]}
          />
        </View>
      </View>
    )
  }

  if (loading && !summary) {
    return (
      <View className="progress-summary loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  if (!summary) {
    return (
      <View className="progress-summary empty">
        <Text className="empty-text">{t('progress.noData')}</Text>
      </View>
    )
  }

  return (
    <View className="progress-summary">
      {/* 概览卡片区 */}
      <View className="summary-header">
        <Text className="summary-period">
          {t('progress.summaryPeriod')}: {t(`progress.period.${summary.summary_period}`)}
        </Text>
        <View className="summary-stats">
          <View className="stat-item">
            <Text className="stat-value">{summary.total_analyses}</Text>
            <Text className="stat-label">{t('progress.totalAnalyses')}</Text>
          </View>
          <View className="stat-item">
            <Tag background={TREND_COLORS[summary.overall_progress] || 'var(--color-secondary)'} color="var(--color-text-inverse)">
              {t(`progress.trend.${summary.overall_progress}`)}
            </Tag>
            <Text className="stat-label">{t('progress.overallProgress')}</Text>
          </View>
        </View>
      </View>

      {/* 指标趋势卡片区（点击跳单项趋势详情） */}
      <View className="section">
        <Text className="section-title">{t('progress.metricTrends')}</Text>
        {summary.metric_trends.map((mt) => (
          <Cell
            key={mt.metric}
            title={mt.metric_name}
            description={`${t('progress.currentValue')}: ${mt.current_value ?? '-'} → ${t('progress.target')}: ${mt.target ?? '-'}`}
            clickable
            onClick={() => {
              Taro.navigateTo({
                url: `/pages/progress/trend-detail/index?metric=${mt.metric}`,
              })
            }}
            extra={
              <View className="trend-extra">
                {mt.trend && (
                  <Tag
                    background={TREND_COLORS[mt.trend] || 'var(--color-text-secondary)'}
                    color="var(--color-text-inverse)"
                  >
                    {t(`progress.trend.${mt.trend}`)}
                  </Tag>
                )}
                {mt.target_progress != null && (
                  <Progress
                    percent={mt.target_progress}
                    color={TREND_COLORS[mt.trend ?? ''] || 'var(--color-accent)'}
                    strokeWidth="8px"
                  />
                )}
              </View>
            }
          />
        ))}
      </View>

      {/* 问题变化区 */}
      <View className="section">
        <Text className="section-title">{t('progress.problemChanges')}</Text>
        <View className="problem-group">
          <Text className="problem-label problem-new">
            {t('progress.newProblems')} ({summary.problem_changes.new.length})
          </Text>
          {summary.problem_changes.new.map((p, i) => (
            <Text key={i} className="problem-item">• {p}</Text>
          ))}
        </View>
        <View className="problem-group">
          <Text className="problem-label problem-resolved">
            {t('progress.resolvedProblems')} ({summary.problem_changes.resolved.length})
          </Text>
          {summary.problem_changes.resolved.map((p, i) => (
            <Text key={i} className="problem-item">• {p}</Text>
          ))}
        </View>
        <View className="problem-group">
          <Text className="problem-label problem-persistent">
            {t('progress.persistentProblems')} ({summary.problem_changes.persistent.length})
          </Text>
          {summary.problem_changes.persistent.map((p, i) => (
            <Text key={i} className="problem-item">• {p}</Text>
          ))}
        </View>
      </View>

      {/* 当前训练方案（R4-Progress-4 契约预留，FS5 消费点） */}
      {summary.training_plan_status && (
        <View className="section">
          <Text className="section-title">{t('progress.currentPlan')}</Text>
          <Cell
            title={`${t('progress.planVersion')} v${summary.training_plan_status.plan_version}`}
            description={
              summary.training_plan_status.adjustment_reason ||
              (summary.training_plan_status.goal_completion &&
              Object.entries(summary.training_plan_status.goal_completion).length > 0
                ? Object.entries(summary.training_plan_status.goal_completion)
                    // R-FE-R2 批次E（FE-P3-30）：goal_completion 键走 progress.metric.* 映射
                    // （修复前直显后端英文键名 backhand_ratio，与同页 L109 metric_name 中文口径不一）
                    .map(([metric, val]) => `${t(`progress.metric.${metric}`)}: ${val}`)
                    .join(' · ')
                : t('progress.noData'))
            }
            clickable
            onClick={() => {
              Taro.navigateTo({
                url: `/pages/training/plans/detail/index?plan_id=${summary.training_plan_status!.current_plan_id}`,
              })
            }}
            extra={<Text className="plan-link">›</Text>}
          />
        </View>
      )}

      {/* 预测区（线性回归） */}
      {Object.keys(summary.forecast).length > 0 && (
        <View className="section">
          <Text className="section-title">{t('progress.forecast')}</Text>
          {Object.entries(summary.forecast).map(([metric, fc]) => (
            <Cell
              key={metric}
              title={metric}
              description={`${t('progress.predictedWeeks')}: ${fc.predicted_weeks_to_target ?? '-'}`}
              extra={
                <Tag
                  background={fc.confidence === 'high' ? 'var(--color-success)' : 'var(--color-accent)'}
                  color="var(--color-text-inverse)"
                >
                  R²={fc.r_squared.toFixed(2)}
                </Tag>
              }
            />
          ))}
        </View>
      )}
    </View>
  )
}
