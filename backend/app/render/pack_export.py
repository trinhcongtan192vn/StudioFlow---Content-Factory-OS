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
from app.render.captions import DEFAULT_MAX_CUE_CHARS, split_block_into_cues
from app.render.engine import _find_beat, _load_brand_profile, build_narration_download, load_render_state
from app.render.schemas import NARRATION_LANGUAGES, ShotRenderStatus


def _format_srt_timestamp(sec: float) -> str:
    ms_total = max(0, round(sec * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt_text(
    pack: dict, shots_state: list[ShotRenderStatus], *, lang: str | None = None, primary_language: str = "vi",
    max_cue_chars: int = DEFAULT_MAX_CUE_CHARS,
) -> str:
    """Timing = ĐÚNG logic `_shot_base_duration` dùng lúc ghép video (ưu tiên độ dài
    giọng đọc THẬT, fallback timestamp kịch bản khi chưa sinh) — khớp thời điểm thật
    của `narration_full.mp3` xuất cùng bundle này (mỗi shot nối liền nhau không khoảng
    trống, xem `build_narration_download`), để SRT tra đúng track audio đó. Shot không
    có lời thoại (`beat.audio` rỗng — VD shot chỉ hình không lời) KHÔNG tạo cue, nhưng
    vẫn cộng đủ thời lượng vào mốc thời gian chung để các shot SAU không bị lệch.

    `lang` — **mới (2026-09-04)**, giọng đọc đa ngôn ngữ: `None`/ngôn ngữ chính giữ
    NGUYÊN hành vi cũ. Ngôn ngữ khác đọc `beat.audio_by_lang[lang]` + thời lượng THẬT
    của `status.narration_translations[lang]` (fallback `_shot_base_duration` ngôn ngữ
    chính khi chưa sinh — timeline vẫn hợp lý dù chưa xong hẳn ngôn ngữ đó).

    **Cắt nhỏ cue dài — mới (2026-09-12)**, theo yêu cầu người dùng: "mỗi block có thể
    đọc quá dài nên việc hiển thị subtitle theo transcript bị tràn chữ. Cần cắt ngắn
    xuống". `text`/`dur` tính XONG như trên (đã đúng VO thật của TỪNG ngôn ngữ — xem
    docstring `captions.py`) rồi mới đưa qua `captions.split_block_into_cues` để cắt
    thành nhiều cue ngắn hơn `max_cue_chars`, timestamp chia lại theo tỷ lệ ký tự — dùng
    ĐÚNG khoảng `[t, t+dur)` đã tính, không đổi tổng thời lượng/vị trí shot trên timeline
    (chỉ chia nhỏ HIỂN THỊ bên trong, không ảnh hưởng shot khác)."""
    is_primary = lang is None or lang == primary_language
    shots = sorted(pack.get("shots", []), key=lambda s: s.get("linked_timestamp_sec") or 0)
    by_id = {s.shot_id: s for s in shots_state}
    lines: list[str] = []
    t = 0.0
    idx = 1
    for shot in shots:
        beat = _find_beat(pack, shot)
        status = by_id.get(shot["shot_id"])
        if is_primary:
            text = (beat.get("audio") or "").strip()
            dur = _shot_base_duration(status, beat, primary_language, primary_language) if status else _beat_duration(beat)
        else:
            text = ((beat.get("audio_by_lang") or {}).get(lang) or "").strip()
            translation = status.narration_translations.get(lang) if status else None
            if translation is not None and translation.narration_status == "ready" and translation.narration_duration_sec:
                dur = translation.narration_duration_sec
            else:
                # Chưa sinh xong giọng đọc ngôn ngữ này — fallback về độ dài NGÔN NGỮ
                # CHÍNH (không phải `lang` đang xét), giữ nguyên hành vi gốc trước khi
                # `_shot_base_duration` tổng quát hoá theo ngôn ngữ (2026-09-11).
                dur = _shot_base_duration(status, beat, primary_language, primary_language) if status else _beat_duration(beat)
        if text:
            for cue_start, cue_end, cue_text in split_block_into_cues(text, t, dur, max_chars=max_cue_chars):
                lines.append(f"{idx}\n{_format_srt_timestamp(cue_start)} --> {_format_srt_timestamp(cue_end)}\n{cue_text}\n")
                idx += 1
        t += dur
    return "\n".join(lines)


def build_script_txt(pack: dict, *, lang: str | None = None, primary_language: str = "vi") -> str:
    """Kịch bản dạng `.txt` THUẦN — KHÔNG timestamp/SRT numbering (khác `build_srt_text`
    ở trên) — mới (2026-09-12), theo yêu cầu người dùng: tải để đọc/duyệt/dịch nội dung
    liền mạch, không cần đồng bộ timeline. Xây ĐỘNG từ `pack.script.body` — CỐ Ý KHÔNG
    dùng `Script.full_text` (field đó chỉ là snapshot NGÔN NGỮ CHÍNH lúc import CSV/Excel
    ban đầu, không theo kịp chỉnh sửa từng block/bản dịch về sau, xem docstring
    `schemas/__init__.py::Script.full_text`). Duyệt theo ĐÚNG thứ tự `body` (nguồn sự
    thật cho thứ tự kịch bản, `pack.shots` cũng đã được đồng bộ khớp thứ tự này — xem
    mục 131 IMPLEMENTATION_REPORT.md). `lang=None`/bằng `primary_language` đọc
    `beat.audio` (ngôn ngữ chính); ngôn ngữ khác đọc `beat.audio_by_lang[lang]`. Block
    không có lời thoại (VD shot chỉ hình không lời) bị bỏ qua — không có timeline nào
    cần giữ chỗ như `build_srt_text`. Mỗi block cách nhau 1 dòng trống."""
    is_primary = lang is None or lang == primary_language
    body = (pack.get("script") or {}).get("body", [])
    lines: list[str] = []
    for b in body:
        text = (b.get("audio") if is_primary else (b.get("audio_by_lang") or {}).get(lang, "")) or ""
        text = text.strip()
        if text:
            lines.append(text)
    return "\n\n".join(lines)


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
        primary_language = _load_brand_profile(p.channel_id).get("primary_language") or "vi"

        # Hậu tố ngôn ngữ trong tên file transcript — **mới (2026-09-11), theo yêu cầu
        # người dùng** ("transcript cũng xử lý tương tự thành transcript_<lang>.srt") —
        # ĐỔI từ tên KHÔNG hậu tố cho ngôn ngữ chính (`transcript.srt`) sang CÓ hậu tố
        # luôn (`transcript_<primary_language>.srt`), nhất quán với `video_final_<lang>`/
        # `narration_full_<lang>`.
        primary_transcript_name = f"transcript_{primary_language}.srt"
        srt_text = build_srt_text(pack, state.shots)
        (out_dir / primary_transcript_name).write_text(srt_text, encoding="utf-8")
        included.append(primary_transcript_name)

        # Kịch bản .txt THUẦN, không timestamp — mới (2026-09-12), theo yêu cầu người
        # dùng ("Xuất pack cũng xuất các file này"), cùng quy ước hậu tố ngôn ngữ như
        # transcript/narration/video ở trên.
        primary_script_txt_name = f"script_{primary_language}.txt"
        script_txt = build_script_txt(pack, primary_language=primary_language)
        if script_txt.strip():
            (out_dir / primary_script_txt_name).write_text(script_txt, encoding="utf-8")
            included.append(primary_script_txt_name)
        else:
            skipped.append({"item": primary_script_txt_name, "reason": "Chưa có nội dung lời thoại nào."})

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

        # Hậu tố ngôn ngữ trong tên file narration_full — **mới (2026-09-11), theo yêu
        # cầu người dùng** ("tương tự với tên file narration_full, cũng thêm hậu tố ngôn
        # ngữ tương ứng", tiếp ngay sau yêu cầu tương tự cho video_final) — ĐỔI từ tên
        # KHÔNG hậu tố cho ngôn ngữ chính (`narration_full.mp3`) sang CÓ hậu tố luôn
        # (`narration_full_<primary_language>.mp3`), nhất quán với `video_final_<lang>`.
        primary_narration_name = f"narration_full_{primary_language}.mp3"
        try:
            narration_path = build_narration_download(project_id)
            shutil.copy2(narration_path, out_dir / primary_narration_name)
            included.append(primary_narration_name)
        except RuntimeError as e:
            skipped.append({"item": primary_narration_name, "reason": str(e)})

        # Giọng đọc đa ngôn ngữ (2026-09-04) — xuất transcript_<lang>.srt +
        # narration_full_<lang>.mp3 cho MỖI ngôn ngữ (khác ngôn ngữ chính, đã xuất ở
        # trên) có ÍT NHẤT 1 block đã có văn bản dịch. Ngôn ngữ chưa dùng tới (không
        # block nào có `audio_by_lang[lang]`) bị BỎ QUA HOÀN TOÀN — không thêm vào
        # `included`/`skipped`, tránh liệt kê rác cho ngôn ngữ dự án không quan tâm.
        body = (pack.get("script") or {}).get("body", [])
        for lang in NARRATION_LANGUAGES:
            if lang == primary_language:
                continue
            has_any_text = any((b.get("audio_by_lang") or {}).get(lang, "").strip() for b in body)
            if not has_any_text:
                continue
            srt_lang_text = build_srt_text(pack, state.shots, lang=lang, primary_language=primary_language)
            if srt_lang_text.strip():
                (out_dir / f"transcript_{lang}.srt").write_text(srt_lang_text, encoding="utf-8")
                included.append(f"transcript_{lang}.srt")
            script_txt_lang = build_script_txt(pack, lang=lang, primary_language=primary_language)
            if script_txt_lang.strip():
                (out_dir / f"script_{lang}.txt").write_text(script_txt_lang, encoding="utf-8")
                included.append(f"script_{lang}.txt")
            try:
                narration_lang_path = build_narration_download(project_id, lang=lang)
                shutil.copy2(narration_lang_path, out_dir / f"narration_full_{lang}.mp3")
                included.append(f"narration_full_{lang}.mp3")
            except RuntimeError as e:
                skipped.append({"item": f"narration_full_{lang}.mp3", "reason": str(e)})

        if state.assembly_status == "done" and state.final_video_path and Path(state.final_video_path).exists():
            final_src = Path(state.final_video_path)
            # Hậu tố ngôn ngữ trong tên file (2026-09-11, theo yêu cầu người dùng) — kể
            # từ khi có tính năng chọn ngôn ngữ xuất video (`state.final_video_lang`, xem
            # `assembly.py::_assemble_video_impl`), mỗi lần ghép lại có thể dùng 1 ngôn
            # ngữ khác nhau; đặt tên rõ ngôn ngữ NÀO đang nằm trong file này tránh nhầm
            # lẫn (VD ghép "de" rồi export Pack, sau đó ghép lại "vi" rồi export Pack lần
            # 2 vào CÙNG 1 thư mục đích — không có hậu tố sẽ ghi đè, tưởng nhầm còn bản
            # "de"). `final_video_lang` là `None` cho render cũ trước khi có field này —
            # fallback về ngôn ngữ chính của kênh.
            video_lang = state.final_video_lang or primary_language
            video_name = f"video_final_{video_lang}{final_src.suffix}"
            shutil.copy2(final_src, out_dir / video_name)
            included.append(video_name)
        else:
            skipped.append({"item": "video_final", "reason": "Chưa ghép video (hoặc lần ghép gần nhất chưa xong)."})

        # Short-video 9:16 xuất từ 1 khoảng block — mới (2026-09-12), theo yêu cầu người
        # dùng ("Phần xuất Pack lưu local cũng cần cover video short này với tiền tố hoặc
        # hậu tố trong tên file phù hợp"). Tiền tố `short_` + khoảng block (`<start>-
        # <end>`) — tự nhiên phân biệt tối đa 3 short-video/project mà không đụng độ tên
        # file, khớp quy ước hậu tố ngôn ngữ đã dùng cho video_final/narration_full/
        # transcript/script ở trên. Chỉ export nào ĐÃ xong (`status=="done"`) mới xuất —
        # export đang chạy dở/lỗi bị bỏ qua HOÀN TOÀN (không thêm vào `included`/
        # `skipped` — đây không phải nội dung "thiếu", chỉ đơn giản là chưa yêu cầu xuất).
        #
        # Hậu tố ngôn ngữ (`_<lang>`) — mới (2026-09-12, theo yêu cầu người dùng "cho phép
        # chọn ngôn ngữ khi xuất short-video") — CẦN THIẾT (không chỉ nhất quán): 2 export
        # CÙNG khoảng block nhưng KHÁC ngôn ngữ (VD B01-B05 tiếng Đức + B01-B05 tiếng Anh)
        # hoàn toàn hợp lệ (chiếm 2/3 slot khác nhau), thiếu hậu tố này sẽ ĐÈ tên file lên
        # nhau trong bundle. `export.lang` có thể `None` với export CŨ tạo trước tính
        # năng này — fallback về ngôn ngữ chính của kênh.
        for export in state.short_exports:
            if export.status != "done" or not export.video_path or not Path(export.video_path).exists():
                continue
            short_src = Path(export.video_path)
            short_lang = export.lang or primary_language
            short_name = f"short_{export.start_block_id}-{export.end_block_id}_{short_lang}{short_src.suffix}"
            shutil.copy2(short_src, out_dir / short_name)
            included.append(short_name)

        return {"dest_dir": str(out_dir), "included": included, "skipped": skipped}
    finally:
        db.close()
