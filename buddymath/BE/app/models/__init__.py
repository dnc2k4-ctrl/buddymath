"""ORM models — import tất cả để đăng ký vào Base.metadata."""
from app.models.user import ParentChildLink, User
from app.models.score import ScoreRecord

__all__ = ["User", "ParentChildLink", "ScoreRecord"]
