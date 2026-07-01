"""
db.py – MathBuddy Database Layer (PostgreSQL)
Quản lý:
  • Bảng accounts  – tài khoản người dùng và admin monitor
  • Bảng chat_logs – log mỗi lượt chat (session, route, tokens...)
  • Bảng login_logs – lịch sử đăng nhập (ip, user-agent, kết quả)

Thông tin kết nối (mặc định, override bằng biến môi trường):
  Host    : localhost:5432
  User    : postgres
  Password: postgres
  Database: mathbuddy

Hỗ trợ cả DATABASE_URL (vd trên Render/Heroku) — nếu biến này được set,
nó được ưu tiên dùng làm chuỗi kết nối psycopg2 trực tiếp.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# ─── Whitelist route chat thật (dùng để lọc Conversations) ───────────────────
# Chỉ các route này mới được tính là hội thoại chatbot với Buddy.
# Các route khác (classroom, synthesis, prompt, exam, v1_messages...) là
# lời gọi AI nội bộ phục vụ tính năng — không phải cuộc trò chuyện.
CHAT_ROUTES: tuple[str, ...] = (
    "chat", "chat-text", "buddy-chat",
    "theory", "exercise", "solution", "hint",
)
_CHAT_ROUTES_PH = "(" + ",".join(["%s"] * len(CHAT_ROUTES)) + ")"  # SQL IN placeholder

# ─── Cấu hình kết nối ─────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_HOST     = os.environ.get("DB_HOST",     "localhost")
DB_PORT     = int(os.environ.get("DB_PORT", "5432"))
DB_USER     = os.environ.get("DB_USER",     "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")
DB_NAME     = os.environ.get("DB_NAME",     "mathbuddy")

# Biểu thức "thời điểm hiện tại theo UTC" — thay cho GETUTCDATE() của MSSQL.
_UTC_NOW = "(now() at time zone 'utc')"


def _connect(dbname: Optional[str] = None):
    """Mở một psycopg2 connection. Ưu tiên DATABASE_URL nếu có."""
    if DATABASE_URL and dbname is None:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=dbname or DB_NAME,
    )


# ─── Connection helper ────────────────────────────────────────────────────────
@contextmanager
def get_conn():
    """Context manager trả về psycopg2 connection đã sẵn sàng."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _dict_cursor(conn):
    """Cursor trả về mỗi dòng dưới dạng dict (thay cho pymssql as_dict=True)."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ─── Khởi tạo database + bảng ────────────────────────────────────────────────
# PostgreSQL hỗ trợ CREATE TABLE IF NOT EXISTS nên có thể gửi cả khối trong
# một execute() duy nhất — an toàn để chạy lại nhiều lần.
INIT_SQL = f"""
-- Bảng tài khoản người dùng
CREATE TABLE IF NOT EXISTS accounts (
    id                SERIAL        PRIMARY KEY,
    username          VARCHAR(64)   NOT NULL UNIQUE,
    password_hash     VARCHAR(256)  NOT NULL,
    email             VARCHAR(128),
    role              VARCHAR(16)   NOT NULL DEFAULT 'student',
        -- 'student' | 'teacher' | 'admin'
    status            VARCHAR(16)   NOT NULL DEFAULT 'active',
        -- 'pending' (chờ duyệt) | 'active' | 'rejected' | 'disabled'
    display_name      VARCHAR(128),
    is_active         SMALLINT      NOT NULL DEFAULT 1,
        -- giữ lại để tương thích cũ — status là nguồn sự thật chính
    created_at        TIMESTAMP     NOT NULL DEFAULT {_UTC_NOW},
    last_login        TIMESTAMP,
    login_count       INT           NOT NULL DEFAULT 0,
    total_chats       INT           NOT NULL DEFAULT 0,
    allowed_grades    VARCHAR(200)  NOT NULL DEFAULT '[]',
    daily_token_limit INT           NOT NULL DEFAULT 0,
    total_tokens_used BIGINT        NOT NULL DEFAULT 0
);

-- Bảng thông báo cho monitor (vd: có tài khoản mới đăng ký chờ duyệt)
CREATE TABLE IF NOT EXISTS notifications (
    id            SERIAL         PRIMARY KEY,
    type          VARCHAR(32)    NOT NULL DEFAULT 'register',
        -- 'register' | (có thể mở rộng sau)
    account_id    INT,
    username      VARCHAR(64),
    display_name  VARCHAR(128),
    message       VARCHAR(512),
    is_read       SMALLINT       NOT NULL DEFAULT 0,
    created_at    TIMESTAMP      NOT NULL DEFAULT {_UTC_NOW}
);

