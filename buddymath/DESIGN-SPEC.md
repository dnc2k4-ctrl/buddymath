# SmartBuddy — Design system v2 (Mint) + phạm vi công việc

Mục tiêu: dựng lại **toàn bộ** giao diện web SmartBuddy (thư mục `FE/`) khớp 11 ảnh mẫu trong
`design/refs/`, **fit đúng 1 khung hình, KHÔNG có thanh cuộn trang** (kể cả dọc và ngang),
kích thước/căn chỉnh chuẩn, giữ nguyên 100% logic JS/API hiện có.

Ảnh mẫu (view ở 100%, kích thước gốc 1672×941 / 1859×846 / 1871×841):

| File | Màn hình | Trang/khung |
|---|---|---|
| `design/refs/06-login.png` | Đăng nhập | `login.html` |
| `design/refs/11-home.png` | Trang chủ dashboard | `/app` – view Trang chủ |
| `design/refs/09-chat.png` | Hỏi đáp với Buddy | `/app` – panel Hỏi đáp |
| `design/refs/02-prompt.png` | Tư duy đặt câu hỏi | `/app` – panel prompt-playground |
| `design/refs/08-english.png` | Tiếng Anh | `/app` – panel english_hub |
| `design/refs/07-history.png` | Lịch sử học tập | `/app` – panel score_history |
| `design/refs/05-achievements.png` | Thành tích | `/app` – openAchievements() |
| `design/refs/01-profile.png` | Hồ sơ cá nhân | `/app` – openProfile() |
| `design/refs/04-settings.png` | Cài đặt | `/app` – openSettings() |
| `design/refs/10-onboarding.png` | Modal hướng dẫn nhanh | `/app` – openLearningGuide() |
| `design/refs/03-parent.png` | Cổng phụ huynh | `parent.html` (`/parent-portal`) |

Ngoài 11 màn trên, các trang `admin.html`, `404.html`, `terms.html`, `privacy.html`,
các panel Toán / Kỹ năng sống / classroom / hướng dẫn / chat đang trò chuyện cũng phải theo
cùng design system (dùng lại component, không tự phát minh style mới).

---

## 1. Design tokens

Dùng file dùng chung `FE/assets/mint-v2.css` (do Lead quản lý) — **đã import sẵn** vào các trang.
Không sửa file này; nếu cần style riêng cho trang của mình thì viết CSS scoped trong file của mình
(prefix `lp-`, `pp-`, `sp-`…).

```
/* Màu */
--mint-50:#F1FBF7;  --mint-100:#E4F8F1; --mint-200:#C9F2E6;
--mint-300:#8FE9D4; --mint-400:#4FD9B8; --mint-500:#2FCBA6;  /* primary */
--mint-600:#1DB894; --mint-700:#11917A; --mint-800:#0B6E5C;
--ink:#102A43;      /* heading navy */
--ink-2:#16324F;    --ink-3:#40566B;
--muted:#6B7C93;    /* body/subtitle */
--muted-2:#93A3B5;  /* hint */
--line:#E4F1EC;     /* divider */
--white:#FFFFFF;
--sky:#4E8CFF;      --sky-bg:#EAF2FF;
--violet:#A55EEA;   --violet-bg:#F3ECFF;
--amber:#FFB020;    --amber-bg:#FFF6E2;
--peach:#FF8A5B;    --peach-bg:#FFEFE8;
--rose:#FF6B9D;     --rose-bg:#FFEAF2;
--danger:#EF5B5B;   --danger-bg:#FFF0F0;
--mint-grad: linear-gradient(135deg,#4FDDBB 0%,#23C7A3 55%,#12B994 100%);
--page-grad: radial-gradient(1200px 620px at 18% -10%, #EAFBF5 0%, rgba(234,251,245,0) 60%),
             linear-gradient(165deg,#E6FAF3 0%,#DFF7F1 38%,#EFFCF8 100%);
/* Bo góc */
--r-sm:12px; --r-md:16px; --r-lg:20px; --r-xl:26px; --r-pill:999px;
/* Đổ bóng */
--sh-1:0 6px 18px rgba(16,80,70,.06);
--sh-2:0 14px 34px rgba(16,80,70,.10);
--sh-3:0 24px 60px rgba(16,80,70,.16);
```

Font: `'Baloo 2'` cho heading/số lớn (weight 700–800), `'Nunito'` cho body (600–900).
Font đã load sẵn từ Google Fonts ở mọi trang.

## 2. Quy tắc "fit 1 màn hình, không thanh cuộn" (BẮT BUỘC)

