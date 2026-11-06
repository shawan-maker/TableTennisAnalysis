/**
 * 训练方法组件（07-training_advice/frontend.md §4.4）
 * 有序号圆形编号 + 方法名 + 描述
 */
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import type { TrainingMethodItem } from '@/services/training'
import './TrainingMethodsSection.scss'

interface Props {
  methods: TrainingMethodItem[]
}

export default function TrainingMethodsSection({ methods }: Props) {
  const { t } = useTranslation()

  if (methods.length === 0) {
    return (
      <View className="methods-section">
        <Text className="section-title">🎯 {t('training.trainingMethods')}</Text>
        <View className="empty-state">
          <Text>{t('training.noMethods')}</Text>
        </View>
      </View>
    )
  }

  return (
    <View className="methods-section">
      <Text className="section-title">🎯 {t('training.trainingMethods')}</Text>
      {methods.map((method, i) => (
        <View className="method-card" key={method.method_id}>
          <View className="method-header">
            <Text className="method-index">{i + 1}</Text>
            <Text className="method-name">{method.name}</Text>
          </View>
          {method.description && (
            <Text className="method-desc">{method.description}</Text>
          )}
        </View>
      ))}
    </View>
  )
}
