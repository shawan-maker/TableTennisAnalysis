# 第十七轮 API 端点级一致性审查报告

> **审查日期**：2026-10-16  
> **审查维度**：API 端点级一致性  
> **审查代理**：第十七轮 API 端点级审查代理  
> **基准文档**：`docs/04详细设计/05-API详细设计.md`（v1.3）、`docs/03系统架构/01-系统架构设计.md`（v2.4）§5.7、`docs/06垂直模块前后端切片设计/00-垂直切片设计总览.md`  
> **切片文档**：12 模块 backend.md + 13-infrastructure/admin.md + 00-home/frontend.md  
> **前十六轮累计修复**：749 项  

---

## 1. 审查范围

本轮审查聚焦 API 设计文档 v1.3 与后端切片之间的端点级一致性，覆盖以下检查项：

| 编号 | 检查项 | 类别 |
|------|--------|------|
| 1-3 | R16 P1-1~3 修复验证：首页聚合端点清单三文档一致 | 修复验证 |
| 4 | R16 P2-1 修复验证：架构 §5.7 training/calendar→gamification/checkin-calendar | 修复验证 |
| 5-8 | R15 遗留 4 项验证（P2-1 task_uuid + P3-1~3） | 修复验证 |
| 9 | 端点总数验证（79 + 17 = 96） | 端点对比 |
| 10 | 逐模块端点路径/HTTP 方法对比（API §2-§13 vs 切片 @router） | 端点对比 |
| 11 | 管理后台 §19 的 17 个端点 vs admin.md | 端点对比 |
| 12 | 架构 §5.7 端点清单 vs API 设计 vs 切片 | 跨文档对比 |
| 13 | 请求体/响应体字段对比 | Schema 对比 |
| 14 | 限流配置对比（API §1.5 vs 切片 limiter） | 限流对比 |
| 15 | 错误码对比（API §1.7/§1.8 vs 切片 HTTPException/AppException） | 错误码对比 |
| 16 | 首页聚合端点实际调用 vs 文档声明 | 深层检查 |
| 17 | scoring 3 端点（start/abandon/resume）状态码 | 深层检查 |
| 18 | payment refund 422 状态码 | 深层检查 |
| 19 | progress summary 缓存 TTL 5min | 深层检查 |
| 20 | feedbacks 端点归属 | 深层检查 |

---

## 2. R16 修复验证

### 2.1 P1-1~3：首页聚合端点清单三文档一致

| 编号 | R16 修复项 | 验证结果 | 依据 |
|------|-----------|----------|------|
| P1-1~3 | 首页聚合端点清单在 API §14a、架构 §5.7、00-home/frontend.md 三处完全一致 | 🔴 未完全修复 | API §14a 与架构 §5.7 文字描述一致，但 00-home/frontend.md 实际调用的端点与前两者不一致（详见 §2.1.1） |

#### 2.1.1 详细说明

**API §14a（L3403）声明的端点清单**：
1. `GET /users/profile`
2. `GET /scoring/matches`
3. `GET /training/advice/contextual`
4. `GET /gamification/points`
5. `GET /notification/unread-count`

**架构 §5.7（L955-959）声明的端点清单**：
1. `GET /users/profile`
2. `GET /scoring/matches`
3. `GET /training/advice/contextual`
4. `GET /gamification/points`
5. `GET /notification/unread-count`

✅ API §14a 与架构 §5.7 **文字描述完全一致**。

**00-home/frontend.md 实际调用的端点**（`services/home.ts` L82-105）：
1. `dashboardApi.getOverview()` → `GET /dashboard/overview`（非 `/users/profile`）
2. `request.get('/gamification/points')` → `GET /gamification/points`（函数名 `getCheckinCalendar` 但调用积分端点）
3. `request.get('/scoring/matches', { params: { page: 1, page_size: 3 } })` → `GET /scoring/matches`
4. `request.get('/notification/unread-count')` → `GET /notification/unread-count`

**差异分析**：

| # | API §14a/架构 §5.7 声明 | 00-home/frontend.md 实际调用 | 差异 |
|---|------------------------|------------------------------|------|
| 1 | `GET /users/profile` | 无（用户信息从 authStore 获取，L126 注释说明） | 前端少调用 1 个端点 |
| 2 | `GET /training/advice/contextual` | 无（从 `/dashboard/overview` 响应体的 `latest_advice_summary` 字段获取，L184） | 前端少调用 1 个端点 |
| 3 | — | `GET /dashboard/overview` | 前端多调用 1 个端点 |
| 4 | `GET /gamification/points` | `GET /gamification/points`（函数名 `getCheckinCalendar`） | 端点一致但函数名误导 |
| 5 | `GET /scoring/matches` | `GET /scoring/matches` | ✅ 一致 |
| 6 | `GET /notification/unread-count` | `GET /notification/unread-count` | ✅ 一致 |

**结论**：R16 P1-1~3 声称"三处完全一致"不准确。API §14a 与架构 §5.7 的文字描述确实一致（R16 修复了这两处），但 00-home/frontend.md 的实际代码实现调用的端点集合与前两者不同。前端通过 `/dashboard/overview` 的 `latest_advice_summary` 字段获取训练建议（API §6.1 L1782-1786 确认该字段存在），且从 authStore 获取用户信息而非单独调用 `/users/profile`。三文档未真正对齐。

---

### 2.2 P2-1：架构 §5.7 training/calendar→gamification/checkin-calendar

