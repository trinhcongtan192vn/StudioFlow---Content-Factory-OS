"""Xuất short-video 9:16 từ 1 khoảng block, ở Output Center — mới (2026-09-12), theo yêu
cầu người dùng. Xem docstring `ShortVideoExport` (render/schemas.py) và
`render/short_export.py` cho thiết kế đầy đủ. Test chia 2 nhóm: (1) validate/cap/router —
KHÔNG cần ffmpeg thật (stub `run_short_export`); (2) pipeline ghép thật — CẦN ffmpeg thật
trên PATH (`@pytest.mark.skipif`), verify crop-fill (không co ảnh, không viền
đen)/video-không-bao-giờ-sinh-lại/sinh ảnh qua provider giả bằng ffprobe/pixel sampling
THẬT, không suy đoán."""
from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import project_dir
from app.db import SessionLocal
from app.filestore import read_json, write_json
from app.render.schemas import RenderState, ShortVideoExport, ShotRenderStatus


def _import_shots(client, project_id: str, rows: list[list[str]]) -> list[str]:
    """`rows` — mỗi phần tử `[block_id, ts_label, visual_type, visual_fx, audio_sfx, vo]`.
    Trả về danh sách `shot_id` theo ĐÚNG thứ tự đã import (cùng helper dùng ở
    `test_visual_studio_vault.py`)."""
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{project_id}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    confirm = client.post(f"/projects/{project_id}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200, confirm.text
    resp = client.post(f"/projects/{project_id}/visual/generate")
    assert resp.status_code == 200, resp.text
    return [s["shot_id"] for s in resp.json()["shots"]]


def _mark_shot_ready_fake(client, project_id: str, channel_id: str, shot_id: str, *, suffix: str, content: bytes = b"fake-bytes", narration_ready: bool = True) -> None:
    """Đánh dấu shot `ready` bằng bytes GIẢ (đủ cho test validate/cap/router — KHÔNG đi
    qua ffmpeg thật). `narration_ready=True` (mặc định, mới — theo gate ngôn ngữ mục
    "cho phép chọn ngôn ngữ khi xuất short-video") — giọng đọc ngôn ngữ CHÍNH ("vi") của
    shot cũng phải "ready" thì `create_short_export` mới không bị 400; đường fake KHÔNG
    cần file audio thật tồn tại (`create_short_export` chỉ đọc field `narration_status`,
    không mở file)."""
    pdir = project_dir(channel_id, project_id)
    asset_path = pdir / "assets" / f"{shot_id}{suffix}"
    asset_path.write_bytes(content)
    narration_path = pdir / "assets" / f"{shot_id}_narration.mp3" if narration_ready else None
    _patch_render_state(project_id, pdir, shot_id, str(asset_path), narration_asset_path=str(narration_path) if narration_path else None)


def _mark_shot_ready_real(ffmpeg: str, project_id: str, channel_id: str, shot_id: str, *, color: str, is_video: bool, narration_ready: bool = True, narration_duration: float = 2.0) -> None:
    """Đánh dấu shot `ready` bằng ảnh/video THẬT dựng qua ffmpeg (màu đặc `color`) — bắt
    buộc cho MỌI test đi qua `run_short_export` thật (tránh đúng bẫy FAKE_PNG làm ffmpeg
    thật treo vô hạn, xem IMPLEMENTATION_REPORT.md — bug đã sửa trong chính session này).
    `narration_ready=True` (mặc định) — dựng luôn 1 file audio CÂM THẬT qua ffmpeg
    (`anullsrc`, bắt buộc cho `run_short_export` thật — `_build_segment` mux audio này
    qua ffmpeg thật, KHÔNG chấp nhận bytes giả, cùng lý do ảnh/video phải là file thật)."""
    pdir = project_dir(channel_id, project_id)
    ext = ".mp4" if is_video else ".png"
    asset_path = pdir / "assets" / f"{shot_id}{ext}"
    if is_video:
        cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=640x360:d=2", "-pix_fmt", "yuv420p", str(asset_path)]
    else:
        cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=640x360", "-frames:v", "1", "-update", "1", str(asset_path)]
    subprocess.run(cmd, capture_output=True, check=True, text=True)
    narration_path = None
    if narration_ready:
        narration_path = pdir / "assets" / f"{shot_id}_narration.mp3"
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=44100", "-t", str(narration_duration), str(narration_path)],
            capture_output=True, check=True, text=True,
        )
    _patch_render_state(
        project_id, pdir, shot_id, str(asset_path),
        narration_asset_path=str(narration_path) if narration_path else None,
        narration_duration_sec=narration_duration if narration_ready else None,
    )


