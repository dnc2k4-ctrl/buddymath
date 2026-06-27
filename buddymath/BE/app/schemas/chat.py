"""Pydantic schemas cho chat, chat ảnh và proxy LLM."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message:    str
    session_id: str           = "default"
    topic:      Optional[str] = None
    subject:    Optional[str] = None
    stream:     bool          = False


class ChatResponse(BaseModel):
    answer:     str
    sources:    list[dict] = []
    route:      str        = "general"
    session_id: str
    model:      str        = ""


class ImageChatRequest(BaseModel):
    image_base64: str                          # chuỗi base64 của ảnh
    media_type:   str           = "image/jpeg" # MIME type, vd "image/png"
    prompt:       str           = ""           # câu hỏi kèm ảnh
    session_id:   str           = "buddy-main"
    topic:        Optional[str] = None
    subject:      Optional[str] = None


class GroqDirectRequest(BaseModel):
    messages:         list[dict]
    system:           Optional[str] = None
    model:            Optional[str] = None
    max_tokens:       int           = 1000
    temperature:      float         = 0.5
    image_base64:     Optional[str] = None
    image_media_type: str           = "image/jpeg"
