/**
 * match_data 状态管理（05-match_data/frontend.md §3）
 * 列表分页（append 模式）+ 详情 + 创建（快速/详细录入统一入口）
 */
import { create } from 'zustand'
import * as matchDataApi from '@/services/matchData'
import type { MatchRecordListItem, MatchRecordDetailItem } from '@/services/matchData'

/** 创建结果（镜像后端 MatchRecordCreateResponse） */
export interface CreateRecordResult {
  id: number
  is_win: boolean
  match_id?: number | null
}

interface MatchDataState {
  // 列表
  records: MatchRecordListItem[]
  total: number
  page: number
  isLoading: boolean

  // 详情
  currentDetail: MatchRecordDetailItem | null

  // Actions
  fetchRecords: (result?: string, page?: number) => Promise<void>
  fetchDetail: (id: number) => Promise<void>
  createRecord: (params: matchDataApi.MatchRecordCreateParams) => Promise<CreateRecordResult>
  clearDetail: () => void
  /** 重置列表（离开列表页时清空旧数据） */
  resetList: () => void
}

export const useMatchDataStore = create<MatchDataState>((set, get) => ({
  records: [],
  total: 0,
  page: 1,
  isLoading: false,
  currentDetail: null,

  fetchRecords: async (result = 'all', page = 1) => {
    set({ isLoading: true })
    try {
      const res = await matchDataApi.listRecords(result, page)
      const data = res.data.data
      if (page === 1) {
        set({ records: data.items })
      } else {
        set({ records: [...get().records, ...data.items] })
      }
      set({ total: data.total, page })
    } finally {
      set({ isLoading: false })
    }
  },

  fetchDetail: async (id) => {
    set({ isLoading: true })
    try {
      const res = await matchDataApi.getRecord(id)
      set({ currentDetail: res.data.data })
    } finally {
      set({ isLoading: false })
    }
  },

  createRecord: async (params) => {
    set({ isLoading: true })
    try {
      const res = await matchDataApi.createRecord(params)
      return res.data.data
    } finally {
      set({ isLoading: false })
    }
  },

  clearDetail: () => set({ currentDetail: null }),

  resetList: () => set({ records: [], total: 0, page: 1 }),
}))
