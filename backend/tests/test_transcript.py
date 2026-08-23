"""Test transcript .srt export — 2026-08-20, theo yêu cầu người dùng: timestamp kịch
bản (nhập tay lúc import) CHỈ mang tính tham khảo, KHÔNG dùng để tính timeline transcript
nữa — ưu tiên độ dài GIỌNG ĐỌC THẬT (đo qua ffprobe), cộng thêm offset intro (nếu có,
xem `app/render/intro.py`) để khớp đúng timeline video THẬT ghép ra.
"""
import io

import pytest


def _parse_srt(content: str) -> list[tuple[str, str, str]]:
    """Parse .srt tối giản — trả list (start, end, text), đủ dùng để so sánh trong test."""
    blocks = [b for b in content.strip().split("\n\n") if b.strip()]
    result = []
    for b in blocks:
        lines = b.splitlines()
        start, _, end = lines[1].partition(" --> ")
        text = "\n".join(lines[2:])
        result.append((start, end, text))
    return result


# ---------------------------------------------------------------------------
# `_build_srt` — logic thuần, không cần ffmpeg (input đã là số đo sẵn).
# ---------------------------------------------------------------------------
def test_build_srt_uses_real_narration_duration_over_timestamp():
    from app.render.schemas import ShotRenderStatus
    from app.routers.pipeline import _build_srt

    body = [{"block_id": "B01", "audio": "Xin chao", "timestamp_sec": 0, "end_sec": 40}]  # kịch bản ghi 40s
    shot_by_block_id = {"B01": {"shot_id": "s1"}}
    narration_by_shot_id = {"s1": ShotRenderStatus(shot_id="s1", narration_status="ready", narration_duration_sec=34.0)}

    srt = _build_srt(body, shot_by_block_id=shot_by_block_id, narration_by_shot_id=narration_by_shot_id, intro_offset=0.0)
    cues = _parse_srt(srt)
    assert len(cues) == 1
    start, end, text = cues[0]
    assert start == "00:00:00,000"
    assert end == "00:00:34,000"  # khớp giọng đọc thật 34s, KHÔNG PHẢI 40s ghi trong kịch bản
    assert text == "Xin chao"


def test_build_srt_falls_back_to_timestamp_when_narration_not_ready():
    from app.routers.pipeline import _build_srt

    body = [{"block_id": "B01", "audio": "Xin chao", "timestamp_sec": 0, "end_sec": 6}]
    srt = _build_srt(body, shot_by_block_id={}, narration_by_shot_id={}, intro_offset=0.0)
    cues = _parse_srt(srt)
    assert cues[0][1] == "00:00:06,000"


def test_build_srt_cues_are_cumulative_not_original_timestamps():
    """Cue thứ 2 phải bắt đầu NGAY sau khi cue 1 (theo giọng đọc thật) kết thúc — không
    dùng lại `timestamp_sec` gốc của block 2 trong kịch bản (có thể lệch hẳn so với
    tổng giọng đọc thật cộng dồn tới lúc đó)."""
    from app.render.schemas import ShotRenderStatus
    from app.routers.pipeline import _build_srt

    body = [
        {"block_id": "B01", "audio": "Cau 1", "timestamp_sec": 0, "end_sec": 40},
        {"block_id": "B02", "audio": "Cau 2", "timestamp_sec": 40, "end_sec": 80},  # kịch bản ghi bắt đầu ở giây 40
    ]
    shot_by_block_id = {"B01": {"shot_id": "s1"}, "B02": {"shot_id": "s2"}}
    narration_by_shot_id = {
        "s1": ShotRenderStatus(shot_id="s1", narration_status="ready", narration_duration_sec=10.0),  # thật chỉ 10s, không phải 40s
        "s2": ShotRenderStatus(shot_id="s2", narration_status="ready", narration_duration_sec=5.0),
    }
    srt = _build_srt(body, shot_by_block_id=shot_by_block_id, narration_by_shot_id=narration_by_shot_id, intro_offset=0.0)
    cues = _parse_srt(srt)
    assert cues[0] == ("00:00:00,000", "00:00:10,000", "Cau 1")
    # Cue 2 bắt đầu ĐÚNG lúc cue 1 (giọng đọc thật) kết thúc — giây 10, KHÔNG PHẢI giây 40.
    assert cues[1] == ("00:00:10,000", "00:00:15,000", "Cau 2")


