# 第十七轮 DB 字段级一致性审查报告

> **审查维度**：DB 字段级一致性（§2 表定义 / §5 SQLAlchemy 模型 / §6 索引总表 / 切片 Model 四方对齐）
> **审查日期**：2026-10-16
> **审查代理**：第十七轮 DB 字段级审查代理
> **基线文档**：数据库详细设计 v1.6（`docs/04详细设计/04-数据库详细设计.md`，最后修改 2026-10-16 12:30）
> **切片文件**：9 份垂直切片 backend.md（02-user / 01-auth / 03-video_analysis / 04-scoring / 05-match_data / 09-gamification / 10-membership / 11-payment / 13-infrastructure/admin.md）
> **前序状态**：第十六轮新发现 2 项 P2 + 15 项 P3；本轮验证 R16 修复 + 深层 §5 系统性不同步排查

---

## 1. 审查范围

### 1.1 基线文件清单

| # | 文件路径 | 关键章节 |
|---|---------|---------|
| 1 | `docs/04详细设计/04-数据库详细设计.md` | §1 ER 图、§2 表定义（权威源）、§3 Phase 2-4 表定义、§4 枚举、§5 SQLAlchemy 模型、§6 索引总表 |
| 2 | `docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` | FileRecord / VideoTask / PipelineStep / AnalysisReport / FeedbackRecord / ShareRecord |
| 3 | `docs/06垂直模块前后端切片设计/04-scoring/backend.md` | Match / ScoreRecord / MatchStatistic |
| 4 | `docs/06垂直模块前后端切片设计/05-match_data/backend.md` | MatchRecord / ManualScoreDetail |
| 5 | `docs/06垂直模块前后端切片设计/09-gamification/backend.md` | UserPoints / CheckInRecord / BadgeDefinition / UserBadge / BadgeProgress |
| 6 | `docs/06垂直模块前后端切片设计/10-membership/backend.md` | MembershipTier / Subscription |
| 7 | `docs/06垂直模块前后端切片设计/11-payment/backend.md` | Order / PaymentRecord / RefundRecord |
| 8 | `docs/06垂直模块前后端切片设计/02-user/backend.md` | User / RatingHistory / ExportTask |
| 9 | `docs/06垂直模块前后端切片设计/01-auth/backend.md` | ConsentLog |
| 10 | `docs/06垂直模块前后端切片设计/13-infrastructure/admin.md` | AdminUser / AuditLog / SystemConfig |

### 1.2 审查清单（21 项）

| # | 类别 | 检查项 |
|---|------|--------|
| 1 | R16 修复验证 | P2-3：DB §5.5 PaymentRecord 补 paid_at 字段 |
| 2 | R16 修复验证 | P2-4：DB §5.5 Subscription 补 payment_method 和 cancelled_at 字段 |
| 3 | R16 修复验证 | P3-1：§4.1 UserStatus 补 pending_deletion |
| 4 | R16 修复验证 | P3-2：§4.1 SubscriptionStatus 补 cancelled |
| 5 | R16 修复验证 | P3-3：§5.5 Subscription status 注释补 cancelled |
| 6 | R16 修复验证 | P3-4：VideoTask 索引名称三方一致 |
| 7 | R16 修复验证 | P3-5：Subscription 索引名称切片与 DB 一致 |
| 8 | R16 修复验证 | P3-6：FileRecord 索引三方一致 |
| 9 | R16 修复验证 | P3-7：badge 表 FK ondelete 策略一致 |
| 10 | R16 修复验证 | P3-8：audit_log 表 FK ondelete 策略一致 |
| 11 | R16 修复验证 | P3-9：§5.2 FileRecord 补 updated_at |
| 12 | R16 修复验证 | P3-10：§5 各模型补 §6 索引总表索引 |
| 13 | R16 修复验证 | P3-11：§5 补 RefundRecord 模型示例 |
| 14 | R16 修复验证 | P3-12：ER 图 VideoTask 补 v1.4 新增字段 |
| 15 | R16 修复验证 | P3-13：ER 图 AnalysisReport 补缺失字段 |
| 16 | R16 修复验证 | P3-14：§5.2 AnalysisReport JSONB 字段补默认值 |
| 17 | R16 修复验证 | P3-15：FeedbackRecord UniqueConstraint 列顺序一致 |
| 18 | R16 修复验证 | §5 权威源注释已添加 |
| 19 | 深层检查 | §5 模型代码与 §2 表定义逐表字段对齐（系统性不同步排查）|
| 20 | 深层检查 | §5 模型 __table_args__ 与 §6 索引总表逐项对齐 |
| 21 | 深层检查 | ER 图 vs §2 表定义字段一致性 |

---

## 2. 第十六轮修复验证（第 1-18 项）

### 2.1 P2-3：§5.5 PaymentRecord 补 paid_at ⚠️ 已应用但引入回归

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.5 L2606
- **修复内容**：`paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # R16-P2-3: 补充 paid_at（§2.19 已定义）`
- **验证结果**：字段已添加 ✅，**但 nullable 属性与权威源不一致** ❌
  - §2.19 表定义（L767）：`paid_at | TIMESTAMPTZ | Y | — | 支付时间`（必填 Y）
  - 切片 `11-payment/backend.md`（L495）：`paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))`（非 Optional → 非空）
  - §5.5 当前实现：`Mapped[datetime | None]` + `nullable=True`（可空）
- **结论**：⚠️ **修复有回归** — 见 §3.1 R17-P2-1

### 2.2 P2-4：§5.5 Subscription 补 payment_method 和 cancelled_at ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.5 L2556、L2562
- **验证结果**：
  - L2556：`payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # R16-P2-4: 补充 payment_method（§2.17 已定义）` ✅
  - L2562：`cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # R16-P2-4: 补充 cancelled_at（§2.17 已定义）` ✅
  - 与 §2.17（L730、L734）和切片 `10-membership/backend.md`（L234、L235）完全一致
- **结论**：✅ 无回归

### 2.3 P3-1：§4.1 UserStatus 补 pending_deletion ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §4.1 L2037
- **验证结果**：`pending_deletion = "pending_deletion"  # R16-P3: 补充 pending_deletion（§2.1 已定义）` ✅
  - 与 §2.1（L447）`active/pending_deletion/deleted` 一致
- **结论**：✅ 无回归

### 2.4 P3-2：§4.1 SubscriptionStatus 补 cancelled ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §4.1 L2128
- **验证结果**：`cancelled = "cancelled"  # R16-P3: 补充 cancelled（§2.17 已定义）` ✅
  - 与 §2.17（L729）`active/expiring_soon/expired/grace_period/cancelled/closed` 一致
- **结论**：✅ 无回归

### 2.5 P3-3：§5.5 Subscription status 注释补 cancelled ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.5 L2555
- **验证结果**：`status: Mapped[str] = mapped_column(String(20))  # active/expiring_soon/expired/grace_period/cancelled/closed` ✅
- **结论**：✅ 无回归

### 2.6 P3-4：VideoTask 索引名称三方一致 ❌ 未修复

