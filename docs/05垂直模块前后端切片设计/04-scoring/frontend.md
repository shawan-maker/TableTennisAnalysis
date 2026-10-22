# scoring 模块 — 前端垂直切片设计

> **模块名称**：`scoring`
> **前端目录**：`frontend/src/pages/scoring/` + `frontend/src/services/scoring.ts` + `frontend/src/stores/scoringStore.ts`
> **定位**：记分牌主界面（比赛设置 → 实时记分 → 比赛结束统计）、比赛列表页、大按钮单手操作 UI
> **依据**：前端需求与界面设计 v2.0 §E3.1-E3.3、API 详细设计 v1.3 §5

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §E3.1（智能记分牌 — 比赛设置）
- [ ] 阅读前端设计 v2.0 §E3.2（智能记分牌 — 实时记分，大按钮单手操作）
- [ ] 阅读前端设计 v2.0 §E3.3（记分牌 — 比赛结束统计）
- [ ] 阅读本模块的 API 契约（§5.1-5.7，7 个端点）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：比赛设置页 + 实时记分页 + 比赛统计页 + 比赛列表页 + scoring Store + WebSocket 订阅

---

## 2. API Service 模块

```typescript
// frontend/src/services/scoring.ts
import request from './request'

/** 比赛创建参数 */
export interface MatchCreateParams {
  opponent_name: string
  opponent_rating?: number
  format: 'bo1' | 'bo3' | 'bo5' | 'bo7' | 'custom'
  match_type: 'friendly' | 'tournament' | 'training'
  target_score: number
}

/** 记分参数 */
export interface ScoreParams {
  scorer: 'user' | 'opponent'
  score_method: 'serve_point' | 'rally_point' | 'opponent_error'
  technique_action?: string
}

/**
 * 创建比赛。
 */
export function createMatch(params: MatchCreateParams) {
  return request.post('/scoring/matches', params)
}

/**
 * 获取比赛列表。
 * @param status - 状态筛选
 * @param page - 页码
 * @param page_size - 每页条数
 */
export function listMatches(status?: string, page = 1, pageSize = 20) {
  return request.get('/scoring/matches', { status, page, page_size: pageSize })
}

/**
 * 获取比赛详情（含比分序列）。
 */
export function getMatch(id: number) {
  return request.get(`/scoring/matches/${id}`)
}

/**
 * 记分（得分方 + 得分方式）。
 */
export function score(matchId: number, params: ScoreParams) {
  return request.post(`/scoring/matches/${matchId}/score`, params)
}

/**
 * 撤销最近一球。
 */
export function undo(matchId: number, expectedSeq?: number) {
  return request.post(`/scoring/matches/${matchId}/undo`, expectedSeq ? { expected_seq: expectedSeq } : null)
}

/**
 * 结束比赛 → 生成统计。
 */
export function finishMatch(matchId: number) {
  return request.post(`/scoring/matches/${matchId}/finish`)
}

/**
 * 获取比赛统计。
 */
export function getStatistics(matchId: number) {
  return request.get(`/scoring/matches/${matchId}/statistics`)
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/scoringStore.ts
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import * as scoringApi from '@/services/scoring'

/** 单条得分记录 */
export interface ScoreRecordItem {
  seq: number
  scorer: 'user' | 'opponent'
  score_method: string
  technique_action?: string
  game_number: number
}

/** 比赛详情 */
export interface MatchDetail {
  id: number
  opponent_name: string
  opponent_rating?: number
  format: string
  match_type: string
  target_score: number
  status: 'setup' | 'in_progress' | 'finished' | 'abandoned'
  current_score_user: number
  current_score_opp: number
  current_server?: 'user' | 'opponent'
  current_game: number
  is_win?: boolean
  final_score?: string
  created_at: string
  finished_at?: string
  score_sequence: ScoreRecordItem[]
}

/** 比赛统计 */
export interface MatchStatistics {
  match_id: number
  stats_data: {
    score_distribution: Record<string, number>
    key_points: Array<{ seq: number; scorer: string; method: string }>
    technique_breakdown: Record<string, number>
    total_points: number
  }
}

interface ScoringState {
  // 当前比赛
  currentMatch: MatchDetail | null
  currentStatistics: MatchStatistics | null
  isLoading: boolean
  isScoring: boolean

  // Actions
  createMatch: (params: scoringApi.MatchCreateParams) => Promise<number>
  fetchMatch: (id: number) => Promise<void>
  doScore: (matchId: number, params: scoringApi.ScoreParams) => Promise<void>
  doUndo: (matchId: number) => Promise<void>
  finishMatch: (matchId: number) => Promise<void>
  fetchStatistics: (matchId: number) => Promise<void>
  clearCurrent: () => void
}

export const useScoringStore = create<ScoringState>((set, get) => ({
  currentMatch: null,
  currentStatistics: null,
  isLoading: false,
  isScoring: false,

  createMatch: async (params) => {
    set({ isLoading: true })
    try {
      const res = await scoringApi.createMatch(params)
      const matchId = res.data.data.match_id
      await get().fetchMatch(matchId)
      return matchId
    } catch (error) {
      console.error('createMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  fetchMatch: async (id) => {
    set({ isLoading: true })
    try {
      const res = await scoringApi.getMatch(id)
      set({ currentMatch: res.data.data })
    } catch (error) {
      console.error('fetchMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  doScore: async (matchId, params) => {
    set({ isScoring: true })
    try {
      await scoringApi.score(matchId, params)
      // 重新拉取比赛详情
      await get().fetchMatch(matchId)
    } catch (error) {
      console.error('doScore failed', error)
      throw error
    } finally {
      set({ isScoring: false })
    }
  },

  doUndo: async (matchId) => {
    set({ isScoring: true })
    try {
      await scoringApi.undo(matchId)
      await get().fetchMatch(matchId)
    } catch (error) {
      console.error('doUndo failed', error)
      throw error
    } finally {
      set({ isScoring: false })
    }
  },

  finishMatch: async (matchId) => {
    set({ isLoading: true })
    try {
      await scoringApi.finishMatch(matchId)
      await get().fetchMatch(matchId)
    } catch (error) {
      console.error('finishMatch failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  fetchStatistics: async (matchId) => {
    set({ isLoading: true })
    try {
      const res = await scoringApi.getStatistics(matchId)
      set({ currentStatistics: res.data.data })
    } catch (error) {
      console.error('fetchStatistics failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  clearCurrent: () => {
    set({ currentMatch: null, currentStatistics: null })
  },
}))
```

