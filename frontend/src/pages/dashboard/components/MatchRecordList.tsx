/**
 * 比赛记录列表组件（06-data_dashboard/frontend.md §4.6）
 * 胜/负/全部筛选 Tabs + 分页加载 + 跳转 S2 记分数据详情（联动）
 */
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Tabs, Empty } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { MatchRecordItem, ResultFilter } from '@/services/dashboard'
import { RESULT_FILTER_OPTIONS } from '@/constants/dashboard'
import './MatchRecordList.scss'

interface Props {
  items: MatchRecordItem[]
  total: number
  filter: ResultFilter
  loading: boolean
  hasMore: boolean
  onFilterChange: (filter: ResultFilter) => void
  onLoadMore: () => void
}

export default function MatchRecordList({
  items,
  total,
  filter,
  loading,
  hasMore,
  onFilterChange,
  onLoadMore,
}: Props) {
  const { t } = useTranslation()

  // R-FE-R1 批次C（FE-P3-16）：筛选选项收敛至 constants/dashboard.ts（设计 L1408-1431）
  const filterOptions = RESULT_FILTER_OPTIONS.map((o) => ({ key: o.key, label: t(o.labelKey) }))

  const handleItemClick = (item: MatchRecordItem) => {
    // 跳转 S2 记分数据详情（模块联动）
    Taro.navigateTo({
      url: `/pages/match-data/record-detail/index?id=${item.id}`,
    })
  }

  return (
    <View className="match-record-list">
      <View className="section-header">
        <Text className="section-title">📋 {t('dashboard.matchRecords')}</Text>
        <Text className="section-count">{t('dashboard.totalMatches', { count: total })}</Text>
      </View>

      <Tabs value={filter} onChange={(val) => onFilterChange(val as ResultFilter)}>
        {filterOptions.map((opt) => (
          <Tabs.TabPane key={opt.key} title={opt.label} value={opt.key} />
        ))}
      </Tabs>

      {items.length === 0 && !loading ? (
        <Empty description={t('dashboard.noMatchRecords')} />
      ) : (
        <View className="record-list">
          {items.map((item) => (
            <View
              className={`record-card ${item.is_win ? 'card-win' : 'card-lose'}`}
              key={item.id}
              onClick={() => handleItemClick(item)}
            >
              <View className="record-left">
                <Text className="record-date">
                  {item.match_date ? new Date(item.match_date).toLocaleDateString() : ''}
                </Text>
                <Text className="record-opponent">
                  vs {item.opponent_name || t('dashboard.unknownOpponent')}
                </Text>
                {item.opponent_rating != null && (
                  <Text className="record-rating">
                    {t('dashboard.rating')}: {item.opponent_rating}
                  </Text>
                )}
              </View>
              <View className="record-right">
                <Text className="record-score">
                  {item.my_score} - {item.opponent_score}
                </Text>
                <Text className={`record-result ${item.is_win ? 'win' : 'lose'}`}>
                  {item.is_win ? t('dashboard.win') : t('dashboard.lose')}
                </Text>
              </View>
            </View>
          ))}

          {/* 上拉加载更多 */}
          {hasMore && (
            <View className="load-more" onClick={onLoadMore}>
              <Text>{loading ? t('common.loading') : t('common.loadMore')}</Text>
            </View>
          )}
        </View>
      )}
    </View>
  )
}
