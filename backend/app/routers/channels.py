import shutil
import subprocess
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import channel_dir, delete_channel_dir
from app.db import get_db
from app.filestore import read_json, unlink_retrying, write_bytes, write_versioned
from app.models import AuditLog, BrandProfileVersion, Channel, Project
from app.rangefile import range_file_response
from app.render.schemas import NARRATION_LANGUAGES
from app.schemas import BrandProfile
from app.timeutil import vn_isoformat

router = APIRouter(tags=["channels"])


def _new_id(prefix: str) -> str:
    # Hậu tố hex ngẫu nhiên (2026-09-12) — tránh trùng ID khi 2 hàng tạo trong CÙNG 1
    # mili giây (bug thật gặp lúc full test suite chạy nhanh, `UNIQUE constraint
    # failed`) — xem giải thích đầy đủ ở `asset_vault/ingest.py::_new_id`.
    return f"{prefix}_{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"


class ChannelCreate(BaseModel):
    name: str
    niche: str = ""


class ChannelPatch(BaseModel):
    name: str | None = None
    niche: str | None = None
    archived: bool | None = None


def _channel_out(db: Session, ch: Channel) -> dict:
    # `review_count` (đếm project ở status await_gate1/await_gate2) đã bỏ (2026-08-17,
    # mục 44 IMPLEMENTATION_REPORT.md) — không còn gate duyệt bắt buộc nào để "chờ".
    running = db.query(Project).filter(Project.channel_id == ch.id, Project.archived == False, Project.status.notin_(["exported", "published"])).count()  # noqa: E712
    return {
        "id": ch.id,
        "name": ch.name,
        "niche": ch.niche,
        "letter": (ch.name[:1] or "?").upper(),
        "archived": ch.archived,
        "brandprofile_version": ch.brandprofile_version,
        "running_count": running,
        # Chỉ số YouTube — mới (2026-09-12) — xem `routers/youtube_analytics.py`.
        "youtube_channel_id": ch.youtube_channel_id,
        "youtube_channel_title": ch.youtube_channel_title,
        "youtube_connected_at": ch.youtube_connected_at,
    }


@router.get("/channels")
def list_channels(db: Session = Depends(get_db)):
    chs = db.query(Channel).filter(Channel.archived == False).order_by(Channel.order_index).all()  # noqa: E712
    return [_channel_out(db, c) for c in chs]


class ReorderChannelsBody(BaseModel):
    channel_ids: list[str]


@router.patch("/channels/reorder")
def reorder_channels(body: ReorderChannelsBody, db: Session = Depends(get_db)):
    """Kéo thả sắp xếp lại thứ tự kênh trên Sidebar — mới (2026-09-19). Nhận NGUYÊN danh
    sách ID theo thứ tự mới mong muốn, gán `order_index` = vị trí trong danh sách đó."""
    chs = db.query(Channel).filter(Channel.id.in_(body.channel_ids)).all()
    by_id = {c.id: c for c in chs}
    missing = [cid for cid in body.channel_ids if cid not in by_id]
    if missing:
        raise HTTPException(404, f"Không tìm thấy kênh: {', '.join(missing)}")
    for idx, cid in enumerate(body.channel_ids):
        by_id[cid].order_index = idx
    db.commit()
    return {"ok": True}


@router.post("/channels")
def create_channel(body: ChannelCreate, db: Session = Depends(get_db)):
    cid = _new_id("ch")
    # order_index = cuối danh sách hiện có (2026-09-19, xem docstring cột) — khớp hành vi
    # mặc định hiện tại (kênh mới luôn xuất hiện cuối, không có optimistic chèn đầu nào).
    max_order = db.query(func.max(Channel.order_index)).scalar()
    ch = Channel(id=cid, name=body.name, niche=body.niche, brandprofile_version=1, order_index=0 if max_order is None else max_order + 1)
    db.add(ch)
    db.flush()

    profile = BrandProfile(channel_id=cid, niche=body.niche)
    cdir = channel_dir(cid)
    current, versioned = write_versioned(cdir, "brandprofile", profile.model_dump(), 1)
    ch.brandprofile_path = str(current)
    db.add(BrandProfileVersion(channel_id=cid, version=1, file_path=str(versioned), note="Khởi tạo"))
    db.add(AuditLog(action="Tạo kênh", detail=body.name, entity=body.name))
    db.commit()
    return _channel_out(db, ch)


