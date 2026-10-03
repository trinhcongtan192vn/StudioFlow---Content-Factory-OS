"""Chỉ số YouTube (kết nối OAuth, đồng bộ, hiển thị) — mới (2026-09-12), theo yêu cầu
người dùng "đề xuất phương án triển khai tính năng thống kê các chỉ số cho kênh, kéo dữ
liệu từ youtube về". Xem `app/youtube_analytics.py` (OAuth/gọi API) và
`app/routers/youtube_analytics.py` (điều phối HTTP).

Test chia 2 nhóm: (1) đơn vị thuần cho `youtube_analytics.py` (không gọi Google thật —
KHÔNG có OAuth Client thật lúc code tính năng này, xem kế hoạch); (2) router — mock toàn
bộ hàm gọi Google API qua monkeypatch (đúng pattern đã dùng cho provider AI khác trong
`test_render.py`/`test_providers.py`), verify LUỒNG ĐIỀU PHỐI/lưu DB đúng, không verify
lại hình dạng response THẬT của Google (việc đó cần 1 kênh test thật, nằm ngoài phạm vi
test tự động)."""
from __future__ import annotations

import io
import json

import pytest


# ---------------------------------------------------------------------------
# `youtube_analytics.py` — logic thuần.
# ---------------------------------------------------------------------------
def test_parse_iso8601_duration_various_formats():
    from app.youtube_analytics import parse_iso8601_duration

    assert parse_iso8601_duration("PT1H2M3S") == 3723.0
    assert parse_iso8601_duration("PT45S") == 45.0
    assert parse_iso8601_duration("PT5M") == 300.0
    assert parse_iso8601_duration("PT2H") == 7200.0
    assert parse_iso8601_duration("") == 0.0
    assert parse_iso8601_duration("khong-hop-le") == 0.0


def test_retention_at_ratio_interpolates_linearly():
    from app.youtube_analytics import retention_at_ratio

    curve = [{"ratio": 0.0, "watch_ratio": 1.0}, {"ratio": 0.5, "watch_ratio": 0.6}, {"ratio": 1.0, "watch_ratio": 0.2}]
    assert retention_at_ratio(curve, 0.25) == pytest.approx(0.8)  # giữa 1.0 và 0.6
    assert retention_at_ratio(curve, 0.75) == pytest.approx(0.4)  # giữa 0.6 và 0.2
    assert retention_at_ratio(curve, 0.0) == pytest.approx(1.0)
    assert retention_at_ratio(curve, 1.0) == pytest.approx(0.2)


def test_retention_at_ratio_returns_none_for_empty_curve_or_out_of_range():
    from app.youtube_analytics import retention_at_ratio

    assert retention_at_ratio([], 0.5) is None
    curve = [{"ratio": 0.1, "watch_ratio": 0.9}, {"ratio": 0.9, "watch_ratio": 0.3}]
    assert retention_at_ratio(curve, 0.05) is None  # ngoài khoảng dữ liệu, không ngoại suy
    assert retention_at_ratio(curve, 0.95) is None


def test_fetch_video_analytics_does_not_request_nonexistent_impressions_metrics(monkeypatch):
    """Bug thật (2026-09-19, user báo lỗi đồng bộ THẬT): `metrics=` trước đây có
    `impressions,impressionClickThroughRate` — Google trả 400 "Unknown identifier
    (impressions)" vì 2 metric này KHÔNG tồn tại trong YouTube Analytics API công khai
    (tra lại tài liệu chính thức xác nhận, xem docstring `fetch_video_analytics`). Test
    này spy request THẬT gửi lên (qua `_build_analytics_client` giả lập) để khoá lại —
    không ai vô tình thêm nhầm 2 metric này trở lại."""
    import app.youtube_analytics as ya

    captured_kwargs = {}

    class _FakeQuery:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

        def execute(self):
            return {
                "columnHeaders": [{"name": "video"}, {"name": "views"}, {"name": "averageViewPercentage"}, {"name": "averageViewDuration"}, {"name": "comments"}],
                "rows": [["vid1", 100, 50.0, 30.0, 5]],
            }

    class _FakeReports:
        def query(self, **kwargs):
            return _FakeQuery(**kwargs)

    class _FakeAnalyticsClient:
        def reports(self):
            return _FakeReports()

    monkeypatch.setattr(ya, "_build_analytics_client", lambda credentials: _FakeAnalyticsClient())

    result = ya.fetch_video_analytics(object(), "UCabc", ["vid1"])

    assert "impressions" not in captured_kwargs["metrics"]
    assert "impressionClickThroughRate" not in captured_kwargs["metrics"]
    assert result["vid1"]["views"] == 100
    assert "impressions" not in result["vid1"]
    assert "impression_ctr" not in result["vid1"]


