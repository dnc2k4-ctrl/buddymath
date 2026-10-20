from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent / "buddymath" / "BE"
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