-- Bảng log từng tin nhắn chat
CREATE TABLE IF NOT EXISTS chat_logs (
    id            SERIAL         PRIMARY KEY,
    session_id    VARCHAR(64)    NOT NULL,
    user_id       INT,                     -- FK lỏng: NULL nếu khách
    username      VARCHAR(64),
    message       TEXT           NOT NULL,
    answer        TEXT,
    route         VARCHAR(32),             -- theory/exercise/solution/hint/chat
    subject       VARCHAR(64),
    topic         VARCHAR(128),
    has_image     SMALLINT       NOT NULL DEFAULT 0,
    model         VARCHAR(64),
    duration_ms   INT,                     -- thời gian phản hồi
    tokens_used   INT            NOT NULL DEFAULT 0,
    created_at    TIMESTAMP      NOT NULL DEFAULT {_UTC_NOW}
);

-- Bảng log đăng nhập / đăng xuất
CREATE TABLE IF NOT EXISTS login_logs (
    id            SERIAL        PRIMARY KEY,
    username      VARCHAR(64)   NOT NULL,
    ip_address    VARCHAR(64),
    user_agent    VARCHAR(512),
    action        VARCHAR(16)   NOT NULL DEFAULT 'login',
        -- 'login' | 'logout' | 'failed'
    success       SMALLINT      NOT NULL DEFAULT 1,
    fail_reason   VARCHAR(256),
    created_at    TIMESTAMP     NOT NULL DEFAULT {_UTC_NOW}
);

-- Bảng session token (đơn giản, không dùng JWT ở đây)
CREATE TABLE IF NOT EXISTS sessions (
    token         VARCHAR(128) PRIMARY KEY,
    user_id       INT           NOT NULL,
    username      VARCHAR(64)   NOT NULL,
    role          VARCHAR(16)   NOT NULL,
    expires_at    TIMESTAMP     NOT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT {_UTC_NOW}
);
"""


def _migrate_existing_schema() -> None:
    """
    Đảm bảo các cột mới tồn tại trên DB đã chạy từ trước.

    PostgreSQL hỗ trợ ALTER TABLE ... ADD COLUMN IF NOT EXISTS và không có
    vấn đề "biên dịch cả batch trước khi thực thi" như SQL Server, nên phần
    migrate ở đây đơn giản hơn nhiều. Riêng cột 'status' cần backfill từ
    is_active — chỉ backfill khi cột vừa được thêm lần đầu, tránh ghi đè
    trạng thái đã đặt tay (vd 'pending').
    """
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'accounts' AND column_name = 'status'
            """
        )
        has_status_column = cur.fetchone()[0] > 0

        if not has_status_column:
            cur.execute(
                "ALTER TABLE accounts ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'"
            )
            conn.commit()
            # Tài khoản cũ coi như đã active nếu is_active=1, ngược lại disabled.
            cur.execute(
                """
                UPDATE accounts
                SET status = CASE WHEN is_active = 1 THEN 'active' ELSE 'disabled' END
                """
            )
            conn.commit()
            logger.info("Đã thêm cột 'status' vào bảng accounts và backfill dữ liệu cũ.")

        # ── Các cột mới cho phân quyền lớp + giới hạn token (xem _ensure_column) ──
        _ensure_column(cur, conn, "accounts",  "allowed_grades",     "VARCHAR(200) NOT NULL DEFAULT '[]'")
        _ensure_column(cur, conn, "accounts",  "daily_token_limit",  "INT NOT NULL DEFAULT 0")
        _ensure_column(cur, conn, "accounts",  "total_tokens_used",  "BIGINT NOT NULL DEFAULT 0")
        _ensure_column(cur, conn, "chat_logs", "tokens_used",        "INT NOT NULL DEFAULT 0")

    logger.info("Migration schema kiểm tra hoàn tất.")


def _ensure_column(cur, conn, table: str, column: str, ddl_type: str) -> None:
    """Thêm 1 cột vào bảng nếu chưa tồn tại (idempotent nhờ IF NOT EXISTS)."""
    cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type}")
    conn.commit()


