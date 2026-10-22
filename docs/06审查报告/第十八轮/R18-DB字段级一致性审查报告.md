# R18-DB 字段级一致性审查报告

> **审查轮次**：第十八轮（R18）  
> **审查维度**：DB 字段级一致性  
> **审查日期**：2026-10-16  
> **DB 设计版本**：v1.6  
> **审查代理**：R18 审查代理

---

## 1. 审查范围

### 1.1 DB 设计文件

| 文件 | 说明 |
|------|------|
| `docs/04详细设计/04-数据库详细设计.md` | DB 设计 v1.6（§2 DDL + §3 ER + §5 SQLAlchemy Models + §6 索引总表），共 2587+ 行 |

### 1.2 后端切片文件（12 个）

| 切片 | 文件路径 | 模型 |
|------|---------|------|
| 01-auth | `06.../01-auth/backend.md` | User, ConsentLog |
| 02-user | `06.../02-user/backend.md` | User, RatingHistory, ExportTask |
| 03-video_analysis | `06.../03-video_analysis/backend.md` | FileRecord, VideoTask, PipelineStep, AnalysisReport, FeedbackRecord, ShareRecord |
| 04-scoring | `06.../04-scoring/backend.md` | Match, ScoreRecord, MatchStatistic |
| 05-match_data | `06.../05-match_data/backend.md` | MatchRecord, ManualScoreDetail |
| 06-data_dashboard | `06.../06-data_dashboard/backend.md` | （注释引用，无独立模型） |
| 07-training_advice | `06.../07-training_advice/backend.md` | TrainingPlan, PlanAdjustment |
| 08-progress_analysis | `06.../08-progress_analysis/backend.md` | ProgressSnapshot, TechniqueTrend |
| 09-gamification | `06.../09-gamification/backend.md` | UserPoints, CheckInRecord, BadgeDefinition, UserBadge, BadgeProgress |
| 10-membership | `06.../10-membership/backend.md` | MembershipTier, Subscription |
| 11-payment | `06.../11-payment/backend.md` | Order, PaymentRecord, RefundRecord |
| 12-notification | `06.../12-notification/backend.md` | NotificationRecord |

### 1.3 基础设施文件

| 文件 | 说明 |
|------|------|
| `13-infrastructure/admin.md` | AdminUser, AuditLog, SystemConfig 模型 |
| `13-infrastructure/knowledge_base.md` | KnowledgeCategory, KnowledgeEntry, RuleDefinition, TrainingTemplate 模型 |
| `13-infrastructure/ai_pipeline.md` | 复用 video_analysis 模块模型，无独立定义 |
| `13-infrastructure/file_management.md` | 无模型定义 |
| `13-infrastructure/ai_inference.md` | 无模型定义 |

### 1.4 审查方法

- 使用 `grep` 搜索 `class.*Base`、`__tablename__`、`__table_args__`、`Column`、`ForeignKey`、`Index(` 等模式
- 交叉比对 DB §2 DDL 表定义、§5 SQLAlchemy 模型、§6 索引总表与切片模型
- `[REDACTED]` 显示伪影：`primary_key` 行显示为 `[REDACTED]]]]`，实际为 `True`，通过 grep 模式匹配绕过

---

## 2. R17 修复验证表（7 项）

