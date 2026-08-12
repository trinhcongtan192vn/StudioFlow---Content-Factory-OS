"""Test Render Studio (M2 Production Layer) — mock TOÀN BỘ HTTP call ra ngoài qua
respx (ElevenLabs/OpenAI Image/Sora), không gọi API thật, không tốn phí. Lái project
qua pipeline thật (giống test_pipeline_flow.py) tới trạng thái ready_output trước khi
test render — render/start yêu cầu đã qua Gate #2.
"""
import base64

import pytest
import respx
from httpx import Response

from app.render.assembly import _beat_duration

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
FAKE_MP3 = b"ID3" + b"0" * 20
FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20


def _drive_to_ready_output(client, project_with_brief) -> str:
    pid = project_with_brief["id"]
    research = client.post(f"/projects/{pid}/research").json()
    outline_id = research["research"]["outlines"][0]["id"]
    hook_id = research["hooks"][0]["id"]
    client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": outline_id, "chosen_hook_id": hook_id})
    client.post(f"/projects/{pid}/script/approve")
    client.post(f"/projects/{pid}/visual/generate")
    client.post(f"/projects/{pid}/pack/build")
    resp = client.post(f"/projects/{pid}/gate2", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    client.post(f"/projects/{pid}/output/enter")
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


def test_render_start_blocked_before_gate2(client, project_with_brief):
    resp = client.post(f"/projects/{project_with_brief['id']}/render/start")
    assert resp.status_code == 400


def test_render_status_empty_before_start(client, render_ready_project):
    resp = client.get(f"/projects/{render_ready_project}/render/status")
    assert resp.status_code == 200
    assert resp.json()["shots"] == []


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


def test_download_requires_assembly_done(client, render_ready_project):
    resp = client.get(f"/projects/{render_ready_project}/render/download")
    assert resp.status_code == 400


def test_beat_duration_uses_timestamp_range():
    assert _beat_duration({"timestamp_sec": 10, "end_sec": 18}) == 8.0
    assert _beat_duration({"timestamp_sec": 10, "end_sec": None}) == 5.0
    assert _beat_duration({}) == 5.0
