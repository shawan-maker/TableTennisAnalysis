/**
 * 比赛统计页（04-scoring/frontend.md §4.3）
 * 比赛结果卡片 + 得分分布 + 技术动作分解 + 关键分 + 总得分
 *
 * R-FE-R1 批次B/C：赛后动作三件套（分享/关联视频/看板，v1.0 L573-580 +
 * v2.0 L1430 流程 2 尾段「统计 → 数据看板 → 关联视频」——修复前三入口零命中）；
 * 逐局比分明细（FE-P2-12，v1.0 L557-558）；分布计数+占比（FE-P3-13）；
 * 关键分聚合（FE-P3-28，v1.0 L568-569）。
 */
import { useEffect, useMemo, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Button, Skeleton, Toast } from '@nutui/nutui-react'
import { useScoringStore } from '@/stores/scoringStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function MatchStatisticsPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const matchId = parseInt((router.params.matchId || '0') as string, 10)
  const { currentMatch, currentStatistics, fetchMatch, fetchStatistics } = useScoringStore()

  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  useEffect(() => {
    if (matchId) {
      fetchMatch(matchId)
      fetchStatistics(matchId)
    }
  }, [matchId])

  // R-FE-R1（FE-P2-12）：逐局比分——score_sequence 按 game_number 分组，
  // 每条记录为一分，按局计数还原各局比分（bo 多局大比分为局分语义）
  const gamesDetail = useMemo(() => {
    const seq = currentMatch?.score_sequence || []
    const byGame = new Map<number, { user: number; opp: number }>()
    seq.forEach((r) => {
      const g = byGame.get(r.game_number) || { user: 0, opp: 0 }
      if (r.scorer === 'user') g.user++
      else g.opp++
      byGame.set(r.game_number, g)
    })
    return Array.from(byGame.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([game, s]) => ({ game, ...s }))
  }, [currentMatch?.score_sequence])

  if (!currentMatch || !currentStatistics || currentMatch.id !== matchId) {
    return (
      <View className="match-stats loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const { stats_data } = currentStatistics
  const { score_distribution, technique_breakdown, key_points, total_points } = stats_data

  // R-FE-R1（FE-P2-9）：分享比赛结果——Phase 1 按 report 页先例剪贴板复制比分文本
  const handleShareResult = () => {
    const text = `乒乓AI：${currentMatch.is_win ? t('scoring.youWin') : t('scoring.youLose')} ${currentMatch.final_score} (${t('scoring.vs')} ${currentMatch.opponent_name})`
    Taro.setClipboardData({ data: text })
    showToast(t('scoring.shareCopied'))
  }

  // R-FE-R1（FE-P3-28）：关键分聚合——我方拿下的关键分占比（纯前端计算）
  const kpWon = (key_points || []).filter((kp) => kp.winner === 'user').length
  const kpTotal = (key_points || []).length
  const kpPct = kpTotal > 0 ? Math.round((kpWon / kpTotal) * 100) : 0

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
        {/* R-FE-R1（FE-P2-12）：逐局比分明细（bo 多局模式，如 (11-7, 8-11, 11-9)） */}
        {gamesDetail.length > 1 && (
          <Text className="result-games-detail">
            ({gamesDetail.map((g) => `${g.user}-${g.opp}`).join(', ')})
          </Text>
        )}
      </View>

      {/* 得分分布 */}
      <View className="stats-section">
        <Text className="section-title">{t('scoring.scoreDistribution')}</Text>
        <View className="distribution-list">
          {Object.entries(score_distribution).map(([method, count]) => (
            <Cell
              key={method}
              title={t(`scoring.method.${method}`)}
              extra={
                <Text className="dist-count">
                  {count} ({total_points > 0 ? Math.round((count / total_points) * 100) : 0}%)
                </Text>
              }
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

          <Text className="kp-summary">
            {t('scoring.keyPointsSummary', { won: kpWon, total: kpTotal, pct: kpPct })}
          </Text>
        </View>
      )}

      {/* 总分 */}
      <View className="total-points">
        <Text>{t('scoring.totalPoints')}: {total_points}</Text>
      </View>

      {/* R-FE-R1 批次B（FE-P2-9/10/11）：赛后动作三件套——修复前统计页
          是流程 2 终点、三入口全工程零命中；FE-P2-10 携带 matchId 供后续关联 */}
      <View className="post-match-actions">
        <Button className="btn-post-match" size="small" onClick={handleShareResult}>
          {t('scoring.shareResult')}
        </Button>
        <Button
          className="btn-post-match"
          size="small"
          onClick={() =>
            Taro.navigateTo({ url: `/pages/video-analysis/upload/index?matchId=${matchId}` })
          }
        >
          {t('scoring.linkVideoAnalysis')}
        </Button>
        <Button
          className="btn-post-match"
          size="small"
          onClick={() => Taro.navigateTo({ url: '/pages/dashboard/index' })}
        >
          {t('scoring.viewDashboard')}
        </Button>
      </View>

      <Toast visible={toastVisible} content={toastMsg} onClose={() => setToastVisible(false)} />
    </View>
  )
}
