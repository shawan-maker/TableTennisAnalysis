/**
 * 概览卡片组件（06-data_dashboard/frontend.md §4.2）
 * 胜率 / 分析次数 / 训练频次 / 连续天数 4 卡 + 训练提醒横幅
 */
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { OverviewData } from '@/services/dashboard'
import './OverviewCards.scss'

interface Props {
  data: OverviewData | null
  loading: boolean
}

export default function OverviewCards({ data, loading }: Props) {
  const { t } = useTranslation()

  if (loading && !data) {
    return (
      <View className="overview-cards">
        {[0, 1, 2, 3].map((i) => (
          <View className="overview-card" key={i}>
            <Skeleton rows={1} animated />
          </View>
        ))}
      </View>
    )
  }

  if (!data) return null

  const trendIcon = data.trend === 'up' ? '↑' : data.trend === 'down' ? '↓' : '→'
  const trendClass =
    data.trend === 'up' ? 'trend-up' : data.trend === 'down' ? 'trend-down' : 'trend-flat'

  return (
    <View className="overview-cards">
      {/* 胜率卡片 */}
      <View className="overview-card card-winrate">
        <Text className="card-label">{t('dashboard.winRate')}</Text>
        <Text className="card-value">{(data.win_rate * 100).toFixed(0)}%</Text>
        <Text className="card-sub">
          {data.wins}
          {t('dashboard.wins')} / {data.losses}
          {t('dashboard.losses')}
          <Text className={`trend-icon ${trendClass}`}>{trendIcon}</Text>
        </Text>
      </View>

      {/* 分析次数卡片 */}
      <View className="overview-card card-analysis">
        <Text className="card-label">{t('dashboard.analysisCount')}</Text>
        <Text className="card-value">{data.analysis_count}</Text>
        <Text className="card-sub">{t('dashboard.times')}</Text>
      </View>

      {/* 训练频次卡片 */}
      <View className="overview-card card-training">
        <Text className="card-label">{t('dashboard.trainingFreq')}</Text>
        <Text className="card-value">{data.training_frequency_per_week}</Text>
        <Text className="card-sub">{t('dashboard.timesPerWeek')}</Text>
      </View>

      {/* 连续天数卡片 */}
      <View className="overview-card card-streak">
        <Text className="card-label">{t('dashboard.streakDays')}</Text>
        <Text className="card-value">{data.streak_days}</Text>
        <Text className="card-sub">{t('dashboard.days')}</Text>
      </View>

      {/* 训练提醒横幅（降级用户 latest_advice_summary 恒为 null，R12-Dash-2） */}
      {data.latest_advice_summary && (
        <View className="advice-banner">
          <Text className="advice-text">{data.latest_advice_summary.summary}</Text>
          {data.latest_advice_summary.has_unresolved_issues && (
            <Text className="advice-tag">{t('dashboard.hasIssues')}</Text>
          )}
        </View>
      )}
    </View>
  )
}
