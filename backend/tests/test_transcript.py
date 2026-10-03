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
# `captions.py` — cắt nhỏ cue dài — mới (2026-09-12), theo yêu cầu người dùng: "File
# transcript srt đang chia timestamp theo block. Vấn đề là mỗi block có thể đọc quá dài
# nên việc hiển thị subtitle theo transcript bị tràn chữ. Cần cắt ngắn xuống."
# ---------------------------------------------------------------------------
def _srt_timestamp_to_sec(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def test_split_text_into_cue_texts_keeps_short_text_as_single_chunk():
    from app.render.captions import split_text_into_cue_texts

    assert split_text_into_cue_texts("Cau ngan.", max_chars=84) == ["Cau ngan."]


def test_split_text_into_cue_texts_never_breaks_mid_word():
    from app.render.captions import split_text_into_cue_texts

    text = " ".join(f"tu{i}" for i in range(40))  # "tu0 tu1 ... tu39" — chắc chắn dài hơn 20 ký tự
    chunks = split_text_into_cue_texts(text, max_chars=20)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 20, f"Đoạn '{c}' vượt quá 20 ký tự"
    # Ghép lại đúng nguyên văn, không mất/lặp từ nào.
    assert " ".join(chunks) == text


def test_split_text_into_cue_texts_keeps_overlong_single_word_whole():
    from app.render.captions import split_text_into_cue_texts

    long_word = "a" * 50
    chunks = split_text_into_cue_texts(f"ngan {long_word} ngan", max_chars=10)
    assert long_word in chunks  # không bị cắt vỡ dù dài hơn max_chars


def test_split_block_into_cues_returns_single_cue_when_text_fits():
    from app.render.captions import split_block_into_cues

    cues = split_block_into_cues("Cau ngan.", 5.0, 3.0, max_chars=84)
    assert cues == [(5.0, 8.0, "Cau ngan.")]


def test_split_block_into_cues_splits_long_text_proportionally_by_char_count():
    from app.render.captions import split_block_into_cues

    # 2 câu ngắn ghép lại dài hơn max_chars=20 — "Cau mot ngan." (13 ký tự) + "Cau hai dai hon nhieu." (22 ký tự).
    text = "Cau mot ngan. Cau hai dai hon nhieu."
    cues = split_block_into_cues(text, 10.0, 10.0, max_chars=20)
    assert len(cues) >= 2
    # Liên tục — không hở/đè giữa các cue.
    for i in range(len(cues) - 1):
        assert cues[i][1] == cues[i + 1][0]
    # Khớp khít khoảng đưa vào.
    assert cues[0][0] == 10.0
    assert cues[-1][1] == pytest.approx(20.0)
    # Ghép lại đúng nguyên văn.
    assert " ".join(c[2] for c in cues) == text
    # Cue DÀI HƠN (nhiều ký tự hơn) phải được cấp NHIỀU THỜI GIAN HƠN — tỷ lệ thuận theo
    # ký tự, không chia đều theo số cue.
    durations = [end - start for start, end, _ in cues]
    chars = [len(t) for _, _, t in cues]
    for i in range(len(cues) - 1):
        if chars[i] != chars[i + 1]:
            assert (durations[i] > durations[i + 1]) == (chars[i] > chars[i + 1])


def test_split_block_into_cues_empty_text_returns_no_cues():
    from app.render.captions import split_block_into_cues

    assert split_block_into_cues("   ", 0.0, 5.0) == []


def test_split_block_into_cues_zero_duration_returns_degenerate_single_cue():
    from app.render.captions import split_block_into_cues

    assert split_block_into_cues("Xin chao", 2.0, 0.0) == [(2.0, 2.0, "Xin chao")]


# ---------------------------------------------------------------------------
# Cắt cue dài áp dụng ĐÚNG vào `_build_srt` (endpoint Script Studio) VÀ
# `pack_export.build_srt_text` (Pack Export) — cả 2 nơi xuất .srt trong app.
# ---------------------------------------------------------------------------
def test_build_srt_splits_long_block_into_multiple_short_cues():
    from app.render.schemas import ShotRenderStatus
    from app.routers.pipeline import _build_srt

    long_text = "Cau mot khong ngan chut nao. Cau hai cung dai khong kem gi ca. Cau ba lai cang dai hon nua day."
    body = [{"block_id": "B01", "audio": long_text, "timestamp_sec": 0, "end_sec": 20}]
    shot_by_block_id = {"B01": {"shot_id": "s1"}}
    narration_by_shot_id = {"s1": ShotRenderStatus(shot_id="s1", narration_status="ready", narration_duration_sec=15.0)}

    srt = _build_srt(body, shot_by_block_id=shot_by_block_id, narration_by_shot_id=narration_by_shot_id, intro_offset=0.0, max_cue_chars=40)
    cues = _parse_srt(srt)
    assert len(cues) > 1, "Block dài phải bị cắt thành nhiều cue"
    for _, _, text in cues:
        assert len(text) <= 40
    # Liên tục, khớp khít đúng 15s giọng đọc thật (KHÔNG PHẢI 20s ghi trong kịch bản).
    assert cues[0][0] == "00:00:00,000"
    assert _srt_timestamp_to_sec(cues[-1][1]) == pytest.approx(15.0, abs=0.01)
    for i in range(len(cues) - 1):
        assert cues[i][1] == cues[i + 1][0]
    # Đánh số cue liên tục (không reset về 1 giữa các sub-cue của CÙNG 1 block).
    assert " ".join(c[2] for c in cues) == long_text


def test_build_srt_text_pack_export_splits_long_block_matching_real_vo_duration_per_language():
    """Xác nhận timing khớp ĐÚNG VO thật của TỪNG NGÔN NGỮ (theo yêu cầu người dùng xác
    nhận thêm: "cần khớp với VO giọng đọc của từng loại ngôn ngữ") — bản dịch "de" DÀI HƠN
    hẳn bản gốc "vi" về số ký tự (đặc trưng thật của tiếng Đức) NHƯNG giọng đọc "de" đo
    thật lại NGẮN HƠN — cue phải chia theo ĐÚNG thời lượng "de" đo được, không lẫn với
    thời lượng "vi"."""
    from app.render.pack_export import build_srt_text
    from app.render.schemas import ShotRenderStatus, TranslatedNarrationStatus

    vi_text = "Cau tieng Viet ngan."
    de_text = "Ein sehr viel laengerer deutscher Satz mit vielen zusammengesetzten Woertern hier."
    pack = {
        "script": {"body": [{"block_id": "B01", "audio": vi_text, "audio_by_lang": {"vi": vi_text, "de": de_text}, "timestamp_sec": 0, "end_sec": 10}]},
        "shots": [{"shot_id": "s1", "block_id": "B01", "linked_timestamp_sec": 0}],
    }
    status = ShotRenderStatus(
        shot_id="s1", narration_status="ready", narration_duration_sec=8.0,
        narration_translations={"de": TranslatedNarrationStatus(narration_status="ready", narration_duration_sec=4.0)},
    )

    srt_vi = build_srt_text(pack, [status], lang="vi", primary_language="vi", max_cue_chars=30)
    srt_de = build_srt_text(pack, [status], lang="de", primary_language="vi", max_cue_chars=30)

    cues_vi = _parse_srt(srt_vi)
    cues_de = _parse_srt(srt_de)
    # "vi" ngắn hơn max_chars=30 → 1 cue duy nhất, khớp đúng 8.0s đo thật của "vi".
    assert len(cues_vi) == 1
    assert _srt_timestamp_to_sec(cues_vi[0][1]) == pytest.approx(8.0)
    # "de" dài hơn 30 ký tự → bị cắt thành nhiều cue, TỔNG khớp đúng 4.0s đo thật của
    # "de" (KHÔNG PHẢI 8.0s của "vi") — đúng yêu cầu "khớp VO của từng ngôn ngữ".
    assert len(cues_de) > 1
    assert _srt_timestamp_to_sec(cues_de[-1][1]) == pytest.approx(4.0, abs=0.01)
    assert " ".join(c[2] for c in cues_de) == de_text


# ---------------------------------------------------------------------------
# `build_script_txt` (2026-09-12) — kịch bản .txt THUẦN, KHÔNG timestamp, theo yêu cầu
# người dùng: "Thêm nút tải kịch bản dạng .txt không có timestamp ở màn script studio
# cho mọi ngôn ngữ."
# ---------------------------------------------------------------------------
def test_build_script_txt_joins_blocks_with_blank_line_no_timestamp():
    from app.render.pack_export import build_script_txt

    pack = {"script": {"body": [
        {"block_id": "B01", "audio": "Cau mot."},
        {"block_id": "B02", "audio": "Cau hai."},
    ]}}
    text = build_script_txt(pack, primary_language="vi")
    assert text == "Cau mot.\n\nCau hai."
    assert "-->" not in text  # KHÔNG có timeline như .srt


def test_build_script_txt_skips_blocks_without_audio_text():
    from app.render.pack_export import build_script_txt

    pack = {"script": {"body": [
        {"block_id": "B01", "audio": ""},
        {"block_id": "B02", "audio": "Co loi thoai."},
    ]}}
    text = build_script_txt(pack, primary_language="vi")
    assert text == "Co loi thoai."


def test_build_script_txt_reads_translation_for_non_primary_lang():
    from app.render.pack_export import build_script_txt

    pack = {"script": {"body": [
        {"block_id": "B01", "audio": "Vietnamese text", "audio_by_lang": {"vi": "Vietnamese text", "en": "English text"}},
    ]}}
    assert build_script_txt(pack, lang="vi", primary_language="vi") == "Vietnamese text"
    assert build_script_txt(pack, lang="en", primary_language="vi") == "English text"


def test_build_script_txt_skips_block_when_translation_missing():
    from app.render.pack_export import build_script_txt

    pack = {"script": {"body": [
        {"block_id": "B01", "audio": "Vietnamese text", "audio_by_lang": {"vi": "Vietnamese text"}},
    ]}}
    # Chưa dịch sang "de" — block bị bỏ qua (khác timeline .srt vẫn cần giữ chỗ), kết quả rỗng.
    assert build_script_txt(pack, lang="de", primary_language="vi") == ""


# ---------------------------------------------------------------------------
# Endpoint /script/transcript-txt(/{lang}) — qua HTTP thật.
# ---------------------------------------------------------------------------
def _import_simple_script(client, pid: str, rows: list[list[str]]) -> None:
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    confirm = client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200, confirm.text


def test_download_transcript_txt_endpoint_requires_script(client, project):
    resp = client.get(f"/projects/{project['id']}/script/transcript-txt")
    assert resp.status_code == 400


def test_download_transcript_txt_endpoint_returns_plain_text_primary_lang(client, project):
    pid = project["id"]
    _import_simple_script(client, pid, [
        ["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai block mot."],
        ["B02", "0:03–0:06", "Image", "Canh 2", "", "Loi thoai block hai."],
    ])
    resp = client.get(f"/projects/{pid}/script/transcript-txt")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/plain")
    assert 'filename="script.txt"' in resp.headers["content-disposition"]
    content = resp.content.decode("utf-8")
    assert content == "Loi thoai block mot.\n\nLoi thoai block hai."
    assert "-->" not in content  # KHÔNG timestamp, khác .srt


def test_download_transcript_txt_lang_endpoint_rejects_invalid_lang(client, project):
    resp = client.get(f"/projects/{project['id']}/script/transcript-txt/xx")
    assert resp.status_code == 400


def test_download_transcript_txt_lang_endpoint_requires_translated_content(client, project):
    pid = project["id"]
    _import_simple_script(client, pid, [["B01", "0:00–0:03", "Image", "Canh 1", "", "Loi thoai."]])
    # Ngôn ngữ hợp lệ nhưng CHƯA từng dịch — không có nội dung để xuất.
    resp = client.get(f"/projects/{pid}/script/transcript-txt/de")
    assert resp.status_code == 400


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