- **涉及文件**：DB §5.2 L2336-2337、§6 L2710-2711、切片 `03-video_analysis/backend.md` L261-263
- **当前状态**（仍未对齐）：

| 索引用途 | DB §5.2 模型 | DB §6 索引总表 | 切片 __table_args__ |
|---------|-------------|--------------|-------------------|
| (user_id, created_at) | `idx_video_task_user_created` | `idx_vtask_user_created` | `idx_video_task_user_created` |
| (status, created_at) | `idx_video_task_status` | `idx_vtask_status` | `idx_video_task_status_created` |

- **结论**：❌ **未修复** — DB §5.2 与 §6 索引名称不一致；切片与 §5.2 在第二个索引名上不一致。延续至本轮 P3-17

### 2.7 P3-5：Subscription 索引名称切片与 DB 一致 ❌ 未修复（切片侧）

- **涉及文件**：切片 `10-membership/backend.md` L242、DB §5.5 L2567-2568、§6 L2721-2722
- **当前状态**：
  - DB §5.5（L2567-2568）：`idx_sub_status_expire`, `idx_sub_user_status` ✅
  - DB §6（L2721-2722）：`idx_sub_status_expire`, `idx_sub_user_status` ✅
  - **DB §5.5 与 §6 已对齐** ✅
  - 切片（L242）：仍使用 `idx_subscription_user_status`（与 DB 不一致）❌
- **结论**：❌ **切片侧未修复** — 切片需统一为 `idx_sub_user_status`。延续至本轮 P3-16

### 2.8 P3-6：FileRecord 索引三方一致 ❌ 未修复

- **涉及文件**：DB §5.2 L2305-2308、§6 L2726-2728、切片 `03-video_analysis/backend.md` L232-235
- **当前状态**：

| 索引 | DB §5.2 | DB §6 | 切片 |
|------|---------|-------|------|
| (user_id, created_at) | `idx_file_record_user_created` ✅ | `idx_file_record_user_created` ✅ | `idx_file_record_user_created` ✅ |
| (file_type) | `idx_file_record_type` ✅ | `idx_file_record_type` ✅ | ❌ 缺失 |
| (status, created_at) | ❌ 缺失 | `idx_file_status_created` | `idx_file_record_status_created`（名称不同）|

- **结论**：❌ **未修复** — 三方仍不一致。延续至本轮 P3-11（切片侧）、P3-5（§5.2 侧）

### 2.9 P3-7：badge 表 FK ondelete 策略一致 ⚠️ 已应用但引入新不一致

- **涉及文件**：DB §3.1.5 L1206、§3.1.6 L1227、切片 `09-gamification/backend.md` L244、L258
- **当前状态**：

| 表 | DB §3.1 表定义 | 切片模型 |
|----|--------------|---------|
| user_badge.badge_id | `FK → badge_definition(id), NOT NULL, CASCADE`（R16 已补充） | `ForeignKey("badge_definition.id", ondelete="RESTRICT")` |
| badge_progress.badge_id | `FK → badge_definition(id), NOT NULL, CASCADE`（R16 已补充） | `ForeignKey("badge_definition.id", ondelete="RESTRICT")` |

- **结论**：⚠️ **DB 与切片策略相反** — DB §3.1 选择 CASCADE，切片选择 RESTRICT，引用完整性语义不同。见 §3.2 R17-P1-1

### 2.10 P3-8：audit_log 表 FK ondelete 策略一致 ❌ admin_id 未修复

- **涉及文件**：DB §2.31 L1005、L1010、切片 `13-infrastructure/admin.md` L88、L97
- **当前状态**：

| 字段 | DB §2.31 表定义 | 切片模型 |
|------|--------------|---------|
| admin_id | `FK→admin_user.id, SET NULL`（与 NOT NULL 矛盾）| `ForeignKey("admin_user.id", ondelete="RESTRICT"), nullable=False` ✅ |
| user_id | `FK→user.id, SET NULL`（与 nullable 一致）✅ | `ForeignKey("user.id", ondelete="SET NULL"), nullable=True` ✅ |

- **结论**：❌ **admin_id 侧未修复** — DB §2.31 admin_id 标记为 `Y`（NOT NULL）但使用 `SET NULL`，语义矛盾；切片正确使用 RESTRICT。延续至本轮 P3-7

### 2.11 P3-9：§5.2 FileRecord 补 updated_at ❌ 未修复

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.2 L2289-2308
- **当前状态**：§5.2 FileRecord 模型仍缺少 `updated_at` 字段
  - §2.4 表定义（L506）：`updated_at | TIMESTAMPTZ | Y | DEFAULT NOW() | 更新时间 | P2 补充：切片已定义`
  - 切片 `03-video_analysis/backend.md`（L229）：`updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))`
  - §5.2（L2293-2308）：仍无 updated_at ❌
- **结论**：❌ **未修复** — 延续至本轮 P3-4

### 2.12 P3-10：§5 各模型补 §6 索引总表索引 ❌ 多数未修复

- **当前状态**：

| 模型 | §5 位置 | §6 列出的索引 | §5 是否包含 | 切片是否包含 |
|------|---------|------------|-----------|------------|
| AnalysisReport | §5.2 L2362-2380 | `idx_report_user_created` + GIN `idx_report_text_gin` | ❌ 无 __table_args__ | `idx_analysis_report_user_created`（名称不同）|
| MatchStatistic | §5.3 L2468-2477 | `idx_mstat_match` | ❌ 无 __table_args__ | 无（用 unique=True 自动生成）|
| ShareRecord | §5.2 L2383-2397 | `idx_share_user_created` | ❌ 无 __table_args__ | 无（用 index=True 内联）|
| FeedbackRecord | §5.6 L2666-2683 | `idx_feedback_status`, `idx_feedback_correct_created` | ❌ 仅 UniqueConstraint | ❌ 无 |
| ProgressSnapshot | §5.6 L2630-2642 | `idx_ps_metrics_gin` | ❌ 仅有 `idx_ps_user_created` | 无（用 unique=True 自动生成）|
| UserPoints | §5 缺失 | `idx_points_user_updated` | ❌ §5 无 UserPoints 模型 | 切片有模型但无 __table_args__ |

- **结论**：❌ **多数未修复** — 延续至本轮 P3-2/P3-6/P3-8/P3-9/P3-10

### 2.13 P3-11：§5 补 RefundRecord 模型示例 ❌ 未修复

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5
- **当前状态**：§5.5 仅包含 Subscription + Order + PaymentRecord 三个模型，仍无 RefundRecord 模型代码
  - §2.19b（L772-790）已定义 refund_record 表
  - 切片 `11-payment/backend.md`（L505-524）已实现 RefundRecord 模型
- **结论**：❌ **未修复** — 延续至本轮 P3-19

### 2.14 P3-12：ER 图 VideoTask 补 v1.4 新增字段 ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §1.1 L88-105
- **验证结果**：ER 图 VideoTask 实体现包含 16 个字段（id/user_id/file_id/oss_key/duration_sec/status/current_step/task_uuid/total_steps/step_name/progress/estimated_remaining_seconds/error_message/retry_count/created_at/completed_at），覆盖 §2.5 表定义全部字段 ✅
- **结论**：✅ 无回归

