"""Xác định nguồn nhạc nền (background music) — video/audio thương hiệu cấp kênh HOẶC
override riêng của project (mới, 2026-08-20, theo yêu cầu người dùng) — TÁCH RIÊNG khỏi
`assembly.py`, KHÔNG phụ thuộc `engine.py` (cùng lý do `intro.py`/`transitions.py`/
`camera_motion.py` — tránh vòng import `engine.py` → `routers/pipeline.py`).
"""
from __future__ import annotations

from app.render.schemas import BgMusicOverride


def resolve_bg_music_source(project_bg: BgMusicOverride | None, brand: dict) -> tuple[str, float] | None:
    """Ưu tiên nhạc nền RIÊNG của project (override, nếu có `asset_path`) hơn nhạc nền
    mặc định cấp kênh — trả `(asset_path, volume)` hoặc `None` nếu không có nguồn nào."""
    if project_bg and project_bg.asset_path:
        return (project_bg.asset_path, project_bg.volume)
    if brand.get("bg_music_path"):
        return (brand["bg_music_path"], brand.get("bg_music_volume", 0.3))
    return None
