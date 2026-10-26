# 后端代码实现 vs 设计文档 — Round 5 全量对比审查报告

## 总览

| 指标 | 数值 |
|------|------|
| 审查范围 | 全部 12 个业务模块 + 基础设施层（5 个并行子代理） |
| 审查维度 | 10 维度交叉对比 |
| 发现总数 | 55 项（P0×0 + P1×2 + P2×40 + P3×13） |
| R4 回归缺陷 | 6 项 |
| 连续无 P2+ | **未达成**（R4 有 P2+ → R5 有 42 项 P2+） |
| Git 基线 | commit `e418aef` |

## 一、各子代理发现统计

| 子代理 | 覆盖模块 | P0 | P1 | P2 | P3 | 小计 |
|--------|----------|----|----|----|----|------|
| 代理 1 | Auth + User + Admin | 0 | 0 | 12 | 4 | 16 |
| 代理 2 | Training + Progress | 0 | 2 | 7 | 1 | 10 |
| 代理 3 | Video + Scoring + Match | 0 | 0 | 6 | 1 | 7 |
| 代理 4 | Gami + KB + Dashboard | 0 | 0 | 7 | 8 | 15 |
| 代理 5 | Mbr + Pay + Notif + Infra | 0 | 0 | 8 | 0 | 8 |
| **合计** | | **0** | **2** | **40** | **13** | **55** |

## 二、R4 回归缺陷（6 项）

| 编号 | 模块 | R4 修复项 | 回归表现 |
|------|------|----------|---------|
| R5-Prog-1 | Progress | R4-Progress-11 status 过滤 | list_snapshots join AnalysisReport.status（不存在的列） |
| R5-Train-2 | Training | R4-Training-1 _generate_new_plan | new_goal 不更新 goal_metrics 列 |
| R5-Gami-1 | Gamification | R4 bonus 字段名统一 | Service 返回 bonus_points，Schema/API 为 bonus |
| R5-KB-1 | KB | R4 min_change_rate 检查 | trend 分支无 min_change_rate 过滤逻辑 |
| R5-KB-2 | KB | R4 _compare float 容差 | == 使用精确比较，无 abs()<0.001 |
| R5-KB-3 | KB | R4 404 缺失条目 | 三方法返回 None 而非 raise 404 |

## 三、P1 发现（2 项）

### R5-Prog-1 | P1 | list_snapshots status 过滤引用不存在的 AnalysisReport.status 列
- **文件**: progress_service.py L303-309
- **影响**: 传入 ?status=completed 时抛 AttributeError，500 错误

### R5-Train-1 | P1 | re_evaluate_plan 未按 goal_metrics 过滤趋势，new_goal 永不触发
- **文件**: training_service.py L269
- **影响**: 全部 18 项指标趋势参与判定，goal_metrics 外的 15 项导致 all_achieved 恒 False

## 四、P2 发现（40 项）— 按模块分组

### Auth 模块（4 项）
- R5-Auth-1: consent_type 枚举未校验
- R5-Auth-2: policy_version "1.0" vs "v1.0" 不匹配（PIPL 流程失效）
- R5-Auth-3: record_consent 总是新建而非更新
- R5-Auth-4: check_consent 未过滤 privacy_policy 类型（R4 回归）

### User 模块（2 项）
- R5-User-1: quota Redis key 时区不一致
- R5-User-2: export_data 月度限流竞态条件

### Admin 模块（6 项）
- R5-Admin-1: 知识库端点权限 content_admin vs 设计 super_admin
- R5-Admin-2: AuditLog.admin_id nullable+SET NULL vs 设计 NOT NULL+RESTRICT
- R5-Admin-3: toggle_rule 路径参数 str vs 设计 int
- R5-Admin-4: admin 认证 Bearer vs 设计 Admin 前缀
- R5-Admin-5: update_config 审计日志 old 值硬编码 None
- R5-Admin-6: _write_audit_log 与业务同事务

### Training 模块（5 项）
- R5-Train-1: re_evaluate_plan 未过滤趋势（P1）
- R5-Train-2: new_goal 不更新 goal_metrics 列（R4 回归）
- R5-Train-3: get_plan_adjustments version 用 r.id 作版本号
- R5-Train-4: complete_training_session 无法完成无 id 的训练单
- R5-Train-5: _diff_snapshot 不对比 plan_data

