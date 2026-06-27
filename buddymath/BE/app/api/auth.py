"""
auth.py – Router đăng ký/đăng nhập, profile và admin/debug.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password, make_token, verify_password
from app.models.user import User
from app.schemas.auth import LoginReq, RegisterReq
from app.services.auth_service import seed_demo_accounts

router = APIRouter(tags=["auth"])


@router.post("/auth/register")
async def register(req: RegisterReq, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email.lower()).first():
        raise HTTPException(400, "Email này đã được đăng ký rồi")
    if len(req.password) < 6:
        raise HTTPException(400, "Mật khẩu phải có ít nhất 6 ký tự")
    user = User(
        email=req.email.lower(),
        username=req.username.strip(),
        password_hash=hash_password(req.password),
        role=req.role,
        grade=req.grade if req.role == "student" else 0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": make_token(user.id, user.role), "user": user.to_dict()}


@router.post("/auth/login")
async def login(req: LoginReq, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Email hoặc mật khẩu không đúng")
    if not user.is_active:
        raise HTTPException(403, "Tài khoản đã bị khóa")
    return {"token": make_token(user.id, user.role), "user": user.to_dict()}


@router.get("/auth/me")
async def me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()


@router.post("/auth/update-profile")
async def update_profile(
    req: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    body = await req.json()
    if "username" in body and body["username"].strip():
        current_user.username = body["username"].strip()
    if "avatar" in body:
        current_user.avatar = str(body["avatar"])
    if "grade" in body and current_user.role == "student":
        current_user.grade = int(body["grade"])
    db.commit()
    return current_user.to_dict()


# ─── Admin / Debug ────────────────────────────────────────────────────────────
@router.get("/admin/users")
async def admin_list_users(db: Session = Depends(get_db)):
    """Xem danh sách tài khoản — chỉ để debug."""
    users = db.query(User).order_by(User.created_at).all()
    return [
        {
            "id":         u.id[:8] + "…",
            "email":      u.email,
            "username":   u.username,
            "role":       u.role,
            "grade":      u.grade,
            "is_active":  u.is_active,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
        }
        for u in users
    ]


@router.delete("/admin/reset-demo")
async def admin_reset_demo(db: Session = Depends(get_db)):
    """Xóa và tạo lại tài khoản demo."""
    for email in ["student@demo.vn", "parent@demo.vn", "admin@smartbuddy.vn"]:
        u = db.query(User).filter(User.email == email).first()
        if u:
            db.delete(u)
    db.commit()
    seed_demo_accounts()
    return {"status": "ok", "message": "Đã reset tài khoản demo thành công"}
