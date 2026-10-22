# 系统架构设计模板

> **使用说明**：复制本模板，将 `[占位符]` 替换为实际值。所有技术版本、模块名、目录结构均为 AITestPlatform 项目的规范约束，不可随意更改。

---

## 1. 项目概述

### 1.1 系统定位

- **产品名称**：[中文名] / [英文名]
- **一句话定位**：[例如：面向QA团队的AI驱动测试管理平台，覆盖需求管理、API/功能测试、用例生成与执行报告全流程]
- **目标用户规模**：[例如：10-200人测试团队]

### 1.2 核心用户角色

| 角色 | 权限范围 | 典型操作 |
|------|---------|---------|
| Super Admin | 全局管理 | 用户管理、项目创建、系统配置 |
| Project Owner | 项目级全权 | 成员管理、模块配置、数据删除 |
| Project Editor | 项目级读写 | 创建/编辑用例、执行测试、提交缺陷 |
| Project Viewer | 项目级只读 | 查看用例、查看报告、导出结果 |

### 1.3 系统边界

| 范围内（In Scope） | 范围外（Out of Scope） |
|-------------------|----------------------|
| 需求文档管理与RAG索引 | CI/CD流水线编排 |
| API接口定义与版本管理 | 移动端App测试 |
| 功能/API测试用例CRUD | 性能压测（JMeter/Locust集成） |
| AI辅助用例生成（SSE流式） | 自动化UI录制回放 |
| 测试套件/任务/执行/报告 | 生产环境监控告警 |
| 缺陷管理与状态流转 | 第三方项目管理工具同步 |
| 测试环境与变量管理 | 容器化部署编排(K8s) |

---

## 2. 技术栈选型表

> **Anti-hallucination**: 以下版本号为本项目实际使用版本，新增技术时必须填写选型理由。

| 层 | 技术 | 版本 | 选型理由 |
|----|------|------|---------|
| 前端框架 | Vue 3 | 3.4+ | Composition API + `<script setup>` 语法糖，类型推导好 |
| UI组件库 | Element Plus | 2.7+ | 成熟稳定，组件丰富，中文文档完善 |
| 构建工具 | Vite | 5.x | 极速HMR，原生ESM，Vue官方推荐 |
| 状态管理 | Pinia | 2.x | Vue 3官方推荐，TypeScript友好 |
| 国际化 | vue-i18n | 9.x | zh-CN / en-US 双语支持 |
| HTTP客户端 | Axios | 1.x | 拦截器、自动token刷新、取消请求 |
| 代码编辑器 | Monaco Editor | 0.45+ | VS Code同款，语法高亮+智能提示 |
| 图表库 | ECharts | 5.x | 丰富的图表类型，响应式 |
| 后端框架 | FastAPI | 0.110+ | 异步原生、自动OpenAPI文档、Pydantic校验 |
| ORM | Tortoise ORM | 0.21+ | 异步原生支持，Django风格API |
| 数据库 | MySQL | 8.0+ | 团队熟悉，utf8mb4字符集 |
| 缓存 | Redis | 6+ | JWT撤销黑名单（可选降级，无Redis时跳过） |
| 认证 | python-jose + bcrypt | - | JWT access+refresh token，密码哈希 |
| AI框架 | LangGraph | 0.2+ | Agent工作流编排，支持流式输出 |
| 迁移工具 | Aerich | 0.7+ | Tortoise ORM官方迁移工具 |
| 测试框架 | pytest + pytest-asyncio | 7.x / 0.23+ | asyncio_mode=auto |

---

## 3. 系统架构图

```mermaid
graph TB
    subgraph Client["客户端"]
        Browser["浏览器 (Chrome/Edge/Firefox)"]
    end

    subgraph Frontend["前端 (Vue 3 + Vite)"]
        VueApp["Vue 3 SPA"]
        Router["vue-router + 路由守卫"]
        Store["Pinia Store"]
        AxiosClient["Axios HTTP Client"]
        SSEClient["SSE Stream Client"]
    end

    subgraph Proxy["代理层"]
        ViteProxy["Vite Dev Proxy<br/>/api → localhost:8000"]
        Nginx["Nginx (Production)<br/>静态资源 + API反代"]
    end

    subgraph Backend["后端 (FastAPI)"]
        APIRouter["API Router (/api/v1)"]
        Deps["依赖注入 (deps.py)"]
        AuthService["Auth Service (JWT)"]
        BizServices["业务服务层"]
        SSEStream["SSE Streaming<br/>(Agent Stream)"]
    end

    subgraph Data["数据层"]
        MySQL["MySQL 8.0<br/>(Tortoise ORM)"]
        Redis["Redis 6+<br/>(Token Blacklist)"]
        FileSystem["文件系统<br/>(文档上传/RAG)"]
    end

    subgraph External["外部服务"]
        LLM["LLM API<br/>(OpenAI兼容)"]
    end

    Browser --> VueApp
    VueApp --> Router & Store & AxiosClient & SSEClient
    AxiosClient --> ViteProxy
    SSEClient --> ViteProxy
    ViteProxy --> APIRouter
    Nginx --> APIRouter
    APIRouter --> Deps
    Deps --> AuthService
    Deps --> BizServices
    BizServices --> MySQL & Redis & FileSystem
    SSEStream --> LLM
    AuthService --> Redis
```