def test_correlate_retention_with_blocks_splits_by_cumulative_duration_ratio():
    from app.youtube_analytics import correlate_retention_with_blocks

    # Đường cong tuyến tính đơn giản: watch_ratio giảm đều 1.0 -> 0.0 theo ratio.
    curve = [{"ratio": r / 10, "watch_ratio": 1.0 - r / 10} for r in range(11)]
    # 3 block: B01 dài 2s, B02 dài 2s, B03 dài 6s — tổng 10s.
    block_durations = [("B01", 2.0), ("B02", 2.0), ("B03", 6.0)]
    chapters = correlate_retention_with_blocks(curve, block_durations)

    assert len(chapters) == 3
    assert chapters[0]["block_id"] == "B01"
    assert chapters[0]["start_ratio"] == pytest.approx(0.0)
    assert chapters[0]["end_ratio"] == pytest.approx(0.2)
    assert chapters[1]["start_ratio"] == pytest.approx(0.2)
    assert chapters[1]["end_ratio"] == pytest.approx(0.4)
    assert chapters[2]["start_ratio"] == pytest.approx(0.4)
    assert chapters[2]["end_ratio"] == pytest.approx(1.0)
    # Retention giảm dần theo ratio (đường cong tuyến tính giảm) — block SAU phải có
    # avg_retention THẤP HƠN block TRƯỚC (đúng bản chất "chương sau người xem rơi nhiều
    # hơn chương trước" mà tính năng này muốn phát hiện).
    assert chapters[0]["avg_retention"] > chapters[1]["avg_retention"] > chapters[2]["avg_retention"]


def test_correlate_retention_with_blocks_returns_empty_for_zero_total_duration():
    from app.youtube_analytics import correlate_retention_with_blocks

    assert correlate_retention_with_blocks([{"ratio": 0.0, "watch_ratio": 1.0}], []) == []
    assert correlate_retention_with_blocks([], [("B01", 5.0)]) == []


def test_oauth_client_save_and_load_roundtrip_encrypted(channel):
    from app.db import SessionLocal
    from app.youtube_analytics import load_oauth_client, save_oauth_client

    db = SessionLocal()
    try:
        assert load_oauth_client(db) is None or True  # có thể đã có từ test khác chạy trước trong CÙNG session DB — chỉ verify roundtrip dưới
        save_oauth_client(db, "test-client-id.apps.googleusercontent.com", "test-client-secret-xyz")
        loaded = load_oauth_client(db)
        assert loaded == ("test-client-id.apps.googleusercontent.com", "test-client-secret-xyz")

        from app.models import AppSetting
        row = db.query(AppSetting).filter(AppSetting.key == "youtube_oauth_client").first()
        raw = json.loads(row.value)
        # Xác nhận THẬT SỰ mã hoá tại chỗ — giá trị lưu trong DB KHÔNG phải plaintext.
        assert "test-client-secret-xyz" not in raw["client_secret_encrypted"]
    finally:
        db.close()


def test_load_credentials_raises_not_connected_when_no_client_configured():
    from app.db import SessionLocal
    from app.youtube_analytics import YoutubeNotConnectedError, load_credentials

    db = SessionLocal()
    try:
        from app.models import AppSetting
        db.query(AppSetting).filter(AppSetting.key.in_(["youtube_oauth_client", "youtube_oauth:some-channel"])).delete(synchronize_session=False)
        db.commit()
        with pytest.raises(YoutubeNotConnectedError):
            load_credentials(db, "some-channel")
    finally:
        db.close()


