def test_get_settings_defaults(client):
    resp = client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "general" in data and "ai_params" in data and "app_branding" in data
    assert data["general"]["org_name"]
    assert data["ai_params"]["framework"] in ("AIDA", "PAS")


def test_put_settings_updates_general_and_branding(client):
    resp = client.put(
        "/settings",
        json={
            "general": {"org_name": "Studio Test", "language": "vi", "timezone": "Asia/Ho_Chi_Minh", "export_format": "markdown", "naming_convention": "x"},
            "app_branding": {"name": "Studio Test", "accent_swatch": 2},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["general"]["org_name"] == "Studio Test"
    assert resp.json()["app_branding"]["accent_swatch"] == 2

    # đọc lại phải giữ giá trị mới
    resp = client.get("/settings")
    assert resp.json()["general"]["org_name"] == "Studio Test"


def test_put_settings_ai_params(client):
    resp = client.put("/settings", json={"ai_params": {"temperature": 0.9, "length": "6-10 phút", "hook_count": 5, "framework": "PAS"}})
    assert resp.status_code == 200
    assert resp.json()["ai_params"]["framework"] == "PAS"


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------
def test_list_prompt_templates_seeded(client):
    resp = client.get("/prompt-templates")
    assert resp.status_code == 200
    templates = resp.json()
    # 3 template còn lại sau khi bỏ AI Research/Outline/Hook/Full-Script + Pack Review
    # (2026-08-17, mục 44) — chỉ còn nhóm Visual Studio (ảnh/video/giọng đọc từng shot).
    assert len(templates) >= 3  # PROMPT_SEED trong app/seed.py
    visual_tpl = next(t for t in templates if t["task"] == "visual_image")
    assert visual_tpl["body"]  # active version phải có nội dung
    assert len(visual_tpl["versions"]) >= 1


def test_create_prompt_template(client, unique_name):
    resp = client.post("/prompt-templates", json={"name": f"Template {unique_name}", "task": "brief", "body": "Nội dung prompt v1"})
    assert resp.status_code == 200
    t = resp.json()
    assert t["active_version"] == "v1"
    assert t["body"] == "Nội dung prompt v1"
    assert len(t["versions"]) == 1


def test_patch_prompt_template_rename_and_change_task(client, unique_name):
    t = client.post("/prompt-templates", json={"name": f"T {unique_name}", "task": "brief", "body": "abc"}).json()
    resp = client.patch(f"/prompt-templates/{t['id']}", json={"name": "Đổi tên", "task": "thumbnail"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Đổi tên"
    assert resp.json()["task"] == "thumbnail"


def test_patch_prompt_template_new_version_and_set_active(client, unique_name):
    t = client.post("/prompt-templates", json={"name": f"T {unique_name}", "task": "brief", "body": "v1 body"}).json()

    resp = client.patch(f"/prompt-templates/{t['id']}", json={"new_version_body": "v2 body", "new_version_note": "cải tiến"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_version"] == "v2"
    assert data["body"] == "v2 body"
    assert len(data["versions"]) == 2

    resp = client.patch(f"/prompt-templates/{t['id']}", json={"active_version": "v1"})
    assert resp.status_code == 200
    assert resp.json()["active_version"] == "v1"
    assert resp.json()["body"] == "v1 body"


def test_delete_prompt_template_404(client):
    resp = client.delete("/prompt-templates/does-not-exist")
    assert resp.status_code == 404


def test_delete_prompt_template(client, unique_name):
    t = client.post("/prompt-templates", json={"name": f"T {unique_name}", "task": "brief", "body": "abc"}).json()
    resp = client.delete(f"/prompt-templates/{t['id']}")
    assert resp.status_code == 200
    ids = [x["id"] for x in client.get("/prompt-templates").json()]
    assert t["id"] not in ids


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def test_audit_log_records_and_filters_by_type(client, unique_name):
    client.post("/channels", json={"name": f"Audit test {unique_name}", "niche": ""})
    resp = client.get("/audit-log")
    assert resp.status_code == 200
    log = resp.json()
    assert any(a["action"] == "Tạo kênh" for a in log)

    resp = client.get("/audit-log?type=system")
    assert all(a["type"] == "system" for a in resp.json())


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------
def test_budget_list_autocreates_row_per_channel(client, channel):
    resp = client.get("/budget")
    assert resp.status_code == 200
    row = next(b for b in resp.json() if b["channel_id"] == channel["id"])
    assert row["soft_limit"] == 8
    assert row["threshold_pct"] == 60
    assert row["spent"] == 0


def test_budget_patch_soft_limit_and_threshold(client, channel):
    resp = client.patch(f"/budget/{channel['id']}", json={"soft_limit": 15, "threshold_pct": 80})
    assert resp.status_code == 200
    data = resp.json()
    assert data["soft_limit"] == 15
    assert data["threshold_pct"] == 80

    row = next(b for b in client.get("/budget").json() if b["channel_id"] == channel["id"])
    assert row["soft_limit"] == 15


def test_budget_over_threshold_flag(client, channel):
    client.patch(f"/budget/{channel['id']}", json={"soft_limit": 1, "threshold_pct": 10})
    # spent vẫn 0 nên chưa vượt ngưỡng (0/1*100=0 < 10)
    row = next(b for b in client.get("/budget").json() if b["channel_id"] == channel["id"])
    assert row["over_threshold"] is False


def test_budget_detail_empty_when_no_expense(client, channel):
    resp = client.get(f"/budget/{channel['id']}/detail")
    assert resp.status_code == 200
    data = resp.json()
    assert data["channel_name"] == channel["name"]
    assert data["rows"] == []


def test_budget_detail_groups_after_pipeline_usage(client, project_with_brief, monkeypatch):
    """Chạy 1 bước pipeline thật (provider Mock, cost=0 nhưng vẫn ghi log request) rồi
    kiểm tra budget detail group đúng theo project/provider (bug đã sửa: record_usage
    + endpoint /budget/{id}/detail).

    2026-08-17 (mục 44): đường cũ dùng /research + /gate1 để có usage LLM — cả 2 đã bỏ
    cùng AI Research/Outline/Hook. **Đổi lại 2026-08-25**: "Tạo lại Visual"
    (`regenerate-visual`) từng dùng để tạo 1 lượt usage LLM thật, nhưng theo yêu cầu
    người dùng endpoint đó giờ CHỈ khôi phục nguyên si từ script gốc, KHÔNG còn gọi LLM
    (xem `app/pipeline/generation.py`) — LLM giờ chỉ còn được gọi ở nhánh Hook Strength
    của `run_guardrail_check` (`app/guardrail/check.py`), CHỈ chạy khi `pack.script.
    hook.spoken` khác rỗng (script import không tự điền field này — AI Hook Variants đã
    bỏ) — set trực tiếp field đó lên đĩa rồi gọi `POST /guardrail/check` (chạy lại thủ
    công), đúng con đường THẬT duy nhất còn lại trong app hiện gọi tới LLM.

    `score_hook_strength()` (`app/guardrail/check.py`) CHỈ record usage khi response
    parse được thành JSON `{"hook_strength": ...}` — `MockLLMProvider` (seed mặc định
    của test client) LUÔN trả văn xuôi placeholder, KHÔNG BAO GIỜ ra JSON hợp lệ (xác
    nhận đúng hành vi đã ghi ở `test_guardrail.py::
    test_score_hook_strength_mock_provider_uses_fallback` — rơi vào fallback heuristic,
    không phải bug) — phải monkeypatch `MockLLMProvider.complete` trả JSON hợp lệ để
    exercise được đúng nhánh ghi usage qua HTTP thật (khác `test_guardrail.py`, nơi gọi
    thẳng hàm Python với provider giả `_JsonLLM`, không qua router/DB)."""
    import io

    from app.config import project_dir
    from app.filestore import read_json, write_json
    from app.providers.base import LLMResult
    from app.providers.mock import MockLLMProvider

    def _fake_complete(self, system, messages, *, temperature=0.7, max_tokens=4000):
        return LLMResult(text='{"hook_strength": 0.6, "reasons": ["test"]}', input_tokens=10, output_tokens=10, estimated_cost_usd=0.0, model=self.model_name)

    monkeypatch.setattr(MockLLMProvider, "complete", _fake_complete)

    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    row = ["B01", "0:00–0:05", "Image", "Cảnh mở", "Nhạc nền", "Xin chào các bạn."]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, row])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    client.post(f"/projects/{pid}/visual/generate")

    pdir = project_dir(channel_id, pid)
    pack = read_json(pdir / "pack.json")
    pack["script"]["hook"]["spoken"] = "Bạn có biết điều này chưa?"
    write_json(pdir / "pack.json", pack)

    r1 = client.post(f"/projects/{pid}/guardrail/check")
    assert r1.status_code == 200, r1.text
    assert r1.json()["hook_strength"] == 0.6

    resp = client.get(f"/budget/{channel_id}/detail")
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert len(rows) >= 1
    assert rows[0]["provider"] == "LLM"
    assert rows[0]["request_count"] >= 1
