# 📚 Hướng dẫn thêm Sách giáo khoa (Toán lớp 3–9) & Tiếng Anh

> SmartBuddy dùng RAG: bạn **thả file tài liệu vào đúng thư mục**, hệ thống tự đọc
> và dùng để dạy. Mình **không tự tạo nội dung sách** (bản quyền) — bạn cần có file
> PDF/DOCX của sách rồi đặt vào theo cấu trúc bên dưới.

## 1) Cấu trúc thư mục (đã dựng sẵn)

```
data/
  toan3/  dai_so/   hinh_hoc/
  toan4/  dai_so/   hinh_hoc/
  toan5/  dai_so/   hinh_hoc/
  toan6/  dai_so/   hinh_hoc/
  toan7/  dai_so/   hinh_hoc/
  toan8/  dai_so/   hinh_hoc/   ← mới tạo, đang trống
  toan9/  dai_so/   hinh_hoc/   ← mới tạo, đang trống
```

- `toanN` = lớp N. `dai_so` = Số học/Đại số. `hinh_hoc` = Hình học.
- Định dạng nhận: **.pdf .docx .txt .md .tex**

## 2) Cách thêm sách (3 bước)

1. **Copy** file sách vào đúng thư mục, ví dụ:
   - `data/toan8/dai_so/Bài 1 - Phân thức đại số.pdf`
   - `data/toan9/hinh_hoc/Bài 1 - Đường tròn.pdf`
   - Đặt tên rõ ràng (gợi ý: `Bài 1 - Tên bài.pdf`) — tên file sẽ hiện trong "Lớp học ảo".
2. **Nạp lại** (không cần khởi động lại server):
   ```
   POST http://localhost:8000/ingest/reload
   ```
   Hoặc khởi động lại server — nó tự ingest file mới khi chạy.
3. **Kiểm tra**: vào "Lớp học ảo" → chọn lớp tương ứng, danh sách bài sẽ xuất hiện.

## 3) Tiếng Anh

Hiện các mục Tiếng Anh (Từ vựng, Hội thoại, Bài tập) đang dùng **AI trực tiếp**
(không đọc từ file). Muốn thêm **giáo trình Tiếng Anh dạng tài liệu** để AI bám sát:

1. Tạo thư mục môn, ví dụ:
   ```
   data/english/vocabulary/
   data/english/grammar/
   data/english/reading/
   ```
2. Thả file vào, rồi cần **nối tính năng Tiếng Anh vào RAG** (việc ở backend) —
   báo mình nếu muốn làm phần này.

## 4) Lưu ý khi deploy (Render)

- Các file index (`faiss.index`, `metadata.pkl`, `.ingested_manifest.json`) được
  tạo tự động và **đã .gitignore** — không commit.
- File sách (.pdf/.docx) **được commit** vào repo → Render build sẽ ingest tự động.
  Nếu sách rất nặng, cân nhắc dùng Git LFS hoặc lưu trữ ngoài.
