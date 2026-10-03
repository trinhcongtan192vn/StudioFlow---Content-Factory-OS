"""Kho Tài Nguyên (Asset Vault) API — CHANGE_Semantic_BRoll_Asset_Vault.md §4/§7.2.

**Đổi thành API TOÀN CỤC (2026-08-27, theo yêu cầu người dùng)** — trước đây mọi endpoint
theo `channel_id` trong path (kho riêng từng kênh); giờ Kho Tài Nguyên là 1 màn RIÊNG hiện
TẤT CẢ video/clip từ MỌI kênh, lọc theo kênh qua query param `?channel_id=`. 1 `RawVideo`
gắn được NHIỀU kênh (dạng tag, `channel_ids` bắt buộc ≥1 lúc import — xem
`models.py::raw_video_channel`); `ProcessedClip` kế thừa kênh của `raw_video` cha (JOIN,
xem `asset_vault/matching.py::_clips_for_channel`), không có tag riêng."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.asset_vault.ingest import (
    auto_detect_scenes,
    caption_all_pending_clips,
    caption_clips,
    create_raw_video_placeholder_for_url,
    delete_processed_clip,
    download_raw_video_from_url,
    import_raw_video_upload,
    manual_cut_clip,
    reconcile_raw_video_status,
    remove_watermark_from_raw_video,
)
from app.config import asset_vault_clips_dir, asset_vault_raw_dir
from app.db import get_db
from app.models import Channel, ProcessedClip, RawVideo, processed_clip_channel, raw_video_channel
from app.rangefile import range_file_response

router = APIRouter(tags=["asset-vault"])


@router.get("/asset-vault/folders")
def get_asset_vault_folders():
    """Đường dẫn filesystem THẬT của 2 thư mục lưu trữ (video gốc/clip đã cắt) — dùng cho
    nút "Mở thư mục" ở UI (renderer không tự biết đường dẫn tuyệt đối, chỉ backend biết).
    `asset_vault_raw_dir`/`asset_vault_clips_dir` tự tạo thư mục nếu chưa tồn tại (xem
    config.py) — nút "Mở thư mục" luôn mở được 1 thư mục THẬT, kể cả máy mới chưa import
    video nào."""
    return {"raw_dir": str(asset_vault_raw_dir()), "clips_dir": str(asset_vault_clips_dir())}


def _channel_list_out(channels) -> list[dict]:
    return [{"id": c.id, "name": c.name} for c in channels]


def _channels_out(r: RawVideo | None) -> list[dict]:
    """Kênh của 1 RawVideo — `r` có thể `None` (VD gọi từ `_raw_video_name`-style helper
    trên 1 clip đã mồ côi, xem `_clip_out` — clip TỰ có `channels` riêng từ 2026-08-28,
    KHÔNG còn suy ra qua hàm này nữa, chỉ `RawVideo` mới dùng)."""
    if r is None:
        return []
    return _channel_list_out(r.channels)


def _raw_video_name(r: RawVideo | None) -> str:
    """Tên hiển thị cho video gốc — dùng ở cột "Video nguồn" trong bảng Clip đã cắt/Raw
    Library. Ưu tiên `original_filename` (tên file THẬT lúc upload, 2026-08-27 — người
    dùng cần biết chính xác đã upload file gì), rồi `import_note` (ghi chú tự nhập), rồi
    tên file cuối của `source_url` (tải từ URL), cuối cùng mới về `id` kỹ thuật."""
    if r is None:
        return "(video gốc đã bị xoá)"
    if r.original_filename:
        return r.original_filename
    if r.import_note:
        return r.import_note
    if r.source_url:
        return r.source_url.rstrip("/").rsplit("/", 1)[-1]
    return r.id


def _raw_out(r: RawVideo) -> dict:
    return {
        "id": r.id,
        "channels": _channels_out(r),
        "source_url": r.source_url,
        "original_filename": r.original_filename,
        "import_note": r.import_note,
        "status": r.status,
        "error_message": r.error_message,
        "progress_current": r.progress_current,
        "progress_total": r.progress_total,
        "progress_label": r.progress_label,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _clip_out(c: ProcessedClip) -> dict:
    return {
        "clip_id": c.clip_id,
        "raw_video_id": c.raw_video_id,
        "raw_video_name": _raw_video_name(c.raw_video),
        "raw_video_status": c.raw_video.status if c.raw_video else None,
        # Kênh RIÊNG của clip (2026-08-28, xem docstring `models.py::ProcessedClip`) —
        # KHÔNG còn suy ra qua `raw_video` cha, nên vẫn đúng dù raw_video đã bị xoá.
        "channels": _channel_list_out(c.channels),
        "duration_sec": c.duration_sec,
        "resolution": c.resolution,
        "caption": c.caption,
        "tags": json.loads(c.tags or "[]"),
        "mood_tone": c.mood_tone,
        "usage_count": c.usage_count,
        "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        "active": c.active,
        "rights_status": c.rights_status,
        "rights_note": c.rights_note,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "caption_error": c.caption_error,
        # Mới (2026-09-11) — lưu ảnh/video từ Visual Studio vào Kho Tài Nguyên, xem
        # `asset_vault/from_visual_studio.py`. `media_kind` phân biệt ảnh/video (mọi clip
        # cắt cảnh cũ đều "video"). `from_visual_studio` = clip này đến từ Visual Studio
        # (raw_video CHA là hàng "ảo" đại diện project) hay từ cắt cảnh B-roll thật —
        # frontend dùng để tách 2 section riêng trong Kho Tài Nguyên.
        "media_kind": c.media_kind or "video",
        "from_visual_studio": bool(c.raw_video and c.raw_video.source_project_id),
    }


def _get_raw_or_404(db: Session, raw_id: str) -> RawVideo:
    raw = db.query(RawVideo).filter(RawVideo.id == raw_id).first()
    if not raw:
        raise HTTPException(404, "Không tìm thấy video gốc")
    return raw


def _get_clip_or_404(db: Session, clip_id: str) -> ProcessedClip:
    clip = db.query(ProcessedClip).filter(ProcessedClip.clip_id == clip_id).first()
    if not clip:
        raise HTTPException(404, "Không tìm thấy clip")
    return clip


def _raw_video_ids_for_channel(db: Session, channel_id: str):
    return db.query(raw_video_channel.c.raw_video_id).filter(raw_video_channel.c.channel_id == channel_id).subquery()


# ---------------------------------------------------------------------------
# Raw Library (§7.2 khu trên)
# ---------------------------------------------------------------------------
@router.get("/asset-vault/raw")
def list_raw_videos(channel_id: str | None = Query(default=None), kind: str = Query(default="raw"), db: Session = Depends(get_db)):
    # Loại hàng "ảo" đại diện project (2026-09-11, xem docstring `models.py::RawVideo.
    # source_project_id`) — không phải video thật user upload/dán URL, không có hành
    # động cắt cảnh/xoá watermark nào áp dụng được, không thuộc "Raw Library". `kind`
    # (mới 2026-09-13) đảo ngược filter này khi ="project" — dùng riêng để build dropdown
    # "Video nguồn" ở bảng "Asset từ Visual Studio" (Kho Tài Nguyên), nơi mỗi clip trỏ
    # ĐÚNG 1 hàng ảo này qua `raw_video_id` chứ không phải video thật nào.
    if kind == "project":
        q = db.query(RawVideo).filter(RawVideo.source_project_id.isnot(None))
    else:
        q = db.query(RawVideo).filter(RawVideo.source_project_id.is_(None))
    if channel_id:
        q = q.join(raw_video_channel, raw_video_channel.c.raw_video_id == RawVideo.id).filter(raw_video_channel.c.channel_id == channel_id)
    rows = q.order_by(RawVideo.created_at.desc()).all()
    # Tự phục hồi status kẹt do backend crash giữa task nền (mục 132) — KHÔNG chạy job
    # nào mới, chỉ suy lại từ dữ liệu clip con đã có sẵn, trước khi trả response.
    changed = False
    for r in rows:
        if reconcile_raw_video_status(db, r):
            changed = True
    if changed:
        db.commit()
    return [_raw_out(r) for r in rows]


@router.post("/asset-vault/raw/upload")
async def upload_raw_video(channel_ids: str = Form(...), file: UploadFile = File(...), import_note: str = Form(""), db: Session = Depends(get_db)):
    """`channel_ids` — chuỗi JSON list (multipart form không hỗ trợ field kiểu list gọn
    gàng qua `Form`, encode/decode JSON đơn giản hơn tự parse `channel_ids[]` kiểu cũ).
    Bắt buộc ≥1 kênh — đúng yêu cầu "gắn tên Kênh TRƯỚC KHI cắt cảnh"."""
    try:
        ids = json.loads(channel_ids)
    except json.JSONDecodeError as e:
        raise HTTPException(400, "channel_ids phải là JSON list hợp lệ") from e
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "Phải gắn ít nhất 1 kênh trước khi import video")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File rỗng")
    try:
        raw = import_raw_video_upload(db, ids, file.filename or "video.mp4", data, import_note)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _raw_out(raw)


class ImportUrlBody(BaseModel):
    url: str
    channel_ids: list[str]
    import_note: str = ""


@router.post("/asset-vault/raw/import-url")
def import_raw_video_from_url(body: ImportUrlBody, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """CHỈ gọi khi user tự dán link + bấm nút xác nhận ở UI — route này KHÔNG được gọi
    tự động bởi bất kỳ tiến trình nền nào trong app (§1). **Chạy nền (2026-08-27)** — tải
    video (yt-dlp) có thể mất nhiều phút, tạo hàng `RawVideo` NGAY (đồng bộ, trả về liền)
    rồi tải THẬT trong `BackgroundTasks`, để frontend poll được tiến trình tải giữa
    chừng (`progress_current`/`progress_total`, xem `ingest.py::download_raw_video_from_url`)."""
    if not body.url.strip():
        raise HTTPException(400, "Chưa nhập URL")
    if not body.channel_ids:
        raise HTTPException(400, "Phải gắn ít nhất 1 kênh trước khi import video")
    try:
        raw = create_raw_video_placeholder_for_url(db, body.channel_ids, body.url.strip(), body.import_note)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    def _run():
        from app.db import SessionLocal

        bg_db = SessionLocal()
        try:
            bg_raw = bg_db.query(RawVideo).filter(RawVideo.id == raw.id).first()
            if bg_raw:
                download_raw_video_from_url(bg_db, bg_raw)
        finally:
            bg_db.close()

    background_tasks.add_task(_run)
    return _raw_out(raw)


class RawChannelsPatchBody(BaseModel):
    channel_ids: list[str]


@router.patch("/asset-vault/raw/{raw_id}/channels")
def patch_raw_video_channels(raw_id: str, body: RawChannelsPatchBody, db: Session = Depends(get_db)):
    """Sửa lại tag kênh sau khi đã tạo — "quản lý dưới dạng tag" (thêm/bớt kênh bất kỳ
    lúc nào, không chỉ lúc import). Ghi đè TOÀN BỘ danh sách (không phải add/remove lẻ) —
    đơn giản hơn, khớp cách 1 multi-select kênh trên UI hoạt động.

    **Cascade sang clip con (2026-08-28)**: từ khi clip có tag kênh RIÊNG (xem
    `models.py::ProcessedClip`), sửa kênh ở đây (mức raw video) ĐỒNG BỘ ghi đè kênh của
    MỌI clip hiện đang thuộc `raw_video_id` này — khớp kỳ vọng người dùng (1 control edit
    kênh cho "cả video + toàn bộ clip con"). Muốn sửa kênh RIÊNG 1 clip mà không ảnh hưởng
    clip khác cùng nguồn (VD clip mồ côi cần gắn lại tay) → dùng `PATCH
    /asset-vault/clips/{clip_id}/channels` thay vì endpoint này."""
    raw = _get_raw_or_404(db, raw_id)
    if not body.channel_ids:
        raise HTTPException(400, "Phải gắn ít nhất 1 kênh")
    channels = db.query(Channel).filter(Channel.id.in_(body.channel_ids)).all()
    if len(channels) != len(set(body.channel_ids)):
        raise HTTPException(400, "1 hoặc nhiều channel_id không tồn tại")
    raw.channels = channels
    for clip in db.query(ProcessedClip).filter(ProcessedClip.raw_video_id == raw_id).all():
        clip.channels = list(channels)
    db.commit()
    return _raw_out(raw)


@router.delete("/asset-vault/raw/{raw_id}")
def delete_raw_video(raw_id: str, db: Session = Depends(get_db)):
    """Xoá RawVideo — KHÔNG cascade xoá `ProcessedClip` con (clip đã cắt là đơn vị dùng
    được ĐỘC LẬP một khi đã tạo, xem §4 — mất video gốc không có nghĩa clip đã cắt hết
    dùng được, nhất là clip đã gán vào shot của project khác)."""
    raw = _get_raw_or_404(db, raw_id)
    path = Path(raw.file_path)
    if path.exists():
        path.unlink(missing_ok=True)
    db.delete(raw)
    db.commit()
    return {"ok": True}


@router.get("/asset-vault/raw/{raw_id}/file")
def get_raw_video_file(request: Request, raw_id: str, db: Session = Depends(get_db)):
    """Xem trước video gốc (nút Play, bảng Raw Library) — cùng cơ chế range-request với
    `GET /asset-vault/clips/{id}/file` (tua được, không tải nguyên file mỗi lần seek)."""
    raw = _get_raw_or_404(db, raw_id)
    return range_file_response(request, raw.file_path)


class BatchTagChannelsBody(BaseModel):
    raw_ids: list[str]
    channel_ids: list[str]


@router.post("/asset-vault/raw/batch-tag-channels")
def batch_tag_raw_video_channels(body: BatchTagChannelsBody, db: Session = Depends(get_db)):
    """Gắn thêm tag kênh cho NHIỀU video gốc cùng lúc — **mới (2026-08-27)**, khác PATCH
    `/raw/{id}/channels` (SỬA 1 video, GHI ĐÈ toàn bộ danh sách): endpoint này CỘNG THÊM
    (union — không ghi đè) `channel_ids` vào tập kênh HIỆN CÓ của từng video, vì các video
    được chọn hàng loạt thường đã có tag kênh KHÁC NHAU sẵn — ghi đè sẽ xoá mất tag cũ
    ngoài ý muốn, cộng thêm mới an toàn và đúng ý "tag nhiều video 1 lúc". Cascade cộng
    thêm cùng `channel_ids` vào clip con của từng video (2026-08-28, cùng lý do đã ghi ở
    `patch_raw_video_channels`)."""
    if not body.raw_ids:
        raise HTTPException(400, "Chưa chọn video nào")
    if not body.channel_ids:
        raise HTTPException(400, "Chưa chọn kênh nào để gắn thêm")
    channels_to_add = db.query(Channel).filter(Channel.id.in_(body.channel_ids)).all()
    if len(channels_to_add) != len(set(body.channel_ids)):
        raise HTTPException(400, "1 hoặc nhiều channel_id không tồn tại")
    raws = db.query(RawVideo).filter(RawVideo.id.in_(body.raw_ids)).all()
    missing = set(body.raw_ids) - {r.id for r in raws}
    if missing:
        raise HTTPException(400, f"Không tìm thấy video: {', '.join(sorted(missing))}")
    for raw in raws:
        existing_ids = {c.id for c in raw.channels}
        raw.channels = raw.channels + [c for c in channels_to_add if c.id not in existing_ids]
        for clip in db.query(ProcessedClip).filter(ProcessedClip.raw_video_id == raw.id).all():
            clip_existing_ids = {c.id for c in clip.channels}
            clip.channels = clip.channels + [c for c in channels_to_add if c.id not in clip_existing_ids]
    db.commit()
    return [_raw_out(r) for r in raws]


class BatchDeleteRawBody(BaseModel):
    raw_ids: list[str]


@router.post("/asset-vault/raw/batch-delete")
def batch_delete_raw_videos(body: BatchDeleteRawBody, db: Session = Depends(get_db)):
    """Xoá NHIỀU video gốc cùng lúc — cùng hành vi `delete_raw_video` (KHÔNG cascade xoá
    clip con), lặp qua từng video thay vì 1 câu DELETE hàng loạt để dọn file trên đĩa cho
    từng video (bulk SQL DELETE không tự xoá được file filesystem)."""
    if not body.raw_ids:
        raise HTTPException(400, "Chưa chọn video nào")
    raws = db.query(RawVideo).filter(RawVideo.id.in_(body.raw_ids)).all()
    for raw in raws:
        path = Path(raw.file_path)
        if path.exists():
            path.unlink(missing_ok=True)
        db.delete(raw)
    db.commit()
    return {"ok": True, "deleted": len(raws)}


@router.post("/asset-vault/raw/{raw_id}/detect-scenes")
def detect_scenes_endpoint(raw_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Cắt cảnh TỰ ĐỘNG (PySceneDetect) — chạy nền vì có thể chậm với video dài, tránh
    chặn request. Tiến trình thật qua `progress_current`/`progress_total` (poll
    `GET .../raw`, xem `ingest.py::auto_detect_scenes`)."""
    raw = _get_raw_or_404(db, raw_id)

    def _run():
        from app.db import SessionLocal

        bg_db = SessionLocal()
        try:
            bg_raw = bg_db.query(RawVideo).filter(RawVideo.id == raw_id).first()
            if bg_raw:
                auto_detect_scenes(bg_db, bg_raw)
        finally:
            bg_db.close()

    background_tasks.add_task(_run)
    return _raw_out(raw)


