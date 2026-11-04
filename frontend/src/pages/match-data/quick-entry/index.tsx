/**
 * 快速录入页（05-match_data/frontend.md §4.1）
 * 只录总比分：对手信息 + 赛制/类型 + 比分 → 提交
 */
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Input, Toast } from '@nutui/nutui-react'
import { useMatchDataStore } from '@/stores/matchDataStore'
import { useTranslation } from 'react-i18next'
import { FORMAT_OPTIONS, MATCH_TYPE_OPTIONS } from '@/constants/scoring'
import './index.scss'

export default function QuickEntry() {
  const { t } = useTranslation()
  const { createRecord, isLoading } = useMatchDataStore()

  const [opponentName, setOpponentName] = useState('')
  const [opponentRating, setOpponentRating] = useState('')
  const [myScore, setMyScore] = useState('')
  const [oppScore, setOppScore] = useState('')
  const [formatIdx, setFormatIdx] = useState(2) // bo5
  const [typeIdx, setTypeIdx] = useState(0) // friendly
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  const handleSubmit = useCallback(async () => {
    if (!opponentName.trim()) {
      showToast(t('matchData.fillOpponentName'))
      return
    }
    if (myScore === '' || oppScore === '') {
      showToast(t('matchData.fillScore'))
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
        details: null,
      })
      showToast(result.is_win ? t('matchData.recordWin') : t('matchData.recordLose'))
      // 延迟返回
      setTimeout(() => Taro.navigateBack(), 1500)
    } catch (err: any) {
      showToast(err?.message || t('matchData.createFailed'))
    }
  }, [opponentName, opponentRating, myScore, oppScore, formatIdx, typeIdx, createRecord, t])

  return (
    <View className="quick-entry">
      {/* 页面标题 */}
      <View className="entry-header">
        <Text className="entry-title">{t('matchData.quickEntry')}</Text>
        <Text className="entry-desc">{t('matchData.quickEntryDesc')}</Text>
      </View>

      {/* 对手信息 */}
      <Cell title={t('matchData.opponentName')}>
        <Input
          className="cell-input"
          placeholder={t('matchData.opponentNamePlaceholder')}
          value={opponentName}
          maxLength={64}
          onChange={(val: string) => setOpponentName(val)}
        />
      </Cell>

      <Cell title={t('matchData.opponentRating')}>
        <Input
          className="cell-input"
          type="number"
          placeholder={t('matchData.opponentRatingPlaceholder')}
          value={opponentRating}
          maxLength={4}
          onChange={(val: string) => setOpponentRating(val)}
        />
      </Cell>

      {/* 赛制选择 */}
      <Cell title={t('matchData.format')}>
        <Picker
          mode="selector"
          range={FORMAT_OPTIONS.map((o) => t(o.labelKey))}
          value={formatIdx}
          onChange={(e: any) => setFormatIdx(parseInt(e.detail.value, 10))}
        >
          <View className="picker-value">{t(FORMAT_OPTIONS[formatIdx].labelKey)}</View>
        </Picker>
      </Cell>

      {/* 比赛类型 */}
      <Cell title={t('matchData.matchType')}>
        <Picker
          mode="selector"
          range={MATCH_TYPE_OPTIONS.map((o) => t(o.labelKey))}
          value={typeIdx}
          onChange={(e: any) => setTypeIdx(parseInt(e.detail.value, 10))}
        >
          <View className="picker-value">{t(MATCH_TYPE_OPTIONS[typeIdx].labelKey)}</View>
        </Picker>
      </Cell>

      {/* 比分输入（数字键盘，双列居中） */}
      <View className="score-input-section">
        <View className="score-input-side">
          <Text className="score-input-label">{t('matchData.myScore')}</Text>
          <Input
            className="score-input-number"
            type="number"
            placeholder="0"
            value={myScore}
            maxLength={2}
            onChange={(val: string) => setMyScore(val)}
          />
        </View>
        <Text className="score-input-colon">:</Text>
        <View className="score-input-side">
          <Text className="score-input-label">{t('matchData.oppScore')}</Text>
          <Input
            className="score-input-number"
            type="number"
            placeholder="0"
            value={oppScore}
            maxLength={2}
            onChange={(val: string) => setOppScore(val)}
          />
        </View>
      </View>

      {/* 提交按钮 */}
      <View className="entry-actions">
        <Button type="primary" block loading={isLoading} onClick={handleSubmit}>
          {t('matchData.submit')}
        </Button>
      </View>

      {/* 切换到详细录入 */}
      <View
        className="entry-switch"
        onClick={() => Taro.redirectTo({ url: '/pages/match-data/detailed-entry/index' })}
      >
        <Text>{t('matchData.switchToDetailed')}</Text>
      </View>

      <Toast visible={toastVisible} content={toastMsg} onClose={() => setToastVisible(false)} />
    </View>
  )
}
