# 后端代码 - 遗漏检查报告 - Round 14

> 日期：2026-11-02 / 2026-11-03（测试补齐 + 重建收尾 + 死代码清理 + P3 同步 + 全量回归）
> 范围：R13 修复基线之上的三方全量对比审计（R12 八批次方法复用）→ U+FFFD 历史乱码文档重建（7 份）→ 测试缺口补齐（7 代理 99 例）→ 生产缺陷修复（9 项）→ 死代码清理（22 处）→ P3 文档同步（9 文档 25+ 处）→ 全量回归
> 基线：R13 收敛后 499 用例全绿（498 passed + 1 skipped）
> 目标：连续两轮零 P2+（R14 为第一轮）

## 一、执行摘要

| 事项 | 数量 | 状态 |
|------|------|------|
| U+FFFD 文档重建 | 7 份（611 处乱码 → 0） | ✅ 01-auth(68)/07-training(89)/08-progress(73)/09-gamification(149)/11-payment(158)/conftest.py.md(61)/ai_pipeline(89+88) |
| R14 审计新发现 P1/P2 | 9 项 | ✅ 全部代码修复 + 99 例新测试锁定（零 flaky） |
| 测试缺口补齐 | 7 代理 / 99 例 | ✅ A auth_user 16 + B va_scoring 12 + C match_training 11 + D pay_mbr_notif 14 + E admin_kb 19 + F aip_beat 15 + G progress_notif 12 |
| 死代码清理 | 22 处 | ✅ 删 1 死常量 + 3 硬编码接线常量 + 18 死导入（含 2 处孤儿脚手架块） |
| P3 文档同步 | 9 文档 25+ 处 | ✅ 本轮代码修复引发的全部文档滞后回写（含 API §1.8 错误码注册 4 码） |
| 系统性观察（不计缺陷） | 2 类 | ⚠️ 全项目 101 处未用导入（本轮清 22）/ ~60 个声明未用的响应 Schema（routers-return-dicts 设计特性）→ Phase 2 对齐项 |
| 全量回归 | 598 用例 | ✅ 最终 597 passed / 0 failed / 1 skipped（2 次运行收敛，见 §七） |
| 测试侧契约滞后修复 | 1 项 | ✅ R14-Conc-Test-1（test_concurrency 判定仍按旧 None 契约 + UTC 清键 + bonus 池漏清，见 §7.1） |

**结论**：R14 完成"重建 → 审计 → 修复 → 补测 → 清理 → 同步 → 回归"全链路。9 项 P1/P2 生产缺陷全部修复并由 99 例新测试锁定（其中 R14-AIP-N1 为状态机守卫交互导致通知分支不可达的回归型缺陷，A/B 对照探针实证）；两份高乱码文档（payment 158 行、ai_pipeline 177 行）完成证据链重建，存疑填充逐项留档。死代码清理与 P3 同步后全量回归全绿即达成"连续两轮零 P2+"的第一轮。

## 二、U+FFFD 文档重建（7 份，611 处 → 0）

### 2.1 重建清单与策略

| 文档 | 乱码行数 | 策略 | 行数变化 |
|------|---------|------|---------|
| 01-auth/backend.md | 68 | 主会话整段重建（同构模板 + 实际实现） | 918 → 939 |
| 07-training_advice/backend.md | 89 | 1:1 行内替换 | 1416 → 1428 |
| 08-progress_analysis/backend.md | 73 | 1:1 行内替换（样例区） | 1839 → 1847 |
| 09-gamification/backend.md | 149 | 1:1 + 5 处粘连行拆分 | 1298 → 1305 |
| 11-payment/backend.md | 158（前半 80 + 后半 78） | 两代理分区 1:1（互不越界断言） | 1657 → 1660（含头部注记 +3） |
| 13-infrastructure/conftest.py.md | 61 | 子代理重建 | 455 → 461 |
| 13-infrastructure/ai_pipeline.md | 177（前半 89 + 后半 88） | 前半 A1 1:1；后半 R14-07 先例拆粘连行重建 | 1134 → 1176（1168 + 注记 2 + §5.2/§5.5/§8 三处 R14 契约注记） |

