"""
auth_routes.py – FastAPI router cho Authentication & Monitor API
Đăng nhập / đăng xuất / đăng ký cho mathbuddy-kids.html và monitor.html.
Tất cả endpoint đều ở prefix /auth

Endpoints:
  POST /auth/login          – đăng nhập, trả về token
  POST /auth/register       – đăng ký tài khoản mới (role=student, status=pending)
  POST /auth/logout         – đăng xuất, xoá session
  GET  /auth/me             – lấy thông tin user hiện tại (từ token)
  GET  /auth/check          – kiểm tra token còn hạn không

Monitor-only endpoints (yêu cầu role=admin):
  GET  /monitor                          – serve monitor.html
  GET  /monitor/stats                    – dashboard stats
  GET  /monitor/accounts                 – danh sách tài khoản (lọc theo ?status=)
  POST /monitor/accounts                 – tạo tài khoản mới
  PUT  /monitor/accounts/{id}/status     – bật/tắt tài khoản (tương thích cũ)
  PUT  /monitor/accounts/{id}/set-status – đặt status tường minh (duyệt/từ chối/khoá)
  GET  /monitor/chat-logs                – log chat có phân trang + filter
  GET  /monitor/login-logs               – log đăng nhập
  GET  /monitor/notifications              – danh sách thông báo
  GET  /monitor/notifications/unread-count – số thông báo chưa đọc (để poll)
  PUT  /monitor/notifications/{id}/read    – đánh dấu 1 thông báo đã đọc
  PUT  /monitor/notifications/read-all     – đánh dấu tất cả đã đọc
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

import db

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Pydantic models ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username:     str
    password:     str
    display_name: str = ""
    email:        str = ""

class CreateAccountRequest(BaseModel):
    username:     str
    password:     str
    role:         str  = "student"
    display_name: str  = ""
    email:        str  = ""

class ChangePasswordRequest(BaseModel):
    new_password: str

class SetStatusRequest(BaseModel):
    status: str  # 'pending' | 'active' | 'rejected' | 'disabled'

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _get_token(request: Request) -> Optional[str]:
    """Lấy token từ header Authorization hoặc cookie."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("mb_token")


def _require_auth(request: Request) -> dict:
    """Dependency: yêu cầu đăng nhập hợp lệ."""
    token = _get_token(request)
    user = db.verify_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập hoặc phiên đã hết hạn.")
    return user


