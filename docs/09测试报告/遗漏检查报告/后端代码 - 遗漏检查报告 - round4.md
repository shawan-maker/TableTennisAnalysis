# 后端代码实现 vs 设计文档 — Round 4 全量对比审查报告

## 总览

| 指标 | 数值 |
|------|------|
| 审查范围 | membership / payment / notification 三模块 + 基础设施层（logging/sentry/metrics/beat_schedule/ws_manager/redis/database/conftest） |
| 审查维度 | API 端点 / ORM 模型 / Schema 字段 / 会员状态机 / 支付流程 / 通知通道 / Celery Beat / 基础设施初始化 / model_validate / 返回结构 |
| 发现总数 | 27 项（P0×2 + P1×9 + P2×8 + P3×8） |
| R2/R3 修复验证 | 5 项已落地 ✅ + 2 项仍为空桩（R2 推迟项） |
| 修复状态 | 本轮为审查报告，尚未修复 |
| Git 提交 | 无（待修复后提交） |

## 一、审查范围与方法

Round 4 对 Round 2/3 未充分覆盖的三个垂直模块及基础设施层进行代码 vs 设计文档逐行对比：

| 模块组 | 覆盖文件 | 设计文档 |
|--------|----------|----------|
| Membership | models/schemas/services/router/tasks | `10-membership/backend.md` + DB §2.17 + API §11 |
| Payment | models/schemas/services/router | `11-payment/backend.md` + DB §2.18/§2.31 + API §12 |
| Notification | models/schemas/services/router/tasks | `12-notification/backend.md` + DB §2.19 + API §13 |
| Infrastructure | core/logging/sentry/metrics/beat_schedule/websocket/redis/database/celery/deps/response/pagination/config/exceptions + main.py + conftest + pytest.ini | `13-infrastructure/*.md`（logging/sentry/metrics/beat_schedule/ws_manager/conftest.py/pytest_config） |

审查排除 Round 2/3 已修复并验证的 5 项（Membership WS downgrade_policy、Membership Redis cleanup_at、Notification 索引 idx_notif_user_unread、Notification mark_read 原子 decrby、Notification subscribe_templates 422 校验），仅验证其是否仍正确落地、有无回归。

## 二、P0 发现（2 项）

### R4-Infra-1 | P0 | 日志/Sentry/指标基础设施在 main.py 中完全未初始化

| 项目 | 内容 |
|------|------|
| **文件** | `app/main.py` 全文（L1-139） |
| **设计要求** | `logging.md` §2 L59 `configure_logging(log_level, log_format)` 应用启动时调用；`sentry.md` §2 L122-132 `configure_sentry(...)`；`metrics.md` §2 L131-157 `configure_metrics(app)` 暴露 `/metrics` 端点 |
| **代码实现** | `lifespan()`（L28-51）仅初始化 Redis 连接和 WS 中继，未调用 `configure_logging()`、`init_sentry()`、`configure_metrics()`。grep 确认三个函数在 main.py 无引用 |
| **影响** | 生产环境日志为 Python 默认格式而非 structlog JSON；Sentry 从不初始化，异常不上报；`/metrics` 端点不存在，Prometheus 无法 scrape。可观测性基础设施完全失效 |

