"""
auth.py – Router đăng ký/đăng nhập, profile và admin/debug.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import plans
from app.config import ENABLE_MOCK_BILLING
from app.api.deps import get_admin_user, get_current_user, get_optional_user
from app.api.ratelimit import rate_limit_auth
from app.core.database import get_db
from app.core.security import hash_password, make_token, verify_password
from app.models.user import ParentChildLink, User
from app.schemas.auth import LoginReq, RegisterReq, SendOtpReq
from app.services import otp_service, quota_service
from app.services.auth_service import seed_demo_accounts
from app.services.email_service import send_otp_email, smtp_configured

router = APIRouter(tags=["auth"])


class ForgotReq(BaseModel):
    email: str


class ResetReq(BaseModel):
    email: str
    code: str
    new_password: str


@router.post("/auth/send-otp", dependencies=[Depends(rate_limit_auth)])
async def send_register_otp(req: SendOtpReq, db: Session = Depends(get_db)):
    """Gửi mã OTP xác minh email khi ĐĂNG KÝ."""
    email = req.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email này đã được đăng ký rồi")
    if not otp_service.can_send("register", email):
        raise HTTPException(429, "Bạn vừa yêu cầu mã. Vui lòng đợi khoảng 45 giây.")
    code = otp_service.create_otp("register", email)
    resp = {"ok": True, "message": "Mã xác minh đã được gửi tới email của bạn."}
    if not smtp_configured():
        resp["dev_code"] = code
        resp["message"] = "SMTP chưa cấu hình — dùng mã dev bên dưới để thử (chỉ hiện ở dev)."
        return resp
    try:
        await asyncio.to_thread(send_otp_email, email, code, "register")
    except Exception:
        raise HTTPException(500, "Không gửi được email lúc này. Vui lòng thử lại.")
    return resp


@router.post("/auth/register", dependencies=[Depends(rate_limit_auth)])
async def register(req: RegisterReq, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email này đã được đăng ký rồi")
    if len(req.password) < 6:
        raise HTTPException(400, "Mật khẩu phải có ít nhất 6 ký tự")
    phone = (req.phone or "").strip() or None
    if phone and db.query(User).filter(User.phone == phone).first():
        raise HTTPException(400, "Số điện thoại này đã được đăng ký rồi")
    # BẮT BUỘC xác minh email bằng OTP trước khi tạo tài khoản (chống đăng ký chui/bot).
    # Tài khoản demo được seed sẵn ở server lúc khởi động nên không đi qua đây.
    code = (req.code or "").strip()
    if not code:
        raise HTTPException(400, "Vui lòng nhập mã xác minh đã gửi tới email.")
    ok, msg = otp_service.verify_otp("register", email, code)
    if not ok:
        raise HTTPException(400, msg)
    # Đăng ký công khai chỉ cho phép student/parent — không tự cấp quyền admin
    role = req.role if req.role in ("student", "parent") else "student"
    user = User(
        email=email,
        phone=phone,
        username=req.username.strip(),
        password_hash=hash_password(req.password),
        role=role,
        grade=(req.grade or 5) if role == "student" else 0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": make_token(user.id, user.role), "user": user.to_dict()}


@router.post("/auth/login", dependencies=[Depends(rate_limit_auth)])
async def login(req: LoginReq, db: Session = Depends(get_db)):
    ident = (req.email or "").strip()
    # Cho phép đăng nhập bằng EMAIL hoặc SỐ ĐIỆN THOẠI
    user = db.query(User).filter(User.email == ident.lower()).first()
    if not user and ident:
        user = db.query(User).filter(User.phone == ident).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Email/SĐT hoặc mật khẩu không đúng")
    if not user.is_active:
        raise HTTPException(403, "Tài khoản đã bị khóa")
    return {"token": make_token(user.id, user.role), "user": user.to_dict()}


@router.post("/auth/forgot-password", dependencies=[Depends(rate_limit_auth)])
async def forgot_password(req: ForgotReq, db: Session = Depends(get_db)):
    """Gửi mã OTP đặt lại mật khẩu về email. Luôn trả success để không lộ email nào tồn tại."""
    email = req.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    resp = {"ok": True, "message": "Nếu email tồn tại trong hệ thống, mã xác minh đã được gửi."}
    if not user:
        return resp
    if not otp_service.can_send("reset", email):
        raise HTTPException(429, "Bạn vừa yêu cầu mã. Vui lòng đợi khoảng 45 giây rồi thử lại.")
    code = otp_service.create_otp("reset", email)
    if not smtp_configured():
        # Chưa cấu hình SMTP (thường là môi trường dev) → trả mã để test cục bộ.
        # Trên production đã cấu hình SMTP thì KHÔNG bao giờ lộ mã.
        resp["dev_code"] = code
        resp["message"] = "SMTP chưa cấu hình — dùng mã dev bên dưới để thử (chỉ hiện ở môi trường dev)."
        return resp
    try:
        await asyncio.to_thread(send_otp_email, email, code, "reset")
    except Exception:
        raise HTTPException(500, "Không gửi được email lúc này. Vui lòng thử lại sau ít phút.")
    return resp


@router.post("/auth/reset-password", dependencies=[Depends(rate_limit_auth)])
async def reset_password(req: ResetReq, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if len(req.new_password) < 6:
        raise HTTPException(400, "Mật khẩu mới phải có ít nhất 6 ký tự")
    ok, msg = otp_service.verify_otp("reset", email, req.code)
    if not ok:
        raise HTTPException(400, msg)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"ok": True, "message": "Đặt lại mật khẩu thành công! Mời bạn đăng nhập lại."}


@router.get("/auth/me")
async def me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()


# ─── Gói đăng ký: usage hiện tại + nâng gói (mock thanh toán) ───────────────────
class UpgradeReq(BaseModel):
    plan: str                       # "standard" | "premium"
    months: Optional[int] = 1       # số tháng (mặc định 1)


@router.get("/billing/usage")
async def billing_usage(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Gói đang hiệu lực + số lượt đã dùng hôm nay (để FE hiện 'còn X lượt')."""
    return quota_service.usage_summary(db, request, user)


