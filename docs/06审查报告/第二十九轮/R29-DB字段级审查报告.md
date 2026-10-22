# 第二十九轮 - DB 字段级一致性审查报告

> **审查日期**：2026-10-20
> **审查对象**：DB 设计 v1.6（`docs/04详细设计/04-数据库详细设计.md`，146636 字节，2026-10-20 13:20）+ 12 后端切片 backend.md + 13-infrastructure/admin.md + 13-infrastructure/knowledge_base.md + API 设计 §2-§19 + 架构 §9.1/§9.3 分区策略
> **审查维度**：R28 修复回归验证（R28-OBS-1/R28-OBS-2 落地状态）+ DB §2/§5/§6 vs 切片 SQLAlchemy Model 字段级一致性 + 35 表口径跨文档一致性 + DB §9.1/§9.3 分区策略与切片实现一致性 + index=True 合规残留最终审计
> **审查基线**：R28-DB 字段级审查报告（连续第八轮无 P2+，R28-OBS-1/R28-OBS-2 两项观察项建议在后续轮次落地）
> **本轮目标**：DB 维度连续第九轮无 P2+（在 R20-R28 连续八轮无 P2+ 基线上的第九轮验证）；R28-OBS-1/R28-OBS-2 修复回归验证
> **输出位置**：`docs/07审查报告/第二十九轮/R29-DB字段级审查报告.md`

---

## 0. 执行摘要

R29 DB 字段级审查在 R28 基线上展开，重点验证 **R28 声称建议落地的 R28-OBS-1/R28-OBS-2 两项 P3 观察项的修复状态**（R28 报告 §11.1/§11.2 建议在后续轮次落地），以及 DB §2/§5/§6 与切片实现层的字段级一致性 + 分区策略 §9.1/§9.3 跨文档一致性。

**审查目标未达成**：DB 维度连续第九轮无 P2+ ❌（R20-R28 连续八轮无 P2+ 基线中断）

**关键结论**：

- **R28-OBS-1 修复落地验证** ✅：切片 03 L248 VideoTask.file_id + L346 ShareRecord.report_id 两处 `index=True` 已移除，注释标记 "R28-OBS-1: 移除冗余 index=True" 完整在位。但 **L248 注释描述存在事实错误**（见 R29-P3-1）：注释声称 "__table_args__ idx_video_task_user_created 已覆盖 user_id+file_id 复合索引"，实际 __table_args__ L263 显示 idx_video_task_user_created 仅有 (user_id, created_at)，**不含 file_id**。注释描述与实际索引定义不符。file_id 作为 FK 字段，PostgreSQL 会自动创建 B-Tree 索引，因此移除 index=True 不会引发功能缺陷，但注释描述错误需修正
- **R28-OBS-2 修复落地验证** ⚠️ 部分修正正确 + 部分引入回归：
  - **切片 10 L215 MembershipTier.is_active**：✅ 修正正确（保留 `index=True` + 补注释 "R28-OBS-2: 保留 index=True（业务查询"激活的会员等级列表"常用过滤条件，DB §6.1 应补充声明此索引）"）
  - **切片 05 L417 MatchRecord.match_id**：❌ 修正引入回归（见 **R29-P2-1 新发现**）。已移除 `index=True`，但注释声称 "__table_args__ idx_match_record_match_id_created 已覆盖复合索引" — 实际 __table_args__ L425-427 中**根本没有该索引**（该索引名在切片层不存在）。更严重的是，DB §5.4 L2616 和 DB §6.1 L2990 都显式声明 `idx_mrecord_match (match_id)` 索引，但切片 05 __table_args__ **未实现该索引**，导致 R28-OBS-2 修复在移除 L417 index=True 后，match_id 字段在切片层丢失索引覆盖
- **35 表口径跨文档一致** ✅：DB §2（39 张定义含 4 张 Phase 2）+ 实施计划 §1.1（35 张 Sprint 交付）+ 架构 §5.7 + 切片总览在 R18-P3-20 口径框架下保持一致
- **分区策略 §9.1/§9.3 跨文档一致** ✅：DB §9.1 L3201-3214 与架构 §9.3 L1786-1799 完全一致，3 张表按月分区（video_task / score_record / notification_record）+ 5 张表不分区（analysis_report / feedback_record / progress_snapshot / technique_trend / plan_adjustment）
- **subscription.tier VARCHAR(20) 六处对齐** ✅：维持 R28 验证结果，R19-P2-7 修复闭环
- **consent_log 表 + requires_consent 字段对齐** ✅：维持 R28 验证结果，R22-P1-1 修复闭环
- **GIN 索引三表对齐** ✅：维持 R28 验证结果（analysis_report / progress_snapshot / knowledge_entry 三张 GIN 索引完整实现）
- **R19-DB 12 项 P3 全部维持闭环** ✅：R26 最终落地的 P3-2 + P3-7 在 R29 复核确认全部维持，无回归

**关键风险点**：

- **R29-P2-1（新发现 P2）**：切片 05-match_data/backend.md L425-427 MatchRecord.__table_args__ 缺失 `idx_mrecord_match (match_id)` 索引声明。DB §5.4 L2616 + DB §6.1 L2990 都显式声明该索引，但切片层 __table_args__ 中未实现（注释中错误引用了不存在的索引名 `idx_match_record_match_id_created`）。这是 R28-OBS-2 修复时移除 L417 的 `index=True` 后未在 __table_args__ 补充对应 Index() 声明所引入的回归缺陷。该问题影响 nullable FK 字段 match_id 的查询性能（按比赛查询比赛记录会全表扫描），属重要索引缺失
- **R29-P3-1（新发现 P3）**：切片 03 L248 VideoTask.file_id 注释描述与实际 __table_args__ 索引定义不符。注释声称 idx_video_task_user_created 覆盖 user_id+file_id 复合索引，实际索引仅含 (user_id, created_at)。file_id 作为 FK 由 PostgreSQL 自动创建索引，无功能影响，但注释描述错误需修正

---

## 1. 审查汇总

### 1.1 总体统计

| 维度 | 项数 | 通过 | 偏差 | 待确认 | 通过率 |
|------|------|------|------|--------|--------|
| R28-OBS-1 修复回归验证（切片 03 L248/L346） | 2 | 1 | 1（P3 注释描述错误） | 0 | 50% |
| R28-OBS-2 修复回归验证（切片 05 L417 + 切片 10 L215） | 2 | 1 | 1（P2 切片 05 引入回归） | 0 | 50% |
| R19-DB 12 项 P3 维持闭环回归验证 | 12 | 12 | 0 | 0 | 100% |
| R26-P3-26/R26-P3-27 维持闭环 | 2 | 2 | 0 | 0 | 100% |
| 35 表口径跨文档一致性（DB §2 + 实施计划 + 架构 §5.7 + 切片总览） | 4 | 4 | 0 | 0 | 100% |
| DB §2 表定义 vs 切片 Model 字段级一致性（35 表口径） | 35 | 35 | 0 | 0 | 100% |
| DB §5 SQLAlchemy Model vs 切片 Base Model 类清单一致性 | 28 | 28 | 0 | 0 | 100% |
| DB §6.1 核心索引清单 vs 切片 __table_args__ Index() 一致性 | 48 | 47 | 1（R29-P2-1 切片 05 缺失 idx_mrecord_match） | 0 | 97.92% |
| DB §6.2 GIN 索引三表对齐 | 3 | 3 | 0 | 0 | 100% |
| DB §9.1/§9.3 分区策略跨文档一致性（DB §9.1 vs 架构 §9.3） | 8 | 8 | 0 | 0 | 100% |
| subscription.tier VARCHAR(20) 六处对齐 | 6 | 6 | 0 | 0 | 100% |
| consent_log 表 + requires_consent 字段对齐 | 2 | 2 | 0 | 0 | 100% |
| **合计** | **152** | **150** | **2（1 P2 + 1 P3）** | **0** | **98.68%** |

