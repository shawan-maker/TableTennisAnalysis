# 第三十轮 - DB 字段级一致性审查报告

> **审查日期**：2026-10-20
> **审查对象**：DB 设计 v1.6（`docs/04详细设计/04-数据库详细设计.md`，146636 字节，2026-10-20 13:20）+ 12 后端切片 backend.md + 13-infrastructure/admin.md + knowledge_base.md + API 设计 §2-§19 + 架构 §9.3（`docs/03系统架构/01-系统架构设计.md`）分区策略
> **审查维度**：R29 修复回归验证（R29-P2-1 切片 05 L417 注释 + R29-P3-1 切片 03 L248 注释）+ DB §2/§5/§6/§9 vs 切片 SQLAlchemy Model 字段级一致性 + 35 表口径跨文档一致性 + 索引覆盖声明交叉验证 + 分区策略 §9.1/§9.3 跨文档一致性
> **审查基线**：R29-DB 字段级审查报告（连续无 P2+ 中断；R29 发现 1 项 P2 + 1 项 P3）
> **本轮目标**：验证 R29 修复是否落地 + 判定连续无 P2+ 是否重新达成（R29 中断后 R30 是否重新开始连续第一轮 ✅ 或再次中断 ❌）
> **输出位置**：`docs/07审查报告/第三十轮/R30-DB字段级审查报告.md`

---

## 0. 执行摘要

R30 DB 字段级审查在 R29 基线上展开，重点验证 **R29-P2-1（切片 05 L417 MatchRecord.match_id 注释）** 和 **R29-P3-1（切片 03 L248 VideoTask.file_id 注释）** 两项修复的落地状态，以及 DB §2/§5/§6/§9 与切片实现层的字段级一致性 + 分区策略 §9.1/§9.3 跨文档一致性 + DB §5.4/§6.1 索引声明与切片 __table_args__ 的最新对齐状态。

**审查目标未达成**：DB 维度连续无 P2+ 未能重新达成 ❌（R29 中断后 R30 再次出现 P2）

**关键结论**：

- **R29-P2-1 修复落地验证** ⚠️ 部分修正正确 + 部分未完成：
  - **切片 05 L417 注释** ✅ 已修正：新注释正确引用 `idx_mrecord_user_date`（实际存在于 __table_args__ L426），删除了错误的 `idx_match_record_match_id_created` 索引名引用；新增 "match_id 为可选 FK 字段，无独立查询场景" 的设计决策说明；声明 "与 DB §2.13 索引声明一致"（属实，DB §2.13 L685 仅声明 `(user_id, match_date DESC)`，未声明 idx_mrecord_match）
  - **切片 05 __table_args__** ✅ 与 DB §2.13 一致：两者均不声明 idx_mrecord_match
  - **DB §5.4 L2616** ❌ 未同步清理：仍然声明 `Index("idx_mrecord_match", "match_id"),  # R26-P3-28: 补充 match_id 索引（切片 05 L417 index=True 已定义）` — 注释引用 "切片 05 L417 index=True 已定义" 已过时（L417 的 index=True 在 R28-OBS-2 已移除）
  - **DB §6.1 L2990** ❌ 未同步清理：仍然声明 `| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |  <!-- R27-P3-30: 同步 §5.4 L2616 新增索引 -->` — 该索引未在切片 05 __table_args__ 实现，且 DB §2.13 也未声明
  - **结论**：切片侧修复已正确落地（注释+__table_args__），但 R29-P2-1 的修复决策（"match_id 无独立查询场景，不需要 idx_mrecord_match 索引"）未传播到 DB §5.4/§6.1，导致 DB 设计文档内部 §2.13 ↔ §5.4/§6.1 出现新的不一致（详见 §5 R30-P2-1）

- **R29-P3-1 修复落地验证** ✅ 完全通过：
  - 切片 03 L248 注释已修正为 `# R28-OBS-1/R29-P2-2: 移除冗余 index=True（__table_args__ idx_video_task_user_created 仅含 user_id+created_at，不含 file_id；file_id 为 FK 字段，无独立查询场景，主查询路径由 user_id 复合索引覆盖，与 DB §2.5 索引声明一致）`
  - 修正点 1：删除了错误的 "已覆盖 user_id+file_id 复合索引" 声明，改为准确描述 "idx_video_task_user_created 仅含 user_id+created_at，不含 file_id"
  - 修正点 2：新增 "file_id 为 FK 字段，无独立查询场景" 的设计决策说明
  - 修正点 3：声明 "与 DB §2.5 索引声明一致"（属实，DB §2.5 L539 仅声明 `(user_id, created_at DESC), (status, created_at)`，未声明涉及 file_id 的索引）
  - 交叉验证：切片 03 __table_args__ L262-265 与 DB §2.5 L539 完全一致

- **R29-P2-3（安全报告，切片 03 L346 ShareRecord.report_id）附带验证** ✅ 通过（任务未列入但实际已修复）：
  - 切片 03 L346 注释已修正为 `# R28-OBS-1/R29-P2-3: 移除冗余 index=True（__table_args__ idx_share_user_created 已覆盖 user_id+created_at 查询路径；report_id 为 FK 字段，PostgreSQL 不会自动为 FK 创建索引，但无独立查询场景，主查询由 share_token UNIQUE 索引或 user_id 复合索引覆盖，与 DB §2.9 一致）`
  - 修正点：删除了错误的 "report_id 作为 FK 由 join 操作隐式索引" 声明，改为准确描述 "PostgreSQL 不会自动为 FK 创建索引"
  - 交叉验证：切片 03 __table_args__ L355-357 (`idx_share_user_created`) 与 DB §6.1 L2993 一致

- **35 表口径跨文档一致** ✅：DB §2 L438-442 显式声明 39 张表定义（35 核心 + 4 Phase 2 提前实现），与实施计划 §1.1（35 张 Sprint 交付）口径框架维持一致
- **分区策略 §9.1/§9.3 跨文档一致** ✅：DB §9.1 L3201-3212 与架构 §9.3 L1786-1799 完全一致，3 张表按月分区（video_task / score_record / notification_record）+ 5 张表不分区（analysis_report / feedback_record / progress_snapshot / technique_trend / plan_adjustment）
- **subscription.tier VARCHAR(20) 六处对齐** ✅：维持 R28/R29 验证结果
- **consent_log 表 + requires_consent 字段对齐** ✅：维持 R28/R29 验证结果
- **GIN 索引三表对齐** ✅：analysis_report / progress_snapshot / knowledge_entry 三张 GIN 索引完整实现
- **R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 全部维持闭环** ✅

**关键风险点**：

- **R30-P2-1（新发现 P2）**：DB §5.4 L2616 + DB §6.1 L2990 仍声明 `idx_mrecord_match (match_id)` 索引，但该索引的切片层实现（切片 05 __table_args__）从未存在，且 R29-P2-1 修复决策已明确 "match_id 无独立查询场景"。DB §5.4/§6.1 的声明现已变为**过期残留**，与 DB §2.13（权威表定义，未声明 idx_mrecord_match）和切片 05 __table_args__（未实现 idx_mrecord_match）三方不一致。R29-P2-1 的修复仅传播到切片注释层，未传播到 DB §5.4/§6.1 声明层，导致原 R29-P2-1 问题（DB §5.4/§6.1 声明 vs 切片未实现的不一致）以另一种形式延续
- **R29-P3-1（旧 P3）**：R30 验证确认已完全修复，无回归

