"""Xuất short-video 9:16 từ 1 khoảng block — **mới (2026-09-12)**, theo yêu cầu người
dùng: repurpose 1 đoạn của project long-form thành YouTube Shorts/TikTok mà KHÔNG cần
tạo 1 project short-form riêng (xem docstring `ShortVideoExport` trong render/schemas.py
cho lý do KHÁC hẳn `Project.format=="short"`/`parent_project_id`). Artifact này sống
NGAY trong `RenderState.short_exports` của CHÍNH project long-form, tối đa
`MAX_SHORT_EXPORTS_PER_PROJECT` cái/project.

Short-video CHỈ gồm THUẦN các shot trong khoảng đã chọn (ảnh/video + giọng đọc, giữ
transition đã cấu hình giữa các shot) — KHÔNG kèm intro/nhạc nền/overlay thương hiệu như
video chính (`assembly.py::_assemble_video_impl`) — tránh phải tái dùng gần hết pipeline
đó, phạm vi đã chốt qua AskUserQuestion lúc lên kế hoạch. Tái dùng NGUYÊN VẸN các
primitive dựng segment/nối video của `assembly.py`
(`_build_segment`/`_run_boundaries`/`_concat_fast`/`_xfade_chain`/`_shot_base_duration`/
`_reflow_video_durations`/`_narration_for_lang`) — module này chỉ điều phối 1 luồng
NGẮN HƠN, không dựng lại logic ghép từ đầu.

**Chọn ngôn ngữ giọng đọc — mới (2026-09-12)**, theo yêu cầu người dùng ("cho phép chọn
ngôn ngữ khi xuất short-video, tương tự như khi render long-video"): `ShortVideoExport.lang`
mặc định ngôn ngữ CHÍNH của kênh, cùng gate cứng như `assemble_video` chính — 400 NGAY
nếu giọng đọc ngôn ngữ đã chọn CHƯA sinh xong, nhưng CHỈ soi shot TRONG KHOẢNG đã chọn
(không phải toàn project, xem `create_short_export`).
"""
from __future__ import annotations

import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import project_dir
from app.db import SessionLocal
from app.filestore import read_json, write_bytes
from app.models import Project
from app.providers.factory import NoProviderConfiguredError, get_image_chain
from app.render.assembly import (
    CODEC_MAP,
    CRF_TABLE,
    RESOLUTION_MAP_VERTICAL,
    _XFADE_DURATION_SEC,
    _build_segment,
    _concat_fast,
    _ensure_ffmpeg,
    _narration_for_lang,
    _reflow_video_durations,
    _run_boundaries,
    _shot_base_duration,
    _xfade_chain,
    resolve_video_codec,
)
from app.render.captions import write_shot_caption_ass
from app.render.engine import (
    _IMAGE_COST_FN,
    _build_visual_prompt,
    _deterministic_seed,
    _load_brand_profile,
    load_render_state,
    save_render_state,
)
from app.providers.image_openai import estimate_cost as estimate_openai_image_cost
from app.render.schemas import NARRATION_LANGUAGES, RenderState, ShortVideoExport, ShotRenderStatus
from app.routers.pipeline import record_asset_usage
from app.timeutil import vn_isoformat

MAX_SHORT_EXPORTS_PER_PROJECT = 3

# Cấu hình export CỐ ĐỊNH — không thêm UI chọn độ phân giải/codec/chất lượng cho tính
# năng này (ngoài phạm vi yêu cầu, giữ UI đơn giản: 2 ô mã block + 1 checkbox + 1 nút).
_EXPORT_RESOLUTION = RESOLUTION_MAP_VERTICAL["1080p"]
_EXPORT_CODEC = "h264"
_EXPORT_QUALITY = "medium"


