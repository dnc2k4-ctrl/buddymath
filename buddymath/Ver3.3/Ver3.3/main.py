"""
MathBuddy Backend – Main Entry Point  (Gemini Embedding Edition)
Mở trình duyệt tại http://localhost:8000 → load giao diện MathBuddy.

Tính năng mới so với bản cũ:
  • Khi khởi động: tự động scan và ingest toàn bộ data/
  • GET  /subjects              → dynamic từ thư mục data/ (không hardcode)
  • GET  /subjects/{s}/topics  → dynamic từ thư mục data/
  • POST /topics/synthesis      → LLM tổng hợp nội dung theo chủ đề
  • GET  /topics/{s}/{t}/synthesis → GET alias cho endpoint trên
  • POST /ingest/reload         → force re-ingest (dùng khi thêm file mới)

Environment variables:
  GROQ_API_KEY   – Groq API key
  GROQ_MODEL     – model id  (default: llama-3.1-8b-instant)
  GROQ_BASE_URL  – (default: https://api.groq.com/openai/v1)
"""

from __future__ import annotations

import base64
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

from chunking import DocumentChunker
from data_loader import DataDirectoryLoader
from pipeline import MathBuddyPipeline, LLMClient, is_vision_model
from rag import RAGEngine

from auth_routes import router as auth_router
import db

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Globals ─────────────────────────────────────────────────────────────────
rag_engine:  Optional[RAGEngine]         = None
pipeline:    Optional[MathBuddyPipeline] = None
data_loader: Optional[DataDirectoryLoader] = None

# Cache cho synthesis (key: "subject/topic")
_synthesis_cache: dict[str, dict] = {}

BASE_DIR  = Path(__file__).parent
HTML_FILE = BASE_DIR / "mathbuddy-kids.html"


# ─── Synthesis Helper ─────────────────────────────────────────────────────────
async def _synthesize_topic(
    subject: str,
    topic: str,
    llm: LLMClient,
    rag: RAGEngine,
    force: bool = False,
) -> dict:
    """
    Tổng hợp toàn bộ tài liệu của một topic thành nội dung có cấu trúc.
    Kết quả được cache trong bộ nhớ (mất khi restart).
    """
    cache_key = f"{subject}/{topic}"
    if not force and cache_key in _synthesis_cache:
        logger.info(f"Synthesis cache hit: {cache_key}")
        return _synthesis_cache[cache_key]

    # Lấy tất cả chunks của topic
    all_chunks = rag.get_all_chunks(subject=subject, topic=topic)
    if not all_chunks:
        return {
            "subject": subject,
            "topic":   topic,
            "status":  "empty",
            "message": f"Chưa có tài liệu nào cho chủ đề '{topic}' trong '{subject}'.",
        }

    # Gom nội dung, ưu tiên lý thuyết trước
    theory_chunks   = [c for c in all_chunks if c.doc_type == "theory"]
    exercise_chunks = [c for c in all_chunks if c.doc_type == "exercise"]
    solution_chunks = [c for c in all_chunks if c.doc_type == "solution"]

    def _join(chunks, max_chars=6000) -> str:
        joined = "\n\n---\n\n".join(c.content for c in chunks)
        return joined[:max_chars] if len(joined) > max_chars else joined

    context_parts = []
    if theory_chunks:
        context_parts.append("=== LÝ THUYẾT ===\n" + _join(theory_chunks, 4000))
    if exercise_chunks:
        context_parts.append("=== BÀI TẬP ===\n"  + _join(exercise_chunks, 2000))
    if solution_chunks:
        context_parts.append("=== LỜI GIẢI ===\n" + _join(solution_chunks, 1500))

    full_context = "\n\n".join(context_parts)

    # Prompt yêu cầu output JSON có cấu trúc
    system_prompt = (
        "Bạn là trợ lý giáo dục. Nhiệm vụ của bạn là tổng hợp các tài liệu học tập "
        "thành một bản tóm tắt chủ đề có cấu trúc rõ ràng.\n"
        "Hãy trả về DUY NHẤT một JSON object (không có markdown, không có ```), "
        "với cấu trúc sau:\n"
        "{\n"
        '  "title": "Tên chủ đề ngắn gọn",\n'
        '  "overview": "Mô tả tổng quan 2-3 câu về chủ đề",\n'
        '  "key_concepts": ["Khái niệm 1", "Khái niệm 2", ...],\n'
        '  "important_formulas": [\n'
        '    {"name": "Tên công thức", "formula": "LaTeX hoặc text", "note": "Ghi chú ngắn"}\n'
        '  ],\n'
        '  "learning_steps": ["Bước 1: ...", "Bước 2: ...", ...],\n'
        '  "common_mistakes": ["Lỗi thường gặp 1", ...],\n'
        '  "example_summary": "Tóm tắt ví dụ điển hình từ tài liệu (nếu có)"\n'
        "}\n"
        "Giữ ngắn gọn, súc tích, phù hợp với học sinh. "
        "Dùng ngôn ngữ của tài liệu (tiếng Việt hoặc tiếng Anh)."
    )

    user_message = (
        f"Chủ đề: {topic} (môn: {subject})\n\n"
        f"Tài liệu:\n{full_context}"
    )

    try:
        raw_reply = await llm.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.2,
            max_tokens=1500,
        )

        # Parse JSON từ reply
        raw_reply = raw_reply.strip()
        if raw_reply.startswith("```"):
            raw_reply = raw_reply.split("```")[1]
            if raw_reply.startswith("json"):
                raw_reply = raw_reply[4:]
        synthesis = json.loads(raw_reply)

    except json.JSONDecodeError as exc:
        logger.warning(f"LLM không trả về JSON hợp lệ: {exc}. Dùng plain text.")
        synthesis = {
            "title":           topic,
            "overview":        raw_reply[:500] if "raw_reply" in dir() else "Không thể tổng hợp.",
            "key_concepts":    [],
            "important_formulas": [],
            "learning_steps":  [],
            "common_mistakes": [],
            "example_summary": "",
        }
    except Exception as exc:
        logger.error(f"Synthesis LLM error: {exc}", exc_info=True)
        raise

    result = {
        "subject":      subject,
        "topic":        topic,
        "status":       "ok",
        "chunk_count":  len(all_chunks),
        "source_files": sorted({c.source_file.split("/")[-1] for c in all_chunks}),
        "synthesis":    synthesis,
    }
    _synthesis_cache[cache_key] = result
    return result


