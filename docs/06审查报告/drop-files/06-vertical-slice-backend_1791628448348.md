# 垂直切片开发 — 后端模板

> 本模板指导后端切片的完整开发流程：准备 → 测试 → 实现 → 验证。
> 前置依赖：必须先阅读 `00-common-conventions.md`。

---

## 1. 切片准备清单

在写任何代码前，完成以下步骤：

- [ ] 阅读本模块的功能规格书（`templates/03-module-spec.md` 输出）
- [ ] 阅读本切片的 API 契约（`templates/05-api-contract.md` 对应节）
- [ ] 阅读 **至少一个** 已有类似模块的完整实现：
  - `service/project/models.py` — Model 模式参考
  - `service/project/schemas.py` — Schema 模式参考
  - `service/project/project_service.py` — Service 模式参考
  - `service/project/api.py` — API 路由模式参考
- [ ] 确认本切片范围（哪些 API + 哪些 Service 方法）
- [ ] 输出任务清单（按依赖排序）

### 切片任务清单模板

| # | 任务 | 文件 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 定义 Model | `service/{module}/models.py` | 无 | ☐ |
| 2 | 注册 Model | `service/core/config.py` | #1 | ☐ |
| 3 | 定义 Schema | `service/{module}/schemas.py` | #1 | ☐ |
| 4 | 实现 Service | `service/{module}/{xxx}_service.py` | #2, #3 | ☐ |
| 5 | 实现 API 路由 | `service/{module}/api.py` | #4 | ☐ |
| 6 | 注册 Router | `service/router.py` | #5 | ☐ |
| 7 | 编写测试 | `tests/{module}/test_{xxx}.py` | #4 | ☐ |
| 8 | 编写冒烟测试 | `tests/smoke/{module}_smoke_test.py` | #5 | ☐ |

---

## 2. 测试先行

### 2.1 测试文件结构

```python
# tests/{module}/test_{feature}.py
"""
{模块名} — {功能名} 测试。
覆盖：正常流程、参数校验、权限控制、业务规则。
"""
import uuid
import pytest
from service.core.exceptions import AppException

@pytest.fixture
async def ctx(db):
    """创建测试上下文：项目 + 不同角色的用户。"""
    suffix = uuid.uuid4().hex[:8]
    project = await Project.create(
        name=f"test-project-{suffix}",
        created_by=admin_user,
    )
    viewer = await create_test_user(f"viewer-{suffix}")
    editor = await create_test_user(f"editor-{suffix}")
    await add_project_member(project, viewer, role="viewer")
    await add_project_member(project, editor, role="editor")

    yield {
        "project": project,
        "viewer": viewer,
        "editor": editor,
    }

    # 清理：按依赖逆序删除
    await MyEntity.filter(project=project).delete()
    await project.delete()
```

### 2.2 四类测试用例

```python
# === 1. Happy Path（正常流程） ===
@pytest.mark.asyncio
async def test_create_entity_success(ctx):
    """editor 可以正常创建实体。"""
    result = await MyEntityService.create(ctx["editor"], MyEntityCreateRequest(
        project_id=ctx["project"].id,
        name="测试实体",
    ))
    assert result.id > 0
    assert result.name == "测试实体"

# === 2. Validation Failure（参数校验失败） ===
@pytest.mark.asyncio
async def test_create_entity_empty_name(ctx):
    """名称为空时应抛出校验错误。"""
    with pytest.raises(ValidationError):
        await MyEntityService.create(ctx["editor"], MyEntityCreateRequest(
            project_id=ctx["project"].id,
            name="",  # 空名称
        ))

# === 3. Permission Denied（权限不足） ===
@pytest.mark.asyncio
async def test_create_entity_viewer_forbidden(ctx):
    """viewer 角色不可创建实体，应返回 403。"""
    with pytest.raises(AppException) as exc:
        await MyEntityService.create(ctx["viewer"], MyEntityCreateRequest(
            project_id=ctx["project"].id,
            name="测试",
        ))
    assert exc.value.code == 403

# === 4. Business Rule Violation（业务规则违反） ===
@pytest.mark.asyncio
async def test_create_entity_duplicate_name(ctx):
    """同项目下名称不可重复，应返回 409。"""
    await MyEntityService.create(ctx["editor"], MyEntityCreateRequest(
        project_id=ctx["project"].id, name="重复名称",
    ))
    with pytest.raises(AppException) as exc:
        await MyEntityService.create(ctx["editor"], MyEntityCreateRequest(
            project_id=ctx["project"].id, name="重复名称",
        ))
    assert exc.value.code == 409
```