### 2.2 重建证据链（ai_pipeline.md 重点）

- 文档仅 2 个 git 提交（784ff4b=v0 1107 行/302 FFD、e2f702e HEAD 1134 行/301 FFD），双双损坏 → **无干净基线可回溯**，重建只能依赖推断。
- b5e0e1a 代码 blob（report_generator/circuit_breaker/progress）FFD=0 但是**另一套实现**（tuple 返回、dict issues、静态熔断器 API）→ 文档 §5.4-§5.6 样例为纯设计稿，从未对应任何已提交代码；`app/services/ai_pipeline_service.py` 在 git 历史中从未存在（§5.5 样例同为设计稿）。
- 重建源优先级（验证有效）：**03-模块详细设计.md 逐字原文 > 同文档已重建兄弟行/同构模板 > 代码词汇锚点**（git blob 仅作词汇来源，不作结构来源）。
- 契约点双轨：近轮契约变更（R12-Prog-1→R13-AIP-1 快照 Celery 投递、R14 修复）按实际实现优先回写到注记层；历史设计稿样例保持原形态不回退（R13-P3 注记已声明"静态方法形态已废弃，样例保留作历史参考"）。
- 关键证据：03-模块详细设计.md L1406-1411 验证清单原文与 L1115 逐字吻合（平息 R13 注记压缩转写 `3-5/6-7` 与 resolver 语料 `与 ` 的冲突）；L1371 `两个 chain 并行后 join` 确定 L610 填充为 `后 `（推翻早前 `执行→` 的中间记录）；L1360 `Step 3-5 与 Step 6-7 可并行执行` 佐证注释行文。
- 补丁纪律：断言先行（旧行 repr 比对 + 行数 + BOM + 纯 LF + 无尾换行 + L1-591 字节不变 + 栅栏偶校验）、单次落盘、失败不落盘；执行后字节级独立复核（FFFD bytes=0、CRLF=0）+ git diff 行集核对（差异行恰为重建行集）。

### 2.3 存疑清单（低置信填充，供 R15 审查重点核验）

**ai_pipeline.md（20 处，证据：tmp/r14_aip_patch2.py UNCERTAIN 字典 + result 文件）**

| 行 | 填充类型 | 依据 |
|----|---------|------|
| 629 | `功， vs 功、`（顿号/逗号取舍） | 同构模板 |
| 638 | `器（§5.4 标题 = 报告生成器）` | 同构推断 |
| 669 | `→` 无空格箭头 | A1 L525 `输出→JSONB` 同构 |
| 672 | `果（提取各步骤结果）` | 语义推断 |
| 711 | 仅换行（注释=触发级联） | b5 L68 同构，未补"链" |
| 774 | `回 `（请返回 JSON） | 语义 |
| 805 | `别 `（= 共识别，total_shots 语义） | 语义推断 |
| 815 | `——` 与"表" | L825 同行族 training_plan 佐证 |
| 831 | `——` 与"的"（模块的 Celery） | 同构 |
| 832 | `相关` 与 `——` | L928 `）——Redis` 同构 |
| 899 | `态（更新任务状态）` | 同构 |
| 975/984 | docstring 句号行尾 | 多行 docstring 首行风格 |
| 989 | `态: ` 冒号后无空格 | 同构 |
| 1019 | `式*/功//。` 复合 | 同构 |
| 1117 | `后`（失败后 WS push） | 与同行"失败后"一致 |
| 1127 | `由*与供`（闭合粗体） | 同构 |
| 1130 | `后与款`（失败后/不退款） | 同行族 |
| 1131 | `链与线`（级联链/流水线） | 同行族 |
| 1134 | `）*/§5/束/续/。` 七处复合 | 同构收尾 |

**11-payment/backend.md（11 处，证据：tmp/r14_pay_patch{1,2}.py REBUILD 表）**：以破折号/箭头语义连接符行为主——L1（`—` 后端垂直切片设计）、L42、L147（回调流程连接）、L304（幂等返回）、L686（下单流程）、L1626 等；其余 147 处为 pairdict（334 对验证语料）+ 同构模板机械匹配（高置信）。

