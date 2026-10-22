# 乒乓智能分析平台 — 系统架构设计

> **版本**：v2.1
> **日期**：2026-10-09
> **依据**：需求分析与路线图 v0.4、前端需求与界面设计 v2.0、Phase 0 技术预研汇总报告、架构文档差距分析报告
> **团队约束**：个人开发 + AI 辅助 → 架构极简化，最大化云服务，最小化运维
> **v2.0 变更**：根据差距分析报告修复 7 个关键缺失、8 个规格不足、5 个命名不一致
> **v2.1 变更**：补充跨端落地策略（小程序优先 + H5 降级），明确小程序能力边界和分包方案

---

## 1. 项目概述

### 1.1 系统定位

- **产品名称**：乒乓智能分析平台 / PingPongAI
- **一句话定位**：面向中国乒乓球爱好者的 AI 驱动训练分析平台，覆盖视频智能分析、3D 数字人物教学、数据看板、赛事社区全流程
- **目标用户规模**：Phase 1 验证 1000+ 注册用户，中长期 10 万+ 活跃用户
- **核心壁垒**：数据飞轮（用户上传视频 → AI 分析 → 用户反馈 → 标注数据 → 模型 fine-tune → 精度提升 → 更多用户上传）

### 1.2 核心用户角色

| 角色 | 权限范围 | 典型操作 |
|------|---------|---------|
| 游客 | 公开浏览 | 查看社区公开内容、球馆搜索 |
| 免费用户 | 基础功能 | 每日 3 次 AI 分析、记分牌、手动数据录入、数据看板、社区浏览 |
| 会员用户 | 会员权益 | 无限 AI 分析、训练方案、训练单、3D 教学、历史对比 |
| 专业用户 | 专业权益 | 高级分析、对手建模、月度报告 |
| 教练用户 | 教练权益 | 学员管理、批量分析、教练工具、线上指导服务 |
| 创作者 | 内容管理 | 上传教学视频、定价、收益管理 |
| 管理员 | 全局管理 | 内容审核、用户管理、系统配置、模型管理 |

### 1.3 系统边界

| 范围内（In Scope） | 范围外（Out of Scope） |
|-------------------|----------------------|
| 微信小程序 + iOS/Android App 跨平台客户端 | PC Web 端（Phase 5 可选） |
| AI 视频分析（球体检测/追踪/落点/动作识别） | 实时视频流分析（仅支持离线视频） |
| 3D 数字人物动作教学（Three.js 渲染） | VR/AR 沉浸式训练 |
| 智能记分牌 + 比赛数据管理 | 球馆 IoT 固定摄像头方案（Phase 5） |
| 训练方案 + 训练单生成与跟练 | 可穿戴设备数据同步（Phase 5） |
| 社区（动态/学习视频/问答/圈子/排行榜） | 直播功能 |
| 赛事报名 + 积分排名（对接开球网） | 赛事直播/转播 |
| 同城约球 + 球馆搜索 + 地图导航 | 球馆在线订场 SaaS（Phase 5 扩展） |
| 装备评测 + 电商导购 | 自营仓储物流 |
| 创作者经济（UGC 视频上传/定价/分成） | 第三方支付（仅微信支付） |
| 信用分体系 | — |
| 微信支付集成 | 支付宝/银联（暂不支持） |
| 乒乓球专业知识库 + 规则引擎 | 通用体育分析（仅乒乓球） |
| 数据飞轮（用户反馈 → 模型优化） | 自动化模型训练平台（使用半自动流程） |

---

## 2. 技术栈选型表

> **Anti-hallucination**: 以下版本号为本项目确定使用的版本，新增技术时必须填写选型理由。

### 2.1 前端技术栈

| 层 | 技术 | 版本 | 选型理由 |
|----|------|------|---------|
| 跨平台框架 | **Taro 4** | 4.x | React 语法体系，一套代码编译微信小程序 / H5 / React Native App；与 React Three Fiber 生态对齐，京东系维护活跃 |
| UI 框架 | NutUI React | 4.x | 京东出品，Taro 官方推荐 UI 库，移动端组件丰富 |
| 3D 渲染引擎 | Three.js + React Three Fiber | 0.168+ / 8.x | Phase 0 确认：轻量 ~500KB，R3F 声明式编程；小程序端使用 threejs-miniprogram 适配 |
| 3D 辅助库 | @react-three/drei | 9.x | useGLTF / OrbitControls / Environment 等高质量组件 |
| 3D 模型压缩 | Draco | — | GLB 模型 Draco 压缩 ≤2MB，首屏 ≤3 秒 |
| 状态管理 | Zustand | 5.x | 轻量、无 boilerplate、TypeScript 友好，比 Redux 简洁 |
| HTTP 客户端 | Taro.request 封装 | — | 跨平台请求统一，拦截器 + token 自动刷新 |
| 图表库 | ECharts (taro-echarts) | 5.x | 丰富的图表类型（热力图/环形图/折线图），小程序兼容 |
| 地图 SDK | 高德地图 JS SDK | 2.x | 需求文档指定高德地图，球馆搜索/导航/约球 LBS |
| 富文本编辑 | wangeditor | 5.x | 社区动态/技术问答内容编辑 |
| 视频播放 | video.js + Taro Video 组件 | 7.x | H5 端 video.js（支持慢放/逐帧），小程序端原生 Video 组件 |
| 国际化 | i18next | 23.x | Phase 5 国际化预留，初期仅中文 |

### 2.2 跨平台方案选型决策

> **决策结论：选择 Taro 4（React 体系），排除 uni-app（Vue 体系）。**

| 维度 | Taro 4 (React) | uni-app (Vue) | 决策依据 |
|------|---------------|--------------|---------|
| 3D 生态对齐 | ✅ React Three Fiber 原生支持 | ❌ Vue 3D 生态弱（TresJS 不成熟） | Phase 0 确定 R3F，Taro 与之天然对齐 |
| 小程序 3D 适配 | ✅ threejs-miniprogram 适配版 | ✅ 同样支持 | 两者均可，但 Taro 更好封装 |
| App 渲染层 | React Native + WebView（3D 用 H5） | nvue/Weex + WebView | RN 生态更大，WebView 方案两者一致 |
| 一码多端 | 微信小程序 + H5 + RN App | 微信小程序 + H5 + App | 均满足，Taro 编译产物更标准 |
| TypeScript 支持 | ✅ 原生支持 | ✅ 原生支持 | 两者均满足 |
| 维护活跃度 | 京东团队，持续更新 | DCloud，持续更新 | 两者均活跃 |
| 社区规模 | GitHub 35k+ star | GitHub 40k+ star | 两者均成熟 |

**3D 跨端策略**：

| 平台 | 3D 渲染方案 | 说明 |
|------|-----------|------|
| 微信小程序 | threejs-miniprogram（基于 Three.js 0.108 定制） | 小程序 WebGL 适配，体积减少 40% |
| App（iOS/Android） | React Native WebView 嵌入 H5 + React Three Fiber | WebView 渲染 WebGL，性能可达 30-60fps |
| H5 | React Three Fiber + @react-three/drei | 完整 R3F 生态，最佳开发体验 |

> 3D 核心场景逻辑（模型加载、动画播放、OrbitControls）封装为平台无关的 Three.js 模块，各端通过薄适配层调用，减少代码重复。

### 2.3 后端技术栈

| 层 | 技术 | 版本 | 选型理由 |
|----|------|------|---------|
| Web 框架 | **FastAPI** | 0.110+ | 异步原生、自动 OpenAPI 文档、Pydantic 校验；与 AI/ML Python 生态统一语言 |
| ASGI 服务器 | Uvicorn + Gunicorn | 0.30+ / 22+ | 生产级 ASGI 部署，多 worker 进程管理 |
| ORM | **SQLAlchemy 2.0 (async)** | 2.0+ | 最成熟 Python ORM，async 支持，GeoAlchemy2 扩展支持 PostGIS 地理查询 |
| 数据库 | **PostgreSQL** | 15+ | JSONB 存储分析结果/知识库；PostGIS 支持 LBS 查询（约球/球馆/赛事）；ACID 保证支付/记分 |
| 地理扩展 | GeoAlchemy2 | 0.14+ | PostGIS ORM 封装，球馆/约球空间查询 |
| 迁移工具 | Alembic | 1.13+ | SQLAlchemy 官方迁移工具 |
| 缓存 | **Redis** | 7+ | 任务队列、会话管理、限流、排行榜 ZSET |
| 任务队列 | **Celery + Redis** | 5.3+ | AI 视频分析异步流水线，进度追踪 |
| 对象存储 | 阿里云 OSS / 腾讯云 COS | — | 视频文件、3D 模型、用户头像、分析报告图片 |
| CDN | 阿里云 CDN / 腾讯云 CDN | — | 视频分发、3D 模型加速、静态资源加速 |
| 认证 | python-jose + passlib(bcrypt) | — | JWT access+refresh token，微信登录 + 手机号登录 |
| 支付 | 微信支付 SDK (wechatpayv3) | — | 微信支付 JSAPI（小程序）/ APP 支付 |
| LLM 集成 | httpx (async) | — | OpenAI 兼容 API 调用，报告生成/训练建议 |

### 2.4 AI 推理服务技术栈

> AI 推理服务独立部署在 GPU 实例上，与主业务服务分离。

| 层 | 技术 | 版本 | 选型理由 |
|----|------|------|---------|
| 推理服务框架 | FastAPI + uvicorn | 0.110+ | 与主服务统一技术栈，HTTP API 对外暴露 |
| 深度学习框架 | **PyTorch** | 2.2+ | TTNet/TrackNet 均为 PyTorch 实现，生态统一 |
| 球体检测模型 | **TTNet / TrackNetV5** | — | Phase 0 确认：专为乒乓球设计，heatmap 检测，非通用 YOLO |
| 球体追踪 | 卡尔曼滤波 + 抛物线物理模型 | filterpy | Phase 0 确认：DeepSORT 不适用（为行人设计，球体外观单一） |
| 球台检测 | YOLO-pose + OpenCV 单应性矩阵 | ultralytics 8.x | 关键点检测球台四角 + 透视变换映射落点 |
| 人体姿态 | **MediaPipe** | 0.10+ | Phase 0 确认：轻量，适合移动端视频，2D 姿态提取 |
| 动作识别 | **Temporal CNN (2D 姿态序列)** | PyTorch | Phase 0 确认：99.37% 准确率（有论文验证） |
| 视频处理 | FFmpeg + OpenCV | 4.x / 4.9+ | 视频转码、帧提取、标注视频生成 |
| GPU 实例 | 阿里云 GN7i / 腾讯云 GN10X (T4) | — | Phase 0 确认：T4 实例 ~1.87 元/小时，按需调用 |
| 模型管理 | MLflow (可选) | — | 模型版本管理、A/B 测试（Phase 2+ 引入） |

### 2.5 3D 内容生产技术栈

| 层 | 技术 | 版本 | 选型理由 |
|----|------|------|---------|
| 3D 建模 | Blender | 4.x | 免费、开源、Python 脚本自动化 |
| 角色模型生成 | ReadyPlayerMe | — | 免费 GLB 角色生成，版权风险极低 |
| 动画制作 | Blender 关键帧动画 | — | 乒乓球专项无现成资源，自主制作 6+ 关键姿势/动作 |
| 模型导出 | glTF 2.0 + Draco 压缩 | — | 跨平台 3D 格式标准，Draco 压缩 ≤2MB |

### 2.6 基础设施

| 层 | 技术 | 说明 |
|----|------|------|
| 容器化 | Docker + Docker Compose | 开发/测试/生产统一环境 |
| CI/CD | GitHub Actions | 自动构建、测试、部署 |
| 进程管理 | Supervisor / systemd | Uvicorn worker + Celery worker 进程管理 |
| 日志 | Python logging + 阿里云 SLS | 结构化日志，集中查询 |
| 监控 | 阿里云云监控 / Prometheus | 服务健康、GPU 利用率、队列积压监控 |
| 域名/SSL | 阿里云域名 + Let's Encrypt | HTTPS 强制 |

### 2.7 关键选型补充说明

#### 放弃微信云开发的理由

需求 v0.4 提到"微信云开发（小程序端）+ 独立云服务（App端）"，架构最终选择**统一 FastAPI 后端**，放弃微信云开发。

| 维度 | 微信云开发 + 独立云服务（双后端） | 统一 FastAPI 后端（本方案） |
|------|-------------------------------|------------------------|
| 后端维护数 | 2 套（云函数 + FastAPI） | 1 套（FastAPI） |
| 业务逻辑同步 | 需在两套后端间同步，易出错 | 统一一份，无同步问题 |
| AI 集成 | 云函数不支持 GPU 推理，仍需独立 AI 服务 | 统一调用 AI 推理服务 |
| 数据一致性 | 云开发数据库与 PostgreSQL 数据同步复杂 | 统一 PostgreSQL |
| 个人开发效率 | 双后端维护成本翻倍 | 单后端，效率最大化 |
| 小程序适配 | 云开发天然支持 | FastAPI 通过 HTTP API 对接小程序，无障碍 |

> **结论**：个人开发场景下，维护双后端是不可承受的成本。FastAPI 统一后端通过 HTTP API 服务小程序和 App，微信云开发不提供不可替代的能力。

#### 排除 MongoDB 的理由

需求 v0.4 提到"MongoDB / PostgreSQL"，架构最终选择 **PostgreSQL**。

| 维度 | MongoDB | PostgreSQL（本方案） |
|------|---------|-------------------|
| JSON 存储 | 原生文档数据库 | JSONB 字段，功能等价且支持索引 |
| ACID 事务 | 4.0+ 支持多文档事务，但复杂 | 成熟 ACID，支付/记分场景必须 |
| 地理查询 | 2dsphere 索引，功能基本 | PostGIS，功能更强、生态更成熟 |
| 关系查询 | 不擅长 JOIN | 原生关系查询，赛事/订单/积分场景必需 |
| ORM 支持 | Motor/Odmantic（异步但不成熟） | SQLAlchemy 2.0 async（最成熟） |
| 团队熟悉度 | 一般 | 更通用，文档/社区更丰富 |

> **结论**：PostgreSQL 的 JSONB 已满足 JSON 存储需求，同时提供 ACID 事务（支付/记分）、PostGIS（LBS 查询）、成熟关系查询（赛事/订单/积分），无需引入 MongoDB 增加运维复杂度。

### 2.8 跨端落地策略：小程序优先 + H5 降级

> **决策结论**：Phase 1 优先上线微信小程序（覆盖 ~83% 功能），重功能通过 web-view 嵌入 H5 页面降级处理；Phase 2+ 补充 App（React Native）实现完整体验。H5 降级页面复用 Taro H5 编译产物，不额外开发。

#### 落地策略总览

```
┌─────────────────────────────────────────────────────────┐
│                    Taro 4 一套代码                        │
│              (React + TypeScript 体系)                    │
└──────────┬──────────────┬──────────────┬────────────────┘
           │              │              │
    ┌──────▼──────┐ ┌────▼─────┐ ┌──────▼───────┐
    │  微信小程序   │ │   H5     │ │  App (RN)    │
    │  (Phase 1)  │ │ (降级页)  │ │ (Phase 2+)   │
    │  83% 功能    │ │ 17% 降级  │ │ 100% 功能    │
    └──────┬──────┘ └────┬─────┘ └──────────────┘
           │              │
           │    ┌─────────┘
           │    │
    ┌──────▼────▼────┐
    │ web-view 组件   │
    │ 嵌入 H5 降级页  │
    │ (Token 认证透传) │
    └────────────────┘
```

| 端 | 角色 | 上线阶段 | 功能覆盖率 | 说明 |
|----|------|---------|-----------|------|
| 微信小程序 | **主入口** | Phase 1 | ~83% | 5 Tab + 分包加载，重功能跳转 H5 |
| H5 | **降级补充** | Phase 1（随小程序上线） | 17% 降级功能 | 复用 Taro H5 编译，web-view 嵌入 |
| App (iOS/Android) | **完整体验** | Phase 2+ | 100% | React Native 编译，iOS/Android 一套代码 |

#### 小程序硬限制与影响

| 限制项 | 具体约束 | 对本项目的直接影响 |
|--------|---------|-------------------|
| 包体大小 | 主包 ≤2MB，分包总计 ≤20MB | 45 页面 + ECharts + 组件库，不分包会超限 |
| 视频选择 | wx.chooseMedia 限制时长 ≤60s，压缩后 ≤10MB | AI 分析需 30-180s 原始视频，压缩后画质不足 |
| WebGL | threejs-miniprogram 基于 Three.js 0.108（旧版） | 3D 教学复杂交互（逐帧/crossFade）受限 |
| iframe | 小程序不支持原生 iframe | 嵌入式教学视频（B站/抖音）无法直接播放 |
| 富文本编辑 | 无成熟富文本编辑器组件 | 社区图文动态发布受限 |
| 文件上传 | 不支持大文件直传 | 视频文件 100-500MB 无法处理 |
| 后台运行 | 小程序不能后台持续运行 | 视频分析进度需 WebSocket + 微信通知补偿 |

