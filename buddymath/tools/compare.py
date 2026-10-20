r"""compare.py — Ghép ảnh mẫu và ảnh chụp hiện tại cạnh nhau để so từng pixel.

Chạy:
  venv\Scripts\python.exe tools\compare.py --shots ..\shots\v3 --out ..\design
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "design" / "refs"

# tên ảnh chụp -> ảnh mẫu
PAIRS = {
    "home": "11-home.png",
    "buddy": "09-chat.png",
    "prompt": "02-prompt.png",
    "english": "08-english.png",
    "history": "07-history.png",
    "achievements": "05-achievements.png",
    "profile": "01-profile.png",
    "settings": "04-settings.png",
    "onboarding": "10-onboarding.png",
    "parent": "03-parent.png",
    "login": "06-login.png",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", required=True)
    ap.add_argument("--out", default=str(ROOT / "design"))
    ap.add_argument("--height", type=int, default=760)
    args = ap.parse_args()
    shots = Path(args.shots)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 26)
    except Exception:
        font = ImageFont.load_default()

    for name, ref in PAIRS.items():
        shot = shots / f"{name}.png"
        refp = REFS / ref
        if not shot.exists() or not refp.exists():
            continue
        a = Image.open(refp).convert("RGB")
        b = Image.open(shot).convert("RGB")
        h = args.height
        aw = round(a.width * h / a.height)
        bw = round(b.width * h / b.height)
        a = a.resize((aw, h), Image.LANCZOS)
        b = b.resize((bw, h), Image.LANCZOS)
        canvas = Image.new("RGB", (aw + bw + 30, h + 44), (245, 250, 248))
        canvas.paste(a, (0, 44))
        canvas.paste(b, (aw + 30, 44))
        d = ImageDraw.Draw(canvas)
        d.text((4, 8), f"MẪU  {ref}", fill=(200, 30, 80), font=font)
        d.text((aw + 34, 8), f"HIỆN TẠI  {name}.png", fill=(20, 110, 90), font=font)
        canvas.save(out / f"compare-{name}.png")
        print(f"✓ design/compare-{name}.png  ({a.width}x{h} | {b.width}x{h})")


if __name__ == "__main__":
    main()
