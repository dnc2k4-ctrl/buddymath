"""
security.py – Băm mật khẩu (bcrypt) và phát hành/giải mã JWT.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import ACCESS_TOKEN_EXPIRE_HOURS, JWT_ALGORITHM, SECRET_KEY

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(pw: str) -> str:
    return _pwd_ctx.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    return _pwd_ctx.verify(pw, hashed)


def make_token(user_id: str, role: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": exp},
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return {}
