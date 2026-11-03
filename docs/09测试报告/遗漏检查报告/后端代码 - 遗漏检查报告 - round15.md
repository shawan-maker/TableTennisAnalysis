# 后端代码 - 遗漏检查报告 - Round 15

> **审查对象**：app/ 全部生产代码 + tests/ + docs/ 设计文档（重点：R14 重建文档回归核验 + R14 修复交互面）
> **审查方式**：5 并行子代理（A1 契约/支付链、A2 基础设施/测试计数、A3 重建账目/样例契约、A4 围栏/格式完整性、A5 生产缺口交叉）
> **修复纪律**：P2+ 逐项"代码修复 → 锁测试 → 域回归"闭环；文档补丁断言先行单次落盘；全量回归收敛后提交
> **报告基线**：round14.md（185 行）+ 全量回归基线 597 passed / 1 skipped（r14_full2.log）

## 一、执行摘要

- **R15 审查发现 P1×1 + P2×6 + P3 批量**，全部修复闭环（7 项生产/测试/文档修复，无推迟 P2+）。
- **连续两轮零 P2+ 目标中断**：R14 为第一轮零 P2+，R15 出现 1 P1 + 6 P2 → 计数中断，**R16 重启计数**（须连续 R16+R17 两轮零 P2+）。
- **新增 29 例锁测试全绿**（5 个新测试文件 25 例 + 2 个既有文件增量 4 例），全量回归 **626 passed / 1 skipped**（基线 598 + 29 = 627，零失败、零 flaky、覆盖率 77.08% 达 70% 门控）。
- **P3 文档同步 14 份文档**（含 2 处 R14 重建引入/遗留的结构性缺陷：01-auth 围栏缺失闭合、file_management 围栏缺失开启 — 均为 v0 原始缺陷，非重建回归）。
- **round14 报告 7 处修正**（6 处测试失实陈述 + 1 处行数账目漏计），重建回归专项结论：R14 重建本体无回归，报告侧陈述失实已全部修正。

## 二、R15 审查发现（P1×1 + P2×6）

| 编号 | 级别 | 领域 | 发现 |
|------|------|------|------|
| R15-State-N1 | P1 | ai_pipeline | `generate_snapshot` 链路：调用方先行终态转换（completed）后被调方内部二次转换被 `TASK_TRANSITIONS` 终态空集拒绝 → 通知/WS 分支不可达；重试链通知投递时机错误；`cascade:done:*` / `notif:*` 键未纳入 conftest 清理 → 跨测试行为级污染 |
| R15-Pay-N1 | P2 | payment | 退款不回收 analysis_pack 付费额度（`quota:bonus:{uid}` 仅回调 INCR 写入、无退款消费面对称回收 → 退款后额度虚增，写入-回收链不对称） |
| R15-VA-N1 | P2 | user/membership | `bonus_remaining` 展示层缺失：QuotaResponse（两处）/MembershipCheckResult 无该字段；免费分支 `has_quota` 不含付费包余额（免费额度耗尽 + 付费包有余额时误判不可创建） |
| R15-User-N1 | P2 | user | 注销匿名化遗漏 5 个画像字段（kqs_rating / kqs_username / playing_style / equipment_config / self_assessed_level → PIPL 删除权残留） |
| R15-User-N2 | P2 | file_management | 软删文件 OSS 物理删除断链：文档契约「status=deleted，24h 后 OSS 物理删除」无任何实现（任务未注册、方法不存在） |
| R15-Test-N1 | P2 | tests | ①B4-1 断言缺失（40415 差异化守卫未落地，round14 报告声称存在）；②Gam-N1 feedback/share 积分断言缺失（积分入账无回归守卫）；③round14 报告 6 处陈述失实（详见 §六） |
| R15-Doc-N1 | P2 | infrastructure | conftest.py.md 重建注记失实：声称「按实际实现逐行重建」但样例自始为设计稿形态（SQLite+fakeredis+event_loop vs 实际 PG+Redis+无 event_loop） |

P3 批量（本次全部同步或留档，见 §五）：API §3.11/§11.3 quota 契约、02-user/10-membership quota 样例、DB 设计 purged 状态、测试计划 ENUM-U-03、file_management §4/§6.2、ai_pipeline 测试计数 14→15、09-gam add_points 样例旧形态、payment L1135 补偿机制失实声明、payment 行数账目、alembic 迁移注释（留档）。

## 三、P1 + P2 修复明细（7 项，全修复 + 测试锁定）

