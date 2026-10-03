"""Hiệu ứng chuyển động camera (Ken Burns) cho ẢNH TĨNH — mô phỏng góc nhìn/đường đi máy
quay trên 1 bức ảnh: zoom in/out, pan/tilt, roll, orbit. TÁCH RIÊNG khỏi `assembly.py`
cùng lý do với `transitions.py` (tránh import vòng `assembly.py` → `engine.py` →
`routers/pipeline.py`) + gọn theo mối quan tâm riêng.

**2026-08-19, theo yêu cầu người dùng** — chỉ áp dụng cho shot ẢNH (`Shot.visual_type
== "image"`), KHÔNG áp dụng cho video (video đã có chuyển động thật sẵn). Xem
`assembly.py::_build_segment` cho điểm nối vào pipeline ghép MP4 thật.

**Bug thật phát hiện lúc phát triển (quan trọng, quyết định thiết kế `roll`)**: ffmpeg
filter `zoompan` KHÔNG re-sample lại các filter NGƯỢC DÒNG (upstream) mỗi output frame —
nó chỉ kéo 1 input frame rồi tự sinh `d` output frame từ CHÍNH input frame đó (đúng thiết
kế gốc của zoompan: giữ 1 frame video rồi tự animate zoom/pan trên đó). Nếu đặt 1 filter
đổi theo thời gian (VD `rotate=a='...*sin(2*PI*t/...)'`) NGAY TRƯỚC `zoompan`, zoompan sẽ
"đóng băng" giá trị `t` tại thời điểm nó kéo input frame (gần như luôn là t≈0 với ảnh
tĩnh `-loop 1`, vì `d` được đặt bằng CẢ số frame output nên chỉ kéo input 1 LẦN DUY NHẤT)
— toàn bộ clip ra góc xoay gần như 0°, không có chuyển động thật dù công thức đúng.
Xác nhận bằng test thật (dựng ảnh có viền, trích frame giữa clip, xem bằng mắt — không
thấy xoay) trước khi sửa. **Fix**: `roll` KHÔNG dùng `zoompan` — dùng `rotate` (filter
per-frame bình thường, `t` cập nhật đúng mỗi frame) + `crop` TĨNH (không phải zoompan)
để cắt bỏ góc ảnh bị lộ ra khi xoay. `zoom_in`/`zoom_out`/`pan_*`/`tilt_*`/`orbit` KHÔNG
gặp vấn đề này vì chúng chỉ dùng biến nội bộ của `zoompan` (`on`, `zoom` tự tham chiếu)
— không phụ thuộc filter nào đứng trước, đúng use-case gốc của zoompan.
"""
from __future__ import annotations

import math

CAMERA_MOTIONS: dict[str, str] = {
    "none": "Không hiệu ứng (ảnh tĩnh, mặc định)",
    "zoom_in": "Phóng to (Zoom in)",
    "zoom_out": "Thu nhỏ (Zoom out)",
    "pan_left": "Trượt trái (Pan left)",
    "pan_right": "Trượt phải (Pan right)",
    "tilt_up": "Trượt lên (Tilt up)",
    "tilt_down": "Trượt xuống (Tilt down)",
    "roll": "Xoay nhẹ (Roll)",
    "orbit": "Lượn quanh chủ thể (Orbit)",
}

# Biên độ zoom cho zoom_in/zoom_out — 18% đủ để thấy rõ hiệu ứng trong vài giây mà
# không "nuốt" mất phần rìa khung hình quá nhanh (đo thật bằng mắt qua ảnh test).
_ZOOM_MIN, _ZOOM_MAX = 1.0, 1.18
# Zoom CỐ ĐỊNH khi pan/tilt — cần > 1.0 để có "biên" cho khung hình trượt qua (zoom=1.0
# thì x/y luôn phải =0, không trượt được gì).
_PAN_ZOOM = 1.18
# Góc roll tối đa mỗi hướng (độ) — nhẹ, đúng tinh thần "xoay nhẹ" chứ không phải xoay
# ngộ nghĩnh; dao động qua lại theo sin (0 → +max → 0 → -max → 0) trong suốt clip.
_ROLL_ANGLE_RAD = math.radians(3.0)
# Crop margin đủ che góc ảnh bị lộ ra khi rotate ở góc tối đa — đo thật: rotate 3° không
# crop lộ viền đen mỏng ở góc; crop 1/1.15 (≈13% margin) che sạch, xác nhận bằng ảnh test.
_ROLL_CROP_MARGIN = 1.15
# Biên độ zoom cho orbit — nhẹ hơn zoom_in vì orbit đã có chuyển động ngang/dọc riêng,
# zoom quá mạnh cộng dồn sẽ gây rối mắt.
_ORBIT_ZOOM_MIN, _ORBIT_ZOOM_MAX = 1.05, 1.22

# Phóng to ảnh gốc TRƯỚC khi zoompan/rotate — zoompan zoom theo pixel của ẢNH ĐÃ SCALE,
# ảnh gốc nhỏ mà zoom trực tiếp sẽ bị "nhảy" pixel (jitter) rõ rệt lúc phát; x2 đủ mượt
# cho biên độ zoom nhỏ (~1.2) đang dùng ở đây, không cần phóng quá lớn tốn CPU/RAM vô ích.
_UPSCALE = "scale=iw*2:ih*2"


