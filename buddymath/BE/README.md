# BuddyMath — Backend (BE)

API FastAPI phân lớp, gộp toàn bộ chức năng: auth/điểm số/báo cáo phụ huynh
(SmartBuddy) + RAG/chat/classroom/synthesis (MathBuddy) trên **một cổng duy nhất**.

## Cấu trúc

```
BE/
  app/
    main.py            # FastAPI app factory + lifespan (ingest data lúc khởi động)
    config.py          # đọc cấu hình từ .env (KHÔNG hardcode secret)
    core/              # database (SQLAlchemy), security (JWT, bcrypt)
    models/            # ORM: User, ParentChildLink, ScoreRecord
    schemas/           # Pydantic DTO
    api/               # routers: pages, auth, scores, parent, chat, catalog, classroom
    services/          # nghiệp vụ: runtime (singletons), auth, email, synthesis
    rag/               # engine (FAISS), router (intent), chunking, data_loader, embedder (Jina)
    llm/               # client (Groq), pipeline
  data/                # tài liệu nguồn data/{subject}/{topic}/*.pdf|docx...
  requirements.txt
  .env.example         # mẫu cấu hình — copy thành .env
  run.bat              # khởi động nhanh trên Windows
```

## Chạy

```bash
cd BE
cp .env.example .env        # rồi điền GROQ_API_KEY, JINA_API_KEY...
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Hoặc trên Windows: nhấp đôi `run.bat`.

- Login:  http://localhost:8000/
- App:    http://localhost:8000/app
- Parent: http://localhost:8000/parent-portal
- Docs:   http://localhost:8000/docs

## Tài khoản và gói học

Mỗi email gắn với một tài khoản duy nhất. Tài khoản miễn phí có 7 ngày trải nghiệm,
tối đa 10 lượt AI mỗi ngày (lượt gửi ảnh cũng được tính vào hạn mức này). Nâng cấp
chính tài khoản đó lên Standard hoặc Premium sẽ mở Cổng Phụ huynh mà không cần tạo
tài khoản trùng email. Standard nhận email tổng hợp hàng tuần; Premium nhận tối đa
một thông báo hoạt động AI mỗi ngày cho mỗi phụ huynh–học sinh đã liên kết.

## Deploy lên Vercel

BuddyMath có thể được deploy như một FastAPI Function duy nhất, phục vụ cả API
lẫn frontend. Xem hướng dẫn đầy đủ ở [DEPLOY.md](../../DEPLOY.md).

- Vercel project phải dùng repository root làm **Root Directory**.
- Cần đặt `DATABASE_URL` trỏ tới PostgreSQL bền vững; SQLite không dùng được
  trên Vercel.
- Hai RAG artifacts `data/faiss.index` và `data/metadata.pkl` được đóng gói
  cùng deploy. Vercel chỉ đọc chúng; cập nhật index rồi redeploy để đổi dữ liệu.
- Cần cấu hình `SECRET_KEY`, `GROQ_API_KEY`, `JINA_API_KEY` và `CRON_SECRET`
  trong Project Environment Variables.

## Biến môi trường chính

| Biến | Bắt buộc | Mô tả |
|------|----------|-------|
| `GROQ_API_KEY`  | ✅ | Key Groq cho LLM (chat, classroom, synthesis) |
| `JINA_API_KEY`  | ✅ | Key Jina AI cho embedding RAG |
| `SECRET_KEY`    | nên đổi | Khóa ký JWT |
| `SMTP_USER/PASS`| tuỳ chọn | Bật email báo cáo phụ huynh |
| `CLAUDE_API_KEY`| tuỳ chọn | Chỉ dùng nếu chuyển proxy sang Claude |

## Ghi chú bảo mật

Secret chỉ đọc từ `.env` (đã được `.gitignore`). Các key Groq/Jina từng bị
commit trong lịch sử git — **nên xoay (rotate) lại** để đảm bảo an toàn.