---

## 1. 审查汇总

### 1.1 总体统计

| 维度 | 项数 | 通过 | 偏差 | 待确认 | 通过率 |
|------|------|------|------|--------|--------|
| R29-P2-1 修复回归验证（切片 05 L417 注释 + __table_args__ + DB §5.4 L2616 + DB §6.1 L2990） | 4 | 2（切片注释 + __table_args__） | 2（DB §5.4/§6.1 未同步清理） | 0 | 50% |
| R29-P3-1 修复回归验证（切片 03 L248 注释 + DB §2.5 一致性） | 2 | 2 | 0 | 0 | 100% |
| R29-P2-3 附带验证（切片 03 L346 注释 + DB §6.1 一致性） | 2 | 2 | 0 | 0 | 100% |
| R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 维持闭环 | 14 | 14 | 0 | 0 | 100% |
| 35 表口径跨文档一致性（DB §2 + 实施计划 + 架构 §5.7 + 切片总览） | 4 | 4 | 0 | 0 | 100% |
| DB §2 表定义 vs 切片 Model 字段级一致性（35 表口径） | 35 | 35 | 0 | 0 | 100% |
| DB §5 SQLAlchemy Model vs 切片 Base Model 类清单一致性 | 28 | 27 | 1（MatchRecord __table_args__ DB §5.4 含 idx_mrecord_match 而切片 05 缺失） | 0 | 96.43% |
| DB §6.1 核心索引清单 vs 切片 __table_args__ Index() 一致性 | 48 | 47 | 1（idx_mrecord_match DB §6.1 声明但切片未实现） | 0 | 97.92% |
| DB §6.2 GIN 索引三表对齐 | 3 | 3 | 0 | 0 | 100% |
| DB §9.1/§9.3 分区策略跨文档一致性（DB §9.1 vs 架构 §9.3） | 8 | 8 | 0 | 0 | 100% |
| subscription.tier VARCHAR(20) 六处对齐 | 6 | 6 | 0 | 0 | 100% |
| consent_log 表 + requires_consent 字段对齐 | 2 | 2 | 0 | 0 | 100% |
| **合计** | **156** | **154** | **2（1 项 P2 新发现 + 1 项 P3 旧维持）** | **0** | **98.72%** |

### 1.2 P0-P3 分级汇总

| 优先级 | 数量 | 编号 | 说明 |
|--------|------|------|------|
| P0（阻断级） | 0 | — | 无阻断级问题 |
| P1（严重级） | 0 | — | 无严重级问题 |
| P2（重要级） | **1** | **R30-P2-1** | DB §5.4 L2616 + DB §6.1 L2990 过期声明 idx_mrecord_match 索引，与 DB §2.13 + 切片 05 __table_args__ 三方不一致（R29-P2-1 修复决策未传播到 DB 设计文档） |
| P3（建议级） | 0 | — | R29-P3-1 已完全修复，无新 P3 发现 |

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
| R29 | 1 项 P2（R29-P2-1）+ 1 项 P3（R29-P3-1） | 24 | ❌ 连续无 P2+ 中断（R28-OBS-2 切片 05 修复引入回归） |
| **第三十轮（本轮）** | **1 项 P2（R30-P2-1）** | **24（R29 修复未完全落地）** | **❌ 连续无 P2+ 再次中断**（R29-P2-1 切片侧修复 ✅，但 DB §5.4/§6.1 过期声明未清理） |

> **判定**：R30 发现 1 项 P2 级问题（R30-P2-1），DB 维度连续无 P2+ 状态在 R29 中断后**未能重新达成**。R29-P2-1 的修复仅传播到切片注释层（切片 05 L417 注释 + __table_args__ 与 DB §2.13 对齐），但未传播到 DB §5.4 L2616 / §6.1 L2990 的索引声明层，导致原问题以 "DB §5.4/§6.1 过期声明" 的新形式延续。

---

## 2. R29 修复回归验证

### 2.1 R29-P2-1 修复回归验证（切片 05 L417 MatchRecord.match_id 注释）

R29 报告 §5.1 R29-P2-1 描述："切片 05-match_data/backend.md L425-427 MatchRecord.__table_args__ 缺失 idx_mrecord_match (match_id) 索引声明。DB §5.4 L2616 + DB §6.1 L2990 都显式声明该索引"。

R29-P2-1 建议处理："在切片 05 L425-427 __table_args__ 中补充 Index("idx_mrecord_match", "match_id") 声明，与 DB §5.4 L2616 / §6.1 L2990 对齐；同时修正 L417 注释为 # R29-P2-1: 移除冗余 index=True（__table_args__ idx_mrecord_match 已覆盖），删除错误的索引名 idx_match_record_match_id_created"。

**实际修复方式**：未按 R29 建议在切片 __table_args__ 补充索引，而是采用了另一种修复路径——更新切片 L417 注释以说明 "match_id 无独立查询场景" 的设计决策，并声明 "与 DB §2.13 索引声明一致"（而非与 DB §5.4/§6.1 对齐）。

| 编号 | 位置 | R29 状态 | R30 复核 | 验证细节 | 判定 |
|------|------|---------|---------|---------|------|
| R29-P2-1-a | 切片 05-match_data/backend.md L417 MatchRecord.match_id 注释 | P2（注释引用不存在的索引名 + 切片 __table_args__ 缺失索引） | ✅ 切片注释已修正 | L417 新注释：`ForeignKey("match.id", ondelete="SET NULL"), nullable=True,  # R28-OBS-2/R29-P2-1: 移除冗余 index=True（__table_args__ idx_mrecord_user_date 已覆盖 user_id 查询路径；match_id 为可选 FK 字段，无独立查询场景，与 DB §2.13 索引声明一致）` — 注释正确引用 idx_mrecord_user_date（实际存在于 L426 __table_args__），删除了错误的 idx_match_record_match_id_created 引用，新增 "match_id 无独立查询场景" 决策说明，声明 "与 DB §2.13 索引声明一致" | ✅ 切片注释修正落地 |
| R29-P2-1-b | 切片 05-match_data/backend.md L425-427 MatchRecord.__table_args__ | P2（缺失 idx_mrecord_match） | ✅ 与 DB §2.13 一致 | L425-427 实际内容：`__table_args__ = ( Index("idx_mrecord_user_date", "user_id", "match_date"), )` — 未补充 idx_mrecord_match。DB §2.13 L685 仅声明 `(user_id, match_date DESC)` 索引，未声明 idx_mrecord_match，因此切片 __table_args__ 与 DB §2.13 一致 | ✅ 与 DB §2.13 一致（但与 DB §5.4/§6.1 不一致，见 R30-P2-1） |
| R29-P2-1-c | DB §5.4 L2616 MatchRecord.__table_args__ Model 示例 | P2（声明 idx_mrecord_match 但切片未实现） | ❌ 未同步清理 | DB §5.4 L2614-2617 仍声明：`__table_args__ = ( Index("idx_mrecord_user_date", "user_id", "match_date"), Index("idx_mrecord_match", "match_id"),  # R26-P3-28: 补充 match_id 索引（切片 05 L417 index=True 已定义） )` — 注释 "切片 05 L417 index=True 已定义" 已过时（L417 的 index=True 在 R28-OBS-2 已移除）；R29-P2-1 修复决策（"match_id 无独立查询场景"）未传播到 DB §5.4 | ❌ DB §5.4 未同步清理 |
| R29-P2-1-d | DB §6.1 L2990 索引清单 | P2（声明 idx_mrecord_match 但切片未实现） | ❌ 未同步清理 | DB §6.1 L2990 仍声明：`| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |  <!-- R27-P3-30: 同步 §5.4 L2616 新增索引 -->` — R29-P2-1 修复决策未传播到 DB §6.1 | ❌ DB §6.1 未同步清理 |

