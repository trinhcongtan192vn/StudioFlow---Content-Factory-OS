"""Module xoá watermark (app/watermark/) — Florence-2 (detect) + LaMa (inpaint), xem
docstring `app/watermark/__init__.py` cho bằng chứng verify thật (dựng ảnh/video test
tổng hợp, xác nhận bbox đúng + kết quả liền mạch bằng mắt, KHÔNG suy đoán). Model THẬT
(~90s nạp lần đầu) quá chậm để chạy trong test suite tự động mỗi lần commit — test ở đây
MOCK `detect_watermark_bboxes`/`inpaint_*` (giữ nguyên logic điều phối: cắt frame, gọi
đúng thứ tự, cập nhật DB, dọn file tạm, xử lý lỗi) bằng hàm giả NHANH, tương tự cách
Vision/Embedding provider được mock qua `respx` ở `test_asset_vault.py` — model thật đã
verify tay riêng, không lặp lại ở đây.

**Bug thật bắt được lúc verify tay (2026-08-27, ghi lại làm bài học)**: prompt mặc định
ban đầu `"watermark, logo, text overlay"` (nhiều khái niệm) làm Florence-2 trả bbox SAI
(nguyên cả khung hình) — hạ về `"watermark"` (1 từ đơn) mới đúng, xem docstring
`detector.py::detect_watermark_bboxes`.

**Bug thật #2 (2026-08-28, user báo video Gemini/Veo "mất hình ảnh" sau khi xoá
watermark)** — ngay cả 1 từ đơn `"watermark"` VẪN có thể trả bbox GẦN NHƯ FULL-FRAME cho
watermark dạng icon nhỏ (VD sparkle icon của Gemini/Veo) — LaMa vá gần hết khung hình =
phá huỷ nội dung gốc. Fix: `detect_watermark_bboxes_robust` (lọc bbox quá lớn + tự thử
prompt dự phòng) — pipeline giờ gọi hàm NÀY thay vì `detect_watermark_bboxes` trực tiếp,
xem `test_detect_watermark_bboxes_robust_*` bên dưới cho test riêng của bản vá này.

**Bug thật #3+#4 (2026-09-04, user báo ảnh minh hoạ không xoá được logo Gemini góc dưới
phải)** — #3: bbox lọt ngưỡng diện tích nhưng sai HÌNH DẠNG (dải dọc gần trọn chiều cao),
fix bằng `_bbox_has_plausible_shape`. #4: verify thật bằng Florence-2 THẬT trên ảnh lỗi của
user xác nhận model KHÔNG đủ khả năng định vị icon lấp lánh trong suốt của Gemini trên nền
minh hoạ chi tiết dù thử 8+ prompt — theo xác nhận của user, ẢNH giờ dùng thẳng
`detector.gemini_corner_bbox` (vị trí tương đối cố định đã đo thật) thay vì Florence-2,
xem `test_remove_watermark_from_image_uses_gemini_corner_bbox_by_default` và
`test_gemini_corner_bbox_*` bên dưới."""
from __future__ import annotations

import shutil
import subprocess

import pytest
from PIL import Image

from app.watermark import detector as wm_detector
from app.watermark import pipeline as wm_pipeline


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    assert path, "cần ffmpeg thật trên PATH"
    return path


def _fake_detect(image, text_input="watermark"):
    """Trả 1 bbox CỐ ĐỊNH ở góc dưới phải — không cần load Florence-2 thật."""
    w, h = image.size
    return [(w - 100, h - 40, w - 10, h - 10)]


def _fake_inpaint_batch_cropped(images, bbox, pad=6, context_pad=40):
    """Không chạy LaMa thật — chỉ vẽ đè màu xám lên vùng bbox để CHỨNG MINH hàm ĐÃ được
    gọi đúng vùng (verify qua đọc lại pixel), nhanh hơn hẳn model thật. Ký hiệu khớp bản
    BATCH (`remover.py::inpaint_regions_batch_cropped`, thay cho `inpaint_region_cropped`
    tuần tự cũ — xem lý do tăng tốc ở docstring module đó) — nhận/trả LIST ảnh."""
    from PIL import ImageDraw

    results = []
    for image in images:
        result = image.copy()
        draw = ImageDraw.Draw(result)
        x1, y1, x2, y2 = bbox
        draw.rectangle([x1, y1, x2, y2], fill=(128, 128, 128))
        results.append(result)
    return results


