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


def test_local_endpoint_only_allowed_for_llm_task(client):
    resp = client.post(
        "/providers",
        json={"task": "image", "provider_name": "local", "display_name": "Local X", "connection_type": "local_endpoint", "endpoint_url": "http://localhost:11434/v1"},
    )
    assert resp.status_code == 400


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


def test_patch_provider_404(client):
    resp = client.patch("/providers/999999", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_provider(client):
    pv = client.post("/providers", json={"task": "image", "provider_name": "flux", "display_name": "Flux", "connection_type": "cloud_api", "api_key": "sk-flux"}).json()
    resp = client.delete(f"/providers/{pv['id']}")
    assert resp.status_code == 200
    ids = [p["id"] for p in client.get("/providers").json()]
    assert pv["id"] not in ids
