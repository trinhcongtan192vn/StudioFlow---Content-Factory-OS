"""Test hành vi khi KHÔNG có Provider AI nào cấu hình cho task 'llm' — app phải báo
lỗi rõ ràng (400, thông điệp hướng dẫn vào Cài đặt), KHÔNG âm thầm dùng Mock provider
thay thế (đổi theo yêu cầu người dùng — xem app/providers/factory.py
NoProviderConfiguredError, IMPLEMENTATION_REPORT.md).

Mỗi test tự xoá hết provider LLM hiện có (do fixture `_ensure_mock_llm_is_default`
trong conftest.py tạo sẵn) rồi mới thao tác — fixture đó sẽ tự tạo lại provider Mock
cho các test SAU, nên không cần tự khôi phục ở cuối.

2026-08-17 (mục 44 IMPLEMENTATION_REPORT.md): bỏ hẳn luồng AI Research/Outline/Hook/
Full-Script + Pack Review/Gate #2 — các test riêng cho `/research`/`/gate1`/
`/guardrail/check` (nhánh có hook)/`/pack/titles-meta`/`/visual/generate` (nhánh AI)
đã XOÁ cùng lúc, vì các endpoint/nhánh đó không còn tồn tại. Script import (không cần
AI) giờ là con đường DUY NHẤT — test còn lại xác nhận đúng luồng đó chạy được không
cần provider nào.
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
