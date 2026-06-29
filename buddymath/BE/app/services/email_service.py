"""
email_service.py – Gửi email báo cáo cho phụ huynh (SMTP) + template HTML.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.config import (
    FROM_EMAIL,
    PUBLIC_BASE_URL,
    SMTP_HOST,
    SMTP_PASS,
    SMTP_PORT,
    SMTP_USER,
)
from app.models.score import ScoreRecord
from app.models.user import ParentChildLink, User

logger = logging.getLogger(__name__)


def smtp_send(to: str, subject: str, html: str) -> None:
    if not SMTP_USER:
        raise ValueError("SMTP chưa cấu hình. Thêm SMTP_USER + SMTP_PASS vào file .env")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = FROM_EMAIL
    msg["To"]      = to
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(FROM_EMAIL, to, msg.as_string())


def notify_parents(student: User, rec: ScoreRecord, db: Session) -> None:
    """Gửi email thông báo điểm tới tất cả phụ huynh đã liên kết."""
    if not SMTP_USER:
        return
    links = db.query(ParentChildLink).filter(ParentChildLink.child_id == student.id).all()
    for link in links:
        parent = db.query(User).filter(User.id == link.parent_id).first()
        if parent and parent.email:
            try:
                _send_score_email(parent.email, parent.username, student, rec)
            except Exception as e:
                logger.warning(f"Failed to email parent {parent.email}: {e}")


def _send_score_email(to: str, parent_name: str, student: User, rec: ScoreRecord) -> None:
    pct   = round(rec.score / rec.total * 100) if rec.total else 0
    emoji = "🏆" if pct >= 80 else "👍" if pct >= 60 else "📚"
    color = "#2ED573" if pct >= 80 else "#FF6B35" if pct >= 60 else "#FF4757"
    msg_text = (
        "Tuyệt vời! Em học rất giỏi, hãy tiếp tục phát huy nhé!" if pct >= 80
        else "Khá tốt! Cố gắng thêm một chút là hoàn hảo rồi!" if pct >= 60
        else "Chưa sao, lần sau cố gắng hơn nhé! SmartBuddy luôn ở đây hỗ trợ em!"
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;border-radius:16px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.12);">
      <div style="background:linear-gradient(135deg,#2EC4A0,#1E90FF);padding:24px;text-align:center;">
        <div style="font-size:48px;">{emoji}</div>
        <h2 style="color:white;margin:8px 0 0;">Kết quả bài làm mới!</h2>
        <p style="color:rgba(255,255,255,0.85);margin:4px 0 0;">SmartBuddy · Học thông minh, Tiến vững vàng</p>
      </div>
      <div style="background:white;padding:24px;">
        <p>Kính gửi Phụ huynh <strong>{parent_name}</strong>,</p>
        <p><strong>{student.username}</strong> (Lớp {student.grade}) vừa hoàn thành:</p>
        <div style="background:#f8f9ff;border-radius:14px;padding:16px;margin:16px 0;text-align:center;">
          <div style="font-size:14px;color:#666;margin-bottom:8px;">📚 {rec.subject} · {rec.topic}</div>
          <div style="font-size:52px;font-weight:900;color:{color};margin:8px 0;">{pct}%</div>
          <div style="font-size:14px;color:#666;">{rec.score:.0f} / {rec.total:.0f} câu đúng</div>
        </div>
        <div style="background:#e8f5e9;border-radius:12px;padding:14px;border-left:4px solid #2ED573;">
          <strong>💬 SmartBuddy nhận xét:</strong><br>
          <span style="color:#444;">{rec.feedback or msg_text}</span>
        </div>
        <p style="margin-top:16px;color:#888;font-size:12px;">
          Email này được gửi tự động từ hệ thống SmartBuddy. Đăng nhập tại
          <a href="{PUBLIC_BASE_URL}/parent-portal">Cổng Phụ Huynh</a> để xem chi tiết.
        </p>
      </div>
    </div>"""
    smtp_send(to, f"{emoji} {student.username} vừa làm xong bài {rec.subject} — {pct}%", html)


