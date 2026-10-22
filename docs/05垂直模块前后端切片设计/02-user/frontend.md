# user 模块 — 前端垂直切片设计

> **模块名称**：`user`
> **前端目录**：`frontend/src/pages/user/` + `frontend/src/services/user.ts` + `frontend/src/stores/userStore.ts`
> **定位**：个人档案编辑、乒乓大数据展示、积分历史折线图、数据导出（X-24）、用户注销（X-23）
> **依据**：前端需求与界面设计 v2.0 §P5.1 / X-23 / X-24、API 详细设计 v1.3 §3

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §P5.1（个人主页 → 个人档案 + 乒乓大数据 + 积分历史）
- [ ] 阅读本模块的 API 契约（§3.1-3.10（不含 §3.7 跨模块端点），9 个端点）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 阅读 auth 模块前端代码（`stores/authStore.ts`，了解 user 基础结构）
- [ ] 确认本切片范围：个人档案编辑页 + 乒乓大数据页 + 积分历史折线图 + 用户注销 UI（X-23）+ 数据导出 UI（X-24）

---

## 2. API Service 模块

```typescript
// frontend/src/services/user.ts
import request from './request'

/**
 * 获取个人档案。
 * 返回用户基础信息 + profile（含 kqs_rating, playing_style, equipment_config, profile_completeness）
 */
export function getProfile() {
  return request.get('/users/profile')
}

/**
 * 更新个人档案（PATCH 语义，仅更新传入字段）。
 * @param data - playing_style / self_assessed_level / equipment_config
 */
export function updateProfile(data: {
  playing_style?: string
  self_assessed_level?: string
  equipment_config?: Record<string, any>
}) {
  return request.patch('/users/profile', data)
}

/**
 * 更新开球网积分。
 * @param rating - 积分值 (500-3000)
 * @param kqsUsername - 开球网用户名（可选）
 * @param source - 来源: manual / kqs_sync
 */
export function updateRating(rating: number, kqsUsername?: string, source: string = 'manual') {
  return request.patch('/users/rating', { rating, kqs_username: kqsUsername, source })
}

/**
 * 积分历史记录（分页）。
 * @param page - 页码
 * @param pageSize - 每页条数
 */
export function getRatingHistory(page: number = 1, pageSize: number = 20) {
  return request.get('/users/rating-history', { page, page_size: pageSize })
}

/**
 * 乒乓大数据（趣味统计，24h 缓存）。
 */
export function getBigData() {
  return request.get('/users/big-data')
}

/**
 * 用户注销（72h 冷静期）。
 * @param reason - 注销原因
 * @param confirmation - 必须为 "DELETE_ACCOUNT_CONFIRM"
 */
export function deleteAccount(reason: string, confirmation: string) {
  return request.delete('/users/account', { reason, confirmation })
}

/**
 * 取消注销（冷静期内可撤销）。
 */
export function cancelDeletion() {
  return request.post('/users/account/cancel-deletion')
}

/**
 * 发起个人数据导出（PIPL 数据可携带权）。
 */
export function exportData() {
  return request.post('/users/export-data')
}

/**
 * 查询导出状态 + 下载链接。
 * @param taskId - 导出任务 ID
 */
export function getExportStatus(taskId: string) {
  return request.get(`/users/export-data/${taskId}`)
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/userStore.ts
import { create } from 'zustand'
import * as userApi from '@/services/user'

interface EquipmentConfig {
  blade?: { brand: string; model: string }
  rubber_fh?: { brand: string; model: string; hardness?: string }
  rubber_bh?: { brand: string; model: string }
  shoes?: string
}

interface UserProfile {
  id: number
  nickname: string
  avatar_url: string | null
  profile: {
    kqs_rating: number | null
    kqs_username: string | null
    playing_style: string | null
    self_assessed_level: string | null
    equipment_config: EquipmentConfig | null
    profile_completeness: number
  }
}

interface BigData {
  highest_win_rating: number | null
  win_streak: number
  match_cities: number
  total_opponents: number
  indirect_wins: string[]
  total_matches: number
  win_rate: number
  favorite_shot: string | null
}

interface RatingHistoryItem {
  id: number
  rating: number
  source: string
  recorded_at: string
}

/** 注销状态 */
export interface AccountDeletionState {
  status: 'none' | 'pending' | 'cooling'  // none: 未发起 / pending: 已发起等待 / cooling: 冷静期内
  scheduled_at: string | null              // 注销计划执行时间
  cooling_ends_at: string | null           // 冷静期结束时间
}

/** 数据导出状态 */
export interface ExportTaskState {
  task_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  download_url: string | null
  created_at: string
  expires_at: string | null
}

interface UserState {
  profile: UserProfile | null
  bigData: BigData | null
  ratingHistory: RatingHistoryItem[]
  ratingHistoryTotal: number
  isLoading: boolean

  // X-23: 用户注销
  deletionState: AccountDeletionState | null
  deletionLoading: boolean

  // X-24: 数据导出
  exportTask: ExportTaskState | null
  exportLoading: boolean

  fetchProfile: () => Promise<void>
  updateProfile: (data: {
    playing_style?: string
    self_assessed_level?: string
    equipment_config?: Record<string, any>
  }) => Promise<void>
  updateRating: (rating: number, kqsUsername?: string) => Promise<void>
  fetchRatingHistory: (page?: number, pageSize?: number) => Promise<void>
  fetchBigData: () => Promise<void>

  // X-23: 用户注销
  requestDeletion: (reason: string) => Promise<void>
  cancelDeletion: () => Promise<void>

  // X-24: 数据导出
  requestExport: () => Promise<void>
  fetchExportStatus: (taskId: string) => Promise<void>
  pollExportStatus: (taskId: string) => Promise<void>
  handleExportCompleted: (data: ExportTaskState) => void
}

export const useUserStore = create<UserState>((set, get) => ({
  profile: null,
  bigData: null,
  ratingHistory: [],
  ratingHistoryTotal: 0,
  isLoading: false,
  deletionState: null,
  deletionLoading: false,
  exportTask: null,
  exportLoading: false,

  fetchProfile: async () => {
    set({ isLoading: true })
    try {
      const res = await userApi.getProfile()
      set({ profile: res.data.data })
    } catch (error) {
      console.error('fetchProfile failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  updateProfile: async (data) => {
    set({ isLoading: true })
    try {
      await userApi.updateProfile(data)
      // 重新获取档案以更新完整度
      const res = await userApi.getProfile()
      set({ profile: res.data.data })
    } catch (error) {
      console.error('updateProfile failed', error)
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  updateRating: async (rating, kqsUsername) => {
    try {
      await userApi.updateRating(rating, kqsUsername)
      // 重新获取档案
      const res = await userApi.getProfile()
      set({ profile: res.data.data })
    } catch (error) {
      console.error('updateRating failed', error)
      throw error
    }
  },

  fetchRatingHistory: async (page = 1, pageSize = 20) => {
    try {
      const res = await userApi.getRatingHistory(page, pageSize)
      const data = res.data.data
      set({
        ratingHistory: data.items,
        ratingHistoryTotal: data.total,
      })
    } catch (error) {
      console.error('fetchRatingHistory failed', error)
      throw error
    }
  },

  fetchBigData: async () => {
    try {
      const res = await userApi.getBigData()
      set({ bigData: res.data.data })
    } catch (error) {
      console.error('fetchBigData failed', error)
      throw error
    }
  },

  // X-23: 用户注销
  requestDeletion: async (reason: string) => {
    set({ deletionLoading: true })
    try {
      await userApi.deleteAccount(reason, 'DELETE_ACCOUNT_CONFIRM')
      set({
        deletionState: {
          status: 'cooling',
          scheduled_at: new Date().toISOString(),
          cooling_ends_at: new Date(Date.now() + 72 * 60 * 60 * 1000).toISOString(),
        },
      })
    } catch (error) {
      console.error('requestDeletion failed', error)
      throw error
    } finally {
      set({ deletionLoading: false })
    }
  },

  // R19-fix: 移除 fetchDeletionStatus 方法
  // 原因：GET /users/account/deletion-status 端点未在后端 API 契约中定义
  // 修改后：deletionState 由 requestDeletion 提交注销后写入 store
  //       页面加载时不再预查询注销状态（用户提交注销后自然进入冷静期）

  cancelDeletion: async () => {
    set({ deletionLoading: true })
    try {
      await userApi.cancelDeletion()
      set({ deletionState: null })
    } catch (error) {
      console.error('cancelDeletion failed', error)
      throw error
    } finally {
      set({ deletionLoading: false })
    }
  },

  // X-24: 数据导出
  requestExport: async () => {
    set({ exportLoading: true })
    try {
      const res = await userApi.exportData()
      set({ exportTask: res.data.data })
    } catch (error) {
      console.error('requestExport failed', error)
      throw error
    } finally {
      set({ exportLoading: false })
    }
  },

  fetchExportStatus: async (taskId: string) => {
    try {
      const res = await userApi.getExportStatus(taskId)
      set({ exportTask: res.data.data })
    } catch {
      // 查询失败不阻塞
    }
  },

  pollExportStatus: async (taskId: string) => {
    // 轮询直到完成或失败（最多 5 次，间隔 3s）
    // 注意：export_completed WS 事件可通过 handleExportCompleted 直接更新状态，无需轮询
    for (let i = 0; i < 5; i++) {
      await new Promise((resolve) => setTimeout(resolve, 3000))
      await get().fetchExportStatus(taskId)
      const current = useUserStore.getState().exportTask
      if (current?.status === 'completed' || current?.status === 'failed') {
        break
      }
    }
  },

  // X-24: 处理 export_completed WebSocket 事件
  // 当后端通过 WS 推送 export_completed 事件时，直接更新导出任务状态，
  // 无需依赖轮询。调用方应在 profile 页面通过 useWebSocket.onMessage 监听
  // msg.event === 'export_completed' 后调用此方法。
  handleExportCompleted: (data: ExportTaskState) => {
    set({ exportTask: data })
  },
}))
```

