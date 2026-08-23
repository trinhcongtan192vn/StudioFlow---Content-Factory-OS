"""Test Render Studio (M2 Production Layer) — mock TOÀN BỘ HTTP call ra ngoài qua
respx (ElevenLabs/OpenAI Image/Sora/Gemini/Veo), không gọi API thật, không tốn phí.
Lái project qua pipeline thật (giống test_pipeline_flow.py).

2026-08-17 (mục 44 IMPLEMENTATION_REPORT.md): bỏ hẳn Pack Review/Gate #2 — sinh asset
thật (`render/start` + regenerate) VÀ `render/assemble` (ghép MP4) đều dùng được ngay
từ Visual Studio, không còn gate nào theo `project.status`. `render/assemble` tự kiểm
trực tiếp trên `state.shots` (mọi shot đã sinh xong visual VÀ đã duyệt) thay cho gate cũ.
"""
import base64
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import respx
from httpx import Response

from app.render.assembly import _XFADE_DURATION_SEC, _beat_duration, _build_segment, _xfade_chain

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
FAKE_MP3 = b"ID3" + b"0" * 20
FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20
FAKE_WAV = b"RIFF" + b"0" * 40


def _import_script_csv(client, pid: str, n: int = 6) -> None:
    """Import 1 script CSV có `n` block, trộn Image/Video (đại khái 2:1, giống tỉ lệ
    `fallback_shots` cũ dùng cho đường AI) — thay thế đường AI Research/Outline/Hook/
    Gate1/script-approve đã bỏ (2026-08-17, mục 44 IMPLEMENTATION_REPORT.md)."""
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = []
    for i in range(n):
        start, end = i * 8, i * 8 + 8
        visual_type = "Video" if i % 3 == 1 else "Image"
        rows.append([f"B{i + 1:02d}", f"0:{start:02d}–0:{end:02d}", visual_type, f"Mo ta canh {i + 1}", f"Nhac nen {i + 1}", f"Day la loi thoai cho block so {i + 1}, du dai de test."])
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    confirm = client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200, confirm.text


def _drive_to_visual_studio(client, project_with_brief) -> str:
    """Import script rồi vào Visual Studio — KHÔNG còn gate duyệt nào chặn `render/start`
    dùng được từ đây (không đổi so với trước, chỉ đổi cách có script)."""
    pid = project_with_brief["id"]
    _import_script_csv(client, pid)
    resp = client.post(f"/projects/{pid}/visual/generate")
    assert resp.status_code == 200, resp.text
    proj = client.get(f"/projects/{pid}").json()
    assert proj["status"] == "generating"
    return pid


def _drive_to_ready_output(client, project_with_brief) -> str:
    """KHÔNG còn Pack Review/Gate #2 (2026-08-17, mục 44) — Output vào được thẳng từ
    Visual Studio, không cần build_pack/gate2 approve nữa."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    resp = client.post(f"/projects/{pid}/output/enter")
    assert resp.status_code == 200, resp.text
    return pid


def _delete_all_asset_providers(client) -> None:
    for p in client.get("/providers").json():
        if p["task"] in ("tts", "image", "video"):
            client.delete(f"/providers/{p['id']}")


def _setup_asset_providers(client) -> None:
    tts = client.post("/providers", json={"task": "tts", "provider_name": "elevenlabs", "display_name": "EL", "connection_type": "cloud_api", "api_key": "sk-el-test"}).json()
    client.patch(f"/providers/{tts['id']}", json={"is_default": True})
    image = client.post("/providers", json={"task": "image", "provider_name": "openai", "display_name": "OAI Img", "connection_type": "cloud_api", "api_key": "sk-oai-test"}).json()
    client.patch(f"/providers/{image['id']}", json={"is_default": True})
    video = client.post("/providers", json={"task": "video", "provider_name": "sora", "display_name": "Sora", "connection_type": "cloud_api", "api_key": "sk-oai-test"}).json()
    client.patch(f"/providers/{video['id']}", json={"is_default": True})


def _mock_asset_apis():
    respx.post("https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM").mock(return_value=Response(200, content=FAKE_MP3))
    respx.post("https://api.openai.com/v1/images/generations").mock(return_value=Response(200, json={"data": [{"b64_json": base64.b64encode(FAKE_PNG).decode()}]}))
    respx.post("https://api.openai.com/v1/videos").mock(return_value=Response(200, json={"id": "vid_1", "status": "queued"}))
    respx.get("https://api.openai.com/v1/videos/vid_1").mock(return_value=Response(200, json={"id": "vid_1", "status": "completed"}))
    respx.get("https://api.openai.com/v1/videos/vid_1/content").mock(return_value=Response(200, content=FAKE_MP4))


@pytest.fixture()
def render_ready_project(client, project_with_brief):
    pid = _drive_to_ready_output(client, project_with_brief)
    _setup_asset_providers(client)
    return pid


def test_render_start_requires_shots(client, project_with_brief):
    resp = client.post(f"/projects/{project_with_brief['id']}/render/start")
    assert resp.status_code == 400


@respx.mock
def test_render_start_works_from_visual_studio(client, project_with_brief):
    """Sinh asset thật dùng được ngay ở Visual Studio — không cần gate/status nào."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()

    resp = client.post(f"/projects/{pid}/render/start")
    assert resp.status_code == 200
    state = client.get(f"/projects/{pid}/render/status").json()
    assert len(state["shots"]) > 0
    assert all(s["visual_status"] == "ready" for s in state["shots"])

    proj = client.get(f"/projects/{pid}").json()
    assert proj["status"] == "generating"  # sinh asset không tự đổi status


@respx.mock
def test_cancel_before_start_stops_batch_immediately(client, project_with_brief):
    """Đặt cờ huỷ TRƯỚC khi gọi render/start — batch dừng ngay ở lần kiểm tra đầu
    (KHÔNG xử lý shot nào), khác lỗi provider thật (vẫn set 'error' sau khi thử). Cờ
    phải tự dọn sau khi batch dừng (finally trong run_asset_generation) — lần start kế
    tiếp không bị dính cờ cũ, chạy bình thường."""
    from app.render import engine

    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()

    engine.request_cancel(pid)
    resp = client.post(f"/projects/{pid}/render/start")
    assert resp.status_code == 200
    state = client.get(f"/projects/{pid}/render/status").json()
    assert all(s["visual_status"] == "pending" for s in state["shots"])
    assert not engine.is_cancel_requested(pid)  # tự dọn cờ, không rò rỉ sang lần sau
    assert not engine.is_generation_in_progress(pid)  # cờ "đang chạy" cũng tự dọn

    # Start lại bình thường (không huỷ) — không bị dính cờ cũ, chạy xong thật.
    resp2 = client.post(f"/projects/{pid}/render/start")
    assert resp2.status_code == 200
    state2 = client.get(f"/projects/{pid}/render/status").json()
    assert all(s["visual_status"] == "ready" for s in state2["shots"])


def test_render_cancel_endpoint_returns_state(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    resp = client.post(f"/projects/{pid}/render/cancel")
    assert resp.status_code == 200
    assert resp.json()["project_id"] == pid


def test_start_render_rejected_while_another_task_in_progress(client, project_with_brief):
    """Chặn mở batch/regenerate MỚI khi project đã có 1 task đang chạy — tránh 2
    BackgroundTasks cùng ghi đè render.json (bug thật đã gặp: bấm 'toàn bộ block' rồi
    bấm 'sinh lại' 1 shot ngay lúc batch đang chạy, các shot sau không bao giờ được xử
    lý). Giả lập "đang chạy" trực tiếp qua engine, không cần chờ job thật."""
    from app.render import engine

    pid = _drive_to_visual_studio(client, project_with_brief)
    engine._mark_in_progress(pid)
    try:
        resp = client.post(f"/projects/{pid}/render/start")
        assert resp.status_code == 409
    finally:
        engine._mark_done(pid)

    # Sau khi "xong" (không còn bị chặn 409), request được CHẤP NHẬN bình thường —
    # chưa setup provider ở test này nên từng shot lỗi "chưa cấu hình provider" (khác
    # hẳn 409 ở trên, không liên quan tới cờ in-progress).
    resp2 = client.post(f"/projects/{pid}/render/start")
    assert resp2.status_code == 200


@respx.mock
def test_assemble_works_without_output_enter(client, project_with_brief, monkeypatch):
    """2026-08-17 (mục 44): ghép MP4 KHÔNG còn cần qua Gate #2/`output/enter` nữa — chỉ
    cần shot đã sinh xong visual VÀ đã duyệt, dùng được thẳng từ Visual Studio.

    Giả lập chưa cài ffmpeg (như `test_assemble_fails_clearly_without_ffmpeg`) — asset
    ở đây là bytes ảnh GIẢ (`FAKE_PNG`, không phải PNG thật), để ffmpeg THẬT xử lý sẽ
    treo/lỗi không đoán trước được (TestClient chạy BackgroundTasks ĐỒNG BỘ trong cùng
    request, nên 1 lệnh ffmpeg thật bị treo sẽ treo LUÔN cả request `client.post`). Test
    này chỉ cần xác nhận request ĐƯỢC CHẤP NHẬN (không còn bị chặn bởi gate cũ), không
    cần assembly thật sự chạy xong — không liên quan tới điều đang kiểm."""
    import shutil as _shutil

    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        resp = client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})
        assert resp.status_code == 200

    monkeypatch.setattr(_shutil, "which", lambda name: None)
    resp = client.post(f"/projects/{pid}/render/assemble")
    assert resp.status_code == 200
    assert resp.json()["assembly_status"] == "assembling"


def test_render_status_empty_before_start(client, render_ready_project):
    resp = client.get(f"/projects/{render_ready_project}/render/status")
    assert resp.status_code == 200
    assert resp.json()["shots"] == []


