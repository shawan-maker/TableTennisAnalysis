/**
 * 诊断短板组件（07-training_advice/frontend.md §4.2）
 * 问题名 + 严重程度 Tag + 趋势图标 + 描述
 */
import { View, Text } from '@tarojs/components'
import { Tag } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { DiagnosisItem } from '@/services/training'
import './DiagnosisSection.scss'

interface Props {
  diagnosis: DiagnosisItem[]
}

/** 严重程度映射（§7 SEVERITY_MAP：低=绿 / 中=橙 / 高=红） */
const SEVERITY_MAP: Record<string, string> = {
  low: 'var(--color-success)',
  medium: 'var(--color-accent)',
  high: 'var(--color-primary)',
}

/** 趋势映射（§7 TREND_MAP，labelKey 对应 i18n training.trend*） */
const TREND_MAP: Record<string, { icon: string; color: string; labelKey: string }> = {
  improving: { icon: '↑', color: 'var(--color-success)', labelKey: 'training.trendImproving' },
  stagnant: { icon: '→', color: 'var(--color-accent)', labelKey: 'training.trendStagnant' },
  declining: { icon: '↓', color: 'var(--color-primary)', labelKey: 'training.trendDeclining' },
  achieved: { icon: '✓', color: 'var(--color-success)', labelKey: 'training.trendAchieved' },
  new: { icon: '★', color: 'var(--color-accent)', labelKey: 'training.trendNew' },
  resolved: { icon: '✓', color: 'var(--color-success)', labelKey: 'training.trendResolved' },
}

export default function DiagnosisSection({ diagnosis }: Props) {
  const { t } = useTranslation()

  if (diagnosis.length === 0) {
    return (
      <View className="diagnosis-section">
        <Text className="section-title">📋 {t('training.diagnosis')}</Text>
        <View className="empty-state">
          <Text>{t('training.noDiagnosis')}</Text>
        </View>
      </View>
    )
  }

  return (
    <View className="diagnosis-section">
      <Text className="section-title">📋 {t('training.diagnosis')}</Text>
      {diagnosis.map((item) => {
        const severityColor = SEVERITY_MAP[item.severity] || SEVERITY_MAP.medium
        const trend = TREND_MAP[item.trend] || TREND_MAP.new

        return (
          <View className="diagnosis-card" key={item.problem_id}>
            <View className="diagnosis-header">
              <Text className="diagnosis-name">{item.problem_name}</Text>
              <Tag background={severityColor} color="var(--color-text-inverse)">
                {t(`training.severity.${item.severity}`)}
              </Tag>
            </View>
            <View className="diagnosis-trend">
              <Text className="trend-icon" style={{ color: trend.color }}>
                {trend.icon}
              </Text>
              <Text className="trend-label" style={{ color: trend.color }}>
                {t(trend.labelKey)}
              </Text>
            </View>
            <Text className="diagnosis-desc">{item.description}</Text>
          </View>
        )
      })}
    </View>
  )
}