**注**：存疑填充不代表错误——为 R15 审查提供定向核验坐标；重建注记不构成审查豁免。

## 三、R14 生产缺陷修复（9 项）

| 编号 | 级别 | 问题 | 修复 | 锁定测试 |
|------|------|------|------|---------|
| R14-AIP-N1 | P1 | run_pipeline_async Step 10 后先行 `transition_task_status("completed")`，致 `on_task_complete` 内部二次转换被 `TASK_TRANSITIONS["completed"]=set()` 终态空集拒绝 → R13-AIP-2 完成通知分支（在线 WS / 离线 DB 落库）**永不可达**（R12-VA-2 与 R13-AIP-2 两轮修复交互引入的回归） | 移除先行转换，`processing→completed` 单点收口于 `on_task_complete` | test_r14_f（离线落库/在线 WS/终态幂等 3 例，A/B 对照探针实证因果：先行转换存在时通知落库=0，移除后=1） |
| R14-Pay-N1 | P1 | `quota:bonus` 有写入方（支付回调 INCR+90d TTL）**无消费方**——模块详设 §2.11 BR-2"分析包→增加额外额度"全链路空转，用户购买分析包后可用次数实际未增加 | 消费链补齐：`_check_free_quota` 返回 `free/bonus` 来源（免费耗尽→原子 DECR bonus，负数回补防并发超扣）；`consume_analysis_quota` 同型；`create_task` 写 `quota:src:{task_id}` 标记（24h TTL） | test_r14_d + test_r14_b |
| R14-Pay-N1-d1 | P2 | 退款幂等方案 getdel 即删，"已退还"与"无标记历史任务"不可区分 → bonus 任务二次退款误走 free 回退扣减日额度 | 墓碑标记 `refunded`（保留 TTL）先行改写，二次调用直接返回 | test_r14_d（墓碑幂等/分池回退） |
| R14-Pay-N2 | P2 | 24h-7d 窗口 `full_reversal` 分支直接放行全额退款，绕过 API §12 "≤50%" 限额 | 该窗口全额退款改拒绝（400），仅允许部分退款；`full_reversal` 值废弃（Model 注释同步） | test_r14_d + 探针（probe_r14_pay_refund_window.py） |
| R14-B4-1 | P2 | progress"技术指标不存在"误用 40420 与 training"训练方案不存在"同码双义（API §1.8 命名空间要求业务 code 唯一，前端按 code 差异化提示必错） | 新码 40415 `ERR_METRIC_NOT_FOUND`；training 域 40420/40421/40422 语义不变；API §1.8 补注册 4 码 | test_r14_g |
| R14-Gam-N1 | P2 | `add_points` 契约仅 flush（09-gam 切片 §5 注记 2），4 个调用方（match_data/scoring/va feedback/va share）缺 commit 收口 → 积分与自动打卡随 session 结束回滚丢失 | 4 处补 `await db.commit()` | test_r14_b/c（跨模块积分链断言） |
| R14-User-1 | P1 | `process_account_deletions` 仅置 `status="deleted"`：PII（phone/openid/nickname）永久留存，且 phone/openid 继续占据部分唯一索引 → **已注销手机号/微信号无法重新注册**；API §3.6 规则 3 / 02-user 切片 §9 BR-4 七步级联未实现 | BR-4 级联补齐：匿名化（释放唯一索引）→ 视频标记删除 → 报告匿名化保留（user_id 保留供训练）→ 非终态订阅取消 → status=deleted → Redis 清理（big_data:user/notif:unread，失败不回滚）→ 审计日志 | test_r14_a |
| R14-User-2 | P2 | `cancel_deletion` 缺 API §3.10 业务规则 3 要求的撤销审计日志 | 补 AuditLog（user 侧操作，admin_id 为空） | test_r14_a |
| R14-VA-1 | P3 | submit_feedback 调用不存在的 `FileService.archive_for_training`（AttributeError 吞噬后仅 warning）——数据飞轮归档空转 | 移除死调用；`feedback_record.status=archived/manual_review` 落库即飞轮归档语义（与切片 Model 注释一致）；Phase 2 接入点注释留档 | test_r14_b |
| R14-KB-1 | P2 | `init_knowledge_base` `pop("category_code")` 原地删除模块级常量 PROBLEMS → 同进程第二次调用在幂等跳过逻辑之前抛 KeyError | 改读取 + 字典推导构造（常量不可变） | test_r14_e（同实例二次调用幂等） |