# ---------------------------------------------------------------------------
# render/start?force=true — mới (2026-08-22), theo yêu cầu người dùng: nút "toàn bộ
# block" trước đây LUÔN bỏ qua shot đã `ready` (đúng cho resume sau lỗi), nhưng không có
# cách sinh lại HÀNG LOẠT khi đổi BrandProfile (giọng/style ảnh mới). `force=true` reset
# TRƯỚC mọi shot `ready` (đúng kind) về "generating" ngay ở router — cùng cơ chế
# `regenerate_visual`/`regenerate_narration` đã dùng cho 1 shot.
# ---------------------------------------------------------------------------
def _count_calls(url_fragment: str) -> int:
    """Đếm số lần gọi THẬT tới 1 URL qua call log toàn cục của respx — KHÔNG re-khai báo
    route bằng `respx.post(url)` để lấy `call_count` (bug thật gặp lúc viết test này: gọi
    `respx.post(url)` LẦN 2 không kèm `.mock(...)` tạo/trả về route THIẾU response, khiến
    lần gọi thật kế tiếp nhận body rỗng → lỗi JSONDecodeError ở tầng provider)."""
    return sum(1 for c in respx.calls if url_fragment in str(c.request.url))


@respx.mock
def test_render_start_without_force_leaves_ready_shots_untouched(client, project_with_brief):
    """Hành vi MẶC ĐỊNH (force=False, không đổi) — resume: shot đã ready/đã duyệt KHÔNG
    bị đụng tới, không gọi lại API tốn phí."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    calls_before = _count_calls("images/generations")

    resp = client.post(f"/projects/{pid}/render/start")
    assert resp.status_code == 200
    state2 = client.get(f"/projects/{pid}/render/status").json()
    image_shots = [s for s in state2["shots"] if s["visual_provider"] == "openai"]
    assert image_shots
    assert all(s["approved"] is True for s in image_shots)  # KHÔNG bị bỏ duyệt
    assert _count_calls("images/generations") == calls_before  # KHÔNG gọi lại API


@respx.mock
def test_render_start_force_regenerates_ready_shots(client, project_with_brief):
    """force=True PHẢI sinh lại THẬT (gọi lại API) cho shot đã ready — đúng bug người
    dùng báo: nút "toàn bộ block" không hoạt động khi shot đã có sẵn."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")

    img_calls_before = _count_calls("images/generations")
    tts_calls_before = _count_calls("text-to-speech")
    assert img_calls_before > 0 and tts_calls_before > 0  # xác nhận lần đầu đã gọi thật

    resp = client.post(f"/projects/{pid}/render/start", params={"kind": "both", "force": "true"})
    assert resp.status_code == 200
    state = client.get(f"/projects/{pid}/render/status").json()
    assert all(s["visual_status"] == "ready" for s in state["shots"])
    assert all(s["narration_status"] == "ready" for s in state["shots"])
    assert _count_calls("images/generations") > img_calls_before  # gọi lại THẬT, không bị bỏ qua
    assert _count_calls("text-to-speech") > tts_calls_before