def init_db() -> None:
    """Tạo database 'mathbuddy' nếu chưa có, rồi tạo các bảng."""
    # Bước 1: tạo DB nếu chưa có (kết nối vào DB hệ thống 'postgres').
    # Bỏ qua nếu dùng DATABASE_URL (DB do nhà cung cấp tạo sẵn, thường không
    # có quyền CREATE DATABASE).
    if not DATABASE_URL:
        try:
            conn_admin = _connect(dbname="postgres")
            conn_admin.autocommit = True   # CREATE DATABASE không chạy trong transaction
            cur = conn_admin.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{DB_NAME}"')
            conn_admin.close()
            logger.info(f"Database '{DB_NAME}' sẵn sàng.")
        except Exception as exc:
            logger.warning(f"Không thể tạo DB (có thể đã tồn tại): {exc}")

    # Bước 2: tạo bảng. PostgreSQL cho phép nhiều câu lệnh trong một execute().
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(INIT_SQL)
        conn.commit()
    logger.info("Tất cả bảng đã được khởi tạo.")

    # Bước 2b: migrate schema cho DB đã tồn tại từ trước (vd thêm cột status)
    _migrate_existing_schema()

    # Bước 3: seed tài khoản mặc định nếu bảng còn trống
    _seed_default_accounts()


def _seed_default_accounts() -> None:
    """Tạo tài khoản mặc định admin + student nếu chưa có."""
    defaults = [
        ("admin",   "Admin@123",   "admin",   "Administrator",       "admin@mathbuddy.local"),
        ("monitor", "Monitor@123", "admin",   "Monitor Dashboard",   "monitor@mathbuddy.local"),
        ("student1","Student@123", "student", "Học sinh mẫu",        None),
    ]
    for username, password, role, display_name, email in defaults:
        try:
            create_account(username, password, role=role,
                           display_name=display_name, email=email)
            logger.info(f"Seed account: {username} [{role}]")
        except Exception:
            pass  # đã tồn tại → bỏ qua


