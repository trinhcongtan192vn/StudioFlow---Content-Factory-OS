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

import os
import random
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.config import project_dir
from app.db import SessionLocal
from app.filestore import read_json
from app.models import Project
from app.render.camera_motion import build_camera_motion_filter
from app.render.engine import (
    _find_beat,
    _load_brand_profile,
    _mark_assembly_done,
    _mark_assembly_in_progress,
    _probe_audio_duration_sec,
    is_assembly_in_progress,
    load_render_state,
    save_render_state,
)
from app.render.bg_music import resolve_bg_music_source as _resolve_bg_music_source
from app.render.intro import intro_duration_sec as _intro_duration_sec, resolve_intro_source as _resolve_intro_source
from app.render.media_probe import probe_video_dimensions
from app.render.overlay import resolve_overlay_source as _resolve_overlay_source
from app.render.schemas import AssemblyProgress, ImageLayer, ShotRenderStatus, VideoLayer
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


def _scale_blurfill_filter(resolution: str) -> str:
    """Biến thể "blur-fill" thay cho cover-crop (`_scale_cover_filter`) khi lệch tỷ lệ
    khung hình — CHANGE_Semantic_BRoll_Asset_Vault.md §9b.3. Nền là CHÍNH nội dung đó
    phóng to + làm mờ (`gblur`), nội dung gốc giữ NGUYÊN VẸN (scale-fit, không crop mất
    rìa) ở giữa — hữu ích cho clip B-roll từ Asset Vault lệch tỷ lệ (VD clip ngang ghép
    vào project short-form dọc), không mất chi tiết rìa như crop có thể gây ra.

    Trả về 1 ĐOẠN FILTERGRAPH ĐA NHÁNH (`split`/named pad, không phải chuỗi đơn giản
    comma-nối được như `_scale_cover_filter`) — vẫn NỐI ĐƯỢC bằng dấu phẩy với filter kế
    tiếp (color grade/fps) ở nơi gọi, vì đoạn cuối (`overlay=...,setsar=1`) là 1
    filterchain KHÔNG gắn tên pad — verify thật bằng ffmpeg: ghép cả blur-fill + color
    grade (`eq=...`) + `fps=30` chung 1 chuỗi `-vf`, chạy được không lỗi, không suy đoán
    cú pháp `-vf` chấp nhận `split`/pad tên bên trong 1 chuỗi đơn (có, đã xác nhận)."""
    w, h = resolution.split(":")
    return (
        "split=2[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=20[bg2];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


def _resolve_scale_filter(resolution: str, brand: dict) -> str:
    """`BrandProfile.aspect_fill_mode` (§9b.3) — `"crop"` (mặc định, hành vi cover-crop
    cũ NGUYÊN VẸN) hoặc `"blur"` (blur-fill, xem `_scale_blurfill_filter`)."""
    if (brand or {}).get("aspect_fill_mode") == "blur":
        return _scale_blurfill_filter(resolution)
    return _scale_cover_filter(resolution)


_GRADE_PRESETS: dict[str, str] = {
    "cinematic_warm": "eq=contrast=1.08:saturation=1.12:brightness=0.02:gamma_r=1.03:gamma_b=0.97",
    "moody_dark": "eq=contrast=1.15:saturation=0.85:brightness=-0.04",
    "documentary_faded": "eq=contrast=0.95:saturation=0.8:brightness=0.01",
}


def _resolve_color_grade_filter(brand: dict) -> str:
    """`BrandProfile.visual_grade` (CHANGE_Semantic_BRoll_Asset_Vault.md §9b.2) — preset
    màu CỐ ĐỊNH theo TỪNG KÊNH, thay hằng số `_COLOR_GRADE_FILTER` áp DÙNG CHUNG TOÀN HỆ
    THỐNG trước đây. Rỗng/không khớp preset nào trong `_GRADE_PRESETS` → dùng ĐÚNG hằng
    số cũ (KHÔNG đổi hành vi cho kênh chưa cấu hình, giữ tương thích ngược tuyệt đối)."""
    preset = (brand or {}).get("visual_grade") or ""
    return _GRADE_PRESETS.get(preset, _COLOR_GRADE_FILTER)


def _grain_filter_suffix(brand: dict) -> str:
    """Film grain overlay — `BrandProfile.grain_enabled` (§9b.2), TẮT mặc định. Dùng
    `noise=alls=8:allf=t+u` (nhiễu ĐỘNG theo cả thời gian lẫn không gian — mô phỏng hạt
    phim; mức `alls=8` THẤP, chỉ đủ tạo kết cấu, không làm nhiễu ảnh rõ rệt). Trả CHUỖI
    RỖNG khi tắt — nối thẳng vào cuối `vf` chain bằng dấu phẩy tại nơi gọi (rỗng = không
    thêm gì, giữ nguyên chain cũ nguyên vẹn)."""
    if not (brand or {}).get("grain_enabled"):
        return ""
    return ",noise=alls=8:allf=t+u"

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
    phức tạp hơn cho 1 sự kiện hiếm khi xảy ra giữa lúc app đang chạy).

    **Bug thật thứ 2 (2026-08-26)** — phát hiện NGAY sau khi người dùng update driver
    lên 610.88 (đủ điều kiện ở trên): frame test `64x64` cũ giờ bị NVENC từ chối RIÊNG vì
    lý do KHÁC — `InitializeEncoder failed: invalid param (8): Frame Dimension less than
    the minimum supported value.` Xác nhận thật bằng ffmpeg: `128x128` vẫn FAIL, `145x49`/
    `256x144` PASS — 64x64 dưới ngưỡng kích thước tối thiểu NVENC yêu cầu (không liên quan
    gì driver, encode THẬT ở độ phân giải thật 1280x720 verify chạy tốt bình thường) —
    probe cũ sẽ báo "không dùng được" SAI ngay cả khi GPU encode thật sự hoạt động tốt.
    Đổi sang `256x144` (16:9 thu nhỏ, an toàn trên ngưỡng tối thiểu đã đo thật)."""
    if ffmpeg in _GPU_PROBE_CACHE:
        return _GPU_PROBE_CACHE[ffmpeg]
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=256x144:d=0.1", "-frames:v", "1",
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

# Timeout (giây) cho các lệnh ffmpeg xử lý CẢ project trong 1 LỆNH DUY NHẤT — dựng video
# nền chung (`_build_background_video_master`/`_build_background_video_playlist`, mục
# 106/110) và ghép layer định vị (`_composite_layers`, mục 112) — **mới (2026-09-02, mục
# 111)**, theo yêu cầu người dùng ("cách nào để tránh lỗi tương tự"): các hàm này KHÔNG
# có tiến trình con/checkpoint nào để báo lại giữa chừng (khác Pass 2 xử lý TỪNG shot
# riêng lẻ) — nếu ffmpeg treo THẬT (input hỏng, deadlock, máy quá tải), KHÔNG có gì tự
# cắt nó ra, `state.assembly_status="assembling"` sẽ kẹt vô thời hạn (đúng dạng bug đã
# gặp, dù nguyên nhân LẦN ĐÓ có vẻ khác — process/thread chết chứ không phải ffmpeg treo,
# xem `engine.py::_assembly_in_progress`). 2 giờ — đủ RỘNG RÃI cho video rất dài (project
# thật đã gặp ~28 phút vẫn chỉ mất ~2 phút để dựng master) mà vẫn có 1 TRẦN cuối cùng
# thay vì vô hạn — hết giờ → `subprocess.TimeoutExpired` → lỗi RÕ RÀNG (xem except ở
# `assemble_video`), không còn "kẹt" mãi mãi.
_WHOLE_VIDEO_FFMPEG_TIMEOUT_SEC = 7200

# Số segment build ĐỒNG THỜI (Pass 2, `assemble_video`) — **mới (2026-08-26)**, theo yêu
# cầu người dùng cải thiện tốc độ ghép ("bước ghép toàn bộ các cảnh có vẻ chậm"). Mỗi
# shot build ra 1 file `segment_{i}.{ext}` HOÀN TOÀN ĐỘC LẬP (không đọc/ghi chung gì với
# shot khác) — trước đây chạy TUẦN TỰ dù không có lý do kỹ thuật nào bắt buộc, phí thời
# gian chờ khi có nhiều shot (project long-form thật, VD "31 shot, video 12+ phút" —
# xem `_xfade_chain` docstring). Verify thật bằng ffmpeg trên chính máy dev (RTX 5060 Ti,
# 20 CPU logical core): 4 encode `h264_nvenc` đồng thời không bị driver từ chối (một số
# GPU GeForce đời cũ giới hạn số phiên NVENC đồng thời qua driver, máy này KHÔNG giới hạn)
# — 4x đồng thời nhanh hơn ~26% so với tuần tự cho cùng 4 lần encode (2.65s → 1.96s);
# CPU (libx264, vốn đã tự đa luồng NỘI BỘ mỗi tiến trình) đo được vẫn nhanh hơn khi chạy
# đồng thời trên máy 20 core (5.14s → 4.38s), không bị "oversubscribe" nghiêm trọng. Chọn
# 4 làm mặc định CỐ ĐỊNH (không đọc từ cấu hình — thêm 1 field cấu hình cho việc này là
# over-engineer so với yêu cầu) — đủ để tận dụng máy nhiều core/GPU rảnh, không quá cao
# để tránh làm máy YẾU HƠN (ít CPU core, GPU thế hệ cũ giới hạn phiên NVENC) bị quá tải;
# `min(4, cpu_count)` tự hạ xuống trên máy ít core hơn 4 (VD laptop 2-4 core).
_SEGMENT_BUILD_WORKERS = min(4, os.cpu_count() or 4)


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


def _narration_floor(status: ShotRenderStatus) -> float:
    """Độ dài TỐI THIỂU 1 shot phải giữ để không cắt cụt giọng đọc CỦA CHÍNH shot đó —
    0 nếu shot không có giọng đọc (sẵn sàng) để bảo vệ. Dùng làm sàn (floor) khi
    `_reflow_video_durations` định co ngắn 1 shot video, xem bug thật ở đó."""
    if status.narration_status == "ready" and status.narration_duration_sec:
        return status.narration_duration_sec
    return 0.0


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
    riêng upload, vì chênh lệch có thể xảy ra ở cả 2 nguồn.

    **Bug thật (2026-08-26)**: người dùng báo giọng đọc của 1 shot bị CẮT CỤT ngay khi
    chuyển sang shot kế — xảy ra khi shot đó là VIDEO ngắn hơn chính giọng đọc của nó
    (VD video AI sinh ~6s nhưng giọng đọc dài 10s). `durations[i]` LÚC ĐẦU (Pass 1,
    `_shot_base_duration`) đã ưu tiên đúng độ dài giọng đọc (10s) — nhưng vòng lặp NÀY
    trước đây LUÔN co `durations[i]` về ĐÚNG `actual` (độ dài video thật, 6s) bất kể lý do
    gì làm `durations[i]` dài hơn `actual` lúc đầu, kể cả khi lý do đó CHÍNH LÀ giọng đọc
    CỦA SHOT ĐÓ — `_build_segment` sau đó cắt audio narration theo đúng 6s méo này, mất
    4s cuối lời thoại. Fix: `target` không còn LUÔN bằng `actual` — lấy
    `max(actual, _narration_floor(status))`, không bao giờ co 1 shot xuống dưới độ dài
    giọng đọc CỦA CHÍNH NÓ. Khi giọng đọc ready và dài hơn video thật, `target ==
    durations[i]` (vì `_shot_base_duration` đã set y hệt giá trị này) → `diff≈0` → bỏ
    qua hẳn, KHÔNG co/vay gì — thay vào đó `_build_segment` tự lấp phần video còn thiếu
    bằng cách ĐÓNG BĂNG khung hình cuối (freeze last frame, xem `tpad` ở đó), không loop
    lại từ đầu — đúng hướng người dùng đề xuất, thay hẳn giải pháp loop cũ.

    Áp dụng CÙNG sàn này khi shot khác "vay" bớt của 1 shot LÁNG GIỀNG (`donor`, nhánh
    video DÀI hơn `duration` quy định, phải rút bớt thời lượng hiển thị ảnh của láng
    giềng để bù) — láng giềng bị vay KHÔNG được co xuống dưới giọng đọc CỦA CHÍNH NÓ,
    dù nó không phải shot đang xét trực tiếp trong vòng lặp này."""
    for i, status in enumerate(statuses):
        path = status.visual_asset_path or ""
        if not path.lower().endswith(_VIDEO_ASSET_EXTS):
            continue
        actual = _probe_audio_duration_sec(path)
        if actual is None or actual <= 0:
            continue  # không đo được (thiếu ffprobe/file lỗi) — để _build_segment tự đóng băng/cắt như cũ
        target = max(actual, _narration_floor(status))
        diff = round(durations[i] - target, 3)
        if abs(diff) < _REFLOW_EPSILON_SEC:
            continue
        if i + 1 < len(statuses):
            donor = i + 1
        elif i - 1 >= 0:
            donor = i - 1
        else:
            continue  # chỉ có 1 shot duy nhất — không có ai để bù, giữ hành vi cũ
        donor_floor = _narration_floor(statuses[donor])
        durations[donor] = max(_MIN_DONOR_DURATION_SEC, donor_floor, durations[donor] + diff)
        durations[i] = target


