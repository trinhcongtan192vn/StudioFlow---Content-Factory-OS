"""Ghép các asset đã duyệt (human review) thành 1 MP4 hoàn chỉnh — M2 Production
Layer, bước cuối cùng của `/render`. Gọi ffmpeg qua subprocess (yêu cầu cài ffmpeg
trên PATH máy chạy backend — xem README.md, KHÔNG bundle binary ở đợt này).

Vẫn giữ nguyên tắc tách biệt: chỉ đọc `pack.json` (thứ tự shot theo timestamp,
duration mỗi beat) + `render.json` (đường dẫn asset đã sinh) — không sửa pack.json.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.config import project_dir
from app.db import SessionLocal
from app.filestore import read_json
from app.models import Project
from app.render.engine import _find_beat, load_render_state, save_render_state

SEGMENT_RESOLUTION = "1920:1080"
DEFAULT_BEAT_DURATION_SEC = 5.0


class FfmpegNotFoundError(Exception):
    pass


def _ensure_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FfmpegNotFoundError("Chưa cài ffmpeg trên máy chạy backend — xem README.md mục yêu cầu hệ thống trước khi ghép video.")
    return path


def _beat_duration(beat: dict) -> float:
    start = beat.get("timestamp_sec")
    end = beat.get("end_sec")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
        return float(end - start)
    return DEFAULT_BEAT_DURATION_SEC


def _build_segment(ffmpeg: str, visual_path: str, narration_path: str | None, duration: float, out_path: Path) -> None:
    is_video = visual_path.lower().endswith(".mp4")
    cmd = [ffmpeg, "-y"]
    cmd += ["-i", visual_path] if is_video else ["-loop", "1", "-i", visual_path]
    if narration_path:
        cmd += ["-i", narration_path, "-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-an"]
    cmd += [
        "-t", str(duration),
        "-vf", f"scale={SEGMENT_RESOLUTION}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def assemble_video(project_id: str) -> None:
    """Chạy trong FastAPI BackgroundTasks (app/routers/render.py::POST .../assemble).
    Yêu cầu MỌI shot đã `visual_status=="ready"` VÀ `approved=True` (human review) —
    thiếu 1 shot chưa duyệt sẽ raise lỗi rõ ràng, không ghép thiếu cảnh."""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        pdir = project_dir(p.channel_id, p.id)
        state = load_render_state(pdir, project_id)
        state.assembly_status = "assembling"
        state.assembly_error = None
        save_render_state(pdir, state)

        try:
            ffmpeg = _ensure_ffmpeg()
            pack = read_json(pdir / "pack.json") or {}
            shots = pack.get("shots", [])
            by_id = {s.shot_id: s for s in state.shots}

            segments_dir = pdir / "renders" / "segments"
            segments_dir.mkdir(parents=True, exist_ok=True)
            list_path = pdir / "renders" / "list.txt"
            lines = []
            for i, shot in enumerate(shots):
                status = by_id.get(shot["shot_id"])
                if not status or status.visual_status != "ready" or not status.visual_asset_path:
                    raise RuntimeError(f"Shot {shot['shot_id']} chưa sinh xong visual — không thể ghép.")
                if not status.approved:
                    raise RuntimeError(f"Shot {shot['shot_id']} chưa được duyệt (human review) — không thể ghép.")
                beat = _find_beat(pack, shot)
                duration = _beat_duration(beat)
                narration_path = status.narration_asset_path if status.narration_status == "ready" else None
                seg_path = segments_dir / f"segment_{i:03d}.mp4"
                _build_segment(ffmpeg, status.visual_asset_path, narration_path, duration, seg_path)
                lines.append(f"file '{seg_path.as_posix()}'")

            if not lines:
                raise RuntimeError("Chưa có shot nào để ghép.")
            list_path.write_text("\n".join(lines), encoding="utf-8")

            final_path = pdir / "renders" / "final.mp4"
            concat_cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(final_path)]
            subprocess.run(concat_cmd, capture_output=True, check=True, text=True)

            state.final_video_path = str(final_path)
            state.assembly_status = "done"
        except subprocess.CalledProcessError as e:
            state.assembly_status = "error"
            state.assembly_error = f"ffmpeg lỗi: {(e.stderr or '')[:1000]}"
        except Exception as e:  # noqa: BLE001
            state.assembly_status = "error"
            state.assembly_error = str(e)
        finally:
            save_render_state(pdir, state)
    finally:
        db.close()