# ─── Password hashing (sha-256 + bcrypt-style salt) ───────────────────────────
def _hash_password(password: str) -> str:
    """Hash mật khẩu theo SHA-256 + salt đơn giản."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hashed = stored_hash.split(":", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except Exception:
        return False


# ─── Account CRUD ─────────────────────────────────────────────────────────────
def create_account(
    username: str,
    password: str,
    role: str = "student",
    display_name: str = "",
    email: str = "",
    status: str = "active",
) -> int:
    """Tạo tài khoản mới (do admin tạo trực tiếp). Trả về id. Raise nếu username đã tồn tại."""
    pw_hash = _hash_password(password)
    is_active = 1 if status == "active" else 0
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO accounts (username, password_hash, role, display_name, email, status, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (username, pw_hash, role, display_name or username, email or None, status, is_active),
        )
        row = cur.fetchone()
        return int(row[0])


def register_account(
    username: str,
    password: str,
    display_name: str = "",
    email: str = "",
) -> int:
    """
    Đăng ký tài khoản công khai (từ form đăng ký trên trang chính).
    Luôn tạo với role='student' và status='pending' — cần admin duyệt (active)
    trước khi đăng nhập được. Tạo kèm 1 notification cho monitor.
    """
    username = (username or "").strip()
    if not username:
        raise ValueError("Username không được để trống.")
    if len(username) < 3:
        raise ValueError("Username phải có ít nhất 3 ký tự.")
    if not password or len(password) < 6:
        raise ValueError("Mật khẩu phải có ít nhất 6 ký tự.")

    account_id = create_account(
        username=username,
        password=password,
        role="student",
        display_name=display_name or username,
        email=email,
        status="pending",
    )
    create_notification(
        type_="register",
        account_id=account_id,
        username=username,
        display_name=display_name or username,
        message=f"Tài khoản mới '{username}' vừa đăng ký, đang chờ duyệt.",
    )
    return account_id


def verify_login(username: str, password: str) -> Optional[dict]:
    """
    Kiểm tra đăng nhập. Trả về dict thông tin user nếu đúng & active.
    Raise AccountNotActiveError nếu tài khoản đúng password nhưng chưa active
    (pending/rejected/disabled) — để backend trả message rõ ràng cho người dùng.
    Trả về None nếu sai username/password.
    """
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT * FROM accounts WHERE username=%s",
            (username,),
        )
        row = cur.fetchone()
        if not row:
            return None
        if not _verify_password(password, row["password_hash"]):
            return None

        status = row.get("status") or ("active" if row.get("is_active") else "disabled")
        if status != "active":
            raise AccountNotActiveError(status)

        # Cập nhật last_login
        cur.execute(
            f"""
            UPDATE accounts
            SET last_login={_UTC_NOW}, login_count=login_count+1
            WHERE id=%s
            """,
            (row["id"],),
        )
        return {
            "id":           row["id"],
            "username":     row["username"],
            "role":         row["role"],
            "display_name": row["display_name"],
            "email":        row["email"],
        }


class AccountNotActiveError(Exception):
    """Raised khi login đúng password nhưng tài khoản chưa được duyệt/bị khoá."""
    def __init__(self, status: str):
        self.status = status
        messages = {
            "pending":  "Tài khoản đang chờ admin duyệt. Vui lòng quay lại sau.",
            "rejected": "Tài khoản đã bị từ chối duyệt.",
            "disabled": "Tài khoản đã bị khoá.",
        }
        super().__init__(messages.get(status, "Tài khoản chưa thể đăng nhập."))


def list_accounts(page: int = 1, page_size: int = 20, status: str = "") -> list[dict]:
    offset = (page - 1) * page_size
    where = ""
    params: tuple = ()
    if status:
        where = "WHERE status = %s"
        params = (status,)
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            f"""
            SELECT id, username, email, role, display_name, is_active, status,
                   created_at, last_login, login_count, total_chats,
                   allowed_grades, daily_token_limit, total_tokens_used
            FROM accounts
            {where}
            ORDER BY created_at DESC
            LIMIT {page_size} OFFSET {offset}
            """,
            params,
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            r = dict(r)
            try:
                r["allowed_grades"] = _json.loads(r.get("allowed_grades") or "[]")
            except Exception:
                r["allowed_grades"] = []
            result.append(r)
        return result


def count_accounts(status: str = "") -> int:
    where = ""
    params: tuple = ()
    if status:
        where = "WHERE status = %s"
        params = (status,)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM accounts {where}", params)
        return cur.fetchone()[0]


def update_account_status(user_id: int, is_active: bool) -> None:
    """Bật/tắt nhanh (giữ tương thích cũ): map sang status active/disabled."""
    status = "active" if is_active else "disabled"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE accounts SET is_active=%s, status=%s WHERE id=%s",
            (1 if is_active else 0, status, user_id),
        )


def set_account_status(user_id: int, status: str) -> None:
    """
    Đặt status tường minh: 'pending' | 'active' | 'rejected' | 'disabled'.
    Dùng cho luồng duyệt tài khoản mới đăng ký từ trang monitor.
    """
    if status not in ("pending", "active", "rejected", "disabled"):
        raise ValueError(f"Status không hợp lệ: {status}")
    is_active = 1 if status == "active" else 0
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE accounts SET status=%s, is_active=%s WHERE id=%s",
            (status, is_active, user_id),
        )


def change_password(user_id: int, new_password: str) -> None:
    pw_hash = _hash_password(new_password)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE accounts SET password_hash=%s WHERE id=%s",
            (pw_hash, user_id),
        )


# ─── Session management ───────────────────────────────────────────────────────
SESSION_TTL_HOURS = 24


def create_session(user_id: int, username: str, role: str) -> str:
    token = secrets.token_urlsafe(48)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO sessions (token, user_id, username, role, expires_at)
            VALUES (%s, %s, %s, %s,
                    {_UTC_NOW} + make_interval(hours => %s))
            """,
            (token, user_id, username, role, SESSION_TTL_HOURS),
        )
    return token