@router.get("/channels/{channel_id}")
def get_channel(channel_id: str, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    out = _channel_out(db, ch)
    out["brand_profile"] = profile
    return out


@router.patch("/channels/{channel_id}")
def patch_channel(channel_id: str, body: ChannelPatch, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    if body.name is not None:
        ch.name = body.name
    if body.niche is not None:
        ch.niche = body.niche
    if body.archived is not None:
        ch.archived = body.archived
        db.add(AuditLog(action="Xóa kênh" if body.archived else "Khôi phục kênh", detail=ch.name, entity=ch.name))
    db.commit()
    return _channel_out(db, ch)


@router.post("/channels/{channel_id}/restore")
def restore_channel(channel_id: str, db: Session = Depends(get_db)):
    """Khôi phục kênh khỏi Thùng rác — chỉ đổi `archived` về False (đối xứng với
    `PATCH .../archived=true` vốn là cách "xoá" kênh hiện có, xem Dashboard.tsx)."""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    ch.archived = False
    db.add(AuditLog(action="Khôi phục kênh", detail=ch.name, entity=ch.name))
    db.commit()
    return _channel_out(db, ch)


@router.delete("/channels/{channel_id}/permanent")
def delete_channel_permanent(channel_id: str, db: Session = Depends(get_db)):
    """Xoá vĩnh viễn — CHỈ cho phép với kênh đã ở Thùng rác (archived=True), tránh bấm
    nhầm xoá cứng 1 kênh đang hoạt động bình thường. Xoá DB row (cascade sang mọi
    Project/BrandProfileVersion con — xem Channel.projects/brandprofile_versions,
    app/models/__init__.py) VÀ xoá luôn thư mục trên đĩa (`delete_channel_dir` —
    KHÔNG khôi phục được nữa sau bước này, khác archive)."""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    if not ch.archived:
        raise HTTPException(400, "Chỉ xoá vĩnh viễn được kênh đã ở Thùng rác — xoá kênh (archive) trước.")
    name = ch.name
    db.add(AuditLog(action="Xoá vĩnh viễn kênh", detail=name, entity=name))
    db.delete(ch)
    db.commit()
    delete_channel_dir(channel_id)
    return {"ok": True}


@router.get("/channels/{channel_id}/brandprofile")
def get_brandprofile(channel_id: str, db: Session = Depends(get_db)):
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    if profile is None:
        raise HTTPException(404, "Chưa có BrandProfile")
    return profile


@router.put("/channels/{channel_id}/brandprofile")
def put_brandprofile(channel_id: str, body: BrandProfile, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    next_version = (ch.brandprofile_version or 0) + 1
    body.version = next_version
    cdir = channel_dir(channel_id)
    current, versioned = write_versioned(cdir, "brandprofile", body.model_dump(), next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note="Cập nhật BrandProfile"))
    db.add(AuditLog(action="Sửa BrandProfile", detail=ch.name, entity=ch.name))
    db.commit()
    return body.model_dump()


_VOICE_EXT_BY_CONTENT_TYPE = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/vnd.wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/x-mp3": "mp3",
    "audio/mpeg3": "mp3",
    "audio/x-mpeg-3": "mp3",
}
_VOICE_EXT_BY_SUFFIX = {".wav": "wav", ".mp3": "mp3"}


_VOICE_SAMPLE_MAX_SEC = 10.0  # cắt về tối đa ngần này — xem docstring _trim_voice_sample


def _trim_voice_sample(path: Path) -> tuple[bool, float | None]:
    """Cắt mẫu giọng về tối đa `_VOICE_SAMPLE_MAX_SEC` giây (đè lên file gốc) — trả về
    `(đã_cắt, thời_lượng_gốc_giây)` để endpoint báo lại cho người dùng biết (frontend
    hiện thông báo rõ khi mẫu bị cắt ngắn, không âm thầm). KHÔNG làm gì (trả
    `(False, None)`) nếu ffmpeg/ffprobe không có sẵn hoặc mẫu đã đủ ngắn.

    Bug thật phát hiện 2026-08-16: người dùng báo audio narration voice-cloning (OmniVoice)
    "lẫn nội dung của audio sample với nội dung cần đọc". Đo thật: mẫu giọng người dùng
    upload dài **57.7 giây**; OmniVoice tự trim về ≤20s khi thiếu `ref_text` (xem
    `omnivoice/models/omnivoice.py::create_voice_clone_prompt`) nhưng CHÍNH TÀI LIỆU
    package cảnh báo mẫu >10s "may cause slower generation, higher memory usage, and
    degraded voice cloning quality" — khuyến nghị 3-10s. Đối chiếu số liệu thật xác nhận
    đúng hiện tượng: narration B02/B03 (omnivoice) chỉ ~7.2 ký tự/giây, chậm gần 4 lần so
    với baseline Piper (~27 ký tự/giây cho project này) — dấu hiệu rõ ràng model "lẫn"
    nội dung tham chiếu vào output, không chỉ đọc chậm tự nhiên. Cắt sẵn ở bước upload
    (thay vì tin cậy hoàn toàn vào auto-trim 20s của model) để tránh lặp lại bug này cho
    người dùng khác — xem IMPLEMENTATION_REPORT.md."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return False, None
    try:
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        duration = float(probe.stdout.strip())
    except Exception:  # noqa: BLE001
        return False, None  # không đọc được thời lượng — để nguyên file, không chặn upload
    if duration <= _VOICE_SAMPLE_MAX_SEC:
        return False, None
    # `path.stem + "_trim" + path.suffix` (KHÔNG phải `path.suffix + ".trim"`) — ffmpeg
    # suy ra định dạng output từ ĐUÔI FILE THẬT (`.mp3`/`.wav`); tên kiểu "voice_sample.
    # mp3.trim" khiến ffmpeg đọc nhầm đuôi thành ".trim" (không phải định dạng hợp lệ) →
    # lỗi "Unable to choose an output format" — bug thật bắt được lúc verify (2026-08-16).
    tmp_path = path.with_name(f"{path.stem}_trim{path.suffix}")
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(path), "-t", str(_VOICE_SAMPLE_MAX_SEC), "-af", "afade=t=out:st=9.7:d=0.3", str(tmp_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            tmp_path.unlink(missing_ok=True)
            return False, None
        tmp_path.replace(path)
        return True, duration
    except Exception:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)  # trim thất bại — giữ nguyên file gốc, không chặn upload
        return False, None


@router.post("/channels/{channel_id}/brandprofile/voice-sample/upload")
async def upload_voice_sample(channel_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Mẫu giọng đọc thương hiệu — dùng làm `reference_audio` cho voice cloning
    (OmniVoice, xem app/providers/tts_omnivoice.py) khi sinh narration cho MỌI project
    của kênh này, giữ giọng nhất quán xuyên suốt portfolio (§05 mục OmniVoice). Không
    cần transcript tay — OmniVoice tự dùng Whisper ASR phiên âm mẫu khi thiếu `ref_text`.
    Tự CẮT về tối đa 10 giây (xem `_trim_voice_sample`) — mẫu dài hơn gây lẫn nội dung
    tham chiếu vào narration sinh ra (bug thật đã gặp, IMPLEMENTATION_REPORT.md).
    Bỏ mẫu: PUT lại BrandProfile với `voice_clone_ref_path=""` (dùng chung endpoint có
    sẵn, không cần route xoá riêng)."""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    if profile is None:
        raise HTTPException(404, "Chưa có BrandProfile")

    # Trình duyệt/OS không phải lúc nào cũng gửi đúng Content-Type (VD Windows chưa
    # đăng ký MIME cho .mp3 → "application/octet-stream" hoặc rỗng) — fallback theo
    # đuôi file thật khi content_type không nhận diện được, để không từ chối nhầm file
    # WAV/MP3 hợp lệ.
    ext = _VOICE_EXT_BY_CONTENT_TYPE.get(file.content_type or "") or _VOICE_EXT_BY_SUFFIX.get(Path(file.filename or "").suffix.lower())
    if not ext:
        raise HTTPException(400, "Chỉ nhận audio WAV/MP3")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File audio rỗng")

    cdir = channel_dir(channel_id)
    sample_path = cdir / f"voice_sample.{ext}"
    write_bytes(sample_path, data)
    trimmed, original_duration_sec = _trim_voice_sample(sample_path)

    profile["voice_clone_ref_path"] = str(sample_path)
    next_version = (ch.brandprofile_version or 0) + 1
    profile["version"] = next_version
    current, versioned = write_versioned(cdir, "brandprofile", profile, next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note="Upload mẫu giọng thương hiệu"))
    db.add(AuditLog(action="Upload giọng thương hiệu", detail=ch.name, entity=ch.name))
    db.commit()
    # 2 field thêm KHÔNG thuộc BrandProfile persist — chỉ để frontend báo 1 lần ngay sau
    # upload rằng mẫu đã bị cắt ngắn (mục 24 IMPLEMENTATION_REPORT.md), không âm thầm.
    return {**profile, "voice_sample_trimmed": trimmed, "voice_sample_original_duration_sec": original_duration_sec}


