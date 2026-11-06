/**
 * 训练积分卡片组件（09-gamification/frontend.md §4.1）
 * 总积分 + 本月积分 + 连续天数（streak>=3 火焰）
 *
 * FS5-P3：设计定位「嵌入首页 Dashboard」，首页聚合归 FS7 升级，
 * 本 Sprint 嵌入打卡日历页顶部（streak 上下文关联，语义一致）。
 */
import { useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useGamificationStore } from '@/stores/gamificationStore'
import './PointsCard.scss'

export default function PointsCard() {
  const { t } = useTranslation()
  const points = useGamificationStore((s) => s.points)
  const isLoadingPoints = useGamificationStore((s) => s.isLoadingPoints)
  const fetchPoints = useGamificationStore((s) => s.fetchPoints)

  useEffect(() => {
    fetchPoints()
  }, [fetchPoints])

  if (isLoadingPoints && !points) {
    return (
      <View className="points-card loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const streak = points?.current_streak ?? 0
  const showFlame = streak >= 3

  return (
    <View className="points-card">
      <View className="points-header">
        <Text className="points-title">{t('gamification.trainingPoints')}</Text>
      </View>
      <View className="points-body">
        <View className="points-total">
          <Text className="points-number">{points?.total_points ?? 0}</Text>
          <Text className="points-label">{t('gamification.totalPoints')}</Text>
        </View>
        <View className="points-monthly">
          <Text className="points-monthly-number">{points?.monthly_points ?? 0}</Text>
          <Text className="points-monthly-label">{t('gamification.monthlyPoints')}</Text>
        </View>
        <View className="points-streak">
          {showFlame && <Text className="streak-flame">🔥</Text>}
          <Text className="streak-number">{streak}</Text>
          <Text className="streak-label">{t('gamification.dayStreak')}</Text>
        </View>
      </View>
    </View>
  )
}