@router.post("/billing/mock-upgrade")
async def mock_upgrade(
    req: UpgradeReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    MOCK: xác nhận thanh toán → nâng gói cho user đang đăng nhập (+N tháng).
    ⚠️ Chưa nối cổng thanh toán thật; endpoint này chỉ để chạy thử luồng.
    Hết hạn sẽ tự về Free (KHÔNG gia hạn ngầm) nhờ effective_plan().
    ⚠️ Chỉ hoạt động khi bật ENABLE_MOCK_BILLING (dev). Production dùng thanh toán thật.
    """
    if not ENABLE_MOCK_BILLING:
        raise HTTPException(403, "Nâng gói thử nghiệm đã tắt. Vui lòng thanh toán qua chuyển khoản (VietQR).")
    if req.plan not in ("standard", "premium"):
        raise HTTPException(400, "Gói không hợp lệ. Chỉ nhận 'standard' hoặc 'premium'.")
    months = max(1, min(int(req.months or 1), 12))
    # Cộng dồn nếu đang còn hạn cùng gói, ngược lại tính từ hôm nay.
    now = datetime.utcnow()
    base = current_user.plan_expires_at if (
        current_user.plan == req.plan
        and current_user.plan_expires_at
        and current_user.plan_expires_at > now
    ) else now
    current_user.plan = req.plan
    current_user.plan_expires_at = base + timedelta(days=30 * months)
    db.commit()
    db.refresh(current_user)
    return {
        "ok": True,
        "message": f"Đã nâng cấp gói {plans.get_plan(req.plan)['name']} thành công!",
        "user": current_user.to_dict(),
    }


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
        "plan":        u.effective_plan(),
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