## 四、测试缺口补齐（7 代理 99 例）

| 代理 | 文件 | 例数 | 覆盖重点 |
|------|------|------|---------|
| A | test_r14_a_auth_user.py | 16 | 注销七步级联 / 撤销审计 / 飞轮反馈积分 commit 收口 |
| B | test_r14_b_va_scoring.py | 12 | quota 分池（free/bonus 边界）/ 退款窗口 422/400 / feedback 状态落库 |
| C | test_r14_c_match_training.py | 11 | match +5 积分 commit / 记录积分 / 训练方案 40420/40422 差异化 |
| D | test_r14_d_pay_mbr_notif.py | 14 | 退款墓碑幂等 / bonus 回退 / 回调重放 / 通知落库 |
| E | test_r14_e_admin_kb.py | 19 | create 审计 target_id / KB 脚本幂等重入 / admin 筛选 |
| F | test_r14_f_aip_beat.py | 15 | 完成通知可达性（R14-AIP-N1 回归守卫）/ 熔断 half_open / was_unavailable 模板回退 / beat 三分支 |
| G | test_r14_g_progress_notif.py | 12 | 40415 差异化 / 快照幂等重入 / period 滚动窗口边界 / 通知三态 |

全部 99 例单文件运行全绿（G 代理含 2 次全量复跑确认无 flaky）；既有 499 基线用例在死代码清理后针对性冒烟（4 文件 138 例）全绿。

### 4.1 G 代理观察项（非缺陷，留档）

1. 进度快照幂等重入返回**当前调用值**而非库内首版（同 report_id 重复触发时 metrics 为最新 result_data）——语义与"幂等"字面有偏差，实现自洽，留观察。
2. `notif:subscribed:{uid}` 为只写不读的空转键（无消费方）。
3. conftest Redis 清理清单不含 `notif:*`——通知计数测试须自行清键防跨测试污染（schema 每测试 DROP/CREATE 使用户 id 复用）。
4. `list_snapshots` period 参数为**滚动窗口**（now-N 至 now）而非日历锚定窗口——测试断言须按滚动口径计算期望集（嵌套窗陷阱：月窗⊂季窗⊂年窗）。

### 4.2 审计描述修正（R14 审计自身标注错误，以 grep 实证为准）

1. **B4-4**："训练建议未持久化"——实际 advice 持久化正常（`generate_advice_task` 落库 training_plan），审计描述与实现归属不符，未构成缺陷。
2. **ND-4**：SAVEPOINT（`begin_nested`）实际位于 `gamification_service.py`，审计标注的 `notification_service` 归属错误。
3. **7d-out 退款**：超 7 天窗口实际返回 **422**（非审计描述的 400），代码与 API §12 表述一致。

## 五、死代码清理（22 处）

### 5.1 清理明细