### 2.15 P3-13：ER 图 AnalysisReport 补缺失字段 ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §1.1 L117-129
- **验证结果**：ER 图 AnalysisReport 实体现包含 11 个字段，含 `is_llm_generated`、`is_anonymized`、`report_images` ✅
- **结论**：✅ 无回归

### 2.16 P3-14：§5.2 AnalysisReport JSONB 字段补默认值 ❌ 未修复

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.2 L2369-2370
- **当前状态**：
  - L2369：`result_data: Mapped[dict] = mapped_column(JSONB)` — 无 `default`
  - L2370：`report_text: Mapped[dict] = mapped_column(JSONB)` — 无 `default`
  - 类型标注为 `Mapped[dict]`（非 Optional），但无默认值，ORM 与 DB 层语义不一致
- **对比切片**：切片 `03-video_analysis/backend.md`（L301-302）使用 `nullable=False`，亦无 default
- **结论**：❌ **未修复** — 延续至本轮 P3-3

### 2.17 P3-15：FeedbackRecord UniqueConstraint 列顺序一致 ❌ 未修复

- **涉及文件**：DB §5.6 L2682、切片 `03-video_analysis/backend.md` L331
- **当前状态**：
  - DB §5.6：`UniqueConstraint("user_id", "report_id", name="uq_feedback_user_report")`
  - 切片：`UniqueConstraint("report_id", "user_id", name="uq_feedback_user_report")`
  - 列顺序仍不同（约束名相同，UNIQUE 语义等价，但索引前缀不同）
- **结论**：❌ **未修复** — 延续至本轮 P3-18

### 2.18 §5 权威源注释 ✅

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5 前置注释 L2231
- **验证结果**：`> **R16-P3 注释**：§2 表定义为权威源，§5 代码示例仅供参考。索引命名以 §6 索引总表为权威源，§5 Model 的 __table_args__ 中的索引命名可能与之存在差异，实际开发以 §2/§6 定义为准。` ✅
- **结论**：✅ 注释已添加

### 2.19 R16 修复验证汇总

| 修复项 | 验证结果 |
|--------|---------|
| P2-3 PaymentRecord paid_at | ⚠️ 字段已补，但 nullable 属性回归（详见 R17-P2-1）|
| P2-4 Subscription payment_method + cancelled_at | ✅ 完全一致 |
| P3-1 UserStatus pending_deletion | ✅ 无回归 |
| P3-2 SubscriptionStatus cancelled | ✅ 无回归 |
| P3-3 §5.5 Subscription status 注释 | ✅ 无回归 |
| P3-4 VideoTask 索引名称 | ❌ 未修复 |
| P3-5 Subscription 索引名称 | ⚠️ DB 内部已对齐，切片侧未修复 |
| P3-6 FileRecord 索引 | ❌ 未修复 |
| P3-7 badge FK ondelete | ⚠️ 已补 CASCADE，但与切片 RESTRICT 矛盾（详见 R17-P1-1）|
| P3-8 audit_log FK ondelete | ❌ admin_id 未修复（详见 R17-P2-2）|
| P3-9 §5.2 FileRecord updated_at | ❌ 未修复 |
| P3-10 §5 补 §6 索引 | ❌ 多数未修复 |
| P3-11 §5 补 RefundRecord | ❌ 未修复 |
| P3-12 ER 图 VideoTask | ✅ 无回归 |
| P3-13 ER 图 AnalysisReport | ✅ 无回归 |
| P3-14 AnalysisReport JSONB 默认值 | ❌ 未修复 |
| P3-15 FeedbackRecord UniqueConstraint 列顺序 | ❌ 未修复 |
| §5 权威源注释 | ✅ 已添加 |

**统计**：R16 修复 18 项中，✅ 完全修复 7 项、⚠️ 引入新问题 2 项、❌ 未修复 9 项

---

## 3. 本轮新发现（按 P0/P1/P2/P3 分级）

### 3.1 P0 级发现（0 项）

无阻断性问题。✅

### 3.2 P1 级发现（1 项）

#### R17-P1-1：badge 表 FK ondelete 策略 DB §3.1 与切片相反（R16 P3-7 修复引入）

- **涉及文件**：
  - DB `04-数据库详细设计.md` §3.1.5 L1206、§3.1.6 L1227
  - 切片 `09-gamification/backend.md` L244、L258
- **问题描述**：R16 修复为 badge 表 FK 补充了 ondelete 策略，但 DB §3.1 选择 `CASCADE`，切片 `09-gamification` 选择 `RESTRICT`：

| 表 | DB §3.1 表定义 | 切片模型 |
|----|--------------|---------|
| user_badge.badge_id | `FK → badge_definition(id), NOT NULL, CASCADE` | `ForeignKey("badge_definition.id", ondelete="RESTRICT")` |
| badge_progress.badge_id | `FK → badge_definition(id), NOT NULL, CASCADE` | `ForeignKey("badge_definition.id", ondelete="RESTRICT")` |

- **影响**：引用完整性语义相反
  - DB §3.1 选择 CASCADE：删除 badge_definition 时级联删除所有 user_badge / badge_progress 记录，**历史已获得徽章会丢失**
  - 切片选择 RESTRICT：删除 badge_definition 时若存在引用则拒绝删除，**保留历史徽章记录**
- **建议**：统一为 `RESTRICT`（与切片一致）— 徽章定义是运营资产，删除前应先迁移用户引用；CASCADE 会导致已发徽章静默消失，违反审计合规
- **修复位置**：DB §3.1.5 L1206、§3.1.6 L1227：将 `CASCADE` 改为 `RESTRICT`

### 3.3 P2 级发现（2 项）

#### R17-P2-1：§5.5 PaymentRecord.paid_at nullable 属性与权威源矛盾（R16 P2-3 修复引入）

- **涉及文件**：`docs/04详细设计/04-数据库详细设计.md` §5.5 L2606
- **问题描述**：R16 修复为 §5.5 补充了 paid_at 字段，但设置为 `nullable=True`，与 §2 表定义和切片均不一致：

| 来源 | 定义 | nullable |
|------|------|---------|
| §2.19 表定义（L767） | `paid_at \| TIMESTAMPTZ \| Y \| — \| 支付时间` | 必填（Y）|
| 切片 `11-payment/backend.md`（L495） | `paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))` | 非空（非 Optional）|
| §5.5 模型（L2606） | `paid_at: Mapped[datetime \| None] = mapped_column(DateTime(timezone=True), nullable=True)` | 可空 ❌ |

- **影响**：开发者参照 §5.5 实现时，PaymentRecord 创建可不填 paid_at，但 §2.19 与切片均要求必填。支付完成后无 paid_at 时间戳将导致财务对账异常
- **建议**：将 §5.5 改为 `paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))`（移除 `| None` 和 `nullable=True`），与 §2.19 和切片一致
- **修复位置**：DB §5.5 L2606

