"""Pipeline AI (lõi) — specs/03_api.md mục Pipeline + specs/07 prompt templates.

**Luồng chính (2026-08-17, mục 44 IMPLEMENTATION_REPORT.md — bỏ hẳn AI Research/
Outline/Hook/Full-Script + Pack Review/Gate #2 theo yêu cầu người dùng):**
Upload script (`/script/import/*`) → Script Studio → Visual Studio (sinh ảnh/video/
giọng đọc) → Output. Script import là con đường DUY NHẤT để có script trong Pack —
không còn đường AI tự viết. Không còn gate duyệt bắt buộc nào (`render/assemble`/
`/export` tự kiểm shot ready+approved trực tiếp thay vì dựa vào `project.status`)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json, write_json, write_versioned
from app.guardrail.check import annotate_body_with_warnings, run_guardrail_check
from app.models import AuditLog, Budget, Channel, Project
from app.pipeline import generation as gen
from app.pipeline.script_import import ScriptImportError, build_template_workbook, parse_script_file
from app.render.camera_motion import CAMERA_MOTIONS
from app.render.captions import DEFAULT_MAX_CUE_CHARS, split_block_into_cues
from app.render.intro import intro_duration_sec, resolve_intro_source
from app.render.schemas import NARRATION_LANGUAGES, RenderState
from app.render.transitions import TRANSITIONS
import json

router = APIRouter(tags=["pipeline"])


def record_usage(db: Session, channel_id: str, project_title: str, usage: list[dict]) -> None:
    """Ghi Audit Log chi phí + cộng dồn Budget.spent cho từng lệnh gọi LLM thật đã
    thành công trong request hiện tại (usage được generation.py append vào)."""
    if not usage:
        return
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    channel_name = ch.name if ch else channel_id
    total_cost = 0.0
    for u in usage:
        total_cost += u["cost"]
        tokens_label = f"{u['input_tokens']}+{u['output_tokens']} tok"
        db.add(
            AuditLog(
                action="Chi phí AI",
                detail=json.dumps({"project": project_title, "provider": "LLM", "model": u["model"], "stage": u["stage"], "tokens": tokens_label}, ensure_ascii=False),
                entity=channel_name,
                type="expense",
                cost=u["cost"],
            )
        )
    if total_cost > 0:
        budget = db.query(Budget).filter(Budget.channel_id == channel_id).first()
        if not budget:
            budget = Budget(channel_id=channel_id, soft_limit=8, threshold_pct=60, spent=0)
            db.add(budget)
            db.flush()
        budget.spent = (budget.spent or 0) + total_cost


def record_asset_usage(db: Session, channel_id: str, project_title: str, *, provider: str, stage: str, unit_label: str, cost: float) -> None:
    """Bản tương đương record_usage() cho chi phí sinh asset TTS/Image/Video (M2
    Production Layer) — không có input/output token nên không tái dùng nguyên
    record_usage(), nhưng ghi vào cùng AuditLog/Budget theo đúng convention (type
    "expense", cộng dồn Budget.spent) để màn Chi phí & Ngân sách hiện đúng, không cần
    sửa gì ở đó. Gọi từ app/render/engine.py (module tách biệt script core) — hàm này
    thuộc nhóm tiện ích billing dùng chung, không phải business logic của script core,
    nên đặt cạnh record_usage() là hợp lý (giống cách routers/guardrail.py đã import
    record_usage từ đây)."""
    if cost <= 0:
        return
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    channel_name = ch.name if ch else channel_id
    db.add(
        AuditLog(
            action="Chi phí AI",
            detail=json.dumps({"project": project_title, "provider": provider, "model": provider, "stage": stage, "tokens": unit_label}, ensure_ascii=False),
            entity=channel_name,
            type="expense",
            cost=cost,
        )
    )
    budget = db.query(Budget).filter(Budget.channel_id == channel_id).first()
    if not budget:
        budget = Budget(channel_id=channel_id, soft_limit=8, threshold_pct=60, spent=0)
        db.add(budget)
        db.flush()
    budget.spent = (budget.spent or 0) + cost


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return p


def _load(db: Session, p: Project):
    pdir = project_dir(p.channel_id, p.id)
    brand = read_json(pdir.parent.parent / "brandprofile.json") or {}
    brief = read_json(pdir / "brief.json") or {}
    pack = read_json(pdir / "pack.json") or {}
    return pdir, brand, brief, pack


def _save_pack(db: Session, p: Project, pack: dict, *, bump_version: bool = False, status_at_save: str = ""):
    pdir = project_dir(p.channel_id, p.id)
    version = (p.pack_version or 1) + (1 if bump_version else 0)
    pack["version"] = version
    write_versioned(pdir, "pack", pack, version)
    p.pack_version = version
    from app.models import PackVersion

    db.add(PackVersion(project_id=p.id, version=version, file_path=str(pdir / f"pack.v{version}.json"), status_at_save=status_at_save or pack.get("status", "")))
    return pack


# ---------------------------------------------------------------------------
class BlockAudioBody(BaseModel):
    audio: str


@router.patch("/projects/{project_id}/script/body/{index}/audio")
def edit_script_block_audio(project_id: str, index: int, body: BlockAudioBody, db: Session = Depends(get_db)):
    """Sửa tay nội dung Audio (VO) của 1 block RIÊNG LẺ — SAU KHI đã bóc tách theo đoạn
    (khác `PATCH /script/text`, sửa cả Full Script TRƯỚC KHI bóc tách). Nút "Sửa" cạnh
    cột Audio mỗi block ở Script Studio (2026-08-17, theo yêu cầu người dùng). Dùng
    INDEX (không phải `block_id`) làm khoá — script AI-viết không có `block_id` ổn định
    (mục 31 IMPLEMENTATION_REPORT.md), index là thứ duy nhất luôn có cho mọi loại
    script; block không bị sắp xếp lại nên an toàn.

    Đồng bộ lại `full_text` (nối toàn bộ `audio` từng block) — PackReview hiển thị
    `script.full_text` như 1 khối riêng, sửa từng block mà không cập nhật sẽ làm 2 chỗ
    lệch nhau."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    body_items = (pack.get("script") or {}).get("body") or []
    if index < 0 or index >= len(body_items):
        raise HTTPException(404, "Không tìm thấy block")
    body_items[index]["audio"] = body.audio
    pack["script"]["body"] = body_items
    pack["script"]["full_text"] = "\n\n".join(b.get("audio", "") for b in body_items if b.get("audio"))
    write_json(pdir / "pack.json", pack)
    return pack


