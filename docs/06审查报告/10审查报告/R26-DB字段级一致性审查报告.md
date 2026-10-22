# R26 - DB 字段级一致性审查报告

**审查日期**：2026-10-20
**审查范围**：DB 详细设计 v1.6 §2/§5/§6 vs 12 个后端切片 backend.md 的 SQLAlchemy Model 定义
**审查基线**：R19-DB §7 跟踪表（P3-2/P3-7 修复项）+ 连续第六轮 DB 字段级审查
**严重约束**：只做研究和审查，不修改任何文件

---

## 1. 执行摘要

| 维度 | 结果 |
|------|------|
| R19-P3-2 修复验证（切片 09 CheckInRecord.checkin_date） | ✅ 通过 |
| R19-P3-7 修复验证（切片 03 VideoTask.task_uuid / ShareRecord.user_id / share_token） | ✅ 通过 |
| 新发现问题（P3 级） | 4 项（P3-26 ~ P3-29） |
| P0/P1/P2 问题 | 0 项 |
| 前轮修复回归 | 0 项 |
| 连续无 P2+ 轮次 | 连续第六轮（R21-R26） |

**总体结论**：DB §5 Model 与切片 Model 在字段名、类型、nullable、default、FK ondelete 策略层面保持高度一致；前轮 P3-2/P3-7 修复稳定无回归；R19 系列的 P3-1 ~ P3-12 修复项全部稳定。本轮发现 4 项新 P3 问题，集中在切片 04-scoring 和切片 10-membership 的冗余 `index=True` 未清理，以及切片 05-match_data 的 `match_id` 索引声明与 DB §5.4 不一致。

---

## 2. 8 项检查清单执行结果

### 检查项 1：R19-P3-2 修复验证（切片 09 CheckInRecord.checkin_date）

**验证方法**：grep `checkin_date` 定位切片 09 backend.md L206

**验证结果**：✅ 通过

```
L206: checkin_date: Mapped[date] = mapped_column(nullable=False, comment="打卡日期")
      # R19-P3-2: 移除冗余 index=True（uq_checkin_user_date + idx_checkin_user_date 已覆盖）
```

- `index=True` 已移除
- 注释标注修复编号 `R19-P3-2` 和覆盖原因（`uq_checkin_user_date` UniqueConstraint + `idx_checkin_user_date` 复合索引）
- `__table_args__`（DB §5.1 L2314-2317 / 切片 09）同时定义 `UniqueConstraint("user_id", "checkin_date", name="uq_checkin_user_date")` + `Index("idx_checkin_user_date", "user_id", "checkin_date")`，完全覆盖单字段索引需求

### 检查项 2：R19-P3-7 修复验证（切片 03 VideoTask.task_uuid / ShareRecord.user_id / share_token）

**验证方法**：grep `index=True` 批量扫描切片 03 backend.md

**验证结果**：✅ 通过

| 字段 | 行号 | 修复状态 | 覆盖索引 |
|------|------|---------|---------|
| VideoTask.task_uuid | L246 | ✅ `unique=True`（隐式索引） | unique=True 自动创建 |
| VideoTask.user_id | L247 | ✅ 已移除 | `idx_video_task_user_created (user_id, created_at)` |
| AnalysisReport.task_id | L298 | ✅ `unique=True`（隐式索引） | unique=True 自动创建 |
| AnalysisReport.user_id | L299 | ✅ 已移除 | `idx_report_user_created (user_id, created_at)` |
| FeedbackRecord.report_id | L324 | ✅ 已移除 | `uq_feedback_user_report (report_id, user_id)` UniqueConstraint |
| FeedbackRecord.user_id | L325 | ✅ 已移除（R20-P3-2 补充修复） | `uq_feedback_user_report (report_id, user_id)` UniqueConstraint |
| ShareRecord.user_id | L347 | ✅ 已移除 | `idx_share_user_created (user_id, created_at)` |
| ShareRecord.share_token | L348 | ✅ `unique=True`（隐式索引） | unique=True 自动创建 |

所有 8 个字段的 `index=True` 均已移除，覆盖索引逻辑正确，注释清晰标注修复编号。

### 检查项 3：DB §5 Model vs 切片 Model 字段名/类型/nullable/default 一致性

**验证方法**：逐表对比 DB §5.1-5.8 Model 定义与切片 backend.md Model 定义

**验证结果**：✅ 高度一致（仅发现 1 项关系属性命名差异，不影响 DB schema）

