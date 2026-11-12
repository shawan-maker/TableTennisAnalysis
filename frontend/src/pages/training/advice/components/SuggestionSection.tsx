/**
 * 建议区域组件（07-training_advice/frontend.md §4.3）
 * 进步确认/持续问题/新问题/首次分析四类，左边框色区分
 */
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import type { SuggestionItem } from '@/services/training'
// R-FE-R2（FE-P3-17）：SUGGESTION_TYPE 映射收敛至 constants/training（§7 L1870-1904）
import { SUGGESTION_TYPE_MAP } from '@/constants/training'
import './SuggestionSection.scss'

interface Props {
  suggestions: SuggestionItem[]
}

export default function SuggestionSection({ suggestions }: Props) {
  const { t } = useTranslation()

  if (suggestions.length === 0) {
    return (
      <View className="suggestion-section">
        <Text className="section-title">🏋️ {t('training.suggestions')}</Text>
        <View className="empty-state">
          <Text>{t('training.noSuggestions')}</Text>
        </View>
      </View>
    )
  }

  return (
    <View className="suggestion-section">
      <Text className="section-title">🏋️ {t('training.suggestions')}</Text>
      {suggestions.map((item, i) => {
        // R-FE-R2（FE-P3-17）：映射外值兜底 new_issue（与原内联 SUGGESTION_STYLE_MAP 行为一致）
        const style = SUGGESTION_TYPE_MAP[item.type] || SUGGESTION_TYPE_MAP.new_issue

        return (
          <View
            className="suggestion-card"
            key={`${item.type}-${i}`}
            style={{ borderLeftColor: style.color }}
          >
            <View className="suggestion-header">
              <Text className="suggestion-icon">{style.icon}</Text>
              <Text className="suggestion-type" style={{ color: style.color }}>
                {t(style.labelKey)}
              </Text>
            </View>
            <Text className="suggestion-text">{item.text}</Text>
          </View>
        )
      })}
    </View>
  )
}