def _patch_render_state(project_id: str, pdir, shot_id: str, asset_path: str, *, narration_asset_path: str | None = None, narration_duration_sec: float | None = None) -> None:
    render_path = pdir / "render.json"
    existing = read_json(render_path) or {}
    state = RenderState(**existing) if existing else RenderState(project_id=project_id)
    by_id = {s.shot_id: s for s in state.shots}
    status = by_id.get(shot_id) or ShotRenderStatus(shot_id=shot_id)
    status.visual_status = "ready"
    status.visual_asset_path = asset_path
    if narration_asset_path:
        status.narration_status = "ready"
        status.narration_asset_path = narration_asset_path
        status.narration_duration_sec = narration_duration_sec or 2.0
    by_id[shot_id] = status
    state.shots = list(by_id.values())
    write_json(render_path, state.model_dump())


def _seed_dummy_done_exports(project_id: str, channel_id: str, n: int) -> None:
    """Điền thẳng `n` entry `ShortVideoExport(status="done")` giả vào `render.json` —
    dùng cho test cap-3/xoá KHÔNG cần chạy pipeline ghép thật."""
    pdir = project_dir(channel_id, project_id)
    render_path = pdir / "render.json"
    existing = read_json(render_path) or {}
    state = RenderState(**existing) if existing else RenderState(project_id=project_id)
    video_dir = pdir / "renders" / "short"
    video_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        video_path = video_dir / f"dummy_{i}.mp4"
        video_path.write_bytes(b"dummy")
        state.short_exports.append(
            ShortVideoExport(id=f"short_dummy_{i}", start_block_id="B01", end_block_id="B01", status="done", video_path=str(video_path))
        )
    write_json(render_path, state.model_dump())


@pytest.fixture()
def short_export_project(client, channel):
    """5 block: B01/B02/B03 ảnh, B04 video, B05 ảnh — CHỈ B01-B04 đã `ready` (B05 CỐ Ý
    để `pending` — dùng để verify validate chỉ soi đúng khoảng đã chọn)."""
    resp = client.post(f"/channels/{channel['id']}/projects", json={"title": "Short Export Test"})
    project = resp.json()
    rows = [
        ["B01", "0:00–0:02", "Image", "Canh song mua he", "", "Loi thoai B01."],
        ["B02", "0:02–0:04", "Image", "Canh nui non hung vi", "", "Loi thoai B02."],
        ["B03", "0:04–0:06", "Image", "Canh cho dong que", "", "Loi thoai B03."],
        ["B04", "0:06–0:09", "Video", "Drone bay qua rung", "", "Loi thoai B04."],
        ["B05", "0:09–0:11", "Image", "Canh hoang hon", "", "Loi thoai B05."],
    ]
    shot_ids = _import_shots(client, project["id"], rows)
    for shot_id in shot_ids[:3]:
        _mark_shot_ready_fake(client, project["id"], channel["id"], shot_id, suffix=".png")
    _mark_shot_ready_fake(client, project["id"], channel["id"], shot_ids[3], suffix=".mp4")
    return {"project": project, "channel": channel, "shot_ids": shot_ids}


# ---------------------------------------------------------------------------
# `_resolve_block_range` — tầng module, không qua HTTP
# ---------------------------------------------------------------------------
def _fake_pack(block_ids: list[str]) -> dict:
    return {
        "script": {"body": [{"block_id": b, "timestamp_sec": i * 2, "end_sec": i * 2 + 2, "audio": f"Loi {b}"} for i, b in enumerate(block_ids)]},
        "shots": [{"shot_id": f"shot_{b}", "block_id": b, "visual_type": "image", "transition_to_next": "cut"} for b in block_ids],
    }


