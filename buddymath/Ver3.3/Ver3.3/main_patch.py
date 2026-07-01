"""
main_patch.py – Đoạn code CẦN THÊM vào main.py hiện có
═══════════════════════════════════════════════════════════
Hướng dẫn:

1. Thêm vào phần import đầu main.py:
   ─────────────────────────────────
   from auth_routes import router as auth_router
   import db

2. Thêm sau dòng `app = FastAPI(...)`:
   ────────────────────────────────────
   app.include_router(auth_router)

3. Thêm vào hàm lifespan (sau `rag_engine = RAGEngine()`):
   ─────────────────────────────────────────────────────────
   try:
       db.init_db()
       logger.info("✅ Database PostgreSQL sẵn sàng.")
   except Exception as exc:
       logger.warning(f"⚠ DB init failed (sẽ chạy không có DB): {exc}")

4. Thêm vào /chat endpoint (sau khi có `result`):
   ──────────────────────────────────────────────
   # Log vào DB
   try:
       username = req.session_id.split('_')[0] if '_' in req.session_id else ""
       db.log_chat(
           session_id=req.session_id,
           message=req.message,
           answer=result.get("answer",""),
           route=result.get("route",""),
           subject=req.subject or "",
           topic=req.topic or "",
           model=pipeline.llm.model,
           username=username,
       )
   except Exception as db_exc:
       logger.warning(f"DB log error: {db_exc}")

5. Thêm static mount cho monitor.html:
   ─────────────────────────────────────
   from fastapi.staticfiles import StaticFiles
   # sau app.include_router(auth_router):
   # MONITOR_HTML đã được serve tại GET /monitor qua auth_routes.py

6. Thêm vào file .env:
   ─────────────────────
   DB_HOST=localhost
   DB_PORT=5432
   DB_USER=postgres
   DB_PASSWORD=postgres
   DB_NAME=mathbuddy
   # hoặc dùng chuỗi kết nối đầy đủ (ưu tiên nếu có):
   # DATABASE_URL=postgresql://user:password@host:5432/mathbuddy

7. Thêm vào requirements.txt:
   ────────────────────────────
   psycopg2-binary>=2.9.0
   bcrypt>=4.0.0

═══════════════════════════════════════════════════════════
SAU KHI THÊM, main.py sẽ có dạng (phần liên quan):
═══════════════════════════════════════════════════════════
"""

# ══ PHẦN IMPORT CẦN THÊM ══════════════════════════════════════════════════════
from auth_routes import router as auth_router
import db

# ══ PHẦN LIFESPAN CẦN THÊM (vào trong @asynccontextmanager lifespan) ══════════
async def _lifespan_db_init():
    try:
        db.init_db()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"DB init failed: {exc}")

# ══ PHẦN REGISTER ROUTER (sau app = FastAPI(...)) ═══════════════════════════════
# app.include_router(auth_router)

# ══ PATCH CHAT LOG (thêm vào endpoint /chat sau khi có result) ════════════════
def _log_chat_safe(req, result, pipeline):
    import logging
    try:
        username = req.session_id.split('_')[0] if '_' in req.session_id else ""
        db.log_chat(
            session_id=req.session_id,
            message=req.message,
            answer=result.get("answer", ""),
            route=result.get("route", ""),
            subject=req.subject or "",
            topic=req.topic or "",
            model=pipeline.llm.model,
            username=username,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(f"DB log error: {exc}")
