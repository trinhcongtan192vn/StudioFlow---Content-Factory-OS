"""Render Studio API — M2 Production Layer (sinh asset thật + ghép MP4).
Module tách biệt script core (specs/09) — mọi endpoint ở đây chỉ ĐỌC pack.json qua
app/render/engine.py, không bao giờ ghi lại vào pack.json.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json
from app.models import Project
from app.render import engine
from app.render.assembly import assemble_video

router = APIRouter(tags=["render"])

READY_STATUSES = ("ready_output", "exported", "published")


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return p


def _find_shot_status(state, shot_id: str):
    return next((s for s in state.shots if s.shot_id == shot_id), None)


def _find_shot_and_beat(pack: dict, shot_id: str):
    shot = next((s for s in pack.get("shots", []) if s["shot_id"] == shot_id), None)
    if not shot:
        raise HTTPException(404, "Không tìm thấy shot")
    return shot, engine._find_beat(pack, shot)


@router.post("/projects/{project_id}/render/start")
def start_render(project_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    if p.status not in READY_STATUSES:
        raise HTTPException(400, "Project phải qua Gate #2 (đã duyệt Pack) trước khi sinh asset thật")
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    shots = pack.get("shots", [])
    if not shots:
        raise HTTPException(400, "Chưa có shot nào — hoàn tất Visual Studio trước")

    state = engine.load_render_state(pdir, project_id)
    engine._ensure_shot_entries(state, shots)
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.run_asset_generation, project_id)
    return state.model_dump()


@router.get("/projects/{project_id}/render/status")
def get_render_status(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    return engine.load_render_state(pdir, project_id).model_dump()


class ApproveBody(BaseModel):
    approved: bool = True


@router.post("/projects/{project_id}/render/shots/{shot_id}/approve")
def approve_shot(project_id: str, shot_id: str, body: ApproveBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này — bấm 'Bắt đầu sinh asset' trước")
    if status.visual_status != "ready":
        raise HTTPException(400, "Shot chưa sinh xong visual — chưa thể duyệt")
    status.approved = body.approved
    engine.save_render_state(pdir, state)
    return state.model_dump()


@router.post("/projects/{project_id}/render/shots/{shot_id}/regenerate-visual")
def regenerate_visual(project_id: str, shot_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    _find_shot_and_beat(pack, shot_id)  # 404 sớm nếu shot không tồn tại

    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này — bấm 'Bắt đầu sinh asset' trước")
    status.visual_status = "generating"  # reset trước — generate_visual_asset() bỏ qua nếu đang "ready"
    status.approved = False  # sinh lại → cần duyệt lại
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.regenerate_single_visual, project_id, shot_id)
    return state.model_dump()


@router.post("/projects/{project_id}/render/shots/{shot_id}/regenerate-narration")
def regenerate_narration(project_id: str, shot_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    _find_shot_and_beat(pack, shot_id)

    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này — bấm 'Bắt đầu sinh asset' trước")
    status.narration_status = "generating"
    engine.save_render_state(pdir, state)

    background_tasks.add_task(engine.regenerate_single_narration, project_id, shot_id)
    return state.model_dump()


@router.post("/projects/{project_id}/render/assemble")
def start_assemble(project_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if not state.shots:
        raise HTTPException(400, "Chưa sinh asset nào — bấm 'Bắt đầu sinh asset' trước")
    not_ready = [s.shot_id for s in state.shots if s.visual_status != "ready"]
    not_approved = [s.shot_id for s in state.shots if s.visual_status == "ready" and not s.approved]
    if not_ready:
        raise HTTPException(400, f"Còn {len(not_ready)} shot chưa sinh xong visual: {', '.join(not_ready)}")
    if not_approved:
        raise HTTPException(400, f"Còn {len(not_approved)} shot chưa được duyệt: {', '.join(not_approved)}")

    state.assembly_status = "assembling"
    state.assembly_error = None
    engine.save_render_state(pdir, state)
    background_tasks.add_task(assemble_video, project_id)
    return state.model_dump()


@router.get("/projects/{project_id}/render/shots/{shot_id}/asset/{kind}")
def get_shot_asset(project_id: str, shot_id: str, kind: str, db: Session = Depends(get_db)):
    """Phục vụ file nhị phân (ảnh/video/audio) đã sinh cho 1 shot — render.json chỉ
    lưu đường dẫn filesystem, frontend cần URL HTTP để hiển thị <img>/<video>/<audio>."""
    if kind not in ("visual", "narration"):
        raise HTTPException(400, "kind phải là visual hoặc narration")
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    status = _find_shot_status(state, shot_id)
    if not status:
        raise HTTPException(404, "Không tìm thấy trạng thái render cho shot này")
    path = status.visual_asset_path if kind == "visual" else status.narration_asset_path
    if not path:
        raise HTTPException(404, "Chưa sinh asset này")
    return FileResponse(path)


@router.get("/projects/{project_id}/render/download")
def download_render(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, p.id)
    state = engine.load_render_state(pdir, project_id)
    if state.assembly_status != "done" or not state.final_video_path:
        raise HTTPException(400, "Chưa ghép xong video")
    return FileResponse(state.final_video_path, filename="final.mp4", media_type="video/mp4")
