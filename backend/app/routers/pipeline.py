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
from app.providers.factory import get_llm
from app.render.camera_motion import CAMERA_MOTIONS
from app.render.intro import intro_duration_sec, resolve_intro_source
from app.render.schemas import RenderState
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


_SRT_DEFAULT_DURATION_SEC = 5.0


def _format_srt_timestamp(sec: float) -> str:
    sec = max(0.0, sec)
    total_ms = round(sec * 1000)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_srt(body: list[dict], *, shot_by_block_id: dict[str, dict], narration_by_shot_id: dict, intro_offset: float) -> str:
    """Sinh nội dung .srt chuẩn từ `script.body` — 1 cue/block (KHÔNG tự tách câu dài
    thành nhiều dòng phụ đề ngắn như phần mềm sub chuyên dụng — đủ dùng làm transcript
    có timeline theo dõi, đúng phạm vi yêu cầu).

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
    khớp timeline video thật, không phải bắt đầu từ 0 như video không có intro."""
    cues: list[tuple[float, float, str]] = []
    cursor = intro_offset
    for b in body:
        text = (b.get("audio") or "").strip()
        if not text:
            continue
        shot = shot_by_block_id.get(b.get("block_id"))
        status = narration_by_shot_id.get(shot["shot_id"]) if shot else None
        if status is not None and status.narration_status == "ready" and status.narration_duration_sec:
            duration = status.narration_duration_sec
        else:
            start_raw = b.get("timestamp_sec")
            end_raw = b.get("end_sec")
            start_est = float(start_raw) if isinstance(start_raw, (int, float)) else 0.0
            end_est = float(end_raw) if isinstance(end_raw, (int, float)) and end_raw > start_est else start_est + _SRT_DEFAULT_DURATION_SEC
            duration = max(0.1, end_est - start_est)
        start = cursor
        end = cursor + duration
        cues.append((start, end, text))
        cursor = end
    lines: list[str] = []
    for i, (start, end, text) in enumerate(cues):
        lines.append(str(i + 1))
        lines.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


