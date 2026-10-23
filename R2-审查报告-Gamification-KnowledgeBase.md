# Round 2 全量对比审查报告 — Gamification & Knowledge Base 模块

> **审查日期**：2026-10-23  
> **审查范围**：Gamification 模块（router/service/schema/model）+ Knowledge Base 模块（service/schema/model）  
> **对比基准**：09-gamification/backend.md、13-infrastructure/knowledge_base.md、04-数据库详细设计.md  
> **审查维度**：10 项（API 端点 / ORM 字段 / Schema 字段 / 打卡逻辑 / 积分规则 / 徽章进度 / _evaluate_rule / get_rules_by_problem / match_rules 模板 / model_validate）

---

## 汇总统计

| 级别 | 数量 | 模块分布 |
|------|------|----------|
| **P0** | 0 | — |
| **P1** | 9 | Gamification 6, Knowledge Base 3 |
| **P2** | 18 | Gamification 10, Knowledge Base 8 |
| **P3** | 5 | Gamification 3, Knowledge Base 2 |
| **合计** | **32** | — |

---

## P1 级发现（高优先级 — 逻辑/行为差异）

### R2-Gam-1 ｜ P1 ｜ 打卡返回 points_earned 包含 bonus 积分，设计要求仅返回基础积分

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L137-162 (`checkin` 方法) |
| **设计定义** | 切片 §5 L557-561：`points_earned=GamificationService.POINTS_RULES["checkin"]`（仅基础积分 2），`bonus=bonus`（单独返回 20）。测试用例 L99-101 明确断言 `data["points_earned"] == 2` 且 `data["bonus"] == 20` |
| **代码实现** | L137: `points = POINTS_RULES["checkin"] + bonus`（合并为 22），L159: `"points_earned": points`（返回 22） |
| **差异描述** | 代码将基础打卡积分(2)与连续打卡奖励(20)合并为 `points_earned=22` 返回，而设计要求 `points_earned=2`（基础）+ `bonus=20`（额外）分开返回。单元测试 `test_checkin_streak_7_days_bonus` 将失败 |

### R2-Gam-2 ｜ P1 ｜ _auto_checkin 将 base+bonus 合并为单次 _add_points("checkin") 调用，丢失 bonus 事件类型

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L230-244 (`_auto_checkin` 方法) |
| **设计定义** | 切片 §5 L711-724：分两次调用 `_add_points`——先 `_add_points(db, user_id, "checkin", POINTS_RULES["checkin"])`，再 `_add_points(db, user_id, "streak_7", POINTS_RULES["streak_7"])` 或 `"streak_30"`。事件类型分别记录 |
| **代码实现** | L233: `points = POINTS_RULES["checkin"] + bonus`，L244: `await GamificationService._add_points(db, user_id, "checkin", points, None)`——合并为单次 "checkin" 事件 |
| **差异描述** | 代码将连续打卡奖励积分合并到 "checkin" 事件类型中，设计要求以 "streak_7"/"streak_30" 独立事件类型记录。导致积分来源无法按事件类型区分，后续积分审计/统计无法追溯 bonus 来源 |

### R2-Gam-3 ｜ P1 ｜ _auto_checkin 与 add_points 双重调用 check_badges，徽章检测重复执行

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L249-252（`_auto_checkin` 内）+ L183-185（`add_points` 内） |
| **设计定义** | 切片 §5 L585-591：`_auto_checkin` 不调用 `check_badges`；`add_points` 在 `_auto_checkin` 完成后调用一次 `BadgeService.check_badges(db, user_id)` |
| **代码实现** | `_auto_checkin` L249-252: `await BadgeService.check_badges(db, user_id)` + `add_points` L183-185: `await BadgeService.check_badges(db, user_id)`。当 `event_type in ("analysis", "match", "record")` 且当天首次触发自动打卡时，`check_badges` 被调用两次 |
| **差异描述** | 徽章检测在自动打卡场景下被重复执行。虽然 `UserBadge` 有 UNIQUE 约束防止重复插入，但 `check_badges` 内部的 WS 推送 `badge_unlocked` 事件可能触发两次，且额外的 DB 查询（徽章定义/已获得/进度/用户指标）造成性能浪费 |