class BlockTranslationBody(BaseModel):
    text: str


@router.patch("/projects/{project_id}/script/body/{index}/translation/{lang}")
def edit_script_block_translation(project_id: str, index: int, lang: str, body: BlockTranslationBody, db: Session = Depends(get_db)):
    """Sửa tay bản dịch VO của 1 block cho 1 NGÔN NGỮ (giọng đọc đa ngôn ngữ, 2026-09-04)
    — ghi vào `body[index].audio_by_lang[lang]`, KHÔNG đụng `audio` gốc (đó luôn là bản
    dịch của `primary_language`, xem `edit_script_block_audio` ở trên cho field đó).
    Dùng khi cần chỉnh 1 câu sau khi import file đa ngôn ngữ, không cần re-import cả
    file. `lang` phải thuộc `NARRATION_LANGUAGES` (app/render/schemas.py)."""
    if lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    body_items = (pack.get("script") or {}).get("body") or []
    if index < 0 or index >= len(body_items):
        raise HTTPException(404, "Không tìm thấy block")
    audio_by_lang = body_items[index].get("audio_by_lang") or {}
    audio_by_lang[lang] = body.text
    body_items[index]["audio_by_lang"] = audio_by_lang
    if lang == (brand.get("primary_language") or "vi"):
        body_items[index]["audio"] = body.text
    pack["script"]["body"] = body_items
    pack["script"]["full_text"] = "\n\n".join(b.get("audio", "") for b in body_items if b.get("audio"))
    write_json(pdir / "pack.json", pack)
    return pack


_SRT_DEFAULT_DURATION_SEC = 5.0