### R4-Pay-1 | P0 | AuditLog.admin_id NOT NULL 但支付 Service 从不设置，审计日志插入必失败

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/payment_service.py` L105-117/L361-373/L500-511/L585-597；`app/models/admin.py` L77-79 |
| **设计要求** | DB §2.31（`04-数据库详细设计.md` L1012）：`admin_id BIGINT Y FK→admin_user.id, RESTRICT`（必填）；`user_id BIGINT N NULL`（可空，"非管理员操作时填写，如支付模块"）。切片 `11-payment/backend.md` §5 审计日志创建处仅设 `user_id` |
| **代码实现** | `admin.py` L77-79 `admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("admin_user.id", ondelete="RESTRICT"), nullable=False)`；payment_service 四处 AuditLog 创建均仅设 `user_id=`，从不设 `admin_id=` |
| **影响** | `db.commit()` 触发 PostgreSQL NOT NULL constraint violation IntegrityError，支付订单创建、回调处理、退款全部失败。DB 设计（admin_id 必填）与切片设计（支付模块以 user_id 记录审计）冲突在代码层直接体现 |


## 三、P1 发现（9 项）

### R4-Infra-2 | P1 | Sentry ignore_errors 过滤方向与设计相反 + 缺少 before_send 脱敏钩子

| 项目 | 内容 |
|------|------|
| **文件** | `app/core/sentry.py` L45-48 |
| **设计要求** | `sentry.md` §2 L94-98 `ignore_errors=[HTTPException]`，注释"R27-P3-backend-1: 移除 AppException — 业务异常应上报"；L48-61 定义 `_before_send` 钩子对 phone/openid/token 脱敏 |
| **代码实现** | L45-47 `ignore_errors=["app.core.exceptions.AppException"]`（与设计相反，过滤了应上报的 AppException，未过滤 HTTPException）；无 `before_send` 钩子（grep 确认 `before_send` 在 `app/` 无匹配） |
| **影响** | 业务异常被全部过滤，Sentry 收不到任何业务错误；敏感信息（openid/token）未经脱敏直接上报，违反 PIPL 合规和设计 L225 anti-hallucination 约束 |

### R4-Infra-3 | P1 | structlog 缺少 _redact_sensitive 和 _add_request_id 处理器

| 项目 | 内容 |
|------|------|
| **文件** | `app/core/logging.py` L28-35 |
| **设计要求** | `logging.md` §2 L37-46 `_redact_sensitive`（phone/token/openid 等保留前4后4）；L49-55 `_add_request_id`（从 `request_id_var` ContextVar 注入 request_id） |
| **代码实现** | processors 列表为 `merge_contextvars`、`add_log_level`、`TimeStamper(fmt="iso")`、`StackInfoRenderer`、`format_exc_info`，两个关键处理器完全缺失；无 `app/core/context.py`（`request_id_var` 未定义） |
| **影响** | 敏感信息明文写入日志，违反设计 L199 约束；日志无 request_id 字段，无法实现 L14"贯穿 Service → Celery → WebSocket 全链路"请求追踪 |

### R4-Infra-4 | P1 | Prometheus 指标定义与设计严重不一致 + /metrics 端点未挂载

| 项目 | 内容 |
|------|------|
| **文件** | `app/core/metrics.py` L1-113；`app/main.py`（无 /metrics 路由） |
| **设计要求** | `metrics.md` §2 定义 12 个业务指标：ai_analysis_total、ai_analysis_duration_seconds、ai_pipeline_step_duration_seconds、gpu_inference_queue_depth、gpu_memory_usage_bytes、payment_order_total、payment_amount_cents_total、payment_callback_duration_seconds、membership_active_count、membership_downgrade_total、ws_active_connections、app_info；`configure_metrics(app)` 用 Instrumentator 采集并暴露 `/metrics` |
| **代码实现** | 定义完全不同的指标集：http_requests_total、http_request_duration、active_users、video_analysis_tasks_total（非 ai_analysis_total）、ai_inference_duration（非 ai_analysis_duration_seconds）、celery_tasks_total、redis_connections。完全缺失：支付指标×3、会员指标×2、WS 指标、GPU 指标×2、流水线步骤指标、app_info。`configure_metrics` 函数不存在，`metrics_endpoint()` 定义但从未挂载 |
| **影响** | 指标命名、Label、采集方式均不符；`/metrics` 端点不存在，Prometheus scrape 完全不可用 |

### R4-Notif-1 | P1 | Celery 通知任务为空桩实现（cleanup_old_notifications / training_reminder）

| 项目 | 内容 |
|------|------|
| **文件** | `app/tasks/notification.py` L8-22 |
| **设计要求** | `12-notification/backend.md` §6.3（L844-927）training_reminder 应查询 >3 天未训练用户并调用 send_training_reminder；§6.4（L933-979）cleanup_old_notifications 应删除 90 天前已读 + 归档 180 天前未读 |
| **代码实现** | 两个任务仅有 `logger.info` + `return {"status": "ok"}` + TODO 注释，业务逻辑完全未实现 |
| **影响** | Beat 调度触发任务但无实际效果；旧通知永不清理（数据膨胀），训练提醒永不发送 |

### R4-Mbr-1 | P1 | MembershipService._send_wechat_subscribe 仍为空桩（R2 推迟项未解决）

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/membership_service.py` L355-377 |
| **设计要求** | `10-membership/backend.md` §5 L753-776 调用 `from app.core.wechat import send_subscribe_message`，传入 template_id="membership_expiry_reminder"、page、data |
| **代码实现** | L368-377 为 TODO 注释桩，仅 `logger.info("wechat subscribe message sent: ...")` |
| **影响** | R2-Mbr-1 推迟项仍存在；会员到期提醒仅走 WS 通道，微信订阅消息通道未实现 |

