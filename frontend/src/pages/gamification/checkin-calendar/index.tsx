/**
 * 打卡日历页（09-gamification/frontend.md §4.2）
 * 积分卡片 + 月度日历（上/下月导航）+ 连续打卡火焰 + 手动打卡
 *
 * FS5-P3 契约同步：
 * - 本地日期构造替代 toISOString()（UTC 偏移导致 CST 跨日错位，后端按 CST 计日）
 * - 409 重复打卡按 request 层抛错处理（Error.message 已含后端 40901 文案），
 *   样例的 err.response.status 分支在本工程封装下不存在
 * - NutUI 受控 Toast 样例改 Taro.showToast（FS4 先例）
 */
import { useEffect, useState, useCallback } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { Button, Skeleton } from '@nutui/nutui-react'
import Taro from '@tarojs/taro'
import { useTranslation } from 'react-i18next'
import { useGamificationStore } from '@/stores/gamificationStore'
import PointsCard from '../components/PointsCard'
import BadgeUnlockPopup from '@/components/BadgeUnlockPopup'
import './index.scss'

/** 本地日期 → YYYY-MM-DD（避免 toISOString 的 UTC 跨日偏移，后端按 CST 计日） */
function localDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export default function CheckinCalendarPage() {
  const { t } = useTranslation()
  const calendar = useGamificationStore((s) => s.calendar)
  const isLoadingCalendar = useGamificationStore((s) => s.isLoadingCalendar)
  const isCheckingIn = useGamificationStore((s) => s.isCheckingIn)
  const fetchCalendar = useGamificationStore((s) => s.fetchCalendar)
  const doCheckin = useGamificationStore((s) => s.doCheckin)

  const [currentYear, setCurrentYear] = useState(() => new Date().getFullYear())
  const [currentMonth, setCurrentMonth] = useState(() => new Date().getMonth() + 1)

  useEffect(() => {
    fetchCalendar(currentYear, currentMonth)
  }, [fetchCalendar, currentYear, currentMonth])

  /** 上个月 */
  const handlePrevMonth = useCallback(() => {
    if (currentMonth === 1) {
      setCurrentMonth(12)
      setCurrentYear((y) => y - 1)
    } else {
      setCurrentMonth((m) => m - 1)
    }
  }, [currentMonth])

  /** 下个月 */
  const handleNextMonth = useCallback(() => {
    if (currentMonth === 12) {
      setCurrentMonth(1)
      setCurrentYear((y) => y + 1)
    } else {
      setCurrentMonth((m) => m + 1)
    }
  }, [currentMonth])

  /** 手动打卡（409/40901 等错误经 Error.message 展示） */
  const handleCheckin = useCallback(async () => {
    try {
      const result = await doCheckin()
      if (result) {
        let msg = t('gamification.checkinSuccess', { points: result.points_earned })
        if (result.bonus) {
          msg += t('gamification.streakBonus', { bonus: result.bonus })
        }
        Taro.showToast({ title: msg, icon: 'none' })
      }
    } catch (err: any) {
      Taro.showToast({ title: err?.message || t('gamification.checkinFailed'), icon: 'none' })
    }
  }, [doCheckin, t])

  // 星期表头（周一开始）
  const weekdays = [
    t('common.mon'),
    t('common.tue'),
    t('common.wed'),
    t('common.thu'),
    t('common.fri'),
    t('common.sat'),
    t('common.sun'),
  ]
  const todayStr = localDateStr(new Date())
  const days = calendar?.days ?? []
  // 首日星期（本地时区构造，ISO 字符串解析有 UTC 歧义）；周一开始偏移
  const firstDay = days.length > 0 ? new Date(currentYear, currentMonth - 1, 1).getDay() : 0
  const emptyCells = (firstDay + 6) % 7

  return (
    <View className="checkin-calendar-page">
      <ScrollView scrollY className="calendar-scroll">
        {/* 训练积分卡片（FS5：嵌入打卡页，首页嵌入归 FS7） */}
        <PointsCard />

        {/* 打卡日历卡 */}
        <View className="checkin-calendar">
          {isLoadingCalendar && !calendar ? (
            <View className="calendar-loading">
              <Skeleton rows={4} animated />
            </View>
          ) : (
            <>
              {/* 月份导航 */}
              <View className="calendar-header">
                <View className="month-nav prev" onClick={handlePrevMonth}>
                  <Text>‹</Text>
                </View>
                <Text className="month-title">
                  {t('gamification.checkin.monthTitle', { year: currentYear, month: currentMonth })}
                </Text>
                <View className="month-nav next" onClick={handleNextMonth}>
                  <Text>›</Text>
                </View>
              </View>

              {/* 连续打卡提示 */}
              <View className="calendar-streak">
                <Text className="streak-text">
                  {t('gamification.currentStreak', { days: calendar?.streak_days ?? 0 })}
                </Text>
                {(calendar?.streak_days ?? 0) >= 3 && <Text className="streak-flame">🔥</Text>}
              </View>

              {/* 星期表头 */}
              <View className="calendar-weekdays">
                {weekdays.map((day) => (
                  <View key={day} className="weekday-cell">
                    <Text className="weekday-text">{day}</Text>
                  </View>
                ))}
              </View>

              {/* 日历网格 */}
              <View className="calendar-grid">
                {Array.from({ length: emptyCells }).map((_, i) => (
                  <View key={`empty-${i}`} className="calendar-cell empty" />
                ))}
                {days.map((day) => (
                  <View
                    key={day.date}
                    className={`calendar-cell ${day.checked_in ? 'checked' : ''} ${
                      day.date === todayStr ? 'today' : ''
                    }`}
                  >
                    <Text className="cell-date">{parseInt(day.date.slice(8), 10)}</Text>
                    {day.checked_in && <Text className="cell-dot">●</Text>}
                  </View>
                ))}
              </View>

              {/* 月度统计 */}
              <View className="calendar-summary">
                <Text className="summary-text">
                  {t('gamification.monthlyCheckins', {
                    count: calendar?.monthly_checkin_count ?? 0,
                  })}
                </Text>
              </View>

              {/* 打卡按钮 */}
              <Button
                type="primary"
                block
                loading={isCheckingIn}
                onClick={handleCheckin}
                className="checkin-btn"
              >
                {t('gamification.doCheckin')}
              </Button>
            </>
          )}
        </View>
      </ScrollView>

      {/* 徽章解锁弹层（打卡触发 streak 徽章） */}
      <BadgeUnlockPopup />
    </View>
  )
}
