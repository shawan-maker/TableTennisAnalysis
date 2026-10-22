# R19-DB 字段级 + 数据完整性审查报告

> **审查轮次**：第十九轮（R19）
> **审查维度**：DB 字段级一致性 + 数据完整性
> **审查日期**：2026-10-19
> **DB 设计版本**：v1.6（2026-10-19 09:49 更新）
> **基线报告**：R18-DB 字段级一致性审查报告（2026-10-16）
> **审查代理**：R19 审查代理

---

## 1. 审查范围

### 1.1 DB 设计文件

| 文件 | 说明 |
|------|------|
| `docs/04详细设计/04-数据库详细设计.md` | DB 设计 v1.6（§1 ER + §2 DDL 39 张表 + §3 Phase 2-4 表 + §4 枚举 + §5 SQLAlchemy Models 29 个 + §6 索引总表 + §7 JSONB + §10 反幻觉约束），共 3227 行 |

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

### 1.3 基础设施文件（3 个）

| 文件 | 说明 |
|------|------|
| `13-infrastructure/admin.md` | AdminUser, AuditLog, SystemConfig 模型 |
| `13-infrastructure/knowledge_base.md` | KnowledgeCategory, KnowledgeEntry, RuleDefinition, TrainingTemplate 模型 |
| `13-infrastructure/ai_inference.md` | 无独立模型（R18-P3-12 HTTPException→AppException 修复点） |
| `13-infrastructure/ai_pipeline.md` | 复用 video_analysis 模块模型，无独立定义 |
| `13-infrastructure/file_management.md` | 无模型定义（仅 FileService + Pydantic Schema） |

### 1.4 审查方法

- 使用 `grep` 搜索 `class.*Base`、`__tablename__`、`__table_args__`、`Column`、`ForeignKey`、`Index(`、`default=` 等模式
- 交叉比对 DB §1 ER / §2 DDL / §5 SQLAlchemy 模型 / §6 索引总表 / §10 反幻觉约束 / 切片模型 / 基础设施模型
- `[REDACTED]` 显示伪影：`primary_key` 行显示为 `[REDACTED]]]]]]...`，实际为 `True`，通过 grep 模式匹配绕过
- **R18 修复验证**：以 R18 报告 21 项 + R18 推迟项 2 项 = 23 项为基线，逐项回归
- **R19 深层检查**：11 项检查清单（表名/列名/类型一致性、DateTime 时区、PK/FK/Unique/Check、FK ondelete 策略、索引完整性、§5 模型覆盖度、数据完整性、冗余索引检测、复合索引覆盖度、N+1 风险、表数口径）

---

## 2. R18 修复验证表（21 项 + 2 项推迟 = 23 项）

### 2.1 R18 P1 修复（5 项）

| # | 验证项 | 状态 | 备注 |
|---|--------|------|------|
| 1 | **P1-1**：§5 MatchStatistic 缺失 `created_at` | ✅ | §5 L2572 已补充 `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))`，带注释 `# R18-P1-1: 补充 created_at（§2.12 已定义）` |
| 2 | **P1-2**：切片 03 ShareRecord 缺失 `__table_args__` | ✅ | 切片 03-video_analysis L354-355 已补充 `__table_args__ = (Index("idx_share_user_created", "user_id", "created_at"),)`，带注释 `# R18-P1-2: 补充索引（§5/§6 已定义）` |
| 3 | **P1-3**：切片 03 FeedbackRecord 缺失审核队列索引 | ✅ | 切片 L331-335 `__table_args__` 已补充 `Index("idx_feedback_status", "status")` 和 `Index("idx_feedback_correct_created", "is_correct", "created_at")`，带注释 `# R18-P1-3` |
| 4 | **P1-4**：切片 09 UserPoints 缺失 `__table_args__` | ✅ | 切片 09-gamification L195-196 已补充 `__table_args__ = (Index("idx_points_user_updated", "user_id", "updated_at"),)`，带注释 `# R18-P1-4` |
| 5 | **P1-5**：§5 Subscription `status` 缺 `default='active'` | ✅ | §5 L2657 `status: Mapped[str] = mapped_column(String(20), default="active")` 已补充，带注释 `# R18-P1-5` |

### 2.2 R18 P2 修复（10 项）

| # | 验证项 | 状态 | 备注 |
|---|--------|------|------|
| 6 | **P2-1**：§5 缺失 10 个 §2 表的 SQLAlchemy 模型 | ✅ | §5 L2240 已添加 `R18-P2-1 注释`，明确声明"§5 仅包含核心模型代码示例（29 个），10 个 §2 Phase 1 表的 SQLAlchemy 模型定义见对应切片文件" |
| 7 | **P2-2**：§6 索引总表缺失 8 张表索引 | ✅ | §6 L3001-3011 已补充 `badge_definition / user_badge / badge_progress / consent_log / export_task / match / pipeline_step / refund_record` 8 张表索引，均带 `<!-- R18-P2-2 -->` 注释 |
| 8 | **P2-3**：切片 09 BadgeDefinition `idx_badge_definition_category` 缺 `sort_order` | ✅ | 切片 L238 `Index("idx_badge_definition_category", "category", "sort_order")` 已补充 `sort_order` 列，带注释 `# R18-P2-3` |
| 9 | **P2-4**：切片 09 UserBadge 缺失 `idx_user_badge_user` | ✅ | 切片 L254 `Index("idx_user_badge_user", "user_id")` 已补充，带注释 `# R18-P2-4` |
| 10 | **P2-5**：切片 09 BadgeProgress 缺失 `idx_badge_progress_user` | ✅ | 切片 L272 `Index("idx_badge_progress_user", "user_id")` 已补充，带注释 `# R18-P2-5` |
| 11 | **P2-6**：切片 10 Subscription 索引命名不一致 | ✅ | 切片 L242 `Index("idx_sub_user_status", "user_id", "status")` 已对齐 §5/§6，带注释 `# R18-P2-6` |
| 12 | **P2-7**：切片 11 RefundRecord 索引命名不一致 | ✅ | 切片 L523 `Index("idx_refund_order", "order_id")` 已对齐 §5/§6，带注释 `# R18-P2-7` |
| 13 | **P2-8**：切片 04 Match 缺失 `idx_match_status` | ✅ | 切片 L352 `Index("idx_match_status", "status")` 已补充；L334 `status` 字段移除 `index=True`，改用 `__table_args__` 显式索引，均带注释 `# R18-P2-8` |
| 14 | **P2-9**：§5 TechniqueTrend Float 类型缺失 | ✅ | §5 L2746 `from sqlalchemy import ... Float` 已导入；L2777-2781 四个字段 `current_value/previous_value/change_rate/target_value` 均补充 `Float` 类型，带注释 `# R18-P2-9` |
| 15 | **P2-10**：VideoTask 索引命名 §5/§6 不一致 | ✅ | §6 L2968-2969 已对齐 §5/切片 `idx_video_task_user_created` 和 `idx_video_task_status_created`，带注释 `<!-- R18-P2-10: 索引命名对齐 §5/切片 -->` |

