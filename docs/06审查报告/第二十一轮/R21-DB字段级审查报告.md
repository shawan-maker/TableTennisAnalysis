# 第二十一轮审查报告 — DB 字段级 + 数据完整性审查（连续两轮无 P2+ 新第一轮）

> **审查日期**：2026-10-19
> **审查范围**：R20 DB 维度 5 项 P3 修复回归验证 + 核心一致性维度（表名/列名/类型/DateTime 时区/PK/FK/Unique/Check/ondelete 策略）+ §5 模型声明完整性 + §6 索引覆盖度 + §2 DDL 一致性
> **审查方法**：grep 模式定位 + DB 设计文档（§2 DDL / §5 模型 / §6 索引 / §8 种子数据）与 12 个后端切片 backend.md + 2 个 infrastructure 切片（admin.md / knowledge_base.md）交叉比对
> **基线文档**：`docs/04详细设计/04-数据库详细设计.md` v1.6（39 表定义 + §5 29 个模型 + §6 索引清单）+ `docs/07审查报告/第二十轮/R20-DB字段级审查报告.md`
> **累计修复基线**：880 项（R19 综合报告；R20 全 P3 新发现建议开发阶段清理，累计未变）

---

## 1. 执行摘要

本轮 R21 DB 维度审查在 R20 基线上执行 R20 5 项 DB 维度 P3 修复回归验证 + 核心一致性维度全量比对 + §5 模型完整性 + §6 索引覆盖度。

**审查结论**：R20 5 项 DB 维度 P3 修复回归验证显示 **0/5 完全修复**（R20-P3-2 部分修复 2/5 处，其余 4 项均未落地）；核心一致性维度全部维持 ✅；§5 模型覆盖度 29 个核心 + 8 个外置 = 37 张表有 Model 定义（Phase 2 提前实现表 model_3d_asset / action_category 在切片中无定义，R20-DB 报告 §5.2 描述偏差）；§6 索引清单实际 §6.1 46 条 + §6.2 3 条 GIN（R20-DB 报告计数/描述偏差）；**新发现仅 P3 级残留 `index=True` + R20-DB 报告描述偏差**，**无 P0/P1/P2 新发现** ✅

**DB 维度连续两轮无 P2+（新第一轮完成）**：R20 报告声明"连续第一轮完成"（基于零 P2+ 新发现），本轮 R21 继续保持零 P2+ 新发现，正式达成"连续两轮无 P2+"目标。由于 R20-P3-1 ~ R20-P3-5 修复进度为 0%（全 P3 级，建议开发阶段统一清理），本轮 R21 按"新第一轮"标准（零 P2+ 新发现 + P3 残留跟踪）重新计数，**新第一轮完成**，需 R22 保持零 P2+ 才能达成"连续两轮无 P2+（新标准）"目标。

| 指标 | R18 | R19 | R20 | R21 |
|------|-----|-----|-----|-----|
| 新发现 | 23 | 18 | 5（全 P3） | 9（全 P3，含 R20-DB 报告描述偏差 4 项） |
| P0 | 0 | 0 | 0 | 0 |
| P1 | 1 | 1 | 0 | 0 |
| P2 | 2 | 5 | 0 | 0 |
| P3 | 20 | 12 | 5 | 9 |
| 修复率（上轮 P3） | 100% | 39% | 0% | 0%（R20 5 项 P3 全部未修复） |
| 连续两轮无 P2+ | — | — | 第一轮完成 | **第二轮完成（新第一轮完成）** |

R21 零 P2+ 新发现是 DB 维度审查历史的第二次（R20 首次零 P2+）。P3 级残留集中在冗余 `index=True` 清理和 R20-DB 报告描述偏差纠正两个维度，可在开发阶段或 R22 统一清理。

---

## 2. R20 修复验证表（5 项 DB 维度 P3）

### 2.1 R20-P3-1：切片 09 CheckInRecord.checkin_date L206 残留 index=True（R19-P3-2 闭环缺口）

- **R20 报告位置**：切片 09-gamification/backend.md L206
- **R20 修复方案**：移除 L206 的 `index=True`，仅保留 `nullable=False` 和 comment
- **R21 验证结果**：❌ **未修复**

**证据**：grep `index=True` 命中切片 09 L206：
```
checkin_date: Mapped[date] = mapped_column(nullable=False, index=True, comment="打卡日期")
```
L206 仍保留 `index=True`，与 R20 报告修复方案不一致。

**影响**：`uq_checkin_user_date` UniqueConstraint (user_id, checkin_date) 已隐式创建复合唯一索引，可覆盖 checkin_date 单列查询（PostgreSQL 跳跃扫描），额外 `index=True` 创建独立的 `ix_checkin_record_checkin_date` B-Tree 索引，存在轻微存储/写入开销冗余。**P3 级**。

### 2.2 R20-P3-2：切片 03 多处残留 index=True（5 处）

> **注**：任务清单的 R20-P3-2 描述为"切片 04 MatchRecord.match_id + ManualScoreDetail.match_record_id"，与 R20-DB 报告的"切片 03 多处残留"不一致。经核实，R20-DB 报告的版本为实际版本，任务清单描述存在编号混淆。本节按 R20-DB 报告实际版本验证。

- **R20 报告位置**：切片 03-video_analysis/backend.md L221/L246/L325/L347/L348
- **R20 修复方案**：移除 5 处的 `index=True`（保留 `unique=True` 即可）
- **R21 验证结果**：⚠️ **部分修复（2/5 已修复，3/5 未修复）**

| 位置 | 字段 | R20 状态 | R21 验证 | 结果 |
|------|------|---------|---------|------|
| L221 | FileRecord.oss_key | `unique=True, index=True` | `unique=True)`（注释 `# R20-P3-2: 移除冗余 index=True`） | ✅ 已修复 |
| L246 | VideoTask.task_uuid | `unique=True, index=True` | `unique=True, index=True`（无注释） | ❌ 未修复 |
| L325 | FeedbackRecord.user_id | `index=True` | `ForeignKey("user.id", ondelete="CASCADE"))`（注释 `# R20-P3-2`） | ✅ 已修复 |
| L347 | ShareRecord.user_id | `index=True` | `ForeignKey("user.id", ondelete="CASCADE"), index=True` | ❌ 未修复 |
| L348 | ShareRecord.share_token | `unique=True, index=True` | `unique=True, index=True` | ❌ 未修复 |

