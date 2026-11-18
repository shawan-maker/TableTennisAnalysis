/**
 * onboardingStore 单元测试（14-tab-pages/onboarding.md §2）
 * - 新用户判定双条件（注册 < 24h 或 档案完整度 < 30%）与初始化落位
 * - 进度持久化往返（saveToStorage → initOnboarding 恢复，避免重复引导）
 * - 状态机推进：nextStep 顺序 / goToStep / complete / skip 终态收敛
 * - 存储异常静默（读取损坏 JSON / 空值不抛错）
 *
 * 注：STORAGE_KEY 经 store 内部闭环使用（saveToStorage 预置），
 * 测试不引用键字面量；存储断言走 Taro mock 的调用记录。
 */
import Taro from '@tarojs/taro'
import { __resetStorage } from '../../../test/mocks/taro'
import { useOnboardingStore } from '@/stores/onboardingStore'

const store = useOnboardingStore
/** mock 包装断言（mock 模块实现签名非 jest.Mock 类型面） */
const taroGet = Taro.getStorageSync as unknown as jest.Mock
const taroSet = Taro.setStorageSync as unknown as jest.Mock

const resetStore = () =>
  store.setState({
    isNewUser: false,
    currentStep: 'profile',
    completed: false,
    showHomeTour: false,
    popupVisible: false,
  })

/** 预置 storage（经 store 自身 saveToStorage 闭环，避免引用键字面量） */
const seedStorage = (step: string, completed: boolean) => {
  store.setState({ currentStep: step as any, completed })
  store.getState().saveToStorage()
}

describe('onboardingStore 新用户引导状态机', () => {
  beforeEach(() => {
    resetStore()
    __resetStorage()
    jest.clearAllMocks()
  })

  describe('initOnboarding 新用户判定（双条件）', () => {
    it('注册 2h 内 → 新用户：profile 起步 + 弹窗可见', () => {
      const recent = new Date(Date.now() - 2 * 3600 * 1000).toISOString()
      store.getState().initOnboarding(recent, 100)
      const s = store.getState()
      expect(s.isNewUser).toBe(true)
      expect(s.currentStep).toBe('profile')
      expect(s.completed).toBe(false)
      expect(s.popupVisible).toBe(true)
    })

    it('档案完整度 < 30% → 新用户（注册超 24h 仍判定新）', () => {
      const old = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString()
      store.getState().initOnboarding(old, 10)
      expect(store.getState().isNewUser).toBe(true)
      expect(store.getState().popupVisible).toBe(true)
    })

    it('注册超 24h 且完整度 ≥ 30% → 老用户：直接 completed 不打扰', () => {
      const old = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString()
      store.getState().initOnboarding(old, 100)
      const s = store.getState()
      expect(s.isNewUser).toBe(false)
      expect(s.currentStep).toBe('completed')
      expect(s.completed).toBe(true)
      expect(s.popupVisible).toBe(false)
    })

    it('storage 已 completed → 无论注册时间均不重复引导（持久化往返闭环）', () => {
      seedStorage('completed', true)
      resetStore()
      const recent = new Date(Date.now() - 2 * 3600 * 1000).toISOString()
      store.getState().initOnboarding(recent, 0)
      const s = store.getState()
      expect(s.completed).toBe(true)
      expect(s.isNewUser).toBe(false)
      expect(s.currentStep).toBe('completed')
    })

    it('storage 中途进度 + 仍属新用户 → 恢复步骤且弹窗可见', () => {
      seedStorage('first_match', false)
      resetStore()
      const recent = new Date(Date.now() - 5 * 3600 * 1000).toISOString()
      store.getState().initOnboarding(recent, 100)
      const s = store.getState()
      expect(s.currentStep).toBe('first_match')
      expect(s.isNewUser).toBe(true)
      expect(s.popupVisible).toBe(true)
    })
  })

  describe('状态机推进与持久化', () => {
    it('nextStep 顺序推进：profile → home_tour，并持久化当前步', () => {
      store.getState().nextStep()
      expect(store.getState().currentStep).toBe('home_tour')
      const saved = taroSet.mock.calls.at(-1)?.[1]
      expect(saved).toBe(JSON.stringify({ step: 'home_tour', completed: false }))
    })

    it('nextStep 直至 completed → 终态收敛（completed/isNewUser/popupVisible 三清）', () => {
      store.setState({ currentStep: 'view_advice' })
      store.getState().nextStep()
      const s = store.getState()
      expect(s.currentStep).toBe('completed')
      expect(s.completed).toBe(true)
      expect(s.isNewUser).toBe(false)
      expect(s.popupVisible).toBe(false)
    })

    it('nextStep 于终态 → 幂等保持 completed', () => {
      store.setState({ currentStep: 'completed', completed: true })
      store.getState().nextStep()
      expect(store.getState().currentStep).toBe('completed')
      expect(store.getState().completed).toBe(true)
    })

    it('goToStep 指定步 + 持久化', () => {
      store.getState().goToStep('first_upload')
      expect(store.getState().currentStep).toBe('first_upload')
      const saved = taroSet.mock.calls.at(-1)?.[1]
      expect(saved).toBe(JSON.stringify({ step: 'first_upload', completed: false }))
    })

    it('complete/skip → 同收敛终态（含 showHomeTour 清除），round-trip 后不再打扰', () => {
      store.setState({ showHomeTour: true })
      store.getState().complete()
      expect(store.getState().completed).toBe(true)
      expect(store.getState().showHomeTour).toBe(false)

      resetStore()
      store.setState({ showHomeTour: true })
      store.getState().skip()
      expect(store.getState().completed).toBe(true)
      expect(store.getState().showHomeTour).toBe(false)

      // 持久化往返：重初始化不再引导
      resetStore()
      store.getState().initOnboarding(new Date().toISOString(), 0)
      expect(store.getState().completed).toBe(true)
    })

    it('loadFromStorage 恢复中途进度；无存储 → 状态保持', () => {
      seedStorage('home_tour', false)
      resetStore()
      store.getState().loadFromStorage()
      expect(store.getState().currentStep).toBe('home_tour')
      expect(store.getState().isNewUser).toBe(true)

      resetStore()
      __resetStorage()
      store.getState().loadFromStorage()
      expect(store.getState().currentStep).toBe('profile')
      expect(store.getState().completed).toBe(false)
    })
  })

  describe('存储异常静默（跨端 storage 不可用防御）', () => {
    it('读取到损坏 JSON → 按无存储处理，不抛错', () => {
      taroGet.mockReturnValueOnce('garbage{not-json')
      expect(() => store.getState().initOnboarding(new Date().toISOString(), 100)).not.toThrow()
      expect(store.getState().isNewUser).toBe(true)
    })

    it('getStorageSync 抛错 → 静默，初始化正常进行', () => {
      taroGet.mockImplementationOnce(() => {
        throw new Error('storage unavailable')
      })
      expect(() => store.getState().initOnboarding(new Date().toISOString(), 100)).not.toThrow()
      expect(store.getState().isNewUser).toBe(true)
    })

    it('setStorageSync 抛错 → nextStep 不受阻断（进度态照常推进）', () => {
      taroSet.mockImplementationOnce(() => {
        throw new Error('quota exceeded')
      })
      expect(() => store.getState().nextStep()).not.toThrow()
      expect(store.getState().currentStep).toBe('home_tour')
    })
  })
})
