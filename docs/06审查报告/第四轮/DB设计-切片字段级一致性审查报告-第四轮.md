# DB 设计 — 切片字段级一致性审查报告（第四轮）

> **审查日期**：2026-10-13
> **审查范围**：数据库详细设计 v1.4（§2 Phase 1 表定义 + §3.1 Phase 2 表定义 + §5 SQLAlchemy 代码块）vs 垂直切片后端设计 01-12 + 13-infrastructure/admin（backend.md 中 Model 定义）
> **审查维度**：表归属、字段名、字段类型、主键设计、外键约束、nullable、default、PK/FK/UK/索引、枚举值、JSONB 策略
> **审查类型**：只读审查（未修改任何源文件）
> **基线**：第三轮审查报告（基于 DB v1.3），本次验证第三轮修复落地情况并发现新问题

---

## 1. 总览

### 1.1 第三轮修复验证

| # | 修复项 | 第三轮状态 | 第四轮验证 | 结论 |
|---|--------|:---:|:---:|:---:|
| R3-1 | VideoTask PK 改为 BigInteger | P1 | §5.2 已用 BigInteger PK | 已落地 |
| R3-2 | badge_definition PK 改为 VARCHAR(64) | P1 | §3.1.4 + 切片09 均用 String(64) PK | 已落地 |
| R3-3 | FeedbackRecord 补充 status 字段 | P1 | §2.8 + §5.6 + 切片03 均有 status | 已落地 |
| R3-4 | match_statistic.stats_data 改为 JSONB | P1 | §5.3 + 切片04 均用 JSONB | 已落地 |
| R3-5 | subscription.tier 改为 VARCHAR(32) | P1 | §2.17 + §5.5 + 切片10 均为 String(32) | 已落地 |
| R3-6 | training_template 表新增字段 | P1 | §2.27 已含 category/difficulty/description/template_config/updated_at | 已落地 |
| R3-7 | CheckInRecord.bonus_points 补充 | P2 | §2.16 + 切片09 均有 bonus_points | 已落地 |
| R3-8 | share_record 字段名对齐 | P2 | 切片03 用 share_token/card_image_url/share_scope/view_count | 已落地 |
| R3-9 | match 新增 final_score/started_at/abandoned_at/updated_at | P2 | §2.10 + §5.3 + 切片04 均有 | 已落地 |
| R3-10 | match_record 新增 is_detailed/updated_at | P2 | §2.13 + §5.4 + 切片05 均有 | 已落地 |
| R3-11 | manual_score_detail FK 改为 match_record_id | P2 | §5.4 + 切片05 均用 match_record_id | 已落地 |
| R3-12 | refund_record 表定义 | P1 | §2.19b 已定义 | 已落地 |
| R3-13 | export_task 表定义 | P2 | §3.1.15 已定义 | 已落地 |
| R3-14 | membership_tier_config PK 改为 id + tier UNIQUE | P1 | §2.31 用 id PK + tier UNIQUE；切片10 同 | 已落地 |
| R3-15 | 06-dashboard 不再重复定义 Model | P1 | 切片06 改为引用注释 | 已落地 |

**结论**：第三轮全部 15 项修复已在 DB v1.4 中落地。

### 1.2 第四轮偏差统计

| 偏差类型 | 数量 | 严重程度分布 |
|---------|:---:|------|
| DB §5 代码块内部与 §2 不一致 | 10 | P1x10 |
| JSON vs JSONB 类型不一致 | 1 | P1x1 |
| 枚举值不一致 | 2 | P1x1, P2x1 |
| 字段长度不一致 | 5 | P1x2, P2x3 |
| 字段 nullability 不一致 | 3 | P1x2, P2x1 |
| 切片新增字段未回写 DB §2 | 2 | P2x2 |
| UniqueConstraint 缺失 | 1 | P2x1 |
| DB §5 代码块缺字段（vs §2 + 切片） | 3 | P1x2, P3x1 |
| 切片 stale 注释 | 1 | P3x1 |
| admin.md 字段差异 | 1 | P2x1 |

---

## 2. P0 — 阻断级偏差

> 无 P0 级偏差。所有 Phase 1 核心表在切片和 DB 设计中均有定义，无关键表缺失。

---

## 3. P1 — 高优先级偏差

### P1-1：analysis_report 使用 JSON 而非 JSONB

