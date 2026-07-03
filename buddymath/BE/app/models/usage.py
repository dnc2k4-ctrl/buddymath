"""
usage.py – Bảng đếm mức dùng theo NGÀY để enforce quota gói (câu Toán/ảnh mỗi ngày).

Mỗi dòng = 1 (đối tượng, ngày, loại) với bộ đếm tăng dần. Bền qua restart (khác với
rate-limit chống spam nằm trong RAM ở api/ratelimit.py).

  • subject_key: "user:<id>" nếu đã đăng nhập, "ip:<addr>" nếu khách vãng lai.
  • day:        chuỗi "YYYY-MM-DD" theo UTC (mốc reset mỗi ngày).
  • metric:     "math" (câu hỏi AI/Toán) | "image" (giải bài bằng ảnh).
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, Integer, String, UniqueConstraint

from app.core.database import Base


class DailyUsage(Base):
    __tablename__ = "daily_usage"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_key = Column(String, nullable=False, index=True)   # user:<id> | ip:<addr>
    day         = Column(String, nullable=False, index=True)   # YYYY-MM-DD (UTC)
    metric      = Column(String, nullable=False)               # math | image
    count       = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("subject_key", "day", "metric", name="uq_daily_usage"),
    )