#### 逐 Phase 功能可行性矩阵

**Phase 1（14 页）— 小程序覆盖率 93%**

| 功能 | 小程序原生 | H5 降级 | 说明 |
|------|:---------:|:-------:|------|
| 首页 Dashboard | ✅ | — | 数据卡片 + 打卡日历 + 快捷入口 |
| 记分牌（设置/实时/统计） | ✅ | — | wx.connectSocket 支持实时同步 |
| 数据看板 | ✅ | — | taro-echarts 支持热力图/折线图/环形图 |
| 比赛数据手动录入 | ✅ | — | 表单录入，无限制 |
| 训练建议 | ✅ | — | 文字 + 模板展示 |
| 游戏化（积分/打卡/徽章） | ✅ | — | 完全支持 |
| 会员中心 + 微信支付 | ✅ | — | 微信支付 JSAPI 原生支持 |
| 个人档案 + 乒乓大数据 | ✅ | — | 表单 + 数据卡片 |
| 分析报告查看 | ✅ | — | ECharts 图表 + 视频回放 |
| **视频上传 → AI 分析** | ❌ | **H5** | 大文件上传受限，需 H5 页面处理 |

**Phase 2（8 页）— 小程序覆盖率 75%**

| 功能 | 小程序原生 | H5 降级 | 说明 |
|------|:---------:|:-------:|------|
| 高级分析报告 | ✅ | — | 图表展示 |
| 训练方案 + 训练单 | ✅ | — | 文字 + 计划展示 |
| 训练单跟练 | ✅ | — | 计时器 + 内容清单 |
| 月度训练报告 | ✅ | — | 图表 + 趋势 |
| 徽章/成就 | ✅ | — | 图标展示 |
| 对手分析/Scout 报告 | ✅ | — | 图表 + 数据 |
| **3D 教学查看器** | ⚠️ 受限 | **H5** | threejs-miniprogram 旧版，复杂交互受限 |
| **视频 vs 3D 对比分析** | ❌ | **H5** | 需视频上传 + 3D 渲染 |

**Phase 3（12 页）— 小程序覆盖率 67%**

| 功能 | 小程序原生 | H5 降级 | 说明 |
|------|:---------:|:-------:|------|
| 社区信息流（浏览） | ✅ | — | 列表 + 图片展示 |
| 帖子详情（浏览） | ✅ | — | 图文 + 评论展示 |
| **发布动态（图文编辑）** | ⚠️ 受限 | **H5** | 富文本编辑器受限 |
| 技术问答（浏览/回答） | ✅ | — | Markdown 级文本可支持 |
| 学习视频库（浏览） | ✅ | — | 列表 + 缩略图 |
| **学习视频播放 + 跟练** | ⚠️ 受限 | **H5** | 慢放/逐帧/技术要点同步受限 |
| **嵌入视频（B站等）** | ❌ | **H5** | 小程序不支持 iframe |
| 创作者数据概览 | ✅ | — | 图表 |
| **创作者上传视频** | ❌ | **H5** | 大文件上传 |
| 约球（列表/详情/发布） | ✅ | — | LBS + 表单 |
| 球馆搜索（地图/列表） | ✅ | — | wx 地图组件支持 |
| 教练列表/详情/预约 | ✅ | — | 列表 + 表单 |
| 排行榜 | ✅ | — | ZSET + 列表 |
| 圈子/话题 | ✅ | — | 列表 + 详情 |

**Phase 4（8 页）— 小程序覆盖率 100%**

| 功能 | 小程序原生 | H5 降级 | 说明 |
|------|:---------:|:-------:|------|
| 赛事列表/详情/报名 | ✅ | — | 列表 + 微信支付 |
| 积分排名 | ✅ | — | 列表 |
| 活动组织 + 智能组队 | ✅ | — | 表单 + 算法计算 |
| 地图导航 | ✅ | — | wx.openLocation |
| 装备评测/商城 | ✅ | — | 列表 + 微信支付 |
| 订单管理 | ✅ | — | 列表 + 状态 |
| 信用分 | ✅ | — | 分数 + 记录 |

**汇总**

| Phase | 总页面 | 小程序原生 | H5 降级 | 覆盖率 |
|-------|--------|-----------|---------|--------|
| Phase 1 | 14 | 13 | 1 | 93% |
| Phase 2 | 8 | 6 | 2 | 75% |
| Phase 3 | 12 | 8 | 4 | 67% |
| Phase 4 | 8 | 8 | 0 | 100% |
| **合计** | **42** | **35** | **7** | **83%** |

#### H5 降级技术实现

> **核心优势**：H5 降级页面复用 Taro H5 编译产物，**不需要额外开发**。同一个 React 组件在小程序端用原生组件渲染，在 H5 端用 DOM 渲染，功能天然完整。

**降级流程**：

```mermaid
sequenceDiagram
    participant MP as 小程序
    participant WV as web-view 组件
    participant H5 as H5 页面
    participant B as 后端

    MP->>MP: 用户点击"上传分析"等重功能
    MP->>B: GET /api/v1/auth/h5-token (JWT → 临时 token)
    B-->>MP: {token: "xxx", expire: 300s}
    MP->>WV: wx.navigateTo web-view 页面
    WV->>H5: 加载 https://h5.pingpongai.com/upload?token=xxx
    H5->>B: POST /api/v1/auth/h5-exchange {token} → JWT
    B-->>H5: {access_token}
    H5->>H5: 正常功能（大文件上传 / 3D 渲染 / 富文本编辑）
    H5->>WV: postMessage({action: "complete", result: {...}})
    WV->>MP: wx.miniProgram.postMessage → 触发回调
    MP->>MP: navigateBack + 刷新数据
```

**H5 降级页面清单（全 Phase）**

| 降级页面 | H5 功能 | 触发条件 | 上线阶段 |
|---------|---------|---------|---------|
| 视频上传页 | 大文件 OSS 直传 + 任务创建 | 用户点击"上传分析" | Phase 1 |
| 3D 教学查看器 | React Three Fiber 完整渲染 + 交互 | 用户进入 3D 教学 | Phase 2 |
| 视频 vs 3D 对比 | 视频上传 + 3D 渲染 + 并排/叠加 | 用户点击"对比分析" | Phase 2 |
| 社区动态发布 | 富文本编辑器 + 图片/视频附件 | 用户点击"发布动态" | Phase 3 |
| 学习视频播放器 | video.js 慢放/逐帧/跟练 | 用户点击"跟练模式" | Phase 3 |
| 嵌入视频播放 | iframe 嵌入第三方播放器 | 用户点击嵌入视频 | Phase 3 |
| 创作者视频上传 | 大文件上传 + 信息填写 + 定价 | 创作者点击"上传视频" | Phase 3 |

> **认证透传**：小程序 → 后端获取一次性 H5 Token（5 分钟过期）→ H5 页面用 Token 换 JWT → H5 内完成操作 → postMessage 通知小程序返回。Token 一次性使用，防止泄露。

#### 小程序分包策略

```
主包 (≤2MB):
  ├── 5 个 Tab 页（首页/训练/赛事/社区/我的）
  ├── 认证页面（微信登录/手机登录）
  ├── 公共组件（导航栏/卡片/按钮/空状态/骨架屏）
  └── 核心工具（request 封装/websocket/upload 封装）

分包1: training-sub (≤2MB)
  ├── 视频分析（拍摄引导/处理中/报告页）
  ├── 数据看板
  └── 训练方案

分包2: events-sub (≤2MB)
  ├── 记分牌（设置/实时/统计）
  ├── 赛事列表/详情/报名
  └── 约球/球馆搜索

分包3: community-sub (≤2MB)
  ├── 社区信息流
  ├── 帖子详情
  └── 创作者中心概览

分包4: profile-sub (≤2MB)
  ├── 会员中心
  ├── 装备配置/评测
  └── 订单管理

web-view 容器页 (主包):
  └── 通用 web-view 组件，src 由参数动态传入
```

> **体积控制**：总计 ≤8MB（4 个分包各 2MB + 主包 2MB），远在 20MB 限制内。ECharts 按需引入（仅热力图/折线图/环形图模块），NutUI 组件 Tree-shaking 裁剪。Phase 3/4 新增页面继续按 Tab 分包，每个分包有 2MB 余量。

#### App（React Native）路线图

| 阶段 | App 状态 | 说明 |
|------|---------|------|
| Phase 1 | ❌ 不上线 | 资源集中在小程序 + H5 降级 |
| Phase 2 | ⚠️ 可选启动 | 3D 教学需求驱动，App 提供 3D 原生渲染（React Native WebView + R3F） |
| Phase 3 | ✅ 正式上线 | 社区 + 创作者功能需要完整体验（富文本编辑/视频上传/嵌入播放） |
| Phase 4+ | ✅ 持续迭代 | 全功能对等，小程序为轻量入口 |

> **iOS/Android 差异处理**：Taro 4 编译到 App 时使用 React Native，一套代码同时输出 iOS 和 Android。平台差异通过 `process.env.TARO_ENV === 'rn'` + `Platform.OS` 条件编译处理。主要差异点：推送通知（APNs/FCM）、支付方式（微信 APP 支付）、权限申请文案。

---

## 3. 系统架构图

### 3.1 总体架构图

```mermaid
graph TB
    subgraph Client["客户端层"]
        MiniProgram["微信小程序<br/>(Taro 4 编译)"]
        App["iOS / Android App<br/>(Taro 4 + React Native)"]
        H5["H5 页面<br/>(Taro 4 编译)"]
    end

    subgraph Frontend["前端应用"]
        TaroApp["Taro 4 SPA<br/>(React 体系)"]
        Router["路由 + 页面守卫"]
        Store["Zustand Store"]
        HTTPClient["HTTP Client<br/>(Taro.request 封装)"]
        ThreeJS_3D["3D 教学模块<br/>(R3F / threejs-miniprogram)"]
        ECharts["ECharts 图表<br/>(热力图/环形图/折线图)"]
        AmapSDK["高德地图 SDK<br/>(球馆/约球/导航)"]
    end

    subgraph Gateway["接入层"]
        Nginx["Nginx<br/>(SSL + 静态资源 + API 反代)"]
        WAF["WAF 防火墙"]
    end

    subgraph Backend["主业务服务 (FastAPI)"]
        APIRouter["API Router (/api/v1)"]
        Auth["认证服务<br/>(微信登录 + JWT)"]
        BizServices["业务服务层<br/>(用户/赛事/社区/电商...)"]
        KnowledgeEngine["知识库 + 规则引擎<br/>(训练建议生成)"]
        Payment["微信支付服务"]
        Notification["通知服务<br/>(WebSocket Push)"]
    end

    subgraph AI["AI 推理服务 (独立部署)"]
        AIGateway["AI API Gateway"]
        BallDetection["球体检测<br/>(TTNet/TrackNetV5)"]
        BallTracking["球体追踪<br/>(卡尔曼滤波)"]
        TableDetection["球台检测<br/>(YOLO-pose)"]
        PoseEstimation["姿态估计<br/>(MediaPipe)"]
        ActionRecognition["动作识别<br/>(Temporal CNN)"]
        LandingEstimation["落点估算<br/>(单应性矩阵)"]
        ReportGen["报告生成<br/>(规则引擎 + LLM)"]
    end

    subgraph Worker["异步任务层"]
        CeleryWorker["Celery Worker<br/>(视频分析流水线)"]
        TaskQueue["Redis 任务队列"]
        ProgressTracker["进度追踪<br/>(WebSocket 推送)"]
    end

    subgraph Data["数据层"]
        PostgreSQL["PostgreSQL 15+<br/>(SQLAlchemy 2.0 async)"]
        Redis["Redis 7+<br/>(缓存/队列/排行榜)"]
        OSS["对象存储 OSS/COS<br/>(视频/图片/3D 模型)"]
        CDN["CDN<br/>(视频/模型分发)"]
    end

    subgraph External["外部服务"]
        WeChat["微信开放平台<br/>(登录/支付/分享)"]
        KQS["开球网 API<br/>(积分同步/赛事对接)"]
        LLM["LLM API<br/>(OpenAI 兼容)"]
        Amap["高德地图 API<br/>(逆地理编码/POI)"]
        GPU["云端 GPU<br/>(T4 按需实例)"]
    end

    MiniProgram --> TaroApp
    App --> TaroApp
    H5 --> TaroApp
    TaroApp --> Router & Store & HTTPClient & ThreeJS_3D & ECharts & AmapSDK
    HTTPClient --> Nginx
    Nginx --> WAF
    WAF --> APIRouter
    APIRouter --> Auth & BizServices & KnowledgeEngine & Payment & Notification
    BizServices --> PostgreSQL & Redis & OSS
    BizServices --> CeleryWorker
    CeleryWorker --> TaskQueue
    TaskQueue --> CeleryWorker
    CeleryWorker --> AIGateway
    CeleryWorker --> ProgressTracker
    ProgressTracker --> MiniProgram & App
    AIGateway --> BallDetection & BallTracking & TableDetection & PoseEstimation & ActionRecognition & LandingEstimation
    BallDetection & BallTracking & TableDetection & PoseEstimation & ActionRecognition & LandingEstimation --> ReportGen
    ReportGen --> LLM
    AIGateway --> GPU
    Auth --> WeChat
    BizServices --> KQS
    BizServices --> Amap
    OSS --> CDN
    CDN --> MiniProgram & App & H5
```

### 3.2 AI 视频分析流水线架构

```mermaid
graph LR
    subgraph Upload["1. 上传阶段"]
        VideoUpload["用户上传视频<br/>(Taro.chooseVideo)"]
        OSSUpload["直传 OSS<br/>(STS Token)"]
    end

    subgraph Queue["2. 排队阶段"]
        CreateTask["创建分析任务<br/>(PostgreSQL)"]
        Enqueue["入队 Redis<br/>(Celery task)"]
    end

    subgraph Pipeline["3. AI 分析流水线 (Celery Worker)"]
        Step1["Step 1: 视频预处理<br/>(FFmpeg 转码/抽帧)"]
        Step2["Step 2: 球台检测<br/>(YOLO-pose 四角定位)"]
        Step3["Step 3: 球体检测<br/>(TTNet/TrackNetV5)"]
        Step4["Step 4: 球体追踪<br/>(卡尔曼滤波 + 抛物线)"]
        Step5["Step 5: 落点估算<br/>(单应性矩阵映射)"]
        Step6["Step 6: 姿态估计<br/>(MediaPipe 2D)"]
        Step7["Step 7: 动作识别<br/>(Temporal CNN)"]
        Step8["Step 8: 回合分割<br/>(弹跳事件检测)"]
        Step9["Step 9: 报告生成<br/>(规则引擎 + LLM)"]
        Step10["Step 10: 标注视频生成<br/>(FFmpeg 叠加)"]
    end

    subgraph Store["4. 结果存储"]
        SaveResult["分析结果 → PostgreSQL<br/>(JSONB)"]
        SaveVideo["标注视频 → OSS/CDN"]
        SaveReport["报告图片 → OSS/CDN"]
    end

    subgraph Notify["5. 通知阶段"]
        WSNotify["WebSocket 推送<br/>(分析完成)"]
        WxNotify["微信模板消息<br/>(小程序)"]
    end

    VideoUpload --> OSSUpload
    OSSUpload --> CreateTask
    CreateTask --> Enqueue
    Enqueue --> Step1
    Step1 --> Step2 --> Step3 --> Step4 --> Step5
    Step5 --> Step6 --> Step7 --> Step8
    Step8 --> Step9 --> Step10
    Step10 --> SaveResult & SaveVideo & SaveReport
    SaveResult --> WSNotify & WxNotify
```

> **流水线说明**：
> - Step 1-2 可并行（球台检测与视频预处理无依赖）
> - Step 3-5 串行（检测→追踪→落点为级联依赖）
> - Step 6-7 串行（姿态→动作识别）
> - Step 3-5 与 Step 6-7 可并行（球分析与人分析无依赖）
> - 每步完成后通过 WebSocket 推送进度更新
> - 球速估算穿插在 Step 4（帧间位移 + 帧率 + 镜头标定），误差 20-30%，展示为范围值

### 3.3 数据飞轮架构

