# 第十六轮 DB 字段级一致性审查报告

> **审查维度**：DB 字段级一致性
> **审查日期**：2026-10-16
> **审查代理**：第十六轮审查代理
> **基线文档**：数据库详细设计 v1.6（`docs/04详细设计/04-数据库详细设计.md`）
> **切片文件**：9 份垂直切片 backend.md / ai_pipeline.md / conftest.py.md
> **前序状态**：前十五轮累计修复 704 项；第十五轮遗留 9 项 DB P3 + 3 项 API P3 待验证

---

## 1. 审查范围

### 1.1 基线文件清单

| # | 文件路径 | 关键章节 |
|---|---------|---------|
| 1 | `docs/04详细设计/04-数据库详细设计.md` | §1 ER 图、§2 表定义、§4 枚举、§5 SQLAlchemy 模型、§6 索引总表 |
| 2 | `docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` | Model（FileRecord/VideoTask/PipelineStep/AnalysisReport/FeedbackRecord/ShareRecord）+ Service（create_share） |
| 3 | `docs/06垂直模块前后端切片设计/09-gamification/backend.md` | Model（UserPoints/CheckInRecord/BadgeDefinition/UserBadge/BadgeProgress）+ Service（checkin/_update_streak/grant_badge_points） |
| 4 | `docs/06垂直模块前后端切片设计/10-membership/backend.md` | Model（MembershipTier/Subscription）+ Service（consume_analysis_quota/check_expiry） |
| 5 | `docs/06垂直模块前后端切片设计/04-scoring/backend.md` | Model（Match/ScoreRecord/MatchStatistic）+ Service（cleanup_abandoned_matches） |
| 6 | `docs/06垂直模块前后端切片设计/02-user/backend.md` | Model（User/RatingHistory/ExportTask）+ Service（cleanup_old_export_tasks/export_user_data） |
| 7 | `docs/06垂直模块前后端切片设计/13-infrastructure/ai_pipeline.md` | step def + Redis Key CST |
| 8 | `docs/06垂直模块前后端切片设计/13-infrastructure/conftest.py.md` | MockRedis 完整性 |
| 9 | `docs/06垂直模块前后端切片设计/11-payment/backend.md` | Model（Order/PaymentRecord/RefundRecord） |

### 1.2 审查清单（18 项）

| # | 类别 | 检查项 |
|---|------|--------|
| 1 | 修复验证 | PipelineStep 模型在 video_analysis 切片中定义 |
| 2 | 修复验证 | PipelineStep 模型在 DB 设计 §5.2 中定义 |
| 3 | 修复验证 | consume_analysis_quota docstring 说明调用方 |
| 4 | 修复验证 | create_share 使用 share.share_token |
| 5 | 修复验证 | gamification 3 处 date.today→CST |
| 6 | 修复验证 | DB §5 DDL FileRecord/ScoreRecord/Order/FeedbackRecord 索引/约束 |
| 7 | 修复验证 | DB §2.17 Subscription.status 补 cancelled |
| 8 | 修复验证 | DB §2.1 User.status 补 pending_deletion |
| 9 | 深层检查 | 索引命名一致性（DB §6 索引总表 vs 切片 __table_args__） |
| 10 | 深层检查 | 枚举字段 comment 列出所有合法值 |
| 11 | 深层检查 | Badge FK ondelete 策略 |
| 12 | 深层检查 | audit_log FK ondelete 策略 |
| 13 | 深层检查 | ER 图与切片 relationship 一致性 |
| 14 | 深层检查 | JSONB 字段默认值 |
| 15 | 深层检查 | 金额字段 _cents 后缀 |
| 16 | 深层检查 | updated_at onupdate 默认值 |
| 17 | 深层检查 | PipelineStep 模型字段与 DB §2.6 对齐 |
| 18 | 深层检查 | VideoTask.relationship pipeline_steps |

---

## 2. 第十五轮修复验证（第 1-8 项）

### 2.1 PipelineStep 模型在 video_analysis 切片中定义 ✅

