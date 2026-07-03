"""
test_plans_quota.py – Unit test cơ bản cho giới hạn theo gói (BƯỚC 3).

Chạy KHÔNG cần pytest (môi trường chưa cài):
    cd buddymath/BE && python tests/test_plans_quota.py
Nếu có pytest thì cũng chạy được: pytest tests/test_plans_quota.py

Kiểm:
  • Free bị chặn sau 10 câu Toán/ngày và sau 2 ảnh/ngày (429, kèm gợi ý nâng cấp).
  • Standard/Premium math không giới hạn → không bị chặn.
  • Tiếng Anh khoá ở Free, mở ở Standard/Premium (403 khi khoá).
  • Kỹ năng sống khoá ở Free/Standard, mở ở Premium.
  • Hết hạn subscription → tự hạ về Free (không gia hạn ngầm).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

# Cho phép "import app.*" khi chạy trực tiếp từ thư mục BE/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models, plans  # noqa: E402,F401  (import models để đăng ký bảng)
from app.core.database import Base  # noqa: E402
from app.services import quota_service as q  # noqa: E402


# ── DB in-memory riêng cho test (không đụng DB thật) ──
_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(_engine)
_Session = sessionmaker(bind=_engine)


def _fresh_db():
    db = _Session()
    db.query(models.DailyUsage).delete()
    db.commit()
    return db


class _FakeReq:
    """Giả Request đủ để key_for() lấy IP."""
    def __init__(self, ip="1.2.3.4"):
        self.headers = {}
        self.client = type("C", (), {"host": ip})()


def _status_of(fn) -> int:
    """Chạy fn, trả HTTP status nếu raise HTTPException, 200 nếu qua."""
    try:
        fn()
        return 200
    except HTTPException as e:
        return e.status_code


# ─────────────────────────────────────────────────────────────────────────────
def test_free_math_limit_10():
    db = _fresh_db()
    key = "user:free-math"
    for i in range(10):                       # 10 câu đầu: OK
        assert _status_of(lambda: q.check_and_record(db, key=key, plan_id="free", metric=q.METRIC_MATH)) == 200, \
            f"câu thứ {i+1} không được bị chặn"
    # Câu thứ 11: bị chặn 429
    st = _status_of(lambda: q.check_and_record(db, key=key, plan_id="free", metric=q.METRIC_MATH))
    assert st == 429, f"câu 11 phải 429, nhận {st}"
    assert q.current_count(db, key, q.METRIC_MATH) == 10, "không được đếm quá 10"


def test_free_image_limit_2():
    db = _fresh_db()
    key = "ip:9.9.9.9"
    assert _status_of(lambda: q.check_and_record(db, key=key, plan_id="free", metric=q.METRIC_IMAGE)) == 200
    assert _status_of(lambda: q.check_and_record(db, key=key, plan_id="free", metric=q.METRIC_IMAGE)) == 200
    st = _status_of(lambda: q.check_and_record(db, key=key, plan_id="free", metric=q.METRIC_IMAGE))
    assert st == 429, f"ảnh thứ 3 phải 429, nhận {st}"


def test_quota_error_payload_has_upgrade_hint():
    db = _fresh_db()
    key = "user:payload"
    for _ in range(10):
        q.check_and_record(db, key=key, plan_id="free", metric=q.METRIC_MATH)
    try:
        q.check_and_record(db, key=key, plan_id="free", metric=q.METRIC_MATH)
        assert False, "phải raise 429"
    except HTTPException as e:
        d = e.detail
        assert d["error"] == "quota_exceeded" and d["metric"] == "math"
        assert d["upgradeTo"] == "standard"
        assert d["cta"] and d["message"], "phải kèm nội dung + nút gợi ý nâng cấp"


def test_paid_math_unlimited():
    db = _fresh_db()
    for plan in ("standard", "premium"):
        key = f"user:{plan}-math"
        for _ in range(50):                   # 50 câu vẫn không bị chặn
            st = _status_of(lambda: q.check_and_record(db, key=key, plan_id=plan, metric=q.METRIC_MATH))
            assert st == 200, f"{plan} math phải không giới hạn"
        # Không giới hạn thì KHÔNG ghi đếm
        assert q.current_count(db, key, q.METRIC_MATH) == 0


def test_english_locked_on_free_open_on_paid():
    assert _status_of(lambda: q.enforce_feature(plan_id="free", subject="english")) == 403
    assert _status_of(lambda: q.enforce_feature(plan_id="standard", subject="english")) == 200
    assert _status_of(lambda: q.enforce_feature(plan_id="premium", subject="english")) == 200


def test_life_skills_only_on_premium():
    assert _status_of(lambda: q.enforce_feature(plan_id="free", subject="life_skills")) == 403
    assert _status_of(lambda: q.enforce_feature(plan_id="standard", subject="life_skills")) == 403
    assert _status_of(lambda: q.enforce_feature(plan_id="premium", subject="life_skills")) == 200


def test_math_subject_never_locked():
    for plan in ("free", "standard", "premium"):
        assert _status_of(lambda: q.enforce_feature(plan_id=plan, subject="Toán học")) == 200
        assert _status_of(lambda: q.enforce_feature(plan_id=plan, subject=None)) == 200


def test_expired_subscription_downgrades_to_free():
    past = datetime.utcnow() - timedelta(days=1)
    future = datetime.utcnow() + timedelta(days=5)
    assert plans.effective_plan("premium", past) == "free", "hết hạn phải về free"
    assert plans.effective_plan("premium", future) == "premium", "còn hạn giữ premium"
    assert plans.effective_plan("standard", None) == "free", "không có hạn = coi như hết → free"
    assert plans.effective_plan("free", None) == "free"


def test_usage_summary_shape():
    db = _fresh_db()
    req = _FakeReq("5.5.5.5")
    q.check_and_record(db, key=q.key_for(req, None), plan_id="free", metric=q.METRIC_MATH)
    s = q.usage_summary(db, req, None)          # khách (chưa đăng nhập) → free
    assert s["plan"] == "free"
    assert s["usage"]["math"]["used"] == 1
    assert s["usage"]["math"]["limit"] == 10
    assert s["usage"]["math"]["remaining"] == 9
    assert s["usage"]["image"]["limit"] == 2


# ── Runner tự chạy khi không có pytest ──
def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} test PASSED")
    return passed == len(tests)


if __name__ == "__main__":
    ok = _run()
    sys.exit(0 if ok else 1)
