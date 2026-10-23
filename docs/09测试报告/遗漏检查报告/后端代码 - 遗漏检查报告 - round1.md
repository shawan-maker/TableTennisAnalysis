# 📋 后端代码实现 vs 设计文档 — 遗漏检查报告

## 总览

| 指标               | 数值                                                |
| ------------------ | --------------------------------------------------- |
| 对比模块           | 13 个业务模块 + 基础设施                            |
| 对比维度           | 4 维度（API 端点 / ORM 模型 / 业务逻辑 / 基础设施） |
| 已实现端点         | ~89/96 HTTP + 1 WebSocket                           |
| ORM 模型           | 36 个（设计 35 表 + 1 提前实现）                    |
| **P0（严重遗漏）** | **30 项**                                           |
| **P1（重要偏差）** | **14 项**                                           |
| **P2（一般偏差）** | **31 项**                                           |
| **P3（建议优化）** | **32 项**                                           |
| **合计**           | **107 项**                                          |

## 一、P0 严重遗漏（30 项 — 必须立即修复）

### 1.1 端点完全缺失（10 项）

| #     | 模块 | 设计端点                              | 代码状态 | 影响                                                         |
| ----- | ---- | ------------------------------------- | -------- | ------------------------------------------------------------ |
| P0-1  | Auth | `POST /auth/phone-login`              | ❌ 未实现 | 手机号登录链路完全缺失                                       |
| P0-2  | Auth | `POST /auth/send-sms`                 | ❌ 未实现 | 短信验证码发送缺失                                           |
| P0-3  | User | `GET /users/big-data`                 | ❌ 未实现 | 趣味统计卡片功能缺失（含间接胜利 BFS 算法）                  |
| P0-4  | User | `DELETE /users/account`               | ❌ 未实现 | 用户注销功能缺失（72h 冷静期 + Celery 延迟任务）             |
| P0-5  | User | `POST /users/account/cancel-deletion` | ❌ 未实现 | 注销取消功能缺失                                             |
| P0-6  | User | `POST /users/export-data`             | ❌ 未实现 | 数据导出功能缺失（PIPL 合规）                                |
| P0-7  | User | `GET /users/export-data/{task_id}`    | ❌ 未实现 | 导出状态查询缺失                                             |
| P0-8  | User | 对应 Service 方法全部缺失             | ❌ 未实现 | `get_big_data` / `_compute_indirect_wins` / `delete_account` / `cancel_deletion` / `export_data` / `get_export_status` 共 6 个方法 |
| P0-9  | User | 对应 Schema 全部未定义                | ❌ 未实现 | `BigDataResponse` / `AccountDeletionRequest` / `AccountDeletionResponse` / `ExportCreateResponse` / `ExportStatusResponse` 共 5 个 Schema |
| P0-10 | User | `ExportTask` ORM Model                | ❌ 未实现 | 数据导出任务表完全缺失                                       |

### 1.2 权限守卫缺失（2 项）

| #     | 模块     | 设计要求                                                     | 代码实现                                          | 影响                   |
| ----- | -------- | ------------------------------------------------------------ | ------------------------------------------------- | ---------------------- |
| P0-11 | Training | `GET /templates`、`GET /templates/{id}`、`GET /plans/{id}/adjustments`、`POST /plans/{id}/re-evaluate`、`GET /plans/{id}/sessions`、`POST /plans/{id}/sessions/{sid}/complete` 共 6 个端点权限为 `require_membership("member")` | 6 个端点仅使用 `get_current_user`（登录即可访问） | 免费用户可访问会员功能 |
| P0-12 | Training | `re_evaluate_plan` 方法内调用 `MembershipService.check_membership` → 非会员 403 | 无会员权限检查                                    | 会员权限校验完全缺失   |

### 1.3 基础设施完全缺失（4 项）

| #     | 模块     | 设计要求                                        | 代码实现                                 | 影响                                                         |
| ----- | -------- | ----------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------ |
| P0-13 | 基础设施 | `app/tasks/` 下 10 个 Celery 任务实现           | `app/tasks/__init__.py` 为空文件（1 行） | **全部 10 个定时任务无法执行**：会员到期检测、通知清理、训练提醒、审计清理、积分结算、OSS 清理、分区创建、AI 重试、月报生成、排行快照 |
| P0-14 | 基础设施 | `app/core/logging.py` — structlog JSON 格式日志 | ❌ 文件不存在                             | 结构化日志完全缺失                                           |
| P0-15 | 基础设施 | `app/core/sentry.py` — Sentry 错误追踪          | ❌ 文件不存在                             | 错误追踪完全缺失                                             |
| P0-16 | 基础设施 | `app/core/metrics.py` — Prometheus 指标         | ❌ 文件不存在                             | 指标监控完全缺失                                             |

