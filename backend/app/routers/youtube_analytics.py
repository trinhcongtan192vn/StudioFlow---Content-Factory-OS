"""Chỉ số YouTube (kết nối OAuth, đồng bộ, hiển thị) — **mới (2026-09-12)**, theo yêu
cầu người dùng: "đề xuất phương án triển khai tính năng thống kê các chỉ số cho kênh,
kéo dữ liệu từ youtube về". Xem `app/youtube_analytics.py` cho toàn bộ logic OAuth/gọi
API — router này CHỈ điều phối HTTP + đọc/ghi DB.

**Không tự động đồng bộ nền** — CLAUDE.md nguyên tắc 3 ("mỗi bước là hành động rõ ràng
người dùng tự bấm"). Mọi lượt đồng bộ đều do người dùng chủ động bấm nút.

**OAuth giờ RIÊNG theo từng kênh (mục 154, 2026-09-19)** — mỗi Channel StudioFlow tự chạy
1 lượt OAuth qua `GET /channels/{channel_id}/youtube/authorize-url` +
`GET /oauth/callback` (dùng chung 1 redirect_uri, phân biệt kênh qua `state`) +
`GET /channels/{channel_id}/youtube/oauth-status`. Xem docstring
`app/youtube_analytics.py` cho lý do (1 Google Account có thể quản nhiều kênh YouTube,
token dùng chung trước đây làm 2 kênh StudioFlow bị gán NHẦM cùng 1 kênh YouTube)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json
from app.models import Channel, Project, YoutubeChannelMetricsSnapshot, YoutubeVideoMetricsSnapshot
from app.render.schemas import RenderState
from app.timeutil import vn_isoformat
from app.youtube_analytics import (
    YoutubeApiError,
    YoutubeNotConnectedError,
    build_authorize_url,
    correlate_retention_with_blocks,
    delete_credentials,
    exchange_code_for_credentials,
    fetch_channel_info,
    fetch_country_breakdown,
    fetch_retention_curve,
    fetch_uploaded_videos,
    fetch_video_analytics,
    fetch_video_durations,
    is_connected,
    load_credentials,
    load_oauth_client,
    retention_at_ratio,
    save_credentials,
    save_oauth_client,
)

router = APIRouter(tags=["youtube-analytics"])


def _get_channel_or_404(db: Session, channel_id: str) -> Channel:
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Không tìm thấy kênh")
    return ch


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return p


# ---------------------------------------------------------------------------
# OAuth Client + luồng kết nối tài khoản Google (Settings).
# ---------------------------------------------------------------------------
class YoutubeOAuthClientBody(BaseModel):
    client_id: str
    client_secret: str


@router.post("/settings/youtube/oauth-client")
def save_youtube_oauth_client(body: YoutubeOAuthClientBody, db: Session = Depends(get_db)):
    if not body.client_id.strip() or not body.client_secret.strip():
        raise HTTPException(400, "Cần nhập đủ client_id và client_secret")
    save_oauth_client(db, body.client_id.strip(), body.client_secret.strip())
    return {"ok": True}


@router.get("/settings/youtube/status")
def get_youtube_status(db: Session = Depends(get_db)):
    """Chỉ còn field `has_oauth_client` — "đã kết nối" giờ là khái niệm RIÊNG của TỪNG
    kênh (xem `GET /channels/{channel_id}/youtube/oauth-status`), không còn ý nghĩa ở
    cấp toàn app (mục 154, sửa lỗ hổng 1 token dùng chung cho nhiều kênh)."""
    return {"has_oauth_client": load_oauth_client(db) is not None}


# ---------------------------------------------------------------------------
# Liên kết Channel StudioFlow ↔ Kênh YouTube thật — OAuth RIÊNG cho từng kênh (mục 154).
# ---------------------------------------------------------------------------
@router.get("/channels/{channel_id}/youtube/authorize-url")
def get_youtube_channel_authorize_url(channel_id: str, redirect_uri: str, db: Session = Depends(get_db)):
    """`redirect_uri` do FRONTEND cung cấp (`{BASE}/oauth/callback`, `BASE` chính là cổng
    backend đang chạy mà frontend đã biết qua `window.STUDIOFLOW_API_BASE`) — xem
    docstring `youtube_analytics.py` cho lý do loopback KHÔNG cần đăng ký port trước.
    `channel_id` được nhúng vào `state` — xem `build_authorize_url`/`youtube_oauth_
    callback` cho cách callback dùng lại nó để biết token vừa nhận thuộc kênh nào."""
    _get_channel_or_404(db, channel_id)
    client = load_oauth_client(db)
    if not client:
        raise HTTPException(400, "Chưa cấu hình OAuth Client (client_id/client_secret) — nhập trước ở Settings.")
    client_id, client_secret = client
    return {"url": build_authorize_url(client_id, client_secret, redirect_uri, state=channel_id)}


@router.get("/channels/{channel_id}/youtube/oauth-status")
def get_youtube_channel_oauth_status(channel_id: str, db: Session = Depends(get_db)):
    """Frontend POLL endpoint này sau khi mở trình duyệt hệ thống tới `authorize-url` của
    CHÍNH kênh này — không có cách nào khác để biết người dùng đã đồng ý xong trên trình
    duyệt ngoài (xem docstring `youtube_analytics.py::youtube_oauth_callback`)."""
    _get_channel_or_404(db, channel_id)
    return {"connected": is_connected(db, channel_id)}


@router.get("/oauth/callback")
def youtube_oauth_callback(request: Request, code: str | None = None, error: str | None = None, state: str | None = None, db: Session = Depends(get_db)):
    """Google redirect THẲNG VỀ ĐÂY (loopback) sau khi người dùng đồng ý/từ chối trên
    trình duyệt hệ thống — route này được chính backend FastAPI đang chạy phục vụ (KHÔNG
    cần mở thêm 1 HTTP server tạm riêng), DÙNG CHUNG cho MỌI kênh (chỉ 1 redirect_uri
    loopback đăng ký) — `state` (chính là `channel_id`, xem `authorize-url` ở trên) mới
    là thứ phân biệt token này thuộc kênh StudioFlow nào. Trả HTML đơn giản (route này
    được TRÌNH DUYỆT HỆ THỐNG mở, không phải app React — không thể trả JSON cho người
    dùng đọc được) báo kết quả, người dùng tự đóng tab quay lại app; `YoutubeMetricsPanel`
    tự phát hiện đã kết nối xong qua polling `GET /channels/{channel_id}/youtube/oauth-
    status`.

    `redirect_uri` dùng để ĐỔI code lấy token PHẢI khớp CHÍNH XÁC giá trị đã dùng lúc
    dựng `authorize-url` (yêu cầu bắt buộc của OAuth 2.0). **Tự TÁI TẠO từ chính
    `request.url`** (scheme+host+path, BỎ query string) thay vì tin Google echo lại 1
    query param tuỳ ý — Google CHỈ đảm bảo giữ nguyên `code`/`scope`/`state`, KHÔNG có
    nghĩa vụ giữ nguyên query param khác gắn thêm vào `redirect_uri` gốc. Vì route callback
    này LUÔN được truy cập ĐÚNG BẰNG chính redirect_uri đã đăng ký (Google điều hướng
    trình duyệt thẳng tới đó), tự tái tạo từ URL request THẬT SỰ đang nhận là cách DUY
    NHẤT đảm bảo khớp tuyệt đối, không phụ thuộc hành vi round-trip của Google.

    **Gán luôn `Channel.youtube_channel_id/title` ngay tại đây** (mục 154) — trước đây
    việc này nằm ở 1 endpoint `POST /channels/{id}/youtube/connect` RIÊNG, giả định token
    dùng chung đã tồn tại sẵn; giờ token là CỦA RIÊNG kênh này nên biết ngay lúc này luôn
    là thời điểm chính xác để đọc + gán, không cần endpoint riêng nữa."""
    redirect_uri = f"{request.url.scheme}://{request.url.netloc}{request.url.path}"
    if error:
        return HTMLResponse(f"<h2>Kết nối YouTube thất bại</h2><p>{error}</p><p>Đóng tab này và thử lại trong StudioFlow.</p>", status_code=400)
    if not code:
        return HTMLResponse("<h2>Thiếu tham số callback</h2><p>Đóng tab này và thử lại trong StudioFlow.</p>", status_code=400)
    ch = db.query(Channel).filter(Channel.id == state).first() if state else None
    if not ch:
        return HTMLResponse("<h2>Thiếu thông tin kênh</h2><p>Không xác định được kênh StudioFlow đang kết nối — thử lại từ StudioFlow.</p>", status_code=400)
    client = load_oauth_client(db)
    if not client:
        return HTMLResponse("<h2>Chưa cấu hình OAuth Client</h2>", status_code=400)
    client_id, client_secret = client
    try:
        credentials = exchange_code_for_credentials(client_id, client_secret, redirect_uri, code)
    except Exception as e:  # noqa: BLE001 — lỗi đổi code (hết hạn/dùng lại...) hiện rõ cho người dùng
        return HTMLResponse(f"<h2>Kết nối YouTube thất bại</h2><p>{e}</p><p>Đóng tab này và thử lại trong StudioFlow.</p>", status_code=400)
    save_credentials(db, ch.id, credentials)
    try:
        info = fetch_channel_info(credentials)
    except YoutubeApiError as e:
        return HTMLResponse(f"<h2>Đã lưu quyền truy cập nhưng chưa đọc được thông tin kênh</h2><p>{e}</p><p>Đóng tab này, quay lại StudioFlow và thử bấm 'Kết nối lại' ở kênh này.</p>", status_code=502)
    ch.youtube_channel_id = info["channel_id"]
    ch.youtube_channel_title = info["title"]
    ch.youtube_connected_at = vn_isoformat(datetime.now(timezone.utc))
    db.commit()
    return HTMLResponse(f"<h2>Đã kết nối kênh \"{ch.name}\" với YouTube \"{info['title']}\" thành công!</h2><p>Đóng tab này và quay lại StudioFlow.</p>")


@router.post("/channels/{channel_id}/youtube/disconnect")
def disconnect_channel_from_youtube(channel_id: str, db: Session = Depends(get_db)):
    """Gỡ liên kết kênh StudioFlow này với kênh YouTube VÀ xoá luôn token OAuth riêng của
    kênh này (mục 154 — token giờ là RIÊNG từng kênh, không còn dùng chung nên không có
    lý do giữ lại token không ai đọc nữa)."""
    ch = _get_channel_or_404(db, channel_id)
    ch.youtube_channel_id = None
    ch.youtube_channel_title = None
    ch.youtube_connected_at = None
    delete_credentials(db, channel_id)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Liên kết Project ↔ Video YouTube.
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/youtube-videos-available")
def get_youtube_videos_available(project_id: str, db: Session = Depends(get_db)):
    """Danh sách video YouTube của kênh (đã đăng) CHƯA liên kết project nào khác, ĐỂ
    người dùng TỰ CHỌN đúng video ứng với project này — KHÔNG tự đoán theo tên trùng
    khớp (xem quyết định kiến trúc đã chốt). Luôn kèm video ĐANG liên kết project này
    (nếu có) dù nó "đã bị chiếm" bởi chính project này, để dropdown hiện đúng lựa chọn
    hiện tại."""
    p = _get_project_or_404(db, project_id)
    ch = _get_channel_or_404(db, p.channel_id)
    if not ch.youtube_channel_id:
        raise HTTPException(400, "Kênh này chưa kết nối YouTube — kết nối ở Dashboard trước.")
    try:
        credentials = load_credentials(db, ch.id)
        info = fetch_channel_info(credentials)
        videos = fetch_uploaded_videos(credentials, info["uploads_playlist_id"])
    except YoutubeNotConnectedError as e:
        raise HTTPException(400, str(e)) from e
    except YoutubeApiError as e:
        raise HTTPException(502, str(e)) from e

    linked_video_ids = {
        row.youtube_video_id
        for row in db.query(Project).filter(Project.channel_id == p.channel_id, Project.youtube_video_id.isnot(None)).all()
        if row.id != project_id
    }
    available = [v for v in videos if v["video_id"] not in linked_video_ids]
    return {"videos": available, "current_video_id": p.youtube_video_id}


class YoutubeLinkBody(BaseModel):
    video_id: str | None = None


@router.patch("/projects/{project_id}/youtube-link")
def patch_youtube_link(project_id: str, body: YoutubeLinkBody, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    p.youtube_video_id = body.video_id or None
    db.commit()
    return {"youtube_video_id": p.youtube_video_id}


# ---------------------------------------------------------------------------
# Đồng bộ chỉ số (nút bấm thủ công, KHÔNG polling nền).
# ---------------------------------------------------------------------------
def _weighted_avg(pairs: list[tuple[float | None, int]]) -> float | None:
    """Trung bình CÓ TRỌNG SỐ theo `weight` (thường là lượt view) — bỏ qua cặp có `value
    is None` HOẶC `weight<=0`. Trả `None` nếu không còn cặp nào hợp lệ (không phải 0.0 —
    tránh hiểu nhầm "trung bình bằng 0" với "chưa có dữ liệu")."""
    valid = [(v, w) for v, w in pairs if v is not None and w > 0]
    if not valid:
        return None
    total_weight = sum(w for _, w in valid)
    return sum(v * w for v, w in valid) / total_weight


@router.post("/channels/{channel_id}/youtube/sync")
def sync_youtube_metrics(channel_id: str, db: Session = Depends(get_db)):
    """Đồng bộ TOÀN BỘ video đã liên kết trong kênh CÙNG LÚC (1 lượt gọi Analytics API
    dạng batch nhiều video, xem `fetch_video_analytics`) — ghi 1
    `YoutubeChannelMetricsSnapshot` MỚI + N `YoutubeVideoMetricsSnapshot` MỚI (mỗi lần
    LUÔN insert dòng mới, giữ lịch sử — cùng nguyên tắc `RetentionEntry`)."""
    ch = _get_channel_or_404(db, channel_id)
    if not ch.youtube_channel_id:
        raise HTTPException(400, "Kênh này chưa kết nối YouTube.")
    projects_with_video = db.query(Project).filter(Project.channel_id == channel_id, Project.youtube_video_id.isnot(None)).all()
    if not projects_with_video:
        raise HTTPException(400, "Chưa có project nào liên kết video YouTube — liên kết ở Output Center trước.")

    try:
        credentials = load_credentials(db, channel_id)
        video_ids = [p.youtube_video_id for p in projects_with_video]
        durations = fetch_video_durations(credentials, video_ids)
        analytics_by_video = fetch_video_analytics(credentials, ch.youtube_channel_id, video_ids)
        country_by_video = fetch_country_breakdown(credentials, ch.youtube_channel_id, video_ids)
        channel_info = fetch_channel_info(credentials)
    except YoutubeNotConnectedError as e:
        raise HTTPException(400, str(e)) from e
    except YoutubeApiError as e:
        raise HTTPException(502, str(e)) from e

    synced_at = vn_isoformat(datetime.now(timezone.utc))
    weighted_apv: list[tuple[float | None, int]] = []
    weighted_ret30: list[tuple[float | None, int]] = []
    total_comments = 0
    total_views_synced = 0
    total_de_at_ch_views = 0

    for p in projects_with_video:
        vid = p.youtube_video_id
        metrics = analytics_by_video.get(vid)
        duration_sec = durations.get(vid) or 0.0
        countries = country_by_video.get(vid) or {}
        views = metrics["views"] if metrics else None

        retention_curve = None
        retention_30s = None
        if metrics and duration_sec > 0:
            try:
                curve = fetch_retention_curve(credentials, ch.youtube_channel_id, vid)
            except (YoutubeNotConnectedError, YoutubeApiError):
                curve = []
            if curve:
                retention_curve = json.dumps(curve)
                ratio_30s = min(1.0, 30.0 / duration_sec)
                r = retention_at_ratio(curve, ratio_30s)
                retention_30s = round(r * 100, 2) if r is not None else None

        de_at_ch_views = sum(countries.get(c, 0) for c in ("DE", "AT", "CH"))

        db.add(YoutubeVideoMetricsSnapshot(
            project_id=p.id,
            synced_at=synced_at,
            views=views,
            avg_view_percentage=metrics["avg_view_percentage"] if metrics else None,
            avg_view_duration_sec=metrics["avg_view_duration_sec"] if metrics else None,
            retention_at_30s=retention_30s,
            # KHÔNG tự động hoá được — xem docstring `youtube_analytics.py::
            # fetch_video_analytics` (2026-09-19, bug thật 400 "Unknown identifier
            # (impressions)": metric này không tồn tại trong YouTube Analytics API công
            # khai). Giữ NGUYÊN cột (không xoá migration) — CTR thumbnail vẫn nạp tay qua
            # `RetentionEntry.thumbnail_ctr` như trước khi có tính năng này.
            impressions=None,
            impression_ctr=None,
            comment_count=metrics["comment_count"] if metrics else None,
            video_duration_sec=duration_sec or None,
            views_by_country=json.dumps(countries) if countries else None,
            retention_curve=retention_curve,
        ))

        if metrics:
            weighted_apv.append((metrics["avg_view_percentage"], views or 0))
            weighted_ret30.append((retention_30s, views or 0))
            total_comments += metrics["comment_count"]
            total_views_synced += views or 0
            total_de_at_ch_views += de_at_ch_views

    db.add(YoutubeChannelMetricsSnapshot(
        channel_id=channel_id,
        synced_at=synced_at,
        subscriber_count=channel_info["subscriber_count"],
        total_views=channel_info["total_views"],
        video_count=channel_info["video_count"],
        avg_view_percentage=_weighted_avg(weighted_apv),
        # KHÔNG tự động hoá được — xem docstring `youtube_analytics.py::
        # fetch_video_analytics` (2026-09-19).
        avg_impression_ctr=None,
        avg_retention_at_30s=_weighted_avg(weighted_ret30),
        comments_per_1000_views=round(total_comments / total_views_synced * 1000, 2) if total_views_synced > 0 else None,
        de_at_ch_views_pct=round(total_de_at_ch_views / total_views_synced * 100, 2) if total_views_synced > 0 else None,
    ))
    db.commit()
    return get_youtube_channel_metrics(channel_id, db)


# ---------------------------------------------------------------------------
# Đọc snapshot mới nhất (Dashboard).
# ---------------------------------------------------------------------------
def _video_snapshot_out(row: YoutubeVideoMetricsSnapshot) -> dict:
    return {
        "project_id": row.project_id,
        "synced_at": row.synced_at,
        "views": row.views,
        "avg_view_percentage": row.avg_view_percentage,
        "avg_view_duration_sec": row.avg_view_duration_sec,
        "retention_at_30s": row.retention_at_30s,
        "impressions": row.impressions,
        "impression_ctr": row.impression_ctr,
        "comment_count": row.comment_count,
        "comments_per_1000_views": round(row.comment_count / row.views * 1000, 2) if row.views and row.comment_count is not None else None,
        "video_duration_sec": row.video_duration_sec,
        "views_by_country": json.loads(row.views_by_country) if row.views_by_country else None,
    }


@router.get("/channels/{channel_id}/youtube/metrics")
def get_youtube_channel_metrics(channel_id: str, db: Session = Depends(get_db)):
    """Snapshot MỚI NHẤT cấp kênh + list video (mỗi project đã liên kết) kèm snapshot
    mới nhất của TỪNG video — dùng cho tab "Chỉ số YouTube" ở Dashboard."""
    ch = _get_channel_or_404(db, channel_id)
    channel_snapshot = (
        db.query(YoutubeChannelMetricsSnapshot)
        .filter(YoutubeChannelMetricsSnapshot.channel_id == channel_id)
        .order_by(YoutubeChannelMetricsSnapshot.id.desc())
        .first()
    )
    projects_with_video = db.query(Project).filter(Project.channel_id == channel_id, Project.youtube_video_id.isnot(None)).all()
    videos = []
    for p in projects_with_video:
        latest = (
            db.query(YoutubeVideoMetricsSnapshot)
            .filter(YoutubeVideoMetricsSnapshot.project_id == p.id)
            .order_by(YoutubeVideoMetricsSnapshot.id.desc())
            .first()
        )
        videos.append({
            "project_id": p.id,
            "project_title": p.title,
            "youtube_video_id": p.youtube_video_id,
            "metrics": _video_snapshot_out(latest) if latest else None,
        })
    return {
        "youtube_channel_id": ch.youtube_channel_id,
        "youtube_channel_title": ch.youtube_channel_title,
        "channel_snapshot": {
            "synced_at": channel_snapshot.synced_at,
            "subscriber_count": channel_snapshot.subscriber_count,
            "total_views": channel_snapshot.total_views,
            "video_count": channel_snapshot.video_count,
            "avg_view_percentage": channel_snapshot.avg_view_percentage,
            "avg_impression_ctr": channel_snapshot.avg_impression_ctr,
            "avg_retention_at_30s": channel_snapshot.avg_retention_at_30s,
            "comments_per_1000_views": channel_snapshot.comments_per_1000_views,
            "de_at_ch_views_pct": channel_snapshot.de_at_ch_views_pct,
        } if channel_snapshot else None,
        "videos": videos,
    }


@router.get("/projects/{project_id}/youtube/retention-chapters")
def get_retention_chapters(project_id: str, db: Session = Depends(get_db)):
    """Khớp đường cong retention (snapshot mới nhất) với TỪNG BLOCK kịch bản — theo yêu
    cầu người dùng ("theo dõi thêm retention theo từng chương... để biết chương nào kéo
    người xem rơi"). Ưu tiên độ dài THẬT từng shot (`ShotRenderStatus.narration_
    duration_sec`, nếu project ghép qua chính StudioFlow) — fallback độ dài kịch bản gốc
    (`end_sec - timestamp_sec`) khi chưa có/chưa render — xem docstring
    `youtube_analytics.py::correlate_retention_with_blocks` cho lý do KHÔNG dùng giây
    tuyệt đối của kịch bản gốc trực tiếp."""
    p = _get_project_or_404(db, project_id)
    latest = (
        db.query(YoutubeVideoMetricsSnapshot)
        .filter(YoutubeVideoMetricsSnapshot.project_id == project_id)
        .order_by(YoutubeVideoMetricsSnapshot.id.desc())
        .first()
    )
    if not latest or not latest.retention_curve:
        raise HTTPException(400, "Chưa có dữ liệu retention — đồng bộ chỉ số YouTube trước.")
    curve = json.loads(latest.retention_curve)

    pdir = project_dir(p.channel_id, p.id)
    pack = read_json(pdir / "pack.json") or {}
    body = (pack.get("script") or {}).get("body", [])
    render_raw = read_json(pdir / "render.json")
    render_state = RenderState.model_validate(render_raw) if render_raw else None
    narration_by_shot_id = {s.shot_id: s for s in render_state.shots} if render_state else {}
    shots_by_block_id = {s.get("block_id"): s for s in pack.get("shots", []) if s.get("block_id")}

    block_durations: list[tuple[str, float]] = []
    for b in body:
        block_id = b.get("block_id")
        if not block_id:
            continue
        shot = shots_by_block_id.get(block_id)
        status = narration_by_shot_id.get(shot["shot_id"]) if shot else None
        if status and status.narration_status == "ready" and status.narration_duration_sec:
            duration = status.narration_duration_sec
        else:
            start = b.get("timestamp_sec")
            end = b.get("end_sec")
            duration = float(end - start) if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start else 5.0
        block_durations.append((block_id, duration))

    if not block_durations:
        raise HTTPException(400, "Project chưa có kịch bản.")
    chapters = correlate_retention_with_blocks(curve, block_durations)
    return {"video_duration_sec": latest.video_duration_sec, "chapters": chapters}
