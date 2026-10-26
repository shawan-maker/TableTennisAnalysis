"""
app/api/v1/__init__.py — API v1 路由聚合

架构约束：§5.7 端点
规范：各模块 router 在此挂载到 api_router
"""

from fastapi import APIRouter

from app.api.v1.auth.router import router as auth_router
from app.api.v1.users.router import router as users_router
from app.api.v1.scoring.router import router as scoring_router
from app.api.v1.match_data.router import router as match_data_router
from app.api.v1.video_analysis.router import router as video_analysis_router
from app.api.v1.video_analysis.router import share_router as video_share_router
from app.api.v1.dashboard.router import router as dashboard_router
from app.api.v1.gamification.router import router as gamification_router
from app.api.v1.progress.router import router as progress_router
from app.api.v1.training.router import router as training_router
from app.api.v1.membership.router import router as membership_router
from app.api.v1.payment.router import router as payment_router
from app.api.v1.notification.router import router as notification_router
from app.api.v1.admin.router import router as admin_router

api_router = APIRouter()

# 挂载各模块路由
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(scoring_router)
api_router.include_router(match_data_router)
api_router.include_router(video_analysis_router)
api_router.include_router(video_share_router)
api_router.include_router(dashboard_router)
api_router.include_router(gamification_router)
api_router.include_router(progress_router)
api_router.include_router(training_router)
api_router.include_router(membership_router)
api_router.include_router(payment_router)
api_router.include_router(notification_router)
api_router.include_router(admin_router)
