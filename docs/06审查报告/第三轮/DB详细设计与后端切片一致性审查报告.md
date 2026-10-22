# 数据库详细设计与后端切片一致性审查报告

> **审查日期**：2026-10-13
> **DB设计基准**：04-数据库详细设计.md v1.4 (2026-10-12)
> **切片基准**：06-垂直模块前后端切片设计/01-auth ~ 12-notification（共12个模块的 backend.md）
> **审查范围**：Phase 1 全部表定义 + 切片实际实现的 Phase 2 表

---

## 1. 总览统计

| 指标 | 数值 |
|------|------|
| DB设计 Phase 1 表数 | 30（§2.1–2.31，含基础设施表） |
| DB设计 Phase 2 表数 | 9（§3.1.1–3.1.16） |
| 切片 Model 类总数 | 32（User 在 01-auth 和 02-user 各定义一次） |
| 切片覆盖表数 | 27（含3个Phase 2提前实现表） |
| 完全一致表数 | 4（notification_record、progress_snapshot、technique_trend、plan_adjustment） |
| 不一致项总计 | **48** |
| ─ P0（阻断级） | 0 |
| ─ P1（严重：数据完整性风险） | **6** |
| ─ P2（重要：应修复） | **29** |
| ─ P3（轻微：文档/约束细节） | **13** |

### 级别定义

| 级别 | 含义 |
|------|------|
| **P0** | 阻断级：表名冲突或核心字段缺失，阻断开发 |
| **P1** | 严重级：类型降级可能导致数据溢出/截断，或约束缺失导致数据完整性风险 |
| **P2** | 重要级：长度/默认值/nullable 不匹配，FK 缺少 ondelete，索引缺失，Phase 归属不符 |
| **P3** | 轻微级：注释错误、额外字段/约束（语义正确）、索引命名差异 |

---

## 2. 不一致详情表

### P1 — 严重级（6项）

| # | 表名 | 字段/约束 | DB设计定义 | 切片定义 | 来源切片 | 问题描述 |
|---|------|----------|-----------|---------|---------|---------|
| 1 | order | order_no | VARCHAR(64), UNIQUE | String(32), unique=True | 11-payment L455 | 长度截断：DB设计64字符，切片仅32。长订单号可能被截断 |
| 2 | file_record | file_size | BIGINT | Integer | 03-video_analysis L222 | 类型降级：BIGINT→Integer，Integer上限~2.1GB，大文件可能溢出 |
| 3 | file_record | actual_size | BIGINT | Integer | 03-video_analysis L226 | 类型降级：同file_size，BIGINT→Integer |
| 4 | refund_record | status (默认值) | DEFAULT 'pending' | default="processing" | 11-payment L515 | 默认值不一致：DB设计初始状态为pending，切片为processing，可能中断状态机流程 |
| 5 | payment_record | transaction_id (UNIQUE) | VARCHAR(64), UNIQUE | String(64), 无unique=True | 11-payment L489 | 缺失唯一约束：DB设计要求UNIQUE，切片未实现，允许重复交易号 |
| 6 | training_template | （整表） | ER图§1.2定义实体，§2.28 FK引用，但无表定义 | 切片07引用FK("training_template.id")，亦无定义 | 07-training_advice | FK目标表未定义：training_plan.template_id引用training_template.id，但DB设计和所有切片均未定义此表 |

### P2 — 重要级（29项）

#### 2.1 字段类型/长度不匹配（10项）

| # | 表名 | 字段 | DB设计 | 切片 | 来源 | 描述 |
|---|------|------|--------|------|------|------|
| 7 | video_task | task_uuid | VARCHAR(64) | String(36) | 03 L239 | UUID为36字符，功能可用但不匹配DB规格 |
| 8 | score_record | technique_action | VARCHAR(32) | String(30) | 04 L366, 05 L440 | 长度缩短2字符，长动作名可能截断 |
| 9 | score_record | score_method | VARCHAR(32) | String(20) | 04 L365, 05 L439 | 长度缩短12字符，长方法名可能截断 |
| 10 | manual_score_detail | technique_action | VARCHAR(32) | String(30) | 05 L440 | 同#8 |
| 11 | manual_score_detail | score_method | VARCHAR(32) | String(20) | 05 L439 | 同#9 |
| 12 | video_task | step_name | VARCHAR(32) | String(128) | 03 L247 | 长度扩展4倍，不匹配DB设计 |
| 13 | video_task | progress | INT | Float | 03 L248 | 类型不匹配：整数→浮点 |
| 14 | match | format | VARCHAR(20) | String(10) | 04 L330 | 长度缩短，"tournament"（10字符）恰好放不下 |
| 15 | membership_tier_config | tier | VARCHAR(20) | String(32) | 10 L207 | 长度不一致 |
| 16 | membership_tier_config | name | VARCHAR(32) | String(64) | 10 L208 | 长度不一致 |