@router.get("/channels/{channel_id}/brandprofile/voice-sample")
def get_voice_sample(request: Request, channel_id: str, db: Session = Depends(get_db)):
    profile = read_json(channel_dir(channel_id) / "brandprofile.json") or {}
    path = profile.get("voice_clone_ref_path")
    if not path:
        raise HTTPException(404, "Chưa có mẫu giọng thương hiệu")
    return range_file_response(request, path)


@router.post("/channels/{channel_id}/brandprofile/voice-sample/upload/{lang}")
async def upload_voice_sample_lang(channel_id: str, lang: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Mẫu giọng đọc RIÊNG cho 1 NGÔN NGỮ — giọng đọc đa ngôn ngữ cho thị trường nước
    ngoài (2026-09-04). Ghi vào `BrandProfile.voice_clone_ref_paths[lang]` (KHÔNG đụng
    `voice_clone_ref_path` đơn cũ) — dùng làm `reference_audio` khi sinh giọng đọc ngôn
    ngữ đó (xem `app/render/engine.py::_read_voice_clone_ref_for_lang`). Cùng logic cắt
    10s/validate định dạng như `upload_voice_sample` (mẫu ngôn ngữ chính)."""
    if lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    if profile is None:
        raise HTTPException(404, "Chưa có BrandProfile")

    ext = _VOICE_EXT_BY_CONTENT_TYPE.get(file.content_type or "") or _VOICE_EXT_BY_SUFFIX.get(Path(file.filename or "").suffix.lower())
    if not ext:
        raise HTTPException(400, "Chỉ nhận audio WAV/MP3")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File audio rỗng")

    cdir = channel_dir(channel_id)
    sample_path = cdir / f"voice_sample_{lang}.{ext}"
    write_bytes(sample_path, data)
    trimmed, original_duration_sec = _trim_voice_sample(sample_path)

    voice_clone_ref_paths = dict(profile.get("voice_clone_ref_paths") or {})
    voice_clone_ref_paths[lang] = str(sample_path)
    profile["voice_clone_ref_paths"] = voice_clone_ref_paths
    next_version = (ch.brandprofile_version or 0) + 1
    profile["version"] = next_version
    current, versioned = write_versioned(cdir, "brandprofile", profile, next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note=f"Upload mẫu giọng ngôn ngữ {lang}"))
    db.add(AuditLog(action="Upload giọng đa ngôn ngữ", detail=f"{ch.name} ({lang})", entity=ch.name))
    db.commit()
    return {**profile, "voice_sample_trimmed": trimmed, "voice_sample_original_duration_sec": original_duration_sec}


@router.get("/channels/{channel_id}/brandprofile/voice-sample/{lang}")
def get_voice_sample_lang(request: Request, channel_id: str, lang: str, db: Session = Depends(get_db)):
    if lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json") or {}
    path = (profile.get("voice_clone_ref_paths") or {}).get(lang)
    if not path:
        raise HTTPException(404, "Chưa có mẫu giọng cho ngôn ngữ này")
    return range_file_response(request, path)


_LOGO_EXT_BY_CONTENT_TYPE = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_LOGO_EXT_BY_SUFFIX = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp"}


@router.post("/channels/{channel_id}/brandprofile/logo/upload")
async def upload_brand_logo(channel_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Logo kênh — **mới (2026-08-22)**, theo yêu cầu người dùng. Thuần hiển thị nhận diện
    thương hiệu (xem `BrandProfile.logo_path`) — KHÔNG dùng trong pipeline sinh asset/ghép
    video, khác `intro_video_path`/`voice_clone_ref_path`. Cùng pattern upload ảnh tĩnh
    (`render.py::_IMAGE_EXT_BY_*`) — nhận PNG/JPEG/WEBP, thay TẠI CHỖ (xoá file cũ khác
    đuôi nếu có, cùng nguyên tắc `upload_brand_intro`).
    Bỏ logo: PUT lại BrandProfile với `logo_path=""` (cùng pattern voice-sample/intro,
    không cần route xoá riêng)."""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    if profile is None:
        raise HTTPException(404, "Chưa có BrandProfile")

    ext = _LOGO_EXT_BY_CONTENT_TYPE.get(file.content_type or "") or _LOGO_EXT_BY_SUFFIX.get(Path(file.filename or "").suffix.lower())
    if not ext:
        raise HTTPException(400, "Chỉ nhận ảnh PNG/JPEG/WEBP")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File ảnh rỗng")

    cdir = channel_dir(channel_id)
    new_path = cdir / f"logo.{ext}"
    old_path_str = profile.get("logo_path")
    if old_path_str and Path(old_path_str).exists() and Path(old_path_str) != new_path:
        unlink_retrying(Path(old_path_str))
    write_bytes(new_path, data)

    profile["logo_path"] = str(new_path)
    next_version = (ch.brandprofile_version or 0) + 1
    profile["version"] = next_version
    current, versioned = write_versioned(cdir, "brandprofile", profile, next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note="Upload logo thương hiệu"))
    db.add(AuditLog(action="Upload logo thương hiệu", detail=ch.name, entity=ch.name))
    db.commit()
    return profile


