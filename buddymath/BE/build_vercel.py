from pathlib import Path


PUBLIC_DIR = Path(__file__).resolve().parent / "public"
REQUIRED_PAGES = ("login.html", "mathbuddy-kids.html", "parent.html", "admin.html")
missing = [name for name in REQUIRED_PAGES if not (PUBLIC_DIR / name).is_file()]
if missing:
    raise SystemExit(f"Missing committed Vercel public files: {', '.join(missing)}")

print("Vercel public files are present.")
