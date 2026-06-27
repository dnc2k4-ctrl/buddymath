"""
config.py – Cấu hình tập trung cho BuddyMath backend.

Mọi secret/đường dẫn đọc từ biến môi trường (file .env). KHÔNG hardcode
key trong code. Sao chép .env.example → .env và điền giá trị thực.
"""
from __future__ import annotations

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
SECRET_KEY                = os.environ.get("SECRET_KEY") or "smartbuddy-default-secret-key-change-in-production"
JWT_ALGORITHM             = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.environ.get("ACCESS_TOKEN_EXPIRE_HOURS", str(24 * 7)))  # 7 ngày

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(BE_DIR / 'smartbuddy.db').as_posix()}")
# Render/Heroku cấp Postgres dưới scheme cũ "postgres://" — SQLAlchemy cần "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# ─── LLM: Groq (chat / synthesis / classroom) ────────────────────────────────
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL    = os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

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


def vision_models() -> set[str]:
    extra = os.environ.get("GROQ_VISION_MODELS", "")
    return _BUILTIN_VISION_MODELS | {m.strip() for m in extra.split(",") if m.strip()}


# ─── LLM: Claude (proxy tuỳ chọn) ─────────────────────────────────────────────
CLAUDE_API_KEY  = os.environ.get("CLAUDE_API_KEY", "")
CLAUDE_BASE_URL = os.environ.get("CLAUDE_BASE_URL", "https://api.anthropic.com/v1")
CLAUDE_MODEL    = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


# ─── Embedding: Jina AI ───────────────────────────────────────────────────────
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_MODEL   = os.environ.get("JINA_MODEL", "jina-embeddings-v3")
JINA_URL     = os.environ.get("JINA_URL", "https://api.jina.ai/v1/embeddings")


# ─── Email / SMTP (báo cáo phụ huynh) ─────────────────────────────────────────
SMTP_HOST  = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER  = os.environ.get("SMTP_USER", "")
SMTP_PASS  = os.environ.get("SMTP_PASS", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL") or SMTP_USER

# URL gốc dùng trong nội dung email
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
