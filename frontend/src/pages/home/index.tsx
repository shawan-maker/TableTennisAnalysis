/**
 * 首页 Dashboard 聚合页（00-home/frontend.md §4.1）
 * 顶部栏 + 数据概览 + 快捷宫格 + 打卡周视图 + 最近报告 + 训练提醒。
 *
 * FS7-P3 实现注记：
 * - 页面级下拉刷新（enablePullDownRefresh + usePullDownRefresh）替代设计样例
 *   PullRefresh 组件（weapp 下与 ScrollView 嵌套冲突，FS5 先例）；
 * - 通知铃铛复用 NotificationBell 组件挂 TopBar（12-notification §5 迁回首页）；
 * - 首页 onShow 检测新用户 → 跳转 onboarding 引导页（onboarding.md §5 触发约定）；
 * - HomeTourOverlay（引导 Step 2 首页遮罩）挂本页，onboardingStore.showHomeTour 控制。
 */
import { useEffect } from 'react'
import Taro, { usePullDownRefresh, useDidShow } from '@tarojs/taro'
import { View } from '@tarojs/components'
import { useHomeStore } from '@/stores/homeStore'
import { useAuthStore } from '@/stores/authStore'
import { useUserStore } from '@/stores/userStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import HomeTourOverlay from '@/pages/onboarding/components/HomeTourOverlay'
import TopBar from './components/TopBar'
import OverviewCards from './components/OverviewCards'
import QuickGrid from './components/QuickGrid'
import CheckinCalendar from './components/CheckinCalendar'
import LatestReportCard from './components/LatestReportCard'
import AdviceBanner from './components/AdviceBanner'
// R-FE-R1 批次A（FE-P1-9）：训练积分卡嵌入首页 Dashboard（09-gamification §4.1 注记③后半句兑现）
import PointsCard from '@/pages/gamification/components/PointsCard'
import './index.scss'

export default function HomePage() {
  const {
    overview, overviewLoading,
    weekView, checkinLoading,
    latestReport, reportLoading,
    adviceSummary,
    refreshAll,
  } = useHomeStore()
  const { user } = useAuthStore()

  useEffect(() => {
    refreshAll()
  }, [refreshAll])

  // 下拉刷新（页面级，FS5 先例）
  usePullDownRefresh(() => {
    refreshAll().then(() => {
      Taro.stopPullDownRefresh()
    })
  })

  // 首页 onShow：新用户引导检测（onboarding.md §5：登录后首次进入首页时触发）
  useDidShow(() => {
    const createdAt = user?.created_at
    if (!createdAt) return
    const { profile, fetchProfile } = useUserStore.getState()
    const completeness = profile?.profile.profile_completeness
    if (typeof completeness === 'number') {
      triggerOnboarding(createdAt, completeness)
    } else {
      // 首次进入尚未拉档案：先拉取再检测
      fetchProfile()
        .then(() => {
          const c = useUserStore.getState().profile?.profile.profile_completeness ?? 0
          triggerOnboarding(createdAt, c)
        })
        .catch(() => {})
    }
  })

  const triggerOnboarding = (createdAt: string, completeness: number) => {
    useOnboardingStore.getState().initOnboarding(createdAt, completeness)
    // FS8-P1-2（E2E-01 抓获）：initOnboarding 内部 set() 后须重读快照——
    // 修复前 getState() 取的是 init 前旧值（isNewUser 恒 false），引导页永不触发
    const { isNewUser, completed } = useOnboardingStore.getState()
    // 新用户且未完成 → 进入引导页（引导页内含 Steps 弹窗与分步跳转）
    if (isNewUser && !completed) {
      Taro.navigateTo({ url: '/pages/onboarding/index' })
    }
  }

  return (
    <View className="home-page">
      {/* 顶部栏：头像 + 昵称 + KQS 积分 + 通知铃铛（FS6 组件迁回） */}
      <TopBar />

      <View className="home-scroll">
        {/* 数据概览卡片 */}
        <OverviewCards data={overview} loading={overviewLoading} />

        {/* 快捷操作宫格 */}
        <QuickGrid />

        {/* 训练积分卡（R-FE-R1 批次A FE-P1-9：09-gamification §4.1「嵌入首页 Dashboard」） */}
        <PointsCard />

        {/* 训练打卡日历（周视图） */}
        <CheckinCalendar data={weekView} loading={checkinLoading} />

        {/* 最近分析报告 */}
        <LatestReportCard report={latestReport} loading={reportLoading} />

        {/* 训练提醒 */}
        <AdviceBanner advice={adviceSummary} loading={overviewLoading} />
      </View>

      {/* 引导 Step 2：首页功能遮罩（onboardingStore.showHomeTour 控制） */}
      <HomeTourOverlay />
    </View>
  )
}
