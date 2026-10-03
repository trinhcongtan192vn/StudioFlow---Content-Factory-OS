"""Layer CAPTION (phụ đề cứng burn-in) — mới (2026-09-12), theo yêu cầu người dùng: "Bổ
sung tính năng cho phép user thêm caption vào video ở bước visual studio... chọn 9 vị
trí, kích thước, độ mờ tương tự phần Layer video định vị", sau đó xác nhận thêm "chọn cả
loại ngôn ngữ nữa". Xem `app/render/schemas.py::CaptionLayer`,
`app/render/captions.py::write_shot_caption_ass`, `assembly.py::_build_segment` (tham số
`caption_ass_path`).

Test chia 3 nhóm: (1) đơn vị thuần cho `captions.py` (không cần ffmpeg); (2) router PATCH
`/render/caption-layer` (không cần ffmpeg thật); (3) burn-in THẬT qua `_build_segment`
(cần ffmpeg — `@pytest.mark.skipif`)."""
from __future__ import annotations

import shutil
import subprocess

import pytest


# ---------------------------------------------------------------------------
# `captions.py::write_shot_caption_ass` — thuần, không ffmpeg.
# ---------------------------------------------------------------------------
def test_write_shot_caption_ass_returns_false_for_empty_text(tmp_path):
    from app.render.captions import write_shot_caption_ass

    path = tmp_path / "cap.ass"
    ok = write_shot_caption_ass(path, "   ", 5.0, position="bottom-center", size_pct=0.045, opacity=1.0, out_w=1080, out_h=1920)
    assert ok is False
    assert not path.exists()


def test_write_shot_caption_ass_writes_playres_matching_output_resolution(tmp_path):
    from app.render.captions import write_shot_caption_ass

    path = tmp_path / "cap.ass"
    assert write_shot_caption_ass(path, "Xin chao the gioi.", 4.0, position="bottom-center", size_pct=0.045, opacity=1.0, out_w=1080, out_h=1920)
    content = path.read_text(encoding="utf-8")
    # PlayResX/Y PHẢI khớp ĐÚNG khung hình xuất — bug thật đã sửa (trước đây dùng
    # `force_style` + `.srt` thuần, libass tự chọn PlayRes mặc định làm Fontsize sai
    # lệch hẳn, xem docstring hàm). Tự viết .ass mới đảm bảo khớp trực tiếp.
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "Xin chao the gioi." in content
    assert "0:00:00.00,0:00:04.00" in content  # timestamp cục bộ [0, 4.0)


def test_write_shot_caption_ass_maps_all_9_positions_to_correct_alignment():
    from app.render.captions import LAYER_POSITION_TO_ASS_ALIGNMENT

    assert LAYER_POSITION_TO_ASS_ALIGNMENT == {
        "bottom-left": 1, "bottom-center": 2, "bottom-right": 3,
        "middle-left": 4, "center": 5, "middle-right": 6,
        "top-left": 7, "top-center": 8, "top-right": 9,
    }


def test_write_shot_caption_ass_fontsize_from_size_pct_and_out_h(tmp_path):
    from app.render.captions import write_shot_caption_ass

    path = tmp_path / "cap.ass"
    write_shot_caption_ass(path, "Xin chao.", 2.0, position="bottom-center", size_pct=0.05, opacity=1.0, out_w=1080, out_h=1000)
    content = path.read_text(encoding="utf-8")
    # Style line: "...,{fontsize},..." — 0.05 * 1000 = 50.
    assert ",50," in content


def test_write_shot_caption_ass_opacity_maps_to_ass_alpha_inverted(tmp_path):
    from app.render.captions import write_shot_caption_ass

    # opacity=1.0 (đục hoàn toàn) → alpha=00 (ASS: 00=đục, FF=trong suốt — NGƯỢC trực giác).
    opaque_path = tmp_path / "opaque.ass"
    write_shot_caption_ass(opaque_path, "Xin chao.", 2.0, position="bottom-center", size_pct=0.045, opacity=1.0, out_w=1080, out_h=1920)
    assert "&H00FFFFFF" in opaque_path.read_text(encoding="utf-8")
    # opacity=0.0 (trong suốt hoàn toàn) → alpha=FF.
    transparent_path = tmp_path / "transparent.ass"
    write_shot_caption_ass(transparent_path, "Xin chao.", 2.0, position="bottom-center", size_pct=0.045, opacity=0.0, out_w=1080, out_h=1920)
    assert "&HFFFFFFFF" in transparent_path.read_text(encoding="utf-8")


