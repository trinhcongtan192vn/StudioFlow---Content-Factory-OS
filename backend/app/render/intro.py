"""Xác định + đo thời lượng intro (video/audio thương hiệu cấp kênh HOẶC shot mở đầu
riêng của project, mục 51 IMPLEMENTATION_REPORT.md) — TÁCH RIÊNG khỏi `assembly.py`,
KHÔNG phụ thuộc `engine.py` (giống `transitions.py`/`camera_motion.py`, tránh vòng
import `engine.py` → `routers/pipeline.py`).

Lý do tách: CẢ `assembly.py::assemble_video` (ghép MP4 thật) LẪN
`routers/pipeline.py::download_transcript_srt` (xuất transcript .srt) đều cần biết
"video có intro không, dài bao nhiêu" để 2 nơi KHỚP NHAU — transcript phải cùng offset
với video thật ghép ra, không phải suy đoán riêng — dùng CHUNG 1 hàm thay vì lặp logic
2 nơi dễ lệch (2026-08-20, theo yêu cầu người dùng).
"""
from __future__ import annotations

from app.render.media_probe import probe_duration_sec
from app.render.schemas import IntroAssetStatus, ShotRenderStatus


def intro_is_usable(intro: IntroAssetStatus | None) -> bool:
    """Shot mở đầu (project-level, override) chỉ "đủ" khi: video có visual_asset_path,
    HOẶC ảnh có CẢ visual_asset_path lẫn audio_asset_path (audio bắt buộc với ảnh —
    yêu cầu người dùng, 2026-08-20)."""
    if not intro or not intro.visual_asset_path:
        return False
    return intro.kind == "video" or bool(intro.audio_asset_path)


def resolve_intro_source(
    intro: IntroAssetStatus | None, brand: dict, shots: list[dict], by_id: dict[str, ShotRenderStatus],
) -> tuple[str, str, str | None] | None:
    """Quyết định nguồn intro (nếu có) theo đúng thứ tự ưu tiên người dùng yêu cầu
    (2026-08-20, cập nhật 2026-08-22 thêm bước (0)): **(0) `intro.disabled == True`** —
    người dùng CHỦ ĐỘNG bỏ hẳn shot mở đầu cho project này ở Visual Studio, KHÔNG dùng
    intro nào cả, kể cả brand có cấu hình (xem `IntroAssetStatus.disabled`) — (1) shot mở
    đầu RIÊNG của project (override, xem `intro_is_usable`) — (1b) project CHỈ có audio
    (không ảnh/video) — minh hoạ bằng ẢNH shot đầu tiên, VẪN ưu tiên hơn thương hiệu cấp
    kênh vì đây vẫn là lựa chọn RIÊNG của project — (2) video thương hiệu cấp kênh — (3)
    audio thương hiệu cấp kênh, minh hoạ bằng ẢNH của shot ĐẦU TIÊN trong project (chỉ
    dùng được nếu shot đó đã sinh xong visual). Trước đây bước (2)/(3) là fallback NGẦM
    khi project chưa cấu hình gì — giờ Visual Studio HIỂN THỊ rõ đây là trạng thái "kế
    thừa từ hồ sơ thương hiệu" thay vì im lặng, xem `frontend/src/screens/steps/
    VisualStudio.tsx::IntroShotCard`.
    Trả `(kind, visual_path, audio_path)` hoặc `None` nếu không có nguồn nào khả dụng."""
    if intro and intro.disabled:
        return None
    if intro_is_usable(intro):
        return (intro.kind, intro.visual_asset_path, intro.audio_asset_path)  # type: ignore[union-attr]
    if intro and intro.audio_asset_path and not intro.visual_asset_path and shots:
        first_status = by_id.get(shots[0]["shot_id"])
        if first_status and first_status.visual_asset_path:
            return ("image", first_status.visual_asset_path, intro.audio_asset_path)
    if brand.get("intro_video_path"):
        return ("video", brand["intro_video_path"], None)
    if brand.get("intro_audio_path") and shots:
        first_status = by_id.get(shots[0]["shot_id"])
        if first_status and first_status.visual_asset_path:
            return ("image", first_status.visual_asset_path, brand["intro_audio_path"])
    return None


def intro_duration_sec(resolved: tuple[str, str, str | None] | None) -> float:
    """Thời lượng THẬT (giây, đo qua ffprobe) của nguồn intro đã `resolve_intro_source`
    trả về — `0.0` nếu không có intro hoặc không đo được. `kind=="video"` đo chính file
    video (audio đi kèm sẵn trong đó, không tách riêng); `kind=="image"` đo audio đi
    kèm (ảnh không có "thời lượng" riêng, phát theo đúng độ dài audio)."""
    if not resolved:
        return 0.0
    kind, visual_path, audio_path = resolved
    path = visual_path if kind == "video" else audio_path
    if not path:
        return 0.0
    return probe_duration_sec(path) or 0.0