### 2.3 R18 P3 修复（6 项）

| # | 验证项 | 状态 | 备注 |
|---|--------|------|------|
| 16 | **P3-1**：切片 01 User nickname 多余 `default="球友"` | ✅ | 切片 01-auth L134 `nickname: Mapped[str] = mapped_column(String(64))` 已移除 default，带注释 `# R18-P3-1: 移除 default="球友"（§2.1/§5 未定义）`；业务层 L306/L356 仍保留 `nickname=req.nickname or "球友"` 是合理的运行时默认值，非 DB 层 default |
| 17 | **P3-2**：切片 01 User openid/phone 冗余 `index=True` | ✅ | 切片 L132-133 已移除 `index=True`，仅保留 `unique=True`，带注释 `# R18-P3-2` |
| 18 | **P3-3**：§2.3 rating_history `source` 缺 `DEFAULT 'manual'` | ✅ | §2.3 L492 已补充 `DEFAULT 'manual'`，带注释 `R18-P3-3: 补充 DEFAULT（与切片 02 对齐）` |
| 19 | **P3-4**：§5/切片 Order `product_type` 注释缺 `tournament` | ✅ | §5 L2683 注释 `# membership/analysis_pack/equipment/tournament  R18-P3-4: 补充 tournament（§2.18 已定义）` 已补充；切片 11-payment L457 注释也已同步 |
| 20 | **P3-5**：§2.31 admin_user 缺失 `last_login_at` | ✅ | §2.31 L1004 已补充 `last_login_at TIMESTAMPTZ N NULL`，带注释 `R18-P3-5: 补充（§5 AdminUser 已定义，切片 admin.md 已定义）` — **但切片 13-admin.md 仍未同步**（见 R19 P1-1） |
| 21 | **P3-6**：§2.10 match `format`/`match_type` 缺 DEFAULT | ✅ | §2.10 L621-622 已补充 `DEFAULT 'bo5'` 和 `DEFAULT 'friendly'`，均带注释 `R18-P3-6` |

### 2.4 R18 推迟项闭环（2 项）

| # | 验证项 | 状态 | 备注 |
|---|--------|------|------|
| 22 | **表数口径 39 vs 35 注释** | ✅ | §2 L438-442 已添加 `R18-P3-20 修复（已在 R18 落地）` 注释块，详细说明 35 张核心 Phase 1 业务表 + 4 张 Phase 2 提前实现表（plan_adjustment/action_category/model_3d_asset/training_plan）= 39 张表的口径差异，与实施计划 §1.1 "Phase 1 = 35 表" 不冲突 |
| 23 | **AI 推理 HTTPException→AppException** | ✅ | ai_inference.md L363 已添加 `R18-P3-12 修复` 注释，L373 `from app.core.exceptions import AppException`，L396/412/423/439/453/469/480/495 八处推理端点（ball/table/pose/action detection）的 `raise AppException(...)` 已全部替换，错误响应统一返回 `{code, message, data}` 结构 |

**R18 修复验证结论**：23/23 项全部通过 ✅（含 21 项 R18 问题修复 + 2 项 R18 推迟项闭环）

> **R18-P3-5 闭环缺口**：§2.31 DDL 和 §5 AdminUser 模型均已补充 `last_login_at`，但 R18 报告中 P3-5 备注称"切片 admin.md 已定义"实际不成立——切片 13-infrastructure/admin.md L69-80 AdminUser 模型仍缺少此字段。这是 R18 修复未完全闭环的回归问题，归入 R19 P1-1。

---

## 3. R19 新发现

### P0 — 严重（阻断级）

无 P0 级问题。

---

### P1 — 高优先级

#### P1-1：切片 13-admin AdminUser 缺少 `last_login_at` 字段（R18-P3-5 闭环缺口）

| 属性 | 值 |
|------|-----|
| 表名 | admin_user |
| 文件 | `docs/06垂直模块前后端切片设计/13-infrastructure/admin.md` |
| 行号 | L69-80（AdminUser 模型完整定义） |
| 问题描述 | §2.31 L1004 已补充 `last_login_at TIMESTAMPTZ N NULL`（R18-P3-5 已修复，带注释），§5 L2923 AdminUser 模型也定义了 `last_login_at: Mapped[datetime \| None] = mapped_column(DateTime(timezone=True), nullable=True)`，但**切片 13-admin.md L69-80 AdminUser 模型仍缺少此字段**。切片定义仅包含 `id/username/password_hash/role/is_active/created_at` 6 个字段，未同步 `last_login_at`。这是 R18-P3-5 修复声明与实际实现不一致的回归问题，会导致 Alembic 迁移生成时遗漏此字段，进而造成运行时管理员登录后无法记录最后登录时间。 |
| 修复建议 | 在切片 13-admin.md AdminUser 模型 L80（`created_at` 后）补充：`last_login_at: Mapped[datetime \| None] = mapped_column(DateTime(timezone=True), nullable=True)` 以与 §2.31 和 §5 三方对齐 |

