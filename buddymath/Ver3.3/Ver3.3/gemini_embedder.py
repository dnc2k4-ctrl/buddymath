"""
gemini_embedder.py – Google Gemini Embedding client for MathBuddy

Tự động dò tìm model embedding khả dụng khi khởi động.
Thứ tự thử: embedding-001 (v1beta) → embedding-001 (v1)
            → text-embedding-004 (v1beta) → text-embedding-004 (v1)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Literal

import httpx
import numpy as np

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCXLbJC65uUODqBaHx977Rqrjn6isgWvco")

# Thử theo thứ tự từ model cũ (ổn định) → mới (cần quyền cao hơn)
CANDIDATE_MODELS = [
    ("https://generativelanguage.googleapis.com/v1beta", "models/embedding-001",       768),
    ("https://generativelanguage.googleapis.com/v1",     "models/embedding-001",       768),
    ("https://generativelanguage.googleapis.com/v1beta", "models/text-embedding-004",  768),
    ("https://generativelanguage.googleapis.com/v1",     "models/text-embedding-004",  768),
]

BATCH_SIZE  = 50
RETRY_DELAY = 2.0
MAX_RETRIES = 3

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY", "SEMANTIC_SIMILARITY"]


def _probe(base: str, model: str, api_key: str) -> bool:
    """Thử embed 1 đoạn text để kiểm tra model hoạt động không."""
    url = f"{base}/{model}:batchEmbedContents?key={api_key}"
    payload = {
        "requests": [{
            "model":    model,
            "content":  {"parts": [{"text": "kiểm tra"}]},
            "taskType": "RETRIEVAL_DOCUMENT",
        }]
    }
    try:
        resp = httpx.post(url, json=payload,
                          headers={"Content-Type": "application/json"},
                          timeout=15.0)
        ok = resp.status_code == 200
        if ok:
            logger.info(f"✅ Embedding OK: {model}  [{base.split('googleapis.com/')[1]}]")
        else:
            logger.debug(f"  ✗ {model} [{base.split('googleapis.com/')[1]}] → {resp.status_code}")
        return ok
    except Exception as exc:
        logger.debug(f"  ✗ {model} → {exc}")
        return False


def _find_working_model(api_key: str) -> tuple[str, str, int]:
    logger.info("🔍 Đang dò tìm Gemini embedding model khả dụng…")
    for base, model, dim in CANDIDATE_MODELS:
        if _probe(base, model, api_key):
            return base, model, dim
    raise RuntimeError(
        "❌ Không tìm được Gemini embedding model nào hoạt động.\n"
        "Nguyên nhân có thể:\n"
        "  • API key không hợp lệ hoặc bị thu hồi\n"
        "  • Chưa bật 'Generative Language API' trong Google Cloud Console\n"
        "  • API key bị giới hạn IP/domain\n"
        "Kiểm tra tại: https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com"
    )


class GeminiEmbedder:
    """
    Wraps Gemini batchEmbedContents REST API.
    Tự động phát hiện model và URL khi khởi tạo.

    Usage
    -----
    embedder  = GeminiEmbedder()
    doc_vecs  = embedder.embed_documents(["lý thuyết 1", "lý thuyết 2"])  # (N, 768)
    query_vec = embedder.embed_query("phương trình bậc hai là gì?")        # (1, 768)
    """

    def __init__(self, api_key: str = GEMINI_API_KEY):
        self.api_key            = api_key
        self._base, self.model, self.dim = _find_working_model(api_key)

    # ── Gọi API ──────────────────────────────────────────────────────────────
    def _batch_embed(
        self,
        texts:     list[str],
        task_type: TaskType = "RETRIEVAL_DOCUMENT",
    ) -> np.ndarray:
        url = f"{self._base}/{self.model}:batchEmbedContents?key={self.api_key}"
        payload = {
            "requests": [
                {
                    "model":    self.model,
                    "content":  {"parts": [{"text": t[:8000]}]},
                    "taskType": task_type,
                }
                for t in texts
            ]
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = httpx.post(
                    url, json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=60.0,
                )
                if resp.status_code == 429:
                    wait = RETRY_DELAY * attempt
                    logger.warning(f"Rate-limited (attempt {attempt}), retry in {wait:.1f}s…")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                embeddings = resp.json()["embeddings"]
                return np.array([e["values"] for e in embeddings], dtype="float32")

            except httpx.HTTPStatusError as exc:
                logger.error(f"Gemini HTTP error: {exc.response.text[:200]}")
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(RETRY_DELAY)
            except Exception as exc:
                logger.error(f"Gemini embedding error: {exc}")
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(RETRY_DELAY)

        raise RuntimeError("Gemini embedding thất bại sau tất cả lần thử.")

    # ── Public API ────────────────────────────────────────────────────────────
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """Embed danh sách tài liệu. Trả về (N, 768) float32."""
        if not texts:
            return np.empty((0, self.dim), dtype="float32")

        results: list[np.ndarray] = []
        total = len(texts)
        for i in range(0, total, BATCH_SIZE):
            batch = texts[i: i + BATCH_SIZE]
            logger.info(
                f"GeminiEmbedder: batch {i // BATCH_SIZE + 1} "
                f"({len(batch)} texts, {i + len(batch)}/{total})"
            )
            results.append(self._batch_embed(batch, "RETRIEVAL_DOCUMENT"))
            if i + BATCH_SIZE < total:
                time.sleep(0.25)      # tránh rate limit
        return np.vstack(results)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed câu hỏi tìm kiếm. Trả về (1, 768) float32."""
        return self._batch_embed([text], "RETRIEVAL_QUERY")

    def __repr__(self) -> str:
        return (
            f"GeminiEmbedder(model={self.model!r}, "
            f"api={self._base.split('googleapis.com/')[1]!r}, "
            f"dim={self.dim})"
        )