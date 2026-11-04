/**
 * 隐私政策同意页（01-auth/frontend.md §9.1，R20-P1-3：PIPL 合规）
 *
 * 触发条件：wechatLogin/phoneLogin 成功后 requires_consent=true（API §2.1/§2.2），
 * 或 checkConsentStatus 返回 consented=false（API §2.10）时跳转至此页。
 */
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
