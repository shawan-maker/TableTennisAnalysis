"""
app/api/v1/scoring/router.py — 记分牌模块 API 路由

依据：API §5 scoring 端点契约 / 切片 04-scoring/backend.md §7
规范：路由只调用 Service，禁止在路由中写业务逻辑
S2 实现：10 个 scoring 端点

R2-P1-1（批次H）：10 端点全量 response_model — schema 即契约。
统一信封 success() 返回 JSONResponse，FastAPI 对 Response 对象跳过
response_model 运行时过滤，故路由内显式 model_validate(data).model_dump()：
- 声明 response_model= 承载 OpenAPI 文档契约；
- model_validate 在运行时强制校验 service 返回 dict（schema 加键而
  service 漏给时立即 ValidationError 暴露，防止「schema 是摆设、
  手拼 dict 即线上契约」再次漂移——批次B FE-P1-6 假修复形态根源）；
- model_dump() 剔除 schema 外的多余键，响应面与文档一致。
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user
from app.core.limiter import RateLimits, limiter
from app.core.response import success
from app.models.user import User
from app.schemas.scoring import (
    FinishResponse,
    MatchAbandonResponse,
    MatchCreateRequest,
    MatchCreateResponse,
    MatchDetailWithSequence,
    MatchListResponse,
    MatchResumeResponse,
    MatchStartResponse,
    MatchStatisticResponse,
    ScoreRequest,
    ScoreResponse,
    UndoRequest,
    UndoResponse,
)
from app.services.scoring_service import ScoringService

router = APIRouter(prefix="/scoring", tags=["记分牌"])


@router.post("/matches", summary="创建比赛", response_model=MatchCreateResponse)
@limiter.limit(RateLimits.DEFAULT)
async def create_match(
    body: MatchCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """创建比赛（赛制/对手/类型）"""
    data = await ScoringService.create_match(user.id, body)
    return success(
        data=MatchCreateResponse.model_validate(data).model_dump(),
        message="比赛已创建",
    )


@router.get("/matches", summary="比赛列表", response_model=MatchListResponse)
@limiter.limit(RateLimits.DEFAULT)
async def list_matches(
    request: Request,
    status: Optional[str] = Query(default=None, description="状态过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页条数"),
    user: User = Depends(get_current_user),
):
    """比赛列表（分页）"""
    data = await ScoringService.list_matches(user.id, status, page, page_size)
    return success(data=MatchListResponse.model_validate(data).model_dump())


@router.get("/matches/{match_id}", summary="比赛详情", response_model=MatchDetailWithSequence)
@limiter.limit(RateLimits.DEFAULT)
async def get_match(
    request: Request,
    match_id: int,
    user: User = Depends(get_current_user),
):
    """比赛详情（含比分序列 + 局分 games_won_user/opp，R2-P1-1）"""
    data = await ScoringService.get_match_detail(user.id, match_id)
    return success(data=MatchDetailWithSequence.model_validate(data).model_dump())


@router.post(
    "/matches/{match_id}/start", summary="开始比赛", response_model=MatchStartResponse
)
@limiter.limit(RateLimits.DEFAULT)
async def start_match(
    request: Request,
    match_id: int,
    user: User = Depends(get_current_user),
):
    """开始比赛（状态机：setup -> in_progress）"""
    data = await ScoringService.start_match(user.id, match_id)
    return success(
        data=MatchStartResponse.model_validate(data).model_dump(), message="比赛已开始"
    )


@router.post(
    "/matches/{match_id}/score", summary="记分", response_model=ScoreResponse
)
@limiter.limit(RateLimits.DEFAULT)
async def score(
    body: ScoreRequest,
    request: Request,
    match_id: int,
    user: User = Depends(get_current_user),
):
    """记分（得分方 + 得分方式 + Redis INCR 序号）"""
    data = await ScoringService.score(user.id, match_id, body)
    return success(data=ScoreResponse.model_validate(data).model_dump())


@router.post(
    "/matches/{match_id}/undo", summary="撤销最近一球", response_model=UndoResponse
)
@limiter.limit(RateLimits.DEFAULT)
async def undo(
    request: Request,
    match_id: int,
    user: User = Depends(get_current_user),
    body: UndoRequest | None = None,
):
    """撤销最近一球（乐观并发控制）"""
    data = await ScoringService.undo(user.id, match_id, body)
    return success(data=UndoResponse.model_validate(data).model_dump())


@router.post(
    "/matches/{match_id}/finish", summary="结束比赛", response_model=FinishResponse
)
@limiter.limit(RateLimits.DEFAULT)
async def finish_match(
    request: Request,
    match_id: int,
    user: User = Depends(get_current_user),
):
    """结束比赛 -> 生成统计 + 级联创建记录"""
    data = await ScoringService.finish_match(user.id, match_id)
    return success(
        data=FinishResponse.model_validate(data).model_dump(), message="比赛已结束"
    )


@router.get(
    "/matches/{match_id}/statistics",
    summary="比赛统计",
    response_model=MatchStatisticResponse,
)
@limiter.limit(RateLimits.DEFAULT)
async def get_statistics(
    request: Request,
    match_id: int,
    user: User = Depends(get_current_user),
):
    """获取比赛统计数据"""
    data = await ScoringService.get_statistics(user.id, match_id)
    return success(data=MatchStatisticResponse.model_validate(data).model_dump())


@router.post(
    "/matches/{match_id}/abandon",
    summary="放弃比赛",
    response_model=MatchAbandonResponse,
)
@limiter.limit(RateLimits.DEFAULT)
async def abandon_match(
    request: Request,
    match_id: int,
    user: User = Depends(get_current_user),
):
    """放弃比赛（状态机：in_progress -> abandoned）"""
    data = await ScoringService.abandon_match(user.id, match_id)
    return success(
        data=MatchAbandonResponse.model_validate(data).model_dump(),
        message="比赛已放弃",
    )


@router.post(
    "/matches/{match_id}/resume",
    summary="恢复比赛",
    response_model=MatchResumeResponse,
)
@limiter.limit(RateLimits.DEFAULT)
async def resume_match(
    request: Request,
    match_id: int,
    user: User = Depends(get_current_user),
):
    """恢复放弃的比赛（状态机：abandoned -> in_progress，24h 内）"""
    data = await ScoringService.resume_match(user.id, match_id)
    return success(
        data=MatchResumeResponse.model_validate(data).model_dump(), message="比赛已恢复"
    )