def test_load_credentials_raises_not_connected_when_client_set_but_no_token():
    # Token giờ RIÊNG theo kênh (mục 154) — 1 kênh chưa từng connect KHÔNG có key
    # `youtube_oauth:{channel_id}` dù đã có OAuth Client, phải raise.
    from app.db import SessionLocal
    from app.youtube_analytics import YoutubeNotConnectedError, load_credentials, save_oauth_client

    db = SessionLocal()
    try:
        from app.models import AppSetting
        db.query(AppSetting).filter(AppSetting.key == "youtube_oauth:some-other-channel").delete(synchronize_session=False)
        db.commit()
        save_oauth_client(db, "cid", "csecret")
        with pytest.raises(YoutubeNotConnectedError):
            load_credentials(db, "some-other-channel")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Router — mock toàn bộ lời gọi Google API thật qua monkeypatch.
# ---------------------------------------------------------------------------
def test_save_youtube_oauth_client_endpoint(client):
    resp = client.post("/settings/youtube/oauth-client", json={"client_id": "cid123", "client_secret": "csecret456"})
    assert resp.status_code == 200, resp.text
    status = client.get("/settings/youtube/status").json()
    assert status["has_oauth_client"] is True


def test_save_youtube_oauth_client_rejects_empty(client):
    resp = client.post("/settings/youtube/oauth-client", json={"client_id": "", "client_secret": "x"})
    assert resp.status_code == 400


def test_get_authorize_url_400_without_oauth_client(client, channel):
    from app.db import SessionLocal
    from app.models import AppSetting

    db = SessionLocal()
    db.query(AppSetting).filter(AppSetting.key == "youtube_oauth_client").delete(synchronize_session=False)
    db.commit()
    db.close()
    resp = client.get(f"/channels/{channel['id']}/youtube/authorize-url", params={"redirect_uri": "http://127.0.0.1:8756/oauth/callback"})
    assert resp.status_code == 400


def test_get_authorize_url_404_for_unknown_channel(client):
    client.post("/settings/youtube/oauth-client", json={"client_id": "cid", "client_secret": "csecret"})
    resp = client.get("/channels/khong-ton-tai/youtube/authorize-url", params={"redirect_uri": "http://127.0.0.1:8756/oauth/callback"})
    assert resp.status_code == 404


def test_get_authorize_url_returns_google_consent_url_with_channel_id_as_state(client, channel):
    client.post("/settings/youtube/oauth-client", json={"client_id": "myclient.apps.googleusercontent.com", "client_secret": "mysecret"})
    resp = client.get(f"/channels/{channel['id']}/youtube/authorize-url", params={"redirect_uri": "http://127.0.0.1:8756/oauth/callback"})
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    assert "accounts.google.com" in url
    assert "myclient.apps.googleusercontent.com" in url
    # `state` mang đúng channel_id — đây là cơ chế callback dùng để biết token vừa nhận
    # thuộc kênh StudioFlow nào (mục 154, sửa lỗ hổng token dùng chung).
    assert f"state={channel['id']}" in url


def test_oauth_callback_shows_error_html_when_google_returns_error(client):
    resp = client.get("/oauth/callback", params={"error": "access_denied"})
    assert resp.status_code == 400
    assert "access_denied" in resp.text


def test_oauth_callback_400_when_missing_code(client):
    resp = client.get("/oauth/callback")
    assert resp.status_code == 400


def test_oauth_callback_400_when_missing_or_invalid_state(client, monkeypatch):
    client.post("/settings/youtube/oauth-client", json={"client_id": "cid", "client_secret": "csecret"})

    class FakeCredentials:
        token = "fake-access-token"
        refresh_token = "fake-refresh-token"
        expiry = None
        scopes = ["https://www.googleapis.com/auth/youtube.readonly"]

    monkeypatch.setattr("app.routers.youtube_analytics.exchange_code_for_credentials", lambda *a, **k: FakeCredentials())

    resp = client.get("/oauth/callback", params={"code": "fake-code"})  # thiếu state
    assert resp.status_code == 400

    resp = client.get("/oauth/callback", params={"code": "fake-code", "state": "khong-ton-tai"})
    assert resp.status_code == 400