**R29-P2-1 验证结论**：⚠️ 部分修正正确（切片 05 L417 注释 ✅ + __table_args__ 与 DB §2.13 一致 ✅）+ 部分未完成（DB §5.4 L2616 + DB §6.1 L2990 过期声明未清理 ❌）。

**关键分析**：

R29-P2-1 的根本问题是 "DB §5.4/§6.1 声明 idx_mrecord_match 但切片 __table_args__ 未实现"。R29 报告建议两种修复路径：
1. 路径 A（补索引）：在切片 05 __table_args__ 补充 `Index("idx_mrecord_match", "match_id")` 与 DB §5.4/§6.1 对齐
2. 路径 B（删声明）：从 DB §5.4/§6.1 删除 idx_mrecord_match 声明，与切片 __table_args__ 对齐

**实际修复采用了第三种路径 C**：保留切片 __table_args__ 不变（不补 idx_mrecord_match），更新切片 L417 注释以说明 "match_id 无独立查询场景" 的设计决策，并声明与 DB §2.13 一致。但未同步清理 DB §5.4 L2616 / §6.1 L2990 的过期声明。

路径 C 在切片层是自洽的（注释 + __table_args__ + DB §2.13 三方一致），但在 DB 设计文档层引入了新的内部不一致：
- DB §2.13（权威表定义）：未声明 idx_mrecord_match
- DB §5.4 L2616（Model 示例）：仍声明 idx_mrecord_match（过期）
- DB §6.1 L2990（索引清单）：仍声明 idx_mrecord_match（过期）

这导致 DB §2.13 ↔ DB §5.4/§6.1 内部不一致，以及 DB §5.4/§6.1 ↔ 切片 05 __table_args__ 跨文档不一致（详见 §5 R30-P2-1）。

### 2.2 R29-P3-1 修复回归验证（切片 03 L248 VideoTask.file_id 注释）

R29 报告 §6.1 R29-P3-1 描述："切片 03 L248 注释声称 __table_args__ idx_video_task_user_created 已覆盖 user_id+file_id 复合索引，实际 idx_video_task_user_created 仅有 (user_id, created_at)，不含 file_id"。

R29-P3-1 建议处理："修正 L248 注释为 # R28-OBS-1: 移除冗余 index=True（FK 字段由 PostgreSQL 自动创建索引，参考 R19-P3-7 模式）"。

| 编号 | 位置 | R29 状态 | R30 复核 | 验证细节 | 判定 |
|------|------|---------|---------|---------|------|
| R29-P3-1-a | 切片 03-video_analysis/backend.md L248 VideoTask.file_id 注释 | P3（注释描述与实际 __table_args__ 索引定义不符） | ✅ 注释已修正 | L248 新注释：`ForeignKey("file_record.id", ondelete="CASCADE"))  # R28-OBS-1/R29-P2-2: 移除冗余 index=True（__table_args__ idx_video_task_user_created 仅含 user_id+created_at，不含 file_id；file_id 为 FK 字段，无独立查询场景，主查询路径由 user_id 复合索引覆盖，与 DB §2.5 索引声明一致）` — 修正点 1：删除错误的 "已覆盖 user_id+file_id 复合索引" 声明；修正点 2：准确描述 "idx_video_task_user_created 仅含 user_id+created_at，不含 file_id"；修正点 3：新增 "file_id 为 FK 字段，无独立查询场景" 决策说明；修正点 4：声明 "与 DB §2.5 索引声明一致" | ✅ 注释修正落地 |
| R29-P3-1-b | 切片 03 __table_args__ L262-265 vs DB §2.5 L539 一致性 | — | ✅ 一致 | 切片 03 L263-264：`Index("idx_video_task_user_created", "user_id", "created_at"), Index("idx_video_task_status_created", "status", "created_at")`；DB §2.5 L539：`**索引**：(user_id, created_at DESC), (status, created_at) — 队列监控` — 两者完全一致，均不声明涉及 file_id 的索引 | ✅ 一致 |

**R29-P3-1 验证结论**：✅ 完全通过。切片 03 L248 注释已修正为准确描述 idx_video_task_user_created 的实际索引列，并声明与 DB §2.5 一致（属实）。切片 03 __table_args__ 与 DB §2.5 完全一致。无回归。

### 2.3 R29-P2-3 附带验证（切片 03 L346 ShareRecord.report_id 注释）

> **说明**：R29-P2-3 属于 R29 后端跨模块安全审查报告的发现（非 DB 字段级审查报告的发现），但 R30 在验证切片 03 时发现该修复也已落地，一并进行回归验证。

R29 安全报告 §4.3 R29-P2-3 描述："切片 03 L346 注释声称 report_id 作为 FK 由 join 操作隐式索引，但 SQLAlchemy/PostgreSQL 中 FK 字段不会自动创建索引"。

| 编号 | 位置 | R29 状态 | R30 复核 | 验证细节 | 判定 |
|------|------|---------|---------|---------|------|
| R29-P2-3-a | 切片 03-video_analysis/backend.md L346 ShareRecord.report_id 注释 | P2（注释 FK 隐式索引声明错误） | ✅ 注释已修正 | L346 新注释：`ForeignKey("analysis_report.id", ondelete="CASCADE"))  # R28-OBS-1/R29-P2-3: 移除冗余 index=True（__table_args__ idx_share_user_created 已覆盖 user_id+created_at 查询路径；report_id 为 FK 字段，PostgreSQL 不会自动为 FK 创建索引，但无独立查询场景，主查询由 share_token UNIQUE 索引或 user_id 复合索引覆盖，与 DB §2.9 一致）` — 修正点 1：删除错误的 "report_id 作为 FK 由 join 操作隐式索引" 声明；修正点 2：准确描述 "PostgreSQL 不会自动为 FK 创建索引"（事实正确）；修正点 3：新增 "无独立查询场景" 决策说明 | ✅ 注释修正落地 |
| R29-P2-3-b | 切片 03 ShareRecord __table_args__ L355-357 vs DB §6.1 L2993 一致性 | — | ✅ 一致 | 切片 03 L355-357：`Index("idx_share_user_created", "user_id", "created_at")`；DB §6.1 L2993：`| share_record | idx_share_user_created | (user_id, created_at DESC) | B-Tree | 按用户查分享记录 |` — 两者一致 | ✅ 一致 |

**R29-P2-3 附带验证结论**：✅ 通过。切片 03 L346 注释已修正为准确描述 PostgreSQL 不自动为 FK 创建索引的事实，并声明与 DB §2.9/§6.1 一致。切片 03 ShareRecord __table_args__ 与 DB §6.1 一致。无回归。

---

## 3. R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 维持闭环回归验证

### 3.1 R19-DB 12 项 P3 跟踪表（全部维持闭环）