---

## 4. 模块责任矩阵

> **Anti-hallucination**: 模块名必须使用 snake_case，位于 `service/` 目录下。

| 模块 | 职责 | 核心实体 | 依赖模块 |
|------|------|---------|---------|
| `user` | 用户注册/登录、JWT认证、角色管理、超级管理员引导 | User, RefreshToken | core/security, core/redis |
| `project` | 项目CRUD、成员管理(viewer/editor/owner)、模块划分 | Project, ProjectMember, Module | user |
| `knowledge` | 文档上传/版本管理、RAG索引、Swagger/OpenAPI解析、下游导入 | Document, DocumentVersion, KnowledgeIndex | project |
| `functional_test` | 功能测试用例目录树、用例CRUD、用例导入导出 | FunctionalCase, FunctionalCatalog | project |
| `api_test` | API接口定义(版本化)、基础用例、可运行用例、调试执行、依赖推断、目录管理 | ApiInterface, ApiBaseCase, ApiRunCase, ApiCatalog | project, test_environment |
| `test_environment` | 测试环境配置、环境变量、数据库连接、文件配置、全局函数 | TestEnvironment, EnvVariable, DbConnection, GlobalFunction | project |
| `test_management` | 测试套件、测试任务、缺陷管理、用例选择器 | TestSuite, TestTask, Defect, Picker | project, functional_test, api_test |
| `test_execution` | 测试执行(串行/并行)、套件/任务运行器、进度追踪、报告、手动执行、缺陷创建 | TestRun, TestRunResult, TestReport | test_management, api_test, test_environment |
| `ai_generation` | AI Agent会话(SSE流式)、功能/API用例生成(LangGraph) | AgentSession, GenerationResult | project, knowledge, api_test, functional_test |

---

## 5. 通信架构

### 5.1 REST API 模式

```
Client → POST/GET/PUT/DELETE /api/v1/{module}/{resource}
       ← {code: 200, message: "success", data: {...}, timestamp: "..."}
```

- 统一响应格式：`service/core/response.py` → `success(data, message)`
- 统一异常处理：`service/core/exceptions.py` → `AppException(message, code)`
- 分页：`service/core/pagination.py` → `paginate(qs, page, page_size)` → `(total, items)`

### 5.2 SSE 流式传输模式

```
Client → POST /api/v1/ai-generation/stream (Accept: text/event-stream)
       ← event: phase      data: {"stage": "analyzing"}
       ← event: token      data: {"content": "..."}
       ← event: complete   data: {"result_id": "..."}
       ← event: error      data: {"message": "..."}
```

- 后端：`service/ai_generation/agent_stream.py`
- 前端：`frontend/src/utils/sse.js` (`postEventStream`, `consumeSseStream`)
- 超时：默认600s，通过 `AI_AGENT_TIMEOUT_SECONDS` 环境变量配置

### 5.3 JWT 认证流程

```mermaid
sequenceDiagram
    participant C as Client
    participant B as Backend
    participant R as Redis

    C->>B: POST /auth/login (username, password)
    B-->>C: {access_token, refresh_token}
    Note over C: 存储tokens

    C->>B: GET /api/v1/xxx (Authorization: Bearer access_token)
    B->>R: Check token jti in blacklist
    alt Token valid
        R-->>B: Not found (valid)
        B-->>C: 200 Response
    else Token revoked
        R-->>B: Found (revoked)
        B-->>C: 401 Unauthorized
    end

    C->>B: POST /auth/refresh (refresh_token)
    B-->>C: {new access_token, new refresh_token}
    Note over B: Old access_token jti added to Redis blacklist
```

---

## 6. 目录结构规范

