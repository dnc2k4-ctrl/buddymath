"""
pipeline.py – MathBuddy Chatbot Pipeline (Groq Edition)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx

# ── Load .env nếu có (ưu tiên file .env cùng thư mục pipeline.py) ────────────
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=True)
except ImportError:
    pass  # python-dotenv chưa cài, dùng os.environ trực tiếp

from rag import RAGEngine, RetrievedChunk
from rag_router import PromptBuilder, RAGRouter, Route, RouteResult

logger = logging.getLogger(__name__)

# ─── Groq Configuration ──────────────────────────────────────────────────────
# Thứ tự ưu tiên: biến môi trường > .env > giá trị mặc định dưới đây
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY",  "")  # BẮT BUỘC set qua .env / biến môi trường, KHÔNG hard-code key vào source
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
#GROQ_MODEL    = os.environ.get("GROQ_MODEL",    "meta-llama/llama-4-scout-17b-16e-instruct") 
#GROQ_MODEL    = os.environ.get("GROQ_MODEL",    "llama-3.1-8b-instant")
GROQ_MODEL    = os.environ.get("GROQ_MODEL",    "llama-3.3-70b-versatile")
LLM_TIMEOUT    = float(os.environ.get("LLM_TIMEOUT",    "60"))
RAG_TOP_K      = int(os.environ.get("RAG_TOP_K",        "5"))
HISTORY_WINDOW = int(os.environ.get("HISTORY_WINDOW",   "10"))

# ─── Vision Model Registry ────────────────────────────────────────────────────
# Danh sách model hỗ trợ vision (image_url content).
# Cập nhật bằng env var: GROQ_VISION_MODELS="model-a,model-b"
# hoặc thêm trực tiếp vào _BUILTIN_VISION_MODELS bên dưới.
_BUILTIN_VISION_MODELS: set[str] = {
    # Groq vision-capable models (xem thêm: https://console.groq.com/docs/vision)
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llava-v1.5-7b-4096-preview",
    "llava-v1.6-34b",
    # Thêm model mới tại đây nếu cần
}

def _load_vision_models() -> set[str]:
    """Merge builtin list với GROQ_VISION_MODELS env var."""
    extra = os.environ.get("GROQ_VISION_MODELS", "")
    extra_set = {m.strip() for m in extra.split(",") if m.strip()}
    return _BUILTIN_VISION_MODELS | extra_set

VISION_MODELS = _load_vision_models()

def is_vision_model(model_name: str) -> bool:
    """
    Kiểm tra model có hỗ trợ vision không.
    So sánh exact + substring để xử lý alias/version suffix.
    Ví dụ: "llama-4-scout" vẫn match "meta-llama/llama-4-scout-17b-16e-instruct"
    """
    m = model_name.lower()
    return any(m == v.lower() or v.lower() in m or m in v.lower() for v in VISION_MODELS)

# In ra để dễ kiểm tra lúc khởi động (chỉ hiện 8 ký tự đầu + 4 cuối)
_k = GROQ_API_KEY
logger.info(f"Groq key loaded: {_k[:8]}...{_k[-4:]} (len={len(_k)})")
logger.info(f"Vision support: {'✅ YES' if is_vision_model(GROQ_MODEL) else '❌ NO (text-only)'} — model={GROQ_MODEL}")


# ─── Session Memory ──────────────────────────────────────────────────────────
class SessionMemory:
    def __init__(self, window: int = HISTORY_WINDOW):
        self.window = window
        self._store: dict[str, list[dict]] = defaultdict(list)

    def add(self, session_id: str, role: str, content: str) -> None:
        self._store[session_id].append({"role": role, "content": content})
        if len(self._store[session_id]) > self.window:
            self._store[session_id] = self._store[session_id][-self.window:]

    def get(self, session_id: str) -> list[dict]:
        return list(self._store[session_id])

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)


# ─── Groq LLM Client ─────────────────────────────────────────────────────────
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
        text, _usage = await self._complete_raw(messages, temperature, max_tokens)
        return text

    async def complete_with_usage(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int    = 1024,
    ) -> tuple[str, dict]:
        """
        Giống complete(), nhưng trả thêm usage (số token) mà Groq trả về.
        usage = {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        Dùng khi cần ghi log token thật (vd Monitor / Token Stats) thay vì ước lượng.
        Nếu Groq không trả usage (hiếm, tuỳ model), usage sẽ là {} — caller nên
        tự fallback sang ước lượng theo độ dài ký tự trong trường hợp đó.
        """
        return await self._complete_raw(messages, temperature, max_tokens)

    async def _complete_raw(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int    = 1024,
    ) -> tuple[str, dict]:
        payload = {
            "model":       self.model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            )
            if not resp.is_success:
                body = resp.text
                logger.error(f"Groq API error {resp.status_code}: {body}")
            resp.raise_for_status()
            data  = resp.json()
            text  = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            return text, usage

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
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError):
                        continue


# ─── Pipeline ────────────────────────────────────────────────────────────────
class MathBuddyPipeline:
    def __init__(
        self,
        rag_engine: RAGEngine,
        llm_client: Optional[LLMClient] = None,
        router: Optional[RAGRouter]     = None,
        memory: Optional[SessionMemory] = None,
    ):
        self.rag    = rag_engine
        self.llm    = llm_client or LLMClient()
        self.router = router or RAGRouter(llm_fallback=self._llm_route_fallback)
        self.memory = memory or SessionMemory()

    async def _llm_route_fallback(self, text: str) -> str:
        prompt = (
            "Classify the following student message into exactly one category: "
            "theory, exercise, solution, hint, chat, unknown.\n"
            "Reply with ONLY the category word.\n\n"
            f"Message: {text}"
        )
        result = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        return result.strip().lower()

    async def run(
        self,
        message: str,
        session_id: str = "default",
        topic: str | None = None,
        subject: str | None = None,
        image_base64: str | None = None,
        image_media_type: str = "image/jpeg",
    ) -> dict:
        route_result: RouteResult = await self.router.route(
            message, topic=topic, subject=subject
        )
        logger.info(
            f"[{session_id}] Route={route_result.route.value} "
            f"conf={route_result.confidence:.2f}"
        )

        chunks: list[RetrievedChunk] = []
        if route_result.route not in (Route.CHAT,):
            chunks = self.rag.search(
                query=message,
                top_k=RAG_TOP_K,
                subject=route_result.detected_subject or subject,
                topic=topic,
            )

        context_str = self.rag.get_context_string(chunks) if chunks else ""
        system_prompt = PromptBuilder.build(
            route=route_result.route,
            context=context_str,
            subject=route_result.detected_subject or subject or "",
            topic=topic or route_result.detected_topic,
        )

        history = self.memory.get(session_id)

        # Xây dựng user content với vision-aware fallback:
        # - Model hỗ trợ vision → gửi image_url + text (multipart)
        # - Model text-only     → bỏ ảnh, trả thông báo hướng dẫn nhập text
        if image_base64:
            if is_vision_model(self.llm.model):
                user_content: list[dict] | str = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_media_type};base64,{image_base64}",
                        },
                    },
                    {"type": "text", "text": message or "Hãy giải bài toán trong ảnh này."},
                ]
                logger.info(f"[{session_id}] Vision mode ✅ — model={self.llm.model}")
            else:
                user_content = (
                    "⚠️ Model hiện tại không hỗ trợ đọc ảnh.\n"
                    "Vui lòng gõ lại đề bài bằng văn bản để Buddy giải giúp nhé!\n\n"
                    + (f"Câu hỏi kèm theo: {message}" if message else "")
                )
                logger.warning(
                    f"[{session_id}] Vision fallback — model '{self.llm.model}' "
                    "không có trong VISION_MODELS. "
                    "Thêm vào _BUILTIN_VISION_MODELS hoặc env GROQ_VISION_MODELS nếu cần."
                )
        else:
            user_content = message

        messages: list[dict] = (
            [{"role": "system", "content": system_prompt}]
            + history
            + [{"role": "user", "content": user_content}]
        )

        answer = await self.llm.complete(messages)
        self.memory.add(session_id, "user", message)
        self.memory.add(session_id, "assistant", answer)

        sources = [
            {**chunk.document.to_dict(), "score": round(chunk.score, 4)}
            for chunk in chunks
        ]
        return {"answer": answer, "sources": sources, "route": route_result.route.value}

    async def stream(
        self,
        message: str,
        session_id: str = "default",
        topic: str | None = None,
        subject: str | None = None,
        image_base64: str | None = None,
        image_media_type: str = "image/jpeg",
    ) -> AsyncIterator[str]:
        route_result = await self.router.route(message, topic=topic, subject=subject)

        chunks = []
        if route_result.route not in (Route.CHAT,):
            chunks = self.rag.search(
                query=message,
                top_k=RAG_TOP_K,
                subject=route_result.detected_subject or subject,
                topic=topic,
            )

        context_str   = self.rag.get_context_string(chunks) if chunks else ""
        system_prompt = PromptBuilder.build(
            route=route_result.route,
            context=context_str,
            subject=route_result.detected_subject or subject or "",
            topic=topic or route_result.detected_topic,
        )
        history  = self.memory.get(session_id)

        # Xây dựng user content với vision-aware fallback (giống run())
        if image_base64:
            if is_vision_model(self.llm.model):
                user_content: list[dict] | str = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_media_type};base64,{image_base64}",
                        },
                    },
                    {"type": "text", "text": message or "Hãy giải bài toán trong ảnh này."},
                ]
                logger.info(f"Stream vision mode ✅ — model={self.llm.model}")
            else:
                user_content = (
                    "⚠️ Model hiện tại không hỗ trợ đọc ảnh.\n"
                    "Vui lòng gõ lại đề bài bằng văn bản để Buddy giải giúp nhé!\n\n"
                    + (f"Câu hỏi kèm theo: {message}" if message else "")
                )
                logger.warning(
                    f"Stream vision fallback — model '{self.llm.model}' "
                    "không có trong VISION_MODELS."
                )
        else:
            user_content = message

        messages = (
            [{"role": "system", "content": system_prompt}]
            + history
            + [{"role": "user", "content": user_content}]
        )

        meta = json.dumps({
            "type":    "meta",
            "route":   route_result.route.value,
            "sources": [chunk.document.to_dict() for chunk in chunks],
        })
        yield meta

        full_reply = []
        async for delta in self.llm.stream(messages):
            full_reply.append(delta)
            yield json.dumps({"type": "delta", "text": delta})

        self.memory.add(session_id, "user", message)
        self.memory.add(session_id, "assistant", "".join(full_reply))