| 编号 | R16 修复项 | 验证结果 | 依据 |
|------|-----------|----------|------|
| P2-1 | 架构 §5.7 中 training/calendar→gamification/checkin-calendar | ✅ 已修复 | 架构 §5.7 训练模块（L893-896）无 `training/calendar` 端点；游戏化模块（L903）为 `GET /gamification/checkin-calendar` |

---

### 2.3 R15 遗留 4 项验证

| 编号 | R15 遗留项 | R16 状态 | R17 验证结果 | 依据 |
|------|-----------|----------|-------------|------|
| P2-1 | ReportDetailResponse 缺少 task_uuid 字段 | 🔴 未修复 | 🟡 部分修复 | 切片 `ReportDetailResponse`（L468）**已添加** `task_uuid: str` 字段；但 Service `get_report_detail`（L843）使用 `model_validate(report)` 从 AnalysisReport 对象验证，而 `task_uuid` 在 VideoTask 模型上（L245），AnalysisReport 无此属性且查询未预加载 task 关系，`model_validate` 将抛出 ValidationError（详见 §2.3.1） |
| P3-1 | GET /training/templates 请求参数表缺少分页参数 | 🟡 未修复 | ✅ 已修复 | API §8.3 L2221-2222 已补充 `page`（query, int, N, 页码，默认 1）和 `page_size`（query, int, N, 每页条数，默认 20）；切片 L1194-1195 已实现分页参数 |
| P3-2 | §4.7 ReportListItem task_id 示例值类型错误 | 🟡 未修复 | ✅ 已修复 | API §4.7 L1229 已改为 `"task_id": 12345`（int 类型），与 §4.4 L919 声明 `int` 及切片 L457 `task_id: int` 一致 |
| P3-3 | get_report_detail 返回未文档化 is_readonly 字段 | 🟡 未修复 | ✅ 已修复 | API §4.6 L1189 响应体已包含 `"is_readonly": false` 字段；L1195 已添加字段说明（R15-P3-3 修复标注） |

#### 2.3.1 P2-1 详细说明（Service 注入不完整）

切片 `ReportDetailResponse`（L465-476）已添加 `task_uuid: str` 字段：

```python
# 03-video_analysis/backend.md L465-476
class ReportDetailResponse(BaseModel):
    id: int
    task_id: int
    task_uuid: str          # ← 已添加
    created_at: datetime
    is_llm_generated: bool
    result_data: Optional[dict[str, Any]] = None
    report_text: Optional[dict[str, Any]] = None
    annotated_video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    report_images: Optional[dict[str, Any]] = None
    model_config = {"from_attributes": True}
```

但 Service `get_report_detail`（L828-845）存在问题：

```python
# L831-834: 查询未预加载 task 关系
stmt = select(AnalysisReport).where(
    AnalysisReport.id == report_id, AnalysisReport.user_id == user_id,
)
report = (await db.execute(stmt)).scalar_one_or_none()

# L843: model_validate 尝试从 report 对象获取所有字段
data = ReportDetailResponse.model_validate(report).model_dump()
```

**问题**：`AnalysisReport` 模型（L292-314）没有 `task_uuid` 字段（该字段在 `VideoTask` 模型 L245）。虽然有 `task: Mapped["VideoTask"] = relationship(back_populates="report")`（L312），但：
1. 查询未使用 `selectinload(AnalysisReport.task)` 或 `joinedload` 预加载 task 关系
2. `model_config = {"from_attributes": True}` 使 Pydantic 从对象属性获取值，但 `report.task_uuid` 不存在（`task_uuid` 在 `report.task.task_uuid` 上）
3. 即使预加载了 task 关系，Pydantic 也不会自动从 `report.task.task_uuid` 获取 `task_uuid` 字段

**结果**：`model_validate(report)` 会因为缺少 `task_uuid` 属性而抛出 `ValidationError`。

**修复建议**：在 Service 方法中手动注入 task_uuid：
```python
stmt = select(AnalysisReport).options(
    selectinload(AnalysisReport.task)
).where(AnalysisReport.id == report_id, AnalysisReport.user_id == user_id)
report = (await db.execute(stmt)).scalar_one_or_none()
...
data = ReportDetailResponse.model_validate(report).model_dump()
data["task_uuid"] = report.task.task_uuid  # 手动注入
data["is_readonly"] = is_readonly
```

---

### 2.4 §1.7 通用错误码回归验证

| 编号 | 检查项 | 验证结果 | 依据 |
|------|--------|----------|------|
| 1 | 400 / 40000 业务校验失败 | ✅ 无回归 | `05-API详细设计.md` L96：`400 / 40000` |
| 2 | 502 / 50200 第三方服务不可用 | ✅ 无回归 | `05-API详细设计.md` L97：`502 / 50200` |
| 3 | §1.8 端点级错误码 12 条 | ✅ 无回归 | L106-119：12 条端点级错误码完整 |

---

## 3. 端点总数对比

### 3.1 端点总数验证

| 来源 | 业务端点 | Admin 端点 | 合计 |
|------|---------|-----------|------|
| API 设计 v1.3（§2-§13） | 79 | — | 79 |
| API 设计 v1.3（§19） | — | 17 | 17 |
| 架构 §5.7 | 79 | 17（引用 §19） | 96 |
| 总览（L846） | 79 | 17 | 96 |
| 切片实际（12 模块 backend.md + admin.md） | 79 | 17 | 96 |

✅ **端点总数一致：79 + 17 = 96**

### 3.2 逐模块端点数对比

