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

    resp = client.post(f"/projects/{pid}/visual/shots/{shot_id}/regenerate-visual")
    assert resp.status_code == 200
    assert resp.json()["shots"][0]["visual_fx"]

    resp = client.post(f"/projects/{pid}/visual/shots/{shot_id}/regenerate-audio")
    assert resp.status_code == 200
    assert resp.json()["shots"][0]["audio_sfx"]

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
