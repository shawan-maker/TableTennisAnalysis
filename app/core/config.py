"""
app/core/config.py — Pydantic Settings 环境变量配置

架构约束：§5.1 配置管理 / §12 安全 / §15 约束 #1
依据：切片 13-infrastructure/docker.md §6 .env.example
"""

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置 — 从 .env 环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Application ----------
    APP_NAME: str = "TableTennisAnalysis"
    ENV: str = "development"
    DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ---------- Database ----------
    DATABASE_URL: str = "postgresql+asyncpg://tta_user:tta_pass_dev@localhost:5432/tta"
    POSTGRES_DB: str = "tta"
    POSTGRES_USER: str = "tta_user"
    POSTGRES_PASSWORD: str = "tta_pass_dev"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600

    # ---------- Redis ----------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "redis_dev_pass"
    REDIS_URL: Optional[str] = None

    # ---------- JWT ----------
    JWT_SECRET_KEY: str = ""
    JWT_REFRESH_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---------- WeChat ----------
    WECHAT_APPID: str = ""
    WECHAT_APP_SECRET: str = ""

    # ---------- Celery ----------
    CELERY_BROKER_URL: str = "redis://:redis_dev_pass@localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://:redis_dev_pass@localhost:6379/2"

    # ---------- SMS ----------
    SMS_MOCK: bool = True

    # ---------- Logging ----------
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"

    # ---------- CORS ----------
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "JWT_SECRET_KEY is required. "
                "Set it in .env file. Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if len(v) < 16:
            raise ValueError("JWT_SECRET_KEY must be at least 16 characters long")
        return v

    @field_validator("JWT_REFRESH_SECRET_KEY")
    @classmethod
    def validate_jwt_refresh_secret(cls, v: str) -> str:
        if not v:
            raise ValueError("JWT_REFRESH_SECRET_KEY is required. Set it in .env file.")
        if len(v) < 16:
            raise ValueError("JWT_REFRESH_SECRET_KEY must be at least 16 characters long")
        return v

    @property
    def redis_url_computed(self) -> str:
        """计算 Redis URL，优先使用 REDIS_URL 环境变量"""
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


# 全局配置实例
settings = get_settings()
