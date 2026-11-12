/**
 * 诊断短板组件（07-training_advice/frontend.md §4.2）
 * 问题名 + 严重程度 Tag + 趋势图标 + 描述
 */
import { View, Text } from '@tarojs/components'
import { Tag } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { DiagnosisItem } from '@/services/training'
// R-FE-R2（FE-P3-17）：SEVERITY/TREND 映射收敛至 constants/training（§7 L1870-1904）
import { SEVERITY_MAP, TREND_MAP } from '@/constants/training'
import './DiagnosisSection.scss'

interface Props {
  diagnosis: DiagnosisItem[]
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
        // R-FE-R2（FE-P3-17）：StyleMeta 结构（color/labelKey），映射外值兜底 medium
        const severity = SEVERITY_MAP[item.severity] || SEVERITY_MAP.medium
        const trend = TREND_MAP[item.trend] || TREND_MAP.new

        return (
          <View className="diagnosis-card" key={item.problem_name}>
            <View className="diagnosis-header">
              <Text className="diagnosis-name">{item.problem_name}</Text>
              <Tag background={severity.color} color="var(--color-text-inverse)">
                {t(severity.labelKey)}
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
