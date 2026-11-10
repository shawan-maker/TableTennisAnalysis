/**
 * E2E 基础 mock 数据工厂（FS8）
 * 字段与前端 service 类型逐字镜像（后端 schema 权威）。
 */
import type { MockRoute } from './mock-api'

const NOW = new Date()
const iso = (offsetDays = 0) =>
  new Date(NOW.getTime() + offsetDays * 86400_000).toISOString()

export const E2E_USER = {
  id: 1,
  nickname: 'E2E测试用户',
  avatar_url: null,
  has_profile: true,
  created_at: iso(0), // 注册即当下 → 新用户（onboarding 判定 <24h）
  membership_tier: 'free',
  membership_expire_at: null,
}

/** GET /users/profile（UserProfile） */
export const PROFILE = {
  id: 1,
  nickname: 'E2E测试用户',
  avatar_url: null,
  profile: {
    kqs_rating: 1500,
    kqs_username: null,
    playing_style: 'loop',
    self_assessed_level: 'intermediate',
    equipment_config: null,
    profile_completeness: 85,
  },
}

/** GET /dashboard/overview（OverviewData） */
export const OVERVIEW = {
  win_rate: 0.56,
  wins: 5,
  losses: 4,
  analysis_count: 3,
  training_frequency_per_week: 2,
  streak_days: 3,
  trend: 'up',
  latest_advice_summary: {
    report_id: 9,
    summary: '加强正手拉冲练习',
    has_unresolved_issues: true,
    latest_report_at: iso(-1),
  },
}

/** GET /gamification/points（PointsData） */
export const POINTS = {
  total_points: 120,
  monthly_points: 30,
  current_streak: 3,
  streak_icon: '🔥',
}

/** GET /gamification/checkin-calendar（月历） */
export function makeCalendar(checkedDates: string[] = []) {
  const y = NOW.getFullYear()
  const m = NOW.getMonth() + 1
  const dim = new Date(y, m, 0).getDate()
  const days = Array.from({ length: dim }, (_, i) => {
    const date = `${y}-${String(m).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`
    return { date, checked_in: checkedDates.includes(date), type: checkedDates.includes(date) ? 'training' : null }
  })
  return { year: y, month: m, days, monthly_checkin_count: checkedDates.length, streak_days: 3 }
}

/** GET /membership/tiers（TierListData；quota_config 为 TierInfo 必填，模型默认 dict） */
export const TIERS = {
  tiers: [
    { tier: 'free', name: '免费版', price_monthly_cents: 0, price_quarterly_cents: 0, price_yearly_cents: 0, benefits: ['每日 3 次分析'], quota_config: { daily_analysis_limit: 3 } },
    { tier: 'member', name: '会员版', price_monthly_cents: 1800, price_quarterly_cents: 4500, price_yearly_cents: 15800, benefits: ['无限分析', '训练方案'], quota_config: { daily_analysis_limit: -1 } },
    { tier: 'pro', name: '专业版', price_monthly_cents: 4800, price_quarterly_cents: 12800, price_yearly_cents: 42800, benefits: ['无限分析', '训练方案', '专属客服'], quota_config: { daily_analysis_limit: -1 } },
    { tier: 'coach', name: '教练版', price_monthly_cents: 9800, price_quarterly_cents: 25800, price_yearly_cents: 88000, benefits: ['无限分析', '训练方案', '数据大屏'], quota_config: { daily_analysis_limit: -1 } },
  ],
}

/** GET /membership/current（CurrentMembershipData） */
export function makeCurrentMembership(tier = 'free', status = 'none') {
  return {
    tier,
    status,
    start_at: tier === 'free' ? null : iso(-10),
    expire_at: tier === 'free' ? null : iso(20),
    days_remaining: tier === 'free' ? 0 : 20,
    auto_renew: tier !== 'free',
  }
}

/** GET /membership/quota（QuotaData，R15-VA-N1） */
export function makeQuota(usedToday: number, dailyLimit = 3, bonusRemaining = 0) {
  return {
    tier: 'free',
    daily_limit: dailyLimit,
    used_today: usedToday,
    remaining: Math.max(0, dailyLimit - usedToday),
    reset_at: iso(1),
    bonus_remaining: bonusRemaining,
  }
}

/** GET /notification/list（NotificationListData） */
export function makeNotifications(count: number, unread: number) {
  const items = Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    type: i % 2 === 0 ? 'analysis_completed' : 'system',
    title: i % 2 === 0 ? `分析报告已生成 #${i + 1}` : '系统通知',
    content: `E2E 通知内容 ${i + 1}`,
    is_read: i >= unread ? true : false,
    created_at: iso(-1),
    extra_data: null,
  }))
  return { items, total: count, page: 1, page_size: 20 }
}