| # | 验证项 | 状态 | 备注 |
|---|--------|------|------|
| 1 | **11 个缺失模型**：§5 是否已补充 FileRecord, AnalysisReport, PipelineStep, MatchRecord, BadgeDefinition, UserBadge, UserPoints, CheckinRecord, ShareRecord, FeedbackRecord, ExportTask, ConsentLog | ✅ | §5 现包含全部 29 个模型。FileRecord L2365, AnalysisReport L2440, PipelineStep L2419, MatchRecord L2583, BadgeDefinition L2835, UserBadge L2856, UserPoints L2274, CheckinRecord L2293, ShareRecord L2466, FeedbackRecord L2781, ExportTask L2332, ConsentLog L2312 — 全部存在 |
| 2 | **6 个 `__table_args__`**：FileRecord, AnalysisReport, MatchRecord, BadgeDefinition, UserPoints, CheckinRecord | ✅ | FileRecord §5 L2382, AnalysisReport §5 L2460, MatchRecord §5 L2604, BadgeDefinition §5 L2849, UserPoints §5 L2287, CheckinRecord §5 L2305 — 全部有 `__table_args__` |
| 3 | **badge FK ondelete RESTRICT**：§3.1.5/3.1.6 中 badge 表 FK | ✅ | §3.1.5 L1206 `RESTRICT`，§3.1.6 L1227 `RESTRICT`；§5 UserBadge L2862 `ondelete="RESTRICT"`，BadgeProgress L2878 `ondelete="RESTRICT"`；切片 09-gamification L245/L259 同步 `ondelete="RESTRICT"` |
| 4 | **PaymentRecord paid_at nullable=False**：§5.5 中 paid_at | ✅ | §5 L2698 `paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))` — 无 nullable=True（即 nullable=False），注释标注 `R17-P2: 移除 nullable=True`；切片 11-payment L495 同步 |
| 5 | **audit_log admin_id FK RESTRICT**：§2.31 中 admin_id FK | ✅ | §2.31 L1005 `FK→admin_user.id, RESTRICT`（注释 R17-P2: SET NULL→RESTRICT）；§5 L2923 `ondelete="RESTRICT"`；切片 admin.md L88 `ondelete="RESTRICT", nullable=False` |
| 6 | **切片索引命名**：FileRecord `idx_file_status_created`、MatchRecord `idx_mrecord_user_date`、AnalysisReport `idx_report_user_created` | ✅ | 切片 03 L234 `idx_file_status_created`，切片 05 L426 `idx_mrecord_user_date`，切片 03 L310 `idx_report_user_created` — 全部正确 |
| 7 | **BadgeDefinition 索引 `idx_badge_definition_active`**：切片中是否补充 | ✅ | 切片 09-gamification L235 `Index("idx_badge_definition_active", "is_active")`；§5 L2851 同步；§3.1.4 L1192 定义 |

**R17 修复验证结论**：7/7 项全部通过 ✅

---

## 3. 新发现

### P0 — 严重（阻断级）

无 P0 级问题。

---

### P1 — 高优先级

#### P1-1：§5 MatchStatistic 缺少 `created_at` 字段

| 属性 | 值 |
|------|-----|
| 表名 | match_statistic |
| 文件 | `docs/04详细设计/04-数据库详细设计.md` |
| 行号 | §5 L2556-2568 |
| 问题描述 | §5 MatchStatistic 模型只有 `id`、`match_id`、`stats_data` 三个字段，缺少 `created_at` 字段。DB §2.12 L658 明确定义 `created_at TIMESTAMPTZ Y DEFAULT NOW()`。切片 04-scoring L393 已正确定义 `created_at`。 |
| 修复建议 | 在 §5 MatchStatistic 模型中补充 `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))` |

#### P1-2：切片 03-video_analysis ShareRecord 缺少 `__table_args__`

| 属性 | 值 |
|------|-----|
| 表名 | share_record |
| 文件 | `docs/06.../03-video_analysis/backend.md` |
| 行号 | L338-353 |
| 问题描述 | 切片 ShareRecord 模型没有 `__table_args__`，缺少 `idx_share_user_created` 索引。DB §5 L2482-2484 定义了 `__table_args__ = (Index("idx_share_user_created", "user_id", text("created_at DESC")),)`。§6 L2980 也列出此索引。 |
| 修复建议 | 在切片 ShareRecord 中添加 `__table_args__ = (Index("idx_share_user_created", "user_id", "created_at"),)` |

#### P1-3：切片 03-video_analysis FeedbackRecord 缺少审核队列索引

