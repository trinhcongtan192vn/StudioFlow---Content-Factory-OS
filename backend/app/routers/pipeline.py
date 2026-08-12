"""Pipeline AI (lõi) — specs/03_api.md mục Pipeline + specs/07 prompt templates.

Lệch so với 03_api.md gốc (chi tiết trong IMPLEMENTATION_REPORT.md):
- `/research` sinh CẢ outline lẫn hook trong 1 lệnh gọi (thay vì 2 endpoint tách rời
  /research và /hooks) — khớp UX design: nhấn "Bắt đầu Research" xong thấy cả outline
  lẫn Hook Variants cùng lúc ở Gate 1. Endpoint `/hooks` vẫn giữ để sinh lại hook riêng
  nếu cần (không bắt buộc theo luồng chính).
- `/generate` tách thành 3 bước nhỏ hơn khớp 2 màn hình mới trong design (Script Studio
  tách biệt "viết Full Script" và "bóc tách theo đoạn"; Visual Studio sinh shot):
  `/script/full`, `/script/regenerate`, `/script/approve`, `/visual/generate`,
  `/visual/shots/{id}` (sửa tay), `/visual/shots/{id}/regenerate`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json, write_json, write_versioned
from app.guardrail.check import annotate_body_with_warnings, run_guardrail_check
from app.models import AppSetting, AuditLog, Budget, Channel, Project
from app.pipeline import generation as gen
from app.pipeline.script_import import ScriptImportError, parse_script_file
from app.providers.factory import get_llm
import json

router = APIRouter(tags=["pipeline"])


def _load_source_texts(pdir, brief: dict, max_chars: int = 8000) -> str:
    """Ghép nội dung đã trích xuất từ các nguồn tham khảo (file/YouTube transcript,
    xem routers/projects.py + app/youtube.py) để đưa vào prompt AI Research."""
    docs = brief.get("raw_knowledge", {}).get("documents", [])
    parts = []
    for d in docs:
        cp = d.get("content_path")
        if not cp:
            continue
        f = pdir / "sources" / cp
        if f.exists():
            parts.append(f"[{d.get('label', '')}]\n{f.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)[:max_chars]


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


def _ai_params(db: Session) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == "ai_params").first()
    if row:
        return json.loads(row.value)
    return {"temperature": 0.7, "length": "3-6 phút", "hook_count": 3, "framework": "AIDA"}


# ---------------------------------------------------------------------------
@router.post("/projects/{project_id}/research")
def run_research(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    llm = get_llm(db, task_role="research")
    usage: list[dict] = []

    source_text = _load_source_texts(pdir, brief)
    brief_for_prompt = {**brief, "source_texts": source_text} if source_text else brief

    research = gen.generate_research(llm, db, brand, brief_for_prompt, usage=usage)
    hooks = gen.generate_hooks(llm, db, brand, brief_for_prompt, research["outlines"][0] if research["outlines"] else {}, usage=usage)

    pack["research"] = research
    pack["hooks"] = hooks
    pack["status"] = "await_gate1"
    _save_pack(db, p, pack, status_at_save="await_gate1")

    p.step = 1
    p.max_step_reached = max(p.max_step_reached, 1)
    p.status = "await_gate1"
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


class Gate1Body(BaseModel):
    chosen_outline_id: str
    chosen_hook_id: str
    edited_hook_text: str | None = None


@router.post("/projects/{project_id}/gate1")
def approve_gate1(project_id: str, body: Gate1Body, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)

    outlines = pack.get("research", {}).get("outlines", [])
    for o in outlines:
        o["selected"] = o["id"] == body.chosen_outline_id
    chosen_outline = next((o for o in outlines if o["id"] == body.chosen_outline_id), None)
    if not chosen_outline:
        raise HTTPException(400, "chosen_outline_id không hợp lệ")

    hooks = pack.get("hooks", [])
    for h in hooks:
        h["selected"] = h["id"] == body.chosen_hook_id
    chosen_hook = next((h for h in hooks if h["id"] == body.chosen_hook_id), None)
    if not chosen_hook:
        raise HTTPException(400, "chosen_hook_id không hợp lệ")
    if body.edited_hook_text:
        chosen_hook["spoken"] = body.edited_hook_text

    params = _ai_params(db)
    llm = get_llm(db, task_role="script")
    usage: list[dict] = []
    full_text = gen.generate_full_script(llm, db, brand, brief, chosen_outline, chosen_hook, params.get("framework", "AIDA"), params.get("length", "3-6 phút"), usage=usage)

    pack["script"] = {
        "hook": {"spoken": chosen_hook["spoken"], "visual": chosen_hook.get("visual", ""), "duration_sec": 4},
        "body": [],
        "cta": {"spoken": "", "conversion_point": brief.get("strategy", {}).get("conversion_point", "none")},
        "full_text": full_text,
    }
    pack["status"] = "generating"
    _save_pack(db, p, pack, status_at_save="generating")

    p.step = 2
    p.max_step_reached = max(p.max_step_reached, 2)
    p.status = "generating"
    p.return_note = ""
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


class ScriptFeedbackBody(BaseModel):
    feedback: str


@router.post("/projects/{project_id}/script/regenerate")
def regenerate_script(project_id: str, body: ScriptFeedbackBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    if not pack.get("script"):
        raise HTTPException(400, "Chưa có script để tạo lại")
    llm = get_llm(db, task_role="script")
    params = _ai_params(db)
    usage: list[dict] = []
    new_text = gen.regenerate_full_script(llm, db, brand, pack["script"]["full_text"], body.feedback, params.get("length", "3-6 phút"), usage=usage)
    pack["script"]["full_text"] = new_text
    pack["script"]["body"] = []
    _save_pack(db, p, pack)
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


class ScriptTextBody(BaseModel):
    full_text: str


@router.patch("/projects/{project_id}/script/text")
def edit_script_text(project_id: str, body: ScriptTextBody, db: Session = Depends(get_db)):
    """Auto-save khi người dùng sửa tay Full Script (§06 mục 5 auto-save im lặng)."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    if not pack.get("script"):
        raise HTTPException(400, "Chưa có script")
    pack["script"]["full_text"] = body.full_text
    write_json(pdir / "pack.json", pack)
    return pack


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
    BỎ QUA bước AI Generation Full Script, nhảy thẳng tới Script Studio ở trạng thái
    đã duyệt. Khớp design: import thay thế cả luồng chọn outline/hook lẫn AI viết Full
    Script — không yêu cầu đã qua Gate 1 trước đó."""
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
        hook_spoken="",  # import không có Hook được chọn qua Gate 1 — không chấm Hook Strength, không cần Provider AI
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

    p.step = 2
    p.max_step_reached = max(p.max_step_reached, 2)
    p.status = "generating"
    p.return_note = ""
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


@router.post("/projects/{project_id}/script/approve")
def approve_script(project_id: str, db: Session = Depends(get_db)):
    """Bóc tách Full Script theo đoạn (timestamp/audio/visual/direction) + chạy guardrail inline."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    script = pack.get("script")
    if not script:
        raise HTTPException(400, "Chưa có script")
    llm = get_llm(db, task_role="script")
    benchmark = brand.get("retention_benchmark", {})
    usage: list[dict] = []
    body_items = gen.breakdown_script(llm, db, script["full_text"], benchmark.get("max_anchor_gap_sec", 45), usage=usage)

    result = run_guardrail_check(
        db=db,
        hook_spoken=script.get("hook", {}).get("spoken", ""),
        body=body_items,
        benchmark=benchmark,
        forbidden=brand.get("forbidden", []),
        pain_points=brief.get("audience", {}).get("pain_points", []),
        usage=usage,
    )
    body_items = annotate_body_with_warnings(body_items, result["warnings"])

    pack["script"]["body"] = body_items
    pack["retention_check"] = result
    _save_pack(db, p, pack)
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