| 项 | 内容 |
|---|---|
| **表名** | analysis_report |
| **偏差类型** | JSON vs JSONB 类型不一致 |
| **DB 设计** | §2.7 L552-556: result_data JSONB, report_text JSONB, report_images JSONB；§5.2 L2323-2327: 同为 JSONB |
| **切片实现** | 03-video_analysis/backend.md L268-272: result_data JSON, report_text JSON, report_images JSON |
| **影响** | JSON 不支持 GIN 索引、@>/? 查询操作符，DB 设计 §6.2 规划了 GIN(report_text) 全文搜索索引和 JSONB 查询索引，使用 JSON 将导致索引和查询功能不可用 |
| **修复方案** | 切片 03 将 JSON 改为 from sqlalchemy.dialects.postgresql import JSONB 并使用 JSONB 类型，与 DB §2.7 和 §5.2 对齐 |

### P1-2：DB §5.3 Match.format String(10) vs §2.10 VARCHAR(20)

| 项 | 内容 |
|---|---|
| **表名** | match |
| **偏差类型** | DB 设计内部 §2 vs §5 字段长度不一致 |
| **DB §2.10** | L607: format VARCHAR(20) — enum: bo3/bo5/bo7/custom |
| **DB §5.3** | L2375: format String(10) |
| **切片 04** | L330: format String(20) default=bo5 — 与 §2.10 一致 |
| **修复方案** | 将 DB §5.3 L2375 的 String(10) 改为 String(20) |

### P1-3：DB §5.3 ScoreRecord.score_method String(20) vs §2.11 VARCHAR(32)

| 项 | 内容 |
|---|---|
| **表名** | score_record |
| **偏差类型** | DB 设计内部 §2 vs §5 字段长度不一致 |
| **DB §2.11** | L634: score_method VARCHAR(32) NULL |
| **DB §5.3** | L2407: score_method String(20) |
| **切片 04** | L365: score_method String(32) — 与 §2.11 一致 |
| **修复方案** | 将 DB §5.3 L2407 的 String(20) 改为 String(32) |

### P1-4：DB §5.4 MatchRecord.format String(10) vs §2.13 VARCHAR(20)

| 项 | 内容 |
|---|---|
| **表名** | match_record |
| **偏差类型** | DB 设计内部 §2 vs §5 字段长度不一致 |
| **DB §2.13** | L664: format VARCHAR(20) |
| **DB §5.4** | L2455: format String(10) |
| **切片 05** | L412: format String(10) — 与 §5.4 一致但与 §2.13 不一致 |
| **修复方案** | 将 DB §5.4 L2455 和切片 05 L412 的 String(10) 改为 String(20) |

### P1-5：DB §5.4 ManualScoreDetail.score_method String(20) vs §2.14 VARCHAR(32)

| 项 | 内容 |
|---|---|
| **表名** | manual_score_detail |
| **偏差类型** | DB 设计内部 §2 vs §5 字段长度不一致 |
| **DB §2.14** | L681: score_method VARCHAR(32) NULL |
| **DB §5.4** | L2477: score_method String(20) |
| **切片 05** | L439: score_method String(32) — 与 §2.14 一致 |
| **修复方案** | 将 DB §5.4 L2477 的 String(20) 改为 String(32) |

### P1-6：DB §5.5 Subscription.status 枚举 grace vs §2.17 grace_period

| 项 | 内容 |
|---|---|
| **表名** | subscription |
| **偏差类型** | DB 设计内部 §2 vs §5 枚举值不一致 |
| **DB §2.17** | L719: status enum active/expiring_soon/expired/grace_period/closed |
| **DB §5.5** | L2507: status 注释 active/expiring_soon/expired/grace/closed |
| **切片 10** | L226-229: status 注释 active/expiring_soon/expired/grace_period/closed — 与 §2.17 一致 |
| **修复方案** | 将 DB §5.5 L2507 的注释 grace 改为 grace_period |

### P1-7：DB §5.5 Order.order_no/product_type 与 §2.18 不一致

| 项 | 内容 |
|---|---|
| **表名** | order |
| **偏差类型** | DB 设计内部 §2 vs §5 字段长度不一致 + 字段缺失 |
| **DB §2.18** | L733: order_no VARCHAR(64)；L736: product_type VARCHAR(32)；L741: extra_data JSONB NULL |
| **DB §5.5** | L2529: order_no String(32)；L2530: product_type String(20)；无 extra_data 字段 |
| **切片 11** | L455: order_no String(64)；L456: product_type String(32)；L465: extra_data JSONB nullable=True — 与 §2.18 一致 |
| **修复方案** | 将 §5.5 L2529 改 String(64)、L2530 改 String(32)、新增 extra_data JSONB nullable |