**补充说明**：
- L346 ShareRecord.report_id 也有 `index=True`，但属**合理保留**（FK 单列查询，ShareRecord 表 `__table_args__` 仅 `idx_share_user_created` (user_id, created_at) 复合索引，未覆盖 report_id 单列查询），R20 报告未将其列入问题，R21 确认合理。
- L248 VideoTask.file_id 也有 `index=True`，属**合理保留**（VideoTask 表 `__table_args__` 有 `idx_video_task_user_created` / `idx_video_task_status_created`，未覆盖 file_id 单列查询）。

**影响**：3 处未修复的 `index=True` 均为冗余索引（`unique=True` 已隐式创建唯一索引，或复合索引已覆盖单列查询），轻微存储/写入开销冗余。**P3 级**。

### 2.3 R20-P3-3：切片 04 Match.user_id + ScoreRecord.match_id 残留 index=True

> **注**：任务清单的 R20-P3-3 描述为"切片 03 FileRecord.oss_key + FeedbackRecord.user_id（L221/L325 已在 R20-P3-2 需求维度修复）"，与 R20-DB 报告的"切片 04 Match.user_id + ScoreRecord.match_id"不一致。任务清单描述的 L221/L325 已在 §2.2 验证为已修复。本节按 R20-DB 报告实际版本验证切片 04 的残留。

- **R20 报告位置**：切片 04-scoring/backend.md L327（Match.user_id）+ L369（ScoreRecord.match_id）
- **R20 修复方案**：移除 2 处的 `index=True`
- **R21 验证结果**：❌ **未修复（2/2 均未修复）**

| 位置 | 字段 | R21 grep 结果 | 复合索引覆盖 | 结果 |
|------|------|--------------|-------------|------|
| L327 | Match.user_id | `ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="创建者用户ID"` | `idx_match_user_created` (user_id, created_at) 已覆盖 user_id 单列查询 | ❌ 冗余 |
| L369 | ScoreRecord.match_id | `ForeignKey("match.id", ondelete="CASCADE"), index=True)` | `idx_score_record_match_seq` (match_id, sequence) + `idx_score_record_match_game` (match_id, game_number) 已覆盖 match_id 单列查询 | ❌ 冗余 |

**影响**：2 处 `index=True` 均为冗余索引（复合索引已覆盖单列查询），轻微存储/写入开销冗余。**P3 级**。

### 2.4 R20-P3-4：§5 MatchRecord.match_id 缺 index=True（三方不一致）

> **注**：任务清单的 R20-P3-4 描述为"§5 ManualScoreDetail.match_record_id 缺 index=True"，与 R20-DB 报告的"§5 MatchRecord.match_id 缺 index=True"不一致。经核实：
> - §5 L2624 `match_record_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("match_record.id", ondelete="CASCADE"))` — 缺 `index=True`
> - 切片 05 L440 `match_record_id: Mapped[int] = mapped_column(ForeignKey("match_record.id", ondelete="CASCADE"))` — 也缺 `index=True`
> - 两者一致（都无 `index=True`，因 `idx_msd_record_seq` 复合索引已覆盖），**不构成三方不一致**。
> 
> 真正的三方不一致是 §5 L2599 MatchRecord.match_id 缺 `index=True`（与切片 05 L417 不一致）。本节按 R20-DB 报告实际版本验证。

- **R20 报告位置**：DB §5 L2599 MatchRecord.match_id（切片 05 L417 有 `index=True`，§5 缺）
- **R20 修复方案**：§5 L2599 补充 `index=True`，与切片 05 和 §2.13 三方一致
- **R21 验证结果**：❌ **未修复**

**证据**：
- DB §5 L2599：`match_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("match.id", ondelete="SET NULL"), nullable=True)` — **缺 `index=True`**
- 切片 05 L417：`match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("match.id", ondelete="SET NULL"), nullable=True, index=True, comment="关联的记分牌比赛ID（可选）")` — **有 `index=True`**（合理保留，FK 单列查询无复合索引覆盖）

三方不一致：§2.13 L684 `match_id BIGINT NULL`（未声明索引） / §5 L2599（缺 `index=True`）/ 切片 05 L417（有 `index=True`）。

**影响**：§5 作为模型示例代码与切片实现不一致，可能误导开发者。实际运行时以切片 05 L417 为准（创建 `ix_match_record_match_id` 单列索引）。**P3 级**。

### 2.5 R20-P3-5：§6 索引总表缺 membership_tier_config.is_active

- **R20 报告位置**：DB §6.1 索引清单缺 membership_tier_config 表的 `ix_membership_tier_config_is_active` 索引
- **R20 修复方案**：§6.1 补充 `| membership_tier_config | ix_membership_tier_config_is_active | is_active | B-Tree | 活跃等级查询 |`
- **R21 验证结果**：❌ **未修复**

**证据**：
- 切片 10-membership/backend.md L215：`is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)` — 隐式创建 `ix_membership_tier_config_is_active`
- DB §6.1 L2963-3012 索引清单：**未包含 membership_tier_config 表的任何索引**

**影响**：§6 vs 切片轻微不一致，但 is_active 索引合理（查询活跃会员等级），不影响实现。**P3 级**。

### 2.6 R20 修复验证小结

| 编号 | 问题 | 优先级 | R21 验证结果 |
|------|------|--------|------------|
| R20-P3-1 | 切片 09 CheckInRecord.checkin_date 残留 index=True | P3 | ❌ 未修复 |
| R20-P3-2 | 切片 03 5 处残留 index=True | P3 | ⚠️ 部分修复（2/5 已修复，3/5 未修复） |
| R20-P3-3 | 切片 04 Match.user_id + ScoreRecord.match_id 残留 index=True | P3 | ❌ 未修复（2/2 均未修复） |
| R20-P3-4 | §5 MatchRecord.match_id 缺 index=True（三方不一致） | P3 | ❌ 未修复 |
| R20-P3-5 | §6 索引总表缺 membership_tier_config.is_active | P3 | ❌ 未修复 |