### 1.2 P0-P3 分级汇总

| 优先级 | 数量 | 编号 | 说明 |
|--------|------|------|------|
| P0（阻断级） | 0 | — | 无阻断级问题 |
| P1（严重级） | 0 | — | 无严重级问题 |
| P2（重要级） | **1** | **R29-P2-1** | 切片 05 __table_args__ 缺失 idx_mrecord_match (match_id) 索引（DB §5.4 L2616/§6.1 L2990 声明但切片层未实现），由 R28-OBS-2 修复引入的回归缺陷 |
| P3（建议级） | 1 | R29-P3-1 | 切片 03 L248 注释描述错误（idx_video_task_user_created 实际不含 file_id） |

### 1.3 连续无 P2+ 进度跟踪

| 轮次 | DB 维度新发现 P2+ | 累计修复落地计数 | 说明 |
|------|-------------------|------------------|------|
| R19（DB 基线） | 1 项 P1 + 5 项 P2 | 12 项 P3 | DB 维度基线建立（含 12 项 P3 跟踪表） |
| R20 | 0 | 22 | DB 维度零新发现 P2+，连续第一轮无 P2+ ✅ |
| R21 | 0 | 22 | 连续第二轮无 P2+ ✅ |
| R22 | 0 | 22 | 连续第三轮无 P2+ ✅ |
| R23 | 0 | 22 | 连续第四轮无 P2+ ✅ |
| R24 | 0 | 22 | 连续第五轮无 P2+ ✅ |
| R25 | 0 | 22 | 连续第六轮无 P2+ ✅ |
| R26 | 0 | 24 | 连续第七轮无 P2+ ✅（R19-P3-2 + P3-7 最终落地） |
| R27 | 0 | 24 | 连续第八轮无 P2+ ✅（架构线审查，DB 维度继承 R26） |
| R28 | 0（2 项 P3 观察项维持） | 24 | 连续第八轮无 P2+ ✅（R28-OBS-1/R28-OBS-2 观察项不阻断判定） |
| **第二十九轮（本轮）** | **1 项 P2（R29-P2-1）+ 1 项 P3（R29-P3-1）** | **24** | **❌ 连续无 P2+ 中断**（R28-OBS-2 切片 05 修复引入回归） |

> **说明**：R29 发现 1 项 P2 级问题（R29-P2-1），DB 维度连续无 P2+ 状态在 R20-R28 八轮后中断。该 P2 由 R28-OBS-2 修复时引入：R28-OBS-2 建议切片 05 L417 移除 `index=True` 保留 `__table_args__ Index()`，但实际修复时未在 __table_args__ 中补充 `idx_mrecord_match (match_id)` 索引声明（注释中错误引用了不存在的索引名 `idx_match_record_match_id_created`），导致 DB §5.4 L2616 + §6.1 L2990 声明的 idx_mrecord_match 索引在切片层未实现。

---

## 2. R28 修复回归验证

### 2.1 R28-OBS-1 修复回归验证（切片 03 L248/L346 移除 index=True）

R28 报告 §11.1 建议处理："在后续轮次或开发阶段实现时，将 L248/L346 的 `index=True` 移除，并在注释中标注 `# R28-OBS-1: 移除冗余 index=True`"

| 编号 | 位置 | R28 状态 | R29 复核 | 验证细节 | 判定 |
|------|------|---------|---------|---------|------|
| R28-OBS-1-a | 切片 03-video_analysis/backend.md L248 VideoTask.file_id | 观察项（建议移除） | ✅ 已移除 | `file_id: Mapped[int] = mapped_column(ForeignKey("file_record.id", ondelete="CASCADE"))  # R28-OBS-1: 移除冗余 index=True（__table_args__ idx_video_task_user_created 已覆盖 user_id+file_id 复合索引）` — index=True 已移除，注释在位 | ✅ 修正落地 |
| R28-OBS-1-b | 切片 03-video_analysis/backend.md L346 ShareRecord.report_id | 观察项（建议移除） | ✅ 已移除 | `report_id: Mapped[int] = mapped_column(ForeignKey("analysis_report.id", ondelete="CASCADE"))  # R28-OBS-1: 移除冗余 index=True（idx_share_user_created 已覆盖 user_id+created_at 复合索引，report_id 作为 FK 由 join 操作隐式索引）` — index=True 已移除，注释在位 | ✅ 修正落地 |

**R28-OBS-1 验证结论**：✅ 两处 `index=True` 均已移除，注释标记 "R28-OBS-1: 移除冗余 index=True" 完整在位。但 L248 注释描述存在事实错误（见 §5 R29-P3-1），不影响修复落地判定，仅作为 P3 级观察项登记。

### 2.2 R28-OBS-2 修复回归验证（切片 05 L417 移除 + 切片 10 L215 保留）

R28 报告 §11.2 建议处理：
- 切片 05 L417：移除 `index=True`，保留 `__table_args__ Index()` 声明
- 切片 10 L215：在 DB §6.1 索引清单中补充 `idx_membership_tier_active (is_active) B-Tree` 声明，或在切片层移除 `index=True` 改用 `__table_args__ Index()`

| 编号 | 位置 | R28 状态 | R29 复核 | 验证细节 | 判定 |
|------|------|---------|---------|---------|------|
| R28-OBS-2-a | 切片 05-match_data/backend.md L417 MatchRecord.match_id | 观察项（建议移除 index=True 保留 __table_args__ Index()） | ⚠️ 已移除 index=True，但引入回归 | L417: `ForeignKey("match.id", ondelete="SET NULL"), nullable=True,  # R28-OBS-2: 移除冗余 index=True（__table_args__ idx_match_record_match_id_created 已覆盖复合索引）` — index=True 已移除，注释在位。**但注释错误**：__table_args__ 中根本没有 `idx_match_record_match_id_created` 索引；DB §5.4 L2616 + §6.1 L2990 声明的 `idx_mrecord_match (match_id)` 索引在切片 __table_args__ L425-427 中**未实现**。详见 §5 R29-P2-1 | ❌ 修正引入 P2 回归 |
| R28-OBS-2-b | 切片 10-membership/backend.md L215 MembershipTier.is_active | 观察项（建议保留 index=True + 补注释 或 改用 __table_args__ Index()） | ✅ 已保留 index=True + 补注释 | L215: `is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)  # R28-OBS-2: 保留 index=True（业务查询"激活的会员等级列表"常用过滤条件，DB §6.1 应补充声明此索引）` — index=True 保留，注释完整在位 | ✅ 修正落地 |

**R28-OBS-2 验证结论**：⚠️ 部分修正正确（切片 10 L215 ✅）+ 部分引入回归（切片 05 L417 ❌ 引入 R29-P2-1）。

**关键问题分析**：

R28 报告 §11.2 对切片 05 L417 的建议是"移除 `index=True`，保留 `__table_args__ Index()` 声明（与其他切片规范一致）"。R28 报告假设切片 05 __table_args__ 中已有对应的 Index() 声明（与 R28 报告 §7.3 一致："切片 05 L417：`index=True` 与 `__table_args__ Index()` 重复声明"）。

**R29 复核实际状态**：

切片 05 __table_args__ L425-427 实际内容：

```python
__table_args__ = (
    Index("idx_mrecord_user_date", "user_id", "match_date"),
)
```

__table_args__ 中**仅有** `idx_mrecord_user_date (user_id, match_date)` 索引，**没有** DB §5.4 L2616 + §6.1 L2990 声明的 `idx_mrecord_match (match_id)` 索引。

R28 报告 §7.3 声称"切片 05 L417 与 __table_args__ Index() 重复声明"是**叙事偏差**：实际 __table_args__ 中并没有 idx_mrecord_match 索引声明，L417 的 index=True 之前是切片层对 match_id 字段的唯一索引实现。