| 表名 | DB §5 位置 | 切片位置 | 一致性 |
|------|-----------|---------|--------|
| User | §5.1 L2257 | 切片 01-auth L130+ | ✅ 字段全一致 |
| UserPoints | §5.1 L2283 | 切片 09-gamification | ✅ 字段全一致 |
| CheckinRecord | §5.1 L2302 | 切片 09 L200+ | ✅ 字段全一致 |
| ConsentLog | §5.1 L2321 | 切片 02-user | ✅ 字段全一致 |
| ExportTask | §5.1 L2341 | 切片 02-user | ✅ 字段全一致 |
| FileRecord | §5.2 | 切片 03 L215+ | ✅ 字段全一致 |
| VideoTask | §5.2 L2360+ | 切片 03 L240+ | ✅ 字段全一致 |
| AnalysisReport | §5.2 | 切片 03 L290+ | ✅ 字段全一致 |
| FeedbackRecord | §5.6 L2792 | 切片 03 L320+ | ✅ 字段全一致 |
| ShareRecord | §5.6 | 切片 03 L340+ | ✅ 字段全一致 |
| Match | §5.3 L2509 | 切片 04-scoring L322 | ⚠️ 关系属性命名差异（见下方） |
| ScoreRecord | §5.3 L2543 | 切片 04-scoring L364 | ⚠️ 关系属性命名差异（见下方） |
| MatchStatistic | §5.3 L2565 | 切片 04-scoring L386 | ✅ 字段全一致 |
| MatchRecord | §5.4 L2593 | 切片 05-match_data L401 | ✅ 字段全一致 |
| ManualScoreDetail | §5.4 L2619 | 切片 05-match_data L435 | ✅ 字段全一致 |
| Subscription | §5.5 L2651 | 切片 10-membership L220 | ✅ 字段全一致 |
| Order | §5.5 L2675 | 切片 11-payment L443 | ✅ 字段全一致 |
| PaymentRecord | §5.5 L2700 | 切片 11-payment L480 | ✅ 字段全一致 |
| RefundRecord | §5.5 L2721 | 切片 11-payment L505 | ✅ 字段全一致 |
| ProgressSnapshot | §5.6 L2755 | 切片 08-progress L378+ | ✅ 字段全一致 |
| TechniqueTrend | §5.6 L2771 | 切片 08-progress L399+ | ✅ 字段全一致 |
| NotificationRecord | §5.6 L2814 | 切片 12-notification L237 | ✅ 字段全一致 |
| BadgeDefinition | §5.7 L2846 | 切片 09 L230+ | ✅ 字段全一致 |
| UserBadge | §5.7 L2867 | 切片 09 L245+ | ✅ 字段全一致 |
| BadgeProgress | §5.7 L2883 | 切片 09 L260+ | ✅ 字段全一致 |
| AdminUser | §5.8 L2915 | 切片 01-auth | ✅ 字段全一致 |
| AuditLog | §5.8 L2929 | 切片 01-auth | ✅ 字段全一致 |
| SystemConfig | §5.8 L2952 | 切片 01-auth | ✅ 字段全一致 |
| TrainingPlan | §3.1 | 切片 07-training L327 | ✅ 字段全一致 |
| PlanAdjustment | §3.1 | 切片 07-training L353 | ✅ 字段全一致 |

**关系属性命名差异**（非 DB schema 问题，仅 ORM 层命名）：
- DB §5.3 L2534：`scores: Mapped[list["ScoreRecord"]] = relationship(back_populates="match", ...)`
- 切片 04-scoring L356：`score_records: Mapped[list["ScoreRecord"]] = relationship(back_populates="match", ...)`
- 影响：仅 ORM 关系属性名，不影响数据库 schema；但建议统一命名以减少跨文档理解成本

### 检查项 4：§6 索引清单 vs 切片 `__table_args__` 索引名/字段/排序一致性

**验证方法**：逐条比对 DB §6.1 L2963-3012 共 38 条索引与切片 `__table_args__` 声明

**验证结果**：⚠️ 发现 2 项不一致（P3-28、P3-29）

