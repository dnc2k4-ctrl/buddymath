"""
otp_service.py — Sinh & xác minh mã OTP 6 số cho email / số điện thoại.

Lưu tạm trong RAM (đủ cho 1 instance). Mã ngắn hạn (10 phút) nên việc mất khi
restart là chấp nhận được. Có chống spam (cooldown) và giới hạn số lần nhập sai.
"""
from __future__ import annotations

import hashlib
import random
import time

_OTP_TTL = 600          # mã sống 10 phút
_MAX_ATTEMPTS = 5       # nhập sai tối đa 5 lần
_RESEND_COOLDOWN = 45   # giây tối thiểu giữa 2 lần gửi

# key -> {"hash": str, "exp": float, "attempts": int, "last": float}
_store: dict[str, dict] = {}


def _key(purpose: str, target: str) -> str:
    return f"{purpose}:{target.strip().lower()}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def can_send(purpose: str, target: str) -> bool:
    """False nếu vừa gửi mã trong khoảng cooldown (chống spam)."""
    e = _store.get(_key(purpose, target))
    return not e or (time.time() - e.get("last", 0)) >= _RESEND_COOLDOWN


def create_otp(purpose: str, target: str) -> str:
    """Sinh mã 6 số mới, lưu bản băm + hạn dùng. Trả về mã gốc để đi gửi."""
    code = f"{random.randint(0, 999999):06d}"
    _store[_key(purpose, target)] = {
        "hash": _hash(code),
        "exp": time.time() + _OTP_TTL,
        "attempts": 0,
        "last": time.time(),
    }
    return code


def verify_otp(purpose: str, target: str, code: str) -> tuple[bool, str]:
    """Xác minh mã. Đúng → xoá mã (dùng 1 lần). Trả về (ok, thông báo)."""
    k = _key(purpose, target)
    e = _store.get(k)
    if not e:
        return False, "Mã không tồn tại hoặc đã hết hạn. Hãy gửi lại mã."
    if time.time() > e["exp"]:
        _store.pop(k, None)
        return False, "Mã đã hết hạn. Hãy gửi lại mã."
    if e["attempts"] >= _MAX_ATTEMPTS:
        _store.pop(k, None)
        return False, "Nhập sai quá nhiều lần. Hãy gửi lại mã mới."
    e["attempts"] += 1
    if _hash(code) != e["hash"]:
        left = _MAX_ATTEMPTS - e["attempts"]
        return False, f"Mã xác minh không đúng. Còn {left} lần thử."
    _store.pop(k, None)
    return True, "OK"