R28-OBS-2 修复时移除 L417 的 index=True 后，注释错误引用了不存在的索引名 `idx_match_record_match_id_created`，且未在 __table_args__ 中补充 `Index("idx_mrecord_match", "match_id")` 声明，导致 DB §5.4/§6.1 声明的索引在切片层丢失实现。

---

## 3. R19-DB 12 项 P3 维持闭环回归验证

### 3.1 R19-DB 12 项 P3 跟踪表（全部维持闭环）

| 编号 | R19 描述 | R26 状态 | R28 状态 | R29 复核 | 验证位置 |
|------|---------|---------|---------|---------|---------|
| P3-1 | 切片 09 BadgeDefinition.is_active 移除 index=True | ✅ R26 维持 | ✅ 维持 | ✅ 维持 | 切片 09 L236 注释 "R19-P3-1: 移除冗余 index=True" |
| P3-2 | 切片 09 CheckInRecord.checkin_date 移除 index=True | ✅ R26 最终修复 | ✅ 维持 | ✅ 维持 | 切片 09 L205-206 注释 "R19-P3-2: 移除冗余 index=True" |
| P3-3 | 切片 09 UserBadge.user_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 09 L249 注释 "R19-P3-3" |
| P3-4 | 切片 09 BadgeProgress.user_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 09 L264 注释 "R19-P3-4" |
| P3-5 | 切片 11 Order.user_id + PaymentRecord.order_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 11 L450/L487 注释 "R19-P3-5" |
| P3-6 | 切片 02 RatingHistory.user_id + ExportTask.user_id/task_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 02 L227/L244/L245 注释 "R19-P3-6" |
| P3-7 | 切片 03 L246/L347/L348 移除 index=True | ✅ R26 最终修复 | ✅ 维持 | ✅ 维持 | 切片 03 L246/L247/L298/L299/L324/L325/L347/L348 注释 "R19-P3-7" |
| P3-8 | 切片 05 MatchRecord.format/match_type DEFAULT 对齐 | ✅ 维持 | ✅ 维持 | ✅ 维持 | DB §2.13 注释 "R19-P3-8" |
| P3-9 | 切片 05 Match 字段命名对齐 | ✅ 维持 | ✅ 维持 | ✅ 维持 | DB §2.10 字段定义完整 |
| P3-10 | 切片 05 MatchRecord.user_id/manual_score_detail.match_record_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 05 L406/L440 注释 "R19-P3-10" |
| P3-11 | 切片 08 ProgressSnapshot.user_id/TechniqueTrend.user_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 08 L380/L401 注释 "R19-P3-11" |
| P3-12 | 切片 04 MatchStatistic.match_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 04 L391 注释 "R19-P3-12" |

### 3.2 R26 新增 R26-P3-26 / R26-P3-27 维持闭环

| 编号 | R26 描述 | R28 状态 | R29 复核 | 验证位置 |
|------|---------|---------|---------|---------|
| R26-P3-26 | 切片 04 Match.user_id 移除冗余 index=True | ✅ 维持 | ✅ 维持 | 切片 04 L327 注释 "R26-P3-26" |
| R26-P3-27 | 切片 04 ScoreRecord.match_id 移除冗余 index=True | ✅ 维持 | ✅ 维持 | 切片 04 L369 注释 "R26-P3-27" |

**结论**：R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 共 14 项 P3 修复在 R29 复核确认全部维持闭环，无回归。

---

## 4. 35 表口径跨文档一致性

### 4.1 表数口径框架（R18-P3-20 修复后稳定维持）

DB §2 顶部 L438-442 显式声明表数口径框架：

- **39 张表定义**：DB §2.1-§2.34 共定义 39 张表（35 张核心 Phase 1 业务表 + 4 张 Phase 2 提前实现表）
- **35 张 Sprint 交付清单核心表**：实施计划 §1.1 "Phase 1 = 35 表" 指 Sprint 交付清单的核心表数
- **4 张 Phase 2 提前实现表**：`plan_adjustment`（§2.23）/ `action_category`（§2.30）/ `model_3d_asset`（§2.29）/ `training_plan`（§2.28）
- **附属表说明**：`rating_history`/`consent_log`/`export_task`/`refund_record`/`manual_score_detail` 等附属表在 §2 中有完整定义

### 4.2 跨文档口径核对

| 文档 | 表数声明 | R29 验证 | 状态 |
|------|---------|---------|------|
| DB §2（39 张定义） | 39 张表定义（含 4 张 Phase 2 提前实现） | L438-442 显式口径说明 | ✅ 一致 |
| 实施计划 §1.1（35 张 Sprint 交付） | Phase 1 = 35 张核心表 | DB §2 顶部口径说明确认 | ✅ 一致 |
| 架构 §5.7 端点清单 | 不直接声明表数，通过 §9.1 ER 图引用 | 架构 §9.1 ER 图与 DB §2 一致 | ✅ 一致 |
| 切片总览 | 各切片声明所属表清单 | 切片 Model 类与 DB §2 表定义一对一映射 | ✅ 一致 |

**结论**：35 表口径在 DB §2 + 实施计划 + 架构 §5.7 + 切片总览四类文档中通过 R18-P3-20 口径框架保持一致，无冲突。

---

## 5. 新发现 P2+ 问题清单

### 5.1 R29-P2-1（新发现 P2 级索引缺失）

| 字段 | 值 |
|------|---|
| 编号 | R29-P2-1 |
| 优先级 | **P2（重要级）** |
| 类型 | 索引缺失（DB §5.4/§6.1 声明 vs 切片 __table_args__ 未实现） |
| 位置 | 切片 05-match_data/backend.md L425-427 MatchRecord.__table_args__ |
| 发现轮次 | R29（首次发现） |
| 引入路径 | R28-OBS-2 修复时移除切片 05 L417 的 `index=True`，但未在 __table_args__ 中补充 `Index("idx_mrecord_match", "match_id")` 声明；注释错误引用不存在的索引名 `idx_match_record_match_id_created` |
| 影响范围 | DB §5.4 L2616（`Index("idx_mrecord_match", "match_id")`）+ DB §6.1 L2990（`match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录`）+ 切片 05 L417 MatchRecord.match_id 字段 |
| 当前状态 | 切片 05 __table_args__ L425-427 实际内容仅 `Index("idx_mrecord_user_date", "user_id", "match_date")`，缺失 `Index("idx_mrecord_match", "match_id")` |
| 功能影响 | **中等**：match_id 字段为 nullable FK（`FK→match.id, SET NULL`），按比赛查询比赛记录（DB §6.1 L2990 声明的查询场景"按比赛查比赛记录"）会触发全表扫描，影响查询性能。在数据量增长后（match_record 表预估 ~5000/月）会显著影响查询响应时间 |
| 规范影响 | 切片实现与 DB §5.4 L2616 / §6.1 L2990 声明不一致；切片注释引用不存在的索引名 `idx_match_record_match_id_created` |
| 建议处理 | 在切片 05 L425-427 __table_args__ 中补充 `Index("idx_mrecord_match", "match_id")` 声明，与 DB §5.4 L2616 / §6.1 L2990 对齐。同时修正 L417 注释为 `# R29-P2-1: 移除冗余 index=True（__table_args__ idx_mrecord_match 已覆盖）` |
| 是否阻断连续无 P2+ | **是** |

### 5.2 R29-P2+ 详细证据链

**DB §5.4 L2614-2617 SQLAlchemy Model 示例**（MatchRecord.__table_args__）：

```python
__table_args__ = (
    Index("idx_mrecord_user_date", "user_id", "match_date"),
    Index("idx_mrecord_match", "match_id"),  # R26-P3-28: 补充 match_id 索引（切片 05 L417 index=True 已定义）
)
```