| 模块 | API 设计 | 架构 §5.7 | 切片实际 | 一致性 |
|------|---------|----------|---------|--------|
| auth | 10 | 10 | 10 | ⚠️ 路径差异（§4.1） |
| user | 9+1(feedbacks) | 9 | 9+1(feedbacks in video_analysis) | ✅ 一致 |
| video_analysis | 11+1(share) | 12 | 12 | ✅ 一致 |
| scoring | 10 | 10 | 10 | ✅ 一致 |
| match_data | 4 | 4 | 4 | ✅ 一致 |
| dashboard | 5 | 5 | 5 | ✅ 一致 |
| training | 8 | 7（去重后） | 8 | ⚠️ 架构缺 2 端点 + 路径差异（§4.2） |
| progress | 6 | 6 | 6 | ⚠️ 缓存 TTL 差异（§4.3） |
| gamification | 4 | 4 | 4 | ✅ 一致 |
| membership | 3 | 3 | 3 | ✅ 一致 |
| payment | 4 | 4 | 4 | ✅ 一致 |
| notification | 4 | 4 | 4 | ✅ 一致 |
| admin | 17 | 17（引用） | 17 | ✅ 一致 |
| **合计** | **79+17=96** | **79+17=96** | **79+17=96** | — |

---

## 4. 深层检查发现

### 4.1 架构 §5.7 consent 端点路径不一致

| 来源 | 路径 | 行号 |
|------|------|------|
| 架构 §5.7 | `GET /auth/consent/history` | L822 |
| API §2.10 | `GET /auth/consent-status` | L465 |
| 切片 01-auth | `GET /consent-status`（router prefix `/auth`） | L675 |

**不一致**：架构 §5.7 使用 `consent/history`，API 和切片使用 `consent-status`。架构端点路径与 API/切片不一致。

### 4.2 架构 §5.7 训练模块端点路径与数量不一致

| 架构 §5.7 端点 | API 设计 / 切片对应 | 差异 |
|---------------|---------------------|------|
| `POST /training/templates/{id}/sessions` | 无直接对应（API/切片无此端点） | 架构多出 1 个不存在的端点 |
| `GET /training/plan/{id}/adjustments`（单数 plan） | `GET /training/plans/{plan_id}/adjustments`（复数 plans） | 路径参数名不一致（plan vs plans） |
| `POST /training/plan/{id}/re-evaluate`（单数 plan） | `POST /training/plans/{plan_id}/re-evaluate`（复数 plans） | 路径参数名不一致 |
| — | `GET /training/plans/{plan_id}/sessions`（API §8.7 / 切片 L1237） | 架构缺少此端点 |
| — | `POST /training/plans/{plan_id}/sessions/{session_id}/complete`（API §8.8 / 切片 L1248） | 架构缺少此端点 |

**不一致**：架构 §5.7 训练模块端点清单与 API 设计/切片存在 4 处差异（1 个多余端点 + 2 个路径不一致 + 2 个缺失端点）。架构去重后仅 7 个端点，API/切片有 8 个。

### 4.3 架构 §5.7 progress/summary 缓存 TTL 不一致

| 来源 | 缓存 TTL | 行号 |
|------|---------|------|
| 架构 §5.7 | 1h | L938 |
| API §9.5 | 5min | L2624 |
| 切片 08-progress_analysis | 5min（`redis.setex(cache_key, 300, ...)`） | L1189 |

**不一致**：A-4 修复（summary 缓存从 1h 降至 5min）已应用于 API 设计和切片，但未回写架构 §5.7。架构仍标注 1h。

### 4.4 首页聚合 getCheckinCalendar 调用错误端点

**00-home/frontend.md L89-91**：

```typescript
export function getCheckinCalendar() {
  return request.get('/gamification/points')
}
```

**问题**：函数名 `getCheckinCalendar` 和注释"获取训练打卡日历（周视图）"表明应调用打卡日历端点，但实际调用的是 `/gamification/points`（积分端点）。正确端点应为 `/gamification/checkin-calendar`（API §10.2 / 切片 L1066）。

### 4.5 ReportDetailResponse model_validate 缺少 task_uuid 注入

详见 §2.3.1。切片 `ReportDetailResponse` 已有 `task_uuid: str` 字段，但 Service `get_report_detail` 未正确注入该值，`model_validate(report)` 会因 AnalysisReport 缺少 `task_uuid` 属性而抛出 ValidationError。

### 4.6 API §12.4 refund 错误情况表缺少 422 条目

**API §12.4**：
- L3169 业务规则："下单 7d 后：不支持退款，返回 422"
- L3199-3206 错误情况表：仅列出 404、400×2、502，**缺少 422 条目**

**切片 11-payment L1207**：`raise AppException("超过7天的订单不可退款", 422)` — 正确使用 422

**不一致**：API 设计错误情况表未列出 422 状态码条目，与业务规则段落和切片实现不完整对应。

### 4.7 架构 §5.7 管理后台端点引用章节号错误

**架构 §5.7 L963**：

> 管理后台 17 个端点（admin_user 管理、audit_log 查询、系统配置、内容审核、模型管理等）详见 API 设计 **§17**

**实际位置**：管理后台 API 在 API 设计 **§19**（L5050），§17 是"Phase 4 API 端点详细设计"（L4553）。

**不一致**：架构引用章节号错误（§17 应为 §19）。

### 4.8 架构 §5.7 scoring start 端点描述不准确

**架构 §5.7 L862**：

> `POST | /scoring/matches/{id}/start | 开始比赛（从暂停态恢复）`

