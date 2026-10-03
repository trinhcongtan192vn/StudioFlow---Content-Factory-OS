"""Giọng đọc đa ngôn ngữ cho thị trường nước ngoài (2026-09-04) — Script Studio cho phép
sinh giọng đọc/tải srt+mp3 cho 6 ngôn ngữ (vi/en/de/pt_br/es/fr), văn bản dịch sẵn đọc từ
`ScriptBodyItem.audio_by_lang` (nhập qua file — xem test_script_import.py cho phần parse
cột VO (XX)). Ngôn ngữ CHÍNH của kênh (`BrandProfile.primary_language`) tiếp tục dùng
NGUYÊN field `narration_*`/`audio` gốc — 0 thay đổi hành vi render/timestamp/SRT hiện có,
test ở đây tập trung vào phần MỞ RỘNG (ngôn ngữ khác + endpoint/engine mới)."""
import io

import pytest

MULTILANG_HEADER = ["Mã", "Thời lượng", "Loại Visual", "Visual/FX", "Audio/SFX", "VO (VI)", "VO (EN)", "VO (DE)"]


def _csv_bytes(rows: list[list[str]]) -> bytes:
    lines = [",".join(f'"{c}"' for c in row) for row in rows]
    return ("\n".join(lines)).encode("utf-8")


class _FakeTTSProvider:
    provider_name = "omnivoice"

    def __init__(self, text_to_bytes=None):
        self.calls: list[dict] = []
        self._text_to_bytes = text_to_bytes or (lambda text: f"AUDIO:{text}".encode("utf-8"))

    def synthesize(self, text, *, emotion="", reference_audio=None):
        self.calls.append({"text": text, "emotion": emotion, "reference_audio": reference_audio})
        return self._text_to_bytes(text)


@pytest.fixture()
def multilang_project(client, channel):
    """Kênh + project đã import script 2 block, đủ VO (VI)/(EN)/(DE) cho block đầu,
    THIẾU (DE) ở block 2 (kiểm tra rollout dần từng ngôn ngữ) — primary_language mặc
    định vẫn "vi" (không đổi) trừ khi test cụ thể tự đổi."""
    proj = client.post(f"/channels/{channel['id']}/projects", json={"title": "Multilang"}).json()
    pid = proj["id"]
    csv_bytes = _csv_bytes([
        MULTILANG_HEADER,
        ["B01", "0:00–0:04", "Image", "Canh 1", "", "Xin chào các bạn, hôm nay ta nói về lịch sử.", "Hello everyone, today we discuss history.", "Hallo zusammen, heute sprechen wir über Geschichte."],
        ["B02", "0:04–0:08", "Image", "Canh 2", "", "Đây là block thứ hai của kịch bản.", "This is the second block of the script.", ""],
    ])
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shots = client.post(f"/projects/{pid}/visual/generate").json()["shots"]
    return {"channel_id": channel["id"], "project_id": pid, "shot_ids": [s["shot_id"] for s in shots]}


# ---------------------------------------------------------------------------
# engine.generate_narration_translation — unit-level qua DB thật, TTS provider giả
# ---------------------------------------------------------------------------
def test_generate_narration_translation_ready_when_no_translated_text(multilang_project):
    """Shot không có `audio_by_lang["fr"]` (ngôn ngữ chưa dịch tới) phải coi là READY
    (bỏ qua, không lỗi) — giống hệt nguyên tắc `generate_narration_asset` cho beat rỗng."""
    from app.config import project_dir
    from app.db import SessionLocal
    from app.models import Project
    from app.render import engine
    from app.render.schemas import RenderState, ShotRenderStatus

    pid = multilang_project["project_id"]
    pdir = project_dir(multilang_project["channel_id"], pid)
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        beat = {"audio_by_lang": {"vi": "..."}, "direction": ""}
        status = ShotRenderStatus(shot_id=multilang_project["shot_ids"][0])
        engine.generate_narration_translation(db, p, pdir, beat, status, "fr", RenderState(project_id=pid))
    finally:
        db.close()
    assert status.narration_translations["fr"].narration_status == "ready"
    assert status.narration_translations["fr"].narration_asset_path is None


