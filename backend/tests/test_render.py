"""Test Render Studio (M2 Production Layer) — mock TOÀN BỘ HTTP call ra ngoài qua
respx (ElevenLabs/OpenAI Image/Sora/Gemini/Veo), không gọi API thật, không tốn phí.
Lái project qua pipeline thật (giống test_pipeline_flow.py).

Đổi theo yêu cầu người dùng (đợt 2): sinh asset thật (`render/start` + regenerate)
dùng được ngay từ Visual Studio — TRƯỚC Gate #2 (`project.status == "generating"`) —
không còn yêu cầu `ready_output` như M2 ban đầu. Chỉ `render/assemble` (ghép MP4) vẫn
yêu cầu qua Gate #2, vì đó là bước xuất thành phẩm cuối ở Output Center.
"""
import base64

import pytest
import respx
from httpx import Response

from app.render.assembly import _beat_duration

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
FAKE_MP3 = b"ID3" + b"0" * 20
FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20
FAKE_WAV = b"RIFF" + b"0" * 40


def _drive_to_visual_studio(client, project_with_brief) -> str:
    """Dừng lại đúng lúc Visual Studio (step 3, status vẫn "generating") — KHÔNG qua
    Gate #2 — để test render/start dùng được từ đây (thay đổi chính của đợt 2)."""
    pid = project_with_brief["id"]
    research = client.post(f"/projects/{pid}/research").json()
    outline_id = research["research"]["outlines"][0]["id"]
    hook_id = research["hooks"][0]["id"]
    client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": outline_id, "chosen_hook_id": hook_id})
    client.post(f"/projects/{pid}/script/approve")
    resp = client.post(f"/projects/{pid}/visual/generate")
    assert resp.status_code == 200, resp.text
    proj = client.get(f"/projects/{pid}").json()
    assert proj["status"] == "generating"  # vẫn TRƯỚC Gate #2
    return pid


def _drive_to_ready_output(client, project_with_brief) -> str:
    pid = _drive_to_visual_studio(client, project_with_brief)
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


def test_render_start_requires_shots(client, project_with_brief):
    resp = client.post(f"/projects/{project_with_brief['id']}/render/start")
    assert resp.status_code == 400


@respx.mock
def test_render_start_works_from_visual_studio_before_gate2(client, project_with_brief):
    """Thay đổi chính đợt 2: sinh asset thật dùng được ngay ở Visual Studio, KHÔNG
    còn phải đợi qua Gate #2 như M2 ban đầu."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()

    resp = client.post(f"/projects/{pid}/render/start")
    assert resp.status_code == 200
    state = client.get(f"/projects/{pid}/render/status").json()
    assert len(state["shots"]) > 0
    assert all(s["visual_status"] == "ready" for s in state["shots"])

    proj = client.get(f"/projects/{pid}").json()
    assert proj["status"] == "generating"  # vẫn chưa qua Gate #2, sinh asset không tự đổi status


@respx.mock
def test_assemble_requires_gate2(client, project_with_brief):
    """Ghép MP4 vẫn CHỈ làm được sau Gate #2 (vai trò còn lại của Render Studio) —
    khác render/start giờ mở từ Visual Studio."""
    pid = _drive_to_visual_studio(client, project_with_brief)
    _setup_asset_providers(client)
    _mock_asset_apis()
    client.post(f"/projects/{pid}/render/start")

    resp = client.post(f"/projects/{pid}/render/assemble")
    assert resp.status_code == 400
    assert "Gate #2" in resp.json()["detail"]


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