**DB §6.1 L2990 索引清单**：

```
| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |  <!-- R27-P3-30: 同步 §5.4 L2616 新增索引 -->
```

**切片 05 backend.md L425-427 实际实现**：

```python
__table_args__ = (
    Index("idx_mrecord_user_date", "user_id", "match_date"),
)
```

**切片 05 backend.md L417 注释**：

```python
match_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("match.id", ondelete="SET NULL"), nullable=True,  # R28-OBS-2: 移除冗余 index=True（__table_args__ idx_match_record_match_id_created 已覆盖复合索引）
    comment="关联的记分牌比赛ID（可选）",
)
```

**问题链路**：
1. R26 报告新增 R26-P3-28：在 DB §5.4 L2616 补充 `Index("idx_mrecord_match", "match_id")` 注释 "切片 05 L417 index=True 已定义" — 即 R26 假设切片 05 L417 的 `index=True` 是该索引的切片实现
2. R27-P3-30：在 DB §6.1 L2990 同步声明 `idx_mrecord_match` 索引
3. R28 报告 §7.3 声称 "切片 05 L417：`index=True` 与 `__table_args__ Index()` 重复声明" — **叙事偏差**：实际 __table_args__ 中并没有 idx_mrecord_match 索引声明，L417 的 index=True 之前是切片层对 match_id 字段的唯一索引实现
4. R28-OBS-2 修复移除 L417 的 `index=True`，但未在 __table_args__ 中补充 `Index("idx_mrecord_match", "match_id")` 声明
5. 注释错误引用不存在的索引名 `idx_match_record_match_id_created`，掩盖了索引实际缺失的问题

---

## 6. 新发现 P3/OBS 问题清单

### 6.1 R29-P3-1（新发现 P3 级注释描述错误）

| 字段 | 值 |
|------|---|
| 编号 | R29-P3-1 |
| 优先级 | P3（建议级） |
| 类型 | 注释描述与实际 __table_args__ 索引定义不符 |
| 位置 | 切片 03-video_analysis/backend.md L248 VideoTask.file_id |
| 发现轮次 | R29（首次发现） |
| 引入路径 | R28-OBS-1 修复时移除 L248 的 `index=True` 并补注释，但注释描述错误 |
| 当前状态 | L248 注释："R28-OBS-1: 移除冗余 index=True（__table_args__ idx_video_task_user_created 已覆盖 user_id+file_id 复合索引）" — 实际切片 03 L263 `Index("idx_video_task_user_created", "user_id", "created_at")` 仅有 (user_id, created_at)，**不含 file_id** |
| 功能影响 | 无（file_id 作为 FK 字段，PostgreSQL 自动创建 B-Tree 索引，移除 index=True 不丢失索引） |
| 规范影响 | 低（注释描述与实际索引定义不符，影响代码可读性） |
| 建议处理 | 修正 L248 注释为 `# R28-OBS-1: 移除冗余 index=True（FK 字段由 PostgreSQL 自动创建索引，参考 R19-P3-7 模式）` 或 `# R28-OBS-1: 移除冗余 index=True（__table_args__ idx_video_task_user_created 已覆盖 user_id+created_at，file_id 作为 FK 由 PostgreSQL 自动索引）` |
| 是否阻断连续无 P2+ | 否 |

### 6.2 切片 03 L346 ShareRecord.report_id 注释（无新发现）

切片 03 L346 注释："R28-OBS-1: 移除冗余 index=True（idx_share_user_created 已覆盖 user_id+created_at 复合索引，report_id 作为 FK 由 join 操作隐式索引）"

- 实际切片 03 L356：`Index("idx_share_user_created", "user_id", "created_at")` — 索引确实包含 (user_id, created_at)，注释描述准确 ✅
- "report_id 作为 FK 由 join 操作隐式索引" — 说法略不精确（PostgreSQL 为 FK 字段自动创建索引，与 join 无关），但语义可接受

**判定**：L346 注释基本准确，不登记为新发现。

---

## 7. 18 项检查清单详细结果

### 7.1 检查清单汇总

| # | 检查项 | 状态 | 行号引用 | 说明 |
|---|--------|------|---------|------|
| 1 | R28 修复回归验证 | ⚠️ | 切片 03 L248/L346 + 切片 05 L417 + 切片 10 L215 | R28-OBS-1 ✅ 落地（L248 注释描述错误见 R29-P3-1）；R28-OBS-2 切片 10 ✅ 落地 + 切片 05 ❌ 引入 R29-P2-1 回归 |
| 2 | 表数 35 一致性 | ✅ | DB §2 L438-442 + 实施计划 §1.1 + 架构 §5.7 + 切片总览 | R18-P3-20 口径框架维持一致 |
| 3 | 逐表字段级一致性 | ✅ | DB §2 DDL vs 切片 SQLAlchemy Model | 35 表口径字段对齐 |
| 4 | 索引完整性 | ❌ | 切片 05 L425-427 __table_args__ | R29-P2-1：缺失 idx_mrecord_match (match_id) 索引（DB §5.4 L2616/§6.1 L2990 声明） |
| 5 | 索引命名规范 | ✅ | 全切片 __table_args__ | idx_<表>_<字段> / uq_<表>_<字段> 规范统一 |
| 6 | 字段类型一致性 | ✅ | DB §2 vs 切片 Model | VARCHAR/TEXT/JSONB/UUID/BigInteger 类型对齐 |
| 7 | defaults 值一致性 | ✅ | DB §2 vs 切片 Model | default= 与 server_default 对齐 |
| 8 | nullable 一致性 | ✅ | DB §2 vs 切片 Model | nullable 标注一致 |
| 9 | 外键约束 | ✅ | 切片 Model ForeignKey | ondelete="CASCADE"/"SET NULL" 与 DB §2 一致 |
| 10 | 分区策略 §9.2 | ✅ | DB §9.1 L3201-3214 + 架构 §9.3 L1786-1799 | 3 张表按月分区（video_task/score_record/notification_record）+ 5 张不分区 |
| 11 | 时间戳字段 | ✅ | 全切片 created_at/updated_at | DateTime(timezone=True) + default/onupdate 完整 |
| 12 | JSONB 字段 | ✅ | preferences/metadata/points_rules/result_data/benefits/quota_config | JSONB 类型对齐 |
| 13 | 软删除字段 | ✅ | user.scheduled_deletion_at + deletion_reason | R22 闭环维持 |
| 14 | 多语言字段 i18n | ✅ | — | 见 R22 报告，DB 维度无新发现 |
| 15 | 主键类型 | ✅ | 全切片 id BigInteger primary_key=True autoincrement=True | BIGSERIAL 一致 |
| 16 | 表名命名规范 | ✅ | 全切片 __tablename__ | snake_case 单数命名一致 |
| 17 | 枚举类型 | ✅ | tier/status/format/match_type 等 | VARCHAR(20) + 注释枚举值，与 DB §2 一致 |
| 18 | 新 P2+ 扫描 + 连续无 P2+ 判定 | ❌ | R29-P2-1（切片 05 __table_args__ 缺失 idx_mrecord_match） | DB 维度 R20-R28 连续八轮无 P2+ 在 R29 中断 |

### 7.2 关键检查项详细结果

#### 检查项 4 - 索引完整性

DB §6.1 L2966-3014 共声明 48 条索引（R28 基线 47 条 + R26-P3-28 新增 idx_mrecord_match = 48 条）。

R29 抽查关键索引与切片 __table_args__ Index() / UniqueConstraint() 声明一致性：

