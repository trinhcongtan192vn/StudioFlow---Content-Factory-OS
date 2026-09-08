"""Xác định nguồn hiệu ứng lớp phủ (overlay effect — VD mưa rơi, tuyết rơi) — video/audio
thương hiệu cấp kênh HOẶC override riêng của project — **mới (2026-08-22)**, theo yêu cầu
người dùng. TÁCH RIÊNG khỏi `assembly.py`, KHÔNG phụ thuộc `engine.py` (cùng lý do
`bg_music.py`/`intro.py`/`transitions.py`/`camera_motion.py` — tránh vòng import
`engine.py` → `routers/pipeline.py`).

Cấu trúc CHÍNH XÁC như `bg_music.py` (2 cấp kênh/project, project ưu tiên hơn) — overlay
phủ LIÊN TỤC suốt toàn bộ video (kể cả intro), giống cách nhạc nền hoạt động, KHÁC
`intro.py` (chỉ áp dụng cho đoạn mở đầu) — xem `app/render/assembly.py::_mix_overlay_effect`.
"""
from __future__ import annotations

from app.render.schemas import OverlayEffectOverride


def resolve_overlay_source(project_overlay: OverlayEffectOverride | None, brand: dict) -> tuple[str, float] | None:
    """Ưu tiên overlay RIÊNG của project (override, nếu có `asset_path`) hơn overlay mặc
    định cấp kênh — trả `(asset_path, opacity)` hoặc `None` nếu không có nguồn nào.

    `project_overlay.disabled == True` (mới 2026-09-02) — người dùng CHỦ ĐỘNG tắt hẳn
    overlay cho project này, KHÔNG dùng overlay nào cả kể cả brand có cấu hình — cùng
    nguyên tắc bước (0) của `intro.py::resolve_intro_source`."""
    if project_overlay and project_overlay.disabled:
        return None
    if project_overlay and project_overlay.asset_path:
        return (project_overlay.asset_path, project_overlay.opacity)
    if brand.get("overlay_effect_path"):
        return (brand["overlay_effect_path"], brand.get("overlay_effect_opacity", 0.5))
    return None