### 1.4 ORM 模型字段严重不一致（3 项）

| #     | 模块  | 设计定义                                                 | 代码实现                                     | 影响                       |
| ----- | ----- | -------------------------------------------------------- | -------------------------------------------- | -------------------------- |
| P0-17 | Admin | `AuditLog.admin_id` → FK `admin_user.id` (RESTRICT)      | `AuditLog.user_id` → FK `user.id` (SET NULL) | 审计日志无法关联管理员身份 |
| P0-18 | Admin | `AuditLog.changes` JSONB（字段级变更 {field:{old,new}}） | ❌ 字段不存在                                 | 变更内容无法记录           |
| P0-19 | Admin | `SystemConfig.config_value` JSONB                        | `SystemConfig.value` Text                    | 无法存储结构化配置         |

### 1.5 配置缺失（3 项）

| #     | 模块 | 设计要求                                                     | 代码实现           | 影响                    |
| ----- | ---- | ------------------------------------------------------------ | ------------------ | ----------------------- |
| P0-20 | Auth | `AuthService.phone_login` / `send_sms` / `_send_aliyun_sms`  | ❌ 方法完全缺失     | 手机号登录链路无法工作  |
| P0-21 | Core | `config.py` 缺少 `ALIYUN_SMS_ACCESS_KEY` / `ALIYUN_SMS_SECRET` / `ALIYUN_SMS_SIGN_NAME` / `ALIYUN_SMS_TEMPLATE_CODE` | ❌ 环境变量未定义   | 阿里云短信服务无法配置  |
| P0-22 | Core | `security.py` RSA 加密工具                                   | ❌ 注释提及但无实现 | 密码加密等 RSA 场景缺失 |

### 1.6 业务逻辑缺失（8 项）

| #     | 模块           | 设计要求                                                     | 代码实现                                            | 影响                                            |
| ----- | -------------- | ------------------------------------------------------------ | --------------------------------------------------- | ----------------------------------------------- |
| P0-23 | Video Analysis | `confirm_upload` 校验 `5s ≤ duration ≤ 600s`                 | 获取 duration 后未做范围校验                        | 用户可上传任意时长视频进入 AI 流水线            |
| P0-24 | Progress       | `_linear_regression_forecast` 方法（R²>0.4 返回预测）        | ❌ 方法完全缺失，`get_summary` 返回 `"forecast": {}` | 趋势预测功能完全缺失                            |
| P0-25 | Progress       | `get_comparison` 返回 6 维度对比                             | 仅返回 2 维度（technique_stats + problem_changes）  | 报告对比缺失 4 个维度                           |
| P0-26 | Progress       | `get_problem_changes` 返回 `ProblemChangeItem` 结构化对象    | 返回简单字符串列表 `list[str]`                      | 缺失 first_seen / last_seen / persistence_count |
| P0-27 | Progress       | `_extract_metrics` 从 `technique_stats` 直接读取比率值       | 从 `technique_distribution` 计算比率                | 指标提取逻辑不一致，可能导致指标值错误          |
| P0-28 | Gamification   | `_auto_checkin` 完整逻辑（更新 streak + 加打卡积分 + 处理 bonus） | 仅写打卡记录(points_earned=0)                       | 自动打卡积分和连续打卡奖励完全缺失              |
| P0-29 | Admin          | 退款端点应使用 `get_admin_session`（Redis session 独立认证） | 使用 `get_current_admin`（临时 JWT 实现）           | Admin 认证体系未替换为正式实现                  |
| P0-30 | Notification   | `_send_wechat_subscribe` 微信订阅消息推送                    | 空桩实现（仅 logger.info + return True）            | 离线用户无法收到微信通知                        |

## 二、P1 重要偏差（14 项 — 本迭代应修复）

