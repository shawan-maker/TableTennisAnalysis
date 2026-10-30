# 后端代码 - 遗漏检查报告 - Round 13

> 日期：2026-10-29 / 2026-10-30（回归收尾）
> 范围：R12 全部修复的闭环复验（P1 28 + P2 60 + P3 63）+ R13 新发现 P2+ 修复 + 全量回归
> 方法：P1 逐项核验（代码级证据 + 针对性回归测试）→ 8 批次 P3 文档同步代理 → R13 复验新发现修复 → 分批 + 全量回归（回归阶段 py-spy + 探针 + 时间窗 + Redis 键实证 6 项测试侧缺陷并修复，其中 1 项兼生产 worker 缺陷）
> 基线：R8-R11 审查循环收敛后，R12 新增"测试覆盖完整性"维度发现 151 项，本轮完成全部闭环

## 一、执行摘要

| 事项 | 数量 | 状态 |
|------|------|------|
| R12 P1 复验 | 28 项 | ✅ 24 项代码修复核验通过 + 4 项 Phase 2 边界声明闭环 |
| R12 P2 复验 | 60 项 | ✅ 全部修复（round12 §三状态列 + 本轮回归验证） |
| R12 P3 文档同步 | 27 项 | ✅ 8 批次代理回写 16 个切片文档（179 处标注） |
| R13 新发现 | 17 项（1 P1 + 16 P2） | ✅ 全部修复 + 回归测试锁定（含全量回归阶段实证/暴露的 6 项测试侧缺陷：轮询挂死 1 + 跨 loop 连接池污染 2 + 键断言误用 1 + 时间窗依赖 1 + 限流计数跨运行残留 1） |
| R13 代码修复引发的文档滞后 | 4 处 | ✅ 本轮回写闭环（ai_pipeline/auth/match_data/gam） |
| 全量回归 | 499 用例 | ✅ 最终 498 passed / 0 failed / 1 skipped（4 次运行收敛，见 §6.2） |

**结论**：R12 遗留任务（P1 修复、Phase 2 边界、P3 文档同步、全量回归、复验报告）全部完成；R13 复验自身新发现 17 项 P2+ 已全部修复闭环（其中 6 项为全量回归阶段以挂死/失败为线索反向定位出的测试侧缺陷：wait_for 轮询语义失效挂死、跨 loop 连接池污染（测试域 + Celery 任务域两型，后者兼生产 worker 缺陷）、Redis 键断言误用、时间窗依赖、限流计数跨运行残留；均经 py-spy/探针/时间窗/Redis 键实证根因）。Round 14 起进入"连续两轮零 P2+"收敛验证。

## 二、R12 P1 复验明细（28 项）

### 2.1 安全与数据完整性（6 项，全部代码修复核验通过）

| 编号 | 问题 | 复验证据 |
|------|------|----------|
| MatchData-B1 | is_win 前端篡改 | Update Schema 无 is_win 字段；`test_update_record_is_win_not_acceptable` 断言非法字段忽略 + 422 空更新体 |
| MatchData-B2 | is_win 重算 AND→OR | `update_record` 任一比分变更即重算（match_data_service L352-361）；`test_update_record_single_score_recalc` 单边改分翻转胜负 |
| Admin-1 | 禁用管理员 30min 绕过 | admin_service 每请求校验 `is_active`（Redis session 之上）；test_admin 20 passed + 1 skipped |
| Auth-2 | wechat_login 不查 banned | 登录入口拦截封禁用户 403；`TestWechatLogin` 封禁 403 测试 |
| Payment-1 | 续期退款不撤权益 | payment_service L490-508 续期分支回填 `order.subscription_id` + 审计 `target_id=subscription_id` |
| Membership-1 | expired 误报无限额度 | membership_service L115-150 expired/closed 按免费 3 次/日（不再以 tier=member 判定） |

### 2.2 业务规则缺陷（13 项，全部代码修复核验通过）

