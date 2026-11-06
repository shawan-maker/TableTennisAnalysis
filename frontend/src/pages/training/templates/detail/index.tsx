/**
 * 训练模板详情页（07-training_advice/frontend.md §4.7）
 * 目标 / 训练内容 / 练习项目 / 检验指标 四区
 *
 * FS5-P3 契约同步：支持 id / code 双查询参数 —— 设计样例 advice 页跳转携带
 * ?code={template_code} 而本页样例只读 id（两处自相矛盾）；code 时先查模板
 * 列表定位 id 再取详情（模板为预置数据，首页 50 条覆盖）。
 */
import { useEffect } from 'react'
import { useRouter } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Skeleton, Empty } from '@nutui/nutui-react'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import { useTrainingStore } from '@/stores/trainingStore'
import { getTemplates } from '@/services/training'
import './index.scss'

export default function TemplateDetailPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const currentTemplate = useTrainingStore((s) => s.currentTemplate)
  const templateDetailLoading = useTrainingStore((s) => s.templateDetailLoading)
  const templateDetailError = useTrainingStore((s) => s.templateDetailError)
  const templateDetailNeedsMembership = useTrainingStore((s) => s.templateDetailNeedsMembership)
  const fetchTemplateDetail = useTrainingStore((s) => s.fetchTemplateDetail)

  useEffect(() => {
    const { id, code } = router.params
    if (id) {
      fetchTemplateDetail(Number(id))
    } else if (code) {
      // code 查询：先从模板列表定位 id（模板为预置数据，首页 50 条覆盖）
      getTemplates(undefined, 1, 50)
        .then((res) => {
          const matched = res.data.data.items.find(
            (item) => item.template_code === code
          )
          if (matched) {
            fetchTemplateDetail(matched.id)
          }
        })
        .catch(() => {
          // 列表查询失败（含会员守卫）：详情加载由 store 状态呈现
        })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleUpgrade = () => {
    Taro.navigateTo({ url: '/pages/membership/index' })
  }

  if (templateDetailLoading && !currentTemplate) {
    return (
      <View className="template-detail-page">
        <View className="detail-header">
          <Text className="page-title">{t('training.templateDetail')}</Text>
        </View>
        <View className="detail-skeleton">
          <Skeleton rows={4} animated />
        </View>
      </View>
    )
  }

  // 会员守卫：升级引导
  if (templateDetailNeedsMembership) {
    return (
      <View className="template-detail-page">
        <View className="detail-header">
          <Text className="page-title">{t('training.templateDetail')}</Text>
        </View>
        <View className="detail-error">
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

  if (!currentTemplate) {
    return (
      <View className="template-detail-page">
        <View className="detail-header">
          <Text className="page-title">{t('training.templateDetail')}</Text>
        </View>
        <View className="detail-error">
          <Empty title={templateDetailError || t('training.templateNotFound')} />
        </View>
      </View>
    )
  }

  const data = currentTemplate.template_data

  return (
    <View className="template-detail-page">
      <View className="detail-header">
        <Text className="page-title">{currentTemplate.name}</Text>
        <Text className="template-code-label">{currentTemplate.template_code}</Text>
      </View>

      <ScrollView scrollY className="detail-scroll">
        {/* 目标 */}
        {data.goal && (
          <View className="detail-section">
            <Text className="section-title">🎯 {t('training.goal')}</Text>
            <View className="goal-card">
              <Text className="goal-metric">{data.goal.metric}</Text>
              <Text className="goal-target">
                {t('training.targetValue')}: {data.goal.target}
              </Text>
            </View>
          </View>
        )}

        {/* 训练内容 */}
        {data.sessions && data.sessions.length > 0 && (
          <View className="detail-section">
            <Text className="section-title">📋 {t('training.sessions')}</Text>
            {data.sessions.map((session, i) => (
              <View className="session-card" key={`${session.name}-${i}`}>
                <Text className="session-name">
                  {i + 1}. {session.name}
                </Text>
                <Text className="session-reps">
                  {t('training.reps')}: {session.reps}
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* 练习项目 */}
        {data.exercises && data.exercises.length > 0 && (
          <View className="detail-section">
            <Text className="section-title">🏓 {t('training.exercises')}</Text>
            {data.exercises.map((exercise, i) => (
              <View className="exercise-item" key={`${exercise}-${i}`}>
                <Text className="exercise-dot">•</Text>
                <Text className="exercise-text">{exercise}</Text>
              </View>
            ))}
          </View>
        )}

        {/* 检验指标 */}
        {data.metrics && data.metrics.length > 0 && (
          <View className="detail-section">
            <Text className="section-title">📊 {t('training.metrics')}</Text>
            <View className="metrics-list">
              {data.metrics.map((metric, i) => (
                <View className="metric-tag" key={`${metric}-${i}`}>
                  <Text>{metric}</Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  )
}