def test_resolve_block_range_returns_shots_in_order():
    from app.render.short_export import _resolve_block_range

    pack = _fake_pack(["B01", "B02", "B03", "B04"])
    shots = _resolve_block_range(pack, "B02", "B03")
    assert [s["shot_id"] for s in shots] == ["shot_B02", "shot_B03"]


def test_resolve_block_range_raises_when_start_block_missing():
    from app.render.short_export import _resolve_block_range

    pack = _fake_pack(["B01", "B02"])
    with pytest.raises(ValueError, match="block đầu"):
        _resolve_block_range(pack, "B99", "B02")


def test_resolve_block_range_raises_when_end_block_missing():
    from app.render.short_export import _resolve_block_range

    pack = _fake_pack(["B01", "B02"])
    with pytest.raises(ValueError, match="block cuối"):
        _resolve_block_range(pack, "B01", "B99")


def test_resolve_block_range_raises_when_start_after_end():
    from app.render.short_export import _resolve_block_range

    pack = _fake_pack(["B01", "B02", "B03"])
    with pytest.raises(ValueError, match="trước"):
        _resolve_block_range(pack, "B03", "B01")


# ---------------------------------------------------------------------------
# `create_short_export` / cap 3 — tầng module
# ---------------------------------------------------------------------------
def test_create_short_export_raises_on_invalid_block_range(short_export_project):
    from app.models import Project
    from app.render.short_export import create_short_export

    pid = short_export_project["project"]["id"]
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        with pytest.raises(ValueError, match="block đầu"):
            create_short_export(db, project, "KHONG_TON_TAI", "B02", False)
    finally:
        db.close()


def test_create_short_export_enforces_cap_of_3(short_export_project):
    from app.models import Project
    from app.render.short_export import create_short_export

    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    _seed_dummy_done_exports(pid, channel_id, 3)
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        with pytest.raises(ValueError, match="Đã đủ 3"):
            create_short_export(db, project, "B01", "B02", False)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Chọn ngôn ngữ khi xuất short-video — mới (2026-09-12), theo yêu cầu người dùng "cho
# phép chọn ngôn ngữ khi xuất short-video, tương tự như khi render long-video".
# ---------------------------------------------------------------------------
def test_create_short_export_defaults_lang_to_primary_language(short_export_project):
    from app.models import Project
    from app.render.short_export import create_short_export

    pid = short_export_project["project"]["id"]
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        export = create_short_export(db, project, "B01", "B02", False)  # lang=None
        assert export.lang == "vi"  # ngôn ngữ chính mặc định của kênh mới tạo
    finally:
        db.close()


def test_create_short_export_raises_on_invalid_lang(short_export_project):
    from app.models import Project
    from app.render.short_export import create_short_export

    pid = short_export_project["project"]["id"]
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        with pytest.raises(ValueError, match="Ngôn ngữ không hợp lệ"):
            create_short_export(db, project, "B01", "B02", False, lang="klingon")
    finally:
        db.close()


def test_create_short_export_raises_when_narration_missing_for_selected_lang(short_export_project):
    """B01/B02 chỉ có giọng đọc ngôn ngữ CHÍNH ("vi", từ fixture) — chọn "en" (chưa từng
    sinh cho bất kỳ shot nào) phải bị chặn 400, liệt kê đúng shot thiếu."""
    from app.models import Project
    from app.render.short_export import create_short_export

    pid = short_export_project["project"]["id"]
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        with pytest.raises(ValueError, match=r"Giọng đọc \[en\]"):
            create_short_export(db, project, "B01", "B02", False, lang="en")
    finally:
        db.close()


