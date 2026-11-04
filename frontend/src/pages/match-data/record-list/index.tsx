/**
 * 比赛记录列表页（05-match_data/frontend.md §4.3）
 * 胜负筛选 + 记录卡片 + 上拉分页 + 点击进入详情
 */
import { useState, useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Button, Empty, Skeleton } from '@nutui/nutui-react'
import { useMatchDataStore } from '@/stores/matchDataStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

type ResultFilter = 'all' | 'win' | 'lose'

export default function RecordList() {
  const { t } = useTranslation()
  const { records, total, page, isLoading, fetchRecords, resetList } = useMatchDataStore()
  const [resultFilter, setResultFilter] = useState<ResultFilter>('all')

  useEffect(() => {
    fetchRecords(resultFilter, 1)
    return () => {
      // 离开页面时清空列表态，避免下次进入旧数据闪现
      resetList()
    }
  }, [resultFilter, fetchRecords, resetList])

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
        {(['all', 'win', 'lose'] as const).map((key) => (
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
      {isLoading && records.length === 0 ? (
        <View className="list-skeleton">
          <Skeleton rows={3} animated />
        </View>
      ) : records.length === 0 ? (
        <Empty description={t('matchData.noRecords')} />
      ) : (
        <View className="record-cards">
          {records.map((item) => (
            <View key={item.id} className="record-card" onClick={() => handleItemClick(item.id)}>
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
                <Text className="card-date">{(item.match_date || '').slice(0, 10)}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 上拉加载更多 */}
      {records.length < total && (
        <View className="load-more" onClick={handleLoadMore}>
          <Text>{isLoading ? t('common.loading') : t('common.loadMore')}</Text>
        </View>
      )}
    </View>
  )
}