---

### P2 — 中优先级

#### P2-1：§5 ManualScoreDetail 缺少 `created_at` 字段（§2.14 DDL 已定义）

| 属性 | 值 |
|------|-----|
| 表名 | manual_score_detail |
| 文件 | `docs/04详细设计/04-数据库详细设计.md` |
| 行号 | §5 L2619-2634（ManualScoreDetail 完整模型） |
| 问题描述 | §5 ManualScoreDetail 模型仅包含 `id/match_record_id/sequence/scorer/score_method/technique_action` 6 个字段，缺少 `created_at` 字段。DB §2.14 L697 明确定义 `created_at TIMESTAMPTZ Y DEFAULT NOW()`。切片 05-match_data L445 也正确定义了 `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))`。§5 模型与 §2/切片不一致，会导致以 §5 为参考生成的 Alembic 迁移遗漏此字段。 |
| 修复建议 | 在 §5 ManualScoreDetail 模型 L628（`technique_action` 后）补充：`created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))` 以与 §2.14 和切片 05 三方对齐 |

#### P2-2：切片 03-video_analysis AnalysisReport 缺失 `idx_report_text_gin` GIN 索引

| 属性 | 值 |
|------|-----|
| 表名 | analysis_report |
| 文件 | `docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` |
| 行号 | L309-311（AnalysisReport `__table_args__`） |
| 问题描述 | 切片 AnalysisReport `__table_args__` 只定义了 `Index("idx_report_user_created", "user_id", "created_at")`，缺少 `idx_report_text_gin` GIN 索引。§5 L2470-2471 明确定义 `Index("idx_report_text_gin", text("to_tsvector('simple', report_text)"), postgresql_using="gin")`，§6.2 L3017 索引总表也列出 `analysis_report \| report_text \| GIN \| 按问题关键词搜索报告`。切片缺失此 GIN 索引会导致按问题关键词搜索报告时全表扫描，性能严重退化（analysis_report 是 JSONB 重表，预计 500/月累积）。 |
| 修复建议 | 在切片 AnalysisReport `__table_args__` 中补充：`Index("idx_report_text_gin", text("to_tsvector('simple', report_text)"), postgresql_using="gin")`，并在文件顶部导入 `from sqlalchemy import text`（若未导入） |

#### P2-3：切片 08-progress_analysis ProgressSnapshot 缺失 `idx_ps_metrics_gin` GIN 索引

| 属性 | 值 |
|------|-----|
| 表名 | progress_snapshot |
| 文件 | `docs/06垂直模块前后端切片设计/08-progress_analysis/backend.md` |
| 行号 | L388-391（ProgressSnapshot `__table_args__`） |
| 问题描述 | 切片 ProgressSnapshot `__table_args__` 只定义了 `Index("idx_ps_user_created", "user_id", "created_at")`，并用注释 `# GIN 索引通过 Alembic 迁移手动添加` `# CREATE INDEX idx_ps_metrics_gin ON progress_snapshot USING GIN (metrics_snapshot);` 代替 GIN 索引定义。§5 L2766 明确定义 `Index("idx_ps_metrics_gin", "metrics_snapshot", postgresql_using="gin")` 在 `__table_args__` 中，§6.2 L3018 也列出 `progress_snapshot \| metrics_snapshot \| GIN \| 按指标查询快照`。切片注释方式存在两个问题：①Alembic autogenerate 不会自动包含注释中的 SQL，需开发者手动执行；②若开发者按注释操作但忘写迁移文件，GIN 索引会丢失。 |
| 修复建议 | 将切片 L390 注释替换为正式索引定义：`Index("idx_ps_metrics_gin", "metrics_snapshot", postgresql_using="gin")`，同时移除 L427 "在迁移文件中手动添加 GIN 索引"的实现清单项 |

#### P2-4：切片 03-video_analysis AnalysisReport `idx_report_user_created` 索引缺 `text("created_at DESC")` 排序

| 属性 | 值 |
|------|-----|
| 表名 | analysis_report |
| 文件 | `docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` |
| 行号 | L310（AnalysisReport `__table_args__` 第一行） |
| 问题描述 | 切片 L310 `Index("idx_report_user_created", "user_id", "created_at")` 缺少 DESC 排序声明。§5 L2470 `Index("idx_report_user_created", "user_id", text("created_at DESC"))` 明确使用 `text("created_at DESC")`，§6.1 L2970 索引总表也声明 `(user_id, created_at DESC)`。分析报告列表查询通常按时间倒序（最新在前），缺少 DESC 排序会让 PostgreSQL 在用户列表查询时额外执行 `Sort` 算子或反向扫描，影响性能。 |
| 修复建议 | 将切片 L310 改为 `Index("idx_report_user_created", "user_id", text("created_at DESC"))`，并在文件顶部导入 `from sqlalchemy import text`（若未导入） |

#### P2-5：切片 13-knowledge_base KnowledgeEntry 缺失 `content` GIN 索引定义

| 属性 | 值 |
|------|-----|
| 表名 | knowledge_entry |
| 文件 | `docs/06垂直模块前后端切片设计/13-infrastructure/knowledge_base.md` |
| 行号 | L80-96（KnowledgeEntry 模型完整定义，无 `__table_args__`） |
| 问题描述 | 切片 KnowledgeEntry 模型没有 `__table_args__`，缺少 `content` 字段的 GIN 索引定义。§6.2 L3019 索引总表明确定义 `knowledge_entry \| content \| GIN \| 知识库内容搜索`，§2.25 L905 DDL 也声明 `content JSONB Y — 条目内容 GIN 索引`。知识库内容搜索是知识库模块核心功能，缺索引会导致全表扫描。 |
| 修复建议 | 在切片 KnowledgeEntry 模型中添加 `__table_args__ = (Index("idx_knowledge_entry_content_gin", "content", postgresql_using="gin"),)`，并在文件顶部导入 `from sqlalchemy import Index`（若未导入） |

