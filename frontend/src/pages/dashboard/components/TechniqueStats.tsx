/**
 * 技术统计环形图组件（06-data_dashboard/frontend.md §4.4）
 * weapp 端 conic-gradient 实现（样例 SVG stroke-dasharray 为 H5 端方案）；
 * 后端 technique_distribution 已带 name(中文)/value/color 三元组
 */
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { TechniqueStatsData } from '@/services/dashboard'
import './TechniqueStats.scss'

interface Props {
  data: TechniqueStatsData | null
  loading: boolean
}

export default function TechniqueStats({ data, loading }: Props) {
  const { t } = useTranslation()

  if (loading || !data) {
    return (
      <View className="technique-stats">
        <Text className="section-title">🏓 {t('dashboard.techniqueStats')}</Text>
        <Skeleton rows={3} animated />
      </View>
    )
  }

  // 防御缺字段（E2E-02 实证：形状漂移时 undefined.reduce 会崩掉整页渲染树）
  const items = data.technique_distribution ?? []
  const total = items.reduce((sum, item) => sum + item.value, 0)

  if (total === 0) {
    return (
      <View className="technique-stats">
        <Text className="section-title">🏓 {t('dashboard.techniqueStats')}</Text>
        <View className="empty-state">
          <Text>{t('dashboard.noTechniqueData')}</Text>
        </View>
      </View>
    )
  }

  // conic-gradient 分段（后端下发每项 color）
  let acc = 0
  const stops: string[] = []
  items.forEach((item) => {
    const pct = (item.value / total) * 100
    stops.push(`${item.color} ${acc}%, ${item.color} ${acc + pct}%`)
    acc += pct
  })
  const gradient = `conic-gradient(${stops.join(', ')})`

  return (
    <View className="technique-stats">
      <Text className="section-title">🏓 {t('dashboard.techniqueStats')}</Text>
      <View className="technique-content">
        {/* 环形图（conic-gradient + 内圆挖洞） */}
        <View
          className="donut-chart"
          style={{ background: gradient }}
          role="img"
          aria-label={`${t('dashboard.techniqueStats')}: ${items
            .map((i) => `${i.name} ${(i.value / total * 100).toFixed(0)}%`)
            .join(', ')}`}
        >
          <View className="donut-hole">
            <Text className="hole-label">{t('dashboard.total')}</Text>
            <Text className="hole-value">{total}</Text>
          </View>
        </View>

        {/* 图例 */}
        <View className="legend-list">
          {items.map((item, i) => (
            <View className="legend-item" key={i}>
              <View className="legend-dot" style={{ background: item.color }} />
              <Text className="legend-name">{item.name}</Text>
              <Text className="legend-value">
                {item.value} ({((item.value / total) * 100).toFixed(0)}%)
              </Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  )
}