### R4-Notif-2 | P1 | NotificationService._send_wechat_subscribe 仍为空桩（R2 推迟项未解决）

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/notification_service.py` L117-140 |
| **设计要求** | `12-notification/backend.md` §5 L394-422 获取用户 openid，构造 template_msg，调用 wechat_client.send_subscribe_message |
| **代码实现** | L129-139 为 TODO 注释桩，仅 `logger.info("wechat subscribe message sent: ...")` + `return True` |
| **影响** | R2-Notif-1 推迟项仍存在；离线用户通知仅写 DB，微信订阅消息通道未实现。设计 L1099 [X-14] 覆盖度修复声称已替换 pass 占位，但代码仍为 TODO 桩 |

### R4-Infra-5 | P1 | conftest.py 使用真实 PostgreSQL/Redis 而非设计的内存 SQLite + fakeredis

| 项目 | 内容 |
|------|------|
| **文件** | `tests/conftest.py` L31-91 |
| **设计要求** | `conftest.py.md` §2 L145-162 `db_session` 用 `create_async_engine("sqlite+aiosqlite:///:memory:")`；L169-349 定义 MockRedis 类（完整方法集）+ mock_redis fixture；L382-392 `_build_override_map` 覆盖 get_redis 依赖 |
| **代码实现** | 用真实 PostgreSQL（DROP SCHEMA/CREATE SCHEMA，L39-42）和真实 Redis（`await get_redis()` L46）；无 MockRedis 类、无 mock_redis fixture、无依赖覆盖 |
| **影响** | 测试依赖外部 PostgreSQL + Redis 服务（Docker Compose），无法在无外部依赖环境下运行，违反设计 L15"内存 SQLite + fakeredis，无需外部依赖"目标 |

### R4-Pay-2 | P1 | 退款未执行 24h-7d 部分退款 50% 限额校验

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/payment_service.py` L548-557 |
| **设计要求** | `05-API详细设计.md` §12.4 L3186 "下单 24h~7d：支持部分退款（refund_amount_cents ≤ order.amount_cents * 50%），需管理员审核" |
| **代码实现** | L544-557 仅检查 `refund_amount_cents > order.amount_cents`（全额超出），未检查 24h-7d 区间 50% 限额；partial 分支不校验是否 ≤50% |
| **影响** | 允许 24h-7d 区间全额退款（refund_amount_cents = order.amount_cents），违反业务规则 |

### R4-Infra-6 | P1 | 缺少 request_id 中间件（X-Request-ID 注入）