```mermaid
graph TB
    subgraph Flywheel["数据飞轮"]
        A["用户上传视频"] --> B["AI 自动分析"]
        B --> C["用户查看报告"]
        C --> D{"用户反馈<br/>标记对/不对"}
        D -->|正确| E["自动标注数据<br/>加入训练集"]
        D -->|错误| F["人工审核修正<br/>加入训练集"]
        E --> G["标注数据积累<br/>(OSS + Manifest)"]
        F --> G
        G --> H["模型 Fine-tune<br/>(半自动流程)"]
        H --> I["新模型部署<br/>(AI 推理服务)"]
        I --> J["分析精度提升"]
        J --> A
    end

    subgraph DataStore["数据存储"]
        VideoArchive["原始视频归档<br/>(OSS 冷存储)"]
        AnnotationStore["标注数据集<br/>(OSS + JSON Manifest)"]
        FeedbackDB["用户反馈记录<br/>(PostgreSQL)"]
        ModelRegistry["模型版本管理<br/>(本地 / MLflow)"]
    end

    A --> VideoArchive
    D --> FeedbackDB
    E & F --> AnnotationStore
    H --> ModelRegistry
```

> **飞轮要点**：
> - 用户在分析报告中标记"对/不对"，反馈存入 PostgreSQL
> - 正确分析的视频 + AI 结果自动归档为标注候选
> - 错误分析的视频进入人工审核队列（修正后归档）
> - 积累足够数据后触发模型 fine-tune（半自动，开发者手动触发）
> - 新模型通过 AI 推理服务灰度上线，对比效果后全量切换
> - 这是产品的核心壁垒：先发者数据越多，后来者越难追赶

---

## 4. 模块责任矩阵

> **Anti-hallucination**: 后端模块使用 snake_case，位于 `app/api/v1/` 和 `app/services/` 下。每个模块遵循 `router.py` + `service.py` + `schemas.py` + `models.py` 标准结构。
>
> **命名一致性约束**：模块矩阵名称 = API 目录名称 = service 文件名。以下为合并/包含关系说明：
> - `training/` 目录包含 `training_advice`（Phase 1）和 `training_plan`（Phase 2），共用 `training_service.py`
> - `gamification/` 目录包含 `gamification`（Phase 1）和 `badge_system`（Phase 2），共用 `gamification_service.py`，badge 相关逻辑在 `gamification/badge_service.py`
> - `social_match/` 和 `venue_search/` 为独立目录（Phase 3），不做合并

### 4.1 Phase 1 核心模块

| 模块 | 职责 | 核心实体 | 依赖模块 | 上线阶段 |
|------|------|---------|---------|---------|
| `auth` | 微信登录(小程序)/手机号登录(App)、JWT 认证、Token 管理 | User, UserSession | core/security, core/redis | Phase 1 |
| `user` | 个人档案、开球网积分、打法类型、装备配置、乒乓大数据 | UserProfile, RatingHistory, PlayingStyle | auth | Phase 1 |
| `video_analysis` | 视频上传、AI 分析任务管理、分析报告、结果反馈 | VideoTask, AnalysisReport, FeedbackRecord | auth, user, ai_pipeline | Phase 1 |
| `scoring` | 智能记分牌、比赛设置、实时记分、比赛统计、得分方式标记 | Match, ScoreRecord, MatchStatistic | auth, user | Phase 1 |
| `match_data` | 比赛数据手动录入、快速录入模板、比赛记录管理 | MatchRecord, ScoreDetail | auth, user, scoring | Phase 1 |
| `data_dashboard` | 数据看板、战绩趋势、技术统计、累计落点热图 | DashboardView, TrendData | video_analysis, scoring, match_data | Phase 1 |
| `training_advice` | 训练建议生成（基于分析报告 + 历史趋势 + 知识库规则）、训练计划模板 | TrainingAdvice, TrainingPlanTemplate | video_analysis, progress_analysis, knowledge_base | Phase 1 |
| `progress_analysis` | 进度快照生成、技术指标趋势计算、报告对比、训练方案有效性评估 | ProgressSnapshot, TechniqueTrend, PlanAdjustment | video_analysis, match_data | Phase 1 |
| `gamification` | 训练积分、打卡日历、基础徽章、连续打卡 | UserPoints, CheckinRecord, Badge | auth, video_analysis, scoring | Phase 1 |
| `membership` | 会员等级、权益管理、订阅/续费、免费额度控制 | Subscription, MembershipTier, UsageQuota | auth, payment | Phase 1 |
| `payment` | 微信支付集成、订单管理、支付回调、退款 | Order, PaymentRecord, RefundRecord | auth, membership | Phase 1 |
| `notification` | WebSocket 实时推送、微信模板消息、训练提醒 | NotificationRecord, PushSubscription | auth | Phase 1 |

### 4.2 Phase 2 智能教练模块

| 模块 | 职责 | 核心实体 | 依赖模块 | 上线阶段 |
|------|------|---------|---------|---------|
| `advanced_analysis` | 球速估算、击球动作细节、弧度分析、攻防转换时间轴 | AdvancedReport, BallSpeedData | video_analysis, ai_pipeline | Phase 2 |
| `opponent_analysis` | 对手建模、习惯落点、发球偏好、弱点区域、Scout 报告 | OpponentProfile, OpponentStat | video_analysis, data_dashboard | Phase 2 |
| `3d_teaching` | 3D 模型库管理、动作分类、交互查看器 API、对比分析 | Model3DAsset, ActionCategory, ComparisonResult | auth, video_analysis | Phase 2 |
| `training_plan` | 体系化训练方案、诊断短板、进度追踪、训练单生成、跟练模式、**方案动态调整** | TrainingPlan, TrainingSession, TrainingSheet, PlanAdjustment | training_advice, progress_analysis, knowledge_base | Phase 2 |
| `monthly_report` | 月度训练概览、技术进步趋势、成就展示、下月建议 | MonthlyReport, ProgressTrend | data_dashboard, progress_analysis, gamification | Phase 2 |
| `badge_system` | 完整徽章/成就系统、进度追踪、解锁条件 | Badge, UserBadge, BadgeProgress | gamification | Phase 2 |

### 4.3 Phase 3 社区与社交模块

| 模块 | 职责 | 核心实体 | 依赖模块 | 上线阶段 |
|------|------|---------|---------|---------|
| `community` | 社区信息流、帖子/动态、评论/点赞/收藏/分享、标签 | Post, Comment, Like, Collection, Tag | auth, user | Phase 3 |
| `qa` | 技术问答、提问/回答/最佳答案、采纳机制 | Question, Answer | community | Phase 3 |
| `learning_video` | 学习视频库、嵌入/授权/UGC 三种模式、跟练模式、智能推荐 | VideoCourse, VideoCategory, FollowAlong | auth, community, video_analysis | Phase 3 |
| `creator_center` | 创作者上传/定价/审核/收益/提现、分成管理 | CreatorProfile, CreatorVideo, Revenue, Withdrawal | learning_video, payment | Phase 3 |
| `circle` | 圈子/话题、圈子列表、话题详情、圈子管理 | Circle, Topic, CircleMember | community | Phase 3 |
| `leaderboard` | 周榜/月榜/总榜、训练达人/分析达人/社区内容榜 | LeaderboardEntry, LeaderboardSnapshot | gamification, community | Phase 3 |
| `coach_service` | 教练入驻、教练列表/详情、线上指导服务、学员评价 | CoachProfile, CoachingService, CoachReview, CoachingOrder | auth, payment, video_analysis | Phase 3 |
| `social_match` | 同城约球、LBS 匹配、约球发布/报名/管理 | PlayDate, PlayDateRegistration | auth, user | Phase 3 |
| `venue_search` | 球馆搜索、地图/列表双模式、球馆详情、用户评价 | Venue, VenueReview, VenueRating | auth, social_match | Phase 3 |
| `content_moderation` | 内容审核、举报处理、敏感词过滤、自动审核规则 | ModerationRecord, Report, SensitiveWord | community, learning_video | Phase 3 |

### 4.4 Phase 4 商业生态模块

| 模块 | 职责 | 核心实体 | 依赖模块 | 上线阶段 |
|------|------|---------|---------|---------|
| `tournament` | 赛事列表/详情/报名/缴费/成绩录入、对接开球网 | Tournament, TournamentRegistration, TournamentResult | auth, payment, kqs_integration | Phase 4 |
| `ranking` | 全国/省/市三级排名、积分变化历史、对接开球网 | RankingSnapshot, RatingHistory | kqs_integration, user | Phase 4 |
| `activity` | 活动组织、创建/邀请/管理、现场智能组队 | Activity, ActivityRegistration, TeamAssignment | auth, social_match | Phase 4 |
| `map_navigation` | 高德地图集成、球馆导航、赛事地点导航 | — | venue_search | Phase 4 |
| `equipment` | 装备评测、装备推荐、装备商城、打法档案 | Equipment, EquipmentReview, EquipmentRecommendation | auth, user | Phase 4 |
| `ecommerce` | 装备商城、订单管理、物流追踪、自营/导购 | Product, Order, Shipment | payment, equipment | Phase 4 |
| `credit_score` | 信用分体系、加减分规则、信用等级、权益挂钩 | CreditScore, CreditRecord | auth, tournament | Phase 4 |
| `kqs_integration` | 开球网 API 对接、积分同步、赛事数据同步 | KqsSyncLog, KqsRatingCache | user, tournament, ranking | Phase 4 |

### 4.5 跨阶段基础设施模块

| 模块 | 职责 | 核心实体 | 依赖模块 | 上线阶段 |
|------|------|---------|---------|---------|
| `knowledge_base` | 乒乓球专业知识库、结构化存储、规则引擎、训练方案模板 | KnowledgeCategory, KnowledgeEntry, TrainingTemplate, RuleDefinition | — | Phase 1 |
| `ai_pipeline` | AI 分析流水线编排、Celery 任务定义、进度追踪、结果聚合 | AnalysisTask, PipelineStep, AnalysisResult | video_analysis, ai_inference | Phase 1 |
| `ai_inference` | AI 推理服务（独立部署）、模型加载、推理 API | ModelVersion, InferenceRequest | — | Phase 1 |
| `file_management` | 文件上传(STS)、OSS 管理、CDN 分发、视频转码 | FileRecord, UploadToken | — | Phase 1 |
| `admin` | 管理后台、内容审核、用户管理、模型管理、系统配置 | AdminUser, AuditLog, SystemConfig | — | Phase 1 |

---

## 5. 通信架构

### 5.1 REST API 模式

```
Client → POST/GET/PUT/DELETE /api/v1/{module}/{resource}
        ← {code: 200, message: "success", data: {...}, timestamp: "..."}
```

- **统一响应格式**：`app/core/response.py` → `success(data, message)` / `error(code, message)`
- **统一异常处理**：`app/core/exceptions.py` → `AppException(message, code, status_code)`
- **分页**：`app/core/pagination.py` → `paginate(query, page, page_size)` → `{total, page, page_size, items}`
- **API 文档**：FastAPI 自动生成 OpenAPI `/docs`（仅开发环境开放）

### 5.2 WebSocket 实时通信

```
Client → WS /api/v1/ws (Authorization: Bearer {token})
        ← event: analysis_progress  data: {"task_id": "...", "step": 5, "total": 10, "message": "球体追踪中..."}
        ← event: analysis_complete   data: {"task_id": "...", "report_id": "..."}
        ← event: score_update        data: {"match_id": "...", "score": "11:8", "server": "player"}
        ← event: notification        data: {"type": "training_reminder", "content": "..."}
```

- **后端**：`app/api/v1/ws.py` → FastAPI WebSocket 端点
- **前端**：`src/utils/websocket.ts` → Taro WebSocket 封装（小程序用 wx.connectSocket，App 用 WebSocket）
- **用途**：
  - AI 分析进度实时推送（步骤式进度）
  - 记分牌实时同步（多设备观赛）
  - 训练提醒/系统通知推送
- **心跳**：30s 间隔，90s 无响应断开重连

### 5.3 异步任务队列模式

```
Client → POST /api/v1/video-analysis/tasks
        ← {code: 200, data: {"task_id": "task_xxx", "status": "queued"}}

[后台 Celery Worker 执行流水线]
  → Redis 队列消费 → AI 推理 → 结果聚合 → 存储 → WebSocket 通知
```

- **任务队列**：Redis broker + Celery
- **任务定义**：`app/services/ai_pipeline/tasks.py`
- **进度追踪**：每个 Step 完成后更新 Redis + PostgreSQL + WebSocket 推送
- **超时控制**：单个分析任务 600s 超时（`AI_ANALYSIS_TIMEOUT_SECONDS`）
- **重试策略**：失败步骤自动重试 2 次，指数退避

### 5.4 微信登录认证流程

```mermaid
sequenceDiagram
    participant C as Client (小程序)
    participant B as Backend (FastAPI)
    participant W as 微信开放平台
    participant D as PostgreSQL
    participant R as Redis

    C->>W: wx.login() → code
    W-->>C:临时登录凭证 code
    C->>B: POST /api/v1/auth/wechat-login {code}
    B->>W: code2session(code) → openid + session_key
    W-->>B: {openid, session_key}
    B->>D: 查询/创建 User (by openid)
    D-->>B: User record
    B->>B: 生成 JWT (access + refresh)
    B->>R: 存储 session_key (供后续解密)
    B-->>C: {access_token, refresh_token, user_profile}

    Note over C: 后续请求携带 Bearer Token

    C->>B: GET /api/v1/xxx (Authorization: Bearer {access_token})
    B->>B: 验证 JWT
    B-->>C: 200 Response

    C->>B: POST /api/v1/auth/refresh {refresh_token}
    B-->>C: {new access_token, new refresh_token}
```

### 5.5 微信支付流程

```mermaid
sequenceDiagram
    participant C as Client
    participant B as Backend (FastAPI)
    participant W as 微信支付
    participant D as PostgreSQL

    C->>B: POST /api/v1/orders {product_type, ...}
    B->>D: 创建订单 (status=pending)
    B->>W: 统一下单 (JSAPI/APP)
    W-->>B: prepay_id + 签名参数
    B-->>C: 支付参数 (prepay_id, paySign, ...)

    C->>W: 调起微信支付 (wx.requestPayment)
    W-->>C: 支付结果

    W->>B: 异步回调 /api/v1/payment/notify
    B->>B: 验签 + 解密
    B->>D: 更新订单 (status=paid)
    B->>B: 触发业务逻辑 (会员开通/分析额度/创作者收益)
    B-->>W: 200 (ACK)
    B->>C: WebSocket 推送支付成功
```

### 5.6 LLM 报告生成流程

```
[AI 流水线 Step 9: 报告生成]
  → 收集前 8 步结构化结果 (球轨迹/落点/动作/回合...)
  → 规则引擎查询知识库 (匹配问题模式 → 训练方法)
  → 组装 LLM Prompt (结构化数据 + 知识库上下文 + 用户画像)
  → 调用 LLM API (OpenAI 兼容)
  → 解析 LLM 输出 → 结构化报告 (JSON)
  → 存储 PostgreSQL (JSONB)
```

- **LLM 调用**：`app/services/ai_pipeline/report_generator.py`
- **Prompt 模板**：`app/services/knowledge_base/prompts/`
- **超时**：30s，失败降级为纯规则引擎输出
- **成本控制**：单次报告生成 LLM 调用预算 ¥0.1-0.3

### 5.7 Phase 1 核心 API 端点清单

> 以下为 Phase 1 各模块的核心 REST API 端点。所有端点挂载在 `/api/v1` 下，统一响应格式 `{code, message, data, timestamp}`。

#### 认证模块 (`/auth`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| POST | `/auth/wechat-login` | 微信小程序登录（code → JWT） | 公开 | 10/min |
| POST | `/auth/phone-login` | 手机号验证码登录（App） | 公开 | 5/min |
| POST | `/auth/send-sms` | 发送短信验证码 | 公开 | 1/min |
| POST | `/auth/refresh` | 刷新 access_token | refresh_token | — |
| POST | `/auth/logout` | 登出（撤销 token） | 登录 | — |
| GET | `/auth/me` | 获取当前用户信息 | 登录 | — |
| POST | `/auth/h5-token` | 生成 H5 降级临时 Token（5 分钟过期） | 登录 | — |
| POST | `/auth/h5-exchange` | H5 Token 换 JWT（web-view 降级页认证） | H5 Token | 一次性使用 |

#### 用户模块 (`/users`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| GET | `/users/profile` | 获取个人档案 | 登录 | — |
| PUT | `/users/profile` | 更新个人档案（打法/装备/自评水平） | 登录 | — |
| PUT | `/users/rating` | 更新开球网积分（手动填写/ID） | 登录 | — |
| GET | `/users/rating-history` | 积分历史记录 | 登录 | — |
| GET | `/users/big-data` | 乒乓大数据（趣味统计） | 登录 | 缓存 24h |

