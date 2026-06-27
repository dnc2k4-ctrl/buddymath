"""
router.py – Intent Router cho BuddyMath.
Phân loại message của học sinh và xây system prompt tương ứng.

Routes: theory | exercise | solution | hint | chat | unknown
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ─── Route Enum ──────────────────────────────────────────────────────────────
class Route(str, Enum):
    THEORY   = "theory"
    EXERCISE = "exercise"
    SOLUTION = "solution"
    HINT     = "hint"
    CHAT     = "chat"
    UNKNOWN  = "unknown"


@dataclass
class RouteResult:
    route: Route
    confidence: float          # 0.0 – 1.0
    detected_topic: str = ""
    detected_subject: str = ""
    reasoning: str = ""


# ─── Keyword Banks ───────────────────────────────────────────────────────────
_THEORY_KW = [
    r"\bgi[aả]i th[íi]ch\b", r"\bkh[áa]i ni[eệ]m\b", r"\bđ[ịi]nh ngh[ĩi]a\b",
    r"\bth[eế] n[àa]o\b",    r"\bl[àa] g[ìi]\b",       r"\btại sao\b",
    r"\bnguy[eê]n l[ýy]\b",  r"\bl[ýý] thuy[eế]t\b",   r"\bc[ôo]ng th[uứ]c\b",
    r"\bexplain\b",           r"\bdefine\b",             r"\bwhat is\b",
    r"\bhow does\b",          r"\btheory\b",             r"\bconcept\b",
    r"\bformula\b",
]

_EXERCISE_KW = [
    r"\bb[àa]i t[ậa]p\b",    r"\bgi[aả]i b[àa]i\b",    r"\bt[íi]nh\b",
    r"\bt[ìi]m\b",            r"\bchr[uứ]ng minh\b",      r"\bsolve\b",
    r"\bcalculate\b",         r"\bfind\b",               r"\bcompute\b",
    r"\bexercise\b",          r"\bproblem\b",             r"\bquestion\b",
    r"\b\d+\s*[\+\-\*\/\^]\s*\d+\b",
    r"\b\w+\s*=\s*\?",
]

_SOLUTION_KW = [
    r"\bl[ờo]i gi[ảa]i\b",   r"\bc[áa]ch gi[ảa]i\b",   r"\bbước\b",
    r"\bh[ướu]ng d[ẫa]n\b",  r"\bgi[ảa]i chi ti[eế]t\b",
    r"\bstep by step\b",      r"\bsolution\b",           r"\bwork(ed)? (out|through)\b",
    r"\bshow me how\b",       r"\bwalkt?h?rough\b",
]

_HINT_KW = [
    r"\bg[ợo]i [ýy]\b",      r"\bh[ìi]nh d[uứ]ng\b",   r"\bch[ỉi] cho\b",
    r"\bhint\b",              r"\bclue\b",               r"\bnudge\b",
    r"\btip\b",               r"\bpointer\b",
]

_CHAT_KW = [
    r"\bxin ch[àa]o\b",       r"\bch[àa]o\b",           r"\bhi\b",
    r"\bhello\b",             r"\bhey\b",                r"\bth[ắa]c m[ắa]c\b",
    r"\bcảm ơn\b",            r"\bthank\b",              r"\bbye\b",
    r"\btạm bi[eệ]t\b",
]

_SUBJECT_MAP: dict[str, list[str]] = {
    "algebra":      [r"đại số", r"phương tr[ìi]nh", r"algebra", r"equation", r"polynomial"],
    "geometry":     [r"h[ìi]nh h[ọo]c", r"geometry", r"triangle", r"circle", r"angle"],
    "calculus":     [r"gi[ảa]i t[íi]ch", r"đạo h[àa]m", r"t[íi]ch ph[âa]n", r"calculus",
                     r"derivative", r"integral", r"limit"],
    "statistics":   [r"th[ốo]ng k[êe]", r"x[áa]c su[ấa]t", r"statistics", r"probability",
                     r"distribution", r"mean", r"variance"],
    "arithmetic":   [r"s[ốo] h[ọo]c", r"arithmetic", r"fraction", r"decimal", r"percentage"],
    "trigonometry": [r"lượng gi[áa]c", r"sin", r"cos", r"tan", r"trigonometry"],
    "linear_algebra": [r"đại số tuy[eế]n t[íi]nh", r"ma tr[ậa]n", r"matrix",
                       r"vector", r"determinant"],
}


# ─── Router Class ────────────────────────────────────────────────────────────
class RAGRouter:
    """Router rule-based nhẹ, fallback sang LLM classifier khi mơ hồ."""

    def __init__(self, llm_fallback=None):
        self.llm_fallback = llm_fallback

    @staticmethod
    def _score(text: str, patterns: list[str]) -> float:
        hits = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
        return hits / len(patterns) if patterns else 0.0

    @staticmethod
    def _detect_subject(text: str) -> str:
        best_subject, best_hits = "", 0
        for subject, patterns in _SUBJECT_MAP.items():
            hits = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
            if hits > best_hits:
                best_hits, best_subject = hits, subject
        return best_subject

    async def route(
        self,
        message: str,
        topic: str | None = None,
        subject: str | None = None,
    ) -> RouteResult:
        text = message.strip()

        scores: dict[Route, float] = {
            Route.THEORY:   self._score(text, _THEORY_KW),
            Route.EXERCISE: self._score(text, _EXERCISE_KW),
            Route.SOLUTION: self._score(text, _SOLUTION_KW),
            Route.HINT:     self._score(text, _HINT_KW),
            Route.CHAT:     self._score(text, _CHAT_KW),
        }

        best_route = max(scores, key=lambda r: scores[r])
        best_score = scores[best_route]
        detected_subject = subject or self._detect_subject(text)

        if best_score < 0.02 and self.llm_fallback:
            try:
                llm_route_name = await self.llm_fallback(text)
                best_route = Route(llm_route_name.lower())
                best_score = 0.6
                reasoning  = "LLM fallback classifier used."
            except Exception as exc:
                logger.warning(f"LLM fallback failed: {exc}")
                best_route = Route.UNKNOWN
                best_score = 0.0
                reasoning  = "LLM fallback error; defaulting to UNKNOWN."
        elif best_score < 0.02:
            best_route = Route.UNKNOWN
            reasoning  = "No strong signal; below threshold."
        else:
            reasoning = f"Keyword scores: { {r.value: round(s, 3) for r, s in scores.items()} }"

        return RouteResult(
            route=best_route,
            confidence=min(best_score * 20, 1.0),
            detected_topic=topic or "",
            detected_subject=detected_subject,
            reasoning=reasoning,
        )


# ─── System Prompt Factory ───────────────────────────────────────────────────
class PromptBuilder:
    """Xây system prompt theo route đã phát hiện."""

    BASE_SYSTEM = (
        "Bạn là MathBuddy – gia sư toán học AI thân thiện, kiên nhẫn, chính xác và khích lệ học sinh. "
        "Câu hỏi là ngôn ngữ gì thì trả lời bằng ngôn ngữ đó. Ví dụ: Nếu hỏi tiếng việt thì trả lời bằng tiếng việt, nếu hỏi tiếng anh thì trả lời bằng tiếng anh. Sử dụng LaTeX cho công thức ($...$).\n\n"

        "NGUYÊN TẮC BẮT BUỘC KHI XỬ LÝ TÍNH TOÁN CỦA HỌC SINH:\n"
        "0. XÁC MINH TRƯỚC KHI PHẢN HỒI: Trước khi nói bất cứ điều gì về kết quả học sinh, Buddy PHẢI tự tính toán lại bài toán một cách độc lập để xác minh đáp án đúng.\n"
        "1. LUÔN khen ngợi sự cố gắng, thái độ học tập trước (ví dụ: 'Em tính nhanh lắm!', 'Em cố gắng tốt rồi!').\n"
        "2. TUYỆT ĐỐI KHÔNG được nói 'Chính xác!', 'Em làm đúng!', 'Đúng rồi!' khi chưa tự xác minh và chắc chắn 100% kết quả là đúng.\n"
        "3. Nếu nghi ngờ hoặc phát hiện sai (đặc biệt với bài hình học đường thẳng, đoạn thẳng), dùng ngôn ngữ nhẹ nhàng, không khẳng định:\n"
        "   - 'Buddy thấy kết quả em đưa ra hơi khác một chút...'\n"
        "   - 'Em thử kiểm tra lại phép tính xem sao?'\n"
        "   - 'Hãy cùng xem lại bước này nhé...'\n"
        "   - 'Em có thể vẽ hình minh họa và viết lại phép tính không?'\n"
        "4. KHÔNG bao giờ lặp lại hoặc viết lại phép tính sai của học sinh.\n"
        "5. KHÔNG hé lộ đáp án đúng (không nói số nào là đúng).\n"
        "6. Dẫn dắt học sinh tự phát hiện lỗi bằng cách yêu cầu:\n"
        "   - Viết lại phép tính chi tiết từng bước.\n"
        "   - Vẽ hình hoặc mô tả vị trí các điểm.\n"
        "   - Thử thay đổi số liệu để kiểm tra logic.\n"
        "7. Chỉ khen 'Chính xác!' hoặc 'Em làm đúng!' khi đã tự xác minh và học sinh đã tự đưa ra đáp án đúng.\n\n"

        "QUAN TRỌNG:\n"
        "• Không làm bài thay, không sửa hộ, không tính hộ.\n"
        "• Ưu tiên khuyến khích học sinh tự suy nghĩ và tự sửa.\n"
        "• Giọng điệu vui vẻ, kiên nhẫn, như người bạn lớn.\n\n"

        "Cấu trúc trả lời mong muốn:\n"
        "1. Khen nỗ lực của em.\n"
        "2. Nhẹ nhàng gợi ý kiểm tra lại (nếu nghi sai) — không khẳng định sai, không nêu đáp án đúng.\n"
        "3. Đặt câu hỏi dẫn dắt hoặc yêu cầu em giải thích chi tiết bước làm.\n"
        "4. Kết thúc bằng lời động viên tích cực."
    )

    _ROUTE_ADDENDUM: dict[Route, str] = {
        Route.THEORY: (
            "Nhiệm vụ hiện tại: GIẢI THÍCH LÝ THUYẾT.\n"
            "– Trình bày khái niệm rõ ràng, từ đơn giản đến phức tạp.\n"
            "– Đưa ra định nghĩa chính xác và ít nhất một ví dụ minh hoạ.\n"
            "– Nếu có tài liệu tham khảo (context), hãy trích dẫn nguồn.\n"
        ),
        Route.EXERCISE: (
            "Nhiệm vụ hiện tại: HƯỚNG DẪN GIẢI BÀI TẬP.\n"
            "– Phân tích đề bài, xác định dạng toán.\n"
            "– Giải từng bước, giải thích lý do từng bước.\n"
            "– Đóng khung đáp án cuối cùng.\n"
        ),
        Route.SOLUTION: (
            "Nhiệm vụ hiện tại: ĐƯA RA LỜI GIẢI CHI TIẾT.\n"
            "– Trình bày đầy đủ các bước theo thứ tự rõ ràng.\n"
            "– Giải thích cơ sở toán học của từng bước.\n"
            "– Kiểm tra lại đáp án nếu có thể.\n"
        ),
        Route.HINT: (
            "Nhiệm vụ hiện tại: CHO GỢI Ý (KHÔNG tiết lộ lời giải đầy đủ).\n"
            "– Gợi ý bước tiếp theo hoặc công thức cần dùng.\n"
            "– Đặt câu hỏi dẫn dắt để học sinh tự suy nghĩ.\n"
            "– Giữ gợi ý ngắn gọn, không quá 3 câu.\n"
        ),
        Route.CHAT: (
            "Nhiệm vụ hiện tại: TRÒ CHUYỆN THÂN THIỆN.\n"
            "– Hồi đáp tự nhiên, ấm áp.\n"
            "– Khuyến khích học sinh đặt câu hỏi về toán học.\n"
        ),
        Route.UNKNOWN: (
            "Nhiệm vụ hiện tại: YÊU CẦU CHƯA RÕ RÀNG.\n"
            "– Hỏi lại để làm rõ ý định của học sinh.\n"
        ),
    }

    @classmethod
    def build(cls, route: Route, context: str = "", subject: str = "", topic: str = "") -> str:
        prompt = cls.BASE_SYSTEM
        if subject:
            prompt += f"Môn học: {subject}. "
        if topic:
            prompt += f"Chủ đề: {topic}.\n"
        prompt += "\n" + cls._ROUTE_ADDENDUM.get(route, "")
        if context:
            prompt += f"\n===TÀI LIỆU THAM KHẢO===\n{context}\n========================\n"
        return prompt