@respx.mock
def test_render_start_force_resets_approval_for_regenerated_visual(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    client.post(f"/projects/{pid}/render/start", params={"kind": "visual", "force": "true"})
    state2 = client.get(f"/projects/{pid}/render/status").json()
    assert all(s["approved"] is False for s in state2["shots"])  # sinh lại -> cần duyệt lại


@respx.mock
def test_render_start_force_respects_kind_scope(client, project_with_brief):
    """force=True, kind="narration" — CHỈ sinh lại giọng đọc, KHÔNG đụng ảnh/video/duyệt."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    img_calls_before = _count_calls("images/generations")

    resp = client.post(f"/projects/{pid}/render/start", params={"kind": "narration", "force": "true"})
    assert resp.status_code == 200
    state2 = client.get(f"/projects/{pid}/render/status").json()
    image_shots = [s for s in state2["shots"] if s["visual_provider"] == "openai"]
    assert all(s["approved"] is True for s in image_shots)  # visual KHÔNG bị đụng
    assert _count_calls("images/generations") == img_calls_before  # KHÔNG gọi lại API ảnh


@respx.mock
def test_render_start_generates_all_assets_and_status_polls(client, render_ready_project):
    pid = render_ready_project
    _mock_asset_apis()

    resp = client.post(f"/projects/{pid}/render/start")
    assert resp.status_code == 200

    state = client.get(f"/projects/{pid}/render/status").json()
    assert len(state["shots"]) > 0
    for s in state["shots"]:
        assert s["visual_status"] == "ready", s
        assert s["visual_asset_path"]
        assert s["visual_provider"] in ("openai", "sora")
        # mọi beat fallback đều có lời đọc -> narration phải ready
        assert s["narration_status"] == "ready", s
        assert s["narration_asset_path"]
        assert not s["approved"]


@respx.mock
def test_approve_requires_ready_visual(client, render_ready_project):
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot_id = state["shots"][0]["shot_id"]

    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/approve", json={"approved": True})
    assert resp.status_code == 200
    assert next(s for s in resp.json()["shots"] if s["shot_id"] == shot_id)["approved"] is True

    resp = client.post(f"/projects/{pid}/render/shots/does-not-exist/approve", json={"approved": True})
    assert resp.status_code == 404


@respx.mock
def test_regenerate_visual_resets_approval(client, render_ready_project):
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot_id = state["shots"][0]["shot_id"]
    client.post(f"/projects/{pid}/render/shots/{shot_id}/approve", json={"approved": True})

    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/regenerate-visual")
    assert resp.status_code == 200
    state = client.get(f"/projects/{pid}/render/status").json()
    shot = next(s for s in state["shots"] if s["shot_id"] == shot_id)
    assert shot["visual_status"] == "ready"
    assert shot["approved"] is False  # sinh lại -> phải duyệt lại


@respx.mock
def test_upload_shot_visual_replaces_asset_and_resets_approval(client, render_ready_project):
    """Upload ảnh thay thế asset AI đã sinh — cùng shot_id, provider đổi thành "upload",
    approved reset về False, file AI cũ (đuôi khác) bị xoá thay vì để rác trên đĩa."""
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot = next(s for s in state["shots"] if s["visual_status"] == "ready")
    shot_id = shot["shot_id"]
    old_path = shot["visual_asset_path"]
    assert old_path and Path(old_path).exists()
    client.post(f"/projects/{pid}/render/shots/{shot_id}/approve", json={"approved": True})

    # Upload đuôi KHÁC AI cũ (.png -> .jpg, cùng kiểu "ảnh") để thật sự exercise nhánh
    # xoá file cũ — nếu cùng đuôi thì old_path == new_path, write_bytes tự ghi đè,
    # không có gì để xoá (không phải bug, chỉ là case khác).
    new_jpg = b"\xff\xd8\xff" + b"1" * 30
    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/upload-visual", files={"file": ("moi.jpg", io.BytesIO(new_jpg), "image/jpeg")})
    assert resp.status_code == 200, resp.text
    uploaded = next(s for s in resp.json()["shots"] if s["shot_id"] == shot_id)
    assert uploaded["visual_status"] == "ready"
    assert uploaded["visual_provider"] == "upload"
    assert uploaded["approved"] is False  # thay ảnh mới -> phải duyệt lại
    new_path = uploaded["visual_asset_path"]
    assert new_path.endswith(f"{shot_id}.jpg")
    assert Path(new_path).read_bytes() == new_jpg
    assert not Path(old_path).exists()  # file AI cũ (.png) đã bị xoá, không để rác


@respx.mock
def test_upload_shot_visual_works_before_render_start(client, project_with_brief):
    """Upload phải dùng được ngay cả khi CHƯA từng bấm 'Bắt đầu sinh asset' — tự tạo
    entry render.json thay vì bắt lỗi 404 như approve/regenerate (khác quy ước cũ)."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    shot_id = pack["shots"][0]["shot_id"]

    resp = client.post(f"/projects/{pid}/render/status")  # sanity: chưa có gì
    png = b"\x89PNG\r\n\x1a\n" + b"2" * 10
    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/upload-visual", files={"file": ("a.png", io.BytesIO(png), "image/png")})
    assert resp.status_code == 200, resp.text
    shot = next(s for s in resp.json()["shots"] if s["shot_id"] == shot_id)
    assert shot["visual_status"] == "ready"
    assert shot["visual_provider"] == "upload"


@respx.mock
def test_upload_shot_visual_rejects_type_mismatch(client, render_ready_project):
    pid = render_ready_project
    pack = client.get(f"/projects/{pid}/pack").json()
    image_shot = next(s for s in pack["shots"] if s["visual_type"] == "image")

    resp = client.post(
        f"/projects/{pid}/render/shots/{image_shot['shot_id']}/upload-visual",
        files={"file": ("a.mp4", io.BytesIO(b"\x00\x00\x00\x18ftyp" + b"0" * 10), "video/mp4")},
    )
    assert resp.status_code == 400
    assert "kiểu ảnh" in resp.json()["detail"]


@respx.mock
def test_upload_shot_visual_rejected_while_in_progress(client, render_ready_project):
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot_id = state["shots"][0]["shot_id"]

    from app.render import engine as render_engine
    render_engine._mark_in_progress(pid)
    try:
        resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/upload-visual", files={"file": ("a.png", io.BytesIO(b"x"), "image/png")})
        assert resp.status_code == 409
    finally:
        render_engine._mark_done(pid)


@respx.mock  # an toàn kép: nếu lỡ còn provider sót lại từ test khác, request thật sẽ
# raise lỗi respx (không route nào được đăng ký) thay vì lọt ra network thật.
def test_asset_generation_fails_clearly_without_provider(client, project_with_brief):
    """Không cấu hình provider tts/image/video -> mỗi shot ghi lỗi rõ ràng vào
    render.json (không raise 500, không âm thầm bỏ qua) — cùng tinh thần
    NoProviderConfiguredError đã áp dụng cho LLM (test_no_provider.py). Chủ động xoá
    hết provider tts/image/video hiện có trước khi test — `client` dùng chung 1 session
    với các test khác trong file này (VD render_ready_project) nên có thể còn sót lại
    provider từ trước, gây lẫn giữa 2 lớp lỗi khác nhau (thiếu provider vs key sai)."""
    _delete_all_asset_providers(client)
    pid = _drive_to_ready_output(client, project_with_brief)
    resp = client.post(f"/projects/{pid}/render/start")
    assert resp.status_code == 200
    state = client.get(f"/projects/{pid}/render/status").json()
    assert len(state["shots"]) > 0
    for s in state["shots"]:
        assert s["visual_status"] == "error"
        assert "Provider AI" in s["visual_error"]
        assert s["narration_status"] == "error"
        assert "Provider AI" in s["narration_error"]


@respx.mock
def test_assemble_requires_all_shots_ready_and_approved(client, render_ready_project):
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")

    resp = client.post(f"/projects/{pid}/render/assemble")
    assert resp.status_code == 400  # chưa duyệt shot nào


@respx.mock
def test_assemble_fails_clearly_without_ffmpeg(client, render_ready_project, monkeypatch):
    """Giả lập máy chưa cài ffmpeg (shutil.which trả None) — assembly phải ghi lỗi rõ
    vào render.json thay vì crash, không cần ffmpeg thật cài trên máy chạy test."""
    import shutil as _shutil

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    monkeypatch.setattr(_shutil, "which", lambda name: None)
    resp = client.post(f"/projects/{pid}/render/assemble")
    assert resp.status_code == 200  # kick off thành công (chạy nền), lỗi xuất hiện sau ở status

    state = client.get(f"/projects/{pid}/render/status").json()
    assert state["assembly_status"] == "error"
    assert "ffmpeg" in state["assembly_error"].lower()


@respx.mock
def test_assemble_rejects_gpu_with_vp9_immediately(client, render_ready_project):
    """Router phải validate NGAY (400 trước khi giao BackgroundTasks), không đợi
    assembly chạy xong đoạn đầu mới báo lỗi — không có `vp9_nvenc` trong ffmpeg (xác
    nhận thật bằng `ffmpeg -encoders`) nên tổ hợp GPU+VP9 luôn vô nghĩa."""
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    resp = client.post(f"/projects/{pid}/render/assemble", json={"codec": "vp9", "use_gpu": True})
    assert resp.status_code == 400
    assert "nvenc" in resp.json()["detail"].lower() or "gpu" in resp.json()["detail"].lower()

    state = client.get(f"/projects/{pid}/render/status").json()
    assert state["assembly_status"] != "assembling"  # bị chặn trước khi kịp đổi trạng thái


def test_gpu_encode_status_endpoint_returns_bool(client):
    """Endpoint machine-level (không gắn project) — frontend gọi lúc mở màn cấu hình
    export để biết hiện/disable checkbox GPU TRƯỚC khi người dùng bấm 'Ghép video'."""
    resp = client.get("/render/gpu-encode-status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["available"], bool)
    assert "message" in data


def test_gpu_encode_status_missing_ffmpeg_returns_unavailable(client, monkeypatch):
    import app.routers.render as render_router

    monkeypatch.setattr(render_router.shutil, "which", lambda name: None)
    resp = client.get("/render/gpu-encode-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert "ffmpeg" in data["message"].lower()


def test_download_requires_assembly_done(client, render_ready_project):
    resp = client.get(f"/projects/{render_ready_project}/render/download")
    assert resp.status_code == 400


def test_beat_duration_uses_timestamp_range():
    assert _beat_duration({"timestamp_sec": 10, "end_sec": 18}) == 8.0
    assert _beat_duration({"timestamp_sec": 10, "end_sec": None}) == 5.0
    assert _beat_duration({}) == 5.0


# ---------------------------------------------------------------------------
# `_shot_base_duration` — 2026-08-20, theo yêu cầu người dùng: timestamp kịch bản chỉ
# tham khảo, KHÔNG dùng để render — ưu tiên độ dài giọng đọc THẬT. Bug thật đã gặp:
# timestamp ghi 40s nhưng giọng đọc TTS chỉ 34s → ảnh đứng yên "chết" 6s trước khi giọng
# đọc shot kế tiếp mới phát.
# ---------------------------------------------------------------------------
def test_shot_base_duration_prefers_real_narration_over_beat_timestamp():
    from app.render.assembly import _shot_base_duration
    from app.render.schemas import ShotRenderStatus

    status = ShotRenderStatus(shot_id="s1", narration_status="ready", narration_duration_sec=34.0)
    beat = {"timestamp_sec": 0, "end_sec": 40}  # kịch bản ghi 40s — PHẢI bị bỏ qua
    assert _shot_base_duration(status, beat) == 34.0


def test_shot_base_duration_falls_back_to_beat_when_narration_not_ready():
    from app.render.assembly import _shot_base_duration
    from app.render.schemas import ShotRenderStatus

    beat = {"timestamp_sec": 0, "end_sec": 40}
    pending = ShotRenderStatus(shot_id="s1", narration_status="pending")
    assert _shot_base_duration(pending, beat) == 40.0

    ready_but_no_duration = ShotRenderStatus(shot_id="s1", narration_status="ready", narration_duration_sec=None)
    assert _shot_base_duration(ready_but_no_duration, beat) == 40.0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_uses_real_narration_duration_not_beat_timestamp(client, project_with_brief, tmp_path):
    """Verify THẬT xuyên suốt (bug thật người dùng báo, 2026-08-20): import script với
    1 block ghi timestamp DÀI 8s (`0:00–0:08`), nhưng giọng đọc THẬT chỉ ~2s — gọi
    `assemble_video()` thật (ffmpeg thật, không mock) — xác nhận video kết quả dài
    ~2s (khớp giọng đọc thật), KHÔNG PHẢI ~8s (khớp timestamp kịch bản, tức còn "khoảng
    chết" ảnh đứng yên không tiếng — đúng bug đã báo)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:08", "Image", "Canh test", "Khong tieng", "Loi thoai ngan hon nhieu so voi timestamp kich ban ghi."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    narration_mp3 = pdir / "assets" / f"{shot_id}.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "mp3", str(narration_mp3)], capture_output=True, check=True, text=True)
    real_narration_sec = _ffprobe_duration(narration_mp3)
    assert real_narration_sec < 3.0  # sanity: ngắn hơn hẳn 8s timestamp kịch bản

    state = RenderState(project_id=pid, shots=[ShotRenderStatus(
        shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True,
        narration_status="ready", narration_asset_path=str(narration_mp3), narration_duration_sec=real_narration_sec,
    )])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])
    total_duration = _ffprobe_duration(final_path)
    assert total_duration == pytest.approx(real_narration_sec, abs=0.5), (
        f"Video ra dài {total_duration}s — kỳ vọng khớp giọng đọc thật ({real_narration_sec}s), "
        f"không phải timestamp kịch bản (8s) — nghi ngờ vẫn còn dùng _beat_duration thay vì narration_duration_sec"
    )


# ---------------------------------------------------------------------------
# GPU encode (NVENC) — 2026-08-17, theo yêu cầu người dùng ("CPU render có vẻ lâu").
# ---------------------------------------------------------------------------
def test_resolve_video_codec_cpu_default():
    from app.render.assembly import resolve_video_codec

    assert resolve_video_codec("h264", False) == "libx264"
    assert resolve_video_codec("h265", False) == "libx265"
    assert resolve_video_codec("vp9", False) == "libvpx-vp9"


def test_resolve_video_codec_gpu_maps_to_nvenc():
    from app.render.assembly import resolve_video_codec

    assert resolve_video_codec("h264", True) == "h264_nvenc"
    assert resolve_video_codec("h265", True) == "hevc_nvenc"


def test_resolve_video_codec_gpu_rejects_vp9():
    """Không có `vp9_nvenc` trong ffmpeg (xác nhận thật bằng `ffmpeg -encoders` trên máy
    dev) — phải raise rõ ràng thay vì âm thầm rơi về CPU hay để ffmpeg tự lỗi khó hiểu."""
    from app.render.assembly import resolve_video_codec

    with pytest.raises(ValueError, match="NVENC"):
        resolve_video_codec("vp9", True)


def test_quality_flags_cpu_uses_crf():
    from app.render.assembly import _quality_flags

    assert _quality_flags("libx264", 23) == ["-crf", "23"]
    assert _quality_flags("libvpx-vp9", 31) == ["-crf", "31"]


def test_quality_flags_gpu_uses_cq():
    """NVENC không nhận `-crf` — dùng `-rc vbr -cq N` (xác nhận thật bằng `ffmpeg -h
    encoder=h264_nvenc`: hỗ trợ `-cq` thang 0-51, cùng thang với CRF_TABLE hiện có)."""
    from app.render.assembly import _quality_flags

    assert _quality_flags("h264_nvenc", 23) == ["-rc", "vbr", "-cq", "23"]
    assert _quality_flags("hevc_nvenc", 28) == ["-rc", "vbr", "-cq", "28"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_probe_gpu_encoder_real_returns_consistent_cached_result():
    """Test THẬT (không mock subprocess) — kết quả `ok` phụ thuộc máy chạy test (có GPU
    NVIDIA + driver đủ mới cho bản ffmpeg này hay không — đã gặp thật lúc phát triển
    tính năng: RTX 5060 Ti + driver 576.88 hiện KHÔNG đủ mới, ffmpeg báo "Driver does
    not support the required nvenc API version"), nên KHÔNG assert cứng `ok` là True
    hay False — chỉ xác nhận hàm không crash, trả đúng kiểu, và cache đúng (gọi lần 2 ra
    cùng kết quả, không phụ thuộc lại subprocess mới)."""
    from app.render import assembly

    assembly._GPU_PROBE_CACHE.clear()
    ffmpeg = shutil.which("ffmpeg")
    ok1, msg1 = assembly.probe_gpu_encoder(ffmpeg)
    assert isinstance(ok1, bool)
    assert isinstance(msg1, str)
    ok2, msg2 = assembly.probe_gpu_encoder(ffmpeg)
    assert (ok1, msg1) == (ok2, msg2)


def test_probe_gpu_encoder_missing_ffmpeg_path_returns_false():
    from app.render import assembly

    assembly._GPU_PROBE_CACHE.clear()
    ok, msg = assembly.probe_gpu_encoder("C:/khong-ton-tai/ffmpeg-gia.exe")
    assert ok is False
    assert msg


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return float(out.stdout.strip())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_segment_loops_short_video_to_fill_target_duration(tmp_path):
    """Bug thật (2026-08-17, mục 43): B01 của project thật người dùng có shot video
    (AI sinh "6s loopable" HOẶC upload tay) NGẮN HƠN duration của beat — trước fix,
    `_build_segment` không loop input video, segment ra ĐÚNG bằng độ dài file gốc (ngắn
    hơn `duration` yêu cầu). `_xfade_chain` tính offset dựa trên `duration` danh nghĩa
    (không phải độ dài thật của segment) → lệch, ffmpeg lỗi filter graph ở bước ghép
    cuối. Verify bằng ffmpeg THẬT: dựng 1 video test 2s, yêu cầu segment 5s, xác nhận
    file kết quả THẬT SỰ dài ~5s (không phải 2s) — tức video đã được loop để lấp đủ."""
    ffmpeg = shutil.which("ffmpeg")
    short_video = tmp_path / "short.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(short_video)],
        capture_output=True, check=True, text=True,
    )
    assert round(_ffprobe_duration(short_video)) == 2  # sanity: input thật ngắn hơn target bên dưới

    out_path = tmp_path / "segment_out.mp4"
    _build_segment(
        ffmpeg, str(short_video), None, duration=5.0, out_path=out_path,
        resolution="320:240", video_codec="libx264", audio_codec="aac", crf=28, ensure_audio_track=True,
    )
    result_duration = _ffprobe_duration(out_path)
    assert result_duration >= 4.8, f"Segment chỉ dài {result_duration}s dù yêu cầu 5s — video ngắn KHÔNG được loop để lấp đủ (bug cũ)"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_segment_recognizes_webm_and_mov_as_video(tmp_path):
    """Bug thật thứ 2 phát hiện cùng lúc: `is_video` trước đây chỉ nhận diện đuôi
    `.mp4` (`visual_path.lower().endswith(".mp4")`), trong khi tính năng upload
    (`render.py::upload_shot_visual`, mục 42) cho phép cả `.webm`/`.mov`. File
    `.webm`/`.mov` bị lọt vào nhánh ẢNH (`-loop 1 -i file.webm`) — sai hoàn toàn với
    file video thật. Verify: dựng file `.webm` thật, xác nhận `_build_segment` xử lý
    đúng nhánh video (loop input, KHÔNG dùng `-loop 1`) bằng cách kiểm tra segment output
    vẫn ra đúng duration yêu cầu dù input `.webm` ngắn hơn (chỉ nhánh video mới loop)."""
    ffmpeg = shutil.which("ffmpeg")
    short_webm = tmp_path / "short.webm"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10", "-c:v", "libvpx-vp9", str(short_webm)],
        capture_output=True, check=True, text=True,
    )
    out_path = tmp_path / "segment_webm.mp4"
    _build_segment(
        ffmpeg, str(short_webm), None, duration=3.0, out_path=out_path,
        resolution="320:240", video_codec="libx264", audio_codec="aac", crf=28, ensure_audio_track=True,
    )
    result_duration = _ffprobe_duration(out_path)
    assert result_duration >= 2.8, f"Segment chỉ dài {result_duration}s — .webm không được nhận diện là video (bug cũ, rơi vào nhánh ảnh)"


def _probe_audio_format(path: Path) -> tuple[int, int]:
    """Trả `(sample_rate, channels)` của stream audio ĐẦU TIÊN — dùng verify chuẩn hoá
    44.1kHz stereo (`_AUDIO_FORMAT_FLAGS`, mục 57 IMPLEMENTATION_REPORT.md)."""
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate,channels", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    sr, ch = out.stdout.strip().split(",")
    return int(sr), int(ch)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_build_segment_normalizes_mismatched_narration_sample_rate(tmp_path):
    """Bug thật người dùng báo (2026-08-21, mục 57): video render "lỗi không ghép được
    giọng đọc" — điều tra thật xác nhận nguyên nhân là narration từ provider OmniVoice
    xuất ra **24kHz MONO** (khác hẳn 44.1kHz STEREO dùng xuyên suốt phần còn lại của
    app), trong khi `_build_segment` trước đây KHÔNG ép sample rate/kênh ở output — cứ
    theo NGUYÊN VẸN định dạng input. Khi 1 segment mang định dạng lệch này sau đó bị
    trộn/ghép (xfade/amix) với segment/nguồn KHÁC chuẩn 44.1kHz stereo, audio bị hỏng
    hoặc MẤT HẲN (xem test end-to-end `test_intro.py::
    test_assemble_intro_fade_transition_preserves_mismatched_rate_narration`).

    Verify: dựng 1 file audio giả lập ĐÚNG định dạng OmniVoice (24kHz mono), truyền vào
    `_build_segment` làm narration — xác nhận OUTPUT LUÔN 44100Hz/2 kênh (chuẩn hoá),
    KHÔNG PHẢI 24000Hz/1 kênh (định dạng input gốc)."""
    ffmpeg = shutil.which("ffmpeg")
    image_src = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(image_src)], capture_output=True, check=True, text=True)

    narration_24k_mono = tmp_path / "narration_omnivoice.wav"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-ar", "24000", "-ac", "1", str(narration_24k_mono)],
        capture_output=True, check=True, text=True,
    )
    sr_in, ch_in = _probe_audio_format(narration_24k_mono)
    assert (sr_in, ch_in) == (24000, 1)  # sanity: input thật đúng định dạng OmniVoice cần tái hiện

    out_path = tmp_path / "segment_out.mp4"
    _build_segment(
        ffmpeg, str(image_src), str(narration_24k_mono), duration=2.0, out_path=out_path,
        resolution="320:240", video_codec="libx264", audio_codec="aac", crf=28,
    )
    sr_out, ch_out = _probe_audio_format(out_path)
    assert (sr_out, ch_out) == (44100, 2), f"Segment giữ NGUYÊN định dạng input ({sr_out}Hz/{ch_out}ch) thay vì chuẩn hoá 44100Hz/2ch — sẽ vỡ khi trộn với segment/nguồn khác chuẩn"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_xfade_chain_handles_mixed_image_and_video_framerates(tmp_path):
    """Bug thật thứ 2 (2026-08-17, mục 43) — phát hiện NGAY SAU khi fix bug loop video ở
    trên, khi thử ghép lại project thật của người dùng qua API: ffmpeg lỗi
    "First input link main timebase (1/12288) do not match the corresponding second
    input link xfade timebase (1/12800)" ở đúng bước `_xfade_chain`. Nguyên nhân đo thật:
    `_build_segment` trước đây KHÔNG ép framerate output — ảnh mặc định ra 25fps, video
    giữ nguyên framerate gốc của file input (project thật: video upload 24fps) → 2
    segment khác nguồn (1 từ ảnh AI sinh, 1 từ video upload) ra 2 timebase khác nhau,
    `xfade` KHÔNG chấp nhận chain 2 input lệch timebase.

    Verify bằng ffmpeg THẬT, tái hiện đúng kịch bản lỗi: 1 run dựng từ ẢNH (mặc định
    25fps), 1 run dựng từ VIDEO 24fps thật (khác hẳn 25fps) — trước fix, gọi
    `_xfade_chain` nối 2 run này sẽ CalledProcessError đúng lỗi timebase trên. Sau fix
    (ép `fps={_OUTPUT_FPS}` ở MỌI segment), ghép thành công, file output thật sự tồn
    tại và có cả 2 stream video+audio."""
    ffmpeg = shutil.which("ffmpeg")

    image_src = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", str(image_src)], capture_output=True, check=True, text=True)
    video_src = tmp_path / "src24fps.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=24", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_src)],
        capture_output=True, check=True, text=True,
    )

    run_image = tmp_path / "run_image.mp4"
    _build_segment(ffmpeg, str(image_src), None, duration=3.0, out_path=run_image, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=28, ensure_audio_track=True)
    run_video = tmp_path / "run_video.mp4"
    _build_segment(ffmpeg, str(video_src), None, duration=3.0, out_path=run_video, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=28, ensure_audio_track=True)

    out_path = tmp_path / "xfade_out.mp4"
    _xfade_chain(ffmpeg, [run_image, run_video], [3.0, 3.0], ["fade"], out_path, video_codec="libx264", audio_codec="aac", crf=28)

    assert out_path.exists() and out_path.stat().st_size > 0
    probe = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out_path)],
        capture_output=True, check=True, text=True,
    )
    kinds = probe.stdout.split()
    assert "video" in kinds and "audio" in kinds


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_xfade_chain_merges_incrementally_and_cleans_up_intermediates(tmp_path):
    """Bug thật (2026-08-17, mục 43, tiếp theo) — bản 1-lệnh-duy-nhất (mở TẤT CẢ input
    cùng lúc trong 1 filter_complex) làm ffmpeg lỗi thật "Cannot allocate memory" trên
    project 31 shot/12+ phút/nhiều transition của người dùng — tái hiện y hệt 2 lần liên
    tiếp qua API thật, luôn đúng cùng 1 frame cuối. Fix: ghép TUẦN TỰ từng cặp (mỗi lệnh
    ffmpeg chỉ mở 2 input) thay vì 1 lệnh khổng lồ.

    Verify với 3 run (bắt buộc >2 để thật sự exercise nhánh tạo file trung gian
    `_xstepNN` + dọn dẹp — test 2-run ở trên không đi qua nhánh này): ghép xong đúng,
    VÀ file trung gian phải bị XOÁ sau khi hoàn tất (không để rác trong thư mục
    renders/)."""
    ffmpeg = shutil.which("ffmpeg")
    runs = []
    for i, color in enumerate(["red", "green", "blue"]):
        p = tmp_path / f"run{i}.mp4"
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d=2", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
             "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)],
            capture_output=True, check=True, text=True,
        )
        runs.append(p)

    out_path = tmp_path / "final.mp4"
    _xfade_chain(ffmpeg, runs, [2.0, 2.0, 2.0], ["fade", "wipeleft"], out_path, video_codec="libx264", audio_codec="aac", crf=28)

    assert out_path.exists() and out_path.stat().st_size > 0
    # File trung gian (`_xstepNN` VÀ `_xheadNN`/`_xblendNN` mới thêm — xem docstring
    # `_xfade_chain`) phải bị dọn hết — không còn sót trên đĩa.
    leftover = list(tmp_path.glob("final_xstep*.mp4")) + list(tmp_path.glob("final_xhead*.mp4")) + list(tmp_path.glob("final_xblend*.mp4"))
    assert leftover == [], f"Còn sót file trung gian chưa dọn: {leftover}"
    result_duration = _ffprobe_duration(out_path)
    # 3 run 2s ghép bằng 2 xfade (mỗi lần chồng lấn ~0.6s) → ngắn hơn tổng thô 6s, dài hơn 1 run đơn.
    assert 3.0 < result_duration < 6.0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_xfade_chain_bounds_cost_by_trimming_accumulator_not_reprocessing_whole_video(tmp_path):
    """Bug thật TIẾP THEO (2026-08-17, cùng ngày) — sau khi người dùng đổi HẾT video
    sang ẢNH TĨNH (loại trừ được bug reflow mục 45), vẫn gặp lại y hệt lỗi ffmpeg
    "Cannot allocate memory" (-12) ở bước ghép cuối cùng của 1 chain xfade dài (~13 phút
    38s, log thật gửi kèm báo lỗi). Nguyên nhân thật: `xfade` decode+re-encode LẠI TOÀN
    BỘ input0 mỗi lần gọi (không chỉ đúng đoạn overlap) — dù mỗi lệnh chỉ mở 2 input
    (fix trước, mục 43), `current_path` (bên tích luỹ) vẫn phình dần qua từng vòng lặp,
    khiến lệnh CUỐI phải xử lý gần hết video. Fix: cắt `current_path` làm 2 (head giữ
    nguyên, stream-copy KHÔNG decode; chỉ đúng `t` giây đuôi mới decode qua xfade) TRƯỚC
    khi gọi xfade — chi phí decode+encode mỗi bước giờ chỉ còn ~`t` giây, không còn phụ
    thuộc `current_path` đã tích luỹ bao lâu.

    Verify GIÁN TIẾP (không đo được RAM/CPU thật trong unit test, không mô phỏng được 1
    video 13 phút rẻ tiền trong CI): ghép chain DÀI HƠN hẳn (6 run, không phải 2-3 như
    test trên) để `current_path` thật sự tích luỹ qua NHIỀU thế hệ — nếu logic cắt
    head/blend sai (lệch offset, trùng/thiếu frame ở ranh giới cắt), sai số sẽ CỘNG DỒN
    rõ rệt theo số run, lộ ra ở duration cuối cùng thay vì chỉ lệch nhẹ như test 2-3 run
    có thể che giấu. Xác nhận: ghép xong đúng, dọn sạch mọi file trung gian, tổng
    duration nằm trong dải hợp lý (tổng thô trừ hết overlap lý thuyết .. tổng thô)."""
    ffmpeg = shutil.which("ffmpeg")
    n_runs = 6
    run_len = 2.0
    colors = ["red", "green", "blue", "yellow", "white", "black"]
    runs = []
    for i in range(n_runs):
        p = tmp_path / f"run{i}.mp4"
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={colors[i]}:s=320x240:d={run_len}", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
             "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)],
            capture_output=True, check=True, text=True,
        )
        runs.append(p)

    out_path = tmp_path / "final6.mp4"
    durations = [run_len] * n_runs
    transitions = ["fade"] * (n_runs - 1)
    _xfade_chain(ffmpeg, runs, durations, transitions, out_path, video_codec="libx264", audio_codec="aac", crf=28)

    assert out_path.exists() and out_path.stat().st_size > 0
    leftover = list(tmp_path.glob("final6_xstep*.mp4")) + list(tmp_path.glob("final6_xhead*.mp4")) + list(tmp_path.glob("final6_xblend*.mp4"))
    assert leftover == [], f"Còn sót file trung gian chưa dọn: {leftover}"

    result_duration = _ffprobe_duration(out_path)
    raw_total = n_runs * run_len
    max_overlap = (n_runs - 1) * _XFADE_DURATION_SEC
    lo, hi = raw_total - max_overlap - 0.5, raw_total + 0.5
    assert lo < result_duration < hi, (
        f"Tổng duration {result_duration}s lệch bất thường so với dải hợp lý ({lo}..{hi}) "
        "— nghi ngờ lỗi cắt head/blend tích luỹ qua nhiều bước."
    )


# ---------------------------------------------------------------------------
# Duration reflow (2026-08-17) — theo yêu cầu người dùng: video upload/AI sinh lệch độ
# dài thật so với slot quy định (thường gặp nhất khi upload tay) không còn bị loop/cắt
# cứng (mục 43) — thay vào đó PHÁT ĐỦ độ dài thật, bù/trừ chênh lệch qua shot liền kề.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_reflow_borrows_from_next_shot_when_video_shorter_than_slot(tmp_path):
    from app.render.assembly import _reflow_video_durations
    from app.render.schemas import ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    short_video = tmp_path / "short.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(short_video)],
        capture_output=True, check=True, text=True,
    )
    actual = _ffprobe_duration(short_video)
    assert round(actual) == 2

    # s1 (ảnh, path=None nên bị bỏ qua an toàn), s2 (video ngắn hơn slot), s3 (ảnh)
    statuses = [
        ShotRenderStatus(shot_id="s1", visual_asset_path=None),
        ShotRenderStatus(shot_id="s2", visual_asset_path=str(short_video)),
        ShotRenderStatus(shot_id="s3", visual_asset_path=None),
    ]
    durations = [3.0, 5.0, 3.0]
    _reflow_video_durations(statuses, durations)

    assert durations[1] == pytest.approx(actual, abs=0.05)  # s2 phát đúng độ dài thật, không loop
    assert durations[2] == pytest.approx(3.0 + (5.0 - actual), abs=0.05)  # s3 (shot SAU) nhận phần thiếu
    assert durations[0] == 3.0  # shot TRƯỚC không bị đụng tới khi có shot sau để bù


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_reflow_borrows_from_previous_shot_when_last_shot_video_shorter(tmp_path):
    """Video ngắn nằm ở shot CUỐI CÙNG (không có shot sau) — phải bù từ shot TRƯỚC."""
    from app.render.assembly import _reflow_video_durations
    from app.render.schemas import ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    short_video = tmp_path / "short_last.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(short_video)],
        capture_output=True, check=True, text=True,
    )
    actual = _ffprobe_duration(short_video)

    statuses = [
        ShotRenderStatus(shot_id="s1", visual_asset_path=None),
        ShotRenderStatus(shot_id="s2", visual_asset_path=str(short_video)),
    ]
    durations = [4.0, 5.0]
    _reflow_video_durations(statuses, durations)

    assert durations[1] == pytest.approx(actual, abs=0.05)
    assert durations[0] == pytest.approx(4.0 + (5.0 - actual), abs=0.05)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_reflow_shortens_next_shot_when_video_longer_than_slot(tmp_path):
    """Video THẬT dài hơn slot quy định — KHÔNG cắt video (khác `-t duration` cũ), phát
    đủ, co ngắn thời lượng hiển thị ảnh của shot SAU để bù."""
    from app.render.assembly import _reflow_video_durations
    from app.render.schemas import ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    long_video = tmp_path / "long.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(long_video)],
        capture_output=True, check=True, text=True,
    )
    actual = _ffprobe_duration(long_video)
    assert round(actual) == 5

    statuses = [
        ShotRenderStatus(shot_id="s1", visual_asset_path=str(long_video)),
        ShotRenderStatus(shot_id="s2", visual_asset_path=None),
    ]
    durations = [2.0, 6.0]
    _reflow_video_durations(statuses, durations)

    assert durations[0] == pytest.approx(actual, abs=0.05)
    assert durations[1] == pytest.approx(6.0 - (actual - 2.0), abs=0.05)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_reflow_clamps_donor_at_minimum_duration_floor(tmp_path):
    """Chênh lệch quá lớn so với ngân sách của shot liền kề — không để shot đó bị co về
    gần 0s/âm (ffmpeg xử lý segment gần-0s không ổn định), chặn ở sàn `_MIN_DONOR_DURATION_SEC`."""
    from app.render.assembly import _MIN_DONOR_DURATION_SEC, _reflow_video_durations
    from app.render.schemas import ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    very_long_video = tmp_path / "very_long.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=10:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(very_long_video)],
        capture_output=True, check=True, text=True,
    )
    statuses = [
        ShotRenderStatus(shot_id="s1", visual_asset_path=str(very_long_video)),
        ShotRenderStatus(shot_id="s2", visual_asset_path=None),
    ]
    durations = [2.0, 1.0]  # shot sau chỉ có 1s ngân sách, chênh lệch cần bù ~8s
    _reflow_video_durations(statuses, durations)
    assert durations[1] == pytest.approx(_MIN_DONOR_DURATION_SEC, abs=0.01)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_reflow_skips_when_only_one_shot_no_donor_available(tmp_path):
    """Chỉ có 1 shot duy nhất — không có ai để vay/trả, giữ nguyên `durations` để
    `_build_segment` tự loop/cắt như lưới an toàn cũ (mục 43)."""
    from app.render.assembly import _reflow_video_durations
    from app.render.schemas import ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    short_video = tmp_path / "solo.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(short_video)],
        capture_output=True, check=True, text=True,
    )
    statuses = [ShotRenderStatus(shot_id="s1", visual_asset_path=str(short_video))]
    durations = [5.0]
    _reflow_video_durations(statuses, durations)
    assert durations[0] == 5.0


# ---------------------------------------------------------------------------
# Camera motion (Ken Burns) cho ảnh tĩnh — 2026-08-19, theo yêu cầu người dùng.
# ---------------------------------------------------------------------------
def test_build_camera_motion_filter_none_and_invalid_return_none():
    from app.render.camera_motion import build_camera_motion_filter

    assert build_camera_motion_filter("none", 3.0, 640, 480, 25) is None
    assert build_camera_motion_filter("khong-ton-tai", 3.0, 640, 480, 25) is None


def test_build_camera_motion_filter_covers_every_real_motion():
    """Mỗi key trong CAMERA_MOTIONS (trừ "none") phải build được filter string hợp lệ —
    bắt lỗi gõ sai biến/cú pháp trong biểu thức ffmpeg ở TỪNG nhánh, không cần chạy
    ffmpeg thật (nhanh, chạy mọi lần commit)."""
    from app.render.camera_motion import CAMERA_MOTIONS, build_camera_motion_filter

    for motion in CAMERA_MOTIONS:
        if motion == "none":
            continue
        result = build_camera_motion_filter(motion, 3.0, 1920, 1080, 30)
        assert isinstance(result, str) and result, f"motion={motion} không trả filter hợp lệ"
        assert "1920x1080" in result or "1920:1080" in result


def _corner_test_image(ffmpeg: str, path: Path) -> None:
    """Ảnh test 640x480: 4 ô màu ở góc + 1 ô đen giữa — dùng để xác nhận HƯỚNG chuyển
    động thật (không chỉ "chạy không lỗi") bằng cách lấy mẫu màu pixel tại toạ độ biết
    trước, TRƯỚC/SAU hiệu ứng."""
    base = path.with_name(f"{path.stem}_base{path.suffix}")
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=white:s=640x480", "-frames:v", "1", "-update", "1", str(base)], capture_output=True, check=True, text=True)
    subprocess.run(
        [ffmpeg, "-y", "-i", str(base), "-vf",
         "drawbox=x=0:y=0:w=100:h=100:color=red@1:t=fill,"
         "drawbox=x=540:y=0:w=100:h=100:color=green@1:t=fill,"
         "drawbox=x=0:y=380:w=100:h=100:color=blue@1:t=fill,"
         "drawbox=x=540:y=380:w=100:h=100:color=yellow@1:t=fill,"
         "drawbox=x=280:y=200:w=80:h=80:color=black@1:t=fill",
         "-frames:v", "1", "-update", "1", str(path)],
        capture_output=True, check=True, text=True,
    )


def _pixel_rgb(ffmpeg: str, path: Path, x: int, y: int) -> tuple[int, int, int]:
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(path), "-vf", f"crop=1:1:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-frames:v", "1", "-"],
        capture_output=True, check=True,
    )
    data = result.stdout
    return data[0], data[1], data[2]


def _approx_rgb(actual: tuple[int, int, int], expected: tuple[int, int, int], tol: int = 12) -> bool:
    """So màu XẤP XỈ — nén H.264 (kể cả CRF thấp) làm lệch nhẹ giá trị kênh màu 1-2 đơn
    vị so với màu vẽ gốc, so bằng tuyệt đối sẽ flake giả (đã gặp thật: 127 != 128)."""
    return all(abs(a - e) <= tol for a, e in zip(actual, expected))


def _extract_frame(ffmpeg: str, video_path: Path, out_path: Path, *, at_end: bool = False) -> None:
    if at_end:
        subprocess.run([ffmpeg, "-y", "-sseof", "-0.12", "-i", str(video_path), "-vframes", "1", "-update", "1", str(out_path)], capture_output=True, check=True, text=True)
    else:
        subprocess.run([ffmpeg, "-y", "-i", str(video_path), "-vf", "select=eq(n\\,0)", "-vframes", "1", "-update", "1", str(out_path)], capture_output=True, check=True, text=True)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_camera_motion_zoom_in_makes_corner_content_disappear(tmp_path):
    """Verify THẬT bằng lấy mẫu pixel (không chỉ "chạy không lỗi"): zoom_in phải zoom
    CENTERED — pixel ở góc trên-trái (trong ô đỏ lúc chưa zoom) phải KHÔNG còn đỏ ở
    frame cuối (đã zoom ra khỏi khung nhìn), còn tâm khung (ô đen) vẫn đứng yên."""
    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "test.png"
    _corner_test_image(ffmpeg, src)

    out_path = tmp_path / "zoom_in.mp4"
    _build_segment(
        ffmpeg, str(src), None, duration=2.0, out_path=out_path,
        resolution="640:480", video_codec="libx264", audio_codec="aac", crf=28, camera_motion="zoom_in",
    )
    first, last = tmp_path / "f0.png", tmp_path / "f1.png"
    _extract_frame(ffmpeg, out_path, first)
    _extract_frame(ffmpeg, out_path, last, at_end=True)

    # Điểm (90,90): ở zoom=1.0 map thẳng về chính nó (90,90) — vẫn TRONG ô đỏ 100x100.
    # Ở zoom=1.18 (centered), map về source (320+(90-320)/1.18, ...) ≈ (125,125) — đã
    # RA NGOÀI ô đỏ (>100). Tính tay theo đúng công thức x/y centered zoompan dùng.
    assert _approx_rgb(_pixel_rgb(ffmpeg, first, 90, 90), (255, 0, 0)), "Frame đầu: (90,90) phải còn đỏ (chưa zoom)"
    assert not _approx_rgb(_pixel_rgb(ffmpeg, last, 90, 90), (255, 0, 0)), "Frame cuối: (90,90) vẫn đỏ — zoom_in không zoom vào giữa như kỳ vọng"
    # Tâm khung (ô đen) phải LỚN HƠN — pixel cách tâm ~45px (ngoài ô đen 40px lúc chưa
    # zoom, nhưng lọt vào trong sau khi zoom 1.18x) phải chuyển từ trắng sang đen.
    assert _approx_rgb(_pixel_rgb(ffmpeg, first, 365, 240), (255, 255, 255))
    assert _approx_rgb(_pixel_rgb(ffmpeg, last, 365, 240), (0, 0, 0))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_camera_motion_pan_left_shifts_view_from_right_to_left(tmp_path):
    """pan_left: khung nhìn BẮT ĐẦU lệch phải (thấy góc xanh lá/vàng bên phải rõ hơn),
    KẾT THÚC lệch trái (thấy góc đỏ/xanh dương bên trái rõ hơn)."""
    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "test.png"
    _corner_test_image(ffmpeg, src)

    out_path = tmp_path / "pan_left.mp4"
    _build_segment(
        ffmpeg, str(src), None, duration=2.0, out_path=out_path,
        resolution="640:480", video_codec="libx264", audio_codec="aac", crf=28, camera_motion="pan_left",
    )
    first, last = tmp_path / "f0.png", tmp_path / "f1.png"
    _extract_frame(ffmpeg, out_path, first)
    _extract_frame(ffmpeg, out_path, last, at_end=True)

    # Frame đầu: góc PHẢI (xanh lá) còn thấy rõ, góc TRÁI (đỏ) gần như mất hẳn.
    assert _approx_rgb(_pixel_rgb(ffmpeg, first, 620, 10), (0, 128, 0))
    assert not _approx_rgb(_pixel_rgb(ffmpeg, first, 10, 10), (255, 0, 0))
    # Frame cuối: đảo ngược — góc TRÁI (đỏ) thấy rõ, góc PHẢI (xanh lá) gần như mất hẳn.
    assert _approx_rgb(_pixel_rgb(ffmpeg, last, 10, 10), (255, 0, 0))
    assert not _approx_rgb(_pixel_rgb(ffmpeg, last, 620, 10), (0, 128, 0))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_camera_motion_pan_eases_in_and_out_instead_of_constant_velocity(tmp_path):
    """Bug thật người dùng báo (2026-08-20): hiệu ứng camera "hơi bị giật". Đo thật
    bằng ảnh gradient ngang (đen→trắng) + lấy mẫu 1 pixel cố định tại nhiều điểm dọc
    clip (không đoán): chuyển động TUYẾN TÍNH (vận tốc không đổi, bản trước fix) khởi
    động/dừng ĐỘT NGỘT ở 2 đầu clip — camera thật không bao giờ bắt đầu/dừng tức thời.
    Fix: smoothstep easing (`camera_motion._eased_progress`). Verify: "vận tốc" (chênh
    lệch mức xám giữa 2 mốc frame CÙNG khoảng cách) ở gần GIỮA clip phải lớn hơn RÕ RỆT
    vận tốc gần 2 ĐẦU clip — đúng dáng ease-in/ease-out, khác dáng tuyến tính đều (mọi
    vận tốc bằng nhau) mà bản trước fix từng có (đã tự đo thật trước khi sửa)."""
    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "gradient.png"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=640x480", "-vf", "geq=lum='255*X/W':cb=128:cr=128", "-frames:v", "1", "-update", "1", str(src)],
        capture_output=True, check=True, text=True,
    )
    out_path = tmp_path / "pan_ease.mp4"
    _build_segment(
        ffmpeg, str(src), None, duration=2.0, out_path=out_path,
        resolution="640:480", video_codec="libx264", audio_codec="aac", crf=18, camera_motion="pan_left",
    )

    def gray_at_frame(n: int) -> int:
        frame = tmp_path / f"pf{n}.png"
        subprocess.run([ffmpeg, "-y", "-i", str(out_path), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", "-update", "1", str(frame)], capture_output=True, check=True, text=True)
        return _pixel_rgb(ffmpeg, frame, 320, 240)[0]

    total = 60  # 2.0s * _OUTPUT_FPS(30)
    # Cửa sổ 8 frame ở mỗi vùng — đủ rộng để trung bình hoá nhiễu làm tròn per-frame
    # (đã gặp thật: nén H.264 lệch 1-2 mức xám/frame), vẫn đủ hẹp để phân biệt vùng.
    start_speed = abs(gray_at_frame(8) - gray_at_frame(0))
    mid_speed = abs(gray_at_frame(34) - gray_at_frame(26))
    end_speed = abs(gray_at_frame(59) - gray_at_frame(51))

    assert mid_speed > start_speed, f"Vận tốc giữa clip ({mid_speed}) không nhanh hơn đầu clip ({start_speed}) — thiếu ease-in, có thể đã regress về tuyến tính đều"
    assert mid_speed > end_speed, f"Vận tốc giữa clip ({mid_speed}) không nhanh hơn cuối clip ({end_speed}) — thiếu ease-out, có thể đã regress về tuyến tính đều"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_camera_motion_roll_rotates_without_black_corners(tmp_path):
    """Bug thật phát hiện lúc phát triển (xem docstring `camera_motion.py`): đặt `rotate`
    (time-varying) TRƯỚC `zoompan` bị zoompan "đóng băng" tại t≈0 — clip ra KHÔNG xoay
    dù công thức đúng. Verify: (1) pixel gần góc khung KHÔNG bao giờ đen tuyền (không
    lộ góc ảnh bị rotate, đã crop che đủ), (2) SO SÁNH pixel gần rìa dọc giữa 2 frame xa
    nhau trong clip — phải có ít nhất 1 pixel đổi màu đáng kể (bằng chứng ảnh THẬT SỰ
    xoay qua lại, không đứng yên như bug đã gặp)."""
    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "test.png"
    _corner_test_image(ffmpeg, src)

    out_path = tmp_path / "roll.mp4"
    _build_segment(
        ffmpeg, str(src), None, duration=2.0, out_path=out_path,
        resolution="640:480", video_codec="libx264", audio_codec="aac", crf=28, camera_motion="roll",
    )
    first = tmp_path / "f0.png"
    mid = tmp_path / "fmid.png"
    _extract_frame(ffmpeg, out_path, first)
    subprocess.run([ffmpeg, "-y", "-ss", "0.5", "-i", str(out_path), "-vframes", "1", "-update", "1", str(mid)], capture_output=True, check=True, text=True)

    # Không lộ góc đen ở 4 góc khung (crop margin đủ che rotate ±3°).
    for x, y in ((2, 2), (637, 2), (2, 477), (637, 477)):
        assert _pixel_rgb(ffmpeg, first, x, y) != (0, 0, 0), f"Lộ góc đen tại ({x},{y}) — crop margin không đủ che rotate"

    # Bằng chứng THẬT có xoay: lấy mẫu dọc theo cạnh TRÊN (nơi rotate dịch chuyển rõ
    # nhất) — ít nhất 1 điểm phải đổi màu giữa frame đầu (t≈0, góc≈0°) và frame giữa
    # (t=0.5s, góc≈max theo sin) — nếu KHÔNG đổi màu ở bất kỳ điểm nào, nghĩa là ảnh
    # đứng yên (đúng bug đã phát hiện, PHẢI fail để bắt regression).
    changed = any(_pixel_rgb(ffmpeg, first, x, 8) != _pixel_rgb(ffmpeg, mid, x, 8) for x in range(0, 640, 8))
    assert changed, "Không pixel nào đổi màu giữa frame đầu và giữa — roll KHÔNG xoay thật (regression của bug zoompan đóng băng upstream)"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_camera_motion_not_applied_to_video_shots(tmp_path):
    """`camera_motion` CHỈ áp dụng cho shot ẢNH — 1 shot VIDEO với `camera_motion="zoom_in"`
    phải ra kết quả GIỐNG HỆT như khi `camera_motion="none"` (video giữ nguyên chuyển
    động thật của nó, không bị Ken Burns đè lên)."""
    ffmpeg = shutil.which("ffmpeg")
    video_src = tmp_path / "src.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=640x480:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_src)],
        capture_output=True, check=True, text=True,
    )
    out_none = tmp_path / "out_none.mp4"
    out_zoom = tmp_path / "out_zoom.mp4"
    _build_segment(ffmpeg, str(video_src), None, duration=2.0, out_path=out_none, resolution="640:480", video_codec="libx264", audio_codec="aac", crf=28, camera_motion="none")
    _build_segment(ffmpeg, str(video_src), None, duration=2.0, out_path=out_zoom, resolution="640:480", video_codec="libx264", audio_codec="aac", crf=28, camera_motion="zoom_in")

    assert out_none.stat().st_size == out_zoom.stat().st_size, "Kích thước file khác nhau — camera_motion có vẻ vẫn bị áp cho shot video"
    assert _ffprobe_duration(out_none) == pytest.approx(_ffprobe_duration(out_zoom), abs=0.05)


def test_patch_shot_rejects_invalid_camera_motion(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    shot_id = pack["shots"][0]["shot_id"]

    resp = client.patch(f"/projects/{pid}/visual/shots/{shot_id}", json={"camera_motion": "khong-ton-tai"})
    assert resp.status_code == 400

    resp = client.patch(f"/projects/{pid}/visual/shots/{shot_id}", json={"camera_motion": "zoom_in"})
    assert resp.status_code == 200
    patched_shot = next(s for s in resp.json()["shots"] if s["shot_id"] == shot_id)
    assert patched_shot["camera_motion"] == "zoom_in"


# ---------------------------------------------------------------------------
# Fallback provider (đợt 2) — is_fallback trước đây chỉ là cờ DB không ai đọc.
# ---------------------------------------------------------------------------
GEMINI_GENERATE_RE = r"https://generativelanguage\.googleapis\.com/v1beta/models/.*:generateContent.*"


@respx.mock
def test_image_fallback_used_when_default_fails(client, project_with_brief):
    """Provider mặc định (OpenAI, key sai -> 401) thất bại -> tự động thử provider
    fallback (Gemini) -> shot vẫn `ready`, `visual_provider` phải là "gemini" (không
    phải "openai") -> xác nhận is_fallback THẬT SỰ được dùng, không chỉ lưu DB."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    default_img = client.post("/providers", json={"task": "image", "provider_name": "openai", "display_name": "OAI (key sai)", "connection_type": "cloud_api", "api_key": "sk-bad"}).json()
    client.patch(f"/providers/{default_img['id']}", json={"is_default": True})
    fallback_img = client.post("/providers", json={"task": "image", "provider_name": "gemini", "display_name": "Gemini (fallback)", "connection_type": "cloud_api", "api_key": "sk-good"}).json()
    client.patch(f"/providers/{fallback_img['id']}", json={"is_fallback": True})
    tts = client.post("/providers", json={"task": "tts", "provider_name": "elevenlabs", "display_name": "EL", "connection_type": "cloud_api", "api_key": "sk-el"}).json()
    client.patch(f"/providers/{tts['id']}", json={"is_default": True})

    respx.post("https://api.openai.com/v1/images/generations").mock(return_value=Response(401, json={"error": {"message": "bad key"}}))
    respx.post(url__regex=GEMINI_GENERATE_RE).mock(
        return_value=Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(FAKE_PNG).decode(), "mimeType": "image/png"}}]}}]})
    )
    respx.post("https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM").mock(return_value=Response(200, content=FAKE_MP3))

    resp = client.post(f"/projects/{pid}/render/start")
    assert resp.status_code == 200
    state = client.get(f"/projects/{pid}/render/status").json()
    pack = client.get(f"/projects/{pid}/pack").json()
    image_shot_ids = {s["shot_id"] for s in pack["shots"] if s["visual_type"] == "image"}
    image_states = [s for s in state["shots"] if s["shot_id"] in image_shot_ids]
    assert image_states, "cần ít nhất 1 shot ảnh để test có ý nghĩa"
    for s in image_states:
        assert s["visual_status"] == "ready", s
        assert s["visual_provider"] == "gemini"  # fallback được dùng, KHÔNG phải default (openai) đã lỗi


