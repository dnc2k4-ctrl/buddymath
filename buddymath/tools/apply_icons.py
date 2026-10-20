r"""apply_icons.py — thay emoji điều hướng bằng icon SVG tự thiết kế (data-i) + nhúng icons.js."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "FE"

NAV = {
    "🏠": "home", "💬": "chat", "🧠": "brain", "📐": "math", "🌏": "globe",
    "🌟": "sun", "🕐": "clock", "🏆": "trophy", "👤": "user", "⚙️": "gear", "📘": "book",
}

# 1) Thay icon trong sidebar (mathbuddy-kids.html)
kids = FE / "mathbuddy-kids.html"
html = kids.read_text(encoding="utf-8")
for emo, key in NAV.items():
    html = html.replace('<span class="nav-ic-em">' + emo + '</span>',
                        '<span class="nav-ic-em"><span data-i="' + key + '"></span></span>')
kids.write_text(html, encoding="utf-8")
print("✓ nav icons:", sum(1 for e in NAV.values() if 'data-i="' + e + '"' in html))

# 2) Nhúng icons.js vào tất cả các trang (sau stage-loader)
PAGES = ["mathbuddy-kids.html", "login.html", "parent.html", "admin.html",
         "terms.html", "privacy.html", "404.html"]
for name in PAGES:
    p = FE / name
    if not p.is_file():
        continue
    s = p.read_text(encoding="utf-8")
    if "icons.js" in s:
        continue
    anchor = '<script src="/assets/stage-loader.js?v=1"></script>'
    inject = '<script src="/assets/icons.js?v=1"></script>'
    if anchor in s:
        s = s.replace(anchor, anchor + "\n" + inject, 1)
        p.write_text(s, encoding="utf-8")
        print("✓ inject icons.js ->", name)
    else:
        print("! không thấy stage-loader trong", name)