def test_create_short_export_narration_gate_only_checks_shots_within_selected_range(short_export_project):
    """Giọng đọc "en" CHỈ sinh cho B01 (trong khoảng đang xuất) — B02..B05 KHÔNG có "en"
    (kể cả B02 dù đã ready ở ngôn ngữ chính) — vẫn phải xuất ĐƯỢC khoảng B01-B01, đúng
    nguyên tắc validate CHỈ soi shot TRONG khoảng đã chọn."""
    from app.models import Project
    from app.render.schemas import TranslatedNarrationStatus
    from app.render.short_export import create_short_export

    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    shot_ids = short_export_project["shot_ids"]
    pdir = project_dir(channel_id, pid)
    state = RenderState(**read_json(pdir / "render.json"))
    by_id = {s.shot_id: s for s in state.shots}
    by_id[shot_ids[0]].narration_translations["en"] = TranslatedNarrationStatus(narration_status="ready", narration_asset_path="/fake/en.mp3", narration_duration_sec=2.0)
    write_json(pdir / "render.json", state.model_dump())

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        export = create_short_export(db, project, "B01", "B01", False, lang="en")
        assert export.lang == "en"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Router — POST/DELETE/GET download (stub `run_short_export`, không cần ffmpeg thật)
# ---------------------------------------------------------------------------
def test_post_short_export_creates_pending_entry_and_schedules_background_task(client, short_export_project, monkeypatch):
    calls = []
    monkeypatch.setattr("app.routers.render.run_short_export", lambda pid, eid: calls.append((pid, eid)))

    pid = short_export_project["project"]["id"]
    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B02", "regenerate_images": False})
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert len(state["short_exports"]) == 1
    export = state["short_exports"][0]
    assert export["start_block_id"] == "B01"
    assert export["end_block_id"] == "B02"
    assert export["regenerate_images"] is False
    assert calls == [(pid, export["id"])]


def test_post_short_export_400_on_unknown_block_id(client, short_export_project, monkeypatch):
    monkeypatch.setattr("app.routers.render.run_short_export", lambda pid, eid: None)
    pid = short_export_project["project"]["id"]
    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "KHONG_TON_TAI", "end_block_id": "B02"})
    assert resp.status_code == 400


def test_post_short_export_400_on_invalid_lang(client, short_export_project, monkeypatch):
    monkeypatch.setattr("app.routers.render.run_short_export", lambda pid, eid: None)
    pid = short_export_project["project"]["id"]
    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B02", "lang": "klingon"})
    assert resp.status_code == 400


def test_post_short_export_400_when_narration_missing_for_selected_lang(client, short_export_project, monkeypatch):
    monkeypatch.setattr("app.routers.render.run_short_export", lambda pid, eid: None)
    pid = short_export_project["project"]["id"]
    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B02", "lang": "de"})
    assert resp.status_code == 400
    assert "de" in resp.json()["detail"]


def test_post_short_export_400_when_cap_reached(client, short_export_project, monkeypatch):
    monkeypatch.setattr("app.routers.render.run_short_export", lambda pid, eid: None)
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    _seed_dummy_done_exports(pid, channel_id, 3)
    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B02"})
    assert resp.status_code == 400
    assert "3" in resp.json()["detail"]


def test_delete_short_export_removes_entry_and_frees_cap_slot(client, short_export_project, monkeypatch):
    monkeypatch.setattr("app.routers.render.run_short_export", lambda pid, eid: None)
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    _seed_dummy_done_exports(pid, channel_id, 3)

    # Đầy cap — tạo mới bị chặn.
    assert client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B02"}).status_code == 400

    state = client.get(f"/projects/{pid}/render/status").json()
    victim_id = state["short_exports"][0]["id"]
    victim_video_path = state["short_exports"][0]["video_path"]
    assert Path(victim_video_path).exists()

    resp = client.delete(f"/projects/{pid}/render/short-export/{victim_id}")
    assert resp.status_code == 200
    new_state = resp.json()
    assert len(new_state["short_exports"]) == 2
    assert all(e["id"] != victim_id for e in new_state["short_exports"])
    assert not Path(victim_video_path).exists()

    # Slot đã giải phóng — tạo mới lại được.
    resp2 = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B02"})
    assert resp2.status_code == 200


def test_delete_short_export_404_when_not_found(client, short_export_project):
    pid = short_export_project["project"]["id"]
    resp = client.delete(f"/projects/{pid}/render/short-export/khong_ton_tai")
    assert resp.status_code == 404


def test_download_short_export_400_when_not_done(client, short_export_project, monkeypatch):
    monkeypatch.setattr("app.routers.render.run_short_export", lambda pid, eid: None)
    pid = short_export_project["project"]["id"]
    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B02"})
    export_id = resp.json()["short_exports"][0]["id"]
    dl = client.get(f"/projects/{pid}/render/short-export/{export_id}/download")
    assert dl.status_code == 400