### R2-Gam-4 ｜ P1 ｜ 缺少 _get_streak 方法，get_points/get_checkin_calendar 从 DB 读取 streak 而非 Redis

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L71-82 (`get_points`)、L111-120 (`get_checkin_calendar`) |
| **设计定义** | 切片 §5 L456: `current_streak = await GamificationService._get_streak(user_id)`——从 Redis 实时读取。§6 L501: `streak_days = await GamificationService._get_streak(user_id)`。`_get_streak` 方法定义于 L616-620 |
| **代码实现** | L75: `streak = up.current_streak`（从 DB `UserPoints` 表读取）；L112: `streak = up.current_streak if up else 0`。无 `_get_streak` 方法定义 |
| **差异描述** | 设计要求从 Redis 实时读取连续打卡天数（`gamification:streak:user:{user_id}`），确保与 `_update_streak` 的 Redis 写入一致。代码改从 DB 读取 `current_streak` 字段，该字段仅在 `_auto_update_streak` 被调用后才更新。若 Redis streak 已更新但 DB 尚未 flush（如 `_auto_checkin` 中 `_update_streak` 已执行但 `_auto_update_streak` 未执行时），get_points 返回过期值 |

### R2-Gam-5 ｜ P1 ｜ _get_user_metrics 统计来源不同——代码从 AnalysisReport/Match 表统计，设计从 CheckInRecord 按 type 统计

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L397-418 (`_get_user_metrics` 方法) |
| **设计定义** | 切片 §6 L897-937：`analysis_count` = `CheckInRecord` 中 `checkin_type == "analysis"` 的记录数；`match_count` = `CheckInRecord` 中 `checkin_type in ["match", "record"]` 的记录数；`streak_days` = `_get_streak(user_id)` (Redis) |
| **代码实现** | L398-400: `analysis_count` = `AnalysisReport` 表 count where `user_id`；L402-404: `match_count` = `Match` 表 count where `user_id`；L411: `streak_days = up.current_streak`（DB）。额外引入 `from app.models.match import Match, MatchRecord` 和 `from app.models.video_analysis import AnalysisReport` 跨模块依赖 |
| **差异描述** | 统计语义不同：设计基于打卡记录计数（反映用户活跃行为触发自动打卡的次数），代码基于实际业务记录计数（反映用户实际完成分析/比赛的总数）。两种统计方式在自动打卡失败或手动打卡场景下结果不同。此外引入了设计未要求的跨模块 Model 依赖 |

### R2-Gam-6 ｜ P1 ｜ 所有 Service 方法返回 raw dict 而非 Pydantic Model，缺少 model_validate 转换

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L71-82, L84-120, L122-162, L294-337 |
| **设计定义** | 切片 §5-6：`get_points` 返回 `PointsResponse`，`get_checkin_calendar` 返回 `CheckInCalendarResponse`，`checkin` 返回 `CheckInResponse`，`get_badges` 返回 `BadgeListResponse`。所有 Schema 均有 `model_config = {"from_attributes": True}` |
| **代码实现** | 所有方法返回 `dict`（如 L78-82 `return {"total_points": up.total_points, ...}`）。无任何 `model_validate` 调用。项目其他 Service（user_service L209, admin_service L197/207/224/243 等）均使用 `model_validate` |
| **差异描述** | 代码返回原始 dict，跳过了 Pydantic 类型验证和序列化保障。缺少 `model_config = {"from_attributes": True}` 意味着无法从 ORM 对象直接转换。与项目其他 Service 的编码规范不一致。可能导致 API 响应字段类型不一致或遗漏计算字段 |