- **文件**：`docs/06垂直模块前后端切片设计/03-video_analysis/backend.md`
- **行号**：L271-290
- **验证结果**：PipelineStep 模型已完整定义，包含 id/task_id/step_number/step_name/status/duration_ms/step_result/error_message/started_at/completed_at 全部 10 个字段，且有 `__table_args__` 含 `idx_pipeline_step_task_step` 索引和 `task` relationship
- **结论**：✅ 无回归

### 2.2 PipelineStep 模型在 DB 设计 §5.2 中定义 ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md`
- **行号**：L2325-2344
- **验证结果**：§5.2 PipelineStep 模型代码完整，字段与切片一致，含 `idx_pipeline_step_task_step` 索引和 `task: Mapped["VideoTask"] = relationship(back_populates="pipeline_steps")` 双向关联
- **结论**：✅ 无回归

### 2.3 consume_analysis_quota docstring 说明调用方 ✅

- **文件**：`docs/06垂直模块前后端切片设计/10-membership/backend.md`
- **行号**：L530-537
- **验证结果**：docstring 清晰说明 "由 video_analysis 模块 POST /video-analysis/tasks 时调用"
- **结论**：✅ 无回归

### 2.4 create_share 使用 share.share_token ✅

- **文件**：`docs/06垂直模块前后端切片设计/03-video_analysis/backend.md`
- **行号**：L1066
- **验证结果**：`share_url = f"https://api.pingpongai.com/share/{share.share_token}"` — 使用模型属性 `share.share_token` 而非局部变量
- **结论**：✅ 无回归

### 2.5 gamification 3 处 date.today→CST ✅

- **文件**：`docs/06垂直模块前后端切片设计/09-gamification/backend.md`
- **行号**：L506、L624、L682
- **验证结果**：
  - L506（checkin 方法）：`today = datetime.now(timezone(timedelta(hours=8))).date()` ✅
  - L624（_update_streak 方法）：`today = datetime.now(timezone(timedelta(hours=8))).date()` ✅
  - L682（_auto_checkin 方法）：`today = datetime.now(timezone(timedelta(hours=8))).date()` ✅
- **结论**：✅ 无回归。测试代码中仍使用 `date.today()`（L93/L139/L153），属测试辅助场景，可接受

### 2.6 DB §5 DDL 索引/约束补充 ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md`
- **验证结果**：
  - FileRecord（§5.2 L2289-2292）：`idx_file_record_user_created` + `idx_file_record_type` ✅
  - ScoreRecord（§5.3 L2447-2449）：`idx_score_record_match_seq` + `idx_score_record_match_game` ✅
  - Order（§5.5 L2574-2576）：`idx_order_user_created` + `idx_order_status` ✅
  - FeedbackRecord（§5.6 L2663）：`uq_feedback_user_report` UniqueConstraint ✅
- **结论**：✅ 无回归

### 2.7 DB §2.17 Subscription.status 补 cancelled ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md`
- **行号**：L717
- **验证结果**：`status | VARCHAR(20) | Y | DEFAULT 'active' | 状态 | active/expiring_soon/expired/grace_period/cancelled/closed` — 包含 `cancelled` ✅
- **结论**：✅ 无回归

### 2.8 DB §2.1 User.status 补 pending_deletion ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md`
- **行号**：L435
- **验证结果**：`status | VARCHAR(20) | Y | DEFAULT 'active' | 用户状态 | active/pending_deletion/deleted` — 包含 `pending_deletion` ✅
- **结论**：✅ 无回归

---

## 3. 深层检查（第 9-18 项）

### 3.1 索引命名一致性（第 9 项）

#### 发现 P3-4：VideoTask 索引名称三方不一致

- **涉及文件**：
  - DB `04-数据库详细设计.md` §5.2 L2320-2321、§6 L2691-2692
  - 切片 `03-video_analysis/backend.md` L262-263
- **问题描述**：

| 索引用途 | DB §5.2 模型代码 | DB §6 索引总表 | 切片 __table_args__ |
|---------|-----------------|--------------|-------------------|
| (user_id, created_at) | `idx_video_task_user_created` | `idx_vtask_user_created` | `idx_video_task_user_created` |
| (status, created_at) | `idx_video_task_status` | `idx_vtask_status` | `idx_video_task_status_created` |