# ---------------------------------------------------------------------------
# Pipeline ghép THẬT — cần ffmpeg trên PATH
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_run_short_export_only_validates_shots_within_selected_range(client, short_export_project):
    """B05 (ngoài khoảng B01-B02) vẫn `pending` — KHÔNG được để chặn export chỉ chọn
    B01-B02. `client.post` (Starlette TestClient) chạy `BackgroundTasks` NGAY TRONG
    request — không cần gọi `run_short_export` tay thêm lần nữa (gọi lại sẽ chạy pipeline
    2 LẦN, đã bắt được bug này ở 1 test khác trong cùng file)."""
    ffmpeg = shutil.which("ffmpeg")
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    shot_ids = short_export_project["shot_ids"]
    _mark_shot_ready_real(ffmpeg, pid, channel_id, shot_ids[0], color="red", is_video=False)
    _mark_shot_ready_real(ffmpeg, pid, channel_id, shot_ids[1], color="blue", is_video=False)

    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B02"})
    export_id = resp.json()["short_exports"][0]["id"]

    pdir = project_dir(channel_id, pid)
    state = RenderState(**read_json(pdir / "render.json"))
    export = next(e for e in state.short_exports if e.id == export_id)
    assert export.status == "done", export.error
    assert export.video_path and Path(export.video_path).exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_run_short_export_burns_caption_when_caption_layer_enabled(client, short_export_project):
    """Caption Layer (mới 2026-09-12) áp dụng CHO CẢ short-video export, theo yêu cầu
    người dùng xác nhận (dùng CHUNG `state.caption_layer` với video chính). Bật qua ĐÚNG
    endpoint PATCH thật (giống người dùng thao tác qua UI), verify khung hình cuối THẬT
    SỰ có pixel caption ở dải dưới khung hình dọc 1080x1920."""
    ffmpeg = shutil.which("ffmpeg")
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    shot_ids = short_export_project["shot_ids"]
    _mark_shot_ready_real(ffmpeg, pid, channel_id, shot_ids[0], color="blue", is_video=False)

    resp = client.patch(f"/projects/{pid}/render/caption-layer", json={"enabled": True, "position": "bottom-center", "size_pct": 0.06})
    assert resp.status_code == 200, resp.text

    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B01"})
    export_id = resp.json()["short_exports"][0]["id"]

    pdir = project_dir(channel_id, pid)
    state = RenderState(**read_json(pdir / "render.json"))
    export = next(e for e in state.short_exports if e.id == export_id)
    assert export.status == "done", export.error

    frame = pdir / "renders" / "short" / "caption_check_frame.png"
    subprocess.run([ffmpeg, "-y", "-i", export.video_path, "-frames:v", "1", str(frame)], capture_output=True, check=True, text=True)

    def _non_blue_count(y: int, h: int) -> int:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(frame), "-vf", f"crop=iw:{h}:0:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        )
        data = result.stdout
        return sum(1 for i in range(0, len(data) - 2, 3) if abs(data[i]) > 40 or abs(data[i + 1]) > 40 or abs(data[i + 2] - 255) > 40)

    assert _non_blue_count(1700, 200) > 200, "Không thấy pixel caption ở dải dưới khung hình short-video dù caption_layer.enabled=True"


