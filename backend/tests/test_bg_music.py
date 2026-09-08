"""Test tính năng nhạc nền (background music) — mặc định cấp kênh (BrandProfile) +
override riêng của project (2026-08-20, theo yêu cầu người dùng) — xem
`app/render/bg_music.py::resolve_bg_music_source` cho thứ tự ưu tiên: project override
> nhạc nền mặc định cấp kênh.
"""
import io
import shutil
import subprocess
from pathlib import Path

import pytest

FAKE_MP3 = b"ID3" + b"0" * 20


# ---------------------------------------------------------------------------
# Channel-level: POST/GET /channels/{id}/brandprofile/bg-music
# ---------------------------------------------------------------------------
def test_upload_brand_bg_music_sets_path(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/bg-music/upload",
        files={"file": ("music.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")},
    )
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["bg_music_path"]

    fetched = client.get(f"/channels/{channel['id']}/brandprofile").json()
    assert fetched["bg_music_path"] == profile["bg_music_path"]


def test_upload_brand_bg_music_rejects_unknown_file_type(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/bg-music/upload",
        files={"file": ("music.txt", io.BytesIO(b"khong phai audio"), "text/plain")},
    )
    assert resp.status_code == 400


def test_get_brand_bg_music_404_when_none(client, channel):
    resp = client.get(f"/channels/{channel['id']}/brandprofile/bg-music")
    assert resp.status_code == 404


