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
    phone:    Optional[str] = None
    code:     Optional[str] = None   # mã OTP xác minh email (nếu FE gửi)


class LoginReq(BaseModel):
    email:    str   # thực chất là "định danh": email HOẶC số điện thoại
    password: str


class SendOtpReq(BaseModel):
    email: str


class LinkChildReq(BaseModel):
    child_email: str


class SendReportReq(BaseModel):
    child_id: str
    period:   str = "week"   # week | month


class ParentAdvisorReq(BaseModel):
    child_id: str
    message:  str
    history:  list[dict] = []          # [{role: 'user'|'assistant', content: str}, ...]
    period:   str = "month"            # bối cảnh điểm số: week | month