#### 视频分析模块 (`/video-analysis`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| POST | `/video-analysis/upload-token` | 获取 OSS STS 直传凭证 | 登录 | — |
| POST | `/video-analysis/tasks` | 创建分析任务（视频 OSS Key） | 登录 | 免费 3/天, 会员无限 |
| GET | `/video-analysis/tasks` | 任务列表（分页） | 登录 | — |
| GET | `/video-analysis/tasks/{id}` | 任务详情 + 进度 | 登录 | — |
| GET | `/video-analysis/reports/{id}` | 分析报告详情 | 登录 | — |
| GET | `/video-analysis/reports` | 报告列表（分页） | 登录 | — |
| POST | `/video-analysis/reports/{id}/feedback` | 提交反馈（对/不对标记） | 登录 | — |
| GET | `/video-analysis/reports/{id}/annotated-video` | 标注视频 CDN URL | 登录 | — |

#### 记分牌模块 (`/scoring`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| POST | `/scoring/matches` | 创建比赛（赛制/对手/类型） | 登录 | — |
| GET | `/scoring/matches` | 比赛列表 | 登录 | — |
| GET | `/scoring/matches/{id}` | 比赛详情 | 登录 | — |
| POST | `/scoring/matches/{id}/score` | 记分（得分方 + 得分方式） | 登录 | — |
| POST | `/scoring/matches/{id}/undo` | 撤销最近一球 | 登录 | — |
| POST | `/scoring/matches/{id}/finish` | 结束比赛 → 生成统计 | 登录 | — |
| GET | `/scoring/matches/{id}/statistics` | 比赛统计 | 登录 | — |

#### 数据看板 (`/dashboard`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| GET | `/dashboard/overview` | 概览卡片（胜率/分析次数/训练频次） | 登录 | 缓存 5min |
| GET | `/dashboard/win-rate-trend` | 战绩趋势 | 登录 | 缓存 1h |
| GET | `/dashboard/technique-stats` | 技术统计 | 登录 | 缓存 1h |
| GET | `/dashboard/landing-heatmap` | 累计落点热图 | 登录 | 缓存 1h |
| GET | `/dashboard/match-records` | 比赛记录列表 | 登录 | — |

#### 训练建议 (`/training`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| GET | `/training/advice/{report_id}` | 基于分析报告的训练建议 | 登录 | — |
| GET | `/training/templates` | 训练方案模板列表 | 登录 | — |
| GET | `/training/templates/{id}` | 模板详情 | 登录 | — |

#### 游戏化 (`/gamification`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| GET | `/gamification/points` | 训练积分 | 登录 | — |
| GET | `/gamification/checkin-calendar` | 打卡日历（月度） | 登录 | — |
| POST | `/gamification/checkin` | 手动打卡 | 登录 | 1/天 |
| GET | `/gamification/badges` | 徽章列表（已获得/未获得） | 登录 | — |

#### 会员与支付 (`/membership`, `/payment`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| GET | `/membership/tiers` | 会员等级与权益对比 | 登录 | 缓存 1h |
| GET | `/membership/current` | 当前会员状态 | 登录 | — |
| GET | `/membership/quota` | 今日剩余免费分析次数 | 登录 | — |
| POST | `/payment/orders` | 创建订单（会员订阅/分析次数包） | 登录 | — |
| GET | `/payment/orders` | 订单列表 | 登录 | — |
| POST | `/payment/notify` | 微信支付异步回调 | 微信签名 | — |

#### 通知 (`/notification`)

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| GET | `/notification/list` | 通知列表（分页） | 登录 | — |
| POST | `/notification/read` | 标记已读 | 登录 | — |
| POST | `/notification/subscribe` | 微信订阅消息授权 | 登录 | — |

#### 进度分析 (`/progress`)

> 训练建议从"单次报告快照式"升级为"基于历史数据对比的趋势式"。每次分析后自动生成进度快照并计算趋势。

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| GET | `/progress/snapshots` | 进度快照列表（按时间倒序，支持 `period` 参数） | 登录 | — |
| GET | `/progress/technique-trends` | 全部技术指标趋势（方向/变化率/持续性） | 登录 | 缓存 1h |
| GET | `/progress/technique-trends/{metric}` | 单项指标趋势详情（含时间序列数据） | 登录 | 缓存 1h |
| GET | `/progress/comparison?report_a={id}&report_b={id}` | 两次分析报告对比 | 登录 | — |
| GET | `/progress/summary` | 进度综合摘要（趋势+问题变化+方案状态） | 登录 | 缓存 1h |
| GET | `/progress/problem-changes` | 问题变化列表（新增/已解决/持续） | 登录 | 缓存 1h |

#### 训练建议增强 (`/training`)

> 原 `GET /training/advice/{report_id}` 增强为包含历史趋势上下文的综合建议。

| Method | Path | 说明 | 权限 | 限流 |
|--------|------|------|------|------|
| GET | `/training/advice/{report_id}` | 基于分析报告的训练建议（增强：含历史趋势对比） | 登录 | — |
| GET | `/training/advice/contextual` | 基于最新报告+历史趋势的综合建议（自动取最新报告） | 登录 | — |
| GET | `/training/plan/{id}/adjustments` | 训练方案调整历史（版本化记录） | 登录 | — |
| POST | `/training/plan/{id}/re-evaluate` | 手动触发方案重新评估 | 会员 | — |

### 5.8 通知分发策略

#### 通道选择矩阵

| 通知类型 | 用户在线 (WS) | 用户离线 (小程序) | 用户离线 (App) | 优先级 |
|---------|-------------|----------------|--------------|--------|
| AI 分析完成 | ✅ WebSocket 推送 | ✅ 微信订阅消息 | ✅ 推送通知 (APNs/FCM) | 高 |
| AI 分析失败 | ✅ WebSocket 推送 | ✅ 微信订阅消息 | ✅ 推送通知 | 高 |
| 记分牌实时同步 | ✅ WebSocket 推送 | ❌ 不推送 | ❌ 不推送 | 中 |
| 训练提醒 | ❌ 不推送 | ✅ 微信订阅消息 | ✅ 推送通知 | 低 |
| 支付成功 | ✅ WebSocket 推送 | ✅ 微信订阅消息 | ✅ 推送通知 | 高 |
| 系统/活动通知 | ❌ 不推送 | ✅ 微信模板消息 | ✅ 推送通知 | 低 |

#### 微信订阅消息管理

- **订阅模型**：微信小程序订阅消息为"一次性订阅"（每次用户操作时授权一次，发一条消耗一次）
- **授权时机**：用户点击"上传分析"时弹出订阅授权（分析完成通知）
- **长期订阅**：仅特定类目（教育/政务）可申请长期订阅，本项目暂不可用
- **降级**：订阅消息额度耗尽时，仅 WebSocket 推送，不补发

#### 训练提醒触发机制

- **Celery Beat 定时任务**：每日 19:00 检查"超过 3 天未训练的用户"
- **规则**：上次分析/记分距今 > 3 天 → 发送训练提醒
- **频率控制**：同一用户每周最多 2 次训练提醒
- **内容**：包含上次分析报告的训练建议摘要

---

## 6. AI 视频分析流水线设计

### 6.1 流水线步骤详解

| 步骤 | 名称 | 模型/算法 | 输入 | 输出 | 预估耗时 | GPU 需求 |
|------|------|----------|------|------|---------|---------|
| 1 | 视频预处理 | FFmpeg | 原始视频 (OSS) | 标准化帧序列 (30fps, 1080p) | 10-30s | CPU |
| 2 | 球台检测 | YOLO-pose + OpenCV | 帧序列 | 球台四角坐标 + 单应性矩阵 | 5-15s | GPU (T4) |
| 3 | 球体检测 | TTNet / TrackNetV5 | 连续 9 帧拼接 | 球位置 heatmap → 坐标序列 | 30-120s | GPU (T4) |
| 4 | 球体追踪 | 卡尔曼滤波 + 抛物线模型 | 球坐标序列 + 弹跳事件 | 连续球轨迹 + 球速估算 | 10-30s | CPU/GPU |
| 5 | 落点估算 | 单应性矩阵映射 | 球轨迹 + 球台坐标 | 落点九宫格分布 | 5-10s | CPU |
| 6 | 姿态估计 | MediaPipe | 帧序列 | 2D 关键点序列 (33 点) | 20-60s | CPU/GPU |
| 7 | 动作识别 | Temporal CNN | 关键点序列 | 动作分类序列 (21 类) | 10-30s | GPU (T4) |
| 8 | 回合分割 | 弹跳事件 + 节奏分析 | 球轨迹 + 动作序列 | 回合边界 + 得分归属 | 5-15s | CPU |
| 9 | 报告生成 | 规则引擎 + LLM | 全部结构化结果 + 知识库 | 分析报告 (JSON + 文字) | 10-30s | CPU |
| 10 | 标注视频 | FFmpeg | 原始视频 + 标注数据 | 标注视频 (球轨迹叠加/关键帧) | 30-60s | CPU |

> **总预估**：单视频分析 2-7 分钟（视视频时长和 GPU 实例规格）
> **GPU 成本**：T4 实例 ~1.87 元/小时，单次分析 GPU 成本 ~0.1-0.3 元

### 6.2 GPU 实例调度策略

```mermaid
graph TB
    subgraph AutoScale["GPU 自动伸缩策略"]
        QueueMonitor["队列监控<br/>(每 10s 检查)"]
        ScaleUp{"待处理任务 > 0?"}
        StartGPU["启动 GPU 实例<br/>(T4 spot 实例)"]
        ProcessTask["处理分析任务"]
        IdleCheck{"空闲 > 5 分钟?"}
        ShutdownGPU["关闭 GPU 实例<br/>(节省成本)"]
    end

    QueueMonitor --> ScaleUp
    ScaleUp -->|是| StartGPU
    StartGPU --> ProcessTask
    ProcessTask --> IdleCheck
    IdleCheck -->|是| ShutdownGPU
    IdleCheck -->|否| ProcessTask
    ScaleUp -->|否| QueueMonitor
```

> **策略要点**：
> - 使用 spot 实例（竞价实例），成本约为按量付费的 30-50%
> - 无任务时 GPU 实例自动关闭，月成本可控在 ~354 元（Phase 0 估算）
> - 高峰期可自动扩容多台 GPU 实例并行处理
> - 模型预加载到实例镜像，减少冷启动时间

### 6.3 分析结果数据结构

```json
{
  "task_id": "task_xxx",
  "video_info": {
    "duration_sec": 180,
    "fps": 30,
    "resolution": "1920x1080",
    "total_frames": 5400
  },
  "rally_analysis": {
    "total_rallies": 23,
    "avg_rally_length": 5.2,
    "max_rally_length": 18,
    "rhythm_data": [{"time": 0.5, "frequency": 1.2}, ...]
  },
  "landing_points": {
    "nine_grid": [[2, 5, 3], [4, 8, 6], [1, 3, 2]],
    "distribution": {"forehand": 0.68, "backhand": 0.25, "middle": 0.07},
    "heatmap_data": [...]
  },
  "technique_stats": {
    "forehand_drive": 45,
    "backhand_drive": 18,
    "forehand_loop": 12,
    "serve": 23,
    "push": 8,
    "other": 5
  },
  "action_sequence": [
    {"frame": 150, "action": "serve", "player": "server"},
    {"frame": 165, "action": "forehand_drive", "player": "receiver"},
    ...
  ],
  "ball_speed": {
    "avg_speed_mps": 18.5,
    "max_speed_mps": 25.3,
    "speed_range": [15.2, 22.1],
    "note": "误差范围 20-30%，展示为范围值"
  },
  "score_analysis": {
    "final_score": "11:8",
    "score_progression": [...],
    "key_points": [...]
  },
  "report_text": {
    "summary": "本局正手使用率 68%，落点偏反手区域...",
    "issues": ["反手使用率偏低(25%)", "落点变化不足"],
    "suggestions": ["增加反手拉球练习", "提升落点控制能力"]
  }
}
```

---

### 6.4 视频转码策略

> 用户上传视频格式/分辨率/帧率不一，AI 分析和 CDN 分发需标准化处理。

#### 标准化输入格式（送入 AI）

| 参数 | 标准值 | 说明 |
|------|--------|------|
| 编码格式 | H.264 (libx264) | 通用兼容 |
| 容器格式 | MP4 | 标准 |
| 分辨率 | 1920×1080 (1080p) | 过高分辨率降采样，过低则保持原样 |
| 帧率 | 30 fps | 高帧率抽帧降至 30fps，低帧率保持原样 |
| 音频 | 移除 | AI 分析不需要音频 |

> 转码命令示例：`ffmpeg -i input.mov -vf scale=1920:1080 -r 30 -an -c:v libx264 -preset fast -crf 23 output_standard.mp4`

#### 多清晰度输出（CDN 分发）

| 清晰度 | 分辨率 | 码率 | 用途 |
|--------|--------|------|------|
| 原画 | 原始 | 原始 | 下载/高质量回看 |
| 1080p | 1920×1080 | 4Mbps | WiFi 播放 |
| 720p | 1280×720 | 2Mbps | 4G 播放 |
| 480p | 854×480 | 1Mbps | 弱网播放 |

#### 转码任务编排

```mermaid
graph LR
    Upload["用户上传<br/>(原始视频→OSS)"]
    StandardTranscode["标准化转码<br/>(FFmpeg→1080p/30fps)"]
    AIPipeline["AI 分析流水线<br/>(Step 1-10)"]
    MultiBitrate["多清晰度转码<br/>(FFmpeg→720p/480p)"]
    Thumbnail["封面图/缩略图<br/>(FFmpeg 截帧)"]
    CDNUpload["上传 CDN"]

    Upload --> StandardTranscode
    StandardTranscode --> AIPipeline
    StandardTranscode --> MultiBitrate
    StandardTranscode --> Thumbnail
    AIPipeline --> CDNUpload
    MultiBitrate --> CDNUpload
    Thumbnail --> CDNUpload
```

> - 标准化转码是 AI 流水线 Step 1 的前置，转码完成后触发 AI 分析
> - 多清晰度转码与 AI 分析**并行**执行（不互相阻塞）
> - 标注视频（Step 10 产出）基于标准化 1080p 版本叠加
> - 转码超时：5 分钟，失败则通知用户"视频格式不支持，请重新上传"

#### 封面图生成

- 视频第 1 秒截帧作为封面图（OSS 存储）
- 分析报告分享时自动附带封面图

### 6.5 AI 服务熔断与降级机制

#### 熔断器设计

```mermaid
graph LR
    subgraph CircuitBreaker["熔断器状态机"]
        Closed["关闭态<br/>(正常请求)"]
        Open["打开态<br/>(快速失败)"]
        HalfOpen["半开态<br/>(探测恢复)"]
    end

    Closed -->|"连续失败 ≥ 5 次"| Open
    Open -->|"等待 60s"| HalfOpen
    HalfOpen -->|"探测请求成功"| Closed
    HalfOpen -->|"探测请求失败"| Open
```

| 状态 | 行为 | 触发条件 |
|------|------|---------|
| Closed（关闭） | 正常转发请求到 AI 推理服务 | 默认状态 |
| Open（打开） | 快速失败，返回"分析服务繁忙" | 连续 5 次请求失败（超时/5xx） |
| Half-Open（半开） | 放行 1 个探测请求 | Open 状态持续 60s 后自动进入 |

#### Spot 实例抢占处理

| 场景 | 检测方式 | 处理策略 |
|------|---------|---------|
| GPU 实例被抢占 | AI 推理服务健康检查失败 | 任务自动重排队（Redis 队列），等待新实例启动 |
| GPU 实例 OOM | 推理 API 返回 503 | 熔断器触发，任务重排队 |
| 模型加载失败 | 推理 API 返回 500 | 记录告警，任务标记为"分析失败"，通知用户重试 |

#### LLM 降级策略

```mermaid
graph TB
    ReportStep["Step 9: 报告生成"]
    CheckLLM{"LLM 可用?<br/>(环境变量<br/>LLM_ENABLED=true)"}
    CallLLM["调用 LLM API"]
    LLMSuccess{"成功?"}
    RuleEngine["纯规则引擎<br/>生成报告"]
    StoreResult["存储报告"]

    ReportStep --> CheckLLM
    CheckLLM -->|是| CallLLM
    CheckLLM -->|否| RuleEngine
    CallLLM --> LLMSuccess
    LLMSuccess -->|是| StoreResult
    LLMSuccess -->|否| RuleEngine
    RuleEngine --> StoreResult
```

- **LLM 开关**：环境变量 `LLM_ENABLED`（默认 true），可快速关闭
- **降级输出**：纯规则引擎输出结构化数据（数据统计 + 问题诊断 + 训练方法），不含 LLM 润色的自然语言描述
- **用户感知**：报告标注"AI 辅助分析"（LLM 版）或"数据分析报告"（规则引擎版）