### R2-KB-1 ｜ P1 ｜ _evaluate_rule 使用 rule.rule_type 字段而非 condition.aggregation 字段判断规则类型

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/knowledge_base_service.py` L218-282 (`_evaluate_rule` 方法) |
| **设计定义** | 切片 §5 L419-478：`aggregation = cond.get("aggregation", "single")`，通过 condition JSONB 中的 `aggregation` 字段决定评估分支。DB §7.3 condition JSONB 示例包含 `"aggregation": "single"` |
| **代码实现** | L226: `rule_type = rule.rule_type`——直接使用 RuleDefinition 表的 `rule_type` 列值作为分支判断依据，不读取 `condition.aggregation` |
| **差异描述** | 设计要求从 condition JSONB 的 `aggregation` 字段判断评估方式，代码改用 `rule_type` 列。若某条规则的 `rule_type="single"` 但 `condition.aggregation="trend_persistent"`（或反之），代码与设计的评估路径将不同。DB §7.3 明确定义 condition JSONB 包含 `aggregation` 字段，代码完全忽略该字段 |

### R2-KB-2 ｜ P1 ｜ 建议模板占位符名称不匹配——代码用 {value}，设计用 {current_value}

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/knowledge_base_service.py` L237 (`_evaluate_rule` single 分支)、L252-257 (trend 分支) |
| **设计定义** | 切片 §5 L461-465：`suggestion = suggestion.replace("{current_value}", str(ctx.metrics[metric]))` + `suggestion = suggestion.replace("{threshold}", str(threshold))`。DB §7.4 diagnosis 示例：`"suggestion_template": "反手使用率 {current_value}，低于推荐值 {threshold}"` |
| **代码实现** | L237: `suggestion_params.update({"metric": metric, "value": value, "threshold": threshold})`——占位符键为 `value`，通过 `_fill_placeholders` 渲染为 `{value}`。L252-257: trend 分支使用 `direction`/`persistence`/`change_rate` 作为 params 键 |
| **差异描述** | 设计的 `suggestion_template` 使用 `{current_value}` 占位符，代码的 `suggestion_params` 提供 `{value}`。当 seed 数据中模板写的是 `{current_value}` 时，代码的 `_fill_placeholders` 无法匹配替换，用户将看到原始占位符文本 `{current_value}` 而非实际数值 |

### R2-KB-3 ｜ P1 ｜ 所有 KB Service 方法返回 raw dict 而非 Pydantic Model，缺少 model_validate

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/knowledge_base_service.py` L38-45, L48-60, L62-75, L77-91, L93-110, L112-137, L139-155, L157-171, L174-215 |
| **设计定义** | 切片 §5：所有方法使用 `model_validate` 返回 Pydantic Model：`list_categories` → `list[CategoryBrief]` via `CategoryBrief.model_validate(c)`；`get_rules_by_problem` → `list[RuleDetail]` via `RuleDetail.model_validate(r)`；`match_rules` → `list[MatchResult]` |
| **代码实现** | 所有方法手动构造 dict 返回（如 L42-45: `{"id": r.id, "name": r.name, "code": r.code}`）。无任何 `model_validate` 调用 |
| **差异描述** | 代码完全跳过 Pydantic 验证，手动构造 dict 容易遗漏字段或类型不一致。`match_rules` 返回 `list[dict]` 而非 `list[MatchResult]`，调用方无法获得类型提示。与设计文档的 `model_validate` 要求全面偏离 |

---

## P2 级发现（中优先级 — 结构/偏差问题）

### R2-Gam-7 ｜ P2 ｜ POINTS_RULES 定义为模块级常量而非类属性

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L37-47 |
| **设计定义** | 切片 §5 L421-432：`POINTS_RULES` 定义为 `GamificationService` 类属性，引用方式为 `GamificationService.POINTS_RULES["checkin"]` |
| **代码实现** | L37: 模块级常量 `POINTS_RULES = {...}`，引用方式为 `POINTS_RULES["checkin"]` |
| **差异描述** | 模块级常量与类属性在功能上等价，但破坏了设计文档的封装结构。类属性可通过 `GamificationService.POINTS_RULES` 被其他模块引用，模块级常量需要 `from app.services.gamification_service import POINTS_RULES` |

### R2-Gam-8 ｜ P2 ｜ BadgeService 未拆分到独立文件 badge_service.py

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L290-424（BadgeService 类定义） |
| **设计定义** | 切片 §1 L4: `badge 逻辑在 badge_service.py`；§6 L755: `# app/services/badge_service.py` |
| **代码实现** | BadgeService 与 GamificationService 定义在同一个文件 `gamification_service.py` 中 |
| **差异描述** | 设计要求 BadgeService 位于独立文件 `app/services/badge_service.py`，代码合并到 `gamification_service.py`。影响模块边界清晰度和导入路径 |

