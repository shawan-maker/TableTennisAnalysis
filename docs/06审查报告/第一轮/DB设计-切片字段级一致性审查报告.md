# DB 设计 — 切片字段级一致性审查报告

> **审查日期**：2026-10-12
> **审查范围**：数据库详细设计 v1.3（§2 Phase 1 表定义 + §5 SQLAlchemy 代码块）vs 垂直切片后端设计 01-12 + 13a-13e（backend.md 中 Model 定义）
> **审查维度**：表归属、字段名、字段类型、主键设计、外键约束、新增/缺失字段、重复定义
> **审查类型**：只读审查（未修改任何源文件）

---

## 1. 总览

### 1.1 逐表一致性矩阵

| # | 表名 | DB 设计章节 | 切片归属 | 一致性 | 关键偏差 |
|---|------|-----------|---------|:---:|------|
| 01 | user | §2.1 + §5.1 | 01-auth, 02-user | ⚠️ | 02-user 合并 user_profile 字段进 User 模型；新增注销字段 |
| 02 | user_profile | §2.2 + §5.1 | 02-user | ❌ | 切片将 user_profile 字段合并进 User，未独立建表 |
| 03 | rating_history | §2.3 | 02-user | ✅ | 字段一致 |
| 04 | file_record | §2.4 + §5.2 | 03-video_analysis, 13e-file_management | ❌ | 重复定义；字段名 filename vs original_filename |
| 05 | video_task | §2.5 + §5.2 | 03-video_analysis, 13a-ai_pipeline | ⚠️ | 切片新增 task_uuid, total_steps, step_name, progress, estimated_remaining_seconds |
| 06 | pipeline_step | §2.6 | 13a-ai_pipeline | ✅ | 字段一致 |
| 07 | analysis_report | §2.7 + §5.2 | 03-video_analysis, 06-data_dashboard | ❌ | 06-dashboard 重复定义且字段简化；切片新增 is_anonymized |
| 08 | feedback_record | §2.8 + §5.6 | 03-video_analysis | ✅ | v1.3 已同步 status 字段 |
| 09 | share_record | §2.9 + §5.2 | 03-video_analysis | ⚠️ | 字段名 token vs share_token, share_card_url vs card_image_url；缺失 share_scope, view_count |
| 10 | match | §2.10 + §5.3 | 04-scoring | ⚠️ | 切片新增 final_score, started_at, abandoned_at, updated_at；DB 设计内部 §2.10 与 §5.3 字段不一致 |
| 11 | score_record | §2.11 + §5.3 | 04-scoring | ✅ | 切片含 game_number + is_key_point（DB 表定义有，代码块遗漏） |
| 12 | match_statistic | §2.12 + §5.3 | 04-scoring | ⚠️ | stats_data 类型 Text vs JSONB |
| 13 | match_record | §2.13 + §5.4 | 05-match_data, 06-data_dashboard | ❌ | 06-dashboard 重复定义且字段简化；切片新增 is_detailed, updated_at |
| 14 | manual_score_detail | §2.14 + §5.4 | 05-match_data | ⚠️ | FK 字段名 record_id vs match_record_id |
| 15 | user_points | §2.15 | 09-gamification | ✅ | 字段一致 |
| 16 | checkin_record | §2.16 | 09-gamification | ✅ | 字段一致 |
| 17 | subscription | §2.17 + §5.5 | 10-membership | ⚠️ | tier 长度 String(32) vs String(20) |
| 18 | order | §2.18 + §5.5 | 11-payment | ⚠️ | DB 设计内部 §2.18 (product_ref_id) vs §5.5 (subscription_id) 不一致；切片两者都有 |
| 19 | payment_record | §2.19 + §5.5 | 11-payment | ✅ | 字段一致 |
| 20 | refund_record | — | 11-payment | ❌ | DB 设计未定义此表 |
| 21 | notification_record | §2.20 + §5.6 | 12-notification | ✅ | 字段一致 |
| 22 | progress_snapshot | §2.21 + §5.6 | 08-progress_analysis | ✅ | 字段一致 |
| 23 | technique_trend | §2.22 + §5.6 | 08-progress_analysis | ✅ | 字段一致 |
| 24 | plan_adjustment | §2.23 | 07-training_advice | ✅ | 字段一致 |
| 25 | badge_definition | §3.1.4 | 09-gamification | ✅ | v1.3 已改为 VARCHAR(64) PK，切片一致 |
| 26 | user_badge | §3.1.5 | 09-gamification | ✅ | 字段一致 |
| 27 | badge_progress | §3.1.6 | 09-gamification | ✅ | v1.3 已补充此表，切片一致 |
| 28 | membership_tier_config | §2.31 | 10-membership | ❌ | PK 设计不同（tier PK vs id PK + tier UNIQUE）；切片新增 is_active/created_at/updated_at |
| 29 | export_task | — | 02-user | ⚠️ | DB 设计未定义此表 |
| 30 | admin_user | §2.31 | 13d-admin | ✅ | 字段一致 |
| 31 | audit_log | §2.31 | 13d-admin | ✅ | 字段一致 |
| 32 | system_config | §2.31 | 13d-admin | ✅ | 字段一致 |