def _require_admin(request: Request) -> dict:
    """Dependency: yêu cầu role=admin."""
    user = _require_auth(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Không có quyền truy cập.")
    return user


def pymssql_UniqueViolation():
    """Type cho except clause khi username trùng - PostgreSQL/psycopg2 dùng IntegrityError."""
    import psycopg2
    return psycopg2.IntegrityError


# ─── Auth endpoints ──────────────────────────────────────────────────────────

@router.post("/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    ip  = request.headers.get("X-Forwarded-For", request.client.host if request.client else "")
    ua  = request.headers.get("User-Agent", "")

    try:
        user = db.verify_login(req.username, req.password)
    except db.AccountNotActiveError as exc:
        db.log_login(req.username, success=False,
                     ip_address=ip, user_agent=ua,
                     action="failed", fail_reason=f"Account status={exc.status}")
        raise HTTPException(status_code=403, detail=str(exc))

    if not user:
        db.log_login(req.username, success=False,
                     ip_address=ip, user_agent=ua,
                     action="failed", fail_reason="Sai tên đăng nhập hoặc mật khẩu")
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu.")

    token = db.create_session(user["id"], user["username"], user["role"])
    db.log_login(user["username"], success=True, ip_address=ip, user_agent=ua)

    # Lấy phân quyền lớp học để trả về cùng lúc (tránh round-trip thứ 2)
    perms = db.get_user_permissions(user["id"])

    # Gán cookie HttpOnly
    response.set_cookie(
        key="mb_token", value=token,
        max_age=86400, httponly=True, samesite="lax",
    )
    return {
        "token":          token,
        "username":       user["username"],
        "role":           user["role"],
        "display_name":   user["display_name"],
        "email":          user.get("email", ""),
        "allowed_grades": perms.get("allowed_grades", []),
    }


@router.post("/auth/register")
async def register(req: RegisterRequest, request: Request):
    """
    Đăng ký tài khoản mới (công khai, không cần đăng nhập).
    Tài khoản được tạo với role='student', status='pending' — cần admin
    duyệt (active) trong trang Monitor trước khi đăng nhập được.
    Tạo kèm 1 thông báo cho monitor.
    """
    try:
        account_id = db.register_account(
            username=req.username,
            password=req.password,
            display_name=req.display_name,
            email=req.email,
        )
    except ValueError as exc:
        # Lỗi validate (username/password quá ngắn, v.v.)
        raise HTTPException(status_code=400, detail=str(exc))
    except pymssql_UniqueViolation():
        raise HTTPException(status_code=409, detail="Username đã tồn tại.")
    except Exception as exc:
        logger.error(f"register error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Không thể đăng ký, vui lòng thử lại.")

    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "")
    db.log_login(req.username, success=True, ip_address=ip, action="register")

    return {
        "status":  "pending",
        "id":      account_id,
        "message": "Đăng ký thành công! Tài khoản của bạn đang chờ admin duyệt.",
    }


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = _get_token(request)
    if token:
        username = ""
        sess = db.verify_session(token)
        if sess:
            username = sess.get("username", "")
        db.delete_session(token)
        ip = request.headers.get("X-Forwarded-For", "")
        db.log_login(username or "?", success=True,
                     ip_address=ip, action="logout")
    response.delete_cookie("mb_token")
    return {"status": "ok"}


@router.get("/auth/me")
async def me(request: Request):
    token = _get_token(request)
    user  = db.verify_session(token) if token else None
    if not user:
        return {"authenticated": False}
    # Lấy allowed_grades để frontend có thể ẩn lớp không được phân quyền
    perms = db.get_user_permissions(user["user_id"])
    return {
        "authenticated":  True,
        "username":       user["username"],
        "role":           user["role"],
        "display_name":   user.get("display_name", user["username"]),
        "allowed_grades": perms.get("allowed_grades", []),
    }


@router.get("/auth/check")
async def check(request: Request):
    token = _get_token(request)
    user  = db.verify_session(token) if token else None
    return {"valid": bool(user)}


# ─── Auth patch JS (script nạp vào mathbuddy-kids.html) ───────────────────────

AUTH_PATCH_JS = Path(__file__).parent / "auth_patch.js"

@router.get("/auth_patch.js")
async def serve_auth_patch_js():
    """
    Phục vụ file auth_patch.js cho <script src="auth_patch.js"> trong
    mathbuddy-kids.html. Không có route này thì request 404, khiến
    loginWithCredentials/registerAccount không tồn tại → trang báo
    "Hệ thống đăng nhập/đăng ký chưa sẵn sàng".
    """
    if not AUTH_PATCH_JS.exists():
        raise HTTPException(status_code=404, detail="auth_patch.js không tìm thấy.")
    return Response(
        content=AUTH_PATCH_JS.read_text(encoding="utf-8"),
        media_type="application/javascript",
    )


# ─── Monitor HTML ─────────────────────────────────────────────────────────────

MONITOR_HTML = Path(__file__).parent / "monitor.html"

@router.get("/monitor", response_class=HTMLResponse)
async def serve_monitor():
    if not MONITOR_HTML.exists():
        raise HTTPException(status_code=404, detail="monitor.html không tìm thấy.")
    return HTMLResponse(content=MONITOR_HTML.read_text(encoding="utf-8"))


# ─── Monitor API (admin only) ─────────────────────────────────────────────────

@router.get("/monitor/stats")
async def monitor_stats(request: Request, _=Depends(_require_admin)):
    try:
        stats = db.get_dashboard_stats()
        return stats
    except Exception as exc:
        logger.error(f"monitor_stats error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/monitor/accounts")
async def monitor_accounts(
    request: Request,
    page:      int = 1,
    page_size: int = 20,
    status:    str = "",
    _=Depends(_require_admin),
):
    try:
        rows  = db.list_accounts(page=page, page_size=page_size, status=status)
        total = db.count_accounts(status=status)
        # Chuyển datetime sang string
        for r in rows:
            for k in ("created_at", "last_login"):
                if r.get(k):
                    r[k] = str(r[k])
        return {"total": total, "page": page, "accounts": rows}
    except Exception as exc:
        logger.error(f"monitor_accounts error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/monitor/accounts")
async def monitor_create_account(
    req: CreateAccountRequest,
    _=Depends(_require_admin),
):
    try:
        uid = db.create_account(
            username=req.username,
            password=req.password,
            role=req.role,
            display_name=req.display_name,
            email=req.email,
        )
        return {"status": "ok", "id": uid}
    except pymssql_UniqueViolation():
        raise HTTPException(status_code=409, detail="Username đã tồn tại.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/monitor/accounts/{user_id}/status")
async def monitor_toggle_status(
    user_id: int,
    is_active: bool,
    _=Depends(_require_admin),
):
    """Giữ tương thích cũ: bật/tắt nhanh (map sang active/disabled)."""
    db.update_account_status(user_id, is_active)
    return {"status": "ok"}


@router.put("/monitor/accounts/{user_id}/set-status")
async def monitor_set_status(
    user_id: int,
    req: SetStatusRequest,
    _=Depends(_require_admin),
):
    """
    Đặt status tường minh cho tài khoản — dùng để duyệt (pending → active)
    hoặc từ chối (pending → rejected) tài khoản mới đăng ký, hay khoá/mở
    tài khoản bất kỳ (disabled ↔ active).
    """
    try:
        db.set_account_status(user_id, req.status)
        return {"status": "ok"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/monitor/accounts/{user_id}/password")
async def monitor_change_password(
    user_id: int,
    req: ChangePasswordRequest,
    _=Depends(_require_admin),
):
    db.change_password(user_id, req.new_password)
    return {"status": "ok"}


@router.delete("/monitor/accounts/{user_id}")
async def monitor_delete_account(
    user_id: int,
    _=Depends(_require_admin),
):
    """
    Xóa vĩnh viễn tài khoản và toàn bộ dữ liệu liên quan
    (sessions, chat_logs, login_logs, notifications).
    Thao tác không thể hoàn tác — frontend cần xác nhận trước khi gọi.
    """
    try:
        db.delete_account(user_id)
        return {"status": "ok", "deleted_id": user_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/monitor/chat-logs/usernames")
async def monitor_chat_usernames(
    _=Depends(_require_admin),
):
    """Danh sách username duy nhất đã chat (cho dropdown filter Conversations)."""
    try:
        return {"usernames": db.get_chat_usernames()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/monitor/chat-logs")
async def monitor_chat_logs(
    request: Request,
    page:       int  = 1,
    page_size:  int  = 50,
    username:   str  = "",
    route:      str  = "",
    date_from:  str  = "",
    date_to:    str  = "",
    session_id: str  = "",
    chat_only:  bool = False,
    _=Depends(_require_admin),
):
    try:
        rows  = db.get_chat_logs(
            page, page_size, username, route, date_from, date_to,
            session_id=session_id, chat_only=chat_only,
        )
        total = db.count_chat_logs(username, route)
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])
        return {"total": total, "page": page, "logs": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/monitor/login-logs")
async def monitor_login_logs(
    request: Request,
    page:      int = 1,
    page_size: int = 50,
    _=Depends(_require_admin),
):
    try:
        rows = db.get_login_logs(page, page_size)
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])
        return {"logs": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Notifications (cho trang monitor — badge + toast khi có đăng ký mới) ─────

@router.get("/monitor/notifications")
async def monitor_notifications(
    request: Request,
    page:        int  = 1,
    page_size:   int  = 20,
    unread_only: bool = False,
    _=Depends(_require_admin),
):
    try:
        rows = db.get_notifications(page=page, page_size=page_size, unread_only=unread_only)
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])
        return {"notifications": rows}
    except Exception as exc:
        logger.error(f"monitor_notifications error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/monitor/notifications/unread-count")
