# 🗄️ MathBuddy – Hướng dẫn tích hợp MSSQL Auth & Monitor

## Tổng quan các file mới

| File | Mô tả |
|------|--------|
| `db.py` | Module kết nối MSSQL, quản lý accounts/sessions/logs |
| `auth_routes.py` | FastAPI router cho login/logout/monitor API |
| `monitor.html` | Trang dashboard admin (đặt cùng thư mục với main.py) |
| `auth_patch.js` | JS tích hợp auth vào mathbuddy-kids.html |
| `.env` | Biến môi trường (có thêm cấu hình DB) |
| `requirements.txt` | Cập nhật thêm `pymssql` |

---

## Bước 1 – Cài đặt thư viện

```bash
pip install pymssql>=2.3.0
# Hoặc cài toàn bộ:
pip install -r requirements.txt
```

> **Lưu ý:** `pymssql` không cần ODBC driver, cài được ngay trên Windows/Linux/macOS.

---

## Bước 2 – Cập nhật `.env`

Thêm các dòng sau vào file `.env`:

```env
DB_HOST=192.168.0.101
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=Abcd1234@
DB_NAME=mathbuddy
```

---

## Bước 3 – Sửa `main.py`

### 3.1 Thêm import (đầu file, sau các import hiện có):

```python
from auth_routes import router as auth_router
import db
```

### 3.2 Đăng ký router (sau dòng `app = FastAPI(...)`):

```python
app.include_router(auth_router)
```

### 3.3 Khởi tạo DB trong lifespan (thêm vào đầu hàm `lifespan`):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_engine, pipeline, data_loader

    # ✅ THÊM ĐOẠN NÀY
    try:
        db.init_db()
        logger.info("✅ Database MSSQL đã sẵn sàng.")
    except Exception as exc:
        logger.warning(f"⚠ DB init thất bại (tiếp tục không có DB): {exc}")

    logger.info("🚀 Khởi động MathBuddy backend...")
    rag_engine  = RAGEngine()
    pipeline    = MathBuddyPipeline(rag_engine=rag_engine)
    # ... phần còn lại giữ nguyên
```

### 3.4 Log chat vào DB (trong endpoint `/chat`):

Tìm đoạn return trong `async def chat(req: ChatRequest)` và thêm log:

```python
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng.")
    try:
        result = await pipeline.run(
            message=req.message,
            session_id=req.session_id,
            topic=req.topic,
            subject=req.subject,
        )

        # ✅ THÊM ĐOẠN NÀY
        try:
            username = req.session_id.split('_')[0] if '_' in req.session_id else ""
            db.log_chat(
                session_id=req.session_id,
                message=req.message,
                answer=result.get("answer", ""),
                route=result.get("route", ""),
                subject=req.subject or "",
                topic=req.topic or "",
                model=pipeline.llm.model,
                username=username,
            )
        except Exception as db_exc:
            logger.warning(f"DB log error: {db_exc}")

        return ChatResponse(...)
```

---

## Bước 4 – Tích hợp auth vào `mathbuddy-kids.html`

Thêm thẻ `<script>` vào cuối `mathbuddy-kids.html`, **trước** `</body>`:

```html
<!-- Auth DB Integration -->
<script src="auth_patch.js"></script>
```

Hoặc nếu muốn inline, copy toàn bộ nội dung `auth_patch.js` vào trước thẻ `</script>` cuối cùng trong file.

> **Kết quả:** Trang MathBuddy sẽ có thêm tab **"🔑 Tài khoản"** trong modal đăng nhập,
> cho phép đăng nhập bằng username/password thật từ MSSQL.

---

## Bước 5 – Đặt `monitor.html` đúng chỗ

```
project/
├── main.py
├── auth_routes.py      ← file mới
├── db.py               ← file mới
├── monitor.html        ← file mới (đặt cùng thư mục main.py)
├── mathbuddy-kids.html
├── auth_patch.js       ← file mới (cùng thư mục, hoặc inline)
├── .env
└── requirements.txt
```

---

## Cấu trúc Database (tự động tạo khi khởi động)

### Bảng `accounts`
| Cột | Kiểu | Mô tả |
|-----|------|--------|
| id | INT IDENTITY | Primary key |
| username | NVARCHAR(64) | Unique |
| password_hash | NVARCHAR(256) | SHA-256 + salt |
| role | NVARCHAR(16) | `student` / `teacher` / `admin` |
| display_name | NVARCHAR(128) | Tên hiển thị |
| is_active | BIT | Trạng thái kích hoạt |
| login_count | INT | Số lần đăng nhập |
| total_chats | INT | Số tin nhắn đã gửi |

### Bảng `chat_logs`
| Cột | Mô tả |
|-----|--------|
| session_id | ID phiên chat |
| username | Người dùng |
| message | Tin nhắn gốc |
| answer | Câu trả lời AI |
| route | theory/exercise/solution/hint/chat |
| subject / topic | Môn học / chủ đề |
| duration_ms | Thời gian phản hồi |

### Bảng `login_logs`
Ghi lại mọi lần login/logout/failed kèm IP và user-agent.

### Bảng `sessions`
Token phiên đăng nhập (hết hạn sau 24h).

---

## Tài khoản mặc định (seed tự động)

| Username | Password | Role | Dùng cho |
|----------|----------|------|----------|
| `admin` | `Admin@123` | admin | Quản trị hệ thống |
| `monitor` | `Monitor@123` | admin | Truy cập monitor.html |
| `student1` | `Student@123` | student | Tài khoản học sinh mẫu |

> ⚠️ **Đổi mật khẩu ngay sau khi deploy!**

---

## Truy cập Monitor

- URL: `http://your-server:8000/monitor`
- Đăng nhập bằng tài khoản role `admin` (vd: `admin` / `Admin@123`)
- Dashboard tự động làm mới mỗi 30 giây

### Tính năng Monitor:
- 📊 **Dashboard**: Tổng số user, chat hôm nay, đăng nhập, tốc độ phản hồi
- 📈 **Biểu đồ**: Chat 7 ngày, phân bổ route (theory/exercise/...)
- 👥 **Tài khoản**: Xem, tạo, bật/tắt tài khoản
- 💬 **Log Chat**: Tìm kiếm theo user/route/ngày
- 🔐 **Log Đăng nhập**: Theo dõi thất bại đăng nhập

---

## API Endpoints mới

| Method | Path | Mô tả |
|--------|------|--------|
| POST | `/auth/login` | Đăng nhập, nhận token |
| POST | `/auth/logout` | Đăng xuất |
| GET | `/auth/me` | Thông tin user hiện tại |
| GET | `/auth/check` | Kiểm tra token còn hạn |
| GET | `/monitor` | Trang monitor (HTML) |
| GET | `/monitor/stats` | Dashboard stats (admin) |
| GET | `/monitor/accounts` | Danh sách tài khoản (admin) |
| POST | `/monitor/accounts` | Tạo tài khoản (admin) |
| PUT | `/monitor/accounts/{id}/status` | Bật/tắt tài khoản (admin) |
| GET | `/monitor/chat-logs` | Log chat với filter (admin) |
| GET | `/monitor/login-logs` | Log đăng nhập (admin) |