### 3.1 R15-State-N1（P1）— 状态机先行转换 + 通知链 + 键污染

- `app/ai_pipeline/progress.py` L164（on_step_failed 不再先行 transition → failed）、L199（失败通知迁移至最终失败处）、L240（清除重试窗口内 cascade:done:* 残留键）
- `app/ai_pipeline/tasks.py` L224（on_task_complete 成为唯一终态收口点）、L257（最终失败通知：在线 WS / 离线 DB 落库）
- `app/ai_pipeline/report_generator.py` L266-272（快照投递 SETNX 幂等防重）
- `app/services/video_analysis_service.py` L231（eager 模式 Retry 异常分支状态语义）、L257（失败通知随终态触发）
- `tests/conftest.py` L117：清理清单新增 `cascade:done:*`、`notif:*`（防跨运行残留污染计数断言）
- 锁测试：`tests/unit/test_r15_state_retry.py`（6 例，重试链状态/通知/幂等/键清理全覆盖）

### 3.2 R15-Pay-N1（P2）— 退款回收付费额度

- `app/services/payment_service.py` L642-680：退款 commit 后回收 `quota:bonus:{user_id}` — 全额退款全量回收；部分退款按 `bonus_qty * refund_amount_cents // order.amount_cents` 取整回收；clamp 至当前余额（get+min+decrby）；键过期/缺失无操作不落负键；membership 订单分支隔离不受影响；回收失败独立 try/except 不阻塞退款主流程（退款已先行 commit）
- 锁测试：`tests/unit/test_r15_pay_refund_bonus.py`（6 例：全额/部分/clamp/过期无操作/取整零/membership 隔离）；支付域回归 70 例全绿（test_payment 20 + test_r14_d 14 + test_supplements_p2 36）

### 3.3 R15-VA-N1（P2）— bonus 展示层与免费分支判定

- `app/schemas/user.py` L116（QuotaResponse.+bonus_remaining）、`app/schemas/membership.py` L53/L69（QuotaResponse + MembershipCheckResult 同步）
- `app/services/user_service.py` L224（get_quota 读取 quota:bonus，max(0,int)，Redis 异常降级 0）
- `app/services/membership_service.py` L161（check_membership 免费分支 `has_quota = remaining > 0 or bonus_remaining > 0`）、L179（新增 `_get_bonus_remaining` 统一读取）
- 外部调用方核验：deps.require_membership / training_service / va create_task 三处均只用 is_member，语义修正零风险
- 锁测试：`tests/unit/test_r15_va_bonus_display.py`（6 例）；回归 test_membership+test_r14_d 29 例、test_user 19 例全绿

### 3.4 R15-User-N1（P2）— 注销匿名化画像字段

- `app/tasks/user.py` L76：anonymization 扩展 5 字段（kqs_rating / kqs_username / playing_style / equipment_config / self_assessed_level = None）
- 锁测试：`tests/unit/test_r15_user_anonymize.py`（2 例）

### 3.5 R15-User-N2（P2）— 软删文件 OSS 物理删除

- `app/services/file_service.py` L187：`cleanup_deleted_files()` — 扫描 `status='deleted'` 且 `updated_at` < NOW()-24h → `delete_object`（FileNotFoundError 吸收 = 404 幂等）→ 成功置 `status='purged'`（终态，WHERE 幂等不重扫）；失败保持 deleted 下轮重试（泄漏自愈）
- `app/tasks/file_management.py` L38：任务包装；`app/core/beat_schedule.py` L23-30：注册 `file-management-deleted-cleanup`（每小时 :30 偏移避开孤儿清理 :00，queue=infra）
- `app/models/video_analysis.py`：FileRecord status 注释 +purged（不加 deleted_at 列，无 schema 变更；软删时间戳 = updated_at，ORM onupdate 在 Core update() 同样生效）
- 锁测试：`tests/unit/test_r15_user_oss_purge.py`（5 例，含 beat 注册断言 + 裸 asyncio.run 任务体经 asyncio.to_thread 调用模式）；回归 test_r14_a + test_cascade_chains 44 例全绿

### 3.6 R15-Test-N1（P2）— 守卫补齐 + round14 报告修正

