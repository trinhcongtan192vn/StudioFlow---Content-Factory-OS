"""Short-form sub-project (9:16) — **mới (2026-08-21)**, theo yêu cầu người dùng: short-
form (YouTube Shorts/TikTok) là project ĐỘC LẬP nội dung, lồng dưới 1 project long-form
CÙNG kênh chỉ để nhóm hiển thị (KHÔNG PHẢI auto-repurpose, xem `Project.parent_project_id`/
`format`, app/models/__init__.py). Test 3 nhóm: (1) CRUD/cascade archive-restore-xoá
vĩnh viễn, (2) provider adapter nhận đúng tham số khung DỌC, (3) render THẬT ra đúng
kích thước dọc (không mock ffmpeg).
"""
import base64
import io
import shutil
import subprocess
from pathlib import Path

import pytest
import respx
from httpx import Response

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


# ---------------------------------------------------------------------------
# 1. Tạo short-form + cascade archive/restore/xoá vĩnh viễn
# ---------------------------------------------------------------------------
def test_create_short_form_under_long_form_parent(client, channel, project):
    resp = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short 1", "parent_project_id": project["id"]})
    assert resp.status_code == 200
    child = resp.json()
    assert child["parent_project_id"] == project["id"]
    assert child["format"] == "short"


def test_long_form_project_defaults_no_parent(client, project):
    assert project["parent_project_id"] is None
    assert project["format"] == "long"


def test_create_short_form_rejects_missing_parent(client, channel):
    resp = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short mồ côi", "parent_project_id": "prj_does_not_exist"})
    assert resp.status_code == 404


def test_create_short_form_rejects_parent_from_different_channel(client, channel, project):
    other_channel = client.post("/channels", json={"name": "Kênh khác", "niche": "Test"}).json()
    resp = client.post(f"/channels/{other_channel['id']}/projects", json={"title": "Short sai kênh", "parent_project_id": project["id"]})
    assert resp.status_code == 400


def test_create_short_form_rejects_nesting_under_short_form(client, channel, project):
    short = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short 1", "parent_project_id": project["id"]}).json()
    resp = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short lồng short", "parent_project_id": short["id"]})
    assert resp.status_code == 400


def test_archive_long_form_cascades_to_short_form_children(client, channel, project):
    short = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short 1", "parent_project_id": project["id"]}).json()

    resp = client.delete(f"/projects/{project['id']}")
    assert resp.status_code == 200

    remaining_ids = [p["id"] for p in client.get(f"/channels/{channel['id']}/projects").json()]
    assert project["id"] not in remaining_ids
    assert short["id"] not in remaining_ids  # short-form con cũng bị archive theo


def test_archive_short_form_does_not_affect_parent(client, channel, project):
    """Archive 1 short-form con riêng lẻ KHÔNG được kéo theo cha (chỉ chiều long→short,
    không phải hai chiều)."""
    short = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short 1", "parent_project_id": project["id"]}).json()
    client.delete(f"/projects/{short['id']}")

    remaining_ids = [p["id"] for p in client.get(f"/channels/{channel['id']}/projects").json()]
    assert project["id"] in remaining_ids
    assert short["id"] not in remaining_ids


def test_restore_long_form_cascades_to_short_form_children(client, channel, project):
    short = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short 1", "parent_project_id": project["id"]}).json()
    client.delete(f"/projects/{project['id']}")

    resp = client.post(f"/projects/{project['id']}/restore")
    assert resp.status_code == 200

    remaining_ids = [p["id"] for p in client.get(f"/channels/{channel['id']}/projects").json()]
    assert project["id"] in remaining_ids
    assert short["id"] in remaining_ids  # short-form con cũng được khôi phục theo


def test_permanent_delete_long_form_cascades_to_short_form_children(client, channel, project):
    from app.config import project_dir

    short = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short 1", "parent_project_id": project["id"]}).json()
    short_dir = project_dir(channel["id"], short["id"])
    assert short_dir.exists()

    client.delete(f"/projects/{project['id']}")  # archive trước — bắt buộc trước khi permanent
    resp = client.delete(f"/projects/{project['id']}/permanent")
    assert resp.status_code == 200

    assert client.get(f"/projects/{short['id']}").status_code == 404  # con cũng bị xoá DB row
    assert not short_dir.exists()  # và xoá cả thư mục trên đĩa


# ---------------------------------------------------------------------------
# 2. Provider adapter nhận đúng tham số khung DỌC (aspect_ratio="9:16")
# ---------------------------------------------------------------------------
@respx.mock
def test_openai_image_provider_uses_vertical_size_for_short_form():
    from app.providers.image_openai import OpenAIImageProvider

    route = respx.post("https://api.openai.com/v1/images/generations").mock(
        return_value=Response(200, json={"data": [{"b64_json": base64.b64encode(FAKE_PNG).decode()}]})
    )
    provider = OpenAIImageProvider(api_key="sk-test")

    provider.generate("prompt", aspect_ratio="9:16")
    assert route.calls.last.request.content
    import json as _json
    body = _json.loads(route.calls.last.request.content)
    assert body["size"] == "1024x1792"

    provider.generate("prompt", aspect_ratio="16:9")
    body2 = _json.loads(route.calls.last.request.content)
    assert body2["size"] == "1792x1024"


