"""
client.py – LLM client (OpenAI-compatible) + TỰ ĐỘNG dự phòng Groq.

Endpoint & key đọc từ app.config (ACTIVE_* = provider đang dùng, vd Gemini).
Nếu provider chính (Gemini) lỗi/hết quota/timeout → tự chuyển sang Groq để app
KHÔNG BAO GIỜ đứng máy. Groq lỗi thì mới báo lỗi thật.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.config import (
    ACTIVE_API_KEY,
    ACTIVE_BASE_URL,
    ACTIVE_TEXT_MODEL,
    ACTIVE_VISION_MODEL,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_TEXT_MODEL,
    GROQ_VISION_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT,
    vision_models,
)

logger = logging.getLogger(__name__)

VISION_MODELS = vision_models()

# Bật dự phòng khi đang dùng provider KHÁC Groq (vd Gemini) mà vẫn có sẵn key Groq.
_FALLBACK_ON = LLM_PROVIDER != "groq" and bool(GROQ_API_KEY)


def is_vision_model(model_name: str) -> bool:
    """Kiểm tra model có hỗ trợ vision không (exact + substring để xử lý alias)."""
    m = model_name.lower()
    return any(m == v.lower() or v.lower() in m or m in v.lower() for v in VISION_MODELS)


if ACTIVE_API_KEY:
    _k = ACTIVE_API_KEY
    logger.info(f"LLM key loaded: {_k[:8]}…{_k[-4:]} (len={len(_k)})")
else:
    logger.warning("Chưa cấu hình API key LLM (GROQ_API_KEY / GEMINI_API_KEY) — chat sẽ lỗi.")
logger.info(
    f"Model TEXT={ACTIVE_TEXT_MODEL} | VISION={ACTIVE_VISION_MODEL} "
    f"(vision ok: {'✅' if is_vision_model(ACTIVE_VISION_MODEL) else '❌'}) "
    f"| dự phòng Groq: {'✅ bật' if _FALLBACK_ON else '— tắt'}"
)


class LLMClient:
    def __init__(
        self,
        base_url: str  = ACTIVE_BASE_URL,
        api_key: str   = ACTIVE_API_KEY,
        model: str     = ACTIVE_TEXT_MODEL,
        timeout: float = LLM_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model    = model
        self.timeout  = timeout
        self._headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        # Dự phòng Groq — chỉ gắn khi client này đang dùng provider ACTIVE (vd Gemini).
        self._fallback = None
        if _FALLBACK_ON and self.base_url == ACTIVE_BASE_URL.rstrip("/"):
            self._fallback = {
                "base_url": GROQ_BASE_URL.rstrip("/"),
                # Dự phòng dùng model TEXT Groq ổn định (vd llama-3.3-70b) cho mọi trường hợp.
                "model": GROQ_TEXT_MODEL,
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                },
            }

    # ── Non-stream ────────────────────────────────────────────────────────────
    async def complete(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int    = 1024,
    ) -> str:
        try:
            return await self._complete_once(
                self.base_url, self._headers, self.model, messages, temperature, max_tokens
            )
        except Exception as e:
            if not self._fallback:
                raise
            logger.warning(
                f"⚠️ LLM chính lỗi ({type(e).__name__}: {str(e)[:120]}) — "
                f"tự chuyển DỰ PHÒNG Groq (model={self._fallback['model']})."
            )
            return await self._complete_once(
                self._fallback["base_url"], self._fallback["headers"],
                self._fallback["model"], messages, temperature, max_tokens,
            )

    async def _complete_once(self, base_url, headers, model, messages, temperature, max_tokens) -> str:
        payload = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            if not resp.is_success:
                logger.error(f"LLM API error {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            data = resp.json()
            try:
                content = data["choices"][0]["message"].get("content")
            except (KeyError, IndexError, TypeError):
                content = None
            if not content:                       # rỗng/null → coi như lỗi để kích hoạt dự phòng
                fr = (data.get("choices") or [{}])[0].get("finish_reason")
                raise RuntimeError(f"LLM trả về nội dung rỗng (finish_reason={fr}).")
            return content

    # ── Stream ────────────────────────────────────────────────────────────────
    async def stream(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int    = 1024,
    ) -> AsyncIterator[str]:
        yielded = False
        try:
            async for chunk in self._stream_once(
                self.base_url, self._headers, self.model, messages, temperature, max_tokens
            ):
                yielded = True
                yield chunk
        except Exception as e:
            # Chỉ dự phòng nếu CHƯA phát ra chữ nào (tránh lặp nội dung).
            if not self._fallback or yielded:
                raise
            logger.warning(
                f"⚠️ LLM chính lỗi khi stream ({type(e).__name__}) — tự chuyển DỰ PHÒNG Groq."
            )
            async for chunk in self._stream_once(
                self._fallback["base_url"], self._fallback["headers"],
                self._fallback["model"], messages, temperature, max_tokens,
            ):
                yield chunk

    async def _stream_once(self, base_url, headers, model, messages, temperature, max_tokens):
        payload = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      True,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{base_url}/chat/completions", headers=headers, json=payload
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
