"""Pydantic schemas cho ingest, synthesis và classroom."""
from __future__ import annotations

from pydantic import BaseModel


class IngestRequest(BaseModel):
    file_path: str
    subject:   str
    topic:     str
    metadata:  dict = {}


class IngestResponse(BaseModel):
    status:         str
    chunks_created: int
    message:        str


class SynthesisRequest(BaseModel):
    subject: str
    topic:   str
    force:   bool = False   # True → bỏ cache, tổng hợp lại


class ClassroomLessonRequest(BaseModel):
    subject:    str
    topic:      str
    lesson:     str               # tên file (vd: "Bai_1_To_hop.pdf")
    message:    str = ""          # câu hỏi của học sinh; rỗng = mở đầu bài học
    session_id: str = "default"
    history:    list[dict] = []   # [{"role": "...", "content": "..."}]
