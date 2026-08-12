from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json, write_json
from app.guardrail.check import annotate_body_with_warnings, run_guardrail_check
from app.models import Project, RetentionEntry
from app.routers.pipeline import record_usage

router = APIRouter(tags=["guardrail", "retention"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return p


@router.post("/projects/{project_id}/guardrail/check")
def guardrail_check(project_id: str, db: Session = Depends(get_db)):
    """Chạy lại thủ công sau khi sửa (§08 mục 5) — không đổi step/status."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, project_id)
    pack = read_json(pdir / "pack.json") or {}
    brand = read_json(pdir.parent.parent / "brandprofile.json") or {}
    brief = read_json(pdir / "brief.json") or {}
    body = (pack.get("script") or {}).get("body", [])
    if not body:
        raise HTTPException(400, "Chưa có body script để check")

    benchmark = brand.get("retention_benchmark", {})
    usage: list[dict] = []
    result = run_guardrail_check(
        db=db,
        hook_spoken=(pack.get("script") or {}).get("hook", {}).get("spoken", ""),
        body=body,
        benchmark=benchmark,
        forbidden=brand.get("forbidden", []),
        pain_points=brief.get("audience", {}).get("pain_points", []),
        usage=usage,
    )
    pack["script"]["body"] = annotate_body_with_warnings(body, result["warnings"])
    pack["retention_check"] = result
    write_json(pdir / "pack.json", pack)
    record_usage(db, p.channel_id, p.title, usage)
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Retention nạp thủ công (§08 mục 6, §03 "Retention nạp tay")
# ---------------------------------------------------------------------------
class RetentionBody(BaseModel):
    published_at: str | None = None
    ret_0: float | None = None
    ret_25: float | None = None
    ret_50: float | None = None
    ret_100: float | None = None
    avg_view_duration: float | None = None
    thumbnail_ctr: float | None = None


@router.get("/projects/{project_id}/retention")
def get_retention(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    entry = (
        db.query(RetentionEntry)
        .filter(RetentionEntry.project_id == project_id)
        .order_by(RetentionEntry.created_at.desc())
        .first()
    )
    pdir = project_dir(p.channel_id, project_id)
    brand = read_json(pdir.parent.parent / "brandprofile.json") or {}
    pack = read_json(pdir / "pack.json") or {}
    target_hook = brand.get("retention_benchmark", {}).get("target_hook_strength")
    hook_strength = (pack.get("retention_check") or {}).get("hook_strength")
    diff = None
    if entry and entry.ret_0 is not None and target_hook is not None:
        diff = round(entry.ret_0 / 100 - target_hook, 3)
    return {
        "entry": None
        if not entry
        else {
            "published_at": entry.published_at,
            "ret_0": entry.ret_0,
            "ret_25": entry.ret_25,
            "ret_50": entry.ret_50,
            "ret_100": entry.ret_100,
            "avg_view_duration": entry.avg_view_duration,
            "thumbnail_ctr": entry.thumbnail_ctr,
        },
        "target_hook_strength": target_hook,
        "guardrail_hook_strength": hook_strength,
        "diff_vs_benchmark": diff,
    }


@router.put("/projects/{project_id}/retention")
def put_retention(project_id: str, body: RetentionBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    entry = RetentionEntry(project_id=project_id, **body.model_dump())
    db.add(entry)
    p.status = "published"
    db.commit()
    return get_retention(project_id, db)
