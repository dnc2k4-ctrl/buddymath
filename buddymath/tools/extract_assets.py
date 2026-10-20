#!/usr/bin/env python
r"""
extract_assets.py — "Sinh" bộ asset hình minh họa 3D từ chính ảnh mockup của dự án.

Ý tưởng: các ảnh mẫu trong design/refs/*.png có độ phân giải cao và chứa đúng
những hình minh họa (mascot đọc sách, chồng sách, cây, địa cầu, icon 3D...) mà
thiết kế cần. Script cắt vùng ảnh (box theo tỉ lệ), ước lượng màu nền (trắng
hoặc gradient) rồi tách nền thành alpha, tự trim sát viền nội dung, lưu PNG
trong suốt vào FE/images/v2/.

Chạy:
    venv\Scripts\python.exe tools\extract_assets.py
    venv\Scripts\python.exe tools\extract_assets.py --sheet   # kèm contact sheet
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "design" / "refs"
OUT = ROOT / "FE" / "images" / "v2"

# name, file, box=(x0,y0,x1,y1) tỉ lệ 0..1, mode=auto|white|gradient, blob=chỉ giữ cụm lớn nhất
ASSETS = [
    # ── Trang chủ: 4 mascot trong thẻ danh mục (giữ nguyên nền thẻ) ─────────
    ("cat-math-plate",    "11-home.png",      (0.229, 0.648, 0.334, 0.826), "plate", False),
    ("cat-english-plate", "11-home.png",      (0.347, 0.648, 0.452, 0.826), "plate", False),
    ("cat-life-plate",    "11-home.png",      (0.462, 0.648, 0.567, 0.826), "plate", False),
    ("cat-think-plate",   "11-home.png",      (0.580, 0.648, 0.685, 0.826), "plate", False),
    ("cat-math",        "11-home.png",        (0.235, 0.650, 0.330, 0.800), "gradient", True),
    ("cat-english",     "11-home.png",        (0.345, 0.650, 0.440, 0.800), "gradient", True),
    ("cat-life",        "11-home.png",        (0.458, 0.650, 0.553, 0.800), "gradient", True),
    ("cat-think",       "11-home.png",        (0.573, 0.650, 0.668, 0.800), "gradient", True),
    # icon trong ô tròn màu (giữ nguyên ô tròn, nền card trắng)
    ("ic-star3d",       "11-home.png",        (0.716, 0.495, 0.763, 0.578), "white", False),
    ("ic-target3d",     "11-home.png",        (0.716, 0.570, 0.763, 0.653), "white", False),
    ("ic-flame3d",      "11-home.png",        (0.716, 0.645, 0.763, 0.728), "white", False),

    # ── Hỏi đáp với Buddy: mascot đọc sách + chồng sách + chữ viết tay ──────
    ("chat-hero-art",   "09-chat.png",        (0.615, 0.100, 0.790, 0.600), "gradient", True),

    # ── Tiếng Anh: hero art + 3 minh họa thẻ (giữ nền trắng của card) ───────
    ("eng-hero-art",    "08-english.png",     (0.725, 0.070, 0.970, 0.395), "gradient", False),
    ("eng-card-vocab",  "08-english.png",     (0.245, 0.415, 0.370, 0.600), "plate", False),
    ("eng-card-speak",  "08-english.png",     (0.495, 0.415, 0.620, 0.600), "plate", False),
    ("eng-card-test",   "08-english.png",     (0.745, 0.415, 0.870, 0.600), "plate", False),

    # ── Tư duy đặt câu hỏi: hero art ───────────────────────────────────────
    ("prompt-hero-art", "02-prompt.png",      (0.595, 0.055, 0.855, 0.565), "gradient", False),

    # ── Thành tích: hero art + icon thống kê (ô tròn) + art empty state ────
    ("ach-hero-art",    "05-achievements.png", (0.710, 0.100, 0.888, 0.292), "gradient", False),
    ("ic-trophy3d",     "05-achievements.png", (0.238, 0.325, 0.282, 0.418), "white", False),
    ("ic-star3d-2",     "05-achievements.png", (0.493, 0.325, 0.537, 0.418), "white", False),
    ("ic-flame3d-2",    "05-achievements.png", (0.736, 0.325, 0.780, 0.418), "white", False),
    ("ach-empty-art",   "05-achievements.png", (0.498, 0.515, 0.632, 0.782), "gradient", False),
    ("ic-trophy-title", "05-achievements.png", (0.238, 0.105, 0.286, 0.190), "gradient", True),

    # ── Cài đặt: mascot góc phải + 4 icon dòng (ô màu) ─────────────────────
    ("set-hero-art",    "04-settings.png",    (0.745, 0.070, 0.865, 0.240), "gradient", False),
    ("ic-bell3d",       "04-settings.png",    (0.266, 0.256, 0.304, 0.323), "white", False),
    ("ic-speaker3d",    "04-settings.png",    (0.266, 0.390, 0.304, 0.457), "white", False),
    ("ic-palette3d",    "04-settings.png",    (0.266, 0.522, 0.304, 0.589), "white", False),
    ("ic-globe3d",      "04-settings.png",    (0.266, 0.654, 0.304, 0.721), "white", False),

    # ── Hồ sơ cá nhân: art thẻ + icon dòng + icon gói ──────────────────────
    ("prof-art",        "01-profile.png",     (0.405, 0.205, 0.497, 0.405), "gradient", False),
    ("ic-mail3d",       "01-profile.png",     (0.239, 0.445, 0.263, 0.485), "white", True),
    ("ic-user3d",       "01-profile.png",     (0.239, 0.515, 0.263, 0.555), "white", True),
    ("ic-crown3d",      "01-profile.png",     (0.239, 0.585, 0.263, 0.625), "white", True),
    ("ic-lock3d",       "01-profile.png",     (0.267, 0.700, 0.290, 0.748), "white", True),
    ("ic-logout3d",     "01-profile.png",     (0.392, 0.700, 0.415, 0.748), "white", True),
    ("ic-gift3d",       "01-profile.png",     (0.530, 0.390, 0.566, 0.448), "white", False),
    ("ic-crown3d-s",    "01-profile.png",     (0.688, 0.390, 0.724, 0.448), "white", False),
    ("ic-crown3d-p",    "01-profile.png",     (0.840, 0.390, 0.876, 0.448), "white", False),

    # ── Lịch sử học tập: art hero + icon tài liệu + art empty state ────────
    ("hist-hero-art",   "07-history.png",     (0.752, 0.095, 0.862, 0.300), "gradient", True),
    ("hist-doc3d",      "07-history.png",     (0.242, 0.100, 0.305, 0.200), "gradient", True),
    ("hist-empty-art",  "07-history.png",     (0.505, 0.415, 0.640, 0.860), "gradient", False),
    ("ic-gear3d",       "04-settings.png",    (0.244, 0.052, 0.305, 0.172), "gradient", True),

    # ── Cổng phụ huynh ─────────────────────────────────────────────────────
    ("parent-empty-art", "03-parent.png",     (0.515, 0.265, 0.690, 0.645), "gradient", False),
    ("parent-tip-art",   "03-parent.png",     (0.040, 0.715, 0.140, 0.905), "gradient", True),
    ("parent-banner-art","03-parent.png",     (0.815, 0.110, 0.955, 0.325), "gradient", False),

    # ── Modal hướng dẫn nhanh (10-onboarding) ──────────────────────────────
    ("ic-crown-guide",  "10-onboarding.png",  (0.312, 0.295, 0.362, 0.372), "white", False),
    ("ic-bulb-guide",   "10-onboarding.png",  (0.318, 0.428, 0.368, 0.505), "white", False),
    ("ic-mail-guide",   "10-onboarding.png",  (0.318, 0.672, 0.368, 0.749), "white", False),
    ("guide-mascot",    "10-onboarding.png",  (0.295, 0.800, 0.390, 0.965), "gradient", False),

    # ── Nền trang trí (mây, lá, máy bay) cắt từ ảnh mẫu (nền gradient -> tách alpha) ──
    ("bg-leaves-l",  "11-home.png", (0.000, 0.880, 0.115, 1.000), "gradient", True),
    ("bg-leaves-r",  "11-home.png", (0.885, 0.880, 1.000, 1.000), "gradient", True),
    ("bg-cloud",     "11-home.png", (0.200, 0.930, 0.500, 1.000), "gradient", False),
    ("bg-plane",     "11-home.png", (0.585, 0.055, 0.700, 0.200), "gradient", True),
    ("bg-foliage-r", "09-chat.png", (0.855, 0.000, 1.000, 0.560), "gradient", False),
    ("bg-leaves-l2", "09-chat.png", (0.000, 0.000, 0.075, 0.960), "gradient", False),

    # ── Đăng nhập: đồ trang trí + 3 icon thanh lợi ích ─────────────────────
    ("login-deco-left",  "06-login.png",      (0.010, 0.550, 0.110, 0.835), "gradient", False),
    ("login-deco-globe", "06-login.png",      (0.895, 0.665, 0.995, 0.985), "gradient", False),
    ("ic-shield3d",      "06-login.png",      (0.266, 0.848, 0.300, 0.920), "white", False),
    ("ic-target3d-l",    "06-login.png",      (0.413, 0.848, 0.447, 0.920), "white", False),
    ("ic-star3d-l",      "06-login.png",      (0.588, 0.848, 0.622, 0.920), "white", False),
]


def _load(ref: str) -> np.ndarray:
    im = Image.open(REFS / ref).convert("RGB")
    return np.asarray(im).astype(np.float64)


def _alpha_white(rgb: np.ndarray) -> np.ndarray:
    """Tách nền trắng: alpha theo khoảng cách màu tới trắng (có làm mượt)."""
    diff = np.sqrt(((255.0 - rgb) ** 2).sum(-1)) / 255.0     # 0..1
    a = np.clip((diff - 0.045) / 0.16, 0, 1) ** 0.85
    return a


def _alpha_gradient(rgb: np.ndarray) -> np.ndarray:
    """Tách nền gradient: khớp đa thức bậc 3 theo viền rồi lấy sai khác màu."""
    h, w, _ = rgb.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    xs /= max(w - 1, 1)
    ys /= max(h - 1, 1)
    band = max(3, int(min(h, w) * 0.05))
    mask = np.zeros((h, w), bool)
    mask[:band, :] = True
    mask[-band:, :] = True
    mask[:, :band] = True
    mask[:, -band:] = True
    m = mask.ravel()
    feat = np.stack([np.ones_like(xs), xs, ys, xs * xs, ys * ys, xs * ys,
                     xs ** 3, ys ** 3, xs * xs * ys, xs * ys * ys], -1).reshape(-1, 10)
    bg = np.zeros_like(rgb)
    for c in range(3):
        coef, *_ = np.linalg.lstsq(feat[m], rgb[..., c].ravel()[m], rcond=None)
        bg[..., c] = (feat @ coef).reshape(h, w)
    diff = np.sqrt(((rgb - bg) ** 2).sum(-1)) / 255.0
    a = np.clip((diff - 0.042) / 0.050, 0, 1) ** 0.85
    return a


def _main_blob(a: np.ndarray) -> np.ndarray:
    """Giữ cụm nội dung lớn nhất (loại chữ/hoạ tiết rời trong khung cắt)."""
    try:
        from scipy import ndimage
    except Exception:
        return a
    m = a > 0.22
    grown = ndimage.binary_dilation(m, iterations=max(2, int(min(a.shape) * 0.03)))
    lab, n = ndimage.label(grown)
    if n <= 1:
        return a
    sizes = ndimage.sum(grown, lab, range(1, n + 1))
    keep = (np.argmax(sizes) + 1)
    keepmask = lab == keep
    keepmask = ndimage.binary_dilation(keepmask, iterations=max(2, int(min(a.shape) * 0.03)))
    return a * keepmask


def extract(name: str, ref: str, box, mode: str, blob: bool = True) -> dict:
    rgb_full = _load(ref)
    H, W, _ = rgb_full.shape
    x0, y0, x1, y1 = box
    L, T = int(x0 * W), int(y0 * H)
    R, B = int(x1 * W), int(y1 * H)
    crop = rgb_full[T:B, L:R]
    if crop.size == 0:
        raise SystemExit(f"{name}: box rỗng")
    a = _alpha_white(crop) if mode == "white" else _alpha_gradient(crop)
    if mode == "plate":
        a = np.ones(crop.shape[:2])
    if blob:
        a = _main_blob(a)

    # trim theo alpha
    ys, xs = np.where(a > 0.12)
    if len(xs) == 0:
        raise SystemExit(f"{name}: không tách được nội dung (mode={mode})")
    p = 2
    l, r = max(0, xs.min() - p), min(a.shape[1], xs.max() + p)
    t, b = max(0, ys.min() - p), min(a.shape[0], ys.max() + p)
    crop = crop[t:b, l:r]
    a = a[t:b, l:r]

    rgba = np.dstack([np.clip(crop, 0, 255), np.clip(a * 255, 0, 255)]).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA")
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / f"{name}.png")
    return {"name": name, "size": img.size, "src": ref}


def contact_sheet(assets: list[dict]) -> Path:
    """Xếp mọi asset lên nền kiểm tra để xem nhanh chất lượng tách nền."""
    cell = 220
    cols = 8
    rows = (len(assets) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 22)), (223, 247, 240))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
    for i, a in enumerate(assets):
        cx, cy = (i % cols) * cell, (i // cols) * (cell + 22)
        # nền caro nhẹ để thấy vùng trong suốt
        for gy in range(0, cell, 22):
            for gx in range(0, cell, 22):
                if ((gx // 22) + (gy // 22)) % 2 == 0:
                    d.rectangle([cx + gx, cy + gy, cx + gx + 21, cy + gy + 21], fill=(235, 250, 245))
        img = Image.open(OUT / f"{a['name']}.png")
        w, h = img.size
        s = min((cell - 16) / w, (cell - 16) / h, 1)
        img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
        sheet.paste(img, (cx + (cell - img.size[0]) // 2, cy + (cell - img.size[1]) // 2), img)
        d.text((cx + 6, cy + cell + 3), f"{a['name']} {w}x{h}", fill=(20, 90, 80), font=font)
    p = ROOT / "design" / "asset-sheet.png"
    sheet.save(p)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    done = []
    for name, ref, box, mode, blob in ASSETS:
        if only and name not in only:
            continue
        try:
            info = extract(name, ref, box, mode, blob)
            done.append(info)
            print(f"  ✓ {name:<18} {info['size'][0]:>4}x{info['size'][1]:<4} <- {ref}")
        except SystemExit as e:
            print(f"  ! {e}")
        except Exception as e:
            print(f"  ! {name}: {type(e).__name__}: {e}")
    print(f"\nĐã tạo {len(done)} asset → {OUT}")
    if args.sheet and done:
        print("Contact sheet:", contact_sheet(done))


if __name__ == "__main__":
    main()