### 1.2 偏差统计

| 偏差类型 | 数量 | 严重程度分布 |
|---------|:---:|------|
| 表缺失（切片有、DB 设计无） | 2 | P1×1, P2×1 |
| 重复定义（多切片定义同一表） | 3 | P1×1, P2×2 |
| 主键设计不一致 | 1 | P1×1 |
| 字段类型不一致 | 1 | P1×1 |
| 字段名不一致 | 3 | P1×1, P2×2 |
| 新增字段未回写 DB 设计 | 5 | P2×4, P3×1 |
| 缺失字段（切片少、DB 设计有） | 1 | P1×1 |
| DB 设计内部不一致 | 2 | P2×2 |

---

## 2. P0 — 阻断级偏差

> 无 P0 级偏差。所有 Phase 1 核心表在切片中均有定义，无关键表缺失。

---

## 3. P1 — 高优先级偏差

### P1-1：membership_tier_config 主键设计不一致

| 项 | 内容 |
|---|---|
| **表名** | membership_tier_config |
| **偏差类型** | 主键设计不一致 |
| **DB 设计** | §2.31: `id BIGSERIAL PK` + `tier VARCHAR(20) UNIQUE`；ER 图 §1.2 同 |
| **切片实现** | 10-membership/backend.md L202: `tier: Mapped[str] = mapped_column(String(32), primary_key=True)` — 无 id 列，tier 直接作 PK |
| **影响** | 主键设计差异导致 Alembic 迁移冲突。DB 设计用自增 id + tier 唯一约束，切片用 tier 语义化 PK。FK 引用方式不同（id vs tier 字符串）。此外切片 tier 长度 String(32) vs DB 设计 VARCHAR(20)。 |
| **建议** | 统一为 DB 设计方案（id BIGSERIAL PK + tier UNIQUE），因为 Subscription.tier 是普通 String 非 FK，用 id 做 PK 更规范。或统一为切片方案（tier PK），需更新 DB 设计 §2.31 和 ER 图。 |

### P1-2：refund_record 表 DB 设计未定义

| 项 | 内容 |
|---|---|
| **表名** | refund_record |
| **偏差类型** | 表缺失（切片有、DB 设计无） |
| **DB 设计** | 无此表定义（grep 确认仅 OrderStatus 枚举中有 "refunded" 状态值） |
| **切片实现** | 11-payment/backend.md L505: `class RefundRecord(Base)` — 完整定义含 id, order_id, refund_no, refund_amount_cents, reason, status, operator_id, callback_raw, created_at, updated_at |
| **影响** | 退款是支付模块核心功能，DB 设计缺少表定义将导致迁移脚本和表结构缺失。 |
| **建议** | 将 RefundRecord 表回写至 DB 设计 §2 新增 §2.19b（或 §2.20 之前），补全字段定义和索引。 |

### P1-3：share_record 字段名不一致 + 缺失字段

