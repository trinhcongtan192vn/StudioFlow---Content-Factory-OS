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
    assert len(templates) >= 9  # PROMPT_SEED trong app/seed.py
    outline_tpl = next(t for t in templates if t["task"] == "outline")
    assert outline_tpl["body"]  # active version phải có nội dung
    assert len(outline_tpl["versions"]) >= 1


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


def test_budget_detail_groups_after_pipeline_usage(client, project_with_brief):
    """Chạy 1 bước pipeline thật (provider Mock, cost=0 nhưng vẫn ghi log request) rồi
    kiểm tra budget detail group đúng theo project/provider (bug đã sửa: record_usage
    + endpoint /budget/{id}/detail)."""
    pid = project_with_brief["id"]
    channel_id = project_with_brief["channel_id"]

    r1 = client.post(f"/projects/{pid}/research")
    assert r1.status_code == 200, r1.text
    research = r1.json()
    outline_id = research["research"]["outlines"][0]["id"]
    hook_id = research["hooks"][0]["id"]
    r2 = client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": outline_id, "chosen_hook_id": hook_id})
    assert r2.status_code == 200, r2.text

    resp = client.get(f"/budget/{channel_id}/detail")
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert len(rows) >= 1
    assert rows[0]["provider"] == "LLM"
    assert rows[0]["request_count"] >= 1
