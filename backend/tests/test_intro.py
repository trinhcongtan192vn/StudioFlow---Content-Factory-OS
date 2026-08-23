"""Test tính năng video/audio thương hiệu (BrandProfile) + shot mở đầu riêng của
project (2026-08-20, theo yêu cầu người dùng) — xem `app/render/assembly.py::
_resolve_intro_source` cho thứ tự ưu tiên: shot mở đầu project (override) > video
thương hiệu kênh > audio thương hiệu kênh (minh hoạ bằng ảnh shot đầu tiên).
"""
import io
import shutil
import subprocess
from pathlib import Path

import pytest

FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20
FAKE_MP3 = b"ID3" + b"0" * 20
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


# ---------------------------------------------------------------------------
# Brand-level: POST/GET /channels/{id}/brandprofile/intro
# ---------------------------------------------------------------------------
def test_upload_brand_intro_video_sets_video_path_only(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/intro/upload",
        files={"file": ("intro.mp4", io.BytesIO(FAKE_MP4), "video/mp4")},
    )
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["intro_video_path"]
    assert profile["intro_audio_path"] == ""

    fetched = client.get(f"/channels/{channel['id']}/brandprofile").json()
    assert fetched["intro_video_path"] == profile["intro_video_path"]


def test_upload_brand_intro_audio_sets_audio_path_only(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/intro/upload",
        files={"file": ("intro.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")},
    )
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["intro_audio_path"]
    assert profile["intro_video_path"] == ""