---

## 4. 主要页面组件

### 4.1 个人档案页

```tsx
// frontend/src/pages/user/profile/index.tsx
import { useEffect, useState, useCallback, useRef } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Image, ScrollView } from '@tarojs/components'
import { Cell, Button, Toast, Progress, Dialog, Popup, Tag, Skeleton, Textarea } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useAuthStore } from '@/stores/authStore'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function ProfilePage() {
  const { t } = useTranslation()
  const {
    profile, fetchProfile, updateRating, isLoading,
    // X-23: 注销
    deletionState, deletionLoading, requestDeletion, cancelDeletion,
    // X-24: 数据导出
    exportTask, exportLoading, requestExport, pollExportStatus,
  } = useUserStore()
  const { logout } = useAuthStore()
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
    Taro.showModal({
      title: t('user.updateRating'),
      content: t('user.ratingInputPrompt'),
      editable: true,
      placeholderText: '500-3000',
      success: async (res) => {
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
    })
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
      </View>

      {/* 档案完整度 */}
      <View className="completeness-section">
        <View className="section-title">{t('user.profileCompleteness')}</View>
        <Progress
          percentage={completeness}
          color="var(--color-primary)"
          strokeWidth={8}
        />
        <Text className="completeness-text">{completeness}% {t('user.completenessHint')}</Text>
      </View>

      {/* 档案信息 */}
      <View className="info-section">
        <Cell title={t('user.playingStyle')} value={playingStyleText} />
        <Cell
          title={t('user.selfLevel')}
          value={
            profile.profile.self_assessed_level
              ? t(`user.level_${profile.profile.self_assessed_level}`)
              : t('user.notSet')
          }
        />
        <Cell
          title={t('user.kqsUsername')}
          value={profile.profile.kqs_username || t('user.notSet')}
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
                value={`${profile.profile.equipment_config.blade.brand} ${profile.profile.equipment_config.blade.model}`}
              />
            )}
            {profile.profile.equipment_config.rubber_fh && (
              <Cell
                title={t('user.rubberFH')}
                value={`${profile.profile.equipment_config.rubber_fh.brand} ${profile.profile.equipment_config.rubber_fh.model}`}
              />
            )}
            {profile.profile.equipment_config.rubber_bh && (
              <Cell
                title={t('user.rubberBH')}
                value={`${profile.profile.equipment_config.rubber_bh.brand} ${profile.profile.equipment_config.rubber_bh.model}`}
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
      </View>

      {/* X-24: 数据导出入口 */}
      <View className="account-section">
        <Cell
          title={t('user.exportData')}
          subTitle={t('user.exportDataDesc')}
          isLink
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
            subTitle={t('user.deleteAccountDesc')}
            isLink
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
        confirmBtnProps={{ loading: deletionLoading }}
      >
        <View className="deletion-dialog-content">
          <Text className="deletion-warning">{t('user.deletionWarning')}</Text>
          <Text className="deletion-cooling-hint">
            {t('user.deletionCoolingHint')}
          </Text>
          <View className="deletion-reason-section">
            <Text className="reason-label">{t('user.deletionReasonLabel')}</Text>
            <Textarea
              className="reason-input"
              placeholder={t('user.deletionReasonPlaceholder')}
              value={deletionReason}
              onChange={(val) => setDeletionReason(val)}
              maxlength={200}
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
                    percentage={exportTask.status === 'pending' ? 30 : 70}
                    color="var(--color-primary)"
                    strokeWidth={6}
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
```