def _fake_inpaint_full(image, bboxes, pad=6):
    from PIL import ImageDraw

    result = image.copy()
    draw = ImageDraw.Draw(result)
    for x1, y1, x2, y2 in bboxes:
        draw.rectangle([x1, y1, x2, y2], fill=(128, 128, 128))
    return result


def test_remove_watermark_from_image_uses_gemini_corner_bbox_by_default(monkeypatch, tmp_path):
    """Bug thật #4 (2026-09-04) — ảnh KHÔNG còn qua Florence-2, dùng thẳng
    `gemini_corner_bbox` (vị trí tương đối cố định đã đo thật) làm bbox mặc định."""
    def _boom(*a, **k):
        raise AssertionError("ảnh không còn gọi Florence-2 detect nữa (bug thật #4)")

    monkeypatch.setattr(wm_pipeline, "detect_watermark_bboxes_robust", _boom)
    monkeypatch.setattr(wm_pipeline, "inpaint_regions_full_frame", _fake_inpaint_full)

    src = tmp_path / "in.png"
    Image.new("RGB", (200, 150), (10, 20, 30)).save(src)
    out_path = tmp_path / "out.png"

    bboxes = wm_pipeline.remove_watermark_from_image(str(src), out_path)
    assert bboxes == [wm_detector.gemini_corner_bbox((200, 150))]
    assert out_path.exists()
    result = Image.open(out_path)
    x1, y1, x2, y2 = bboxes[0]
    assert result.getpixel((x1 + 1, y1 + 1)) == (128, 128, 128)  # vùng bbox đã bị "vá" (giả lập)
    assert result.getpixel((5, 5)) == (10, 20, 30)  # ngoài bbox giữ nguyên


def test_remove_watermark_from_image_uses_provided_bboxes_instead_of_default(monkeypatch, tmp_path):
    """`bboxes` truyền tay → dùng ĐÚNG vùng đó thay vì `gemini_corner_bbox` mặc định (dành
    cho UI khoanh vùng tay sau này, xem docstring hàm)."""
    monkeypatch.setattr(wm_pipeline, "inpaint_regions_full_frame", _fake_inpaint_full)

    src = tmp_path / "in.png"
    Image.new("RGB", (200, 150), (10, 20, 30)).save(src)
    out_path = tmp_path / "out.png"
    bboxes = wm_pipeline.remove_watermark_from_image(str(src), out_path, bboxes=[(0, 0, 10, 10)])
    assert bboxes == [(0, 0, 10, 10)]