- `tests/unit/test_r14_g_progress_notif.py`：新增 `TestB4_1_MetricNotFound40415`（2 例：无效指标 → 404 + code 40415 + msg；合法指标无数据 → 200 null 字段）
- `tests/unit/test_r14_b_va_scoring.py`：新增 `_points_total` / `_create_report` 辅助 + feedback（+1）/ share（+2）积分入账断言（基线 12 = analysis+10 + auto_checkin+2；BadgeDefinition 非全局种子无徽章加成，绝对值断言可靠）
- round14.md 6 处修正（见 §六）

### 3.7 R15-Doc-N1（P2）— conftest.py.md 注记如实化

- `docs/05垂直模块前后端切片设计/13-infrastructure/conftest.py.md` L6-7：删除「按实际实现逐行重建」失实声明，改为如实声明（样例为历史设计稿形态：SQLite + fakeredis + event_loop + mock_redis；实际：PG + Redis、无自定义 event_loop、per-loop 池重建 `_redis_pool_per_loop`）+ R15-Doc-N1 修正注记。BOM+LF 保持。

## 四、测试补齐（29 例，全绿）

| 文件 | 例数 | 覆盖 | 运行 |
|------|------|------|------|
| tests/unit/test_r15_state_retry.py | 6 | State-N1：重试链状态语义/最终失败通知/快照幂等/键清理 | 全绿 |
| tests/unit/test_r15_pay_refund_bonus.py | 6 | Pay-N1：全额/部分/clamp/过期/取整零/membership 隔离 | 16.2s 全绿 |
| tests/unit/test_r15_va_bonus_display.py | 6 | VA-N1：两处 QuotaResponse + 免费分支 has_quota 语义 | 14.6s 全绿 |
| tests/unit/test_r15_user_anonymize.py | 2 | User-N1：5 画像字段匿名化 | 4.8s 全绿 |
| tests/unit/test_r15_user_oss_purge.py | 5 | User-N2：批扫/404 幂等/purged 终态/失败重试/beat 注册 | 11.2s 全绿 |
| test_r14_g_progress_notif.py（+2） | 12→14 | B4-1 40415 守卫（报告声称 → 真实成立） | 28/28 全绿 |
| test_r14_b_va_scoring.py（+2） | 12→14 | Gam-N1 feedback/share 积分入账守卫 | 28/28 全绿 |

**合计 29 例新增；域回归组合**：支付域 70 例（Pay-N1 后）、会员+用户域 48 例（VA-N1 后）、44 例（User-N2 后）、ai_pipeline 域（State-N1 后）全绿，既有用例零破坏（新增响应字段不破坏字段级断言，既有 quota 测试无全字典相等断言）。

## 五、P3 文档同步（14 份文档）

| # | 文档 | 修改 |
|---|------|------|
| 1 | 05-API详细设计.md §3.11 | GET /users/quota Response + bonus_remaining + 业务规则 4 + R15-P3 注记（混合行尾：LF 区） |
| 2 | 05-API详细设计.md §11.3 | GET /membership/quota Response + bonus_remaining + 业务规则 + R15-P3 注记（CRLF 区） |
| 3 | 02-user/backend.md | QuotaResponse 样例 + bonus_remaining + §5 注记 1 扩展 |
| 4 | 10-membership/backend.md | 两 Schema + get_quota/check_membership 样例同步（_get_bonus_remaining + has_quota or-bonus 行替换） |
| 5 | 04-数据库详细设计.md L507 | FileRecord status 枚举 + purged + 状态说明行 |
| 6 | 07实施计划/02-测试计划.md L1565 | ENUM-U-03 枚举 + purged（R15-User-N2 扩展） |
| 7 | file_management.md §4 | 软删 bullet 补实现说明（cleanup_deleted_files Beat 批扫 → purged） |
| 8 | file_management.md §6.2 | R15-P3 同步注记（physical_delete_task 设计草稿形态保留声明 + 实际 Beat 批扫契约） |
| 9 | file_management.md L377 | **结构修复**：archive_for_training 块补缺失开栅栏（v0 原始缺陷，15→16 围栏严格配对） |
| 10 | 09-gamification/backend.md | add_points 样例按实际实现回写（R13-Gam-N1 修复前旧形态：局部 logging / 类属性 POINTS_RULES / except 内 rollback / check_badges 混入同 try）+ 注记 12 |
| 11 | 11-payment/backend.md L1134-1135 | F4-1 注释粘连行拆分 + 补偿机制声明如实化（设计意图未实现 — beat 注册表 11 任务无此项，历史遗留文档-代码矛盾非重建引入） |
| 12 | ai_pipeline.md L1087 | R14 测试计数修正 14 → 15（实测 15 例：3+4+4+3+1） |
| 13 | 01-auth/backend.md L179 | **结构修复**：ConsentLog 代码块补缺失闭合围栏（R12 同步遗留，17→18 围栏 9 对严格交替） |
| 14 | round14.md L33 | payment 行数账目修正：1657→1666（原 1660 漏计 R14-Pay-N2 退款窗口修复注释块 +6；difflib 归因：头部注记 +2 / N2 注释块 +6 / EOF 空行 +1） |