def verify_session(token: str) -> Optional[dict]:
    """Kiểm tra token hợp lệ và chưa hết hạn."""
    if not token:
        return None
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            f"""
            SELECT s.*, a.display_name
            FROM sessions s
            JOIN accounts a ON a.id = s.user_id
            WHERE s.token=%s AND s.expires_at > {_UTC_NOW}
            """,
            (token,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_session(token: str) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token=%s", (token,))


def cleanup_expired_sessions() -> int:
    """Xoá session hết hạn. Trả về số session đã xoá."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM sessions WHERE expires_at <= {_UTC_NOW}")
        return cur.rowcount


# ─── Chat Log ────────────────────────────────────────────────────────────────
def log_chat(
    session_id: str,
    message: str,
    answer: str = "",
    route: str = "",
    subject: str = "",
    topic: str = "",
    has_image: bool = False,
    model: str = "",
    duration_ms: int = 0,
    user_id: int = None,
    username: str = "",
    tokens_used: int = 0,
) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO chat_logs
                (session_id, user_id, username, message, answer,
                 route, subject, topic, has_image, model, duration_ms, tokens_used)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                user_id,
                username or None,
                message[:4000],
                answer[:4000] if answer else None,
                route or None,
                subject or None,
                topic or None,
                1 if has_image else 0,
                model or None,
                duration_ms or None,
                tokens_used or 0,
            ),
        )
        # Cập nhật total_chats nếu có user
        if user_id:
            cur.execute(
                "UPDATE accounts SET total_chats=total_chats+1 WHERE id=%s",
                (user_id,),
            )
        # Cộng dồn total_tokens_used cho user
        if user_id and tokens_used:
            cur.execute(
                "UPDATE accounts SET total_tokens_used=COALESCE(total_tokens_used,0)+%s WHERE id=%s",
                (tokens_used, user_id),
            )


def get_chat_logs(
    page: int = 1,
    page_size: int = 50,
    username: str = "",
    route: str = "",
    date_from: str = "",
    date_to: str = "",
    session_id: str = "",
    chat_only: bool = False,
) -> list[dict]:
    """
    Lấy log chat có phân trang + bộ lọc.

    chat_only=True  → chỉ lấy các route chat thật (CHAT_ROUTES whitelist).
                      Dùng khi mở modal Conversations để không hiển thị
                      lời gọi AI nội bộ (tạo đề, prompt, kiểm tra…).
    session_id      → lọc theo 1 phiên cụ thể (dùng khi mở modal hội thoại).
    """
    clauses, params = [], []
    if username:
        clauses.append("username LIKE %s")
        params.append(f"%{username}%")
    if route:
        clauses.append("route=%s")
        params.append(route)
    if date_from:
        clauses.append("created_at >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("created_at <= %s")
        params.append(date_to)
    if session_id:
        clauses.append("session_id=%s")
        params.append(session_id)
    if chat_only:
        clauses.append(f"route IN {_CHAT_ROUTES_PH}")
        params.extend(CHAT_ROUTES)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    sql = f"""
        SELECT id, session_id, username, route, subject, topic,
               has_image, model, duration_ms, created_at,
               tokens_used,
               LEFT(message, 120) AS message_preview,
               LEFT(answer,  120) AS answer_preview
        FROM chat_logs
        {where}
        ORDER BY created_at ASC
        LIMIT {page_size} OFFSET {offset}
    """
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(sql, tuple(params) if params else None)
        return [dict(r) for r in cur.fetchall()]


def count_chat_logs(username: str = "", route: str = "") -> int:
    clauses, params = [], []
    if username:
        clauses.append("username LIKE %s")
        params.append(f"%{username}%")
    if route:
        clauses.append("route=%s")
        params.append(route)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM chat_logs {where}", tuple(params) if params else None)
        return cur.fetchone()[0]


# ─── Login Log ───────────────────────────────────────────────────────────────
def log_login(
    username: str,
    success: bool,
    ip_address: str = "",
    user_agent: str = "",
    action: str = "login",
    fail_reason: str = "",
) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO login_logs
                (username, ip_address, user_agent, action, success, fail_reason)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                username,
                ip_address or None,
                (user_agent or "")[:500],
                action,
                1 if success else 0,
                fail_reason or None,
            ),
        )


def get_login_logs(page: int = 1, page_size: int = 50) -> list[dict]:
    offset = (page - 1) * page_size
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            f"""
            SELECT id, username, ip_address, action, success,
                   fail_reason, created_at
            FROM login_logs
            ORDER BY created_at DESC
            LIMIT {page_size} OFFSET {offset}
            """
        )
        return [dict(r) for r in cur.fetchall()]


# ─── Dashboard Stats ─────────────────────────────────────────────────────────
def get_dashboard_stats() -> dict:
    """Trả về các số liệu tổng hợp cho trang monitor."""
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM accounts WHERE is_active=1")
        active_users = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM accounts WHERE role='student'")
        total_students = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM chat_logs")
        total_chats = cur.fetchone()[0]

        cur.execute(
            f"SELECT COUNT(*) FROM chat_logs "
            f"WHERE created_at >= CAST({_UTC_NOW} AS DATE)"
        )
        chats_today = cur.fetchone()[0]

        cur.execute(
            f"SELECT COUNT(*) FROM login_logs "
            f"WHERE action='login' AND success=1 "
            f"AND created_at >= CAST({_UTC_NOW} AS DATE)"
        )
        logins_today = cur.fetchone()[0]

        cur.execute(
            f"SELECT COUNT(*) FROM login_logs "
            f"WHERE (action='failed' OR success=0) "
            f"AND created_at >= CAST({_UTC_NOW} AS DATE)"
        )
        failed_logins_today = cur.fetchone()[0]

        cur.execute(
            """
            SELECT route, COUNT(*) as cnt
            FROM chat_logs
            WHERE route IS NOT NULL
            GROUP BY route
            ORDER BY cnt DESC
            LIMIT 5
            """
        )
        top_routes = [{"route": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            f"""
            SELECT CAST(created_at AS DATE) as day,
                   COUNT(*) as cnt
            FROM chat_logs
            WHERE created_at >= CAST({_UTC_NOW} AS DATE) - 6
            GROUP BY CAST(created_at AS DATE)
            ORDER BY day
            LIMIT 7
            """
        )
        chats_by_day = [
            {"day": str(r[0]), "count": r[1]} for r in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT username, COUNT(*) as cnt
            FROM chat_logs
            WHERE username IS NOT NULL
            GROUP BY username
            ORDER BY cnt DESC
            LIMIT 5
            """
        )
        top_users = [{"username": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute("SELECT AVG(duration_ms::float8) FROM chat_logs WHERE duration_ms > 0")
        avg_duration = cur.fetchone()[0] or 0

        return {
            "active_users":        active_users,
            "total_students":      total_students,
            "total_chats":         total_chats,
            "chats_today":         chats_today,
            "logins_today":        logins_today,
            "failed_logins_today": failed_logins_today,
            "top_routes":          top_routes,
            "chats_by_day":        chats_by_day,
            "top_users":           top_users,
            "avg_response_ms":     round(avg_duration, 1),
        }


# ─── Notifications (cho trang monitor) ───────────────────────────────────────
def create_notification(
    type_: str,
    message: str,
    account_id: int = None,
    username: str = "",
    display_name: str = "",
) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO notifications (type, account_id, username, display_name, message)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (type_, account_id, username or None, display_name or None, message),
        )
        return int(cur.fetchone()[0])


def get_notifications(page: int = 1, page_size: int = 20, unread_only: bool = False) -> list[dict]:
    offset = (page - 1) * page_size
    where = "WHERE is_read = 0" if unread_only else ""
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            f"""
            SELECT id, type, account_id, username, display_name, message, is_read, created_at
            FROM notifications
            {where}
            ORDER BY created_at DESC
            LIMIT {page_size} OFFSET {offset}
            """
        )
        return [dict(r) for r in cur.fetchall()]


