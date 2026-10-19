"""
user.py – ORM models cho người dùng và liên kết phụ huynh–học sinh.
"""
from __future__ import annotations

import uuid
import math
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app import plans
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email         = Column(String, unique=True, index=True, nullable=False)
    phone         = Column(String, index=True, nullable=True)
    username      = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role          = Column(String, default="student")   # student | parent
    grade         = Column(Integer, default=5)
    avatar        = Column(String, default="1")          # 1-10 mascot pose
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    # ── Gói đăng ký (nguồn giới hạn ở app/plans.py) ──
    # plan = gói đã MUA; plan_expires_at = hạn dùng. Gói THỰC TẾ tính qua effective_plan()
    # (hết hạn tự về Free, KHÔNG gia hạn ngầm).
    plan            = Column(String, default=plans.DEFAULT_PLAN)   # free | standard | premium
    plan_expires_at = Column(DateTime, nullable=True)

    scores = relationship("ScoreRecord", back_populates="user", cascade="all, delete-orphan")

    def effective_plan(self, now: Optional[datetime] = None) -> str:
        """Gói đang thực sự hiệu lực (hết hạn → Free)."""
        return plans.effective_plan(self.plan, self.plan_expires_at, now)

    def to_dict(self) -> dict:
        now = datetime.utcnow()
        plan = self.effective_plan(now)
        trial_days = int(plans.get_plan("free").get("trialDays", 0))
        trial_ends_at = self.created_at + timedelta(days=trial_days) if self.created_at and trial_days else None
        remaining_seconds = (trial_ends_at - now).total_seconds() if trial_ends_at else 0
        subscription_plan = self.plan if (
            self.plan in ("standard", "premium") and self.plan_expires_at
        ) else None
        subscription_days_remaining = (
            math.ceil((self.plan_expires_at - now).total_seconds() / 86400)
            if subscription_plan else None
        )
        return {
            "id":       self.id,
            "email":    self.email,
            "phone":    self.phone,
            "username": self.username,
            "role":     self.role,
            "grade":    self.grade,
            "avatar":   self.avatar,
            "plan":            plan,
            "subscription_plan": subscription_plan,
            "plan_expires_at": self.plan_expires_at.isoformat() if self.plan_expires_at else None,
            "subscription_days_remaining": subscription_days_remaining,
            "trial_ends_at": trial_ends_at.isoformat() if plan == plans.DEFAULT_PLAN and trial_ends_at else None,
            "trial_days_remaining": max(0, math.ceil(remaining_seconds / 86400)) if plan == plans.DEFAULT_PLAN else None,
            "parent_access": self.role in ("student", "parent") and plans.feature_enabled(plan, "parentPortalEnabled"),
        }


class ParentChildLink(Base):
    __tablename__ = "parent_child_links"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id  = Column(String, ForeignKey("users.id"), nullable=False)
    child_id   = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Lần gửi báo cáo THEO LỊCH gần nhất (chống gửi trùng trong 1 kỳ).
    last_report_at = Column(DateTime, nullable=True)
    # Premium: lần gửi thông báo hoạt động AI trong ngày gần nhất.
    last_activity_email_at = Column(DateTime, nullable=True)
