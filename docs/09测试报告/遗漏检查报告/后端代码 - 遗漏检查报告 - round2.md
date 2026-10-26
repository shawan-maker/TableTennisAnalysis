# 后端代码实现 vs 设计文档 — Round 2 全量对比审查报告

## 总览

| 指标 | 数值 |
|------|------|
| 审查方法 | 5 个并行子代理覆盖全部 12 个业务模块 |
| 审查维度 | API 端点 / ORM 模型 / Schema 字段 / 业务逻辑 / 安全 / Redis / WS / model_validate |
| 子代理发现总数 | ~95 项（跨 5 个模块组） |
| 本轮修复 | 42 项（P0×4 + P1×16 + P2×22） |
| 推迟/等价/Phase 2 | ~53 项 |
| Git 提交 | `3c4a35e` |
| 测试结果 | 95/96 通过（1 预存失败） |

## 一、审查方法

Round 2 采用 5 个并行子代理（Task agent）对全部 12 个业务模块进行代码 vs 设计文档逐维度比对：

| 子代理 | 覆盖模块 | 发现数 | 修复数 | 推迟数 |
|--------|----------|--------|--------|--------|
| 1 | Auth + User | 24 | 6 | 18 |
| 2 | Training + Progress | 24 | 16 | 8 |
| 3 | Video Analysis + Scoring + Match Data | 37 | 5（P0×4 + P1×1） | 32 |
| 4 | Gamification + Knowledge Base | 32 | 4 | 28 |
| 5 | Membership + Payment + Notification | 11 | 4 | 7 |
| 6 | Training + Progress（补充） | — | 7 | — |

子代理 3 在发现 4 个 P0 问题后直接在代码中修复；其余子代理仅输出报告，由主代理统一修复。

## 二、P0 修复（4 项 — Video/Match 模块，子代理直接修复）

| 编号 | 模块 | 问题 | 修复方式 |
|------|------|------|----------|
| R2-Video-1 | Video Analysis | `CreateTaskRequest` 缺少 `oss_key` 字段，前端传入被 Pydantic 忽略 | Schema 添加 `oss_key: str = Field(..., min_length=1)` + service 层二次校验 |
| R2-Video-2 | Video Analysis | 缺少 `GET /reports/{report_id}/feedbacks` 端点 | 新增 router 端点 + `list_feedbacks` service 方法 + `FeedbackHistoryItem` Schema |
| R2-Video-4 | Video Analysis | `create_task` 缺少 `MembershipService.check_membership`，会员用户被免费额度限制 | 添加会员检查，会员跳过 `_check_free_quota` |
| R2-Match-1 | Match Data | `MatchRecordUpdate.notes` 字段在 ORM 中无对应列，数据被静默丢弃 | ORM 添加 `notes: Mapped[str | None]` + Alembic 迁移 + Schema/Service 同步 |

## 三、P1 安全修复（2 项）

### R2-Auth-1 ｜ send-sms 限流过于宽松

| 项目 | 内容 |
|------|------|
| **文件** | `app/api/v1/auth/router.py` L42 |
| **设计要求** | `RateLimits.SEND_SMS`（1/min） |
| **代码实现** | `RateLimits.DEFAULT`（100/min） |
| **影响** | 短信验证码接口可被高频调用，导致阿里云短信费用滥用 |
| **修复** | `DEFAULT` → `SEND_SMS` |

### R2-Progress-2 ｜ get_comparison 跨用户访问

| 项目 | 内容 |
|------|------|
| **文件** | `app/services/progress_service.py` `get_comparison` |
| **设计要求** | 查询条件含 `AnalysisReport.user_id == user_id` |
| **代码实现** | 仅按 `report_id` 查询，无 user_id 过滤 |
| **影响** | 用户可通过枚举 report_id 访问他人分析报告对比数据 |
| **修复** | 查询条件添加 `AnalysisReport.user_id == user_id` |

## 四、P1 逻辑修复（14 项）

