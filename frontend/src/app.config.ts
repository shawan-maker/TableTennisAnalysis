export default defineAppConfig({
  pages: [
    // ===== Tab Bar 页面（5，§3.4 统一配置）=====
    'pages/home/index',           // 首页 Tab
    'pages/training/index',       // 训练 Tab
    'pages/match/index',          // 赛事 Tab
    'pages/community/index',      // 社区 Tab（占位，Phase 2+）
    'pages/user/profile/index',   // 我的 Tab
    // ===== user 域（3）=====
    'pages/user/edit/index',           // 个人档案编辑
    'pages/user/big-data/index',       // 乒乓大数据
    'pages/user/rating-history/index', // 积分历史
    // ===== auth 域（2）=====
    'pages/auth/login/index',
    'pages/auth/consent/index',   // 隐私政策同意页（R21-P3-2 注册）
    // ===== video-analysis 域（4）=====
    'pages/video-analysis/upload/index',
    'pages/video-analysis/processing/index',
    'pages/video-analysis/report/index',
    'pages/video-analysis/list/index',        // 报告列表页
    // ===== dashboard 域（1）=====
    'pages/dashboard/index',
    // ===== match-data 域（4）=====
    'pages/match-data/quick-entry/index',
    'pages/match-data/detailed-entry/index', // 详细录入
    'pages/match-data/record-list/index',
    'pages/match-data/record-detail/index',
    // ===== scoring 域（4）=====
    'pages/scoring/setup/index',
    'pages/scoring/scoreboard/index',
    'pages/scoring/match-list/index',
    'pages/scoring/statistics/index',
    // ===== training 域（4，另有 training/index Tab 已注册）=====
    'pages/training/advice/index',
    'pages/training/plans/detail/index',      // 训练方案详情（注册表记法 pages/training/plans/[plan_id]/index，plan_id 经页面 query 传递）
    'pages/training/templates/index',
    'pages/training/templates/detail/index',
    // ===== progress 域（3）=====
    'pages/progress/comparison/index',
    'pages/progress/summary/index',
    'pages/progress/trend-detail/index',
    // ===== gamification 域（2）=====
    'pages/gamification/badges/index',
    'pages/gamification/checkin-calendar/index',  // 打卡日历页
    // ===== membership 域（1）=====
    'pages/membership/index',
    // ===== payment 域（2）=====
    'pages/payment/create/index',
    'pages/payment/orders/index',
    // ===== notification 域（1）=====
    'pages/notification/list/index',
    // ===== 公共页面（4）=====
    'pages/settings/index',       // 设置页
    'pages/settings/webview/index', // 协议 WebView 承载页（R-FE-R1 批次B FE-P2-21）
    'pages/onboarding/index',     // 新用户引导首页
    'pages/onboarding/profile/index', // 新用户资料填写页
  ],
  tabBar: {
    // FS8-7 WCAG AA：tabBar 文字色与全局 token 同步（H5 端 weui tabbar 同源）
    color: '#5A636B',
    selectedColor: '#C92738',
    backgroundColor: '#FFFFFF',
    borderStyle: 'white',
    list: [
      { pagePath: 'pages/home/index', text: '首页', iconPath: 'assets/tab/home.png', selectedIconPath: 'assets/tab/home-active.png' },
      { pagePath: 'pages/training/index', text: '训练', iconPath: 'assets/tab/training.png', selectedIconPath: 'assets/tab/training-active.png' },
      { pagePath: 'pages/match/index', text: '赛事', iconPath: 'assets/tab/match.png', selectedIconPath: 'assets/tab/match-active.png' },
      { pagePath: 'pages/community/index', text: '社区', iconPath: 'assets/tab/community.png', selectedIconPath: 'assets/tab/community-active.png' },
      { pagePath: 'pages/user/profile/index', text: '我的', iconPath: 'assets/tab/user.png', selectedIconPath: 'assets/tab/user-active.png' },
    ],
  },
  window: {
    backgroundTextStyle: 'dark',
    navigationBarBackgroundColor: '#FFFFFF',
    navigationBarTitleText: '乒乓智能分析',
    navigationBarTextStyle: 'black',
  },
})
