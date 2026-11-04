/**
 * H5 降级中转页（01-auth/frontend.md §9）
 *
 * 用途：微信小程序内打开 H5 页面时的认证中转（小程序生成 H5 Token 跳转 H5；
 * H5 页面携带 token 回跳时换取 JWT）。
 *
 * 注意：本页不在 app.config.ts 注册（H5 端条件页，总览 §3.4 注册表维持 39 页口径）；
 * 构建脚本未引用时不会进入产物。
 */
import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { generateH5Token, exchangeH5Token } from '@/services/auth'
import { useTranslation } from 'react-i18next'

export default function H5Bridge() {
  const { t } = useTranslation()
  const router = useRouter()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    const { token } = router.params
    if (token) {
      // H5 页面 → 用 token 换 JWT
      handleH5Exchange(token)
    } else {
      // 小程序 → 生成 H5 Token 并跳转
      handleH5Redirect()
    }
  }, [])

  const handleH5Exchange = async (token: string) => {
    try {
      const res = await exchangeH5Token(token)
      Taro.setStorageSync('access_token', res.data.data.access_token)
      Taro.setStorageSync('refresh_token', res.data.data.refresh_token)
      setStatus('success')
      // 延迟跳转首页
      setTimeout(() => Taro.switchTab({ url: '/pages/home/index' }), 1000)
    } catch (err: any) {
      setStatus('error')
      setErrorMsg(err?.message || t('auth.h5TokenExpired'))
    }
  }

  const handleH5Redirect = async () => {
    try {
      const res = await generateH5Token()
      const h5Token = res.data.data.token
      const targetUrl = router.params.target || '/pages/home/index'
      // 跳转到 H5 页面，携带 token
      Taro.navigateTo({
        url: `${targetUrl}?h5_token=${h5Token}`,
      })
    } catch {
      setStatus('error')
    }
  }

  return (
    <View className="h5-bridge">
      {status === 'loading' && <Skeleton rows={3} animated />}
      {status === 'success' && <Text>{t('auth.loginSuccess')}</Text>}
      {status === 'error' && <Text>{errorMsg || t('auth.loginFailed')}</Text>}
    </View>
  )
}
