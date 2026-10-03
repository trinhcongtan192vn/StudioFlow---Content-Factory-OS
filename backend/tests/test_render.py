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
import re
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


# ---------------------------------------------------------------------------
# Upload cả folder ảnh/video khớp theo mã block (2026-09-16, theo yêu cầu người dùng) —
# tên file (bỏ đuôi) PHẢI trùng shot_id/mã block, VD "B01.png" -> shot "B01". `_import_
# script_csv` tạo B01..B06 với B02/B05 = "video", còn lại = "image" (i % 3 == 1).
# ---------------------------------------------------------------------------
def test_upload_shot_visual_batch_matches_by_filename_and_reports_unmatched(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)

    files = [
        ("files", ("B01.png", io.BytesIO(FAKE_PNG), "image/png")),  # khớp đúng loại (image)
        ("files", ("B05.mp4", io.BytesIO(FAKE_MP4), "video/mp4")),  # khớp đúng loại (video)
        ("files", ("B_khong_ton_tai.png", io.BytesIO(FAKE_PNG), "image/png")),  # không khớp shot nào
        ("files", ("B02.png", io.BytesIO(FAKE_PNG), "image/png")),  # khớp tên nhưng B02 là "video" -> sai loại
    ]
    resp = client.post(f"/projects/{pid}/render/shots/upload-visual-batch", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    matched_ids = {m["shot_id"] for m in body["matched"]}
    assert matched_ids == {"B01", "B05"}
    unmatched_names = {u["filename"] for u in body["unmatched"]}
    assert unmatched_names == {"B_khong_ton_tai.png", "B02.png"}
    b02_reason = next(u["reason"] for u in body["unmatched"] if u["filename"] == "B02.png")
    assert "video" in b02_reason.lower()

    state = client.get(f"/projects/{pid}/render/status").json()
    b01 = next(s for s in state["shots"] if s["shot_id"] == "B01")
    assert b01["visual_status"] == "ready"
    assert b01["visual_provider"] == "upload"
    assert Path(b01["visual_asset_path"]).read_bytes() == FAKE_PNG
    b05 = next(s for s in state["shots"] if s["shot_id"] == "B05")
    assert b05["visual_status"] == "ready"
    assert Path(b05["visual_asset_path"]).read_bytes() == FAKE_MP4
    # Shot KHÔNG có file khớp (VD B03) giữ nguyên trạng thái ban đầu, không bị đụng vào.
    b03 = next(s for s in state["shots"] if s["shot_id"] == "B03")
    assert b03["visual_status"] == "pending"


@respx.mock
def test_upload_shot_visual_batch_overwrites_already_ready_shot(client, render_ready_project):
    """Upload trùng tên 1 shot ĐÃ sẵn ảnh AI -> ghi đè + reset duyệt lại, cùng hành vi
    `upload_shot_visual` đơn lẻ (mục 42)."""
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    # Lấy đúng shot ẢNH đã ready (state không có `visual_type`, tra qua pack.json).
    pack = client.get(f"/projects/{pid}/pack").json()
    ready_image_shot_id = next(s["shot_id"] for s in state["shots"] if s["visual_status"] == "ready" and next(p for p in pack["shots"] if p["shot_id"] == s["shot_id"])["visual_type"] == "image")
    client.post(f"/projects/{pid}/render/shots/{ready_image_shot_id}/approve", json={"approved": True})

    new_png = b"\x89PNG\r\n\x1a\n" + b"9" * 40
    resp = client.post(f"/projects/{pid}/render/shots/upload-visual-batch", files=[("files", (f"{ready_image_shot_id}.png", io.BytesIO(new_png), "image/png"))])
    assert resp.status_code == 200, resp.text
    assert resp.json()["matched"] == [{"shot_id": ready_image_shot_id, "filename": f"{ready_image_shot_id}.png"}]

    state2 = client.get(f"/projects/{pid}/render/status").json()
    shot2 = next(s for s in state2["shots"] if s["shot_id"] == ready_image_shot_id)
    assert shot2["approved"] is False  # ghi đè -> phải duyệt lại
    assert Path(shot2["visual_asset_path"]).read_bytes() == new_png


def test_upload_shot_visual_batch_rejected_while_in_progress(client, render_ready_project):
    pid = render_ready_project
    from app.render import engine as render_engine

    render_engine._mark_in_progress(pid)
    try:
        resp = client.post(f"/projects/{pid}/render/shots/upload-visual-batch", files=[("files", ("B01.png", io.BytesIO(FAKE_PNG), "image/png"))])
        assert resp.status_code == 409
    finally:
        render_engine._mark_done(pid)


# ---------------------------------------------------------------------------
# Xoá ảnh/video của 1 shot (Visual Studio, 2026-09-02, theo yêu cầu người dùng: "Cho
# phép remove video/image ở từng shot/block sau khi đã add") — trả shot về "pending",
# xoá file trên đĩa, KHÔNG tự sinh/upload lại cái khác ngay.
# ---------------------------------------------------------------------------
@respx.mock
def test_remove_shot_visual_resets_to_pending_and_deletes_file(client, render_ready_project):
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot = next(s for s in state["shots"] if s["visual_status"] == "ready")
    shot_id = shot["shot_id"]
    asset_path = Path(shot["visual_asset_path"])
    assert asset_path.exists()
    client.post(f"/projects/{pid}/render/shots/{shot_id}/approve", json={"approved": True})

    resp = client.delete(f"/projects/{pid}/render/shots/{shot_id}/visual")
    assert resp.status_code == 200, resp.text
    removed = next(s for s in resp.json()["shots"] if s["shot_id"] == shot_id)
    assert removed["visual_status"] == "pending"
    assert removed["visual_asset_path"] is None
    assert removed["visual_provider"] is None
    assert removed["approved"] is False
    assert not asset_path.exists()  # file cũ đã bị xoá trên đĩa, không để rác


@respx.mock
def test_remove_shot_visual_clears_linked_vault_clip(client, render_ready_project):
    """Gán clip từ Kho tư liệu rồi xoá — `linked_clip_id` phải về None (chỉ hết gán cho
    shot này, clip vẫn còn nguyên trong Kho, không bị xoá)."""
    from app.config import project_dir
    from app.render import engine as render_engine

    pid = render_ready_project
    channel_id = client.get(f"/projects/{pid}").json()["channel_id"]
    pdir = project_dir(channel_id, pid)
    pack = client.get(f"/projects/{pid}/pack").json()
    video_shot = next(s for s in pack["shots"] if s["visual_type"] == "video")
    resp = client.post(f"/projects/{pid}/render/shots/{video_shot['shot_id']}/upload-visual", files={"file": ("a.mp4", io.BytesIO(b"\x00\x00\x00\x18ftyp" + b"0" * 10), "video/mp4")})
    assert resp.status_code == 200, resp.text
    state = render_engine.load_render_state(pdir, pid)
    status = next(s for s in state.shots if s.shot_id == video_shot["shot_id"])
    status.linked_clip_id = "fake-clip-id"
    render_engine.save_render_state(pdir, state)

    resp = client.delete(f"/projects/{pid}/render/shots/{video_shot['shot_id']}/visual")
    assert resp.status_code == 200, resp.text
    removed = next(s for s in resp.json()["shots"] if s["shot_id"] == video_shot["shot_id"])
    assert removed["linked_clip_id"] is None


def test_remove_shot_visual_404_when_no_render_state(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    shot_id = pack["shots"][0]["shot_id"]
    resp = client.delete(f"/projects/{pid}/render/shots/{shot_id}/visual")
    assert resp.status_code == 404


def test_remove_shot_visual_404_unknown_shot(client, render_ready_project):
    resp = client.delete(f"/projects/{render_ready_project}/render/shots/does-not-exist/visual")
    assert resp.status_code == 404


@respx.mock
def test_remove_shot_visual_rejected_while_in_progress(client, render_ready_project):
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot_id = state["shots"][0]["shot_id"]

    from app.render import engine as render_engine
    render_engine._mark_in_progress(pid)
    try:
        resp = client.delete(f"/projects/{pid}/render/shots/{shot_id}/visual")
        assert resp.status_code == 409
    finally:
        render_engine._mark_done(pid)


@respx.mock
def test_assemble_does_not_require_all_shots_to_have_visual_after_removal_when_no_background_video(client, render_ready_project):
    """Xoá visual của 1 shot mà KHÔNG cấu hình video nền chung — shot đó về "pending",
    ghép video phải bị chặn lại (400) đúng như shot chưa từng sinh, không phải lỗi 500
    bất ngờ ở tầng ffmpeg."""
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot_id = state["shots"][0]["shot_id"]
    client.delete(f"/projects/{pid}/render/shots/{shot_id}/visual")

    resp = client.post(f"/projects/{pid}/render/assemble")
    assert resp.status_code == 400
    assert shot_id in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Xoá watermark (Visual Studio, 2026-08-28) — tái dùng app/watermark/, model thật đã
# verify riêng ở test_watermark.py (chậm, ~90s nạp lần đầu) — mock ở đây, chỉ test đúng
# luồng điều phối (cập nhật render.json, phân biệt "không tìm thấy" vs lỗi thật, tóm tắt
# hàng loạt), cùng nguyên tắc test_asset_vault.py's watermark tests.
# ---------------------------------------------------------------------------
def _fake_wm_image_ok(image_path, out_path, *, bboxes=None, text_input="watermark"):
    import shutil as _shutil

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(image_path, out_path)
    return [(0, 0, 10, 10)]


def _fake_wm_video_ok(ffmpeg, video_path, out_path, tmp_dir, *, text_input="watermark", force_gemini=False, on_progress=None):
    import shutil as _shutil

    if on_progress:
        on_progress(0, 20, "Đang tách frame từ video")
        on_progress(10, 20, "Đang xoá watermark 10/20 frame")
        on_progress(20, 20, "Đang xoá watermark 20/20 frame")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(video_path, out_path)
    return [(0, 0, 10, 10)]


def _fake_wm_image_none(image_path, out_path, *, bboxes=None, text_input="watermark"):
    raise ValueError("Không phát hiện được watermark nào trong ảnh — thử mô tả khác hoặc khoanh vùng tay.")


def _fake_wm_video_none(ffmpeg, video_path, out_path, tmp_dir, *, text_input="watermark", force_gemini=False, on_progress=None):
    raise ValueError("Không phát hiện được watermark nào trong video — thử mô tả khác.")


def _fake_wm_image_fails(image_path, out_path, *, bboxes=None, text_input="watermark"):
    raise RuntimeError("model lỗi giả lập")


def _fake_wm_video_fails(ffmpeg, video_path, out_path, tmp_dir, *, text_input="watermark", force_gemini=False, on_progress=None):
    raise RuntimeError("model lỗi giả lập")


@respx.mock
def test_remove_shot_watermark_cleans_asset_and_keeps_ready(client, render_ready_project, monkeypatch):
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _fake_wm_image_ok)
    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _fake_wm_video_ok)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot = state["shots"][0]
    old_path = shot["visual_asset_path"]

    # mode=gemini — shot[0] là ẢNH, provider thật (openai qua _setup_asset_providers)
    # KHÔNG phải "gemini" (2026-09-18, gate provider mới) — test này kiểm tra LUỒNG xoá,
    # không phải gate, nên ép mode=gemini để bỏ qua gate, giữ nguyên ý định test gốc.
    resp = client.post(f"/projects/{pid}/render/shots/{shot['shot_id']}/remove-watermark?mode=gemini")
    assert resp.status_code == 200, resp.text
    # Response của POST phản ánh trạng thái ĐỒNG BỘ (vừa set "generating" TRƯỚC khi mở
    # BackgroundTasks, xem router) — phải GET lại /render/status để thấy kết quả SAU khi
    # background task chạy xong, cùng pattern `test_regenerate_visual_resets_approval`.
    state2 = client.get(f"/projects/{pid}/render/status").json()
    updated = next(s for s in state2["shots"] if s["shot_id"] == shot["shot_id"])
    assert updated["visual_status"] == "ready"
    assert updated["visual_watermark_note"] is None
    assert updated["visual_error"] is None
    assert updated["visual_asset_path"] != old_path
    assert updated["visual_asset_path"].endswith("_nowm" + Path(old_path).suffix)
    assert Path(updated["visual_asset_path"]).exists()
    assert not Path(old_path).exists()  # file cũ đã bị xoá, không để rác


@respx.mock
def test_remove_shot_watermark_reports_progress_then_clears_it(client, render_ready_project, monkeypatch):
    """Thanh tiến trình (2026-09-02, theo yêu cầu người dùng: "tương tự Kho Tài Nguyên") —
    xác nhận `on_progress` ghi TỚI render.json (không chỉ giữ trong biến tạm) mỗi lần gọi
    (spy `save_render_state`, vì TestClient chạy BackgroundTasks đồng bộ nên không polling
    HTTP giữa chừng được), và progress được DỌN SẠCH (None) ở trạng thái cuối cùng."""
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _fake_wm_image_ok)
    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _fake_wm_video_ok)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    pack = client.get(f"/projects/{pid}/pack").json()
    video_shot_id = next(s["shot_id"] for s in pack["shots"] if s["visual_type"] == "video")

    snapshots = []
    original_save = render_engine.save_render_state

    def _spy_save(pdir, state):
        shot = next((s for s in state.shots if s.shot_id == video_shot_id), None)
        if shot:
            snapshots.append((shot.visual_watermark_progress_current, shot.visual_watermark_progress_total, shot.visual_watermark_progress_label))
        original_save(pdir, state)

    monkeypatch.setattr(render_engine, "save_render_state", _spy_save)

    resp = client.post(f"/projects/{pid}/render/shots/{video_shot_id}/remove-watermark")
    assert resp.status_code == 200, resp.text

    assert (10, 20, "Đang xoá watermark 10/20 frame") in snapshots
    assert (20, 20, "Đang xoá watermark 20/20 frame") in snapshots
    assert snapshots[-1] == (None, None, None)  # trạng thái cuối cùng đã dọn sạch progress

    state2 = client.get(f"/projects/{pid}/render/status").json()
    updated = next(s for s in state2["shots"] if s["shot_id"] == video_shot_id)
    assert updated["visual_watermark_progress_current"] is None
    assert updated["visual_watermark_progress_total"] is None
    assert updated["visual_watermark_progress_label"] is None


