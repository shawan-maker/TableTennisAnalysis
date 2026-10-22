# 第十五轮 API 端点级一致性审查报告

> **审查日期**：2026-10-16  
> **审查维度**：API 端点级一致性  
> **审查代理**：第十五轮 API 端点级审查代理  
> **基准文档**：`docs/04详细设计/05-API详细设计.md`（v1.3）、`docs/06垂直模块前后端切片设计/00-垂直切片设计总览.md`  
> **切片文档**：`03-video_analysis/backend.md`、`11-payment/backend.md`、`07-training_advice/backend.md`、`13-infrastructure/admin.md`  
> **前十四轮累计修复**：674 项  

---

## 1. 审查范围

本轮审查聚焦 API 设计文档与后端切片之间的端点级一致性，覆盖以下检查项：

| 编号 | 检查项 | 类别 |
|------|--------|------|
| 1-5 | 第十四轮修复验证（回归检查） | 修复验证 |
| 6 | admin 端点实现完整性（§19 × admin.md） | 深层检查 |
| 7 | 响应 Schema 字段一致性（API 设计响应体 vs 切片 Pydantic Model） | 深层检查 |
| 8 | POST/PUT/PATCH 请求体定义完整性 | 深层检查 |
| 9 | 分页参数命名统一性（page/page_size） | 深层检查 |
| 10 | 认证依赖一致性（get_current_user / require_membership） | 深层检查 |
| 11 | share_router HTMLResponse 返回类型 | 深层检查 |
| 12 | 端点总数验证（79 + 17 = 96） | 深层检查 |
| 13 | §1.8 端点级业务错误码覆盖度 | 深层检查 |

---

## 2. 第十四轮修复验证（5/5 通过）

| 编号 | 修复项 | 验证结果 | 依据 |
|------|--------|----------|------|
| 1 | share limiter 5/day | ✅ 通过 | `03-video_analysis/backend.md` L1224：`@limiter.limit("5/day", key_func=lambda r: r.state.user)` |
| 2 | §14a 首页聚合路径修正 | ✅ 通过 | `00-垂直切片设计总览.md` L92：「无独立后端端点」，前端 React Query 并发请求多个已有端点聚合 |
| 3 | §1.2 page_size 上限（用户端 50 / 管理端 100） | ✅ 通过 | `05-API详细设计.md` L46：「`page_size` 默认 20，用户端最大 50，管理端最大 100」 |
| 4 | §1.7 通用错误码 400(40000) + 502(50200) | ✅ 通过 | `05-API详细设计.md` L96：`400 / 40000`；L97：`502 / 50200` |
| 5 | 总览 L92 前端聚合并无独立后端端点 | ✅ 通过 | 总览 L92 明确声明「无独立后端端点」，与 API 设计 §14a 一致 |

**结论**：第十四轮 5 项修复全部通过回归验证，无回退。

---

## 3. 深层检查发现

### P2-1：ReportDetailResponse 缺少 task_uuid 字段

| 属性 | 值 |
|------|-----|
| **优先级** | P2 |
| **位置** | API 设计 §4.6 L1161-1162 vs `03-video_analysis/backend.md` L443-453 |
| **状态** | 🔴 未修复 |

**问题描述**：

API 设计 §4.6 `GET /video-analysis/reports/{report_id}` 响应体包含 `task_uuid` 字段：

```json
// API 设计 L1161-1162
"task_id": 1001,
"task_uuid": "task_a1b2c3d4-e5f6",
```

切片 `ReportDetailResponse` Pydantic Model 未定义 `task_uuid` 字段：

```python
# 03-video_analysis/backend.md L443-453
class ReportDetailResponse(BaseModel):
    id: int
    task_id: int
    created_at: datetime
    is_llm_generated: bool
    result_data: Optional[dict[str, Any]] = None
    report_text: Optional[dict[str, Any]] = None
    annotated_video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    report_images: Optional[dict[str, Any]] = None
    model_config = {"from_attributes": True}
```

**影响**：API 设计 §4.4 说明（L919-921）明确 `task_uuid` 用于对外暴露（分享链接、CDN 路径、WebSocket 推送），前端在报告详情页引用任务时应使用 `task_uuid`。切片 schema 缺失该字段将导致前端无法获取 `task_uuid`。

**修复建议**：在 `ReportDetailResponse` 中添加 `task_uuid: str` 字段。

---

### P2-2：ShareResponse 字段名不一致

| 属性 | 值 |
|------|-----|
| **优先级** | P2 |
| **位置** | API 设计 §4.10 L1328 vs `03-video_analysis/backend.md` L480-482 |
| **状态** | 🔴 未修复 |

**问题描述**：

API 设计 §4.10 `POST /video-analysis/reports/{report_id}/share` 响应体使用 `share_card_url`：

```json
// API 设计 L1328
"share_card_url": "https://cdn.pingpongai.com/images/share-cards/1/card.jpg",
```

切片 `ShareResponse` Pydantic Model 使用 `card_image_url`：

```python
# 03-video_analysis/backend.md L480-482
class ShareResponse(BaseModel):
    share_url: str
    card_image_url: Optional[str] = None
    expire_at: datetime
```

