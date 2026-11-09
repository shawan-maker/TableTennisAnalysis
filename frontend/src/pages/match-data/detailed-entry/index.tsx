/**
 * 详细录入页（05-match_data/frontend.md §4.2）
 * 逐分记录技术动作：添加得分（方式弹窗）→ 明细列表（左滑删除）→ 自动累计比分 → 提交
 *
 * NutUI 2.x Swipe 组件为 leftAction/rightAction（ReactNode）API，
 * 设计样例的 right=[{text,onClick}] 数组 API 为 1.x 形态，按真实 API 对齐（FS1 惯例）。
 */
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Input, Toast, Popup, Swipe } from '@nutui/nutui-react'
import { useMatchDataStore } from '@/stores/matchDataStore'
import { useTranslation } from 'react-i18next'
import { FORMAT_OPTIONS, MATCH_TYPE_OPTIONS, SCORE_METHODS } from '@/constants/scoring'
import type { ScoreDetailItem } from '@/services/matchData'
import './index.scss'

export default function DetailedEntry() {
  const { t } = useTranslation()
  const { createRecord, isLoading } = useMatchDataStore()

  const [opponentName, setOpponentName] = useState('')
  const [opponentRating, setOpponentRating] = useState('')
  const [myScore, setMyScore] = useState('0')
  const [oppScore, setOppScore] = useState('0')
  const [formatIdx, setFormatIdx] = useState(4) // custom
  const [typeIdx, setTypeIdx] = useState(0) // friendly
  const [details, setDetails] = useState<ScoreDetailItem[]>([])
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')
  const [showMethodDialog, setShowMethodDialog] = useState(false)
  const [pendingScorer, setPendingScorer] = useState<'user' | 'opponent'>('user')

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  /** 添加得分 */
  const handleAddScore = useCallback((scorer: 'user' | 'opponent') => {
    setPendingScorer(scorer)
    setShowMethodDialog(true)
  }, [])

  /** 选择得分方式后添加到列表并自动累计比分 */
  const handleMethodSelect = useCallback(
    (method: string, technique?: string) => {
      setShowMethodDialog(false)
      const seq = details.length + 1
      setDetails([
        ...details,
        {
          sequence: seq,
          scorer: pendingScorer,
          score_method: method as ScoreDetailItem['score_method'],
          technique_action: technique,
        },
      ])
      // 自动更新比分
      if (pendingScorer === 'user') {
        setMyScore(String(parseInt(myScore || '0', 10) + 1))
      } else {
        setOppScore(String(parseInt(oppScore || '0', 10) + 1))
      }
    },
    [details, pendingScorer, myScore, oppScore]
  )

  /** 删除某条明细（左滑删除，重排序号并重算比分） */
  const handleDeleteDetail = useCallback(
    (seq: number) => {
      const newDetails = details
        .filter((d) => d.sequence !== seq)
        .map((d, idx) => ({ ...d, sequence: idx + 1 }))
      setDetails(newDetails)
      // 重新计算比分
      const userCount = newDetails.filter((d) => d.scorer === 'user').length
      const oppCount = newDetails.filter((d) => d.scorer === 'opponent').length
      setMyScore(String(userCount))
      setOppScore(String(oppCount))
    },
    [details]
  )

  /** 提交 */
  const handleSubmit = useCallback(async () => {
    if (!opponentName.trim()) {
      showToast(t('matchData.fillOpponentName'))
      return
    }
    if (details.length === 0) {
      showToast(t('matchData.needAtLeastOneDetail'))
      return
    }
    if (myScore === oppScore) {
      showToast(t('matchData.scoreCannotBeEqual'))
      return
    }

    try {
      const result = await createRecord({
        opponent_name: opponentName.trim(),
        opponent_rating: opponentRating ? parseInt(opponentRating, 10) : undefined,
        my_score: parseInt(myScore, 10),
        opponent_score: parseInt(oppScore, 10),
        format: FORMAT_OPTIONS[formatIdx].value,
        match_type: MATCH_TYPE_OPTIONS[typeIdx].value,
        match_date: new Date().toISOString(),
        details,
      })
      showToast(result.is_win ? t('matchData.recordWin') : t('matchData.recordLose'))
      setTimeout(() => Taro.navigateBack(), 1500)
    } catch (err: any) {
      showToast(err?.message || t('matchData.createFailed'))
    }
  }, [opponentName, opponentRating, myScore, oppScore, formatIdx, typeIdx, details, createRecord, t])

  return (
    <View className="detailed-entry">
      {/* 页面标题 */}
      <View className="entry-header">
        <Text className="entry-title">{t('matchData.detailedEntry')}</Text>
        <Text className="entry-desc">{t('matchData.detailedEntryDesc')}</Text>
      </View>

      {/* 对手信息 */}
      <Cell
        title={t('matchData.opponentName')}
        extra={
          <Input
            className="cell-input"
            placeholder={t('matchData.opponentNamePlaceholder')}
            value={opponentName}
            maxLength={64}
            onChange={(val: string) => setOpponentName(val)}
          />
        }
      />

      <Cell
        title={t('matchData.opponentRating')}
        extra={
          <Input
            className="cell-input"
            type="number"
            placeholder={t('matchData.opponentRatingPlaceholder')}
            value={opponentRating}
            maxLength={4}
            onChange={(val: string) => setOpponentRating(val)}
          />
        }
      />

      {/* 赛制 */}
      <Cell
        title={t('matchData.format')}
        extra={
          <Picker
            mode="selector"
            range={FORMAT_OPTIONS.map((o) => t(o.labelKey))}
            value={formatIdx}
            onChange={(e: any) => setFormatIdx(parseInt(e.detail.value, 10))}
          >
            <View className="picker-value">{t(FORMAT_OPTIONS[formatIdx].labelKey)}</View>
          </Picker>
        }
      />

      {/* 比赛类型 */}
      <Cell
        title={t('matchData.matchType')}
        extra={
          <Picker
            mode="selector"
            range={MATCH_TYPE_OPTIONS.map((o) => t(o.labelKey))}
            value={typeIdx}
            onChange={(e: any) => setTypeIdx(parseInt(e.detail.value, 10))}
          >
            <View className="picker-value">{t(MATCH_TYPE_OPTIONS[typeIdx].labelKey)}</View>
          </Picker>
        }
      />

      {/* 当前比分 */}
      <View className="current-score-bar" aria-live="polite">
        <Text className="current-label">{t('matchData.currentScore')}</Text>
        <Text className="current-score">
          {myScore} : {oppScore}
        </Text>
      </View>

      {/* 添加得分按钮 */}
      <View className="add-score-buttons">
        <Button
          className="btn-add btn-add-user"
          size="large"
          type="primary"
          aria-label={t('matchData.iScored')}
          onClick={() => handleAddScore('user')}
        >
          {t('matchData.iScored')}
        </Button>
        <Button
          className="btn-add btn-add-opp"
          size="large"
          aria-label={t('matchData.opponentScored')}
          onClick={() => handleAddScore('opponent')}
        >
          {t('matchData.opponentScored')}
        </Button>
      </View>

      {/* 得分明细列表（左滑删除） */}
      <View className="detail-list">
        <Text className="detail-list-title">
          {t('matchData.scoreDetails')} ({details.length})
        </Text>
        {details.map((d) => (
          <Swipe
            key={d.sequence}
            rightAction={
              <Button
                className="btn-swipe-delete"
                size="small"
                type="primary"
                aria-label={t('common.delete')}
                onClick={() => handleDeleteDetail(d.sequence)}
              >
                {t('common.delete')}
              </Button>
            }
          >
            <View className="detail-item">
              <Text className="detail-seq">#{d.sequence}</Text>
              <Text className={`detail-scorer ${d.scorer}`}>
                {d.scorer === 'user' ? t('matchData.me') : t('matchData.opponent')}
              </Text>
              <Text className="detail-method">{t(`scoring.method.${d.score_method}`)}</Text>
              {d.technique_action && (
                <Text className="detail-technique">{t(`scoring.technique.${d.technique_action}`)}</Text>
              )}
            </View>
          </Swipe>
        ))}
      </View>

      {/* 提交按钮 */}
      <View className="entry-actions">
        <Button type="primary" block loading={isLoading} onClick={handleSubmit}>
          {t('matchData.submit')}
        </Button>
      </View>

      {/* 得分方式选择弹窗（底部 Popup，2 列 Grid） */}
      <Popup
        visible={showMethodDialog}
        position="bottom"
        round
        onClose={() => setShowMethodDialog(false)}
      >
        <View className="method-sheet">
          <Text className="method-title">{t('matchData.selectMethod')}</Text>
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

      <Toast visible={toastVisible} content={toastMsg} onClose={() => setToastVisible(false)} />
    </View>
  )
}