### 4.2 档案编辑页

```tsx
// frontend/src/pages/user/edit.tsx
import { useState, useEffect } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Picker } from '@tarojs/components'
import { Cell, Button, Form, Toast, Input, Textarea } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useTranslation } from 'react-i18next'
import './edit.scss'

const PLAYING_STYLES = [
  { value: 'loop', labelKey: 'user.style_loop' },
  { value: 'quick_attack', labelKey: 'user.style_quick_attack' },
  { value: 'chop', labelKey: 'user.style_chop' },
  { value: 'allround', labelKey: 'user.style_allround' },
]

const SELF_LEVELS = [
  { value: 'beginner', labelKey: 'user.level_beginner' },
  { value: 'intermediate', labelKey: 'user.level_intermediate' },
  { value: 'advanced', labelKey: 'user.level_advanced' },
]

// P1-FE3 i18n：常量层无法使用 useTranslation hook，使用 labelKey 替代 label，
// 组件渲染时通过 t(item.labelKey) 获取本地化文本

export default function ProfileEditPage() {
  const { t } = useTranslation()
  const { profile, updateProfile, fetchProfile } = useUserStore()
  const [playingStyle, setPlayingStyle] = useState('')
  const [selfLevel, setSelfLevel] = useState('')
  const [bladeBrand, setBladeBrand] = useState('')
  const [bladeModel, setBladeModel] = useState('')
  const [rubberFhBrand, setRubberFhBrand] = useState('')
  const [rubberFhModel, setRubberFhModel] = useState('')
  const [rubberBhBrand, setRubberBhBrand] = useState('')
  const [rubberBhModel, setRubberBhModel] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  useEffect(() => {
    if (!profile) {
      fetchProfile()
      return
    }
    const p = profile.profile
    setPlayingStyle(p.playing_style || '')
    setSelfLevel(p.self_assessed_level || '')
    const eq = p.equipment_config
    if (eq) {
      setBladeBrand(eq.blade?.brand || '')
      setBladeModel(eq.blade?.model || '')
      setRubberFhBrand(eq.rubber_fh?.brand || '')
      setRubberFhModel(eq.rubber_fh?.model || '')
      setRubberBhBrand(eq.rubber_bh?.brand || '')
      setRubberBhModel(eq.rubber_bh?.model || '')
    }
  }, [profile])

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const data: any = {}
      if (playingStyle) data.playing_style = playingStyle
      if (selfLevel) data.self_assessed_level = selfLevel

      // 仅在有输入时组装装备配置
      if (bladeBrand || bladeModel || rubberFhBrand || rubberBhBrand) {
        data.equipment_config = {}
        if (bladeBrand || bladeModel) {
          data.equipment_config.blade = { brand: bladeBrand, model: bladeModel }
        }
        if (rubberFhBrand || rubberFhModel) {
          data.equipment_config.rubber_fh = { brand: rubberFhBrand, model: rubberFhModel }
        }
        if (rubberBhBrand || rubberBhModel) {
          data.equipment_config.rubber_bh = { brand: rubberBhBrand, model: rubberBhModel }
        }
      }

      await updateProfile(data)
      showToast(t('common.saved'))
      setTimeout(() => Taro.navigateBack(), 1000)
    } catch (err: any) {
      showToast(err?.message || t('common.saveFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <View className="edit-page">
      {/* 打法选择 */}
      <View className="form-section">
        <View className="section-title">{t('user.playingStyle')}</View>
        <View className="style-grid">
          {PLAYING_STYLES.map((s) => (
            <View
              key={s.value}
              className={`style-chip ${playingStyle === s.value ? 'active' : ''}`}
              onClick={() => setPlayingStyle(s.value)}
            >
              <Text>{t(s.labelKey)}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* 自评水平 */}
      <View className="form-section">
        <View className="section-title">{t('user.selfLevel')}</View>
        <View className="level-grid">
          {SELF_LEVELS.map((l) => (
            <View
              key={l.value}
              className={`level-chip ${selfLevel === l.value ? 'active' : ''}`}
              onClick={() => setSelfLevel(l.value)}
            >
              <Text>{t(l.labelKey)}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* 装备配置 */}
      <View className="form-section">
        <View className="section-title">{t('user.equipment')}</View>
        <Cell title={t('user.bladeBrand')}>
          <Input
            placeholder={t('user.brandPlaceholder')}
            value={bladeBrand}
            onChange={(val) => setBladeBrand(val)}
          />
        </Cell>
        <Cell title={t('user.bladeModel')}>
          <Input
            placeholder={t('user.modelPlaceholder')}
            value={bladeModel}
            onChange={(val) => setBladeModel(val)}
          />
        </Cell>
        <Cell title={t('user.rubberFHBrand')}>
          <Input
            placeholder={t('user.brandPlaceholder')}
            value={rubberFhBrand}
            onChange={(val) => setRubberFhBrand(val)}
          />
        </Cell>
        <Cell title={t('user.rubberFHModel')}>
          <Input
            placeholder={t('user.modelPlaceholder')}
            value={rubberFhModel}
            onChange={(val) => setRubberFhModel(val)}
          />
        </Cell>
        <Cell title={t('user.rubberBHBrand')}>
          <Input
            placeholder={t('user.brandPlaceholder')}
            value={rubberBhBrand}
            onChange={(val) => setRubberBhBrand(val)}
          />
        </Cell>
        <Cell title={t('user.rubberBHModel')}>
          <Input
            placeholder={t('user.modelPlaceholder')}
            value={rubberBhModel}
            onChange={(val) => setRubberBhModel(val)}
          />
        </Cell>
      </View>

      <Button
        type="primary"
        block
        loading={submitting}
        onClick={handleSubmit}
        className="submit-btn"
      >
        {t('common.save')}
      </Button>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

### 4.3 乒乓大数据页

```tsx
// frontend/src/pages/user/big-data.tsx
import { useEffect } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useTranslation } from 'react-i18next'
import './big-data.scss'