### R2-Gam-9 ｜ P2 ｜ Schema 缺少 model_config = {"from_attributes": True}

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/schemas/gamification.py` L11-56（所有 Schema 类） |
| **设计定义** | 切片 §4 L326/335/346/355/365/376/384：每个 Schema 类均有 `model_config = {"from_attributes": True}` |
| **代码实现** | 所有 Schema 类均无 `model_config` 定义 |
| **差异描述** | 缺少 `from_attributes` 配置意味着无法通过 `Model.model_validate(orm_obj)` 从 ORM 对象直接转换。虽然当前代码返回 dict 不触发此路径，但与设计规范不一致 |

### R2-Gam-10 ｜ P2 ｜ streak_icon 阈值不同——代码 ≥7 显示🔥，设计 ≥3 显示🔥

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L76 |
| **设计定义** | 切片 §5 L462: `streak_icon="🔥" if current_streak >= 3 else ""`——连续 3 天即显示火焰 |
| **代码实现** | L76: `icon = "🌟" if streak >= 30 else "🔥" if streak >= 7 else ""`——需 ≥7 天才显示火焰，≥30 天显示星星 |
| **差异描述** | 代码的火焰图标阈值（7天）比设计（3天）更严格。设计不包含 ≥30 天的星星图标。用户体验差异：连续 3-6 天打卡时设计显示🔥但代码显示空字符串 |

### R2-Gam-11 ｜ P2 ｜ BadgeEarned.earned_at 返回完整 datetime ISO 字符串，设计要求 date-only

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L322 |
| **设计定义** | 切片 §6 L812: `earned_at=earned_map[definition.id].earned_at.date().isoformat()`——仅日期部分，如 "2026-01-15" |
| **代码实现** | L322: `earned_map[d.id].earned_at.isoformat() if earned_map[d.id].earned_at else ""`——完整 datetime，如 "2026-01-15T10:30:00+00:00" |
| **差异描述** | 返回格式不同，前端展示需要额外截断处理 |

### R2-Gam-12 ｜ P2 ｜ WS 推送 badge_unlocked 消息结构不同——代码发送列表，设计按单个徽章推送含 points_reward

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L388-394 |
| **设计定义** | 切片 §6 L984-992：`for badge in badges: await NotificationService.push_ws_message(user_id, "badge_unlocked", {"badge_id": ..., "name": ..., "icon": ..., "points_reward": ...})`——逐个推送，含 points_reward 字段 |
| **代码实现** | L392: `await NotificationService.push_ws_message(user_id, "badge_unlocked", newly_unlocked)`——`newly_unlocked` 为 `list[dict]`，每个 dict 仅含 `badge_id`/`name`/`icon`，无 `points_reward` |
| **差异描述** | 消息结构不同（列表 vs 单对象），缺少 `points_reward` 字段。前端 WebSocket 处理逻辑需适配不同结构 |

### R2-Gam-13 ｜ P2 ｜ checkin 路由缺少 message="打卡成功" 返回

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/api/v1/gamification/router.py` L71 |
| **设计定义** | 切片 §7 L1101: `return success(data=data, message="打卡成功")` |
| **代码实现** | L71: `return success(data=data)`——无 message 参数 |
| **差异描述** | 打卡成功提示消息缺失，前端无法展示"打卡成功"反馈 |

### R2-Gam-14 ｜ P2 ｜ 事务管理不同——代码在 Service 内 flush，设计在 Service 内 commit

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L151 (`checkin`)、L180 (`add_points`)；`app/api/v1/gamification/router.py` L70 |
| **设计定义** | 切片 §5 L552: `await db.commit()`（Service 内提交）；§5 L589: `await db.commit()`（add_points 内提交） |
| **代码实现** | Service 内调用 `await db.flush()`（L151/L180），commit 在 Router 层 L70 执行 |
| **差异描述** | 代码将 commit 职责移至 Router 层，Service 仅 flush。设计要求 Service 内 commit。影响事务边界和错误回滚策略。若 Router 层 commit 前发生异常，Service 的 flush 数据将回滚 |

### R2-Gam-15 ｜ P2 ｜ add_points 异常时不执行 db.rollback

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L188-190 |
| **设计定义** | 切片 §5 L597: `await db.rollback()`——异常时回滚事务 |
| **代码实现** | L188-190: `except Exception as e: logger.warning(...); return 0`——仅记录日志返回 0，不回滚 |
| **差异描述** | 异常时未回滚事务，可能导致部分写入（如 _add_points 已 flush 但 _auto_checkin 失败时）残留到后续 commit |