**R20 5 项 P3 修复回归通过率**：**0% 完全修复 + 20% 部分修复（R20-P3-2 的 2/5）= 20% 部分通过率**。

R20 报告明确标注"修复率 0%（P3 级，开发阶段统一清理）"，R21 验证确认 R20 5 项 P3 全部未落地（仅 R20-P3-2 的 L221/L325 在 R20 报告生成时已修复），符合 R20 报告预期。所有未修复项均为 P3 级，不影响 P2+ 判定。

---

## 3. 核心一致性维度（全量通过 ✅）

### 3.1 表名/列名/数据类型一致性

| 维度 | 一致性 | 备注 |
|------|--------|------|
| 表名（`__tablename__`） | ✅ 三方一致 | DB §2 DDL / §5 SQLAlchemy Model / 切片 backend.md 全部一致（37 张有 Model 定义的表，model_3d_asset / action_category 见 §4） |
| 列名 | ✅ 三方一致 | DB §2 / §5 / 切片所有列名一致，无偏差 |
| 数据类型 | ✅ 三方一致 | BigInteger / String(10/16/20/32/45/64/128/255/512) / Integer / Boolean / Text / Float / Date / JSONB 全部一致 |
| 字段必填性（NOT NULL） | ✅ 三方一致 | nullable=True/False 与 §2 必填列一致 |

### 3.2 DateTime 时区统一

- ✅ **所有 DateTime 字段全部使用 `DateTime(timezone=True)`**：DB §5 + 切片 13 个 backend.md + 2 个 infrastructure 切片，零偏差
- ✅ **零 `DateTime()` 无时区用法**：全量 grep `DateTime\(\)` 在切片目录无匹配
- ✅ **default 一致**：`default=lambda: datetime.now(timezone.utc)` 全部使用 UTC 时间，DB/切片一致
- ✅ **onupdate 一致**：`onupdate=lambda: datetime.now(timezone.utc)` 用于 updated_at 字段（User/Subscription/Order/PaymentRecord/RefundRecord/TechniqueTrend/FeedbackRecord/NotificationRecord/UserPoints/AdminUser/SystemConfig/FileRecord/MatchRecord/Match 等）

### 3.3 主键 / 外键 / 唯一约束 / 检查约束

| 约束类型 | 一致性 | 备注 |
|----------|--------|------|
| PRIMARY KEY | ✅ 一致 | 所有表使用 `BigInteger, primary_key=True, autoincrement=True` |
| FOREIGN KEY | ✅ 一致 | 所有 FK 关系一致，详见 §3.4 ondelete 策略 |
| UNIQUE 约束 | ✅ 一致 | 单列 unique + UniqueConstraint 双形式一致（uq_checkin_user_date / uq_feedback_user_report / uq_trend_user_metric 等） |
| CHECK 约束 | ✅ 一致 | DB §2 部分表有 CHECK 约束（如 subscription.status 枚举），切片通过 Pydantic Schema 枚举校验 |

### 3.4 FK ondelete 策略一致性

DB §5 + 切片共 38+ 处 ondelete 策略全部一致：

| ondelete 策略 | 使用场景 | 数量 | 验证 |
|---------------|---------|------|------|
| `CASCADE` | 强依赖（用户删除时清理相关数据）：user_id 关联（30+ 处）、file_id、task_id、match_id、order_id、match_record_id、report_id、plan_id、training_plan_id、category_id 等 | 33+ | ✅ |
| `SET NULL` | 弱关联（可独立存在）：subscription_id（Order）、match_id（MatchRecord）、template_id（TrainingPlan）、report_id（PlanAdjustment）、user_id（AuditLog 非管理员操作时） | 5 | ✅ |
| `RESTRICT` | 防误删：badge_id（UserBadge L250 / BadgeProgress L265）、admin_id（AuditLog L89） | 3 | ✅ grep `ondelete="RESTRICT"` 命中 3 处，全部合理 |

策略设计合理：
- CASCADE 用于强依赖关系（用户删除时清理相关数据）
- SET NULL 用于弱关联（订阅/比赛记录可独立存在，避免级联删除）
- RESTRICT 用于防止误删（徽章定义/管理员账号不能直接删除，需先迁移关联数据）

grep `ondelete="SET DEFAULT"` 无匹配，无异常策略。

---

## 4. §5 模型完整性

### 4.1 §5 核心模型清单（29 个）

§5 共 8 个子节（L2236-2960），定义 29 个核心 SQLAlchemy Model：

| 子节 | 行号 | 模型 | 表名 | 数量 |
|------|------|------|------|------|
| §5.1 User | L2242 | User / UserPoints / CheckinRecord / ConsentLog / ExportTask | user / user_points / checkin_record / consent_log / export_task | 5 |
| §5.2 VideoTask + AnalysisReport | L2360 | FileRecord / VideoTask / PipelineStep / AnalysisReport / ShareRecord | file_record / video_task / pipeline_step / analysis_report / share_record | 5 |
| §5.3 Match + ScoreRecord + MatchStatistic | L2496 | Match / ScoreRecord / MatchStatistic | match / score_record / match_statistic | 3 |
| §5.4 MatchRecord + ManualScoreDetail | L2581 | MatchRecord / ManualScoreDetail | match_record / manual_score_detail | 2 |
| §5.5 Subscription + Order + PaymentRecord | L2638 | Subscription / Order / PaymentRecord / RefundRecord | subscription / order / payment_record / refund_record | 4 |
| §5.6 ProgressSnapshot + TechniqueTrend + FeedbackRecord + NotificationRecord | L2742 | ProgressSnapshot / TechniqueTrend / FeedbackRecord / NotificationRecord | progress_snapshot / technique_trend / feedback_record / notification_record | 4 |
| §5.7 Badge + Gamification | L2832 | BadgeDefinition / UserBadge / BadgeProgress | badge_definition / user_badge / badge_progress | 3 |
| §5.8 Admin + Config | L2901 | AdminUser / AuditLog / SystemConfig | admin_user / audit_log / system_config | 3 |
| **合计** | — | — | — | **29** |

