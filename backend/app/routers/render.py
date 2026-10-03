"""Render Studio API — M2 Production Layer (sinh asset thật + ghép MP4).
Module tách biệt script core (specs/09) — mọi endpoint ở đây chỉ ĐỌC pack.json qua
app/render/engine.py, không bao giờ ghi lại vào pack.json.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json, unlink_retrying, write_bytes
from app.models import Project
from app.rangefile import range_file_response
from app.render import engine
from app.render.assembly import (
    Codec,
    Quality,
    Resolution,
    _narration_for_lang,
    assemble_video,
    probe_gpu_encoder,
    resolve_video_codec,
)
from app.render.pack_export import export_pack_bundle
from app.render.short_export import create_short_export, delete_short_export, run_short_export
from app.providers.factory import NoProviderConfiguredError, get_vision
from app.render.schemas import NARRATION_LANGUAGES, BackgroundVideoOverride, BgMusicOverride, CaptionLayer, CharacterReferenceStatus, ImageLayer, IntroAssetStatus, OverlayEffectOverride, RenderState, TranslatedNarrationStatus, VideoLayer
from app.render.transitions import TRANSITIONS
from app.timeutil import vn_isoformat

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


@router.post("/projects/{project_id}/render/shots/{shot_id}/remove-watermark")
def remove_shot_watermark(project_id: str, shot_id: str, background_tasks: BackgroundTasks, mode: str = "auto", db: Session = Depends(get_db)):
    """Xoá watermark khỏi ảnh/video ĐÃ SINH/upload cho 1 shot — tái dùng `app/watermark/`
    (Florence-2 + LaMa) xây cho Kho Tài Nguyên (IMPLEMENTATION_REPORT.md mục 96/97/99).
    Yêu cầu shot đã có asset `visual_status=="ready"`. KHÔNG phát hiện watermark KHÔNG
    coi là lỗi (400/500) — asset gốc giữ NGUYÊN, chỉ ghi `visual_watermark_note` để UI
    báo rõ ràng, tách biệt khỏi `visual_error` (lỗi thật).

    `mode` (2026-09-18) — `"auto"` (mặc định, nút "Xoá watermark" chung): với ẢNH, CHỈ
    chạy nếu `status.visual_provider == "gemini"` (xoá ảnh mặc định luôn vá vị trí góc cố
    định của Gemini/Nano Banana — `watermark/detector.py::gemini_corner_bbox` — áp nhầm
    cho ảnh nguồn khác sẽ làm hỏng 1 vùng ảnh không hề có watermark, xem
    IMPLEMENTATION_REPORT.md mục tương ứng). VIDEO không bị gate này — tự định vị qua
    đa-frame/Florence-2 (không phụ thuộc provider). `"gemini"` (nút riêng "Xoá watermark
    Gemini", CHO CẢ ẢNH LẪN VIDEO — người dùng chủ động xác nhận "asset này có watermark
    Gemini") — ép chạy bất kể `visual_provider`: ảnh dùng `gemini_corner_bbox` như cũ,
    VIDEO cũng CHUYỂN sang dùng thẳng `gemini_corner_bbox` (bỏ qua đa-frame/Florence-2) —
    xem docstring `watermark/pipeline.py::remove_watermark_from_video` `force_gemini` cho
    lý do (đã thử so khớp mẫu template, verify thật cho thấy KHÔNG đáng tin trên nền chi
    tiết, nên quay về vị trí cố định đã verify)."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    shot, _beat = _find_shot_and_beat(pack, shot_id)  # 404 sớm nếu shot không tồn tại

    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này")
    if status.visual_status != "ready" or not status.visual_asset_path:
        raise HTTPException(400, "Shot chưa có ảnh/video sẵn sàng — sinh hoặc upload trước khi xoá watermark.")
    is_video = shot.get("visual_type") == "video"
    if mode == "auto" and not is_video and status.visual_provider != "gemini":
        raise HTTPException(
            400,
            f"Ảnh này không rõ có phải từ Gemini không (provider: {status.visual_provider or 'không rõ'}) — "
            'dùng nút "Xoá watermark Gemini" nếu bạn chắc chắn ảnh có watermark Gemini, hoặc bỏ qua nếu ảnh không có watermark.',
        )
    status.visual_status = "generating"
    status.visual_watermark_note = None
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.remove_shot_watermark, project_id, shot_id, mode)
    return state.model_dump()


