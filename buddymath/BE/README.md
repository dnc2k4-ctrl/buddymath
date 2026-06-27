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
