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

    # ---------- WeChat Pay ----------
    WECHAT_PAY_MOCK: bool = True  # 开发模式：跳过真实微信支付 API 调用
    WECHAT_MCH_ID: str = ""
    WECHAT_API_V3_KEY: str = ""
    WECHAT_CERT_SERIAL: str = ""
    WECHAT_PRIVATE_KEY: str = ""  # PEM 格式私钥（多行字符串）
    WECHAT_NOTIFY_URL: str = "https://example.com/api/v1/payment/notify"

    # ---------- Admin ----------
    ADMIN_USER_IDS: str = ""  # 逗号分隔的管理员用户 ID 列表（测试时动态设置）

    # ---------- Celery ----------
    CELERY_BROKER_URL: str = "redis://:redis_dev_pass@localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://:redis_dev_pass@localhost:6379/2"

    # ---------- File Storage (OSS) ----------
    FILE_STORAGE_MOCK: bool = True
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = ""
    OSS_ENDPOINT: str = "oss-cn-hangzhou.aliyuncs.com"
    OSS_CDN_DOMAIN: str = ""
    LOCAL_UPLOAD_DIR: str = "./tmp/uploads"

    # ---------- AI Inference ----------
    AI_INFERENCE_MOCK: bool = True
    INFERENCE_BASE_URL: str = "http://localhost:8501"
    INFERENCE_TIMEOUT: int = 300

    # ---------- LLM ----------
    LLM_ENABLED: bool = False
    LLM_API_URL: str = ""

    # ---------- Video Analysis ----------
    MAX_FILE_SIZE: int = 524288000  # 500MB
    MIN_FILE_SIZE: int = 1048576    # 1MB
    MIN_VIDEO_DURATION: int = 5
    MAX_VIDEO_DURATION: int = 600
    FREE_DAILY_ANALYSIS_LIMIT: int = 3
    SHARE_DAILY_LIMIT: int = 5
    SHARE_EXPIRE_DAYS: int = 7

    # ---------- SMS ----------
    SMS_MOCK: bool = True
    ALIYUN_SMS_ACCESS_KEY: str = ""
    ALIYUN_SMS_SECRET: str = ""
    ALIYUN_SMS_SIGN_NAME: str = ""
    ALIYUN_SMS_TEMPLATE_CODE: str = ""

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
