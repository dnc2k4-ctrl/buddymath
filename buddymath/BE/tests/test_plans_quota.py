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

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta

# Cho phép "import app.*" khi chạy trực tiếp từ thư mục BE/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models, plans  # noqa: E402,F401  (import models để đăng ký bảng)
from app.api.auth import register  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.user import ParentChildLink, User  # noqa: E402
from app.api.parent import _require_parent, link_child  # noqa: E402
from app.schemas.auth import LinkChildReq, RegisterReq  # noqa: E402
from app.services import email_service, report_scheduler  # noqa: E402
from app.services import quota_service as q  # noqa: E402


# ── DB in-memory riêng cho test (không đụng DB thật) ──
_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(_engine)
_Session = sessionmaker(bind=_engine)


def _fresh_db():
    db = _Session()
    db.query(models.DailyUsage).delete()
    db.query(ParentChildLink).delete()
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


def test_image_request_counts_toward_daily_question_limit():
    db = _fresh_db()
    user = User(
        email=f"image-{uuid.uuid4()}@example.test",
        username="Student",
        password_hash="unused",
        role="student",
        created_at=datetime.utcnow() - timedelta(days=1),
    )
    db.add(user)
    db.commit()
    for _ in range(2):
        q.enforce_request(db, _FakeReq(), user, metric=q.METRIC_IMAGE)
    assert q.current_count(db, f"user:{user.id}", q.METRIC_MATH) == 2
    assert q.current_count(db, f"user:{user.id}", q.METRIC_IMAGE) == 2


def test_image_request_obeys_paid_subject_entitlements():
    db = _fresh_db()
    user = User(
        email=f"english-image-{uuid.uuid4()}@example.test",
        username="Student",
        password_hash="unused",
        role="student",
        created_at=datetime.utcnow() - timedelta(days=1),
    )
    db.add(user)
    db.commit()
    try:
        q.enforce_request(db, _FakeReq(), user, metric=q.METRIC_IMAGE, subject="Tiếng Anh")
        assert False, "Free không được dùng ảnh để vượt khóa môn Tiếng Anh"
    except HTTPException as exc:
        assert exc.status_code == 403 and exc.detail["error"] == "feature_locked"
    assert q.current_count(db, f"user:{user.id}", q.METRIC_IMAGE) == 0


def test_free_trial_expires_after_seven_days():
    db = _fresh_db()
    user = User(
        email=f"trial-{uuid.uuid4()}@example.test",
        username="Student",
        password_hash="unused",
        role="student",
        created_at=datetime.utcnow() - timedelta(days=6),
    )
    db.add(user)
    db.commit()
    assert _status_of(lambda: q.enforce_request(
        db, _FakeReq(), user, metric=q.METRIC_MATH
    )) == 200
    user.created_at = datetime.utcnow() - timedelta(days=7)
    db.commit()
    try:
        q.enforce_request(db, _FakeReq(), user, metric=q.METRIC_MATH)
        assert False, "tài khoản free hết 7 ngày phải bị chặn"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["error"] == "trial_expired"
        assert exc.detail["upgradeTo"] == "standard"
        assert exc.detail["message"] and exc.detail["cta"]