---

## 3. Model 实现

参考 `templates/04-data-model.md` 的完整模板。关键点：

```python
from tortoise import fields, models
from service.core.enums import SomeEnum

class MyEntity(models.Model):
    """实体描述。"""
    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project", related_name="my_entities", on_delete=fields.CASCADE,
    )
    name = fields.CharField(max_length=255)
    status = fields.CharEnumField(SomeEnum, default=SomeEnum.default_value)
    created_by = fields.ForeignKeyField(
        "models.User", related_name="created_my_entities", on_delete=fields.RESTRICT,
    )
    created_at = fields.DatetimeField(auto_now_add=True, precision=6)
    updated_at = fields.DatetimeField(auto_now=True, precision=6)

    class Meta:
        table = "my_entity"
        unique_together = (("project_id", "name"),)
```

**实现后必须**：
- [ ] 在 `service/core/config.py` 的 TORTOISE_ORM 中注册
- [ ] 运行 `python scripts/db_manage.py migrate -m "add_my_entity"`
- [ ] 运行 `python scripts/db_manage.py upgrade`

---

## 4. Schema 实现

```python
from pydantic import BaseModel, Field
from datetime import datetime
from service.core.pagination import Paginated

# --- 请求 Schema ---
class MyEntityCreateRequest(BaseModel):
    project_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None)

class MyEntityUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None

# --- 响应 Schema ---
class MyEntityBrief(BaseModel):
    id: int
    name: str
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}

class MyEntityDetail(MyEntityBrief):
    description: str | None
    created_by_name: str | None

# --- 查询 Schema ---
class MyEntityListQuery(BaseModel):
    project_id: int = Field(..., ge=1)
    q: str | None = None
    status: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

# --- 分页包装 ---
PaginatedMyEntities = Paginated[MyEntityBrief]
```

---

## 5. Service 实现

```python
from service.core.deps import ensure_project_viewer, ensure_project_editor
from service.core.exceptions import AppException
from service.core.pagination import paginate

class MyEntityService:
    """MyEntity 业务逻辑层。"""

    @classmethod
    async def _get_or_404(cls, entity_id: int) -> MyEntity:
        """获取实体，不存在则抛 404。"""
        entity = await MyEntity.get_or_none(id=entity_id)
        if not entity:
            raise AppException("资源不存在", 404)
        return entity

    @classmethod
    def _to_brief(cls, entity: MyEntity) -> MyEntityBrief:
        """ORM 对象转 Brief Schema。"""
        return MyEntityBrief(
            id=entity.id, name=entity.name,
            status=entity.status.value if hasattr(entity.status, 'value') else entity.status,
            created_at=entity.created_at,
        )

    @classmethod
    async def list_entities(cls, user, query: MyEntityListQuery) -> PaginatedMyEntities:
        """查询实体列表。权限：viewer 及以上。"""
        await ensure_project_viewer(query.project_id, user)
        qs = MyEntity.filter(project_id=query.project_id)
        if query.q:
            qs = qs.filter(name__icontains=query.q)
        if query.status:
            qs = qs.filter(status=query.status)
        qs = qs.order_by("-created_at")
        total, items = await paginate(qs, query.page, query.page_size)
        return PaginatedMyEntities(
            total=total, page=query.page, page_size=query.page_size,
            items=[cls._to_brief(i) for i in items],
        )

    @classmethod
    async def create(cls, user, data: MyEntityCreateRequest) -> MyEntityBrief:
        """创建实体。权限：editor 及以上。"""
        await ensure_project_editor(data.project_id, user)
        # 业务校验：名称唯一性
        exists = await MyEntity.exists(project_id=data.project_id, name=data.name)
        if exists:
            raise AppException(f"名称「{data.name}」已存在", 409)
        entity = await MyEntity.create(
            project_id=data.project_id,
            name=data.name,
            description=data.description,
            created_by=user,
        )
        return cls._to_brief(entity)

    @classmethod
    async def delete(cls, user, entity_id: int):
        """删除实体。权限：editor 及以上。"""
        entity = await cls._get_or_404(entity_id)
        await ensure_project_editor(entity.project_id, user)
        await entity.delete()
```

---

## 6. API 路由实现

