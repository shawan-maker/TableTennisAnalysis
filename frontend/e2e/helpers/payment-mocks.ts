/**
 * E2E-03 付费转化 mock 状态机（docs/07实施计划/02-测试计划.md §7.3）
 *
 * 以内存状态镜像后端语义（响应字段与前端 service 镜像的后端 schema 逐字一致）：
 * - GET  /users/quota          始终免费额度视图（user_service.get_quota 不看会员态）
 *                              —— used_today=3 即测试计划步骤 1「免费分析 3 次」
 * - POST /video-analysis/tasks 免费态 → HTTP 429 + code 42910（步骤 2「第 4 次尝试」，
 *                              video_analysis_service._check_free_quota AppException 消息逐字）；
 *                              会员态放行（create_task 会员跳过额度检查，S5）
 * - POST /payment/orders       创建 pending 订单（OrderCreateResult 镜像；
 *                              amount_cents 由 tier/period 匹配 tiers 定价）
 * - GET  /payment/orders       创建后首次查询翻转为 paid（模拟微信回调在
 *                              pollOrderStatus 2s 轮询窗内到达；后端无单订单
 *                              GET 端点，轮询走列表过滤 order_id）
 * - GET  /membership/current   paid 后 tier=member/status=active（权益生效）
 * - GET  /membership/quota     会员态 {daily_limit:-1, remaining:-1}（R12-Membership-1）
 */
import type { MockRoute } from './mock-api'
import { makeCurrentMembership } from './base-mocks'

const iso = () => new Date().toISOString()

/** 免费日额度已用 3/3（后端 FREE_DAILY_LIMIT=3；与 /users/quota 免费视图一致） */
const EXHAUSTED_FREE_QUOTA = {
  tier: 'free',
  daily_limit: 3,
  used_today: 3,
  remaining: 0,
  reset_at: iso(),
  bonus_remaining: 0,
}

export interface PaymentOrderState {
  id: number
  order_no: string
  product_type: string
  amount_cents: number
  status: 'pending' | 'paid' | 'refunded' | 'cancelled'
  created_at: string
  paid_at: string | null
}

/**
 * 构建付费转化 mock 路由（闭包共享状态）。
 * 返回 { routes, state }：state.paid 供测试侧读取订单/断言 WS 载荷。
 */
export function createPaymentMocks() {
  const state: { paid: boolean; order: PaymentOrderState | null; nextOrderId: number } = {
    paid: false,
    order: null,
    nextOrderId: 9001,
  }

  /** tier/period → 分定价（与 base-mocks TIERS 同源；后端 pricing 唯一权威） */
  const PRICING: Record<string, Record<string, number>> = {
    member: { monthly: 1800, quarterly: 4500, yearly: 15800 },
    pro: { monthly: 4800, quarterly: 12800, yearly: 42800 },
    coach: { monthly: 9800, quarterly: 25800, yearly: 88000 },
  }

  const routes: MockRoute[] = [
    // ── 分析上传链（upload-token → OSS 直传 → 确认；POST tasks 由状态机分流）──
    // OSS 直传（PostObject 表单；复用 api 域以便 page.route 统一拦截，同 E2E-01）
    { method: 'POST', pattern: '/mock-oss/videos/*', data: {} },
    {
      method: 'POST',
      pattern: '/video-analysis/upload-token',
      data: {
        file_id: 42,
        oss_key: '[REDACTED:sha256:c92dd3e7c7b7]',
        sts_credentials: {
          access_key_id: 'e2e-ak',
          access_key_secret: '[REDACTED]',
          security_token: '[REDACTED:sha256:deff2daef65b]',
          expiration: iso(),
          bucket: 'e2e-bucket',
          endpoint: 'https://oss.example.com',
        },
        upload_url: 'https://api.pingpongai.com/api/v1/mock-oss/videos/e2e-video.mp4',
        expire_at: iso(),
      },
    },
    { method: 'POST', pattern: '/video-analysis/upload-complete', data: { file_id: 42, status: 'uploaded' } },
    // 步骤 2/8：创建任务——免费态 429/42910（后端消息逐字），会员态放行
    {
      method: 'POST',
      pattern: '/video-analysis/tasks',
      statusFn: () => (state.paid ? 200 : 429),
      envelopeCode: 42910,
      errorMessage: '今日免费分析次数已用完，升级会员可无限分析',
      dynamic: () => ({ task_id: 3, task_uuid: 'e2e-task-3', status: 'processing', estimated_wait_minutes: 2 }),
    },
    // 进度页对账（步骤 8 断言 processing 态；静态 processing 载荷，报告全流程归 E2E-01）
    {
      method: 'GET',
      pattern: '/video-analysis/tasks/*',
      data: {
        task_id: 3,
        task_uuid: 'e2e-task-3',
        status: 'processing',
        current_step: 4,
        total_steps: 10,
        step_name: 'ball_tracking',
        progress: 0.35,
        estimated_remaining_seconds: 60,
        error_message: null,
        created_at: iso(),
        report_id: null,
      },
    },

    // ── 额度视图 ──
    // /users/quota：始终免费视图（后端 get_quota 不感知会员态，展示层如实反映）
    { method: 'GET', pattern: '/users/quota', data: EXHAUSTED_FREE_QUOTA },
    // /membership/quota：会员态 -1 无限（R12-Membership-1）；免费态已耗尽
    {
      method: 'GET',
      pattern: '/membership/quota',
      dynamic: () =>
        state.paid
          ? { tier: 'member', daily_limit: -1, used_today: 0, remaining: -1, reset_at: '', bonus_remaining: 0 }
          : EXHAUSTED_FREE_QUOTA,
    },

    // ── 订单（API §12.1/12.2）──
    {
      method: 'POST',
      pattern: '/payment/orders',
      dynamic: ({ body }) => {
        const tier = (body?.tier ?? 'member') as string
        const period = (body?.period ?? 'monthly') as string
        const id = state.nextOrderId++
        const order: PaymentOrderState = {
          id,
          order_no: `E2E${new Date().toISOString().slice(0, 10).replace(/-/g, '')}${String(id).padStart(4, '0')}`,
          product_type: body?.product_type ?? 'membership',
          amount_cents: PRICING[tier]?.[period] ?? 1800,
          status: 'pending',
          created_at: iso(),
          paid_at: null,
        }
        state.order = order
        return {
          order_id: order.id,
          order_no: order.order_no,
          amount_cents: order.amount_cents,
          payment_params: {
            prepay_id: 'e2e-prepay-1',
            pay_sign: 'e2e-sign',
            timestamp: '1760000000',
            nonce_str: 'e2e-nonce',
          },
        }
      },
    },
    // 创建后首次查询翻 paid：模拟微信回调在 pollOrderStatus 2s 等待窗内到达
    //（订单列表 GET 是后端无单订单 GET 端点下的轮询通道，paymentStore.pollOrderStatus）
    {
      method: 'GET',
      pattern: '/payment/orders',
      dynamic: () => {
        if (state.order && state.order.status === 'pending') {
          state.order = { ...state.order, status: 'paid', paid_at: iso() }
          state.paid = true
        }
        const items = state.order ? [state.order] : []
        return { items, total: items.length, page: 1, page_size: 50 }
      },
    },

    // ── 会员权益（paid 后 member/active）──
    {
      method: 'GET',
      pattern: '/membership/current',
      dynamic: () => (state.paid ? makeCurrentMembership('member', 'active') : makeCurrentMembership()),
    },
  ]

  return { routes, state }
}
