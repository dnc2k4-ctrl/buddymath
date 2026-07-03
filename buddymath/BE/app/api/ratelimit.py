"""
ratelimit.py – Rate-limit cho các endpoint gọi LLM (an toàn trẻ em + chặn lạm dụng/chi phí).

Cửa sổ trượt trong bộ nhớ, phân biệt:
  • Đã đăng nhập (có JWT hợp lệ) → hạn mức rộng, khoá theo user id.
  • Khách vãng lai → hạn mức chặt hơn, khoá theo IP.

Không cần DB (chỉ decode JWT), an toàn cho hot-path. Cấu hình qua env RL_*.
Lưu ý: state nằm trong RAM 1 tiến trình — đủ cho 1 instance (Render free); nếu chạy
nhiều worker/instance thì cần Redis. Với quy mô hiện tại là hợp lý.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.security import decode_token


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


# (cửa sổ giây, hạn mức user, hạn mức khách)
_WINDOWS = [
    (60,   _env_int("RL_USER_PER_MIN", 40),  _env_int("RL_ANON_PER_MIN", 12)),
    (3600, _env_int("RL_USER_PER_HOUR", 600), _env_int("RL_ANON_PER_HOUR", 100)),
]
_MAX_WIN = max(w[0] for w in _WINDOWS)

_store: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _identify(request: Request) -> tuple[str, bool]:
    """Trả về (key, is_authenticated)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        payload = decode_token(auth[7:].strip())
        sub = payload.get("sub") if payload else None
        if sub:
            return f"user:{sub}", True
    return f"ip:{_client_ip(request)}", False


async def rate_limit_llm(request: Request) -> None:
    """Dependency: chặn 429 nếu vượt hạn mức. Gắn vào các endpoint gọi LLM."""
    key, is_user = _identify(request)
    now = time.time()
    with _lock:
        dq = _store[key]
        while dq and now - dq[0] > _MAX_WIN:
            dq.popleft()
        for win, ulim, alim in _WINDOWS:
            limit = ulim if is_user else alim
            count = sum(1 for ts in dq if now - ts <= win)
            if count >= limit:
                oldest_in_win = next((ts for ts in dq if now - ts <= win), now)
                retry = max(1, int(win - (now - oldest_in_win)))
                raise HTTPException(
                    status_code=429,
                    detail="Bạn đang gửi hơi nhanh. Nghỉ một chút rồi thử lại nhé! 🙂",
                    headers={"Retry-After": str(retry)},
                )
        dq.append(now)
        if len(_store) > 5000:  # dọn key rỗng để không phình RAM
            for k in [k for k, v in _store.items() if not v]:
                _store.pop(k, None)
