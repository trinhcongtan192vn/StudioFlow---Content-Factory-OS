"""Kéo chỉ số THẬT từ YouTube (Data API v3 + Analytics API v2) — **mới (2026-09-12)**,
theo yêu cầu người dùng: thay "Nạp retention thủ công" (`RetentionEntry`,
`routers/guardrail.py`) bằng dữ liệu tự động, đúng lộ trình đã ghi sẵn ở
`specs/08_retention_guardrail.md` §7 "Lộ trình M4". KHÁC hẳn `app/youtube.py` (chỉ bọc
`youtube_transcript_api` lấy transcript CÔNG KHAI, không OAuth) — module này cần OAuth
2.0 THẬT vì mọi chỉ số Analytics (APV, retention, CTR, quốc gia...) là dữ liệu RIÊNG của
chủ kênh, không public.

**Quyết định đã chốt lúc lên kế hoạch (hỏi trực tiếp người dùng)**: RPM (doanh thu) cần
quyền OAuth `yt-analytics-monetary.readonly` — quyền RẤT KHÓ xin cho app cá nhân/nhỏ
(Google thường yêu cầu audit CMS/Content Owner) — KHÔNG tự động hoá, giữ nhập tay qua
`RetentionEntry.rpm`. Module này CHỈ xin `youtube.readonly` + `yt-analytics.readonly`.

**OAuth Client do NGƯỜI DÙNG TỰ ĐĂNG KÝ** (Google Cloud Console, loại "Desktop app") —
app KHÔNG nhúng sẵn 1 client dùng chung (rủi ro bảo mật khi phân phối + tranh chấp quota
giữa nhiều người dùng khác nhau). `client_id`/`client_secret` do người dùng dán vào
Settings, lưu mã hoá qua `app/crypto.py` (đúng nguyên tắc đã áp dụng cho API key provider
AI) — CHỈ 1 cặp dùng CHUNG cho toàn app (đây là định danh CỦA APP đăng ký với Google, không
phải danh tính người dùng, nên dùng chung không sao).

**Token OAuth (access/refresh) LƯU RIÊNG THEO TỪNG KÊNH StudioFlow** — sửa
(2026-09-19, theo câu hỏi thật của người dùng: "1 account có thể có nhiều kênh (gồm brand
channel và các kênh được share) — vậy làm sao gắn đúng kênh trên App với kênh của account
Google đó?"). Thiết kế CŨ (Phase 1) lưu CHUNG 1 dòng `AppSetting` cho toàn app — SAI khi 1
Google Account quản nhiều kênh: 2 kênh StudioFlow bấm connect sẽ nhận NHẦM cùng 1
`youtube_channel_id` vì dùng chung 1 token. Đã verify THẬT (không suy đoán) qua báo cáo
thực tế trên GitHub (google/google-api-javascript-client#628 — người dùng khác xác nhận
màn hình đồng ý OAuth của Google TỰ hiện bộ chọn kênh/brand account khi tài khoản quản lý
nhiều kênh): cơ chế ĐÚNG là để MỖI kênh StudioFlow tự chạy 1 lượt OAuth RIÊNG (chọn đúng
kênh ở màn Google), lưu token RIÊNG cho kênh đó — key `AppSetting` giờ là
`f"youtube_oauth:{channel_id}"` thay vì 1 key cố định (tái dùng bảng `AppSetting` key-
value sẵn có, không cần bảng/cột mới). Đánh đổi: người dùng cần đăng nhập lại Google 1
lần cho MỖI kênh StudioFlow muốn kết nối (không dùng lại được token của kênh khác) — đã
hỏi trực tiếp người dùng, chấp nhận đánh đổi này ("chỉ cần connect lần đầu tiên cho mỗi
kênh thì ko sao").

**Luồng OAuth**: Authorization Code (loopback, RFC 8252 "installed app") — KHÔNG cần
server public. `redirect_uri` do FRONTEND cung cấp (`http://127.0.0.1:{port}/oauth/
callback`, `port` chính là cổng backend đang chạy — frontend đã biết qua
`window.STUDIOFLOW_API_BASE`) — Google KHÔNG yêu cầu đăng ký trước CHÍNH XÁC port cho
loại client "Desktop", chỉ cần đúng dạng `http://127.0.0.1:*/...` hoặc `http://
localhost:*/...`. Callback được phục vụ NGAY bởi chính FastAPI backend đang chạy (không
cần mở thêm 1 HTTP server tạm riêng)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.crypto import decrypt_secret, encrypt_secret
from app.models import AppSetting
from app.timeutil import vn_isoformat

# Scope tối thiểu đủ cho MỌI chỉ số Phase 1 (APV/CTR/retention giây 30/bình luận mỗi
# 1.000 view/DE-AT-CH) — KHÔNG xin `yt-analytics-monetary.readonly` (RPM giữ nhập tay,
# xem docstring module).
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

_OAUTH_SETTING_KEY = "youtube_oauth"


class YoutubeNotConnectedError(RuntimeError):
    """Chưa cấu hình OAuth Client (`client_id`/`client_secret`) HOẶC chưa kết nối tài
    khoản Google (chưa có `refresh_token`) — router quy đổi thành 400 kèm thông điệp rõ
    "Cần kết nối tài khoản Google trước", không phải lỗi 500 chung chung."""


class YoutubeApiError(RuntimeError):
    """Bọc `googleapiclient.errors.HttpError` thành thông điệp tiếng Việt dễ hiểu (quota
    vượt hạn mức, token bị thu hồi, video không tồn tại...) — xem `_wrap_http_error`."""


def _wrap_http_error(e: HttpError) -> YoutubeApiError:
    status = e.resp.status if e.resp else 0
    if status == 401:
        return YoutubeApiError("Token Google đã hết hạn/bị thu hồi — cần kết nối lại tài khoản Google.")
    if status == 403:
        return YoutubeApiError("YouTube từ chối quyền truy cập (quota vượt hạn mức hoặc scope không đủ) — thử lại sau hoặc kiểm tra lại quyền đã xin.")
    if status == 429:
        return YoutubeApiError("Đã vượt hạn mức (quota) gọi API YouTube hôm nay — thử lại vào ngày mai.")
    return YoutubeApiError(f"Lỗi gọi API YouTube (HTTP {status}): {e}")


# ---------------------------------------------------------------------------
# OAuth Client (client_id/client_secret do người dùng tự đăng ký) — lưu ở AppSetting
# riêng (key "youtube_oauth_client"), TÁCH khỏi token (key "youtube_oauth") — cho phép
# đổi/xoá client mà không tự động mất token đã có (dù đổi client thường sẽ cần kết nối
# lại, tách 2 field vẫn rõ ràng hơn gộp chung 1 blob).
# ---------------------------------------------------------------------------
_OAUTH_CLIENT_SETTING_KEY = "youtube_oauth_client"


def load_oauth_client(db: Session) -> tuple[str, str] | None:
    row = db.query(AppSetting).filter(AppSetting.key == _OAUTH_CLIENT_SETTING_KEY).first()
    if not row:
        return None
    data = json.loads(row.value)
    client_id = decrypt_secret(data.get("client_id_encrypted", ""))
    client_secret = decrypt_secret(data.get("client_secret_encrypted", ""))
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def save_oauth_client(db: Session, client_id: str, client_secret: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == _OAUTH_CLIENT_SETTING_KEY).first()
    encoded = json.dumps({"client_id_encrypted": encrypt_secret(client_id), "client_secret_encrypted": encrypt_secret(client_secret)})
    if row:
        row.value = encoded
    else:
        db.add(AppSetting(key=_OAUTH_CLIENT_SETTING_KEY, value=encoded))
    db.commit()


# ---------------------------------------------------------------------------
# OAuth token (access_token/refresh_token) — RIÊNG theo từng Channel StudioFlow (xem
# docstring module) — key `AppSetting` là `f"youtube_oauth:{channel_id}"`, không phải 1
# key cố định như trước.
# ---------------------------------------------------------------------------
def _oauth_token_setting_key(channel_id: str) -> str:
    return f"{_OAUTH_SETTING_KEY}:{channel_id}"


def _flow(client_id: str, client_secret: str, redirect_uri: str) -> Flow:
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)


def build_authorize_url(client_id: str, client_secret: str, redirect_uri: str, state: str) -> str:
    """`access_type="offline"` — BẮT BUỘC để Google trả kèm `refresh_token` (mặc định
    chỉ trả `access_token` sống ~1 giờ). `prompt="consent"` — ép hiện lại màn đồng ý MỖI
    LẦN (kể cả đã từng đồng ý trước đó) — đảm bảo LUÔN nhận được `refresh_token` mới ở
    lần kết nối lại (Google chỉ trả `refresh_token` ở LẦN ĐẦU đồng ý cho 1 client, trừ
    khi ép `prompt=consent`).

    `state` mang `channel_id` của kênh StudioFlow đang kết nối — Google echo lại NGUYÊN
    VĂN qua query `state` ở `/oauth/callback` (đã verify qua đọc trực tiếp source
    `google_auth_oauthlib/flow.py`: `authorization_url(**kwargs)` truyền thẳng xuống
    `oauth2session.authorization_url`, không cần Flow nào khác biết trước `state`) — nhờ
    đó callback biết CHÍNH XÁC token vừa nhận thuộc về kênh StudioFlow nào, không cần
    bảng tạm lưu state↔channel_id."""
    flow = _flow(client_id, client_secret, redirect_uri)
    url, _state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true", state=state)
    return url


def exchange_code_for_credentials(client_id: str, client_secret: str, redirect_uri: str, code: str) -> Credentials:
    flow = _flow(client_id, client_secret, redirect_uri)
    flow.fetch_token(code=code)
    return flow.credentials


def _credentials_to_dict(credentials: Credentials) -> dict:
    return {
        "access_token_encrypted": encrypt_secret(credentials.token or ""),
        "refresh_token_encrypted": encrypt_secret(credentials.refresh_token or ""),
        "token_expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        "scopes": credentials.scopes or SCOPES,
    }


def save_credentials(db: Session, channel_id: str, credentials: Credentials) -> None:
    key = _oauth_token_setting_key(channel_id)
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    encoded = json.dumps(_credentials_to_dict(credentials))
    if row:
        row.value = encoded
    else:
        db.add(AppSetting(key=key, value=encoded))
    db.commit()


def delete_credentials(db: Session, channel_id: str) -> None:
    """Xoá token RIÊNG của kênh này — dùng khi disconnect. KHÁC với thiết kế cũ (token
    dùng chung, cố ý không xoá vì "kênh khác vẫn cần") — giờ token là của RIÊNG kênh này,
    không ai khác dùng lại được nên xoá luôn, tránh rác trong `AppSetting`."""
    key = _oauth_token_setting_key(channel_id)
    db.query(AppSetting).filter(AppSetting.key == key).delete()
    db.commit()


def load_credentials(db: Session, channel_id: str) -> Credentials:
    """Nạp lại `Credentials` CỦA RIÊNG `channel_id` từ DB, TỰ ĐỘNG refresh nếu access
    token đã hết hạn (dùng `refresh_token` đã lưu) — ghi lại access token MỚI vào DB sau
    khi refresh thành công (refresh_token thường KHÔNG đổi, nhưng access_token/expiry thì
    có). Raise `YoutubeNotConnectedError` nếu chưa cấu hình OAuth Client hoặc kênh này
    chưa từng kết nối (chưa có `refresh_token` riêng của nó)."""
    client = load_oauth_client(db)
    if not client:
        raise YoutubeNotConnectedError("Chưa cấu hình OAuth Client (client_id/client_secret) ở Settings.")
    client_id, client_secret = client

    row = db.query(AppSetting).filter(AppSetting.key == _oauth_token_setting_key(channel_id)).first()
    if not row:
        raise YoutubeNotConnectedError("Kênh này chưa kết nối YouTube — bấm 'Kết nối kênh này với YouTube'.")
    data = json.loads(row.value)
    refresh_token = decrypt_secret(data.get("refresh_token_encrypted", ""))
    if not refresh_token:
        raise YoutubeNotConnectedError("Kênh này chưa kết nối YouTube — bấm 'Kết nối kênh này với YouTube'.")

    credentials = Credentials(
        token=decrypt_secret(data.get("access_token_encrypted", "")) or None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=data.get("scopes") or SCOPES,
    )
    if data.get("token_expiry"):
        credentials.expiry = datetime.fromisoformat(data["token_expiry"])

    if not credentials.valid:
        try:
            credentials.refresh(GoogleAuthRequest())
        except Exception as e:  # noqa: BLE001 — refresh_token hết hiệu lực/bị thu hồi
            raise YoutubeNotConnectedError("Token Google đã hết hạn/bị thu hồi — cần kết nối lại kênh này với YouTube.") from e
        save_credentials(db, channel_id, credentials)
    return credentials


def is_connected(db: Session, channel_id: str) -> bool:
    try:
        load_credentials(db, channel_id)
        return True
    except YoutubeNotConnectedError:
        return False


# ---------------------------------------------------------------------------
# Data API v3 — thông tin kênh/video công khai CỦA CHÍNH chủ tài khoản đã xác thực.
# ---------------------------------------------------------------------------
def _build_data_client(credentials: Credentials):
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def _build_analytics_client(credentials: Credentials):
    return build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)


_ISO8601_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_iso8601_duration(duration: str) -> float:
    """YouTube Data API trả độ dài video dạng ISO 8601 (`PT1H2M3S`) — quy đổi ra giây.
    Trả `0.0` nếu không parse được (chuỗi rỗng/dạng lạ) thay vì raise — best-effort, 1
    video lỗi không nên chặn cả lượt đồng bộ."""
    match = _ISO8601_DURATION_RE.fullmatch((duration or "").strip())
    if not match:
        return 0.0
    h, m, s = (int(g) if g else 0 for g in match.groups())
    return float(h * 3600 + m * 60 + s)


def fetch_channel_info(credentials: Credentials) -> dict:
    """`channels.list(mine=true)` — kênh YouTube gắn với CHÍNH tài khoản Google vừa xác
    thực, KHÔNG cần người dùng tự tìm/dán Channel ID. Trả
    `{channel_id, title, subscriber_count, total_views, video_count, uploads_playlist_id}`
    — `uploads_playlist_id` (từ `contentDetails.relatedPlaylists.uploads`) dùng để liệt
    kê video đã đăng qua `playlistItems.list` (rẻ hơn NHIỀU `search.list` về quota — 1
    unit thay vì 100 unit mỗi lần gọi)."""
    try:
        youtube = _build_data_client(credentials)
        resp = youtube.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
    except HttpError as e:
        raise _wrap_http_error(e) from e
    items = resp.get("items") or []
    if not items:
        raise YoutubeApiError("Tài khoản Google đã kết nối không có kênh YouTube nào.")
    item = items[0]
    stats = item.get("statistics") or {}
    return {
        "channel_id": item["id"],
        "title": (item.get("snippet") or {}).get("title") or "",
        "subscriber_count": int(stats.get("subscriberCount") or 0),
        "total_views": int(stats.get("viewCount") or 0),
        "video_count": int(stats.get("videoCount") or 0),
        "uploads_playlist_id": ((item.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or "",
    }


def fetch_uploaded_videos(credentials: Credentials, uploads_playlist_id: str, max_results: int = 200) -> list[dict]:
    """Danh sách video đã đăng, MỚI NHẤT trước — `playlistItems.list` trên playlist
    "uploads" (xem `fetch_channel_info`), tự phân trang tới khi đủ `max_results` hoặc hết
    danh sách. Trả `[{video_id, title, published_at}]`."""
    try:
        youtube = _build_data_client(credentials)
        videos: list[dict] = []
        page_token = None
        while len(videos) < max_results:
            resp = youtube.playlistItems().list(
                part="snippet,contentDetails", playlistId=uploads_playlist_id, maxResults=50, pageToken=page_token,
            ).execute()
            for item in resp.get("items") or []:
                content = item.get("contentDetails") or {}
                snippet = item.get("snippet") or {}
                videos.append({
                    "video_id": content.get("videoId") or "",
                    "title": snippet.get("title") or "",
                    "published_at": content.get("videoPublishedAt") or snippet.get("publishedAt") or "",
                })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return videos[:max_results]
    except HttpError as e:
        raise _wrap_http_error(e) from e


def fetch_video_durations(credentials: Credentials, video_ids: list[str]) -> dict[str, float]:
    """`videos.list(part=contentDetails)` — `id` nhận TỐI ĐA 50 video/lượt gọi (giới hạn
    Data API) — tự chia nhóm nếu `video_ids` dài hơn."""
    if not video_ids:
        return {}
    try:
        youtube = _build_data_client(credentials)
        result: dict[str, float] = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            resp = youtube.videos().list(part="contentDetails", id=",".join(batch)).execute()
            for item in resp.get("items") or []:
                result[item["id"]] = parse_iso8601_duration((item.get("contentDetails") or {}).get("duration", ""))
        return result
    except HttpError as e:
        raise _wrap_http_error(e) from e


# ---------------------------------------------------------------------------
# Analytics API v2 — chỉ số RIÊNG của chủ kênh (cần scope yt-analytics.readonly).
#
# **Tên metric CHƯA VERIFY bằng response THẬT** (chưa có OAuth Client thật lúc code —
# xem kế hoạch, bước xác minh cần 1 kênh YouTube test thật) — dựa theo tài liệu công khai
# YouTube Analytics API v2 (Channel reports). Nếu tên field sai lệch khi verify thật,
# CHỈ cần sửa danh sách `metrics`/tên field đọc kết quả ở các hàm dưới, không đổi kiến
# trúc tổng thể.
# ---------------------------------------------------------------------------
def _default_date_range(days: int = 90) -> tuple[str, str]:
    """Khoảng ngày mặc định cho báo cáo Analytics — 90 ngày gần nhất, đủ dài để có dữ
    liệu ổn định cho video mới đăng lẫn video cũ (report Analytics cho phép query khoảng
    RẤT dài, không giới hạn như quota Data API — chọn 90 ngày làm mặc định hợp lý, không
    phải giới hạn kỹ thuật). `end_date` lùi 2 ngày so với hôm nay — dữ liệu Analytics
    thường TRỄ 1-2 ngày so với thực tế, query tới hôm nay dễ ra thiếu/rỗng cho ngày gần
    nhất."""
    end = datetime.now(timezone.utc).date() - timedelta(days=2)
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def fetch_video_analytics(credentials: Credentials, channel_id: str, video_ids: list[str]) -> dict[str, dict]:
    """1 lượt gọi `reports.query` LẤY CẢ CHO NHIỀU VIDEO CÙNG LÚC (dimension `video`,
    filter `video==id1,id2,...`) — tiết kiệm hẳn N lượt gọi riêng lẻ. Trả
    `{video_id: {views, avg_view_percentage, avg_view_duration_sec, comment_count}}` —
    video KHÔNG có trong kết quả (chưa đủ dữ liệu/mới đăng) được caller coi là `None`/bỏ
    qua, không raise lỗi riêng.

    **Bug thật (2026-09-19, user báo lỗi 400 lúc đồng bộ THẬT)**: `metrics=` trước đây có
    `impressions,impressionClickThroughRate` (đoán tên lúc code, ghi rõ "CHƯA VERIFY bằng
    response THẬT" — chưa có OAuth Client thật lúc build) — verify thật xác nhận Google
    trả lỗi `HTTP 400 "Unknown identifier (impressions) given in field parameters.metrics"`,
    tức 2 metric này KHÔNG tồn tại trong YouTube Analytics API công khai (đã tra lại
    `developers.google.com/youtube/analytics/metrics` + `.../channel_reports` — không có
    metric "impressions"/"impressionClickThroughRate"/"videoThumbnailImpressions" nào cho
    dimension `video`, dù YouTube Studio CÓ hiện thẻ "Số lần hiển thị & tỷ lệ nhấp" — dữ
    liệu đó KHÔNG được lộ qua Analytics API công khai). CÙNG NHÓM giới hạn với RPM/
    Returning Viewers (xem `models.py::RetentionEntry.rpm`) — bỏ hẳn 2 metric này khỏi
    request, `impressions`/`impression_ctr` ở caller giữ NGUYÊN `None` vĩnh viễn (không
    tự động hoá được, CTR thumbnail vẫn cần nạp tay qua `RetentionEntry.thumbnail_ctr` đã
    có sẵn từ trước tính năng này)."""
    if not video_ids:
        return {}
    start_date, end_date = _default_date_range()
    try:
        analytics = _build_analytics_client(credentials)
        resp = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="views,averageViewPercentage,averageViewDuration,comments",
            dimensions="video",
            filters=f"video=={','.join(video_ids)}",
        ).execute()
    except HttpError as e:
        raise _wrap_http_error(e) from e

    headers = [h["name"] for h in resp.get("columnHeaders") or []]
    result: dict[str, dict] = {}
    for row in resp.get("rows") or []:
        values = dict(zip(headers, row))
        video_id = values.get("video")
        if not video_id:
            continue
        result[video_id] = {
            "views": int(values.get("views") or 0),
            "avg_view_percentage": float(values.get("averageViewPercentage") or 0.0),
            "avg_view_duration_sec": float(values.get("averageViewDuration") or 0.0),
            "comment_count": int(values.get("comments") or 0),
        }
    return result


def fetch_retention_curve(credentials: Credentials, channel_id: str, video_id: str) -> list[dict]:
    """`audienceRetention` report — dimension `elapsedVideoTimeRatio` (0.0-1.0), metric
    `audienceWatchRatio`. KHÔNG gộp batch nhiều video (Analytics API không hỗ trợ nhiều
    giá trị dimension `elapsedVideoTimeRatio` cùng lúc theo tài liệu) — gọi RIÊNG từng
    video, CHỈ cho video đã liên kết project (không phải toàn bộ video trong kênh, tránh
    tốn quota vô ích cho video không quan tâm). Trả `[{ratio, watch_ratio}]` sắp xếp theo
    `ratio` tăng dần."""
    start_date, end_date = _default_date_range()
    try:
        analytics = _build_analytics_client(credentials)
        resp = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="audienceWatchRatio",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
        ).execute()
    except HttpError as e:
        raise _wrap_http_error(e) from e

    headers = [h["name"] for h in resp.get("columnHeaders") or []]
    curve = []
    for row in resp.get("rows") or []:
        values = dict(zip(headers, row))
        curve.append({"ratio": float(values.get("elapsedVideoTimeRatio") or 0.0), "watch_ratio": float(values.get("audienceWatchRatio") or 0.0)})
    curve.sort(key=lambda c: c["ratio"])
    return curve


def fetch_country_breakdown(credentials: Credentials, channel_id: str, video_ids: list[str]) -> dict[str, dict[str, int]]:
    """`dimensions=video,country` — trả `{video_id: {country_code: views}}`. Dùng để
    tính tỷ trọng lưu lượng DE/AT/CH (chỉ số vận hành trong bộ North-star người dùng
    cung cấp)."""
    if not video_ids:
        return {}
    start_date, end_date = _default_date_range()
    try:
        analytics = _build_analytics_client(credentials)
        resp = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="views",
            dimensions="video,country",
            filters=f"video=={','.join(video_ids)}",
        ).execute()
    except HttpError as e:
        raise _wrap_http_error(e) from e

    headers = [h["name"] for h in resp.get("columnHeaders") or []]
    result: dict[str, dict[str, int]] = {}
    for row in resp.get("rows") or []:
        values = dict(zip(headers, row))
        video_id = values.get("video")
        country = values.get("country")
        if not video_id or not country:
            continue
        result.setdefault(video_id, {})[country] = int(values.get("views") or 0)
    return result


def retention_at_ratio(curve: list[dict], ratio: float) -> float | None:
    """Nội suy tuyến tính `watch_ratio` tại 1 `ratio` bất kỳ từ đường cong retention đã
    sắp xếp — dùng để tính "retention tại giây 30" (chuyển giây 30 → ratio bằng
    `30/video_duration_sec` rồi tra hàm này). Trả `None` nếu `curve` rỗng hoặc `ratio`
    nằm NGOÀI khoảng đã có dữ liệu (không ngoại suy — an toàn hơn đoán bừa)."""
    if not curve:
        return None
    if ratio <= curve[0]["ratio"]:
        return curve[0]["watch_ratio"] if ratio >= curve[0]["ratio"] - 1e-9 else None
    if ratio >= curve[-1]["ratio"]:
        return curve[-1]["watch_ratio"] if ratio <= curve[-1]["ratio"] + 1e-9 else None
    for i in range(len(curve) - 1):
        a, b = curve[i], curve[i + 1]
        if a["ratio"] <= ratio <= b["ratio"]:
            if b["ratio"] == a["ratio"]:
                return a["watch_ratio"]
            t = (ratio - a["ratio"]) / (b["ratio"] - a["ratio"])
            return a["watch_ratio"] + t * (b["watch_ratio"] - a["watch_ratio"])
    return None


def correlate_retention_with_blocks(curve: list[dict], block_durations: list[tuple[str, float]]) -> list[dict]:
    """Khớp đường cong retention (tỷ lệ 0.0-1.0 theo TOÀN VIDEO) với từng BLOCK/chương
    kịch bản — theo yêu cầu người dùng ("theo dõi thêm retention theo từng chương, không
    chỉ APV tổng, để biết chương nào kéo người xem rơi").

    **Dùng TỶ LỆ cộng dồn theo THỨ TỰ block, KHÔNG dùng giây tuyệt đối của kịch bản
    gốc** — `pack.script.body[].timestamp_sec` là ước lượng LÚC VIẾT kịch bản, KHÔNG
    phải timeline video THẬT đã ghép/đăng (độ dài từng block thật ăn theo giọng đọc thật,
    xem `assembly.py::_shot_base_duration`) — với video ĐÃ publish, caller nên truyền
    `block_durations` lấy từ NGUỒN GẦN VỚI THẬT NHẤT hiện có (ưu tiên
    `ShotRenderStatus.narration_duration_sec` nếu project được ghép qua chính StudioFlow;
    fallback `end_sec - timestamp_sec` của kịch bản nếu không có). Hàm này CHỈ lo phần
    quy đổi tỷ lệ — không tự chọn nguồn dữ liệu.

    Trả `[{block_id, start_ratio, end_ratio, avg_retention}]` — `avg_retention` là trung
    bình các điểm `watch_ratio` trong đường cong RƠI VÀO khoảng `[start_ratio, end_ratio)`
    của block đó (nội suy 2 đầu mút qua `retention_at_ratio` nếu khoảng đó không có điểm
    dữ liệu THẬT nào — đường cong Analytics API thường có ~100 điểm cho toàn video, block
    ngắn có thể lọt qua giữa 2 điểm liên tiếp)."""
    total_duration = sum(d for _, d in block_durations)
    if total_duration <= 0 or not curve:
        return []

    results = []
    cumulative = 0.0
    for block_id, duration in block_durations:
        start_ratio = cumulative / total_duration
        cumulative += duration
        end_ratio = cumulative / total_duration
        points_in_range = [c["watch_ratio"] for c in curve if start_ratio <= c["ratio"] < end_ratio]
        if points_in_range:
            avg_retention = sum(points_in_range) / len(points_in_range)
        else:
            mid_ratio = (start_ratio + end_ratio) / 2
            avg_retention = retention_at_ratio(curve, mid_ratio) or 0.0
        results.append({"block_id": block_id, "start_ratio": start_ratio, "end_ratio": end_ratio, "avg_retention": avg_retention})
    return results