@respx.mock
def test_remove_shot_watermark_no_watermark_sets_note_not_error(client, render_ready_project, monkeypatch):
    """Yêu cầu người dùng: "nếu ảnh nào không phát hiện watermark thì có thông báo rõ
    ràng" — KHÔNG được coi là lỗi (asset gốc vẫn hợp lệ, không đổi)."""
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _fake_wm_image_none)
    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _fake_wm_video_none)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot = state["shots"][0]
    old_path = shot["visual_asset_path"]

    # mode=gemini — xem chú thích ở test_remove_shot_watermark_cleans_asset_and_keeps_ready.
    resp = client.post(f"/projects/{pid}/render/shots/{shot['shot_id']}/remove-watermark?mode=gemini")
    assert resp.status_code == 200, resp.text
    state2 = client.get(f"/projects/{pid}/render/status").json()
    updated = next(s for s in state2["shots"] if s["shot_id"] == shot["shot_id"])
    assert updated["visual_status"] == "ready"  # KHÔNG "error"
    assert updated["visual_error"] is None
    assert updated["visual_watermark_note"] and "không phát hiện" in updated["visual_watermark_note"].lower()
    assert updated["visual_asset_path"] == old_path  # asset gốc GIỮ NGUYÊN


@respx.mock
def test_remove_shot_watermark_real_failure_sets_error(client, render_ready_project, monkeypatch):
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _fake_wm_image_fails)
    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _fake_wm_video_fails)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot = state["shots"][0]

    # mode=gemini — xem chú thích ở test_remove_shot_watermark_cleans_asset_and_keeps_ready.
    resp = client.post(f"/projects/{pid}/render/shots/{shot['shot_id']}/remove-watermark?mode=gemini")
    assert resp.status_code == 200, resp.text
    state2 = client.get(f"/projects/{pid}/render/status").json()
    updated = next(s for s in state2["shots"] if s["shot_id"] == shot["shot_id"])
    assert updated["visual_status"] == "error"
    assert "model lỗi giả lập" in updated["visual_error"]
    assert updated["visual_watermark_note"] is None