def _cover_crop_to_target(out_w: int, out_h: int) -> str:
    """Crop-fill ảnh nguồn về ĐÚNG tỷ lệ khung xuất (`out_w:out_h`) TRƯỚC khi vào
    `zoompan`/`rotate` — **bug thật (2026-09-12), phát hiện lúc test tính năng xuất
    short-video 9:16**: `zoompan`'s tham số `s={out_w}x{out_h}` chỉ ÉP kích thước output
    CUỐI CÙNG, KHÔNG hề giữ tỷ lệ khung hình gốc — với ảnh 16:9 (project long-form) đưa
    thẳng vào rồi ép `s=1080x1920` (9:16), kết quả bị BÓP MÉO (width co mạnh, height giãn
    mạnh, nhìn như ảnh "co lại theo chiều dọc") thay vì crop 2 bên như
    `assembly.py::_scale_cover_filter` đã làm cho MỌI shot KHÔNG bật camera motion. Toàn
    bộ short-export ép `aspect_fill_mode="crop"` (mục 138) qua `_resolve_scale_filter`
    NHƯNG nhánh camera-motion này của `_build_segment` KHÔNG hề đi qua
    `_resolve_scale_filter` (`build_camera_motion_filter` tự dựng filter chain riêng) —
    override ở `short_export.py` vô tác dụng với MỌI shot có `camera_motion != "none"`
    (thực tế là ĐA SỐ shot, Ken Burns là lựa chọn phổ biến).

    Fix: cover-crop (scale-lên-rồi-cắt-thừa, CÙNG công thức `_scale_cover_filter`) đưa
    ảnh về ĐÚNG tỷ lệ `out_w:out_h` NGAY TỪ ĐẦU, trước cả `_UPSCALE` — khung `zoompan`
    animate bên trong từ đây trở đi LUÔN cùng tỷ lệ khung xuất, nên `s={out_w}x{out_h}`
    ở cuối chỉ còn là scale ĐỒNG NHẤT (không bóp méo). Vô hại/gần như no-op khi ảnh nguồn
    đã ĐÚNG tỷ lệ khung xuất (case phổ biến nhất — ảnh long-form 16:9 ghép vào video
    16:9), chỉ thật sự cắt bớt khi tỷ lệ lệch nhau (VD ảnh 16:9 ghép vào short-video 9:16
    — đúng bug này)."""
    return f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h}"


def _eased_progress(n_frames: int) -> str:
    """Tỉ lệ tiến trình 0..1 đã làm MƯỢT bằng smoothstep (3f²-2f³) thay vì tuyến tính
    thô `on/(n-1)`. **Bug thật người dùng báo (2026-08-20)**: hiệu ứng camera "hơi bị
    giật" — đo thật bằng cách dựng ảnh gradient, lấy mẫu 1 pixel cố định qua từng frame
    (không đoán): chuyển động tuyến tính (vận tốc KHÔNG ĐỔI suốt clip) khởi động/dừng
    ĐỘT NGỘT ở 2 đầu — camera thật không bao giờ bắt đầu/dừng tức thời, cảm giác máy móc.
    Smoothstep tăng tốc dần từ 0 lúc bắt đầu, giảm tốc dần về 0 lúc kết thúc — xác nhận
    lại bằng đúng phép đo pixel-per-frame: delta ở 2 đầu clip nhỏ hơn hẳn delta ở giữa
    (đúng dáng ease-in/ease-out) sau khi áp fix này, khác hẳn dáng tuyến tính đều trước đó."""
    f = f"(on/{max(1, n_frames - 1)})"
    return f"({f}*{f}*(3-2*{f}))"


def _zoom_expr(z_start: float, z_end: float, n_frames: int) -> str:
    """Hàm ĐÓNG theo `on` (không tự tham chiếu `zoom` frame trước như bản cũ) — cho
    phép áp `_eased_progress` trực tiếp; bản đệ quy `zoom+step` cũ chỉ tạo được tuyến
    tính đều, không dễ làm mượt 2 đầu."""
    return f"({z_start}+({z_end}-({z_start}))*{_eased_progress(n_frames)})"


def _linear_expr(start: str, end: str, n_frames: int) -> str:
    """Nội suy CÓ EASING (smoothstep, xem `_eased_progress`) theo `on` — KHÔNG còn
    tuyến tính đều như bản cũ (nguyên nhân "giật" đã đo thật, xem `_eased_progress`)."""
    return f"({start})+(({end})-({start}))*{_eased_progress(n_frames)}"