@respx.mock
def test_sora_provider_uses_vertical_size_for_short_form():
    from app.providers.video_sora import SoraVideoProvider

    route = respx.post("https://api.openai.com/v1/videos").mock(return_value=Response(200, json={"id": "vid_1"}))
    provider = SoraVideoProvider(api_key="sk-test")

    provider.start_generation("prompt", aspect_ratio="9:16")
    import json as _json
    body = _json.loads(route.calls.last.request.content)
    assert body["size"] == "720x1280"

    provider.start_generation("prompt", aspect_ratio="16:9")
    body2 = _json.loads(route.calls.last.request.content)
    assert body2["size"] == "1280x720"


@respx.mock
def test_veo_provider_uses_vertical_aspect_ratio_for_short_form():
    from app.providers.video_veo import VeoVideoProvider

    route = respx.post(url__regex=r"https://generativelanguage\.googleapis\.com/v1beta/models/.*:predictLongRunning.*").mock(
        return_value=Response(200, json={"name": "op_1"})
    )
    provider = VeoVideoProvider(api_key="k")

    provider.start_generation("prompt", aspect_ratio="9:16")
    import json as _json
    body = _json.loads(route.calls.last.request.content)
    assert body["parameters"]["aspectRatio"] == "9:16"

    provider.start_generation("prompt", aspect_ratio="16:9")
    body2 = _json.loads(route.calls.last.request.content)
    assert body2["parameters"]["aspectRatio"] == "16:9"


@respx.mock
def test_gemini_image_provider_adds_vertical_prompt_hint():
    """Gemini KHÔNG có tham số kích thước — chỉ verify prompt được nối thêm gợi ý bố cục
    dọc khi aspect_ratio="9:16" (best-effort, xem docstring image_gemini.py)."""
    from app.providers.image_gemini import GeminiImageProvider

    route = respx.post(url__regex=r"https://generativelanguage\.googleapis\.com/v1beta/models/.*:generateContent.*").mock(
        return_value=Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(FAKE_PNG).decode()}}]}}]})
    )
    provider = GeminiImageProvider(api_key="k")

    provider.generate("mo ta canh", aspect_ratio="9:16")
    import json as _json
    body = _json.loads(route.calls.last.request.content)
    text = body["contents"][0]["parts"][0]["text"]
    assert "mo ta canh" in text
    assert "dọc" in text.lower() or "9:16" in text

    provider.generate("mo ta canh", aspect_ratio="16:9")
    body2 = _json.loads(route.calls.last.request.content)
    assert body2["contents"][0]["parts"][0]["text"] == "mo ta canh"  # không đổi gì khi 16:9


@respx.mock
def test_flux_image_provider_uses_vertical_width_height_for_short_form():
    from app.providers.image_flux import FluxImageProvider

    submit_route = respx.post("https://api.bfl.ai/v1/flux-2-pro").mock(return_value=Response(200, json={"id": "req_1"}))
    respx.get("https://api.bfl.ai/v1/get_result").mock(return_value=Response(200, json={"status": "Ready", "result": {"sample": "https://example.com/out.png"}}))
    respx.get("https://example.com/out.png").mock(return_value=Response(200, content=FAKE_PNG))
    provider = FluxImageProvider(api_key="k")

    provider.generate("prompt", aspect_ratio="9:16")
    import json as _json
    body = _json.loads(submit_route.calls.last.request.content)
    assert (body["width"], body["height"]) == (800, 1408)


def test_sdxl_workflow_builder_uses_vertical_dims_when_passed():
    from app.providers.image_comfy_sdxl import _build_txt2img_workflow

    wf_default = _build_txt2img_workflow(prompt="x", seed=1)
    assert wf_default["5"]["inputs"]["width"] == 1344 and wf_default["5"]["inputs"]["height"] == 768

    wf_vertical = _build_txt2img_workflow(prompt="x", seed=1, width=768, height=1344)
    assert wf_vertical["5"]["inputs"]["width"] == 768 and wf_vertical["5"]["inputs"]["height"] == 1344


def test_wan_workflow_builder_uses_vertical_dims_when_passed():
    from app.providers.video_comfy_wan import _build_txt2vid_workflow

    wf_default = _build_txt2vid_workflow(prompt="x", seed=1, num_frames=25)
    assert wf_default["55"]["inputs"]["width"] == 1280 and wf_default["55"]["inputs"]["height"] == 704

    wf_vertical = _build_txt2vid_workflow(prompt="x", seed=1, num_frames=25, width=704, height=1280)
    assert wf_vertical["55"]["inputs"]["width"] == 704 and wf_vertical["55"]["inputs"]["height"] == 1280


