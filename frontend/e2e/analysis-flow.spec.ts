/**
 * E2E-01 新用户分析全流程（docs/07实施计划/02-测试计划.md §7.1）
 * 手机号登录（新用户）→ 隐私同意 → onboarding 跳过 → 上传视频 →
 * AI 分析进度 → 查看报告 → 训练建议（home AdviceBanner 入口）。
 *
 * 覆盖修复：FS8-P1-1——requires_consent=true 时同意页必须真实停留
 * （修复前 login 页无条件 switchTab home 会把 consent 页立即切走）。
 *
 * Mock 口径：REST 全拦截（本机无后端）；WS 不可达 → processing 页
 * useAnalysisProgress 的 5s REST 轮询对账兜底驱动 completed → 自动跳报告。
 */
import { test, expect } from '@playwright/test'
import { setup, loginByPhone } from './helpers/auth'
import { recordSampleVideo } from './helpers/record-video'
import type { MockRoute } from './helpers/mock-api'

const OSS_UPLOAD_URL = 'https://api.pingpongai.com/api/v1/mock-oss/videos/e2e-video.mp4'
const iso = () => new Date().toISOString()

/** 分析链路端点（upload-token → OSS 直传 → 确认 → 任务 → 轮询 → 报告） */
const analysisMocks: MockRoute[] = [
  // OSS 直传（PostObject 表单；E2E 复用 api 域以便 page.route 统一拦截）
  { method: 'POST', pattern: '/mock-oss/videos/*', data: {} },
  // STS 上传凭证（UploadTokenResult 镜像，service/videoAnalysis.ts 契约）
  {
    method: 'POST',
    pattern: '/video-analysis/upload-token',
    data: {
      file_id: 42,
      oss_key: 'videos/e2e-video.mp4',
      sts_credentials: {
        access_key_id: 'e2e-ak',
        access_key_secret: 'e2e-sk',
        security_token: 'e2e-sts-token',
        expiration: iso(),
        bucket: 'e2e-bucket',
        endpoint: 'https://oss.example.com',
      },
      upload_url: OSS_UPLOAD_URL,
      expire_at: iso(),
    },
  },
  { method: 'POST', pattern: '/video-analysis/upload-complete', data: { file_id: 42, status: 'uploaded' } },
  // 创建分析任务（CreateTaskResult 镜像）
  {
    method: 'POST',
    pattern: '/video-analysis/tasks',
    data: { task_id: 3, task_uuid: 'e2e-task-3', status: 'processing', estimated_wait_minutes: 2 },
  },
  // 任务详情：REST 轮询对账——首查 processing（进度条/步骤 UI），次查 completed
  //（自动 redirectTo 报告页，processing/index.tsx useEffect）
  {
    method: 'GET',
    pattern: '/video-analysis/tasks/*',
    dynamic: ({ params, callCount }) =>
      callCount === 1
        ? {
            task_id: Number(params[0]),
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
          }
        : {
            task_id: Number(params[0]),
            task_uuid: 'e2e-task-3',
            status: 'completed',
            current_step: 10,
            total_steps: 10,
            step_name: null,
            progress: 1,
            estimated_remaining_seconds: null,
            error_message: null,
            created_at: iso(),
            report_id: 7,
          },
  },
  // 报告详情（ReportDetail 镜像，stores/videoAnalysisStore.ts 契约）
  {
    method: 'GET',
    pattern: '/video-analysis/reports/*',
    data: {
      id: 7,
      task_id: 3,
      task_uuid: 'e2e-task-3',
      created_at: iso(),
      is_llm_generated: true,
      is_readonly: false,
      result_data: {
        video_info: { duration_sec: 125, fps: 30, resolution: '1920x1080' },
        rally_analysis: {
          total_rallies: 48,
          avg_rally_length: 5.2,
          max_rally_length: 12,
          // R-FE-R2 批次G（FE-P2-5）：节奏序列（报告页折线区块消费）
          rally_tempo: [8.2, 12.1, 6.4, 15.3, 9.8, 11.2, 7.5, 13.6, 10.4, 8.9, 12.8, 9.1, 14.2, 6.8, 11.5, 10.2, 7.9, 13.1, 9.6, 8.4],
        },
        landing_points: {
          nine_grid: [
            [2, 3, 1],
            [4, 8, 2],
            [3, 5, 2],
          ],
          distribution: { forehand: 0.6, backhand: 0.25, middle: 0.15 },
        },
        // R-FE-R2 批次G（FE-P1-3）：热图双源（对手侧九宫格）
        landing_heatmap: {
          nine_grid: [
            [2, 3, 1],
            [4, 8, 2],
            [3, 5, 2],
          ],
          opponent_nine_grid: [
            [3, 1, 2],
            [5, 2, 4],
            [2, 6, 1],
          ],
        },
        technique_stats: { loop: 30, smash: 12, push: 8, block: 10 },
        ball_speed: { avg_speed_mps: 12.5, max_speed_mps: 18.2, speed_range: [8.1, 18.2] },
        // R-FE-R2 批次G（FE-P2-6）：关键分带视频相对秒（marker seek 消费）
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
      annotated_video_url: 'https://cdn.test-videos.local/annotated.mp4',
      cover_image_url: null,
      report_images: null,
    },
  },
]

test('E2E-01 新用户分析全流程：登录→consent→上传→分析→报告→建议', async ({ page }) => {
  // 1-2. 新用户登录 + 隐私同意（requires_consent=true 分支）
  await setup(page, analysisMocks, { requiresConsent: true })
  await loginByPhone(page)
  // FS8-P1-1：同意页必须真实停留（修复前被 switchTab home 覆盖）
  await page.waitForURL(/\/pages\/auth\/consent\/index/, { timeout: 10000 })
  // 标题在 Taro 导航栏 + 页面内各出现一次，断言页面内（#app）实例
  await expect(page.locator('#app').getByText('隐私政策同意')).toBeVisible()
  await page.getByRole('button', { name: '同意并继续' }).click()

  // 3. 进入首页 → 新用户 onboarding 弹窗 → 跳过引导
  await expect(page.getByText('欢迎来到乒乓AI')).toBeVisible({ timeout: 15000 })
  await page.getByText('跳过引导').click()
  // 跳过仅标记完成（设计如此，无自动返回）→ 模拟用户返回首页
  await page.goBack()
  await expect(page.getByText('快捷操作')).toBeVisible({ timeout: 10000 })

  // 4. 快捷宫格 AI分析 → 上传页（额度提示可见，R15-VA-N1 会员守卫展示层）
  await page.getByText('AI分析').first().click()
  await expect(page.getByText('拍摄引导')).toBeVisible({ timeout: 10000 })
  await expect(page.getByText('免费用户每日可分析 3 次，会员无限分析')).toBeVisible()

  // 5. 选择/拍摄视频 → STS 直传 → 确认 → 创建任务
  //（Taro H5 loadMedia 真实解析视频元数据，须喂真实 webm——helpers/record-video）
  const sample = await recordSampleVideo(page)
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: '选择/拍摄视频' }).click()
  const chooser = await chooserPromise
  await chooser.setFiles({
    name: sample.name,
    mimeType: sample.mimeType,
    buffer: sample.buffer,
  })

  // 6. 创建成功 → 跳转进度页（upload/index.tsx redirectTo）
  await page.waitForURL(/task_id=3/, { timeout: 15000 })
  // 7. 进度页：processing 态（首查 progress 0.35 → 步骤/进度 UI）
  await expect(page.getByText('AI 正在分析你的视频...')).toBeVisible({ timeout: 10000 })

  // 8. 轮询对账 completed（5s 兜底）→ 自动跳报告页
  await page.waitForURL(/report_id=7/, { timeout: 25000 })

  // 9. 报告页：核心指标 + 落点热图 + 技术分布 + 球速 + 结论
  await expect(page.getByText('总板数')).toBeVisible({ timeout: 10000 })
  // 48 会子串误中九宫格数字拼串（"2 3 1 4 8..."），断言收紧到指标卡
  await expect(page.locator('.data-value').filter({ hasText: /^48$/ })).toBeVisible()
  await expect(page.getByText('落点分布')).toBeVisible()
  await expect(page.getByText('技术动作分布')).toBeVisible()
  await expect(page.getByText('击球球速')).toBeVisible()
  await expect(page.getByText('分析结论')).toBeVisible()
  // issues[0] 同时渲染进 technique-hint（§4.3 设计）→ 断言收紧到结论列表项
  await expect(page.locator('.issue-item').filter({ hasText: '反手击球点偏晚' })).toBeVisible()
  await expect(
    page.locator('.suggestion-item').filter({ hasText: '加强反手推挡多球训练' })
  ).toBeVisible()

  // R-FE-R2 批次G（FE-P2-5）：节奏曲线区块渲染
  await expect(page.getByText('回合节奏曲线')).toBeVisible()
  await expect(page.locator('.tempo-segment').first()).toBeVisible()

  // R-FE-R2 批次G（FE-P1-3）：对手落点 toggle 切换（对手 grid 无 8 值，切换后消失）
  await expect(page.locator('.cell-value').filter({ hasText: /^8$/ })).toHaveCount(1)
  await page.getByText('对手落点').click()
  await expect(page.locator('.toggle-btn.active')).toHaveText(/对手落点/)
  await expect(page.locator('.cell-value').filter({ hasText: /^8$/ })).toHaveCount(0)

  // R-FE-R2 批次G（FE-P2-6）：关键分 marker 渲染 + 点击 seek（无崩溃即通过）
  await expect(page.locator('.keypoint-chip').filter({ hasText: '10:10' })).toBeVisible()
  await page.locator('.keypoint-chip').filter({ hasText: '10:10' }).click()

  // 10. 返回首页 → 训练提醒横幅（latest_advice_summary）→ 训练建议页
  await page.goBack()
  await expect(page.getByText('加强正手拉冲练习')).toBeVisible({ timeout: 10000 })
  await page.getByText('加强正手拉冲练习').click()
  // R-FE-R1（FE-P1-7）：报告页驻留 DOM 新增「查看训练建议」按钮，子串会双命中
  // （Taro H5 页栈 DOM 驻留），收紧 exact 只匹配建议页 page-title
  await expect(page.getByText('训练建议', { exact: true })).toBeVisible({ timeout: 10000 })
  // 4 类建议（diagnosis/suggestions/methods/template，字段镜像 services/training.ts）
  await expect(page.getByText('正手击球点偏晚')).toBeVisible()
  await expect(page.getByText('正手拉冲多球训练：每组 30 球，共 3 组，固定高点期击球')).toBeVisible()
  // 「多球训练」同时子串命中 suggestion 文案 → 断言收紧到方法名节点
  await expect(page.locator('.method-name').filter({ hasText: '多球训练' })).toBeVisible()
})
