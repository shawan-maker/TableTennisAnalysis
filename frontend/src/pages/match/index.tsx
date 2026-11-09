/**
 * 赛事 Tab 入口页（14-tab-pages/match-tab.md §4）
 * 页面标题 + 记分牌入口卡（含进行中比分预览）+ 比赛记录入口卡（含最近战绩预览）。
 *
 * FS7-P3 契约同步（与设计样例的差异，以后端实际契约为准）：
 * - 进行中预览字段 MatchBrief.current_score_user/current_score_opp/status='in_progress'
 *   （设计样例 my_score/opponent_score/ongoing 为臆造；端点 /scoring/current 不存在，
 *   改 listMatches('in_progress') 取首条，见 services/matchTab.ts）；
 * - Skeleton 2.7.14 真实 API 为 rows/animated（无 width/height，FS5 先例）。
 */
import { useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useMatchTabStore } from '@/stores/matchTabStore'
import { MATCH_ROUTES } from '@/constants/matchTab'
import './index.scss'

/** 赛事入口项 */
interface MatchEntry {
  icon: string
  titleKey: string
  descKey: string
  route: string
  colorVar: string
}

const MATCH_ENTRIES: MatchEntry[] = [
  {
    icon: '🏓',
    titleKey: 'matchTab.scoreboard',
    descKey: 'matchTab.scoreboardDesc',
    route: MATCH_ROUTES.scoreboard,
    colorVar: 'var(--color-primary)',
  },
  {
    icon: '📋',
    titleKey: 'matchTab.matchRecords',
    descKey: 'matchTab.matchRecordsDesc',
    route: MATCH_ROUTES.matchRecords,
    colorVar: 'var(--color-secondary)',
  },
]

export default function MatchTabPage() {
  const { t } = useTranslation()
  const {
    latestMatch,
    latestMatchLoading,
    currentScoring,
    currentScoringLoading,
    refreshAll,
  } = useMatchTabStore()

  useEffect(() => {
    refreshAll()
  }, [refreshAll])

  /** 记分牌预览内容（FS7-P3：MatchBrief 实际字段） */
  const scoringPreview = () => {
    if (currentScoringLoading && !currentScoring) {
      return <Skeleton rows={1} animated />
    }
    if (currentScoring) {
      return (
        <View className="preview-row">
          <Text className="preview-score">
            {currentScoring.current_score_user} - {currentScoring.current_score_opp}
          </Text>
          <Text className="preview-badge ongoing">{t('matchTab.ongoing')}</Text>
        </View>
      )
    }
    return <Text className="preview-empty">{t('matchTab.noScoring')}</Text>
  }

  /** 比赛记录预览内容（MatchRecordListItem：my_score/opponent_score/is_win） */
  const matchPreview = () => {
    if (latestMatchLoading && !latestMatch) {
      return <Skeleton rows={1} animated />
    }
    if (latestMatch) {
      return (
        <View className="preview-row">
          <Text className="preview-score">
            {latestMatch.my_score} - {latestMatch.opponent_score}
          </Text>
          <Text className={`preview-result ${latestMatch.is_win ? 'win' : 'lose'}`}>
            {latestMatch.is_win ? t('matchTab.win') : t('matchTab.lose')}
          </Text>
        </View>
      )
    }
    return <Text className="preview-empty">{t('matchTab.noMatch')}</Text>
  }

  const handleNavigate = (entry: MatchEntry) => {
    Taro.navigateTo({ url: entry.route })
  }

  const previewFor = (idx: number) => (idx === 0 ? scoringPreview() : matchPreview())

  return (
    <View className="match-tab-page">
      {/* 页面标题 */}
      <View className="page-header">
        <Text className="page-title">{t('matchTab.title')}</Text>
        <Text className="page-subtitle">{t('matchTab.subtitle')}</Text>
      </View>

      {MATCH_ENTRIES.map((entry, idx) => (
        <View
          className="entry-card"
          key={entry.route}
          onClick={() => handleNavigate(entry)}
        >
          <View
            className="entry-icon-wrapper"
            style={{ background: `color-mix(in srgb, ${entry.colorVar} 10%, transparent)` }}
          >
            <Text className="entry-icon" style={{ color: entry.colorVar }}>
              {entry.icon}
            </Text>
          </View>
          <View className="entry-content">
            <Text className="entry-title">{t(entry.titleKey)}</Text>
            <Text className="entry-desc">{t(entry.descKey)}</Text>
            <View className="entry-preview">{previewFor(idx)}</View>
          </View>
          <Text className="entry-arrow">›</Text>
        </View>
      ))}
    </View>
  )
}