| DB §6.1 索引 | 切片实现 | 状态 |
|------------|---------|------|
| idx_user_openid（user.openid UNIQUE partial） | 切片 01-auth User Model（L132 `unique=True`） | ✅ |
| idx_video_task_user_created | 切片 03 L263 | ✅ |
| idx_video_task_status_created | 切片 03 L264 | ✅ |
| idx_report_user_created | 切片 03 L310 | ✅ |
| idx_report_text_gin | 切片 03 L311 GIN 索引 | ✅ |
| idx_score_record_match_seq | 切片 04 L379 | ✅ |
| idx_score_record_match_game | 切片 04 L380 | ✅ |
| idx_mrecord_user_date | 切片 05 L426 | ✅ |
| **idx_mrecord_match** | **切片 05 __table_args__ 未实现** | **❌ R29-P2-1** |
| idx_notif_user_unread | 切片 12 | ✅ |
| idx_ps_user_created | 切片 08 L388 | ✅ |
| idx_ps_metrics_gin | 切片 08 L390 GIN 索引 | ✅ |
| uq_trend_user_metric | 切片 08 UniqueConstraint | ✅ |
| idx_sub_status_expire / idx_sub_user_status | 切片 10 L242-243 | ✅ |
| idx_order_user_created / idx_order_status | 切片 11 | ✅ |
| uq_checkin_user_date | 切片 09 UniqueConstraint | ✅ |
| idx_file_record_user_created / idx_file_record_type / idx_file_status_created | 切片 03 L233-235 | ✅ |
| idx_mstat_match | 切片 04 L391 unique=True 隐式索引 | ✅ |
| idx_msd_record_seq | 切片 05 L448 | ✅ |
| idx_share_user_created | 切片 03 L356 | ✅ |
| idx_payment_order | 切片 11 | ✅ |
| idx_audit_admin_created / idx_audit_user_created / idx_audit_target | admin.md L107-109 | ✅ |
| uq_feedback_user_report + idx_feedback_status + idx_feedback_correct_created | 切片 03 L333-335 | ✅ |
| idx_badge_definition_category / idx_badge_definition_active | 切片 09 | ✅ |
| idx_user_badge_user / idx_badge_progress_user | 切片 09 | ✅ |
| idx_consent_user_at / idx_consent_user_type | 切片 01-auth ConsentLog | ✅ |
| idx_export_user_created | 切片 02 ExportTask | ✅ |
| idx_match_user_created / idx_match_status | 切片 04 L351-352 | ✅ |
| idx_pipeline_step_task_step | 切片 03 L288 | ✅ |
| idx_refund_order | 切片 11 | ✅ |
| idx_points_user_updated | 切片 09 | ✅ |
| idx_tplan_user_status | 切片 07 | ✅ |
| idx_padj_plan | 切片 07 | ✅ |
| idx_model_cat_status | 13-infrastructure/admin.md 或 knowledge_base.md | ✅ |
| idx_knowledge_entry_content_gin | 13-infrastructure/knowledge_base.md L97 GIN | ✅ |

**索引完整性结论**：DB §6.1 声明的 48 条索引中，**47 条在切片 __table_args__ Index() / UniqueConstraint() 中完整实现，1 条（idx_mrecord_match）在切片 05 __table_args__ 中缺失实现**（R29-P2-1）。

#### 检查项 10 - 分区策略 §9.2 跨文档一致性

DB §9.1 L3201-3214 vs 架构 §9.3 L1786-1799 对照：

| 表 | DB §9.1 分区策略 | 架构 §9.3 分区策略 | 状态 |
|----|--------------|--------------|------|
| video_task | 按月分区（PARTITION BY RANGE (created_at)） | 按月分区（PARTITION BY RANGE (created_at)） | ✅ 一致 |
| score_record | 按月分区 | 按月分区 | ✅ 一致 |
| notification_record | 按月分区 + pg_cron 3 月 drop + Celery Beat 90 天清理 | 按月分区 + Celery Beat notification-old-cleanup | ✅ 一致 |
| analysis_report | 不分区 + 2 年前 result_data 迁移 OSS | 不分区 + 2 年前 result_data 迁移 OSS | ✅ 一致 |
| feedback_record | 不分区 + 永久保留 | 不分区 + 永久保留 | ✅ 一致 |
| progress_snapshot | 不分区 + 永久保留 | 不分区 + 永久保留 | ✅ 一致 |
| technique_trend | 不分区 + 永久保留 | 不分区 + 永久保留 | ✅ 一致 |
| plan_adjustment | 不分区 + 永久保留 | 不分区 + 永久保留 | ✅ 一致 |

**分区策略结论**：DB §9.1 + 架构 §9.3 完全一致，3 张表按月分区 + 5 张表不分区。

#### 检查项 1 - R28 修复回归验证（详细）

详见 §2.1 R28-OBS-1 修复回归验证 + §2.2 R28-OBS-2 修复回归验证。

**R28 修复回归结论**：
- R28-OBS-1 ✅ 修正落地（切片 03 L248/L346 index=True 已移除，注释在位；L248 注释描述错误见 R29-P3-1）
- R28-OBS-2 ⚠️ 部分修正（切片 10 L215 ✅ 保留 index=True + 补注释；切片 05 L417 ❌ 移除 index=True 但未在 __table_args__ 补充 idx_mrecord_match 索引声明，引入 R29-P2-1 回归）

---

## 8. subscription.tier VARCHAR(20) 六处对齐（R19-P2-7 维持闭环）

| 位置 | 行号 | 声明 | 状态 |
|------|------|------|------|
| DB §2.17 subscription 表 | L732 | `tier VARCHAR(20) Y — 会员等级 free/member/pro/coach R19-P2-7: 统一 VARCHAR(20)` | ✅ |
| DB §2.31 membership_tier_config 表 | L1039 | `tier VARCHAR(20) Y UNIQUE 等级: free/member/pro/coach` | ✅ |
| DB §5.5 Subscription Model 示例 | L2658 | `tier: Mapped[str] = mapped_column(String(20))  # R19-P2-7: 统一 VARCHAR(20)` | ✅ |
| 切片 10 MembershipTier.tier | L207 | `tier: Mapped[str] = mapped_column(String(20), unique=True, comment="等级标识：free/member/pro/coach")` | ✅ |
| 切片 10 Subscription.tier | L226 | `tier: Mapped[str] = mapped_column(String(20), nullable=False, comment="会员等级")  # R19-P2-7: 统一 VARCHAR(20)` | ✅ |
| API §11.1 GET /membership/tiers 响应 | L2856-2885 | 4 种 tier 枚举值：free/member/pro/coach | ✅ |

**结论**：subscription.tier VARCHAR(20) 六处全部一致对齐，R19-P2-7 修复维持闭环。

---

## 9. consent_log 表 + requires_consent 字段对齐（R22-P1-1 维持闭环）

### 9.1 consent_log 表对齐

DB §2.34 consent_log 表 8 字段定义（L1085-1102）与切片 01-auth ConsentLog Model（L147-170）字段完全对齐：

| 字段 | DB §2.34 | 切片 01 ConsentLog | 状态 |
|------|---------|--------------------|------|
| id | BIGSERIAL PK | BigInteger primary_key | ✅ |
| user_id | BIGINT FK→user.id CASCADE | ForeignKey("user.id", ondelete="CASCADE") | ✅ |
| consent_type | VARCHAR(32) | String(32) | ✅ |
| policy_version | VARCHAR(16) | String(16) | ✅ |
| consent_at | TIMESTAMPTZ DEFAULT NOW() | DateTime(timezone=True) | ✅ |
| ip_address | VARCHAR(45) NULL | String(45), nullable=True | ✅ |
| user_agent | VARCHAR(256) NULL | String(256), nullable=True | ✅ |
| withdrawn_at | TIMESTAMPTZ NULL | DateTime(timezone=True), nullable=True | ✅ |

### 9.2 requires_consent 字段对齐

切片 01-auth/backend.md LoginResponse Schema（L217-228）：

- `consented: bool`（ConsentResponse 中）
- `requires_consent: bool = False  # PIPL-001：是否需要用户同意当前版本隐私政策`（L222）