- `html, body { height:100%; overflow:hidden; }` cho mọi trang app/portal/login.
- Khung ngoài: `height:100dvh` (fallback 100vh), không dùng `min-height` gây tràn.
- Mọi kích thước lớn dùng đơn vị theo chiều cao màn hình, **không hardcode px cố định**:
  `clamp(min, Xvh, max)` cho font-size, padding, gap, radius, kích thước ảnh.
  Reference: 1vh = 9.41px ở 1672×941. Ví dụ: tít 34px → `clamp(22px, 3.6vh, 40px)`.
- Nội dung dài (danh sách lịch sử, điều khoản…) phải co giãn trong khung: dùng grid/flex,
  `overflow:hidden`, phân trang/rút gọn — **không để trang sinh scrollbar**.
- Ảnh: luôn có `width/height` hoặc `aspect-ratio` + `object-fit:contain` để không nhảy layout.
- Kiểm chứng: `python tools/shot.py --out ..\shots\<ten> --only <man>` in ra `OK/SCROLL`.
  Chỉ nhận khi tất cả là `OK` và ảnh chụp khớp ảnh mẫu.

## 3. Khung chung màn hình học sinh (sidebar + main)

- Nền trang: `--page-grad` + lớp trang trí: mây trắng mờ (radial-gradient trắng), lá mint ở
  2 góc dưới (`blur` + `border-radius`), vài ngôi sao vàng nhỏ + máy bay giấy (glyph, opacity thấp).
  Trang trí nằm sau nội dung, `pointer-events:none`.
- **Sidebar**: card trắng `width: clamp(272px, 20vw, 360px)`, `margin: clamp(10px,1.6vh,18px)`,
  `border-radius: var(--r-xl)`, `box-shadow: var(--sh-2)`.
  - Logo: ảnh `/images/logogiaodienmoi.jpg` (nền trắng, bo 18px) rộng `clamp(112px,7.6vw,150px)`
    đặt giữa, cách mép trên ~22px; dưới logo là đường kẻ `--line`.
  - Nav: item cao `clamp(38px,4.6vh,48px)`, padding-x 14px, gap 4–6px, radius 14px,
    icon emoji 20–22px, chữ 15–16px/700 màu `--ink-2`.
  - Item active: nền `--mint-grad`, chữ trắng, shadow mint; các item còn lại trong suốt.
  - Cuối sidebar: dòng chữ "Cùng Buddy chinh phục tri thức!" nghiêng, màu `--mint-700`, 13–14px.
- **Main**: chiếm phần còn lại, `padding: clamp(12px,2vh,22px) clamp(14px,1.6vw,26px)`.
  - Top-right luôn có: nút chuông tròn trắng 42–46px (chấm đỏ), pill tài khoản trắng
    (avatar tròn mint + tên + ▾). Đặt `position:absolute; top:clamp(10px,1.8vh,20px); right:...`
    trong main, z-index 30.
  - Header màn hình (greeting): `--ink` Baloo 800, size theo ảnh mẫu; subtitle `--muted` 15–16px.
- **Card** trắng: `border-radius: var(--r-xl)`, `box-shadow: var(--sh-2)`,
  viền `1px solid rgba(47,203,166,.10)`, padding trong 20–26px.
- **Banner**: gradient mint nhạt (`linear-gradient(120deg,#BFF3E6,#DDF9F1 55%,#CFF6EC)`),
  radius `--r-xl`, viền trắng mờ, mascot cut-out (PNG trong suốt) đặt mép phải.
- **Nút**: primary `--mint-grad`, chữ trắng 900, radius 14–16px, shadow mềm; ghost = trắng +
  viền `--mint-300` + chữ `--mint-700`; danger = `--danger-bg` + chữ `--danger`.
- **Chip**: pill trắng/nền nhạt, viền mint, chữ 13–14px/800; active = `--mint-grad` chữ trắng.
- **Vòng tròn mũi tên** cuối card: 30–38px, nền màu chủ đề, icon → trắng.

## 4. Yêu cầu riêng từng màn

### 4.1 `login.html` (owner: login-page) — mẫu `06-login.png`
Bố cục: nền mint + mây + đồ trang trí (cây/bút chì trái, quả địa cầu phải, sách, sao).
Logo `logogiaodienmoi.jpg` (nền trắng bo 22px) đặt **phía trên** card, căn giữa (~180–200px rộng).
Card trắng rộng `clamp(460px, 36vw, 620px)`, radius 30px, padding ~40px 52px, gồm:
- Tiêu đề "Chào mừng trở lại! 👋" 34px Baloo 800 `--ink`, căn giữa; phụ đề 16px `--muted`.
- 2 tab "🏫 Khu vực học sinh" | "👨‍👩‍👧 Khu vực phụ huynh" (tab active mint đậm + gạch chân,
  phân cách bằng dấu `|`), bấm được (giữ nguyên logic đăng nhập phụ huynh hiện có nếu có).
