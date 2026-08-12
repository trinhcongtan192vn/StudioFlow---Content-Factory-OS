"""Schema trạng thái render (M2 — Production Layer) — cố ý TÁCH khỏi
app/schemas/__init__.py::ProductionPack (specs/09 mục "Ràng buộc xuyên suốt": "Chống
coupling: script core ⟂ render module"). Module render CHỈ ĐỌC pack.json (script/shots
đã duyệt), không bao giờ ghi field mới vào đó — mọi trạng thái sinh asset/ghép video
sống trong file riêng `render.json` (xem app/config.py::project_dir, app/render/engine.py).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

AssetStatus = Literal["pending", "generating", "ready", "error"]
AssemblyStatus = Literal["not_started", "assembling", "done", "error"]


class ShotRenderStatus(BaseModel):
    shot_id: str
    visual_status: AssetStatus = "pending"
    visual_asset_path: Optional[str] = None
    visual_provider: Optional[str] = None
    visual_error: Optional[str] = None
    approved: bool = False  # human review bắt buộc trước khi ghép (specs/09 M2)

    narration_status: AssetStatus = "pending"
    narration_asset_path: Optional[str] = None
    narration_provider: Optional[str] = None
    narration_error: Optional[str] = None
    narration_duration_sec: Optional[float] = None  # đo thật qua ffprobe — dùng cho thời lượng video THỰC ở Pack Review


class RenderState(BaseModel):
    project_id: str
    shots: list[ShotRenderStatus] = Field(default_factory=list)
    assembly_status: AssemblyStatus = "not_started"
    assembly_error: Optional[str] = None
    final_video_path: Optional[str] = None
