"""
report_scheduler.py – Gửi email báo cáo cho phụ huynh THEO LỊCH của gói.

Tần suất đọc từ app/plans.py (emailReportFrequency):
  • free      → None        → KHÔNG gửi theo lịch
  • standard  → "weekly"    → gửi HÀNG TUẦN (module này lo)
  • premium   → "per_lesson"→ gửi sau MỖI bài (đã lo ở email_service.notify_parents)

Chống gửi trùng: mỗi cặp phụ huynh–con lưu `last_report_at`; chỉ gửi khi tới kỳ.
Được gọi bởi: (1) vòng lặp nền trong lifespan; (2) endpoint /tasks/run-scheduled-reports (cron).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import plans
from app.models.score import ScoreRecord
from app.models.user import ParentChildLink, User
from app.services import chat_history_service
from app.services.email_service import build_report_html, smtp_configured, smtp_send

logger = logging.getLogger(__name__)

# Khoảng cách tối thiểu giữa 2 lần gửi cho mỗi tần suất (giây → timedelta).
_PERIOD_DAYS = {"weekly": 7}


def send_due_reports(db: Session) -> dict:
    """Duyệt mọi cặp phụ huynh–con, gửi báo cáo cho những cặp ĐÃ TỚI KỲ theo gói."""
    if not smtp_configured():
        return {"ok": False, "reason": "email chưa cấu hình (BREVO_API_KEY/SMTP)", "checked": 0, "sent": 0}

    now = datetime.utcnow()
    checked = sent = 0
    for link in db.query(ParentChildLink).all():
        parent = db.query(User).filter(User.id == link.parent_id).first()
        child = db.query(User).filter(User.id == link.child_id).first()
        if not (parent and child and parent.email):
            continue

        freq = plans.get_limit(child.effective_plan(), "emailReportFrequency")
        # Chỉ gửi theo lịch cho tần suất định kỳ (hiện là 'weekly'). per_lesson lo ở notify_parents,
        # None (free) = không gửi.
        if freq not in _PERIOD_DAYS:
            continue

        checked += 1
        days = _PERIOD_DAYS[freq]
        if link.last_report_at and (now - link.last_report_at) < timedelta(days=days):
            continue  # chưa tới kỳ

        try:
            since = now - timedelta(days=days)
            recs = db.query(ScoreRecord).filter(
                ScoreRecord.user_id == child.id,
                ScoreRecord.created_at >= since,
            ).all()
            ai = chat_history_service.activity_summary(db, child.id, days=days)
            period = "week" if days <= 7 else "month"
            html = build_report_html(parent, child, recs, period, ai_activity=ai)
            label = "tuần" if days <= 7 else "tháng"
            smtp_send(parent.email, f"📊 Báo cáo học tập {label} của {child.username}", html)
            link.last_report_at = now
            db.commit()
            sent += 1
            logger.info(f"[SCHEDULE] Đã gửi báo cáo {label} → {parent.email} (con {child.username}).")
        except Exception as e:
            logger.warning(f"[SCHEDULE] Lỗi gửi báo cáo cho {parent.email}: {e}")
            try:
                db.rollback()
            except Exception:
                pass

    return {"ok": True, "checked": checked, "sent": sent}