def test_generate_narration_translation_synthesizes_from_audio_by_lang(multilang_project, monkeypatch):
    from app.config import project_dir
    from app.db import SessionLocal
    from app.models import Project
    from app.render import engine
    from app.render.schemas import RenderState, ShotRenderStatus

    fake = _FakeTTSProvider()
    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [fake])

    pid = multilang_project["project_id"]
    pdir = project_dir(multilang_project["channel_id"], pid)
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        beat = {"audio_by_lang": {"en": "Hello everyone."}, "direction": ""}
        status = ShotRenderStatus(shot_id=multilang_project["shot_ids"][0])
        engine.generate_narration_translation(db, p, pdir, beat, status, "en", RenderState(project_id=pid))
    finally:
        db.close()

    entry = status.narration_translations["en"]
    assert entry.narration_status == "ready", entry.narration_error
    assert entry.narration_asset_path
    assert entry.narration_asset_path.endswith(f"{status.shot_id}_en.wav") or entry.narration_asset_path.endswith(f"{status.shot_id}_en.mp3")
    assert fake.calls[0]["text"] == "Hello everyone."


def test_generate_narration_translation_prioritizes_omnivoice_when_voice_sample_configured(multilang_project, monkeypatch, tmp_path):
    """Bug thật phát hiện lúc tự rà soát (2026-09-04) — chain provider mặc định có thể
    KHÔNG phải OmniVoice (VD ElevenLabs mặc định, OmniVoice chỉ là fallback thứ 2+) —
    provider không hỗ trợ cloning nhận `reference_audio` rồi ÂM THẦM bỏ qua, khiến mẫu
    giọng vừa upload KHÔNG có tác dụng gì nếu cứ theo đúng thứ tự chain. OmniVoice phải
    được đưa lên ĐẦU bất kể thứ tự cấu hình, MIỄN LÀ có mẫu giọng cho ngôn ngữ này."""
    from app.config import project_dir
    from app.db import SessionLocal
    from app.filestore import write_json
    from app.models import Project
    from app.render import engine
    from app.render.schemas import RenderState, ShotRenderStatus

    elevenlabs = _FakeTTSProvider()
    elevenlabs.provider_name = "elevenlabs"
    omnivoice = _FakeTTSProvider()
    omnivoice.provider_name = "omnivoice"
    # Chain THẬT: ElevenLabs (mặc định) TRƯỚC OmniVoice (fallback) — mô phỏng đúng cấu
    # hình phổ biến (provider cloud làm mặc định, local làm dự phòng).
    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [elevenlabs, omnivoice])

    pid = multilang_project["project_id"]
    channel_id = multilang_project["channel_id"]
    pdir = project_dir(channel_id, pid)

    # Cấu hình mẫu giọng tiếng Anh cho kênh — set thẳng vào brandprofile.json trên đĩa
    # (bỏ qua endpoint upload — chỉ cần file tồn tại để `_read_voice_clone_ref_for_lang`
    # đọc được).
    sample_path = tmp_path / "en_sample.wav"
    sample_path.write_bytes(b"RIFF-fake-en-sample")
    from app.config import channel_dir
    from app.filestore import read_json

    profile = read_json(channel_dir(channel_id) / "brandprofile.json")
    profile["voice_clone_ref_paths"] = {"en": str(sample_path)}
    write_json(channel_dir(channel_id) / "brandprofile.json", profile)

    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        beat = {"audio_by_lang": {"en": "Hello everyone."}, "direction": ""}
        status = ShotRenderStatus(shot_id=multilang_project["shot_ids"][0])
        engine.generate_narration_translation(db, p, pdir, beat, status, "en", RenderState(project_id=pid))
    finally:
        db.close()

    assert status.narration_translations["en"].narration_status == "ready"
    assert status.narration_translations["en"].narration_provider == "omnivoice"
    assert not elevenlabs.calls  # KHÔNG được thử ElevenLabs trước — OmniVoice phải đứng đầu
    assert omnivoice.calls[0]["reference_audio"] == b"RIFF-fake-en-sample"


def test_generate_narration_translation_keeps_configured_order_when_no_voice_sample(multilang_project, monkeypatch):
    """KHÔNG có mẫu giọng cho ngôn ngữ này — giữ NGUYÊN thứ tự chain đã cấu hình (không
    ép OmniVoice lên đầu vô lý khi chẳng có gì để clone)."""
    from app.config import project_dir
    from app.db import SessionLocal
    from app.models import Project
    from app.render import engine
    from app.render.schemas import RenderState, ShotRenderStatus

    elevenlabs = _FakeTTSProvider()
    elevenlabs.provider_name = "elevenlabs"
    omnivoice = _FakeTTSProvider()
    omnivoice.provider_name = "omnivoice"
    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [elevenlabs, omnivoice])

    pid = multilang_project["project_id"]
    pdir = project_dir(multilang_project["channel_id"], pid)
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        beat = {"audio_by_lang": {"en": "Hello everyone."}, "direction": ""}
        status = ShotRenderStatus(shot_id=multilang_project["shot_ids"][0])
        engine.generate_narration_translation(db, p, pdir, beat, status, "en", RenderState(project_id=pid))
    finally:
        db.close()

    assert status.narration_translations["en"].narration_provider == "elevenlabs"


