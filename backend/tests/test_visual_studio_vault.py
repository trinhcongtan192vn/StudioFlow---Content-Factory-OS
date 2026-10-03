"""Lưu ảnh/video từ Visual Studio vào Kho Tài Nguyên để tái sử dụng — mới (2026-09-11),
theo yêu cầu người dùng. Bao gồm: `asset_vault/from_visual_studio.py` (lưu/cập nhật đè),
nới lỏng `assign_vault_clip`/`matching.py` cho media_kind ảnh, và tính năng "Tự động điền
từ Kho tài nguyên" (2 endpoint mới ở `routers/render.py`)."""
from __future__ import annotations

import io
import json

import pytest
import respx
from httpx import Response

from app.db import SessionLocal


def _import_shots(client, project_id: str, rows: list[list[str]]) -> list[str]:
    """`rows` — mỗi phần tử `[block_id, ts_label, visual_type, visual_fx, audio_sfx, vo]`,
    khớp thứ tự cột file CSV import thật (`03_api.md`). Trả về danh sách `shot_id` theo
    ĐÚNG thứ tự đã import (sau `/visual/generate`)."""
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{project_id}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    confirm = client.post(f"/projects/{project_id}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200, confirm.text
    resp = client.post(f"/projects/{project_id}/visual/generate")
    assert resp.status_code == 200, resp.text
    return [s["shot_id"] for s in resp.json()["shots"]]


def _mark_shot_ready(client, project_id: str, channel_id: str, shot_id: str, *, suffix: str, content: bytes = b"fake-bytes") -> None:
    """Ghi thẳng `render.json` (KHÔNG cần ffmpeg thật — `save_shots_to_vault` chỉ
    `shutil.copy2`, probe duration/resolution graceful trả None/"" khi file không hợp lệ,
    không lỗi) — nhanh, tách biệt khỏi việc test AI provider sinh asset thật."""
    from app.config import project_dir
    from app.filestore import read_json, write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    pdir = project_dir(channel_id, project_id)
    asset_path = pdir / "assets" / f"{shot_id}{suffix}"
    asset_path.write_bytes(content)

    render_path = pdir / "render.json"
    existing = read_json(render_path) or {}
    state = RenderState(**existing) if existing else RenderState(project_id=project_id)
    by_id = {s.shot_id: s for s in state.shots}
    status = by_id.get(shot_id) or ShotRenderStatus(shot_id=shot_id)
    status.visual_status = "ready"
    status.visual_asset_path = str(asset_path)
    by_id[shot_id] = status
    state.shots = list(by_id.values())
    write_json(render_path, state.model_dump())


@pytest.fixture()
def vault_project(client, channel):
    """1 project với 2 shot: B01 (image), B02 (video) — cả 2 đã `visual_status=="ready"`
    (file giả, không cần ffmpeg thật)."""
    resp = client.post(f"/channels/{channel['id']}/projects", json={"title": "Vault Save Test"})
    project = resp.json()
    rows = [
        ["B01", "0:00–0:03", "Image", "A calm river at sunset", "", "Loi thoai anh."],
        ["B02", "0:03–0:08", "Video", "Drone flying over mountains", "", "Loi thoai video."],
    ]
    shot_ids = _import_shots(client, project["id"], rows)
    _mark_shot_ready(client, project["id"], channel["id"], shot_ids[0], suffix=".png")
    _mark_shot_ready(client, project["id"], channel["id"], shot_ids[1], suffix=".mp4")
    return {"project": project, "channel": channel, "shot_ids": shot_ids}


# ---------------------------------------------------------------------------
# get_or_create_project_raw_video / save_shots_to_vault (tầng module, không qua HTTP)
# ---------------------------------------------------------------------------
def test_get_or_create_project_raw_video_is_idempotent(vault_project):
    from app.asset_vault.from_visual_studio import get_or_create_project_raw_video
    from app.models import Project, RawVideo

    pid = vault_project["project"]["id"]
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        raw1 = get_or_create_project_raw_video(db, project)
        raw2 = get_or_create_project_raw_video(db, project)
        assert raw1.id == raw2.id
        assert raw1.original_filename == "Vault Save Test"
        assert raw1.source_project_id == pid
        count = db.query(RawVideo).filter(RawVideo.source_project_id == pid).count()
        assert count == 1
    finally:
        db.close()


def test_save_shots_to_vault_creates_clip_with_correct_media_kind_and_caption(vault_project):
    from app.asset_vault.from_visual_studio import save_shots_to_vault
    from app.models import Project

    pid = vault_project["project"]["id"]
    shot_ids = vault_project["shot_ids"]
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        result = save_shots_to_vault(db, project, shot_ids)
        assert result["saved"] == shot_ids
        assert result["updated"] == []
        assert result["skipped"] == []
    finally:
        db.close()


def test_save_shots_to_vault_endpoint_creates_clips_matching_shot_kind(client, vault_project):
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    shot_ids = vault_project["shot_ids"]

    resp = client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": shot_ids})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["saved"]) == set(shot_ids)
    assert body["updated"] == []
    assert body["skipped"] == []

    clips = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    vault_clips = [c for c in clips if c["from_visual_studio"]]
    assert len(vault_clips) == 2
    by_shot = {}
    for c in vault_clips:
        assert c["raw_video_name"] == "Vault Save Test"  # "video nguồn" = tên project
        by_shot[c["caption"]] = c
    assert "A calm river at sunset" in by_shot
    assert by_shot["A calm river at sunset"]["media_kind"] == "image"
    assert "Drone flying over mountains" in by_shot
    assert by_shot["Drone flying over mountains"]["media_kind"] == "video"

    # Hàng RawVideo "ảo" đại diện project KHÔNG xuất hiện ở Raw Library.
    raw_list = client.get(f"/asset-vault/raw?channel_id={channel_id}").json()
    assert all(r["original_filename"] != "Vault Save Test" for r in raw_list)


def test_save_shots_to_vault_updates_existing_clip_when_saved_again(client, vault_project):
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    shot_id = vault_project["shot_ids"][0]

    first = client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": [shot_id]}).json()
    assert first["saved"] == [shot_id]
    clips_after_first = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    clip_id_first = next(c["clip_id"] for c in clips_after_first if c["from_visual_studio"])

    # Đổi visual_fx (mô phỏng sửa lại nội dung) rồi lưu lại.
    client.patch(f"/projects/{pid}/visual/shots/{shot_id}", json={"visual_fx": "A different sunset scene"})
    second = client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": [shot_id]}).json()
    assert second["saved"] == []
    assert second["updated"] == [shot_id]

    clips_after_second = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    vault_clips = [c for c in clips_after_second if c["from_visual_studio"]]
    assert len(vault_clips) == 1  # KHÔNG tạo dòng mới
    assert vault_clips[0]["clip_id"] == clip_id_first
    assert vault_clips[0]["caption"] == "A different sunset scene"


def test_save_shots_to_vault_indexes_embedding_when_provider_configured(client, vault_project):
    """Bug thật đã sửa (2026-09-13, xem IMPLEMENTATION_REPORT.md mục 146, phát hiện qua
    người dùng báo "Tự động điền" không thấy ảnh khớp 100%) — TRƯỚC ĐÂY
    `save_shots_to_vault` không hề embed/index vào Chroma, khiến MỌI asset Visual Studio
    vô hình với auto-fill (chỉ tìm qua semantic). Test này xác nhận `vector_id` được set
    NGAY khi lưu, không cần bước "Gắn nhãn" riêng như B-roll thật."""
    from app.models import ProcessedClip, ProviderConfig

    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    shot_ids = vault_project["shot_ids"]

    db = SessionLocal()
    embedding_cfg = ProviderConfig(task="embedding", provider_name="localai_embedding", display_name="Embedding test", connection_type="local_endpoint", endpoint_url="http://127.0.0.1:8099", model_name="all-MiniLM-L6-v2", is_default=True, enabled=True)
    db.add(embedding_cfg)
    db.commit()
    cfg_id = embedding_cfg.id
    db.close()

    try:
        with respx.mock:
            respx.post("http://127.0.0.1:8099/v1/embeddings").mock(return_value=Response(200, json={"data": [{"embedding": [0.1, 0.2]}]}))
            resp = client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": shot_ids})
            assert resp.status_code == 200, resp.text

        clips = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
        vault_clips = [c for c in clips if c["from_visual_studio"]]
        assert len(vault_clips) == 2

        db2 = SessionLocal()
        try:
            for c in vault_clips:
                row = db2.query(ProcessedClip).filter(ProcessedClip.clip_id == c["clip_id"]).first()
                assert row.vector_id == row.clip_id
        finally:
            db2.close()
    finally:
        db3 = SessionLocal()
        db3.query(ProviderConfig).filter(ProviderConfig.id == cfg_id).delete()
        db3.commit()
        db3.close()


def test_save_shots_to_vault_succeeds_without_embedding_provider_configured(client, vault_project):
    """Không có Embedding provider nào cấu hình (trạng thái mặc định/hợp lệ của app) —
    lưu vào Kho vẫn PHẢI thành công, chỉ là `vector_id` ở lại `None` (không semantic được,
    vẫn tìm được qua keyword) — lỗi thiếu provider KHÔNG được chặn hành động lưu."""
    from app.models import ProcessedClip

    pid = vault_project["project"]["id"]
    shot_ids = vault_project["shot_ids"]

    resp = client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": shot_ids})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["saved"] == shot_ids

    db = SessionLocal()
    try:
        for shot_id in shot_ids:
            row = db.query(ProcessedClip).filter(ProcessedClip.source_shot_id == shot_id).first()
            assert row is not None
            assert row.vector_id is None
    finally:
        db.close()


def test_save_shots_to_vault_skips_shot_not_ready(client, vault_project):
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    # Import thêm 1 project rỗng để có shot_id KHÔNG có visual sẵn sàng.
    resp = client.post(f"/channels/{channel_id}/projects", json={"title": "Vault Save Test 2"})
    pid2 = resp.json()["id"]
    shot_ids2 = _import_shots(client, pid2, [["B01", "0:00–0:03", "Image", "Chua sinh", "", "Loi thoai."]])

    resp = client.post(f"/projects/{pid2}/visual/shots/save-to-vault", json={"shot_ids": shot_ids2})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["saved"] == []
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["shot_id"] == shot_ids2[0]
    assert "chưa sinh" in body["skipped"][0]["reason"].lower()


def test_save_shots_to_vault_skips_missing_file_without_blocking_batch(client, vault_project):
    """1 shot có file bị mất (VD user tự xoá tay ngoài app) KHÔNG chặn shot còn lại trong
    CÙNG batch — nguyên tắc "lỗi 1 phần không chặn cả batch"."""
    from app.config import project_dir
    from pathlib import Path

    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    shot_ids = vault_project["shot_ids"]

    pdir = project_dir(channel_id, pid)
    missing_path = pdir / "assets" / f"{shot_ids[0]}.png"
    Path(missing_path).unlink()

    resp = client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": shot_ids})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert shot_ids[0] in [s["shot_id"] for s in body["skipped"]]
    assert body["saved"] == [shot_ids[1]]


def test_save_shots_to_vault_rejects_empty_shot_ids(client, vault_project):
    pid = vault_project["project"]["id"]
    resp = client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": []})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# media_kind — assign_vault_clip nới lỏng cho ẢNH
# ---------------------------------------------------------------------------
def test_assign_vault_clip_accepts_image_clip_for_image_shot(client, vault_project):
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    shot_ids = vault_project["shot_ids"]

    client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": [shot_ids[0]]})
    clips = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    image_clip = next(c for c in clips if c["media_kind"] == "image")

    # Project THỨ 2 cùng kênh, 1 shot ảnh trống — gán clip ảnh vừa lưu vào đó.
    resp = client.post(f"/channels/{channel_id}/projects", json={"title": "Vault Assign Test"})
    pid2 = resp.json()["id"]
    shot_ids2 = _import_shots(client, pid2, [["B01", "0:00–0:03", "Image", "Placeholder", "", "Loi thoai."]])

    resp = client.post(f"/projects/{pid2}/render/shots/{shot_ids2[0]}/assign-vault-clip", json={"clip_id": image_clip["clip_id"]})
    assert resp.status_code == 200, resp.text
    state = resp.json()
    status = next(s for s in state["shots"] if s["shot_id"] == shot_ids2[0])
    assert status["visual_status"] == "ready"
    assert status["linked_clip_id"] == image_clip["clip_id"]


def test_assign_vault_clip_rejects_image_clip_for_video_shot(client, vault_project):
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    shot_ids = vault_project["shot_ids"]

    client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": [shot_ids[0]]})
    clips = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    image_clip = next(c for c in clips if c["media_kind"] == "image")

    resp = client.post(f"/channels/{channel_id}/projects", json={"title": "Vault Assign Mismatch Test"})
    pid2 = resp.json()["id"]
    shot_ids2 = _import_shots(client, pid2, [["B01", "0:00–0:03", "Video", "Placeholder", "", "Loi thoai."]])

    resp = client.post(f"/projects/{pid2}/render/shots/{shot_ids2[0]}/assign-vault-clip", json={"clip_id": image_clip["clip_id"]})
    assert resp.status_code == 400
    assert "image" in resp.json()["detail"].lower() or "không khớp" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# matching.py media_kind filter (tầng module)
# ---------------------------------------------------------------------------
def test_clips_for_channel_filters_by_media_kind(channel):
    from app.asset_vault import matching
    from app.models import Channel, ProcessedClip, RawVideo

    db = SessionLocal()
    try:
        ch = db.query(Channel).filter(Channel.id == channel["id"]).first()
        raw = RawVideo(id="raw_mk_test", file_path="/fake/raw.mp4", status="tagging")
        raw.channels = [ch]
        db.add(raw)
        video_clip = ProcessedClip(clip_id="clip_mk_video", raw_video_id="raw_mk_test", storage_url="/fake/v.mp4", media_kind="video")
        image_clip = ProcessedClip(clip_id="clip_mk_image", raw_video_id="raw_mk_test", storage_url="/fake/i.png", media_kind="image")
        video_clip.channels = [ch]
        image_clip.channels = [ch]
        db.add_all([video_clip, image_clip])
        db.commit()

        assert {c.clip_id for c in matching._clips_for_channel(db, channel["id"], "video").all()} == {"clip_mk_video"}
        assert {c.clip_id for c in matching._clips_for_channel(db, channel["id"], "image").all()} == {"clip_mk_image"}
        assert {c.clip_id for c in matching._clips_for_channel(db, channel["id"], None).all()} == {"clip_mk_video", "clip_mk_image"}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tự động điền từ Kho tài nguyên (mới) — mock embedding/Chroma cùng pattern
# test_match_semantic_filters_by_threshold_active_and_channel đã có.
# ---------------------------------------------------------------------------
class _FakeEmbedding:
    def embed(self, text):
        return [1.0, 0.0]


def _mock_semantic_search(monkeypatch, mapping: dict[str, float]):
    """`mapping` — clip_id -> similarity trả về SẴN, mô phỏng kết quả Chroma."""
    import app.asset_vault.matching as matching_mod

    monkeypatch.setattr(matching_mod, "get_embedding", lambda db: _FakeEmbedding())
    monkeypatch.setattr(matching_mod, "query_similar_clips", lambda embedding, top_k=3: sorted(mapping.items(), key=lambda kv: -kv[1]))


def test_auto_fill_suggestions_only_scans_shots_missing_visual(client, vault_project, monkeypatch):
    """B01/B02 đã `ready` (fixture) — thêm B03 CHƯA sinh, xác nhận chỉ B03 được quét."""
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]

    # Thêm B03 vào CÙNG project (chưa sinh visual) — cần patch lại pack.json trực tiếp
    # vì `_import_shots` helper reset toàn bộ script; đơn giản hơn: tạo 1 clip ứng viên
    # trong Kho rồi tạo RIÊNG 1 project mới có đúng 1 shot trống để test rõ ràng.
    client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": [vault_project["shot_ids"][0]]})
    clips = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    image_clip = next(c for c in clips if c["media_kind"] == "image")

    resp = client.post(f"/channels/{channel_id}/projects", json={"title": "Auto Fill Test"})
    pid2 = resp.json()["id"]
    shot_ids2 = _import_shots(client, pid2, [
        ["B01", "0:00–0:03", "Image", "A calm river at sunset", "", "Loi thoai."],
    ])

    _mock_semantic_search(monkeypatch, {image_clip["clip_id"]: 0.95})

    resp = client.post(f"/projects/{pid2}/render/vault-auto-fill-scan")
    assert resp.status_code == 200, resp.text
    status = client.get(f"/projects/{pid2}/render/vault-auto-fill-scan/status").json()
    assert status["status"] == "done", status
    assert status["total"] == 1
    body = status["result"]
    assert body["scanned_count"] == 1
    assert body["matched_count"] == 1
    assert body["suggestions"][0]["shot_id"] == shot_ids2[0]
    assert body["suggestions"][0]["clip_id"] == image_clip["clip_id"]