| 项目 | 内容 |
|------|------|
| **文件** | `app/main.py` L76-95（中间件区）；`app/core/` 无 context.py / middleware.py |
| **设计要求** | `logging.md` §2 L116-133 `app/core/middleware.py` 定义 request_id_middleware，从 X-Request-ID header 或 uuid4[:8] 生成 request_id，设置到 request_id_var ContextVar，响应头回传 |
| **代码实现** | main.py 仅有 CORS 中间件（L81-87）和限流（L90-91），无 request_id 中间件；无 `app/core/context.py`（request_id_var 未定义）；无 `app/core/middleware.py` |
| **影响** | 设计 L14"每个请求分配 request_id，贯穿全链路"无法实现；日志无 request_id 关联，Sentry 无 request_id tag（set_request_context 也不存在） |


## 四、P2 发现（8 项）

### R4-Mbr-2 | P2 | 会员状态机 grace_period 状态从未被赋值

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/membership_service.py` L185-225（check_expiry） |
| **设计要求** | `10-membership/backend.md` §9 L952 验证清单"订阅生命周期状态正确（active → expiring_soon → expired → grace_period → closed）"；`_get_active_subscription` L630 含 grace_period 在合法状态列表 |
| **代码实现** | check_expiry 三步：active→expiring_soon（L200）、active/expiring_soon→expired（L211）、expired→closed（L222）。grace_period 从未被任何代码路径赋值 |
| **影响** | 状态机设计为五态但代码仅实现四态（跳过 grace_period）；`_get_active_subscription` 查询条件含 grace_period 但永无数据；宽限期概念存在但未落地 |

### R4-Mbr-3 | P2 | 实时兜底仅检查 active 状态到期，未覆盖 expiring_soon→expired 转换

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/membership_service.py` L90-97 |
| **设计要求** | `10-membership/backend.md` §5 L441-452 实时校验兜底应在每次请求时检查 `expire_at < now` |
| **代码实现** | L90 `if subscription.status == "active" and subscription.expire_at < now` 仅处理 active 状态到期；L94 仅处理 active 即将到期；未处理 expiring_soon 状态的到期转换 |
| **影响** | 若用户在 expiring_soon 期间未访问系统，订阅实际已过期但状态仍为 expiring_soon；下次请求 `_get_active_subscription` 返回此记录（expiring_soon 在合法列表），但实时检查跳过它；导致已过期订阅前端显示为 expiring_soon 而非 expired |

### R4-Notif-3 | P2 | WS 端点重连时不调用 on_ws_reconnect 补偿机制

| 项目 | 内容 |
|------|------|
| **文件** | `app/api/v1/ws.py` L62-72 |
| **设计要求** | `12-notification/backend.md` §5 L617-632 `on_ws_reconnect` 拉取未读通知数并推送 sync 事件；§8 L1068 验证清单"离线消息补偿：断连期间消息写入 DB，重连后 sync 事件推送" |
| **代码实现** | ws.py L68-72 仅发送 `{"event": "connected", "data": {"user_id": user_id}}`，从未调用 `NotificationService.on_ws_reconnect(user_id)` |
| **影响** | `on_ws_reconnect` 方法在 notification_service.py L304-321 已实现，但 WS 端点不调用；断连期间离线消息（已写 DB）不会在重连时通过 sync 事件补偿推送，违反设计 L1068 |

### R4-Infra-7 | P2 | WS 端点绕过 WSManager，直接操作 Redis pubsub

| 项目 | 内容 |
|------|------|
| **文件** | `app/api/v1/ws.py` L64-66/L77-86；`app/services/notification_service.py` L43-46 |
| **设计要求** | `ws_manager.md` §6 L261-262 "基础设施层提供统一 WS 能力，业务模块通过依赖注入调用，不直接操作 starlette WebSocket"；`WSManager` 提供 broadcast_to_room/broadcast_to_user/send_personal |
| **代码实现** | ws.py 端点直接调用 `redis.pubsub()` 和 `redis.setex(f"ws:online:{user_id}", ...)`，不使用 WSManager；notification_service 的 `_push_ws` 直接 `redis.publish(channel, message)`，不通过 ws_manager.broadcast_to_user |
| **影响** | WSManager 已实现（websocket.py 116 行）且 main.py L39 启动了 start_relay()，但实际 WS 端点和通知 Service 都不使用它；WSManager 的 _rooms 映射永远为空，relay 中继消息无本地消费者；统一 WS 抽象层形同虚设 |