| 编号 | 问题 | 复验证据 |
|------|------|----------|
| VA-1 | 分享链接 404 | main.py L128-130 share 路由挂根路径 `/share/{share_token}` |
| VA-2 | 任务状态机校验缺失 | ai_pipeline/progress.py L42 `TASK_TRANSITIONS` 矩阵 + L66 转换校验；test_ai_pipeline 矩阵测试 |
| SC-1 | 多局推进未实现 | scoring_service L259-345：局结束累计局分、达赛制自动 finish、致胜球归属局号；R13 补 2 项回归测试（见 §三 SC-1） |
| Training-B1 | generate_advice 任务缺失 | app/tasks/training.py L33 `generate_advice_task`（max_retries=1，SUP-1/2 修复模式） |
| Training-B2 | first_analysis 类型污染 | 建议类型按 new_issue/progress_confirm/persistent_warning 正确分派 |
| Prog-1 | 快照生成无调用方 | R13-AIP-1 闭环：report_generator → `generate_snapshot_task.delay()`（见 §三） |
| Prog-2 | resolved 趋势未实现 | progress_service L228-232 历史有值当前消失 → `trend=resolved` |
| Gam-1 | BADGE_SEEDS 零引用 | gamification_service L482 `seed_badge_definitions` + scripts/seed_badges.py |
| Dash-1 | bust_cache 无调用方 | R13-AIP-1 闭环：scoring finish_match → `bust_cache_task.delay(user_id, "match_end")`（见 §三） |
| Dash-2 | 降级只读检查缺失 | dashboard_service L62-64 读 `downgrade:report:readonly:{uid}` 键 |
| KB-2 | severity 来源错误 | knowledge_base_service L206-208 severity 取 diagnosis JSONB |
| Admin-2 | create_category 重复 500 | admin_service L420 重复 name/code 预检返回 409 |
| Notif-1 | 训练提醒候选判定 | 基于 3 天内 AI 分析/比赛活动（非 TrainingPlan.updated_at） |

### 2.3 外部集成（12 项：8 项代码修复 + 4 项 Phase 2 边界声明）

| 编号 | 处理 | 复验证据 |
|------|------|----------|
| User-2 export_data 断链 | ✅ 代码修复 | tasks/user.py `export_user_data`（SUP-3 `_run_async` 模式）+ spy 投递测试 |
| AIPipeline-1 重试失效 | ✅ 代码修复 | `self.retry()` 无 exc 语义（SUP-1 探针实证三种场景） |
| AIPipeline-2 失败退额度缺失 | ✅ 代码修复 | test_ai_pipeline 退额度语义 4 测试（DECR 回 0/禁负数/幂等不双退/终态不退） |
| AIPipeline-3 级联链不完整 | ✅ 代码修复 | R13-AIP-1 完成（见 §三） |
| AIPipeline-4 is_llm_generated 失真 | ✅ 代码修复 | 按实际生成方式写入；test L456-457 断言降级路径 False |
| Admin-3 / BeatTasks-2 审计清理空壳 | ✅ 代码修复 | tasks/audit.py L16 `AUDIT_LOG_RETENTION_DAYS = 365*3`（3 年 PIPL 保留） |
| BeatTasks-1 4 任务空壳 | ✅ 代码修复 | file_management.py `cleanup_orphan_files`、export.py `cleanup_old_tasks` 等真实实现 |
| KB-1 知识库初始化缺失 | ✅ 代码修复 | scripts/init_knowledge_base.py 幂等灌入 |
| Auth-1 阿里云 SMS | ⏸ Phase 2 边界 | auth_service `_send_aliyun_sms` TODO 桩 + R12 边界注释 + 01-auth/backend.md 边界标注 |
| Notif-2 微信订阅消息 | ⏸ Phase 2 边界 | notification_service `_send_wechat_subscribe` 桩 + 12-notification/backend.md 边界标注 |
| Membership-2 微信到期提醒 | ⏸ Phase 2 边界 | membership_service `_send_wechat_subscribe` 桩 + 10-membership/backend.md 边界标注 |
| AIPipeline-5 AI 推理调用 | ⏸ Phase 2 边界 | Step 1-8 mock 返回 + 切片文档边界标注 |

## 三、R13 新发现与修复（17 项）

