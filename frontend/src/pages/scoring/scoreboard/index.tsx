/**
 * 实时记分页（04-scoring/frontend.md §4.2，核心页面）
 * 大按钮单手记分 + 得分方式弹窗 + 撤销 + 结束/放弃 + WS 多设备实时同步
 *
 * 无障碍（总览 §3.8）：大按钮 aria-label + 比分 aria-live="polite" + 触摸目标 ≥120px
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Dialog, Toast, Skeleton, Popup } from '@nutui/nutui-react'
import { useScoringStore } from '@/stores/scoringStore'
import { useMatchSync } from '@/hooks/useMatchSync'
import { useTranslation } from 'react-i18next'
import { SCORE_METHODS } from '@/constants/scoring'
import './index.scss'

export default function Scoreboard() {
  const { t } = useTranslation()
  const router = useRouter()
  const matchId = parseInt((router.params.matchId || '0') as string, 10)
  const { currentMatch, fetchMatch, startMatch, doScore, doUndo, finishMatch, abandonMatch, resumeMatch, isScoring } =
    useScoringStore()
  const { isConnected } = useMatchSync(matchId || null)

  const [showMethodSheet, setShowMethodSheet] = useState(false)
  const [pendingScorer, setPendingScorer] = useState<'user' | 'opponent'>('user')
  const [showFinishDialog, setShowFinishDialog] = useState(false)
  const [showAbandonDialog, setShowAbandonDialog] = useState(false)
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')
  /** 已发起的 start 请求防重入 */
  const startingRef = useRef(false)

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  /** 加载比赛详情；setup 态自动开赛（后端 score 要求 in_progress，X-21） */
  useEffect(() => {
    if (!matchId) return
    let cancelled = false
    const bootstrap = async () => {
      try {
        await fetchMatch(matchId)
        const match = useScoringStore.getState().currentMatch
        if (cancelled || !match || match.id !== matchId) return
        if (match.status === 'setup' && !startingRef.current) {
          startingRef.current = true
          try {
            await startMatch(matchId)
          } catch (err: any) {
            showToast(err?.message || t('scoring.startFailed'))
          } finally {
            startingRef.current = false
          }
        }
      } catch (err: any) {
        showToast(err?.message || t('scoring.startFailed'))
      }
    }
    bootstrap()
    return () => {
      cancelled = true
    }
  }, [matchId])

  /** 已结束的比赛自动跳转统计页（含 WS match_finished 场景兜底） */
  useEffect(() => {
    if (currentMatch?.status === 'finished' && currentMatch.id === matchId) {
      Taro.redirectTo({ url: `/pages/scoring/statistics/index?matchId=${matchId}` })
    }
  }, [currentMatch?.status, currentMatch?.id, matchId])

  /** 点击得分大按钮 */
  const handleScoreClick = useCallback((scorer: 'user' | 'opponent') => {
    setPendingScorer(scorer)
    setShowMethodSheet(true)
  }, [])

  /** 选择得分方式后提交 */
  const handleMethodSelect = useCallback(
    async (method: string, technique?: string) => {
      setShowMethodSheet(false)
      try {
        await doScore(matchId, {
          scorer: pendingScorer,
          score_method: method as 'serve_point' | 'rally_point' | 'opponent_error',
          technique_action: technique,
        })
      } catch (err: any) {
        showToast(err?.message || t('scoring.scoreFailed'))
      }
    },
    [matchId, pendingScorer, doScore, t]
  )

  /** 撤销 */
  const handleUndo = useCallback(async () => {
    try {
      await doUndo(matchId)
    } catch (err: any) {
      showToast(err?.message || t('scoring.undoFailed'))
    }
  }, [matchId, doUndo, t])

  /** 结束比赛 → 跳转统计页 */
  const handleFinish = useCallback(async () => {
    setShowFinishDialog(false)
    try {
      await finishMatch(matchId)
      Taro.redirectTo({ url: `/pages/scoring/statistics/index?matchId=${matchId}` })
    } catch (err: any) {
      showToast(err?.message || t('scoring.finishFailed'))
    }
  }, [matchId, finishMatch, t])

  /** 放弃比赛（X-26：in_progress → abandoned，24h 内可恢复） */
  const handleAbandon = useCallback(async () => {
    setShowAbandonDialog(false)
    try {
      await abandonMatch(matchId)
      Taro.navigateBack()
    } catch (err: any) {
      showToast(err?.message || t('scoring.abandonFailed'))
    }
  }, [matchId, abandonMatch, t])

  /** 恢复放弃的比赛（X-26：abandoned → in_progress，24h 内） */
  const handleResume = useCallback(async () => {
    try {
      await resumeMatch(matchId)
    } catch (err: any) {
      showToast(err?.message || t('scoring.resumeFailed'))
    }
  }, [matchId, resumeMatch, t])

  if (!currentMatch || (currentMatch && matchId && currentMatch.id !== matchId)) {
    return (
      <View className="scoreboard loading">
        <Skeleton rows={3} animated />
      </View>
    )
  }

  const { current_score_user, current_score_opp, current_server, status } = currentMatch
  const seqLength = currentMatch.score_sequence?.length || 0

  return (
    <View className="scoreboard">
      {/* WebSocket 连接状态指示器（断线横幅） */}
      {!isConnected && (
        <View className="ws-banner" aria-live="polite">
          {t('scoring.wsDisconnected')}
        </View>
      )}

      {/* 比分显示区（aria-live：多设备/本人记分即时播报） */}
      <View className="score-display" aria-live="polite" aria-label={t('scoring.matchSetup')}>
        <View className="score-side score-user">
          <Text className="score-name">{t('scoring.me')}</Text>
          <Text className="score-number">{current_score_user}</Text>
          {current_server === 'user' && <Text className="server-badge">🏓</Text>}
        </View>
        <View className="score-vs">
          <Text className="vs-text">VS</Text>
        </View>
        <View className="score-side score-opp">
          <Text className="score-name">{currentMatch.opponent_name}</Text>
          <Text className="score-number">{current_score_opp}</Text>
          {current_server === 'opponent' && <Text className="server-badge">🏓</Text>}
        </View>
      </View>

      {status === 'abandoned' ? (
        /* 已放弃比赛：仅提供恢复（24h 内） */
        <View className="score-buttons">
          <Button className="btn-score btn-user" size="large" type="primary" onClick={handleResume}>
            {t('scoring.resumeMatch')}
          </Button>
        </View>
      ) : (
        <>
          {/* 大按钮记分区（单手操作，≥120px） */}
          <View className="score-buttons">
            <Button
              className="btn-score btn-user"
              size="large"
              type="primary"
              loading={isScoring}
              aria-label={t('scoring.iScored')}
              onClick={() => handleScoreClick('user')}
            >
              {t('scoring.iScored')}
            </Button>
            <Button
              className="btn-score btn-opp"
              size="large"
              loading={isScoring}
              aria-label={t('scoring.opponentScored')}
              onClick={() => handleScoreClick('opponent')}
            >
              {t('scoring.opponentScored')}
            </Button>
          </View>

          {/* 操作按钮区 */}
          <View className="action-bar">
            <Button
              className="btn-action"
              size="small"
              onClick={handleUndo}
              disabled={isScoring || seqLength === 0}
            >
              {t('scoring.undo')}
            </Button>
            <Button
              className="btn-action btn-finish"
              size="small"
              onClick={() => setShowFinishDialog(true)}
              disabled={isScoring}
            >
              {t('scoring.finishMatch')}
            </Button>
            <Button className="btn-action btn-abandon" size="small" onClick={() => setShowAbandonDialog(true)}>
              {t('scoring.abandonMatch')}
            </Button>
          </View>
        </>
      )}

      {/* 得分方式选择弹窗（底部） */}
      <Popup
        visible={showMethodSheet}
        position="bottom"
        round
        onClose={() => setShowMethodSheet(false)}
      >
        <View className="method-sheet">
          <Text className="method-title">{t('scoring.selectMethod')}</Text>
          <View className="method-grid">
            {SCORE_METHODS.map((m) => (
              <Button
                key={`${m.value}-${m.technique || 'none'}`}
                className="btn-method"
                size="small"
                onClick={() => handleMethodSelect(m.value, m.technique)}
              >
                {t(m.labelKey)}
              </Button>
            ))}
          </View>
        </View>
      </Popup>

      {/* 结束比赛确认弹窗 */}
      <Dialog
        title={t('scoring.confirmFinish')}
        visible={showFinishDialog}
        onConfirm={handleFinish}
        onCancel={() => setShowFinishDialog(false)}
        confirmText={t('scoring.finishMatch')}
        cancelText={t('common.cancel')}
      >
        <Text className="dialog-desc">{t('scoring.confirmFinishDesc')}</Text>
      </Dialog>

      {/* 放弃比赛确认弹窗 */}
      <Dialog
        title={t('scoring.confirmAbandon')}
        visible={showAbandonDialog}
        onConfirm={handleAbandon}
        onCancel={() => setShowAbandonDialog(false)}
        confirmText={t('scoring.abandonMatch')}
        cancelText={t('common.cancel')}
      >
        <Text className="dialog-desc">{t('scoring.confirmAbandonDesc')}</Text>
      </Dialog>

      <Toast visible={toastVisible} content={toastMsg} onClose={() => setToastVisible(false)} />
    </View>
  )
}
