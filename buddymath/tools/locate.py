#!/usr/bin/env python
r"""locate.py — Vẽ lưới toạ độ 5% lên ảnh mockup để chọn box cắt asset chính xác."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "design" / "refs"
OUT = ROOT / "design"

FILES = ["01-profile.png", "04-settings.png", "05-achievements.png", "06-login.png", "11-home.png"]


def main():
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 20)
        small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    except Exception:
        font = small = ImageFont.load_default()
    for f in FILES:
        im = Image.open(REFS / f).convert("RGB")
        w, h = im.size
        d = ImageDraw.Draw(im, "RGBA")
        for i in range(1, 20):
            x = round(w * i / 20)
            d.line([(x, 0), (x, h)], fill=(255, 0, 90, 120), width=1)
            d.text((x + 3, 4), f"{i*5}", fill=(200, 0, 60), font=small)
            y = round(h * i / 20)
            d.line([(0, y), (w, y)], fill=(0, 120, 255, 120), width=1)
            d.text((4, y + 1), f"{i*5}", fill=(0, 80, 200), font=small)
        d.text((w - 300, h - 30), f"{f}  {w}x{h}", fill=(0, 0, 0), font=font)
        im.save(OUT / f"grid-{f}")
        print("✓", OUT / f"grid-{f}")


if __name__ == "__main__":
    main()
