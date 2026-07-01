"""Pydantic schemas cho auth & quản lý phụ huynh."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RegisterReq(BaseModel):
    email:    str
    username: str
    password: str
    role:     str = "student"
    grade:    Optional[int] = 5   # cho phép null (vd phụ huynh không có lớp)


class LoginReq(BaseModel):
    email:    str
    password: str


class LinkChildReq(BaseModel):
    child_email: str


class SendReportReq(BaseModel):
    child_id: str
    period:   str = "week"   # week | month
