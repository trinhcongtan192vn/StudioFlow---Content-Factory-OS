"""Cắt nhỏ text 1 block/shot DÀI thành nhiều "cue" phụ đề ngắn hơn, kèm timestamp chia
lại theo tỷ lệ số ký tự — **mới (2026-09-12)**, theo yêu cầu người dùng: "File transcript
srt đang chia timestamp theo block... mỗi block có thể đọc quá dài nên việc hiển thị
subtitle theo transcript bị tràn chữ. Cần cắt ngắn xuống... để có thể sử dụng sau này (ví
dụ chèn caption vào video khi render)".

Tách RIÊNG module (khác `pack_export.py`, vốn chỉ lo đóng gói/ghi file ra bundle) vì đây
là 1 mối quan tâm ĐỘC LẬP — "1 khoảng thời gian nói nên hiển thị bao nhiêu chữ 1 lần" —
không phụ thuộc gì vào việc xuất bundle, và theo đúng yêu cầu người dùng cần TÁI DÙNG ĐƯỢC
cho tính năng khác sau này (chèn caption cứng lúc `assembly.py` ghép video).

**Đã dùng tới (2026-09-12, tiếp ngay sau)**: `write_shot_caption_ass` bên dưới — burn
caption CỨNG (pixel thật) vào video lúc ghép, theo yêu cầu người dùng "Bổ sung tính năng
cho phép user thêm caption vào video... chọn 9 vị trí, kích thước, độ mờ tương tự phần
Layer video định vị" (`RenderState.caption_layer`, xem `schemas.py::CaptionLayer`). Burn
TRỰC TIẾP vào TỪNG SEGMENT (không phải 1 lượt trên video ghép xong) — mỗi segment tự
ffmpeg đảm bảo đúng độ dài qua `-t duration`, nên timestamp CỤC BỘ `[0, duration)` của
`write_shot_caption_ass` LUÔN khớp khít, không cần tính lại mốc thời gian tuyệt đối qua
transition/reflow/offset intro (rủi ro lệch/trôi cao nếu làm ở tầng video đã ghép xong).
Ghi hẳn 1 file `.ass` HOÀN CHỈNH (không phải `.srt` + `force_style`) — xem bug thật đã
sửa trong docstring `write_shot_caption_ass`.

**Khớp ĐÚNG VO thật của TỪNG ngôn ngữ** (theo yêu cầu người dùng xác nhận thêm): hàm ở
đây KHÔNG tự giả định tốc độ đọc (ký tự/giây) theo ngôn ngữ nào cả — nó chỉ CHIA LẠI 1
khoảng `(start, duration)` đã có sẵn theo tỷ lệ SỐ KÝ TỰ của từng cue trên tổng ký tự của
CHÍNH đoạn text đó. Caller (`pack_export.py::build_srt_text`) đã tự chọn đúng `text`
(`audio` hoặc `audio_by_lang[lang]`) VÀ đúng `duration` (giọng đọc THẬT đo qua ffprobe của
CHÍNH ngôn ngữ đó — `narration_duration_sec`/`translation.narration_duration_sec`) TRƯỚC
khi gọi hàm ở đây — vì vậy timing luôn khớp với tốc độ nói THẬT của ngôn ngữ đang xử lý
(tiếng Đức nói chậm hơn/nhanh hơn tiếng Việt không quan trọng, vì ta không giả định tốc độ
— ta CHIA LẠI đúng khoảng thời gian giọng đọc thật đã đo được của ngôn ngữ đó)."""
from __future__ import annotations

import re
from pathlib import Path

# Số ký tự tối đa mỗi cue — quy ước phổ biến cho phụ đề 2 dòng (~42 ký tự/dòng, kiểu
# hướng dẫn caption style của Netflix/YouTube) → 84 ký tự. Áp dụng CHUNG cho mọi ngôn ngữ
# (VI/EN/DE/PT_BR/ES/FR) — không cần hệ số riêng, vì đây là giới hạn HIỂN THỊ (không tràn
# khung hình) chứ không phải giới hạn tốc độ đọc/nói.
DEFAULT_MAX_CUE_CHARS = 84

_WORD_SPLIT_RE = re.compile(r"\s+")


def split_text_into_cue_texts(text: str, *, max_chars: int = DEFAULT_MAX_CUE_CHARS) -> list[str]:
    """Cắt `text` thành nhiều đoạn NGẮN HƠN `max_chars` — "greedy word wrap" chuẩn (gộp
    từ liên tiếp cho tới khi thêm từ tiếp theo sẽ vượt giới hạn thì xuống đoạn mới), CHỈ
    cắt tại ranh giới TỪ, KHÔNG BAO GIỜ cắt giữa 1 từ. 1 từ đơn lẻ dài hơn `max_chars`
    (hiếm gặp — URL/số dài) vẫn giữ NGUYÊN VẸN trên 1 đoạn riêng dù vượt giới hạn — ưu
    tiên "không cắt vỡ chữ" hơn "tuyệt đối không vượt max_chars"."""
    words = [w for w in _WORD_SPLIT_RE.split(text.strip()) if w]
    if not words:
        return []
    cues: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        added_len = len(word) + (1 if current else 0)  # +1 cho dấu cách nối vào current
        if current and current_len + added_len > max_chars:
            cues.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += added_len
    if current:
        cues.append(" ".join(current))
    return cues


