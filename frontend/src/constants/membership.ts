/**
 * membership 模块常量（10-membership/frontend.md §7）
 *
 * FS6-P3 契约同步：设计样例的 TIER_PRICING 硬编码（元级定价）不落盘——
 * 定价以后端 GET /membership/tiers（MembershipTierConfig 表，分单位 price_*_cents）
 * 为唯一权威源（避免与后端种子数据双源漂移）；等级名称/权益文案渲染同走后端
 * tiers.name / benefits 字符串。仅保留 UI 状态机相关常量。
 */

/** 会员等级顺序 */
export const TIER_ORDER = ['free', 'member', 'pro', 'coach'] as const
export type TierName = (typeof TIER_ORDER)[number]

/** 会员状态映射（状态色 + i18n key） */
export const MEMBERSHIP_STATUS_MAP: Record<string, {
  color: string
  labelKey: string
}> = {
  active: { color: 'var(--color-success)', labelKey: 'membership.statusActive' },
  expiring_soon: { color: 'var(--color-accent)', labelKey: 'membership.statusExpiringSoon' },
  expired: { color: 'var(--color-primary)', labelKey: 'membership.statusExpired' },
  grace_period: { color: 'var(--color-accent)', labelKey: 'membership.statusGracePeriod' },
  closed: { color: 'var(--color-text-secondary)', labelKey: 'membership.statusClosed' },
  none: { color: 'var(--color-text-secondary)', labelKey: 'membership.statusNone' },
}

/** 权益到期后的功能访问状态（用于前端功能入口控制，useMembershipGate 消费） */
export const EXPIRED_ACCESS_MAP = {
  analysis_reports: 'readonly', // 历史分析报告只读
  annotated_video: '30days', // 标注视频 30 天内
  training_plan: 'readonly', // 训练方案只读
  teaching_3d: 'hidden', // 3D 教学隐藏
  progress_analysis: 'hidden', // 进度分析隐藏
  dashboard: 'basic', // 数据看板基础
} as const

export type MembershipFeature = keyof typeof EXPIRED_ACCESS_MAP
export type ExpiredAccessLevel = (typeof EXPIRED_ACCESS_MAP)[MembershipFeature]

/**
 * 「我的」Tab 在 tabBar 中的索引（app.config.ts 顺序：
 * home=0 / training=1 / match=2 / community=3 / user=4），
 * 通知角标挂载点。
 */
export const USER_TAB_INDEX = 4