@router.post("/projects/{project_id}/render/remove-watermark-all")
def remove_all_shots_watermark(project_id: str, background_tasks: BackgroundTasks, mode: str = "auto", db: Session = Depends(get_db)):
    """Xoá watermark cho MỌI shot đang có ảnh/video sẵn sàng trong project — bỏ qua thầm
    lặng shot chưa sinh xong (cùng nguyên tắc `approve_all_shots`). Tóm tắt kết quả
    (`scanned`/`cleaned`/`no_watermark`/`failed`) trả qua `RenderState.
    watermark_scan_summary` sau khi chạy xong nền — frontend poll như mọi bulk khác.

    `mode` (2026-09-18) — `"auto"` (mặc định, nút "Xoá watermark toàn bộ slot"): CŨNG bỏ
    qua thầm lặng ảnh không rõ nguồn Gemini (không tính vào `scanned`) — video luôn được
    xử lý. `"gemini"` (nút riêng "Xoá watermark Gemini toàn bộ slot") — xử lý MỌI shot
    ready (ảnh lẫn video), không gate provider — xem docstring `engine.py::
    remove_all_shots_watermark`."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    background_tasks.add_task(engine.remove_all_shots_watermark, project_id, mode)
    return state.model_dump()


_IMAGE_EXT_BY_CONTENT_TYPE = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_IMAGE_EXT_BY_SUFFIX = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp"}
_VIDEO_EXT_BY_CONTENT_TYPE = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}
_VIDEO_EXT_BY_SUFFIX = {".mp4": "mp4", ".webm": "webm", ".mov": "mov"}


def _match_ext_for_shot(shot: dict, filename: str, content_type: str | None) -> str | None:
    """Xác định đuôi file chuẩn hoá (`png`/`jpg`/`webp`/`mp4`/`webm`/`mov`) nếu loại file
    (ảnh/video) khớp `shot.visual_type` — `None` nếu sai loại. Tách từ `upload_shot_visual`
    (2026-09-16) để dùng chung cho cả upload 1 shot lẫn upload hàng loạt theo mã block."""
    is_video = shot.get("visual_type") == "video"
    ct_map = _VIDEO_EXT_BY_CONTENT_TYPE if is_video else _IMAGE_EXT_BY_CONTENT_TYPE
    suffix_map = _VIDEO_EXT_BY_SUFFIX if is_video else _IMAGE_EXT_BY_SUFFIX
    return ct_map.get(content_type or "") or suffix_map.get(Path(filename).suffix.lower())


def _upload_shot_visual_core(pdir: Path, status, shot_id: str, ext: str, data: bytes) -> None:
    """Ghi file vào slot cố định `assets/{shot_id}.<ext>` + cập nhật `ShotRenderStatus` —
    KHÔNG tự `save_render_state` (caller quyết định lưu 1 lần lúc nào, để batch upload
    dồn nhiều shot vào 1 lượt ghi thay vì ghi lại toàn bộ render.json mỗi file)."""
    old_path = Path(status.visual_asset_path) if status.visual_asset_path else None
    new_path = pdir / "assets" / f"{shot_id}.{ext}"
    if old_path and old_path.exists() and old_path != new_path:
        unlink_retrying(old_path)  # tránh rác file cũ khác đuôi (VD trước .png giờ upload .jpg)
    write_bytes(new_path, data)

    status.visual_asset_path = str(new_path)
    status.visual_provider = "upload"
    status.visual_status = "ready"
    status.visual_error = None
    status.visual_started_at = None
    status.visual_updated_at = vn_isoformat(datetime.now(timezone.utc))
    status.approved = False  # thay ảnh/video mới → cần duyệt lại


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

    ext = _match_ext_for_shot(shot, file.filename or "", file.content_type)
    if not ext:
        is_video = shot.get("visual_type") == "video"
        kind_vn = "video (MP4/WEBM/MOV)" if is_video else "ảnh (PNG/JPEG/WEBP)"
        raise HTTPException(400, f"Shot này đang ở kiểu {'video' if is_video else 'ảnh'} — chỉ nhận {kind_vn}. Đổi kiểu (tag Image/Video) trước nếu muốn upload loại khác.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File rỗng")

    state = engine.load_render_state(pdir, project_id)
    by_id = engine._ensure_shot_entries(state, pack.get("shots", []))
    status = by_id[shot_id]

    _upload_shot_visual_core(pdir, status, shot_id, ext, data)
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.post("/projects/{project_id}/render/shots/upload-visual-batch")
async def upload_shot_visual_batch(project_id: str, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Upload CẢ FOLDER ảnh/video 1 lần — mới (2026-09-16), theo yêu cầu người dùng: tên
    file (bỏ đuôi mở rộng) PHẢI trùng `shot_id`/mã block (VD `B01.png` → shot `B01`) —
    KHÔNG cần bảng tra cứu, vì `shot_id` chính là mã block (`pipeline.py::
    _seed_shot_from_beat`: `"shot_id": beat.get("block_id") or ...`). File không khớp
    tên shot nào, hoặc khớp tên nhưng sai loại ảnh/video so với `shot.visual_type` (cùng
    validate như `upload_shot_visual`, KHÔNG tự đổi `visual_type`), đều xếp vào
    `unmatched` kèm lý do — KHÔNG chặn các file còn lại (nguyên tắc "lỗi 1 phần không
    chặn cả batch" đã dùng xuyên suốt app). Ghi `render.json` 1 LẦN sau khi xử lý xong
    toàn bộ file (khác `_upload_shot_visual_core` gọi lẻ, tránh ghi lại state nhiều lần)."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    shots = pack.get("shots", [])
    shots_by_id = {s["shot_id"]: s for s in shots}

    state = engine.load_render_state(pdir, project_id)
    by_id = engine._ensure_shot_entries(state, shots)

    matched: list[dict[str, str]] = []
    unmatched: list[dict[str, str]] = []

    for file in files:
        filename = file.filename or ""
        shot_id = Path(filename).stem
        shot = shots_by_id.get(shot_id)
        if not shot:
            unmatched.append({"filename": filename, "reason": f"Không tìm thấy block \"{shot_id}\" trong project này."})
            continue
        ext = _match_ext_for_shot(shot, filename, file.content_type)
        if not ext:
            is_video = shot.get("visual_type") == "video"
            kind_vn = "video" if is_video else "ảnh"
            unmatched.append({"filename": filename, "reason": f"Shot {shot_id} đang ở kiểu {kind_vn} — đổi tag Image/Video của shot trước nếu muốn upload loại khác."})
            continue
        data = await file.read()
        if not data:
            unmatched.append({"filename": filename, "reason": "File rỗng."})
            continue
        _upload_shot_visual_core(pdir, by_id[shot_id], shot_id, ext, data)
        matched.append({"shot_id": shot_id, "filename": filename})

    engine.save_render_state(pdir, state)
    return {"matched": matched, "unmatched": unmatched, "state": state.model_dump()}


@router.delete("/projects/{project_id}/render/shots/{shot_id}/visual")
def remove_shot_visual(project_id: str, shot_id: str, db: Session = Depends(get_db)):
    """Xoá ảnh/video đã sinh/upload/gán cho 1 shot — trả shot về `visual_status="pending"`
    như chưa từng sinh (2026-09-02, theo yêu cầu người dùng: cho phép bỏ 1 asset không ưng
    ý mà không bị buộc phải sinh/upload cái khác ngay). Xoá file trên đĩa (`unlink_retrying`)
    và reset mọi field liên quan — kể cả `linked_clip_id` (chỉ hết gán cho shot này, clip
    trong Kho tư liệu không bị xoá) và `visual_watermark_note`."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    _find_shot_and_beat(pack, shot_id)  # 404 sớm nếu shot không tồn tại

    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này")
    if status.visual_asset_path:
        old_path = Path(status.visual_asset_path)
        if old_path.exists():
            unlink_retrying(old_path)
    status.visual_asset_path = None
    status.visual_provider = None
    status.visual_status = "pending"
    status.visual_error = None
    status.visual_started_at = None
    status.visual_updated_at = None
    status.linked_clip_id = None
    status.approved = False
    status.visual_watermark_note = None
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.get("/projects/{project_id}/render/shots/{shot_id}/vault-candidates")
def get_vault_candidates(project_id: str, shot_id: str, db: Session = Depends(get_db)):
    """Video Slot nguồn "Video từ Kho" (CHANGE_Semantic_BRoll_Asset_Vault.md §7.3) — gợi
    ý clip từ Channel Asset Vault khớp mô tả CHÍNH shot này (`shot.visual_fx`, đọc từ
    pack.json — module này chỉ ĐỌC, không ghi, xem docstring đầu file). Thử semantic
    trước (nếu đã cấu hình Embedding provider + kênh đã index clip nào), rơi về keyword
    khi chưa. Loại clip ĐÃ gán cho SHOT KHÁC trong CHÍNH project này (dedup §5) — chỉ gợi
    ý, KHÔNG tự gán (human-gate).

    **media_kind (2026-09-11)** — chỉ gợi ý clip CÙNG loại với `shot.visual_type` (Kho
    giờ chứa cả ảnh lẫn video, xem `asset_vault/from_visual_studio.py`) — tránh gợi ý
    ảnh cho shot video hoặc ngược lại."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    shot, _beat = _find_shot_and_beat(pack, shot_id)
    description = (shot.get("visual_fx") or "").strip()
    if not description:
        raise HTTPException(400, "Shot này chưa có mô tả Visual/FX để tìm clip khớp.")
    media_kind = shot.get("visual_type") or "image"

    state = engine.load_render_state(pdir, project_id)
    used_clip_ids = {s.linked_clip_id for s in state.shots if s.linked_clip_id and s.shot_id != shot_id}

    from app.asset_vault.matching import apply_dedup, fallback_neutral_broll, match_by_keyword, match_semantic

    candidates: list[tuple] = []
    used_semantic = False
    try:
        semantic = match_semantic(db, p.channel_id, description, media_kind=media_kind)
        if semantic:
            candidates = semantic
            used_semantic = True
    except Exception:  # noqa: BLE001
        pass  # chưa cấu hình Embedding provider, hoặc lỗi gọi — rơi về keyword bên dưới

    if not candidates:
        # match_by_keyword trả kèm điểm chuẩn hoá 0-1 (2026-09-13, xem docstring hàm đó)
        # — cùng thang với match_semantic, để picker hiển thị match score cho CẢ 2 nguồn
        # gợi ý thay vì chỉ semantic như trước.
        candidates = match_by_keyword(db, p.channel_id, description, media_kind=media_kind)

    filtered = apply_dedup([c for c, _ in candidates], used_clip_ids)
    if not filtered:
        fallback = fallback_neutral_broll(db, p.channel_id, media_kind=media_kind)
        filtered = apply_dedup(fallback, used_clip_ids)

    score_by_id = {c.clip_id: s for c, s in candidates}
    # Sắp xếp TƯỜNG MINH theo match score giảm dần (2026-09-13, theo yêu cầu người dùng)
    # — không chỉ dựa vào thứ tự sẵn có từ `match_semantic`/`match_by_keyword` (dù cả 2
    # đều đã sort nội bộ) để đảm bảo đúng ngay cả với `fallback_neutral_broll` (không có
    # điểm — luôn xếp CUỐI danh sách).
    filtered = sorted(filtered, key=lambda c: score_by_id.get(c.clip_id) if score_by_id.get(c.clip_id) is not None else -1, reverse=True)
    return {
        "used_semantic": used_semantic,
        "candidates": [
            {
                "clip_id": c.clip_id,
                "caption": c.caption,
                "duration_sec": c.duration_sec,
                "match_score": score_by_id.get(c.clip_id),
                "rights_status": c.rights_status,
                # Mở rộng (2026-09-13, theo yêu cầu người dùng "hiển thị đủ thông tin
                # giúp chọn visual phù hợp nhất") — các field này đã có sẵn trên chính
                # `ProcessedClip` đang cầm trong tay, y hệt `_clip_out()` ở
                # `asset_vault.py`, chỉ chưa từng được đưa vào response picker này.
                "resolution": c.resolution,
                "tags": json.loads(c.tags or "[]"),
                "mood_tone": c.mood_tone,
                "usage_count": c.usage_count,
                # rights_status mặc định "unverified" không có ý nghĩa cho asset TỰ SINH
                # từ Visual Studio (không phải B-roll có nguồn/license thật) — cờ này cho
                # frontend ẩn badge rights trong trường hợp đó, cùng công thức `_clip_out`.
                "from_visual_studio": bool(c.raw_video and c.raw_video.source_project_id),
            }
            for c in filtered
        ],
    }


class AssignVaultClipBody(BaseModel):
    clip_id: str


@router.post("/projects/{project_id}/render/shots/{shot_id}/assign-vault-clip")
def assign_vault_clip(project_id: str, shot_id: str, body: AssignVaultClipBody, db: Session = Depends(get_db)):
    """Gán 1 clip từ Channel Asset Vault vào shot — hành vi Y HỆT `upload_shot_visual`
    (thay TẠI CHỖ asset của shot, `approved` reset về False) chỉ khác NGUỒN bytes (copy
    từ Asset Vault thay vì nhận từ browser). `linked_clip_id` sống trên
    `ShotRenderStatus` (render.json), KHÔNG trên `Shot` (pack.json) — tránh module này
    phải ghi pack.json (xem docstring đầu file: "chỉ ĐỌC pack.json, không bao giờ ghi
    lại"). Yêu cầu `shot.visual_type` khớp `ProcessedClip.media_kind` của clip đang gán
    (cùng ràng buộc `upload_shot_visual` — người dùng đổi tag Image/Video ở ShotCard
    TRƯỚC nếu cần).

    **media_kind (2026-09-11)** — Kho Tài Nguyên giờ chứa CẢ clip video (cắt từ
    RawVideo) LẪN ảnh (lưu từ Visual Studio, xem `asset_vault/from_visual_studio.py`) —
    check kiểu đổi từ "chỉ nhận video" (chặn cứng theo shot) sang tra clip TRƯỚC rồi so
    `shot.visual_type` với `clip.media_kind` của ĐÚNG clip đang gán."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    state = _assign_vault_clip_core(db, p, shot_id, body.clip_id)
    return state.model_dump()


def _assign_vault_clip_core(db: Session, p: Project, shot_id: str, clip_id: str) -> RenderState:
    """Thân THẬT của `assign_vault_clip` — tách riêng (2026-09-11) để dùng chung với
    `vault-auto-fill-apply` (áp dụng hàng loạt gợi ý đã người dùng duyệt ở màn review,
    xem `_auto_fill_apply`), tránh copy-paste logic gán clip. Raise `HTTPException` khi
    lỗi — caller đơn lẻ (`assign_vault_clip`) để lỗi nổi lên bình thường, caller hàng
    loạt tự try/except từng item (lỗi 1 item không chặn cả batch)."""
    import shutil as _shutil

    from app.models import ProcessedClip, processed_clip_channel

    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    shot, _beat = _find_shot_and_beat(pack, shot_id)

    # Bug thật (2026-09-02, phát hiện lúc user hỏi về hành vi matching sau khi xoá clip) —
    # câu này TỪNG JOIN qua `raw_video_channel` (kênh của raw_video CHA), sót lại từ TRƯỚC
    # khi ProcessedClip có tag kênh RIÊNG (mục 98) — sai theo 2 cách: (1) clip đã tự sửa tag
    # khác raw_video cha sẽ bị lọc SAI, (2) clip mồ côi (raw_video cha đã bị xoá) KHÔNG BAO
    # GIỜ gán được nữa dù vẫn hiện đúng trong danh sách gợi ý (`matching.py` đã fix ở mục
    # 98, nhưng hàm NÀY sót lại query cũ). Đổi sang lọc qua `processed_clip_channel` (tag
    # riêng của clip) cho khớp `matching.py::_clips_for_channel`.
    clip = (
        db.query(ProcessedClip)
        .join(processed_clip_channel, processed_clip_channel.c.clip_id == ProcessedClip.clip_id)
        .filter(ProcessedClip.clip_id == clip_id, processed_clip_channel.c.channel_id == p.channel_id)
        .first()
    )
    if not clip:
        raise HTTPException(404, "Không tìm thấy clip trong Kho tư liệu của kênh này")
    clip_kind = clip.media_kind or "video"
    shot_kind = shot.get("visual_type") or "image"
    if shot_kind != clip_kind:
        raise HTTPException(400, f'Shot này đang ở kiểu "{shot_kind}" — clip trong Kho là "{clip_kind}", không khớp. Đổi tag Image/Video của shot trước.')
    src_path = Path(clip.storage_url)
    if not src_path.exists():
        raise HTTPException(400, "File clip không còn tồn tại trên đĩa")

    state = engine.load_render_state(pdir, p.id)
    by_id = engine._ensure_shot_entries(state, pack.get("shots", []))
    status = by_id[shot_id]

    old_path = Path(status.visual_asset_path) if status.visual_asset_path else None
    new_path = pdir / "assets" / f"{shot_id}{src_path.suffix}"
    if old_path and old_path.exists() and old_path != new_path:
        unlink_retrying(old_path)
    _shutil.copy2(src_path, new_path)

    status.visual_asset_path = str(new_path)
    status.visual_provider = "asset_vault"
    status.visual_status = "ready"
    status.visual_error = None
    status.visual_started_at = None
    status.visual_updated_at = vn_isoformat(datetime.now(timezone.utc))
    status.linked_clip_id = clip.clip_id
    status.approved = False
    engine.save_render_state(pdir, state)

    # Dedup/usage tracking (§5) — tăng usage_count/last_used_at NGAY khi gán (không đợi
    # tới lúc ghép video), khớp thời điểm "đã dùng" thực tế theo góc nhìn người dùng.
    clip.usage_count = (clip.usage_count or 0) + 1
    clip.last_used_at = datetime.utcnow()
    db.commit()

    return state


# Ngưỡng similarity RIÊNG cho auto-fill (2026-09-11, theo yêu cầu người dùng) — CAO HƠN
# `matching.DEFAULT_SIMILARITY_THRESHOLD` (0.65, dùng cho gợi ý thủ công "Video từ Kho"
# từng shot, nơi người dùng LUÔN tự mắt xem qua trước khi bấm chọn) — tính năng bulk/tự
# động này quét NHIỀU shot cùng lúc, chỉ gợi ý match THẬT chắc để giảm case sai người
# dùng phải tự soát kỹ ở màn review.
_AUTO_FILL_THRESHOLD = 0.8


def _resolution_orientation_matches(resolution: str | None, project_format: str | None) -> bool:
    """True nếu khung hình ngang/dọc (suy từ `resolution`, dạng `"WIDTHxHEIGHT"` —
    `asset_vault/ingest.py::_probe_resolution`) khớp `project_format` ("short" → kỳ vọng
    khung DỌC 9:16, khác → kỳ vọng khung NGANG 16:9, cùng cách đọc field đã dùng ở
    `assembly.py`: `(p.format or "long") == "short"`). Thiếu dữ liệu (resolution rỗng/
    không đọc được) → `True` (KHÔNG loại oan candidate chỉ vì thiếu dữ liệu — độ chính
    xác của filter này chỉ là 1 lớp lọc THÊM, không phải điều kiện bắt buộc duy nhất)."""
    if not resolution or "x" not in resolution.lower():
        return True
    try:
        w_str, h_str = resolution.lower().split("x", 1)
        w, h = int(w_str), int(h_str)
    except ValueError:
        return True
    if w <= 0 or h <= 0:
        return True
    is_portrait = h > w
    expects_portrait = (project_format or "long") == "short"
    return is_portrait == expects_portrait


# Trạng thái job quét auto-fill, cấp module, key = project_id — **mới (2026-09-13)**,
# theo yêu cầu người dùng cần thấy tiến trình quét (đang quét gì/tới đâu/bao lâu). Đây
# là job quét CẢ project chứ không gắn với 1 row DB sẵn có (khác `RawVideo.progress_*`),
# và app single-user/local không cần bền vững qua restart hay khoá đa tiến trình — dict
# bộ nhớ đơn giản là đủ, tránh over-engineer thêm 1 bảng SQL chỉ cho state tạm thời.
_AUTO_FILL_JOBS: dict[str, dict] = {}


def _run_vault_auto_fill_scan(project_id: str) -> None:
    from app.db import SessionLocal

    job = _AUTO_FILL_JOBS[project_id]
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            job["status"] = "error"
            job["error"] = "Project không tồn tại."
            return
        pdir = project_dir(p.channel_id, p.id)
        pack = read_json(pdir / "pack.json") or {}
        shots = pack.get("shots", [])
        state = engine.load_render_state(pdir, project_id)
        status_by_id = {s.shot_id: s for s in state.shots}
        used_clip_ids = {s.linked_clip_id for s in state.shots if s.linked_clip_id}

        from app.asset_vault.matching import apply_dedup, match_semantic

        pending_shots = [s for s in shots if not (status_by_id.get(s["shot_id"]) and status_by_id[s["shot_id"]].visual_status == "ready")]
        job["total"] = len(pending_shots)

        suggestions = []
        scanned = 0
        for shot in pending_shots:
            scanned += 1
            job["current"] = scanned
            description = (shot.get("visual_fx") or "").strip()
            job["current_label"] = f"{shot['shot_id']}: {description[:60]}" if description else shot["shot_id"]
            if not description:
                continue
            media_kind = shot.get("visual_type") or "image"
            try:
                candidates = match_semantic(db, p.channel_id, description, threshold=_AUTO_FILL_THRESHOLD, top_k=3, media_kind=media_kind)
            except Exception:  # noqa: BLE001
                # Chưa cấu hình Embedding provider, hoặc lỗi gọi — auto-fill bỏ qua shot
                # này (KHÔNG rơi về keyword search như `get_vault_candidates`: độ tin cậy
                # của keyword match thấp hơn hẳn, không phù hợp cho tính năng TỰ ĐỘNG quét
                # hàng loạt này — người dùng vẫn dùng được "Video từ Kho" thủ công).
                continue
            filtered = apply_dedup([c for c, _ in candidates], used_clip_ids)
            score_by_id = {c.clip_id: s for c, s in candidates}
            best = next((c for c in filtered if _resolution_orientation_matches(c.resolution, p.format)), None)
            if not best:
                continue
            used_clip_ids.add(best.clip_id)
            suggestions.append({
                "shot_id": shot["shot_id"],
                "visual_fx": description,
                "clip_id": best.clip_id,
                "caption": best.caption,
                "media_kind": best.media_kind or "video",
                "resolution": best.resolution,
                "match_score": score_by_id.get(best.clip_id),
            })

        job["status"] = "done"
        job["result"] = {"suggestions": suggestions, "scanned_count": scanned, "matched_count": len(suggestions)}
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)
    finally:
        db.close()