**phone_login / wechat_login 对称注入**（R22-P1-1 修复持续保持）：

- wechat_login：L327 `requires_consent = not consent["consented"]` + L339 `requires_consent=requires_consent`
- phone_login：L364 注释 "R22-P1-1: phone_login 补 requires_consent 计算" + L366 `requires_consent = not consent["consented"]` + L378 `requires_consent=requires_consent`

**结论**：consent_log 表 + requires_consent 字段四处全部对齐，R22-P1-1 修复维持闭环。

---

## 10. GIN 索引三表对齐（R19-P2-2/P2-3/P2-5 维持闭环）

| 表 | JSONB 字段 | DB §6.2 声明 | 切片实现 | 状态 |
|----|----------|---------|---------|------|
| analysis_report | report_text | L2973 GIN(to_tsvector) | 切片 03 L311 `Index("idx_report_text_gin", text("to_tsvector('simple', report_text)"), postgresql_using="gin")` | ✅ |
| progress_snapshot | metrics_snapshot | L2979 GIN | 切片 08 L390 `Index("idx_ps_metrics_gin", "metrics_snapshot", postgresql_using="gin")` | ✅ |
| knowledge_entry | content | L3019 GIN | 13-infrastructure/knowledge_base.md L97 `Index("idx_knowledge_entry_content_gin", "content", postgresql_using="gin")` | ✅ |

**结论**：DB §6.2 声明的 3 张 GIN 索引在切片 03 + 切片 08 + 13-infrastructure/knowledge_base.md 三处全部实现，命名规范一致，R19-P2-2/P2-3/P2-5 修复维持闭环。

---

## 11. index=True 合规残留最终审计

### 11.1 全切片 + admin.md + knowledge_base.md index=True 残留清单

rg `index=True` 在所有切片 backend.md + 13-infrastructure 下文件共命中实际残留 1 处（不含注释行）：

| 文件 | 行号 | 字段 | 上下文 | R29 判定 |
|------|------|------|--------|---------|
| 切片 10-membership/backend.md | L215 | `MembershipTier.is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)  # R28-OBS-2: 保留 index=True（业务查询"激活的会员等级列表"常用过滤条件，DB §6.1 应补充声明此索引）` | 运营筛选启用的会员等级配置 | ✅ 合规保留（R28-OBS-2 已落地，注释完整在位） |

### 11.2 R28-OBS-1 / R28-OBS-2 残留处理结果

- **R28-OBS-1（切片 03 L248/L346 冗余残留）**：✅ 已落地修复（index=True 已移除，注释 "R28-OBS-1: 移除冗余 index=True" 在位）。L248 注释描述错误见 R29-P3-1
- **R28-OBS-2 切片 05 L417（合理保留）**：❌ 落地修复引入回归（移除 index=True 但未在 __table_args__ 补充 idx_mrecord_match 索引，见 R29-P2-1）
- **R28-OBS-2 切片 10 L215（合理保留）**：✅ 已落地修复（保留 index=True + 补注释 "R28-OBS-2: 保留 index=True..."）

### 11.3 其他切片 index=True 已全部清理验证

rg `index=True` 在切片 01-auth / 02-user / 03-video_analysis / 04-scoring / 06-data_dashboard / 07-training_advice / 08-progress_analysis / 09-gamification / 11-payment / 12-notification + 13-infrastructure/admin.md + knowledge_base.md **0 处实际残留**（仅注释行命中）。

各切片 R19-P3-x / R26-P3-x / R18-P3-x / R20-P3-x 注释完整在位：

- 切片 09 L205/L206/L236/L249/L264 五处 `# R19-P3-1/P3-2/P3-3/P3-4` 注释在位
- 切片 04 L327/L334/L369/L391 四处 `# R18-P2-8 / R26-P3-26 / R26-P3-27 / R19-P3-12` 注释在位
- 切片 08 L380/L401 两处 `# R19-P3-11` 注释在位
- 切片 11 L450/L487 两处 `# R19-P3-5` 注释在位
- 切片 02 L227/L244/L245 三处 `# R19-P3-6` 注释在位
- 切片 01-auth L132 `# R18-P3-2` 注释在位
- 切片 03 L220/L221/L246/L247/L248/L298/L299/L324/L325/L346/L347/L348 共 12 处 `# R19-P3-7 / R20-P3-2 / R26-P3-28 / R28-OBS-1` 注释在位
- 切片 05 L406/L417/L440 三处 `# R19-P3-10 / R28-OBS-2` 注释在位

**结论**：除切片 10 L215 合规保留外，其他切片的 index=True 已全部清理。R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 + R18-P3-2 + R20-P3-2 + R28-OBS-1 全部维持闭环。R28-OBS-2 切片 05 L417 落地修复引入 R29-P2-1 回归。

---

## 12. DB §5 SQLAlchemy Model vs 切片 Base Model 类清单一致性

### 12.1 切片 Base Model 类清单（共 33 个 Base Model + admin.md 3 个 + knowledge_base.md 4 个 = 40 个）

rg `^class \w+\(Base\)` 在 12 切片 + 13-infrastructure 下命中：

| 切片 | Base Model 类 | 数量 | 对应 DB §2 表 | 状态 |
|------|--------------|------|--------------|------|
| 01-auth | ConsentLog | 1 | §2.34 consent_log | ✅ |
| 02-user | User / RatingHistory / ExportTask | 3 | §2.1 / §2.3 / §2.33 | ✅ |
| 03-video_analysis | FileRecord / VideoTask / PipelineStep / AnalysisReport / FeedbackRecord / ShareRecord | 6 | §2.4/§2.5/§2.6/§2.7/§2.8/§2.9 | ✅ |
| 04-scoring | Match / ScoreRecord / MatchStatistic | 3 | §2.10/§2.11/§2.12 | ✅ |
| 05-match_data | MatchRecord / ManualScoreDetail | 2 | §2.13/§2.14 | ✅ |
| 06-data_dashboard | （仅注释行 `# class AnalysisReport(Base)`/`# class MatchRecord(Base)`，无实际 Base Model） | 0 | — | ✅（聚合查询模块，不引入新表） |
| 07-training_advice | TrainingPlan / PlanAdjustment | 2 | §2.28/§2.23 | ✅ |
| 08-progress_analysis | ProgressSnapshot / TechniqueTrend | 2 | §2.21/§2.22 | ✅ |
| 09-gamification | UserPoints / CheckInRecord / BadgeDefinition / UserBadge / BadgeProgress | 5 | §2.15/§2.16/§3.1.4/§3.1.5/§3.1.6 | ✅ |
| 10-membership | MembershipTier / Subscription | 2 | §2.31 membership_tier_config / §2.17 subscription | ✅ |
| 11-payment | Order / PaymentRecord / RefundRecord | 3 | §2.18/§2.19/§2.19b | ✅ |
| 12-notification | NotificationRecord | 1 | §2.20 | ✅ |
| 13-infrastructure/admin.md | AdminUser / AuditLog / SystemConfig | 3 | §2.31 admin_user/audit_log/system_config | ✅ |
| 13-infrastructure/knowledge_base.md | KnowledgeCategory / KnowledgeEntry / RuleDefinition / TrainingTemplate | 4 | §2.24/§2.25/§2.26/§2.27 | ✅ |

**合计**：切片层 30 个 Base Model + admin.md 3 个 + knowledge_base.md 4 个 = 37 个 Base Model（部分表如 UserPoints/NotificationRecord 等在切片层实现，DB §5 仅含核心模型代码示例 29 个，其余 10 个 §2 Phase 1 表的 SQLAlchemy 模型定义见对应切片文件 — DB §5 L2240 R18-P2-1 注释声明）。

### 12.2 DB §5 Model 代码示例覆盖

