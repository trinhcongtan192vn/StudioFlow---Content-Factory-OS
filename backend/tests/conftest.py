"""Fixture chung cho test suite.

Cách ly hoàn toàn khỏi workspace/ thật của app (không đụng dữ liệu người dùng đang
test thủ công): trỏ STUDIOFLOW_WORKSPACE sang thư mục tạm TRƯỚC khi bất kỳ module
`app.*` nào được import — app/config.py đọc biến môi trường này ở mức module-level
nên phải set trước import đầu tiên.

DB + seed dùng chung cho cả session test (session-scoped) — không refactor app sang
dependency injection chỉ để phục vụ test cách ly triệt để từng hàm; đổi lại, test
nào tạo dữ liệu riêng thì tự đặt tên duy nhất (uuid) để không đụng nhau.
"""
import os
import shutil
import tempfile
import uuid
from pathlib import Path

_TEST_WORKSPACE = Path(tempfile.mkdtemp(prefix="studioflow_test_"))
os.environ["STUDIOFLOW_WORKSPACE"] = str(_TEST_WORKSPACE)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402  (import sau khi set env — trigger create_all + seed)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
    shutil.rmtree(_TEST_WORKSPACE, ignore_errors=True)


@pytest.fixture(autouse=True)
def _ensure_mock_llm_is_default(client):
    """DB dùng chung cho cả session test (xem docstring module) — nếu 1 test nào đó
    đổi provider LLM mặc định (vd. test_patch_provider_set_default_unsets_others) mà
    quên khôi phục, các test khác gọi pipeline thật sẽ âm thầm rơi vào fallback content
    (network lỗi với key giả) thay vì dùng Mock, khiến usage/audit log không được ghi —
    lỗi khó nhìn ra vì API vẫn trả 200. Fixture này chạy trước MỌI test, đảm bảo Mock
    luôn là default cho task 'llm' bất kể thứ tự/test khác làm gì."""
    providers = client.get("/providers").json()
    mock = next((p for p in providers if p["provider_name"] == "mock"), None)
    if mock and not mock["is_default"]:
        client.patch(f"/providers/{mock['id']}", json={"is_default": True})
    yield


@pytest.fixture()
def unique_name():
    """Chuỗi ngẫu nhiên ngắn để đặt tên kênh/project không đụng test khác."""
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def channel(client, unique_name):
    """Tạo 1 kênh mới, trả về dict {id, name, ...} — mỗi test có kênh riêng."""
    resp = client.post("/channels", json={"name": f"Test Channel {unique_name}", "niche": "Test"})
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture()
def project(client, channel):
    """Tạo 1 project draft trong `channel`, trả về dict project."""
    resp = client.post(f"/channels/{channel['id']}/projects", json={"title": "Test Project"})
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture()
def project_with_brief(client, project):
    """Project đã có brief đủ điều kiện chạy Research (topic/insight/audience/goal)."""
    body = {
        "project_id": project["id"],
        "channel_id": project["channel_id"],
        "topic": "Chủ đề test",
        "insight": "Insight test",
        "strategy": {"content_matrix_slot": "", "growth_objective": "Tăng tương tác", "conversion_point": "none"},
        "audience": {"seo_keywords": [], "retention_notes": "", "pain_points": ["mất thời gian"], "description": "Khán giả test"},
        "raw_knowledge": {"documents": [], "expert_notes": "", "key_message": ""},
        "conversion_note": "",
        "brand_voice_override": None,
    }
    resp = client.put(f"/projects/{project['id']}/brief", json=body)
    assert resp.status_code == 200
    return project