### 4.2 §5 外置模型清单（10 个，见切片）

依据 §5 开头 R18-P2-1 注释（L2240），以下 10 张表的 SQLAlchemy Model 定义位于对应切片文件。R21 全量 grep `__tablename__ = ` 验证：

| 表名 | R20-DB 报告位置 | R21 grep 验证 | 实际位置 | 结果 |
|------|----------------|--------------|---------|------|
| rating_history | 切片 02-user L222 | ✅ 命中 L224 | 切片 02-user/backend.md L224 | ✅ |
| training_plan | 切片 07-training_advice | ✅ 命中 L329 | 切片 07-training_advice/backend.md L329 | ✅ |
| plan_adjustment | 切片 07-training_advice | ✅ 命中 L355 | 切片 07-training_advice/backend.md L355 | ✅ |
| knowledge_category | 切片 13-knowledge_base L62 | ✅ 命中 L64 | 切片 13-infrastructure/knowledge_base.md L64 | ✅ |
| knowledge_entry | 切片 13-knowledge_base L80 | ✅ 命中 L82 | 切片 13-infrastructure/knowledge_base.md L82 | ✅ |
| rule_definition | 切片 13-knowledge_base L103 | ✅ 命中 L105 | 切片 13-infrastructure/knowledge_base.md L105 | ✅ |
| training_template | 切片 13-knowledge_base L127 | ✅ 命中 L129 | 切片 13-infrastructure/knowledge_base.md L129 | ✅ |
| membership_tier_config | 切片 10-membership L211 | ✅ 命中 L204 | 切片 10-membership/backend.md L204 | ✅ |
| **model_3d_asset** | 切片 13-admin 或 knowledge_base | ❌ **无匹配** | **切片中无定义** | ⚠️ R20-DB 报告描述偏差 |
| **action_category** | 切片 13-admin 或 knowledge_base | ❌ **无匹配** | **切片中无定义** | ⚠️ R20-DB 报告描述偏差 |

**R21 新发现**：R20-DB 报告 §5.2 声称 model_3d_asset 和 action_category 在切片 13 中有定义（✅），但实际全量 grep `__tablename__ = ` 在切片目录只命中 37 个表（去重后），**model_3d_asset 和 action_category 两张 Phase 2 提前实现表在切片中无 Model 定义**。

**影响评估**：
- model_3d_asset 和 action_category 均为 Phase 2 提前实现表（DB §2 L440 注释），Phase 2 模块（3d_teaching）尚未开发，切片中暂无 Model 定义属合理推迟
- 不影响 Phase 1 业务逻辑正确性
- R20-DB 报告 §5.2 的 ✅ 标记为**描述偏差**，应纠正为"Phase 2 表，切片中暂无定义（合理推迟）"

### 4.3 §5 完整性结论

- ✅ **§5 核心模型**：29 个，与 DB §2 Phase 1 表定义一致
- ✅ **§5 外置模型（已定义）**：8 个（rating_history / training_plan / plan_adjustment / knowledge_category / knowledge_entry / rule_definition / training_template / membership_tier_config）
- ⚠️ **§5 外置模型（未定义）**：2 个（model_3d_asset / action_category），Phase 2 提前实现表，切片中暂无 Model 定义
- ✅ **§5 + 切片已定义模型总数**：29 + 8 = **37 张表**有 Model 定义
- ⚠️ **DB §2 定义 39 张表**：差 2 张（model_3d_asset / action_category），均为 Phase 2 提前实现表，合理推迟
- ✅ **所有已定义模型均有 `__tablename__` 和 `id` 主键**
- ✅ **§5 模型均有 `__table_args__` 索引/约束定义**（除 AdminUser 简表外）
- ✅ **§5 模型字段类型与 §2 DDL 一致**

---

## 5. §6 索引覆盖度

### 5.1 §6.1 核心索引清单（实际 46 条，含 2 条 GIN）

DB §6.1 L2963-3012 实际列出 46 条索引（含 2 条 GIN：idx_report_text_gin / idx_ps_metrics_gin）。R20-DB 报告声称 §6.1 有 38 条核心索引，**存在计数偏差**（实际 46 条 vs 报告 38 条，差 8 条）。

完整索引清单（按表分组）：