| 项 | 内容 |
|---|---|
| **表名** | share_record |
| **偏差类型** | 字段名不一致 + 缺失字段 |
| **DB 设计** | §2.9 + §5.2 代码块: `share_token`, `share_scope`, `card_image_url`, `view_count` |
| **切片实现** | 03-video_analysis/backend.md L294-306: `token`（非 share_token）, `share_card_url`（非 card_image_url）；**缺失** `share_scope` 和 `view_count` |
| **影响** | 字段名不一致导致 ORM 映射冲突；缺失 share_scope 无法区分公开/好友分享；缺失 view_count 无法统计分享浏览量。 |
| **建议** | 更新切片 ShareRecord 模型：将 `token` 改为 `share_token`，`share_card_url` 改为 `card_image_url`，补充 `share_scope: Mapped[str] = mapped_column(String(20), default="public")` 和 `view_count: Mapped[int] = mapped_column(Integer, default=0)`。 |

### P1-4：match_statistic stats_data 类型不一致

| 项 | 内容 |
|---|---|
| **表名** | match_statistic |
| **偏差类型** | 字段类型不一致 |
| **DB 设计** | §2.12: `stats_data JSONB`；§5.3 代码块: `stats_data: Mapped[dict] = mapped_column(JSONB)` |
| **切片实现** | 04-scoring/backend.md L380: `stats_data: Mapped[dict] = mapped_column(Text, comment="统计JSON: ...")` |
| **影响** | Text 类型无法使用 JSONB 索引和查询操作符（`->>`, `@>`），降低了统计数据的查询效率。 |
| **建议** | 将切片 `stats_data` 类型从 `Text` 改为 `JSONB`，与 DB 设计对齐。 |

### P1-5：file_record 重复定义

| 项 | 内容 |
|---|---|
| **表名** | file_record |
| **偏差类型** | 重复定义 |
| **定义位置 1** | 03-video_analysis/backend.md L214: `class FileRecord(Base)` — 含 filename, updated_at |
| **定义位置 2** | 13-infrastructure/file_management.md L57: `class FileRecord(Base)` |
| **DB 设计** | §2.4 + §5.2: `original_filename`（非 filename），有 uploaded_at（切片无），无 updated_at |
| **影响** | 多处定义同一模型违反单一归属原则，可能导致 Alembic 迁移冲突。字段名 `filename` vs `original_filename` 不一致。 |
| **建议** | 统一 file_record 的定义归属（建议 03-video_analysis 或 13e-file_management 单一归属），将字段名改为 `original_filename`，补充 `uploaded_at`，与 DB 设计 §2.4 对齐。 |

### P1-6：analysis_report 重复定义且字段简化

| 项 | 内容 |
|---|---|
| **表名** | analysis_report |
| **偏差类型** | 重复定义 + 字段简化 |
| **定义位置 1** | 03-video_analysis/backend.md L257: `class AnalysisReport(Base)` — 完整定义（含 is_llm_generated, is_anonymized, report_images 等） |
| **定义位置 2** | 06-data_dashboard/backend.md L261: 重复定义 — 仅 5 字段（id, task_id, user_id, result_data, report_text, created_at），缺失 annotated_video_url, cover_image_url, report_images, is_llm_generated |
| **DB 设计** | §2.7 + §5.2: 完整字段定义 |
| **影响** | dashboard 切片的简化定义可能导致其他切片引用到不完整的模型。违反单一归属原则。 |
| **建议** | 06-data_dashboard 切片应 import AnalysisReport 而非重复定义。如需只读视图，使用 Pydantic Schema 而非重新定义 Model。 |

---

## 4. P2 — 中优先级偏差

### P2-1：user_profile 表合并进 user 模型

