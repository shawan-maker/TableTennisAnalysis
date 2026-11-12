/**
 * 个人档案页（02-user/frontend.md §4.1）
 * 档案展示 + 积分更新 + 注销（X-23）+ 数据导出（X-24）
 *
 * R-FE-R1 批次A（遗漏检查报告 round1）：功能入口区集中修复 5 个
 * 已实现页面零入口问题——我的分析（FE-P1-5）/ 训练报告（FE-P0-2）/
 * 我的订单（FE-P1-11）/ 我的徽章（FE-P0-3）/ 设置（FE-P0-1）。
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Image, ScrollView } from '@tarojs/components'
import { Cell, Button, Toast, Progress, Dialog, Popup, Tag, Skeleton, TextArea } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useAuthStore } from '@/stores/authStore'
import { useTranslation } from 'react-i18next'
// R-FE-R2 批次E（FE-P3-33）：注销冷静期公共横幅（倒计时逻辑下沉组件）
import DeletionCoolingBanner from '@/components/DeletionCoolingBanner'
import './index.scss'

export default function ProfilePage() {
  const { t } = useTranslation()
  const {
    profile, fetchProfile, updateRating,
    // X-23: 注销
    deletionState, deletionLoading, requestDeletion, cancelDeletion,
    // X-24: 数据导出
    exportTask, exportLoading, requestExport, pollExportStatus,
  } = useUserStore()
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  // X-23: 注销弹窗状态
  const [deletionDialogVisible, setDeletionDialogVisible] = useState(false)
  const [deletionReason, setDeletionReason] = useState('')

  // X-24: 数据导出弹窗状态
  const [exportPopupVisible, setExportPopupVisible] = useState(false)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    // R-FE-R1 批次B（FE-P2-1）：未登录不拉档案——改为渲染登录引导卡
    //（修复前未登录 fetchProfile 必 401，只能靠 request 拦截器被动 reLaunch 登录页）
    if (useAuthStore.getState().isAuthenticated) {
      fetchProfile()
    }
    // R19-fix: 移除 fetchDeletionStatus() 调用
    // 原因：GET /users/account/deletion-status 端点未在后端 API 契约中定义
    // deletionState 仅由用户主动提交注销请求后由 store 写入
  }, [])

  // X-24: 导出轮询清理
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
      }
    }
  }, [])

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  /** 跳转到档案编辑页 */
  const handleEditProfile = () => {
    Taro.navigateTo({ url: '/pages/user/edit/index' })
  }

  /** 更新积分 */
  const handleUpdateRating = () => {
    // editable showModal：weapp 原生支持可编辑弹窗，Taro 类型定义未覆盖（as any 绕过）
    Taro.showModal({
      title: t('user.updateRating'),
      content: t('user.ratingInputPrompt'),
      editable: true,
      placeholderText: '500-3000',
      success: async (res: any) => {
        if (res.confirm && res.content) {
          const rating = parseInt(res.content, 10)
          if (isNaN(rating) || rating < 500 || rating > 3000) {
            showToast(t('user.ratingOutOfRange'))
            return
          }
          try {
            await updateRating(rating)
            showToast(t('user.ratingUpdated'))
          } catch (err: any) {
            showToast(err?.message || t('user.updateFailed'))
          }
        }
      },
    } as any)
  }

  /** 跳转到乒乓大数据 */
  const handleBigData = () => {
    Taro.navigateTo({ url: '/pages/user/big-data/index' })
  }

  /** 跳转到积分历史 */
  const handleRatingHistory = () => {
    Taro.navigateTo({ url: '/pages/user/rating-history/index' })
  }

  // X-23: 确认注销
  const handleConfirmDeletion = async () => {
    // R-FE-R2 批次E（FE-P3-25）：提交中防重（设计承诺 confirmBtnProps loading，
    // 本地 NutUI 2.7.14 Dialog 无该属性——改入口卫语句拦截，行为等价）
    if (deletionLoading) return
    try {
      await requestDeletion(deletionReason || t('user.deletionDefaultReason'))
      setDeletionDialogVisible(false)
      setDeletionReason('')
      showToast(t('user.deletionRequested'))
    } catch (err: any) {
      showToast(err?.message || t('user.deletionFailed'))
    }
  }

  // X-23: 取消注销
  const handleCancelDeletion = async () => {
    try {
      await cancelDeletion()
      showToast(t('user.deletionCancelled'))
    } catch (err: any) {
      showToast(err?.message || t('user.deletionCancelFailed'))
    }
  }

  // X-24: 发起数据导出
  const handleStartExport = async () => {
    setExportPopupVisible(true)
    try {
      await requestExport()
      // 开启轮询
      const taskId = useUserStore.getState().exportTask?.task_id
      if (taskId) {
        await pollExportStatus(taskId)
      }
    } catch (err: any) {
      showToast(err?.message || t('user.exportFailed'))
    }
  }

  // X-24: 下载导出文件
  const handleDownloadExport = useCallback(() => {
    if (exportTask?.download_url) {
      Taro.downloadFile({
        url: exportTask.download_url,
        success: (res) => {
          Taro.openDocument({
            filePath: res.tempFilePath,
            fail: () => showToast(t('user.downloadFailed')),
          })
        },
        fail: () => showToast(t('user.downloadFailed')),
      })
    }
  }, [exportTask, t])

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  // R-FE-R1 批次B（FE-P2-1）：未登录引导卡（01-auth frontend.md L12
  // 「我的 Tab → 个人主页 → 登录引导」——修复前无此分支）
  if (!isAuthenticated) {
    return (
      <View className="profile-page login-guide">
        <View
          className="login-guide-card"
          onClick={() => Taro.navigateTo({ url: '/pages/auth/login/index' })}
        >
          <Image
            className="avatar"
            src="https://cdn.pingpongai.com/images/default-avatar.png"
            mode="aspectFill"
            alt={t('auth.loginPrompt')}
          />
          <View className="header-info">
            <Text className="nickname">{t('auth.loginPrompt')}</Text>
            <Text className="login-guide-desc">{t('auth.loginPromptDesc')}</Text>
          </View>
        </View>
      </View>
    )
  }

  if (!profile) {
    return <View className="profile-loading"><Skeleton rows={3} animated /></View>
  }

  const completeness = profile.profile.profile_completeness
  const playingStyleText = profile.profile.playing_style
    ? t(`user.style_${profile.profile.playing_style}`)
    : t('user.notSet')

  return (
    <ScrollView scrollY className="profile-page">
      {/* 用户头部信息 */}
      <View className="profile-header">
        <Image
          className="avatar"
          src={profile.avatar_url || 'https://cdn.pingpongai.com/images/default-avatar.png'}
          mode="aspectFill"
          alt={profile.nickname}
        />
        <View className="header-info">
          <Text className="nickname">{profile.nickname}</Text>
          <View className="rating-row">
            <Text className="rating-label">{t('user.kqsRating')}</Text>
            <Text className="rating-value">
              {profile.profile.kqs_rating || '--'}
            </Text>
            <Text className="update-link" onClick={handleUpdateRating}>
              {t('user.update')}
            </Text>
          </View>
        </View>
        {/* FS7: 通知铃铛迁回首页 TopBar（12-notification §5 设计意图，单一挂载点） */}
      </View>

      {/* 档案完整度 */}
      <View className="completeness-section">
        <View className="section-title">{t('user.profileCompleteness')}</View>
        <Progress
          percent={completeness}
          color="var(--color-primary)"
          strokeWidth="8px"
        />
        <Text className="completeness-text">{completeness}% {t('user.completenessHint')}</Text>
      </View>

      {/* 档案信息 */}
      <View className="info-section">
        <Cell title={t('user.playingStyle')} extra={playingStyleText} />
        <Cell
          title={t('user.selfLevel')}
          extra={
            profile.profile.self_assessed_level
              ? t(`user.level_${profile.profile.self_assessed_level}`)
              : t('user.notSet')
          }
        />
        <Cell
          title={t('user.kqsUsername')}
          extra={profile.profile.kqs_username || t('user.notSet')}
        />
      </View>

      {/* 装备配置 */}
      <View className="equipment-section">
        <View className="section-title">
          {t('user.equipment')}
          <Text className="edit-link" onClick={handleEditProfile}>{t('common.edit')}</Text>
        </View>
        {profile.profile.equipment_config ? (
          <View className="equipment-list">
            {profile.profile.equipment_config.blade && (
              <Cell
                title={t('user.blade')}
                extra={`${profile.profile.equipment_config.blade.brand} ${profile.profile.equipment_config.blade.model}`}
              />
            )}
            {profile.profile.equipment_config.rubber_fh && (
              <Cell
                title={t('user.rubberFH')}
                extra={`${profile.profile.equipment_config.rubber_fh.brand} ${profile.profile.equipment_config.rubber_fh.model}`}
              />
            )}
            {profile.profile.equipment_config.rubber_bh && (
              <Cell
                title={t('user.rubberBH')}
                extra={`${profile.profile.equipment_config.rubber_bh.brand} ${profile.profile.equipment_config.rubber_bh.model}`}
              />
            )}
          </View>
        ) : (
          <View className="empty-equipment">
            <Text className="empty-text">{t('user.noEquipment')}</Text>
            <Button size="small" type="primary" onClick={handleEditProfile}>
              {t('user.addEquipment')}
            </Button>
          </View>
        )}
      </View>

      {/* 快捷入口 */}
      <View className="quick-actions">
        <View className="action-card" onClick={handleBigData}>
          <Text className="action-icon">📊</Text>
          <Text className="action-text">{t('user.bigData')}</Text>
        </View>
        <View className="action-card" onClick={handleRatingHistory}>
          <Text className="action-icon">📈</Text>
          <Text className="action-text">{t('user.ratingHistory')}</Text>
        </View>
        {/* FS6: 会员中心入口（membership/frontend.md §6「我的 Tab → 会员中心」） */}
        <View
          className="action-card"
          onClick={() => Taro.navigateTo({ url: '/pages/membership/index' })}
        >
          <Text className="action-icon">👑</Text>
          <Text className="action-text">{t('membership.title')}</Text>
        </View>
      </View>

      {/* R-FE-R1 批次A：功能入口（修复 5 个已实现页面零入口——报告 FE-P0-1/2/3 + FE-P1-5/11） */}
      <View className="feature-section">
        <Cell
          title={t('analysis.myReports')}
          clickable
          onClick={() => Taro.navigateTo({ url: '/pages/video-analysis/list/index' })}
        />
        <Cell
          title={t('user.progressEntry')}
          clickable
          onClick={() => Taro.navigateTo({ url: '/pages/progress/summary/index' })}
        />
        <Cell
          title={t('payment.ordersEntry')}
          clickable
          onClick={() => Taro.navigateTo({ url: '/pages/payment/orders/index' })}
        />
        <Cell
          title={t('gamification.myBadges')}
          clickable
          onClick={() => Taro.navigateTo({ url: '/pages/gamification/badges/index' })}
        />
        <Cell
          title={t('user.settingsEntry')}
          clickable
          onClick={() => Taro.navigateTo({ url: '/pages/settings/index' })}
        />
      </View>

      {/* X-24: 数据导出入口 */}
      <View className="account-section">
        <Cell
          title={t('user.exportData')}
          description={t('user.exportDataDesc')}
          clickable
          onClick={handleStartExport}
        />
      </View>

      {/* X-23: 注销冷静期状态（R-FE-R2 批次E FE-P3-33：改公共 DeletionCoolingBanner，
          秒级倒计时逻辑随组件下沉） */}
      <DeletionCoolingBanner
        deletionState={deletionState}
        loading={deletionLoading}
        onCancel={handleCancelDeletion}
      />

      {/* X-23: 注销账号入口（冷静期不显示） */}
      {deletionState?.status !== 'cooling' && (
        <View className="danger-section">
          <Cell
            title={t('user.deleteAccount')}
            description={t('user.deleteAccountDesc')}
            clickable
            onClick={() => setDeletionDialogVisible(true)}
          />
        </View>
      )}

      {/* X-23: 注销确认弹窗 */}
      <Dialog
        title={t('user.deletionDialogTitle')}
        visible={deletionDialogVisible}
        onConfirm={handleConfirmDeletion}
        onCancel={() => {
          setDeletionDialogVisible(false)
          setDeletionReason('')
        }}
        confirmText={t('user.confirmDelete')}
        cancelText={t('common.cancel')}
      >
        <View className="deletion-dialog-content">
          <Text className="deletion-warning">{t('user.deletionWarning')}</Text>
          <Text className="deletion-cooling-hint">
            {t('user.deletionCoolingHint')}
          </Text>
          <View className="deletion-reason-section">
            <Text className="reason-label">{t('user.deletionReasonLabel')}</Text>
            <TextArea
              className="reason-input"
              placeholder={t('user.deletionReasonPlaceholder')}
              value={deletionReason}
              onChange={(val) => setDeletionReason(val)}
              maxLength={200}
            />
          </View>
          <View className="deletion-confirm-hint">
            <Text className="confirm-text">
              {t('user.deletionConfirmHint')}
            </Text>
            <Text className="confirm-command">DELETE_ACCOUNT_CONFIRM</Text>
          </View>
        </View>
      </Dialog>

      {/* X-24: 数据导出弹窗 */}
      <Popup
        visible={exportPopupVisible}
        position="bottom"
        round
        onClose={() => setExportPopupVisible(false)}
      >
        <View className="export-popup">
          <View className="popup-header">
            <Text className="popup-title">{t('user.exportTitle')}</Text>
            <Text className="popup-desc">{t('user.exportDesc')}</Text>
          </View>

          {/* 导出进度 */}
          <View className="export-progress">
            {exportLoading && !exportTask && (
              <View className="progress-pending">
                <Text className="progress-text">{t('user.exportStarting')}</Text>
              </View>
            )}
            {exportTask && (
              <>
                <View className="progress-status-row">
                  <Tag
                    type={exportTask.status === 'completed' ? 'success' : exportTask.status === 'failed' ? 'danger' : 'primary'}
                  >
                    {t(`user.exportStatus_${exportTask.status}`)}
                  </Tag>
                </View>
                {(exportTask.status === 'pending' || exportTask.status === 'processing') && (
                  <Progress
                    percent={exportTask.status === 'pending' ? 30 : 70}
                    color="var(--color-primary)"
                    strokeWidth="6px"
                  />
                )}
                {exportTask.status === 'completed' && exportTask.download_url && (
                  <Button
                    type="primary"
                    block
                    onClick={handleDownloadExport}
                    className="download-btn"
                  >
                    {t('user.downloadExport')}
                  </Button>
                )}
                {exportTask.status === 'failed' && (
                  <Button
                    type="default"
                    block
                    onClick={handleStartExport}
                    className="retry-btn"
                  >
                    {t('user.retryExport')}
                  </Button>
                )}
                <Text className="export-task-id">
                  {t('user.exportTaskId')}: {exportTask.task_id}
                </Text>
              </>
            )}
          </View>
        </View>
      </Popup>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </ScrollView>
  )
}