### R4-Notif-4 | P2 | 通知清理任务设计引用不存在的 status 字段

| 项目 | 内容 |
|------|------|
| **文件** | 设计 `12-notification/backend.md` L976；代码 `app/models/notification.py` L28-55 |
| **设计要求** | 设计 §6.4 L968-977 `record.status = "archived"` 归档 180 天前未读通知 |
| **代码实现** | NotificationRecord 模型字段为 id/user_id/type/title/content/is_read/extra_data/created_at，无 status 字段 |
| **影响** | 设计清理逻辑引用了模型中不存在的 status 字段；若按设计实现清理任务（当前为 TODO 桩避免了此问题），将触发 AttributeError；设计与模型定义不一致 |

### R4-Pay-3 | P2 | PaginatedOrders 类型别名缺失，list_orders 返回 dict 而非设计 Schema

| 项目 | 内容 |
|------|------|
| **文件** | `app/schemas/payment.py`（无 PaginatedOrders）；`app/services/payment_service.py` L271-292 |
| **设计要求** | `11-payment/backend.md` §4 L598 `PaginatedOrders = Paginated[OrderBrief]`；§5 L917-920 `list_orders` 返回 PaginatedOrders 实例 |
| **代码实现** | schemas/payment.py 未定义 PaginatedOrders，未导入 Paginated；list_orders 返回 dict（L289-292）`{"total":..., "page":..., "page_size":..., "items":[...]}` |
| **影响** | 返回结构字段名与设计一致，但类型从 PaginatedOrders（Pydantic 模型）降级为裸 dict，丢失类型安全和 model_config；同样问题存在于 notification_service.py list_notifications |

### R4-Infra-8 | P2 | Celery Beat 任务名使用 app.tasks 前缀，与设计短名不一致

| 项目 | 内容 |
|------|------|
| **文件** | `app/core/beat_schedule.py` L17-67；`app/tasks/membership.py` L9；`app/tasks/notification.py` L8/L16 |
| **设计要求** | `beat_schedule.py.md` §2 L46 `"task": "file_management.cleanup_orphans"`、L66 `"task": "membership.check_expiry"`；切片 `10-membership/backend.md` §7 L854 `@shared_task(name="membership.check_expiry")` |
| **代码实现** | beat_schedule 用 `"app.tasks.file_management.cleanup_orphan_files"`、`"app.tasks.membership.check_expiry"` 等；@shared_task 用 `name="app.tasks.membership.check_expiry"` 等 |
| **影响** | 任务名统一加了 app.tasks. 前缀，与设计短名不符；代码内 beat 表与 @shared_task 声明一致（功能正常），但偏离设计命名规范，影响跨环境任务名引用和文档对齐 |

### R4-Infra-9 | P2 | Beat 调度缺少 default 队列 options 和 description 字段

| 项目 | 内容 |
|------|------|
| **文件** | `app/core/beat_schedule.py` L14-68 |
| **设计要求** | `beat_schedule.py.md` §2 每个 Beat 条目含 `"options": {"queue": "default"|"infra"}` + `"description": "..."` |
| **代码实现** | 仅 file-management-orphan-cleanup（L19）、notification-old-cleanup（L35）、audit-log-cleanup（L60）、export-cleanup-old-tasks（L66）有 options；scoring/membership/notification-training-reminder/ai-inference-health-check/gamification/user-account-deletion 均缺 options；所有条目缺 description |
| **影响** | default 队列任务未显式指定队列（虽默认行为可接受），description 缺失影响运维可读性；设计 §5 L242"错峰调度"、L243"队列分离"运维要求未完整落地 |