| 项 | 内容 |
|---|---|
| **表名** | user / user_profile |
| **偏差类型** | 表结构设计分歧 |
| **DB 设计** | §2.1 + §2.2 + §5.1: User 和 UserProfile 独立建表，一对一关系 |
| **切片实现** | 02-user/backend.md L188-211: User 类直接包含 kqs_rating, kqs_username, playing_style, self_assessed_level, equipment_config 等 user_profile 字段；新增 scheduled_deletion_at, deletion_reason |
| **影响** | 合并设计简化了查询但违反了 DB 设计的表分离原则。UserProfile 表在切片中不存在。DB 设计 ER 图和迁移脚本与切片不匹配。 |
| **建议** | 在报告中标注此为切片设计决策。如确认合并方案：更新 DB 设计 §2.2 标注"已合并至 user 表"，移除 UserProfile 独立表定义。如确认分离方案：切片恢复 UserProfile 独立模型。 |

### P2-2：match_record 新增 is_detailed + updated_at 字段

| 项 | 内容 |
|---|---|
| **表名** | match_record |
| **偏差类型** | 新增字段未回写 DB 设计 |
| **DB 设计** | §2.13 + §5.4: 无 is_detailed, 无 updated_at |
| **切片实现** | 05-match_data/backend.md L421: `is_detailed: Mapped[bool] = mapped_column(Boolean, default=False)` + L423: `updated_at` |
| **影响** | is_detailed 标记快速录入/详细录入模式，是切片扩展的业务字段。DB 设计未同步。 |
| **建议** | 将 is_detailed 和 updated_at 回写至 DB 设计 §2.13 match_record 表定义。 |

### P2-3：match_record 重复定义且字段简化

| 项 | 内容 |
|---|---|
| **表名** | match_record |
| **偏差类型** | 重复定义 + 字段简化 |
| **定义位置 1** | 05-match_data/backend.md L401: 完整定义（含 match_id, is_detailed, updated_at） |
| **定义位置 2** | 06-data_dashboard/backend.md L272: 简化定义 — 缺失 match_id, is_detailed, updated_at |
| **影响** | 同 P1-6，违反单一归属原则。 |
| **建议** | 06-data_dashboard 应 import MatchRecord 而非重复定义。 |

### P2-4：video_task 新增字段未回写 DB 设计

| 项 | 内容 |
|---|---|
| **表名** | video_task |
| **偏差类型** | 新增字段未回写 |
| **DB 设计** | §2.5 + §5.2: 无 task_uuid, total_steps, step_name, progress, estimated_remaining_seconds |
| **切片实现** | 03-video_analysis/backend.md L237-249: 新增 `task_uuid` (UUID 对外标识), `total_steps`, `step_name`, `progress` (Float), `estimated_remaining_seconds` |
| **影响** | task_uuid 是对外暴露的 UUID 标识（API 层使用），total_steps/step_name/progress 用于实时进度展示。DB 设计未包含这些字段。 |
| **建议** | 将 5 个新字段回写至 DB 设计 §2.5 video_task 表定义。task_uuid 需加 UNIQUE 索引。 |

### P2-5：match 新增字段 + DB 设计内部不一致

| 项 | 内容 |
|---|---|
| **表名** | match |
| **偏差类型** | 新增字段 + DB 设计内部不一致 |
| **DB 设计 §2.10** | 有 score_sequence (JSONB)；无 current_game, is_win, final_score, started_at, abandoned_at, updated_at |
| **DB 设计 §5.3 代码** | 有 current_game, is_win；无 score_sequence, final_score, started_at, abandoned_at, updated_at |
| **切片实现** | 04-scoring/backend.md L321-345: 有 current_game, is_win, final_score, started_at, abandoned_at, updated_at；无 score_sequence（改用 Redis 缓存） |
| **影响** | DB 设计 §2.10 与 §5.3 代码块自身不一致（score_sequence vs current_game/is_win）。切片取两者并集并新增状态机字段。 |
| **建议** | 1) 统一 DB 设计 §2.10 和 §5.3（合并字段或标注差异原因）；2) 将切片新增的 final_score, started_at, abandoned_at, updated_at 回写至 DB 设计。 |

### P2-6：subscription tier 字符串长度不一致

