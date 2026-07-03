# 🧠 ARCHITECTURE & LOGIC — SmartBuddy (BuddyMath)

Tài liệu mô tả **cách website hoạt động**: kiến trúc, các luồng xử lý chính, phân
quyền và danh mục API. Xem bản đồ trang ở [SITEMAP.md](SITEMAP.md).

---

## 1. Công nghệ & phân lớp

**Một web service duy nhất** (FastAPI) vừa chạy API, vừa trả các trang HTML trong
`buddymath/FE/` → same-origin, không CORS, không cần host FE riêng.

| Lớp | Thư mục | Nhiệm vụ |
|-----|---------|----------|
| Presentation | `BE/app/api/` | Routers: `pages, auth, scores, parent, chat, catalog, classroom` |
| Nghiệp vụ | `BE/app/services/` | `auth_service`, `synthesis_service`, `email_service`, `runtime` (singletons) |
| Dữ liệu | `BE/app/models/` + `core/database.py` | ORM `User`, `Score` · PostgreSQL (prod) / SQLite (dev) |
| DTO | `BE/app/schemas/` | Pydantic validate request/response |
| AI — RAG | `BE/app/rag/` | `engine`, `chunking`, `embedder` (Jina), `router` · vector index **FAISS** |
| AI — LLM | `BE/app/llm/` | `client` (Groq), `pipeline` |
| Frontend | `FE/*.html` | SPA thuần (HTML/CSS/JS), gọi API cùng origin, lưu JWT ở `localStorage` |

**Bảo mật HTTP** (middleware trong `main.py`): CSP, `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS.

---

## 2. Kiến trúc tổng thể

```mermaid
flowchart LR
  U["🧑‍🎓 Trình duyệt<br/>(login/app/parent/admin.html)"]

  subgraph SVC["⚙️ FastAPI web service (Render, Singapore)"]
    MW["Middleware<br/>CSP + security headers"]
    subgraph R["Routers /api"]
      P["pages"]; A["auth + admin"]; S["scores"]; PA["parent"]; C["chat"]; CAT["catalog"]; CL["classroom"]
    end
    SVCL["services/ (nghiệp vụ)"]
    RAG["rag/ · FAISS index"]
    LLMP["llm/ · pipeline"]
  end

  DB[("🗄️ PostgreSQL<br/>users · scores")]
  GROQ["☁️ Groq LLM"]
  JINA["☁️ Jina embeddings"]

  U -->|HTTPS same-origin| MW --> R
  A --> SVCL --> DB
  S --> DB
  PA --> DB
  C --> LLMP --> GROQ
  C --> RAG
  CAT --> RAG
  RAG --> JINA
  P -->|FileResponse| U
```

---

## 3. Luồng đăng nhập & phân quyền

```mermaid
sequenceDiagram
  participant B as Trình duyệt
  participant API as FastAPI (auth)
  participant DB as PostgreSQL
  B->>API: POST /auth/login {email, password}
  API->>DB: kiểm tra user + hash mật khẩu
  DB-->>API: user (role, grade)
  API-->>B: { token (JWT), user }
  B->>B: lưu sb_token, sb_user vào localStorage
  Note over B: renderAuthState() → hiện khu vực theo role
  alt role = parent
    B->>B: mở /parent-portal
  else role = admin
    B->>B: mở /admin
  else student
    B->>B: ở lại /app
  end
  B->>API: các request sau kèm Authorization: Bearer <token>
  API->>API: deps.py xác thực token + role
```

- Token JWT ký bằng `SECRET_KEY`; FE đính kèm `Authorization: Bearer` cho mọi API cần đăng nhập.
- Khi mở lại trang: `restoreSession()` đọc `localStorage`, gọi `GET /auth/me` để xác thực token còn hiệu lực.

---

## 4. Luồng gia sư AI (Socratic — không giải hộ)

```mermaid
flowchart TD
  Q["Học sinh nhập câu hỏi / ảnh bài"] --> CH{"Có ảnh?"}
  CH -->|có| IMG["POST /chat/image<br/>(vision)"]
  CH -->|không| TXT["POST /chat"]
  IMG --> PIPE["llm/pipeline"]
  TXT --> PIPE
  PIPE --> SYS["System prompt:<br/>LUẬT VÀNG — mỗi câu trả lời<br/>PHẢI kết thúc bằng 1 câu hỏi dẫn dắt"]
  SYS --> GROQ["Groq LLM (streaming)"]
  GROQ --> ANS["Trả lời từng bước + câu hỏi phản biện"]
  ANS --> Q
