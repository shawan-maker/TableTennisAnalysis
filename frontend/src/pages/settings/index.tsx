/**
 * 设置页（14-tab-pages/settings.md §2）
 * 通知开关 + 隐私（导出/注销）+ 账号信息 + 关于
 *
 * 注：设计样例含 fetchDeletionStatus() 调用，但该方法已被 R19-fix 从
 * userStore 移除（GET /users/account/deletion-status 未在后端 API 契约中
 * 定义）；deletionState 仅由用户主动提交注销后由 store 写入，本页不预查询。
 */
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Switch, Button, Toast, Popup, Skeleton } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useUserStore } from '@/stores/userStore'
import { NOTIF_ITEMS, NOTIF_STORAGE_PREFIX, APP_VERSION } from '@/constants/settings'
import './index.scss'

export default function SettingsPage() {
  const { t } = useTranslation()
  const {
    // 数据导出
    exportTask, exportLoading, requestExport, pollExportStatus,
    // 用户注销
    deletionState, deletionLoading, requestDeletion, cancelDeletion,
  } = useUserStore()

  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  // 通知开关状态
  const [notifStates, setNotifStates] = useState<Record<string, boolean>>({})

  // 注销确认弹窗
  const [deletionDialogVisible, setDeletionDialogVisible] = useState(false)
  const [deletionReason, setDeletionReason] = useState('')

  // 数据导出弹窗
  const [exportPopupVisible, setExportPopupVisible] = useState(false)

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  // 初始化通知开关状态
  useEffect(() => {
    const states: Record<string, boolean> = {}
    NOTIF_ITEMS.forEach((item) => {
      const stored = Taro.getStorageSync(`${NOTIF_STORAGE_PREFIX}${item.storageKey}`)
      states[item.storageKey] = stored === '' ? item.defaultOn : stored === 'true'
    })
    setNotifStates(states)
    // R19-fix: 不预查询注销状态（deletionState 仅由 requestDeletion 写入）
  }, [])

  /** 切换通知开关 */
  const handleNotifChange = (storageKey: string, val: boolean) => {
    setNotifStates((prev) => ({ ...prev, [storageKey]: val }))
    Taro.setStorageSync(`${NOTIF_STORAGE_PREFIX}${storageKey}`, String(val))
  }

  /** 跳转到数据导出 */
  const handleExport = async () => {
    setExportPopupVisible(true)
    try {
      await requestExport()
      const taskId = useUserStore.getState().exportTask?.task_id
      if (taskId) {
        await pollExportStatus(taskId)
      }
    } catch (err: any) {
      showToast(err?.message || t('user.exportFailed'))
    }
  }

  /** 下载导出文件 */
  const handleDownloadExport = () => {
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
  }

  /** 确认注销 */
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

  /** 撤销注销 */
  const handleCancelDeletion = async () => {
    try {
      await cancelDeletion()
      showToast(t('user.deletionCancelled'))
    } catch (err: any) {
      showToast(err?.message || t('user.deletionCancelFailed'))
    }
  }

  /** 检查更新 */
  const handleCheckUpdate = () => {
    // 实际项目中调用 Taro.getUpdateManager() 或后端版本检查 API
    showToast(t('settings.alreadyLatest'))
  }

  /** 反馈意见 */
  const handleFeedback = () => {
    // 跳转到反馈页面或打开客服会话
    showToast(t('settings.feedbackComingSoon'))
  }

  return (
    <View className="settings-page">
      {/* ========== 1. 通知设置 ========== */}
      <View className="settings-section">
        <Text className="section-title">{t('settings.notifSection')}</Text>
        <View className="settings-group">
          {NOTIF_ITEMS.map((item) => (
            <Cell
              key={item.storageKey}
              title={t(item.labelKey)}
              className="settings-cell"
              extra={
                <Switch
                  checked={notifStates[item.storageKey] ?? item.defaultOn}
                  onChange={(val) => handleNotifChange(item.storageKey, val)}
                />
              }
            />
          ))}
        </View>
      </View>

      {/* ========== 2. 隐私设置 ========== */}
      <View className="settings-section">
        <Text className="section-title">{t('settings.privacySection')}</Text>
        <View className="settings-group">
          {/* 数据导出入口 */}
          <Cell
            title={t('user.exportData')}
            description={t('user.exportDataDesc')}
            clickable
            onClick={handleExport}
          />

          {/* 注销冷静期状态（如果存在） */}
          {deletionLoading && !deletionState ? (
            <Skeleton rows={2} visible={deletionLoading} />
          ) : deletionState?.status === 'cooling' ? (
            <View className="deletion-cooling-banner">
              <View className="banner-row">
                <Text className="banner-icon">⚠️</Text>
                <Text className="banner-text">{t('user.deletionCoolingTitle')}</Text>
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
          ) : (
            <Cell
              title={t('user.deleteAccount')}
              description={t('user.deleteAccountDesc')}
              clickable
              onClick={() => setDeletionDialogVisible(true)}
            />
          )}
        </View>
      </View>

      {/* ========== 3. 账号信息 ========== */}
      <View className="settings-section">
        <Text className="section-title">{t('settings.accountSection')}</Text>
        <View className="settings-group">
          <Cell title={t('settings.appVersion')} extra={`v${APP_VERSION}`} />
          <Cell
            title={t('settings.userAgreement')}
            clickable
            onClick={() => showToast(t('settings.openingDocument'))}
          />
          <Cell
            title={t('settings.privacyPolicy')}
            clickable
            onClick={() => showToast(t('settings.openingDocument'))}
          />
        </View>
      </View>

      {/* ========== 4. 关于 ========== */}
      <View className="settings-section">
        <Text className="section-title">{t('settings.aboutSection')}</Text>
        <View className="settings-group">
          <Cell title={t('settings.appVersion')} extra={`v${APP_VERSION}`} />
          <Cell
            title={t('settings.checkUpdate')}
            clickable
            onClick={handleCheckUpdate}
          />
          <Cell
            title={t('settings.feedback')}
            clickable
            onClick={handleFeedback}
          />
        </View>
      </View>

      {/* 注销确认弹窗 */}
      <Popup
        visible={deletionDialogVisible}
        position="bottom"
        round
        onClose={() => {
          setDeletionDialogVisible(false)
          setDeletionReason('')
        }}
      >
        <View className="deletion-popup">
          <View className="popup-header">
            <Text className="popup-title">{t('user.deletionDialogTitle')}</Text>
          </View>
          <View className="deletion-dialog-content">
            <Text className="deletion-warning">{t('user.deletionWarning')}</Text>
            <Text className="deletion-cooling-hint">
              {t('user.deletionCoolingHint')}
            </Text>
            <View className="deletion-reason-section">
              <Text className="reason-label">{t('user.deletionReasonLabel')}</Text>
              <Text className="reason-placeholder">{t('user.deletionReasonPlaceholder')}</Text>
            </View>
          </View>
          <View className="popup-actions">
            <Button
              type="primary"
              block
              loading={deletionLoading}
              onClick={handleConfirmDeletion}
            >
              {t('user.confirmDelete')}
            </Button>
            <Button
              block
              onClick={() => {
                setDeletionDialogVisible(false)
                setDeletionReason('')
              }}
            >
              {t('common.cancel')}
            </Button>
          </View>
        </View>
      </Popup>

      {/* 数据导出弹窗 */}
      <Popup
        visible={exportPopupVisible}
        position="bottom"
        round
        onClose={() => setExportPopupVisible(false)}
      >
        <View className="export-popup">
          <View className="popup-header">
            <Text className="popup-title">{t('user.exportTitle')}</Text>
          </View>
          <View className="export-dialog-content">
            <Text className="export-desc">{t('user.exportDesc')}</Text>
            {exportLoading && !exportTask && (
              <Skeleton rows={2} visible={exportLoading} />
            )}
            {exportTask && (
              <View className="export-status-row">
                <Text className="export-status-text">
                  {t(`user.exportStatus_${exportTask.status}`)}
                </Text>
                {exportTask.status === 'completed' && exportTask.download_url && (
                  <Text className="export-ready">{t('user.downloadExport')}</Text>
                )}
                {exportTask.status === 'failed' && (
                  <Text className="export-retry">{t('user.retryExport')}</Text>
                )}
              </View>
            )}
          </View>
          <View className="popup-actions">
            <Button
              type="primary"
              block
              onClick={() => {
                if (exportTask?.status === 'completed' && exportTask.download_url) {
                  handleDownloadExport()
                } else {
                  setExportPopupVisible(false)
                }
              }}
            >
              {exportTask?.status === 'completed' && exportTask.download_url
                ? t('user.downloadExport')
                : t('common.close')}
            </Button>
          </View>
        </View>
      </Popup>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