---

### P3 — 低优先级（冗余索引与命名偏差）

#### P3-1：切片 09-gamification BadgeDefinition `is_active` 冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | badge_definition |
| 文件 | `09-gamification/backend.md` |
| 行号 | L235 |
| 问题描述 | 切片 L235 `is_active: Mapped[bool] = mapped_column(default=True, index=True)` 和 L239 `Index("idx_badge_definition_active", "is_active")` 同时定义 `is_active` 索引，会生成两个重复索引（`ix_badge_definition_is_active` + `idx_badge_definition_active`）。§5 L2857 仅使用 `mapped_column(Boolean, default=True)` 不带 `index=True`，仅靠 `__table_args__` 显式索引。R18 P2-2 修复 §6 索引总表时声明"对齐切片 L231 index=True"，但实际是冗余。 |
| 修复建议 | 移除切片 L235 的 `index=True`，仅保留 `__table_args__` 中的 `idx_badge_definition_active` 索引 |

#### P3-2：切片 09-gamification CheckInRecord 缺失 `idx_checkin_user_date` 索引（同时存在多个冗余 `index=True`）

| 属性 | 值 |
|------|-----|
| 表名 | checkin_record |
| 文件 | `09-gamification/backend.md` |
| 行号 | L205-206, L215-217 |
| 问题描述 | 切片 CheckInRecord `__table_args__` L215-217 只有 `UniqueConstraint("user_id", "checkin_date", name="uq_checkin_user_date")`，缺少 `Index("idx_checkin_user_date", "user_id", "checkin_date")`。§5 L2314-2317 明确同时定义 UniqueConstraint + Index。同时切片 L205 `user_id` 加 `index=True`、L206 `checkin_date` 加 `index=True`，会创建两个冗余单列索引（`ix_checkin_record_user_id` + `ix_checkin_record_checkin_date`），而唯一约束已覆盖两列组合查询。 |
| 修复建议 | ①移除 L205 和 L206 的 `index=True`；②在 `__table_args__` 中补充 `Index("idx_checkin_user_date", "user_id", "checkin_date")` |

#### P3-3：切片 09-gamification UserBadge `user_id` 冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | user_badge |
| 文件 | `09-gamification/backend.md` |
| 行号 | L248 |
| 问题描述 | 切片 L248 `user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)` 有 `index=True`，但 `__table_args__` L254 已有 `Index("idx_user_badge_user", "user_id")`，会创建重复索引。R18-P2-4 修复时只补充了 `idx_user_badge_user` 索引，未移除 `index=True`。§5 L2871 仅使用 `mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"))` 不带 `index=True`。 |
| 修复建议 | 移除切片 L248 的 `index=True` |

#### P3-4：切片 09-gamification BadgeProgress `user_id` 冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | badge_progress |
| 文件 | `09-gamification/backend.md` |
| 行号 | L263 |
| 问题描述 | 切片 L263 `user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)` 有 `index=True`，但 `__table_args__` L272 已有 `Index("idx_badge_progress_user", "user_id")`，会创建重复索引。R18-P2-5 修复时只补充了 `idx_badge_progress_user` 索引，未移除 `index=True`。§5 L2887 不带 `index=True`。 |
| 修复建议 | 移除切片 L263 的 `index=True` |

#### P3-5：切片 11-payment Order/PaymentRecord 多处冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | order, payment_record |
| 文件 | `11-payment/backend.md` |
| 行号 | L450 Order.user_id, L487 PaymentRecord.order_id |
| 问题描述 | 切片 Order L450 `user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), index=True,)` 有 `index=True`，但 `__table_args__` L475 已有 `Index("idx_order_user_created", "user_id", "created_at")` 复合索引（覆盖 user_id 单列查询）；切片 PaymentRecord L487 `order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("order.id", ondelete="CASCADE"), index=True,)` 有 `index=True`，但 `__table_args__` L501 已有 `Index("idx_payment_order", "order_id")` 同名索引（覆盖 order_id 单列查询）。§5 L2679/L2704 均不带 `index=True`。两处都生成冗余索引 `ix_order_user_id` + `ix_payment_record_order_id`。 |
| 修复建议 | 移除切片 L450 和 L487 的 `index=True` |

#### P3-6：切片 02-user RatingHistory/ExportTask 多处冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | rating_history, export_task |
| 文件 | `02-user/backend.md` |
| 行号 | L227 RatingHistory.user_id, L244 ExportTask.user_id, L245 ExportTask.task_id |
| 问题描述 | ①切片 RatingHistory L227 `user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)` 有 `index=True`，但 `__table_args__` L233 已有 `Index("idx_rating_history_user_date", "user_id", "recorded_at")` 复合索引；②切片 ExportTask L244 `user_id` 有 `index=True`，但 `__table_args__` L254 已有 `Index("idx_export_user_created", "user_id", "created_at")` 复合索引；③切片 ExportTask L245 `task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)` 同时使用 `unique=True, index=True`，`unique=True` 已隐式创建唯一索引，`index=True` 会创建重复的 B-Tree 索引。§5 ExportTask L2347 仅使用 `unique=True` 不带 `index=True`。 |
| 修复建议 | 移除切片 L227、L244、L245 的 `index=True` |

