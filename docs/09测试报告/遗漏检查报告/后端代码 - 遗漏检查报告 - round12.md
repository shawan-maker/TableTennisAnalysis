# 后端代码 - 遗漏检查报告 - Round 12

> 日期：2026-10-27
> 范围：13 个业务模块 + 2 个基础设施模块，"设计文档 vs 代码实现 vs 测试覆盖"三方全量对比
> 方法：8 个并行批次（每批 2 个模块），每批覆盖端点完整性/业务规则/错误处理/测试覆盖 4 维度
> 基线：R8-R11 审查循环已收敛（连续两轮零 P2+），本轮新增"测试覆盖完整性"维度

## 一、汇总统计

| 模块 | P0 | P1 | P2 | P3 | 一致性确认 |
|------|----|----|----|----|-----------|
| Auth | 0 | 1 | 6 | 4 | 端点/错误码/consent 链路/H5 一次性使用一致 |
| User | 0 | 1 | 2 | 4 | 端点/72h 冷静期/错误码一致 |
| Membership | 0 | 0 | 2 | 4 | 端点/五态状态机/CST 重置/幂等 INCR 一致 |
| Payment | 0 | 1 | 2 | 4 | 端点/退款窗口/续期逻辑/幂等一致 |
| VideoAnalysis | 0 | 2 | 6 | 4 | 端点/10 步流水线/STS/额度一致 |
| Scoring | 0 | 1 | 4 | 4 | 端点/状态机/撤销乐观锁/Beat 清理一致 |
| MatchData | 0 | 2 | 2 | 4 | 端点/422 校验/错误码一致 |
| Training | 0 | 1 | 5 | 5 | 端点/403 守卫/404 矩阵一致 |
| Gamification | 0 | 1 | 7 | 5 | 端点/积分规则/409 重复一致 |
| Dashboard | 0 | 2 | 2 | 3 | 端点/缓存键 TTL 一致 |
| Notification | 0 | 2 | 4 | 4 | 端点/WS 认证/通道矩阵/重连补偿一致 |
| Progress | 0 | 2 | 3 | 5 | 端点/18 项指标/方向感知一致 |
| Admin | 0 | 3 | 3 | 7 | 端点/30min TTL/限流/权限矩阵一致 |
| KnowledgeBase | 0 | 2 | 2 | 2 | 规则类型优先级/占位符渲染一致 |
| AIPipeline | 0 | 5 | 7 | 3 | 10 步流水线/熔断参数一致 |
| BeatTasks | 0 | 2 | 3 | 1 | 10 任务调度链路/6 真实实现一致 |
| **合计** | **0** | **28** | **60** | **63** | |

## 二、P1 问题清单（28 项）

> **Round 13 复验结论（2026-10-29）**：28 项 P1 全部闭环 —— 24 项代码修复逐项核验通过
>（针对性回归测试全绿），4 项外联桩升级为 Phase 2 边界声明（代码 R12 边界注释 +
> 01-auth/10-membership/12-notification 切片设计文档双向标注），详见
> 《后端代码 - 遗漏检查报告 - round13.md》§二/§五。

