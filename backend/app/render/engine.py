"""Sinh asset thật (ảnh/video + giọng đọc) cho từng shot — M2 Production Layer.

Nguyên tắc tách biệt (specs/09 "Chống coupling: script core ⟂ render module"): module
này CHỈ ĐỌC `pack.json` (script/shots đã duyệt qua Gate #2, brand), KHÔNG BAO GIỜ ghi
lại vào đó — mọi trạng thái sinh asset sống trong `render.json` riêng (app/render/
schemas.py). Chạy trong FastAPI BackgroundTasks (app/routers/render.py) — KHÔNG block
request thread, vì video (Sora) có thể mất vài phút để hoàn tất.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from app.config import channel_dir, project_dir
from app.db import SessionLocal
from app.filestore import read_json, unlink_retrying, write_bytes, write_json
from app.models import Project, ProviderConfig
from app.providers.base import GenerationInterrupted, VideoProvider
from app.providers.factory import NoProviderConfiguredError, build_llm_provider, get_image_chain, get_tts_chain, get_video_chain
from app.providers.gpu_lock import gpu_lock
from app.providers.image_comfy_sdxl import estimate_cost as estimate_local_sdxl_cost
from app.providers.image_localai import estimate_cost as estimate_localai_image_cost
from app.providers.image_flux import estimate_cost as estimate_flux_image_cost
from app.providers.image_flux_kontext import estimate_cost as estimate_flux_kontext_image_cost
from app.providers.image_gemini import estimate_cost as estimate_gemini_image_cost
from app.providers.image_openai import estimate_cost as estimate_openai_image_cost
from app.providers.tts_elevenlabs import estimate_cost as estimate_elevenlabs_tts_cost
from app.providers.tts_gemini import estimate_cost as estimate_gemini_tts_cost
from app.providers.tts_omnivoice import estimate_cost as estimate_omnivoice_tts_cost
from app.providers.tts_piper import estimate_cost as estimate_piper_tts_cost
from app.providers.video_comfy_wan import estimate_cost as estimate_local_wan_cost
from app.providers.video_localai import estimate_cost as estimate_localai_video_cost
from app.providers.video_flux import estimate_cost as estimate_flux_video_cost
from app.providers.video_sora import estimate_cost as estimate_sora_video_cost
from app.providers.video_veo import estimate_cost as estimate_veo_video_cost
from app.render.media_probe import probe_duration_sec
from app.render.schemas import RenderState, ShotRenderStatus, WatermarkScanSummary
from app.routers.pipeline import record_asset_usage
from app.timeutil import vn_isoformat
from app.watermark.pipeline import remove_watermark_from_image, remove_watermark_from_video

VIDEO_POLL_INTERVAL_SEC = 10
# 25 phút — cũ là 480s (8 phút, đủ cho Sora/Veo). Đo thật với Wan2.2 TI2V-5B (local,
# ComfyUI) trên RTX 5060 Ti: 1 clip ~8s tốn 7-18.5 phút tuỳ tải hệ thống (20 bước
# KSampler, ~25-65s/bước) — vượt xa 480s cũ nếu máy đang bận việc khác. Tăng lên rộng
# rãi hơn hẳn vì local chậm hơn cloud đáng kể, không tốn phí khi chờ thêm (khác Sora/Veo
# tính theo thời gian xử lý phía nhà cung cấp, không phải phía client chờ).
VIDEO_MAX_WAIT_SEC = 1500

# Mỗi task tra đúng hàm ước tính chi phí theo provider THẬT SỰ THÀNH CÔNG trong chain
# fallback (không biết trước sẽ là default hay fallback) — xem _candidate_configs()
# trong factory.py. Provider local (piper/local_sdxl/local_wan) luôn $0 — thêm dần khi
# từng adapter local ra đời (xem IMPLEMENTATION_REPORT.md mục local AI provider).
_IMAGE_COST_FN = {
    "openai": estimate_openai_image_cost, "gemini": estimate_gemini_image_cost, "flux": estimate_flux_image_cost, "flux_kontext": estimate_flux_kontext_image_cost,
    "local_sdxl": estimate_local_sdxl_cost, "localai_image": estimate_localai_image_cost,
}
_VIDEO_COST_FN = {
    "sora": estimate_sora_video_cost, "veo": estimate_veo_video_cost, "flux": estimate_flux_video_cost,
    "local_wan": estimate_local_wan_cost, "localai_video": estimate_localai_video_cost,
}

# `local_sdxl`/`local_wan` (ComfyUI) SONG SONG `localai_image`/`localai_video` (LocalAI,
# mới 2026-08-25) — dùng CHUNG mọi chỗ trong file này cần biết "provider này có phải
# local SDXL/Wan (bất kể chạy qua ComfyUI hay LocalAI) không", tránh lặp lại tuple ở
# nhiều nơi. Additive theo kế hoạch migrate — xoá `local_sdxl`/`local_wan` khỏi đây SAU
# khi verify LocalAI thật qua GPU người dùng và xoá hẳn code ComfyUI.
_LOCAL_IMAGE_PROVIDER_NAMES = ("local_sdxl", "localai_image")
_LOCAL_VIDEO_PROVIDER_NAMES = ("local_wan", "localai_video")
_TTS_COST_FN = {"elevenlabs": estimate_elevenlabs_tts_cost, "gemini": estimate_gemini_tts_cost, "piper": estimate_piper_tts_cost, "omnivoice": estimate_omnivoice_tts_cost}

# ElevenLabs trả MP3, Gemini TTS trả WAV (tự bọc từ PCM thô — xem tts_gemini.py) —
# đuôi file SAI khiến FileResponse (app/routers/render.py::get_shot_asset) đoán nhầm
# Content-Type theo phần mở rộng, browser phát âm thanh có thể lỗi.
_TTS_EXT = {"elevenlabs": "mp3", "gemini": "wav", "piper": "wav", "omnivoice": "wav"}

# Cờ huỷ theo project — trong bộ nhớ (không ghi DB/file), đủ dùng cho app 1 người dùng,
# không cần sống sót qua việc restart backend (huỷ là hành động tức thời, không phải
# trạng thái cần bền vững). Set đơn giản, an toàn dưới GIL cho add/discard/contains —
# không cần Lock riêng (khác gpu_lock.py, nơi thật sự có race điều kiện GPU).
_cancel_requested: set[str] = set()

# Chống chạy chồng lấn: `render/start` (batch) và 2 nút sinh lại từng shot đều tự mở
# BackgroundTasks riêng — nếu người dùng bấm "toàn bộ block" rồi bấm "sinh lại" cho 1
# shot NGAY LÚC batch đang xử lý (chưa kịp thấy nút bị disable), 2 task chạy song song,
# mỗi task tự load 1 bản RenderState RIÊNG từ render.json rồi ghi đè — bản ghi sau THẮNG,
# xoá mất tiến độ của bản kia (đã gặp thật: batch dừng giữa chừng ở B01, các shot sau
# không bao giờ được xử lý). Chặn TỪ ĐẦU bằng cờ "đang chạy" theo project, kiểm tra ở
# router (app/routers/render.py) TRƯỚC khi mở BackgroundTasks mới — không phải sửa ở
# đây vì cần trả lỗi rõ ràng cho người dùng (409), không nên âm thầm bỏ qua trong nền.
_in_progress: set[str] = set()


def is_generation_in_progress(project_id: str) -> bool:
    return project_id in _in_progress


def _mark_in_progress(project_id: str) -> None:
    _in_progress.add(project_id)


def _mark_done(project_id: str) -> None:
    _in_progress.discard(project_id)


# Cờ "đang ghép THẬT" theo project — **mới (2026-09-02, mục 111)**, cùng cơ chế
# `_in_progress` ở trên nhưng RIÊNG cho `assemble_video` (không dùng chung — sinh asset
# và ghép video là 2 việc độc lập, không cần chặn nhau). Bug thật người dùng báo: thread
# chạy `assemble_video` CHẾT LẶNG (không rõ nguyên nhân chính xác — nghi lỗi tầng thấp
# hơn Python exception, VD crash lúc log Unicode ra console cp1252, xem `electron/src/
# backend-launcher.ts::PYTHONIOENCODING`) SAU KHI đã dựng xong 1 file trung gian 3.4GB,
# TRƯỚC KHI kịp lưu tiến độ tiếp — `state.assembly_status` bị kẹt "assembling" MÃI MÃI
# trong render.json vì router (`start_assemble`) TRƯỚC ĐÂY chỉ tin field ĐÃ LƯU này, dù
# tiến trình thật sự xử lý nó đã biến mất từ lâu — kể cả khởi động lại app cũng KHÔNG tự
# hết kẹt (field nằm trong file, không phải bộ nhớ). Cờ này (trong bộ nhớ, giống `_in_
# progress`) tự về rỗng khi tiến trình backend khởi động lại HOẶC khi `assemble_video`
# chạy xong (thành công/lỗi bình thường, qua `finally` bọc ngoài cùng — xem docstring
# `assembly.py::assemble_video`) — `start_assemble` giờ CHỈ chặn 409 khi cờ NÀY còn
# `True` (tiến trình THẬT SỰ đang chạy), tự phục hồi khi không còn đúng nữa.
_assembly_in_progress: set[str] = set()


def is_assembly_in_progress(project_id: str) -> bool:
    return project_id in _assembly_in_progress


def _mark_assembly_in_progress(project_id: str) -> None:
    _assembly_in_progress.add(project_id)


def _mark_assembly_done(project_id: str) -> None:
    _assembly_in_progress.discard(project_id)


class GenerationCancelled(Exception):
    """Người dùng bấm huỷ giữa chừng — KHÁC lỗi thật (provider fail): không thử tiếp
    provider fallback, không tính vào build_errors, dừng ngay lập tức."""


def request_cancel(project_id: str) -> None:
    _cancel_requested.add(project_id)


def is_cancel_requested(project_id: str) -> bool:
    return project_id in _cancel_requested


def _clear_cancel(project_id: str) -> None:
    _cancel_requested.discard(project_id)


def try_interrupt_local_gpu_job(db: Session) -> None:
    """Best-effort: gọi ComfyUI `/interrupt` để dừng NGAY job GPU đang chạy (ảnh hoặc
    video) thay vì chỉ ngừng chờ phía client — job không bị huỷ thật ở ComfyUI sẽ tiếp
    tục chạy vô ích, chiếm GPU/VRAM tới khi tự xong. Không có API tương đương cho Ollama
    (LLM không cần huỷ — mỗi lệnh gọi chỉ vài chục giây, không đáng để thêm phức tạp).
    Nuốt lỗi — dọn GPU thất bại không nên chặn việc set cờ huỷ chính."""
    for task in ("image", "video"):
        cfg = (
            db.query(ProviderConfig)
            .filter(ProviderConfig.task == task, ProviderConfig.connection_type == "local_endpoint", ProviderConfig.enabled == True)  # noqa: E712
            .first()
        )
        if cfg and cfg.endpoint_url:
            try:
                httpx.post(f"{cfg.endpoint_url.rstrip('/')}/interrupt", timeout=5)
            except Exception:  # noqa: BLE001
                pass


def get_local_gpu_status(db: Session) -> dict:
    """Trạng thái hàng đợi ComfyUI (Image/Video local) — cho UI hiện "GPU đang chạy
    job X, còn Y job chờ" thay vì chỉ im lặng chờ (đỡ sốt ruột khi video local mất
    7-18 phút, xem IMPLEMENTATION_REPORT.md mục 16.6c). Best-effort — trả
    `reachable: False` nếu không có provider local nào cấu hình hoặc ComfyUI không phản
    hồi, KHÔNG raise (đây là thông tin phụ trợ, không nên chặn màn hình chính)."""
    cfg = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task.in_(("image", "video")), ProviderConfig.connection_type == "local_endpoint", ProviderConfig.enabled == True)  # noqa: E712
        .first()
    )
    if not cfg or not cfg.endpoint_url:
        return {"reachable": False, "queue_running": 0, "queue_pending": 0, "gpu_name": None}
    base_url = cfg.endpoint_url.rstrip("/")
    try:
        with httpx.Client(timeout=5) as client:
            queue_resp = client.get(f"{base_url}/queue")
            queue_resp.raise_for_status()
            queue = queue_resp.json()
            gpu_name = None
            try:
                stats_resp = client.get(f"{base_url}/system_stats")
                if stats_resp.status_code == 200:
                    devices = stats_resp.json().get("devices", [])
                    if devices:
                        gpu_name = devices[0].get("name")
            except Exception:  # noqa: BLE001
                pass
        return {
            "reachable": True,
            "queue_running": len(queue.get("queue_running", [])),
            "queue_pending": len(queue.get("queue_pending", [])),
            "gpu_name": gpu_name,
        }
    except Exception:  # noqa: BLE001
        return {"reachable": False, "queue_running": 0, "queue_pending": 0, "gpu_name": None}


# `_probe_audio_duration_sec` chuyển logic thật sang `media_probe.py` (2026-08-20) —
# module đó KHÔNG phụ thuộc gì trong app nên `routers/pipeline.py` dùng được cho
# transcript .srt (mục 52 IMPLEMENTATION_REPORT.md), khác `engine.py` mà pipeline.py
# KHÔNG import được (vòng: engine.py → routers/pipeline.py, xem docstring media_probe.py).
# Giữ alias tên cũ — mọi chỗ import `engine._probe_audio_duration_sec` không cần đổi.
_probe_audio_duration_sec = probe_duration_sec


def _apply_narration_speed(path: Path, speed: float) -> None:
    """Chỉnh tốc độ PHÁT file giọng đọc VỪA sinh (time-stretch qua ffmpeg `atempo`,
    KHÔNG đổi cao độ) — theo yêu cầu người dùng (2026-09-02, mục 109): "điều chỉnh tốc
    độ của file giọng đọc được tạo ra", áp dụng NGAY TẠI FILE trên đĩa SAU khi provider
    TTS sinh xong, KHÔNG PHẢI 1 tham số của API provider — hoạt động ĐỒNG NHẤT bất kể
    provider nào đang cấu hình (ElevenLabs/Gemini/Piper/OmniVoice), không cần sửa từng
    adapter riêng. Chạy TRƯỚC `_probe_audio_duration_sec` (gọi ngay sau ở call site) —
    mọi logic đo thời lượng downstream (segment duration, transcript .srt) tự động dùng
    ĐÚNG thời lượng đã điều chỉnh mà không cần biết gì về khái niệm "speed".

    `speed==1.0` — bỏ qua hoàn toàn, không tốn 1 lần re-encode vô ích, giữ nguyên hành
    vi cũ. Thiếu ffmpeg trên máy hoặc lệnh lỗi — bỏ qua ÂM THẦM, giữ nguyên file gốc
    CHƯA điều chỉnh (cùng nguyên tắc `probe_duration_sec`: xử lý phụ trợ không được
    chặn luồng generate chính)."""
    if speed == 1.0:
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    # Giữ NGUYÊN đuôi file gốc (.wav/.mp3) cho tên tạm — ffmpeg suy ra format output từ
    # đuôi file, dùng đuôi lạ (VD ".tmp") sẽ khiến ffmpeg không tự chọn được muxer đúng.
    tmp_path = path.parent / f"{path.stem}_speed_tmp{path.suffix}"
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", str(path), "-filter:a", f"atempo={speed}", str(tmp_path)],
            capture_output=True, check=True, text=True, timeout=60,
        )
        tmp_path.replace(path)
    except Exception:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)


def _render_path(pdir):
    return pdir / "render.json"


def load_render_state(pdir, project_id: str) -> RenderState:
    data = read_json(_render_path(pdir))
    state = RenderState.model_validate(data) if data else RenderState(project_id=project_id)
    _reconcile_stale_generating(pdir, state, project_id)
    return state


def save_render_state(pdir, state: RenderState) -> None:
    write_json(_render_path(pdir), state.model_dump())


_STALE_GENERATING_MSG = "Tiến trình sinh bị gián đoạn (backend tắt/khởi động lại giữa chừng) — trạng thái không xác định, bấm Tạo lại."


def _reconcile_stale_generating(pdir, state: RenderState, project_id: str) -> None:
    """Tự sửa shot bị KẸT VĨNH VIỄN ở "generating" — xảy ra khi backend bị tắt/khởi
    động lại (VD người dùng bấm "Restart app", hoặc máy khởi động lại) NGAY LÚC 1 shot
    đang sinh: `run_asset_generation`/`regenerate_single_*` chạy trong BackgroundTasks
    của tiến trình cũ, tiến trình đó chết theo backend — không còn cơ hội chạy tới đoạn
    `except`/cuối hàm để ghi lại trạng thái cuối (ready/error) vào render.json, nên shot
    đứng yên ở "generating" MÃI MÃI dù GPU/ComfyUI thật ra đã dừng từ lâu (bug thật
    người dùng báo: UI GPU status hiện "0 job đang chạy" nhưng shot vẫn "generating").

    Chỉ can thiệp khi `is_generation_in_progress(project_id)` là False — tức KHÔNG có
    task nào thật sự đang chạy cho project này trong tiến trình HIỆN TẠI. Nếu có, đây là
    "generating" THẬT (task vẫn đang chạy), không được đụng vào. An toàn gọi mỗi lần
    `load_render_state()` — hàm này được gọi lại xuyên suốt vòng đời request, không chỉ
    lúc backend khởi động, nên tự sửa được ngay khi người dùng mở lại màn hình, không
    cần đợi 1 job "reconcile lúc startup" riêng."""
    if is_generation_in_progress(project_id):
        return
    changed = False
    for s in state.shots:
        if s.visual_status == "generating":
            s.visual_status, s.visual_error, s.visual_started_at = "error", _STALE_GENERATING_MSG, None
            changed = True
        if s.narration_status == "generating":
            s.narration_status, s.narration_error, s.narration_started_at = "error", _STALE_GENERATING_MSG, None
            changed = True
    if changed:
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


def run_asset_generation(project_id: str, *, kind: str = "both") -> None:
    """Sinh visual +/hoặc narration cho MỌI shot của project chưa `ready`. `kind`
    ("both"|"visual"|"narration", mặc định "both" — giữ hành vi cũ) — người dùng yêu
    cầu tách nút "Sinh asset cho toàn bộ block" thành 2 nút riêng (Visual/Giọng đọc),
    cùng lý do đã tách sinh PROMPT riêng (`visual/generate-all-visual`/`-all-tts`,
    pipeline.py): 1 provider lỗi/chậm (VD hết quota Image) không nên chặn luôn cả
    TTS đang chạy tốt của batch đó, và người dùng có thể chỉ muốn làm lại 1 loại asset
    cho toàn bộ block (VD đổi provider TTS, không cần sinh lại ảnh/video).

    Lỗi ở 1 shot KHÔNG dừng cả batch — ghi vào *_error, tiếp tục shot kế tiếp (người
    dùng có thể tự bấm "Tạo lại" riêng cho shot lỗi sau, xem app/routers/render.py).

    Kiểm tra cờ huỷ (`is_cancel_requested`) TRƯỚC mỗi shot — dừng cả batch ngay, không
    đụng tới các shot chưa bắt đầu (giữ nguyên trạng thái `pending`/`error` cũ, không
    tự đổi thành `ready` giả). Shot ĐANG generate lúc huỷ được xử lý trong
    `generate_visual_asset()`/`_poll_video_until_done()` (video local check cờ huỷ mỗi
    lần poll — xem `GenerationCancelled`).

    `_mark_in_progress`/`_mark_done` (finally) — router (`render.py::start_render`) từ
    chối mở batch/regenerate MỚI nếu project đã có 1 task đang chạy, tránh 2
    BackgroundTasks cùng ghi đè `render.json` (đã gặp thật: batch + regenerate 1 shot
    chạy chồng làm mất tiến độ các shot sau, xem `_in_progress` phía trên)."""
    _mark_in_progress(project_id)
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
            if is_cancel_requested(project_id):
                break
            status = by_id[shot["shot_id"]]
            beat = _find_beat(pack, shot)

            if kind in ("both", "visual"):
                generate_visual_asset(db, p, pdir, shot, beat, status, state)
                save_render_state(pdir, state)

            if is_cancel_requested(project_id):
                break
            if kind in ("both", "narration"):
                generate_narration_asset(db, p, pdir, beat, status, state)
                save_render_state(pdir, state)

        db.commit()
    finally:
        _clear_cancel(project_id)
        _mark_done(project_id)
        db.close()


def regenerate_single_visual(project_id: str, shot_id: str) -> None:
    """Sinh lại visual cho ĐÚNG 1 shot — dùng cho BackgroundTasks trong
    app/routers/render.py. Tự mở/đóng session riêng (KHÔNG dùng session request-scoped
    của FastAPI `Depends(get_db)` — session đó đã bị đóng ngay khi response được trả
    về, TRƯỚC KHI BackgroundTasks thực thi; dùng lại sẽ lỗi "session is closed").
    `_mark_in_progress` cùng cờ với batch (xem run_asset_generation) — router chặn
    trước khi tới đây nếu đã có task khác chạy cho project này."""
    _mark_in_progress(project_id)
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
        generate_visual_asset(db, p, pdir, shot, beat, status, state)
        save_render_state(pdir, state)
        db.commit()
    finally:
        _clear_cancel(project_id)
        _mark_done(project_id)
        db.close()


def regenerate_single_narration(project_id: str, shot_id: str) -> None:
    """Tương đương regenerate_single_visual() nhưng cho narration."""
    _mark_in_progress(project_id)
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
        generate_narration_asset(db, p, pdir, beat, status, state)
        save_render_state(pdir, state)
        db.commit()
    finally:
        _mark_done(project_id)
        db.close()


# ---------------------------------------------------------------------------
# Xoá watermark cho asset đã sinh/upload (2026-08-28) — tái dùng app/watermark/ (Florence-2
# + LaMa) đã build cho Kho Tài Nguyên (IMPLEMENTATION_REPORT.md mục 96/97), theo yêu cầu
# người dùng: quét/xoá watermark cho từng shot HOẶC cả block, trước khi ghép video cuối.
# ---------------------------------------------------------------------------
def _remove_watermark_for_status(pdir, shot: dict, status: ShotRenderStatus, on_progress: Callable[[int, int, str], None] | None = None) -> str:
    """Xoá watermark khỏi asset HIỆN TẠI của `status`, cập nhật `status` tại chỗ. Trả về
    "cleaned"|"no_watermark"|"failed" — KHÔNG tự set `visual_status` (caller quyết định,
    vì đơn lẻ/hàng loạt xử lý outcome hơi khác nhau ở tầng gọi). "no_watermark" KHÔNG phải
    lỗi — asset gốc giữ NGUYÊN, chỉ ghi `visual_watermark_note` để UI báo rõ ràng, tách
    biệt khỏi `visual_error` (dành cho lỗi thật, VD model crash/ffmpeg thiếu). `on_progress`
    (2026-09-02, theo yêu cầu người dùng — thanh tiến trình giống Kho Tài Nguyên) — CHỈ có
    tác dụng cho shot VIDEO (`remove_watermark_from_video` tự gọi mỗi ~8 frame, xem
    `watermark/pipeline.py`); shot ẢNH vá 1 lượt LaMa duy nhất tại vị trí cố định (2026-09-
    04, xem bug thật #4 `watermark/detector.py` — không còn qua Florence-2), quá nhanh để
    cần tiến trình dạng %."""
    if not status.visual_asset_path:
        status.visual_error = "Chưa có ảnh/video nào để xoá watermark."
        return "failed"
    old_path = Path(status.visual_asset_path)
    if not old_path.exists():
        status.visual_error = "File ảnh/video không còn tồn tại trên đĩa."
        return "failed"
    is_video = shot.get("visual_type") == "video"
    new_path = old_path.with_name(f"{old_path.stem}_nowm{old_path.suffix}")
    tmp_dir = pdir / "assets" / "_watermark_tmp" / status.shot_id
    try:
        if is_video:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("Chưa cài ffmpeg trên máy chạy backend.")
            remove_watermark_from_video(ffmpeg, str(old_path), new_path, tmp_dir, on_progress=on_progress)
        else:
            remove_watermark_from_image(str(old_path), new_path)
    except ValueError:
        status.visual_watermark_note = "Đã quét — không phát hiện watermark nào trong ảnh/video này."
        return "no_watermark"
    except Exception as e:  # noqa: BLE001
        status.visual_error = f"Xoá watermark thất bại: {e}"
        return "failed"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # Hết việc (dù thành công/lỗi/không tìm thấy) — dọn tiến trình, nút quay lại trạng
        # thái tĩnh "Xoá watermark" thay vì kẹt hiện % cũ.
        status.visual_watermark_progress_current = None
        status.visual_watermark_progress_total = None
        status.visual_watermark_progress_label = None

    unlink_retrying(old_path)
    status.visual_asset_path = str(new_path)
    status.visual_updated_at = vn_isoformat(datetime.now(timezone.utc))
    status.visual_watermark_note = None
    status.visual_error = None
    return "cleaned"


def remove_shot_watermark(project_id: str, shot_id: str) -> None:
    """Xoá watermark cho ĐÚNG 1 shot — dùng cho BackgroundTasks. Cùng cờ `_in_progress`
    với sinh asset (router chặn chạy chồng TRƯỚC khi tới đây, xem `_require_not_in_
    progress` — cùng bug lớp đã sửa cho Kho Tài Nguyên ở mục 97, tránh tái diễn: 2 tiến
    trình cùng đụng `render.json`/asset của project sẽ ghi đè tiến độ của nhau)."""
    _mark_in_progress(project_id)
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
        state = load_render_state(pdir, project_id)
        status = next((s for s in state.shots if s.shot_id == shot_id), None)
        if not status:
            return

        def _on_progress(current: int, total: int, label: str) -> None:
            status.visual_watermark_progress_current = current
            status.visual_watermark_progress_total = total
            status.visual_watermark_progress_label = label
            save_render_state(pdir, state)

        outcome = _remove_watermark_for_status(pdir, shot, status, on_progress=_on_progress)
        status.visual_status = "error" if outcome == "failed" else "ready"
        save_render_state(pdir, state)
        db.commit()
    finally:
        _mark_done(project_id)
        db.close()


def remove_all_shots_watermark(project_id: str) -> None:
    """Xoá watermark cho MỌI shot đang có asset sẵn sàng (`visual_status=="ready"`) —
    bỏ qua thầm lặng shot chưa sinh xong (cùng nguyên tắc `approve_all_shots`). Lỗi 1 shot
    KHÔNG dừng cả batch (cùng nguyên tắc `run_asset_generation`). Ghi tóm tắt kết quả vào
    `RenderState.watermark_scan_summary` — người dùng yêu cầu rõ "ảnh nào không phát hiện
    watermark thì có thông báo rõ ràng"; với cả BLOCK, 1 banner tóm tắt sau khi xong dễ
    thấy hơn hẳn phải tự rà từng shot."""
    _mark_in_progress(project_id)
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        pdir = project_dir(p.channel_id, p.id)
        pack = read_json(pdir / "pack.json") or {}
        shots_by_id = {s["shot_id"]: s for s in pack.get("shots", [])}

        state = load_render_state(pdir, project_id)
        counts = {"cleaned": 0, "no_watermark": 0, "failed": 0}
        scanned = 0
        for status in state.shots:
            if is_cancel_requested(project_id):
                break
            shot = shots_by_id.get(status.shot_id)
            if status.visual_status != "ready" or not status.visual_asset_path or not shot:
                continue
            scanned += 1
            status.visual_status = "generating"
            status.visual_watermark_note = None
            save_render_state(pdir, state)

            def _on_progress(current: int, total: int, label: str) -> None:
                status.visual_watermark_progress_current = current
                status.visual_watermark_progress_total = total
                status.visual_watermark_progress_label = label
                save_render_state(pdir, state)

            outcome = _remove_watermark_for_status(pdir, shot, status, on_progress=_on_progress)
            status.visual_status = "error" if outcome == "failed" else "ready"
            counts[outcome] += 1
            save_render_state(pdir, state)

        state.watermark_scan_summary = WatermarkScanSummary(
            scanned=scanned, cleaned=counts["cleaned"], no_watermark=counts["no_watermark"], failed=counts["failed"],
            finished_at=vn_isoformat(datetime.now(timezone.utc)),
        )
        save_render_state(pdir, state)
        db.commit()
    finally:
        _clear_cancel(project_id)
        _mark_done(project_id)
        db.close()


def _poll_video_until_done(provider: VideoProvider, job_id: str, project_id: str) -> bytes:
    waited = 0
    while waited < VIDEO_MAX_WAIT_SEC:
        if is_cancel_requested(project_id):
            raise GenerationCancelled(f"Đã dừng theo yêu cầu người dùng (video job {job_id}).")
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


def _load_brand_profile(channel_id: str) -> dict:
    return read_json(channel_dir(channel_id) / "brandprofile.json") or {}


# Trần cố định (KHÔNG phụ thuộc budget còn lại) cho phần `visual_style_prompt` của kênh
# trong prompt local — **mới (2026-08-22, đợt 3)**, sửa bug thật phát hiện khi người dùng
# test: shot có `visual_fx` NGẮN (VD "Cô gái chăn trâu", 17 ký tự) — thiết kế CŨ tính
# "budget CÒN LẠI sau content" rồi lấp ĐẦY chỗ đó bằng `visual_style_prompt` (đoạn văn dài
# hàng trăm ký tự mô tả tông màu/chất liệu) → nội dung cảnh chỉ chiếm ~5% tổng prompt, bị
# style kênh + khối từ khoá cố định (§ dưới) nhấn chìm hoàn toàn — SDXL ra ẢNH ĐÚNG STYLE
# nhưng SAI HẲN chủ thể (xác nhận thật: prompt cũ cho shot này chỉ có 17/320 ký tự là nội
# dung cảnh, ảnh ra không có "cô gái"/"trâu" nào). Trần CỐ ĐỊNH nhỏ ở đây đảm bảo phần
# style kênh KHÔNG BAO GIỜ phình to hơn mức cần thiết dù content ngắn tới đâu.
_LOCAL_SDXL_BRAND_STYLE_MAX_CHARS = 90
# Khối style CỐ ĐỊNH chèn prompt local — **mới (2026-08-22)**, theo tài liệu đề xuất
# `StudioFlow_Style_Checkpoint_Proposal.md`: art direction kênh "Người kể sử" đòi hỏi
# painterly/sơn dầu/ink wash (KHÔNG photoreal, KHÔNG 3D nhựa hoá) — SDXL fine-tune/LoRA
# painterly (đợt 2) vẫn cần từ khoá style rõ ràng đẩy đúng hướng, không chỉ dựa vào
# checkpoint/LoRA. HẰNG SỐ dùng chung mọi kênh (đơn giản trước — CLAUDE.md "không over-
# engineer"), CHƯA đưa vào BrandProfile theo từng kênh — cân nhắc sau nếu có kênh khác cần
# style khác hẳn (VD kênh tài chính/tâm lý học đã có trong seed demo, không cần "sơn dầu").
#
# **Đổi VỊ TRÍ (đợt 3, 2026-08-22)** — TRƯỚC đứng ĐẦU prompt (theo đúng đề xuất "chèn cố
# định ở đầu"), GIỜ đứng SAU nội dung cảnh (`visual_fx`) — người dùng báo thật "style ảnh
# đúng nhưng nội dung ảnh không giống mô tả text": đặt khối style (bao gồm cả khối cố định
# này lẫn `visual_style_prompt` của kênh) TRƯỚC nội dung cảnh khiến chủ thể bị đẩy xuống vị
# trí sau, loãng tín hiệu — đúng NGƯỢC với hướng dẫn gốc ở tài liệu đề xuất ĐẦU TIÊN
# (`StudioFlow_ImageVideo_Improvement.md`): "đưa yếu tố bố cục quan trọng nhất lên đầu câu,
# cắt/nén mô tả style PHỤ". Chủ thể (visual_fx) mới là phần "quan trọng nhất", không phải
# khối style cố định — đổi lại đúng thứ tự: NỘI DUNG trước, STYLE sau.
_LOCAL_SDXL_STYLE_PREFIX = "oil painting, hand-painted, ink wash, muted warm tones, aged paper texture, cinematic concept art"
# `[Visual]: ...` là tag DUY NHẤT mang nội dung CẢNH thật (xác nhận đọc thật pack.json
# nhiều project — mọi shot đều bắt đầu `visual_fx` bằng đúng tag này, đôi khi lặp 2 lần
# cho 2 nhịp camera trong cùng 1 shot) — cần TÁCH RIÊNG (unwrap: bỏ nhãn, GIỮ nội dung),
# khác mọi tag khác (`[Title Card]`, `[Graphic]`, `[Text Overlay]`, `[Quote Text]`,
# `[Insight Box]`, `[Animation]`, `[Graphic Overlays]`...) — toàn bộ các tag CÒN LẠI quan
# sát được đều mang chữ/số cần "vẽ" lên ảnh (title card, trích dẫn, số liệu...), xoá HẲN
# (tag + nội dung). Regex `_OTHER_BRACKET_TAG_RE` dùng negative lookahead để CHỈ xoá tag
# khác "Visual", chạy TRƯỚC `_VISUAL_TAG_RE` (chỉ xoá đúng nhãn `[Visual]:`, giữ câu sau).
_OTHER_BRACKET_TAG_RE = re.compile(r"\[(?!Visual\])[^\]]+\]:[^\[]*", re.IGNORECASE)
_VISUAL_TAG_RE = re.compile(r"\[Visual\]:\s*", re.IGNORECASE)


def _strip_text_overlay_tags(text: str) -> str:
    """Bỏ các đoạn `[Tag]: nội dung` chỉ định chữ/graphic chèn lên ảnh khỏi `visual_fx`,
    GIỮ NGUYÊN nội dung mô tả cảnh ở tag `[Visual]:` — **mới (2026-08-22)**, phát hiện
    lúc điều tra "ảnh model local xấu hơn hẳn Gemini": `visual_fx` do LLM sinh LUÔN chứa
    chỉ dẫn chèn CHỮ lên ảnh (`[Title Card]: TRẬN RẠCH GẦM...`, `[Text Overlay]: ...`,
    `[Graphic]: Dòng chữ nổi lên...`) — xác nhận thật qua `pack.json` nhiều project của
    người dùng (grep toàn bộ shot: tag nào cũng có `[Visual]:` + đúng 1 trong các tag
    chữ/graphic kể trên). `app/render/assembly.py` KHÔNG có bước `drawtext`/overlay chữ
    riêng nào, nên các tag này đang trông cậy HOÀN TOÀN vào chính model sinh ảnh để "vẽ"
    chữ tiếng Việt có dấu thành pixel — SDXL (mọi checkpoint, kể cả fine-tune tốt) render
    chữ RẤT kém, đặc biệt chữ có dấu, gần như luôn ra ký tự vô nghĩa/méo mó — khác biệt
    lớn hơn hẳn so với Gemini (xử lý việc này khá hơn nhiều, dù không hoàn hảo). Ngoài ra
    `_NEGATIVE_PROMPT` (`image_comfy_sdxl.py`) đã có sẵn từ khoá "text" — 2 chiều
    positive/negative đang mâu thuẫn nhau ngay trong cùng 1 request.

    CHỈ áp dụng cho local SDXL (xem `for_local_sdxl` bên dưới) — KHÔNG đổi hành vi cloud
    (Gemini/OpenAI/Flux xử lý chữ khá hơn, và đây không phải phạm vi yêu cầu lần này)."""
    text = re.sub(_OTHER_BRACKET_TAG_RE, "", text)
    text = re.sub(_VISUAL_TAG_RE, "", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_visual_prompt(shot: dict, brand: dict, *, is_video: bool, for_local_sdxl: bool = False) -> str:
    """Ghép prompt THẬT gửi cho provider ảnh/video — trước đây chỉ gửi nguyên văn
    `shot.visual_fx` do LLM tự diễn giải lúc sinh script, KHÔNG kèm style kênh
    (`brand.visual_style_prompt`) dù đó là ngữ cảnh có sẵn, khiến visual giữa các shot
    lệch phong cách/tông màu (nguyên nhân #1 trong phân tích "visual không đồng nhất" —
    xem IMPLEMENTATION_REPORT.md). Luôn nối `visual_style_prompt` bất kể LLM đã tự nhắc
    style trong `visual_fx` hay chưa — Tier 1 của cải tiến.

    `audio_sfx` (mô tả nhạc nền/không khí, VD "nhạc căng thẳng, nhịp tim dồn dập") CHỈ
    nối vào khi `is_video=True` — đổi 2026-08-16 theo yêu cầu người dùng: model ẢNH TĨNH
    không có khái niệm nhịp điệu/âm thanh, đưa `audio_sfx` vào prompt ảnh khiến model vẽ
    LUÔN cả chữ "[SFX]"/"[BGM]"/waveform giả lên ảnh (thấy thật lúc test — xem
    IMPLEMENTATION_REPORT.md mục 20) thay vì chỉ dùng làm gợi ý mood như ý định ban đầu.
    Video (chuyển động theo thời gian) hợp lý hơn để giữ làm gợi ý nhịp điệu/không khí.

    `for_local_sdxl` — **mới (2026-08-22)**, theo yêu cầu người dùng "cải thiện chất
    lượng ảnh model local": SDXL (local, qua ComfyUI) khác hẳn Gemini/OpenAI/Flux ở 2
    điểm cần prompt riêng — (1) render chữ rất kém (xem `_strip_text_overlay_tags` ở
    trên), (2) CLIP text encoder giới hạn ~77 token, câu văn tự nhiên dài dễ bị cắt cụt
    giữa chừng. Khi `True`: bỏ tag `[Title Card]`/... khỏi `visual_fx`, nối các phần bằng
    ", " thay vì ". " (gần văn phong prompt SD hơn câu văn đầy đủ).

    **Thứ tự (đổi lại đợt 3, 2026-08-22 — xem bug thật ở docstring
    `_LOCAL_SDXL_BRAND_STYLE_MAX_CHARS`)**: NỘI DUNG CẢNH (`visual_fx`, đã lọc tag) LUÔN
    đứng ĐẦU — đây là phần model cần vẽ ĐÚNG nhất, không được để bất kỳ khối style nào che
    lấp. Theo sau là `_LOCAL_SDXL_STYLE_PREFIX` (từ khoá art direction cố định — đợt 2) rồi
    `visual_style_prompt` của kênh, CẮT về tối đa `_LOCAL_SDXL_BRAND_STYLE_MAX_CHARS` ký
    tự CỐ ĐỊNH (không phụ thuộc content dài/ngắn — tránh phần style "phình to" lấp chỗ
    trống khi content ngắn, đúng bug đã sửa). `visual_fx` KHÔNG bị cắt bởi bất kỳ giới hạn
    nào ở đây — tin tưởng LLM viết độ dài hợp lý, tầng này chỉ chắc chắn phần STYLE (phụ)
    không bao giờ lấn át. Chỉ dẫn "không vẽ chữ" (đợt 1) đã CHUYỂN sang đúng chỗ — negative
    prompt thật ở `image_comfy_sdxl.py::_NEGATIVE_PROMPT` (đợt 2) — không còn ở hàm này.

    KHÔNG tái cấu trúc "chủ thể-hành động-vị trí" lên đầu câu bằng thuật toán — `visual_fx`
    là văn xuôi tự do do LLM viết, tách lại đúng ngữ pháp cần thêm 1 lệnh gọi LLM riêng
    (tốn chi phí/độ trễ mỗi shot, đi ngược tinh thần "pipeline local miễn phí").

    `cultural_lock_positive` — **mới (2026-08-23)**, theo yêu cầu người dùng chống thiên
    lệch văn hoá Nhật/Hàn của checkpoint/LoRA "Á Đông" (đa số train từ dữ liệu Nhật/Trung/
    Hàn): từ khoá Việt Nam cụ thể (trang phục theo triều đại, kiến trúc, hoạ tiết), nối
    NGAY SAU nội dung cảnh — ÁP DỤNG CHO MỌI provider (cloud lẫn local), khác
    `visual_style_prompt`/`_LOCAL_SDXL_STYLE_PREFIX` (chỉ về phong cách thị giác, không
    phải vấn đề ĐÚNG/SAI nội dung văn hoá)."""
    parts = []
    visual_fx = (shot.get("visual_fx") or "").strip()
    if for_local_sdxl:
        visual_fx = _strip_text_overlay_tags(visual_fx)
    if visual_fx:
        parts.append(visual_fx)
    if is_video:
        audio_sfx = (shot.get("audio_sfx") or "").strip()
        if audio_sfx:
            parts.append(f"Không khí/nhịp điệu hình ảnh gợi ý từ nhạc nền: {audio_sfx}")
    cultural_lock = (brand.get("cultural_lock_positive") or "").strip()
    if cultural_lock:
        parts.append(cultural_lock)
    if for_local_sdxl:
        parts.append(_LOCAL_SDXL_STYLE_PREFIX)
    style = (brand.get("visual_style_prompt") or "").strip()
    if style:
        if for_local_sdxl:
            style = style[:_LOCAL_SDXL_BRAND_STYLE_MAX_CHARS].strip()
            if style:
                parts.append(style)
        else:
            parts.append(f"Style hình ảnh kênh: {style}")
    if for_local_sdxl:
        return ", ".join(parts)
    return ". ".join(parts)


def _build_video_motion_prompt(shot: dict, brand: dict) -> str:
    """Prompt CHUYỂN ĐỘNG riêng cho Wan2.2 (`local_wan`) — **mới (2026-08-23)**, theo
    `StudioFlow_Video_Improvement_Plan.md`: khác `_build_visual_prompt(is_video=True)`
    (dùng cho provider video cloud — Sora/Veo/Flux, KHÔNG đổi) ở 2 điểm — (1) lọc tag
    `[Title Card]`/... khỏi `visual_fx` (CÙNG lý do `for_local_sdxl` — Wan cũng là
    model local, render chữ kém, xem `_strip_text_overlay_tags`); (2) thêm
    `brand.motion_tone` làm ràng buộc chuyển động RIÊNG (khác `visual_style_prompt` —
    đó là phong cách thị giác TĨNH, không nói gì về tốc độ/kiểu chuyển động).

    Nối bằng ". " (câu văn đầy đủ), KHÔNG theo kiểu từ khoá phẩy-ngăn-cách của
    `for_local_sdxl` — Wan dùng text encoder UMT5 XXL (kiểu T5, hiểu câu văn tự nhiên
    tốt hơn hẳn CLIP của SDXL), giữ nguyên văn phong câu để tận dụng đúng khả năng
    model thay vì ép về "từ khoá rời rạc" không cần thiết. Content (`visual_fx`) LUÔN
    đứng đầu — cùng nguyên tắc content-first đã sửa cho ảnh (mục 66 IMPLEMENTATION_
    REPORT.md), tránh ràng buộc chuyển động che lấp nội dung cảnh.

    `cultural_lock_positive` (2026-08-23) — nối SAU content, TRƯỚC motion_tone — cùng lý
    do đã thêm ở `_build_visual_prompt` (Wan cũng học từ dữ liệu Á Đông thiên lệch Nhật/
    Hàn giống hệt SDXL, cần từ khoá Việt cụ thể như nhau)."""
    parts = []
    visual_fx = _strip_text_overlay_tags((shot.get("visual_fx") or "").strip())
    if visual_fx:
        parts.append(visual_fx)
    cultural_lock = (brand.get("cultural_lock_positive") or "").strip()
    if cultural_lock:
        parts.append(cultural_lock)
    motion_tone = (brand.get("motion_tone") or "").strip()
    if motion_tone:
        parts.append(motion_tone)
    return ". ".join(parts)


def _local_sdxl_kwargs(brand: dict) -> dict:
    """Kwarg RIÊNG cho provider `local_sdxl` — **mới (2026-08-23)**, tách thành hàm dùng
    chung vì cần ở CẢ `_try_generate_wan_anchor_image` (ảnh anchor cho video) LẪN nhánh
    ảnh thường trong `generate_visual_asset`, tránh lặp lại logic đọc `brand` 2 nơi.
    `loras` — **đổi từ 1 LoRA đơn sang STACK nhiều LoRA** (`BrandProfile.style_loras`,
    xem docstring field đó) — theo đề xuất người dùng chống thiên lệch văn hoá Nhật/Hàn
    (1 LoRA "chất liệu" + 1 LoRA "hướng văn hoá" không mâu thuẫn nhau). `extra_negative`
    — `cultural_lock_negative` (mặc định đã có sẵn cụm loại trừ Nhật/Hàn), nối vào
    negative prompt THẬT gửi ComfyUI (`image_comfy_sdxl.py::_NEGATIVE_PROMPT`).
    `reference_images` — đọc bytes từng ảnh trong `BrandProfile.style_reference_paths`
    (IPAdapter — mới 2026-08-23), BỎ QUA ảnh nào không đọc được (file bị xoá tay ngoài
    app, hoặc lỗi đĩa) thay vì chặn hẳn việc sinh ảnh — đây là lớp TỐI ƯU PHONG CÁCH,
    không phải bắt buộc."""
    loras = [{"name": entry.get("name") or "", "strength": entry.get("strength") or 0.8} for entry in (brand.get("style_loras") or []) if entry.get("name")]
    reference_images = []
    for path_str in brand.get("style_reference_paths") or []:
        try:
            reference_images.append(Path(path_str).read_bytes())
        except OSError:
            continue
    return {
        "loras": loras,
        "extra_negative": (brand.get("cultural_lock_negative") or "").strip(),
        "reference_images": reference_images,
        "style_reference_weight": brand.get("style_reference_weight") or 0.6,
    }


def _try_generate_wan_anchor_image(db: Session, pdir, shot: dict, brand: dict, *, seed: int, aspect_ratio: str) -> bytes | None:
    """Sinh ẢNH ANCHOR bằng ĐÚNG pipeline SDXL đã tune (checkpoint/LoRA/prompt) cho
    ĐÚNG shot này — dùng làm khung hình đầu (`start_image`) cho Wan2.2, thay vì để Wan
    tự "tưởng tượng" cả cảnh từ noise thuần (T2V thuần, hành vi cũ) — **mới
    (2026-08-23)**, theo `StudioFlow_Video_Improvement_Plan.md` §3.1. KHÁC hẳn Tier 2
    cũ (mục ~18, đã tắt): đây là ảnh sinh RIÊNG cho từng shot (đúng nội dung/seed của
    NÓ), không phải 1 ảnh thumbnail dùng chung cho mọi shot trong project — tránh đúng
    lỗi lệch nội dung đã gặp trước đây.

    BEST-EFFORT: trả `None` (không raise) nếu chưa cấu hình provider ảnh `local_sdxl`,
    hoặc bước sinh ảnh lỗi bất kỳ — đây là bước TỐI ƯU CHẤT LƯỢNG, không được phép chặn
    việc sinh video (vẫn rơi về T2V thuần y hệt hành vi trước khi có tính năng này).
    Không gọi `record_asset_usage` — nội bộ, cost=$0 (local), tránh rác audit log."""
    try:
        image_providers = get_image_chain(db)
    except NoProviderConfiguredError:
        return None
    sdxl = next((p for p in image_providers if p.provider_name in _LOCAL_IMAGE_PROVIDER_NAMES), None)
    if sdxl is None:
        return None
    try:
        anchor_prompt = _build_visual_prompt(shot, brand, is_video=False, for_local_sdxl=True)
        data = sdxl.generate(anchor_prompt, seed=seed, aspect_ratio=aspect_ratio, **_local_sdxl_kwargs(brand))
        write_bytes(pdir / "assets" / f"{shot['shot_id']}_anchor.png", data)
        return data
    except Exception:  # noqa: BLE001
        return None


def _deterministic_seed(project_id: str, shot_id: str) -> int:
    """Seed cố định theo project_id+shot_id thay vì random theo thời gian gọi — cùng 1
    shot sinh lại (VD đổi provider fallback, hoặc người dùng bấm "Tạo lại" mà không đổi
    gì khác) ra kết quả tương đồng hơn thay vì hoàn toàn ngẫu nhiên mỗi lần, và các shot
    khác nhau trong CÙNG project vẫn có seed khác nhau (không trùng nhau) — Tier 1."""
    digest = hashlib.sha256(f"{project_id}:{shot_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (2**31 - 1)


def _read_voice_clone_ref(brand: dict) -> bytes | None:
    """Đọc bytes mẫu giọng thương hiệu (`BrandProfile.voice_clone_ref_path`, upload qua
    `POST /channels/{id}/brandprofile/voice-sample/upload`) để truyền làm
    `reference_audio` cho voice cloning (chỉ OmniVoice dùng tới, provider khác nhận rồi
    bỏ qua — xem `TTSProvider.synthesize()`, app/providers/base.py). Trả None nếu chưa
    cấu hình hoặc file bị xoá — không nên chặn sinh giọng đọc vì thiếu mẫu, coi như
    chưa có, quay lại giọng mặc định của provider."""
    path = brand.get("voice_clone_ref_path")
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return p.read_bytes()
    except OSError:
        return None


def _free_llm_vram_if_local(db: Session) -> None:
    """Nếu LLM mặc định đang là local (Ollama), yêu cầu giải phóng VRAM trước khi sinh
    Image/Video local — Ollama mặc định giữ model nạp sẵn ~5 phút sau lần gọi cuối, đủ
    để tranh chấp VRAM với ComfyUI (đo thật, gây thrashing — xem IMPLEMENTATION_REPORT.md
    mục 16.6b). Best-effort, không raise nếu lỗi — dọn VRAM thất bại không nên chặn việc
    sinh asset chính."""
    cfg = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task == "llm", ProviderConfig.connection_type == "local_endpoint", ProviderConfig.enabled == True)  # noqa: E712
        .first()
    )
    if cfg is None:
        return
    try:
        adapter = build_llm_provider(cfg)
    except Exception:  # noqa: BLE001
        return
    unload = getattr(adapter, "unload", None)
    if callable(unload):
        unload()


def generate_visual_asset(db: Session, p: Project, pdir, shot: dict, beat: dict, status: ShotRenderStatus, state: RenderState | None = None) -> None:
    """Sinh 1 asset hình/video cho 1 shot — dùng chung cho batch (run_asset_generation)
    và regenerate 1 shot riêng lẻ (app/routers/render.py). Bỏ qua nếu đã `ready` —
    tránh gọi API tốn phí lại khi `run_asset_generation` chạy lần 2 (VD sau khi 1 vài
    shot khác lỗi); muốn sinh lại 1 shot ĐÃ ready thì gọi trực tiếp từ endpoint
    regenerate (không qua đường batch này).

    Thử LẦN LƯỢT từng provider trong chain (mặc định trước, fallback sau nếu có cấu
    hình — `factory.py::get_image_chain`/`get_video_chain`) — dừng ở provider đầu
    tiên gọi API thành công; chỉ báo lỗi khi TẤT CẢ đều lỗi, gộp lý do từng lần thử.

    `state` (tuỳ chọn) — nếu có, ghi `render.json` NGAY sau khi set "generating", TRƯỚC
    khi gọi provider (có thể mất 30s-18 phút với video local). Thiếu bước này là lý do
    UI KHÔNG BAO GIỜ thấy được trạng thái "generating" thật — trước đây `save_render_state()`
    chỉ được gọi SAU KHI hàm này return (đã xong hẳn), nên đĩa nhảy thẳng
    pending→ready/error, dù trong bộ nhớ có đi qua "generating" — bug thật gặp lúc
    verify tính năng Dừng (IMPLEMENTATION_REPORT.md)."""
    if status.visual_status == "ready":
        return
    status.visual_status = "generating"
    status.visual_error = None
    status.visual_started_at = vn_isoformat(datetime.now(timezone.utc))
    if state is not None:
        save_render_state(pdir, state)
    brand = _load_brand_profile(p.channel_id)
    is_video = shot.get("visual_type") == "video"
    seed = _deterministic_seed(p.id, shot["shot_id"])
    # Tier 2 (ảnh Thumbnail làm "anchor" img2img cho ẢNH — mục 18) TẮT theo mặc định từ
    # 2026-08-16: verify thật qua GPU cho thấy khi Thumbnail là ảnh nhiều chi tiết đồ
    # hoạ (bản đồ minh hoạ, không phải ảnh chụp/nhân vật đơn giản), img2img ở MỌI mức
    # denoise thử qua đều hoặc (a) copy nguyên khung/chữ vào shot, hoặc (b) đè mất nội
    # dung riêng từng shot bằng bối cảnh chung của thumbnail — không có điểm cân bằng ổn
    # định. Người dùng chọn quay lại Tier 1 (chỉ nhất quán qua text — `_build_visual_prompt`
    # ở trên đã gộp visual_style_prompt) — an toàn hơn, nội dung shot luôn đúng mô tả
    # riêng. `reference_image` (biến này) vẫn dùng CHO ẢNH và CHO VIDEO CLOUD (Sora/
    # Veo/Flux — ngoài phạm vi cải tiến 2026-08-23), giữ `None`. RIÊNG `local_wan`
    # (video local) đã có anchor MỚI (2026-08-23, `_try_generate_wan_anchor_image`) —
    # khác Tier 2 cũ ở chỗ ảnh anchor sinh RIÊNG cho từng shot (không dùng chung 1
    # thumbnail cho cả project) nên không gặp lại lỗi lệch nội dung — xem biến
    # `wan_reference_image` tính riêng trong vòng lặp provider bên dưới.
    reference_image = None
    # Short-form (9:16) — mới (2026-08-21), theo yêu cầu người dùng: `Project.format`
    # quyết định tỷ lệ khung sinh ảnh/video — xem app/providers/base.py::AspectRatio.
    aspect_ratio = "9:16" if (p.format or "long") == "short" else "16:9"
    _free_llm_vram_if_local(db)
    try:
        providers = get_video_chain(db) if is_video else get_image_chain(db)
    except NoProviderConfiguredError as e:
        status.visual_status = "error"
        status.visual_error = str(e)
        status.visual_started_at = None
        return

    errors = []
    for provider in providers:
        # `for_local_sdxl` — mới (2026-08-22), theo yêu cầu người dùng: 1 chain có thể
        # vừa có local_sdxl (default) vừa có provider cloud (fallback), MỖI provider cần
        # đúng biến thể prompt của nó — không còn tính 1 lần dùng chung như trước (xem
        # docstring `_build_visual_prompt`).
        #
        # `local_wan` — **đổi (2026-08-23)**, Image-to-Video (xem `_build_video_motion_
        # prompt`/`_try_generate_wan_anchor_image`): prompt + ảnh mồi RIÊNG cho Wan,
        # khác hẳn nhánh `_build_visual_prompt` dùng chung cho provider video cloud.
        if is_video and provider.provider_name in _LOCAL_VIDEO_PROVIDER_NAMES:
            wan_reference_image = _try_generate_wan_anchor_image(db, pdir, shot, brand, seed=seed, aspect_ratio=aspect_ratio)
            prompt = _build_video_motion_prompt(shot, brand)
        else:
            wan_reference_image = None
            prompt = _build_visual_prompt(shot, brand, is_video=is_video, for_local_sdxl=(provider.provider_name in _LOCAL_IMAGE_PROVIDER_NAMES))
        try:
            if is_video:
                seconds = _video_duration_sec(beat)
                # gpu_lock chỉ cần cho provider GPU LOCAL (local_wan qua ComfyUI) —
                # Sora/Veo chạy trên hạ tầng nhà cung cấp, không tranh VRAM máy này,
                # không nên bị chặn chờ bởi LLM/Image local đang chạy (xem gpu_lock.py).
                # Giữ khoá suốt cả submit + poll (không chỉ start_generation) vì đây là
                # cả quá trình GPU máy này bận cho tới khi ComfyUI trả kết quả.
                if provider.provider_name in _LOCAL_VIDEO_PROVIDER_NAMES:
                    # `extra_negative` (cultural_lock_negative) — cùng lý do đã thêm cho
                    # local_sdxl (`_local_sdxl_kwargs`): Wan cũng học từ dữ liệu Á Đông
                    # thiên lệch Nhật/Hàn, cần loại trừ y hệt qua negative prompt THẬT.
                    with gpu_lock:
                        job_id = provider.start_generation(
                            prompt, seconds=seconds, seed=seed, reference_image=wan_reference_image, aspect_ratio=aspect_ratio,
                            extra_negative=(brand.get("cultural_lock_negative") or "").strip(),
                        )
                        data = _poll_video_until_done(provider, job_id, p.id)
                else:
                    job_id = provider.start_generation(prompt, seconds=seconds, seed=seed, reference_image=reference_image, aspect_ratio=aspect_ratio)
                    data = _poll_video_until_done(provider, job_id, p.id)
                ext = "mp4"
                cost = _VIDEO_COST_FN.get(provider.provider_name, estimate_sora_video_cost)(seconds, getattr(provider, "model_name", ""))
                unit_label = f"1 video (~{seconds}s)"
            else:
                # `loras`/`extra_negative` — **mới (2026-08-22, đổi 2026-08-23)** — CHỈ
                # truyền cho đúng `local_sdxl` (BrandProfile.style_loras + cultural_lock_
                # negative), không gọi chung cho mọi provider — xem docstring
                # `ComfySDXLImageProvider.generate()` (app/providers/image_comfy_sdxl.py)
                # lý do KHÔNG khai báo tham số này trên `ImageProvider` interface chung,
                # và `_local_sdxl_kwargs()` ở trên cho lý do gộp logic dùng chung.
                extra_kwargs = _local_sdxl_kwargs(brand) if provider.provider_name in _LOCAL_IMAGE_PROVIDER_NAMES else {}
                data = provider.generate(prompt, seed=seed, reference_image=reference_image, aspect_ratio=aspect_ratio, **extra_kwargs)
                ext = "png"
                cost = _IMAGE_COST_FN.get(provider.provider_name, estimate_openai_image_cost)(1, getattr(provider, "model_name", ""))
                unit_label = "1 ảnh"

            path = pdir / "assets" / f"{shot['shot_id']}.{ext}"
            write_bytes(path, data)
            status.visual_asset_path = str(path)
            status.visual_provider = provider.provider_name
            status.visual_status = "ready"
            status.visual_error = None
            status.visual_started_at = None
            status.visual_updated_at = vn_isoformat(datetime.now(timezone.utc))
            record_asset_usage(db, p.channel_id, p.title, provider=provider.provider_name, stage="visual", unit_label=unit_label, cost=cost)
            return
        except (GenerationCancelled, GenerationInterrupted) as e:
            # Huỷ thật (người dùng bấm dừng — phát hiện qua cờ `is_cancel_requested` phía
            # client HOẶC qua ComfyUI tự báo `execution_interrupted`, xem docstring
            # `GenerationInterrupted`) — KHÔNG thử fallback provider tiếp theo, dừng ngay
            # tại đây (khác lỗi provider thường, vẫn thử fallback bên dưới).
            status.visual_status = "error"
            status.visual_error = str(e)
            status.visual_started_at = None
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"{provider.provider_name}: {e}")

    status.visual_status = "error"
    status.visual_error = "; ".join(errors)
    status.visual_started_at = None


def generate_narration_asset(db: Session, p: Project, pdir, beat: dict, status: ShotRenderStatus, state: RenderState | None = None) -> None:
    """Sinh 1 clip giọng đọc — TTS hoá LỜI THOẠI THẬT (`beat.audio`), KHÔNG PHẢI
    `shot.audio_sfx` (đó là mô tả nhạc nền/cảm xúc, không phải lời đọc — xem
    specs/07 mục 7). `audio_sfx`/`direction` chỉ dùng làm gợi ý emotion. Bỏ qua nếu đã
    `ready` — cùng lý do tránh tốn phí lại như generate_visual_asset(). Cùng cơ chế
    fallback chain (default → fallback) như generate_visual_asset().

    `state` — ghi đĩa ngay khi chuyển "generating", cùng lý do đã ghi ở
    generate_visual_asset()."""
    if status.narration_status == "ready":
        return
    text = (beat.get("audio") or "").strip()
    if not text:
        status.narration_status = "ready"  # không có lời đọc ở beat này — bỏ qua, không phải lỗi
        return
    status.narration_status = "generating"
    status.narration_error = None
    status.narration_started_at = vn_isoformat(datetime.now(timezone.utc))
    if state is not None:
        save_render_state(pdir, state)
    brand = _load_brand_profile(p.channel_id)
    reference_audio = _read_voice_clone_ref(brand)
    try:
        providers = get_tts_chain(db)
    except NoProviderConfiguredError as e:
        status.narration_status = "error"
        status.narration_error = str(e)
        status.narration_started_at = None
        return

    emotion = beat.get("direction", "")
    errors = []
    for provider in providers:
        try:
            data = provider.synthesize(text, emotion=emotion, reference_audio=reference_audio)
            ext = _TTS_EXT.get(provider.provider_name, "mp3")
            path = pdir / "assets" / f"{status.shot_id}.{ext}"
            write_bytes(path, data)
            if state is not None and state.narration_speed != 1.0:
                _apply_narration_speed(path, state.narration_speed)
            status.narration_asset_path = str(path)
            status.narration_provider = provider.provider_name
            status.narration_duration_sec = _probe_audio_duration_sec(path)
            status.narration_status = "ready"
            status.narration_error = None
            status.narration_started_at = None
            status.narration_updated_at = vn_isoformat(datetime.now(timezone.utc))
            cost = _TTS_COST_FN.get(provider.provider_name, estimate_elevenlabs_tts_cost)(len(text), getattr(provider, "model_name", ""))
            record_asset_usage(db, p.channel_id, p.title, provider=provider.provider_name, stage="narration", unit_label=f"{len(text)} ký tự", cost=cost)
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"{provider.provider_name}: {e}")

    status.narration_status = "error"
    status.narration_error = "; ".join(errors)
    status.narration_started_at = None


def build_narration_download(project_id: str) -> Path:
    """Ghép narration TỪNG shot (đã sinh, `narration_status=="ready"`) thành 1 file
    audio DUY NHẤT cho toàn bộ script, theo đúng thứ tự timestamp — nút "Tải giọng đọc
    toàn bộ script" ở Script Studio (mục 30 IMPLEMENTATION_REPORT.md, 2026-08-16).

    Dùng `-filter_complex concat` (KHÔNG phải concat demuxer + `-c copy` như
    `assembly.py` dùng cho video) — mỗi shot có thể do provider TTS KHÁC NHAU sinh
    (Piper/OmniVoice trả WAV, ElevenLabs trả MP3, Gemini tự bọc WAV từ PCM thô —
    `_TTS_EXT`), demuxer đồng nhất+stream-copy sẽ lỗi khi codec khác nhau giữa các
    shot; filter concat GIẢI MÃ mọi input về PCM trước khi nối, không quan tâm codec
    gốc — an toàn với danh sách provider hỗn hợp.

    Raise `RuntimeError` (thông điệp tiếng Việt, hiển thị thẳng cho người dùng) nếu
    thiếu shot/ffmpeg/còn block chưa sinh xong."""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            raise RuntimeError("Không tìm thấy project")
        pdir = project_dir(p.channel_id, p.id)
        pack = read_json(pdir / "pack.json") or {}
        shots = sorted(pack.get("shots", []), key=lambda s: s.get("linked_timestamp_sec") or 0)
        if not shots:
            raise RuntimeError("Chưa có shot nào — cần sinh giọng đọc trước.")

        state = load_render_state(pdir, project_id)
        by_id = {s.shot_id: s for s in state.shots}
        missing: list[str] = []
        paths: list[str] = []
        for shot in shots:
            status = by_id.get(shot["shot_id"])
            if not status or status.narration_status != "ready" or not status.narration_asset_path:
                missing.append(shot["shot_id"])
            else:
                paths.append(status.narration_asset_path)
        if missing:
            preview = ", ".join(missing[:5]) + ("…" if len(missing) > 5 else "")
            raise RuntimeError(f"Còn {len(missing)} block chưa có giọng đọc sẵn sàng ({preview}) — sinh xong hết mới ghép/tải được.")

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("Chưa cài ffmpeg trên máy chạy backend.")

        out_path = pdir / "renders" / "narration_full.mp3"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        n = len(paths)
        cmd = [ffmpeg, "-y"]
        for path in paths:
            cmd += ["-i", path]
        filter_str = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        cmd += ["-filter_complex", filter_str, "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg lỗi khi ghép giọng đọc: {(result.stderr or '')[-800:]}")
        return out_path
    finally:
        db.close()
