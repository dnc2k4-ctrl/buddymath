"""Pydantic schema cho ghi điểm."""
from __future__ import annotations

from pydantic import BaseModel


class ScoreReq(BaseModel):
    subject:  str
    topic:    str   = ""
    score:    float
    total:    float = 10
    details:  str   = ""
    feedback: str   = ""
