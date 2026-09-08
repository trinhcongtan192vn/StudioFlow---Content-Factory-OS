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


def probe_video_dimensions(path) -> tuple[int, int] | None:
    """Kích thước (width, height) THẬT của video stream đầu tiên — **mới (2026-09-02,
    mục 113)**, dùng cho `assembly.py::_composite_layers` (chế độ `screen`, cần biết tỉ
    lệ khung hình GỐC của layer để tính chiều cao khi scale, khác chế độ `alpha` dùng
    `-2` để ffmpeg tự tính). Cùng nguyên tắc `probe_duration_sec` — lỗi/thiếu binary chỉ
    bỏ qua, trả `None`, caller tự có fallback hợp lý (không chặn luồng ghép)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(path)],
            capture_output=True, check=True, text=True, timeout=15,
        )
        w_str, h_str = result.stdout.strip().split("x")
        return int(w_str), int(h_str)
    except Exception:  # noqa: BLE001
        return None
