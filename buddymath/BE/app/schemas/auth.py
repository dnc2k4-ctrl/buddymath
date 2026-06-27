"""Pydantic schemas cho auth & quản lý phụ huynh."""
from __future__ import annotations

from pydantic import BaseModel


class RegisterReq(BaseModel):
    email:    str
    username: str
    password: str
    role:     str = "student"
    grade:    int = 5


class LoginReq(BaseModel):
    email:    str
    password: str


class LinkChildReq(BaseModel):
    child_email: str


class SendReportReq(BaseModel):
    child_id: str
    period:   str = "week"   # week | month
