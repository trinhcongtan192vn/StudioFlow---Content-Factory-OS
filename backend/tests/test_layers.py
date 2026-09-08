"""Layer video ĐỊNH VỊ theo lưới 3x3 (VD voice wave, logo) — 2026-09-02, mục 112, theo
yêu cầu người dùng: "thêm layer voice wave (dạng video loop) vào bên trên video nền",
chia khung hình thành 9 phần và chọn vị trí đặt layer. 2 chế độ blend (mục 113): `"alpha"`
(mặc định) — nguồn CÓ SẴN kênh alpha (WebM VP9/MOV ProRes4444 trong suốt), composite bằng
filter `overlay` thẳng; `"screen"` — nguồn NỀN ĐEN ĐẶC (không alpha, theo yêu cầu người
dùng: "tôi chỉ có video layer nền đen thôi, hãy process nền đen"), screen-blend CỤC BỘ
đúng vùng layer (khác `OverlayEffectOverride` — hàm đó screen-blend TOÀN khung hình). Xem
`app/render/schemas.py::VideoLayer`, `app/render/assembly.py::_composite_layers`.
"""
import io
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20


# ---------------------------------------------------------------------------
# Endpoint CRUD — mirror test_background_video.py
# ---------------------------------------------------------------------------
def test_upload_project_layer_appends_to_list_with_defaults(client, project):
    pid = project["id"]
    resp = client.post(
        f"/projects/{pid}/render/layers/upload",
        files={"file": ("wave.webm", io.BytesIO(FAKE_MP4), "video/webm")},
    )
    assert resp.status_code == 200, resp.text
    layers = resp.json()["layers"]
    assert len(layers) == 1
    assert layers[0]["position"] == "bottom-center"
    assert layers[0]["width_pct"] == pytest.approx(0.3)
    assert layers[0]["opacity"] == pytest.approx(1.0)
    assert layers[0]["id"]
    assert layers[0]["asset_path"]


def test_upload_project_layer_accepts_custom_position_size_opacity(client, project):
    pid = project["id"]
    resp = client.post(
        f"/projects/{pid}/render/layers/upload",
        files={"file": ("wave.webm", io.BytesIO(FAKE_MP4), "video/webm")},
        data={"position": "top-left", "width_pct": "0.5", "opacity": "0.7"},
    )
    assert resp.status_code == 200, resp.text
    layer = resp.json()["layers"][0]
    assert layer["position"] == "top-left"
    assert layer["width_pct"] == pytest.approx(0.5)
    assert layer["opacity"] == pytest.approx(0.7)


