"""Nhập kịch bản từ CSV/Excel — 6 cột: Mã block, Thời lượng, Loại Visual,
Hình ảnh & Hiệu ứng (Visual/FX), Âm thanh & Nhạc nền (Audio/SFX), Kịch bản Giọng đọc (VO).

Quyết định triển khai (đã build vòng 4, khác design gốc): design parse file bằng
SheetJS (`xlsx.full.min.js`, ~800KB) chạy phía client. Bản build này parse phía
SERVER (Python) — tránh nạp thêm thư viện JS nặng vào bundle Electron, gom logic
parse/validate vào 1 chỗ và test được bằng pytest (đúng nguyên tắc đã áp dụng cho
toàn bộ backend). Frontend chỉ upload file thô, không tự parse.

**Giọng đọc đa ngôn ngữ (2026-09-04)** — cột VO đơn ("Kịch bản Giọng đọc (VO Content)")
GIỮ NGUYÊN parse được y hệt cũ (tương thích ngược, coi là văn bản ngôn ngữ CHÍNH của
kênh). Kênh phục vụ thị trường nước ngoài có thể thay bằng NHIỀU cột dạng `VO (XX)`
(VD "VO (VI)", "VO (DE)", "VO (PT-BR)") — mỗi cột 1 ngôn ngữ trong `NARRATION_LANGUAGES`
(app/render/schemas.py), dò bằng `_VO_LANG_COLUMN_RE` thay vì `COLUMN_KEYWORDS["vo"]`
đơn. File có ÍT NHẤT 1 trong 2 dạng cột trên là hợp lệ — không bắt buộc đủ cả 6 ngôn
ngữ (dịch dần từng ngôn ngữ theo tiến độ dự án, không phải tất cả cùng lúc)."""
from __future__ import annotations

import csv
import io
import re

COLUMN_KEYWORDS: dict[str, list[str]] = {
    "block_id": ["mã"],
    "ts": ["thời lượng"],
    "visual_type": ["loại visual"],
    "visual": ["hình ảnh", "visual/fx"],
    "audio_sfx": ["âm thanh", "audio/sfx"],
}
# Cột VO ĐƠN (cũ, tương thích ngược) — dò riêng khỏi `COLUMN_KEYWORDS` vì có thể bị
# THAY bằng nhiều cột `VO (XX)` (xem `_VO_LANG_COLUMN_RE`), không bắt buộc cùng lúc.
_VO_SINGLE_KEYWORDS = ["kịch bản", "vo content", "giọng đọc"]
# "VO (VI)"/"VO (DE)"/"VO (PT-BR)"... — bắt mã ngôn ngữ trong ngoặc, không phân biệt
# hoa/thường/khoảng trắng quanh dấu ngoặc.
_VO_LANG_COLUMN_RE = re.compile(r"vo\s*\(\s*([a-z-]+)\s*\)", re.IGNORECASE)
# Map mã cột (chữ hoa trong ngoặc file Excel) -> mã ngôn ngữ nội bộ (NARRATION_LANGUAGES).
_VO_LANG_COLUMN_TO_CODE = {"VI": "vi", "EN": "en", "DE": "de", "PT-BR": "pt_br", "ES": "es", "FR": "fr"}

REQUIRED_COLUMNS_MESSAGE = (
    "File cần đủ 5 cột: Mã block, Thời lượng, Loại Visual, "
    "Hình ảnh & Hiệu ứng (Visual/FX), Âm thanh & Nhạc nền (Audio/SFX), "
    "và ít nhất 1 cột giọng đọc (\"Kịch bản Giọng đọc (VO Content)\" HOẶC 1/nhiều cột "
    "dạng \"VO (VI)\", \"VO (EN)\"...)."
)

DEFAULT_BLOCK_SEC = 8  # ước tính khi không đọc được "Thời lượng" của 1 block


class ScriptImportError(Exception):
    """Lỗi hiển thị trực tiếp cho người dùng trong dialog xác nhận nhập kịch bản."""


def _find_col(header: list[str], keywords: list[str]) -> int:
    for i, h in enumerate(header):
        low = h.lower().strip()
        if any(k in low for k in keywords):
            return i
    return -1


def _rows_from_csv(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader if any(str(c).strip() for c in row)]


def _rows_from_xlsx(content: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), data_only=True)
    sheet = wb[wb.sheetnames[0]]
    rows: list[list[str]] = []
    for row in sheet.iter_rows(values_only=True):
        cells = ["" if c is None else str(c) for c in row]
        if any(c.strip() for c in cells):
            rows.append(cells)
    return rows