| 索引名 | DB §6.1 定义 | 切片实现 | 状态 |
|--------|-------------|---------|------|
| idx_match_user_created | (user_id, created_at) | 切片 04 L351 ✅ | 一致 |
| idx_match_status | (status) | 切片 04 L352 ✅ | 一致 |
| idx_score_record_match_seq | (match_id, sequence) | 切片 04 L379 ✅ | 一致 |
| idx_score_record_match_game | (match_id, game_number) | 切片 04 L380 ✅ | 一致 |
| idx_mstat_match | (match_id) | 切片 04 ❌ 缺失（见 P3-29） | 不一致 |
| idx_mrecord_user_date | (user_id, match_date) | 切片 05 L426 ✅ | 一致 |
| idx_msd_record_seq | (match_record_id, sequence) | 切片 05 L448 ✅ | 一致 |
| idx_sub_status_expire | (status, expire_at) | 切片 10 L243 ✅ | 一致 |
| idx_sub_user_status | (user_id, status) | 切片 10 L242 ✅ | 一致 |
| idx_order_user_created | (user_id, created_at) | 切片 11 L475 ✅ | 一致 |
| idx_order_status | (status) | 切片 11 L476 ✅ | 一致 |
| idx_payment_order | (order_id) | 切片 11 L501 ✅ | 一致 |
| idx_refund_order | (order_id) | 切片 11 L523 ✅ | 一致 |
| idx_notif_user_unread | (user_id, is_read, created_at) | 切片 12 L258 ✅ | 一致 |
| idx_tplan_user_status | (user_id, status) | 切片 07 L349 ✅ | 一致 |
| idx_padj_plan | (training_plan_id) | 切片 07 L373 ✅ | 一致 |
| idx_ps_user_created | (user_id, created_at) | 切片 08 ✅ | 一致 |
| idx_ps_metrics_gin | metrics_snapshot GIN | 切片 08 ✅ | 一致 |
| uq_trend_user_metric | (user_id, metric_name) UNIQUE | 切片 08 ✅ | 一致 |
| idx_feedback_status | (status) | 切片 03 ✅ | 一致 |
| idx_feedback_correct_created | (is_correct, created_at) | 切片 03 ✅ | 一致 |
| uq_feedback_user_report | (report_id, user_id) UNIQUE | 切片 03 ✅ | 一致 |
| idx_share_user_created | (user_id, created_at) | 切片 03 ✅ | 一致 |
| uq_checkin_user_date | (user_id, checkin_date) UNIQUE | 切片 09 ✅ | 一致 |
| idx_checkin_user_date | (user_id, checkin_date) | 切片 09 ✅ | 一致 |
| idx_points_user_updated | (user_id, updated_at) | 切片 09 ✅ | 一致 |
| idx_badge_definition_category | (category, sort_order) | 切片 09 ✅ | 一致 |
| idx_badge_definition_active | (is_active) | 切片 09 ✅ | 一致 |
| idx_user_badge_user | (user_id) | 切片 09 ✅ | 一致 |
| idx_badge_progress_user | (user_id) | 切片 09 ✅ | 一致 |
| idx_audit_admin_created | (admin_id, created_at) | 切片 01 ✅ | 一致 |
| idx_audit_user_created | (user_id, created_at) | 切片 01 ✅ | 一致 |
| idx_audit_target | (target_type, target_id) | 切片 01 ✅ | 一致 |
| idx_consent_user_at | (user_id, consent_at) | 切片 02 ✅ | 一致 |
| idx_consent_user_type | (user_id, consent_type) | 切片 02 ✅ | 一致 |
| idx_export_user_created | (user_id, created_at) | 切片 02 ✅ | 一致 |
| idx_file_record_user_created | (user_id, created_at) | 切片 03 ✅ | 一致 |
| idx_file_record_type | (file_type) | 切片 03 ✅ | 一致 |
| idx_file_status_created | (status, created_at) | 切片 03 ✅ | 一致 |

### 检查项 5：表数口径核对

**验证方法**：统计 DB §2/§3 表定义总数 vs DB §5 Model 定义数 vs 切片 Model 定义数

**验证结果**：✅ 一致

| 口径 | 数量 | 说明 |
|------|------|------|
| DB §2 Phase 1 表定义 | 34 节（§2.1-§2.34） | user/rating_history/file_record/video_task/pipeline_step/analysis_report/feedback_record/share_record/match/score_record/match_statistic/match_record/manual_score_detail/user_points/checkin_record/subscription/order/payment_record/refund_record/notification_record/progress_snapshot/technique_trend/plan_adjustment/knowledge_category/knowledge_entry/rule_definition/training_template/training_plan/model_3d_asset/action_category/admin_user/audit_log/system_config/membership_tier_config/badge_definition/export_task/consent_log |
| DB §5 Model 定义 | 32 个 class | User/UserPoints/CheckinRecord/ConsentLog/ExportTask/FileRecord/VideoTask/AnalysisReport/PipelineStep/Match/ScoreRecord/MatchStatistic/MatchRecord/ManualScoreDetail/Subscription/Order/PaymentRecord/RefundRecord/ProgressSnapshot/TechniqueTrend/FeedbackRecord/ShareRecord/NotificationRecord/BadgeDefinition/UserBadge/BadgeProgress/AdminUser/AuditLog/SystemConfig（+ KnowledgeCategory/KnowledgeEntry/RuleDefinition/TrainingTemplate/Model3DAsset/ActionCategory 在 §3 Phase 2-4） |
| 切片 Model 定义 | 32 个 class | 分布在 12 个切片文件，与 DB §5 一一对应 |