def _resolve_block_range(pack: dict, start_block_id: str, end_block_id: str) -> list[dict]:
    """Tìm khoảng block trong `pack['script']['body']` (nguồn thứ tự block THẬT — mã
    block do người dùng nhập tay có thể KHÔNG map 1-1 với `pack['shots']` nếu 1 block bị
    xoá shot hoặc chưa từng có shot), rồi lọc `pack['shots']` khớp `block_id` nằm trong
    khoảng đó — GIỮ NGUYÊN thứ tự của `pack['shots']` (mirror thứ tự body, xem mục 131
    IMPLEMENTATION_REPORT.md). Raise `ValueError` (caller quy đổi ra 400) nếu block đầu/
    cuối không tồn tại, thứ tự ngược, hoặc khoảng không chứa shot nào."""
    body = (pack.get("script") or {}).get("body", [])
    block_ids_in_order = [b.get("block_id") for b in body]
    try:
        start_idx = block_ids_in_order.index(start_block_id)
    except ValueError:
        raise ValueError(f'Không tìm thấy mã block đầu "{start_block_id}" trong kịch bản.')
    try:
        end_idx = block_ids_in_order.index(end_block_id)
    except ValueError:
        raise ValueError(f'Không tìm thấy mã block cuối "{end_block_id}" trong kịch bản.')
    if start_idx > end_idx:
        raise ValueError("Mã block đầu phải đứng trước (hoặc trùng) mã block cuối trong kịch bản.")
    block_ids_in_range = set(block_ids_in_order[start_idx : end_idx + 1])
    shots_in_range = [s for s in pack.get("shots", []) if s.get("block_id") in block_ids_in_range]
    if not shots_in_range:
        raise ValueError("Không có shot nào trong khoảng block đã chọn.")
    return shots_in_range


