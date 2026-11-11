/**
 * FS8-7 axe 扫描补充 mocks（39 页真实内容态）
 *
 * baseMocks 覆盖通用首屏端点；本文件补齐扫描时渲染空态的页面主端点，
 * 载荷与前端 service 镜像的后端 schema 逐字一致：
 * - /users/big-data            userStore.BigData
 * - /users/rating-history      RatingHistoryItem 分页
 * - /video-analysis/tasks/3    TaskDetail（processing 态，扫描进度 UI 真实内容）
 * - /video-analysis/reports/7  ReportDetail（E2E-01 同源载荷）
 * - /match-data/records/1     MatchRecordDetailItem
 * - /scoring/matches           MatchBrief 分页（match-list 页）
 * - /scoring/matches/1         MatchDetailWithSequence（in_progress 记分牌态）
 * - /scoring/matches/1/statistics MatchStatisticResponse.stats_data
 * - /progress/summary          SummaryData
 * - /progress/comparison       ComparisonData（report_a/report_b query）
 * - /progress/technique-trends(/:metric) MetricTrend 列表 / TrendDetail
 * - /membership/current        member/active（R-FE-R1 批次B：progress 三页
 *   useMembershipGate 门控下 free 态会渲染升级引导而非真实内容——
 *   覆盖为会员态以保真扫描三页真实 UI；会员页 baseMocks free 态扫描让位）
 */
import type { MockRoute } from './mock-api'
import { makeCurrentMembership } from './base-mocks'

const iso = () => new Date().toISOString()

