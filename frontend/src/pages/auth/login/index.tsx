/**
 * 登录页（01-auth/frontend.md §4）
 * 微信一键登录 / 手机号验证码登录
 */
import { useState, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { Cell, Toast, Input, Button } from '@nutui/nutui-react'
import { useAuthStore } from '@/stores/authStore'
import { sendSms } from '@/services/auth'
import { useTranslation } from 'react-i18next'
import './index.scss'

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
      // FS8-P1-1: needsConsent=true 时 store 已 navigateTo 同意页，
      // 页面不得再 switchTab home（否则同意页被立即切走，PIPL 链路断裂）
      const needsConsent = await wechatLogin(code)
      if (!needsConsent) {
        Taro.switchTab({ url: '/pages/home/index' })
      }
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
      // FS8-P1-1: needsConsent=true 时 store 已 navigateTo 同意页，勿再 switchTab
      const needsConsent = await phoneLogin(phone, smsCode)
      if (!needsConsent) {
        Taro.switchTab({ url: '/pages/home/index' })
      }
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
            maxLength={11}
            placeholder={t('auth.phonePlaceholder')}
            value={phone}
            onChange={(val) => setPhone(val)}
          />
        </Cell>
        <Cell>
          <View className="sms-row">
            <Input
              type="number"
              maxLength={6}
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