def _frame_top_and_middle_rgb(ffmpeg: str, frame: Path) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    def _avg_rgb(y: int, h: int) -> tuple[float, float, float]:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(frame), "-vf", f"crop=1080:{h}:0:{y},scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        )
        data = result.stdout
        return (data[0], data[1], data[2]) if len(data) >= 3 else (0, 0, 0)

    return _avg_rgb(0, 40), _avg_rgb(940, 40)  # viền trên / giữa khung dọc 1920 cao


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_run_short_export_crops_original_16_9_image_without_shrinking(client, short_export_project):
    """`regenerate_images=False` (mặc định) — ảnh 16:9 gốc phải được CROP-FILL vào khung
    dọc (phóng lên vừa chiều cao rồi cắt bớt 2 bên), KHÔNG co nhỏ nội dung + viền đen —
    **đổi (2026-09-12), theo yêu cầu người dùng**: bản đầu dùng letterbox, người dùng báo
    ảnh bị "co hẹp" giữa 2 viền đen, yêu cầu đổi sang crop. Verify bằng ffprobe/ffmpeg
    THẬT: lấy 1 khung hình giữa video, đo màu ở dải TRÊN CÙNG và dải GIỮA khung — CẢ 2
    phải là màu nội dung thật (`red`), KHÔNG có dải nào gần đen (letterbox cũ sẽ làm dải
    trên ra đen — bug đã sửa)."""
    ffmpeg = shutil.which("ffmpeg")
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    shot_ids = short_export_project["shot_ids"]
    _mark_shot_ready_real(ffmpeg, pid, channel_id, shot_ids[0], color="red", is_video=False)

    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B01"})
    export_id = resp.json()["short_exports"][0]["id"]

    pdir = project_dir(channel_id, pid)
    state = RenderState(**read_json(pdir / "render.json"))
    export = next(e for e in state.short_exports if e.id == export_id)
    assert export.status == "done", export.error

    frame = pdir / "renders" / "short" / "frame_test.png"
    subprocess.run([ffmpeg, "-y", "-i", export.video_path, "-frames:v", "1", str(frame)], capture_output=True, check=True, text=True)
    top_rgb, middle_rgb = _frame_top_and_middle_rgb(ffmpeg, frame)

    assert top_rgb[0] > 150 and top_rgb[1] < 80 and top_rgb[2] < 80, f"Viền trên phải VẪN LÀ màu đỏ nội dung (crop, không letterbox), đo được {top_rgb}"
    assert middle_rgb[0] > 150 and middle_rgb[1] < 80 and middle_rgb[2] < 80, f"Giữa khung phải là màu đỏ nội dung gốc, đo được {middle_rgb}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_run_short_export_crops_original_16_9_video_without_shrinking(client, short_export_project):
    """Cùng bug/fix ở trên — ÁP DỤNG CHO CẢ shot dạng VIDEO (theo yêu cầu người dùng
    "làm tương tự với visual là loại video"), không chỉ ảnh."""
    ffmpeg = shutil.which("ffmpeg")
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    shot_ids = short_export_project["shot_ids"]
    _mark_shot_ready_real(ffmpeg, pid, channel_id, shot_ids[3], color="red", is_video=True)

    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B04", "end_block_id": "B04"})
    export_id = resp.json()["short_exports"][0]["id"]

    pdir = project_dir(channel_id, pid)
    state = RenderState(**read_json(pdir / "render.json"))
    export = next(e for e in state.short_exports if e.id == export_id)
    assert export.status == "done", export.error

    frame = pdir / "renders" / "short" / "frame_test_video.png"
    subprocess.run([ffmpeg, "-y", "-i", export.video_path, "-frames:v", "1", str(frame)], capture_output=True, check=True, text=True)
    top_rgb, middle_rgb = _frame_top_and_middle_rgb(ffmpeg, frame)

    assert top_rgb[0] > 150 and top_rgb[1] < 80 and top_rgb[2] < 80, f"Viền trên phải VẪN LÀ màu đỏ nội dung (crop, không letterbox), đo được {top_rgb}"
    assert middle_rgb[0] > 150 and middle_rgb[1] < 80 and middle_rgb[2] < 80, f"Giữa khung phải là màu đỏ nội dung gốc, đo được {middle_rgb}"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_run_short_export_never_regenerates_video_shots_even_when_regenerate_images_true(client, short_export_project, monkeypatch):
    """Shot dạng VIDEO trong khoảng LUÔN giữ nguyên bản gốc + letterbox — theo yêu cầu
    người dùng, sinh lại VIDEO 9:16 ngoài phạm vi tính năng này. Verify bằng cách monkeypatch
    `get_image_chain` để RAISE nếu bị gọi — export chỉ có 1 shot VIDEO trong khoảng nên
    hàm sinh ảnh không được phép gọi tới nó."""
    def _fail_if_called(db):
        raise AssertionError("get_image_chain KHÔNG được gọi khi khoảng chỉ toàn shot video")

    monkeypatch.setattr("app.render.short_export.get_image_chain", _fail_if_called)

    ffmpeg = shutil.which("ffmpeg")
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    shot_ids = short_export_project["shot_ids"]
    _mark_shot_ready_real(ffmpeg, pid, channel_id, shot_ids[3], color="green", is_video=True)

    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B04", "end_block_id": "B04", "regenerate_images": True})
    export_id = resp.json()["short_exports"][0]["id"]

    pdir = project_dir(channel_id, pid)
    state = RenderState(**read_json(pdir / "render.json"))
    export = next(e for e in state.short_exports if e.id == export_id)
    assert export.status == "done", export.error


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_run_short_export_regenerates_image_to_separate_path_without_touching_original(client, short_export_project, monkeypatch, tmp_path):
    """`regenerate_images=True` — ảnh MỚI (9:16) phải lưu ở thư mục RIÊNG của export,
    KHÔNG được đè lên `visual_asset_path` gốc 16:9 của shot."""
    ffmpeg = shutil.which("ffmpeg")
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    shot_ids = short_export_project["shot_ids"]
    _mark_shot_ready_real(ffmpeg, pid, channel_id, shot_ids[0], color="red", is_video=False)

    pdir = project_dir(channel_id, pid)
    original_path = Path(RenderState(**read_json(pdir / "render.json")).shots[0].visual_asset_path)
    original_bytes = original_path.read_bytes()

    new_png = tmp_path / "regenerated.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=yellow:s=200x360", "-frames:v", "1", "-update", "1", str(new_png)], capture_output=True, check=True, text=True)
    new_png_bytes = new_png.read_bytes()

    calls = {"aspect_ratio": None, "count": 0}

    class FakeQwenProvider:
        provider_name = "local_qwen"

        def generate(self, prompt, *, seed=None, reference_image=None, aspect_ratio="16:9"):
            calls["aspect_ratio"] = aspect_ratio
            calls["count"] += 1
            return new_png_bytes

    monkeypatch.setattr("app.render.short_export.get_image_chain", lambda db: [FakeQwenProvider()])

    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B01", "regenerate_images": True})
    export_id = resp.json()["short_exports"][0]["id"]

    state = RenderState(**read_json(pdir / "render.json"))
    export = next(e for e in state.short_exports if e.id == export_id)
    assert export.status == "done", export.error
    assert calls["count"] == 1
    assert calls["aspect_ratio"] == "9:16"
    assert original_path.read_bytes() == original_bytes  # asset gốc KHÔNG bị đụng
    regenerated_path = pdir / "renders" / "short" / export_id / "assets" / f"{shot_ids[0]}.png"
    assert regenerated_path.exists()
    assert regenerated_path.read_bytes() == new_png_bytes


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg thật trên PATH")
def test_export_pack_bundle_includes_done_short_exports_with_block_range_name(client, short_export_project, tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    pid = short_export_project["project"]["id"]
    channel_id = short_export_project["channel"]["id"]
    shot_ids = short_export_project["shot_ids"]
    _mark_shot_ready_real(ffmpeg, pid, channel_id, shot_ids[0], color="red", is_video=False)

    resp = client.post(f"/projects/{pid}/render/short-export", json={"start_block_id": "B01", "end_block_id": "B01"})
    export_id = resp.json()["short_exports"][0]["id"]
    # `client.post` (Starlette TestClient) chạy xong `BackgroundTasks` TRƯỚC KHI trả lại
    # điều khiển cho test, nhưng response JSON được dựng TRƯỚC bước đó (còn "pending") —
    # đọc lại `render.json` từ đĩa mới thấy trạng thái THẬT sau khi pipeline chạy xong.
    pdir = project_dir(channel_id, pid)
    export = next(e for e in RenderState(**read_json(pdir / "render.json")).short_exports if e.id == export_id)
    assert export.status == "done", export.error

    dest_dir = tmp_path / "bundle"
    resp = client.post(f"/projects/{pid}/export/pack-bundle", json={"dest_dir": str(dest_dir)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "short_B01-B01_vi.mp4" in body["included"]
    assert (dest_dir / "short_B01-B01_vi.mp4").exists()