---

## 4. 主要页面组件

### 4.1 比赛设置页

```tsx
// frontend/src/pages/scoring/setup.tsx
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Input, Toast } from '@nutui/nutui-react'
import { useScoringStore } from '@/stores/scoringStore'
import { useTranslation } from 'react-i18next'
import { FORMAT_OPTIONS, MATCH_TYPE_OPTIONS } from '@/constants/scoring'
import './setup.scss'

export default function MatchSetup() {
  const { t } = useTranslation()
  const { createMatch, isLoading } = useScoringStore()
  const [opponentName, setOpponentName] = useState('')
  const [opponentRating, setOpponentRating] = useState('')
  const [formatIdx, setFormatIdx] = useState(2) // 默认 bo5
  const [typeIdx, setTypeIdx] = useState(0)     // 默认 friendly
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
        opponent_rating: opponentRating ? parseInt(opponentRating) : undefined,
        format: FORMAT_OPTIONS[formatIdx].value,
        match_type: MATCH_TYPE_OPTIONS[typeIdx].value,
        target_score: 11,
      })
      // 跳转到实时记分页
      Taro.navigateTo({ url: `/pages/scoring/scoreboard/index?matchId=${matchId}` })
    } catch (err: any) {
      showToast(err?.message || t('scoring.createFailed'))
    }
  }, [opponentName, opponentRating, formatIdx, typeIdx, createMatch, t])

  return (
    <View className="match-setup">
      {/* 页面标题 */}
      <View className="setup-header">
        <Text className="setup-title">{t('scoring.matchSetup')}</Text>
      </View>

      {/* 对手信息 */}
      <Cell title={t('scoring.opponentName')}>
        <Input
          placeholder={t('scoring.opponentNamePlaceholder')}
          value={opponentName}
          maxLength={64}
          onChange={(val) => setOpponentName(val)}
        />
      </Cell>

      <Cell title={t('scoring.opponentRating')}>
        <Input
          type="number"
          placeholder={t('scoring.opponentRatingPlaceholder')}
          value={opponentRating}
          maxlength={4}
          onChange={(val) => setOpponentRating(val)}
        />
      </Cell>

      {/* 赛制选择 */}
      <Cell title={t('scoring.format')}>
        <Picker
          mode="selector"
          range={FORMAT_OPTIONS.map(o => o.label)}
          value={formatIdx}
          onChange={(e: any) => setFormatIdx(parseInt(e.detail.value))}
        >
          <View className="picker-value">{FORMAT_OPTIONS[formatIdx].label}</View>
        </Picker>
      </Cell>

      {/* 比赛类型 */}
      <Cell title={t('scoring.matchType')}>
        <Picker
          mode="selector"
          range={MATCH_TYPE_OPTIONS.map(o => o.label)}
          value={typeIdx}
          onChange={(e: any) => setTypeIdx(parseInt(e.detail.value))}
        >
          <View className="picker-value">{MATCH_TYPE_OPTIONS[typeIdx].label}</View>
        </Picker>
      </Cell>

      {/* 创建按钮 */}
      <View className="setup-actions">
        <Button
          type="primary"
          block
          loading={isLoading}
          onClick={handleCreate}
        >
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
```