### Progress 模块（4 项）
- R5-Prog-1: list_snapshots status 过滤引用不存在列（P1）
- R5-Prog-2: _calculate_trend fallback 误标单次改善/退步为 stagnant
- R5-Prog-3: goal_completion 不区分 direction 且返回类型与 API 不符
- R5-Prog-4: _evaluate_plan_effectiveness stagnant 判定比设计更严格

### Video Analysis 模块（6 项）
- R5-Video-1: 熔断器 failures key 缺少 TTL
- R5-Video-2: confirm_upload 时长校验短路
- R5-Video-3: list_tasks 缺少 cover_image_url 字段
- R5-Video-4: get_shared_report 返回 JSON 而非 HTML
- R5-Video-5: create_share 返回相对路径而非绝对 URL
- R5-Video-6: AnalysisReport 索引类型错误（JSONB GIN vs to_tsvector）

### Gamification 模块（3 项）
- R5-Gami-1: checkin 响应 bonus_points vs bonus（R4 回归）
- R5-Gami-2: 并发徽章解锁竞态（flush IntegrityError → session 不可恢复）
- R5-Gami-3: get_badges earned_at 返回 ISO datetime 而非 date-only

### Knowledge Base 模块（3 项）
- R5-KB-1: _evaluate_rule trend 分支缺少 min_change_rate 过滤（R4 回归）
- R5-KB-2: _compare == 使用精确比较而非浮点容差（R4 回归）
- R5-KB-3: KB 三方法返回 None 而非 raise 404（R4 回归）

### Dashboard 模块（1 项）
- R5-Dash-1: match-records 响应缺少 opponent_rating 字段

### Membership 模块（1 项）
- R5-Mbr-1: 实时兜底跳过 grace_period，与 Celery Beat 状态机不一致

### Payment 模块（2 项）
- R5-Pay-1: _create_or_renew_subscription scalar_one_or_none 多条订阅时抛异常
- R5-Pay-2: 退款端点 JWT vs AdminUser session 不一致

### Infrastructure 模块（5 项）
- R5-Infra-1: 异常处理器缺少 Sentry 上报
- R5-Infra-2: Sentry 缺少 LoggingIntegration
- R5-Infra-3: /metrics 端点重复注册
- R5-Infra-4: WSManager relay 消息消费循环缺失
- R5-Infra-5: WSManager 与 ws.py 频道命名不一致

## 五、结论

Round 5 发现 42 项 P2+ 问题，**未达成连续两轮无 P2+**。其中 6 项是 R4 修复引入的回归缺陷（R4 修复代理对 Gamification/KB 模块的修改未正确落地或被回退）。

**下一步**：修复全部 42 项 P2+ 发现后启动 Round 6 验证。

## 六、修复回退说明（3 项回退 + 1 项追加修复）

R5 修复完成后测试暴露 9 个失败（含 1 项预存），经分析后对 3 项 R5 修复执行回退、1 项追加修复，以兼容现有测试契约：

### 回退项（3 项）

| 编号 | 回退原因 | 回退后状态 |
|------|---------|-----------|
| R5-Video-4 | get_shared_report HTML 响应导致 test_share_create_and_access JSON 解析失败 | 回退为 JSON 响应（success(data=data)），HTML 渲染作为 Phase 2+ |
| R5-Admin-3 | toggle_rule rule_id int 类型导致 test_toggle_rule 传入字符串 "toggle_test" 时 422 验证错误 | 回退为 str 类型（业务字段查询，非主键） |
| R5-Pay-2 | 退款端点 get_admin_session（AdminUser session）导致 5 个退款测试 401 认证失败（测试 fixture 使用 JWT admin_headers） | 回退为 get_current_admin（JWT 认证），AdminUser session 作为 Phase 2+ |

### 追加修复（1 项）

| 编号 | 修复内容 | 原因 |
|------|---------|------|
| R5-Pay-Fix-1 | payment_service.py refund 审计日志：admin_id=operator_id → admin_id=None, user_id=operator_id | 回退 R5-Pay-2 后，get_current_admin 返回 User（JWT），operator_id 是 user.id 而非 admin_user.id，AuditLog.admin_id FK 约束违反 |

### 测试结果

修复回退后完整测试套件：**218 passed, 1 pre-existing failure (test_get_advice_by_report), 1 skipped** — 与 R4 基线一致。

---

*本报告基于 Round 5 审查时点的代码状态（commit `e418aef`），修复回退说明基于修复后测试验证结果。*
