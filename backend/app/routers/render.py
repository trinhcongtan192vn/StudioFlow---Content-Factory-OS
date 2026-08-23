"""Render Studio API — M2 Production Layer (sinh asset thật + ghép MP4).
Module tách biệt script core (specs/09) — mọi endpoint ở đây chỉ ĐỌC pack.json qua
app/render/engine.py, không bao giờ ghi lại vào pack.json.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json, write_bytes
from app.models import Project
from app.rangefile import range_file_response
from app.render import engine
from app.render.assembly import Codec, Quality, Resolution, assemble_video, probe_gpu_encoder, resolve_video_codec
from app.render.schemas import BgMusicOverride, IntroAssetStatus, OverlayEffectOverride
from app.render.transitions import TRANSITIONS

router = APIRouter(tags=["render"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return p


def _find_shot_status(state, shot_id: str):
    return next((s for s in state.shots if s.shot_id == shot_id), None)


def _find_shot_and_beat(pack: dict, shot_id: str):
    shot = next((s for s in pack.get("shots", []) if s["shot_id"] == shot_id), None)
    if not shot:
        raise HTTPException(404, "Không tìm thấy shot")
    return shot, engine._find_beat(pack, shot)


def _require_not_in_progress(project_id: str) -> None:
    """Chặn mở batch/regenerate MỚI khi project đã có 1 task đang chạy — `render/start`
    và 2 nút sinh lại từng shot đều tự mở BackgroundTasks riêng; bấm chồng lên nhau khi
    task trước CHƯA kịp disable nút trên UI (VD vừa bấm "toàn bộ block" rồi bấm "sinh
    lại" cho 1 shot đang generate) từng làm 2 task cùng ghi đè `render.json`, mất tiến
    độ các shot chưa xử lý. 409 rõ ràng thay vì âm thầm chạy chồng."""
    if engine.is_generation_in_progress(project_id):
        raise HTTPException(409, "Đang có 1 tiến trình sinh asset chạy cho project này — đợi xong hoặc bấm Dừng trước khi bắt đầu tiến trình khác.")


@router.post("/projects/{project_id}/render/start")
def start_render(project_id: str, background_tasks: BackgroundTasks, kind: str = "both", force: bool = False, db: Session = Depends(get_db)):
    """Sinh asset thật (ảnh/video/giọng đọc) cho từng shot — dùng ngay ở Visual Studio.
    Chỉ cần đã có shot list (`/visual/generate` đã chạy) — không gate theo
    `project.status`. KHÔNG còn yêu cầu duyệt Thumbnail trước (bỏ 2026-08-16 — Thumbnail
    hết vai trò "anchor" bắt buộc, xem app/render/engine.py::generate_visual_asset).

    `kind` — "both" (mặc định, giữ hành vi cũ) | "visual" | "narration": tách nút
    "Sinh asset cho toàn bộ block" ở Visual Studio thành 2 nút riêng (2026-08-16, theo
    yêu cầu người dùng, xem `engine.run_asset_generation` docstring).

    `force` — **mới (2026-08-22)**, theo yêu cầu người dùng: mặc định `False` giữ NGUYÊN
    hành vi cũ (bỏ qua shot đã `ready` — tránh gọi API tốn phí lại khi resume sau lỗi 1
    vài shot, xem `engine.generate_visual_asset`/`generate_narration_asset`). `True` —
    dùng khi đổi cấu hình BrandProfile (giọng mới/style ảnh mới) và cần SINH LẠI TOÀN BỘ
    block, kể cả shot đã có sẵn asset — reset TRƯỚC mọi shot đang `ready` (đúng kind) về
    `"generating"` NGAY TẠI ĐÂY (giống hệt cơ chế `regenerate_visual`/`regenerate_narration`
    bên dưới — router tự reset trước khi dispatch, KHÔNG cần đổi guard trong
    `engine.py`, giữ nguyên hành vi resume mặc định không đổi). Reset `approved=False`
    cho visual bị sinh lại — sinh lại nghĩa là cần duyệt lại, cùng nguyên tắc
    `regenerate_visual`."""
    if kind not in ("both", "visual", "narration"):
        raise HTTPException(400, "kind phải là 'both', 'visual' hoặc 'narration'")
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    shots = pack.get("shots", [])
    if not shots:
        raise HTTPException(400, "Chưa có shot nào — hoàn tất Visual Studio trước")

    state = engine.load_render_state(pdir, project_id)
    engine._ensure_shot_entries(state, shots)
    if force:
        for status in state.shots:
            if kind in ("both", "visual") and status.visual_status == "ready":
                status.visual_status = "generating"
                status.approved = False
            if kind in ("both", "narration") and status.narration_status == "ready":
                status.narration_status = "generating"
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.run_asset_generation, project_id, kind=kind)
    return state.model_dump()


@router.get("/projects/{project_id}/render/status")
def get_render_status(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    return engine.load_render_state(pdir, project_id).model_dump()


@router.get("/projects/{project_id}/render/gpu-status")
def get_gpu_status(project_id: str, db: Session = Depends(get_db)):
    """Trạng thái hàng đợi GPU local (ComfyUI) — không gắn với project cụ thể (GPU dùng
    chung cho cả app), nhưng đặt dưới path project cho nhất quán với các endpoint render
    khác. Frontend poll cái này SONG SONG với render/status khi có shot đang generate,
    hiện "GPU đang bận" thay vì màn hình im lặng."""
    _get_project_or_404(db, project_id)
    return engine.get_local_gpu_status(db)


@router.post("/projects/{project_id}/render/cancel")
def cancel_render(project_id: str, db: Session = Depends(get_db)):
    """Dừng batch sinh asset đang chạy (`render/start` hoặc 1 trong 2 nút sinh lại từng
    shot) — KHÔNG rollback asset đã sinh xong (`ready` giữ nguyên), chỉ dừng các shot
    chưa xong. Với video local (ComfyUI) đang render dở, gọi thêm `/interrupt` để dừng
    NGAY tại GPU — nếu chỉ đặt cờ mà không huỷ job thật, ComfyUI vẫn tiếp tục chạy tới
    khi tự xong (lãng phí GPU, đi ngược mục đích nút Dừng). An toàn khi gọi dù không có
    gì đang chạy (best-effort, không lỗi)."""
    p = _get_project_or_404(db, project_id)
    engine.request_cancel(project_id)
    engine.try_interrupt_local_gpu_job(db)
    pdir = project_dir(p.channel_id, p.id)
    return engine.load_render_state(pdir, project_id).model_dump()


class ApproveBody(BaseModel):
    approved: bool = True


@router.post("/projects/{project_id}/render/shots/{shot_id}/approve")
def approve_shot(project_id: str, shot_id: str, body: ApproveBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này — bấm 'Bắt đầu sinh asset' trước")
    if status.visual_status != "ready":
        raise HTTPException(400, "Shot chưa sinh xong visual — chưa thể duyệt")
    status.approved = body.approved
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.post("/projects/{project_id}/render/approve-all")
def approve_all_shots(project_id: str, db: Session = Depends(get_db)):
    """Header Visual Studio — nút "Duyệt toàn bộ block" (2026-08-17). Duyệt hàng loạt mọi
    shot đã sinh visual xong (`visual_status == "ready"`) mà chưa duyệt — khớp đúng điều
    kiện gate `POST render/assemble` đang kiểm (mục `not_approved` bên dưới), bỏ qua thầm
    lặng shot chưa sẵn sàng thay vì lỗi cả loạt (người dùng có thể duyệt phần đã xong,
    quay lại duyệt nốt phần còn sinh dở sau)."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    for status in state.shots:
        if status.visual_status == "ready":
            status.approved = True
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.post("/projects/{project_id}/render/shots/{shot_id}/regenerate-visual")
def regenerate_visual(project_id: str, shot_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    _find_shot_and_beat(pack, shot_id)  # 404 sớm nếu shot không tồn tại

    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này — bấm 'Bắt đầu sinh asset' trước")
    status.visual_status = "generating"  # reset trước — generate_visual_asset() bỏ qua nếu đang "ready"
    status.approved = False  # sinh lại → cần duyệt lại
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.regenerate_single_visual, project_id, shot_id)
    return state.model_dump()


_IMAGE_EXT_BY_CONTENT_TYPE = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_IMAGE_EXT_BY_SUFFIX = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp"}
_VIDEO_EXT_BY_CONTENT_TYPE = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}
_VIDEO_EXT_BY_SUFFIX = {".mp4": "mp4", ".webm": "webm", ".mov": "mov"}


