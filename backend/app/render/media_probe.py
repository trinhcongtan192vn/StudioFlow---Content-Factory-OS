"""Đo thời lượng THẬT (giây) của 1 file media (audio/video) qua ffprobe — TÁCH RIÊNG,
KHÔNG phụ thuộc gì trong app (giống `transitions.py`/`camera_motion.py`) để cả
`app/render/engine.py` VÀ `app/routers/pipeline.py` đều dùng được mà không đụng vòng
import có sẵn: `engine.py` → `app.routers.pipeline` (import `record_asset_usage`) —
nếu `pipeline.py` import ngược lại `engine.py` sẽ vỡ ngay lúc khởi động app.
"""
from __future__ import annotations

import shutil
import subprocess


def probe_duration_sec(path) -> float | None:
    """Không bắt buộc cài ffprobe cho phần còn lại của app — lỗi/thiếu binary chỉ bỏ
    qua, trả `None`, KHÔNG chặn luồng gọi (đo thời lượng chỉ là thông tin bổ trợ)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, check=True, text=True, timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:  # noqa: BLE001
        return None
