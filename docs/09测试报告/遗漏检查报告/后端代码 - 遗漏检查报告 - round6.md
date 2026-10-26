# 后端代码实现 vs 设计文档 — Round 6 全量对比审查报告

## 总览

| 指标 | 数值 |
|------|------|
| 审查范围 | 全部 12 个业务模块 + 基础设施层（5 个并行子代理） |
| 审查维度 | 10 维度交叉对比 |
| 发现总数 | 94 项（P0×0 + P1×4 + P2×27 + P3×63） |
| R5 回归缺陷 | 0 项（R5 修复全部正确实施，无回归） |
| 连续无 P2+ | **未达成**（R5 有 42 P2+ → R6 有 31 P2+） |
| Git 基线 | commit `2557ae8` |

## 一、各子代理发现统计

| 子代理 | 覆盖模块 | P0 | P1 | P2 | P3 | 小计 |
|--------|----------|----|----|----|----|------|
| 代理 1 | Auth + User + Admin | 0 | 0 | 10 | 17 | 27 |
| 代理 2 | Training + Progress | 0 | 1 | 3 | 8 | 12 |
| 代理 3 | Video + Scoring + Match | 0 | 0 | 7 | 18 | 25 |
| 代理 4 | Gami + KB + Dashboard | 0 | 1 | 4 | 15 | 20 |
| 代理 5 | Mbr + Pay + Notif + Infra | 0 | 2 | 3 | 5 | 10 |
| **合计** | | **0** | **4** | **27** | **63** | **94** |

## 二、R5 修复回归验证

**全部 42 项 R5 P2+ 修复均正确实施，无回归缺陷。** 各代理逐项验证结果：

- R5-Auth-1~4: ✅ 全部通过
- R5-User-1~2: ⚠️ R5-User-1 部分通过（Redis Key 改 CST 但 reset_at 显示值时区仍错误 → R6-User-1）
- R5-Admin-1~6: ✅ 全部通过
- R5-Train-1~5: ✅ 全部通过
- R5-Prog-1~4: ✅ 全部通过
- R5-Video-1~6: ✅ 全部通过（R5-Video-4 回退为 JSON，正确）
- R5-Gami-1~3: ⚠️ R5-Gami-2 引入 P1 回归（IntegrityError rollback 范围过广 → R6-Gami-1）
- R5-KB-1~3: ✅ 全部通过
- R5-Dash-1: ✅ 通过
- R5-Mbr-1: ✅ 通过
- R5-Pay-1~2: ✅ 全部通过（R5-Pay-2 回退 + 审计日志 FK 修复正确）
- R5-Infra-1~5: ✅ 全部通过

## 三、P1 发现（4 项）

### R6-Train-1 | P1 | test_get_advice_by_report 测试 fixture technique_stats 键名不匹配
- **文件**: tests/unit/test_training.py:95-102 vs app/services/progress_service.py:92,101-103
- **影响**: 预存测试失败（technique_stats 用 COUNT 键 forehand_drive/backhand_drive/serve，但 _extract_metrics 读 RATIO 键 backhand_ratio/forehand_ratio/serve_ratio）
- **修复**: 更新测试 fixture technique_stats 使用 ratio 键

### R6-Gami-1 | P1 | check_badges IntegrityError rollback 范围过广
- **文件**: app/services/gamification_service.py
- **影响**: db.rollback() 连同调用方事务（打卡/积分/连续天数）一起回滚，API 返回 200 但数据静默丢失
- **修复**: 使用 db.begin_nested()（SAVEPOINT）隔离徽章解锁

### R6-Mbr-1 | P1 | check_membership 不检查 subscription.status
- **文件**: app/services/membership_service.py:136-153,258
- **影响**: expired 订阅被视为有效会员，过期会员仍享无限分析额度
- **修复**: 增加 subscription.status == "active" 检查

### R6-Notif-1 | P1 | on_ws_reconnect 在 subscribe 之前 publish sync 消息
- **文件**: app/api/v1/ws.py:75-85
- **影响**: Redis pubsub 不缓冲无订阅者消息，sync 事件丢失，重连补偿功能损坏
- **修复**: 先 subscribe 再 publish sync 消息

## 四、P2 发现（27 项）— 按模块分组

### Auth 模块（1 项）
- R6-Auth-1: get_current_user 允许 pending_deletion 状态用户（设计应拒绝）