def test_build_srt_shifts_all_cues_by_intro_offset():
    from app.render.schemas import ShotRenderStatus
    from app.routers.pipeline import _build_srt

    body = [{"block_id": "B01", "audio": "Xin chao", "timestamp_sec": 0, "end_sec": 5}]
    shot_by_block_id = {"B01": {"shot_id": "s1"}}
    narration_by_shot_id = {"s1": ShotRenderStatus(shot_id="s1", narration_status="ready", narration_duration_sec=3.0)}

    srt = _build_srt(body, shot_by_block_id=shot_by_block_id, narration_by_shot_id=narration_by_shot_id, intro_offset=7.5)
    cues = _parse_srt(srt)
    assert cues[0][0] == "00:00:07,500"  # khớp video THẬT: intro 7.5s phát trước, rồi mới tới cue này
    assert cues[0][1] == "00:00:10,500"


def test_build_srt_skips_blocks_without_audio_text():
    from app.routers.pipeline import _build_srt

    body = [{"block_id": "B01", "audio": "", "timestamp_sec": 0, "end_sec": 5}, {"block_id": "B02", "audio": "Co loi thoai", "timestamp_sec": 5, "end_sec": 10}]
    srt = _build_srt(body, shot_by_block_id={}, narration_by_shot_id={}, intro_offset=0.0)
    cues = _parse_srt(srt)
    assert len(cues) == 1
    assert cues[0][2] == "Co loi thoai"


# ---------------------------------------------------------------------------
# Endpoint thật — real ffmpeg (đo narration/intro thật qua ffprobe).
# ---------------------------------------------------------------------------
import shutil
import subprocess
from pathlib import Path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_transcript_endpoint_uses_real_narration_and_intro_offset(client, project, tmp_path):
    """Test THẬT xuyên suốt (bug thật người dùng báo, 2026-08-20 — "cần cover cả case
    brand video/audio để tính toán timestamp cho đúng"): brand có audio thương hiệu 1s,
    1 shot có giọng đọc thật 2s (khác timestamp kịch bản ghi 8s) — gọi endpoint THẬT,
    xác nhận cue transcript bắt đầu ở giây ~1 (SAU intro), kết thúc ~3s (1s intro + 2s
    giọng đọc thật) — KHÔNG PHẢI 0-8s như nếu vẫn dùng timestamp kịch bản không offset."""
    from app.config import project_dir
    from app.filestore import write_json
    from app.render.schemas import RenderState, ShotRenderStatus

    ffmpeg = shutil.which("ffmpeg")
    pid = project["id"]
    channel_id = project["channel_id"]

    # Brand audio thương hiệu, ~1 giây thật.
    brand_audio_src = tmp_path / "brand_intro.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "mp3", str(brand_audio_src)], capture_output=True, check=True, text=True)
    client.post(f"/channels/{channel_id}/brandprofile/intro/upload", files={"file": ("intro.mp3", brand_audio_src.open("rb"), "audio/mpeg")})

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [["B01", "0:00–0:08", "Image", "Canh test", "Khong tieng", "Loi thoai that ngan hon nhieu."]]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    pdir = project_dir(channel_id, pid)
    shot_png = pdir / "assets" / f"{shot_id}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", "-update", "1", str(shot_png)], capture_output=True, check=True, text=True)
    narration_mp3 = pdir / "assets" / f"{shot_id}.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=2", "-c:a", "mp3", str(narration_mp3)], capture_output=True, check=True, text=True)

    state = RenderState(project_id=pid, shots=[ShotRenderStatus(
        shot_id=shot_id, visual_status="ready", visual_asset_path=str(shot_png), approved=True,
        narration_status="ready", narration_asset_path=str(narration_mp3), narration_duration_sec=2.0,
    )])
    write_json(pdir / "render.json", state.model_dump())

    resp = client.get(f"/projects/{pid}/script/transcript-srt")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    cues = _parse_srt(content)
    assert len(cues) == 1
    start, end, _text = cues[0]
    # Offset ~1s (audio thương hiệu) rồi mới tới giọng đọc thật ~2s — cho phép sai số nhỏ
    # (mp3 encode có thể lệch vài chục ms so với duration khai báo).
    assert start.startswith("00:00:00,9") or start.startswith("00:00:01,0") or start.startswith("00:00:01,1")
    assert end.startswith("00:00:02,9") or end.startswith("00:00:03,0") or end.startswith("00:00:03,1")
