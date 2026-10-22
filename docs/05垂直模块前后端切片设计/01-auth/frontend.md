# auth 模块 — 前端垂直切片设计

> **模块名称**：`auth`
> **前端目录**：`frontend/src/pages/auth/` + `frontend/src/services/auth.ts` + `frontend/src/stores/authStore.ts`
> **定位**：微信登录/手机号登录、Token 管理、H5 降级认证
> **依据**：前端需求与界面设计 v2.0、API 详细设计 v1.3 §2

---

## 1. 切片准备清单

- [ ] 阅读前端设计 v2.0 §2.2 L1（我的 Tab → 个人主页 → 登录引导）
- [ ] 阅读本模块的 API 契约（§2.1-2.10，10 个端点，含 §2.9 consent 与 §2.10 consent-status）
- [ ] 阅读设计系统规范（§1.1-1.4，色彩/字体/间距/组件）
- [ ] 确认本切片范围：登录页 + Token 管理 Service + authStore

---

## 2. API Service 模块

```typescript
// frontend/src/services/auth.ts
import request from './request'

/**
 * 微信小程序登录。
 * @param code - wx.login() 返回的 code
 * @param nickname - 用户昵称（首次登录时）
 * @param avatarUrl - 用户头像 URL
 */
export function wechatLogin(code: string, nickname?: string, avatarUrl?: string) {
  return request.post('/auth/wechat-login', { code, nickname, avatar_url: avatarUrl })
}

/**
 * 手机号验证码登录。
 */
export function phoneLogin(phone: string, code: string) {
  return request.post('/auth/phone-login', { phone, code })
}

/**
 * 发送短信验证码。
 */
export function sendSms(phone: string) {
  return request.post('/auth/send-sms', { phone })
}

/**
 * 刷新 access_token。
 */
export function refreshToken(refreshToken: string) {
  return request.post('/auth/refresh', { refresh_token: refreshToken })
}

/**
 * 登出。
 */
export function logout() {
  return request.post('/auth/logout')
}

/**
 * 获取当前登录用户信息。
 */
export function getMe() {
  return request.get('/auth/me')
}

/**
 * 生成 H5 降级临时 Token。
 */
export function generateH5Token() {
  return request.post('/auth/h5-token')
}

/**
 * H5 Token 换 JWT。
 */
export function exchangeH5Token(token: string) {
  return request.post('/auth/h5-exchange', { token })
}

/**
 * 隐私政策同意（PIPL 合规）。
 * 对应 API §2.9 POST /auth/consent。
 * @param consentType - 同意类型枚举（如 'privacy_policy' / 'user_agreement'）
 * @param policyVersion - 所同意的隐私政策版本号（如 'v1.0'）
 */
export function recordConsent(consentType: string, policyVersion: string) {
  return request.post('/auth/consent', {
    consent_type: consentType,
    policy_version: policyVersion,
  })
}

/**
 * 查询当前用户隐私政策同意状态。
 * 对应 API §2.10 GET /auth/consent-status。
 * 用于登录后判断是否需要弹出隐私政策同意页（consented=false 时）。
 * // R20-P1-2: API §2.10 返回 consented 字段，needs_consent = !consented
 * // R21-P1-1: 注意此端点返回 consented（true=已同意），与 login 端点返回的 requires_consent（true=需同意）极性相反
 */
export function getConsentStatus() {
  return request.get('/auth/consent-status')
}
```

---

## 3. 状态管理（Zustand Store）

```typescript
// frontend/src/stores/authStore.ts
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import * as authApi from '@/services/auth'

interface AuthUser {
  id: number
  nickname: string
  avatar_url: string | null
  has_profile: boolean
  membership_tier?: string | null
  membership_expire_at?: string | null
  // R20-P1-2: 改名 requires_consent → needs_consent（store 内部统一字段）
  // R21-P1-1: 字段来源极性说明：
  //   - POST /auth/wechat-login / /auth/phone-login 返回 requires_consent: bool（true=需同意）
  //   - GET  /auth/consent-status                返回 consented: bool       （true=已同意）
  //   前端 store 统一字段 needs_consent: bool（true=需同意）。
  //   - wechatLogin/phoneLogin：needs_consent = requires_consent
  //   - checkConsentStatus    ：needs_consent = !consented
  needs_consent?: boolean  // R20-P1-2: store 字段 requires_consent→needs_consent
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
        user: { ...user, needs_consent: requires_consent },  // R21-P1-1: needs_consent=requires_consent（极性 true=需同意）
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
        user: { ...user, needs_consent: requires_consent },  // R21-P1-1: needs_consent=requires_consent（极性 true=需同意）
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
        user: state.user ? { ...state.user, needs_consent: false } : state.user,  // R20-P1-2: requires_consent→needs_consent
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
      const consented = !!res.data?.data?.consented  // R20-P1-2: requires_consent→consented（极性反转）
      set((state) => ({
        user: state.user ? { ...state.user, needs_consent: !consented } : state.user,  // R20-P1-2: needs_consent = !consented
      }))
    } catch {
      // 查询失败不阻塞主流程，默认 needs_consent 由登录响应提供
    }
  },
}))
```

