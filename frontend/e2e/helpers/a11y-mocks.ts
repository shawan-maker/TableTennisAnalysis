/**
 * FS8-7 axe 扫描补充 mocks（39 页真实内容态）
 *
 * baseMocks 覆盖通用首屏端点；本文件补齐扫描时渲染空态的页面主端点，
 * 载荷与前端 service 镜像的后端 schema 逐字一致：
 * - /users/big-data            userStore.BigData
 * - /users/rating-history      RatingHistoryItem 分页
 * - /video-analysis/tasks/3    TaskDetail（processing 态，扫描进度 UI 真实内容）
 * - /video-analysis/reports/7  ReportDetail（载荷与 E2E-01 同源；唯一刻意差异
 *   annotated_video_url=null——video 无 track 触发 axe video-caption，见 payload 注。
 *   R2-P3-22 批次I：score_analysis 已补齐镜像，video-section/marker chips 为
 *   已知 a11y 盲区，差异口径与 analysis-flow 双侧留痕〔R2-P3-23〕）
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
        rally_analysis: {
          total_rallies: 48,
          avg_rally_length: 5.2,
          max_rally_length: 12,
          // R-FE-R2 批次G（FE-P2-5）：节奏序列（a11y 扫描折线区块渲染）
          rally_tempo: [8.2, 12.1, 6.4, 15.3, 9.8, 11.2, 7.5, 13.6, 10.4, 8.9, 12.8, 9.1, 14.2, 6.8, 11.5, 10.2, 7.9, 13.1, 9.6, 8.4],
        },
        landing_points: {
          nine_grid: [[2, 3, 1], [4, 8, 2], [3, 5, 2]],
          distribution: { forehand: 0.6, backhand: 0.25, middle: 0.15 },
        },
        // R-FE-R2 批次G（FE-P1-3）：对手侧九宫格（a11y 扫描 toggle 渲染；
        // annotated_video_url 保持 null——video 无 track 会触发 axe video-caption）
        landing_heatmap: {
          nine_grid: [[2, 3, 1], [4, 8, 2], [3, 5, 2]],
          opponent_nine_grid: [[3, 1, 2], [5, 2, 4], [2, 6, 1]],
        },
        // R2-P3-4（批次I）：键集对齐 API §4.6（forehand_drive 等，analysis-flow 同源）
        technique_stats: { forehand_drive: 45, backhand_drive: 18, forehand_loop: 12, serve: 23 },
        // R3-P3-7：dashboard 兼容段镜像后端下发（ai_pipeline/report_generator.py:155-160
        // —technique_distribution 与 technique_stats 同值、metrics 三落点键取
        // landing_points.distribution 值；报告页不消费，前向交付保真）
        technique_distribution: { forehand_drive: 45, backhand_drive: 18, forehand_loop: 12, serve: 23 },
        metrics: { landing_forehand_pct: 0.6, landing_backhand_pct: 0.25, landing_middle_pct: 0.15 },
        ball_speed: { avg_speed_mps: 12.5, max_speed_mps: 18.2, speed_range: [8.1, 18.2] },
        // R2-P3-22（批次I）：补 score_analysis 段（E2E-01 同源）——annotated_video_url
        // 保持 null（防 axe video-caption），video-section（含关键分 marker chips）仍
        // 不入扫描：已知 a11y 盲区，chips 交互正确性由 analysis-flow 真 URL 流程覆盖
        // （E2E-01 marker 点击断言）；差异口径双侧留痕见 analysis-flow.spec.ts 对称注记
        score_analysis: {
          final_score: '11:8',
          key_points: [
            { seq: 20, score: '10:10', winner: 'user', timestamp: 95.4 },
            { seq: 23, score: '11:10', winner: 'opponent', timestamp: 112.8 },
          ],
        },
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
      // R3-P3-6：批次G 字段回显（schemas/scoring.py:86 + scoring_service.py:213
      // —MatchDetail 下发 opponent_playing_style；取值 Literal 四枚举之一，
      // detail 页渲染零消费为前向交付，mock 补齐保真）
      opponent_playing_style: 'loop_drive',
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
          // R3-P2-1：loop_success_rate 为臆造键（后端 METRIC_DEFINITIONS 18 键
          // 无此键，progress_service.py:28-47），改真实键 backhand_ratio——
          // summary 页 t(`progress.metric.${key}`) 渲染，值口径为比率 0-1
          metric: 'backhand_ratio',
          metric_name: '反手使用率',
          current_value: 0.32,
          previous_value: 0.28,
          change_rate: 0.143,
          trend: 'up',
          target: 0.35,
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
        goal_completion: { backhand_ratio: '45%' },
      },
      forecast: { backhand_ratio: { predicted_weeks_to_target: 4, confidence: 'medium', r_squared: 0.72 } },
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
          // Round 4 复审（R2-P3-4 谱系）：键集对齐后端 comparison 契约
          // progress_service.py:516（forehand_ratio/backhand_ratio/serve_ratio）——
          // 原 loop/smash 为臆造键，前端 t(`progress.metric.${key}`) 查无此键
          // 回退渲染裸键名（i18nKeys.test:189 保障的真实键集此前 mock 未提供）
          forehand_ratio: { a: 25, b: 30, change: 0.2 },
          backhand_ratio: { a: 10, b: 12, change: 0.2 },
          serve_ratio: { a: 8, b: 9, change: 0.12 },
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
          // R3-P2-1：臆造键 loop_success_rate → 真实键 backhand_ratio（同 summary）
          metric: 'backhand_ratio',
          metric_name: '反手使用率',
          current_value: 0.32,
          previous_value: 0.28,
          change_rate: 0.143,
          trend: 'up',
          target: 0.35,
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
    // R3-P2-1：未知 metric 镜像后端 40415 分支（progress_service.py:409-410
    // AppException("指标不存在", 404, code=40415)）——a11y 补扫错误分支
    // （修复前 spec 参数用臆造键 loop_success_rate，mock 恒返回成功体，
    // 40415 错误态 render 零 axe 覆盖）
    statusFn: ({ params }) =>
      ['backhand_ratio', 'forehand_ratio', 'serve_ratio'].includes(params[0]) ? 200 : 404,
    envelopeCode: 40415,
    errorMessage: '指标不存在',
    dynamic: ({ params }) => ({
      metric: params[0],
      metric_name: '反手使用率',
      current_value: 0.32,
      target_value: 0.35,
      target_progress: 0.45,
      trend: 'up',
      change_rate: 0.143,
      persistence_count: 3,
      history: [
        { date: '2026-10-20', value: 0.28 },
        { date: '2026-11-01', value: 0.3 },
        { date: '2026-11-08', value: 0.32 },
      ],
    }),
  },
]
