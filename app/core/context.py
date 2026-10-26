"""
app/core/context.py — 请求级 ContextVar 定义

架构约束：§12.8 可观测性 / 切片 13-infrastructure/logging.md
功能：request_id ContextVar，供日志中间件注入、structlog processor 读取，
     实现单次请求全链路日志关联。
"""

from contextvars import ContextVar

# 请求 ID — 中间件设置，structlog processor 读取，异常处理器回写响应头
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