- **影响**：§5.2 与 §6 索引名称不一致（DB 设计内部），切片与 §5.2 在第二个索引名称上不一致
- **建议**：统一为 `idx_video_task_user_created` 和 `idx_video_task_status_created`，同步更新 §5.2 和 §6

#### 发现 P3-5：Subscription 索引名称切片与 DB 不一致

- **涉及文件**：
  - 切片 `10-membership/backend.md` L242
  - DB `04-数据库详细设计.md` §5.5 L2550、§6 L2703
- **问题描述**：切片使用 `idx_subscription_user_status`，DB §5.5 和 §6 均使用 `idx_sub_user_status`
- **建议**：切片统一为 `idx_sub_user_status`，与 DB 设计一致

#### 发现 P3-6：FileRecord 索引三方不一致

- **涉及文件**：
  - DB `04-数据库详细设计.md` §5.2 L2289-2292、§6 L2707-2709
  - 切片 `03-video_analysis/backend.md` L232-235
- **问题描述**：

| 索引 | DB §5.2 | DB §6 | 切片 |
|------|---------|-------|------|
| (user_id, created_at) | `idx_file_record_user_created` ✅ | `idx_file_record_user_created` ✅ | `idx_file_record_user_created` ✅ |
| (file_type) | `idx_file_record_type` ✅ | `idx_file_record_type` ✅ | ❌ 缺失 |
| (status, created_at) | ❌ 缺失 | `idx_file_status_created` | `idx_file_record_status_created`（名称不同）|

- **影响**：切片缺少 `idx_file_record_type` 索引；`idx_file_status_created`（§6）vs `idx_file_record_status_created`（切片）名称不一致
- **建议**：切片补充 `idx_file_record_type` 索引，统一状态索引命名为 `idx_file_status_created`（与 §6 一致）

### 3.2 枚举字段 comment 完整性（第 10 项）

#### 发现 P3-1：UserStatus 枚举缺少 pending_deletion

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §4.1 L2022-2025
- **问题描述**：`UserStatus` 枚举仅定义 `active` 和 `deleted`，缺少 `pending_deletion`。§2.1 user 表定义（L435）注释列出 `active/pending_deletion/deleted`，切片 `02-user/backend.md`（L1998）也包含 `pending_deletion`
- **建议**：在 §4.1 `UserStatus` 中补充 `pending_deletion = "pending_deletion"  # 注销待删除`

#### 发现 P3-2：SubscriptionStatus 枚举缺少 cancelled

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §4.1 L2109-2115
- **问题描述**：`SubscriptionStatus` 枚举仅定义 `active/expiring_soon/expired/grace_period/closed`，缺少 `cancelled`。§2.17 subscription 表定义（L717）和切片 `10-membership/backend.md`（L229）均包含 `cancelled`
- **建议**：在 §4.1 `SubscriptionStatus` 中补充 `cancelled = "cancelled"  # 已取消`

#### 发现 P3-3：DB §5.5 Subscription 模型 status 注释缺少 cancelled

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.5 L2539
- **问题描述**：§5.5 Subscription 模型 `status` 字段注释为 `# active/expiring_soon/expired/grace_period/closed`，缺少 `cancelled`，与 §2.17 表定义（L717）和切片（L229）不一致
- **建议**：更新 §5.5 注释为 `# active/expiring_soon/expired/grace_period/cancelled/closed`

### 3.3 Badge FK ondelete 策略（第 11 项）

#### 发现 P3-7：badge 表 FK 未指定 ondelete 策略

- **涉及文件**：`docs/04详细设计/04-数据库详细设计.md` §3.1.5 L1194、§3.1.6 L1215
- **切片对比**：`docs/06垂直模块前后端切片设计/09-gamification/backend.md` L244、L258

| 表 | DB §3.1 表定义 | 切片模型 |
|----|--------------|---------|
| user_badge.badge_id | `FK → badge_definition(id), NOT NULL`（无策略）| `ForeignKey("badge_definition.id", ondelete="RESTRICT")` ✅ |
| badge_progress.badge_id | `FK → badge_definition(id), NOT NULL`（无策略）| `ForeignKey("badge_definition.id", ondelete="RESTRICT")` ✅ |