### R2-Gam-16 ｜ P2 ｜ get_checkin_calendar 使用 EXTRACT 而非日期范围查询，可能无法利用索引

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L90-98 |
| **设计定义** | 切片 §5 L477-483: `CheckInRecord.checkin_date >= month_start` AND `< month_end`——范围查询，可利用 `idx_checkin_user_date` 索引 |
| **代码实现** | L94-95: `func.extract("year", CheckInRecord.checkin_date) == year` AND `func.extract("month", ...) == month`——EXTRACT 函数查询 |
| **差异描述** | EXTRACT 函数在 PostgreSQL 中无法利用 B-Tree 索引（需全表扫描后过滤），设计的范围查询可利用 `idx_checkin_user_date` 索引。数据量大时性能差异显著 |

### R2-Gam-17 ｜ P2 ｜ 徽章进度 BadgeLocked.progress 未截断为 min(current, target)

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L328-335 (`get_badges` 方法) |
| **设计定义** | 切片 §6 L820: `progress = min(current_value, target)`——进度值不超过目标值 |
| **代码实现** | L328: `progress = min(100, int(current / target * 100)) if target > 0 else 0`（百分比，计算后未使用）；L333: `"progress": current`（返回原始值，未截断） |
| **差异描述** | 代码计算了百分比 `progress` 但未使用（死代码），实际输出使用原始 `current` 值且未截断。设计要求 `progress = min(current_value, target)` 截断。当 current > target 时（如分析 15 次但徽章只需 10 次），代码返回 15 而设计返回 10 |

### R2-KB-4 ｜ P2 ｜ Schema 命名不一致——TemplateBriefSchema vs 设计 TemplateBrief

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/schemas/knowledge_base.py` L50 (`TemplateBriefSchema`)、L57 (`TemplateDetailSchema`) |
| **设计定义** | 切片 §4 L211: `class TemplateBrief(BaseModel)`、L219: `class TemplateDetail(TemplateBrief)` |
| **代码实现** | L50: `class TemplateBriefSchema(BaseModel)`、L57: `class TemplateDetailSchema(TemplateBriefSchema)` |
| **差异描述** | Schema 类名添加了 `Schema` 后缀，与设计文档命名不一致。影响跨模块 import 引用的一致性 |

### R2-KB-5 ｜ P2 ｜ Schema 缺少 model_config = {"from_attributes": True}

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/schemas/knowledge_base.py` L11-78（所有 Schema 类） |
| **设计定义** | 切片 §4 L173/186/200/217 等：`CategoryBrief`/`EntryBrief`/`RuleBrief`/`TemplateBrief` 均有 `model_config = {"from_attributes": True}` |
| **代码实现** | 所有 Schema 类均无 `model_config` 定义 |
| **差异描述** | 同 R2-Gam-9，KB 模块所有 Schema 缺少 `from_attributes` 配置 |

### R2-KB-6 ｜ P2 ｜ CategoryDetail/EntryDetail 的 content/created_at 字段类型不同

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/schemas/knowledge_base.py` L18-19 (`CategoryDetail`)、L30-31 (`EntryDetail`) |
| **设计定义** | 切片 §4 L177-178: `content: dict`（非可选）、`created_at: datetime`（非可选） |
| **代码实现** | L18: `content: dict = {}`（有默认值）、L19: `created_at: Optional[datetime] = None`（可选） |
| **差异描述** | 代码将 content 和 created_at 设为可选/有默认值，设计要求必填。当 ORM 对象的 content 为 None 或 created_at 为 None 时，代码不报错而设计应报错 |

### R2-KB-7 ｜ P2 ｜ RuleContext 使用 mutable 默认值 {} 而非 Field(default_factory=dict)

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/schemas/knowledge_base.py` L76-78 |
| **设计定义** | 切片 §4 L240-242: `metrics: dict[str, Any] = Field(default_factory=dict)`、`trends: dict[str, dict] = Field(default_factory=dict)` |
| **代码实现** | L76: `metrics: dict[str, Any] = {}`、L77: `trends: dict[str, dict] = {}` |
| **差异描述** | 虽然在 Pydantic v2 中 mutable 默认值会被安全处理，但设计明确使用 `Field(default_factory=dict)` 是更规范的写法，确保每个实例获得独立副本 |