/** GET /video-analysis/reports 首条（ReportListItem） */
export const REPORT_ITEM = {
  id: 7,
  task_id: 3,
  created_at: iso(-1),
  is_llm_generated: true,
  cover_image_url: null,
  report_summary: '正手进攻效率提升，反手稳定性待加强',
}

/** GET /training/advice/contextual（TrainingAdviceData，字段镜像 services/training.ts） */
export const TRAINING_ADVICE = {
  report_id: 7,
  is_first_analysis: false,
  diagnosis: [
    {
      problem_id: 'forehand_late_contact',
      problem_name: '正手击球点偏晚',
      severity: 'medium',
      trend: 'new',
      description: '拉冲时击球点偏晚，影响连续进攻质量',
    },
  ],
  suggestions: [
    { type: 'new_issue', text: '正手拉冲多球训练：每组 30 球，共 3 组，固定高点期击球' },
  ],
  training_methods: [
    { method_id: 'm_001', name: '多球训练', description: '教练连续供球，固定落点区强化击球时机' },
  ],
  training_plan_template: 'quick_improvement',
}

/**
 * 全页面通用基础 mocks（首屏端点）。
 * requires_consent 可控登录响应；补充 mocks 追加到返回数组之后（先注册优先）。
 */
export function baseMocks(opts: { requiresConsent?: boolean } = {}): MockRoute[] {
  const requiresConsent = opts.requiresConsent ?? false
  return [
    {
      method: 'POST',
      pattern: '/auth/phone-login',
      data: {
        access_token: 'e2e-access-token',
        refresh_token: 'e2e-refresh-token',
        user: E2E_USER,
        requires_consent: requiresConsent,
      },
    },
    { method: 'POST', pattern: '/auth/refresh', data: { access_token: 'e2e-access-token', refresh_token: 'e2e-refresh-token' } },
    { method: 'GET', pattern: '/auth/me', data: E2E_USER },
    { method: 'GET', pattern: '/auth/consent-status', data: { consented: true } },
    { method: 'POST', pattern: '/auth/consent', data: { consent_type: 'privacy_policy', policy_version: 'v1.0', consented_at: iso(0) } },
    { method: 'GET', pattern: '/users/profile', data: PROFILE },
    { method: 'GET', pattern: '/users/quota', data: makeQuota(2) },
    { method: 'GET', pattern: '/dashboard/overview', data: OVERVIEW },
    { method: 'GET', pattern: '/dashboard/win-rate-trend', data: { labels: ['10/01', '11/01'], series: [{ name: '胜率', data: [0.4, 0.56] }] } },
    // 形状镜像 services/dashboard.ts TechniqueStatsData（technique_distribution）；
    // E2E-02 曾因误写 { items: [] } 导致 TechniqueStats 组件 undefined.reduce 崩掉整页
    { method: 'GET', pattern: '/dashboard/technique-stats', data: { technique_distribution: [] } },
    // 形状镜像 LandingHeatmapData（nine_grid 9×9 + distribution + 计数）
    {
      method: 'GET',
      pattern: '/dashboard/landing-heatmap',
      data: {
        nine_grid: Array.from({ length: 9 }, () => Array.from({ length: 9 }, () => 0)),
        distribution: { forehand: 0, backhand: 0, middle: 0 },
        total_rallies: 0,
        source_reports_count: 0,
      },
    },
    { method: 'GET', pattern: '/dashboard/match-records', data: { items: [], total: 0, page: 1, page_size: 20 } },
    { method: 'GET', pattern: '/gamification/points', data: POINTS },
    { method: 'GET', pattern: '/gamification/checkin-calendar', data: makeCalendar() },
    { method: 'GET', pattern: '/gamification/badges', data: { earned: [], locked: [] } },
    { method: 'GET', pattern: '/notification/unread-count', data: { unread_count: 3 } },
    { method: 'GET', pattern: '/notification/list', data: makeNotifications(5, 3) },
    { method: 'GET', pattern: '/video-analysis/reports', data: { items: [REPORT_ITEM], total: 1, page: 1, page_size: 20 } },
    { method: 'GET', pattern: '/membership/tiers', data: TIERS },
    { method: 'GET', pattern: '/membership/current', data: makeCurrentMembership() },
    { method: 'GET', pattern: '/membership/quota', data: makeQuota(2) },
    { method: 'GET', pattern: '/training/advice/contextual', data: TRAINING_ADVICE },
  ]
}