### P1-8：DB §5.5 PaymentRecord.transaction_id 缺少 UNIQUE 约束

| 项 | 内容 |
|---|---|
| **表名** | payment_record |
| **DB §2.19** | L753: transaction_id VARCHAR(64) UNIQUE |
| **DB §5.5** | L2550: transaction_id String(64) — 无 unique=True |
| **切片 11** | L489: transaction_id String(64) unique=True — 与 §2.19 一致 |
| **修复方案** | 在 DB §5.5 L2550 添加 unique=True |

### P1-9：DB §5.5 PaymentRecord.callback_raw nullability 与 §2.19 不一致

| 项 | 内容 |
|---|---|
| **表名** | payment_record |
| **DB §2.19** | L757: callback_raw JSONB NULL |
| **DB §5.5** | L2553: callback_raw JSONB — Mapped[dict] 非 Mapped[dict | None]，即 NOT NULL |
| **切片 11** | L494: callback_raw JSONB nullable=True — 与 §2.19 一致 |
| **修复方案** | 将 §5.5 L2553 改为 Mapped[dict | None] 和 nullable=True |

### P1-10：DB §5.6 NotificationRecord.content nullability 与 §2.20 不一致

| 项 | 内容 |
|---|---|
| **表名** | notification_record |
| **DB §2.20** | L789: content TEXT NULL |
| **DB §5.6** | L2636: content Text — Mapped[str] 非 Mapped[str | None]，即 NOT NULL |
| **切片 12** | L250: content Text nullable=True — 与 §2.20 一致 |
| **修复方案** | 将 §5.6 L2636 改为 Mapped[str | None] 和 nullable=True |

### P1-11：DB §5.2 VideoTask 缺少 5 个字段

| 项 | 内容 |
|---|---|
| **表名** | video_task |
| **DB §2.5** | 定义了 task_uuid VARCHAR(64) UNIQUE, total_steps INT DEFAULT 10, step_name VARCHAR(32), progress INT DEFAULT 0, estimated_remaining_seconds INT |
| **DB §5.2** | L2291-2305 VideoTask 类缺少上述 5 个字段 |
| **切片 03** | L239-250 全部包含这 5 个字段 |
| **修复方案** | 在 DB §5.2 VideoTask 类中补入这 5 个字段定义 |

### P1-12：DB §5.2 FileRecord 缺少 updated_at

| 项 | 内容 |
|---|---|
| **表名** | file_record |
| **DB §2.4** | L498: updated_at TIMESTAMPTZ — 标注 P2 补充：切片已定义 |
| **DB §5.2** | L2274-2288 FileRecord 类无 updated_at 字段 |
| **切片 03** | L228: updated_at DateTime(timezone=True) |
| **修复方案** | 在 DB §5.2 FileRecord 类中补入 updated_at 字段 |

### P1-13：DB §5.3 Match 缺少 score_sequence

| 项 | 内容 |
|---|---|
| **表名** | match |
| **DB §2.10** | L620: score_sequence JSONB NULL — Redis 镜像 |
| **DB §5.3** | L2367-2396 Match 类无 score_sequence 字段 |
| **切片 04** | L322-346 Match 类无 score_sequence 字段 |
| **修复方案** | 在 §5.3 和切片 04 补入 score_sequence JSONB nullable=True；或在 §2.10 标注为仅 Redis 缓存不持久化 |

### P1-14：share_record.share_scope 枚举不一致

| 项 | 内容 |
|---|---|
| **表名** | share_record |
| **DB §2.9** | L593: share_scope enum public/friend |
| **DB §5.2** | L2345: share_scope 注释 public/friend — 与 §2.9 一致 |
| **切片 03** | L309: share_scope 注释 public/private |
| **修复方案** | 将切片 03 L309 的注释 public/private 改为 public/friend |

---

## 4. P2 — 中优先级偏差

### P2-1：match.format 枚举包含 bo1 但 DB §2.10 无

| 项 | 内容 |
|---|---|
| **DB §2.10** | L607: format enum bo3/bo5/bo7/custom（无 bo1） |
| **切片 04** | L330: format comment bo1/bo3/bo5/bo7/custom（含 bo1） |
| **修复方案** | 在 DB §2.10 的 format 枚举中添加 bo1，或从切片 04 注释中移除 bo1 |

