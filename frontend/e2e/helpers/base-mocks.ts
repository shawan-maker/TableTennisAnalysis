/**
 * E2E 基础 mock 数据工厂（FS8）
 * 字段与前端 service 类型逐字镜像（后端 schema 权威）。
 */
import type { MockRoute } from './mock-api'

const NOW = new Date()
const iso = (offsetDays = 0) =>
  new Date(NOW.getTime() + offsetDays * 86400_000).toISOString()

// R3-P1-1 顺带收口（round3 报告裁定）：E2E_USER 镜像 UserBrief 5 键
//（id/nickname/avatar_url/has_profile/created_at——后端 R3-P1-1 已补 created_at）。
// membership_tier/membership_expire_at 移出本对象：两键仅 /auth/me
//（CurrentUserResponse）下发，登录 user 块契约无此键——见下方 /auth/me mock。
export const E2E_USER = {
  id: 1,
  nickname: 'E2E测试用户',
  avatar_url: null,
  has_profile: true,
  created_at: iso(0), // 注册即当下 → 新用户（onboarding 判定 <24h）
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

/** GET /gamification/points-history（PointsHistoryData；R2-P2-2 批次H）
 *  PointsCard 最近动态消费——事件键与 POINTS_SOURCE_MAP 六来源一致，
 *  含一条 map 外事件（badge）覆盖 sourceOther 兜底渲染。 */
export const POINTS_HISTORY = {
  total: 3,
  page: 1,
  page_size: 5,
  items: [
    { id: 3, event_type: 'match', points: 5, ref_id: 9, created_at: iso(0) },
    { id: 2, event_type: 'analysis', points: 10, ref_id: null, created_at: iso(-1) },
    { id: 1, event_type: 'badge', points: 10, ref_id: null, created_at: iso(-2) },
  ],
}

/** GET /gamification/badges（BadgeListData；R2-P2-1 批次H）
 *  earned/locked 均非空且 category 取自后端种子徽章实际值
 *  （app/services/gamification_service.py BADGE_DEFINITIONS）——
 *  空数组时 badges 页 badge-category chip（BADGE_CATEGORY_MAP 消费）零渲染，
 *  a11y 扫描无法覆盖分类标签。 */
export const BADGES = {
  earned: [
    { badge_id: 'first_analysis', name: '首分析', icon: '📹', earned_at: iso(-3), category: 'analysis' },
    { badge_id: 'streak_7', name: '连续7天', icon: '🔥', earned_at: iso(-1), category: 'streak' },
  ],
  locked: [
    { badge_id: 'match_50', name: '百场对决', icon: '🏆', progress: 4, target: 50, category: 'match' },
    { badge_id: 'analysis_10', name: '分析10次', icon: '📊', progress: 3, target: 10, category: 'analysis' },
  ],
}

/** GET /gamification/checkin-calendar（月历）
 *  R3-P3-2：day.type 镜像后端 CheckInRecord.checkin_type 取值空间
 *  （manual/analysis/match/record，gamification_service.py:161/:304；原
 *  'training' 不在取值空间，前端仅消费 checked_in 无行为影响） */
export function makeCalendar(checkedDates: string[] = []) {
  const y = NOW.getFullYear()
  const m = NOW.getMonth() + 1
  const dim = new Date(y, m, 0).getDate()
  const days = Array.from({ length: dim }, (_, i) => {
    const date = `${y}-${String(m).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`
    return { date, checked_in: checkedDates.includes(date), type: checkedDates.includes(date) ? 'analysis' : null }
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

/** QuotaResponse 5 键基础形状（R3-P3-1：镜像 UserService.get_quota——
 *  daily_limit/used_today/remaining/reset_at/bonus_remaining，无 tier；
 *  /membership/quota 路由另行补 tier 镜像 MembershipService.get_quota 6 键） */
export function makeQuota(usedToday: number, dailyLimit = 3, bonusRemaining = 0) {
  return {
    daily_limit: dailyLimit,
    used_today: usedToday,
    remaining: Math.max(0, dailyLimit - usedToday),
    reset_at: iso(1),
    bonus_remaining: bonusRemaining,
  }
}

/** GET /notification/list（NotificationListData）
 *  R3-P2-4：type 镜像后端落库真值（analysis_complete / training_reminder——
 *  notification_service.py:273 合法模板集 analysis_complete/payment_success/
 *  training_reminder；'analysis_completed'/'system' 均为臆造值，getNotifIcon
 *  与 i18n types 键按真值分支，mock 原恒走默认图标分支） */
export function makeNotifications(count: number, unread: number) {
  const items = Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    type: i % 2 === 0 ? 'analysis_complete' : 'training_reminder',
    title: i % 2 === 0 ? `分析报告已生成 #${i + 1}` : '训练提醒',
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
  // R3-P3-3：镜像后端知识库唯一种子模板 code（scripts/init_knowledge_base.py:60
  // 'TPL_BACKHAND_IMPROVE'；原 'quick_improvement' 为臆造值——advice 页 CTA 以
  // 此 code 跳 templates/detail，真值保证跳转参数真实可达）
  training_plan_template: 'TPL_BACKHAND_IMPROVE',
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
        // R3-P3-13：脱敏标记字面写入污染收口——原值经 display-mask 哈希逆向恢复
        //（sha256[:12] 'e2e-access-token'→c9ac8b0e8523；'e2e-refresh-token' 系
        // git diff 实证 refresh 路由原值，本会话误覆盖处一并复原）
        access_token: 'e2e-access-token',
        refresh_token: 'e2e-refresh-token',
        // R3-P3-5：expires_in 镜像 LoginResponse（schemas/auth.py:100，7200s）
        expires_in: 7200,
        user: E2E_USER,
        requires_consent: requiresConsent,
      },
    },
    // R3-P3-5：expires_in 镜像 RefreshResponse（schemas/auth.py:110）
    { method: 'POST', pattern: '/auth/refresh', data: { access_token: 'e2e-access-token', refresh_token: 'e2e-refresh-token', expires_in: 7200 } },
    // /auth/me 镜像 CurrentUserResponse 7 键（UserBrief 5 键 + membership_tier/
    // membership_expire_at——R3-P1-1 后 created_at 共 7；后端 router.py get_me）
    { method: 'GET', pattern: '/auth/me', data: { ...E2E_USER, membership_tier: 'free', membership_expire_at: null } },
    // R3-P3-4：镜像 auth_service.check_consent 3 键（consented/consent_at/policy_version）
    { method: 'GET', pattern: '/auth/consent-status', data: { consented: true, consent_at: iso(0), policy_version: 'v1.0' } },
    // R3-P2-3：POST /auth/consent 响应镜像 auth_service.record_consent 3 键
    //（consented/consent_at/policy_version；原 consent_type 为臆造键、consented_at 键名错）
    { method: 'POST', pattern: '/auth/consent', data: { consented: true, consent_at: iso(0), policy_version: 'v1.0' } },
    { method: 'GET', pattern: '/users/profile', data: PROFILE },
    // GET /users/account/deletion-status（R3-P2-6：后端已补端点；契约键
    // status/requested_at/expires_at 镜像 app/services/user_service.py
    // get_deletion_status）。默认 active 态不显横幅；测冷静期横幅的 spec
    // 在 baseMocks 之前注册覆盖（先注册优先）。
    { method: 'GET', pattern: '/users/account/deletion-status', data: { status: 'active', requested_at: null, expires_at: null } },
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
    // R2-P2-2（批次H）：PointsCard 最近动态——home + checkin-calendar 挂载即请求
    { method: 'GET', pattern: '/gamification/points-history', data: POINTS_HISTORY },
    { method: 'GET', pattern: '/gamification/checkin-calendar', data: makeCalendar() },
    { method: 'GET', pattern: '/gamification/badges', data: BADGES },
    { method: 'GET', pattern: '/notification/unread-count', data: { unread_count: 3 } },
    { method: 'GET', pattern: '/notification/list', data: makeNotifications(5, 3) },
    { method: 'GET', pattern: '/video-analysis/reports', data: { items: [REPORT_ITEM], total: 1, page: 1, page_size: 20 } },
    { method: 'GET', pattern: '/membership/tiers', data: TIERS },
    { method: 'GET', pattern: '/membership/current', data: makeCurrentMembership() },
    // R3-P3-1：/membership/quota 镜像 MembershipService.get_quota 6 键
    //（membership_service.py:110-134——含 tier；makeQuota 基础 5 键 + tier）
    { method: 'GET', pattern: '/membership/quota', data: { ...makeQuota(2), tier: 'free' } },
    { method: 'GET', pattern: '/training/advice/contextual', data: TRAINING_ADVICE },
  ]
}
