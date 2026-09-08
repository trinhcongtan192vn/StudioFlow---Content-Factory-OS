"""Layer ẢNH ĐỊNH VỊ (khác layer VIDEO — test_layers.py) — 2026-09-02, mục 115, theo yêu
cầu người dùng: "bổ sung thêm block... setup Layer ảnh định vị với chức năng tương tự
[layer video] nhưng cho ảnh nền đen hoặc không có nền. Ngoài hỗ trợ 9 vị trí layer thì
còn hỗ trợ thêm full khung hình". Song song `test_layers.py` — cùng 2 chế độ blend
(`"alpha"`/`"screen"`), CHỈ khác: nguồn LUÔN ảnh tĩnh (PNG/JPEG/WEBP, `-loop 1` thay
`-stream_loop -1`), và `position` có thêm `"full"` (phủ toàn khung hình). Xem
`app/render/schemas.py::ImageLayer`, `app/render/assembly.py::_composite_image_layers`.
"""
import io
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def _solid_png(color: tuple, out_path: Path, size=(200, 200), alpha: int | None = 255) -> Path:
    """Ảnh PNG màu thuần — `alpha=None` tạo ảnh RGB KHÔNG có kênh alpha (giả lập ĐÚNG
    "ảnh nền đen hoặc không có nền" người dùng mô tả, dùng cho test chế độ `screen`);
    `alpha=255` tạo RGBA opaque hoàn toàn (dùng cho test chế độ `alpha`)."""
    if alpha is None:
        img = Image.new("RGB", size, color)
    else:
        img = Image.new("RGBA", size, (*color, alpha))
    img.save(out_path)
    return out_path


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return float(out.stdout.strip())


