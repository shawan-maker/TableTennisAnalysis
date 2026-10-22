# 第十六轮 API 端点级一致性审查报告

> **审查日期**：2026-10-16  
> **审查维度**：API 端点级一致性  
> **审查代理**：第十六轮 API 端点级审查代理  
> **基准文档**：`docs/04详细设计/05-API详细设计.md`（v1.3）、`docs/06垂直模块前后端切片设计/00-垂直切片设计总览.md`  
> **切片文档**：`03-video_analysis/backend.md`、`11-payment/backend.md`、`07-training_advice/backend.md`、`13-infrastructure/admin.md`  
> **前十五轮累计修复**：704 项  

---

## 1. 审查范围

本轮审查聚焦 API 设计文档与后端切片之间的端点级一致性，覆盖以下检查项：

| 编号 | 检查项 | 类别 |
|------|--------|------|
| 1-3 | 第十五轮 P2 修复验证（回归检查） | 修复验证 |
| 4-6 | 第十五轮 P3 遗留项验证 | 修复验证 |
| 7 | §1.7 通用错误码 400(40000)+502(50200) 无回归 | 回归验证 |
| 8 | 端点总数验证（79 + 17 = 96） | 深层检查 |
| 9 | admin 17 端点实现完整性（§19 × admin.md） | 深层检查 |
| 10 | 响应 Schema 字段一致性（API 设计响应体 vs 切片 Pydantic Model） | 深层检查 |
| 11 | POST/PUT/PATCH 请求体定义完整性 | 深层检查 |
| 12 | 分页参数命名统一性（page/page_size） | 深层检查 |
| 13 | 认证依赖一致性（get_current_user / require_membership） | 深层检查 |
| 14 | share_router HTMLResponse 返回类型 | 深层检查 |
| 15 | 限流配置一致性 | 深层检查 |
| 16 | APIRouter prefix 叠加检查 | 深层检查 |

---

## 2. 第十五轮修复验证（2/6 已修复）

### 2.1 P2 项修复验证

| 编号 | R15 修复项 | 验证结果 | 依据 |
|------|-----------|----------|------|
| P2-1 | ReportDetailResponse 缺少 task_uuid 字段 | 🔴 未修复 | API §4.6 L1153 新增字段说明注释，但切片 `ReportDetailResponse`（L465-475）仍未添加 `task_uuid` 字段，Service `get_report_detail`（L828-844）未动态注入 |
| P2-2 | ShareResponse 字段名不一致（share_card_url → card_image_url） | ✅ 已修复 | API §4.10 L1330 响应体已改为 `"card_image_url"`，与切片 `ShareResponse`（L504）`card_image_url` 一致 |
| P2-3 | 退款状态值不一致（processing → pending） | ✅ 已修复 | API §12.4 L3175 `refund_status` 改为 `"pending"`，L3188 `status=pending`，与切片 L515 `default="pending"`、L1274 `refund_status="pending"` 一致 |

**P2-1 详细说明**：

API 设计 §4.6（L1153）新增了字段说明注释：

> **字段说明**：`task_id` 为任务整数主键，`task_uuid` 为任务唯一标识（字符串，VARCHAR(64)），两者并存。前端引用任务时使用 `task_uuid`，列表/详情展示中使用 `task_id`。

API §4.6 响应体（L1164）包含 `"task_uuid": "task_a1b2c3d4-e5f6"`。

但切片 `ReportDetailResponse` Pydantic Model（L465-475）仍未定义 `task_uuid` 字段：