**API §5.8 L1643**："开始比赛（状态机转换：setup → in_progress）"  
**切片 L1216**："开始比赛（状态机入口）"

**不一致**：架构描述"从暂停态恢复"实际是 resume 端点（abandoned → in_progress）的语义，start 端点是从 setup → in_progress 的状态机入口。

---

## 5. 逐模块端点对比通过项

### 5.1 auth 模块（10 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 |
|---------|-------------|---------|---------|
| §2.1 POST /auth/wechat-login | L588 POST /wechat-login | ✅ | ✅ |
| §2.2 POST /auth/phone-login | L594 POST /phone-login | ✅ | ✅ |
| §2.3 POST /auth/send-sms | L600 POST /send-sms | ✅ | ✅ |
| §2.4 POST /auth/refresh | L606 POST /refresh | ✅ | ✅ |
| §2.5 POST /auth/logout | L612 POST /logout | ✅ | ✅ |
| §2.6 GET /auth/me | L626 GET /me | ✅ | ✅ |
| §2.7 POST /auth/h5-token | L643 POST /h5-token | ✅ | ✅ |
| §2.8 POST /auth/h5-exchange | L649 POST /h5-exchange | ✅ | ✅ |
| §2.9 POST /auth/consent | L656 POST /consent | ✅ | ✅ |
| §2.10 GET /auth/consent-status | L675 GET /consent-status | ✅ | ✅ |

限流：wechat-login 10/min ✓，phone-login 5/min ✓，send-sms 1/min ✓

### 5.2 user 模块（9 端点）+ feedbacks（在 video_analysis 实现）

| API 设计 | 切片 @router | 路径一致 | 方法一致 |
|---------|-------------|---------|---------|
| §3.1 GET /users/profile | L776 GET /profile | ✅ | ✅ |
| §3.2 PATCH /users/profile | L786 PATCH /profile | ✅ | ✅ |
| §3.3 PATCH /users/rating | L797 PATCH /rating | ✅ | ✅ |
| §3.4 GET /users/rating-history | L808 GET /rating-history | ✅ | ✅ |
| §3.5 GET /users/big-data | L820 GET /big-data | ✅ | ✅ |
| §3.6 DELETE /users/account | L830 DELETE /account | ✅ | ✅ |
| §3.7 GET /video-analysis/reports/{report_id}/feedbacks | 03-video_analysis L1222 GET /reports/{report_id}/feedbacks | ✅ | ✅ |
| §3.8 POST /users/export-data | L851 POST /export-data | ✅ | ✅ |
| §3.9 GET /users/export-data/{task_id} | L861 GET /export-data/{task_id} | ✅ | ✅ |
| §3.10 POST /users/account/cancel-deletion | L841 POST /account/cancel-deletion | ✅ | ✅ |

### 5.3 video_analysis 模块（12 端点含 share_router）

| API 设计 | 切片 @router | 路径一致 | 方法一致 |
|---------|-------------|---------|---------|
| §4.1 POST /video-analysis/upload-token | L1128 POST /upload-token | ✅ | ✅ |
| §4.2 POST /video-analysis/upload-complete | L1139 POST /upload-complete | ✅ | ✅ |
| §4.3 POST /video-analysis/tasks | L1150 POST /tasks | ✅ | ✅ |
| §4.4 GET /video-analysis/tasks | L1161 GET /tasks | ✅ | ✅ |
| §4.5 GET /video-analysis/tasks/{task_id} | L1174 GET /tasks/{task_id} | ✅ | ✅ |
| §4.6 GET /video-analysis/reports/{report_id} | L1185 GET /reports/{report_id} | ✅ | ✅ |
| §4.7 GET /video-analysis/reports | L1196 GET /reports | ✅ | ✅ |
| §4.8 POST /video-analysis/reports/{report_id}/feedback | L1208 POST /reports/{report_id}/feedback | ✅ | ✅ |
| §4.9 GET /video-analysis/reports/{report_id}/annotated-video | L1235 GET /reports/{report_id}/annotated-video | ✅ | ✅ |
| §4.10 POST /video-analysis/reports/{report_id}/share | L1246 POST /reports/{report_id}/share | ✅ | ✅ |
| §4.11 GET /share/{share_token} | L1271 @share_router GET /share/{share_token} | ✅ | ✅ |

限流：tasks 10/hour ✓，share 5/day ✓

### 5.4 scoring 模块（10 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 | 状态码 |
|---------|-------------|---------|---------|--------|
| §5.1 POST /scoring/matches | L1140 POST /matches | ✅ | ✅ | — |
| §5.2 GET /scoring/matches | L1150 GET /matches | ✅ | ✅ | — |
| §5.3 GET /scoring/matches/{match_id} | L1164 GET /matches/{match_id} | ✅ | ✅ | — |
| §5.4 POST /scoring/matches/{match_id}/score | L1174 POST /matches/{match_id}/score | ✅ | ✅ | 409 ✓ |
| §5.5 POST /scoring/matches/{match_id}/undo | L1185 POST /matches/{match_id}/undo | ✅ | ✅ | 409 ✓ |
| §5.6 POST /scoring/matches/{match_id}/finish | L1196 POST /matches/{match_id}/finish | ✅ | ✅ | 409 ✓ |
| §5.7 GET /scoring/matches/{match_id}/statistics | L1206 GET /matches/{match_id}/statistics | ✅ | ✅ | — |
| §5.8 POST /scoring/matches/{match_id}/start | L1216 POST /matches/{match_id}/start | ✅ | ✅ | 400 ✓ |
| §5.9 POST /scoring/matches/{match_id}/abandon | L1227 POST /matches/{match_id}/abandon | ✅ | ✅ | 400 ✓ |
| §5.10 POST /scoring/matches/{match_id}/resume | L1238 POST /matches/{match_id}/resume | ✅ | ✅ | 400 ✓ |