| 分类 | 编号 | R13 复验状态 | 证据 |
|------|------|--------------|------|
| 安全 | MatchData-B1/B2 | ✅ 修复核验通过 | update schema 无 is_win；OR 语义重算（test_match_data 20/20，含 R13-MatchData-1 新增赛制校验联动） |
| 安全 | Admin-1 | ✅ 修复核验通过 | admin_service 每请求校验 is_active（test_admin 20 passed + 1 skipped） |
| 安全 | Auth-2 | ✅ 修复核验通过 | wechat_login banned 拦截（TestWechatLogin 封禁 403） |
| 安全 | Payment-1 | ✅ 修复核验通过 | payment_service L490-508 续期分支回填 subscription_id + 审计 target_id |
| 安全 | Membership-1 | ✅ 修复核验通过 | membership_service L115-150 expired/closed 按免费 3 次/日 |
| 业务 | VA-1/VA-2 | ✅ 修复核验通过 | main.py L128-130 share 路由根路径挂载；ai_pipeline/progress.py L42 TASK_TRANSITIONS + L66 转换校验（test_ai_pipeline 覆盖） |
| 业务 | SC-1 | ✅ 修复核验通过 | scoring_service L259-345 多局推进 + 达赛制自动 finish；R13 补 SC-1 回归测试 2 项（bo3 自动结束 + 跨局撤销保护） |
| 业务 | Training-B1/B2 | ✅ 修复核验通过 | app/tasks/training.py generate_advice_task（L33）；first_analysis 类型污染修复 |
| 业务 | Prog-1/Prog-2 | ✅ 修复核验通过 | R13-AIP-1 级联 snapshot 改 Celery 投递闭环；progress_service L228-232 resolved 趋势类型 |
| 业务 | Gam-1 | ✅ 修复核验通过 | gamification_service seed_badge_definitions + scripts/seed_badges.py |
| 业务 | Dash-1/Dash-2 | ✅ 修复核验通过 | R13-AIP-1 finish_match → bust_cache_task 投递；dashboard_service L62-64 降级只读检查 |
| 业务 | KB-2 / Admin-2 / Notif-1 | ✅ 修复核验通过 | knowledge_base_service L206-208 severity 取 diagnosis JSONB；admin_service L420 重复 409；通知提醒 3 天活动候选 |
| 边界 | Auth-1 | ⏸ Phase 2 边界声明 | 阿里云 SMS 桩 + 01-auth/backend.md 边界标注 |
| 边界 | Notif-2 / Membership-2 | ⏸ Phase 2 边界声明 | 微信订阅消息桩 + 12-notification/10-membership backend.md 边界标注 |
| 边界 | AIPipeline-5 | ⏸ Phase 2 边界声明 | AI 推理 mock + 切片文档边界标注 |
| 外联已修 | User-2 / AIPipeline-1-4 / Admin-3 / BeatTasks-1/2 / KB-1 | ✅ 修复核验通过 | tasks/user.py export_user_data；SUP-1/2 重试语义；AIP-2 退额度；R13-AIP-1 级联；tasks/audit.py 3 年保留（L16）；cleanup_orphan_files/cleanup_old_tasks；scripts/init_knowledge_base.py |


### 安全与数据完整性（优先修复）

| 编号 | 问题 | 设计要求 | 实际情况 |
|------|------|----------|----------|
| MatchData-B1 | is_win 可被前端篡改 | 自动计算禁止前端传入 | Update schema 含 is_win 字段可直接写入 |
| MatchData-B2 | is_win 重算条件与设计相反 | 任一比分变更即重算 | AND 逻辑，单改一比分不重算 |
| Admin-1 | 禁用管理员权限绕过 | 每请求校验 is_active | 仅读 Redis session，禁用后 30min 内仍可用 |
| Auth-2 | wechat_login 不检查 banned | 登录入口拦截封禁用户 | 仅 phone_login 有拦截 |
| Payment-1 | 续期订单退款不撤销权益 | 退款撤销会员权益 | 续期分支不回填 subscription_id，全额退款仍保留权益 |
| Membership-1 | get_quota 对 expired 误报无限 | expired 按免费 3 次/日 | tier=member 即返回 -1 无限额度 |

### 业务规则缺陷（核心功能）