def test_remove_watermark_from_image_raises_when_bboxes_explicitly_empty(tmp_path):
    src = tmp_path / "in.png"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(src)
    with pytest.raises(ValueError):
        wm_pipeline.remove_watermark_from_image(str(src), tmp_path / "out.png", bboxes=[])


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_remove_watermark_from_video_processes_all_frames_and_reports_progress(monkeypatch, tmp_path):
    monkeypatch.setattr(wm_pipeline, "detect_watermark_bboxes_robust", _fake_detect)
    monkeypatch.setattr(wm_pipeline, "inpaint_regions_batch_cropped", _fake_inpaint_batch_cropped)

    ffmpeg = _ffmpeg()
    video_path = tmp_path / "in.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1:r=5", "-pix_fmt", "yuv420p", str(video_path)],
        capture_output=True, check=True, text=True,
    )
    out_path = tmp_path / "out.mp4"
    tmp_dir = tmp_path / "wm_tmp"
    progress_snapshots = []
    bboxes = wm_pipeline.remove_watermark_from_video(
        ffmpeg, str(video_path), out_path, tmp_dir,
        on_progress=lambda cur, total, label: progress_snapshots.append((cur, total)),
    )
    assert bboxes == [(220, 200, 310, 230)]
    assert out_path.exists()
    assert progress_snapshots[-1] == (5, 5)  # 5 frame (1s @ 5fps) — snapshot cuối phải khớp current=total
    assert not tmp_dir.joinpath("wm_frames").exists()  # dọn sạch frame tạm sau khi xong


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_remove_watermark_from_video_force_gemini_uses_corner_bbox(monkeypatch, tmp_path):
    """Bug thật (2026-09-19, user báo lỗi khi bấm 'Xoá watermark Gemini' cho shot video):
    `UnboundLocalError: cannot access local variable 'bboxes'` — hàm trả `return bboxes`
    nhưng biến đó CHỈ được gán trong nhánh dự phòng Florence-2 (mục 148), trong khi nhánh
    `force_gemini`/`detect_static_watermark_bbox` thành công chỉ gán `bbox` (số ít). Test
    này gọi THẬT (không mock `detect_static_watermark_bbox`/`gemini_corner_bbox`, chỉ mock
    bước vá LaMa) với `force_gemini=True` để bắt lại đúng lớp lỗi này nếu tái diễn."""
    monkeypatch.setattr(wm_pipeline, "inpaint_regions_batch_cropped", _fake_inpaint_batch_cropped)

    ffmpeg = _ffmpeg()
    video_path = tmp_path / "in.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=1:r=5", "-pix_fmt", "yuv420p", str(video_path)],
        capture_output=True, check=True, text=True,
    )
    out_path = tmp_path / "out.mp4"
    tmp_dir = tmp_path / "wm_tmp"
    bboxes = wm_pipeline.remove_watermark_from_video(ffmpeg, str(video_path), out_path, tmp_dir, force_gemini=True)
    assert bboxes == [wm_detector.gemini_corner_bbox((320, 240))]
    assert out_path.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_remove_watermark_from_video_cleans_up_tmp_dir_on_detection_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(wm_pipeline, "detect_watermark_bboxes_robust", lambda image, text_input="watermark": [])

    ffmpeg = _ffmpeg()
    video_path = tmp_path / "in.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1:r=5", "-pix_fmt", "yuv420p", str(video_path)],
        capture_output=True, check=True, text=True,
    )
    tmp_dir = tmp_path / "wm_tmp"
    with pytest.raises(ValueError):
        wm_pipeline.remove_watermark_from_video(ffmpeg, str(video_path), tmp_path / "out.mp4", tmp_dir)
    assert not tmp_dir.joinpath("wm_frames").exists()


# ---------------------------------------------------------------------------
# detect_watermark_bboxes_robust (2026-08-28, bug thật #2 ở docstring module) — test
# TRỰC TIẾP logic lọc bbox quá lớn + tự thử prompt dự phòng, mock `detect_watermark_bboxes`
# (hàm gọi model thật, cấp thấp) bằng bảng tra theo prompt để mô phỏng đúng tình huống lỗi
# thật đã đo trên video Gemini/Veo (prompt chính trả full-frame, prompt dự phòng mới đúng).
# ---------------------------------------------------------------------------
_FRAME_SIZE = (1280, 720)  # khớp kích thước frame thật đã dùng để đo bug


def _fake_detect_by_prompt(responses: dict[str, list[tuple[int, int, int, int]]]):
    def _fake(image, text_input="watermark"):
        return responses.get(text_input, [])
    return _fake


class _FakeImage:
    size = _FRAME_SIZE


def test_detect_watermark_bboxes_robust_rejects_near_full_frame_bbox(monkeypatch):
    """Mô phỏng ĐÚNG bug thật: prompt chính trả bbox 99.6% diện tích (như đo được trên
    `raw_1788341279704_L3B01.mp4`) — phải bị LOẠI, không được coi là watermark hợp lệ."""
    monkeypatch.setattr(wm_detector, "detect_watermark_bboxes", _fake_detect_by_prompt({
        "watermark": [(1, 0, 1278, 719)],  # 99.6% diện tích — bbox THẬT đo được, sai
    }))
    result = wm_detector.detect_watermark_bboxes_robust(_FakeImage(), "watermark", fallback_prompts=())
    assert result == []


def test_detect_watermark_bboxes_robust_falls_back_to_smaller_prompt(monkeypatch):
    """Prompt chính SAI (full-frame), prompt dự phòng ĐÚNG (bbox nhỏ, khít icon thật) —
    phải tự chuyển sang dùng kết quả của prompt dự phòng, không dừng lại ở kết quả rỗng."""
    small_bbox = (1130, 571, 1191, 629)  # bbox THẬT đo được với prompt "star icon"
    monkeypatch.setattr(wm_detector, "detect_watermark_bboxes", _fake_detect_by_prompt({
        "watermark": [(1, 0, 1278, 719)],
        "logo": [(172, 169, 1159, 624)],  # cũng sai (78% diện tích) — bbox THẬT đo được
        "small icon in the corner": [small_bbox],
    }))
    result = wm_detector.detect_watermark_bboxes_robust(_FakeImage(), "watermark")
    assert result == [small_bbox]