def _format_srt_timestamp(sec: float) -> str:
    sec = max(0.0, sec)
    total_ms = round(sec * 1000)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_srt(
    body: list[dict], *, shot_by_block_id: dict[str, dict], narration_by_shot_id: dict, intro_offset: float,
    lang: str | None = None, primary_language: str = "vi", max_cue_chars: int = DEFAULT_MAX_CUE_CHARS,
) -> str:
    """Sinh nội dung .srt chuẩn từ `script.body`.

    **Cắt nhỏ cue dài — mới (2026-09-12)**, theo yêu cầu người dùng: "File transcript srt
    đang chia timestamp theo block. Vấn đề là mỗi block có thể đọc quá dài nên việc hiển
    thị subtitle theo transcript bị tràn chữ. Cần cắt ngắn xuống" — TRƯỚC ĐÂY hàm này cố
    tình 1 cue/block NGUYÊN VĂN (xem lịch sử mục 52), giờ mỗi block được cắt thành nhiều
    cue ngắn hơn `max_cue_chars` qua `captions.split_block_into_cues` — timestamp mỗi
    cue chia lại theo tỷ lệ ký tự trên CHÍNH khoảng `(start, duration)` đã tính đúng theo
    giọng đọc THẬT của ngôn ngữ đang xử lý (xem đoạn dưới) — không đổi tổng thời lượng/vị
    trí từng block trên timeline, chỉ chia nhỏ HIỂN THỊ bên trong. Xem thêm docstring
    `captions.py` cho lý do timing luôn khớp ĐÚNG VO thật của từng ngôn ngữ dù không giả
    định tốc độ đọc/nói.

    **Đổi nguồn thời lượng (2026-08-20, theo yêu cầu người dùng)**: timestamp kịch bản
    (`timestamp_sec`/`end_sec`, nhập tay lúc import CSV/Excel) CHỈ mang tính THAM KHẢO —
    KHÔNG dùng để tính timeline transcript nữa (cùng lý do không dùng để render, xem
    `render/assembly.py::_shot_base_duration`: người dùng ước lượng timestamp có thể
    sai, VD ghi 40s nhưng giọng đọc TTS thật chỉ 34s). Ưu tiên độ dài GIỌNG ĐỌC THẬT
    (`narration_duration_sec`, đo qua ffprobe) của shot khớp `block_id` — chỉ fallback
    về timestamp kịch bản khi CHƯA sinh giọng đọc cho shot đó (transcript vẫn xuất được
    sớm, trước khi hoàn tất Visual Studio, chỉ kém chính xác hơn).

    `intro_offset` (giây) — cộng vào MỌI cue: nếu project có intro (shot mở đầu riêng
    HOẶC video/audio thương hiệu cấp kênh, xem `render/intro.py`), video ghép ra THẬT
    SỰ bắt đầu với đoạn intro đó TRƯỚC — transcript phải dịch theo đúng offset này mới
    khớp timeline video thật, không phải bắt đầu từ 0 như video không có intro.

    `lang` — **mới (2026-09-04)**, giọng đọc đa ngôn ngữ: `None` (mặc định) hoặc bằng
    `primary_language` giữ NGUYÊN hành vi cũ (đọc `b.audio`/field `narration_*` gốc của
    shot). Ngôn ngữ KHÁC đọc `b.audio_by_lang[lang]` + `status.narration_translations[lang]`
    — timeline theo giọng đọc THẬT của CHÍNH ngôn ngữ đó (không dùng lại thời lượng
    ngôn ngữ chính, vì bản dịch dài/ngắn khác nhau ra audio khác thời lượng)."""
    is_primary = lang is None or lang == primary_language
    cues: list[tuple[float, float, str]] = []
    cursor = intro_offset
    for b in body:
        text = (b.get("audio") if is_primary else (b.get("audio_by_lang") or {}).get(lang, "")) or ""
        text = text.strip()
        if not text:
            continue
        shot = shot_by_block_id.get(b.get("block_id"))
        status = narration_by_shot_id.get(shot["shot_id"]) if shot else None
        duration = None
        if status is not None:
            if is_primary:
                if status.narration_status == "ready" and status.narration_duration_sec:
                    duration = status.narration_duration_sec
            else:
                translation = status.narration_translations.get(lang)
                if translation is not None and translation.narration_status == "ready" and translation.narration_duration_sec:
                    duration = translation.narration_duration_sec
        if duration is None:
            start_raw = b.get("timestamp_sec")
            end_raw = b.get("end_sec")
            start_est = float(start_raw) if isinstance(start_raw, (int, float)) else 0.0
            end_est = float(end_raw) if isinstance(end_raw, (int, float)) and end_raw > start_est else start_est + _SRT_DEFAULT_DURATION_SEC
            duration = max(0.1, end_est - start_est)
        start = cursor
        end = cursor + duration
        cues.extend(split_block_into_cues(text, start, duration, max_chars=max_cue_chars))
        cursor = end
    lines: list[str] = []
    for i, (start, end, text) in enumerate(cues):
        lines.append(str(i + 1))
        lines.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _load_srt_context(db: Session, p: Project, project_id: str):
    pdir, brand, brief, pack = _load(db, p)
    body = (pack.get("script") or {}).get("body", [])
    shots = pack.get("shots", [])
    shot_by_block_id = {s.get("block_id"): s for s in shots if s.get("block_id")}
    render_raw = read_json(pdir / "render.json")
    render_state = RenderState.model_validate(render_raw) if render_raw else RenderState(project_id=project_id)
    narration_by_shot_id = {s.shot_id: s for s in render_state.shots}
    intro_source = resolve_intro_source(render_state.intro, brand, shots, narration_by_shot_id)
    intro_offset = intro_duration_sec(intro_source)
    return body, shot_by_block_id, narration_by_shot_id, intro_offset, brand.get("primary_language") or "vi"


@router.get("/projects/{project_id}/script/transcript-srt")
def download_transcript_srt(project_id: str, db: Session = Depends(get_db)):
    """Transcript kịch bản dạng `.srt` (timeline giống phụ đề) — mỗi block script = 1
    cue. Nút "Tải transcript (.srt)" ở Script Studio (2026-08-16, theo yêu cầu người
    dùng). Timeline dùng ĐỘ DÀI GIỌNG ĐỌC THẬT + offset intro (nếu có) — xem docstring
    `_build_srt` (2026-08-20, mục 52 IMPLEMENTATION_REPORT.md). Luôn xuất ngôn ngữ CHÍNH
    của kênh — xem `download_transcript_srt_lang` bên dưới cho ngôn ngữ khác."""
    p = _get_project_or_404(db, project_id)
    body, shot_by_block_id, narration_by_shot_id, intro_offset, primary_language = _load_srt_context(db, p, project_id)
    if not body:
        raise HTTPException(400, "Chưa có script để xuất transcript")

    content = _build_srt(body, shot_by_block_id=shot_by_block_id, narration_by_shot_id=narration_by_shot_id, intro_offset=intro_offset, primary_language=primary_language)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-subrip",
        headers={"Content-Disposition": 'attachment; filename="transcript.srt"'},
    )


