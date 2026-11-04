/**
 * 比赛列表页（04-scoring/frontend.md §4.4）
 * 状态筛选 + 分页列表 + 点击进入记分/统计
 */
import { useState, useEffect, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Empty, Skeleton } from '@nutui/nutui-react'
import { listMatches } from '@/services/scoring'
import { useTranslation } from 'react-i18next'
import { MATCH_STATUS_MAP } from '@/constants/scoring'
import './index.scss'

export interface MatchListItem {
  id: number
  opponent_name: string | null
  format: string
  match_type: string
  status: string
  current_score_user: number
  current_score_opp: number
  is_win?: boolean | null
  created_at?: string | null
}

export default function MatchList() {
  const { t } = useTranslation()
  const [items, setItems] = useState<MatchListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)

  const load = useCallback(
    async (pageNum = 1) => {
      setLoading(true)
      try {
        const res = await listMatches(statusFilter, pageNum)
        const data = res.data.data
        if (pageNum === 1) {
          setItems(data.items)
        } else {
          setItems((prev) => [...prev, ...data.items])
        }
        setTotal(data.total)
        setPage(pageNum)
      } catch (error) {
        console.error('load matches failed', error)
      } finally {
        setLoading(false)
      }
    },
    [statusFilter]
  )

  useEffect(() => {
    load(1)
  }, [load])

  const handleCreate = () => {
    Taro.navigateTo({ url: '/pages/scoring/setup/index' })
  }

  /**
   * 点击比赛：
   * - setup / in_progress → 继续记分
   * - abandoned → 记分页提供恢复（24h 内，X-26）；统计端点要求 finished，
   *   若跳统计页会 400，故按状态机路由到记分页
   * - finished → 统计页
   */
  const handleItemClick = (item: MatchListItem) => {
    if (item.status === 'in_progress' || item.status === 'setup' || item.status === 'abandoned') {
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
      {loading && items.length === 0 ? (
        <View className="list-skeleton">
          <Skeleton rows={3} animated />
        </View>
      ) : items.length === 0 ? (
        <Empty description={t('scoring.noMatches')} />
      ) : (
        <View className="match-cards">
          {items.map((item) => (
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
                <Text className="card-date">{(item.created_at || '').slice(0, 10)}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 上拉加载更多 */}
      {hasMore && (
        <View className="load-more" onClick={() => load(page + 1)}>
          <Text>{loading ? t('common.loading') : t('common.loadMore')}</Text>
        </View>
      )}
    </View>
  )
}
