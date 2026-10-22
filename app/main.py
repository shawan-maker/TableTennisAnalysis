"""
app/main.py — FastAPI 应用入口

架构约束：§3 技术栈 / §5.1 认证流程 / §12 安全 / §14 部署
依据：切片 13-infrastructure/docker.md / 总览 §3.5 限流配置
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.api.v1.ws import router as ws_router
from app.core.config import settings
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
)
from app.core.limiter import RateLimitExceeded, limiter, rate_limit_exceeded_handler
from app.core.redis import close_redis, get_redis
from app.core.websocket import manager as ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 启动时初始化连接，关闭时清理资源"""
    # 启动时：验证 Redis 连接
    try:
        redis = await get_redis()
        await redis.ping()
        print(f"[{datetime.now(timezone.utc).isoformat()}] Redis connected successfully")
    except Exception as e:
        print(f"[WARNING] Redis connection failed: {e}")

    # 启动 WS Redis 中继
    await ws_manager.start_relay()

    # 确保 models 被导入（Alembic 需要）
    import app.models  # noqa: F401

    yield

    # 关闭时：停止 WS 中继
    await ws_manager.stop_relay()

    # 关闭时：清理 Redis 连接
    await close_redis()
    print(f"[{datetime.now(timezone.utc).isoformat()}] Redis connection closed")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="""
## 乒乓智能分析平台 API

面向中国乒乓球爱好者的 AI 驱动训练分析平台。

### 当前 Sprint
- **S1**：基础认证（微信登录 + 用户档案 + 免费额度）
- **S2**：记分牌 + 比赛数据 + WebSocket
- **S3**：视频分析 + Celery AI 流水线 + 分析报告
    """,
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# =================================================================
# 中间件配置
# =================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流（slowapi）
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# 异常处理
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# =================================================================
# 路由挂载
# =================================================================

app.include_router(api_router, prefix="/api/v1")
app.include_router(ws_router)  # WebSocket 端点挂载在根路径 /ws


# =================================================================
# 健康检查端点
# =================================================================

@app.get("/health", tags=["系统"], summary="健康检查")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.ENV,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/", tags=["系统"], summary="根路径")
async def root():
    """根路径 — 重定向到 API 文档"""
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
    )