### P2-2：match_record.opponent_name nullability 不一致

| 项 | 内容 |
|---|---|
| **DB §2.13** | L659: opponent_name VARCHAR(64) NULL |
| **DB §5.4** | L2450: opponent_name nullable=True |
| **切片 05** | L407: opponent_name Mapped[str]（NOT NULL） |
| **修复方案** | 将切片 05 L407 改为 Mapped[str | None] 和 nullable=True |

### P2-3：match_record.format 长度不一致（切片 05 vs §2.13）

| 项 | 内容 |
|---|---|
| **DB §2.13** | L664: format VARCHAR(20) |
| **切片 05** | L412: format String(10) |
| **修复方案** | 将切片 05 L412 的 String(10) 改为 String(20)（与 P1-4 一并修复） |

### P2-4：user_points.bonus_points — 切片新增字段未回写 DB §2.15

| 项 | 内容 |
|---|---|
| **DB §2.15** | L684-694: 无 bonus_points 字段 |
| **切片 09** | L190: bonus_points Integer default=0 |
| **修复方案** | 在 DB §2.15 user_points 表中添加 bonus_points INT DEFAULT 0 |

### P2-5：checkin_record.checkin_type 长度不一致

| 项 | 内容 |
|---|---|
| **DB §2.16** | L703: checkin_type VARCHAR(16) |
| **切片 09** | L203: checkin_type String(20) |
| **修复方案** | 将 DB §2.16 L703 的 VARCHAR(16) 改为 VARCHAR(20) |

### P2-6：subscription.cancelled_at — 切片新增字段未回写 DB §2.17

| 项 | 内容 |
|---|---|
| **DB §2.17** | L710-723: 无 cancelled_at 字段 |
| **DB §5.5** | L2500-2518: 无 cancelled_at 字段 |
| **切片 10** | L234: cancelled_at DateTime nullable=True |
| **修复方案** | 在 DB §2.17 和 §5.5 Subscription 表中添加 cancelled_at TIMESTAMPTZ NULL |

### P2-7：membership_tier_config.tier 长度不一致

| 项 | 内容 |
|---|---|
| **DB §2.31** | L1016: tier VARCHAR(20) UNIQUE |
| **切片 10** | L207: tier String(32) unique=True |
| **修复方案** | 将 DB §2.31 L1016 的 VARCHAR(20) 改为 VARCHAR(32) |

### P2-8：membership_tier_config.name 长度不一致

| 项 | 内容 |
|---|---|
| **DB §2.31** | L1017: name VARCHAR(32) |
| **切片 10** | L208: name String(64) |
| **修复方案** | 将 DB §2.31 L1017 的 VARCHAR(32) 改为 VARCHAR(64) |

### P2-9：feedback_record 缺少 (report_id, user_id) UniqueConstraint

| 项 | 内容 |
|---|---|
| **DB §2.8** | L579: 约束 (report_id, user_id) UNIQUE |
| **DB §5.6** | L2612-2625: 无 UniqueConstraint |
| **切片 03** | L280-291: 无 UniqueConstraint |
| **修复方案** | 在 §5.6 和切片 03 的 FeedbackRecord 类中添加 UniqueConstraint(report_id, user_id) |

### P2-10：admin.md AuditLog 字段与 DB §2.31 不一致

| 项 | 内容 |
|---|---|
| **DB §2.31** | L989-999: 字段 id, admin_id (NOT NULL), action, target_type, target_id, changes, created_at |
| **切片 admin.md** | 比 DB 多 user_id, detail, ip_address 三字段；admin_id nullable=True |
| **修复方案** | 在 DB §2.31 添加 user_id/detail/ip_address 字段；将切片 admin_id 改为 nullable=False |

---

## 5. P3 — 低优先级偏差

### P3-1：file_record.status 枚举缺少 abandoned

| 项 | 内容 |
|---|---|
| **DB §2.4** | L493: status enum uploading/uploaded/abandoned/deleted |
| **切片 03** | L224: status comment uploading/uploaded/deleted（缺 abandoned） |
| **修复方案** | 在切片 03 L224 的注释中补充 abandoned 状态 |

### P3-2：切片 10 MembershipTier stale 注释

