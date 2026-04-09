from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "app" / "static" / "uploads"
FILENET_DIR = BASE_DIR / "app" / "static" / "filenet"
DB_PATH = DATA_DIR / "iasw.db"
AUDIT_LOG = DATA_DIR / "audit.log"

for directory in (DATA_DIR, UPLOAD_DIR, FILENET_DIR):
    directory.mkdir(parents=True, exist_ok=True)