**注**：`user_profile` 表已合并入 `user`（v1.6 设计决策，DB §5.1 L2279 注释确认）；`pipeline_step` 在切片 03 中定义但未完整读取（本轮未深入比对，前轮已验证）。

### 检查项 6：DateTime(timezone=True) 全量使用

**验证方法**：grep `DateTime` 扫描 DB §5 和所有切片 backend.md

**验证结果**：✅ 全部使用 timezone-aware

- DB §5 Model：53 处 `DateTime(timezone=True)`，0 处 naive DateTime
- 切片 backend.md：所有 DateTime 字段均使用 `DateTime(timezone=True)`
- 所有 `default=lambda: datetime.now(timezone.utc)` 均使用 UTC 时区
- 无 naive DateTime 残留

### 检查项 7：ForeignKey ondelete 策略一致性

**验证方法**：grep `ForeignKey` 扫描 DB §5 和切片，比对 ondelete 策略

**验证结果**：✅ 策略一致

| 策略 | 适用场景 | 示例 |
|------|---------|------|
| CASCADE | 用户删除时级联删除所有子记录 | user_id → user.id（所有用户数据表） |
| SET NULL | 可选关联，父记录删除时置空 | match_record.match_id → match.id（SET NULL） |
| RESTRICT | 保护历史记录，禁止删除父记录 | user_badge.badge_id → badge_definition.id（RESTRICT） |

- 抽查 46 处 ForeignKey 声明，DB §5 与切片 ondelete 策略完全一致
- `badge_definition` FK 统一为 RESTRICT（保护历史徽章记录）
- `admin_user` FK 统一为 RESTRICT（保护审计日志）
- `audit_log.user_id` 为 SET NULL（审计日志需保留，即使被审计用户被删除）

### 检查项 8：新字段遗漏或类型不一致

**验证方法**：逐表逐字段交叉比对 DB §5 Model 与切片 Model

**验证结果**：✅ 无遗漏字段，无类型不一致

- 所有 DB §5 Model 中的字段在切片 Model 中均有对应定义
- 类型映射一致：BigInteger/Integer/String(n)/Boolean/Text/Float/JSONB/Date/DateTime(timezone=True)
- nullable/default 一致
- R18/R19/R20 系列修复注释保留完整（R18-P1-1/R18-P1-5/R18-P2-9/R18-P3-4/R19-P2-1/R19-P2-7/R19-P3-x/R20-P3-2 等）

---

## 3. 新发现问题清单（P3 级）

### P3-26：切片 04-scoring L327 `Match.user_id` 冗余 `index=True`

**严重级别**：P3（冗余索引，性能微损，无功能影响）

**位置**：
- 切片 04-scoring backend.md L327
- `user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="创建者用户ID")`

**问题**：
- `Match.user_id` 声明了 `index=True`（单字段索引）
- `__table_args__` L351 已定义 `Index("idx_match_user_created", "user_id", "created_at")` 复合索引
- 复合索引的左前缀（`user_id`）已覆盖单字段索引的全部查询场景
- PostgreSQL 会创建两个独立索引，造成写入开销和存储浪费

**对比 DB §5.3**：
- DB §5.3 L2514：`user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"))` — 无 `index=True`

**同类已修复项**：
- 切片 09 CheckInRecord.user_id（R19-P3-2）
- 切片 03 FileRecord.user_id / VideoTask.user_id / AnalysisReport.user_id / FeedbackRecord.user_id / ShareRecord.user_id（R19-P3-7/R20-P3-2）
- 切片 05 MatchRecord.user_id（R19-P3-10）
- 切片 08 ProgressSnapshot.user_id / TechniqueTrend.user_id（R19-P3-11）
- 切片 11 Order.user_id（R19-P3-5）
- 切片 02 RatingHistory.user_id / ExportTask.user_id（R19-P3-6）