async def monitor_notifications_unread_count(_=Depends(_require_admin)):
    """
    Endpoint nhẹ để trang monitor poll định kỳ (vd mỗi 5s) lấy số thông báo
    chưa đọc, dùng để hiện badge số lượng mà không cần tải lại toàn bộ danh sách.
    """
    try:
        return {"unread": db.count_unread_notifications()}
    except Exception as exc:
        logger.error(f"monitor_notifications_unread_count error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/monitor/notifications/{notification_id}/read")
async def monitor_mark_notification_read(
    notification_id: int,
    _=Depends(_require_admin),
):
    db.mark_notification_read(notification_id)
    return {"status": "ok"}


@router.put("/monitor/notifications/read-all")
async def monitor_mark_all_notifications_read(_=Depends(_require_admin)):
    db.mark_all_notifications_read()
    return {"status": "ok"}


# ─── Quản lý mở rộng: sửa user / phân quyền / token stats / conversations ─────

class UpdateUserPayload(BaseModel):
    display_name: Optional[str] = None
    email:        Optional[str] = None
    role:         Optional[str] = None
    status:       Optional[str] = None
    new_password: Optional[str] = None

class PermissionsPayload(BaseModel):
    allowed_grades:    list[str] = []
    daily_token_limit: int       = 0


