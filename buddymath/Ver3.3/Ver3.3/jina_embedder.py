"""
jina_embedder.py – Jina AI Embedder for MathBuddy
Thay thế GeminiEmbedder bằng Jina AI Embeddings API (free tier).

Model: jina-embeddings-v5-text-small
Dim:   512
Docs:  https://jina.ai/embeddings/
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import requests

logger = logging.getLogger(__name__)

# ── Cấu hình ──────────────────────────────────────────────────────────────────
JINA_API_KEY   = os.environ.get(
    "JINA_API_KEY",
    "jina_90073953640b43d6a5f576f32f664360DUlSFSAuJQDQ7p8Ks_z_NG40Ur95",
)
JINA_URL       = "https://api.jina.ai/v1/embeddings"
JINA_MODEL     = "jina-embeddings-v5-text-small"
EMBED_DIM      = 1024   # jina-embeddings-v5-text-small output dim
BATCH_SIZE     = 64    # max items per request (free tier an toàn)
REQUEST_TIMEOUT = 60   # seconds


class JinaEmbedder:
    """
    Embedder dùng Jina AI REST API.

    Tương thích giao diện Embedder protocol của rag.py:
        .dim                  -> int
        .embed_documents(...) -> np.ndarray  shape (N, dim)
        .embed_query(...)     -> np.ndarray  shape (1, dim)
    """

    dim: int = EMBED_DIM

    def __init__(
        self,
        api_key: str  = JINA_API_KEY,
        model: str    = JINA_MODEL,
        batch_size: int = BATCH_SIZE,
    ):
        self.api_key    = api_key
        self.model      = model
        self.batch_size = batch_size
        self._headers   = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # Thử kết nối khi khởi tạo
        self._verify_connection()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _verify_connection(self) -> None:
        """Gọi thử 1 item, auto-detect dim thực tế từ API."""
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
        """
        Gọi Jina API, trả về ndarray float32 shape (len(texts), dim).
        task: "retrieval.passage" cho documents, "retrieval.query" cho queries.
        """
        payload: dict[str, Any] = {
            "model":      self.model,
            "task":       task,
            "normalized": True,   # API trả về vector đã L2-normalize
            "input":      texts,
        }
        resp = requests.post(
            JINA_URL,
            headers=self._headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Jina API trả về {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        # data["data"] là list[{"index": int, "embedding": list[float], ...}]
        items = sorted(data["data"], key=lambda x: x["index"])
        vectors = np.array([item["embedding"] for item in items], dtype="float32")
        return vectors

    def _batch_embed(self, texts: list[str], task: str) -> np.ndarray:
        """Chia thành batches để tránh vượt giới hạn API."""
        all_vecs: list[np.ndarray] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vecs  = self._call_api(batch, task=task)
            all_vecs.append(vecs)
            logger.debug(f"  Embedded batch [{start}:{start+len(batch)}]")
        return np.vstack(all_vecs) if all_vecs else np.empty((0, self.dim), dtype="float32")

    # ── Public API (Embedder Protocol) ────────────────────────────────────────
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """
        Embed danh sách documents (passages).
        Trả về ndarray float32 shape (N, 512), đã normalize.
        """
        if not texts:
            return np.empty((0, self.dim), dtype="float32")
        logger.info(f"Embedding {len(texts)} documents qua Jina AI…")
        return self._batch_embed(texts, task="retrieval.passage")

    def embed_query(self, text: str) -> np.ndarray:
        """
        Embed một query string.
        Trả về ndarray float32 shape (1, 512), đã normalize.
        """
        return self._call_api([text], task="retrieval.query")

    def __repr__(self) -> str:
        return f"JinaEmbedder(model={self.model!r}, dim={self.dim})"