#### R17-P2-2：§2.31 audit_log.admin_id FK ondelete=SET NULL 与 NOT NULL 矛盾（R16 P3-8 部分未修复）

- **涉及文件**：`docs/04详细设计/04-数据库详细设计.md` §2.31 L1005
- **问题描述**：DB §2.31 audit_log 表定义中：

| 字段 | 必填 | FK 策略 | 矛盾 |
|------|------|---------|------|
| admin_id | Y（NOT NULL）| `FK→admin_user.id, SET NULL` | ❌ SET NULL 与 NOT NULL 矛盾 |
| user_id | N（NULL）| `FK→user.id, SET NULL` | ✅ 一致 |

- **切片对比**：`13-infrastructure/admin.md` L88：`admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("admin_user.id", ondelete="RESTRICT"), nullable=False)` — 切片正确使用 RESTRICT + NOT NULL
- **影响**：SET NULL 在 NOT NULL 列上无法执行（PostgreSQL 会报错），Alembic 生成的迁移与表定义语义矛盾
- **建议**：将 §2.31 admin_id 改为 `FK→admin_user.id, RESTRICT`（与切片一致）— 审计日志为合规资产，管理员删除时应拒绝（RESTRICT）而非置空
- **修复位置**：DB §2.31 L1005

### 3.4 P3 级发现（20 项）

| # | 编号 | 文件 | 行号 | 简述 | 优先 |
|---|------|------|------|------|------|
| 1 | R17-P3-1 | DB §5.3 Match __table_args__ | L2441-2443 | Match 索引 `idx_match_user_status` (user_id, status) 与 §2.10/切片均不一致 | 中 |
| 2 | R17-P3-2 | DB §5.2 AnalysisReport | L2362-2380 | §5.2 无 __table_args__，缺 §6 `idx_report_user_created` + GIN 索引 | 中 |
| 3 | R17-P3-3 | DB §5.2 AnalysisReport | L2369-2370 | result_data/report_text 无 default（R16 P3-14 延续）| 低 |
| 4 | R17-P3-4 | DB §5.2 FileRecord | L2289-2308 | 缺 updated_at 字段（R16 P3-9 延续）| 低 |
| 5 | R17-P3-5 | DB §5.2 FileRecord __table_args__ | L2305-2308 | 缺 §6 `idx_file_status_created`（R16 P3-6 延续）| 中 |
| 6 | R17-P3-6 | DB §5.2 ShareRecord | L2383-2397 | §5.2 无 __table_args__，缺 §6 `idx_share_user_created` | 中 |
| 7 | R17-P3-7 | DB §5.3 MatchStatistic | L2468-2477 | §5.3 无 __table_args__，缺 §6 `idx_mstat_match` | 中 |
| 8 | R17-P3-8 | DB §5.6 FeedbackRecord __table_args__ | L2681-2683 | 缺 §6 `idx_feedback_status` + `idx_feedback_correct_created` | 中 |
| 9 | R17-P3-9 | DB §5.6 ProgressSnapshot __table_args__ | L2640-2642 | 缺 §6 `idx_ps_metrics_gin` GIN 索引 | 中 |
| 10 | R17-P3-10 | DB §5 | — | §5 缺 UserPoints / CheckInRecord / RefundRecord / ConsentLog / AdminUser / AuditLog / SystemConfig / ExportTask 模型 | 中 |
| 11 | R17-P3-11 | 切片 `03-video_analysis` FileRecord __table_args__ | L232-235 | 切片 `idx_file_record_status_created` 与 §6 `idx_file_status_created` 名称不一致 + 缺 `idx_file_record_type` | 中 |
| 12 | R17-P3-12 | DB §6 | L2736 | §6 缺 audit_log `idx_audit_user_created` 和 `idx_audit_target`（切片有）| 低 |
| 13 | R17-P3-13 | DB §2.34 consent_log 索引 | L1095 | §2.34 第二索引 `(consent_type, withdrawn_at)` 与切片 `idx_consent_user_type` (user_id, consent_type) 列不同 | 中 |
| 14 | R17-P3-14 | 切片 `09-gamification` BadgeDefinition __table_args__ | L233-235 | 切片缺 §3.1.4 `idx_badge_definition_active`（用 index=True 内联代替）| 低 |
| 15 | R17-P3-15 | 切片 `05-match_data` MatchRecord __table_args__ | L426 | 切片 `idx_match_record_user_date` 与 §5.4/§6 `idx_mrecord_user_date` 名称不一致 | 低 |
| 16 | R17-P3-16 | 切片 `10-membership` Subscription __table_args__ | L242 | 切片 `idx_subscription_user_status` 与 DB `idx_sub_user_status` 不一致（R16 P3-5 延续）| 中 |
| 17 | R17-P3-17 | DB §5.2 VideoTask __table_args__ + §6 | L2337 / L2711 | 第二索引名三方不一致：§5.2 `idx_video_task_status` / §6 `idx_vtask_status` / 切片 `idx_video_task_status_created`（R16 P3-4 延续）| 中 |
| 18 | R17-P3-18 | DB §5.6 FeedbackRecord UniqueConstraint | L2682 | 列顺序 `(user_id, report_id)` 与切片 `(report_id, user_id)` 不一致（R16 P3-15 延续）| 低 |
| 19 | R17-P3-19 | DB §5 | — | §5 缺 RefundRecord 模型代码示例（R16 P3-11 延续）| 低 |
| 20 | R17-P3-20 | DB §5.2 AnalysisReport __table_args__ | L2362-2380 | 切片 `idx_analysis_report_user_created` 与 §6 `idx_report_user_created` 名称不一致 | 低 |

### P3 详细说明

#### R17-P3-1：DB §5.3 Match __table_args__ 索引与 §2.10/切片均不一致

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.3 L2441-2443
- **问题描述**：

| 来源 | 索引名 | 字段 |
|------|-------|------|
| §2.10 表定义（L632） | — | `(user_id, created_at DESC)`, `(status)` — 2 个索引 |
| DB §5.3 模型（L2442） | `idx_match_user_status` | (user_id, status) — 1 个，与 §2.10 两个都不匹配 |
| 切片 `04-scoring/backend.md`（L351） | `idx_match_user_created` | (user_id, created_at) — 1 个，匹配 §2.10 第一个 |
| §6 索引总表 | — | 未列出 match 表索引 |

- **影响**：§5.3 模型代码的索引既不匹配 §2.10 表定义，也不匹配切片实现，开发者参照 §5.3 时索引设计错误
- **建议**：§5.3 改为 `idx_match_user_created` (user_id, created_at) + `idx_match_status` (status)，与 §2.10 对齐

#### R17-P3-2：DB §5.2 AnalysisReport 缺 __table_args__ 与 §6 索引

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.2 L2362-2380
- **问题描述**：§5.2 AnalysisReport 模型未定义 __table_args__，§6 索引总表列出的两个索引均未在模型中实现：
  - §6 L2712：`idx_report_user_created` (user_id, created_at DESC) — B-Tree，用户报告列表
  - §6 L2713：`idx_report_text_gin` GIN(to_tsvector('simple', report_text::text)) — 全文搜索