@respx.mock
def test_local_sdxl_generation_uses_style_lora_from_brand_profile(client, project_with_brief):
    """Đợt 2 (style checkpoint painterly) end-to-end: BrandProfile.style_lora_path PHẢI
    tới được đúng request ComfyUI thật cho `local_sdxl` — không chỉ đúng ở tầng
    ComfySDXLImageProvider đơn lẻ (đã test riêng ở test_image_comfy_sdxl.py) mà còn đúng
    ở tầng engine.py::generate_visual_asset đọc brand + truyền qua provider.generate()."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    channel_id = project_with_brief["channel_id"]

    profile = client.get(f"/channels/{channel_id}/brandprofile").json()
    profile["style_lora_path"] = "InkArtXL_1.2.safetensors"
    profile["style_lora_strength"] = 0.9
    client.put(f"/channels/{channel_id}/brandprofile", json=profile)

    image = client.post("/providers", json={"task": "image", "provider_name": "local_sdxl", "display_name": "SDXL local", "connection_type": "local_endpoint", "endpoint_url": "http://127.0.0.1:8188"}).json()
    client.patch(f"/providers/{image['id']}", json={"is_default": True})
    tts = client.post("/providers", json={"task": "tts", "provider_name": "elevenlabs", "display_name": "EL", "connection_type": "cloud_api", "api_key": "sk-el"}).json()
    client.patch(f"/providers/{tts['id']}", json={"is_default": True})

    respx.post("https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM").mock(return_value=Response(200, content=FAKE_MP3))
    submit_route = respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(200, json={"prompt_id": "job-1"}))
    respx.get("http://127.0.0.1:8188/history/job-1").mock(
        return_value=Response(200, json={"job-1": {"outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}})
    )
    respx.get("http://127.0.0.1:8188/view").mock(return_value=Response(200, content=FAKE_PNG))

    resp = client.post(f"/projects/{pid}/render/start")
    assert resp.status_code == 200

    sent_bodies = [json.loads(c.request.content) for c in submit_route.calls]
    assert sent_bodies, "phải có ít nhất 1 request sinh ảnh gửi tới ComfyUI"
    for body in sent_bodies:
        workflow = body["prompt"]
        assert workflow["13"]["inputs"]["lora_name"] == "InkArtXL_1.2.safetensors"
        assert workflow["13"]["inputs"]["strength_model"] == 0.9


# ---------------------------------------------------------------------------
# Gemini TTS / Gemini Image / Google Veo — adapter mới (đợt 2)
# ---------------------------------------------------------------------------
def test_gemini_tts_wraps_pcm_as_wav():
    from app.providers.tts_gemini import GeminiTTSProvider

    pcm = b"\x00\x01" * 100
    with respx.mock:
        respx.post(url__regex=GEMINI_GENERATE_RE).mock(
            return_value=Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm).decode(), "mimeType": "audio/L16;rate=24000"}}]}}]})
        )
        data = GeminiTTSProvider(api_key="sk-test").synthesize("xin chào")
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"
    assert pcm in data


def test_gemini_image_decodes_base64():
    from app.providers.image_gemini import GeminiImageProvider

    with respx.mock:
        respx.post(url__regex=GEMINI_GENERATE_RE).mock(
            return_value=Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(FAKE_PNG).decode(), "mimeType": "image/png"}}]}}]})
        )
        data = GeminiImageProvider(api_key="sk-test").generate("a cat")
    assert data == FAKE_PNG


def test_veo_start_and_poll_downloads_video():
    from app.providers.video_veo import VeoVideoProvider

    with respx.mock:
        respx.post(url__regex=r".*:predictLongRunning.*").mock(return_value=Response(200, json={"name": "operations/abc123"}))
        respx.get(url__regex=r"https://generativelanguage\.googleapis\.com/v1beta/operations/abc123.*").mock(
            return_value=Response(200, json={"done": True, "response": {"generateVideoResponse": {"generatedSamples": [{"video": {"uri": "https://example.com/video.mp4"}}]}}})
        )
        respx.get(url__regex=r"https://example\.com/video\.mp4.*").mock(return_value=Response(200, content=FAKE_MP4))

        provider = VeoVideoProvider(api_key="sk-test")
        job_id = provider.start_generation("a dog running")
        status, data = provider.poll_generation(job_id)
    assert job_id == "operations/abc123"
    assert status == "completed"
    assert data == FAKE_MP4


def test_veo_poll_not_done_returns_no_bytes():
    from app.providers.video_veo import VeoVideoProvider

    with respx.mock:
        respx.get(url__regex=r"https://generativelanguage\.googleapis\.com/v1beta/operations/xyz.*").mock(return_value=Response(200, json={"done": False}))
        status, data = VeoVideoProvider(api_key="sk-test").poll_generation("operations/xyz")
    assert status == "processing"
    assert data is None


def test_probe_audio_duration_invalid_file_returns_none(tmp_path):
    """File không phải audio thật (VD FAKE_MP3 dùng trong test khác) — ffprobe (nếu có
    cài) sẽ lỗi parse, hàm phải trả None thay vì raise, không được chặn việc lưu
    narration_asset_path/ready ở generate_narration_asset()."""
    from app.render.engine import _probe_audio_duration_sec

    fake = tmp_path / "fake.mp3"
    fake.write_bytes(FAKE_MP3)
    assert _probe_audio_duration_sec(fake) is None


def test_probe_audio_duration_missing_ffprobe_returns_none(tmp_path, monkeypatch):
    from app.render import engine

    monkeypatch.setattr(engine.shutil, "which", lambda name: None)
    fake = tmp_path / "fake.wav"
    fake.write_bytes(FAKE_WAV)
    assert engine._probe_audio_duration_sec(fake) is None


# ---------------------------------------------------------------------------
# _build_visual_prompt(for_local_sdxl=...) / _strip_text_overlay_tags — mới (2026-08-22),
# theo yêu cầu người dùng "cải thiện chất lượng ảnh model local" — xem
# IMPLEMENTATION_REPORT.md.
# ---------------------------------------------------------------------------
def test_strip_text_overlay_tags_removes_graphic_tag_but_keeps_visual_scene():
    """Đúng cấu trúc THẬT quan sát được trong pack.json: `[Visual]:` mang nội dung cảnh
    (PHẢI giữ), tag khác (`[Graphic]`, `[Title Card]`, ...) mang chữ cần vẽ lên ảnh
    (PHẢI xoá cả tag lẫn nội dung)."""
    from app.render.engine import _strip_text_overlay_tags

    raw = '[Visual]: Cận cảnh mặt sông tối đen, ánh đuốc lập lòe. [Graphic]: Dòng chữ nổi lên: "2 vạn quân."'
    result = _strip_text_overlay_tags(raw)
    assert "[Graphic]" not in result
    assert "[Visual]" not in result
    assert "2 vạn quân" not in result
    assert "Cận cảnh mặt sông tối đen, ánh đuốc lập lòe" in result


def test_strip_text_overlay_tags_handles_repeated_visual_tag():
    """1 số shot có `[Visual]:` lặp 2 lần (2 nhịp camera trong cùng shot, xác nhận thật
    qua pack.json) — cả 2 đoạn cảnh đều phải được giữ lại."""
    from app.render.engine import _strip_text_overlay_tags

    raw = "[Visual]: Cảnh mở đầu yên tĩnh. [Visual]: Camera lia nhanh sang cảnh chiến trận."
    result = _strip_text_overlay_tags(raw)
    assert "[Visual]" not in result
    assert "Cảnh mở đầu yên tĩnh" in result
    assert "Camera lia nhanh sang cảnh chiến trận" in result


def test_strip_text_overlay_tags_keeps_plain_scene_description():
    from app.render.engine import _strip_text_overlay_tags

    raw = "Cận cảnh mặt sông tối đen, ánh đuốc lập lòe phản chiếu trên nước."
    assert _strip_text_overlay_tags(raw) == raw


def test_strip_text_overlay_tags_no_tags_is_noop():
    from app.render.engine import _strip_text_overlay_tags

    assert _strip_text_overlay_tags("") == ""


def test_build_visual_prompt_cloud_unchanged_keeps_text_overlay_tags():
    """Nhánh mặc định (for_local_sdxl=False, dùng cho Gemini/OpenAI/Flux) PHẢI giữ
    nguyên hành vi cũ — không lọc tag, nối bằng ". "."""
    from app.render.engine import _build_visual_prompt

    shot = {"visual_fx": '[Title Card]: TRẬN RẠCH GẦM 1785'}
    brand = {"visual_style_prompt": "archival tone, muted sepia"}
    result = _build_visual_prompt(shot, brand, is_video=False)
    assert "[Title Card]" in result
    assert result == '[Title Card]: TRẬN RẠCH GẦM 1785. Style hình ảnh kênh: archival tone, muted sepia'


def test_build_visual_prompt_local_sdxl_strips_tags_and_uses_comma_style():
    from app.render.engine import _build_visual_prompt

    shot = {"visual_fx": "Cận cảnh mặt sông tối đen, ánh đuốc lập lòe. [Graphic]: 2 vạn quân."}
    brand = {"visual_style_prompt": "archival tone"}
    result = _build_visual_prompt(shot, brand, is_video=False, for_local_sdxl=True)
    assert "[Graphic]" not in result
    assert "2 vạn quân" not in result
    assert ", " in result


def test_build_visual_prompt_local_sdxl_content_leads_style_follows():
    """Đợt 3 (2026-08-22) — đổi lại thứ tự: NỘI DUNG CẢNH (visual_fx) LUÔN đứng ĐẦU, khối
    style cố định + style kênh đứng SAU — ngược lại đợt 2 (khi đó style đứng đầu). Sửa bug
    thật người dùng báo: "style ảnh đúng nhưng nội dung ảnh không giống mô tả text" —
    style đứng đầu + dài làm loãng/che khuất chủ thể, đặc biệt khi visual_fx ngắn."""
    from app.render.engine import _LOCAL_SDXL_STYLE_PREFIX, _build_visual_prompt

    shot = {"visual_fx": "Cảnh sông đêm."}
    result_local = _build_visual_prompt(shot, {}, is_video=False, for_local_sdxl=True)
    assert result_local.startswith("Cảnh sông đêm.")
    assert _LOCAL_SDXL_STYLE_PREFIX in result_local

    result_cloud = _build_visual_prompt(shot, {}, is_video=False, for_local_sdxl=False)
    assert _LOCAL_SDXL_STYLE_PREFIX not in result_cloud


def test_build_visual_prompt_local_sdxl_never_truncates_scene_content():
    """Prompt local phải giữ NGUYÊN VẸN mô tả cảnh (visual_fx) dù dài tới đâu — chỉ phần
    style kênh (phụ) bị cắt, xem _LOCAL_SDXL_BRAND_STYLE_MAX_CHARS."""
    from app.render.engine import _build_visual_prompt

    long_scene = "Cảnh chiến trận sông nước rộng lớn, " * 8  # dài
    shot = {"visual_fx": long_scene}
    brand = {"visual_style_prompt": "archival tone, muted sepia, cinematic, " * 10}  # style rất dài
    result = _build_visual_prompt(shot, brand, is_video=False, for_local_sdxl=True)
    assert long_scene.strip() in result  # mô tả cảnh KHÔNG bị cắt


def test_build_visual_prompt_local_sdxl_short_content_not_drowned_by_style():
    """Bug thật người dùng báo (2026-08-22) — shot "Cô gái chăn trâu" (S2-04, project
    "Bài học 'trọng dụng lúc khủng hoảng...'"): visual_fx NGẮN bị style kênh (đoạn văn dài
    hàng trăm ký tự) nhấn chìm — ảnh ra ĐÚNG STYLE nhưng SAI HẲN chủ thể. Xác nhận: nội
    dung cảnh phải đứng đầu VÀ chiếm tỷ trọng đáng kể (không bị cắt), phần style kênh phải
    bị giới hạn cố định, không được phép dài hơn hẳn nội dung cảnh."""
    from app.render.engine import _LOCAL_SDXL_BRAND_STYLE_MAX_CHARS, _build_visual_prompt

    shot = {"visual_fx": "Cô gái chăn trâu"}
    brand = {
        "visual_style_prompt": (
            "Visual Style (Phong cách Thị giác) Tông màu chủ đạo (Color Palette): Warm Muted Tones — Mực tàu, giấy dó, "
            "gỗ trầm, đồng cổ, đỏ nhạt phong hóa. Tạo cảm giác cổ kính, trầm mặc nhưng sang trọng. Chất liệu hình ảnh "
            "rất dài phía sau nữa để đảm bảo test thật sự cắt bớt phần này."
        )
    }
    result = _build_visual_prompt(shot, brand, is_video=False, for_local_sdxl=True)
    assert result.startswith("Cô gái chăn trâu")
    # Phần style kênh trong kết quả không được dài hơn giới hạn cố định.
    style_part = result.split("cinematic concept art, ", 1)[1]
    assert len(style_part) <= _LOCAL_SDXL_BRAND_STYLE_MAX_CHARS
    # Nội dung cảnh phải chiếm tỷ trọng khá hơn hẳn trước — bug thật: trước đây chỉ ~5%
    # (17/320, ở GIỮA prompt, bị bao vây bởi style cả 2 phía). Vị trí (đứng ĐẦU, xem assert
    # startswith ở trên) mới là fix chính; tỷ trọng chỉ cần khá hơn rõ rệt, không cần tuyệt đối.
    assert len("Cô gái chăn trâu") / len(result) >= 0.07


def test_build_visual_prompt_local_sdxl_ignores_audio_sfx_for_image():
    """is_video=False — audio_sfx không được đưa vào prompt (cả 2 nhánh local/cloud),
    hành vi này giữ nguyên không đổi bởi thay đổi lần này."""
    from app.render.engine import _build_visual_prompt

    shot = {"visual_fx": "Cảnh sông đêm.", "audio_sfx": "nhạc căng thẳng"}
    result = _build_visual_prompt(shot, {}, is_video=False, for_local_sdxl=True)
    assert "nhạc căng thẳng" not in result


@respx.mock
def test_gemini_and_veo_test_connection_via_api(client):
    """Test connection thật qua endpoint /providers/{id}/test cho 3 provider mới —
    xác nhận không còn "chưa xác minh" chung chung như lúc còn là stub."""
    respx.get(url__regex=r"https://generativelanguage\.googleapis\.com/v1beta/models\?key=.*").mock(return_value=Response(200, json={"models": []}))

    for task, provider_name in (("tts", "gemini"), ("image", "gemini"), ("video", "veo")):
        pv = client.post("/providers", json={"task": task, "provider_name": provider_name, "display_name": f"{provider_name}-{task}", "connection_type": "cloud_api", "api_key": "sk-test"}).json()
        resp = client.post(f"/providers/{pv['id']}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True, body
        assert "thành công" in body["message"]
        client.delete(f"/providers/{pv['id']}")