def test_detect_watermark_bboxes_robust_returns_empty_when_all_prompts_unreliable(monkeypatch):
    monkeypatch.setattr(wm_detector, "detect_watermark_bboxes", _fake_detect_by_prompt({
        "watermark": [(1, 0, 1278, 719)],
        "logo": [(172, 169, 1159, 624)],
        "small icon in the corner": [],
    }))
    assert wm_detector.detect_watermark_bboxes_robust(_FakeImage(), "watermark") == []


def test_detect_watermark_bboxes_robust_accepts_normal_bbox_from_primary_prompt(monkeypatch):
    """Trường hợp bình thường (watermark chữ/logo cỡ vừa, như video test tổng hợp trước
    đây) — prompt chính ĐÃ đủ tin cậy, KHÔNG cần thử prompt dự phòng."""
    normal_bbox = (1080, 640, 1260, 700)  # ~9.7% diện tích — hợp lý cho 1 dòng chữ credit góc dưới

    def _boom(image, text_input="watermark"):
        raise AssertionError(f"không nên thử prompt dự phòng '{text_input}' khi prompt chính đã đủ tin cậy")

    def _primary(image, text_input="watermark"):
        if text_input == "watermark":
            return [normal_bbox]
        return _boom(image, text_input)

    monkeypatch.setattr(wm_detector, "detect_watermark_bboxes", _primary)
    result = wm_detector.detect_watermark_bboxes_robust(_FakeImage(), "watermark")
    assert result == [normal_bbox]


# ---------------------------------------------------------------------------
# Bug thật #3 (2026-09-04, user báo ảnh minh hoạ vẽ tay không xoá được logo Gemini góc dưới
# phải, project "p" kênh "t") — bbox chỉ chiếm ~31% DIỆN TÍCH (LỌT ngưỡng
# `_MAX_BBOX_AREA_FRACTION=0.35`) nhưng trải GẦN TRỌN CHIỀU CAO khung hình, đo trực tiếp
# trên `B01_nowm.png` thật của user (phân tích độ nét theo cột: vùng bị LaMa làm mờ là 1
# dải DỌC bên phải ảnh). Fix: `_bbox_has_plausible_shape` — xem docstring `detector.py`.
# ---------------------------------------------------------------------------
_ILLUSTRATION_SIZE = (2752, 1536)  # khớp kích thước ảnh thật đã đo bug


def test_detect_watermark_bboxes_robust_rejects_full_height_vertical_strip(monkeypatch):
    """Bbox THẬT đo được (dải dọc bên phải, ~31% diện tích nhưng gần trọn chiều cao) phải bị
    loại dù dưới ngưỡng diện tích — không khớp dạng icon gọn lẫn dạng dải mỏng hợp lệ."""
    bad_bbox = (1602, 0, 2452, 1536)  # ~31% diện tích, height fraction = 100%
    monkeypatch.setattr(wm_detector, "detect_watermark_bboxes", _fake_detect_by_prompt({
        "watermark": [bad_bbox],
    }))
    fake_image = type("_FakeImage", (), {"size": _ILLUSTRATION_SIZE})()
    result = wm_detector.detect_watermark_bboxes_robust(fake_image, "watermark", fallback_prompts=())
    assert result == []


def test_detect_watermark_bboxes_robust_falls_back_when_primary_bbox_is_wrong_shape(monkeypatch):
    """Prompt chính trả dải dọc sai hình dạng, prompt dự phòng trả đúng icon Gemini góc dưới
    phải (gọn, nhỏ) — phải tự chuyển sang dùng bbox của prompt dự phòng."""
    bad_bbox = (1602, 0, 2452, 1536)
    corner_icon = (2600, 1400, 2720, 1500)  # icon gọn, góc dưới phải — khớp mô tả "logo Gemini"
    monkeypatch.setattr(wm_detector, "detect_watermark_bboxes", _fake_detect_by_prompt({
        "watermark": [bad_bbox],
        "logo": [corner_icon],
    }))
    fake_image = type("_FakeImage", (), {"size": _ILLUSTRATION_SIZE})()
    result = wm_detector.detect_watermark_bboxes_robust(fake_image, "watermark")
    assert result == [corner_icon]