| #     | 模块         | 设计要求                                                     | 代码实现                                    | 影响                              |
| ----- | ------------ | ------------------------------------------------------------ | ------------------------------------------- | --------------------------------- |
| P1-1  | Auth         | `GET /auth/me` 返回 `membership_tier` 和 `membership_expire_at` | 返回 None（代码注释 `TODO S5`）             | 当前用户信息缺少会员状态          |
| P1-2  | User         | `RatingUpdateRequest.rating` 范围 `ge=500`                   | `ge=0`（Service 层有 500-3000 校验）        | Schema 校验与设计不一致           |
| P1-3  | Video        | AI 熔断器应包裹每个 AI 步骤调用                              | `AICircuitBreaker` 已实现但完全未接入流水线 | AI 服务连续失败时无法自动降级     |
| P1-4  | Video        | 10 步流水线应支持并行编排（Step 4/6 可并行）                 | 严格顺序执行 Step 1→10                      | 流水线耗时非最优                  |
| P1-5  | Progress     | `_calculate_trend` 停滞判定需 `len(values)>=4` + `change_rate<5%` | 变化不显著时始终返回 stagnant               | 停滞误判风险                      |
| P1-6  | Training     | `get_plan_adjustments` 调用 `_diff_snapshot` 计算 changes_summary | 返回空字符串                                | 调整历史缺失变更摘要              |
| P1-7  | Training     | `list_training_sessions` 处理字段映射 (title→name, status→is_completed) | 不处理字段转换                              | 训练单列表字段映射不完整          |
| P1-8  | Notification | WS 重连补偿推送 `sync` 事件（含 unread_count）               | 推送 `notification` 事件（逐条推送 20 条）  | 消息洪泛 + 事件类型不匹配前端预期 |
| P1-9  | Membership   | 会员到期通知应 WS + 微信订阅消息双通道                       | 仅 WS 推送                                  | 离线会员无法收到到期续费提醒      |
| P1-10 | Admin        | `AdminUser` 多出 `updated_at` 字段                           | DB 设计仅有 `created_at`                    | ORM 与 DB schema 不一致           |
| P1-11 | Admin        | `model-versions/{id}/activate` 端点设计为 Phase 2+ 占位      | 已提前实现并激活                            | Phase 边界不一致                  |
| P1-12 | Payment      | `payment_record.paid_at` 设计为必填 (NOT NULL)               | SQLAlchemy 未标记 nullable=False            | 可能产生空值                      |
| P1-13 | Notification | 通知模块缺少分区迁移脚本                                     | DB 设计要求 notification_record 按月分区    | 分区策略未实现                    |
| P1-14 | Gamification | 打卡日历使用 CST 时区 `datetime.now(timezone(timedelta(hours=8)))` | 使用 `date.today()`（服务器本地时区）       | 跨日打卡边界错误                  |

## 三、P2 一般偏差（31 项 — 后续迭代修复）

### 按模块分组：

| 模块                        | P2 数量 | 主要问题                                                     |
| --------------------------- | ------- | ------------------------------------------------------------ |
| **User**                    | 7       | Schema 命名不一致（`UpdateProfileRequest` vs `ProfileUpdateRequest` 等）；`ProfileResponse` 结构为扁平 vs 设计嵌套；`/quota` 端点设计未列出 |
| **Training**                | 4       | `model_validate` 未使用（返回手工 dict）；ORM relationships 缺失；`_diff_snapshot` 未实现；字段映射不完整 |
| **Progress**                | 4       | `training_plan_status` 返回 None；`target_progress` 硬编码 0；`list_snapshots` 缺 `status` 参数；趋势判定逻辑简化 |
| **Gamification**            | 2       | `POST /checkin` 缺 `key_func`；连续激励值硬编码              |
| **Knowledge Base**          | 3       | `get_rules_by_problem` 全表扫描替代 JSONB 查询；`model_validate` 未使用；`_evaluate_rule` 返回 bool 而非 MatchResult |
| **Scoring/Video/Dashboard** | 2       | Service 全部返回手工 dict（缺 `model_validate`）；18 项指标仅覆盖约 8 项 |
| **Admin**                   | 3       | `SystemConfig` 字段名/类型不匹配；`AuditLog` 索引名/字段不匹配；`AdminUser` 多 `updated_at` |
| **Membership**              | 2       | 时间字段用 `server_default` 而非 Python default；`payment_method` 值域不匹配 |
| **Notification**            | 1       | 训练提醒 TTL 简化为固定 7 天                                 |
| **Payment**                 | 1       | `Order` 缺 `order_no` 独立索引（由 unique 隐式覆盖）         |
| **Core**                    | 2       | `conftest.py` 使用真实 PG/Redis 而非 Mock；缺 `admin_user` fixture |