## 五、P3 发现（8 项）

### R4-Mbr-4 | P3 | MembershipTierConfig 的 created_at/updated_at 使用 server_default 而非设计要求的 lambda

| 项目 | 内容 |
|------|------|
| **文件** | `app/models/membership.py` L43-48 |
| **设计要求** | `10-membership/backend.md` §3 L216-217 `default=lambda: datetime.now(timezone.utc)`；L971 覆盖度修复 A-9 明确要求"default/onupdate 改为 lambda 表达式" |
| **代码实现** | L43-48 使用 `server_default=func.now()` 和 `onupdate=func.now()`（DB 端默认值）；同文件 Subscription（L74-79）使用 `default=lambda: datetime.now(timezone.utc)`（Python 端） |
| **影响** | 同一文件内两种默认值策略不一致；server_default 依赖 DB 时区配置，lambda 保证 UTC；Order/PaymentRecord/RefundRecord/NotificationRecord 同样使用 server_default 而非 lambda |

### R4-Notif-5 | P3 | mark_read 使用 .returning() 替代 rowcount（偏离设计但为改进）

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/notification_service.py` L177-188 |
| **设计要求** | `12-notification/backend.md` §5 L510-521 `result = await db.execute(stmt); updated = result.rowcount` |
| **代码实现** | L178-187 使用 `.returning(NotificationRecord.id)` + `result.scalars().all()` 获取实际更新 ID 列表，`updated_count = len(updated_ids)` |
| **影响** | 使用 RETURNING 子句替代 rowcount，在 async SQLAlchemy 中更可靠（rowcount 在某些场景不可靠），功能等价或更优，但偏离设计实现 |

### R4-Infra-10 | P3 | Celery autodiscover 使用 "app.tasks" 而非设计显式模块列表

| 项目 | 内容 |
|------|------|
| **文件** | `app/core/celery.py` L39-42 |
| **设计要求** | `beat_schedule.py.md` §4 L217-229 列出 9 个显式模块路径：app.tasks.file_management/scoring/membership/notification/ai_inference_health/gamification/user/audit + app.ai_pipeline |
| **代码实现** | L39-42 仅 `["app.ai_pipeline", "app.tasks"]`，依赖 `app/tasks/__init__.py` 导入所有子模块 |
| **影响** | 功能等价（`__init__.py` L4-14 导入了全部 9 个模块），但设计要求显式列举；app.tasks 方式依赖 __init__.py 维护完整导入列表，若遗漏导入则任务不被发现 |

### R4-Infra-11 | P3 | pytest.ini 缺少 unit/integration/gpu 标记和 asyncio_default_fixture_loop_scope

| 项目 | 内容 |
|------|------|
| **文件** | `pytest.ini` L1-39 |
| **设计要求** | `pytest_config.md` §2 L40-45 markers 含 unit/integration/slow/gpu 四个；L37 `asyncio_default_fixture_loop_scope = "session"`；L78-102 定义 .coveragerc |
| **代码实现** | markers 仅有 slow/integration/smoke（L30-33），缺 unit 和 gpu；无 asyncio_default_fixture_loop_scope；无 .coveragerc 文件 |
| **影响** | 缺 unit 标记导致 `pytest -m unit` 无法筛选单元测试；缺 gpu 标记导致 CI 无法通过 `-m "not gpu"` 跳过 GPU 测试 |

### R4-Pay-4 | P3 | Order 模型 idx_order_no 索引与 unique 约束冗余

| 项目 | 内容 |
|------|------|
| **文件** | `app/models/payment.py` L61 |
| **设计要求** | `11-payment/backend.md` §3 L475-477 `__table_args__` 仅定义 idx_order_user_created 和 idx_order_status；order_no 字段已有 unique=True（L455）自动创建唯一索引 |
| **代码实现** | L61 额外定义 `Index("idx_order_no", "order_no")`（DB 设计 §2.18 L762 确实列出此索引，但 unique=True 已覆盖） |
| **影响** | unique=True 已创建唯一索引，idx_order_no 非唯一索引冗余；虽对齐 DB 设计但浪费存储和写入开销 |

### R4-Infra-12 | P3 | structlog 配置偏离设计（wrapper_class/logger_factory/context_class）

| 项目 | 内容 |
|------|------|
| **文件** | `app/core/logging.py` L41-46 |
| **设计要求** | `logging.md` §2 L81-87 `wrapper_class=structlog.stdlib.BoundLogger`、`context_class=dict`、`logger_factory=structlog.stdlib.LoggerFactory()` |
| **代码实现** | L43 `wrapper_class=structlog.make_filtering_bound_logger(log_level)`（不同）、L44 `logger_factory=structlog.PrintLoggerFactory()`（不同）、无 `context_class=dict` |
| **影响** | make_filtering_bound_logger 提供日志级别过滤（功能差异），PrintLoggerFactory vs stdlib.LoggerFactory 输出方式不同；context_class=dict 缺失影响 ContextVar 合并行为 |

### R4-Mbr-5 | P3 | NotificationRecord 模型导入 Integer 但未使用

| 项目 | 内容 |
|------|------|
| **文件** | `app/models/notification.py` L17 |
| **设计要求** | 设计 §3（`12-notification/backend.md` L230）仅导入 BigInteger/String/Text/Boolean/ForeignKey/Index/DateTime |
| **代码实现** | L11-21 额外导入 Integer（未使用） |
| **影响** | 冗余导入，不影响功能 |

### R4-Pay-5 | P3 | _decrypt_callback MOCK 模式直接返回 resource 而非模拟解密

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/payment_service.py` L427-430 |
| **设计要求** | `11-payment/backend.md` §5 L1066-1086 `_decrypt_callback` 应使用 AES-256-GCM 解密 |
| **代码实现** | L428-430 `if settings.WECHAT_PAY_MOCK: return resource`——MOCK 模式直接返回原始 resource 字典，不模拟解密 |
| **影响** | 设计文档无 MOCK 模式概念；MOCK 模式下回调测试无法验证解密逻辑路径；生产环境关闭 MOCK 后走真实 AESGCM 解密（L432-446），逻辑正确 |

