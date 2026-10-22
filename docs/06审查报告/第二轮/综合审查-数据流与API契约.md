# 综合审查报告 — 数据流与 API 契约一致性

> **审查日期**：2026-10-12
> **审查范围**：需求分析 v0.4、系统架构 v2.4、模块详细设计 v1.2、数据库设计 v1.4、API 详细设计 v1.3、12 个后端切片、5 个基础设施切片
> **审查维度**：8 个维度（视频上传→分析→报告、记分→统计、分析报告→反馈→训练建议、会员→支付→订阅、游戏化事件链、跨模块依赖图、Schema/响应一致性、错误码一致性）
> **审查性质**：只读审查，未修改任何源文件

---

## 目录

1. [审查总览](#1-审查总览)
2. [维度 1：视频上传 → 分析 → 报告数据流](#2-维度-1视频上传--分析--报告数据流)
3. [维度 2：记分牌 → 统计数据流](#3-维度-2记分牌--统计数据流)
4. [维度 3：分析报告 → 反馈 → 训练建议数据流](#4-维度-3分析报告--反馈--训练建议数据流)
5. [维度 4：会员 → 支付 → 订阅数据流](#5-维度-4会员--支付--订阅数据流)
6. [维度 5：游戏化事件链](#6-维度-5游戏化事件链)
7. [维度 6：跨模块 API 依赖图](#7-维度-6跨模块-api-依赖图)
8. [维度 7：Schema/响应一致性](#8-维度-7schema响应一致性)
9. [维度 8：错误码一致性](#9-维度-8错误码一致性)
10. [P0-P3 分级汇总](#10-p0-p3-分级汇总)
11. [优化建议](#11-优化建议)

---

## 1. 审查总览

### 1.1 审查文档清单

| 文档 | 版本 | 覆盖度 |
|------|------|--------|
| 需求分析与路线图 | v0.4 | 核心章节已读 |
| 系统架构设计 | v2.4 | 全文 3345 行已读 |
| 模块详细设计 | v1.2 | §2.11-2.12, §3.1-3.5 已读 |
| 数据库详细设计 | v1.4 | 已读 |
| API 详细设计 | v1.3 | 全文 ~3200 行已读 |
| 后端切片 01-12 | — | 全部已读 |
| 基础设施切片 13 | — | 全部 5 个已读 |

### 1.2 审查方法

- **逐维度追踪**：对每个数据流维度，从入口 API → Service 层 → 数据库 → 跨模块调用 → 输出 API 进行全链路追踪
- **交叉比对**：架构设计 § vs 模块详细设计 § vs API 详细设计 § vs 切片设计实现
- **一致性校验**：响应字段名/类型、错误码、Redis Key 命名、状态枚举值在各文档间交叉比对
- **依赖图构建**：从切片代码中提取模块间 import/call 关系，构建依赖图并验证与架构 § 4 模块矩阵的一致性

---

## 2. 维度 1：视频上传 → 分析 → 报告数据流

### 2.1 数据流追踪

```
[1] POST /video-analysis/upload-token
    → file_management: 校验文件类型(mp4/mov)+大小(≤500MB)
    → 生成 OSS Key: videos/raw/{user_id}/{yyyymmdd}/{uuid}.mp4
    → STS Token 签发 (PutObject 权限, 15min 过期)
    → 创建 file_record (status=uploading)
    → 返回 {file_id, oss_key, sts_credentials, upload_url}

[2] 客户端直传 OSS (PutObject)

[3] POST /video-analysis/upload-complete
    → file_management: HEAD Object 校验文件存在 + Content-Length 匹配
    → 更新 file_record (status=uploaded, oss_etag, actual_size, uploaded_at)

[4] POST /video-analysis/tasks
    → membership: check_membership() / Redis INCR quota:analysis:{uid}:{date}
    → 创建 video_task (status=queued)
    → Celery: ai_pipeline 入队
    → 返回 {task_id, task_uuid, status, estimated_wait_minutes}

[5] Celery ai_pipeline 10 步流水线:
    Step 1: 视频预处理 (FFmpeg 标准化→1080p/30fps/H.264)
    Step 2: 球台检测 (YOLO-pose → 四角坐标 + 单应性矩阵)
    ── Step 1-2 可并行 ──
    Step 3: 球体检测 (TTNet/TrackNetV5 → 每帧 bbox)
    Step 4: 球体追踪 (卡尔曼滤波 → 连续轨迹)
    Step 5: 落点估算 (单应性矩阵映射 → 九宫格)
    ── Step 3-5 串行级联 ──
    Step 6: 姿态估计 (MediaPipe → 33 关键点)
    Step 7: 动作识别 (Temporal CNN → 21 类动作)
    ── Step 6-7 串行, 与 Step 3-5 并行 ──
    Step 8: 回合分割 (弹跳事件+节奏 → 回合边界)
    Step 9: 报告生成 (规则引擎+LLM → result_data + report_text)
    Step 10: 标注视频 (FFmpeg → 球轨迹叠加 MP4)
    → 每步: pipeline_step 记录 + WS push analysis_progress

[6] Step 9 完成后: ReportGenerator._trigger_cascade()
    → celery_app.send_task() 异步触发:
      a. progress_snapshot 生成 (18 项关键指标)
      b. training_advice 生成 (规则引擎匹配)
      c. dashboard cache bust (redis.delete)
      d. notification WS push analysis_complete

[7] GET /video-analysis/reports/{id}
    → 返回 {result_data, report_text, annotated_video_url, cover_image_url, report_images}
```

**文档参考**：
- API § 4.1-4.6（upload-token, upload-complete, tasks, report detail）
- 架构 § 6.1-6.5（AI 流水线规格、数据结构、转码策略、熔断降级）
- 模块设计 § 3.2（ai_pipeline 模块 BR-1~BR-4）
- 切片 03-video_analysis/backend.md（VideoAnalysisService 实现）
- 切片 13-infrastructure/ai_pipeline.md（ReportGenerator._trigger_cascade）
- 切片 13-infrastructure/file_management.md（STS 签发、HEAD 校验、孤儿清理）

### 2.2 发现

#### F1-1 [P2] 视频标准化转码的归属位置不一致

| 文档 | 描述 |
|------|------|
| 架构 § 6.4 | "标准化转码是 AI 流水线 Step 1 的**前置**，转码完成后触发 AI 分析" |
| 模块设计 § 3.2 BR-1 | Step 1 名称="视频预处理"，输入=`oss_key`(原始视频)，输出="标准化帧序列" |
| 切片 ai_pipeline | Step 1 `_step1_preprocess()` 内部调用 FFmpeg 进行标准化转码 |

**问题**：架构说转码是 Step 1 的前置（独立步骤），但模块设计和切片实现将转码包含在 Step 1 内部。这导致：
- 转码超时（架构 § 6.4 定为 5 分钟）与 Step 1 超时（模块设计定为 120s）冲突
- 若转码失败，架构描述为"通知用户视频格式不支持"，但切片实现中 Step 1 失败走流水线重试逻辑

**建议**：统一为"Step 1 = 视频预处理（含标准化转码）"，架构 § 6.4 的"前置"描述改为"Step 1 的第一个子步骤"。转码超时 300s 应与 Step 1 超时 120s 对齐，建议 Step 1 超时调整为 300s。

#### F1-2 [P2] 级联触发机制：架构同步 vs 切片异步

| 文档 | 描述 |
|------|------|
| 架构 § 12.7 | 进度快照生成用同步 sequenceDiagram：Pipeline→Progress→DB→RuleEngine→Progress→DB |
| 切片 ai_pipeline | `ReportGenerator._trigger_cascade()` 使用 `celery_app.send_task()` 异步触发 |

**问题**：架构的 sequenceDiagram 暗同步调用链（Pipeline 等待 Progress 完成），但切片实现为异步 fire-and-forget。这导致：
- 架构描述的用户体验：分析完成后立即可查看训练建议（同步保证）
- 切片实现的用户体验：分析完成后训练建议可能有延迟（异步任务排队）
- 若异步任务失败，无重试/补偿机制描述

**建议**：架构 § 12.7 的 sequenceDiagram 应标注为"逻辑流程"而非"调用时序"，并明确说明实际实现采用 Celery 异步触发。在切片中补充异步任务的失败重试策略（如 3 次重试 + 告警）。

#### F1-3 [P3] estimated_wait_minutes 计算方法未定义

| 文档 | 描述 |
|------|------|
| API § 4.3 | 响应包含 `estimated_wait_minutes: 5` |
| 切片 03 | 返回硬编码值 5，注释 "TODO: 根据队列深度计算" |

**问题**：API 契约定义了字段但未定义计算规则，切片实现为硬编码。

**建议**：定义估算公式 `estimated_wait_minutes = ceil(queue_depth * avg_task_duration / gpu_instances)`，或 Phase 1 接受固定值 5 并在 API 文档中标注"Phase 1 为估算值"。

---

## 3. 维度 2：记分牌 → 统计数据流

### 3.1 数据流追踪

```
[1] POST /scoring/matches
    → 创建 match (status=setup, opponent_name, format, match_type, target_score)
    → 返回 {match_id, status, current_server}

[2] POST /scoring/matches/{id}/start
    → 状态守卫: 仅 setup → in_progress
    → 更新 match.status, 记录 started_at
    → Redis: scoring:match:{id}:status = in_progress

[3] POST /scoring/matches/{id}/score (循环记分)
    → Redis INCR match:{id}:seq → 全局序号
    → 写入 score_record (seq, scorer, score_method, technique_action)
    → 更新 match current_score + current_server (自动轮换发球)
    → WS push score_update 到 ws:match:{id}
    → 达到赛制要求 → 自动触发 finish

[4] POST /scoring/matches/{id}/finish
    → 状态守卫: 仅 in_progress → finished
    → 生成 match_statistic (stats_data: score_distribution, key_points, technique_breakdown)
    → 返回 {match_id, final_score, is_win, statistic_id}

[5] 比赛结束后: match_data 模块创建 match_record + score_detail
    → (跨模块触发方式未明确定义)

[6] GET /scoring/matches/{id}/statistics
    → 返回 stats_data

[7] 撤销: POST /scoring/matches/{id}/undo
    → 校验最新球 seq == 本地记录
    → 删除最后一条 score_record, 回退 current_score
    → WS push score_update {action: undo}

[8] 多设备同步:
    → 设备 B 断连重连 → WS reconnect → 加入 ws:match:{id}
    → 读取 match:{id}:current_score + 最近 N 条 score_record
    → WS push sync_match (全量同步)
```

**文档参考**：
- API § 5.1-5.10（matches CRUD, score, undo, finish, statistics, start, abandon, resume）
- 架构 § 12.8（比赛状态机、多设备同步协议、并发冲突处理、撤销同步）
- 切片 04-scoring/backend.md（ScoringService 实现）
- 切片 05-match_data/backend.md（MatchDataService 实现）

### 3.2 发现

#### F2-1 [P2] 比赛结束后 scoring → match_data 的跨模块触发未定义

| 文档 | 描述 |
|------|------|
| 架构 § 9.1 ER | MATCH ‖--‖ MATCH_STATISTIC; MATCH_RECORD 为独立表 |
| API § 5.6 | finish 返回 `statistic_id`，但未提及 match_record 创建 |
| API § 7.1 | POST /match-data/records 是用户手动创建比赛记录 |
| 切片 04 | finish 方法只生成 match_statistic，不调用 match_data 模块 |
| 切片 05 | MatchDataService 的 create_record 方法独立创建 match_record |

**问题**：scoring 模块比赛结束后，match_data 模块的 match_record 是通过用户手动 POST /match-data/records 创建的，而非自动从 scoring 同步。但 API § 7.1 的"详细录入"模式包含 `details` 数组（score_detail），这些数据应来自 scoring 的 score_record。架构和 API 均未描述：
- scoring finish 后是否自动创建 match_record？
- 若自动创建，match_record.details 从 score_record 导入的字段映射是什么？
- 若不自动创建，用户需要手动重新录入比分，体验差且数据可能不一致

**建议**：明确定义 scoring finish 后自动调用 match_data 模块创建 match_record，从 score_record 导入 score_detail。字段映射：`score_record.seq → score_detail.sequence`, `score_record.scorer → score_detail.scorer`, `score_record.score_method → score_detail.score_method`, `score_record.technique_action → score_detail.technique_action`。同时允许用户通过 PATCH /match-data/records/{id} 补充修改。

#### F2-2 [P3] 发球轮换算法未定义

| 文档 | 描述 |
|------|------|
| API § 5.4 | 响应包含 `current_server` 字段 |
| 架构 § 12.8 | 仅提及"自动轮换发球"，未定义规则 |
| 切片 04 | `_rotate_server()` 实现为每 2 球轮换 |

**问题**：发球轮换规则（每 2 球轮换？每 5 球轮换？决胜期每 1 球轮换？）在架构和 API 中均未定义。切片实现为每 2 球轮换，但乒乓球规则中 11 分制为每 2 球轮换、决胜期(10:10后)每 1 球轮换。

**建议**：架构 § 12.8 补充发球轮换规则：每 2 球轮换发球方；10:10 平分后每 1 球轮换。API § 5.4 的业务规则补充此条。

#### F2-3 [P3] match_id 与 match_record.id 的关联关系未在 API 中体现

| 文档 | 描述 |
|------|------|
| 架构 § 9.1 | MATCH_RECORD 有 `match_id FK` 字段（关联到 MATCH） |
| API § 7.4 | PATCH /match-data/records/{id} 业务规则："若比赛记录关联了记分牌比赛（match_id 不为空），返回 403 禁止编辑" |
| API § 7.1 | POST /match-data/records 请求体无 match_id 字段 |

**问题**：API § 7.1 创建比赛记录时不接受 match_id，但 § 7.4 又检查 match_id 是否为空。如果手动录入不支持关联 match_id，那只有自动同步（若实现）才能设置 match_id。这与 F2-1 问题相关联。

**建议**：POST /match-data/records 请求体增加可选 `match_id` 字段，允许从记分牌比赛导入时关联。或明确文档说明 match_id 仅由系统内部同步设置。

---

## 4. 维度 3：分析报告 → 反馈 → 训练建议数据流

### 4.1 数据流追踪

```
[1] AI 流水线 Step 9 生成 analysis_report
    → result_data JSONB (落点/技术/回合/球速/得分)
    → report_text JSONB (summary, issues[], suggestions[])
    → LLM 降级: LLM_ENABLED=false → 纯规则引擎生成, is_llm_generated=false

[2] 级联触发 (异步):
    → progress_analysis: 生成 progress_snapshot (18 项指标)
    → progress_analysis: 读取历史快照 → 计算 technique_trend
    → knowledge_base: 规则引擎匹配 (单次规则+趋势规则+改善规则+停滞规则)
    → 生成增强训练建议 (诊断+建议+方案调整)
    → 存储到 training_plan + plan_adjustment

[3] GET /training/advice/{report_id}
    → 返回 {diagnosis[], suggestions[], training_methods[], training_plan_template}
    → is_first_analysis: 是否为用户首次分析

[4] GET /training/advice/contextual
    → 自动取用户最新报告，返回同 [3]

[5] POST /video-analysis/reports/{id}/feedback
    → 创建 feedback_record (is_correct, comment)
    → is_correct=true → 视频标记为标注候选 (数据飞轮)
    → is_correct=false → 进入人工审核队列

[6] 训练方案管理:
    GET /training/plans/{id}/adjustments → 方案调整历史
    POST /training/plans/{id}/re-evaluate → 手动触发方案重新评估
    GET /training/plans/{plan_id}/sessions → 训练单列表
    POST /training/plans/{plan_id}/sessions/{session_id}/complete → 标记完成 (+5 gamification points)

[7] 进度分析:
    GET /progress/snapshots → 快照列表
    GET /progress/technique-trends → 全部指标趋势
    GET /progress/technique-trends/{metric} → 单项指标详情
    GET /progress/comparison → 两次报告对比
    GET /progress/summary → 综合摘要 (含 forecast)
    GET /progress/problem-changes → 问题变化列表
```

**文档参考**：
- API § 4.8（feedback）、§ 8.1-8.8（training advice, templates, plans, sessions）
- API § 9.1-9.6（progress snapshots, trends, comparison, summary, problem-changes）
- 架构 § 8.2-8.3（规则引擎架构、规则定义示例）
- 架构 § 12.7（进度分析与历史趋势架构）
- 切片 07-training_advice/backend.md（TrainingAdviceService 实现）
- 切片 08-progress_analysis/backend.md（ProgressAnalysisService 实现）
- 切片 13-infrastructure/knowledge_base.md（KnowledgeBaseService 实现）

### 4.2 发现

#### F3-1 [P1] 训练建议存储的模块归属不清晰

| 文档 | 描述 |
|------|------|
| 架构 § 12.7 | 进度分析模块存储"增强训练建议" |
| 切片 07 | TrainingAdviceService 提供 GET /training/advice/{report_id} 端点 |
| 切片 08 | ProgressAnalysisService 在级联中生成并存储训练建议 |
| API § 8.1 | GET /training/advice/{report_id} 归属训练模块 |

**问题**：架构 § 12.7 的流程图显示：Pipeline → ProgressAnalysis → RuleEngine → ProgressAnalysis(存储增强建议)。但 API § 8.1 的 GET /training/advice/{report_id} 端点归属 training_advice 模块。这意味着：
- 训练建议由 progress_analysis 模块生成并存储
- 但由 training_advice 模块的 API 端点提供查询
- training_advice 模块查询的数据由 progress_analysis 模块写入
- 两个模块共享 training_plan 表，但各自的写入/读取职责未明确划分

**建议**：明确模块边界：
- progress_analysis 模块负责：快照生成、趋势计算、方案评估（写入 progress_snapshot, technique_trend, plan_adjustment）
- training_advice 模块负责：训练建议生成（调用 knowledge_base 规则引擎）、训练方案管理、训练单管理（写入/读取 training_plan, training_session）
- 级联触发中，ai_pipeline 应调用 training_advice 模块（而非 progress_analysis）生成训练建议，再调用 progress_analysis 模块生成快照和趋势

#### F3-2 [P2] 训练单完成触发积分的跨模块容错未定义

| 文档 | 描述 |
|------|------|
| API § 8.8 | 业务规则第 4 条："触发 gamification 积分（+5）" |
| 切片 07 | `session_complete()` 调用 `GamificationService.add_points(user_id, 5, "training_session")` |
| 切片 09 | `GamificationService.add_points()` 为同步方法调用 |

**问题**：训练单完成时同步调用 gamification 模块加分。若 gamification 模块 DB 异常，训练单完成操作也会失败。这种同步跨模块调用没有 try-catch 或降级策略。

**建议**：在 training_advice 的 `session_complete()` 中，将 gamification 加分包装在 try-except 中，失败时记录日志但不阻塞训练单完成。或改用 Celery 异步任务触发加分。

#### F3-3 [P2] training_advice sessions 端点在模块详细设计中缺失

| 文档 | 描述 |
|------|------|
| API § 8.7-8.8 | 定义了 GET /training/plans/{plan_id}/sessions 和 POST complete 端点 |
| 模块详细设计 § 2 | 无 training_advice 模块章节（模块设计仅到 § 2.12 通知模块） |
| 切片 07 | 完整实现了 sessions 端点 |

**问题**：模块详细设计文档缺少 training_advice 模块的完整设计。sessions 相关的 BR（业务规则）只在 API 文档和切片中定义，未在模块详细设计中体现。这违反了"模块详细设计 → API 详细设计 → 切片设计"的文档层级关系。

**建议**：在模块详细设计文档中补充 training_advice 模块章节，包含训练建议生成、训练方案管理、训练单管理的完整业务规则。

#### F3-4 [P3] 反馈→数据飞轮的后续处理流程不完整

| 文档 | 描述 |
|------|------|
| API § 4.8 | is_correct=false → "进入人工审核队列" |
| 模块设计 § 3.5 | admin 模块 F3 "内容审核队列" 标注为 P1, Phase 3 社区上线后激活 |
| 切片 03 | feedback_record.status 初始为 "pending" |

**问题**：反馈审核队列在 Phase 1 标为 P1 但 admin 模块的审核功能要到 Phase 3 才激活。Phase 1 期间的 is_correct=false 反馈无人处理，feedback_record 永远停留在 "pending" 状态。

**建议**：Phase 1 期间定义简单的反馈处理流程：开发者直接在 admin 后台查看反馈列表，手动标记为 "reviewed"。或在 Phase 1 限制反馈仅做数据收集（不触发审核流程），Phase 3 再激活审核队列。

---

## 5. 维度 4：会员 → 支付 → 订阅数据流

### 5.1 数据流追踪

```
[1] POST /payment/orders
    → 创建 order (status=pending, product_type, tier, period)
    → 调用微信统一下单 (JSAPI/APP)
    → 返回 {order_id, order_no, amount_cents, payment_params}

[2] 用户在微信中支付

[3] 微信异步回调: POST /payment/notify
    → 验签 (Wechatpay-Signature, 平台证书)
    → 解密 (AEAD_AES_256_GCM, APIv3 密钥)
    → 查找 order by out_trade_no
    → 幂等检查: order.status == 'paid' → 200 SUCCESS (不重复处理)
    → 更新 order (status=paid, paid_at=NOW())
    → 创建 payment_record (transaction_id, payment_method, amount_cents)
    → 触发业务逻辑:
        membership → 创建/续期 subscription (start_at=NOW(), expire_at=start_at+period)
        analysis_pack → Redis INCR quota:bonus:{uid}
    → WS push payment_success {order_id, product_type} 到 ws:user:{uid}
    → 返回 200 {"code":"SUCCESS","message":"成功"}

[4] 会员状态查询:
    GET /membership/current → {tier, status, start_at, expire_at, days_remaining}
    GET /membership/quota → {tier, daily_limit, used_today, remaining, reset_at}

[5] 会员校验 (在其他模块中):
    video_analysis: POST /video-analysis/tasks → check_membership()
        免费: Redis INCR quota:analysis:{uid}:{date}, 超 3 → DECR 回退 → 403
        会员: 直接入队
    training_advice: POST /training/plans/{id}/re-evaluate → require 会员
    training_advice: GET /training/plans/{plan_id}/sessions → require 会员

[6] 到期检测:
    Celery Beat 每日 00:30 扫描 subscription 表:
        expire_at 在未来 3 天 → 标记 expiring_soon, 发续费提醒
        expire_at 已过期 → 标记 expired, 触发权益降级
        expire_at 过期超 7 天 → 标记 closed
    实时校验: 每次请求会员功能时检查 expire_at (兜底)

[7] 退款: POST /payment/orders/{id}/refund (管理员)
    → 调用微信退款 API
    → 创建 refund_record (status=processing)
    → 退款成功 → 撤销会员权益
```

**文档参考**：
- API § 11.1-11.3（membership tiers, current, quota）
- API § 12.1-12.4（payment orders, notify, refund）
- 架构 § 12.9（订阅生命周期、续费方式、到期检测、权益降级、免费额度计数器）
- 模块设计 § 2.11（支付模块 BR-1, BR-2, 支付回调流程图）
- 切片 10-membership/backend.md（MembershipService 实现）
- 切片 11-payment/backend.md（PaymentService 实现）

### 5.2 发现

#### F4-1 [P2] 支付回调部分失败的补偿机制未定义

| 文档 | 描述 |
|------|------|
| 模块设计 § 2.11 BR-2 | "支付成功后业务处理"：更新 order → 创建 payment_record → 触发业务逻辑 → WS 推送 |
| 架构 § 12.9 | 到期检测、权益降级机制 |

**问题**：支付回调的业务流程为：order.status=paid → payment_record → subscription 创建/续期 → WS 推送。若在 subscription 创建步骤失败（DB 异常），order 已标记为 paid 但 subscription 未创建。用户已付款但无会员权益。文档未描述：
- 是否有 DB 事务包裹（order 更新 + subscription 创建应在同一事务中）
- 若 subscription 创建失败，order 是否回滚为 pending
- 若 WS 推送失败，是否影响业务逻辑（应该不影响，但未明确）

**建议**：明确 payment 模块的 `_trigger_business_logic()` 使用 DB 事务，order 更新 + payment_record 创建 + subscription 创建/续期 在同一事务中。WS 推送放在事务提交后执行，失败时仅记录日志。补充补偿机制：Celery Beat 定时扫描 status=paid 但无 subscription 的 order，重试业务逻辑。

#### F4-2 [P3] expiring_soon 状态未在 API 中暴露

| 文档 | 描述 |
|------|------|
| 架构 § 12.9 | 订阅生命周期包含 `expiring_soon` 状态（到期前 3 天） |
| API § 11.2 | GET /membership/current 响应 status 字段值未定义枚举 |

**问题**：架构定义了 5 种订阅状态（active, expiring_soon, expired, grace_period, closed），但 API § 11.2 的响应示例只展示了 `status: "active"`。`expiring_soon` 状态未在 API 响应中明确定义，前端无法通过 API 获知订阅即将到期（只能通过通知消息）。

**建议**：API § 11.2 补充 status 字段的枚举值定义（active, expiring_soon, expired, grace_period, closed），并在响应中增加 `days_remaining` 字段（已有但需明确计算方式）。前端可根据 status 和 days_remaining 展示续费提醒。

#### F4-3 [P3] 免费额度计数的 Redis Key TTL 不一致

| 文档 | 描述 |
|------|------|
| 架构 § 12.9 | "Redis Key 设置 TTL 至当日 23:59:59 + 1h" |
| 切片 10 | `quota:analysis:{uid}:{date}` TTL 设置为 "次日 00:00:00 + 1h" |

**问题**：架构描述为 23:59:59 + 1h（即次日 00:59:59），切片实现为次日 00:00:00 + 1h（即次日 01:00:00）。两者相差约 1 分钟，功能影响不大但描述不一致。

**建议**：统一为"次日 00:00:00 + 1h"，架构 § 12.9 描述同步更新。

---

## 6. 维度 5：游戏化事件链

### 6.1 数据流追踪

```
积分来源 (同步调用 GamificationService.add_points):
  ├─ video_analysis: 分析完成 → +N points
  ├─ scoring: 比赛结束 (win) → +N points + streak bonus
  ├─ match_data: 比赛记录创建 → +N points
  ├─ training_advice: 训练单完成 → +5 points
  └─ gamification: 手动打卡 → +2 points

积分存储:
  → user_points 表 (total_points, monthly_points)
  → checkin_record 表 (checkin_date, checkin_type)

徽章检查:
  → badge_definition.condition JSONB (metric, operator, threshold)
  → 评估条件是否满足 → 颁发徽章 → user_badge 表
  → badge_progress 表 (current_value, target_value, progress_pct)

打卡日历:
  → checkin_record 按月聚合
  → streak_days 计算 (连续打卡天数)
```

**文档参考**：
- API § 10.1-10.4（points, checkin-calendar, checkin, badges）
- 架构 § 9.1 ER（USER_POINTS, CHECKIN_RECORD, BADGE_DEFINITION, USER_BADGE, BADGE_PROGRESS）
- 切片 09-gamification/backend.md（GamificationService 实现）

### 6.2 发现

#### F5-1 [P1] 游戏化模块架构声明与实现不一致：事件驱动 vs 同步调用

| 文档 | 描述 |
|------|------|
| 架构 § 4 模块矩阵 | gamification 模块标注为"事件驱动"模式 |
| 切片 09 | `GamificationService.add_points()` 为同步方法调用，无事件总线 |

**问题**：架构 § 4 将 gamification 模块的设计模式标注为"事件驱动"（Event-Driven），但切片 09 的实现完全为同步直接调用：
- video_analysis、scoring、match_data、training_advice 等模块直接 import 并调用 `GamificationService.add_points()`
- 没有事件总线（Event Bus）实现
- 没有事件发布/订阅机制
- gamification 模块不是事件的被动消费者，而是被调用方

这意味着：
1. 架构文档声明了事件驱动模式但未实现
2. gamification 模块故障会阻塞调用方（同步依赖）
3. 新增 gamification 触发点需要修改调用方代码（非动态扩展）
4. 无法实现"事件不可达时降级"策略

**建议**：
- **方案 A（推荐）**：将架构 § 4 的 gamification 模块模式标注从"事件驱动"改为"同步调用"，与实现保持一致。Phase 2+ 考虑引入 Redis Stream 或 Celery 事件实现真正的事件驱动。
- **方案 B**：在切片中实现事件驱动：调用方 `celery_app.send_task('gamification.add_points', ...)`，gamification 模块作为 Celery 任务消费者。但这会增加系统复杂度。

#### F5-2 [P2] 积分操作的跨模块容错未定义

| 文档 | 描述 |
|------|------|
| 切片 09 | `add_points(user_id, points, reason)` 同步操作 DB |
| 各调用方切片 | 无 try-catch 包裹 gamification 调用 |

**问题**：4 个模块（video_analysis, scoring, match_data, training_advice）同步调用 gamification.add_points()，若 gamification 的 DB 操作失败（如 user_points 表锁超时），调用方操作也会失败。用户完成了比赛/分析/训练但积分未增加，体验受损。

**建议**：各调用方将 gamification.add_points() 包装在 try-except 中，失败时记录日志但不阻塞主流程。或改为异步 Celery 任务触发（与 F5-1 方案 B 一致）。

#### F5-3 [P3] 徽章条件评估逻辑未在任何文档中定义

| 文档 | 描述 |
|------|------|
| 架构 § 9.1 | badge_definition.condition JSONB: `{metric, operator, threshold}` |
| API § 10.4 | GET /gamification/badges 返回 earned + locked 列表（locked 含 progress/target） |
| 切片 09 | `_check_badges()` 遍历 badge_definition，解析 condition JSONB |

**问题**：徽章条件评估的具体逻辑（哪些 metric 可用、operator 支持哪些操作符、threshold 的数据类型）未在任何文档中定义。切片实现为通用的 JSONB 解析，但可用的 metric 名称（如 "total_analyses", "win_streak", "training_sessions_completed"）未列举。

**建议**：在架构 § 9 或模块详细设计中补充徽章条件评估规范，定义可用 metric 列表、支持的 operator 枚举（`==, >=, <=, >, <`）、示例徽章定义。

---

## 7. 维度 6：跨模块 API 依赖图

### 7.1 依赖图总览

以下为从切片代码和架构文档中提取的跨模块调用关系：

```
video_analysis ──→ membership (check_membership, consume_analysis_quota)
                ──→ file_management (STS签发, HEAD校验, 软删除)
                ──→ ai_pipeline (Celery enqueue)
                ──→ notification (WS push analysis_progress/complete/failed)
                ──→ gamification (add_points on analysis complete)

ai_pipeline ──→ ai_inference (HTTP /infer/*)
            ──→ notification (WS push progress)
            ──→ progress_analysis (cascade: snapshot + trend) [via celery_app.send_task]
            ──→ training_advice (cascade: rule engine + advice) [via celery_app.send_task]
            ──→ data_dashboard (cache bust) [via redis.delete — 直接操作!]
            ──→ notification (cascade: WS push analysis_complete) [via celery_app.send_task]

scoring ──→ notification (WS push score_update, sync_match)
        ──→ match_data (post-finish record creation) [触发方式未定义!]
        ──→ gamification (add_points on match finish)

match_data ──→ gamification (add_points on record create)

payment ──→ membership (subscription create/renew) [in _trigger_business_logic]
         ──→ notification (WS push payment_success) [调用方式不明确!]

training_advice ──→ knowledge_base (rule engine match)
                ──→ gamification (add_points on session complete)
                ──→ progress_analysis (trend data for rule engine)

progress_analysis ──→ knowledge_base (rule engine match)
                   ──→ training_advice (plan adjustment) [模块边界不清晰!]

admin ──→ knowledge_base (CRUD管理)
      ──→ ai_inference (模型版本管理)
      ──→ video_analysis (内容审核队列)
```

### 7.2 发现

#### F6-1 [P1] ai_pipeline 直接操作 data_dashboard 的 Redis Key（模块耦合违规）

| 文档 | 描述 |
|------|------|
| 架构 § 12.11 | "新分析报告完成 → Redis DEL dashboard:overview:{uid}, dashboard:technique:{uid}, dashboard:heatmap:{uid}" |
| 切片 ai_pipeline | `ReportGenerator._trigger_cascade()` 中直接 `redis.delete(f"dashboard:overview:{uid}")` 等 |

**问题**：ai_pipeline 基础设施模块直接操作 data_dashboard 业务模块的 Redis 缓存 Key。这违反了模块边界原则：
- ai_pipeline 不应知道 data_dashboard 的缓存 Key 命名规则
- 若 data_dashboard 修改 Key 命名（如从 `dashboard:overview:{uid}` 改为 `dashboard:overview:v2:{uid}`），ai_pipeline 也需同步修改
- 这是基础设施模块对业务模块的反向依赖

**建议**：data_dashboard 模块暴露 `DashboardService.bust_cache(user_id)` 公共方法，ai_pipeline 通过 Celery 异步任务调用此方法，而非直接操作 Redis Key。这样缓存 Key 命名变更只需修改 data_dashboard 模块。

#### F6-2 [P2] payment → notification 的调用链不明确

| 文档 | 描述 |
|------|------|
| 模块设计 § 2.11 BR-2 | "WS 推送 payment_success" |
| API § 12.3 | 业务规则第 8 条："WS 推送：向 ws:user:{uid} 推送 payment_success" |
| 切片 11 | PaymentService._trigger_business_logic() 未直接 import notification 模块 |

**问题**：支付回调流程中需要推送 WS 通知 `payment_success` 事件，但 payment 模块的切片实现中未发现对 notification 模块的直接调用。WS 推送可能：
- 由 payment 模块内部直接操作 Redis pubsub（绕过 notification 模块）
- 或由某个未在切片中展示的中间件/装饰器处理
- 或在 _trigger_business_logic 的某处间接调用

文档和代码之间的调用链不清晰，存在"链接断裂"风险。

**建议**：在 payment 切片中明确调用 `NotificationService.push_ws_message(user_id, "payment_success", data)`，或通过 Celery 异步任务触发。在模块设计 § 2.11 中补充 payment 对 notification 的依赖声明。

#### F6-3 [P2] progress_analysis 越权存储 training_advice 数据

| 文档 | 描述 |
|------|------|
| 架构 § 12.7 | "Progress → DB: 存储增强建议" |
| 切片 08 | ProgressAnalysisService 在级联中生成并存储训练建议到 training_plan 表 |
| 切片 07 | TrainingAdviceService 提供 GET /training/advice 端点查询 training_plan |

**问题**：progress_analysis 模块在级联触发中直接写入 training_plan 表（训练建议数据），但 training_plan 表在逻辑上属于 training_advice 模块。这导致：
- progress_analysis 模块拥有 training_plan 的写入权限，但不是该表的"所有者"模块
- training_advice 模块是 training_plan 的"所有者"但只做读取
- 两个模块共享同一张表但职责划分不清晰

**建议**：将训练建议生成和存储的职责明确归给 training_advice 模块。ai_pipeline 级联触发应调用 training_advice 模块的 `generate_advice(report_id)` 方法，而非让 progress_analysis 代为存储。progress_analysis 仅负责快照、趋势、方案评估（plan_adjustment 表）。

#### F6-4 [P2] dashboard 缓存 bust 的 Key 列表不完整

| 文档 | 描述 |
|------|------|
| 架构 § 12.11 | 分析完成时 bust: `dashboard:overview:{uid}`, `dashboard:technique:{uid}`, `dashboard:heatmap:{uid}` |
| 架构 § 12.11 | 比赛结束时 bust: `dashboard:overview:{uid}`, `dashboard:winrate:{uid}` |
| 切片 ai_pipeline | `_trigger_cascade()` 中 bust 的 Key 列表未明确定义 |

**问题**：ai_pipeline 的级联触发中，dashboard 缓存 bust 应该 bust 哪些 Key 不清晰。架构定义了 3 个 Key 需要 bust（分析完成时），但切片实现可能只 bust 了部分。此外，比赛结束时的 bust 由 scoring 模块触发，但 scoring 切片中是否实现了 dashboard 缓存 bust 未确认。

**建议**：在 ai_pipeline 切片中明确定义 bust 的 Key 列表，与架构 § 12.11 保持一致。在 scoring 切片中补充比赛结束时的 dashboard 缓存 bust 逻辑。

---

## 8. 维度 7：Schema/响应一致性

### 8.1 发现

#### F7-1 [P2] 支付回调响应格式违反统一规范

| 文档 | 描述 |
|------|------|
| API § 1.1 | 统一响应格式: `{code: int, message: string, data: object, timestamp: string}` |
| API § 12.3 | 支付回调响应: `{"code": "SUCCESS", "message": "成功"}` |

**问题**：支付回调端点的响应格式完全不符合 § 1.1 的统一规范：
- `code` 为字符串 "SUCCESS"/"FAIL" 而非整数 HTTP 状态码
- 无 `data` 字段
- 无 `timestamp` 字段

虽然这是微信支付要求的格式，但 API 文档未明确标注此为统一规范的例外。

**建议**：在 API § 12.3 增加显式说明："此端点响应格式为例外，不遵循 § 1.1 统一响应格式，因为微信支付要求特定的 ACK 格式。"并在 § 1.1 中增加例外说明引用。

#### F7-2 [P2] 比分序列字段命名不一致

| 端点 | 字段名 |
|------|--------|
| API § 5.3 GET /scoring/matches/{id} → score_sequence[] | `seq`, `scorer`, `method`, `action` |
| API § 7.3 GET /match-data/records/{id} → details[] | `sequence`, `scorer`, `score_method`, `technique_action` |

**问题**：同概念的比分明细数据在 scoring 和 match_data 两个模块中使用了不同的字段名：
- `seq` vs `sequence`
- `method` vs `score_method`
- `action` vs `technique_action`

这增加前端数据适配的工作量，且在 scoring → match_data 数据同步时需要字段映射。

**建议**：统一字段命名。建议采用更描述性的名称：`sequence`, `scorer`, `score_method`, `technique_action`。在 scoring API 中将 `seq` 改为 `sequence`，`method` 改为 `score_method`，`action` 改为 `technique_action`。

#### F7-3 [P3] report 中的 task_id 类型不一致

| 端点 | 字段 | 类型 |
|------|------|------|
| API § 4.3 POST /video-analysis/tasks → data.task_id | `task_id` | int |
| API § 4.3 POST /video-analysis/tasks → data.task_uuid | `task_uuid` | string |
| API § 4.6 GET /video-analysis/reports/{id} → data.task_id | `task_id` | string ("task_xxx") |

**问题**：POST /video-analysis/tasks 响应中 `task_id` 为整数（数据库主键），但 GET /video-analysis/reports/{id} 响应中 `task_id` 为字符串（UUID 格式 "task_xxx"）。报告详情端点的 `task_id` 字段实际应为 `task_uuid`，存在命名混淆。

**建议**：GET /video-analysis/reports/{id} 响应中将 `task_id` 拆分为 `task_id`（int, 数据库主键）和 `task_uuid`（string, 外部 UUID），与 POST /video-analysis/tasks 保持一致。

#### F7-4 [P3] 比分表示格式不一致

| 端点 | 比分表示 |
|------|---------|
| API § 5.3 GET /scoring/matches/{id} | `current_score_user: 8` (int), `current_score_opp: 5` (int) |
| API § 5.6 POST /scoring/matches/{id}/finish | `final_score: "3:1"` (string) |
| API § 4.6 GET /video-analysis/reports/{id} | `result_data.score_analysis.final_score: "11:8"` (string) |

**问题**：比分在比赛详情中使用两个整数字段（`current_score_user` + `current_score_opp`），在比赛结束和报告分析中使用字符串（`final_score: "X:Y"`）。同一概念的数据格式不一致。

**建议**：统一比分表示。建议在所有端点中同时提供结构化字段和格式化字符串：
```json
"current_score": {"user": 8, "opponent": 5, "display": "8:5"}
```

#### F7-5 [P3] API 文档中多处 Markdown 格式问题

**问题**：以下端点的响应体 JSON 代码块后有多余的 ``` 标记：
- § 5.6 POST /scoring/matches/{id}/finish（第 1365 行附近）
- § 8.5 GET /training/plans/{id}/adjustments（第 2040 行附近）
- § 9.2 GET /progress/technique-trends（第 2234 行附近）
- § 9.3 GET /progress/technique-trends/{metric}（第 2274 行附近）
- § 9.4 GET /progress/comparison（第 2327 行附近）
- § 9.5 GET /progress/summary（第 2377 行附近）

**建议**：清理 API 文档中的多余 ``` 标记。

---

## 9. 维度 8：错误码一致性

### 9.1 全局错误码表（API § 1.7）

| HTTP | code | 条件 | 消息 |
|------|------|------|------|
| 401 | 40100 | 未携带 JWT 或 JWT 无效 | 请先登录 |
| 401 | 40101 | access_token 已过期 | 登录已过期，请刷新 Token |
| 403 | 40300 | 权限不足 | 权限不足，请升级会员 |
| 404 | 40400 | 资源不存在 | 资源不存在 |
| 422 | 42200 | 参数校验失败 | 参数校验失败：{field} {detail} |
| 429 | 42900 | 触发限流 | 请求过于频繁，请稍后重试 |
| 500 | 50000 | 服务端内部错误 | 服务暂时不可用，请稍后重试 |

### 9.2 发现

#### F8-1 [P1] 业务错误码缺失：端点级错误未定义 5 位 code

| 文档 | 描述 |
|------|------|
| API § 1.7 | 全局错误码使用 5 位业务码（40100, 40101, 40300, 40400, 42200, 42900, 50000） |
| API § 4.3 | `| 403 | 免费额度用完 | 今日免费分析次数已用完 |` — 无业务码 |
| API § 5.4 | `| 400 | 比赛不在进行中 | 比赛未在进行中 |` — 无业务码 |
| API § 8.8 | `| 403 | 非会员用户 | 此功能需要会员及以上等级 |` — 无业务码 |

**问题**：§ 1.7 定义了全局错误码体系（5 位 code），但所有端点级"错误情况"表仅使用 HTTP 状态码 + 中文消息，未定义对应的 5 位业务 code。这导致：

1. **前端无法区分同 HTTP 状态码的不同错误**：
   - 403 既可能是"权限不足"（40300）也可能是"免费额度用完"（未定义 code）→ 前端只能靠解析 message 字符串区分
   - 404 既可能是"通用资源不存在"（40400）也可能是"报告不存在"/"比赛不存在"/"任务不存在"等具体业务错误

2. **§ 1.7 与端点错误表的格式不一致**：
   - § 1.7: `| HTTP | code | 条件 | 消息 |`（4 列含 code）
   - 端点表: `| HTTP | 条件 | 消息 |`（3 列无 code）

3. **特殊场景未定义**：
   - 免费额度用完（§ 4.3 的 403）应使用什么 code？40300 是"权限不足"，但免费额度是业务限制而非权限问题
   - 比赛状态冲突（§ 5.4 的 400）应使用什么 code？40000 未在全局表中定义

**建议**：为所有端点级错误定义 5 位业务码。建议命名规则：`{HTTP}{模块号}{错误序号}`，如：
- 40301: 免费分析额度用完
- 40302: 非会员用户访问会员功能
- 40001: 比赛不在进行中
- 40002: 比分已被其他设备更新（撤销冲突）
- 40901: 今日已打卡
- 40902: 该训练单已完成

端点错误表统一为 4 列格式（含 code），与 § 1.7 保持一致。

#### F8-2 [P2] HTTP 状态码语义使用不当

| 端点 | 当前 HTTP | 建议 HTTP | 理由 |
|------|---------|---------|------|
| § 4.3 免费额度用完 | 403 | 429 | 本质是速率限制（每日 N 次），非权限问题 |
| § 5.4 比赛不在进行中 | 400 | 409 | 状态冲突，非请求格式错误 |
| § 5.5 比分已被其他设备更新 | 409 | 409 ✅ | 正确使用 |
| § 8.8 训练单已完成 | 409 | 409 ✅ | 正确使用 |
| § 7.4 关联记分牌不可编辑 | 403 | 409 | 状态冲突（已关联），非权限问题 |

**问题**：多个端点使用 400（Bad Request）处理状态冲突类错误，使用 403（Forbidden）处理速率限制类错误。HTTP 状态码语义不符合 RFC 7231 规范。

**建议**：按 RESTful 规范统一 HTTP 状态码使用：
- 400: 请求体格式错误/参数缺失
- 403: 权限不足（用户角色/会员等级不够）
- 409: 状态冲突（资源状态不允许此操作）
- 429: 速率限制/额度用完

#### F8-3 [P2] 404 错误消息不统一

| 端点 | 404 消息 |
|------|---------|
| § 1.7 全局 | 资源不存在 |
| § 4.3 | 文件记录不存在 |
| § 4.5 | 任务不存在 |
| § 4.6 | 报告不存在 |
| § 5.3 | 比赛不存在 |
| § 7.3 | 比赛记录不存在 |
| § 8.1 | 报告不存在 |

**问题**：404 的消息在不同端点中不一致——有些使用通用"资源不存在"，有些使用具体资源名"报告不存在"/"比赛不存在"。前端需要同时处理通用和具体的消息文本。

**建议**：统一为具体消息（用户友好），如"报告不存在"/"比赛不存在"。前端 404 处理直接展示 message 字段，无需 fallback 到通用消息。全局 40400 的消息改为"资源不存在"仅用于未定义路径（如 /api/v1/unknown/{id}）。

#### F8-4 [P3] 支付回调错误格式未在 § 1.7 中标注为例外

| 文档 | 描述 |
|------|------|
| API § 1.7 | 全局错误码表 |
| API § 12.3 | 支付回调使用 `{"code": "FAIL", "message": "..."}` 格式 |

**问题**：支付回调的错误响应格式（`code` 为字符串 "FAIL"）与全局规范（`code` 为整数）完全不同。虽然这是微信支付的要求，但 § 1.7 未提及此例外。

**建议**：在 § 1.7 全局错误码表后增加说明："除 § 12.3 POST /payment/notify 外，所有端点适用以上错误码规范。支付回调端点的响应格式为微信支付 APIv3 要求的例外格式。"

---

## 10. P0-P3 分级汇总

### 10.1 分级标准

| 级别 | 定义 | 处理时限 |
|------|------|---------|
| P0 | 阻塞性问题：数据流断裂或核心功能无法实现 | 立即修复 |
| P1 | 严重问题：架构-实现不一致或模块边界冲突 | 当前 Phase 修复 |
| P2 | 中等问题：跨模块容错/一致性缺陷 | 下一个迭代修复 |
| P3 | 轻微问题：命名/格式/文档缺陷 | 可延后修复 |

### 10.2 全部发现汇总

| ID | 级别 | 维度 | 标题 | 涉及文档 |
|----|------|------|------|---------|
| F1-1 | P2 | 1 | 视频标准化转码归属位置不一致 | 架构 §6.4 vs 模块设计 §3.2 vs 切片 |
| F1-2 | P2 | 1 | 级联触发：架构同步 vs 切片异步 | 架构 §12.7 vs 切片 ai_pipeline |
| F1-3 | P3 | 1 | estimated_wait_minutes 计算方法未定义 | API §4.3 vs 切片 03 |
| F2-1 | P2 | 2 | scoring→match_data 跨模块触发未定义 | 架构 §9.1 vs API §5.6/§7.1 vs 切片 04/05 |
| F2-2 | P3 | 2 | 发球轮换算法未定义 | 架构 §12.8 vs API §5.4 |
| F2-3 | P3 | 2 | match_id 关联关系未在 API 体现 | API §7.1/§7.4 |
| F3-1 | P1 | 3 | 训练建议存储的模块归属不清晰 | 架构 §12.7 vs 切片 07/08 |
| F3-2 | P2 | 3 | 训练单完成触发积分的跨模块容错未定义 | API §8.8 vs 切片 07/09 |
| F3-3 | P2 | 3 | training_advice sessions 端点在模块详细设计中缺失 | 模块设计 vs API §8.7-8.8 vs 切片 07 |
| F3-4 | P3 | 3 | 反馈→数据飞轮后续处理流程不完整 | API §4.8 vs 模块设计 §3.5 |
| F4-1 | P2 | 4 | 支付回调部分失败的补偿机制未定义 | 模块设计 §2.11 vs 切片 11 |
| F4-2 | P3 | 4 | expiring_soon 状态未在 API 中暴露 | 架构 §12.9 vs API §11.2 |
| F4-3 | P3 | 4 | 免费额度 Redis Key TTL 不一致 | 架构 §12.9 vs 切片 10 |
| F5-1 | P1 | 5 | 游戏化模块：架构声明事件驱动 vs 实现同步调用 | 架构 §4 vs 切片 09 |
| F5-2 | P2 | 5 | 积分操作跨模块容错未定义 | 切片 09 + 各调用方 |
| F5-3 | P3 | 5 | 徽章条件评估逻辑未定义 | 架构 §9.1 vs 切片 09 |
| F6-1 | P1 | 6 | ai_pipeline 直接操作 dashboard Redis Key | 架构 §12.11 vs 切片 ai_pipeline |
| F6-2 | P2 | 6 | payment→notification 调用链不明确 | 模块设计 §2.11 vs 切片 11 |
| F6-3 | P2 | 6 | progress_analysis 越权存储 training_advice 数据 | 架构 §12.7 vs 切片 07/08 |
| F6-4 | P2 | 6 | dashboard 缓存 bust Key 列表不完整 | 架构 §12.11 vs 切片 ai_pipeline |
| F7-1 | P2 | 7 | 支付回调响应格式违反统一规范 | API §1.1 vs §12.3 |
| F7-2 | P2 | 7 | 比分序列字段命名不一致 | API §5.3 vs §7.3 |
| F7-3 | P3 | 7 | report 中 task_id 类型不一致 | API §4.3 vs §4.6 |
| F7-4 | P3 | 7 | 比分表示格式不一致 | API §5.3 vs §5.6 vs §4.6 |
| F7-5 | P3 | 7 | API 文档 Markdown 格式问题 | API §5.6/§8.5/§9.2-9.5 |
| F8-1 | P1 | 8 | 业务错误码缺失：端点级错误未定义 5 位 code | API §1.7 vs 各端点 |
| F8-2 | P2 | 8 | HTTP 状态码语义使用不当 | API §4.3/§5.4/§7.4 |
| F8-3 | P2 | 8 | 404 错误消息不统一 | API §1.7 vs 各端点 |
| F8-4 | P3 | 8 | 支付回调错误格式未标注为例外 | API §1.7 vs §12.3 |

### 10.3 按级别统计

| 级别 | 数量 | 涉及维度 |
|------|------|---------|
| P0 | 0 | — |
| P1 | 4 | 维度 3(F3-1), 维度 5(F5-1), 维度 6(F6-1), 维度 8(F8-1) |
| P2 | 12 | 维度 1(F1-1,F1-2), 维度 2(F2-1), 维度 3(F3-2,F3-3), 维度 4(F4-1), 维度 5(F5-2), 维度 6(F6-2,F6-3,F6-4), 维度 7(F7-1,F7-2), 维度 8(F8-2,F8-3) |
| P3 | 12 | 维度 1(F1-3), 维度 2(F2-2,F2-3), 维度 3(F3-4), 维度 4(F4-2,F4-3), 维度 5(F5-3), 维度 7(F7-3,F7-4,F7-5), 维度 8(F8-4) |
| **合计** | **28** | |

### 10.4 P0/P1 重点项详情

#### P1-1: F3-1 — 训练建议存储的模块归属不清晰

**影响**：training_advice 模块查询的数据由 progress_analysis 模块写入，模块边界模糊，职责划分不清。后续维护时，修改 training_plan 表结构需要同时修改两个模块。

**修复建议**：级联触发中，ai_pipeline 应分别调用 training_advice（生成建议）和 progress_analysis（生成快照/趋势），而非让 progress_analysis 代为生成和存储训练建议。

#### P1-2: F5-1 — 游戏化模块架构声明与实现不一致

**影响**：架构 § 4 声明 gamification 为"事件驱动"但实际为同步调用。这误导开发者对系统架构的理解，可能导致后续开发中错误地依赖事件驱动特性（如期待 gamification 故障不影响调用方）。

**修复建议**：将架构 § 4 的 gamification 模块模式标注从"事件驱动"改为"同步调用"。若未来需要事件驱动，应设计独立的事件总线方案。

#### P1-3: F6-1 — ai_pipeline 直接操作 dashboard Redis Key

**影响**：基础设施模块（ai_pipeline）直接操作业务模块（data_dashboard）的缓存 Key，违反模块边界原则。Key 命名变更需同步修改两个模块。

**修复建议**：data_dashboard 暴露 `DashboardService.bust_cache(user_id)` 方法，ai_pipeline 通过 Celery 异步调用此方法。

#### P1-4: F8-1 — 业务错误码缺失

**影响**：前端无法通过 code 区分同 HTTP 状态码的不同业务错误（如 403 可能是权限不足或额度用完），只能靠解析 message 字符串，脆弱且不可靠。

**修复建议**：为所有端点级错误定义 5 位业务码，端点错误表统一为 4 列格式（HTTP, code, 条件, 消息）。

---

## 11. 优化建议

### 11.1 架构层面优化

#### O-1: 引入轻量级内部事件机制

**当前问题**：gamification 模块被 4 个模块同步调用，任何 gamification 故障都会级联影响调用方。ai_pipeline 级联触发虽然使用 Celery 异步，但各目标模块的写入操作仍可能失败。

**建议**：引入轻量级内部事件机制（Phase 2+）：
- 使用 Redis Stream 或 Celery 事件作为内部事件总线
- gamification 模块订阅事件（`analysis.complete`, `match.finish`, `training.session.complete`）
- 各模块发布事件而非直接调用 gamification
- 事件包含 `event_type, user_id, metadata, timestamp`
- gamification 消费失败自动重试 3 次，不影响发布方

**收益**：解耦 gamification 与调用方，提高系统容错性，支持未来新增 gamification 触发点无需修改调用方。

#### O-2: 模块边界明确化 — 缓存操作封装

**当前问题**：ai_pipeline 直接 `redis.delete()` 操作 dashboard 的缓存 Key（F6-1），违反模块边界。

**建议**：各业务模块封装自己的缓存操作为 Service 层公共方法：
```python
# data_dashboard 模块
class DashboardService:
    @staticmethod
    async def bust_cache(user_id: int, event: str):
        """根据事件类型 bust 对应缓存"""
        keys_to_delete = CACHE_BUST_MAP[event]
        for key_pattern in keys_to_delete:
            await redis.delete(key_pattern.format(uid=user_id))
```

ai_pipeline 通过 Celery 调用：
```python
celery_app.send_task('dashboard.bust_cache', args=[user_id, 'analysis_complete'])
```

**收益**：缓存 Key 命名变更只需修改 data_dashboard 模块；ai_pipeline 不需知道具体 Key。

### 11.2 API 契约层面优化

#### O-3: 错误码体系完善

**当前问题**：端点级错误未定义 5 位业务码（F8-1），HTTP 状态码语义不当（F8-2），404 消息不统一（F8-3）。

**建议**：建立完整的错误码体系：

```
错误码格式: {HTTP 3位}{模块 2位}{错误 2位} = 7位
  - HTTP: 400/401/403/404/409/422/429/500
  - 模块: 00=全局, 01=auth, 02=user, 03=video_analysis, ...
  - 错误: 模块内自增

示例:
  4030301 = 403(video_analysis 模块)(免费额度用完)
  4090501 = 409(match_data 模块)(关联记分牌不可编辑)
  4091001 = 409(gamification 模块)(今日已打卡)
```

**收益**：前端可通过 code 精确区分错误类型，实现差异化 UI（如额度用完引导升级会员，打卡冲突提示明天再来）。

#### O-4: 响应字段命名统一规范

**当前问题**：比分序列字段命名不一致（F7-2），task_id 类型不一致（F7-3），比分格式不一致（F7-4）。

**建议**：建立 API 命名规范文档，规定：
- ID 字段：数据库主键用 `_id` 后缀（int），外部 UUID 用 `_uuid` 后缀（string）
- 比分字段：结构化 `{user: int, opponent: int}` + 展示字符串 `display: "X:Y"`
- 序列字段：统一用 `sequence`（不用 `seq`）
- 方法字段：统一用 `score_method`（不用 `method`），`technique_action`（不用 `action`）
- 时间字段：ISO 8601 带时区，统一用 `_at` 后缀（`created_at`, `paid_at`）

### 11.3 数据流层面优化

#### O-5: scoring → match_data 自动同步

**当前问题**：scoring 比赛结束后 match_record 需要用户手动创建（F2-1），数据可能不一致。

**建议**：scoring `finish()` 方法成功后，通过 Celery 异步任务调用 match_data 模块创建 match_record：

```python
# scoring 模块
async def finish_match(self, match_id: int):
    # ... 生成 match_statistic ...
    celery_app.send_task('match_data.create_from_scoring', 
                         args=[match_id])
    return result
```

```python
# match_data 模块
@celery_app.task
def create_from_scoring(match_id: int):
    match = await get_match(match_id)
    score_records = await get_score_records(match_id)
    match_record = await create_record(
        user_id=match.user_id,
        opponent_name=match.opponent_name,
        my_score=match.current_score_user,
        opponent_score=match.current_score_opp,
        is_win=match.is_win,
        match_id=match_id,  # 关联记分牌比赛
        details=[ScoreDetail(seq=r.seq, scorer=r.scorer, 
                            score_method=r.score_method,
                            technique_action=r.technique_action) 
                 for r in score_records]
    )
```

**收益**：用户无需手动录入，数据自动同步，字段映射由系统保证一致性。

#### O-6: 支付回调补偿机制

**当前问题**：支付回调部分失败（order paid 但 subscription 未创建）无补偿机制（F4-1）。

**建议**：增加 Celery Beat 定时补偿任务：

```python
@celery_app.task
def compensate_payment_orders():
    """每 10 分钟扫描 status=paid 但无 subscription/payment_record 的 order"""
    orders = await get_orphan_paid_orders()
    for order in orders:
        try:
            await retry_business_logic(order)
        except Exception as e:
            logger.error(f"Compensate order {order.id} failed: {e}")
            if order.retry_count > 5:
                await notify_admin(f"Order {order.id} compensation failed 5+ times")
```

**收益**：即使回调中 subscription 创建失败，补偿任务会自动重试，确保用户付款后获得权益。

---

## 附录：审查文档版本信息

| 文档 | 文件路径 | 版本 | 日期 |
|------|---------|------|------|
| 需求分析 | docs/01需求分析/乒乓智能分析平台-需求分析与路线图-v0.4.md | v0.4 | — |
| 系统架构 | docs/03系统架构/01-系统架构设计.md | v2.4 | — |
| 模块详细设计 | docs/04详细设计/03-模块详细设计.md | v1.2 | — |
| 数据库详细设计 | docs/04详细设计/04-数据库详细设计.md | v1.4 | — |
| API 详细设计 | docs/04详细设计/05-API详细设计.md | v1.3 | 2026-10-12 |
| 后端切片 01-12 | docs/06垂直模块前后端切片设计/01-auth~12-notification/backend.md | — | — |
| 基础设施切片 13 | docs/06垂直模块前后端切片设计/13-infrastructure/*.md | — | — |

---

> **审查声明**：本报告基于 2026-10-12 时的文档版本进行只读审查，未修改任何源文件。所有发现均附带文档参考位置，可直接定位到具体文档行号进行验证。
