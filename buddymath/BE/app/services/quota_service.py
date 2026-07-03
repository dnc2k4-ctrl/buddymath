"""
quota_service.py – Enforce GIỚI HẠN THEO GÓI (đọc từ app/plans.py — nguồn duy nhất).

Ba việc:
  1. Đếm & chặn số câu Toán/AI mỗi ngày và số ảnh giải mỗi ngày (metric math/image).
  2. Khoá môn theo gói (Tiếng Anh cần englishEnabled, Kỹ năng sống cần lifeSkillsEnabled).
  3. Trả lỗi có CẤU TRÚC (429/403) kèm nội dung khích lệ (lấy từ plans.UI_TEXT) để FE
     hiện popup thân thiện trẻ em + nút "Xem các gói".

Nhận diện đối tượng: user đã đăng nhập → "user:<id>"; khách → "ip:<addr>".
Gói áp dụng: user.effective_plan() (hết hạn tự về Free); khách → Free.
Đếm lưu ở bảng daily_usage (bền qua restart). Nếu DB lỗi → FAIL-OPEN (cho qua, chỉ log)
để không chặn oan trẻ đang học; chỉ 429/403 khi thực sự vượt giới hạn.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app import plans
from app.models.usage import DailyUsage

logger = logging.getLogger(__name__)

METRIC_MATH = "math"
METRIC_IMAGE = "image"

# metric → key trong plans.limits
_METRIC_LIMIT_KEY = {
    METRIC_MATH: "mathQuestionsPerDay",
    METRIC_IMAGE: "imageSolvesPerDay",
}
# metric → khoá trong plans.UI_TEXT["limitReached"]
_METRIC_UI_KEY = {METRIC_MATH: "math", METRIC_IMAGE: "image"}

# Môn cần mở khoá theo gói: (subject chuẩn hoá) → (limits key, UI key, gói tối thiểu)
_FEATURE_SUBJECTS = {
    "english":     ("englishEnabled",    "english",    "standard"),
    "life_skills": ("lifeSkillsEnabled", "lifeSkills", "premium"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Nhận diện đối tượng & gói
# ─────────────────────────────────────────────────────────────────────────────
def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def key_for(request: Request, user=None) -> str:
    """Khoá đếm: user đã đăng nhập theo id, khách theo IP."""
    if user is not None:
        return f"user:{user.id}"
    return f"ip:{_client_ip(request)}"


def plan_for(user=None) -> str:
    """Gói THỰC TẾ đang hiệu lực: khách = Free; user = effective_plan (hết hạn → Free)."""
    if user is None:
        return plans.DEFAULT_PLAN
    return user.effective_plan()


def normalize_subject(subject: Optional[str]) -> str:
    """Gom nhãn môn FE gửi về 3 nhóm chuẩn: english | life_skills | math (mặc định)."""
    s = (subject or "").strip().lower()
    if not s:
        return "math"
    if s.startswith("english") or "tiếng anh" in s or "tieng anh" in s or "anh văn" in s:
        return "english"
    if s.startswith("life") or "kỹ năng" in s or "ky nang" in s or "kynang" in s:
        return "life_skills"
    # Toán / Khoa học / Môn khác / chat chung → tính vào quota "câu hỏi AI mỗi ngày"
    return "math"


def _today_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────────────
# Lỗi có cấu trúc cho FE
# ─────────────────────────────────────────────────────────────────────────────
def _quota_error(metric: str, plan_id: str, limit) -> HTTPException:
    ui = plans.UI_TEXT["limitReached"][_METRIC_UI_KEY[metric]]
    return HTTPException(
        status_code=429,
        detail={
            "error": "quota_exceeded",
            "metric": metric,
            "plan": plan_id,
            "limit": limit,
            "upgradeTo": "standard",
            "title": ui["title"],
            "message": ui["body"],
            "cta": ui["cta"],
        },
    )


def _feature_error(ui_key: str, feature_key: str, plan_id: str, upgrade_to: str) -> HTTPException:
    ui = plans.UI_TEXT["limitReached"][ui_key]
    return HTTPException(
        status_code=403,
        detail={
            "error": "feature_locked",
            "feature": feature_key,
            "plan": plan_id,
            "upgradeTo": upgrade_to,
            "title": ui["title"],
            "message": ui["body"],
            "cta": ui["cta"],
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Đếm usage (DB)
# ─────────────────────────────────────────────────────────────────────────────
def _row(db: Session, key: str, day: str, metric: str) -> Optional[DailyUsage]:
    return (
        db.query(DailyUsage)
        .filter(DailyUsage.subject_key == key, DailyUsage.day == day, DailyUsage.metric == metric)
        .first()
    )


def current_count(db: Session, key: str, metric: str) -> int:
    row = _row(db, key, _today_utc(), metric)
    return row.count if row else 0


def _increment(db: Session, key: str, metric: str) -> None:
    """Cộng 1 cho (key, hôm nay, metric). Chống đua bằng retry khi vướng unique."""
    day = _today_utc()
    row = _row(db, key, day, metric)
    if row:
        row.count += 1
        db.commit()
        return
    db.add(DailyUsage(subject_key=key, day=day, metric=metric, count=1))
    try:
        db.commit()
    except Exception:                      # 2 request cùng lúc tạo trùng dòng
        db.rollback()
        row = _row(db, key, day, metric)
        if row:
            row.count += 1
            db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# API công khai để endpoint gọi
# ─────────────────────────────────────────────────────────────────────────────
def enforce_feature(*, plan_id: str, subject: Optional[str]) -> None:
    """Khoá môn theo gói. Raise 403 nếu gói chưa mở môn này."""
    entry = _FEATURE_SUBJECTS.get(normalize_subject(subject))
    if not entry:
        return
    feature_key, ui_key, upgrade_to = entry
    if not plans.feature_enabled(plan_id, feature_key):
        raise _feature_error(ui_key, feature_key, plan_id, upgrade_to)


def check_and_record(db: Session, *, key: str, plan_id: str, metric: str) -> None:
    """
    Chặn 429 nếu đã đạt giới hạn ngày; nếu còn lượt thì +1.
    Gói không giới hạn (Infinity) → không đếm, cho qua luôn.
    DB lỗi → fail-open (log, cho qua) để không chặn oan.
    """
    limit = plans.get_limit(plan_id, _METRIC_LIMIT_KEY[metric])
    if plans.is_unlimited(limit):
        return
    try:
        used = current_count(db, key, metric)
    except Exception as e:                  # noqa: BLE001
        logger.warning(f"[quota] đọc usage lỗi ({key}/{metric}): {e} — fail-open")
        return
    if used >= limit:
        raise _quota_error(metric, plan_id, limit)
    try:
        _increment(db, key, metric)
    except Exception as e:                   # noqa: BLE001
        logger.warning(f"[quota] ghi usage lỗi ({key}/{metric}): {e} — cho qua")


def enforce_request(
    db: Session, request: Request, user, *, metric: str, subject: Optional[str] = None
) -> None:
    """Gộp: khoá môn (nếu có) + đếm/chặn quota. Endpoint chỉ cần gọi 1 hàm này."""
    plan_id = plan_for(user)
    if metric == METRIC_MATH:              # môn học chỉ áp cho câu hỏi text
        enforce_feature(plan_id=plan_id, subject=subject)
    check_and_record(db, key=key_for(request, user), plan_id=plan_id, metric=metric)


# ─────────────────────────────────────────────────────────────────────────────
# Tóm tắt cho FE (hiện "còn X lượt" + hạn gói)
# ─────────────────────────────────────────────────────────────────────────────
def usage_summary(db: Session, request: Request, user) -> dict:
    plan_id = plan_for(user)
    key = key_for(request, user)

    def _metric_info(metric: str) -> dict:
        limit = plans.get_limit(plan_id, _METRIC_LIMIT_KEY[metric])
        unlimited = plans.is_unlimited(limit)
        used = 0
        try:
            used = current_count(db, key, metric)
        except Exception:                   # noqa: BLE001
            pass
        return {
            "used": used,
            "limit": None if unlimited else limit,
            "unlimited": unlimited,
            "remaining": None if unlimited else max(0, limit - used),
        }

    expires = getattr(user, "plan_expires_at", None) if user else None
    return {
        "plan": plan_id,
        "plan_expires_at": expires.isoformat() if expires else None,
        "usage": {
            "math": _metric_info(METRIC_MATH),
            "image": _metric_info(METRIC_IMAGE),
        },
    }
