/**
 * 训练积分卡片组件（09-gamification/frontend.md §4.1）
 * 总积分 + 本月积分 + 连续天数（streak>=3 火焰）+ 最近积分动态
 *
 * FS5-P3：设计定位「嵌入首页 Dashboard」，首页聚合归 FS7 升级，
 * 本 Sprint 嵌入打卡日历页顶部（streak 上下文关联，语义一致）。
 * R-FE-R1 批次A（FE-P1-9）：注记后半句兑现——已嵌入首页 Dashboard
 * （home/index.tsx，QuickGrid 与打卡日历之间），打卡页保留展示。
 * R2-P2-2（批次H）：最近动态区——消费 POINTS_SOURCE_MAP（此前零消费孤儿
 * 常量），数据源为 GET /gamification/points-history 积分流水分页端点。
 */
import { useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useGamificationStore } from '@/stores/gamificationStore'
import { POINTS_SOURCE_MAP } from '@/constants/gamification'
import './PointsCard.scss'

/** 积分来源标签文案（六来源映射外的事件由 sourceOther 兜底） */
export function pointsSourceLabel(
  t: (k: string) => string,
  eventType: string
): string {
  return t(POINTS_SOURCE_MAP[eventType] ?? 'gamification.sourceOther')
}

/** 相对时间（今日/昨日/MM-DD，后端 created_at 为 ISO 墙钟） */
function formatRelativeDate(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  if (sameDay(d, now)) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 最近动态展示条数 */
const RECENT_LIMIT = 5

export default function PointsCard() {
  const { t } = useTranslation()
  const points = useGamificationStore((s) => s.points)
  const isLoadingPoints = useGamificationStore((s) => s.isLoadingPoints)
  const fetchPoints = useGamificationStore((s) => s.fetchPoints)
  // R2-P2-2（批次H）：积分流水（最近动态）
  const pointsHistory = useGamificationStore((s) => s.pointsHistory)
  const fetchPointsHistory = useGamificationStore((s) => s.fetchPointsHistory)

  useEffect(() => {
    fetchPoints()
    fetchPointsHistory(1, RECENT_LIMIT)
  }, [fetchPoints, fetchPointsHistory])

  if (isLoadingPoints && !points) {
    return (
      <View className="points-card loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const streak = points?.current_streak ?? 0
  const showFlame = streak >= 3
  const recentItems = (pointsHistory?.items ?? []).slice(0, RECENT_LIMIT)

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

      {/* R2-P2-2（批次H）：最近积分动态（POINTS_SOURCE_MAP 消费） */}
      {recentItems.length > 0 && (
        <View className="points-recent">
          <Text className="recent-title">{t('gamification.recentActivity')}</Text>
          {recentItems.map((item) => (
            <View key={item.id} className="recent-row">
              <Text className="recent-source">{pointsSourceLabel(t, item.event_type)}</Text>
              <Text className="recent-date">{formatRelativeDate(item.created_at)}</Text>
              <Text className="recent-points">+{item.points}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  )
}
