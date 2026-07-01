"""
auth.py – Router đăng ký/đăng nhập, profile và admin/debug.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user, get_current_user
from app.core.database import get_db
from app.core.security import hash_password, make_token, verify_password
from app.models.user import ParentChildLink, User
from app.schemas.auth import LoginReq, RegisterReq
from app.services.auth_service import seed_demo_accounts

router = APIRouter(tags=["auth"])


@router.post("/auth/register")
async def register(req: RegisterReq, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email.lower()).first():
        raise HTTPException(400, "Email này đã được đăng ký rồi")
    if len(req.password) < 6:
        raise HTTPException(400, "Mật khẩu phải có ít nhất 6 ký tự")
    # Đăng ký công khai chỉ cho phép student/parent — không tự cấp quyền admin
    role = req.role if req.role in ("student", "parent") else "student"
    user = User(
        email=req.email.lower(),
        username=req.username.strip(),
        password_hash=hash_password(req.password),
        role=role,
        grade=(req.grade or 5) if role == "student" else 0,
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


# ─── Admin: Quản lý người dùng (chỉ role 'admin') ──────────────────────────────
VALID_ROLES = {"student", "parent", "admin"}


def _admin_user_dict(u: User) -> dict:
    """Bản đầy đủ cho trang quản trị (gồm id thật, trạng thái, số bài đã làm)."""
    return {
        "id":          u.id,
        "email":       u.email,
        "username":    u.username,
        "role":        u.role,
        "grade":       u.grade,
        "avatar":      u.avatar,
        "is_active":   u.is_active,
        "created_at":  u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
        "score_count": len(u.scores),
    }


@router.get("/admin/users")
async def admin_list_users(
    _admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Danh sách toàn bộ tài khoản — chỉ quản trị viên.
    Mỗi tài khoản kèm thông tin liên kết phụ huynh–học sinh:
      • học sinh → danh sách phụ huynh đã liên kết (field 'linked')
      • phụ huynh → danh sách học sinh đã liên kết
    'linked' rỗng nghĩa là CHƯA liên kết với ai.
    """
    users = db.query(User).order_by(User.created_at).all()
    links = db.query(ParentChildLink).all()

    by_id = {u.id: u for u in users}
    children_of: dict[str, list] = {}   # parent_id -> [con...]
    parents_of:  dict[str, list] = {}   # child_id  -> [phụ huynh...]

    def _brief(u: User) -> dict:
        return {"id": u.id, "username": u.username, "email": u.email, "role": u.role}

    for lk in links:
        parent = by_id.get(lk.parent_id)
        child = by_id.get(lk.child_id)
        if parent and child:
            children_of.setdefault(parent.id, []).append(_brief(child))
            parents_of.setdefault(child.id, []).append(_brief(parent))

    result = []
    for u in users:
        d = _admin_user_dict(u)
        if u.role == "parent":
            d["linked"] = children_of.get(u.id, [])
        elif u.role == "student":
            d["linked"] = parents_of.get(u.id, [])
        else:
            d["linked"] = []
        result.append(d)
    return result


@router.get("/admin/stats")
async def admin_stats(
    _admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Số liệu tổng quan cho trang quản trị."""
    users = db.query(User).all()
    return {
        "total":    len(users),
        "students": sum(1 for u in users if u.role == "student"),
        "parents":  sum(1 for u in users if u.role == "parent"),
        "admins":   sum(1 for u in users if u.role == "admin"),
        "active":   sum(1 for u in users if u.is_active),
        "locked":   sum(1 for u in users if not u.is_active),
    }


@router.post("/admin/users")
async def admin_create_user(
    req: Request,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Tạo tài khoản mới từ trang quản trị."""
    body = await req.json()
    email    = (body.get("email") or "").strip().lower()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role     = body.get("role") or "student"
    grade    = body.get("grade") or 0

    if not email or not username:
        raise HTTPException(400, "Cần nhập email và tên")
    if role not in VALID_ROLES:
        raise HTTPException(400, "Vai trò không hợp lệ")
    if len(password) < 6:
        raise HTTPException(400, "Mật khẩu phải có ít nhất 6 ký tự")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email này đã được đăng ký rồi")

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        role=role,
        grade=int(grade) if role == "student" else 0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _admin_user_dict(user)


@router.patch("/admin/users/{user_id}")
async def admin_update_user(
    user_id: str,
    req: Request,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Cập nhật tên / vai trò / lớp / trạng thái khóa của một tài khoản."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    body = await req.json()

    if "username" in body and str(body["username"]).strip():
        user.username = str(body["username"]).strip()

    if "role" in body:
        new_role = body["role"]
        if new_role not in VALID_ROLES:
            raise HTTPException(400, "Vai trò không hợp lệ")
        # Không cho tự hạ cấp chính mình → tránh khóa cứng hệ thống
        if user.id == admin.id and new_role != "admin":
            raise HTTPException(400, "Không thể tự bỏ quyền quản trị của chính mình")
        # Không cho hạ cấp admin cuối cùng
        if user.role == "admin" and new_role != "admin":
            others = db.query(User).filter(User.role == "admin", User.id != user.id).count()
            if others == 0:
                raise HTTPException(400, "Phải còn ít nhất một quản trị viên")
        user.role = new_role
        if new_role != "student":
            user.grade = 0

    if "grade" in body and user.role == "student":
        user.grade = int(body["grade"])

    if "is_active" in body:
        active = bool(body["is_active"])
        if user.id == admin.id and not active:
            raise HTTPException(400, "Không thể tự khóa tài khoản của chính mình")
        user.is_active = active

    db.commit()
    db.refresh(user)
    return _admin_user_dict(user)


@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str,
    req: Request,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Đặt lại mật khẩu cho một tài khoản."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    body = await req.json()
    new_pw = body.get("password") or ""
    if len(new_pw) < 6:
        raise HTTPException(400, "Mật khẩu mới phải có ít nhất 6 ký tự")
    user.password_hash = hash_password(new_pw)
    db.commit()
    return {"status": "ok", "message": "Đã đặt lại mật khẩu"}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Xóa hẳn một tài khoản (kèm dữ liệu điểm số liên quan)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    if user.id == admin.id:
        raise HTTPException(400, "Không thể tự xóa tài khoản của chính mình")
    if user.role == "admin":
        others = db.query(User).filter(User.role == "admin", User.id != user.id).count()
        if others == 0:
            raise HTTPException(400, "Phải còn ít nhất một quản trị viên")
    db.delete(user)
    db.commit()
    return {"status": "ok", "message": "Đã xóa tài khoản"}


@router.delete("/admin/reset-demo")
async def admin_reset_demo(
    _admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Xóa và tạo lại tài khoản demo."""
    for email in ["student@demo.vn", "parent@demo.vn"]:
        u = db.query(User).filter(User.email == email).first()
        if u:
            db.delete(u)
    db.commit()
    seed_demo_accounts()
    return {"status": "ok", "message": "Đã reset tài khoản demo thành công"}
