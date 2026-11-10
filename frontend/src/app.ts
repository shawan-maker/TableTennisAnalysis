import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import '@nutui/nutui-react-taro/dist/style.css'
import { initI18n } from './locales'
import { useAuthStore } from './stores/authStore'
import { setupA11yH5Patches } from './utils/a11y-h5'
import './styles/app.scss'

// i18n 在模块加载阶段同步初始化（页面渲染前就绪，幂等）
initI18n()

function App({ children }: PropsWithChildren<any>) {
  useLaunch(() => {
    // FS8-P1-3（a11y 扫描抓获）：H5 整页重载/深链场景 user 丢失——
    // token 持久化于 Storage 但 user 仅由登录响应写入（fetchMe 从未被调用），
    // 导致依赖 authStore.user 的链路（onboarding 新用户检测、TopBar 用户
    // 信息）刷新后失效。启动时 token 有效态静默恢复用户身份（失败不阻塞，
    // 401 由 request 拦截器统一跳登录）。
    const { isAuthenticated, user, fetchMe } = useAuthStore.getState()
    if (isAuthenticated && !user) {
      fetchMe().catch(() => {})
    }
    // FS8-7 axe：H5 滚动容器（.taro_page/.filter-bar）动态补 tabindex
    setupA11yH5Patches()
  })

  // children 是将要会渲染的页面
  return children
}

export default App
