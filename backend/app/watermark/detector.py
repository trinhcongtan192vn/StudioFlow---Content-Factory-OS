"""Phát hiện vùng watermark bằng Florence-2 (Microsoft, `microsoft/Florence-2-base`) —
open-vocabulary object detection: đưa 1 câu mô tả bằng chữ ("watermark"), model trả về
bounding box khớp mô tả đó trong ảnh, KHÔNG cần train riêng cho từng loại watermark cụ
thể. Cache model theo tiến trình (giống pattern `depth_parallax.py::_get_session`) — nạp
model ~63s (đo thật lúc verify), chỉ nạp 1 LẦN rồi tái dùng cho mọi lần gọi sau trong
CÙNG tiến trình backend, không nạp lại mỗi request.

**`trust_remote_code=True` bắt buộc** — Florence-2 định nghĩa kiến trúc model riêng
(`configuration_florence2.py`/`modeling_florence2.py`), không có trong `transformers`
gốc, HuggingFace tự tải code này về máy lúc `from_pretrained` (cảnh báo bảo mật chuẩn của
`transformers` khi làm vậy — chấp nhận được vì đây là repo chính chủ Microsoft, không
phải fork lạ).

**Bug thật gặp lúc verify (2026-08-27)**: `transformers` bản MỚI NHẤT lúc cài (5.16.1, hệ
API đã viết lại lớn so với dòng 4.x) làm code Florence-2 (viết cho `transformers` 4.x)
crash `AttributeError: 'Florence2LanguageConfig' object has no attribute
'forced_bos_token_id'` ngay lúc nạp config — hạ về `transformers==4.49.0` (ghim trong
requirements.txt) chạy đúng, xác nhận thật bằng cách chạy lại nguyên script verify."""
from __future__ import annotations

from PIL import Image

_FLORENCE_MODEL_ID = "microsoft/Florence-2-base"
_DETECTION_TASK = "<OPEN_VOCABULARY_DETECTION>"

_session: dict[str, object] = {}


def _get_florence():
    if "model" not in _session:
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        model = AutoModelForCausalLM.from_pretrained(_FLORENCE_MODEL_ID, trust_remote_code=True, torch_dtype=dtype).to(device)
        processor = AutoProcessor.from_pretrained(_FLORENCE_MODEL_ID, trust_remote_code=True)
        _session.update(model=model, processor=processor, device=device, dtype=dtype)
    return _session["model"], _session["processor"], _session["device"], _session["dtype"]


def detect_watermark_bboxes(image: Image.Image, text_input: str = "watermark") -> list[tuple[int, int, int, int]]:
    """Trả list bbox `(x1,y1,x2,y2)` (toạ độ pixel THẬT trên `image`, đã làm tròn int) —
    rỗng nếu không tìm thấy vùng nào khớp mô tả.

    **`text_input` — CHỈ nên để 1 TỪ ĐƠN, đã verify thật, không suy đoán**: ban đầu định
    dùng `"watermark, logo, text overlay"` (nhiều khái niệm cách nhau dấu phẩy, tưởng
    Florence-2 hiểu là "hoặc" giữa các khái niệm) — verify tay trên CHÍNH 1 frame video
    test thật cho kết quả SAI hẳn (bbox trả về là NGUYÊN CẢ khung hình `[0,0,639,479]`,
    không phải vùng watermark thật), trong khi 2 từ đơn riêng biệt `"watermark"` và
    `"logo"` trên ĐÚNG frame đó đều cho bbox CHÍNH XÁC (khớp watermark thật đã vẽ, sai lệch
    <5px) — cụm `"text overlay"` (dù chỉ 1 khái niệm) CŨNG cho kết quả sai full-frame
    tương tự. Kết luận: câu prompt phức tạp/nhiều khái niệm làm open-vocabulary detection
    của Florence-2 kém tin cậy hẳn — giữ mặc định `"watermark"` (đã verify ổn định), KHÔNG
    tự ý mở rộng thành câu dài hơn nếu chưa verify lại bằng ảnh thật."""
    model, processor, device, dtype = _get_florence()
    prompt = _DETECTION_TASK + text_input
    inputs = processor(text=prompt, images=image, return_tensors="pt").to(device, dtype)
    generated_ids = model.generate(
        input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
        max_new_tokens=1024, num_beams=3, do_sample=False,
    )
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    parsed = processor.post_process_generation(generated_text, task=_DETECTION_TASK, image_size=(image.width, image.height))
    result = parsed.get(_DETECTION_TASK, {})
    bboxes = result.get("bboxes", [])
    return [tuple(int(round(v)) for v in b) for b in bboxes]


