# Deploy BuddyMath lên Render (1 service — BE phục vụ cả FE)

Toàn bộ app chạy trong **một web service** trên Render: backend FastAPI vừa
chạy API vừa trả các trang HTML trong `buddymath/FE/` (same-origin, không CORS,
không cần host FE riêng).

## Cách 1 — Blueprint (khuyến nghị, dùng [render.yaml](render.yaml))

1. Push repo này lên GitHub.
2. Render Dashboard → **New → Blueprint** → chọn repo → Render đọc `render.yaml`,
   tạo sẵn 1 web service `buddymath` + 1 PostgreSQL `buddymath-db`.
3. Điền các **Environment Variables** được đánh dấu `sync:false`:
   - `GROQ_API_KEY` — key Groq
   - `JINA_API_KEY` — key Jina AI (embedding)
   - `PUBLIC_BASE_URL` — điền sau khi biết domain, vd `https://buddymath.onrender.com`
   - (tuỳ chọn) `SMTP_USER`, `SMTP_PASS`, `FROM_EMAIL` để bật email báo cáo
   - `SECRET_KEY` đã được Render tự sinh; `DATABASE_URL` tự nối từ Postgres.
4. **Create** → đợi build. Truy cập:
   - `https://<app>.onrender.com/`            → trang đăng nhập
   - `https://<app>.onrender.com/app`         → app học sinh
   - `https://<app>.onrender.com/parent-portal` → cổng phụ huynh

## Cách 2 — Tạo Web Service thủ công

| Mục | Giá trị |
|-----|---------|
| Root Directory | `buddymath/BE` |
| Build Command  | `pip install -r requirements.txt` |
| Start Command  | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check   | `/health` |

Rồi thêm Postgres (New → PostgreSQL) và set các env var như Cách 1.

## Lưu ý quan trọng

- **Database**: dùng PostgreSQL (đã wire sẵn). KHÔNG dùng SQLite trên Render —
  filesystem ephemeral nên dữ liệu mất sau mỗi redeploy/restart. Code đọc DB qua
  `DATABASE_URL` nên không phải sửa gì; chỉ cần set biến môi trường.
- **Free Postgres hết hạn sau 30 ngày** (giới hạn Render free). Nâng plan hoặc
  dùng Neon/Supabase rồi dán `DATABASE_URL` nếu cần dùng lâu dài.
- **Free web service ngủ sau ~15 phút** không truy cập; request đầu sau khi ngủ
  sẽ chậm (cold start) vì app ingest lại `data/` (gọi Jina embedding) lúc khởi động.
- **Secret**: chỉ đặt trong Environment Variables của Render. `.env` đã được
  `.gitignore`, không commit lên repo. Các key Groq/Jina từng lộ trong lịch sử
  git — **nên rotate lại**.
- **FE gọi API same-origin**: `login.html`, `parent.html`, `mathbuddy-kids.html`
  tự dùng domain đang chạy, nên không cần cấu hình URL khi deploy.
