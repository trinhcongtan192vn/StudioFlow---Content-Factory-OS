"""Test sinh ảnh thumbnail thật ở Pack Review (tái dùng OpenAI Image adapter, M2) —
mock HTTP qua respx, không gọi API thật."""
import base64

import respx
from httpx import Response

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def _drive_to_pack_built(client, project_with_brief) -> str:
    pid = project_with_brief["id"]
    research = client.post(f"/projects/{pid}/research").json()
    outline_id = research["research"]["outlines"][0]["id"]
    hook_id = research["hooks"][0]["id"]
    client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": outline_id, "chosen_hook_id": hook_id})
    client.post(f"/projects/{pid}/script/approve")
    client.post(f"/projects/{pid}/visual/generate")
    resp = client.post(f"/projects/{pid}/pack/build")
    assert resp.status_code == 200, resp.text
    return pid


def _setup_openai_image_provider(client) -> None:
    image = client.post("/providers", json={"task": "image", "provider_name": "openai", "display_name": "OAI Img", "connection_type": "cloud_api", "api_key": "sk-oai-test"}).json()
    client.patch(f"/providers/{image['id']}", json={"is_default": True})


def test_generate_thumbnail_requires_description(client, project_with_brief):
    pid = _drive_to_pack_built(client, project_with_brief)
    client.patch(f"/projects/{pid}/pack", json={"youtube_meta": {"description": "x", "hashtags": [], "chapters": [], "thumbnail_description": ""}})
    resp = client.post(f"/projects/{pid}/pack/thumbnail/generate")
    assert resp.status_code == 400


@respx.mock
def test_generate_thumbnail_success_and_download(client, project_with_brief):
    pid = _drive_to_pack_built(client, project_with_brief)
    _setup_openai_image_provider(client)
    respx.post("https://api.openai.com/v1/images/generations").mock(return_value=Response(200, json={"data": [{"b64_json": base64.b64encode(FAKE_PNG).decode()}]}))

    resp = client.post(f"/projects/{pid}/pack/thumbnail/generate")
    assert resp.status_code == 200
    ym = resp.json()["youtube_meta"]
    assert ym["thumbnail_status"] == "ready"
    assert ym["thumbnail_asset_path"]
    assert ym["thumbnail_provider"] == "openai"

    dl = client.get(f"/projects/{pid}/pack/thumbnail")
    assert dl.status_code == 200
    assert dl.content == FAKE_PNG


def test_download_thumbnail_before_generated(client, project_with_brief):
    pid = _drive_to_pack_built(client, project_with_brief)
    resp = client.get(f"/projects/{pid}/pack/thumbnail")
    assert resp.status_code == 404


def test_generate_thumbnail_fails_clearly_without_provider(client, project_with_brief):
    pid = _drive_to_pack_built(client, project_with_brief)
    for p in client.get("/providers").json():
        if p["task"] == "image":
            client.delete(f"/providers/{p['id']}")
    resp = client.post(f"/projects/{pid}/pack/thumbnail/generate")
    assert resp.status_code == 200  # sinh lỗi có kiểm soát, không phải 500
    ym = resp.json()["youtube_meta"]
    assert ym["thumbnail_status"] == "error"
    assert "Provider AI" in ym["thumbnail_error"]