| 属性 | 值 |
|------|-----|
| 表名 | feedback_record |
| 文件 | `docs/06.../03-video_analysis/backend.md` |
| 行号 | L331-333 |
| 问题描述 | 切片 FeedbackRecord 的 `__table_args__` 只有 `UniqueConstraint("report_id", "user_id", name="uq_feedback_user_report")`，缺少 `idx_feedback_status` 和 `idx_feedback_correct_created` 索引。DB §5 L2797-2799 和 §6 L2989-2990 均定义了这两个索引（数据飞轮审核队列查询和飞轮数据统计用途）。 |
| 修复建议 | 在切片 `__table_args__` 中补充：`Index("idx_feedback_status", "status"), Index("idx_feedback_correct_created", "is_correct", "created_at")` |

#### P1-4：切片 09-gamification UserPoints 缺少 `__table_args__`

| 属性 | 值 |
|------|-----|
| 表名 | user_points |
| 文件 | `docs/06.../09-gamification/backend.md` |
| 行号 | L179-193 |
| 问题描述 | 切片 UserPoints 模型没有 `__table_args__`，缺少 `idx_points_user_updated` 索引。DB §5 L2287-2289 定义了 `__table_args__ = (Index("idx_points_user_updated", "user_id", "updated_at"),)`。§6 L2979 也列出此索引。 |
| 修复建议 | 在切片 UserPoints 中添加 `__table_args__ = (Index("idx_points_user_updated", "user_id", "updated_at"),)` |

#### P1-5：§5 Subscription `status` 字段缺少 `default='active'`

| 属性 | 值 |
|------|-----|
| 表名 | subscription |
| 文件 | `docs/04详细设计/04-数据库详细设计.md` |
| 行号 | §5 L2647 |
| 问题描述 | §5 Subscription 模型 `status: Mapped[str] = mapped_column(String(20))` 没有 default 值。DB §2.17 L729 明确定义 `DEFAULT 'active'`。切片 10-membership L227-228 正确定义了 `default="active"`。 |
| 修复建议 | 将 §5 L2647 改为 `status: Mapped[str] = mapped_column(String(20), default="active")` |

---

### P2 — 中优先级

#### P2-1：§5 缺少 10 个 §2 中定义的表的 SQLAlchemy 模型

| 属性 | 值 |
|------|-----|
| 表名 | rating_history, training_plan, plan_adjustment, knowledge_category, knowledge_entry, rule_definition, training_template, model_3d_asset, action_category, membership_tier_config |
| 文件 | `docs/04详细设计/04-数据库详细设计.md` |
| 行号 | §5 各节（L2229-2950） |
| 问题描述 | §5 SQLAlchemy Model 代码示例仅包含 29 个模型，但 §2 Phase 1 定义了 38 张表。以下 10 张表在 §2 中有完整定义、在切片中有模型实现，但 §5 中无对应模型：RatingHistory(§2.3)、TrainingPlan(§2.28)、PlanAdjustment(§2.23)、KnowledgeCategory(§2.24)、KnowledgeEntry(§2.25)、RuleDefinition(§2.26)、TrainingTemplate(§2.27)、Model3DAsset(§2.29)、ActionCategory(§2.30)、MembershipTierConfig(§2.31)。 |
| 修复建议 | 在 §5 中补充这 10 个模型的 SQLAlchemy 代码示例，或在 §5 开头明确声明"仅包含核心模型示例，完整模型见各切片文件"。 |

#### P2-2：§6 索引总表缺少多个表的索引