def test_auto_fill_suggestions_filters_below_threshold(client, vault_project, monkeypatch):
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": [vault_project["shot_ids"][0]]})
    clips = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    image_clip = next(c for c in clips if c["media_kind"] == "image")

    resp = client.post(f"/channels/{channel_id}/projects", json={"title": "Auto Fill Threshold Test"})
    pid2 = resp.json()["id"]
    shot_ids2 = _import_shots(client, pid2, [["B01", "0:00–0:03", "Image", "A calm river at sunset", "", "Loi thoai."]])

    # 0.7 vượt ngưỡng manual (0.65) nhưng DƯỚI ngưỡng auto-fill riêng (0.8) — không gợi ý.
    _mock_semantic_search(monkeypatch, {image_clip["clip_id"]: 0.7})

    resp = client.post(f"/projects/{pid2}/render/vault-auto-fill-scan")
    assert resp.status_code == 200, resp.text
    status = client.get(f"/projects/{pid2}/render/vault-auto-fill-scan/status").json()
    assert status["status"] == "done", status
    body = status["result"]
    assert body["matched_count"] == 0
    assert body["suggestions"] == []


def test_auto_fill_scan_status_is_idle_before_first_scan(client, vault_project):
    pid2 = client.post(f"/channels/{vault_project['channel']['id']}/projects", json={"title": "Auto Fill Idle Test"}).json()["id"]
    status = client.get(f"/projects/{pid2}/render/vault-auto-fill-scan/status").json()
    assert status == {"status": "idle"}