| 项 | 内容 |
|---|---|
| **切片 10** | L214-216: is_active/created_at/updated_at 注释为 切片新增（DB 设计 §2.31 无此字段） |
| **DB §2.31** | L1023-1025: 这三个字段已定义，注释 P3 注释修正：DB 设计已定义 |
| **修复方案** | 更新切片 10 L214-216 的注释，移除 切片新增 标注 |

### P3-3：DB §5.5 Subscription 缺少 payment_method 和额外索引

| 项 | 内容 |
|---|---|
| **DB §2.17** | L720: payment_method VARCHAR(20) NULL |
| **DB §5.5** | L2500-2518: 无 payment_method 字段；仅有 idx_sub_status_expire |
| **切片 10** | L233: payment_method String(20) nullable=True；额外有 ix_subscription_user_status 和 ix_subscription_expire_at |
| **修复方案** | 在 DB §5.5 Subscription 类中补入 payment_method 字段和 (user_id, status) 索引 |

### P3-4：VideoTask.task_uuid 长度 36 vs 64

| 项 | 内容 |
|---|---|
| **DB §2.5** | L515: task_uuid VARCHAR(64) UNIQUE |
| **切片 03** | L239: task_uuid String(36) unique=True |
| **修复方案** | 将切片 03 L239 的 String(36) 改为 String(64) 以与 §2.5 对齐 |

---

## 6. 已确认一致的关键表（无偏差）

| 表名 | DB 章节 | 切片归属 | 备注 |
|------|---------|---------|------|
| progress_snapshot | §2.21 + §5.6 | 08-progress_analysis | 字段、类型、FK、索引全部一致 |
| technique_trend | §2.22 + §5.6 | 08-progress_analysis | 含 UniqueConstraint(user_id, metric_name) |
| training_plan | §2.28 | 07-training_advice | 字段一致 |
| plan_adjustment | §2.23 | 07-training_advice | 字段一致 |
| badge_definition | §3.1.4 | 09-gamification | PK VARCHAR(64) 一致 |
| user_badge | §3.1.5 | 09-gamification | UniqueConstraint 一致 |
| badge_progress | §3.1.6 | 09-gamification | 字段一致 |
| refund_record | §2.19b | 11-payment | 第三轮新增，全部一致 |
| match_statistic | §2.12 + §5.3 | 04-scoring | stats_data JSONB 一致 |
| admin_user | §2.31 | 13-infrastructure/admin | 字段一致 |
| system_config | §2.31 | 13-infrastructure/admin | 字段一致 |

---

## 7. 修复优先级建议

### 立即修复（P1，共 14 项）

1. P1-1：切片 03 analysis_report 的 JSON 改为 JSONB
2. P1-2 至 P1-5：DB §5.3/§5.4 中 4 处 String 长度与 §2 不一致
3. P1-6：DB §5.5 Subscription.status 枚举 grace 改为 grace_period
4. P1-7 至 P1-10：DB §5.5/§5.6 中 4 处字段缺失/约束/nullability 不一致
5. P1-11 至 P1-13：DB §5.2/§5.3 中 3 处缺字段
6. P1-14：切片 03 share_record.share_scope 枚举 private 改为 friend

### 尽快修复（P2，共 10 项）

1. P2-1 至 P2-3：match/format 枚举和长度对齐
2. P2-4 至 P2-6：切片新增字段回写 DB §2
3. P2-7 至 P2-8：membership_tier_config 长度对齐
4. P2-9：feedback_record 补 UniqueConstraint
5. P2-10：admin.md AuditLog 字段对齐

### 后续修复（P3，共 4 项）

1. P3-1：file_record.status 枚举补 abandoned
2. P3-2：切片 10 stale 注释更新
3. P3-3：DB §5.5 Subscription 补字段和索引
4. P3-4：VideoTask.task_uuid 长度对齐

---

## 8. 附录：逐表一致性矩阵