| 属性 | 值 |
|------|-----|
| 文件 | `docs/04详细设计/04-数据库详细设计.md` |
| 行号 | §6 L2952-2991 |
| 问题描述 | §6 核心索引清单缺少以下表的索引定义：①badge_definition（`idx_badge_definition_category`、`idx_badge_definition_active`，§3.1.4 L1191-1192 已定义）；②user_badge（`idx_user_badge_user`，§5 L2867 已定义）；③badge_progress（`idx_badge_progress_user`，§5 L2886 已定义）；④consent_log（`idx_consent_user_at`、`idx_consent_user_type`，§5 L2326-2327 已定义）；⑤export_task（`idx_export_user_created`，§5 L2347 已定义）；⑥match（`idx_match_user_created`、`idx_match_status`，§5 L2529-2530 已定义）；⑦pipeline_step（`idx_pipeline_step_task_step`，§5 L2435 已定义）；⑧refund_record（`idx_refund_order`，§5 L2727 已定义）。 |
| 修复建议 | 在 §6 索引总表中补充以上 8 张表对应的索引行，确保索引总表覆盖所有 §5 和切片中定义的索引。 |

#### P2-3：切片 09-gamification BadgeDefinition `idx_badge_definition_category` 索引缺少 `sort_order` 列

| 属性 | 值 |
|------|-----|
| 表名 | badge_definition |
| 文件 | `docs/06.../09-gamification/backend.md` |
| 行号 | L234 |
| 问题描述 | 切片 `Index("idx_badge_definition_category", "category")` 只有 `category` 一列，但 DB §5 L2850 和 §3.1.4 L1191 均定义索引为 `(category, sort_order)` 双列索引。缺少 `sort_order` 会影响按分类排序查询的效率。 |
| 修复建议 | 将切片 L234 改为 `Index("idx_badge_definition_category", "category", "sort_order")` |

#### P2-4：切片 09-gamification UserBadge 缺少 `idx_user_badge_user` 索引

| 属性 | 值 |
|------|-----|
| 表名 | user_badge |
| 文件 | `docs/06.../09-gamification/backend.md` |
| 行号 | L248-250 |
| 问题描述 | 切片 UserBadge 的 `__table_args__` 只有 `UniqueConstraint("user_id", "badge_id", name="uq_user_badge")`，缺少 `Index("idx_user_badge_user", "user_id")` 索引。DB §5 L2867 和 §3.1.5 L1210 均定义了此索引（用户徽章列表查询）。 |
| 修复建议 | 在 `__table_args__` 中补充 `Index("idx_user_badge_user", "user_id")` |

#### P2-5：切片 09-gamification BadgeProgress 缺少 `idx_badge_progress_user` 索引

| 属性 | 值 |
|------|-----|
| 表名 | badge_progress |
| 文件 | `docs/06.../09-gamification/backend.md` |
| 行号 | L265-267 |
| 问题描述 | 切片 BadgeProgress 的 `__table_args__` 只有 `UniqueConstraint("user_id", "badge_id", name="uq_badge_progress")`，缺少 `Index("idx_badge_progress_user", "user_id")` 索引。DB §5 L2886 和 §3.1.6 L1234 均定义了此索引（用户进度列表查询）。 |
| 修复建议 | 在 `__table_args__` 中补充 `Index("idx_badge_progress_user", "user_id")` |

#### P2-6：切片 10-membership Subscription 索引命名与 §5/§6 不一致

| 属性 | 值 |
|------|-----|
| 表名 | subscription |
| 文件 | `docs/06.../10-membership/backend.md` |
| 行号 | L242 |
| 问题描述 | 切片使用 `Index("idx_subscription_user_status", "user_id", "status")`，但 DB §5 L2660 和 §6 L2970 均使用 `idx_sub_user_status`。索引命名不一致可能导致 Alembic 迁移生成重复索引。 |
| 修复建议 | 将切片 L242 改为 `Index("idx_sub_user_status", "user_id", "status")` 以与 §5/§6 对齐。 |

#### P2-7：切片 11-payment RefundRecord 索引命名与 §5 不一致

| 属性 | 值 |
|------|-----|
| 表名 | refund_record |
| 文件 | `docs/06.../11-payment/backend.md` |
| 行号 | L523 |
| 问题描述 | 切片使用 `Index("idx_refund_record_order", "order_id")`，但 DB §5 L2727 使用 `idx_refund_order`。索引命名不一致。 |
| 修复建议 | 将切片 L523 改为 `Index("idx_refund_order", "order_id")` 以与 §5 对齐。 |