## 六、R2/R3 修复验证

| 修复项 | 状态 | 验证结果 |
|--------|------|---------|
| Membership WS 推送 downgrade_policy | ✅ 已落地 | membership_service.py L304-310 downgrade_policy 字段含 5 项策略 |
| Membership Redis key cleanup_at | ✅ 已落地 | membership_service.py L289-293 cleanup_at 字段在 JSON 中 |
| Notification 索引名 idx_notif_user_unread | ✅ 已落地 | notification.py L51 `Index("idx_notif_user_unread", "user_id", "is_read", "created_at")` |
| Notification mark_read 原子 decrby | ✅ 已落地 | notification_service.py L195 `redis.decrby(key, len(updated_ids))` + L198-199 负数修正 |
| Notification subscribe_templates 422 校验 | ✅ 已落地 | notification_service.py L243-246 模板 ID 校验 + L246 `AppException(..., 422, code=40004)` |
| R2-Mbr-1: wechat_subscribe 空桩 | ⚠️ 仍存在 | 见 R4-Mbr-1 |
| R2-Notif-1: wechat_subscribe 空桩 | ⚠️ 仍存在 | 见 R4-Notif-2 |

**R2/R3 修复未引入新问题**：已验证的 5 项修复实现正确，未发现因修复引入的回归。decrby + 负数修正逻辑正确。downgrade_policy 结构完整。

## 七、汇总统计