| 类型 | 明细 |
|------|------|
| 死常量删除 | `RateLimits.USER_EXPORT = "1/month"`（app/core/limiter.py，0 代码引用 + 0 文档引用；月度导出限额实际由 UserService.export_data 服务层 Redis 计数实现，02-user 切片 L1042 "Redis 计数"一致） |
| 硬编码接线常量 | admin router L36 `"5/minute"` → `RateLimits.ADMIN_LOGIN`；va router L69 `"10/hour"` → `RateLimits.AI_ANALYSIS`；va router L175 `"5/day"` → `RateLimits.SHARE`（值完全一致，行为不变，消除 magic string） |
| 生产死导入 | tasks.py（settings/PipelineStep）；report_generator.py（datetime/timezone/AsyncSession）；admin router（require_model_admin/AppException/ERR_UNAUTHORIZED/AdminLoginResponse/dt_time）；va router（AsyncSession/get_db） |
| 测试死导入 | conftest.py（asyncio/datetime/timezone/pytest/ConsentLog）；test_cascade_chains（datetime 三连/User/Order/PaymentRecord/MembershipTierConfig/三 Service 导入行）；test_supplements_p1（CheckInRecord/SystemConfig）；test_video_analysis（httpx 行 + L606-613 孤儿脚手架块——被废弃 JWT/service 直调方案残留）；test_r14_e（desc） |

**保留项（有意保留，非死代码）**：limiter.py `RateLimitExceeded`（跨文件 re-export，app/main.py 引用）；test_cascade_chains L357 `app` 导入（`# noqa: F401` 显式任务注册副作用）。

### 5.2 安全性验证

- `from app.core.celery import celery_app` 导入链注册**全部 37 张表**（order/payment_record/match/subscription/membership_tier_config/admin_user 等 10 项逐一确认）→ 测试文件未用模型导入无注册副作用，可安全删除。
- 全部删除目标经 AST 分析 + 词边界 rg 双重验证（覆盖 Name/Attribute/字符串注解/装饰器/别名导入），无误删。

### 5.3 系统性观察（P3/Phase 2 对齐项，不属本轮清理）

1. **全项目 101 处未用导入**（本轮清理 22 处后余 ~77，其中 2 处为有意 re-export）——证据：tmp/r14_unused_scan.txt。建议 Phase 2 引入 ruff/flake8 F401 到 CI。
2. **~60 个声明未用的响应 Schema**（auth 3/gamification 7/knowledge_base 10/match_data 3/payment WechatNotifyResponse/progress 15/scoring 11/training 10/video_analysis 13）——源于"API 详设声明响应 Schema、路由实际返回 dict（success() 包装）"的系统性设计缺口，涉及全部切片，属 Phase 2 契约对齐决策（补 response_model 或删声明），不做单点清理。

## 六、P3 文档同步（9 文档 25+ 处）

| 文档 | 同步内容 |
|------|---------|
| API 详细设计 §1.8 | 补注册 40415/40420/40421/40422 + R14-B4-1 注记 |
| 08-progress §5.5 | 快照触发链回写 R13-AIP-1 当前基线（内联 await → Celery 投递，与 report_generator L287-302 逐字一致）；§5 错误码 40420→ERR_METRIC_NOT_FOUND；文末补 R14 同步变更表 |
| 13-infrastructure/ai_pipeline.md | §5.2 注记扩展（R14-AIP-N1 转换单点收口 + R14-Pay-N1 退款分池/墓碑）；§5.5 注记（refund 签名扩展）；§8 注记（R14 新增测试 14 + 15 例覆盖清单） |
| 11-payment §5 | 退款窗口样例回写 R14-Pay-N2（full_reversal 分支 → 拒绝）；Model reversal_type 注释（代码 + 文档同步：full/partial） |
| 05-match_data §5 | add_points 补 commit 收口行（R14-Gam-N1） |
| 04-scoring §5 | 同上（含切片 §5 注记 2 引用） |
| 10-membership §5 | consume_analysis_quota 全量回写（has_quota 前置检查移除 / R13-Mbr-N1 yyyymmdd 键 / bonus 回退分支）；_get_used_count 读取键同步 yyyymmdd（原 isoformat 读取方永远读不到扣减计数） |
| 02-user §5/§9 | cancel_deletion 补审计日志；process_account_deletions 注记改"已实现"+ 实现侧差异清单（唯一索引释放/非终态订阅/Redis 键/审计写入）+ 样例 Redis 键与审计步骤同步 |
| 03-video_analysis §5 | _check_free_quota 签名 `-> str` + bonus 分支；create_task quota_source + quota:src 标记；启动失败退额度注记传 task_id；feedback/share 两处 add_points commit |

