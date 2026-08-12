"""Test hành vi khi KHÔNG có Provider AI nào cấu hình cho task 'llm' — app phải báo
lỗi rõ ràng (400, thông điệp hướng dẫn vào Cài đặt), KHÔNG âm thầm dùng Mock provider
thay thế (đổi theo yêu cầu người dùng — xem app/providers/factory.py
NoProviderConfiguredError, IMPLEMENTATION_REPORT.md).

Mỗi test tự xoá hết provider LLM hiện có (do fixture `_ensure_mock_llm_is_default`
trong conftest.py tạo sẵn) rồi mới thao tác — fixture đó sẽ tự tạo lại provider Mock
cho các test SAU, nên không cần tự khôi phục ở cuối.
"""
import io


def _delete_all_llm_providers(client):
    for p in client.get("/providers").json():
        if p["task"] == "llm":
            client.delete(f"/providers/{p['id']}")


def test_bootstrap_reports_no_llm_provider(client):
    _delete_all_llm_providers(client)
    resp = client.get("/bootstrap")
    assert resp.status_code == 200
    assert resp.json()["has_llm_provider"] is False


def test_research_fails_clearly_without_provider(client, project_with_brief):
    _delete_all_llm_providers(client)
    resp = client.post(f"/projects/{project_with_brief['id']}/research")
    assert resp.status_code == 400
    assert "Cài đặt" in resp.json()["detail"]
    assert "Provider AI" in resp.json()["detail"]


def test_gate1_fails_clearly_without_provider(client, project_with_brief):
    pid = project_with_brief["id"]
    research = client.post(f"/projects/{pid}/research").json()
    outline_id = research["research"]["outlines"][0]["id"]
    hook_id = research["hooks"][0]["id"]

    _delete_all_llm_providers(client)
    resp = client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": outline_id, "chosen_hook_id": hook_id})
    assert resp.status_code == 400
    assert "Provider AI" in resp.json()["detail"]


def test_guardrail_check_fails_only_when_hook_present_without_provider(client, project_with_brief):
    """Script từ AI (có hook) -> guardrail cần Provider AI để chấm Hook Strength.
    Script từ import (hook rỗng) -> KHÔNG cần Provider AI (test riêng bên dưới)."""
    pid = project_with_brief["id"]
    research = client.post(f"/projects/{pid}/research").json()
    outline_id = research["research"]["outlines"][0]["id"]
    hook_id = research["hooks"][0]["id"]
    client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": outline_id, "chosen_hook_id": hook_id})
    client.post(f"/projects/{pid}/script/approve")

    _delete_all_llm_providers(client)
    resp = client.post(f"/projects/{pid}/guardrail/check")
    assert resp.status_code == 400
    assert "Provider AI" in resp.json()["detail"]


def test_import_confirm_works_without_any_provider(client, project):
    """Script nhập từ CSV không có hook -> guardrail không cần chấm Hook Strength ->
    không cần Provider AI. Visual Studio cũng seed thẳng từ nội dung import, không gọi
    AI. Toàn bộ luồng import phải chạy được kể cả khi CHƯA cấu hình provider nào."""
    pid = project["id"]
    _delete_all_llm_providers(client)

    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    row = ["B01", "0:00–0:05", "Video", "Cảnh mở", "Nhạc nền", "Xin chào các bạn."]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, row])).encode("utf-8")

    parsed = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")})
    assert parsed.status_code == 200
    preview = parsed.json()

    confirm = client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200
    assert confirm.json()["retention_check"] is not None

    visual = client.post(f"/projects/{pid}/visual/generate")
    assert visual.status_code == 200
    assert visual.json()["shots"][0]["visual_fx"] == "Cảnh mở"


def test_pack_build_fails_without_provider_even_for_import(client, project):
    """Title/Description/Thumbnail LUÔN cần AI dù script từ import hay AI-generated —
    khác guardrail (chỉ cần AI khi có hook)."""
    pid = project["id"]
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    row = ["B01", "0:00–0:05", "Video", "Cảnh mở", "Nhạc nền", "Xin chào các bạn."]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, row])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    client.post(f"/projects/{pid}/visual/generate")

    _delete_all_llm_providers(client)
    resp = client.post(f"/projects/{pid}/pack/build")
    assert resp.status_code == 400
    assert "Provider AI" in resp.json()["detail"]


def test_visual_generate_ai_path_fails_without_provider(client, project_with_brief):
    """Script từ AI (không phải import) -> /visual/generate PHẢI gọi AI -> cần provider."""
    pid = project_with_brief["id"]
    research = client.post(f"/projects/{pid}/research").json()
    outline_id = research["research"]["outlines"][0]["id"]
    hook_id = research["hooks"][0]["id"]
    client.post(f"/projects/{pid}/gate1", json={"chosen_outline_id": outline_id, "chosen_hook_id": hook_id})
    client.post(f"/projects/{pid}/script/approve")

    _delete_all_llm_providers(client)
    resp = client.post(f"/projects/{pid}/visual/generate")
    assert resp.status_code == 400
    assert "Provider AI" in resp.json()["detail"]