@router.post("/projects/{project_id}/render/shots/{shot_id}/upload-visual")
async def upload_shot_visual(project_id: str, shot_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload ảnh/video có sẵn từ máy THAY CHO sinh bằng AI cho 1 shot (2026-08-17, theo
    yêu cầu người dùng) — thay thế TẠI CHỖ asset của đúng shot_id (cùng slot file
    `assets/{shot_id}.<ext>` mà `generate_visual_asset` dùng, cùng `ShotRenderStatus`
    trong render.json) để đồng bộ với Pack Review/Output Center, không tạo ID mới.

    Loại file (ảnh/video) PHẢI khớp `shot.visual_type` hiện có trong pack.json — người
    dùng đổi kiểu qua tag Image/Video ở ShotCard (PATCH /visual/shots/{id}, pipeline.py)
    TRƯỚC nếu muốn đổi loại, KHÔNG tự suy luận/ghi đè `visual_type` ở đây: module này
    (`render.py`) chỉ ĐỌC pack.json, không bao giờ ghi lại (xem docstring đầu file) —
    giữ đúng ranh giới script core (pipeline.py) ⟂ render module đã có từ trước."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    shot, _beat = _find_shot_and_beat(pack, shot_id)

    is_video = shot.get("visual_type") == "video"
    ct_map = _VIDEO_EXT_BY_CONTENT_TYPE if is_video else _IMAGE_EXT_BY_CONTENT_TYPE
    suffix_map = _VIDEO_EXT_BY_SUFFIX if is_video else _IMAGE_EXT_BY_SUFFIX
    ext = ct_map.get(file.content_type or "") or suffix_map.get(Path(file.filename or "").suffix.lower())
    if not ext:
        kind_vn = "video (MP4/WEBM/MOV)" if is_video else "ảnh (PNG/JPEG/WEBP)"
        raise HTTPException(400, f"Shot này đang ở kiểu {'video' if is_video else 'ảnh'} — chỉ nhận {kind_vn}. Đổi kiểu (tag Image/Video) trước nếu muốn upload loại khác.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File rỗng")

    state = engine.load_render_state(pdir, project_id)
    by_id = engine._ensure_shot_entries(state, pack.get("shots", []))
    status = by_id[shot_id]

    old_path = Path(status.visual_asset_path) if status.visual_asset_path else None
    new_path = pdir / "assets" / f"{shot_id}.{ext}"
    if old_path and old_path.exists() and old_path != new_path:
        old_path.unlink()  # tránh rác file cũ khác đuôi (VD trước .png giờ upload .jpg)
    write_bytes(new_path, data)

    status.visual_asset_path = str(new_path)
    status.visual_provider = "upload"
    status.visual_status = "ready"
    status.visual_error = None
    status.visual_started_at = None
    status.approved = False  # thay ảnh/video mới → cần duyệt lại
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.post("/projects/{project_id}/render/shots/{shot_id}/regenerate-narration")
def regenerate_narration(project_id: str, shot_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    _find_shot_and_beat(pack, shot_id)

    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này — bấm 'Bắt đầu sinh asset' trước")
    status.narration_status = "generating"
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.regenerate_single_narration, project_id, shot_id)
    return state.model_dump()


_AUDIO_EXT_BY_CONTENT_TYPE = {
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/vnd.wave": "wav",
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/x-mp3": "mp3", "audio/mpeg3": "mp3", "audio/x-mpeg-3": "mp3",
}
_AUDIO_EXT_BY_SUFFIX = {".wav": "wav", ".mp3": "mp3"}


@router.post("/projects/{project_id}/render/intro/upload-visual")
async def upload_intro_visual(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Shot MỞ ĐẦU riêng của project — **mới (2026-08-20)**, theo yêu cầu người dùng.
    Khác `upload_shot_visual` (thay ảnh/video cho 1 shot CÓ SẴN trong kịch bản, phải
    khớp `visual_type` hiện có) — đây là 1 SLOT ĐỘC LẬP, không gắn với script/shot nào,
    tự suy loại (ảnh/video) theo file upload. Nếu điền đủ (video, HOẶC ảnh + audio đi
    kèm bắt buộc — xem `upload_intro_audio`), OVERRIDE HẲN video/audio thương hiệu cấp
    kênh (`BrandProfile.intro_video_path`/`intro_audio_path`) khi ghép MP4 — xem
    `app/render/assembly.py::_resolve_intro_source`."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)

    ct = file.content_type or ""
    suffix = Path(file.filename or "").suffix.lower()
    video_ext = _VIDEO_EXT_BY_CONTENT_TYPE.get(ct) or _VIDEO_EXT_BY_SUFFIX.get(suffix)
    image_ext = _IMAGE_EXT_BY_CONTENT_TYPE.get(ct) or _IMAGE_EXT_BY_SUFFIX.get(suffix)
    if not video_ext and not image_ext:
        raise HTTPException(400, "Chỉ nhận ảnh (PNG/JPEG/WEBP) hoặc video (MP4/WEBM/MOV)")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File rỗng")

    kind = "video" if video_ext else "image"
    ext = video_ext or image_ext
    new_path = pdir / "assets" / f"intro.{ext}"

    state = engine.load_render_state(pdir, project_id)
    if state.intro is None:
        state.intro = IntroAssetStatus()
    old_visual = Path(state.intro.visual_asset_path) if state.intro.visual_asset_path else None
    if old_visual and old_visual.exists() and old_visual != new_path:
        old_visual.unlink()  # tránh rác file cũ khác đuôi/khác loại
    write_bytes(new_path, data)

    state.intro.kind = kind
    state.intro.visual_asset_path = str(new_path)
    state.intro.disabled = False  # upload = người dùng muốn DÙNG intro — huỷ trạng thái "đã bỏ hẳn" nếu có (xem IntroAssetStatus.disabled)
    if kind == "video":
        # Video tự có audio riêng — audio rời (nếu còn sót từ lúc trước đó là ảnh) không
        # còn ý nghĩa, xoá hẳn để tránh trạng thái lửng lơ gây hiểu nhầm.
        old_audio = Path(state.intro.audio_asset_path) if state.intro.audio_asset_path else None
        if old_audio and old_audio.exists():
            old_audio.unlink()
        state.intro.audio_asset_path = None
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.post("/projects/{project_id}/render/intro/upload-audio")
async def upload_intro_audio(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Audio mở đầu riêng của project — **đã đổi (2026-08-20), theo yêu cầu người dùng**:
    upload được ĐỘC LẬP, không còn bắt buộc phải có ảnh trước. Nếu upload audio mà CHƯA
    có ảnh/video mở đầu, lúc ghép sẽ tự dùng ẢNH của shot ĐẦU TIÊN trong project làm hình
    minh hoạ (giống hệt cách video/audio thương hiệu cấp kênh chỉ có audio hoạt động —
    xem `app/render/intro.py::resolve_intro_source`). 400 nếu shot mở đầu hiện đang là
    VIDEO (video tự có audio riêng, không nhận audio rời — xem `upload_intro_visual`)."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)

    state = engine.load_render_state(pdir, project_id)
    if state.intro is None:
        state.intro = IntroAssetStatus()
    if state.intro.visual_asset_path and state.intro.kind == "video":
        raise HTTPException(400, "Shot mở đầu hiện là video — video tự có audio riêng, không cần/nhận audio rời")

    ct = file.content_type or ""
    suffix = Path(file.filename or "").suffix.lower()
    ext = _AUDIO_EXT_BY_CONTENT_TYPE.get(ct) or _AUDIO_EXT_BY_SUFFIX.get(suffix)
    if not ext:
        raise HTTPException(400, "Chỉ nhận audio WAV/MP3")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File audio rỗng")

    old_audio = Path(state.intro.audio_asset_path) if state.intro.audio_asset_path else None
    new_path = pdir / "assets" / f"intro_audio.{ext}"
    if old_audio and old_audio.exists() and old_audio != new_path:
        old_audio.unlink()
    write_bytes(new_path, data)
    state.intro.audio_asset_path = str(new_path)
    state.intro.disabled = False  # cùng lý do upload_intro_visual ở trên
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.delete("/projects/{project_id}/render/intro")
def delete_intro(project_id: str, db: Session = Depends(get_db)):
    """Bỏ HẲN shot mở đầu cho project này — **đổi hành vi (2026-08-22), theo yêu cầu
    người dùng**: TRƯỚC ĐÂY endpoint này chỉ xoá asset riêng của project rồi quay về
    dùng video/audio thương hiệu cấp kênh (fallback ngầm) — giờ Visual Studio hiển thị rõ
    intro thương hiệu như MỘT LỰA CHỌN kế thừa mặc định, nên "Bỏ shot mở đầu" giờ phải
    nghĩa là TẮT HẲN — không dùng brand fallback nữa (`IntroAssetStatus.disabled=True`),
    dù trước đó project đang ở trạng thái nào (đã có asset riêng, hay đang ngầm kế thừa
    brand). XOÁ HẲN file asset riêng của project trên đĩa nếu có (không đụng file
    BrandProfile cấp kênh — endpoint này chỉ từng ghi vào `render.json` của project, chưa
    bao giờ đụng `brandprofile.json`). Muốn dùng lại intro brand mặc định → gọi
    `enable_intro_inherit` bên dưới; muốn dùng asset riêng khác → upload lại (tự bật lại
    `disabled=False`, xem `upload_intro_visual`/`upload_intro_audio`)."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.intro:
        for path_str in (state.intro.visual_asset_path, state.intro.audio_asset_path):
            if path_str and Path(path_str).exists():
                Path(path_str).unlink()
    state.intro = IntroAssetStatus(disabled=True)
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.patch("/projects/{project_id}/render/intro/inherit")
def enable_intro_inherit(project_id: str, db: Session = Depends(get_db)):
    """Dùng lại video/audio thương hiệu cấp kênh làm shot mở đầu — huỷ trạng thái "đã bỏ
    hẳn" (`disabled=True`, xem `delete_intro`) đặt về `False`. **Mới (2026-08-22)**,
    theo yêu cầu người dùng: sau khi bấm "Bỏ shot mở đầu", cần 1 lối quay lại kế thừa
    brand mà KHÔNG phải tự tải file thương hiệu về rồi upload lại thủ công. KHÔNG đụng
    tới field visual/audio riêng của project (nếu có sẵn từ trước — hiếm khi xảy ra qua
    UI vì `delete_intro` luôn xoá sạch trước khi set `disabled=True`, nhưng giữ an toàn
    logic đơn giản: chỉ đổi đúng 1 field)."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.intro is None:
        state.intro = IntroAssetStatus()
    state.intro.disabled = False
    engine.save_render_state(pdir, state)
    return state.model_dump()


class IntroTransitionBody(BaseModel):
    transition_to_next: str = "cut"


@router.patch("/projects/{project_id}/render/intro/transition")
def patch_intro_transition(project_id: str, body: IntroTransitionBody, db: Session = Depends(get_db)):
    """Hiệu ứng chuyển cảnh GIỮA shot mở đầu và shot đầu tiên của kịch bản — **mới
    (2026-08-21)**, theo yêu cầu người dùng. Cùng bảng `TRANSITIONS` dùng cho
    `transition_to_next` giữa 2 shot thường (`pipeline.py::patch_shot`) — validate y hệt.
    Tự tạo `IntroAssetStatus` nếu chưa có (cùng pattern `patch_project_bg_music_volume`
    — chỉnh transition trước khi kịp upload asset mở đầu vẫn hợp lệ, áp dụng ngay khi
    intro có nội dung sau đó)."""
    if body.transition_to_next not in TRANSITIONS:
        raise HTTPException(400, f"Transition không hợp lệ — chỉ nhận: {', '.join(TRANSITIONS)}")
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.intro is None:
        state.intro = IntroAssetStatus()
    state.intro.transition_to_next = body.transition_to_next
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.get("/projects/{project_id}/render/intro/asset/{kind}")
def get_intro_asset(request: Request, project_id: str, kind: str, db: Session = Depends(get_db)):
    if kind not in ("visual", "audio"):
        raise HTTPException(400, "kind phải là visual hoặc audio")
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    path = None
    if state.intro:
        path = state.intro.visual_asset_path if kind == "visual" else state.intro.audio_asset_path
    if not path:
        raise HTTPException(404, "Chưa có asset này")
    return range_file_response(request, path)


@router.post("/projects/{project_id}/render/bg-music/upload")
async def upload_project_bg_music(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Nhạc nền RIÊNG của project — **mới (2026-08-20)**, theo yêu cầu người dùng: khi
    có, OVERRIDE HẲN nhạc nền mặc định cấp kênh (`BrandProfile.bg_music_path`) — xem
    `app/render/bg_music.py::resolve_bg_music_source`. LUÔN audio, cùng pattern
    `upload_intro_audio`. Giữ nguyên `volume` hiện có (nếu đã chỉnh trước đó qua PATCH),
    chỉ thay file."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)

    ct = file.content_type or ""
    suffix = Path(file.filename or "").suffix.lower()
    ext = _AUDIO_EXT_BY_CONTENT_TYPE.get(ct) or _AUDIO_EXT_BY_SUFFIX.get(suffix)
    if not ext:
        raise HTTPException(400, "Chỉ nhận audio WAV/MP3")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File audio rỗng")

    state = engine.load_render_state(pdir, project_id)
    if state.bg_music is None:
        state.bg_music = BgMusicOverride()
    old_path = Path(state.bg_music.asset_path) if state.bg_music.asset_path else None
    new_path = pdir / "assets" / f"bg_music.{ext}"
    if old_path and old_path.exists() and old_path != new_path:
        old_path.unlink()
    write_bytes(new_path, data)
    state.bg_music.asset_path = str(new_path)
    engine.save_render_state(pdir, state)
    return state.model_dump()


class BgMusicVolumeBody(BaseModel):
    volume: float = 0.3


@router.patch("/projects/{project_id}/render/bg-music")
def patch_project_bg_music_volume(project_id: str, body: BgMusicVolumeBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.bg_music is None:
        state.bg_music = BgMusicOverride()
    state.bg_music.volume = body.volume
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.delete("/projects/{project_id}/render/bg-music")
def delete_project_bg_music(project_id: str, db: Session = Depends(get_db)):
    """Bỏ nhạc nền riêng — quay về dùng nhạc nền mặc định cấp kênh (nếu có). Xoá hẳn
    file trên đĩa, cùng nguyên tắc `delete_intro`."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.bg_music and state.bg_music.asset_path and Path(state.bg_music.asset_path).exists():
        Path(state.bg_music.asset_path).unlink()
    state.bg_music = None
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.get("/projects/{project_id}/render/bg-music/asset")
def get_project_bg_music_asset(request: Request, project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    path = state.bg_music.asset_path if state.bg_music else None
    if not path:
        raise HTTPException(404, "Chưa có nhạc nền riêng")
    return range_file_response(request, path)


@router.post("/projects/{project_id}/render/overlay/upload")
async def upload_project_overlay(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Hiệu ứng lớp phủ (overlay, VD mưa/tuyết rơi) RIÊNG của project — **mới
    (2026-08-22)**, theo yêu cầu người dùng: khi có, OVERRIDE HẲN overlay mặc định cấp
    kênh (`BrandProfile.overlay_effect_path`) — xem `app/render/overlay.py::
    resolve_overlay_source`. LUÔN video (mp4/webm/mov, cùng pattern `upload_intro_visual`
    — khác bg-music là audio). Giữ nguyên `opacity` hiện có (nếu đã chỉnh trước đó qua
    PATCH), chỉ thay file."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)

    ct = file.content_type or ""
    suffix = Path(file.filename or "").suffix.lower()
    ext = _VIDEO_EXT_BY_CONTENT_TYPE.get(ct) or _VIDEO_EXT_BY_SUFFIX.get(suffix)
    if not ext:
        raise HTTPException(400, "Chỉ nhận video MP4/WEBM/MOV")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File video rỗng")

    state = engine.load_render_state(pdir, project_id)
    if state.overlay is None:
        state.overlay = OverlayEffectOverride()
    old_path = Path(state.overlay.asset_path) if state.overlay.asset_path else None
    new_path = pdir / "assets" / f"overlay.{ext}"
    if old_path and old_path.exists() and old_path != new_path:
        old_path.unlink()
    write_bytes(new_path, data)
    state.overlay.asset_path = str(new_path)
    engine.save_render_state(pdir, state)
    return state.model_dump()


class OverlayOpacityBody(BaseModel):
    opacity: float = 0.5


@router.patch("/projects/{project_id}/render/overlay")
def patch_project_overlay_opacity(project_id: str, body: OverlayOpacityBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.overlay is None:
        state.overlay = OverlayEffectOverride()
    state.overlay.opacity = body.opacity
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.delete("/projects/{project_id}/render/overlay")
def delete_project_overlay(project_id: str, db: Session = Depends(get_db)):
    """Bỏ overlay riêng — quay về dùng overlay mặc định cấp kênh (nếu có). Xoá hẳn file
    trên đĩa, cùng nguyên tắc `delete_intro`/`delete_project_bg_music`."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.overlay and state.overlay.asset_path and Path(state.overlay.asset_path).exists():
        Path(state.overlay.asset_path).unlink()
    state.overlay = None
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.get("/projects/{project_id}/render/overlay/asset")
def get_project_overlay_asset(request: Request, project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    path = state.overlay.asset_path if state.overlay else None
    if not path:
        raise HTTPException(404, "Chưa có overlay riêng")
    return range_file_response(request, path)


class AssembleBody(BaseModel):
    resolution: Resolution = "1080p"
    codec: Codec = "h264"
    quality: Quality = "medium"
    use_gpu: bool = False  # NVENC — mới (2026-08-17), theo yêu cầu người dùng ("CPU render có vẻ lâu")


@router.get("/render/gpu-encode-status")
def gpu_encode_status():
    """Kiểm tra THẬT có mã hoá được bằng GPU (NVENC) không — encode thử 1 frame bé, KHÔNG
    chỉ tra `ffmpeg -encoders` (encoder có thể ĐĂNG KÝ nhưng driver NVIDIA chưa đủ mới,
    gặp thật khi phát triển tính năng này: RTX 5060 Ti + driver 576.88 báo "Driver does
    not support the required nvenc API version"). Frontend gọi lúc mở màn cấu hình export
    để hiện/ẩn hoặc disable checkbox NGAY, không đợi người dùng bấm "Ghép video" rồi mới
    biết fail — cùng nguyên tắc "báo lỗi sớm" đã áp dụng cho `render/assemble` (mục 43)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {"available": False, "message": "Chưa cài ffmpeg trên máy — xem README.md."}
    ok, message = probe_gpu_encoder(ffmpeg)
    if ok:
        return {"available": True, "message": ""}
    return {"available": False, "message": message or "GPU encode (NVENC) không dùng được trên máy này — dùng CPU thay thế."}


@router.post("/projects/{project_id}/render/assemble")
def start_assemble(project_id: str, background_tasks: BackgroundTasks, body: AssembleBody = AssembleBody(), db: Session = Depends(get_db)):
    """Ghép video — vai trò CÒN LẠI của Render Studio sau khi sinh asset đã chuyển sang
    Visual Studio. KHÔNG còn gate theo `project.status` (2026-08-17, mục 44 — bỏ hẳn
    Gate #2) — điều kiện ghép được kiểm TRỰC TIẾP trên `state.shots` ngay dưới đây (mọi
    shot đã sinh xong visual VÀ đã duyệt), tự nó đã đủ chặt, không cần thêm gate status.
    Cấu hình export (độ phân giải/codec/chất lượng/GPU) — xem
    app/render/assembly.py::RESOLUTION_MAP/CODEC_MAP/CRF_TABLE/resolve_video_codec."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.assembly_status == "assembling":
        raise HTTPException(409, "Đang ghép video rồi — đợi xong hoặc kiểm tra lại sau.")
    if not state.shots:
        raise HTTPException(400, "Chưa sinh asset nào — bấm 'Bắt đầu sinh asset' trước")
    not_ready = [s.shot_id for s in state.shots if s.visual_status != "ready"]
    not_approved = [s.shot_id for s in state.shots if s.visual_status == "ready" and not s.approved]
    if not_ready:
        raise HTTPException(400, f"Còn {len(not_ready)} shot chưa sinh xong visual: {', '.join(not_ready)}")
    if not_approved:
        raise HTTPException(400, f"Còn {len(not_approved)} shot chưa được duyệt: {', '.join(not_approved)}")
    try:
        resolve_video_codec(body.codec, body.use_gpu)  # validate NGAY (400) — không đợi BackgroundTasks mới báo lỗi
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    state.assembly_status = "assembling"
    state.assembly_error = None
    engine.save_render_state(pdir, state)
    background_tasks.add_task(assemble_video, project_id, resolution=body.resolution, codec=body.codec, quality=body.quality, use_gpu=body.use_gpu)
    return state.model_dump()


@router.get("/projects/{project_id}/render/shots/{shot_id}/asset/{kind}")
def get_shot_asset(request: Request, project_id: str, shot_id: str, kind: str, db: Session = Depends(get_db)):
    """Phục vụ file nhị phân (ảnh/video/audio) đã sinh cho 1 shot — render.json chỉ
    lưu đường dẫn filesystem, frontend cần URL HTTP để hiển thị <img>/<video>/<audio>.
    `range_file_response` — mới (2026-08-20) — hỗ trợ tua video/audio preview thật."""
    if kind not in ("visual", "narration"):
        raise HTTPException(400, "kind phải là visual hoặc narration")
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này")
    path = status.visual_asset_path if kind == "visual" else status.narration_asset_path
    if not path:
        raise HTTPException(404, "Chưa sinh asset này")
    return range_file_response(request, path)


@router.get("/projects/{project_id}/render/download")
def download_render(request: Request, project_id: str, db: Session = Depends(get_db)):
    """**Bug thật người dùng báo (2026-08-20)**: player video ở Render Studio không tua
    được — xác nhận nguyên nhân thật là `FileResponse` (Starlette 0.38.6 đang cài) KHÔNG
    hỗ trợ HTTP Range request (đọc thẳng source `starlette/responses.py`, không có 1
    dòng nào xử lý header `Range`), luôn trả nguyên file bất kể trình duyệt seek tới đâu.
    Sửa bằng `range_file_response` (xem `app/rangefile.py`) — tự trả 206 Partial Content
    đúng chuẩn khi có header `Range`, giữ nguyên hành vi cũ (200, nguyên file) khi không
    có Range (VD tải file qua `downloadRenderFile`)."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.assembly_status != "done" or not state.final_video_path:
        raise HTTPException(400, "Chưa ghép xong video")
    # Đuôi file thay đổi theo codec đã chọn lúc ghép (mp4 cho h264/h265, webm cho vp9) —
    # xem app/render/assembly.py::CODEC_MAP — suy ra media_type đúng thay vì cố định mp4.
    ext = state.final_video_path.rsplit(".", 1)[-1].lower()
    media_type = "video/webm" if ext == "webm" else "video/mp4"
    return range_file_response(request, state.final_video_path, filename=f"final.{ext}", media_type=media_type)


@router.get("/projects/{project_id}/render/narration-download")
def download_narration_full(request: Request, project_id: str, db: Session = Depends(get_db)):
    """Ghép + tải giọng đọc TOÀN BỘ script thành 1 file audio — nút riêng ở Script
    Studio, dùng được ngay khi đã sinh xong hết narration (không cần đợi tới Visual
    Studio/Render). Xem `engine.build_narration_download` — 400 kèm thông điệp rõ nếu
    còn block chưa sinh xong."""
    _get_project_or_404(db, project_id)
    try:
        path = engine.build_narration_download(project_id)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return range_file_response(request, path, filename="narration_full.mp3", media_type="audio/mpeg")