---

## 4. 登录页面

```tsx
// frontend/src/pages/auth/login.tsx
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Toast, Input, Button } from '@nutui/nutui-react'
import { useAuthStore } from '@/stores/authStore'
import { sendSms } from '@/services/auth'
import { useTranslation } from 'react-i18next'
import './login.scss'

export default function Login() {
  const { t } = useTranslation()
  const { wechatLogin, phoneLogin, isLoading } = useAuthStore()
  const [phone, setPhone] = useState('')
  const [smsCode, setSmsCode] = useState('')
  const [countdown, setCountdown] = useState(0)
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setToastVisible(true)
  }

  /** 微信登录 */
  const handleWechatLogin = useCallback(async () => {
    try {
      const { code } = await Taro.login()
      await wechatLogin(code)
      Taro.switchTab({ url: '/pages/home/index' })
    } catch (err: any) {
      showToast(err?.message || t('auth.loginFailed'))
    }
  }, [wechatLogin, t])

  /** 发送验证码 */
  const handleSendSms = useCallback(async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      showToast(t('auth.invalidPhone'))
      return
    }
    if (countdown > 0) return
    try {
      await sendSms(phone)
      showToast(t('auth.smsSent'))
      setCountdown(60)
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer)
            return 0
          }
          return prev - 1
        })
      }, 1000)
    } catch (err: any) {
      showToast(err?.message || t('auth.smsSendFailed'))
    }
  }, [phone, countdown, t])

  /** 手机号登录 */
  const handlePhoneLogin = useCallback(async () => {
    if (!phone || !smsCode) {
      showToast(t('auth.fillAllFields'))
      return
    }
    try {
      await phoneLogin(phone, smsCode)
      Taro.switchTab({ url: '/pages/home/index' })
    } catch (err: any) {
      showToast(err?.message || t('auth.loginFailed'))
    }
  }, [phone, smsCode, phoneLogin, t])

  return (
    <View className="login-page">
      {/* Logo 区域 */}
      <View className="login-header">
        <Text className="login-title">{t('app.name')}</Text>
        <Text className="login-subtitle">{t('app.slogan')}</Text>
      </View>

      {/* 微信登录按钮 */}
      <View className="login-wechat">
        <Button
          type="primary"
          block
          loading={isLoading}
          onClick={handleWechatLogin}
          className="btn-wechat"
        >
          {t('auth.wechatLogin')}
        </Button>
      </View>

      {/* 分割线 */}
      <View className="login-divider">
        <View className="divider-line" />
        <Text className="divider-text">{t('auth.orPhoneLogin')}</Text>
        <View className="divider-line" />
      </View>

      {/* 手机号登录 */}
      <View className="login-phone">
        <Cell>
          <Input
            type="number"
            maxlength={11}
            placeholder={t('auth.phonePlaceholder')}
            value={phone}
            onChange={(val) => setPhone(val)}
          />
        </Cell>
        <Cell>
          <View className="sms-row">
            <Input
              type="number"
              maxlength={6}
              placeholder={t('auth.codePlaceholder')}
              value={smsCode}
              onChange={(val) => setSmsCode(val)}
            />
            <Button
              size="small"
              disabled={countdown > 0}
              onClick={handleSendSms}
            >
              {countdown > 0 ? `${countdown}s` : t('auth.sendCode')}
            </Button>
          </View>
        </Cell>
        <Button
          type="primary"
          block
          loading={isLoading}
          onClick={handlePhoneLogin}
          className="btn-phone"
        >
          {t('auth.login')}
        </Button>
      </View>

      {/* 协议 */}
      <View className="login-agreement">
        <Text className="agreement-text">{t('auth.agreementPrefix')}</Text>
        <Text className="agreement-link">{t('auth.userAgreement')}</Text>
        <Text className="agreement-text">{t('auth.and')}</Text>
        <Text className="agreement-link">{t('auth.privacyPolicy')}</Text>
      </View>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

---

## 5. 样式

```scss
// frontend/src/pages/auth/login.scss
.login-page {
  min-height: 100vh;
  padding: 0 var(--spacing-xl);
  background: var(--color-background);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.login-header {
  margin-top: var(--spacing-2xl); /* P3-fix: 120px→48px (--spacing-2xl) */
  text-align: center;

  .login-title {
    display: block;
    font-size: 32px;
    font-weight: bold;
    color: var(--color-primary);
  }

  .login-subtitle {
    display: block;
    margin-top: var(--spacing-sm);
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.login-wechat {
  margin-top: var(--spacing-2xl);
  width: 100%;

  .btn-wechat {
    background: var(--color-success);
    color: var(--color-text-inverse);
    border-radius: var(--radius-sm);
    height: 48px;
    font-size: 15px;
  }
}

.login-divider {
  display: flex;
  align-items: center;
  margin: var(--spacing-xl) 0;
  width: 100%;

  .divider-line {
    flex: 1;
    height: 1px;
    background: var(--color-divider);
  }

  .divider-text {
    padding: 0 var(--spacing-md);
    font-size: 13px;
    color: var(--color-text-secondary);
  }
}

.login-phone {
  width: 100%;

  .sms-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm-md);
  }

  .btn-phone {
    margin-top: var(--spacing-lg);
    background: var(--color-primary);
    color: var(--color-text-inverse);
    border-radius: var(--radius-sm);
    height: 48px;
    font-size: 15px;
  }
}

.login-agreement {
  margin-top: auto;
  margin-bottom: var(--spacing-2xl);
  text-align: center;
  font-size: 12px;

  .agreement-text {
    color: var(--color-text-secondary);
  }

  .agreement-link {
    color: var(--color-primary);
  }
}
```

---

## 6. 路由配置

```typescript
// frontend/src/app.config.ts（新增 auth 页面）
export default {
  pages: [
    'pages/home/index',
    'pages/auth/login/index',     // 新增
    'pages/auth/h5-bridge/index', // 新增：H5 降级中转页
    'pages/auth/consent/index',   // R20-P1-3: 新增：隐私政策同意页（PIPL 合规＜br>
                                   // R20-P1-3: 需 requires_consent=true 时由 wechatLogin/phoneLogin/checkConsentStatus 跳转至此页
    // ... 其他页面
  ],
  // TabBar 配置以总览 §3.4 app.config.ts 为准，此处不重复定义
}
```

---

## 7. 常量与 i18n

### i18n 条目

```json
// frontend/src/locales/zh-CN.json（新增）
{
  "auth": {
    "wechatLogin": "微信一键登录",
    "orPhoneLogin": "或手机号登录",
    "phonePlaceholder": "请输入手机号",
    "codePlaceholder": "请输入验证码",
    "sendCode": "发送验证码",
    "login": "登录",
    "loginFailed": "登录失败，请重试",
    "invalidPhone": "请输入正确的手机号",
    "smsSent": "验证码已发送",
    "smsSendFailed": "验证码发送失败",
    "fillAllFields": "请填写手机号和验证码",
    "agreementPrefix": "登录即表示同意",
    "userAgreement": "《用户协议》",
    "and": "和",
    "privacyPolicy": "《隐私政策》"
  }
}
```

```json
// frontend/src/locales/en-US.json（新增）
{
  "auth": {
    "wechatLogin": "Login with WeChat",
    "orPhoneLogin": "or phone login",
    "phonePlaceholder": "Enter phone number",
    "codePlaceholder": "Enter verification code",
    "sendCode": "Send Code",
    "login": "Login",
    "loginFailed": "Login failed, please try again",
    "invalidPhone": "Please enter a valid phone number",
    "smsSent": "Verification code sent",
    "smsSendFailed": "Failed to send verification code",
    "fillAllFields": "Please fill in phone and code",
    "agreementPrefix": "By logging in you agree to the",
    "userAgreement": "Terms of Service",
    "and": "and",
    "privacyPolicy": "Privacy Policy"
  }
}
```

---

## 8. request 拦截器（Token 自动刷新）

```typescript
// frontend/src/services/request.ts（核心部分）
import Taro from '@tarojs/taro'
import { useAuthStore } from '@/stores/authStore'

const BASE_URL = process.env.TARO_APP_API || 'https://api.pingpongai.com/api/v1'

let isRefreshing = false
let pendingRequests: Array<() => void> = []

async function refreshAndRetry(): Promise<boolean> {
  if (isRefreshing) {
    return new Promise((resolve) => {
      pendingRequests.push(() => resolve(true))
    })
  }
  isRefreshing = true
  const success = await useAuthStore.getState().refreshAccessToken()
  isRefreshing = false
  if (success) {
    pendingRequests.forEach((fn) => fn())
    pendingRequests = []
  }
  return success
}

const request = {
  async get(url: string, params?: Record<string, any>) {
    return this._request('GET', url, null, params)
  },

  async post(url: string, data?: any) {
    return this._request('POST', url, data)
  },

  async patch(url: string, data?: any) {
    return this._request('PATCH', url, data)
  },

  async delete(url: string) {
    return this._request('DELETE', url)
  },

  async _request(method: string, url: string, data?: any, params?: any) {
    const token = Taro.getStorageSync('access_token')
    const header: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (token) {
      header['Authorization'] = `Bearer ${token}`
    }

    const res = await Taro.request({
      url: `${BASE_URL}${url}`,
      method: method as any,
      data: method === 'GET' ? params : data,
      header,
    })

    // Token 过期 → 自动刷新
    if (res.statusCode === 401 && res.data?.code === 40101) {
      const refreshed = await refreshAndRetry()
      if (refreshed) {
        return this._request(method, url, data, params) // 重试
      }
      // 刷新失败 → 跳转登录
      Taro.reLaunch({ url: '/pages/auth/login/index' })
      throw new Error('Login expired')
    }

    // 权限不足
    if (res.statusCode === 403) {
      throw new Error(res.data?.message || 'Permission denied')
    }

    if (res.statusCode >= 400) {
      throw new Error(res.data?.message || 'Request failed')
    }

    return res
  },
}

export default request
```

---

## 9. H5 降级中转页

```tsx
// frontend/src/pages/auth/h5-bridge.tsx
import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Skeleton } from '@nutui/nutui-react'
import { useAuthStore } from '@/stores/authStore'
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
```

---
## 9.1 隐私政策同意页（R20-P1-3：PIPL 合规）

> **触发条件**：当 `wechatLogin` / `phoneLogin` 成功后检测到 `requires_consent=true`（API §2.1/§2.2），或 `checkConsentStatus` 返回 `consented=false`（API §2.10）时，跳转至此页引导用户完成同意流程。R21-P1-1：两字段极性相反但各自正确（login=requires_consent，consent-status=consented）。

```tsx
// frontend/src/pages/auth/consent/index.tsx
// R20-P1-3: consent 同意页（新增）
import { useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { Button, Toast } from '@nutui/nutui-react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/stores/authStore'
import './index.scss'

// R20-P1-3: 隐私政策版本号
const PRIVACY_POLICY_VERSION = 'v1.0'

// R20-P1-3: 隐私政策文本内容（实际项目中可从 i18n 加载）
function PrivacyPolicyContent() {
  const { t } = useTranslation()
  return (
    <View className="policy-content">
      <Text className="policy-title">{t('auth.privacyPolicyTitle')}</Text>
      <Text className="policy-text">{t('auth.privacyPolicyBody')}</Text>
      {/* R20-P1-3: 实际项目应在此包含完整隐私政策文本（包括信息收集/使用/共享/存储/用户权利等） */}
    </View>
  )
}

// R20-P1-3: consent 同意页主组件
export default function ConsentPage() {
  const { t } = useTranslation()
  const { recordConsent, isLoading } = useAuthStore()
  const [toastVisible, setToastVisible] = useState(false)
  const [toastMsg, setToastMsg] = useState('')

  // R20-P1-3: 同意并继续：调用 recordConsent 记录同意，成功后跳转首页
  const handleAgree = async () => {
    const success = await recordConsent('privacy_policy', PRIVACY_POLICY_VERSION)
    if (success) {
      Taro.switchTab({ url: '/pages/home/index' })
    } else {
      setToastMsg(t('auth.consentFailed'))
      setToastVisible(true)
    }
  }

  // R20-P1-3: 拒绝：不同意则不能使用系统，给出提示
  const handleRefuse = () => {
    Taro.showToast({ title: t('auth.consentRequired'), icon: 'none' })
  }

  return (
    <View className="consent-page">
      <View className="consent-header">
        <Text className="page-title">{t('auth.privacyConsentTitle')}</Text>
      </View>

      <ScrollView scrollY className="policy-scroll">
        <PrivacyPolicyContent />
      </ScrollView>

      <View className="consent-actions">
        <Button
          type="primary"
          block
          loading={isLoading}
          onClick={handleAgree}
          className="btn-agree"
        >
          {t('auth.agreeAndContinue')}
        </Button>
        <Button
          plain
          block
          onClick={handleRefuse}
          className="btn-refuse"
        >
          {t('auth.refuse')}
        </Button>
      </View>

      <Toast
        visible={toastVisible}
        content={toastMsg}
        onClose={() => setToastVisible(false)}
      />
    </View>
  )
}
```

```scss
// frontend/src/pages/auth/consent/index.scss
.consent-page {
  min-height: 100vh;
  background: var(--color-background);
  display: flex;
  flex-direction: column;
}

.consent-header {
  padding: var(--spacing-lg) var(--spacing-md);
  text-align: center;

  .page-title {
    display: block;
    font-size: 18px;
    font-weight: bold;
    color: var(--color-text-primary);
  }
}

.policy-scroll {
  flex: 1;
  padding: 0 var(--spacing-md);
  max-height: 60vh;
}

.policy-content {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  box-shadow: var(--shadow-card);

  .policy-title {
    display: block;
    /* R21-P2-1: 字号对齐规范集 {12,13,15,18,24,32}px */
    font-size: var(--fs-body); /* 15px */
    font-weight: bold;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm);
  }

  .policy-text {
    display: block;
    font-size: 13px;
    color: var(--color-text-secondary);
    line-height: 1.6;
  }
}

