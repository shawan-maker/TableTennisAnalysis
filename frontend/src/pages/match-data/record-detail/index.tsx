/**
 * 比赛记录详情页（05-match_data/frontend.md §4.4）
 * 结果卡片 + 比赛信息 + 逐分明细（如有）
 */
import { useEffect } from 'react'
import { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Skeleton } from '@nutui/nutui-react'
import { useMatchDataStore } from '@/stores/matchDataStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function RecordDetail() {
  const { t } = useTranslation()
  const router = useRouter()
  const recordId = parseInt((router.params.id || '0') as string, 10)
  const { currentDetail, fetchDetail, clearDetail } = useMatchDataStore()

  useEffect(() => {
    if (recordId) fetchDetail(recordId)
    return () => {
      // 离开页面清空详情态，避免下一条详情闪现旧数据
      clearDetail()
    }
  }, [recordId])

  if (!currentDetail || (recordId && currentDetail.id !== recordId)) {
    return (
      <View className="record-detail loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const { opponent_name, opponent_rating, my_score, opponent_score, is_win, format, match_type, match_date, details } =
    currentDetail

  return (
    <View className="record-detail">
      {/* 结果卡片 */}
      <View className="result-card">
        <Text className={`result-badge ${is_win ? 'win' : 'lose'}`}>
          {is_win ? t('matchData.win') : t('matchData.lose')}
        </Text>
        <Text className="result-score">
          {my_score} : {opponent_score}
        </Text>
        <Text className="result-opponent">
          {t('matchData.vs')} {opponent_name}
        </Text>
      </View>

      {/* 比赛信息 */}
      <Cell title={t('matchData.format')} extra={<Text className="cell-text">{format}</Text>} />
      <Cell
        title={t('matchData.matchType')}
        extra={<Text className="cell-text">{t(`scoring.matchType_${match_type}`)}</Text>}
      />
      {opponent_rating != null && (
        <Cell
          title={t('matchData.opponentRating')}
          extra={<Text className="cell-text">{opponent_rating}</Text>}
        />
      )}
      <Cell
        title={t('matchData.matchDate')}
        extra={<Text className="cell-text">{(match_date || '').slice(0, 10)}</Text>}
      />

      {/* 逐分明细 */}
      {details && details.length > 0 && (
        <View className="details-section">
          <Text className="section-title">
            {t('matchData.scoreDetails')} ({details.length})
          </Text>
          {details.map((d, idx) => (
            <View key={`${d.sequence}-${idx}`} className="detail-row">
              <Text className="detail-seq">#{d.sequence}</Text>
              <Text className={`detail-scorer ${d.scorer}`}>
                {d.scorer === 'user' ? t('matchData.me') : t('matchData.opponent')}
              </Text>
              <Text className="detail-method">{t(`scoring.method.${d.score_method}`)}</Text>
              {d.technique_action && (
                <Text className="detail-technique">{t(`scoring.technique.${d.technique_action}`)}</Text>
              )}
            </View>
          ))}
        </View>
      )}
    </View>
  )
}
