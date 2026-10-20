from pathlib import Path
from shutil import copytree


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "buddymath" / "FE"
PUBLIC_DIR = ROOT / "buddymath" / "BE" / "public"

if not FRONTEND_DIR.is_dir():
    raise RuntimeError(f"Frontend source directory is missing: {FRONTEND_DIR}")

copytree(FRONTEND_DIR, PUBLIC_DIR, dirs_exist_ok=True)
print(f"Copied {sum(1 for path in PUBLIC_DIR.rglob('*') if path.is_file())} frontend files to public/.")

# Inject panel-ui.js after mathbuddy-kids.js (Achievements/Settings mockup panels)
kids = PUBLIC_DIR / "mathbuddy-kids.html"
if kids.is_file():
    html = kids.read_text(encoding="utf-8")
    needle = 'src="/assets/mathbuddy-kids.js'
    inject = '<script src="/assets/panel-ui.js?v=1"></script>\n'
    if "panel-ui.js" not in html and needle in html:
        # insert right after the mathbuddy-kids.js script tag
        idx = html.find(needle)
        end = html.find("</script>", idx)
        if end != -1:
            end += len("</script>")
            html = html[:end] + "\n" + inject + html[end:]
            kids.write_text(html, encoding="utf-8")
            print("Injected panel-ui.js into mathbuddy-kids.html")

# Inject parent-ui-boot.js into parent.html
parent = PUBLIC_DIR / "parent.html"
if parent.is_file():
    html = parent.read_text(encoding="utf-8")
    if "parent-ui-boot.js" not in html and "</head>" in html:
        html = html.replace(
            "</head>",
            '<script src="/assets/parent-ui-boot.js?v=1"></script>\n</head>',
            1,
        )
        parent.write_text(html, encoding="utf-8")
        print("Injected parent-ui-boot.js into parent.html")