def test_remove_shot_watermark_rejects_when_no_render_state_yet(client, project_with_brief):
    """Chưa từng bấm 'Bắt đầu sinh asset' cho shot này — chưa có `ShotRenderStatus` nào
    trong render.json để xoá watermark trên đó."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    shot_id = pack["shots"][0]["shot_id"]
    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/remove-watermark")
    assert resp.status_code == 404


@respx.mock
def test_remove_shot_watermark_rejects_when_not_ready_yet(client, project_with_brief):
    """Có `ShotRenderStatus` nhưng chưa `visual_status=="ready"` (VD lỗi thiếu provider)
    — 400 rõ ràng, không cho xoá watermark trên asset chưa tồn tại."""
    _delete_all_asset_providers(client)
    pid = _drive_to_ready_output(client, project_with_brief)
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot_id = state["shots"][0]["shot_id"]
    assert state["shots"][0]["visual_status"] == "error"  # thiếu provider — xem test_asset_generation_fails_clearly_without_provider

    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/remove-watermark")
    assert resp.status_code == 400


@respx.mock
def test_remove_shot_watermark_rejected_while_in_progress(client, render_ready_project):
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot_id = state["shots"][0]["shot_id"]

    from app.render import engine as render_engine
    render_engine._mark_in_progress(pid)
    try:
        resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/remove-watermark")
        assert resp.status_code == 409
    finally:
        render_engine._mark_done(pid)


@respx.mock
def test_remove_all_shots_watermark_summarizes_mixed_results(client, render_ready_project, monkeypatch):
    """Hàng loạt — 1 shot xoá thành công, 1 shot không phát hiện watermark, 1 lỗi thật
    (nếu project có đủ ≥3 shot; nếu ít hơn, phần còn lại vẫn phải cộng đúng vào tổng)."""
    from app.render import engine as render_engine

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot_ids = [s["shot_id"] for s in state["shots"]]
    assert len(shot_ids) >= 1

    # Ép visual_provider="gemini" cho MỌI shot (2026-09-18, gate provider mới ở bulk —
    # xem `engine.py::remove_all_shots_watermark`) — provider thật lúc sinh là "openai"
    # (qua `_setup_asset_providers`), sẽ bị gate BỎ QUA ảnh không rõ nguồn Gemini, làm
    # sai `summary["scanned"]` mà test này không nhắm tới (test nhắm vào logic TỔNG HỢP
    # kết quả cleaned/no_watermark/failed, không phải gate).
    from app.config import project_dir

    channel_id = client.get(f"/projects/{pid}").json()["channel_id"]
    pdir = project_dir(channel_id, pid)
    rstate = render_engine.load_render_state(pdir, pid)
    for s in rstate.shots:
        s.visual_provider = "gemini"
    render_engine.save_render_state(pdir, rstate)

    outcomes = ["ok", "none", "fail"]
    fakes_image = {"ok": _fake_wm_image_ok, "none": _fake_wm_image_none, "fail": _fake_wm_image_fails}
    fakes_video = {"ok": _fake_wm_video_ok, "none": _fake_wm_video_none, "fail": _fake_wm_video_fails}
    # Gán outcome xoay vòng cho từng shot theo THỨ TỰ — patch 1 hàm DUY NHẤT tự tra theo
    # shot_id đang xử lý (đơn giản hơn patch lại nhiều lần giữa các lượt gọi tuần tự).
    plan = {shot_id: outcomes[i % len(outcomes)] for i, shot_id in enumerate(shot_ids)}

    def _dispatch_image(image_path, out_path, *, bboxes=None, text_input="watermark"):
        shot_id = Path(image_path).stem
        return fakes_image[plan[shot_id]](image_path, out_path, bboxes=bboxes, text_input=text_input)

    def _dispatch_video(ffmpeg, video_path, out_path, tmp_dir, *, text_input="watermark", force_gemini=False, on_progress=None):
        shot_id = Path(video_path).stem
        return fakes_video[plan[shot_id]](ffmpeg, video_path, out_path, tmp_dir, text_input=text_input, force_gemini=force_gemini, on_progress=on_progress)

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _dispatch_image)
    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _dispatch_video)

    resp = client.post(f"/projects/{pid}/render/remove-watermark-all")
    assert resp.status_code == 200, resp.text

    final_state = client.get(f"/projects/{pid}/render/status").json()
    summary = final_state["watermark_scan_summary"]
    assert summary is not None
    assert summary["scanned"] == len(shot_ids)
    assert summary["cleaned"] + summary["no_watermark"] + summary["failed"] == len(shot_ids)
    assert summary["cleaned"] == sum(1 for v in plan.values() if v == "ok")
    assert summary["no_watermark"] == sum(1 for v in plan.values() if v == "none")
    assert summary["failed"] == sum(1 for v in plan.values() if v == "fail")

    for s in final_state["shots"]:
        outcome = plan[s["shot_id"]]
        if outcome == "fail":
            assert s["visual_status"] == "error"
        else:
            assert s["visual_status"] == "ready"


# ---------------------------------------------------------------------------
# Gate provider Gemini cho ẢNH (2026-09-18) — nút "Xoá watermark" (mode="auto") chỉ tự
# chạy khi CHẮC CHẮN ảnh từ Gemini (`status.visual_provider == "gemini"`), tránh vá nhầm
# 1 vùng góc không hề có watermark trên ảnh nguồn khác (OpenAI/Flux/Midjourney/upload).
# Nút riêng "Xoá watermark Gemini" (mode="gemini") ép chạy bất kể provider.
# ---------------------------------------------------------------------------
@respx.mock
def test_remove_shot_watermark_auto_mode_rejects_non_gemini_image(client, render_ready_project, monkeypatch):
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _fake_wm_image_ok)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot = state["shots"][0]  # B01 = ảnh, provider thật = "openai" (_setup_asset_providers)
    assert shot["visual_provider"] == "openai"

    resp = client.post(f"/projects/{pid}/render/shots/{shot['shot_id']}/remove-watermark")
    assert resp.status_code == 400, resp.text
    assert "gemini" in resp.json()["detail"].lower()
    # Shot KHÔNG bị đụng vào — vẫn đúng asset/provider ban đầu, không hề gọi tới xoá watermark.
    state2 = client.get(f"/projects/{pid}/render/status").json()
    unchanged = next(s for s in state2["shots"] if s["shot_id"] == shot["shot_id"])
    assert unchanged["visual_asset_path"] == shot["visual_asset_path"]


@respx.mock
def test_remove_shot_watermark_gemini_mode_bypasses_provider_gate(client, render_ready_project, monkeypatch):
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _fake_wm_image_ok)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    shot = state["shots"][0]
    assert shot["visual_provider"] == "openai"

    resp = client.post(f"/projects/{pid}/render/shots/{shot['shot_id']}/remove-watermark?mode=gemini")
    assert resp.status_code == 200, resp.text
    state2 = client.get(f"/projects/{pid}/render/status").json()
    updated = next(s for s in state2["shots"] if s["shot_id"] == shot["shot_id"])
    assert updated["visual_status"] == "ready"
    assert updated["visual_asset_path"] != shot["visual_asset_path"]  # đã thật sự xoá


@respx.mock
def test_remove_shot_watermark_auto_mode_does_not_gate_video(client, render_ready_project, monkeypatch):
    """Video KHÔNG bị gate provider — tự định vị theo nội dung thật (đa-frame/Florence-2),
    không phụ thuộc `visual_provider`."""
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _fake_wm_video_ok)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    pack = client.get(f"/projects/{pid}/pack").json()
    video_shot_id = next(s["shot_id"] for s in pack["shots"] if s["visual_type"] == "video")

    resp = client.post(f"/projects/{pid}/render/shots/{video_shot_id}/remove-watermark")
    assert resp.status_code == 200, resp.text


@respx.mock
def test_remove_all_shots_watermark_skips_non_gemini_images_silently(client, render_ready_project, monkeypatch):
    """Nút "Xoá watermark toàn bộ slot" — bỏ qua THẦM LẶNG ảnh không rõ nguồn Gemini
    (không tính vào `scanned`, không lỗi), VẪN xử lý video bình thường."""
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _fake_wm_image_ok)
    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _fake_wm_video_ok)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    pack = client.get(f"/projects/{pid}/pack").json()
    state = client.get(f"/projects/{pid}/render/status").json()
    n_image = sum(1 for s in pack["shots"] if s["visual_type"] == "image")
    n_video = sum(1 for s in pack["shots"] if s["visual_type"] == "video")
    assert n_image >= 1 and n_video >= 1  # đủ cả 2 loại để test có ý nghĩa (đúng fixture _import_script_csv mặc định)
    image_shot_ids = {s["shot_id"] for s in pack["shots"] if s["visual_type"] == "image"}
    assert all(s["visual_provider"] == "openai" for s in state["shots"] if s["shot_id"] in image_shot_ids)  # không phải gemini (video dùng "sora", không liên quan gate)

    resp = client.post(f"/projects/{pid}/render/remove-watermark-all")
    assert resp.status_code == 200, resp.text
    final_state = client.get(f"/projects/{pid}/render/status").json()
    summary = final_state["watermark_scan_summary"]
    assert summary["scanned"] == n_video  # ảnh KHÔNG được tính vào scanned
    assert summary["cleaned"] == n_video


@respx.mock
def test_remove_shot_watermark_gemini_mode_uses_corner_bbox_for_video(client, render_ready_project, monkeypatch):
    """mode="gemini" cho VIDEO (2026-09-19, theo yêu cầu người dùng: bấm nút này là xác
    nhận CHỦ ĐỘNG "chắc chắn có watermark Gemini") — dùng THẲNG `gemini_corner_bbox`
    (`force_gemini=True`), KHÔNG qua đa-frame/Florence-2. Đã thử "so khớp mẫu template"
    trước đó nhưng verify thật trên frame video THẬT cho kết quả sai (khớp nhầm hoạ tiết
    nền) — quay lại dùng vị trí cố định đã verify, xem docstring `pipeline.py::
    remove_watermark_from_video`."""
    from app.render import engine as render_engine

    calls = []

    def _spy_video(ffmpeg, video_path, out_path, tmp_dir, *, text_input="watermark", force_gemini=False, on_progress=None):
        calls.append(force_gemini)
        return _fake_wm_video_ok(ffmpeg, video_path, out_path, tmp_dir, text_input=text_input, force_gemini=force_gemini, on_progress=on_progress)

    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _spy_video)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    pack = client.get(f"/projects/{pid}/pack").json()
    video_shot_id = next(s["shot_id"] for s in pack["shots"] if s["visual_type"] == "video")

    resp = client.post(f"/projects/{pid}/render/shots/{video_shot_id}/remove-watermark?mode=gemini")
    assert resp.status_code == 200, resp.text
    assert calls == [True]

    resp2 = client.post(f"/projects/{pid}/render/shots/{video_shot_id}/remove-watermark")
    assert resp2.status_code == 200, resp2.text
    assert calls == [True, False]


@respx.mock
def test_remove_all_shots_watermark_gemini_mode_processes_all_shots_no_gate(client, render_ready_project, monkeypatch):
    """Bulk "Xoá watermark Gemini toàn bộ slot" (mode="gemini") — xử lý MỌI shot ready
    (ảnh lẫn video), KHÔNG gate provider, khác hẳn mode="auto" (mục 148, chỉ xử lý video +
    ảnh rõ nguồn Gemini)."""
    from app.render import engine as render_engine

    monkeypatch.setattr(render_engine, "remove_watermark_from_image", _fake_wm_image_ok)
    monkeypatch.setattr(render_engine, "remove_watermark_from_video", _fake_wm_video_ok)

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    total_shots = len(state["shots"])

    resp = client.post(f"/projects/{pid}/render/remove-watermark-all?mode=gemini")
    assert resp.status_code == 200, resp.text
    final_state = client.get(f"/projects/{pid}/render/status").json()
    summary = final_state["watermark_scan_summary"]
    assert summary["scanned"] == total_shots  # KHÔNG bỏ qua ảnh non-Gemini nào
    assert summary["cleaned"] == total_shots


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
def test_assemble_requires_all_shots_ready(client, render_ready_project):
    pid = render_ready_project
    resp = client.post(f"/projects/{pid}/render/assemble")
    assert resp.status_code == 400  # chưa sinh asset nào (render/start chưa chạy)


@respx.mock
def test_assemble_does_not_require_approval(client, render_ready_project, monkeypatch):
    """2026-09-02, theo yêu cầu người dùng ("bỏ luồng duyệt block, ko cần phải có thì
    mới render được video") — ghép video KHÔNG còn yêu cầu `approved=True` cho từng
    shot, chỉ cần visual đã "ready". Giả lập chưa cài ffmpeg (như
    `test_assemble_works_without_output_enter`) — chỉ cần xác nhận request ĐƯỢC CHẤP
    NHẬN dù KHÔNG shot nào được duyệt."""
    import shutil as _shutil

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")

    monkeypatch.setattr(_shutil, "which", lambda name: None)
    resp = client.post(f"/projects/{pid}/render/assemble")
    assert resp.status_code == 200
    assert resp.json()["assembly_status"] == "assembling"


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


@respx.mock
def test_assemble_rejects_invalid_export_lang_immediately(client, render_ready_project):
    """Mới (2026-09-11) — chọn ngôn ngữ xuất video: router validate NGAY (400), không
    đợi BackgroundTasks mới báo, cùng nguyên tắc "báo lỗi sớm" đã áp dụng cho
    codec+GPU."""
    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    resp = client.post(f"/projects/{pid}/render/assemble", json={"lang": "xx"})
    assert resp.status_code == 400
    state = client.get(f"/projects/{pid}/render/status").json()
    assert state["assembly_status"] != "assembling"


@respx.mock
def test_assemble_blocks_when_narration_not_ready_for_selected_lang(client, render_ready_project, monkeypatch):
    """Mới (2026-09-11), theo yêu cầu người dùng: "nếu giọng đọc của ngôn ngữ được chọn
    chưa sinh hết, hiển thị cho user biết và KHÔNG cho render" — chọn ngôn ngữ CHƯA từng
    dịch/sinh giọng đọc (project chỉ có giọng đọc ngôn ngữ CHÍNH, mặc định "vi") phải bị
    chặn 400, KHÔNG được ghép. Ngôn ngữ chính (mặc định, không truyền `lang`) vẫn ghép
    bình thường vì `/render/start` đã sinh xong.

    **Bug thật tự phát hiện (2026-09-11)** — lượt gán thứ 2 (`resp2`, ngôn ngữ chính, kỳ
    vọng 200) trước đây gọi THẬT `POST .../render/assemble` không giả lập thiếu ffmpeg —
    `TestClient` chạy BackgroundTasks ĐỒNG BỘ trong cùng request nên assembly THẬT chạy
    ngay, dùng ảnh từ `_mock_asset_apis()` (FAKE_PNG, không phải PNG thật) — đúng bẫy đã
    cảnh báo ở docstring `test_assemble_works_without_output_enter` phía trên ("ffmpeg
    THẬT xử lý sẽ treo/lỗi không đoán trước được"): ffmpeg THẬT treo vô thời hạn xử lý
    FAKE_PNG, làm cả request treo theo, kéo treo luôn suốt lượt `pytest` sau đó (phát
    hiện lúc điều tra vì sao full suite chạy quá lâu). Test này chỉ cần xác nhận request
    ĐƯỢC CHẤP NHẬN (400/200 đúng gate), không cần assembly thật sự chạy xong — áp dụng
    ĐÚNG cùng 1 cách né (giả lập thiếu ffmpeg) như test phía trên."""
    import shutil as _shutil

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})
        assert s["narration_status"] == "ready"  # sanity: /render/start đã sinh xong ngôn ngữ chính

    # Ngôn ngữ CHƯA từng dịch/sinh giọng đọc — phải bị chặn.
    resp = client.post(f"/projects/{pid}/render/assemble", json={"lang": "en"})
    assert resp.status_code == 400
    assert "en" in resp.json()["detail"] or "Giọng đọc" in resp.json()["detail"]
    state = client.get(f"/projects/{pid}/render/status").json()
    assert state["assembly_status"] != "assembling"

    # Ngôn ngữ CHÍNH (mặc định) — đã sẵn sàng, router chấp nhận request (200). Giả lập
    # thiếu ffmpeg TRƯỚC lượt gọi này — không cần assembly thật sự chạy xong, chỉ cần
    # xác nhận gate ngôn ngữ chính không chặn (khác lượt "en" ở trên).
    monkeypatch.setattr(_shutil, "which", lambda name: None)
    resp2 = client.post(f"/projects/{pid}/render/assemble")
    assert resp2.status_code == 200, resp2.text


# ---------------------------------------------------------------------------
# Tự phục hồi khi `assembly_status` bị KẸT "assembling" (2026-09-02, mục 111) — bug thật
# người dùng báo: thread chạy `assemble_video` chết lặng giữa chừng (không rõ nguyên
# nhân — nghi UnicodeEncodeError lúc log tiếng Việt ra console cp1252, xem `electron/
# src/backend-launcher.ts::PYTHONIOENCODING`), để lại `assembly_status="assembling"`
# MÃI MÃI trong render.json — router giờ chỉ tin `engine.is_assembly_in_progress`
# (cờ TRONG BỘ NHỚ, tự về `False` khi tiến trình backend khởi động lại), không tin mù
# quáng field đã lưu. Cộng thêm nút "Đặt lại tiến trình bị treo" (`POST .../assemble/
# reset`) làm giải pháp UI trực tiếp, không cần sửa tay render.json/khởi động lại app.
# ---------------------------------------------------------------------------
def _write_stale_assembling_status(pid: str, render_ready_project_channel_id: str) -> None:
    """Mô phỏng ĐÚNG bug thật: `assembly_status="assembling"` đã lưu trong render.json,
    nhưng KHÔNG có `_mark_assembly_in_progress` nào đang giữ (thread xử lý nó đã "chết
    lặng"/tiến trình backend đã khởi động lại) — khác trường hợp đang chạy thật."""
    from app.config import project_dir
    from app.render import engine as render_engine

    pdir = project_dir(render_ready_project_channel_id, pid)
    state = render_engine.load_render_state(pdir, pid)
    state.assembly_status = "assembling"
    state.assembly_error = None
    render_engine.save_render_state(pdir, state)


def test_start_assemble_self_heals_stale_assembling_status(client, render_ready_project, monkeypatch):
    """`assembly_status` kẹt "assembling" nhưng KHÔNG có tiến trình thật đang giữ cờ
    (`is_assembly_in_progress` == False, VD sau khi backend khởi động lại) — bấm "Ghép
    video" phải ĐƯỢC PHÉP chạy tiếp (tự phục hồi), KHÔNG còn bị 409 như trước mục 111.
    Giả lập thiếu ffmpeg (như `test_assemble_works_without_output_enter`) — chỉ cần xác
    nhận request ĐƯỢC CHẤP NHẬN, không cần assembly thật chạy xong."""
    import shutil as _shutil

    from app.render import engine as render_engine

    pid = render_ready_project
    channel_id = client.get(f"/projects/{pid}").json()["channel_id"]
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    _write_stale_assembling_status(pid, channel_id)
    assert not render_engine.is_assembly_in_progress(pid)  # sanity — đúng kịch bản "kẹt", không phải đang chạy thật

    monkeypatch.setattr(_shutil, "which", lambda name: None)
    resp = client.post(f"/projects/{pid}/render/assemble")
    assert resp.status_code != 409, resp.text


def test_start_assemble_still_blocks_when_actually_in_progress(client, render_ready_project):
    """KHÁC bug đã fix — nếu `is_assembly_in_progress` THẬT SỰ `True` (task đang chạy
    trong CHÍNH tiến trình backend này), vẫn phải chặn 409 như cũ, không được tự phục
    hồi nhầm 1 tiến trình đang xử lý bình thường."""
    from app.render import engine as render_engine

    pid = render_ready_project
    channel_id = client.get(f"/projects/{pid}").json()["channel_id"]
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    _write_stale_assembling_status(pid, channel_id)
    render_engine._mark_assembly_in_progress(pid)
    try:
        resp = client.post(f"/projects/{pid}/render/assemble")
        assert resp.status_code == 409
    finally:
        render_engine._mark_assembly_done(pid)


def test_reset_stuck_assembly_resets_status_when_not_actually_in_progress(client, render_ready_project):
    pid = render_ready_project
    channel_id = client.get(f"/projects/{pid}").json()["channel_id"]
    _write_stale_assembling_status(pid, channel_id)

    resp = client.post(f"/projects/{pid}/render/assemble/reset")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["assembly_status"] == "error"
    assert data["assembly_progress"] is None
    assert data["assembly_started_at"] is None
    assert "treo" in data["assembly_error"].lower() or "đặt lại" in data["assembly_error"].lower()


def test_reset_stuck_assembly_rejects_when_actually_in_progress(client, render_ready_project):
    from app.render import engine as render_engine

    pid = render_ready_project
    channel_id = client.get(f"/projects/{pid}").json()["channel_id"]
    _write_stale_assembling_status(pid, channel_id)
    render_engine._mark_assembly_in_progress(pid)
    try:
        resp = client.post(f"/projects/{pid}/render/assemble/reset")
        assert resp.status_code == 409
    finally:
        render_engine._mark_assembly_done(pid)


def test_reset_stuck_assembly_400_when_nothing_to_reset(client, render_ready_project):
    resp = client.post(f"/projects/{render_ready_project}/render/assemble/reset")
    assert resp.status_code == 400


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
@respx.mock
def test_assemble_video_marks_and_clears_in_progress_flag(client, render_ready_project, monkeypatch):
    """`_mark_assembly_in_progress`/`_mark_assembly_done` (mục 111) phải bọc ĐÚNG toàn
    bộ vòng đời `assemble_video()` — verify TRỰC TIẾP bằng spy: cờ phải `True` NGAY khi
    `_build_segment` (Pass 2) đang chạy, và `False` NGAY sau khi hàm trả về, dù thành
    công hay lỗi (dùng ffmpeg thiếu để ép lỗi — vẫn phải dọn cờ qua `finally`)."""
    import app.render.assembly as assembly_mod
    from app.render import engine as render_engine

    pid = render_ready_project
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")
    state = client.get(f"/projects/{pid}/render/status").json()
    for s in state["shots"]:
        client.post(f"/projects/{pid}/render/shots/{s['shot_id']}/approve", json={"approved": True})

    # Short-circuit — KHÔNG gọi `real_build_segment` thật (asset ở đây là bytes GIẢ, VD
    # FAKE_PNG không phải PNG thật — để ffmpeg THẬT xử lý sẽ treo/chậm không đoán trước
    # được, đúng lớp rủi ro "ffmpeg hang" đã phát hiện lúc viết test này, KHÔNG liên quan
    # gì tới thứ đang test ở đây). Raise lỗi NGAY sau khi ghi nhận cờ — vừa verify cờ
    # `True` lúc Pass 2 đang chạy, vừa verify LUÔN nhánh lỗi dọn cờ đúng qua `finally`.
    observed = {}

    def spy_build_segment(*args, **kwargs):
        observed["during"] = render_engine.is_assembly_in_progress(pid)
        raise RuntimeError("giả lập lỗi ngay trong Pass 2 — không cần ffmpeg xử lý thật")

    monkeypatch.setattr(assembly_mod, "_build_segment", spy_build_segment)

    assert not render_engine.is_assembly_in_progress(pid)
    assembly_mod.assemble_video(pid, resolution="720p", codec="h264", quality="low")
    assert observed.get("during") is True
    assert not render_engine.is_assembly_in_progress(pid)  # LUÔN dọn sau khi xong, kể cả lỗi


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
    assert _shot_base_duration(status, beat, "vi", "vi") == 34.0


def test_shot_base_duration_falls_back_to_beat_when_narration_not_ready():
    from app.render.assembly import _shot_base_duration
    from app.render.schemas import ShotRenderStatus

    beat = {"timestamp_sec": 0, "end_sec": 40}
    pending = ShotRenderStatus(shot_id="s1", narration_status="pending")
    assert _shot_base_duration(pending, beat, "vi", "vi") == 40.0

    ready_but_no_duration = ShotRenderStatus(shot_id="s1", narration_status="ready", narration_duration_sec=None)
    assert _shot_base_duration(ready_but_no_duration, beat, "vi", "vi") == 40.0


def test_shot_base_duration_uses_translation_when_export_lang_not_primary():
    """Mới (2026-09-11) — chọn ngôn ngữ xuất video khác ngôn ngữ chính của kênh: thời
    lượng shot phải ăn theo giọng đọc CỦA NGÔN NGỮ ĐÓ (narration_translations[lang]),
    không phải field phẳng (ngôn ngữ chính)."""
    from app.render.assembly import _shot_base_duration
    from app.render.schemas import ShotRenderStatus, TranslatedNarrationStatus

    beat = {"timestamp_sec": 0, "end_sec": 40}
    status = ShotRenderStatus(
        shot_id="s1", narration_status="ready", narration_duration_sec=34.0,
        narration_translations={"en": TranslatedNarrationStatus(narration_status="ready", narration_asset_path="/en.mp3", narration_duration_sec=21.0)},
    )
    assert _shot_base_duration(status, beat, "vi", "vi") == 34.0  # ngôn ngữ chính — field phẳng
    assert _shot_base_duration(status, beat, "en", "vi") == 21.0  # ngôn ngữ khác — translation
    assert _shot_base_duration(status, beat, "de", "vi") == 40.0  # chưa dịch/sinh giọng "de" — fallback beat


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
    assert final_state["assembly_completed_at"] is not None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_burns_caption_when_caption_layer_enabled(client, project_with_brief):
    """Tích hợp THẬT xuyên suốt `assemble_video()` với `state.caption_layer.enabled=True`
    — mới (2026-09-12), theo yêu cầu người dùng "thêm caption vào video". Xác nhận:
    (1) pipeline chạy xong bình thường (`status="done"`, không lỗi) — caption KHÔNG được
    phép làm hỏng luồng ghép chính; (2) khung hình cuối THẬT SỰ có pixel caption (chữ
    trắng/viền đen) ở dải dưới khung hình (vị trí mặc định "bottom-center"), không phải
    chỉ "chạy không lỗi" mà không burn gì (test riêng cho filter đã có ở
    `test_caption_layer.py`, đây chỉ verify WIRING đúng qua CẢ pipeline chính)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import CaptionLayer, RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:03", "Image", "Canh test", "", "Loi thoai test cho caption burn in."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x480", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    narration_mp3 = pdir / "assets" / f"{shot_id}.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "mp3", str(narration_mp3)], capture_output=True, check=True, text=True)
    real_narration_sec = _ffprobe_duration(narration_mp3)

    state = RenderState(
        project_id=pid,
        shots=[ShotRenderStatus(
            shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True,
            narration_status="ready", narration_asset_path=str(narration_mp3), narration_duration_sec=real_narration_sec,
        )],
        caption_layer=CaptionLayer(enabled=True, position="bottom-center", size_pct=0.06, opacity=1.0),
    )
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    final_path = Path(final_state["final_video_path"])

    frame = final_path.with_name("caption_check_frame.png")
    subprocess.run([ffmpeg, "-y", "-i", str(final_path), "-frames:v", "1", str(frame)], capture_output=True, check=True, text=True)

    def _non_blue_count(y: int, h: int) -> int:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(frame), "-vf", f"crop=iw:{h}:0:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        )
        data = result.stdout
        return sum(1 for i in range(0, len(data) - 2, 3) if abs(data[i]) > 40 or abs(data[i + 1]) > 40 or abs(data[i + 2] - 255) > 40)

    # 720p = 1280x720 — dải dưới cùng (y=600..720) phải có pixel caption thật.
    assert _non_blue_count(600, 120) > 200, "Không thấy pixel caption ở dải dưới khung hình dù caption_layer.enabled=True"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_uses_translated_narration_duration_when_lang_selected(client, project_with_brief, tmp_path):
    """Mới (2026-09-11), theo yêu cầu người dùng: chọn được ngôn ngữ xuất video (mặc
    định ngôn ngữ chính của kênh), thời lượng từng cảnh ăn theo giọng đọc của NGÔN NGỮ
    ĐÓ. Dựng 1 shot có CẢ giọng đọc chính (vi, ~5s) LẪN bản dịch (en, ~2s) — gọi
    `assemble_video(..., lang="en")` (ffmpeg thật) — xác nhận video ra dài ~2s (khớp
    "en"), KHÔNG PHẢI ~5s (khớp "vi", ngôn ngữ chính — hành vi cũ trước tính năng này)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus, TranslatedNarrationStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:08", "Image", "Canh test", "Khong tieng", "Loi thoai."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    vi_mp3 = pdir / "assets" / f"{shot_id}.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5", "-c:a", "mp3", str(vi_mp3)], capture_output=True, check=True, text=True)
    en_mp3 = pdir / "assets" / f"{shot_id}_en.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "mp3", str(en_mp3)], capture_output=True, check=True, text=True)
    vi_dur = _ffprobe_duration(vi_mp3)
    en_dur = _ffprobe_duration(en_mp3)
    assert en_dur < vi_dur - 1.0  # sanity: 2 ngôn ngữ khác hẳn độ dài nhau

    state = RenderState(project_id=pid, shots=[ShotRenderStatus(
        shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True,
        narration_status="ready", narration_asset_path=str(vi_mp3), narration_duration_sec=vi_dur,
        narration_translations={"en": TranslatedNarrationStatus(narration_status="ready", narration_asset_path=str(en_mp3), narration_duration_sec=en_dur)},
    )])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low", lang="en")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    total_duration = _ffprobe_duration(Path(final_state["final_video_path"]))
    assert total_duration == pytest.approx(en_dur, abs=0.5), (
        f"Video ra dài {total_duration}s — kỳ vọng khớp giọng đọc 'en' đã chọn ({en_dur}s), "
        f"không phải 'vi' (ngôn ngữ chính, {vi_dur}s) — nghi ngờ chưa đọc đúng ngôn ngữ xuất video"
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_visual_updated_at_outlives_assembly_completed_at_after_regenerate(client, project_with_brief):
    """Bug thật người dùng báo (2026-08-23): ảnh hiện ở Visual Studio khác ảnh trong video
    đã ghép, KHÔNG có cảnh báo gì cho biết video đã lệch. `visual_updated_at` (set lúc
    sinh/upload THÀNH CÔNG, không bị xoá về None như `visual_started_at`) phải mới hơn
    `assembly_completed_at` (set lúc ghép xong) sau khi regenerate 1 shot ĐÃ từng nằm
    trong lần ghép trước — đây là dữ liệu `RenderStudio.tsx` dùng để hiện banner cảnh
    báo "video không còn khớp".

    Dựng asset thật qua ffmpeg (KHÔNG dùng `_mock_asset_apis`'s FAKE_PNG cho bước ghép —
    bug thật gặp lúc viết test này: ffmpeg thật xử lý PNG giả bị treo/lỗi không đoán
    trước được, đúng cảnh báo đã ghi ở `test_assemble_works_without_output_enter`), chỉ
    mock provider ảnh (respx) cho ĐÚNG bước regenerate (`generate_visual_asset` ghi bytes
    thẳng ra đĩa, không qua ffmpeg nên FAKE_PNG an toàn ở bước này)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:03", "Image", "Canh test", "Khong tieng", "Loi thoai ngan."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    narration_mp3 = pdir / "assets" / f"{shot_id}.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "mp3", str(narration_mp3)], capture_output=True, check=True, text=True)
    real_narration_sec = _ffprobe_duration(narration_mp3)

    state = RenderState(project_id=pid, shots=[ShotRenderStatus(
        shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True,
        narration_status="ready", narration_asset_path=str(narration_mp3), narration_duration_sec=real_narration_sec,
    )])
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    assembled_state = client.get(f"/projects/{pid}/render/status").json()
    assert assembled_state["assembly_status"] == "done", assembled_state.get("assembly_error")
    completed_at = assembled_state["assembly_completed_at"]
    assert completed_at is not None

    with respx.mock:
        image = client.post("/providers", json={"task": "image", "provider_name": "openai", "display_name": "OAI", "connection_type": "cloud_api", "api_key": "sk-x"}).json()
        client.patch(f"/providers/{image['id']}", json={"is_default": True})
        respx.post("https://api.openai.com/v1/images/generations").mock(return_value=Response(200, json={"data": [{"b64_json": base64.b64encode(FAKE_PNG).decode()}]}))
        resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/regenerate-visual")
        assert resp.status_code == 200

    after_state = client.get(f"/projects/{pid}/render/status").json()
    shot_after = next(s for s in after_state["shots"] if s["shot_id"] == shot_id)
    assert shot_after["visual_status"] == "ready"
    assert shot_after["visual_updated_at"] is not None
    # ISO 8601 (`vn_isoformat`) so sánh được trực tiếp bằng string — cùng múi giờ/độ dài.
    assert shot_after["visual_updated_at"] > completed_at, "visual_updated_at phải MỚI HƠN assembly_completed_at sau khi regenerate — đây là điều kiện RenderStudio.tsx dùng để hiện banner cảnh báo video đã cũ"
    assert after_state["assembly_status"] == "done"  # ghép cũ KHÔNG tự đổi trạng thái — chỉ cảnh báo, không tự động ghép lại (specs/01: mỗi bước là hành động người dùng tự bấm)


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
def test_build_segment_freezes_last_frame_of_short_video_to_fill_target_duration(tmp_path):
    """Bug thật (2026-08-17, mục 43): B01 của project thật người dùng có shot video
    (AI sinh "6s loopable" HOẶC upload tay) NGẮN HƠN duration của beat — trước fix,
    `_build_segment` không xử lý gì input video, segment ra ĐÚNG bằng độ dài file gốc
    (ngắn hơn `duration` yêu cầu). `_xfade_chain` tính offset dựa trên `duration` danh
    nghĩa (không phải độ dài thật của segment) → lệch, ffmpeg lỗi filter graph ở bước
    ghép cuối. Fix lúc đó: loop video từ đầu (`-stream_loop -1`) tới đủ `duration`.

    **Đổi lại (2026-08-26)**: loop nhìn giả (chuyển động "giật" quay lại đầu) — đổi sang
    ĐÓNG BĂNG khung hình CUỐI thay vì lặp lại từ đầu (`tpad=stop_mode=clone`, xem
    `_build_segment`). Verify bằng ffmpeg THẬT: dựng 1 video test 2s có nội dung ĐỔI DẦN
    theo thời gian (`testsrc`), yêu cầu segment 5s — xác nhận (1) file kết quả THẬT SỰ
    dài ~5s (không phải 2s, tức có lấp đủ), VÀ (2) frame ở giây 4.5 (trong vùng lấp thêm)
    GIỐNG HỆT frame ở giây 1.9 (gần cuối clip gốc) — tức đang ĐÓNG BĂNG khung cuối, KHÔNG
    lặp lại từ đầu (nếu còn loop, frame ở giây 4.5 sẽ khớp vị trí ~0.5s của lượt lặp thứ
    3, nội dung testsrc lúc đó khác hẳn frame ở giây 1.9)."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
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
    assert result_duration >= 4.8, f"Segment chỉ dài {result_duration}s dù yêu cầu 5s — video ngắn không được lấp đủ (bug cũ)"

    def _extract_frame(t: float, name: str) -> Path:
        frame_path = tmp_path / name
        subprocess.run([ffmpeg, "-y", "-ss", str(t), "-i", str(out_path), "-frames:v", "1", "-update", "1", str(frame_path)], capture_output=True, check=True, text=True)
        return frame_path

    frame_near_original_end = _extract_frame(1.9, "frame_1_9.png")
    frame_in_padded_tail = _extract_frame(4.5, "frame_4_5.png")

    # So khớp bằng SSIM (không so BYTE thô) — segment ra là H.264 lossy, 2 lần trích frame
    # riêng biệt có thể lệch vài byte pixel do nhiễu nén dù nội dung nhìn giống hệt nhau
    # (đã xác nhận thật: so byte thô của 2 khung ĐÓNG BĂNG thật vẫn lệch ở vài vị trí, SSIM
    # đo được vẫn ra đúng 1.0). SSIM ~1.0 = ảnh giống hệt (đóng băng đúng); nếu lỡ quay lại
    # loop từ đầu, khung ở giây 4.5 sẽ rơi vào ~giữa lượt lặp thứ 3 của `testsrc` — nội
    # dung đổi rõ rệt theo thời gian, SSIM sẽ tụt hẳn xuống thấp, không thể nhầm lẫn.
    ssim_result = subprocess.run(
        [ffmpeg, "-i", str(frame_near_original_end), "-i", str(frame_in_padded_tail), "-filter_complex", "ssim", "-f", "null", "-"],
        capture_output=True, check=True, text=True,
    )
    match = re.search(r"All:([\d.]+)", ssim_result.stderr)
    assert match, f"Không đọc được SSIM từ output ffmpeg: {ssim_result.stderr[-500:]}"
    ssim_score = float(match.group(1))
    assert ssim_score > 0.99, f"SSIM giữa khung gần cuối clip gốc và khung trong vùng lấp thêm chỉ {ssim_score} — nghi ngờ vẫn đang loop lại từ đầu thay vì đóng băng"


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
def test_build_segment_pads_narration_lead_in_and_lead_out_with_silence(tmp_path):
    """Bug thật người dùng báo (2026-08-23): bật hiệu ứng chuyển cảnh (transition khác
    "cut") làm giọng đọc bị "nuốt chữ" ở cả đầu lẫn cuối shot — nguyên nhân là
    `_xfade_chain` cắt/trộn `_XFADE_DURATION_SEC` giây ĐẦU/CUỐI audio, mà audio gốc
    (TTS) lấp ĐẦY nguyên slot, không có khoảng lặng để "hy sinh". Fix: `_build_segment`
    nhận thêm `narration_lead_in_sec`/`narration_lead_out_sec` — đệm lặng vào audio bằng
    `adelay`/`apad` TRƯỚC khi ghép, segment dài thêm đúng bằng phần đệm.

    Verify bằng ffmpeg THẬT: dựng 1 audio "đặc" (tiếng liên tục, không khoảng lặng) dài
    2s, build segment với lead_in=lead_out=0.6s — xác nhận (1) segment DÀI HƠN đúng 1.2s
    (2.0 + 0.6 + 0.6), (2) CÓ khoảng lặng thật ở đúng 0.6s đầu và 0.6s cuối (audio gốc
    "đặc" không hề có khoảng lặng nào — mọi khoảng lặng đo được PHẢI đến từ phần đệm mới
    thêm, không phải ngẫu nhiên từ nguồn)."""
    ffmpeg = shutil.which("ffmpeg")
    image_src = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(image_src)], capture_output=True, check=True, text=True)
    narration = tmp_path / "narration_dac.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(narration)], capture_output=True, check=True, text=True)

    out_path = tmp_path / "segment_padded.mp4"
    _build_segment(
        ffmpeg, str(image_src), str(narration), duration=2.0 + 0.6 + 0.6, out_path=out_path,
        resolution="320:240", video_codec="libx264", audio_codec="aac", crf=28,
        narration_lead_in_sec=0.6, narration_lead_out_sec=0.6,
    )

    result_duration = _ffprobe_duration(out_path)
    assert result_duration == pytest.approx(3.2, abs=0.1)

    proc = subprocess.run(
        [ffmpeg, "-i", str(out_path), "-af", "silencedetect=noise=-40dB:d=0.3", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    silences = re.findall(r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", proc.stderr, re.DOTALL)
    assert silences, f"Không phát hiện khoảng lặng nào — đệm lead-in/lead-out không có tác dụng thật. stderr: {proc.stderr[-800:]}"
    starts = [float(s) for s, _ in silences]
    ends = [float(e) for _, e in silences]
    assert any(s < 0.1 for s in starts), f"Không thấy khoảng lặng bắt đầu ngay từ đầu (đệm lead-in) — starts={starts}"
    assert any(e > result_duration - 0.1 for e in ends), f"Không thấy khoảng lặng kéo dài tới cuối (đệm lead-out) — ends={ends}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_pads_narration_only_at_shots_touching_a_transition(client, project_with_brief):
    """Xác nhận `assemble_video` chỉ đệm lặng ĐÚNG những shot thật sự giáp ranh giới
    transition (khác "cut") — không đệm lãng phí cho shot nối bằng "cut" (không xfade,
    không cần bảo vệ gì). 3 shot: S0→S1 dùng "fade" (cần đệm), S1→S2 dùng "cut" (không
    cần đệm) — kỳ vọng: S0 chỉ đệm ĐUÔI (giáp fade phía sau), S1 chỉ đệm ĐẦU (giáp fade
    phía trước, đuôi giáp cut nên không đệm), S2 không đệm gì (giáp cut, là shot cuối)."""
    from app.config import project_dir
    from app.render.assembly import _XFADE_DURATION_SEC as XFADE

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:02", "Image", "Canh 1", "", "Loi thoai mot."],
        ["B02", "0:02–0:04", "Image", "Canh 2", "", "Loi thoai hai."],
        ["B03", "0:04–0:06", "Image", "Canh 3", "", "Loi thoai ba."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_ids = [s["shot_id"] for s in client.post(f"/projects/{pid}/visual/generate").json()["shots"]]
    assert len(shot_ids) == 3

    resp = client.patch(f"/projects/{pid}/visual/shots/{shot_ids[0]}", json={"transition_to_next": "fade"})
    assert resp.status_code == 200, resp.text
    resp = client.patch(f"/projects/{pid}/visual/shots/{shot_ids[1]}", json={"transition_to_next": "cut"})
    assert resp.status_code == 200, resp.text

    pdir = project_dir(channel_id, pid)
    base_durations = [1.5, 1.8, 1.2]
    for shot_id, dur in zip(shot_ids, base_durations):
        png = pdir / "assets" / f"{shot_id}.png"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)
        wav = pdir / "assets" / f"{shot_id}.wav"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", str(wav)], capture_output=True, check=True, text=True)

    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus

    shot_statuses = [
        ShotRenderStatus(
            shot_id=shot_id, visual_status="ready", visual_asset_path=str(pdir / "assets" / f"{shot_id}.png"), approved=True,
            narration_status="ready", narration_asset_path=str(pdir / "assets" / f"{shot_id}.wav"), narration_duration_sec=_ffprobe_duration(pdir / "assets" / f"{shot_id}.wav"),
        )
        for shot_id in shot_ids
    ]
    write_json(pdir / "render.json", RenderState(project_id=pid, shots=shot_statuses).model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")

    seg_dir = pdir / "renders" / "segments"
    seg_durations = [_ffprobe_duration(seg_dir / f"segment_{i:03d}.mp4") for i in range(3)]
    real_base = [_ffprobe_duration(pdir / "assets" / f"{shot_id}.wav") for shot_id in shot_ids]

    assert seg_durations[0] == pytest.approx(real_base[0] + XFADE, abs=0.1), "S0 giáp fade PHÍA SAU — phải đệm ĐUÔI"
    assert seg_durations[1] == pytest.approx(real_base[1] + XFADE, abs=0.1), "S1 giáp fade PHÍA TRƯỚC (đuôi giáp cut, không đệm) — chỉ đệm ĐẦU"
    assert seg_durations[2] == pytest.approx(real_base[2], abs=0.1), "S2 giáp cut cả 2 phía (shot cuối) — KHÔNG đệm gì"


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


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_with_intro_and_all_transitions_does_not_drop_last_shot(client, project_with_brief):
    """Bug thật người dùng báo (2026-08-23): shot CUỐI (ảnh + giọng đọc) "biến mất" khỏi
    video ghép khi project vừa CÓ intro riêng VỪA dùng transition (khác "cut") ở MỌI ranh
    giới shot. Xác nhận nguyên nhân gốc bằng ffmpeg/ffprobe THẬT (không suy đoán, xem
    IMPLEMENTATION_REPORT.md mục 76): `_xfade_chain` (ghép shot-to-shot qua transition)
    ra `body_path` với video track TẦN SỐ KHUNG HÌNH KHÔNG ỔN ĐỊNH — mỗi bước là 1
    `_concat_fast` (concat DEMUXER, `-c copy`) nối "head" (stream-copy cắt dở
    `current_path`) với "blend" (re-encode xfade/acrossfade riêng, timestamp bắt đầu từ 0
    ĐỘC LẬP) — 2 nguồn timestamp khác nhau ghép bằng stream-copy tích luỹ lệch qua từng
    bước. Khi `_concat_intro_and_body` (filter `concat`) ghép tiếp `body_path` này với
    intro (CFR sạch), ffmpeg gặp audio DTS không tăng đơn điệu và tự ý DROP hẳn ~2.3s
    frame video CUỐI (đúng bằng độ dài shot cuối) — KHÔNG raise exception, KHÔNG ghi gì
    vào `assembly_error` (ffmpeg exit code 0, "drop" chỉ in ở stdout summary). Fix
    (`assemble_video`): chuẩn hoá `body_path` về CFR sạch (`-vsync cfr` + `aresample=
    async=1:first_pts=0`) trước khi đưa vào `_concat_intro_and_body`, CHỈ khi có CẢ intro
    LẪN transition (2 điều kiện cùng lúc mới lộ bug này).

    Verify bằng ffmpeg THẬT: cố ý đặt shot CUỐI NGẮN NHẤT (đúng đặc điểm dễ "biến mất"
    nhất của bug thật) — tổng duration video ra phải gần đúng lý thuyết (intro + tổng
    slot shot - overlap xfade), KHÔNG được ngắn hơn hẳn (dấu hiệu 1 shot bị drop hoàn
    toàn)."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import _XFADE_DURATION_SEC, assemble_video
    from app.render.schemas import IntroAssetStatus, RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai block mot."],
        ["B02", "0:03–0:06", "Image", "Canh 2", "", "Loi thoai block hai."],
        ["B03", "0:06–0:09", "Image", "Canh 3", "", "Loi thoai block ba, la shot cuoi cung."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_ids = [s["shot_id"] for s in client.post(f"/projects/{pid}/visual/generate").json()["shots"]]
    assert len(shot_ids) == 3

    # MỌI ranh giới shot dùng transition khác "cut" — đúng kịch bản lỗi thật.
    for shot_id, transition in zip(shot_ids[:-1], ["fade", "fadeblack"]):
        resp = client.patch(f"/projects/{pid}/visual/shots/{shot_id}", json={"transition_to_next": transition})
        assert resp.status_code == 200, resp.text

    pdir = project_dir(channel_id, pid)
    shot_statuses = []
    shot_durations = [2.5, 3.0, 2.0]  # shot CUỐI ngắn nhất — đúng đặc điểm bug thật
    for shot_id, dur in zip(shot_ids, shot_durations):
        png = pdir / "assets" / f"{shot_id}.png"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)
        wav = pdir / "assets" / f"{shot_id}.wav"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", str(wav)], capture_output=True, check=True, text=True)
        shot_statuses.append(ShotRenderStatus(
            shot_id=shot_id, visual_status="ready", visual_asset_path=str(png), approved=True,
            narration_status="ready", narration_asset_path=str(wav), narration_duration_sec=_ffprobe_duration(wav),
        ))

    intro_src = pdir / "assets" / "intro_src.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(intro_src)],
        capture_output=True, check=True, text=True,
    )
    intro_dur = _ffprobe_duration(intro_src)

    state = RenderState(
        project_id=pid, shots=shot_statuses,
        intro=IntroAssetStatus(kind="video", visual_asset_path=str(intro_src), transition_to_next="cut"),
    )
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    result_duration = _ffprobe_duration(Path(final_state["final_video_path"]))

    expected_total = intro_dur + sum(s.narration_duration_sec for s in shot_statuses) - 2 * _XFADE_DURATION_SEC
    assert result_duration > expected_total - 1.0, (
        f"Video ra dài {result_duration}s — ngắn hơn hẳn kỳ vọng ({expected_total}s), "
        "nghi ngờ shot cuối bị ffmpeg concat filter drop mất — đúng bug thật đã sửa (mục 76)"
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_with_intro_and_no_transitions_does_not_drop_last_shot(client, project_with_brief):
    """Bug thật người dùng báo lại (2026-08-26, project short-form thật "Đính chính lầm
    tưởng..."): shot CUỐI vẫn "biến mất" dù project KHÔNG dùng transition nào (mọi ranh
    giới "cut" mặc định) — CHỈ có intro riêng. Test `test_assemble_with_intro_and_all_
    transitions_does_not_drop_last_shot` ở trên (mục 76) chỉ phủ nhánh CÓ transition; fix
    lúc đó cố tình CHỈ chuẩn hoá CFR cho nhánh đó, với lý do (SAI, xem sửa lại mục 78 mới)
    "nhánh không-transition dùng concat DEMUXER, cùng nguồn `_build_segment` nên không gặp
    lệch". Tái hiện THẬT trên chính project người dùng báo lỗi (`prj_1787673042428`, xem
    IMPLEMENTATION_REPORT.md mục mới): concat DEMUXER `-c copy` VẪN có thể giữ nguyên
    timebase/DTS không đều tuỳ input gốc, KHÔNG chỉ riêng đường `_xfade_chain` — khi
    `_concat_intro_and_body` ghép `body_path` (từ concat demuxer) với intro, ffmpeg vẫn
    silently drop shot cuối y hệt bug mục 76. Fix: chuyển bước CFR-normalize ra áp dụng
    MỌI khi có intro, bất kể `has_transitions`."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import IntroAssetStatus, RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai block mot."],
        ["B02", "0:03–0:06", "Image", "Canh 2", "", "Loi thoai block hai."],
        ["B03", "0:06–0:09", "Image", "Canh 3", "", "Loi thoai block ba, la shot cuoi cung."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_ids = [s["shot_id"] for s in client.post(f"/projects/{pid}/visual/generate").json()["shots"]]
    assert len(shot_ids) == 3
    # KHÔNG patch transition_to_next của bất kỳ shot nào — giữ mặc định "cut" (has_transitions=False).

    pdir = project_dir(channel_id, pid)
    shot_statuses = []
    shot_durations = [2.5, 3.0, 2.0]  # shot CUỐI ngắn nhất — đúng đặc điểm bug thật
    for shot_id, dur in zip(shot_ids, shot_durations):
        png = pdir / "assets" / f"{shot_id}.png"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)
        wav = pdir / "assets" / f"{shot_id}.wav"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", str(wav)], capture_output=True, check=True, text=True)
        shot_statuses.append(ShotRenderStatus(
            shot_id=shot_id, visual_status="ready", visual_asset_path=str(png), approved=True,
            narration_status="ready", narration_asset_path=str(wav), narration_duration_sec=_ffprobe_duration(wav),
        ))

    intro_src = pdir / "assets" / "intro_src.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(intro_src)],
        capture_output=True, check=True, text=True,
    )
    intro_dur = _ffprobe_duration(intro_src)

    state = RenderState(
        project_id=pid, shots=shot_statuses,
        intro=IntroAssetStatus(kind="video", visual_asset_path=str(intro_src), transition_to_next="cut"),
    )
    write_json(pdir / "render.json", state.model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low")

    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")
    result_duration = _ffprobe_duration(Path(final_state["final_video_path"]))

    expected_total = intro_dur + sum(s.narration_duration_sec for s in shot_statuses)
    assert result_duration > expected_total - 1.0, (
        f"Video ra dài {result_duration}s — ngắn hơn hẳn kỳ vọng ({expected_total}s), "
        "nghi ngờ shot cuối bị ffmpeg concat filter drop mất dù KHÔNG dùng transition nào"
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
    _reflow_video_durations(statuses, durations, "vi", "vi")

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
    _reflow_video_durations(statuses, durations, "vi", "vi")

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
    _reflow_video_durations(statuses, durations, "vi", "vi")

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
    _reflow_video_durations(statuses, durations, "vi", "vi")
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
    _reflow_video_durations(statuses, durations, "vi", "vi")
    assert durations[0] == 5.0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_reflow_does_not_shrink_video_shot_below_its_own_ready_narration(tmp_path):
    """Bug thật người dùng báo (2026-08-26): shot VIDEO ngắn hơn giọng đọc CỦA CHÍNH NÓ
    (VD video AI ~2s nhưng giọng đọc dài 6s) bị CẮT CỤT giọng đọc khi chuyển sang shot kế
    — vòng lặp reflow trước đây LUÔN co `durations[i]` về đúng độ dài video thật (2s), bất
    kể `durations[i]` đang dài hơn (6s) vì CHÍNH giọng đọc shot đó, không phải vì lý do gì
    khác. Fix: sàn `_narration_floor` — không bao giờ co xuống dưới giọng đọc của chính
    shot khi giọng đọc đã sẵn sàng (`narration_status=="ready"`)."""
    from app.render.assembly import _reflow_video_durations
    from app.render.schemas import ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    short_video = tmp_path / "short.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(short_video)],
        capture_output=True, check=True, text=True,
    )
    assert round(_ffprobe_duration(short_video)) == 2  # video thật NGẮN HƠN giọng đọc bên dưới (6s)

    statuses = [
        ShotRenderStatus(shot_id="s1", visual_asset_path=str(short_video), narration_status="ready", narration_duration_sec=6.0),
        ShotRenderStatus(shot_id="s2", visual_asset_path=None),
    ]
    durations = [6.0, 3.0]  # durations[0] khởi tạo = narration_duration_sec, đúng theo _shot_base_duration thật
    _reflow_video_durations(statuses, durations, "vi", "vi")

    assert durations[0] == 6.0, f"Shot video bị co xuống {durations[0]}s dù giọng đọc CỦA CHÍNH NÓ dài 6s — sẽ bị _build_segment cắt cụt audio"
    assert durations[1] == 3.0  # không vay/trả gì — video "ngắn hơn" chỉ vì lý do giọng đọc của chính nó, không phải lệch thật cần bù


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_video_shot_shorter_than_narration_does_not_truncate_audio(client, project_with_brief):
    """Verify END-TO-END qua đúng `assemble_video()` thật (không chỉ unit-test hàm
    reflow riêng): 1 shot VIDEO 2s + giọng đọc 6s — segment ra phải dài ĐỦ ~6s (đóng băng
    khung cuối lấp phần thiếu, xem `_build_segment`), KHÔNG bị cắt còn ~2s theo độ dài
    video gốc — đúng bug thật người dùng báo khi chuyển shot làm giọng đọc bị cắt cụt."""
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:06", "Video", "Canh video ngan", "", "Loi thoai dai hon video that nhieu."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    from app.config import project_dir
    from app.filestore import write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    pdir = project_dir(channel_id, pid)
    video_path = pdir / "assets" / f"{shot_id}.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path)], capture_output=True, check=True, text=True)
    wav_path = pdir / "assets" / f"{shot_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(wav_path)], capture_output=True, check=True, text=True)
    narration_dur = _ffprobe_duration(wav_path)
    assert round(narration_dur) == 6

    write_json(pdir / "render.json", RenderState(project_id=pid, shots=[
        ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(video_path), approved=True,
                          narration_status="ready", narration_asset_path=str(wav_path), narration_duration_sec=narration_dur),
    ]).model_dump())

    resp = client.post(f"/projects/{pid}/render/assemble", json={"resolution": "720p", "codec": "h264", "quality": "low"})
    assert resp.status_code == 200, resp.text
    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")

    result_duration = _ffprobe_duration(Path(final_state["final_video_path"]))
    assert result_duration >= 5.7, f"Video ra chỉ dài {result_duration}s — giọng đọc 6s có vẻ đã bị cắt cụt theo độ dài video gốc (2s)"


def _silence_ranges(ffmpeg: str, path) -> list[tuple[float, float]]:
    """Chạy `silencedetect` thật lên audio đã ghép — trả list (start, end) các khoảng lặng
    thật sự (không tiếng, kể cả silence do `apad` đệm cho transition) — dùng để xác nhận
    KHÔNG có khoảng lặng bất thường nào lọt VÀO GIỮA nội dung giọng đọc thật (sine tone),
    ngoài đúng 1 khoảng ở ranh giới transition đã biết trước."""
    result = subprocess.run(
        [ffmpeg, "-i", str(path), "-af", "silencedetect=noise=-30dB:d=0.1", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", result.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", result.stderr)]
    return list(zip(starts, ends))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_freeze_video_shot_lead_out_before_transition_does_not_truncate_narration(client, project_with_brief):
    """Kết hợp 2 tính năng: shot VIDEO ngắn hơn giọng đọc (đóng băng khung cuối, mục 81)
    NẰM NGAY TRƯỚC 1 ranh giới transition (cần đệm lặng `narration_lead_out_sec`, mục 57)
    — người dùng yêu cầu xác nhận đệm lặng transition vẫn hoạt động đúng cho shot video
    bị đóng băng, không chỉ ảnh tĩnh. Verify bằng `silencedetect` thật: CHỈ 1 khoảng lặng
    (đúng vùng đệm transition) xuất hiện SAU khi giọng đọc 6s đã phát HẾT — không có
    khoảng lặng nào lọt vào giữa 6s giọng đọc (tức không bị cắt cụt bởi khung hình đóng
    băng ngắn hơn giọng đọc)."""
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:06", "Video", "Canh video ngan", "", "Loi thoai dai hon video that nhieu, can nghe het khong bi cat."],
        ["B02", "0:06–0:09", "Image", "Canh anh", "", "Loi thoai shot hai."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shots = client.post(f"/projects/{pid}/visual/generate").json()["shots"]
    shot_a, shot_b = shots[0]["shot_id"], shots[1]["shot_id"]
    resp = client.patch(f"/projects/{pid}/visual/shots/{shot_a}", json={"transition_to_next": "fade"})
    assert resp.status_code == 200, resp.text

    from app.config import project_dir
    from app.filestore import write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    pdir = project_dir(channel_id, pid)
    video_a = pdir / "assets" / f"{shot_a}.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_a)], capture_output=True, check=True, text=True)
    wav_a = pdir / "assets" / f"{shot_a}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(wav_a)], capture_output=True, check=True, text=True)
    narr_a_dur = _ffprobe_duration(wav_a)

    png_b = pdir / "assets" / f"{shot_b}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240", "-frames:v", "1", "-update", "1", str(png_b)], capture_output=True, check=True, text=True)
    wav_b = pdir / "assets" / f"{shot_b}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=3", str(wav_b)], capture_output=True, check=True, text=True)
    narr_b_dur = _ffprobe_duration(wav_b)

    write_json(pdir / "render.json", RenderState(project_id=pid, shots=[
        ShotRenderStatus(shot_id=shot_a, visual_status="ready", visual_asset_path=str(video_a), approved=True,
                          narration_status="ready", narration_asset_path=str(wav_a), narration_duration_sec=narr_a_dur),
        ShotRenderStatus(shot_id=shot_b, visual_status="ready", visual_asset_path=str(png_b), approved=True,
                          narration_status="ready", narration_asset_path=str(wav_b), narration_duration_sec=narr_b_dur),
    ]).model_dump())

    resp = client.post(f"/projects/{pid}/render/assemble", json={"resolution": "720p", "codec": "h264", "quality": "low"})
    assert resp.status_code == 200, resp.text
    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")

    ranges = _silence_ranges(ffmpeg, final_state["final_video_path"])
    assert len(ranges) == 1, f"Kỳ vọng đúng 1 khoảng lặng (vùng đệm transition), thấy {len(ranges)}: {ranges}"
    silence_start, _silence_end = ranges[0]
    assert silence_start >= narr_a_dur - 0.2, (
        f"Khoảng lặng bắt đầu ở {silence_start}s, TRƯỚC khi giọng đọc {narr_a_dur}s phát xong — "
        "nghi ngờ đóng băng khung hình video ngắn làm giọng đọc bị cắt cụt sớm"
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_freeze_video_shot_lead_in_after_transition_does_not_truncate_narration(client, project_with_brief):
    """Chiều NGƯỢC lại của test trên: shot VIDEO ngắn hơn giọng đọc nằm NGAY SAU 1 ranh
    giới transition (cần đệm lặng `narration_lead_in_sec`) — verify giọng đọc CỦA SHOT
    VIDEO (6s) phát đủ, không bị cắt cụt vì khung hình đóng băng."""
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:03", "Image", "Canh anh", "", "Loi thoai shot mot."],
        ["B02", "0:03–0:09", "Video", "Canh video ngan", "", "Loi thoai dai hon video that nhieu, can nghe het khong bi cat dau."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shots = client.post(f"/projects/{pid}/visual/generate").json()["shots"]
    shot_a, shot_b = shots[0]["shot_id"], shots[1]["shot_id"]
    resp = client.patch(f"/projects/{pid}/visual/shots/{shot_a}", json={"transition_to_next": "fade"})
    assert resp.status_code == 200, resp.text

    from app.config import project_dir
    from app.filestore import write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    pdir = project_dir(channel_id, pid)
    png_a = pdir / "assets" / f"{shot_a}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(png_a)], capture_output=True, check=True, text=True)
    wav_a = pdir / "assets" / f"{shot_a}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=3", str(wav_a)], capture_output=True, check=True, text=True)
    narr_a_dur = _ffprobe_duration(wav_a)

    video_b = pdir / "assets" / f"{shot_b}.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_b)], capture_output=True, check=True, text=True)
    wav_b = pdir / "assets" / f"{shot_b}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(wav_b)], capture_output=True, check=True, text=True)
    narr_b_dur = _ffprobe_duration(wav_b)

    write_json(pdir / "render.json", RenderState(project_id=pid, shots=[
        ShotRenderStatus(shot_id=shot_a, visual_status="ready", visual_asset_path=str(png_a), approved=True,
                          narration_status="ready", narration_asset_path=str(wav_a), narration_duration_sec=narr_a_dur),
        ShotRenderStatus(shot_id=shot_b, visual_status="ready", visual_asset_path=str(video_b), approved=True,
                          narration_status="ready", narration_asset_path=str(wav_b), narration_duration_sec=narr_b_dur),
    ]).model_dump())

    resp = client.post(f"/projects/{pid}/render/assemble", json={"resolution": "720p", "codec": "h264", "quality": "low"})
    assert resp.status_code == 200, resp.text
    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")

    total_dur = _ffprobe_duration(Path(final_state["final_video_path"]))
    ranges = _silence_ranges(ffmpeg, final_state["final_video_path"])
    assert len(ranges) == 1, f"Kỳ vọng đúng 1 khoảng lặng (vùng đệm transition), thấy {len(ranges)}: {ranges}"
    _silence_start, silence_end = ranges[0]
    # Sau khoảng lặng transition, giọng đọc shot B (6s) phải phát ĐỦ tới cuối video — không
    # còn khoảng lặng nào khác nghĩa là không có gì cắt cụt nó giữa chừng.
    assert total_dur - silence_end >= narr_b_dur - 0.3, (
        f"Chỉ còn {total_dur - silence_end}s sau vùng đệm transition, KHÔNG đủ cho giọng đọc "
        f"{narr_b_dur}s của shot video — nghi ngờ bị cắt cụt"
    )