```python
# 03-video_analysis/backend.md L465-475
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

切片 Service 方法 `get_report_detail`（L828-844）仅动态注入 `is_readonly`，未注入 `task_uuid`：

```python
# 03-video_analysis/backend.md L842-844
data = ReportDetailResponse.model_validate(report).model_dump()
data["is_readonly"] = is_readonly
return data
```

**结论**：API 侧新增字段说明注释属于文档改进，但切片 Pydantic Model 和 Service 方法均未同步，问题未实质修复。

---

### 2.2 P3 遗留项验证

| 编号 | R15 遗留项 | 验证结果 | 依据 |
|------|-----------|----------|------|
| P3-1 | GET /training/templates 请求参数表缺少分页参数 | 🟡 未修复 | API §8.3 L2215-2217 请求参数表仍仅 `problem_id`，未补充 `page`/`page_size`；切片 L1194-1195 已实现分页参数 |
| P3-2 | §4.7 ReportListItem task_id 示例值类型错误（string vs int） | 🟡 未修复 | API §4.7 L1226 仍为 `"task_id": "task_xxx"`（string），与 §4.4 L919 声明 `int` 及切片 L457 `task_id: int` 矛盾 |
| P3-3 | get_report_detail 返回未文档化 is_readonly 字段 | 🟡 未修复 | API §4.6 L1157-1192 响应体仍未定义 `is_readonly` 字段；切片 L843 仍动态注入 `data["is_readonly"] = is_readonly` |

**P3-1 详细说明**：

API §8.3 请求参数表（L2215-2217）：

```
| 参数 | 位置 | 类型 | 必填 | 描述 |
| problem_id | query | string | N | 按问题筛选 |
```

响应体（L2226-2228）为分页格式：

```json
"total": 5,
"page": 1,
"page_size": 20,
```

切片已实现分页参数（L1194-1195）：

```python
page: int = Query(default=1, ge=1),
page_size: int = Query(default=20, ge=1, le=50),
```

**P3-2 详细说明**：

API §4.4（L919）明确 `task_id` 类型为 `int`。§4.6 响应示例（L1163）正确使用 `"task_id": 1001`。但 §4.7 ReportListItem 响应示例（L1226）仍使用字符串：

```json
"task_id": "task_xxx",
```

切片 `ReportListItem`（L455-462）正确定义为 `task_id: int`。

**P3-3 详细说明**：

切片 `get_report_detail`（L837-843）动态注入降级用户只读标记：

```python
# 降级用户只读检查 (BL-15 修复)
redis = await get_redis()
readonly = await redis.get(f"downgrade:report:readonly:{user_id}")
is_readonly = readonly is not None