| # | 表名 | DB §2 | DB §5 | 切片 | 一致性 | 关键偏差 |
|---|------|:---:|:---:|------|:---:|------|
| 01 | user | §2.1 | §5.1 | 01-auth, 02-user | OK | 字段一致 |
| 02 | user_profile | §2.2 | §5.1 | 02-user | OK | 字段一致（切片合并进 User） |
| 03 | rating_history | §2.3 | — | 02-user | OK | 字段一致 |
| 04 | file_record | §2.4 | §5.2 | 03-video_analysis | WARN | §5.2 缺 updated_at（P1-12）；切片 status 缺 abandoned（P3-1） |
| 05 | video_task | §2.5 | §5.2 | 03-video_analysis | FAIL | §5.2 缺 5 字段（P1-11）；task_uuid 长度 36 vs 64（P3-4） |
| 06 | pipeline_step | §2.6 | — | 13a-ai_pipeline | OK | 字段一致 |
| 07 | analysis_report | §2.7 | §5.2 | 03-video_analysis | FAIL | 切片用 JSON 非 JSONB（P1-1） |
| 08 | feedback_record | §2.8 | §5.6 | 03-video_analysis | WARN | 缺 UniqueConstraint（P2-9） |
| 09 | share_record | §2.9 | §5.2 | 03-video_analysis | WARN | share_scope 枚举不一致（P1-14） |
| 10 | match | §2.10 | §5.3 | 04-scoring | FAIL | §5.3 format String(10)（P1-2）；缺 score_sequence（P1-13）；bo1 枚举（P2-1） |
| 11 | score_record | §2.11 | §5.3 | 04-scoring | WARN | §5.3 score_method String(20)（P1-3） |
| 12 | match_statistic | §2.12 | §5.3 | 04-scoring | OK | 字段一致 |
| 13 | match_record | §2.13 | §5.4 | 05-match_data | FAIL | §5.4 format String(10)（P1-4）；切片 opponent_name NOT NULL（P2-2）；切片 format String(10)（P2-3） |
| 14 | manual_score_detail | §2.14 | §5.4 | 05-match_data | WARN | §5.4 score_method String(20)（P1-5） |
| 15 | user_points | §2.15 | — | 09-gamification | WARN | 切片有 bonus_points 未回写（P2-4） |
| 16 | checkin_record | §2.16 | — | 09-gamification | WARN | checkin_type 长度 20 vs 16（P2-5） |
| 17 | subscription | §2.17 | §5.5 | 10-membership | FAIL | §5.5 枚举 grace（P1-6）；切片有 cancelled_at 未回写（P2-6）；§5.5 缺 payment_method（P3-3） |
| 18 | order | §2.18 | §5.5 | 11-payment | FAIL | §5.5 order_no String(32)（P1-7）；product_type String(20)；缺 extra_data |
| 19 | payment_record | §2.19 | §5.5 | 11-payment | FAIL | §5.5 缺 UNIQUE（P1-8）；callback_raw nullability（P1-9） |
| 20 | refund_record | §2.19b | — | 11-payment | OK | 字段一致 |
| 21 | notification_record | §2.20 | §5.6 | 12-notification | WARN | §5.6 content NOT NULL（P1-10） |
| 22 | progress_snapshot | §2.21 | §5.6 | 08-progress_analysis | OK | 字段一致 |
| 23 | technique_trend | §2.22 | §5.6 | 08-progress_analysis | OK | 字段一致 |
| 24 | plan_adjustment | §2.23 | — | 07-training_advice | OK | 字段一致 |
| 25 | training_plan | §2.28 | — | 07-training_advice | OK | 字段一致 |
| 26 | badge_definition | §3.1.4 | — | 09-gamification | OK | PK VARCHAR(64) 一致 |
| 27 | user_badge | §3.1.5 | — | 09-gamification | OK | 字段一致 |
| 28 | badge_progress | §3.1.6 | — | 09-gamification | OK | 字段一致 |
| 29 | membership_tier_config | §2.31 | — | 10-membership | WARN | tier 20 转 32（P2-7）；name 32 转 64（P2-8）；stale 注释（P3-2） |
| 30 | admin_user | §2.31 | — | 13-infrastructure/admin | OK | 字段一致 |
| 31 | audit_log | §2.31 | — | 13-infrastructure/admin | WARN | 切片多 user_id/detail/ip_address；admin_id nullable（P2-10） |
| 32 | system_config | §2.31 | — | 13-infrastructure/admin | OK | 字段一致 |

---

> **审查总结**：DB v1.4 已落地第三轮全部 15 项修复。第四轮发现 28 项新偏差（P1x14, P2x10, P3x4），主要集中在 DB §5 SQLAlchemy 代码块与 §2 表定义的内部不一致（10 项 P1），以及切片与 §2 的类型/枚举/约束差异。建议优先修复 P1 中的 DB §5 代码块问题，因其直接影响 Alembic 迁移生成的 DDL 正确性。