| 项 | 内容 |
|---|---|
| **表名** | subscription |
| **偏差类型** | 字段长度不一致 |
| **DB 设计** | §2.17: `tier VARCHAR(20)`；§5.5: `String(20)` |
| **切片实现** | 10-membership/backend.md L224: `tier: Mapped[str] = mapped_column(String(32))` |
| **影响** | 长度差异可能导致超长 tier 值在 DB 设计约束下被截断。实际使用值（free/member/pro/coach）均在 20 字符内。 |
| **建议** | 统一为 String(32) 或 String(20)，更新 DB 设计或切片。 |

### P2-7：manual_score_detail FK 字段名不一致

| 项 | 内容 |
|---|---|
| **表名** | manual_score_detail |
| **偏差类型** | FK 字段名不一致 |
| **DB 设计** | §5.4 代码块: `match_record_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("match_record.id", ondelete="CASCADE"))` |
| **切片实现** | 05-match_data/backend.md L436: `record_id: Mapped[int] = mapped_column(ForeignKey("match_record.id", ondelete="CASCADE"))` |
| **影响** | FK 列名不一致导致 ORM relationship 配置和查询条件可能出错。 |
| **建议** | 统一为 `match_record_id`（与 DB 设计一致），或统一为 `record_id`（更新 DB 设计）。推荐前者。 |

### P2-8：export_task 表 DB 设计未定义

| 项 | 内容 |
|---|---|
| **表名** | export_task |
| **偏差类型** | 表缺失（切片有、DB 设计无） |
| **DB 设计** | 无此表定义 |
| **切片实现** | 02-user/backend.md L231: `class ExportTask(Base)` — 含 id, user_id, task_id, status, download_url, file_size, expire_at, created_at, completed_at |
| **影响** | 个人数据导出是 PIPL 合规功能，DB 设计缺少表定义。 |
| **建议** | 将 ExportTask 表回写至 DB 设计（新增 §2.x），含字段定义和索引。 |

### P2-9：order 表 DB 设计内部不一致

| 项 | 内容 |
|---|---|
| **表名** | order |
| **偏差类型** | DB 设计内部不一致 |
| **DB 设计 §2.18** | 有 `product_ref_id BIGINT NULL`，无 `subscription_id` |
| **DB 设计 §5.5 代码** | 有 `subscription_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("subscription.id", ondelete="SET NULL"))`，无 `product_ref_id` |
| **切片实现** | 11-payment/backend.md L452-459: 两者都有 — `subscription_id` (FK) + `product_ref_id` (普通 BigInteger) |
| **影响** | DB 设计表定义与代码块使用不同的 FK 策略。切片合并了两者的字段。 |
| **建议** | 统一 DB 设计：保留 subscription_id (FK) 和 product_ref_id (普通列) 两个字段，更新 §2.18 和 §5.5 使其一致。 |

---

## 5. P3 — 低优先级偏差

### P3-1：membership_tier_config 切片新增字段

| 项 | 内容 |
|---|---|
| **表名** | membership_tier_config |
| **偏差类型** | 新增字段（切片自标注） |
| **DB 设计** | §2.31: 无 is_active, created_at, updated_at |
| **切片实现** | 10-membership/backend.md L213-215: 新增 `is_active`, `created_at`, `updated_at`（代码注释明确标注"切片新增（DB 设计 §2.31 无此字段）"） |
| **建议** | 将 3 个字段回写至 DB 设计 §2.31。 |

### P3-2：analysis_report 新增 is_anonymized 字段

| 项 | 内容 |
|---|---|
| **表名** | analysis_report |
| **偏差类型** | 新增字段 |
| **DB 设计** | §2.7 + §5.2: 无 is_anonymized |
| **切片实现** | 03-video_analysis/backend.md L265: `is_anonymized: Mapped[bool] = mapped_column(Boolean, default=False)` — 用户注销后匿名归档标记 |
| **建议** | 将 is_anonymized 回写至 DB 设计 §2.7。 |

### P3-3：score_record DB 设计代码块遗漏字段

