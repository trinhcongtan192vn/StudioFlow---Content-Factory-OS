"""Test tính năng hiệu ứng lớp phủ (overlay effect — VD mưa/tuyết rơi) — mặc định cấp
kênh (BrandProfile) + override riêng của project (2026-08-22, theo yêu cầu người dùng:
"tương tự như intro video" ở khoản cấu hình 2 cấp, nhưng ÁP DỤNG như bg_music — blend đè
liên tục suốt toàn bộ video, không chỉ đoạn mở đầu) — xem `app/render/overlay.py::
resolve_overlay_source` cho thứ tự ưu tiên: project override > overlay mặc định cấp kênh.
Cùng cấu trúc/pattern test với `test_bg_music.py` (audio→video).
"""
import io
import shutil
import subprocess
from pathlib import Path

import pytest

FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20


# ---------------------------------------------------------------------------
# Channel-level: POST/GET /channels/{id}/brandprofile/overlay
# ---------------------------------------------------------------------------
def test_upload_brand_overlay_sets_path(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/overlay/upload",
        files={"file": ("overlay.mp4", io.BytesIO(FAKE_MP4), "video/mp4")},
    )
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["overlay_effect_path"]

    fetched = client.get(f"/channels/{channel['id']}/brandprofile").json()
    assert fetched["overlay_effect_path"] == profile["overlay_effect_path"]


def test_upload_brand_overlay_rejects_unknown_file_type(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/overlay/upload",
        files={"file": ("overlay.txt", io.BytesIO(b"khong phai video"), "text/plain")},
    )
    assert resp.status_code == 400


def test_get_brand_overlay_404_when_none(client, channel):
    resp = client.get(f"/channels/{channel['id']}/brandprofile/overlay")
    assert resp.status_code == 404


