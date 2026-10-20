import numpy as np
from pathlib import Path
from PIL import Image

OUT = Path("buddymath/FE/images/art"); OUT.mkdir(parents=True, exist_ok=True)
W, H = 1600, 900
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
x, y = xx / W, yy / H


def gen(name, cols, glows):
    base = np.zeros((H, W, 3), np.float32)
    n = len(cols) - 1
    for i in range(n):
        t = np.clip((x * 0.7 + y * 0.5 - i / n) * n, 0, 1)[..., None]
        base = base * (1 - t) + (np.array(cols[i], np.float32) * (1 - t) + np.array(cols[i + 1], np.float32) * t)
    for cx, cy, r, c, k in glows:
        d = np.clip(1 - np.sqrt(((x - cx) / r) ** 2 + ((y - cy) / (r * 0.8)) ** 2), 0, 1) ** 2.3
        base += d[..., None] * np.array(c, np.float32) * k
    base += np.exp(-((y - 0.4 - 0.15 * np.sin(x * 4.5)) ** 2) / 0.005)[..., None] * np.array([110, 255, 225], np.float32) * 0.25
    base *= np.clip(1 - 0.4 * (((x - .5) ** 2 + (y - .5) ** 2) * 2.6), 0, 1)[..., None]
    Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).save(OUT / name, quality=92)
    print("+", name)


gen("aurora-mint.jpg", [(10, 52, 50), (24, 132, 114), (130, 240, 214), (240, 255, 250)],
    [(0.75, 0.25, 0.42, (90, 255, 222), 0.9), (0.3, 0.15, 0.3, (60, 190, 255), 0.5), (0.6, 0.9, 0.5, (255, 220, 140), 0.5)])
gen("aurora-ocean.jpg", [(8, 32, 66), (18, 88, 150), (70, 190, 220), (230, 250, 255)],
    [(0.7, 0.3, 0.45, (120, 235, 255), 0.85), (0.25, 0.2, 0.3, (170, 140, 255), 0.45), (0.75, 0.85, 0.5, (110, 255, 210), 0.45)])
gen("aurora-sunset.jpg", [(46, 20, 60), (120, 50, 120), (240, 140, 140), (255, 235, 200)],
    [(0.72, 0.28, 0.45, (255, 190, 200), 0.75), (0.3, 0.2, 0.3, (255, 200, 120), 0.5), (0.7, 0.9, 0.5, (160, 220, 255), 0.45)])