| 编号 | 优先级 | 问题 | 修复 | 测试锁定 |
|------|--------|------|------|----------|
| R13-Mbr-N1 | P1 | 额度 Redis key 日期格式跨模块分裂（membership/user isoformat vs yyyymmdd）→ 配额判定读不到对方写入的计数 | membership_service L185/L290、user_service L211 统一 `strftime('%Y%m%d')` | `test_quota_key_format_consistent_across_modules`（模拟扣减方写 yyyymmdd key → GET /membership/quota used_today=2 remaining=1） |
| R13-Auth-N1 | P2 | phone-login 验证码尝试无限制（可无限爆破 6 位码） | `SMS_CODE_MAX_ATTEMPTS=5` + `sms:attempts:{phone}` 计数（5 次/5min 窗口 → 429 ERR_RATE_LIMITED；成功登录清零） | `TestPhoneLoginAttemptLimit`（2 测试：5 次错误后 429 + 正确码在窗口内仍可用） |
| R13-Auth-N2 | P2 | wechat-login/phone-login/send-sms 三端点 422（Pydantic detail）vs API 设计 400 中文消息 | Schema 移除 `min_length`/`pattern` 先行约束，service 层校验返回 400 + 中文 message（`PHONE_PATTERN` 常量） | `TestAuth400ChineseMessages`（3 测试）+ `test_send_sms_invalid_phone` 断言更新 |
| R13-MatchData-1 | P2 | PATCH 编辑比分无赛制校验（单边改分可造平局/非法比分） | `update_record` 应用更新后统一调 `_validate_score_by_format` → 422 ERR_SCORE_INVALID + is_win 重算 | `test_update_record_single_score_recalc` 改用 custom 赛制锁定单边翻转语义（定局赛制无法单边翻转胜负——见 05-match_data 文档同步注记） |
| R13-Gam-N1 | P2 | `add_points` 无 SAVEPOINT 隔离（子操作 IntegrityError 污染调用方事务 → session invalid 连带主流程失败） | 写入段 `db.begin_nested()` 包裹；`check_badges` 移出 SAVEPOINT 单独容错 | test_gamification 回归通过（批次 1） |
| R13-Admin-1 | P2 | 审计日志 ip_address 字段全链路未接线（11 个方法签名有参数但无调用方传入） | admin_service 11 方法签名 + 11 处 `_write_audit_log` 传参 + router 10 活跃端点 `_client_ip(request)` 提取 | test_admin 20 passed + 1 skipped |
| R13-AIP-1 | P2 | 级联 snapshot/bust_cache 内联 await 违反反幻觉约束"级联链必须异步触发"（用户请求路径同步执行） | 新建 `app/tasks/progress.py`（`generate_snapshot_task`）+ `app/tasks/dashboard.py`（`bust_cache_task`）；report_generator/scoring_service 改 `.delay()` 投递；tasks/__init__.py 注册 | test_ai_pipeline autouse spy fixture + `test_full_pipeline_completes` 级联投递断言；test_cascade_chains 28/28 |
| R13-AIP-2 | P2 | 分析完成/失败通知离线兜底缺失（仅 WS 推送，离线用户永远收不到） | progress.py `on_task_complete`/`on_step_failed` 改调 `send_notification`（在线 WS 事件契约不变 / 离线 DB 落库 + 未读 INCR） | test_progress/test_notification 回归通过（批次 2：53/53） |
| R13-Test-N1 | P2 | conftest 废弃 session-scope event_loop fixture（pytest-asyncio 0.24 行为未定义 → 间歇性 "relation user does not exist"） | 移除废弃 fixture + `db_setup` 前后 `engine.dispose()`（清 asyncpg 语句缓存与 DROP SCHEMA 竞态）+ pytest.ini `asyncio_default_fixture_loop_scope = function` | auth 20/20 复验通过 |
| R13-SC-1 | P2 | R12-SC-1 多局推进修复零回归测试（测试覆盖维度缺口） | 新增 `test_multi_game_progression_bo3_auto_finish`（bo3 两局 11:0 → 自动 finish + is_win/final_score 按局分）+ `test_multi_game_cross_game_undo_protection`（跨局撤销 400） | test_scoring 25/25 |
| R13-ND-1 | P2 | `test_cache_bust_match_end` 残缺（只填缓存未断言 bust，测试名与行为不符） | 补全：填 overview + winrate 三 period + technique/heatmap 对照 key → 直调 `bust_cache(match_end)` → 断言事件范围删除 + 范围隔离保留；SC-1 测试补投递断言（spy 化 `bust_cache_task` → `(user_id, "match_end")` 恰一次） | test_dashboard 回归通过（批次 2） |
| R13-WS-Test-1 | P2 | test_ws_channels 5 处 `asyncio.wait_for(pubsub.get_message(), timeout=N)` 挂死：redis-py 7.1.0 `get_message()` 为即时非阻塞轮询（内部 `async_timeout(0)` 立即取消读取返回 None），Python 3.11 嵌套 asyncio.timeout 丢失外层 wait_for 定时器 → 永不超时；`test_reconnect_pushes_unread_notifications` 的 `while len<5` 无限热循环，全量回归挂死于此（py-spy 栈实证 + 探针脚本逐步复刻定位） | 新增 `_poll_pubsub_message`/`_poll_pubsub_messages` 截止时间轮询助手（固定预算 + 50ms 间隔 + 提前收满退出），替换全部 5 处调用点；生产代码无此问题（websocket.py 用 `pubsub.listen()` 阻塞消费） | test_ws_channels 8/8 |
| R13-Test-N2 | P2 | 全局 Redis 池跨 event loop 复用：每测试独立 loop（R13-Test-N1 语义）下，上一测试归还的连接仍满足 `is_connected`（reader/writer 非 None，redis-py `connect_check_health` 早退），新测试检出后首条命令抛 `RuntimeError: Event loop is closed`；被 `is_user_online` 的 `except: return False` 静默吞掉 → 在线用户误判离线 → 写 DB 不推 WS（行为级污染：test_send_notification_online_no_db_write 组合运行必现/单跑通过，探针实证翻转点） | conftest 新增 autouse `_redis_pool_per_loop` fixture（前置丢弃全局引用 + 后置当前 loop `close_redis`，每 loop 重建池）；`is_user_online` 降级路径补 warning 日志（原静默吞错不可观测） | 最小复现（相邻 async 测试对首调用必抛 RuntimeError）修复后消除；test_ws_channels 8/8 + test_ws（同步）/test_scoring 34/34 |
| R13-Test-N3 | P2 | Celery 任务线程循环与全局连接池跨 loop（N2 同型、范围更广）：eager 测试与生产 worker 均逐任务 `asyncio.run` 新循环，复用全局 Redis 池与 asyncpg 引擎池 → 死连接检出 → RuntimeError: Event loop is closed（Redis 侧被吞错、asyncpg 侧 `_cancel_current_command`）→ 全量回归 test_video_analysis 7 项失败（'failed' != 'completed' / 422==200）；兼生产 worker 缺陷（任务循环关闭后池内连接残留死引用） | redis.py 新增 `reset_redis_client()` + `run_isolated(coro)`（前置重置全局引用 + 结束当前 loop close_redis），5 个 `_run_async` 内部包装 + 9 个直调 `asyncio.run` 点包装（共 14 处）；DB 侧 `DB_NULLPOOL` 环境开关 → engine NullPool（conftest.py 顶部 + celery.py 顶部置 1；database.py 条件 = 环境变量 or settings.DEBUG；生产 Web 主进程不导 celery.py 保留连接池复用） | test_video_analysis 19/19（修复前 7 失败 → 修复后全绿） |
| R13-Auth-N3 | P2 | test_new_user_wechat_login_creates_user 断言 wx:session_key 键参数误用 user_id（探针实证 auth_service 写 `wx:session_key:{openid}`，按 user_id 取键不存在 → None）；实施计划 REDIS-I 键表（03 L778 + 02-测试计划 L997）均为 {openid}，01-auth 样例代码 {user.id} 与测试断言为同源笔误 | 测试断言改按 openid 取键（p2_wx_new_001）+ 注释标明键表依据；01-auth/backend.md L333 样例回写 {openid}（P3 文档同步，加 R13 标注） | test_supplements_p2 38/38 |
| R13-Admin-Test-1 | P2 | test_audit_log_filters 时间窗依赖：种子 log4=now-4h，UTC<04:00（上海中午前）运行时落进“昨天” → end_date=昨日 23:59:59 无法排除 → total 4==3（本轮上海 10:36 运行恰在窗口内实证；filter 5 通过/6 失败的组合暴露 end_date 未过滤任何记录） | `_seed_logs` created_at 锚定日历边界固定钟点（`datetime.combine(今日±N 天, 12:00, UTC)`：log1-4 = D-3/D-2/D-1/D 正午），对任意运行时刻确定性成立；注释同步 | test_supplements_p2 38/38 |
| R13-RL-Test-1 | P2 | test_checkin_daily_limit_returns_slowapi_429 跨运行非幂等：limiter storage 为共享远程 Redis（storage_uri=settings.redis_url_computed），checkin `1/day` 计数键 TTL=24h → 第二次全量回归 resp1 即 429（assert 429==200）；实证残留键 `LIMITS:LIMITER/user:1//api/v1/gamification/checkin/1/1/day` value=3、TTL≈22h——#2 通过时写入、#3 命中耗尽（user id 每测试重置为 1 加剧键碰撞） | 文件 autouse fixture 每测试前 `limiter.reset()`——limits 库 Lua 脚本仅按 `LIMITS:*` 前缀分块删除（不触碰业务键），每测试零计数开始 | 连续两次独立运行 5/5 + 5/5（幂等性验证） |