@router.get("/projects/{project_id}/script/transcript-srt/{lang}")
def download_transcript_srt_lang(project_id: str, lang: str, db: Session = Depends(get_db)):
    """Transcript `.srt` cho 1 NGÔN NGỮ CỤ THỂ — giọng đọc đa ngôn ngữ (2026-09-04). Cùng
    logic `download_transcript_srt` ở trên, khác timeline nếu `lang` không phải ngôn ngữ
    chính (đọc `audio_by_lang[lang]` + `narration_translations[lang]`, xem `_build_srt`)."""
    if lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")
    p = _get_project_or_404(db, project_id)
    body, shot_by_block_id, narration_by_shot_id, intro_offset, primary_language = _load_srt_context(db, p, project_id)
    if not body:
        raise HTTPException(400, "Chưa có script để xuất transcript")

    content = _build_srt(body, shot_by_block_id=shot_by_block_id, narration_by_shot_id=narration_by_shot_id, intro_offset=intro_offset, lang=lang, primary_language=primary_language)
    if not content.strip():
        raise HTTPException(400, f"Chưa có văn bản/giọng đọc ngôn ngữ '{lang}' nào sẵn sàng để xuất.")
    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="transcript_{lang}.srt"'},
    )


@router.get("/projects/{project_id}/script/transcript-txt")
def download_transcript_txt(project_id: str, db: Session = Depends(get_db)):
    """Kịch bản dạng `.txt` THUẦN, KHÔNG timestamp (khác `.srt` ở trên) — mới
    (2026-09-12), theo yêu cầu người dùng: "Thêm nút tải kịch bản dạng .txt không có
    timestamp ở màn script studio cho mọi ngôn ngữ." Nút "Tải kịch bản (.txt)" ở Script
    Studio, cạnh nút .srt đã có. Luôn xuất ngôn ngữ CHÍNH của kênh — xem
    `download_transcript_txt_lang` bên dưới cho ngôn ngữ khác."""
    p = _get_project_or_404(db, project_id)
    _pdir, brand, _brief, pack = _load(db, p)
    body = (pack.get("script") or {}).get("body", [])
    if not body:
        raise HTTPException(400, "Chưa có script để xuất kịch bản")

    from app.render.pack_export import build_script_txt

    content = build_script_txt(pack, primary_language=brand.get("primary_language") or "vi")
    if not content.strip():
        raise HTTPException(400, "Chưa có nội dung lời thoại nào để xuất.")
    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="script.txt"'},
    )


@router.get("/projects/{project_id}/script/transcript-txt/{lang}")
def download_transcript_txt_lang(project_id: str, lang: str, db: Session = Depends(get_db)):
    """Kịch bản `.txt` THUẦN cho 1 NGÔN NGỮ CỤ THỂ — mới (2026-09-12). Cùng logic
    `download_transcript_txt` ở trên, khác nguồn văn bản nếu `lang` không phải ngôn ngữ
    chính (đọc `audio_by_lang[lang]`, xem `build_script_txt`)."""
    if lang not in NARRATION_LANGUAGES:
        raise HTTPException(400, f"Ngôn ngữ không hợp lệ — phải là 1 trong {NARRATION_LANGUAGES}")
    p = _get_project_or_404(db, project_id)
    _pdir, brand, _brief, pack = _load(db, p)
    body = (pack.get("script") or {}).get("body", [])
    if not body:
        raise HTTPException(400, "Chưa có script để xuất kịch bản")

    from app.render.pack_export import build_script_txt

    primary_language = brand.get("primary_language") or "vi"
    content = build_script_txt(pack, lang=lang, primary_language=primary_language)
    if not content.strip():
        raise HTTPException(400, f"Chưa có văn bản ngôn ngữ '{lang}' nào sẵn sàng để xuất.")
    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="script_{lang}.txt"'},
    )