| 编号 | 问题 | 设计要求 | 实际情况 |
|------|------|----------|----------|
| VA-1 | 分享链接 404 | 挂载根路径 /share/{token} | share_router 挂 api_router 实际 /api/v1/share，URL 生成 /share 必 404 |
| VA-2 | 任务状态机校验缺失 | TASK_TRANSITIONS 矩阵校验 | 直接 update status 无转换校验 |
| SC-1 | 多局推进未实现 | 达赛制要求自动 finish | current_game 永不递增，bo3/bo5 按单局记分 |
| Training-B1 | generate_advice 任务缺失 | Celery 异步生成+WS 推送 | 无任务文件无调用方，链路断裂 |
| Training-B2 | first_analysis 类型污染 | new_issue/progress_confirm/persistent_warning | 首次分析所有建议 type 被改写 |
| Prog-1 | 快照生成生产集成缺失 | Step 9 后自动触发 | 全项目无调用方，6 端点空转 |
| Prog-2 | resolved 趋势类型未实现 | 6 种趋势类型含 resolved | current=None 统一返回 "new" |
| Gam-1 | BADGE_SEEDS 零引用 | seed 脚本预置 6 徽章 | 死代码，生产徽章恒空 |
| Dash-1 | bust_cache 无调用方 | 分析完成/比赛结束时调用 | 全生产代码无调用，看板最长陈旧 1h |
| Dash-2 | 降级只读检查缺失 | 降级用户返回简化看板 | get_overview 不读 downgrade 键 |
| KB-2 | 规则引擎 severity 来源错误 | severity 取自 diagnosis JSONB | 从 condition 读取，恒为 medium 兜底 |
| Admin-2 | create_category 缺重复检查 | 重复 code 返回 409 | 直接插入触发 IntegrityError 500 |
| Notif-1 | 训练提醒候选判定错误 | 基于 3 天内 AI/比赛活动 | 基于 TrainingPlan.updated_at，无计划用户排除 |

### 外部集成空壳（mock/TODO 桩，Phase 2 范围需文档确认）

| 编号 | 问题 | 设计要求 | 实际情况 |
|------|------|----------|----------|
| Auth-1 | 阿里云 SMS SDK 未接入 | dysmsapi 发送失败 502 | TODO 桩仅打日志返回成功 |
| User-2 | export_data Celery 断链 | 异步导出 Celery 投递 | delay() TODO，任务永远 pending |
| Notif-2 | 微信订阅消息桩实现 | send_subscribe_message 真实发送 | 仅构造 template_msg 记日志 |
| Membership-2 | 微信到期提醒桩实现 | subscribe message 真实发送 | 同上 |
| AIPipeline-5 | AI 推理调用缺失 | httpx 调用 INFERENCE_BASE_URL | Step 1-8 硬编码 mock 返回 |
| AIPipeline-1 | 重试机制失效 | max_retries+指数退避 | 异常路径无 self.retry() |
| AIPipeline-2 | 失败退额度缺失 | 失败后 Redis DECR 退额度 | 全项目无退额度实现 |
| AIPipeline-3 | 级联链不完整 | 触发 advice/bust_cache/通知 | 仅 add_points，三链缺失注释 S4 占位 |
| AIPipeline-4 | is_llm_generated 失真 | 按实际生成方式记录 | 直接写全局 LLM_ENABLED |
| Admin-3/BeatTasks-2 | 审计清理空壳+保留期矛盾 | 3 年保留（PIPL） | 空壳且 TODO 写 180 天 |
| BeatTasks-1 | 4/10 Beat 任务空壳 | 孤儿清理/审计/导出/GPU 探测 | 四者 TODO 直接 return ok |
| KB-1 | 知识库初始化脚本缺失 | init_knowledge_base.py 幂等灌入 | 全项目无实现 |

## 三、P2 问题清单（60 项）

### 代码缺陷类（19 项）

