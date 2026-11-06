/**
 * 建议区域组件（07-training_advice/frontend.md §4.3）
 * 进步确认/持续问题/新问题/首次分析四类，左边框色区分
 */
import { View, Text } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import type { SuggestionItem } from '@/services/training'
import './SuggestionSection.scss'

interface Props {
  suggestions: SuggestionItem[]
}

/** 建议类型映射（§7 SUGGESTION_TYPE_MAP，labelKey 对应 i18n training.*） */
const SUGGESTION_STYLE_MAP: Record<
  string,
  { icon: string; color: string; labelKey: string }
> = {
  progress_confirm: {
    icon: '✅',
    color: 'var(--color-success)',
    labelKey: 'training.progressConfirm',
  },
  persistent_warning: {
    icon: '⚠️',
    color: 'var(--color-accent)',
    labelKey: 'training.persistentWarning',
  },
  new_issue: {
    icon: '🔴',
    color: 'var(--color-primary)',
    labelKey: 'training.newIssue',
  },
  first_analysis: {
    icon: 'ℹ️',
    color: 'var(--color-secondary)',
    labelKey: 'training.firstAnalysis',
  },
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
        const style = SUGGESTION_STYLE_MAP[item.type] || SUGGESTION_STYLE_MAP.new_issue

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
