# match_data 模块 — 前端垂直切片设计

> **模块名称**：`match_data`
> **前端目录**：`frontend/src/pages/match-data/` + `frontend/src/services/matchData.ts` + `frontend/src/stores/matchDataStore.ts`
> **定位**：快速录入页（只录总比分）、详细录入页（逐分技术动作）、比赛记录列表页
> **依据**：前端需求与界面设计 v2.0 §T2.5、API 详细设计 v1.3 §7

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §T2.5（比赛数据手动录入）
- [ ] 阅读本模块的 API 契约（§7.1-7.3，3 个端点）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 阅读 scoring 前端文档（共用得分方式常量、技术动作常量）
- [ ] 确认本切片范围：快速录入页 + 详细录入页 + 比赛记录列表页 + matchData Store

---

## 2. API Service 模块

```typescript
// frontend/src/services/matchData.ts
import request from './request'

/** 逐分明细条目 */
export interface ScoreDetailItem {
  sequence: number
  scorer: 'user' | 'opponent'
  score_method: 'serve_point' | 'rally_point' | 'opponent_error'
  technique_action?: string
}

/** 创建比赛记录参数 */
export interface MatchRecordCreateParams {
  opponent_name: string
  opponent_rating?: number
  my_score: number
  opponent_score: number
  format: 'bo1' | 'bo3' | 'bo5' | 'bo7' | 'custom'
  match_type: 'friendly' | 'tournament' | 'training'
  match_date: string
  details?: ScoreDetailItem[] | null
  match_id?: number
}

/** 比赛记录列表项 */
export interface MatchRecordListItem {
  id: number
  opponent_name: string
  opponent_rating?: number
  my_score: number
  opponent_score: number
  is_win: boolean
  format: string
  match_type: string
  match_date: string
}

/** 比赛记录详情 */
export interface MatchRecordDetailItem extends MatchRecordListItem {
  match_id?: number
  is_detailed: boolean
  details: ScoreDetailItem[]
}

/**
 * 创建比赛记录（快速/详细录入统一入口）。
 */
export function createRecord(params: MatchRecordCreateParams) {
  return request.post('/match-data/records', params)
}

/**
 * 获取比赛记录列表。
 * @param result - 胜负筛选: win/lose/all
 * @param page - 页码
 * @param pageSize - 每页条数
 */
export function listRecords(result?: string, page = 1, pageSize = 20) {
  return request.get('/match-data/records', { result: result || 'all', page, page_size: pageSize })
}

/**
 * 获取比赛记录详情（含逐分明细）。
 */
export function getRecord(id: number) {
  return request.get(`/match-data/records/${id}`)
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/matchDataStore.ts
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import * as matchDataApi from '@/services/matchData'
import type { MatchRecordListItem, MatchRecordDetailItem } from '@/services/matchData'

interface MatchDataState {
  // 列表
  records: MatchRecordListItem[]
  total: number
  page: number
  isLoading: boolean

  // 详情
  currentDetail: MatchRecordDetailItem | null

  // Actions
  fetchRecords: (result?: string, page?: number) => Promise<void>
  fetchDetail: (id: number) => Promise<void>
  createRecord: (params: matchDataApi.MatchRecordCreateParams) => Promise<{ id: number; is_win: boolean }>
  clearDetail: () => void
}

export const useMatchDataStore = create<MatchDataState>((set, get) => ({
  records: [],
  total: 0,
  page: 1,
  isLoading: false,
  currentDetail: null,

  fetchRecords: async (result = 'all', page = 1) => {
    set({ isLoading: true })
    try {
      const res = await matchDataApi.listRecords(result, page)
      const data = res.data.data
      if (page === 1) {
        set({ records: data.items })
      } else {
        set({ records: [...get().records, ...data.items] })
      }
      set({ total: data.total, page })
    } finally {
      set({ isLoading: false })
    }
  },

  fetchDetail: async (id) => {
    set({ isLoading: true })
    try {
      const res = await matchDataApi.getRecord(id)
      set({ currentDetail: res.data.data })
    } finally {
      set({ isLoading: false })
    }
  },

  createRecord: async (params) => {
    set({ isLoading: true })
    try {
      const res = await matchDataApi.createRecord(params)
      return res.data.data
    } finally {
      set({ isLoading: false })
    }
  },

  clearDetail: () => set({ currentDetail: null }),
}))
```

