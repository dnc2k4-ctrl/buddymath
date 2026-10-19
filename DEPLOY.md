# Deploy BuddyMath lên Vercel hoặc Render

BuddyMath có thể chạy trên **một Vercel project**: FastAPI phục vụ API và các
trang trong `buddymath/FE/` trên cùng domain. Vercel hỗ trợ FastAPI qua Python
Functions; database và RAG artifacts cần cấu hình riêng như dưới đây.

## Cách 1 — Vercel (khuyến nghị nếu chuyển hosting)

### 1. Tạo PostgreSQL và chuyển dữ liệu

Vercel Functions không có ổ đĩa bền vững. Tạo PostgreSQL trên Neon (hoặc
PostgreSQL tương thích) trước khi deploy; lấy URL kết nối có SSL. Không dùng
`smartbuddy.db`/SQLite làm production database.

Để **giữ tài khoản, điểm, thanh toán và liên kết hiện tại**, dump toàn bộ
database PostgreSQL hiện trên Render rồi restore vào database Neon đang trống.
Lấy **External Database URL** từ Render (không dùng internal URL), và dùng
`pg_dump`/`pg_restore` cài từ PostgreSQL client tools:

```powershell
$env:SOURCE_DATABASE_URL = Read-Host "Render External Database URL"
$env:TARGET_DATABASE_URL = Read-Host "Neon Database URL"
pg_dump --no-owner --no-privileges --format=custom --file=buddymath.dump $env:SOURCE_DATABASE_URL
pg_restore --no-owner --no-privileges --dbname $env:TARGET_DATABASE_URL .\buddymath.dump
Remove-Item Env:SOURCE_DATABASE_URL, Env:TARGET_DATABASE_URL
```

Không dán URL database vào chat, Git, hoặc commit file dump. Giữ Render/database
cũ nguyên trạng cho đến khi xác nhận đăng nhập, dữ liệu học tập và thanh toán
đã hoạt động với Neon. Nếu chưa truy cập được Render database, cần khôi phục
quyền truy cập trước; đừng khởi chạy production bằng database trống.

### 2. Import repository vào Vercel

1. Vercel Dashboard → **Add New → Project** → import Git repository
   `dnc2k4-ctrl/buddymath`.
2. Để **Root Directory** là repository root (không đặt `buddymath/BE`).
   Entrypoint Python và các dependency đã được cấu hình từ root.
3. Thêm biến môi trường dưới đây cho **Production**, rồi deploy nhánh `main`.

| Biến | Bắt buộc | Ghi chú |
|------|----------|---------|
| `DATABASE_URL` | Có | Neon PostgreSQL URL. Vercel Neon integration tự cấp `DATABASE_POSTGRES_URL`; app tự nhận biến này nếu chưa đặt `DATABASE_URL`. |
| `SECRET_KEY` | Có | Secret riêng, dài/ngẫu nhiên; không dùng giá trị mặc định |
| `GROQ_API_KEY` | Có | API key cho chat và synthesis |
| `JINA_API_KEY` | Có | API key cho embedding truy vấn RAG |
| `CRON_SECRET` | Có | Secret mạnh cho cron; Vercel gửi dưới dạng `Authorization: Bearer ...` |
| `PUBLIC_BASE_URL` | Nên có | Domain production, ví dụ `https://<project>.vercel.app` |
| `ADMIN_PASSWORD` | Khuyến nghị | Mật khẩu mạnh cho `admin@smartbuddy.vn` |
| `BREVO_API_KEY`, `FROM_EMAIL` | Tuỳ chọn | Gửi email báo cáo phụ huynh |

`GROQ_MODEL`, `JINA_MODEL`, `LLM_PROVIDER` và các cấu hình khác dùng mặc định
trong `app/config.py` nếu không đặt. Không bật demo accounts ở production.

### 3. Kiểm tra sau deploy

- `/health` trả `status: ok` và số `indexed_docs` khác 0.
- Kiểm tra đăng nhập bằng tài khoản đã có, điểm số, liên kết phụ huynh và thanh toán.
- Gửi thử một câu hỏi RAG/chat; kiểm tra log Function nếu Jina/Groq báo lỗi.
- Xác nhận email/cron trong Vercel **Cron Jobs**. Báo cáo theo lịch chạy tối đa
  mỗi ngày một lần; không có tiến trình chạy nền liên tục trên Vercel.

### Giới hạn cần biết

- Cơ sở dữ liệu phải là PostgreSQL ngoài Vercel; Vercel Function filesystem tạm
  thời nên không được lưu dữ liệu người dùng hoặc index mới lên đó.
- `faiss.index` và `metadata.pkl` được đóng gói read-only trong deploy. Hai file
  này đã được cho phép theo dõi trong Git. Để thêm/sửa tài liệu RAG, cập nhật
  index bằng môi trường local, commit cả hai artifacts rồi redeploy.
- API `/ingest` và `/ingest/reload` trả `501` trên Vercel vì file ghi trên
  Function không tồn tại bền vững.
- Cron báo cáo chạy một lần/ngày (UTC). Vercel Hobby không thay thế worker
  always-on; không dựa vào vòng lặp nền của Render.
- Không tắt Render hoặc xoá database cũ cho tới khi đã xác nhận dữ liệu Neon.

## Cách 2 — Render (giữ cấu hình hiện tại)

Toàn bộ app chạy trong **một web service** trên Render: backend FastAPI vừa
chạy API vừa trả các trang HTML trong `buddymath/FE/` (same-origin, không CORS,
không cần host FE riêng).

## Render Blueprint (dùng [render.yaml](render.yaml))

1. **Tạo DB bền trước** (xem mục "Tạo Postgres bền với Neon" bên dưới) → có sẵn
   chuỗi `DATABASE_URL`.
2. Push repo này lên GitHub.
3. Render Dashboard → **New → Blueprint** → chọn repo → Render đọc `render.yaml`,
   tạo 1 web service `buddymath`.
4. Điền các **Environment Variables** được đánh dấu `sync:false`:
   - `DATABASE_URL` — **dán chuỗi kết nối Postgres của Neon** (giữ dữ liệu vĩnh viễn)
   - `GROQ_API_KEY` — key Groq
   - `JINA_API_KEY` — key Jina AI (embedding)
   - `PUBLIC_BASE_URL` — điền sau khi biết domain, vd `https://buddymath.onrender.com`
   - (tuỳ chọn) `SMTP_USER`, `SMTP_PASS`, `FROM_EMAIL` để bật email báo cáo
   - `SECRET_KEY` đã được Render tự sinh.
5. **Create** → đợi build. Truy cập:
   - `https://<app>.onrender.com/`            → trang đăng nhập
   - `https://<app>.onrender.com/app`         → app học sinh
   - `https://<app>.onrender.com/parent-portal` → cổng phụ huynh

## Render Web Service thủ công

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