_TS_RANGE = re.compile(r"^(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})$")
_TS_SINGLE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_ts(ts: str) -> tuple[int | None, int | None]:
    """'0:00–0:05' -> (0, 5). '1:30' -> (90, None). Không nhận dạng được -> (None, None)."""
    ts = ts.strip()
    m = _TS_RANGE.match(ts)
    if m:
        start = int(m.group(1)) * 60 + int(m.group(2))
        end = int(m.group(3)) * 60 + int(m.group(4))
        return start, end
    m = _TS_SINGLE.match(ts)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)), None
    return None, None


def _find_vo_lang_columns(header: list[str]) -> dict[str, int]:
    """Dò cột dạng `VO (XX)` — trả `{lang_code: column_index}`, chỉ giữ mã ngôn ngữ nhận
    diện được (`_VO_LANG_COLUMN_TO_CODE`). Rỗng nếu file dùng dạng cột VO đơn cũ."""
    found: dict[str, int] = {}
    for i, h in enumerate(header):
        m = _VO_LANG_COLUMN_RE.search(h or "")
        if not m:
            continue
        code = _VO_LANG_COLUMN_TO_CODE.get(m.group(1).upper())
        if code:
            found[code] = i
    return found


def parse_script_rows(rows: list[list[str]], *, primary_language: str = "vi") -> dict:
    """Trả `{beats, stats, full_text}`. Raise `ScriptImportError` (thông điệp tiếng
    Việt hiển thị thẳng cho người dùng) nếu file trống/thiếu cột/không có block.

    `primary_language` — **mới (2026-09-04)**, giọng đọc đa ngôn ngữ: quyết định cột
    `VO (XX)` nào trở thành `beat["audio"]` (field gốc, mọi nơi downstream — assembly,
    SRT, guardrail — tiếp tục đọc y hệt cũ). Chỉ có tác dụng khi file dùng dạng NHIỀU
    cột `VO (XX)`; file dùng cột VO đơn (cũ) bỏ qua tham số này, luôn map thẳng vào
    `audio` như trước."""
    if not rows:
        raise ScriptImportError("File trống — không tìm thấy dữ liệu.")

    header = [str(h or "") for h in rows[0]]
    idx = {k: _find_col(header, kws) for k, kws in COLUMN_KEYWORDS.items()}
    missing = [k for k, v in idx.items() if v == -1]
    if missing:
        raise ScriptImportError(REQUIRED_COLUMNS_MESSAGE)

    vo_lang_cols = _find_vo_lang_columns(header)
    vo_single_idx = -1 if vo_lang_cols else _find_col(header, _VO_SINGLE_KEYWORDS)
    if not vo_lang_cols and vo_single_idx == -1:
        raise ScriptImportError(REQUIRED_COLUMNS_MESSAGE)

    data_rows = rows[1:]
    if not data_rows:
        raise ScriptImportError("File không có block nào ở dưới dòng tiêu đề.")

    def cell(r: list, i: int) -> str:
        return str(r[i]).strip() if i < len(r) and r[i] is not None else ""

    beats = []
    cursor = 0
    for r in data_rows:
        ts_raw = cell(r, idx["ts"])
        start, end = parse_ts(ts_raw)
        if start is None:
            start = cursor
        if vo_lang_cols:
            audio_by_lang = {lang: cell(r, i) for lang, i in vo_lang_cols.items()}
            audio = audio_by_lang.get(primary_language) or next(iter(audio_by_lang.values()), "")
        else:
            audio_by_lang = {}
            audio = cell(r, vo_single_idx)
        beats.append(
            {
                "block_id": cell(r, idx["block_id"]),
                "ts_label": ts_raw or f"{start // 60}:{start % 60:02d}",
                "timestamp_sec": start,
                "end_sec": end,
                "visual_type": cell(r, idx["visual_type"]),
                "visual": cell(r, idx["visual"]),
                "direction": cell(r, idx["audio_sfx"]),
                "direction_label": "Audio/SFX",
                "audio": audio,
                "audio_by_lang": audio_by_lang,
                "anchor": False,
            }
        )
        cursor = (end if end is not None else start) + DEFAULT_BLOCK_SEC

    full_text = "\n\n".join(b["audio"] for b in beats if b["audio"])
    word_count = len(full_text.split())
    has_duration = any(b["end_sec"] is not None for b in beats)
    if has_duration:
        total_sec = sum((b["end_sec"] - b["timestamp_sec"]) for b in beats if b["end_sec"] is not None)
        duration_label = f"{total_sec // 60}:{total_sec % 60:02d}"
    else:
        duration_label = "Không xác định"

    return {
        "beats": beats,
        "stats": {"block_count": len(beats), "word_count": word_count, "duration_label": duration_label},
        "full_text": full_text,
    }


