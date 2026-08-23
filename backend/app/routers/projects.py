import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import delete_project_dir, project_dir
from app.db import get_db
from app.filestore import read_json, write_json
from app.models import AuditLog, Channel, Project
from app.schemas import Brief, BriefSource, ProductionPack
from app.timeutil import vn_isoformat
from app.youtube import extract_video_id, fetch_transcript_text

router = APIRouter(tags=["projects"])


def _new_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


def _project_out(p: Project) -> dict:
    return {
        "id": p.id,
        "channel_id": p.channel_id,
        "title": p.title,
        "status": p.status,
        "step": p.step,
        "max_step_reached": p.max_step_reached,
        "pack_version": p.pack_version,
        "return_note": p.return_note,
        "archived": p.archived,
        "parent_project_id": p.parent_project_id,
        "format": p.format or "long",
        "created_at": vn_isoformat(p.created_at) if p.created_at else None,
        "updated_at": vn_isoformat(p.updated_at) if p.updated_at else None,
    }


class ProjectCreate(BaseModel):
    title: str = "Dự án mới chưa có tên"
    # Short-form (9:16) — mới (2026-08-21): truyền id của 1 project long-form CÙNG kênh
    # để tạo sub-project lồng dưới nó. `format` KHÔNG nhận trực tiếp từ client — server
    # tự suy theo có/không có field này (xem create_project bên dưới).
    parent_project_id: str | None = None


class ProjectPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    step: int | None = None
    return_note: str | None = None


@router.get("/channels/{channel_id}/projects")
def list_projects(channel_id: str, db: Session = Depends(get_db)):
    ps = db.query(Project).filter(Project.channel_id == channel_id, Project.archived == False).all()  # noqa: E712
    return [_project_out(p) for p in ps]