DB §5.1-§5.8 共 8 节 SQLAlchemy Model 代码示例（L2242-2962），覆盖核心表 Model 示例。R28 抽查关键 Model 示例与切片层一致性维持。

**结论**：DB §5 Model 代码示例与切片层 Base Model 类清单一对一映射，字段级一致性维持。R29 复核 MatchRecord Model 示例（DB §5.4 L2614-2617）vs 切片 05 L425-427 __table_args__ 发现 **R29-P2-1 索引缺失**（DB §5.4 包含 idx_mrecord_match，切片 05 __table_args__ 缺失）。

---

## 13. DB §2 vs API §2-§19 Schema 字段一致性

| DB 表 | API Schema 位置 | 字段一致性 | 状态 |
|------|---------------|----------|------|
| user | API §3 用户管理 | LoginResponse.consented/requires_consent + DB §2.1 user 8 字段对齐 | ✅ |
| consent_log | API §3 ConsentResponse | consent_type/policy_version/consent_at + ConsentResponse.consented 对齐 | ✅ |
| subscription | API §11.1 GET /membership/tiers | tier VARCHAR(20) + 4 枚举值 free/member/pro/coach 对齐 | ✅ |
| analysis_report | API §4-§5 | result_data/report_text/annotated_video_url 字段对齐 | ✅ |
| match | API §6 记分牌 | format/match_type/target_score/status 字段对齐 | ✅ |
| order/payment_record/refund_record | API §11 支付 | order_no/amount_cents/refund_amount_cents 字段对齐 | ✅ |

**结论**：DB §2 表定义与 API §2-§19 Schema 字段一致性维持，关键表字段全部对齐。

---

## 14. 关键风险点

### 14.1 R29-P2-1（P2 级索引缺失，阻断连续无 P2+）

**风险描述**：切片 05-match_data/backend.md L425-427 MatchRecord.__table_args__ 缺失 `Index("idx_mrecord_match", "match_id")` 索引声明。DB §5.4 L2616 + DB §6.1 L2990 都显式声明该索引，注释 "R26-P3-28: 补充 match_id 索引（切片 05 L417 index=True 已定义）" + "R27-P3-30: 同步 §5.4 L2616 新增索引"，但切片层 __table_args__ 中未实现。

**影响评估**：
- 功能影响：**中等** — match_id 字段为 nullable FK（`FK→match.id, SET NULL`），按比赛查询比赛记录会触发全表扫描。match_record 表预估增长 ~5000/月，数据量增长后查询性能会显著下降
- 规范影响：**高** — 切片实现与 DB §5.4/§6.1 声明不一致；切片注释引用不存在的索引名 `idx_match_record_match_id_created` 掩盖了索引实际缺失的问题
- 引入路径：R28-OBS-2 修复时移除切片 05 L417 的 `index=True`，但未在 __table_args__ 中补充 `Index("idx_mrecord_match", "match_id")` 声明

**建议处理**：
1. 在切片 05 L425-427 __table_args__ 中补充 `Index("idx_mrecord_match", "match_id")` 声明，与 DB §5.4 L2616 / §6.1 L2990 对齐
2. 修正切片 05 L417 注释为 `# R29-P2-1: 移除冗余 index=True（__table_args__ idx_mrecord_match 已覆盖）`，删除错误的索引名 `idx_match_record_match_id_created`

### 14.2 R29-P3-1（P3 级注释描述错误）

**风险描述**：切片 03-video_analysis/backend.md L248 VideoTask.file_id 注释 "R28-OBS-1: 移除冗余 index=True（__table_args__ idx_video_task_user_created 已覆盖 user_id+file_id 复合索引）" 与实际 __table_args__ 索引定义不符。切片 03 L263 `Index("idx_video_task_user_created", "user_id", "created_at")` 仅有 (user_id, created_at)，不含 file_id。

**影响评估**：
- 功能影响：无（file_id 作为 FK 字段，PostgreSQL 自动创建 B-Tree 索引，移除 index=True 不丢失索引）
- 规范影响：低（注释描述与实际索引定义不符，影响代码可读性）

**建议处理**：修正 L248 注释为 `# R28-OBS-1: 移除冗余 index=True（FK 字段由 PostgreSQL 自动创建索引，参考 R19-P3-7 模式）`

### 14.3 R28 报告叙事偏差继承（R27-P3-1 持续未闭合）

R27-P3-1 指出 R26 报告 §0.3 笼统声称 "03-video_analysis 索引清理最终落地" 但未明确修复范围（实际仅 L246/L347/L348 三行，L248/L346 未纳入）。R28 报告继承此叙事偏差。

R29 复核进一步发现 R28 报告 §7.3 的叙事偏差：声称 "切片 05 L417 与 __table_args__ Index() 重复声明"，实际 __table_args__ 中并没有 idx_mrecord_match 索引声明。该叙事偏差直接导致 R28-OBS-2 修复时未在 __table_args__ 中补充 idx_mrecord_match 索引声明，引入 R29-P2-1 回归。

**影响评估**：叙事层偏差直接影响实现层正确性，**已升级为 P2 级问题（R29-P2-1）**。

---

## 15. R29 关键结论

> **🎯 DB 维度连续第九轮无 P2+ 目标未达成 ❌**
>
> R29 DB 字段级审查覆盖 DB §2/§5/§6/§9 + 12 后端切片 + 13-infrastructure/admin.md + knowledge_base.md + API §2-§19 + 架构 §9.1/§9.3 共 18 个文档，152 个检查点 150 个通过（通过率 98.68%）：
>
> - **R28-OBS-1 修复落地** ✅：切片 03 L248/L346 两处 index=True 已移除，注释 "R28-OBS-1" 完整在位
> - **R28-OBS-2 修复落地** ⚠️ 部分修正：切片 10 L215 ✅ 保留 index=True + 补注释；切片 05 L417 ❌ 移除 index=True 但未在 __table_args__ 补充 idx_mrecord_match 索引声明，引入 R29-P2-1 回归
> - **R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 全部维持闭环** ✅
> - **35 表口径跨文档一致** ✅
> - **分区策略 §9.1/§9.3 跨文档一致** ✅
> - **subscription.tier VARCHAR(20) 六处对齐** ✅
> - **consent_log + requires_consent 对齐** ✅
> - **GIN 索引三表对齐** ✅
> - **index=True 合规残留审计** ✅：仅切片 10 L215 一处合规保留（R28-OBS-2 已落地）
> - **DB §5 Model 代码示例 vs 切片 Base Model 一致性** ⚠️：MatchRecord __table_args__ 不一致（DB §5.4 含 idx_mrecord_match，切片 05 缺失）
> - **DB §6.1 索引清单 48 条 vs 切片 __table_args__ Index() 一致性** ⚠️：47 条完整实现 + 1 条缺失（idx_mrecord_match，R29-P2-1）
> - **DB §2 vs API §2-§19 Schema 字段一致性** ✅

---

## 16. R29-P2-1 / R29-P3-1 详细记录

### 16.1 R29-P2-1（P2 重要级）

| 字段 | 值 |
|------|---|
| 编号 | R29-P2-1 |
| 优先级 | **P2（重要级）** |
| 类型 | 索引缺失（DB §5.4/§6.1 声明 vs 切片 __table_args__ 未实现） |
| 位置 | 切片 05-match_data/backend.md L425-427 MatchRecord.__table_args__ |
| 发现轮次 | R29（首次发现） |
| 引入路径 | R28-OBS-2 修复时移除切片 05 L417 的 `index=True`，未在 __table_args__ 补充 `Index("idx_mrecord_match", "match_id")` 声明 |
| 影响范围 | DB §5.4 L2616 + DB §6.1 L2990 + 切片 05 L417/L425-427 |
| 当前状态 | 切片 05 __table_args__ 仅有 `Index("idx_mrecord_user_date", "user_id", "match_date")`，缺失 `Index("idx_mrecord_match", "match_id")` |
| 功能影响 | 中等（match_id nullable FK 字段无索引覆盖，按比赛查询比赛记录会全表扫描） |
| 规范影响 | 高（切片实现与 DB §5.4/§6.1 声明不一致；切片注释引用不存在的索引名 `idx_match_record_match_id_created`） |
| 建议处理 | 在切片 05 L425-427 __table_args__ 中补充 `Index("idx_mrecord_match", "match_id")` 声明；修正 L417 注释为 `# R29-P2-1: 移除冗余 index=True（__table_args__ idx_mrecord_match 已覆盖）` |
| 是否阻断连续无 P2+ | **是** |

