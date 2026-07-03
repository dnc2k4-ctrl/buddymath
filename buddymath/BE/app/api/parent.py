"""
parent.py – Router quản lý phụ huynh: liên kết con, xem báo cáo, gửi email.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.llm.client import LLMClient
from app.models.score import ScoreRecord
from app.models.user import ParentChildLink, User
from app.schemas.auth import LinkChildReq, ParentAdvisorReq, SendReportReq
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
            "id":    r.id,
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


# ─── AI Cố vấn cho phụ huynh (grounded bằng điểm thật của con) ──────────────────
def _build_child_context(child: User, recs: list[ScoreRecord], period: str) -> str:
    """Tóm tắt dữ liệu học tập THẬT của con thành ngữ cảnh cho LLM."""
    period_label = "30 ngày qua" if period == "month" else "7 ngày qua"
    age = (child.grade or 5) + 6  # lớp 1 ~ 6 tuổi ở Việt Nam

    if not recs:
        return (
            f"- Tên con: {child.username}, lớp {child.grade} (khoảng {age} tuổi)\n"
            f"- Trong {period_label}: con CHƯA có bài làm nào trên hệ thống.\n"
            f"(Không có dữ liệu điểm số — hãy tư vấn dựa trên độ tuổi và động viên phụ huynh "
            f"cùng con bắt đầu học đều đặn.)"
        )

    by_subject: dict[str, list] = {}
    for r in recs:
        pct = round(r.score / r.total * 100) if r.total else 0
        by_subject.setdefault(r.subject, []).append((pct, r.topic))

    subj_avgs, lines = [], []
    all_pcts = []
    for subj, items in by_subject.items():
        pcts = [p for p, _ in items]
        all_pcts.extend(pcts)
        avg = round(sum(pcts) / len(pcts))
        subj_avgs.append((subj, avg))
        weak_topics = list(dict.fromkeys(t for p, t in items if p < 60 and t))
        line = f"  • {subj}: trung bình {avg}% ({len(items)} bài)"
        if weak_topics:
            line += f" — còn yếu ở: {', '.join(weak_topics[:3])}"
        lines.append(line)

    overall = round(sum(all_pcts) / len(all_pcts)) if all_pcts else 0
    subj_avgs.sort(key=lambda x: x[1], reverse=True)
    best = subj_avgs[0]
    weak = subj_avgs[-1]
    strength_line = f"- Môn mạnh nhất: {best[0]} ({best[1]}%)."
    if len(subj_avgs) > 1 and best[0] != weak[0]:
        strength_line += f" Môn cần hỗ trợ thêm: {weak[0]} ({weak[1]}%)."

    return (
        f"- Tên con: {child.username}, lớp {child.grade} (khoảng {age} tuổi)\n"
        f"- Dữ liệu {period_label}: {len(recs)} bài đã làm, điểm trung bình chung {overall}%.\n"
        f"- Chi tiết theo môn:\n" + "\n".join(lines) + "\n"
        f"{strength_line}"
    )


def _advisor_system_prompt(child_context: str, age: int) -> str:
    return (
        "Bạn là chuyên gia tư vấn giáo dục & tâm lý lứa tuổi của SmartBuddy, đang trò chuyện "
        "với PHỤ HUYNH (không phải học sinh) để giúp họ đồng hành cùng con.\n\n"
        "THÔNG TIN THẬT VỀ CON (từ hệ thống — hãy bám sát, KHÔNG bịa thêm điểm/môn không có):\n"
        f"{child_context}\n\n"
        "NHIỆM VỤ: Trả lời câu hỏi/băn khoăn của phụ huynh, dựa trên dữ liệu con ở trên và tâm lý "
        f"lứa tuổi khoảng {age} tuổi. Tìm ra vấn đề con đang gặp và đề xuất giải pháp, định hướng cụ thể.\n\n"
        "YÊU CẦU:\n"
        "- Trả lời bằng tiếng Việt, ấm áp và tôn trọng; xưng \"em\", gọi phụ huynh là \"anh/chị\".\n"
        "- Bám sát dữ liệu thật của con; nếu cần số liệu chưa có thì nói rõ, không bịa.\n"
        "- Lời khuyên cụ thể, khả thi, phù hợp độ tuổi và ĐÚNG vấn đề phụ huynh nêu; ưu tiên bước hành động rõ ràng.\n"
        "- Trình bày ngắn gọn: 3–6 gạch đầu dòng, **in đậm** ý chính.\n"
        "- Nếu vấn đề nghiêm trọng (sức khỏe tâm thần, bạo lực, tự làm hại...) → khuyên phụ huynh tìm chuyên gia/bác sĩ phù hợp.\n"
        "- Nếu câu hỏi ngoài phạm vi nuôi dạy & giáo dục con → nhẹ nhàng dẫn về chủ đề đồng hành cùng con."
    )


@router.post("/advisor")
async def parent_advisor(
    req: ParentAdvisorReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_parent(current_user)
    _require_link(db, current_user.id, req.child_id)
    child = db.query(User).filter(User.id == req.child_id).first()
    if not child:
        raise HTTPException(404, "Không tìm thấy tài khoản con")
    if not (req.message or "").strip():
        raise HTTPException(400, "Câu hỏi không được để trống")

    days  = 30 if req.period == "month" else 7
    since = datetime.utcnow() - timedelta(days=days)
    recs  = db.query(ScoreRecord).filter(
        ScoreRecord.user_id == child.id,
        ScoreRecord.created_at >= since,
    ).order_by(ScoreRecord.created_at.desc()).all()

    age = (child.grade or 5) + 6
    context = _build_child_context(child, recs, req.period)
    messages = [{"role": "system", "content": _advisor_system_prompt(context, age)}]

    # Lịch sử hội thoại gần nhất (tối đa 8 lượt) để giữ mạch trò chuyện
    for h in req.history[-8:]:
        role = h.get("role")
        content = (h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": req.message.strip()})

    try:
        reply = await LLMClient().complete(messages, temperature=0.6, max_tokens=800)
    except Exception as e:
        logger.error(f"Parent advisor error: {e}", exc_info=True)
        raise HTTPException(502, "Trợ lý tư vấn tạm thời chưa phản hồi được. Vui lòng thử lại sau.")

    return {"answer": reply}


class AssessRecordReq(BaseModel):
    record_id: str


def _fmt_num(x: float) -> str:
    """8.0 → '8', 7.5 → '7.5' (hiển thị gọn)."""
    return str(int(x)) if float(x).is_integer() else str(round(x, 1))


@router.post("/assess-record")
async def assess_record(
    req: AssessRecordReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Nhận xét CHI TIẾT một bài làm cho phụ huynh (đúng/sai + phần con còn yếu + gợi ý ôn).
    Vì hệ thống chỉ lưu tổng điểm (không có đáp án từng câu), AI suy luận theo chủ đề + mức điểm,
    KHÔNG bịa số liệu câu cụ thể.
    """
    _require_parent(current_user)
    rec = db.query(ScoreRecord).filter(ScoreRecord.id == req.record_id).first()
    if not rec:
        raise HTTPException(404, "Không tìm thấy bài làm này")
    _require_link(db, current_user.id, rec.user_id)   # phụ huynh phải liên kết với con này
    child = db.query(User).filter(User.id == rec.user_id).first()

    total   = rec.total or 0
    correct = rec.score or 0
    wrong   = max(0, total - correct)
    pct     = round(correct / total * 100) if total else 0
    grade   = child.grade or 5

    # Kết quả TỪNG CÂU (nếu bài có lưu details) → nhận xét bám đúng câu con sai
    questions: list[dict] = []
    try:
        parsed = json.loads(rec.details) if rec.details else []
        if isinstance(parsed, list):
            for q in parsed:
                if isinstance(q, dict):
                    questions.append({
                        "no":      q.get("no"),
                        "q":       str(q.get("q", "")),
                        "chosen":  str(q.get("chosen", "")),
                        "answer":  str(q.get("answer", "")),
                        "explain": str(q.get("explain", "")),
                        "loai":    str(q.get("loai", "")),
                        "correct": bool(q.get("correct")),
                    })
    except Exception:
        questions = []
    wrong_qs = [q for q in questions if not q["correct"]]

    common_rules = (
        "Giọng ấm áp, tôn trọng; gọi phụ huynh là \"anh/chị\", gọi học sinh là \"con\". "
        "Trình bày gạch đầu dòng ngắn, **in đậm** ý chính, không lan man, không chào hỏi dài dòng. "
        "QUAN TRỌNG: viết HOÀN TOÀN bằng tiếng Việt có dấu; TUYỆT ĐỐI không chèn chữ Hán/tiếng Trung hay ngôn ngữ khác."
    )

    if questions:
        # Có dữ liệu từng câu → phân tích CHÍNH XÁC câu sai
        if wrong_qs:
            lines = []
            for q in wrong_qs:
                extra = f" [{q['loai']}]" if q["loai"] else ""
                exp = f" (giải thích: {q['explain']})" if q["explain"] else ""
                lines.append(
                    f"  • Câu {q['no']}{extra}: {q['q']} — con trả lời \"{q['chosen']}\", "
                    f"đáp án đúng \"{q['answer']}\"{exp}"
                )
            detail_block = "CÁC CÂU CON LÀM SAI (dữ liệu thật):\n" + "\n".join(lines)
        else:
            detail_block = "Con làm ĐÚNG toàn bộ các câu."
        system = (
            "Bạn là chuyên gia phân tích học tập của SmartBuddy, viết NHẬN XÉT CHI TIẾT một bài làm cho PHỤ HUYNH. "
            + common_rules + "\n"
            f"Bài: môn {rec.subject}, chủ đề \"{rec.topic or 'tổng hợp'}\", lớp {grade}, "
            f"đúng {_fmt_num(correct)}/{_fmt_num(total)} câu ({pct}%).\n"
            f"{detail_block}\n\n"
            "Bám CHÍNH XÁC vào các câu con làm sai ở trên (KHÔNG bịa câu/kiến thức không có). Viết nhận xét gồm:\n"
            "1. **Đánh giá chung**: 1 câu về mức độ con nắm bài.\n"
            "2. **Con sai ở đâu & vì sao**: với từng câu sai, chỉ rõ con sai ở phần kiến thức/kỹ năng nào và vì sao dễ nhầm.\n"
            "3. **Gợi ý ôn ở nhà**: 2–3 việc cụ thể, khả thi, đúng phần con còn yếu.\n"
            "Nếu con đúng hết: khen ngợi và gợi ý bài nâng cao hơn."
        )
        user_msg = f"Viết nhận xét chi tiết cho bài {rec.subject} — {rec.topic or 'tổng hợp'}."
    else:
        # Không có dữ liệu từng câu (bài cũ) → suy luận theo chủ đề + mức điểm
        system = (
            "Bạn là chuyên gia phân tích học tập của SmartBuddy, viết NHẬN XÉT CHI TIẾT một bài làm cho PHỤ HUYNH. "
            + common_rules + "\n"
            f"Bài: môn {rec.subject}, chủ đề \"{rec.topic or 'tổng hợp'}\", lớp {grade}, "
            f"đúng {_fmt_num(correct)}/{_fmt_num(total)} câu ({pct}%).\n"
            "LƯU Ý: bài này chỉ có tổng điểm, KHÔNG có đáp án từng câu — hãy SUY LUẬN hợp lý theo chủ đề và mức điểm, "
            "TUYỆT ĐỐI không bịa nội dung câu cụ thể.\n\n"
            "Viết nhận xét gồm:\n"
            "1. **Đánh giá chung**: mức độ con nắm chủ đề.\n"
            "2. **Có thể con chưa vững**: 2–3 kỹ năng/phần kiến thức trong chủ đề mà mức điểm này gợi ý con còn yếu.\n"
            "3. **Gợi ý ôn ở nhà**: 2–3 việc cụ thể, khả thi, hợp lứa tuổi."
        )
        user_msg = (
            f"Viết nhận xét chi tiết cho bài {rec.subject} — {rec.topic or 'tổng hợp'}, "
            f"đúng {_fmt_num(correct)}/{_fmt_num(total)} câu."
        )

    try:
        reply = await LLMClient().complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            temperature=0.5, max_tokens=650,
        )
    except Exception as e:
        logger.error(f"assess_record error: {e}", exc_info=True)
        raise HTTPException(502, "Chưa tạo được nhận xét lúc này. Anh/chị thử lại sau nhé.")

    return {
        "assessment": reply,
        "correct": _fmt_num(correct), "wrong": _fmt_num(wrong),
        "total": _fmt_num(total), "pct": pct,
        "subject": rec.subject, "topic": rec.topic,
        "questions": questions,      # rỗng nếu bài cũ chưa có dữ liệu từng câu
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