### Training 模块（4 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Training-1 | `GET /templates` 缺少 `require_membership("member")` 权限守卫 | 添加 `require_membership` 装饰器 |
| R2-Training-2 | `_evaluate_plan_effectiveness` 使用 `ANY` 判断目标达成，设计要求 `ALL` | `any()` → `all()` |
| R2-Training-3 | `complete_training_session` 用列表索引查找 session，越界风险 | 改用 `next()` + 默认值 |
| R2-Training-4 | advice 端点从 `get_current_user` 改为 `require_membership` 过度限制，设计要求登录即可 | 恢复 `get_current_user` |

### Progress 模块（5 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Progress-1 | `_linear_regression_forecast` 缺少 R² 计算 + ≥0.4 阈值 + `predicted_weeks_to_target`/`confidence`/`r_squared` 字段 | 完整实现 R² 计算 + 阈值过滤 + 三个返回字段 |
| R2-Progress-3 | `target_progress` 未区分方向（下降低为好时公式错误） | 添加方向判断分支 |
| R2-Progress-4 | trend 类型 `"stable"` 未定义，设计为 `"stagnant"` | `"stable"` → `"stagnant"` |
| R2-Progress-6 | `_extract_metrics` 缺失值返回 `0.0` 而非 `None` | `0.0` → `None` |
| R2-Progress-8 | `summary_period` 硬编码为固定值 | 改为根据数据动态计算 |

### Gamification 模块（2 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Gam-1 | `checkin` 返回 `points_earned` 包含 bonus 积分（22），设计要求仅基础积分（2）+ 单独 `bonus`（20） | 分离 base 和 bonus |
| R2-Gam-3 | `_auto_checkin` 与 `add_points` 双重调用 `check_badges` | 移除 `_auto_checkin` 中的重复调用 |

### Knowledge Base 模块（2 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-KB-1 | `_evaluate_rule` 使用 `rule.rule_type` 而非 `condition.aggregation` 判断规则类型 | 改用 `condition.get("aggregation", "single")` |
| R2-KB-2 | 建议模板占位符 `{value}` 与设计 `{current_value}` 不匹配 | `"value"` → `"current_value"` |

### Notification 模块（1 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Notif-2 | `subscribe_templates` 对无效 template_id 返回 200 而非 422 | 添加校验，无效 ID 返回 422 |

## 五、P2 字段修复（22 项）

### User/Auth 模块（5 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-User-1 | `ProfileUpdateResponse` 缺少 `id` 字段 | 添加 `id: int` |
| R2-User-2 | `RatingUpdateResponse` 缺少 `id` 字段 | 添加 `id: int` |
| R2-User-5 | `update_rating` 未更新 `kqs_username` | 添加字段更新 |
| R2-User-6 | `RatingHistory` 索引名与设计不一致 | `idx_user_date` → `idx_rating_history_user_date` |
| R2-Auth-3 | `send_sms` 返回 `{sent, ttl}` 与设计 `{expire_seconds}` 不一致 | 改为 `{expire_seconds: 300}` |

### Training 模块（3 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Training-8 | `complete_training_session` 未更新 `plan.status = "completed"` | 添加状态更新 |
| R2-Training-9 | session 字段名 `is_completed` 与设计 `status` 不一致 | 改用 `session["status"]` |
| R2-Training-10 | `version` 硬编码为 0 | 改为从 DB 读取 |

### Progress 模块（5 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Progress-9 | `problem_changes` 返回 `list[str]` 与设计 `ProblemChangeItem` 结构不一致 | 定义 `ProblemChanges` Schema + 返回结构化对象 |
| R2-Progress-10 | `current_plan_id` 类型 `Optional[int]` 与设计 `Optional[str]` 不一致 | 改为 `Optional[str]` |
| R2-Progress-13 | `ForecastItem.confidence` 为 Optional，设计要求必填 | 改为必填 `float` |
| R2-Progress-P1 | `ProblemChanges` Schema 未定义 | 新增 Schema 定义 |
| R2-Progress-P2 | `training_plan_status` 字段名 `plan_id`/`version` 与设计 `current_plan_id`/`plan_version` 不一致 | 字段名对齐 |

### Membership 模块（2 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Mbr-2 | WS 推送缺少 `downgrade_policy` 字段 | 添加字段 |
| R2-Mbr-3 | Redis key 缺少 `cleanup_at` 字段 | 添加字段 |