## 四、P3 建议优化（32 项 — 无需紧急修复）

主要包括：

- Schema/字段命名风格差异（功能等价）
- `server_default=func.now()` vs Python `default=lambda` （功能等价）
- Celery Task 异步生成训练建议未实现（Phase 2 功能）
- OSS/AI/LLM Mock 模式（设计预期内的 Phase 1 降级）
- 关系命名差异（`rating_history` vs `rating_histories`）
- etc.

## 五、按模块汇总统计

| 模块               | P0     | P1     | P2     | P3     | 合计    | 完成度 |
| ------------------ | ------ | ------ | ------ | ------ | ------- | ------ |
| **Auth**           | 3      | 1      | 0      | 3      | 7       | ~80%   |
| **User**           | 10     | 1      | 7      | 5      | 23      | ~44%   |
| **Core/Infra**     | 6      | 0      | 2      | 7      | 15      | ~75%   |
| **Scoring**        | 0      | 0      | 1      | 0      | 1       | ~95%   |
| **Match Data**     | 0      | 0      | 0      | 0      | 0       | ~100%  |
| **Video Analysis** | 1      | 2      | 1      | 2      | 6       | ~85%   |
| **Dashboard**      | 0      | 0      | 1      | 0      | 1       | ~90%   |
| **Training**       | 2      | 2      | 4      | 3      | 11      | ~75%   |
| **Progress**       | 4      | 1      | 4      | 1      | 10      | ~65%   |
| **Gamification**   | 1      | 1      | 2      | 4      | 8       | ~80%   |
| **Knowledge Base** | 0      | 0      | 3      | 3      | 6       | ~80%   |
| **Membership**     | 0      | 1      | 2      | 1      | 4       | ~85%   |
| **Payment**        | 0      | 1      | 1      | 1      | 3       | ~85%   |
| **Notification**   | 1      | 2      | 1      | 2      | 6       | ~70%   |
| **Admin**          | 2      | 0      | 3      | 1      | 6       | ~70%   |
| **合计**           | **30** | **14** | **31** | **32** | **107** | —      |

## 六、修复优先级路线图

### 第一优先级：P0 核心功能补齐（预计 5-7 天）

| 批次 | 任务                                                         | 预计工时 |
| ---- | ------------------------------------------------------------ | -------- |
| 1    | User 模块补齐：`ExportTask` Model + 5 个端点（big-data / account / cancel-deletion / export-data × 2）+ 5 个 Schema + 6 个 Service 方法 | 3d       |
| 2    | Auth 模块补齐：`phone-login` + `send-sms` 端点 + 3 个 Service 方法 + `config.py` SMS 配置 | 1d       |
| 3    | Training 权限守卫：6 个端点添加 `require_membership("member")` + `re_evaluate_plan` 会员校验 | 0.5d     |
| 4    | 基础设施三件套：创建 `logging.py` + `sentry.py` + `metrics.py` + config 补齐 | 1d       |
| 5    | Celery Tasks：创建 `app/tasks/` 下 10 个任务实现文件         | 1d       |
| 6    | Admin 模型修复：`AuditLog` admin_id FK + changes JSONB + `SystemConfig` value→JSONB | 0.5d     |
| 7    | Progress 补齐：`_linear_regression_forecast` + `get_comparison` 6 维度 + `get_problem_changes` 结构化 | 1d       |
| 8    | Gamification 修复：`_auto_checkin` 完整逻辑                  | 0.5d     |
| 9    | Video Analysis 修复：`confirm_upload` 时长校验               | 0.5d     |

### 第二优先级：P1 重要偏差修复（预计 3-4 天）

- AI 熔断器接入流水线
- 通知 WS 重连补偿逻辑修正
- 会员到期通知双通道
- 打卡 CST 时区统一
- 退款端点认证体系替换
- `_send_wechat_subscribe` 微信订阅消息实现
- 各模块 `model_validate` 统一使用

### 第三优先级：P2 一般偏差（预计 3-5 天）

- Schema 命名统一
- ORM relationships 补齐
- JSONB 查询优化
- conftest.py Mock 化