---

## 4. 主要页面组件

### 4.1 快速录入页

```tsx
// frontend/src/pages/match-data/quick-entry.tsx
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Input, Toast } from '@nutui/nutui-react'
import { useMatchDataStore } from '@/stores/matchDataStore'
import { useTranslation } from 'react-i18next'
import { FORMAT_OPTIONS, MATCH_TYPE_OPTIONS } from '@/constants/scoring'
import './quick-entry.scss'

export default function QuickEntry() {
  const { t } = useTranslation()
  const { createRecord, isLoading } = useMatchDataStore()

  const [opponentName, setOpponentName] = useState('')
  const [opponentRating, setOpponentRating] = useState('')
  const [myScore, setMyScore] = useState('')
  const [oppScore, setOppScore] = useState('')
  const [formatIdx, setFormatIdx] = useState(2) // bo5
  const [typeIdx, setTypeIdx] = useState(0)    // friendly
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
        opponent_rating: opponentRating ? parseInt(opponentRating) : undefined,
        my_score: parseInt(myScore),
        opponent_score: parseInt(oppScore),
        format: FORMAT_OPTIONS[formatIdx].value as any,
        match_type: MATCH_TYPE_OPTIONS[typeIdx].value as any,
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
          placeholder={t('matchData.opponentNamePlaceholder')}
          value={opponentName}
          maxLength={64}
          onChange={(val) => setOpponentName(val)}
        />
      </Cell>

      <Cell title={t('matchData.opponentRating')}>
        <Input
          type="number"
          placeholder={t('matchData.opponentRatingPlaceholder')}
          value={opponentRating}
          maxlength={4}
          onChange={(val) => setOpponentRating(val)}
        />
      </Cell>

      {/* 赛制选择 */}
      <Cell title={t('matchData.format')}>
        <Picker
          mode="selector"
          range={FORMAT_OPTIONS.map(o => o.label)}
          value={formatIdx}
          onChange={(e: any) => setFormatIdx(parseInt(e.detail.value))}
        >
          <View className="picker-value">{FORMAT_OPTIONS[formatIdx].label}</View>
        </Picker>
      </Cell>

      <Cell title={t('matchData.matchType')}>
        <Picker
          mode="selector"
          range={MATCH_TYPE_OPTIONS.map(o => o.label)}
          value={typeIdx}
          onChange={(e: any) => setTypeIdx(parseInt(e.detail.value))}
        >
          <View className="picker-value">{MATCH_TYPE_OPTIONS[typeIdx].label}</View>
        </Picker>
      </Cell>

      {/* 比分输入 */}
      <View className="score-input-section">
        <View className="score-input-side">
          <Text className="score-input-label">{t('matchData.myScore')}</Text>
          <Input
            type="number"
            className="score-input-number"
            placeholder="0"
            value={myScore}
            maxlength={2}
            onChange={(val) => setMyScore(val)}
          />
        </View>
        <Text className="score-input-colon">:</Text>
        <View className="score-input-side">
          <Text className="score-input-label">{t('matchData.oppScore')}</Text>
          <Input
            type="number"
            className="score-input-number"
            placeholder="0"
            value={oppScore}
            maxlength={2}
            onChange={(val) => setOppScore(val)}
          />
        </View>
      </View>

      {/* 提交按钮 */}
      <View className="entry-actions">
        <Button
          type="primary"
          block
          loading={isLoading}
          onClick={handleSubmit}
        >
          {t('matchData.submit')}
        </Button>
      </View>

      {/* 切换到详细录入 */}
      <View className="entry-switch" onClick={() => Taro.redirectTo({ url: '/pages/match-data/detailed-entry/index' })}>
        <Text>{t('matchData.switchToDetailed')}</Text>
      </View>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

### 4.2 详细录入页（逐分技术动作）

```tsx
// frontend/src/pages/match-data/detailed-entry.tsx
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Input, Toast, Popup, SwipeAction } from '@nutui/nutui-react'
import { useMatchDataStore } from '@/stores/matchDataStore'
import { useTranslation } from 'react-i18next'
import { FORMAT_OPTIONS, MATCH_TYPE_OPTIONS, SCORE_METHODS } from '@/constants/scoring'
import type { ScoreDetailItem } from '@/services/matchData'
import './detailed-entry.scss'