切片前端类型定义使用 `share_card_url`（与 API 设计一致）：

```typescript
// 03-video_analysis/frontend.md L220
createShare: (reportId: number) => Promise<{ share_url: string; share_card_url: string | null }>
```

**影响**：后端返回 `card_image_url`，但 API 设计和前端期望 `share_card_url`，前端接收到的分享卡片 URL 字段名不匹配，将导致 `share_card_url` 为 `undefined`。

**修复建议**：将切片 `ShareResponse.card_image_url` 重命名为 `share_card_url`，同步修改 Service 层返回值构造（L1030、L1048）。

---

### P2-3：退款状态值不一致

| 属性 | 值 |
|------|-----|
| **优先级** | P2 |
| **位置** | API 设计 §12.4 L3173/L3186 vs `11-payment/backend.md` L515/L1274 |
| **状态** | 🔴 未修复 |

**问题描述**：

API 设计 §12.4 退款流程定义 RefundRecord 初始状态为 `processing`，终态为 `success`/`failed`：

```json
// API 设计 L3173
"refund_status": "processing",

// API 设计 L3186
3. 创建 refund_record（order_id, refund_amount, reason, status=processing）

// API 设计 L3188
4. 退款成功回调 → refund_record.status=success

// API 设计 L3190
5. 退款失败 → refund_record.status=failed
```

切片 RefundRecord Model 默认值为 `pending`，Service 返回值也是 `pending`：

```python
# 11-payment/backend.md L515
status: Mapped[str] = mapped_column(String(20), default="pending")

# 11-payment/backend.md L1272-1274
return RefundResponse(
    order_id=order.id,
    refund_status="pending",
    ...
)
```

**影响**：前端按 API 设计期望退款状态为 `processing`，但后端返回 `pending`，状态判断逻辑（如显示"退款处理中"）将失效。同时 RefundRecord 状态枚举值不一致（API 设计：processing/success/failed，切片：pending/...）。

**修复建议**：
1. 切片 RefundRecord `status` 默认值改为 `"processing"`
2. 切片 RefundResponse `refund_status` 返回值改为 `"processing"`
3. 同步修改 RefundRecord 状态流转逻辑：`processing` → `success`/`failed`

---

### P3-1：GET /training/templates 请求参数表缺少分页参数

| 属性 | 值 |
|------|-----|
| **优先级** | P3 |
| **位置** | API 设计 §8.3 L2213-2215 vs `07-training_advice/backend.md` L1194-1195 |
| **状态** | 🟡 未修复 |

**问题描述**：

API 设计 §8.3 `GET /training/templates` 请求参数表仅定义 `problem_id`，未包含分页参数：

```
// API 设计 L2213-2215
| 参数 | 位置 | 类型 | 必填 | 描述 |
| problem_id | query | string | N | 按问题筛选 |
```

但响应体为分页格式（L2224-2226）：

```json
"total": 5,
"page": 1,
"page_size": 20,
```

切片路由函数已实现分页参数：

```python
# 07-training_advice/backend.md L1194-1195
page: int = Query(default=1, ge=1),
page_size: int = Query(default=20, ge=1, le=50),
```

**影响**：API 设计文档与切片实现不一致。开发者参照 API 设计可能遗漏分页参数，前端可能不知道可传 `page`/`page_size`。

**修复建议**：API 设计 §8.3 请求参数表补充 `page`（query, int, N, 页码）和 `page_size`（query, int, N, 每页条数）两行。

---

### P3-2：API 设计 §4.7 ReportListItem task_id 示例值类型错误

| 属性 | 值 |
|------|-----|
| **优先级** | P3 |
| **位置** | API 设计 §4.7 L1224 vs §4.4 L919/L1096 |
| **状态** | 🟡 未修复 |

**问题描述**：

API 设计 §4.4 说明（L919）明确 `task_id` 类型为 `int`：

> `task_id`（`int`）：数据库自增主键，用于内部关联和数据库查询。

§4.4 TaskListItem 响应示例（L1096）正确使用 int：

```json
"task_id": 1001,
```

但 §4.7 ReportListItem 响应示例（L1224）使用了字符串：

```json
"task_id": "task_xxx",
```

切片 `ReportListItem` 正确定义为 int（L435）：

```python
class ReportListItem(BaseModel):
    id: int
    task_id: int
```

**影响**：API 设计文档内部不一致，前端开发者可能误将 `task_id` 当作字符串处理。

**修复建议**：API 设计 §4.7 L1224 的 `"task_id": "task_xxx"` 改为 `"task_id": 1001`。

---

### P3-3：get_report_detail 返回未文档化 is_readonly 字段

| 属性 | 值 |
|------|-----|
| **优先级** | P3 |
| **位置** | API 设计 §4.6 L1155-1190 vs `03-video_analysis/backend.md` L818-821 |
| **状态** | 🟡 未修复 |

**问题描述**：

API 设计 §4.6 `GET /video-analysis/reports/{report_id}` 响应体未定义 `is_readonly` 字段。

切片 Service 方法 `get_report_detail` 在运行时动态添加了 `is_readonly` 字段：

