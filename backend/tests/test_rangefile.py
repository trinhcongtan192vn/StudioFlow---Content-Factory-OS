"""Test `app/rangefile.py` — bug thật người dùng báo (2026-08-20): player video ở
Render Studio không tua được. Nguyên nhân thật (xác nhận bằng đọc source, không đoán):
Starlette 0.38.6 (bản cài) — `FileResponse` KHÔNG xử lý header `Range` (không có 1 dòng
"range"/"206"/"Accept-Ranges" nào trong `starlette/responses.py`). Test qua 1 app
Starlette TỐI GIẢN tự dựng (không đụng router thật của app) — verify hành vi HTTP thật
(request/response ASGI đầy đủ), không mock nội bộ.
"""
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from app.rangefile import range_file_response


def _make_client(tmp_path, content: bytes):
    f = tmp_path / "f.bin"
    f.write_bytes(content)

    async def endpoint(request):
        return range_file_response(request, f, media_type="application/octet-stream")

    app = Starlette(routes=[Route("/f", endpoint)])
    return TestClient(app), f


def test_no_range_header_returns_full_file_with_accept_ranges_advertised(tmp_path):
    content = bytes(range(256)) * 4  # 1024 byte, mỗi offset 1 giá trị phân biệt được
    client, _ = _make_client(tmp_path, content)

    resp = client.get("/f")
    assert resp.status_code == 200
    assert resp.content == content
    # Quảng cáo hỗ trợ Range NGAY từ response đầu tiên — để trình duyệt biết có thể tua
    # mà không cần thử Range trước (bug gốc: FileResponse không có header này).
    assert resp.headers["accept-ranges"] == "bytes"


def test_partial_range_returns_206_with_exact_requested_bytes(tmp_path):
    content = bytes(range(256)) * 4
    client, _ = _make_client(tmp_path, content)

    resp = client.get("/f", headers={"Range": "bytes=10-19"})
    assert resp.status_code == 206
    assert resp.headers["content-range"] == f"bytes 10-19/{len(content)}"
    assert resp.headers["content-length"] == "10"
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.content == content[10:20]


def test_open_ended_range_returns_from_start_to_end_of_file(tmp_path):
    """`Range: bytes=1000-` (không có số cuối) — trình duyệt dùng dạng này khi tua gần
    cuối file, phải trả đúng tới hết file, không lỗi."""
    content = bytes(range(256)) * 4  # 1024 byte
    client, _ = _make_client(tmp_path, content)

    resp = client.get("/f", headers={"Range": "bytes=1000-"})
    assert resp.status_code == 206
    assert resp.content == content[1000:]
    assert resp.headers["content-range"] == f"bytes 1000-1023/{len(content)}"


def test_range_end_beyond_file_size_clamps_to_actual_end(tmp_path):
    content = bytes(range(256)) * 4
    client, _ = _make_client(tmp_path, content)

    resp = client.get("/f", headers={"Range": "bytes=1000-99999"})
    assert resp.status_code == 206
    assert resp.content == content[1000:]
    assert resp.headers["content-range"] == f"bytes 1000-1023/{len(content)}"


def test_malformed_range_header_returns_416(tmp_path):
    """Range sai định dạng (đơn vị lạ/số âm/start>end) — trả 416 đúng chuẩn HTTP (RFC
    7233) thay vì lờ đi/crash."""
    client, _ = _make_client(tmp_path, b"0123456789")
    for bad in ("items=0-5", "bytes=abc-xyz", "bytes=20-5"):
        resp = client.get("/f", headers={"Range": bad})
        assert resp.status_code == 416, f"Range={bad!r} phải trả 416"