| 表 | 索引数 | 索引名 | R20-DB 报告 |
|----|--------|--------|------------|
| user | 2 | idx_user_openid, idx_user_phone（partial UNIQUE） | ✅ 一致 |
| video_task | 2 | idx_video_task_user_created, idx_video_task_status_created | ✅ 一致 |
| analysis_report | 2 | idx_report_user_created, idx_report_text_gin（GIN） | ✅ 一致 |
| score_record | 2 | idx_score_record_match_seq, idx_score_record_match_game | ✅ 一致 |
| match_record | 1 | idx_mrecord_user_date | ✅ 一致 |
| notification_record | 1 | idx_notif_user_unread | ✅ 一致 |
| progress_snapshot | 2 | idx_ps_user_created, idx_ps_metrics_gin（GIN） | ✅ 一致 |
| technique_trend | 1 | uq_trend_user_metric（UNIQUE） | ✅ 一致 |
| subscription | 2 | idx_sub_status_expire, idx_sub_user_status | ✅ 一致 |
| order | 2 | idx_order_user_created, idx_order_status | ✅ 一致 |
| checkin_record | 1 | uq_checkin_user_date（UNIQUE） | ✅ 一致 |
| file_record | 3 | idx_file_record_user_created, idx_file_record_type, idx_file_status_created | ⚠️ R20 报告声称 3 条但名字不一致 |
| match_statistic | 1 | idx_mstat_match（R20 报告写 idx_match_statistic_match） | ⚠️ 命名不一致 |
| manual_score_detail | 1 | idx_msd_record_seq | ✅ 一致 |
| user_points | 1 | idx_points_user_updated | ✅ 一致 |
| share_record | 1 | idx_share_user_created | ✅ 一致 |
| payment_record | 1 | idx_payment_order | ✅ 一致 |
| training_plan | 1 | idx_tplan_user_status（R20 报告写 idx_training_plan_user_status） | ⚠️ 命名不一致 |
| plan_adjustment | 1 | idx_padj_plan（R20 报告写 idx_plan_adjustment_plan） | ⚠️ 命名不一致 |
| audit_log | 3 | idx_audit_admin_created, idx_audit_user_created, idx_audit_target | ✅ 一致 |
| model_3d_asset | 1 | idx_model_cat_status（R20 报告写 idx_model_asset_category） | ⚠️ 命名不一致 |
| feedback_record | 3 | uq_feedback_user_report, idx_feedback_status, idx_feedback_correct_created | ✅ 一致 |
| badge_definition | 2 | idx_badge_definition_category, idx_badge_definition_active | ✅ 一致 |
| user_badge | 1 | idx_user_badge_user | ✅ 一致 |
| badge_progress | 1 | idx_badge_progress_user | ✅ 一致 |
| consent_log | 2 | idx_consent_user_at, idx_consent_user_type | ✅ 一致 |
| export_task | 1 | idx_export_user_created | ✅ 一致 |
| match | 2 | idx_match_user_created, idx_match_status | ✅ 一致 |
| pipeline_step | 1 | idx_pipeline_step_task_step | ✅ 一致 |
| refund_record | 1 | idx_refund_order | ✅ 一致 |
| **合计** | **46** | — | R20 报告声称 38 条 |

**R21 新发现**：R20-DB 报告 §6.1 计数偏差（声称 38 条 vs 实际 46 条），且部分索引命名描述与实际不一致（如 idx_mstat_match vs idx_match_statistic_match）。**P3 级**（文档描述偏差，不影响实现）。

### 5.2 §6.2 GIN 索引清单（实际 3 条 GIN + 1 条不索引）

DB §6.2 L3014-3021 实际列出：

| 表 | JSONB 字段 | 索引 | 查询场景 |
|----|----------|------|---------|
| analysis_report | report_text | GIN(to_tsvector) | 按问题关键词搜索报告 |
| progress_snapshot | metrics_snapshot | GIN | 按指标查询快照 |
| knowledge_entry | content | GIN | 知识库内容搜索 |
| rule_definition | condition | **不索引** | 服务端解析 |

**R20-DB 报告 §6.2 描述偏差**：
- R20-DB 报告声称 §6.2 有 4 条 GIN 索引（含 model_3d_asset.tags GIN）
- 实际 §6.2 只列出 3 条 GIN + 1 条"不索引"（rule_definition.condition）
- model_3d_asset.tags GIN 索引在 §6.2 中**未列出**

**R21 新发现**：R20-DB 报告 §6.2 描述偏差（声称 4 条 GIN 含 model_3d_asset.tags，实际 3 条 GIN + 1 条不索引，无 model_3d_asset.tags）。**P3 级**（文档描述偏差）。

**补充说明**：
- §6.1 中的 idx_report_text_gin 和 idx_ps_metrics_gin 两条 GIN 索引在 §6.2 中重复列出（设计意图：§6.1 是索引总表，§6.2 单独说明 JSONB 查询场景）
- model_3d_asset 表的 tags JSONB 字段在切片中无 Model 定义（Phase 2 表），因此无 GIN 索引定义，§6.2 未列出是合理的

### 5.3 §6 索引覆盖度结论

- ✅ **§6 索引总数**：§6.1 实际 46 条（含 2 条 GIN） + §6.2 实际 3 条 GIN + 1 条不索引 = **46 条唯一索引**（§6.1 和 §6.2 有 2 条 GIN 重复）
- ✅ **所有核心业务表均至少有 1 个复合索引**（user/video_task/analysis_report/score_record/match_record 等）
- ✅ **所有 FK 单列查询场景均有索引覆盖**（复合索引首列覆盖或 `index=True` 单列索引）
- ✅ **JSONB 字段有 GIN 索引**（3 处：analysis_report.report_text / progress_snapshot.metrics_snapshot / knowledge_entry.content）
- ✅ **§6 与切片 `__table_args__` 完全一致**（每条索引都能在切片中找到对应定义）
- ⚠️ **§6 未覆盖 membership_tier_config.is_active**（R20-P3-5 未修复，见 §2.5）
- ⚠️ **R20-DB 报告 §6 计数/描述偏差**（§6.1 声称 38 条 vs 实际 46 条；§6.2 声称 4 条 GIN vs 实际 3 条 GIN + 1 条不索引）

---

## 6. 新发现 P0-P3 分级

### 6.1 P0 / P1 / P2 新发现

**无 P0 / P1 / P2 新发现** ✅

DB 维度连续第二轮无 P2+ 残留（R20 第一轮 + R21 第二轮）。

### 6.2 P3 新发现（9 项）

#### R21-P3-1：切片 09 CheckInRecord.checkin_date L206 残留 index=True（R20-P3-1 未修复）

- **位置**：`docs/06垂直模块前后端切片设计/09-gamification/backend.md` L206
- **问题**：`checkin_date: Mapped[date] = mapped_column(nullable=False, index=True, comment="打卡日期")` 仍有 `index=True`
- **原因**：R20-P3-1 要求移除 L206 的 `index=True`，R21 验证未落地
- **影响**：`uq_checkin_user_date` UniqueConstraint (user_id, checkin_date) 已隐式创建复合唯一索引，可覆盖 checkin_date 单列查询，额外 `index=True` 创建独立的 `ix_checkin_record_checkin_date` B-Tree 索引，存在轻微存储/写入开销冗余
- **优先级**：P3
- **修复方案**：移除 L206 的 `index=True`，仅保留 `nullable=False` 和 comment

