"""
engine.py – RAG Engine cho BuddyMath.

  • Embedder inject vào (mặc định: JinaEmbedder, dim auto-detect)
  • Hỗ trợ brute-force cosine search khi FAISS không có
  • get_all_chunks() cho synthesis endpoint
  • Index/metadata lưu trong data/ (cấu hình ở app.config)
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from app.config import INDEX_PATH, META_PATH

logger = logging.getLogger(__name__)

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False
    logger.warning("faiss-cpu không có – dùng brute-force cosine search.")


# ─── Embedder Protocol ───────────────────────────────────────────────────────
class Embedder(Protocol):
    dim: int
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def _default_embedder() -> Embedder:
    """Tạo JinaEmbedder; fallback random vectors nếu lỗi (chỉ để dev)."""
    try:
        from app.rag.embedder import JinaEmbedder
        emb = JinaEmbedder()
        logger.info(f"Dùng embedder: {emb}")
        return emb
    except Exception as exc:
        logger.warning(f"Không khởi tạo được JinaEmbedder: {exc}. Dùng fallback random.")

        class _FallbackEmbedder:
            dim = 1024
            def embed_documents(self, texts):
                logger.warning("FallbackEmbedder: random vectors – KHÔNG dùng cho production!")
                return np.random.rand(len(texts), self.dim).astype("float32")
            def embed_query(self, text):
                return np.random.rand(1, self.dim).astype("float32")

        return _FallbackEmbedder()


# ─── Data Classes ────────────────────────────────────────────────────────────
@dataclass
class Document:
    """Một chunk nội dung đã sẵn sàng để embed và lưu trữ."""
    content: str
    subject: str
    topic: str
    doc_type: str = "theory"         # "theory" | "exercise" | "solution"
    source_file: str = ""
    page: int = 0
    chunk_id: str = ""
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "content":     self.content,
            "subject":     self.subject,
            "topic":       self.topic,
            "doc_type":    self.doc_type,
            "source_file": self.source_file,
            "page":        self.page,
            "chunk_id":    self.chunk_id,
            **self.extra_metadata,
        }


@dataclass
class RetrievedChunk:
    """Chunk trả về từ similarity search kèm điểm số."""
    document: Document
    score: float


# ─── RAG Engine ──────────────────────────────────────────────────────────────
class RAGEngine:
    """Quản lý embedding model và vector index cho BuddyMath."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        index_path: Path = INDEX_PATH,
        meta_path: Path  = META_PATH,
    ):
        self.embedder      = embedder or _default_embedder()
        self.embedding_dim = self.embedder.dim
        self.index_path    = index_path
        self.meta_path     = meta_path

        self._documents: list[Document] = []
        self._raw_vectors: np.ndarray | None = None   # fallback khi không có FAISS

        self._index = self._load_or_create_index()
        self._load_metadata()

    # ── Index ────────────────────────────────────────────────────────────────
    def _load_or_create_index(self):
        if not _FAISS_AVAILABLE:
            return None
        if self.index_path.exists():
            try:
                idx = faiss.read_index(str(self.index_path))
                if idx.d != self.embedding_dim:
                    logger.warning(
                        f"FAISS index dim={idx.d} ≠ embedder dim={self.embedding_dim}. Tạo index mới."
                    )
                    return faiss.IndexFlatIP(self.embedding_dim)
                logger.info(f"Tải FAISS index từ {self.index_path}")
                return idx
            except Exception as exc:
                logger.warning(f"Không tải được FAISS index: {exc}. Tạo mới.")
        logger.info("Tạo FAISS IndexFlatIP mới (inner product = cosine sau normalize).")
        return faiss.IndexFlatIP(self.embedding_dim)

    def _save_index(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        if _FAISS_AVAILABLE and self._index is not None:
            faiss.write_index(self._index, str(self.index_path))
        with open(self.meta_path, "wb") as f:
            pickle.dump(self._documents, f)
        logger.info(f"Đã lưu index ({len(self._documents)} documents).")

    def _load_metadata(self) -> None:
        if self.meta_path.exists():
            try:
                with open(self.meta_path, "rb") as f:
                    self._documents = pickle.load(f)
                logger.info(f"Tải {len(self._documents)} document entries.")
            except Exception as exc:
                logger.warning(f"Không tải được metadata: {exc}")

    # ── Embedding ────────────────────────────────────────────────────────────
    @staticmethod
    def _normalize(vecs: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return vecs / norms

    def _embed_docs(self, texts: list[str]) -> np.ndarray:
        return self._normalize(self.embedder.embed_documents(texts))

    def _embed_query(self, text: str) -> np.ndarray:
        return self._normalize(self.embedder.embed_query(text))

    # ── Public API ───────────────────────────────────────────────────────────
    def add_documents(self, documents: list[Document]) -> None:
        if not documents:
            return

        vectors = self._embed_docs([doc.content for doc in documents])

        if _FAISS_AVAILABLE and self._index is not None:
            self._index.add(vectors)
        else:
            self._raw_vectors = (
                vectors if self._raw_vectors is None
                else np.vstack([self._raw_vectors, vectors])
            )

        self._documents.extend(documents)
        self._save_index()
        logger.info(f"Thêm {len(documents)} docs. Tổng: {len(self._documents)}.")

    def search(
        self,
        query: str,
        top_k: int = 5,
        subject: str | None = None,
        topic: str | None   = None,
        doc_type: str | None = None,
    ) -> list[RetrievedChunk]:
        if not self._documents:
            return []

        query_vec = self._embed_query(query)   # (1, D)
        over_k    = min(top_k * 10, len(self._documents))

        if _FAISS_AVAILABLE and self._index is not None:
            scores, indices = self._index.search(query_vec, over_k)
            candidates = [
                RetrievedChunk(document=self._documents[i], score=float(scores[0][j]))
                for j, i in enumerate(indices[0])
                if 0 <= i < len(self._documents)
            ]
        elif self._raw_vectors is not None:
            sims = (self._raw_vectors @ query_vec.T).squeeze()
            if sims.ndim == 0:
                sims = sims.reshape(1)
            top_idx = np.argsort(sims)[::-1][:over_k]
            candidates = [
                RetrievedChunk(document=self._documents[i], score=float(sims[i]))
                for i in top_idx
            ]
        else:
            return []

        def passes(c: RetrievedChunk) -> bool:
            d = c.document
            if subject  and d.subject.lower()  != subject.lower():  return False
            if topic    and d.topic.lower()    != topic.lower():    return False
            if doc_type and d.doc_type.lower() != doc_type.lower(): return False
            return True

        return [c for c in candidates if passes(c)][:top_k]

    def get_all_chunks(
        self,
        subject: str,
        topic: str,
        doc_type: str | None = None,
    ) -> list[Document]:
        return [
            doc for doc in self._documents
            if doc.subject.lower() == subject.lower()
            and doc.topic.lower()  == topic.lower()
            and (doc_type is None or doc.doc_type.lower() == doc_type.lower())
        ]

    def get_context_string(self, chunks: list[RetrievedChunk]) -> str:
        parts = []
        for i, chunk in enumerate(chunks, 1):
            doc = chunk.document
            parts.append(
                f"[Nguồn {i} | {doc.subject} > {doc.topic} | {doc.doc_type}]\n{doc.content}\n"
            )
        return "\n---\n".join(parts)

    # ── Catalog helpers ──────────────────────────────────────────────────────
    def list_subjects(self) -> list[str]:
        return sorted({doc.subject for doc in self._documents})

    def list_topics(self, subject: str) -> list[str]:
        return sorted(
            {doc.topic for doc in self._documents if doc.subject.lower() == subject.lower()}
        )

    def get_topic_content(self, subject: str, topic: str) -> dict:
        theory = [
            doc for doc in self._documents
            if doc.subject.lower() == subject.lower()
            and doc.topic.lower()  == topic.lower()
            and doc.doc_type == "theory"
        ]
        exercises = [
            doc for doc in self._documents
            if doc.subject.lower() == subject.lower()
            and doc.topic.lower()  == topic.lower()
            and doc.doc_type in ("exercise", "solution")
        ]
        if not theory and not exercises:
            return {}
        return {
            "subject":   subject,
            "topic":     topic,
            "theory":    [d.to_dict() for d in theory],
            "exercises": [d.to_dict() for d in exercises],
        }

    def __repr__(self) -> str:
        return (
            f"RAGEngine(embedder={self.embedder!r}, "
            f"docs={len(self._documents)}, faiss={_FAISS_AVAILABLE})"
        )
