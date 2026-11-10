/**
 * 训练打卡日历（周视图）组件（00-home/frontend.md §4.5）
 * 周一~周日 7 天横排：已打卡绿色 ✓、今日红色边框、跨月空格灰点。
 *
 * FS7-P3：后端为月历结构，周视图由 utils/weekView.buildWeekView 派生
 * （页面经 homeStore.weekView 传入；样例的 exp_earned 字段不存在，忽略）。
 */
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import type { WeekView } from '@/utils/weekView'
import { WEEKDAY_KEYS } from '@/constants/home'
import './CheckinCalendar.scss'

interface Props {
  data: WeekView | null
  loading: boolean
}

export default function CheckinCalendar({ data, loading }: Props) {
  const { t } = useTranslation()

  const handleCheckin = () => {
    if (data?.todayCheckedIn) return
    Taro.navigateTo({ url: '/pages/gamification/checkin-calendar/index' })
  }

  if (loading || !data) {
    return (
      <View className="checkin-calendar">
        <Text className="section-title">📅 {t('home.checkinCalendar')}</Text>
        <View className="loading-placeholder">
          <Skeleton rows={3} animated />
        </View>
      </View>
    )
  }

  return (
    <View className="checkin-calendar">
      <View className="section-header">
        <Text className="section-title">📅 {t('home.checkinCalendar')}</Text>
        <Text className="streak-badge">
          🔥 {data.streakDays} {t('home.days')}
        </Text>
      </View>

      <View className="week-row">
        {data.days.map((day, i) => (
          <View
            className={`day-cell ${day.checked_in ? 'checked' : ''} ${day.isToday ? 'today' : ''}`}
            key={day.date}
          >
            <Text className="day-weekday">{t(WEEKDAY_KEYS[i])}</Text>
            <Text className="day-date">{Number(day.date.slice(8, 10))}</Text>
            <View className="day-status">
              {day.checked_in ? (
                <Text className="check-icon">✓</Text>
              ) : (
                <Text className="check-placeholder" aria-hidden="true">·</Text>
              )}
            </View>
          </View>
        ))}
      </View>

      <View
        className={`checkin-btn ${data.todayCheckedIn ? 'done' : ''}`}
        onClick={handleCheckin}
      >
        <Text>
          {data.todayCheckedIn ? t('home.todayCheckedIn') : t('home.checkinNow')}
        </Text>
      </View>
    </View>
  )
}
