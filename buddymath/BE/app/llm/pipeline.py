"""
pipeline.py – BuddyMath Chatbot Pipeline (Groq + RAG).
Điều phối: route intent → RAG search → build prompt → gọi LLM (có hỗ trợ vision).
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import AsyncIterator, Optional

from app.config import HISTORY_WINDOW, RAG_TOP_K
from app.llm.client import LLMClient, is_vision_model
from app.rag.engine import RAGEngine, RetrievedChunk
from app.rag.router import PromptBuilder, RAGRouter, Route, RouteResult

logger = logging.getLogger(__name__)


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


def _vision_fallback_text(message: str) -> str:
    return (
        "⚠️ Model hiện tại không hỗ trợ đọc ảnh.\n"
        "Vui lòng gõ lại đề bài bằng văn bản để Buddy giải giúp nhé!\n\n"
        + (f"Câu hỏi kèm theo: {message}" if message else "")
    )


def _build_user_content(model: str, message: str, image_base64: str | None, image_media_type: str):
    """Trả về user content: list[dict] (vision) hoặc str (text-only/no image)."""
    if not image_base64:
        return message
    if is_vision_model(model):
        return [
            {"type": "image_url",
             "image_url": {"url": f"data:{image_media_type};base64,{image_base64}"}},
            {"type": "text", "text": message or "Hãy giải bài toán trong ảnh này."},
        ]
    logger.warning(f"Vision fallback — model '{model}' không hỗ trợ vision.")
    return _vision_fallback_text(message)


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
            messages=[{"role": "user", "content": prompt}], temperature=0.0, max_tokens=10
        )
        return result.strip().lower()

    async def _prepare(self, message, topic, subject):
        """Route + RAG search + build system prompt. Trả về (system_prompt, chunks, route)."""
        route_result: RouteResult = await self.router.route(message, topic=topic, subject=subject)

        chunks: list[RetrievedChunk] = []
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
        return system_prompt, chunks, route_result

    async def run(
        self,
        message: str,
        session_id: str = "default",
        topic: str | None = None,
        subject: str | None = None,
        image_base64: str | None = None,
        image_media_type: str = "image/jpeg",
    ) -> dict:
        system_prompt, chunks, route_result = await self._prepare(message, topic, subject)
        logger.info(f"[{session_id}] Route={route_result.route.value} conf={route_result.confidence:.2f}")

        user_content = _build_user_content(self.llm.model, message, image_base64, image_media_type)
        messages = (
            [{"role": "system", "content": system_prompt}]
            + self.memory.get(session_id)
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
        system_prompt, chunks, route_result = await self._prepare(message, topic, subject)

        user_content = _build_user_content(self.llm.model, message, image_base64, image_media_type)
        messages = (
            [{"role": "system", "content": system_prompt}]
            + self.memory.get(session_id)
            + [{"role": "user", "content": user_content}]
        )

        yield json.dumps({
            "type":    "meta",
            "route":   route_result.route.value,
            "sources": [chunk.document.to_dict() for chunk in chunks],
        })

        full_reply: list[str] = []
        async for delta in self.llm.stream(messages):
            full_reply.append(delta)
            yield json.dumps({"type": "delta", "text": delta})

        self.memory.add(session_id, "user", message)
        self.memory.add(session_id, "assistant", "".join(full_reply))