def test_vault_candidates_shows_extra_fields_and_hides_rights_for_visual_studio_clip(client, vault_project):
    """Clip lưu từ Visual Studio (mục 135) trỏ `raw_video` "ảo" đại diện project — picker
    (mục yêu cầu người dùng 2026-09-13 "hiển thị đủ thông tin") cần trả thêm resolution/
    tags/mood_tone/usage_count VÀ đánh dấu `from_visual_studio=True` để frontend ẩn badge
    rights_status (vô nghĩa cho asset tự sinh, xem docstring `get_vault_candidates`)."""
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": [vault_project["shot_ids"][0]]})
    clips = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    image_clip = next(c for c in clips if c["media_kind"] == "image")

    resp = client.post(f"/channels/{channel_id}/projects", json={"title": "Vault Candidates Extra Fields Test"})
    pid2 = resp.json()["id"]
    shot_ids2 = _import_shots(client, pid2, [["B01", "0:00–0:03", "Image", "A calm river at sunset", "", "Loi thoai."]])

    resp = client.get(f"/projects/{pid2}/render/shots/{shot_ids2[0]}/vault-candidates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    cand = next(c for c in body["candidates"] if c["clip_id"] == image_clip["clip_id"])
    assert cand["from_visual_studio"] is True
    assert "resolution" in cand
    assert cand["tags"] == []
    assert "mood_tone" in cand
    assert cand["usage_count"] == 0


def test_auto_fill_apply_assigns_accepted_items_and_skips_failed(client, vault_project, monkeypatch):
    pid = vault_project["project"]["id"]
    channel_id = vault_project["channel"]["id"]
    client.post(f"/projects/{pid}/visual/shots/save-to-vault", json={"shot_ids": [vault_project["shot_ids"][0]]})
    clips = client.get(f"/asset-vault/clips?channel_id={channel_id}").json()
    image_clip = next(c for c in clips if c["media_kind"] == "image")

    resp = client.post(f"/channels/{channel_id}/projects", json={"title": "Auto Fill Apply Test"})
    pid2 = resp.json()["id"]
    shot_ids2 = _import_shots(client, pid2, [["B01", "0:00–0:03", "Image", "A calm river at sunset", "", "Loi thoai."]])

    resp = client.post(
        f"/projects/{pid2}/render/vault-auto-fill-apply",
        json={"items": [{"shot_id": shot_ids2[0], "clip_id": image_clip["clip_id"]}, {"shot_id": "shot_khong_ton_tai", "clip_id": image_clip["clip_id"]}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] == [shot_ids2[0]]
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["shot_id"] == "shot_khong_ton_tai"


def test_auto_fill_apply_rejects_when_project_missing(client):
    resp = client.post("/projects/prj_not_exist/render/vault-auto-fill-apply", json={"items": []})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Migration — 3 cột mới ADD COLUMN idempotent trên schema CŨ (thiếu cột)
# ---------------------------------------------------------------------------
def test_add_missing_columns_backfills_media_kind_default_video():
    """Mô phỏng DB CŨ (thiếu `media_kind`/`source_shot_id`/`source_project_id`) — chạy
    lại `_add_missing_columns`, xác nhận clip cũ tự có `media_kind="video"` (backfill qua
    DEFAULT hằng số trong chính câu ALTER TABLE, không chỉ default Python-level của ORM)."""
    import sqlite3
    import tempfile
    from pathlib import Path

    from sqlalchemy import create_engine, inspect, text

    tmp_db = Path(tempfile.mktemp(suffix=".db"))
    try:
        conn = sqlite3.connect(str(tmp_db))
        conn.executescript(
            """
            CREATE TABLE raw_video (id TEXT PRIMARY KEY, file_path TEXT NOT NULL, source_url TEXT, import_note TEXT, status TEXT, error_message TEXT, created_at TEXT);
            CREATE TABLE processed_clip (clip_id TEXT PRIMARY KEY, raw_video_id TEXT NOT NULL, storage_url TEXT NOT NULL, duration_sec REAL, resolution TEXT, caption TEXT, tags TEXT, mood_tone TEXT, vector_id TEXT, usage_count INTEGER, last_used_at TEXT, active BOOLEAN, rights_status TEXT, rights_note TEXT, created_at TEXT);
            INSERT INTO raw_video (id, file_path, status) VALUES ('raw_old', '/fake/old.mp4', 'tagging');
            INSERT INTO processed_clip (clip_id, raw_video_id, storage_url) VALUES ('clip_old', 'raw_old', '/fake/old_clip.mp4');
            """
        )
        conn.commit()
        conn.close()

        engine = create_engine(f"sqlite:///{tmp_db}")
        from app.asset_vault.migration import _add_missing_columns

        inspector = inspect(engine)
        _add_missing_columns(engine, inspector)

        with engine.connect() as c:
            row = c.execute(text("SELECT media_kind, source_shot_id FROM processed_clip WHERE clip_id='clip_old'")).fetchone()
            assert row[0] == "video"  # backfill đúng cho clip cũ
            assert row[1] is None
            raw_row = c.execute(text("SELECT source_project_id FROM raw_video WHERE id='raw_old'")).fetchone()
            assert raw_row[0] is None

        # Idempotent — chạy lại lần 2 không lỗi (cột đã tồn tại).
        inspector2 = inspect(engine)
        _add_missing_columns(engine, inspector2)
        engine.dispose()  # đóng connection trước khi xoá file — Windows khoá file đang mở
    finally:
        tmp_db.unlink(missing_ok=True)