- **影响**：DB 表定义未明确 ondelete 策略，可能导致 Alembic 自动生成迁移时遗漏
- **建议**：在 §3.1.5 和 §3.1.6 表定义中补充 `FK → badge_definition(id), RESTRICT`

### 3.4 audit_log FK ondelete 策略（第 12 项）

#### 发现 P3-8：audit_log 表 FK 未指定 ondelete 策略

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §2.31 L993、L998

| 字段 | DB §2.31 表定义 | 建议策略 |
|------|--------------|---------|
| admin_id | `FK→admin_user.id`（无策略）| `FK→admin_user.id, RESTRICT` |
| user_id | `FK→user.id`（无策略）| `FK→user.id, SET NULL` |

- **理由**：审计日志为合规资产，管理员删除时不应级联删除审计记录（RESTRICT）；用户注销后审计日志应保留但 user_id 置空（SET NULL，因 user_id 已 nullable）
- **建议**：在 §2.31 表定义中补充上述 ondelete 策略

### 3.5 ER 图与切片 relationship 一致性（第 13 项）

**验证结果**：✅ 一致

- ER 图 §1.1（L15-296）展示 Phase 1 全部实体关系
- `VIDEO_TASK ||--o{ PIPELINE_STEP`：切片 L268 `pipeline_steps` relationship ✅
- `ANALYSIS_REPORT ||--o{ FEEDBACK_RECORD`：切片 L334 `report` relationship ✅
- `ANALYSIS_REPORT ||--o{ SHARE_RECORD`：切片 L351 `report` relationship ✅
- `FILE_RECORD ||--|| VIDEO_TASK`：切片 L237/L266 双向 `back_populates` ✅

#### 发现 P3-12：ER 图 VideoTask 实体未列出 v1.4 新增字段

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §1.1 L88-98
- **问题描述**：ER 图中 VideoTask 仅列出 9 个字段（id/user_id/file_id/oss_key/duration_sec/status/current_step/created_at/completed_at），缺少 task_uuid/total_steps/step_name/progress/estimated_remaining_seconds/error_message/retry_count 共 7 个 v1.4 新增字段
- **建议**：更新 ER 图 VideoTask 实体，补充缺失字段

#### 发现 P3-13：ER 图 AnalysisReport 实体未列出部分字段

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §1.1 L110-119
- **问题描述**：ER 图中 AnalysisReport 缺少 is_llm_generated/is_anonymized/report_images 字段，§2.7 表定义（L552-554）和 §5.2 模型（L2358-2357）均已定义
- **建议**：更新 ER 图 AnalysisReport 实体，补充缺失字段

### 3.6 JSONB 字段默认值（第 14 项）

#### 发现 P3-14：AnalysisReport 模型 JSONB 字段未设默认值

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.2 L2353-2354
- **问题描述**：`result_data: Mapped[dict] = mapped_column(JSONB)` 和 `report_text: Mapped[dict] = mapped_column(JSONB)` 均未设置 `default` 参数
- **影响**：创建 AnalysisReport 时若未显式传值，字段为 NULL，但类型标注为 `Mapped[dict]`（非 Optional），ORM 层和 DB 层语义不一致
- **建议**：添加 `default=dict` 或改为 `Mapped[dict | None]` + `nullable=True`

### 3.7 金额字段 _cents 后缀（第 15 项）

**验证结果**：✅ 一致

| 字段 | DB §2 表定义 | DB §5 模型 | 切片模型 |
|------|-----------|-----------|---------|
| Order.amount_cents | §2.18 L738 ✅ | §5.5 L2565 ✅ | payment L460 ✅ |
| PaymentRecord.amount_cents | §2.19 L754 ✅ | §5.5 L2587 ✅ | payment L493 ✅ |
| RefundRecord.refund_amount_cents | §2.19b L767 ✅ | §5 无模型 | payment L513 ✅ |
| MembershipTier.price_monthly_cents | §2.31 L1022 ✅ | — | membership L209 ✅ |

### 3.8 updated_at onupdate 默认值（第 16 项）