> 测试链路分工说明（R13-AIP-1/ND-1 确立的模式）：eager 模式下 Celery 任务体经 `_run_async` 在新线程 `asyncio.run` 执行，与 pytest-asyncio 主循环的全局连接池跨循环冲突（SUP-4 同型）。R13-Test-N3 证实生产 worker 逐任务新建循环同样命中（全局池跨任务残留死连接），已通过 `run_isolated`（Redis）+ NullPool（DB）系统性修复；修复后 spy 断言与 service 直调的测试分工不变。

## 四、P3 文档同步（R12 遗留 27 项 → 16 文件全覆盖）

8 个批次代理（后因超时与 DB 互踩拆为 10 个子代理）按"以实现为准回写 + 标注"原则完成全部 15+1 模块切片文档同步：

| 模块切片 | 回写处数 | 模块切片 | 回写处数 |
|----------|----------|----------|----------|
| 01-auth | 9 | 09-gamification | 25 |
| 02-user | 17 | 10-membership | 7 |
| 03-video_analysis | 15 | 11-payment | 13 |
| 04-scoring | 16 | 12-notification | 15 |
| 05-match_data | 11 | 13-admin | 14 |
| 06-data_dashboard | 20 | 13-ai_pipeline | 9 |
| 07-training_advice | 9 | 13-beat_schedule | 4 |
| 08-progress_analysis | 9 | 13-knowledge_base | 16 |