# ─── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_engine, pipeline, data_loader
    logger.info("🚀 Khởi động MathBuddy backend (Gemini Embedding)…")

    # Khởi tạo / đồng bộ schema PostgreSQL (tạo bảng còn thiếu, migrate cột mới...)
    try:
        db.init_db()
        logger.info("✅ Database PostgreSQL đã sẵn sàng.")
    except Exception as exc:
        logger.warning(f"⚠ DB init thất bại (tiếp tục không có DB): {exc}")

    # Khởi tạo các thành phần core
    rag_engine  = RAGEngine()
    pipeline    = MathBuddyPipeline(rag_engine=rag_engine)
    data_loader = DataDirectoryLoader()

    # Tự động ingest tài liệu từ data/
    logger.info("📂 Bắt đầu scan và ingest thư mục data/…")
    summary = data_loader.ingest_all(rag_engine)
    logger.info(
        f"✅ Ingest hoàn tất: "
        f"{summary['new_files_ingested']} file mới, "
        f"{summary['skipped_files']} bỏ qua, "
        f"{summary['total_chunks']} chunks."
    )
    if summary["errors"]:
        logger.warning(f"⚠ Lỗi ingest: {summary['errors']}")

    logger.info("✅ MathBuddy sẵn sàng.")
    yield
    logger.info("🛑 Đang tắt MathBuddy backend.")


# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MathBuddy API",
    version="3.0.0",
    lifespan=lifespan,
)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response Models ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:    str
    session_id: str           = "default"
    topic:      Optional[str] = None
    subject:    Optional[str] = None
    stream:     bool          = False

class ChatResponse(BaseModel):
    answer:     str
    sources:    list[dict] = []
    route:      str        = "general"
    session_id: str
    model:      str        = ""

class IngestRequest(BaseModel):
    file_path: str
    subject:   str
    topic:     str
    metadata:  dict = {}

class IngestResponse(BaseModel):
    status:         str
    chunks_created: int
    message:        str

class SynthesisRequest(BaseModel):
    subject: str
    topic:   str
    force:   bool = False   # True → bỏ cache, tổng hợp lại

class GroqDirectRequest(BaseModel):
    messages:         list[dict]
    system:           Optional[str] = None
    model:            Optional[str] = None
    max_tokens:       int           = 1000
    temperature:      float         = 0.5
    image_base64:     Optional[str] = None        # chuỗi base64 của ảnh (nếu có)
    image_media_type: str           = "image/jpeg" # MIME type tương ứng
    session_id:       Optional[str] = None        # để gom log chat theo phiên
    username:         Optional[str] = None        # tên user hiện tại (nếu đã đăng nhập)
    route_tag:        Optional[str] = None        # nhãn tính năng gọi (chat, classroom, synthesis...)


# ─── Frontend ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if not HTML_FILE.exists():
        return HTMLResponse(
            content="<h2>⚠️ Không tìm thấy mathbuddy-kids.html</h2>",
            status_code=404,
        )
    return HTMLResponse(content=HTML_FILE.read_text(encoding="utf-8"))


# ─── Health ──────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    docs = len(rag_engine._documents) if rag_engine else 0
    return {
        "status":       "ok",
        "service":      "MathBuddy API",
        "version":      "3.0.0",
        "llm":          "Groq",
        "embedder":     "Gemini text-embedding-004",
        "indexed_docs": docs,
    }


