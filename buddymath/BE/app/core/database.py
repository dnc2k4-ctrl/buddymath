"""
database.py – Khởi tạo SQLAlchemy engine, session và Base.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine       = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


def get_db():
    """FastAPI dependency: yield một DB session, đảm bảo đóng sau request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tạo toàn bộ bảng. Gọi sau khi đã import models."""
    # import models để chúng đăng ký vào Base.metadata
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