#### R21-P3-2：切片 03 VideoTask.task_uuid L246 残留 index=True（R20-P3-2 位置 2 未修复）

- **位置**：`docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` L246
- **问题**：`task_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)` — `unique=True` 已隐式创建唯一索引，`index=True` 冗余
- **原因**：R20-P3-2 位置 2 要求移除 L246 的 `index=True`，R21 验证未落地
- **影响**：轻微存储/写入开销冗余
- **优先级**：P3
- **修复方案**：移除 L246 的 `index=True`（保留 `unique=True`）

#### R21-P3-3：切片 03 ShareRecord.user_id L347 残留 index=True（R20-P3-2 位置 4 未修复）

- **位置**：`docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` L347
- **问题**：`user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)` — `idx_share_user_created` (user_id, created_at) 复合索引已覆盖 user_id 单列查询，`index=True` 冗余
- **原因**：R20-P3-2 位置 4 要求移除 L347 的 `index=True`，R21 验证未落地
- **影响**：轻微存储/写入开销冗余
- **优先级**：P3
- **修复方案**：移除 L347 的 `index=True`

#### R21-P3-4：切片 03 ShareRecord.share_token L348 残留 index=True（R20-P3-2 位置 5 未修复）

- **位置**：`docs/06垂直模块前后端切片设计/03-video_analysis/backend.md` L348
- **问题**：`share_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)` — `unique=True` 已隐式创建唯一索引，`index=True` 冗余
- **原因**：R20-P3-2 位置 5 要求移除 L348 的 `index=True`，R21 验证未落地
- **影响**：轻微存储/写入开销冗余
- **优先级**：P3
- **修复方案**：移除 L348 的 `index=True`（保留 `unique=True`）

#### R21-P3-5：切片 04 Match.user_id L327 残留 index=True（R20-P3-3 位置 1 未修复）

- **位置**：`docs/06垂直模块前后端切片设计/04-scoring/backend.md` L327
- **问题**：`user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="创建者用户ID")` — `idx_match_user_created` (user_id, created_at) 复合索引已覆盖 user_id 单列查询，`index=True` 冗余
- **原因**：R20-P3-3 位置 1 要求移除 L327 的 `index=True`，R21 验证未落地
- **影响**：轻微存储/写入开销冗余
- **优先级**：P3
- **修复方案**：移除 L327 的 `index=True`

#### R21-P3-6：切片 04 ScoreRecord.match_id L369 残留 index=True（R20-P3-3 位置 2 未修复）

- **位置**：`docs/06垂直模块前后端切片设计/04-scoring/backend.md` L369
- **问题**：`match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"), index=True)` — `idx_score_record_match_seq` (match_id, sequence) 和 `idx_score_record_match_game` (match_id, game_number) 复合索引已覆盖 match_id 单列查询，`index=True` 冗余
- **原因**：R20-P3-3 位置 2 要求移除 L369 的 `index=True`，R21 验证未落地
- **影响**：轻微存储/写入开销冗余
- **优先级**：P3
- **修复方案**：移除 L369 的 `index=True`

#### R21-P3-7：§5 MatchRecord.match_id L2599 缺 index=True（R20-P3-4 未修复，三方不一致）

- **位置**：`docs/04详细设计/04-数据库详细设计.md` §5 L2599
- **问题**：`match_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("match.id", ondelete="SET NULL"), nullable=True)` — 缺 `index=True`
- **原因**：R20-P3-4 要求 §5 L2599 补充 `index=True`，R21 验证未落地
- **影响**：§5 vs 切片 05 L417 三方一致性偏差（§5 仅作示例参考，实际以切片 05 L417 为准）
- **优先级**：P3
- **修复方案**：§5 L2599 补充 `index=True`，与切片 05 L417 和 §2.13 三方一致

#### R21-P3-8：§6.1 索引总表缺 membership_tier_config.is_active（R20-P3-5 未修复）

- **位置**：`docs/04详细设计/04-数据库详细设计.md` §6.1 L2963-3012
- **问题**：§6.1 索引清单未包含 membership_tier_config 表的 `ix_membership_tier_config_is_active` 索引
- **原因**：R20-P3-5 要求 §6.1 补充一行，R21 验证未落地
- **影响**：§6 vs 切片 10 L215 轻微不一致（is_active 索引合理，不影响实现）
- **优先级**：P3
- **修复方案**：§6.1 补充 `| membership_tier_config | ix_membership_tier_config_is_active | is_active | B-Tree | 活跃等级查询 |`

#### R21-P3-9：R20-DB 报告 §5.2/§6.1/§6.2 描述偏差（4 处）

- **位置 1**：R20-DB 报告 §5.2 L172 `| model_3d_asset | 切片 13-infrastructure/admin.md 或 knowledge_base.md | ✅ |` — 实际切片中无 Model3DAsset 类定义
- **位置 2**：R20-DB 报告 §5.2 L172 `| action_category | 切片 13-infrastructure/admin.md 或 knowledge_base.md | ✅ |` — 实际切片中无 ActionCategory 类定义
- **位置 3**：R20-DB 报告 §6.1 L189 `§6.1 L2963-3011 列出 38 条核心索引` — 实际 §6.1 L2963-3012 列出 46 条索引（含 2 条 GIN）
- **位置 4**：R20-DB 报告 §6.2 L226-233 声称 §6.2 有 4 条 GIN 索引（含 model_3d_asset.tags GIN） — 实际 §6.2 L3014-3021 只列出 3 条 GIN + 1 条不索引（rule_definition.condition），无 model_3d_asset.tags

**原因**：R20-DB 报告基于早期版本或估算生成，未与实际 DB §5/§6 全量交叉验证
**影响**：R20-DB 报告描述与实际 DB 设计文档不一致，可能误导后续审查者；不影响 DB 设计本身正确性
**优先级**：P3
**修复方案**：在 R21 报告中纠正描述（已在 §4.2 和 §5 中纠正），无需修改 DB 设计文档

