"""Kho Tài Nguyên (Asset Vault) — CHANGE_Semantic_BRoll_Asset_Vault.md, chuyển thành kho
TOÀN CỤC + gắn nhiều kênh dạng tag (2026-08-27). Mock HTTP (Vision/Embedding provider) qua
`respx` như mọi provider khác trong app; scene detection/cắt clip/tiến trình dùng ffmpeg +
PySceneDetect THẬT (đã verify tay trước khi viết code, xem docstring
`app/asset_vault/ingest.py` + IMPLEMENTATION_REPORT.md mục 90)."""
from __future__ import annotations

import io
import json
import shutil
import subprocess

import pytest
import respx
from httpx import Response

from app.asset_vault import ingest, matching
from app.db import SessionLocal
from app.models import Channel, ProcessedClip, RawVideo


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    assert path, "cần ffmpeg thật trên PATH"
    return path


def test_new_id_unique_even_when_time_collides(monkeypatch):
    """Cùng bug/fix `_new_id` đã sửa ở `test_projects_brief.py` (xem docstring đầy đủ ở
    đó) — `asset_vault/ingest.py` có bản copy RIÊNG, cần verify riêng."""
    monkeypatch.setattr(ingest.time, "time", lambda: 1789999999.999)
    ids = [ingest._new_id("clip") for _ in range(50)]
    assert len(set(ids)) == 50


def _make_two_scene_video(path) -> None:
    """Video 6s, 2 cảnh màu tách biệt (0-3s đỏ, 3-6s xanh) — cùng clip test đã verify
    tay `scenedetect.AdaptiveDetector` phát hiện đúng 2 scene tại mốc 3.0s."""
    ffmpeg = _ffmpeg()
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=3", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=3",
         "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-r", "25", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, check=True, text=True,
    )


def _seed_raw_video(db, channel_ids: list[str], raw_id: str, file_path: str = "/fake/raw.mp4") -> RawVideo:
    channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all()
    raw = RawVideo(id=raw_id, file_path=file_path, status="tagging")
    raw.channels = channels
    db.add(raw)
    db.commit()
    return raw


def _seed_clip(db, channel_ids: list[str], clip_id: str, caption="", tags=None, active=True, rights_status="unverified", usage_count=0, storage_url=None, duration_sec=0.0, raw_video_id=None):
    if raw_video_id is None:
        raw_video_id = f"raw_for_{clip_id}"
        _seed_raw_video(db, channel_ids, raw_video_id)
    clip = ProcessedClip(
        clip_id=clip_id, raw_video_id=raw_video_id, storage_url=storage_url or f"/fake/{clip_id}.mp4",
        caption=caption, tags=json.dumps(tags or []), active=active, rights_status=rights_status,
        usage_count=usage_count, duration_sec=duration_sec,
    )
    # Clip có tag kênh RIÊNG từ 2026-08-28 (xem models.py::ProcessedClip) — helper seed
    # test này giả lập ĐÚNG hành vi thật lúc cắt cảnh (`ingest.py::_make_clip_row`): sao
    # chép channel_ids truyền vào (không phải luôn đọc lại từ raw_video, vì raw_video có
    # thể KHÔNG có đúng channel_ids này nếu caller truyền `raw_video_id` có sẵn của 1 raw
    # video khác kênh — giữ đúng ý caller).
    clip.channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all()
    db.add(clip)
    db.commit()
    return clip


# ---------------------------------------------------------------------------
# Providers (Vision/Embedding) — mock HTTP qua respx (không đụng schema — giữ nguyên)
# ---------------------------------------------------------------------------
@respx.mock
def test_localai_vision_caption_parses_json_response():
    from app.providers.vision_localai import LocalAIVisionProvider

    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": '{"caption": "a river at sunset", "tags": ["river", "sunset"], "mood_tone": "calm"}'}}]})
    )
    provider = LocalAIVisionProvider()
    result = provider.caption(b"\x89PNG\r\n\x1a\n0000", prompt="describe this")
    assert result.caption == "a river at sunset"
    assert result.tags == ["river", "sunset"]
    assert result.mood_tone == "calm"


@respx.mock
def test_localai_vision_caption_falls_back_when_not_json():
    from app.providers.vision_localai import LocalAIVisionProvider

    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": "just a plain sentence, no JSON here"}}]})
    )
    provider = LocalAIVisionProvider()
    result = provider.caption(b"fake", prompt="describe")
    assert result.caption == "just a plain sentence, no JSON here"
    assert result.tags == []


@respx.mock
def test_localai_vision_test_connection_ok():
    from app.providers.vision_localai import LocalAIVisionProvider

    respx.get("http://127.0.0.1:8080/v1/models").mock(return_value=Response(200, json={"data": []}))
    status = LocalAIVisionProvider().test_connection()
    assert status.ok is True


@respx.mock
def test_gemini_vision_caption_parses_json_response():
    from app.providers.vision_gemini import GeminiVisionProvider

    respx.post(url__regex=r"https://generativelanguage\.googleapis\.com/v1beta/models/.*:generateContent.*").mock(
        return_value=Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"caption": "a cat", "tags": ["cat"], "mood_tone": "joyful"}'}]}}]})
    )
    provider = GeminiVisionProvider(api_key="sk-test")
    result = provider.caption(b"fake", prompt="describe")
    assert result.caption == "a cat"
    assert result.mood_tone == "joyful"


@respx.mock
def test_localai_embedding_tries_v1_then_falls_back_to_bare_path():
    from app.providers.embedding_localai import LocalAIEmbeddingProvider

    respx.post("http://127.0.0.1:8080/v1/embeddings").mock(return_value=Response(404))
    respx.post("http://127.0.0.1:8080/embeddings").mock(return_value=Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]}))
    provider = LocalAIEmbeddingProvider()
    vector = provider.embed("some text")
    assert vector == [0.1, 0.2, 0.3]


@respx.mock
def test_localai_embedding_uses_v1_directly_when_available():
    from app.providers.embedding_localai import LocalAIEmbeddingProvider

    route = respx.post("http://127.0.0.1:8080/v1/embeddings").mock(return_value=Response(200, json={"data": [{"embedding": [0.5]}]}))
    provider = LocalAIEmbeddingProvider()
    vector = provider.embed("text")
    assert vector == [0.5]
    assert route.called


# ---------------------------------------------------------------------------
# Ingest — cắt cảnh thủ công/tự động + captioning (ffmpeg thật, provider mock)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_import_raw_video_upload_saves_file_and_creates_row(channel):
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "test.mp4", b"\x00\x00\x00\x18ftyp0000", import_note="from stock library X")
        assert raw.status == "detecting"
        assert raw.import_note == "from stock library X"
        assert [c.id for c in raw.channels] == [channel["id"]]
        from pathlib import Path

        assert Path(raw.file_path).exists()
    finally:
        db.close()


