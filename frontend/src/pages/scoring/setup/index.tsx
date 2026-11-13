/**
 * 比赛设置页（04-scoring/frontend.md §4.1）
 * 对手信息 + 赛制/类型选择 → 创建比赛 → 跳转实时记分页
 */
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Input, Toast } from '@nutui/nutui-react'
import { useScoringStore } from '@/stores/scoringStore'
import { useUserStore } from '@/stores/userStore'
import { useTranslation } from 'react-i18next'
import { FORMAT_OPTIONS, MATCH_TYPE_OPTIONS, OPPONENT_STYLE_OPTIONS, TARGET_SCORE_OPTIONS } from '@/constants/scoring'
import './index.scss'

export default function MatchSetup() {
  const { t } = useTranslation()
  const { createMatch, isLoading } = useScoringStore()
  // R-FE-R2 批次E（FE-P3-27）：本人档案只读展示（v1.0 L481-482「你的信息：姓名/积分」）
  const userProfile = useUserStore((s) => s.profile)
  const [opponentName, setOpponentName] = useState('')
  const [opponentRating, setOpponentRating] = useState('')
  // R-FE-R2 批次G（FE-P2-14）：对手打法四选项（v1.0 L487）；
  // idx 0 = 未选择不传（后端 Optional Literal），1-4 映射四打法
  const [styleIdx, setStyleIdx] = useState(0)
  const [formatIdx, setFormatIdx] = useState(2) // 默认 bo5
  const [typeIdx, setTypeIdx] = useState(0) // 默认 friendly
  // R-FE-R1 批次C（FE-P2-13）：每局目标分（v1.0 L478 21 分制承诺；后端契约 1-21）
  const [targetScoreIdx, setTargetScoreIdx] = useState(0) // 默认 11 分制
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  const handleCreate = useCallback(async () => {
    if (!opponentName.trim()) {
      showToast(t('scoring.fillOpponentName'))
      return
    }
    try {
      const matchId = await createMatch({
        opponent_name: opponentName.trim(),
        opponent_rating: opponentRating ? parseInt(opponentRating, 10) : undefined,
        opponent_playing_style:
          styleIdx > 0 ? OPPONENT_STYLE_OPTIONS[styleIdx - 1].value : undefined,
        format: FORMAT_OPTIONS[formatIdx].value,
        match_type: MATCH_TYPE_OPTIONS[typeIdx].value,
        target_score: TARGET_SCORE_OPTIONS[targetScoreIdx].value,
      })
      // 跳转到实时记分页（记分页检测 status=setup 时自动调 start，后端 X-21）
      Taro.redirectTo({ url: `/pages/scoring/scoreboard/index?matchId=${matchId}` })
    } catch (err: any) {
      showToast(err?.message || t('scoring.createFailed'))
    }
  }, [opponentName, opponentRating, styleIdx, formatIdx, typeIdx, targetScoreIdx, createMatch, t])

  return (
    <View className="match-setup">
      {/* 页面标题 */}
      <View className="setup-header">
        <Text className="setup-title">{t('scoring.matchSetup')}</Text>
      </View>

      {/* 你的信息（R-FE-R2 批次E FE-P3-27：v1.0 L481-482 只读档案区，读 userStore 缓存，未加载时不渲染） */}
      {userProfile && (
        <View className="my-profile-row">
          <Text className="profile-label">{t('scoring.yourInfo')}</Text>
          <Text className="profile-value">
            {userProfile.nickname} · {t('scoring.myPoints')}{' '}
            {userProfile.profile.kqs_rating ?? '-'}
          </Text>
        </View>
      )}

      {/* 对手信息 */}
      <Cell
        title={t('scoring.opponentName')}
        extra={
          <Input
            className="cell-input"
            placeholder={t('scoring.opponentNamePlaceholder')}
            value={opponentName}
            maxLength={64}
            onChange={(val: string) => setOpponentName(val)}
          />
        }
      />

      <Cell
        title={t('scoring.opponentRating')}
        extra={
          <Input
            className="cell-input"
            type="number"
            placeholder={t('scoring.opponentRatingPlaceholder')}
            value={opponentRating}
            maxLength={4}
            onChange={(val: string) => setOpponentRating(val)}
          />
        }
      />

      {/* 对手打法（R-FE-R2 批次G FE-P2-14：v1.0 L487 四选项，选填 idx 0 不传） */}
      <Cell
        title={t('scoring.opponentPlayingStyle')}
        extra={
          <Picker
            mode="selector"
            range={[
              t('scoring.playStyle_unselected'),
              ...OPPONENT_STYLE_OPTIONS.map((o) => t(o.labelKey)),
            ]}
            value={styleIdx}
            onChange={(e: any) => setStyleIdx(parseInt(e.detail.value, 10))}
          >
            <View className="picker-value">
              {styleIdx > 0 ? t(OPPONENT_STYLE_OPTIONS[styleIdx - 1].labelKey) : t('scoring.playStyle_unselected')}
            </View>
          </Picker>
        }
      />

      {/* 赛制选择 */}
      <Cell
        title={t('scoring.format')}
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
        title={t('scoring.matchType')}
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

      {/* 每局目标分（R-FE-R1 批次C FE-P2-13：11/21 切换，替代硬编码 11） */}
      <Cell
        title={t('scoring.targetScore')}
        extra={
          <Picker
            mode="selector"
            range={TARGET_SCORE_OPTIONS.map((o) => t(o.labelKey))}
            value={targetScoreIdx}
            onChange={(e: any) => setTargetScoreIdx(parseInt(e.detail.value, 10))}
          >
            <View className="picker-value">{t(TARGET_SCORE_OPTIONS[targetScoreIdx].labelKey)}</View>
          </Picker>
        }
      />

      {/* 创建按钮 */}
      <View className="setup-actions">
        <Button type="primary" block loading={isLoading} onClick={handleCreate}>
          {t('scoring.startMatch')}
        </Button>
      </View>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
