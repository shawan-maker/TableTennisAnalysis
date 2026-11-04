/**
 * 用户档案状态管理（02-user/frontend.md §3）
 */
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
  status: 'none' | 'pending' | 'cooling' // none: 未发起 / pending: 已发起等待 / cooling: 冷静期内
  scheduled_at: string | null // 注销计划执行时间
  cooling_ends_at: string | null // 冷静期结束时间
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