def split_block_into_cues(
    text: str, start_sec: float, duration_sec: float, *, max_chars: int = DEFAULT_MAX_CUE_CHARS,
) -> list[tuple[float, float, str]]:
    """Cắt 1 block/shot DÀI thành nhiều cue phụ đề ngắn, CHIA LẠI `(start_sec,
    start_sec+duration_sec)` theo tỷ lệ SỐ KÝ TỰ mỗi cue trên tổng ký tự — xấp xỉ tốt
    nhất có thể khi KHÔNG có timestamp per-word thật (app chưa có forced alignment/ASR;
    TTS chỉ trả về 1 file audio + tổng thời lượng, không có mốc thời gian từng từ). Trả
    list `(start, end, text)` LIÊN TỤC, khớp khít khoảng đưa vào — không hở/đè giữa các
    cue, cue CUỐI luôn kết thúc ĐÚNG `start_sec+duration_sec` (tránh lệch số thập phân
    cộng dồn qua nhiều cue).

    Trả `[(start_sec, start_sec+duration_sec, text)]` (1 cue DUY NHẤT, không cắt) nếu
    `text` đã ngắn hơn `max_chars` hoặc `duration_sec<=0` — giữ NGUYÊN hành vi cũ (trước
    khi có tính năng cắt cue) cho block ngắn, không tốn công cắt vô ích, cũng tránh chia 0."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars or duration_sec <= 0:
        return [(start_sec, start_sec + duration_sec, text)]

    chunks = split_text_into_cue_texts(text, max_chars=max_chars)
    if len(chunks) <= 1:
        return [(start_sec, start_sec + duration_sec, text)]

    total_chars = sum(len(c) for c in chunks)
    cues: list[tuple[float, float, str]] = []
    cursor = start_sec
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            cue_end = start_sec + duration_sec
        else:
            cue_end = cursor + duration_sec * (len(chunk) / total_chars)
        cues.append((cursor, cue_end, chunk))
        cursor = cue_end
    return cues


def _format_ass_timestamp(sec: float) -> str:
    """Định dạng timestamp kiểu ASS/SSA — `H:MM:SS.cc` (centigiây 2 chữ số, PHÂN CÁCH
    giờ bằng `:` nhưng KHÔNG có số 0 đệm ở giờ — khác hẳn `.srt` dùng `HH:MM:SS,mmm`
    mili giây 3 chữ số phân cách bằng dấu PHẨY). Bản copy cục bộ, không import chéo
    module tầng khác (`captions.py` là module TẦNG THẤP)."""
    sec = max(0.0, sec)
    total_cs = round(sec * 100)  # centigiây
    h, rem = divmod(total_cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    """Escape ký tự có Ý NGHĨA ĐẶC BIỆT trong `[Events]` của ASS — `{`/`}` mở/đóng khối
    override tag (VD `{\\b1}` in đậm); text thật từ script gần như không bao giờ chứa 2
    ký tự này, nhưng escape phòng hờ để tránh hiển thị sai/lỗi parse nếu lỡ có."""
    return text.replace("{", "\\{").replace("}", "\\}")


# Map 9 vị trí lưới 3x3 (`LayerPosition`, dùng chung với `VideoLayer`/`ImageLayer` — tái
# dùng đúng khái niệm "định vị theo lưới" người dùng đã quen) sang mã "Alignment" kiểu
# numpad của ASS/libass — KHỚP Y HỆT quy ước libass (1-3 = hàng dưới, 4-6 = hàng giữa,
# 7-9 = hàng trên; cột trái/giữa/phải lặp lại mỗi hàng), không cần bảng tra phức tạp.
LAYER_POSITION_TO_ASS_ALIGNMENT: dict[str, int] = {
    "bottom-left": 1, "bottom-center": 2, "bottom-right": 3,
    "middle-left": 4, "center": 5, "middle-right": 6,
    "top-left": 7, "top-center": 8, "top-right": 9,
}


def write_shot_caption_ass(
    path: Path, text: str, duration_sec: float, *,
    position: str, size_pct: float, opacity: float, out_w: int, out_h: int, max_chars: int = DEFAULT_MAX_CUE_CHARS,
) -> bool:
    """Ghi 1 file `.ass` HOÀN CHỈNH (tự khai `PlayResX`/`PlayResY`/1 Style/nhiều
    Dialogue) cho ĐÚNG 1 shot/segment, timestamp CỤC BỘ `[0, duration_sec)` — dùng để
    burn caption TRỰC TIẾP vào TỪNG SEGMENT lúc `assembly.py::_build_segment` (KHÔNG
    PHẢI burn 1 lần lên video đã ghép xong — xem quyết định kiến trúc trong docstring
    `CaptionLayer`, `render/schemas.py`: burn theo segment loại bỏ hẳn nhu cầu tính lại
    mốc thời gian tuyệt đối qua transition/reflow/intro offset, vì mỗi segment tự ffmpeg
    đảm bảo đúng `duration_sec` qua `-t`).

    **Đổi từ `.srt` + `force_style` sang tự viết `.ass` HOÀN CHỈNH (2026-09-12, bug thật
    xác nhận bằng ffmpeg thật)** — bản đầu dùng filter `subtitles=file.srt:original_size=
    {out_w}x{out_h}:force_style='Fontsize=...'`, kỳ vọng `original_size` khiến `Fontsize`
    (đơn vị pixel trong `force_style`) map ĐÚNG theo khung hình xuất thật. Verify bằng
    ffmpeg + trích frame thật: SAI HẲN — `original_size` KHÔNG có tác dụng đó (dùng để
    scale font theo tỷ lệ khung hình GỐC ↔ khung hình ĐANG decode, không phải quy đổi
    "Fontsize nghĩa là pixel thật"); `.srt` thuần (không header) khiến libass tự chọn
    `PlayResX`/`PlayResY` mặc định — với `Fontsize=96` trên khung 1080x1920, chữ ra
    KHỔNG LỒ (chiếm gần hết chiều cao khung hình, xác nhận bằng ảnh trích frame thật,
    không suy đoán) — hoàn toàn không dùng được. Fix: tự viết `[Script Info]
    PlayResX/PlayResY` = ĐÚNG `out_w`/`out_h`, khai Style TRỰC TIẾP trong `[V4+ Styles]`
    (không qua `force_style` nữa) — `Fontsize` giờ LUÔN đúng đơn vị pixel trong hệ toạ độ
    `PlayResX×PlayResY` đã khai, KHÔNG còn phụ thuộc suy luận về hành vi mặc định của
    libass. Verify lại bằng ffmpeg thật: chữ ra đúng cỡ hợp lý, đúng vị trí bottom-center
    (đo pixel: dải dưới khung hình có nhiều pixel khác nền hẳn dải trên, tỷ lệ ngược lại
    khi đổi "top-center") — xem `tests/test_caption_layer.py`.

    Trả `False` (KHÔNG ghi file gì) khi `text` rỗng — caller (vòng lặp build segment ở
    `_assemble_video_impl`/`short_export.py`) bỏ qua hẳn việc burn caption cho shot đó,
    không phải lỗi (shot chỉ hình không lời, hoặc ngôn ngữ caption chưa có bản dịch cho
    block này — cùng nguyên tắc "bỏ qua block rỗng" của `build_srt_text`/`build_script_
    txt`).

    `opacity` — ASS dùng `&HAABBGGRR` (alpha 2 hex đầu, 00=ĐỤC hoàn toàn, FF=TRONG SUỐT
    hoàn toàn — NGƯỢC trực giác thông thường), `alpha = round((1-opacity)*255)`. Áp DÙNG
    CHUNG 1 giá trị opacity cho cả chữ (`PrimaryColour`, trắng) VÀ viền/bóng
    (`OutlineColour`/`BackColour`, đen) — 1 nút "độ mờ" duy nhất theo đúng yêu cầu người
    dùng (không tách riêng độ mờ chữ/viền — không được yêu cầu, tránh over-engineer).
    `BorderStyle=1` (viền + đổ bóng) + `Outline=2` (độ dày viền cố định) — chữ trắng viền
    đen là quy ước phụ đề phổ biến nhất, đọc được trên hầu hết nền hình ảnh. `MarginV`/
    `MarginL`/`MarginR` — lề cố định ~6% kích thước khung tương ứng, tránh caption dính
    sát mép khung hình."""
    cues = split_block_into_cues(text, 0.0, duration_sec, max_chars=max_chars)
    if not cues:
        return False

    alignment = LAYER_POSITION_TO_ASS_ALIGNMENT.get(position, 2)
    font_size = max(1, round(size_pct * out_h))
    alpha = max(0, min(255, round((1 - opacity) * 255)))
    primary_color = f"&H{alpha:02X}FFFFFF"  # chữ trắng
    outline_color = f"&H{alpha:02X}000000"  # viền/bóng đen
    margin_v = round(0.06 * out_h)
    margin_h = round(0.06 * out_w)

    events = "\n".join(
        f"Dialogue: 0,{_format_ass_timestamp(start)},{_format_ass_timestamp(end)},Default,,0,0,0,,{_escape_ass_text(cue_text)}"
        for start, end, cue_text in cues
    )
    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {out_w}
PlayResY: {out_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},{primary_color},{primary_color},{outline_color},{outline_color},0,0,0,0,100,100,0,0,1,2,0,{alignment},{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{events}
"""
    path.write_text(content, encoding="utf-8")
    return True
