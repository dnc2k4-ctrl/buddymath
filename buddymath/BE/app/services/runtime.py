"""
runtime.py – Các singleton dùng chung (RAG engine, pipeline, data loader)
được khởi tạo trong lifespan và truy cập bởi các router qua getter.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

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
    rag_engine  = RAGEngine()
    pipeline    = MathBuddyPipeline(rag_engine=rag_engine)
    data_loader = DataDirectoryLoader()
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