#### P2-8：切片 04-scoring Match 缺少 `idx_match_status` 索引

| 属性 | 值 |
|------|-----|
| 表名 | match |
| 文件 | `docs/06.../04-scoring/backend.md` |
| 行号 | L350-352 |
| 问题描述 | 切片 Match 的 `__table_args__` 只有 `Index("idx_match_user_created", "user_id", "created_at")`，缺少 `Index("idx_match_status", "status")` 索引。DB §5 L2530 和 §2.10 L632 均定义了 `(status)` 索引用于恢复比赛查询。切片 L334 虽然在 `status` 字段上加了 `index=True`，但生成的自动索引名与 §5 命名不一致。 |
| 修复建议 | 移除 L334 的 `index=True`，在 `__table_args__` 中显式添加 `Index("idx_match_status", "status")` |

#### P2-9：§5 TechniqueTrend 的 Float 类型字段缺少类型指定

| 属性 | 值 |
|------|-----|
| 表名 | technique_trend |
| 文件 | `docs/04详细设计/04-数据库详细设计.md` |
| 行号 | §5 L2767-2771 |
| 问题描述 | §5 TechniqueTrend 模型中 `current_value`、`previous_value`、`change_rate`、`target_value` 四个字段的 `mapped_column(nullable=True)` 没有显式指定 `Float` 类型。DB §2.22 L851-855 定义为 `FLOAT`。切片 08-progress_analysis L404-411 正确使用了 `mapped_column(Float, nullable=True)`。§5 缺少类型指定可能导致 SQLAlchemy 类型推断为默认类型而非 Float。 |
| 修复建议 | 在 §5 中为这四个字段补充 Float 类型：`mapped_column(Float, nullable=True)` |

#### P2-10：切片 VideoTask 索引命名与 §6 权威源不一致

| 属性 | 值 |
|------|-----|
| 表名 | video_task |
| 文件 | `docs/06.../03-video_analysis/backend.md` + `docs/04详细设计/04-数据库详细设计.md` |
| 行号 | 切片 L263-264；§5 L2414-2415；§6 L2958-2959 |
| 问题描述 | 切片和 §5 均使用 `idx_video_task_user_created` 和 `idx_video_task_status_created`，但 §6 索引总表（L2231 注释标注为权威源）使用 `idx_vtask_user_created` 和 `idx_vtask_status`。切片应与 §6 对齐。**注**：§5 L2231 已声明"索引命名以 §6 索引总表为权威源"，但切片未据此对齐。 |
| 修复建议 | 统一决策：要么将 §6 索引名改为 `idx_video_task_*` 以匹配 §5/切片，要么将切片改为 `idx_vtask_*` 以匹配 §6。建议以 §6 为准修改切片。 |

---

### P3 — 低优先级

#### P3-1：切片 01-auth User `nickname` 添加了 DB 未定义的 default 值

| 属性 | 值 |
|------|-----|
| 表名 | user |
| 文件 | `docs/06.../01-auth/backend.md` |
| 行号 | L134 |
| 问题描述 | 切片 `nickname: Mapped[str] = mapped_column(String(64), default="球友")`，但 DB §2.1 L445 和 §5 L2255 均无 default 值。切片 02-user L196 也无 default。 |
| 修复建议 | 移除 `default="球友"`，或在 DB §2.1 和 §5 中统一补充此 default 值（需业务确认）。 |

#### P3-2：切片 01-auth User `openid`/`phone` 添加了冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | user |
| 文件 | `docs/06.../01-auth/backend.md` |
| 行号 | L132-133 |
| 问题描述 | 切片对 `openid` 和 `phone` 同时使用 `unique=True, index=True`。DB §2.1 L461-462 定义的是部分唯一索引（`WHERE openid IS NOT NULL`），`unique=True` 已隐式创建索引，额外的 `index=True` 会创建冗余的 B-Tree 索引。切片 02-user L194-195 仅使用 `unique=True` 无 `index=True`。 |
| 修复建议 | 移除 `index=True`，仅保留 `unique=True`。 |