@router.get("/projects/{project_id}/script/transcript-srt")
def download_transcript_srt(project_id: str, db: Session = Depends(get_db)):
    """Transcript kịch bản dạng `.srt` (timeline giống phụ đề) — mỗi block script = 1
    cue. Nút "Tải transcript (.srt)" ở Script Studio (2026-08-16, theo yêu cầu người
    dùng). Timeline dùng ĐỘ DÀI GIỌNG ĐỌC THẬT + offset intro (nếu có) — xem docstring
    `_build_srt` (2026-08-20, mục 52 IMPLEMENTATION_REPORT.md)."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    body = (pack.get("script") or {}).get("body", [])
    if not body:
        raise HTTPException(400, "Chưa có script để xuất transcript")

    shots = pack.get("shots", [])
    shot_by_block_id = {s.get("block_id"): s for s in shots if s.get("block_id")}
    render_raw = read_json(pdir / "render.json")
    render_state = RenderState.model_validate(render_raw) if render_raw else RenderState(project_id=project_id)
    narration_by_shot_id = {s.shot_id: s for s in render_state.shots}
    intro_source = resolve_intro_source(render_state.intro, brand, shots, narration_by_shot_id)
    intro_offset = intro_duration_sec(intro_source)

    content = _build_srt(body, shot_by_block_id=shot_by_block_id, narration_by_shot_id=narration_by_shot_id, intro_offset=intro_offset)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-subrip",
        headers={"Content-Disposition": 'attachment; filename="transcript.srt"'},
    )


@router.get("/projects/{project_id}/script/import/template")
def download_script_import_template(project_id: str, db: Session = Depends(get_db)):
    """File Excel mẫu đúng 6 cột `script_import.py::parse_script_rows()` yêu cầu, kèm
    2 dòng ví dụ — người dùng tải về, điền theo, rồi dùng lại chính nút "Nhập kịch bản
    từ file" bên cạnh. Nội dung mẫu tĩnh (không phụ thuộc project) nhưng vẫn đặt path
    lồng theo project cho nhất quán với 2 endpoint import/parse, import/confirm."""
    _get_project_or_404(db, project_id)
    return Response(
        content=build_template_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="mau-nhap-kich-ban.xlsx"'},
    )


@router.post("/projects/{project_id}/script/import/parse")
async def import_script_parse(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bước 1 nhập kịch bản từ CSV/Excel (đã build vòng 4) — chỉ parse & trả preview
    (số block/số từ/thời lượng ước tính), CHƯA lưu vào Pack. Khớp dialog xác nhận
    trong design. Parse phía server — xem app/pipeline/script_import.py."""
    _get_project_or_404(db, project_id)
    content = await file.read()
    try:
        result = parse_script_file(content, file.filename or "")
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
    """Tạo/ĐỒNG BỘ shot list — IDEMPOTENT với shot đã có (không ghi đè/xoá), nhưng vẫn
    bổ sung shot MỚI cho block chưa có shot. Dùng chung cho `/visual/generate` (bấm
    "Đi tới Visual Studio") VÀ `/visual/ensure-shots-for-narration` (bấm "Sinh giọng
    đọc cho toàn bộ block" ở Script Studio, mục 30 IMPLEMENTATION_REPORT.md).

    **Bug thật phát hiện 2026-08-17 (mục 31)**: bản đầu tiên của hàm này ("tạo nếu rỗng,
    có gì thì trả nguyên") xử lý đúng trường hợp shots CHƯA TỪNG tạo, nhưng SAI khi
    người dùng SỬA/DUYỆT LẠI Full Script dài hơn (thêm block) sau khi shots đã tạo từ
    trước — `body` dài ra nhưng `pack.shots` (đã tồn tại) không bao giờ được mở rộng
    theo, "có gì thì trả nguyên" giữ mãi bộ shot CŨ NGẮN HƠN. Đo thật trên project người
    dùng: 31 block script nhưng chỉ 12 shot — 19 block cuối KHÔNG BAO GIỜ có shot, nên
    không thể sinh visual/narration cho chúng ở bất kỳ màn nào.

    **Fix — ĐỒNG BỘ theo `block_id`** (field ổn định, duy nhất — KHÔNG dùng
    `linked_timestamp_sec` vì giá trị này có thể lệch giữa các lần tạo/sửa): block nào
    CHƯA có shot khớp `block_id` → tạo mới bằng `_seed_shot_from_beat`, APPEND vào cuối;
    shot đã có GIỮ NGUYÊN (không đụng — bảo toàn liên kết visual/narration đã sinh cho
    các block cũ).

    **Đơn giản hoá 2026-08-17 (mục 44)**: trước đây còn 1 nhánh AI tự sinh shot
    (`gen.generate_shots`) cho script KHÔNG phải import (`source != "import"`) — nhánh
    đó đã XOÁ cùng lúc bỏ AI Research/Outline/Hook/Full-Script, vì `script.source` giờ
    LUÔN LÀ `"import"` (đường DUY NHẤT còn lại để có script). Hàm này giờ chỉ còn đúng 1
    đường xử lý, không branch theo `source` nữa."""
    existing = pack.get("shots") or []
    have_block_ids = {s.get("block_id") for s in existing if s.get("block_id")}
    missing = [(i, b) for i, b in enumerate(body) if b.get("block_id") not in have_block_ids]
    if not missing and existing:
        return existing
    new_shots = [_seed_shot_from_beat(b, i) for i, b in missing]
    return existing + new_shots if existing else new_shots


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
    """Sinh lại RIÊNG Visual/FX (đã build vòng 4 — tách khỏi Audio/SFX, khớp 2 nút
    "Tạo lại Visual" / "Tạo lại giọng đọc" riêng biệt trong design)."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    target, beat = _find_shot_and_beat(pack, shot_id)
    llm = get_llm(db, task_role="shots")
    usage: list[dict] = []
    target["visual_fx"] = gen.regenerate_shot_visual_fx(llm, db, brand, beat, visual_type=target.get("visual_type", "image"), usage=usage)
    write_json(pdir / "pack.json", pack)
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


@router.post("/projects/{project_id}/visual/shots/{shot_id}/regenerate-audio")
def regenerate_shot_audio(project_id: str, shot_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    target, beat = _find_shot_and_beat(pack, shot_id)
    llm = get_llm(db, task_role="shots")
    usage: list[dict] = []
    target["audio_sfx"] = gen.regenerate_shot_audio_sfx(llm, db, brand, beat, usage=usage)
    write_json(pdir / "pack.json", pack)
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


@router.post("/projects/{project_id}/visual/generate-all-visual")
def generate_all_visual(project_id: str, db: Session = Depends(get_db)):
    """Header Visual Studio — "Tạo Visual cho toàn bộ block" (đã build vòng 4)."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    shots = pack.get("shots", [])
    body = (pack.get("script") or {}).get("body", [])
    if not shots:
        raise HTTPException(400, "Chưa có shot nào — vào Visual Studio trước")
    llm = get_llm(db, task_role="shots")
    usage: list[dict] = []
    for s in shots:
        beat = next((b for b in body if b.get("timestamp_sec") == s.get("linked_timestamp_sec")), body[0] if body else {})
        s["visual_fx"] = gen.regenerate_shot_visual_fx(llm, db, brand, beat, visual_type=s.get("visual_type", "image"), usage=usage)
    write_json(pdir / "pack.json", pack)
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


@router.post("/projects/{project_id}/visual/generate-all-tts")
def generate_all_tts(project_id: str, db: Session = Depends(get_db)):
    """Header Visual Studio — "Tạo giọng đọc (TTS) cho toàn bộ block" (đã build vòng 4)."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    shots = pack.get("shots", [])
    body = (pack.get("script") or {}).get("body", [])
    if not shots:
        raise HTTPException(400, "Chưa có shot nào — vào Visual Studio trước")
    llm = get_llm(db, task_role="shots")
    usage: list[dict] = []
    for s in shots:
        beat = next((b for b in body if b.get("timestamp_sec") == s.get("linked_timestamp_sec")), body[0] if body else {})
        s["audio_sfx"] = gen.regenerate_shot_audio_sfx(llm, db, brand, beat, usage=usage)
    write_json(pdir / "pack.json", pack)
    record_usage(db, p.channel_id, p.title, usage)
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