#### 2.2 默认值/Nullable不匹配（8项）

| # | 表名 | 字段 | DB设计 | 切片 | 来源 | 描述 |
|---|------|------|--------|------|------|------|
| 17 | analysis_report | is_llm_generated | DEFAULT true | default=False | 03 L265 | 默认值语义反转 |
| 18 | analysis_report | result_data | NOT NULL | nullable=True | 03 L267 | nullable不匹配 |
| 19 | analysis_report | report_text | NOT NULL | nullable=True | 03 L268 | nullable不匹配 |
| 20 | share_record | share_scope | NOT NULL, DEFAULT 'public' | nullable=True, 无默认值 | 03 L304 | nullable+默认值均不匹配 |
| 21 | share_record | share_scope (值域) | public/friend | public/private | 03 L304 | 值域不匹配 |
| 22 | file_record | original_filename | nullable=True | NOT NULL (Mapped[str]) | 03 L221 | nullable不匹配 |
| 23 | payment_record | callback_raw | nullable=True | NOT NULL (Mapped[dict]) | 11 L494 | nullable不匹配 |
| 24 | refund_record | reason | nullable=True | NOT NULL (Mapped[str]) | 11 L514 | nullable不匹配 |

#### 2.3 约束缺失（3项）

| # | 表名 | 约束 | DB设计 | 切片 | 来源 | 描述 |
|---|------|------|--------|------|------|------|
| 25 | analysis_report | task_id UNIQUE | FK+CASCADE+UNIQUE | FK, index=True, 无unique | 03 L263 | 缺失UNIQUE约束，一对一关系未强制 |
| 26 | feedback_record | (report_id, user_id) UNIQUE | UNIQUE约束 | 无UniqueConstraint | 03 L279-290 | 缺失联合唯一约束，允许重复反馈 |
| 27 | match | opponent_name nullable | nullable=True (N) | NOT NULL (Mapped[str]) | 04 L328 | nullable反转 |

#### 2.4 FK缺少 ondelete CASCADE（1项，涉及10处）

| # | 表名 | 涉及字段 | 来源切片 | 描述 |
|---|------|---------|---------|------|
| 28 | 多表 | FileRecord.user_id, VideoTask.user_id, VideoTask.file_id, AnalysisReport.task_id, AnalysisReport.user_id, FeedbackRecord.report_id, FeedbackRecord.user_id, Match.user_id, checkin_record.user_id, subscription.user_id | 03 L219/240/241/263/264/284/285, 04 L327, 09 L200, 10 L224 | DB设计均指定ondelete CASCADE，切片均缺少ondelete参数，用户删除时产生孤儿记录 |

#### 2.5 字段缺失（2项）

| # | 表名 | 缺失字段 | DB设计定义 | 来源切片 | 描述 |
|---|------|---------|-----------|---------|------|
| 29 | video_task | retry_count | INT, DEFAULT 0 | 03 L234-252 | 切片Model中未定义此字段 |
| 30 | match | score_sequence | JSONB, nullable | 04 L322-346 | DB设计为Redis镜像缓存字段，切片Model中未定义 |

#### 2.6 索引缺失（1项）

| # | 表名 | 缺失索引 | DB设计定义 | 来源切片 | 描述 |
|---|------|---------|-----------|---------|------|
| 31 | subscription | (user_id, status), (status, expire_at) | §2.17 明确指定 | 10 L219-235 | 切片无__table_args__，缺少复合索引，影响到期扫描性能 |

#### 2.7 结构差异（1项）

| # | 表名 | 问题描述 | 来源切片 |
|---|------|---------|---------|
| 32 | user_profile → User | DB设计§2.2定义独立user_profile表（含kqs_rating/playing_style/equipment_config等字段），切片02将字段合并进User模型。切片line 968文档说明为有意设计，但DB设计未同步更新 | 02-user L200-204, L968 |

