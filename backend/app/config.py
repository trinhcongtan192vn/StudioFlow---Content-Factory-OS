"""Cấu hình đường dẫn & hằng số dùng chung cho backend.

Workspace layout theo specs/01_architecture.md:
  workspace/studioflow.db
  workspace/channels/<id>/brandprofile.json (+ versions)
  workspace/channels/<id>/projects/<id>/{brief,pack,retention}.json (+ exports/)
"""
from pathlib import Path
import os
import shutil

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

WORKSPACE_DIR = Path(os.environ.get("STUDIOFLOW_WORKSPACE", REPO_ROOT / "workspace")).resolve()
CHANNELS_DIR = WORKSPACE_DIR / "channels"
DB_PATH = WORKSPACE_DIR / "studioflow.db"
# Thư viện Creative Asset (nhạc nền/video/ảnh/giọng đọc dùng lại nhiều nơi) — mới
# (2026-08-20), theo yêu cầu người dùng. Đứng NGOÀI channels/ (không gắn kênh nào cụ
# thể — dùng chung toàn app, khớp entry point "Thư viện" ở sidebar ngang hàng Dashboard,
# không phải mục con của 1 kênh).
LIBRARY_DIR = WORKSPACE_DIR / "library"

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
CHANNELS_DIR.mkdir(parents=True, exist_ok=True)
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# Khóa mã hoá API key at-rest. MVP: sinh & lưu 1 lần trong workspace (single-user, local).
# Không phải giải pháp bảo mật cấp production multi-user — phù hợp phạm vi single-user local app (CLAUDE.md).
SECRET_KEY_PATH = WORKSPACE_DIR / ".secret_key"

# Model weights local (Piper TTS) — không commit vào git (xem .gitignore), tải riêng
# theo hướng dẫn IMPLEMENTATION_REPORT.md khi setup máy có GPU/local model.
PIPER_MODELS_DIR = BACKEND_DIR / "models" / "piper"


def channel_dir(channel_id: str) -> Path:
    d = CHANNELS_DIR / channel_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def library_kind_dir(kind: str) -> Path:
    d = LIBRARY_DIR / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_dir(channel_id: str, project_id: str) -> Path:
    d = channel_dir(channel_id) / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "exports").mkdir(exist_ok=True)
    (d / "assets").mkdir(exist_ok=True)  # ảnh/audio từng shot sinh thật — M2 Production Layer
    (d / "renders").mkdir(exist_ok=True)  # MP4 cuối cùng sau khi ghép — M2
    return d


def _rmtree_within_channels(d: Path) -> None:
    """Xoá hẳn 1 thư mục con của `CHANNELS_DIR` khỏi đĩa — dùng cho "Xoá vĩnh viễn" ở
    Thùng rác (khác archive/soft-delete vốn không đụng file). Kiểm tra `d` thật sự nằm
    TRONG `CHANNELS_DIR` trước khi `rmtree` — phòng vệ thêm dù `channel_id`/`project_id`
    luôn do server tự sinh (không phải input người dùng ghép trực tiếp vào path), tránh
    lỡ tay xoá nhầm thư mục ngoài ý muốn nếu logic gọi hàm này sau này đổi khác."""
    resolved = d.resolve()
    if resolved == CHANNELS_DIR.resolve() or CHANNELS_DIR.resolve() not in resolved.parents:
        return
    if resolved.exists():
        shutil.rmtree(resolved)


def delete_channel_dir(channel_id: str) -> None:
    """Xoá vĩnh viễn `workspace/channels/<id>/` — gồm CẢ brandprofile lẫn mọi project
    con (thư mục `projects/`), vì DB row Project đã bị xoá cascade cùng lúc (xem
    `Channel.projects` cascade="all, delete-orphan", app/models/__init__.py)."""
    _rmtree_within_channels(CHANNELS_DIR / channel_id)


def delete_project_dir(channel_id: str, project_id: str) -> None:
    """Xoá vĩnh viễn `workspace/channels/<id>/projects/<id>/` — dùng khi xoá vĩnh viễn
    1 project riêng lẻ (không xoá cả kênh)."""
    _rmtree_within_channels(CHANNELS_DIR / channel_id / "projects" / project_id)