export default function DetailedEntry() {
  const { t } = useTranslation()
  const { createRecord, isLoading } = useMatchDataStore()

  const [opponentName, setOpponentName] = useState('')
  const [opponentRating, setOpponentRating] = useState('')
  const [myScore, setMyScore] = useState('')
  const [oppScore, setOppScore] = useState('')
  const [formatIdx, setFormatIdx] = useState(4) // custom
  const [typeIdx, setTypeIdx] = useState(0)
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

  /** 选择得分方式后添加到列表 */
  const handleMethodSelect = useCallback((method: string, technique?: string) => {
    setShowMethodDialog(false)
    const seq = details.length + 1
    setDetails([...details, {
      sequence: seq,
      scorer: pendingScorer,
      score_method: method as any,
      technique_action: technique,
    }])
    // 自动更新比分
    if (pendingScorer === 'user') {
      setMyScore(prev => String(parseInt(prev || '0') + 1))
    } else {
      setOppScore(prev => String(parseInt(prev || '0') + 1))
    }
  }, [details, pendingScorer])

  /** 删除某条明细 */
  const handleDeleteDetail = useCallback((seq: number) => {
    const newDetails = details.filter(d => d.sequence !== seq)
      .map((d, idx) => ({ ...d, sequence: idx + 1 }))
    setDetails(newDetails)
    // 重新计算比分
    const userCount = newDetails.filter(d => d.scorer === 'user').length
    const oppCount = newDetails.filter(d => d.scorer === 'opponent').length
    setMyScore(String(userCount))
    setOppScore(String(oppCount))
  }, [details])

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
        opponent_rating: opponentRating ? parseInt(opponentRating) : undefined,
        my_score: parseInt(myScore),
        opponent_score: parseInt(oppScore),
        format: FORMAT_OPTIONS[formatIdx].value as any,
        match_type: MATCH_TYPE_OPTIONS[typeIdx].value as any,
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
      <Cell title={t('matchData.opponentName')}>
        <Input
          placeholder={t('matchData.opponentNamePlaceholder')}
          value={opponentName}
          maxLength={64}
          onChange={(val) => setOpponentName(val)}
        />
      </Cell>

      <Cell title={t('matchData.opponentRating')}>
        <Input
          type="number"
          placeholder={t('matchData.opponentRatingPlaceholder')}
          value={opponentRating}
          maxlength={4}
          onChange={(val) => setOpponentRating(val)}
        />
      </Cell>

      {/* 赛制 */}
      <Cell title={t('matchData.format')}>
        <Picker
          mode="selector"
          range={FORMAT_OPTIONS.map(o => o.label)}
          value={formatIdx}
          onChange={(e: any) => setFormatIdx(parseInt(e.detail.value))}
        >
          <View className="picker-value">{FORMAT_OPTIONS[formatIdx].label}</View>
        </Picker>
      </Cell>

      {/* 当前比分 */}
      <View className="current-score-bar">
        <Text className="current-label">{t('matchData.currentScore')}</Text>
        <Text className="current-score">{myScore} : {oppScore}</Text>
      </View>

      {/* 添加得分按钮 */}
      <View className="add-score-buttons">
        <Button className="btn-add btn-add-user" size="large" onClick={() => handleAddScore('user')}>
          {t('matchData.iScored')}
        </Button>
        <Button className="btn-add btn-add-opp" size="large" onClick={() => handleAddScore('opponent')}>
          {t('matchData.opponentScored')}
        </Button>
      </View>

      {/* 得分明细列表 */}
      <View className="detail-list">
        <Text className="detail-list-title">{t('matchData.scoreDetails')} ({details.length})</Text>
        {details.map((d) => (
          <SwipeAction
            key={d.sequence}
            right={[
              { text: t('common.delete'), style: { background: 'var(--color-primary)' }, onClick: () => handleDeleteDetail(d.sequence) },
            ]}
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
          </SwipeAction>
        ))}
      </View>

      {/* 提交按钮 */}
      <View className="entry-actions">
        <Button
          type="primary"
          block
          loading={isLoading}
          onClick={handleSubmit}
        >
          {t('matchData.submit')}
        </Button>
      </View>

      {/* 得分方式选择弹窗（底部 Popup） */}
      <Popup
        visible={showMethodDialog}
        title={t('matchData.selectMethod')}
        position="bottom"
        onClose={() => setShowMethodDialog(false)}
      >
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
      </Popup>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

### 4.3 比赛记录列表页

```tsx
// frontend/src/pages/match-data/record-list.tsx
import { useState, useEffect, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Empty, Skeleton } from '@nutui/nutui-react'
import { useMatchDataStore } from '@/stores/matchDataStore'
import { useTranslation } from 'react-i18next'
import './record-list.scss'

export default function RecordList() {
  const { t } = useTranslation()
  const { records, total, page, isLoading, fetchRecords } = useMatchDataStore()
  const [resultFilter, setResultFilter] = useState<'all' | 'win' | 'lose'>('all')

  useEffect(() => {
    fetchRecords(resultFilter, 1)
  }, [resultFilter, fetchRecords])

  const handleCreate = () => {
    Taro.navigateTo({ url: '/pages/match-data/quick-entry/index' })
  }

  const handleItemClick = (id: number) => {
    Taro.navigateTo({ url: `/pages/match-data/record-detail/index?id=${id}` })
  }

  const handleLoadMore = () => {
    if (!isLoading && records.length < total) {
      fetchRecords(resultFilter, page + 1)
    }
  }

  return (
    <View className="record-list">
      {/* 创建按钮 */}
      <View className="list-header">
        <Button type="primary" size="small" onClick={handleCreate}>
          {t('matchData.newRecord')}
        </Button>
      </View>

      {/* 胜负筛选 */}
      <View className="filter-bar">
        {(['all', 'win', 'lose'] as const).map(key => (
          <Text
            key={key}
            className={`filter-tag ${resultFilter === key ? 'active' : ''}`}
            onClick={() => setResultFilter(key)}
          >
            {t(`matchData.filter.${key}`)}
          </Text>
        ))}
      </View>

      {/* 列表 */}
      {records.length === 0 && !isLoading ? (
        <Empty description={t('matchData.noRecords')} />
      ) : (
        <View className="record-cards">
          {records.map(item => (
            <View
              key={item.id}
              className="record-card"
              onClick={() => handleItemClick(item.id)}
            >
              <View className="card-top">
                <Text className="card-opponent">{item.opponent_name}</Text>
                <Text className={`card-result ${item.is_win ? 'win' : 'lose'}`}>
                  {item.is_win ? t('matchData.win') : t('matchData.lose')}
                </Text>
              </View>
              <View className="card-bottom">
                <Text className="card-score">
                  {item.my_score} : {item.opponent_score}
                </Text>
                <Text className="card-format">{item.format}</Text>
                <Text className="card-date">{item.match_date.slice(0, 10)}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 上拉加载更多 */}
      {records.length < total && (
        <View className="load-more" onClick={handleLoadMore}>
          {isLoading ? <Skeleton width="60%" height="16px" animated /> : <Text>{t('common.loadMore')}</Text>}
        </View>
      )}
    </View>
  )
}
```

### 4.4 比赛记录详情页

```tsx
// frontend/src/pages/match-data/record-detail.tsx
import { useEffect } from 'react'
import { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Skeleton } from '@nutui/nutui-react'
import { useMatchDataStore } from '@/stores/matchDataStore'
import { useTranslation } from 'react-i18next'
import './record-detail.scss'

export default function RecordDetail() {
  const { t } = useTranslation()
  const router = useRouter()
  const recordId = parseInt(router.params.id as string)
  const { currentDetail, fetchDetail } = useMatchDataStore()

  useEffect(() => {
    if (recordId) fetchDetail(recordId)
  }, [recordId])

  if (!currentDetail) {
    return <View className="record-detail loading"><Skeleton rows={3} animated /></View>
  }

  const { opponent_name, opponent_rating, my_score, opponent_score, is_win, format, match_type, match_date, details } = currentDetail

  return (
    <View className="record-detail">
      {/* 结果卡片 */}
      <View className="result-card">
        <Text className={`result-badge ${is_win ? 'win' : 'lose'}`}>
          {is_win ? t('matchData.win') : t('matchData.lose')}
        </Text>
        <Text className="result-score">{my_score} : {opponent_score}</Text>
        <Text className="result-opponent">{t('matchData.vs')} {opponent_name}</Text>
      </View>

      {/* 比赛信息 */}
      <Cell title={t('matchData.format')}>{format}</Cell>
      <Cell title={t('matchData.matchType')}>{t(`scoring.matchType.${match_type}`)}</Cell>
      {opponent_rating && (
        <Cell title={t('matchData.opponentRating')}>{opponent_rating}</Cell>
      )}
      <Cell title={t('matchData.matchDate')}>{match_date.slice(0, 10)}</Cell>

      {/* 逐分明细 */}
      {details && details.length > 0 && (
        <View className="details-section">
          <Text className="section-title">{t('matchData.scoreDetails')} ({details.length})</Text>
          {details.map((d, idx) => (
            <View key={idx} className="detail-row">
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
```

---

## 5. 样式

### 5.1 快速录入页样式

```scss
// frontend/src/pages/match-data/quick-entry.scss
.quick-entry {
  min-height: 100vh;
  background: var(--color-background);
  padding: 0 var(--spacing-md);
}

.entry-header {
  padding: var(--spacing-lg) 0 var(--spacing-md);

  .entry-title {
    display: block;
    font-size: 24px;
    font-weight: bold;
    color: var(--color-primary);
  }

  .entry-desc {
    display: block;
    margin-top: var(--spacing-xs);
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.picker-value {
  color: var(--color-text-primary);
  font-size: 15px;
}

/* 比分输入区 */
.score-input-section {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg) var(--spacing-md);
  background: var(--color-card);
  border-radius: var(--radius-md);
  margin: var(--spacing-md) 0;
}

.score-input-side {
  display: flex;
  flex-direction: column;
  align-items: center;

  .score-input-label {
    font-size: 13px;
    color: var(--color-text-secondary);
    margin-bottom: var(--spacing-sm);
  }

  .score-input-number {
    width: 80px;
    height: 64px;
    text-align: center;
    font-size: 32px;
    font-weight: bold;
    color: var(--color-primary);
    border: 2px solid var(--color-divider);
    border-radius: var(--radius-sm);
  }
}

.score-input-colon {
  font-size: 32px;
  font-weight: bold;
  color: var(--color-text-secondary);
}

.entry-actions {
  margin-top: var(--spacing-lg);
  padding-bottom: var(--spacing-md);

  :global(.nut-button.primary) {
    background: var(--color-primary);
    border-radius: var(--radius-md);
    height: 48px;
    font-size: 18px;
  }
}

.entry-switch {
  text-align: center;
  padding: var(--spacing-md);
  color: var(--color-secondary);
  font-size: 13px;
}
```

### 5.2 详细录入页样式

```scss
// frontend/src/pages/match-data/detailed-entry.scss
.detailed-entry {
  min-height: 100vh;
  background: var(--color-background);
  padding: 0 var(--spacing-md);
}

/* 当前比分条 */
.current-score-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm-md) var(--spacing-md);
  background: var(--color-card);
  border-radius: var(--radius-sm);
  margin: var(--spacing-md) 0;

  .current-label {
    font-size: 13px;
    color: var(--color-text-secondary);
  }

  .current-score {
    font-size: 24px;
    font-weight: bold;
    color: var(--color-primary);
  }
}

/* 添加得分按钮 */
.add-score-buttons {
  display: flex;
  gap: var(--spacing-sm-md);
  margin-bottom: var(--spacing-md);
}

.btn-add {
  flex: 1;
  height: 80px !important;
  font-size: 18px !important;
  font-weight: bold !important;
  border-radius: var(--radius-md) !important;
}

.btn-add-user {
  background: var(--color-primary) !important;
  color: var(--color-text-inverse) !important;
}

.btn-add-opp {
  background: var(--color-secondary) !important;
  color: var(--color-text-inverse) !important;
}

/* 得分明细列表 */
.detail-list {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);

  .detail-list-title {
    display: block;
    font-size: 15px;
    font-weight: bold;
    color: var(--color-secondary);
    margin-bottom: var(--spacing-sm-md);
  }
}

.detail-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm-md);
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--color-divider);

  .detail-seq {
    font-size: 13px;
    color: var(--color-text-secondary);
    min-width: 32px;
  }

  .detail-scorer {
    font-size: 13px;
    font-weight: bold;
    min-width: 48px;

    &.user { color: var(--color-primary); }
    &.opponent { color: var(--color-secondary); }
  }

  .detail-method {
    font-size: 13px;
    color: var(--color-text-primary);
  }

  .detail-technique {
    font-size: 12px;
    color: var(--color-accent);
    background: color-mix(in srgb, var(--color-accent) 10%, transparent);
    padding: var(--spacing-xs) var(--spacing-sm);
    border-radius: var(--radius-sm);
  }
}

.method-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-sm-md);
  padding: var(--spacing-md);
}

.btn-method {
  border-radius: var(--radius-sm) !important;
}
```

### 5.3 比赛记录列表页样式

```scss
// frontend/src/pages/match-data/record-list.scss
.record-list {
  min-height: 100vh;
  background: var(--color-background);
  padding: var(--spacing-md);
}

.list-header {
  margin-bottom: var(--spacing-md);
  display: flex;
  justify-content: flex-end;
}

.filter-bar {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);

  .filter-tag {
    flex: 1;
    text-align: center;
    padding: var(--spacing-sm) 0;
    border-radius: var(--radius-sm);
    font-size: 13px;
    background: var(--color-card);
    color: var(--color-text-secondary);

    &.active {
      background: var(--color-primary);
      color: var(--color-text-inverse);
    }
  }
}

.record-cards {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm-md);
}

.record-card {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);

  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--spacing-sm-md);

    .card-opponent {
      font-size: 15px;
      font-weight: bold;
      color: var(--color-text-primary);
    }

    .card-result {
      font-size: 12px;
      padding: var(--spacing-xs) var(--spacing-sm-md);
      border-radius: var(--radius-md);
      font-weight: bold;

      &.win { background: var(--color-success); color: var(--color-text-inverse); }
      &.lose { background: var(--color-warning); color: var(--color-text-inverse); }
    }
  }

  .card-bottom {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm-md);

    .card-score {
      font-size: 24px;
      font-weight: bold;
      color: var(--color-primary);
    }

    .card-format {
      font-size: 12px;
      color: var(--color-text-secondary);
    }

    .card-date {
      margin-left: auto;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
  }
}

.load-more {
  text-align: center;
  padding: var(--spacing-md);
  color: var(--color-text-secondary);
  font-size: 13px;
}
```

### 5.4 比赛记录详情页样式

```scss
// frontend/src/pages/match-data/record-detail.scss
.record-detail {
  min-height: 100vh;
  background: var(--color-background);
  padding: var(--spacing-md);
}

.result-card {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  text-align: center;
  margin-bottom: var(--spacing-md);

  .result-badge {
    display: inline-block;
    padding: var(--spacing-xs) var(--spacing-lg);
    border-radius: var(--radius-md);
    font-size: 13px;
    font-weight: bold;
    margin-bottom: var(--spacing-sm);

    &.win { background: var(--color-success); color: var(--color-text-inverse); }
    &.lose { background: var(--color-warning); color: var(--color-text-inverse); }
  }

  .result-score {
    display: block;
    font-size: 32px;
    font-weight: bold;
    color: var(--color-primary);
    margin-bottom: var(--spacing-sm);
  }

  .result-opponent {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.details-section {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-top: var(--spacing-md);

  .section-title {
    display: block;
    font-size: 15px;
    font-weight: bold;
    color: var(--color-secondary);
    margin-bottom: var(--spacing-sm-md);
  }
}

.detail-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm-md);
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--color-divider);

  .detail-seq {
    font-size: 13px;
    color: var(--color-text-secondary);
    min-width: 32px;
  }

  .detail-scorer {
    font-size: 13px;
    font-weight: bold;
    min-width: 48px;

    &.user { color: var(--color-primary); }
    &.opponent { color: var(--color-secondary); }
  }

  .detail-method {
    font-size: 13px;
    color: var(--color-text-primary);
  }

  .detail-technique {
    font-size: 12px;
    color: var(--color-accent);
    background: color-mix(in srgb, var(--color-accent) 10%, transparent);
    padding: var(--spacing-xs) var(--spacing-sm);
    border-radius: var(--radius-sm);
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 match-data 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    // scoring 模块页面
    'pages/scoring/setup/index',
    'pages/scoring/scoreboard/index',
    'pages/scoring/statistics/index',
    'pages/scoring/match-list/index',
    // match-data 模块页面
    'pages/match-data/quick-entry/index',    // 快速录入
    'pages/match-data/detailed-entry/index', // 详细录入
    'pages/match-data/record-list/index',    // 比赛记录列表
    'pages/match-data/record-detail/index',  // 比赛记录详情
    // ... 其他页面
  ],
}
```

---

## 7. 常量与 i18n

### 常量复用

match_data 模块复用 scoring 模块定义的常量：
- `FORMAT_OPTIONS` — 赛制选项
- `MATCH_TYPE_OPTIONS` — 比赛类型选项
- `SCORE_METHODS` — 得分方式（详细录入时使用）

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增 matchData 条目）
{
  "matchData": {
    "quickEntry": "快速录入",
    "quickEntryDesc": "只记录总比分，快速完成录入",
    "detailedEntry": "详细录入",
    "detailedEntryDesc": "逐分记录技术动作，生成精准统计",
    "opponentName": "对手姓名",
    "opponentNamePlaceholder": "请输入对手姓名",
    "opponentRating": "对手积分",
    "opponentRatingPlaceholder": "选填",
    "format": "赛制",
    "matchType": "比赛类型",
    "myScore": "我的得分",
    "oppScore": "对手得分",
    "scoreCannotBeEqual": "比分不能相同",
    "fillOpponentName": "请填写对手姓名",
    "fillScore": "请填写比分",
    "submit": "提交",
    "switchToDetailed": "切换到详细录入 →",
    "selectMethod": "选择得分方式",
    "iScored": "我得分",
    "opponentScored": "对手得分",
    "scoreDetails": "得分明细",
    "needAtLeastOneDetail": "至少录入一条得分",
    "currentScore": "当前比分",
    "createFailed": "录入失败",
    "recordWin": "已记录：胜利",
    "recordLose": "已记录：失败",
    "win": "胜",
    "lose": "负",
    "vs": "VS",
    "me": "我",
    "opponent": "对手",
    "newRecord": "录入比赛",
    "noRecords": "暂无比赛记录",
    "matchDate": "比赛日期",
    "filter": {
      "all": "全部",
      "win": "胜场",
      "lose": "负场"
    }
  }
}
```

```json
// frontend/src/locales/en-US.json（新增 matchData 条目）
{
  "matchData": {
    "quickEntry": "Quick Entry",
    "quickEntryDesc": "Record final score only, fast entry",
    "detailedEntry": "Detailed Entry",
    "detailedEntryDesc": "Record each point with technique action",
    "opponentName": "Opponent Name",
    "opponentNamePlaceholder": "Enter opponent name",
    "opponentRating": "Opponent Rating",
    "opponentRatingPlaceholder": "Optional",
    "format": "Format",
    "matchType": "Match Type",
    "myScore": "My Score",
    "oppScore": "Opponent Score",
    "scoreCannotBeEqual": "Scores cannot be equal",
    "fillOpponentName": "Please enter opponent name",
    "fillScore": "Please enter scores",
    "submit": "Submit",
    "switchToDetailed": "Switch to Detailed Entry →",
    "selectMethod": "Select Method",
    "iScored": "I Scored",
    "opponentScored": "Opponent Scored",
    "scoreDetails": "Score Details",
    "needAtLeastOneDetail": "At least one score required",
    "currentScore": "Current Score",
    "createFailed": "Entry failed",
    "recordWin": "Recorded: Win",
    "recordLose": "Recorded: Loss",
    "win": "Win",
    "lose": "Loss",
    "vs": "VS",
    "me": "Me",
    "opponent": "Opponent",
    "newRecord": "New Record",
    "noRecords": "No records yet",
    "matchDate": "Match Date",
    "filter": {
      "all": "All",
      "win": "Wins",
      "lose": "Losses"
    }
  }
}
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 快速录入页布局：对手信息 + 赛制选择 + 比分输入（双列居中）+ 提交按钮
- [ ] 比分输入框使用大字号（32px），醒目可读
- [ ] 详细录入页大按钮（80px）单手可操作
- [ ] 得分明细列表支持左滑删除（SwipeAction）
- [ ] 得分方式弹窗使用 2 列 Grid 布局
- [ ] 比赛记录列表卡片使用成功色 `#2A9D8F`（胜）和警告色 `#F4A261`（负）
- [ ] 详情页结果卡片使用大比分数字（48px）

### 功能验证
- [ ] 快速录入：填写对手 + 比分 → 提交 → Toast 显示胜负 → 返回
- [ ] 详细录入：添加得分 → 选择方式 → 自动更新比分 → 左滑删除 → 提交
- [ ] 快速录入 ↔ 详细录入可切换
- [ ] 比赛记录列表：按全部/胜场/负场筛选 → 点击进入详情
- [ ] 详情页展示逐分明细（如有）
- [ ] 上拉加载更多
- [ ] 比分相同时前端拦截 + 后端校验

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/matchData.ts` 封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 比分输入使用数字键盘，**禁止** 文本输入
- **ALL** 详细录入的逐分明细支持左滑删除（`SwipeAction`）
- **ALL** 常量复用 scoring 模块定义（`FORMAT_OPTIONS`、`MATCH_TYPE_OPTIONS`、`SCORE_METHODS`）
- **禁止** 使用 class 组件
- **禁止** 硬编码颜色值，使用 CSS 变量
- **禁止** 安装新的 npm 包
