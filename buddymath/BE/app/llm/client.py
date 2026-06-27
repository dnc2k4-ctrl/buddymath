"""
client.py – Groq LLM client (OpenAI-compatible) + helper vision.

API key đọc từ env GROQ_API_KEY (app.config). Không hardcode key.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
    LLM_TIMEOUT,
    vision_models,
)

logger = logging.getLogger(__name__)

VISION_MODELS = vision_models()


def is_vision_model(model_name: str) -> bool:
    """Kiểm tra model có hỗ trợ vision không (exact + substring để xử lý alias)."""
    m = model_name.lower()
    return any(m == v.lower() or v.lower() in m or m in v.lower() for v in VISION_MODELS)


if GROQ_API_KEY:
    _k = GROQ_API_KEY
    logger.info(f"Groq key loaded: {_k[:8]}…{_k[-4:]} (len={len(_k)})")
else:
    logger.warning("GROQ_API_KEY chưa cấu hình trong .env — các tính năng chat sẽ lỗi.")
logger.info(f"Vision support: {'✅ YES' if is_vision_model(GROQ_MODEL) else '❌ NO'} — model={GROQ_MODEL}")


class LLMClient:
    def __init__(
        self,
        base_url: str  = GROQ_BASE_URL,
        api_key: str   = GROQ_API_KEY,
        model: str     = GROQ_MODEL,
        timeout: float = LLM_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model    = model
        self.timeout  = timeout
        self._headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    async def complete(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int    = 1024,
    ) -> str:
        payload = {
            "model":       self.model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", headers=self._headers, json=payload
            )
            if not resp.is_success:
                logger.error(f"Groq API error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def stream(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int    = 1024,
    ) -> AsyncIterator[str]:
        payload = {
            "model":       self.model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      True,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", headers=self._headers, json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        delta = json.loads(raw)["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError):
                        continue
