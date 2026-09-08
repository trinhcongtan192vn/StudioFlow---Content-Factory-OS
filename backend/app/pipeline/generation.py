"""Khôi phục Visual/FX + Audio/SFX của 1 shot từ ĐÚNG script gốc — specs/07 mục 7.

**Đổi (2026-08-25), theo yêu cầu người dùng**: trước đây "Tạo lại Visual"/"Tạo lại
giọng đọc" gọi LLM diễn giải lại `beat.visual`/`beat.direction` (script gốc) thành 1
đoạn prompt khác — nhưng `shot.visual_fx`/`shot.audio_sfx` vốn ĐÃ được khởi tạo trực
tiếp từ CHÍNH 2 field đó lúc tạo shot (`routers/pipeline.py` dòng ~325-326, xem
`_find_shot_and_beat`), không qua LLM. Vậy bước LLM chỉ diễn giải LẠI dữ liệu đã có sẵn
trong script — không cộng thêm thông tin mới, tốn 1 lệnh gọi Provider AI (cần cấu hình,
có độ trễ/chi phí) cho việc mà chỉ cần đọc lại đúng field gốc. Bỏ hẳn LLM khỏi 2 hàm
này — "Tạo lại" giờ nghĩa là "khôi phục về đúng như script gốc" (hữu ích khi người dùng
đã tự sửa tay `visual_fx`/`audio_sfx` ở Visual Studio và muốn quay lại bản gốc).

`fallback_content.py`/template `visual_image`/`visual_video`/`visual_tts` (Cài đặt →
Prompt Templates) KHÔNG còn được đọc bởi module này nữa — màn Prompt Templates vẫn còn
(hạ tầng CRUD chung, dùng được cho task khác), chỉ 3 template này hết tác dụng thật, xem
IMPLEMENTATION_REPORT.md để biết có nên dọn tiếp UI/seed data hay không."""
from __future__ import annotations


def restore_shot_visual_fx(beat: dict) -> str:
    """Trả nguyên si `beat.visual` (cột "Hình ảnh & Hiệu ứng" của script gốc) — raise
    `ValueError` nếu rỗng (script gốc không có mô tả cho shot này, không có gì để khôi
    phục về)."""
    visual = (beat.get("visual") or "").strip()
    if not visual:
        raise ValueError("Script gốc không có mô tả Visual/FX cho shot này.")
    return visual


def restore_shot_audio_sfx(beat: dict) -> str:
    """Trả nguyên si `beat.direction` (cột "Âm thanh & Nhạc nền" của script gốc) —
    raise `ValueError` nếu rỗng."""
    direction = (beat.get("direction") or "").strip()
    if not direction:
        raise ValueError("Script gốc không có mô tả Audio/SFX cho shot này.")
    return direction