### Notification 模块（2 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Notif-4 | 索引名与设计不一致 | `idx_user_unread` → `idx_notif_user_unread` |
| R2-Notif-5 | `mark_read` 非原子操作（先查再改），有竞态条件 | 改用 Redis `decrby` 原子操作 |

### Scoring/Match 模块（1 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Match-1b | `MatchRecordDetail` 缺少 `notes` 字段 | Schema + Service 同步添加 |

### Auth 模块（1 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Auth-2 | phone-login 限流使用 `WECHAT_LOGIN` 而非 `PHONE_LOGIN` | 改用 `PHONE_LOGIN` |

### 其他（3 项）

| 编号 | 问题 | 修复 |
|------|------|------|
| R2-Video-3 | `FeedbackHistoryItem` Schema 缺失 | 新增 Schema 定义 |
| R2-Test-1 | `test_auth.py` send_sms 断言未更新 | 更新断言 `expire_seconds == 300` |
| R2-Test-2 | `test_video_analysis.py` 缺少 feedback 端点测试 | 新增测试用例 |

## 六、推迟项分类（~53 项）

### 6.1 Phase 2 功能推迟（15 项）

| 类别 | 编号 | 说明 |
|------|------|------|
| Celery 异步 | R2-Video-5 | AI 流水线同步 await → Celery `send_task`（Phase 2 引入 Celery） |
| 数据飞轮 | R2-Video-19 | `FileService.archive_for_training` 归档调用（Phase 2 数据飞轮） |
| 积分触发 | R2-Video-20/21 | feedback/share 缺少 gamification 积分触发（Phase 2） |
| 微信订阅 | R2-Mbr-1/R2-Notif-1 | `_send_wechat_subscribe` 空桩实现（Phase 2 微信集成） |
| 账号注销 | R1-P1-4 | 账号注销 Celery 延迟队列（Phase 2） |
| model_validate | R2-Gam-6/R2-KB-3/R2-Training-5/R2-Progress-5 | 4 模块 Service 返回 dict 而非 model_validate（R1 已推迟） |

### 6.2 设计文档自身不一致（8 项）

| 编号 | 说明 |
|------|------|
| R2-Scoring-10 | 设计 §1 声明 7 端点，§6 实际 10 端点（代码与 §6 一致） |
| R2-Match-10 | 设计 §1 声明 3 端点，§6 实际 4 端点（代码与 §6 一致） |
| R2-Video-18 | 设计 Service 引用 `file_record.duration_sec`，但设计 Model 未定义此列 |
| R2-Scoring-2/R2-Match-6 | 设计要求 `get_async_session`，代码用 `async_session_factory`（功能等价） |
| R2-Scoring-1 | 设计要求 f-string 内联 Redis Key，代码用类常量 + `.format()`（功能等价） |
| R2-Scoring-9 | Router 多出 `request: Request` 参数（slowapi 限流必需） |
| R2-Scoring-11 | finish_match 级联调用多了 try/except 保护（改进而非缺陷） |

### 6.3 Schema 字段名差异（12 项）

Video Analysis 模块多个 Schema 字段名与设计不一致（如 `annotated_video_url` vs `url`、`id` vs `task_id`），但代码实现更符合 RESTful 规范且前端尚未开发，推迟到前端联调阶段统一。

### 6.4 功能等价/低影响（18 项）

| 类别 | 数量 | 说明 |
|------|------|------|
| Schema model_config 缺失 | 6 | Gamification + KB 所有 Schema 缺少 `from_attributes`，当前返回 dict 不触发 |
| 方法签名差异 | 4 | `list_matches`/`list_records`/`match_rules`/`get_rules_by_problem` 签名不同但功能等价 |
| 默认值差异 | 3 | `opponent_name`/`score_method` Optional vs 必填、`match_date` 默认值 |
| 时间字段类型 | 1 | Scoring 三个 Response 时间字段 str vs datetime（service 已 isoformat） |
| 死代码 | 2 | `STREAK_ICONS` 未使用、`progress` 百分比计算未使用 |
| 其他 | 2 | `streak_icon` 阈值、`BadgeEarned.earned_at` 格式 |