def test_generate_narration_translation_does_not_touch_primary_fields(multilang_project, monkeypatch):
    """Sinh giọng đọc ngôn ngữ KHÁC không được đụng field `narration_*` gốc (ngôn ngữ
    chính) — 0 rủi ro hồi quy cho luồng render/timestamp hiện có."""
    from app.config import project_dir
    from app.db import SessionLocal
    from app.models import Project
    from app.render import engine
    from app.render.schemas import RenderState, ShotRenderStatus

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeTTSProvider()])
    pid = multilang_project["project_id"]
    pdir = project_dir(multilang_project["channel_id"], pid)
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        beat = {"audio_by_lang": {"de": "Hallo."}, "audio": "Xin chào.", "direction": ""}
        status = ShotRenderStatus(shot_id=multilang_project["shot_ids"][0])
        engine.generate_narration_translation(db, p, pdir, beat, status, "de", RenderState(project_id=pid))
    finally:
        db.close()
    assert status.narration_status == "pending"
    assert status.narration_asset_path is None


def test_read_voice_clone_ref_for_lang_uses_per_language_map(tmp_path):
    from app.render.engine import _read_voice_clone_ref_for_lang

    sample = tmp_path / "de_sample.wav"
    sample.write_bytes(b"RIFF-fake-de")
    brand = {"primary_language": "vi", "voice_clone_ref_paths": {"de": str(sample)}}
    assert _read_voice_clone_ref_for_lang(brand, "de") == b"RIFF-fake-de"
    assert _read_voice_clone_ref_for_lang(brand, "fr") is None  # chưa cấu hình mẫu tiếng Pháp


def test_read_voice_clone_ref_for_lang_backward_compat_single_path(tmp_path):
    """Dữ liệu CŨ chỉ có `voice_clone_ref_path` đơn (trước khi có khái niệm đa ngôn ngữ)
    — coi là mẫu của `primary_language`."""
    from app.render.engine import _read_voice_clone_ref_for_lang

    sample = tmp_path / "old_sample.wav"
    sample.write_bytes(b"RIFF-fake-old")
    brand = {"primary_language": "vi", "voice_clone_ref_path": str(sample)}
    assert _read_voice_clone_ref_for_lang(brand, "vi") == b"RIFF-fake-old"
    assert _read_voice_clone_ref_for_lang(brand, "en") is None


# ---------------------------------------------------------------------------
# Router — batch/single generate, asset serving, download, SRT
# ---------------------------------------------------------------------------
def test_start_narration_translation_batch_rejects_invalid_lang(client, multilang_project):
    resp = client.post(f"/projects/{multilang_project['project_id']}/render/narration-translations/xx/start")
    assert resp.status_code == 400


def test_start_narration_translation_batch_generates_for_all_translated_shots(client, multilang_project, monkeypatch):
    from app.render import engine

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeTTSProvider()])
    pid = multilang_project["project_id"]
    resp = client.post(f"/projects/{pid}/render/narration-translations/en/start")
    assert resp.status_code == 200

    status = client.get(f"/projects/{pid}/render/status").json()
    translations = [s["narration_translations"].get("en") for s in status["shots"]]
    assert all(t is not None and t["narration_status"] == "ready" for t in translations)
    # Ngôn ngữ chính (vi) không hề bị đụng tới bởi batch tiếng Anh.
    assert all(s["narration_status"] == "pending" for s in status["shots"])