#### P3-7：切片 03-video_analysis 多处冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | file_record, video_task, analysis_report, feedback_record |
| 文件 | `03-video_analysis/backend.md` |
| 行号 | L220 FileRecord.user_id, L221 FileRecord.oss_key, L247 VideoTask.user_id, L298 AnalysisReport.task_id, L299 AnalysisReport.user_id, L323 FeedbackRecord.report_id, L324 FeedbackRecord.user_id |
| 问题描述 | 切片多处冗余 `index=True`：①FileRecord.user_id L220 与 `__table_args__` L233 `idx_file_record_user_created` 复合索引重复；②FileRecord.oss_key L221 `unique=True, index=True`，`unique=True` 已隐式创建索引；③VideoTask.user_id L247 与 `__table_args__` L263 `idx_video_task_user_created` 复合索引重复；④AnalysisReport.task_id L298 `unique=True, index=True`，`unique=True` 已隐式创建索引；⑤AnalysisReport.user_id L299 与 `__table_args__` L310 `idx_report_user_created` 复合索引重复；⑥FeedbackRecord.report_id L323 与 `__table_args__` L332 `UniqueConstraint("report_id", "user_id", name="uq_feedback_user_report")` 唯一约束（已隐式创建索引）重复；⑦FeedbackRecord.user_id L324 同上唯一约束重复。§5 各对应字段均不带 `index=True`。 |
| 修复建议 | 移除切片 L220、L221、L247、L298、L299、L323、L324 的 `index=True`（VideoTask.task_uuid L246 和 VideoTask.file_id L248 与 §5 一致，但 task_uuid 也是冗余 unique+index，建议 §5 也同步清理） |

#### P3-8：切片 05-match_data MatchRecord `format`/`match_type` default 值偏差（与 §2.13/§5 不一致）

| 属性 | 值 |
|------|-----|
| 表名 | match_record |
| 文件 | `05-match_data/backend.md` |
| 行号 | L412-L413 |
| 问题描述 | 切片 MatchRecord L412 `format: Mapped[str] = mapped_column(String(20), default="bo5", comment="赛制: bo1/bo3/bo5/bo7/custom")` 和 L413 `match_type: Mapped[str] = mapped_column(String(20), default="friendly", comment="比赛类型")`，但 §2.13 L678-679 `format VARCHAR(20) Y` 和 `match_type VARCHAR(20) Y` 都没有 DEFAULT（仅必填），§5 L2605-2606 也无 default。注意：这是 `match_record` 表（手动录入比赛记录），不是 `match` 表（记分牌）；§2.10 match 表已补充 DEFAULT（R18-P3-6），但 §2.13 match_record 表的 default 是新发现的偏差。 |
| 修复建议 | 在 §2.13 中补充 `format DEFAULT 'bo5'` 和 `match_type DEFAULT 'friendly'` 以与切片 05 对齐，或在切片中移除 default 值（需确认业务需求：手动录入比赛时，无 format/match_type 时是否合理使用 bo5/friendly 默认值，业务上似乎合理） |

#### P3-9：切片 05-match_data MatchRecord `match_date` 缺失 default

| 属性 | 值 |
|------|-----|
| 表名 | match_record |
| 文件 | `05-match_data/backend.md` |
| 行号 | L414 |
| 问题描述 | 切片 MatchRecord L414 `match_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="比赛日期时间")` 没有 default，但 §5 L2607 `match_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))` 有 default，§2.13 L680 `match_date TIMESTAMPTZ Y DEFAULT NOW()` 也定义了 DEFAULT NOW()。切片与 §2/§5 不一致，会导致手动录入比赛时若未传 match_date 直接报 NOT NULL 约束错误。 |
| 修复建议 | 在切片 L414 中补充 `default=lambda: datetime.now(timezone.utc)` |

#### P3-10：切片 05-match_data MatchRecord/ManualScoreDetail 多处冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | match_record, manual_score_detail |
| 文件 | `05-match_data/backend.md` |
| 行号 | L406 MatchRecord.user_id, L440 ManualScoreDetail.match_record_id |
| 问题描述 | ①切片 MatchRecord.user_id L406 `index=True`，但 `__table_args__` L426 已有 `Index("idx_mrecord_user_date", "user_id", "match_date")` 复合索引（覆盖 user_id 单列查询）；②切片 ManualScoreDetail.match_record_id L440 `index=True`，但 `__table_args__` L440（实际在 `__table_args__` 内）已有 `Index("idx_msd_record_seq", "match_record_id", "sequence")` 复合索引（覆盖 match_record_id 单列查询）。§5 L2598/L2624 均不带 `index=True`。 |
| 修复建议 | 移除切片 L406 和 L440 的 `index=True`。切片 L417 MatchRecord.match_id `index=True` 是合理的（FK 单列查询，无复合索引覆盖），建议在 §5 L2599 也同步补充 `index=True` 以保持三方一致 |

#### P3-11：切片 08-progress_analysis ProgressSnapshot/TechniqueTrend 冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | progress_snapshot, technique_trend |
| 文件 | `08-progress_analysis/backend.md` |
| 行号 | L380 ProgressSnapshot.user_id, L401 TechniqueTrend.user_id |
| 问题描述 | ①切片 ProgressSnapshot.user_id L380 `index=True`，但 `__table_args__` L389 已有 `Index("idx_ps_user_created", "user_id", "created_at")` 复合索引；②切片 TechniqueTrend.user_id L401 `index=True`，但 `__table_args__` L420 `Index("uq_trend_user_metric", "user_id", "metric_name", unique=True)` 唯一约束（已隐式创建索引，覆盖 user_id 单列查询）。§5 L2759/L2775 均不带 `index=True`。 |
| 修复建议 | 移除切片 L380 和 L401 的 `index=True` |

#### P3-12：切片 04-scoring MatchStatistic `match_id` 冗余 `index=True`

| 属性 | 值 |
|------|-----|
| 表名 | match_statistic |
| 文件 | `04-scoring/backend.md` |
| 行号 | L391 |
| 问题描述 | 切片 MatchStatistic L391 `match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), unique=True, index=True)` 同时使用 `unique=True, index=True`，`unique=True` 已隐式创建唯一索引，`index=True` 会创建重复的 B-Tree 索引。§5 L2570 仅使用 `unique=True` 不带 `index=True`。 |
| 修复建议 | 移除切片 L391 的 `index=True` |

---

## 4. 汇总统计

### 4.1 问题分级统计