#### 发现 P3-9：DB §5.2 FileRecord 模型缺少 updated_at 字段

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.2 L2273-2292
- **问题描述**：§2.4 file_record 表定义（L494）有 `updated_at` 字段（P2 补充），切片 `03-video_analysis/backend.md`（L229）也有 `updated_at` + `onupdate=lambda: datetime.now(timezone.utc)`，但 §5.2 FileRecord 模型代码未包含该字段
- **影响**：§5 模型代码与 §2 表定义不同步
- **建议**：在 §5.2 FileRecord 模型中补充 `updated_at` 字段

**其余模型验证结果**：✅ 均包含 `updated_at` + `onupdate`
- User（§5.1 L2251）✅ | Match（§5.3 L2418）✅ | MatchRecord（§5.4 L2492）✅ | Subscription（§5.5 L2544）✅ | TechniqueTrend（§5.6 L2640）✅ | FeedbackRecord（§5.6 L2658）✅

### 3.9 PipelineStep 模型字段与 DB §2.6 对齐（第 17 项）

**验证结果**：✅ 完全一致

| 字段 | DB §2.6 表定义（L526-537） | DB §5.2 模型（L2325-2342） | 切片模型（L271-288） |
|------|--------------------------|--------------------------|-------------------|
| id | BIGSERIAL, PK | BigInteger, PK ✅ | BigInteger, PK ✅ |
| task_id | BIGINT, FK→video_task.id, CASCADE | BigInteger, FK CASCADE ✅ | BigInteger, FK CASCADE ✅ |
| step_number | INT | Integer, nullable=False ✅ | Integer, nullable=False ✅ |
| step_name | VARCHAR(64) | String(64), nullable=False ✅ | String(64), nullable=False ✅ |
| status | VARCHAR(20), DEFAULT 'pending' | String(20), default="pending" ✅ | String(20), default="pending" ✅ |
| duration_ms | INT, NULL | Integer, nullable=True ✅ | Integer, nullable=True ✅ |
| step_result | JSONB, NULL | JSONB, nullable=True ✅ | JSONB, nullable=True ✅ |
| error_message | TEXT, NULL | Text, nullable=True ✅ | Text, nullable=True ✅ |
| started_at | TIMESTAMPTZ, NULL | DateTime(timezone=True), nullable=True ✅ | DateTime(timezone=True), nullable=True ✅ |
| completed_at | TIMESTAMPTZ, NULL | DateTime(timezone=True), nullable=True ✅ | DateTime(timezone=True), nullable=True ✅ |

### 3.10 VideoTask.relationship pipeline_steps（第 18 项）

**验证结果**：✅ 一致

- DB §5.2（L2317）：`pipeline_steps: Mapped[list["PipelineStep"]] = relationship(back_populates="task", cascade="all, delete-orphan")` ✅
- 切片（L268）：`pipeline_steps: Mapped[list["PipelineStep"]] = relationship(back_populates="task", cascade="all, delete-orphan")` ✅
- ER 图 §1.1（L38）：`VIDEO_TASK ||--o{ PIPELINE_STEP : "流水线步骤"` ✅

---

## 4. P2 级发现

### P2-1：DB §5.5 PaymentRecord 模型缺少 paid_at 字段

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.5 L2579-2595
- **问题描述**：§5.5 PaymentRecord SQLAlchemy 模型代码未包含 `paid_at` 字段
  - §2.19 表定义（L755）：`paid_at | TIMESTAMPTZ | Y | — | 支付时间`
  - 切片 `11-payment/backend.md`（L495）：`paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))`
  - §5.5 模型代码仅有 created_at，缺少 paid_at
- **影响**：§5 模型代码示例不完整，开发者参照 §5 实现时可能遗漏该必填字段
- **建议**：在 §5.5 PaymentRecord 模型中补充 `paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))`

### P2-2：DB §5.5 Subscription 模型缺少 payment_method 和 cancelled_at 字段

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.5 L2532-2551
- **问题描述**：§5.5 Subscription 模型缺少两个字段：

| 字段 | §2.17 表定义 | 切片模型 | §5.5 模型 |
|------|-----------|---------|---------|
| payment_method | L718 ✅ | L234 ✅ | ❌ 缺失 |
| cancelled_at | L722 ✅ | L235 ✅ | ❌ 缺失 |

- **影响**：§5 模型代码与 §2 表定义严重不同步，可能误导开发者
- **建议**：在 §5.5 Subscription 模型中补充：
  ```python
  payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
  cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="取消时间（退款撤销时设置）")
  ```