# Blur chuyển động TỔNG HỢP — **mới (2026-08-20)**, theo phản hồi người dùng ("vẫn bị
# giật" ngay cả sau khi thêm easing ở trên). Đo thật loại trừ hết nguyên nhân kỹ thuật
# (không duplicate frame, PTS cách đều tuyệt đối, vị trí crop tăng/giảm đơn điệu mượt) —
# camera thật KHÔNG BAO GIỜ chụp ảnh "đứng hình tuyệt đối" mỗi frame khi đang di chuyển,
# có motion blur tự nhiên; Ken Burns số hoá (mỗi frame là 1 crop SẮC NÉT tuyệt đối, không
# blur) tạo cảm giác "khựng"/rung hình dù chuyển động bên dưới hoàn toàn mượt về mặt toán
# học — hiện tượng đã biết rộng rãi khi làm Ken Burns bằng phần mềm (không riêng ffmpeg).
# `tmix` trộn TRUNG BÌNH 3 frame liên tiếp (frame hiện tại + 2 frame trước, trọng số bằng
# nhau) — mô phỏng motion blur nhẹ, xoá cảm giác "đứng hình" mà không làm mờ hẳn nội dung
# (chỉ 3 frame ở 30fps ≈ 0.1s cửa sổ blur, tự nhiên như rung tay máy quay thật).
_MOTION_BLUR = "tmix=frames=3:weights='1 1 1'"


def build_camera_motion_filter(motion: str, duration: float, out_w: int, out_h: int, fps: int) -> str | None:
    """Trả 1 đoạn filter ffmpeg (nối bằng dấu phẩy vào `-vf`, KHÔNG gồm scale cuối/màu —
    những cái đó `_build_segment` tự nối tiếp sau) áp hiệu ứng camera cho ảnh tĩnh, hoặc
    `None` nếu `motion` là "none"/không hợp lệ (giữ nguyên hành vi ảnh tĩnh cũ)."""
    if motion not in CAMERA_MOTIONS or motion == "none":
        return None
    n_frames = max(1, round(duration * fps))
    size = f"{out_w}x{out_h}"
    # Ép ảnh nguồn về ĐÚNG tỷ lệ khung xuất TRƯỚC `_UPSCALE`/`zoompan`/`rotate` — xem
    # docstring `_cover_crop_to_target` cho bug thật đã sửa (2026-09-12).
    cover_crop = _cover_crop_to_target(out_w, out_h)
    core: str

    if motion in ("zoom_in", "zoom_out"):
        z0, z1 = (_ZOOM_MIN, _ZOOM_MAX) if motion == "zoom_in" else (_ZOOM_MAX, _ZOOM_MIN)
        z_expr = _zoom_expr(z0, z1, n_frames)
        core = f"{cover_crop},{_UPSCALE},zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s={size}:fps={fps}"

    elif motion in ("pan_left", "pan_right", "tilt_up", "tilt_down"):
        z = _PAN_ZOOM
        is_horizontal = motion in ("pan_left", "pan_right")
        max_offset = f"(iw-iw/{z})" if is_horizontal else f"(ih-ih/{z})"
        reverse = motion in ("pan_left", "tilt_up")  # 2 hướng này trượt TỪ biên VỀ 0
        start, end = (max_offset, "0") if reverse else ("0", max_offset)
        moving_expr = _linear_expr(start, end, n_frames)
        centered_expr = "ih/2-(ih/zoom/2)" if is_horizontal else "iw/2-(iw/zoom/2)"
        x_expr = moving_expr if is_horizontal else centered_expr
        y_expr = centered_expr if is_horizontal else moving_expr
        core = f"{cover_crop},{_UPSCALE},zoompan=z={z}:x='{x_expr}':y='{y_expr}':d={n_frames}:s={size}:fps={fps}"

    elif motion == "roll":
        period = max(duration, 0.1)
        angle_expr = f"{_ROLL_ANGLE_RAD:.6f}*sin(2*PI*t/{period:.3f})"
        core = (
            f"{cover_crop},{_UPSCALE},rotate=a='{angle_expr}':ow=iw:oh=ih:fillcolor=black,"
            f"crop=iw/{_ROLL_CROP_MARGIN}:ih/{_ROLL_CROP_MARGIN},scale={out_w}:{out_h},fps={fps}"
        )

    elif motion == "orbit":
        # Xấp xỉ "lượn quanh chủ thể" từ 1 ảnh phẳng (không có depth thật) — kết hợp zoom
        # tăng dần + trượt CHÉO theo quỹ đạo hình tròn (sin/cos lệch pha 90°), tạo cảm
        # giác parallax/lượn nhẹ thay vì xoay 3D thật (không khả thi từ 1 ảnh tĩnh).
        z_expr = _zoom_expr(_ORBIT_ZOOM_MIN, _ORBIT_ZOOM_MAX, n_frames)
        x_expr = f"(iw-iw/zoom)*(0.5+0.5*sin(2*PI*on/{n_frames}))"
        y_expr = f"(ih-ih/zoom)*(0.5+0.5*cos(2*PI*on/{n_frames}))"
        core = f"{cover_crop},{_UPSCALE},zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={n_frames}:s={size}:fps={fps}"

    else:
        return None  # pragma: no cover — mọi key trong CAMERA_MOTIONS (trừ "none") đã xử lý ở trên

    return f"{core},{_MOTION_BLUR}"
