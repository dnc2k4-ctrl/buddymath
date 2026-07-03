"""
billing.py – Thanh toán nâng gói qua VietQR + SePay.

  POST /billing/create-order      → tạo đơn pending, trả mã VietQR + thông tin CK
  GET  /billing/order-status      → FE hỏi trạng thái đơn (polling) đến khi 'paid'
  POST /billing/webhook/sepay     → SePay gọi khi có tiền vào → tự nâng gói
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import (
    BANK_ACCOUNT_NAME,
    BANK_ACCOUNT_NUMBER,
    BANK_CODE,
    ORDER_TTL_MIN,
    SEPAY_API_KEY,
)
from app.core.database import get_db
from app.models.payment import PaymentOrder
from app.models.user import User
from app.services import billing_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["billing"])


class CreateOrderReq(BaseModel):
    plan: str
    months: Optional[int] = 1


def _payment_configured() -> bool:
    return bool(BANK_ACCOUNT_NUMBER and BANK_CODE)


@router.get("/billing/config")
async def billing_config():
    """FE hỏi xem thanh toán đã bật chưa (để ẩn/hiện nút 'Nâng cấp')."""
    return {"enabled": _payment_configured()}


@router.post("/billing/create-order")
async def create_order(
    req: CreateOrderReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _payment_configured():
        raise HTTPException(503, "Thanh toán chưa được cấu hình. Vui lòng liên hệ quản trị viên.")
    try:
        order = billing_service.create_order(db, user, req.plan, req.months)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "order":            order.to_dict(),
        "qr_url":           billing_service.qr_image_url(order.amount, order.code),
        "transfer_content": order.code,
        "amount":           order.amount,
        "bank": {
            "account_number": BANK_ACCOUNT_NUMBER,
            "bank_code":      BANK_CODE,
            "account_name":   BANK_ACCOUNT_NAME,
        },
        "expires_in_min":   ORDER_TTL_MIN,
    }


@router.get("/billing/order-status")
async def order_status(
    code: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.code == code, PaymentOrder.user_id == user.id)
        .first()
    )
    if not order:
        raise HTTPException(404, "Không tìm thấy đơn hàng.")
    # Tự đánh dấu hết hạn nếu quá TTL mà chưa thanh toán (không chặn nếu đã paid).
    if order.status == "pending" and billing_service.is_expired(order):
        order.status = "expired"
        db.commit()
    return {
        "status": order.status,
        "plan":   order.plan,
        "user":   user.to_dict() if order.status == "paid" else None,
    }


@router.post("/billing/webhook/sepay")
async def sepay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    SePay gọi endpoint này khi có giao dịch. Xác thực bằng header
    `Authorization: Apikey <SEPAY_API_KEY>` (đặt trùng cấu hình trên SePay).
    Luôn trả HTTP 200 {success:true} để SePay không retry vô hạn (lỗi đã được log).
    """
    if SEPAY_API_KEY:
        auth = request.headers.get("authorization", "")
        provided = auth[7:].strip() if auth.lower().startswith("apikey ") else auth.strip()
        if provided != SEPAY_API_KEY:
            raise HTTPException(401, "Unauthorized")

    try:
        payload = await request.json()
    except Exception:
        return {"success": False, "error": "invalid json"}

    try:
        result = billing_service.process_sepay_webhook(db, payload)
        return {"success": True, **result}
    except Exception as e:  # không để SePay retry vô hạn; đã log để soi lại
        logger.warning(f"[SePay] Lỗi xử lý webhook: {e}")
        return {"success": True, "error": "processing failed (logged)"}
