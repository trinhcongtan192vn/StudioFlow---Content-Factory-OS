"""Hàm cấp cao, TÁI SỬ DỤNG ĐƯỢC — dùng trực tiếp từ `asset_vault/ingest.py` (xoá
watermark video gốc, Kho Tài Nguyên) và Visual Studio (xoá watermark ảnh/video user tự
upload cho 1 shot). Xem `app/watermark/__init__.py` cho tổng quan kiến trúc (Florence-2
phát hiện + LaMa inpaint) và bằng chứng verify thật.

**Ảnh — KHÔNG dùng Florence-2, dùng vị trí tương đối CỐ ĐỊNH** (2026-09-04, bug thật #4
`detector.py`): Florence-2-base không đủ khả năng định vị icon lấp lánh TRONG SUỐT của
Gemini/Nano Banana trên nền minh hoạ chi tiết (verify thật, nhiều prompt/crop đều sai) —
`remove_watermark_from_image` dùng `detector.gemini_corner_bbox` (vị trí đã đo thật, luôn
~90%/83% chiều rộng/cao) làm mặc định thay vì AI định vị theo nội dung.

**Video — phát hiện 1 LẦN, áp cho MỌI frame** (stock footage/video tư liệu hầu hết CỐ ĐỊNH
vị trí watermark suốt clip — logo góc, dòng chữ credit... — phát hiện lại mỗi frame vừa
tốn kém vừa rủi ro giật hình nếu 1-2 frame phát hiện lệch nhau). **Phương pháp CHÍNH
(2026-09-18, theo đề xuất người dùng)**: `detector.detect_static_watermark_bbox` — đo độ
lệch chuẩn THEO THỜI GIAN của từng pixel trên nhiều frame lấy mẫu rải đều (watermark
không di chuyển, nội dung thật luôn đổi) — đáng tin hơn hẳn việc chỉ nhìn 1 frame đơn.
Không tìm được vùng đủ tin cậy (VD cảnh quay quá tĩnh) → rơi về **Florence-2** (lưới an
toàn — verify thật cho video Gemini/Veo, mục bug #2, khác hẳn watermark ẢNH ở trên đủ
tương phản để định vị được) trên 1 FRAME ĐẠI DIỆN (lấy tại 20% thời lượng — né đoạn
đầu/leader có thể đen/mờ khác thường). Dù nguồn nào, bbox tìm được dùng CHUNG cho toàn bộ
frame còn lại, vá theo LÔ (batch) qua `remover.inpaint_regions_batch_cropped` — nhanh hơn
hẳn vá tuần tự từng frame, xem docstring `remover.py` cho số đo thật."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from PIL import Image

from .detector import detect_static_watermark_bbox, detect_watermark_bboxes_robust, gemini_corner_bbox
from .remover import inpaint_regions_batch_cropped, inpaint_regions_full_frame

ProgressCallback = Callable[[int, int, str], None]

_FRAME_EXT = ".jpg"
_FRAME_QUALITY = 3  # ffmpeg -q:v (2-5 = chất lượng cao, đủ dùng cho bước trung gian, ảnh cuối re-encode lại qua libx264 nên không cần PNG lossless)
# Số frame vá watermark trong 1 lượt forward LaMa (xem `remover.py::inpaint_regions_batch_
# cropped` — đo thật trên GPU: batch=8 nhanh hơn ~4-6 lần so với gọi tuần tự từng frame vì
# crop nhỏ nên 1 lượt đơn KHÔNG tận dụng hết GPU). Vẫn có tác dụng trên CPU (giảm overhead
# Python/tận dụng song song nội bộ của thư viện BLAS/conv cho batch), chỉ ít rõ rệt hơn.
_INPAINT_BATCH_SIZE = 8


def remove_watermark_from_image(
    image_path: str, out_path: Path, *, bboxes: list[tuple[int, int, int, int]] | None = None,
) -> list[tuple[int, int, int, int]]:
    """Xoá watermark khỏi 1 ẢNH ĐƠN LẺ — dùng trực tiếp được cho Visual Studio (ảnh user
    upload cho 1 shot). `bboxes` truyền sẵn (VD UI sau này cho user tự khoanh vùng) để dùng
    ĐÚNG vùng đó thay vì mặc định — `None` = dùng `gemini_corner_bbox` (vị trí watermark
    Gemini/Nano Banana đã đo thật, xem bug thật #4 `detector.py`). Trả về bboxes ĐÃ DÙNG
    (caller có thể cache lại, VD để áp cùng bbox cho nhiều ảnh cùng nguồn).

    **KHÔNG còn dùng Florence-2 cho ảnh** (khác video, vẫn dùng `detect_watermark_bboxes_
    robust` — xem `remove_watermark_from_video`) — verify thật (bug #4) xác nhận Florence-2
    không đủ khả năng định vị icon lấp lánh TRONG SUỐT của Gemini trên nền minh hoạ chi
    tiết dù thử nhiều prompt/crop khác nhau; theo xác nhận trực tiếp của người dùng, vị trí
    TƯƠNG ĐỐI CỐ ĐỊNH đáng tin cậy hơn hẳn AI định vị theo nội dung cho đúng trường hợp này."""
    image = Image.open(image_path).convert("RGB")
    if bboxes is None:
        bboxes = [gemini_corner_bbox(image.size)]
    if not bboxes:
        raise ValueError("Không phát hiện được watermark nào trong ảnh — thử khoanh vùng tay.")
    result = inpaint_regions_full_frame(image, bboxes)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(out_path)
    return bboxes


def _probe_fps(ffprobe: str, video_path: str) -> str:
    """Trả chuỗi fps DẠNG PHÂN SỐ THẬT (VD "30000/1001") — giữ nguyên dạng phân số khi
    truyền lại cho `-r` lúc re-encode (ép về số thập phân làm tròn có thể lệch fps gốc,
    gây trôi đồng bộ audio/video trên video dài)."""
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, check=True, text=True, timeout=15,
    )
    return result.stdout.strip() or "30/1"


def _has_audio_stream(ffprobe: str, video_path: str) -> bool:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", video_path],
        capture_output=True, check=True, text=True, timeout=15,
    )
    return bool(result.stdout.strip())


def remove_watermark_from_video(
    ffmpeg: str, video_path: str, out_path: Path, tmp_dir: Path, *,
    text_input: str = "watermark",
    force_gemini: bool = False,
    on_progress: ProgressCallback | None = None,
) -> list[tuple[int, int, int, int]]:
    """Xoá watermark khỏi CẢ VIDEO — 3 giai đoạn, báo tiến trình qua `on_progress(current,
    total, label)` sau mỗi bước đáng kể (khớp pattern `ingest.py::auto_detect_scenes`):
    (1) tách toàn bộ frame ra JPG (ffmpeg, nhanh — I/O thuần, không AI), (2) phát hiện
    watermark trên 1 frame đại diện rồi vá TỪNG frame (chậm nhất — 1 lượt LaMa/frame), (3)
    ghép lại video từ frame đã vá + audio gốc (nếu có). Dọn sạch `tmp_dir` khi xong (kể cả
    khi lỗi giữa chừng, qua `finally`). Trả về bbox đã dùng (debug/log).

    `force_gemini` (2026-09-18, nút "Xoá watermark Gemini" riêng — người dùng CHỦ ĐỘNG
    xác nhận asset có watermark Gemini, bất kể `visual_provider`) — dùng THẲNG
    `gemini_corner_bbox` (vị trí tương đối cố định, cùng hàm đã verify cho ẢNH từ bug #4)
    thay vì đa-frame/Florence-2. **Đã thử "so khớp mẫu template" (lưu icon Gemini thật rồi
    `cv2.matchTemplate`) TRƯỚC KHI chọn hướng này — verify thật trên frame video THẬT của
    người dùng (nền giấy cũ nhiều chữ) cho thấy cả so khớp pixel thô lẫn bản đồ cạnh Canny
    đều khớp NHẦM vào hoạ tiết nền thay vì icon thật (điểm tự tin 0.49-0.59 nhưng SAI vị
    trí) — cùng nguyên nhân khiến Florence-2 thất bại (nền chi tiết tương phản cao hơn hẳn
    icon mờ bán trong suốt). Đo trực tiếp xác nhận `gemini_corner_bbox` VẪN chứa đúng vị
    trí icon thật trên chính frame đó — nên tái dùng hàm đã verify này thay vì thuật toán
    mới rủi ro hơn."""
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    frames_dir = tmp_dir / "wm_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    try:
        if on_progress:
            on_progress(0, 0, "Đang tách frame từ video")
        subprocess.run(
            [ffmpeg, "-y", "-i", video_path, "-q:v", str(_FRAME_QUALITY), str(frames_dir / f"frame_%06d{_FRAME_EXT}")],
            capture_output=True, check=True, text=True,
        )
        frame_paths = sorted(frames_dir.glob(f"frame_*{_FRAME_EXT}"))
        n_frames = len(frame_paths)
        if n_frames == 0:
            raise RuntimeError("Không tách được frame nào từ video (file lỗi hoặc rỗng)")

        sample_idx = max(0, min(n_frames - 1, int(n_frames * 0.2)))
        if force_gemini:
            # Người dùng đã CHẮC CHẮN đây là Gemini — dùng thẳng vị trí cố định đã verify,
            # không cần lớp phát hiện nội dung tổng quát nào (xem docstring hàm).
            sample_image = Image.open(frame_paths[sample_idx]).convert("RGB")
            bbox = gemini_corner_bbox(sample_image.size)
        else:
            # Phát hiện CHÍNH qua nhiều frame (độ lệch chuẩn theo thời gian, 2026-09-18,
            # theo đề xuất người dùng: watermark không di chuyển trong khi nội dung thật
            # luôn đổi) — xem docstring `detector.py::detect_static_watermark_bbox`. Đáng
            # tin hơn hẳn Florence-2 trên 1 frame đơn (rủi ro đoán sai lan ra CẢ video, bug
            # #1/#2). Không tìm được vùng nào đủ tin cậy → rơi về Florence-2 (lưới an toàn
            # cũ, GIỮ NGUYÊN khả năng đã có) trên 1 frame đại diện tại ~20% thời lượng —
            # né đoạn đầu có thể đen/mờ.
            bbox = detect_static_watermark_bbox(frame_paths)
            if bbox is None:
                sample_image = Image.open(frame_paths[sample_idx]).convert("RGB")
                bboxes = detect_watermark_bboxes_robust(sample_image, text_input)
                if not bboxes:
                    raise ValueError("Không phát hiện được watermark nào trong video — thử mô tả khác.")
                bbox = bboxes[0]  # 1 vùng nổi bật nhất — đa số watermark stock footage chỉ có 1 logo/dòng chữ cố định

        if on_progress:
            on_progress(0, n_frames, f"Đang xoá watermark 0/{n_frames} frame")
        for chunk_start in range(0, n_frames, _INPAINT_BATCH_SIZE):
            chunk_paths = frame_paths[chunk_start : chunk_start + _INPAINT_BATCH_SIZE]
            images = [Image.open(p).convert("RGB") for p in chunk_paths]
            patched = inpaint_regions_batch_cropped(images, bbox)
            for frame_path, patched_image in zip(chunk_paths, patched):
                patched_image.save(frame_path, quality=90)
            done = chunk_start + len(chunk_paths)
            if on_progress:
                on_progress(done, n_frames, f"Đang xoá watermark {done}/{n_frames} frame")

        if on_progress:
            on_progress(n_frames, n_frames, "Đang ghép lại video")
        fps = _probe_fps(ffprobe, video_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [ffmpeg, "-y", "-r", fps, "-i", str(frames_dir / f"frame_%06d{_FRAME_EXT}")]
        has_audio = _has_audio_stream(ffprobe, video_path)
        if has_audio:
            cmd += ["-i", video_path, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "copy", "-shortest"]
        cmd += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out_path)]
        subprocess.run(cmd, capture_output=True, check=True, text=True)
        return [bbox]
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)
