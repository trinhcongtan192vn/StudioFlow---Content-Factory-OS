"""Test `_retry_on_permission_error`/`unlink_retrying`/`write_bytes` — bug thật
(2026-08-23, người dùng báo "thêm/xoá overlay bị lỗi, thử lại lại được"): trên Windows,
xoá/ghi đè 1 file media ngay sau khi trình duyệt vừa stream xong preview có thể gặp
`PermissionError` (WinError 32) thoáng qua — phải tự thử lại trong tiến trình thay vì
để lỗi văng thẳng ra người dùng.
"""
from pathlib import Path

import pytest

from app.filestore import unlink_retrying, write_bytes


def test_unlink_retrying_succeeds_after_transient_permission_error(tmp_path, monkeypatch):
    f = tmp_path / "locked.mp4"
    f.write_bytes(b"data")

    real_unlink = Path.unlink
    calls = {"count": 0}

    def flaky_unlink(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError("[WinError 32] file in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    monkeypatch.setattr("app.filestore.time.sleep", lambda _: None)

    unlink_retrying(f)
    assert calls["count"] == 3
    assert not f.exists()


def test_unlink_retrying_reraises_after_exhausting_attempts(tmp_path, monkeypatch):
    f = tmp_path / "stuck.mp4"
    f.write_bytes(b"data")

    def always_locked(self, *args, **kwargs):
        raise PermissionError("[WinError 32] file in use")

    monkeypatch.setattr(Path, "unlink", always_locked)
    monkeypatch.setattr("app.filestore.time.sleep", lambda _: None)

    with pytest.raises(PermissionError):
        unlink_retrying(f)


def test_write_bytes_retries_on_transient_permission_error(tmp_path, monkeypatch):
    f = tmp_path / "overlay.mp4"

    real_write_bytes = Path.write_bytes
    calls = {"count": 0}

    def flaky_write_bytes(self, data, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            raise PermissionError("[WinError 32] file in use")
        return real_write_bytes(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)
    monkeypatch.setattr("app.filestore.time.sleep", lambda _: None)

    write_bytes(f, b"new content")
    assert calls["count"] == 2
    assert f.read_bytes() == b"new content"
