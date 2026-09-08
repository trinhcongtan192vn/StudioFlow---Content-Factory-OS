"""Video nền CHUNG cho toàn bộ block (2026-09-02, theo yêu cầu người dùng) — NHIỀU video
(mục 110) nối thành 1 "playlist" (cắt cứng hoặc xfade giữa các video, tuỳ chọn xáo trộn
thứ tự mỗi lượt ghép qua `random_order`) rồi loop theo tổng thời lượng timeline shot
list; shot CHƯA cấu hình visual riêng tự lấy đúng đoạn nền tương ứng trên timeline, shot
ĐÃ có visual riêng thay thế TOÀN MÀN HÌNH cho đúng khoảng thời gian của nó — xem
`app/render/schemas.py::BackgroundVideoOverride`, `app/render/assembly.py::assemble_video`
(phần dựng `_bg_playlist`/`_bg_master`/cắt chunk).
"""
import io
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20


# ---------------------------------------------------------------------------
# Endpoint CRUD — mirror test_overlay.py/test_bg_music.py, đổi cho danh sách NHIỀU video
# (mục 110) thay vì 1 video đơn.
# ---------------------------------------------------------------------------
def test_upload_project_background_video_appends_to_list(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("bg.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    assert resp.status_code == 200, resp.text
    first_paths = resp.json()["background_video"]["asset_paths"]
    assert len(first_paths) == 1 and first_paths[0]

    resp2 = client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("bg2.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    assert resp2.status_code == 200, resp2.text
    paths = resp2.json()["background_video"]["asset_paths"]
    assert len(paths) == 2
    assert paths[0] != paths[1]  # tên file khác nhau (mốc thời gian), không đè lên nhau


def test_upload_project_background_video_rejects_unknown_file_type(client, project):
    resp = client.post(f"/projects/{project['id']}/render/background-video/upload", files={"file": ("bg.txt", io.BytesIO(b"khong phai video"), "text/plain")})
    assert resp.status_code == 400


def test_delete_project_background_video_item_removes_only_that_index(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("a.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("b.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    state_before = client.get(f"/projects/{pid}/render/status").json()
    path0, path1 = state_before["background_video"]["asset_paths"]
    assert Path(path0).exists() and Path(path1).exists()

    resp = client.delete(f"/projects/{pid}/render/background-video/0")
    assert resp.status_code == 200, resp.text
    paths_after = resp.json()["background_video"]["asset_paths"]
    assert paths_after == [path1]
    assert not Path(path0).exists()  # file đã xoá
    assert Path(path1).exists()  # video còn lại KHÔNG bị đụng


def test_delete_project_background_video_item_404_out_of_range(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("a.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    resp = client.delete(f"/projects/{pid}/render/background-video/5")
    assert resp.status_code == 404


def test_delete_project_background_video_clears_everything(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("a.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("b.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    paths = client.get(f"/projects/{pid}/render/status").json()["background_video"]["asset_paths"]
    assert len(paths) == 2

    resp = client.delete(f"/projects/{pid}/render/background-video")
    assert resp.status_code == 200
    assert resp.json()["background_video"] is None
    assert all(not Path(p).exists() for p in paths)


def test_get_project_background_video_asset_serves_file_by_index(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("a.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    other = b"\x00\x00\x00\x18ftyp" + b"1" * 20
    client.post(f"/projects/{pid}/render/background-video/upload", files={"file": ("b.mp4", io.BytesIO(other), "video/mp4")})

    resp0 = client.get(f"/projects/{pid}/render/background-video/asset/0")
    assert resp0.status_code == 200
    assert resp0.content == FAKE_MP4
    resp1 = client.get(f"/projects/{pid}/render/background-video/asset/1")
    assert resp1.status_code == 200
    assert resp1.content == other


def test_get_project_background_video_asset_404_when_none(client, project):
    resp = client.get(f"/projects/{project['id']}/render/background-video/asset/0")
    assert resp.status_code == 404


def test_patch_background_video_settings_saves_random_order_and_transition(client, project):
    pid = project["id"]
    resp = client.patch(f"/projects/{pid}/render/background-video", json={"random_order": True, "transition": "fade"})
    assert resp.status_code == 200, resp.text
    bg = resp.json()["background_video"]
    assert bg["random_order"] is True
    assert bg["transition"] == "fade"

    # Partial update — chỉ gửi 1 field, field kia giữ nguyên.
    resp2 = client.patch(f"/projects/{pid}/render/background-video", json={"random_order": False})
    assert resp2.json()["background_video"]["random_order"] is False
    assert resp2.json()["background_video"]["transition"] == "fade"


def test_patch_background_video_settings_rejects_unknown_transition(client, project):
    resp = client.patch(f"/projects/{project['id']}/render/background-video", json={"transition": "khong-ton-tai"})
    assert resp.status_code == 400


def test_background_video_defaults(client, project):
    """Chưa cấu hình gì — `background_video` là `null` (khác bg_music/overlay có thể tự
    tạo entry rỗng), khớp hành vi gốc trước mục 110."""
    status = client.get(f"/projects/{project['id']}/render/status").json()
    assert status["background_video"] is None


# ---------------------------------------------------------------------------
# ffmpeg thật — helper dùng chung
# ---------------------------------------------------------------------------
def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return float(out.stdout.strip())


def _extract_frame_color(ffmpeg: str, video_path: Path, t: float, tmp_path: Path, name: str) -> tuple[int, int, int]:
    frame_path = tmp_path / name
    subprocess.run([ffmpeg, "-y", "-ss", str(t), "-i", str(video_path), "-frames:v", "1", "-update", "1", str(frame_path)], capture_output=True, check=True, text=True)
    img = Image.open(frame_path).convert("RGB")
    # Lấy trung bình cả ảnh (không phải 1 điểm ảnh đơn) — bền hơn trước nhiễu nén H.264 ở
    # rìa ảnh, vẫn đủ phân biệt rõ 2 màu KHÁC HẲN nhau.
    pixels = list(img.getdata())
    n = len(pixels)
    return (sum(p[0] for p in pixels) // n, sum(p[1] for p in pixels) // n, sum(p[2] for p in pixels) // n)


def _solid_color_clip(ffmpeg: str, color: str, out_path: Path, duration: float = 1.0) -> Path:
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={duration}", "-pix_fmt", "yuv420p", str(out_path)], capture_output=True, check=True, text=True)
    return out_path


# ---------------------------------------------------------------------------
# `_build_background_video_playlist` — ffmpeg thật, unit-level (mới, mục 110)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_background_video_playlist_cut_concatenates_in_order(tmp_path):
    from app.render.assembly import _build_background_video_playlist

    ffmpeg = shutil.which("ffmpeg")
    green = _solid_color_clip(ffmpeg, "green", tmp_path / "green.mp4", duration=1.0)
    yellow = _solid_color_clip(ffmpeg, "yellow", tmp_path / "yellow.mp4", duration=1.0)

    out = tmp_path / "playlist.mp4"
    _build_background_video_playlist(ffmpeg, [str(green), str(yellow)], "cut", out, resolution="320:240", video_codec="libx264", crf=28, brand=None)

    assert _ffprobe_duration(out) == pytest.approx(2.0, abs=0.3)
    r0, g0, b0 = _extract_frame_color(ffmpeg, out, 0.3, tmp_path, "early.png")
    assert g0 > 100 and r0 < 30 and b0 < 30, f"Đầu playlist phải là XANH LÁ (green trước) — ra {(r0, g0, b0)}"
    r1, g1, b1 = _extract_frame_color(ffmpeg, out, 1.7, tmp_path, "late.png")
    assert r1 > 150 and g1 > 150 and b1 < 100, f"Cuối playlist phải là VÀNG (yellow sau) — ra {(r1, g1, b1)}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_background_video_playlist_transition_blends_and_shortens_total(tmp_path):
    """Khác "cut" — dùng `xfade` THẬT, tổng thời lượng phải NGẮN HƠN tổng 2 clip cộng lại
    (do overlap khi blend), khác hẳn "cut" (nối liền, tổng = đúng tổng 2 clip)."""
    from app.render.assembly import _XFADE_DURATION_SEC, _build_background_video_playlist

    ffmpeg = shutil.which("ffmpeg")
    green = _solid_color_clip(ffmpeg, "green", tmp_path / "green.mp4", duration=2.0)
    yellow = _solid_color_clip(ffmpeg, "yellow", tmp_path / "yellow.mp4", duration=2.0)

    out = tmp_path / "playlist_fade.mp4"
    _build_background_video_playlist(ffmpeg, [str(green), str(yellow)], "fade", out, resolution="320:240", video_codec="libx264", crf=28, brand=None)

    total = _ffprobe_duration(out)
    assert total == pytest.approx(4.0 - _XFADE_DURATION_SEC, abs=0.3)
    assert total < 4.0 - 0.1  # rõ ràng ngắn hơn tổng thô, xác nhận có blend thật


# ---------------------------------------------------------------------------
# Assembly thật — ffmpeg thật, không mock (verify THẬT hành vi ghép, không phải suy đoán)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_fills_blank_shot_with_background_video_slice_and_keeps_own_visual_for_configured_shot(client, project_with_brief, tmp_path):
    """Verify THẬT toàn bộ hành vi CASE 1 VIDEO NỀN (đường ĐƠN GIẢN nhất — không cần
    dựng playlist, xem `needs_playlist` trong `assemble_video`): project 2 shot — shot A
    CÓ visual riêng (video ĐỎ thuần), shot B KHÔNG cấu hình gì (visual_asset_path=None) —
    bật video nền CHUNG (video XANH DƯƠNG thuần). Ghép thật (ffmpeg thật) — xác nhận: (1)
    KHÔNG bị chặn dù shot B chưa có visual (trước đây sẽ raise "chưa sinh xong visual"),
    (2) tổng thời lượng khớp tổng 2 narration, (3) frame trong khoảng shot A ra ĐÚNG màu
    đỏ (giữ visual riêng, không bị nền đè), (4) frame trong khoảng shot B ra ĐÚNG màu
    xanh dương (lấp bằng đúng đoạn nền tương ứng trên timeline)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import BackgroundVideoOverride, RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:02", "Video", "Canh A", "", "Loi thoai block mot."],
        ["B02", "0:02–0:04", "Video", "Canh B", "", "Loi thoai block hai."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_ids = [s["shot_id"] for s in client.post(f"/projects/{pid}/visual/generate").json()["shots"]]
    assert len(shot_ids) == 2
    shot_a_id, shot_b_id = shot_ids

    pdir = project_dir(channel_id, pid)

    # Shot A: video ĐỎ thuần 2s + narration 2s.
    shot_a_video = pdir / "assets" / f"{shot_a_id}.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2", "-pix_fmt", "yuv420p", str(shot_a_video)], capture_output=True, check=True, text=True)
    narration_a = pdir / "assets" / f"{shot_a_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(narration_a)], capture_output=True, check=True, text=True)
    dur_a = _ffprobe_duration(narration_a)

    # Shot B: KHÔNG có visual/narration nào — chỉ có narration để biết thời lượng (shot
    # câm hoàn toàn vẫn hợp lệ về mặt kỹ thuật nhưng khó verify màu theo mốc thời gian).
    narration_b = pdir / "assets" / f"{shot_b_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(narration_b)], capture_output=True, check=True, text=True)
    dur_b = _ffprobe_duration(narration_b)

    # Video nền CHUNG: XANH DƯƠNG thuần, cố tình NGẮN hơn hẳn tổng timeline (1s) để verify
    # luôn cả việc LOOP hoạt động đúng (không chỉ trim 1 đoạn từ video dài đủ).
    bg_video = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-pix_fmt", "yuv420p", str(bg_video)], capture_output=True, check=True, text=True)

    state = RenderState(
        project_id=pid,
        shots=[
            ShotRenderStatus(
                shot_id=shot_a_id, visual_status="ready", visual_asset_path=str(shot_a_video), approved=True,
                narration_status="ready", narration_asset_path=str(narration_a), narration_duration_sec=dur_a,
            ),
            ShotRenderStatus(
                shot_id=shot_b_id,  # KHÔNG set visual_asset_path — shot trống, đúng kịch bản cần test
                narration_status="ready", narration_asset_path=str(narration_b), narration_duration_sec=dur_b,
            ),
        ],
        background_video=BackgroundVideoOverride(asset_paths=[str(bg_video)]),
    )
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])
    total_duration = _ffprobe_duration(final_path)
    assert total_duration == pytest.approx(dur_a + dur_b, abs=0.5)

    color_in_shot_a = _extract_frame_color(ffmpeg, final_path, dur_a * 0.5, tmp_path, "frame_a.png")
    color_in_shot_b = _extract_frame_color(ffmpeg, final_path, dur_a + dur_b * 0.5, tmp_path, "frame_b.png")

    r_a, g_a, b_a = color_in_shot_a
    assert r_a > 150 and g_a < 80 and b_a < 80, f"Shot A (có visual riêng, video ĐỎ) ra màu {color_in_shot_a} — kỳ vọng đỏ, nghi bị nền đè lên"

    r_b, g_b, b_b = color_in_shot_b
    assert b_b > 150 and r_b < 80 and g_b < 80, f"Shot B (KHÔNG cấu hình visual) ra màu {color_in_shot_b} — kỳ vọng xanh dương (video nền), nghi chưa lấp đúng"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_with_multiple_background_videos_builds_playlist_first(client, project_with_brief, tmp_path):
    """Case NHIỀU video nền (mới, mục 110) — 2 video (XANH LÁ + VÀNG, "cut") phải được
    nối thành 1 playlist TRƯỚC khi loop — xác nhận qua kết quả cuối: shot trống dài đủ
    2 video nối tiếp (không loop) phải thấy CẢ 2 màu theo đúng thứ tự upload (random_order
    mặc định False — giữ nguyên thứ tự)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import BackgroundVideoOverride, RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:02", "Image", "Canh trong", "", "Loi thoai dai du de phu 2 video nen."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    narration = pdir / "assets" / f"{shot_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(narration)], capture_output=True, check=True, text=True)
    dur = _ffprobe_duration(narration)

    green = _solid_color_clip(ffmpeg, "green", tmp_path / "green.mp4", duration=1.0)
    yellow = _solid_color_clip(ffmpeg, "yellow", tmp_path / "yellow.mp4", duration=1.0)

    state = RenderState(
        project_id=pid,
        shots=[ShotRenderStatus(shot_id=shot_id, narration_status="ready", narration_asset_path=str(narration), narration_duration_sec=dur)],
        background_video=BackgroundVideoOverride(asset_paths=[str(green), str(yellow)], transition="cut", random_order=False),
    )
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    color_early = _extract_frame_color(ffmpeg, final_path, dur * 0.25, tmp_path, "e.png")
    color_late = _extract_frame_color(ffmpeg, final_path, dur * 0.75, tmp_path, "l.png")
    r0, g0, b0 = color_early
    assert g0 > 100 and r0 < 30 and b0 < 30, f"Nửa đầu (video nền #1 = green) ra {color_early}"
    r1, g1, b1 = color_late
    assert r1 > 150 and g1 > 150 and b1 < 100, f"Nửa sau (video nền #2 = yellow) ra {color_late}"


# ---------------------------------------------------------------------------
# Progress — mục 108, xác nhận vẫn đúng cho CẢ 2 nhánh (1 video vs nhiều video)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_reports_background_video_stage_progress_single_video(client, project_with_brief, tmp_path, monkeypatch):
    """Bug thật (2026-09-02, mục 108): TRƯỚC ĐÂY `assembly_progress` đứng yên ở
    `stage="segments", current=0` SUỐT bước dựng video nền chung — UI hiện nhầm "Đang
    ghép cảnh 0/N..." dù chưa segment nào thật sự bắt đầu. Verify TRỰC TIẾP bằng cách spy
    quanh các hàm ffmpeg thật, đọc LẠI render.json NGAY TRƯỚC mỗi lần gọi. Case 1 video —
    `needs_playlist=False` (mục 110), KHÔNG có bước "background_video/playlist" riêng,
    `bg_total = 1 (master) + len(blank_indices)` — giữ NGUYÊN đúng hành vi trước mục 110."""
    import app.render.assembly as assembly_mod
    from app.config import project_dir
    from app.filestore import write_json
    from app.render import engine as render_engine
    from app.render.schemas import BackgroundVideoOverride, RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:01", "Video", "Canh A", "", "Loi thoai mot."],
        ["B02", "0:01–0:02", "Video", "Canh B", "", "Loi thoai hai."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_a_id, shot_b_id = [s["shot_id"] for s in client.post(f"/projects/{pid}/visual/generate").json()["shots"]]

    pdir = project_dir(channel_id, pid)
    shot_a_video = pdir / "assets" / f"{shot_a_id}.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-pix_fmt", "yuv420p", str(shot_a_video)], capture_output=True, check=True, text=True)
    narration_a = pdir / "assets" / f"{shot_a_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(narration_a)], capture_output=True, check=True, text=True)
    narration_b = pdir / "assets" / f"{shot_b_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", str(narration_b)], capture_output=True, check=True, text=True)
    bg_video = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-pix_fmt", "yuv420p", str(bg_video)], capture_output=True, check=True, text=True)

    state = RenderState(
        project_id=pid,
        shots=[
            ShotRenderStatus(shot_id=shot_a_id, visual_status="ready", visual_asset_path=str(shot_a_video), approved=True, narration_status="ready", narration_asset_path=str(narration_a), narration_duration_sec=1.0),
            ShotRenderStatus(shot_id=shot_b_id, narration_status="ready", narration_asset_path=str(narration_b), narration_duration_sec=1.0),  # shot trống — kích hoạt nhánh video nền
        ],
        background_video=BackgroundVideoOverride(asset_paths=[str(bg_video)]),
    )
    write_json(pdir / "render.json", state.model_dump())

    observed: list[tuple] = []

    real_build_master = assembly_mod._build_background_video_master

    def spy_build_master(*args, **kwargs):
        s = render_engine.load_render_state(pdir, pid)
        observed.append(("before_master", s.assembly_progress.stage, s.assembly_progress.current, s.assembly_progress.total, s.assembly_progress.stage_started_at))
        return real_build_master(*args, **kwargs)

    real_extract_chunk = assembly_mod._extract_background_video_chunk

    def spy_extract_chunk(*args, **kwargs):
        s = render_engine.load_render_state(pdir, pid)
        observed.append(("before_chunk", s.assembly_progress.stage, s.assembly_progress.current, s.assembly_progress.total, s.assembly_progress.stage_started_at))
        return real_extract_chunk(*args, **kwargs)

    real_build_segment = assembly_mod._build_segment

    def spy_build_segment(*args, **kwargs):
        s = render_engine.load_render_state(pdir, pid)
        observed.append(("before_segment", s.assembly_progress.stage, s.assembly_progress.current, s.assembly_progress.total, s.assembly_progress.stage_started_at))
        return real_build_segment(*args, **kwargs)

    monkeypatch.setattr(assembly_mod, "_build_background_video_master", spy_build_master)
    monkeypatch.setattr(assembly_mod, "_extract_background_video_chunk", spy_extract_chunk)
    monkeypatch.setattr(assembly_mod, "_build_segment", spy_build_segment)

    assembly_mod.assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = render_engine.load_render_state(pdir, pid)
    assert final_state.assembly_status == "done", final_state.assembly_error

    before_master = next(o for o in observed if o[0] == "before_master")
    before_chunk = next(o for o in observed if o[0] == "before_chunk")
    segment_calls = [o for o in observed if o[0] == "before_segment"]

    # Đúng lúc dựng master — stage phải LÀ "background_video" ngay từ đầu (0/2: 1 master +
    # 1 chunk cho shot B trống, KHÔNG có bước playlist vì chỉ 1 video), KHÔNG còn kẹt ở
    # "segments" như bug cũ.
    assert before_master[1] == "background_video"
    assert (before_master[2], before_master[3]) == (0, 2)
    # Sau khi master xong, TRƯỚC lúc cắt chunk — current đã tăng lên 1.
    assert before_chunk[1] == "background_video"
    assert (before_chunk[2], before_chunk[3]) == (1, 2)
    # Khi Pass 2 (segment thật) bắt đầu — stage đã chuyển hẳn sang "segments", VÀ
    # `stage_started_at` là mốc MỚI, KHÁC mốc bg stage (không gộp elapsed 2 bước lại,
    # tránh ETA segment bị thổi phồng vì tính luôn thời gian dựng video nền).
    assert segment_calls, "Pass 2 (_build_segment) phải được gọi ít nhất 1 lần"
    assert all(o[1] == "segments" for o in segment_calls)
    assert all(o[4] != before_master[4] for o in segment_calls)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_reports_playlist_stage_when_multiple_background_videos(client, project_with_brief, tmp_path, monkeypatch):
    """Case NHIỀU video (mới, mục 110) — thêm 1 bước "playlist" TRƯỚC "master", đơn vị
    tiến trình phải là `2 (playlist + master) + len(blank_indices)`, KHÁC case 1 video ở
    test phía trên (chỉ `1 + len(blank_indices)`)."""
    import app.render.assembly as assembly_mod
    from app.config import project_dir
    from app.filestore import write_json
    from app.render import engine as render_engine
    from app.render.schemas import BackgroundVideoOverride, RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:01", "Image", "Canh trong", "", "Loi thoai mot."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    narration = pdir / "assets" / f"{shot_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(narration)], capture_output=True, check=True, text=True)
    green = _solid_color_clip(ffmpeg, "green", tmp_path / "green.mp4", duration=1.0)
    yellow = _solid_color_clip(ffmpeg, "yellow", tmp_path / "yellow.mp4", duration=1.0)

    state = RenderState(
        project_id=pid,
        shots=[ShotRenderStatus(shot_id=shot_id, narration_status="ready", narration_asset_path=str(narration), narration_duration_sec=1.0)],
        background_video=BackgroundVideoOverride(asset_paths=[str(green), str(yellow)], transition="cut"),
    )
    write_json(pdir / "render.json", state.model_dump())

    observed: list[tuple] = []
    real_build_playlist = assembly_mod._build_background_video_playlist

    def spy_build_playlist(*args, **kwargs):
        s = render_engine.load_render_state(pdir, pid)
        observed.append((s.assembly_progress.stage, s.assembly_progress.current, s.assembly_progress.total))
        return real_build_playlist(*args, **kwargs)

    monkeypatch.setattr(assembly_mod, "_build_background_video_playlist", spy_build_playlist)

    assembly_mod.assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = render_engine.load_render_state(pdir, pid)
    assert final_state.assembly_status == "done", final_state.assembly_error
    assert len(observed) == 1
    stage, current, total = observed[0]
    assert stage == "background_video"
    assert (current, total) == (0, 3)  # 1 playlist + 1 master + 1 chunk (1 shot trống)


# ---------------------------------------------------------------------------
# Timeout ffmpeg — mới (2026-09-02, mục 111), theo yêu cầu người dùng ("cách nào để
# tránh lỗi tương tự") — `_build_background_video_master`/`_build_background_video_
# playlist` chạy 1 lệnh ffmpeg DUY NHẤT xử lý CẢ project, không có cách nào tự báo giữa
# chừng nếu treo THẬT (input hỏng/deadlock/máy quá tải) — thêm `timeout=` để biến 1 lần
# treo thật thành lỗi RÕ RÀNG (`assembly_status="error"`) thay vì kẹt "assembling" vô
# thời hạn (đúng lớp bug đã gặp, dù nguyên nhân lần đó khác — xem `engine.py::
# _assembly_in_progress`, mục 111).
# ---------------------------------------------------------------------------
def test_assemble_reports_clear_error_when_background_video_master_times_out(client, project_with_brief, tmp_path, monkeypatch):
    import subprocess as subprocess_mod

    import app.render.assembly as assembly_mod
    from app.config import project_dir
    from app.filestore import write_json
    from app.render import engine as render_engine
    from app.render.schemas import BackgroundVideoOverride, RenderState, ShotRenderStatus

    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:01", "Image", "Canh trong", "", "Loi thoai mot."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    state = RenderState(
        project_id=pid,
        shots=[ShotRenderStatus(shot_id=shot_id, narration_status="ready", narration_asset_path=str(tmp_path / "fake.wav"), narration_duration_sec=1.0)],
        background_video=BackgroundVideoOverride(asset_paths=[str(tmp_path / "fake_bg.mp4")]),
    )
    write_json(pdir / "render.json", state.model_dump())

    def _boom(*args, **kwargs):
        raise subprocess_mod.TimeoutExpired(cmd="ffmpeg", timeout=7200)

    monkeypatch.setattr(assembly_mod.subprocess, "run", _boom)

    assert not render_engine.is_assembly_in_progress(pid)
    assembly_mod.assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = render_engine.load_render_state(pdir, pid)
    assert final_state.assembly_status == "error"
    assert "quá lâu" in final_state.assembly_error.lower() or "timeout" in final_state.assembly_error.lower()
    assert not render_engine.is_assembly_in_progress(pid)  # LUÔN dọn cờ, kể cả nhánh timeout