全部同步后验证：13 份触碰文档 FFD=0、代码围栏偶数、BOM 保持（ai_pipeline 无尾换行 / payment 有尾换行，各自原格式不变）。

## 七、全量回归

单进程串行运行（避免并发批次 DB schema 互踩）；PYTHONUNBUFFERED + `--timeout=120` 防护；远程 VM PostgreSQL/Redis（192.168.40.147）。总计 598 用例 = R13 基线 499 + R14 新增 99。

| 运行 | 触发条件 | 结果 | 结论 |
|------|----------|------|------|
| 第 1 次 | 死代码清理 + P3 文档同步完成后 | 596 passed / 1 failed / 1 skipped（27:24） | 唯一失败 = R14-Conc-Test-1（test_concurrency.py::test_free_quota_concurrent_increment，assert 0 == 3）——测试侧契约滞后，非生产缺陷（见 §7.1） |
| 第 2 次 | R14-Conc-Test-1 修复后 | **597 passed / 0 failed / 1 skipped（27:31）** | 全量收敛：598 用例全部通过（唯一 skip 为 test_admin 既有跳过项）；99 例 R14 新测试与 499 例基线在全量上下文同时验证闭环 |

### 7.1 R14-Conc-Test-1（第 1 次全量唯一失败，根因实证）

- **现象**：`assert success_count == 3` 实得 0——3 次并发调用全部判为失败。
- **根因**：R14-Pay-N1 将 `_check_free_quota` 返回值契约从 `None`（成功）改为字符串来源标记 `"free"`/`"bonus"`（供退款按来源退还），测试 L175 仍以 `r is None` 判成功 → 成功调用全部漏计。属生产契约变更后测试未同步（R13-Test-N3 同型），死代码清理与 P3 同步均非诱因。
- **附带两个同点位潜在缺陷**（同批修复）：
  1. L161 用 **UTC 日期**清键而服务用 **CST（UTC+8）** yyyymmdd——UTC 16:00-24:00（即 CST 凌晨 00:00-08:00）时段清理键与服务键错位（R13-Admin-Test-1/R14-VA-2 同型）；改为 `timezone(timedelta(hours=8))`。
  2. 清理未覆盖 `quota:bonus:{user_id}` 池——bonus 有跨测试残留时"成功"消耗 bonus、日计数回滚，会误伤 L183 `count == success_count` 断言；setup/teardown 补删双键。
- **修复与验证**：成功判定改 `r in ("free", "bonus")`；隔离复跑该文件 4/4 passed（12.24s）；随后第 2 次全量 597 全绿。
- **断言未弱化**：`count == success_count` 与 3 并发语义保留（free/bonus 双耗尽路径已由 test_r14_b 覆盖，本测试聚焦并发递增原子性）。

## 八、结论与 Round 15 计划

1. **R14 闭环完成**：9 项 P1/P2 生产缺陷修复 + 99 例测试锁定 + 22 处死代码清理 + 7 份乱码文档重建（611 处 FFD → 0）+ 9 文档 P3 同步 + 1 项测试侧契约滞后修复（R14-Conc-Test-1，第 1 次全量唯一失败根因）→ 第 2 次全量 597/598 全绿（1 skip 既有）。
2. **Round 15 计划**：按 R14 基线执行三方对比审计（重建注记不构成豁免，§2.3 存疑清单 31 处为定向核验坐标）；目标与 R16 共同达成"连续两轮零 P2+"。
3. **风险提示**：
   - R12+R13+R14 全部修复尚未 git commit（86+ 文件），建议本报告输出后执行里程碑 commit。
   - 测试环境依赖远程 VM PostgreSQL/Redis（192.168.40.147）；conftest DROP/CREATE 每测试重建 schema，必须单进程串行运行。
   - `notif:*` Redis 键不在 conftest 清理清单（G 观察 3），通知计数断言类测试自行清键。
   - 系统性观察 2 类（未用导入 / 未用 Schema）建议 Phase 2 引入 lint 门控与契约对齐决策。
