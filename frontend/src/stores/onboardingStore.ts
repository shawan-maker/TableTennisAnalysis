/**
 * 新用户引导状态管理（14-tab-pages/onboarding.md §2）
 * 引导进度持久化到 Taro Storage（H5 端底层 localStorage，小程序端原生存储），
 * 避免用户中途退出后重复引导。
 */
import { create } from 'zustand'
import Taro from '@tarojs/taro'

/** 引导步骤 */
export type OnboardingStep =
  | 'profile' // Step 1: 填写档案
  | 'home_tour' // Step 2: 首页引导
  | 'first_match' // Step 3: 录入第一场比赛
  | 'first_upload' // Step 4: 上传第一个视频
  | 'view_advice' // Step 5: 查看训练建议
  | 'completed' // 已完成

/** 引导步骤顺序 */
const STEP_ORDER: OnboardingStep[] = [
  'profile',
  'home_tour',
  'first_match',
  'first_upload',
  'view_advice',
  'completed',
]

const STORAGE_KEY = 'onboarding_progress'

interface OnboardingState {
  /** 是否为新用户（需要引导） */
  isNewUser: boolean
  /** 当前步骤 */
  currentStep: OnboardingStep
  /** 是否已完成引导 */
  completed: boolean
  /** 是否显示首页引导遮罩 */
  showHomeTour: boolean
  /** Steps 弹窗是否可见 */
  popupVisible: boolean

  /** 初始化：检查新用户状态 */
  initOnboarding: (createdAt: string, profileCompleteness: number) => void
  /** 从 storage 恢复进度 */
  loadFromStorage: () => void
  /** 保存进度到 storage */
  saveToStorage: () => void
  /** 进入下一步 */
  nextStep: () => void
  /** 跳到指定步骤 */
  goToStep: (step: OnboardingStep) => void
  /** 完成引导 */
  complete: () => void
  /** 跳过引导 */
  skip: () => void
  /** 打开/关闭 Steps 弹窗 */
  setPopupVisible: (visible: boolean) => void
  /** 显示/隐藏首页引导遮罩 */
  setShowHomeTour: (show: boolean) => void
}

function saveStorage(step: OnboardingStep, completed: boolean) {
  try {
    Taro.setStorageSync(STORAGE_KEY, JSON.stringify({ step, completed }))
  } catch {
    // 存储不可用时静默失败
  }
}

function loadStorage(): { step: OnboardingStep; completed: boolean } | null {
  try {
    const raw = Taro.getStorageSync(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    // 读取失败静默处理
  }
  return null
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  isNewUser: false,
  currentStep: 'profile',
  completed: false,
  showHomeTour: false,
  popupVisible: false,

  initOnboarding: (createdAt: string, profileCompleteness: number) => {
    // 先从 storage 恢复
    const stored = loadStorage()
    if (stored?.completed) {
      set({ completed: true, isNewUser: false, currentStep: 'completed' })
      return
    }

    // 判断是否新用户：注册时间 < 24h 或 profile 完整度 < 30%
    const created = new Date(createdAt)
    const now = new Date()
    const hoursSinceCreated = (now.getTime() - created.getTime()) / (1000 * 60 * 60)
    const isNew = hoursSinceCreated < 24 || profileCompleteness < 30

    if (stored) {
      set({
        isNewUser: true,
        currentStep: stored.step,
        popupVisible: isNew,
      })
    } else {
      set({
        isNewUser: isNew,
        currentStep: isNew ? 'profile' : 'completed',
        completed: !isNew,
        popupVisible: isNew,
      })
    }
  },

  loadFromStorage: () => {
    const stored = loadStorage()
    if (stored) {
      set({
        currentStep: stored.step,
        completed: stored.completed,
        isNewUser: !stored.completed,
      })
    }
  },

  saveToStorage: () => {
    const { currentStep, completed } = get()
    saveStorage(currentStep, completed)
  },

  nextStep: () => {
    const { currentStep } = get()
    const idx = STEP_ORDER.indexOf(currentStep)
    const next = idx >= 0 && idx < STEP_ORDER.length - 1
      ? STEP_ORDER[idx + 1]
      : 'completed'
    set({ currentStep: next })
    get().saveToStorage()
    if (next === 'completed') {
      set({ completed: true, isNewUser: false, popupVisible: false })
    }
  },

  goToStep: (step: OnboardingStep) => {
    set({ currentStep: step })
    get().saveToStorage()
  },

  complete: () => {
    set({
      currentStep: 'completed',
      completed: true,
      isNewUser: false,
      popupVisible: false,
      showHomeTour: false,
    })
    get().saveToStorage()
  },

  skip: () => {
    set({
      currentStep: 'completed',
      completed: true,
      isNewUser: false,
      popupVisible: false,
      showHomeTour: false,
    })
    get().saveToStorage()
  },

  setPopupVisible: (visible: boolean) => set({ popupVisible: visible }),
  setShowHomeTour: (show: boolean) => set({ showHomeTour: show }),
}))