```python
# 03-video_analysis/backend.md L815-821
# 降级用户只读检查 (BL-15 修复)
redis = await get_redis()
readonly = await redis.get(f"downgrade:report:readonly:{user_id}")
is_readonly = readonly is not None

data = ReportDetailResponse.model_validate(report).model_dump()
data["is_readonly"] = is_readonly
return data
```

**影响**：后端返回了 API 设计未定义的字段，属于 Schema 扩展。虽然功能上合理（BL-15 降级用户只读检查），但 API 设计文档应同步补充。

**修复建议**：API 设计 §4.6 响应体补充 `is_readonly`（boolean）字段定义，并添加说明：「降级用户只读标记，`true` 表示用户处于降级状态，报告内容只读」。

---

## 4. 通过项汇总

| 编号 | 检查项 | 结果 | 依据 |
|------|--------|------|------|
| ✅1 | 端点总数验证 | 通过 | 79 业务端点（总览 L846）+ 17 admin 端点（§19 定义）= 96 |
| ✅2 | admin 17 端点实现完整性 | 通过 | `13-infrastructure/admin.md` 定义全部 17 端点（16 个 Phase 1 活跃 + 1 个 Phase 2+ 占位注释），与 API 设计 §19.2-§19.6 完全对应 |
| ✅3 | §1.7 通用错误码 | 通过 | 9 条全局错误码（40100/40101/40300/40400/42200/42900/40000/50200/50000），覆盖认证/权限/资源/校验/限流/业务/第三方/内部错误 |
| ✅4 | §1.8 端点级业务错误码 | 通过 | 12 条端点级错误码覆盖视频分析（40010/40410/40412/42910）、记分牌（40411/40910）、比赛记录（40413/40911/42210）、分享（40414）、通用（40011/40310） |
| ✅5 | 分页参数命名统一 | 通过 | 全部端点使用 `page`/`page_size`，默认 20，用户端最大 50，管理端最大 100 |
| ✅6 | share_router HTMLResponse | 通过 | `03-video_analysis/backend.md` L1250 `@share_router.get("/share/{share_token}", response_class=HTMLResponse)` 与 API 设计 §4.11 一致 |
| ✅7 | 认证依赖 | 通过 | 所有需认证端点均配置 `get_current_user` 或 `require_membership("member")` 依赖；公开端点（login/share）无认证依赖 |
| ✅8 | 限流配置 | 通过 | 全局默认 100/min，AI 分析创建 10/hour，报告分享 5/day（L1224 确认），auth login 10/min |
| ✅9 | POST/PUT/PATCH 请求体定义 | 通过 | 所有需请求体的端点均有 Request Body JSON 示例和字段说明 |
| ✅10 | 404 错误消息规范 | 通过 | 遵循 `{资源名}不存在` 格式（§1.7 L100 规范 + 各端点错误情况表逐一定义具体消息） |

---

## 5. 问题汇总

| 编号 | 优先级 | 问题 | 位置 | 状态 |
|------|--------|------|------|------|
| P2-1 | P2 | ReportDetailResponse 缺少 task_uuid 字段 | API §4.6 vs 切片 L443-453 | 🔴 未修复 |
| P2-2 | P2 | ShareResponse 字段名不一致（share_card_url vs card_image_url） | API §4.10 L1328 vs 切片 L480-482 | 🔴 未修复 |
| P2-3 | P2 | 退款状态值不一致（processing vs pending） | API §12.4 L3173 vs 切片 L515/L1274 | 🔴 未修复 |
| P3-1 | P3 | GET /training/templates 请求参数表缺少分页参数 | API §8.3 L2213-2215 vs 切片 L1194-1195 | 🟡 未修复 |
| P3-2 | P3 | API §4.7 ReportListItem task_id 示例值类型错误（string vs int） | API §4.7 L1224 | 🟡 未修复 |
| P3-3 | P3 | get_report_detail 返回未文档化 is_readonly 字段 | API §4.6 vs 切片 L818-821 | 🟡 未修复 |

**统计**：P0×0 | P1×0 | P2×3 | P3×3 | 共 6 项

---

## 6. 修复优先级建议

1. **P2-2（ShareResponse 字段名）**：前后端字段名不匹配将直接导致前端 `share_card_url` 为 `undefined`，建议优先修复
2. **P2-3（退款状态值）**：状态值不一致影响前端退款流程状态判断，建议与 P2-2 同步修复
3. **P2-1（task_uuid 缺失）**：前端无法获取 `task_uuid` 构建分享链接和 CDN 路径，建议尽快修复
4. **P3-1/P3-2/P3-3**：文档一致性问题，不影响运行时行为，可在下一轮文档同步中批量修复

---

> **审查结论**：第十五轮 API 端点级一致性审查发现 6 项问题（P2×3 + P3×3），无 P0/P1 级问题。第十四轮 5 项修复全部通过回归验证。端点总数、admin 端点实现、错误码体系、分页参数、认证依赖、限流配置等 10 项深层检查通过。核心风险集中在 3 项 P2 级 Schema/状态值不一致问题，建议在下一轮修复中优先处理。