def _assessment_text(avg: float | None, by_sub: dict[str, list[ScoreRecord]], total: int) -> tuple[str, str]:
    """Sinh nhận xét tự động về con dựa trên điểm số. Trả về (tiêu đề, nội dung)."""
    if not total or avg is None:
        return ("🌱 Cùng bắt đầu nào!",
                "Con chưa có bài làm nào trong kỳ này. Hãy khích lệ con học cùng SmartBuddy "
                "mỗi ngày 15–20 phút để tạo thói quen tốt nhé!")
    # Môn mạnh nhất / yếu nhất
    subj_avg = sorted(
        ((s, sum(r.score / r.total * 100 for r in rs if r.total) / len(rs)) for s, rs in by_sub.items()),
        key=lambda x: x[1], reverse=True,
    )
    best, weak = subj_avg[0], subj_avg[-1]
    extra = ""
    if len(subj_avg) > 1 and best[0] != weak[0]:
        extra = f" Con mạnh nhất ở <b>{best[0]}</b> ({best[1]:.0f}%) và nên ôn thêm <b>{weak[0]}</b> ({weak[1]:.0f}%)."
    if avg >= 80:
        return ("🏆 Con đang học rất tốt!",
                f"Con duy trì phong độ xuất sắc với điểm trung bình <b>{avg:.0f}%</b>. "
                f"Hãy tiếp tục khen ngợi và có thể cho con thử các bài nâng cao hơn.{extra}")
    if avg >= 60:
        return ("👍 Con đang tiến bộ ổn định",
                f"Điểm trung bình <b>{avg:.0f}%</b> cho thấy con nắm bài khá tốt. "
                f"Cố gắng đều đặn thêm chút nữa là con sẽ bứt phá.{extra}")
    return ("💪 Con cần được đồng hành thêm",
            f"Điểm trung bình <b>{avg:.0f}%</b>. Đây là lúc con cần cha mẹ động viên — "
            f"hãy cùng con ôn lại phần còn yếu, chia nhỏ bài học và tránh tạo áp lực.{extra}")