def test_write_shot_caption_ass_splits_long_text_into_multiple_dialogue_lines(tmp_path):
    from app.render.captions import write_shot_caption_ass

    long_text = "Cau mot khong ngan chut nao. Cau hai cung dai khong kem gi ca. Cau ba lai cang dai hon nua day."
    path = tmp_path / "cap.ass"
    write_shot_caption_ass(path, long_text, 15.0, position="bottom-center", size_pct=0.045, opacity=1.0, out_w=1080, out_h=1920, max_chars=40)
    content = path.read_text(encoding="utf-8")
    assert content.count("Dialogue:") > 1, "Text dài hơn max_chars phải tách nhiều dòng Dialogue"


# ---------------------------------------------------------------------------
# Router — PATCH /projects/{id}/render/caption-layer (không cần ffmpeg thật).
# ---------------------------------------------------------------------------
def test_patch_caption_layer_creates_with_defaults_then_applies_given_field(client, project):
    pid = project["id"]
    resp = client.patch(f"/projects/{pid}/render/caption-layer", json={"enabled": True})
    assert resp.status_code == 200, resp.text
    layer = resp.json()["caption_layer"]
    assert layer["enabled"] is True
    assert layer["position"] == "bottom-center"
    assert layer["size_pct"] == pytest.approx(0.045)
    assert layer["opacity"] == pytest.approx(1.0)
    assert layer["lang"] is None


def test_patch_caption_layer_updates_only_given_fields(client, project):
    pid = project["id"]
    client.patch(f"/projects/{pid}/render/caption-layer", json={"enabled": True, "position": "top-left"})
    resp = client.patch(f"/projects/{pid}/render/caption-layer", json={"opacity": 0.6})
    layer = resp.json()["caption_layer"]
    assert layer["position"] == "top-left"  # vẫn giữ lần đổi trước
    assert layer["opacity"] == pytest.approx(0.6)


def test_patch_caption_layer_lang_roundtrip(client, project):
    pid = project["id"]
    resp = client.patch(f"/projects/{pid}/render/caption-layer", json={"lang": "de"})
    assert resp.json()["caption_layer"]["lang"] == "de"
    # Gửi lại chuỗi rỗng — nghĩa là "theo ngôn ngữ đang ghép" (auto), quy về null.
    resp2 = client.patch(f"/projects/{pid}/render/caption-layer", json={"lang": ""})
    assert resp2.json()["caption_layer"]["lang"] is None


def test_patch_caption_layer_rejects_invalid_position(client, project):
    resp = client.patch(f"/projects/{project['id']}/render/caption-layer", json={"position": "nowhere"})
    assert resp.status_code == 400


def test_patch_caption_layer_rejects_invalid_lang(client, project):
    resp = client.patch(f"/projects/{project['id']}/render/caption-layer", json={"lang": "klingon"})
    assert resp.status_code == 400


@pytest.mark.parametrize("field,value", [("size_pct", 0.0), ("size_pct", 0.5), ("opacity", -0.1), ("opacity", 1.1)])
def test_patch_caption_layer_rejects_out_of_range_values(client, project, field, value):
    resp = client.patch(f"/projects/{project['id']}/render/caption-layer", json={field: value})
    assert resp.status_code == 400


def test_patch_caption_layer_404_unknown_project(client):
    resp = client.patch("/projects/khong-ton-tai/render/caption-layer", json={"enabled": True})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Burn-in THẬT qua `_build_segment` — cần ffmpeg thật trên PATH.
# ---------------------------------------------------------------------------
def _extract_frame(ffmpeg: str, video_path, out_path) -> None:
    subprocess.run([ffmpeg, "-y", "-i", str(video_path), "-frames:v", "1", str(out_path)], capture_output=True, check=True, text=True)


