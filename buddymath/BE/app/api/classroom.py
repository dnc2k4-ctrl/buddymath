"""
classroom.py – Router Virtual Classroom: danh sách bài học + hội thoại giảng bài.
"""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException

from app.schemas.catalog import ClassroomLessonRequest
from app.services.runtime import get_loader, get_pipeline, get_rag

logger = logging.getLogger(__name__)
router = APIRouter(tags=["classroom"])


@router.get("/classroom/{subject}/{topic}/files")
async def classroom_files(subject: str, topic: str):
    """Danh sách file PDF/DOCX/TXT trong data/{subject}/{topic}/."""
    files = get_loader().get_topic_files(subject, topic)
    return {"subject": subject, "topic": topic, "files": files}


def _join_chunks(chunks, max_chars: int = 6000) -> str:
    out, total = [], 0
    for c in chunks:
        if total + len(c.content) > max_chars:
            break
        out.append(c.content)
        total += len(c.content)
    return "\n\n".join(out)


async def _complete_with_retry(llm, messages, max_tokens, temperature=0.3, retries=3):
    """Gọi LLM, tự retry khi gặp 429 (rate limit)."""
    for attempt in range(retries):
        try:
            return await llm.complete(messages=messages, max_tokens=max_tokens, temperature=temperature)
        except Exception as exc:
            err = str(exc)
            if "429" in err and attempt < retries - 1:
                wait = 2.0
                m = re.search(r"try again in (\d+\.?\d*)ms", err)
                if m:
                    wait = float(m.group(1)) / 1000 + 0.1
                logger.warning(f"Groq 429 – chờ {wait:.1f}s rồi thử lại (lần {attempt+1})…")
                await asyncio.sleep(wait)
            else:
                raise


@router.post("/classroom/lesson")
async def classroom_lesson(req: ClassroomLessonRequest):
    rag      = get_rag()
    pipeline = get_pipeline()

    all_chunks  = rag.get_all_chunks(req.subject, req.topic)
    lesson_stem = req.lesson.rsplit(".", 1)[0].lower().replace(" ", "_")
    lesson_chunks = [
        c for c in all_chunks
        if lesson_stem in c.source_file.lower().replace(" ", "_")
    ] or all_chunks
    has_rag = len(lesson_chunks) > 0

    sources = [
        {"source_file": c.source_file, "doc_type": c.doc_type, "subject": c.subject, "topic": c.topic}
        for c in lesson_chunks[:3]
    ] if has_rag else []

    # ── MODE 1: MỞ BÀI HỌC ────────────────────────────────────────────────────
    if not req.message.strip():
        lesson_content = _join_chunks(lesson_chunks)
        if has_rag:
            system = f"""Bạn là gia sư toán học. CHỈ dùng nội dung từ SGK bên dưới.

YÊU CẦU:
1. Trích đúng các đầu mục I, II, III... từ tài liệu (không tự đặt mục mới)
2. Giảng Mục I: định nghĩa + ví dụ từ SGK
3. Kết bằng 1 câu hỏi ngắn kiểm tra hiểu bài

TÀI LIỆU ({req.lesson}):
{lesson_content}"""
        else:
            system = (
                f'Bạn là gia sư toán học. Chưa có SGK trong hệ thống.\n'
                f'Hãy giới thiệu bài "{req.lesson}" theo chương trình lớp 6 Việt Nam '
                f'và liệt kê 3-4 mục chính.'
            )
        try:
            answer = await _complete_with_retry(pipeline.llm, [{"role": "user", "content": system}], max_tokens=1200)
        except Exception as exc:
            logger.error(f"Classroom open-lesson LLM error: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))

        outline = [
            line.strip() for line in answer.split("\n")
            if re.match(r"^(I{1,3}V?|VI{0,3}|IX|X)\.\s", line.strip())
        ]
        return {"answer": answer, "lesson_outline": outline, "sources": sources, "has_rag": has_rag}

    # ── MODE 2: HỎI ĐÁP (RAG search) ──────────────────────────────────────────
    if has_rag:
        results    = rag.search(query=req.message, subject=req.subject, topic=req.topic, top_k=5)
        context    = "\n\n---\n\n".join(r.document.content for r in results)
        qa_sources = [
            {"source_file": r.document.source_file, "doc_type": r.document.doc_type, "score": round(r.score, 3)}
            for r in results
        ]
    else:
        context, qa_sources = "", []

    if context:
        system = f"""Bạn là gia sư toán. Trả lời dựa trên SGK bên dưới. Không bịa nội dung ngoài tài liệu. Ngắn gọn, rõ ràng.

TÀI LIỆU:
{context}"""
    else:
        system = "Bạn là gia sư toán học thân thiện dành cho học sinh THCS Việt Nam. Trả lời ngắn gọn, rõ ràng."

    messages = [{"role": "system", "content": system}]
    if req.history:
        messages.extend(req.history[-8:])
    messages.append({"role": "user", "content": req.message})

    try:
        answer = await _complete_with_retry(pipeline.llm, messages, max_tokens=800)
    except Exception as exc:
        logger.error(f"Classroom Q&A LLM error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return {"answer": answer, "lesson_outline": [], "sources": qa_sources, "has_rag": has_rag}
