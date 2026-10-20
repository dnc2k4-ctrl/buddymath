r"""gen_art.py (v2) — sinh hero "glass aurora" chất lượng cao bằng numpy (không dùng ảnh mẫu)."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "FE" / "images" / "art"
SS = 2  # supersample
W, H = 1600 * SS, 900 * SS


def radial(x, y, cx, cy, r, ry=None):
    ry = ry or r
    return np.clip(1 - np.sqrt(((x - cx) / r) ** 2 + ((y - cy) / ry) ** 2), 0, 1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    x, y = xx / W, yy / H

    # 1) nền gradient chéo: teal đậm -> xanh mint -> vàng nhạt góc
    base = np.zeros((H, W, 3), np.float32)
    top = np.array([9, 46, 44], np.float32)
    mid = np.array([22, 130, 112], np.float32)
    bot = np.array([196, 255, 240], np.float32)
    t = np.clip(x * 0.55 + y * 0.65, 0, 1)[..., None]
    base = top * (1 - t) ** 1.6 + mid * (1 - abs(t - 0.55)) ** 2 + bot * t ** 2.4

    # 2) các quầng sáng (glow) tính trực tiếp, cộng màu
    glows = [
        (0.78, 0.22, 0.42, (90, 255, 220), 1.15),
        (0.36, 0.12, 0.34, (60, 200, 255), 0.55),
        (0.62, 0.92, 0.5, (255, 214, 130), 0.75),
        (0.08, 0.85, 0.35, (30, 255, 200), 0.5),
        (0.95, 0.85, 0.4, (120, 200, 255), 0.45),
    ]
    for cx, cy, r, col, k in glows:
        g = radial(x, y, cx, cy, r) ** 2.4
        base += g[..., None] * np.array(col, np.float32) * k

    # 3) dải sáng chéo (aurora)
    band = np.exp(-((y - 0.36 - 0.22 * np.sin(x * 5.2 + 1.2)) ** 2) / 0.0045)
    base += band[..., None] * np.array([120, 255, 226], np.float32) * 0.42
    band2 = np.exp(-((y - 0.58 - 0.18 * np.sin(x * 3.6)) ** 2) / 0.006)
    base += band2[..., None] * np.array([255, 236, 176], np.float32) * 0.22

    base = np.clip(base, 0, 255)

    # 4) vòng quỹ đạo (vẽ supersample rồi giảm)
    img = Image.fromarray(base.astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = int(0.72 * W), int(0.5 * H)
    for rw, col, wd in ((0.46, (170, 255, 235, 70), 3 * SS), (0.36, (255, 255, 255, 55), 2 * SS), (0.55, (140, 240, 255, 40), 2 * SS)):
        rx, ry = int(rw * W * 0.62), int(rw * H * 0.9)
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=col, width=wd)

    # 5) quả cầu thuỷ tinh
    sx, sy, sr = int(0.72 * W), int(0.5 * H), int(0.20 * H)
    disc = radial(x, y, 0.72, 0.5, sr / W, sr / H)
    rim = np.clip((disc - radial(x, y, 0.72, 0.5, (sr - 8 * SS) / W, (sr - 8 * SS) / H)) * 3, 0, 1)
    inner = disc ** 3.2
    sph_col = np.array([18, 120, 110], np.float32) * (1 - inner[..., None]) + np.array([160, 255, 238], np.float32) * inner[..., None] * 0.85
    spec = radial(x, y, 0.655, 0.40, 0.10, 0.10) ** 2.2
    sph_col += spec[..., None] * np.array([255, 255, 255], np.float32) * 0.9
    glow = radial(x, y, 0.72, 0.5, 0.36, 0.5) ** 2.0
    base = base * (1 - glow[..., None] * 0.25) + np.array([120, 255, 230], np.float32) * glow[..., None] * 0.30
    base = base * (1 - disc[..., None]) + sph_col * disc[..., None]
    base += rim[..., None] * np.array([220, 255, 250], np.float32) * 0.9

    # 6) hạt sáng + vignette + noise nhẹ
    rng = np.random.default_rng(11)
    for _ in range(220):
        px, py = int(rng.uniform(0, W)), int(rng.uniform(0, H))
        rr = int(rng.uniform(1, 3) * SS)
        a = int(rng.uniform(40, 190))
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(255, 255, 255, a))

    vig = np.clip(1 - 0.42 * (((x - 0.5) ** 2 + (y - 0.5) ** 2) * 2.4), 0, 1)
    base *= vig[..., None]
    base += rng.normal(0, 1.6, (H, W, 1))
    out = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").resize((W // SS, H // SS), Image.LANCZOS)
    out.save(OUT / "hero-aurora.jpg", quality=93)
    print("✓", OUT / "hero-aurora.jpg", out.size)


if __name__ == "__main__":
    main()
