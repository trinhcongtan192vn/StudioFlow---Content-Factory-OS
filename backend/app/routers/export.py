"""Output — Export (M1) — specs/03_api.md, specs/04 mục 4.

Quyết định triển khai: định dạng "pdf" ở M1 xuất ra văn bản thuần (.pdf chứa text,
không phải PDF render layout thật qua WeasyPrint/wkhtmltopdf) — việc dựng pipeline
render PDF đẹp là công sức ngoài phạm vi "chất lượng kịch bản/retention" ưu tiên số 1
của MVP (CLAUDE.md "không over-engineer"). Ghi rõ trong IMPLEMENTATION_REPORT.md.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json
from app.models import AuditLog, Project

router = APIRouter(tags=["export"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return p


def _render_markdown(pack: dict, project_title: str) -> str:
    lines = [f"# {project_title}", ""]
    script = pack.get("script") or {}
    hook = script.get("hook") or {}
    lines += ["## Hook", f"- **Spoken:** {hook.get('spoken', '')}", f"- **Visual:** {hook.get('visual', '')}", ""]
    lines += ["## Kịch bản đa cột", "", "| Timestamp | Audio | Visual | Direction |", "|---|---|---|---|"]
    for b in script.get("body", []):
        lines.append(f"| {b.get('timestamp_sec')}s | {b.get('audio', '')} | {b.get('visual', '')} | {b.get('direction', '')} |")
    cta = script.get("cta") or {}
    lines += ["", "## CTA", f"- {cta.get('spoken', '')} (→ {cta.get('conversion_point', 'none')})", ""]
    lines += ["## Shot List", ""]
    for s in pack.get("shots", []):
        lines.append(f"- **{s.get('shot_id')}** [{s.get('asset_type')}] — {s.get('prompt')} (TTS: {s.get('tts_emotion', '')})")
    lines += ["", "## Titles", ""]
    for t in pack.get("titles", []):
        lines.append(f"- {t.get('text')} ({t.get('angle', '')})")
    ym = pack.get("youtube_meta") or {}
    lines += ["", "## YouTube Description", "", ym.get("description", ""), ""]
    lines += ["## Thumbnail", ym.get("thumbnail_description", "")]
    return "\n".join(lines)


class ExportBody(BaseModel):
    format: str  # markdown | pdf | json


@router.post("/projects/{project_id}/export")
def export_pack(project_id: str, body: ExportBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    if p.status not in ("ready_output", "exported", "published"):
        raise HTTPException(400, "Yêu cầu project ở trạng thái ready_output (đã qua Gate #2)")
    pdir = project_dir(p.channel_id, project_id)
    pack = read_json(pdir / "pack.json") or {}
    exports_dir = pdir / "exports"
    exports_dir.mkdir(exist_ok=True)

    if body.format == "json":
        path = exports_dir / "production-pack.json"
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    elif body.format in ("markdown", "pdf"):
        md = _render_markdown(pack, p.title)
        ext = "md" if body.format == "markdown" else "pdf"
        path = exports_dir / f"production-pack.{ext}"
        path.write_text(md, encoding="utf-8")
    else:
        raise HTTPException(400, "format phải là markdown | pdf | json")

    p.status = "exported"
    db.add(AuditLog(action="Export Pack", detail=f"{p.title} ({body.format})", entity=p.title))
    db.commit()
    return {"path": f"/projects/{project_id}/exports/{path.name}", "filename": path.name}


@router.get("/projects/{project_id}/exports/{filename}")
def download_export(project_id: str, filename: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    path = project_dir(p.channel_id, project_id) / "exports" / filename
    if not path.exists():
        raise HTTPException(404, "Không tìm thấy file export")
    return FileResponse(path, filename=filename)
