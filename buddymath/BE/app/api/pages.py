"""
pages.py – Phục vụ các trang HTML (login, app, parent) và health check.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session

from app import plans
from app.config import ACTIVE_TEXT_MODEL, ACTIVE_VISION_MODEL, FRONTEND_DIR, LLM_PROVIDER, SCHEDULER_TOKEN
from app.core.database import get_db
from app.services import report_scheduler, runtime

router = APIRouter(tags=["pages"])


def _serve(filename: str):
    p = FRONTEND_DIR / filename
    if p.exists():
        return FileResponse(p)
    return JSONResponse({"error": f"Không tìm thấy {filename}"}, status_code=404)


@router.get("/")
async def root():
    return _serve("login.html")


@router.get("/app")
async def serve_app():
    return _serve("mathbuddy-kids.html")


@router.get("/parent-portal")
async def serve_parent():
    return _serve("parent.html")


@router.get("/admin")
async def serve_admin():
    """Trang quản trị riêng — có form đăng nhập, chỉ admin dùng được."""
    return _serve("admin.html")


@router.get("/terms")
async def serve_terms():
    """Điều khoản sử dụng (bắt buộc cho sản phẩm công khai)."""
    return _serve("terms.html")


@router.get("/privacy")
async def serve_privacy():
    """Chính sách bảo mật (bắt buộc cho sản phẩm công khai)."""
    return _serve("privacy.html")


# ─── Gói đăng ký: 1 nguồn duy nhất (app/plans.py) phơi ra cho FE ──────────────
@router.get("/config/plans.js", include_in_schema=False)
async def plans_js():
    """FE nạp bằng <script src> → gán window.SB_PLANS. Cùng dữ liệu với /api/plans."""
    return Response(
        content=plans.plans_as_js(),
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/api/plans")
async def api_plans():
    """JSON gói đăng ký (unlimited numeric → null). Cho công cụ/API khác."""
    return plans.plans_as_json()


@router.get("/robots.txt", include_in_schema=False)
async def robots(request: Request):
    base = str(request.base_url).rstrip("/")
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /app\n"
        "Allow: /parent-portal\n"
        "Disallow: /admin\n"
        "Disallow: /docs\n"
        "Disallow: /redoc\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return PlainTextResponse(body)


# Các trang công khai đưa vào sitemap (không gồm /admin vì noindex).
# priority/changefreq tuỳ mức quan trọng cho SEO.
_SITEMAP_PAGES = [
    ("/",             "weekly",  "1.0"),
    ("/app",          "weekly",  "0.8"),
    ("/parent-portal", "monthly", "0.5"),
    ("/terms",        "yearly",  "0.3"),
    ("/privacy",      "yearly",  "0.3"),
]


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap(request: Request):
    """Sinh sitemap.xml động theo domain đang chạy (localhost, *.onrender.com, domain riêng)."""
    base = str(request.base_url).rstrip("/")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    urls = "".join(
        f"  <url><loc>{base}{path}</loc>"
        f"<lastmod>{today}</lastmod>"
        f"<changefreq>{freq}</changefreq>"
        f"<priority>{prio}</priority></url>\n"
        for path, freq, prio in _SITEMAP_PAGES
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/health")
async def health():
    docs = len(runtime.rag_engine._documents) if runtime.rag_engine else 0
    return {
        "status":       "ok",
        "service":      "BuddyMath API",
        "version":      "3.0.0",
        "llm":          LLM_PROVIDER,
        "model":        ACTIVE_TEXT_MODEL,
        "model_text":   ACTIVE_TEXT_MODEL,
        "model_vision": ACTIVE_VISION_MODEL,
        "embedder":     "Jina AI",
        "indexed_docs": docs,
        "time":         datetime.utcnow().isoformat(),
    }


@router.post("/tasks/run-scheduled-reports")
async def run_scheduled_reports(request: Request, db: Session = Depends(get_db)):
    """
    Gửi email báo cáo THEO LỊCH của gói (Standard = hàng tuần). Idempotent nhờ last_report_at
    → gọi nhiều lần trong kỳ cũng không gửi trùng. Dành cho cron/hosting gọi mỗi ngày.
    Bảo vệ bằng SCHEDULER_TOKEN (gửi header 'X-Task-Token' hoặc query '?token=').
    """
    if SCHEDULER_TOKEN:
        tok = request.headers.get("x-task-token") or request.query_params.get("token")
        if tok != SCHEDULER_TOKEN:
            raise HTTPException(401, "Unauthorized")
    return report_scheduler.send_due_reports(db)