**状态码说明**：score/undo/finish 使用 409（§1.8 端点级错误码 40910），start/abandon/resume 使用 400（状态转换冲突）。API 设计与切片一致。

### 5.5 match_data 模块（4 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 |
|---------|-------------|---------|---------|
| §7.1 POST /match-data/records | L919 POST /records | ✅ | ✅ |
| §7.2 GET /match-data/records | L929 GET /records | ✅ | ✅ |
| §7.3 GET /match-data/records/{record_id} | L942 GET /records/{record_id} | ✅ | ✅ |
| §7.4 PATCH /match-data/records/{record_id} | L952 PATCH /records/{record_id} | ✅ | ✅ |

### 5.6 dashboard 模块（5 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 | 缓存 |
|---------|-------------|---------|---------|------|
| §6.1 GET /dashboard/overview | L782 GET /overview | ✅ | ✅ | 5min ✓ |
| §6.2 GET /dashboard/win-rate-trend | L789 GET /win-rate-trend | ✅ | ✅ | 1h ✓ |
| §6.3 GET /dashboard/technique-stats | L799 GET /technique-stats | ✅ | ✅ | 1h ✓ |
| §6.4 GET /dashboard/landing-heatmap | L806 GET /landing-heatmap | ✅ | ✅ | 1h ✓ |
| §6.5 GET /dashboard/match-records | L813 GET /match-records | ✅ | ✅ | — |

### 5.7 training_advice 模块（8 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 |
|---------|-------------|---------|---------|
| §8.1 GET /training/advice/{report_id} | L1172 GET /advice/{report_id} | ✅ | ✅ |
| §8.2 GET /training/advice/contextual | L1182 GET /advice/contextual | ✅ | ✅ |
| §8.3 GET /training/templates | L1191 GET /templates | ✅ | ✅ |
| §8.4 GET /training/templates/{template_id} | L1205 GET /templates/{template_id} | ✅ | ✅ |
| §8.5 GET /training/plans/{plan_id}/adjustments | L1215 GET /plans/{plan_id}/adjustments | ✅ | ✅ |
| §8.6 POST /training/plans/{plan_id}/re-evaluate | L1225 POST /plans/{plan_id}/re-evaluate | ✅ | ✅ |
| §8.7 GET /training/plans/{plan_id}/sessions | L1237 GET /plans/{plan_id}/sessions | ✅ | ✅ |
| §8.8 POST /training/plans/{plan_id}/sessions/{session_id}/complete | L1248 POST /plans/{plan_id}/sessions/{session_id}/complete | ✅ | ✅ |

### 5.8 progress_analysis 模块（6 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 | 缓存 |
|---------|-------------|---------|---------|------|
| §9.1 GET /progress/snapshots | L1373 GET /snapshots | ✅ | ✅ | — |
| §9.2 GET /progress/technique-trends | L1387 GET /technique-trends | ✅ | ✅ | 1h ✓ |
| §9.3 GET /progress/technique-trends/{metric} | L1397 GET /technique-trends/{metric} | ✅ | ✅ | 1h ✓ |
| §9.4 GET /progress/comparison | L1408 GET /comparison | ✅ | ✅ | — |
| §9.5 GET /progress/summary | L1421 GET /summary | ✅ | ✅ | 5min ✓ |
| §9.6 GET /progress/problem-changes | L1431 GET /problem-changes | ✅ | ✅ | 1h ✓ |

### 5.9 gamification 模块（4 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 | 限流 |
|---------|-------------|---------|---------|------|
| §10.1 GET /gamification/points | L1055 GET /points | ✅ | ✅ | 100/min ✓ |
| §10.2 GET /gamification/checkin-calendar | L1066 GET /checkin-calendar | ✅ | ✅ | 100/min ✓ |
| §10.3 POST /gamification/checkin | L1086 POST /checkin | ✅ | ✅ | 1/day ✓ |
| §10.4 GET /gamification/badges | L1097 GET /badges | ✅ | ✅ | 100/min ✓ |

### 5.10 membership 模块（3 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 |
|---------|-------------|---------|---------|
| §11.1 GET /membership/tiers | L801 GET /tiers | ✅ | ✅ |
| §11.2 GET /membership/current | L812 GET /current | ✅ | ✅ |
| §11.3 GET /membership/quota | L823 GET /quota | ✅ | ✅ |

### 5.11 payment 模块（4 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 | 限流 |
|---------|-------------|---------|---------|------|
| §12.1 POST /payment/orders | L1340 POST /orders | ✅ | ✅ | 100/min ✓ |
| §12.2 GET /payment/orders | L1356 GET /orders | ✅ | ✅ | 100/min ✓ |
| §12.3 POST /payment/notify | L1376 POST /notify | ✅ | ✅ | 无限流（SEC-006）✓ |
| §12.4 POST /payment/orders/{order_id}/refund | L1414 POST /orders/{order_id}/refund | ✅ | ✅ | 100/min ✓ |

### 5.12 notification 模块（4 端点）