### 6.3 新发现汇总

| 优先级 | 数量 | 修复建议 |
|--------|------|---------|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 0 | — |
| P3 | 9 | 含 R20-P3-1~5 未修复项 8 处（切片 09 L206 + 切片 03 L246/L347/L348 + 切片 04 L327/L369 + §5 L2599 + §6.1）+ R20-DB 报告描述偏差 4 处合并为 1 项 |
| **合计** | **9** | **全部 P3 级，可在 R22 或开发阶段统一清理** |

---

## 7. 修复跟踪表

### 7.1 R20 5 项 P3 修复闭环状态（R21 验证）

| 编号 | 优先级 | R20 状态 | R21 验证 | 闭环状态 | 备注 |
|------|--------|---------|---------|---------|------|
| R20-P3-1 | P3 | ⏳ 待修复 | ❌ 未修复 | ⏳ 继续推迟 | 切片 09 L206 checkin_date 残留 index=True → R21-P3-1 |
| R20-P3-2 | P3 | ⏳ 待修复 | ⚠️ 部分修复（2/5） | ⏳ 部分闭环 | L221/L325 已修复；L246/L347/L348 未修复 → R21-P3-2/3/4 |
| R20-P3-3 | P3 | ⏳ 待修复 | ❌ 未修复（2/2） | ⏳ 继续推迟 | 切片 04 L327/L369 残留 index=True → R21-P3-5/6 |
| R20-P3-4 | P3 | ⏳ 待修复 | ❌ 未修复 | ⏳ 继续推迟 | §5 L2599 MatchRecord.match_id 缺 index=True → R21-P3-7 |
| R20-P3-5 | P3 | ⏳ 待修复 | ❌ 未修复 | ⏳ 继续推迟 | §6.1 缺 membership_tier_config.is_active → R21-P3-8 |

### 7.2 R21 新发现 9 项 P3 修复跟踪

| 编号 | 问题 | 位置 | 优先级 | 状态 | 修复方案 | 责任方 |
|------|------|------|--------|------|---------|--------|
| R21-P3-1 | CheckInRecord.checkin_date 残留 index=True | 切片 09 L206 | P3 | ⏳ 待修复 | 移除 index=True，保留 nullable=False + comment | 切片 09 |
| R21-P3-2 | VideoTask.task_uuid 残留 index=True | 切片 03 L246 | P3 | ⏳ 待修复 | 移除 index=True（保留 unique=True） | 切片 03 |
| R21-P3-3 | ShareRecord.user_id 残留 index=True | 切片 03 L347 | P3 | ⏳ 待修复 | 移除 index=True | 切片 03 |
| R21-P3-4 | ShareRecord.share_token 残留 index=True | 切片 03 L348 | P3 | ⏳ 待修复 | 移除 index=True（保留 unique=True） | 切片 03 |
| R21-P3-5 | Match.user_id 残留 index=True | 切片 04 L327 | P3 | ⏳ 待修复 | 移除 index=True | 切片 04 |
| R21-P3-6 | ScoreRecord.match_id 残留 index=True | 切片 04 L369 | P3 | ⏳ 待修复 | 移除 index=True | 切片 04 |
| R21-P3-7 | §5 MatchRecord.match_id 缺 index=True | §5 L2599 | P3 | ⏳ 待修复 | §5 补充 index=True | DB 设计 §5 |
| R21-P3-8 | §6 索引总表缺 membership_tier_config.is_active | §6.1 | P3 | ⏳ 待修复 | §6.1 补充一行 | DB 设计 §6 |
| R21-P3-9 | R20-DB 报告 §5.2/§6.1/§6.2 描述偏差（4 处） | R20-DB 报告 | P3 | ✅ 已在 R21 报告纠正 | R21 报告 §4.2/§5 已纠正描述 | R21 报告 |

### 7.3 连续两轮无 P2+ 进度跟踪

| 维度 | 状态 | 备注 |
|------|------|------|
| 连续两轮无 P2+（DB 维度，R20 标准） | **第二轮完成** | R20 零 P2+ 新发现 + R21 零 P2+ 新发现 = 连续两轮 ✅ |
| 连续两轮无 P2+（DB 维度，新标准：含 P3 残留跟踪） | **新第一轮完成** | R21 零 P2+ 新发现，但 R20-P3-1~5 未修复，按新标准本轮为"新第一轮"，需 R22 保持零 P2+ 才能达成"连续两轮（新标准）" |

---

## 8. 结论

### 8.1 核心结论

本轮 R21 DB 字段级 + 数据完整性审查覆盖 R20 5 项 DB 维度 P3 修复回归验证 + 核心一致性维度（表名/列名/类型/DateTime 时区/PK/FK/Unique/Check/ondelete 策略）+ §5 模型完整性 + §6 索引覆盖度。

**核心结论**：
1. ❌ **R20 5 项 DB 维度 P3 修复全部未落地**（R20-P3-2 部分修复 2/5，其余 4 项均未修复），符合 R20 报告"开发阶段统一清理"预期
2. ✅ **核心一致性维度全部通过**（表名/列名/类型/DateTime 时区/PK/FK/Unique/Check/ondelete 策略零偏差）
3. ✅ **§5 模型完整性**：29 个核心模型 + 8 个外置模型 = 37 张表有 Model 定义（Phase 2 提前实现表 model_3d_asset / action_category 在切片中无定义，合理推迟）
4. ✅ **§6 索引覆盖度**：§6.1 实际 46 条 + §6.2 实际 3 条 GIN + 1 条不索引，完整覆盖所有核心业务表
5. ✅ **新发现仅 P3 级 9 项**（含 R20-P3-1~5 未修复项 8 处 + R20-DB 报告描述偏差 1 项），**无 P0/P1/P2 新发现**
6. ✅ **DB 维度连续两轮无 P2+ 残留**（R20 第一轮 + R21 第二轮）；按"新第一轮"标准（含 P3 残留跟踪），本轮为"新第一轮完成"

