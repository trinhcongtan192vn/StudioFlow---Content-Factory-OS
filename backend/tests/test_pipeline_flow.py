"""Test tích hợp toàn bộ pipeline — dùng provider Mock mặc định (seed), không cần
mạng/API key. Mỗi bước phụ thuộc trạng thái bước trước, viết liền mạch như 1 luồng
sử dụng thật: Brief → Research → Gate1 → Script Studio → Visual Studio → Pack
Review → Gate2 (return rồi approve lại) → Output.
"""


def test_full_pipeline_happy_path(client, project_with_brief):
    pid = project_with_brief["id"]

    # ---- AI Research (gộp outline + hook, §03 đã build) ----
    resp = client.post(f"/projects/{pid}/research")
    assert resp.status_code == 200
    pack = resp.json()
    assert len(pack["research"]["outlines"]) >= 1
    assert len(pack["hooks"]) == 3
    assert pack["status"] == "await_gate1"

    proj = client.get(f"/projects/{pid}").json()
    assert proj["step"] == 1
    assert proj["max_step_reached"] == 1
    assert proj["status"] == "await_gate1"

    outline_id = pack["research"]["outlines"][0]["id"]
    hook_id = pack["hooks"][0]["id"]

    # ---- Human Gate #1 ----
    resp = client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": "sai", "chosen_hook_id": hook_id})
    assert resp.status_code == 400  # outline không hợp lệ phải bị chặn

    resp = client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": outline_id, "chosen_hook_id": hook_id, "edited_hook_text": "Hook đã chỉnh tay"})
    assert resp.status_code == 200
    pack = resp.json()
    assert pack["script"]["hook"]["spoken"] == "Hook đã chỉnh tay"
    assert len(pack["script"]["full_text"]) > 40
    assert pack["script"]["body"] == []

    proj = client.get(f"/projects/{pid}").json()
    assert proj["step"] == 2
    assert proj["status"] == "generating"

    # ---- Script Studio: sửa tay (auto-save), rồi tạo lại theo góp ý ----
    resp = client.patch(f"/projects/{pid}/script/text", json={"full_text": "Bản nháp người dùng tự sửa tay."})
    assert resp.status_code == 200
    assert resp.json()["script"]["full_text"] == "Bản nháp người dùng tự sửa tay."

    resp = client.post(f"/projects/{pid}/script/regenerate", json={"feedback": "Rút ngắn đoạn mở đầu"})
    assert resp.status_code == 200
    assert len(resp.json()["script"]["full_text"]) > 0

    # regenerate không cho gọi khi chưa có script (project khác, step 0)
    resp = client.post(f"/projects/{pid}/script/regenerate", json={"feedback": "x"})
    assert resp.status_code == 200  # vẫn có script từ trước, chỉ kiểm tra guard ở nơi khác

    # ---- Duyệt & bóc tách theo đoạn + guardrail inline ----
    resp = client.post(f"/projects/{pid}/script/approve")
    assert resp.status_code == 200
    pack = resp.json()
    body = pack["script"]["body"]
    assert len(body) >= 1
    assert all("timestamp_sec" in b for b in body)
    assert pack["retention_check"] is not None
    assert pack["retention_check"]["max_anchor_gap_sec"] is not None

    # ---- Visual Studio ----
    resp = client.post(f"/projects/{pid}/visual/generate")
    assert resp.status_code == 200
    pack = resp.json()
    shots = pack["shots"]
    assert len(shots) == len(body)
    proj = client.get(f"/projects/{pid}").json()
    assert proj["step"] == 3

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

    # ---- Pack Review (build title/thumbnail/youtube_meta + guardrail tổng hợp) ----
    resp = client.post(f"/projects/{pid}/pack/build")
    assert resp.status_code == 200
    pack = resp.json()
    assert len(pack["titles"]) >= 1
    assert pack["youtube_meta"]["description"]
    assert pack["status"] == "await_gate2"
    proj = client.get(f"/projects/{pid}").json()
    assert proj["step"] == 4

    # ---- Guardrail check thủ công (chạy lại sau khi sửa, §08 mục 5) ----
    resp = client.post(f"/projects/{pid}/guardrail/check")
    assert resp.status_code == 200
    check = resp.json()
    assert "hook_strength" in check and "warnings" in check

    # ---- Human Gate #2: Trả về trước (bắt buộc có note) ----
    resp = client.post(f"/projects/{pid}/gate2", json={"action": "return", "note": ""})
    assert resp.status_code == 400

    resp = client.post(f"/projects/{pid}/gate2", json={"action": "return", "note": "Hook chưa đủ mạnh"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["project"]["step"] == 2
    assert data["project"]["status"] == "generating"
    assert data["project"]["return_note"] == "Hook chưa đủ mạnh"

    proj = client.get(f"/projects/{pid}").json()
    assert proj["pack_version"] >= 2  # trả về phải tăng version, giữ lịch sử

    # ---- Đi lại từ Script Studio tới Gate 2, lần này Approve ----
    client.post(f"/projects/{pid}/script/approve")
    client.post(f"/projects/{pid}/visual/generate")
    client.post(f"/projects/{pid}/pack/build")

    resp = client.post(f"/projects/{pid}/gate2", json={"action": "invalid"})
    assert resp.status_code == 400

    resp = client.post(f"/projects/{pid}/gate2", json={"action": "approve"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["project"]["step"] == 5
    assert data["project"]["status"] == "ready_output"

    # ---- Output: enter + export ----
    resp = client.post(f"/projects/{pid}/output/enter")
    assert resp.status_code == 200

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


def test_export_blocked_before_gate2_approved(client, project):
    resp = client.post(f"/projects/{project['id']}/export", json={"format": "json"})
    assert resp.status_code == 400


def test_guardrail_check_requires_body(client, project):
    resp = client.post(f"/projects/{project['id']}/guardrail/check")
    assert resp.status_code == 400


def test_visual_generate_requires_body(client, project):
    resp = client.post(f"/projects/{project['id']}/visual/generate")
    assert resp.status_code == 400


def test_pack_build_requires_body(client, project):
    resp = client.post(f"/projects/{project['id']}/pack/build")
    assert resp.status_code == 400