| 编号 | 问题摘要 | 修复状态 |
|------|----------|----------|
| Auth-3 | policy_version 设计 1.0 vs 实现 v1.0 | ✅ 已修复（切片样例统一 v1.0） |
| Auth-4 | consent 不校验版本合法性，可产生无效同意记录 | ✅ 已修复（record_consent 仅接受 CURRENT_POLICY_VERSION，422） |
| User-3 | rating 超范围 400 分支死代码（Schema 先 422） | ✅ 已修复（移除 Schema ge/le，service 400 分支生效） |
| VA-3 | 分享摘要页应 HTML 实际 JSON | ✅ 已修复（share 端点改 HTMLResponse 渲染页） |
| VA-4 | upload-token 类型/大小错误码 400 vs 422 | ✅ 已修复（类型/过大 400、过小 422，移除 Schema 先行拦截） |
| VA-5 | upload-complete 404 vs 400 | ✅ 已修复（OSS 缺失 404） |
| VA-6 | confirm_upload 未回写 duration_sec | ✅ 已修复（文档同步：duration 不入 file_record，持久化于 video_task，API §4.2 规则 3 + 切片样例已更正） |
| SC-2 | sync_match 重连同步事件未实现 | ✅ 已修复（subscribe 后推送 sync_match 全量同步） |
| Training-B3 | escalate 分支自行改写方案（设计无此分支） | ✅ 已修复（删除 reps*1.5 分支，escalate 仅诊断） |
| Gam-2 | streak icon 阈值 3 vs 7 + STREAK_ICONS 死常量 | ✅ 已修复 |
| Gam-3 | 日历 streak 读 DB 不读 Redis | ✅ 已修复 |
| Gam-4 | 徽章统计源不含手动录入 | ✅ 已修复 |
| Admin-4 | toggle_rule 参数 int vs str（文档自相矛盾） | ✅ 已修复（对齐设计 int 数据库 ID） |
| Admin-5 | update_config/toggle_rule changes 裸值残留 | ✅ 已修复（changes 统一 {old,new}） |
| Admin-6 | update/delete 审计先于业务 commit（幽灵审计风险） | ✅ 已修复（7 处审计移至 commit 后） |
| KB-3 | stagnant 规则条件键 min_persistence vs min_stagnation | ✅ 已修复 |
| AIPipeline-7 | 熔断器每步独立稀释保护语义 | ✅ 已修复（共享 ai_inference 服务级熔断器） |
| AIPipeline-8 | LLM 路径无熔断检查 | ✅ 已修复（open 时降级模板生成，成功/失败计入熔断器） |
| AIPipeline-11 | Step 9 先标 completed 后执行报告生成 | ✅ 已修复（start → 生成 → complete/failed 手工编排） |
| Training-D4（新发现） | _generate_new_plan 浅拷贝后原地变更共享 sessions → committed_state/old_snapshot 污染，SQLAlchemy 相等性短路致 adjust 分支 reps 增幅不落库、历史 diff 失真（Training-D3 测试暴露） | ✅ 已修复（copy.deepcopy 隔离 + 补 diff 断言回归） |

### 测试缺口类（41 项）

