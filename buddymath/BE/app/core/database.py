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

    # Migration nhẹ: thêm cột mới cho DB cũ chưa có (SQLite/Postgres).
    # Mỗi ALTER chạy trong transaction riêng — nếu cột đã tồn tại thì bỏ qua,
    # không làm hỏng các ALTER sau (Postgres sẽ abort cả transaction khi lỗi).
    from sqlalchemy import text
    _migrations = [
        "ALTER TABLE users ADD COLUMN phone VARCHAR",
        "ALTER TABLE users ADD COLUMN plan VARCHAR DEFAULT 'free'",
        "ALTER TABLE users ADD COLUMN plan_expires_at TIMESTAMP",
    ]
    for ddl in _migrations:
        try:
            with engine.begin() as conn:
                conn.execute(text(ddl))
        except Exception:
            pass  # cột đã tồn tại