def _fake_channel_info(channel_id="UC_fake_channel"):
    return {"channel_id": channel_id, "title": "Kênh Test Fake", "subscriber_count": 1000, "total_views": 50000, "video_count": 20, "uploads_playlist_id": "UU_fake_uploads"}


def _connect_channel(client, channel_id: str, monkeypatch, channel_info: dict | None = None):
    """Mô phỏng ĐÚNG luồng OAuth per-channel thật (mục 154): cấu hình OAuth Client, fake
    `exchange_code_for_credentials`/`fetch_channel_info`, chạy qua `GET /oauth/callback`
    với `state=channel_id` — callback tự lưu token riêng của kênh này VÀ gán `Channel.
    youtube_channel_id/title` (không còn `POST /channels/{id}/youtube/connect` riêng)."""
    client.post("/settings/youtube/oauth-client", json={"client_id": "cid", "client_secret": "csecret"})

    class FakeCredentials:
        token = "fake-access-token"
        refresh_token = "fake-refresh-token"
        expiry = None
        scopes = ["https://www.googleapis.com/auth/youtube.readonly"]

    monkeypatch.setattr("app.routers.youtube_analytics.exchange_code_for_credentials", lambda *a, **k: FakeCredentials())
    monkeypatch.setattr("app.routers.youtube_analytics.fetch_channel_info", lambda creds: channel_info or _fake_channel_info())
    resp = client.get("/oauth/callback", params={"code": "fake-code", "state": channel_id})
    assert resp.status_code == 200, resp.text
    return resp


def test_oauth_callback_saves_credentials_and_sets_channel_fields_on_success(client, channel, monkeypatch):
    resp = _connect_channel(client, channel["id"], monkeypatch)
    assert "thành công" in resp.text

    ch = client.get(f"/channels/{channel['id']}").json()
    assert ch["youtube_channel_id"] == "UC_fake_channel"
    assert ch["youtube_channel_title"] == "Kênh Test Fake"
    assert ch["youtube_connected_at"] is not None

    status = client.get(f"/channels/{channel['id']}/youtube/oauth-status").json()
    assert status["connected"] is True


def test_two_channels_connect_to_different_youtube_channels_independently(client, monkeypatch):
    """Test cốt lõi cho mục 154 — chứng minh ĐÚNG vấn đề người dùng nêu đã được sửa: 1
    Google Account có thể quản nhiều kênh YouTube; trước đây 2 kênh StudioFlow dùng CHUNG
    1 token nên bị gán NHẦM cùng 1 `youtube_channel_id`. Giờ mỗi kênh tự OAuth riêng
    (state=channel_id khác nhau) phải giữ ĐÚNG kênh YouTube riêng của mình, không lẫn."""
    channel_a = client.post("/channels", json={"name": "Kênh A"}).json()
    channel_b = client.post("/channels", json={"name": "Kênh B"}).json()

    _connect_channel(client, channel_a["id"], monkeypatch, channel_info=_fake_channel_info("UC_channel_A"))
    _connect_channel(client, channel_b["id"], monkeypatch, channel_info=_fake_channel_info("UC_channel_B"))

    ch_a = client.get(f"/channels/{channel_a['id']}").json()
    ch_b = client.get(f"/channels/{channel_b['id']}").json()
    assert ch_a["youtube_channel_id"] == "UC_channel_A"
    assert ch_b["youtube_channel_id"] == "UC_channel_B"

    # Token cũng RIÊNG — load_credentials của kênh A không lẫn với kênh B.
    from app.db import SessionLocal
    from app.youtube_analytics import load_credentials

    db = SessionLocal()
    try:
        creds_a = load_credentials(db, channel_a["id"])
        creds_b = load_credentials(db, channel_b["id"])
        assert creds_a.refresh_token == "fake-refresh-token"
        assert creds_b.refresh_token == "fake-refresh-token"  # cùng giá trị fake, nhưng...
        from app.models import AppSetting
        # ...lưu ở 2 dòng AppSetting TÁCH BIỆT theo channel_id, không phải 1 dòng dùng chung.
        assert db.query(AppSetting).filter(AppSetting.key == f"youtube_oauth:{channel_a['id']}").first() is not None
        assert db.query(AppSetting).filter(AppSetting.key == f"youtube_oauth:{channel_b['id']}").first() is not None
    finally:
        db.close()


