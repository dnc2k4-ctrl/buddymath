"""
scores.py – Router ghi nhận và truy vấn điểm số học sinh.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.score import ScoreRecord
from app.models.user import User
from app.schemas.scores import ScoreReq
from app.services.email_service import notify_parents

router = APIRouter(prefix="/scores", tags=["scores"])


@router.post("/record")
async def record_score(
    req: ScoreReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rec = ScoreRecord(
        user_id=current_user.id,
        subject=req.subject,
        topic=req.topic,
        score=req.score,
        total=req.total,
        details=req.details,
        feedback=req.feedback,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    notify_parents(current_user, rec, db)
    return {"success": True, "id": rec.id}


@router.get("/history")
async def score_history(
    subject: Optional[str] = None,
    limit: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(ScoreRecord).filter(ScoreRecord.user_id == current_user.id)
    if subject:
        q = q.filter(ScoreRecord.subject == subject)
    recs = q.order_by(ScoreRecord.created_at.desc()).limit(limit).all()
    return [
        {
            "id":         r.id,
            "subject":    r.subject,
            "topic":      r.topic,
            "score":      r.score,
            "total":      r.total,
            "pct":        round(r.score / r.total * 100) if r.total else 0,
            "feedback":   r.feedback,
            "created_at": r.created_at.isoformat(),
        }
        for r in recs
    ]


@router.get("/summary")
async def score_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=30)
    recs  = db.query(ScoreRecord).filter(
        ScoreRecord.user_id == current_user.id,
        ScoreRecord.created_at >= since,
    ).all()
    by_sub: dict[str, list] = {}
    for r in recs:
        by_sub.setdefault(r.subject, []).append(r.score / r.total * 100 if r.total else 0)
    return {
        "total_sessions": len(recs),
        "by_subject": {
            s: {"count": len(pcts), "avg_pct": round(sum(pcts) / len(pcts))}
            for s, pcts in by_sub.items()
        },
    }