| 编号 | 问题摘要 | 修复状态 |
|------|----------|----------|
| Auth-7/8/9 | wechat-login/refresh/logout 三端点零覆盖 | ✅ 全部已补（TestAuthRefreshLogout 4 测试 + TestWechatLogin 4 测试：新用户创建/复用不覆盖昵称/封禁 403/注销中 403，code2session mock） |
| User-4 | rating 超范围无测试 | ✅ 已补（TestRatingRangeValidation：499/3001/0/99999 → 400） |
| Payment-2 | 验签失败场景零测试（安全关键） | ✅ 已补（TestPaymentNotifySignature） |
| Payment-3 | analysis_pack 支付触发额度 INCR 无测试 | ✅ 已补（TestAnalysisPackQuotaIncrement：INCR quantity + 重复回调幂等不加倍） |
| VA-7 | 分享负向测试因路由错全部空转 | ✅ 已修复（改用真实挂载路径 /share/{token}） |
| VA-8 | 分享限流 429 无测试 | ✅ 已补（TestShareDailyLimit：预置计数 5 → 429、4 → 200 对照） |
| SC-3/4/5 | target_score 越界/未结束统计 400/WS 房间广播无测试 | ✅ 全部已补（SC-3 越界 422+边界合法 / SC-4 未结束统计 400 / SC-5 test_ws_match_room_broadcast：真实广播器 broadcast_to_room→ws:relay 频道+隔离断言，test_ws.py 9/9） |
| MatchData-D1 | 隔离测试 URL 缺 /records 段（假阳性） | ✅ 已修复 |
| MatchData-D2 | PATCH 跨用户隔离零覆盖 | ✅ 已补（TestMatchRecordPatchIsolation：跨用户 404/40413+数据不变、属主 PATCH 成功对照） |
| Training-D1 | 权限守卫测试选用无守卫端点（假阳性） | ✅ 已修复（改用 /templates 守卫端点） |
| Training-D2 | 趋势对比建议零覆盖 | ✅ 已补（TestTrendComparisonAdvice：带 aggregation 键的 improving/stagnant 规则 → progress_confirm/persistent_warning + 负对照；现有种子规则缺 aggregation 键从未真正命中趋势分支） |
| Training-D3 | 方案调整版本化/评估动作零覆盖 | ✅ 已补（TestPlanAdjustmentVersioning 版本语义 + TestPlanReEvaluateActions 四动作分支/跨用户 404；暴露并修复 Training-D4 浅拷贝缺陷） |
| Gam-5/6/7/8 | 断签重置/徽章解锁端到端/401/冒烟测试缺失 | ✅ 已补（TestCheckinFlow 5 测试：401/冒烟+同日 409/断签重置/连续日对照/streak_7 徽章端到端） |
| Dash-3/4 | period 非法值/冒烟测试缺失 | ✅ 已补（TestDashboardSmoke 2 测试；Dash-3 预期修正为 422——API §6.2 无"降级 month"契约，路由 pattern 校验生效，service 兜底属防御性代码） |
| Notif-3/4/5/6 | 无效模板 422/归档策略/在线 WS 推送/频率控制测试缺失 | ✅ 已补（订阅静默过滤+覆盖语义 ×2；归档 90/180 天清理；在线 WS 不落库 vs 离线落库+未读 INCR；提醒 3 天阈值+每周 2 次频率控制。附带重构：cleanup_old_notifications 任务体提取为模块级 async impl 便于测试直调） |
| Prog-6/7/8 | 趋势判定分支/R² 阈值/跨用户对比测试缺失 | ✅ 已补（Prog-6 TestTrendResolved；Prog-7 R²<0.4 过滤 + 高 R² high 置信 + 达标周数计算；Prog-8 comparison 属主 200/同报告 422/跨用户 404/混搭 404） |
| Admin-12/13 | 审计筛选参数/session 续期测试缺失 | ✅ 已补（action/target_type/admin_id+JOIN admin_username/start_date/end_date/分页去重全维度；session 滑动续期 TTL 1800 + logout 后 401） |
| KB-6 | test_knowledge_base.py 整文件缺失 | ✅ 已补（22/22 通过） |
| AIPipeline-12 | test_ai_pipeline.py 整文件缺失 | ✅ 已补（18/18 通过：全流程/重试退额度耗尽/失败幂等/断路器回退） |
| BeatTasks-5 | Beat 任务注册表匹配断言缺失 | ✅ 已补（test_beat_tasks_registered_in_celery：beat 条目 task 名逐一断言存在于 celery_app.tasks，防 UnknownTaskError） |
| 其余 | VA-12 feedback 422、User-5 资源隔离、Gam-13 409/429 遮蔽、Notif-7/8/9、Prog-9/10、Dash-5 热图边界、SC-9 undo 409 | ✅ 全部已补：VA-12（feedback 422 缺 is_correct/超长/边界 500→业务层）/ User-5（export-data 跨用户 404+code 40400+属主对照）/ Gam-13（限流真实生效下 409 不遮蔽 + checkin 1/day 第二次 slowapi 429 实证遮蔽语义，test_rate_limiting.py 5/5）/ Notif-7/8/9（is_read 过滤/101 ids 422+100 对照/空 template_ids 422）/ Prog-9（_calculate_trend 九分支矩阵直调）/ Prog-10（period 422+无认证 401）/ Dash-5（热图 5 分支：字段名兼容/畸形跳过/distribution 回退/除零防护/最新 10 份截断）/ SC-9（undo 未开始 409+code 40910） |

