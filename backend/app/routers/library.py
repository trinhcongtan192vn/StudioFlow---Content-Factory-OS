"""Thư viện Creative Asset — **mới (2026-08-20)**, theo yêu cầu người dùng: quản lý tập
trung nhạc nền/video/ảnh/giọng đọc dùng lại được ở NHIỀU nơi trong app (song song việc
upload trực tiếp từ máy ở từng màn). Đứng ĐỘC LẬP, không gắn channel/project nào — entry
point "Thư viện" ở sidebar ngang hàng Dashboard (xem app/models/__init__.py::CreativeAsset).

**Quyết định kiến trúc quan trọng**: KHÔNG thêm endpoint "-from-library" ở từng nơi
upload hiện có (voice sample, intro, shot visual, bg music...). Frontend tự `fetch()`
bytes của asset thư viện qua `GET .../file` rồi gói lại thành `File`, gọi THẲNG API
upload sẵn có y hệt như người dùng tự chọn file từ máy — 0 thay đổi ở mọi endpoint
upload hiện tại, tránh phình route trùng lặp gần như y hệt nhau."""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import library_kind_dir
from app.db import get_db
from app.filestore import write_bytes
from app.models import CreativeAsset
from app.rangefile import range_file_response
from app.timeutil import vn_isoformat

router = APIRouter(tags=["library"])

_KINDS = ("music", "video", "image", "voice")

_EXT_BY_CONTENT_TYPE: dict[str, dict[str, str]] = {
    "music": {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav"},
    "voice": {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav"},
    "video": {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"},
    "image": {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"},
}
_EXT_BY_SUFFIX: dict[str, dict[str, str]] = {
    "music": {".mp3": "mp3", ".wav": "wav"},
    "voice": {".mp3": "mp3", ".wav": "wav"},
    "video": {".mp4": "mp4", ".webm": "webm", ".mov": "mov"},
    "image": {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp"},
}


def _new_id() -> str:
    # Hậu tố hex ngẫu nhiên (2026-09-12) — tránh trùng ID khi 2 hàng tạo trong CÙNG 1
    # mili giây (bug thật gặp lúc full test suite chạy nhanh, `UNIQUE constraint
    # failed`) — xem giải thích đầy đủ ở `asset_vault/ingest.py::_new_id`.
    return f"asset_{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"


def _asset_out(a: CreativeAsset) -> dict:
    return {
        "id": a.id,
        "kind": a.kind,
        "name": a.name,
        "created_at": vn_isoformat(a.created_at),
    }


@router.get("/library/assets")
def list_library_assets(kind: str | None = Query(default=None), db: Session = Depends(get_db)):
    if kind is not None and kind not in _KINDS:
        raise HTTPException(400, f"kind phải là 1 trong {_KINDS}")
    q = db.query(CreativeAsset)
    if kind:
        q = q.filter(CreativeAsset.kind == kind)
    assets = q.order_by(CreativeAsset.created_at.desc()).all()
    return [_asset_out(a) for a in assets]


@router.post("/library/assets/upload")
async def upload_library_asset(
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """`kind` truyền qua query string (multipart form không tiện khai báo field bắt
    buộc kiểu Literal cùng lúc với `UploadFile` qua Form() — query string đơn giản hơn,
    tương tự cách `list_library_assets` nhận `kind` lọc)."""
    if kind not in _KINDS:
        raise HTTPException(400, f"kind phải là 1 trong {_KINDS}")

    ct = file.content_type or ""
    suffix = Path(file.filename or "").suffix.lower()
    ext = _EXT_BY_CONTENT_TYPE[kind].get(ct) or _EXT_BY_SUFFIX[kind].get(suffix)
    if not ext:
        raise HTTPException(400, "Định dạng file không phù hợp với loại asset đã chọn")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File rỗng")

    asset_id = _new_id()
    name = Path(file.filename or asset_id).stem or asset_id
    file_path = library_kind_dir(kind) / f"{asset_id}.{ext}"
    write_bytes(file_path, data)

    asset = CreativeAsset(id=asset_id, kind=kind, name=name, file_path=str(file_path))
    db.add(asset)
    db.commit()
    return _asset_out(asset)


class RenameBody(BaseModel):
    name: str


@router.patch("/library/assets/{asset_id}")
def rename_library_asset(asset_id: str, body: RenameBody, db: Session = Depends(get_db)):
    """Đổi tên hiển thị — **mới (2026-08-21)**, theo yêu cầu người dùng: sửa được NGAY
    sau khi bấm "Thêm vào thư viện" ở các màn upload (tên gợi ý ban đầu lấy theo ngữ
    cảnh, VD "shot-mo-dau", không phải lúc nào cũng đúng ý người dùng) VÀ sửa lại bất kỳ
    lúc nào ở màn Thư viện. Chỉ đổi `name` (cột hiển thị) — KHÔNG đụng `file_path` trên
    đĩa (đổi tên file không cần thiết, tên hiển thị độc lập với tên file vật lý)."""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Tên không được để trống")
    asset = db.query(CreativeAsset).filter(CreativeAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Không tìm thấy asset")
    asset.name = name
    db.commit()
    return _asset_out(asset)


@router.delete("/library/assets/{asset_id}")
def delete_library_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(CreativeAsset).filter(CreativeAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Không tìm thấy asset")
    path = Path(asset.file_path)
    if path.exists():
        path.unlink()
    db.delete(asset)
    db.commit()
    return {"ok": True}


@router.get("/library/assets/{asset_id}/file")
def get_library_asset_file(request: Request, asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(CreativeAsset).filter(CreativeAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Không tìm thấy asset")
    return range_file_response(request, asset.file_path)
