from pathlib import Path
from shutil import copytree


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "buddymath" / "FE"
PUBLIC_DIR = ROOT / "public"

if not FRONTEND_DIR.is_dir():
    raise RuntimeError(f"Frontend source directory is missing: {FRONTEND_DIR}")

copytree(FRONTEND_DIR, PUBLIC_DIR, dirs_exist_ok=True)
print(f"Copied {sum(1 for path in PUBLIC_DIR.rglob('*') if path.is_file())} frontend files to public/.")