---

## 5. P3 级发现汇总

| # | 发现编号 | 文件 | 行号 | 简述 | 建议优先级 |
|---|---------|------|------|------|-----------|
| 1 | P3-1 | `04-数据库详细设计.md` §4.1 | L2022-2025 | UserStatus 枚举缺 pending_deletion | 低 |
| 2 | P3-2 | `04-数据库详细设计.md` §4.1 | L2109-2115 | SubscriptionStatus 枚举缺 cancelled | 低 |
| 3 | P3-3 | `04-数据库详细设计.md` §5.5 | L2539 | Subscription 模型 status 注释缺 cancelled | 低 |
| 4 | P3-4 | `04-数据库详细设计.md` §5.2+§6 / 切片 `03-video_analysis` | L2320-2321 / L2691-2692 / L262-263 | VideoTask 索引名称三方不一致 | 中 |
| 5 | P3-5 | 切片 `10-membership` / DB §5.5+§6 | L242 / L2550 / L2703 | Subscription 索引名称切片与 DB 不一致 | 中 |
| 6 | P3-6 | DB §5.2+§6 / 切片 `03-video_analysis` | L2289-2292 / L2707-2709 / L232-235 | FileRecord 索引三方不一致 | 中 |
| 7 | P3-7 | `04-数据库详细设计.md` §3.1.5+3.1.6 | L1194 / L1215 | badge 表 FK 未指定 ondelete 策略 | 中 |
| 8 | P3-8 | `04-数据库详细设计.md` §2.31 | L993 / L998 | audit_log 表 FK 未指定 ondelete 策略 | 中 |
| 9 | P3-9 | `04-数据库详细设计.md` §5.2 | L2273-2292 | FileRecord 模型缺 updated_at 字段 | 低 |
| 10 | P3-10 | `04-数据库详细设计.md` §5 各模型 | — | §5 多个模型缺 §6 索引总表列出的索引 | 中 |
| 11 | P3-11 | `04-数据库详细设计.md` §5 | — | §5 缺 RefundRecord 模型代码示例 | 低 |
| 12 | P3-12 | `04-数据库详细设计.md` §1.1 | L88-98 | ER 图 VideoTask 实体缺 v1.4 新增字段 | 低 |
| 13 | P3-13 | `04-数据库详细设计.md` §1.1 | L110-119 | ER 图 AnalysisReport 实体缺部分字段 | 低 |
| 14 | P3-14 | `04-数据库详细设计.md` §5.2 | L2353-2354 | AnalysisReport JSONB 字段未设默认值 | 低 |
| 15 | P3-15 | DB §5.6 / 切片 `03-video_analysis` | L2663 / L331 | FeedbackRecord UniqueConstraint 列顺序不一致 | 低 |

### P3-10 详细说明：§5 多个模型缺少 §6 索引总表中列出的索引

| 模型 | §5 位置 | 缺少的索引 | §6 行号 |
|------|---------|----------|---------|
| AnalysisReport | §5.2 | `idx_report_user_created` + GIN 索引 | L2693-2694 |
| MatchStatistic | §5.3 | `idx_mstat_match` | L2710 |
| ShareRecord | §5.2 | `idx_share_user_created` | L2713 |
| FeedbackRecord | §5.6 | `idx_feedback_status` + `idx_feedback_correct_created` | L2720-2721 |
| ProgressSnapshot | §5.6 | `idx_ps_metrics_gin` | L2700 |
| UserPoints | §5（无独立章节）| `idx_points_user_updated` | L2712 |

- **建议**：在各模型 `__table_args__` 中补充 §6 列出的对应索引，确保 §5 模型代码与 §6 索引总表一致

### P3-15 详细说明：FeedbackRecord UniqueConstraint 列顺序不一致

- DB §5.6（L2663）：`UniqueConstraint("user_id", "report_id", name="uq_feedback_user_report")`
- 切片 `03-video_analysis/backend.md`（L331）：`UniqueConstraint("report_id", "user_id", name="uq_feedback_user_report")`
- **影响**：功能等价（UNIQUE 约束不区分列顺序），但索引扫描前缀不同，建议以查询模式为准统一

