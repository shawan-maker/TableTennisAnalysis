/**
 * 个人档案页（02-user/frontend.md §4.1）
 * 档案展示 + 积分更新 + 注销（X-23）+ 数据导出（X-24）
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Image, ScrollView } from '@tarojs/components'
import { Cell, Button, Toast, Progress, Dialog, Popup, Tag, Skeleton, TextArea } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useTranslation } from 'react-i18next'
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
  const [deletionCountdown, setDeletionCountdown] = useState('')

  // X-24: 数据导出弹窗状态
  const [exportPopupVisible, setExportPopupVisible] = useState(false)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    fetchProfile()
    // R19-fix: 移除 fetchDeletionStatus() 调用
    // 原因：GET /users/account/deletion-status 端点未在后端 API 契约中定义
    // deletionState 仅由用户主动提交注销请求后由 store 写入
  }, [])

  // X-23: 注销冷静期倒计时
  useEffect(() => {
    if (deletionState?.status === 'cooling' && deletionState.cooling_ends_at) {
      const updateCountdown = () => {
        const endsAt = new Date(deletionState.cooling_ends_at!).getTime()
        const now = Date.now()
        const diff = endsAt - now
        if (diff <= 0) {
          setDeletionCountdown(t('user.deletionExecuted'))
          return
        }
        const hours = Math.floor(diff / (1000 * 60 * 60))
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
        const seconds = Math.floor((diff % (1000 * 60)) / 1000)
        setDeletionCountdown(`${hours}h ${minutes}m ${seconds}s`)
      }
      updateCountdown()
      const timer = setInterval(updateCountdown, 1000)
      return () => clearInterval(timer)
    }
  }, [deletionState, t])

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

      {/* X-24: 数据导出入口 */}
      <View className="account-section">
        <Cell
          title={t('user.exportData')}
          description={t('user.exportDataDesc')}
          clickable
          onClick={handleStartExport}
        />
      </View>

      {/* X-23: 注销冷静期状态（如果存在） */}
      {deletionState?.status === 'cooling' && (
        <View className="deletion-status-banner">
          <View className="banner-icon-row">
            <Text className="banner-icon">⚠️</Text>
            <Text className="banner-title">{t('user.deletionCoolingTitle')}</Text>
          </View>
          <Text className="banner-desc">{t('user.deletionCoolingDesc')}</Text>
          <View className="countdown-row">
            <Text className="countdown-label">{t('user.deletionCountdown')}</Text>
            <Text className="countdown-value">{deletionCountdown}</Text>
          </View>
          <Button
            size="small"
            type="primary"
            loading={deletionLoading}
            onClick={handleCancelDeletion}
          >
            {t('user.cancelDeletion')}
          </Button>
        </View>
      )}

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
