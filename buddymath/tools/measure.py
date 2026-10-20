r"""
measure.py — Đo màu & kích thước THẬT từ ảnh mẫu (design/refs/*.png) để canh giao diện 1:1.

- Lấy màu chính xác tại các điểm đại diện (nền trang, sidebar, card, banner, chữ...).
- Dò biên dọc/ngang (sidebar, card, banner) bằng chênh lệch màu.
- Xuất JSON để đối chiếu với CSS hiện tại.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "design" / "refs"

# ảnh, các điểm lấy màu (tỉ lệ x,y) đặt tên
POINTS = {
    "11-home.png": [
        ("page_top_left", 0.02, 0.02), ("page_top_right", 0.98, 0.03),
        ("page_bottom", 0.50, 0.97), ("sidebar_bg", 0.02, 0.55),
        ("card_white", 0.50, 0.05), ("hero_img_bg", 0.62, 0.20),
        ("right_card", 0.80, 0.20), ("nav_active", 0.10, 0.50),
        ("nav_text", 0.09, 0.60), ("title", 0.25, 0.045),
    ],
    "09-chat.png": [
        ("page_bg", 0.45, 0.55), ("hero_bg_left", 0.28, 0.12), ("hero_bg_right", 0.72, 0.10),
        ("sidebar_bg", 0.02, 0.55), ("nav_active", 0.10, 0.28), ("input_bar", 0.45, 0.97),
        ("chip_mint", 0.30, 0.36), ("chip_violet", 0.42, 0.36), ("chip_sky", 0.52, 0.36),
    ],
    "02-prompt.png": [
        ("page_bg", 0.45, 0.72), ("banner_left", 0.30, 0.16), ("banner_right", 0.80, 0.12),
        ("note_bg", 0.40, 0.49), ("step1_bg", 0.30, 0.63), ("step2_bg", 0.50, 0.63),
        ("step3_bg", 0.72, 0.63), ("cta_bar", 0.50, 0.79), ("sidebar_bg", 0.02, 0.55),
    ],
    "08-english.png": [
        ("page_bg", 0.45, 0.72), ("banner_bg", 0.40, 0.14), ("card_bg", 0.30, 0.50),
        ("arrow_mint", 0.465, 0.72), ("sidebar_bg", 0.02, 0.55),
    ],
    "07-history.png": [
        ("page_bg", 0.45, 0.80), ("banner_bg", 0.40, 0.14), ("tab_active", 0.30, 0.32),
        ("chip_active", 0.30, 0.42), ("row_bg", 0.45, 0.62), ("sidebar_bg", 0.02, 0.55),
    ],
    "05-achievements.png": [
        ("page_bg", 0.45, 0.78), ("banner_bg", 0.40, 0.18), ("banner_bg2", 0.20, 0.25),
        ("stat_card", 0.20, 0.47), ("sidebar_bg", 0.02, 0.55), ("title", 0.30, 0.18),
    ],
    "01-profile.png": [
        ("page_bg", 0.47, 0.90), ("card_white", 0.30, 0.55), ("card_top_mint", 0.32, 0.28),
        ("plan_hot_border", 0.70, 0.36), ("plan_prem_bg", 0.85, 0.50), ("sidebar_bg", 0.02, 0.55),
        ("title", 0.28, 0.12),
    ],
    "04-settings.png": [
        ("page_bg", 0.47, 0.90), ("card_white", 0.45, 0.45), ("icon_yellow", 0.283, 0.285),
        ("icon_blue", 0.283, 0.41), ("icon_red", 0.283, 0.54), ("icon_violet", 0.283, 0.67),
        ("toggle", 0.845, 0.285), ("sidebar_bg", 0.02, 0.55), ("title", 0.32, 0.125),
    ],
    "10-onboarding.png": [
        ("overlay", 0.10, 0.10), ("modal_bg", 0.45, 0.80), ("box_mint", 0.45, 0.345),
        ("box_violet", 0.45, 0.48), ("box_amber", 0.45, 0.69), ("cta", 0.65, 0.845),
    ],
    "03-parent.png": [
        ("page_bg", 0.50, 0.80), ("header_grad", 0.50, 0.04), ("sidebar_bg", 0.02, 0.55),
        ("welcome_card", 0.55, 0.17), ("tip_card", 0.06, 0.80), ("panel_bg", 0.50, 0.40),
    ],
    "06-login.png": [
        ("page_bg", 0.10, 0.55), ("page_bg2", 0.90, 0.55), ("card_white", 0.50, 0.45),
        ("btn", 0.50, 0.665), ("feature_bar", 0.50, 0.905), ("page_top", 0.50, 0.04),
    ],
}


def px(im: Image.Image, rx: float, ry: float) -> tuple[int, int, int]:
    w, h = im.size
    x = min(w - 1, max(0, int(rx * w)))
    y = min(h - 1, max(0, int(ry * h)))
    r, g, b = im.convert("RGB").getpixel((x, y))
    return (r, g, b)


def hexc(c) -> str:
    return "#%02X%02X%02X" % c


def find_v_edges(im: Image.Image, y_frac: float, x0: float = 0.0, x1: float = 1.0) -> list[int]:
    """Dò biên dọc: các cột có chênh lệch màu lớn so với cột trước."""
    w, h = im.size
    rgb = im.convert("RGB")
    y = int(y_frac * h)
    edges = []
    prev = rgb.getpixel((int(x0 * w), y))
    for x in range(int(x0 * w) + 1, int(x1 * w)):
        cur = rgb.getpixel((x, y))
        d = sum(abs(a - b) for a, b in zip(cur, prev))
        if d > 24:
            edges.append(x)
        prev = cur
    # gộp các biên sát nhau
    out = []
    for e in edges:
        if not out or e - out[-1] > 6:
            out.append(e)
    return out


def find_h_edges(im: Image.Image, x_frac: float, y0: float = 0.0, y1: float = 1.0) -> list[int]:
    w, h = im.size
    rgb = im.convert("RGB")
    x = int(x_frac * w)
    edges = []
    prev = rgb.getpixel((x, int(y0 * h)))
    for y in range(int(y0 * h) + 1, int(y1 * h)):
        cur = rgb.getpixel((x, y))
        d = sum(abs(a - b) for a, b in zip(cur, prev))
        if d > 24:
            edges.append(y)
        prev = cur
    out = []
    for e in edges:
        if not out or e - out[-1] > 6:
            out.append(e)
    return out


def main():
    report = {}
    for name, pts in POINTS.items():
        p = REFS / name
        if not p.exists():
            continue
        im = Image.open(p)
        w, h = im.size
        info = {
            "size": [w, h],
            "colors": {label: hexc(px(im, rx, ry)) for label, rx, ry in pts},
            "v_edges_mid": find_v_edges(im, 0.55),
            "h_edges_left": find_h_edges(im, 0.10),
        }
        report[name] = info
        print(f"\n=== {name} {w}x{h} ===")
        for k, v in info["colors"].items():
            print(f"  {k:<18} {v}")
        print("  biên dọc (y=55%):", info["v_edges_mid"][:12])
        print("  biên ngang (x=10%):", info["h_edges_left"][:12])
    (ROOT / "design" / "measurements.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n→ design/measurements.json")


if __name__ == "__main__":
    main()