---

## 6. 已修复项清单

| # | 原修复轮次 | 检查项 | 本轮验证 |
|---|----------|--------|---------|
| 1 | 第十五轮 | PipelineStep 模型在切片中定义 | ✅ 无回归 |
| 2 | 第十五轮 | PipelineStep 模型在 DB §5.2 中定义 | ✅ 无回归 |
| 3 | 第十五轮 | consume_analysis_quota docstring | ✅ 无回归 |
| 4 | 第十五轮 | create_share 使用 share.share_token | ✅ 无回归 |
| 5 | 第十五轮 | gamification 3 处 date.today→CST | ✅ 无回归 |
| 6 | 第十五轮 | DB §5 DDL 索引/约束补充 | ✅ 无回归 |
| 7 | 第十五轮 | DB §2.17 Subscription.status 补 cancelled | ✅ 无回归 |
| 8 | 第十五轮 | DB §2.1 User.status 补 pending_deletion | ✅ 无回归 |

---

## 7. 本轮统计

| 级别 | 新发现 | 已修复验证 | 遗留 |
|------|--------|-----------|------|
| P0 | 0 | — | 0 |
| P1 | 0 | — | 0 |
| P2 | 2 | — | 2 |
| P3 | 15 | — | 15 |
| **合计** | **17** | **8** | **17** |

### 按修复方向分类

| 修复方向 | 数量 | 优先建议 |
|---------|------|---------|
| DB §5 模型代码与 §2 表定义同步 | 4（P2-1, P2-2, P3-9, P3-14） | 最高——§5 是开发者直接参照的代码示例 |
| 枚举定义与表定义同步 | 3（P3-1, P3-2, P3-3） | 高——枚举不一致可能导致校验遗漏 |
| 索引名称统一 | 3（P3-4, P3-5, P3-6） | 中——影响 Alembic 迁移生成 |
| FK ondelete 策略补充 | 2（P3-7, P3-8） | 中——影响数据完整性保护 |
| §5 模型补充 §6 索引 | 1（P3-10，含 6 个模型） | 中——影响查询性能 |
| ER 图更新 | 2（P3-12, P3-13） | 低——文档准确性 |
| 其他 | 2（P3-11, P3-15） | 低 |

---

## 8. 修复建议优先级排序

### 第一优先级（P2，应尽快修复）

1. **P2-1**：§5.5 PaymentRecord 模型补充 `paid_at` 字段
2. **P2-2**：§5.5 Subscription 模型补充 `payment_method` 和 `cancelled_at` 字段

### 第二优先级（P3-高，建议下一轮修复）

3. **P3-1**：§4.1 UserStatus 枚举补充 `pending_deletion`
4. **P3-2**：§4.1 SubscriptionStatus 枚举补充 `cancelled`
5. **P3-3**：§5.5 Subscription 模型 status 注释补充 `cancelled`
6. **P3-9**：§5.2 FileRecord 模型补充 `updated_at` 字段
7. **P3-14**：§5.2 AnalysisReport 模型 JSONB 字段补充默认值

### 第三优先级（P3-中，建议批量修复）

8. **P3-4**：统一 VideoTask 索引名称
9. **P3-5**：统一 Subscription 索引名称
10. **P3-6**：统一 FileRecord 索引名称和补全
11. **P3-7**：补充 badge 表 FK ondelete RESTRICT 策略
12. **P3-8**：补充 audit_log 表 FK ondelete 策略
13. **P3-10**：§5 各模型补充 §6 索引总表中的索引

### 第四优先级（P3-低，择机修复）

14. **P3-11**：§5 补充 RefundRecord 模型代码示例
15. **P3-12**：更新 ER 图 VideoTask 实体
16. **P3-13**：更新 ER 图 AnalysisReport 实体
17. **P3-15**：统一 FeedbackRecord UniqueConstraint 列顺序

---

> **审查结论**：第十五轮 8 项 DB 修复全部通过验证，无回归。本轮新发现 2 项 P2 + 15 项 P3，主要集中在 DB §5 SQLAlchemy 模型代码与 §2 表定义/§6 索引总表不同步问题。建议优先修复 P2 级模型字段缺失，其次同步枚举定义和索引名称。
