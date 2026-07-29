"""
config.py – Cấu hình tập trung cho BuddyMath backend.

Mọi secret/đường dẫn đọc từ biến môi trường (file .env). KHÔNG hardcode
key trong code. Sao chép .env.example → .env và điền giá trị thực.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Ưu tiên .env nằm trong thư mục BE/ (parent của app/)
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)
    load_dotenv(override=False)  # fallback: .env ở cwd
except ImportError:
    pass


# ─── Đường dẫn ────────────────────────────────────────────────────────────────
BE_DIR        = Path(__file__).resolve().parent.parent           # .../BE
REPO_DIR      = BE_DIR.parent                                    # .../buddymath
FRONTEND_DIR  = Path(os.environ.get("FRONTEND_DIR", REPO_DIR / "FE")).resolve()
DATA_ROOT     = Path(os.environ.get("DATA_ROOT", BE_DIR / "data")).resolve()
IMAGES_DIR    = Path(os.environ.get("IMAGES_DIR", FRONTEND_DIR / "images")).resolve()

INDEX_PATH    = DATA_ROOT / "faiss.index"
META_PATH     = DATA_ROOT / "metadata.pkl"
MANIFEST_PATH = DATA_ROOT / ".ingested_manifest.json"


# ─── Auth / JWT ───────────────────────────────────────────────────────────────
_DEFAULT_SECRET_KEY       = "smartbuddy-default-secret-key-change-in-production"
SECRET_KEY                = os.environ.get("SECRET_KEY") or _DEFAULT_SECRET_KEY
if SECRET_KEY == _DEFAULT_SECRET_KEY:
    logging.getLogger(__name__).warning(
        "⚠️ SECRET_KEY đang dùng giá trị MẶC ĐỊNH — chỉ an toàn ở local. "
        "Đặt SECRET_KEY trong môi trường production, nếu không JWT có thể bị giả mạo!"
    )
JWT_ALGORITHM             = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.environ.get("ACCESS_TOKEN_EXPIRE_HOURS", str(24 * 7)))  # 7 ngày

# ─── Seed tài khoản bootstrap (bảo mật) ───────────────────────────────────────
# Mật khẩu admin LẤY TỪ ENV (không hardcode). Tài khoản demo student/parent chỉ bật ở dev
# (ENABLE_DEMO_ACCOUNTS=1). Production để trống → KHÔNG seed tài khoản mật khẩu mặc định.
ADMIN_EMAIL          = os.environ.get("ADMIN_EMAIL", "admin@smartbuddy.vn")
ADMIN_PASSWORD       = os.environ.get("ADMIN_PASSWORD", "")
ENABLE_DEMO_ACCOUNTS = os.environ.get("ENABLE_DEMO_ACCOUNTS", "").lower() in ("1", "true", "yes")

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(BE_DIR / 'smartbuddy.db').as_posix()}")
# Render/Heroku cấp Postgres dưới scheme cũ "postgres://" — SQLAlchemy cần "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# ─── LLM: Groq (chat / synthesis / classroom) ────────────────────────────────
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL    = os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# ── Tách model theo modality (độ chính xác + vision) ──
# TEXT: model mạnh cho toán/lập luận (không cần vision). Mặc định 70B của Groq.
# VISION: model đọc được ảnh/OCR. Mặc định = GROQ_MODEL (scout — có vision).
# Đổi qua env GROQ_TEXT_MODEL / GROQ_VISION_MODEL nếu muốn.
GROQ_TEXT_MODEL   = os.environ.get("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", GROQ_MODEL)

LLM_TIMEOUT    = float(os.environ.get("LLM_TIMEOUT", "60"))
RAG_TOP_K      = int(os.environ.get("RAG_TOP_K", "5"))
HISTORY_WINDOW = int(os.environ.get("HISTORY_WINDOW", "10"))

# Danh sách model hỗ trợ vision (bổ sung qua env GROQ_VISION_MODELS="a,b")
_BUILTIN_VISION_MODELS: set[str] = {
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llava-v1.5-7b-4096-preview",
    "llava-v1.6-34b",
}


# ─── LLM ĐANG DÙNG (ACTIVE): Groq (mặc định, miễn phí) hoặc Gemini (Google) ────
# GIỮ NGUYÊN cấu hình Groq ở trên làm DỰ PHÒNG. Chọn "bộ não" qua LLM_PROVIDER:
#   • groq   → Groq/Llama (mặc định, miễn phí)
#   • gemini → Google Gemini (thông minh hơn, tiếng Việt tốt) — cần GEMINI_API_KEY
# Provider lỗi/hết quota? Đổi LLM_PROVIDER=groq là chạy lại Groq y như cũ.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").strip().lower()

# Gemini dùng endpoint OpenAI-compatible → client hiện tại gọi được luôn (không cần code riêng).
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "")
GEMINI_BASE_URL     = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
GEMINI_MODEL        = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_VISION_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-flash-latest")  # Gemini flash đa phương thức (đọc ảnh)

if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
    ACTIVE_API_KEY      = GEMINI_API_KEY
    ACTIVE_BASE_URL     = GEMINI_BASE_URL
    ACTIVE_TEXT_MODEL   = GEMINI_MODEL
    ACTIVE_VISION_MODEL = GEMINI_VISION_MODEL
    logging.getLogger(__name__).warning(
        "🤖 LLM_PROVIDER=gemini → dùng Google Gemini (%s). Groq vẫn còn để dự phòng.", GEMINI_MODEL
    )
else:
    ACTIVE_API_KEY      = GROQ_API_KEY
    ACTIVE_BASE_URL     = GROQ_BASE_URL
    ACTIVE_TEXT_MODEL   = GROQ_TEXT_MODEL
    ACTIVE_VISION_MODEL = GROQ_VISION_MODEL
    if LLM_PROVIDER == "gemini":
        logging.getLogger(__name__).warning(
            "⚠️ LLM_PROVIDER=gemini nhưng CHƯA đặt GEMINI_API_KEY → app vẫn dùng Groq."
        )

# Model vision đang dùng phải được nhận diện là 'vision' (cho cả Gemini).
_BUILTIN_VISION_MODELS.add(ACTIVE_VISION_MODEL)


def vision_models() -> set[str]:
    extra = os.environ.get("GROQ_VISION_MODELS", "")
    return _BUILTIN_VISION_MODELS | {m.strip() for m in extra.split(",") if m.strip()}


# Model được phép override qua field `model` của /v1/messages (để so sánh model bằng eval).
# Ứng viên phổ biến trên Groq — client CHỈ chọn được trong danh sách này (chặn lạm dụng model đắt).
# Thêm model khác qua env GROQ_ALLOWED_MODELS="a,b". Model phải có trong gói Groq của bạn.
_BUILTIN_ALLOWED_MODELS: set[str] = {
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
}


def allowed_models() -> set[str]:
    extra = os.environ.get("GROQ_ALLOWED_MODELS", "")
    return (
        {GROQ_MODEL, GROQ_TEXT_MODEL, GROQ_VISION_MODEL, ACTIVE_TEXT_MODEL, ACTIVE_VISION_MODEL}
        | vision_models()
        | _BUILTIN_ALLOWED_MODELS
        | {m.strip() for m in extra.split(",") if m.strip()}
    )


# ─── LLM: Claude (proxy tuỳ chọn) ─────────────────────────────────────────────
CLAUDE_API_KEY  = os.environ.get("CLAUDE_API_KEY", "")
CLAUDE_BASE_URL = os.environ.get("CLAUDE_BASE_URL", "https://api.anthropic.com/v1")
CLAUDE_MODEL    = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


# ─── Embedding: Jina AI ───────────────────────────────────────────────────────
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_MODEL   = os.environ.get("JINA_MODEL", "jina-embeddings-v3")
JINA_URL     = os.environ.get("JINA_URL", "https://api.jina.ai/v1/embeddings")


# ─── Email ────────────────────────────────────────────────────────────────────
# Ưu tiên gửi qua HTTP API (BREVO_API_KEY) vì cloud thường CHẶN cổng SMTP ra ngoài
# (Render chặn 25/465/587 → gửi SMTP bị treo). Brevo/Sendinblue: https://app.brevo.com
# → SMTP & API → tạo API key; xác minh "Senders" = FROM_EMAIL. Free 300 email/ngày.
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")

# SMTP (chỉ dùng khi KHÔNG có BREVO_API_KEY — vd chạy local).
SMTP_HOST  = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER  = os.environ.get("SMTP_USER", "")
SMTP_PASS  = os.environ.get("SMTP_PASS", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL") or SMTP_USER or "SmartBuddy <no-reply@smartbuddy.vn>"

# URL gốc dùng trong nội dung email
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")

# Token bảo vệ endpoint tác vụ nền (gửi báo cáo theo lịch). Cron gửi header X-Task-Token.
# Bỏ trống ở local (endpoint mở); production NÊN đặt để tránh người ngoài gọi.
SCHEDULER_TOKEN = os.environ.get("SCHEDULER_TOKEN", "")


# ─── Thanh toán: VietQR + SePay (đối soát chuyển khoản tự động) ────────────────
# BANK_CODE: mã ngân hàng theo VietQR/SePay (vd: MB, VCB, TPB, ACB, VPB, TCB, BIDV…).
# BANK_ACCOUNT_NUMBER: số tài khoản nhận tiền. BANK_ACCOUNT_NAME: tên chủ TK (để hiển thị).
# SEPAY_API_KEY: khóa để XÁC THỰC webhook SePay gọi về (đặt trùng với cấu hình trên SePay).
BANK_ACCOUNT_NUMBER = os.environ.get("BANK_ACCOUNT_NUMBER", "")
BANK_CODE           = os.environ.get("BANK_CODE", "")
BANK_ACCOUNT_NAME   = os.environ.get("BANK_ACCOUNT_NAME", "")
SEPAY_API_KEY       = os.environ.get("SEPAY_API_KEY", "")
ORDER_TTL_MIN       = int(os.environ.get("ORDER_TTL_MIN", "30"))   # đơn hết hạn sau N phút
# Bật endpoint nâng gói GIẢ (không thanh toán) — CHỈ để dev/thử. Mặc định TẮT ở production.
ENABLE_MOCK_BILLING = os.environ.get("ENABLE_MOCK_BILLING", "").lower() in ("1", "true", "yes")
