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

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from app.api import auth, billing, catalog, chat, classroom, pages, parent, scores
from app.config import FRONTEND_DIR, IMAGES_DIR
from app.core.database import init_db
from app.services import runtime
from app.services.auth_service import seed_demo_accounts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _background_ingest():
    """Nạp RAG/pipeline + ingest data/ ở NỀN (gọi Jina — chậm).

    Chạy trong thread riêng để KHÔNG chặn khởi động: app phản hồi /health ngay,
    tránh Render free health-check (timeout 5s) bị trượt → vòng lặp restart/502.
    Trong lúc nạp, các endpoint cần RAG trả 503 tạm thời (auth/điểm/thanh toán vẫn chạy).
    """
    try:
        logger.info("📂 (nền) Scan và ingest thư mục data/…")
        summary = await asyncio.to_thread(runtime.init_runtime)
        logger.info(
            f"✅ (nền) Ingest hoàn tất: {summary['new_files_ingested']} file mới, "
            f"{summary['skipped_files']} bỏ qua, {summary['total_chunks']} chunks."
        )
        if summary["errors"]:
            logger.warning(f"⚠ (nền) Lỗi ingest: {summary['errors']}")
    except Exception as e:
        logger.warning(f"⚠ (nền) Nạp RAG lỗi: {e}")


async def _report_scheduler_loop():
    """Định kỳ gửi báo cáo email theo LỊCH của gói (Standard = hàng tuần).

    Chạy trong tiến trình → hợp hosting always-on. Hosting hay 'ngủ' thì nên đặt thêm
    một cron ngoài gọi POST /tasks/run-scheduled-reports mỗi ngày (idempotent, không gửi trùng).
    """
    from app.core.database import SessionLocal
    from app.services import report_scheduler
    while True:
        try:
            await asyncio.sleep(6 * 3600)   # kiểm tra mỗi 6 tiếng
            db = SessionLocal()
            try:
                res = await asyncio.to_thread(report_scheduler.send_due_reports, db)
                if res.get("sent"):
                    logger.info(f"[SCHEDULE] Đã gửi {res['sent']} báo cáo theo lịch.")
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[SCHEDULE] Vòng lặp lỗi: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Khởi động BuddyMath backend…")
    init_db()
    seed_demo_accounts()

    # Nạp RAG ở nền → khởi động xong tức thì, health check không còn timeout.
    ingest_task = asyncio.create_task(_background_ingest())
    scheduler_task = asyncio.create_task(_report_scheduler_loop())   # gửi báo cáo theo lịch của gói

    logger.info("✅ BuddyMath sẵn sàng (RAG đang nạp ở nền).")
    yield
    ingest_task.cancel()
    scheduler_task.cancel()
    logger.info("🛑 Đang tắt BuddyMath backend.")


def create_app() -> FastAPI:
    app = FastAPI(title="BuddyMath API", version="3.0.0", lifespan=lifespan)

    # Nén gzip cho HTML/JS/CSS/JSON (trang app ~600KB → giảm mạnh dung lượng tải).
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # CORS: xác thực dùng Bearer token (localStorage), KHÔNG dùng cookie → allow_credentials=False.
    # Mặc định "*" (an toàn khi không có credentials). Khi lên domain riêng, đặt env
    # ALLOWED_ORIGINS="https://tenmien.com" để siết chỉ cho domain của bạn.
    _origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── HTTP security headers (áp cho mọi response) ──────────────────────────
    _CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data: blob: https://qr.sepay.vn https://img.vietqr.io; "
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
    for module in (pages, auth, billing, scores, parent, chat, catalog, classroom):
        app.include_router(module.router)

    # 404 thân thiện: trả trang HTML cho trình duyệt, JSON cho lời gọi API.
    @app.exception_handler(404)
    async def _not_found(request: Request, exc):
        if "text/html" in request.headers.get("accept", ""):
            page = FRONTEND_DIR / "404.html"
            if page.exists():
                return FileResponse(page, status_code=404)
        return JSONResponse({"detail": getattr(exc, "detail", "Not Found")}, status_code=404)

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