#### 用户侧体验降级

| 场景 | 用户看到的内容 |
|------|--------------|
| 分析服务繁忙（熔断） | "分析服务当前繁忙，您的视频已排队，预计 X 分钟后完成" |
| 分析失败（不可恢复） | "分析失败，未消耗免费额度。请检查视频拍摄角度后重试" |
| LLM 降级 | 报告正常展示数据图表，文字描述为精简版（无 LLM 润色） |

---

## 7. 3D 教学模块集成设计

### 7.1 3D 资源管理

| 资源类型 | 存储位置 | 格式 | 大小限制 | CDN 加速 |
|---------|---------|------|---------|---------|
| 3D 角色模型 | OSS | GLB (Draco 压缩) | ≤2MB | ✅ |
| 动画文件 | OSS (内嵌 GLB) | glTF Animation | — | ✅ |
| 关键姿势数据 | PostgreSQL (JSONB) | 关键帧元数据 | — | — |
| 动作分类树 | PostgreSQL | 结构化 JSON | — | — |

### 7.2 3D 模型加载流程

```mermaid
sequenceDiagram
    participant C as Client
    participant B as Backend
    participant OSS as 对象存储
    participant CDN as CDN

    C->>B: GET /api/v1/3d-teaching/models?category=forehand
    B-->>C: 模型列表 + CDN URL

    C->>CDN: 下载 GLB 模型 (Draco 压缩)
    CDN-->>C: GLB 文件 (≤2MB)

    Note over C: Three.js GLTFLoader + DRACOLoader 解析
    Note over C: 小程序: threejs-miniprogram 适配
    Note over C: App/H5: React Three Fiber Canvas

    C->>B: GET /api/v1/3d-teaching/models/{id}/annotations
    B-->>C: 关键点标注数据 (关节角度/拍面角度)

    Note over C: 渲染 3D 场景 + 动画播放 + 交互控制
```

### 7.3 3D 交互功能 API

| 功能 | 前端实现 | 后端 API |
|------|---------|---------|
| 360° 旋转 | OrbitControls (R3F) / 自定义触摸事件 (小程序) | — |
| 4 档速度 (0.25x/0.5x/1x/2x) | AnimationMixer.timeScale | — |
| 逐帧查看 | AnimationMixer 时间控制 | — |
| 关键姿势跳转 | 动画时间点映射 | GET /models/{id}/key-poses |
| 关节角度标注 | CSS2DRenderer 叠加 (R3F) | GET /models/{id}/annotations |
| 动作切换 crossFade | AnimationMixer crossFade | GET /models/{id}/actions |
| 用户视频对比分析 | 并排/叠加 Canvas 渲染 | POST /3d-teaching/compare |

---

## 8. 知识库与规则引擎设计

### 8.1 知识库结构

> Phase 0 已完成 60KB 专业知识库，架构设计中将其结构化为可机读数据。

| 知识类别 | 存储方式 | 用途 |
|---------|---------|------|
| 技术动作分类树 (8 大类) | PostgreSQL JSONB | 动作识别结果映射、报告分类 |
| 常见问题库 (10+ 问题) | PostgreSQL JSONB | 报告诊断、训练建议关联 |
| 数据维度定义 (18 维) | PostgreSQL JSONB | 分析结果结构化、报告渲染 |
| 打法风格分类 (4 大类型) | PostgreSQL JSONB | 用户画像、训练方案个性化 |
| 训练方案模板 | PostgreSQL JSONB | 训练单生成、参数化方案 |
| 视频拍摄建议 | PostgreSQL JSONB | 拍摄引导页面内容 |

### 8.2 规则引擎架构

> **增强设计**：规则引擎输入从"单次分析结果"升级为"最新分析结果 + 历史趋势 + 训练方案进度"，使训练建议基于历史数据对比，更加科学。

```mermaid
graph LR
    subgraph Input["输入"]
        AnalysisResult["最新分析结果<br/>(落点/技术/回合...)"]
        HistoricalTrends["历史趋势数据<br/>(指标变化方向/速率/持续性)"]
        UserProfile["用户画像<br/>(积分/打法/装备)"]
        PlanProgress["训练方案进度<br/>(当前方案目标/完成度)"]
    end

    subgraph RuleEngine["规则引擎"]
        RuleLoader["规则加载器<br/>(从 PostgreSQL 加载)"]
        SingleMatcher["单次问题匹配器<br/>(当前报告 → 问题)"]
        TrendMatcher["趋势问题匹配器<br/>(指标趋势 → 持续性/改善/退步)"]
        PatternMatcher["综合问题匹配器<br/>(合并单次 + 趋势结果)"]
        TrainingRecommender["训练方法推荐器<br/>(问题 → 训练方法 + 差异化策略)"]
        PlanAssessor["方案有效性评估器<br/>(目标达成度/停滞检测)"]
        PlanGenerator["训练方案生成器<br/>(模板参数化/动态调整)"]
    end

    subgraph Knowledge["知识库"]
        Rules["规则定义表<br/>(单次规则 + 趋势规则)"]
        Problems["常见问题库"]
        Methods["训练方法库"]
        Templates["训练方案模板"]
    end

    subgraph Output["输出"]
        Diagnosis["诊断结果<br/>(短板 + 原因 + 趋势标注)"]
        Suggestions["训练建议<br/>(进步确认/持续问题/新问题/已解决)"]
        Plan["训练方案<br/>(新方案 or 调整后方案)"]
        PlanAction["方案调整动作<br/>(维持/调整/升级/设新目标)"]
    end

    AnalysisResult --> SingleMatcher
    HistoricalTrends --> TrendMatcher
    UserProfile --> SingleMatcher
    PlanProgress --> PlanAssessor
    SingleMatcher --> PatternMatcher
    TrendMatcher --> PatternMatcher
    PatternMatcher --> Diagnosis
    PlanAssessor --> PlanAction
    Diagnosis --> TrainingRecommender
    PlanAction --> TrainingRecommender
    TrainingRecommender --> Suggestions
    Suggestions --> PlanGenerator
    PlanGenerator --> Plan
    RuleLoader --> Rules & Problems & Methods & Templates
    Rules --> SingleMatcher & TrendMatcher
    Problems --> PatternMatcher
    Methods --> TrainingRecommender
    Templates --> PlanGenerator
```

> **规则类型**：
> - **单次规则**（已有）：基于当前报告的即时问题匹配（如"反手使用率 < 30%"）
> - **趋势规则**（新增）：基于指标变化趋势的问题识别（如"反手使用率连续 3 次分析 < 30%"）
> - **改善规则**（新增）：识别正在改善的指标，确认进步并维持当前方案
> - **停滞规则**（新增）：检测长期未改善的指标，触发方案调整
> - **方案有效性规则**（新增）：对比训练方案目标与实际进度，评估方案是否有效

### 8.3 规则定义示例

```json
{
  "rule_id": "RULE_001",
  "rule_name": "反手使用率偏低",
  "condition": {
    "field": "technique_stats.backhand_ratio",
    "operator": "<",
    "threshold": 0.30
  },
  "diagnosis": {
    "problem_id": "PROBLEM_003",
    "problem_name": "反手使用率不足",
    "severity": "medium",
    "description": "反手使用率 {value}，低于推荐值 30%，可能影响攻防平衡"
  },
  "training_methods": ["METHOD_012", "METHOD_015", "METHOD_022"],
  "training_plan_template": "TPL_BACKHAND_IMPROVE"
}
```

---

## 9. 数据库设计

### 9.1 Phase 1 核心 ER 图

```mermaid
erDiagram
    USER ||--o{ USER_PROFILE : has
    USER ||--o{ RATING_HISTORY : records
    USER ||--o{ VIDEO_TASK : uploads
    USER ||--o{ MATCH : plays
    USER ||--o{ MATCH_RECORD : records
    USER ||--o{ USER_POINTS : earns
    USER ||--o{ CHECKIN_RECORD : checks
    USER ||--o{ SUBSCRIPTION : subscribes
    USER ||--o{ ORDER : places
    USER ||--o{ NOTIFICATION_RECORD : receives
    USER ||--o{ FEEDBACK_RECORD : submits

    VIDEO_TASK ||--|| ANALYSIS_REPORT : produces
    VIDEO_TASK ||--o{ PIPELINE_STEP : executes
    ANALYSIS_REPORT ||--o{ FEEDBACK_RECORD : receives

    MATCH ||--o{ SCORE_RECORD : contains
    MATCH ||--|| MATCH_STATISTIC : summarizes
    MATCH_RECORD ||--o{ SCORE_DETAIL : contains

    ORDER ||--o{ PAYMENT_RECORD : tracks
    SUBSCRIPTION ||--|| ORDER : paid_by

    USER ||--o{ PROGRESS_SNAPSHOT : tracks
    USER ||--o{ TECHNIQUE_TREND : trends
    ANALYSIS_REPORT ||--|| PROGRESS_SNAPSHOT : generates
    TRAINING_PLAN ||--o{ PLAN_ADJUSTMENT : adjusts

    USER {
        bigint id PK
        varchar openid UK
        varchar phone
        varchar nickname
        varchar avatar_url
        timestamp created_at
    }
        bigint id PK
        varchar openid UK
        varchar phone
        varchar nickname
        varchar avatar_url
        timestamp created_at
    }
    USER_PROFILE {
        bigint id PK
        bigint user_id FK
        int kqs_rating
        varchar kqs_username
        varchar playing_style
        jsonb equipment_config
        varchar self_assessed_level
    }
    RATING_HISTORY {
        bigint id PK
        bigint user_id FK
        int rating
        varchar source
        timestamp recorded_at
    }
    VIDEO_TASK {
        bigint id PK
        bigint user_id FK
        varchar oss_key
        int duration_sec
        varchar status
        timestamp created_at
        timestamp completed_at
    }
    ANALYSIS_REPORT {
        bigint id PK
        bigint task_id FK
        jsonb result_data
        jsonb report_text
        varchar annotated_video_url
        varchar cover_image_url
        timestamp created_at
    }
    FEEDBACK_RECORD {
        bigint id PK
        bigint report_id FK
        bigint user_id FK
        boolean is_correct
        text comment
        timestamp created_at
    }
    MATCH {
        bigint id PK
        bigint user_id FK
        varchar opponent_name
        int opponent_rating
        varchar format
        varchar status
        timestamp created_at
    }
    SCORE_RECORD {
        bigint id PK
        bigint match_id FK
        int sequence
        varchar scorer
        varchar score_method
        timestamp created_at
    }
    MATCH_RECORD {
        bigint id PK
        bigint user_id FK
        varchar opponent_name
        int my_score
        int opponent_score
        boolean is_win
        timestamp match_date
    }
    USER_POINTS {
        bigint id PK
        bigint user_id FK
        int total_points
        int monthly_points
    }
    CHECKIN_RECORD {
        bigint id PK
        bigint user_id FK
        date checkin_date
        varchar checkin_type
    }
    SUBSCRIPTION {
        bigint id PK
        bigint user_id FK
        varchar tier
        timestamp start_at
        timestamp expire_at
        varchar status
    }
    ORDER {
        bigint id PK
        bigint user_id FK
        varchar order_no UK
        varchar product_type
        int amount_cents
        varchar status
        timestamp created_at
    }
    PAYMENT_RECORD {
        bigint id PK
        bigint order_id FK
        varchar transaction_id UK
        varchar payment_method
        int amount_cents
        timestamp paid_at
    }
    NOTIFICATION_RECORD {
        bigint id PK
        bigint user_id FK
        varchar type
        varchar title
        text content
        boolean is_read
        timestamp created_at
    }
    PROGRESS_SNAPSHOT {
        bigint id PK
        bigint user_id FK
        bigint report_id FK
        jsonb metrics_snapshot
        timestamp created_at
    }
    TECHNIQUE_TREND {
        bigint id PK
        bigint user_id FK
        varchar metric_name
        varchar trend_direction
        float change_rate
        int persistence_count
        jsonb time_series
        timestamp updated_at
    }
    PLAN_ADJUSTMENT {
        bigint id PK
        bigint training_plan_id FK
        bigint trigger_report_id FK
        jsonb old_plan_snapshot
        jsonb new_plan_snapshot
        text adjustment_reason
        timestamp created_at
    }
```

### 9.2 JSONB 字段存储策略

| 表 | JSONB 字段 | 内容结构 | 查询方式 |
|----|----------|---------|---------|
| `analysis_report` | `result_data` | 第 6.3 节定义的完整分析结果 JSON | 整体读取，不索引 |
| `analysis_report` | `report_text` | `{summary, issues[], suggestions[]}` | GIN 索引（按问题关键词搜索） |
| `user_profile` | `equipment_config` | `{blade: {...}, rubber_fh: {...}, rubber_bh: {...}, shoes: "..."}` | 整体读取 |
| `knowledge_entry` | `content` | 知识库条目结构化数据（动作要点/常见错误/训练方法） | GIN 索引 |
| `rule_definition` | `condition` | `{field, operator, threshold}` | 服务端解析，不索引 |
| `rule_definition` | `diagnosis` | `{problem_id, problem_name, severity, description}` | 整体读取 |
| `training_template` | `template_data` | `{goal, sessions[], exercises[], metrics[]}` | 整体读取 |
| `match_statistic` | `stats_data` | `{score_distribution, key_points, technique_breakdown}` | 整体读取 |
| `progress_snapshot` | `metrics_snapshot` | `{backhand_ratio: 0.25, forehand_ratio: 0.68, landing_dispersion: 3.2, ...}` | GIN 索引（按指标查询） |
| `technique_trend` | `time_series` | `[{date: "2026-07-10", value: 0.18}, ...]` | 整体读取 |
| `plan_adjustment` | `old_plan_snapshot` / `new_plan_snapshot` | 训练方案完整快照（目标/内容/量/检验） | 整体读取 |

> **GIN 索引策略**：对需要按 JSONB key 查询的字段（如 `report_text.issues`、`knowledge_entry.content`）创建 GIN 索引。对整体读取的字段不索引，避免写入性能下降。

### 9.3 高增长表分区/归档策略

| 表 | 预估增长 | 分区策略 | 归档策略 |
|----|---------|---------|---------|
| `video_task` | ~500/月（Phase 1）→ ~5000/月（增长期） | 按月分区（`PARTITION BY RANGE (created_at)`） | 1 年前任务归档到冷表 `video_task_archive` |
| `score_record` | ~5000/月（每场比赛 ~100 球） | 按月分区 | 1 年前记录归档 |
| `analysis_report` | ~500/月 | 不分区（JSONB 较大，分区反而降低查询效率） | 2 年前的报告 `result_data` 迁移到 OSS（PG 仅存元数据） |
| `notification_record` | ~10000/月 | 按月分区 | 3 个月前自动清理（`pg_cron` 定时任务） |
| `feedback_record` | ~150/月 | 不分区 | 永久保留（数据飞轮核心资产） |
| `progress_snapshot` | ~500/月（每次分析生成一条） | 不分区 | 永久保留（趋势分析基础数据） |
| `technique_trend` | ~9000/月（500 用户 × 18 指标） | 不分区 | 永久保留（更新而非新增） |
| `plan_adjustment` | ~50/月 | 不分区 | 永久保留（方案调整历史） |

> **分区实现**：使用 PostgreSQL 原生声明式分区，Alembic 迁移中创建分区表。每月初通过 `pg_cron` 自动创建下月分区。

---

## 10. 目录结构规范