data = ReportDetailResponse.model_validate(report).model_dump()
data["is_readonly"] = is_readonly
return data
```

API §4.6 响应体（L1157-1192）未定义 `is_readonly` 字段，属未文档化的 Schema 扩展。

---

### 2.3 §1.7 通用错误码回归验证

| 编号 | 检查项 | 验证结果 | 依据 |
|------|--------|----------|------|
| 1 | 400 / 40000 业务校验失败 | ✅ 无回归 | `05-API详细设计.md` L96：`400 / 40000` |
| 2 | 502 / 50200 第三方服务不可用 | ✅ 无回归 | `05-API详细设计.md` L97：`502 / 50200` |

---

## 3. 深层检查发现

本轮深层检查覆盖端点总数、admin 端点实现、响应 Schema 字段一致性、请求体定义、分页参数、认证依赖、Router prefix 等 9 项，均通过验证，无新发现问题。

### 3.1 端点总数验证

| 检查项 | 结果 | 依据 |
|--------|------|------|
| 业务端点 79 个 | ✅ 通过 | `00-垂直切片设计总览.md` L846 声明 79 个业务端点 |
| Admin 端点 17 个 | ✅ 通过 | API §19.2-§19.6 定义 17 个管理端点，`13-infrastructure/admin.md` 全部实现 |
| 合计 96 个 | ✅ 通过 | 79 + 17 = 96，无新增/缺失端点 |

### 3.2 APIRouter Prefix 叠加检查

| 模块 | Router 定义 | 前缀叠加 | 结果 |
|------|------------|----------|------|
| video_analysis | `APIRouter(prefix="/video-analysis")` 挂载于 `/api/v1` | 单层 `/api/v1/video-analysis` | ✅ 通过 |
| payment | `APIRouter(prefix="/payment")` 挂载于 `/api/v1` | 单层 `/api/v1/payment` | ✅ 通过 |
| training_advice | `APIRouter(prefix="/training")` 挂载于 `/api/v1` | 单层 `/api/v1/training` | ✅ 通过 |
| share_router | `APIRouter()` 显式无 prefix，挂载于根 `/` | 路径 `/share/{share_token}` | ✅ 通过 |
| admin | `APIRouter(prefix="/admin")` 挂载于 `/api/v1` | 单层 `/api/v1/admin` | ✅ 通过 |

**结论**：所有 Router 均为单层 prefix，无双重叠加问题。`share_router` 显式无 `/api/v1` 前缀，与 API §4.11 `GET /share/{share_token}` 公开端点设计一致。

### 3.3 响应 Schema 字段一致性

本轮重点复核以下端点的响应字段一致性：

| 端点 | API 响应字段 | 切片 Pydantic Model | 结果 |
|------|-------------|---------------------|------|
| §4.6 GET /reports/{report_id} | id, task_id, task_uuid, created_at, is_llm_generated, result_data, report_text, annotated_video_url, cover_image_url, report_images | ReportDetailResponse: id, task_id, created_at, is_llm_generated, result_data, report_text, annotated_video_url, cover_image_url, report_images | ⚠️ 切片缺 task_uuid（P2-1），切片多 is_readonly（P3-3） |
| §4.10 POST /reports/{report_id}/share | share_url, card_image_url, expire_at | ShareResponse: share_url, card_image_url, expire_at | ✅ 一致 |
| §12.4 POST /orders/{order_id}/refund | order_id, refund_status, refund_amount_cents | RefundResponse: order_id, refund_status, refund_amount_cents | ✅ 一致 |
| §4.7 GET /reports | id, task_id, created_at, is_llm_generated, cover_image_url, report_summary | ReportListItem: id, task_id, created_at, is_llm_generated, cover_image_url, report_summary | ✅ 字段一致（但 API 示例 task_id 类型错误，P3-2） |
| §8.3 GET /training/templates | id, template_code, name, problem_id | 切片实现分页响应 | ✅ 字段一致（但 API 请求参数表缺 page/page_size，P3-1） |

### 3.4 状态码与切片一致性

| 检查项 | 结果 | 依据 |
|--------|------|------|
| 404 错误消息规范 | ✅ 通过 | 各端点均遵循 `{资源名}不存在` 格式 |
| 微信回调非统一响应格式 | ✅ 已标注 | `11-payment/backend.md` L609-612 `WechatNotifyResponse` 返回 `{code: "SUCCESS", message: "成功"}`，非标准 `{code, message, data}` 格式，属业务例外 |
| 429 限流响应 | ✅ 通过 | share 5/day、AI 分析 10/hour、auth 10/min，与 API 设计限流表一致 |

---

## 4. 通过项汇总

| 编号 | 检查项 | 结果 | 依据 |
|------|--------|------|------|
| ✅1 | 端点总数验证 | 通过 | 79 业务端点 + 17 admin 端点 = 96 |
| ✅2 | admin 17 端点实现完整性 | 通过 | `13-infrastructure/admin.md` 定义全部 17 端点（16 个 Phase 1 活跃 + 1 个 Phase 2+ 占位），与 API §19.2-§19.6 完全对应 |
| ✅3 | §1.7 通用错误码 | 通过 | 9 条全局错误码（40100/40101/40300/40400/42200/42900/40000/50200/50000）覆盖完整 |
| ✅4 | §1.8 端点级业务错误码 | 通过 | 12 条端点级错误码覆盖视频分析、记分牌、比赛记录、分享、通用模块 |
| ✅5 | 分页参数命名统一 | 通过 | 全部端点使用 `page`/`page_size`，默认 20，用户端最大 50，管理端最大 100 |
| ✅6 | share_router HTMLResponse | 通过 | `03-video_analysis/backend.md` L1250 `@share_router.get("/share/{share_token}", response_class=HTMLResponse)` 与 API §4.11 一致 |
| ✅7 | 认证依赖 | 通过 | 需认证端点均配置 `get_current_user` 或 `require_membership`；公开端点（login/share）无认证依赖 |
| ✅8 | 限流配置 | 通过 | 全局 100/min，AI 分析 10/hour，报告分享 5/day，auth login 10/min |
| ✅9 | POST/PUT/PATCH 请求体定义 | 通过 | 所有需请求体的端点均有 Request Body JSON 示例和字段说明 |
| ✅10 | 404 错误消息规范 | 通过 | 遵循 `{资源名}不存在` 格式 |
| ✅11 | APIRouter prefix 无叠加 | 通过 | 所有 Router 单层 prefix，share_router 显式无前缀 |
| ✅12 | 微信回调响应格式例外 | 通过 | `WechatNotifyResponse` 非统一响应格式，属业务例外已标注 |

---

## 5. 问题汇总

| 编号 | 优先级 | 问题 | 位置 | R15 状态 | R16 状态 |
|------|--------|------|------|----------|----------|
| P2-1 | P2 | ReportDetailResponse 缺少 task_uuid 字段 | API §4.6 L1153/L1164 vs 切片 L465-475 | 🔴 未修复 | 🔴 未修复（连续两轮） |
| P3-1 | P3 | GET /training/templates 请求参数表缺少分页参数 | API §8.3 L2215-2217 vs 切片 L1194-1195 | 🟡 未修复 | 🟡 未修复（连续两轮） |
| P3-2 | P3 | §4.7 ReportListItem task_id 示例值类型错误（string vs int） | API §4.7 L1226 vs §4.4 L919/切片 L457 | 🟡 未修复 | 🟡 未修复（连续两轮） |
| P3-3 | P3 | get_report_detail 返回未文档化 is_readonly 字段 | API §4.6 L1157-1192 vs 切片 L837-843 | 🟡 未修复 | 🟡 未修复（连续两轮） |

**统计**：P0×0 | P1×0 | P2×1 | P3×3 | 共 4 项遗留

**本轮无新发现。**

---

## 6. 修复优先级建议

### 6.1 P2 级（建议本轮修复）

1. **P2-1（ReportDetailResponse 缺 task_uuid）**：连续两轮未修复。API 设计已明确 `task_uuid` 用于对外暴露（分享链接、CDN 路径、WebSocket 推送），切片 `ReportDetailResponse` 缺失该字段将导致前端无法获取 `task_uuid`。
   - **修复建议**：在切片 `ReportDetailResponse`（L465-475）添加 `task_uuid: str` 字段；在 Service `get_report_detail` 中通过 `report.task.task_uuid` 或关联查询注入该字段。

### 6.2 P3 级（连续两轮未修复，建议升级优先级处理）

三项 P3 级问题均连续两轮未修复，虽然不影响运行时行为，但持续降低 API 设计文档的权威性和开发者体验。建议在下一轮文档同步中批量修复：

2. **P3-1（training/templates 缺分页参数）**：API §8.3 请求参数表补充 `page`（query, int, N, 页码）和 `page_size`（query, int, N, 每页条数）两行。
3. **P3-2（§4.7 task_id 示例类型）**：API §4.7 L1226 `"task_id": "task_xxx"` 改为 `"task_id": 1001`。
4. **P3-3（is_readonly 未文档化）**：API §4.6 响应体补充 `is_readonly`（boolean）字段定义，添加说明：「降级用户只读标记，`true` 表示用户处于降级状态，报告内容只读」。

---

## 7. 审查结论

第十五轮 API 端点级一致性审查发现 6 项问题（P2×3 + P3×3），本轮验证其中 2 项 P2 已修复（P2-2 ShareResponse 字段名、P2-3 退款状态值），1 项 P2 未修复（P2-1 task_uuid），3 项 P3 全部未修复。

本轮深层检查覆盖端点总数、admin 端点实现、Router prefix 叠加、响应 Schema 字段一致性、状态码一致性等 9 项，均通过验证，**无新发现问题**。

当前遗留 4 项（P2×1 + P3×3），其中 P2-1 连续两轮未修复，3 项 P3 连续两轮未修复。建议优先修复 P2-1（切片 Schema 字段缺失），并在下一轮文档同步中批量处理 3 项 P3 级文档一致性问题。

---

> **审查结论**：第十六轮 API 端点级一致性审查遗留 4 项（P2×1 + P3×3），无新发现。R15 的 2 项 P2 修复（ShareResponse 字段名、退款状态值）通过回归验证。核心风险为 P2-1 task_uuid 字段缺失连续两轮未修复，建议优先处理。