```python
from fastapi import APIRouter, Depends, Query
from service.core.deps import get_current_active_user
from service.core.response import success
from service.user.models import User

router = APIRouter(prefix="/my-entities", tags=["模块名-资源名"])

@router.get("", summary="查询列表")
async def list_entities(
    project_id: int = Query(..., ge=1),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(get_current_active_user),
):
    query = MyEntityListQuery(
        project_id=project_id, q=q, status=status,
        page=page, page_size=page_size,
    )
    data = await MyEntityService.list_entities(user, query)
    return success(data=data)

@router.post("", summary="创建")
async def create_entity(
    body: MyEntityCreateRequest,
    user: User = Depends(get_current_active_user),
):
    data = await MyEntityService.create(user, body)
    return success(data=data, message="创建成功")

@router.get("/{entity_id}", summary="获取详情")
async def get_entity(
    entity_id: int,
    user: User = Depends(get_current_active_user),
):
    data = await MyEntityService.get_detail(user, entity_id)
    return success(data=data)

@router.patch("/{entity_id}", summary="更新")
async def update_entity(
    entity_id: int,
    body: MyEntityUpdateRequest,
    user: User = Depends(get_current_active_user),
):
    data = await MyEntityService.update(user, entity_id, body)
    return success(data=data, message="更新成功")

@router.delete("/{entity_id}", summary="删除")
async def delete_entity(
    entity_id: int,
    user: User = Depends(get_current_active_user),
):
    await MyEntityService.delete(user, entity_id)
    return success(message="删除成功")
```

**Router 注册**（`service/router.py`）：
```python
from service.{module}.api import router as my_entity_router
api_router.include_router(my_entity_router)
```

---

## 7. 冒烟测试脚本

```python
"""
{模块名} 冒烟测试。
用法: python tests/smoke/{module}_smoke_test.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi.testclient import TestClient
from main import app

def _login(client, username="admin", password="123456"):
    resp = client.post("/api/v1/auth/login",
                       data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["data"]["access_token"]

def main():
    with TestClient(app) as client:
        token = _login(client)
        h = {"Authorization": f"Bearer {token}"}

        # 获取已有项目
        projects = client.get("/api/v1/projects", headers=h).json()
        project_id = projects["data"]["items"][0]["id"]

        # 1. 创建
        create_resp = client.post("/api/v1/my-entities", headers=h, json={
            "project_id": project_id, "name": "smoke-test-entity"
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        entity_id = create_resp.json()["data"]["id"]
        print(f"  Created entity: {entity_id}")

        # 2. 查询列表
        list_resp = client.get(
            f"/api/v1/my-entities?project_id={project_id}", headers=h)
        assert list_resp.status_code == 200
        assert list_resp.json()["data"]["total"] >= 1
        print(f"  List: {list_resp.json()['data']['total']} items")

        # 3. 获取详情
        get_resp = client.get(f"/api/v1/my-entities/{entity_id}", headers=h)
        assert get_resp.status_code == 200
        print(f"  Got detail: {get_resp.json()['data']['name']}")

        # 4. 删除
        del_resp = client.delete(f"/api/v1/my-entities/{entity_id}", headers=h)
        assert del_resp.status_code == 200
        print(f"  Deleted entity: {entity_id}")

    print("\n{module}_smoke_test: ALL PASSED ✓")

if __name__ == "__main__":
    main()
```

---

## 8. 验证清单

- [ ] 单元测试全部通过：`pytest tests/{module}/ -v`
- [ ] 冒烟测试通过：`python tests/smoke/{module}_smoke_test.py`
- [ ] 后端语法检查：`python -c "import py_compile; ..."`
- [ ] Model 已注册到 `service/core/config.py`
- [ ] Router 已注册到 `service/router.py`
- [ ] 数据库迁移已生成并执行
- [ ] 代码注释完整（文件头、docstring、复杂逻辑注释）
- [ ] 无废话注释、无注释掉的死代码

---

## 反幻觉约束

- Service 方法 **必须** 使用 `@classmethod`，**禁止** 创建实例
- Schema **必须** 遵循命名：`{Entity}CreateRequest`, `{Entity}Brief`, `{Entity}Detail`, `Paginated{Entities}`
- **禁止** 在 API 路由中写业务逻辑，路由只调用 Service
- **禁止** 创建新的异常类型，统一使用 `AppException(message, code)`
- 测试 **必须** 使用 `TestClient(app)`，**禁止** 自建 HTTP 客户端
- 冒烟测试 **必须** 可作为独立脚本运行
- 实现前 **必须** 阅读至少一个已有模块的完整代码
