def test_create_and_list_channel(client, unique_name):
    resp = client.post("/channels", json={"name": f"Kênh {unique_name}", "niche": "Lịch sử"})
    assert resp.status_code == 200
    ch = resp.json()
    assert ch["name"] == f"Kênh {unique_name}"
    assert ch["niche"] == "Lịch sử"
    assert ch["brandprofile_version"] == 1
    assert ch["running_count"] == 0
    assert ch["review_count"] == 0

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
