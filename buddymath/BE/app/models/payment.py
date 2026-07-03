"""payment.py – ORM cho đơn nâng gói (thanh toán VietQR + đối soát SePay)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.core.database import Base


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code        = Column(String, unique=True, index=True, nullable=False)  # nội dung CK để đối soát
    user_id     = Column(String, index=True, nullable=False)
    plan        = Column(String, nullable=False)     # standard | premium
    months      = Column(Integer, default=1)
    amount      = Column(Integer, nullable=False)    # VND
    status      = Column(String, default="pending", index=True)  # pending | paid | expired
    sepay_tx_id = Column(String, nullable=True)      # id giao dịch SePay (chống xử lý trùng)
    created_at  = Column(DateTime, default=datetime.utcnow)
    paid_at     = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "code":       self.code,
            "plan":       self.plan,
            "months":     self.months,
            "amount":     self.amount,
            "status":     self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "paid_at":    self.paid_at.isoformat() if self.paid_at else None,
        }