- **影响**：§5.2 模型代码与 §6 索引总表不同步，开发者可能遗漏全文搜索索引

#### R17-P3-5：DB §5.2 FileRecord __table_args__ 缺 §6 idx_file_status_created

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.2 L2305-2308
- **问题描述**：§5.2 FileRecord __table_args__ 仅含 2 个索引，§6 列出 3 个：

| §5.2 现有 | §6 列出 | 状态 |
|----------|---------|------|
| `idx_file_record_user_created` | `idx_file_record_user_created` | ✅ 一致 |
| `idx_file_record_type` | `idx_file_record_type` | ✅ 一致 |
| — | `idx_file_status_created` (status, created_at) | ❌ §5.2 缺失 |

#### R17-P3-6：DB §5.2 ShareRecord 缺 __table_args__

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.2 L2383-2397
- **问题描述**：§5.2 ShareRecord 模型仅用内联 `index=True`（在 report_id/user_id/share_token 上），未定义 __table_args__。§6 L2732 列出 `idx_share_user_created` (user_id, created_at DESC) — 未在 §5.2 实现
- **影响**：缺少复合索引 `(user_id, created_at DESC)` 会影响用户分享列表分页查询性能

#### R17-P3-7：DB §5.3 MatchStatistic 缺 __table_args__

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.3 L2468-2477
- **问题描述**：§5.3 MatchStatistic 模型仅用 `unique=True` 在 match_id 上，未定义 __table_args__。§6 L2729 列出 `idx_mstat_match` (match_id) — 虽然 unique=True 会自动创建索引，但名称非 `idx_mstat_match`

#### R17-P3-8：DB §5.6 FeedbackRecord __table_args__ 缺 §6 两个索引

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.6 L2681-2683
- **问题描述**：§5.6 FeedbackRecord __table_args__ 仅含 `UniqueConstraint`，§6 列出的两个查询索引均未实现：

| §6 索引 | 用途 | §5.6 状态 |
|---------|------|----------|
| `idx_feedback_status` (status) | 数据飞轮审核队列查询 | ❌ 缺失 |
| `idx_feedback_correct_created` (is_correct, created_at) | 飞轮数据统计 | ❌ 缺失 |

#### R17-P3-9：DB §5.6 ProgressSnapshot __table_args__ 缺 GIN 索引

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5.6 L2640-2642
- **问题描述**：§5.6 ProgressSnapshot __table_args__ 仅有 `idx_ps_user_created`，§6 L2719 列出 `idx_ps_metrics_gin` GIN(metrics_snapshot) — 未在 §5.6 实现
- **影响**：缺少 GIN 索引会影响按指标查询快照性能

#### R17-P3-10：§5 缺多个模型代码示例

- **文件**：`docs/04详细设计/04-数据库详细设计.md` §5
- **问题描述**：§5 章节缺少以下表的 SQLAlchemy 模型代码示例（虽在 §2 表定义中已定义，切片也已实现）：

| 表 | §2 定义位置 | 切片实现位置 | §5 状态 |
|----|----------|------------|---------|
| user_points | §2.15 L693 | `09-gamification/backend.md` L179 | ❌ 缺失 |
| checkin_record | §2.16 L706 | `09-gamification/backend.md` L196 | ❌ 缺失 |
| refund_record | §2.19b L772 | `11-payment/backend.md` L505 | ❌ 缺失（R16 P3-11 延续）|
| consent_log | §2.34 L1078 | `01-auth/backend.md` L147 | ❌ 缺失 |
| admin_user | §2.31 L989 | `13-infrastructure/admin.md` L69 | ❌ 缺失 |
| audit_log | §2.31 L1000 | `13-infrastructure/admin.md` L83 | ❌ 缺失 |
| system_config | §2.31 L1017 | `13-infrastructure/admin.md` L112 | ❌ 缺失 |
| export_task | §2.33 L1058 | `02-user/backend.md` L239 | ❌ 缺失 |
| badge_definition | §3.1.4 L1172 | `09-gamification/backend.md` L216 | ❌ 缺失 |
| user_badge | §3.1.5 L1196 | `09-gamification/backend.md` L238 | ❌ 缺失 |
| badge_progress | §3.1.6 L1217 | `09-gamification/backend.md` L252 | ❌ 缺失 |

- **影响**：§5 章节作为"SQLAlchemy 2.0 Model 代码示例"应覆盖 Phase 1 全部表，缺失 11 个模型示例导致开发者无法统一参照

#### R17-P3-11：切片 FileRecord __table_args__ 与 §6 名称不一致

- **文件**：`docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` L232-235
- **问题描述**：

| §6 索引名 | 切片索引名 | 状态 |
|----------|----------|------|
| `idx_file_record_user_created` | `idx_file_record_user_created` | ✅ |
| `idx_file_record_type` | — | ❌ 切片缺 |
| `idx_file_status_created` (status, created_at) | `idx_file_record_status_created` (status, created_at) | ⚠️ 列相同，名称不同 |

#### R17-P3-13：consent_log 索引列 §2.34 与切片不一致

- **涉及文件**：DB §2.34 L1095、切片 `01-auth/backend.md` L159-162
- **问题描述**：

| 来源 | 索引 1 | 索引 2 |
|------|-------|-------|
| §2.34 表定义 | `(user_id, consent_at DESC)` | `(consent_type, withdrawn_at)` |
| 切片 __table_args__ | `idx_consent_user_at` (user_id, consent_at) | `idx_consent_user_type` (user_id, consent_type) |

- **影响**：§2.34 第二个索引 `(consent_type, withdrawn_at)` 用于按同意类型查撤回记录；切片 `(user_id, consent_type)` 用于按用户查同意类型。两者查询场景不同，缺失任一都会影响特定查询性能

#### R17-P3-14：切片 BadgeDefinition 缺 idx_badge_definition_active

- **文件**：`docs/06垂直模块前后端切片设计/09-gamification/backend.md` L233-235
- **问题描述**：切片 BadgeDefinition __table_args__ 仅含 `idx_badge_definition_category`，§3.1.4 L1192 列出 `idx_badge_definition_active` (is_active) — 切片用 `index=True` 内联在 is_active 上代替，自动生成索引名不符合 §3.1.4 规范

---

## 4. §5 系统性不同步逐表排查（核心交付）

> 以下逐表列出 §5 SQLAlchemy 模型代码与 §2 表定义（权威源）和 §6 索引总表的具体不一致项。已添加 §5 权威源注释说明"§2 为权威源"，但具体差异仍需修复。

### 4.1 user 表（§2.1 vs §5.1）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 16 个 | 16 个 ✅ | 16 个 ✅ | ✅ 一致 |
| openid 索引 | `idx_user_openid`（§6）| 用 `unique=True` 内联 | 用 `unique=True` 内联 | ⚠️ 无显式索引名 |
| phone 索引 | `idx_user_phone`（§6）| 用 `unique=True` 内联 | 用 `unique=True` 内联 | ⚠️ 无显式索引名 |