@router.post("/channels/{channel_id}/projects")
def create_project(channel_id: str, body: ProjectCreate, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")

    fmt = "long"
    if body.parent_project_id:
        parent = db.query(Project).filter(Project.id == body.parent_project_id).first()
        if not parent:
            raise HTTPException(404, "Không tìm thấy project cha")
        if parent.channel_id != channel_id:
            raise HTTPException(400, "Project cha phải cùng kênh")
        if (parent.format or "long") != "long":
            raise HTTPException(400, "Project cha phải là project long-form (không lồng short-form dưới short-form)")
        fmt = "short"

    pid = _new_id("prj")
    pdir = project_dir(channel_id, pid)

    brief = Brief(project_id=pid, channel_id=channel_id)
    write_json(pdir / "brief.json", brief.model_dump())

    pack = ProductionPack(project_id=pid, channel_id=channel_id, brandprofile_version=ch.brandprofile_version or 1, status="draft")
    write_json(pdir / "pack.json", pack.model_dump())
    write_json(pdir / "pack.v1.json", pack.model_dump())

    p = Project(id=pid, channel_id=channel_id, title=body.title, status="draft", step=0, max_step_reached=0,
                brief_path=str(pdir / "brief.json"), pack_path=str(pdir / "pack.json"), pack_version=1,
                parent_project_id=body.parent_project_id, format=fmt)
    db.add(p)
    db.commit()
    return _project_out(p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return _project_out(p)


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    if body.title is not None:
        p.title = body.title
    if body.step is not None:
        if body.step > p.max_step_reached:
            raise HTTPException(400, "Chưa đủ điều kiện đi tới bước này")
        p.step = body.step
    if body.status is not None:
        p.status = body.status
    if body.return_note is not None:
        p.return_note = body.return_note
    db.commit()
    return _project_out(p)


@router.delete("/projects/{project_id}")
def archive_project(project_id: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    p.archived = True
    db.add(AuditLog(action="Archive project", detail=p.title, entity=p.title))
    # Short-form (2026-08-21) — xoá 1 project long-form kéo theo archive LUÔN mọi
    # short-form con (tránh short-form mồ côi không rõ thuộc project nào trong danh sách
    # phẳng của Thùng rác) — chỉ áp dụng khi CHÍNH p là long-form (short-form không có
    # con để cascade tiếp).
    if (p.format or "long") == "long":
        children = db.query(Project).filter(Project.parent_project_id == project_id, Project.archived == False).all()  # noqa: E712
        for child in children:
            child.archived = True
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/restore")
def restore_project(project_id: str, db: Session = Depends(get_db)):
    """Khôi phục project khỏi Thùng rác — đối xứng với `DELETE /projects/{id}` (archive).

    Short-form (2026-08-21): khôi phục 1 project long-form kéo theo khôi phục LUÔN mọi
    short-form con đang archived — đối xứng với cascade archive ở trên. Không phân biệt
    short-form con bị archive CÙNG LÚC với cha hay archive riêng lẻ trước đó (đơn giản
    hoá — chấp nhận trade-off nhỏ: nếu người dùng archive riêng 1 short-form rồi SAU ĐÓ
    mới archive cha, restore cha sẽ khôi phục lại cả short-form đó luôn)."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    p.archived = False
    db.add(AuditLog(action="Khôi phục project", detail=p.title, entity=p.title))
    if (p.format or "long") == "long":
        children = db.query(Project).filter(Project.parent_project_id == project_id, Project.archived == True).all()  # noqa: E712
        for child in children:
            child.archived = False
    db.commit()
    return _project_out(p)


@router.delete("/projects/{project_id}/permanent")
def delete_project_permanent(project_id: str, db: Session = Depends(get_db)):
    """Xoá vĩnh viễn — CHỈ cho phép với project đã ở Thùng rác (archived=True). Xoá DB
    row (cascade PackVersion/RetentionEntry — xem Project.pack_versions/
    retention_entries, app/models/__init__.py) VÀ xoá thư mục project trên đĩa
    (`delete_project_dir`) — KHÔNG khôi phục được nữa.

    Short-form (2026-08-21): xoá vĩnh viễn 1 project long-form xoá LUÔN mọi short-form
    con TRƯỚC (đệ quy 1 cấp — short-form không có con), tránh short-form mồ côi trỏ
    `parent_project_id` tới 1 project đã không còn tồn tại."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    if not p.archived:
        raise HTTPException(400, "Chỉ xoá vĩnh viễn được project đã ở Thùng rác — xoá project trước.")

    if (p.format or "long") == "long":
        children = db.query(Project).filter(Project.parent_project_id == project_id).all()
        for child in children:
            child_title, child_channel_id, child_id = child.title, child.channel_id, child.id
            db.add(AuditLog(action="Xoá vĩnh viễn project", detail=child_title, entity=child_title))
            db.delete(child)
            db.commit()
            delete_project_dir(child_channel_id, child_id)

    title, channel_id = p.title, p.channel_id
    db.add(AuditLog(action="Xoá vĩnh viễn project", detail=title, entity=title))
    db.delete(p)
    db.commit()
    delete_project_dir(channel_id, project_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Brief
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = {
    "group1": ["topic", "insight"],
    "group2_audience": ["audience.description"],
    "group2_goal": ["strategy.growth_objective"],
}


def _missing_groups(brief: dict) -> list[str]:
    missing = []
    if not brief.get("topic") or not brief.get("insight"):
        missing.append("group1")
    if not brief.get("audience", {}).get("description") or not brief.get("strategy", {}).get("growth_objective"):
        missing.append("group2")
    return missing


@router.get("/projects/{project_id}/brief")
def get_brief(project_id: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    brief = read_json(project_dir(p.channel_id, project_id) / "brief.json") or {}
    return {"brief": brief, "missing_groups": _missing_groups(brief)}


@router.put("/projects/{project_id}/brief")
def put_brief(project_id: str, body: Brief, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    data = body.model_dump()
    write_json(project_dir(p.channel_id, project_id) / "brief.json", data)
    db.commit()
    return {"brief": data, "missing_groups": _missing_groups(data)}


@router.post("/projects/{project_id}/brief/sources")
async def add_brief_source(
    project_id: str,
    file: UploadFile | None = File(None),
    youtube_url: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Thêm nguồn tham khảo (file hoặc link YouTube).

    File: trích xuất text đơn giản (decode utf-8, đếm ký tự) cho file text-based.
    YouTube: trích xuất transcript THẬT qua youtube-transcript-api (app/youtube.py) —
    không cần API key, đọc trực tiếp caption công khai. Video không có transcript/tắt
    phụ đề → status='error' kèm lý do trong `error`, không chặn luồng (giữ nguyên
    nguyên tắc "trường thiếu không chặn cứng").
    """
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    pdir = project_dir(p.channel_id, project_id)
    sources_dir = pdir / "sources"
    sources_dir.mkdir(exist_ok=True)
    brief = read_json(pdir / "brief.json") or {}
    brief.setdefault("raw_knowledge", {}).setdefault("documents", [])

    if file is not None:
        content = await file.read()
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            text = ""
        source_id = _new_id("src")
        content_path = None
        if text.strip():
            content_path = f"{source_id}.txt"
            (sources_dir / content_path).write_text(text, encoding="utf-8")
        source = BriefSource(id=source_id, kind="file", label=file.filename or "tệp", status="done", char_count=len(text), content_path=content_path)
    elif youtube_url:
        source_id = _new_id("src")
        video_id = extract_video_id(youtube_url)
        if not video_id:
            source = BriefSource(id=source_id, kind="youtube", label=youtube_url, status="error", error="Không nhận diện được video ID từ link")
        else:
            try:
                text = fetch_transcript_text(video_id)
                content_path = f"{source_id}.txt"
                (sources_dir / content_path).write_text(text, encoding="utf-8")
                source = BriefSource(id=source_id, kind="youtube", label=youtube_url, status="done", char_count=len(text), content_path=content_path)
            except ValueError as e:
                source = BriefSource(id=source_id, kind="youtube", label=youtube_url, status="error", error=str(e))
    else:
        raise HTTPException(400, "Thiếu file hoặc youtube_url")

    brief["raw_knowledge"]["documents"].append(source.model_dump())
    write_json(pdir / "brief.json", brief)
    return brief


@router.delete("/projects/{project_id}/brief/sources/{source_id}")
def remove_brief_source(project_id: str, source_id: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    pdir = project_dir(p.channel_id, project_id)
    brief = read_json(pdir / "brief.json") or {}
    docs = brief.get("raw_knowledge", {}).get("documents", [])
    brief["raw_knowledge"]["documents"] = [d for d in docs if d.get("id") != source_id]
    write_json(pdir / "brief.json", brief)
    return brief