export default function BigDataPage() {
  const { t } = useTranslation()
  const { bigData, fetchBigData } = useUserStore()

  useEffect(() => {
    fetchBigData()
  }, [])

  if (!bigData) {
    return <View className="loading"><Skeleton rows={3} animated /></View>
  }

  return (
    <ScrollView scrollY className="big-data-page">
      {/* 趣味统计卡片 */}
      <View className="stat-grid">
        <View className="stat-card highlight">
          <Text className="stat-value">{bigData.highest_win_rating || '--'}</Text>
          <Text className="stat-label">{t('user.highestWinRating')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{bigData.win_streak}</Text>
          <Text className="stat-label">{t('user.winStreak')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{bigData.match_cities}</Text>
          <Text className="stat-label">{t('user.matchCities')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{bigData.total_opponents}</Text>
          <Text className="stat-label">{t('user.totalOpponents')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{bigData.total_matches}</Text>
          <Text className="stat-label">{t('user.totalMatches')}</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-value">{(bigData.win_rate * 100).toFixed(0)}%</Text>
          <Text className="stat-label">{t('user.winRate')}</Text>
        </View>
      </View>

      {/* 间接胜利 */}
      {bigData.indirect_wins.length > 0 && (
        <View className="indirect-section">
          <View className="section-title">
            <Text className="title-icon">💡</Text>
            {t('user.indirectWins')}
          </View>
          <View className="indirect-chips">
            {bigData.indirect_wins.map((name, idx) => (
              <View key={idx} className="indirect-chip">
                <Text>{name}</Text>
              </View>
            ))}
          </View>
          <Text className="indirect-desc">{t('user.indirectWinsDesc')}</Text>
        </View>
      )}

      {/* 最常用技术 */}
      {bigData.favorite_shot && (
        <View className="favorite-shot-section">
          <View className="section-title">{t('user.favoriteShot')}</View>
          <View className="favorite-shot-card">
            <Text className="shot-icon">🏓</Text>
            <Text className="shot-name">
              {t(`technique.${bigData.favorite_shot}`)}
            </Text>
          </View>
        </View>
      )}
    </ScrollView>
  )
}
```

### 4.4 积分历史折线图

```tsx
// frontend/src/pages/user/rating-history.tsx
import { useEffect, useState } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { Empty } from '@nutui/nutui-react'
import { useUserStore } from '@/stores/userStore'
import { useTranslation } from 'react-i18next'
import './rating-history.scss'

export default function RatingHistoryPage() {
  const { t } = useTranslation()
  const { ratingHistory, ratingHistoryTotal, fetchRatingHistory } = useUserStore()

  useEffect(() => {
    fetchRatingHistory(1, 100) // 拉取足够数据用于折线图
  }, [])

  // 构建折线图数据
  const chartData = [...ratingHistory].reverse() // 按时间正序排列

  // 计算折线图坐标
  const maxRating = Math.max(...chartData.map((d) => d.rating), 1500)
  const minRating = Math.min(...chartData.map((d) => d.rating), 1400)
  const range = maxRating - minRating || 100

  const chartWidth = 320
  const chartHeight = 180
  const padding = 20
  const pointSpacing = chartData.length > 1
    ? (chartWidth - padding * 2) / (chartData.length - 1)
    : 0

  const points = chartData.map((d, i) => ({
    x: padding + i * pointSpacing,
    y: chartHeight - padding - ((d.rating - minRating) / range) * (chartHeight - padding * 2),
    rating: d.rating,
    date: d.recorded_at,
  }))

  const pathD = points.length > 0
    ? points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
    : ''

  return (
    <ScrollView scrollY className="rating-history-page">
      {/* 折线图 */}
      <View className="chart-section">
        <View className="section-title">{t('user.ratingChart')}</View>
        {chartData.length > 0 ? (
          <View className="chart-container">
            {/* SVG 折线图 */}
            <View className="svg-wrapper">
              {/* 简化实现：用 View 组件模拟折线图 */}
              <View className="chart-axis-y">
                <Text className="axis-label">{maxRating}</Text>
                <Text className="axis-label">{Math.round((maxRating + minRating) / 2)}</Text>
                <Text className="axis-label">{minRating}</Text>
              </View>
              <View className="chart-plot">
                {points.map((p, i) => (
                  <View
                    key={i}
                    className="chart-point"
                    style={{
                      left: `${(p.x / chartWidth) * 100}%`,
                      top: `${(p.y / chartHeight) * 100}%`,
                    }}
                  >
                    <Text className="point-value">{p.rating}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>
        ) : (
          <Empty description={t('user.noRatingHistory')} />
        )}
      </View>

      {/* 历史记录列表 */}
      <View className="history-list-section">
        <View className="section-title">
          {t('user.historyRecords')} ({ratingHistoryTotal})
        </View>
        {ratingHistory.map((item) => (
          <View key={item.id} className="history-item">
            <View className="item-info">
              <Text className="item-rating">{item.rating}</Text>
              <Text className="item-source">
                {item.source === 'manual' ? t('user.sourceManual') : t('user.sourceKqs')}
              </Text>
            </View>
            <Text className="item-date">
              {new Date(item.recorded_at).toLocaleDateString()}
            </Text>
          </View>
        ))}
      </View>
    </ScrollView>
  )
}
```

---

## 5. 样式

```scss
// frontend/src/pages/user/profile/index.scss
.profile-page {
  min-height: 100vh;
  background: var(--color-background);
}

.profile-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  color: var(--color-text-secondary);
  font-size: 15px;
}

.profile-header {
  display: flex;
  align-items: center;
  padding: var(--spacing-lg) var(--spacing-md);
  background: var(--color-card);

  .avatar {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    margin-right: var(--spacing-md);
    background: var(--color-divider);
  }

  .header-info {
    flex: 1;

    .nickname {
      font-size: 18px;
      font-weight: bold;
      color: var(--color-text-primary);
    }

    .rating-row {
      display: flex;
      align-items: center;
      margin-top: var(--spacing-sm);
      gap: var(--spacing-sm);

      .rating-label {
        font-size: 13px;
        color: var(--color-text-secondary);
      }

      .rating-value {
        font-size: 18px;
        font-weight: bold;
        color: var(--color-secondary);
      }

      .update-link {
        font-size: 13px;
        color: var(--color-primary);
      }
    }
  }
}

.completeness-section {
  margin: var(--spacing-sm-md) var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-card);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);

  .section-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm-md);
  }

  .completeness-text {
    font-size: 13px;
    color: var(--color-text-secondary);
    margin-top: var(--spacing-sm);
    display: block;
  }
}

.info-section,
.equipment-section,
.quick-actions {
  margin: var(--spacing-sm-md) var(--spacing-md);
  background: var(--color-card);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

.equipment-section {
  .section-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--spacing-md);
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);

    .edit-link {
      font-size: 13px;
      font-weight: 400;
      color: var(--color-primary);
    }
  }

  .empty-equipment {
    padding: var(--spacing-lg) var(--spacing-md);
    text-align: center;

    .empty-text {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-bottom: var(--spacing-sm-md);
    }
  }
}