- Email / Mật khẩu: label 14px 800, input cao 54px radius 14px viền `--line`, icon trái.
- "☑ Ghi nhớ đăng nhập" + "Quên mật khẩu?" (link mint).
- Nút "Đăng nhập →" cao 58px, `--mint-grad`, radius 16px, chữ 20px 900.
- "Chưa có tài khoản? Đăng ký ngay" căn giữa.
Dưới card: thanh trắng radius 20px với 3 mục (An toàn & bảo mật / Học tập hiệu quả / Tiến bộ mỗi ngày)
+ dòng "Điều khoản · Bảo mật". Toàn bộ nằm gọn trong 1 màn hình.
Giữ nguyên: id form, API `/auth/login`, các modal đăng ký/quên mật khẩu hiện có, logic
`?portal=parent`, redirect `/app`.

### 4.2 `parent.html` (owner: parent-page) — mẫu `03-parent.png`
Bố cục riêng: header bar gradient mint cao ~72px (logo trắng + wordmark bên trái, pill "Phụ huynh"
bên phải); thân 2 cột:
- Cột trái ~`clamp(300px,23vw,392px)`: label "👥 CON EM TÔI"; card con đang chọn (viền mint,
  avatar, tên, "Lớp 5 · email", 2 pill "Tuần này: N bài" / "Tổng: N"); label
  "🔗 LIÊN KẾT TÀI KHOẢN HỌC SINH"; card nhập email + nút "+ Liên kết"; card mascot kem
  "Cùng con học mỗi ngày!".
- Cột phải: banner "Xin chào, <tên>! 👋" + mô tả, phần nội dung báo cáo bên dưới; khi chưa chọn
  con/biểu đồ trống thì hiện empty state: mascot + "Chọn con em để xem báo cáo" + phụ đề.
Giữ nguyên toàn bộ JS gọi API phụ huynh, id DOM mà JS dùng. Không có thanh cuộn trang.

### 4.3 Trang tĩnh (owner: static-pages) — `admin.html`, `404.html`, `terms.html`, `privacy.html`
Không có ảnh mẫu riêng: dùng lại tokens/component ở trên (nền mint + card trắng + nút mint).
- `terms.html`, `privacy.html`: **phải fit 1 màn hình** — bố cục 2 cột (hero/tiêu đề trái, nội dung
  phải chia mục ngắn gọn), cỡ chữ vừa phải để toàn bộ nội dung hiện trong 1 khung, không scrollbar.
- `404.html`: căn giữa 1 màn hình, mascot + "Ôi! Trang này không tồn tại" + nút về trang chủ.
- `admin.html`: giữ nguyên toàn bộ logic đăng nhập/quản trị; restyle bảng/ô tìm kiếm/nút theo tokens,
  các khối dài dùng cuộn trong khung (không cuộn trang).

## 5. Quy trình & kiểm chứng

Chụp ảnh tự động (tự chọn cổng, chạy song song được):
```
cd C:\Users\Admin\Downloads\AI Web\buddymath\buddymath
venv\Scripts\python.exe tools\shot.py --out ..\shots\<ten-ban> --only login,parent
```
- `login` = `login.html`, `parent` = `/parent-portal` (đã tự đăng nhập demo), `admin`, `terms`,
  `privacy`, `404`, và các màn app: `home,onboarding,buddy,prompt,math,english,lifeskills,
  history,achievements,profile,settings,guide`.
- Ảnh lưu ở `../shots/<ten-ban>/<man>.png`, log in ra `OK`/`SCROLL` kèm `overflows`.
- Chỉ báo xong khi: ảnh khớp mẫu, mọi màn `OK`, không lỗi console.

Tài khoản demo: `student@demo.vn / demo123`, `parent@demo.vn / demo123` (đã seed).

## 6. Ranh giới file (không giẫm lên nhau)

| Owner | Được sửa |
|---|---|
| Lead | `FE/assets/mint-v2.css`, `FE/assets/app-v2.css`, `FE/mathbuddy-kids.html`, `FE/assets/mathbuddy-kids.js` |
| login-page | `FE/login.html` |
| parent-page | `FE/parent.html` |
| static-pages | `FE/admin.html`, `FE/404.html`, `FE/terms.html`, `FE/privacy.html` |

Không ai được sửa file của owner khác, không sửa `FE/images/*`, không sửa `BE/*`, không sửa
`tools/shot.py`. Nếu cần ảnh mascot mới: báo Lead.
