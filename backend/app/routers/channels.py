import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import channel_dir
from app.db import get_db
from app.filestore import read_json, write_versioned
from app.models import AuditLog, BrandProfileVersion, Channel, Project
from app.schemas import BrandProfile

router = APIRouter(tags=["channels"])


def _new_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


class ChannelCreate(BaseModel):
    name: str
    niche: str = ""


class ChannelPatch(BaseModel):
    name: str | None = None
    niche: str | None = None
    archived: bool | None = None


def _channel_out(db: Session, ch: Channel) -> dict:
    running = db.query(Project).filter(Project.channel_id == ch.id, Project.archived == False, Project.status.notin_(["exported", "published"])).count()  # noqa: E712
    review = db.query(Project).filter(Project.channel_id == ch.id, Project.status.in_(["await_gate1", "await_gate2"])).count()
    return {
        "id": ch.id,
        "name": ch.name,
        "niche": ch.niche,
        "letter": (ch.name[:1] or "?").upper(),
        "archived": ch.archived,
        "brandprofile_version": ch.brandprofile_version,
        "running_count": running,
        "review_count": review,
    }


@router.get("/channels")
def list_channels(db: Session = Depends(get_db)):
    chs = db.query(Channel).filter(Channel.archived == False).all()  # noqa: E712
    return [_channel_out(db, c) for c in chs]


@router.post("/channels")
def create_channel(body: ChannelCreate, db: Session = Depends(get_db)):
    cid = _new_id("ch")
    ch = Channel(id=cid, name=body.name, niche=body.niche, brandprofile_version=1)
    db.add(ch)
    db.flush()

    profile = BrandProfile(channel_id=cid, niche=body.niche)
    cdir = channel_dir(cid)
    current, versioned = write_versioned(cdir, "brandprofile", profile.model_dump(), 1)
    ch.brandprofile_path = str(current)
    db.add(BrandProfileVersion(channel_id=cid, version=1, file_path=str(versioned), note="Khởi tạo"))
    db.add(AuditLog(action="Tạo kênh", detail=body.name, entity=body.name))
    db.commit()
    return _channel_out(db, ch)


@router.get("/channels/{channel_id}")
def get_channel(channel_id: str, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    out = _channel_out(db, ch)
    out["brand_profile"] = profile
    return out


@router.patch("/channels/{channel_id}")
def patch_channel(channel_id: str, body: ChannelPatch, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    if body.name is not None:
        ch.name = body.name
    if body.niche is not None:
        ch.niche = body.niche
    if body.archived is not None:
        ch.archived = body.archived
        db.add(AuditLog(action="Xóa kênh" if body.archived else "Khôi phục kênh", detail=ch.name, entity=ch.name))
    db.commit()
    return _channel_out(db, ch)


@router.get("/channels/{channel_id}/brandprofile")
def get_brandprofile(channel_id: str, db: Session = Depends(get_db)):
    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    if profile is None:
        raise HTTPException(404, "Chưa có BrandProfile")
    return profile


@router.put("/channels/{channel_id}/brandprofile")
def put_brandprofile(channel_id: str, body: BrandProfile, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    next_version = (ch.brandprofile_version or 0) + 1
    body.version = next_version
    cdir = channel_dir(channel_id)
    current, versioned = write_versioned(cdir, "brandprofile", body.model_dump(), next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note="Cập nhật BrandProfile"))
    db.add(AuditLog(action="Sửa BrandProfile", detail=ch.name, entity=ch.name))
    db.commit()
    return body.model_dump()


@router.get("/channels/{channel_id}/brandprofile/versions")
def brandprofile_versions(channel_id: str, db: Session = Depends(get_db)):
    versions = (
        db.query(BrandProfileVersion)
        .filter(BrandProfileVersion.channel_id == channel_id)
        .order_by(BrandProfileVersion.version.desc())
        .all()
    )
    return [{"version": v.version, "created_at": v.created_at.isoformat(), "note": v.note} for v in versions]


@router.post("/channels/{channel_id}/brandprofile/clone-from/{src_channel_id}")
def clone_brandprofile(channel_id: str, src_channel_id: str, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    src_profile = read_json(channel_dir(src_channel_id) / "brandprofile.json")
    if src_profile is None:
        raise HTTPException(404, "Không tìm thấy BrandProfile nguồn")
    src_profile["channel_id"] = channel_id
    next_version = (ch.brandprofile_version or 0) + 1
    src_profile["version"] = next_version
    cdir = channel_dir(channel_id)
    current, versioned = write_versioned(cdir, "brandprofile", src_profile, next_version)
    ch.brandprofile_path = str(current)
    ch.brandprofile_version = next_version
    db.add(BrandProfileVersion(channel_id=channel_id, version=next_version, file_path=str(versioned), note=f"Clone từ {src_channel_id}"))
    db.commit()
    return src_profile
