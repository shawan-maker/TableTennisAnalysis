"""
app/api/v1/training/router.py - 训练建议 API 路由

依据：API 8 / 切片 07-training_advice/backend.md 6
8 个端点：advice/{report_id} / advice/contextual / templates / templates/{id}
          / plans/{id}/adjustments / plans/{id}/re-evaluate / plans/{id}/sessions / plans/{id}/sessions/{sid}/complete
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user, require_membership
from app.core.exceptions import AppException
from app.core.limiter import limiter
from app.core.response import success
from app.models.user import User
from app.services.training_service import TrainingAdviceService

router = APIRouter(prefix="/training", tags=["训练建议"])


@router.get("/advice/contextual", summary="综合训练建议")
@limiter.limit("100/minute")
async def get_contextual_advice(
    request: Request,
    user: User = Depends(get_current_user),
):
    data = await TrainingAdviceService.get_contextual_advice(user.id)
    return success(data=data)


@router.get("/advice/{report_id}", summary="基于报告的训练建议")
@limiter.limit("100/minute")
async def get_advice_by_report(
    request: Request,
    report_id: int,
    user: User = Depends(get_current_user),
):
    data = await TrainingAdviceService.get_advice_by_report(user.id, report_id)
    return success(data=data)


@router.get("/templates", summary="训练模板列表")
@limiter.limit("100/minute")
async def get_templates(
    request: Request,
    problem_id: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.get_templates(problem_id=problem_id, page=page, page_size=page_size)
    return success(data=data)


@router.get("/templates/{template_id}", summary="训练模板详情")
@limiter.limit("100/minute")
async def get_template_detail(
    request: Request,
    template_id: int,
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.get_template_detail(template_id)
    if not data:
        raise AppException("模板不存在", 404, code=40421)
    return success(data=data)


@router.get("/plans/{plan_id}/adjustments", summary="方案调整历史")
@limiter.limit("100/minute")
async def get_plan_adjustments(
    request: Request,
    plan_id: int,
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.get_plan_adjustments(user.id, plan_id)
    return success(data=data)


@router.post("/plans/{plan_id}/re-evaluate", summary="重新评估方案")
@limiter.limit("100/minute")
async def re_evaluate_plan(
    request: Request,
    plan_id: int,
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.re_evaluate_plan(user.id, plan_id)
    return success(data=data)


@router.get("/plans/{plan_id}/sessions", summary="训练单列表")
@limiter.limit("100/minute")
async def get_training_sessions(
    request: Request,
    plan_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.list_training_sessions(user.id, plan_id, page=page, page_size=page_size)
    return success(data=data)


@router.post("/plans/{plan_id}/sessions/{session_id}/complete", summary="完成训练单")
@limiter.limit("100/minute")
async def complete_training_session(
    request: Request,
    plan_id: int,
    session_id: int,
    user: User = Depends(require_membership),
):
    data = await TrainingAdviceService.complete_training_session(user.id, plan_id, session_id)
    return success(data=data)
