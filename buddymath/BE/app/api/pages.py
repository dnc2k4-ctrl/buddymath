"""
pages.py – Phục vụ các trang HTML (login, app, parent) và health check.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from app.config import FRONTEND_DIR
from app.services import runtime

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


@router.get("/health")
async def health():
    docs = len(runtime.rag_engine._documents) if runtime.rag_engine else 0
    return {
        "status":       "ok",
        "service":      "BuddyMath API",
        "version":      "3.0.0",
        "llm":          "Groq",
        "embedder":     "Jina AI",
        "indexed_docs": docs,
        "time":         datetime.utcnow().isoformat(),
    }
