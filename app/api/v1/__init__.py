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

api_router = APIRouter()

# 挂载各模块路由
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(scoring_router)
api_router.include_router(match_data_router)

# Sprint 3+ 新增模块路由在此追加：
# api_router.include_router(video_analysis_router)
# api_router.include_router(dashboard_router)
# ...
