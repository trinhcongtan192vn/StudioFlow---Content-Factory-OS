"""Tốc độ giọng đọc cho TOÀN BỘ block (2026-09-02, mục 109) — nút chỉnh ở Script Studio,
theo yêu cầu người dùng: "điều chỉnh tốc độ của file giọng đọc được tạo ra" — áp dụng
BẰNG CÁCH time-stretch file audio SAU khi provider TTS sinh xong (ffmpeg `atempo`), KHÔNG
PHẢI tham số riêng của từng provider — xem `app/render/engine.py::_apply_narration_speed`,
`app/render/schemas.py::RenderState.narration_speed`.
"""
import io
import shutil
import subprocess
from pathlib import Path

import pytest

FAKE_WAV = b"RIFF" + b"0" * 40


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    )
    return float(out.stdout.strip())


# ---------------------------------------------------------------------------
# Endpoint CRUD đơn thuần
# ---------------------------------------------------------------------------
def test_patch_narration_speed_saves_value(client, project_with_brief):
    pid = project_with_brief["id"]
    resp = client.patch(f"/projects/{pid}/render/narration-speed", json={"speed": 1.25})
    assert resp.status_code == 200, resp.text
    assert resp.json()["narration_speed"] == 1.25

    status = client.get(f"/projects/{pid}/render/status").json()
    assert status["narration_speed"] == 1.25


def test_patch_narration_speed_default_is_one(client, project_with_brief):
    status = client.get(f"/projects/{project_with_brief['id']}/render/status").json()
    assert status["narration_speed"] == 1.0


@pytest.mark.parametrize("speed", [0.1, 0.49, 2.01, 5.0])
def test_patch_narration_speed_rejects_out_of_range(client, project_with_brief, speed):
    resp = client.patch(f"/projects/{project_with_brief['id']}/render/narration-speed", json={"speed": speed})
    assert resp.status_code == 400


@pytest.mark.parametrize("speed", [0.5, 1.0, 2.0])
def test_patch_narration_speed_accepts_boundary_values(client, project_with_brief, speed):
    resp = client.patch(f"/projects/{project_with_brief['id']}/render/narration-speed", json={"speed": speed})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# `_apply_narration_speed` — ffmpeg thật
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_apply_narration_speed_speeds_up_real_audio(tmp_path):
    from app.render.engine import _apply_narration_speed

    ffmpeg = shutil.which("ffmpeg")
    wav = tmp_path / "narration.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav)], capture_output=True, check=True, text=True)
    original_sec = _ffprobe_duration(wav)
    assert original_sec == pytest.approx(2.0, abs=0.1)

    _apply_narration_speed(wav, 2.0)
    assert _ffprobe_duration(wav) == pytest.approx(original_sec / 2.0, abs=0.15)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_apply_narration_speed_slows_down_real_audio(tmp_path):
    from app.render.engine import _apply_narration_speed

    ffmpeg = shutil.which("ffmpeg")
    wav = tmp_path / "narration.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(wav)], capture_output=True, check=True, text=True)
    original_sec = _ffprobe_duration(wav)

    _apply_narration_speed(wav, 0.5)
    assert _ffprobe_duration(wav) == pytest.approx(original_sec / 0.5, abs=0.15)


def test_apply_narration_speed_noop_when_speed_is_one(tmp_path, monkeypatch):
    """speed==1.0 phải bỏ qua HOÀN TOÀN — không gọi ffmpeg, không đụng file gốc (kể cả
    khi ffmpeg không có trên máy chạy test, dùng monkeypatch thay vì skipif ở đây)."""
    from app.render import engine

    def _boom(name):
        raise AssertionError("KHÔNG được gọi shutil.which khi speed==1.0")

    monkeypatch.setattr(engine.shutil, "which", _boom)
    wav = tmp_path / "narration.wav"
    wav.write_bytes(FAKE_WAV)
    engine._apply_narration_speed(wav, 1.0)
    assert wav.read_bytes() == FAKE_WAV


def test_apply_narration_speed_silently_skips_when_ffmpeg_missing(tmp_path, monkeypatch):
    from app.render import engine

    monkeypatch.setattr(engine.shutil, "which", lambda name: None)
    wav = tmp_path / "narration.wav"
    wav.write_bytes(FAKE_WAV)
    engine._apply_narration_speed(wav, 1.5)  # không raise
    assert wav.read_bytes() == FAKE_WAV  # file gốc giữ nguyên, không có bản ".tmp" rác


# ---------------------------------------------------------------------------
# Tích hợp thật qua `generate_narration_asset` — provider TTS giả (trả WAV THẬT, không
# phải bytes rác) để `_apply_narration_speed` thật sự chạy được, xác nhận
# `narration_duration_sec` ghi lại ĐÚNG thời lượng file ĐÃ điều chỉnh tốc độ (không phải
# thời lượng gốc trước khi stretch).
# ---------------------------------------------------------------------------
class _FakeOmniVoiceProvider:
    provider_name = "omnivoice"

    def __init__(self, wav_bytes: bytes):
        self._wav_bytes = wav_bytes

    def synthesize(self, text, *, emotion="", reference_audio=None):
        return self._wav_bytes


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_generate_narration_asset_applies_project_speed_to_new_narration(client, project_with_brief, tmp_path, monkeypatch):
    from app.config import project_dir
    from app.db import SessionLocal
    from app.filestore import write_json
    from app.models import Project
    from app.render import engine
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:04", "Image", "Canh test", "", "Loi thoai cho block mot, du dai de sinh giong doc."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    # "TTS output" giả nhưng THẬT về mặt file — sine wave 2s, để atempo thật sự xử lý được.
    fake_tts_wav = tmp_path / "fake_tts_out.wav"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(fake_tts_wav)], capture_output=True, check=True, text=True)
    fake_wav_bytes = fake_tts_wav.read_bytes()

    monkeypatch.setattr(engine, "get_tts_chain", lambda db: [_FakeOmniVoiceProvider(fake_wav_bytes)])

    pdir = project_dir(channel_id, pid)
    pack = client.get(f"/projects/{pid}/pack").json()
    beat = pack["script"]["body"][0]

    # speed = 2.0 → file cuối cùng phải ~ NGẮN HƠN 2 lần bản gốc (đã stretch).
    state = RenderState(project_id=pid, narration_speed=2.0)
    write_json(pdir / "render.json", state.model_dump())

    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        status = ShotRenderStatus(shot_id=shot_id)
        engine.generate_narration_asset(db, p, pdir, beat, status, state)
    finally:
        db.close()

    assert status.narration_status == "ready", status.narration_error
    assert status.narration_asset_path
    real_duration = _ffprobe_duration(Path(status.narration_asset_path))
    assert real_duration == pytest.approx(2.0 / 2.0, abs=0.2)
    assert status.narration_duration_sec == pytest.approx(real_duration, abs=0.05)