def test_detect_watermark_bboxes_robust_accepts_full_width_thin_band():
    """Dải chữ credit chạy dọc 1 cạnh (gần hết chiều rộng nhưng MỎNG theo chiều cao) vẫn là
    dạng hợp lệ — không bị heuristic hình dạng mới loại nhầm."""
    thin_band = (0, 650, 1280, 720)  # 100% width, ~9.7% height
    assert wm_detector._bbox_has_plausible_shape(thin_band, _FRAME_SIZE) is True


# ---------------------------------------------------------------------------
# gemini_corner_bbox (bug thật #4, 2026-09-04) — khoá lại vị trí đã đo THẬT trên 2 ảnh của
# user (B01_nowm.png 2752x1536, B02_nowm.png 2816x1536) để tránh lệch nếu sau này có ai vô
# tình sửa `_GEMINI_CORNER_CENTER`/`_GEMINI_CORNER_HALF_SIZE` mà không verify lại bằng ảnh
# thật — bbox trả về PHẢI bao trọn vùng icon thật đã đo bằng lưới toạ độ chồng ảnh.
#
# Bug thật #5 (2026-09-04, tiếp #4) — user báo TIẾP shot B02 (ảnh test MỚI) không xoá được
# watermark dù đã qua vùng vá cố định: verify trực tiếp xác nhận vùng vá cũ (half-size 4.5%/
# 5.5%) đặt ĐÚNG vị trí nhưng icon lượt sinh này to/lệch hơn 1 chút, tràn ra ngoài biên vùng
# vá — tăng half-size lên (7%, 9%), khoá lại bằng `test_gemini_corner_bbox_has_generous_
# margin_after_bug5` bên dưới để không ai vô tình thu hẹp lại.
# ---------------------------------------------------------------------------
def test_gemini_corner_bbox_covers_measured_icon_on_b02():
    measured_icon = (2470, 1220, 2600, 1330)  # đo thật trên B02_nowm.png (2816x1536)
    x1, y1, x2, y2 = wm_detector.gemini_corner_bbox((2816, 1536))
    mx1, my1, mx2, my2 = measured_icon
    assert x1 <= mx1 and y1 <= my1 and x2 >= mx2 and y2 >= my2


def test_gemini_corner_bbox_is_relative_not_absolute():
    """Vị trí phải theo TỈ LỆ % khung hình, không phải toạ độ pixel tuyệt đối — 2 ảnh khác
    kích thước phải cho bbox ở tâm tương đối GIỐNG NHAU, không phải cùng toạ độ pixel."""
    box_a = wm_detector.gemini_corner_bbox((2816, 1536))
    box_b = wm_detector.gemini_corner_bbox((1408, 768))  # nửa kích thước
    cx_a = ((box_a[0] + box_a[2]) / 2) / 2816
    cx_b = ((box_b[0] + box_b[2]) / 2) / 1408
    cy_a = ((box_a[1] + box_a[3]) / 2) / 1536
    cy_b = ((box_b[1] + box_b[3]) / 2) / 768
    assert abs(cx_a - cx_b) < 0.01
    assert abs(cy_a - cy_b) < 0.01


def test_gemini_corner_bbox_is_small_relative_to_frame():
    """Vùng phủ phải NHỎ (an toàn, không rủi ro phá huỷ nội dung như bug #1/#2) — dưới 5%
    diện tích khung hình dù đã có biên an toàn rộng rãi quanh icon thật (bug #5)."""
    w, h = 2816, 1536
    x1, y1, x2, y2 = wm_detector.gemini_corner_bbox((w, h))
    area_fraction = (x2 - x1) * (y2 - y1) / (w * h)
    assert area_fraction < 0.05


def test_gemini_corner_bbox_has_generous_margin_after_bug5():
    """Bug thật #5 — vùng vá cũ (half-size 4.5%/5.5%) từng bị icon lượt sinh khác tràn ra
    ngoài biên; khoá lại half-size hiện tại đủ RỘNG hơn hẳn bản cũ, không để ai vô tình thu
    hẹp lại về mức đã biết là không đủ."""
    w, h = 2816, 1536
    x1, y1, x2, y2 = wm_detector.gemini_corner_bbox((w, h))
    width_fraction, height_fraction = (x2 - x1) / w, (y2 - y1) / h
    assert width_fraction >= 0.13  # 2x half-size = 0.14, chừa chút dung sai làm tròn pixel
    assert height_fraction >= 0.17  # 2x half-size = 0.18