def test_upload_project_layer_defaults_blend_mode_to_alpha(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")})
    assert resp.json()["layers"][0]["blend_mode"] == "alpha"


def test_upload_project_layer_accepts_screen_blend_mode(client, project):
    pid = project["id"]
    resp = client.post(
        f"/projects/{pid}/render/layers/upload",
        files={"file": ("wave.mp4", io.BytesIO(FAKE_MP4), "video/mp4")},
        data={"blend_mode": "screen"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["layers"][0]["blend_mode"] == "screen"


def test_upload_project_layer_rejects_invalid_blend_mode(client, project):
    resp = client.post(
        f"/projects/{project['id']}/render/layers/upload",
        files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")},
        data={"blend_mode": "multiply"},
    )
    assert resp.status_code == 400


def test_patch_project_layer_can_switch_blend_mode(client, project):
    pid = project["id"]
    layer_id = client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")}).json()["layers"][0]["id"]
    resp = client.patch(f"/projects/{pid}/render/layers/{layer_id}", json={"blend_mode": "screen"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["layers"][0]["blend_mode"] == "screen"


def test_upload_project_layer_second_call_appends_not_replaces(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")})
    resp = client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("b.webm", io.BytesIO(FAKE_MP4), "video/webm")})
    layers = resp.json()["layers"]
    assert len(layers) == 2
    assert layers[0]["id"] != layers[1]["id"]
    assert layers[0]["asset_path"] != layers[1]["asset_path"]


def test_upload_project_layer_rejects_unknown_file_type(client, project):
    resp = client.post(f"/projects/{project['id']}/render/layers/upload", files={"file": ("a.txt", io.BytesIO(b"khong phai video"), "text/plain")})
    assert resp.status_code == 400


@pytest.mark.parametrize("field,value", [("position", "invalid-spot"), ("width_pct", "0.01"), ("width_pct", "1.5"), ("opacity", "-0.1"), ("opacity", "1.1")])
def test_upload_project_layer_rejects_invalid_fields(client, project, field, value):
    resp = client.post(
        f"/projects/{project['id']}/render/layers/upload",
        files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")},
        data={field: value},
    )
    assert resp.status_code == 400


def test_patch_project_layer_updates_only_given_fields(client, project):
    pid = project["id"]
    layer_id = client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")}).json()["layers"][0]["id"]

    resp = client.patch(f"/projects/{pid}/render/layers/{layer_id}", json={"position": "top-right"})
    assert resp.status_code == 200, resp.text
    layer = resp.json()["layers"][0]
    assert layer["position"] == "top-right"
    assert layer["width_pct"] == pytest.approx(0.3)  # không đổi, không gửi field này

    resp2 = client.patch(f"/projects/{pid}/render/layers/{layer_id}", json={"width_pct": 0.6, "opacity": 0.4})
    layer2 = resp2.json()["layers"][0]
    assert layer2["position"] == "top-right"  # vẫn giữ lần đổi trước
    assert layer2["width_pct"] == pytest.approx(0.6)
    assert layer2["opacity"] == pytest.approx(0.4)


def test_patch_project_layer_404_unknown_id(client, project):
    resp = client.patch(f"/projects/{project['id']}/render/layers/khong-ton-tai", json={"position": "center"})
    assert resp.status_code == 404


def test_patch_project_layer_rejects_invalid_values(client, project):
    pid = project["id"]
    layer_id = client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")}).json()["layers"][0]["id"]
    resp = client.patch(f"/projects/{pid}/render/layers/{layer_id}", json={"position": "nowhere"})
    assert resp.status_code == 400


def test_delete_project_layer_removes_only_that_layer(client, project):
    pid = project["id"]
    id_a = client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")}).json()["layers"][0]["id"]
    resp = client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("b.webm", io.BytesIO(FAKE_MP4), "video/webm")})
    id_b = resp.json()["layers"][1]["id"]
    path_a = resp.json()["layers"][0]["asset_path"]
    assert Path(path_a).exists()

    resp = client.delete(f"/projects/{pid}/render/layers/{id_a}")
    assert resp.status_code == 200, resp.text
    remaining_ids = [layer["id"] for layer in resp.json()["layers"]]
    assert remaining_ids == [id_b]
    assert not Path(path_a).exists()


def test_delete_project_layer_404_unknown_id(client, project):
    resp = client.delete(f"/projects/{project['id']}/render/layers/khong-ton-tai")
    assert resp.status_code == 404


def test_get_project_layer_asset_serves_file(client, project):
    pid = project["id"]
    layer_id = client.post(f"/projects/{pid}/render/layers/upload", files={"file": ("a.webm", io.BytesIO(FAKE_MP4), "video/webm")}).json()["layers"][0]["id"]
    resp = client.get(f"/projects/{pid}/render/layers/{layer_id}/asset")
    assert resp.status_code == 200
    assert resp.content == FAKE_MP4


def test_get_project_layer_asset_404_unknown_id(client, project):
    resp = client.get(f"/projects/{project['id']}/render/layers/khong-ton-tai/asset")
    assert resp.status_code == 404


def test_layers_default_empty_list(client, project):
    status = client.get(f"/projects/{project['id']}/render/status").json()
    assert status["layers"] == []


# ---------------------------------------------------------------------------
# `_composite_layers`/`_layer_position_expr` — ffmpeg thật
# ---------------------------------------------------------------------------
def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return float(out.stdout.strip())


def _pixel_color(ffmpeg: str, video_path: Path, x_frac: float, y_frac: float, t: float, tmp_path: Path, name: str) -> tuple[int, int, int]:
    """Lấy màu trung bình 1 VÙNG NHỎ (không phải 1 điểm ảnh đơn) quanh toạ độ tương đối
    (x_frac, y_frac) trong khung hình — bền hơn trước nhiễu nén H.264 ở rìa vùng."""
    frame_path = tmp_path / name
    subprocess.run([ffmpeg, "-y", "-ss", str(t), "-i", str(video_path), "-frames:v", "1", "-update", "1", str(frame_path)], capture_output=True, check=True, text=True)
    img = Image.open(frame_path).convert("RGB")
    w, h = img.size
    cx, cy = int(w * x_frac), int(h * y_frac)
    box = img.crop((max(0, cx - 5), max(0, cy - 5), min(w, cx + 5), min(h, cy + 5)))
    pixels = list(box.getdata())
    n = len(pixels)
    return (sum(p[0] for p in pixels) // n, sum(p[1] for p in pixels) // n, sum(p[2] for p in pixels) // n)


def _solid_opaque_clip(ffmpeg: str, color: str, out_path: Path, size: str = "200x200", duration: float = 2.0) -> Path:
    """Clip màu thuần CÓ SẴN kênh alpha (opaque hoàn toàn, giả lập đúng loại nguồn tính
    năng này yêu cầu — WebM VP9/MOV alpha thật) — dùng webm/vp9 (yuva420p hỗ trợ alpha)."""
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={duration}", "-vf", "format=yuva420p", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", str(out_path)],
        capture_output=True, check=True, text=True,
    )
    return out_path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_layers_positions_layer_at_chosen_grid_cell(tmp_path):
    from app.render.assembly import _composite_layers
    from app.render.schemas import VideoLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    layer_src = _solid_opaque_clip(ffmpeg, "red", tmp_path / "layer.webm", size="120x120", duration=1.0)

    out = tmp_path / "composited.mp4"
    layer = VideoLayer(id="l1", asset_path=str(layer_src), position="top-left", width_pct=0.3, opacity=1.0)
    _composite_layers(ffmpeg, bg, [layer], out, resolution="640:360", video_codec="libx264", crf=28)

    r0, g0, b0 = _pixel_color(ffmpeg, out, 0.05, 0.05, 0.5, tmp_path, "topleft.png")
    assert r0 > 150 and g0 < 80 and b0 < 80, f"Góc trên-trái phải là ĐỎ (layer) — ra {(r0, g0, b0)}"

    r1, g1, b1 = _pixel_color(ffmpeg, out, 0.9, 0.9, 0.5, tmp_path, "bottomright.png")
    assert g1 > 100 and r1 < 30 and b1 < 30, f"Góc dưới-phải phải là XANH LÁ (nền, không bị layer che) — ra {(r1, g1, b1)}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_layers_applies_opacity_via_alpha(tmp_path):
    from app.render.assembly import _composite_layers
    from app.render.schemas import VideoLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    layer_src = _solid_opaque_clip(ffmpeg, "red", tmp_path / "layer.webm", size="300x300", duration=1.0)

    out_full = tmp_path / "full.mp4"
    _composite_layers(ffmpeg, bg, [VideoLayer(id="l1", asset_path=str(layer_src), position="center", width_pct=0.5, opacity=1.0)], out_full, resolution="640:360", video_codec="libx264", crf=28)
    r_full, g_full, b_full = _pixel_color(ffmpeg, out_full, 0.5, 0.5, 0.5, tmp_path, "full.png")
    assert r_full > 150 and b_full < 80, f"opacity=1.0 phải gần như ĐỎ THUẦN ở tâm — ra {(r_full, g_full, b_full)}"

    out_half = tmp_path / "half.mp4"
    _composite_layers(ffmpeg, bg, [VideoLayer(id="l1", asset_path=str(layer_src), position="center", width_pct=0.5, opacity=0.5)], out_half, resolution="640:360", video_codec="libx264", crf=28)
    r_half, g_half, b_half = _pixel_color(ffmpeg, out_half, 0.5, 0.5, 0.5, tmp_path, "half.png")
    # over-operator: result = fg*alpha + bg*(1-alpha) — đỏ(255,0,0)*0.5 + xanh dương(0,0,255)*0.5 ≈ (127,0,127)
    assert 90 < r_half < 170 and 90 < b_half < 170, f"opacity=0.5 phải là pha trộn đỏ/xanh dương — ra {(r_half, g_half, b_half)}"
    assert r_half < r_full - 40, "opacity=0.5 phải nhạt màu đỏ RÕ RỆT hơn opacity=1.0"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_layers_supports_multiple_layers_simultaneously(tmp_path):
    from app.render.assembly import _composite_layers
    from app.render.schemas import VideoLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    red = _solid_opaque_clip(ffmpeg, "red", tmp_path / "red.webm", size="120x120", duration=1.0)
    yellow = _solid_opaque_clip(ffmpeg, "yellow", tmp_path / "yellow.webm", size="120x120", duration=1.0)

    out = tmp_path / "composited.mp4"
    layers = [
        VideoLayer(id="l1", asset_path=str(red), position="top-left", width_pct=0.3, opacity=1.0),
        VideoLayer(id="l2", asset_path=str(yellow), position="bottom-right", width_pct=0.3, opacity=1.0),
    ]
    _composite_layers(ffmpeg, bg, layers, out, resolution="640:360", video_codec="libx264", crf=28)

    r0, g0, b0 = _pixel_color(ffmpeg, out, 0.05, 0.05, 0.5, tmp_path, "tl.png")
    assert r0 > 150 and g0 < 80 and b0 < 80, f"Layer 1 (đỏ, top-left) — ra {(r0, g0, b0)}"

    r1, g1, b1 = _pixel_color(ffmpeg, out, 0.9, 0.9, 0.5, tmp_path, "br.png")
    assert r1 > 150 and g1 > 150 and b1 < 80, f"Layer 2 (vàng, bottom-right) — ra {(r1, g1, b1)}"

    r2, g2, b2 = _pixel_color(ffmpeg, out, 0.5, 0.5, 0.5, tmp_path, "center.png")
    assert r2 < 40 and g2 < 40 and b2 < 40, f"Giữa khung hình phải vẫn ĐEN (nền, không layer nào che) — ra {(r2, g2, b2)}"


# ---------------------------------------------------------------------------
# `blend_mode="screen"` (mới, mục 113) — theo yêu cầu người dùng: "tôi chỉ có video
# layer nền đen thôi, hãy process nền đen". KHÁC `blend_mode="alpha"` — clip nguồn NỀN
# ĐEN ĐẶC (không alpha), screen-blend CỤC BỘ đúng vùng layer (không phải toàn khung hình
# như overlay hiệu ứng lớp phủ).
# ---------------------------------------------------------------------------
def _solid_color_clip_no_alpha(ffmpeg: str, color: str, out_path: Path, size: str = "200x200", duration: float = 1.0) -> Path:
    """Clip màu thuần KHÔNG alpha (yuv420p thường) — giả lập ĐÚNG loại nguồn "nền đen
    đặc" mà chế độ `screen` xử lý (khác `_solid_opaque_clip` — clip webm/vp9 CÓ alpha,
    dùng cho chế độ `alpha`)."""
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={duration}", "-pix_fmt", "yuv420p", str(out_path)],
        capture_output=True, check=True, text=True,
    )
    return out_path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_layers_screen_mode_makes_black_background_disappear(tmp_path):
    """Layer NGUYÊN 1 màu ĐEN (không hoạ tiết gì, mô phỏng phần nền đen của 1 clip hiệu
    ứng thật) — screen-blend phải làm nền đen "biến mất" HOÀN TOÀN, chỉ còn thấy màu nền
    gốc trong đúng vùng layer (không phải màu đen của layer)."""
    from app.render.assembly import _composite_layers
    from app.render.schemas import VideoLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    black_layer = _solid_color_clip_no_alpha(ffmpeg, "black", tmp_path / "black.mp4", size="200x200", duration=1.0)

    out = tmp_path / "composited.mp4"
    layer = VideoLayer(id="l1", asset_path=str(black_layer), position="center", width_pct=0.5, opacity=1.0, blend_mode="screen")
    _composite_layers(ffmpeg, bg, [layer], out, resolution="640:360", video_codec="libx264", crf=28)

    r, g, b = _pixel_color(ffmpeg, out, 0.5, 0.5, 0.5, tmp_path, "center.png")
    assert g > 100 and r < 30 and b < 30, f"Tâm khung hình (trong vùng layer đen) phải vẫn XANH LÁ (nền đen đã biến mất) — ra {(r, g, b)}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_layers_screen_mode_shows_bright_content_and_stays_positioned(tmp_path):
    """Layer TRẮNG (sáng nhất có thể) — screen-blend phải hiện RÕ (screen với trắng luôn
    ra trắng bất kể nền). Đồng thời xác nhận vùng NGOÀI layer giữ nguyên màu nền — kỹ
    thuật crop+blend+overlay không làm lem ra ngoài vùng đã định vị."""
    from app.render.assembly import _composite_layers
    from app.render.schemas import VideoLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    white_layer = _solid_color_clip_no_alpha(ffmpeg, "white", tmp_path / "white.mp4", size="150x150", duration=1.0)

    out = tmp_path / "composited.mp4"
    layer = VideoLayer(id="l1", asset_path=str(white_layer), position="top-left", width_pct=0.3, opacity=1.0, blend_mode="screen")
    _composite_layers(ffmpeg, bg, [layer], out, resolution="640:360", video_codec="libx264", crf=28)

    r0, g0, b0 = _pixel_color(ffmpeg, out, 0.05, 0.05, 0.5, tmp_path, "topleft.png")
    assert r0 > 220 and g0 > 220 and b0 > 220, f"Góc trên-trái (vùng layer trắng) phải gần TRẮNG THUẦN — ra {(r0, g0, b0)}"

    r1, g1, b1 = _pixel_color(ffmpeg, out, 0.9, 0.9, 0.5, tmp_path, "bottomright.png")
    assert g1 > 100 and r1 < 30 and b1 < 30, f"Góc dưới-phải (ngoài vùng layer) phải vẫn XANH LÁ (nền, không bị lem) — ra {(r1, g1, b1)}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_layers_screen_mode_opacity_dims_effect(tmp_path):
    from app.render.assembly import _composite_layers
    from app.render.schemas import VideoLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    white_layer = _solid_color_clip_no_alpha(ffmpeg, "white", tmp_path / "white.mp4", size="300x300", duration=1.0)

    out_full = tmp_path / "full.mp4"
    _composite_layers(ffmpeg, bg, [VideoLayer(id="l1", asset_path=str(white_layer), position="center", width_pct=0.5, opacity=1.0, blend_mode="screen")], out_full, resolution="640:360", video_codec="libx264", crf=28)
    _, g_full, _ = _pixel_color(ffmpeg, out_full, 0.5, 0.5, 0.5, tmp_path, "full.png")

    out_dim = tmp_path / "dim.mp4"
    _composite_layers(ffmpeg, bg, [VideoLayer(id="l1", asset_path=str(white_layer), position="center", width_pct=0.5, opacity=0.3, blend_mode="screen")], out_dim, resolution="640:360", video_codec="libx264", crf=28)
    _, g_dim, _ = _pixel_color(ffmpeg, out_dim, 0.5, 0.5, 0.5, tmp_path, "dim.png")

    assert g_full > 220, f"opacity=1.0 (trắng full trên nền đen) phải gần trắng thuần — ra kênh xanh lá {g_full}"
    assert g_dim < g_full - 60, f"opacity=0.3 phải NHẠT hơn RÕ RỆT — full={g_full}, dim={g_dim}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_layers_noop_when_list_empty_is_caller_responsibility():
    """`_composite_layers` không tự kiểm `layers` rỗng — caller (`assemble_video`) chịu
    trách nhiệm chỉ gọi khi `state.layers` không rỗng (xem `if state.layers:` trong
    `_assemble_video_impl`) — test này xác nhận ĐÚNG hành vi caller, không phải hàm."""
    import app.render.assembly as assembly_mod
    import inspect

    src = inspect.getsource(assembly_mod._assemble_video_impl)
    assert "if state.layers:" in src


# ---------------------------------------------------------------------------
# Tích hợp qua `assemble_video()` — ffmpeg thật, project nhỏ
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_video_composites_layer_onto_final_output(client, project_with_brief, tmp_path):
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus, VideoLayer

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:02", "Image", "Canh test", "", "Loi thoai ngan."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    narration = pdir / "assets" / f"{shot_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(narration)], capture_output=True, check=True, text=True)

    layer_src = pdir / "assets" / "layer_test.webm"
    _solid_opaque_clip(ffmpeg, "red", layer_src, size="100x100", duration=1.0)

    state = RenderState(
        project_id=pid,
        shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True, narration_status="ready", narration_asset_path=str(narration), narration_duration_sec=2.0)],
        layers=[VideoLayer(id="l1", asset_path=str(layer_src), position="top-right", width_pct=0.3, opacity=1.0)],
    )
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    r, g, b = _pixel_color(ffmpeg, final_path, 0.9, 0.05, 1.0, tmp_path, "layer_check.png")
    assert r > 150 and g < 80 and b < 80, f"Góc trên-phải (layer đỏ) phải nổi trên nền xanh lá của shot — ra {(r, g, b)}"
