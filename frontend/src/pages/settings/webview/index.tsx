/**
 * 协议 WebView 承载页（14-tab-pages/settings.md L524-525）
 * 路由格式：pages/settings/webview?url=xxx&title=xxx（url/title 均 encodeURIComponent）
 *
 * R-FE-R1 批次B（FE-P2-21）：修复前「用户协议/隐私政策」onClick 仅 showToast
 * 「正在打开文档」实际无承载页（settings/webview 全工程零命中）。
 *
 * 端差异：weapp 端用 Taro WebView 组件加载（src 须为业务域名白名单内 https 页）；
 * H5 端虽存在 iframe 实现，但本地/E2E 环境无真实协议站点，且空白 iframe 会引入
 * axe frame-title 风险，故 H5 渲染降级提示（settings.webviewFallback）。
 */
import Taro, { useShareAppMessage } from '@tarojs/taro'
import { View, Text, WebView } from '@tarojs/components'
import { useTranslation } from 'react-i18next'
import './index.scss'

export default function SettingsWebviewPage() {
  const { t } = useTranslation()

  // weapp WebView 仅支持在线 https 页面；H5 端走降级提示分支
  const url = decodeURIComponent(Taro.getCurrentInstance().router?.params?.url || '')
  const titleParam = decodeURIComponent(Taro.getCurrentInstance().router?.params?.title || '')
  const pageTitle = titleParam || t('settings.aboutSection')

  useShareAppMessage(() => ({ title: pageTitle }))

  return (
    <View className="settings-webview-page">
      {process.env.TARO_ENV === 'weapp' && url ? (
        // eslint-disable-next-line jsx-a11y/iframe-has-title -- weapp web-view 为小程序原生组件（非 HTML iframe，无 title prop，标题由导航栏承载）；H5 走降级分支不渲染
        <WebView src={url} />
      ) : (
        <View className="webview-fallback">
          <Text className="fallback-icon">📄</Text>
          <Text className="fallback-title">{pageTitle}</Text>
          <Text className="fallback-text">{t('settings.webviewFallback')}</Text>
        </View>
      )}
    </View>
  )
}