def test_import_raw_video_upload_rejects_unknown_channel_id(channel):
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            ingest.import_raw_video_upload(db, ["khong-ton-tai"], "test.mp4", b"data")
    finally:
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_import_raw_video_upload_tags_multiple_channels(channel, channel2):
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"], channel2["id"]], "test.mp4", b"\x00\x00\x00\x18ftyp0000")
        assert {c.id for c in raw.channels} == {channel["id"], channel2["id"]}
    finally:
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_manual_cut_clip_creates_correct_duration_and_strips_audio(channel, tmp_path):
    ffmpeg = _ffmpeg()
    raw_path = tmp_path / "raw.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=25", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(raw_path)],
        capture_output=True, check=True, text=True,
    )
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "raw.mp4", raw_path.read_bytes())
        clip = ingest.manual_cut_clip(db, raw, 2.0, 4.0)
        assert clip.duration_sec == pytest.approx(2.0, abs=0.1)
        assert [c.id for c in clip.channels] == [channel["id"]]  # kênh sao chép từ raw_video NGAY lúc cắt (2026-08-28)
        probe = subprocess.run(
            [shutil.which("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", clip.storage_url],
            capture_output=True, check=True, text=True,
        )
        assert "audio" not in probe.stdout, "clip cắt phải TÁCH audio (-an), chỉ giữ video sạch"
        db.refresh(raw)
        assert raw.status == "tagging"
    finally:
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_auto_detect_scenes_splits_two_scene_video_correctly(channel, tmp_path):
    """Verify thật (không suy đoán API `scenedetect`) — video 2 cảnh tách biệt phải cho
    ĐÚNG 2 clip, mỗi clip ~3s."""
    raw_path = tmp_path / "raw.mp4"
    _make_two_scene_video(raw_path)
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "raw.mp4", raw_path.read_bytes())
        clips = ingest.auto_detect_scenes(db, raw)
        assert len(clips) == 2
        assert clips[0].duration_sec == pytest.approx(3.0, abs=0.2)
        assert clips[1].duration_sec == pytest.approx(3.0, abs=0.2)
        assert all(c.id == channel["id"] for clip in clips for c in clip.channels)  # kênh sao chép từ raw_video (2026-08-28)
        db.refresh(raw)
        assert raw.status == "tagging"
        assert raw.progress_current is None and raw.progress_total is None  # reset khi xong
    finally:
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_auto_detect_scenes_reports_real_progress_during_cutting(channel, tmp_path):
    """Verify THẬT tiến trình (2026-08-27) — không suy đoán, đo giá trị thật ghi vào
    `progress_current`/`progress_total` NGAY TRONG LÚC hàm chạy (qua monkeypatch
    `db.commit`, bắt snapshot mỗi lần)."""
    raw_path = tmp_path / "raw.mp4"
    _make_two_scene_video(raw_path)
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "raw.mp4", raw_path.read_bytes())
        snapshots = []
        orig_commit = db.commit

        def logging_commit():
            snapshots.append((raw.progress_label, raw.progress_current, raw.progress_total))
            orig_commit()

        db.commit = logging_commit
        clips = ingest.auto_detect_scenes(db, raw)
        assert len(clips) == 2
        cutting_snapshots = [s for s in snapshots if s[0] and "cắt cảnh" in s[0]]
        assert len(cutting_snapshots) >= 2, "phải có ít nhất 1 snapshot progress cho mỗi clip cắt"
        assert cutting_snapshots[-1][1] == 2 and cutting_snapshots[-1][2] == 2  # clip cuối: current=total=2
    finally:
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_auto_detect_scenes_single_continuous_video_yields_one_clip(channel, tmp_path):
    """Video KHÔNG có ranh giới cảnh nào (1 màu xuyên suốt) — coi TOÀN BỘ là 1 clip,
    không phải lỗi (nhánh `if not scene_list` trong `auto_detect_scenes`)."""
    ffmpeg = _ffmpeg()
    raw_path = tmp_path / "raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=2", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "raw.mp4", raw_path.read_bytes())
        clips = ingest.auto_detect_scenes(db, raw)
        assert len(clips) == 1
        assert clips[0].duration_sec == pytest.approx(2.0, abs=0.2)
    finally:
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
@respx.mock
def test_caption_clip_updates_fields_and_upserts_vector(channel, tmp_path, monkeypatch):
    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": '{"caption": "mountain landscape", "tags": ["mountain", "nature"], "mood_tone": "epic"}'}}]})
    )
    respx.post("http://127.0.0.1:8080/v1/embeddings").mock(return_value=Response(200, json={"data": [{"embedding": [0.1, 0.2]}]}))

    db = SessionLocal()
    added_config_ids: list[int] = []
    try:
        from app.models import ProviderConfig

        vision_cfg = ProviderConfig(task="vision", provider_name="localai_vision", display_name="Vision test", connection_type="local_endpoint", endpoint_url="http://127.0.0.1:8080", model_name="moondream2", is_default=True, enabled=True)
        embedding_cfg = ProviderConfig(task="embedding", provider_name="localai_embedding", display_name="Embedding test", connection_type="local_endpoint", endpoint_url="http://127.0.0.1:8080", model_name="all-MiniLM-L6-v2", is_default=True, enabled=True)
        db.add(vision_cfg)
        db.add(embedding_cfg)
        db.commit()
        added_config_ids = [vision_cfg.id, embedding_cfg.id]

        ffmpeg = _ffmpeg()
        raw_path = tmp_path / "raw.mp4"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x240:d=2", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "raw.mp4", raw_path.read_bytes())
        clip = ingest.manual_cut_clip(db, raw, 0.0, 2.0)

        ingest.caption_clip(db, clip)

        db.refresh(clip)
        assert clip.caption == "mountain landscape"
        assert json.loads(clip.tags) == ["mountain", "nature"]
        assert clip.mood_tone == "epic"
        assert clip.vector_id == clip.clip_id
    finally:
        from app.models import ProviderConfig

        if added_config_ids:
            db.query(ProviderConfig).filter(ProviderConfig.id.in_(added_config_ids)).delete(synchronize_session=False)
            db.commit()
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_caption_all_pending_clips_continues_after_one_error(channel, tmp_path):
    """Không cấu hình Vision/Embedding provider nào — `caption_clip` raise
    `NoProviderConfiguredError` cho MỌI clip, nhưng `caption_all_pending_clips` không để
    lỗi văng ra ngoài (ghi `error_message`, đặt `status="error"`) — đúng nguyên tắc lỗi 1
    phần không chặn cả batch."""
    ffmpeg = _ffmpeg()
    raw_path = tmp_path / "raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "raw.mp4", raw_path.read_bytes())
        ingest.manual_cut_clip(db, raw, 0.0, 2.0)
        ingest.caption_all_pending_clips(db, raw)
        db.refresh(raw)
        assert raw.status == "error"
        assert raw.error_message
        clip = db.query(ProcessedClip).filter(ProcessedClip.raw_video_id == raw.id).first()
        assert clip.caption_error  # mới (2026-08-27) — lỗi ghi CẢ vào từng clip, không chỉ RawVideo
    finally:
        db.close()


def test_caption_clips_batch_spans_multiple_raw_videos_and_tracks_per_clip_error(channel, tmp_path):
    """`caption_clips` (bulk gắn nhãn theo lựa chọn tự do) — clip có thể trải NHIỀU
    raw_video khác nhau, không có 1 RawVideo chung để gắn cờ lỗi — verify lỗi ghi ĐÚNG vào
    `ProcessedClip.caption_error` của TỪNG clip, không chặn các clip khác."""
    db = SessionLocal()
    try:
        clip_a = _seed_clip(db, [channel["id"]], "clip_batch_a")
        clip_b = _seed_clip(db, [channel["id"]], "clip_batch_b")  # raw_video khác clip_a (mặc định _seed_clip)
        ok, err = ingest.caption_clips(db, [clip_a, clip_b])
        assert ok == 0 and err == 2  # không cấu hình Vision/Embedding provider nào — cả 2 đều lỗi
        db.refresh(clip_a)
        db.refresh(clip_b)
        assert clip_a.caption_error and clip_b.caption_error
        assert clip_a.raw_video_id != clip_b.raw_video_id
    finally:
        db.close()


def test_delete_processed_clip_removes_file_and_row(channel, tmp_path):
    db = SessionLocal()
    try:
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"fake")
        clip = _seed_clip(db, [channel["id"]], "clip_del_test", storage_url=str(f))
        ingest.delete_processed_clip(db, clip)
        assert not f.exists()
        assert db.query(ProcessedClip).filter(ProcessedClip.clip_id == "clip_del_test").first() is None
    finally:
        db.close()


