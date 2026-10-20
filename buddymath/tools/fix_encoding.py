"""fix_encoding.py — hoàn nguyên file HTML bị double-encode do Set-Content của PowerShell.

PowerShell (Windows PowerShell 5.1) đã đọc file UTF-8 bằng bảng mã CP1252 rồi ghi lại
thành UTF-8 (kèm BOM). Script đảo ngược: mỗi ký tự -> byte gốc theo CP1252 (kể cả các
byte C1 như U+008D mà bảng cp1252 của Python không có).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = sys.argv[1:] or ["FE/mathbuddy-kids.html"]


def encode_cp1252_lenient(text: str) -> bytes:
    out = bytearray()
    for ch in text:
        o = ord(ch)
        if o < 0x100:
            out.append(o)          # byte gốc (gồm cả C1 controls)
        else:
            try:
                out += ch.encode("cp1252")
            except UnicodeEncodeError:
                out += "?".encode()
    return bytes(out)


for rel in TARGETS:
    p = ROOT / rel
    raw = p.read_bytes()
    text = raw.decode("utf-8-sig")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    original = encode_cp1252_lenient(text)
    try:
        check = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"! {rel}: không hoàn nguyên được ({exc}) — giữ nguyên")
        continue
    p.write_bytes(original)
    print(f"✓ {rel}: {len(raw)} -> {len(original)} bytes")
    print("  Chào em:", "Chào em" in check, "| Lịch sử:", "Lịch sử" in check,
          "| Tư duy:", "Tư duy" in check, "| Hỏi đáp:", "Hỏi đáp" in check)
