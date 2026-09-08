"""Xuất "Pack" — gói toàn bộ nội dung video ra 1 folder trên máy local (2026-08-26, theo
yêu cầu người dùng: thay thế "Output A" cũ — export markdown/JSON thuần "spec đọc được"
— bằng 1 bundle THỰC DÙNG ĐƯỢC NGAY để dựng video ở nơi khác: transcript SRT chuẩn, bộ
asset ảnh/video từng shot (đặt tên theo `shot_id`), giọng đọc đã ghép thành 1 file mp3
full, và video đã ghép (nếu project đã ghép xong).

Backend chạy LOCAL ngay trên máy người dùng (Electron desktop, §CLAUDE.md) — ghi THẲNG
ra filesystem tại `dest_dir` (đường dẫn tuyệt đối, người dùng chọn qua dialog chọn thư
mục native ở Electron main process, xem `electron/src/main.ts::choose-folder`), không
cần stream file qua HTTP như các endpoint tải file khác trong `render.py`.

Từng phần LỖI RIÊNG (thiếu asset/narration/video) KHÔNG chặn cả export — ghi vào
`skipped` kèm lý do, giữ đúng nguyên tắc "lỗi 1 phần không chặn cả batch" đã dùng ở
`run_asset_generation`/`generate_all_visual` (xem `app/render/engine.py`,
`app/routers/pipeline.py`)."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import project_dir
from app.db import SessionLocal
from app.filestore import read_json
from app.models import Project
from app.render.assembly import _beat_duration, _shot_base_duration
from app.render.engine import _find_beat, build_narration_download, load_render_state
from app.render.schemas import ShotRenderStatus


def _format_srt_timestamp(sec: float) -> str:
    ms_total = max(0, round(sec * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt_text(pack: dict, shots_state: list[ShotRenderStatus]) -> str:
    """Timing = ĐÚNG logic `_shot_base_duration` dùng lúc ghép video (ưu tiên độ dài
    giọng đọc THẬT, fallback timestamp kịch bản khi chưa sinh) — khớp thời điểm thật
    của `narration_full.mp3` xuất cùng bundle này (mỗi shot nối liền nhau không khoảng
    trống, xem `build_narration_download`), để SRT tra đúng track audio đó. Shot không
    có lời thoại (`beat.audio` rỗng — VD shot chỉ hình không lời) KHÔNG tạo cue, nhưng
    vẫn cộng đủ thời lượng vào mốc thời gian chung để các shot SAU không bị lệch."""
    shots = sorted(pack.get("shots", []), key=lambda s: s.get("linked_timestamp_sec") or 0)
    by_id = {s.shot_id: s for s in shots_state}
    lines: list[str] = []
    t = 0.0
    idx = 1
    for shot in shots:
        beat = _find_beat(pack, shot)
        status = by_id.get(shot["shot_id"])
        dur = _shot_base_duration(status, beat) if status else _beat_duration(beat)
        text = (beat.get("audio") or "").strip()
        if text:
            lines.append(f"{idx}\n{_format_srt_timestamp(t)} --> {_format_srt_timestamp(t + dur)}\n{text}\n")
            idx += 1
        t += dur
    return "\n".join(lines)


def export_pack_bundle(project_id: str, dest_dir: str) -> dict:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            raise RuntimeError("Không tìm thấy project")
        pdir = project_dir(p.channel_id, p.id)
        pack = read_json(pdir / "pack.json") or {}
        shots = pack.get("shots", [])
        if not shots:
            raise RuntimeError("Project chưa có shot nào — hoàn tất Visual Studio trước khi xuất Pack.")

        out_dir = Path(dest_dir)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Không tạo/ghi được thư mục đích: {e}") from e

        state = load_render_state(pdir, project_id)
        by_id = {s.shot_id: s for s in state.shots}
        included: list[str] = []
        skipped: list[dict[str, str]] = []

        srt_text = build_srt_text(pack, state.shots)
        (out_dir / "transcript.srt").write_text(srt_text, encoding="utf-8")
        included.append("transcript.srt")

        assets_dir = out_dir / "assets"
        assets_dir.mkdir(exist_ok=True)
        any_asset = False
        for shot in shots:
            status = by_id.get(shot["shot_id"])
            if not status or status.visual_status != "ready" or not status.visual_asset_path:
                continue
            src = Path(status.visual_asset_path)
            if not src.exists():
                continue
            shutil.copy2(src, assets_dir / f"{shot['shot_id']}{src.suffix}")
            any_asset = True
        if any_asset:
            included.append("assets/")
        else:
            skipped.append({"item": "assets/", "reason": "Chưa shot nào sinh xong visual."})

        try:
            narration_path = build_narration_download(project_id)
            shutil.copy2(narration_path, out_dir / "narration_full.mp3")
            included.append("narration_full.mp3")
        except RuntimeError as e:
            skipped.append({"item": "narration_full.mp3", "reason": str(e)})

        if state.assembly_status == "done" and state.final_video_path and Path(state.final_video_path).exists():
            final_src = Path(state.final_video_path)
            shutil.copy2(final_src, out_dir / f"video_final{final_src.suffix}")
            included.append(f"video_final{final_src.suffix}")
        else:
            skipped.append({"item": "video_final", "reason": "Chưa ghép video (hoặc lần ghép gần nhất chưa xong)."})

        return {"dest_dir": str(out_dir), "included": included, "skipped": skipped}
    finally:
        db.close()