def test_paid_account_is_not_blocked_by_free_trial_age():
    user = User(
        email=f"paid-trial-{uuid.uuid4()}@example.test",
        username="Student",
        password_hash="unused",
        role="student",
        plan="standard",
        plan_expires_at=datetime.utcnow() + timedelta(days=10),
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    assert q.trial_expired(user) is False


def test_subscription_expiry_metadata_preserves_renewal_plan():
    active = User(
        email=f"expiring-{uuid.uuid4()}@example.test",
        username="Learner",
        password_hash="x",
        role="student",
        plan="standard",
        plan_expires_at=datetime.utcnow() + timedelta(days=6),
    ).to_dict()
    assert active["plan"] == "standard"
    assert active["subscription_plan"] == "standard"
    assert active["subscription_days_remaining"] <= 6
    assert active["subscription_days_remaining"] > 0

    expired = User(
        email=f"expired-{uuid.uuid4()}@example.test",
        username="Learner",
        password_hash="x",
        role="student",
        plan="premium",
        plan_expires_at=datetime.utcnow() - timedelta(days=1),
    ).to_dict()
    assert expired["plan"] == "free"
    assert expired["subscription_plan"] == "premium"
    assert expired["subscription_days_remaining"] <= 0

    free = User(
        email=f"free-{uuid.uuid4()}@example.test",
        username="Learner",
        password_hash="x",
        role="student",
    ).to_dict()
    assert free["subscription_plan"] is None
    assert free["subscription_days_remaining"] is None


def test_parent_portal_requires_paid_plan_and_supports_student_account():
    free_student = User(email="free-student@example.test", username="Learner", password_hash="x", role="student")
    paid_student = User(
        email="paid-student@example.test", username="Learner", password_hash="x", role="student",
        plan="standard", plan_expires_at=datetime.utcnow() + timedelta(days=5),
    )
    free_parent = User(email="free-parent@example.test", username="Parent", password_hash="x", role="parent")
    assert _status_of(lambda: _require_parent(free_student)) == 403
    assert _status_of(lambda: _require_parent(free_parent)) == 403
    assert _status_of(lambda: _require_parent(paid_student)) == 200
    assert paid_student.to_dict()["parent_access"] is True
    assert free_student.to_dict()["parent_access"] is False


def test_paid_student_can_link_the_same_account_for_parent_reports():
    db = _fresh_db()
    for role in ("student", "parent"):
        account = User(
            email=f"dual-role-{role}-{uuid.uuid4()}@example.test",
            username="Learner",
            password_hash="x",
            role=role,
            plan="standard",
            plan_expires_at=datetime.utcnow() + timedelta(days=5),
        )
        db.add(account)
        db.commit()

        result = asyncio.run(link_child(
            LinkChildReq(child_email=f" {account.email.upper()} "),
            current_user=account,
            db=db,
        ))

        assert result["success"] is True
        assert result["child"]["id"] == account.id
        links = db.query(ParentChildLink).filter(
            ParentChildLink.parent_id == account.id,
            ParentChildLink.child_id == account.id,
        ).all()
        assert len(links) == 1


def test_same_email_cannot_create_a_second_parent_account():
    db = _fresh_db()
    email = f"one-email-{uuid.uuid4()}@example.test"
    db.add(User(email=email, username="Learner", password_hash="x", role="student"))
    db.commit()
    request = RegisterReq(email=email, username="Parent", password="secret1", role="parent")
    try:
        asyncio.run(register(request, db))
        assert False, "không được tạo tài khoản trùng email"
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "nâng cấp" in exc.detail
    assert db.query(User).filter(User.email == email).count() == 1


def test_email_cadence_is_based_on_parent_plan():
    assert plans.get_limit("standard", "emailReportFrequency") == "weekly"
    assert plans.get_limit("premium", "emailReportFrequency") == "daily_activity"
    assert plans.get_limit("free", "emailReportFrequency") is None


def test_premium_activity_email_sends_once_per_day():
    db = _fresh_db()
    now = datetime.utcnow()
    parent = User(
        email=f"parent-{uuid.uuid4()}@example.test", username="Parent", password_hash="x", role="parent",
        plan="premium", plan_expires_at=now + timedelta(days=20),
    )
    child = User(
        email=f"child-{uuid.uuid4()}@example.test", username="Learner", password_hash="x", role="student",
        created_at=now - timedelta(days=1),
    )
    db.add_all([parent, child])
    db.commit()
    link = ParentChildLink(parent_id=parent.id, child_id=child.id)
    db.add(link)
    db.commit()

    sent = []
    old_configured = email_service.smtp_configured
    old_send = email_service.smtp_send
    email_service.smtp_configured = lambda: True
    email_service.smtp_send = lambda to, subject, body: sent.append((to, subject, body))
    try:
        email_service.notify_parents(child, None, db)
        email_service.notify_parents(child, None, db)
    finally:
        email_service.smtp_configured = old_configured
        email_service.smtp_send = old_send
    assert len(sent) == 1
    assert sent[0][0] == parent.email
    assert link.last_activity_email_at is not None


def test_weekly_scheduler_uses_parent_subscription_not_child_plan():
    db = _fresh_db()
    now = datetime.utcnow()
    parent = User(
        email=f"weekly-parent-{uuid.uuid4()}@example.test", username="Parent", password_hash="x", role="parent",
        plan="standard", plan_expires_at=now + timedelta(days=20),
    )
    child = User(
        email=f"premium-child-{uuid.uuid4()}@example.test", username="Learner", password_hash="x", role="student",
        plan="premium", plan_expires_at=now + timedelta(days=20),
    )
    db.add_all([parent, child])
    db.commit()
    db.add(ParentChildLink(parent_id=parent.id, child_id=child.id))
    db.commit()

    old_configured = report_scheduler.smtp_configured
    old_send = report_scheduler.smtp_send
    sent = []
    report_scheduler.smtp_configured = lambda: True
    report_scheduler.smtp_send = lambda to, subject, body: sent.append((to, subject))
    try:
        result = report_scheduler.send_due_reports(db)
    finally:
        report_scheduler.smtp_configured = old_configured
        report_scheduler.smtp_send = old_send
    assert result["sent"] == 1
    assert sent and sent[0][0] == parent.email


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
