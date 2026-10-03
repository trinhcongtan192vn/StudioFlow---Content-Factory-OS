"""Lưu ảnh/video đã sinh ở Visual Studio vào Kho Tài Nguyên để tái sử dụng cho project
khác CÙNG KÊNH — mới (2026-09-11), theo yêu cầu người dùng. Tái dùng bảng `ProcessedClip`
đã có (thay vì bảng mới riêng) để clip lưu ở đây gán lại được vào shot khác NGAY qua
`assign_vault_clip`/gợi ý semantic search đã có sẵn (xem docstring `models.py::
ProcessedClip.media_kind`/`source_shot_id`).

`ProcessedClip.raw_video_id` là FK NOT NULL — asset Visual Studio không có `RawVideo`
thật (không phải cắt từ video gốc) nên cần 1 `RawVideo` "ảo" đại diện PROJECT
(`get_or_create_project_raw_video`), đặt tên = tên project (khớp đúng ý người dùng "video
nguồn chính là video project"), bị loại khỏi "Raw Library" qua `RawVideo.
source_project_id` (xem `routers/asset_vault.py::list_raw_videos`)."""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.asset_vault.ingest import _new_id, _probe_resolution, index_clip_embedding
from app.config import asset_vault_clips_dir, project_dir
from app.filestore import read_json
from app.models import Channel, Project, ProcessedClip, RawVideo
from app.render import engine
from app.render.media_probe import probe_duration_sec


def _try_index_clip_embedding(db: Session, clip: ProcessedClip) -> None:
    """Bọc `index_clip_embedding` — lỗi (thường gặp nhất: CHƯA cấu hình Embedding
    provider) KHÔNG được chặn hành động "Lưu vào Kho tài nguyên" (asset vẫn lưu tốt,
    tìm được qua keyword search/thủ công — chỉ mất khả năng semantic/auto-fill, đúng
    tinh thần try/except đã dùng cho `match_semantic` ở `render.py::get_vault_candidates`:
    thiếu embedding provider là trạng thái HỢP LỆ, không phải lỗi cần báo người dùng)."""
    try:
        index_clip_embedding(db, clip)
    except Exception:  # noqa: BLE001
        pass


def get_or_create_project_raw_video(db: Session, project: Project) -> RawVideo:
    """Idempotent — 1 hàng `RawVideo` ảo DUY NHẤT cho mỗi project, tạo lúc lưu shot ĐẦU
    TIÊN của project đó vào Kho. `file_path` là placeholder KHÔNG PHẢI file thật (không
    đi qua bất kỳ hàm cắt cảnh/ffprobe trực tiếp trên field này) — chỉ để thoả field
    NOT NULL của model."""
    existing = db.query(RawVideo).filter(RawVideo.source_project_id == project.id).first()
    if existing:
        return existing
    channel = db.query(Channel).filter(Channel.id == project.channel_id).first()
    raw = RawVideo(
        id=_new_id("raw"),
        file_path=f"__visual_studio_project__/{project.id}",
        source_url=None,
        original_filename=project.title,
        import_note="Asset sinh từ Visual Studio — không phải video gốc upload/tải về.",
        status="indexed",
        source_project_id=project.id,
    )
    if channel:
        raw.channels = [channel]
    db.add(raw)
    db.commit()
    db.refresh(raw)
    return raw


def save_shots_to_vault(db: Session, project: Project, shot_ids: list[str]) -> dict:
    """Với mỗi `shot_id`: bỏ qua (vào `skipped`, KHÔNG chặn cả batch — nguyên tắc "lỗi 1
    phần không chặn cả batch" đã dùng xuyên suốt app) nếu chưa sinh xong visual hoặc file
    đã mất trên đĩa. Shot ĐÃ từng lưu (`ShotRenderStatus.saved_to_vault_clip_id` trỏ tới
    1 clip còn tồn tại) → CẬP NHẬT ĐÈ clip cũ (copy file mới, refresh caption/duration/
    resolution, GIỮ NGUYÊN tags/mood_tone/rights_status/usage_count đã có — không mất dữ
    liệu người dùng tự bổ sung). Ngược lại → tạo `ProcessedClip` mới. Trả về
    `{saved: [...], updated: [...], skipped: [{shot_id, reason}]}` (danh sách `shot_id`)."""
    pdir = project_dir(project.channel_id, project.id)
    pack = read_json(pdir / "pack.json") or {}
    pack_shots = {s["shot_id"]: s for s in pack.get("shots", [])}
    state = engine.load_render_state(pdir, project.id)
    by_id = {s.shot_id: s for s in state.shots}

    saved: list[str] = []
    updated: list[str] = []
    skipped: list[dict[str, str]] = []
    project_raw_video: RawVideo | None = None

    for shot_id in shot_ids:
        shot = pack_shots.get(shot_id)
        if not shot:
            skipped.append({"shot_id": shot_id, "reason": "Không tìm thấy shot này."})
            continue
        status = by_id.get(shot_id)
        if not status or status.visual_status != "ready" or not status.visual_asset_path:
            skipped.append({"shot_id": shot_id, "reason": "Shot chưa sinh xong visual."})
            continue
        src_path = Path(status.visual_asset_path)
        if not src_path.exists():
            skipped.append({"shot_id": shot_id, "reason": "File visual không còn tồn tại trên đĩa."})
            continue

        caption = (shot.get("visual_fx") or "").strip()
        media_kind = shot.get("visual_type") or "image"

        existing_clip = None
        if status.saved_to_vault_clip_id:
            existing_clip = db.query(ProcessedClip).filter(ProcessedClip.clip_id == status.saved_to_vault_clip_id).first()

        if existing_clip:
            dest_path = Path(existing_clip.storage_url)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)
            existing_clip.caption = caption
            existing_clip.duration_sec = probe_duration_sec(dest_path) or 0.0
            ffprobe = shutil.which("ffprobe") or ""
            existing_clip.resolution = _probe_resolution(ffprobe, str(dest_path)) if ffprobe else existing_clip.resolution
            existing_clip.media_kind = media_kind
            _try_index_clip_embedding(db, existing_clip)
            db.commit()
            updated.append(shot_id)
            continue

        if project_raw_video is None:
            project_raw_video = get_or_create_project_raw_video(db, project)
        clip_id = _new_id("clip")
        dest_path = asset_vault_clips_dir() / f"{clip_id}{src_path.suffix}"
        shutil.copy2(src_path, dest_path)
        ffprobe = shutil.which("ffprobe") or ""
        clip = ProcessedClip(
            clip_id=clip_id,
            raw_video_id=project_raw_video.id,
            storage_url=str(dest_path),
            duration_sec=probe_duration_sec(dest_path) or 0.0,
            resolution=_probe_resolution(ffprobe, str(dest_path)) if ffprobe else "",
            caption=caption,
            media_kind=media_kind,
            source_shot_id=shot_id,
        )
        channel = db.query(Channel).filter(Channel.id == project.channel_id).first()
        if channel:
            clip.channels = [channel]
        db.add(clip)
        _try_index_clip_embedding(db, clip)
        status.saved_to_vault_clip_id = clip_id
        db.commit()
        saved.append(shot_id)

    engine.save_render_state(pdir, state)
    return {"saved": saved, "updated": updated, "skipped": skipped}
