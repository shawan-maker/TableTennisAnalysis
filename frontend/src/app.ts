import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import '@nutui/nutui-react-taro/dist/style.css'
import { initI18n } from './locales'
import './styles/app.scss'

// i18n 在模块加载阶段同步初始化（页面渲染前就绪，幂等）
initI18n()

function App({ children }: PropsWithChildren<any>) {
  useLaunch(() => {
    console.log('App launched.')
  })

  // children 是将要会渲染的页面
  return children
}

export default App
