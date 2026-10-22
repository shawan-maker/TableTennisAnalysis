"""
app/models/__init__.py — ORM Model 注册

所有 Model 在此导入，确保 Alembic 自动检测到表定义。
"""

from app.models.user import ConsentLog, RatingHistory, User

__all__ = ["User", "RatingHistory", "ConsentLog", "Base"]