# ---------------------------------------------------------------------------
# Camera motion (Ken Burns) cho ảnh tĩnh — 2026-08-19, theo yêu cầu người dùng.
# ---------------------------------------------------------------------------
def test_build_camera_motion_filter_none_and_invalid_return_none():
    from app.render.camera_motion import build_camera_motion_filter

    assert build_camera_motion_filter("none", 3.0, 640, 480, 25) is None
    assert build_camera_motion_filter("khong-ton-tai", 3.0, 640, 480, 25) is None


def test_build_camera_motion_filter_covers_every_real_motion():
    """Mỗi key trong CAMERA_MOTIONS (trừ "none") phải build được filter string hợp lệ —
    bắt lỗi gõ sai biến/cú pháp trong biểu thức ffmpeg ở TỪNG nhánh, không cần chạy ffmpeg
    thật (nhanh, chạy mọi lần commit)."""
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
def test_camera_motion_crops_to_target_aspect_instead_of_distorting(tmp_path):
    """**Bug thật (2026-09-12)**, phát hiện lúc người dùng test tính năng xuất short-video
    9:16: ảnh nguồn 16:9 bị "co lại"/méo khi ghép vào khung DỌC (9:16) dù đã fix
    `_resolve_scale_filter` sang `aspect_fill_mode="crop"` (mục 138) — vì shot có
    `camera_motion != "none"` (Ken Burns, ĐA SỐ shot thực tế) đi qua NHÁNH RIÊNG của
    `_build_segment` (đọc `motion_filter`), hoàn toàn KHÔNG gọi `_resolve_scale_filter`.
    `build_camera_motion_filter` cũ đưa thẳng ảnh gốc vào `zoompan` rồi ép `s={out_w}x
    {out_h}` — với input/output khác tỷ lệ khung (VD 4:3 → khung DỌC ở đây), `zoompan`
    KHÔNG tự giữ tỷ lệ, kết quả bị BÓP MÉO (stretch/squish) thay vì crop 2 bên.

    Verify: ảnh test `_corner_test_image` (640x480, 4 ô màu góc + ô đen giữa) ghép vào
    khung DỌC RẤT hẹp (`1080:1920` — cùng độ phân giải short-export thật dùng) với
    `camera_motion="zoom_in"` (frame ĐẦU, zoom≈1.0 — gần như chưa zoom, phản ánh đúng
    hành vi cover-crop tĩnh). Cover-crop ĐÚNG (đã tính tay theo công thức
    `force_original_aspect_ratio=increase`+`crop`) chỉ giữ lại dải giữa chiều rộng gốc
    (x≈[185,455] trong ảnh 640px) — 2 ô góc trái/phải (x∈[0,100) và x∈[540,640)) phải bị
    CẮT MẤT HOÀN TOÀN, không còn xuất hiện ở rìa trái/phải khung xuất — khác hẳn bug cũ
    (bóp méo, ô góc vẫn xuất hiện ở rìa, chỉ hẹp lại)."""
    ffmpeg = shutil.which("ffmpeg")
    src = tmp_path / "test.png"
    _corner_test_image(ffmpeg, src)

    out_path = tmp_path / "zoom_in_vertical.mp4"
    _build_segment(
        ffmpeg, str(src), None, duration=2.0, out_path=out_path,
        resolution="1080:1920", video_codec="libx264", audio_codec="aac", crf=28, camera_motion="zoom_in",
    )
    frame = tmp_path / "f0.png"
    _extract_frame(ffmpeg, out_path, frame)

    # Rìa TRÁI khung xuất (x=10) — cover-crop đúng map về x≈187 gốc (nền trắng, NGOÀI ô đỏ
    # x∈[0,100)) → phải là TRẮNG. Bug cũ (bóp méo, không crop) map về x≈6 gốc (TRONG ô đỏ)
    # → sẽ ra ĐỎ, test này FAIL đúng lúc đó.
    left_edge = _pixel_rgb(ffmpeg, frame, 10, 10)
    assert _approx_rgb(left_edge, (255, 255, 255)), f"Rìa trái phải là nền trắng (đã crop mất ô đỏ góc) — đo được {left_edge}, nghi ngờ bị bóp méo thay vì crop"
    # Rìa PHẢI (x=1070) — cùng lý do, map về x≈453 gốc (nền trắng, NGOÀI ô xanh lá
    # x∈[540,640)) → phải là TRẮNG. Bug cũ map về x≈634 gốc (TRONG ô xanh lá) → ra XANH LÁ.
    right_edge = _pixel_rgb(ffmpeg, frame, 1070, 10)
    assert _approx_rgb(right_edge, (255, 255, 255)), f"Rìa phải phải là nền trắng (đã crop mất ô xanh lá góc) — đo được {right_edge}, nghi ngờ bị bóp méo thay vì crop"


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
# PATCH /projects/{id}/visual/shots/bulk — bulk edit transition_to_next/camera_motion
# cho nhiều shot cùng lúc (mới 2026-09-10), theo yêu cầu người dùng ở Visual Studio.
# ---------------------------------------------------------------------------
def test_patch_shots_bulk_applies_transition_to_selected_shots_only(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    shot_ids = [s["shot_id"] for s in pack["shots"]]
    assert len(shot_ids) >= 3
    target_ids = shot_ids[:2]  # chỉ 2/N shot — xác nhận KHÔNG đụng shot còn lại

    resp = client.patch(f"/projects/{pid}/visual/shots/bulk", json={"shot_ids": target_ids, "transition_to_next": "fade"})
    assert resp.status_code == 200
    by_id = {s["shot_id"]: s for s in resp.json()["shots"]}
    for sid in target_ids:
        assert by_id[sid]["transition_to_next"] == "fade"
    for sid in shot_ids[2:]:
        assert by_id[sid].get("transition_to_next", "cut") == "cut"  # mặc định, KHÔNG bị đổi


def test_patch_shots_bulk_applies_camera_motion_to_all_shots(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    shot_ids = [s["shot_id"] for s in pack["shots"]]

    resp = client.patch(f"/projects/{pid}/visual/shots/bulk", json={"shot_ids": shot_ids, "camera_motion": "zoom_in"})
    assert resp.status_code == 200
    for s in resp.json()["shots"]:
        assert s["camera_motion"] == "zoom_in"


def test_patch_shots_bulk_can_set_both_fields_at_once(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    shot_id = pack["shots"][0]["shot_id"]

    resp = client.patch(f"/projects/{pid}/visual/shots/bulk", json={"shot_ids": [shot_id], "transition_to_next": "dissolve", "camera_motion": "pan_left"})
    assert resp.status_code == 200
    patched = next(s for s in resp.json()["shots"] if s["shot_id"] == shot_id)
    assert patched["transition_to_next"] == "dissolve"
    assert patched["camera_motion"] == "pan_left"


def test_patch_shots_bulk_rejects_when_no_field_given(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    resp = client.patch(f"/projects/{pid}/visual/shots/bulk", json={"shot_ids": [pack["shots"][0]["shot_id"]]})
    assert resp.status_code == 400


def test_patch_shots_bulk_rejects_invalid_transition(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    resp = client.patch(f"/projects/{pid}/visual/shots/bulk", json={"shot_ids": [pack["shots"][0]["shot_id"]], "transition_to_next": "khong-ton-tai"})
    assert resp.status_code == 400


def test_patch_shots_bulk_rejects_invalid_camera_motion(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    pack = client.get(f"/projects/{pid}/pack").json()
    resp = client.patch(f"/projects/{pid}/visual/shots/bulk", json={"shot_ids": [pack["shots"][0]["shot_id"]], "camera_motion": "khong-ton-tai"})
    assert resp.status_code == 400


def test_patch_shots_bulk_404_when_no_shot_ids_match(client, project_with_brief):
    pid = _drive_to_visual_studio(client, project_with_brief)
    resp = client.patch(f"/projects/{pid}/visual/shots/bulk", json={"shot_ids": ["khong-ton-tai"], "transition_to_next": "fade"})
    assert resp.status_code == 404


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


# ---------------------------------------------------------------------------
# "Xuất Pack" (2026-08-26) — thay "Output A" cũ (export markdown/JSON spec-only) bằng 1
# bundle THỰC DÙNG ĐƯỢC NGAY: transcript SRT, asset ảnh/video từng shot đặt tên theo
# shot_id, giọng đọc ghép full mp3, video đã ghép (nếu có). Xem app/render/pack_export.py.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_export_pack_bundle_writes_srt_assets_and_narration_but_skips_missing_video(client, project_with_brief, tmp_path):
    """Chưa ghép video (`render/assemble` chưa gọi) — bundle vẫn xuất ĐỦ 3 phần còn lại
    (SRT + assets + narration mp3), chỉ `video_final` bị `skipped` kèm lý do rõ ràng
    (KHÔNG lỗi cả request — đúng nguyên tắc "lỗi 1 phần không chặn cả export")."""
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai block mot."],
        ["B02", "0:03–0:06", "Image", "Canh 2", "", "Loi thoai block hai, la shot cuoi."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_ids = [s["shot_id"] for s in client.post(f"/projects/{pid}/visual/generate").json()["shots"]]
    assert len(shot_ids) == 2

    from app.config import project_dir
    from app.filestore import write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    pdir = project_dir(channel_id, pid)
    shot_statuses = []
    for shot_id, dur in zip(shot_ids, [1.5, 2.0]):
        png = pdir / "assets" / f"{shot_id}.png"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)
        wav = pdir / "assets" / f"{shot_id}.wav"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", str(wav)], capture_output=True, check=True, text=True)
        shot_statuses.append(ShotRenderStatus(
            shot_id=shot_id, visual_status="ready", visual_asset_path=str(png), approved=True,
            narration_status="ready", narration_asset_path=str(wav), narration_duration_sec=_ffprobe_duration(wav),
        ))
    write_json(pdir / "render.json", RenderState(project_id=pid, shots=shot_statuses).model_dump())

    dest = tmp_path / "pack_export"
    resp = client.post(f"/projects/{pid}/export/pack-bundle", json={"dest_dir": str(dest)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["included"] == ["transcript_vi.srt", "script_vi.txt", "assets/", "narration_full_vi.mp3"]
    assert len(body["skipped"]) == 1 and body["skipped"][0]["item"] == "video_final"

    srt_text = (dest / "transcript_vi.srt").read_text(encoding="utf-8")
    assert "Loi thoai block mot." in srt_text
    assert "Loi thoai block hai, la shot cuoi." in srt_text
    assert "-->" in srt_text

    for shot_id in shot_ids:
        assert (dest / "assets" / f"{shot_id}.png").exists()

    # Hậu tố ngôn ngữ (2026-09-11, theo yêu cầu người dùng) — ngôn ngữ chính của kênh
    # test này là "vi" (mặc định BrandProfile), nên narration_full giờ tên
    # "narration_full_vi.mp3" thay vì "narration_full.mp3" cũ (nhất quán với
    # `video_final_<lang>`).
    narration_out = dest / "narration_full_vi.mp3"
    assert narration_out.exists()
    assert _ffprobe_duration(narration_out) > 3.0  # ~1.5+2.0s, khớp 2 shot ghép liền


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_export_pack_bundle_includes_final_video_after_assemble(client, project_with_brief, tmp_path):
    """Sau khi `render/assemble` xong — bundle phải kèm `video_final_<lang>.*` (mới
    2026-09-11 — hậu tố ngôn ngữ, theo yêu cầu người dùng; `lang` mặc định = ngôn ngữ
    chính của kênh, "vi" cho project test này), không còn nằm trong `skipped`."""
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_ids = [s["shot_id"] for s in client.post(f"/projects/{pid}/visual/generate").json()["shots"]]

    from app.config import project_dir
    from app.filestore import write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    pdir = project_dir(channel_id, pid)
    shot_id = shot_ids[0]
    png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)
    wav = pdir / "assets" / f"{shot_id}.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5", str(wav)], capture_output=True, check=True, text=True)
    write_json(pdir / "render.json", RenderState(project_id=pid, shots=[
        ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(png), approved=True,
                          narration_status="ready", narration_asset_path=str(wav), narration_duration_sec=_ffprobe_duration(wav)),
    ]).model_dump())

    resp = client.post(f"/projects/{pid}/render/assemble", json={"resolution": "720p", "codec": "h264", "quality": "low"})
    assert resp.status_code == 200, resp.text

    dest = tmp_path / "pack_export_2"
    resp = client.post(f"/projects/{pid}/export/pack-bundle", json={"dest_dir": str(dest)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "video_final_vi.mp4" in body["included"]  # "vi" — ngôn ngữ chính mặc định của project test này
    assert body["skipped"] == []
    assert (dest / "video_final_vi.mp4").exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_export_pack_bundle_video_filename_uses_final_video_lang_not_primary(client, project_with_brief, tmp_path):
    """Mới (2026-09-11) — hậu tố tên file `video_final_<lang>` phải khớp `RenderState.
    final_video_lang` (ngôn ngữ THẬT SỰ đã dùng lúc ghép gần nhất), KHÔNG PHẢI luôn luôn
    ngôn ngữ chính của kênh — ghép bằng ngôn ngữ "en" thì file phải tên
    `video_final_en.mp4` dù kênh có ngôn ngữ chính "vi"."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.assembly import assemble_video
    from app.render.schemas import RenderState, ShotRenderStatus, TranslatedNarrationStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)
    en_wav = pdir / "assets" / f"{shot_id}_en.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5", str(en_wav)], capture_output=True, check=True, text=True)
    write_json(pdir / "render.json", RenderState(project_id=pid, shots=[
        ShotRenderStatus(
            shot_id=shot_id, visual_status="ready", visual_asset_path=str(png), approved=True,
            narration_translations={"en": TranslatedNarrationStatus(narration_status="ready", narration_asset_path=str(en_wav), narration_duration_sec=_ffprobe_duration(en_wav))},
        ),
    ]).model_dump())

    assemble_video(pid, resolution="720p", codec="h264", quality="low", lang="en")

    dest = tmp_path / "pack_export_3"
    resp = client.post(f"/projects/{pid}/export/pack-bundle", json={"dest_dir": str(dest)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "video_final_en.mp4" in body["included"]
    assert (dest / "video_final_en.mp4").exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_export_pack_bundle_video_filename_falls_back_to_primary_lang_for_old_render_state(client, project_with_brief, tmp_path):
    """`final_video_lang` là `None` cho render.json ghi TRƯỚC khi có tính năng chọn ngôn
    ngữ xuất video (2026-09-11) — mô phỏng lại bằng cách ghi thẳng `RenderState` không
    set field này (mặc định `None` từ Pydantic) — tên file phải fallback về ngôn ngữ
    CHÍNH của kênh, không được lỗi/thiếu hậu tố."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]
    pdir = project_dir(channel_id, pid)

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    final_dir = pdir / "renders"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_video = final_dir / "final.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-pix_fmt", "yuv420p", str(final_video)], capture_output=True, check=True, text=True)

    state = RenderState(project_id=pid, shots=[ShotRenderStatus(shot_id=shot_id, visual_status="ready")])
    state.assembly_status = "done"
    state.final_video_path = str(final_video)
    # `final_video_lang` KHÔNG set — giữ mặc định `None`, đúng mô phỏng render cũ.
    write_json(pdir / "render.json", state.model_dump())

    dest = tmp_path / "pack_export_4"
    resp = client.post(f"/projects/{pid}/export/pack-bundle", json={"dest_dir": str(dest)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "video_final_vi.mp4" in body["included"]  # fallback đúng ngôn ngữ chính "vi"
    assert (dest / "video_final_vi.mp4").exists()


def test_export_pack_bundle_requires_dest_dir(client, project_with_brief):
    resp = client.post(f"/projects/{project_with_brief['id']}/export/pack-bundle", json={"dest_dir": ""})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Mở rộng render engine theo BrandProfile — CHANGE_Semantic_BRoll_Asset_Vault.md §9b.
# Mặc định (brand=None/rỗng) PHẢI giữ NGUYÊN hành vi cũ — mọi test dưới đây verify CẢ
# "không cấu hình = không đổi gì" LẪN "có cấu hình = hiệu ứng thật sự áp dụng".
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_color_grade_preset_changes_pixels_vs_default(tmp_path):
    from app.render.assembly import _build_segment

    ffmpeg = shutil.which("ffmpeg")
    png = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)

    default_out = tmp_path / "default.mp4"
    _build_segment(ffmpeg, str(png), None, 1.0, default_out, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=23, brand=None)
    graded_out = tmp_path / "graded.mp4"
    _build_segment(ffmpeg, str(png), None, 1.0, graded_out, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=23, brand={"visual_grade": "moody_dark"})

    ssim_result = subprocess.run(
        [ffmpeg, "-i", str(default_out), "-i", str(graded_out), "-filter_complex", "ssim", "-f", "null", "-"],
        capture_output=True, check=True, text=True,
    )
    match = re.search(r"All:([\d.]+)", ssim_result.stderr)
    assert match
    ssim = float(match.group(1))
    assert ssim < 0.999, f"SSIM {ssim} — preset màu 'moody_dark' phải cho pixel KHÁC bản mặc định"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_color_grade_unset_matches_old_default_behavior(tmp_path):
    """`brand=None` (chưa truyền) và `brand={}` (BrandProfile chưa cấu hình `visual_grade`)
    PHẢI ra pixel GIỐNG HỆT nhau — không đổi hành vi cho kênh chưa cấu hình."""
    from app.render.assembly import _build_segment

    ffmpeg = shutil.which("ffmpeg")
    png = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)

    none_out = tmp_path / "none.mp4"
    _build_segment(ffmpeg, str(png), None, 1.0, none_out, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=23, brand=None)
    empty_out = tmp_path / "empty.mp4"
    _build_segment(ffmpeg, str(png), None, 1.0, empty_out, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=23, brand={})

    ssim_result = subprocess.run(
        [ffmpeg, "-i", str(none_out), "-i", str(empty_out), "-filter_complex", "ssim", "-f", "null", "-"],
        capture_output=True, check=True, text=True,
    )
    match = re.search(r"All:([\d.]+)", ssim_result.stderr)
    assert match
    assert float(match.group(1)) == pytest.approx(1.0, abs=0.0001)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_grain_enabled_adds_visible_noise(tmp_path):
    from app.render.assembly import _build_segment

    ffmpeg = shutil.which("ffmpeg")
    png = tmp_path / "src.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=gray", "-s", "320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)

    plain_out = tmp_path / "plain.mp4"
    _build_segment(ffmpeg, str(png), None, 1.0, plain_out, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=23, brand={"grain_enabled": False})
    grainy_out = tmp_path / "grainy.mp4"
    _build_segment(ffmpeg, str(png), None, 1.0, grainy_out, resolution="320:240", video_codec="libx264", audio_codec="aac", crf=23, brand={"grain_enabled": True})

    ssim_result = subprocess.run(
        [ffmpeg, "-i", str(plain_out), "-i", str(grainy_out), "-filter_complex", "ssim", "-f", "null", "-"],
        capture_output=True, check=True, text=True,
    )
    match = re.search(r"All:([\d.]+)", ssim_result.stderr)
    assert match
    ssim = float(match.group(1))
    assert ssim < 0.999, f"SSIM {ssim} — bật grain phải cho pixel KHÁC bản không grain (bằng phẳng, không noise)"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_blurfill_aspect_mode_letterboxes_without_cropping(tmp_path):
    """`aspect_fill_mode="blur"` — nội dung gốc (ngang) ghép vào khung DỌC phải giữ
    NGUYÊN VẸN ở giữa (không crop mất rìa) — verify bằng cách so khung giữa (content) và
    khung rìa trên/dưới (phải là nền mờ, KHÁC màu/kết cấu content thật)."""
    from app.render.assembly import _build_segment

    ffmpeg = shutil.which("ffmpeg")
    png = tmp_path / "src.png"
    # Nội dung test: chữ nhật đỏ đặc chiếm HẾT khung ngang 320x240 — nếu crop-fill (mặc
    # định) thì khung dọc ra vẫn TOÀN ĐỎ (crop chỉ cắt bớt, không đổi màu); nếu blur-fill
    # đúng thì viền trên/dưới phải là ĐỎ MỜ (từ chính nội dung phóng to+blur), giữa vẫn đỏ
    # sắc nét — cả 2 TRƯỜNG HỢP đều ra đỏ nên test này đổi sang dùng testsrc (có hoạ tiết)
    # để phân biệt được "sắc nét" vs "mờ" bằng biến thiên pixel cục bộ.
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)

    out_path = tmp_path / "blurfill.mp4"
    _build_segment(
        ffmpeg, str(png), None, 1.0, out_path, resolution="1080:1920", video_codec="libx264", audio_codec="aac", crf=23,
        brand={"aspect_fill_mode": "blur"},
    )
    frame = tmp_path / "frame.png"
    subprocess.run([ffmpeg, "-y", "-i", str(out_path), "-frames:v", "1", str(frame)], capture_output=True, check=True, text=True)

    # Crop 1 dải mỏng NGANG ở rìa trên (phải là nền mờ) và 1 dải ở giữa (nội dung sắc nét
    # thật) — đo độ SẮC NÉT thô bằng filter `edgedetect` rồi tính độ sáng trung bình
    # (nhiều cạnh phát hiện = sáng hơn = sắc nét hơn; vùng mờ gblur gần như không có cạnh).
    def _edge_brightness(y: int, h: int) -> float:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(frame), "-vf", f"crop=1080:{h}:0:{y},edgedetect,format=gray", "-f", "rawvideo", "-"],
            capture_output=True, check=True,
        )
        data = result.stdout
        return sum(data) / len(data) if data else 0.0

    top_edge_brightness = _edge_brightness(0, 100)  # rìa trên — vùng nền mờ (blur-fill)
    middle_edge_brightness = _edge_brightness(860, 100)  # giữa khung 1920 cao — vùng nội dung gốc

    assert middle_edge_brightness > top_edge_brightness, (
        f"Vùng giữa (nội dung gốc, kỳ vọng SẮC NÉT, edge brightness={middle_edge_brightness}) "
        f"phải có nhiều cạnh hơn hẳn vùng rìa (nền mờ blur-fill, edge brightness={top_edge_brightness})"
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_bg_music_ducking_reduces_volume_during_narration(tmp_path):
    """Verify thật bằng `volumedetect` CÔ LẬP đúng tần số nhạc nền (`bandpass=f=880`,
    tách khỏi giọng đọc `220Hz`) trong CHÍNH output `_mix_bg_music(ducking_enabled=True)`
    — đo trực tiếp trên bản mix TỔNG (không so với bản `ducking_enabled=False` khác cấu
    hình `amix.normalize`, tránh nhầm lẫn đã gặp lúc verify tay: `amix.normalize=True`
    MẶC ĐỊNH tự động rescale, làm sai lệch so sánh chéo giữa 2 lần mix có `normalize`
    khác nhau — CÔ LẬP tần số trên CÙNG 1 output là cách đo đúng, không phải so 2 output
    khác cấu hình `amix`). Kỳ vọng: năng lượng dải tần nhạc nền THẤP HƠN rõ rệt tại đoạn
    có giọng đọc so với đoạn giọng đọc im lặng."""
    from app.render.assembly import _mix_bg_music

    ffmpeg = shutil.which("ffmpeg")
    # Giọng đọc giả: lặng 2s, tiếng 220Hz 2s, lặng 2s (tổng 6s) — mô phỏng 1 câu thoại giữa video.
    voice = tmp_path / "voice.wav"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "aevalsrc=0:duration=2", "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
         "-f", "lavfi", "-i", "aevalsrc=0:duration=2", "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[voice]", "-map", "[voice]", str(voice)],
        capture_output=True, check=True, text=True,
    )
    video = tmp_path / "video.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=6", "-i", str(voice), "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)],
        capture_output=True, check=True, text=True,
    )
    bg_music = tmp_path / "bg.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=6", str(bg_music)], capture_output=True, check=True, text=True)

    ducked_out = tmp_path / "ducked.mp4"
    _mix_bg_music(ffmpeg, video, str(bg_music), 1.0, ducked_out, audio_codec="aac", ducking_enabled=True)

    def _bg_band_volume(start: float, end: float) -> float:
        result = subprocess.run(
            [ffmpeg, "-i", str(ducked_out), "-af", f"atrim={start}:{end},bandpass=f=880:width_type=h:w=50,volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", result.stderr)
        assert match, result.stderr[-500:]
        return float(match.group(1))

    bg_no_narration = _bg_band_volume(4.5, 5.5)
    bg_during_narration = _bg_band_volume(2.5, 3.5)
    assert bg_during_narration < bg_no_narration - 1.5, (
        f"Dải tần nhạc nền (880Hz) lúc có giọng đọc ({bg_during_narration}dB) phải THẤP HƠN rõ rệt "
        f"lúc im lặng ({bg_no_narration}dB) — ducking chưa thực sự giảm nhạc nền"
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assemble_video_applies_loudnorm_to_final_output(client, project_with_brief):
    """Verify END-TO-END qua `assemble_video()` thật: audio cuối cùng phải đạt loudness
    gần `-14 LUFS` (EBU R128) — dùng chính giọng đọc test (sine, không phải câm) ở mức
    xa mục tiêu (rất nhỏ) để thấy rõ loudnorm THẬT SỰ chỉnh, không phải tình cờ đã đúng."""
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    from app.config import project_dir
    from app.filestore import write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    pdir = project_dir(channel_id, pid)
    png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(png)], capture_output=True, check=True, text=True)
    wav = pdir / "assets" / f"{shot_id}.wav"
    # Mức RẤT NHỎ (volume=0.02, xa hẳn -14 LUFS) — nếu loudnorm KHÔNG chạy, output vẫn
    # sẽ rất nhỏ; nếu CÓ chạy đúng, output phải được kéo LÊN gần -14 LUFS.
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-af", "volume=0.02", str(wav)], capture_output=True, check=True, text=True)
    narration_dur = _ffprobe_duration(wav)

    write_json(pdir / "render.json", RenderState(project_id=pid, shots=[
        ShotRenderStatus(shot_id=shot_id, visual_status="ready", visual_asset_path=str(png), approved=True,
                          narration_status="ready", narration_asset_path=str(wav), narration_duration_sec=narration_dur),
    ]).model_dump())

    resp = client.post(f"/projects/{pid}/render/assemble", json={"resolution": "720p", "codec": "h264", "quality": "low"})
    assert resp.status_code == 200, resp.text
    final_state = client.get(f"/projects/{pid}/render/status").json()
    assert final_state["assembly_status"] == "done", final_state.get("assembly_error")

    result = subprocess.run(
        [ffmpeg, "-i", final_state["final_video_path"], "-af", "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r'"input_i"\s*:\s*"(-?[\d.]+)"', result.stderr)
    assert match, result.stderr[-800:]
    measured_input_lufs = float(match.group(1))
    assert measured_input_lufs > -20, (
        f"Audio cuối cùng đo được {measured_input_lufs} LUFS — quá nhỏ so với mục tiêu -14 LUFS, "
        "loudnorm có vẻ CHƯA áp dụng (input gốc cố tình rất nhỏ, ~volume=0.02)"
    )