#### P3-3：切片 02-user RatingHistory `source` 字段添加了 DB 未定义的 default 值

| 属性 | 值 |
|------|-----|
| 表名 | rating_history |
| 文件 | `docs/06.../02-user/backend.md` |
| 行号 | L229 |
| 问题描述 | 切片 `source: Mapped[str] = mapped_column(String(20), default="manual")`，但 DB §2.3 L486 无 default 定义（必填字段）。 |
| 修复建议 | 此 default 值合理（手动录入为常见来源），建议在 DB §2.3 中补充 `DEFAULT 'manual'` 以对齐。 |

#### P3-4：§5 和切片 Order `product_type` 注释缺少 `tournament` 枚举值

| 属性 | 值 |
|------|-----|
| 表名 | order |
| 文件 | `docs/04详细设计/04-数据库详细设计.md` + `docs/06.../11-payment/backend.md` |
| 行号 | §5 L2673；切片 L457 |
| 问题描述 | DB §2.18 L747 定义 `product_type` 枚举为 `membership/analysis_pack/equipment/tournament`，但 §5 L2673 和切片 L457 的注释仅列出 `membership/analysis_pack/equipment`，缺少 `tournament`。 |
| 修复建议 | 在 §5 和切片注释中补充 `tournament` 枚举值。 |

#### P3-5：§5 AdminUser 包含 §2.31 DDL 中未定义的 `last_login_at` 字段

| 属性 | 值 |
|------|-----|
| 表名 | admin_user |
| 文件 | `docs/04详细设计/04-数据库详细设计.md` |
| 行号 | §5 L2913 |
| 问题描述 | §5 AdminUser 模型包含 `last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)` 字段，但 DB §2.31 L989-999 的 admin_user 表定义中无此字段。切片 admin.md L69-80 也无此字段。 |
| 修复建议 | 在 §2.31 admin_user 表定义中补充 `last_login_at TIMESTAMPTZ N NULL` 字段，或在 §5 中移除此字段（需确认业务需求）。 |

#### P3-6：切片 04-scoring Match `format`/`match_type` 添加了 DB §2.10 未定义的 default 值

| 属性 | 值 |
|------|-----|
| 表名 | match |
| 文件 | `docs/06.../04-scoring/backend.md` |
| 行号 | L330-331 |
| 问题描述 | 切片 `format: Mapped[str] = mapped_column(String(20), default="bo5")` 和 `match_type: Mapped[str] = mapped_column(String(20), default="friendly")`，但 DB §2.10 L615-616 这两个字段无 default 值（仅必填）。§5 L2508-2509 也无 default。 |
| 修复建议 | 在 DB §2.10 中补充 `DEFAULT 'bo5'` 和 `DEFAULT 'friendly'`，或在切片中移除 default（需确认业务需求）。 |

---

## 4. 汇总统计

### 4.1 问题分级统计

| 级别 | 数量 | 说明 |
|------|------|------|
| P0 | 0 | 无阻断级问题 |
| P1 | 5 | 高优先级：字段缺失、索引缺失、default 值缺失 |
| P2 | 10 | 中优先级：模型覆盖度、索引命名一致性、索引总表完整性 |
| P3 | 6 | 低优先级：default 值偏差、冗余索引、注释缺失 |
| **合计** | **21** | |

### 4.2 R17 修复验证统计

| 验证项 | 状态 |
|--------|------|
| 11 个缺失模型补充 | ✅ 通过 |
| 6 个 `__table_args__` 补充 | ✅ 通过 |
| badge FK ondelete RESTRICT | ✅ 通过 |
| PaymentRecord paid_at nullable=False | ✅ 通过 |
| audit_log admin_id FK RESTRICT | ✅ 通过 |
| 切片索引命名修正 | ✅ 通过 |
| BadgeDefinition `idx_badge_definition_active` | ✅ 通过 |
| **合计** | **7/7 全部通过** |