### R2-KB-8 ｜ P2 ｜ match_rules 方法签名不同——代码接收 db+dict，设计接收 RuleContext

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/knowledge_base_service.py` L174 |
| **设计定义** | 切片 §5 L386: `async def match_rules(ctx: RuleContext) -> list[MatchResult]`——接收 Pydantic Model，自管理 DB session |
| **代码实现** | L174: `async def match_rules(db: AsyncSession, ctx: dict) -> list[dict]`——接收 db + dict |
| **差异描述** | 签名差异：设计使用 RuleContext Pydantic Model 作为参数类型，代码使用 dict。设计自管理 session（`async with get_async_session() as db`），代码由调用方传入 session。影响调用方式和类型安全 |

### R2-KB-9 ｜ P2 ｜ get_rules_by_problem 签名不同——代码接收 db 参数，设计自管理 session

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/knowledge_base_service.py` L113 |
| **设计定义** | 切片 §5 L347: `async def get_rules_by_problem(problem_id: str) -> list[RuleDetail]`——无 db 参数，自管理 session |
| **代码实现** | L113: `async def get_rules_by_problem(db: AsyncSession, problem_id: str) -> list[dict]`——接收 db 参数 |
| **差异描述** | 所有 KB Service 方法签名均多了 `db: AsyncSession` 参数，设计使用 `async with get_async_session() as db` 自管理 session。两种模式混合使用影响调用方一致性 |

### R2-KB-10 ｜ P2 ｜ _evaluate_rule 缺少 min_change_rate 检查

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/knowledge_base_service.py` L241-258 (trend_persistent/trend_improving 分支) |
| **设计定义** | 切片 §5 L446-453: 读取 `min_change_rate = cond.get("min_change_rate", 0.0)` 并检查 `if abs(change_rate) < min_change_rate: return None` |
| **代码实现** | L241-258: 不读取 `min_change_rate`，不检查变化率门槛 |
| **差异描述** | 趋势规则缺少变化率最小值校验。设计要求趋势的变化率需达到 `min_change_rate` 阈值才匹配，代码仅检查方向和持续性。可能导致微小变化被误判为趋势匹配 |

### R2-KB-11 ｜ P2 ｜ check_badges 默认 threshold 不同——代码用 1，设计用 0

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L359 |
| **设计定义** | 切片 §6 L862: `target = definition.condition.get("threshold", 0)`——默认 0 |
| **代码实现** | L359: `target = cond.get("threshold", 1)`——默认 1 |
| **差异描述** | 当徽章 condition JSONB 缺少 `threshold` 字段时，代码使用默认值 1（需至少 1 次才解锁），设计使用默认值 0（立即解锁）。极端场景下行为不同 |

---

## P3 级发现（低优先级 — 细微/装饰性问题）

### R2-Gam-18 ｜ P3 ｜ STREAK_ICONS 常量定义但未使用（死代码）

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py` L49 |
| **设计定义** | 设计文档无此常量定义 |
| **代码实现** | L49: `STREAK_ICONS = {0: "", 7: "🔥", 30: "🌟"}`——定义后未在任何方法中引用，get_points 使用内联三元表达式计算 icon |
| **差异描述** | 死代码。建议移除或统一使用 |

### R2-Gam-19 ｜ P3 ｜ 缺少 _insert_checkin_for_test 测试辅助方法

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/services/gamification_service.py`（缺失） |
| **设计定义** | 切片 §5 L728-747: `_insert_checkin_for_test(user_id: int, d: date)` 方法——直接插入指定日期打卡记录 + 更新 Redis streak |
| **代码实现** | 无此方法 |
| **差异描述** | 测试辅助方法缺失。设计文档中的单元测试用例（`test_checkin_streak_7_days_bonus`、`test_streak_reset_after_gap` 等）依赖此方法预置打卡数据 |

### R2-Gam-20 ｜ P3 ｜ API summary 文本不同——"每日打卡" vs "手动打卡"

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/api/v1/gamification/router.py` L63 |
| **设计定义** | 切片 §7 L1094: `summary="手动打卡"` |
| **代码实现** | L63: `summary="每日打卡"` |
| **差异描述** | API 文档 summary 文本差异，不影响功能 |

