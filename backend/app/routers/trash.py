"""Thùng rác — liệt kê kênh/project đã "xoá" (archived=True) để khôi phục hoặc xoá vĩnh
viễn. Chỉ đọc, không có logic riêng — restore/xoá vĩnh viễn nằm ở channels.py/projects.py
(đúng resource sở hữu), module này chỉ gộp 2 danh sách cho 1 màn hình Thùng rác duy nhất.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Channel, Project
from app.routers.channels import _channel_out
from app.routers.projects import _project_out

router = APIRouter(tags=["trash"])


@router.get("/trash")
def get_trash(db: Session = Depends(get_db)):
    channels = db.query(Channel).filter(Channel.archived == True).all()  # noqa: E712
    projects = db.query(Project).filter(Project.archived == True).all()  # noqa: E712
    channel_names = {c.id: c.name for c in db.query(Channel).all()}
    return {
        "channels": [_channel_out(db, c) for c in channels],
        "projects": [{**_project_out(p), "channel_name": channel_names.get(p.channel_id, p.channel_id)} for p in projects],
    }