### 4.3 按文件分布统计

| 文件 | P1 | P2 | P3 | 小计 |
|------|-----|-----|-----|------|
| DB 设计 §5 | 2 | 3 | 1 | 6 |
| DB 设计 §6 | 0 | 1 | 0 | 1 |
| 03-video_analysis/backend.md | 2 | 1 | 0 | 3 |
| 04-scoring/backend.md | 0 | 1 | 1 | 2 |
| 09-gamification/backend.md | 1 | 3 | 0 | 4 |
| 10-membership/backend.md | 0 | 1 | 0 | 1 |
| 11-payment/backend.md | 0 | 1 | 1 | 2 |
| 01-auth/backend.md | 0 | 0 | 2 | 2 |
| 02-user/backend.md | 0 | 0 | 1 | 1 |

### 4.4 按审查清单维度分布

| 审查维度 | P1 | P2 | P3 | 说明 |
|---------|-----|-----|-----|------|
| 1. 表名一致性 | 0 | 0 | 0 | 全部一致 ✅ |
| 2. 列名一致性 | 0 | 0 | 0 | 全部一致 ✅ |
| 3. 列类型一致性 | 0 | 1 | 0 | P2-9: §5 TechniqueTrend Float 类型缺失 |
| 4. DateTime 时区 | 0 | 0 | 0 | 全部使用 `DateTime(timezone=True)` ✅ |
| 5. 主键一致性 | 0 | 0 | 0 | 全部一致 ✅ |
| 6. 外键一致性 | 0 | 0 | 0 | 全部一致（含 ondelete 策略）✅ |
| 7. 唯一约束一致性 | 0 | 0 | 0 | 全部一致 ✅ |
| 8. 默认值一致性 | 1 | 0 | 3 | P1-5: §5 Subscription status 缺 default；P3-1/P3-3/P3-6: 切片 default 偏差 |
| 9. 非空约束一致性 | 0 | 0 | 0 | 全部一致 ✅ |
| 10. 索引命名一致性 | 0 | 3 | 0 | P2-6/P2-7/P2-10: 索引命名偏差 |
| 11. `__table_args__` 完整性 | 3 | 2 | 0 | P1-2/P1-3/P1-4: 切片缺失；P2-4/P2-5: badge 索引缺失 |
| 12. §5 模型覆盖度 | 0 | 1 | 0 | P2-1: 10 个模型缺失 |
| 13. 枚举值一致性 | 0 | 0 | 1 | P3-4: product_type 注释缺 tournament |
| 14. ER 图字段一致性 | 0 | 0 | 0 | 未发现不一致 ✅ |
| §6 索引总表完整性 | — | 1 | 0 | P2-2: 8 张表索引未列入 |
| 字段增补 | 0 | 0 | 1 | P3-5: §5 AdminUser last_login_at |

### 4.5 总体评价

**R17 修复状态**：7 项修复全部验证通过，R17 提出的所有问题均已正确修复。

**当前一致性水平**：DB 设计 v1.6 与切片在表名、列名、列类型、主键、外键、唯一约束、非空约束、DateTime 时区等核心维度上高度一致。剩余问题集中在索引完整性（切片中部分索引缺失）和索引命名一致性（切片与 §6 权威源之间的命名偏差），以及 §5 模型覆盖度（10 个 Phase 1 表缺少 §5 代码示例）。

**优先修复建议**：
1. **P1 优先**：修复 §5 MatchStatistic 缺失 `created_at`（P1-1）、切片 ShareRecord/FeedbackRecord/UserPoints 缺失索引（P1-2/P1-3/P1-4）、§5 Subscription status 缺 default（P1-5）
2. **P2 跟进**：补全 §6 索引总表（P2-2）、对齐索引命名（P2-6/P2-7/P2-10）、补充 badge 索引（P2-4/P2-5）
3. **P3 视情况处理**：default 值偏差和注释缺失等低风险问题

---

*报告结束*