@router.get("/channels/{channel_id}/brandprofile/logo")
def get_brand_logo(channel_id: str, db: Session = Depends(get_db)):
    profile = read_json(channel_dir(channel_id) / "brandprofile.json") or {}
    path = profile.get("logo_path")
    if not path:
        raise HTTPException(404, "Chưa có logo thương hiệu")
    # `Cache-Control: no-cache` — cùng lý do đã thêm ở `range_file_response`
    # (app/rangefile.py, 2026-08-23): logo bị ĐÈ TẠI CHỖ mỗi lần đổi, không có header này
    # trình duyệt có thể trả bytes cũ từ cache mà không revalidate.
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


_INTRO_VIDEO_EXT_BY_CONTENT_TYPE = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}
_INTRO_VIDEO_EXT_BY_SUFFIX = {".mp4": "mp4", ".webm": "webm", ".mov": "mov"}


@router.post("/channels/{channel_id}/brandprofile/intro/upload")
async def upload_brand_intro(channel_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Video/audio thương hiệu — **mới (2026-08-20)**, theo yêu cầu người dùng: phát ở
    ĐẦU MỌI video của kênh này khi ghép MP4 (trừ khi 1 project cụ thể tự có shot mở đầu
    riêng — override, xem `render.py::upload_intro_visual`). CHỈ 1 trong 2 (video HOẶC
    audio) được lưu tại 1 thời điểm — loại file upload QUYẾT ĐỊNH kind, XOÁ NGAY field
    còn lại (cùng nguyên tắc mutual-exclusivity người dùng yêu cầu). Nhận diện loại file
    qua `_INTRO_VIDEO_EXT_BY_*` (video) trước, rồi `_VOICE_EXT_BY_*` (audio, tái dùng
    map đã có cho mẫu giọng) — file không khớp cả 2 → 400.
    Bỏ: PUT lại BrandProfile với field tương ứng rỗng (cùng pattern voice-sample)."""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    if profile is None:
        raise HTTPException(404, "Chưa có BrandProfile")

    suffix = Path(file.filename or "").suffix.lower()
    video_ext = _INTRO_VIDEO_EXT_BY_CONTENT_TYPE.get(file.content_type or "") or _INTRO_VIDEO_EXT_BY_SUFFIX.get(suffix)
    audio_ext = _VOICE_EXT_BY_CONTENT_TYPE.get(file.content_type or "") or _VOICE_EXT_BY_SUFFIX.get(suffix)
    if not video_ext and not audio_ext:
        raise HTTPException(400, "Chỉ nhận video (MP4/WEBM/MOV) hoặc audio (WAV/MP3)")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File rỗng")

    cdir = channel_dir(channel_id)
    kind = "video" if video_ext else "audio"
    ext = video_ext or audio_ext
    new_path = cdir / f"intro.{ext}"
    # Xoá file intro CŨ (kể cả khác loại — VD trước là audio giờ đổi sang video) tránh
    # rác — cùng nguyên tắc "thay thế TẠI CHỖ" đã dùng cho upload-visual từng shot.
    for old_field in ("intro_video_path", "intro_audio_path"):
        old_path = profile.get(old_field)
        if old_path and Path(old_path).exists() and Path(old_path) != new_path:
            unlink_retrying(Path(old_path))
    write_bytes(new_path, data)

    profile["intro_video_path"] = str(new_path) if kind == "video" else ""
    profile["intro_audio_path"] = str(new_path) if kind == "audio" else ""
    next_version = (ch.brandprofile_version or 0) + 1
    profile["version"] = next_version
    current, versioned = write_versioned(cdir, "brandprofile", profile, next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note="Upload video/audio thương hiệu"))
    db.add(AuditLog(action="Upload video/audio thương hiệu", detail=ch.name, entity=ch.name))
    db.commit()
    return profile


@router.get("/channels/{channel_id}/brandprofile/intro")
def get_brand_intro(request: Request, channel_id: str, db: Session = Depends(get_db)):
    profile = read_json(channel_dir(channel_id) / "brandprofile.json") or {}
    path = profile.get("intro_video_path") or profile.get("intro_audio_path")
    if not path:
        raise HTTPException(404, "Chưa có video/audio thương hiệu")
    return range_file_response(request, path)


@router.post("/channels/{channel_id}/brandprofile/bg-music/upload")
async def upload_brand_bg_music(channel_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Nhạc nền MẶC ĐỊNH của kênh — **mới (2026-08-20)**, theo yêu cầu người dùng: phát
    ĐÈ LIÊN TỤC dưới TOÀN BỘ video (kể cả intro) khi ghép MP4 cho mọi project của kênh
    này, trừ khi project tự override riêng (`render.py::upload_project_bg_music`, ưu
    tiên cao hơn — xem `app/render/bg_music.py::resolve_bg_music_source`). LUÔN audio
    (khác intro — không có nhánh video), tái dùng map `_VOICE_EXT_BY_*` sẵn có. Chỉnh
    âm lượng qua `PUT .../brandprofile` (`bg_music_volume`, dùng chung endpoint đã có).
    Bỏ nhạc nền: PUT lại với `bg_music_path=""` (cùng pattern voice-sample/intro)."""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    if profile is None:
        raise HTTPException(404, "Chưa có BrandProfile")

    ext = _VOICE_EXT_BY_CONTENT_TYPE.get(file.content_type or "") or _VOICE_EXT_BY_SUFFIX.get(Path(file.filename or "").suffix.lower())
    if not ext:
        raise HTTPException(400, "Chỉ nhận audio WAV/MP3")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File audio rỗng")

    cdir = channel_dir(channel_id)
    old_path = profile.get("bg_music_path")
    new_path = cdir / f"bg_music.{ext}"
    if old_path and Path(old_path).exists() and Path(old_path) != new_path:
        unlink_retrying(Path(old_path))
    write_bytes(new_path, data)

    profile["bg_music_path"] = str(new_path)
    next_version = (ch.brandprofile_version or 0) + 1
    profile["version"] = next_version
    current, versioned = write_versioned(cdir, "brandprofile", profile, next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note="Upload nhạc nền kênh"))
    db.add(AuditLog(action="Upload nhạc nền kênh", detail=ch.name, entity=ch.name))
    db.commit()
    return profile