| 编号 | R19 描述 | R28 状态 | R29 状态 | R30 复核 | 验证位置 |
|------|---------|---------|---------|---------|---------|
| P3-1 | 切片 09 BadgeDefinition.is_active 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 09 L236 注释 "R19-P3-1: 移除冗余 index=True" |
| P3-2 | 切片 09 CheckInRecord.checkin_date 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 09 L205-206 注释 "R19-P3-2" |
| P3-3 | 切片 09 UserBadge.user_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 09 L249 注释 "R19-P3-3" |
| P3-4 | 切片 09 BadgeProgress.user_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 09 L264 注释 "R19-P3-4" |
| P3-5 | 切片 11 Order.user_id + PaymentRecord.order_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 11 L450/L487 注释 "R19-P3-5" |
| P3-6 | 切片 02 RatingHistory.user_id + ExportTask.user_id/task_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 02 L227/L244 注释 "R19-P3-6" |
| P3-7 | 切片 03 L246/L347/L348 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 03 L246/L247/L298/L299/L324/L325/L347/L348 注释 "R19-P3-7" |
| P3-8 | 切片 05 MatchRecord.format/match_type DEFAULT 对齐 | ✅ 维持 | ✅ 维持 | ✅ 维持 | DB §2.13 注释 "R19-P3-8" |
| P3-9 | 切片 05 Match 字段命名对齐 | ✅ 维持 | ✅ 维持 | ✅ 维持 | DB §2.10 字段定义完整 |
| P3-10 | 切片 05 MatchRecord.user_id/manual_score_detail.match_record_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 05 L406/L440 注释 "R19-P3-10" |
| P3-11 | 切片 08 ProgressSnapshot.user_id/TechniqueTrend.user_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 08 L380/L401 注释 "R19-P3-11" |
| P3-12 | 切片 04 MatchStatistic.match_id 移除 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 04 L391 注释 "R19-P3-12" |

### 3.2 R26 新增 R26-P3-26 / R26-P3-27 维持闭环

| 编号 | R26 描述 | R28 状态 | R29 状态 | R30 复核 | 验证位置 |
|------|---------|---------|---------|---------|---------|
| R26-P3-26 | 切片 04 Match.user_id 移除冗余 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 04 L327 注释 "R26-P3-26" |
| R26-P3-27 | 切片 04 ScoreRecord.match_id 移除冗余 index=True | ✅ 维持 | ✅ 维持 | ✅ 维持 | 切片 04 L369 注释 "R26-P3-27" |

**结论**：R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 共 14 项 P3 修复在 R30 复核确认全部维持闭环，无回归。

---

## 4. 35 表口径跨文档一致性

### 4.1 表数口径框架（R18-P3-20 修复后稳定维持）

DB §2 顶部 L438-442 显式声明表数口径框架（R30 复核维持）：

- **39 张表定义**：DB §2.1-§2.34 共定义 39 张表（35 张核心 Phase 1 业务表 + 4 张 Phase 2 提前实现表）
- **35 张 Sprint 交付清单核心表**：实施计划 §1.1 "Phase 1 = 35 表" 指 Sprint 交付清单的核心表数
- **4 张 Phase 2 提前实现表**：`plan_adjustment`（§2.23）/ `action_category`（§2.30）/ `model_3d_asset`（§2.29）/ `training_plan`（§2.28）

### 4.2 跨文档口径核对

| 文档 | 表数声明 | R30 验证 | 状态 |
|------|---------|---------|------|
| DB §2（39 张定义） | 39 张表定义（含 4 张 Phase 2 提前实现） | L438-442 显式口径说明维持 | ✅ 一致 |
| 实施计划 §1.1（35 张 Sprint 交付） | Phase 1 = 35 张核心表 | DB §2 顶部口径说明确认 | ✅ 一致 |
| 架构 §5.7 端点清单 | 不直接声明表数，通过 §9.3 ER 图引用 | 架构 §9.3 与 DB §9.1 一致 | ✅ 一致 |
| 切片总览 | 各切片声明所属表清单 | 切片 Model 类与 DB §2 表定义一对一映射 | ✅ 一致 |

**结论**：35 表口径在 DB §2 + 实施计划 + 架构 §5.7 + 切片总览四类文档中通过 R18-P3-20 口径框架保持一致，无冲突。

---

## 5. 新发现 P2+ 问题清单

### 5.1 R30-P2-1（新发现 P2 级 DB 设计文档过期声明）

| 字段 | 值 |
|------|---|
| 编号 | R30-P2-1 |
| 优先级 | **P2（重要级）** |
| 类型 | DB 设计文档过期声明导致跨文档不一致（DB §5.4/§6.1 声明 vs DB §2.13 + 切片 __table_args__ 未实现） |
| 位置 | DB §5.4 L2616 + DB §6.1 L2990 |
| 发现轮次 | R30（首次发现；R29-P2-1 的延续） |
| 引入路径 | R29-P2-1 修复采用路径 C（保留切片 __table_args__ 不变 + 更新切片注释说明 "match_id 无独立查询场景"），但未同步清理 DB §5.4 L2616 / §6.1 L2990 的 idx_mrecord_match 声明，导致 R29-P2-1 修复决策未传播到 DB 设计文档层 |
| 影响范围 | DB §5.4 L2614-2617 MatchRecord.__table_args__ Model 示例 + DB §6.1 L2990 索引清单 + DB §2.13 L685 表定义 + 切片 05 L417/L425-427 |
| 当前状态 | DB §5.4 L2616 仍声明 `Index("idx_mrecord_match", "match_id"),  # R26-P3-28: 补充 match_id 索引（切片 05 L417 index=True 已定义）`（注释 "切片 05 L417 index=True 已定义" 已过时）；DB §6.1 L2990 仍声明 `| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |`；但 DB §2.13 L685 仅声明 `(user_id, match_date DESC)`，未声明 idx_mrecord_match；切片 05 __table_args__ L425-427 也未实现 idx_mrecord_match |
| 功能影响 | **低**：R29-P2-1 修复决策已明确 "match_id 为可选 FK 字段，无独立查询场景"，因此 idx_mrecord_match 索引本身不需要。但 DB §5.4/§6.1 的过期声明会误导后续维护者认为该索引应被实现，或在 Alembic 迁移时基于 DB §5.4 Model 示例生成多余的 CreateIndex 操作 |
| 规范影响 | **高**：DB 设计文档内部 §2.13 ↔ §5.4/§6.1 出现不一致；DB §5.4/§6.1 ↔ 切片 05 __table_args__ 跨文档不一致。R29-P2-1 的根本问题（DB §5.4/§6.1 声明 vs 切片未实现的不一致）以 "DB §5.4/§6.1 过期声明" 的新形式延续 |
| 建议处理 | 方案 A（推荐）：删除 DB §5.4 L2616 的 `Index("idx_mrecord_match", "match_id"),` 行及其注释，并在 L2614-2617 __table_args__ 仅保留 `Index("idx_mrecord_user_date", "user_id", "match_date")`；同时删除 DB §6.1 L2990 的 `| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |` 行。方案 B（备选）：保留 DB §5.4/§6.1 声明，在切片 05 __table_args__ 补充 `Index("idx_mrecord_match", "match_id")` 实现（即采用 R29 原建议路径 A） |
| 是否阻断连续无 P2+ | **是** |

### 5.2 R30-P2-1 详细证据链

**DB §5.4 L2614-2617 SQLAlchemy Model 示例**（MatchRecord.__table_args__）——R30 复核原文：

```python
__table_args__ = (
    Index("idx_mrecord_user_date", "user_id", "match_date"),
    Index("idx_mrecord_match", "match_id"),  # R26-P3-28: 补充 match_id 索引（切片 05 L417 index=True 已定义）
)
```

