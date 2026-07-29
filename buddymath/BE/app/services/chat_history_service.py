"""
chat_history_service.py – Lưu & truy vấn lịch sử trò chuyện với AI.

- save_exchange: lưu 1 lượt hỏi–đáp (fail-safe: lỗi thì bỏ qua, KHÔNG làm hỏng chat).
- history_for_user: lấy lịch sử của 1 user (mới nhất trước).
- activity_summary: tóm tắt hoạt động dùng AI (cho báo cáo email phụ huynh).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.chat_history import ChatMessage

logger = logging.getLogger(__name__)

_MAX_LEN = 4000   # cắt nội dung quá dài để tránh phình DB


def save_exchange(db: Session, user_id: str, user_text: str, assistant_text: str,
                  subject: str = "", session_id: str | None = None) -> None:
    """Lưu 1 lượt hỏi–đáp (tối đa 2 dòng: user + assistant)."""
    if not user_id:
        return
    try:
        rows = []
        if (user_text or "").strip():
            rows.append(ChatMessage(user_id=user_id, session_id=session_id, subject=subject or "",
                                    role="user", content=(user_text or "")[:_MAX_LEN]))
        if (assistant_text or "").strip():
            rows.append(ChatMessage(user_id=user_id, session_id=session_id, subject=subject or "",
                                    role="assistant", content=(assistant_text or "")[:_MAX_LEN]))
        if rows:
            db.add_all(rows)
            db.commit()
    except Exception as e:
        logger.warning(f"Lưu lịch sử chat lỗi: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def history_for_user(db: Session, user_id: str, days: int = 30, limit: int = 400,
                     subject: str | None = None) -> list[dict]:
    """Lịch sử trò chuyện của 1 user, mới nhất trước (kèm ngày/giờ để FE nhóm theo ngày)."""
    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id, ChatMessage.created_at >= since
    )
    if subject:
        q = q.filter(ChatMessage.subject == subject)
    rows = q.order_by(ChatMessage.created_at.desc()).limit(limit).all()
    return [{
        "id":         r.id,
        "role":       r.role,
        "content":    r.content,
        "subject":    r.subject,
        "session_id": r.session_id,
        "created_at": r.created_at.isoformat(),
    } for r in rows]


def activity_summary(db: Session, user_id: str, days: int = 7) -> dict:
    """Tóm tắt hoạt động dùng AI trong N ngày (cho nhận xét email phụ huynh)."""
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id,
        ChatMessage.created_at >= since,
        ChatMessage.role == "user",
    ).all()
    by_subject: dict[str, int] = {}
    active_days = set()
    for r in rows:
        by_subject[r.subject or "khác"] = by_subject.get(r.subject or "khác", 0) + 1
        active_days.add(r.created_at.date())
    return {
        "questions_asked": len(rows),
        "active_days":     len(active_days),
        "by_subject":      by_subject,
    }