#### 2.8 Phase归属不符（3项）

| # | 表名 | DB设计Phase | 切片Phase | 来源切片 | 描述 |
|---|------|-----------|----------|---------|------|
| 33 | badge_definition, user_badge, badge_progress | Phase 2 (§3.1.4-3.1.6) | Phase 1 | 09-gamification | Phase 2表在Phase 1切片中实现 |
| 34 | consent_log | Phase 2 (§3.1.16) | Phase 1 | 01-auth L147 | Phase 2表在Phase 1切片中实现 |
| 35 | export_task | Phase 2 (§3.1.15) | Phase 1 | 02-user L231 | Phase 2表在Phase 1切片中实现 |

#### 2.9 Phase 1表未在任何切片实现（2项）

| # | 表名 | DB设计位置 | 描述 |
|---|------|-----------|------|
| 36 | pipeline_step | §2.6 (Phase 1) | DB设计Phase 1定义，但无切片实现PipelineStep Model |
| 37 | knowledge_category, knowledge_entry, rule_definition | §2.24-2.26 (Phase 1) | 切片07注释"由knowledge_base模块统一定义"，但无knowledge_base切片 |

### P3 — 轻微级（13项）

| # | 表名 | 字段/问题 | 描述 | 来源切片 |
|---|------|----------|------|---------|
| 38 | membership_tier_config | is_active/created_at/updated_at 注释 | 切片注释"切片新增（DB设计§2.31无此字段）"，但DB设计§2.31实际包含这3个字段。注释错误 | 10 L214-216 |
| 39 | payment_record | created_at | DB设计无此字段，切片新增。可能为DB设计遗漏 | 11 L496 |
| 40 | refund_record | reversal_type | DB设计无此字段，切片新增 (String(20), nullable) | 11 L516 |
| 41 | file_record | updated_at | DB设计无此字段，切片新增 | 03 L228 |
| 42 | checkin_record | checkin_type 默认值 | DB设计无默认值，切片添加 default="manual" | 09 L203 |
| 43 | checkin_record | points_earned 默认值 | DB设计无默认值，切片添加 default=2 | 09 L206 |
| 44 | progress_snapshot | report_id UNIQUE | DB设计未提及UNIQUE，切片添加 unique=True（1:1关系语义正确） | 08 L392 |
| 45 | badge_definition | 缺失索引 | DB设计§3.1.4指定 idx_badge_definition_category(category, sort_order)，切片无__table_args__ | 09 L214-229 |
| 46 | order | product_type 注释 | DB设计值域含"tournament"，切片注释仅"membership/analysis_pack/equipment" | 11 L457 |
| 47 | score_record | is_key_point nullable | DB设计为nullable，切片为NOT NULL+default=False | 04 L368 |
| 48 | admin_user, audit_log, system_config | 未在切片实现 | 基础设施表，可能在独立管理模块中实现 | — |

---

## 3. 重复定义检查

| 表名 | 定义位置 | 类型 | 严重度 | 描述 |
|------|---------|------|--------|------|
| **user** | 01-auth L129 + 02-user L188 | 类继承扩展 | P2 | 01-auth定义User基础字段（id, openid, phone, nickname, avatar_url, status），02-user在同一User类上扩展user_profile字段（kqs_rating, playing_style, self_assessed_level, equipment_config）。为同一类的分文件扩展，非独立重复定义，但Python不允许同一类名在两处独立定义——实际实现时需合并到单一文件 |
| **AnalysisReport** | 03-video_analysis L258 (定义) + 06-data_dashboard L262/L270 (注释引用) | 注释引用 | P3 ✅ | 06-data_dashboard以注释形式引用AnalysisReport和MatchRecord，非实际重复定义 |
| **MatchRecord** | 05-match_data L401 (定义) + 06-data_dashboard L270 (注释引用) | 注释引用 | P3 ✅ | 同上 |

**结论**：无真正的重复定义冲突。User在01-auth和02-user的"分文件扩展"模式在实际Python工程中需统一到单一 `app/models/user.py` 文件，建议在切片中明确标注合并策略。

---

## 4. 缺失检查

### 4.1 DB设计定义但切片未实现的表