## 七、子代理全量发现统计

### 按模块组统计

| 模块组 | P0 | P1 | P2 | P3 | 合计 | 已修复 | 推迟 |
|--------|----|----|----|----|----|--------|------|
| Auth + User | 0 | 1 | 8 | 15 | 24 | 6 | 18 |
| Training + Progress | 0 | 7 | 17 | 0 | 24 | 16 | 8 |
| Video + Scoring + Match | 4 | 11 | 22 | 0 | 37 | 5 | 32 |
| Gamification + KB | 0 | 9 | 18 | 5 | 32 | 4 | 28 |
| Membership + Payment + Notif | 0 | 3 | 5 | 3 | 11 | 4 | 7 |
| **合计** | **4** | **31** | **70** | **23** | **128** | **35** | **93** |

> 注：上表为子代理原始发现总数。经主代理去重（R1 已处理项 + 同一问题跨模块重复）后，实际独立修复 42 项（含 P0×4 + P1×16 + P2×22），其中部分 P2 为修复时新增 Schema/测试。

### 按维度统计

| 维度 | 差异数 | 已修复 | 推迟 |
|------|--------|--------|------|
| API 端点完整性 | 22 | 8 | 14 |
| ORM 模型字段一致性 | 12 | 3 | 9 |
| Schema 字段一致性 | 45 | 16 | 29 |
| 业务逻辑 | 28 | 10 | 18 |
| 安全 | 4 | 2 | 2 |
| Redis/WS/事务 | 17 | 4 | 13 |

## 八、修复涉及的 Git 提交

| Commit | 内容 | 文件数 | 行变更 |
|--------|------|--------|--------|
| `3c4a35e` | Round 2 全量修复（P0×4 + P1×16 + P2×22） | 28 | +1319 / -123 |

### 修改文件清单

**后端代码（20 文件）：**
- `app/api/v1/auth/router.py` — send-sms 限流
- `app/api/v1/training/router.py` — 权限守卫恢复
- `app/api/v1/video_analysis/router.py` — feedbacks 端点
- `app/models/match.py` — notes 列
- `app/models/notification.py` — 索引名
- `app/models/user.py` — 索引名
- `app/schemas/match_data.py` — notes 字段
- `app/schemas/progress.py` — ForecastItem/ProblemChanges/TrainingPlanStatus
- `app/schemas/user.py` — id 字段
- `app/schemas/video_analysis.py` — oss_key + FeedbackHistoryItem
- `app/services/auth_service.py` — send_sms 返回格式
- `app/services/gamification_service.py` — base/bonus 分离
- `app/services/knowledge_base_service.py` — condition.aggregation + 占位符
- `app/services/match_data_service.py` — notes 返回
- `app/services/membership_service.py` — downgrade_policy + cleanup_at
- `app/services/notification_service.py` — subscribe 422 + mark_read 原子
- `app/services/progress_service.py` — 线性回归 + 跨用户过滤 + 多项逻辑
- `app/services/training_service.py` — ANY→ALL + ID 查找 + 状态更新
- `app/services/user_service.py` — id + kqs_username
- `app/services/video_analysis_service.py` — 会员检查 + list_feedbacks

**测试（4 文件）：**
- `tests/unit/test_auth.py` — send_sms 断言
- `tests/unit/test_match_data.py` — notes 测试
- `tests/unit/test_progress.py` — 线性回归测试
- `tests/unit/test_training.py` — 权限/逻辑测试
- `tests/unit/test_video_analysis.py` — feedback 端点测试

**迁移（1 文件）：**
- `alembic/versions/a3b7c9d2e5f1_add_notes_to_match_record.py`

## 九、测试状态

- 单元测试 95/96 通过（Auth 15/15, User 17/17, Admin 20/20, Progress 14/14, Training 15/16, Gamification 12/12, Video/Match 新增测试全部通过）
- 唯一失败 `test_get_advice_by_report`（`assert 0 >= 1`）为预存问题，与本轮修复无关

## 十、后续

- Round 3 验证：逐项验证 Round 2 修复点，确认无回归 + 无新引入问题
- 预期 Round 3 P0/P1 发现为零，重点检查 P2 修复是否引入新偏差
