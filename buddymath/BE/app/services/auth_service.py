"""
auth_service.py – Nghiệp vụ tài khoản: seed demo, helper user dict.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.config import ADMIN_EMAIL, ADMIN_PASSWORD, ENABLE_DEMO_ACCOUNTS
from app.core.database import SessionLocal
from app.core.security import hash_password, verify_password
from app.models.user import User

logger = logging.getLogger(__name__)

# Tài khoản demo luôn ở gói Premium "vĩnh viễn" để trình diễn ĐẦY ĐỦ mọi tính năng.
_DEMO_PREMIUM_EXPIRES = datetime(2099, 1, 1)

# Tài khoản demo student/parent — CHỈ tạo ở dev (ENABLE_DEMO_ACCOUNTS=1). Prod không có.
DEMO_ACCOUNTS = [
    {"email": "student@demo.vn", "username": "Học Sinh Demo",  "password": "demo123", "role": "student", "grade": 5},
    {"email": "parent@demo.vn",  "username": "Phụ Huynh Demo", "password": "demo123", "role": "parent",  "grade": 0},
]

_OLD_DEFAULT_ADMIN_PW = "admin123"   # mật khẩu mặc định cũ (lỗ hổng) — sẽ tự thay bằng ADMIN_PASSWORD


def seed_demo_accounts() -> None:
    """
    Seed tài khoản bootstrap AN TOÀN:
      • Demo student/parent: chỉ khi ENABLE_DEMO_ACCOUNTS (dev/local).
      • Admin: mật khẩu lấy từ ENV (ADMIN_PASSWORD). Nếu admin cũ còn dùng 'admin123'
        và đã đặt ADMIN_PASSWORD → tự đổi sang mật khẩu mới (khắc phục lỗ hổng cũ).
      • Prod không đặt ADMIN_PASSWORD → KHÔNG tạo admin mật khẩu mặc định (chỉ cảnh báo).
    """
    db = SessionLocal()
    try:
        # 1) Tài khoản demo (chỉ dev) — LUÔN Premium để xem demo mọi tính năng ─────
        if ENABLE_DEMO_ACCOUNTS:
            for d in DEMO_ACCOUNTS:
                u = db.query(User).filter(User.email == d["email"]).first()
                if not u:
                    u = User(
                        email=d["email"], username=d["username"],
                        password_hash=hash_password(d["password"]),
                        role=d["role"], grade=d["grade"],
                    )
                    db.add(u)
                    logger.info(f"[SEED] Tạo tài khoản demo: {d['email']}")
                # Mở khoá toàn bộ tính năng: đặt gói Premium hết hạn rất xa.
                if u.plan != "premium" or not u.plan_expires_at or u.plan_expires_at < _DEMO_PREMIUM_EXPIRES:
                    u.plan = "premium"
                    u.plan_expires_at = _DEMO_PREMIUM_EXPIRES
                    logger.info(f"[SEED] {d['email']} → Premium (demo, mở khoá mọi tính năng).")

        # 2) Tài khoản admin (mật khẩu từ ENV) ───────────────────────────────────
        admin_pw = ADMIN_PASSWORD or (_OLD_DEFAULT_ADMIN_PW if ENABLE_DEMO_ACCOUNTS else "")
        admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if admin_pw:
            if not admin:
                db.add(User(
                    email=ADMIN_EMAIL, username="Quản Trị Viên",
                    password_hash=hash_password(admin_pw), role="admin", grade=0,
                ))
                logger.info(f"[SEED] Tạo tài khoản admin: {ADMIN_EMAIL}")
            else:
                if admin.role != "admin":       # nâng cấp tài khoản admin cũ gán nhầm role
                    admin.role, admin.grade = "admin", 0
                    logger.info(f"[SEED] Nâng cấp role admin cho {ADMIN_EMAIL}")
                # Khắc phục lỗ hổng: admin còn dùng 'admin123' + đã có ADMIN_PASSWORD → đổi ngay.
                if ADMIN_PASSWORD and verify_password(_OLD_DEFAULT_ADMIN_PW, admin.password_hash):
                    admin.password_hash = hash_password(ADMIN_PASSWORD)
                    logger.warning(f"[SEED] Đã đổi mật khẩu admin mặc định cũ → ADMIN_PASSWORD ({ADMIN_EMAIL}).")
        else:
            # Prod chưa đặt ADMIN_PASSWORD → cảnh báo rõ, KHÔNG tạo admin yếu.
            if admin and verify_password(_OLD_DEFAULT_ADMIN_PW, admin.password_hash):
                logger.warning(
                    f"⚠️ [SEED] Admin {ADMIN_EMAIL} đang dùng mật khẩu mặc định 'admin123' nhưng CHƯA đặt "
                    f"ADMIN_PASSWORD. Hãy đặt ADMIN_PASSWORD trong môi trường rồi deploy lại để tự đổi."
                )
            elif not admin:
                logger.warning(
                    "⚠️ [SEED] Chưa có admin và chưa đặt ADMIN_PASSWORD. "
                    "Đặt ADMIN_PASSWORD trong môi trường để tạo tài khoản quản trị an toàn."
                )
        db.commit()
    except Exception as e:
        logger.warning(f"[SEED] Lỗi seed: {e}")
    finally:
        db.close()
