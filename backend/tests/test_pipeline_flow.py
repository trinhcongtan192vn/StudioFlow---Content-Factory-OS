"""Test tích hợp toàn bộ pipeline — dùng provider Mock mặc định (seed), không cần
mạng/API key. Viết liền mạch như 1 luồng sử dụng thật: Brief → Upload script → Script
Studio → Visual Studio → Output.

2026-08-17 (mục 44 IMPLEMENTATION_REPORT.md): bỏ hẳn luồng AI Research/Outline/Hook/
Full-Script + Pack Review/Gate #2 theo yêu cầu người dùng — "upload script" (CSV/Excel
import) giờ là con đường DUY NHẤT để có script, không còn gate duyệt bắt buộc nào
trước khi vào Output."""
import io


def test_full_pipeline_happy_path(client, project_with_brief):
    pid = project_with_brief["id"]

    # ---- Upload script (con đường duy nhất để có script) ----
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:08", "Image", "Cảnh mở, tông ấm", "Nhạc nền nhẹ", "Xin chào các bạn, hôm nay chúng ta sẽ nói về một chủ đề thú vị."],
        ["B02", "0:08–0:16", "Video", "Cận cảnh, nhịp nhanh", "Nhạc nền dồn dập", "Điều đầu tiên cần biết là mọi thứ đều bắt đầu từ một quyết định nhỏ."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    parsed = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")})
    assert parsed.status_code == 200
    preview = parsed.json()

    resp = client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert resp.status_code == 200
    pack = resp.json()
    body = pack["script"]["body"]
    assert len(body) == 2
    assert pack["script"]["source"] == "import"
    assert pack["retention_check"] is not None
    assert pack["retention_check"]["max_anchor_gap_sec"] is not None

    proj = client.get(f"/projects/{pid}").json()
    assert proj["step"] == 1
    assert proj["max_step_reached"] == 1
    assert proj["status"] == "generating"

    # ---- Sửa tay 1 block (index-based, sau khi đã bóc tách) ----
    resp = client.patch(f"/projects/{pid}/script/body/0/audio", json={"audio": "Câu mở đầu đã sửa tay."})
    assert resp.status_code == 200
    assert resp.json()["script"]["body"][0]["audio"] == "Câu mở đầu đã sửa tay."

    # ---- Visual Studio ----
    resp = client.post(f"/projects/{pid}/visual/generate")
    assert resp.status_code == 200
    pack = resp.json()
    shots = pack["shots"]
    assert len(shots) == len(body)
    proj = client.get(f"/projects/{pid}").json()
    assert proj["step"] == 2

    shot_id = shots[0]["shot_id"]
    resp = client.patch(f"/projects/{pid}/visual/shots/{shot_id}", json={"visual_fx": "prompt sửa tay", "audio_sfx": "ấm áp"})
    assert resp.status_code == 200
    updated_shot = next(s for s in resp.json()["shots"] if s["shot_id"] == shot_id)
    assert updated_shot["visual_fx"] == "prompt sửa tay"
    assert updated_shot["audio_sfx"] == "ấm áp"

    # "Tạo lại Visual/Audio" — 2026-08-25, theo yêu cầu người dùng: KHÔNG còn gọi LLM,
    # khôi phục NGUYÊN SI về đúng script gốc (bỏ bản sửa tay "prompt sửa tay"/"ấm áp" ở
    # trên, quay lại đúng "Cảnh mở, tông ấm"/"Nhạc nền nhẹ" — cột Visual/FX + Audio/SFX
    # gốc của block B01 trong CSV import).
    resp = client.post(f"/projects/{pid}/visual/shots/{shot_id}/regenerate-visual")
    assert resp.status_code == 200
    assert resp.json()["shots"][0]["visual_fx"] == "Cảnh mở, tông ấm"

    resp = client.post(f"/projects/{pid}/visual/shots/{shot_id}/regenerate-audio")
    assert resp.status_code == 200
    assert resp.json()["shots"][0]["audio_sfx"] == "Nhạc nền nhẹ"

    resp = client.post(f"/projects/{pid}/visual/generate-all-visual")
    assert resp.status_code == 200
    resp = client.post(f"/projects/{pid}/visual/generate-all-tts")
    assert resp.status_code == 200

    resp = client.patch(f"/projects/{pid}/visual/shots/khong-ton-tai", json={"visual_fx": "x"})
    assert resp.status_code == 404

    resp = client.post(f"/projects/{pid}/visual/shots/khong-ton-tai/regenerate-visual")
    assert resp.status_code == 404

    # ---- Guardrail check thủ công (chạy lại sau khi sửa, §08 mục 5) ----
    resp = client.post(f"/projects/{pid}/guardrail/check")
    assert resp.status_code == 200
    check = resp.json()
    assert "hook_strength" in check and "warnings" in check

    # ---- Output: KHÔNG còn gate duyệt nào chặn trước — vào thẳng được ----
    resp = client.post(f"/projects/{pid}/output/enter")
    assert resp.status_code == 200
    proj = client.get(f"/projects/{pid}").json()
    assert proj["step"] == 3
    assert proj["status"] == "ready_output"

    resp = client.post(f"/projects/{pid}/export", json={"format": "markdown"})
    assert resp.status_code == 200
    filename = resp.json()["filename"]
    assert filename.endswith(".md")

    resp = client.get(f"/projects/{pid}/exports/{filename}")
    assert resp.status_code == 200
    assert len(resp.content) > 0

    resp = client.post(f"/projects/{pid}/export", json={"format": "json"})
    assert resp.status_code == 200

    resp = client.post(f"/projects/{pid}/export", json={"format": "invalid-format"})
    assert resp.status_code == 400


def test_regenerate_visual_errors_when_script_beat_has_no_visual_description(client, project_with_brief):
    """2026-08-25, theo yêu cầu người dùng: "Tạo lại Visual" không còn LLM để "bịa" ra
    mô tả khi script gốc không có gì — phải báo lỗi rõ ràng (400) thay vì rơi về 1 câu
    fallback vô nghĩa như thiết kế cũ."""
    pid = project_with_brief["id"]
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    row = ["B01", "0:00–0:05", "Image", "", "", "Xin chào các bạn."]  # Visual/FX + Audio/SFX đều RỖNG
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, row])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    shot_id = client.post(f"/projects/{pid}/visual/generate").json()["shots"][0]["shot_id"]

    resp = client.post(f"/projects/{pid}/visual/shots/{shot_id}/regenerate-visual")
    assert resp.status_code == 400

    resp = client.post(f"/projects/{pid}/visual/shots/{shot_id}/regenerate-audio")
    assert resp.status_code == 400


