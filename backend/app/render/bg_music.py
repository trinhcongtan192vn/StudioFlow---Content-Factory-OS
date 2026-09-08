"""Xác định nguồn nhạc nền (background music) — video/audio thương hiệu cấp kênh HOẶC
override riêng của project (mới, 2026-08-20, theo yêu cầu người dùng) — TÁCH RIÊNG khỏi
`assembly.py`, KHÔNG phụ thuộc `engine.py` (cùng lý do `intro.py`/`transitions.py`/
`camera_motion.py` — tránh vòng import `engine.py` → `routers/pipeline.py`).
"""
from __future__ import annotations

from app.render.schemas import BgMusicOverride


def resolve_bg_music_source(project_bg: BgMusicOverride | None, brand: dict) -> tuple[str, float] | None:
    """Ưu tiên nhạc nền RIÊNG của project (override, nếu có `asset_path`) hơn nhạc nền
    mặc định cấp kênh — trả `(asset_path, volume)` hoặc `None` nếu không có nguồn nào.

    **Đổi (2026-08-23, theo yêu cầu người dùng "Block phần nhạc nền cũng cần bổ sung
    thêm cấu hình âm lượng ở Visual Studio tương tự như ở brand profile")**: TÁCH RIÊNG
    `asset_path` và `volume` thay vì coi `BgMusicOverride` là all-or-nothing — người dùng
    muốn CHỈNH RIÊNG âm lượng cho 1 project trong khi vẫn DÙNG file nhạc nền mặc định
    của kênh (VD video có nhiều thoại hơn, cần nhạc nhỏ hơn, nhưng không muốn đổi hẳn
    bài nhạc). TRƯỚC ĐÂY: override CHƯA có `asset_path` (mới chỉnh volume, chưa upload)
    bị bỏ qua HOÀN TOÀN, kể cả phần volume đã chỉnh — PATCH volume trong lúc đang kế
    thừa nhạc nền brand hoàn toàn vô tác dụng lúc ghép MP4. GIỜ: `asset_path` vẫn ưu
    tiên project > brand (fallback riêng biệt), nhưng `volume` ưu tiên project (nếu
    object override TỒN TẠI, bất kể có `asset_path` hay chưa) > brand — cho phép
    "dùng nhạc brand, chỉnh âm lượng riêng" mà không cần upload lại file."""
    asset_path = (project_bg.asset_path if project_bg else None) or brand.get("bg_music_path")
    if not asset_path:
        return None
    volume = project_bg.volume if project_bg is not None else brand.get("bg_music_volume", 0.3)
    return (asset_path, volume)