.quick-actions {
  display: flex;
  padding: var(--spacing-md);
  gap: var(--spacing-sm-md);

  .action-card {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: var(--spacing-md) var(--spacing-sm);
    background: var(--color-background);
    border-radius: var(--radius-sm);

    .action-icon {
      font-size: 24px;
      margin-bottom: var(--spacing-xs);
    }

    .action-text {
      font-size: 13px;
      color: var(--color-text-primary);
    }
  }
}

/* X-24: 数据导出入口 */
.account-section {
  margin: var(--spacing-sm-md) var(--spacing-md);
  background: var(--color-card);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

/* X-23: 注销冷静期状态横幅 */
.deletion-status-banner {
  margin: var(--spacing-sm-md) var(--spacing-md);
  padding: var(--spacing-md);
  background: color-mix(in srgb, var(--color-primary) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-primary) 20%, transparent);
  border-radius: var(--radius-md);

  .banner-icon-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    margin-bottom: var(--spacing-sm);

    .banner-icon {
      font-size: 18px;
    }

    .banner-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--color-primary);
    }
  }

  .banner-desc {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
    line-height: 1.5;
    margin-bottom: var(--spacing-sm-md);
  }

  .countdown-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--spacing-sm-md);

    .countdown-label {
      font-size: 13px;
      color: var(--color-text-secondary);
    }

    .countdown-value {
      font-size: 18px;
      font-weight: bold;
      color: var(--color-primary);
      font-variant-numeric: tabular-nums;
    }
  }
}

