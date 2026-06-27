"""
chat.py – Router chat: /chat, /chat/stream, /chat/image và proxy /v1/messages (Groq).
"""
from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.llm.client import LLMClient, is_vision_model
from app.schemas.chat import ChatRequest, ChatResponse, GroqDirectRequest, ImageChatRequest
from app.services.runtime import get_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB


# ─── Chat thường ──────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    pipeline = get_pipeline()
    try:
        result = await pipeline.run(
            message=req.message,
            session_id=req.session_id,
            topic=req.topic,
            subject=req.subject,
        )
        return ChatResponse(
            answer=result["answer"],
            sources=result.get("sources", []),
            route=result.get("route", "general"),
            session_id=req.session_id,
            model=pipeline.llm.model,
        )
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    pipeline = get_pipeline()

    async def event_generator():
        async for chunk in pipeline.stream(
            message=req.message,
            session_id=req.session_id,
            topic=req.topic,
            subject=req.subject,
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Chat với ảnh đính kèm ────────────────────────────────────────────────────
@router.post("/chat/image", response_model=ChatResponse)
async def chat_with_image(req: ImageChatRequest):
    pipeline = get_pipeline()

    content_type = req.media_type.lower().strip()
    if content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Loại ảnh '{content_type}' không được hỗ trợ. "
                   f"Chỉ chấp nhận: {', '.join(sorted(_ALLOWED_IMAGE_TYPES))}.",
        )
    if not req.image_base64:
        raise HTTPException(status_code=400, detail="image_base64 không được rỗng.")
    try:
        raw_bytes = base64.b64decode(req.image_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="image_base64 không hợp lệ, không decode được.")
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"Ảnh quá lớn ({len(raw_bytes)//1024} KB). Giới hạn 20 MB.")

    message = req.prompt or "Hãy giải bài toán trong ảnh này từng bước."
    logger.info(f"[{req.session_id}] Nhận ảnh: {content_type}, {len(raw_bytes)//1024} KB")

    try:
        result = await pipeline.run(
            message=message,
            session_id=req.session_id,
            topic=req.topic,
            subject=req.subject,
            image_base64=req.image_base64,
            image_media_type=content_type,
        )
    except Exception as exc:
        logger.error(f"Image chat error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        route=result.get("route", "vision"),
        session_id=req.session_id,
        model=pipeline.llm.model,
    )


# ─── Proxy /v1/messages (Groq, định dạng tương thích Claude content[]) ─────────
def _normalize_content(content, model_supports_vision: bool):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    if model_supports_vision:
        blocks = []
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t in ("image_url", "text"):
                blocks.append(b)
            elif t == "document":
                data = b.get("source", {}).get("data", "")
                if data:
                    blocks.append({"type": "text", "text": data})
        return blocks or ""

    parts = []
    for b in content:
        if not isinstance(b, dict):
            parts.append(str(b))
            continue
        t = b.get("type")
        if t == "text":
            parts.append(b.get("text", ""))
        elif t == "image_url":
            parts.append("[Ảnh đính kèm – model hiện tại không hỗ trợ vision]")
        elif t == "document":
            parts.append(b.get("source", {}).get("data", ""))
    return "\n".join(filter(None, parts))


@router.post("/v1/messages")
async def groq_proxy(req: GroqDirectRequest):
    client = LLMClient()
    msgs: list[dict] = []
    if req.system:
        msgs.append({"role": "system", "content": req.system})
    msgs.extend(req.messages)

    supports_vision = is_vision_model(client.model)
    normalized_msgs = [
        {**msg, "content": _normalize_content(msg.get("content", ""), supports_vision)}
        for msg in msgs
    ]

    # Inject ảnh vào user message cuối nếu frontend gửi image_base64
    if req.image_base64:
        try:
            base64.b64decode(req.image_base64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="image_base64 không hợp lệ.")

        last_user_idx = next(
            (i for i in range(len(normalized_msgs) - 1, -1, -1)
             if normalized_msgs[i].get("role") == "user"),
            None,
        )

        if supports_vision:
            image_block = {
                "type": "image_url",
                "image_url": {"url": f"data:{req.image_media_type};base64,{req.image_base64}"},
            }
            if last_user_idx is not None:
                existing = normalized_msgs[last_user_idx]["content"]
                if isinstance(existing, str):
                    text_blocks = [{"type": "text", "text": existing}] if existing else []
                elif isinstance(existing, list):
                    text_blocks = existing
                else:
                    text_blocks = []
                normalized_msgs[last_user_idx]["content"] = [image_block, *text_blocks]
            else:
                normalized_msgs.append({
                    "role": "user",
                    "content": [image_block, {"type": "text", "text": "Hãy giải bài toán trong ảnh này."}],
                })
            logger.info(f"groq_proxy: đã inject ảnh ({req.image_media_type}) — model={client.model}")
        else:
            logger.warning(f"groq_proxy: model '{client.model}' không hỗ trợ vision — bỏ ảnh.")
            if last_user_idx is not None:
                existing_text = normalized_msgs[last_user_idx].get("content", "")
                if isinstance(existing_text, list):
                    existing_text = " ".join(
                        b.get("text", "") for b in existing_text if b.get("type") == "text"
                    )
                normalized_msgs[last_user_idx]["content"] = (
                    "⚠️ Model hiện tại không hỗ trợ đọc ảnh.\n"
                    "Vui lòng gõ lại đề bài bằng văn bản để Buddy giải giúp nhé!\n\n"
                    + (f"Câu hỏi kèm theo: {existing_text}" if existing_text else "")
                )

    try:
        reply = await client.complete(
            messages=normalized_msgs,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except Exception as exc:
        logger.error(f"Groq proxy error: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Groq error: {exc}")

    return {
        "content": [{"type": "text", "text": reply}],
        "model":   client.model,
        "role":    "assistant",
    }
