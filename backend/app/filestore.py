"""Đọc/ghi file JSON trên workspace + version hoá — specs/01 mục 5, §02 mục 4.

Version = ghi file mới `*.v{n}.json` + thêm dòng bảng version + cập nhật con trỏ hiện hành.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _retry_on_permission_error(fn: Callable[[], T], attempts: int = 10, delay: float = 0.15) -> T:
    """Bug thật (2026-08-23, người dùng báo "thêm/xoá overlay bị lỗi, thử lại lại
    được"): xoá/ghi đè 1 file media (VD overlay.mp4) NGAY SAU KHI trình duyệt vừa stream
    xong preview `<video>`/`<audio>` có thể vẫn còn giữ handle đọc file trong chốc lát
    trên Windows — `unlink()`/`open('wb')` lúc đó ném `PermissionError` (WinError 32:
    "process cannot access the file because it is being used by another process"), dù
    bấm lại NGAY SAU đó (handle đã được trình duyệt nhả) lại thành công. Thử lại NGẮN
    trong tiến trình (tối đa 10 lần × 150ms ≈ 1.5s) thay vì bắt người dùng tự bấm lại."""
    last_err: PermissionError | None = None
    for _ in range(attempts):
        try:
            return fn()
        except PermissionError as exc:
            last_err = exc
            time.sleep(delay)
    assert last_err is not None
    raise last_err


def unlink_retrying(path: Path) -> None:
    """Xoá file, tự thử lại khi gặp Windows file lock thoáng qua — xem
    `_retry_on_permission_error`."""
    _retry_on_permission_error(path.unlink)


def write_bytes(path: Path, data: bytes) -> None:
    """Ghi asset nhị phân (ảnh/audio/video sinh từ provider — M2 Production Layer). Tự
    thử lại khi gặp Windows file lock thoáng qua (VD ghi đè lại đúng tên file vừa
    stream xong) — xem `_retry_on_permission_error`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _retry_on_permission_error(lambda: path.write_bytes(data))


def write_versioned(dir_path: Path, base_name: str, data: dict, version: int) -> tuple[Path, Path]:
    """Ghi bản hiện hành `<base_name>.json` + snapshot `<base_name>.v{n}.json`.
    Trả (current_path, version_path)."""
    current = dir_path / f"{base_name}.json"
    versioned = dir_path / f"{base_name}.v{version}.json"
    write_json(current, data)
    write_json(versioned, data)
    return current, versioned