```
TableTennisAnalysis/
├── backend/                       # 后端服务 (FastAPI)
│   ├── app/
│   │   ├── main.py               # FastAPI 应用入口
│   │   ├── core/                 # 核心基础设施
│   │   │   ├── config.py         # 配置管理 (.env + Pydantic Settings)
│   │   │   ├── database.py       # SQLAlchemy async engine + session
│   │   │   ├── redis.py          # Redis 连接池
│   │   │   ├── security.py       # JWT + 微信登录验证
│   │   │   ├── deps.py           # FastAPI 依赖注入
│   │   │   ├── response.py       # 统一响应格式
│   │   │   ├── pagination.py     # 分页工具
│   │   │   ├── exceptions.py     # 异常定义 + 全局处理器
│   │   │   └── enums.py          # 领域枚举 (会员等级/动作类型/比赛状态等)
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── __init__.py   # 路由聚合 (挂载 /api/v1)
│   │   │       ├── auth/         # 认证模块
│   │   │       ├── users/        # 用户模块
│   │   │       ├── video_analysis/  # 视频分析模块
│   │   │       ├── scoring/      # 记分牌模块
│   │   │       ├── match_data/   # 比赛数据模块
│   │   │       ├── dashboard/    # 数据看板模块
│   │   │       ├── training/     # 训练建议模块
│   │   │       ├── gamification/ # 游戏化模块
│   │   │       ├── membership/   # 会员模块
│   │   │       ├── payment/      # 支付模块
│   │   │       ├── notification/ # 通知模块
│   │   │       ├── 3d_teaching/      # 3D 教学模块 (Phase 2)
│   │   │       ├── opponent_analysis/ # 对手分析模块 (Phase 2)
│   │   │       ├── training/       # 训练模块 (含 training_advice P1 + training_plan P2)
│   │   │       ├── progress/       # 进度分析模块 (快照/趋势/对比/方案评估)
│   │   │       ├── community/      # 社区模块 (Phase 3)
│   │   │       ├── learning_video/ # 学习视频模块 (Phase 3)
│   │   │       ├── creator_center/ # 创作者中心模块 (Phase 3)
│   │   │       ├── social_match/   # 约球模块 (Phase 3)
│   │   │       ├── venue_search/   # 球馆搜索模块 (Phase 3)
│   │   │       ├── tournament/   # 赛事模块 (Phase 4)
│   │   │       ├── ranking/      # 排名模块 (Phase 4)
│   │   │       ├── ecommerce/    # 电商模块 (Phase 4)
│   │   │       ├── credit_score/  # 信用分模块 (Phase 4)
│   │   │       ├── advanced_analysis/ # 高级分析模块 (Phase 2)
│   │   │       ├── monthly_report/ # 月度报告模块 (Phase 2)
│   │   │       ├── admin/        # 管理后台模块
│   │   │       └── ws.py         # WebSocket 端点
│   │   ├── services/             # 业务服务层
│   │   │   ├── auth_service.py
│   │   │   ├── user_service.py
│   │   │   ├── video_analysis_service.py
│   │   │   ├── scoring_service.py
│   │   │   ├── training_service.py
│   │   │   ├── payment_service.py
│   │   │   ├── knowledge_base_service.py
│   │   │   ├── rule_engine_service.py
│   │   │   ├── kqs_integration_service.py
│   │   │   └── ...
│   │   ├── models/               # SQLAlchemy 数据模型
│   │   │   ├── user.py
│   │   │   ├── video_analysis.py
│   │   │   ├── scoring.py
│   │   │   ├── match_data.py
│   │   │   ├── gamification.py
│   │   │   ├── membership.py
│   │   │   ├── payment.py
│   │   │   ├── community.py
│   │   │   ├── tournament.py
│   │   │   ├── knowledge_base.py
│   │   │   └── ...
│   │   ├── schemas/              # Pydantic 请求/响应模型
│   │   └── ai_pipeline/          # AI 分析流水线
│   │       ├── tasks.py          # Celery 任务定义
│   │       ├── pipeline.py       # 流水线编排
│   │       ├── progress.py       # 进度追踪
│   │       └── report_generator.py  # 报告生成 (规则引擎 + LLM)
│   ├── alembic/                  # 数据库迁移
│   ├── tests/                    # 测试
│   │   ├── conftest.py
│   │   ├── unit/
│   │   └── integration/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
│
├── ai_inference/                  # AI 推理服务 (独立部署)
│   ├── app/
│   │   ├── main.py               # FastAPI 推理服务入口
│   │   ├── models/               # 模型加载与管理
│   │   │   ├── ball_detection.py # TTNet/TrackNet 球体检测
│   │   │   ├── ball_tracking.py  # 卡尔曼滤波追踪
│   │   │   ├── table_detection.py # YOLO-pose 球台检测
│   │   │   ├── pose_estimation.py # MediaPipe 姿态估计
│   │   │   ├── action_recognition.py # Temporal CNN 动作识别
│   │   │   └── landing_estimation.py # 落点估算
│   │   ├── api/
│   │   │   └── inference.py      # 推理 API 端点
│   │   ├── utils/
│   │   │   ├── video_processor.py # FFmpeg 视频处理
│   │   │   └── result_aggregator.py # 结果聚合
│   │   └── config.py
│   ├── weights/                  # 模型权重文件 (gitignore)
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                     # 前端应用 (Taro 4)
│   ├── src/
│   │   ├── app.tsx               # Taro 应用入口
│   │   ├── app.config.ts         # 全局配置 (tabBar/路由)
│   │   ├── pages/                # 页面组件
│   │   │   ├── home/             # Tab 1: 首页
│   │   │   ├── training/         # Tab 2: 训练
│   │   │   ├── events/          # Tab 3: 赛事
│   │   │   ├── community/       # Tab 4: 社区 (Phase 3)
│   │   │   └── profile/         # Tab 5: 我的
│   │   ├── components/           # 通用组件
│   │   │   ├── ScoreBoard/       # 记分牌组件
│   │   │   ├── AnalysisReport/  # 分析报告组件
│   │   │   ├── DataChart/        # 数据图表组件 (ECharts)
│   │   │   ├── ThreeViewer/      # 3D 查看器组件
│   │   │   └── ...
│   │   ├── stores/               # Zustand 状态管理
│   │   │   ├── authStore.ts
│   │   │   ├── analysisStore.ts
│   │   │   ├── scoringStore.ts
│   │   │   └── ...
│   │   ├── services/             # API 调用封装
│   │   │   ├── request.ts        # HTTP 请求封装
│   │   │   ├── auth.ts
│   │   │   ├── videoAnalysis.ts
│   │   │   └── ...
│   │   ├── utils/                # 工具函数
│   │   │   ├── websocket.ts      # WebSocket 封装
│   │   │   ├── upload.ts         # OSS 直传封装
│   │   │   └── ...
│   │   ├── three/                # 3D 模块 (跨端适配层)
│   │   │   ├── adapter.ts        # 平台适配 (R3F / threejs-miniprogram)
│   │   │   ├── SceneManager.ts   # 场景管理
│   │   │   ├── AnimationPlayer.ts # 动画播放控制
│   │   │   └── ModelLoader.ts    # GLB 模型加载
│   │   ├── styles/               # 全局样式
│   │   └── constants/            # 常量定义
│   ├── config/
│   │   ├── index.ts              # Taro 编译配置
│   │   ├── dev.ts                # 开发环境配置
│   │   └── prod.ts               # 生产环境配置
│   ├── package.json
│   └── tsconfig.json
│
├── docs/                         # 项目文档
│   ├── 01需求分析/
│   ├── 02界面设计/
│   └── 03系统架构/
│
├── scripts/                      # 管理脚本
│   ├── init_knowledge_base.py    # 知识库初始化脚本
│   ├── train_model.py            # 模型 fine-tune 脚本
│   └── export_annotations.py     # 标注数据导出脚本
│
├── docker-compose.yml            # 开发环境编排
├── docker-compose.prod.yml       # 生产环境编排
└── .env.example                  # 环境变量模板
```

> **Anti-hallucination 约束**：
> 1. 每个后端 API 模块遵循 `router.py` + `service.py` + `schemas.py` + `models.py` 标准结构
> 2. 新增数据模型必须在 `app/models/__init__.py` 中导入，Alembic 自动检测
> 3. AI 推理服务 (`ai_inference/`) 独立部署在 GPU 实例，不与主业务服务混部
> 4. 3D 模块 (`frontend/src/three/`) 封装跨端适配层，业务代码不直接调用 Three.js API
> 5. Celery 任务定义必须在 `app/ai_pipeline/tasks.py` 中注册

---

## 11. 安全规范

### 11.1 认证与授权

| 机制 | 实现 | 配置 |
|------|------|------|
| 微信登录 | 小程序: wx.login() → code2session → openid | 小程序 AppID + AppSecret |
| 手机号登录 | App: 短信验证码登录 | 短信服务商集成 (阿里云短信) |
| Access Token | JWT (HS256)，携带 jti + user_id | 过期: 120 分钟 (`ACCESS_TOKEN_EXPIRE_MINUTES`) |
| Refresh Token | JWT，单独签发 | 过期: 7 天 (`REFRESH_TOKEN_EXPIRE_DAYS`) |
| Token 撤销 | Redis SET 存储已撤销 jti | 无 Redis 时优雅降级 |
| 权限守卫 | FastAPI Depends 链 | `get_current_user` → `require_membership(tier)` → `require_creator` |
| 免费额度控制 | Redis 计数器 (每日 3 次分析) | 每日 00:00 重置 |

### 11.2 API 安全

| 机制 | 实现 | 说明 |
|------|------|------|
| CORS | FastAPI CORSMiddleware | 开发: 允许 localhost; 生产: 仅配置域名 |
| 请求限流 | slowapi (Redis 后端) | 全局: 100 req/min; AI 分析: 10 req/hour (免费用户) |
| 文件上传 | 类型白名单 + 大小限制 | 视频: mp4/mov, ≤500MB; 图片: jpg/png, ≤10MB |
| SQL 注入 | SQLAlchemy 参数化查询 | 全程 ORM，禁止裸 SQL 拼接 |
| XSS | 前端文本插值，非 dangerouslySetInnerHTML | 社区内容服务端过滤 HTML |
| 内容审核 | 敏感词过滤 + 人工审核队列 | 社区帖子/评论/视频 UGC |
| 签名验证 | 微信支付回调验签 + 微信消息验签 | 微信平台证书 + APIv3 |

### 11.3 数据安全

| 机制 | 说明 |
|------|------|
| 密码存储 | bcrypt 哈希，禁止明文 |
| 敏感字段脱敏 | 手机号/身份证/支付信息不在日志中打印 |
| 视频隐私 | 用户视频默认私有，分析报告分享需用户主动操作 |
| OSS 访问控制 | STS Token 临时授权，15 分钟过期；私有 Bucket |
| HTTPS 强制 | 全站 HTTPS，HTTP 自动 301 跳转 |
| 开球网积分 | 用户授权后才同步，不在前端缓存完整积分历史 |

### 11.4 数据合规 (PIPL)

> 遵守《中华人民共和国个人信息保护法》(PIPL) 的合规要求。

| 合规项 | 实现方案 | 对应模块 |
|--------|---------|---------|
| 隐私政策 | 用户首次登录展示隐私政策弹窗，需明确同意后方可使用 | auth |
| 用户授权 | 收集手机号/位置/微信信息前单独授权（微信授权框） | auth, user |
| 数据留存策略 | 见下方留存表 | file_management, admin |
| 被遗忘权 | 用户注销账号 → 72h 内删除个人信息（手机号/位置/头像），视频转为匿名归档 | user (account_deletion) |
| 数据可携带权 | 用户可导出个人数据（JSON 格式：档案/比赛记录/分析报告摘要） | admin (数据导出工具) |
| 敏感数据加密 | 手机号 AES-256 加密存储，位置信息仅保留到区级精度 | user |
| 第三方数据共享 | 微信登录/支付/地图仅传输必要数据，不共享用户个人信息 | auth, payment |

#### 数据留存策略

| 数据类型 | 留存期 | 到期处理 |
|---------|--------|---------|
| 原始上传视频 | 90 天热存储 → 1 年冷存储 | 1 年后从 OSS 删除 |
| 标注视频（分析结果） | 与原始视频同期 | 同上 |
| 分析报告（JSONB） | 永久 | 不删除（用户可手动删除） |
| 比赛记录/记分数据 | 永久 | 不删除 |
| 用户反馈记录 | 永久 | 不删除（数据飞轮资产） |
| 操作日志 | 6 个月 | 6 个月后自动清理 |
| 微信 session_key | 15 分钟 | Redis 自动过期 |
| 手机号 | 用户注销后 72h 内删除 | — |

#### 用户注销流程

```mermaid
graph LR
    Request["用户申请注销"] --> Verify{"验证身份<br/>(二次确认 + 密码/验证码)"}
    Verify -->|通过| Anonymize["匿名化处理<br/>(昵称→已注销用户<br/>头像→默认<br/>手机号→删除)"]
    Verify -->|失败| Reject["拒绝注销"]
    Anonymize --> Archive["视频转为匿名归档<br/>(保留用于数据飞轮)"]
    Archive --> Revoke["撤销所有 JWT Token"]
    Revoke --> Done["注销完成 (72h 内生效)"]
```

---

## 12. 专项算法设计

### 12.1 乒乓大数据——间接胜利算法

> 需求：A 战胜 B，B 战胜 C → A "间接战胜" C。展示"间接战胜马龙/孙颖莎"等趣味数据。

#### 问题描述

间接胜利是一个有向图可达性问题。全图 BFS/DFS 随用户量增长计算成本极高（O(V+E)），不可实时计算。

#### 设计方案：预计算 + 缓存 + 深度限制

```mermaid
graph TB
    MatchFinish["比赛结束<br/>(A 战胜 B)"]
    TriggerUpdate["触发异步更新任务<br/>(Celery task)"]
    BFS["受限 BFS<br/>(从 A 出发，沿胜利边遍历<br/>最多 4 层)"]
    UpdateRedis["更新 Redis 缓存<br/>(A 的间接胜利集合)"]
    UpdateDB["更新 PostgreSQL<br/>(间接战胜最高分/名人列表)"]

    MatchFinish --> TriggerUpdate
    TriggerUpdate --> BFS
    BFS --> UpdateRedis
    UpdateRedis --> UpdateDB
```

| 参数 | 值 | 说明 |
|------|-----|------|
| 最大遍历深度 | 4 层 | A→B→C→D→E，覆盖绝大多数有意义路径 |
| 缓存 Key | `big_data:user:{uid}` | Redis Hash |
| 缓存 TTL | 24h | 过期后下次查询重新计算 |
| 计算触发 | 比赛结束后异步 Celery 任务 | 不阻塞比赛记分流程 |
| 名人匹配 | 预置名人积分 ID 列表（马龙/孙颖莎等国手开球网 ID） | 匹配间接胜利集合中的名人 ID |

> **降级策略**：用户量 < 1000 时可全量计算；用户量增长后深度限制为 4 层 + 缓存。极端情况下（图过大）仅计算 3 层。

### 12.2 智能组队算法（Phase 4）

> 需求：现场活动按开球网积分智能匹配队伍，保证实力平均。

#### 蛇形分配算法

```
输入：N 名球员，按积分降序排序 [P1, P2, P3, ..., PN]
目标：分成 K 队，每队实力尽可能平均

算法（蛇形分配）：
  第 1 轮：P1→队1, P2→队2, ..., PK→队K
  第 2 轮：P(K+1)→队K, P(K+2)→队(K-1), ..., P(2K)→队1  （反向）
  第 3 轮：P(2K+1)→队1, P(2K+2)→队2, ...
  ...依此类推

结果：每队积分总和尽可能接近
```

| 参数 | 说明 |
|------|------|
| 时间复杂度 | O(N log N)（排序）+ O(N)（分配），现场秒级完成 |
| 积分来源 | 用户开球网积分（`user_profile.kqs_rating`） |
| 人数不等时 | 人数不能整除 K 时，部分队伍多 1 人 |
| 手动调整 | 组队结果展示后，组织者可手动微调（拖拽换人） |

### 12.3 搜索服务架构

| 阶段 | 方案 | 适用场景 |
|------|------|---------|
| Phase 1-2 | PostgreSQL 全文搜索（`tsvector` + `GIN` 索引） | 分析报告搜索、训练模板搜索 |
| Phase 3+ | Meilisearch（轻量搜索引擎） | 社区帖子/视频/球馆/装备全文搜索 |

> **选型理由**：Meilisearch 比 Elasticsearch 更轻量（单二进制部署），适合个人开发者。支持中文分词、模糊搜索、 typo-tolerance。Phase 3 社区上线后内容量增长，PG 全文搜索性能不足时引入。

#### PostgreSQL 全文搜索示例（Phase 1-2）

```sql
-- 分析报告按问题关键词搜索
CREATE INDEX idx_report_text_gin ON analysis_report
  USING GIN (to_tsvector('simple', report_text::text));

SELECT * FROM analysis_report
WHERE to_tsvector('simple', report_text::text) @@ to_tsquery('simple', '反手 & 落点');
```

### 12.4 内容审核流程（Phase 3）

```mermaid
graph TB
    Submit["用户提交内容<br/>(帖子/评论/视频)"]
    AutoCheck["自动审核<br/>(敏感词过滤 + 图片/视频 API)"]
    AutoResult{"自动审核结果"}
    AutoResult -->|通过| Publish["自动发布"]
    AutoResult -->|可疑| ManualQueue["人工审核队列"]
    AutoResult -->|违规| Reject["拒绝 + 通知用户"]

    ManualQueue --> ManualReview["管理员审核"]
    ManualReview -->|通过| Publish
    ManualReview -->|拒绝| Reject

    Report["用户举报"]
    Report --> ManualQueue

    Publish --> Monitor["发布后监控<br/>(关键词更新回溯)"]
    Monitor -->|发现违规| Unpublish["下架 + 通知作者"]
```