def test_batch_delete_clips_removes_files_and_rows(client, channel, tmp_path):
    db = SessionLocal()
    try:
        f1 = tmp_path / "c1.mp4"
        f2 = tmp_path / "c2.mp4"
        f1.write_bytes(b"fake")
        f2.write_bytes(b"fake")
        _seed_clip(db, [channel["id"]], "clip_batch_del_1", storage_url=str(f1))
        _seed_clip(db, [channel["id"]], "clip_batch_del_2", storage_url=str(f2))
    finally:
        db.close()
    resp = client.post("/asset-vault/clips/batch-delete", json={"clip_ids": ["clip_batch_del_1", "clip_batch_del_2"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 2
    assert not f1.exists() and not f2.exists()
    remaining = client.get("/asset-vault/clips").json()
    assert all(c["clip_id"] not in ("clip_batch_del_1", "clip_batch_del_2") for c in remaining)


def test_batch_delete_clips_rejects_empty_list(client):
    resp = client.post("/asset-vault/clips/batch-delete", json={"clip_ids": []})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Matching — lọc theo kênh qua JOIN (2026-08-27, xem matching.py::_clips_for_channel)
# ---------------------------------------------------------------------------
def test_match_by_keyword_scores_by_word_overlap(channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_kw_1", caption="a river flowing through a green forest", tags=["river", "forest"])
        _seed_clip(db, [channel["id"]], "clip_kw_2", caption="a busy city street at night", tags=["city", "night"])
        results = matching.match_by_keyword(db, channel["id"], "footage of a river in the forest")
        assert results[0][0].clip_id == "clip_kw_1"
        assert 0 < results[0][1] <= 1
    finally:
        db.close()


def test_match_by_keyword_excludes_inactive_clips(channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_inactive", caption="mountain river", tags=["river"], active=False)
        results = matching.match_by_keyword(db, channel["id"], "river")
        assert all(c.clip_id != "clip_inactive" for c, _ in results)
    finally:
        db.close()


def test_match_by_keyword_excludes_clips_from_other_channel(channel, channel2):
    """Test MỚI (2026-08-27) — clip của kênh khác KHÔNG được lẫn vào kết quả, dù cùng từ
    khoá — đúng ý nghĩa cốt lõi của việc lọc theo kênh qua JOIN thay Chroma vật lý tách."""
    db = SessionLocal()
    try:
        _seed_clip(db, [channel2["id"]], "clip_other_ch", caption="a river in the forest", tags=["river"])
        results = matching.match_by_keyword(db, channel["id"], "river forest")
        assert all(c.clip_id != "clip_other_ch" for c, _ in results)
    finally:
        db.close()


def test_match_by_keyword_includes_clip_tagged_to_multiple_channels(channel, channel2):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"], channel2["id"]], "clip_multi_ch", caption="a river in the forest", tags=["river"])
        results_a = matching.match_by_keyword(db, channel["id"], "river forest")
        results_b = matching.match_by_keyword(db, channel2["id"], "river forest")
        assert any(c.clip_id == "clip_multi_ch" for c, _ in results_a)
        assert any(c.clip_id == "clip_multi_ch" for c, _ in results_b)
    finally:
        db.close()


def test_apply_dedup_removes_used_clip_ids(channel):
    db = SessionLocal()
    try:
        a = _seed_clip(db, [channel["id"]], "clip_dedup_a")
        b = _seed_clip(db, [channel["id"]], "clip_dedup_b")
        result = matching.apply_dedup([a, b], used_clip_ids={"clip_dedup_a"})
        assert [c.clip_id for c in result] == ["clip_dedup_b"]
    finally:
        db.close()


def test_fallback_neutral_broll_filters_ambient_tag(channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_ambient", tags=["ambient", "clouds"])
        _seed_clip(db, [channel["id"]], "clip_specific", tags=["interview"])
        results = matching.fallback_neutral_broll(db, channel["id"])
        assert [c.clip_id for c in results] == ["clip_ambient"]
    finally:
        db.close()


def test_match_semantic_filters_by_threshold_active_and_channel(channel, channel2):
    """`query_similar_clips` giờ KHÔNG nhận `channel_id` (Chroma toàn cục) — lọc kênh xảy
    ra ở tầng SQL SAU khi có kết quả (xem `match_semantic`), verify bằng cách trộn candidate
    của kênh khác vào kết quả giả lập."""
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_sem_1", caption="a calm lake")
        _seed_clip(db, [channel2["id"]], "clip_sem_other_channel", caption="a calm lake too")

        class _FakeEmbedding:
            def embed(self, text):
                return [1.0, 0.0]

        monkeypatch_target = "app.asset_vault.matching.get_embedding"
        import app.asset_vault.matching as matching_mod

        orig_get_embedding = matching_mod.get_embedding
        matching_mod.get_embedding = lambda db: _FakeEmbedding()
        orig_query = matching_mod.query_similar_clips
        matching_mod.query_similar_clips = lambda embedding, top_k=3: [
            ("clip_sem_1", 0.9), ("clip_sem_other_channel", 0.85), ("clip_sem_missing", 0.8), ("clip_sem_1", 0.4),
        ]
        try:
            results = matching.match_semantic(db, channel["id"], "a peaceful lake", threshold=0.65)
        finally:
            matching_mod.get_embedding = orig_get_embedding
            matching_mod.query_similar_clips = orig_query

        assert len(results) == 1
        assert results[0][0].clip_id == "clip_sem_1"
        assert results[0][1] == 0.9
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Router asset_vault.py — qua HTTP thật (test client), API TOÀN CỤC
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_upload_raw_video_endpoint(client, channel):
    ffmpeg = shutil.which("ffmpeg")
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        raw_path = Path(d) / "raw.mp4"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
        resp = client.post(
            "/asset-vault/raw/upload",
            data={"channel_ids": json.dumps([channel["id"]])},
            files={"file": ("Great Wall drone footage (final cut).mp4", raw_path.read_bytes(), "video/mp4")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "detecting"
    assert body["channels"] == [{"id": channel["id"], "name": channel["name"]}]
    # `original_filename` — mới (2026-08-27) — giữ NGUYÊN VẸN tên gốc (kể cả khoảng
    # trắng/dấu ngoặc) để hiển thị; tên file THẬT trên đĩa vẫn phải chứa 1 bản đã lọc ký
    # tự nguy hiểm của tên gốc, không chỉ là ID kỹ thuật trơ trọi.
    assert body["original_filename"] == "Great Wall drone footage (final cut).mp4"
    from app.db import SessionLocal
    from app.models import RawVideo

    db = SessionLocal()
    try:
        raw = db.query(RawVideo).filter(RawVideo.id == body["id"]).first()
        assert "Great_Wall_drone_footage" in raw.file_path
    finally:
        db.close()

    listed = client.get("/asset-vault/raw").json()
    assert any(r["id"] == body["id"] for r in listed)

    listed_filtered = client.get("/asset-vault/raw", params={"channel_id": channel["id"]}).json()
    assert any(r["id"] == body["id"] for r in listed_filtered)


def test_upload_raw_video_rejects_without_channel_ids(client):
    resp = client.post("/asset-vault/raw/upload", data={"channel_ids": "[]"}, files={"file": ("raw.mp4", b"data", "video/mp4")})
    assert resp.status_code == 400


def test_upload_raw_video_rejects_empty_file(client, channel):
    resp = client.post("/asset-vault/raw/upload", data={"channel_ids": json.dumps([channel["id"]])}, files={"file": ("raw.mp4", b"", "video/mp4")})
    assert resp.status_code == 400


def test_import_url_requires_nonempty_url(client, channel):
    resp = client.post("/asset-vault/raw/import-url", json={"url": "", "channel_ids": [channel["id"]]})
    assert resp.status_code == 400


def test_import_url_requires_channel_ids(client):
    resp = client.post("/asset-vault/raw/import-url", json={"url": "https://example.com/x.mp4", "channel_ids": []})
    assert resp.status_code == 400


def test_raw_video_404_for_unknown_raw_id(client):
    resp = client.get("/asset-vault/raw", params={"channel_id": "khong-ton-tai"})
    assert resp.status_code == 200
    assert resp.json() == []  # kênh không tồn tại -> lọc ra rỗng, KHÔNG phải 404 (đúng API toàn cục, không có 1 kênh "sở hữu" endpoint)


def test_get_asset_vault_folders_returns_real_existing_paths(client):
    """Nút "Mở thư mục" ở UI cần 2 đường dẫn filesystem THẬT — verify cả 2 tồn tại thật
    trên đĩa (không chỉ trả chuỗi), khớp đúng `asset_vault_raw_dir()`/`asset_vault_clips_dir()`."""
    from pathlib import Path

    from app.config import asset_vault_clips_dir, asset_vault_raw_dir

    resp = client.get("/asset-vault/folders")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["raw_dir"] == str(asset_vault_raw_dir())
    assert body["clips_dir"] == str(asset_vault_clips_dir())
    assert Path(body["raw_dir"]).is_dir()
    assert Path(body["clips_dir"]).is_dir()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_manual_cut_endpoint_creates_clip(client, channel, tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    raw_path = tmp_path / "raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=4", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
    raw = client.post("/asset-vault/raw/upload", data={"channel_ids": json.dumps([channel["id"]])}, files={"file": ("raw.mp4", raw_path.read_bytes(), "video/mp4")}).json()

    resp = client.post(f"/asset-vault/raw/{raw['id']}/manual-cut", json={"start_sec": 0.5, "end_sec": 2.5})
    assert resp.status_code == 200, resp.text
    clip = resp.json()
    assert clip["duration_sec"] == pytest.approx(2.0, abs=0.1)
    assert clip["channels"] == [{"id": channel["id"], "name": channel["name"]}]

    listed = client.get("/asset-vault/clips", params={"raw_video_id": raw["id"]}).json()
    assert len(listed) == 1
    assert listed[0]["clip_id"] == clip["clip_id"]

    listed_by_channel = client.get("/asset-vault/clips", params={"channel_id": channel["id"]}).json()
    assert any(c["clip_id"] == clip["clip_id"] for c in listed_by_channel)


def test_manual_cut_endpoint_rejects_invalid_range(client, channel):
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_bad_range")
    finally:
        db.close()
    resp = client.post("/asset-vault/raw/raw_bad_range/manual-cut", json={"start_sec": 3.0, "end_sec": 1.0})
    assert resp.status_code == 400


def test_patch_raw_video_channels_retag(client, channel, channel2):
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_retag")
    finally:
        db.close()
    resp = client.patch("/asset-vault/raw/raw_retag/channels", json={"channel_ids": [channel2["id"]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["channels"] == [{"id": channel2["id"], "name": channel2["name"]}]


def test_patch_raw_video_channels_cascades_to_existing_clips(client, channel, channel2):
    """Sửa kênh RAW VIDEO đồng bộ ghi đè kênh của MỌI clip con hiện có (2026-08-28) — 1
    control ở mức raw video vẫn edit được "cả video + clip con", khớp UX cũ trước khi clip
    có tag riêng."""
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_cascade")
        _seed_clip(db, [channel["id"]], "clip_cascade_1", raw_video_id="raw_cascade")
        _seed_clip(db, [channel["id"]], "clip_cascade_2", raw_video_id="raw_cascade")
    finally:
        db.close()
    resp = client.patch("/asset-vault/raw/raw_cascade/channels", json={"channel_ids": [channel2["id"]]})
    assert resp.status_code == 200, resp.text

    resp = client.get("/asset-vault/clips?raw_video_id=raw_cascade")
    assert resp.status_code == 200, resp.text
    for c in resp.json():
        assert c["channels"] == [{"id": channel2["id"], "name": channel2["name"]}]


def test_patch_raw_video_channels_rejects_empty_list(client, channel):
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_retag_2")
    finally:
        db.close()
    resp = client.patch("/asset-vault/raw/raw_retag_2/channels", json={"channel_ids": []})
    assert resp.status_code == 400


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_get_raw_video_file_serves_content(client, channel, tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    raw_path = tmp_path / "raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
    resp = client.post("/asset-vault/raw/upload", data={"channel_ids": json.dumps([channel["id"]])}, files={"file": ("preview_test.mp4", raw_path.read_bytes(), "video/mp4")})
    raw_id = resp.json()["id"]
    file_resp = client.get(f"/asset-vault/raw/{raw_id}/file")
    assert file_resp.status_code == 200


def _fake_remove_watermark_ok(ffmpeg, video_path, out_path, tmp_dir, *, text_input="watermark", on_progress=None):
    """Giả lập `watermark.pipeline.remove_watermark_from_video` — không chạy Florence-2/
    LaMa thật (chậm, đã verify riêng ở test_watermark.py), chỉ copy file input sang
    out_path + gọi `on_progress` vài lần để test được đúng luồng điều phối/DB."""
    import shutil as _shutil

    if on_progress:
        on_progress(0, 2, "Đang tách frame từ video")
        on_progress(2, 2, "Đang ghép lại video")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(video_path, out_path)
    return [(0, 0, 10, 10)]


def _fake_remove_watermark_fails(*a, **k):
    raise ValueError("Không phát hiện được watermark nào trong video — thử mô tả khác.")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_remove_watermark_from_raw_video_replaces_file_path(monkeypatch, channel, tmp_path):
    from pathlib import Path

    monkeypatch.setattr(ingest, "remove_watermark_from_video", _fake_remove_watermark_ok)
    ffmpeg = _ffmpeg()
    raw_path = tmp_path / "raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=1", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "raw.mp4", raw_path.read_bytes())
        old_path = raw.file_path
        ingest.remove_watermark_from_raw_video(db, raw)
        db.refresh(raw)
        assert raw.file_path != old_path
        assert raw.file_path.endswith("_nowm.mp4")
        assert Path(raw.file_path).exists()
        assert not Path(old_path).exists()  # file cũ (có watermark) bị xoá sau khi thay
        assert raw.progress_current is None and raw.progress_total is None  # progress đã dọn sau khi xong
        assert raw.status == "detecting"  # KHÔNG đổi status — vẫn sẵn sàng "Cắt cảnh tự động" tiếp
    finally:
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_remove_watermark_from_raw_video_uses_isolated_tmp_dir_per_video(monkeypatch, channel, tmp_path):
    """Bug thật (2026-08-28, user báo test 2 video CÙNG LÚC): `tmp_dir` TỪNG là 1 thư mục
    tên CỐ ĐỊNH dùng chung cho MỌI video — 2 lượt xoá watermark song song ghi đè frame của
    nhau (số frame báo giống hệt nhau) và lượt xong trước xoá `finally` mất frame lượt kia
    đang xử lý dở. Test này KHÔNG chạy 2 lượt thật song song (tốn thời gian, model thật) —
    chỉ xác nhận `tmp_dir` truyền cho `remove_watermark_from_video` được TÍNH THEO
    `raw_video.id` (nên chắc chắn khác nhau giữa 2 video khác nhau), bằng cách chặn lại
    (spy) giá trị `tmp_dir` thật đã truyền cho 2 lần gọi liên tiếp trên 2 raw video khác
    nhau."""
    captured_tmp_dirs = []

    def _spy_remove_watermark(ffmpeg, video_path, out_path, tmp_dir, *, text_input="watermark", on_progress=None):
        captured_tmp_dirs.append(tmp_dir)
        return _fake_remove_watermark_ok(ffmpeg, video_path, out_path, tmp_dir, text_input=text_input, on_progress=on_progress)

    monkeypatch.setattr(ingest, "remove_watermark_from_video", _spy_remove_watermark)
    ffmpeg = _ffmpeg()
    db = SessionLocal()
    try:
        for color in ("cyan", "magenta"):
            raw_path = tmp_path / f"raw_{color}.mp4"
            subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d=1", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
            raw = ingest.import_raw_video_upload(db, [channel["id"]], f"raw_{color}.mp4", raw_path.read_bytes())
            ingest.remove_watermark_from_raw_video(db, raw)
    finally:
        db.close()

    assert len(captured_tmp_dirs) == 2
    assert captured_tmp_dirs[0] != captured_tmp_dirs[1]  # 2 video khác nhau -> tmp_dir khác nhau, không còn dùng chung


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_remove_watermark_from_raw_video_sets_error_on_failure(monkeypatch, channel, tmp_path):
    monkeypatch.setattr(ingest, "remove_watermark_from_video", _fake_remove_watermark_fails)
    ffmpeg = _ffmpeg()
    raw_path = tmp_path / "raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=yellow:s=320x240:d=1", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
    db = SessionLocal()
    try:
        raw = ingest.import_raw_video_upload(db, [channel["id"]], "raw.mp4", raw_path.read_bytes())
        with pytest.raises(ValueError):
            ingest.remove_watermark_from_raw_video(db, raw)
        db.refresh(raw)
        assert raw.status == "error"
        assert raw.error_message and "watermark" in raw.error_message.lower()
        assert raw.progress_current is None
    finally:
        db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_remove_watermark_endpoint_runs_via_background_task(monkeypatch, client, channel, tmp_path):
    """`monkeypatch` áp NGAY TRÊN module `app.asset_vault.ingest` — hàm thật `remove_
    watermark_from_raw_video` (router gọi nguyên bản, không mock) tự gọi `remove_
    watermark_from_video` qua namespace CHÍNH module `ingest` nó được định nghĩa, nên patch
    ở đây có hiệu lực dù router import tên hàm ngoài trực tiếp (khác việc patch `app.
    watermark.pipeline...` sẽ KHÔNG có tác dụng vì `ingest.py` đã bind tên vào namespace
    riêng lúc `from ... import` — cùng lưu ý đã áp dụng ở test_remove_watermark_from_raw_
    video_replaces_file_path phía trên). TestClient chạy BackgroundTasks đồng bộ nên assert
    được NGAY sau `client.post`."""
    monkeypatch.setattr(ingest, "remove_watermark_from_video", _fake_remove_watermark_ok)

    ffmpeg = _ffmpeg()
    raw_path = tmp_path / "raw.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=purple:s=320x240:d=1", "-pix_fmt", "yuv420p", str(raw_path)], capture_output=True, check=True, text=True)
    upload_resp = client.post("/asset-vault/raw/upload", data={"channel_ids": json.dumps([channel["id"]])}, files={"file": ("wm.mp4", raw_path.read_bytes(), "video/mp4")})
    raw_id = upload_resp.json()["id"]

    resp = client.post(f"/asset-vault/raw/{raw_id}/remove-watermark")
    assert resp.status_code == 200, resp.text

    listed = client.get("/asset-vault/raw").json()
    updated = next(r for r in listed if r["id"] == raw_id)
    assert updated["status"] == "detecting"  # không đổi status, thành công
    assert updated["progress_current"] is None  # đã dọn tiến trình sau khi xong
    assert updated["error_message"] is None


def test_batch_tag_raw_video_channels_adds_without_replacing_existing(client, channel, channel2):
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_batch_tag_1")
        _seed_raw_video(db, [channel2["id"]], "raw_batch_tag_2")
    finally:
        db.close()
    resp = client.post("/asset-vault/raw/batch-tag-channels", json={"raw_ids": ["raw_batch_tag_1", "raw_batch_tag_2"], "channel_ids": [channel2["id"]]})
    assert resp.status_code == 200, resp.text
    results = {r["id"]: {c["id"] for c in r["channels"]} for r in resp.json()}
    # video 1 vốn chỉ có `channel` — sau batch-tag phải CÓ CẢ 2 (cộng thêm, không ghi đè)
    assert results["raw_batch_tag_1"] == {channel["id"], channel2["id"]}
    # video 2 vốn đã có sẵn channel2 — batch-tag lại channel2 không tạo trùng lặp
    assert results["raw_batch_tag_2"] == {channel2["id"]}


def test_batch_tag_raw_video_channels_rejects_empty_inputs(client, channel):
    resp = client.post("/asset-vault/raw/batch-tag-channels", json={"raw_ids": [], "channel_ids": [channel["id"]]})
    assert resp.status_code == 400
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_batch_tag_3")
    finally:
        db.close()
    resp = client.post("/asset-vault/raw/batch-tag-channels", json={"raw_ids": ["raw_batch_tag_3"], "channel_ids": []})
    assert resp.status_code == 400


def test_batch_tag_raw_video_channels_cascades_to_clips(client, channel, channel2):
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_batch_cascade")
        _seed_clip(db, [channel["id"]], "clip_batch_cascade", raw_video_id="raw_batch_cascade")
    finally:
        db.close()
    resp = client.post("/asset-vault/raw/batch-tag-channels", json={"raw_ids": ["raw_batch_cascade"], "channel_ids": [channel2["id"]]})
    assert resp.status_code == 200, resp.text

    resp = client.get("/asset-vault/clips?raw_video_id=raw_batch_cascade")
    clip = resp.json()[0]
    assert {c["id"] for c in clip["channels"]} == {channel["id"], channel2["id"]}  # cộng thêm, không mất tag cũ


def test_patch_clip_channels_replaces_own_tags_independent_of_raw_video(client, channel, channel2):
    """Sửa kênh Ở MỨC CLIP không đụng tới raw_video cha (khác `patch_raw_video_channels`)
    — đây là đường sửa lại tag cho clip đã mồ côi (raw_video cha đã bị xoá, không còn
    control kênh nào khác dùng được)."""
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_clip_retag")
        _seed_clip(db, [channel["id"]], "clip_retag_own", raw_video_id="raw_clip_retag")
    finally:
        db.close()
    resp = client.patch("/asset-vault/clips/clip_retag_own/channels", json={"channel_ids": [channel2["id"]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["channels"] == [{"id": channel2["id"], "name": channel2["name"]}]

    # raw_video cha KHÔNG bị đụng tới
    resp = client.get("/asset-vault/raw")
    raw = next(r for r in resp.json() if r["id"] == "raw_clip_retag")
    assert raw["channels"] == [{"id": channel["id"], "name": channel["name"]}]


def test_patch_clip_channels_rejects_empty_list(client, channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_retag_empty")
    finally:
        db.close()
    resp = client.patch("/asset-vault/clips/clip_retag_empty/channels", json={"channel_ids": []})
    assert resp.status_code == 400


def test_batch_tag_clip_channels_adds_without_replacing_existing(client, channel, channel2):
    """Bulk gán tag kênh cho NHIỀU clip đã chọn — yêu cầu mới của người dùng (2026-08-28),
    cộng thêm (union) chứ không ghi đè."""
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_bulk_tag_1")
        _seed_clip(db, [channel2["id"]], "clip_bulk_tag_2")
    finally:
        db.close()
    resp = client.post("/asset-vault/clips/batch-tag-channels", json={"clip_ids": ["clip_bulk_tag_1", "clip_bulk_tag_2"], "channel_ids": [channel2["id"]]})
    assert resp.status_code == 200, resp.text
    results = {c["clip_id"]: {ch["id"] for ch in c["channels"]} for c in resp.json()}
    assert results["clip_bulk_tag_1"] == {channel["id"], channel2["id"]}
    assert results["clip_bulk_tag_2"] == {channel2["id"]}


def test_batch_tag_clip_channels_rejects_empty_inputs(client, channel):
    resp = client.post("/asset-vault/clips/batch-tag-channels", json={"clip_ids": [], "channel_ids": [channel["id"]]})
    assert resp.status_code == 400
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_bulk_tag_3")
    finally:
        db.close()
    resp = client.post("/asset-vault/clips/batch-tag-channels", json={"clip_ids": ["clip_bulk_tag_3"], "channel_ids": []})
    assert resp.status_code == 400


def test_batch_delete_raw_videos_removes_files_and_rows(client, channel, tmp_path):
    db = SessionLocal()
    try:
        f1 = tmp_path / "a.mp4"
        f2 = tmp_path / "b.mp4"
        f1.write_bytes(b"fake")
        f2.write_bytes(b"fake")
        raw1 = _seed_raw_video(db, [channel["id"]], "raw_batch_del_1", file_path=str(f1))
        raw2 = _seed_raw_video(db, [channel["id"]], "raw_batch_del_2", file_path=str(f2))
    finally:
        db.close()
    resp = client.post("/asset-vault/raw/batch-delete", json={"raw_ids": ["raw_batch_del_1", "raw_batch_del_2"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 2
    assert not f1.exists() and not f2.exists()
    remaining = client.get("/asset-vault/raw").json()
    assert all(r["id"] not in ("raw_batch_del_1", "raw_batch_del_2") for r in remaining)


def test_batch_delete_raw_videos_rejects_empty_list(client):
    resp = client.post("/asset-vault/raw/batch-delete", json={"raw_ids": []})
    assert resp.status_code == 400


def test_list_clips_survives_orphaned_clip_after_raw_video_deleted(client, channel, tmp_path):
    """Bug thật #1 (2026-08-27, bắt được lúc verify UI thật qua CDP) — `delete_raw_video`
    CỐ Ý không cascade xoá `ProcessedClip` con (clip đã cắt dùng được độc lập), nên 1 clip
    có thể mồ côi (`raw_video_id` trỏ tới hàng đã xoá). `GET /asset-vault/clips` trước đây
    crash 500 (`AttributeError: 'NoneType' object has no attribute 'channels'`) vì
    `_channels_out` không xử lý `raw_video is None`.

    Bug thật #2 (2026-08-28, user tự phát hiện) — bản vá bug #1 (trả `channels: []` cho
    clip mồ côi) ĐÚNG là không crash nữa, nhưng ẨN 1 bug NẶNG hơn: kênh của clip TỪNG chỉ
    suy ra qua raw_video cha, nên xoá raw_video làm MẤT SẠCH thông tin kênh — không chỉ
    hiển thị rỗng, còn làm clip biến mất khỏi MỌI kết quả matching B-roll (xem
    `test_matching.py`/`matching.py::_clips_for_channel`). Fix: clip có tag kênh RIÊNG
    (`ProcessedClip.channels`, sao chép lúc cắt cảnh) — verify lại ĐÚNG hành vi MỚI: xoá
    raw_video KHÔNG còn làm mất kênh của clip con."""
    db = SessionLocal()
    try:
        f = tmp_path / "orphan_clip.mp4"
        f.write_bytes(b"fake")
        _seed_raw_video(db, [channel["id"]], "raw_to_delete")
        _seed_clip(db, [channel["id"]], "clip_orphan", storage_url=str(f), duration_sec=1.0, raw_video_id="raw_to_delete")
    finally:
        db.close()

    resp = client.delete("/asset-vault/raw/raw_to_delete")
    assert resp.status_code == 200

    resp = client.get("/asset-vault/clips")
    assert resp.status_code == 200, resp.text
    orphan = next(c for c in resp.json() if c["clip_id"] == "clip_orphan")
    assert orphan["channels"] == [{"id": channel["id"], "name": channel["name"]}]  # KHÔNG còn rỗng sau khi xoá raw_video cha

    # Vẫn lọc được đúng theo kênh sau khi raw_video cha đã mất — trước đây filter join qua
    # raw_video nên clip mồ côi biến mất khỏi MỌI kết quả lọc kênh.
    resp = client.get(f"/asset-vault/clips?channel_id={channel['id']}")
    assert resp.status_code == 200, resp.text
    assert any(c["clip_id"] == "clip_orphan" for c in resp.json())


# ---------------------------------------------------------------------------
# Tự phục hồi status kẹt (mục 132) — bug thật báo bởi người dùng: "Video đã cắt cảnh vẫn
# hiện đang cắt cảnh, đã gán nhãn nhưng vẫn hiện đang gán nhãn" — gốc rễ do BackgroundTasks
# không có try/except quanh lệnh gọi lõi, backend crash giữa task để lại status kẹt dù dữ
# liệu con (clip/caption) đã hoàn tất thật.
# ---------------------------------------------------------------------------
def test_reconcile_heals_stuck_tagging_status_when_all_clips_captioned(client, channel):
    """Case CONFIRMED thật trên dữ liệu production (raw_1789050452744: 36/36 clip đã có
    caption nhưng status vẫn "tagging") — mô phỏng lại bằng 2 clip đều đã caption."""
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_stuck_tagging")
        _seed_clip(db, [channel["id"]], "clip_stuck_1", caption="a river", raw_video_id="raw_stuck_tagging")
        _seed_clip(db, [channel["id"]], "clip_stuck_2", caption="a mountain", raw_video_id="raw_stuck_tagging")
    finally:
        db.close()

    listed = client.get("/asset-vault/raw").json()
    updated = next(r for r in listed if r["id"] == "raw_stuck_tagging")
    assert updated["status"] == "indexed"
    assert updated["error_message"] is None


def test_reconcile_heals_stuck_tagging_status_to_error_when_a_clip_failed(client, channel):
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_stuck_tagging_err")
        _seed_clip(db, [channel["id"]], "clip_stuck_err_1", caption="ok", raw_video_id="raw_stuck_tagging_err")
        clip2 = _seed_clip(db, [channel["id"]], "clip_stuck_err_2", raw_video_id="raw_stuck_tagging_err")
        clip2.caption_error = "vision provider timeout"
        db.commit()
    finally:
        db.close()

    listed = client.get("/asset-vault/raw").json()
    updated = next(r for r in listed if r["id"] == "raw_stuck_tagging_err")
    assert updated["status"] == "error"
    assert "clip_stuck_err_2" in updated["error_message"]


def test_reconcile_leaves_tagging_status_when_some_clips_still_uncaptioned(client, channel):
    """Task gắn nhãn ĐANG thật sự chạy dở (chưa crash) — không được vội suy "indexed"."""
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_tagging_in_progress")
        _seed_clip(db, [channel["id"]], "clip_pending_1", caption="done", raw_video_id="raw_tagging_in_progress")
        _seed_clip(db, [channel["id"]], "clip_pending_2", caption="", raw_video_id="raw_tagging_in_progress")
    finally:
        db.close()

    listed = client.get("/asset-vault/raw").json()
    updated = next(r for r in listed if r["id"] == "raw_tagging_in_progress")
    assert updated["status"] == "tagging"


def test_reconcile_heals_stuck_detecting_status_when_clips_already_exist(client, channel):
    """Cắt cảnh đã cắt xong (clip con đã tồn tại) nhưng crash trước khi kịp ghi "tagging"
    — `progress_*` đều None (không có task nào đang chạy dở) là tín hiệu phân biệt với
    task đang chạy thật."""
    db = SessionLocal()
    try:
        raw = _seed_raw_video(db, [channel["id"]], "raw_stuck_detecting")
        raw.status = "detecting"
        db.commit()
        _seed_clip(db, [channel["id"]], "clip_after_stuck_detect", raw_video_id="raw_stuck_detecting")
    finally:
        db.close()

    listed = client.get("/asset-vault/raw").json()
    updated = next(r for r in listed if r["id"] == "raw_stuck_detecting")
    assert updated["status"] == "tagging"


def test_reconcile_does_not_touch_detecting_status_with_no_clips_yet(client, channel):
    """7 video thật trên production ở đúng case này (mới upload, 0 clip) — ĐÂY LÀ trạng
    thái ban đầu đúng, KHÔNG phải bug, không được tự đổi status."""
    db = SessionLocal()
    try:
        raw = _seed_raw_video(db, [channel["id"]], "raw_fresh_upload")
        raw.status = "detecting"
        db.commit()
    finally:
        db.close()

    listed = client.get("/asset-vault/raw").json()
    updated = next(r for r in listed if r["id"] == "raw_fresh_upload")
    assert updated["status"] == "detecting"


def test_reconcile_does_not_touch_detecting_status_while_task_actively_running(client, channel):
    """`progress_*` đã set (task thật đang chạy dở) — dù ĐÃ có vài clip cắt xong, KHÔNG
    được vội chuyển "tagging" khi task còn đang cắt tiếp các clip còn lại."""
    db = SessionLocal()
    try:
        raw = _seed_raw_video(db, [channel["id"]], "raw_detecting_active")
        raw.status = "detecting"
        raw.progress_current = 2
        raw.progress_total = 5
        raw.progress_label = "Đang cắt cảnh 2/5"
        db.commit()
        _seed_clip(db, [channel["id"]], "clip_mid_detect", raw_video_id="raw_detecting_active")
    finally:
        db.close()

    listed = client.get("/asset-vault/raw").json()
    updated = next(r for r in listed if r["id"] == "raw_detecting_active")
    assert updated["status"] == "detecting"


def test_reconcile_also_applies_via_clips_list_endpoint(client, channel):
    """`GET /asset-vault/clips` hiện `raw_video_status` (bảng "Clip đã cắt") — phải thấy
    status ĐÃ suy lại, không chỉ `GET /asset-vault/raw` (bảng "Raw Library")."""
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_stuck_via_clips")
        _seed_clip(db, [channel["id"]], "clip_via_clips_1", caption="a", raw_video_id="raw_stuck_via_clips")
    finally:
        db.close()

    resp = client.get("/asset-vault/clips?raw_video_id=raw_stuck_via_clips")
    assert resp.status_code == 200, resp.text
    clip = resp.json()[0]
    assert clip["raw_video_status"] == "indexed"


def test_matching_clips_for_channel_finds_clip_after_raw_video_deleted(client, channel):
    """Hệ quả NẶNG nhất của bug #98 — `matching.py::_clips_for_channel` TỪNG INNER JOIN
    qua `RawVideo`, nên xoá raw_video cha làm clip biến mất khỏi MỌI kết quả matching
    B-roll (Render Studio "Video từ Kho") dù file/caption/embedding vẫn còn nguyên. Verify
    trực tiếp ở tầng matching (không chỉ qua router `/clips`) — đây là nơi Render Studio
    thật sự gọi tới lúc gợi ý clip cho 1 shot."""
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_for_matching")
        _seed_clip(db, [channel["id"]], "clip_for_matching", active=True, raw_video_id="raw_for_matching")
    finally:
        db.close()

    resp = client.delete("/asset-vault/raw/raw_for_matching")
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        found = matching._clips_for_channel(db, channel["id"]).all()
        assert [c.clip_id for c in found] == ["clip_for_matching"]
    finally:
        db.close()


def test_patch_processed_clip_updates_rights_and_tags(client, channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_patch_1", caption="old caption")
    finally:
        db.close()
    resp = client.patch(
        "/asset-vault/clips/clip_patch_1",
        json={"caption": "new caption", "tags": ["a", "b"], "rights_status": "licensed_verified", "rights_note": "bought from stock site"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["caption"] == "new caption"
    assert body["tags"] == ["a", "b"]
    assert body["rights_status"] == "licensed_verified"


def test_patch_processed_clip_rejects_invalid_rights_status(client, channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_patch_invalid")
    finally:
        db.close()
    resp = client.patch("/asset-vault/clips/clip_patch_invalid", json={"rights_status": "not-a-real-status"})
    assert resp.status_code == 400


def test_batch_patch_processed_clips_updates_multiple(client, channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_batch_1")
        _seed_clip(db, [channel["id"]], "clip_batch_2")
    finally:
        db.close()
    resp = client.post(
        "/asset-vault/clips/batch",
        json={"clip_ids": ["clip_batch_1", "clip_batch_2"], "rights_status": "public_domain", "add_tag": "batch-tagged"},
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()
    assert len(results) == 2
    assert all(c["rights_status"] == "public_domain" for c in results)
    assert all("batch-tagged" in c["tags"] for c in results)


def test_caption_batch_endpoint_rejects_empty_list(client):
    resp = client.post("/asset-vault/clips/caption-batch", json={"clip_ids": []})
    assert resp.status_code == 400


def test_caption_batch_endpoint_rejects_unknown_clip_id(client, channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_caption_batch_known")
    finally:
        db.close()
    resp = client.post("/asset-vault/clips/caption-batch", json={"clip_ids": ["clip_caption_batch_known", "khong-ton-tai"]})
    assert resp.status_code == 400


@respx.mock
def test_caption_batch_endpoint_captions_clips_across_different_raw_videos(client, channel, channel2):
    """`POST .../caption-batch` — clip lựa chọn tự do có thể trải NHIỀU raw_video khác
    nhau (khác kênh nhau luôn) — verify cả 2 đều được gắn nhãn qua ĐÚNG 1 lượt gọi bulk,
    TestClient chạy BackgroundTasks đồng bộ (chặn tới khi xong) trước khi trả response nên
    assert được NGAY sau `client.post`, không cần poll."""
    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": '{"caption": "batch caption", "tags": ["a"], "mood_tone": "calm"}'}}]})
    )
    # Dimension PHẢI khớp các test khác trong cùng session (Chroma collection TOÀN CỤC
    # dùng chung 1 `client` session-scoped — trộn dimension khác nhau trong CÙNG collection
    # bị Chroma từ chối thật: "Collection expecting embedding with dimension of 2, got 1").
    respx.post("http://127.0.0.1:8080/v1/embeddings").mock(return_value=Response(200, json={"data": [{"embedding": [0.1, 0.2]}]}))

    db = SessionLocal()
    added_config_ids: list[int] = []
    try:
        from app.models import ProviderConfig

        vision_cfg = ProviderConfig(task="vision", provider_name="localai_vision", display_name="Vision test", connection_type="local_endpoint", endpoint_url="http://127.0.0.1:8080", model_name="moondream2", is_default=True, enabled=True)
        embedding_cfg = ProviderConfig(task="embedding", provider_name="localai_embedding", display_name="Embedding test", connection_type="local_endpoint", endpoint_url="http://127.0.0.1:8080", model_name="all-MiniLM-L6-v2", is_default=True, enabled=True)
        db.add(vision_cfg)
        db.add(embedding_cfg)
        db.commit()
        added_config_ids = [vision_cfg.id, embedding_cfg.id]

        clip_a = _seed_clip(db, [channel["id"]], "clip_caption_batch_a", storage_url=None)
        clip_b = _seed_clip(db, [channel2["id"]], "clip_caption_batch_b", storage_url=None)
        # `_seed_clip` không tạo file thật lẫn keyframe — cần ảnh thật để `_extract_keyframe` chạy ffmpeg.
    finally:
        db.close()

    # Storage_url mặc định của _seed_clip trỏ file không tồn tại — dựng lại clip với video thật.
    ffmpeg = _ffmpeg()
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        clip_path = Path(d) / "clip.mp4"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=2", "-pix_fmt", "yuv420p", str(clip_path)], capture_output=True, check=True, text=True)
        db = SessionLocal()
        try:
            for cid in ("clip_caption_batch_a", "clip_caption_batch_b"):
                c = db.query(ProcessedClip).filter(ProcessedClip.clip_id == cid).first()
                c.storage_url = str(clip_path)
                c.duration_sec = 2.0
            db.commit()
        finally:
            db.close()

        resp = client.post("/asset-vault/clips/caption-batch", json={"clip_ids": ["clip_caption_batch_a", "clip_caption_batch_b"]})
        assert resp.status_code == 200, resp.text

    db = SessionLocal()
    try:
        clip_a = db.query(ProcessedClip).filter(ProcessedClip.clip_id == "clip_caption_batch_a").first()
        clip_b = db.query(ProcessedClip).filter(ProcessedClip.clip_id == "clip_caption_batch_b").first()
        assert clip_a.caption == "batch caption" and clip_a.caption_error is None
        assert clip_b.caption == "batch caption" and clip_b.caption_error is None
        assert clip_a.raw_video_id != clip_b.raw_video_id
    finally:
        from app.models import ProviderConfig

        if added_config_ids:
            db.query(ProviderConfig).filter(ProviderConfig.id.in_(added_config_ids)).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_list_clips_filters_unlabeled(client, channel):
    db = SessionLocal()
    try:
        _seed_clip(db, [channel["id"]], "clip_unlabeled_1", caption="")
        _seed_clip(db, [channel["id"]], "clip_labeled_1", caption="already captioned")
    finally:
        db.close()
    resp = client.get("/asset-vault/clips", params={"unlabeled": "true"})
    assert resp.status_code == 200, resp.text
    ids = {c["clip_id"] for c in resp.json()}
    assert "clip_unlabeled_1" in ids
    assert "clip_labeled_1" not in ids


def test_list_clips_filters_by_raw_status(client, channel):
    db = SessionLocal()
    try:
        raw_ready = _seed_raw_video(db, [channel["id"]], "raw_status_indexed")
        raw_ready.status = "indexed"
        raw_error = _seed_raw_video(db, [channel["id"]], "raw_status_error")
        raw_error.status = "error"
        db.commit()
        _seed_clip(db, [channel["id"]], "clip_status_indexed", raw_video_id="raw_status_indexed")
        _seed_clip(db, [channel["id"]], "clip_status_error", raw_video_id="raw_status_error")
    finally:
        db.close()
    resp = client.get("/asset-vault/clips", params={"raw_status": "error"})
    assert resp.status_code == 200, resp.text
    ids = {c["clip_id"] for c in resp.json()}
    assert "clip_status_error" in ids
    assert "clip_status_indexed" not in ids


def test_list_clips_includes_raw_video_name_and_status(client, channel):
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel["id"]], "raw_named", file_path="/fake/raw.mp4")
        raw = db.query(RawVideo).filter(RawVideo.id == "raw_named").first()
        raw.import_note = "Nguồn: kho tư liệu lịch sử"
        db.commit()
        _seed_clip(db, [channel["id"]], "clip_named", raw_video_id="raw_named")
    finally:
        db.close()
    resp = client.get("/asset-vault/clips", params={"raw_video_id": "raw_named"})
    assert resp.status_code == 200, resp.text
    clip = resp.json()[0]
    assert clip["raw_video_name"] == "Nguồn: kho tư liệu lịch sử"
    assert clip["raw_video_status"] == "tagging"


def test_delete_clip_endpoint(client, channel, tmp_path):
    db = SessionLocal()
    try:
        f = tmp_path / "clip_to_delete.mp4"
        f.write_bytes(b"fake")
        _seed_clip(db, [channel["id"]], "clip_delete_http", storage_url=str(f))
    finally:
        db.close()
    resp = client.delete("/asset-vault/clips/clip_delete_http")
    assert resp.status_code == 200
    resp2 = client.get("/asset-vault/clips", params={"channel_id": channel["id"]})
    assert all(c["clip_id"] != "clip_delete_http" for c in resp2.json())


# ---------------------------------------------------------------------------
# Video Slot (render.py) — vault-candidates + assign-vault-clip
# ---------------------------------------------------------------------------
def _import_one_shot_csv(client, pid: str, visual_fx: str = "a river in the forest") -> str:
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:05", "Video", visual_fx, "", "Loi thoai."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]
    return shot_id


def test_vault_candidates_uses_keyword_fallback_without_embedding_provider(client, project_with_brief):
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]
    shot_id = _import_one_shot_csv(client, pid, visual_fx="a river flowing through a green forest")

    db = SessionLocal()
    try:
        _seed_clip(db, [channel_id], "clip_candidate_1", caption="river forest footage", tags=["river", "forest"])
    finally:
        db.close()

    resp = client.get(f"/projects/{pid}/render/shots/{shot_id}/vault-candidates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["used_semantic"] is False
    cand = next(c for c in body["candidates"] if c["clip_id"] == "clip_candidate_1")
    # from_visual_studio=False cho clip B-roll thật (raw_video KHÔNG phải hàng ảo đại
    # diện project) — mới (2026-09-13), xem test riêng trong test_visual_studio_vault.py
    # cho trường hợp ngược lại (asset lưu từ Visual Studio).
    assert cand["from_visual_studio"] is False
    assert cand["tags"] == ["river", "forest"]
    # match_score cho keyword fallback — mới (2026-09-13, theo yêu cầu người dùng "thêm
    # matching score") — trước đây LUÔN null cho nhánh keyword, giờ có điểm chuẩn hoá 0-1.
    assert cand["match_score"] is not None and 0 < cand["match_score"] <= 1


def test_vault_candidates_sorted_by_match_score_descending(client, project_with_brief):
    """Theo yêu cầu người dùng — Vault Clip Picker phải xếp candidate theo match score
    GIẢM DẦN. `clip_best` khớp cả 5 từ mô tả, `clip_partial` chỉ khớp 2/5 — xác nhận thứ
    tự VÀ điểm số đúng, không chỉ tình cờ đúng nhờ thứ tự insert."""
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]
    shot_id = _import_one_shot_csv(client, pid, visual_fx="a calm river flowing through green forest")

    db = SessionLocal()
    try:
        # Chèn "clip_partial" TRƯỚC "clip_best" — nếu code chỉ dựa vào thứ tự insert/query
        # mặc định (không sort tường minh theo score) thì test này sẽ fail.
        _seed_clip(db, [channel_id], "clip_partial", caption="a busy river street", tags=[])
        _seed_clip(db, [channel_id], "clip_best", caption="a calm river flowing through green forest", tags=[])
    finally:
        db.close()

    resp = client.get(f"/projects/{pid}/render/shots/{shot_id}/vault-candidates")
    assert resp.status_code == 200, resp.text
    candidates = resp.json()["candidates"]
    ids = [c["clip_id"] for c in candidates]
    assert ids.index("clip_best") < ids.index("clip_partial")
    scores = {c["clip_id"]: c["match_score"] for c in candidates}
    assert scores["clip_best"] > scores["clip_partial"]
    assert all(a["match_score"] >= b["match_score"] for a, b in zip(candidates, candidates[1:]) if a["match_score"] is not None and b["match_score"] is not None)


def test_vault_candidates_requires_shot_description(client, project_with_brief):
    pid = project_with_brief["id"]
    shot_id = _import_one_shot_csv(client, pid, visual_fx="")
    resp = client.get(f"/projects/{pid}/render/shots/{shot_id}/vault-candidates")
    assert resp.status_code == 400


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assign_vault_clip_requires_video_visual_type(client, project_with_brief, tmp_path):
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:05", "Image", "canh tinh", "", "Loi thoai."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    db = SessionLocal()
    try:
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"fake")
        _seed_clip(db, [channel_id], "clip_wrong_type", storage_url=str(f))
    finally:
        db.close()

    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/assign-vault-clip", json={"clip_id": "clip_wrong_type"})
    assert resp.status_code == 400


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_assign_vault_clip_copies_file_and_updates_render_state(client, project_with_brief, tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]
    shot_id = _import_one_shot_csv(client, pid)

    clip_path = tmp_path / "clip.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=yellow:s=320x240:d=3", "-pix_fmt", "yuv420p", str(clip_path)], capture_output=True, check=True, text=True)
    db = SessionLocal()
    try:
        _seed_clip(db, [channel_id], "clip_assign_1", storage_url=str(clip_path), duration_sec=3.0)
    finally:
        db.close()

    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/assign-vault-clip", json={"clip_id": "clip_assign_1"})
    assert resp.status_code == 200, resp.text
    state = resp.json()
    status = next(s for s in state["shots"] if s["shot_id"] == shot_id)
    assert status["visual_provider"] == "asset_vault"
    assert status["visual_status"] == "ready"
    assert status["linked_clip_id"] == "clip_assign_1"
    assert status["approved"] is False
    from pathlib import Path

    assert Path(status["visual_asset_path"]).exists()

    db = SessionLocal()
    try:
        clip = db.query(ProcessedClip).filter(ProcessedClip.clip_id == "clip_assign_1").first()
        assert clip.usage_count == 1
        assert clip.last_used_at is not None
    finally:
        db.close()


def test_assign_vault_clip_404_for_clip_in_other_channel(client, project_with_brief, channel2):
    """Clip gắn với 1 kênh KHÁC (fixture `channel2`, id khác biệt thật — không dùng chuỗi
    giả để tránh phụ thuộc ngầm vào việc SQLite không ép FK) phải KHÔNG gán được vào shot
    của project đang test — 404."""
    pid = project_with_brief["id"]
    shot_id = _import_one_shot_csv(client, pid)
    db = SessionLocal()
    try:
        _seed_clip(db, [channel2["id"]], "clip_other_channel")
    finally:
        db.close()
    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/assign-vault-clip", json={"clip_id": "clip_other_channel"})
    assert resp.status_code == 404


def test_assign_vault_clip_works_for_clip_whose_raw_video_was_deleted(client, project_with_brief, tmp_path):
    """Bug thật (2026-09-02) — `assign_vault_clip` TỪNG lọc kênh qua JOIN `raw_video_
    channel` (kênh của raw_video CHA) thay vì tag kênh RIÊNG của clip (mục 98) — clip mồ
    côi (raw_video cha đã bị xoá, xem mục 98) không còn hàng `raw_video` nào để JOIN tới,
    nên KHÔNG BAO GIỜ gán được nữa dù vẫn hiện đúng trong danh sách gợi ý matching. Verify
    lại đúng hành vi MỚI: xoá raw_video cha KHÔNG làm mất khả năng gán clip vào shot."""
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]
    shot_id = _import_one_shot_csv(client, pid)

    clip_path = tmp_path / "orphan_clip.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=cyan:s=320x240:d=2", "-pix_fmt", "yuv420p", str(clip_path)], capture_output=True, check=True, text=True)
    db = SessionLocal()
    try:
        _seed_raw_video(db, [channel_id], "raw_for_orphan_assign")
        _seed_clip(db, [channel_id], "clip_orphan_assign", storage_url=str(clip_path), duration_sec=2.0, raw_video_id="raw_for_orphan_assign")
    finally:
        db.close()

    del_resp = client.delete("/asset-vault/raw/raw_for_orphan_assign")
    assert del_resp.status_code == 200

    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/assign-vault-clip", json={"clip_id": "clip_orphan_assign"})
    assert resp.status_code == 200, resp.text
    status = next(s for s in resp.json()["shots"] if s["shot_id"] == shot_id)
    assert status["linked_clip_id"] == "clip_orphan_assign"


# ---------------------------------------------------------------------------
# Guardrail rights warning (routers/guardrail.py::_check_rights_warnings)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_guardrail_check_warns_on_unverified_vault_clip(client, project_with_brief):
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]
    shot_id = _import_one_shot_csv(client, pid)

    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        clip_path = Path(d) / "clip.mp4"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=purple:s=320x240:d=2", "-pix_fmt", "yuv420p", str(clip_path)], capture_output=True, check=True, text=True)
        db = SessionLocal()
        try:
            _seed_clip(db, [channel_id], "clip_rights_unverified", storage_url=str(clip_path), duration_sec=2.0, rights_status="unverified")
        finally:
            db.close()
        resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/assign-vault-clip", json={"clip_id": "clip_rights_unverified"})
        assert resp.status_code == 200, resp.text

    resp = client.post(f"/projects/{pid}/guardrail/check")
    assert resp.status_code == 200, resp.text
    warnings = resp.json()["warnings"]
    rights_warnings = [w for w in warnings if w["type"] == "rights"]
    assert len(rights_warnings) == 1
    assert shot_id in rights_warnings[0]["message"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_guardrail_check_no_rights_warning_when_verified(client, project_with_brief):
    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]
    shot_id = _import_one_shot_csv(client, pid)

    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        clip_path = Path(d) / "clip.mp4"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=orange:s=320x240:d=2", "-pix_fmt", "yuv420p", str(clip_path)], capture_output=True, check=True, text=True)
        db = SessionLocal()
        try:
            _seed_clip(db, [channel_id], "clip_rights_verified", storage_url=str(clip_path), duration_sec=2.0, rights_status="licensed_verified")
        finally:
            db.close()
        resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/assign-vault-clip", json={"clip_id": "clip_rights_verified"})
        assert resp.status_code == 200, resp.text

    resp = client.post(f"/projects/{pid}/guardrail/check")
    assert resp.status_code == 200, resp.text
    rights_warnings = [w for w in resp.json()["warnings"] if w["type"] == "rights"]
    assert rights_warnings == []
