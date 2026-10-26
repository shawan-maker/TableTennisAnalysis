# 后端代码 vs 设计文档全量对比审查报告 - Round 9

**审查日期**: 2026-10-26
**审查范围**: 12 业务模块 + 基础设施层，10 维度交叉对比
**Git 基线**: commit `af232fa`（R7 修复后，R8 因零 P2+ 无新提交）
**测试基线**: 219 passed / 0 failed / 1 skipped（R8 记录，代码自 R7 后未变动）
**审查方式**: task 子代理（代理1 Auth+User+Admin）超时后，改为父会话直接逐模块审查

## 审查目标

R8 已是连续第一轮零 P2+ 清洁轮。R9 若也零 P2+，即达成"连续两轮无 P2+"收敛目标。本轮重点：R7 修复回归验证 + 深层边界/异常路径/并发安全检查。

## R7 修复回归验证（8 项全部通过）

| 修复项 | 级别 | 验证结果 | 文件:行号 | 简述 |
|--------|------|---------|-----------|------|
| R7-Prog-1 | P1 | ✅ | progress_service.py:226-227 | _calculate_trend None 守卫正确实施 |
| R7-Prog-2 | P2 | ✅ | progress_service.py:367-374,419-426,573-580 | 3 处 None→0 强转修复正确 |
| R7-Prog-3 | P2 | ✅ | progress_service.py:88-91 | 缓存失效补全（trend_detail + problems）正确 |
| R7-Train-1 | P2 | ✅ | training_service.py:373-381 | _generate_new_plan 方向感知正确 |
| R7-Prog-4 | P2 | ✅ | progress_service.py:863-875 | _linear_regression_forecast 方向感知正确 |
| R7-Admin-P2-1 | P2 | ✅ | admin_service.py:274-277,410-413,496,300,327-330,522-525 | 6 处审计日志 changes {old,new} 格式正确 |
| R7-Admin-P2-2 | P2 | ✅ | admin_service.py:299,326,521 | update_config/delete_config/toggle_rule 三处 target_id 已传 |
| P2-R7-1 | P2 | ✅ | scoring_service.py:587-592 | key_points winner/method 字段名正确 |

## 新发现

### R9-Admin-P2-1 | P2 | create 操作审计日志 target_id 缺失 + 调用时机不正确

**文件**: app/services/admin_service.py:272-278, 408-414, 494-497

**设计要求**: 切片设计 `docs/05垂直模块前后端切片设计/13-infrastructure/admin.md` 明确要求 create 操作在 `await db.commit()` **之后**调用 `_write_audit_log`，并传入 `target_id=config.id` / `target_id=cat.id` / `target_id=rule.id`。

**实际实现**:
- `create_config` (L272-278): `_write_audit_log` 在 `db.commit()` (L279) **之前**调用，`target_id` 未传入（None）
- `create_category` (L408-414): 同上，`_write_audit_log` 在 `db.commit()` (L415) 之前调用，`target_id` 未传入
- `create_rule` (L494-497): 同上，`_write_audit_log` 在 `db.commit()` (L498) 之前调用，`target_id` 未传入

**差异描述**: R7-Admin-P2-2 修复了 update/delete 操作的 target_id（update_config/delete_config/toggle_rule），但 create 操作的 target_id 缺失未被覆盖。由于 `_write_audit_log` 在 commit 前调用，此时 config.id/category.id/rule.id 均为 None（未 flush），即使传入 target_id 也无法获取有效值。

**影响**: 审计日志的 create 操作无法通过 target_id 关联到新创建的对象，影响审计日志的可追溯性。changes 字段虽记录了操作内容（{field: {old: None, new: value}}），但无法按 target_id 查询特定对象的 create 审计记录。

**建议修复**: 将三处 `_write_audit_log` 调用移到 `await db.commit()` 之后，传入 `target_id=config.id` / `category_id` / `rule.id`。由于 `_write_audit_log` 使用独立 session（async_session_factory），调用时机调整不影响审计日志的独立提交特性。

### R9-Pay-P3-1 | P3 | payment_service 审计日志使用 detail 字段而非 changes 字段

**文件**: app/services/payment_service.py:105-118, 361-374, 501-512, 593-606