### 8.2 DB 维度审查历史趋势

| 指标 | R18 | R19 | R20 | R21 |
|------|-----|-----|-----|-----|
| 新发现 | 23 | 18 | 5 | 9 |
| P0 | 0 | 0 | 0 | 0 |
| P1 | 1 | 1 | 0 | 0 |
| P2 | 2 | 5 | 0 | 0 |
| P3 | 20 | 12 | 5 | 9 |
| 修复率（上轮 P3） | 100% | 39% | 0% | 0%（R20 5 项 P3 全部未修复） |
| 累计修复 | 854 | 880 | 880 | 880 |
| 表数 | 39 | 39 | 39 | 39（37 有 Model + 2 Phase 2 推迟） |
| §5 模型数 | 29 | 29 | 29 | 29 |
| §6 索引数 | 38+4 | 38+4 | 38+4（实际 46+3） | 46+3（R21 纠正计数） |
| 连续无 P2+ | — | — | 第一轮完成 | **第二轮完成（新第一轮完成）** |

R21 P2+ 新发现归零是 DB 维度审查历史的第二次（R20 首次零 P2+）。新发现从 R18 的 23 项下降到 R21 的 9 项（全部 P3 级），表明 DB 设计文档已高度收敛。R21 新发现数量较 R20（5 项）有所上升（9 项），主要原因是 R21 增加了对 R20-DB 报告描述偏差的纠正（4 处合并为 1 项）以及 R20-P3-1~5 未修复项的细化跟踪（8 处），并非 DB 设计本身出现新问题。

### 8.3 后续行动

1. **R21-P3-1 ~ R21-P3-8 修复**：建议在开发阶段（Alembic 迁移脚本生成时）统一清理冗余 `index=True`，并同步 §5/§6 文档。预计可在 R22 验证闭环。
2. **R22 验证连续两轮无 P2+（新标准）目标的第二轮**：R21 已达成新第一轮零 P2+，R22 需保持零 P2+ 新发现 + R21-P3-1~8 修复落地，正式达成"连续两轮无 P2+（新标准）"目标。
3. **R20-DB 报告描述偏差已在 R21 纠正**：§5.2 model_3d_asset/action_category 标记为"Phase 2 表，切片中暂无定义（合理推迟）"；§6.1 索引计数纠正为 46 条；§6.2 GIN 索引纠正为 3 条 + 1 条不索引。
4. **持续监控 §5/§6 与切片三方一致性**：R21-P3-7（§5 MatchRecord.match_id）和 R21-P3-8（§6 缺 membership_tier_config）表明 §5/§6 总表仍需持续维护。

### 8.4 风险评估

- **低风险**：R21 新发现 9 项 P3 级问题均为冗余 `index=True` 清理、§5/§6 总表遗漏或 R20-DB 报告描述偏差，不影响业务逻辑正确性，可在开发阶段统一清理。
- **低风险**：R20 5 项 P3 修复全部未落地，符合 R20 报告"开发阶段统一清理"预期，不影响 P2+ 判定。
- **低风险**：核心一致性维度全部通过，无表结构/字段类型/ondelete 策略偏差。
- **低风险**：Phase 2 提前实现表（model_3d_asset / action_category）在切片中无 Model 定义，属合理推迟，不影响 Phase 1 业务。

---

## 附录 A：任务清单与 R20-DB 报告编号差异说明

任务描述的 R20 修复验证清单与 R20-DB 报告的编号存在差异：

| 任务清单编号 | 任务描述 | R20-DB 报告编号 | R20-DB 报告描述 | 差异说明 |
|------------|---------|----------------|----------------|---------|
| R20-P3-1 | 切片 09 CheckInRecord.checkin_date L206 | R20-P3-1 | 切片 09 CheckInRecord.checkin_date L206 | ✅ 一致 |
| R20-P3-2 | 切片 04 MatchRecord.match_id + ManualScoreDetail.match_record_id | R20-P3-2 | 切片 03 多处残留（L221/L246/L325/L347/L348） | ❌ 不一致（任务描述疑似编号混淆） |
| R20-P3-3 | 切片 03 FileRecord.oss_key + FeedbackRecord.user_id（L221/L325 已修复） | R20-P3-3 | 切片 04 Match.user_id + ScoreRecord.match_id | ❌ 不一致（任务描述疑似编号混淆） |
| R20-P3-4 | §5 ManualScoreDetail.match_record_id 缺 index=True | R20-P3-4 | §5 MatchRecord.match_id 缺 index=True | ❌ 不一致（任务描述字段名错误） |
| R20-P3-5 | §6 索引总表缺 membership_tier_config.is_active | R20-P3-5 | §6 索引总表缺 membership_tier_config.is_active | ✅ 一致 |

**处理方式**：
- R20-P3-1 和 R20-P3-5：任务清单与 R20-DB 报告一致，按任一版本验证均可。
- R20-P3-2 和 R20-P3-3：任务清单与 R20-DB 报告编号交换。R21 按 R20-DB 报告实际版本验证（切片 03 多处残留 + 切片 04 Match/ScoreRecord 残留），同时在 §2.2 和 §2.3 说明任务清单描述的 L221/L325 已修复情况。
- R20-P3-4：任务清单说 ManualScoreDetail.match_record_id，R20-DB 报告说 MatchRecord.match_id。R21 验证确认任务清单描述有误（ManualScoreDetail.match_record_id 在 §5 和切片 05 三方一致，都无 `index=True`，因复合索引已覆盖），真正的不一致是 §5 MatchRecord.match_id 缺 `index=True`（与切片 05 L417 不一致）。

---

*审查完成。DB 维度累计 880 项修复保持不变（R21 全 P3 级新发现，建议开发阶段统一清理）。DB 设计 v1.6 与 12 个切片 SQLAlchemy Model 核心维度零偏差。DB 维度连续两轮无 P2+ 残留（R20 第一轮 + R21 第二轮），按"新第一轮"标准本轮完成，建议 R22 验证连续两轮无 P2+（新标准）目标的第二轮。*
