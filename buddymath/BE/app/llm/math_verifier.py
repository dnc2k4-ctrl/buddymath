"""
math_verifier.py – Kiểm chứng số học/đại số bằng sympy để cấp "ground truth" cho AI.

Vì LLM (nhất là model nhỏ) hay tính sai và có thể khen đúng một kết quả sai,
module này trích các phép tính & đẳng thức trong câu của HỌC SINH, tính lại độc lập
bằng sympy, rồi sinh một ghi chú "chỉ để Buddy tự đối chiếu" tiêm vào system prompt.

Nguyên tắc:
  • FAIL-OPEN: không chắc chắn thì im lặng (thà không nói còn hơn cấp dữ kiện sai).
  • Chỉ nhận chuỗi toàn CHỮ SỐ + toán tử (whitelist) → sympify an toàn, không exec code.
  • Không hé đáp án cho học sinh — ghi chú luôn nhắc "đừng đọc thẳng con số".
"""
from __future__ import annotations

import re

try:
    from sympy import sympify
    _SYMPY_OK = True
except Exception:  # pragma: no cover - sympy luôn có trong requirements
    _SYMPY_OK = False

_MAX_FACTS = 4
_ALLOWED = re.compile(r"^[0-9+\-*/().\s]+$")            # sau normalize: chỉ số + toán tử
_CLAIM = re.compile(r"([0-9][0-9+\-*/(). ]*[+\-*/][0-9+\-*/(). ]*?)=\s*(-?[0-9][0-9./]*)")
_BARE = re.compile(r"[0-9][0-9+\-*/(). ]*[+*/][0-9+\-*/(). ]*[0-9]")


def _normalize(text: str) -> str:
    t = text
    for ch in "×·✕∗":
        t = t.replace(ch, "*")
    for ch in "÷∕":
        t = t.replace(ch, "/")
    for ch in "–—−":
        t = t.replace(ch, "-")
    t = t.replace("^", "**")
    t = re.sub(r"(\d)\s*[xX]\s*(\d)", r"\1*\2", t)      # 24 x 5 -> 24*5
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)              # 3,5 -> 3.5 (thập phân VN)
    return t


def _safe_eval(expr: str):
    """Tính giá trị số của một biểu thức an toàn; None nếu không chắc/không hợp lệ."""
    expr = expr.strip()
    if not expr or not _ALLOWED.match(expr) or len(expr) > 40:
        return None
    if re.search(r"\*\*\s*\d{2,}", expr):              # mũ >= 10 → bỏ (tránh DoS)
        return None
    if re.search(r"\d{7,}", expr):                     # số quá lớn → bỏ
        return None
    if expr.count("(") != expr.count(")"):
        return None
    try:
        val = sympify(expr)
    except Exception:
        return None
    if val is None or not getattr(val, "is_number", False):
        return None
    if val.is_finite is False:                          # chia 0 → zoo/oo
        return None
    return val


def _fmt(val) -> str:
    if getattr(val, "is_Integer", False):
        return str(val)
    if getattr(val, "is_Rational", False):
        return f"{val.p}/{val.q}"
    try:
        f = float(val)
        return str(int(f)) if f == int(f) else f"{f:g}"
    except Exception:
        return str(val)


def _is_equal(lval, rval) -> bool:
    d = lval - rval
    if getattr(d, "is_zero", None) is True:
        return True
    try:
        return abs(float(d)) < 1e-9
    except Exception:
        return False


def verification_note(text: str) -> str:
    """Trả về ghi chú "dữ kiện đã kiểm chứng" để tiêm vào system prompt (rỗng nếu không có gì chắc chắn)."""
    if not _SYMPY_OK or not text:
        return ""
    t = _normalize(text[:400])
    facts: list[str] = []
    spans: list[tuple[int, int]] = []

    # 1) Đẳng thức học sinh khẳng định: "LHS = RHS"
    for m in _CLAIM.finditer(t):
        if len(facts) >= _MAX_FACTS:
            break
        lhs, rhs = m.group(1).strip(), m.group(2).strip()
        lval, rval = _safe_eval(lhs), _safe_eval(rhs)
        if lval is None or rval is None:
            continue
        spans.append((m.start(), m.end()))
        if _is_equal(lval, rval):
            facts.append(f'Đẳng thức "{lhs} = {rhs}" mà học sinh viết là ĐÚNG.')
        else:
            facts.append(
                f'Đẳng thức "{lhs} = {rhs}" mà học sinh viết là SAI — giá trị đúng của "{lhs}" là {_fmt(lval)}. '
                f'Đừng khen đúng; hãy nhẹ nhàng dẫn em tự kiểm tra lại.'
            )

    # 2) Phép tính "trần" (không có =) — che các span đẳng thức để khỏi trùng
    masked = list(t)
    for s, e in spans:
        for i in range(s, e):
            masked[i] = " "
    masked = "".join(masked)
    seen = {f for f in facts}
    for m in _BARE.finditer(masked):
        if len(facts) >= _MAX_FACTS:
            break
        expr = m.group(0).strip()
        val = _safe_eval(expr)
        if val is None:
            continue
        fact = f'Phép tính "{expr}" có kết quả đúng = {_fmt(val)} (chỉ để Buddy đối chiếu, đừng đọc thẳng đáp án cho học sinh).'
        if fact not in seen:
            seen.add(fact)
            facts.append(fact)

    if not facts:
        return ""
    return (
        "\n\n----- DỮ KIỆN ĐÃ KIỂM CHỨNG (sympy) — CHỈ để Buddy tự đối chiếu, "
        "KHÔNG đọc thẳng con số đáp án cho học sinh -----\n"
        + "\n".join(f"• {f}" for f in facts)
    )