- 合计约 179 处回写，标注形式统一含 "P3 文档同步"（R13 批次标注 "R13-P3 文档同步" / "P3 文档同步（R12 复验批次 N）"）
- 处理原则：实现优于设计的文档滞后 → 以实现为准回写并加注；实质契约偏差（如 Auth 422 vs 400）→ 不回写、上报 P2+（本轮 Auth-P2-N2 已修复后回写）
- 16 个切片文档现存 "P3 文档同步" 标注累计 209 处（含 R12 修复期沿用标注）

### 4.1 R13 代码修复引发的文档滞后回写（本轮闭环 4 处）

| 文档 | 回写内容 |
|------|----------|
| 13-infrastructure/ai_pipeline.md L645 | R13-AIP-1 级联改 Celery 投递（任务名/调用点）+ R13-AIP-2 通知离线兜底（原"内联 await 待决策"注记过期） |
| 01-auth/backend.md L124 + §5 端点注释 | Auth-P2-N2 已修复回写（400 中文消息与样例一致）+ R13-Auth-N1 尝试限制语义（5 次/5min → 429） |
| 05-match_data/backend.md §8 测试注记 | R13-MatchData-1 PATCH 赛制校验 422 语义 + 单边翻转仅 custom 赛制可行的说明 |
| 09-gamification/backend.md §5 注记第 11 条 | R13-Gam-N1 add_points SAVEPOINT 事务隔离语义 |

> 12-notification/backend.md 验证无需回写：`send_notification` 通道矩阵（在线 WS / 离线 DB+微信）设计与实现本就一致，R13-AIP-2 变更仅在调用方（ai_pipeline/progress.py），已记录于 ai_pipeline.md。admin.md 验证无需回写：`_write_audit_log` ip_address 参数设计本就存在，R13-Admin-1 修复使实现对齐设计。

## 五、Phase 2 边界声明（4 项，双向声明闭环）

| 编号 | 外联依赖 | 代码侧声明 | 文档侧声明 |
|------|----------|------------|------------|
| Auth-1 | 阿里云 SMS（dysmsapi） | auth_service `_send_aliyun_sms` R12 边界注释（失败仅日志，不阻塞登录链路） | 01-auth/backend.md |
| Notif-2 | 微信订阅消息 | notification_service `_send_wechat_subscribe` R12 边界注释（构造 template_msg 记日志） | 12-notification/backend.md 通道矩阵注记 |
| Membership-2 | 微信到期提醒订阅 | membership_service `_send_wechat_subscribe` R12 边界注释 | 10-membership/backend.md |
| AIPipeline-5 | AI 推理服务（httpx INFERENCE_BASE_URL） | Step 1-8 mock 返回 + ai_pipeline.md Phase 2 标注（含 30s→5min 超时等 R18 修订） | 13-infrastructure/ai_pipeline.md |