export const a11yMocks: MockRoute[] = [
  // 乒乓大数据（userStore.BigData）
  {
    method: 'GET',
    pattern: '/users/big-data',
    data: {
      highest_win_rating: 1600,
      win_streak: 3,
      match_cities: 2,
      total_opponents: 12,
      indirect_wins: ['张选手', '李选手'],
      total_matches: 9,
      win_rate: 0.56,
      favorite_shot: '正手拉冲',
    },
  },
  // 积分历史（RatingHistoryItem 分页）
  {
    method: 'GET',
    pattern: '/users/rating-history',
    data: {
      items: [
        { id: 1, rating: 1500, source: 'manual', recorded_at: iso() },
        { id: 2, rating: 1520, source: 'match', recorded_at: iso() },
      ],
      total: 2,
      page: 1,
      page_size: 20,
    },
  },
  // 分析任务详情（processing 态——processing 页扫描进度 UI 真实内容）
  {
    method: 'GET',
    pattern: '/video-analysis/tasks/*',
    data: {
      task_id: 3,
      task_uuid: 'a11y-task-3',
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
  // 报告详情（ReportDetail 镜像，E2E-01 同源载荷）
  {
    method: 'GET',
    pattern: '/video-analysis/reports/*',
    data: {
      id: 7,
      task_id: 3,
      task_uuid: 'a11y-task-3',
      created_at: iso(),
      is_llm_generated: true,
      is_readonly: false,
      result_data: {
        video_info: { duration_sec: 125, fps: 30, resolution: '1920x1080' },
        rally_analysis: { total_rallies: 48, avg_rally_length: 5.2, max_rally_length: 12 },
        landing_points: {
          nine_grid: [[2, 3, 1], [4, 8, 2], [3, 5, 2]],
          distribution: { forehand: 0.6, backhand: 0.25, middle: 0.15 },
        },
        technique_stats: { loop: 30, smash: 12, push: 8, block: 10 },
        ball_speed: { avg_speed_mps: 12.5, max_speed_mps: 18.2, speed_range: [8.1, 18.2] },
      },
      report_text: {
        summary: '正手进攻效率不错，反手稳定性待加强',
        issues: ['反手击球点偏晚', '步法移动偏慢'],
        suggestions: ['加强反手推挡多球训练', '组合步法练习提升移动'],
      },
      annotated_video_url: null,
      cover_image_url: null,
      report_images: null,
    },
  },
  // 比赛记录详情（MatchRecordDetailItem 镜像）
  {
    method: 'GET',
    pattern: '/match-data/records/*',
    data: {
      id: 1,
      opponent_name: '王教练',
      opponent_rating: 1550,
      my_score: 3,
      opponent_score: 1,
      is_win: true,
      format: 'bo3',
      match_type: 'friendly',
      match_date: iso(),
      match_id: 4001,
      is_detailed: true,
      notes: '正手拉冲发挥出色',
      details: [
        { sequence: 1, scorer: 'user', score_method: 'serve_point', technique_action: '正手拉冲' },
        { sequence: 2, scorer: 'opponent', score_method: 'rally_point' },
      ],
    },
  },
  // 比赛记录列表（match-data/record-list 页）
  {
    method: 'GET',
    pattern: '/match-data/records',
    data: {
      items: [
        {
          id: 1,
          opponent_name: '王教练',
          opponent_rating: 1550,
          my_score: 3,
          opponent_score: 1,
          is_win: true,
          format: 'bo3',
          match_type: 'friendly',
          match_date: iso(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    },
  },
  // 记分比赛列表（scoring/match-list 页，MatchBrief 分页）
  {
    method: 'GET',
    pattern: '/scoring/matches',
    data: {
      total: 2,
      page: 1,
      page_size: 20,
      items: [
        {
          id: 1,
          opponent_name: '王教练',
          format: 'bo3',
          match_type: 'friendly',
          status: 'in_progress',
          current_score_user: 3,
          current_score_opp: 2,
          is_win: null,
          created_at: iso(),
        },
        {
          id: 2,
          opponent_name: '李球友',
          format: 'bo1',
          match_type: 'training',
          status: 'finished',
          current_score_user: 11,
          current_score_opp: 7,
          is_win: true,
          created_at: iso(),
        },
      ],
    },
  },
  // 记分牌（MatchDetailWithSequence，in_progress 记分态）
  {
    method: 'GET',
    pattern: '/scoring/matches/*',
    dynamic: ({ params }) => ({
      id: Number(params[0]),
      opponent_name: '王教练',
      opponent_rating: 1550,
      format: 'bo3',
      match_type: 'friendly',
      target_score: 11,
      status: 'in_progress',
      current_score_user: 3,
      current_score_opp: 2,
      current_score: '3:2',
      current_server: 'user',
      current_game: 1,
      games_won_user: 0,
      games_won_opp: 0,
      is_win: null,
      final_score: null,
      created_at: iso(),
      finished_at: null,
      score_sequence: [
        { sequence: 1, scorer: 'user', score_method: 'serve_point', technique_action: '正手拉冲', game_number: 1 },
        { sequence: 2, scorer: 'opponent', score_method: 'rally_point', technique_action: null, game_number: 1 },
        { sequence: 3, scorer: 'user', score_method: 'rally_point', technique_action: '反手推挡', game_number: 1 },
      ],
    }),
  },
  // 比赛统计（stats_data 镜像 scoring-mocks）
  {
    method: 'GET',
    pattern: '/scoring/matches/*/statistics',
    data: {
      match_id: 1,
      stats_data: {
        score_distribution: { serve_point: 2, rally_point: 3, opponent_error: 1 },
        key_points: [],
        technique_breakdown: { '正手拉冲': 2, '反手推挡': 1 },
        total_points: 6,
      },
    },
  },
  // 会员当前态（R-FE-R1 批次B：extraMocks 优先级高于 baseMocks 的 free 态——
  // progress 三页 progress_analysis 门控 hidden，member/active 才渲染真实内容）
  {
    method: 'GET',
    pattern: '/membership/current',
    data: makeCurrentMembership('member', 'active'),
  },
  // 进度综合摘要（SummaryData）
  {
    method: 'GET',
    pattern: '/progress/summary',
    data: {
      summary_period: 'recent',
      total_analyses: 5,
      overall_progress: 'improving',
      metric_trends: [
        {
          metric: 'loop_success_rate',
          metric_name: '正手拉冲成功率',
          current_value: 62,
          previous_value: 55,
          change_rate: 0.127,
          trend: 'up',
          target: 70,
          target_progress: 0.45,
          persistence_count: 3,
        },
      ],
      problem_changes: { new: ['反手击球点偏晚'], resolved: ['发球抛球过高'], persistent: ['步法移动偏慢'] },
      training_plan_status: {
        current_plan_id: '8001',
        plan_version: 2,
        last_adjustment: iso(),
        adjustment_reason: '连续 3 次分析无改善，下调训练强度',
        goal_completion: { loop_success_rate: '45%' },
      },
      forecast: { loop_success_rate: { predicted_weeks_to_target: 4, confidence: 'medium', r_squared: 0.72 } },
    },
  },
  // 报告对比（ComparisonData；report_a/report_b query 透传）
  {
    method: 'GET',
    pattern: '/progress/comparison',
    dynamic: ({ query }) => ({
      report_a: { id: Number(query.get('report_a') ?? 6), created_at: iso() },
      report_b: { id: Number(query.get('report_b') ?? 7), created_at: iso() },
      comparisons: {
        technique_stats: {
          loop: { a: 25, b: 30, change: 0.2 },
          smash: { a: 10, b: 12, change: 0.2 },
        },
        landing: {
          forehand_pct: { a: 52, b: 60, change: 0.15 },
          backhand_pct: { a: 28, b: 25, change: -0.11 },
          middle_pct: { a: 20, b: 15, change: -0.25 },
        },
        rally: { avg_length_a: 4.8, avg_length_b: 5.2, max_length_a: 10, max_length_b: 12, change: 0.08 },
        ball_speed: { avg_a: 11.8, avg_b: 12.5, max_a: 16.4, max_b: 18.2, change: 0.06 },
        score_analysis: { win_rate_a: 0.48, win_rate_b: 0.56, change: 0.17 },
        problem_changes: { new: ['反手击球点偏晚'], resolved: ['发球抛球过高'], persistent: ['步法移动偏慢'] },
      },
    }),
  },
  // 全部技术指标趋势
  {
    method: 'GET',
    pattern: '/progress/technique-trends',
    data: {
      metrics: [
        {
          metric: 'loop_success_rate',
          metric_name: '正手拉冲成功率',
          current_value: 62,
          previous_value: 55,
          change_rate: 0.127,
          trend: 'up',
          target: 70,
          target_progress: 0.45,
          persistence_count: 3,
        },
      ],
    },
  },
  // 单项趋势详情（TrendDetail）
  {
    method: 'GET',
    pattern: '/progress/technique-trends/*',
    dynamic: ({ params }) => ({
      metric: params[0],
      metric_name: '正手拉冲成功率',
      current_value: 62,
      target_value: 70,
      target_progress: 0.45,
      trend: 'up',
      change_rate: 0.127,
      persistence_count: 3,
      history: [
        { date: '2026-10-20', value: 55 },
        { date: '2026-11-01', value: 58 },
        { date: '2026-11-08', value: 62 },
      ],
    }),
  },
]
