/**
 * 数据概览卡片组件（00-home/frontend.md §4.3）
 * 胜率（含胜负明细+趋势箭头）/ 分析次数 / 连续打卡天数 三卡。
 */
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { OverviewData } from '@/services/home'
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
        {[0, 1, 2].map((i) => (
          <View className="overview-card" key={i}>
            {/* NutUI 2.7.14 真实 API：Skeleton 用 rows（无 width/height，FS5 先例） */}
            <Skeleton rows={2} animated />
          </View>
        ))}
      </View>
    )
  }

  if (!data) return null

  const trendIcon = data.trend === 'up' ? '↑' : data.trend === 'down' ? '↓' : '→'
  const trendCls = data.trend === 'up' ? 'trend-up' : data.trend === 'down' ? 'trend-down' : 'trend-flat'

  return (
    <View className="overview-cards">
      {/* 胜率 */}
      <View className="overview-card card-winrate">
        <Text className="card-label">{t('home.winRate')}</Text>
        <Text className="card-value">{(data.win_rate * 100).toFixed(0)}%</Text>
        <Text className={`card-sub ${trendCls}`}>
          {data.wins}{t('home.wins')} / {data.losses}{t('home.losses')} {trendIcon}
        </Text>
      </View>

      {/* 分析次数 */}
      <View className="overview-card card-analysis">
        <Text className="card-label">{t('home.analysisCount')}</Text>
        <Text className="card-value">{data.analysis_count}</Text>
        <Text className="card-sub">{t('home.times')}</Text>
      </View>

      {/* 连续打卡天数 */}
      <View className="overview-card card-streak">
        <Text className="card-label">{t('home.streakDays')}</Text>
        <Text className="card-value">{data.streak_days}</Text>
        <Text className="card-sub">{t('home.days')}</Text>
      </View>
    </View>
  )
}