def _pixel_color(ffmpeg: str, video_path: Path, x_frac: float, y_frac: float, t: float, tmp_path: Path, name: str) -> tuple[int, int, int]:
    frame_path = tmp_path / name
    subprocess.run([ffmpeg, "-y", "-ss", str(t), "-i", str(video_path), "-frames:v", "1", "-update", "1", str(frame_path)], capture_output=True, check=True, text=True)
    img = Image.open(frame_path).convert("RGB")
    w, h = img.size
    cx, cy = int(w * x_frac), int(h * y_frac)
    box = img.crop((max(0, cx - 5), max(0, cy - 5), min(w, cx + 5), min(h, cy + 5)))
    pixels = list(box.getdata())
    n = len(pixels)
    return (sum(p[0] for p in pixels) // n, sum(p[1] for p in pixels) // n, sum(p[2] for p in pixels) // n)


# ---------------------------------------------------------------------------
# Endpoint CRUD — mirror test_layers.py
# ---------------------------------------------------------------------------
def test_upload_project_image_layer_appends_to_list_with_defaults(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/image-layers/upload", files={"file": ("wm.png", io.BytesIO(FAKE_PNG), "image/png")})
    assert resp.status_code == 200, resp.text
    layers = resp.json()["image_layers"]
    assert len(layers) == 1
    assert layers[0]["position"] == "bottom-center"
    assert layers[0]["width_pct"] == pytest.approx(0.3)
    assert layers[0]["opacity"] == pytest.approx(1.0)
    assert layers[0]["blend_mode"] == "alpha"
    assert layers[0]["id"]
    assert layers[0]["asset_path"]


def test_upload_project_image_layer_accepts_full_position(client, project):
    pid = project["id"]
    resp = client.post(
        f"/projects/{pid}/render/image-layers/upload",
        files={"file": ("wm.png", io.BytesIO(FAKE_PNG), "image/png")},
        data={"position": "full", "blend_mode": "screen"},
    )
    assert resp.status_code == 200, resp.text
    layer = resp.json()["image_layers"][0]
    assert layer["position"] == "full"
    assert layer["blend_mode"] == "screen"


def test_upload_project_image_layer_accepts_custom_fields(client, project):
    pid = project["id"]
    resp = client.post(
        f"/projects/{pid}/render/image-layers/upload",
        files={"file": ("wm.jpg", io.BytesIO(FAKE_PNG), "image/jpeg")},
        data={"position": "top-left", "width_pct": "0.5", "opacity": "0.7", "blend_mode": "screen"},
    )
    assert resp.status_code == 200, resp.text
    layer = resp.json()["image_layers"][0]
    assert layer["position"] == "top-left"
    assert layer["width_pct"] == pytest.approx(0.5)
    assert layer["opacity"] == pytest.approx(0.7)
    assert layer["blend_mode"] == "screen"


def test_upload_project_image_layer_second_call_appends_not_replaces(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/image-layers/upload", files={"file": ("a.png", io.BytesIO(FAKE_PNG), "image/png")})
    resp = client.post(f"/projects/{pid}/render/image-layers/upload", files={"file": ("b.png", io.BytesIO(FAKE_PNG), "image/png")})
    layers = resp.json()["image_layers"]
    assert len(layers) == 2
    assert layers[0]["id"] != layers[1]["id"]
    assert layers[0]["asset_path"] != layers[1]["asset_path"]


def test_upload_project_image_layer_rejects_unknown_file_type(client, project):
    resp = client.post(f"/projects/{project['id']}/render/image-layers/upload", files={"file": ("a.txt", io.BytesIO(b"khong phai anh"), "text/plain")})
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "field,value",
    [("position", "invalid-spot"), ("width_pct", "0.01"), ("width_pct", "1.5"), ("opacity", "-0.1"), ("opacity", "1.1"), ("blend_mode", "multiply")],
)
def test_upload_project_image_layer_rejects_invalid_fields(client, project, field, value):
    resp = client.post(
        f"/projects/{project['id']}/render/image-layers/upload",
        files={"file": ("a.png", io.BytesIO(FAKE_PNG), "image/png")},
        data={field: value},
    )
    assert resp.status_code == 400


def test_patch_project_image_layer_updates_only_given_fields(client, project):
    pid = project["id"]
    layer_id = client.post(f"/projects/{pid}/render/image-layers/upload", files={"file": ("a.png", io.BytesIO(FAKE_PNG), "image/png")}).json()["image_layers"][0]["id"]

    resp = client.patch(f"/projects/{pid}/render/image-layers/{layer_id}", json={"position": "full"})
    assert resp.status_code == 200, resp.text
    layer = resp.json()["image_layers"][0]
    assert layer["position"] == "full"
    assert layer["width_pct"] == pytest.approx(0.3)  # không đổi

    resp2 = client.patch(f"/projects/{pid}/render/image-layers/{layer_id}", json={"blend_mode": "screen", "opacity": 0.4})
    layer2 = resp2.json()["image_layers"][0]
    assert layer2["position"] == "full"  # vẫn giữ lần đổi trước
    assert layer2["blend_mode"] == "screen"
    assert layer2["opacity"] == pytest.approx(0.4)


def test_patch_project_image_layer_404_unknown_id(client, project):
    resp = client.patch(f"/projects/{project['id']}/render/image-layers/khong-ton-tai", json={"position": "center"})
    assert resp.status_code == 404


def test_patch_project_image_layer_rejects_invalid_values(client, project):
    pid = project["id"]
    layer_id = client.post(f"/projects/{pid}/render/image-layers/upload", files={"file": ("a.png", io.BytesIO(FAKE_PNG), "image/png")}).json()["image_layers"][0]["id"]
    resp = client.patch(f"/projects/{pid}/render/image-layers/{layer_id}", json={"position": "nowhere"})
    assert resp.status_code == 400


def test_delete_project_image_layer_removes_only_that_layer(client, project):
    pid = project["id"]
    id_a = client.post(f"/projects/{pid}/render/image-layers/upload", files={"file": ("a.png", io.BytesIO(FAKE_PNG), "image/png")}).json()["image_layers"][0]["id"]
    resp = client.post(f"/projects/{pid}/render/image-layers/upload", files={"file": ("b.png", io.BytesIO(FAKE_PNG), "image/png")})
    id_b = resp.json()["image_layers"][1]["id"]
    path_a = resp.json()["image_layers"][0]["asset_path"]
    assert Path(path_a).exists()

    resp = client.delete(f"/projects/{pid}/render/image-layers/{id_a}")
    assert resp.status_code == 200, resp.text
    remaining_ids = [layer["id"] for layer in resp.json()["image_layers"]]
    assert remaining_ids == [id_b]
    assert not Path(path_a).exists()


def test_delete_project_image_layer_404_unknown_id(client, project):
    resp = client.delete(f"/projects/{project['id']}/render/image-layers/khong-ton-tai")
    assert resp.status_code == 404


def test_get_project_image_layer_asset_serves_file(client, project):
    pid = project["id"]
    layer_id = client.post(f"/projects/{pid}/render/image-layers/upload", files={"file": ("a.png", io.BytesIO(FAKE_PNG), "image/png")}).json()["image_layers"][0]["id"]
    resp = client.get(f"/projects/{pid}/render/image-layers/{layer_id}/asset")
    assert resp.status_code == 200
    assert resp.content == FAKE_PNG


def test_get_project_image_layer_asset_404_unknown_id(client, project):
    resp = client.get(f"/projects/{project['id']}/render/image-layers/khong-ton-tai/asset")
    assert resp.status_code == 404


def test_image_layers_default_empty_list(client, project):
    status = client.get(f"/projects/{project['id']}/render/status").json()
    assert status["image_layers"] == []


# ---------------------------------------------------------------------------
# `_composite_image_layers` — ffmpeg thật
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_image_layers_positions_at_chosen_grid_cell_alpha_mode(tmp_path):
    from app.render.assembly import _composite_image_layers
    from app.render.schemas import ImageLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    red_png = _solid_png((255, 0, 0), tmp_path / "red.png", size=(120, 120), alpha=255)

    out = tmp_path / "composited.mp4"
    layer = ImageLayer(id="l1", asset_path=str(red_png), position="top-left", width_pct=0.3, opacity=1.0, blend_mode="alpha")
    _composite_image_layers(ffmpeg, bg, [layer], out, resolution="640:360", video_codec="libx264", crf=28)

    r0, g0, b0 = _pixel_color(ffmpeg, out, 0.05, 0.05, 0.5, tmp_path, "topleft.png")
    assert r0 > 150 and g0 < 80 and b0 < 80, f"Góc trên-trái phải là ĐỎ (layer) — ra {(r0, g0, b0)}"

    r1, g1, b1 = _pixel_color(ffmpeg, out, 0.9, 0.9, 0.5, tmp_path, "bottomright.png")
    assert g1 > 100 and r1 < 30 and b1 < 30, f"Góc dưới-phải phải vẫn XANH LÁ (nền) — ra {(r1, g1, b1)}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_image_layers_applies_opacity_via_alpha(tmp_path):
    from app.render.assembly import _composite_image_layers
    from app.render.schemas import ImageLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    red_png = _solid_png((255, 0, 0), tmp_path / "red.png", size=(300, 300), alpha=255)

    out_full = tmp_path / "full.mp4"
    _composite_image_layers(ffmpeg, bg, [ImageLayer(id="l1", asset_path=str(red_png), position="center", width_pct=0.5, opacity=1.0)], out_full, resolution="640:360", video_codec="libx264", crf=28)
    r_full, _, b_full = _pixel_color(ffmpeg, out_full, 0.5, 0.5, 0.5, tmp_path, "full.png")

    out_half = tmp_path / "half.mp4"
    _composite_image_layers(ffmpeg, bg, [ImageLayer(id="l1", asset_path=str(red_png), position="center", width_pct=0.5, opacity=0.5)], out_half, resolution="640:360", video_codec="libx264", crf=28)
    r_half, _, b_half = _pixel_color(ffmpeg, out_half, 0.5, 0.5, 0.5, tmp_path, "half.png")

    assert r_full > 150 and b_full < 80, f"opacity=1.0 phải gần như ĐỎ THUẦN — ra r={r_full} b={b_full}"
    assert r_half < r_full - 40, "opacity=0.5 phải nhạt màu đỏ RÕ RỆT hơn opacity=1.0"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_image_layers_supports_multiple_layers_simultaneously(tmp_path):
    from app.render.assembly import _composite_image_layers
    from app.render.schemas import ImageLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    red_png = _solid_png((255, 0, 0), tmp_path / "red.png", size=(120, 120), alpha=255)
    yellow_png = _solid_png((255, 255, 0), tmp_path / "yellow.png", size=(120, 120), alpha=255)

    out = tmp_path / "composited.mp4"
    layers = [
        ImageLayer(id="l1", asset_path=str(red_png), position="top-left", width_pct=0.3, opacity=1.0),
        ImageLayer(id="l2", asset_path=str(yellow_png), position="bottom-right", width_pct=0.3, opacity=1.0),
    ]
    _composite_image_layers(ffmpeg, bg, layers, out, resolution="640:360", video_codec="libx264", crf=28)

    r0, g0, b0 = _pixel_color(ffmpeg, out, 0.05, 0.05, 0.5, tmp_path, "tl.png")
    assert r0 > 150 and g0 < 80 and b0 < 80, f"Layer 1 (đỏ, top-left) — ra {(r0, g0, b0)}"

    r1, g1, b1 = _pixel_color(ffmpeg, out, 0.9, 0.9, 0.5, tmp_path, "br.png")
    assert r1 > 150 and g1 > 150 and b1 < 80, f"Layer 2 (vàng, bottom-right) — ra {(r1, g1, b1)}"

    r2, g2, b2 = _pixel_color(ffmpeg, out, 0.5, 0.5, 0.5, tmp_path, "center.png")
    assert r2 < 40 and g2 < 40 and b2 < 40, f"Giữa khung hình phải vẫn ĐEN (nền) — ra {(r2, g2, b2)}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_image_layers_full_position_covers_whole_frame_alpha_mode(tmp_path):
    """position="full" — mới, mục 115: ảnh phủ TOÀN khung hình thay vì 1 ô lưới — xác
    nhận CẢ 4 góc + tâm đều thấy layer (không chỉ 1 vùng nhỏ)."""
    from app.render.assembly import _composite_image_layers
    from app.render.schemas import ImageLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    red_png = _solid_png((255, 0, 0), tmp_path / "red.png", size=(640, 360), alpha=255)

    out = tmp_path / "composited.mp4"
    layer = ImageLayer(id="l1", asset_path=str(red_png), position="full", opacity=1.0, blend_mode="alpha")
    _composite_image_layers(ffmpeg, bg, [layer], out, resolution="640:360", video_codec="libx264", crf=28)

    for name, (xf, yf) in {"topleft": (0.05, 0.05), "bottomright": (0.95, 0.95), "center": (0.5, 0.5)}.items():
        r, g, b = _pixel_color(ffmpeg, out, xf, yf, 0.5, tmp_path, f"{name}.png")
        assert r > 150 and g < 80 and b < 80, f"{name} phải ĐỎ (layer phủ toàn khung hình) — ra {(r, g, b)}"


# ---------------------------------------------------------------------------
# `blend_mode="screen"` (ảnh nền đen/không nền)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_image_layers_screen_mode_makes_black_background_disappear(tmp_path):
    from app.render.assembly import _composite_image_layers
    from app.render.schemas import ImageLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    black_png = _solid_png((0, 0, 0), tmp_path / "black.png", size=(200, 200), alpha=None)  # KHÔNG alpha — đúng "ảnh không có nền"

    out = tmp_path / "composited.mp4"
    layer = ImageLayer(id="l1", asset_path=str(black_png), position="center", width_pct=0.5, opacity=1.0, blend_mode="screen")
    _composite_image_layers(ffmpeg, bg, [layer], out, resolution="640:360", video_codec="libx264", crf=28)

    r, g, b = _pixel_color(ffmpeg, out, 0.5, 0.5, 0.5, tmp_path, "center.png")
    assert g > 100 and r < 30 and b < 30, f"Tâm (vùng layer đen) phải vẫn XANH LÁ (nền đen đã biến mất) — ra {(r, g, b)}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_image_layers_screen_mode_shows_bright_content_and_stays_positioned(tmp_path):
    from app.render.assembly import _composite_image_layers
    from app.render.schemas import ImageLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    white_png = _solid_png((255, 255, 255), tmp_path / "white.png", size=(150, 150), alpha=None)

    out = tmp_path / "composited.mp4"
    layer = ImageLayer(id="l1", asset_path=str(white_png), position="top-left", width_pct=0.3, opacity=1.0, blend_mode="screen")
    _composite_image_layers(ffmpeg, bg, [layer], out, resolution="640:360", video_codec="libx264", crf=28)

    r0, g0, b0 = _pixel_color(ffmpeg, out, 0.05, 0.05, 0.5, tmp_path, "topleft.png")
    assert r0 > 220 and g0 > 220 and b0 > 220, f"Vùng layer trắng phải gần TRẮNG THUẦN — ra {(r0, g0, b0)}"

    r1, g1, b1 = _pixel_color(ffmpeg, out, 0.9, 0.9, 0.5, tmp_path, "bottomright.png")
    assert g1 > 100 and r1 < 30 and b1 < 30, f"Ngoài vùng layer phải vẫn XANH LÁ (không lem) — ra {(r1, g1, b1)}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_composite_image_layers_full_position_screen_mode_like_overlay_effect(tmp_path):
    """position="full" + blend_mode="screen" — bản chất chính là "hiệu ứng lớp phủ" áp
    dụng cho ảnh tĩnh thay vì video (không cần bước crop — vùng blend = toàn khung
    hình)."""
    from app.render.assembly import _composite_image_layers
    from app.render.schemas import ImageLayer

    ffmpeg = shutil.which("ffmpeg")
    bg = tmp_path / "bg.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1", "-pix_fmt", "yuv420p", str(bg)], capture_output=True, check=True, text=True)
    white_png = _solid_png((255, 255, 255), tmp_path / "white.png", size=(640, 360), alpha=None)

    out = tmp_path / "composited.mp4"
    layer = ImageLayer(id="l1", asset_path=str(white_png), position="full", opacity=0.5, blend_mode="screen")
    _composite_image_layers(ffmpeg, bg, [layer], out, resolution="640:360", video_codec="libx264", crf=28)

    r, g, b = _pixel_color(ffmpeg, out, 0.5, 0.5, 0.5, tmp_path, "center.png")
    # screen(nền đen, trắng*0.5 opacity) — nền đen "biến mất" hoàn toàn dù opacity nào,
    # nhưng opacity giảm SÁNG layer trước khi blend nên kết quả phải XÁM (không trắng tuyệt đối).
    assert 80 < r < 220 and 80 < g < 220 and 80 < b < 220, f"opacity=0.5 phủ toàn khung hình phải ra XÁM (không đen, không trắng tuyệt đối) — ra {(r, g, b)}"


# ---------------------------------------------------------------------------
# Tích hợp qua `assemble_video()` — ffmpeg thật, project nhỏ
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_video_composites_image_layer_onto_final_output(client, project_with_brief, tmp_path):
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import ImageLayer, RenderState, ShotRenderStatus

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

    layer_src = pdir / "assets" / "image_layer_test.png"
    _solid_png((255, 0, 0), layer_src, size=(100, 100), alpha=255)

    state = RenderState(
        project_id=pid,
        shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True, narration_status="ready", narration_asset_path=str(narration), narration_duration_sec=2.0)],
        image_layers=[ImageLayer(id="l1", asset_path=str(layer_src), position="top-right", width_pct=0.3, opacity=1.0)],
    )
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    r, g, b = _pixel_color(ffmpeg, final_path, 0.9, 0.05, 1.0, tmp_path, "layer_check.png")
    assert r > 150 and g < 80 and b < 80, f"Góc trên-phải (image layer đỏ) phải nổi trên nền xanh lá của shot — ra {(r, g, b)}"