@router.post("/asset-vault/raw/{raw_id}/remove-watermark")
def remove_watermark_endpoint(raw_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Xoá watermark khỏi video gốc TRƯỚC KHI cắt cảnh — chạy nền (Florence-2 + LaMa qua
    `app/watermark/`, có thể mất vài chục giây tới vài phút tuỳ độ dài video + lần đầu
    cần nạp model ~90s). Tiến trình thật qua `progress_current`/`progress_total` (poll
    `GET .../raw`, xem `ingest.py::remove_watermark_from_raw_video`). KHÔNG đổi `status`
    — video vẫn ở đúng bước tiếp theo (VD "detecting", sẵn sàng "Cắt cảnh tự động" ngay
    sau khi xoá watermark xong)."""
    raw = _get_raw_or_404(db, raw_id)

    def _run():
        from app.db import SessionLocal

        bg_db = SessionLocal()
        try:
            bg_raw = bg_db.query(RawVideo).filter(RawVideo.id == raw_id).first()
            if bg_raw:
                remove_watermark_from_raw_video(bg_db, bg_raw)
        finally:
            bg_db.close()

    background_tasks.add_task(_run)
    return _raw_out(raw)


class ManualCutBody(BaseModel):
    start_sec: float
    end_sec: float


@router.post("/asset-vault/raw/{raw_id}/manual-cut")
def manual_cut_endpoint(raw_id: str, body: ManualCutBody, db: Session = Depends(get_db)):
    """Cắt cảnh THỦ CÔNG — chạy ĐỒNG BỘ (1 lệnh ffmpeg trim, đủ nhanh, không cần
    BackgroundTasks) — lưới an toàn khi PySceneDetect chưa tinh chỉnh tốt cho video cụ
    thể (câu hỏi mở #4 change-spec)."""
    raw = _get_raw_or_404(db, raw_id)
    if body.end_sec <= body.start_sec:
        raise HTTPException(400, "end_sec phải lớn hơn start_sec")
    try:
        clip = manual_cut_clip(db, raw, body.start_sec, body.end_sec)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Cắt cảnh thất bại: {e}") from e
    return _clip_out(clip)


@router.post("/asset-vault/raw/{raw_id}/caption-all")
def caption_all_endpoint(raw_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Gắn nhãn (Vision + Embedding) TOÀN BỘ clip đã cắt từ video gốc này — chạy nền
    (nhiều clip × 1 lượt gọi VLM/embedding mỗi clip, có thể chậm)."""
    raw = _get_raw_or_404(db, raw_id)

    def _run():
        from app.db import SessionLocal

        bg_db = SessionLocal()
        try:
            bg_raw = bg_db.query(RawVideo).filter(RawVideo.id == raw_id).first()
            if bg_raw:
                caption_all_pending_clips(bg_db, bg_raw)
        finally:
            bg_db.close()

    background_tasks.add_task(_run)
    return _raw_out(raw)


# ---------------------------------------------------------------------------
# Processed Clip Library (§7.2 khu dưới)
# ---------------------------------------------------------------------------
@router.get("/asset-vault/clips")
def list_processed_clips(
    channel_id: str | None = Query(default=None),
    raw_video_id: str | None = Query(default=None),
    rights_status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    mood_tone: str | None = Query(default=None),
    unlabeled: bool = Query(default=False),
    raw_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """`unlabeled=true` — lọc clip CHƯA gắn nhãn (caption rỗng), bất kể trạng thái
    `raw_video` cha (VD raw_video đang "tagging" nhưng đã có VÀI clip lỡ gắn nhãn xong từ
    lần chạy trước — vẫn muốn thấy đúng phần CÒN THIẾU để bulk gắn nhãn tiếp). `raw_status`
    — lọc theo trạng thái của `raw_video` cha (`detecting`/`tagging`/`indexed`/`error`),
    hữu ích để tìm nhanh clip thuộc video gốc đang lỗi. Cả 2 filter mới (2026-08-27, phục
    vụ bảng "Clip đã cắt" dạng table + bulk gắn nhãn theo lựa chọn tự do)."""
    q = db.query(ProcessedClip)
    if raw_status:
        q = q.join(RawVideo, ProcessedClip.raw_video_id == RawVideo.id)
    if channel_id:
        # Lọc theo tag kênh RIÊNG của clip (2026-08-28) — KHÔNG còn qua raw_video cha, nên
        # đúng cả với clip đã tự sửa tag khác raw_video, hoặc raw_video cha đã bị xoá.
        q = q.join(processed_clip_channel, processed_clip_channel.c.clip_id == ProcessedClip.clip_id).filter(processed_clip_channel.c.channel_id == channel_id)
    if raw_status:
        q = q.filter(RawVideo.status == raw_status)
    if raw_video_id:
        q = q.filter(ProcessedClip.raw_video_id == raw_video_id)
    if rights_status:
        q = q.filter(ProcessedClip.rights_status == rights_status)
    if mood_tone:
        q = q.filter(ProcessedClip.mood_tone == mood_tone)
    if unlabeled:
        q = q.filter((ProcessedClip.caption == None) | (ProcessedClip.caption == ""))  # noqa: E711
    rows = q.order_by(ProcessedClip.created_at.desc()).all()
    if tag:
        tag_lower = tag.lower()
        rows = [c for c in rows if tag_lower in (c.tags or "").lower()]
    # Tự phục hồi status kẹt của raw_video CHA (mục 132) — `_clip_out` đọc
    # `c.raw_video.status`, nên "Clip đã cắt" cũng cần thấy status đã suy lại, không chỉ
    # "Raw Library". Suy theo từng raw_video CHA riêng biệt (1 raw_video có thể xuất hiện
    # nhiều lần qua nhiều clip con).
    seen_raw_ids: set[str] = set()
    changed = False
    for c in rows:
        if c.raw_video and c.raw_video.id not in seen_raw_ids:
            seen_raw_ids.add(c.raw_video.id)
            if reconcile_raw_video_status(db, c.raw_video):
                changed = True
    if changed:
        db.commit()
    return [_clip_out(c) for c in rows]


@router.get("/asset-vault/clips/{clip_id}/file")
def get_clip_file(request: Request, clip_id: str, db: Session = Depends(get_db)):
    clip = _get_clip_or_404(db, clip_id)
    return range_file_response(request, clip.storage_url)


class ClipPatchBody(BaseModel):
    caption: str | None = None
    tags: list[str] | None = None
    mood_tone: str | None = None
    rights_status: str | None = None
    rights_note: str | None = None
    active: bool | None = None


_VALID_RIGHTS_STATUS = ("unverified", "licensed_verified", "public_domain")


class ClipChannelsPatchBody(BaseModel):
    channel_ids: list[str]


@router.patch("/asset-vault/clips/{clip_id}/channels")
def patch_clip_channels(clip_id: str, body: ClipChannelsPatchBody, db: Session = Depends(get_db)):
    """Sửa tag kênh RIÊNG của 1 clip — ghi đè toàn bộ danh sách, KHÔNG đụng tới
    `raw_video` cha (khác `patch_raw_video_channels`, vốn cascade xuống MỌI clip con).
    Đây là đường DUY NHẤT gắn lại kênh cho 1 clip đã MỒ CÔI (raw_video cha đã bị xoá,
    không còn control kênh nào ở mức raw video để dùng nữa) — xem
    IMPLEMENTATION_REPORT.md mục 98."""
    clip = _get_clip_or_404(db, clip_id)
    if not body.channel_ids:
        raise HTTPException(400, "Phải gắn ít nhất 1 kênh")
    channels = db.query(Channel).filter(Channel.id.in_(body.channel_ids)).all()
    if len(channels) != len(set(body.channel_ids)):
        raise HTTPException(400, "1 hoặc nhiều channel_id không tồn tại")
    clip.channels = channels
    db.commit()
    return _clip_out(clip)


class BatchTagClipChannelsBody(BaseModel):
    clip_ids: list[str]
    channel_ids: list[str]


@router.post("/asset-vault/clips/batch-tag-channels")
def batch_tag_clip_channels(body: BatchTagClipChannelsBody, db: Session = Depends(get_db)):
    """Gắn thêm tag kênh cho NHIỀU clip cùng lúc (bulk edit) — CỘNG THÊM (union, không ghi
    đè) vào tập kênh hiện có của từng clip, cùng nguyên tắc `batch_tag_raw_video_channels`
    (các clip chọn hàng loạt thường có tag khác nhau sẵn, ghi đè sẽ mất tag cũ)."""
    if not body.clip_ids:
        raise HTTPException(400, "Chưa chọn clip nào")
    if not body.channel_ids:
        raise HTTPException(400, "Chưa chọn kênh nào để gắn thêm")
    channels_to_add = db.query(Channel).filter(Channel.id.in_(body.channel_ids)).all()
    if len(channels_to_add) != len(set(body.channel_ids)):
        raise HTTPException(400, "1 hoặc nhiều channel_id không tồn tại")
    clips = db.query(ProcessedClip).filter(ProcessedClip.clip_id.in_(body.clip_ids)).all()
    missing = set(body.clip_ids) - {c.clip_id for c in clips}
    if missing:
        raise HTTPException(400, f"Không tìm thấy clip: {', '.join(sorted(missing))}")
    for clip in clips:
        existing_ids = {c.id for c in clip.channels}
        clip.channels = clip.channels + [c for c in channels_to_add if c.id not in existing_ids]
    db.commit()
    return [_clip_out(c) for c in clips]


@router.patch("/asset-vault/clips/{clip_id}")
def patch_processed_clip(clip_id: str, body: ClipPatchBody, db: Session = Depends(get_db)):
    clip = _get_clip_or_404(db, clip_id)
    if body.rights_status is not None and body.rights_status not in _VALID_RIGHTS_STATUS:
        raise HTTPException(400, f"rights_status phải là 1 trong {_VALID_RIGHTS_STATUS}")
    if body.caption is not None:
        clip.caption = body.caption
        clip.caption_error = None  # người dùng tự sửa tay — lỗi AI gắn nhãn lần trước (nếu có) không còn ý nghĩa
    if body.tags is not None:
        clip.tags = json.dumps(body.tags, ensure_ascii=False)
    if body.mood_tone is not None:
        clip.mood_tone = body.mood_tone
    if body.rights_status is not None:
        clip.rights_status = body.rights_status
    if body.rights_note is not None:
        clip.rights_note = body.rights_note
    if body.active is not None:
        clip.active = body.active
    db.commit()
    return _clip_out(clip)


class BatchPatchBody(BaseModel):
    clip_ids: list[str]
    rights_status: str | None = None
    add_tag: str | None = None
    active: bool | None = None


@router.post("/asset-vault/clips/batch")
def batch_patch_processed_clips(body: BatchPatchBody, db: Session = Depends(get_db)):
    """Thao tác theo lô (§7.2) — quan trọng khi 1 video gốc sinh hàng chục clip cùng
    nguồn/cùng license, gán 1 lượt thay vì sửa từng clip."""
    if body.rights_status is not None and body.rights_status not in _VALID_RIGHTS_STATUS:
        raise HTTPException(400, f"rights_status phải là 1 trong {_VALID_RIGHTS_STATUS}")
    clips = db.query(ProcessedClip).filter(ProcessedClip.clip_id.in_(body.clip_ids)).all()
    for clip in clips:
        if body.rights_status is not None:
            clip.rights_status = body.rights_status
        if body.add_tag:
            tags = json.loads(clip.tags or "[]")
            if body.add_tag not in tags:
                tags.append(body.add_tag)
            clip.tags = json.dumps(tags, ensure_ascii=False)
        if body.active is not None:
            clip.active = body.active
    db.commit()
    return [_clip_out(c) for c in clips]


class CaptionBatchBody(BaseModel):
    clip_ids: list[str]


@router.post("/asset-vault/clips/caption-batch")
def caption_clips_batch_endpoint(body: CaptionBatchBody, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Bulk gắn nhãn theo LỰA CHỌN TỰ DO (tick từng clip/select all ở bảng "Clip đã cắt")
    — **mới (2026-08-27)**, khác `caption_all_pending_clips` (luôn scope theo 1
    `raw_video`): `clip_ids` có thể trải nhiều `raw_video` khác nhau. Chạy nền qua
    `BackgroundTasks` (mỗi clip = 1 lượt gọi Vision + Embedding provider, có thể chậm nếu
    chọn nhiều) — frontend poll `GET .../clips` như thường lệ, xem `caption`/
    `caption_error` của từng clip cập nhật dần (mỗi clip tự commit ngay khi xong, không
    đợi cả batch — xem `ingest.py::caption_clips`)."""
    if not body.clip_ids:
        raise HTTPException(400, "Chưa chọn clip nào")
    existing_ids = {c.clip_id for c in db.query(ProcessedClip.clip_id).filter(ProcessedClip.clip_id.in_(body.clip_ids)).all()}
    missing = set(body.clip_ids) - existing_ids
    if missing:
        raise HTTPException(400, f"Không tìm thấy clip: {', '.join(sorted(missing))}")

    def _run():
        from app.db import SessionLocal

        bg_db = SessionLocal()
        try:
            bg_clips = bg_db.query(ProcessedClip).filter(ProcessedClip.clip_id.in_(body.clip_ids)).all()
            caption_clips(bg_db, bg_clips)
        finally:
            bg_db.close()

    background_tasks.add_task(_run)
    return {"ok": True, "count": len(body.clip_ids)}


@router.delete("/asset-vault/clips/{clip_id}")
def delete_clip_endpoint(clip_id: str, db: Session = Depends(get_db)):
    clip = _get_clip_or_404(db, clip_id)
    delete_processed_clip(db, clip)
    return {"ok": True}


class BatchDeleteClipsBody(BaseModel):
    clip_ids: list[str]


@router.post("/asset-vault/clips/batch-delete")
def batch_delete_clips_endpoint(body: BatchDeleteClipsBody, db: Session = Depends(get_db)):
    """Xoá NHIỀU clip đã cắt cùng lúc (bulk edit, theo yêu cầu người dùng 2026-09-02) —
    cùng hành vi `delete_clip_endpoint`/`delete_processed_clip` (xoá file trên đĩa + vector
    Chroma + hàng DB) lặp qua từng clip, cùng nguyên tắc `batch_delete_raw_videos` (bulk SQL
    DELETE không tự xoá được file filesystem/vector, phải lặp qua ORM)."""
    if not body.clip_ids:
        raise HTTPException(400, "Chưa chọn clip nào")
    clips = db.query(ProcessedClip).filter(ProcessedClip.clip_id.in_(body.clip_ids)).all()
    for clip in clips:
        delete_processed_clip(db, clip)
    return {"ok": True, "deleted": len(clips)}
