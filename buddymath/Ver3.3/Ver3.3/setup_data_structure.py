#!/usr/bin/env python3
"""
setup_data_structure.py
Tạo cấu trúc thư mục data/ mẫu và file README hướng dẫn.
Chạy một lần khi setup dự án: python setup_data_structure.py
"""

from pathlib import Path

# ─── Định nghĩa cấu trúc mẫu ─────────────────────────────────────────────────
STRUCTURE = {
    "toan": {
        "dai_so":        "Đại số (phương trình, bất phương trình, hàm số)",
        "hinh_hoc":      "Hình học (tam giác, đường tròn, hình không gian)",
        "giai_tich":     "Giải tích (đạo hàm, tích phân, giới hạn)",
        "thong_ke":      "Thống kê và xác suất",
        "so_hoc":        "Số học (số nguyên, ước bội, phân số)",
        "luong_giac":    "Lượng giác (sin, cos, tan và công thức)",
        "dai_so_tuyen_tinh": "Đại số tuyến tính (ma trận, vector)",
    },
    "vat_ly": {
        "co_hoc":        "Cơ học (lực, chuyển động, năng lượng)",
        "dien_hoc":      "Điện học (điện trường, mạch điện)",
        "quang_hoc":     "Quang học (ánh sáng, thấu kính)",
        "nhiet_hoc":     "Nhiệt học (nhiệt độ, entropi)",
    },
    "hoa_hoc": {
        "hoa_huu_co":    "Hóa hữu cơ (carbon, hydrocarbons)",
        "hoa_vo_co":     "Hóa vô cơ (muối, axit, bazơ)",
        "dien_hoa":      "Điện hóa (pin, điện phân)",
    },
}

README_TEMPLATE = """\
# 📚 Thư mục tài liệu MathBuddy

## Quy ước đặt tên

```
data/
  {{subject}}/         ← tên môn học (dùng tiếng Anh hoặc tiếng Việt không dấu)
    {{topic}}/         ← tên chủ đề (gạch dưới thay dấu cách)
      file1.pdf      ← tài liệu (pdf, docx, txt, md)
      file2.docx
      bai_tap.pdf
```

## Môn học và chủ đề đã tạo

{subject_list}

## Cách thêm tài liệu

1. **Copy file** vào đúng thư mục `data/{{subject}}/{{topic}}/`
2. **Gọi API reload** (không cần restart server):
   ```bash
   curl -X POST http://localhost:8000/ingest/reload
   ```
3. **Xem kết quả tổng hợp**:
   ```bash
   curl http://localhost:8000/topics/{{subject}}/{{topic}}/synthesis
   ```

## Định dạng hỗ trợ

| Định dạng | Extension | Ghi chú |
|-----------|-----------|---------|
| PDF       | `.pdf`    | Dùng PyMuPDF để extract text |
| Word      | `.docx`   | Dùng python-docx, hỗ trợ heading styles |
| Text      | `.txt`    | UTF-8 |
| Markdown  | `.md`     | Hỗ trợ LaTeX trong `$$...$$` |

## API endpoints chính

| Method | Path | Mô tả |
|--------|------|-------|
| GET  | `/subjects` | Danh sách môn học (dynamic) |
| GET  | `/subjects/{{s}}/topics` | Chủ đề của một môn |
| GET  | `/topics/{{s}}/{{t}}/synthesis` | Tổng hợp nội dung theo chủ đề |
| POST | `/topics/synthesis` | Tổng hợp (có thể force reload cache) |
| POST | `/ingest/reload` | Re-scan toàn bộ data/ |
| POST | `/ingest` | Ingest một file đơn lẻ |

## Ví dụ tổng hợp chủ đề

```json
// GET /topics/toan/dai_so/synthesis
{{
  "subject": "toan",
  "topic": "dai_so",
  "status": "ok",
  "chunk_count": 47,
  "source_files": ["phuong_trinh.pdf", "bat_phuong_trinh.docx"],
  "synthesis": {{
    "title": "Đại Số",
    "overview": "Đại số nghiên cứu các phương trình và bất phương trình...",
    "key_concepts": ["Phương trình bậc nhất", "Phương trình bậc hai", "Hệ phương trình"],
    "important_formulas": [
      {{"name": "Nghiệm phương trình bậc 2", "formula": "x = (-b ± √(b²-4ac)) / 2a", "note": "Dùng khi Δ ≥ 0"}}
    ],
    "learning_steps": ["Bước 1: Xác định dạng phương trình", "..."],
    "common_mistakes": ["Quên kiểm tra điều kiện xác định", "..."],
    "example_summary": "Ví dụ điển hình: Giải phương trình x² - 5x + 6 = 0..."
  }}
}}
```
"""


def main():
    data_root = Path("data")
    created_dirs  = []
    subject_lines = []

    for subject, topics in STRUCTURE.items():
        subject_dir = data_root / subject
        subject_lines.append(f"\n### `{subject}/`\n")
        for topic, description in topics.items():
            topic_dir = subject_dir / topic
            topic_dir.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(topic_dir))

            # Tạo file hướng dẫn trong mỗi thư mục topic
            guide = topic_dir / "README.txt"
            guide.write_text(
                f"Thư mục: {subject}/{topic}\n"
                f"Mô tả: {description}\n\n"
                f"Đặt file tài liệu (.pdf, .docx, .txt, .md) vào đây.\n"
                f"Server sẽ tự động ingest khi khởi động hoặc khi gọi /ingest/reload\n",
                encoding="utf-8",
            )
            subject_lines.append(f"- `{topic}/` – {description}")

    # Viết README chính
    readme = data_root / "README.md"
    readme.write_text(
        README_TEMPLATE.format(
            subject_list="\n".join(subject_lines)
        ),
        encoding="utf-8",
    )

    print("✅ Cấu trúc thư mục data/ đã được tạo:")
    for d in created_dirs:
        print(f"   {d}/")
    print(f"\n📄 README: {readme}")
    print("\n🎯 Bước tiếp theo:")
    print("   1. Copy tài liệu PDF/DOCX vào đúng thư mục subject/topic")
    print("   2. python main.py   (server sẽ tự động ingest khi khởi động)")
    print("   3. Gọi GET /topics/{subject}/{topic}/synthesis để xem tổng hợp")


if __name__ == "__main__":
    main()