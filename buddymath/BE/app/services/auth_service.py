"""
auth_service.py – Nghiệp vụ tài khoản: seed demo, helper user dict.
"""
from __future__ import annotations

import logging

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User

logger = logging.getLogger(__name__)

DEMO_ACCOUNTS = [
    {"email": "student@demo.vn",     "username": "Học Sinh Demo",  "password": "demo123",  "role": "student", "grade": 5},
    {"email": "parent@demo.vn",      "username": "Phụ Huynh Demo", "password": "demo123",  "role": "parent",  "grade": 0},
    {"email": "admin@smartbuddy.vn", "username": "Quản Trị Viên",  "password": "admin123", "role": "admin",   "grade": 0},
]


def seed_demo_accounts() -> None:
    """Tạo tài khoản demo mẫu nếu chưa tồn tại, và nâng cấp tài khoản admin cũ."""
    db = SessionLocal()
    try:
        for d in DEMO_ACCOUNTS:
            existing = db.query(User).filter(User.email == d["email"]).first()
            if not existing:
                db.add(User(
                    email=d["email"],
                    username=d["username"],
                    password_hash=hash_password(d["password"]),
                    role=d["role"],
                    grade=d["grade"],
                ))
                logger.info(f"[SEED] Tạo tài khoản demo: {d['email']}")
            elif existing.role != d["role"]:
                # Nâng cấp tài khoản admin cũ (trước đây gán nhầm role 'parent')
                existing.role = d["role"]
                logger.info(f"[SEED] Cập nhật role cho {d['email']} → {d['role']}")
        db.commit()
    except Exception as e:
        logger.warning(f"[SEED] Lỗi seed demo: {e}")
    finally:
        db.close()
