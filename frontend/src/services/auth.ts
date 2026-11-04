/**
 * auth 模块 API Service（01-auth/frontend.md §2）
 * 端点与后端 app/api/v1/auth/router.py 逐字一致
 */
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
