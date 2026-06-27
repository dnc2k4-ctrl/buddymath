# Thư mục tài liệu BuddyMath

## Quy ước

```
data/
  {subject}/        ← tên môn (vd: toan3, toan6)
    {topic}/        ← tên chủ đề (gạch dưới thay dấu cách, vd: dai_so, hinh_hoc)
      bai1.pdf      ← tài liệu (.pdf .docx .txt .md .markdown .tex)
```

## Thêm tài liệu

1. Copy file vào đúng `data/{subject}/{topic}/`
2. Gọi reload (không cần restart): `POST http://localhost:8000/ingest/reload`
3. Xem tổng hợp: `GET http://localhost:8000/topics/{subject}/{topic}/synthesis`

File index (`faiss.index`, `metadata.pkl`, `.ingested_manifest.json`) được sinh
tự động khi ingest và đã được `.gitignore`.