/* X-23: 注销入口（危险区域） */
.danger-section {
  margin: var(--spacing-sm-md) var(--spacing-md) var(--spacing-xl);
  background: var(--color-card);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

/* X-23: 注销确认弹窗内容 */
.deletion-dialog-content {
  padding: var(--spacing-xs) 0;

  .deletion-warning {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--color-primary);
    margin-bottom: var(--spacing-sm);
  }

  .deletion-cooling-hint {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
    line-height: 1.5;
    margin-bottom: var(--spacing-md);
  }

  .deletion-reason-section {
    margin-bottom: var(--spacing-md);

    .reason-label {
      display: block;
      font-size: 13px;
      color: var(--color-text-primary);
      margin-bottom: var(--spacing-sm);
    }

    .reason-input {
      width: 100%;
      min-height: 80px;
      padding: var(--spacing-sm) var(--spacing-sm-md);
      background: var(--color-background);
      border: 1px solid var(--color-divider);
      border-radius: var(--radius-sm);
      font-size: 13px;
      color: var(--color-text-primary);
      box-sizing: border-box;
    }
  }

  .deletion-confirm-hint {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    padding: var(--spacing-sm) var(--spacing-sm-md);
    background: color-mix(in srgb, var(--color-primary) 5%, transparent);
    border-radius: var(--radius-sm);

    .confirm-text {
      font-size: 12px;
      color: var(--color-text-secondary);
    }

    .confirm-command {
      font-size: 13px;
      font-family: monospace;
      font-weight: bold;
      color: var(--color-primary);
    }
  }
}

/* X-24: 数据导出弹窗 */
.export-popup {
  padding: var(--spacing-lg) var(--spacing-md);

  .popup-header {
    text-align: center;
    margin-bottom: 20px;

    .popup-title {
      display: block;
      font-size: 18px;
      font-weight: bold;
      color: var(--color-text-primary);
    }

    .popup-desc {
      display: block;
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-top: var(--spacing-xs);
    }
  }

  .export-progress {
    .progress-pending {
      padding: var(--spacing-lg) 0;
      text-align: center;

      .progress-text {
        font-size: 13px;
        color: var(--color-text-secondary);
      }
    }

    .progress-status-row {
      display: flex;
      justify-content: center;
      margin-bottom: var(--spacing-md);
    }

    .download-btn,
    .retry-btn {
      margin-top: var(--spacing-md);
    }

    .export-task-id {
      display: block;
      margin-top: var(--spacing-sm-md);
      font-size: 12px;
      color: var(--color-text-secondary);
      text-align: center;
      word-break: break-all;
    }
  }
}
```

```scss
// frontend/src/pages/user/big-data.scss
.big-data-page {
  min-height: 100vh;
  background: var(--color-background);
  padding: var(--spacing-md);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-sm-md);

  .stat-card {
    background: var(--color-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-lg) var(--spacing-md);
    text-align: center;
    box-shadow: var(--shadow-card);

    .stat-value {
      display: block;
      font-size: 32px;
      font-weight: bold;
      color: var(--color-secondary);
    }

    .stat-label {
      display: block;
      margin-top: var(--spacing-xs);
      font-size: 13px;
      color: var(--color-text-secondary);
    }

    &.highlight .stat-value {
      color: var(--color-primary);
    }
  }
}

.indirect-section {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-card);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);

  .section-title {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm-md);

    .title-icon {
      font-size: 18px;
    }
  }

  .indirect-chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--spacing-sm);

    .indirect-chip {
      padding: var(--spacing-xs) var(--spacing-sm-md);
      background: var(--color-accent);
      color: var(--color-text-inverse);
      border-radius: var(--radius-md);
      font-size: 13px;
    }
  }

  .indirect-desc {
    display: block;
    margin-top: var(--spacing-sm);
    font-size: 12px;
    color: var(--color-text-secondary);
  }
}
```

```scss
// frontend/src/pages/user/edit.scss
.edit-page {
  min-height: 100vh;
  background: var(--color-background);
  padding-bottom: 80px;
}

.form-section {
  margin: var(--spacing-sm-md) var(--spacing-md);
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  box-shadow: var(--shadow-card);

  .section-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm-md);
  }
}

.style-grid,
.level-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);

  .style-chip,
  .level-chip {
    padding: var(--spacing-sm) var(--spacing-md);
    background: var(--color-background);
    border: 2px solid transparent;
    border-radius: var(--radius-sm);
    font-size: 13px;
    color: var(--color-text-primary);

    &.active {
      background: color-mix(in srgb, var(--color-primary) 10%, transparent);
      border-color: var(--color-primary);
      color: var(--color-primary);
    }
  }
}

