/**
 * 认证状态管理（01-auth/frontend.md §3）
 * Token 持久化到 Taro Storage（weapp/H5 跨端）
 */
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import * as authApi from '@/services/auth'

interface AuthUser {
  id: number
  nickname: string
  avatar_url: string | null
  has_profile: boolean
  /** 注册时间（ISO 字符串，onboarding 判定新用户用） */
  created_at?: string
  membership_tier?: string | null
  membership_expire_at?: string | null
  // R20-P1-2: 改名 requires_consent → needs_consent（store 内部统一字段）
  // R21-P1-1: 字段来源极性说明：
  //   - POST /auth/wechat-login / /auth/phone-login 返回 requires_consent: bool（true=需同意）
  //   - GET  /auth/consent-status                返回 consented: bool       （true=已同意）
  //   前端 store 统一字段 needs_consent: bool（true=需同意）。
  //   - wechatLogin/phoneLogin：needs_consent = requires_consent
  //   - checkConsentStatus    ：needs_consent = !consented
  needs_consent?: boolean // R20-P1-2: store 字段 requires_consent→needs_consent
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean

  // Actions
  wechatLogin: (code: string, nickname?: string, avatarUrl?: string) => Promise<void>
  phoneLogin: (phone: string, code: string) => Promise<void>
  refreshAccessToken: () => Promise<boolean>
  fetchMe: () => Promise<void>
  logout: () => Promise<void>
  clearAuth: () => void
  // R19-fix: PIPL 合规 — consent 端点调用（API §2.9 / §2.10）
  recordConsent: (consentType: string, policyVersion: string) => Promise<boolean>
  checkConsentStatus: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: Taro.getStorageSync('access_token') || null,
  refreshToken: Taro.getStorageSync('refresh_token') || null,
  isAuthenticated: !!Taro.getStorageSync('access_token'),
  isLoading: false,

  wechatLogin: async (code, nickname, avatarUrl) => {
    set({ isLoading: true })
    try {
      const res = await authApi.wechatLogin(code, nickname, avatarUrl)
      // R21-P1-1: login 返回 requires_consent（非 consented），极性 true=需同意
      // R20-P1-4: 检查 consented 字段，未同意则跳转同意页（API §2.1 wechat-login 响应）
      const { access_token, refresh_token, user, requires_consent } = res.data.data
      Taro.setStorageSync('access_token', access_token)
      Taro.setStorageSync('refresh_token', refresh_token)
      set({
        accessToken: access_token,
        refreshToken: refresh_token,
        user: { ...user, needs_consent: requires_consent }, // R21-P1-1: needs_consent=requires_consent（极性 true=需同意）
        isAuthenticated: true,
      })
      // R21-P1-1: requires_consent=true 时跳转同意页，不进入首页
      if (requires_consent) {
        Taro.navigateTo({ url: '/pages/auth/consent/index' })
        return
      }
    } finally {
      set({ isLoading: false })
    }
  },

  phoneLogin: async (phone, code) => {
    set({ isLoading: true })
    try {
      const res = await authApi.phoneLogin(phone, code)
      // R21-P1-1: login 返回 requires_consent（非 consented），极性 true=需同意
      // R20-P1-4: 检查 consented 字段，未同意则跳转同意页（API §2.2 phone-login 响应）
      const { access_token, refresh_token, user, requires_consent } = res.data.data
      Taro.setStorageSync('access_token', access_token)
      Taro.setStorageSync('refresh_token', refresh_token)
      set({
        accessToken: access_token,
        refreshToken: refresh_token,
        user: { ...user, needs_consent: requires_consent }, // R21-P1-1: needs_consent=requires_consent（极性 true=需同意）
        isAuthenticated: true,
      })
      // R21-P1-1: requires_consent=true 时跳转同意页，不进入首页
      if (requires_consent) {
        Taro.navigateTo({ url: '/pages/auth/consent/index' })
        return
      }
    } finally {
      set({ isLoading: false })
    }
  },

  refreshAccessToken: async () => {
    const { refreshToken } = get()
    if (!refreshToken) return false
    try {
      const res = await authApi.refreshToken(refreshToken)
      const { access_token, refresh_token } = res.data.data
      Taro.setStorageSync('access_token', access_token)
      Taro.setStorageSync('refresh_token', refresh_token)
      set({ accessToken: access_token, refreshToken: refresh_token })
      return true
    } catch {
      get().clearAuth()
      return false
    }
  },

  fetchMe: async () => {
    const res = await authApi.getMe()
    set({ user: res.data.data })
  },

  logout: async () => {
    try {
      await authApi.logout()
    } finally {
      get().clearAuth()
    }
  },

  clearAuth: () => {
    Taro.removeStorageSync('access_token')
    Taro.removeStorageSync('refresh_token')
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    })
  },

  // R20-P1-2: 隐私政策同意（PIPL 合规，对应 API §2.9 POST /auth/consent）
  // 调用成功后用户 needs_consent 置为 false，并跳转至首页
  recordConsent: async (consentType, policyVersion) => {
    set({ isLoading: true })
    try {
      await authApi.recordConsent(consentType, policyVersion)
      set((state) => ({
        user: state.user ? { ...state.user, needs_consent: false } : state.user, // R20-P1-2: requires_consent→needs_consent
      }))
      return true
    } catch (err: any) {
      Taro.showToast({
        title: err?.message || 'Consent recording failed',
        icon: 'none',
      })
      return false
    } finally {
      set({ isLoading: false })
    }
  },

  // R20-P1-2: 查询隐私政策同意状态，对应 API §2.10 GET /auth/consent-status）
  // 登录后调用以判断是否需要跳转至 pages/auth/consent/index
  // R20-P1-2: API §2.10 返回 consented 字段，needs_consent = !consented
  checkConsentStatus: async () => {
    try {
      const res = await authApi.getConsentStatus()
      const consented = !!res.data?.data?.consented // R20-P1-2: requires_consent→consented（极性反转）
      set((state) => ({
        user: state.user ? { ...state.user, needs_consent: !consented } : state.user, // R20-P1-2: needs_consent = !consented
      }))
    } catch {
      // 查询失败不阻塞主流程，默认 needs_consent 由登录响应提供
    }
  },
}))