### 4.2 实时记分页（核心页面）

```tsx
// frontend/src/pages/scoring/scoreboard.tsx
import { useState, useEffect, useCallback } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Popup, Toast, Skeleton } from '@nutui/nutui-react'
import { useScoringStore } from '@/stores/scoringStore'
import { useMatchSync } from '@/hooks/useMatchSync'
import { useTranslation } from 'react-i18next'
import { SCORE_METHODS } from '@/constants/scoring'
import './scoreboard.scss'

export default function Scoreboard() {
  const { t } = useTranslation()
  const router = useRouter()
  const matchId = parseInt(router.params.matchId as string)
  const { currentMatch, fetchMatch, doScore, doUndo, finishMatch, isScoring } = useScoringStore()
  const { isConnected } = useMatchSync(matchId)

  const [showMethodSheet, setShowMethodSheet] = useState(false)
  const [pendingScorer, setPendingScorer] = useState<'user' | 'opponent'>('user')
  const [showFinishPopup, setShowFinishPopup] = useState(false)
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  useEffect(() => {
    if (matchId) fetchMatch(matchId)
  }, [matchId])

  /** 点击得分大按钮 */
  const handleScoreClick = useCallback((scorer: 'user' | 'opponent') => {
    setPendingScorer(scorer)
    setShowMethodSheet(true)
  }, [])

  /** 选择得分方式后提交 */
  const handleMethodSelect = useCallback(async (method: string, technique?: string) => {
    setShowMethodSheet(false)
    try {
      await doScore(matchId, {
        scorer: pendingScorer,
        score_method: method as any,
        technique_action: technique,
      })
    } catch (err: any) {
      showToast(err?.message || t('scoring.scoreFailed'))
    }
  }, [matchId, pendingScorer, doScore, t])

  /** 撤销 */
  const handleUndo = useCallback(async () => {
    try {
      await doUndo(matchId)
    } catch (err: any) {
      showToast(err?.message || t('scoring.undoFailed'))
    }
  }, [matchId, doUndo, t])

  /** 结束比赛 */
  const handleFinish = useCallback(async () => {
    setShowFinishPopup(false)
    try {
      await finishMatch(matchId)
      // 跳转到统计页
      Taro.navigateTo({ url: `/pages/scoring/statistics/index?matchId=${matchId}` })
    } catch (err: any) {
      showToast(err?.message || t('scoring.finishFailed'))
    }
  }, [matchId, finishMatch, t])

  if (!currentMatch) {
    return <View className="scoreboard loading"><Skeleton rows={3} animated /></View>
  }

  const { current_score_user, current_score_opp, current_server, status } = currentMatch

  return (
    <View className="scoreboard">
      {/* WebSocket 连接状态指示器 */}
      {!isConnected && (
        <View style={{ padding: '8px', background: 'var(--color-danger)', color: 'var(--color-text-inverse)', textAlign: 'center', fontSize: '12px' }}>
          {t('scoring.wsDisconnected')}
        </View>
      )}
      {/* 比分显示区 */}
      <View className="score-display">
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

      {/* 大按钮记分区（单手操作） */}
      <View className="score-buttons">
        <Button
          className="btn-score btn-user"
          size="large"
          loading={isScoring}
          onClick={() => handleScoreClick('user')}
        >
          {t('scoring.iScored')}
        </Button>
        <Button
          className="btn-score btn-opp"
          size="large"
          loading={isScoring}
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
          disabled={isScoring || currentMatch.score_sequence.length === 0}
        >
          {t('scoring.undo')}
        </Button>
        <Button
          className="btn-action btn-finish"
          size="small"
          onClick={() => setShowFinishPopup(true)}
          disabled={isScoring}
        >
          {t('scoring.finishMatch')}
        </Button>
      </View>

      {/* 得分方式选择弹窗 */}
      <Popup
        visible={showMethodSheet}
        title={t('scoring.selectMethod')}
        onClose={() => setShowMethodSheet(false)}
      >
        <View className="method-grid">
          {SCORE_METHODS.map((m) => (
            <Button
              key={m.value}
              className="btn-method"
              size="small"
              onClick={() => handleMethodSelect(m.value, m.technique)}
            >
              {t(m.labelKey)}
            </Button>
          ))}
        </View>
      </Popup>

      {/* 结束比赛确认弹窗 */}
      <Popup
        visible={showFinishPopup}
        title={t('scoring.confirmFinish')}
        content={t('scoring.confirmFinishDesc')}
        onConfirm={handleFinish}
        onCancel={() => setShowFinishPopup(false)}
      />

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

### 4.3 比赛统计页

```tsx
// frontend/src/pages/scoring/statistics.tsx
import { useEffect } from 'react'
import { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Skeleton } from '@nutui/nutui-react'
import { useScoringStore } from '@/stores/scoringStore'
import { useTranslation } from 'react-i18next'
import './statistics.scss'