@router.post("/projects/{project_id}/visual/generate")
def generate_visual_shots(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    script = pack.get("script") or {}
    body = script.get("body", [])
    if not body:
        raise HTTPException(400, "Chưa có body script để sinh shot")

    usage: list[dict] = []
    if script.get("source") == "import":
        shots = [_seed_shot_from_beat(b, i) for i, b in enumerate(body)]
    else:
        llm = get_llm(db, task_role="shots")
        shots = gen.generate_shots(llm, db, brand, body, usage=usage)
    pack["shots"] = shots
    _save_pack(db, p, pack)
    p.step = 3
    p.max_step_reached = max(p.max_step_reached, 3)
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


class ShotPatchBody(BaseModel):
    visual_fx: str | None = None
    audio_sfx: str | None = None
    visual_type: str | None = None


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


@router.post("/projects/{project_id}/pack/build")
def build_pack(project_id: str, db: Session = Depends(get_db)):
    """(Re)build title/thumbnail concepts từ script + chạy guardrail check tổng hợp (§03)."""
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)
    body = (pack.get("script") or {}).get("body", [])
    if not body:
        raise HTTPException(400, "Chưa có script để build Pack")
    llm = get_llm(db, task_role="titles")
    usage: list[dict] = []
    meta = gen.generate_titles_and_meta(llm, db, brand, brief, body, usage=usage)
    pack["titles"] = meta["titles"]
    pack["youtube_meta"] = meta["youtube_meta"]
    if not pack.get("thumbnail_concepts"):
        pack["thumbnail_concepts"] = [{"prompt": meta["youtube_meta"]["thumbnail_description"]}]

    benchmark = brand.get("retention_benchmark", {})
    result = run_guardrail_check(
        db=db,
        hook_spoken=(pack.get("script") or {}).get("hook", {}).get("spoken", ""),
        body=body,
        benchmark=benchmark,
        forbidden=brand.get("forbidden", []),
        pain_points=brief.get("audience", {}).get("pain_points", []),
        usage=usage,
    )
    pack["retention_check"] = result
    pack["status"] = "await_gate2"
    _save_pack(db, p, pack, status_at_save="await_gate2")

    p.step = 4
    p.max_step_reached = max(p.max_step_reached, 4)
    p.status = "await_gate2"
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return pack


