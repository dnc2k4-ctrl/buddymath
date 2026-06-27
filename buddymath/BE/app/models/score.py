"""
score.py – ORM model lưu kết quả bài làm của học sinh.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class ScoreRecord(Base):
    __tablename__ = "score_records"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    subject    = Column(String, nullable=False)   # Toán | Tiếng Anh | Kỹ năng sống
    topic      = Column(String, default="")
    score      = Column(Float, default=0)
    total      = Column(Float, default=10)
    details    = Column(Text, default="")         # JSON array kết quả từng câu
    feedback   = Column(Text, default="")         # nhận xét AI
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="scores")
