/**
 * matchTab 模块状态管理（14-tab-pages/match-tab.md §3）
 * 赛事 Tab 入口页预览：最近比赛记录 + 进行中记分牌，并发加载；
 * 单个失败静默显示空状态（反幻觉约束：不阻塞另一预览）。
 */
import { create } from 'zustand'
import * as matchTabApi from '@/services/matchTab'
import type { LatestMatchPreview, CurrentScoringPreview } from '@/services/matchTab'

interface MatchTabState {
  latestMatch: LatestMatchPreview | null
  latestMatchLoading: boolean

  currentScoring: CurrentScoringPreview | null
  currentScoringLoading: boolean

  fetchLatestMatch: () => Promise<void>
  fetchCurrentScoring: () => Promise<void>
  refreshAll: () => Promise<void>
}

export const useMatchTabStore = create<MatchTabState>((set) => ({
  latestMatch: null,
  latestMatchLoading: false,
  currentScoring: null,
  currentScoringLoading: false,

  fetchLatestMatch: async () => {
    set({ latestMatchLoading: true })
    try {
      const res = await matchTabApi.getLatestMatch()
      const items: LatestMatchPreview[] = res.data.data.items || []
      set({ latestMatch: items.length > 0 ? items[0] : null })
    } catch {
      set({ latestMatch: null })
    } finally {
      set({ latestMatchLoading: false })
    }
  },

  fetchCurrentScoring: async () => {
    set({ currentScoringLoading: true })
    try {
      const res = await matchTabApi.getCurrentScoring()
      const items: CurrentScoringPreview[] = res.data.data.items || []
      // FS7-P3：无 /scoring/current 端点，取 in_progress 列表第一条
      set({ currentScoring: items.length > 0 ? items[0] : null })
    } catch {
      set({ currentScoring: null })
    } finally {
      set({ currentScoringLoading: false })
    }
  },

  refreshAll: async () => {
    await Promise.all([
      useMatchTabStore.getState().fetchLatestMatch(),
      useMatchTabStore.getState().fetchCurrentScoring(),
    ])
  },
}))