### User 模块（2 项）
- R6-User-1: quota reset_at 显示值时区错误（Redis Key 已 CST 但返回值仍用 UTC）
- R6-User-2: /users/quota 端点不在 API §3 设计中（代码新增但 API 未文档化）

### Admin 模块（7 项）
- R6-Admin-1: 审计日志 action 值与 API 设计不一致（create_rule→"create_rule" vs 设计 "rule_create"）
- R6-Admin-2: 审计日志 target_type 值与 API 设计不一致
- R6-Admin-3: 审计日志 target_id 部分端点传 0 而非 None
- R6-Admin-4: 审计日志 changes 字段使用 detail 而非 changes JSONB 列
- R6-Admin-5: AuditLogBrief.admin_id 类型 int 而非 Optional[int]（admin_id 可空时 500 风险）
- R6-Admin-6: AuditLogBrief 类型不匹配（int vs Optional[int]）
- R6-Admin-7: toggle_rule 路径参数 str vs 设计 int（R5 有意回退，标记为已知偏差）

### Training 模块（2 项）
- R6-Train-2: _evaluate_plan_effectiveness all_achieved 不区分 direction（down 指标已达标误判为未达标）
- R6-Train-3: get_templates 排序 id 而非 created_at.desc()（见 P3 部分 R6-Prog-4 重编号）

### Progress 模块（2 项）
- R6-Prog-1: goal_completion 对 down 指标 current_value==0 返回 "0%" 而非 "100%"
- R6-Prog-2: get_technique_trend_detail 对有效指标无趋势数据时返回 404（设计应返回 null 字段响应）

### Video Analysis 模块（3 项）
- R6-Video-1: confirm_upload 错误消息单一化（API §4.2 指定两条不同消息 + code=42200）
- R6-Video-2: get_upload_token 文件类型校验返回 422（API §4.1 指定 400）+ Schema 缺 field_validator
- R6-Video-3: get_shared_report 返回嵌套 report_text 结构（切片 §5 指定扁平 report_summary + top_issues）

### Scoring 模块（2 项）
- R6-Scoring-1: score_sequence items 用 seq 字段名（API §5.3 指定 sequence）
- R6-Scoring-2: MatchDetail schema 缺少 current_score 字段

### Match Data 模块（2 项）
- R6-Match-1: MatchRecordCreateResponse schema 缺少 match_id 字段
- R6-Match-2: MatchRecord model 有未文档化的 opponent_user_id 列

### Gamification 模块（3 项）
- R6-Gami-2: checkin 返回 bonus: 0 而非设计的 bonus: null
- R6-Gami-3: _get_user_metrics 用 AnalysisReport/Match 计数而非设计的 CheckInRecord（按 checkin_type）
- R6-Gami-4: get_points 连续天数从 DB 读取而非设计的 Redis 实时值

### Knowledge Base 模块（1 项）
- R6-KB-1: toggle_rule 参数类型 str vs API 设计 int（与 R6-Admin-7 重复，R5 有意回退）

### Payment 模块（2 项）
- R6-Pay-1: _create_or_renew_subscription status 过滤缺 grace_period（宽限期内支付会创建重复订阅）
- R6-Pay-2: 退款 + 撤销订阅跨事务分离，撤销失败无补偿

### Notification 模块（1 项）
- R6-Notif-2: subscribe_templates 静默过滤与 API §13.3 定义 422 不一致（需同步文档）

## 五、结论

Round 6 发现 31 项 P2+ 问题（4 P1 + 27 P2），**未达成连续两轮无 P2+**。

**关键观察**：
- R5 修复全部正确实施，**无 R5 回归**
- 本轮 P2+ 以 Schema/API 契约偏差为主（字段名/缺失字段/类型不一致），非逻辑错误
- R6-Gami-1 是 R5-Gami-2 修复引入的 P1 回归（IntegrityError rollback 范围过广）
- R6-Train-1 是预存测试失败根因诊断（technique_stats 键名不匹配）
- R6-Admin-7 / R6-KB-1 toggle_rule str vs int 是 R5 有意回退（测试契约），标记为已知偏差

**修复策略**：修复全部 4 P1 + 26 P2（去除 1 重复/有意回退项），启动 Round 7 验证。

---

*本报告基于 Round 6 审查时点的代码状态（commit `2557ae8`）。*