**问题点 1**：L2616 注释 "切片 05 L417 index=True 已定义" 已过时 — 切片 05 L417 的 `index=True` 在 R28-OBS-2 修复时已移除，R29-P2-1 修复时也未重新添加。

**DB §6.1 L2990 索引清单**——R30 复核原文：

```
| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |  <!-- R27-P3-30: 同步 §5.4 L2616 新增索引 -->
```

**问题点 2**：L2990 注释 "同步 §5.4 L2616 新增索引" — 但 §5.4 L2616 本身就是过期的，§6.1 L2990 同步了一个过期的声明。

**DB §2.13 L685 表定义**——R30 复核原文：

```
**索引**：`(user_id, match_date DESC)`
```

**DB §2.13 仅声明 `(user_id, match_date DESC)`，未声明 idx_mrecord_match**。

**切片 05 L425-427 __table_args__**——R30 复核原文：

```python
__table_args__ = (
    Index("idx_mrecord_user_date", "user_id", "match_date"),
)
```

**切片 05 __table_args__ 仅实现 idx_mrecord_user_date，未实现 idx_mrecord_match**。

**切片 05 L417 注释**——R30 复核原文（R29-P2-1 修复后）：

```python
match_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("match.id", ondelete="SET NULL"), nullable=True,  # R28-OBS-2/R29-P2-1: 移除冗余 index=True（__table_args__ idx_mrecord_user_date 已覆盖 user_id 查询路径；match_id 为可选 FK 字段，无独立查询场景，与 DB §2.13 索引声明一致）
    comment="关联的记分牌比赛ID（可选）",
)
```

**切片 L417 注释声明 "与 DB §2.13 索引声明一致"** — 属实（DB §2.13 未声明 idx_mrecord_match，切片也未实现）。但注释未提及 DB §5.4/§6.1 仍声明 idx_mrecord_match 的事实。

**问题链路总结**：

1. R26-P3-28 在 DB §5.4 L2616 补充 `Index("idx_mrecord_match", "match_id")` 注释 "切片 05 L417 index=True 已定义" — 假设切片 05 L417 的 `index=True` 是该索引的切片实现
2. R27-P3-30 在 DB §6.1 L2990 同步声明 `idx_mrecord_match` 索引
3. R28-OBS-2 修复移除切片 05 L417 的 `index=True`（但 R28 报告 §7.3 叙事偏差声称 "__table_args__ Index() 重复声明"，实际 __table_args__ 并无 idx_mrecord_match）
4. R29-P2-1 发现 "DB §5.4/§6.1 声明 idx_mrecord_match 但切片 __table_args__ 未实现"，标记为 P2
5. R29-P2-1 修复采用路径 C（更新切片注释 + 声明与 DB §2.13 一致），但未同步清理 DB §5.4 L2616 / §6.1 L2990 的过期声明
6. R30 复核发现 DB §5.4 L2616 / §6.1 L2990 的过期声明仍然存在，导致 DB 设计文档内部 §2.13 ↔ §5.4/§6.1 不一致，以及 DB §5.4/§6.1 ↔ 切片 05 __table_args__ 跨文档不一致

---

## 6. 新发现 P3/OBS 问题清单

### 6.1 R30 无新发现 P3/OBS 问题

R30 审查范围内未发现新的 P3 或 OBS 级问题。所有 R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 + R28-OBS-1/R28-OBS-2 + R29-P3-1 均维持闭环或已完全修复。

### 6.2 R29 报告叙事偏差继承状态

R29 报告 §14.3 提及 "R27-P3-1 持续未闭合" + "R28 报告 §7.3 叙事偏差" — R30 复核确认：

- R28 报告 §7.3 声称 "切片 05 L417 与 __table_args__ Index() 重复声明" 的叙事偏差在 R29-P2-1 修复后已通过切片注释澄清（注释明确说明 "match_id 无独立查询场景"）
- 但 DB §5.4 L2616 的注释 "切片 05 L417 index=True 已定义" 仍保留了 R26-P3-28 的叙事偏差（声称切片 L417 有 index=True，实际已在 R28-OBS-2 移除）
- 这属于 R30-P2-1 的一部分，不单独登记为新 P3

---

## 7. 18 项检查清单详细结果

### 7.1 检查清单汇总

| # | 检查项 | 状态 | 行号引用 | 说明 |
|---|--------|------|---------|------|
| 1 | R29 修复回归验证 | ⚠️ | 切片 05 L417/L425-427 + 切片 03 L248/L346 + DB §5.4 L2616 + DB §6.1 L2990 | R29-P2-1 ⚠️ 切片侧修复 ✅ + DB §5.4/§6.1 过期声明未清理 ❌（见 R30-P2-1）；R29-P3-1 ✅ 完全通过；R29-P2-3 ✅ 附带验证通过 |
| 2 | 表数 35 一致性 | ✅ | DB §2 L438-442 + 实施计划 §1.1 + 架构 §5.7 + 切片总览 | R18-P3-20 口径框架维持一致 |
| 3 | 逐表字段级一致性 | ✅ | DB §2 DDL vs 切片 SQLAlchemy Model | 35 表口径字段对齐 |
| 4 | 索引完整性 | ❌ | DB §5.4 L2616 + DB §6.1 L2990 vs 切片 05 __table_args__ | R30-P2-1：DB §5.4/§6.1 过期声明 idx_mrecord_match，与 DB §2.13 + 切片 05 不一致 |
| 5 | 索引命名规范 | ✅ | 全切片 __table_args__ | idx_<表>_<字段> / uq_<表>_<字段> 规范统一 |
| 6 | 字段类型一致性 | ✅ | DB §2 vs 切片 Model | VARCHAR/TEXT/JSONB/UUID/BigInteger 类型对齐 |
| 7 | defaults 值一致性 | ✅ | DB §2 vs 切片 Model | default= 与 server_default 对齐 |
| 8 | nullable 一致性 | ✅ | DB §2 vs 切片 Model | nullable 标注一致 |
| 9 | 外键约束 | ✅ | 切片 Model ForeignKey | ondelete="CASCADE"/"SET NULL" 与 DB §2 一致 |
| 10 | 分区策略 §9.1/§9.3 | ✅ | DB §9.1 L3201-3212 + 架构 §9.3 L1786-1799 | 3 张表按月分区 + 5 张不分区，跨文档完全一致 |
| 11 | 时间戳字段 | ✅ | 全切片 created_at/updated_at | DateTime(timezone=True) + default/onupdate 完整 |
| 12 | JSONB 字段 | ✅ | preferences/metadata/points_rules/result_data/benefits/quota_config | JSONB 类型对齐 |
| 13 | 软删除字段 | ✅ | user.scheduled_deletion_at + deletion_reason | R22 闭环维持 |
| 14 | 多语言字段 i18n | ✅ | — | 见 R22 报告，DB 维度无新发现 |
| 15 | 主键类型 | ✅ | 全切片 id BigInteger primary_key autoincrement=True | BIGSERIAL 一致 |
| 16 | 表名命名规范 | ✅ | 全切片 __tablename__ | snake_case 单数命名一致 |
| 17 | 枚举类型 | ✅ | tier/status/format/match_type 等 | VARCHAR(20) + 注释枚举值，与 DB §2 一致 |
| 18 | 新 P2+ 扫描 + 连续无 P2+ 判定 | ❌ | R30-P2-1（DB §5.4/§6.1 过期声明 idx_mrecord_match） | DB 维度 R29 中断后 R30 再次出现 P2，连续无 P2+ 未重新达成 |