def build_report_html(current_user: User, child: User, recs: list[ScoreRecord], period: str) -> str:
    period_label = "tuần" if period == "week" else "tháng"
    by_sub: dict[str, list[ScoreRecord]] = {}
    for r in recs:
        by_sub.setdefault(r.subject, []).append(r)

    all_pcts = [r.score / r.total * 100 for r in recs if r.total]
    overall_avg = sum(all_pcts) / len(all_pcts) if all_pcts else None

    rows = ""
    for subj, srecs in by_sub.items():
        avg = sum(r.score / r.total * 100 for r in srecs if r.total) / len(srecs)
        em  = "🏆" if avg >= 80 else "👍" if avg >= 60 else "📚"
        clr = "#2ED573" if avg >= 80 else "#FF6B35" if avg >= 60 else "#FF4757"
        rows += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid #eee;">{em} {subj}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #eee;text-align:center;">{len(srecs)}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #eee;text-align:center;font-weight:900;color:{clr};">{avg:.0f}%</td>
        </tr>"""

    # Chi tiết từng bài gần đây (kèm nhận xét nếu có)
    detail = ""
    for subj, srecs in by_sub.items():
        items = ""
        for r in sorted(srecs, key=lambda x: x.created_at, reverse=True)[:5]:
            pct = round(r.score / r.total * 100) if r.total else 0
            clr = "#2ED573" if pct >= 80 else "#FF6B35" if pct >= 60 else "#FF4757"
            fb  = f'<div style="font-size:12px;color:#888;margin-top:2px;">💬 {r.feedback}</div>' if r.feedback else ""
            items += f"""
            <div style="padding:8px 0;border-bottom:1px solid #f3f3f3;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:13px;color:#444;">📝 {r.topic or 'Bài học'}</span>
                <span style="font-size:13px;font-weight:900;color:{clr};">{pct}%</span>
              </div>{fb}
            </div>"""
        detail += f"""
        <div style="background:#f8fffc;border-radius:12px;padding:12px 16px;margin-top:12px;border:1px solid #e6f4ef;">
          <div style="font-weight:800;color:#1A2340;margin-bottom:4px;">{subj}</div>{items}
        </div>"""

    assess_title, assess_body = _assessment_text(overall_avg, by_sub, len(recs))
    avg_display = f"{overall_avg:.0f}%" if overall_avg is not None else "—"

    empty_row = '<tr><td colspan="3" style="padding:16px;text-align:center;color:#888;">Chưa có dữ liệu trong khoảng thời gian này</td></tr>'
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
      <div style="background:linear-gradient(135deg,#3F7FD6,#2BB6A6);padding:28px;text-align:center;border-radius:16px 16px 0 0;">
        <div style="font-size:40px;">📊</div>
        <h1 style="color:white;margin:8px 0;">Báo cáo học tập {period_label} qua</h1>
        <p style="color:rgba(255,255,255,0.85);">Học sinh: <strong>{child.username}</strong> · Lớp {child.grade}</p>
      </div>
      <div style="background:white;padding:24px;">
        <p>Kính gửi <strong>{current_user.username}</strong>,</p>
        <p>Đây là tóm tắt hoạt động học tập của <strong>{child.username}</strong> trong {period_label} qua:</p>

        <!-- Số liệu tổng quan -->
        <table style="width:100%;border-collapse:separate;border-spacing:8px 0;margin:8px 0 16px;">
          <tr>
            <td style="background:#f0fff8;border-radius:12px;padding:14px;text-align:center;">
              <div style="font-size:26px;font-weight:900;color:#1FCBA6;">{len(recs)}</div>
              <div style="color:#666;font-size:12px;">Bài đã học</div>
            </td>
            <td style="background:#f0f4ff;border-radius:12px;padding:14px;text-align:center;">
              <div style="font-size:26px;font-weight:900;color:#3F7FD6;">{avg_display}</div>
              <div style="color:#666;font-size:12px;">Điểm trung bình</div>
            </td>
            <td style="background:#fff7ef;border-radius:12px;padding:14px;text-align:center;">
              <div style="font-size:26px;font-weight:900;color:#FF6B35;">{len(by_sub)}</div>
              <div style="color:#666;font-size:12px;">Môn học</div>
            </td>
          </tr>
        </table>

        <!-- Nhận xét về con -->
        <div style="background:#eef6ff;border-radius:12px;padding:16px;border-left:4px solid #3F7FD6;margin-bottom:16px;">
          <div style="font-weight:900;color:#1A2340;margin-bottom:4px;">{assess_title}</div>
          <div style="color:#444;font-size:14px;line-height:1.6;">{assess_body}</div>
        </div>

        <table style="width:100%;border-collapse:collapse;margin:16px 0;border-radius:12px;overflow:hidden;">
          <thead>
            <tr style="background:#f0f4ff;">
              <th style="padding:12px 14px;text-align:left;font-size:13px;color:#666;">Môn học</th>
              <th style="padding:12px 14px;text-align:center;font-size:13px;color:#666;">Số bài</th>
              <th style="padding:12px 14px;text-align:center;font-size:13px;color:#666;">Điểm TB</th>
            </tr>
          </thead>
          <tbody>{rows if rows else empty_row}</tbody>
        </table>

        <!-- Chi tiết các bài gần đây -->
        {f'<h3 style="margin:18px 0 0;color:#1A2340;font-size:15px;">📚 Chi tiết bài học gần đây</h3>{detail}' if detail else ''}

        <div style="background:#e8f5e9;border-radius:12px;padding:14px;margin-top:16px;border-left:4px solid #2ED573;">
          💡 <strong>Lời khuyên:</strong> Hãy khuyến khích em học đều đặn mỗi ngày 20-30 phút.
          Kiên trì là chìa khóa dẫn đến thành công! 🌟
        </div>
        <p style="color:#aaa;font-size:11px;margin-top:20px;">
          Xem chi tiết &amp; nhận tư vấn giáo dục tại: <a href="{PUBLIC_BASE_URL}/app">Bảng kiểm soát Phụ Huynh SmartBuddy</a>
        </p>
      </div>
      <div style="background:#f5f5f5;padding:14px;text-align:center;color:#888;font-size:12px;border-radius:0 0 16px 16px;">
        SmartBuddy — Học thông minh, Tiến vững vàng 🤖
      </div>
    </div>"""
