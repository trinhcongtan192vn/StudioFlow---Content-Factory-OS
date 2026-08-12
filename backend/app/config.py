"""Cấu hình đường dẫn & hằng số dùng chung cho backend.

Workspace layout theo specs/01_architecture.md:
  workspace/studioflow.db
  workspace/channels/<id>/brandprofile.json (+ versions)
  workspace/channels/<id>/projects/<id>/{brief,pack,retention}.json (+ exports/)
"""
from pathlib import Path
import os

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

WORKSPACE_DIR = Path(os.environ.get("STUDIOFLOW_WORKSPACE", REPO_ROOT / "workspace")).resolve()
CHANNELS_DIR = WORKSPACE_DIR / "channels"
DB_PATH = WORKSPACE_DIR / "studioflow.db"

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
CHANNELS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# Khóa mã hoá API key at-rest. MVP: sinh & lưu 1 lần trong workspace (single-user, local).
# Không phải giải pháp bảo mật cấp production multi-user — phù hợp phạm vi single-user local app (CLAUDE.md).
SECRET_KEY_PATH = WORKSPACE_DIR / ".secret_key"


def channel_dir(channel_id: str) -> Path:
    d = CHANNELS_DIR / channel_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_dir(channel_id: str, project_id: str) -> Path:
    d = channel_dir(channel_id) / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "exports").mkdir(exist_ok=True)
    (d / "assets").mkdir(exist_ok=True)  # ảnh/audio từng shot sinh thật — M2 Production Layer
    (d / "renders").mkdir(exist_ok=True)  # MP4 cuối cùng sau khi ghép — M2
    return d
