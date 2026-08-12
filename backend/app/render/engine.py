"""Sinh asset thật (ảnh/video + giọng đọc) cho từng shot — M2 Production Layer.

Nguyên tắc tách biệt (specs/09 "Chống coupling: script core ⟂ render module"): module
này CHỈ ĐỌC `pack.json` (script/shots đã duyệt qua Gate #2, brand), KHÔNG BAO GIỜ ghi
lại vào đó — mọi trạng thái sinh asset sống trong `render.json` riêng (app/render/
schemas.py). Chạy trong FastAPI BackgroundTasks (app/routers/render.py) — KHÔNG block
request thread, vì video (Sora) có thể mất vài phút để hoàn tất.
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import SessionLocal
from app.filestore import read_json, write_bytes, write_json
from app.models import Project
from app.providers.base import VideoProvider
from app.providers.factory import NoProviderConfiguredError, get_image_chain, get_tts_chain, get_video_chain
from app.providers.image_gemini import estimate_cost as estimate_gemini_image_cost
from app.providers.image_openai import estimate_cost as estimate_openai_image_cost
from app.providers.tts_elevenlabs import estimate_cost as estimate_elevenlabs_tts_cost
from app.providers.tts_gemini import estimate_cost as estimate_gemini_tts_cost
from app.providers.video_sora import estimate_cost as estimate_sora_video_cost
from app.providers.video_veo import estimate_cost as estimate_veo_video_cost
from app.render.schemas import RenderState, ShotRenderStatus
from app.routers.pipeline import record_asset_usage

VIDEO_POLL_INTERVAL_SEC = 10
VIDEO_MAX_WAIT_SEC = 480  # 8 phút — khớp giới hạn ghi trong plan

# Mỗi task tra đúng hàm ước tính chi phí theo provider THẬT SỰ THÀNH CÔNG trong chain
# fallback (không biết trước sẽ là default hay fallback) — xem _candidate_configs()
# trong factory.py.
_IMAGE_COST_FN = {"openai": estimate_openai_image_cost, "gemini": estimate_gemini_image_cost}
_VIDEO_COST_FN = {"sora": estimate_sora_video_cost, "veo": estimate_veo_video_cost}
_TTS_COST_FN = {"elevenlabs": estimate_elevenlabs_tts_cost, "gemini": estimate_gemini_tts_cost}

# ElevenLabs trả MP3, Gemini TTS trả WAV (tự bọc từ PCM thô — xem tts_gemini.py) —
# đuôi file SAI khiến FileResponse (app/routers/render.py::get_shot_asset) đoán nhầm
# Content-Type theo phần mở rộng, browser phát âm thanh có thể lỗi.
_TTS_EXT = {"elevenlabs": "mp3", "gemini": "wav"}


def _render_path(pdir):
    return pdir / "render.json"


def load_render_state(pdir, project_id: str) -> RenderState:
    data = read_json(_render_path(pdir))
    if data:
        return RenderState.model_validate(data)
    return RenderState(project_id=project_id)


def save_render_state(pdir, state: RenderState) -> None:
    write_json(_render_path(pdir), state.model_dump())


def _find_beat(pack: dict, shot: dict) -> dict:
    body = (pack.get("script") or {}).get("body", [])
    return next((b for b in body if b.get("timestamp_sec") == shot.get("linked_timestamp_sec")), body[0] if body else {})


def _ensure_shot_entries(state: RenderState, shots: list[dict]) -> dict[str, ShotRenderStatus]:
    by_id = {s.shot_id: s for s in state.shots}
    for shot in shots:
        if shot["shot_id"] not in by_id:
            entry = ShotRenderStatus(shot_id=shot["shot_id"])
            state.shots.append(entry)
            by_id[shot["shot_id"]] = entry
    return by_id


def run_asset_generation(project_id: str) -> None:
    """Sinh visual + narration cho MỌI shot của project chưa `ready`. Lỗi ở 1 shot
    KHÔNG dừng cả batch — ghi vào *_error, tiếp tục shot kế tiếp (người dùng có thể tự
    bấm "Tạo lại" riêng cho shot lỗi sau, xem app/routers/render.py)."""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        pdir = project_dir(p.channel_id, p.id)
        pack = read_json(pdir / "pack.json") or {}
        shots = pack.get("shots", [])

        state = load_render_state(pdir, project_id)
        by_id = _ensure_shot_entries(state, shots)
        save_render_state(pdir, state)

        for shot in shots:
            status = by_id[shot["shot_id"]]
            beat = _find_beat(pack, shot)

            generate_visual_asset(db, p, pdir, shot, beat, status)
            save_render_state(pdir, state)

            generate_narration_asset(db, p, pdir, beat, status)
            save_render_state(pdir, state)

        db.commit()
    finally:
        db.close()


def regenerate_single_visual(project_id: str, shot_id: str) -> None:
    """Sinh lại visual cho ĐÚNG 1 shot — dùng cho BackgroundTasks trong
    app/routers/render.py. Tự mở/đóng session riêng (KHÔNG dùng session request-scoped
    của FastAPI `Depends(get_db)` — session đó đã bị đóng ngay khi response được trả
    về, TRƯỚC KHI BackgroundTasks thực thi; dùng lại sẽ lỗi "session is closed")."""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        pdir = project_dir(p.channel_id, p.id)
        pack = read_json(pdir / "pack.json") or {}
        shot = next((s for s in pack.get("shots", []) if s["shot_id"] == shot_id), None)
        if not shot:
            return
        beat = _find_beat(pack, shot)

        state = load_render_state(pdir, project_id)
        by_id = _ensure_shot_entries(state, pack.get("shots", []))
        status = by_id[shot_id]
        generate_visual_asset(db, p, pdir, shot, beat, status)
        save_render_state(pdir, state)
        db.commit()
    finally:
        db.close()


def regenerate_single_narration(project_id: str, shot_id: str) -> None:
    """Tương đương regenerate_single_visual() nhưng cho narration."""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        pdir = project_dir(p.channel_id, p.id)
        pack = read_json(pdir / "pack.json") or {}
        shot = next((s for s in pack.get("shots", []) if s["shot_id"] == shot_id), None)
        if not shot:
            return
        beat = _find_beat(pack, shot)

        state = load_render_state(pdir, project_id)
        by_id = _ensure_shot_entries(state, pack.get("shots", []))
        status = by_id[shot_id]
        generate_narration_asset(db, p, pdir, beat, status)
        save_render_state(pdir, state)
        db.commit()
    finally:
        db.close()


def _poll_video_until_done(provider: VideoProvider, job_id: str) -> bytes:
    waited = 0
    while waited < VIDEO_MAX_WAIT_SEC:
        status, data = provider.poll_generation(job_id)
        if data is not None:
            return data
        time.sleep(VIDEO_POLL_INTERVAL_SEC)
        waited += VIDEO_POLL_INTERVAL_SEC
    raise RuntimeError(f"Video job {job_id} quá thời gian chờ ({VIDEO_MAX_WAIT_SEC}s) — thử lại sau hoặc kiểm tra trạng thái job phía provider.")


def _video_duration_sec(beat: dict) -> int:
    """Ước tính thời lượng clip video cần sinh từ độ dài beat script (end_sec -
    timestamp_sec) — clamp về khoảng hợp lý (4-20s) vì chưa rõ Sora chấp nhận giá trị
    nào chính xác (rủi ro đã ghi trong plan); nếu API từ chối, lỗi sẽ hiện rõ qua
    raise_for_status_with_body() khi thử thật."""
    start = beat.get("timestamp_sec")
    end = beat.get("end_sec")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
        return 8
    return max(4, min(20, round(end - start)))


def generate_visual_asset(db: Session, p: Project, pdir, shot: dict, beat: dict, status: ShotRenderStatus) -> None:
    """Sinh 1 asset hình/video cho 1 shot — dùng chung cho batch (run_asset_generation)
    và regenerate 1 shot riêng lẻ (app/routers/render.py). Bỏ qua nếu đã `ready` —
    tránh gọi API tốn phí lại khi `run_asset_generation` chạy lần 2 (VD sau khi 1 vài
    shot khác lỗi); muốn sinh lại 1 shot ĐÃ ready thì gọi trực tiếp từ endpoint
    regenerate (không qua đường batch này).

    Thử LẦN LƯỢT từng provider trong chain (mặc định trước, fallback sau nếu có cấu
    hình — `factory.py::get_image_chain`/`get_video_chain`) — dừng ở provider đầu
    tiên gọi API thành công; chỉ báo lỗi khi TẤT CẢ đều lỗi, gộp lý do từng lần thử."""
    if status.visual_status == "ready":
        return
    status.visual_status = "generating"
    status.visual_error = None
    prompt = shot.get("visual_fx", "")
    is_video = shot.get("visual_type") == "video"
    try:
        providers = get_video_chain(db) if is_video else get_image_chain(db)
    except NoProviderConfiguredError as e:
        status.visual_status = "error"
        status.visual_error = str(e)
        return

    errors = []
    for provider in providers:
        try:
            if is_video:
                seconds = _video_duration_sec(beat)
                job_id = provider.start_generation(prompt, seconds=seconds)
                data = _poll_video_until_done(provider, job_id)
                ext = "mp4"
                cost = _VIDEO_COST_FN.get(provider.provider_name, estimate_sora_video_cost)(seconds, getattr(provider, "model_name", ""))
                unit_label = f"1 video (~{seconds}s)"
            else:
                data = provider.generate(prompt)
                ext = "png"
                cost = _IMAGE_COST_FN.get(provider.provider_name, estimate_openai_image_cost)(1, getattr(provider, "model_name", ""))
                unit_label = "1 ảnh"

            path = pdir / "assets" / f"{shot['shot_id']}.{ext}"
            write_bytes(path, data)
            status.visual_asset_path = str(path)
            status.visual_provider = provider.provider_name
            status.visual_status = "ready"
            status.visual_error = None
            record_asset_usage(db, p.channel_id, p.title, provider=provider.provider_name, stage="visual", unit_label=unit_label, cost=cost)
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"{provider.provider_name}: {e}")

    status.visual_status = "error"
    status.visual_error = "; ".join(errors)


def generate_narration_asset(db: Session, p: Project, pdir, beat: dict, status: ShotRenderStatus) -> None:
    """Sinh 1 clip giọng đọc — TTS hoá LỜI THOẠI THẬT (`beat.audio`), KHÔNG PHẢI
    `shot.audio_sfx` (đó là mô tả nhạc nền/cảm xúc, không phải lời đọc — xem
    specs/07 mục 7). `audio_sfx`/`direction` chỉ dùng làm gợi ý emotion. Bỏ qua nếu đã
    `ready` — cùng lý do tránh tốn phí lại như generate_visual_asset(). Cùng cơ chế
    fallback chain (default → fallback) như generate_visual_asset()."""
    if status.narration_status == "ready":
        return
    text = (beat.get("audio") or "").strip()
    if not text:
        status.narration_status = "ready"  # không có lời đọc ở beat này — bỏ qua, không phải lỗi
        return
    status.narration_status = "generating"
    status.narration_error = None
    try:
        providers = get_tts_chain(db)
    except NoProviderConfiguredError as e:
        status.narration_status = "error"
        status.narration_error = str(e)
        return

    emotion = beat.get("direction", "")
    errors = []
    for provider in providers:
        try:
            data = provider.synthesize(text, emotion=emotion)
            ext = _TTS_EXT.get(provider.provider_name, "mp3")
            path = pdir / "assets" / f"{status.shot_id}.{ext}"
            write_bytes(path, data)
            status.narration_asset_path = str(path)
            status.narration_provider = provider.provider_name
            status.narration_status = "ready"
            status.narration_error = None
            cost = _TTS_COST_FN.get(provider.provider_name, estimate_elevenlabs_tts_cost)(len(text), getattr(provider, "model_name", ""))
            record_asset_usage(db, p.channel_id, p.title, provider=provider.provider_name, stage="narration", unit_label=f"{len(text)} ký tự", cost=cost)
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"{provider.provider_name}: {e}")

    status.narration_status = "error"
    status.narration_error = "; ".join(errors)