### 7.2 关键检查项详细结果

#### 检查项 1 - R29 修复回归验证（详细）

详见 §2.1 R29-P2-1 修复回归验证 + §2.2 R29-P3-1 修复回归验证 + §2.3 R29-P2-3 附带验证。

**R29 修复回归结论**：
- R29-P2-1 ⚠️ 部分修正（切片 05 L417 注释 ✅ + __table_args__ 与 DB §2.13 一致 ✅ + DB §5.4/§6.1 过期声明未清理 ❌）
- R29-P3-1 ✅ 完全通过（切片 03 L248 注释修正 + __table_args__ 与 DB §2.5 一致）
- R29-P2-3 ✅ 附带验证通过（切片 03 L346 注释修正 + __table_args__ 与 DB §6.1 一致）

#### 检查项 4 - 索引完整性

DB §6.1 L2966-3014 共声明 48 条索引（R29 基线 48 条）。R30 复核关键索引与切片 __table_args__ Index() / UniqueConstraint() 声明一致性：

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
| **idx_mrecord_match** | **DB §6.1 L2990 声明但切片 05 __table_args__ 未实现；DB §2.13 也未声明** | **❌ R30-P2-1（DB §6.1 过期声明）** |
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

**索引完整性结论**：DB §6.1 声明的 48 条索引中，**47 条在切片 __table_args__ Index() / UniqueConstraint() 中完整实现**，1 条（idx_mrecord_match）在 DB §6.1 L2990 过期声明但切片 05 __table_args__ 未实现，且 DB §2.13 也未声明（R30-P2-1）。

**与 R29 对比**：R29-P2-1 将 idx_mrecord_match 判定为 "切片缺失索引"（DB §6.1 声明但切片未实现）；R30 复核后，切片侧已通过注释修复明确 "不需要 idx_mrecord_match"，但 DB §6.1 L2990 的声明未清理，问题从 "切片缺失索引" 转变为 "DB §6.1 过期声明"。P2 问题持续存在，只是表现形式变化。

#### 检查项 10 - 分区策略 §9.1/§9.3 跨文档一致性

DB §9.1 L3201-3212 vs 架构 §9.3 L1786-1799（`docs/03系统架构/01-系统架构设计.md`）对照：

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

DB §2.34 consent_log 表 8 字段定义（L1085-1102）与切片 01-auth ConsentLog Model（L147-170）字段完全对齐（R30 复核维持）。

### 9.2 requires_consent 字段对齐

切片 01-auth/backend.md LoginResponse Schema（L217-228）维持 `requires_consent: bool = False  # PIPL-001：是否需要用户同意当前版本隐私政策`（L222）。

phone_login / wechat_login 对称注入（R22-P1-1 修复持续保持）维持。

**结论**：consent_log 表 + requires_consent 字段四处全部对齐，R22-P1-1 修复维持闭环。

---

## 10. GIN 索引三表对齐（R19-P2-2/P2-3/P2-5 维持闭环）

| 表 | JSONB 字段 | DB §6.2 声明 | 切片实现 | 状态 |
|----|----------|---------|---------|------|
| analysis_report | report_text | L2973 GIN(to_tsvector) | 切片 03 L311 `Index("idx_report_text_gin", text("to_tsvector('simple', report_text)"), postgresql_using="gin")` | ✅ |
| progress_snapshot | metrics_snapshot | L2979 GIN | 切片 08 L390 `Index("idx_ps_metrics_gin", "metrics_snapshot", postgresql_using="gin")` | ✅ |
| knowledge_entry | content | L3022 GIN | 13-infrastructure/knowledge_base.md L97 `Index("idx_knowledge_entry_content_gin", "content", postgresql_using="gin")` | ✅ |

**结论**：DB §6.2 声明的 3 张 GIN 索引在切片 03 + 切片 08 + 13-infrastructure/knowledge_base.md 三处全部实现，命名规范一致，R19-P2-2/P2-3/P2-5 修复维持闭环。

---

## 11. index=True 合规残留最终审计

### 11.1 全切片 + admin.md + knowledge_base.md index=True 残留清单

R30 复核 `index=True` 在所有切片 backend.md + 13-infrastructure 下文件共命中实际残留 1 处（不含注释行）：

| 文件 | 行号 | 字段 | 上下文 | R30 判定 |
|------|------|------|--------|---------|
| 切片 10-membership/backend.md | L215 | `MembershipTier.is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)  # R28-OBS-2: 保留 index=True（业务查询"激活的会员等级列表"常用过滤条件，DB §6.1 应补充声明此索引）` | 运营筛选启用的会员等级配置 | ✅ 合规保留（R28-OBS-2 已落地，注释完整在位；R29/R30 维持） |

### 11.2 R28-OBS-1 / R28-OBS-2 / R29-P2-1 / R29-P3-1 残留处理结果

- **R28-OBS-1（切片 03 L248/L346 冗余残留）**：✅ 已落地修复（index=True 已移除，注释 "R28-OBS-1" 完整在位）。L248 注释描述错误已在 R29-P3-1 修复，R30 复核确认注释准确；L346 注释错误已在 R29-P2-3 修复，R30 复核确认注释准确
- **R28-OBS-2 切片 05 L417（合理保留）**：⚠️ 切片侧修复 ✅（注释修正 + __table_args__ 与 DB §2.13 一致），但 DB §5.4 L2616 / §6.1 L2990 过期声明未清理（R30-P2-1）
- **R28-OBS-2 切片 10 L215（合理保留）**：✅ 已落地修复（保留 index=True + 补注释 "R28-OBS-2: 保留 index=True..."）
- **R29-P2-1（切片 05 L417 注释）**：⚠️ 切片侧修复 ✅，DB §5.4/§6.1 未同步清理（R30-P2-1）
- **R29-P3-1（切片 03 L248 注释）**：✅ 已完全修复，R30 复核无回归

### 11.3 其他切片 index=True 已全部清理验证

`index=True` 在切片 01-auth / 02-user / 03-video_analysis / 04-scoring / 05-match_data / 06-data_dashboard / 07-training_advice / 08-progress_analysis / 09-gamification / 11-payment / 12-notification + 13-infrastructure/admin.md + knowledge_base.md **0 处实际残留**（仅注释行命中）。

各切片 R19-P3-x / R26-P3-x / R18-P3-x / R20-P3-x / R28-OBS-1 / R29-P2-1 / R29-P2-2 / R29-P2-3 注释完整在位（R30 复核维持）。

**结论**：除切片 10 L215 合规保留外，其他切片的 index=True 已全部清理。R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 + R18-P3-2 + R20-P3-2 + R28-OBS-1 + R29-P2-1（切片侧）+ R29-P2-2 + R29-P2-3 全部维持闭环。R28-OBS-2 切片 05 L417 切片侧修复落地，但 DB §5.4/§6.1 过期声明未清理（R30-P2-1）。

---

## 12. DB §5 SQLAlchemy Model vs 切片 Base Model 类清单一致性

### 12.1 切片 Base Model 类清单（共 37 个 Base Model）

R30 复核维持 R29 验证结果：切片层 30 个 Base Model + admin.md 3 个 + knowledge_base.md 4 个 = 37 个 Base Model，与 DB §2 表定义一对一映射。

