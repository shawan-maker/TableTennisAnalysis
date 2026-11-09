/**
 * 比赛统计页（04-scoring/frontend.md §4.3）
 * 比赛结果卡片 + 得分分布 + 技术动作分解 + 关键分 + 总得分
 */
import { useEffect } from 'react'
import { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Skeleton } from '@nutui/nutui-react'
import { useScoringStore } from '@/stores/scoringStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function MatchStatisticsPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const matchId = parseInt((router.params.matchId || '0') as string, 10)
  const { currentMatch, currentStatistics, fetchMatch, fetchStatistics } = useScoringStore()

  useEffect(() => {
    if (matchId) {
      fetchMatch(matchId)
      fetchStatistics(matchId)
    }
  }, [matchId])

  if (!currentMatch || !currentStatistics || currentMatch.id !== matchId) {
    return (
      <View className="match-stats loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const { stats_data } = currentStatistics
  const { score_distribution, technique_breakdown, key_points, total_points } = stats_data

  return (
    <View className="match-stats">
      {/* 比赛结果卡片 */}
      <View className="result-card">
        <Text className={`result-title ${currentMatch.is_win ? 'win' : 'lose'}`}>
          {currentMatch.is_win ? t('scoring.youWin') : t('scoring.youLose')}
        </Text>
        <Text className="result-score">{currentMatch.final_score}</Text>
        <Text className="result-opponent">
          {t('scoring.vs')} {currentMatch.opponent_name}
        </Text>
      </View>

      {/* 得分分布 */}
      <View className="stats-section">
        <Text className="section-title">{t('scoring.scoreDistribution')}</Text>
        <View className="distribution-list">
          {Object.entries(score_distribution).map(([method, count]) => (
            <Cell
              key={method}
              title={t(`scoring.method.${method}`)}
              extra={<Text className="dist-count">{count}</Text>}
            />
          ))}
        </View>
      </View>

      {/* 技术动作分解 */}
      <View className="stats-section">
        <Text className="section-title">{t('scoring.techniqueBreakdown')}</Text>
        <View className="technique-list">
          {Object.entries(technique_breakdown).map(([tech, count]) => (
            <Cell
              key={tech}
              title={t(`scoring.technique.${tech}`)}
              extra={<Text className="dist-count">{count}</Text>}
            />
          ))}
        </View>
      </View>

      {/* 关键分 */}
      {key_points && key_points.length > 0 && (
        <View className="stats-section">
          <Text className="section-title">{t('scoring.keyPoints')}</Text>
          <View className="key-points-list">
            {key_points.map((kp, idx) => (
              <View key={`${kp.seq}-${idx}`} className="key-point-item">
                <Text className="kp-seq">#{kp.seq}</Text>
                <Text className={`kp-winner ${kp.winner}`}>
                  {kp.winner === 'user' ? t('scoring.me') : t('scoring.opponent')}
                </Text>
                <Text className="kp-score">{kp.score}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 总分 */}
      <View className="total-points">
        <Text>{t('scoring.totalPoints')}: {total_points}</Text>
      </View>
    </View>
  )
}
