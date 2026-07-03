"""
plans.py – NGUỒN DUY NHẤT (single source of truth) cho gói đăng ký Smart Buddy.

Backend đọc file này để enforce giới hạn. Frontend nhận CÙNG dữ liệu này qua:
  • GET /config/plans.js  → gán window.SB_PLANS (FE nạp bằng <script src>)
  • GET /api/plans        → JSON (cho công cụ/API khác)

Quy ước "không giới hạn" = float('inf') trong Python và Infinity trong JS.
emailReportFrequency = None nghĩa là KHÔNG có báo cáo (khác với "không giới hạn").

⚠️ Đổi gói/giá/giới hạn: CHỈ sửa ở đây. Không hardcode số liệu ở nơi khác.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

UNLIMITED = float("inf")
DEFAULT_PLAN = "free"

# ─────────────────────────────────────────────────────────────────────────────
# Định nghĩa gói (đúng cấu trúc spec)
# ─────────────────────────────────────────────────────────────────────────────
PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Miễn phí",
        "price": 0,
        "billingCycle": None,
        "limits": {
            "mathQuestionsPerDay": 10,
            "imageSolvesPerDay": 2,
            "englishEnabled": False,
            "lifeSkillsEnabled": False,
            "emailReportFrequency": None,   # không có báo cáo email
            "aiDebateDepth": "none",        # AI phản biện/đạo đức
        },
    },
    "standard": {
        "id": "standard",
        "name": "Standard",
        "price": 199000,
        "billingCycle": "monthly",
        "limits": {
            "mathQuestionsPerDay": UNLIMITED,
            "imageSolvesPerDay": 15,
            "englishEnabled": True,
            "lifeSkillsEnabled": False,
            "emailReportFrequency": "weekly",
            "aiDebateDepth": "basic",
        },
    },
    "premium": {
        "id": "premium",
        "name": "Premium",
        "price": 299000,
        "billingCycle": "monthly",
        "limits": {
            "mathQuestionsPerDay": UNLIMITED,
            "imageSolvesPerDay": UNLIMITED,
            "englishEnabled": True,
            "lifeSkillsEnabled": True,
            "emailReportFrequency": "per_lesson",  # sau mỗi bài học
            "aiDebateDepth": "full",
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Metadata hiển thị cho FE (bảng so sánh ✓/✗, CTA, thông báo) — cũng là source of truth
# ─────────────────────────────────────────────────────────────────────────────
# Thứ tự dòng của bảng so sánh tính năng.
FEATURE_ROWS: list[dict[str, Any]] = [
    {"key": "mathQuestionsPerDay", "label": "Câu hỏi Toán mỗi ngày", "type": "count", "unit": "câu/ngày"},
    {"key": "imageSolvesPerDay",   "label": "Giải bài bằng ảnh",      "type": "count", "unit": "ảnh/ngày"},
    {"key": "englishEnabled",      "label": "Môn Tiếng Anh",          "type": "bool"},
    {"key": "lifeSkillsEnabled",   "label": "Môn Kỹ năng sống",       "type": "bool"},
    {"key": "emailReportFrequency", "label": "Báo cáo email cho phụ huynh", "type": "enum",
     "enumLabels": {"none": "—", "weekly": "Hàng tuần", "per_lesson": "Sau mỗi bài học"}},
    {"key": "aiDebateDepth",       "label": "AI phản biện / đạo đức", "type": "enum",
     "enumLabels": {"none": "—", "basic": "Cơ bản", "full": "Đầy đủ"}},
]

# Toàn bộ text hiển thị liên quan gói (để FE không hardcode chữ).
UI_TEXT: dict[str, Any] = {
    "unlimitedLabel": "Không giới hạn",
    "priceFreeLabel": "0đ",
    "priceSuffixMonthly": "/tháng",
    "cta": {"free": "Bắt đầu miễn phí", "paid": "Nâng cấp ngay"},
    "compareTitle": "So sánh các gói",
    "pricingTitle": "Chọn gói học cùng Smart Buddy",
    "pricingSubtitle": "Nâng cấp để học không giới hạn và mở khoá thêm môn ✨",
    # Thông báo khi user Free chạm giới hạn (BƯỚC 5) — giọng khích lệ, hợp trẻ 3–9
    "limitReached": {
        "math": {
            "title": "Hết lượt hỏi Toán hôm nay rồi! 🌟",
            "body": "Hôm nay em đã dùng hết lượt hỏi Toán miễn phí. Nâng cấp lên Standard để hỏi Buddy không giới hạn mỗi ngày nhé!",
            "cta": "Xem các gói",
        },
        "image": {
            "title": "Hết lượt giải bài bằng ảnh hôm nay rồi! 📸",
            "body": "Hôm nay em đã dùng hết lượt chụp ảnh hỏi bài. Nâng cấp gói để chụp ảnh hỏi Buddy thoải mái hơn nhé!",
            "cta": "Xem các gói",
        },
        "english": {
            "title": "Môn Tiếng Anh có ở gói Standard 🇬🇧",
            "body": "Nâng cấp lên Standard để cùng Buddy học Tiếng Anh nhé!",
            "cta": "Xem các gói",
        },
        "lifeSkills": {
            "title": "Môn Kỹ năng sống có ở gói Premium 🌱",
            "body": "Nâng cấp lên Premium để khám phá các bài Kỹ năng sống cùng Buddy nhé!",
            "cta": "Xem các gói",
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers (backend dùng để enforce)
# ─────────────────────────────────────────────────────────────────────────────
def normalize_plan(plan_id: Optional[str]) -> str:
    return plan_id if plan_id in PLANS else DEFAULT_PLAN


def get_plan(plan_id: Optional[str]) -> dict[str, Any]:
    return PLANS[normalize_plan(plan_id)]


def plan_limits(plan_id: Optional[str]) -> dict[str, Any]:
    return get_plan(plan_id)["limits"]


def get_limit(plan_id: Optional[str], key: str) -> Any:
    return plan_limits(plan_id).get(key)


def is_unlimited(value: Any) -> bool:
    return value == UNLIMITED


def feature_enabled(plan_id: Optional[str], feature_key: str) -> bool:
    return bool(plan_limits(plan_id).get(feature_key, False))


def effective_plan(plan_id: Optional[str], expires_at: Optional[datetime],
                   now: Optional[datetime] = None) -> str:
    """Gói THỰC TẾ đang hiệu lực: nếu subscription đã hết hạn → tự hạ về Free (không gia hạn ngầm)."""
    pid = normalize_plan(plan_id)
    if pid == DEFAULT_PLAN:
        return pid
    now = now or datetime.utcnow()
    if expires_at is None or expires_at <= now:
        return DEFAULT_PLAN
    return pid


# ─────────────────────────────────────────────────────────────────────────────
# Serialize để phục vụ FE (giữ NGUYÊN 1 nguồn)
# ─────────────────────────────────────────────────────────────────────────────
def _js_value(v: Any) -> str:
    """Serialize sang literal JS (giữ Infinity/null đúng như spec)."""
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, float) and v == UNLIMITED:
        return "Infinity"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        return "{" + ",".join(f"{json.dumps(str(k), ensure_ascii=False)}:{_js_value(val)}"
                              for k, val in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_js_value(x) for x in v) + "]"
    return "null"


def _payload() -> dict[str, Any]:
    return {
        "plans": PLANS,
        "order": ["free", "standard", "premium"],
        "featureRows": FEATURE_ROWS,
        "ui": UI_TEXT,
        "defaultPlan": DEFAULT_PLAN,
    }


def plans_as_js() -> str:
    """Nội dung file /config/plans.js — gán window.SB_PLANS (Infinity là literal JS hợp lệ)."""
    return "/* Auto-generated từ app/plans.py — KHÔNG sửa tay. */\n" \
           "window.SB_PLANS = " + _js_value(_payload()) + ";\n"


def _json_safe(v: Any) -> Any:
    """inf → None cho JSON (JSON không có Infinity). Field số null = không giới hạn."""
    if isinstance(v, float) and v == UNLIMITED:
        return None
    if isinstance(v, dict):
        return {k: _json_safe(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v


def plans_as_json() -> dict[str, Any]:
    """Payload JSON cho /api/plans (unlimited numeric → null)."""
    return _json_safe(_payload())