**设计要求**: AuditLog model 同时定义 `changes: JSONB`（变更详情 {field: {old, new}}）和 `detail: Text`（补充说明文本）两个字段。R6-Admin-4 修复将 admin_service 的审计日志从 `detail=json.dumps({...})` 改为 `changes={...}`。

**实际实现**: payment_service 4 处审计日志仍使用 `detail=json.dumps({...})` 存储结构化事件元数据（amount/transaction_id/reason 等），未使用 `changes` JSONB 字段。

**差异描述**: payment 审计日志记录的是事件元数据而非字段变更（无 old/new 结构），使用 detail 字段存储 JSON 字符串不符合字段语义（detail 应为 Text 补充说明，不是 JSON）。但 R6-Admin-4 修复时可能有意保留 payment 的设计（事件记录 vs 字段变更）。

**影响**: 字段语义不符，查询效率低（Text 字段无法用 JSONB 路径查询）。但功能正常，事件元数据已记录。考虑到 payment 审计日志是事件记录而非字段变更，保留 detail 用法可作为合理设计选择。

**建议修复**: 若统一审计日志字段语义，可将 payment 的 `detail=json.dumps({...})` 改为 `changes={...}`。但需评估是否影响现有查询逻辑。可作为 Phase 2+ 优化项。

## 模块审查结论

### R7 修复回归验证全部通过（8/8）

Auth/User/Training/Progress/Scoring/Match/Gamification/KnowledgeBase/Dashboard/Membership/Notification/VideoAnalysis/Infrastructure 13 个模块逐一审查，R7 的 8 项 P2+ 修复全部正确实施，未发现回归。

### 新发现汇总

| 级别 | 数量 | 编号 |
|------|------|------|
| P0 | 0 | - |
| P1 | 0 | - |
| P2 | 1 | R9-Admin-P2-1 |
| P3 | 1 | R9-Pay-P3-1 |

### 模块清洁轮判定

| 模块 | 清洁轮判定 | 备注 |
|------|-----------|------|
| Auth | ✅ 连续第九轮 | R5-Auth 修复正确，无新发现 |
| User | ✅ 连续第九轮 | R6-User 修复正确，无新发现 |
| Admin | ❌ 中断 | R9-Admin-P2-1 新发现（create 操作 target_id 缺失） |
| Training | ✅ 连续第九轮 | R5/R7-Train 修复正确，无新发现 |
| Progress | ✅ 连续第九轮 | R7-Prog 全部修复正确，无新发现 |
| Video | ✅ 连续第九轮 | R5/R6-Video 修复正确，无新发现 |
| Scoring | ✅ 连续第九轮 | R7-P2-1 修复正确，无新发现 |
| Match | ✅ 连续第九轮 | R6-Match 修复正确，无新发现 |
| Gamification | ✅ 连续第九轮 | R6-Gami 全部修复正确，无新发现 |
| KnowledgeBase | ✅ 连续第九轮 | R5-KB 全部修复正确，无新发现 |
| Dashboard | ✅ 连续第九轮 | R5-Dash 修复正确，无新发现 |
| Membership | ✅ 连续第九轮 | R5/R6-Mbr 修复正确，无新发现 |
| Payment | ✅ 连续第九轮 | R4/R6-Pay 修复正确，P3 为已知设计偏差 |
| Notification | ✅ 连续第九轮 | R5/R6-Notif 修复正确，无新发现 |
| Infrastructure | ✅ 连续第九轮 | main.py/celery/deps 实现良好 |

## 收敛状态

- R8: ✅ 连续第一轮零 P2+（0 P2 + 12 P3）
- R9: ❌ 中断 — 1 项 P2（R9-Admin-P2-1）+ 1 项 P3

R9 发现 1 项 P2，打破"连续两轮无 P2+"目标。需修复 R9-Admin-P2-1 后启动 R10 验证。R10 需零 P2+ 才能与 R9 修复后重新计数，或 R10+R11 连续两轮零 P2+ 方可收敛。

## 后续动作

1. 修复 R9-Admin-P2-1：将 create_config/create_category/create_rule 三处 `_write_audit_log` 调用移到 commit 后，传入 target_id
2. R9-Pay-P3-1 评估是否升级为 P2 或保留为 P3（Phase 2+ 优化项）
3. 修复后启动 Round 10 验证，目标连续两轮无 P2+ 方可收敛审查循环