def test_generate_all_visual_skips_shots_with_no_script_description_instead_of_erroring(client, project_with_brief):
    """Bulk "Tạo Visual cho toàn bộ block" KHÁC shot lẻ ở test trên — shot thiếu mô tả
    BỊ BỎ QUA (giữ nguyên `visual_fx` hiện có), KHÔNG chặn cả batch chỉ vì 1 shot rỗng."""
    pid = project_with_brief["id"]
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    rows = [
        ["B01", "0:00–0:05", "Image", "Cảnh có mô tả", "Nhạc nhẹ", "Câu một."],
        ["B02", "0:05–0:10", "Image", "", "", "Câu hai."],
    ]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    client.post(f"/projects/{pid}/visual/generate")

    resp = client.post(f"/projects/{pid}/visual/generate-all-visual")
    assert resp.status_code == 200
    shots = resp.json()["shots"]
    assert shots[0]["visual_fx"] == "Cảnh có mô tả"
    assert shots[1]["visual_fx"] == ""  # shot B02 bị bỏ qua, giữ nguyên rỗng — không lỗi cả batch


def test_export_blocked_without_script(client, project):
    """Export không còn gate theo `project.status` (Gate #2 đã bỏ) — chỉ cần có script.
    Project mới tạo (chưa import/viết gì) chưa có script -> vẫn bị chặn, nhưng vì lý do
    khác (chưa có nội dung để xuất, không phải "chưa qua Gate #2")."""
    resp = client.post(f"/projects/{project['id']}/export", json={"format": "json"})
    assert resp.status_code == 400
    assert "script" in resp.json()["detail"].lower()


def test_guardrail_check_requires_body(client, project):
    resp = client.post(f"/projects/{project['id']}/guardrail/check")
    assert resp.status_code == 400


def test_visual_generate_requires_body(client, project):
    resp = client.post(f"/projects/{project['id']}/visual/generate")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# _ensure_shots — đồng bộ shot list theo `body` (đơn vị, không qua HTTP) — mới
