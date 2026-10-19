"""
runtime.py – Các singleton dùng chung (RAG engine, pipeline, data loader)
được khởi tạo trong lifespan và truy cập bởi các router qua getter.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from app.config import INDEX_PATH, IS_VERCEL, META_PATH
from app.llm.pipeline import MathBuddyPipeline
from app.rag.data_loader import DataDirectoryLoader
from app.rag.engine import RAGEngine

rag_engine:  Optional[RAGEngine]         = None
pipeline:    Optional[MathBuddyPipeline] = None
data_loader: Optional[DataDirectoryLoader] = None

# Cache synthesis theo key "subject/topic" (mất khi restart)
synthesis_cache: dict[str, dict] = {}


def init_runtime() -> dict:
    """Khởi tạo core components và ingest data/. Gọi trong lifespan."""
    global rag_engine, pipeline, data_loader
    if IS_VERCEL:
        missing = [path.name for path in (INDEX_PATH, META_PATH) if not path.is_file()]
        if missing:
            raise RuntimeError(
                "Vercel deployment is missing the prebuilt RAG artifact(s): "
                + ", ".join(missing)
            )

    rag_engine  = RAGEngine()
    pipeline    = MathBuddyPipeline(rag_engine=rag_engine)
    data_loader = DataDirectoryLoader()
    if IS_VERCEL:
        if not rag_engine.document_count:
            raise RuntimeError("The packaged Vercel RAG metadata contains no indexed documents.")
        return {
            "new_files_ingested": 0,
            "skipped_files": len(data_loader.scan()),
            "total_chunks": rag_engine.document_count,
            "errors": [],
        }
    return data_loader.ingest_all(rag_engine)


def get_rag() -> RAGEngine:
    if rag_engine is None:
        raise HTTPException(status_code=503, detail="RAG engine chưa sẵn sàng.")
    return rag_engine


def get_pipeline() -> MathBuddyPipeline:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng.")
    return pipeline


def get_loader() -> DataDirectoryLoader:
    if data_loader is None:
        raise HTTPException(status_code=503, detail="DataLoader chưa sẵn sàng.")
    return data_loader