| 表名 | DB设计位置 | Phase | 切片覆盖情况 | 严重度 | 建议 |
|------|-----------|-------|-------------|--------|------|
| user_profile | §2.2 | 1 | 合并进User模型（切片02） | P2 | DB设计应同步更新，或切片恢复独立表 |
| pipeline_step | §2.6 | 1 | **未实现** | P2 | 切片03-video_analysis应补充PipelineStep Model |
| knowledge_category | §2.24 | 1 | **未实现** | P2 | 需新增knowledge_base切片或在07-training_advice中实现 |
| knowledge_entry | §2.25 | 1 | **未实现** | P2 | 同上 |
| rule_definition | §2.26 | 1 | **未实现** | P2 | 同上 |
| model_3d_asset | §2.29 | 2 | 未实现 | P3 | Phase 2表，暂无需实现 |
| action_category | §2.30 | 2 | 未实现 | P3 | Phase 2表，暂无需实现 |
| admin_user | §2.31 | 1 | 未实现 | P3 | 基础设施表，可能在管理后台独立实现 |
| audit_log | §2.31 | 1 | 未实现 | P3 | 同上 |
| system_config | §2.31 | 1 | 未实现 | P3 | 同上 |

### 4.2 切片实现但DB设计未定义的表/字段

| 表名 | 字段 | 来源切片 | 严重度 | 建议 |
|------|------|---------|--------|------|
| training_template | （整表） | 07 L396 引用 | P1 | DB设计需补充training_template表定义（ER图§1.2已有实体） |
| payment_record | created_at | 11 L496 | P3 | DB设计应补充此字段 |
| refund_record | reversal_type | 11 L516 | P3 | DB设计应补充此字段 |
| file_record | updated_at | 03 L228 | P3 | DB设计应补充此字段 |

### 4.3 切片实现的Phase 2表（提前实现）

| 表名 | DB设计Phase | 实现切片 | 严重度 | 建议 |
|------|-----------|---------|--------|------|
| badge_definition | Phase 2 (§3.1.4) | 09-gamification | P2 | 确认是否调整到Phase 1，若是则DB设计应移至§2 |
| user_badge | Phase 2 (§3.1.5) | 09-gamification | P2 | 同上 |
| badge_progress | Phase 2 (§3.1.6) | 09-gamification | P2 | 同上 |
| consent_log | Phase 2 (§3.1.16) | 01-auth | P2 | 同上 |
| export_task | Phase 2 (§3.1.15) | 02-user | P2 | 同上 |

---

## 5. 完全一致的表（无不一致项）

以下表的切片Model定义与DB设计完全一致（或仅有TIMESTAMPTZ→DateTime的等价类型映射）：

| 表名 | 来源切片 | 备注 |
|------|---------|------|
| notification_record | 12-notification | ✅ 字段/类型/约束/索引全一致 |
| progress_snapshot | 08-progress_analysis | ✅ 仅report_id额外添加unique=True (P3) |
| technique_trend | 08-progress_analysis | ✅ 全一致 |
| plan_adjustment | 07-training_advice | ✅ 全一致 |
| training_plan | 07-training_advice | ✅ 全一致 |
| user_points | 09-gamification | ✅ 全一致 |
| rating_history | 02-user | ✅ 全一致 |

---

## 6. 修复优先级建议

### 立即修复（P1，6项）
1. `order.order_no` → 改为 `String(64)` 匹配DB设计
2. `file_record.file_size` / `actual_size` → 改为 `BigInteger` 匹配DB设计
3. `refund_record.status` 默认值 → 统一为 `"pending"` 或DB设计改为 `"processing"`（需业务确认）
4. `payment_record.transaction_id` → 添加 `unique=True`
5. `training_template` → DB设计补充表定义，或切片明确标注定义位置

### 尽快修复（P2 高频项）
6. 统一所有FK的 `ondelete="CASCADE"`（影响10处外键）
7. 统一 `technique_action` / `score_method` 的字段长度（影响04-scoring和05-match_data两个切片）
8. 修正 `analysis_report` 的 `result_data`/`report_text` nullable 和 `task_id` UNIQUE
9. 修正 `share_record.share_scope` 的 nullable + 默认值 + 值域
10. 修正 `membership_tier_config` 的 `tier`/`name` 长度
11. 确认Phase归属：badge/consent_log/export_task 是否调整到Phase 1
12. 补充 `pipeline_step` 和 knowledge 三表的切片实现

### 计划修复（P3）
13. 修正切片中"切片新增"的错误注释
14. DB设计补充切片新增的合理字段（created_at/updated_at/reversal_type）
15. 补充缺失索引定义
