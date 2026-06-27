"""
parent.py – Router quản lý phụ huynh: liên kết con, xem báo cáo, gửi email.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.score import ScoreRecord
from app.models.user import ParentChildLink, User
from app.schemas.auth import LinkChildReq, SendReportReq
from app.services.email_service import build_report_html, smtp_send

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parent", tags=["parent"])


def _require_parent(user: User) -> None:
    if user.role != "parent":
        raise HTTPException(403, "Chỉ tài khoản phụ huynh mới có quyền này")


def _require_link(db: Session, parent_id: str, child_id: str) -> ParentChildLink:
    link = db.query(ParentChildLink).filter(
        ParentChildLink.parent_id == parent_id,
        ParentChildLink.child_id  == child_id,
    ).first()
    if not link:
        raise HTTPException(403, "Không có quyền xem báo cáo này")
    return link


@router.post("/link-child")
async def link_child(
    req: LinkChildReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_parent(current_user)
    child = db.query(User).filter(User.email == req.child_email.lower()).first()
    if not child:
        raise HTTPException(404, "Không tìm thấy tài khoản học sinh với email này")
    if child.role != "student":
        raise HTTPException(400, "Tài khoản này không phải là học sinh")
    existing = db.query(ParentChildLink).filter(
        ParentChildLink.parent_id == current_user.id,
        ParentChildLink.child_id == child.id,
    ).first()
    if not existing:
        db.add(ParentChildLink(parent_id=current_user.id, child_id=child.id))
        db.commit()
    return {"success": True, "child": child.to_dict()}


@router.get("/children")
async def get_children(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_parent(current_user)
    links  = db.query(ParentChildLink).filter(ParentChildLink.parent_id == current_user.id).all()
    result = []
    for link in links:
        child = db.query(User).filter(User.id == link.child_id).first()
        if not child:
            continue
        since     = datetime.utcnow() - timedelta(days=7)
        week_recs = db.query(ScoreRecord).filter(
            ScoreRecord.user_id == child.id,
            ScoreRecord.created_at >= since,
        ).all()
        total_recs = db.query(ScoreRecord).filter(ScoreRecord.user_id == child.id).count()
        avg_pct = (
            round(sum(r.score / r.total * 100 for r in week_recs if r.total) / len(week_recs))
            if week_recs else None
        )
        result.append({
            **child.to_dict(),
            "total_sessions": total_recs,
            "week_sessions":  len(week_recs),
            "week_avg_pct":   avg_pct,
        })
    return result


@router.get("/reports/{child_id}")
async def child_report(
    child_id: str,
    period:   str = "week",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_parent(current_user)
    _require_link(db, current_user.id, child_id)
    child = db.query(User).filter(User.id == child_id).first()
    if not child:
        raise HTTPException(404)
    days  = 7 if period == "week" else 30
    since = datetime.utcnow() - timedelta(days=days)
    recs  = db.query(ScoreRecord).filter(
        ScoreRecord.user_id  == child_id,
        ScoreRecord.created_at >= since,
    ).order_by(ScoreRecord.created_at.desc()).all()
    by_sub: dict[str, list] = {}
    for r in recs:
        by_sub.setdefault(r.subject, []).append({
            "topic": r.topic, "score": r.score, "total": r.total,
            "pct":   round(r.score / r.total * 100) if r.total else 0,
            "feedback": r.feedback,
            "date":  r.created_at.isoformat(),
        })
    return {
        "child":          child.to_dict(),
        "period":         period,
        "total_sessions": len(recs),
        "by_subject":     by_sub,
    }


@router.post("/send-report")
async def send_report(
    req: SendReportReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_parent(current_user)
    _require_link(db, current_user.id, req.child_id)
    child = db.query(User).filter(User.id == req.child_id).first()
    days  = 7 if req.period == "week" else 30
    since = datetime.utcnow() - timedelta(days=days)
    recs  = db.query(ScoreRecord).filter(
        ScoreRecord.user_id == req.child_id,
        ScoreRecord.created_at >= since,
    ).all()
    period_label = "tuần" if req.period == "week" else "tháng"
    html = build_report_html(current_user, child, recs, req.period)
    try:
        smtp_send(current_user.email, f"📊 Báo cáo học tập {period_label} qua của {child.username}", html)
        return {"success": True, "message": f"Đã gửi báo cáo đến {current_user.email}"}
    except Exception as e:
        logger.error(f"Email error: {e}")
        raise HTTPException(500, f"Không gửi được email: {e}. Vui lòng kiểm tra cấu hình SMTP trong .env")