### R2-KB-12 ｜ P3 ｜ training_template.name 字段长度——代码/切片 128 vs DB 设计 64

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/models/knowledge_base.py` L93 |
| **设计定义** | DB §2.27 L933: `name VARCHAR(64)` |
| **代码实现** | L93: `name = Column(String(128), nullable=False)`（切片设计 §3 L134 也用 128） |
| **差异描述** | 代码与切片设计一致（128），但与 DB 设计文档不一致（64）。DB 设计文档的 VARCHAR(64) 可能是笔误，但三方不完全一致 |

### R2-KB-13 ｜ P3 ｜ KnowledgeEntry 缺少 category_id 的 index=True

| 项目 | 内容 |
|------|------|
| **文件+行号** | `app/models/knowledge_base.py` L53-55 |
| **设计定义** | 切片 §3 L86: `category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey(...), index=True)` |
| **代码实现** | L53-55: `category_id = Column(BigInteger, ForeignKey(...), nullable=False)`——无 `index=True` |
| **差异描述** | 切片设计要求在 category_id 上创建索引（加速按分类查询条目），代码未实现。DB 设计文档未明确定义此索引 |

---

## 维度覆盖矩阵

| # | 审查维度 | 发现编号 | 最高级别 |
|---|----------|----------|----------|
| 1 | API 端点完整性 | R2-Gam-13, R2-Gam-20 | P2 |
| 2 | ORM 模型字段一致性 | R2-KB-12, R2-KB-13 | P3 |
| 3 | Schema 字段一致性 | R2-Gam-9, R2-KB-4, R2-KB-5, R2-KB-6, R2-KB-7 | P2 |
| 4 | 打卡逻辑 _auto_checkin 完整性 | R2-Gam-1, R2-Gam-2, R2-Gam-3, R2-Gam-4, R2-Gam-14, R2-Gam-15, R2-Gam-19 | P1 |
| 5 | 积分规则 POINTS_RULES | R2-Gam-7 | P2 |
| 6 | 徽章进度计算 | R2-Gam-17, R2-KB-11 | P2 |
| 7 | _evaluate_rule 返回 MatchResult dict | R2-KB-1, R2-KB-2, R2-KB-10 | P1 |
| 8 | get_rules_by_problem JSONB 查询 | R2-KB-9 | P2 |
| 9 | match_rules 建议模板填充 | R2-KB-2, R2-KB-8 | P1 |
| 10 | model_validate 使用情况 | R2-Gam-6, R2-KB-3 | P1 |
| — | 额外发现 | R2-Gam-5, R2-Gam-8, R2-Gam-10, R2-Gam-11, R2-Gam-12, R2-Gam-16, R2-Gam-18 | P1 |

---

## 修复优先级建议

### 必须立即修复（P1）
1. **R2-Gam-1**: `checkin` 返回 `points_earned` 改为仅基础积分，bonus 单独返回
2. **R2-Gam-2**: `_auto_checkin` 拆分为两次 `_add_points` 调用，分别使用 "checkin" 和 "streak_7"/"streak_30" 事件类型
3. **R2-Gam-3**: 从 `_auto_checkin` 中移除 `check_badges` 调用，仅保留 `add_points` 中的调用
4. **R2-Gam-4**: 补充 `_get_streak` 方法，`get_points`/`get_checkin_calendar` 改为从 Redis 读取 streak
5. **R2-Gam-5**: `_get_user_metrics` 改为从 `CheckInRecord` 按 `checkin_type` 统计，移除 AnalysisReport/Match 跨模块依赖
6. **R2-Gam-6 + R2-KB-3**: 所有 Service 方法补充 `model_validate` 返回 Pydantic Model
7. **R2-KB-1**: `_evaluate_rule` 改为使用 `condition.aggregation` 字段判断规则类型
8. **R2-KB-2**: `suggestion_params` 中 `"value"` 改为 `"current_value"`，与 DB §7.4 的模板占位符对齐

### 建议尽快修复（P2）
9. **R2-Gam-8**: BadgeService 拆分到 `app/services/badge_service.py`
10. **R2-Gam-9 + R2-KB-5**: 所有 Schema 补充 `model_config = {"from_attributes": True}`
11. **R2-Gam-12**: WS 推送改为逐个推送且包含 `points_reward` 字段
12. **R2-Gam-14-15**: 统一事务管理策略，补充 rollback
13. **R2-Gam-16**: `get_checkin_calendar` 改为日期范围查询
14. **R2-KB-8-9**: KB Service 方法签名对齐设计（自管理 session 或统一 db 参数模式）

---

## 反幻觉声明

- 本报告仅基于代码文件与设计文档的字面对比，未运行任何代码验证
- 所有行号引用已通过文件读取确认
- `model_validate` 缺失已通过全项目 grep 验证（gamification_service.py 和 knowledge_base_service.py 中 0 匹配，其他 Service 文件有 9 处匹配）
- 未修改任何文件