def test_get_brand_overlay_serves_uploaded_file(client, channel):
    client.post(f"/channels/{channel['id']}/brandprofile/overlay/upload", files={"file": ("overlay.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    resp = client.get(f"/channels/{channel['id']}/brandprofile/overlay")
    assert resp.status_code == 200
    assert resp.content == FAKE_MP4


def test_set_brand_overlay_opacity_via_put(client, channel):
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["overlay_effect_opacity"] = 0.8
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile)
    assert resp.status_code == 200
    assert resp.json()["overlay_effect_opacity"] == 0.8


def test_clear_brand_overlay_via_put(client, channel):
    client.post(f"/channels/{channel['id']}/brandprofile/overlay/upload", files={"file": ("overlay.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["overlay_effect_path"] = ""
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile)
    assert resp.status_code == 200
    assert resp.json()["overlay_effect_path"] == ""
    assert client.get(f"/channels/{channel['id']}/brandprofile/overlay").status_code == 404


# ---------------------------------------------------------------------------
# Project-level: /projects/{id}/render/overlay (override)
# ---------------------------------------------------------------------------
def test_upload_project_overlay_sets_asset_path(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/overlay/upload", files={"file": ("overlay.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    assert resp.status_code == 200
    state = resp.json()
    assert state["overlay"]["asset_path"]
    assert state["overlay"]["opacity"] == pytest.approx(0.5)  # mặc định


def test_patch_project_overlay_opacity(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/overlay/upload", files={"file": ("overlay.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    resp = client.patch(f"/projects/{pid}/render/overlay", json={"opacity": 0.9})
    assert resp.status_code == 200
    assert resp.json()["overlay"]["opacity"] == pytest.approx(0.9)


def test_patch_project_overlay_opacity_creates_override_if_missing(client, project):
    pid = project["id"]
    resp = client.patch(f"/projects/{pid}/render/overlay", json={"opacity": 0.2})
    assert resp.status_code == 200
    assert resp.json()["overlay"]["opacity"] == pytest.approx(0.2)
    assert resp.json()["overlay"]["asset_path"] is None


def test_delete_project_overlay_clears_state_and_file(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/overlay/upload", files={"file": ("overlay.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    status_before = client.get(f"/projects/{pid}/render/status").json()
    asset_path = Path(status_before["overlay"]["asset_path"])
    assert asset_path.exists()

    resp = client.delete(f"/projects/{pid}/render/overlay")
    assert resp.status_code == 200
    assert resp.json()["overlay"] is None
    assert not asset_path.exists()


def test_get_project_overlay_asset_serves_file(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/overlay/upload", files={"file": ("overlay.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    resp = client.get(f"/projects/{pid}/render/overlay/asset")
    assert resp.status_code == 200
    assert resp.content == FAKE_MP4


def test_get_project_overlay_asset_404_when_none(client, project):
    resp = client.get(f"/projects/{project['id']}/render/overlay/asset")
    assert resp.status_code == 404


def test_upload_project_overlay_rejects_unknown_file_type(client, project):
    resp = client.post(f"/projects/{project['id']}/render/overlay/upload", files={"file": ("overlay.txt", io.BytesIO(b"khong phai video"), "text/plain")})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# `resolve_overlay_source` — logic ưu tiên thuần (không cần ffmpeg thật)
# ---------------------------------------------------------------------------
def test_resolve_overlay_source_prefers_project_override():
    from app.render.overlay import resolve_overlay_source
    from app.render.schemas import OverlayEffectOverride

    project_overlay = OverlayEffectOverride(asset_path="/tmp/project_overlay.mp4", opacity=0.7)
    brand = {"overlay_effect_path": "/tmp/brand_overlay.mp4", "overlay_effect_opacity": 0.5}
    result = resolve_overlay_source(project_overlay, brand)
    assert result == ("/tmp/project_overlay.mp4", 0.7)


def test_resolve_overlay_source_falls_back_to_brand():
    from app.render.overlay import resolve_overlay_source

    brand = {"overlay_effect_path": "/tmp/brand_overlay.mp4", "overlay_effect_opacity": 0.4}
    result = resolve_overlay_source(None, brand)
    assert result == ("/tmp/brand_overlay.mp4", 0.4)


def test_resolve_overlay_source_ignores_override_without_asset_path():
    from app.render.overlay import resolve_overlay_source
    from app.render.schemas import OverlayEffectOverride

    project_overlay = OverlayEffectOverride(asset_path=None, opacity=0.9)  # chỉ chỉnh opacity, chưa upload
    brand = {"overlay_effect_path": "/tmp/brand_overlay.mp4", "overlay_effect_opacity": 0.5}
    result = resolve_overlay_source(project_overlay, brand)
    assert result == ("/tmp/brand_overlay.mp4", 0.5)


def test_resolve_overlay_source_none_when_nothing_configured():
    from app.render.overlay import resolve_overlay_source

    assert resolve_overlay_source(None, {}) is None


# ---------------------------------------------------------------------------
# `_mix_overlay_effect` — real ffmpeg
# ---------------------------------------------------------------------------
def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return float(out.stdout.strip())


def _sample_pixel_gray(ffmpeg: str, path: Path, *, ss: float | None = None) -> int:
    """Lấy độ sáng TRUNG BÌNH (0-255) của 1 frame — scale cả frame về 1x1 rồi xuất
    grayscale thô (1 byte duy nhất). Cách đơn giản, không cần parse text output như
    `volumedetect` (audio) — dùng để xác nhận overlay đã blend vào (frame sáng hơn hẳn
    nền đen gốc) mà không cần so sánh ảnh phức tạp."""
    cmd = [ffmpeg, "-y"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", str(path), "-frames:v", "1", "-vf", "scale=1:1,format=gray", "-f", "rawvideo", "-"]
    result = subprocess.run(cmd, capture_output=True, check=True)
    assert len(result.stdout) >= 1, f"Không lấy được pixel — stderr: {result.stderr[-500:]}"
    return result.stdout[0]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_mix_overlay_effect_blends_and_bounds_output_to_video_duration(tmp_path):
    """Overlay NGẮN HƠN video nhiều lần (1s overlay, 3s video) — `-stream_loop -1` phải
    lặp đủ (frame ở giây thứ 2, thuộc vòng lặp thứ 2, vẫn phải sáng), nhưng `-shortest`
    phải CHẶN output ở đúng độ dài video (KHÔNG kéo dài vô hạn theo overlay lặp mãi)."""
    from app.render.assembly import _mix_overlay_effect

    ffmpeg = shutil.which("ffmpeg")
    # Video nền ĐEN tuyền — bất kỳ độ sáng nào đo được ở output chỉ có thể tới từ overlay
    # blend vào (tránh false positive), giống nguyên tắc "narration câm" ở test_bg_music.py.
    video_path = tmp_path / "video_black.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path)],
        capture_output=True, check=True, text=True,
    )
    # Overlay TRẮNG tuyền, chỉ dài 1s — blend `screen` của đen+trắng = trắng (sáng tối đa).
    overlay_path = tmp_path / "overlay_white_1s.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=white:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(overlay_path)],
        capture_output=True, check=True, text=True,
    )

    out_path = tmp_path / "overlaid_out.mp4"
    _mix_overlay_effect(ffmpeg, video_path, str(overlay_path), 1.0, out_path, resolution="320:240", video_codec="libx264", crf=23)

    assert out_path.exists()
    assert _ffprobe_duration(out_path) == pytest.approx(3.0, abs=0.3)

    gray_black_only = _sample_pixel_gray(ffmpeg, video_path, ss=0.1)
    gray_overlaid_start = _sample_pixel_gray(ffmpeg, out_path, ss=0.1)
    gray_overlaid_second_loop = _sample_pixel_gray(ffmpeg, out_path, ss=2.0)  # sau khi overlay 1s đã lặp lại >=1 lần
    assert gray_black_only < 30, f"Video nền phải gần đen tuyền để test có ý nghĩa (đo được {gray_black_only})"
    assert gray_overlaid_start > 180, f"Đầu video sau blend phải sáng rõ (trắng đè lên đen) — đo được {gray_overlaid_start}"
    assert gray_overlaid_second_loop > 180, f"Giây thứ 2 (overlay đã lặp) vẫn phải sáng — đo được {gray_overlaid_second_loop} — overlay có thể KHÔNG được lặp lại đúng"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_mix_overlay_effect_opacity_controls_intensity(tmp_path):
    """`opacity` thấp phải cho kết quả MỜ HƠN (gần nền gốc hơn) so với `opacity` cao —
    xác nhận `colorchannelmixer` thật sự điều khiển được cường độ hiệu ứng."""
    from app.render.assembly import _mix_overlay_effect

    ffmpeg = shutil.which("ffmpeg")
    video_path = tmp_path / "video_black.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path)],
        capture_output=True, check=True, text=True,
    )
    overlay_path = tmp_path / "overlay_white.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=white:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(overlay_path)],
        capture_output=True, check=True, text=True,
    )

    out_low = tmp_path / "out_low.mp4"
    out_high = tmp_path / "out_high.mp4"
    _mix_overlay_effect(ffmpeg, video_path, str(overlay_path), 0.1, out_low, resolution="320:240", video_codec="libx264", crf=23)
    _mix_overlay_effect(ffmpeg, video_path, str(overlay_path), 1.0, out_high, resolution="320:240", video_codec="libx264", crf=23)

    gray_low = _sample_pixel_gray(ffmpeg, out_low, ss=0.1)
    gray_high = _sample_pixel_gray(ffmpeg, out_high, ss=0.1)
    assert gray_high > gray_low, f"opacity=1.0 (sáng {gray_high}) phải sáng hơn opacity=0.1 (sáng {gray_low})"


# ---------------------------------------------------------------------------
# End-to-end: assemble_video() thật blend overlay vào TOÀN BỘ video — real ffmpeg.
# ---------------------------------------------------------------------------
def _import_one_image_shot(client, pid: str) -> str:
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:03", "Image", "Canh den", "Khong tieng", "Loi thoai test."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    confirm = client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200, confirm.text
    resp = client.post(f"/projects/{pid}/visual/generate")
    assert resp.status_code == 200, resp.text
    return resp.json()["shots"][0]["shot_id"]


def _solid_color_png(ffmpeg: str, color: str, path: Path) -> None:
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240", "-frames:v", "1", "-update", "1", str(path)], capture_output=True, check=True, text=True)


def _solid_color_video(ffmpeg: str, color: str, duration: float, path: Path) -> None:
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, check=True, text=True,
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_blends_brand_overlay_over_whole_video(client, project, tmp_path):
    """Overlay mặc định cấp kênh (không có project override) phải được blend vào SUỐT
    video, kể cả khi không có intro. Verify THẬT (không mock): shot nền ĐEN tuyền, sau
    khi ghép + blend overlay TRẮNG phải ra frame SÁNG RÕ (không còn đen)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    overlay_src = tmp_path / "brand_overlay.mp4"
    _solid_color_video(ffmpeg, "white", 1.0, overlay_src)
    upload = client.post(f"/channels/{channel_id}/brandprofile/overlay/upload", files={"file": ("overlay.mp4", overlay_src.open("rb"), "video/mp4")})
    assert upload.status_code == 200, upload.text
    profile = client.get(f"/channels/{channel_id}/brandprofile").json()
    profile["overlay_effect_opacity"] = 1.0
    client.put(f"/channels/{channel_id}/brandprofile", json=profile)

    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "black", shot_png)
    state = RenderState(project_id=pid, shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])
    assert final_path.exists() and final_path.stat().st_size > 0

    total_duration = _ffprobe_duration(final_path)
    assert total_duration == pytest.approx(3.0, abs=0.5)  # ~3s shot, KHÔNG dài thêm vì overlay

    gray_start = _sample_pixel_gray(ffmpeg, final_path, ss=0.2)
    gray_end = _sample_pixel_gray(ffmpeg, final_path, ss=2.5)
    assert gray_start > 150, f"Đầu video vẫn tối ({gray_start}) — overlay không được blend vào"
    assert gray_end > 150, f"Cuối video vẫn tối ({gray_end}) — overlay không phủ hết toàn bộ video (không lặp lại đủ)"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_project_overlay_overrides_brand_overlay(client, project, tmp_path):
    """Overlay RIÊNG của project phải override overlay mặc định cấp kênh — verify qua
    kênh màu khác nhau: brand dùng ĐỎ (không được thấy), project dùng XANH LAM."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    brand_overlay_src = tmp_path / "brand_overlay_red.mp4"
    _solid_color_video(ffmpeg, "red", 1.0, brand_overlay_src)
    client.post(f"/channels/{channel_id}/brandprofile/overlay/upload", files={"file": ("overlay.mp4", brand_overlay_src.open("rb"), "video/mp4")})
    profile = client.get(f"/channels/{channel_id}/brandprofile").json()
    profile["overlay_effect_opacity"] = 1.0
    client.put(f"/channels/{channel_id}/brandprofile", json=profile)

    project_overlay_src = tmp_path / "project_overlay_blue.mp4"
    _solid_color_video(ffmpeg, "blue", 1.0, project_overlay_src)
    upload = client.post(f"/projects/{pid}/render/overlay/upload", files={"file": ("overlay.mp4", project_overlay_src.open("rb"), "video/mp4")})
    assert upload.status_code == 200, upload.text
    client.patch(f"/projects/{pid}/render/overlay", json={"opacity": 1.0})

    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "black", shot_png)
    state = RenderState.model_validate(client.get(f"/projects/{pid}/render/status").json())
    state.shots = [ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)]
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    # So kênh màu R vs B ở 1 frame — project (xanh lam) phải chiếm ưu thế RÕ so với brand (đỏ).
    result = subprocess.run(
        [ffmpeg, "-y", "-ss", "0.2", "-i", str(final_path), "-frames:v", "1", "-vf", "scale=1:1,format=rgb24", "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    )
    r, g, b = result.stdout[0], result.stdout[1], result.stdout[2]
    assert b > r + 30, f"Kênh xanh lam (project override) phải trội hơn hẳn kênh đỏ (brand) — đo được R={r} G={g} B={b}, có thể đang dùng overlay BRAND thay vì PROJECT"