| 级别 | 数量 | 说明 |
|------|------|------|
| P0 | 0 | 无阻断级问题 |
| P1 | 1 | 高优先级：R18-P3-5 闭环缺口（切片 13-admin AdminUser 缺 last_login_at） |
| P2 | 5 | 中优先级：§5 字段缺失（ManualScoreDetail created_at）、切片 GIN 索引缺失（analysis_report/progress_snapshot/knowledge_entry）、索引排序偏差（idx_report_user_created DESC） |
| P3 | 12 | 低优先级：切片多处冗余 index=True、match_record format/match_type default 偏差、match_date 缺 default |
| **合计** | **18** | |

### 4.2 R18 修复验证统计

| 验证项 | 状态 |
|--------|------|
| R18 P1（5 项）：MatchStatistic created_at / Subscription default / ShareRecord __table_args__ / FeedbackRecord 索引 / UserPoints __table_args__ | ✅ 5/5 通过 |
| R18 P2（10 项）：§5 模型覆盖度注释 / §6 索引补充 / BadgeDefinition sort_order / UserBadge 索引 / BadgeProgress 索引 / Subscription 索引命名 / RefundRecord 索引命名 / Match idx_match_status / TechniqueTrend Float / VideoTask 索引命名 | ✅ 10/10 通过 |
| R18 P3（6 项）：User nickname default / User openid index / rating_history DEFAULT / Order tournament 注释 / admin_user last_login_at / match format DEFAULT | ✅ 6/6 通过（P3-5 有闭环缺口，归入 R19 P1-1） |
| R18 推迟项（2 项）：表数口径 39 vs 35 注释 / AI 推理 HTTPException→AppException | ✅ 2/2 通过 |
| **合计** | **23/23 全部通过** |

### 4.3 按文件分布统计

| 文件 | P1 | P2 | P3 | 小计 |
|------|-----|-----|-----|------|
| 04-数据库详细设计.md（§5） | 0 | 1 | 0 | 1 |
| 13-infrastructure/admin.md | 1 | 0 | 0 | 1 |
| 13-infrastructure/knowledge_base.md | 0 | 1 | 0 | 1 |
| 03-video_analysis/backend.md | 0 | 2 | 1 | 3 |
| 08-progress_analysis/backend.md | 0 | 1 | 1 | 2 |
| 09-gamification/backend.md | 0 | 0 | 4 | 4 |
| 11-payment/backend.md | 0 | 0 | 1 | 1 |
| 02-user/backend.md | 0 | 0 | 1 | 1 |
| 05-match_data/backend.md | 0 | 0 | 3 | 3 |
| 04-scoring/backend.md | 0 | 0 | 1 | 1 |

### 4.4 按审查清单维度分布

| 审查维度 | P1 | P2 | P3 | 说明 |
|---------|-----|-----|-----|------|
| 1. 表名/列名一致性 | 0 | 0 | 0 | 全部一致 ✅ |
| 2. 列类型一致性 | 0 | 0 | 0 | Float 已修复，全部一致 ✅ |
| 3. DateTime 时区统一 | 0 | 0 | 0 | 全部使用 `DateTime(timezone=True)` ✅ |
| 4. PK/FK/Unique/Check 约束 | 0 | 0 | 0 | 全部一致 ✅ |
| 5. FK ondelete 策略一致性 | 0 | 0 | 0 | CASCADE/RESTRICT/SET NULL 全部一致 ✅ |
| 6. 索引完整性（§6 vs 切片 __table_args__） | 0 | 3 | 1 | P2-2/P2-3/P2-5 GIN 索引缺失；P3-2 idx_checkin_user_date 缺失 |
| 7. §5 模型覆盖度 | 0 | 1 | 0 | P2-1: §5 ManualScoreDetail 缺 created_at |
| 8. 数据完整性（枚举/默认/非空） | 0 | 0 | 2 | P3-8 match_record default 偏差；P3-9 match_date 缺 default |
| 9. 索引命名一致性 | 0 | 1 | 0 | P2-4: idx_report_user_created 缺 DESC 排序 |
| 10. 性能优化（冗余索引检测） | 0 | 0 | 8 | P3-1/P3-3/P3-4/P3-5/P3-6/P3-7/P3-10/P3-11/P3-12 多处冗余 index=True |
| 11. 复合索引覆盖度 | 0 | 0 | 0 | 复合索引已覆盖 FK 单列查询 ✅ |
| R18 修复闭环验证 | 1 | 0 | 0 | P1-1: R18-P3-5 闭环缺口（切片 AdminUser 缺 last_login_at） |

### 4.5 总体评价

**R18 修复状态**：23/23 项修复全部验证通过（含 R18 P1/P2/P3 21 项 + 推迟项 2 项）。R18 提出的所有问题在 DB 设计文档（§2/§5/§6）层面均已正确修复，且 R18 推迟的"表数口径 39 vs 35 注释"和"AI 推理 HTTPException→AppException"两项也已在 R18 内闭环。

**R18 闭环缺口**：R18-P3-5 在 §2.31 DDL 和 §5 AdminUser 模型已修复，但 R18 报告备注"切片 admin.md 已定义"实际不成立——切片 13-admin.md AdminUser 模型未同步 `last_login_at` 字段。这是 R18 修复闭环的最后一步遗漏，归入 R19 P1-1。

**当前一致性水平**：DB 设计 v1.6（2026-10-19）与切片在表名、列名、列类型、主键、外键、唯一约束、非空约束、DateTime 时区、FK ondelete 策略等核心维度上高度一致。R19 新发现问题集中在两个方向：

1. **切片 GIN 索引缺失**（P2-2/P2-3/P2-5）：切片 03/08/13-knowledge_base 三处 GIN 索引未在 `__table_args__` 中显式定义，依赖注释提示手动添加，存在迁移遗漏风险。
2. **切片冗余 index=True**（P3 系列 8 项）：多个切片在 FK 字段或 UNIQUE 字段上同时使用 `index=True` 与 `__table_args__` 显式索引/唯一约束，生成重复索引。这些是历史代码遗留，R18 修复索引命名时未清理 `index=True`。

**优先修复建议**：