### 修复期补充发现（测试补齐过程中新发现并修复的生产缺陷）

| 编号 | 问题 | 处理 |
|------|------|------|
| SUP-1 | `self.retry(exc=e)` 耗尽语义：Celery 传 exc 时耗尽后重抛原异常而非 MaxRetriesExceededError（celery/app/task.py retry L732-741），`except MaxRetriesExceededError` 兜底分支永远不可达（任务卡 processing + 额度不退） | ✅ ai_pipeline/tasks.py + tasks/training.py 两处改为 `self.retry()`；tmp/probe_retry.py 探针实证三种场景语义 |
| SUP-2 | `_run_async` 异常掩盖：try 块同时包裹探测与执行，业务 RuntimeError 被误判为"无循环"，对已消费协程再次 asyncio.run → "cannot be called from a running event loop" 掩盖原始异常 | ✅ ai_pipeline/tasks.py + tasks/training.py 两处：try 只包探测，执行移出捕获范围 |
| SUP-3 | tasks/user.py 任务体裸 `asyncio.run`（与 SUP-2 同型）：R12-User-2 接通 export `.delay()` 投递后，eager 内联在运行循环中炸（导出端点 500，test_user.py 3 测试回归失败） | ✅ tasks/user.py 统一 `_run_async` 模式（export_user_data + process_account_deletions 两处） |
| SUP-4 | 测试侧跨 loop 连接池冲突：线程池新事件循环与主循环共用 asyncpg 连接池 → "Future attached to a different loop"（仅 eager 测试环境，生产 worker 独立循环无此问题） | ✅ 导出路由测试改 spy 投递（_ExportDispatchSpy 验证 delay 参数）+ 直调异步实现（等价路径）验证任务体语义 |

### 测试资产增量汇总（R12 全部缺口闭环后）

- 新建文件：test_rate_limiting.py（5 测试）、test_knowledge_base.py（22）、test_ai_pipeline.py（18）
- 追加：test_ws.py（SC-5，9/9）、test_video_analysis.py（VA-12）、test_dashboard.py（Dash-5 ×5）、test_notification.py（Notif-7/8/9 ×3）、test_progress.py（Prog-9/10 ×3）、test_user.py（User-5 隔离 + 任务体直调 + spy 投递，19/19）、test_scoring.py（SC-9）、test_supplements_p1.py（TestWechatLogin ×4）、test_cascade_chains.py（BeatTasks-5）
- 修复 3 个既有测试的语义过期断言（export pending→409 在投递链路接通后由 spy 方案保证确定性）

## 四、P3 问题清单（63 项，汇总）

文档不同步类 27 项（Auth-5/6/10/11、User-1/5/6、Membership-3/4、Payment-4/5/6/7、VA-9/10/11/12、SC-6/7/8/9、MatchData-B3/4/5、Training-B4/5/6/C2、Gam-9/10/11/12/13、Dash-5/6/7、Notif-3、Prog-3/4/5、Admin-7/8/9/10/11、KB-4/5、AIPipeline-9/10/13/14/15、BeatTasks-3/4/7）——主要为设计文档滞后于有意重构（R4-R7 修复后未回写文档）或反向（实现优于设计），统一以文档同步方式处理。

## 五、修复计划

1. **第一批（安全+资金+核心规则，P1×13）**：MatchData is_win×2、Admin-1、Auth-2、Payment-1、Membership-1、VA-1、VA-2、SC-1、Training-B1/B2、Prog-1、KB-2
2. **第二批（P2 代码缺陷×19）**：逐项修复
3. **第三批（测试缺口×41）**：优先修复假阳性测试（MatchData-D1、Training-D1、VA-7），再补安全类（Payment-2 验签）、再补核心业务测试
4. **第四批（外联空壳×12 + 文档同步×27）**：SMS/微信/AI 推理类保持 mock 并同步设计文档明确 Phase 2 边界；可本地实现类（退额度/重试/级联/清理任务）直接补齐实现
5. 全量回归测试后输出 Round 13 复验报告