.consent-actions {
  padding: var(--spacing-md) var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);

  .btn-agree {
    background: var(--color-primary);
    color: var(--color-text-inverse);
    border-radius: var(--radius-sm);
    height: 48px;
    font-size: 15px;
  }

  .btn-refuse {
    border-radius: var(--radius-sm);
    height: 44px;
    /* R21-P2-1: 字号对齐规范集 {12,13,15,18,24,32}px */
    font-size: var(--fs-small); /* 13px */
  }
}
```

> **i18n 新增条目**：
> - zh-CN: `auth.privacyConsentTitle` = "隐私政策同意"
> - zh-CN: `auth.privacyPolicyTitle` = "隐私政策"
> - zh-CN: `auth.privacyPolicyBody` = "（隐私政策正文内容）"
> - zh-CN: `auth.agreeAndContinue` = "同意并继续"
> - zh-CN: `auth.refuse` = "拒绝"
> - zh-CN: `auth.consentRequired` = "需同意隐私政策才能使用"
> - zh-CN: `auth.consentFailed` = "同意记录失败，请重试"
>
> <!-- R21-P3-1: 补充 en-US 对应翻译 -->
> - en-US: `auth.privacyConsentTitle` = "Privacy Policy Consent"
> - en-US: `auth.privacyPolicyTitle` = "Privacy Policy"
> - en-US: `auth.privacyPolicyBody` = "(Privacy policy content)"
> - en-US: `auth.agreeAndContinue` = "Agree and Continue"
> - en-US: `auth.refuse` = "Refuse"
> - en-US: `auth.consentRequired` = "You must agree to the privacy policy to continue"
> - en-US: `auth.consentFailed` = "Consent recording failed, please retry"



## 10. 验证清单

### 构建验证
```bash
cd frontend && npm run build:h5
```

### 视觉验证
- [ ] 登录页布局符合设计系统（Logo 区域 + 微信按钮 + 手机号区域 + 协议）
- [ ] 微信按钮使用绿色 `#2A9D8F`
- [ ] 手机号登录按钮使用主色 `#E63946`
- [ ] 验证码倒计时按钮在倒计时时禁用
- [ ] 空状态正确显示引导文字

### 功能验证
- [ ] 微信登录：点击 → wx.login() → 后端 → 返回 JWT → 跳转首页
- [ ] 手机号登录：输入手机号 → 发送验证码 → 输入验证码 → 登录 → 跳转首页
- [ ] Token 自动刷新：access_token 过期 → 用 refresh_token 刷新 → 重试请求
- [ ] 登出：清除本地 Token → 跳转登录页
- [ ] H5 降级：生成 Token → 跳转 H5 → 换取 JWT

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 页面使用 React 函数组件 + TypeScript
- **ALL** 状态管理使用 Zustand
- **ALL** API 调用通过 `services/` 层封装，**禁止** 在组件中直接调用 `Taro.request`
- **禁止** 使用 class 组件
- **禁止** 硬编码颜色值，使用 CSS 变量
- **禁止** 安装新的 npm 包
