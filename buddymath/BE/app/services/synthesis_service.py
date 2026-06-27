"""
synthesis_service.py – Tổng hợp toàn bộ tài liệu của một topic thành nội dung
có cấu trúc (overview, key_concepts, formulas...) qua LLM. Có cache.
"""
from __future__ import annotations

import json
import logging

from app.llm.client import LLMClient
from app.rag.engine import RAGEngine

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Bạn là trợ lý giáo dục. Nhiệm vụ của bạn là tổng hợp các tài liệu học tập "
    "thành một bản tóm tắt chủ đề có cấu trúc rõ ràng.\n"
    "Hãy trả về DUY NHẤT một JSON object (không có markdown, không có ```), với cấu trúc sau:\n"
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


async def synthesize_topic(
    subject: str,
    topic: str,
    llm: LLMClient,
    rag: RAGEngine,
    cache: dict[str, dict],
    force: bool = False,
) -> dict:
    cache_key = f"{subject}/{topic}"
    if not force and cache_key in cache:
        logger.info(f"Synthesis cache hit: {cache_key}")
        return cache[cache_key]

    all_chunks = rag.get_all_chunks(subject=subject, topic=topic)
    if not all_chunks:
        return {
            "subject": subject,
            "topic":   topic,
            "status":  "empty",
            "message": f"Chưa có tài liệu nào cho chủ đề '{topic}' trong '{subject}'.",
        }

    theory   = [c for c in all_chunks if c.doc_type == "theory"]
    exercise = [c for c in all_chunks if c.doc_type == "exercise"]
    solution = [c for c in all_chunks if c.doc_type == "solution"]

    def _join(chunks, max_chars: int) -> str:
        joined = "\n\n---\n\n".join(c.content for c in chunks)
        return joined[:max_chars]

    parts = []
    if theory:
        parts.append("=== LÝ THUYẾT ===\n" + _join(theory, 4000))
    if exercise:
        parts.append("=== BÀI TẬP ===\n" + _join(exercise, 2000))
    if solution:
        parts.append("=== LỜI GIẢI ===\n" + _join(solution, 1500))
    full_context = "\n\n".join(parts)

    user_message = f"Chủ đề: {topic} (môn: {subject})\n\nTài liệu:\n{full_context}"

    raw_reply = ""
    try:
        raw_reply = (await llm.complete(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.2,
            max_tokens=1500,
        )).strip()

        if raw_reply.startswith("```"):
            raw_reply = raw_reply.split("```")[1]
            if raw_reply.startswith("json"):
                raw_reply = raw_reply[4:]
        synthesis = json.loads(raw_reply)

    except json.JSONDecodeError as exc:
        logger.warning(f"LLM không trả về JSON hợp lệ: {exc}. Dùng plain text.")
        synthesis = {
            "title":              topic,
            "overview":           raw_reply[:500] or "Không thể tổng hợp.",
            "key_concepts":       [],
            "important_formulas": [],
            "learning_steps":     [],
            "common_mistakes":    [],
            "example_summary":    "",
        }
    except Exception as exc:
        logger.error(f"Synthesis LLM error: {exc}", exc_info=True)
        raise

    result = {
        "subject":      subject,
        "topic":        topic,
        "status":       "ok",
        "chunk_count":  len(all_chunks),
        "source_files": sorted({c.source_file.replace("\\", "/").split("/")[-1] for c in all_chunks}),
        "synthesis":    synthesis,
    }
    cache[cache_key] = result
    return result