def create_short_export(db, project: Project, start_block_id: str, end_block_id: str, regenerate_images: bool, lang: str | None = None) -> ShortVideoExport:
    """Tạo entry `ShortVideoExport` mới (status="pending") — validate cap 3 + khoảng
    block + ngôn ngữ giọng đọc NGAY TẠI ĐÂY (400 tức thì ở router), KHÔNG đợi tới lúc
    chạy nền (`run_short_export`) mới báo lỗi. Router tự
    `background_tasks.add_task(run_short_export, project.id, export.id)` sau khi hàm này
    trả về thành công.

    `lang` — **mới (2026-09-12)**, theo yêu cầu người dùng ("cho phép chọn ngôn ngữ khi
    xuất short-video, tương tự như khi render long-video"): `None`/không hợp lệ → ngôn
    ngữ CHÍNH của kênh. RESOLVE + LƯU LUÔN vào `export.lang` (không lưu nguyên giá trị
    tham số thô) — `run_short_export` đọc thẳng `export.lang`, không cần tính lại. Cùng
    gate cứng như `routers/render.py::start_assemble` (400 nếu giọng đọc chưa sinh xong)
    nhưng CHỈ soi shot TRONG KHOẢNG đã chọn — không chặn nhầm vì shot NGOÀI khoảng chưa
    có giọng đọc ngôn ngữ này."""
    pdir = project_dir(project.channel_id, project.id)
    state = load_render_state(pdir, project.id)
    if len(state.short_exports) >= MAX_SHORT_EXPORTS_PER_PROJECT:
        raise ValueError(f"Đã đủ {MAX_SHORT_EXPORTS_PER_PROJECT} short-video cho project này — xoá bớt 1 cái trước khi xuất thêm.")
    pack = read_json(pdir / "pack.json") or {}
    shots = _resolve_block_range(pack, start_block_id, end_block_id)  # raise ValueError nếu sai

    if lang is not None and lang not in NARRATION_LANGUAGES:
        raise ValueError(f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")
    brand = _load_brand_profile(project.channel_id)
    primary_language = brand.get("primary_language") or "vi"
    export_lang = lang if lang in NARRATION_LANGUAGES else primary_language

    by_id = {s.shot_id: s for s in state.shots}
    missing_narration = [
        s["shot_id"] for s in shots
        if _narration_for_lang(by_id.get(s["shot_id"]) or ShotRenderStatus(shot_id=s["shot_id"]), export_lang, primary_language)[0] != "ready"
    ]
    if missing_narration:
        raise ValueError(
            f"Giọng đọc [{export_lang}] chưa sinh xong cho {len(missing_narration)} shot trong khoảng: "
            f"{', '.join(missing_narration[:5])}{'...' if len(missing_narration) > 5 else ''} — "
            "sinh xong giọng đọc ở ngôn ngữ này trước khi xuất short-video."
        )

    export = ShortVideoExport(
        id=f"short_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
        start_block_id=start_block_id,
        end_block_id=end_block_id,
        regenerate_images=regenerate_images,
        lang=export_lang,
        status="pending",
        created_at=vn_isoformat(datetime.now(timezone.utc)),
    )
    state.short_exports.append(export)
    save_render_state(pdir, state)
    return export


def delete_short_export(project: Project, export_id: str) -> RenderState:
    """Xoá 1 `ShortVideoExport` — file video + thư mục asset riêng (nếu có) + entry
    trong `state.short_exports`, giải phóng lại 1 slot trong cap 3."""
    pdir = project_dir(project.channel_id, project.id)
    state = load_render_state(pdir, project.id)
    export = next((e for e in state.short_exports if e.id == export_id), None)
    if export is None:
        raise ValueError("Không tìm thấy short-video này.")
    if export.video_path:
        Path(export.video_path).unlink(missing_ok=True)
    export_dir = pdir / "renders" / "short" / export.id
    if export_dir.exists():
        shutil.rmtree(export_dir, ignore_errors=True)
    state.short_exports = [e for e in state.short_exports if e.id != export_id]
    save_render_state(pdir, state)
    return state


def _regenerate_images_for_export(db, p: Project, pdir: Path, brand: dict, shots: list[dict], export_dir: Path, export: ShortVideoExport, state: RenderState) -> dict[str, str]:
    """Sinh lại ẢNH (KHÔNG BAO GIỜ video — theo yêu cầu người dùng, sinh lại video 9:16
    tốn kém/chậm hơn hẳn ảnh, ngoài phạm vi tính năng này) theo đúng tỷ lệ 9:16 cho từng
    shot ẢNH trong khoảng, lưu vào thư mục RIÊNG của export (`{export_dir}/assets/`) —
    KHÔNG đụng `ShotRenderStatus.visual_asset_path` gốc 16:9. Trả `{shot_id: path}` cho
    những shot đã sinh lại thành công — shot KHÔNG có trong dict này (shot VIDEO, hoặc
    `regenerate_images=False`) dùng asset gốc + crop-fill (không letterbox — xem ghi chú
    2026-09-12 ở vòng lặp build segment) lúc build segment.

    Cập nhật `progress_current/total/label` SAU MỖI ảnh, lưu `render.json` ngay — cùng
    pattern incremental-progress đã dùng ở `auto_detect_scenes`/`generate_visual_asset`,
    để UI poll thấy tiến độ thật thay vì nhảy thẳng 0%→100%."""
    image_shots = [s for s in shots if s.get("visual_type") != "video"]
    regenerated: dict[str, str] = {}
    if not image_shots:
        return regenerated
    assets_dir = export_dir / "assets"
    export.status = "generating_images"
    export.progress_current = 0
    export.progress_total = len(image_shots)
    export.progress_label = "Đang sinh ảnh theo tỷ lệ 9:16..."
    save_render_state(pdir, state)

    try:
        providers = get_image_chain(db)
    except NoProviderConfiguredError as e:
        raise RuntimeError(str(e)) from e

    for i, shot in enumerate(image_shots):
        seed = _deterministic_seed(p.id, shot["shot_id"])
        errors: list[str] = []
        for provider in providers:
            prompt = _build_visual_prompt(shot, brand, is_video=False)
            try:
                data = provider.generate(prompt, seed=seed, reference_image=None, aspect_ratio="9:16")
                path = assets_dir / f"{shot['shot_id']}.png"
                write_bytes(path, data)
                cost = _IMAGE_COST_FN.get(provider.provider_name, estimate_openai_image_cost)(1, getattr(provider, "model_name", ""))
                record_asset_usage(db, p.channel_id, p.title, provider=provider.provider_name, stage="visual", unit_label="1 ảnh (short 9:16)", cost=cost)
                regenerated[shot["shot_id"]] = str(path)
                break
            except Exception as e:  # noqa: BLE001
                errors.append(f"{provider.provider_name}: {e}")
        else:
            raise RuntimeError(f"Sinh ảnh 9:16 lỗi cho shot {shot['shot_id']}: {'; '.join(errors)}")
        export.progress_current = i + 1
        save_render_state(pdir, state)
    return regenerated


def run_short_export(project_id: str, export_id: str) -> None:
    """Chạy nền (FastAPI BackgroundTasks) — TRY/EXCEPT tổng ghi `status="error"`, không
    crash tiến trình nền, khớp pattern `assemble_video`."""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        pdir = project_dir(p.channel_id, p.id)
        state = load_render_state(pdir, project_id)
        export = next((e for e in state.short_exports if e.id == export_id), None)
        if export is None:
            return
        try:
            ffmpeg = _ensure_ffmpeg()
            pack = read_json(pdir / "pack.json") or {}
            shots = _resolve_block_range(pack, export.start_block_id, export.end_block_id)
            by_id = {s.shot_id: s for s in state.shots}
            body_by_block = {b.get("block_id"): b for b in (pack.get("script") or {}).get("body", [])}
            brand = _load_brand_profile(p.channel_id)
            primary_language = brand.get("primary_language") or "vi"
            # `export.lang` LUÔN đã resolve sẵn ở `create_short_export` — `or
            # primary_language` chỉ còn là lưới an toàn cho export CŨ tạo TRƯỚC tính
            # năng chọn ngôn ngữ (field mặc định `None`).
            export_lang = export.lang or primary_language

            statuses = []
            for shot in shots:
                status = by_id.get(shot["shot_id"])
                if not status or not status.visual_asset_path or status.visual_status != "ready":
                    raise RuntimeError(f"Shot {shot['shot_id']} (block {shot.get('block_id')}) chưa sinh xong visual — không thể xuất short-video.")
                statuses.append(status)

            export_dir = pdir / "renders" / "short" / export.id
            (export_dir / "assets").mkdir(parents=True, exist_ok=True)
            regenerated_paths = _regenerate_images_for_export(db, p, pdir, brand, shots, export_dir, export, state) if export.regenerate_images else {}

            export.status = "assembling"
            export.progress_current = None
            export.progress_total = None
            export.progress_label = "Đang ghép video..."
            save_render_state(pdir, state)

            video_codec = resolve_video_codec(_EXPORT_CODEC, use_gpu=False)
            _, audio_codec, ext = CODEC_MAP[_EXPORT_CODEC]
            crf = CRF_TABLE[_EXPORT_CODEC][_EXPORT_QUALITY]
            resolution = _EXPORT_RESOLUTION

            durations: list[float] = []
            for shot, status in zip(shots, statuses):
                beat = body_by_block.get(shot.get("block_id"), {})
                durations.append(_shot_base_duration(status, beat, export_lang, primary_language))
            _reflow_video_durations(statuses, durations, export_lang, primary_language)

            has_transitions = any((s.get("transition_to_next") or "cut") != "cut" for s in shots[:-1]) if len(shots) > 1 else False

            # Đệm lặng đầu/cuối giọng đọc tại ranh giới transition — cùng lý do/cơ chế đã
            # sửa cho `assemble_video` chính (xem docstring `_build_segment`): không đệm
            # sẽ "nuốt chữ" giọng đọc ở ranh giới xfade. Không có khái niệm "intro" ở
            # short-video (luôn "cut" — export CHỈ gồm thuần shot trong khoảng).
            lead_ins: list[float] = []
            lead_outs: list[float] = []
            for i, shot in enumerate(shots):
                _n_status, _n_asset_path, _ = _narration_for_lang(statuses[i], export_lang, primary_language)
                has_narration = _n_status == "ready" and bool(_n_asset_path)
                needs_lead_in = has_narration and i > 0 and (shots[i - 1].get("transition_to_next") or "cut") != "cut"
                needs_lead_out = has_narration and i < len(shots) - 1 and (shot.get("transition_to_next") or "cut") != "cut"
                lead_in = _XFADE_DURATION_SEC if needs_lead_in else 0.0
                lead_out = _XFADE_DURATION_SEC if needs_lead_out else 0.0
                lead_ins.append(lead_in)
                lead_outs.append(lead_out)
                durations[i] += lead_in + lead_out

            segments_dir = export_dir / "segments"
            segments_dir.mkdir(parents=True, exist_ok=True)
            seg_paths: list[Path] = []
            for i, (shot, status) in enumerate(zip(shots, statuses)):
                _n_status, narration_path, _ = _narration_for_lang(status, export_lang, primary_language)
                if _n_status != "ready":
                    narration_path = None
                regenerated = regenerated_paths.get(shot["shot_id"])
                # Ảnh ĐÃ sinh lại đúng 9:16 → brand THẬT (cover-crop bình thường, an toàn
                # vì ảnh đã đúng tỷ lệ). Asset GỐC 16:9 (ảnh không sinh lại, HOẶC mọi shot
                # video) → dict brand TẠM THỜI ép "crop" — **đổi (2026-09-12), theo yêu
                # cầu người dùng**: bản đầu dùng letterbox (viền đen, hiện FULL khung
                # ngang, không crop) nhưng người dùng báo ảnh bị "co hẹp" (thumbnail nhỏ
                # lại giữa 2 viền đen) — yêu cầu KHÔNG co ảnh, CHỈ crop phần giữa cho khớp
                # 9:16 (phóng khung ngang lên vừa CHIỀU CAO khung dọc rồi cắt bớt 2 bên,
                # xem `_scale_cover_filter`). Ép CỐ ĐỊNH "crop" ở đây (KHÔNG đọc
                # `brand.aspect_fill_mode` thật của kênh) — hành vi short-video độc lập
                # với tuỳ chọn crop/blur của video chính, luôn nhất quán 1 kiểu.
                if regenerated:
                    visual_path, seg_brand = regenerated, brand
                else:
                    visual_path, seg_brand = status.visual_asset_path, {**brand, "aspect_fill_mode": "crop"}
                seg_path = segments_dir / f"segment_{i:03d}.{ext}"

                # Caption Layer (burn-in) — mới (2026-09-12), theo yêu cầu người dùng:
                # áp dụng CHO CẢ short-video export, dùng CHUNG `state.caption_layer`
                # với video chính (nhất quán, tái dùng nguyên `_build_segment`). Xem
                # `assembly.py::_build_one_segment` cho cùng logic/lý do đầy đủ.
                caption_ass_path = None
                if state.caption_layer and state.caption_layer.enabled:
                    beat = body_by_block.get(shot.get("block_id"), {})
                    caption_lang = state.caption_layer.lang if state.caption_layer.lang in NARRATION_LANGUAGES else export_lang
                    caption_text = (beat.get("audio") if caption_lang == primary_language else (beat.get("audio_by_lang") or {}).get(caption_lang, "")) or ""
                    ass_path = segments_dir / f"caption_{i:03d}.ass"
                    cap_w, cap_h = map(int, resolution.split(":"))
                    if write_shot_caption_ass(
                        ass_path, caption_text, durations[i],
                        position=state.caption_layer.position, size_pct=state.caption_layer.size_pct, opacity=state.caption_layer.opacity,
                        out_w=cap_w, out_h=cap_h,
                    ):
                        caption_ass_path = str(ass_path)

                _build_segment(
                    ffmpeg, visual_path, narration_path, durations[i], seg_path,
                    resolution=resolution, video_codec=video_codec, audio_codec=audio_codec, crf=crf,
                    ensure_audio_track=has_transitions, camera_motion=shot.get("camera_motion") or "none",
                    narration_lead_in_sec=lead_ins[i], narration_lead_out_sec=lead_outs[i], brand=seg_brand,
                    caption_ass_path=caption_ass_path,
                )
                seg_paths.append(seg_path)

            final_path = export_dir / f"short_final.{ext}"
            if not has_transitions:
                _concat_fast(ffmpeg, seg_paths, final_path)
            else:
                boundaries = _run_boundaries(shots)
                run_paths: list[Path] = []
                run_durations: list[float] = []
                run_transitions: list[str] = []
                for r in range(len(boundaries) - 1):
                    start, end = boundaries[r], boundaries[r + 1]
                    run_segs = seg_paths[start:end]
                    run_dur = sum(durations[start:end])
                    if len(run_segs) == 1:
                        run_path = run_segs[0]
                    else:
                        run_path = segments_dir / f"run_{r:02d}.{ext}"
                        _concat_fast(ffmpeg, run_segs, run_path)
                    run_paths.append(run_path)
                    run_durations.append(run_dur)
                    if end < len(shots):
                        run_transitions.append(shots[end - 1].get("transition_to_next") or "cut")
                _xfade_chain(ffmpeg, run_paths, run_durations, run_transitions, final_path, video_codec=video_codec, audio_codec=audio_codec, crf=crf)

            export.video_path = str(final_path)
            export.status = "done"
            export.error = None
            export.progress_current = None
            export.progress_total = None
            export.progress_label = None
        except Exception as e:  # noqa: BLE001
            export.status = "error"
            export.error = str(e)
            export.progress_current = None
            export.progress_total = None
            export.progress_label = None
        finally:
            save_render_state(pdir, state)
    finally:
        db.close()