def test_start_narration_translation_batch_skips_shot_without_translation(client, multilang_project, monkeypatch):
    """B02 KHÔNG có VO (DE) — batch tiếng Đức phải coi B02 là 'ready' (bỏ qua), không lỗi."""
    from app.render import engine

    fake = _FakeTTSProvider()
    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [fake])
    pid = multilang_project["project_id"]
    resp = client.post(f"/projects/{pid}/render/narration-translations/de/start")
    assert resp.status_code == 200

    status = client.get(f"/projects/{pid}/render/status").json()
    translations = {s["shot_id"]: s["narration_translations"].get("de") for s in status["shots"]}
    assert translations[multilang_project["shot_ids"][0]]["narration_status"] == "ready"
    assert translations[multilang_project["shot_ids"][0]]["narration_asset_path"]
    assert translations[multilang_project["shot_ids"][1]]["narration_status"] == "ready"
    assert translations[multilang_project["shot_ids"][1]]["narration_asset_path"] is None
    assert len(fake.calls) == 1  # chỉ B01 thật sự gọi TTS


def test_regenerate_single_narration_translation(client, multilang_project, monkeypatch):
    from app.render import engine

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeTTSProvider()])
    pid = multilang_project["project_id"]
    shot_id = multilang_project["shot_ids"][0]
    # `regenerate-narration-translation` (cùng `regenerate_narration` gốc) yêu cầu shot
    # đã có entry trong render.json — `render/start` seed entry đó (cùng luồng thật:
    # Visual Studio luôn sinh asset toàn bộ block trước khi có nút sinh lại từng shot).
    client.post(f"/projects/{pid}/render/start", params={"kind": "narration"})
    resp = client.post(f"/projects/{pid}/render/shots/{shot_id}/regenerate-narration-translation/en")
    assert resp.status_code == 200

    status = client.get(f"/projects/{pid}/render/status").json()
    shot_status = next(s for s in status["shots"] if s["shot_id"] == shot_id)
    assert shot_status["narration_translations"]["en"]["narration_status"] == "ready"


def test_get_narration_translation_asset_404_before_generated(client, multilang_project):
    pid = multilang_project["project_id"]
    shot_id = multilang_project["shot_ids"][0]
    resp = client.get(f"/projects/{pid}/render/shots/{shot_id}/asset/narration/en")
    assert resp.status_code == 404


def test_get_narration_translation_asset_serves_file_after_generated(client, multilang_project, monkeypatch):
    from app.render import engine

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeTTSProvider()])
    pid = multilang_project["project_id"]
    shot_id = multilang_project["shot_ids"][0]
    client.post(f"/projects/{pid}/render/start", params={"kind": "narration"})
    client.post(f"/projects/{pid}/render/shots/{shot_id}/regenerate-narration-translation/en")
    resp = client.get(f"/projects/{pid}/render/shots/{shot_id}/asset/narration/en")
    assert resp.status_code == 200
    assert resp.content.startswith(b"AUDIO:")


def test_download_narration_full_lang_reports_missing_shots(client, multilang_project, monkeypatch):
    from app.render import engine

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeTTSProvider()])
    pid = multilang_project["project_id"]
    # Chỉ sinh cho 1 shot, chưa sinh shot còn lại — endpoint phải báo rõ còn thiếu.
    shot_id = multilang_project["shot_ids"][0]
    client.post(f"/projects/{pid}/render/shots/{shot_id}/regenerate-narration-translation/en")
    resp = client.get(f"/projects/{pid}/render/narration-download/en")
    assert resp.status_code == 400
    assert "chưa có giọng đọc" in resp.json()["detail"].lower()


def test_download_narration_full_lang_succeeds_when_all_translated_shots_ready(client, multilang_project, monkeypatch):
    import shutil

    if not shutil.which("ffmpeg"):
        pytest.skip("cần ffmpeg thật trên PATH")
    from app.render import engine

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeTTSProvider(lambda text: _sine_wav())])
    pid = multilang_project["project_id"]
    client.post(f"/projects/{pid}/render/narration-translations/en/start")
    resp = client.get(f"/projects/{pid}/render/narration-download/en")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"


def _sine_wav() -> bytes:
    import subprocess
    import shutil
    import tempfile
    from pathlib import Path

    ffmpeg = shutil.which("ffmpeg")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "s.wav"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", str(out)], capture_output=True, check=True, text=True)
        return out.read_bytes()


def test_transcript_srt_lang_endpoint(client, multilang_project, monkeypatch):
    from app.render import engine

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeTTSProvider()])
    pid = multilang_project["project_id"]
    client.post(f"/projects/{pid}/render/narration-translations/en/start")
    resp = client.get(f"/projects/{pid}/script/transcript-srt/en")
    assert resp.status_code == 200
    text = resp.content.decode("utf-8")
    assert "Hello everyone" in text
    assert "-->" in text