.submit-btn {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 48px;
  background: var(--color-primary) !important;
  color: var(--color-text-inverse) !important;
  border-radius: 0 !important;
  font-size: 15px;
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 profile 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',
    'pages/user/profile/index',           // 新增：个人档案
    'pages/user/edit/index',            // 新增：档案编辑
    'pages/user/big-data/index',        // 新增：乒乓大数据
    'pages/user/rating-history/index',  // 新增：积分历史
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "user": {
    "kqsRating": "开球网积分",
    "update": "更新",
    "updateRating": "更新积分",
    "ratingInputPrompt": "请输入新的积分值 (500-3000)",
    "ratingOutOfRange": "积分值必须在 500-3000 之间",
    "ratingUpdated": "积分已更新",
    "updateFailed": "更新失败",
    "playingStyle": "打法类型",
    "selfLevel": "自评水平",
    "kqsUsername": "开球网用户名",
    "equipment": "我的装备",
    "blade": "底板",
    "bladeBrand": "底板品牌",
    "bladeModel": "底板型号",
    "rubberFH": "正手胶皮",
    "rubberFHBrand": "正手胶皮品牌",
    "rubberFHModel": "正手胶皮型号",
    "rubberBH": "反手胶皮",
    "rubberBHBrand": "反手胶皮品牌",
    "rubberBHModel": "反手胶皮型号",
    "brandPlaceholder": "请输入品牌",
    "modelPlaceholder": "请输入型号",
    "notSet": "未设置",
    "noEquipment": "尚未填写装备信息",
    "addEquipment": "添加装备",
    "profileCompleteness": "档案完整度",
    "completenessHint": "完整档案可获得更精准的训练建议",
    "bigData": "乒乓大数据",
    "ratingHistory": "积分历史",
    "style_loop": "弧圈型",
    "style_quick_attack": "快攻型",
    "style_chop": "削球型",
    "style_allround": "全面型",
    "level_beginner": "初级",
    "level_intermediate": "中级",
    "level_advanced": "高级",
    "highestWinRating": "战胜最高分",
    "winStreak": "连胜纪录",
    "matchCities": "比赛城市数",
    "totalOpponents": "累计交手",
    "totalMatches": "累计比赛",
    "winRate": "总胜率",
    "indirectWins": "间接战胜",
    "indirectWinsDesc": "基于比赛胜负关系链计算，仅供参考",
    "favoriteShot": "最常用技术",
    "ratingChart": "积分变化曲线",
    "historyRecords": "历史记录",
    "noRatingHistory": "暂无积分历史记录",
    "sourceManual": "手动录入",
    "sourceKqs": "开球网同步",
    "exportData": "导出我的数据",
    "exportDataDesc": "下载你的所有数据副本",
    "exportTitle": "数据导出",
    "exportDesc": "系统将打包你的所有数据，处理完成后可下载",
    "exportStarting": "正在发起导出请求...",
    "exportStatus_pending": "等待处理",
    "exportStatus_processing": "处理中",
    "exportStatus_completed": "已完成",
    "exportStatus_failed": "导出失败",
    "downloadExport": "下载导出文件",
    "retryExport": "重新导出",
    "exportTaskId": "任务 ID",
    "exportFailed": "导出请求失败",
    "downloadFailed": "下载失败",
    "deleteAccount": "注销账号",
    "deleteAccountDesc": "永久删除你的账号和所有数据",
    "deletionDialogTitle": "确认注销账号",
    "deletionWarning": "⚠️ 此操作将永久删除你的账号、比赛记录、分析报告等所有数据，不可恢复。",
    "deletionCoolingHint": "注销将在 72 小时冷静期后执行。冷静期内你可以随时撤销注销请求。",
    "deletionReasonLabel": "注销原因（可选）",
    "deletionReasonPlaceholder": "请告诉我们离开的原因，帮助我们改进...",
    "deletionConfirmHint": "确认命令（请勿修改）：",
    "confirmDelete": "确认注销",
    "deletionRequested": "注销请求已提交，72 小时冷静期已开始",
    "deletionFailed": "注销请求失败",
    "deletionDefaultReason": "用户主动注销",
    "deletionCoolingTitle": "账号注销进行中",
    "deletionCoolingDesc": "你的账号正处于 72 小时冷静期，期满后将永久删除。如需恢复，请点击下方按钮撤销注销。",
    "deletionCountdown": "剩余时间",
    "deletionExecuted": "注销即将执行",
    "cancelDeletion": "撤销注销",
    "deletionCancelled": "注销已撤销，账号恢复正常",
    "deletionCancelFailed": "撤销失败，请稍后重试"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "user": {
    "kqsRating": "KQS Rating",
    "update": "Update",
    "updateRating": "Update Rating",
    "ratingInputPrompt": "Enter new rating (500-3000)",
    "ratingOutOfRange": "Rating must be between 500 and 3000",
    "ratingUpdated": "Rating updated",
    "updateFailed": "Update failed",
    "playingStyle": "Playing Style",
    "selfLevel": "Self Level",
    "kqsUsername": "KQS Username",
    "equipment": "Equipment",
    "blade": "Blade",
    "bladeBrand": "Blade Brand",
    "bladeModel": "Blade Model",
    "rubberFH": "Forehand Rubber",
    "rubberFHBrand": "FH Rubber Brand",
    "rubberFHModel": "FH Rubber Model",
    "rubberBH": "Backhand Rubber",
    "rubberBHBrand": "BH Rubber Brand",
    "rubberBHModel": "BH Rubber Model",
    "brandPlaceholder": "Enter brand",
    "modelPlaceholder": "Enter model",
    "notSet": "Not set",
    "noEquipment": "No equipment added",
    "addEquipment": "Add Equipment",
    "profileCompleteness": "Profile Completeness",
    "completenessHint": "Complete profile for better training advice",
    "bigData": "Big Data",
    "ratingHistory": "Rating History",
    "style_loop": "Loop",
    "style_quick_attack": "Quick Attack",
    "style_chop": "Chop",
    "style_allround": "All-round",
    "level_beginner": "Beginner",
    "level_intermediate": "Intermediate",
    "level_advanced": "Advanced",
    "highestWinRating": "Highest Win",
    "winStreak": "Win Streak",
    "matchCities": "Cities",
    "totalOpponents": "Opponents",
    "totalMatches": "Total Matches",
    "winRate": "Win Rate",
    "indirectWins": "Indirect Wins",
    "indirectWinsDesc": "Calculated from match result chains, for reference only",
    "favoriteShot": "Favorite Shot",
    "ratingChart": "Rating Trend",
    "historyRecords": "History",
    "noRatingHistory": "No rating history yet",
    "sourceManual": "Manual",
    "sourceKqs": "KQS Sync",
    "exportData": "Export My Data",
    "exportDataDesc": "Download a copy of all your data",
    "exportTitle": "Data Export",
    "exportDesc": "The system will package all your data for download",
    "exportStarting": "Starting export request...",
    "exportStatus_pending": "Pending",
    "exportStatus_processing": "Processing",
    "exportStatus_completed": "Completed",
    "exportStatus_failed": "Failed",
    "downloadExport": "Download File",
    "retryExport": "Retry Export",
    "exportTaskId": "Task ID",
    "exportFailed": "Export request failed",
    "downloadFailed": "Download failed",
    "deleteAccount": "Delete Account",
    "deleteAccountDesc": "Permanently delete your account and all data",
    "deletionDialogTitle": "Confirm Account Deletion",
    "deletionWarning": "⚠️ This will permanently delete your account, match records, analysis reports, and all data. This cannot be undone.",
    "deletionCoolingHint": "Deletion will be executed after a 72-hour cooling period. You can cancel the request at any time during this period.",
    "deletionReasonLabel": "Reason (optional)",
    "deletionReasonPlaceholder": "Tell us why you're leaving so we can improve...",
    "deletionConfirmHint": "Confirmation command (do not modify):",
    "confirmDelete": "Confirm Delete",
    "deletionRequested": "Deletion request submitted, 72-hour cooling period started",
    "deletionFailed": "Deletion request failed",
    "deletionDefaultReason": "User initiated deletion",
    "deletionCoolingTitle": "Account Deletion In Progress",
    "deletionCoolingDesc": "Your account is in the 72-hour cooling period. It will be permanently deleted after it expires. To recover, click the button below to cancel.",
    "deletionCountdown": "Time remaining",
    "deletionExecuted": "Deletion imminent",
    "cancelDeletion": "Cancel Deletion",
    "deletionCancelled": "Deletion cancelled, account restored",
    "deletionCancelFailed": "Cancellation failed, please try again later"
  }
}
```

---

## 8. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 个人档案页布局符合设计系统（头部信息 + 完整度 + 档案信息 + 装备 + 快捷入口 + 数据导出 + 注销）
- [ ] 档案完整度进度条颜色为主色 `#E63946`
- [ ] 打法选择 chip 选中时使用主色高亮
- [ ] 乒乓大数据卡片使用 2 列网格布局
- [ ] 积分历史折线图数据点正确分布
- [ ] 空状态正确显示引导文字
- [ ] X-23 注销冷静期横幅红色背景 + 倒计时实时刷新
- [ ] X-23 注销 Dialog 显示警告文案 + 72h 说明 + 原因输入框 + 确认命令
- [ ] X-24 数据导出弹窗底部弹出，圆角，进度条主色
- [ ] X-24 导出状态 Tag 颜色：pending/processing 主色、completed 绿色、failed 红色

### 功能验证
- [ ] 获取档案：进入页面自动加载用户档案
- [ ] 更新积分：弹窗输入 → 校验范围 → 提交 → 刷新档案
- [ ] 编辑档案：选择打法 → 填写装备 → 保存 → 返回刷新
- [ ] 乒乓大数据：进入页面加载（24h 缓存）
- [ ] 积分历史：加载历史记录 → 折线图展示 → 列表展示
- [ ] X-23 注销：点击"注销账号" → 弹出 Dialog → 显示 72h 冷静期说明 → 输入原因 → 确认 → 进入冷静期
- [ ] X-23 冷静期：个人主页底部显示注销倒计时横幅 → 倒计时每秒更新 → 可撤销注销
- [ ] X-23 撤销：点击"撤销注销" → 调用取消 API → 横幅消失 → 恢复注销入口
- [ ] X-24 导出：点击"导出我的数据" → 弹出底部 Popup → 发起导出请求 → 轮询状态
- [ ] X-24 进度：显示 pending/processing/completed/failed 状态 + 进度条
- [ ] X-24 下载：完成后显示下载按钮 → 点击下载文件
- [ ] X-24 失败：失败时显示重试按钮

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **ALL** 积分历史数据按时间正序排列用于折线图渲染
- **X-23** 注销必须经过 72h 冷静期，冷静期内可撤销，**禁止** 立即删除
- **X-23** 注销确认弹窗必须显示警告文案 + 72h 冷静期说明 + 确认命令 `DELETE_ACCOUNT_CONFIRM`
- **X-23** 冷静期倒计时必须实时刷新（每秒），**禁止** 静态显示
- **X-23** 冷静期内个人主页必须显示注销状态横幅，**禁止** 隐藏注销状态
- **X-24** 数据导出必须显示进度状态（pending → processing → completed/failed），**禁止** 无反馈等待
- **X-24** 导出轮询最多 5 次（间隔 3s），**禁止** 无限轮询
- **X-24** 下载链接仅在 completed 状态显示，**禁止** 在 pending/processing 状态显示
- **禁止** 使用 class 组件
- **禁止** 硬编码颜色值，使用 CSS 变量
- **禁止** 安装新的 npm 包
- **禁止** 在前端做积分范围校验逻辑（仅提示，实际校验在后端）
