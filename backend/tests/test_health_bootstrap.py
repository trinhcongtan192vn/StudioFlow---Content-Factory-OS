def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_bootstrap(client):
    resp = client.get("/bootstrap")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_name"] == "StudioFlow"
    # seed đăng ký sẵn provider Mock -> luôn có LLM provider ngay từ đầu (§06 mục 4)
    assert data["has_llm_provider"] is True
    # seed 3 kênh demo
    assert data["channel_count"] >= 3