| 项 | 内容 |
|---|---|
| **表名** | score_record |
| **偏差类型** | DB 设计内部不一致 |
| **DB 设计 §2.11** | 有 game_number, is_key_point |
| **DB 设计 §5.3 代码块** | 无 game_number, is_key_point |
| **切片实现** | 04-scoring/backend.md L366-367: 有 game_number, is_key_point |
| **建议** | 将 game_number, is_key_point 补入 DB 设计 §5.3 代码块，与 §2.11 表定义对齐。 |

---

## 6. 重复定义汇总

| # | 表名 | 定义位置 1 | 定义位置 2 | 差异 | 优先级 |
|---|------|---------|---------|------|:---:|
| 1 | file_record | 03-video_analysis L214 | 13e-file_management L57 | 字段名 filename vs original_filename | P1 |
| 2 | analysis_report | 03-video_analysis L257（完整） | 06-data_dashboard L261（简化） | dashboard 版缺失 6 个字段 | P1 |
| 3 | match_record | 05-match_data L401（完整） | 06-data_dashboard L272（简化） | dashboard 版缺失 match_id, is_detailed, updated_at | P2 |

> **根因分析**：06-data_dashboard 切片为独立查询需要重新定义了 AnalysisReport 和 MatchRecord 的简化版本，违反了 Model 单一归属原则。应改为 import 已有 Model 或使用 Pydantic Schema 做只读投影。

---

## 7. 缺失表汇总

| # | 表名 | 切片定义位置 | DB 设计状态 | 优先级 | 说明 |
|---|------|---------|---------|:---:|------|
| 1 | refund_record | 11-payment/backend.md L505 | 未定义 | P1 | 退款记录，支付核心功能 |
| 2 | export_task | 02-user/backend.md L231 | 未定义 | P2 | 数据导出，PIPL 合规 |

---

## 8. 建议回写 DB 设计的字段清单

以下字段在切片中已实现但 DB 设计未包含，建议回写：

| # | 表名 | 字段名 | 类型 | 切片位置 | DB 设计章节 |
|---|------|--------|------|---------|---------|
| 1 | video_task | task_uuid | String(36) UNIQUE | 03-video_analysis L238 | §2.5 |
| 2 | video_task | total_steps | Integer default=10 | 03-video_analysis L245 | §2.5 |
| 3 | video_task | step_name | String(128) nullable | 03-video_analysis L246 | §2.5 |
| 4 | video_task | progress | Float default=0.0 | 03-video_analysis L247 | §2.5 |
| 5 | video_task | estimated_remaining_seconds | Integer nullable | 03-video_analysis L249 | §2.5 |
| 6 | match_record | is_detailed | Boolean default=False | 05-match_data L421 | §2.13 |
| 7 | match_record | updated_at | TIMESTAMPTZ | 05-match_data L423 | §2.13 |
| 8 | match | final_score | VARCHAR(20) nullable | 04-scoring L340 | §2.10 |
| 9 | match | started_at | TIMESTAMPTZ nullable | 04-scoring L342 | §2.10 |
| 10 | match | abandoned_at | TIMESTAMPTZ nullable | 04-scoring L344 | §2.10 |
| 11 | match | updated_at | TIMESTAMPTZ | 04-scoring L345 | §2.10 |
| 12 | analysis_report | is_anonymized | Boolean default=False | 03-video_analysis L265 | §2.7 |
| 13 | membership_tier_config | is_active | Boolean default=True | 10-membership L213 | §2.31 |
| 14 | membership_tier_config | created_at | TIMESTAMPTZ | 10-membership L214 | §2.31 |
| 15 | membership_tier_config | updated_at | TIMESTAMPTZ | 10-membership L215 | §2.31 |

---

## 9. 已修复项（Fixed Items）

以下偏差此前存在，经 DB 设计 v1.3 更新后已同步：