### 12.2 DB §5 Model 代码示例 vs 切片 __table_args__ 一致性

R30 重点关注 MatchRecord Model 示例（DB §5.4 L2614-2617）vs 切片 05 L425-427 __table_args__：

- **DB §5.4 L2614-2617**：`__table_args__ = ( Index("idx_mrecord_user_date", "user_id", "match_date"), Index("idx_mrecord_match", "match_id"), )` — 含 idx_mrecord_match
- **切片 05 L425-427**：`__table_args__ = ( Index("idx_mrecord_user_date", "user_id", "match_date"), )` — 不含 idx_mrecord_match

**不一致**：DB §5.4 Model 示例含 idx_mrecord_match，切片 05 __table_args__ 不含。该不一致即 R30-P2-1 的核心表现。

**结论**：DB §5 Model 代码示例与切片层 Base Model 类清单一对一映射维持，字段级一致性维持。但 MatchRecord __table_args__ 在 DB §5.4 与切片 05 之间存在不一致（R30-P2-1）。

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
| match_record | API §8（注销时保留） | L772 注释 "比赛记录 match_record.user_id 保留" | ✅ |

**结论**：DB §2 表定义与 API §2-§19 Schema 字段一致性维持，关键表字段全部对齐。

---

## 14. 关键风险点

### 14.1 R30-P2-1（P2 级 DB 设计文档过期声明，阻断连续无 P2+ 重新达成）

**风险描述**：DB §5.4 L2616 + DB §6.1 L2990 仍声明 `idx_mrecord_match (match_id)` 索引，但该索引：
- 在 DB §2.13（权威表定义）中未声明
- 在切片 05 __table_args__ 中未实现
- R29-P2-1 修复决策已明确 "match_id 无独立查询场景"

DB §5.4 L2616 的注释 "切片 05 L417 index=True 已定义" 已过时（L417 的 index=True 在 R28-OBS-2 已移除）。DB §6.1 L2990 的注释 "同步 §5.4 L2616 新增索引" 同步了一个过期的声明。

**影响评估**：
- 功能影响：**低** — R29-P2-1 修复决策已明确不需要 idx_mrecord_match 索引。但 DB §5.4 Model 示例可能误导开发者基于 Model 示例生成 Alembic 迁移时创建多余的 idx_mrecord_match 索引
- 规范影响：**高** — DB 设计文档内部 §2.13 ↔ §5.4/§6.1 不一致；DB §5.4/§6.1 ↔ 切片 05 __table_args__ 跨文档不一致。R29-P2-1 的根本问题（DB §5.4/§6.1 声明 vs 切片未实现）以 "DB §5.4/§6.1 过期声明" 的新形式延续
- 引入路径：R29-P2-1 修复采用路径 C（更新切片注释 + 声明与 DB §2.13 一致），但未同步清理 DB §5.4 L2616 / §6.1 L2990 的过期声明

**建议处理**：
1. **方案 A（推荐）**：删除 DB §5.4 L2616 的 `Index("idx_mrecord_match", "match_id"),` 行及其注释；删除 DB §6.1 L2990 的 `| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |` 行。同时在 DB §5.4 L2614-2617 __table_args__ 仅保留 `Index("idx_mrecord_user_date", "user_id", "match_date")`。DB §6.1 索引总数从 48 条降为 47 条
2. **方案 B（备选）**：保留 DB §5.4/§6.1 声明，在切片 05 __table_args__ 补充 `Index("idx_mrecord_match", "match_id")` 实现（即采用 R29 原建议路径 A）。但此方案与 R29-P2-1 修复决策（"match_id 无独立查询场景"）矛盾

### 14.2 R29-P3-1（旧 P3，R30 已完全修复）

R29-P3-1 在 R30 复核确认已完全修复，切片 03 L248 注释准确描述 idx_video_task_user_created 的实际索引列，与 DB §2.5 一致。无回归，无残留风险。

### 14.3 R29 报告叙事偏差继承状态

R29 报告 §14.3 提及的 "R27-P3-1 持续未闭合" + "R28 报告 §7.3 叙事偏差" 在 R30 复核状态：
- 切片侧已通过 R29-P2-1 修复澄清（注释明确 "match_id 无独立查询场景"）
- 但 DB §5.4 L2616 的注释 "切片 05 L417 index=True 已定义" 仍保留 R26-P3-28 的叙事偏差
- 这属于 R30-P2-1 的一部分，建议在清理 DB §5.4 L2616 时一并修正注释

---

## 15. R30 关键结论

> **🎯 DB 维度连续无 P2+ 未能重新达成 ❌**
>
> R30 DB 字段级审查覆盖 DB §2/§5/§6/§9 + 12 后端切片 + 13-infrastructure/admin.md + knowledge_base.md + API §2-§19 + 架构 §9.3 共 18 个文档，156 个检查点 154 个通过（通过率 98.72%）：
>
> - **R29-P2-1 修复落地** ⚠️ 部分修正：切片 05 L417 注释 ✅ 修正（正确引用 idx_mrecord_user_date，声明与 DB §2.13 一致）；切片 05 __table_args__ ✅ 与 DB §2.13 一致；DB §5.4 L2616 ❌ 过期声明未清理；DB §6.1 L2990 ❌ 过期声明未清理
> - **R29-P3-1 修复落地** ✅ 完全通过：切片 03 L248 注释修正（准确描述 idx_video_task_user_created 仅含 user_id+created_at），与 DB §2.5 一致
> - **R29-P2-3 附带验证** ✅ 通过：切片 03 L346 注释修正（删除 "FK 由 join 操作隐式索引" 错误声明，准确描述 PostgreSQL 不自动为 FK 创建索引），与 DB §6.1 一致
> - **R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 全部维持闭环** ✅
> - **35 表口径跨文档一致** ✅
> - **分区策略 §9.1/§9.3 跨文档一致** ✅
> - **subscription.tier VARCHAR(20) 六处对齐** ✅
> - **consent_log + requires_consent 对齐** ✅
> - **GIN 索引三表对齐** ✅
> - **index=True 合规残留审计** ✅：仅切片 10 L215 一处合规保留
> - **DB §5 Model 代码示例 vs 切片 Base Model 一致性** ⚠️：MatchRecord __table_args__ 不一致（DB §5.4 含 idx_mrecord_match，切片 05 缺失）—— 即 R30-P2-1
> - **DB §6.1 索引清单 48 条 vs 切片 __table_args__ Index() 一致性** ⚠️：47 条完整实现 + 1 条过期声明（idx_mrecord_match，R30-P2-1）
> - **DB §2 vs API §2-§19 Schema 字段一致性** ✅

---

## 16. R30-P2-1 详细记录

### 16.1 R30-P2-1（P2 重要级）

