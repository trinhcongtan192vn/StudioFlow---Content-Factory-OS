"""Thùng rác — xoá (archive) kênh/project, khôi phục, xoá vĩnh viễn (DB + file trên đĩa)."""


def test_channel_delete_appears_in_trash_and_restore_removes_it(client, channel):
    resp = client.patch(f"/channels/{channel['id']}", json={"archived": True})
    assert resp.status_code == 200

    trash = client.get("/trash").json()
    ids = [c["id"] for c in trash["channels"]]
    assert channel["id"] in ids

    resp = client.post(f"/channels/{channel['id']}/restore")
    assert resp.status_code == 200
    assert resp.json()["archived"] is False

    trash = client.get("/trash").json()
    assert channel["id"] not in [c["id"] for c in trash["channels"]]
    assert channel["id"] in [c["id"] for c in client.get("/channels").json()]


def test_channel_permanent_delete_requires_archived_first(client, channel):
    resp = client.delete(f"/channels/{channel['id']}/permanent")
    assert resp.status_code == 400


def test_channel_permanent_delete_removes_db_and_files(client, channel):
    from app.config import CHANNELS_DIR

    real_dir = CHANNELS_DIR / channel["id"]
    assert real_dir.exists()

    client.patch(f"/channels/{channel['id']}", json={"archived": True})
    resp = client.delete(f"/channels/{channel['id']}/permanent")
    assert resp.status_code == 200

    assert client.get(f"/channels/{channel['id']}").status_code == 404
    trash = client.get("/trash").json()
    assert channel["id"] not in [c["id"] for c in trash["channels"]]
    assert not real_dir.exists()


def test_project_delete_appears_in_trash_with_channel_name_and_restore(client, project):
    resp = client.delete(f"/projects/{project['id']}")
    assert resp.status_code == 200

    trash = client.get("/trash").json()
    match = next((p for p in trash["projects"] if p["id"] == project["id"]), None)
    assert match is not None
    assert match["channel_name"]

    resp = client.post(f"/projects/{project['id']}/restore")
    assert resp.status_code == 200
    assert resp.json()["archived"] is False

    trash = client.get("/trash").json()
    assert project["id"] not in [p["id"] for p in trash["projects"]]


def test_project_permanent_delete_requires_archived_first(client, project):
    resp = client.delete(f"/projects/{project['id']}/permanent")
    assert resp.status_code == 400


def test_project_permanent_delete_removes_db_and_files(client, project):
    from app.config import CHANNELS_DIR

    real_dir = CHANNELS_DIR / project["channel_id"] / "projects" / project["id"]
    assert real_dir.exists()

    client.delete(f"/projects/{project['id']}")
    resp = client.delete(f"/projects/{project['id']}/permanent")
    assert resp.status_code == 200

    assert client.get(f"/projects/{project['id']}").status_code == 404
    assert not real_dir.exists()