| 审核层 | 技术 | 说明 |
|--------|------|------|
| 敏感词过滤 | 自维护敏感词库 + DFA 算法 | 文本内容实时过滤，~1ms/10万字 |
| 图片审核 | 阿里云内容安全 API | 色情/暴恐/广告检测，~200ms/图 |
| 视频审核 | 阿里云视频审核 API | 抽帧审核，~30s/分钟视频 |
| 审核时效 | 帖子/评论 < 1min（自动），视频 < 30min | 创作者视频需人工复审 |
| 举报 SLA | 24h 内处理 | 紧急举报（涉政/违法）2h 内处理 |

### 12.5 嵌入式视频模式方案（Phase 3）

> 学习视频三种模式中"嵌入模式"的技术实现。

| 模式 | 实现方案 | 技术细节 |
|------|---------|---------|
| 嵌入模式 | iframe 嵌入第三方播放器（B站/抖音/YouTube） | 仅存储外链 URL + 元数据，不下载不重新托管 |
| 授权本地化 | 下载到 OSS + 平台播放器 | 创作者授权后下载，CDN 分发，支持慢放/逐帧 |
| UGC | 用户上传到 OSS + 平台播放器 | 创作者直接上传，需审核后上线 |

#### 嵌入模式技术细节

- **iframe 播放器**：B站 `//player.bilibili.com/player.html?bvid=xxx`，抖音/YouTube 各有嵌入 API
- **外链可用性监控**：每日定时任务检查嵌入视频外链是否有效（HTTP HEAD 请求），失效则标记"视频已下架"
- **信息流统一展示**：嵌入视频在社区信息流中与平台内视频统一展示，缩略图 + 来源标注（"来自B站"）
- **版权声明**：嵌入页面底部标注"本视频来自 {平台}，版权归原作者所有"
- **跟练模式**：嵌入模式不支持跟练（无法控制播放器速度），仅授权本地化和 UGC 支持

### 12.6 CDN 缓存策略

| 资源类型 | CDN 缓存 TTL | 缓存失效策略 | 回源比例 |
|---------|-------------|-------------|---------|
| 3D 模型 (GLB) | 1 年 | 版本化 URL（`model_v2.glb`），更新即新 URL | <1% |
| 标注视频 | 30 天 | 报告删除时 CDN 缓存自然过期 | <5% |
| 用户头像 | 7 天 | 用户更新头像 → URL 加 `?v=timestamp` 参数 | <10% |
| 分析报告图片 | 30 天 | 不更新（历史快照） | <1% |
| 前端静态资源 | 1 年 | 文件名 hash 化（`app.a3f8b2.js`），发布即新文件 | <1% |
| 教学视频缩略图 | 30 天 | 创作者更新 → CDN 刷新 API 主动刷新 | <5% |

> **缓存刷新**：头像/缩略图等用户可变资源，更新后调用 CDN 刷新 API（阿里云 `RefreshObjectCaches`）主动刷新。

### 12.7 进度分析与历史趋势架构

> **设计目标**：将训练建议从"单次报告快照式"升级为"基于历史数据对比的趋势式"，使训练方案更科学、可动态调整。

#### 架构总览

```mermaid
graph TB
    subgraph DataSources["数据源（已有）"]
        AnalysisReport["分析报告<br/>(ANALYSIS_REPORT JSONB)"]
        MatchData["比赛数据<br/>(MATCH / MATCH_RECORD)"]
        MatchStats["比赛统计<br/>(MATCH_STATISTIC)"]
    end

    subgraph ProgressAnalysis["进度分析模块 (新增)"]
        SnapshotGenerator["进度快照生成器<br/>(每次分析后自动触发)"]
        TrendCalculator["趋势计算器<br/>(指标变化方向/速率/持续性)"]
        ComparisonEngine["对比引擎<br/>(报告间/时间区间对比)"]
        ProgressAssessor["方案有效性评估器<br/>(目标达成度/停滞检测)"]
    end

    subgraph RuleEngineEnhanced["增强规则引擎"]
        PatternMatcherEnhanced["增强问题匹配器<br/>(单次 + 趋势 + 持续性)"]
        TrainingRecommenderEnhanced["增强训练推荐器<br/>(基于趋势的差异化建议)"]
        PlanAdjuster["方案调整器<br/>(动态调整训练方案)"]
    end

    subgraph Output["输出"]
        ContextualAdvice["上下文训练建议<br/>(含进步确认/持续问题/方案评估)"]
        AdjustedPlan["调整后训练方案<br/>(版本化记录)"]
        TrendData["趋势数据<br/>(供看板/月报展示)"]
    end

    AnalysisReport --> SnapshotGenerator
    MatchData --> SnapshotGenerator
    MatchStats --> SnapshotGenerator
    SnapshotGenerator --> TrendCalculator
    TrendCalculator --> ComparisonEngine
    TrendCalculator --> ProgressAssessor
    ComparisonEngine --> PatternMatcherEnhanced
    ProgressAssessor --> PatternMatcherEnhanced
    PatternMatcherEnhanced --> TrainingRecommenderEnhanced
    TrainingRecommenderEnhanced --> PlanAdjuster
    TrainingRecommenderEnhanced --> ContextualAdvice
    PlanAdjuster --> AdjustedPlan
    TrendCalculator --> TrendData
```

#### 进度快照生成

每次 AI 分析报告生成后，自动从报告 JSONB 中提取关键指标，生成一条进度快照：

```mermaid
sequenceDiagram
    participant Pipeline as AI 流水线
    participant Progress as 进度分析服务
    participant DB as PostgreSQL
    participant RuleEngine as 规则引擎

    Pipeline->>Progress: 分析完成 (report_id)
    Progress->>DB: 读取 analysis_report.result_data
    Progress->>Progress: 提取 18 项关键指标
    Progress->>DB: 写入 progress_snapshot
    Progress->>DB: 读取该用户历史快照 (最近 N 条)
    Progress->>Progress: 计算趋势 (方向/变化率/持续性)
    Progress->>DB: 更新 technique_trend
    Progress->>RuleEngine: 传入 最新报告 + 历史趋势 + 方案进度
    RuleEngine-->>Progress: 增强训练建议 + 方案调整建议
    Progress->>DB: 存储增强建议
    Note over Progress: 如检测到停滞 → 触发方案调整
```

**可追踪的 18 项技术指标**（对应知识库数据维度定义）：

| 指标 Key | 来源 | 说明 |
|----------|------|------|
| `backhand_ratio` | `technique_stats` | 反手使用率 |
| `forehand_ratio` | `technique_stats` | 正手使用率 |
| `serve_ratio` | `technique_stats` | 发球占比 |
| `landing_forehand_pct` | `landing_points.distribution` | 落点正手区比例 |
| `landing_backhand_pct` | `landing_points.distribution` | 落点反手区比例 |
| `landing_middle_pct` | `landing_points.distribution` | 落点中区比例 |
| `landing_dispersion` | `landing_points` 计算 | 落点分散度（九宫格熵值） |
| `avg_rally_length` | `rally_analysis` | 平均回合长度 |
| `max_rally_length` | `rally_analysis` | 最长回合长度 |
| `rally_frequency` | `rally_analysis` | 击球频率 |
| `avg_ball_speed` | `ball_speed` | 平均球速（范围值中值） |
| `max_ball_speed` | `ball_speed` | 最大球速 |
| `score_win_rate` | `score_analysis` | 得分率 |
| `key_point_win_rate` | `score_analysis` | 关键分得分率 |
| `serve_point_win_rate` | `score_analysis` | 发球轮得分率 |
| `receive_point_win_rate` | `score_analysis` | 接发球轮得分率 |
| `attack_transition_rate` | `action_sequence` 计算 | 攻防转换率 |
| `error_rate` | `action_sequence` 计算 | 失误率 |

#### 趋势计算规则

| 趋势类型 | 判定条件 | 建议生成策略 |
|---------|---------|------------|
| 📈 改善中 | 连续 ≥ 2 次分析，指标向目标值靠近，变化率 > 5% | "进步确认 + 维持当前方案" |
| ➡️ 停滞 | 连续 ≥ 3 次分析，指标变化率 < 5%，未达目标 | "停滞警告 + 调整方案/增加训练量" |
| 📉 退步 | 连续 ≥ 2 次分析，指标远离目标值，变化率 > 5% | "退步警告 + 诊断原因 + 调整方案" |
| ✅ 已达标 | 指标达到目标值并保持 ≥ 2 次分析 | "目标达成 + 维持/设新目标" |
| 🆕 新问题 | 最新报告中出现但历史报告中未出现过的问题 | "新问题识别 + 针对性建议" |
| 🔄 已解决 | 历史报告中存在但最近 2 次报告中消失的问题 | "问题已改善 + 确认/巩固建议" |

#### 增强规则定义示例

```json
{
  "rule_id": "RULE_TREND_001",
  "rule_name": "反手使用率持续偏低",
  "rule_type": "trend_persistent",
  "condition": {
    "field": "technique_stats.backhand_ratio",
    "operator": "<",
    "threshold": 0.30,
    "persistence_count": 3,
    "time_window_days": 90
  },
  "diagnosis": {
    "problem_id": "PROBLEM_003",
    "problem_name": "反手使用率持续不足",
    "severity": "high",
    "description": "反手使用率 {latest_value}，已连续 {persistence_count} 次分析低于推荐值 30%（历史趋势: {trend_summary}）"
  },
  "training_methods": ["METHOD_012", "METHOD_015", "METHOD_022"],
  "training_plan_template": "TPL_BACKHAND_INTENSIVE",
  "adjustment_action": "escalate_plan"
}
```

```json
{
  "rule_id": "RULE_TREND_002",
  "rule_name": "反手使用率改善中",
  "rule_type": "trend_improving",
  "condition": {
    "field": "technique_stats.backhand_ratio",
    "operator": "improving_toward",
    "target": 0.30,
    "min_change_rate": 0.05,
    "consecutive_count": 2
  },
  "diagnosis": {
    "problem_id": "PROBLEM_003",
    "problem_name": "反手使用率正在改善",
    "severity": "low",
    "description": "反手使用率从 {previous_value} 提升至 {latest_value}（+{change_rate}），趋势向好"
  },
  "training_methods": ["METHOD_012", "METHOD_015"],
  "training_plan_template": null,
  "adjustment_action": "maintain_current_plan"
}
```

#### 训练方案动态调整闭环

```mermaid
graph LR
    subgraph PlanLoop["方案调整闭环"]
        NewReport["新分析报告"]
        Snapshot["生成进度快照"]
        Trend["计算趋势"]
        Assess{"方案有效性评估"}
        Maintain["维持当前方案<br/>(进步中)"]
        Adjust["调整方案<br/>(停滞/退步)"]
        Escalate["升级方案<br/>(持续问题)"]
        NewGoal["设新目标<br/>(已达标)"]
        Version["方案版本化记录"]
    end

    NewReport --> Snapshot --> Trend --> Assess
    Assess -->|改善中| Maintain
    Assess -->|停滞| Adjust
    Assess -->|退步| Escalate
    Assess -->|已达标| NewGoal
    Maintain --> Version
    Adjust --> Version
    Escalate --> Version
    NewGoal --> Version
```

**方案调整记录**：

每次方案调整生成一条 `PLAN_ADJUSTMENT` 记录，包含：
- 旧方案快照 → 新方案快照（diff 对比）
- 调整原因（趋势分析结论）
- 触发报告 ID（哪次分析触发了调整）
- 用户可见的调整说明（"你的反手训练已连续3次分析无明显改善，已将训练重点从多球练习调整为实战对抗练习"）

#### 报告对比功能

支持用户选择任意两次历史分析报告进行对比：

| 对比维度 | 展示内容 |
|---------|---------|
| 技术统计对比 | 正/反手使用率变化（±N%） |
| 落点分布对比 | 两次九宫格热图并排 + 差异高亮 |
| 回合数据对比 | 平均回合长度/击球频率变化 |
| 球速对比 | 平均/最大球速变化（范围值） |
| 得分分析对比 | 得分率/关键分表现变化 |
| 问题变化 | 新增问题 / 已解决问题 / 持续问题 |

#### 进度综合摘要

`GET /progress/summary` 返回：

```json
{
  "user_id": 123,
  "summary_period": "last_3_months",
  "total_analyses": 8,
  "overall_progress": "improving",
  "metric_trends": [
    {
      "metric": "backhand_ratio",
      "metric_name": "反手使用率",
      "current_value": 0.32,
      "previous_value": 0.25,
      "change_rate": 0.28,
      "trend": "improving",
      "target": 0.35,
      "target_progress": 91,
      "history": [
        {"date": "2026-07-10", "value": 0.18},
        {"date": "2026-07-25", "value": 0.22},
        {"date": "2026-08-10", "value": 0.25},
        {"date": "2026-08-28", "value": 0.28},
        {"date": "2026-09-15", "value": 0.30},
        {"date": "2026-10-01", "value": 0.32}
      ]
    }
  ],
  "problem_changes": {
    "resolved": ["发球落点单一"],
    "new": ["反手拉球引拍过大"],
    "persistent": ["正手落点偏集中"]
  },
  "training_plan_status": {
    "current_plan_id": "plan_xxx",
    "plan_version": 3,
    "last_adjustment": "2026-09-15",
    "adjustment_reason": "反手训练连续3次分析改善，维持当前方案",
    "goal_completion": {
      "backhand_ratio": "91% (32%/35%)",
      "landing_dispersion": "60% (熵值4.2/7.0)"
    }
  }
}
```

---

## 13. 运维与质量保障

### 13.1 监控指标与告警

#### 关键监控指标

| 指标类别 | 指标名 | 阈值（告警） | 告警级别 | 说明 |
|---------|--------|------------|---------|------|
| API 性能 | P95 响应延迟 | > 500ms | ⚠️ 警告 | 排查慢查询/GC |
| API 性能 | P99 响应延迟 | > 2s | 🔴 严重 | 可能影响用户体验 |
| API 错误率 | 5xx 错误率 | > 1% | 🔴 严重 | 服务异常 |
| AI 流水线 | 队列积压深度 | > 10 | ⚠️ 警告 | GPU 处理跟不上 |
| AI 流水线 | 单任务分析耗时 | > 10 min | ⚠️ 警告 | 可能卡死 |
| AI 流水线 | 分析失败率 | > 5% | 🔴 严重 | 模型/服务问题 |
| GPU | GPU 利用率 | < 20% 持续 10 min | ℹ️ 信息 | 考虑缩容 |
| GPU | GPU 实例不可用 | — | 🔴 严重 | Spot 被抢占 |
| WebSocket | 活跃连接数 | > 5000 | ⚠️ 警告 | 考虑拆分 |
| 数据库 | 连接池使用率 | > 80% | ⚠️ 警告 | 扩容连接池 |
| 数据库 | 慢查询数 | > 10/min | ⚠️ 警告 | 索引/查询优化 |
| Redis | 内存使用率 | > 80% | ⚠️ 警告 | 检查大 Key |
| 业务 | 免费额度消耗率 | 日均 > 90% | ℹ️ 信息 | 接近上限 |

#### 告警分级与响应

| 级别 | 响应时间 | 通知方式 | 示例 |
|------|---------|---------|------|
| 🔴 严重 | 15 min 内 | 短信 + 微信 + 邮件 | 服务宕机、GPU 不可用、5xx > 5% |
| ⚠️ 警告 | 1h 内 | 微信 + 邮件 | 队列积压、慢查询增多 |
| ℹ️ 信息 | 次日处理 | 邮件汇总 | GPU 利用率低、日度成本报告 |

> **个人开发者值班策略**：非工作时间仅 🔴 级别触发短信通知；⚠️ 和 ℹ️ 聚合到每日邮件报告。

### 13.2 成本监控与预算告警

| 成本项 | 预估月成本 (Phase 1) | 监控方式 | 预算告警阈值 |
|--------|---------------------|---------|-------------|
| GPU (T4 Spot) | ¥354 | 阿里云账单 API + 日粒度 | 月 80% (¥283) |
| OSS 存储 | ¥50-100 | OSS 用量 API | 月 80% |
| CDN 流量 | ¥100-300 | CDN 用量 API | 月 80% |
| LLM API | ¥50-200 (按分析量) | 自建请求计数 + 成本估算 | 日 ¥20 告警 |
| 短信 | ¥30-100 | 短信平台 API | 日 ¥10 告警 |
| 高德地图 API | ¥0-100 (免费额度内) | 调用计数 | 日 80% 免费额度 |
| PostgreSQL RDS | ¥200-400 | 阿里云账单 API | 月 80% |
| Redis | ¥100-200 | 阿里云账单 API | 月 80% |
| **合计** | **¥884-1754** | | 月总预算 ¥2000 |

