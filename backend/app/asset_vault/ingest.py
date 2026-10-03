"""Ingestion pipeline cho Kho Tài Nguyên — CHANGE_Semantic_BRoll_Asset_Vault.md §3 giai
đoạn A (Ingestion & Scene Detection) + phần đầu giai đoạn B (Vision + Vector Indexing).
KHÔNG tự động quét/tải video nào — mọi `RawVideo` chỉ được tạo khi user chủ động upload
hoặc dán URL + xác nhận tường minh (§1), không có job nền nào tự gọi các hàm
`import_raw_video_*`/`download_raw_video_from_url` mà không qua 1 request HTTP thật của
người dùng.

**Đổi thành kho TOÀN CỤC + gắn nhiều kênh dạng tag (2026-08-27)** — mọi hàm import giờ
nhận `channel_ids: list[str]` (≥1, validate ở router) thay vì 1 `channel_id` đơn, gán vào
`RawVideo.channels` (m2m, `models.py::raw_video_channel`). `ProcessedClip` không còn
`channel_id` riêng — kế thừa kênh của `raw_video` cha.

**Tiến trình THẬT (2026-08-27)** — trước đây chỉ có 4 trạng thái thô, giờ
`RawVideo.progress_current`/`progress_total`/`progress_label` được cập nhật thật trong
lúc tải (yt-dlp `progress_hooks`) và lúc cắt cảnh (PySceneDetect `callback=` cho bước
phát hiện, đếm vòng lặp cho bước cắt) — throttle commit DB (không ghi mỗi callback, quá
tốn — chỉ ghi khi đổi ĐỦ nhiều hoặc cách lần trước ≥0.4s).

Cắt cảnh THỦ CÔNG (`manual_cut_clip`) và TỰ ĐỘNG (`auto_detect_scenes`, PySceneDetect)
CÙNG tồn tại — không phải "Phase A thay bằng Phase B", người dùng chọn cách nào phù hợp
với từng video (đặc biệt footage archival chất lượng thấp mà `AdaptiveDetector` có thể
cắt sai, câu hỏi mở #4 của change-spec)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.asset_vault.vector_store import delete_clip_vector, upsert_clip_vector
from app.config import asset_vault_clips_dir, asset_vault_raw_dir
from app.filestore import write_bytes
from app.models import Channel, ProcessedClip, RawVideo
from app.providers.factory import get_embedding, get_vision
from app.render.media_probe import probe_duration_sec
from app.watermark.pipeline import remove_watermark_from_video

_CAPTION_PROMPT = (
    "Describe briefly the action/setting/main subject in this frame in English, then "
    "list 3-6 short keyword tags, then 1 mood_tone word (e.g. dark, epic, calm, tense, "
    "joyful)."
)

_RAW_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi")
_PROGRESS_COMMIT_INTERVAL_SEC = 0.4


def _new_id(prefix: str) -> str:
    # Hậu tố hex ngẫu nhiên (2026-09-12) — bug thật gặp lúc chạy full test suite nhanh:
    # 2 hàng tạo trong CÙNG 1 mili giây (VD batch import nhiều clip liên tiếp) nhận
    # TRÙNG `int(time.time()*1000)`, insert thứ 2 lỗi `UNIQUE constraint failed`. Rủi ro
    # thật ngoài đời cũng có (bấm nút tạo hàng loạt rất nhanh liên tiếp), không chỉ do
    # test chạy nhanh.
    return f"{prefix}_{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._À-ỹ-]+")


def _sanitize_filename_stem(original_filename: str, max_len: int = 60) -> str:
    """Rút gọn tên file gốc thành 1 chuỗi AN TOÀN để ghép vào tên file thật trên đĩa (giữ
    lại chữ có dấu tiếng Việt — dải Unicode `\\u00C0-\\u1EF9` — vì Windows/NTFS/ext4 đều
    chấp nhận Unicode trong tên file, chỉ cần lọc ký tự THẬT SỰ nguy hiểm: `/ \\ : * ? " <
    > |` và khoảng trắng). Rỗng sau khi lọc (VD tên gốc toàn ký tự lạ) → fallback "video"
    để không tạo tên file kết thúc bằng dấu `_` trơ trọi."""
    stem = Path(original_filename).stem
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", stem).strip("_")
    return (cleaned or "video")[:max_len]


def _ensure_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Chưa cài ffmpeg trên máy chạy backend — xem README.md.")
    return ffmpeg


def _load_channels(db: Session, channel_ids: list[str]) -> list[Channel]:
    """Không lặng lẽ bỏ qua id sai — báo lỗi rõ nếu 1 trong các channel_id gửi lên không
    tồn tại, giúp bắt lỗi frontend sớm thay vì âm thầm gắn thiếu tag."""
    channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all()
    found_ids = {c.id for c in channels}
    missing = set(channel_ids) - found_ids
    if missing:
        raise ValueError(f"Không tìm thấy kênh: {', '.join(missing)}")
    return channels


def _clear_progress(raw: RawVideo) -> None:
    raw.progress_current = None
    raw.progress_total = None
    raw.progress_label = None


# ---------------------------------------------------------------------------
# Giai đoạn A.1 — Import raw video
# ---------------------------------------------------------------------------
def import_raw_video_upload(db: Session, channel_ids: list[str], filename: str, data: bytes, import_note: str = "") -> RawVideo:
    """`filename` — tên file THẬT lúc user chọn trên máy — lưu NGUYÊN VẸN vào
    `original_filename` (chỉ để hiển thị) và ghép bản ĐÃ LỌC KÝ TỰ NGUY HIỂM vào tên file
    thật trên đĩa (`{raw_id}_{tên_gốc_đã_lọc}{ext}`) — người dùng xem thư mục lưu trữ qua
    nút "Mở thư mục" vẫn nhận ra ĐÚNG file mình đã upload, không chỉ 1 ID vô nghĩa."""
    channels = _load_channels(db, channel_ids)
    raw_id = _new_id("raw")
    ext = Path(filename).suffix.lower()
    if ext not in _RAW_VIDEO_EXTS:
        ext = ".mp4"
    safe_stem = _sanitize_filename_stem(filename)
    file_path = asset_vault_raw_dir() / f"{raw_id}_{safe_stem}{ext}"
    write_bytes(file_path, data)
    raw = RawVideo(id=raw_id, file_path=str(file_path), source_url=None, original_filename=filename, import_note=import_note, status="detecting")
    raw.channels = channels
    db.add(raw)
    db.commit()
    return raw


def create_raw_video_placeholder_for_url(db: Session, channel_ids: list[str], url: str, import_note: str = "") -> RawVideo:
    """Tạo NGAY 1 hàng `RawVideo` (đồng bộ, nhanh) rồi trả về liền cho router — việc tải
    THẬT (chậm, có thể mất nhiều phút) chạy riêng qua `download_raw_video_from_url` trong
    `BackgroundTasks` (đổi từ đồng bộ 2026-08-27, để frontend poll được tiến trình tải
    giữa chừng thay vì phải đợi cả request). `file_path` gán tạm 1 đường dẫn CHƯA CÓ FILE
    THẬT (hậu tố `.downloading`, không phải phần mở rộng video hợp lệ) — cột này vẫn
    NOT NULL nên cần 1 placeholder hợp lệ, KHÔNG dùng chuỗi rỗng (dễ gây lỗi khó hiểu nếu
    code khác lỡ `Path(...)`/ffprobe chuỗi rỗng) — cập nhật lại thành path thật khi tải
    xong."""
    channels = _load_channels(db, channel_ids)
    raw_id = _new_id("raw")
    placeholder_path = asset_vault_raw_dir() / f"{raw_id}.downloading"
    raw = RawVideo(
        id=raw_id, file_path=str(placeholder_path), source_url=url, import_note=import_note,
        status="detecting", progress_label="Đang tải video từ URL",
    )
    raw.channels = channels
    db.add(raw)
    db.commit()
    return raw


def download_raw_video_from_url(db: Session, raw_video: RawVideo) -> None:
    """Chạy trong `BackgroundTasks` — tải THẬT qua yt-dlp, cập nhật tiến trình qua
    `progress_hooks` (xác nhận thật qua tài liệu yt-dlp: hook nhận dict có
    `downloaded_bytes`/`total_bytes` khi `status=="downloading"`). CHỈ được gọi từ route
    `POST .../raw/import-url` sau khi user tự dán link + bấm xác nhận — không có nơi nào
    khác trong app gọi hàm này tự động (§1)."""
    import yt_dlp  # import trễ — module nặng, chỉ cần khi thật sự tải URL

    out_dir = asset_vault_raw_dir()
    outtmpl = str(out_dir / f"{raw_video.id}.%(ext)s")

    last_commit_at = 0.0

    def hook(d: dict) -> None:
        nonlocal last_commit_at
        if d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes")
        if not total or downloaded is None:
            return
        now = time.time()
        if now - last_commit_at < _PROGRESS_COMMIT_INTERVAL_SEC:
            return
        last_commit_at = now
        raw_video.progress_current = downloaded
        raw_video.progress_total = total
        db.commit()

    opts = {"quiet": True, "outtmpl": outtmpl, "format": "mp4/bestvideo+bestaudio/best", "merge_output_format": "mp4", "progress_hooks": [hook]}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([raw_video.source_url])
    except Exception as e:  # noqa: BLE001
        raw_video.status = "error"
        raw_video.error_message = f"Tải video từ URL thất bại: {e}"
        _clear_progress(raw_video)
        db.commit()
        return

    old_placeholder = Path(raw_video.file_path)
    matches = sorted(p for p in out_dir.glob(f"{raw_video.id}.*") if p != old_placeholder)
    if not matches:
        raw_video.status = "error"
        raw_video.error_message = "Tải xong nhưng không tìm thấy file video output — kiểm tra lại URL."
        _clear_progress(raw_video)
        db.commit()
        return

    raw_video.file_path = str(matches[0])
    raw_video.status = "detecting"
    _clear_progress(raw_video)
    db.commit()


# ---------------------------------------------------------------------------
# Giai đoạn A.2/B.1 — Cắt cảnh (thủ công + PySceneDetect)
# ---------------------------------------------------------------------------
def _extract_clip(ffmpeg: str, raw_path: str, start_sec: float, end_sec: float, out_path: Path) -> None:
    """Cắt đoạn `[start_sec, end_sec)`, TÁCH audio (`-an` — chỉ giữ video sạch, §3 giai
    đoạn A bước 3), chuẩn hoá H.264 (encode lại — KHÔNG stream-copy, cắt bằng stream-copy
    dễ lệch điểm bắt đầu tới keyframe gần nhất thay vì đúng mốc yêu cầu).

    **`-ss` TRƯỚC `-i`, `-t <duration>` SAU `-i`** — đã verify thật bằng ffmpeg (dựng
    video 3 cảnh màu riêng biệt, cắt cảnh giữa, trích frame xác nhận đúng màu + đúng
    duration) — dùng `-to <end>` thay vì `-t <duration>` ở vị trí này SẼ SAI (mốc `-to`
    khi kết hợp `-ss` trước `-i` diễn giải không nhất quán giữa các bản ffmpeg, không
    suy đoán mà đo thật)."""
    duration = round(end_sec - start_sec, 3)
    if duration <= 0:
        raise ValueError(f"Khoảng cắt không hợp lệ: {start_sec}s → {end_sec}s")
    cmd = [
        ffmpeg, "-y", "-ss", str(start_sec), "-i", raw_path, "-t", str(duration),
        "-an", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)


def _probe_resolution(ffprobe_path: str, path: str) -> str:
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path],
            capture_output=True, check=True, text=True, timeout=15,
        )
        return result.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _make_clip_row(db: Session, raw_video: RawVideo, out_path: Path, ffmpeg: str) -> ProcessedClip:
    ffprobe = shutil.which("ffprobe") or ""
    clip = ProcessedClip(
        clip_id=_new_id("clip"),
        raw_video_id=raw_video.id,
        storage_url=str(out_path),
        duration_sec=probe_duration_sec(out_path) or 0.0,
        resolution=_probe_resolution(ffprobe, str(out_path)) if ffprobe else "",
    )
    # Sao chép tag kênh của raw_video cha NGAY LÚC CẮT (2026-08-28) — clip có tag kênh
    # RIÊNG từ đây, độc lập với raw_video (xem docstring `models.py::ProcessedClip`) —
    # tránh bug mất kênh khi raw_video cha bị xoá sau này.
    clip.channels = list(raw_video.channels)
    db.add(clip)
    return clip


def manual_cut_clip(db: Session, raw_video: RawVideo, start_sec: float, end_sec: float) -> ProcessedClip:
    """Cắt cảnh THỦ CÔNG — user tự chỉ định mốc thời gian (lưới an toàn khi
    `AdaptiveDetector` chưa tinh chỉnh tốt cho footage cụ thể, câu hỏi mở #4 spec)."""
    ffmpeg = _ensure_ffmpeg()
    clip_id_hint = _new_id("clip")
    out_path = asset_vault_clips_dir() / f"{clip_id_hint}.mp4"
    _extract_clip(ffmpeg, raw_video.file_path, start_sec, end_sec, out_path)
    clip = _make_clip_row(db, raw_video, out_path, ffmpeg)
    clip.clip_id = clip_id_hint  # khớp tên file đã tạo ở trên
    raw_video.status = "tagging"
    db.commit()
    return clip


def auto_detect_scenes(db: Session, raw_video: RawVideo) -> list[ProcessedClip]:
    """Cắt cảnh TỰ ĐỘNG bằng PySceneDetect `AdaptiveDetector` — §3 giai đoạn A bước 2.
    Verify thật: dựng video 2 cảnh màu tách biệt, `AdaptiveDetector` phát hiện đúng 2
    scene đúng mốc 3.0s (không suy đoán API `get_scene_list()`/`.seconds`).

    **Tiến trình thật (2026-08-27)** — 2 giai đoạn báo riêng: (1) PHÁT HIỆN cảnh, dùng
    `SceneManager.detect_scenes(callback=...)` — đã verify thật API này gọi MỖI FRAME với
    `(frame_ndarray, FrameTimecode)`, đọc `timecode.frame_num` / `video.duration.frame_num`
    làm current/total (throttle, không commit mỗi frame); (2) CẮT từng clip, cập nhật
    `progress_current=i, progress_total=len(scene_list)` SAU MỖI clip (đơn giản/chính xác
    hơn hẳn — không cần hook ffmpeg riêng)."""
    from scenedetect import AdaptiveDetector, SceneManager, open_video

    ffmpeg = _ensure_ffmpeg()
    raw_video.progress_label = "Đang phát hiện cảnh"
    raw_video.progress_current = 0
    raw_video.progress_total = None
    db.commit()

    last_commit_at = [0.0]

    def _on_frame(frame_img, timecode) -> None:  # noqa: ANN001 — chữ ký cố định của scenedetect
        now = time.time()
        if now - last_commit_at[0] < _PROGRESS_COMMIT_INTERVAL_SEC:
            return
        last_commit_at[0] = now
        try:
            total_frames = video.duration.frame_num
        except Exception:  # noqa: BLE001
            total_frames = None
        raw_video.progress_current = timecode.frame_num
        raw_video.progress_total = total_frames
        db.commit()

    try:
        video = open_video(raw_video.file_path)
        manager = SceneManager()
        manager.add_detector(AdaptiveDetector())
        manager.detect_scenes(video=video, callback=_on_frame)
        scene_list = manager.get_scene_list()
    except Exception as e:  # noqa: BLE001
        raw_video.status = "error"
        raw_video.error_message = f"Cắt cảnh tự động thất bại: {e}"
        _clear_progress(raw_video)
        db.commit()
        raise RuntimeError(raw_video.error_message) from e

    if not scene_list:
        # Video không có ranh giới cảnh nào phát hiện được (VD clip đã cắt sẵn 1 cảnh
        # liên tục) — coi TOÀN BỘ video là 1 clip duy nhất, không phải lỗi.
        total = probe_duration_sec(raw_video.file_path) or 0.0
        if total <= 0:
            raw_video.status = "error"
            raw_video.error_message = "Không đo được thời lượng video (thiếu ffprobe hoặc file lỗi)."
            _clear_progress(raw_video)
            db.commit()
            return []
        scene_list = [(0.0, total)]

    clips: list[ProcessedClip] = []
    n_scenes = len(scene_list)
    raw_video.progress_label = f"Đang cắt cảnh 0/{n_scenes}"
    raw_video.progress_current = 0
    raw_video.progress_total = n_scenes
    db.commit()
    for i, (start, end) in enumerate(scene_list, start=1):
        start_sec = start.seconds if hasattr(start, "seconds") else float(start)
        end_sec = end.seconds if hasattr(end, "seconds") else float(end)
        clip_id_hint = _new_id("clip")
        out_path = asset_vault_clips_dir() / f"{clip_id_hint}.mp4"
        try:
            _extract_clip(ffmpeg, raw_video.file_path, start_sec, end_sec, out_path)
        except subprocess.CalledProcessError:
            continue  # 1 đoạn lỗi không chặn cả video — bỏ qua, tiếp tục đoạn khác
        clip = _make_clip_row(db, raw_video, out_path, ffmpeg)
        clip.clip_id = clip_id_hint
        clips.append(clip)
        raw_video.progress_current = i
        raw_video.progress_label = f"Đang cắt cảnh {i}/{n_scenes}"
        db.commit()

    raw_video.status = "tagging" if clips else "error"
    if not clips:
        raw_video.error_message = "Không cắt được clip nào từ video này."
    else:
        raw_video.error_message = None  # xoá lỗi cũ (nếu lần cắt cảnh trước đó từng thất bại)
    _clear_progress(raw_video)
    db.commit()
    return clips


def remove_watermark_from_raw_video(db: Session, raw_video: RawVideo) -> None:
    """Xoá watermark khỏi video gốc TRƯỚC KHI cắt cảnh — dùng `app/watermark/pipeline.py`
    (Florence-2 phát hiện + LaMa inpaint, xem docstring module đó). Thay THẲNG
    `raw_video.file_path` bằng bản đã xoá watermark (đè lên file cũ) — không giữ bản gốc
    có watermark, khớp cách `download_raw_video_from_url` cập nhật `file_path` khi xong;
    KHÔNG đổi `status` (video vẫn ở đúng bước tiếp theo trước đó, VD "detecting" — người
    dùng bấm "Cắt cảnh tự động" ngay sau khi xoá watermark xong, không cần bước trung gian
    nào khác) — chỉ dùng `progress_*` làm chỉ báo "đang xử lý", cùng quy ước với tải URL/
    cắt cảnh tự động ở trên."""
    ffmpeg = _ensure_ffmpeg()
    # Bug thật (2026-08-28, phát hiện lúc test 2 video CÙNG LÚC): `tmp_dir` (và
    # `frames_dir` bên trong `remove_watermark_from_video`) TỪNG dùng chung 1 tên cố định
    # cho MỌI video — 2 lượt xoá watermark chạy song song (2 raw_video khác nhau) ghi đè
    # frame của nhau (số frame báo ra giống hệt nhau, sai) và `finally: shutil.rmtree(...)`
    # của lượt này xoá mất frame lượt kia đang xử lý dở (crash "file not found"). Cô lập
    # theo `raw_video.id` để mỗi lượt có thư mục tạm RIÊNG, chạy song song vô tư.
    tmp_dir = asset_vault_raw_dir() / "_watermark_tmp" / raw_video.id
    tmp_out = tmp_dir / f"{raw_video.id}_clean.mp4"

    def _on_progress(current: int, total: int, label: str) -> None:
        raw_video.progress_current = current
        raw_video.progress_total = total
        raw_video.progress_label = label
        db.commit()

    try:
        remove_watermark_from_video(ffmpeg, raw_video.file_path, tmp_out, tmp_dir, on_progress=_on_progress)
    except Exception as e:  # noqa: BLE001
        raw_video.status = "error"
        raw_video.error_message = f"Xoá watermark thất bại: {e}"
        _clear_progress(raw_video)
        db.commit()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    old_path = Path(raw_video.file_path)
    final_path = old_path.with_name(f"{old_path.stem}_nowm{old_path.suffix}")
    tmp_out.rename(final_path)
    if old_path.exists():
        old_path.unlink(missing_ok=True)
    raw_video.file_path = str(final_path)
    _clear_progress(raw_video)
    db.commit()
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Giai đoạn B.2 — Vision captioning + embedding
# ---------------------------------------------------------------------------
def _extract_keyframe(ffmpeg: str, clip_path: str, duration_sec: float) -> bytes:
    """Trích 1 keyframe đại diện tại GIỮA clip (50% thời lượng) — ĐƠN GIẢN HOÁ có chủ ý
    so với đề xuất "2 keyframe 25%/75%" của change-spec: gộp 2 caption riêng biệt thành 1
    mô tả nhất quán cần thêm 1 lượt LLM/heuristic merge (phức tạp, lợi ích chưa rõ ràng
    hơn hẳn 1 frame đại diện) — 1 frame ở giữa đã đủ đại diện cho phần lớn B-roll ngắn
    (thường 2-8s, ít đổi cảnh giữa chừng). Có thể nâng cấp lên 2 keyframe sau nếu caption
    thực tế cho thấy quá nông."""
    t = max(0.0, duration_sec / 2)
    scratch = Path(clip_path).with_suffix(".keyframe.jpg")
    cmd = [ffmpeg, "-y", "-ss", str(t), "-i", clip_path, "-frames:v", "1", "-q:v", "3", str(scratch)]
    subprocess.run(cmd, capture_output=True, check=True, text=True)
    data = scratch.read_bytes()
    scratch.unlink(missing_ok=True)
    return data


def index_clip_embedding(db: Session, clip: ProcessedClip) -> None:
    """Embed `caption`/`tags`/`mood_tone` ĐÃ CÓ SẴN trên clip rồi upsert vào Chroma — tách
    riêng khỏi `caption_clip` (2026-09-13) để TÁI DÙNG cho asset lưu từ Visual Studio
    (`from_visual_studio.py::save_shots_to_vault`), vốn đã có caption sẵn từ `visual_fx`
    (không cần Vision provider chụp lại) nhưng TRƯỚC ĐÂY không hề gọi bước embed này —
    khiến TOÀN BỘ asset Visual Studio (152/152 ảnh tại thời điểm phát hiện) vô hình với
    "Tự động điền từ Kho tài nguyên" (`render.py::_run_vault_auto_fill_scan`, CHỈ tìm qua
    semantic/Chroma, không có fallback từ khoá) dù khớp caption/mô tả shot 100% — người
    dùng chỉ thấy được qua nút "Video/Ảnh từ Kho" thủ công (có fallback từ khoá). Xem
    IMPLEMENTATION_REPORT.md mục 146. KHÔNG tự `commit()` — caller quyết định thời điểm
    commit (mirror `caption_clip`)."""
    tags = json.loads(clip.tags or "[]")
    document = f"{clip.caption} | Tags: {', '.join(tags)} | Mood: {clip.mood_tone or ''}"
    embedding = get_embedding(db).embed(document)
    vector_id = clip.clip_id
    upsert_clip_vector(vector_id, embedding, document)
    clip.vector_id = vector_id


def caption_clip(db: Session, clip: ProcessedClip) -> None:
    """Gắn caption/tags/mood_tone (Vision provider — mặc định `ollama_vision`/Moondream,
    xem IMPLEMENTATION_REPORT.md) rồi embed + upsert Chroma (§3 giai đoạn B bước 2-4). Lỗi
    ở 1 clip KHÔNG raise ra ngoài — caller (`caption_all_pending_clips`) cần tiếp tục các
    clip khác."""
    ffmpeg = _ensure_ffmpeg()
    frame_bytes = _extract_keyframe(ffmpeg, clip.storage_url, clip.duration_sec or 1.0)
    result = get_vision(db).caption(frame_bytes, prompt=_CAPTION_PROMPT)
    clip.caption = result.caption
    clip.tags = json.dumps(result.tags, ensure_ascii=False)
    clip.mood_tone = result.mood_tone

    index_clip_embedding(db, clip)
    db.commit()


def caption_clips(db: Session, clips: list[ProcessedClip]) -> tuple[int, int]:
    """Gắn nhãn 1 DANH SÁCH clip TUỲ Ý — **mới (2026-08-27)**, dùng cho bulk gắn nhãn theo
    lựa chọn tự do ở bảng "Clip đã cắt" (Kho Tài Nguyên), khác `caption_all_pending_clips`
    dưới (luôn scope theo ĐÚNG 1 `raw_video`) — clip trong `clips` có thể trải nhiều
    `raw_video` khác nhau, nên KHÔNG có 1 hàng RawVideo chung để gắn cờ lỗi/trạng thái;
    lỗi/thành công ghi TRỰC TIẾP vào `ProcessedClip.caption_error` của từng clip (xem
    docstring cột đó ở models.py) thay vì `RawVideo.error_message`. Trả về
    `(so_thanh_cong, so_loi)` — lỗi 1 clip KHÔNG chặn các clip còn lại (đúng nguyên tắc
    lỗi-1-phần-không-chặn-cả-batch đã dùng ở `generate_all_visual`)."""
    ok = 0
    err = 0
    for clip in clips:
        try:
            clip.caption_error = None  # xoá lỗi cũ TRƯỚC khi thử lại — `caption_clip` tự commit khi thành công, gộp chung 1 lượt ghi
            caption_clip(db, clip)
            ok += 1
        except Exception as e:  # noqa: BLE001
            clip.caption_error = str(e)
            err += 1
            db.commit()
    return ok, err


def caption_all_pending_clips(db: Session, raw_video: RawVideo) -> None:
    """Chạy nền qua BackgroundTasks (FastAPI) — KHÔNG dùng job queue riêng, tái dùng
    đúng pattern `run_asset_generation`/`assemble_video` đã có trong app. Lỗi 1 clip ghi
    log rồi tiếp tục — không chặn cả RawVideo (đúng nguyên tắc lỗi-1-phần-không-chặn-cả-
    batch đã dùng ở `generate_all_visual`). Scope theo ĐÚNG 1 `raw_video` (dùng cho nút
    "Gắn nhãn"/"Gắn nhãn lại" của 1 video gốc) — với bulk gắn nhãn theo lựa chọn tự do
    (nhiều raw_video khác nhau), xem `caption_clips` ở trên."""
    clips = db.query(ProcessedClip).filter(ProcessedClip.raw_video_id == raw_video.id).all()
    _ok, err = caption_clips(db, clips)
    had_error = err > 0
    if had_error:
        failed = [c.clip_id for c in clips if c.caption_error]
        raw_video.error_message = f"Lỗi gắn nhãn {len(failed)} clip: {', '.join(failed[:3])}{'...' if len(failed) > 3 else ''}"
    raw_video.status = "error" if had_error else "indexed"
    if not had_error:
        raw_video.error_message = None  # xoá lỗi cũ (nếu có, VD từ lần gắn nhãn lại thất bại trước đó) — status="indexed" không nên còn kèm thông báo lỗi đã hết hiệu lực
    db.commit()


def reconcile_raw_video_status(db: Session, raw_video: RawVideo) -> bool:
    """Tự phục hồi (self-heal) `RawVideo.status` bị KẸT sai — bug thật (2026-09-10, báo
    bởi người dùng: "Video đã cắt cảnh vẫn hiện đang cắt cảnh, đã gán nhãn nhưng vẫn hiện
    đang gán nhãn"). Gốc rễ: `_run()` wrapper (`routers/asset_vault.py`) bọc
    `auto_detect_scenes`/`caption_all_pending_clips` trong `BackgroundTasks` KHÔNG có
    try/except quanh lệnh gọi lõi — nếu backend crash/tự khởi động lại giữa chừng (đã xảy
    ra nhiều lần trong quá trình phát triển), task nền chết lặng lẽ; công việc con (cắt
    từng clip, caption từng clip) đã commit DB tăng dần nhưng dòng CUỐI chuyển `status`
    sang bước kế tiếp không kịp chạy → `status` kẹt vĩnh viễn dù dữ liệu con đã xong thật.

    Gọi ở các endpoint GET (đọc) TRƯỚC KHI trả response — KHÔNG khởi chạy job nền nào mới,
    chỉ SUY LẠI `status` từ dữ liệu con đã có sẵn. Trả về `True` nếu có đổi (caller tự
    `db.commit()`). Chỉ đi TỚI (forward), không bao giờ lùi lại bước trước hay tự gán
    "error" khi thiếu bằng chứng:

    - `status=="tagging"` mà TẤT CẢ clip con đã có `caption` HOẶC `caption_error` (gắn nhãn
      xong, dù thành công hay lỗi từng clip) → suy đúng logic cuối
      `caption_all_pending_clips` lẽ ra đã chạy: "error" nếu có ≥1 clip lỗi, else "indexed".
    - `status=="detecting"` mà ĐÃ có ≥1 clip con VÀ `progress_current`/`progress_total`/
      `progress_label` đều None (không có task nào đang chạy dở — task thật luôn có
      progress) → bước cắt cảnh rõ ràng đã chạy xong (ít nhất 1 phần) nhưng chưa kịp ghi
      "tagging" → suy "tagging". Video mới upload/chưa cắt cảnh lần nào (0 clip) KHÔNG bị
      đụng tới — đây vẫn là trạng thái ban đầu đúng, không phải bug."""
    clips = db.query(ProcessedClip).filter(ProcessedClip.raw_video_id == raw_video.id).all()
    if not clips:
        return False
    if raw_video.status == "tagging" and all(c.caption or c.caption_error for c in clips):
        failed = [c.clip_id for c in clips if c.caption_error]
        raw_video.status = "error" if failed else "indexed"
        if failed:
            raw_video.error_message = f"Lỗi gắn nhãn {len(failed)} clip: {', '.join(failed[:3])}{'...' if len(failed) > 3 else ''}"
        else:
            raw_video.error_message = None
        return True
    if (
        raw_video.status == "detecting"
        and raw_video.progress_current is None
        and raw_video.progress_total is None
        and raw_video.progress_label is None
    ):
        raw_video.status = "tagging"
        return True
    return False


def delete_processed_clip(db: Session, clip: ProcessedClip) -> None:
    path = Path(clip.storage_url)
    if path.exists():
        path.unlink(missing_ok=True)
    delete_clip_vector(clip.clip_id)
    db.delete(clip)
    db.commit()
