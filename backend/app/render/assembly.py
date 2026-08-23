"""Ghép các asset đã duyệt (human review) thành 1 video hoàn chỉnh — M2 Production
Layer, bước cuối cùng của `/render`. Gọi ffmpeg qua subprocess (yêu cầu cài ffmpeg
trên PATH máy chạy backend — xem README.md, KHÔNG bundle binary ở đợt này).

Vẫn giữ nguyên tắc tách biệt: chỉ đọc `pack.json` (thứ tự shot theo timestamp,
duration mỗi beat) + `render.json` (đường dẫn asset đã sinh) — không sửa pack.json.

**Cấu hình export** (độ phân giải/codec/chất lượng — giống hộp thoại export của phần
mềm edit video): chọn được vì test thật xác nhận ffmpeg trên máy có đủ encoder
(libx264/libx265/libvpx-vp9). Dùng CRF (constant quality) thay vì bitrate cố định —
đúng thực hành hiện tại cho xuất VOD, người dùng chỉ cần chọn 1 trong 3 mức thay vì
đoán số bitrate.

**Tiến trình**: theo dõi ở granularity segment (1 shot = 1 lần gọi ffmpeg riêng) —
không parse `ffmpeg -progress` theo frame (phức tạp hơn nhiều để đổi lấy lợi ích nhỏ,
vì mỗi segment vốn đã ngắn/nhanh); ghi `assembly_progress` + `assembly_started_at` vào
render.json sau mỗi segment để frontend poll hiện % và ước lượng thời gian còn lại.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.config import project_dir
from app.db import SessionLocal
from app.filestore import read_json
from app.models import Project
from app.render.camera_motion import build_camera_motion_filter
from app.render.engine import _find_beat, _load_brand_profile, _probe_audio_duration_sec, load_render_state, save_render_state
from app.render.bg_music import resolve_bg_music_source as _resolve_bg_music_source
from app.render.intro import intro_duration_sec as _intro_duration_sec, resolve_intro_source as _resolve_intro_source
from app.render.overlay import resolve_overlay_source as _resolve_overlay_source
from app.render.schemas import AssemblyProgress, ShotRenderStatus
from app.render.transitions import TRANSITIONS
from app.timeutil import vn_isoformat

DEFAULT_BEAT_DURATION_SEC = 5.0

# Sample rate/số kênh CHUẨN chung cho MỌI audio re-encode trong pipeline — **mới
# (2026-08-21)**. Bug thật: narration từ provider OmniVoice xuất ra 24kHz MONO (khác hẳn
# 44.1kHz STEREO dùng xuyên suốt phần còn lại của app — anullsrc câm, video thương hiệu
# người dùng upload, nhạc nền). Trước đây MỌI điểm `-c:a audio_codec` chỉ khai tên codec,
# không ép sample rate/kênh — ffmpeg encode theo ĐÚNG định dạng của input, nên 1 segment
# 24kHz mono lọt vào giữa các segment 44.1kHz stereo (VD shot dùng narration OmniVoice
# xen giữa các shot khác/intro chuẩn) làm audio bị HỎNG/MẤT hẳn khi qua `_xfade_chain`
# (acrossfade)/`_mix_bg_music` (amix) — đã tái hiện + xác nhận thật bằng ffprobe trên
# chính project người dùng báo lỗi (`n_samples: 0` từ đúng điểm audio 24kHz mono trộn
# vào), KHÔNG suy đoán — xem IMPLEMENTATION_REPORT.md mục 57. Ép NGAY tại MỌI điểm
# encode audio (không chỉ chỗ gần narration nhất) — an toàn trước MỌI provider TTS
# tương lai xuất sample rate/kênh khác lạ, không riêng OmniVoice.
_AUDIO_FORMAT_FLAGS = ["-ar", "44100", "-ac", "2"]


def _scale_cover_filter(resolution: str) -> str:
    """`scale=...:force_original_aspect_ratio=increase,crop=...,setsar=1` — **mới
    (2026-08-21)**, thay cho `scale={resolution}` trần trước đây (KÉO GIÃN không đều nếu
    input lệch tỷ lệ so với target, làm méo hình). "Cover crop": scale lên đủ để PHỦ KÍN
    khung target theo đúng tỷ lệ gốc, rồi crop bớt viền thừa CĂN GIỮA — không bao giờ méo
    hình, đổi lại có thể mất 1 phần rìa ảnh nếu input lệch tỷ lệ nhiều. Áp dụng CHO CẢ
    long-form (16:9) lẫn short-form (9:16) — quan trọng hơn hẳn với short-form vì
    `image_gemini.py`/`video_flux.py` không kiểm soát được kích thước output, có thể trả
    về ảnh/video lệch hẳn 9:16 nếu chỉ dựa vào gợi ý prompt (xem 2 file đó). `crop=
    {resolution}` tận dụng ĐÚNG cú pháp "W:H" đã có sẵn của `resolution` — khớp luôn cú
    pháp `crop=W:H` của ffmpeg (mặc định crop CĂN GIỮA khi không truyền x/y).

    **Bug thật (2026-08-22)**: `scale=...force_original_aspect_ratio=increase` khi tỷ lệ
    input KHÔNG khớp CHÍNH XÁC tỷ lệ target (VD ảnh SDXL dọc 768x1344 = tỷ lệ 4:7 ≈
    0.5714, khác 9:16 = 0.5625 của short-form) buộc phải làm tròn 1 chiều về số nguyên —
    ffmpeg TỰ ĐỘNG gán 1 SAR (sample aspect ratio) bù trừ cho phần lẻ đó (VD `10240:10239`,
    `7680:7679` — gần 1:1 nhưng KHÔNG PHẢI 1:1, và khác nhau tuỳ mức lệch tỷ lệ của TỪNG
    input) thay vì để nguyên SAR mặc định. Khi ghép intro (dựng từ video thương hiệu 16:9
    gốc, lệch tỷ lệ khác) với thân video (dựng từ ảnh 4:7) qua filter `concat`
    (`_concat_intro_and_body`), 2 SAR gần-1:1-nhưng-khác-nhau này làm `concat` từ chối
    thẳng: `"Input link ... parameters (size 1080x1920, SAR 0:1) do not match ... output
    link ... (1080x1920, SAR 10240:10239)"` — kích thước PIXEL giống hệt nhau nhưng SAR
    lệch vẫn đủ làm ghép thất bại hoàn toàn (assembly_status="error", không ra video).
    Tái hiện + xác nhận bằng ffmpeg thật trước khi fix (không suy đoán) — `setsar=1` ép
    CỐ ĐỊNH sample aspect ratio về 1:1 (pixel vuông chuẩn) ở CUỐI filter chain, xoá bỏ mọi
    SAR bù trừ tự động của `scale`, đảm bảo MỌI segment/intro LUÔN cùng 1 SAR bất kể input
    gốc lệch tỷ lệ bao nhiêu."""
    return f"scale={resolution}:force_original_aspect_ratio=increase,crop={resolution},setsar=1"

Resolution = Literal["720p", "1080p", "4k"]
Codec = Literal["h264", "h265", "vp9"]
Quality = Literal["low", "medium", "high"]

RESOLUTION_MAP: dict[Resolution, str] = {
    "720p": "1280:720",
    "1080p": "1920:1080",
    "4k": "3840:2160",
}

# Khung DỌC 9:16 — mới (2026-08-21), theo yêu cầu người dùng: project short-form
# (YouTube Shorts/TikTok, `Project.format=="short"`) ghép MP4 theo tỷ lệ này thay vì
# `RESOLUTION_MAP` (16:9 ngang, dùng cho long-form). Cùng 3 mức chất lượng "720p"/
# "1080p"/"4k" — chỉ đổi CHIỀU (W↔H), không phải tuỳ chọn riêng, giữ UI export đơn giản
# (`app/routers/render.py::AssembleBody`, `frontend/RenderStudio.tsx`).
RESOLUTION_MAP_VERTICAL: dict[Resolution, str] = {
    "720p": "720:1280",
    "1080p": "1080:1920",
    "4k": "2160:3840",
}

# (video_encoder, audio_encoder, đuôi file/container) — vp9 đi kèm webm+opus (đúng cặp
# chuẩn, mp4 không hỗ trợ vp9 rộng rãi); h264/h265 dùng chung container mp4 (tương
# thích YouTube + hầu hết trình phát).
CODEC_MAP: dict[Codec, tuple[str, str, str]] = {
    "h264": ("libx264", "aac", "mp4"),
    "h265": ("libx265", "aac", "mp4"),
    "vp9": ("libvpx-vp9", "libopus", "webm"),
}

# CRF thấp hơn = chất lượng cao hơn/file nặng hơn. Thang CRF KHÁC NHAU giữa các codec
# (không dùng chung 1 con số) — H.265 "tương đương chất lượng" H.264 thường thấp hơn
# ~4-6 đơn vị, VP9 lại có thang riêng cao hơn hẳn — xem ffmpeg.org/documentation.
CRF_TABLE: dict[Codec, dict[Quality, int]] = {
    "h264": {"low": 28, "medium": 23, "high": 18},
    "h265": {"low": 32, "medium": 28, "high": 22},
    "vp9": {"low": 36, "medium": 31, "high": 24},
}

# Mã hoá bằng GPU (NVENC) — **mới (2026-08-17)**, theo yêu cầu người dùng vì mã hoá
# CPU (libx264/libx265) "có vẻ lâu". CHỈ đổi ENCODER cuối (bước tốn CPU nặng nhất), filter
# chain (scale/color-grade/fps) vẫn chạy CPU như cũ — không cần dựng lại pipeline
# CUDA decode/filter đầy đủ, đổi encoder thôi đã giảm hẳn tải CPU vì encode H.264/H.265
# software vốn là phần nặng nhất trong cả chuỗi. Chỉ hỗ trợ H.264/H.265 (`h264_nvenc`/
# `hevc_nvenc`) — ffmpeg KHÔNG có `vp9_nvenc` (xác nhận thật bằng `ffmpeg -encoders`).
_GPU_ENCODER_MAP: dict[Codec, str] = {
    "h264": "h264_nvenc",
    "h265": "hevc_nvenc",
}


def resolve_video_codec(codec: Codec, use_gpu: bool) -> str:
    """Trả tên encoder ffmpeg thật sự dùng — tách riêng để router validate được NGAY
    (400 tức thì) trước khi giao BackgroundTasks, không đợi tới lúc assemble mới báo lỗi."""
    if not use_gpu:
        return CODEC_MAP[codec][0]
    gpu_encoder = _GPU_ENCODER_MAP.get(codec)
    if gpu_encoder is None:
        raise ValueError(f'Mã hoá GPU (NVENC) không hỗ trợ định dạng "{codec}" — chỉ có H.264/H.265. Đổi định dạng hoặc tắt GPU.')
    return gpu_encoder


def _quality_flags(video_codec: str, crf: int) -> list[str]:
    """NVENC không dùng `-crf` (đặc thù riêng libx264/libx265/libvpx) — dùng `-rc vbr
    -cq N` (constant-quality trong chế độ VBR), cùng thang số 0-51 nên tái dùng thẳng
    `CRF_TABLE` hiện có, không cần bảng riêng cho GPU (xem `ffmpeg -h encoder=h264_nvenc`,
    đã kiểm tra thật trên máy — hỗ trợ `-cq` khớp mô tả "0 to 51")."""
    if video_codec.endswith("_nvenc"):
        return ["-rc", "vbr", "-cq", str(crf)]
    return ["-crf", str(crf)]


_GPU_PROBE_CACHE: dict[str, tuple[bool, str]] = {}


def probe_gpu_encoder(ffmpeg: str) -> tuple[bool, str]:
    """Thử encode THẬT 1 frame bé bằng `h264_nvenc` — CHỈ thấy encoder trong `ffmpeg
    -encoders` KHÔNG đủ để biết dùng được: bug thật gặp trên chính máy dev (RTX 5060 Ti,
    driver NVIDIA 576.88) — encoder có đăng ký nhưng chạy thật báo lỗi "Driver does not
    support the required nvenc API version. Required: 13.1 Found: 13.0" (driver chưa đủ
    mới cho bản ffmpeg cụ thể này). Cache theo đường dẫn `ffmpeg` (đổi driver cần khởi
    động lại backend mới re-probe — chấp nhận được, không đáng thêm cơ chế invalidate
    phức tạp hơn cho 1 sự kiện hiếm khi xảy ra giữa lúc app đang chạy)."""
    if ffmpeg in _GPU_PROBE_CACHE:
        return _GPU_PROBE_CACHE[ffmpeg]
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1", "-frames:v", "1",
             "-c:v", "h264_nvenc", "-pix_fmt", "yuv420p", "-f", "null", "-"],
            capture_output=True, text=True, timeout=15,
        )
        ok = result.returncode == 0
        message = "" if ok else (result.stderr or "").strip()[-500:]
    except Exception as e:  # noqa: BLE001
        ok, message = False, str(e)
    _GPU_PROBE_CACHE[ffmpeg] = (ok, message)
    return ok, message

# Color-grade ĐỒNG NHẤT áp cho MỌI segment (Tier 1 của cải tiến "visual không đồng
# nhất" — xem IMPLEMENTATION_REPORT.md): các shot có thể đến từ provider/model khác
# nhau (SDXL local, OpenAI, Gemini...), mỗi model tự căn màu/tương phản khác nhau dù
# cùng 1 prompt style — 1 lớp `eq` nhẹ, cố định, phủ lên TẤT CẢ shot lúc ghép giúp kéo
# gần lại tông màu chung mà không cần đổi gì ở bước sinh ảnh/video. Hệ số nhẹ (không
# tạo hiệu ứng "phim màu" rõ rệt) — chỉ để giảm lệch, không thay thế color grading thật.
_COLOR_GRADE_FILTER = "eq=contrast=1.04:saturation=1.06:brightness=0.01"

# Danh sách transition hợp lệ (`TRANSITIONS`) chuyển sang `app/render/transitions.py`
# (tránh import vòng với `app/routers/pipeline.py` — xem docstring module đó).
# Thời lượng transition CỐ ĐỊNH (không cho tuỳ chỉnh riêng từng shot — người dùng chỉ
# yêu cầu chọn KIỂU, thêm tham số thời lượng là over-engineer ngoài phạm vi yêu cầu).
# 0.6s — đủ mượt để nhận ra, không kéo dài làm chậm nhịp phim tài liệu.
_XFADE_DURATION_SEC = 0.6


class FfmpegNotFoundError(Exception):
    pass


def _ensure_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FfmpegNotFoundError("Chưa cài ffmpeg trên máy chạy backend — xem README.md mục yêu cầu hệ thống trước khi ghép video.")
    return path


def _beat_duration(beat: dict) -> float:
    """Thời lượng ƯỚC TÍNH từ timestamp kịch bản (`timestamp_sec`/`end_sec`) — CHỈ dùng
    làm fallback khi chưa có giọng đọc thật (xem `_shot_base_duration`). Timestamp
    trong kịch bản (nhập tay lúc import CSV/Excel) chỉ mang tính THAM KHẢO, không phải
    nguồn thời lượng thật — người dùng có thể ước lượng sai (VD ghi 40s nhưng giọng đọc
    TTS ra thật chỉ 34s)."""
    start = beat.get("timestamp_sec")
    end = beat.get("end_sec")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
        return float(end - start)
    return DEFAULT_BEAT_DURATION_SEC


def _shot_base_duration(status: ShotRenderStatus, beat: dict) -> float:
    """Thời lượng GỐC (trước khi `_reflow_video_durations` điều chỉnh thêm cho video
    lệch slot) của 1 shot — **đổi nguồn 2026-08-20, theo yêu cầu người dùng**: ưu tiên
    độ dài GIỌNG ĐỌC THẬT (`narration_duration_sec`, đo qua ffprobe lúc sinh xong TTS)
    thay vì timestamp kịch bản (`_beat_duration`). Bug thật đã gặp: shot có
    `end_sec-timestamp_sec` = 40s nhưng giọng đọc TTS ra thật chỉ 34s — ảnh đứng yên
    thêm 6s "chết" (không tiếng, không chuyển shot) trước khi giọng đọc SHOT KẾ TIẾP
    mới bắt đầu, vì segment cũ dựng đúng NGUYÊN 40s bất kể giọng đọc đã hết từ lâu.
    Dùng giọng đọc thật làm segment dài chính xác bằng audio → không còn khoảng chết,
    khớp trải nghiệm xem video có phụ đề/giọng đọc liền mạch. Fallback về
    `_beat_duration` khi CHƯA sinh giọng đọc (shot toàn hình, hoặc chưa TTS xong)."""
    if status.narration_status == "ready" and status.narration_duration_sec:
        return status.narration_duration_sec
    return _beat_duration(beat)


_VIDEO_ASSET_EXTS = (".mp4", ".webm", ".mov")

# Framerate CỐ ĐỊNH áp cho MỌI segment (2026-08-17, mục 43 — bug thật thứ 2 phát hiện
# CÙNG LÚC với bug loop video ở trên, lộ ra ngay sau khi fix bug 1). Không set trước đây
# → ffmpeg tự suy framerate output theo INPUT: ảnh mặc định 25fps, video giữ nguyên
# framerate gốc (VD video AI sinh/upload 24fps) — 2 segment khác nguồn ra 2 timebase
# khác nhau (`1/12800` vs `1/12288`, đã đo thật). `_xfade_chain` nối nhiều run bằng
# xfade/acrossfade YÊU CẦU timebase khớp nhau giữa các input liên tiếp — lệch timebase
# làm ffmpeg lỗi thật "First input link main timebase (...) do not match the
# corresponding second input link xfade timebase (...)" ngay bước ghép cuối (đã tái hiện
# + xác nhận qua log thật của người dùng, không phải suy đoán). Đường KHÔNG-transition
# (concat demuxer, stream-copy) vốn không bị lỗi này (không cần khớp timebase), nhưng ép
# framerate đồng nhất cho MỌI segment không đổi hành vi quan sát được của đường đó, chỉ
# giúp video xuất ra mượt/nhất quán hơn khi trộn nguồn ảnh+video khác framerate.
_OUTPUT_FPS = 30


# Sàn tối thiểu cho độ dài 1 shot sau khi bị "vay" bớt để bù cho shot liền kề dài hơn
# quy định (dưới đây, `_reflow_video_durations`) — tránh 1 shot bị co về gần 0s (ffmpeg
# xử lý segment gần-0s không ổn định, và về mặt xem cũng không còn ý nghĩa gì).
_MIN_DONOR_DURATION_SEC = 0.5

# Sai lệch dưới ngưỡng này giữa video thật và slot quy định coi là KHÔNG đáng kể (sai số
# làm tròn của ffprobe/encoder) — bỏ qua, không reflow để tránh xáo trộn không cần thiết.
_REFLOW_EPSILON_SEC = 0.05


def _reflow_video_durations(statuses: list[ShotRenderStatus], durations: list[float]) -> None:
    """**Tính năng mới (2026-08-17)** — theo yêu cầu người dùng: lỗi ghép thường gặp khi
    upload video tay cho 1 shot là do độ dài VIDEO THẬT không khớp `duration` quy định
    theo timestamp kịch bản của shot đó. Cách xử lý CŨ (mục 43, `_build_segment`) ép
    video khớp `duration` bằng loop (`-stream_loop -1`, video ngắn hơn bị lặp lại) hoặc
    cắt (`-t duration`, video dài hơn bị cắt cụt) — người dùng KHÔNG muốn vậy nữa: muốn
    GIỮ NGUYÊN độ dài thật của video (không loop lặp lại nhìn giả, không cắt mất nội
    dung), bù trừ chênh lệch bằng cách kéo dài/co ngắn thời lượng HIỂN THỊ ẢNH của shot
    LIỀN KỀ thay vào — ưu tiên shot SAU, nếu là shot cuối cùng (không có shot sau) thì
    lấy shot TRƯỚC. Tổng thời lượng toàn video giữ nguyên (chỉ dịch ranh giới giữa 2
    shot, không đổi tổng).

    Sửa TRỰC TIẾP `durations` (in-place, cùng thứ tự với `statuses`) TRƯỚC khi build
    segment — nhờ vậy `_build_segment` nhận `duration == actual` cho shot vừa reflow,
    logic loop/cắt cũ ở đó trở thành no-op (đọc đúng 1 lượt hết video, không cần lặp hay
    cắt) — vẫn giữ nguyên logic đó làm lưới an toàn cho các trường hợp không reflow được
    (thiếu ffprobe, hoặc chỉ có đúng 1 shot nên không có ai để vay/trả).

    Chỉ áp dụng cho shot VIDEO (ảnh tĩnh vốn đã khớp CHÍNH XÁC `duration` nhờ `-loop 1`,
    không thể lệch) — áp dụng chung cho MỌI video (cả AI sinh lẫn upload tay), không chỉ
    riêng upload, vì chênh lệch có thể xảy ra ở cả 2 nguồn."""
    for i, status in enumerate(statuses):
        path = status.visual_asset_path or ""
        if not path.lower().endswith(_VIDEO_ASSET_EXTS):
            continue
        actual = _probe_audio_duration_sec(path)
        if actual is None or actual <= 0:
            continue  # không đo được (thiếu ffprobe/file lỗi) — để _build_segment tự loop/cắt như cũ
        diff = round(durations[i] - actual, 3)
        if abs(diff) < _REFLOW_EPSILON_SEC:
            continue
        if i + 1 < len(statuses):
            donor = i + 1
        elif i - 1 >= 0:
            donor = i - 1
        else:
            continue  # chỉ có 1 shot duy nhất — không có ai để bù, giữ hành vi loop/cắt cũ
        durations[donor] = max(_MIN_DONOR_DURATION_SEC, durations[donor] + diff)
        durations[i] = actual


def _build_segment(
    ffmpeg: str, visual_path: str, narration_path: str | None, duration: float, out_path: Path,
    *, resolution: str, video_codec: str, audio_codec: str, crf: int, ensure_audio_track: bool = False,
    camera_motion: str = "none",
) -> None:
    """`camera_motion` — **mới (2026-08-19)**: hiệu ứng Ken Burns (zoom/pan/tilt/roll/
    orbit, xem `app/render/camera_motion.py`) cho shot ẢNH. CHỈ áp dụng khi `not
    is_video` (video đã có chuyển động thật sẵn, không cần mô phỏng thêm) — tính TRƯỚC
    khi biết `is_video` bên dưới nên đặt tính toán filter SAU dòng đó, không phải trước.

    `ensure_audio_track` — chỉ bật khi assembly có dùng transition (`xfade`/
    `acrossfade`, xem `_xfade_chain` dưới): 2 filter đó cần MỌI input có stream audio,
    kể cả shot không có narration (`-an` trước đây bỏ hẳn track audio) — thiếu 1 input
    sẽ làm lỗi cả filter graph khi ghép nhiều segment. Sinh audio CÂM đúng thời lượng
    bằng `anullsrc` thay vì `-an`. Mặc định `False` — đường ghép NHANH cũ (không
    transition) giữ nguyên hành vi/output y hệt trước đây, không đổi gì (mục 33
    IMPLEMENTATION_REPORT.md).

    **Bug thật (2026-08-17, mục 43)**: input video (AI sinh — luôn cố định ~6s "loopable"
    bất kể `duration` thật của beat, xem prompt `pt_visual_video`; HOẶC video upload tay
    ngắn hơn slot) trước đây KHÔNG được loop — `-i video.mp4 -t duration` chỉ cắt tới hết
    độ dài THẬT của file, ngắn hơn `duration` nếu video gốc ngắn hơn. Các đoạn code khác
    (đặc biệt `_xfade_chain`'s toán offset) coi MỌI segment dài ĐÚNG `duration` như ảnh
    tĩnh (`-loop 1`) — lệch giả định này làm offset xfade trỏ QUÁ độ dài thật của stream,
    ffmpeg lỗi filter graph ở bước ghép cuối (không lỗi ngay lúc build segment, dễ gây
    hiểu lầm "lỗi do B01" trong khi B01 chỉ là input NGẮN đầu tiên, không phải bug riêng
    B01). Fix: `-stream_loop -1` cho MỌI input video — nếu video gốc DÀI hơn `duration`
    thì vô hại (chỉ đọc đủ `duration` giây, không cần loop tới); nếu NGẮN hơn thì lặp lại
    cho tới đủ `duration`, giữ đúng bất biến "mọi segment dài chính xác `duration`" như
    ảnh tĩnh — xem thêm `_VIDEO_ASSET_EXTS` (trước đây chỉ nhận diện `.mp4`, bỏ sót
    `.webm`/`.mov` mà tính năng upload cũng cho phép — cùng sửa 1 lượt)."""
    is_video = visual_path.lower().endswith(_VIDEO_ASSET_EXTS)
    cmd = [ffmpeg, "-y"]
    cmd += ["-stream_loop", "-1", "-i", visual_path] if is_video else ["-loop", "1", "-i", visual_path]
    if narration_path:
        cmd += ["-i", narration_path, "-map", "0:v:0", "-map", "1:a:0"]
    elif ensure_audio_track:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-an"]

    motion_filter = None if is_video else build_camera_motion_filter(camera_motion, duration, *map(int, resolution.split(":")), _OUTPUT_FPS)
    # `setsar=1` ở CẢ 2 nhánh — bug thật (2026-08-22, mục 59 IMPLEMENTATION_REPORT.md):
    # dù nhánh Ken Burns (zoompan) thường ra SAR sạch, không LOẠI TRỪ được trường hợp
    # filter `roll` (dùng `crop`+`scale` riêng, khác zoompan thường) hoặc video nguồn tự
    # mang SAR lệch cũng gây đúng lớp lỗi concat SAR-mismatch như nhánh `_scale_cover_filter`
    # đã xác nhận — ép nhất quán CẢ 2 nhánh cho chắc, không chỉ nhánh đã tái hiện được.
    vf = f"{motion_filter},{_COLOR_GRADE_FILTER},setsar=1" if motion_filter else f"{_scale_cover_filter(resolution)},{_COLOR_GRADE_FILTER},fps={_OUTPUT_FPS}"

    cmd += [
        "-t", str(duration),
        "-vf", vf,
        "-c:v", video_codec,
        *_quality_flags(video_codec, crf),
        "-pix_fmt", "yuv420p",
        *_AUDIO_FORMAT_FLAGS,
        "-c:a", audio_codec,
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def _build_intro_segment(
    ffmpeg: str, kind: str, visual_path: str, audio_path: str | None, out_path: Path,
    *, resolution: str, video_codec: str, audio_codec: str, crf: int,
) -> None:
    """Dựng segment intro (video/audio thương hiệu HOẶC shot mở đầu riêng) — LUÔN có
    audio track (khớp `ensure_audio_track` mọi nơi khác trong assembly dùng để concat/
    xfade an toàn). `kind=="video"` GIỮ NGUYÊN audio gốc của chính file video đó (khác
    `_build_segment` — vốn `-an`/audio ngoài cho video B-roll, không hợp ở đây vì intro
    video có thể là jingle thương hiệu tự có tiếng, KHÔNG được cắt bỏ hay đè narration
    khác lên); `kind=="image"` tái dùng thẳng `_build_segment` (đúng use-case: ảnh tĩnh +
    1 audio ngoài, thời lượng = độ dài audio đo thật qua ffprobe)."""
    if kind == "video":
        cmd = [
            ffmpeg, "-y", "-i", visual_path,
            "-vf", f"{_scale_cover_filter(resolution)},{_COLOR_GRADE_FILTER},fps={_OUTPUT_FPS}",
            "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
            *_AUDIO_FORMAT_FLAGS,
            "-c:a", audio_codec,
            str(out_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True, text=True)
    else:
        duration = _probe_audio_duration_sec(audio_path) or DEFAULT_BEAT_DURATION_SEC
        _build_segment(
            ffmpeg, visual_path, audio_path, duration, out_path,
            resolution=resolution, video_codec=video_codec, audio_codec=audio_codec, crf=crf,
            ensure_audio_track=True, camera_motion="none",
        )


def _concat_fast(ffmpeg: str, seg_paths: list[Path], out_path: Path) -> None:
    """Ghép NHIỀU segment thành 1 file bằng concat demuxer (stream-copy, không
    re-encode) — dùng cho từng "run" (chuỗi shot liên tiếp nối với nhau bằng "cut")
    TRƯỚC KHI nối các run lại bằng xfade, xem `_xfade_chain`."""
    list_path = out_path.with_suffix(".txt")
    list_path.write_text("\n".join(f"file '{p.as_posix()}'" for p in seg_paths), encoding="utf-8")
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def _concat_intro_and_body(
    ffmpeg: str, intro_path: Path, body_path: Path, out_path: Path,
    *, video_codec: str, audio_codec: str, crf: int,
) -> None:
    """Ghép intro + thân video bằng filter `concat` (decode + RE-ENCODE), KHÔNG dùng
    `_concat_fast` (stream-copy).

    **Bug thật (2026-08-20)**: `_concat_fast` giả định MỌI file đưa vào có tham số
    encode "tương thích" ở mức container (không chỉ cùng resolution/fps/codec tên gọi,
    mà cả SPS/PPS/cấu trúc GOP) — đúng với `body_path` (mọi segment trong đó LUÔN đi qua
    CHÍNH `_build_segment`, cùng 1 pattern lệnh ffmpeg lặp lại nên tương thích tự nhiên),
    nhưng SAI với intro: `intro_path` build từ 1 lệnh ffmpeg ĐỘC LẬP (`_build_intro_segment`)
    xử lý nội dung nguồn gốc RẤT khác nhau (video thương hiệu người dùng tự upload —
    encoder/GOP/B-frame bất kỳ). Dù ép cùng resolution/fps/codec/crf, stream-copy concat
    vẫn ra lỗi thật `Application provided invalid, non monotonically increasing dts to
    muxer` — file kết quả ĐỌC ĐƯỢC (`ffprobe` không lỗi) nhưng méo timestamp, phát hỏng
    (đã tái hiện + xác nhận bằng test thật, không phải suy đoán). Fix: dùng filter
    `concat` (decode 2 input rồi re-encode làm 1 stream MỚI liền mạch) — chấp nhận chi
    phí re-encode thêm 1 lần (chỉ 2 input, giống `_xfade_chain` đã re-encode ở ranh giới
    transition) để đổi lấy đúng đắn tuyệt đối, không phụ thuộc "may rủi" tương thích
    stream-copy giữa nguồn ngoài bất kỳ và nội dung tự sinh trong app."""
    # `aformat` ép CẢ 2 audio input về CÙNG sample rate/channel layout TRƯỚC khi vào
    # filter `concat` — bản thân `concat` (khác `-c:a`/output) đòi hỏi 2 input khớp định
    # dạng, thiếu bước này là chính xác chỗ audio bị hỏng/mất khi 1 bên lệch chuẩn (VD
    # narration OmniVoice 24kHz mono) — xem `_AUDIO_FORMAT_FLAGS`.
    cmd = [
        ffmpeg, "-y",
        "-i", str(intro_path), "-i", str(body_path),
        "-filter_complex",
        "[0:a:0]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
        "[1:a:0]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
        "[0:v:0][a0][1:v:0][a1]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
        *_AUDIO_FORMAT_FLAGS,
        "-c:a", audio_codec,
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def _mix_bg_music(
    ffmpeg: str, video_path: Path, bg_music_path: str, volume: float, out_path: Path,
    *, audio_codec: str,
) -> None:
    """Trộn nhạc nền vào audio giọng đọc chính — **mới (2026-08-20)**, theo yêu cầu
    người dùng. Video giữ nguyên (`-c:v copy`, không re-encode); CHỈ audio re-encode
    (`amix` bắt buộc decode+trộn thành 1 stream mới). `-stream_loop -1` lặp vô hạn nhạc
    nền (an toàn dù nhạc ngắn hơn nhiều lần so với video) — `amix=duration=first` CHẶN
    ĐÚNG output ở độ dài input ĐẦU (video), đã verify thật bằng ffprobe: không bị kéo dài
    vô hạn theo nhạc nền lặp, không cần thêm `-t`/`-shortest`. `video_path` LUÔN có sẵn
    audio track (`[0:a]`) — `assemble_video` ép `needs_audio_track=True` bất cứ khi nào
    có bg music, giống cách đã làm cho intro/transition."""
    # `aformat` ép cả 2 audio input về CÙNG sample rate/channel layout trước `amix` —
    # `bg_music_path` là file NGƯỜI DÙNG TỰ UPLOAD (chưa từng qua `_build_segment`, có
    # thể mang sample rate/kênh bất kỳ, khác `video_path` giờ đã LUÔN 44.1kHz stereo nhờ
    # `_AUDIO_FORMAT_FLAGS`) — thiếu bước này `amix` có thể trộn sai hoặc mất hẳn 1 bên.
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", bg_music_path,
        "-filter_complex",
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={volume}[bg];"
        "[a0][bg]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy",
        *_AUDIO_FORMAT_FLAGS,
        "-c:a", audio_codec,
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def _mix_overlay_effect(
    ffmpeg: str, video_path: Path, overlay_path: str, opacity: float, out_path: Path,
    *, resolution: str, video_codec: str, crf: int,
) -> None:
    """Blend hiệu ứng lớp phủ (overlay — VD mưa/tuyết rơi) ĐÈ LIÊN TỤC lên TOÀN BỘ video
    đã ghép xong — **mới (2026-08-22)**, theo yêu cầu người dùng, mô phỏng CHÍNH XÁC
    cách `_mix_bg_music` áp dụng nhạc nền (1 lần hậu kỳ trên `final_path`, KHÔNG áp dụng
    per-shot trong `_build_segment`) nhưng blend VIDEO thay vì trộn AUDIO. Audio giữ
    nguyên (`-c:a copy`); CHỈ video re-encode (`blend` bắt buộc decode+chồng thành 1
    stream mới).

    `blend=all_mode=screen` — kỹ thuật chuẩn cho overlay VFX quay nền đen (nền đen tự
    "biến mất" khi blend screen, không cần chroma key/alpha riêng — hầu hết clip mưa/
    tuyết/bụi/light-leak stock đều quay kiểu này). `colorchannelmixer=rr/gg/bb={opacity}`
    giảm độ sáng overlay TRƯỚC khi blend — dùng làm "cường độ hiệu ứng" (0=tắt hẳn,
    1=full) vì `blend` screen không có tham số alpha trực tiếp.

    `_scale_cover_filter(resolution)` (có sẵn, dùng chung `_build_segment`) scale/crop
    overlay đúng khung 16:9/9:16 (short-form) trước khi blend — không méo hình dù clip
    overlay quay ở tỷ lệ khác.

    `-stream_loop -1` cho overlay (lặp vô hạn, an toàn dù clip effect ngắn hơn video
    nhiều lần) + `blend=...:shortest=1` (chặn đúng ở độ dài `video_path`, không kéo dài
    vô hạn theo overlay lặp) — cùng nguyên lý `_mix_bg_music` dùng `amix=duration=first`,
    khác cơ chế vì đây là filter video không phải audio. LƯU Ý: `shortest=1` PHẢI đặt
    trên chính filter `blend` (framesync option), KHÔNG phải cờ `-shortest` ở output —
    mặc định `blend` dùng `eof_action=repeat`: khi input ngắn hơn (video_path) hết, nó
    lặp lại frame cuối MÃI MÃI thay vì báo EOF, nên `-shortest` ở output không bao giờ
    có tín hiệu để dừng → cả tiến trình treo vô hạn (đã tái hiện + xác nhận thực tế khi
    viết test cho hàm này). `shortest=1` khiến chính filter kết thúc khi input ngắn hơn
    kết thúc, giải quyết tận gốc.

    `-map 0:a?` (dấu `?` = optional, KHÁC `_mix_bg_music` map `0:a` bắt buộc) — overlay
    là tính năng ĐỘC LẬP, dùng được mà không cần bg_music/narration/intro nào, nên
    `video_path` KHÔNG chắc chắn đã có audio track tại bước này (khác `_mix_bg_music` —
    hàm đó chỉ chạy khi CÓ bg_music, lúc đó `needs_audio_track` đã đảm bảo có track)."""
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", overlay_path,
        "-filter_complex",
        f"[1:v]{_scale_cover_filter(resolution)},colorchannelmixer=rr={opacity}:gg={opacity}:bb={opacity}[ovl];"
        "[0:v][ovl]blend=all_mode=screen:shortest=1[v]",
        "-map", "[v]", "-map", "0:a?",
        "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def _xfade_chain(
    ffmpeg: str, run_paths: list[Path], run_durations: list[float], transitions: list[str], out_path: Path,
    *, video_codec: str, audio_codec: str, crf: int,
) -> None:
    """Nối các file `run_paths` (mỗi file đã tự ghép cứng bên trong bằng `_concat_fast`
    — KHÔNG cần blend nội bộ) bằng `xfade`/`acrossfade` tại ranh giới GIỮA các run.
    `transitions[i]` là kiểu chuyển cảnh dùng giữa run i và run i+1 (đã lọc bỏ "cut" —
    ranh giới "cut" giữa 2 run liền kề không tồn tại, vì đó chính là định nghĩa của 1
    run: chuỗi shot nối bằng "cut" được gộp làm 1 run duy nhất từ trước).

    **Bug thật (2026-08-17, mục 43, tiếp theo)**: bản đầu tiên mở 1 lệnh ffmpeg DUY NHẤT
    với TẤT CẢ `n` input cùng lúc, chain toàn bộ filter `xfade`/`acrossfade` trong 1
    `filter_complex`. Đúng với project ngắn/ít transition, nhưng project THẬT của người
    dùng (31 shot, video 12+ phút, nhiều ranh giới transition) làm ffmpeg lỗi thật
    `Cannot allocate memory` (error code -12) ngay lúc flush cuối stream — tái hiện được
    2 lần liên tiếp, LUÔN đúng cùng 1 frame (~24443/24469), tức lỗi hết bộ nhớ thật do
    giữ quá nhiều input/buffer filter graph mở đồng thời, không phải flake ngẫu nhiên.

    **Bug thật TIẾP THEO (2026-08-17, cùng ngày — tái hiện lại SAU fix trên)**: fix "ghép
    tuần tự từng cặp" (giữ ở docstring cũ bên dưới) giảm ĐÚNG số input mở đồng thời
    (luôn = 2), nhưng KHÔNG giảm được tổng THỜI LƯỢNG mà xfade phải decode+re-encode mỗi
    lệnh — `xfade` xử lý filter graph trên TOÀN BỘ 2 input đưa vào (không chỉ đúng đoạn
    overlap ~0.6s), nên `current_path` (bên tích luỹ, DÀI DẦN qua mỗi vòng lặp) vẫn bị
    decode+re-encode LẠI TOÀN BỘ ở MỖI bước merge — tới bước CUỐI (merge lớn nhất),
    `current_path` đã dài gần bằng CẢ video (project thật: ~13 phút 38s), 1 lệnh ffmpeg
    DUY NHẤT vẫn phải xử lý gần hết video đó qua filter graph → lỗi thật LẶP LẠI y hệt
    `Cannot allocate memory` (-12), đúng lúc flush cuối, dù đã đổi hết video sang ảnh
    tĩnh (loại trừ được nguyên nhân do bug reflow mục 45) — xác nhận nguyên nhân gốc là
    xfade's "chi phí decode+encode tỉ lệ theo tổng thời lượng input", không phải "số input
    mở cùng lúc" như chẩn đoán ban đầu.

    **Fix thật sự — TÁCH đoạn KHÔNG đổi khỏi đoạn CẦN blend TRƯỚC khi gọi xfade**: với
    mỗi bước merge, `current_path` được cắt làm 2 bằng CHÍNH `ffmpeg`:
    1. `head` = phần ĐẦU `current_path` (trước điểm transition `t` giây cuối) — cắt bằng
       `-c copy` (stream-copy, KHÔNG decode/re-encode, tốn gần như 0 CPU/RAM bất kể
       `current_path` dài bao nhiêu phút).
    2. `blend` = xfade GIỮA ĐÚNG `t` giây cuối của `current_path` (seek nhanh + chính xác
       bằng `-ss` trước `-i`, ffmpeg hiện đại decode-rồi-bỏ tới đúng mốc thay vì snap về
       keyframe gần nhất — chính xác từng frame) VỚI TOÀN BỘ `run_paths[i]` (offset=0, vì
       input0 giờ CHỈ còn đúng `t` giây, không phải `current_duration`).
    3. Ghép lại `[head, blend]` bằng `_concat_fast` (stream-copy, không re-encode thêm).

    Nhờ vậy chi phí decode+encode thật của xfade mỗi bước giờ CHỈ còn ~`t` giây (~0.6s) +
    độ dài `run_paths[i]` (1 run — không phải cả video tích luỹ), KHÔNG còn phụ thuộc
    `current_path` đã tích luỹ bao lâu — chặn đứng bug ở gốc thay vì chỉ giảm nhẹ như fix
    trước. `run_paths[i]` (vế còn lại) CHƯA được cắt tương tự (chỉ `current_path` — vế
    tích luỹ — mới thật sự phình to qua từng vòng lặp; 1 "run" đơn lẻ bị giới hạn bởi số
    shot nối "cut" giữa 2 lần đổi transition, hiếm khi tự nó đã dài bằng cả video) — nếu
    sau này gặp case 1 run đơn lẻ CỰC dài không có transition nào khác, có thể cắt đối
    xứng cả 2 vế, nhưng chưa có bằng chứng cần tới mức đó, không over-engineer trước."""
    n = len(run_paths)
    current_path = run_paths[0]
    current_duration = run_durations[0]
    to_cleanup: list[Path] = []
    try:
        for i in range(1, n):
            # Kẹp `t` theo run NGẮN HƠN trong cặp — run quá ngắn (VD 1-2s) mà dùng
            # transition 0.6s trọn vẹn sẽ chồng lấn gần hết nội dung, nhìn sai hẳn ý đồ;
            # tối thiểu 0.1s để xfade vẫn còn ý nghĩa (không suy biến về gần 0). `t` LUÔN
            # ≤ 0.8*current_duration → `head_keep` LUÔN dương, không cần guard riêng.
            t = max(0.1, min(_XFADE_DURATION_SEC, current_duration * 0.8, run_durations[i] * 0.8))
            head_keep = current_duration - t
            is_last = i == n - 1
            step_path = out_path if is_last else out_path.with_name(f"{out_path.stem}_xstep{i:02d}{out_path.suffix}")
            head_path = out_path.with_name(f"{out_path.stem}_xhead{i:02d}{out_path.suffix}")
            blend_path = out_path.with_name(f"{out_path.stem}_xblend{i:02d}{out_path.suffix}")
            to_cleanup += [head_path, blend_path]

            head_cmd = [ffmpeg, "-y", "-i", str(current_path), "-t", f"{head_keep:.3f}", "-c", "copy", str(head_path)]
            subprocess.run(head_cmd, capture_output=True, check=True, text=True)

            # `aformat` ép CẢ 2 audio input về CÙNG sample rate/channel layout TRƯỚC
            # `acrossfade` — filter này (khác `-c:a`/output) đòi hỏi 2 input khớp định
            # dạng; thiếu bước này là chính xác chỗ audio bị hỏng/mất khi ghép intro
            # (44.1kHz stereo) với thân video có narration OmniVoice (24kHz mono) qua
            # transition khác "cut" — bug thật đã tái hiện + xác nhận (mục 57
            # IMPLEMENTATION_REPORT.md). Cũng áp dụng cho xfade shot-to-shot thường, dù
            # ít gặp lệch hơn (mọi run đều qua `_build_segment` đã chuẩn hoá).
            blend_cmd = [
                ffmpeg, "-y",
                "-ss", f"{head_keep:.3f}", "-i", str(current_path),
                "-i", str(run_paths[i]),
                "-filter_complex",
                f"[0:v][1:v]xfade=transition={transitions[i - 1]}:duration={t:.3f}:offset=0[v];"
                "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
                "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
                f"[a0][a1]acrossfade=d={t:.3f}[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
                *_AUDIO_FORMAT_FLAGS,
                "-c:a", audio_codec,
                str(blend_path),
            ]
            subprocess.run(blend_cmd, capture_output=True, check=True, text=True)

            _concat_fast(ffmpeg, [head_path, blend_path], step_path)

            if current_path not in run_paths:  # chỉ xoá file trung gian TỰ TẠO ở đây, không đụng run gốc
                to_cleanup.append(current_path)
            current_duration = current_duration + run_durations[i] - t
            current_path = step_path
    finally:
        for p in to_cleanup:
            p.unlink(missing_ok=True)


def _run_boundaries(shots: list[dict]) -> list[int]:
    """Trả list INDEX bắt đầu mỗi "run" — ranh giới run mới là ngay SAU shot có
    `transition_to_next` KHÁC "cut" (shot đó là shot CUỐI của run hiện tại, shot kế
    tiếp bắt đầu run mới, sẽ nối bằng xfade thay vì gộp cứng vào cùng run)."""
    boundaries = [0]
    for i, s in enumerate(shots[:-1]):
        if (s.get("transition_to_next") or "cut") != "cut":
            boundaries.append(i + 1)
    boundaries.append(len(shots))
    return boundaries


def assemble_video(
    project_id: str, *,
    resolution: Resolution = "1080p",
    codec: Codec = "h264",
    quality: Quality = "medium",
    use_gpu: bool = False,
) -> None:
    """Chạy trong FastAPI BackgroundTasks (app/routers/render.py::POST .../assemble).
    Yêu cầu MỌI shot đã `visual_status=="ready"` VÀ `approved=True` (human review) —
    thiếu 1 shot chưa duyệt sẽ raise lỗi rõ ràng, không ghép thiếu cảnh.

    `use_gpu` — **mới (2026-08-17)**: đổi encoder cuối sang NVENC (`resolve_video_codec`)
    thay vì libx264/libx265 CPU — router đã validate trước (400 tức thì nếu use_gpu +
    vp9), `ValueError` ở đây chỉ là lưới an toàn thứ 2 (VD gọi trực tiếp ngoài router)."""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        pdir = project_dir(p.channel_id, p.id)
        state = load_render_state(pdir, project_id)
        state.assembly_status = "assembling"
        state.assembly_error = None
        state.assembly_started_at = vn_isoformat(datetime.now(timezone.utc))
        state.assembly_progress = AssemblyProgress(stage="segments", current=0, total=0)
        save_render_state(pdir, state)

        try:
            ffmpeg = _ensure_ffmpeg()
            pack = read_json(pdir / "pack.json") or {}
            shots = pack.get("shots", [])
            by_id = {s.shot_id: s for s in state.shots}
            brand = _load_brand_profile(p.channel_id)
            intro_source = _resolve_intro_source(state.intro, brand, shots, by_id)
            bg_music_source = _resolve_bg_music_source(state.bg_music, brand)
            overlay_source = _resolve_overlay_source(state.overlay, brand)

            # Short-form (9:16) — mới (2026-08-21): `p.format` quyết định map nào áp
            # dụng, xem RESOLUTION_MAP_VERTICAL ở trên.
            scale = RESOLUTION_MAP_VERTICAL[resolution] if (p.format or "long") == "short" else RESOLUTION_MAP[resolution]
            _, audio_codec, ext = CODEC_MAP[codec]
            video_codec = resolve_video_codec(codec, use_gpu)
            crf = CRF_TABLE[codec][quality]

            segments_dir = pdir / "renders" / "segments"
            segments_dir.mkdir(parents=True, exist_ok=True)
            seg_paths: list[Path] = []

            total = len(shots)
            state.assembly_progress = AssemblyProgress(stage="segments", current=0, total=total)
            save_render_state(pdir, state)

            # Quyết định TRƯỚC vòng lặp — quyết định toàn cục (áp dụng cho MỌI segment,
            # không phải riêng lẻ) vì `_xfade_chain` (dưới) cần TẤT CẢ input có track
            # audio, kể cả shot không dùng transition trực tiếp nhưng nằm trong 1 run bị
            # ghép qua `_concat_fast` rồi chính run đó lại nối bằng xfade với run khác.
            has_transitions = any((s.get("transition_to_next") or "cut") != "cut" for s in shots[:-1]) if len(shots) > 1 else False
            # Có intro (LUÔN có audio track — xem `_build_intro_segment`) → thân video
            # PHẢI có audio track để `_concat_intro_and_body` (filter concat, yêu cầu
            # đúng số stream audio ở CẢ 2 input) không lỗi "matches no streams". Bug thật
            # phát hiện lúc viết test: project không narration + không transition trước
            # đây build thân với `-an` (không track audio nào) — hợp lệ khi đứng riêng,
            # nhưng vỡ ngay khi cần ghép thêm intro (luôn có audio) vào trước. Có nhạc
            # nền (bg_music_source) cũng cần audio track ở thân — `_mix_bg_music` (dưới)
            # LUÔN trộn vào `[0:a]` của video cuối, thiếu track sẽ lỗi "matches no streams".
            needs_audio_track = has_transitions or bool(intro_source) or bool(bg_music_source)

            # --- Pass 1: validate shot đã sẵn sàng + độ dài QUY ĐỊNH theo timestamp kịch bản ---
            statuses: list[ShotRenderStatus] = []
            durations: list[float] = []
            for shot in shots:
                status = by_id.get(shot["shot_id"])
                if not status or status.visual_status != "ready" or not status.visual_asset_path:
                    raise RuntimeError(f"Shot {shot['shot_id']} chưa sinh xong visual — không thể ghép.")
                if not status.approved:
                    raise RuntimeError(f"Shot {shot['shot_id']} chưa được duyệt (human review) — không thể ghép.")
                statuses.append(status)
                durations.append(_shot_base_duration(status, _find_beat(pack, shot)))

            _reflow_video_durations(statuses, durations)

            # --- Pass 2: build từng segment theo độ dài đã reflow ---
            for i, shot in enumerate(shots):
                status = statuses[i]
                duration = durations[i]
                narration_path = status.narration_asset_path if status.narration_status == "ready" else None
                seg_path = segments_dir / f"segment_{i:03d}.{ext}"
                _build_segment(
                    ffmpeg, status.visual_asset_path, narration_path, duration, seg_path,
                    resolution=scale, video_codec=video_codec, audio_codec=audio_codec, crf=crf,
                    ensure_audio_track=needs_audio_track, camera_motion=shot.get("camera_motion") or "none",
                )
                seg_paths.append(seg_path)

                state.assembly_progress = AssemblyProgress(stage="segments", current=i + 1, total=total)
                save_render_state(pdir, state)

            if not seg_paths:
                raise RuntimeError("Chưa có shot nào để ghép.")

            final_path = pdir / "renders" / f"final.{ext}"
            # Có intro (shot mở đầu riêng HOẶC video/audio thương hiệu cấp kênh) — dựng
            # phần thân (shot list) ra file TẠM riêng (`body.{ext}`), rồi mới ghép intro
            # + thân lại thành `final_path` ở bước cuối. Không có intro — ghi THẲNG vào
            # `final_path` như cũ, không tốn thêm 1 bước copy vô ích (2026-08-20, theo
            # yêu cầu người dùng: video/audio thương hiệu phát ĐẦU TIÊN mọi video).
            body_path = (pdir / "renders" / f"body.{ext}") if intro_source else final_path

            if not has_transitions:
                # Đường NHANH cũ — stream-copy, không re-encode. Giữ nguyên 100% hành vi
                # trước khi có tính năng transition (mục 33 IMPLEMENTATION_REPORT.md).
                state.assembly_progress = AssemblyProgress(stage="concat", current=total, total=total)
                save_render_state(pdir, state)
                list_path = pdir / "renders" / "list.txt"
                list_path.write_text("\n".join(f"file '{p.as_posix()}'" for p in seg_paths), encoding="utf-8")
                concat_cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(body_path)]
                subprocess.run(concat_cmd, capture_output=True, check=True, text=True)
            else:
                # Có transition — gộp shot liên tiếp nối bằng "cut" thành từng "run" (fast
                # concat, không blend), rồi nối các run lại bằng xfade/acrossfade THẬT tại
                # đúng những ranh giới người dùng chọn transition (xem _run_boundaries).
                state.assembly_progress = AssemblyProgress(stage="concat", current=total, total=total)
                save_render_state(pdir, state)
                boundaries = _run_boundaries(shots)
                run_paths: list[Path] = []
                run_durations: list[float] = []
                run_transitions: list[str] = []
                for r in range(len(boundaries) - 1):
                    start, end = boundaries[r], boundaries[r + 1]
                    run_segs = seg_paths[start:end]
                    run_dur = sum(durations[start:end])
                    if len(run_segs) == 1:
                        run_path = run_segs[0]  # 1 segment — không cần ghép, dùng thẳng
                    else:
                        run_path = pdir / "renders" / f"run_{r:02d}.{ext}"
                        _concat_fast(ffmpeg, run_segs, run_path)
                    run_paths.append(run_path)
                    run_durations.append(run_dur)
                    if end < len(shots):
                        run_transitions.append(shots[end - 1].get("transition_to_next") or "cut")
                # `has_transitions=True` đảm bảo có ÍT NHẤT 1 ranh giới non-"cut" trong
                # `shots[:-1]` → `_run_boundaries` LUÔN tạo ≥2 run — `_xfade_chain` gọi an
                # toàn, không cần nhánh "chỉ 1 run" (không thể xảy ra ở đây).
                _xfade_chain(
                    ffmpeg, run_paths, run_durations, run_transitions, body_path,
                    video_codec=video_codec, audio_codec=audio_codec, crf=crf,
                )

            if intro_source:
                intro_kind, intro_visual, intro_audio = intro_source
                intro_path = pdir / "renders" / f"intro_segment.{ext}"
                _build_intro_segment(
                    ffmpeg, intro_kind, intro_visual, intro_audio, intro_path,
                    resolution=scale, video_codec=video_codec, audio_codec=audio_codec, crf=crf,
                )
                # Hiệu ứng chuyển cảnh intro→thân video — **mới (2026-08-21)**, theo yêu
                # cầu người dùng (trước đây LUÔN cắt cứng). `state.intro` (nếu có) mang
                # `transition_to_next` — dùng "cut" mặc định khi CHƯA có shot mở đầu
                # riêng của project (VD đang dùng brand intro, chưa có nơi nào để cấu
                # hình transition riêng cho trường hợp đó ở UI hiện tại).
                intro_transition = (state.intro.transition_to_next if state.intro else None) or "cut"
                if intro_transition == "cut":
                    # Ghép CẮT CỨNG (không xfade, khớp bản chất "phát trước tiên rồi
                    # chuyển thẳng vào nội dung"). Dùng filter concat (re-encode), KHÔNG
                    # stream-copy — xem docstring `_concat_intro_and_body` (bug thật:
                    # stream-copy giữa nội dung tự sinh trong app và video thương hiệu
                    # người dùng tự upload làm méo timestamp, phát hỏng).
                    _concat_intro_and_body(ffmpeg, intro_path, body_path, final_path, video_codec=video_codec, audio_codec=audio_codec, crf=crf)
                else:
                    # Dùng LẠI `_xfade_chain` (cùng cơ chế xfade/acrossfade đã verify kỹ
                    # cho shot-to-shot, mục 43/47) — coi intro + thân video như 2 "run"
                    # nối bằng 1 transition duy nhất. Cần thời lượng THẬT của cả 2 (đo
                    # qua ffprobe) để `_xfade_chain` tính đúng điểm cắt/overlap.
                    intro_dur = _intro_duration_sec(intro_source) or 1.0
                    body_dur = _probe_audio_duration_sec(body_path) or 1.0
                    _xfade_chain(
                        ffmpeg, [intro_path, body_path], [intro_dur, body_dur], [intro_transition], final_path,
                        video_codec=video_codec, audio_codec=audio_codec, crf=crf,
                    )
                intro_path.unlink(missing_ok=True)
                if body_path != final_path:
                    body_path.unlink(missing_ok=True)

            if bg_music_source:
                # Trộn nhạc nền làm bước HẬU KỲ cuối cùng — SAU intro/transition (nhạc
                # nền phát ĐÈ LIÊN TỤC dưới TOÀN BỘ video, kể cả intro, khớp yêu cầu
                # người dùng), trên CHÍNH `final_path` rồi ghi đè lại (2026-08-20).
                bg_path, bg_volume = bg_music_source
                mixed_path = pdir / "renders" / f"final_mixed.{ext}"
                _mix_bg_music(ffmpeg, final_path, bg_path, bg_volume, mixed_path, audio_codec=audio_codec)
                final_path.unlink(missing_ok=True)
                mixed_path.rename(final_path)

            if overlay_source:
                # Cùng nguyên tắc bg_music ở trên — blend overlay làm bước HẬU KỲ cuối
                # cùng (SAU cả bg_music, thứ tự không quan trọng vì 2 bước độc lập: 1 chỉ
                # đụng audio, 1 chỉ đụng video), trên CHÍNH `final_path` rồi ghi đè lại
                # (2026-08-22). `scale` (đã tính ở trên, dạng "W:H") dùng chung với
                # `_build_segment`/`_scale_cover_filter` — đảm bảo overlay scale đúng
                # khung 16:9/9:16 giống hệt nội dung chính.
                overlay_path, overlay_opacity = overlay_source
                overlaid_path = pdir / "renders" / f"final_overlaid.{ext}"
                _mix_overlay_effect(ffmpeg, final_path, overlay_path, overlay_opacity, overlaid_path, resolution=scale, video_codec=video_codec, crf=crf)
                final_path.unlink(missing_ok=True)
                overlaid_path.rename(final_path)

            state.final_video_path = str(final_path)
            state.assembly_status = "done"
        except subprocess.CalledProcessError as e:
            state.assembly_status = "error"
            # Bug thật (2026-08-17, mục 43): `[:1000]` LẤY ĐẦU chuỗi — stderr ffmpeg luôn
            # mở đầu bằng banner version+configuration (thường DÀI HƠN 1000 ký tự), nên
            # lý do lỗi thật (luôn nằm ở CUỐI stderr) bị cắt mất hoàn toàn, chỉ còn lại
            # banner vô nghĩa (đã thấy thật khi điều tra lỗi assembly của người dùng — xem
            # ghi chú `_build_segment`). Đổi sang lấy ĐUÔI chuỗi.
            state.assembly_error = f"ffmpeg lỗi: {(e.stderr or '').strip()[-2000:]}"
        except Exception as e:  # noqa: BLE001
            state.assembly_status = "error"
            state.assembly_error = str(e)
        finally:
            state.assembly_started_at = None
            save_render_state(pdir, state)
    finally:
        db.close()
