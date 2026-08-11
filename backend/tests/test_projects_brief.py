import io

import app.routers.projects as projects_router


def test_create_project_defaults(client, channel):
    resp = client.post(f"/channels/{channel['id']}/projects", json={"title": "Dự án A"})
    assert resp.status_code == 200
    p = resp.json()
    assert p["title"] == "Dự án A"
    assert p["status"] == "draft"
    assert p["step"] == 0
    assert p["max_step_reached"] == 0
    assert p["pack_version"] == 1

    resp = client.get(f"/channels/{channel['id']}/projects")
    ids = [x["id"] for x in resp.json()]
    assert p["id"] in ids


def test_get_project_404(client):
    resp = client.get("/projects/does_not_exist")
    assert resp.status_code == 404


def test_patch_project_title_and_step_guard(client, project):
    resp = client.patch(f"/projects/{project['id']}", json={"title": "Tên mới"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Tên mới"

    # chưa đạt max_step_reached -> không cho nhảy step
    resp = client.patch(f"/projects/{project['id']}", json={"step": 3})
    assert resp.status_code == 400


def test_archive_project(client, project):
    resp = client.delete(f"/projects/{project['id']}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = client.get(f"/channels/{project['channel_id']}/projects")
    ids = [x["id"] for x in resp.json()]
    assert project["id"] not in ids


def test_brief_missing_groups_not_blocking(client, project):
    resp = client.get(f"/projects/{project['id']}/brief")
    assert resp.status_code == 200
    data = resp.json()
    assert "group1" in data["missing_groups"]
    assert "group2" in data["missing_groups"]

    body = data["brief"]
    body["topic"] = "Chủ đề"
    body["insight"] = "Insight"
    resp = client.put(f"/projects/{project['id']}/brief", json=body)
    assert resp.status_code == 200
    assert "group1" not in resp.json()["missing_groups"]
    assert "group2" in resp.json()["missing_groups"]  # audience/goal vẫn thiếu — không bị chặn


def test_brief_add_file_source(client, project):
    file_content = "Nội dung tài liệu tham khảo test.".encode("utf-8")
    resp = client.post(
        f"/projects/{project['id']}/brief/sources",
        files={"file": ("ghi-chu.txt", io.BytesIO(file_content), "text/plain")},
    )
    assert resp.status_code == 200
    docs = resp.json()["raw_knowledge"]["documents"]
    assert len(docs) == 1
    assert docs[0]["kind"] == "file"
    assert docs[0]["status"] == "done"
    assert docs[0]["char_count"] == len(file_content.decode("utf-8"))
    assert docs[0]["content_path"]


def test_brief_add_youtube_source_success(client, project, monkeypatch):
    monkeypatch.setattr(projects_router, "fetch_transcript_text", lambda video_id: "transcript giả lập cho test")
    resp = client.post(f"/projects/{project['id']}/brief/sources", data={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert resp.status_code == 200
    docs = resp.json()["raw_knowledge"]["documents"]
    src = docs[-1]
    assert src["kind"] == "youtube"
    assert src["status"] == "done"
    assert src["char_count"] == len("transcript giả lập cho test")
    assert src["content_path"]


def test_brief_add_youtube_source_invalid_url(client, project):
    resp = client.post(f"/projects/{project['id']}/brief/sources", data={"youtube_url": "not a youtube url at all"})
    assert resp.status_code == 200
    src = resp.json()["raw_knowledge"]["documents"][-1]
    assert src["status"] == "error"
    assert src["error"]


def test_brief_add_youtube_source_extraction_failure(client, project, monkeypatch):
    def _boom(video_id):
        raise ValueError("Video đã tắt phụ đề/transcript")

    monkeypatch.setattr(projects_router, "fetch_transcript_text", _boom)
    resp = client.post(f"/projects/{project['id']}/brief/sources", data={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"})
    assert resp.status_code == 200
    src = resp.json()["raw_knowledge"]["documents"][-1]
    assert src["status"] == "error"
    assert src["error"] == "Video đã tắt phụ đề/transcript"


def test_brief_missing_file_and_youtube_url_400(client, project):
    resp = client.post(f"/projects/{project['id']}/brief/sources")
    assert resp.status_code == 400


def test_remove_brief_source(client, project, monkeypatch):
    monkeypatch.setattr(projects_router, "fetch_transcript_text", lambda video_id: "abc")
    add = client.post(f"/projects/{project['id']}/brief/sources", data={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"})
    source_id = add.json()["raw_knowledge"]["documents"][-1]["id"]

    resp = client.delete(f"/projects/{project['id']}/brief/sources/{source_id}")
    assert resp.status_code == 200
    ids = [d["id"] for d in resp.json()["raw_knowledge"]["documents"]]
    assert source_id not in ids