def count_unread_notifications() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0")
        return cur.fetchone()[0]


def mark_notification_read(notification_id: int) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE notifications SET is_read = 1 WHERE id = %s",
            (notification_id,),
        )


def mark_all_notifications_read() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")


# ─── Phân quyền lớp học + giới hạn token (admin update / permissions) ─────────

def admin_update_user(
    user_id: int,
    display_name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    new_password: Optional[str] = None,
) -> None:
    """Sửa thông tin tài khoản. Chỉ cập nhật các field không None."""
    sets, params = [], []

    if display_name is not None:
        sets.append("display_name=%s")
        params.append(display_name[:200])

    if email is not None:
        sets.append("email=%s")
        params.append(email[:200])

    if role is not None:
        if role not in ("student", "teacher", "admin"):
            raise ValueError(f"Vai trò không hợp lệ: {role}")
        sets.append("role=%s")
        params.append(role)

    if status is not None:
        if status not in ("active", "disabled", "pending", "rejected"):
            raise ValueError(f"Trạng thái không hợp lệ: {status}")
        sets.append("status=%s")
        params.append(status)
        sets.append("is_active=%s")
        params.append(1 if status == "active" else 0)

    if new_password and new_password.strip():
        sets.append("password_hash=%s")
        params.append(_hash_password(new_password))

    if not sets:
        return  # Không có gì để cập nhật

    params.append(user_id)
    sql = f"UPDATE accounts SET {', '.join(sets)} WHERE id=%s"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))