| 字段 | 值 |
|------|---|
| 编号 | R30-P2-1 |
| 优先级 | **P2（重要级）** |
| 类型 | DB 设计文档过期声明导致跨文档不一致 |
| 位置 | DB §5.4 L2616 + DB §6.1 L2990 |
| 发现轮次 | R30（首次发现；R29-P2-1 的延续） |
| 引入路径 | R29-P2-1 修复采用路径 C（更新切片注释 + 声明与 DB §2.13 一致），未同步清理 DB §5.4 L2616 / §6.1 L2990 的 idx_mrecord_match 声明 |
| 影响范围 | DB §5.4 L2614-2617 + DB §6.1 L2990 + DB §2.13 L685 + 切片 05 L417/L425-427 |
| 当前状态 | DB §5.4 L2616 仍声明 `Index("idx_mrecord_match", "match_id"),  # R26-P3-28: 补充 match_id 索引（切片 05 L417 index=True 已定义）`（注释过时）；DB §6.1 L2990 仍声明 `| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |`；DB §2.13 L685 仅声明 `(user_id, match_date DESC)`；切片 05 __table_args__ 仅实现 idx_mrecord_user_date |
| 功能影响 | 低（R29-P2-1 修复决策已明确不需要 idx_mrecord_match；但 DB §5.4 Model 示例可能误导 Alembic 迁移生成多余索引） |
| 规范影响 | 高（DB §2.13 ↔ §5.4/§6.1 内部不一致；DB §5.4/§6.1 ↔ 切片 05 跨文档不一致） |
| 建议处理 | 方案 A（推荐）：删除 DB §5.4 L2616 的 idx_mrecord_match 行 + DB §6.1 L2990 的 idx_mrecord_match 行；方案 B（备选）：在切片 05 __table_args__ 补充 idx_mrecord_match 实现（但与 R29-P2-1 修复决策矛盾） |
| 是否阻断连续无 P2+ | **是** |

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
| R28 | R28-OBS-1/R28-OBS-2 属观察项，未落地修复 | 14 |
| R29 | R28-OBS-1 已落地 + R28-OBS-2 切片 10 已落地 + R28-OBS-2 切片 05 落地引入 R29-P2-1 回归 + R29-P3-1 登记 | 14 + 2 项落地 - 1 项回归 = 15（R29-P2-1 待修复） |
| **R30（本轮）** | R29-P2-1 切片侧修复 ✅（切片 05 L417 注释 + __table_args__ 与 DB §2.13 一致） + R29-P3-1 完全修复 ✅ + R29-P2-3 附带修复 ✅；但 DB §5.4/§6.1 过期声明未清理（R30-P2-1 新发现） | **15 + 3 项切片侧修复 - 1 项新 P2（DB §5.4/§6.1 过期声明） = 17（切片侧）+ R30-P2-1 待修复（DB 设计文档侧）** |

### 17.2 连续无 P2+ 追踪表

| 轮次 | DB 维度 P0 | DB 维度 P1 | DB 维度 P2 | DB 维度 P3（新增） | 连续无 P2+ |
|------|-----------|-----------|-----------|------------------|-----------|
| R19 | 0 | 1 | 5 | 12 | 基线 |
| R20 | 0 | 0 | 0 | 0 | ✅ 第一轮 |
| R21 | 0 | 0 | 0 | 0 | ✅ 第二轮 |
| R22 | 0 | 0 | 0 | 0 | ✅ 第三轮 |
| R23 | 0 | 0 | 0 | 0 | ✅ 第四轮 |
| R24 | 0 | 0 | 0 | 0 | ✅ 第五轮 |
| R25 | 0 | 0 | 0 | 0 | ✅ 第六轮 |
| R26 | 0 | 0 | 0 | 0 | ✅ 第七轮 |
| R27 | 0 | 0 | 0 | 0 | ✅ 第八轮（继承） |
| R28 | 0 | 0 | 0 | 2（观察项） | ✅ 第八轮 |
| R29 | 0 | 0 | 1（R29-P2-1） | 1（R29-P3-1） | ❌ 中断 |
| **R30** | **0** | **0** | **1（R30-P2-1）** | **0** | **❌ 再次中断（未能重新达成连续第一轮）** |

> **判定**：DB 维度连续无 P2+ 在 R29 中断后，R30 **未能重新达成连续第一轮**。R30 发现 1 项 P2（R30-P2-1：DB §5.4 L2616 + DB §6.1 L2990 过期声明 idx_mrecord_match），该问题是 R29-P2-1 修复未完全传播到 DB 设计文档层的延续。

---

## 18. 综述

R30 DB 字段级审查在 R29 基线上展开，重点验证 R29-P2-1 + R29-P3-1 两项修复的落地状态，以及 DB §2/§5/§6/§9 与切片实现层的字段级一致性 + 分区策略 §9.1/§9.3 跨文档一致性。审查覆盖 18 个文档、156 个检查点，通过率 98.72%（154 通过 + 1 项 P2 + 1 项 P3 旧维持已修复）。

**核心结论**：

1. **R29-P2-1 修复落地** ⚠️ 部分修正 — 切片 05 L417 注释 ✅ 修正（正确引用 idx_mrecord_user_date，声明与 DB §2.13 一致）；切片 05 __table_args__ ✅ 与 DB §2.13 一致；DB §5.4 L2616 ❌ 过期声明未清理；DB §6.1 L2990 ❌ 过期声明未清理
2. **R29-P3-1 修复落地** ✅ 完全通过 — 切片 03 L248 注释修正（准确描述 idx_video_task_user_created 实际索引列），与 DB §2.5 一致
3. **R29-P2-3 附带验证** ✅ 通过 — 切片 03 L346 注释修正（删除 "FK 由 join 操作隐式索引" 错误声明），与 DB §6.1 一致
4. **R30-P2-1（新发现 P2）** — DB §5.4 L2616 + DB §6.1 L2990 过期声明 idx_mrecord_match，与 DB §2.13 + 切片 05 __table_args__ 三方不一致（R29-P2-1 修复决策未传播到 DB 设计文档层）
5. **R19-DB 12 项 P3 + R26-P3-26/R26-P3-27 全部维持闭环** ✅ — 无回归
6. **35 表口径跨文档一致** ✅
7. **分区策略 §9.1/§9.3 跨文档一致** ✅
8. **subscription.tier VARCHAR(20) 六处对齐** ✅
9. **consent_log + requires_consent 对齐** ✅
10. **GIN 索引三表对齐** ✅
11. **index=True 合规残留审计** ✅ — 仅切片 10 L215 一处合规保留
12. **DB 维度连续无 P2+ 重新达成** ❌ — R29 中断后 R30 再次出现 P2（R30-P2-1），未能重新开始连续第一轮

**关键风险点**：R30-P2-1（DB §5.4 L2616 + DB §6.1 L2990 过期声明 idx_mrecord_match）— R29-P2-1 修复决策未传播到 DB 设计文档层。

**建议后续工作**：

1. **优先修复 R30-P2-1**：采用方案 A，删除 DB §5.4 L2616 的 `Index("idx_mrecord_match", "match_id"),` 行及其过时注释；删除 DB §6.1 L2990 的 `| match_record | idx_mrecord_match | (match_id) | B-Tree | 按比赛查比赛记录 |` 行。DB §6.1 索引总数从 48 条降为 47 条。同时在 DB §5.4 L2614-2617 __table_args__ 仅保留 `Index("idx_mrecord_user_date", "user_id", "match_date")`
2. **强化修复落地的传播完整性**：后续轮次如采用 "更新注释 + 声明与某节一致" 的修复路径，应同步清理所有相关声明节（如 DB §5.4 Model 示例 + DB §6.1 索引清单），避免修复决策仅在切片层传播而 DB 设计文档层保留过期声明
3. **R27-P3-1 叙事偏差最终闭合**：建议在清理 DB §5.4 L2616 时，一并修正 R26-P3-28 的过时注释 "切片 05 L417 index=True 已定义"，避免叙事偏差延续

---

*本报告由 R30-DB 字段级审查代理生成，仅做研究性审查，未修复任何文档。*
