/**
 * @tarojs/taro 手动 mock（jest node 环境，moduleNameMapper 映射）
 * - Storage：内存实现（跨端 getStorageSync 返回 '' 约定与 Taro 一致）
 * - 导航/toast：jest.fn() 记录调用
 */
const storage: Record<string, any> = {}

const Taro = {
  getStorageSync: jest.fn((key: string) => (key in storage ? storage[key] : '')),
  setStorageSync: jest.fn((key: string, val: any) => {
    storage[key] = val
  }),
  removeStorageSync: jest.fn((key: string) => {
    delete storage[key]
  }),
  navigateTo: jest.fn(),
  redirectTo: jest.fn(),
  navigateBack: jest.fn(),
  reLaunch: jest.fn(),
  showToast: jest.fn(),
  showModal: jest.fn(),
  getSystemInfoSync: jest.fn(() => ({ language: 'zh_CN' })),
  connectSocket: jest.fn(() => Promise.resolve({ close: jest.fn(), send: jest.fn() })),
  // FS6: JSAPI 支付 / tabBar 角标 / 下拉刷新（Taro API 均返回 Promise）
  requestPayment: jest.fn(() => Promise.resolve({})),
  setTabBarBadge: jest.fn(() => Promise.resolve({})),
  removeTabBarBadge: jest.fn(() => Promise.resolve({})),
  stopPullDownRefresh: jest.fn(() => Promise.resolve({})),
  usePullDownRefresh: jest.fn(),
  useReachBottom: jest.fn(),
  request: jest.fn(),
}

export default Taro

/** 重置内存 Storage（beforeEach 使用） */
export function __resetStorage() {
  Object.keys(storage).forEach((k) => delete storage[k])
}

export const getStorageSync = Taro.getStorageSync
export const setStorageSync = Taro.setStorageSync
export const removeStorageSync = Taro.removeStorageSync
export const navigateTo = Taro.navigateTo
export const redirectTo = Taro.redirectTo
export const navigateBack = Taro.navigateBack
export const reLaunch = Taro.reLaunch
export const showToast = Taro.showToast
export const getSystemInfoSync = Taro.getSystemInfoSync
export const connectSocket = Taro.connectSocket
export const request = Taro.request