# ---------------------------------------------------------------------------
# 3. Render THẬT — output đúng khung dọc (không mock ffmpeg)
# ---------------------------------------------------------------------------
def _ffprobe_video_dims(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    w, h = out.stdout.strip().split(",")
    return int(w), int(h)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_short_form_project_outputs_vertical_resolution(client, channel, project):
    """Verify THẬT xuyên suốt (không mock ffmpeg): tạo short-form con, sinh 1 shot ẢNH
    NGANG cố tình (16:9, mô phỏng provider không kiểm soát được khung — VD Gemini) —
    xác nhận `assemble_video()` vẫn ra ĐÚNG khung DỌC 1080x1920 (không phải 1920x1080,
    không bị méo) nhờ crop-to-fill (`app/render/assembly.py::_scale_cover_filter`)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    short = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short 1", "parent_project_id": project["id"]}).json()
    pid = short["id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:02", "Image", "Canh test", "Khong tieng", "Loi thoai test."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    confirm = client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200, confirm.text
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel["id"], pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    # Ảnh NGANG cố tình (16:9) — mô phỏng provider không kiểm soát được khung dọc.
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    state = RenderState(project_id=pid, shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="1080p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])
    assert final_path.exists()

    w, h = _ffprobe_video_dims(final_path)
    assert (w, h) == (1080, 1920), f"Short-form phải ra khung DỌC 1080x1920, thực tế {w}x{h}"


def _ffprobe_video_sar(path: Path) -> str:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=sample_aspect_ratio", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return out.stdout.strip()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_short_form_with_brand_intro_and_sdxl_bucket_image_succeeds(client, channel, project):
    """Bug thật người dùng báo (2026-08-22, mục 59 IMPLEMENTATION_REPORT.md), project
    "Nghịch lý giữa công lao khai quốc và bản án tru di": render short-form LỖI HẲN
    (assembly_status="error") khi kênh có VIDEO THƯƠNG HIỆU cấp kênh (16:9, brand-level
    fallback intro) VÀ shot ảnh sinh bằng SDXL local (bucket dọc 768x1344 — tỷ lệ 4:7 ≈
    0.5714, LỆCH tỷ lệ 9:16 = 0.5625 thật của short-form, không phải trùng khớp). Lỗi
    ffmpeg thật: `concat` từ chối ghép vì 2 input có SAR (sample aspect ratio) khác nhau
    dù cùng kích thước pixel — `scale=...force_original_aspect_ratio=increase` tự gán
    SAR bù trừ phần lẻ làm tròn, mỗi input lệch tỷ lệ khác nhau ra SAR khác nhau.

    Tái hiện CHÍNH XÁC tổ hợp gây lỗi: video thương hiệu cấp kênh (16:9, brand fallback —
    KHÔNG phải intro riêng của project) + 1 shot ảnh 768x1344 (đúng bucket SDXL dọc, lệch
    9:16) — verify `assemble_video()` thật thành công (không lỗi), output ĐÚNG 1080x1920
    VÀ SAR sạch 1:1 (không phải giá trị bù trừ như "10240:10239")."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")

    # Video thương hiệu 16:9 cấp KÊNH (không phải intro riêng của project — đúng nhánh
    # brand-level fallback trong _resolve_intro_source đã gây lỗi thật).
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    intro_src = tmp / "brand_intro.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=1920x1080:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(intro_src)],
        capture_output=True, check=True, text=True,
    )
    upload = client.post(f"/channels/{channel['id']}/brandprofile/intro/upload", files={"file": ("intro.mp4", intro_src.open("rb"), "video/mp4")})
    assert upload.status_code == 200, upload.text

    short = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short SAR bug", "parent_project_id": project["id"]}).json()
    pid = short["id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:02", "Image", "Canh test", "Khong tieng", "Loi thoai test."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel["id"], pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    # Đúng bucket dọc SDXL (768x1344, tỷ lệ 4:7) — cố tình LỆCH 9:16 thật (0.5625).
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=768x1344", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    state = RenderState(project_id=pid, shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="1080p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])
    assert final_path.exists() and final_path.stat().st_size > 0

    w, h = _ffprobe_video_dims(final_path)
    assert (w, h) == (1080, 1920)
    sar = _ffprobe_video_sar(final_path)
    assert sar in ("1:1", "1", ""), f"SAR không sạch (1:1) — {sar!r}, có thể lộ lại bug SAR-mismatch"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_long_form_project_still_outputs_landscape_resolution(client, project):
    """Long-form KHÔNG bị ảnh hưởng bởi thay đổi crop-to-fill (mục 55/57 IMPLEMENTATION_
    REPORT.md rồi, giờ verify LUÔN cho tính năng short-form): vẫn ra 1920x1080 như cũ."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:02", "Image", "Canh test", "Khong tieng", "Loi thoai test."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    state = RenderState(project_id=pid, shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True)])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="1080p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    w, h = _ffprobe_video_dims(Path(final_state["final_video_path"]))
    assert (w, h) == (1920, 1080)