| # | 表名 | 原偏差 | 修复状态 | 修复位置 |
|---|------|--------|---------|---------|
| 1 | feedback_record | DB 设计缺少 status 字段（数据飞轮审核入口） | ✅ 已修复 | DB 设计 v1.3 §2.8 + §5.6 已补充 status VARCHAR(20) DEFAULT 'pending'；切片 §03-video_analysis L287 已含 |
| 2 | share_record | DB 设计 §5.2 代码块缺少 ShareRecord | ✅ 已修复 | DB 设计 v1.3 §5.2 已补充 ShareRecord 代码块（含 share_token, share_scope, card_image_url, view_count） |
| 3 | badge_definition | PK 设计不一致（DB 设计 BIGSERIAL id vs 切片 VARCHAR(64)） | ✅ 已修复 | DB 设计 v1.3 §3.1.4 已改为 VARCHAR(64) PK，与切片 09-gamification L218 一致 |
| 4 | badge_progress | DB 设计缺少此表 | ✅ 已修复 | DB 设计 v1.3 §3.1.6 已补充 badge_progress 表定义，与切片 09-gamification L246 一致 |
| 5 | user_badge | DB 设计缺少此表 | ✅ 已修复 | DB 设计 v1.3 §3.1.5 已补充 user_badge 表定义，与切片 09-gamification L232 一致 |

---

## 10. 审查方法说明

### 10.1 审查范围

- **基准文档**：数据库详细设计 v1.3（`docs/04详细设计/04-数据库详细设计.md`）§1-§5
- **对比对象**：垂直切片后端设计 01-12 + 13a-13e（`docs/06垂直模块前后端切片设计/*/backend.md` 和 `13-infrastructure/*.md`）中所有 `class XxxModel(Base)` 定义
- **辅助参考**：系统架构设计 v2.4 §9 ER 图

### 10.2 审查维度

每个表按以下维度逐一比对：

1. **表归属**：每个表是否在唯一切片中定义，是否存在重复定义
2. **字段名**：字段名称是否一致（含 FK 列名）
3. **字段类型**：String/Text/JSONB/Integer 等类型是否一致
4. **主键设计**：PK 列和策略是否一致（自增 id vs 语义化 PK）
5. **外键约束**：FK 引用和 ondelete 策略是否一致
6. **新增/缺失字段**：切片有而 DB 设计无、或 DB 设计有而切片无的字段
7. **表存在性**：切片定义了 DB 设计中不存在的表，或反之

### 10.3 优先级定义

- **P0（阻断级）**：核心表缺失或主键冲突导致迁移无法执行
- **P1（高优先级）**：字段名/类型不一致或表缺失，影响 ORM 映射和查询
- **P2（中优先级）**：新增字段未回写或重复定义，不影响核心功能但需文档对齐
- **P3（低优先级）**：DB 设计内部不一致或切片自标注的扩展字段

---

## 11. 结论

DB 设计与切片后端整体一致性中等，32 个表中 14 个完全一致，18 个存在不同程度的偏差。

主要问题集中在：

1. **重复定义**（3 个表）：file_record、analysis_report、match_record 在多个切片中重复定义，06-data_dashboard 是主要重复源。违反 Model 单一归属原则，应改为 import 或使用 Schema 投影。

2. **表缺失**（2 个表）：refund_record（P1）和 export_task（P2）在切片中完整定义但 DB 设计未收录。需回写。

3. **字段未回写**（15 个字段）：切片扩展的业务字段（task_uuid、is_detailed、final_score、started_at、abandoned_at 等）未同步至 DB 设计表定义。

4. **主键设计分歧**（1 个表）：membership_tier_config 的 PK 设计在 DB 设计（id BIGSERIAL）和切片（tier PK）之间根本不同，需统一决策。

5. **DB 设计内部不一致**（3 处）：§2.x 表定义与 §5.x 代码块之间存在字段差异（order 的 subscription_id vs product_ref_id、match 的 score_sequence vs current_game/is_win、score_record 的 game_number/is_key_point 遗漏）。

所有偏差均不影响 Phase 1 核心功能可用性，但需在 Alembic 迁移执行前完成 DB 设计文档对齐工作。

---

> **审查声明**：本报告为只读审查，未修改任何源文件。所有发现基于审查时点（2026-10-12）的文档版本。如需修复，请按"建议回写 DB 设计的字段清单"逐项处理。
