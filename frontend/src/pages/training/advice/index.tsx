/**
 * 训练建议详情页（07-training_advice/frontend.md §4.1）
 * 诊断短板 → 建议 → 训练方法 → 模板推荐；支持 ?report_id= 直达或自动取最新报告
 *
 * FS5-P3 契约同步：
 * - NutUI 2.7.14 Skeleton 无 width/height props，改 rows（FS4 同先例）
 * - NutUI Tag 用 background/color props（type+style 为 2.x 旧口径）
 */
import { useEffect } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Button, Skeleton, Empty } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useTrainingStore } from '@/stores/trainingStore'
import DiagnosisSection from './components/DiagnosisSection'
import SuggestionSection from './components/SuggestionSection'
import TrainingMethodsSection from './components/TrainingMethodsSection'
import TemplateRecommendSection from './components/TemplateRecommendSection'
import './index.scss'

export default function TrainingAdvicePage() {
  const { t } = useTranslation()
  const router = useRouter()
  const advice = useTrainingStore((s) => s.advice)
  const adviceLoading = useTrainingStore((s) => s.adviceLoading)
  const adviceError = useTrainingStore((s) => s.adviceError)
  const fetchAdviceByReport = useTrainingStore((s) => s.fetchAdviceByReport)
  const fetchContextualAdvice = useTrainingStore((s) => s.fetchContextualAdvice)

  useEffect(() => {
    const { report_id } = router.params
    if (report_id) {
      fetchAdviceByReport(Number(report_id))
    } else {
      fetchContextualAdvice()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleViewTemplate = () => {
    if (advice?.training_plan_template) {
      // 跳转到模板详情页（详情页支持 code 查询，见 templates/detail）
      Taro.navigateTo({
        url: `/pages/training/templates/detail/index?code=${advice.training_plan_template}`,
      })
    } else {
      // 跳转到模板列表页
      Taro.navigateTo({ url: '/pages/training/templates/index' })
    }
  }

  if (adviceLoading && !advice) {
    return (
      <View className="advice-page">
        <View className="advice-header">
          <Text className="page-title">{t('training.adviceTitle')}</Text>
        </View>
        {[0, 1, 2].map((i) => (
          <View className="advice-skeleton" key={i}>
            <Skeleton rows={3} animated />
          </View>
        ))}
      </View>
    )
  }

  if (adviceError || !advice) {
    return (
      <View className="advice-page">
        <View className="advice-header">
          <Text className="page-title">{t('training.adviceTitle')}</Text>
        </View>
        <View className="advice-error">
          <Empty
            title={adviceError || t('training.noAdvice')}
            actions={[
              { text: t('common.retry'), type: 'primary', size: 'small', onClick: () => fetchContextualAdvice() },
            ]}
          />
        </View>
      </View>
    )
  }

  return (
    <View className="advice-page">
      {/* 页面标题 */}
      <View className="advice-header">
        <Text className="page-title">{t('training.adviceTitle')}</Text>
        {advice.is_first_analysis && (
          <Text className="first-analysis-tag">{t('training.firstAnalysis')}</Text>
        )}
      </View>

      <ScrollView scrollY className="advice-scroll">
        {/* 诊断短板区域 */}
        <DiagnosisSection diagnosis={advice.diagnosis} />

        {/* 建议区域（进步确认/持续问题/新问题） */}
        <SuggestionSection suggestions={advice.suggestions} />

        {/* 训练方法区域 */}
        <TrainingMethodsSection methods={advice.training_methods} />

        {/* 训练方案模板推荐 */}
        <TemplateRecommendSection
          templateCode={advice.training_plan_template}
          onViewTemplate={handleViewTemplate}
        />

        {/* 底部操作按钮 */}
        <View className="advice-actions">
          <Button block type="primary" onClick={() => Taro.navigateBack()}>
            {t('common.back')}
          </Button>
        </View>
      </ScrollView>
    </View>
  )
}
