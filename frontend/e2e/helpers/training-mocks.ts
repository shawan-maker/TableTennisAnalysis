/**
 * E2E-04 训练闭环 mock 状态机（docs/07实施计划/02-测试计划.md §7.4）
 *
 * 以内存状态镜像后端语义（响应字段与前端 services/training.ts 镜像的后端 schema 逐字一致）：
 * - GET  /training/templates(|/{id})   免费态 HTTP 403 + code 40300「此功能需要会员」
 *                                      （core/deps.require_membership 消息逐字）→ 前端
 *                                      isMembershipError → Empty 升级引导分支；
 *                                      state.member 由测试侧翻转（模拟支付开通）
 * - GET  /training/plans/{id}/sessions  训练单列表（1 已完成 + 1 待完成 → 进度 1/2）
 * - POST /training/plans/{id}/sessions/{sid}/complete  标记完成 +5 分（CompleteSessionData
 *                                      镜像；积分入账为后端域，前端断言 Toast/进度联动）
 * - POST /training/plans/{id}/re-evaluate 重新评估（ReEvaluateData + envelope message
 *                                      携带后端操作提示文案）
 * - GET  /training/plans/{id}/adjustments 调整历史（重新评估后版本 +1）
 */
import type { MockRoute } from './mock-api'

const iso = () => new Date().toISOString()

/** 训练方案训练单（TrainingSessionItem 镜像） */
interface SessionState {
  id: number
  plan_id: number
  name: string
  scheduled_date: string | null
  is_completed: boolean
  completed_at: string | null
  exercises: string[]
  session_index: number
  reps: number
}

export const PLAN_ID = 8001

export function createTrainingMocks() {
  const state: { member: boolean; planVersion: number; sessions: SessionState[] } = {
    member: false,
    planVersion: 2,
    sessions: [
      {
        id: 8101,
        plan_id: PLAN_ID,
        name: '正手拉冲多球',
        scheduled_date: '2026-11-08',
        is_completed: true,
        completed_at: iso(),
        exercises: ['多球连续拉冲'],
        session_index: 1,
        reps: 30,
      },
      {
        id: 8102,
        plan_id: PLAN_ID,
        name: '反手推挡稳定性',
        scheduled_date: '2026-11-09',
        is_completed: false,
        completed_at: null,
        exercises: ['推挡定点'],
        session_index: 2,
        reps: 20,
      },
    ],
  }

  const routes: MockRoute[] = [
    // 模板列表（API §8.3，会员功能；免费态 403/40300 会员守卫）
    {
      method: 'GET',
      pattern: '/training/templates',
      statusFn: () => (state.member ? 200 : 403),
      envelopeCode: 40300,
      errorMessage: '此功能需要会员',
      dynamic: () => ({
        total: 2,
        page: 1,
        page_size: 20,
        items: [
          { id: 101, template_code: 'quick_improvement', name: '快速提升方案', problem_id: 'forehand_late_contact' },
          { id: 102, template_code: 'footwork_base', name: '步法基础巩固', problem_id: null },
        ],
      }),
    },
    // 模板详情（API §8.4，会员功能；TemplateDetail 镜像，含 created_at FS5-P3）
    {
      method: 'GET',
      pattern: '/training/templates/*',
      statusFn: () => (state.member ? 200 : 403),
      envelopeCode: 40300,
      errorMessage: '此功能需要会员',
      dynamic: ({ params }) => ({
        id: Number(params[0]),
        template_code: 'quick_improvement',
        name: '快速提升方案',
        problem_id: 'forehand_late_contact',
        template_data: {
          goal: { metric: '正手拉冲成功率', target: 70 },
          sessions: [
            { name: '多球拉冲', reps: 30 },
            { name: '推挡定点', reps: 20 },
          ],
          exercises: ['正手拉冲', '反手推挡'],
          metrics: ['正手拉冲成功率', '落点命中率'],
        },
        created_at: iso(),
      }),
    },
    // 训练单列表（API §8.7，会员功能）
    {
      method: 'GET',
      pattern: '/training/plans/*/sessions',
      statusFn: () => (state.member ? 200 : 403),
      envelopeCode: 40300,
      errorMessage: '此功能需要会员',
      dynamic: ({ params }) => ({
        plan_id: Number(params[0]),
        total: state.sessions.length,
        page: 1,
        page_size: 20,
        items: state.sessions.map((s) => ({ ...s })),
      }),
    },
    // 标记完成（API §8.8；积分 +5 由后端积分服务入账，CompleteSessionData.points_earned 透传）
    {
      method: 'POST',
      pattern: '/training/plans/*/sessions/*/complete',
      dynamic: ({ params }) => {
        const sessionId = Number(params[1])
        const target = state.sessions.find((s) => s.id === sessionId)
        if (!target) throw new Error('session not found')
        target.is_completed = true
        target.completed_at = iso()
        const completed = state.sessions.filter((s) => s.is_completed).length
        return {
          session_id: sessionId,
          is_completed: true,
          plan_progress: Math.round((completed / state.sessions.length) * 100),
          points_earned: 5,
          completed_at: target.completed_at,
        }
      },
    },
    // 重新评估（API §8.6；envelope message 携带后端操作提示）
    {
      method: 'POST',
      pattern: '/training/plans/*/re-evaluate',
      dynamic: ({ params }) => {
        state.planVersion += 1
        return {
          plan_id: Number(params[0]),
          action: 'adjust',
          reason: '连续 3 次分析无改善，下调训练强度',
        }
      },
      message: '方案已重新评估',
    },
    // 方案调整历史（API §8.5；重新评估后 current_version +1）
    {
      method: 'GET',
      pattern: '/training/plans/*/adjustments',
      dynamic: ({ params }) => ({
        plan_id: Number(params[0]),
        current_version: state.planVersion,
        adjustments: [
          {
            id: 9001,
            version: state.planVersion,
            action: 'adjust',
            reason: '连续 3 次分析无改善，下调训练强度',
            trigger_report_id: 7,
            created_at: iso(),
            changes_summary: '下调正手拉冲组数 30→20',
          },
        ],
      }),
    },
  ]

  return { routes, state }
}