- **结论**：字段一致；索引定义方式不同（§5/切片用 unique=True 自动生成，§6 用显式名称）— 不影响功能，P3 级

### 4.2 file_record 表（§2.4 vs §5.2）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 12 个（含 updated_at）| **11 个（缺 updated_at）** ❌ | 12 个 ✅ | ❌ §5 缺 updated_at（R17-P3-4）|
| 索引 1 | `(user_id, created_at DESC)` | `idx_file_record_user_created` ✅ | `idx_file_record_user_created` ✅ | ✅ 一致 |
| 索引 2 | `(status, created_at)` | — ❌ 缺 | `idx_file_record_status_created` ⚠️ | §5 缺失（R17-P3-5）|
| 索引 3 | — | `idx_file_record_type` ✅ | — ❌ 切片缺 | 切片缺（R17-P3-11）|
| §6 对齐 | `idx_file_status_created` | — | `idx_file_record_status_created`（名称不同）| ⚠️ 三方名称不一致 |

### 4.3 video_task 表（§2.5 vs §5.2）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 16 个 | 16 个 ✅ | 16 个 ✅ | ✅ 一致 |
| 索引 1 | `(user_id, created_at DESC)` | `idx_video_task_user_created` ✅ | `idx_video_task_user_created` ✅ | ✅ 一致 |
| 索引 2 | `(status, created_at)` | `idx_video_task_status` ❌ | `idx_video_task_status_created` | §6 `idx_vtask_status`（R17-P3-17）|

### 4.4 pipeline_step 表（§2.6 vs §5.2）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 10 个 | 10 个 ✅ | 10 个 ✅ | ✅ 一致 |
| 索引 | `(task_id, step_number)` | `idx_pipeline_step_task_step` ✅ | `idx_pipeline_step_task_step` ✅ | ✅ 一致 |
| §6 索引 | 未列出 | — | — | — |

- **结论**：✅ 完全一致

### 4.5 analysis_report 表（§2.7 vs §5.2）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 11 个 | 11 个 ✅ | 11 个 ✅ | ✅ 一致 |
| result_data default | — | 无 default ❌ | 无 default | §5 与切片均缺（R17-P3-3）|
| report_text default | — | 无 default ❌ | 无 default | §5 与切片均缺（R17-P3-3）|
| 索引 1 | `(user_id, created_at DESC)` | ❌ 无 __table_args__ | `idx_analysis_report_user_created` | §5 缺（R17-P3-2）|
| GIN 索引 | `GIN(to_tsvector) + GIN(report_text)` | ❌ 无 | ❌ 无 | §5 和切片均缺 |
| §6 索引名 | `idx_report_user_created` | — | `idx_analysis_report_user_created`（名称不同）| ⚠️（R17-P3-20）|

### 4.6 feedback_record 表（§2.8 vs §5.6）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 8 个 | 8 个 ✅ | 8 个 ✅ | ✅ 一致 |
| Unique 约束列顺序 | `(report_id, user_id)` | `("user_id", "report_id")` | `("report_id", "user_id")` | ⚠️ §5 与切片不一致（R17-P3-18）|
| 索引 `idx_feedback_status` | — | ❌ 缺 | ❌ 缺 | §5 和切片均缺（R17-P3-8）|
| 索引 `idx_feedback_correct_created` | — | ❌ 缺 | ❌ 缺 | §5 和切片均缺（R17-P3-8）|

### 4.7 share_record 表（§2.9 vs §5.2）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 9 个 | 9 个 ✅ | 9 个 ✅ | ✅ 一致 |
| 索引 `(user_id, created_at DESC)` | §6 列出 | ❌ 无 __table_args__（用 index=True 内联）| ❌ 无 __table_args__ | §5 和切片均缺（R17-P3-6）|

### 4.8 match 表（§2.10 vs §5.3）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 18 个 | 18 个 ✅ | 18 个 ✅ | ✅ 一致 |
| 索引 1 | `(user_id, created_at DESC)` | `idx_match_user_status` (user_id, status) ❌ | `idx_match_user_created` (user_id, created_at) ✅ | §5 索引错误（R17-P3-1）|
| 索引 2 | `(status)` | — | — | §5 和切片均缺 |
| §6 索引 | 未列出 match | — | — | — |

### 4.9 score_record 表（§2.11 vs §5.3）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 8 个 | 8 个 ✅ | 8 个 ✅ | ✅ 一致 |
| 索引 1 | `(match_id, sequence)` | `idx_score_record_match_seq` ✅ | `idx_score_record_match_seq` ✅ | ✅ 一致 |
| 索引 2 | `(match_id, game_number)` | `idx_score_record_match_game` ✅ | `idx_score_record_match_game` ✅ | ✅ 一致 |

- **结论**：✅ 完全一致

### 4.10 match_statistic 表（§2.12 vs §5.3）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 4 个 | 4 个 ✅ | 4 个 ✅ | ✅ 一致 |
| 索引 | §6 `idx_mstat_match` (match_id) | ❌ 无 __table_args__（用 unique=True 自动生成）| ❌ 无 __table_args__ | §5 和切片均缺（R17-P3-7）|

### 4.11 match_record 表（§2.13 vs §5.4 vs 切片 `05-match_data`）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 14 个 | 14 个 ✅ | 14 个 ✅ | ✅ 一致 |
| 索引 | `(user_id, match_date DESC)` | `idx_mrecord_user_date` ✅ | `idx_match_record_user_date` ⚠️ | 名称不一致（R17-P3-15）|
| §6 索引名 | `idx_mrecord_user_date` | ✅ 一致 | ⚠️ 不一致 | — |

### 4.12 manual_score_detail 表（§2.14 vs §5.4）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 6 个 | 6 个 ✅ | 6 个 ✅ | ✅ 一致 |
| 索引 | `(match_record_id, sequence)`（§6 `idx_msd_record_seq`）| `idx_msd_record_seq` ✅ | 无 __table_args__（用 index=True 内联）| 切片缺显式索引名 |

### 4.13 user_points 表（§2.15）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 7 个 | ❌ **§5 无此模型** | 7 个 ✅ | §5 缺模型（R17-P3-10）|
| 索引 | §6 `idx_points_user_updated` (user_id, updated_at) | — | 无 __table_args__ | §5 和切片均缺 |

### 4.14 checkin_record 表（§2.16）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 7 个 | ❌ **§5 无此模型** | 7 个 ✅ | §5 缺模型（R17-P3-10）|
| 唯一约束 | `(user_id, checkin_date) UNIQUE` | — | `UniqueConstraint("user_id", "checkin_date", name="uq_checkin_user_date")` ✅ | §6 命名一致，切片实现 ✅ |

### 4.15 subscription 表（§2.17 vs §5.5）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 11 个 | 11 个 ✅（R16 补 payment_method + cancelled_at）| 11 个 ✅ | ✅ 一致 |
| 索引 1 | `(user_id, status)` | `idx_sub_user_status` ✅ | `idx_subscription_user_status` ⚠️ | 切片名称不一致（R17-P3-16）|
| 索引 2 | `(status, expire_at)` | `idx_sub_status_expire` ✅ | `idx_sub_status_expire` ✅ | ✅ 一致 |
| §6 对齐 | `idx_sub_user_status` | ✅ | ⚠️ 切片不一致 | — |

