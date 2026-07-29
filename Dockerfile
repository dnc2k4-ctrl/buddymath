# ──────────────────────────────────────────────────────────────
#  BuddyMath BE — image chạy FastAPI (phục vụ luôn FE tĩnh)
#  Build context = thư mục gốc repo (nơi chứa file này).
# ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

# libgomp1: faiss-cpu cần lúc chạy. Các gói còn lại dùng wheel sẵn có.
# (Nếu pip build lỗi vì thiếu compiler, thêm build-essential vào dòng dưới.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/BE

# 1) Cài dependencies trước để tận dụng cache layer (chỉ chạy lại khi requirements đổi)
COPY buddymath/BE/requirements.txt .
RUN pip install -r requirements.txt

# 2) Copy mã nguồn. FE đặt CẠNH BE để config.py trỏ đúng FRONTEND_DIR (= /app/FE)
COPY buddymath/BE/ /app/BE/
COPY buddymath/FE/ /app/FE/

EXPOSE 8000

# 1 worker: RAG index nạp trong process; nhiều worker sẽ nạp trùng + tốn RAM.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