# Bug thật (2026-08-28, user báo video ghép bằng Gemini/Veo bị "mất hình ảnh" sau khi xoá
# watermark) — verify thật trên ĐÚNG frame video lỗi (`raw_1788341279704_L3B01.mp4`, cảnh
# quay bút lông viết chữ Hán, watermark thật là 1 icon hình ngôi sao lấp lánh nhỏ ở góc dưới
# phải — kiểu watermark chuẩn của Google Gemini/Veo, KHÁC hẳn watermark chữ/logo của các
# video test tổng hợp trước đây): prompt `"watermark"` (mặc định) trả bbox SAI — GẦN NHƯ
# NGUYÊN KHUNG HÌNH (`(1, 0, 1278, 719)`, chiếm 99.6% diện tích), `"logo"` cũng sai tương tự
# (78%) — LaMa sau đó "vá" gần như cả khung hình (hầu hết vùng bị che bởi mask) sinh ra ảnh
# mờ/nhoè GẦN NHƯ MẤT SẠCH nội dung gốc, đúng triệu chứng "mất hình ảnh" người dùng báo.
# Đổi prompt sang `"star icon"`/`"small icon"` (mô tả ĐÚNG hình dạng thật của watermark này)
# trên CHÍNH frame đó cho bbox CHÍNH XÁC, khít sát icon thật (`~60×58px`, 0.4% diện tích).
_MAX_BBOX_AREA_FRACTION = 0.35  # legitimate watermark/logo hiếm khi > ~1/3 khung hình — ngưỡng AN TOÀN, thấp hơn hẳn 2 lần đo sai (99.6%/78%) nhưng đủ rộng cho watermark to (VD dải chữ credit chiếm 1 góc lớn)
_FALLBACK_PROMPTS = ("logo", "small icon in the corner")


def _bbox_area_fraction(bbox: tuple[int, int, int, int], image_size: tuple[int, int]) -> float:
    x1, y1, x2, y2 = bbox
    w, h = image_size
    return max(0, x2 - x1) * max(0, y2 - y1) / (w * h)