### 4.16 order 表（§2.18 vs §5.5）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 11 个 | 11 个 ✅ | 11 个 ✅ | ✅ 一致 |
| 索引 1 | `(user_id, created_at DESC)` | `idx_order_user_created` ✅ | `idx_order_user_created` ✅ | ✅ 一致 |
| 索引 2 | `(order_no)` | 用 `unique=True` 内联 ✅ | 用 `unique=True` 内联 ✅ | ✅ 功能一致 |
| 索引 3 | `(status)` | `idx_order_status` ✅ | `idx_order_status` ✅ | ✅ 一致 |

### 4.17 payment_record 表（§2.19 vs §5.5）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 8 个 | 8 个 ✅（R16 补 paid_at）| 8 个 ✅ | ✅ 一致 |
| **paid_at nullable** | Y（必填）| `nullable=True` ❌ | 非空 ✅ | **§5 nullable 矛盾**（R17-P2-1）|
| 索引 | `(order_id)`（§6 `idx_payment_order`）| `idx_payment_order` ✅ | `idx_payment_order` ✅ | ✅ 一致 |

### 4.18 refund_record 表（§2.19b）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 11 个 | ❌ **§5 无此模型** | 11 个 ✅ | §5 缺模型（R17-P3-19）|
| 索引 | `(order_id)`, `(refund_no)` | — | `idx_refund_record_order` (order_id) + unique=True (refund_no) | §6 未列出 refund_record |

### 4.19 notification_record 表（§2.20 vs §5.6）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 8 个 | 8 个 ✅ | — | §5 一致 |
| 索引 | `(user_id, is_read, created_at DESC)` | `idx_notif_user_unread` ✅ | — | ✅ 与 §6 一致 |

### 4.20 progress_snapshot 表（§2.21 vs §5.6）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 5 个 | 5 个 ✅ | — | ✅ 一致 |
| 索引 1 | `(user_id, created_at DESC)` | `idx_ps_user_created` ✅ | — | ✅ 一致 |
| GIN 索引 | `GIN(metrics_snapshot)` | ❌ 缺 | — | §5 缺（R17-P3-9）|

### 4.21 technique_trend 表（§2.22 vs §5.6）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 11 个 | 11 个 ✅ | — | ✅ 一致 |
| 唯一约束 | `(user_id, metric_name) UNIQUE` | `uq_trend_user_metric` (unique=True) ✅ | — | ✅ 一致 |

### 4.22 admin_user / audit_log / system_config 表（§2.31）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| admin_user 字段 | 5 个 | ❌ §5 无此模型 | 5 个 ✅ | §5 缺（R17-P3-10）|
| audit_log 字段 | 9 个 | ❌ §5 无此模型 | 9 个 ✅ | §5 缺（R17-P3-10）|
| **audit_log.admin_id FK** | `FK→admin_user.id, SET NULL`（NOT NULL 矛盾）❌ | — | `ondelete="RESTRICT", nullable=False` ✅ | **§2.31 矛盾**（R17-P2-2）|
| audit_log.user_id FK | `FK→user.id, SET NULL`（nullable 一致）✅ | — | `ondelete="SET NULL", nullable=True` ✅ | ✅ 一致 |
| audit_log 索引 | §6 `idx_audit_admin_created` | — | `idx_audit_admin_created` ✅ + `idx_audit_user_created` + `idx_audit_target` | 切片多 2 个（R17-P3-12）|
| system_config 字段 | 5 个 | ❌ §5 无此模型 | 5 个 ✅ | §5 缺（R17-P3-10）|

### 4.23 badge_definition / user_badge / badge_progress 表（§3.1.4-3.1.6）

| 检查项 | §3.1 表定义 | §5 模型 | 切片 | 结论 |
|-------|-----------|--------|------|------|
| badge_definition 字段 | 9 个 | ❌ §5 无此模型 | 9 个 ✅ | §5 缺（R17-P3-10）|
| user_badge.badge_id FK | `CASCADE` ❌ | — | `ondelete="RESTRICT"` | **DB §3.1 与切片矛盾**（R17-P1-1）|
| badge_progress.badge_id FK | `CASCADE` ❌ | — | `ondelete="RESTRICT"` | **DB §3.1 与切片矛盾**（R17-P1-1）|
| badge_definition 索引 | `idx_badge_definition_category` + `idx_badge_definition_active` | — | `idx_badge_definition_category` + `index=True` 内联 | 切片缺 `idx_badge_definition_active`（R17-P3-14）|

### 4.24 export_task 表（§2.33）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 9 个 | ❌ §5 无此模型 | 9 个 ✅ | §5 缺（R17-P3-10）|
| 索引 1 | `(user_id, created_at DESC)` | — | `idx_export_user_created` ✅ | ✅ 切片一致 |
| 索引 2 | `(task_id)` | — | 用 `unique=True, index=True` 内联 ✅ | ✅ 功能一致 |

### 4.25 consent_log 表（§2.34）

| 检查项 | §2 表定义 | §5 模型 | 切片 | 结论 |
|-------|---------|--------|------|------|
| 字段 | 8 个 | ❌ §5 无此模型 | 8 个 ✅ | §5 缺（R17-P3-10）|
| 索引 1 | `(user_id, consent_at DESC)` | — | `idx_consent_user_at` (user_id, consent_at) ✅ | 列一致 |
| 索引 2 | `(consent_type, withdrawn_at)` ❌ | — | `idx_consent_user_type` (user_id, consent_type) | **列不同**（R17-P3-13）|

---

## 5. 已修复项清单

| # | 原修复轮次 | 检查项 | 本轮验证 |
|---|----------|--------|---------|
| 1 | R16 P2-4 | §5.5 Subscription 补 payment_method + cancelled_at | ✅ 无回归 |
| 2 | R16 P3-1 | §4.1 UserStatus 补 pending_deletion | ✅ 无回归 |
| 3 | R16 P3-2 | §4.1 SubscriptionStatus 补 cancelled | ✅ 无回归 |
| 4 | R16 P3-3 | §5.5 Subscription status 注释补 cancelled | ✅ 无回归 |
| 5 | R16 P3-12 | ER 图 VideoTask 补 v1.4 字段 | ✅ 无回归 |
| 6 | R16 P3-13 | ER 图 AnalysisReport 补字段 | ✅ 无回归 |
| 7 | R16 §5 注释 | §5 权威源注释 | ✅ 已添加 |
| 8 | R16 P3-5（DB 侧）| §5.5 Subscription 索引名与 §6 对齐 | ✅ DB 内部已对齐 |
| 9 | R16 P3-7（DB 侧）| §3.1.5/3.1.6 badge FK 补 ondelete | ⚠️ 已补 CASCADE，但与切片 RESTRICT 矛盾 |
| 10 | R16 P3-8（user_id 侧）| §2.31 audit_log.user_id FK ondelete=SET NULL | ✅ 一致 |

