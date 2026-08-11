from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json, write_json, write_versioned
from app.models import PackVersion, Project

router = APIRouter(tags=["pack"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return p


@router.get("/projects/{project_id}/pack")
def get_pack(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pack = read_json(project_dir(p.channel_id, project_id) / "pack.json")
    if pack is None:
        raise HTTPException(404, "Chưa có Pack")
    return pack


@router.patch("/projects/{project_id}/pack")
def patch_pack(project_id: str, patch: dict, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, project_id)
    pack = read_json(pdir / "pack.json") or {}
    pack.update(patch)
    version = (p.pack_version or 1) + 1
    pack["version"] = version
    write_versioned(pdir, "pack", pack, version)
    p.pack_version = version
    db.add(PackVersion(project_id=project_id, version=version, file_path=str(pdir / f"pack.v{version}.json"), status_at_save=pack.get("status", "")))
    db.commit()
    return pack


@router.get("/projects/{project_id}/pack/versions")
def pack_versions(project_id: str, db: Session = Depends(get_db)):
    versions = db.query(PackVersion).filter(PackVersion.project_id == project_id).order_by(PackVersion.version.desc()).all()
    return [{"version": v.version, "status_at_save": v.status_at_save, "created_at": v.created_at.isoformat()} for v in versions]