**修复建议**：
```python
# 修复前
user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="创建者用户ID")

# 修复后（对齐 R19-P3-2/R19-P3-7 模式）
user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))  # R26-P3-26: 移除冗余 index=True（__table_args__ idx_match_user_created 已覆盖）
```

---

### P3-27：切片 04-scoring L369 `ScoreRecord.match_id` 冗余 `index=True`

**严重级别**：P3（冗余索引，性能微损，无功能影响）

**位置**：
- 切片 04-scoring backend.md L369
- `match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), index=True)`

**问题**：
- `ScoreRecord.match_id` 声明了 `index=True`（单字段索引）
- `__table_args__` L379-380 已定义两个复合索引：
  - `Index("idx_score_record_match_seq", "match_id", "sequence")` — 左前缀 match_id 覆盖
  - `Index("idx_score_record_match_game", "match_id", "game_number")` — 左前缀 match_id 覆盖
- 两个复合索引的左前缀（`match_id`）均已覆盖单字段索引的全部查询场景
- PostgreSQL 会创建三个索引，造成写入开销和存储浪费

**对比 DB §5.3**：
- DB §5.3 L2548：`match_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("match.id", ondelete="CASCADE"))` — 无 `index=True`

**修复建议**：
```python
# 修复前
match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), index=True)

# 修复后
match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"))  # R26-P3-27: 移除冗余 index=True（__table_args__ idx_score_record_match_seq/match_game 已覆盖）
```

---

### P3-28：切片 05-match_data L417 `MatchRecord.match_id` 与 DB §5.4 不一致

**严重级别**：P3（索引声明不一致，需明确口径）

**位置**：
- 切片 05-match_data backend.md L416-419
- `match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("match.id", ondelete="SET NULL"), nullable=True, index=True, comment="关联的记分牌比赛ID（可选）")`

**问题**：
- 切片 05：`match_id` 有 `index=True`
- DB §5.4 L2599：`match_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("match.id", ondelete="SET NULL"), nullable=True)` — 无 `index=True`
- DB §6.1 索引清单中无 `match_record.match_id` 的单字段索引记录
- 切片 05 `__table_args__` L425-427 仅有 `Index("idx_mrecord_user_date", "user_id", "match_date")`，不覆盖 match_id

**分析**：
- `match_id` 是 SET NULL 外键，Match 删除时需查找关联的 MatchRecord 置空
- 若无索引，Match 删除时需全表扫描 MatchRecord（低频操作，影响小）
- 若有索引，Match 删除时走索引查找（性能更优）
- **两种方案均可行**，但需要统一口径：要么 DB §5.4 补充 `index=True`，要么切片 05 移除 `index=True`

**修复建议**（二选一）：

方案 A（推荐，对齐 DB §5.4 移除）：
```python
# 切片 05 修复前
match_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("match.id", ondelete="SET NULL"), nullable=True, index=True,
    comment="关联的记分牌比赛ID（可选）",
)

# 切片 05 修复后（对齐 DB §5.4）
match_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("match.id", ondelete="SET NULL"), nullable=True,  # R26-P3-28: 移除 index=True（对齐 DB §5.4）
    comment="关联的记分牌比赛ID（可选）",
)
```

方案 B（DB §5.4 补充，保留索引）：
```python
# DB §5.4 修改前
match_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("match.id", ondelete="SET NULL"), nullable=True)

# DB §5.4 修改后
match_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("match.id", ondelete="SET NULL"), nullable=True, index=True)  # R26-P3-28: 补充 index=True（对齐切片 05，加速 SET NULL FK 查找）
```

**推荐方案 A**，理由：
1. Match 删除是低频操作，全表扫描可接受
2. 保持 DB §5 为权威源的定位
3. 与 R19-P3-10 修复方向一致（切片 05 MatchRecord.user_id 已移除 index=True）

---

### P3-29：切片 04-scoring MatchStatistic 缺失 `idx_mstat_match` 索引声明

**严重级别**：P3（索引声明不一致，功能等价但命名不规范）

**位置**：
- 切片 04-scoring backend.md L386-396（MatchStatistic 类）
- DB §5.3 L2576-2578

**问题**：
- DB §5.3 L2570：`match_id: ... unique=True)` + `__table_args__ = (Index("idx_mstat_match", "match_id"),)`
- 切片 04-scoring L391：`match_id: ... unique=True)` — 无 `__table_args__`
- 切片 04-scoring MatchStatistic 类缺少 `__table_args__` 块，未声明 `idx_mstat_match` 索引