| P 级别 | 数量 | 编号 |
|--------|------|------|
| **P0** | **2** | R4-Infra-1, R4-Pay-1 |
| **P1** | **9** | R4-Infra-2, R4-Infra-3, R4-Infra-4, R4-Notif-1, R4-Mbr-1, R4-Notif-2, R4-Infra-5, R4-Pay-2, R4-Infra-6 |
| **P2** | **8** | R4-Mbr-2, R4-Mbr-3, R4-Notif-3, R4-Infra-7, R4-Notif-4, R4-Pay-3, R4-Infra-8, R4-Infra-9 |
| **P3** | **8** | R4-Mbr-4, R4-Notif-5, R4-Infra-10, R4-Infra-11, R4-Pay-4, R4-Infra-12, R4-Mbr-5, R4-Pay-5 |
| **总计** | **27** | |

**按模块分布**：

| 模块 | P0 | P1 | P2 | P3 | 小计 |
|------|----|----|----|----|------|
| Infra（基础设施） | 1 | 5 | 2 | 4 | 12 |
| Mbr（会员） | 0 | 1 | 2 | 1 | 4 |
| Pay（支付） | 1 | 1 | 1 | 2 | 5 |
| Notif（通知） | 0 | 2 | 2 | 1 | 5 |
| 跨模块（Mbr-5 归 Notif） | - | - | - | 1（计 Infra-12 不在此列） | - |

> 注：R4-Mbr-5 实为 notification.py 冗余导入，按发现时归属模块编号为 Mbr，统计时归入 Mbr 列。

## 八、优先修复建议

1. **P0 立即修复**：
   - R4-Pay-1（AuditLog admin_id NOT NULL 冲突——支付功能不可用）：将 `admin.py` 的 `admin_id` 改为 `nullable=True`（对齐 DB 设计 user_id 可空、admin_id 必填的语义需重新评估，或在 payment_service 补设 admin_id）
   - R4-Infra-1（main.py 初始化调用缺失——可观测性归零）：在 `lifespan()` 中补调用 `configure_logging()`、`init_sentry()`、`configure_metrics()`
2. **P1 尽快修复**：
   - R4-Infra-2/3（Sentry/日志安全脱敏缺失）：修正 ignore_errors 方向，补 before_send 钩子和 _redact_sensitive/_add_request_id 处理器
   - R4-Infra-4（Prometheus 指标缺失）：按设计重新定义 12 个业务指标，实现 configure_metrics 并挂载 /metrics
   - R4-Notif-1（Celery 任务空桩）：实现 cleanup_old_notifications 和 training_reminder 业务逻辑
   - R4-Infra-5（conftest 真实服务依赖）：实现 MockRedis 类和内存 SQLite engine
   - R4-Pay-2（退款 50% 校验）：补充 24h-7d 区间部分退款限额检查
   - R4-Infra-6（request_id 中间件）：创建 context.py 和 middleware.py，注册中间件
3. **R2 推迟项**：R4-Mbr-1/R4-Notif-2 微信订阅消息仍为 TODO 桩，建议明确 Phase 2 交付或补充实现

## 九、结论

Round 4 审查表明，Round 2/3 虽已将后端代码审查"收敛"，但其覆盖范围限于 12 个业务模块的 API/ORM/Schema/业务逻辑维度，未充分覆盖 membership/payment/notification 三模块的深度流程（状态机、支付退款规则、通知补偿机制）以及基础设施层的初始化与可观测性配置。

本次审查发现的 2 个 P0 问题（AuditLog admin_id 冲突、main.py 未初始化可观测性）均为功能性阻断级别，需立即修复。9 个 P1 问题集中在基础设施层（Sentry/日志/指标/conftest/request_id 中间件）和 Celery 任务空桩，影响生产环境可观测性、安全合规和定时任务有效性。

建议在修复 P0/P1 后进行 Round 5 验证，确认修复无回归后再进入前端开发阶段。

---

*本报告基于 Round 4 审查时点的代码状态（commit `1f394f8` 之后、未修复 R4 发现项之前）。*