@router.post("/projects/{project_id}/render/vault-auto-fill-scan")
def start_vault_auto_fill_scan(project_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Khởi động quét nền — xem `_run_vault_auto_fill_scan` cho logic thật (y hệt logic
    cũ của `vault-auto-fill-suggestions`, chỉ thêm cập nhật tiến trình mỗi vòng lặp).
    Không khởi động lại nếu đã có job đang "running" cho project này (tránh double-scan
    khi người dùng bấm 2 lần liên tiếp) — trả thẳng trạng thái hiện tại."""
    _get_project_or_404(db, project_id)
    existing = _AUTO_FILL_JOBS.get(project_id)
    if existing and existing["status"] == "running":
        return _auto_fill_job_out(project_id)
    _AUTO_FILL_JOBS[project_id] = {
        "status": "running",
        "current": 0,
        "total": 0,
        "current_label": None,
        "started_at": time.time(),
        "error": None,
        "result": None,
    }
    background_tasks.add_task(_run_vault_auto_fill_scan, project_id)
    return _auto_fill_job_out(project_id)


def _auto_fill_job_out(project_id: str) -> dict:
    job = _AUTO_FILL_JOBS.get(project_id)
    if not job:
        return {"status": "idle"}
    return {**job, "elapsed_sec": round(time.time() - job["started_at"], 1)}


@router.get("/projects/{project_id}/render/vault-auto-fill-scan/status")
def get_vault_auto_fill_scan_status(project_id: str, db: Session = Depends(get_db)):
    """Poll tiến trình quét — xem `start_vault_auto_fill_scan`. `status: "idle"` khi
    project chưa từng quét lần nào."""
    _get_project_or_404(db, project_id)
    return _auto_fill_job_out(project_id)


class VaultAutoFillApplyItem(BaseModel):
    shot_id: str
    clip_id: str


class VaultAutoFillApplyBody(BaseModel):
    items: list[VaultAutoFillApplyItem]


@router.post("/projects/{project_id}/render/vault-auto-fill-apply")
def apply_vault_auto_fill(project_id: str, body: VaultAutoFillApplyBody, db: Session = Depends(get_db)):
    """Áp dụng CÁC gợi ý người dùng đã accept ở màn review (từ `vault-auto-fill-
    suggestions`) — client gửi lại ĐÚNG cặp `(shot_id, clip_id)` đã hiện trên màn hình,
    KHÔNG để backend tự truy vấn lại (tránh lệch dữ liệu nếu Kho đổi giữa lúc quét và
    lúc áp dụng). Lỗi 1 item KHÔNG chặn các item còn lại (nguyên tắc "lỗi 1 phần không
    chặn cả batch"), tái dùng `_assign_vault_clip_core` — hành vi Y HỆT gán thủ công
    từng shot."""
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    applied: list[str] = []
    skipped: list[dict[str, str]] = []
    for item in body.items:
        try:
            _assign_vault_clip_core(db, p, item.shot_id, item.clip_id)
            applied.append(item.shot_id)
        except HTTPException as e:
            skipped.append({"shot_id": item.shot_id, "reason": str(e.detail)})
    return {"applied": applied, "skipped": skipped}


class NarrationSpeedBody(BaseModel):
    speed: float = 1.0


@router.patch("/projects/{project_id}/render/narration-speed")
def patch_narration_speed(project_id: str, body: NarrationSpeedBody, db: Session = Depends(get_db)):
    """Tốc độ phát giọng đọc cho TOÀN BỘ block — nút ở Script Studio (2026-09-02, mục
    109). CHỈ lưu giá trị, KHÔNG tự sinh lại narration đã có sẵn (đúng nguyên tắc "không
    tự chạy ngầm") — người dùng bấm "Sinh giọng đọc cho toàn bộ block" (hoặc sinh lại
    từng shot) SAU khi đổi để asset MỚI áp dụng tốc độ này, xem `engine.py::
    generate_narration_asset`/`_apply_narration_speed`."""
    if not (0.5 <= body.speed <= 2.0):
        raise HTTPException(400, "Tốc độ giọng đọc phải trong khoảng 0.5 – 2.0")
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    state.narration_speed = body.speed
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


def _validate_lang(lang: str) -> None:
    if lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")


@router.post("/projects/{project_id}/render/narration-translations/{lang}/start")
def start_narration_translation_batch(project_id: str, lang: str, background_tasks: BackgroundTasks, force: bool = False, db: Session = Depends(get_db)):
    """Sinh giọng đọc cho 1 NGÔN NGỮ (khác ngôn ngữ chính) cho MỌI shot đã có văn bản
    dịch — nút theo từng ngôn ngữ đang kích hoạt ở Script Studio (giọng đọc đa ngôn ngữ,
    2026-09-04). Cùng pattern `start_render` (`force` reset shot `ready` về `generating`
    trước khi dispatch — dùng khi đổi mẫu giọng clone/BrandProfile và cần sinh lại)."""
    _validate_lang(lang)
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
            translation = status.narration_translations.get(lang)
            if translation is not None and translation.narration_status == "ready":
                translation.narration_status = "generating"
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.run_narration_translation_batch, project_id, lang)
    return state.model_dump()


@router.post("/projects/{project_id}/render/shots/{shot_id}/regenerate-narration-translation/{lang}")
def regenerate_narration_translation(project_id: str, shot_id: str, lang: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Sinh lại giọng đọc 1 NGÔN NGỮ cho ĐÚNG 1 shot (giọng đọc đa ngôn ngữ, 2026-09-04)
    — nút "Tạo giọng đọc" cạnh ô văn bản dịch của ngôn ngữ đang kích hoạt ở Script
    Studio. Cùng pattern `regenerate_narration`."""
    _validate_lang(lang)
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    _find_shot_and_beat(pack, shot_id)

    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này — bấm 'Bắt đầu sinh asset' trước")
    entry = status.narration_translations.get(lang)
    if entry is None:
        entry = TranslatedNarrationStatus()
        status.narration_translations[lang] = entry
    entry.narration_status = "generating"
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.regenerate_single_narration_translation, project_id, shot_id, lang)
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
        unlink_retrying(old_visual)  # tránh rác file cũ khác đuôi/khác loại
    write_bytes(new_path, data)

    state.intro.kind = kind
    state.intro.visual_asset_path = str(new_path)
    state.intro.disabled = False  # upload = người dùng muốn DÙNG intro — huỷ trạng thái "đã bỏ hẳn" nếu có (xem IntroAssetStatus.disabled)
    if kind == "video":
        # Video tự có audio riêng — audio rời (nếu còn sót từ lúc trước đó là ảnh) không
        # còn ý nghĩa, xoá hẳn để tránh trạng thái lửng lơ gây hiểu nhầm.
        old_audio = Path(state.intro.audio_asset_path) if state.intro.audio_asset_path else None
        if old_audio and old_audio.exists():
            unlink_retrying(old_audio)
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
        unlink_retrying(old_audio)
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
                unlink_retrying(Path(path_str))
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


# ---------------------------------------------------------------------------
# Ảnh nhân vật tham khảo (CharacterReferenceStatus) — mới (2026-09-09, mục 127), theo yêu
# cầu người dùng: upload 1 ảnh nhân vật, tự động sinh mô tả qua VisionProvider (CÙNG cơ chế
# Channel Asset Vault dùng để caption clip — xem app/asset_vault/ingest.py::caption_clip),
# mô tả tự nối vào MỌI prompt sinh ảnh của project (xem
# app/render/engine.py::_build_visual_prompt, tham số character_reference_desc). Xem đầy đủ
# bối cảnh/lý do ở docstring CharacterReferenceStatus (render/schemas.py).
# ---------------------------------------------------------------------------
_CHARACTER_REFERENCE_PROMPT = (
    "Describe ONLY the visual design of the main character in this image, in English, in "
    "1-2 concise sentences (about 30-50 words) — focus on distinctive, reusable traits: "
    "head/body shape, hair, face/eyes, colors, clothing, art style. Do NOT describe the "
    "pose, action, or background/scene in this specific image — this description will be "
    "reused to draw the SAME character in different poses and scenes."
)


def _caption_character_reference(db: Session, state: RenderState, image_bytes: bytes) -> None:
    """Gọi VisionProvider sinh `description` — lỗi (chưa cấu hình provider, provider lỗi)
    KHÔNG chặn việc lưu ảnh (khác nhiều nơi khác coi lỗi provider AI là chặn cứng) — ảnh
    tham khảo vẫn hữu ích để NGƯỜI DÙNG tự xem/tự gõ tay `description` qua endpoint PATCH
    bên dưới, ghi rõ lỗi vào `caption_error` để UI hiện thông báo thay vì âm thầm rỗng."""
    assert state.character_reference is not None
    try:
        result = get_vision(db).caption(image_bytes, prompt=_CHARACTER_REFERENCE_PROMPT)
        state.character_reference.description = result.caption.strip()
        state.character_reference.caption_error = None
    except NoProviderConfiguredError as e:
        state.character_reference.caption_error = str(e)
    except Exception as e:  # noqa: BLE001 — lỗi provider AI đa dạng (HTTP/timeout/parse...), không chặn upload
        state.character_reference.caption_error = f"Lỗi sinh mô tả tự động: {e}"


@router.post("/projects/{project_id}/render/character-reference/upload")
async def upload_character_reference(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload ảnh nhân vật tham khảo — TỰ ĐỘNG sinh `description` đồng bộ ngay trong
    request này (không cần polling — 1 ảnh, độ trễ tương đương caption 1 keyframe clip ở
    Asset Vault). Thay THẲNG nếu đã có ảnh trước đó (1 slot duy nhất/project, cùng nguyên
    tắc `upload_intro_visual`)."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)

    ct = file.content_type or ""
    suffix = Path(file.filename or "").suffix.lower()
    ext = _IMAGE_EXT_BY_CONTENT_TYPE.get(ct) or _IMAGE_EXT_BY_SUFFIX.get(suffix)
    if not ext:
        raise HTTPException(400, "Chỉ nhận ảnh PNG/JPEG/WEBP")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File rỗng")

    new_path = pdir / "assets" / f"character_reference.{ext}"
    state = engine.load_render_state(pdir, project_id)
    if state.character_reference is None:
        state.character_reference = CharacterReferenceStatus()
    old_path = Path(state.character_reference.image_path) if state.character_reference.image_path else None
    if old_path and old_path.exists() and old_path != new_path:
        unlink_retrying(old_path)
    write_bytes(new_path, data)
    state.character_reference.image_path = str(new_path)

    _caption_character_reference(db, state, data)
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.post("/projects/{project_id}/render/character-reference/recaption")
def recaption_character_reference(project_id: str, db: Session = Depends(get_db)):
    """Sinh lại `description` từ ảnh ĐÃ CÓ (không upload lại) — dùng khi lần sinh trước lỗi
    (`caption_error`), hoặc muốn thử lại sau khi đổi provider vision ở Cài đặt."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if not state.character_reference or not state.character_reference.image_path:
        raise HTTPException(404, "Chưa có ảnh nhân vật tham khảo nào")
    path = Path(state.character_reference.image_path)
    if not path.exists():
        raise HTTPException(404, "File ảnh không còn tồn tại trên đĩa")
    _caption_character_reference(db, state, path.read_bytes())
    engine.save_render_state(pdir, state)
    return state.model_dump()


class CharacterReferenceDescriptionBody(BaseModel):
    description: str


@router.patch("/projects/{project_id}/render/character-reference/description")
def patch_character_reference_description(project_id: str, body: CharacterReferenceDescriptionBody, db: Session = Depends(get_db)):
    """Sửa tay `description` — VisionProvider không phải lúc nào cũng mô tả đúng ý muốn,
    người dùng có thể tự viết lại/tinh chỉnh sau khi xem kết quả sinh tự động."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.character_reference is None:
        raise HTTPException(404, "Chưa có ảnh nhân vật tham khảo nào")
    state.character_reference.description = body.description.strip()
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.delete("/projects/{project_id}/render/character-reference")
def delete_character_reference(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.character_reference and state.character_reference.image_path:
        path = Path(state.character_reference.image_path)
        if path.exists():
            unlink_retrying(path)
    state.character_reference = None
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.get("/projects/{project_id}/render/character-reference/asset")
def get_character_reference_asset(request: Request, project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if not state.character_reference or not state.character_reference.image_path:
        raise HTTPException(404, "Chưa có ảnh nhân vật tham khảo nào")
    return range_file_response(request, state.character_reference.image_path)


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
        unlink_retrying(old_path)
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
        unlink_retrying(Path(state.bg_music.asset_path))
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
        unlink_retrying(old_path)
    write_bytes(new_path, data)
    state.overlay.asset_path = str(new_path)
    state.overlay.disabled = False  # upload mới → chắc chắn muốn DÙNG overlay, tự bật lại nếu trước đó đang tắt hẳn
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
    """Bỏ HẲN overlay cho project này — **đổi hành vi (2026-09-02), theo yêu cầu người
    dùng, cùng lý do `delete_intro`**: TRƯỚC ĐÂY endpoint này chỉ xoá asset riêng của
    project rồi quay về dùng overlay thương hiệu cấp kênh (fallback ngầm, không có cách
    nào tắt hẳn khi đang kế thừa) — giờ nghĩa là TẮT HẲN
    (`OverlayEffectOverride.disabled=True`), dù trước đó project đang ở trạng thái nào
    (đã có asset riêng, hay đang ngầm kế thừa brand). Xoá hẳn file asset riêng trên đĩa
    nếu có (không đụng overlay BrandProfile cấp kênh). Muốn dùng lại overlay brand mặc
    định → gọi `enable_overlay_inherit` bên dưới; muốn dùng asset riêng khác → upload lại
    (tự bật lại `disabled=False`, xem `upload_project_overlay`)."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.overlay and state.overlay.asset_path and Path(state.overlay.asset_path).exists():
        unlink_retrying(Path(state.overlay.asset_path))
    state.overlay = OverlayEffectOverride(disabled=True)
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.patch("/projects/{project_id}/render/overlay/inherit")
def enable_overlay_inherit(project_id: str, db: Session = Depends(get_db)):
    """Dùng lại overlay thương hiệu cấp kênh — huỷ trạng thái "đã tắt hẳn"
    (`disabled=True`, xem `delete_project_overlay`) đặt về `False`. Không cần body, cùng
    pattern `enable_intro_inherit`."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.overlay is None:
        state.overlay = OverlayEffectOverride()
    state.overlay.disabled = False
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


@router.post("/projects/{project_id}/render/background-video/upload")
async def upload_project_background_video(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Video nền CHUNG cho toàn bộ block — **mới (2026-09-02)**, theo yêu cầu người dùng.
    LUÔN video (mp4/webm/mov, cùng pattern `upload_project_overlay`). KHÔNG có cấp kênh
    mặc định để "inherit" (khác bg_music/overlay) — thuần override của project, xem
    docstring `BackgroundVideoOverride`.

    **Nhiều video (mới 2026-09-02, mục 110)** — mỗi lần gọi THÊM 1 video MỚI vào
    `asset_paths` (KHÔNG còn thay thế tại chỗ như bản cũ 1-video) — tên file gắn mốc
    thời gian mili-giây để không đụng file cũ, cho phép nhiều video cùng đuôi tồn tại
    song song."""
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
    if state.background_video is None:
        state.background_video = BackgroundVideoOverride()
    # `_{len(...)}` cộng thêm mốc mili-giây — 2 lần upload LIÊN TIẾP THẬT NHANH (VD upload
    # nhiều file cùng lúc từ frontend) có thể rơi vào CÙNG 1 mili-giây, riêng mốc thời gian
    # không đủ tránh đè file nhau; độ dài danh sách hiện tại làm hậu tố PHỤ đảm bảo tên
    # luôn khác nhau trong 1 project dù trùng mili-giây. **Thêm hex ngẫu nhiên (2026-09-12)**
    # — `len(...)` một mình KHÔNG đủ an toàn cho 2 request THẬT SỰ song song (mỗi request
    # tự load `state` riêng, đọc `len(...)` TRƯỚC khi request kia kịp append — cùng giá
    # trị độ dài, vẫn đè file nhau) — xem giải thích đầy đủ ở `asset_vault/ingest.py::_new_id`.
    new_path = pdir / "assets" / f"background_video_{int(time.time() * 1000)}_{len(state.background_video.asset_paths)}_{uuid.uuid4().hex[:6]}.{ext}"
    write_bytes(new_path, data)
    state.background_video.asset_paths.append(str(new_path))
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.delete("/projects/{project_id}/render/background-video/{index}")
def delete_project_background_video_item(project_id: str, index: int, db: Session = Depends(get_db)):
    """Bỏ ĐÚNG 1 video nền (theo vị trí `index` trong `asset_paths`, 0-based — khớp thứ
    tự hiện ở danh sách trên UI) — **mới (2026-09-02, mục 110)**, khác `DELETE .../
    background-video` (không kèm index) bỏ HẲN cả danh sách. Xoá hẳn file trên đĩa."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    paths = state.background_video.asset_paths if state.background_video else []
    if index < 0 or index >= len(paths):
        raise HTTPException(404, "Không tìm thấy video nền ở vị trí này")
    removed = paths.pop(index)
    if Path(removed).exists():
        unlink_retrying(Path(removed))
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.delete("/projects/{project_id}/render/background-video")
def delete_project_background_video(project_id: str, db: Session = Depends(get_db)):
    """Bỏ HẲN toàn bộ video nền chung (mọi video trong `asset_paths` + cấu hình random/
    transition) — quay lại yêu cầu MỌI shot phải có visual riêng lúc ghép (hành vi gốc).
    Xoá hẳn MỌI file trên đĩa."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.background_video:
        for path in state.background_video.asset_paths:
            if Path(path).exists():
                unlink_retrying(Path(path))
    state.background_video = None
    engine.save_render_state(pdir, state)
    return state.model_dump()


class BackgroundVideoSettingsBody(BaseModel):
    random_order: Optional[bool] = None
    transition: Optional[str] = None


@router.patch("/projects/{project_id}/render/background-video")
def patch_project_background_video_settings(project_id: str, body: BackgroundVideoSettingsBody, db: Session = Depends(get_db)):
    """Chỉnh `random_order`/`transition` — **mới (2026-09-02, mục 110)**, theo yêu cầu
    người dùng ("cho phép set random loop on/off, cho phép set hiệu ứng chuyển cảnh giữa
    các video"). Body chỉ cần gửi field muốn đổi (field kia giữ nguyên) — cùng tinh thần
    partial-update `PATCH /render/overlay`. Tự tạo `BackgroundVideoOverride` nếu chưa có
    (chỉnh cấu hình TRƯỚC khi kịp upload video vẫn hợp lệ, cùng pattern `bg-music`)."""
    if body.transition is not None and body.transition not in TRANSITIONS:
        raise HTTPException(400, f"Hiệu ứng chuyển cảnh không hợp lệ — chọn 1 trong: {', '.join(TRANSITIONS)}")
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.background_video is None:
        state.background_video = BackgroundVideoOverride()
    if body.random_order is not None:
        state.background_video.random_order = body.random_order
    if body.transition is not None:
        state.background_video.transition = body.transition
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.get("/projects/{project_id}/render/background-video/asset/{index}")
def get_project_background_video_asset(request: Request, project_id: str, index: int, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    paths = state.background_video.asset_paths if state.background_video else []
    if index < 0 or index >= len(paths):
        raise HTTPException(404, "Không tìm thấy video nền ở vị trí này")
    return range_file_response(request, paths[index])


_LAYER_POSITIONS = {
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
}
_LAYER_BLEND_MODES = {"alpha", "screen"}


def _validate_layer_fields(position: str | None, width_pct: float | None, opacity: float | None, blend_mode: str | None = None) -> None:
    if position is not None and position not in _LAYER_POSITIONS:
        raise HTTPException(400, f"Vị trí không hợp lệ — chọn 1 trong: {', '.join(sorted(_LAYER_POSITIONS))}")
    if width_pct is not None and not (0.05 <= width_pct <= 1.0):
        raise HTTPException(400, "Kích thước layer phải trong khoảng 5%–100% chiều rộng khung hình")
    if opacity is not None and not (0.0 <= opacity <= 1.0):
        raise HTTPException(400, "Độ mờ phải trong khoảng 0.0–1.0")
    if blend_mode is not None and blend_mode not in _LAYER_BLEND_MODES:
        raise HTTPException(400, f"Chế độ blend không hợp lệ — chọn 1 trong: {', '.join(sorted(_LAYER_BLEND_MODES))}")


@router.post("/projects/{project_id}/render/layers/upload")
async def upload_project_layer(
    project_id: str,
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    width_pct: float = Form(0.3),
    opacity: float = Form(1.0),
    blend_mode: str = Form("alpha"),
    db: Session = Depends(get_db),
):
    """Layer video ĐỊNH VỊ theo lưới 3x3 (VD voice wave, logo) — **mới (2026-09-02, mục
    112)**, theo yêu cầu người dùng: "thêm layer voice wave (dạng video loop) vào bên
    trên video nền". `blend_mode` — **mới (mục 113)**: `"alpha"` (mặc định) — nguồn CÓ
    SẴN KÊNH ALPHA (WebM VP9/MOV ProRes4444 trong suốt), composite thẳng bằng `overlay`.
    `"screen"` — nguồn NỀN ĐEN ĐẶC (không alpha, VD clip hiệu ứng stock — theo yêu cầu
    người dùng: "tôi chỉ có video layer nền đen thôi, hãy process nền đen"), dùng kỹ
    thuật screen-blend CỤC BỘ đúng vùng layer (khác overlay hiệu ứng lớp phủ — hàm đó
    blend TOÀN khung hình) — xem docstring `VideoLayer`/`assembly.py::_composite_layers`.
    Mỗi lần gọi THÊM 1 layer MỚI vào danh sách `RenderState.layers` (không thay thế —
    cho phép nhiều layer cùng lúc, VD voice wave + logo ở 2 góc khác nhau, mỗi layer có
    thể dùng `blend_mode` khác nhau)."""
    _validate_layer_fields(position, width_pct, opacity, blend_mode)
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
    # `_{len(...)}` cộng mốc mili-giây — cùng lý do tránh đè tên file đã áp dụng cho
    # video nền chung (mục 110): 2 lần upload liên tiếp thật nhanh có thể rơi cùng 1
    # mili-giây, độ dài danh sách hiện tại làm hậu tố phụ đảm bảo luôn khác nhau.
    # Hex ngẫu nhiên (2026-09-12) — `_{len(...)}` một mình không đủ an toàn cho 2 request
    # song song, xem giải thích ở `asset_vault/ingest.py::_new_id`.
    layer_id = f"layer_{int(time.time() * 1000)}_{len(state.layers)}_{uuid.uuid4().hex[:6]}"
    new_path = pdir / "assets" / f"{layer_id}.{ext}"
    write_bytes(new_path, data)
    state.layers.append(VideoLayer(id=layer_id, asset_path=str(new_path), position=position, width_pct=width_pct, opacity=opacity, blend_mode=blend_mode))
    engine.save_render_state(pdir, state)
    return state.model_dump()


class LayerSettingsBody(BaseModel):
    position: Optional[str] = None
    width_pct: Optional[float] = None
    opacity: Optional[float] = None
    blend_mode: Optional[str] = None


@router.patch("/projects/{project_id}/render/layers/{layer_id}")
def patch_project_layer(project_id: str, layer_id: str, body: LayerSettingsBody, db: Session = Depends(get_db)):
    """Đổi vị trí/kích thước/độ mờ/chế độ blend 1 layer đã có — **mới (2026-09-02, mục
    112, `blend_mode` thêm mục 113)**. Body chỉ cần gửi field muốn đổi (field kia giữ
    nguyên), cùng tinh thần `PATCH .../overlay`/`PATCH .../background-video`."""
    _validate_layer_fields(body.position, body.width_pct, body.opacity, body.blend_mode)
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    layer = next((l for l in state.layers if l.id == layer_id), None)
    if not layer:
        raise HTTPException(404, "Không tìm thấy layer này")
    if body.position is not None:
        layer.position = body.position
    if body.width_pct is not None:
        layer.width_pct = body.width_pct
    if body.opacity is not None:
        layer.opacity = body.opacity
    if body.blend_mode is not None:
        layer.blend_mode = body.blend_mode
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.delete("/projects/{project_id}/render/layers/{layer_id}")
def delete_project_layer(project_id: str, layer_id: str, db: Session = Depends(get_db)):
    """Bỏ ĐÚNG 1 layer — **mới (2026-09-02, mục 112)**. Xoá hẳn file trên đĩa."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    layer = next((l for l in state.layers if l.id == layer_id), None)
    if not layer:
        raise HTTPException(404, "Không tìm thấy layer này")
    if Path(layer.asset_path).exists():
        unlink_retrying(Path(layer.asset_path))
    state.layers = [l for l in state.layers if l.id != layer_id]
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.get("/projects/{project_id}/render/layers/{layer_id}/asset")
def get_project_layer_asset(request: Request, project_id: str, layer_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    layer = next((l for l in state.layers if l.id == layer_id), None)
    if not layer:
        raise HTTPException(404, "Không tìm thấy layer này")
    return range_file_response(request, layer.asset_path)


# Layer ẢNH định vị (khác layer VIDEO ở trên) — **mới (2026-09-02, mục 115)**, theo yêu
# cầu người dùng: "Layer ảnh định vị với chức năng tương tự nhưng cho ảnh nền đen hoặc
# không có nền. Ngoài hỗ trợ 9 vị trí layer thì còn hỗ trợ thêm full khung hình". Song
# song hoàn toàn 4 endpoint layer video ở trên, chỉ khác: nhận ẢNH (PNG/JPEG/WEBP, dùng
# lại `_IMAGE_EXT_BY_CONTENT_TYPE`/`_IMAGE_EXT_BY_SUFFIX` — cùng map endpoint upload
# ảnh shot dùng), và `position` có thêm giá trị `"full"` (phủ toàn khung hình).
_IMAGE_LAYER_POSITIONS = _LAYER_POSITIONS | {"full"}


def _validate_image_layer_fields(position: str | None, width_pct: float | None, opacity: float | None, blend_mode: str | None = None) -> None:
    if position is not None and position not in _IMAGE_LAYER_POSITIONS:
        raise HTTPException(400, f"Vị trí không hợp lệ — chọn 1 trong: {', '.join(sorted(_IMAGE_LAYER_POSITIONS))}")
    if width_pct is not None and not (0.05 <= width_pct <= 1.0):
        raise HTTPException(400, "Kích thước layer phải trong khoảng 5%–100% chiều rộng khung hình")
    if opacity is not None and not (0.0 <= opacity <= 1.0):
        raise HTTPException(400, "Độ mờ phải trong khoảng 0.0–1.0")
    if blend_mode is not None and blend_mode not in _LAYER_BLEND_MODES:
        raise HTTPException(400, f"Chế độ blend không hợp lệ — chọn 1 trong: {', '.join(sorted(_LAYER_BLEND_MODES))}")


@router.post("/projects/{project_id}/render/image-layers/upload")
async def upload_project_image_layer(
    project_id: str,
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    width_pct: float = Form(0.3),
    opacity: float = Form(1.0),
    blend_mode: str = Form("alpha"),
    db: Session = Depends(get_db),
):
    """Layer ẢNH ĐỊNH VỊ — **mới (2026-09-02, mục 115)**. `position` — 1 trong 9 ô lưới
    3x3 HOẶC `"full"` (phủ toàn khung hình, bỏ qua `width_pct`). `blend_mode` — cùng
    `"alpha"`/`"screen"` như layer video (xem docstring `ImageLayer`/`assembly.py::
    _composite_image_layers`). Mỗi lần gọi THÊM 1 layer MỚI vào `RenderState.image_
    layers` (list riêng, không chung với layer video)."""
    _validate_image_layer_fields(position, width_pct, opacity, blend_mode)
    p = _get_project_or_404(db, project_id)
    _require_not_in_progress(project_id)
    pdir = project_dir(p.channel_id, p.id)

    ct = file.content_type or ""
    suffix = Path(file.filename or "").suffix.lower()
    ext = _IMAGE_EXT_BY_CONTENT_TYPE.get(ct) or _IMAGE_EXT_BY_SUFFIX.get(suffix)
    if not ext:
        raise HTTPException(400, "Chỉ nhận ảnh PNG/JPEG/WEBP")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File ảnh rỗng")

    state = engine.load_render_state(pdir, project_id)
    # Cùng lý do đặt tên tránh đè file đã áp dụng cho layer video/video nền (mục 110/112).
    # Hex ngẫu nhiên (2026-09-12) — `_{len(...)}` một mình không đủ an toàn cho 2 request
    # song song, xem giải thích ở `asset_vault/ingest.py::_new_id`.
    layer_id = f"imglayer_{int(time.time() * 1000)}_{len(state.image_layers)}_{uuid.uuid4().hex[:6]}"
    new_path = pdir / "assets" / f"{layer_id}.{ext}"
    write_bytes(new_path, data)
    state.image_layers.append(ImageLayer(id=layer_id, asset_path=str(new_path), position=position, width_pct=width_pct, opacity=opacity, blend_mode=blend_mode))
    engine.save_render_state(pdir, state)
    return state.model_dump()


class ImageLayerSettingsBody(BaseModel):
    position: Optional[str] = None
    width_pct: Optional[float] = None
    opacity: Optional[float] = None
    blend_mode: Optional[str] = None


@router.patch("/projects/{project_id}/render/image-layers/{layer_id}")
def patch_project_image_layer(project_id: str, layer_id: str, body: ImageLayerSettingsBody, db: Session = Depends(get_db)):
    """Đổi vị trí/kích thước/độ mờ/chế độ blend 1 layer ảnh đã có — **mới (2026-09-02,
    mục 115)**. Body chỉ cần gửi field muốn đổi (field kia giữ nguyên)."""
    _validate_image_layer_fields(body.position, body.width_pct, body.opacity, body.blend_mode)
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    layer = next((l for l in state.image_layers if l.id == layer_id), None)
    if not layer:
        raise HTTPException(404, "Không tìm thấy layer này")
    if body.position is not None:
        layer.position = body.position
    if body.width_pct is not None:
        layer.width_pct = body.width_pct
    if body.opacity is not None:
        layer.opacity = body.opacity
    if body.blend_mode is not None:
        layer.blend_mode = body.blend_mode
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.delete("/projects/{project_id}/render/image-layers/{layer_id}")
def delete_project_image_layer(project_id: str, layer_id: str, db: Session = Depends(get_db)):
    """Bỏ ĐÚNG 1 layer ảnh — **mới (2026-09-02, mục 115)**. Xoá hẳn file trên đĩa."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    layer = next((l for l in state.image_layers if l.id == layer_id), None)
    if not layer:
        raise HTTPException(404, "Không tìm thấy layer này")
    if Path(layer.asset_path).exists():
        unlink_retrying(Path(layer.asset_path))
    state.image_layers = [l for l in state.image_layers if l.id != layer_id]
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.get("/projects/{project_id}/render/image-layers/{layer_id}/asset")
def get_project_image_layer_asset(request: Request, project_id: str, layer_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    layer = next((l for l in state.image_layers if l.id == layer_id), None)
    if not layer:
        raise HTTPException(404, "Không tìm thấy layer này")
    return range_file_response(request, layer.asset_path)


class CaptionLayerBody(BaseModel):
    enabled: Optional[bool] = None
    position: Optional[str] = None
    size_pct: Optional[float] = None
    opacity: Optional[float] = None
    # `""` (chuỗi rỗng) từ frontend nghĩa là "theo ngôn ngữ đang ghép" — chuẩn hoá về
    # `None` ngay khi nhận (JSON không phân biệt "field không gửi" và "field gửi rỗng"
    # gọn hơn khi field này Optional[str] thay vì thêm cờ riêng).
    lang: Optional[str] = None


def _validate_caption_layer_fields(position: str | None, size_pct: float | None, opacity: float | None, lang: str | None) -> None:
    if position is not None and position not in _LAYER_POSITIONS:
        raise HTTPException(400, f"Vị trí không hợp lệ — chọn 1 trong: {', '.join(sorted(_LAYER_POSITIONS))}")
    if size_pct is not None and not (0.01 <= size_pct <= 0.3):
        raise HTTPException(400, "Kích thước chữ phải trong khoảng 1%–30% chiều cao khung hình")
    if opacity is not None and not (0.0 <= opacity <= 1.0):
        raise HTTPException(400, "Độ mờ phải trong khoảng 0.0–1.0")
    if lang is not None and lang != "" and lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")


@router.patch("/projects/{project_id}/render/caption-layer")
def patch_caption_layer(project_id: str, body: CaptionLayerBody, db: Session = Depends(get_db)):
    """Layer CAPTION (phụ đề cứng burn-in) — **mới (2026-09-12)**, theo yêu cầu người
    dùng: "Bổ sung tính năng cho phép user thêm caption vào video ở bước visual
    studio... chọn 9 vị trí, kích thước, độ mờ tương tự phần Layer video định vị". KHÁC
    `layers`/`image_layers` (list, nhiều instance, upload file) — đây là 1 CẤU HÌNH DUY
    NHẤT/project, KHÔNG có file upload nào (nội dung lấy thẳng từ script) — 1 endpoint
    PATCH duy nhất (partial update, field nào không gửi giữ nguyên), tự tạo
    `state.caption_layer` nếu chưa có (giống `state.bg_music`/`state.overlay` lazy-create).
    Bật/tắt qua field `enabled` — không cần endpoint DELETE riêng."""
    _validate_caption_layer_fields(body.position, body.size_pct, body.opacity, body.lang)
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    layer = state.caption_layer or CaptionLayer()
    if body.enabled is not None:
        layer.enabled = body.enabled
    if body.position is not None:
        layer.position = body.position
    if body.size_pct is not None:
        layer.size_pct = body.size_pct
    if body.opacity is not None:
        layer.opacity = body.opacity
    if body.lang is not None:
        layer.lang = body.lang or None
    state.caption_layer = layer
    engine.save_render_state(pdir, state)
    return state.model_dump()


class AssembleBody(BaseModel):
    resolution: Resolution = "1080p"
    codec: Codec = "h264"
    quality: Quality = "medium"
    use_gpu: bool = False  # NVENC — mới (2026-08-17), theo yêu cầu người dùng ("CPU render có vẻ lâu")
    # Ngôn ngữ xuất video (2026-09-11) — `None` → ngôn ngữ chính của kênh. `start_assemble`
    # dưới CHẶN CỨNG (400) nếu giọng đọc ngôn ngữ này chưa sinh hết cho mọi shot — theo
    # yêu cầu người dùng, xem `assembly.py::assemble_video` docstring cho thiết kế đầy đủ.
    lang: str | None = None


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
    # Chỉ chặn 409 khi TIẾN TRÌNH THẬT SỰ đang chạy (`is_assembly_in_progress`, cờ trong
    # bộ nhớ — mới 2026-09-02, mục 111), KHÔNG còn tin mù quáng `state.assembly_status`
    # đã lưu — field đó có thể bị KẸT "assembling" mãi mãi nếu thread ghép chết lặng giữa
    # chừng (bug thật đã gặp, xem docstring `assembly.py::assemble_video`), tự phục hồi
    # được khi khởi động lại app HOẶC khi cờ tự dọn qua `finally`, không cần sửa tay nữa.
    if state.assembly_status == "assembling" and engine.is_assembly_in_progress(project_id):
        raise HTTPException(409, "Đang ghép video rồi — đợi xong hoặc kiểm tra lại sau.")
    if not state.shots:
        raise HTTPException(400, "Chưa sinh asset nào — bấm 'Bắt đầu sinh asset' trước")
    has_background_video = bool(state.background_video and state.background_video.asset_paths)
    not_ready = [
        s.shot_id for s in state.shots
        if s.visual_status != "ready" and not (has_background_video and not s.visual_asset_path)
    ]
    if not_ready:
        raise HTTPException(400, f"Còn {len(not_ready)} shot chưa sinh xong visual: {', '.join(not_ready)}")
    # Không còn gate theo `approved` (2026-09-02, theo yêu cầu người dùng — bỏ luồng
    # duyệt block, chỉ cần visual "ready" là ghép được, xem thêm assembly.py Pass 1).
    try:
        resolve_video_codec(body.codec, body.use_gpu)  # validate NGAY (400) — không đợi BackgroundTasks mới báo lỗi
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if body.lang is not None and body.lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")

    # Ngôn ngữ xuất video (2026-09-11, theo yêu cầu người dùng: "nếu giọng đọc của ngôn
    # ngữ được chọn chưa sinh hết, hiển thị cho user biết và KHÔNG cho render") — chặn
    # CỨNG (400) giống hệt cách gate visual ở trên, KHÁC lần đầu thiết kế tính năng này
    # (ban đầu chỉ cảnh báo, không chặn — user sau đó yêu cầu đổi thành chặn cứng).
    brand = engine._load_brand_profile(p.channel_id)
    primary_language = brand.get("primary_language") or "vi"
    export_lang = body.lang if body.lang in NARRATION_LANGUAGES else primary_language
    missing_narration = [s.shot_id for s in state.shots if _narration_for_lang(s, export_lang, primary_language)[0] != "ready"]
    if missing_narration:
        raise HTTPException(400, f"Giọng đọc [{export_lang}] chưa sinh xong cho {len(missing_narration)} shot: {', '.join(missing_narration[:5])}{'...' if len(missing_narration) > 5 else ''} — sinh xong giọng đọc ở ngôn ngữ này (Script Studio/Visual Studio) trước khi ghép.")

    state.assembly_status = "assembling"
    state.assembly_error = None
    engine.save_render_state(pdir, state)
    background_tasks.add_task(assemble_video, project_id, resolution=body.resolution, codec=body.codec, quality=body.quality, use_gpu=body.use_gpu, lang=body.lang)
    return state.model_dump()


@router.post("/projects/{project_id}/render/assemble/reset")
def reset_stuck_assembly(project_id: str, db: Session = Depends(get_db)):
    """Đặt lại `assembly_status` bị KẸT "assembling" — **mới (2026-09-02, mục 111)**,
    theo yêu cầu người dùng ("giải pháp để xử lý ở tầng UI cho user biết và làm"). Nút
    "Đặt lại tiến trình bị treo" ở RenderStudio.tsx, hiện SUỐT lúc `assembly_status==
    "assembling"` — cho phép người dùng tự phục hồi NGAY TRONG UI thay vì phải nhờ can
    thiệp tay vào render.json như bug thật đã gặp (xem docstring `assembly.py::
    assemble_video`).

    409 nếu `is_assembly_in_progress` vẫn `True` — đang chạy THẬT SỰ (không phải kẹt),
    tránh người dùng vô tình đặt lại 1 tiến trình đang xử lý ngon lành (VD chỉ đang ở
    bước dựng video nền chung lâu vì video dài, KHÔNG phải bị treo). Không xoá file trung
    gian đã dựng dở (`renders/segments/`) — lần ghép lại sau tự ghi đè (`-y`), không cần
    dọn tay."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if engine.is_assembly_in_progress(project_id):
        raise HTTPException(409, "Tiến trình ghép vẫn đang chạy thật — đợi thêm hoặc thử lại sau nếu nghi ngờ bị treo.")
    if state.assembly_status != "assembling":
        raise HTTPException(400, "Không có tiến trình ghép nào đang kẹt để đặt lại.")
    state.assembly_status = "error"
    state.assembly_error = "Đã đặt lại thủ công — tiến trình ghép trước đó có vẻ bị treo (không tiến triển trong thời gian dài)."
    state.assembly_progress = None
    state.assembly_started_at = None
    engine.save_render_state(pdir, state)
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


@router.get("/projects/{project_id}/render/shots/{shot_id}/asset/narration/{lang}")
def get_shot_narration_translation_asset(request: Request, project_id: str, shot_id: str, lang: str, db: Session = Depends(get_db)):
    """Phục vụ file audio giọng đọc NGÔN NGỮ KHÁC ngôn ngữ chính cho 1 shot — giọng đọc
    đa ngôn ngữ (2026-09-04). Xem `get_shot_asset` ở trên cho ngôn ngữ chính."""
    if lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này")
    translation = status.narration_translations.get(lang)
    if not translation or not translation.narration_asset_path:
        raise HTTPException(404, "Chưa sinh giọng đọc ngôn ngữ này")
    return range_file_response(request, translation.narration_asset_path)


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


@router.get("/projects/{project_id}/render/narration-download/{lang}")
def download_narration_full_lang(request: Request, project_id: str, lang: str, db: Session = Depends(get_db)):
    """Ghép + tải giọng đọc TOÀN BỘ script cho 1 NGÔN NGỮ CỤ THỂ — giọng đọc đa ngôn ngữ
    (2026-09-04). Xem `download_narration_full` ở trên cho ngôn ngữ chính, `engine.
    build_narration_download` cho logic ghép."""
    if lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")
    _get_project_or_404(db, project_id)
    try:
        path = engine.build_narration_download(project_id, lang=lang)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return range_file_response(request, path, filename=f"narration_full_{lang}.mp3", media_type="audio/mpeg")


class ShortExportCreateBody(BaseModel):
    start_block_id: str
    end_block_id: str
    regenerate_images: bool = False
    # Ngôn ngữ giọng đọc dùng để xuất short-video — mới (2026-09-12), theo yêu cầu người
    # dùng ("cho phép chọn ngôn ngữ khi xuất short-video, tương tự như khi render
    # long-video"). `None`/bỏ qua → ngôn ngữ chính của kênh. Validate + gate cứng (400
    # nếu giọng đọc CHƯA sinh xong cho shot trong khoảng) nằm trong `create_short_export`.
    lang: str | None = None


@router.post("/projects/{project_id}/render/short-export")
def create_short_export_endpoint(project_id: str, background_tasks: BackgroundTasks, body: ShortExportCreateBody, db: Session = Depends(get_db)):
    """Xuất short-video 9:16 từ 1 khoảng block — **mới (2026-09-12)**, Output Center.
    Xem docstring `ShortVideoExport` (render/schemas.py) + `render/short_export.py` cho
    thiết kế đầy đủ. `GET .../render/status` (đã có sẵn, frontend poll liên tục) tự
    nhiên trả kèm `short_exports` — không cần endpoint GET riêng cho tiến độ."""
    p = _get_project_or_404(db, project_id)
    try:
        export = create_short_export(db, p, body.start_block_id.strip(), body.end_block_id.strip(), body.regenerate_images, lang=body.lang)
    except ValueError as e:
        raise HTTPException(400, str(e))
    background_tasks.add_task(run_short_export, project_id, export.id)
    pdir = project_dir(p.channel_id, p.id)
    return engine.load_render_state(pdir, project_id).model_dump()


@router.delete("/projects/{project_id}/render/short-export/{export_id}")
def delete_short_export_endpoint(project_id: str, export_id: str, db: Session = Depends(get_db)):
    """Xoá 1 short-video đã xuất — giải phóng lại 1 trong `MAX_SHORT_EXPORTS_PER_PROJECT`
    slot."""
    p = _get_project_or_404(db, project_id)
    try:
        state = delete_short_export(p, export_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return state.model_dump()


@router.get("/projects/{project_id}/render/short-export/{export_id}/download")
def download_short_export(request: Request, project_id: str, export_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    export = next((e for e in state.short_exports if e.id == export_id), None)
    if not export or export.status != "done" or not export.video_path:
        raise HTTPException(400, "Short-video này chưa xuất xong.")
    ext = export.video_path.rsplit(".", 1)[-1].lower()
    media_type = "video/webm" if ext == "webm" else "video/mp4"
    # Hậu tố ngôn ngữ trong tên file tải về — mới (2026-09-12), khớp quy ước
    # `pack_export.py::export_pack_bundle` (2 export cùng khoảng block khác ngôn ngữ cần
    # tên file phân biệt được). `export.lang` có thể `None` với export CŨ tạo trước tính
    # năng chọn ngôn ngữ — fallback ngôn ngữ chính của kênh.
    lang = export.lang or (engine._load_brand_profile(p.channel_id).get("primary_language") or "vi")
    filename = f"short_{export.start_block_id}-{export.end_block_id}_{lang}.{ext}"
    return range_file_response(request, export.video_path, filename=filename, media_type=media_type)


class ExportPackBundleBody(BaseModel):
    dest_dir: str


@router.post("/projects/{project_id}/export/pack-bundle")
def export_pack_bundle_endpoint(project_id: str, body: ExportPackBundleBody, db: Session = Depends(get_db)):
    """Nút "Xuất Pack" — gói toàn bộ nội dung video ra 1 folder trên máy local (thay
    "Output A" cũ, xem `app/render/pack_export.py`). `dest_dir` là đường dẫn tuyệt đối
    người dùng chọn qua dialog chọn thư mục native (Electron) — backend ghi thẳng ra
    filesystem, không trả file qua HTTP."""
    _get_project_or_404(db, project_id)
    if not body.dest_dir.strip():
        raise HTTPException(400, "Chưa chọn thư mục đích.")
    try:
        return export_pack_bundle(project_id, body.dest_dir)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
