"""
app/core/pagination.py — 分页工具

架构约束：API §1.2 分页格式 / 实施计划 §3.4
规范：page(默认1) + page_size(默认20, 用户max50, adminmax100)
响应格式：{total, page, page_size, items}
"""

from typing import Any, Generic, Optional, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    """分页响应泛型包装"""
    total: int
    page: int
    page_size: int
    items: list[T]


class PaginationParams:
    """分页参数依赖注入"""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(default=20, ge=1, le=50, description="每页条数，最大 50"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class AdminPaginationParams:
    """管理端分页参数 — page_size 最大 100"""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="页码"),
        page_size: int = Query(default=20, ge=1, le=100, description="每页条数，最大 100"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


async def paginate(
    db: AsyncSession,
    query: select,
    pagination: PaginationParams,
    *,
    count_query: Optional[select] = None,
) -> dict[str, Any]:
    """
    执行分页查询并返回标准分页格式。

    使用方式：
        pagination = PaginationParams(page=1, page_size=20)
        result = await paginate(db, select(User).order_by(User.id), pagination)

    返回：
        {"total": 58, "page": 1, "page_size": 20, "items": [...]}
    """
    # 计算总数
    if count_query is not None:
        count_result = await db.execute(count_query)
    else:
        # 从原查询构建计数查询
        count_result = await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))
    total = count_result.scalar() or 0

    # 执行分页查询
    result = await db.execute(
        query.offset(pagination.offset).limit(pagination.page_size)
    )
    items = result.scalars().all()

    return {
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "items": items,
    }
