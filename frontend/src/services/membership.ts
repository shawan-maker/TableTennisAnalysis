/**
 * membership 模块 API Service（10-membership/frontend.md §2）
 * 端点与后端 app/api/v1/membership/router.py 逐字一致（3 个）。
 *
 * FS6-P3 契约同步（与设计文档 §2 接口定义的差异，以后端 schema 为准）：
 * - 定价字段为 price_monthly_cents / price_quarterly_cents / price_yearly_cents
 *   （设计样例 price_monthly 等缺 _cents 后缀；app/schemas/membership.py TierBrief）
 * - TierBrief.quota 为 quota_config: Record<string, unknown>（设计样例 quota.daily_analysis_limit）
 * - QuotaData 补 bonus_remaining（R15-VA-N1 付费分析包剩余额度，会员态为信息性展示）
 */
import request from './request'

/** 会员等级权益（app/schemas/membership.py TierBrief） */
export interface TierInfo {
  tier: string
  name: string
  price_monthly_cents: number
  price_quarterly_cents: number
  price_yearly_cents: number
  benefits: string[]
  quota_config: Record<string, unknown>
}

/** 等级列表 */
export interface TierListData {
  tiers: TierInfo[]
}

/** 当前会员状态（app/schemas/membership.py CurrentMembershipResponse） */
export interface CurrentMembershipData {
  tier: string
  status: string // none/active/expiring_soon/expired/grace_period/closed
  start_at: string | null
  expire_at: string | null
  days_remaining: number
  auto_renew: boolean
}

/** 今日剩余额度（app/schemas/membership.py QuotaResponse） */
export interface QuotaData {
  tier: string
  daily_limit: number
  used_today: number
  remaining: number
  reset_at: string
  /** R15-VA-N1：付费分析包剩余额度 */
  bonus_remaining: number
}

/**
 * 获取会员等级与权益对比（API §11.1，缓存 1h）。
 */
export function getTiers() {
  return request.get<TierListData>('/membership/tiers')
}

/**
 * 获取当前会员状态（API §11.2，含到期时间、剩余天数）。
 */
export function getCurrentMembership() {
  return request.get<CurrentMembershipData>('/membership/current')
}

/**
 * 获取今日剩余免费分析次数（API §11.3，Redis 计数器）。
 */
export function getQuota() {
  return request.get<QuotaData>('/membership/quota')
}
