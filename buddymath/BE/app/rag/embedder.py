"""
embedder.py – Jina AI Embedder cho BuddyMath.

API key đọc từ biến môi trường JINA_API_KEY (xem app.config). Dim được
auto-detect từ phản hồi API ngay khi khởi tạo.
Docs: https://jina.ai/embeddings/
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import requests

from app.config import JINA_API_KEY, JINA_MODEL, JINA_URL

logger = logging.getLogger(__name__)

DEFAULT_DIM     = 1024
BATCH_SIZE      = 64
REQUEST_TIMEOUT = 60


class JinaEmbedder:
    """
    Embedder dùng Jina AI REST API. Tương thích Embedder protocol:
        .dim                  -> int
        .embed_documents(...) -> np.ndarray  shape (N, dim)
        .embed_query(...)     -> np.ndarray  shape (1, dim)
    """

    dim: int = DEFAULT_DIM

    def __init__(
        self,
        api_key: str    = JINA_API_KEY,
        model: str      = JINA_MODEL,
        batch_size: int = BATCH_SIZE,
    ):
        if not api_key:
            raise RuntimeError("JINA_API_KEY chưa được cấu hình trong .env")
        self.api_key    = api_key
        self.model      = model
        self.batch_size = batch_size
        self._headers   = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        self._verify_connection()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _verify_connection(self) -> None:
        logger.info(f"🔍 Kiểm tra kết nối Jina AI ({self.model})…")
        try:
            result = self._call_api(["test connection"], task="retrieval.passage")
            actual_dim = result.shape[1]
            if actual_dim != self.dim:
                logger.info(f"Auto-detect dim: {self.dim} → {actual_dim}")
                self.dim = actual_dim
            logger.info(f"✅ Jina AI embedder sẵn sàng (dim={self.dim})")
        except Exception as exc:
            raise RuntimeError(f"❌ Jina AI embedder lỗi kết nối: {exc}") from exc

    def _call_api(self, texts: list[str], task: str = "retrieval.passage") -> np.ndarray:
        payload: dict[str, Any] = {
            "model":      self.model,
            "task":       task,
            "normalized": True,
            "input":      texts,
        }
        resp = requests.post(JINA_URL, headers=self._headers, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            raise RuntimeError(f"Jina API trả về {resp.status_code}: {resp.text[:300]}")
        data  = resp.json()
        items = sorted(data["data"], key=lambda x: x["index"])
        return np.array([item["embedding"] for item in items], dtype="float32")

    def _batch_embed(self, texts: list[str], task: str) -> np.ndarray:
        all_vecs: list[np.ndarray] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            all_vecs.append(self._call_api(batch, task=task))
            logger.debug(f"  Embedded batch [{start}:{start + len(batch)}]")
        return np.vstack(all_vecs) if all_vecs else np.empty((0, self.dim), dtype="float32")

    # ── Public API (Embedder Protocol) ────────────────────────────────────────
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype="float32")
        logger.info(f"Embedding {len(texts)} documents qua Jina AI…")
        return self._batch_embed(texts, task="retrieval.passage")

    def embed_query(self, text: str) -> np.ndarray:
        return self._call_api([text], task="retrieval.query")

    def __repr__(self) -> str:
        return f"JinaEmbedder(model={self.model!r}, dim={self.dim})"