def set_user_permissions(
    user_id: int,
    allowed_grades: list[str],
    daily_token_limit: int = 0,
) -> None:
    """
    Lưu phân quyền lớp học và giới hạn token hàng ngày.
    allowed_grades: ["3","4","5"] hoặc ["full"]
    daily_token_limit: 0 = không giới hạn
    """
    grades_json = _json.dumps(allowed_grades, ensure_ascii=False)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE accounts SET allowed_grades=%s, daily_token_limit=%s WHERE id=%s",
            (grades_json, max(0, daily_token_limit), user_id),
        )


def get_user_permissions(user_id: int) -> dict:
    """Lấy phân quyền của một user."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT allowed_grades, daily_token_limit FROM accounts WHERE id=%s",
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return {"allowed_grades": [], "daily_token_limit": 0}
    try:
        grades = _json.loads(row[0] or "[]")
    except Exception:
        grades = []
    return {"allowed_grades": grades, "daily_token_limit": row[1] or 0}


def check_user_grade_access(user_id: int, grade: str) -> bool:
    """Kiểm tra user có quyền truy cập lớp học không."""
    perms = get_user_permissions(user_id)
    grades = perms["allowed_grades"]
    if not grades or "full" in grades:
        return True
    return str(grade) in grades


def check_token_limit(user_id: int, tokens_to_use: int = 1) -> dict:
    """
    Kiểm tra xem user có còn quota token hôm nay không.
    Trả về: {"allowed": bool, "used_today": int, "limit": int, "remaining": int}
    """
    perms = get_user_permissions(user_id)
    limit = perms["daily_token_limit"]
    if limit <= 0:
        return {"allowed": True, "used_today": 0, "limit": 0, "remaining": -1}

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COALESCE(SUM(tokens_used), 0)
            FROM chat_logs
            WHERE user_id = %s AND created_at >= CAST({_UTC_NOW} AS DATE)
            """,
            (user_id,),
        )
        used = cur.fetchone()[0] or 0
    remaining = limit - used
    return {
        "allowed": remaining >= tokens_to_use,
        "used_today": used,
        "limit": limit,
        "remaining": max(0, remaining),
    }


# ─── Token Stats (thống kê token theo user) ───────────────────────────────────

