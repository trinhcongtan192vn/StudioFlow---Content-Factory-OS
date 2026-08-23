"""Danh sách transition hợp lệ giữa 2 shot liên tiếp — TÁCH RIÊNG khỏi `assembly.py`
(dùng ffmpeg `xfade` thật) để tránh import vòng: `app/routers/pipeline.py` (validate
giá trị `transition_to_next` lúc PATCH shot) không thể import thẳng từ `assembly.py`
vì `assembly.py` → `app/render/engine.py` → `app/routers/pipeline.py` (import
`record_asset_usage`) đã là 1 vòng có sẵn — module riêng, không phụ thuộc gì, phá vòng
đó. Xem `assembly.py` để biết cách dùng thật trong ffmpeg (mục 33
IMPLEMENTATION_REPORT.md, 2026-08-17).
"""

# Curated theo tinh thần nội dung kể chuyện lịch sử/tài liệu dài — bỏ hẳn các loại
# `xfade` hoa mỹ/game-y (zoomin, pixelize, squeezeh...) không hợp giọng điệu nghiêm túc.
# `cut` KHÔNG dùng `xfade` (đường ghép NHANH cũ, stream-copy). Các loại còn lại là tên
# transition CHUẨN của ffmpeg `xfade` filter (không tự đặt tên).
TRANSITIONS: dict[str, str] = {
    "cut": "Cắt cứng (mặc định, nhanh nhất — không re-encode)",
    "fade": "Hoà tan (crossfade mượt)",
    "fadeblack": "Mờ qua đen (ngắt cảnh rõ, hợp đổi chủ đề)",
    "dissolve": "Tan dần (hạt nhiễu, mềm mại)",
    "wipeleft": "Gạt trái",
    "wiperight": "Gạt phải",
    "smoothleft": "Trượt mượt trái",
    "smoothright": "Trượt mượt phải",
}