# ─── Groq proxy ──────────────────────────────────────────────────────────────
@app.post("/v1/messages")
async def groq_proxy(req: GroqDirectRequest):
    client = LLMClient()
    msgs: list[dict] = []
    if req.system:
        msgs.append({"role": "system", "content": req.system})
    msgs.extend(req.messages)

    # Chuẩn hoá content cho Groq API theo khả năng của model:
    #
    #  • Model vision  → giữ nguyên list [image_url, text], chỉ lọc type không hợp lệ
    #  • Model text    → flatten list về string, bỏ image block
    #  • String thuần  → giữ nguyên
    #
    # Thêm model mới vào _BUILTIN_VISION_MODELS (pipeline.py)
    # hoặc env var GROQ_VISION_MODELS="model-a,model-b"
    model_supports_vision = is_vision_model(client.model)

    def _normalize_content(content):
        if isinstance(content, str):
            return content

        if not isinstance(content, list):
            return str(content)

        if model_supports_vision:
            # Giữ image_url + text, chuyển document → text, bỏ type lạ
            blocks = []
            for b in content:
                if not isinstance(b, dict):
                    continue
                t = b.get("type")
                if t in ("image_url", "text"):
                    blocks.append(b)
                elif t == "document":
                    data = b.get("source", {}).get("data", "")
                    if data:
                        blocks.append({"type": "text", "text": data})
            return blocks or ""
        else:
            # Text-only: flatten, bỏ ảnh hoàn toàn
            parts = []
            for b in content:
                if not isinstance(b, dict):
                    parts.append(str(b))
                    continue
                t = b.get("type")
                if t == "text":
                    parts.append(b.get("text", ""))
                elif t == "image_url":
                    parts.append("[Ảnh đính kèm – model hiện tại không hỗ trợ vision]")
                elif t == "document":
                    parts.append(b.get("source", {}).get("data", ""))
            return "\n".join(filter(None, parts))

    normalized_msgs = [
        {**msg, "content": _normalize_content(msg.get("content", ""))}
        for msg in msgs
    ]

    # ── Inject ảnh vào user message cuối cùng (nếu frontend gửi kèm ảnh) ────
    # Frontend gửi image_base64 + image_media_type trong body thay vì tự
    # build multipart content, nên ta inject tại đây trước khi gọi LLM.
    if req.image_base64:
        # Validate base64 decode được
        try:
            base64.b64decode(req.image_base64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="image_base64 không hợp lệ.")

        if model_supports_vision:
            # Tìm user message cuối để gắn ảnh vào
            last_user_idx = next(
                (i for i in range(len(normalized_msgs) - 1, -1, -1)
                 if normalized_msgs[i].get("role") == "user"),
                None,
            )
            if last_user_idx is not None:
                existing = normalized_msgs[last_user_idx]["content"]
                # Chuẩn hóa existing content thành list blocks
                if isinstance(existing, str):
                    text_blocks: list[dict] = [{"type": "text", "text": existing}] if existing else []
                elif isinstance(existing, list):
                    text_blocks = existing
                else:
                    text_blocks = []

                normalized_msgs[last_user_idx] = {
                    **normalized_msgs[last_user_idx],
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{req.image_media_type};base64,{req.image_base64}",
                            },
                        },
                        *text_blocks,
                    ],
                }
                logger.info(
                    f"groq_proxy: đã inject ảnh ({req.image_media_type}) "
                    f"vào user message cuối — model={client.model}"
                )
            else:
                # Không tìm thấy user message → tạo mới
                normalized_msgs.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{req.image_media_type};base64,{req.image_base64}",
                            },
                        },
                        {"type": "text", "text": "Hãy giải bài toán trong ảnh này."},
                    ],
                })
        else:
            # Model text-only: cảnh báo và bỏ ảnh
            logger.warning(
                f"groq_proxy: model '{client.model}' không hỗ trợ vision — "
                "bỏ image_base64. Thêm vào _BUILTIN_VISION_MODELS nếu cần."
            )
            # Thêm chú thích vào user message cuối để LLM biết có ảnh nhưng không đọc được
            last_user_idx = next(
                (i for i in range(len(normalized_msgs) - 1, -1, -1)
                 if normalized_msgs[i].get("role") == "user"),
                None,
            )
            if last_user_idx is not None:
                existing_text = normalized_msgs[last_user_idx].get("content", "")
                if isinstance(existing_text, list):
                    existing_text = " ".join(
                        b.get("text", "") for b in existing_text if b.get("type") == "text"
                    )
                notice = (
                    "⚠️ Model hiện tại không hỗ trợ đọc ảnh.\n"
                    "Vui lòng gõ lại đề bài bằng văn bản để Buddy giải giúp nhé!\n\n"
                    + (f"Câu hỏi kèm theo: {existing_text}" if existing_text else "")
                )
                normalized_msgs[last_user_idx] = {
                    **normalized_msgs[last_user_idx],
                    "content": notice,
                }

    try:
        reply, usage = await client.complete_with_usage(
            messages=normalized_msgs,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except Exception as exc:
        logger.error(f"Groq proxy error: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Groq error: {exc}")

    # ── Log vào chat_logs để Monitor (Conversations / Log Chat / Token) hoạt động ──
    # /v1/messages là route thực tế được frontend dùng (không phải /chat), nên
    # log phải đặt ở đây. Groq trả usage thật (prompt/completion/total_tokens)
    # theo chuẩn OpenAI-compatible — dùng số đó. Chỉ ước lượng theo độ dài ký tự
    # (~4 ký tự/token) khi Groq không trả usage (hiếm, tuỳ model).
    try:
        session_id = req.session_id or "anon"
        username   = req.username or (session_id.split("_")[0] if "_" in session_id else "")

        # Gộp toàn bộ text của các message user vào 1 chuỗi để lưu log
        def _flatten_for_log(content) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            return str(content or "")

        last_user_text = next(
            (
                _flatten_for_log(m.get("content", ""))
                for m in reversed(normalized_msgs)
                if m.get("role") == "user"
            ),
            "",
        )

        total_tokens = usage.get("total_tokens")
        if not total_tokens:
            # Fallback ước lượng nếu Groq không trả usage
            total_tokens = max(1, (len(last_user_text) + len(reply)) // 4)
            logger.warning(
                f"[{session_id}] Groq không trả usage — ước lượng tokens={total_tokens}"
            )

        user_id = db.get_user_id_by_username(username) if username else None
        db.log_chat(
            session_id=session_id,
            message=last_user_text,
            answer=reply,
            route=req.route_tag or "v1_messages",
            model=client.model,
            username=username,
            user_id=user_id,
            has_image=bool(req.image_base64),
            tokens_used=total_tokens,
        )
    except Exception as db_exc:
        logger.warning(f"DB log error (/v1/messages): {db_exc}")


    return {
        "content": [{"type": "text", "text": reply}],
        "model":   client.model,
        "role":    "assistant",
    }


# ─── Chat ─────────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng.")
    try:
        result = await pipeline.run(
            message=req.message,
            session_id=req.session_id,
            topic=req.topic,
            subject=req.subject,
        )
        try:
            username = req.session_id.split('_')[0] if '_' in req.session_id else ""
            user_id  = db.get_user_id_by_username(username) if username else None
            db.log_chat(
                session_id=req.session_id,
                message=req.message,
                answer=result.get("answer", ""),
                route=result.get("route", ""),
                subject=req.subject or "",
                topic=req.topic or "",
                model=pipeline.llm.model,
                username=username,
                user_id=user_id,
            )
        except Exception as db_exc:
            logger.warning(f"DB log error: {db_exc}")

        return ChatResponse(
            answer=result["answer"],
            sources=result.get("sources", []),
            route=result.get("route", "general"),
            session_id=req.session_id,
            model=pipeline.llm.model,
        )
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng.")

    async def event_generator():
        async for chunk in pipeline.stream(
            message=req.message,
            session_id=req.session_id,
            topic=req.topic,
            subject=req.subject,
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Chat với ảnh đính kèm ────────────────────────────────────────────────────
# Các định dạng ảnh được phép
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png",
    "image/gif", "image/webp",
}

# Model JSON khớp đúng với những gì frontend gửi lên
class ImageChatRequest(BaseModel):
    image_base64: str                        # chuỗi base64 của ảnh
    media_type:   str  = "image/jpeg"        # MIME type, vd "image/png"
    prompt:       str  = ""                  # câu hỏi kèm ảnh (frontend dùng key "prompt")
    session_id:   str  = "buddy-main"
    topic:        Optional[str] = None
    subject:      Optional[str] = None

@app.post("/chat/image", response_model=ChatResponse)
async def chat_with_image(req: ImageChatRequest):
    """
    Nhận JSON { image_base64, media_type, prompt, session_id } từ frontend.
    Chỉ hỗ trợ định dạng ảnh: JPEG, PNG, GIF, WEBP.
    """
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng.")

    # ── Validate MIME type ────────────────────────────────────────────────────
    content_type = req.media_type.lower().strip()
    if content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Loại ảnh '{content_type}' không được hỗ trợ. "
                f"Chỉ chấp nhận: {', '.join(sorted(_ALLOWED_IMAGE_TYPES))}."
            ),
        )

    # ── Validate base64 và kích thước ────────────────────────────────────────
    if not req.image_base64:
        raise HTTPException(status_code=400, detail="image_base64 không được rỗng.")

    try:
        raw_bytes = base64.b64decode(req.image_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="image_base64 không hợp lệ, không decode được.")

    MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Ảnh quá lớn ({len(raw_bytes) // 1024} KB). Giới hạn là 20 MB.",
        )

    message = req.prompt or "Hãy giải bài toán trong ảnh này từng bước."
    logger.info(
        f"[{req.session_id}] Nhận ảnh JSON: {content_type}, "
        f"{len(raw_bytes) // 1024} KB, prompt={message[:60]!r}"
    )

    # ── Gọi pipeline với ảnh ─────────────────────────────────────────────────
    try:
        result = await pipeline.run(
            message=message,
            session_id=req.session_id,
            topic=req.topic,
            subject=req.subject,
            image_base64=req.image_base64,   # truyền thẳng b64 string vào pipeline
            image_media_type=content_type,
        )
    except Exception as exc:
        logger.error(f"Image chat error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        route=result.get("route", "vision"),
        session_id=req.session_id,
        model=pipeline.llm.model,
    )


# ─── Subjects & Topics (dynamic từ data/) ────────────────────────────────────
@app.get("/subjects")
async def list_subjects():
    """
    Trả về danh sách subjects từ HAI nguồn:
    1. Thư mục data/ (luôn chính xác theo file thực tế)
    2. RAGEngine (những gì đã được index)
    """
    dir_structure = data_loader.list_structure() if data_loader else {}
    indexed       = set(rag_engine.list_subjects()) if rag_engine else set()
    all_subjects  = sorted(set(dir_structure.keys()) | indexed)
    return {
        "subjects": all_subjects,
        "detail": {
            s: {"has_data_folder": s in dir_structure, "is_indexed": s in indexed}
            for s in all_subjects
        },
    }


@app.get("/subjects/{subject}/topics")
async def list_topics(subject: str):
    """
    Trả về topics từ thư mục data/{subject}/ và từ RAGEngine.
    """
    dir_topics     = []
    if data_loader:
        structure  = data_loader.list_structure()
        dir_topics = structure.get(subject, [])

    indexed_topics = rag_engine.list_topics(subject) if rag_engine else []
    all_topics     = sorted(set(dir_topics) | set(indexed_topics))

    return {
        "subject": subject,
        "topics":  all_topics,
        "files": {
            t: data_loader.get_topic_files(subject, t)
            for t in dir_topics
        } if data_loader else {},
    }


# ─── Synthesis (điểm mới quan trọng nhất) ────────────────────────────────────
@app.post("/topics/synthesis")
async def synthesize_topic_post(req: SynthesisRequest):
    """
    Tổng hợp toàn bộ tài liệu của một chủ đề thành nội dung có cấu trúc.
    LLM đọc tất cả chunks → trả về overview, key_concepts, formulas, v.v.
    Kết quả được cache để lần sau nhanh hơn.
    """
    if rag_engine is None or pipeline is None:
        raise HTTPException(status_code=503, detail="Hệ thống chưa sẵn sàng.")
    try:
        return await _synthesize_topic(
            subject=req.subject,
            topic=req.topic,
            llm=pipeline.llm,
            rag=rag_engine,
            force=req.force,
        )
    except Exception as exc:
        logger.error(f"Synthesis error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/topics/{subject}/{topic}/synthesis")
async def synthesize_topic_get(subject: str, topic: str, force: bool = False):
    """GET alias – tiện dùng từ browser hoặc frontend đơn giản."""
    if rag_engine is None or pipeline is None:
        raise HTTPException(status_code=503, detail="Hệ thống chưa sẵn sàng.")
    try:
        return await _synthesize_topic(
            subject=subject,
            topic=topic,
            llm=pipeline.llm,
            rag=rag_engine,
            force=force,
        )
    except Exception as exc:
        logger.error(f"Synthesis error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Topic raw content (backward compat) ─────────────────────────────────────
@app.get("/topics/{subject}/{topic}/content")
async def get_topic_content(subject: str, topic: str):
    if rag_engine is None:
        raise HTTPException(status_code=503, detail="RAG engine chưa sẵn sàng.")
    content = rag_engine.get_topic_content(subject=subject, topic=topic)
    if not content:
        raise HTTPException(
            status_code=404,
            detail=f"Chưa có nội dung nào cho '{subject}/{topic}'. "
                   "Hãy đặt file vào data/{subject}/{topic}/ và gọi /ingest/reload.",
        )
    return content


# ─── Ingest: file đơn lẻ ─────────────────────────────────────────────────────
@app.post("/ingest", response_model=IngestResponse)
async def ingest_document(req: IngestRequest):
    if rag_engine is None:
        raise HTTPException(status_code=503, detail="RAG engine chưa sẵn sàng.")
    try:
        chunker = DocumentChunker()
        chunks  = chunker.chunk_file(
            file_path=req.file_path,
            subject=req.subject,
            topic=req.topic,
            extra_metadata=req.metadata,
        )
        rag_engine.add_documents(chunks)
        # Xoá synthesis cache của topic này vì đã có tài liệu mới
        _synthesis_cache.pop(f"{req.subject}/{req.topic}", None)
        return IngestResponse(
            status="success",
            chunks_created=len(chunks),
            message=f"Ingest {len(chunks)} chunks từ '{req.file_path}'.",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy: {req.file_path}")
    except Exception as e:
        logger.error(f"Ingest error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Ingest: reload toàn bộ data/ ─────────────────────────────────────────────
@app.post("/ingest/reload")
async def reload_data(background_tasks: BackgroundTasks, force: bool = False):
    """
    Scan lại toàn bộ data/ và ingest file mới / đã sửa.
    Dùng sau khi bạn thêm/sửa tài liệu mà không restart server.

    Query param: ?force=true → re-ingest toàn bộ kể cả file không đổi.
    """
    if rag_engine is None or data_loader is None:
        raise HTTPException(status_code=503, detail="Hệ thống chưa sẵn sàng.")

    def _do_reload():
        global _synthesis_cache
        summary = data_loader.ingest_all(rag_engine, force=force)
        if summary["new_files_ingested"] > 0:
            _synthesis_cache.clear()   # Xoá toàn bộ cache khi có file mới
            logger.info("Synthesis cache đã được xoá sau reload.")
        return summary

    background_tasks.add_task(_do_reload)
    return {
        "status":  "accepted",
        "message": "Đang reload dữ liệu trong background. Kiểm tra log để theo dõi tiến trình.",
        "force":   force,
    }


# ─── Synthesis cache management ───────────────────────────────────────────────
@app.delete("/topics/synthesis/cache")
async def clear_synthesis_cache():
    """Xoá toàn bộ synthesis cache."""
    count = len(_synthesis_cache)
    _synthesis_cache.clear()
    return {"cleared": count, "message": f"Đã xoá {count} synthesis cache entries."}


# ─── Virtual Classroom: danh sách file theo group ────────────────────────────
@app.get("/classroom/{subject}/{topic}/files")
async def classroom_files(subject: str, topic: str):
    """
    Trả về danh sách tên file PDF/DOCX/TXT trong data/{subject}/{topic}/
    để Virtual Classroom hiển thị danh sách bài học thực tế.
    """
    if data_loader is None:
        raise HTTPException(status_code=503, detail="DataLoader chưa sẵn sàng.")
    files = data_loader.get_topic_files(subject, topic)
    if not files:
        # Không lỗi – trả về list rỗng; frontend tự hiển thị thông báo
        return {"subject": subject, "topic": topic, "files": []}
    return {"subject": subject, "topic": topic, "files": files}


# ─── Virtual Classroom: tổng hợp + hội thoại bài học ─────────────────────────
class ClassroomLessonRequest(BaseModel):
    subject:    str
    topic:      str
    lesson:     str            # tên file (ví dụ: "Bai_1_To_hop.pdf")
    message:    str = ""       # câu hỏi của học sinh; rỗng = mở đầu bài học
    session_id: str = "default"
    history:    list[dict] = []   # [{"role":"user"|"assistant","content":"..."}]

class ClassroomLessonResponse(BaseModel):
    answer: str
    lesson_outline: list[str] = []   # chỉ trả về lần đầu (message rỗng)
    sources: list[dict] = []

# @app.post("/classroom/lesson")
# async def classroom_lesson(req: ClassroomLessonRequest):
#     """
#     Endpoint chính cho Virtual Classroom.

#     • Khi message == "" (mở đầu):
#         – Lấy toàn bộ chunks của topic/lesson từ RAG
#         – LLM tổng hợp → trả về outline + lý thuyết đầu mục 1
#         – lesson_outline = ["I. Định nghĩa", "II. Công thức", ...]

#     • Khi message != "" (học sinh hỏi):
#         – RAG search trong topic/lesson
#         – LLM trả lời có ngữ cảnh, theo đúng đề mục hiện tại
#         – lesson_outline = []  (không cần render lại)
#     """
#     if rag_engine is None or pipeline is None:
#         raise HTTPException(status_code=503, detail="Hệ thống chưa sẵn sàng.")

#     # ── 1. Lấy chunks liên quan ───────────────────────────────────────────────
#     # Tìm theo lesson (source_file chứa tên file), fallback về toàn topic
#     lesson_stem = req.lesson.rsplit(".", 1)[0].lower().replace(" ", "_")

#     all_topic_chunks = rag_engine.get_all_chunks(subject=req.subject, topic=req.topic)

#     # Filter chunks thuộc đúng bài học nếu có; nếu không thì lấy toàn topic
#     lesson_chunks = [
#         c for c in all_topic_chunks
#         if lesson_stem in c.source_file.lower().replace(" ", "_")
#     ]
#     if not lesson_chunks:
#         lesson_chunks = all_topic_chunks  # fallback

#     # Gom nội dung (tối đa 5000 ký tự để không vượt context window)
#     def _join_chunks(chunks, max_chars=5000) -> str:
#         out = []
#         total = 0
#         for c in chunks:
#             if total + len(c.content) > max_chars:
#                 break
#             out.append(c.content)
#             total += len(c.content)
#         return "\n\n---\n\n".join(out)

#     lesson_content = _join_chunks(lesson_chunks)

#     # ── 2. Xây system prompt theo chế độ ────────────────────────────────────
#     if not req.message:
#         # ── CHẾ ĐỘ MỞ ĐẦU: tổng hợp bài học, render đầu mục + lý thuyết mục 1
#         system_prompt = (
#             "Bạn là gia sư toán AI đang dạy bài học trên bảng ảo cho học sinh THCS.\n"
#             "Dựa vào TÀI LIỆU bên dưới, hãy:\n"
#             "1. Liệt kê OUTLINE bài học (tối đa 6 đầu mục, đánh số La Mã: I, II, III...)\n"
#             "2. Giảng CHI TIẾT Mục I đầu tiên: định nghĩa, công thức, ví dụ minh họa.\n"
#             "3. Kết thúc bằng 1 câu hỏi khởi động ngắn để kiểm tra hiểu bài.\n\n"
#             "QUAN TRỌNG:\n"
#             "- Trả lời bằng ngôn ngữ của tài liệu (tiếng Việt).\n"
#             "- Dùng **bold** cho các thuật ngữ quan trọng.\n"
#             "- Viết công thức rõ ràng (dùng ký hiệu toán học).\n"
#             "- Giọng văn thân thiện, dễ hiểu với học sinh cấp 2.\n"
#             "- KHÔNG bịa đặt; chỉ dùng thông tin từ tài liệu.\n\n"
#             f"TÀI LIỆU ({req.lesson}):\n{lesson_content}"
#         )
#         user_msg = f"Hãy bắt đầu dạy bài: {req.lesson}"

#     else:
#         # ── CHẾ ĐỘ HỎI ĐÁP: học sinh đặt câu hỏi
#         # RAG search để bổ sung context liên quan nhất
#         rag_chunks = rag_engine.search(
#             query=req.message,
#             top_k=4,
#             subject=req.subject,
#             topic=req.topic,
#         )
#         rag_context = rag_engine.get_context_string(rag_chunks) if rag_chunks else lesson_content[:2000]

#         system_prompt = (
#             "Bạn là gia sư toán AI đang dạy bài học trên bảng ảo.\n"
#             f"Bài học hiện tại: **{req.lesson}** (môn: {req.subject}, chủ đề: {req.topic})\n\n"
#             "Nguyên tắc trả lời:\n"
#             "- Hướng dẫn từng bước nhỏ, KHÔNG giải hết thay học sinh.\n"
#             "- Sau mỗi giải thích, hỏi lại 1 câu để học sinh tự xác nhận hiểu.\n"
#             "- Nếu học sinh hỏi đúng → khen cụ thể, chuyển sang đầu mục tiếp theo.\n"
#             "- Dùng **bold** cho công thức và thuật ngữ chính.\n"
#             "- Ngắn gọn (tối đa 150 từ mỗi câu trả lời).\n"
#             "- Trả lời bằng tiếng Việt.\n\n"
#             f"NGỮ CẢNH TÀI LIỆU:\n{rag_context}"
#         )
#         user_msg = req.message

#     # ── 3. Gọi LLM ───────────────────────────────────────────────────────────
#     messages = [{"role": "system", "content": system_prompt}]
#     # Thêm lịch sử hội thoại (tối đa 10 lượt gần nhất)
#     if req.history:
#         messages.extend(req.history[-10:])
#     messages.append({"role": "user", "content": user_msg})

#     try:
#         answer = await pipeline.llm.complete(
#             messages=messages,
#             temperature=0.3,
#             max_tokens=1200,
#         )
#     except Exception as exc:
#         logger.error(f"Classroom LLM error: {exc}", exc_info=True)
#         raise HTTPException(status_code=500, detail=str(exc))

#     # ── 4. Parse outline từ câu trả lời mở đầu ───────────────────────────────
#     outline: list[str] = []
#     if not req.message:
#         import re
#         # Tìm các dòng dạng "I. ...", "II. ...", "1. ...", "- ..." trong phần đầu
#         outline_matches = re.findall(
#             r'^(?:[IVXivx]+\.|[1-9]\.|[-•])\s+(.+)$',
#             answer, re.MULTILINE
#         )
#         outline = [m.strip() for m in outline_matches[:6]]

#     sources = [c.to_dict() for c in (lesson_chunks[:3] if not req.message else [])]

#     return ClassroomLessonResponse(
#         answer=answer,
#         lesson_outline=outline,
#         sources=sources,
#     )
@app.post("/classroom/lesson")
async def classroom_lesson(req: ClassroomLessonRequest):
    if rag_engine is None or pipeline is None:
        raise HTTPException(status_code=503)

    # ===== LẤY CHUNKS TỪ RAG =====
    all_chunks = rag_engine.get_all_chunks(req.subject, req.topic)

    # Filter theo lesson file nếu có
    lesson_stem = req.lesson.rsplit(".", 1)[0].lower().replace(" ", "_")
    lesson_chunks = [
        c for c in all_chunks
        if lesson_stem in c.source_file.lower().replace(" ", "_")
    ]
    if not lesson_chunks:
        lesson_chunks = all_chunks  # fallback toàn topic

    has_rag = len(lesson_chunks) > 0

    def join_chunks(cs, max_chars=6000):
        out, total = [], 0
        for c in cs:
            if total + len(c.content) > max_chars:
                break
            out.append(c.content)
            total += len(c.content)
        return "\n\n".join(out)

    lesson_content = join_chunks(lesson_chunks)

    # ===== Helper: gọi LLM với retry khi gặp 429 =====
    import asyncio

    async def llm_complete_with_retry(messages, max_tokens, temperature=0.3, retries=3):
        for attempt in range(retries):
            try:
                return await pipeline.llm.complete(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str and attempt < retries - 1:
                    # Parse retry-after từ message nếu có, mặc định 2 giây
                    wait = 2.0
                    import re as _re
                    m = _re.search(r'try again in (\d+\.?\d*)ms', err_str)
                    if m:
                        wait = float(m.group(1)) / 1000 + 0.1
                    logger.warning(f"Groq 429 – chờ {wait:.1f}s rồi thử lại (lần {attempt+1})…")
                    await asyncio.sleep(wait)
                else:
                    raise

    # Sources metadata để frontend biết RAG có data hay không
    sources = [
        {
            "source_file": c.source_file,
            "doc_type": c.doc_type,
            "subject": c.subject,
            "topic": c.topic,
        }
        for c in lesson_chunks[:3]
    ] if has_rag else []

    # ===== MODE 1: MỞ BÀI HỌC =====
    if not req.message.strip():
        if has_rag:
            system = f"""Bạn là gia sư toán học. CHỈ dùng nội dung từ SGK bên dưới.

YÊU CẦU:
1. Trích đúng các đầu mục I, II, III... từ tài liệu (không tự đặt mục mới)
2. Giảng Mục I: định nghĩa + ví dụ từ SGK
3. Kết bằng 1 câu hỏi ngắn kiểm tra hiểu bài

TÀI LIỆU ({req.lesson}):
{lesson_content}"""
        else:
            system = f"""Bạn là gia sư toán học. Chưa có SGK trong hệ thống.
Hãy giới thiệu bài "{req.lesson}" theo chương trình lớp 6 Việt Nam và liệt kê 3-4 mục chính."""

        try:
            answer = await llm_complete_with_retry(
                messages=[{"role": "user", "content": system}],
                max_tokens=1200,
            )
        except Exception as exc:
            logger.error(f"Classroom open-lesson LLM error: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))

        import re
        outline = [
            line.strip()
            for line in answer.split("\n")
            if re.match(r'^(I{1,3}V?|VI{0,3}|IX|X)\.\s', line.strip())
        ]

        return {
            "answer": answer,
            "lesson_outline": outline,
            "sources": sources,
            "has_rag": has_rag,
        }

    # ===== MODE 2: HỎI ĐÁP (RAG search) =====
    if has_rag:
        results = rag_engine.search(
            query=req.message,
            subject=req.subject,
            topic=req.topic,
            top_k=5,
        )
        # FIX: dùng r.document.content, không phải r.content
        context = "\n\n---\n\n".join([r.document.content for r in results])
        qa_sources = [
            {
                "source_file": r.document.source_file,
                "doc_type": r.document.doc_type,
                "score": round(r.score, 3),
            }
            for r in results
        ]
    else:
        context = ""
        qa_sources = []

    if context:
        system = f"""Bạn là gia sư toán. Trả lời dựa trên SGK bên dưới. Không bịa nội dung ngoài tài liệu. Ngắn gọn, rõ ràng.

TÀI LIỆU:
{context}"""
    else:
        system = "Bạn là gia sư toán học thân thiện dành cho học sinh THCS Việt Nam. Trả lời ngắn gọn, rõ ràng."

    # Xây messages với history
    messages = [{"role": "system", "content": system}]
    if req.history:
        messages.extend(req.history[-8:])
    messages.append({"role": "user", "content": req.message})

    try:
        answer = await llm_complete_with_retry(
            messages=messages,
            max_tokens=800,
        )
    except Exception as exc:
        logger.error(f"Classroom Q&A LLM error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "answer": answer,
        "lesson_outline": [],
        "sources": qa_sources,
        "has_rag": has_rag,
    }


# ─── RAG Chunks endpoint cho Topic Detail view ────────────────────────────────
@app.get("/topics/{subject}/{topic}/chunks")
async def get_topic_chunks(subject: str, topic: str):
    """
    Trả về RAW chunks từ RAG cho một topic – dùng bởi frontend topic detail view.
    Không qua LLM, không sinh nội dung, chỉ trả đúng dữ liệu từ SGK.
    """
    if rag_engine is None:
        raise HTTPException(status_code=503, detail="RAG engine chưa sẵn sàng.")
    all_chunks = rag_engine.get_all_chunks(subject=subject, topic=topic)
    if not all_chunks:
        return {
            "subject": subject,
            "topic": topic,
            "status": "empty",
            "chunks": [],
            "source_files": [],
        }
    return {
        "subject": subject,
        "topic": topic,
        "status": "ok",
        "chunk_count": len(all_chunks),
        "source_files": sorted({c.source_file.split("/")[-1].split("\\")[-1] for c in all_chunks}),
        "chunks": [
            {
                "content": c.content,
                "doc_type": c.doc_type,
                "source_file": c.source_file.split("/")[-1].split("\\")[-1],
                "page": c.page,
                "chunk_id": c.chunk_id,
            }
            for c in all_chunks
        ],
    }


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)