def test_transcript_srt_lang_rejects_invalid_lang(client, multilang_project):
    resp = client.get(f"/projects/{multilang_project['project_id']}/script/transcript-srt/xx")
    assert resp.status_code == 400


def test_edit_script_block_translation(client, multilang_project):
    pid = multilang_project["project_id"]
    resp = client.patch(f"/projects/{pid}/script/body/0/translation/fr", json={"text": "Bonjour à tous."})
    assert resp.status_code == 200
    pack = client.get(f"/projects/{pid}/pack").json()
    assert pack["script"]["body"][0]["audio_by_lang"]["fr"] == "Bonjour à tous."
    assert pack["script"]["body"][0]["audio"] == "Xin chào các bạn, hôm nay ta nói về lịch sử."  # primary (vi) không đổi


def test_edit_script_block_translation_updates_audio_when_lang_is_primary(client, multilang_project):
    pid = multilang_project["project_id"]
    resp = client.patch(f"/projects/{pid}/script/body/0/translation/vi", json={"text": "Văn bản đã sửa."})
    assert resp.status_code == 200
    pack = client.get(f"/projects/{pid}/pack").json()
    assert pack["script"]["body"][0]["audio"] == "Văn bản đã sửa."


# ---------------------------------------------------------------------------
# BrandProfile — primary_language + voice_clone_ref_paths
# ---------------------------------------------------------------------------
def test_brandprofile_default_primary_language_is_vi(client, channel):
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    assert profile["primary_language"] == "vi"
    assert profile["voice_clone_ref_paths"] == {}


def test_put_brandprofile_saves_primary_language(client, channel):
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["primary_language"] = "de"
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile)
    assert resp.status_code == 200
    assert resp.json()["primary_language"] == "de"


def test_upload_voice_sample_lang_saves_to_map(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/voice-sample/upload/de",
        files={"file": ("sample.wav", io.BytesIO(b"RIFF" + b"0" * 40), "audio/wav")},
    )
    assert resp.status_code == 200
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    assert "de" in profile["voice_clone_ref_paths"]
    # Không đụng `voice_clone_ref_path` đơn cũ.
    assert profile["voice_clone_ref_path"] == ""


def test_upload_voice_sample_lang_rejects_invalid_lang(client, channel):
    resp = client.post(
        f"/channels/{channel['id']}/brandprofile/voice-sample/upload/xx",
        files={"file": ("sample.wav", io.BytesIO(b"RIFF" + b"0" * 40), "audio/wav")},
    )
    assert resp.status_code == 400


def test_get_voice_sample_lang_404_when_not_uploaded(client, channel):
    resp = client.get(f"/channels/{channel['id']}/brandprofile/voice-sample/fr")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# pack_export — bundle đa ngôn ngữ
# ---------------------------------------------------------------------------
def test_export_pack_bundle_includes_translated_languages(client, multilang_project, monkeypatch, tmp_path):
    import shutil

    if not shutil.which("ffmpeg"):
        pytest.skip("cần ffmpeg thật trên PATH")
    from app.render import engine

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeTTSProvider(lambda text: _sine_wav())])
    pid = multilang_project["project_id"]
    client.post(f"/projects/{pid}/render/narration-translations/en/start")

    from app.render.pack_export import export_pack_bundle

    out_dir = tmp_path / "export"
    result = export_pack_bundle(pid, str(out_dir))
    assert "transcript_en.srt" in result["included"]
    assert "script_en.txt" in result["included"]  # mới (2026-09-12) — kịch bản .txt thuần
    assert "narration_full_en.mp3" in result["included"]
    assert (out_dir / "transcript_en.srt").exists()
    assert (out_dir / "script_en.txt").exists()
    assert (out_dir / "narration_full_en.mp3").exists()
    # Tiếng Đức có văn bản (B01) nhưng CHƯA sinh giọng đọc — srt/txt vẫn xuất được (không
    # cần giọng đọc thật, chỉ cần văn bản), mp3 phải nằm trong "skipped" kèm lý do rõ ràng.
    assert "transcript_de.srt" in result["included"]
    assert "script_de.txt" in result["included"]
    assert any(s["item"] == "narration_full_de.mp3" for s in result["skipped"])
    # Tiếng Pháp KHÔNG có block nào dịch tới — không được liệt kê ở đâu cả.
    assert not any("fr" in item for item in result["included"])
    assert not any("fr" in s["item"] for s in result["skipped"])
