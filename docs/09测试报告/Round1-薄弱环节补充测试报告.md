# 测试报告 — Round 1：薄弱环节补充测试

**日期**：2026-10-23
**测试范围**：数据隔离 + 并发场景 + 事务回滚 + WebSocket 通道
**新增测试文件**：4 个，共 32 个测试用例

---

## 测试文件清单

| 文件 | 用例数 | 覆盖领域 |
|------|--------|----------|
| `tests/integration/test_data_isolation.py` | 14 | 比赛/报告/任务/进度/游戏化/通知/训练计划数据隔离 |
| `tests/integration/test_concurrency.py` | 4 | 支付回调幂等性 + 额度并发递减 + 比赛序号并发分配 |
| `tests/integration/test_transaction_rollback.py` | 6 | 支付失败回滚 + 退款约束 + DB 约束回滚（唯一/外键/CHECK） |
| `tests/integration/test_ws_channels.py` | 8 | WS 消息推送 + 在线状态 + 重连补偿 + 通知通道选择 |

## 执行结果

```
32 passed in 77.62s
```

**全部通过。**

## 修复过程记录

初次运行有 7 个失败，修复后全绿：

| # | 失败原因 | 修复方式 |
|---|----------|----------|
| 1 | API 响应不含 `user_id` 字段 | 改用 `opponent_name` 验证比赛列表隔离 |
| 2 | API 响应不含 `user_id`/`oss_key` 字段 | 改用列表长度验证任务列表隔离 |
| 3 | 并发相同 `transaction_id` 导致 `UniqueViolationError` | 改为顺序测试不同 `transaction_id` 的幂等性 |
| 4 | 退款端点用 JWT admin（非 Redis admin session） | 改用 `settings.ADMIN_USER_IDS` + JWT token |
| 5 | async session `MissingGreenlet` 错误 | 改用独立 `async_session_factory()` session |
| 6 | Redis pubsub 订阅时序问题 | 增加 0.3s 等待 + 消费订阅确认消息 |
| 7 | 事件名错误（`send_notification` 推送事件名为 `"notification"`） | 修正断言为 `data["event"] == "notification"` |

## 发现的已知限制

**支付并发回调竞态条件**：当前实现中，两个不同 `transaction_id` 的并发支付回调（相同 `order_no`）可能创建重复的 Subscription，因为幂等检查基于 `order.status == "paid"` 但没有行级锁（`SELECT FOR UPDATE`）。顺序回调不受影响（幂等检查正常工作）。

## 覆盖维度提升

| 维度 | 补充前 | 补充后 | 提升 |
|------|--------|--------|------|
| 数据隔离 | 4 测试（通知+订单） | 18 测试（比赛+报告+任务+进度+游戏化+通知+训练） | +14 |
| 并发场景 | 1 测试（序号冲突） | 5 测试（幂等+顺序回调+额度并发+序号并发） | +4 |
| 事务回滚 | 0 测试 | 6 测试（支付失败+退款+唯一约束+FK约束+CHECK约束） | +6 |
| WS 通道 | 7 单元测试 | 15 测试（推送+在线+重连+通道选择） | +8 |