class Gate2Body(BaseModel):
    action: str  # approve | return
    note: str = ""


@router.post("/projects/{project_id}/gate2")
def gate2(project_id: str, body: Gate2Body, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir, brand, brief, pack = _load(db, p)

    if body.action == "approve":
        pack["status"] = "approved"
        _save_pack(db, p, pack, status_at_save="approved")
        p.status = "ready_output"
        p.step = 5
        p.max_step_reached = max(p.max_step_reached, 5)
        db.add(AuditLog(action="Duyệt Gate 2", detail=p.title, entity=p.title))
    elif body.action == "return":
        if not body.note.strip():
            raise HTTPException(400, "Cần ghi chú lý do trả về")
        pack["status"] = "generating"
        _save_pack(db, p, pack, status_at_save="generating", bump_version=True)
        p.status = "generating"
        p.step = 2  # quay lại Script Studio — xem IMPLEMENTATION_REPORT.md
        p.return_note = body.note
        db.add(AuditLog(action="Trả về Pack", detail=f"{p.title} — {body.note}", entity=p.title))
    else:
        raise HTTPException(400, "action phải là approve hoặc return")

    db.commit()
    return {"project": {"step": p.step, "status": p.status, "return_note": p.return_note}, "pack": pack}


@router.post("/projects/{project_id}/output/enter")
def enter_output(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    p.step = 5
    db.commit()
    return {"step": p.step}