@router.get("/channels/{channel_id}/brandprofile/bg-music")
def get_brand_bg_music(request: Request, channel_id: str, db: Session = Depends(get_db)):
    profile = read_json(channel_dir(channel_id) / "brandprofile.json") or {}
    path = profile.get("bg_music_path")
    if not path:
        raise HTTPException(404, "Chưa có nhạc nền kênh")
    return range_file_response(request, path)


@router.post("/channels/{channel_id}/brandprofile/overlay/upload")
async def upload_brand_overlay(channel_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Hiệu ứng lớp phủ (overlay, VD mưa/tuyết rơi) MẶC ĐỊNH của kênh — **mới
    (2026-08-22)**, theo yêu cầu người dùng: blend ĐÈ LIÊN TỤC lên TOÀN BỘ video (kể cả
    intro) khi ghép MP4 cho mọi project của kênh này, trừ khi project tự override riêng
    (`render.py::upload_project_overlay`, ưu tiên cao hơn — xem `app/render/overlay.py::
    resolve_overlay_source`). LUÔN video (mp4/webm/mov, tái dùng map `_INTRO_VIDEO_EXT_
    BY_*` sẵn có — cùng loại file với intro, khác bg-music là audio). Chỉnh cường độ qua
    `PUT .../brandprofile` (`overlay_effect_opacity`, dùng chung endpoint đã có).
    Bỏ overlay: PUT lại với `overlay_effect_path=""` (cùng pattern voice-sample/intro/
    bg-music)."""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    if profile is None:
        raise HTTPException(404, "Chưa có BrandProfile")

    ext = _INTRO_VIDEO_EXT_BY_CONTENT_TYPE.get(file.content_type or "") or _INTRO_VIDEO_EXT_BY_SUFFIX.get(Path(file.filename or "").suffix.lower())
    if not ext:
        raise HTTPException(400, "Chỉ nhận video MP4/WEBM/MOV")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File video rỗng")

    cdir = channel_dir(channel_id)
    old_path = profile.get("overlay_effect_path")
    new_path = cdir / f"overlay.{ext}"
    if old_path and Path(old_path).exists() and Path(old_path) != new_path:
        unlink_retrying(Path(old_path))
    write_bytes(new_path, data)

    profile["overlay_effect_path"] = str(new_path)
    next_version = (ch.brandprofile_version or 0) + 1
    profile["version"] = next_version
    current, versioned = write_versioned(cdir, "brandprofile", profile, next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note="Upload hiệu ứng lớp phủ kênh"))
    db.add(AuditLog(action="Upload hiệu ứng lớp phủ kênh", detail=ch.name, entity=ch.name))
    db.commit()
    return profile


@router.get("/channels/{channel_id}/brandprofile/overlay")
def get_brand_overlay(request: Request, channel_id: str, db: Session = Depends(get_db)):
    profile = read_json(channel_dir(channel_id) / "brandprofile.json") or {}
    path = profile.get("overlay_effect_path")
    if not path:
        raise HTTPException(404, "Chưa có hiệu ứng lớp phủ kênh")
    return range_file_response(request, path)


@router.get("/channels/{channel_id}/brandprofile/versions")
def brandprofile_versions(channel_id: str, db: Session = Depends(get_db)):
    versions = (
        db.query(BrandProfileVersion)
        .filter(BrandProfileVersion.channel_id == channel_id)
        .order_by(BrandProfileVersion.version.desc())
        .all()
    )
    return [{"version": v.version, "created_at": vn_isoformat(v.created_at), "note": v.note} for v in versions]


@router.post("/channels/{channel_id}/brandprofile/clone-from/{src_channel_id}")
def clone_brandprofile(channel_id: str, src_channel_id: str, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    src_profile = read_json(channel_dir(src_channel_id) / "brandprofile.json")
    if src_profile is None:
        raise HTTPException(404, "Không tìm thấy BrandProfile nguồn")
    src_profile["channel_id"] = channel_id
    next_version = (ch.brandprofile_version or 0) + 1
    src_profile["version"] = next_version
    cdir = channel_dir(channel_id)
    current, versioned = write_versioned(cdir, "brandprofile", src_profile, next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note=f"Clone từ {src_channel_id}"))
    db.commit()
    return src_profile
