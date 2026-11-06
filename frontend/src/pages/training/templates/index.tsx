/**
 * 训练模板列表页（07-training_advice/frontend.md §4.6）
 * 分页列表 + 上拉加载；会员守卫（403/40300）渲染升级引导
 *
 * FS5-P3：设计样例 PullRefresh 在 weapp 与 ScrollView 嵌套易冲突，
 * 改用页面级下拉刷新（enablePullDownRefresh + usePullDownRefresh，FS3/FS4 先例）；
 * Cell 用 title/description/clickable（NutUI 2.7.14 真实 API）。
 */
import { useEffect, useCallback } from 'react'
import Taro, { usePullDownRefresh } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Cell, Empty, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useTrainingStore } from '@/stores/trainingStore'
import './index.scss'

export default function TemplateListPage() {
  const { t } = useTranslation()
  const templates = useTrainingStore((s) => s.templates)
  const templateTotal = useTrainingStore((s) => s.templateTotal)
  const templateLoading = useTrainingStore((s) => s.templateLoading)
  const templateHasMore = useTrainingStore((s) => s.templateHasMore)
  const templateError = useTrainingStore((s) => s.templateError)
  const templateNeedsMembership = useTrainingStore((s) => s.templateNeedsMembership)
  const fetchTemplates = useTrainingStore((s) => s.fetchTemplates)
  const loadMoreTemplates = useTrainingStore((s) => s.loadMoreTemplates)

  useEffect(() => {
    fetchTemplates(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  usePullDownRefresh(() => {
    fetchTemplates(true).finally(() => Taro.stopPullDownRefresh())
  })

  const handleItemClick = useCallback((id: number) => {
    Taro.navigateTo({ url: `/pages/training/templates/detail/index?id=${id}` })
  }, [])

  const handleLoadMore = useCallback(() => {
    loadMoreTemplates()
  }, [loadMoreTemplates])

  const handleUpgrade = () => {
    Taro.navigateTo({ url: '/pages/membership/index' })
  }

  // 会员守卫：升级引导
  if (templateNeedsMembership) {
    return (
      <View className="template-list-page">
        <View className="template-header">
          <Text className="page-title">{t('training.templateList')}</Text>
        </View>
        <View className="membership-guard">
          <Empty
            title={t('training.membershipRequired')}
            actions={[
              { text: t('training.upgradeMembership'), type: 'primary', size: 'small', onClick: handleUpgrade },
            ]}
          />
        </View>
      </View>
    )
  }

  return (
    <View className="template-list-page">
      <View className="template-header">
        <Text className="page-title">{t('training.templateList')}</Text>
        {templateTotal > 0 && (
          <Text className="template-total">
            {t('training.templateTotal', { count: templateTotal })}
          </Text>
        )}
      </View>

      <ScrollView scrollY className="template-scroll">
        {templateLoading && templates.length === 0 ? (
          <View className="template-skeleton-list">
            {[0, 1, 2, 3].map((i) => (
              <View className="template-skeleton-item" key={i}>
                <Skeleton rows={2} animated />
              </View>
            ))}
          </View>
        ) : templateError ? (
          <View className="template-error">
            <Empty
              title={templateError}
              actions={[
                { text: t('common.retry'), type: 'primary', size: 'small', onClick: () => fetchTemplates(true) },
              ]}
            />
          </View>
        ) : templates.length === 0 ? (
          <Empty title={t('training.noTemplates')} />
        ) : (
          <View className="template-list">
            {templates.map((item) => (
              <Cell
                key={item.id}
                className="template-item"
                title={item.name}
                description={
                  item.problem_id
                    ? `${item.template_code} · ${t('training.problem')}: ${item.problem_id}`
                    : item.template_code
                }
                clickable
                onClick={() => handleItemClick(item.id)}
              />
            ))}

            {templateHasMore && (
              <View className="load-more" onClick={handleLoadMore}>
                <Text>
                  {templateLoading ? t('common.loading') : t('common.loadMore')}
                </Text>
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </View>
  )
}
