"""
user.py – ORM models cho người dùng và liên kết phụ huynh–học sinh.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email         = Column(String, unique=True, index=True, nullable=False)
    username      = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role          = Column(String, default="student")   # student | parent
    grade         = Column(Integer, default=5)
    avatar        = Column(String, default="1")          # 1-10 mascot pose
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    scores = relationship("ScoreRecord", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id":       self.id,
            "email":    self.email,
            "username": self.username,
            "role":     self.role,
            "grade":    self.grade,
            "avatar":   self.avatar,
        }


class ParentChildLink(Base):
    __tablename__ = "parent_child_links"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id  = Column(String, ForeignKey("users.id"), nullable=False)
    child_id   = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
