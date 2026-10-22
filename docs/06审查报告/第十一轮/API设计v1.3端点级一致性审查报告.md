# API 设计 v1.3 ↔ 后端切片端点级一致性审查报告

> **审查日期**：2026-10-15
> **审查范围**：API 设计 v1.3（docs/04详细设计/05-API详细设计.md）vs 13 个后端切片 backend.md
> **审查方法**：141 个 API 端点定义 vs 103 处 @router 装饰器逐条比对
> **Phase 范围**：Phase 1 端点（§2~§13 + §19），Phase 2/3/4 排除

---

## 1. 审查范围

| 维度 | 说明 |
|------|------|
| API 设计 | 05-API详细设计.md v1.3（2026-10-12），共 141 个端点定义 |
| Phase 1 端点 | 96 个（§2 auth 10 + §3 user 9 + §4 video_analysis 12 + §5 scoring 10 + §6 dashboard 5 + §7 match_data 4 + §8 training 8 + §9 progress 6 + §10 gamification 4 + §11 membership 3 + §12 payment 4 + §13 notification 4 + §19 admin 17） |
| 切片实现 | 13 个模块 backend.md，103 处 @router 装饰器（含基础设施内部端点） |
| 对照维度 | 路径一致性 / HTTP 方法 / 请求参数 / 响应 Schema / 权限守卫 / 限流配置 / 状态码 / 错误码 |

---

## 2. 端点级对照矩阵

| 模块 | API 设计 | 切片实现 | 路径 | 方法 | 权限 | 限流 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| §2 auth | 10 | 10 | OK | OK | OK | P3 |
| §3 user | 9 | 9 | OK | OK | OK | OK |
| §4 video_analysis | 12 | 12 | OK | OK | OK | P1 |
| §5 scoring | 10 | 10 | OK | OK | OK | OK |
| §6 dashboard | 5 | 5 | OK | OK | OK | OK |
| §7 match_data | 4 | 4 | OK | OK | OK | OK |
| §8 training | 8 | 8 | OK | OK | P1 | OK |
| §9 progress | 6 | 6 | OK | OK | OK | OK |
| §10 gamification | 4 | 4 | OK | OK | OK | OK |
| §11 membership | 3 | 3 | OK | OK | OK | OK |
| §12 payment | 4 | 4 | OK | OK | OK | OK |
| §13 notification | 4 | 4 | OK | OK | OK | OK |
| §19 admin | 17 | 16+1 | OK | OK | OK | OK |

**端点数量完全匹配，无缺失/多余端点。PATCH vs PUT 已统一为 PATCH。**

---

## 3. 发现清单

### P0-API-001：全部 13 个切片 APIRouter prefix 与 include_router prefix 双重叠加

- **API 设计**：各章节定义路径为 /api/v1/{module}/{endpoint}
- **切片实现**：全部 13 个切片均同时声明 APIRouter(prefix=X) 和 include_router(prefix=X)，示例：
  - 01-auth/backend.md:585 router = APIRouter(prefix="/auth") + :685 include_router(prefix="/auth")
  - 02-user/backend.md:761 + :863；03-video_analysis/backend.md:1070 + :1245
  - 其余 10 个切片同模式
- **差异**：FastAPI 中 include_router(prefix=X) 会叠加到 APIRouter 已有 prefix 上。两者均为 "/auth" 时，最终路由为 /api/v1/auth/auth/wechat-login 而非 /api/v1/auth/wechat-login。全部 96 个 Phase 1 端点受影响
- **修复建议**：移除 APIRouter(prefix=...) 中的 prefix 参数，仅保留 include_router(prefix=...)；或反之

### P1-API-002：POST /video-analysis/reports/{report_id}/share 限流配置不一致

- **API 设计**：05-API详细设计.md:1316 限流 5/天；§1.5:78 报告分享 5/天
- **切片实现**：03-video_analysis/backend.md:1191 @limiter.limit("100/minute")
- **差异**：API 设计要求每日 5 次分享限制（含错误码 429），切片使用全局默认 100/min
- **修复建议**：改为 @limiter.limit("5/day", key_func=lambda r: r.state.user)

### P1-API-003：§8.3/§8.4/§8.5 训练模块权限标注与切片 SEC-003 修复不一致

