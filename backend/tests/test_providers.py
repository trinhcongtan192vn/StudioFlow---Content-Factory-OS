def test_list_providers_includes_test_mock(client):
    """App thật KHÔNG tự seed provider Mock nữa (đổi theo yêu cầu — thiếu provider phải
    báo lỗi rõ ràng). Provider mock trong list này tới từ fixture `_ensure_mock_llm_is_default`
    (conftest.py) để test suite chạy được mà không cần mạng thật."""
    resp = client.get("/providers")
    assert resp.status_code == 200
    providers = resp.json()
    mock = next((p for p in providers if p["provider_name"] == "mock"), None)
    assert mock is not None
    assert mock["task"] == "llm"
    assert mock["is_default"] is True
    assert mock["enabled"] is True


def test_mock_provider_test_connection_ok_no_network(client):
    providers = client.get("/providers").json()
    mock = next(p for p in providers if p["provider_name"] == "mock")
    resp = client.post(f"/providers/{mock['id']}/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


def test_create_cloud_provider(client):
    resp = client.post(
        "/providers",
        json={"task": "llm", "provider_name": "claude", "display_name": "Anthropic Claude", "connection_type": "cloud_api", "api_key": "sk-ant-test-key", "model_name": "claude-sonnet-4-5"},
    )
    assert resp.status_code == 200
    pv = resp.json()
    assert pv["connection_type"] == "cloud_api"
    assert pv["model_name"] == "claude-sonnet-4-5"
    assert pv["has_key"] is True
    assert pv["key_display"] != "sk-ant-test-key"  # không bao giờ trả key thô (§05 mục 8)
    assert "•" in pv["key_display"]


def test_local_endpoint_allowed_for_asset_tasks(client):
    """Trước đây `local_endpoint` chỉ cho task=="llm" — đã nới cho cả tts/image/video
    (xem factory.py::_build_asset_provider + specs/05_ai_providers.md §2, mục local AI
    provider trong IMPLEMENTATION_REPORT.md) vì giờ có adapter local thật cho cả 2
    (piper/local_qwen), không chỉ LLM (Ollama)."""
    resp = client.post(
        "/providers",
        json={"task": "image", "provider_name": "local_qwen", "display_name": "ComfyUI Qwen-Image-2.1", "connection_type": "local_endpoint", "endpoint_url": "http://127.0.0.1:8188"},
    )
    assert resp.status_code == 200
    pv = resp.json()
    assert pv["connection_type"] == "local_endpoint"
    assert pv["task"] == "image"


def test_create_local_llm_provider(client):
    resp = client.post(
        "/providers",
        json={"task": "llm", "provider_name": "local", "display_name": "Ollama Qwen", "connection_type": "local_endpoint", "endpoint_url": "http://localhost:11434/v1", "model_name": "qwen2.5:32b"},
    )
    assert resp.status_code == 200
    pv = resp.json()
    assert pv["endpoint_url"] == "http://localhost:11434/v1"
    assert pv["has_key"] is False


def test_patch_provider_set_default_unsets_others(client):
    """Lưu ý cách ly: test này đổi provider mặc định cho task 'llm' toàn cục (DB dùng
    chung cho cả session test, xem conftest.py) — PHẢI khôi phục lại provider Mock làm
    mặc định ở cuối, nếu không các test pipeline chạy sau (dùng provider thật giả với
    key rác) sẽ tự rơi vào fallback content thay vì gọi provider, khiến usage/audit log
    không được ghi — đã từng gây 1 test khác fail sai chỗ, xem test_settings.py."""
    a = client.post("/providers", json={"task": "llm", "provider_name": "openai", "display_name": "GPT A", "connection_type": "cloud_api", "api_key": "sk-a"}).json()
    b = client.post("/providers", json={"task": "llm", "provider_name": "gemini", "display_name": "Gemini B", "connection_type": "cloud_api", "api_key": "sk-b"}).json()

    resp = client.patch(f"/providers/{a['id']}", json={"is_default": True})
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True

    resp = client.patch(f"/providers/{b['id']}", json={"is_default": True})
    assert resp.json()["is_default"] is True

    # đặt b default rồi -> a phải bị bỏ default (chỉ 1 default/task)
    a_after = next(p for p in client.get("/providers").json() if p["id"] == a["id"])
    assert a_after["is_default"] is False

    # dọn dẹp: xoá 2 provider tạo trong test + khôi phục Mock làm mặc định
    client.delete(f"/providers/{a['id']}")
    client.delete(f"/providers/{b['id']}")
    mock = next(p for p in client.get("/providers").json() if p["provider_name"] == "mock")
    client.patch(f"/providers/{mock['id']}", json={"is_default": True})


# ---------------------------------------------------------------------------
# GET /providers/comfyui/models — liệt kê checkpoint/LoRA/GGUF ComfyUI cho dropdown
# (mới 2026-08-22, theo yêu cầu người dùng "cho chọn thay vì phải gõ"; đổi tên endpoint
# từ /providers/local-sdxl/models — đợt dọn dẹp 2026-09-24 xoá local_sdxl, tên cũ gây
# hiểu nhầm khi SDXL không còn tồn tại, xem IMPLEMENTATION_REPORT.md)
# ---------------------------------------------------------------------------
import respx
from httpx import Response


@respx.mock
def test_list_comfyui_checkpoints(client):
    respx.get("http://127.0.0.1:8188/models/checkpoints").mock(return_value=Response(200, json=["paintersCheckpointOilPaint_v11.safetensors", "sd_xl_base_1.0.safetensors"]))
    resp = client.get("/providers/comfyui/models", params={"kind": "checkpoints"})
    assert resp.status_code == 200
    assert resp.json()["models"] == ["paintersCheckpointOilPaint_v11.safetensors", "sd_xl_base_1.0.safetensors"]


@respx.mock
def test_list_comfyui_loras_with_custom_base_url(client):
    respx.get("http://127.0.0.1:9999/models/loras").mock(return_value=Response(200, json=["InkArtXL_1.2.safetensors", "ClassipeintXL2.1.safetensors"]))
    resp = client.get("/providers/comfyui/models", params={"kind": "loras", "base_url": "http://127.0.0.1:9999"})
    assert resp.status_code == 200
    assert resp.json()["models"] == ["InkArtXL_1.2.safetensors", "ClassipeintXL2.1.safetensors"]


def test_list_comfyui_models_rejects_invalid_kind(client):
    resp = client.get("/providers/comfyui/models", params={"kind": "bogus"})
    assert resp.status_code == 400


@respx.mock
def test_list_comfyui_models_unet_gguf_for_qwen(client):
    """`unet_gguf` — mới (2026-09-09, ban đầu cho `local_flux`, đã xoá), giờ dùng cho
    provider `local_qwen` (dropdown chọn file GGUF ở Cài đặt → Provider AI) — dùng CHUNG
    endpoint ComfyUI `/models/{kind}`, thư mục `unet_gguf` do custom node ComfyUI-GGUF
    tự đăng ký."""
    respx.get("http://127.0.0.1:8188/models/unet_gguf").mock(return_value=Response(200, json=["Qwen-Image-2.1-Q4.gguf", "Qwen-Image-2.1-Q6.gguf"]))
    resp = client.get("/providers/comfyui/models", params={"kind": "unet_gguf"})
    assert resp.status_code == 200
    assert resp.json()["models"] == ["Qwen-Image-2.1-Q4.gguf", "Qwen-Image-2.1-Q6.gguf"]


@respx.mock
def test_list_comfyui_models_502_when_comfyui_unreachable(client):
    respx.get("http://127.0.0.1:8188/models/checkpoints").mock(side_effect=Exception("connection refused"))
    resp = client.get("/providers/comfyui/models", params={"kind": "checkpoints"})
    assert resp.status_code == 502


def test_patch_provider_404(client):
    resp = client.patch("/providers/999999", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_provider(client):
    pv = client.post("/providers", json={"task": "image", "provider_name": "flux", "display_name": "Flux", "connection_type": "cloud_api", "api_key": "sk-flux"}).json()
    resp = client.delete(f"/providers/{pv['id']}")
    assert resp.status_code == 200
    ids = [p["id"] for p in client.get("/providers").json()]
    assert pv["id"] not in ids
