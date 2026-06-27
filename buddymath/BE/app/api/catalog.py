"""
catalog.py – Router danh mục môn/chủ đề, synthesis và ingest tài liệu.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.rag.chunking import DocumentChunker
from app.schemas.catalog import IngestRequest, IngestResponse, SynthesisRequest
from app.services import runtime
from app.services.runtime import get_loader, get_pipeline, get_rag
from app.services.synthesis_service import synthesize_topic

logger = logging.getLogger(__name__)
router = APIRouter(tags=["catalog"])


# ─── Subjects & Topics (dynamic từ data/) ─────────────────────────────────────
@router.get("/subjects")
async def list_subjects():
    loader        = get_loader()
    rag           = get_rag()
    dir_structure = loader.list_structure()
    indexed       = set(rag.list_subjects())
    all_subjects  = sorted(set(dir_structure.keys()) | indexed)
    return {
        "subjects": all_subjects,
        "detail": {
            s: {"has_data_folder": s in dir_structure, "is_indexed": s in indexed}
            for s in all_subjects
        },
    }


@router.get("/subjects/{subject}/topics")
async def list_topics(subject: str):
    loader     = get_loader()
    rag        = get_rag()
    structure  = loader.list_structure()
    dir_topics = structure.get(subject, [])
    all_topics = sorted(set(dir_topics) | set(rag.list_topics(subject)))
    return {
        "subject": subject,
        "topics":  all_topics,
        "files":   {t: loader.get_topic_files(subject, t) for t in dir_topics},
    }


# ─── Synthesis ────────────────────────────────────────────────────────────────
@router.post("/topics/synthesis")
async def synthesize_topic_post(req: SynthesisRequest):
    try:
        return await synthesize_topic(
            subject=req.subject, topic=req.topic,
            llm=get_pipeline().llm, rag=get_rag(),
            cache=runtime.synthesis_cache, force=req.force,
        )
    except Exception as exc:
        logger.error(f"Synthesis error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/topics/{subject}/{topic}/synthesis")
async def synthesize_topic_get(subject: str, topic: str, force: bool = False):
    try:
        return await synthesize_topic(
            subject=subject, topic=topic,
            llm=get_pipeline().llm, rag=get_rag(),
            cache=runtime.synthesis_cache, force=force,
        )
    except Exception as exc:
        logger.error(f"Synthesis error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/topics/synthesis/cache")
async def clear_synthesis_cache():
    count = len(runtime.synthesis_cache)
    runtime.synthesis_cache.clear()
    return {"cleared": count, "message": f"Đã xoá {count} synthesis cache entries."}


# ─── Topic raw content / chunks ───────────────────────────────────────────────
@router.get("/topics/{subject}/{topic}/content")
async def get_topic_content(subject: str, topic: str):
    content = get_rag().get_topic_content(subject=subject, topic=topic)
    if not content:
        raise HTTPException(
            status_code=404,
            detail=f"Chưa có nội dung nào cho '{subject}/{topic}'. "
                   "Hãy đặt file vào data/{subject}/{topic}/ và gọi /ingest/reload.",
        )
    return content


@router.get("/topics/{subject}/{topic}/chunks")
async def get_topic_chunks(subject: str, topic: str):
    """RAW chunks từ RAG cho topic detail view (không qua LLM)."""
    rag        = get_rag()
    all_chunks = rag.get_all_chunks(subject=subject, topic=topic)
    if not all_chunks:
        return {"subject": subject, "topic": topic, "status": "empty", "chunks": [], "source_files": []}

    def _basename(p: str) -> str:
        return p.replace("\\", "/").split("/")[-1]

    return {
        "subject":      subject,
        "topic":        topic,
        "status":       "ok",
        "chunk_count":  len(all_chunks),
        "source_files": sorted({_basename(c.source_file) for c in all_chunks}),
        "chunks": [
            {
                "content":     c.content,
                "doc_type":    c.doc_type,
                "source_file": _basename(c.source_file),
                "page":        c.page,
                "chunk_id":    c.chunk_id,
            }
            for c in all_chunks
        ],
    }


# ─── Ingest ───────────────────────────────────────────────────────────────────
@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(req: IngestRequest):
    rag = get_rag()
    try:
        chunks = DocumentChunker().chunk_file(
            file_path=req.file_path, subject=req.subject, topic=req.topic,
            extra_metadata=req.metadata,
        )
        rag.add_documents(chunks)
        runtime.synthesis_cache.pop(f"{req.subject}/{req.topic}", None)
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


@router.post("/ingest/reload")
async def reload_data(background_tasks: BackgroundTasks, force: bool = False):
    """Scan lại data/ và ingest file mới/đã sửa (background). ?force=true → re-ingest toàn bộ."""
    rag    = get_rag()
    loader = get_loader()

    def _do_reload():
        summary = loader.ingest_all(rag, force=force)
        if summary["new_files_ingested"] > 0:
            runtime.synthesis_cache.clear()
            logger.info("Synthesis cache đã được xoá sau reload.")
        return summary

    background_tasks.add_task(_do_reload)
    return {
        "status":  "accepted",
        "message": "Đang reload dữ liệu trong background. Kiểm tra log để theo dõi.",
        "force":   force,
    }