def test_disconnect_channel_clears_fields_and_deletes_token(client, channel, monkeypatch):
    _connect_channel(client, channel["id"], monkeypatch)

    resp = client.post(f"/channels/{channel['id']}/youtube/disconnect")
    assert resp.status_code == 200
    ch = client.get(f"/channels/{channel['id']}").json()
    assert ch["youtube_channel_id"] is None

    # Token riêng của kênh này bị xoá luôn (không còn "dùng chung cho kênh khác" như
    # thiết kế cũ) — xem `delete_credentials`.
    from app.db import SessionLocal
    from app.models import AppSetting
    db = SessionLocal()
    try:
        assert db.query(AppSetting).filter(AppSetting.key == f"youtube_oauth:{channel['id']}").first() is None
    finally:
        db.close()


def test_migrate_youtube_token_to_per_channel_copies_legacy_token_once(client, channel):
    """Migration dữ liệu mục 154 — copy token CHUNG cũ (`AppSetting["youtube_oauth"]`,
    thiết kế Phase 1) sang token RIÊNG cho kênh ĐÃ kết nối trước bản sửa (có
    `youtube_channel_id`), để không bắt người dùng làm lại OAuth ngay sau khi cập nhật.
    Idempotent — không ghi đè nếu kênh đã có token riêng (vd. đã tự "Kết nối lại")."""
    from app.db import SessionLocal
    from app.models import AppSetting, Channel
    from app.youtube_migration import migrate_youtube_token_to_per_channel

    db = SessionLocal()
    try:
        db.query(AppSetting).filter(AppSetting.key == "youtube_oauth").delete(synchronize_session=False)
        db.query(AppSetting).filter(AppSetting.key == f"youtube_oauth:{channel['id']}").delete(synchronize_session=False)
        ch = db.query(Channel).filter(Channel.id == channel["id"]).first()
        ch.youtube_channel_id = "UC_old_shared"  # mô phỏng kênh ĐÃ "kết nối" qua token chung cũ
        db.add(AppSetting(key="youtube_oauth", value=json.dumps({"refresh_token_encrypted": "legacy-token-blob"})))
        db.commit()

        migrate_youtube_token_to_per_channel(db)

        per_channel = db.query(AppSetting).filter(AppSetting.key == f"youtube_oauth:{channel['id']}").first()
        assert per_channel is not None
        assert json.loads(per_channel.value)["refresh_token_encrypted"] == "legacy-token-blob"

        # Idempotent: mô phỏng kênh đã tự "Kết nối lại" (token riêng đổi khác) — chạy lại
        # KHÔNG được ghi đè bằng token cũ.
        per_channel.value = json.dumps({"refresh_token_encrypted": "new-real-token"})
        db.commit()
        migrate_youtube_token_to_per_channel(db)
        db.refresh(per_channel)
        assert json.loads(per_channel.value)["refresh_token_encrypted"] == "new-real-token"
    finally:
        db.query(AppSetting).filter(AppSetting.key == "youtube_oauth").delete(synchronize_session=False)
        db.commit()
        db.close()