@router.put("/monitor/accounts/{user_id}/update")
async def monitor_update_user(
    user_id: int,
    req: UpdateUserPayload,
    _=Depends(_require_admin),
):
    """Cập nhật display_name, email, role, status và/hoặc password."""
    try:
        db.admin_update_user(
            user_id,
            display_name=req.display_name,
            email=req.email,
            role=req.role,
            status=req.status,
            new_password=req.new_password,
        )
        return {"status": "ok", "message": "Đã cập nhật tài khoản"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"monitor_update_user error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/monitor/accounts/{user_id}/permissions")
async def monitor_set_permissions(
    user_id: int,
    req: PermissionsPayload,
    _=Depends(_require_admin),
):
    """Phân quyền lớp học + giới hạn token hàng ngày cho 1 user."""
    try:
        db.set_user_permissions(user_id, req.allowed_grades, req.daily_token_limit)
        return {"status": "ok", "message": "Đã lưu phân quyền"}
    except Exception as exc:
        logger.error(f"monitor_set_permissions error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/monitor/token-stats")
async def monitor_token_stats(
    page:      int = 1,
    page_size: int = 20,
    username:  str = "",
    _=Depends(_require_admin),
):
    """Thống kê token sử dụng theo từng user (hôm nay + tổng)."""
    try:
        return db.get_token_stats(page=page, page_size=page_size, username=username)
    except Exception as exc:
        logger.error(f"monitor_token_stats error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/monitor/conversations")
async def monitor_conversations(
    page:      int = 1,
    page_size: int = 20,
    username:  str = "",
    date_from: str = "",
    date_to:   str = "",
    _=Depends(_require_admin),
):
    """Danh sách phiên hội thoại nhóm theo session_id."""
    try:
        return db.get_conversations(
            page=page, page_size=page_size,
            username=username, date_from=date_from, date_to=date_to,
        )
    except Exception as exc:
        logger.error(f"monitor_conversations error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