> **免费用户成本控制**：每日 3 次免费分析 × 单次 GPU 成本 ¥0.2 = ¥0.6/用户/天。1000 用户 × 30 天 = ¥18000/月（峰值）。实际利用率约 10-20%，预估 ¥1800-3600/月。通过限流 + 排队控制并发，避免 GPU 突发成本。

### 13.3 测试策略

| 测试层 | 覆盖范围 | 工具 | 覆盖目标 |
|--------|---------|------|---------|
| 单元测试 | 核心服务层（规则引擎/积分计算/组队算法/乒乓大数据） | pytest + pytest-asyncio | > 80% |
| 集成测试 | API 端点 + 数据库（CRUD 全流程） | pytest + httpx (AsyncClient) | 核心模块 100% |
| AI 模型评估 | 球检测准确率/动作识别准确率/落点精度 | 独立评估脚本 + 标注测试集 | 每次模型更新必测 |
| 前端 E2E | 关键用户流程（登录→上传→分析→报告→记分→支付） | Playwright (Taro H5 mode) | 5 核心流程 |
| 负载测试 | API 并发 + AI 队列并发 | locust | 100 并发不降级 |

#### AI 模型评估流程

```
1. 准备标注测试集（~100 段视频，人工标注球位置/动作/落点）
2. 运行评估脚本：python scripts/evaluate_model.py --model {version} --dataset {test_set}
3. 输出指标：
   - 球检测：Recall@95%Precision
   - 动作识别：Top-1 Accuracy（目标 > 95%，当前论文 99.37%）
   - 落点精度：九宫格准确率 + 平均误差距离
4. 与上一版本对比，如精度下降 > 2% 则阻止部署
5. 通过后标记为 candidate，灰度 10% 流量验证
```

> **测试数据管理**：AI 测试集存储在 OSS（视频文件）+ GitHub LFS（标注 JSON）。标注测试集与数据飞轮的标注数据分离，避免测试数据泄露到训练集。

---

## 14. 部署架构

### 14.1 开发环境

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────┐
│  Taro Dev     │────▶│  FastAPI          │────▶│  PostgreSQL   │
│  :10086       │proxy│  uvicorn :8000    │     │  :5432        │
└──────────────┘     └──────────────────┘     └───────────────┘
                            │
                     ┌──────▼──────┐
                     │  Redis :6379│ (队列 + 缓存)
                     └─────────────┘
                            │
                     ┌──────▼──────┐
                     │  Celery     │ (AI 流水线 Worker)
                     │  Worker     │
                     └─────────────┘
                            │
                     ┌──────▼──────┐
                     │  AI 推理    │ (本地 CPU 或远程 GPU)
                     │  :8001      │
                     └─────────────┘

docker-compose.yml 统一编排以上所有服务
```

### 14.2 生产环境

```
                          ┌─────────────┐
                          │  微信小程序  │
                          │  / App / H5 │
                          └──────┬──────┘
                                 │ HTTPS
                          ┌──────▼──────┐
                          │  阿里云 SLB  │ (负载均衡)
                          └──────┬──────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
             ┌──────▼───┐ ┌─────▼────┐ ┌─────▼────┐
             │  Nginx   │ │  Nginx   │ │  Nginx   │
             │  + FastAPI│ │ + FastAPI│ │ + FastAPI│ (多实例)
             │  Gunicorn│ │ Gunicorn │ │ Gunicorn │
             └──────┬───┘ └─────┬────┘ └─────┬────┘
                    │           │            │
                    └───────────┼────────────┘
                                │
                    ┌───────────┼───────────┐
                    │           │           │
             ┌──────▼───┐ ┌────▼─────┐ ┌───▼──────┐
             │PostgreSQL│ │  Redis   │ │  OSS     │
             │  RDS     │ │  云版    │ │  对象存储│
             │ (主从)   │ │          │ │ + CDN    │
             └──────────┘ └──────────┘ └──────────┘

                    ┌───────────────────────┐
                    │   Celery Worker 集群  │
                    │   (视频分析异步处理)    │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   GPU 实例 (T4 Spot)   │
                    │   AI 推理服务          │
                    │   (按需启动/关闭)      │
                    └───────────────────────┘

外部服务: 微信开放平台 / 开球网 API / LLM API / 高德地图 API
```

### 14.3 GPU 实例弹性部署

| 场景 | 实例配置 | 预估月成本 | 说明 |
|------|---------|-----------|------|
| Phase 1 验证期 | 1× T4 Spot (按需) | ~354 元 | 低流量，无任务时关闭 |
| Phase 1 增长期 | 1-2× T4 Spot (自动伸缩) | ~500-1000 元 | 随队列积压自动扩容 |
| Phase 2+ 稳定期 | 2-4× T4 Spot (自动伸缩) | ~1000-3000 元 | 高峰多实例并行 |

### 14.4 环境变量清单

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | Yes | — | PostgreSQL 连接串 `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `REDIS_URL` | Yes | — | Redis 连接串 `redis://host:6379/0` |
| `JWT_SECRET_KEY` | Yes | `change-me-in-production` | JWT 签名密钥 (生产必须修改) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | 120 | Access Token 有效期 (分钟) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | 7 | Refresh Token 有效期 (天) |
| `WECHAT_APPID` | Yes | — | 微信小程序 AppID |
| `WECHAT_APP_SECRET` | Yes | — | 微信小程序 AppSecret |
| `WECHAT_PAY_MCH_ID` | Yes | — | 微信支付商户号 |
| `WECHAT_PAY_API_V3_KEY` | Yes | — | 微信支付 APIv3 密钥 |
| `WECHAT_PAY_CERT_SERIAL_NO` | Yes | — | 微信支付证书序列号 |
| `WECHAT_PAY_PRIVATE_KEY_PATH` | Yes | — | 微信支付商户私钥路径 |
| `OSS_ACCESS_KEY_ID` | Yes | — | 阿里云 OSS AccessKey |
| `OSS_ACCESS_KEY_SECRET` | Yes | — | 阿里云 OSS Secret |
| `OSS_BUCKET_NAME` | Yes | — | OSS Bucket 名称 |
| `OSS_REGION` | Yes | — | OSS 区域 (如 oss-cn-hangzhou) |
| `OSS_CDN_DOMAIN` | No | — | CDN 加速域名 |
| `AI_INFERENCE_URL` | Yes | — | AI 推理服务地址 |
| `AI_ANALYSIS_TIMEOUT_SECONDS` | No | 600 | AI 分析任务超时 (秒) |
| `LLM_API_URL` | Yes | — | LLM API 地址 (OpenAI 兼容) |
| `LLM_API_KEY` | Yes | — | LLM API 密钥 |
| `LLM_MODEL` | No | — | 使用的模型名称 |
| `LLM_ENABLED` | No | true | LLM 降级开关，false 时报告生成降级为纯规则引擎 |
| `BIG_DATA_MAX_DEPTH` | No | 4 | 乒乓大数据间接胜利最大遍历深度 |
| `VIDEO_STANDARD_FPS` | No | 30 | 视频标准化帧率 |
| `VIDEO_STANDARD_RESOLUTION` | No | 1920x1080 | 视频标准化分辨率 |
| `VIDEO_TRANSCODE_TIMEOUT` | No | 300 | 视频转码超时 (秒) |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | No | 5 | 熔断器失败阈值 |
| `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` | No | 60 | 熔断器恢复等待 (秒) |
| `GPU_HEALTH_CHECK_INTERVAL` | No | 10 | GPU 健康检查间隔 (秒) |
| `H5_DOMAIN` | Yes | — | H5 降级页面域名（如 https://h5.pingpongai.com） |
| `H5_TOKEN_EXPIRE_SECONDS` | No | 300 | H5 降级 Token 过期时间 (秒) |
| `KQS_API_URL` | No | — | 开球网 API 地址 (Phase 4) |
| `KQS_API_KEY` | No | — | 开球网 API 密钥 (Phase 4) |
| `AMAP_API_KEY` | Yes | — | 高德地图 API Key |
| `MAX_VIDEO_UPLOAD_BYTES` | No | 524288000 | 视频上传大小上限 (500MB) |
| `FREE_ANALYSIS_DAILY_LIMIT` | No | 3 | 免费用户每日分析次数 |
| `CELERY_BROKER_URL` | No | `{REDIS_URL}` | Celery broker (默认同 Redis) |
| `SENTRY_DSN` | No | — | Sentry 错误监控 DSN (可选) |

---

## 15. 分阶段实施映射

### 15.1 Phase 1 → 架构落地清单

| 序号 | 架构任务 | 交付物 | 依赖 |
|------|---------|--------|------|
| 1 | 后端框架搭建 | FastAPI 骨架 + 核心基础设施 (config/database/redis/security) | — |
| 2 | 数据库设计 | Phase 1 表结构 + Alembic 迁移 | 1 |
| 3 | 认证模块 | 微信登录 + JWT + 手机号登录 | 1, 2 |
| 4 | 用户模块 | 个人档案 + 开球网积分 + 打法 + 乒乓大数据 | 3 |
| 5 | 文件管理 | OSS STS 直传 + CDN 分发 | 1 |
| 6 | AI 推理服务 | TTNet 球检测 + 球台检测 + 追踪 + 落点 + 姿态 + 动作识别 | 5 |
| 7 | AI 流水线 | Celery 流水线编排 + 进度追踪 + WebSocket 推送 | 6, 5 |
| 8 | 视频分析模块 | 上传 → 分析 → 报告 → 反馈 | 7, 5 |
| 9 | 知识库初始化 | 专业知识库结构化导入 PostgreSQL | 2 |
| 10 | 规则引擎 | 规则定义 + 问题匹配 + 训练建议生成 | 9 |
| 11 | 记分牌模块 | 比赛设置 + 实时记分 + WebSocket 同步 + 统计 | 3, 2 |
| 12 | 数据看板 | 战绩趋势 + 技术统计 + 落点热图 + ECharts | 8, 11 |
| 13 | 游戏化 | 训练积分 + 打卡日历 + 基础徽章 | 8, 11 |
| 14 | 会员 + 支付 | 四级会员 + 微信支付 + 免费额度控制 | 3 |
| 15 | 前端框架 | Taro 4 骨架 + 5 Tab 导航 + 路由守卫 | — |
| 16 | 前端首页 | Dashboard + 快捷入口 + 打卡日历 + 最近报告 | 15 |
| 17 | 前端训练 Tab | 拍摄引导 + 上传 + 处理中 + 分析报告 | 15, 8 |
| 18 | 前端赛事 Tab | 记分牌全流程 + 比赛记录 | 15, 11 |
| 19 | 前端我的 Tab | 个人档案 + 会员中心 + 积分历史 | 15, 4, 14 |

### 15.2 补充说明：Phase 1 落地清单更新

> v2.0 更新：在 Phase 1 落地清单中增加以下任务（对应差距分析修复项）：

| 序号 | 架构任务 | 交付物 | 对应差距 |
|------|---------|--------|---------|
| 20 | 视频转码子流程 | FFmpeg 标准化转码 + 多清晰度输出 + 封面图 | 2.4 视频转码 |
| 21 | AI 熔断与降级 | 熔断器状态机 + Spot 抢占处理 + LLM 降级开关 | 2.6 熔断降级 |
| 22 | 通知分发策略 | 通道选择矩阵 + 微信订阅管理 + Celery Beat 定时 | 2.5 通知分发 |
| 23 | PIPL 合规 | 隐私政策弹窗 + 数据留存 + 注销流程 + 数据导出 | 2.7 PIPL 合规 |
| 24 | 乒乓大数据算法 | 受限 BFS + Redis 缓存 + Celery 触发 | 2.3 乒乓大数据 |
| 25 | 数据库 ER 设计 | Phase 1 ER 图 + JSONB 策略 + 分区策略 | 2.1 数据库设计 |
| 26 | API 端点设计 | Phase 1 各模块 API 清单 | 2.2 API 设计 |
| 27 | 监控告警体系 | 指标表 + 告警分级 + 成本看板 | 3.6/3.7 监控成本 |
| 28 | 测试策略 | 单元/集成/AI 评估/E2E | 3.5 测试策略 |
| 29 | 进度分析模块 | 进度快照生成 + 趋势计算 + 报告对比 + 增强规则引擎 | 8, 10 |

> 这些任务与原有 Phase 1 任务并行，不额外增加 Phase 1 周期。

### 15.2 后续 Phase 架构扩展点（更新）

| Phase | 架构扩展 | 新增基础设施 | 新增服务 |
|-------|---------|------------|---------|
| Phase 2 | 3D 教学集成 + 高级分析 + 训练方案 | OSS 3D 模型存储 + CDN | Blender 内容生产流程 |
| Phase 3 | 社区 + 创作者经济 + 约球 + 球馆 | 内容审核服务 + 搜索引擎 | 高德地图 LBS 服务 |
| Phase 4 | 赛事 + 电商 + 信用分 + 开球网对接 | — | 开球网 API 集成 |
| Phase 5 | 多角度分析 + B 端 SaaS + 国际化 | 多 GPU 实例集群 | i18n 国际化层 |

---

## Anti-Hallucination 约束

1. **技术版本**：必须与本设计文档第 2 节表格一致，不得编造版本号
2. **跨平台框架**：确定为 Taro 4 (React 体系)，不使用 uni-app
3. **后端语言**：确定使用 Python (FastAPI)，不使用 Node.js / Go
4. **数据库**：确定使用 PostgreSQL + PostGIS，不使用 MongoDB（理由见 2.7 节）
5. **后端架构**：统一 FastAPI 后端，不使用微信云开发双后端方案（理由见 2.7 节）
6. **AI 模型**：球体检测使用 TTNet/TrackNetV5（非通用 YOLO）；追踪使用卡尔曼滤波（非 DeepSORT）；动作识别使用 Temporal CNN
7. **3D 引擎**：确定使用 Three.js + React Three Fiber（非 Unity WebGL）
8. **3D 模型**：ReadyPlayerMe + Blender 自主制作（非真人/动捕数据）
9. **模块命名**：所有后端模块使用 snake_case，位于 `app/api/v1/` 和 `app/services/` 下；模块矩阵名称 = API 目录名称（见 4 节命名一致性约束）
10. **API 前缀**：所有业务 API 挂载在 `/api/v1` 下
11. **响应格式**：统一 `{code, message, data, timestamp}` 四字段结构
12. **模型注册**：新增 SQLAlchemy 模型必须在 `app/models/__init__.py` 中导入
13. **AI 服务独立部署**：AI 推理服务 (`ai_inference/`) 部署在 GPU 实例，不与主业务服务混部
14. **球速精度**：误差 20-30%，展示时必须使用范围值并标注"估算"
15. **积分体系**：不自建独立积分体系，延用开球网积分
16. **创作者分成**：不低于 75-80%，平台抽 20-25%
17. **视频转码**：AI 分析输入必须标准化为 1080p/30fps/H.264；多清晰度输出与 AI 分析并行
18. **AI 熔断**：连续 5 次失败触发熔断，60s 后半开探测；LLM 降级由 `LLM_ENABLED` 环境变量控制
19. **乒乓大数据**：间接胜利遍历深度限制 4 层，结果 Redis 缓存 TTL 24h
20. **数据留存**：原始视频 90 天热存储 → 1 年冷存储 → 删除；用户注销 72h 内删除个人信息
21. **搜索服务**：Phase 1-2 使用 PostgreSQL 全文搜索；Phase 3+ 评估 Meilisearch（非 Elasticsearch）
22. **内容审核**：文本 DFA 敏感词过滤；图片/视频使用阿里云内容安全 API
23. **跨端策略**：Phase 1 小程序优先（83% 功能原生），重功能通过 web-view 嵌入 H5 降级；App Phase 2+ 补充，iOS/Android 一套 RN 代码
24. **H5 降级**：H5 降级页面复用 Taro H5 编译产物，不额外开发；认证通过一次性 H5 Token 透传（5 分钟过期）
25. **小程序分包**：主包 ≤2MB（5 Tab + 认证 + 公共组件），按 Tab 拆分 4 个分包各 ≤2MB，总计 ≤8MB
23. **训练建议**：训练建议必须基于历史数据对比（进度快照 + 技术趋势），不可仅基于单次分析报告；每次分析后自动生成进度快照并更新趋势
24. **进度快照**：每次 AI 分析完成后自动生成一条 `progress_snapshot` 记录；快照永久保留作为趋势分析基础数据
25. **方案调整**：训练方案检测到停滞（连续 3 次分析无改善）时自动触发方案重新评估；调整记录版本化存储