def _non_background_pixel_count(ffmpeg: str, frame_path, y: int, h: int, bg_rgb: tuple[int, int, int], tol: int = 40) -> int:
    """Đếm pixel LỆCH màu nền quá `tol` trong dải `[y, y+h)` — dùng làm proxy đo "có chữ
    hay không" (chữ trắng + viền đen trên nền màu đặc sẽ tạo pixel khác hẳn màu nền)."""
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(frame_path), "-vf", f"crop=iw:{h}:0:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    data = result.stdout
    count = 0
    for i in range(0, len(data) - 2, 3):
        if abs(data[i] - bg_rgb[0]) > tol or abs(data[i + 1] - bg_rgb[1]) > tol or abs(data[i + 2] - bg_rgb[2]) > tol:
            count += 1
    return count


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_segment_burns_caption_at_bottom_center(tmp_path):
    from app.render.assembly import _build_segment
    from app.render.captions import write_shot_caption_ass

    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920", "-frames:v", "1", "-update", "1", str(src)], capture_output=True, check=True, text=True)

    ass_path = tmp_path / "cap.ass"
    assert write_shot_caption_ass(ass_path, "Day la mot doan caption test kha dai de dam bao xuong dong.", 3.0, position="bottom-center", size_pct=0.05, opacity=1.0, out_w=1080, out_h=1920)

    out_path = tmp_path / "out.mp4"
    _build_segment(
        ffmpeg, str(src), None, 3.0, out_path,
        resolution="1080:1920", video_codec="libx264", audio_codec="aac", crf=23,
        caption_ass_path=str(ass_path),
    )
    frame = tmp_path / "frame.png"
    _extract_frame(ffmpeg, out_path, frame)

    blue = (0, 0, 255)
    bottom_band = _non_background_pixel_count(ffmpeg, frame, 1700, 200, blue)
    top_band = _non_background_pixel_count(ffmpeg, frame, 50, 200, blue)
    assert bottom_band > 500, f"Vùng dưới phải có nhiều pixel caption (chữ trắng/viền đen) — đếm được {bottom_band}"
    assert bottom_band > top_band * 5, f"Caption 'bottom-center' phải tập trung ở dải DƯỚI, không phải trên — dưới={bottom_band}, trên={top_band}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_segment_burns_caption_at_top_center(tmp_path):
    from app.render.assembly import _build_segment
    from app.render.captions import write_shot_caption_ass

    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920", "-frames:v", "1", "-update", "1", str(src)], capture_output=True, check=True, text=True)

    ass_path = tmp_path / "cap.ass"
    write_shot_caption_ass(ass_path, "Day la mot doan caption test kha dai de dam bao xuong dong.", 3.0, position="top-center", size_pct=0.05, opacity=1.0, out_w=1080, out_h=1920)

    out_path = tmp_path / "out.mp4"
    _build_segment(
        ffmpeg, str(src), None, 3.0, out_path,
        resolution="1080:1920", video_codec="libx264", audio_codec="aac", crf=23,
        caption_ass_path=str(ass_path),
    )
    frame = tmp_path / "frame.png"
    _extract_frame(ffmpeg, out_path, frame)

    blue = (0, 0, 255)
    bottom_band = _non_background_pixel_count(ffmpeg, frame, 1700, 200, blue)
    top_band = _non_background_pixel_count(ffmpeg, frame, 50, 200, blue)
    assert top_band > 500, f"Vùng trên phải có nhiều pixel caption khi chọn 'top-center' — đếm được {top_band}"
    assert top_band > bottom_band * 5, f"Caption 'top-center' phải tập trung ở dải TRÊN, không phải dưới — trên={top_band}, dưới={bottom_band}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_segment_without_caption_ass_path_unaffected(tmp_path):
    """Không truyền `caption_ass_path` (mặc định `None`) — hành vi Y HỆT trước khi có
    tính năng caption, không có filter `subtitles` nào được thêm vào."""
    from app.render.assembly import _build_segment

    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x480", "-frames:v", "1", "-update", "1", str(src)], capture_output=True, check=True, text=True)
    out_path = tmp_path / "out.mp4"
    _build_segment(ffmpeg, str(src), None, 1.0, out_path, resolution="640:480", video_codec="libx264", audio_codec="aac", crf=23)
    assert out_path.exists()