- **API 设计**：§8.3 :2207 权限=登录；§8.4 :2246 权限=登录；§8.5 :2280 权限=登录
- **切片实现**：07-training_advice/backend.md:1197/1209/1219 三端点均添加 require_membership("member")
- **差异**：SEC-003 修复在切片中为三端点添加会员权限守卫，但 API 设计 v1.3 未同步回写
- **修复建议**：将 API 设计 §8.3/8.4/8.5 权限标注从"登录"改为"会员"

### P1-API-004：GET /auth/consent-status 切片缺少 consent_type 查询参数

- **API 设计**：05-API详细设计.md:469-473 §2.10 定义 consent_type 查询参数（string, N）
- **切片实现**：01-auth/backend.md:675-679 函数签名无 consent_type 参数
- **差异**：切片无法按同意类型筛选
- **修复建议**：添加 consent_type: Optional[str] = Query(default=None) 参数

### P1-API-005：video_analysis 切片重复注册路由

- **切片实现**：03-video_analysis/backend.md:1207 和 :1245 均有 include_router(video_analysis_router, prefix="/video-analysis")
- **差异**：重复注册导致全部 12 个端点被注册两次
- **修复建议**：删除 :1207 处的重复 include_router，仅保留 :1245 处
### P2-API-006：POST /auth/logout 请求体设为 Optional，API 设计要求 access_token 必填

- **API 设计**：05-API详细设计.md:319-322 §2.5 access_token 必填（Y）
- **切片实现**：01-auth/backend.md:613-615 body: LogoutRequest = None（整个 body 可选）
- **差异**：SEC-001 新增 LogoutRequest（schema 中 access_token 为必填），但路由层 body=None 使其可选。客户端不传 body 时不触发 422 而是传空字符串
- **修复建议**：将 body: LogoutRequest = None 改为 body: LogoutRequest

### P2-API-007：POST /auth/consent 请求体设为 Optional，API 设计要求字段必填

- **API 设计**：05-API详细设计.md:431-434 §2.9 consent_type=Y, policy_version=Y
- **切片实现**：01-auth/backend.md:656-659 body: ConsentRequest = None
- **差异**：客户端不传 body 时，body.consent_type 触发 AttributeError（500）而非 422
- **修复建议**：将 body: ConsentRequest = None 改为 body: ConsentRequest

### P2-API-008：§4.3 create_task 限流标注与 §1.5 全局限流表内部不一致

- **API 设计**：§4.3 :1023 限流"免费 3/天，会员无限"（未提及 10/hour）；§1.5 :77 "10/hour + 免费 3/天"
- **切片实现**：03-video_analysis/backend.md:1095 @limiter.limit("10/hour") + 服务层 Redis 3/天
- **差异**：§4.3 端点级限流字段遗漏 10/hour
- **修复建议**：将 §4.3 限流改为"10/hour + 免费 3/天，会员无限"

### P2-API-009：§12.4 refund 业务规则声明 422 但错误情况表缺失 422

- **API 设计**：§12.4 :3160 业务规则"下单 7d 后返回 422"；错误表 :3192-3197 仅有 404/400/502
- **切片实现**：11-payment/backend.md:1410-1426 422 逻辑在服务层
- **修复建议**：在 §12.4 错误表补充 422 条目；在 §1.8 补充业务错误码

### P2-API-010：page_size 上限全局规范 vs 切片实现不一致

- **API 设计**：05-API详细设计.md:46 §1.2 page_size 默认 20，最大 100
- **切片实现**：用户端 9+ 端点使用 le=50（user/video_analysis/scoring/match_data/dashboard/notification/payment）；admin 端点使用 le=100
- **修复建议**：在 §1.2 补充分级说明"用户端最大 50，管理端最大 100"，或统一为 100

### P2-API-011：§3.3 PATCH /users/rating 错误码 400 vs Schema 约束触发 422

- **API 设计**：§3.3 :632 错误 400 积分超出范围
- **切片实现**：02-user/backend.md:289 rating: int = Field(..., ge=500, le=3000)
- **差异**：Pydantic ge/le 约束超范围时自动返回 422 而非 API 设计期望的 400
- **修复建议**：Schema 去掉范围约束，在 Service 层做业务校验返回 400；或将 API 设计改为 422
### P3-API-012：§2.9 ConsentRequest consent_type 枚举未在 Schema 层强制