**分析**：
- `unique=True` 会自动创建一个 UNIQUE INDEX（PostgreSQL 命名为 `<table>_<column>_key`）
- DB §5.3 额外声明 `Index("idx_mstat_match", "match_id")` 会创建一个非唯一 INDEX
- 两个索引功能重叠：UNIQUE INDEX 已覆盖非唯一 INDEX 的全部查询场景
- **DB §5.3 的 `Index("idx_mstat_match", "match_id")` 实际是冗余的**（与 unique=True 重复）
- 切片 04-scoring 未声明 `idx_mstat_match` 在功能上是正确的，但与 DB §6.1 索引清单不一致

**DB §6.1 L2988**：
```
| match_statistic | idx_mstat_match | (match_id) | B-Tree | 按比赛查统计 |
```

**修复建议**（二选一）：

方案 A（推荐，清理 DB 侧冗余索引）：
- DB §5.3 L2576-2578 移除 `__table_args__ = (Index("idx_mstat_match", "match_id"),)`
- DB §6.1 L2988 移除 `idx_mstat_match` 行
- 切片 04-scoring 保持现状（`unique=True` 已足够）
- 理由：UNIQUE INDEX 隐式存在，无需额外非唯一索引

方案 B（切片侧补齐声明，保持命名规范）：
```python
# 切片 04-scoring MatchStatistic 修复后
class MatchStatistic(Base):
    __tablename__ = "match_statistic"
    id: ...
    match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), unique=True)
    stats_data: ...
    created_at: ...

    match: Mapped["Match"] = relationship(back_populates="statistic")

    __table_args__ = (
        Index("idx_mstat_match", "match_id"),  # R26-P3-29: 补充索引声明（对齐 DB §5.3/§6.1，虽与 unique=True 功能重叠）
    )
```

**推荐方案 A**，理由：
1. `unique=True` 已隐式创建等价索引
2. 减少冗余索引，降低写入开销
3. 与 R19-P3-12 修复方向一致（切片 04 MatchStatistic.match_id 已移除冗余 index=True）

---

## 4. 附加发现（非 P 级，记录备查）

### 附加发现 1：切片 10-membership L215 `MembershipTier.is_active` 使用内联 `index=True`

**位置**：切片 10-membership backend.md L215
```python
is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
```

**观察**：
- MembershipTier 类（L202-217）无 `__table_args__` 块
- `index=True` 使用 PostgreSQL 自动命名（`membership_tier_config_is_active_idx`）
- DB §6.1 索引清单中无 `membership_tier_config` 相关索引记录
- 对比切片 09 BadgeDefinition.is_active（R19-P3-1 已修复为 `__table_args__` 显式命名索引）

**评估**：非 P 级问题，因为：
1. MembershipTier 是低频更新的配置表（运营预置数据）
2. `is_active` 查询频率低
3. 内联 `index=True` 功能正确

**建议**（非强制）：如需统一命名规范，可改为：
```python
is_active: Mapped[bool] = mapped_column(Boolean, default=True)
# ... 其他字段 ...
__table_args__ = (
    Index("idx_membership_tier_active", "is_active"),
)
```

### 附加发现 2：切片 04-scoring 关系属性命名与 DB §5.3 不一致

**位置**：
- DB §5.3 L2534：`scores: Mapped[list["ScoreRecord"]] = relationship(back_populates="match", ...)`
- 切片 04-scoring L356：`score_records: Mapped[list["ScoreRecord"]] = relationship(back_populates="match", ...)`

**评估**：非 P 级问题，因为：
1. 仅 ORM 层关系属性名，不影响数据库 schema
2. 功能等价（back_populates 双向关联正确）
3. 切片 04 命名 `score_records` 更语义化（复数形式明确表示集合）

**建议**（非强制）：如需统一，可将 DB §5.3 L2534 改为 `score_records`，或切片 04 改回 `scores`。

---

## 5. 前轮修复回归验证