def get_token_stats(page: int = 1, page_size: int = 20, username: str = "") -> dict:
    """Thống kê token sử dụng của từng user. Trả về: {users: [...], total: int}"""
    offset = (page - 1) * page_size

    where, params = "WHERE 1=1", []
    if username:
        where += " AND a.username LIKE %s"
        params.append(f"%{username}%")

    count_sql = f"SELECT COUNT(*) FROM accounts a {where}"
    data_sql = f"""
        SELECT a.id, a.username, a.display_name, a.role, a.status,
               a.allowed_grades, a.daily_token_limit,
               COALESCE(a.total_tokens_used, 0) AS total_tokens,
               COALESCE(td.tokens_today, 0)     AS tokens_today
        FROM accounts a
        LEFT JOIN (
            SELECT user_id, SUM(COALESCE(tokens_used, 0)) AS tokens_today
            FROM chat_logs
            WHERE created_at >= CAST({_UTC_NOW} AS DATE)
            GROUP BY user_id
        ) td ON td.user_id = a.id
        {where}
        ORDER BY COALESCE(td.tokens_today, 0) DESC, a.username
        LIMIT {page_size} OFFSET {offset}
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(count_sql, tuple(params))
        total = cur.fetchone()[0]
        cur.execute(data_sql, tuple(params))
        rows = cur.fetchall()

    users = []
    for r in rows:
        try:
            grades = _json.loads(r[5] or "[]")
        except Exception:
            grades = []
        users.append({
            "id": r[0], "username": r[1], "display_name": r[2] or "",
            "role": r[3], "status": r[4], "allowed_grades": grades,
            "daily_token_limit": r[6] or 0,
            "total_tokens": r[7] or 0, "tokens_today": r[8] or 0,
        })
    return {"users": users, "total": total}


# ─── Conversations (hội thoại theo session_id) ────────────────────────────────

def get_conversations(
    page: int = 1,
    page_size: int = 20,
    username: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    """
    Lấy danh sách phiên hội thoại nhóm theo session_id.
    Chỉ đếm và hiển thị các dòng có route thuộc CHAT_ROUTES (chat thật với Buddy).
    Các lời gọi AI nội bộ (tạo đề, kiểm tra, prompt...) bị loại khỏi đây.
    Trả về: {sessions, total}
    """
    offset = (page - 1) * page_size

    # Base clause: chỉ lấy route chat thật
    clauses = [f"c.route IN {_CHAT_ROUTES_PH}"]
    # params phải có CHAT_ROUTES ở đầu mỗi query dùng clauses
    base_params: list = list(CHAT_ROUTES)

    if username:
        clauses.append("c.username LIKE %s")
        base_params.append(f"%{username}%")
    if date_from:
        clauses.append("CAST(c.created_at AS DATE) >= %s")
        base_params.append(date_from)
    if date_to:
        clauses.append("CAST(c.created_at AS DATE) <= %s")
        base_params.append(date_to)

    where = " AND ".join(clauses)

    # COUNT cần cùng param set
    count_sql = f"SELECT COUNT(DISTINCT c.session_id) FROM chat_logs c WHERE {where}"

    # Subquery lấy first_message cũng filter theo CHAT_ROUTES
    sub_routes_ph = _CHAT_ROUTES_PH
    data_sql = f"""
        SELECT c.session_id, c.username,
               COUNT(*)                                   AS message_count,
               SUM(COALESCE(c.tokens_used, 0))            AS total_tokens,
               MIN(c.created_at)                          AS first_time,
               MAX(c.created_at)                          AS last_time,
               (SELECT LEFT(cl2.message, 120)
                FROM chat_logs cl2
                WHERE cl2.session_id = c.session_id
                  AND cl2.route IN {sub_routes_ph}
                ORDER BY cl2.created_at ASC
                LIMIT 1)                                  AS first_message
        FROM chat_logs c
        WHERE {where}
        GROUP BY c.session_id, c.username
        ORDER BY MAX(c.created_at) DESC
        LIMIT {page_size} OFFSET {offset}
    """

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(count_sql, tuple(base_params))
        total = cur.fetchone()[0]
        # data_sql có 2 chỗ dùng CHAT_ROUTES:
        #   1. subquery (cl2.route IN …) — xuất hiện trước trong chuỗi SQL
        #   2. WHERE clause (c.route IN …) — đã nằm trong base_params
        # psycopg2 bind theo thứ tự xuất hiện trong SQL string.
        data_params = list(CHAT_ROUTES) + base_params
        cur.execute(data_sql, tuple(data_params))
        rows = cur.fetchall()

    sessions = [
        {
            "session_id":    r[0],
            "username":      r[1] or "",
            "message_count": r[2] or 0,
            "total_tokens":  r[3] or 0,
            "first_time":    str(r[4]) if r[4] else "",
            "last_time":     str(r[5]) if r[5] else "",
            "first_message": r[6] or "",
        }
        for r in rows
    ]
    return {"sessions": sessions, "total": total}


# ─── Delete account ───────────────────────────────────────────────────────────

def delete_account(user_id: int) -> None:
    """
    Xóa tài khoản và toàn bộ dữ liệu liên quan:
    sessions, chat_logs, login_logs, notifications.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        # Lấy username trước khi xoá (để xoá login_logs theo username)
        cur.execute("SELECT username FROM accounts WHERE id=%s", (user_id,))
        row = cur.fetchone()
        username = row[0] if row else None

        cur.execute("DELETE FROM sessions   WHERE user_id=%s",  (user_id,))
        cur.execute("DELETE FROM chat_logs  WHERE user_id=%s",  (user_id,))
        if username:
            cur.execute("DELETE FROM login_logs WHERE username=%s", (username,))
        cur.execute("DELETE FROM notifications WHERE account_id=%s", (user_id,))
        cur.execute("DELETE FROM accounts WHERE id=%s", (user_id,))


# ─── Utility helpers ──────────────────────────────────────────────────────────

def get_user_id_by_username(username: str) -> Optional[int]:
    """Tra cứu user_id từ username. Trả về None nếu không tìm thấy."""
    if not username:
        return None
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE username=%s", (username,))
        row = cur.fetchone()
        return int(row[0]) if row else None


def get_chat_usernames() -> list[str]:
    """Danh sách username duy nhất đã từng chat (cho dropdown filter)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT username FROM chat_logs
            WHERE username IS NOT NULL
            ORDER BY username
            """
        )
        return [r[0] for r in cur.fetchall()]
