"""Ảnh nhân vật tham khảo RIÊNG của project (2026-09-09, mục 127) — theo yêu cầu người
dùng: upload 1 ảnh nhân vật, tự động sinh mô tả qua VisionProvider, mô tả nối vào MỌI
prompt sinh ảnh của project (xem `app/render/engine.py::_build_visual_prompt`). Mock HTTP
Vision provider qua `respx`, cùng convention `test_asset_vault.py::test_caption_clip_
updates_fields_and_upserts_vector` — verify code build đúng request/parse đúng response,
KHÔNG verify hành vi Vision provider thật (cần GPU/API key người dùng)."""
from __future__ import annotations

import io

import pytest
import respx
from httpx import Response

from app.db import SessionLocal
from app.models import ProviderConfig

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
FAKE_PNG_2 = b"\x89PNG\r\n\x1a\n" + b"1" * 20
FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20


@pytest.fixture
def vision_provider():
    """Đăng ký 1 `localai_vision` provider thật trong DB (cùng pattern test_asset_vault.py)
    — dọn dẹp sau test để không rò rỉ sang test khác trong CÙNG session pytest."""
    db = SessionLocal()
    cfg = ProviderConfig(
        task="vision", provider_name="localai_vision", display_name="Vision test",
        connection_type="local_endpoint", endpoint_url="http://127.0.0.1:8080", model_name="moondream2",
        is_default=True, enabled=True,
    )
    db.add(cfg)
    db.commit()
    cfg_id = cfg.id
    db.close()
    yield
    db = SessionLocal()
    db.query(ProviderConfig).filter(ProviderConfig.id == cfg_id).delete()
    db.commit()
    db.close()


def _mock_vision_caption(caption: str):
    return respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": f'{{"caption": "{caption}", "tags": [], "mood_tone": ""}}'}}]})
    )


@respx.mock
def test_upload_generates_description_via_vision_provider(client, project, vision_provider):
    _mock_vision_caption("a stick figure with a round head and curly hair")
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.png", io.BytesIO(FAKE_PNG), "image/png")})
    assert resp.status_code == 200
    state = resp.json()
    assert state["character_reference"]["image_path"]
    assert state["character_reference"]["description"] == "a stick figure with a round head and curly hair"
    assert state["character_reference"]["caption_error"] is None


def test_upload_without_vision_provider_configured_still_saves_image(client, project):
    """Chưa cấu hình Vision provider nào — `NoProviderConfiguredError` KHÔNG chặn upload
    (khác nhiều chỗ coi lỗi provider AI là chặn cứng) — ảnh vẫn lưu được, chỉ `description`
    rỗng + `caption_error` ghi rõ lý do, người dùng tự gõ tay hoặc cấu hình provider rồi
    bấm sinh lại (xem test_recaption bên dưới)."""
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.png", io.BytesIO(FAKE_PNG), "image/png")})
    assert resp.status_code == 200
    state = resp.json()
    assert state["character_reference"]["image_path"]
    assert state["character_reference"]["description"] == ""
    assert state["character_reference"]["caption_error"]


def test_upload_rejects_non_image_file(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    assert resp.status_code == 400


def test_upload_rejects_empty_file(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.png", io.BytesIO(b""), "image/png")})
    assert resp.status_code == 400


def test_upload_twice_replaces_image(client, project):
    pid = project["id"]
    resp1 = client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.png", io.BytesIO(FAKE_PNG), "image/png")})
    path1 = resp1.json()["character_reference"]["image_path"]

    resp2 = client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref2.png", io.BytesIO(FAKE_PNG_2), "image/png")})
    assert resp2.status_code == 200
    path2 = resp2.json()["character_reference"]["image_path"]
    assert path2 == path1  # cùng tên file cố định (character_reference.png) — ghi đè tại chỗ

    asset_resp = client.get(f"/projects/{pid}/render/character-reference/asset")
    assert asset_resp.content == FAKE_PNG_2


@respx.mock
def test_recaption_without_reupload_after_configuring_provider(client, project):
    """Upload lúc CHƯA có Vision provider (caption_error) → cấu hình provider SAU →
    `recaption` sinh lại `description` từ file ẢNH ĐÃ CÓ, không cần upload lại."""
    pid = project["id"]
    client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.png", io.BytesIO(FAKE_PNG), "image/png")})

    db = SessionLocal()
    cfg = ProviderConfig(
        task="vision", provider_name="localai_vision", display_name="Vision test",
        connection_type="local_endpoint", endpoint_url="http://127.0.0.1:8080", model_name="moondream2",
        is_default=True, enabled=True,
    )
    db.add(cfg)
    db.commit()
    cfg_id = cfg.id
    db.close()
    try:
        _mock_vision_caption("a friendly stick figure character")
        resp = client.post(f"/projects/{pid}/render/character-reference/recaption")
        assert resp.status_code == 200
        state = resp.json()
        assert state["character_reference"]["description"] == "a friendly stick figure character"
        assert state["character_reference"]["caption_error"] is None
    finally:
        db = SessionLocal()
        db.query(ProviderConfig).filter(ProviderConfig.id == cfg_id).delete()
        db.commit()
        db.close()


def test_recaption_404_when_no_reference_uploaded(client, project):
    pid = project["id"]
    resp = client.post(f"/projects/{pid}/render/character-reference/recaption")
    assert resp.status_code == 404


def test_patch_description_overrides_manually(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.png", io.BytesIO(FAKE_PNG), "image/png")})
    resp = client.patch(f"/projects/{pid}/render/character-reference/description", json={"description": "tự viết tay: nhân vật que tay đầu tròn"})
    assert resp.status_code == 200
    assert resp.json()["character_reference"]["description"] == "tự viết tay: nhân vật que tay đầu tròn"


def test_patch_description_404_when_no_reference(client, project):
    pid = project["id"]
    resp = client.patch(f"/projects/{pid}/render/character-reference/description", json={"description": "x"})
    assert resp.status_code == 404


def test_delete_character_reference_clears_state_and_removes_file(client, project):
    pid = project["id"]
    upload_resp = client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.png", io.BytesIO(FAKE_PNG), "image/png")})
    from pathlib import Path

    path = Path(upload_resp.json()["character_reference"]["image_path"])
    assert path.exists()

    resp = client.delete(f"/projects/{pid}/render/character-reference")
    assert resp.status_code == 200
    assert resp.json()["character_reference"] is None
    assert not path.exists()


def test_get_asset_404_when_none(client, project):
    pid = project["id"]
    resp = client.get(f"/projects/{pid}/render/character-reference/asset")
    assert resp.status_code == 404


def test_get_asset_serves_uploaded_file(client, project):
    pid = project["id"]
    client.post(f"/projects/{pid}/render/character-reference/upload", files={"file": ("ref.png", io.BytesIO(FAKE_PNG), "image/png")})
    resp = client.get(f"/projects/{pid}/render/character-reference/asset")
    assert resp.status_code == 200
    assert resp.content == FAKE_PNG