- **API 设计**：§2.9 consent_type 枚举 privacy_policy/user_agreement/data_processing，错误 422
- **切片实现**：01-auth/backend.md:201 consent_type: str = Field(..., max_length=32) 无枚举约束
- **修复建议**：改为 consent_type: Literal["privacy_policy", "user_agreement", "data_processing"]

### P3-API-013：§5.5 POST /scoring/matches/{match_id}/undo 切片有 Request Body 但 API 设计未定义

- **切片实现**：04-scoring/backend.md:1167 body: Optional[UndoRequest] = None；Schema expected_seq
- **修复建议**：在 API 设计 §5.5 补充 Request Body 定义

### P3-API-014：§2.9 POST /auth/consent 限流 10/min 在 API 设计中未标注

- **切片实现**：01-auth/backend.md:655 @limiter.limit("10/minute")
- **修复建议**：在 §2.9 补充限流 10/min

### P3-API-015：§12.4 refund 切片 admin 类型标注为 User 而非 AdminUser

- **切片实现**：11-payment/backend.md:1415 admin: User = Depends(get_current_admin)
- **修复建议**：改为 admin: AdminUser

### P3-API-016：§1.8 端点级业务错误码未在各端点错误情况表中显式引用

- **API 设计**：§1.8 :101-119 定义 12 个业务错误码，说明由具体端点引用
- **切片实现**：各端点错误表仅列 HTTP 状态码，未标注业务 code
- **修复建议**：在各端点错误情况表增加 code 列

### P3-API-017：§1.4 权限标注表缺少 refresh_token 权限类型

- **API 设计**：§2.4 :263 权限=refresh_token；§1.4 :58-68 权限表无 refresh_token
- **修复建议**：在 §1.4 补充 refresh_token 权限类型定义

---

## 4. 回归检查（541 项已修复项扫描）

| 修复项 | 回归状态 | 说明 |
|--------|:---:|------|
| SEC-001（logout 撤销 refresh_token） | 部分回归 | P2-API-006：LogoutRequest body 设为 None 可选 |
| SEC-002（WebSocket 子协议传 token） | 无回归 | API §14.1 与切片均使用 Sec-WebSocket-Protocol |
| SEC-003（会员权限守卫） | API 设计未回写 | P1-API-003：切片已修复但 API 设计 §8.3/8.4/8.5 仍为"登录" |
| SEC-006（支付回调不限流） | 无回归 | notify 端点无 @limiter.limit |
| R-3（训练单端点） | 无回归 | sessions 端点已实现 |
| X-25（match_data F5 编辑） | 无回归 | PATCH /records/{record_id} 已实现 |
| X-26（scoring abandoned 恢复） | 无回归 | abandon/resume 端点已实现，含 24h Celery Beat |
| F7-1~F7-5（字段命名/格式统一） | 无回归 | sequence/task_id+task_uuid 等均一致 |

---

## 5. 遗留待确认项解决

| 待确认项 | 结论 | 证据 |
|----------|------|------|
| match_data +3 积分触发是否存在 | 已确认存在 | 05-match_data/backend.md:632-641 _trigger_gamification 方法调用 GamificationService.add_points(event_type="record")，在创建记录(L699)和 F5 编辑(L772)后均触发。此前 grep 无结果系搜索模式不匹配 |
| conftest MockRedis 是否含 decrby | 已确认存在 | 13-infrastructure/conftest.py.md:268 async def decrby(self, name, amount=1) -> int。第十轮报告 P1-TEST-02 MockRedis decrby 仍缺 为误报 |

---

## 6. 汇总统计

| 优先级 | 数量 | 影响范围 |
|:---:|:---:|------|
| P0 | 1 | 全部 13 个切片 / 96 个 Phase 1 端点 |
| P1 | 4 | share 限流(1端点) + 训练权限(3端点) + consent-status(1端点) + video_analysis 重复注册(12端点) |
| P2 | 6 | logout/consent body(2端点) + create_task 限流标注(1端点) + refund 422(1端点) + page_size(9+端点) + rating 错误码(1端点) |
| P3 | 6 | consent 枚举 + undo body + consent 限流 + admin 类型 + 错误码引用 + 权限标注表 |

**最高优先修复项**：P0-API-001（双前缀，阻塞全部端点）> P1-API-002（share 限流安全风险）> P1-API-005（重复注册路由冲突）