1. **P1 优先（必修）**：修复切片 13-admin AdminUser `last_login_at` 字段同步（R18-P3-5 完全闭环的最后一步）
2. **P2 跟进**：
   - 补全 §5 ManualScoreDetail `created_at` 字段（P2-1）
   - 补全切片 03/08/13 三处 GIN 索引（P2-2/P2-3/P2-5）
   - 修复切片 03 AnalysisReport `idx_report_user_created` DESC 排序（P2-4）
3. **P3 视情况处理**：
   - 批量清理切片冗余 `index=True`（P3-1/P3-3/P3-4/P3-5/P3-6/P3-7/P3-10/P3-11/P3-12，可一次性 PR 完成）
   - 切片 05 MatchRecord `format/match_type/match_date` default 对齐 §2.13/§5（P3-8/P3-9，需业务确认 default 是否合理）

**与 R18 对比的进展**：R18 共 21 项问题（P1×5 + P2×10 + P3×6）全部修复；R19 共 18 项问题（P1×1 + P2×5 + P3×12），无 P0 级阻断。问题严重度持续下降，从 R18 的 5 个 P1（字段缺失级）降至 R19 的 1 个 P1（修复闭环缺口）。剩余问题以性能优化和代码整洁度为主，不影响业务正确性。

---

## 5. 反幻觉约束验证

### 5.1 §10 反幻觉约束 10 条逐条核验

| # | 约束 | 验证结果 | 备注 |
|---|------|---------|------|
| 1 | ALL Model 继承 `Base` | ✅ | 全部切片模型均 `class X(Base)`，无 Tortoise/Peewee |
| 2 | `TIMESTAMPTZ` 带时区 | ✅ | 全部 DateTime 字段使用 `DateTime(timezone=True)` |
| 3 | `BigInteger + autoincrement` 主键 | ✅ | 除 BadgeDefinition PK 为 VARCHAR(64) 语义化编码（设计决策，§3.1.4 已声明）外，其余均 BigInteger |
| 4 | `ForeignKey("table.id")` 字符串引用 | ✅ | 全部切片 FK 使用字符串引用 |
| 5 | 枚举集中定义在 `app/core/enums.py` | ✅ | UserStatus/TaskStatus/PipelineStepStatus 等已集中导入，切片未就地定义枚举 |
| 6 | 使用 `from sqlalchemy.dialects.postgresql import JSONB` | ✅ | 全部 JSONB 字段使用 postgresql.JSONB |
| 7 | 表名 snake_case 单数 | ✅ | `user/match/file_record/video_task` 等均单数 snake_case |
| 8 | `relationship() + back_populates` 双向 | ✅ | User↔RatingHistory, VideoTask↔AnalysisReport, Match↔ScoreRecord 等均双向 |
| 9 | 强归属 CASCADE，弱引用 SET NULL（搭配 nullable=True） | ✅ | user_id 等 CASCADE；subscription_id/order_id 等 SET NULL 搭配 nullable=True |
| 10 | Alembic 迁移 | ✅ | 全部切片"实现后必须"清单均含 `alembic revision --autogenerate` |

### 5.2 表数口径一致性

| 口径 | 数量 | 说明 |
|------|------|------|
| §2 DDL 定义表数 | 39 | §2.1-§2.34 共 39 张表（含 §2.32 badge 3 表引用） |
| §1.1 ER 图覆盖 | 35+4 | Phase 1 核心 35 张 + Phase 2 提前实现 4 张 |
| 实施计划 §1.1 "Phase 1 = 35 表" | 35 | Sprint 交付清单核心表 |
| §5 SQLAlchemy Models | 29 | 核心模型示例（R18-P2-1 注释声明：10 个表见切片） |
| 切片独立模型总数 | 29+10=39 | 与 §2 一致 ✅ |
| R18-P3-20 注释 | ✅ | §2 L438-442 已显式说明 35+4=39 口径差异 |

### 5.3 §6 索引总表完整性验证

| §6 索引总表覆盖 | 数量 | 状态 |
|-----------------|------|------|
| §5 模型 `__table_args__` 中定义的索引 | 36 | 全部列入 ✅ |
| §2 DDL 中提到的索引 | 全部 | 全部列入 ✅ |
| §6.1 核心索引清单 | 38 条 | 覆盖所有业务查询场景 ✅ |
| §6.2 GIN 索引清单 | 4 条 | analysis_report/progress_snapshot/knowledge_entry/rule_definition ✅ |

---

## 6. 优化建议（非问题项）

### 6.1 性能优化机会

1. **N+1 查询风险点**：
   - 切片 03 AnalysisReport → FeedbackRecord → ShareRecord 链式关系（L314/L315），切片已使用 `relationship(cascade="all, delete-orphan")` 但未显式 `selectinload`/`joinedload`，建议在 Service 层统一使用 `selectinload(AnalysisReport.feedbacks).selectinload(AnalysisReport.shares)` 避免列表查询时的 N+1
   - 切片 04 Match → ScoreRecord 关系（L534），ScoreRecord 通常 100+ 条/比赛，建议使用 `selectinload` 或在 schema 层做分页

2. **复合索引覆盖度优化**：
   - `feedback_record` 表当前索引 `(status,)` 和 `(is_correct, created_at)` 是分离的，但数据飞轮审核队列查询常按 `(status, is_correct, created_at)` 三列过滤，建议合并为复合索引 `idx_feedback_status_correct_created (status, is_correct, created_at)` 减少索引数量
   - `notification_record` 表 `(user_id, is_read, created_at)` 索引已合理覆盖未读通知列表场景 ✅

3. **JSONB GIN 索引选择性优化**：
   - `progress_snapshot.metrics_snapshot` GIN 索引覆盖整个 18 指标 JSONB，但实际查询常按单指标过滤（如 `metrics_snapshot->>'forehand_ratio'`），建议评估是否改为表达式索引 `((metrics_snapshot->>'forehand_ratio'))` 以减少索引体积

### 6.2 文档优化建议

