"""
billing_service.py – Nghiệp vụ nâng gói qua VietQR + SePay.

Luồng: user tạo đơn (pending) → hiện mã VietQR (nội dung CK = mã đơn) → khách
chuyển khoản → SePay bắn webhook về server → khớp đơn theo MÃ + SỐ TIỀN → nâng gói.
"""
from __future__ import annotations

import logging
import random
import re
import string
from datetime import datetime, timedelta
from urllib.parse import quote

from sqlalchemy.orm import Session

from app import plans
from app.config import (
    BANK_ACCOUNT_NUMBER,
    BANK_CODE,
    ORDER_TTL_MIN,
)
from app.models.payment import PaymentOrder
from app.models.user import User

logger = logging.getLogger(__name__)

_CODE_RE = re.compile(r"SB[A-Z0-9]{6}")


def _gen_code() -> str:
    """Mã đơn ngắn IN HOA (SB + 6 ký tự) — làm nội dung chuyển khoản để đối soát."""
    return "SB" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def compute_amount(plan_id: str, months: int) -> int:
    price = int(plans.get_plan(plan_id).get("price", 0) or 0)
    return price * max(1, int(months or 1))


def qr_image_url(amount: int, code: str) -> str:
    """URL ảnh VietQR (SePay) — FE gắn thẳng vào <img src>. Đã điền sẵn số tiền + nội dung."""
    return (
        "https://qr.sepay.vn/img"
        f"?acc={quote(BANK_ACCOUNT_NUMBER)}"
        f"&bank={quote(BANK_CODE)}"
        f"&amount={amount}"
        f"&des={quote(code)}"
    )


def create_order(db: Session, user: User, plan_id: str, months: int) -> PaymentOrder:
    plan_id = plans.normalize_plan(plan_id)
    if plan_id not in ("standard", "premium"):
        raise ValueError("Gói không hợp lệ. Chỉ nhận 'standard' hoặc 'premium'.")
    months = max(1, min(int(months or 1), 12))
    amount = compute_amount(plan_id, months)
    if amount <= 0:
        raise ValueError("Số tiền không hợp lệ.")

    code = _gen_code()
    for _ in range(5):  # đảm bảo mã duy nhất
        if not db.query(PaymentOrder).filter(PaymentOrder.code == code).first():
            break
        code = _gen_code()

    order = PaymentOrder(
        code=code, user_id=user.id, plan=plan_id,
        months=months, amount=amount, status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def is_expired(order: PaymentOrder, now: datetime | None = None) -> bool:
    now = now or datetime.utcnow()
    return bool(order.created_at and now - order.created_at > timedelta(minutes=ORDER_TTL_MIN))


def apply_upgrade(db: Session, user: User, plan_id: str, months: int) -> None:
    """Nâng gói cho user (+N tháng); cộng dồn nếu còn hạn cùng gói."""
    plan_id = plans.normalize_plan(plan_id)
    months = max(1, int(months or 1))
    now = datetime.utcnow()
    base = user.plan_expires_at if (
        user.plan == plan_id and user.plan_expires_at and user.plan_expires_at > now
    ) else now
    user.plan = plan_id
    user.plan_expires_at = base + timedelta(days=30 * months)
    db.commit()


def _extract_code(content: str) -> str | None:
    """Tìm mã đơn dạng SBXXXXXX trong nội dung chuyển khoản."""
    if not content:
        return None
    m = _CODE_RE.search(content.upper())
    return m.group(0) if m else None


def process_sepay_webhook(db: Session, payload: dict) -> dict:
    """
    Xử lý payload webhook SePay. Idempotent: bỏ qua nếu đơn đã trả / tx trùng.
    Chỉ nâng gói khi tiền VÀO, khớp mã đơn và đủ số tiền.
    """
    ttype = str(payload.get("transferType") or payload.get("transfer_type") or "").lower()
    if ttype and ttype not in ("in", "money_in", "credit"):
        return {"ok": True, "skipped": "not incoming"}

    content = str(payload.get("content") or payload.get("description") or payload.get("addInfo") or "")
    amount = int(payload.get("transferAmount") or payload.get("amount") or 0)
    tx_id = str(payload.get("id") or payload.get("referenceCode") or payload.get("reference_number") or "")

    code = _extract_code(content)
    if not code:
        logger.info(f"[SePay] Không thấy mã đơn trong nội dung: {content!r}")
        return {"ok": True, "skipped": "no order code"}

    order = db.query(PaymentOrder).filter(PaymentOrder.code == code).first()
    if not order:
        return {"ok": True, "skipped": f"order {code} not found"}
    if order.status == "paid":
        return {"ok": True, "skipped": "already paid"}
    if tx_id and db.query(PaymentOrder).filter(PaymentOrder.sepay_tx_id == tx_id).first():
        return {"ok": True, "skipped": "duplicate tx"}
    if amount < order.amount:
        logger.warning(f"[SePay] Đơn {code}: nhận {amount} < cần {order.amount}")
        return {"ok": True, "skipped": "amount too low"}

    user = db.query(User).filter(User.id == order.user_id).first()
    if not user:
        return {"ok": True, "skipped": "user not found"}

    order.status = "paid"
    order.paid_at = datetime.utcnow()
    order.sepay_tx_id = tx_id or None
    apply_upgrade(db, user, order.plan, order.months)  # commit
    logger.info(f"[SePay] ✅ Nâng gói {order.plan} cho user {user.id} qua đơn {code}")
    return {"ok": True, "upgraded": user.id, "plan": order.plan, "code": code}