def test_youtube_videos_available_excludes_videos_linked_to_other_projects(client, channel, monkeypatch):
    _connect_channel(client, channel["id"], monkeypatch)
    monkeypatch.setattr("app.routers.youtube_analytics.load_credentials", lambda db, channel_id: object())
    monkeypatch.setattr("app.routers.youtube_analytics.fetch_channel_info", lambda creds: _fake_channel_info())

    p1 = client.post(f"/channels/{channel['id']}/projects", json={"title": "Video A"}).json()
    p2 = client.post(f"/channels/{channel['id']}/projects", json={"title": "Video B"}).json()

    fake_videos = [
        {"video_id": "vid1", "title": "Video 1", "published_at": "2026-01-01T00:00:00Z"},
        {"video_id": "vid2", "title": "Video 2", "published_at": "2026-01-02T00:00:00Z"},
    ]
    monkeypatch.setattr("app.routers.youtube_analytics.fetch_uploaded_videos", lambda creds, playlist_id, max_results=200: fake_videos)

    # Liên kết vid1 với p1 trước.
    resp = client.patch(f"/projects/{p1['id']}/youtube-link", json={"video_id": "vid1"})
    assert resp.status_code == 200, resp.text

    available = client.get(f"/projects/{p2['id']}/youtube-videos-available").json()
    video_ids = {v["video_id"] for v in available["videos"]}
    assert "vid1" not in video_ids  # đã bị p1 chiếm
    assert "vid2" in video_ids


def test_youtube_videos_available_400_when_channel_not_connected(client, channel):
    p = client.post(f"/channels/{channel['id']}/projects", json={"title": "P"}).json()
    resp = client.get(f"/projects/{p['id']}/youtube-videos-available")
    assert resp.status_code == 400


def test_sync_youtube_metrics_computes_weighted_averages_and_saves_snapshots(client, channel, monkeypatch):
    _connect_channel(client, channel["id"], monkeypatch)
    monkeypatch.setattr("app.routers.youtube_analytics.load_credentials", lambda db, channel_id: object())
    monkeypatch.setattr("app.routers.youtube_analytics.fetch_channel_info", lambda creds: _fake_channel_info())

    p1 = client.post(f"/channels/{channel['id']}/projects", json={"title": "V1"}).json()
    p2 = client.post(f"/channels/{channel['id']}/projects", json={"title": "V2"}).json()
    client.patch(f"/projects/{p1['id']}/youtube-link", json={"video_id": "vid1"})
    client.patch(f"/projects/{p2['id']}/youtube-link", json={"video_id": "vid2"})

    monkeypatch.setattr("app.routers.youtube_analytics.fetch_video_durations", lambda creds, ids: {"vid1": 600.0, "vid2": 300.0})
    monkeypatch.setattr("app.routers.youtube_analytics.fetch_video_analytics", lambda creds, ch_id, ids: {
        # KHÔNG còn "impressions"/"impression_ctr" — metric này không tồn tại trong
        # YouTube Analytics API công khai (bug thật 400 "Unknown identifier", 2026-09-19,
        # xem docstring `youtube_analytics.py::fetch_video_analytics`); hàm thật giờ
        # không bao giờ trả 2 field này nữa.
        "vid1": {"views": 1000, "avg_view_percentage": 60.0, "avg_view_duration_sec": 360.0, "comment_count": 20},
        "vid2": {"views": 100, "avg_view_percentage": 40.0, "avg_view_duration_sec": 120.0, "comment_count": 2},
    })
    monkeypatch.setattr("app.routers.youtube_analytics.fetch_country_breakdown", lambda creds, ch_id, ids: {
        "vid1": {"DE": 500, "US": 500}, "vid2": {"AT": 50, "US": 50},
    })
    monkeypatch.setattr("app.routers.youtube_analytics.fetch_retention_curve", lambda creds, ch_id, vid: [
        {"ratio": 0.0, "watch_ratio": 1.0}, {"ratio": 1.0, "watch_ratio": 0.3},
    ])

    resp = client.post(f"/channels/{channel['id']}/youtube/sync")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    snap = body["channel_snapshot"]
    assert snap["subscriber_count"] == 1000
    # APV trung bình CÓ TRỌNG SỐ theo view: (60*1000 + 40*100) / 1100 = 58.18...
    assert snap["avg_view_percentage"] == pytest.approx((60.0 * 1000 + 40.0 * 100) / 1100, abs=0.01)
    # bình luận/1.000 view: (20+2) / 1100 * 1000 = 20.0
    assert snap["comments_per_1000_views"] == pytest.approx(20.0, abs=0.01)
    # DE+AT+CH views = 500+50 = 550, tổng view = 1100 -> 50%
    assert snap["de_at_ch_views_pct"] == pytest.approx(50.0, abs=0.01)
    # KHÔNG tự động hoá được (bug thật 2026-09-19) — luôn None, không phải 0.
    assert snap["avg_impression_ctr"] is None

    video_metrics = {v["project_id"]: v["metrics"] for v in body["videos"]}
    assert video_metrics[p1["id"]]["views"] == 1000
    assert video_metrics[p1["id"]]["avg_view_percentage"] == pytest.approx(60.0)
    # retention giây 30 với video 600s -> ratio 30/600=0.05, nội suy tuyến tính giữa (0,1.0) và (1,0.3) -> 1.0 - 0.05*0.7 = 0.965 -> *100 = 96.5%
    assert video_metrics[p1["id"]]["retention_at_30s"] == pytest.approx(96.5, abs=0.1)
    assert video_metrics[p1["id"]]["impressions"] is None
    assert video_metrics[p1["id"]]["impression_ctr"] is None