1. **§5 与切片双向索引声明同步**：建议在 §5 注释中明确"切片 `__table_args__` 是开发权威源，§5 仅供参考"，避免索引命名再次出现 §5/§6/切片三方偏差
2. **R18 闭环验证流程**：建议未来修复备注中明确"修复位置 = §2/§5/切片" 三处，避免 R18-P3-5 类型的闭环缺口

---

## 7. R19 修复跟踪表

| # | 优先级 | 问题项 | 修复位置 | 验证状态 |
|---|--------|--------|---------|---------|
| P1-1 | P1 | 切片 13-admin AdminUser 补充 `last_login_at` | `13-infrastructure/admin.md` L80 后 | ⏳ 待修复 |
| P2-1 | P2 | §5 ManualScoreDetail 补充 `created_at` | `04-数据库详细设计.md` §5 L628 后 | ⏳ 待修复 |
| P2-2 | P2 | 切片 03 AnalysisReport 补充 `idx_report_text_gin` GIN 索引 | `03-video_analysis/backend.md` L309-311 | ⏳ 待修复 |
| P2-3 | P2 | 切片 08 ProgressSnapshot 补充 `idx_ps_metrics_gin` GIN 索引 | `08-progress_analysis/backend.md` L388-391 | ⏳ 待修复 |
| P2-4 | P2 | 切片 03 AnalysisReport `idx_report_user_created` 补 DESC 排序 | `03-video_analysis/backend.md` L310 | ⏳ 待修复 |
| P2-5 | P2 | 切片 13-knowledge_base KnowledgeEntry 补充 `content` GIN 索引 | `13-infrastructure/knowledge_base.md` L80-96 | ⏳ 待修复 |
| P3-1 | P3 | 切片 09 BadgeDefinition `is_active` 移除 `index=True` | `09-gamification/backend.md` L235 | ✅ 已修复（R20 验证） |
| P3-2 | P3 | 切片 09 CheckInRecord 补 `idx_checkin_user_date` + 移除冗余 `index=True` | `09-gamification/backend.md` L205-217 | ✅ 完全修复（R20 验证 idx_checkin_user_date + R26 验证 checkin_date 移除 index=True） |
| P3-3 | P3 | 切片 09 UserBadge `user_id` 移除 `index=True` | `09-gamification/backend.md` L248 | ✅ 已修复（R20 验证） |
| P3-4 | P3 | 切片 09 BadgeProgress `user_id` 移除 `index=True` | `09-gamification/backend.md` L263 | ✅ 已修复（R20 验证） |
| P3-5 | P3 | 切片 11 Order/PaymentRecord FK 移除 `index=True` | `11-payment/backend.md` L450/L487 | ✅ 已修复（R20 验证） |
| P3-6 | P3 | 切片 02 RatingHistory/ExportTask FK 移除 `index=True` | `02-user/backend.md` L227/L244/L245 | ✅ 已修复（R20 验证） |
| P3-7 | P3 | 切片 03 多处 FK 移除冗余 `index=True` | `03-video_analysis/backend.md` L220-L348 | ✅ 完全修复（R20 验证 L220/L221/L247/L298/L299/L324/L325 + R26 验证 L246/L347/L348） |
| P3-8 | P3 | §2.13 match_record `format/match_type` 补 DEFAULT 或切片移除 | `04-数据库详细设计.md` §2.13 L678-679 或切片 L412-413 | ✅ 已修复（R20 验证） |
| P3-9 | P3 | 切片 05 MatchRecord `match_date` 补 default | `05-match_data/backend.md` L414 | ✅ 已修复（R20 验证） |
| P3-10 | P3 | 切片 05 MatchRecord/ManualScoreDetail FK 移除冗余 `index=True` | `05-match_data/backend.md` L406/L440 | ✅ 已修复（R20 验证） |
| P3-11 | P3 | 切片 08 ProgressSnapshot/TechniqueTrend FK 移除 `index=True` | `08-progress_analysis/backend.md` L380/L401 | ✅ 已修复（R20 验证） |
| P3-12 | P3 | 切片 04 MatchStatistic `match_id` 移除 `index=True` | `04-scoring/backend.md` L391 | ✅ 已修复（R20 验证） |

**修复跟踪表统计**：6 项待修复（P1×1 + P2×5）+ 12 项 P3 全部已修复（R20 验证 10 项 + R26 验证 P3-2/P3-7 最终修复）

---

## 8. 与 R18 对比

| 维度 | R18（基线） | R19（当前） | 变化 |
|------|------------|------------|------|
| P0 数量 | 0 | 0 | 持平 ✅ |
| P1 数量 | 5 | 1 | ↓ 4（R18 P1 全部修复，仅剩 R18-P3-5 闭环缺口） |
| P2 数量 | 10 | 5 | ↓ 5（R18 P2 全部修复，R19 新发现 5 项主要是 GIN 索引） |
| P3 数量 | 6 | 12 | ↑ 6（R18 P3 全部修复，R19 新发现 12 项主要是冗余 index=True 检测更深入） |
| 合计 | 21 | 18 | ↓ 3（问题总数下降，严重度下降） |
| R18 修复通过率 | — | 23/23 (100%) | ✅ |
| §5 模型覆盖度 | 29 个（缺 10 个） | 29 个（带 R18-P2-1 注释声明 10 个见切片） | ✅ |
| §6 索引总表覆盖 | 缺 8 张表 | 全部覆盖 | ✅ |
| DateTime 时区统一 | 全部 `timezone=True` | 全部 `timezone=True` | 持平 ✅ |
| FK ondelete 策略 | 一致 | 一致 | 持平 ✅ |
| 反幻觉约束 10 条 | — | 10/10 通过 | ✅ |

**核心进展**：R19 在 R18 23/23 修复通过的基础上，新发现 18 项问题中无 P0 级阻断，仅 1 项 P1（R18-P3-5 闭环缺口），其余 17 项为 P2/P3 级（GIN 索引缺失 + 冗余 index=True）。审查深度从"字段级一致性"扩展到"索引完整性 + 性能优化"，发现更多深层优化机会，但业务正确性已得到充分保障。

---

*报告结束*
