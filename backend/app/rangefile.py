"""Phục vụ file media (video/audio) hỗ trợ HTTP Range request — **bug thật người dùng
báo (2026-08-20)**: player video ở Render Studio không tua được. Xác nhận nguyên nhân
thật (đọc thẳng source, không đoán): `starlette==0.38.6` (bản cài trong `.venv`) —
`FileResponse` KHÔNG hề xử lý header `Range` (không có 1 dòng "range"/"206"/
"Accept-Ranges" nào trong `starlette/responses.py`), luôn trả 200 + NGUYÊN file. Trình
duyệt `<video>`/`<audio>` seek bằng cách gửi `Range: bytes=X-Y` — server bỏ qua hoàn
toàn header đó nên trình duyệt không tua được (chỉ phát tuần tự từ đầu).

Dùng `range_file_response()` thay `FileResponse` cho MỌI endpoint phục vụ video/audio
(ảnh/document không cần — không ai "tua" 1 file JSON/ảnh tĩnh).
"""
from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from starlette.responses import FileResponse, Response, StreamingResponse

_CHUNK_SIZE = 1024 * 1024  # 1MB/lần đọc — đủ lớn để ít lần gọi read(), đủ nhỏ để không giữ cả file trong RAM


def range_file_response(
    request: Request, path: str | Path, *, media_type: str | None = None, filename: str | None = None,
) -> Response:
    path = Path(path)
    file_size = path.stat().st_size
    if media_type is None:
        media_type = mimetypes.guess_type(filename or str(path))[0] or "application/octet-stream"
    range_header = request.headers.get("range")

    if not range_header:
        # Không có Range (VD tải file qua fetch/anchor, không phải <video>/<audio> đang
        # seek) — trả nguyên file như FileResponse vẫn làm, chỉ thêm quảng cáo
        # `Accept-Ranges` để trình duyệt biết CÓ THỂ gửi Range ở lần gọi sau (lúc seek).
        return FileResponse(path, media_type=media_type, filename=filename, headers={"Accept-Ranges": "bytes"})

    try:
        unit, _, range_spec = range_header.partition("=")
        start_str, _, end_str = range_spec.partition("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        if unit != "bytes" or start > end or start < 0:
            raise ValueError
    except ValueError:
        # Range header sai định dạng — trả 416 đúng chuẩn HTTP (RFC 7233) thay vì lờ đi.
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    chunk_length = end - start + 1

    def _iter_range() -> Iterator[bytes]:
        with open(path, "rb") as f:
            f.seek(start)
            remaining = chunk_length
            while remaining > 0:
                data = f.read(min(_CHUNK_SIZE, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_length),
    }
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'  # khớp mặc định của FileResponse
    return StreamingResponse(_iter_range(), status_code=206, media_type=media_type, headers=headers)