| API 设计 | 切片 @router | 路径一致 | 方法一致 |
|---------|-------------|---------|---------|
| §13.1 GET /notification/list | L660 GET /list | ✅ | ✅ |
| §13.2 POST /notification/read | L676 POST /read | ✅ | ✅ |
| §13.3 POST /notification/subscribe | L686 POST /subscribe | ✅ | ✅ |
| §13.4 GET /notification/unread-count | L696 GET /unread-count | ✅ | ✅ |

### 5.13 admin 模块（17 端点）

| API 设计 §19 | 切片 admin.md @router | 路径一致 | 方法一致 |
|-------------|----------------------|---------|---------|
| §19.2.1 POST /admin/login | L873 POST /login | ✅ | ✅ |
| §19.2.2 POST /admin/logout | L881 POST /logout | ✅ | ✅ |
| §19.2.3 GET /admin/users | L894 GET /users | ✅ | ✅ |
| §19.2.4 POST /admin/users/{user_id}/ban | L908 POST /users/{user_id}/ban | ✅ | ✅ |
| §19.2.5 POST /admin/users/{user_id}/unban | L919 POST /users/{user_id}/unban | ✅ | ✅ |
| §19.3.1 GET /admin/configs | L930 GET /configs | ✅ | ✅ |
| §19.3.2 GET /admin/configs/{key} | L939 GET /configs/{key} | ✅ | ✅ |
| §19.3.3 POST /admin/configs | L949 POST /configs | ✅ | ✅ |
| §19.3.4 PATCH /admin/configs/{key} | L959 PATCH /configs/{key} | ✅ | ✅ |
| §19.3.5 DELETE /admin/configs/{key} | L970 DELETE /configs/{key} | ✅ | ✅ |
| §19.4.1 GET /admin/audit-logs | L981 GET /audit-logs | ✅ | ✅ |
| §19.5.1 POST /admin/knowledge/categories | L1003 POST /knowledge/categories | ✅ | ✅ |
| §19.5.2 PATCH /admin/knowledge/categories/{category_id} | L1013 PATCH /knowledge/categories/{category_id} | ✅ | ✅ |
| §19.5.3 DELETE /admin/knowledge/categories/{category_id} | L1024 DELETE /knowledge/categories/{category_id} | ✅ | ✅ |
| §19.5.4 POST /admin/knowledge/rules | L1034 POST /knowledge/rules | ✅ | ✅ |
| §19.5.5 PATCH /admin/knowledge/rules/{rule_id}/toggle | L1044 PATCH /knowledge/rules/{rule_id}/toggle | ✅ | ✅ |
| §19.6.1 POST /admin/model-versions/{version_id}/activate | L1057 注释占位（Phase 2+） | ✅ | ✅ |

限流：login 5/min ✓，其他 100/min ✓

---

## 6. 通过项汇总

| 编号 | 检查项 | 结果 | 依据 |
|------|--------|------|------|
| ✅1 | 端点总数验证 | 通过 | 79 业务端点 + 17 admin 端点 = 96，API/架构/总览/切片四方一致 |
| ✅2 | API §2-§13 vs 切片端点路径/方法 | 通过 | 79 个业务端点路径和 HTTP 方法全部一致（含 share_router 公开端点） |
| ✅3 | admin 17 端点实现完整性 | 通过 | 16 个 Phase 1 活跃端点 + 1 个 Phase 2+ 占位，与 API §19.2-§19.6 完全对应 |
| ✅4 | §1.7 通用错误码 | 通过 | 9 条全局错误码完整无回归 |
| ✅5 | §1.8 端点级业务错误码 | 通过 | 12 条端点级错误码完整无回归 |
| ✅6 | 分页参数命名统一 | 通过 | 全部端点使用 `page`/`page_size`，默认 20，用户端 le=50 |
| ✅7 | share_router HTMLResponse | 通过 | `03-video_analysis/backend.md` L1271 与 API §4.11 一致 |
| ✅8 | 认证依赖 | 通过 | 需认证端点均配置 `get_current_user`/`require_membership`；公开端点无认证 |
| ✅9 | 限流配置 | 通过 | auth 10/5/1 per min，AI 10/hour，share 5/day，checkin 1/day，admin login 5/min，全局 100/min |
| ✅10 | POST/PUT/PATCH 请求体定义 | 通过 | 所有需请求体的端点均有 Request Body JSON 示例和字段说明 |
| ✅11 | 404 错误消息规范 | 通过 | 遵循 `{资源名}不存在` 格式 |
| ✅12 | APIRouter prefix 无叠加 | 通过 | 所有 Router 单层 prefix，share_router 显式无前缀 |
| ✅13 | scoring 3 端点（start/abandon/resume） | 通过 | API §5.8-5.10 与切片 L1216/L1227/L1238 路径/方法/状态码一致 |
| ✅14 | payment refund 422 状态码 | 通过 | 切片 L1207 正确使用 422，与 API §12.4 L3169 业务规则一致 |
| ✅15 | notification unread-count 端点 | 通过 | API §13.4 与切片 L696 一致 |
| ✅16 | feedbacks 端点归属 | 通过 | API §3.7 有模块归属说明（L776），切片在 video_analysis L1222 实现 |
| ✅17 | 微信回调响应格式例外 | 通过 | `WechatNotifyResponse` 非统一格式，属业务例外已标注 |
| ✅18 | progress summary 缓存 5min（API vs 切片） | 通过 | API §9.5 L2624 与切片 L1189 一致（均为 5min） |

---

## 7. 问题汇总