# ---------------------------------------------------------------------------
# detect_static_watermark_bbox — phát hiện video qua ĐỘ LỆCH CHUẨN THEO THỜI GIAN trên
# nhiều frame (2026-09-18, theo đề xuất người dùng: "cần ít nhất 2 ảnh rồi so khớp mảng
# pixel giống hệt nhau giữa các frame" — watermark không di chuyển, nội dung thật luôn
# đổi). Test THUẦN thống kê — KHÔNG cần Florence-2/LaMa/GPU, dựng frame tổng hợp bằng
# numpy/PIL trực tiếp trên đĩa (không cần ffmpeg thật).
# ---------------------------------------------------------------------------
def _make_synthetic_frames(tmp_path, n=30, wm_box=None, wm_alpha=1.0, seed=42):
    """Dựng `n` frame JPG giả — nền NHIỄU + TRÔI DẦN mỗi frame (mô phỏng nội dung thật
    luôn đổi qua thời gian), cộng thêm 1 vùng `wm_box` giữ NGUYÊN qua alpha-blend với hệ
    số `wm_alpha` (1.0 = watermark ĐẶC hoàn toàn tĩnh, <1.0 = BÁN TRONG SUỐT — giá trị vùng
    đó vẫn đổi theo nền bên dưới nhưng đổi ÍT HƠN hẳn phần còn lại). `wm_box=None` = không
    có watermark nào (case âm)."""
    import numpy as np
    from PIL import Image as PILImage

    w, h = 640, 480
    rng = np.random.default_rng(seed)
    paths = []
    for i in range(n):
        bg = rng.integers(0, 255, size=(h, w), dtype=np.uint8).astype(np.float32)
        drift = np.linspace(0, 60, w) + i * 4
        bg = np.clip(bg * 0.3 + drift[None, :], 0, 255)
        if wm_box is not None:
            x1, y1, x2, y2 = wm_box
            overlay = 230.0
            region = bg[y1:y2, x1:x2]
            bg[y1:y2, x1:x2] = region * (1 - wm_alpha) + overlay * wm_alpha
        arr = np.clip(bg, 0, 255).astype(np.uint8)
        img = PILImage.fromarray(arr, mode="L").convert("RGB")
        p = tmp_path / f"frame_{i:04d}.jpg"
        img.save(p, quality=95)
        paths.append(p)
    return paths


def test_detect_static_watermark_bbox_finds_opaque_watermark(tmp_path):
    wm_box = (560, 400, 620, 450)  # gần góc dưới-phải, khớp quy ước đặt watermark thật
    paths = _make_synthetic_frames(tmp_path, wm_box=wm_box, wm_alpha=1.0)
    result = wm_detector.detect_static_watermark_bbox(paths)
    assert result == wm_box


def test_detect_static_watermark_bbox_finds_translucent_watermark(tmp_path):
    """Watermark BÁN TRONG SUỐT (alpha-blend, giá trị pixel VẪN đổi theo nền bên dưới,
    không giống hệt tuyệt đối giữa các frame) — vẫn phải phát hiện được qua ngưỡng
    percentile (không cần pixel giống hệt nhau 100%, chỉ cần lệch chuẩn THẤP HƠN hẳn phần
    còn lại của khung hình)."""
    wm_box = (555, 395, 620, 452)
    paths = _make_synthetic_frames(tmp_path, wm_box=wm_box, wm_alpha=0.45)
    result = wm_detector.detect_static_watermark_bbox(paths)
    assert result == wm_box


def test_detect_static_watermark_bbox_returns_none_when_nothing_static(tmp_path):
    """Không có watermark nào (toàn khung hình đều đổi liên tục) — trả `None`, để caller
    (`pipeline.py::remove_watermark_from_video`) tự rơi về Florence-2."""
    paths = _make_synthetic_frames(tmp_path, wm_box=None)
    result = wm_detector.detect_static_watermark_bbox(paths)
    assert result is None


def test_detect_static_watermark_bbox_returns_none_for_too_few_frames(tmp_path):
    paths = _make_synthetic_frames(tmp_path, n=1, wm_box=(560, 400, 620, 450))
    assert wm_detector.detect_static_watermark_bbox(paths) is None