_TEMPLATE_HEADER = [
    "Mã block",
    "Thời lượng",
    "Loại Visual",
    "Hình ảnh & Hiệu ứng (Visual/FX)",
    "Âm thanh & Nhạc nền (Audio/SFX)",
    "Kịch bản Giọng đọc (VO Content)",
]
_TEMPLATE_EXAMPLE_ROWS = [
    ["B01", "0:00–0:08", "Video", "Cận cảnh nhân vật bước vào khung hình, ánh sáng ngược", "[SFX]: Tiếng bước chân. [BGM]: Trống trầm, nhịp chậm.", "Đêm ấy, không ai ngờ mọi chuyện lại rẽ sang một hướng khác."],
    ["B02", "0:08–0:20", "Image", "Bản đồ cổ, cận cảnh vị trí đánh dấu", "[BGM]: Tiếp tục nền, hạ nhẹ.", "Nội dung lời đọc cho block này — có thể dài nhiều câu."],
]


_TEMPLATE_MULTILANG_HEADER = [
    "Mã",
    "Thời lượng",
    "Loại Visual",
    "Visual/FX",
    "Audio/SFX",
    "VO (VI)",
    "VO (EN)",
    "VO (DE)",
    "VO (PT-BR)",
    "VO (ES)",
    "VO (FR)",
]
_TEMPLATE_MULTILANG_EXAMPLE_ROWS = [
    [
        "B01", "0:00–0:08", "Video", "Cận cảnh nhân vật bước vào khung hình, ánh sáng ngược",
        "[SFX]: Tiếng bước chân. [BGM]: Trống trầm, nhịp chậm.",
        "Đêm ấy, không ai ngờ mọi chuyện lại rẽ sang một hướng khác.",
        "That night, no one expected things to take such a different turn.",
        "In jener Nacht ahnte niemand, dass sich alles so anders wenden würde.",
        "Naquela noite, ninguém esperava que tudo tomasse um rumo tão diferente.",
        "Esa noche, nadie esperaba que todo diera un giro tan distinto.",
        "Cette nuit-là, personne ne s'attendait à ce que tout prenne une tournure si différente.",
    ],
]


def build_template_workbook(*, multilang: bool = False) -> bytes:
    """Tạo file Excel mẫu đúng cột `parse_script_rows()` yêu cầu (`COLUMN_KEYWORDS`/
    `_VO_LANG_COLUMN_TO_CODE` ở trên — SỬA CẢ 2 CHỖ nếu đổi tên cột, để mẫu không lệch
    parser) — kèm dòng ví dụ minh hoạ định dạng "Thời lượng" (H:MM–H:MM) và nội dung
    từng cột, tránh người dùng đoán sai format rồi bị từ chối lúc import thật.

    `multilang` — **mới (2026-09-04)**, giọng đọc đa ngôn ngữ: `True` sinh mẫu 11 cột
    (1 cột VO/ngôn ngữ trong `NARRATION_LANGUAGES` thay vì 1 cột VO đơn) — dùng cho kênh
    phục vụ thị trường nước ngoài, tải qua nút riêng "Mẫu đa ngôn ngữ" ở Script Studio."""
    from openpyxl import Workbook

    header = _TEMPLATE_MULTILANG_HEADER if multilang else _TEMPLATE_HEADER
    example_rows = _TEMPLATE_MULTILANG_EXAMPLE_ROWS if multilang else _TEMPLATE_EXAMPLE_ROWS
    widths = [10, 14, 12, 42, 42] + ([30] * 6 if multilang else [55])
    col_letters = "ABCDEFGHIJK" if multilang else "ABCDEF"

    wb = Workbook()
    ws = wb.active
    ws.title = "Kịch bản"
    ws.append(header)
    for row in example_rows:
        ws.append(row)
    for col_letter, width in zip(col_letters, widths):
        ws.column_dimensions[col_letter].width = width
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_script_file(content: bytes, filename: str, *, primary_language: str = "vi") -> dict:
    is_csv = filename.lower().endswith(".csv")
    try:
        rows = _rows_from_csv(content) if is_csv else _rows_from_xlsx(content)
    except ScriptImportError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ScriptImportError("Không đọc được file. Kiểm tra định dạng CSV/Excel và thử lại.") from e
    return parse_script_rows(rows, primary_language=primary_language)
