"""
chat_history.py – ORM lưu lịch sử trò chuyện với AI (theo ngày/giờ, từng câu hỏi–trả lời).

Dùng cho: học sinh xem lại lịch sử học tập + đưa vào báo cáo email cho phụ huynh
(cả cách con dùng AI ở phần "Tư duy đặt câu hỏi").
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.core.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(String, index=True, nullable=True)   # nhóm 1 phiên trò chuyện
    subject    = Column(String, default="")                  # toan | english | life_skills | prompt-playground | chat
    role       = Column(String, nullable=False)              # 'user' | 'assistant'
    content    = Column(Text, default="")                    # nội dung TEXT (KHÔNG lưu ảnh base64)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