```
AITestPlatform/
├── main.py                    # FastAPI应用入口
├── service/                   # 后端业务逻辑
│   ├── core/                  # 核心基础设施
│   │   ├── config.py          # 配置(.env)
│   │   ├── deps.py            # 依赖注入
│   │   ├── security.py        # JWT + bcrypt
│   │   ├── redis.py           # Redis客户端
│   │   ├── response.py        # 统一响应
│   │   ├── pagination.py      # 分页工具
│   │   ├── exceptions.py      # 异常定义
│   │   └── enums.py           # 领域枚举
│   ├── router.py              # 路由聚合(/api/v1)
│   ├── user/                  # 用户模块
│   ├── project/               # 项目模块
│   ├── knowledge/             # 知识库模块
│   ├── functional_test/       # 功能测试模块
│   ├── api_test/              # API测试模块
│   ├── test_environment/      # 测试环境模块
│   ├── test_management/       # 测试管理模块
│   ├── test_execution/        # 测试执行模块
│   └── ai_generation/         # AI生成模块
├── frontend/                  # 前端(Vue 3)
│   ├── src/
│   │   ├── views/             # 页面组件
│   │   ├── components/        # 通用组件
│   │   ├── stores/            # Pinia状态
│   │   ├── router/            # 路由配置
│   │   ├── api/               # API调用封装
│   │   ├── utils/             # 工具函数
│   │   ├── i18n/              # 国际化(zh-CN/en-US)
│   │   └── styles/            # SCSS样式
│   └── vite.config.js
├── tests/                     # 测试
│   ├── smoke/                 # 冒烟测试
│   └── ...                    # 单元/集成测试
├── migrations/                # Aerich数据库迁移
├── agents/                    # 独立Agent脚本
├── workflow/                  # 工作流编排
├── mcp_tools/                 # MCP工具定义
├── config/                    # RAG/LLM运行时配置
└── scripts/                   # 管理工具
```

> **Anti-hallucination**: 每个业务模块遵循 `models.py` + `api.py` + `schemas.py` + `*_service.py` 的标准结构。新增模块必须在 `service/core/config.py` 的 `TORTOISE_ORM` 中注册模型。

---

## 7. 安全规范

### 7.1 认证与授权

| 机制 | 实现 | 配置 |
|------|------|------|
| Access Token | JWT (HS256), 携带jti | 过期时间: 120分钟 (`ACCESS_TOKEN_EXPIRE_MINUTES`) |
| Refresh Token | JWT, 单独签发 | 过期时间: 7天 (`REFRESH_TOKEN_EXPIRE_DAYS`) |
| Token撤销 | Redis SET存储已撤销jti | 无Redis时优雅降级(跳过检查) |
| 密码存储 | bcrypt哈希 | 禁止明文存储 |
| 权限守卫 | FastAPI Depends链 | `get_current_active_user` → `require_project_editor/viewer/owner` |

### 7.2 CORS 配置

- 开发环境：允许 `http://localhost:5173` (Vite dev server)
- 生产环境：仅允许配置的域名
- 凭证：`allow_credentials=True`
- 方法：GET, POST, PUT, DELETE, OPTIONS

### 7.3 数据安全

- 敏感字段（密码、密钥）不在日志中打印
- 文件上传大小限制：`MAX_UPLOAD_BYTES` (默认10MB)
- SQL注入防护：全程使用Tortoise ORM参数化查询
- XSS防护：前端渲染用户内容时使用文本插值，非v-html

---

## 8. 部署架构

### 8.1 开发环境

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Vite Dev    │────▶│  FastAPI          │────▶│  MySQL 8.0  │
│  :5173       │proxy│  uvicorn :8000    │     │  :3306      │
└─────────────┘     └──────────────────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │  Redis :6379│ (可选)
                    └─────────────┘
```

### 8.2 生产环境

```
┌──────────┐     ┌─────────┐     ┌──────────────────┐     ┌─────────────┐
│  Browser  │────▶│  Nginx  │────▶│  FastAPI/Gunicorn │────▶│  MySQL 8.0  │
│           │     │  :443   │     │  (多worker)        │     │             │
└──────────┘     │  静态资源 │     └──────────────────┘     └─────────────┘
                  │  API反代  │            │
                  └─────────┘     ┌──────▼──────┐
                                  │  Redis       │
                                  └─────────────┘
```

### 8.3 环境变量清单

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | Yes | `mysql://root:123456@127.0.0.1:3306/aiTestPlatform` | MySQL连接串 |
| `REDIS_URL` | No | - | Redis连接串，缺失则禁用token黑名单 |
| `JWT_SECRET_KEY` | Yes | `change-me-in-production` | JWT签名密钥(生产必须修改) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | 120 | Access Token有效期(分钟) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | 7 | Refresh Token有效期(天) |
| `LLM_BINDING_HOST` | Yes | - | LLM API地址 |
| `LLM_BINDING_API_KEY` | Yes | - | LLM API密钥 |
| `LLM_MODEL` | No | - | 使用的模型名称 |
| `AI_AGENT_TIMEOUT_SECONDS` | No | 600 | AI Agent超时(秒) |
| `MAX_UPLOAD_BYTES` | No | 10485760 | 文件上传大小上限(字节) |

---

## Anti-Hallucination 约束

1. **技术版本**：必须与本模板第2节表格一致，不得编造版本号
2. **模块命名**：所有后端模块使用 snake_case，位于 `service/` 下
3. **目录结构**：以第6节为准，新增目录需说明理由
4. **API前缀**：所有业务API挂载在 `/api/v1` 下
5. **响应格式**：统一 `{code, message, data, timestamp}` 四字段结构
6. **模型注册**：新增Tortoise模型必须在 `service/core/config.py` 的 `TORTOISE_ORM` 中声明