```

> Triết lý sản phẩm: Buddy **hướng dẫn tư duy**, luôn hỏi lại để học sinh tự tìm ra
> đáp án — không đưa lời giải sẵn.

---

## 5. Luồng kiểm tra → điểm số → thông báo

```mermaid
flowchart LR
  A["Học sinh nộp bài<br/>submitKiemtra() / submitEnglishTest()"] --> B["AI chấm<br/>POST /v1/messages"]
  B --> C["Tính điểm %,<br/>hiện đáp án + lời giải"]
  C --> D["POST /scores/record<br/>lưu vào DB"]
  C --> E["notifyAchievement()<br/>🔔 thông báo thành tích"]
  D --> F["Xem lại ở<br/>Lịch sử điểm số"]
  E --> G["Phụ huynh thấy trong<br/>báo cáo con"]
```

**Trung tâm thông báo (FE, `localStorage` theo từng user):** `pushNotification(type,…)`
được gọi ở các mốc — đăng nhập, đăng xuất, đăng ký, liên kết phụ huynh, hoàn thành
bài kiểm tra (`achievement`/`perfect`/`reminder`), cảnh báo lỗi, chào mừng. Badge đếm
số chưa đọc; mỗi user có kho riêng (`sb_notif_<email>`).

---

## 6. Luồng phụ huynh ↔ học sinh

```mermaid
sequenceDiagram
  participant P as Phụ huynh (/parent-portal)
  participant API as FastAPI (parent)
  participant DB as PostgreSQL
  P->>API: POST /parent/link-child {child_email}
  API->>DB: tạo liên kết parent–student
  P->>API: GET /parent/children
  P->>API: GET /parent/reports/{child_id}?period=week|month
  API->>DB: tổng hợp điểm theo môn/thời gian
  DB-->>API: dữ liệu báo cáo
  API-->>P: biểu đồ + timeline điểm
  P->>API: POST /parent/send-report (email_service)
```

---

## 7. Danh mục API

| Nhóm | Method & Path | Mô tả |
|------|---------------|-------|
| **Pages** | `GET /`, `/app`, `/parent-portal`, `/admin`, `/health` | Trả HTML / health |
| | `GET /robots.txt`, `/sitemap.xml` | SEO (sinh động theo domain) |
| **Auth** | `POST /auth/register` · `POST /auth/login` | Đăng ký / đăng nhập → JWT |
| | `GET /auth/me` · `POST /auth/update-profile` | Thông tin / cập nhật hồ sơ |
| **Admin** | `GET /admin/users` · `GET /admin/stats` | Danh sách user / thống kê |
| | `POST /admin/users` · `PATCH /admin/users/{id}` | Tạo / sửa user |
| | `POST /admin/users/{id}/reset-password` · `DELETE /admin/users/{id}` | Reset mật khẩu / xoá |
| **Scores** | `POST /scores/record` · `GET /scores/history` · `GET /scores/summary` | Lưu / xem / tổng hợp điểm |
| **Parent** | `POST /parent/link-child` · `GET /parent/children` | Liên kết / danh sách con |
| | `GET /parent/reports/{child_id}` · `POST /parent/send-report` | Báo cáo / gửi email |
| **Chat (AI)** | `POST /chat` · `POST /chat/stream` · `POST /chat/image` · `POST /v1/messages` | Hỏi đáp / streaming / vision / chấm bài |
| **Catalog** | `GET /subjects` · `GET /subjects/{s}/topics` | Danh mục môn / chủ đề |
| | `GET /topics/{s}/{t}/content` · `.../chunks` · `.../synthesis` | Nội dung / RAG chunks / tổng hợp |
| | `POST /ingest` · `POST /ingest/reload` | Nạp tài liệu vào FAISS |
| **Classroom** | `GET /classroom/{s}/{t}/files` · `POST /classroom/lesson` | Tài liệu lớp / bài giảng |

---

## 8. Mô hình dữ liệu (rút gọn)

```mermaid
erDiagram
  USER ||--o{ SCORE : "làm bài"
  USER ||--o{ USER : "parent ⟶ child (liên kết)"
  USER {
    uuid id
    string email
    string username
    string role "student|parent|admin"
    int grade
    string password_hash
  }
  SCORE {
    uuid id
    uuid user_id
    string subject "Toán|Tiếng Anh"
    string topic
    int score
    int total
    int pct
    string feedback
    datetime created_at
  }
```

> ⚠️ Trên Render dùng **PostgreSQL** (bền), không dùng SQLite (filesystem ephemeral →
> mất dữ liệu mỗi lần redeploy). Xem [DEPLOY.md](DEPLOY.md).