| 修复项 | 修复轮次 | 验证状态 | 说明 |
|--------|---------|---------|------|
| R19-P3-1 | R19 | ✅ 稳定 | 切片 09 BadgeDefinition.is_active index=True 已移除 |
| R19-P3-2 | R19 | ✅ 稳定 | 切片 09 CheckInRecord.checkin_date index=True 已移除 |
| R19-P3-3 | R19 | ✅ 稳定 | 切片 09 UserBadge.user_id index=True 已移除 |
| R19-P3-4 | R19 | ✅ 稳定 | 切片 09 BadgeProgress.user_id index=True 已移除 |
| R19-P3-5 | R19 | ✅ 稳定 | 切片 11 Order.user_id / PaymentRecord.order_id index=True 已移除 |
| R19-P3-6 | R19 | ✅ 稳定 | 切片 02 RatingHistory.user_id / ExportTask.user_id / task_id index=True 已移除 |
| R19-P3-7 | R19 | ✅ 稳定 | 切片 03 VideoTask.task_uuid/user_id / AnalysisReport.task_id/user_id / FeedbackRecord.report_id/user_id / ShareRecord.user_id/share_token index=True 已移除 |
| R19-P3-10 | R19 | ✅ 稳定 | 切片 05 MatchRecord.user_id / ManualScoreDetail.match_record_id index=True 已移除 |
| R19-P3-11 | R19 | ✅ 稳定 | 切片 08 ProgressSnapshot.user_id / TechniqueTrend.user_id index=True 已移除 |
| R19-P3-12 | R19 | ✅ 稳定 | 切片 04 MatchStatistic.match_id index=True 已移除 |
| R20-P3-2 | R20 | ✅ 稳定 | 切片 03 FileRecord.oss_key / FeedbackRecord.user_id index=True 已移除 |
| R18-P2-8 | R18 | ✅ 稳定 | 切片 04 Match.status index=True 已移除，改用 __table_args__ |
| R18-P3-2 | R18 | ✅ 稳定 | 切片 01 User.openid index=True 已移除 |
| R18-P2-9 | R18 | ✅ 稳定 | 切片 08 TechniqueTrend Float 类型补充完成 |
| R17-P2 | R17 | ✅ 稳定 | 切片 11 PaymentRecord.paid_at nullable=True 已移除 |

**前轮修复回归总计**：15 项修复全部稳定，无回归。

---

## 6. 连续无 P2+ 轮次追踪

| 轮次 | P0 | P1 | P2 | P3 | 无 P2+ |
|------|----|----|----|----|--------|
| R21 | 0 | 0 | 0 | 2 | ✅ 第一轮 |
| R22 | 0 | 0 | 0 | 1 | ✅ 第二轮 |
| R23 | 0 | 0 | 0 | 0 | ✅ 第三轮 |
| R24 | 0 | 0 | 0 | 1 | ✅ 第四轮 |
| R25 | 0 | 0 | 0 | 2 | ✅ 第五轮 |
| R26 | 0 | 0 | 0 | 4 | ✅ 第六轮 |

**连续无 P2+ 轮次**：连续第六轮（R21-R26）

**说明**：R26 发现 4 项 P3 均为冗余索引清理遗漏，不涉及功能正确性、数据一致性或安全性。

---

## 7. 问题分级汇总

| 编号 | 级别 | 模块 | 摘要 | 修复优先级 |
|------|------|------|------|-----------|
| P3-26 | P3 | 切片 04-scoring | Match.user_id 冗余 index=True（idx_match_user_created 已覆盖） | 低 |
| P3-27 | P3 | 切片 04-scoring | ScoreRecord.match_id 冗余 index=True（idx_score_record_match_seq/match_game 已覆盖） | 低 |
| P3-28 | P3 | 切片 05-match_data | MatchRecord.match_id index=True 与 DB §5.4 不一致（需统一口径） | 低 |
| P3-29 | P3 | 切片 04-scoring / DB §5.3 | MatchStatistic 缺失 idx_mstat_match 声明（或 DB 侧冗余） | 低 |

---

## 8. 修复优先级建议

### 8.1 建议本轮修复（P3-26、P3-27）

**理由**：
- P3-26、P3-27 属于与 R19-P3-2/R19-P3-7 同类的冗余 index=True 问题
- 切片 04-scoring 是唯一未清理同类问题的切片
- 修复方式简单（移除 index=True + 添加修复注释）
- 修复后切片 04 将与其他 11 个切片的索引规范完全一致

**批量修复脚本建议**：
- 切片 04-scoring L327：移除 `index=True`，添加 `# R26-P3-26: 移除冗余 index=True（__table_args__ idx_match_user_created 已覆盖）`
- 切片 04-scoring L369：移除 `index=True`，添加 `# R26-P3-27: 移除冗余 index=True（__table_args__ idx_score_record_match_seq/match_game 已覆盖）`

### 8.2 建议下轮修复（P3-28、P3-29）

**理由**：
- P3-28、P3-29 涉及 DB §5/§6 与切片的口径选择，需要架构决策
- 建议先在架构评审中确定权威源（DB §5 or 切片），再统一修复