def test_get_brand_bg_music_serves_uploaded_file(client, channel):
    client.post(f"/channels/{channel['id']}/brandprofile/bg-music/upload", files={"file": ("music.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    resp = client.get(f"/channels/{channel['id']}/brandprofile/bg-music")
    assert resp.status_code == 200
    assert resp.content == FAKE_MP3


def test_set_brand_bg_music_volume_via_put(client, channel):
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["bg_music_volume"] = 0.5
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile)
    assert resp.status_code == 200
    assert resp.json()["bg_music_volume"] == 0.5


def test_clear_brand_bg_music_via_put(client, channel):
    client.post(f"/channels/{channel['id']}/brandprofile/bg-music/upload", files={"file": ("music.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["bg_music_path"] = ""
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile)
    assert resp.status_code == 200
    assert resp.json()["bg_music_path"] == ""
    assert client.get(f"/channels/{channel['id']}/brandprofile/bg-music").status_code == 404


# ---------------------------------------------------------------------------
# Project-level: /projects/{id}/render/bg-music (override)
# ---------------------------------------------------------------------------
def test_upload_project_bg_music_sets_asset_path(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/bg-music/upload", files={"file": ("music.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    assert resp.status_code == 200
    state = resp.json()
    assert state["bg_music"]["asset_path"]
    assert state["bg_music"]["volume"] == pytest.approx(0.3)  # mặc định


def test_patch_project_bg_music_volume(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/bg-music/upload", files={"file": ("music.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    resp = client.patch(f"/projects/{pid}/render/bg-music", json={"volume": 0.7})
    assert resp.status_code == 200
    assert resp.json()["bg_music"]["volume"] == pytest.approx(0.7)


def test_patch_project_bg_music_volume_creates_override_if_missing(client, project):
    pid = project["id"]
    resp = client.patch(f"/projects/{pid}/render/bg-music", json={"volume": 0.6})
    assert resp.status_code == 200
    assert resp.json()["bg_music"]["volume"] == pytest.approx(0.6)
    assert resp.json()["bg_music"]["asset_path"] is None


def test_delete_project_bg_music_clears_state_and_file(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/bg-music/upload", files={"file": ("music.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    status_before = client.get(f"/projects/{pid}/render/status").json()
    asset_path = Path(status_before["bg_music"]["asset_path"])
    assert asset_path.exists()

    resp = client.delete(f"/projects/{pid}/render/bg-music")
    assert resp.status_code == 200
    assert resp.json()["bg_music"] is None
    assert not asset_path.exists()


def test_get_project_bg_music_asset_serves_file(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/bg-music/upload", files={"file": ("music.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    resp = client.get(f"/projects/{pid}/render/bg-music/asset")
    assert resp.status_code == 200
    assert resp.content == FAKE_MP3


def test_get_project_bg_music_asset_404_when_none(client, project):
    resp = client.get(f"/projects/{project['id']}/render/bg-music/asset")
    assert resp.status_code == 404


def test_upload_project_bg_music_rejects_unknown_file_type(client, project):
    resp = client.post(f"/projects/{project['id']}/render/bg-music/upload", files={"file": ("music.txt", io.BytesIO(b"khong phai audio"), "text/plain")})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# `resolve_bg_music_source` — logic ưu tiên thuần (không cần ffmpeg thật)
# ---------------------------------------------------------------------------
def test_resolve_bg_music_source_prefers_project_override():
    from app.render.bg_music import resolve_bg_music_source
    from app.render.schemas import BgMusicOverride

    project_bg = BgMusicOverride(asset_path="/tmp/project_music.mp3", volume=0.5)
    brand = {"bg_music_path": "/tmp/brand_music.mp3", "bg_music_volume": 0.3}
    result = resolve_bg_music_source(project_bg, brand)
    assert result == ("/tmp/project_music.mp3", 0.5)


def test_resolve_bg_music_source_falls_back_to_brand():
    from app.render.bg_music import resolve_bg_music_source

    brand = {"bg_music_path": "/tmp/brand_music.mp3", "bg_music_volume": 0.4}
    result = resolve_bg_music_source(None, brand)
    assert result == ("/tmp/brand_music.mp3", 0.4)


def test_resolve_bg_music_source_uses_project_volume_with_brand_asset_when_no_project_asset():
    """Đổi hành vi (2026-08-23): override CHƯA có `asset_path` (chỉ chỉnh volume, chưa
    upload nhạc riêng) vẫn phải áp dụng ĐƯỢC phần volume — dùng file nhạc của BRAND
    nhưng với volume RIÊNG của project (cho phép "dùng nhạc brand, chỉnh âm lượng
    riêng" không cần upload lại file)."""
    from app.render.bg_music import resolve_bg_music_source
    from app.render.schemas import BgMusicOverride

    project_bg = BgMusicOverride(asset_path=None, volume=0.7)  # chỉ chỉnh volume, chưa upload
    brand = {"bg_music_path": "/tmp/brand_music.mp3", "bg_music_volume": 0.3}
    result = resolve_bg_music_source(project_bg, brand)
    assert result == ("/tmp/brand_music.mp3", 0.7)


def test_resolve_bg_music_source_none_when_nothing_configured():
    from app.render.bg_music import resolve_bg_music_source

    assert resolve_bg_music_source(None, {}) is None


# ---------------------------------------------------------------------------
# `_mix_bg_music` — real ffmpeg
# ---------------------------------------------------------------------------
def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return float(out.stdout.strip())


def _mean_volume_db(ffmpeg: str, path: Path, *, ss: float | None = None, duration: float | None = None) -> float:
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
def test_mix_bg_music_bounds_output_to_video_duration_even_with_short_looped_music(tmp_path):
    """Nhạc nền NGẮN HƠN video nhiều lần (1s nhạc, 3s video) — `-stream_loop -1` phải
    lặp đủ, nhưng `amix=duration=first` phải CHẶN output ở đúng độ dài video (KHÔNG bị
    kéo dài vô hạn theo nhạc nền lặp mãi)."""
    from app.render.assembly import _mix_bg_music

    ffmpeg = shutil.which("ffmpeg")
    # Video/narration audio CÂM (anullsrc) — tiếng nghe được ở BẤT KỲ điểm nào của
    # output chỉ có thể đến từ nhạc nền, không lẫn với nguồn khác (tránh false positive).
    video_path = tmp_path / "video_narration.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=3", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video_path)],
        capture_output=True, check=True, text=True,
    )
    bg_music_path = tmp_path / "bgmusic_1s.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=1", "-c:a", "mp3", str(bg_music_path)], capture_output=True, check=True, text=True)

    out_path = tmp_path / "mixed_out.mp4"
    _mix_bg_music(ffmpeg, video_path, str(bg_music_path), 0.3, out_path, audio_codec="aac")

    assert out_path.exists()
    assert _ffprobe_duration(out_path) == pytest.approx(3.0, abs=0.2)

    # Nhạc nền lặp lại phải NGHE THẤY ở giây thứ 2 (sau khi vòng lặp đầu 1s hết) —
    # narration/video gốc CÂM, nên tiếng đo được CHỈ có thể tới từ nhạc nền đã lặp lại.
    db_second_loop = _mean_volume_db(ffmpeg, out_path, ss=1.5, duration=0.3)
    assert db_second_loop > -50, f"Giây thứ 2 gần như im lặng ({db_second_loop}dB) — nhạc nền có thể KHÔNG được lặp lại đúng"


# ---------------------------------------------------------------------------
# End-to-end: assemble_video() thật trộn nhạc nền vào TOÀN BỘ video — real ffmpeg.
# ---------------------------------------------------------------------------
def _import_one_image_shot(client, pid: str) -> str:
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:03", "Image", "Canh xanh la", "Khong tieng", "Loi thoai test."]]
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
def test_assemble_mixes_brand_bg_music_under_whole_video(client, project, tmp_path):
    """Nhạc nền mặc định cấp kênh (không có project override) phải được trộn vào SUỐT
    video, kể cả khi không có intro. Verify THẬT (không mock): (1) có tiếng ở CẢ giây
    đầu lẫn giây cuối (nhạc nền phủ toàn bộ, không chỉ 1 đoạn), (2) tổng thời lượng
    KHÔNG bị kéo dài quá độ dài shot gốc (bg music không làm video dài thêm)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    bg_music_src = tmp_path / "brand_music.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=1", "-c:a", "mp3", str(bg_music_src)], capture_output=True, check=True, text=True)
    upload = client.post(f"/channels/{channel_id}/brandprofile/bg-music/upload", files={"file": ("music.mp3", bg_music_src.open("rb"), "audio/mpeg")})
    assert upload.status_code == 200, upload.text

    shot_id = _import_one_image_shot(client, pid)
    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    _solid_color_png(ffmpeg, "green", shot_png)
    state = RenderState(project_id=pid, shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])
    assert final_path.exists() and final_path.stat().st_size > 0

    total_duration = _ffprobe_duration(final_path)
    assert total_duration == pytest.approx(3.0, abs=0.5)  # ~3s shot (B01 0:00-0:03), KHÔNG dài thêm vì nhạc nền

    db_start = _mean_volume_db(ffmpeg, final_path, duration=0.5)
    db_end = _mean_volume_db(ffmpeg, final_path, ss=2.5, duration=0.4)
    assert db_start > -50, f"Đầu video gần như im lặng ({db_start}dB) — nhạc nền không được trộn vào"
    assert db_end > -50, f"Cuối video gần như im lặng ({db_end}dB) — nhạc nền không phủ hết toàn bộ video (không lặp lại đủ)"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_project_bg_music_overrides_brand_bg_music(client, project, tmp_path):
    """Nhạc nền RIÊNG của project phải override nhạc nền mặc định cấp kênh — verify qua
    tần số khác nhau: brand dùng 200Hz (không được nghe thấy), project dùng 3000Hz."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    brand_music_src = tmp_path / "brand_music.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=1", "-c:a", "mp3", str(brand_music_src)], capture_output=True, check=True, text=True)
    client.post(f"/channels/{channel_id}/brandprofile/bg-music/upload", files={"file": ("music.mp3", brand_music_src.open("rb"), "audio/mpeg")})

    project_music_src = tmp_path / "project_music.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=3000:duration=1", "-c:a", "mp3", str(project_music_src)], capture_output=True, check=True, text=True)
    upload = client.post(f"/projects/{pid}/render/bg-music/upload", files={"file": ("music.mp3", project_music_src.open("rb"), "audio/mpeg")})
    assert upload.status_code == 200, upload.text

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

    db_start = _mean_volume_db(ffmpeg, final_path, duration=0.5)
    assert db_start > -50, f"Đầu video gần như im lặng ({db_start}dB) — nhạc nền project override KHÔNG được trộn vào"

    # Phân biệt ĐÚNG nguồn nhạc bằng tần số (không chỉ "có tiếng"): lọc `highpass=f=2000`
    # trước khi đo — brand (200Hz) sẽ bị cắt gần hết, project (3000Hz) vẫn còn rõ. Còn
    # tiếng SAU khi lọc cao tần => xác nhận đúng nhạc PROJECT được dùng, không phải brand.
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(final_path), "-t", "0.5", "-af", "highpass=f=2000,volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    db_highpass = None
    for line in result.stderr.splitlines():
        if "mean_volume:" in line:
            db_highpass = float(line.split("mean_volume:")[1].strip().split(" ")[0])
    assert db_highpass is not None
    assert db_highpass > -50, f"Sau khi lọc bỏ tần số thấp (200Hz brand), vẫn im lặng ({db_highpass}dB) — có thể đang phát nhạc BRAND (200Hz) thay vì PROJECT (3000Hz), tức override KHÔNG hoạt động"
