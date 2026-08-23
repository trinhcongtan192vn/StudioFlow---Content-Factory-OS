"""Test Thư viện Creative Asset (2026-08-20, theo yêu cầu người dùng) —
`app/routers/library.py`: upload/list/delete/serve nhạc nền/video/ảnh/giọng đọc dùng lại
được ở nhiều nơi, độc lập không gắn channel/project nào.
"""
import io

FAKE_MP3 = b"ID3" + b"0" * 20
FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"0" * 20
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def test_upload_music_asset(client):
    resp = client.post("/library/assets/upload?kind=music", files={"file": ("track.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "music"
    assert body["name"] == "track"
    assert body["id"]


def test_upload_video_asset(client):
    resp = client.post("/library/assets/upload?kind=video", files={"file": ("clip.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    assert resp.status_code == 200
    assert resp.json()["kind"] == "video"


def test_upload_image_asset(client):
    resp = client.post("/library/assets/upload?kind=image", files={"file": ("pic.png", io.BytesIO(FAKE_PNG), "image/png")})
    assert resp.status_code == 200
    assert resp.json()["kind"] == "image"


def test_upload_voice_asset(client):
    resp = client.post("/library/assets/upload?kind=voice", files={"file": ("sample.wav", io.BytesIO(FAKE_MP3), "audio/wav")})
    assert resp.status_code == 200
    assert resp.json()["kind"] == "voice"


def test_upload_rejects_invalid_kind(client):
    resp = client.post("/library/assets/upload?kind=bogus", files={"file": ("x.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    assert resp.status_code == 400


def test_upload_rejects_mismatched_file_type(client):
    """kind=image nhưng gửi file mp3 — 400, không lưu nhầm."""
    resp = client.post("/library/assets/upload?kind=image", files={"file": ("track.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    assert resp.status_code == 400


def test_upload_rejects_empty_file(client):
    resp = client.post("/library/assets/upload?kind=music", files={"file": ("empty.mp3", io.BytesIO(b""), "audio/mpeg")})
    assert resp.status_code == 400


def test_list_assets_filters_by_kind(client):
    client.post("/library/assets/upload?kind=music", files={"file": ("a.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")})
    client.post("/library/assets/upload?kind=image", files={"file": ("b.png", io.BytesIO(FAKE_PNG), "image/png")})

    music_only = client.get("/library/assets?kind=music").json()
    assert all(a["kind"] == "music" for a in music_only)
    assert len(music_only) >= 1

    everything = client.get("/library/assets").json()
    assert len(everything) >= len(music_only)


def test_list_assets_rejects_invalid_kind_filter(client):
    resp = client.get("/library/assets?kind=bogus")
    assert resp.status_code == 400


def test_rename_asset_updates_name_only(client):
    upload = client.post("/library/assets/upload?kind=music", files={"file": ("track.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")}).json()
    resp = client.patch(f"/library/assets/{upload['id']}", json={"name": "Nhạc nền chính"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Nhạc nền chính"

    listed = client.get("/library/assets?kind=music").json()
    renamed = next(a for a in listed if a["id"] == upload["id"])
    assert renamed["name"] == "Nhạc nền chính"

    # File vật lý vẫn phục vụ được bình thường — đổi tên hiển thị không đụng file_path.
    file_resp = client.get(f"/library/assets/{upload['id']}/file")
    assert file_resp.status_code == 200
    assert file_resp.content == FAKE_MP3


def test_rename_asset_trims_whitespace(client):
    upload = client.post("/library/assets/upload?kind=music", files={"file": ("track.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")}).json()
    resp = client.patch(f"/library/assets/{upload['id']}", json={"name": "  Nhạc nền  "})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Nhạc nền"


def test_rename_asset_rejects_empty_name(client):
    upload = client.post("/library/assets/upload?kind=music", files={"file": ("track.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")}).json()
    resp = client.patch(f"/library/assets/{upload['id']}", json={"name": "   "})
    assert resp.status_code == 400


def test_rename_asset_404_when_missing(client):
    resp = client.patch("/library/assets/asset_doesnotexist", json={"name": "x"})
    assert resp.status_code == 404


def test_get_asset_file_serves_bytes(client):
    upload = client.post("/library/assets/upload?kind=music", files={"file": ("track.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")}).json()
    resp = client.get(f"/library/assets/{upload['id']}/file")
    assert resp.status_code == 200
    assert resp.content == FAKE_MP3


def test_get_asset_file_404_when_missing(client):
    resp = client.get("/library/assets/asset_doesnotexist/file")
    assert resp.status_code == 404


def test_delete_asset_removes_from_list_and_disk(client):
    from pathlib import Path

    from app.db import SessionLocal
    from app.models import CreativeAsset

    upload = client.post("/library/assets/upload?kind=music", files={"file": ("track.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")}).json()
    db = SessionLocal()
    try:
        file_path = Path(db.query(CreativeAsset).filter(CreativeAsset.id == upload["id"]).first().file_path)
    finally:
        db.close()
    assert file_path.exists()

    resp = client.delete(f"/library/assets/{upload['id']}")
    assert resp.status_code == 200
    assert not file_path.exists()
    assert client.get(f"/library/assets/{upload['id']}/file").status_code == 404


def test_delete_asset_404_when_missing(client):
    resp = client.delete("/library/assets/asset_doesnotexist")
    assert resp.status_code == 404