# (2026-09-10, mục 131): bug thật "APPEND vào cuối" (fix mục 31) làm shot mới bị dồn
# CUỐI mảng thay vì đúng vị trí xen kẽ trong body khi re-import script thêm block RẢI
# RÁC (không phải toàn bộ ở cuối) — ảnh hưởng CẢ hiển thị Visual Studio LẪN thứ tự ghép
# video thật (assembly.py duyệt pack.shots đúng theo thứ tự mảng).
# ---------------------------------------------------------------------------
def test_ensure_shots_creates_shots_matching_body_order_when_empty():
    from app.routers.pipeline import _ensure_shots

    body = [{"block_id": "B01", "visual": "canh 1"}, {"block_id": "B02", "visual": "canh 2"}, {"block_id": "B03", "visual": "canh 3"}]
    shots = _ensure_shots({"shots": []}, body)
    assert [s["shot_id"] for s in shots] == ["B01", "B02", "B03"]


def test_ensure_shots_preserves_existing_shot_data_when_block_id_matches():
    """Shot ĐÃ có (đã sinh visual/narration) không bị tạo mới đè lên — GIỮ NGUYÊN object cũ,
    kể cả khi thứ tự trong `body` không đổi gì."""
    from app.routers.pipeline import _ensure_shots

    existing_shot = {"shot_id": "B01", "block_id": "B01", "visual_fx": "ĐÃ SỬA TAY", "provider": "local_qwen"}
    body = [{"block_id": "B01", "visual": "canh goc, khac voi shot da sua"}]
    shots = _ensure_shots({"shots": [existing_shot]}, body)
    assert shots == [existing_shot]
    assert shots[0]["visual_fx"] == "ĐÃ SỬA TAY"  # KHÔNG bị ghi đè lại từ body


def test_ensure_shots_inserts_new_interspersed_blocks_at_correct_position():
    """Bug thật mục 131 — re-import thêm block RẢI RÁC (không dồn cuối) giữa các block
    cũ đã có shot. Shot MỚI phải nằm ĐÚNG vị trí khớp `body`, không bị dồn hết xuống cuối
    mảng shots (hành vi SAI của fix mục 31, `existing + new_shots`)."""
    from app.routers.pipeline import _ensure_shots

    existing_shots = [{"shot_id": "B01", "block_id": "B01"}, {"shot_id": "B02", "block_id": "B02"}, {"shot_id": "B03", "block_id": "B03"}]
    # Re-import: chèn K1 giữa B01/B02, K2 giữa B02/B03 — đúng kiểu "rải rác" người dùng gặp thật.
    body = [{"block_id": "B01"}, {"block_id": "K1"}, {"block_id": "B02"}, {"block_id": "K2"}, {"block_id": "B03"}]
    shots = _ensure_shots({"shots": existing_shots}, body)
    assert [s["shot_id"] for s in shots] == ["B01", "K1", "B02", "K2", "B03"]
    # 2 shot cũ vẫn ĐÚNG OBJECT cũ (identity), không bị tạo lại.
    assert shots[0] is existing_shots[0]
    assert shots[2] is existing_shots[1]
    assert shots[4] is existing_shots[2]


def test_ensure_shots_preserves_orphaned_shot_when_block_removed_from_body():
    """Block bị xoá khỏi `body` lúc re-import (hiếm) — shot cũ (có thể đã sinh visual)
    KHÔNG bị xoá theo, chỉ không còn "đúng vị trí" nào để xếp vào — nối ở CUỐI, không mất
    dữ liệu đã sinh."""
    from app.routers.pipeline import _ensure_shots

    existing_shots = [{"shot_id": "B01", "block_id": "B01"}, {"shot_id": "B02", "block_id": "B02", "visual_asset_path": "da_sinh.png"}]
    body = [{"block_id": "B01"}]  # B02 không còn trong body
    shots = _ensure_shots({"shots": existing_shots}, body)
    assert [s["shot_id"] for s in shots] == ["B01", "B02"]
    assert shots[1]["visual_asset_path"] == "da_sinh.png"


def test_ensure_shots_idempotent_when_nothing_changed():
    from app.routers.pipeline import _ensure_shots

    existing_shots = [{"shot_id": "B01", "block_id": "B01"}, {"shot_id": "B02", "block_id": "B02"}]
    body = [{"block_id": "B01"}, {"block_id": "B02"}]
    shots = _ensure_shots({"shots": existing_shots}, body)
    assert shots == existing_shots