def _build_segment(
    ffmpeg: str, visual_path: str, narration_path: str | None, duration: float, out_path: Path,
    *, resolution: str, video_codec: str, audio_codec: str, crf: int, ensure_audio_track: bool = False,
    camera_motion: str = "none", narration_lead_in_sec: float = 0.0, narration_lead_out_sec: float = 0.0,
    brand: dict | None = None,
) -> None:
    """`brand` — **mới (2026-08-26, CHANGE_Semantic_BRoll_Asset_Vault.md §9b.2/§9b.3)**:
    style normalization theo BrandProfile — `_resolve_scale_filter` (crop/blur-fill theo
    `aspect_fill_mode`), `_resolve_color_grade_filter` (preset màu theo `visual_grade`),
    `_grain_filter_suffix` (film grain theo `grain_enabled`). `None`/rỗng → dùng ĐÚNG
    hành vi cũ (`_scale_cover_filter` + `_COLOR_GRADE_FILTER` cố định, không grain) —
    KHÔNG đổi output cho caller nào chưa truyền `brand`.

    `narration_lead_in_sec`/`narration_lead_out_sec` — **mới (2026-08-23)**: đệm lặng
    (silence) vào ĐẦU/CUỐI audio giọng đọc — bug thật người dùng báo: bật hiệu ứng chuyển
    cảnh (transition khác "cut") giữa các shot làm giọng đọc bị "nuốt chữ" ở cả đầu lẫn
    cuối shot. Nguyên nhân: `_xfade_chain` cắt `t` giây (~0.6s, `_XFADE_DURATION_SEC`)
    CUỐI của shot đứng trước (head cut trực tiếp vào giọng đọc — không phải khoảng lặng,
    audio gốc lấp ĐẦY nguyên slot) rồi `acrossfade` trộn đoạn đó với `t` giây ĐẦU giọng
    đọc shot sau — cả 2 đều là LỜI THOẠI THẬT (TTS ra sát mép, không có đệm lặng), vừa bị
    cắt cụt vừa bị chồng tiếng lẫn nhau, nghe như nuốt chữ ở CẢ 2 phía ranh giới. Fix
    (`assemble_video` gọi hàm này): với shot có ranh giới dùng transition, đệm thêm lặng
    ĐÚNG BẰNG `_XFADE_DURATION_SEC` (giá trị `t` tối đa có thể xảy ra) vào phía giáp
    transition trước khi build segment — `_xfade_chain` giờ cắt/trộn TRÚNG khoảng lặng
    đệm thêm này, không còn đụng vào lời thoại thật. Segment DÀI HƠN đúng bằng phần đệm
    (do `duration` truyền vào đã cộng sẵn ở nơi gọi) — giọng đọc thật vẫn nguyên vẹn,
    chỉ "lùi lại" 1 chút ở đầu/cuối, đúng đề xuất ban đầu của người dùng ("delay việc
    chạy giọng đọc"). Dùng filter `adelay` (đệm đầu — trễ điểm bắt đầu phát) + `apad`
    (đệm cuối — kéo dài track bằng lặng) trên audio, KHÔNG đụng gì tới video.

    `camera_motion` — **mới (2026-08-19)**: hiệu ứng Ken Burns (zoom/pan/tilt/roll/
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
    B01). Fix LÚC ĐÓ: `-stream_loop -1` cho MỌI input video (lặp lại từ đầu cho tới đủ
    `duration`), giữ đúng bất biến "mọi segment dài chính xác `duration`" như ảnh tĩnh.

    **Đổi lại (2026-08-26), theo yêu cầu người dùng**: loop (lặp lại TỪ ĐẦU) làm giọng
    đọc nghe ổn (không cắt — `_reflow_video_durations` đã đảm bảo `duration` không bao
    giờ ngắn hơn giọng đọc CỦA CHÍNH SHOT, xem bug thật ở đó) nhưng NHÌN GIẢ khi video
    ngắn hơn slot nhiều (VD video AI ~6s lặp lại 2 lần để lấp đủ 13s giọng đọc — người
    xem thấy rõ chuyển động "giật" quay lại đầu). Người dùng đề xuất: phát hết video 1
    lần, hết thì ĐÓNG BĂNG khung hình CUỐI, giữ nguyên tới khi giọng đọc xong mới chuyển
    cảnh — thay `-stream_loop -1` bằng filter `tpad=stop_mode=clone:stop_duration=
    {duration}` (nhân bản khung hình CUỐI thêm tối đa `duration` giây — luôn ĐỦ dư, vì
    phần thừa sẽ bị `-t duration` cắt bớt ở cuối, không cần biết trước độ dài thật của
    video để tính đúng số giây cần đệm). Vô hại khi video DÀI hơn `duration` (phần đệm
    tpad không bao giờ được đọc tới, `-t duration` đã cắt trước khi chạm tới) — verify
    thật bằng ffmpeg: video test 2s ép tpad+`-t 5` ra đúng 5s, trích frame ở giây 1.96
    (gần cuối clip gốc) và giây 4.9 (trong vùng đệm) giống hệt nhau — xác nhận ĐÓNG BĂNG
    đúng, không lặp lại từ đầu. Xem thêm `_VIDEO_ASSET_EXTS` (trước đây chỉ nhận diện
    `.mp4`, bỏ sót `.webm`/`.mov` mà tính năng upload cũng cho phép — cùng sửa 1 lượt)."""
    is_video = visual_path.lower().endswith(_VIDEO_ASSET_EXTS)

    cmd = [ffmpeg, "-y"]
    cmd += ["-i", visual_path] if is_video else ["-loop", "1", "-i", visual_path]
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
    # `tpad=stop_mode=clone:stop_duration={duration}` CHỈ ở nhánh video (đóng băng khung
    # hình cuối khi video ngắn hơn `duration` — xem bug thật ở docstring trên) — kiểm
    # TRỰC TIẾP `is_video`, KHÔNG dùng `motion_filter` làm điều kiện rẽ nhánh (ảnh tĩnh
    # với `camera_motion="none"` cũng cho `motion_filter is None`, dễ nhầm rơi vào nhánh
    # video nếu chỉ if/else theo `motion_filter` — `-loop 1` của ảnh tạo stream VÔ HẠN,
    # tpad không có ý nghĩa/rủi ro hành vi lạ nếu lỡ áp nhầm, xem bug `blend`/`shortest=1`
    # đã gặp ở `_mix_overlay_effect` làm bài học tương tự về input vô hạn + filter chờ EOF).
    color_grade = _resolve_color_grade_filter(brand)
    grain = _grain_filter_suffix(brand)
    if motion_filter:
        vf = f"{motion_filter},{color_grade},setsar=1{grain}"
    elif is_video:
        vf = f"{_resolve_scale_filter(resolution, brand)},{color_grade},fps={_OUTPUT_FPS}{grain},tpad=stop_mode=clone:stop_duration={duration}"
    else:
        vf = f"{_resolve_scale_filter(resolution, brand)},{color_grade},fps={_OUTPUT_FPS}{grain}"

    cmd += ["-t", str(duration), "-vf", vf, "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p"]
    if narration_path and (narration_lead_in_sec > 0 or narration_lead_out_sec > 0):
        # `adelay` (đệm ĐẦU — trễ điểm phát) áp cho CẢ 2 kênh (`adelay=X|X`, đơn vị ms) —
        # thiếu kênh thứ 2 ffmpeg mặc định chỉ trễ kênh trái, lệch stereo. `apad` (đệm
        # CUỐI — kéo dài track bằng lặng) đặt SAU `adelay` — thứ tự không đổi kết quả ở
        # đây (2 filter không tương tác) nhưng theo đúng thứ tự thời gian dễ đọc hơn.
        delay_ms = round(narration_lead_in_sec * 1000)
        af_parts = []
        if delay_ms > 0:
            af_parts.append(f"adelay={delay_ms}|{delay_ms}")
        if narration_lead_out_sec > 0:
            af_parts.append(f"apad=pad_dur={narration_lead_out_sec:.3f}")
        cmd += ["-af", ",".join(af_parts)]
    cmd += [*_AUDIO_FORMAT_FLAGS, "-c:a", audio_codec, str(out_path)]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def _build_background_video_master(
    ffmpeg: str, source_path: str, total_duration: float, out_path: Path,
    *, resolution: str, video_codec: str, crf: int, brand: dict | None = None,
) -> None:
    """Video nền CHUNG (mới 2026-09-02, theo yêu cầu người dùng) — dựng 1 bản "master" LẶP
    LẠI (`-stream_loop -1`) đúng nguồn user upload cho tới khi phủ hết `total_duration`
    (tổng thời lượng timeline shot list SAU reflow — xem `assemble_video`), scale/color-
    grade CHỈ 1 LẦN ở đây (không lặp lại mỗi lần cắt chunk cho từng shot trống, xem
    `_extract_background_video_chunk`). KHÔNG audio (`-an`) — video nền chỉ lấy HÌNH,
    giọng đọc/nhạc nền vẫn là nguồn audio duy nhất, giống mọi visual video khác trong app
    (đúng nguyên tắc `_build_segment` đã áp dụng)."""
    color_grade = _resolve_color_grade_filter(brand)
    grain = _grain_filter_suffix(brand)
    vf = f"{_resolve_scale_filter(resolution, brand)},{color_grade},fps={_OUTPUT_FPS}{grain},setsar=1"
    cmd = [
        ffmpeg, "-y", "-stream_loop", "-1", "-i", source_path,
        "-t", str(total_duration), "-an", "-vf", vf,
        "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True, timeout=_WHOLE_VIDEO_FFMPEG_TIMEOUT_SEC)


def _build_background_video_playlist(
    ffmpeg: str, source_paths: list[str], transition: str, out_path: Path,
    *, resolution: str, video_codec: str, crf: int, brand: dict | None = None,
) -> None:
    """Nối NHIỀU video nền (mới 2026-09-02, mục 110, theo yêu cầu người dùng "cho phép
    upload nhiều video làm nền") thành 1 "playlist" DUY NHẤT — scale/color-grade TỪNG
    clip TRƯỚC khi nối (khác `_build_background_video_master`, vốn chỉ scale 1 LẦN vì
    trước đây LUÔN đúng 1 nguồn duy nhất), rồi nối bằng cắt cứng ("cut") hoặc `xfade`
    THẬT (transition khác "cut", cùng danh sách `TRANSITIONS` dùng cho shot-to-shot).
    Output làm NGUỒN cho `_build_background_video_master` loop lại nhiều lần SAU đó —
    TÁCH RIÊNG bước này khỏi loop để chỉ phải normalize/xfade 1 LẦN DUY NHẤT, dù
    `-stream_loop -1` sau đó lặp lại bao nhiêu lần.

    CHỈ gọi khi có ≥2 video (caller tự bỏ qua bước này khi chỉ có 1, dùng thẳng video đó
    làm nguồn cho `_build_background_video_master` — giữ NGUYÊN hành vi cũ cho case phổ
    biến nhất). `source_paths` — thứ tự ĐÃ QUYẾT ĐỊNH sẵn bởi caller (xáo trộn 1 lần nếu
    `random_order`, xem `assemble_video`) — hàm này KHÔNG tự xáo trộn.

    KHÔNG audio (`-an`) — cùng nguyên tắc video nền chỉ lấy hình. `transition=="cut"` —
    filter `concat` (nhanh, không blend). Khác "cut" — chain `xfade` giữa các input LIÊN
    TIẾP trong 1 lệnh ffmpeg DUY NHẤT: số lượng video nền thực tế thường nhỏ (vài clip
    B-roll dùng làm nền), KHÔNG tới mức cần kỹ thuật "cắt head/blend tách riêng" mà
    `_xfade_chain` dùng cho pipeline chính (nơi phải xử lý video TÍCH LUỸ dài hàng chục
    phút qua nhiều bước merge tuần tự) — 1 lệnh duy nhất ở quy mô này an toàn về bộ nhớ.
    `t` (độ dài overlap mỗi lần chuyển) kẹp theo cặp clip NGẮN HƠN (tối đa 80% — cùng hệ
    số `_xfade_chain` dùng), tránh overlap nuốt gần hết 1 clip ngắn."""
    vf_each = f"{_resolve_scale_filter(resolution, brand)},{_resolve_color_grade_filter(brand)},fps={_OUTPUT_FPS}{_grain_filter_suffix(brand)},setsar=1"
    n = len(source_paths)
    inputs: list[str] = []
    for src in source_paths:
        inputs += ["-i", src]
    norm_filters = [f"[{i}:v]{vf_each}[v{i}]" for i in range(n)]

    if transition == "cut":
        concat_inputs = "".join(f"[v{i}]" for i in range(n))
        filter_complex = ";".join(norm_filters) + f";{concat_inputs}concat=n={n}:v=1:a=0[outv]"
        out_label = "outv"
    else:
        durations = [_probe_audio_duration_sec(Path(p)) or 3.0 for p in source_paths]
        chain: list[str] = []
        cumulative = durations[0]
        prev_label = "v0"
        for i in range(1, n):
            t = max(0.1, min(_XFADE_DURATION_SEC, durations[i - 1] * 0.8, durations[i] * 0.8))
            offset = max(0.0, cumulative - t)
            step_label = f"x{i}"
            chain.append(f"[{prev_label}][v{i}]xfade=transition={transition}:duration={t:.3f}:offset={offset:.3f}[{step_label}]")
            cumulative = cumulative - t + durations[i]
            prev_label = step_label
        filter_complex = ";".join(norm_filters) + ";" + ";".join(chain)
        out_label = prev_label

    cmd = [
        ffmpeg, "-y", *inputs, "-filter_complex", filter_complex, "-map", f"[{out_label}]",
        "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True, timeout=_WHOLE_VIDEO_FFMPEG_TIMEOUT_SEC)


def _extract_background_video_chunk(
    ffmpeg: str, master_path: Path, start_sec: float, duration_sec: float, out_path: Path, *, video_codec: str, crf: int,
) -> None:
    """Cắt ĐÚNG đoạn `[start_sec, start_sec+duration_sec)` từ `master_path` (đã dựng qua
    `_build_background_video_master`, đã scale/grade sẵn — không cần `-vf` lại ở đây) làm
    nội dung cho 1 shot CHƯA cấu hình visual riêng. `start_sec` là mốc THEO TIMELINE TOÀN
    BỘ shot list (offset cộng dồn qua các shot trước đó), KHÔNG reset về 0 mỗi shot — đúng
    yêu cầu người dùng "loop theo độ dài toàn bộ giọng đọc, không phân biệt cảnh/slot": 1
    shot trống ở giữa video thấy ĐÚNG đoạn nền sẽ hiện nếu không có shot nào che, không
    phải 1 vòng lặp riêng biệt bắt đầu lại từ đầu. `-ss` TRƯỚC `-i` + RE-ENCODE (không
    `-c copy`) — ffmpeg hiện đại seek CHÍNH XÁC ở chế độ này (không snap theo keyframe gần
    nhất như stream-copy), cần thiết để các chunk khớp khít nhau, không hở/đè khi ghép nối
    tiếp qua `_build_segment` (đã kiểm — cùng lý do `_extract_clip` ở asset_vault/ingest.py
    dùng `-ss` trước `-i` cho mốc cắt chính xác)."""
    cmd = [
        ffmpeg, "-y", "-ss", str(start_sec), "-i", str(master_path), "-t", str(duration_sec),
        "-an", "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def _build_intro_segment(
    ffmpeg: str, kind: str, visual_path: str, audio_path: str | None, out_path: Path,
    *, resolution: str, video_codec: str, audio_codec: str, crf: int, brand: dict | None = None,
) -> None:
    """Dựng segment intro (video/audio thương hiệu HOẶC shot mở đầu riêng) — LUÔN có
    audio track (khớp `ensure_audio_track` mọi nơi khác trong assembly dùng để concat/
    xfade an toàn). `kind=="video"` GIỮ NGUYÊN audio gốc của chính file video đó (khác
    `_build_segment` — vốn `-an`/audio ngoài cho video B-roll, không hợp ở đây vì intro
    video có thể là jingle thương hiệu tự có tiếng, KHÔNG được cắt bỏ hay đè narration
    khác lên); `kind=="image"` tái dùng thẳng `_build_segment` (đúng use-case: ảnh tĩnh +
    1 audio ngoài, thời lượng = độ dài audio đo thật qua ffprobe). `brand` — style
    normalization (§9b.2/§9b.3), xem docstring `_build_segment`."""
    if kind == "video":
        cmd = [
            ffmpeg, "-y", "-i", visual_path,
            "-vf", f"{_resolve_scale_filter(resolution, brand)},{_resolve_color_grade_filter(brand)},fps={_OUTPUT_FPS}{_grain_filter_suffix(brand)}",
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
            ensure_audio_track=True, camera_motion="none", brand=brand,
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
    stream-copy giữa nguồn ngoài bất kỳ và nội dung tự sinh trong app.

    **Thử gộp CFR-normalize vào ĐÂY rồi PHẢI HOÀN TÁC (2026-08-26)** — theo yêu cầu người
    dùng cải thiện tốc độ ghép, thử thay bước `body_cfr.{ext}` riêng (mục 79, decode+
    re-encode NGUYÊN body) bằng cách chèn thẳng `fps={_OUTPUT_FPS}` + `aresample=
    async=1:first_pts=0` vào filter graph CHUNG với `concat` — LÝ THUYẾT tưởng tương
    đương (đỡ 1 lượt decode+encode toàn bộ thân video). Verify thật lại ĐÚNG project
    người dùng báo lỗi gốc: bản gộp ra LẠI đúng ~40.3s (hụt shot cuối) — TÁI HIỆN bug cũ,
    KHÔNG tương đương như tưởng. Nguyên nhân nghi ngờ (chưa xác nhận sâu, không đáng đầu
    tư điều tra tiếp vì đã có bằng chứng đủ để loại phương án): file trung gian
    `body_cfr.{ext}` khi ghi THẬT ra đĩa rồi đọc lại có bộ timestamp đã "chốt cứng" qua 1
    lượt mux/demux hoàn chỉnh; filter `fps=` áp trong CÙNG 1 filter graph với `concat`
    (không qua mux/demux trung gian) có vẻ KHÔNG dọn sạch được đúng loại lệch timing gây
    ra bug này. Đã HOÀN TÁC về bản 2-lệnh riêng (giữ nguyên đúng mục 79) — không đánh đổi
    tốc độ lấy đúng đắn. Bài học: dù lý thuyết ffmpeg filter graph nghe hợp lý, PHẢI verify
    thật lại đúng kịch bản bug gốc trước khi tin, không suy luận suông.

    `aformat` ép CẢ 2 audio input về CÙNG sample rate/channel layout TRƯỚC khi vào filter
    `concat` — bản thân `concat` (khác `-c:a`/output) đòi hỏi 2 input khớp định dạng,
    thiếu bước này là chính xác chỗ audio bị hỏng/mất khi 1 bên lệch chuẩn (VD narration
    OmniVoice 24kHz mono) — xem `_AUDIO_FORMAT_FLAGS`."""
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
    *, audio_codec: str, ducking_enabled: bool = False,
) -> None:
    """Trộn nhạc nền vào audio giọng đọc chính — **mới (2026-08-20)**, theo yêu cầu
    người dùng. Video giữ nguyên (`-c:v copy`, không re-encode); CHỈ audio re-encode
    (`amix` bắt buộc decode+trộn thành 1 stream mới). `-stream_loop -1` lặp vô hạn nhạc
    nền (an toàn dù nhạc ngắn hơn nhiều lần so với video) — `amix=duration=first` CHẶN
    ĐÚNG output ở độ dài input ĐẦU (video), đã verify thật bằng ffprobe: không bị kéo dài
    vô hạn theo nhạc nền lặp, không cần thêm `-t`/`-shortest`. `video_path` LUÔN có sẵn
    audio track (`[0:a]`) — `assemble_video` ép `needs_audio_track=True` bất cứ khi nào
    có bg music, giống cách đã làm cho intro/transition.

    `ducking_enabled` — **mới (2026-08-26, CHANGE_Semantic_BRoll_Asset_Vault.md §9b.5)**,
    theo `BrandProfile.bg_music_ducking_enabled` (mặc định `False`, giữ NGUYÊN nhánh cũ
    `amix` volume cố định — KHÔNG đổi hành vi/test đã verify cho kênh chưa bật). Khi bật:
    dùng `sidechaincompress` (bg = main, giọng đọc = sidechain trigger) tự giảm nhạc nền
    khi có giọng đọc, rồi `amix` LẠI với `normalize=0`.

    **Verify thật bằng ffmpeg (không suy đoán tham số)** — dựng audio test: giọng đọc
    giả (khoảng lặng-tiếng-lặng) + nhạc nền hằng định, đo `volumedetect` từng đoạn:
    (1) nhánh ducked ĐỘC LẬP (chưa amix) giảm đúng từ -21.1dB (không giọng đọc) xuống
    -34.5dB (có giọng đọc) rồi về lại -21.1dB — xác nhận `sidechaincompress` hoạt động
    đúng hướng. (2) PHÁT HIỆN QUAN TRỌNG: `amix` có `normalize=true` MẶC ĐỊNH (tự scale
    input để tránh clipping) — nếu để mặc định, đo `volumedetect` trên OUTPUT ĐÃ MIX gần
    như không đổi dù nhánh ducked riêng lẻ đã giảm rõ rệt (tưởng ducking "không có tác
    dụng" — SAI, `amix` normalize âm thầm bù lại). Phải ép `normalize=0` mới giữ được
    hiệu quả ducking khi mix. So sánh control (không ducking, `-18.1dB` khi giọng đọc
    hiện diện — gần bằng tổng 2 nguồn) với ducked (`-20.9dB`, gần bằng giọng đọc ĐƠN LẺ
    `-21.1dB`) xác nhận ducking THẬT SỰ có tác dụng trong bản mix cuối, không chỉ ở
    nhánh riêng. Tham số `threshold=0.05:ratio=8:attack=50:release=400` là điểm khởi đầu
    hợp lý (ducking podcast/video phổ biến) — CHƯA tinh chỉnh với giọng đọc THẬT của
    người dùng, có thể cần chỉnh lại `threshold` nếu giọng đọc nhỏ hơn/lớn hơn mức test."""
    # `aformat` ép cả 2 audio input về CÙNG sample rate/channel layout trước `amix`/
    # `sidechaincompress` — `bg_music_path` là file NGƯỜI DÙNG TỰ UPLOAD (chưa từng qua
    # `_build_segment`, có thể mang sample rate/kênh bất kỳ, khác `video_path` giờ đã
    # LUÔN 44.1kHz stereo nhờ `_AUDIO_FORMAT_FLAGS`) — thiếu bước này dễ trộn sai/mất 1 bên.
    if ducking_enabled:
        filter_complex = (
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[voice_sc][voice_mix];"
            f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={volume}[bg];"
            "[bg][voice_sc]sidechaincompress=threshold=0.05:ratio=8:attack=50:release=400:makeup=1[ducked];"
            "[voice_mix][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
        )
    else:
        filter_complex = (
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
            f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={volume}[bg];"
            "[a0][bg]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", bg_music_path,
        "-filter_complex", filter_complex,
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
    hàm đó chỉ chạy khi CÓ bg_music, lúc đó `needs_audio_track` đã đảm bảo có track).

    `format=gbrp` (planar RGB) trên CẢ 2 nhánh TRƯỚC `blend` — **bug thật phát hiện
    2026-08-23** (người dùng báo "video sau khi thêm layer bị đổi màu toàn bộ sang tím"):
    `blend=all_mode=screen` áp thẳng lên `yuv420p` tính "screen" độc lập trên từng
    plane Y/U/V — SAI vì U/V trung tính là 128 (không phải 0 như Y/RGB), làm méo màu.
    Tưởng chừng ép `format=rgb24` trước `blend` sẽ sửa được (RGB không có vùng trung
    tính lệch tâm) nhưng KHÔNG — đã đo bằng tay: `blend` cho ra kênh U/V lệch CỐ ĐỊNH
    ngay cả khi ép rgb24, tức bản thân ffmpeg build này có lỗi xử lý pixel format
    "rgb24" (packed) trong `blend`. Chuyển sang `format=gbrp` (planar RGB, cùng số liệu
    màu nhưng bố cục plane khác — mỗi kênh 1 plane riêng thay vì đan xen từng pixel) thì
    `blend` tính đúng — xác nhận bằng tay: nền đỏ thuần + overlay xám 50% qua
    `blend=screen` phải ra hồng nhạt (255,128,128), `rgb24` cho (255,59,255) — TÍM SAI,
    `gbrp` cho (255,127,127) — ĐÚNG. Không cần hiểu sâu hơn TẠI SAO ffmpeg build này có
    lỗi riêng với rgb24 — `gbrp` cho kết quả đúng và ổn định qua nhiều lần đo lại."""
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", overlay_path,
        "-filter_complex",
        f"[1:v]{_scale_cover_filter(resolution)},format=gbrp,colorchannelmixer=rr={opacity}:gg={opacity}:bb={opacity}[ovl];"
        "[0:v]format=gbrp[bg];"
        "[bg][ovl]blend=all_mode=screen:shortest=1[v]",
        "-map", "[v]", "-map", "0:a?",
        "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


# Lề (margin) quanh mỗi ô lưới 3x3, tính theo % khung hình — **mới (2026-09-02, mục
# 112)** — dùng biểu thức RUNTIME của ffmpeg nên KHÔNG cần biết trước độ phân giải xuất
# cụ thể, tự đúng tỉ lệ dù xuất 720p/1080p/4K. Tỉ lệ margin GIỐNG NHAU cho cả 2 chế độ
# `overlay` (biến `main_w`/`overlay_w`) và `crop` (biến `in_w`/`out_w`, mục 113) — xem
# `_grid_position_expr`.
_LAYER_MARGIN_FRAC = 0.02


def _grid_position_expr(position: str, *, container_w: str, container_h: str, content_w: str, content_h: str) -> tuple[str, str]:
    """Vị trí lưới 3x3 → biểu thức `x`/`y` DÙNG CHUNG cho cả filter `overlay` (container=
    `main_w`/`main_h`, content=`overlay_w`/`overlay_h`) LẪN filter `crop` (container=
    `in_w`/`in_h`, content=`out_w`/`out_h`, mới mục 113 — xem `_composite_layers` chế độ
    `screen`) — chỉ khác TÊN biến runtime ffmpeg cấp cho từng filter, công thức vị trí
    giống hệt nhau. KHÔNG cần tính pixel cụ thể ở tầng Python — tự đúng dù xuất độ phân
    giải nào."""
    margin_w = f"{_LAYER_MARGIN_FRAC}*{container_w}"
    margin_h = f"{_LAYER_MARGIN_FRAC}*{container_h}"
    x_by_col = {
        "left": margin_w,
        "center": f"({container_w}-{content_w})/2",
        "right": f"{container_w}-{content_w}-{margin_w}",
    }
    y_by_row = {
        "top": margin_h,
        "middle": f"({container_h}-{content_h})/2",
        "bottom": f"{container_h}-{content_h}-{margin_h}",
    }
    if position == "center":
        row, col = "middle", "center"
    else:
        row, col = position.split("-", 1)
    return x_by_col[col], y_by_row[row]


def _layer_target_size(layer: VideoLayer | ImageLayer, *, main_w: int, main_h: int) -> tuple[int, int]:
    """Kích thước PIXEL CỤ THỂ (chẵn) của 1 layer sau khi scale theo `width_pct` — **mới
    (2026-09-02, mục 113)**, dùng cho chế độ `screen` (cần biết TRƯỚC cả width LẪN height
    để `crop` đúng vùng nền tương ứng — khác chế độ `alpha` chỉ cần width, height để
    ffmpeg tự tính qua `-2`). Đo tỉ lệ khung hình GỐC qua ffprobe (`probe_video_
    dimensions` — hoạt động ĐÚNG cho cả ảnh tĩnh, ffmpeg coi ảnh như video 1 khung hình,
    dùng CHUNG được cho `ImageLayer` — mục 115). Lỗi/thiếu ffprobe rơi về giả định 16:9
    (KHÔNG chặn luồng ghép, cùng nguyên tắc `probe_duration_sec`). Kẹp KHÔNG vượt quá
    khung hình chính ở CẢ 2 chiều (giữ tỉ lệ, thu nhỏ theo chiều nào chạm giới hạn trước)
    — layer nguồn dọc (VD 9:16) đặt `width_pct` lớn trên khung ngang 16:9 có thể ra chiều
    cao VƯỢT khung hình chính, filter `crop` sẽ LỖI THẬT nếu vùng cắt lớn hơn nguồn bị
    cắt."""
    dims = probe_video_dimensions(layer.asset_path)
    aspect = (dims[0] / dims[1]) if dims else (16 / 9)
    w = max(2, round(layer.width_pct * main_w / 2) * 2)
    h = max(2, round((w / aspect) / 2) * 2)
    if h > main_h:
        h = main_h - (main_h % 2)
        w = max(2, round((h * aspect) / 2) * 2)
    if w > main_w:
        w = main_w - (main_w % 2)
        h = max(2, round((w / aspect) / 2) * 2)
    return w, h


def _composite_layers(
    ffmpeg: str, video_path: Path, layers: list[VideoLayer], out_path: Path,
    *, resolution: str, video_codec: str, crf: int,
) -> None:
    """Ghép NHIỀU layer video ĐỊNH VỊ (VD voice wave, logo) lên video đã ghép xong —
    **mới (2026-09-02, mục 112)**, theo yêu cầu người dùng: "thêm layer voice wave (dạng
    video loop) vào bên trên video nền", định vị theo lưới 3x3. Cùng nguyên tắc `_mix_
    overlay_effect`/`_mix_bg_music` — bước HẬU KỲ áp 1 LẦN lên `video_path` đã ghép hoàn
    chỉnh (kể cả intro), KHÔNG áp per-shot. Gọi SAU overlay hiệu ứng lớp phủ (nếu có,
    xem `assemble_video`) — layer LUÔN nổi TRÊN CÙNG, không bị mưa/tuyết che.

    2 chế độ blend (`layer.blend_mode`, mục 113 thêm `"screen"` — trước đó CHỈ có
    `"alpha"`, theo yêu cầu người dùng: "tôi chỉ có video layer nền đen thôi, hãy process
    nền đen"):

    - `"alpha"` (mặc định) — nguồn CÓ SẴN KÊNH ALPHA (WebM VP9/MOV ProRes4444 trong
      suốt): `-stream_loop -1` → `scale={w}:-2` (chỉ cần width, `-2` giữ tỉ lệ gốc,
      height ffmpeg tự tính) → `format=yuva420p` (đảm bảo có alpha dù nguồn khác định
      dạng) → `colorchannelmixer=aa={opacity}` (chỉnh độ mờ qua alpha CÓ SẴN) →
      `overlay=x=..:y=..:shortest=1` ĐỊNH VỊ thẳng lên `[prev]`.

    - `"screen"` — nguồn NỀN ĐEN ĐẶC (không alpha, VD clip hiệu ứng stock thông thường):
      dùng ĐÚNG kỹ thuật `_mix_overlay_effect` (nền đen "biến mất" khi blend screen) —
      NHƯNG hàm đó blend TOÀN KHUNG HÌNH (2 input CÙNG kích thước), ở đây cần ĐỊNH VỊ tại
      1 vùng nhỏ nên phải thêm 2 bước: (1) `crop={w}:{h}:{x}:{y}` cắt ĐÚNG vùng nền
      tương ứng vị trí layer từ `[prev]` (dùng CHUNG công thức vị trí với `overlay` qua
      `_grid_position_expr`, chỉ khác tên biến runtime — `in_w/in_h/out_w/out_h` của
      `crop` thay vì `main_w/main_h/overlay_w/overlay_h` của `overlay`), (2)
      `format=gbrp` CẢ 2 nhánh (bài học màu tím sai đã ghi ở `_mix_overlay_effect` — KHÔNG
      dùng `yuv420p`/`rgb24` thẳng cho `blend=screen`) rồi `blend=all_mode=screen:
      shortest=1` cho ra 1 "miếng vá" đã hoà trộn, (3) `overlay` MIẾNG VÁ ĐÓ (không phải
      layer thô) trở LẠI ĐÚNG vị trí đã cắt trên `[prev]` — kết quả: vùng layer đã blend
      screen, phần còn lại của khung hình giữ NGUYÊN không đụng tới. Cần biết TRƯỚC cả
      width lẫn height cụ thể (`_layer_target_size`, dùng ffprobe) vì `crop` không có cơ
      chế "-2 tự tính" như `scale`. Độ mờ chỉnh qua `colorchannelmixer=rr/gg/bb={opacity}`
      TRÊN LAYER trước khi blend (giảm SÁNG — cùng cách `_mix_overlay_effect` làm, vì
      `blend` screen không có tham số alpha trực tiếp).

    Nhiều layer — chain NỐI TIẾP (mỗi layer thao tác trên `[prev]`, kể cả layer `screen`
    cắt/vá đúng đúng vị trí của NÓ trên nền đã có layer trước đó, không ảnh hưởng vùng
    khác) trong 1 lệnh ffmpeg DUY NHẤT (số layer thực tế nhỏ — an toàn bộ nhớ, cùng lý do
    đã áp dụng cho `_build_background_video_playlist`).

    `shortest=1` trên MỌI node `overlay`/`blend` trong chain — bài học đã có từ `_mix_
    overlay_effect`: nguồn layer loop VÔ HẠN (`-stream_loop -1`), nếu thiếu cờ này filter
    mặc định lặp lại frame cuối MÃI MÃI (`eof_action=repeat`) chờ nhánh kia hết trước —
    không có tín hiệu EOF nào để dừng, treo vô thời hạn."""
    main_w, main_h = (int(x) for x in resolution.split(":"))
    inputs: list[str] = ["-i", str(video_path)]
    filters: list[str] = []
    for i, layer in enumerate(layers, start=1):
        inputs += ["-stream_loop", "-1", "-i", layer.asset_path]
        if layer.blend_mode == "screen":
            w, h = _layer_target_size(layer, main_w=main_w, main_h=main_h)
            filters.append(f"[{i}:v]scale={w}:{h},format=gbrp,colorchannelmixer=rr={layer.opacity}:gg={layer.opacity}:bb={layer.opacity}[lyr{i}]")
        else:
            layer_w = max(2, round(layer.width_pct * main_w / 2) * 2)  # số chẵn — yêu cầu chuẩn của hầu hết codec video
            filters.append(f"[{i}:v]scale={layer_w}:-2,format=yuva420p,colorchannelmixer=aa={layer.opacity}[lyr{i}]")

    prev = "0:v"
    for i, layer in enumerate(layers, start=1):
        out_label = f"lcomp{i}" if i < len(layers) else "vout"
        if layer.blend_mode == "screen":
            w, h = _layer_target_size(layer, main_w=main_w, main_h=main_h)
            crop_x, crop_y = _grid_position_expr(layer.position, container_w="in_w", container_h="in_h", content_w="out_w", content_h="out_h")
            ov_x, ov_y = _grid_position_expr(layer.position, container_w="main_w", container_h="main_h", content_w="overlay_w", content_h="overlay_h")
            patch_label = f"lpatch{i}"
            filters.append(f"[{prev}]crop={w}:{h}:{crop_x}:{crop_y},format=gbrp[lbg{i}]")
            filters.append(f"[lbg{i}][lyr{i}]blend=all_mode=screen:shortest=1,format=yuv420p[{patch_label}]")
            filters.append(f"[{prev}][{patch_label}]overlay=x={ov_x}:y={ov_y}:shortest=1[{out_label}]")
        else:
            x_expr, y_expr = _grid_position_expr(layer.position, container_w="main_w", container_h="main_h", content_w="overlay_w", content_h="overlay_h")
            filters.append(f"[{prev}][lyr{i}]overlay=x={x_expr}:y={y_expr}:shortest=1[{out_label}]")
        prev = out_label

    cmd = [
        ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", f"[{prev}]", "-map", "0:a?",
        "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True, timeout=_WHOLE_VIDEO_FFMPEG_TIMEOUT_SEC)


def _composite_image_layers(
    ffmpeg: str, video_path: Path, layers: list[ImageLayer], out_path: Path,
    *, resolution: str, video_codec: str, crf: int,
) -> None:
    """Ghép NHIỀU layer ẢNH (khác `_composite_layers` — layer VIDEO) lên video đã ghép
    xong — **mới (2026-09-02, mục 115)**, theo yêu cầu người dùng: "Layer ảnh định vị
    với chức năng tương tự [layer video]... cho ảnh nền đen hoặc không có nền. Ngoài hỗ
    trợ 9 vị trí layer thì còn hỗ trợ thêm full khung hình". Gọi SAU `_composite_layers`
    (layer video, nếu có) trong hậu kỳ cuối cùng — layer ẢNH LUÔN nổi TRÊN CÙNG mọi layer
    khác.

    Giống HỆT `_composite_layers` về 2 chế độ `blend_mode` (`"alpha"` dùng kênh alpha có
    sẵn của PNG/WEBP qua `overlay` thẳng; `"screen"` cho ảnh nền đen đặc, screen-blend
    cục bộ đúng vùng layer — tái dùng NGUYÊN `_layer_target_size`/`_grid_position_expr`),
    CHỈ khác 2 điểm:

    1. Nguồn LUÔN ảnh tĩnh — `-loop 1` (không phải `-stream_loop -1` của video loop) —
       cùng kỹ thuật `_build_segment` dùng cho shot ảnh, tạo stream VÔ HẠN (`shortest=1`
       vẫn cần y hệt lý do đã ghi ở `_composite_layers`).

    2. `position == "full"` — phủ TOÀN KHUNG HÌNH thay vì định vị 1 ô lưới: scale-cover
       đúng `resolution` xuất (`_scale_cover_filter`, CÙNG hàm `_mix_overlay_effect`
       dùng — KHÔNG phụ thuộc `BrandProfile.aspect_fill_mode`, layer là tính năng độc
       lập). Bỏ qua HẲN `width_pct`. Chế độ `"screen"` với `"full"` — KHÔNG cần bước
       `crop` (vùng cần blend = TOÀN khung hình = chính `[prev]`, không phải 1 phần) nên
       blend THẲNG `[prev]` với layer đã scale-cover, ra LUÔN kết quả cuối — bản chất
       chính là `_mix_overlay_effect` áp dụng cho ảnh tĩnh thay vì video."""
    main_w, main_h = (int(x) for x in resolution.split(":"))
    inputs: list[str] = ["-i", str(video_path)]
    filters: list[str] = []
    for i, layer in enumerate(layers, start=1):
        inputs += ["-loop", "1", "-i", layer.asset_path]
        if layer.position == "full":
            scale_expr = _scale_cover_filter(resolution)
        elif layer.blend_mode == "screen":
            w, h = _layer_target_size(layer, main_w=main_w, main_h=main_h)
            scale_expr = f"scale={w}:{h}"
        else:
            layer_w = max(2, round(layer.width_pct * main_w / 2) * 2)
            scale_expr = f"scale={layer_w}:-2"
        if layer.blend_mode == "screen":
            filters.append(f"[{i}:v]{scale_expr},format=gbrp,colorchannelmixer=rr={layer.opacity}:gg={layer.opacity}:bb={layer.opacity}[lyr{i}]")
        else:
            filters.append(f"[{i}:v]{scale_expr},format=yuva420p,colorchannelmixer=aa={layer.opacity}[lyr{i}]")

    prev = "0:v"
    for i, layer in enumerate(layers, start=1):
        out_label = f"ilcomp{i}" if i < len(layers) else "vout"
        if layer.position == "full":
            if layer.blend_mode == "screen":
                filters.append(f"[{prev}]format=gbrp[ibg{i}]")
                filters.append(f"[ibg{i}][lyr{i}]blend=all_mode=screen:shortest=1,format=yuv420p[{out_label}]")
            else:
                filters.append(f"[{prev}][lyr{i}]overlay=x=0:y=0:shortest=1[{out_label}]")
        elif layer.blend_mode == "screen":
            w, h = _layer_target_size(layer, main_w=main_w, main_h=main_h)
            crop_x, crop_y = _grid_position_expr(layer.position, container_w="in_w", container_h="in_h", content_w="out_w", content_h="out_h")
            ov_x, ov_y = _grid_position_expr(layer.position, container_w="main_w", container_h="main_h", content_w="overlay_w", content_h="overlay_h")
            patch_label = f"ilpatch{i}"
            filters.append(f"[{prev}]crop={w}:{h}:{crop_x}:{crop_y},format=gbrp[ibg{i}]")
            filters.append(f"[ibg{i}][lyr{i}]blend=all_mode=screen:shortest=1,format=yuv420p[{patch_label}]")
            filters.append(f"[{prev}][{patch_label}]overlay=x={ov_x}:y={ov_y}:shortest=1[{out_label}]")
        else:
            x_expr, y_expr = _grid_position_expr(layer.position, container_w="main_w", container_h="main_h", content_w="overlay_w", content_h="overlay_h")
            filters.append(f"[{prev}][lyr{i}]overlay=x={x_expr}:y={y_expr}:shortest=1[{out_label}]")
        prev = out_label

    cmd = [
        ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", f"[{prev}]", "-map", "0:a?",
        "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True, timeout=_WHOLE_VIDEO_FFMPEG_TIMEOUT_SEC)


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
    xứng cả 2 vế, nhưng chưa có bằng chứng cần tới mức đó, không over-engineer trước.

    **Bug thật (2026-08-27)**: người dùng báo mất ~2s giọng đọc ở SHOT CUỐI CÙNG trên 1
    project dài, nhiều ranh giới transition (16 run/15 lần merge). Root cause xác nhận
    bằng cross-correlation thật (không suy đoán) giữa audio nguồn (`B29.wav`) và audio
    trong video ghép ra: `current_duration` trước đây CHỈ cộng dồn LÝ THUYẾT
    (`run_durations[]` — giá trị DỰ ĐỊNH, tính từ kịch bản/giọng đọc/reflow, KHÔNG phải
    đo thật từ file `current_path` sau mỗi bước `_concat_fast`/`xfade`) — mỗi bước
    encode/stream-copy có thể lệch NHẸ so với lý thuyết (làm tròn frame ở `-t`, GOP/
    keyframe alignment của encoder, hành vi nội bộ của filter `acrossfade`/`xfade`) —
    verify thật: dựng lại ĐÚNG project lỗi, đo qua ffprobe thấy `current_duration` lý
    thuyết trôi lệch ~2.08s so với thời lượng THẬT của `current_path` chỉ sau 15 lần
    merge. Lệch NHẸ ở đa số project (bù trừ 2 chiều qua nhiều bước) nhưng có thể cộng dồn
    CÙNG CHIỀU trên project nhiều transition — khi `current_duration` (lý thuyết) VƯỢT
    quá thời lượng thật, `head_keep = current_duration - t` tính RA LỚN HƠN nội dung thật
    có trong `current_path`, khiến `-ss head_keep` ở `blend_cmd` SEEK QUÁ đoạn nội dung
    thật (kể cả đệm lặng bảo vệ giọng đọc, xem `narration_lead_out_sec`) — mất thật 1
    phần cuối giọng đọc của run TRƯỚC ranh giới, rõ nhất ở LẦN MERGE CUỐI (gộp shot cuối
    cùng, không còn run nào sau để "che" phần mất). Fix: đo lại `current_duration` THẬT
    bằng ffprobe (`_probe_audio_duration_sec`) ngay ĐẦU mỗi vòng lặp — tự sửa sai số tích
    luỹ ở MỌI bước thay vì chỉ tin phép cộng lý thuyết, loại bỏ hẳn khả năng trôi lệch dù
    nguyên nhân gốc (làm tròn/encoder/filter) là gì. Fallback về giá trị lý thuyết nếu
    ffprobe lỗi/thiếu binary (không chặn luồng ghép, cùng nguyên tắc `probe_duration_sec`)."""
    n = len(run_paths)
    current_path = run_paths[0]
    current_duration = run_durations[0]
    to_cleanup: list[Path] = []
    try:
        for i in range(1, n):
            # Đo lại THẬT (không tin phép cộng lý thuyết đã trôi lệch dần) — xem bug thật
            # ở docstring trên.
            measured_duration = _probe_audio_duration_sec(current_path)
            if measured_duration is not None:
                current_duration = measured_duration
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
    vp9), `ValueError` ở đây chỉ là lưới an toàn thứ 2 (VD gọi trực tiếp ngoài router).

    **Lưới an toàn `_assembly_in_progress` (mới 2026-09-02, mục 111)** — bug thật người
    dùng báo: 1 project dài (~28 phút, 61 shot) bị "treo" ở `assembly_status="assembling"`
    MÃI MÃI — thread chạy hàm này đã CHẾT ngay sau khi dựng xong `_bg_master.mp4` (file
    3.4GB tồn tại thật trên đĩa, nhưng KHÔNG có tiến trình ffmpeg nào còn chạy), TRƯỚC KHI
    kịp lưu tiến độ tiếp theo — try/except/finally nội bộ bên dưới (đã có sẵn, xử lý mọi
    `Exception` bình thường) KHÔNG bắt được (nghi ngờ 1 lỗi tầng thấp hơn Python exception
    thường, VD crash khi encode UnicodeEncodeError lúc log ra console cp1252 — xem
    `electron/src/backend-launcher.ts::PYTHONIOENCODING`). VÌ `render/assemble` gate hoàn
    toàn dựa vào `state.assembly_status` ĐÃ LƯU (khác `run_asset_generation`'s `_in_
    progress`/`_mark_in_progress` — set TRONG BỘ NHỚ, tự về rỗng khi tiến trình backend
    khởi động lại) — 1 lần "chết lặng" như vậy khiến project bị khoá CỨNG, không cách nào
    bấm ghép lại được nữa kể cả sau khi khởi động lại app (trạng thái "assembling" vẫn còn
    y nguyên trong render.json), phải sửa tay file. `_mark_assembly_in_progress`/`_mark_
    assembly_done` (set TRONG BỘ NHỚ, giống hệt cơ chế `_in_progress` đã có) — `router.py::
    start_assemble` giờ CHỈ chặn 409 khi field NÀY còn `True` (tiến trình THẬT SỰ đang
    chạy), KHÔNG còn tin mù quáng field đã lưu — nếu tiến trình backend khởi động lại
    (đóng/mở lại app) HOẶC hàm chạy hết dù lỗi gì (finally luôn dọn cờ trừ khi tiến trình
    bị kill cứng — trường hợp đó khởi động lại app cũng tự dọn), field này tự về `False`,
    project TỰ PHỤC HỒI mà không cần sửa tay."""
    _mark_assembly_in_progress(project_id)
    try:
        _assemble_video_impl(project_id, resolution=resolution, codec=codec, quality=quality, use_gpu=use_gpu)
    finally:
        _mark_assembly_done(project_id)


def _assemble_video_impl(
    project_id: str, *,
    resolution: Resolution = "1080p",
    codec: Codec = "h264",
    quality: Quality = "medium",
    use_gpu: bool = False,
) -> None:
    """Thân hàm THẬT của `assemble_video` — tách riêng (2026-09-02, mục 111) chỉ để bọc
    `_mark_assembly_in_progress`/`_mark_assembly_done` ở ngoài CÙNG mà không phải re-indent
    lại toàn bộ hàm gốc (~400 dòng). Xem docstring `assemble_video` cho lý do/thiết kế đầy
    đủ — hàm này giữ NGUYÊN 100% logic cũ."""
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
            # Video nền chung (mới 2026-09-02) — KHÔNG có cấp kênh mặc định để "resolve"
            # như 3 nguồn trên, đọc THẲNG từ project — xem docstring `BackgroundVideoOverride`.
            # Nhiều video (mới 2026-09-02, mục 110) — `asset_paths` (list) thay `asset_path`
            # đơn cũ.
            background_video_paths = state.background_video.asset_paths if state.background_video else []

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
            # `background_video_source` (mới 2026-09-02, theo yêu cầu người dùng) — shot
            # CHƯA có visual riêng KHÔNG còn bị chặn cứng nếu có video nền chung để lấp
            # vào (xem `_build_background_video_master`/`_extract_background_video_chunk`
            # dưới) — shot ĐÃ có visual riêng vẫn giữ NGUYÊN yêu cầu ready+approved như cũ
            # (video nền không thay thế human-gate cho nội dung ĐÃ cấu hình).
            statuses: list[ShotRenderStatus] = []
            durations: list[float] = []
            for shot in shots:
                status = by_id.get(shot["shot_id"])
                has_own_visual = bool(status and status.visual_asset_path)
                if has_own_visual:
                    if status.visual_status != "ready":
                        raise RuntimeError(f"Shot {shot['shot_id']} chưa sinh xong visual — không thể ghép.")
                    # Không còn gate theo `approved` (2026-09-02, theo yêu cầu người dùng —
                    # bỏ luồng duyệt block, chỉ cần visual "ready" là ghép được). Field
                    # `approved`/nút "Duyệt" vẫn giữ lại trên UI như cờ đánh dấu tuỳ chọn,
                    # không còn chặn render.
                elif not background_video_paths:
                    raise RuntimeError(f"Shot {shot['shot_id']} chưa sinh xong visual — không thể ghép.")
                status = status or ShotRenderStatus(shot_id=shot["shot_id"])
                statuses.append(status)
                durations.append(_shot_base_duration(status, _find_beat(pack, shot)))

            _reflow_video_durations(statuses, durations)

            # Đệm lặng đầu/cuối giọng đọc tại ranh giới transition — **mới (2026-08-23)**,
            # bug thật người dùng báo: bật transition (khác "cut") giữa các shot làm giọng
            # đọc "nuốt chữ" ở cả đầu lẫn cuối shot. Tính SAU `_reflow_video_durations`
            # (không phải TRƯỚC) — đệm là lớp phủ THÊM, không phải 1 phần độ dài video
            # thật cần khớp; cộng vào TRƯỚC reflow sẽ khiến reflow hiểu lầm đệm là lệch
            # cần vay/trả từ shot liền kề, vô tình xoá mất đệm vừa thêm. Chỉ đệm shot CÓ
            # giọng đọc thật (shot câm không có gì để bảo vệ, đệm vào chỉ tốn thời lượng
            # vô ích). Giá trị đệm = `_XFADE_DURATION_SEC` (mức TỐI ĐA `t` có thể đạt tới
            # trong `_xfade_chain`) — đủ để `t` (luôn ≤ giá trị này) không bao giờ chạm
            # tới lời thoại thật, kể cả khi `_xfade_chain` không co hẹp `t` xuống. Xem chi
            # tiết cơ chế trong docstring `_build_segment`.
            intro_transition = ((state.intro.transition_to_next if state.intro else None) or "cut") if intro_source else "cut"
            lead_ins: list[float] = []
            lead_outs: list[float] = []
            for i, shot in enumerate(shots):
                has_narration = statuses[i].narration_status == "ready" and bool(statuses[i].narration_asset_path)
                needs_lead_in = has_narration and (
                    (i == 0 and intro_transition != "cut") or (i > 0 and (shots[i - 1].get("transition_to_next") or "cut") != "cut")
                )
                needs_lead_out = has_narration and i < len(shots) - 1 and (shot.get("transition_to_next") or "cut") != "cut"
                lead_in = _XFADE_DURATION_SEC if needs_lead_in else 0.0
                lead_out = _XFADE_DURATION_SEC if needs_lead_out else 0.0
                lead_ins.append(lead_in)
                lead_outs.append(lead_out)
                durations[i] += lead_in + lead_out

            # Video nền chung — dựng "master" đã loop+scale/grade SẴN (1 lần), rồi cắt
            # ĐÚNG đoạn theo offset cộng dồn trên timeline cho từng shot CHƯA có visual
            # riêng (mới 2026-09-02, xem docstring `BackgroundVideoOverride`/`_build_
            # background_video_master`). Đặt SAU đệm lead-in/out (đã cộng vào `durations`)
            # để chunk cắt ra khớp CHÍNH XÁC độ dài segment cuối cùng — lệch 1 khung hình
            # cũng đủ làm timeline toàn video trôi dần qua nhiều shot.
            background_chunk_paths: dict[int, Path] = {}
            blank_indices = [i for i, s in enumerate(statuses) if not s.visual_asset_path]
            if background_video_paths and blank_indices:
                # Stage riêng (2026-09-02, mục 108) — TRƯỚC ĐÂY bước này chạy trong lúc
                # `assembly_progress` vẫn đứng ở `stage="segments", current=0` (đặt sẵn ở
                # trên cho có total ngay), khiến UI hiện nhầm "Đang ghép cảnh 0/N..." dù
                # segment thật CHƯA hề bắt đầu — dựng master (có thể mất vài phút với
                # video dài, re-encode phủ hết `sum(durations)`) là bước CHẬM NHẤT trong
                # cả assembly nếu có dùng video nền, cần label riêng để không gây hiểu
                # lầm "bị treo". Đơn vị tự nhiên: 1 (dựng playlist, CHỈ khi ≥2 video — mới
                # mục 110) + 1 (dựng master) + 1/chunk cắt.
                bg_stage_started_at = vn_isoformat(datetime.now(timezone.utc))
                needs_playlist = len(background_video_paths) > 1
                bg_total = (2 if needs_playlist else 1) + len(blank_indices)
                state.assembly_progress = AssemblyProgress(stage="background_video", current=0, total=bg_total, stage_started_at=bg_stage_started_at)
                save_render_state(pdir, state)

                bg_done = 0
                if needs_playlist:
                    # Nhiều video (mới 2026-09-02, mục 110, theo yêu cầu người dùng) —
                    # xáo trộn thứ tự 1 LẦN DUY NHẤT cho lượt ghép này nếu bật random_order
                    # (KHÔNG mutate `asset_paths` gốc — thứ tự upload trên UI giữ nguyên,
                    # chỉ đổi thứ tự dùng lúc RENDER), rồi nối lại thành 1 playlist trước
                    # khi loop — xem docstring `_build_background_video_playlist`.
                    ordered_paths = list(background_video_paths)
                    if state.background_video.random_order:
                        random.shuffle(ordered_paths)
                    playlist_path = segments_dir / f"_bg_playlist.{ext}"
                    _build_background_video_playlist(
                        ffmpeg, ordered_paths, state.background_video.transition, playlist_path,
                        resolution=scale, video_codec=video_codec, crf=crf, brand=brand,
                    )
                    bg_master_source = str(playlist_path)
                    bg_done = 1
                    state.assembly_progress = AssemblyProgress(stage="background_video", current=bg_done, total=bg_total, stage_started_at=bg_stage_started_at)
                    save_render_state(pdir, state)
                else:
                    bg_master_source = background_video_paths[0]

                bg_master_path = segments_dir / f"_bg_master.{ext}"
                _build_background_video_master(
                    ffmpeg, bg_master_source, sum(durations), bg_master_path,
                    resolution=scale, video_codec=video_codec, crf=crf, brand=brand,
                )
                bg_done += 1
                state.assembly_progress = AssemblyProgress(stage="background_video", current=bg_done, total=bg_total, stage_started_at=bg_stage_started_at)
                save_render_state(pdir, state)

                cumulative = 0.0
                for i in range(len(shots)):
                    if i in blank_indices:
                        chunk_path = segments_dir / f"_bg_chunk_{i:03d}.{ext}"
                        _extract_background_video_chunk(ffmpeg, bg_master_path, cumulative, durations[i], chunk_path, video_codec=video_codec, crf=crf)
                        background_chunk_paths[i] = chunk_path
                        bg_done += 1
                        state.assembly_progress = AssemblyProgress(stage="background_video", current=bg_done, total=bg_total, stage_started_at=bg_stage_started_at)
                        save_render_state(pdir, state)
                    cumulative += durations[i]

            # --- Pass 2: build từng segment theo độ dài đã reflow + đệm — SONG SONG
            # (xem `_SEGMENT_BUILD_WORKERS`) — mỗi shot độc lập hoàn toàn, chỉ `seg_paths`
            # (điền theo ĐÚNG thứ tự index, không theo thứ tự hoàn thành) và
            # `assembly_progress` (đếm số đã xong, dùng khoá) là trạng thái CHUNG cần
            # đồng bộ giữa các luồng. Reset LẠI `stage_started_at` ngay TRƯỚC KHI luồng
            # segment thật bắt đầu (2026-09-02, mục 108) — nếu không, ước lượng thời gian
            # còn lại ở FE (`RenderStudio.tsx::remainingSec`, tính elapsed/segment trung
            # bình) sẽ TÍNH GỘP luôn thời gian đã tốn ở bước dựng video nền phía trên,
            # thổi phồng sai lệch ETA cho các segment còn lại.
            segments_stage_started_at = vn_isoformat(datetime.now(timezone.utc))
            state.assembly_progress = AssemblyProgress(stage="segments", current=0, total=total, stage_started_at=segments_stage_started_at)
            save_render_state(pdir, state)
            def _build_one_segment(i: int, shot: dict) -> Path:
                status = statuses[i]
                duration = durations[i]
                narration_path = status.narration_asset_path if status.narration_status == "ready" else None
                seg_path = segments_dir / f"segment_{i:03d}.{ext}"
                # Shot chưa có visual riêng + đang dùng video nền chung → đoạn nền ĐÃ cắt
                # sẵn (xem trên) đóng vai trò "visual của shot" cho ĐÚNG khung thời gian
                # này — thay thế TOÀN MÀN HÌNH khi shot CÓ visual riêng (nhánh else giữ
                # nguyên hành vi cũ 100%), không phải chồng mờ/PiP.
                visual_path = status.visual_asset_path or str(background_chunk_paths[i])
                _build_segment(
                    ffmpeg, visual_path, narration_path, duration, seg_path,
                    resolution=scale, video_codec=video_codec, audio_codec=audio_codec, crf=crf,
                    ensure_audio_track=needs_audio_track, camera_motion=shot.get("camera_motion") or "none",
                    narration_lead_in_sec=lead_ins[i], narration_lead_out_sec=lead_outs[i], brand=brand,
                )
                return seg_path

            seg_paths_by_index: dict[int, Path] = {}
            progress_lock = threading.Lock()
            with ThreadPoolExecutor(max_workers=_SEGMENT_BUILD_WORKERS) as executor:
                futures = {executor.submit(_build_one_segment, i, shot): i for i, shot in enumerate(shots)}
                for future in as_completed(futures):
                    i = futures[future]
                    seg_paths_by_index[i] = future.result()  # re-raise lỗi (nếu có) NGAY ở luồng chính, giữ nguyên hành vi "1 shot lỗi thì dừng cả assembly" như trước
                    with progress_lock:
                        state.assembly_progress = AssemblyProgress(stage="segments", current=len(seg_paths_by_index), total=total, stage_started_at=segments_stage_started_at)
                        save_render_state(pdir, state)

            seg_paths = [seg_paths_by_index[i] for i in range(total)]

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
                state.assembly_progress = AssemblyProgress(stage="concat", current=total, total=total, stage_started_at=vn_isoformat(datetime.now(timezone.utc)))
                save_render_state(pdir, state)
                list_path = pdir / "renders" / "list.txt"
                list_path.write_text("\n".join(f"file '{p.as_posix()}'" for p in seg_paths), encoding="utf-8")
                concat_cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(body_path)]
                subprocess.run(concat_cmd, capture_output=True, check=True, text=True)
            else:
                # Có transition — gộp shot liên tiếp nối bằng "cut" thành từng "run" (fast
                # concat, không blend), rồi nối các run lại bằng xfade/acrossfade THẬT tại
                # đúng những ranh giới người dùng chọn transition (xem _run_boundaries).
                state.assembly_progress = AssemblyProgress(stage="concat", current=total, total=total, stage_started_at=vn_isoformat(datetime.now(timezone.utc)))
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
                # **Bug thật (2026-08-23, mở rộng 2026-08-26)**: người dùng báo shot CUỐI
                # (ảnh + giọng đọc) "biến mất" khỏi video ghép — có intro RIÊNG. Xác nhận
                # nguyên nhân gốc bằng ffprobe/ffmpeg thật (không suy đoán): `body_path`
                # mang video track TẦN SỐ KHUNG HÌNH KHÔNG ỔN ĐỊNH (`avg_frame_rate` ra
                # phân số lẻ kiểu "1648640/55011" thay vì "30/1" sạch). Khi
                # `_concat_intro_and_body` bên dưới đưa `body_path` (mang lệch này) qua
                # filter `concat` cùng `intro_path` (CFR sạch), ffmpeg gặp audio DTS không
                # tăng đơn điệu ("Non-monotonic DTS") và tự ý DROP hẳn frame video cuối (mất
                # TOÀN BỘ hình + tiếng shot cuối) để ép lại đơn điệu — không lỗi/log gì hiện
                # ra ở `assembly_error` (ffmpeg vẫn exit code 0, "drop" chỉ in ra stdout
                # summary không phải stderr lỗi).
                #
                # Bản fix đầu (2026-08-23) chỉ áp dụng CFR-normalize khi `has_transitions`
                # (nhánh `_xfade_chain`, nguồn lệch timestamp rõ ràng nhất) — kết luận nhánh
                # KHÔNG-transition (concat DEMUXER `-c copy` ghép thẳng các segment từ
                # `_build_segment`) "không gặp lệch này" vì mọi segment cùng nguồn 1 pattern
                # lệnh ffmpeg. Kết luận đó SAI — tái hiện lại đúng bug (mất shot cuối, hụt
                # đúng bằng độ dài shot cuối) trên project THẬT của người dùng ở ĐÚNG nhánh
                # không-transition này: concat DEMUXER `-c copy` giữ NGUYÊN timestamp gốc
                # từng segment thay vì viết lại liền mạch, nên `body_path` vẫn có thể mang
                # timebase/DTS không đều tuỳ input gốc (VD ảnh PNG kích thước lệch chuẩn),
                # KHÔNG chỉ riêng đường `_xfade_chain`. Chuyển CFR-normalize ra ÁP DỤNG
                # MỌI khi có intro (bất kể `has_transitions`) — verify thật: dựng lại CHÍNH
                # project người dùng báo lỗi với transition "cut" (đúng cấu hình lúc lỗi),
                # thiếu bước này ra đúng 40.3s (thiếu ~2.4s = hụt nguyên shot cuối), có bước
                # này ra đủ ~44.6s (khớp lý thuyết, còn shot cuối).
                #
                # **Đã THỬ gộp bước này vào `_concat_intro_and_body` (2026-08-26, theo yêu
                # cầu cải thiện tốc độ) rồi PHẢI HOÀN TÁC** — verify thật lại đúng project
                # gây bug gốc cho kết quả SAI (tái hiện lại mất shot cuối, ~40.3s thay vì
                # ~44.6s) dù lý thuyết tưởng tương đương. Giữ NGUYÊN bản 2-lệnh riêng này —
                # xem chi tiết ở docstring `_concat_intro_and_body`. Bài học: ĐÚNG ĐẮN
                # (không mất dữ liệu) quan trọng hơn tốc độ — không đánh đổi khi chưa verify
                # được cách nào an toàn hơn.
                cfr_body_path = pdir / "renders" / f"body_cfr.{ext}"
                normalize_cmd = [
                    ffmpeg, "-y", "-i", str(body_path),
                    "-vsync", "cfr", "-r", str(_OUTPUT_FPS),
                    "-af", "aresample=async=1:first_pts=0",
                    "-c:v", video_codec, *_quality_flags(video_codec, crf), "-pix_fmt", "yuv420p",
                    *_AUDIO_FORMAT_FLAGS,
                    "-c:a", audio_codec,
                    str(cfr_body_path),
                ]
                subprocess.run(normalize_cmd, capture_output=True, check=True, text=True)
                body_path.unlink(missing_ok=True)
                body_path = cfr_body_path

                intro_kind, intro_visual, intro_audio = intro_source
                intro_path = pdir / "renders" / f"intro_segment.{ext}"
                _build_intro_segment(
                    ffmpeg, intro_kind, intro_visual, intro_audio, intro_path,
                    resolution=scale, video_codec=video_codec, audio_codec=audio_codec, crf=crf, brand=brand,
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
                ducking_enabled = bool(brand.get("bg_music_ducking_enabled"))
                _mix_bg_music(ffmpeg, final_path, bg_path, bg_volume, mixed_path, audio_codec=audio_codec, ducking_enabled=ducking_enabled)
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

            if state.layers:
                # Layer video định vị (VD voice wave, logo) — **mới (2026-09-02, mục
                # 112)**, theo yêu cầu người dùng. Áp SAU overlay hiệu ứng lớp phủ (nếu
                # có ở trên) — layer LUÔN nổi TRÊN CÙNG, không bị mưa/tuyết che. Cùng
                # nguyên tắc ghi-đè-tại-chỗ như bg_music/overlay ở trên.
                layered_path = pdir / "renders" / f"final_layered.{ext}"
                _composite_layers(ffmpeg, final_path, state.layers, layered_path, resolution=scale, video_codec=video_codec, crf=crf)
                final_path.unlink(missing_ok=True)
                layered_path.rename(final_path)

            if state.image_layers:
                # Layer ẢNH định vị (9 ô lưới HOẶC toàn khung hình) — **mới (2026-09-02,
                # mục 115)**, theo yêu cầu người dùng. Áp SAU layer video (nếu có ở trên)
                # — layer ẢNH LUÔN nổi TRÊN CÙNG mọi layer khác. Cùng nguyên tắc ghi-đè-
                # tại-chỗ như các bước hậu kỳ khác.
                image_layered_path = pdir / "renders" / f"final_image_layered.{ext}"
                _composite_image_layers(ffmpeg, final_path, state.image_layers, image_layered_path, resolution=scale, video_codec=video_codec, crf=crf)
                final_path.unlink(missing_ok=True)
                image_layered_path.rename(final_path)

            # Chuẩn hoá loudness EBU R128 — **mới (2026-08-26, §9b.5)** — bước hậu kỳ
            # CUỐI CÙNG (sau bg_music/overlay), LUÔN áp dụng (không cần cấu hình
            # BrandProfile — chuẩn hoá kỹ thuật thuần tuý cho mọi video xuất ra, không
            # phải lựa chọn thẩm mỹ như grain/color-grade). Video giữ nguyên (`-c:v
            # copy`); CHỈ audio re-encode. Verify thật: `loudnorm=I=-14:TP=-1.0:LRA=11`
            # đo bằng `print_format=json` trên tín hiệu test ra `output_i≈-13.95 LUFS`
            # (khớp mục tiêu -14, sai số làm tròn bình thường của chế độ 1-pass).
            normalized_path = pdir / "renders" / f"final_normalized.{ext}"
            loudnorm_cmd = [
                ffmpeg, "-y", "-i", str(final_path),
                "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
                "-c:v", "copy",
                *_AUDIO_FORMAT_FLAGS,
                "-c:a", audio_codec,
                str(normalized_path),
            ]
            subprocess.run(loudnorm_cmd, capture_output=True, check=True, text=True)
            final_path.unlink(missing_ok=True)
            normalized_path.rename(final_path)

            state.final_video_path = str(final_path)
            state.assembly_status = "done"
            state.assembly_completed_at = vn_isoformat(datetime.now(timezone.utc))
        except subprocess.CalledProcessError as e:
            state.assembly_status = "error"
            # Bug thật (2026-08-17, mục 43): `[:1000]` LẤY ĐẦU chuỗi — stderr ffmpeg luôn
            # mở đầu bằng banner version+configuration (thường DÀI HƠN 1000 ký tự), nên
            # lý do lỗi thật (luôn nằm ở CUỐI stderr) bị cắt mất hoàn toàn, chỉ còn lại
            # banner vô nghĩa (đã thấy thật khi điều tra lỗi assembly của người dùng — xem
            # ghi chú `_build_segment`). Đổi sang lấy ĐUÔI chuỗi.
            state.assembly_error = f"ffmpeg lỗi: {(e.stderr or '').strip()[-2000:]}"
        except subprocess.TimeoutExpired as e:
            # **Mới (2026-09-02, mục 111)** — lưới an toàn cho bước dựng video nền chung
            # (`_build_background_video_master`/`_build_background_video_playlist`, đơn
            # timeout ở đó) — nếu ffmpeg treo THẬT (không phải chết lặng như bug đã gặp,
            # mà đứng yên mãi vì input hỏng/deadlock/tài nguyên) sẽ bị KILL sau ngưỡng
            # thay vì "assembling" kẹt vô thời hạn, biến 1 lần treo thật thành lỗi RÕ
            # RÀNG người dùng thấy ngay + tự bấm ghép lại được (không cần "Đặt lại tiến
            # trình bị treo" nữa vì lần này trạng thái tự chuyển "error" đàng hoàng).
            state.assembly_status = "error"
            state.assembly_error = f"ffmpeg chạy quá lâu (quá {int(e.timeout)}s) và đã bị dừng — có thể do file nguồn lỗi hoặc máy quá tải. Thử lại hoặc kiểm tra lại video/ảnh nguồn."
        except Exception as e:  # noqa: BLE001
            state.assembly_status = "error"
            state.assembly_error = str(e)
        finally:
            state.assembly_started_at = None
            save_render_state(pdir, state)
    finally:
        db.close()