| 编号 | 严重度 | 模块 | API 设计 | 切片 | 不一致描述 |
|------|--------|------|---------|------|-----------|
| R17-P1-1 | P1 | 00-home | §14a 声明 5 个聚合端点（profile/matches/advice/contextual/points/unread-count） | 00-home/frontend.md 实际调用 4 个端点（dashboard/overview/gamification:points/scoring:matches/notification:unread-count） | 首页聚合端点清单三文档不一致：API §14a 与架构 §5.7 文字一致，但 00-home/frontend.md 实际调用 `/dashboard/overview`（非 `/users/profile`），且无独立调用 `/training/advice/contextual`（从 overview 响应体 `latest_advice_summary` 字段获取）。R16 P1-1~3 声称"三处完全一致"不准确 |
| R17-P1-2 | P1 | 00-home | §10.2 `GET /gamification/checkin-calendar`（打卡日历） | 00-home/frontend.md L89-91 `getCheckinCalendar()` 调用 `/gamification/points`（积分端点） | 函数名 `getCheckinCalendar` 应调用 `/gamification/checkin-calendar`，实际错误调用 `/gamification/points`（积分端点）。返回数据结构不匹配（CheckinCalendar vs points 响应） |
| R17-P2-1 | P2 | video_analysis | §4.6 响应体含 `task_uuid` 字段 | 切片 ReportDetailResponse L468 已有 `task_uuid: str`，但 Service `get_report_detail` L843 `model_validate(report)` 未注入 task_uuid | ReportDetailResponse Schema 已添加 task_uuid 字段，但 Service 方法从 AnalysisReport 对象验证时缺少 task_uuid 属性（在 VideoTask 上），且查询未预加载 task 关系，model_validate 将抛出 ValidationError。R15-P2-1 连续三轮未完整修复 |
| R17-P2-2 | P2 | 架构 §5.7 | — | — | 架构 §5.7 L822 consent 端点路径 `GET /auth/consent/history`，API §2.10 和切片均为 `GET /auth/consent-status`。架构端点路径与 API/切片不一致 |
| R17-P2-3 | P2 | 架构 §5.7 | — | — | 架构 §5.7 训练模块端点清单与 API/切片存在 4 处差异：(1) 架构多出 `POST /training/templates/{id}/sessions`（API/切片无此端点）；(2) 架构 `GET /training/plan/{id}/adjustments`（单数 plan）vs API/切片 `plans/{plan_id}/adjustments`（复数）；(3) 架构 `POST /training/plan/{id}/re-evaluate`（单数）vs `plans/{plan_id}/re-evaluate`（复数）；(4) 架构缺少 `GET /training/plans/{plan_id}/sessions` 和 `POST /training/plans/{plan_id}/sessions/{session_id}/complete` 两个端点 |
| R17-P2-4 | P2 | 架构 §5.7 | API §9.5 缓存 5min（L2624） | 切片 L1189 `redis.setex(cache_key, 300, ...)` 5min | 架构 §5.7 L938 progress/summary 缓存标注为 1h，与 API §9.5（5min）和切片（300s=5min）不一致。A-4 修复未回写架构 §5.7 |
| R17-P2-5 | P2 | 架构 §5.7 | — | — | 架构 §5.7 L963 引用"管理后台端点详见 API 设计 §17"，实际管理后台 API 在 §19。§17 是 Phase 4 API。引用章节号错误 |
| R17-P3-1 | P3 | payment | §12.4 L3169 业务规则说"7d 后返回 422"，但错误情况表 L3199-3206 未列出 422 条目 | 切片 L1207 正确使用 422 | API 设计错误情况表不完整，缺少 422 状态码条目 |
| R17-P3-2 | P3 | 架构 §5.7 | API §5.8 "开始比赛（状态机转换：setup → in_progress）" | 切片 L1216 "开始比赛（状态机入口）" | 架构 §5.7 L862 描述 start 端点为"开始比赛（从暂停态恢复）"，实际"从暂停态恢复"是 resume 端点的语义。描述不准确 |

**统计**：P0×0 | P1×2 | P2×5 | P3×2 | 共 9 项

---

## 8. R16 修复验证结果

| 编号 | R16 修复项 | R16 声称 | R17 验证 | 实际状态 |
|------|-----------|---------|---------|---------|
| P1-1~3 | 首页聚合端点清单三文档一致 | ✅ 已修复 | 🔴 不一致 | API §14a 与架构 §5.7 文字一致，但 00-home/frontend.md 实际调用端点不同（多了 dashboard/overview，少了 users/profile 和 training/advice/contextual） |
| P2-1 | 架构 §5.7 training/calendar→checkin-calendar | ✅ 已修复 | ✅ 已修复 | 架构 §5.7 无 training/calendar，gamification 模块为 checkin-calendar |
| R15-P2-1 | ReportDetailResponse task_uuid | 🔴 未修复 | 🟡 部分修复 | Schema 已添加 task_uuid 字段，但 Service model_validate 未注入该值，运行时会报错 |
| R15-P3-1 | training/templates 分页参数 | 🟡 未修复 | ✅ 已修复 | API §8.3 已补充 page/page_size 参数 |
| R15-P3-2 | task_id 示例值类型 | 🟡 未修复 | ✅ 已修复 | API §4.7 L1229 已改为 int 类型 12345 |
| R15-P3-3 | is_readonly 文档化 | 🟡 未修复 | ✅ 已修复 | API §4.6 L1189 已包含 is_readonly 字段 + L1195 说明 |

---