def test_upload_brand_intro_is_mutually_exclusive(client, channel):
    """Upload video RỒI audio — theo yêu cầu "chỉ được phép upload 1 trong 2 loại":
    audio phải THAY THẾ video (xoá field video), không giữ cả 2."""
    client.post(f"/channels/{channel['id']}/brandprofile/intro/upload", files={"file": ("intro.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    resp = client.post(f"/channels/{channel['id']}/brandprofile/intro/upload", files={"file": ("intro.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    profile = resp.json()
    assert profile["intro_audio_path"]
    assert profile["intro_video_path"] == ""


def test_upload_brand_intro_rejects_unknown_file_type(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/intro/upload",
        files={"file": ("intro.txt", io.BytesIO(b"khong phai media"), "text/plain")},
    )
    assert resp.status_code == 400


def test_get_brand_intro_404_when_none(client, channel):
    resp = client.get(f"/channels/{channel['id']}/brandprofile/intro")
    assert resp.status_code == 404


def test_get_brand_intro_serves_uploaded_file(client, channel):
    client.post(f"/channels/{channel['id']}/brandprofile/intro/upload", files={"file": ("intro.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    resp = client.get(f"/channels/{channel['id']}/brandprofile/intro")
    assert resp.status_code == 200
    assert resp.content == FAKE_MP4


def test_clear_brand_intro_via_put(client, channel):
    """Bỏ intro — PUT lại BrandProfile với field rỗng (cùng pattern voice-sample đã có),
    không cần route xoá riêng."""
    client.post(f"/channels/{channel['id']}/brandprofile/intro/upload", files={"file": ("intro.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["intro_video_path"] = ""
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile)
    assert resp.status_code == 200
    assert resp.json()["intro_video_path"] == ""
    assert client.get(f"/channels/{channel['id']}/brandprofile/intro").status_code == 404


# ---------------------------------------------------------------------------
# Project-level: shot mở đầu riêng (override) — /projects/{id}/render/intro/*
# ---------------------------------------------------------------------------
def test_upload_intro_visual_image_sets_kind_image(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.png", io.BytesIO(FAKE_PNG), "image/png")})
    assert resp.status_code == 200
    state = resp.json()
    assert state["intro"]["kind"] == "image"
    assert state["intro"]["visual_asset_path"]
    assert state["intro"]["audio_asset_path"] is None


def test_upload_intro_audio_alone_is_allowed(client, project):
    """Đã đổi (2026-08-20, theo yêu cầu người dùng): audio mở đầu upload ĐỘC LẬP được,
    không còn bắt buộc phải có ảnh trước — lúc ghép sẽ tự dùng ảnh shot đầu tiên (xem
    `test_assemble_project_intro_audio_only_uses_first_shot_image` trong assembly test)."""
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    assert resp.status_code == 200
    state = resp.json()
    assert state["intro"]["audio_asset_path"]
    assert state["intro"]["visual_asset_path"] is None


def test_upload_intro_image_then_audio_completes_intro(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.png", io.BytesIO(FAKE_PNG), "image/png")})
    resp = client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    assert resp.status_code == 200
    state = resp.json()
    assert state["intro"]["kind"] == "image"
    assert state["intro"]["visual_asset_path"]
    assert state["intro"]["audio_asset_path"]


def test_upload_intro_video_clears_prior_audio(client, project):
    """Bắt buộc ảnh phải có audio, nhưng VIDEO thì không — nếu người dùng đổi từ ảnh
    (đã có audio đi kèm) sang video, audio rời cũ phải bị xoá (không còn ý nghĩa)."""
    pid = project["id"]
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.png", io.BytesIO(FAKE_PNG), "image/png")})
    client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})

    resp = client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    assert resp.status_code == 200
    state = resp.json()
    assert state["intro"]["kind"] == "video"
    assert state["intro"]["audio_asset_path"] is None


def test_upload_intro_audio_rejected_when_kind_is_video(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    resp = client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    assert resp.status_code == 400


def test_delete_intro_clears_state_and_files(client, project):
    """Đổi hành vi (2026-08-22): DELETE giờ set `disabled=True` (tắt hẳn, không fallback
    về brand nữa) thay vì `intro=None` (trước đây `None` vẫn ngầm fallback brand) — xem
    docstring `delete_intro`."""
    pid = project["id"]
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.png", io.BytesIO(FAKE_PNG), "image/png")})
    client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})

    status_before = client.get(f"/projects/{pid}/render/status").json()
    visual_path = Path(status_before["intro"]["visual_asset_path"])
    audio_path = Path(status_before["intro"]["audio_asset_path"])
    assert visual_path.exists() and audio_path.exists()

    resp = client.delete(f"/projects/{pid}/render/intro")
    assert resp.status_code == 200
    intro = resp.json()["intro"]
    assert intro["disabled"] is True
    assert intro["visual_asset_path"] is None
    assert intro["audio_asset_path"] is None
    assert not visual_path.exists()
    assert not audio_path.exists()


def test_delete_intro_opts_out_even_with_no_prior_upload(client, project):
    """"Bỏ shot mở đầu" khi project CHƯA từng upload gì (đang ngầm kế thừa brand) vẫn
    phải tắt hẳn được — không chỉ có tác dụng khi đã có asset riêng."""
    pid = project["id"]
    resp = client.delete(f"/projects/{pid}/render/intro")
    assert resp.status_code == 200
    assert resp.json()["intro"]["disabled"] is True


def test_upload_after_delete_re_enables_intro(client, project):
    pid = project["id"]
    client.delete(f"/projects/{pid}/render/intro")
    resp = client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    assert resp.status_code == 200
    assert resp.json()["intro"]["disabled"] is False
    assert resp.json()["intro"]["kind"] == "video"


def test_enable_intro_inherit_clears_disabled_flag(client, project):
    pid = project["id"]
    client.delete(f"/projects/{pid}/render/intro")
    resp = client.patch(f"/projects/{pid}/render/intro/inherit")
    assert resp.status_code == 200
    assert resp.json()["intro"]["disabled"] is False


def test_enable_intro_inherit_auto_creates_intro_if_missing(client, project):
    pid = project["id"]
    status_before = client.get(f"/projects/{pid}/render/status").json()
    assert status_before["intro"] is None
    resp = client.patch(f"/projects/{pid}/render/intro/inherit")
    assert resp.status_code == 200
    assert resp.json()["intro"]["disabled"] is False


def test_get_intro_asset_serves_visual_and_audio(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.png", io.BytesIO(FAKE_PNG), "image/png")})
    client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})

    visual = client.get(f"/projects/{pid}/render/intro/asset/visual")
    assert visual.status_code == 200 and visual.content == FAKE_PNG
    audio = client.get(f"/projects/{pid}/render/intro/asset/audio")
    assert audio.status_code == 200 and audio.content == FAKE_MP3


def test_get_intro_asset_404_when_none(client, project):
    resp = client.get(f"/projects/{project['id']}/render/intro/asset/visual")
    assert resp.status_code == 404


def test_patch_intro_transition_sets_value(client, project):
    pid = project["id"]
    resp = client.patch(f"/projects/{pid}/render/intro/transition", json={"transition_to_next": "fadeblack"})
    assert resp.status_code == 200
    assert resp.json()["intro"]["transition_to_next"] == "fadeblack"


def test_patch_intro_transition_rejects_invalid(client, project):
    resp = client.patch(f"/projects/{project['id']}/render/intro/transition", json={"transition_to_next": "bogus"})
    assert resp.status_code == 400


def test_patch_intro_transition_auto_creates_intro_if_missing(client, project):
    """Chỉnh transition TRƯỚC khi kịp upload asset mở đầu vẫn hợp lệ — cùng pattern
    `patch_project_bg_music_volume` (mục 53) — tự tạo `IntroAssetStatus` rỗng."""
    pid = project["id"]
    status_before = client.get(f"/projects/{pid}/render/status").json()
    assert status_before["intro"] is None
    resp = client.patch(f"/projects/{pid}/render/intro/transition", json={"transition_to_next": "dissolve"})
    assert resp.status_code == 200
    assert resp.json()["intro"]["visual_asset_path"] is None
    assert resp.json()["intro"]["transition_to_next"] == "dissolve"


def test_upload_intro_visual_rejects_unknown_file_type(client, project):
    resp = client.post(f"/projects/{project['id']}/render/intro/upload-visual", files={"file": ("open.txt", io.BytesIO(b"khong phai media"), "text/plain")})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# `_resolve_intro_source` — logic ưu tiên thuần (không cần ffmpeg thật)
# ---------------------------------------------------------------------------
def test_resolve_intro_source_prefers_project_override_over_brand():
    from app.render.assembly import _resolve_intro_source
    from app.render.schemas import IntroAssetStatus, ShotRenderStatus

    project_intro = IntroAssetStatus(kind="video", visual_asset_path="/tmp/project_intro.mp4")
    brand = {"intro_video_path": "/tmp/brand_intro.mp4"}
    result = _resolve_intro_source(project_intro, brand, shots=[], by_id={})
    assert result == ("video", "/tmp/project_intro.mp4", None)


def test_resolve_intro_source_falls_back_to_brand_video():
    from app.render.assembly import _resolve_intro_source

    brand = {"intro_video_path": "/tmp/brand_intro.mp4", "intro_audio_path": ""}
    result = _resolve_intro_source(None, brand, shots=[], by_id={})
    assert result == ("video", "/tmp/brand_intro.mp4", None)


def test_resolve_intro_source_falls_back_to_brand_audio_with_first_shot_image():
    from app.render.assembly import _resolve_intro_source
    from app.render.schemas import ShotRenderStatus

    brand = {"intro_video_path": "", "intro_audio_path": "/tmp/brand_audio.mp3"}
    shots = [{"shot_id": "s1"}, {"shot_id": "s2"}]
    by_id = {"s1": ShotRenderStatus(shot_id="s1", visual_asset_path="/tmp/s1.png", visual_status="ready")}
    result = _resolve_intro_source(None, brand, shots, by_id)
    assert result == ("image", "/tmp/s1.png", "/tmp/brand_audio.mp3")


def test_resolve_intro_source_skips_brand_audio_if_first_shot_not_ready():
    from app.render.assembly import _resolve_intro_source

    brand = {"intro_video_path": "", "intro_audio_path": "/tmp/brand_audio.mp3"}
    shots = [{"shot_id": "s1"}]
    result = _resolve_intro_source(None, brand, shots, by_id={})  # shot s1 chưa có trong render.json
    assert result is None


def test_resolve_intro_source_none_when_nothing_configured():
    from app.render.assembly import _resolve_intro_source

    assert _resolve_intro_source(None, {}, shots=[], by_id={}) is None


def test_resolve_intro_source_disabled_skips_brand_fallback():
    """`disabled=True` — mới (2026-08-22) — phải thắng CẢ project override LẪN brand
    fallback, trả None dù cả 2 đều "đủ dùng"."""
    from app.render.assembly import _resolve_intro_source
    from app.render.schemas import IntroAssetStatus

    disabled_intro = IntroAssetStatus(kind="video", visual_asset_path="/tmp/project_intro.mp4", disabled=True)
    brand = {"intro_video_path": "/tmp/brand_intro.mp4"}
    assert _resolve_intro_source(disabled_intro, brand, shots=[], by_id={}) is None


def test_resolve_intro_source_not_disabled_still_falls_back_to_brand():
    from app.render.assembly import _resolve_intro_source
    from app.render.schemas import IntroAssetStatus

    empty_intro = IntroAssetStatus(disabled=False)
    brand = {"intro_video_path": "/tmp/brand_intro.mp4", "intro_audio_path": ""}
    result = _resolve_intro_source(empty_intro, brand, shots=[], by_id={})
    assert result == ("video", "/tmp/brand_intro.mp4", None)


def test_resolve_intro_source_ignores_incomplete_project_intro():
    """Shot mở đầu project là ẢNH nhưng CHƯA có audio đi kèm — chưa "đủ" (xem
    `_intro_is_usable`), phải rơi về fallback thương hiệu, không dùng ảnh thiếu audio."""
    from app.render.assembly import _resolve_intro_source
    from app.render.schemas import IntroAssetStatus

    incomplete = IntroAssetStatus(kind="image", visual_asset_path="/tmp/open.png", audio_asset_path=None)
    brand = {"intro_video_path": "/tmp/brand_intro.mp4"}
    result = _resolve_intro_source(incomplete, brand, shots=[], by_id={})
    assert result == ("video", "/tmp/brand_intro.mp4", None)


# ---------------------------------------------------------------------------
# `_build_intro_segment` — real ffmpeg
# ---------------------------------------------------------------------------
def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return float(out.stdout.strip())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_intro_segment_video_kind_keeps_original_audio(tmp_path):
    """Khác `_build_segment` (video B-roll luôn -an hoặc audio ngoài) — intro video PHẢI
    giữ NGUYÊN audio gốc của chính nó (VD jingle thương hiệu), không bị cắt/đè."""
    from app.render.assembly import _build_intro_segment

    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "brand_intro.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)],
        capture_output=True, check=True, text=True,
    )
    out_path = tmp_path / "intro_segment.mp4"
    _build_intro_segment(ffmpeg, "video", str(src), None, out_path, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=28)

    assert out_path.exists()
    probe = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out_path)],
        capture_output=True, check=True, text=True,
    )
    kinds = probe.stdout.split()
    assert "video" in kinds and "audio" in kinds, "Intro video bị mất audio gốc"
    assert _ffprobe_duration(out_path) == pytest.approx(2.0, abs=0.3)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_intro_segment_image_kind_uses_audio_duration(tmp_path):
    """kind=="image": thời lượng segment PHẢI khớp độ dài THẬT của audio đi kèm (đo qua
    ffprobe), không phải 1 hằng số mặc định tuỳ tiện."""
    from app.render.assembly import _build_intro_segment

    ffmpeg = shutil.which("ffmpeg")
    image_src = tmp_path / "open.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(image_src)], capture_output=True, check=True, text=True)
    audio_src = tmp_path / "open.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "mp3", str(audio_src)], capture_output=True, check=True, text=True)

    out_path = tmp_path / "intro_segment.mp4"
    _build_intro_segment(ffmpeg, "image", str(image_src), str(audio_src), out_path, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=28)

    assert out_path.exists()
    assert _ffprobe_duration(out_path) == pytest.approx(3.0, abs=0.3)


# ---------------------------------------------------------------------------
# End-to-end: assemble_video() thật ghép intro vào ĐẦU video — real ffmpeg, không mock.
# ---------------------------------------------------------------------------
def _import_one_image_shot(client, pid: str) -> str:
    """Import script CSV 1 block ẢNH duy nhất qua API thật (không gọi AI — nguồn
    "import", xem mục 44 IMPLEMENTATION_REPORT.md) rồi sinh shot list — trả `shot_id`."""
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:02", "Image", "Canh xanh la", "Khong tieng", "Loi thoai test."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    confirm = client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200, confirm.text
    resp = client.post(f"/projects/{pid}/visual/generate")
    assert resp.status_code == 200, resp.text
    return resp.json()["shots"][0]["shot_id"]


def _solid_color_png(ffmpeg: str, color: str, path: Path) -> None:
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240", "-frames:v", "1", "-update", "1", str(path)], capture_output=True, check=True, text=True)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_prepends_brand_intro_video_before_shots(client, project, tmp_path):
    """Test THẬT xuyên suốt: upload video thương hiệu (đỏ) cho kênh, dựng 1 shot ẢNH
    (xanh lá) đã duyệt, gọi `assemble_video()` thật (ffmpeg thật, không mock) — xác nhận
    (1) video kết quả BẮT ĐẦU bằng nội dung ĐỎ (intro), KHÔNG phải xanh lá (shot), (2)
    tổng thời lượng ≈ thời lượng intro + thời lượng shot (video thương hiệu THẬT SỰ
    được ghép vào, không chỉ báo thành công mà không có tác dụng)."""
    from app.config import project_dir
    from app.filestore import write_bytes, write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    # 1. Video thương hiệu ĐỎ, 1 giây, upload qua API thật.
    intro_src = tmp_path / "brand_intro.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(intro_src)],
        capture_output=True, check=True, text=True,
    )
    upload = client.post(f"/channels/{channel_id}/brandprofile/intro/upload", files={"file": ("intro.mp4", intro_src.open("rb"), "video/mp4")})
    assert upload.status_code == 200, upload.text

    # 2. 1 shot ẢNH XANH LÁ đã "sinh xong" — ghi thẳng file thật + render.json (bỏ qua
    # bước gọi AI thật, không liên quan tới tính năng đang test).
    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "green", shot_png)
    state = RenderState(project_id=pid, shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)])
    write_json(pdir / "render.json", state.model_dump())

    # 3. Ghép THẬT.
    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])
    assert final_path.exists() and final_path.stat().st_size > 0, f"final.mp4 size={final_path.stat().st_size if final_path.exists() else 'MISSING'}"

    # Frame ĐẦU TIÊN phải là ĐỎ (intro), không phải xanh lá (shot). `format=rgb24` TRƯỚC
    # `crop` — thiếu bước này, crop=1:1 (kích thước lẻ) trên nguồn yuv420p (H.264) lỗi
    # thật "Invalid too big or non positive size for width '0' or height '0'" do ràng
    # buộc căn chỉnh chroma 4:2:0 — chỉ an toàn khi crop trên khung đã ở rgb24.
    probe = subprocess.run(
        [ffmpeg, "-y", "-i", str(final_path), "-vf", "format=rgb24,crop=1:1:10:10", "-f", "rawvideo", "-pix_fmt", "rgb24", "-frames:v", "1", "-"],
        capture_output=True, check=True,
    )
    r, g, b = probe.stdout[0], probe.stdout[1], probe.stdout[2]
    assert r > 150 and g < 100, f"Frame đầu không đỏ như intro — RGB=({r},{g},{b}), có thể shot bị phát TRƯỚC intro"

    total_duration = _ffprobe_duration(final_path)
    assert total_duration == pytest.approx(3.0, abs=0.6)  # ~1s intro + ~2s shot (B01 0:00-0:02)