def test_sync_youtube_metrics_400_when_no_linked_projects(client, channel, monkeypatch):
    _connect_channel(client, channel["id"], monkeypatch)
    resp = client.post(f"/channels/{channel['id']}/youtube/sync")
    assert resp.status_code == 400


def test_sync_youtube_metrics_400_when_channel_not_connected(client, channel):
    resp = client.post(f"/channels/{channel['id']}/youtube/sync")
    assert resp.status_code == 400


def _import_simple_script(client, pid: str, rows: list[list[str]]) -> list[str]:
    header = ["Mã block", "Thời lượng", "Loại Visual", "Hình ảnh & Hiệu ứng (Visual/FX)", "Âm thanh & Nhạc nền (Audio/SFX)", "Kịch bản Giọng đọc (VO Content)"]
    csv_bytes = ("\n".join(",".join(f'"{c}"' for c in r) for r in [header, *rows])).encode("utf-8")
    preview = client.post(f"/projects/{pid}/script/import/parse", files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    confirm = client.post(f"/projects/{pid}/script/import/confirm", json={"beats": preview["beats"], "full_text": preview["full_text"]})
    assert confirm.status_code == 200, confirm.text
    resp = client.post(f"/projects/{pid}/visual/generate")
    assert resp.status_code == 200, resp.text
    return [s["shot_id"] for s in resp.json()["shots"]]


def test_retention_chapters_uses_script_timestamp_fallback_when_no_narration(client, channel):
    p = client.post(f"/channels/{channel['id']}/projects", json={"title": "P"}).json()
    rows = [
        ["B01", "0:00–0:05", "Image", "Canh 1", "", "Loi thoai 1."],
        ["B02", "0:05–0:15", "Image", "Canh 2", "", "Loi thoai 2."],
    ]
    _import_simple_script(client, p["id"], rows)
    client.patch(f"/projects/{p['id']}/youtube-link", json={"video_id": "vidX"})

    from app.db import SessionLocal
    from app.models import YoutubeVideoMetricsSnapshot
    db = SessionLocal()
    db.add(YoutubeVideoMetricsSnapshot(
        project_id=p["id"], synced_at="2026-09-12T00:00:00+07:00", video_duration_sec=15.0,
        retention_curve=json.dumps([{"ratio": 0.0, "watch_ratio": 1.0}, {"ratio": 1.0, "watch_ratio": 0.5}]),
    ))
    db.commit()
    db.close()

    resp = client.get(f"/projects/{p['id']}/youtube/retention-chapters")
    assert resp.status_code == 200, resp.text
    chapters = resp.json()["chapters"]
    assert len(chapters) == 2
    assert chapters[0]["block_id"] == "B01"
    # B01 dài 5s trên tổng 15s -> ratio [0, 0.333); B02 dài 10s -> [0.333, 1.0)
    assert chapters[0]["end_ratio"] == pytest.approx(1 / 3, abs=0.01)
    assert chapters[1]["end_ratio"] == pytest.approx(1.0)


def test_retention_chapters_400_without_synced_data(client, channel):
    p = client.post(f"/channels/{channel['id']}/projects", json={"title": "P"}).json()
    resp = client.get(f"/projects/{p['id']}/youtube/retention-chapters")
    assert resp.status_code == 400
