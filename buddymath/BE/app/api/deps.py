"""
deps.py – FastAPI dependencies dùng chung (auth bearer, current user).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(401, "Chưa đăng nhập")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(401, "Token không hợp lệ hoặc đã hết hạn")
    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()  # noqa: E712
    if not user:
        raise HTTPException(401, "Tài khoản không tồn tại")
    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Chỉ cho phép tài khoản có role 'admin' đi qua."""
    if current_user.role != "admin":
        raise HTTPException(403, "Chỉ quản trị viên mới được phép thực hiện thao tác này")
    return current_user


async def get_optional_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not creds:
        return None
    payload = decode_token(creds.credentials)
    if not payload:
        return None
    return db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()  # noqa: E712