def _mean_volume_db(ffmpeg: str, path: Path, *, ss: float | None = None, duration: float | None = None) -> float:
    """Đo âm lượng trung bình (dB) — dùng để phân biệt "có tiếng thật" (sine tone, VD
    ~-20dB) với "im lặng" (anullsrc, VD ~-91dB, gần sàn số học của volumedetect). `ss`
    (mới, mục 57) — seek tới 1 mốc thời gian bất kỳ TRƯỚC khi đo, không chỉ đo từ đầu
    file (cần để verify audio ở đoạn SAU intro, đúng chỗ bug audio-format-mismatch xảy
    ra — xem `test_assemble_intro_fade_transition_preserves_mismatched_rate_narration`)."""
    cmd = [ffmpeg, "-y"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", str(path)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-af", "volumedetect", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in result.stderr.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].strip().split(" ")[0])
    raise AssertionError(f"Không tìm thấy mean_volume trong stderr: {result.stderr[-500:]}")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_prepends_brand_intro_audio_only_with_first_shot_image(client, project, tmp_path):
    """Chỉ có AUDIO thương hiệu (không video) — theo yêu cầu người dùng phải minh hoạ
    bằng ẢNH của shot ĐẦU TIÊN rồi phát audio đó lên trên, ở ĐẦU video. Verify THẬT qua
    `assemble_video()` (không mock): (1) tổng thời lượng = audio intro + shot (audio
    THẬT SỰ được ghép, không chỉ báo thành công), (2) 1 GIÂY ĐẦU của audio track kết quả
    phải có TIẾNG THẬT (âm lượng gần với audio thương hiệu gốc), KHÁC hẳn im lặng (nếu
    bug — audio thương hiệu không được ghép — 1 giây đầu sẽ là audio CÂM của shot, đo
    được rõ ràng bằng `volumedetect`, không đoán bằng tai)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    # Audio thương hiệu THẬT (sine 440Hz, không phải im lặng) — CHỈ audio, không video.
    intro_audio_src = tmp_path / "brand_intro.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "mp3", str(intro_audio_src)], capture_output=True, check=True, text=True)
    upload = client.post(f"/channels/{channel_id}/brandprofile/intro/upload", files={"file": ("intro.mp3", intro_audio_src.open("rb"), "audio/mpeg")})
    assert upload.status_code == 200, upload.text
    assert upload.json()["intro_audio_path"]
    assert upload.json()["intro_video_path"] == ""

    # 1 shot ẢNH (KHÔNG narration — im lặng, để phân biệt rõ với audio thương hiệu).
    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "blue", shot_png)
    state = RenderState(project_id=pid, shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])
    assert final_path.exists() and final_path.stat().st_size > 0

    total_duration = _ffprobe_duration(final_path)
    assert total_duration == pytest.approx(3.0, abs=0.6)  # ~1s audio thương hiệu + ~2s shot (B01 0:00-0:02)

    first_second_db = _mean_volume_db(ffmpeg, final_path, duration=1.0)
    assert first_second_db > -50, f"1 giây đầu gần như im lặng ({first_second_db}dB) — audio thương hiệu KHÔNG được ghép vào đầu video (bug thật người dùng báo)"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_project_intro_audio_only_uses_first_shot_image(client, project, tmp_path):
    """Theo yêu cầu người dùng (2026-08-20): "Khi có audio mà ko có ảnh thì sử dụng ảnh
    ở shot đầu tiên ngay sau đó luôn" — áp dụng cho CHÍNH shot mở đầu của project (không
    chỉ audio thương hiệu cấp kênh). Verify: audio mở đầu project (không kèm ảnh) VẪN
    được ghép vào đầu video (có tiếng thật), và vẫn ưu tiên hơn brand intro (nếu có)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    # Audio mở đầu RIÊNG của project — KHÔNG kèm ảnh/video.
    project_audio_src = tmp_path / "open.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=1500:duration=1", "-c:a", "mp3", str(project_audio_src)], capture_output=True, check=True, text=True)
    upload = client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", project_audio_src.open("rb"), "audio/mpeg")})
    assert upload.status_code == 200, upload.text
    assert upload.json()["intro"]["visual_asset_path"] is None

    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "green", shot_png)
    state = RenderState.model_validate(client.get(f"/projects/{pid}/render/status").json())
    state.shots = [ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)]
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    first_second_db = _mean_volume_db(ffmpeg, final_path, duration=1.0)
    assert first_second_db > -50, f"1 giây đầu gần như im lặng ({first_second_db}dB) — audio mở đầu project (không kèm ảnh) KHÔNG được ghép vào"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_project_intro_overrides_brand_audio_only_intro(client, project, tmp_path):
    """Bug thật người dùng báo (2026-08-20): "có vẻ khi có cả audio đã upload ở brand
    profile và Shot ban đầu ở visual studio, thì shot ban đầu chưa override audio của
    brand profile" — verify riêng combo NÀY (brand AUDIO-ONLY, không phải brand VIDEO
    như test override khác đã có), vì đây là 1 nhánh khác trong `_resolve_intro_source`
    (ưu tiên project override PHẢI đứng TRƯỚC cả nhánh brand video LẪN brand audio)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    # Brand audio-only (sẽ bị override, KHÔNG được xuất hiện trong kết quả).
    brand_audio_src = tmp_path / "brand_intro.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=1", "-c:a", "mp3", str(brand_audio_src)], capture_output=True, check=True, text=True)
    client.post(f"/channels/{channel_id}/brandprofile/intro/upload", files={"file": ("intro.mp3", brand_audio_src.open("rb"), "audio/mpeg")})

    # Shot mở đầu RIÊNG của project — ảnh VÀNG + audio khác.
    yellow_png = tmp_path / "open.png"
    _solid_color_png(ffmpeg, "yellow", yellow_png)
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.png", yellow_png.open("rb"), "image/png")})
    project_audio_src = tmp_path / "open.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=1", "-c:a", "mp3", str(project_audio_src)], capture_output=True, check=True, text=True)
    client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", project_audio_src.open("rb"), "audio/mpeg")})

    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "green", shot_png)

    state = client.get(f"/projects/{pid}/render/status").json()
    render_state = RenderState.model_validate(state)
    render_state.shots = [ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)]
    write_json(pdir / "render.json", render_state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    # Frame đầu phải VÀNG (project intro), không phải XANH LÁ (shot) — xác nhận intro
    # project được dùng, không bỏ qua thẳng tới shot.
    probe = subprocess.run(
        [ffmpeg, "-y", "-i", str(final_path), "-vf", "format=rgb24,crop=1:1:10:10", "-f", "rawvideo", "-pix_fmt", "rgb24", "-frames:v", "1", "-"],
        capture_output=True, check=True,
    )
    r, g, b = probe.stdout[0], probe.stdout[1], probe.stdout[2]
    assert r > 150 and g > 150 and b < 100, f"Frame đầu không vàng như shot mở đầu project — RGB=({r},{g},{b})"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_project_intro_overrides_brand_intro(client, project, tmp_path):
    """Shot mở đầu RIÊNG của project (màu VÀNG) phải override video thương hiệu kênh
    (màu ĐỎ) — frame đầu ra phải là VÀNG, không phải ĐỎ."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    # Brand intro ĐỎ (sẽ bị override, không được xuất hiện trong kết quả).
    brand_intro_src = tmp_path / "brand_intro.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(brand_intro_src)],
        capture_output=True, check=True, text=True,
    )
    client.post(f"/channels/{channel_id}/brandprofile/intro/upload", files={"file": ("intro.mp4", brand_intro_src.open("rb"), "video/mp4")})

    # Shot mở đầu RIÊNG của project — ảnh VÀNG + audio, qua API thật.
    yellow_png = tmp_path / "open.png"
    _solid_color_png(ffmpeg, "yellow", yellow_png)
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.png", yellow_png.open("rb"), "image/png")})
    audio_src = tmp_path / "open.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "mp3", str(audio_src)], capture_output=True, check=True, text=True)
    client.post(f"/projects/{pid}/render/intro/upload-audio", files={"file": ("open.mp3", audio_src.open("rb"), "audio/mpeg")})

    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "green", shot_png)

    state = client.get(f"/projects/{pid}/render/status").json()
    render_state = RenderState.model_validate(state)
    render_state.shots = [ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)]
    write_json(pdir / "render.json", render_state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    probe = subprocess.run(
        [ffmpeg, "-y", "-i", str(final_path), "-vf", "format=rgb24,crop=1:1:10:10", "-f", "rawvideo", "-pix_fmt", "rgb24", "-frames:v", "1", "-"],
        capture_output=True, check=True,
    )
    r, g, b = probe.stdout[0], probe.stdout[1], probe.stdout[2]
    # Vàng ≈ (255,255,0) — r VÀ g đều cao, b thấp. Đỏ (brand, phải bị override) có g thấp.
    assert r > 150 and g > 150 and b < 100, f"Frame đầu không vàng như shot mở đầu project — RGB=({r},{g},{b}), project intro có thể chưa override được brand intro"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_intro_transition_fade_blends_shorter_than_hard_cut(client, project, tmp_path):
    """Hiệu ứng chuyển cảnh intro→thân video — **mới (2026-08-21)**, theo yêu cầu người
    dùng (trước đây LUÔN cắt cứng, không cấu hình được). Verify THẬT (không mock, gọi
    `assemble_video()` 2 lần): `_xfade_chain` BLEND ~0.6s chồng lấp giữa intro và shot
    đầu khi transition khác "cut" — nên tổng thời lượng phải NGẮN HƠN RÕ RỆT so với
    "cut" (nối cứng, cộng dồn đủ cả 2 đoạn không mất giây nào) — cùng nguyên lý đã verify
    cho xfade giữa 2 shot thường (mục 43/47), giờ áp dụng thêm cho ranh giới intro."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    # Shot mở đầu RIÊNG của project — video đỏ 1 giây.
    intro_src = tmp_path / "open.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(intro_src)],
        capture_output=True, check=True, text=True,
    )
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.mp4", intro_src.open("rb"), "video/mp4")})

    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "green", shot_png)
    state = RenderState.model_validate(client.get(f"/projects/{pid}/render/status").json())
    state.shots = [ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)]
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")
    cut_state = client.get(f"/projects/{pid}/render/status").json()
    assert cut_state["assembly_status"] == "done", cut_state.get("assembly_error")
    cut_duration = _ffprobe_duration(Path(cut_state["final_video_path"]))

    resp = client.patch(f"/projects/{pid}/render/intro/transition", json={"transition_to_next": "fade"})
    assert resp.status_code == 200 and resp.json()["intro"]["transition_to_next"] == "fade"

    assemble_video(pid, resolution="720p", codec="h264", quality="low")
    fade_state = client.get(f"/projects/{pid}/render/status").json()
    assert fade_state["assembly_status"] == "done", fade_state.get("assembly_error")
    fade_duration = _ffprobe_duration(Path(fade_state["final_video_path"]))

    assert fade_duration < cut_duration - 0.3, (
        f"fade ({fade_duration:.2f}s) không ngắn hơn rõ rệt so với cut ({cut_duration:.2f}s) "
        "— có thể chưa thật sự blend (xfade), chỉ nối cứng như cũ"
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_intro_fade_transition_preserves_mismatched_rate_narration(client, project, tmp_path):
    """Bug thật người dùng báo (2026-08-21, mục 57 IMPLEMENTATION_REPORT.md), project
    "Skip brief test": video render xong nhưng KHÔNG NGHE THẤY giọng đọc — điều tra thật
    trên đúng project đó xác nhận nguyên nhân: narration từ provider OmniVoice xuất ra
    24kHz MONO (khác 44.1kHz STEREO dùng cho intro/nhạc nền/mọi nơi khác), phối hợp với
    intro có transition khác "cut" (dùng `_xfade_chain`, mới thêm ở mục 55) làm audio
    của TOÀN BỘ thân video sau intro bị MẤT HẲN (đo thật bằng `ffprobe`: `n_samples: 0`
    từ đúng điểm sau intro trở đi, KHÔNG PHẢI chỉ nhỏ tiếng).

    Tái hiện CHÍNH XÁC tổ hợp gây lỗi: intro VIDEO 44.1kHz stereo + transition "fade" +
    1 shot có narration 24kHz MONO (giả lập đúng định dạng OmniVoice, KHÔNG PHẢI 44.1kHz
    stereo như các test khác vẫn dùng — đó là lý do bug này lọt qua mọi test trước đó).
    Verify bằng đo VOLUME THẬT tại điểm SAU intro (không chỉ đo trước intro, đúng chỗ bug
    xảy ra) — phải CÓ TIẾNG THẬT, không im lặng."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    # Intro VIDEO chuẩn 44.1kHz stereo (giống video thương hiệu người dùng tự upload).
    intro_src = tmp_path / "open.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2", "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-ar", "44100", "-ac", "2", "-c:a", "aac", str(intro_src)],
        capture_output=True, check=True, text=True,
    )
    client.post(f"/projects/{pid}/render/intro/upload-visual", files={"file": ("open.mp4", intro_src.open("rb"), "video/mp4")})
    resp = client.patch(f"/projects/{pid}/render/intro/transition", json={"transition_to_next": "fade"})
    assert resp.status_code == 200

    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "green", shot_png)

    # Narration 24kHz MONO — ĐÚNG định dạng OmniVoice thật (không phải 44.1kHz stereo
    # như mọi test khác trong repo dùng — chính sự khác biệt này khiến bug lọt lưới).
    narration_src = tmp_path / f"{shot_id}.wav"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=1200:duration=3", "-ar", "24000", "-ac", "1", str(narration_src)],
        capture_output=True, check=True, text=True,
    )
    narration_dur = _ffprobe_duration(narration_src)

    state = RenderState.model_validate(client.get(f"/projects/{pid}/render/status").json())
    state.shots = [ShotRenderStatus(
        shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True,
        narration_status="ready", narration_asset_path=str(narration_src), narration_duration_sec=narration_dur,
    )]
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    total_duration = _ffprobe_duration(final_path)
    # ~2s intro + ~3s narration - ~0.6s chồng lấp fade (không cần chính xác tuyệt đối,
    # chỉ cần xác nhận KHÔNG bị cắt cụt bất thường so với tổng thô).
    assert total_duration > 3.5, f"Video ra chỉ {total_duration:.2f}s — ngắn bất thường, có thể thân video sau intro đã bị mất"

    # Điểm mấu chốt của bug: đo tiếng NGAY TẠI/SAU điểm intro kết thúc (không chỉ đầu
    # video) — đây là đúng chỗ audio bị mất hoàn toàn trước khi fix.
    after_intro_db = _mean_volume_db(ffmpeg, final_path, ss=total_duration - 1.5, duration=1.0)
    assert after_intro_db > -50, (
        f"Gần như im lặng ({after_intro_db}dB) ở đoạn SAU intro — narration 24kHz mono bị mất khi ghép "
        "với intro 44.1kHz stereo qua transition fade (đúng bug thật đã báo, xem mục 57)"
    )
