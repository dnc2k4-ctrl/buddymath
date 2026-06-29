"""
main.py – BuddyMath API (gộp SmartBuddy + MathBuddy).

Một FastAPI app duy nhất, phân lớp:
  api/        – routers (presentation)
  services/   – nghiệp vụ + runtime singletons
  models/     – ORM
  schemas/    – Pydantic DTO
  rag/        – RAG engine, chunking, embedder, router
  llm/        – Groq client + pipeline
  core/       – database, security
  config.py   – cấu hình từ .env

Chạy:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import auth, catalog, chat, classroom, pages, parent, scores
from app.config import IMAGES_DIR
from app.core.database import init_db
from app.services import runtime
from app.services.auth_service import seed_demo_accounts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Khởi động BuddyMath backend…")
    init_db()
    seed_demo_accounts()

    logger.info("📂 Scan và ingest thư mục data/…")
    summary = runtime.init_runtime()
    logger.info(
        f"✅ Ingest hoàn tất: {summary['new_files_ingested']} file mới, "
        f"{summary['skipped_files']} bỏ qua, {summary['total_chunks']} chunks."
    )
    if summary["errors"]:
        logger.warning(f"⚠ Lỗi ingest: {summary['errors']}")

    logger.info("✅ BuddyMath sẵn sàng.")
    yield
    logger.info("🛑 Đang tắt BuddyMath backend.")


def create_app() -> FastAPI:
    app = FastAPI(title="BuddyMath API", version="3.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── HTTP security headers (áp cho mọi response) ──────────────────────────
    _CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; base-uri 'self'; object-src 'none'"
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(self)"
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP chỉ áp cho trang HTML (tránh ảnh hưởng tài liệu/ảnh tĩnh)
        ctype = resp.headers.get("content-type", "")
        if ctype.startswith("text/html"):
            resp.headers["Content-Security-Policy"] = _CSP
        return resp

    # Static images (mascot sprites, logo…)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

    # Routers
    for module in (pages, auth, scores, parent, chat, catalog, classroom):
        app.include_router(module.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    print("\n🤖 BuddyMath API đang khởi động…")
    print("   → Login:  http://localhost:8000/")
    print("   → App:    http://localhost:8000/app")
    print("   → Parent: http://localhost:8000/parent-portal")
    print("   → Docs:   http://localhost:8000/docs\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