---

## 6. 本轮统计

| 级别 | 新发现 | R16 修复引入问题 | 已修复验证通过 | 遗留 |
|------|--------|----------------|------------|------|
| P0 | 0 | 0 | — | 0 |
| P1 | 1（R17-P1-1）| 1 | — | 1 |
| P2 | 0 | 2（R17-P2-1, R17-P2-2）| — | 2 |
| P3 | 20 | — | — | 20 |
| **合计** | **21** | **3** | **10** | **23** |

### 按修复方向分类

| 修复方向 | 数量 | 优先建议 |
|---------|------|---------|
| R16 修复回归（P1+P2）| 3（R17-P1-1, P2-1, P2-2）| 最高 — R16 修复引入新矛盾 |
| §5 模型缺 __table_args__ / 索引 | 7（P3-1, 2, 5, 6, 7, 8, 9）| 高 — §5 与 §6 索引总表系统性不同步 |
| §5 缺多个模型示例 | 1（P3-10，含 11 个模型）| 高 — §5 覆盖度不足 |
| 索引命名三方不一致 | 5（P3-11, 15, 16, 17, 20）| 中 — 影响 Alembic 迁移 |
| 切片缺索引 | 2（P3-12, 14）| 低 |
| §5 模型字段/默认值缺漏 | 3（P3-3, 4, 19）| 低 |
| 索引列不一致 | 2（P3-13, 18）| 低-中 |

---

## 7. 修复建议优先级排序

### 第一优先级（R16 修复回归，应立即修复）

1. **R17-P1-1**：统一 badge 表 FK ondelete 策略 — DB §3.1.5/3.1.6 将 `CASCADE` 改为 `RESTRICT`，与切片一致
2. **R17-P2-1**：§5.5 PaymentRecord.paid_at 移除 `| None` 和 `nullable=True`，改为 `Mapped[datetime] = mapped_column(DateTime(timezone=True))`，与 §2.19（必填）和切片一致
3. **R17-P2-2**：§2.31 audit_log.admin_id 将 `SET NULL` 改为 `RESTRICT`，与 NOT NULL 语义和切片一致

### 第二优先级（P3-高，§5 与 §6 索引系统性不同步）

4. **R17-P3-1**：§5.3 Match __table_args__ 改为 `idx_match_user_created` + `idx_match_status`，与 §2.10 对齐
5. **R17-P3-2**：§5.2 AnalysisReport 补 __table_args__，加 `idx_report_user_created` + GIN 索引
6. **R17-P3-5**：§5.2 FileRecord __table_args__ 补 `idx_file_status_created`
7. **R17-P3-6**：§5.2 ShareRecord 补 __table_args__ 和 `idx_share_user_created`
8. **R17-P3-7**：§5.3 MatchStatistic 补 __table_args__ 和 `idx_mstat_match`
9. **R17-P3-8**：§5.6 FeedbackRecord __table_args__ 补 `idx_feedback_status` + `idx_feedback_correct_created`
10. **R17-P3-9**：§5.6 ProgressSnapshot __table_args__ 补 `idx_ps_metrics_gin` GIN 索引
11. **R17-P3-10**：§5 补全 11 个缺失模型示例（user_points/checkin_record/refund_record/consent_log/admin_user/audit_log/system_config/export_task/badge_definition/user_badge/badge_progress）

### 第三优先级（P3-中，索引命名统一）

12. **R17-P3-11**：切片 FileRecord __table_args__ 补 `idx_file_record_type`，状态索引改名为 `idx_file_status_created`
13. **R17-P3-13**：统一 consent_log 第二索引列定义（§2.34 vs 切片）
14. **R17-P3-16**：切片 Subscription 索引名改为 `idx_sub_user_status`
15. **R17-P3-17**：统一 VideoTask 第二索引名为 `idx_video_task_status_created`，同步 §5.2 和 §6
16. **R17-P3-15**：切片 MatchRecord 索引名改为 `idx_mrecord_user_date`

### 第四优先级（P3-低，文档完善）

17. **R17-P3-3**：§5.2 AnalysisReport JSONB 字段补 `default=dict`
18. **R17-P3-4**：§5.2 FileRecord 补 `updated_at` 字段
19. **R17-P3-12**：§6 补 audit_log `idx_audit_user_created` 和 `idx_audit_target`
20. **R17-P3-14**：切片 BadgeDefinition 补 `idx_badge_definition_active` 索引
21. **R17-P3-18**：统一 FeedbackRecord UniqueConstraint 列顺序
22. **R17-P3-19**：§5 补 RefundRecord 模型代码示例
23. **R17-P3-20**：切片 AnalysisReport 索引名改为 `idx_report_user_created`

---

## 8. 关键结论

1. **P0=0 确认**：本轮无阻断性字段缺失或外键断裂问题

2. **R16 修复回归 3 项**（P1×1 + P2×2）— 这是本轮最关键的发现：
   - **R17-P1-1**：badge FK ondelete 策略 DB §3.1（CASCADE）与切片（RESTRICT）相反，引用完整性语义冲突
   - **R17-P2-1**：§5.5 PaymentRecord.paid_at 被设为 nullable=True，与 §2.19（必填）和切片（非空）矛盾
   - **R17-P2-2**：§2.31 audit_log.admin_id FK=SET NULL 与 NOT NULL 矛盾（R16 P3-8 admin_id 侧未修复）

3. **§5 系统性不同步持续存在**：§5 模型代码与 §2/§6 在以下方面存在系统性差异：
   - **缺模型**：§5 缺 11 个表的模型示例（user_points/checkin_record/refund_record/consent_log/admin_user/audit_log/system_config/export_task/badge_definition/user_badge/badge_progress）
   - **缺索引**：§5 多个模型缺 __table_args__（AnalysisReport/MatchStatistic/ShareRecord），或 __table_args__ 不完整（FeedbackRecord/ProgressSnapshot/FileRecord）
   - **索引名不一致**：VideoTask/FileRecord/Subscription/AnalysisReport/MatchRecord/Match 等表的索引名在 §5/§6/切片三方不一致
   - **字段缺漏**：§5.2 FileRecord 缺 updated_at，§5.2 AnalysisReport JSONB 字段缺 default

4. **已对齐项**：PipelineStep/ScoreRecord/MatchStatistic 字段/Subscription R16 补字段/Order 全部字段/TechniqueTrend/NotificationRecord 字段一致

5. **建议优先处理 R16 修复回归**（3 项 P1+P2），其次集中处理 §5 与 §6 索引系统性不同步（7 项 P3-高），再处理索引命名统一（5 项 P3-中）

---

> **审查结论**：第十六轮 18 项 DB 修复中，7 项完全通过、2 项引入新矛盾（P1×1 + P2×1）、9 项未实际修复或部分修复。本轮新发现 21 项（P1×1 + P2×2 + P3×20），其中 3 项为 R16 修复回归需立即处理，18 项为 §5 系统性不同步延续问题。建议优先修复 R16 回归，其次集中同步 §5 模型代码与 §2/§6 索引总表。
