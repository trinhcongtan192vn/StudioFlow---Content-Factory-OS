import io


def test_create_and_list_channel(client, unique_name):
    resp = client.post("/channels", json={"name": f"Kênh {unique_name}", "niche": "Lịch sử"})
    assert resp.status_code == 200
    ch = resp.json()
    assert ch["name"] == f"Kênh {unique_name}"
    assert ch["niche"] == "Lịch sử"
    assert ch["brandprofile_version"] == 1
    assert ch["running_count"] == 0

    resp = client.get("/channels")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ch["id"] in ids


def test_get_channel_includes_brand_profile(client, channel):
    resp = client.get(f"/channels/{channel['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["brand_profile"]["channel_id"] == channel["id"]
    assert data["brand_profile"]["version"] == 1


def test_get_channel_404(client):
    resp = client.get("/channels/does_not_exist")
    assert resp.status_code == 404


def test_patch_channel_rename_and_archive(client, channel):
    resp = client.patch(f"/channels/{channel['id']}", json={"name": "Đổi tên rồi"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Đổi tên rồi"

    resp = client.patch(f"/channels/{channel['id']}", json={"archived": True})
    assert resp.status_code == 200
    assert resp.json()["archived"] is True

    # kênh archived không còn xuất hiện trong danh sách
    resp = client.get("/channels")
    ids = [c["id"] for c in resp.json()]
    assert channel["id"] not in ids


def test_brandprofile_get_put_versioning(client, channel):
    resp = client.get(f"/channels/{channel['id']}/brandprofile")
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["version"] == 1

    profile["brand_voice"]["tone"] = "Giọng mới sau khi sửa"
    profile["forbidden"] = ["từ cấm A", "từ cấm B"]
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile)
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["version"] == 2
    assert updated["brand_voice"]["tone"] == "Giọng mới sau khi sửa"
    assert updated["forbidden"] == ["từ cấm A", "từ cấm B"]

    # đọc lại phải thấy bản mới nhất
    resp = client.get(f"/channels/{channel['id']}/brandprofile")
    assert resp.json()["version"] == 2

    resp = client.get(f"/channels/{channel['id']}/brandprofile/versions")
    assert resp.status_code == 200
    versions = [v["version"] for v in resp.json()]
    assert 1 in versions and 2 in versions


def test_new_channel_brandprofile_has_blank_motion_tone_and_cultural_lock_negative(client, unique_name):
    """Bug thật (2026-09-02, user báo) — `motion_tone`/`cultural_lock_negative` TỪNG có
    default không rỗng ghim sẵn trong schema (gợi ý "chậm, tinh tế"/loại trừ Nhật-Hàn) —
    kênh MỚI TẠO hiện sẵn giá trị dù người dùng chưa từng nhập gì, trông như đã có dữ liệu.
    Đổi default schema về rỗng — cụm gợi ý cũ chuyển thành placeholder ở frontend, không
    còn là giá trị thật."""
    resp = client.post("/channels", json={"name": f"Kênh trống {unique_name}", "niche": "Test"})
    ch = resp.json()
    profile = client.get(f"/channels/{ch['id']}/brandprofile").json()
    assert profile["motion_tone"] == ""
    assert profile["cultural_lock_negative"] == ""


def test_put_brandprofile_persists_cleared_motion_tone_and_cultural_lock_negative(client, channel):
    """Bug thật (2026-09-02, user tự test) — xoá trắng 2 field này rồi lưu, mở lại vẫn
    thấy giá trị cũ. Root cause thật ra ở FRONTEND (`ChannelDialog.tsx::draftFromProfile`
    dùng `bp.field || "<default cũ>"`, coi chuỗi rỗng ĐÃ LƯU giống hệt "chưa có giá trị" —
    xem IMPLEMENTATION_REPORT.md mục 104) — test này verify riêng phần BACKEND (được hỏi
    trong lúc điều tra: PUT full-replace có DROP chuỗi rỗng không?) — xác nhận KHÔNG, PUT
    lưu ĐÚNG chuỗi rỗng, GET đọc lại ĐÚNG chuỗi rỗng."""
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["motion_tone"] = "chuyển động chậm, tinh tế"
    profile["cultural_lock_negative"] = "japanese kimono"
    client.put(f"/channels/{channel['id']}/brandprofile", json=profile)

    profile2 = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile2["motion_tone"] = ""
    profile2["cultural_lock_negative"] = ""
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile2)
    assert resp.status_code == 200
    assert resp.json()["motion_tone"] == ""
    assert resp.json()["cultural_lock_negative"] == ""

    reloaded = client.get(f"/channels/{channel['id']}/brandprofile").json()
    assert reloaded["motion_tone"] == ""
    assert reloaded["cultural_lock_negative"] == ""


def test_clone_brandprofile(client, channel, unique_name):
    # sửa brandprofile nguồn để có nội dung phân biệt được
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["visual_style_prompt"] = "phong cách đặc trưng để clone"
    client.put(f"/channels/{channel['id']}/brandprofile", json=profile)

    dest = client.post("/channels", json={"name": f"Kênh đích {unique_name}", "niche": ""}).json()
    resp = client.post(f"/channels/{dest['id']}/brandprofile/clone-from/{channel['id']}")
    assert resp.status_code == 200
    cloned = resp.json()
    assert cloned["visual_style_prompt"] == "phong cách đặc trưng để clone"
    assert cloned["channel_id"] == dest["id"]


# ---------------------------------------------------------------------------
# Logo kênh — mới (2026-08-22), theo yêu cầu người dùng
# ---------------------------------------------------------------------------
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def test_upload_brand_logo_sets_logo_path(client, channel):
    resp = client.post(f"/channels/{channel['id']}/brandprofile/logo/upload", files={"file": ("logo.png", io.BytesIO(FAKE_PNG), "image/png")})
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["logo_path"]

    fetched = client.get(f"/channels/{channel['id']}/brandprofile").json()
    assert fetched["logo_path"] == profile["logo_path"]


def test_upload_brand_logo_rejects_unknown_file_type(client, channel):
    resp = client.post(f"/channels/{channel['id']}/brandprofile/logo/upload", files={"file": ("logo.txt", io.BytesIO(b"khong phai anh"), "text/plain")})
    assert resp.status_code == 400


def test_get_brand_logo_404_when_none(client, channel):
    resp = client.get(f"/channels/{channel['id']}/brandprofile/logo")
    assert resp.status_code == 404


def test_get_brand_logo_serves_uploaded_file(client, channel):
    client.post(f"/channels/{channel['id']}/brandprofile/logo/upload", files={"file": ("logo.png", io.BytesIO(FAKE_PNG), "image/png")})
    resp = client.get(f"/channels/{channel['id']}/brandprofile/logo")
    assert resp.status_code == 200
    assert resp.content == FAKE_PNG


def test_upload_brand_logo_replaces_old_file(client, channel):
    first = client.post(f"/channels/{channel['id']}/brandprofile/logo/upload", files={"file": ("logo.png", io.BytesIO(FAKE_PNG), "image/png")}).json()
    from pathlib import Path

    first_path = Path(first["logo_path"])
    assert first_path.exists()

    other_png = b"\x89PNG\r\n\x1a\n" + b"1" * 30
    second = client.post(f"/channels/{channel['id']}/brandprofile/logo/upload", files={"file": ("logo2.jpg", io.BytesIO(other_png), "image/jpeg")}).json()
    assert second["logo_path"] != first["logo_path"]
    assert not first_path.exists()  # file cũ (khác đuôi) phải bị xoá, không để rác

    resp = client.get(f"/channels/{channel['id']}/brandprofile/logo")
    assert resp.content == other_png


def test_clear_brand_logo_via_put(client, channel):
    """Bỏ logo — PUT lại BrandProfile với field rỗng (cùng pattern voice-sample/intro),
    không cần route xoá riêng."""
    client.post(f"/channels/{channel['id']}/brandprofile/logo/upload", files={"file": ("logo.png", io.BytesIO(FAKE_PNG), "image/png")})
    profile = client.get(f"/channels/{channel['id']}/brandprofile").json()
    profile["logo_path"] = ""
    resp = client.put(f"/channels/{channel['id']}/brandprofile", json=profile)
    assert resp.status_code == 200
    assert resp.json()["logo_path"] == ""
    assert client.get(f"/channels/{channel['id']}/brandprofile/logo").status_code == 404
