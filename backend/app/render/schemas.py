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
    visual_started_at: Optional[str] = None  # ISO datetime — set lúc chuyển "generating", None khi xong. Frontend tự tính thời gian đã trôi (đồng hồ đếm) — UX cho video local chạy 7-18 phút, xem IMPLEMENTATION_REPORT.md.
    approved: bool = False  # human review bắt buộc trước khi ghép (specs/09 M2)

    narration_status: AssetStatus = "pending"
    narration_asset_path: Optional[str] = None
    narration_provider: Optional[str] = None
    narration_error: Optional[str] = None
    narration_duration_sec: Optional[float] = None  # đo thật qua ffprobe — dùng cho thời lượng video THỰC ở Pack Review
    narration_started_at: Optional[str] = None


class IntroAssetStatus(BaseModel):
    """Shot mở đầu RIÊNG của project — **mới (2026-08-20)**, theo yêu cầu người dùng.
    KHÔNG phải AI sinh (khác `ShotRenderStatus`) — người dùng tự upload trực tiếp, nên
    không cần các field `*_status`/`*_provider`/`*_started_at`. Khi đầy đủ (video, HOẶC
    ảnh+audio đi kèm), override HẲN video/audio thương hiệu ở cấp kênh (BrandProfile) —
    xem `app/render/assembly.py::_resolve_intro_source`."""
    kind: Literal["image", "video"] = "image"
    visual_asset_path: Optional[str] = None
    # CHỈ áp dụng/bắt buộc khi kind=="image" (video tự có audio riêng, không cần audio
    # rời) — xem app/routers/render.py::upload_intro_audio (400 nếu kind=="video").
    audio_asset_path: Optional[str] = None
    # Hiệu ứng chuyển cảnh GIỮA intro và shot đầu tiên của kịch bản — **mới (2026-08-21)**,
    # theo yêu cầu người dùng. Cùng bảng giá trị `app/render/transitions.py::TRANSITIONS`
    # dùng cho `transition_to_next` giữa 2 shot thường — "cut" (mặc định) đi đường ghép
    # CŨ (`_concat_intro_and_body`, filter concat không xfade); giá trị khác dùng
    # `_xfade_chain` (cùng cơ chế xfade/acrossfade đã có cho shot-to-shot) — xem
    # `app/render/assembly.py::assemble_video`.
    transition_to_next: str = "cut"
    # Người dùng CHỦ ĐỘNG bỏ hẳn shot mở đầu cho project này — **mới (2026-08-22)**,
    # theo yêu cầu người dùng: Visual Studio giờ HIỂN THỊ rõ video/audio thương hiệu cấp
    # kênh làm shot mở đầu MẶC ĐỊNH (kế thừa — hành vi fallback vốn đã có ở
    # `resolve_intro_source`, trước đây chỉ áp dụng NGẦM lúc ghép, không hiện gì ở UI).
    # `disabled=True` là cách DUY NHẤT tắt hẳn intro cho project này — kể cả khi kênh CÓ
    # cấu hình thương hiệu — phân biệt với trạng thái mặc định "project chưa có asset
    # riêng" (ngầm định kế thừa brand). Set field này CHỈ ghi vào `render.json` của TỪNG
    # project — KHÔNG BAO GIỜ đụng tới BrandProfile cấp kênh (xem app/routers/render.py::
    # delete_intro/enable_intro_inherit — 2 endpoint DUY NHẤT đổi field này).
    disabled: bool = False


class BgMusicOverride(BaseModel):
    """Nhạc nền RIÊNG của project — **mới (2026-08-20)**, theo yêu cầu người dùng: khi
    có `asset_path`, OVERRIDE HẲN nhạc nền mặc định cấp kênh (`BrandProfile.bg_music_
    path`) — xem `app/render/bg_music.py::resolve_bg_music_source`. `volume` (0.0=câm,
    1.0=to bằng giọng đọc chính) áp dụng cho CHÍNH override này, không dùng chung
    `bg_music_volume` cấp kênh (project có thể muốn mix khác channel)."""
    asset_path: Optional[str] = None
    volume: float = 0.3


class OverlayEffectOverride(BaseModel):
    """Hiệu ứng lớp phủ (overlay, VD mưa/tuyết rơi) RIÊNG của project — **mới
    (2026-08-22)**, theo yêu cầu người dùng: khi có `asset_path`, OVERRIDE HẲN overlay
    mặc định cấp kênh (`BrandProfile.overlay_effect_path`) — xem `app/render/overlay.py::
    resolve_overlay_source`. `opacity` (0.0=tắt hẳn, 1.0=full cường độ) áp dụng cho CHÍNH
    override này, không dùng chung `overlay_effect_opacity` cấp kênh (project có thể
    muốn cường độ khác channel) — cùng nguyên tắc `BgMusicOverride.volume` ở trên."""
    asset_path: Optional[str] = None
    opacity: float = 0.5


class AssemblyProgress(BaseModel):
    """Tiến trình ghép MP4 theo đơn vị TỰ NHIÊN sẵn có — mỗi shot 1 segment ffmpeg
    riêng, không cần parse `-progress` real-time của ffmpeg (phức tạp hơn nhiều, không
    cần thiết vì số segment đã đủ chi tiết để hiện % + ước lượng thời gian còn lại)."""
    stage: Literal["segments", "concat"] = "segments"
    current: int = 0
    total: int = 0


class RenderState(BaseModel):
    project_id: str
    shots: list[ShotRenderStatus] = Field(default_factory=list)
    intro: Optional[IntroAssetStatus] = None
    bg_music: Optional[BgMusicOverride] = None
    overlay: Optional[OverlayEffectOverride] = None
    assembly_status: AssemblyStatus = "not_started"
    assembly_error: Optional[str] = None
    assembly_progress: Optional[AssemblyProgress] = None
    assembly_started_at: Optional[str] = None
    final_video_path: Optional[str] = None