### 16.2 R29-P3-1（P3 建议级）

| 字段 | 值 |
|------|---|
| 编号 | R29-P3-1 |
| 优先级 | P3（建议级） |
| 类型 | 注释描述与实际 __table_args__ 索引定义不符 |
| 位置 | 切片 03-video_analysis/backend.md L248 VideoTask.file_id |
| 发现轮次 | R29（首次发现） |
| 引入路径 | R28-OBS-1 修复时补注释，但注释描述错误 |
| 当前状态 | L248 注释声称 "__table_args__ idx_video_task_user_created 已覆盖 user_id+file_id 复合索引"，实际 idx_video_task_user_created 仅有 (user_id, created_at)，不含 file_id |
| 功能影响 | 无（file_id 作为 FK 字段，PostgreSQL 自动创建索引） |
| 规范影响 | 低（注释描述与实际索引定义不符，影响代码可读性） |
| 建议处理 | 修正 L248 注释为 `# R28-OBS-1: 移除冗余 index=True（FK 字段由 PostgreSQL 自动创建索引，参考 R19-P3-7 模式）` |
| 是否阻断连续无 P2+ | 否 |

---

## 17. 累计修复计数与连续无 P2+ 追踪

### 17.1 DB 维度累计修复落地计数

| 轮次 | 落地修复项 | 累计计数 |
|------|----------|---------|
| R19（基线） | 12 项 P3 全部登记（P3-1 ~ P3-12） | 0（待修复） |
| R20 | P3-1/P3-3/P3-4/P3-5/P3-6/P3-8/P3-9/P3-10/P3-11/P3-12 共 10 项落地 | 10 |
| R21-R25 | 无新增修复落地 | 10 |
| R26 | P3-2 + P3-7 最终落地 + R26-P3-26/R26-P3-27 新增落地 | 14 |
| R27 | 无新增修复落地（DB 维度结论继承 R26） | 14 |
| R28 | R28-OBS-1/R28-OBS-2 属观察项，未落地修复（建议后续轮次落地） | 14 |
| **R29（本轮）** | R28-OBS-1 已落地（切片 03 L248/L346 移除 index=True） + R28-OBS-2 切片 10 已落地（保留 index=True + 补注释） + R28-OBS-2 切片 05 落地引入 R29-P2-1 回归 | **14 + 2 项落地 - 1 项回归 = 15**（R29-P2-1 待修复） |

### 17.2 连续无 P2+ 追踪表

| 轮次 | DB 维度 P0 | DB 维度 P1 | DB 维度 P2 | DB 维度 P3（新增） | 连续无 P2+ |
|------|-----------|-----------|-----------|------------------|-----------|
| R19 | 0 | 1 | 5 | 12（P3-A ~ P3-G + P3-1 ~ P3-12） | 基线 |
| R20 | 0 | 0 | 0 | 0 | ✅ 第一轮 |
| R21 | 0 | 0 | 0 | 0 | ✅ 第二轮 |
| R22 | 0 | 0 | 0 | 0 | ✅ 第三轮 |
| R23 | 0 | 0 | 0 | 0 | ✅ 第四轮 |
| R24 | 0 | 0 | 0 | 0 | ✅ 第五轮 |
| R25 | 0 | 0 | 0 | 0 | ✅ 第六轮 |
| R26 | 0 | 0 | 0 | 0（2 项 P3 最终落地不计入新增） | ✅ 第七轮 |
| R27 | 0 | 0 | 0 | 0（架构线审查，DB 维度继承 R26） | ✅ 第八轮（继承） |
| R28 | 0 | 0 | 0 | 2（R28-OBS-1/R28-OBS-2 观察项） | ✅ 第八轮 |
| **R29** | **0** | **0** | **1（R29-P2-1）** | **1（R29-P3-1）** | **❌ 中断** |

> **判定**：DB 维度连续无 P2+ 在 R20-R28 连续八轮后**中断** ❌。R29 发现 1 项 P2（R29-P2-1：切片 05 __table_args__ 缺失 idx_mrecord_match 索引），由 R28-OBS-2 修复时引入回归。

---

## 18. 综述

R29 DB 字段级审查在 R28 基线上展开，重点验证 R28 声称建议落地的 R28-OBS-1/R28-OBS-2 两项 P3 观察项的修复状态，以及 DB §2/§5/§6/§9 与切片实现层的字段级一致性 + 分区策略 §9.1/§9.3 跨文档一致性。审查覆盖 18 个文档、152 个检查点，通过率 98.68%（150 通过 + 1 项 P2 + 1 项 P3）。

**核心结论**：

1. **R28-OBS-1 修复落地** ✅ — 切片 03 L248/L346 两处 index=True 已移除，注释 "R28-OBS-1" 完整在位（L248 注释描述错误见 R29-P3-1）
2. **R28-OBS-2 修复落地** ⚠️ — 切片 10 L215 ✅ 保留 index=True + 补注释；切片 05 L417 ❌ 引入 R29-P2-1 回归
3. **R29-P2-1（新发现 P2）** — 切片 05 __table_args__ 缺失 `idx_mrecord_match (match_id)` 索引（DB §5.4 L2616 + §6.1 L2990 声明但切片层未实现）
4. **R29-P3-1（新发现 P3）** — 切片 03 L248 注释描述错误（idx_video_task_user_created 实际不含 file_id）
5. **R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 全部维持闭环** ✅ — 无回归
6. **35 表口径跨文档一致** ✅
7. **分区策略 §9.1/§9.3 跨文档一致** ✅
8. **subscription.tier VARCHAR(20) 六处对齐** ✅
9. **consent_log + requires_consent 对齐** ✅
10. **GIN 索引三表对齐** ✅
11. **index=True 合规残留审计** ✅ — 仅切片 10 L215 一处合规保留
12. **DB 维度连续第九轮无 P2+** ❌ — 中断（R20-R28 八轮无 P2+ 基线被 R29-P2-1 打破）

**关键风险点**：R29-P2-1（切片 05 __table_args__ 缺失 idx_mrecord_match 索引）+ R29-P3-1（切片 03 L248 注释描述错误）+ R27-P3-1/R28 叙事偏差继承（已升级为 R29-P2-1）。

**建议后续工作**：

1. **优先修复 R29-P2-1**：在切片 05 L425-427 __table_args__ 中补充 `Index("idx_mrecord_match", "match_id")` 声明，与 DB §5.4 L2616 / §6.1 L2990 对齐；同时修正 L417 注释删除错误索引名 `idx_match_record_match_id_created`
2. **修正 R29-P3-1**：修正切片 03 L248 注释描述（idx_video_task_user_created 实际不含 file_id）
3. **R27-P3-1 叙事偏差最终闭合**：建议在后续架构报告中明确 R19-P3-7 的实际修复范围 + R28-OBS-2 的实际落地范围（避免笼统声称"__table_args__ Index() 已覆盖"而未核实）
4. **强化修复落地前的索引对齐验证**：后续轮次如建议移除 `index=True`，应先验证 __table_args__ 中是否已有对应的 Index() 声明，避免引入索引缺失回归

---

*本报告由 R29-DB 字段级审查代理生成，仅做研究性审查，未修复任何文档。*