## 六、全量回归结果

### 6.1 分批回归（本轮修复针对性验证）

| 批次 | 范围 | 结果 |
|------|------|------|
| 前置（R13 修复期） | test_auth 20、test_admin 20+1skip、test_ai_pipeline 18、test_cascade_chains 28 | 全绿 |
| 批次 1 | test_match_data + test_gamification + test_membership | 47 项（match_data 1 项测试语义更新后 20/20 全绿） |
| 批次 2 | test_dashboard + test_progress + test_notification | 53/53 全绿 |
| 批次 3 | test_scoring（含 SC-1 新增 2 项 + 投递断言） | 25/25 全绿 |
| 批次 4（挂死修复） | test_ws_channels（R13-WS-Test-1 + R13-Test-N2 修复后） | 8/8 全绿 |
| 批次 5（N2 兼容性） | test_ws（同步 TestClient，验证 autouse 异步 fixture 兼容）+ test_scoring | 34/34 全绿 |
| 批次 6（N3 修复验证） | test_video_analysis（R13-Test-N3 三重修复后） | 19/19 全绿 |
| 批次 7（收尾修复验证） | test_supplements_p2（R13-Auth-N3 + R13-Admin-Test-1 修复后） | 38/38 全绿 |
| 批次 8（幂等性验证） | test_rate_limiting（R13-RL-Test-1 修复后）连续两次独立运行 | 5/5 + 5/5 全绿 |

### 6.2 全量回归（单进程串行，避免并发批次 DB schema 互踩；PYTHONUNBUFFERED + --timeout=120 防护）

| 运行 | 触发条件 | 结果 | 结论 |
|------|----------|------|------|
| 第 1 次 | 批次 3 后首次全量 | 15% 挂死于 test_ws_channels | 首次暴露 R13-WS-Test-1（wait_for 轮询语义失效），py-spy 实证 |
| 第 2 次 | WS-Test-1 + Test-N2 修复后 | 489 passed / 9 failed / 1 skipped（18:32 无挂死） | 9 失败 = R13-Test-N3（test_video_analysis 7 项）+ R13-Auth-N3 / R13-Admin-Test-1（test_supplements_p2 2 项），全部单跑复现定位 |
| 第 3 次 | Test-N3 + 收尾修复后 | 497 passed / 1 failed / 1 skipped（23:12） | 唯一失败 = R13-RL-Test-1（checkin 限流键跨运行残留——#2 通过时埋下的 24h 时间炸弹首次触发，非本轮修复引入） |
| 第 4 次 | RL-Test-1 修复后 | **498 passed / 0 failed / 1 skipped（23:05）** | 全量收敛：499 用例全部通过（唯一 skip 为 test_admin 既有跳过项），R13 全部 17 项修复在全量上下文验证闭环 |

## 七、结论与 Round 14 计划

1. **R12→R13 闭环完成**：P1 28（24 修复 + 4 边界）、P2 60、P3 27 文档同步全部闭环；R13 新发现 17 项 P2+ 全部修复（含全量回归阶段反向定位的 6 项测试侧缺陷——wait_for 轮询语义失效挂死、跨 loop 连接池污染两型（测试域 conftest fixture / Celery 任务域 `run_isolated` + NullPool，后者兼生产 worker 逐任务循环缺陷）、wx:session_key 键断言误用（openid）、审计筛选时间窗依赖、限流计数跨运行残留（LIMITS:* Redis 键）；均实证根因并修复）。
2. **Round 14 计划**：启动新一轮"设计文档 vs 代码实现 vs 测试覆盖"三方全量对比（可复用 R12 的 8 批次方法 + R13 修复后的基线），目标"连续两轮零 P2+"。
3. **风险提示**：
   - 全部 R12+R13 修复（86 文件，+10235/-4532）尚未 git commit，建议本轮报告输出后提交一次里程碑 commit。
   - 测试环境依赖远程 VM PostgreSQL/Redis（.env 192.168.40.147）；本地 Docker Desktop 因 UAC 策略无法启动，不影响当前测试链路。
   - 01-auth/backend.md 存在 68 行历史性 U+FFFD 编码损坏（中文被截断为乱码，非本轮引入），建议 Round 14 按 R19 membership/backend.md 重建模式整体重写该文档（P3）。