**留档项（不修改）**：alembic/versions/140dfb07bb39 L112 `reversal_type` 注释仍含 full_reversal（实际模型 L108 已标注「full_reversal 已废弃，R14-Pay-N2」）— 历史迁移文件不可变更（避免破坏已应用环境的迁移一致性），DB 设计 §5 L791 未枚举值域无矛盾。

**围栏全量扫描**（51 份文档，修正语义：文档态任何栅栏开块 / 代码态仅裸 ``` 闭块）：全部 OK，零异常（初版检查器 5 处误报系裸 ``` 开栅栏合法用法，已甄别排除）。

## 六、round14 报告修正（重建回归专项）

R15 对 round14.md 执行重建回归专项核验（不可凭重建注记豁免），发现 7 处失实并修正：

1. B4-1 行（声称 40415 断言存在 → 实为缺失，本轮 Test-N1 补齐后成立，加 R15 修正注）
2. Gam-N1 行（声称积分断言存在 → 实为缺失，本轮补齐，加 R15 修正注）
3. VA-1 行（归属失实 → 实际位于 test_video_analysis.py L394/L406，非声称文件）
4. B 行计数 12 → 12+2（TestB4_1 增量后）
5. G 行计数 12 → 12+2（gam_n1 增量后，描述同步）
6. L103 总数行（99 例口径 + R15 修正注）
7. L33 payment 行数账目（1660 → 1666，漏计 +6 归因）

**重建回归专项结论**：R14 七份文档重建本体（payment 158 行 / ai_pipeline 177 行 / auth 68 行等 611 处 FFD→0）经 R15 全维度核验**无语义回归**；失实集中在 round14 报告侧的陈述层（测试归属/计数/账目），非重建落盘内容。conftest.py.md 注记失实（R15-Doc-N1）为唯一文档侧 P2，已如实化。

## 七、全量回归

```
626 passed, 1 skipped, 1 warning in 1809.89s (0:30:09)
Required test coverage of 70% reached. Total coverage: 77.08%
```

- **627 = 基线 598（R14 两次收敛 597+1）+ R15 新增 29**，零失败、零 flaky（单次运行收敛）。
- 1 skipped 为既有 Windows 平台条件跳过（与 R14 基线一致）；stderr 尾部 `RuntimeError: Event loop is closed` 为进程退出期 asyncio 清理噪音（历次全量回归均存在，非测试失败）。
- 运行方式：后台 Start-Process + 日志轮询（pytest 串行执行防 conftest DROP/CREATE SCHEMA 互踩；PYTHONUNBUFFERED=1 + PYTHONIOENCODING=utf-8）。

## 八、结论与 Round 16 计划

**结论**：R15 发现的 1 P1 + 6 P2 全部修复并测试锁定（多为 R12-R14 修复的交互面遗留：状态机收口唯一性、写入-回收对称、展示层契约、PIPL 残留、契约断链、报告失实），29 例守卫入册，全量回归 626/627 收敛，覆盖率 77.08%。文档侧 14 份 P3 同步 + 2 处 v0 结构缺陷修复 + 1 项留档。

**Round 16 计划**（连续两轮零 P2+ 计数重启，本轮为第 1 轮）：

1. **R15 修复回归验证**：7 项修复的代码证据 + 测试证据双落地核验（重点：State-N1 终态收口唯一性枚举 transition_task_status 全部调用点；Pay-N1 回收与 R14-Pay-N1 墓碑的交互面）。
2. **重建回归专项延续**：round14 报告修正后再核验（7 处修正落盘验证）+ conftest.py.md 如实化注记的残留一致性。
3. **新增守卫稳定性**：test_r15_* 五文件与 conftest 键清理清单（cascade:done:* / notif:*) 的跨批次稳定性。
4. **P3 留档追踪**：alembic 140dfb07bb39 注释（不改）、conftest.py.md 样例形态（设计稿保留）、physical_delete_task 设计草稿形态保留声明。
5. 常规 6 维度并行审查（若用户启动全维度轮次）。