@router.get("/projects/{project_id}/script/import/template")
def download_script_import_template(project_id: str, multilang: bool = False, db: Session = Depends(get_db)):
    """File Excel mẫu đúng cột `script_import.py::parse_script_rows()` yêu cầu, kèm
    dòng ví dụ — người dùng tải về, điền theo, rồi dùng lại chính nút "Nhập kịch bản
    từ file" bên cạnh. Nội dung mẫu tĩnh (không phụ thuộc project) nhưng vẫn đặt path
    lồng theo project cho nhất quán với 2 endpoint import/parse, import/confirm.

    `multilang` — **mới (2026-09-04)** — `True` trả mẫu 11 cột (1 VO/ngôn ngữ), dùng
    cho nút "Tải mẫu đa ngôn ngữ" ở Script Studio."""
    _get_project_or_404(db, project_id)
    filename = "mau-nhap-kich-ban-da-ngon-ngu.xlsx" if multilang else "mau-nhap-kich-ban.xlsx"
    return Response(
        content=build_template_workbook(multilang=multilang),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/projects/{project_id}/script/import/parse")
async def import_script_parse(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bước 1 nhập kịch bản từ CSV/Excel (đã build vòng 4) — chỉ parse & trả preview
    (số block/số từ/thời lượng ước tính), CHƯA lưu vào Pack. Khớp dialog xác nhận
    trong design. Parse phía server — xem app/pipeline/script_import.py.

    File có nhiều cột `VO (XX)` (giọng đọc đa ngôn ngữ, 2026-09-04) — cột trở thành
    `audio` gốc chọn theo `BrandProfile.primary_language` của kênh."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    content = await file.read()
    try:
        result = parse_script_file(content, file.filename or "", primary_language=brand.get("primary_language") or "vi")
    except ScriptImportError as e:
        raise HTTPException(400, str(e))
    return result


class ImportConfirmBody(BaseModel):
    beats: list[dict]
    full_text: str = ""


@router.post("/projects/{project_id}/script/import/confirm")
def import_script_confirm(project_id: str, body: ImportConfirmBody, db: Session = Depends(get_db)):
    """Bước 2 nhập kịch bản — ghi beats đã parse (từ /script/import/parse) vào Pack,
    nhảy thẳng tới Script Studio ở trạng thái đã duyệt. Đây là con đường DUY NHẤT để có
    script trong Pack (2026-08-17 — bỏ hẳn luồng AI Research/Outline/Hook/Full-Script,
    theo yêu cầu người dùng, xem IMPLEMENTATION_REPORT.md mục 44)."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    if not body.beats:
        raise HTTPException(400, "Không có block nào để nhập")

    full_text = body.full_text or "\n\n".join(b.get("audio", "") for b in body.beats if b.get("audio"))
    existing_script = pack.get("script") or {}
    pack["script"] = {
        "hook": existing_script.get("hook") or {"spoken": "", "visual": "", "duration_sec": 4},
        "body": body.beats,
        "cta": existing_script.get("cta") or {"spoken": "", "conversion_point": brief.get("strategy", {}).get("conversion_point", "none")},
        "full_text": full_text,
        "source": "import",
    }

    benchmark = brand.get("retention_benchmark", {})
    usage: list[dict] = []
    result = run_guardrail_check(
        db=db,
        hook_spoken="",  # script import không có Hook (AI Hook Variants đã bỏ) — không chấm Hook Strength, không cần Provider AI
        body=body.beats,
        benchmark=benchmark,
        forbidden=brand.get("forbidden", []),
        pain_points=brief.get("audience", {}).get("pain_points", []),
        usage=usage,
    )
    pack["script"]["body"] = annotate_body_with_warnings(body.beats, result["warnings"])
    pack["retention_check"] = result
    pack["status"] = "generating"
    _save_pack(db, p, pack, status_at_save="generating")

    p.step = 1
    p.max_step_reached = max(p.max_step_reached, 1)
    p.status = "generating"
    p.return_note = ""
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


def _seed_shot_from_beat(beat: dict, index: int) -> dict:
    """Khởi tạo shot trực tiếp từ nội dung block đã import — KHÔNG gọi AI, vì người
    dùng đã tự viết Visual/FX + Audio/SFX chi tiết trong file, gọi AI viết lại sẽ diễn
    giải lại (paraphrase) nội dung đã chuẩn, ngược ý định của việc import chính xác.
    Xem IMPLEMENTATION_REPORT.md mục "Đã build vòng 4"."""
    visual_type = "video" if str(beat.get("visual_type", "")).strip().lower().startswith("video") else "image"
    return {
        "shot_id": beat.get("block_id") or f"S{index + 1:02d}",
        "asset_type": "broll_video" if visual_type == "video" else "broll_image",
        "visual_type": visual_type,
        "provider": None,
        "visual_fx": beat.get("visual", ""),
        "audio_sfx": beat.get("direction", ""),
        "block_id": beat.get("block_id"),
        "linked_timestamp_sec": beat.get("timestamp_sec"),
    }


def _ensure_shots(pack: dict, body: list[dict]) -> list[dict]:
    """Tạo/ĐỒNG BỘ shot list — IDEMPOTENT với shot đã có (không ghi đè/xoá dữ liệu shot
    đã sinh visual/narration), nhưng vẫn bổ sung shot MỚI cho block chưa có shot, VÀ giữ
    ĐÚNG THỨ TỰ theo `body` (xem bug thật mục 131 bên dưới). Dùng chung cho
    `/visual/generate` (bấm "Đi tới Visual Studio") VÀ `/visual/ensure-shots-for-narration`
    (bấm "Sinh giọng đọc cho toàn bộ block" ở Script Studio, mục 30 IMPLEMENTATION_
    REPORT.md).

    **Bug thật phát hiện 2026-08-17 (mục 31)**: bản đầu tiên của hàm này ("tạo nếu rỗng,
    có gì thì trả nguyên") xử lý đúng trường hợp shots CHƯA TỪNG tạo, nhưng SAI khi
    người dùng SỬA/DUYỆT LẠI Full Script dài hơn (thêm block) sau khi shots đã tạo từ
    trước — `body` dài ra nhưng `pack.shots` (đã tồn tại) không bao giờ được mở rộng
    theo, "có gì thì trả nguyên" giữ mãi bộ shot CŨ NGẮN HƠN. Fix mục 31: đồng bộ theo
    `block_id` (field ổn định, duy nhất — KHÔNG dùng `linked_timestamp_sec` vì giá trị
    này có thể lệch giữa các lần tạo/sửa), block chưa có shot → tạo mới, APPEND vào cuối.

    **Bug thật TIẾP THEO phát hiện 2026-09-10 (mục 131)** — fix mục 31 tự nó lại sai khi
    block MỚI không nằm ở CUỐI `body` mà XEN KẼ giữa các block cũ (VD người dùng re-import
    thêm 8 block "K1".."K8" ở nhiều vị trí rải rác trong kịch bản — K1 ở đầu, K8 gần cuối,
    không phải toàn bộ 8 block dồn ở cuối). "APPEND vào cuối" (mục 31) khiến 8 shot K*
    MỚI bị dồn hết xuống CUỐI mảng `pack.shots`, lệch hẳn vị trí thật trong `body` — không
    chỉ SAI hiển thị ở Visual Studio (shot xen kẽ đúng chỗ trong Script Studio nhưng dồn
    cuối ở Visual Studio) mà còn ảnh hưởng THẬT tới lúc ghép video (`assembly.py` duyệt
    `pack.shots` ĐÚNG THEO THỨ TỰ MẢNG để dựng timeline — shot lệch vị trí = clip lệch vị
    trí trong video xuất ra).

    **Fix mục 131 — DỰNG LẠI mảng shots THEO ĐÚNG THỨ TỰ `body`**: với mỗi block trong
    `body` (theo đúng thứ tự), dùng LẠI shot đã có nếu khớp `block_id` (giữ nguyên toàn bộ
    dữ liệu đã sinh — không tạo mới đè lên), hoặc tạo mới bằng `_seed_shot_from_beat` nếu
    chưa có. Shot CŨ nào không còn khớp block nào trong `body` (hiếm — VD block bị xoá
    khỏi script lúc re-import) được GIỮ LẠI, nối vào CUỐI (không bao giờ xoá dữ liệu đã
    sinh, chỉ khác chỗ những shot này không còn "đúng vị trí" nào để xếp vào — đây là
    trường hợp biên, không phải luồng chính người dùng gặp).

    **Đơn giản hoá 2026-08-17 (mục 44)**: trước đây còn 1 nhánh AI tự sinh shot
    (`gen.generate_shots`) cho script KHÔNG phải import (`source != "import"`) — nhánh
    đó đã XOÁ cùng lúc bỏ AI Research/Outline/Hook/Full-Script, vì `script.source` giờ
    LUÔN LÀ `"import"` (đường DUY NHẤT còn lại để có script). Hàm này giờ chỉ còn đúng 1
    đường xử lý, không branch theo `source` nữa."""
    existing = pack.get("shots") or []
    by_block_id = {s.get("block_id"): s for s in existing if s.get("block_id")}
    body_block_ids = {b.get("block_id") for b in body}
    ordered = [by_block_id[b.get("block_id")] if b.get("block_id") in by_block_id else _seed_shot_from_beat(b, i) for i, b in enumerate(body)]
    orphaned = [s for s in existing if s.get("block_id") not in body_block_ids]
    return ordered + orphaned


@router.post("/projects/{project_id}/visual/ensure-shots-for-narration")
def ensure_shots_for_narration(project_id: str, db: Session = Depends(get_db)):
    """Tạo shot list nếu chưa có — KHÔNG đổi `step`/`status` (khác `/visual/generate`,
    vốn chuyển hẳn sang Visual Studio). Dùng khi bấm "Sinh giọng đọc cho toàn bộ block"
    ở Script Studio (step 1): `render/start` cần `pack.shots` tồn tại để lưu trạng thái
    narration theo `shot_id`, nhưng người dùng chưa hẳn muốn chuyển qua Visual Studio
    (mục 30 IMPLEMENTATION_REPORT.md, 2026-08-16). An toàn gọi nhiều lần (idempotent,
    xem `_ensure_shots`) — gọi lại sau khi shots đã có chỉ trả nguyên dữ liệu cũ."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    body = (pack.get("script") or {}).get("body", [])
    if not body:
        raise HTTPException(400, "Chưa có body script để sinh shot")
    pack["shots"] = _ensure_shots(pack, body)
    _save_pack(db, p, pack)
    db.commit()
    return pack


@router.post("/projects/{project_id}/visual/generate")
def generate_visual_shots(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    script = pack.get("script") or {}
    body = script.get("body", [])
    if not body:
        raise HTTPException(400, "Chưa có body script để sinh shot")

    pack["shots"] = _ensure_shots(pack, body)
    _save_pack(db, p, pack)
    p.step = 2
    p.max_step_reached = max(p.max_step_reached, 2)
    db.commit()
    return pack


class ShotBulkPatchBody(BaseModel):
    shot_ids: list[str]
    transition_to_next: str | None = None
    camera_motion: str | None = None


# **THỨ TỰ ĐĂNG KÝ QUAN TRỌNG** — route path LITERAL `/shots/bulk` PHẢI đăng ký TRƯỚC route
# có path PARAM `/shots/{shot_id}` bên dưới. FastAPI/Starlette khớp route theo ĐÚNG thứ tự
# đăng ký (không tự ưu tiên path cụ thể hơn path param) — nếu để SAU, request
# `PATCH .../shots/bulk` sẽ bị route `{shot_id}` "nuốt" trước (hiểu "bulk" là 1 shot_id),
# `patch_shots_bulk` bên dưới không bao giờ được gọi tới (404 "Không tìm thấy shot" thay vì
# chạy đúng logic bulk) — bug thật gặp lúc viết test, xem IMPLEMENTATION_REPORT.md mục 130.
@router.patch("/projects/{project_id}/visual/shots/bulk")
def patch_shots_bulk(project_id: str, body: ShotBulkPatchBody, db: Session = Depends(get_db)):
    """Sửa hàng loạt `transition_to_next`/`camera_motion` cho NHIỀU shot cùng lúc — mới
    (2026-09-10), theo yêu cầu người dùng: "cho phép bulk edit 2 lựa chọn ... cho nhiều
    hoặc tất cả block" ở Visual Studio. Đọc/ghi `pack.json` ĐÚNG 1 LẦN (không lặp N
    request PATCH đơn lẻ như `patch_shot` bên dưới — tránh đọc/ghi thừa khi áp dụng cho
    nhiều chục shot cùng lúc). Truyền được CẢ 2 field 1 lần hoặc CHỈ 1 field (field còn
    lại giữ nguyên, cùng nguyên tắc "None = không đổi" của `patch_shot`) — frontend gọi
    RIÊNG cho từng field (2 nút "Áp dụng" độc lập) nên trong thực tế luôn chỉ 1 field/lần,
    nhưng endpoint không giả định điều đó.

    KHÔNG validate `visual_type` của từng shot (VD áp `camera_motion` lên cả shot đang là
    video) — set field không dùng tới là VÔ HẠI (assembly.py chỉ đọc `camera_motion` khi
    `not is_video`, xem `_build_segment`), và `shot_ids` gửi lên đã được frontend tự lọc
    đúng loại shot phù hợp trước khi gọi (VD chỉ gửi shot ảnh cho camera_motion) — endpoint
    này chỉ áp dụng đúng những gì được yêu cầu, không tự ý lọc thêm."""
    if body.transition_to_next is None and body.camera_motion is None:
        raise HTTPException(400, "Cần ít nhất 1 trong 2 field transition_to_next/camera_motion")
    if body.transition_to_next is not None and body.transition_to_next not in TRANSITIONS:
        raise HTTPException(400, f"Transition không hợp lệ — chỉ nhận: {', '.join(TRANSITIONS)}")
    if body.camera_motion is not None and body.camera_motion not in CAMERA_MOTIONS:
        raise HTTPException(400, f"Hiệu ứng camera không hợp lệ — chỉ nhận: {', '.join(CAMERA_MOTIONS)}")
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    shot_id_set = set(body.shot_ids)
    matched = 0
    for s in pack.get("shots", []):
        if s["shot_id"] not in shot_id_set:
            continue
        matched += 1
        if body.transition_to_next is not None:
            s["transition_to_next"] = body.transition_to_next
        if body.camera_motion is not None:
            s["camera_motion"] = body.camera_motion
    if matched == 0:
        raise HTTPException(404, "Không tìm thấy shot nào khớp shot_ids")
    write_json(pdir / "pack.json", pack)
    return pack


class SaveShotsToVaultBody(BaseModel):
    shot_ids: list[str]


# Cùng lý do đăng ký TRƯỚC route `{shot_id}` bên dưới như `/shots/bulk` ở trên (mục 130) —
# `save-to-vault` là path LITERAL, phải đứng trước path PARAM để không bị "nuốt" nhầm.
@router.post("/projects/{project_id}/visual/shots/save-to-vault")
def save_shots_to_vault_endpoint(project_id: str, body: SaveShotsToVaultBody, db: Session = Depends(get_db)):
    """Lưu ảnh/video đã sinh của 1-nhiều shot vào Kho Tài Nguyên để tái sử dụng cho
    project khác cùng kênh — mới (2026-09-11), theo yêu cầu người dùng. Xem
    `asset_vault/from_visual_studio.py::save_shots_to_vault` cho logic đầy đủ (bỏ qua
    shot chưa sẵn sàng thay vì chặn cả batch, cập nhật đè nếu shot đã từng lưu)."""
    if not body.shot_ids:
        raise HTTPException(400, "Cần ít nhất 1 shot_id")
    p = _get_project_or_404(db, project_id)
    from app.asset_vault.from_visual_studio import save_shots_to_vault

    return save_shots_to_vault(db, p, body.shot_ids)


class ShotPatchBody(BaseModel):
    visual_fx: str | None = None
    audio_sfx: str | None = None
    visual_type: str | None = None
    transition_to_next: str | None = None
    camera_motion: str | None = None


@router.patch("/projects/{project_id}/visual/shots/{shot_id}")
def patch_shot(project_id: str, shot_id: str, body: ShotPatchBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    for s in pack.get("shots", []):
        if s["shot_id"] == shot_id:
            if body.visual_fx is not None:
                s["visual_fx"] = body.visual_fx
            if body.audio_sfx is not None:
                s["audio_sfx"] = body.audio_sfx
            if body.visual_type is not None:
                s["visual_type"] = body.visual_type
                s["asset_type"] = "broll_video" if body.visual_type == "video" else "broll_image"
            if body.transition_to_next is not None:
                if body.transition_to_next not in TRANSITIONS:
                    raise HTTPException(400, f"Transition không hợp lệ — chỉ nhận: {', '.join(TRANSITIONS)}")
                s["transition_to_next"] = body.transition_to_next
            if body.camera_motion is not None:
                if body.camera_motion not in CAMERA_MOTIONS:
                    raise HTTPException(400, f"Hiệu ứng camera không hợp lệ — chỉ nhận: {', '.join(CAMERA_MOTIONS)}")
                s["camera_motion"] = body.camera_motion
            break
    else:
        raise HTTPException(404, "Không tìm thấy shot")
    write_json(pdir / "pack.json", pack)
    return pack


def _find_shot_and_beat(pack: dict, shot_id: str):
    body = (pack.get("script") or {}).get("body", [])
    target = next((s for s in pack.get("shots", []) if s["shot_id"] == shot_id), None)
    if not target:
        raise HTTPException(404, "Không tìm thấy shot")
    beat = next((b for b in body if b.get("timestamp_sec") == target.get("linked_timestamp_sec")), body[0] if body else {})
    return target, beat


@router.post("/projects/{project_id}/visual/shots/{shot_id}/regenerate-visual")
def regenerate_shot_visual(project_id: str, shot_id: str, db: Session = Depends(get_db)):
    """Khôi phục Visual/FX về ĐÚNG script gốc (`beat.visual`) — **đổi 2026-08-25, theo
    yêu cầu người dùng**: trước đây gọi LLM diễn giải lại, giờ lấy nguyên si (xem
    docstring `app/pipeline/generation.py`). 400 nếu script gốc không có mô tả cho shot
    này — không còn rơi về 1 câu fallback vô nghĩa như trước."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    target, beat = _find_shot_and_beat(pack, shot_id)
    try:
        target["visual_fx"] = gen.restore_shot_visual_fx(beat)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    write_json(pdir / "pack.json", pack)
    db.commit()
    return pack


@router.post("/projects/{project_id}/visual/shots/{shot_id}/regenerate-audio")
def regenerate_shot_audio(project_id: str, shot_id: str, db: Session = Depends(get_db)):
    """Khôi phục Audio/SFX về ĐÚNG script gốc (`beat.direction`) — cùng lý do
    `regenerate_shot_visual` ở trên."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    target, beat = _find_shot_and_beat(pack, shot_id)
    try:
        target["audio_sfx"] = gen.restore_shot_audio_sfx(beat)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    write_json(pdir / "pack.json", pack)
    db.commit()
    return pack


@router.post("/projects/{project_id}/visual/generate-all-visual")
def generate_all_visual(project_id: str, db: Session = Depends(get_db)):
    """Header Visual Studio — "Tạo Visual cho toàn bộ block". **Đổi 2026-08-25**: khôi
    phục nguyên si từ script gốc (không LLM) — shot nào script gốc không có mô tả Visual
    thì BỎ QUA (khác 1 shot lẻ ở endpoint trên — raise lỗi ngay), không chặn cả batch."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    shots = pack.get("shots", [])
    body = (pack.get("script") or {}).get("body", [])
    if not shots:
        raise HTTPException(400, "Chưa có shot nào — vào Visual Studio trước")
    for s in shots:
        beat = next((b for b in body if b.get("timestamp_sec") == s.get("linked_timestamp_sec")), body[0] if body else {})
        try:
            s["visual_fx"] = gen.restore_shot_visual_fx(beat)
        except ValueError:
            continue
    write_json(pdir / "pack.json", pack)
    db.commit()
    return pack


@router.post("/projects/{project_id}/visual/generate-all-tts")
def generate_all_tts(project_id: str, db: Session = Depends(get_db)):
    """Header Visual Studio — "Tạo giọng đọc (TTS) cho toàn bộ block". Cùng lý do
    `generate_all_visual` ở trên — bỏ qua (không chặn batch) shot script gốc không có
    mô tả Audio/SFX."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    shots = pack.get("shots", [])
    body = (pack.get("script") or {}).get("body", [])
    if not shots:
        raise HTTPException(400, "Chưa có shot nào — vào Visual Studio trước")
    for s in shots:
        beat = next((b for b in body if b.get("timestamp_sec") == s.get("linked_timestamp_sec")), body[0] if body else {})
        try:
            s["audio_sfx"] = gen.restore_shot_audio_sfx(beat)
        except ValueError:
            continue
    write_json(pdir / "pack.json", pack)
    db.commit()
    return pack


@router.post("/projects/{project_id}/output/enter")
def enter_output(project_id: str, db: Session = Depends(get_db)):
    """Chuyển sang Output Center — nút "Đi tới Output →" ở Visual Studio. KHÔNG còn gate
    duyệt bắt buộc nào chặn trước bước này (2026-08-17, mục 44 IMPLEMENTATION_REPORT.md —
    bỏ hẳn Pack Review/Gate #2 theo yêu cầu người dùng); `render/assemble` và `/export`
    tự kiểm tra trực tiếp shot đã sẵn sàng + đã duyệt (`ShotRenderStatus`), không còn
    phụ thuộc `project.status` làm gate riêng."""
    p = _get_project_or_404(db, project_id)
    p.step = 3
    p.max_step_reached = max(p.max_step_reached, 3)
    p.status = "ready_output"
    db.commit()
    return {"step": p.step}