## 9. 修复优先级建议

### 9.1 P1 级（建议本轮修复）

1. **R17-P1-1（首页聚合端点清单三文档不一致）**：R16 声称三处一致但实际不一致。需选择以下方案之一：
   - **方案 A（推荐）**：更新 API §14a 和架构 §5.7 的端点清单以匹配 00-home/frontend.md 的实际实现（`GET /dashboard/overview` 替换 `GET /users/profile` + `GET /training/advice/contextual`），因为 dashboard/overview 响应体已包含 `latest_advice_summary` 字段，前端设计更合理
   - **方案 B**：更新 00-home/frontend.md 的 `services/home.ts` 增加 `GET /users/profile` 和 `GET /training/advice/contextual` 调用以匹配文档声明

2. **R17-P1-2（getCheckinCalendar 调用错误端点）**：将 `request.get('/gamification/points')` 改为 `request.get('/gamification/checkin-calendar')`。同时调整 `CheckinCalendar` 类型定义以匹配 `/gamification/checkin-calendar` 的实际响应结构。

### 9.2 P2 级（建议本轮修复）

3. **R17-P2-1（ReportDetailResponse model_validate 缺少 task_uuid 注入）**：连续三轮未完整修复。在 Service `get_report_detail` 中：
   - 查询添加 `selectinload(AnalysisReport.task)` 预加载 task 关系
   - `model_validate` 后手动注入 `data["task_uuid"] = report.task.task_uuid`

4. **R17-P2-2（架构 §5.7 consent 端点路径）**：将架构 §5.7 L822 `GET /auth/consent/history` 改为 `GET /auth/consent-status`，与 API §2.10 和切片一致。

5. **R17-P2-3（架构 §5.7 训练模块端点清单）**：
   - 删除 `POST /training/templates/{id}/sessions`（不存在的端点）
   - `GET /training/plan/{id}/adjustments` → `GET /training/plans/{plan_id}/adjustments`（单数→复数）
   - `POST /training/plan/{id}/re-evaluate` → `POST /training/plans/{plan_id}/re-evaluate`（单数→复数）
   - 补充 `GET /training/plans/{plan_id}/sessions` 和 `POST /training/plans/{plan_id}/sessions/{session_id}/complete`

6. **R17-P2-4（架构 §5.7 progress/summary 缓存 TTL）**：将架构 §5.7 L938 `缓存 1h` 改为 `缓存 5min`，与 API §9.5 和切片一致（A-4 修复回写）。

7. **R17-P2-5（架构 §5.7 管理后台引用章节号）**：将架构 §5.7 L963 `详见 API 设计 §17` 改为 `详见 API 设计 §19`。

### 9.3 P3 级（建议下一轮文档同步修复）

8. **R17-P3-1（API §12.4 refund 错误情况表缺 422）**：在 API §12.4 错误情况表（L3199-3206）补充一行 `| 422 | 下单超过 7 天，不支持退款 | 超过7天的订单不可退款 |`。

9. **R17-P3-2（架构 §5.7 scoring start 描述不准确）**：将架构 §5.7 L862 描述从"开始比赛（从暂停态恢复）"改为"开始比赛（状态机入口：setup → in_progress）"。

---

## 10. 审查结论

第十七轮 API 端点级一致性审查覆盖 79 个业务端点 + 17 个 admin 端点 = 96 个端点的逐端点对比，以及 R16 修复验证和 R15 遗留项验证。

**R16 修复验证**：
- P1-1~3（首页聚合三文档一致）：声称已修复但**实际不一致**。API §14a 与架构 §5.7 文字描述一致，但 00-home/frontend.md 实际调用的端点集合与前两者不同（多了 `/dashboard/overview`，少了 `/users/profile` 和 `/training/advice/contextual`）。
- P2-1（training/calendar→checkin-calendar）：✅ 已修复。
- R15 遗留 4 项：P3-1/P3-2/P3-3 已修复；P2-1（task_uuid）部分修复（Schema 已添加字段，但 Service 注入不完整）。

**新发现 9 项问题**（P1×2 + P2×5 + P3×2）：
- P1 级 2 项：首页聚合端点清单三文档实际不一致 + getCheckinCalendar 调用错误端点
- P2 级 5 项：ReportDetailResponse model_validate 缺 task_uuid 注入 + 架构 §5.7 三处不一致（consent 路径 / 训练端点清单 / 管理后台引用章节号）+ progress/summary 缓存 TTL 未回写
- P3 级 2 项：API refund 错误情况表缺 422 条目 + 架构 scoring start 描述不准确

**核心风险**：R17-P1-1 表明 R16 P1-1~3 的"三处完全一致"修复结论不准确，首页聚合端点清单在文档声明与前端实际实现之间存在系统性偏差。R17-P2-1（task_uuid）连续三轮未完整修复，Schema 已添加字段但 Service 方法运行时会报错。

---

> **审查结论**：第十七轮 API 端点级一致性审查发现 9 项问题（P1×2 + P2×5 + P3×2）。R16 的 P1-1~3（首页聚合三文档一致）修复结论不准确——API §14a 与架构 §5.7 文字一致但 00-home/frontend.md 实际调用端点不同。R15 遗留 P2-1（task_uuid）部分修复（Schema 有字段但 Service 注入不完整），P3-1/P3-2/P3-3 全部已修复。建议优先修复 P1 级首页聚合不一致和 getCheckinCalendar 端点错误，以及 P2 级 task_uuid Service 注入和架构 §5.7 多处不一致。