def _bbox_dimension_fractions(bbox: tuple[int, int, int, int], image_size: tuple[int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    w, h = image_size
    return max(0, x2 - x1) / w, max(0, y2 - y1) / h


# Bug thật #3 (2026-09-04, ảnh minh hoạ vẽ tay, logo Gemini nhỏ ở góc dưới phải, project
# "p" kênh "t" của user): prompt "watermark" trả bbox chỉ chiếm ~31% DIỆN TÍCH (LỌT ngưỡng
# `_MAX_BBOX_AREA_FRACTION`) nhưng trải GẦN TRỌN CHIỀU CAO khung hình (~100% height) — đo
# trực tiếp trên `B01_nowm.png` thật của user (phân tích độ nét theo cột ảnh: vùng bị LaMa
# làm mờ là 1 dải DỌC bên phải ảnh, ~850/2752px ngang × TOÀN BỘ 1536px cao), rõ ràng không
# phải icon góc nhỏ thật — chỉ lọc theo DIỆN TÍCH không đủ, cần lọc thêm HÌNH DẠNG. Watermark
# thật chỉ thuộc 1 trong 2 dạng: (a) icon/logo GỌN — không vượt quá nửa MỖI chiều, hoặc (b)
# dải chữ credit chạy dọc 1 cạnh — gần hết 1 chiều nhưng MỎNG ở chiều còn lại. 1 bbox trải
# gần hết 1 chiều mà KHÔNG mỏng ở chiều kia (như bug thật trên) không khớp dạng nào cả.
_MAX_COMPACT_DIM_FRACTION = 0.5
_MIN_BAND_SPAN_FRACTION = 0.8
_MAX_BAND_THICKNESS_FRACTION = 0.2


def _bbox_has_plausible_shape(bbox: tuple[int, int, int, int], image_size: tuple[int, int]) -> bool:
    wf, hf = _bbox_dimension_fractions(bbox, image_size)
    compact = wf <= _MAX_COMPACT_DIM_FRACTION and hf <= _MAX_COMPACT_DIM_FRACTION
    band = max(wf, hf) >= _MIN_BAND_SPAN_FRACTION and min(wf, hf) <= _MAX_BAND_THICKNESS_FRACTION
    return compact or band


# Bug thật #4 (2026-09-04, tiếp bug #3) — SAU KHI vá lọc hình dạng ở trên, verify trực
# tiếp bằng model Florence-2 THẬT trên `B02_nowm.png` (icon lấp lánh Gemini còn NGUYÊN,
# chưa qua xoá lần nào) với 8+ prompt khác nhau (`"watermark"`, `"logo"`, `"sparkle icon"`,
# `"star icon"`, `"four pointed star icon"`, `"white sparkle logo watermark"`...) VÀ cả khi
# crop sẵn góc dưới phải trước khi đưa vào model — KHÔNG prompt/crop nào định vị đúng icon
# thật (model luôn chỉ ra nhầm quần áo/đồ vật khác trong tranh). Kết luận: icon lấp lánh
# TRONG SUỐT của Gemini/Nano Banana có độ tương phản quá thấp trên nền minh hoạ chi tiết —
# Florence-2-base (open-vocabulary, không train riêng cho watermark) không đủ khả năng nhận
# diện dạng này, không phải lỗi ngưỡng/prompt có thể vá thêm được nữa.
#
# Người dùng xác nhận hướng xử lý (hỏi trực tiếp qua AskUserQuestion, chọn phương án được
# đề xuất): "chỉ cần hỗ trợ case của ảnh từ gemini logo, đúng vị trí đó và icon lấp lánh đó
# của tất cả các ảnh" — bỏ qua AI định vị theo NỘI DUNG ảnh, dùng VỊ TRÍ TƯƠNG ĐỐI CỐ ĐỊNH
# theo quy ước đặt watermark của Gemini/Nano Banana thay thế. Đo TRỰC TIẾP trên 2 ảnh thật
# của user (khác kích thước hẳn nhau — xác nhận đây là tỉ lệ TƯƠNG ĐỐI, không phải toạ độ
# tuyệt đối): `B02_nowm.png` (2816×1536) — bbox icon thật đo bằng lưới toạ độ chồng lên ảnh,
# xác nhận bằng mắt: `(2470, 1220, 2600, 1330)` → tâm ở (90.0%, 83.0%) chiều rộng/cao.
# `B01_nowm.png` (2752×1536, icon đã bị mờ 1 phần do bug #3 nên đo thô hơn) → tâm ước lượng
# (90.9%, 83.7%) — khớp `B02` trong sai số <1%, xác nhận watermark Gemini LUÔN ở cùng 1 vị
# trí tương đối, không phụ thuộc nội dung ảnh cụ thể — khác hẳn watermark truyền thống (chữ/
# logo) vốn cần AI định vị theo nội dung.
#
# Bug thật #5 (2026-09-04, tiếp bug #4) — user báo TIẾP "slot B02 xoá watermark gemini
# không được" với 1 ảnh KHÁC (shot B02 được thay ảnh test mới). Verify trực tiếp: vùng vá cũ
# (half-size 4.5%/5.5%) áp ĐÚNG vị trí lân cận 2 mũi giáo trong ảnh (khớp toạ độ tương đối đã
# đo) nhưng phần mờ/nhoè do LaMa để lại RÕ RÀNG tràn ra NGOÀI biên trên + biên phải của vùng
# đã vá (xem ảnh chụp box đỏ lúc điều tra) — xác nhận icon lấp lánh của lượt sinh ảnh NÀY to/
# lệch hơn 1 chút so với 2 ảnh đo ban đầu (biến thiên giữa các lượt sinh của Gemini, không cố
# định tuyệt đối tới từng pixel). Foundation của fix bug #4 (vị trí TƯƠNG ĐỐI cố định) vẫn
# đúng — chỉ cần vùng phủ RỘNG RÃI hơn để chịu được biến thiên đó. Tăng half-size từ
# (4.5%, 5.5%) → (7%, 9%) — diện tích vùng phủ từ ~1% lên ~2.5% khung hình, vẫn rất nhỏ so
# ngưỡng "phá huỷ nội dung lớn" (~31-35%) đã thấy ở bug #1/#2/#3, nhưng đủ biên an toàn hơn
# hẳn cho biến thiên thực tế giữa các lượt sinh ảnh khác nhau.
_GEMINI_CORNER_CENTER = (0.90, 0.83)  # (x, y) tính theo % chiều rộng/cao từ góc trên-trái
_GEMINI_CORNER_HALF_SIZE = (0.07, 0.09)  # nửa bề rộng/cao vùng phủ, cùng đơn vị %


def gemini_corner_bbox(image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Trả bbox CỐ ĐỊNH khớp vị trí watermark Gemini/Nano Banana đã đo thật (xem bug thật #4
    ở trên) — KHÔNG qua Florence-2, dùng làm bbox MẶC ĐỊNH cho `remove_watermark_from_image`
    khi không có `bboxes` truyền tay. Chỉ áp dụng cho ẢNH (video Gemini/Veo dùng vị trí khác
    hẳn — icon ngôi sao lấp lánh nhỏ hơn nhiều, xem bug thật #2, VẪN định vị được qua
    Florence-2 nên KHÔNG đổi luồng video)."""
    w, h = image_size
    cx, cy = _GEMINI_CORNER_CENTER
    hw, hh = _GEMINI_CORNER_HALF_SIZE
    return round((cx - hw) * w), round((cy - hh) * h), round((cx + hw) * w), round((cy + hh) * h)


def detect_watermark_bboxes_robust(
    image: Image.Image, text_input: str = "watermark", fallback_prompts: tuple[str, ...] = _FALLBACK_PROMPTS,
) -> list[tuple[int, int, int, int]]:
    """Bản AN TOÀN của `detect_watermark_bboxes` — lọc bỏ bbox PHI LÝ (chiếm gần hết khung
    hình, HOẶC trải gần hết 1 chiều mà không mỏng ở chiều kia — dấu hiệu Florence-2 "đoán
    bừa" thay vì định vị đúng vùng nhỏ thật sự, xem bug thật ở trên) TRƯỚC KHI trả về, và tự
    thử LẦN LƯỢT các prompt dự phòng trong `fallback_prompts` nếu prompt chính không cho
    bbox nào đủ tin cậy — nhiều dạng watermark AI-gen hiện đại (icon nhỏ, không phải chữ/
    logo truyền thống) cần mô tả CỤ THỂ HƠN mới định vị đúng. Trả rỗng nếu KHÔNG prompt nào
    (kể cả dự phòng) cho bbox đáng tin — an toàn hơn hẳn việc lỡ tay vá gần hết khung hình,
    dù nghĩa là bỏ sót vài trường hợp đáng lẽ xoá được."""
    for prompt in (text_input, *fallback_prompts):
        bboxes = detect_watermark_bboxes(image, prompt)
        reliable = [
            b for b in bboxes
            if _bbox_area_fraction(b, image.size) <= _MAX_BBOX_AREA_FRACTION
            and _bbox_has_plausible_shape(b, image.size)
        ]
        if reliable:
            return reliable
    return []