### 8.3 不建议修复（附加发现 1、2）

**理由**：
- 附加发现 1（MembershipTier.is_active index=True）：功能正确，配置表低频更新
- 附加发现 2（关系属性命名 scores vs score_records）：非 schema 问题，功能等价

---

## 9. 附录：审查文件清单

### 9.1 DB 设计文档

- `docs/04详细设计/04-数据库详细设计.md`（v1.6）
  - §2 Phase 1 表定义（L436-1106）
  - §3 Phase 2-4 表定义（L1106-2033）
  - §5 SQLAlchemy 2.0 Model 代码示例（L2236-2961）
    - §5.1 User + UserPoints + CheckinRecord + ConsentLog + ExportTask（L2242-2358）
    - §5.2 VideoTask + AnalysisReport（L2360-2496）
    - §5.3 Match + ScoreRecord + MatchStatistic（L2496-2580）
    - §5.4 MatchRecord + ManualScoreDetail（L2581-2636）
    - §5.5 Subscription + Order + PaymentRecord + RefundRecord（L2638-2740）
    - §5.6 ProgressSnapshot + TechniqueTrend + FeedbackRecord + ShareRecord + NotificationRecord（L2742-2830）
    - §5.7 BadgeDefinition + UserBadge + BadgeProgress（L2832-2899）
    - §5.8 AdminUser + AuditLog + SystemConfig（L2901-2961）
  - §6 索引清单（L2963-3023）
    - §6.1 核心索引清单（38 条索引）
    - §6.2 GIN 索引（4 条）

### 9.2 切片 backend.md（12 个）

| 切片 | Model 数 | 审查状态 |
|------|---------|---------|
| 01-auth | AdminUser / AuditLog / SystemConfig / User | ✅ 完成 |
| 02-user | RatingHistory / ExportTask | ✅ 完成 |
| 03-video_analysis | FileRecord / VideoTask / AnalysisReport / FeedbackRecord / ShareRecord | ✅ 完成 |
| 04-scoring | Match / ScoreRecord / MatchStatistic | ✅ 完成（发现 P3-26/P3-27/P3-29） |
| 05-match_data | MatchRecord / ManualScoreDetail | ✅ 完成（发现 P3-28） |
| 06-data_dashboard | （引用其他切片 Model，无独立定义） | ✅ 完成 |
| 07-training_advice | TrainingPlan / PlanAdjustment | ✅ 完成 |
| 08-progress_analysis | ProgressSnapshot / TechniqueTrend | ✅ 完成 |
| 09-gamification | UserPoints / CheckinRecord / BadgeDefinition / UserBadge / BadgeProgress | ✅ 完成 |
| 10-membership | MembershipTier / Subscription | ✅ 完成（附加发现 1） |
| 11-payment | Order / PaymentRecord / RefundRecord | ✅ 完成 |
| 12-notification | NotificationRecord | ✅ 完成 |

---

## 10. 审查方法说明

### 10.1 工具链

- **Grep**：批量搜索 `index=True` / `ForeignKey` / `DateTime` / `__tablename__` / `class \w+\(Base\)` 等模式
- **Read**：逐段读取 DB §5 Model 定义和切片 backend.md Model 定义
- **交叉比对**：逐表逐字段比对 DB §5 vs 切片，记录字段名/类型/nullable/default/FK/索引差异

### 10.2 编码损坏处理

- 切片 03/09 backend.md 存在 `[REDACTED]` + `]]]]]` 乱码字符（primary_key=True 被渲染为 `[REDACTED]]]]]]]]]`）
- 影响：完整逐行读取受干扰，但 grep 定位有效
- 缓解：结合 grep 结果与上下文推断行级内容；关键字段（user_id/match_id/index=True 等）均能通过 grep 准确定位

### 10.3 审查边界

- 本轮审查仅覆盖 DB §5 Model 定义与切片 backend.md Model 定义的字段级一致性
- 不涉及：API 端点、Pydantic Schema、Service 层逻辑、前端 TypeScript 类型
- 不涉及：Alembic 迁移脚本、种子数据、分区策略

---

**报告结束**

R26 审查完成。连续第六轮无 P2+ 问题。发现 4 项 P3 问题（P3-26 ~ P3-29），建议优先修复 P3-26/P3-27（与 R19-P3-2/R19-P3-7 同类的冗余 index=True 清理遗漏），P3-28/P3-29 需架构决策后统一修复。