export default function MatchStatistics() {
  const { t } = useTranslation()
  const router = useRouter()
  const matchId = parseInt(router.params.matchId as string)
  const { currentMatch, currentStatistics, fetchMatch, fetchStatistics } = useScoringStore()

  useEffect(() => {
    if (matchId) {
      fetchMatch(matchId)
      fetchStatistics(matchId)
    }
  }, [matchId])

  if (!currentMatch || !currentStatistics) {
    return <View className="match-stats loading"><Skeleton rows={3} animated /></View>
  }

  const { stats_data } = currentStatistics
  const { score_distribution, technique_breakdown, key_points, total_points } = stats_data

  return (
    <View className="match-stats">
      {/* 比赛结果卡片 */}
      <View className="result-card">
        <Text className="result-title">
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
            <Cell key={method} title={t(`scoring.method.${method}`)}>
              <Text className="dist-count">{count}</Text>
            </Cell>
          ))}
        </View>
      </View>

      {/* 技术动作分解 */}
      <View className="stats-section">
        <Text className="section-title">{t('scoring.techniqueBreakdown')}</Text>
        <View className="technique-list">
          {Object.entries(technique_breakdown).map(([tech, count]) => (
            <Cell key={tech} title={t(`scoring.technique.${tech}`)}>
              <Text className="dist-count">{count}</Text>
            </Cell>
          ))}
        </View>
      </View>

      {/* 关键分 */}
      {key_points && key_points.length > 0 && (
        <View className="stats-section">
          <Text className="section-title">{t('scoring.keyPoints')}</Text>
          <View className="key-points-list">
            {key_points.map((kp, idx) => (
              <View key={idx} className="key-point-item">
                <Text className="kp-seq">#{kp.seq}</Text>
                <Text className="kp-winner">
                  {kp.scorer === 'user' ? t('scoring.me') : t('scoring.opponent')}
                </Text>
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
```

### 4.4 比赛列表页

```tsx
// frontend/src/pages/scoring/match-list.tsx
import { useState, useEffect, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Empty, Skeleton } from '@nutui/nutui-react'
import { listMatches } from '@/services/scoring'
import { useTranslation } from 'react-i18next'
import { MATCH_STATUS_MAP } from '@/constants/scoring'
import './match-list.scss'

interface MatchListItem {
  id: number
  opponent_name: string
  format: string
  match_type: string
  status: string
  current_score_user: number
  current_score_opp: number
  is_win?: boolean
  created_at: string
}

export default function MatchList() {
  const { t } = useTranslation()
  const [items, setItems] = useState<MatchListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)

  const load = useCallback(async (pageNum = 1) => {
    setLoading(true)
    try {
      const res = await listMatches(statusFilter, pageNum)
      const data = res.data.data
      if (pageNum === 1) {
        setItems(data.items)
      } else {
        setItems(prev => [...prev, ...data.items])
      }
      setTotal(data.total)
      setPage(pageNum)
    } catch (error) {
      console.error('load matches failed', error)
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    load(1)
  }, [load])

  const handleCreate = () => {
    Taro.navigateTo({ url: '/pages/scoring/setup/index' })
  }

  const handleItemClick = (item: MatchListItem) => {
    if (item.status === 'in_progress' || item.status === 'setup') {
      Taro.navigateTo({ url: `/pages/scoring/scoreboard/index?matchId=${item.id}` })
    } else {
      Taro.navigateTo({ url: `/pages/scoring/statistics/index?matchId=${item.id}` })
    }
  }

  const hasMore = items.length < total

  return (
    <View className="match-list">
      {/* 创建按钮 */}
      <View className="list-header">
        <Button type="primary" size="small" onClick={handleCreate}>
          {t('scoring.newMatch')}
        </Button>
      </View>

      {/* 状态筛选 */}
      <View className="filter-bar">
        {Object.entries(MATCH_STATUS_MAP).map(([key, val]) => (
          <Text
            key={key}
            className={`filter-tag ${statusFilter === key ? 'active' : ''}`}
            onClick={() => setStatusFilter(key === 'all' ? undefined : key)}
          >
            {t(val.labelKey)}
          </Text>
        ))}
      </View>

      {/* 列表 */}
      {items.length === 0 && !loading ? (
        <Empty description={t('scoring.noMatches')} />
      ) : (
        <View className="match-cards">
          {items.map(item => (
            <View key={item.id} className="match-card" onClick={() => handleItemClick(item)}>
              <View className="card-top">
                <Text className="card-opponent">{item.opponent_name}</Text>
                <Text className={`card-status status-${item.status}`}>
                  {t(MATCH_STATUS_MAP[item.status]?.labelKey || 'scoring.status.unknown')}
                </Text>
              </View>
              <View className="card-bottom">
                <Text className="card-score">
                  {item.current_score_user} : {item.current_score_opp}
                </Text>
                {item.is_win !== null && item.is_win !== undefined && (
                  <Text className={`card-result ${item.is_win ? 'win' : 'lose'}`}>
                    {item.is_win ? t('scoring.win') : t('scoring.lose')}
                  </Text>
                )}
                <Text className="card-date">{item.created_at.slice(0, 10)}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 上拉加载更多 */}
      {hasMore && (
        <View className="load-more" onClick={() => load(page + 1)}>
          {loading ? <Skeleton width="60%" height="16px" animated /> : <Text>{t('common.loadMore')}</Text>}
        </View>
      )}
    </View>
  )
}
```

---

## 5. 样式

### 5.1 比赛设置页样式

```scss
// frontend/src/pages/scoring/setup.scss
.match-setup {
  min-height: 100vh;
  background: var(--color-background);
  padding: 0 var(--spacing-md);
}

.setup-header {
  padding: var(--spacing-lg) 0 var(--spacing-md);

  .setup-title {
    font-size: 24px;
    font-weight: bold;
    color: var(--color-primary);
  }
}

.picker-value {
  color: var(--color-text-primary);
  font-size: 15px;
}

.setup-actions {
  margin-top: var(--spacing-xl);
  padding-bottom: var(--spacing-xl);

  :global(.nut-button.primary) {
    background: var(--color-primary);
    border-radius: var(--radius-sm);
    height: 48px;
    font-size: 18px;
  }
}
```

### 5.2 实时记分页样式（核心 — 大按钮单手操作）

```scss
// frontend/src/pages/scoring/scoreboard.scss
.scoreboard {
  min-height: 100vh;
  background: var(--color-background);
  display: flex;
  flex-direction: column;
}

/* 比分显示区 */
.score-display {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-lg) var(--spacing-md);
  background: var(--color-card);
}

.score-side {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;

  .score-name {
    font-size: 15px;
    color: var(--color-text-secondary);
    margin-bottom: var(--spacing-sm);
  }

  .score-number {
    font-size: 32px;
    font-weight: bold;
    color: var(--color-primary);
  }

  .server-badge {
    position: absolute;
    top: 0;
    font-size: 18px;
  }
}

.score-user .score-number {
  color: var(--color-primary);
}

.score-opp .score-number {
  color: var(--color-secondary);
}

.score-vs {
  .vs-text {
    font-size: 13px;
    color: var(--color-text-secondary);
    font-weight: bold;
  }
}

/* 大按钮记分区 */
.score-buttons {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm-md);
  padding: var(--spacing-md);
}

.btn-score {
  height: 120px !important; /* P3-fix: accessibility requirement ≥120px for single-hand operation, not spacing */
  font-size: 24px !important;
  font-weight: bold !important;
  border-radius: var(--radius-md) !important;
}

.btn-user {
  background: var(--color-primary) !important;
  color: var(--color-text-inverse) !important;
}

.btn-opp {
  background: var(--color-secondary) !important;
  color: var(--color-text-inverse) !important;
}

/* 操作按钮区 */
.action-bar {
  display: flex;
  gap: var(--spacing-sm-md);
  padding: var(--spacing-md);
  padding-bottom: var(--spacing-xl);
}

.btn-action {
  flex: 1;
  border-radius: var(--radius-md) !important;
}

.btn-finish {
  background: var(--color-accent) !important;
  color: var(--color-text-inverse) !important;
}

/* 得分方式弹窗 */
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

### 5.3 比赛统计页样式

```scss
// frontend/src/pages/scoring/statistics.scss
.match-stats {
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

  .result-title {
    display: block;
    font-size: 24px;
    font-weight: bold;
    margin-bottom: var(--spacing-sm);

    &.win { color: var(--color-success); }
    &.lose { color: var(--color-warning); }
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

.stats-section {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-sm-md);

  .section-title {
    display: block;
    font-size: 15px;
    font-weight: bold;
    color: var(--color-secondary);
    margin-bottom: var(--spacing-sm-md);
  }
}

.dist-count {
  font-size: 18px;
  font-weight: bold;
  color: var(--color-accent);
}

.total-points {
  text-align: center;
  padding: var(--spacing-md);
  color: var(--color-text-secondary);
  font-size: 13px;
}
```

### 5.4 比赛列表页样式

```scss
// frontend/src/pages/scoring/match-list.scss
.match-list {
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
  overflow-x: auto;

  .filter-tag {
    padding: var(--spacing-xs) var(--spacing-md);
    border-radius: var(--radius-md);
    font-size: 13px;
    background: var(--color-card);
    color: var(--color-text-secondary);
    white-space: nowrap;

    &.active {
      background: var(--color-primary);
      color: var(--color-text-inverse);
    }
  }
}

.match-cards {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm-md);
}

.match-card {
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

    .card-status {
      font-size: 12px;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--radius-sm);
    }

    .status-in_progress { background: var(--color-success); color: var(--color-text-inverse); }
    .status-finished { background: var(--color-secondary); color: var(--color-text-inverse); }
    .status-setup { background: var(--color-accent); color: var(--color-text-inverse); }
    .status-abandoned { background: var(--color-divider); color: var(--color-text-secondary); }
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

    .card-result {
      font-size: 12px;
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--radius-sm);

      &.win { background: var(--color-success); color: var(--color-text-inverse); }
      &.lose { background: var(--color-warning); color: var(--color-text-inverse); }
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

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 scoring 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    // scoring 模块页面
    'pages/scoring/setup/index',         // 比赛设置
    'pages/scoring/scoreboard/index',    // 实时记分
    'pages/scoring/statistics/index',    // 比赛统计
    'pages/scoring/match-list/index',    // 比赛列表
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 7. 常量与 i18n

### 常量定义

```typescript
// frontend/src/constants/scoring.ts

/** 赛制选项 */
export const FORMAT_OPTIONS = [
  { value: 'bo1', labelKey: 'scoring.format_bo1' },
  { value: 'bo3', labelKey: 'scoring.format_bo3' },
  { value: 'bo5', labelKey: 'scoring.format_bo5' },
  { value: 'bo7', labelKey: 'scoring.format_bo7' },
  { value: 'custom', labelKey: 'scoring.format_custom' },
]

/** 比赛类型选项 */
export const MATCH_TYPE_OPTIONS = [
  { value: 'friendly', labelKey: 'scoring.matchType_friendly' },
  { value: 'tournament', labelKey: 'scoring.matchType_tournament' },
  { value: 'training', labelKey: 'scoring.matchType_training' },
]
// P1-FE3 i18n：label→labelKey 统一，与同文件 SCORE_METHODS/MATCH_STATUS_MAP 风格一致

/** 得分方式（记分时快速选择） */
export const SCORE_METHODS = [
  { value: 'serve_point', labelKey: 'scoring.method.serve_point', technique: undefined },
  { value: 'rally_point', labelKey: 'scoring.method.rally_point', technique: undefined },
  { value: 'opponent_error', labelKey: 'scoring.method.opponent_error', technique: undefined },
  { value: 'rally_point', labelKey: 'scoring.method.forehand_drive', technique: 'forehand_drive' },
  { value: 'rally_point', labelKey: 'scoring.method.backhand_drive', technique: 'backhand_drive' },
  { value: 'rally_point', labelKey: 'scoring.method.forehand_loop', technique: 'forehand_loop' },
]

/** 比赛状态映射 */
export const MATCH_STATUS_MAP: Record<string, { labelKey: string; color: string }> = {
  all: { labelKey: 'scoring.status.all', color: '' },
  setup: { labelKey: 'scoring.status.setup', color: 'accent' },
  in_progress: { labelKey: 'scoring.status.in_progress', color: 'success' },
  finished: { labelKey: 'scoring.status.finished', color: 'secondary' },
  abandoned: { labelKey: 'scoring.status.abandoned', color: 'divider' },
}
```

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增 scoring 条目）
{
  "scoring": {
    "matchSetup": "比赛设置",
    "opponentName": "对手姓名",
    "opponentNamePlaceholder": "请输入对手姓名",
    "opponentRating": "对手积分",
    "opponentRatingPlaceholder": "选填",
    "format": "赛制",
    "matchType": "比赛类型",
    "format_bo1": "1局1胜",
    "format_bo3": "3局2胜",
    "format_bo5": "5局3胜",
    "format_bo7": "7局4胜",
    "format_custom": "自定义",
    "matchType_friendly": "友谊赛",
    "matchType_tournament": "比赛",
    "matchType_training": "训练赛",
    "startMatch": "开始比赛",
    "createFailed": "创建比赛失败",
    "fillOpponentName": "请填写对手姓名",
    "me": "我",
    "opponent": "对手",
    "iScored": "我得分",
    "opponentScored": "对手得分",
    "undo": "撤销",
    "finishMatch": "结束比赛",
    "selectMethod": "选择得分方式",
    "confirmFinish": "确认结束比赛？",
    "confirmFinishDesc": "结束后将生成比赛统计，不可恢复",
    "scoreFailed": "记分失败",
    "undoFailed": "撤销失败",
    "finishFailed": "结束比赛失败",
    "wsDisconnected": "连接已断开，正在重连...",
    "youWin": "胜利",
    "youLose": "失败",
    "vs": "VS",
    "scoreDistribution": "得分分布",
    "techniqueBreakdown": "技术动作",
    "keyPoints": "关键分",
    "totalPoints": "总得分",
    "win": "胜",
    "lose": "负",
    "newMatch": "新建比赛",
    "noMatches": "暂无比赛记录",
    "method": {
      "serve_point": "发球得分",
      "rally_point": "相持得分",
      "opponent_error": "对手失误",
      "forehand_drive": "正手攻球",
      "backhand_drive": "反手拨球",
      "forehand_loop": "正手拉球"
    },
    "status": {
      "all": "全部",
      "setup": "待开始",
      "in_progress": "进行中",
      "finished": "已结束",
      "abandoned": "已放弃",
      "unknown": "未知"
    },
    "technique": {
      "forehand_drive": "正手攻球",
      "backhand_drive": "反手拨球",
      "forehand_loop": "正手拉球"
    }
  }
}
```

```json
// frontend/src/locales/en-US.json（新增 scoring 条目）
{
  "scoring": {
    "matchSetup": "Match Setup",
    "opponentName": "Opponent Name",
    "opponentNamePlaceholder": "Enter opponent name",
    "opponentRating": "Opponent Rating",
    "opponentRatingPlaceholder": "Optional",
    "format": "Format",
    "matchType": "Match Type",
    "format_bo1": "BO1",
    "format_bo3": "BO3",
    "format_bo5": "BO5",
    "format_bo7": "BO7",
    "format_custom": "Custom",
    "matchType_friendly": "Friendly",
    "matchType_tournament": "Tournament",
    "matchType_training": "Training",
    "startMatch": "Start Match",
    "createFailed": "Failed to create match",
    "fillOpponentName": "Please enter opponent name",
    "me": "Me",
    "opponent": "Opponent",
    "iScored": "I Scored",
    "opponentScored": "Opponent Scored",
    "undo": "Undo",
    "finishMatch": "Finish",
    "selectMethod": "Select Method",
    "confirmFinish": "Finish match?",
    "confirmFinishDesc": "Statistics will be generated after finishing",
    "scoreFailed": "Score failed",
    "undoFailed": "Undo failed",
    "finishFailed": "Finish failed",
    "wsDisconnected": "Connection lost, reconnecting...",
    "youWin": "You Win",
    "youLose": "You Lose",
    "vs": "VS",
    "scoreDistribution": "Score Distribution",
    "techniqueBreakdown": "Technique Breakdown",
    "keyPoints": "Key Points",
    "totalPoints": "Total Points",
    "win": "W",
    "lose": "L",
    "newMatch": "New Match",
    "noMatches": "No matches yet",
    "method": {
      "serve_point": "Serve Point",
      "rally_point": "Rally Point",
      "opponent_error": "Opponent Error",
      "forehand_drive": "Forehand Drive",
      "backhand_drive": "Backhand Drive",
      "forehand_loop": "Forehand Loop"
    },
    "status": {
      "all": "All",
      "setup": "Setup",
      "in_progress": "In Progress",
      "finished": "Finished",
      "abandoned": "Abandoned",
      "unknown": "Unknown"
    },
    "technique": {
      "forehand_drive": "Forehand Drive",
      "backhand_drive": "Backhand Drive",
      "forehand_loop": "Forehand Loop"
    }
  }
}
```

---

## 8. WebSocket 订阅 Hook

```typescript
// frontend/src/hooks/useMatchSync.ts
import { useEffect } from 'react'
import { useScoringStore } from '@/stores/scoringStore'
import { useWebSocket } from '@/hooks/useWebSocket'

/**
 * 订阅比赛 WebSocket 推送，实时更新比分。
 * 用于多设备同步场景：设备 A 记分，设备 B 自动收到更新。
 * 使用项目统一的 useWebSocket Hook，由其管理连接、鉴权与断线重连。
 */
export function useMatchSync(matchId: number | null) {
  const { fetchMatch } = useScoringStore()
  const { sendMessage, isConnected, onMessage } = useWebSocket()

  // 连接就绪后加入比赛房间
  useEffect(() => {
    if (!matchId || !isConnected) return
    sendMessage(JSON.stringify({ event: 'join', room: `ws:match:${matchId}` }))
  }, [matchId, isConnected, sendMessage])

  // 监听比分更新与全量同步消息
  useEffect(() => {
    if (!matchId) return

    const removeListener = onMessage((event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data)
        // 注意：score_update 事件存在双路径处理——useWebSocket 的 handleMessage
        // 会通过 Taro.eventCenter.trigger('score_update', ...) 广播给事件中心订阅者，
        // 此处 useMatchSync 的 onMessage 则直接重新拉取当前比赛详情以确保 UI 同步。
        // 两者互不冲突：eventCenter 用于跨模块通知，此处用于即时刷新比分页面。
        if (msg.event === 'score_update') {
          // 收到比分更新，重新拉取详情
          fetchMatch(matchId)
        }
        if (msg.event === 'sync_match') {
          // 全量同步（断线重连后）
          fetchMatch(matchId)
        }
        if (msg.event === 'match_finished') {
          // 比赛结束：重新拉取详情以获取最终比分和状态
          fetchMatch(matchId)
        }
      } catch {
        // 忽略非 JSON 消息
      }
    })

    return () => {
      removeListener()
    }
  }, [matchId, fetchMatch, onMessage])

  return { isConnected }
}
```

---

## 9. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 比赛设置页布局：对手信息 + 赛制选择 + 开始按钮
- [ ] 实时记分页大按钮可达 120px 高，单手可操作
- [ ] 用户得分按钮使用主色 `#E63946`
- [ ] 对手得分按钮使用深蓝 `#1D3557`
- [ ] 发球方有乒乓球拍图标标识
- [ ] 比分数字使用大字号（32px），醒目可读
- [ ] 统计页结果卡片使用成功色 `#2A9D8F`（胜利）或警告色 `#F4A261`（失败）
- [ ] 比赛列表状态标签颜色正确（进行中=绿，已结束=蓝，待开始=橙）

### 功能验证
- [ ] 比赛设置：填写对手信息 → 选择赛制 → 开始 → 跳转实时记分
- [ ] 实时记分：点击大按钮 → 弹出得分方式 → 选择 → 比分更新
- [ ] 撤销：点击撤销 → 比分回退 1 分
- [ ] 结束比赛：确认弹窗 → 结束 → 跳转统计页
- [ ] 比赛统计：得分分布 + 技术动作分解 + 关键分列表
- [ ] 比赛列表：按状态筛选 → 点击进入详情或继续记分
- [ ] 多设备同步：设备 A 记分，设备 B WebSocket 实时收到更新

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/scoring.ts` 封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 实时记分页大按钮高度 ≥ 120px，确保单手操作
- **ALL** 多设备同步必须使用 WebSocket 订阅 `ws:match:{id}` 房间
- **禁止** 使用 class 组件
- **禁止** 硬编码颜色值，使用 CSS 变量（`--color-primary` 等）
- **禁止** 安装新的 npm 包
