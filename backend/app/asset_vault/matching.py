"""Matching Kho Tài Nguyên → shot cần B-roll — CHANGE_Semantic_BRoll_Asset_Vault.md §3
giai đoạn C (Semantic Scene Matching) + §5 (dedup/fallback).

Human-gate GIỮ NGUYÊN: mọi hàm ở đây chỉ TRẢ VỀ candidate + điểm — không hàm nào tự gán
clip vào shot. Việc gán là 1 request PATCH riêng của người dùng (`app/routers/render.py`).

**Lọc theo kênh đổi sang tầng SQL (2026-08-27), rồi đổi sang tag RIÊNG của clip
(2026-08-28)** — `ProcessedClip` có `channels` m2m RIÊNG (`processed_clip_channel`, xem
`models.py`), KHÔNG còn suy ra qua JOIN `RawVideo`/`raw_video_channel` như bản đầu. Bug
thật đã sửa: JOIN qua `RawVideo` là INNER JOIN — clip có `raw_video_id` trỏ tới 1
`RawVideo` ĐÃ BỊ XOÁ (xoá raw_video KHÔNG cascade xoá clip con, xem `routers/asset_vault.
py::delete_raw_video`) bị loại khỏi kết quả JOIN đó, nên biến mất khỏi MỌI kết quả
matching B-roll của MỌI kênh dù clip/file/caption/embedding vẫn còn nguyên — xem
IMPLEMENTATION_REPORT.md mục 98."""
from __future__ import annotations

from sqlalchemy.orm import Query, Session

from app.asset_vault.vector_store import query_similar_clips
from app.models import ProcessedClip, processed_clip_channel
from app.providers.factory import get_embedding

DEFAULT_SIMILARITY_THRESHOLD = 0.65


def _clips_for_channel(db: Session, channel_id: str, media_kind: str | None = None) -> Query:
    """`ProcessedClip` đang `active`, có gắn tag kênh RIÊNG `channel_id` — không phụ
    thuộc `raw_video` cha còn tồn tại hay không. `media_kind` — **mới (2026-09-11)** —
    lọc thêm theo loại ("video"/"image", xem `models.py::ProcessedClip.media_kind`) khi
    truyền; `None` (mặc định) = không lọc, giữ NGUYÊN hành vi cũ cho caller chưa cần phân
    biệt loại."""
    q = (
        db.query(ProcessedClip)
        .join(processed_clip_channel, processed_clip_channel.c.clip_id == ProcessedClip.clip_id)
        .filter(processed_clip_channel.c.channel_id == channel_id, ProcessedClip.active == True)  # noqa: E712
    )
    if media_kind is not None:
        q = q.filter(ProcessedClip.media_kind == media_kind)
    return q


def match_by_keyword(db: Session, channel_id: str, scene_description: str, limit: int = 5, *, media_kind: str | None = None) -> list[tuple[ProcessedClip, float]]:
    """Phase A — so khớp THÔ theo từ khoá (không cần Chroma/embedding provider nào cấu
    hình) — đủ dùng ngay, giá trị tức thì trước khi Phase B (semantic) sẵn sàng. Tách mô
    tả shot thành từ ≥3 ký tự, đếm số từ khớp trong `caption`/`tags` của mỗi clip (OR,
    không cần khớp hết), sắp theo điểm giảm dần. `media_kind` — xem `_clips_for_channel`.

    Trả kèm điểm CHUẨN HOÁ về thang 0-1 (`số từ khớp / tổng số từ mô tả`, **mới
    2026-09-13** — trước đây chỉ trả `ProcessedClip` trần, bỏ điểm sau khi sort) — cùng
    thang với `match_semantic` (similarity 0-1) để `get_vault_candidates` hiển thị VÀ sắp
    xếp ĐỒNG NHẤT cho cả 2 nguồn gợi ý, theo yêu cầu người dùng "thêm matching score và
    xếp theo thứ tự giảm dần" ở Vault Clip Picker."""
    words = [w.lower().strip(",.;:!?\"'()") for w in scene_description.split() if len(w) >= 3]
    words = [w for w in words if w]
    if not words:
        return []
    clips = _clips_for_channel(db, channel_id, media_kind).all()
    scored: list[tuple[int, ProcessedClip]] = []
    for clip in clips:
        haystack = f"{clip.caption} {clip.tags}".lower()
        score = sum(1 for w in words if w in haystack)
        if score > 0:
            scored.append((score, clip))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [(c, count / len(words)) for count, c in scored[:limit]]


def match_semantic(
    db: Session, channel_id: str, scene_description: str, *, threshold: float = DEFAULT_SIMILARITY_THRESHOLD, top_k: int = 3, media_kind: str | None = None
) -> list[tuple[ProcessedClip, float]]:
    """Phase B — embed mô tả shot (CÙNG embedding provider/model đã dùng lúc index clip,
    §3 giai đoạn C bước 2 — bắt buộc để cùng không gian vector), cosine similarity trong
    Chroma collection TOÀN CỤC (không còn tách theo kênh vật lý — xem
    `vector_store.py`). Lọc theo kênh + `active` + `threshold` ở tầng SQL SAU khi có kết
    quả Chroma — overfetch `top_k*10` (hệ số lớn hơn hẳn bản cũ `top_k*3` vì giờ Chroma
    trả candidate từ MỌI kênh, cần dư nhiều hơn để đủ `top_k` sau khi lọc đúng kênh).
    `media_kind` — xem `_clips_for_channel`."""
    embedding = get_embedding(db).embed(scene_description)
    raw_matches = query_similar_clips(embedding, top_k=top_k * 10)
    channel_clip_ids = {c.clip_id for c in _clips_for_channel(db, channel_id, media_kind).all()}
    results: list[tuple[ProcessedClip, float]] = []
    for clip_id, similarity in raw_matches:
        if similarity < threshold or clip_id not in channel_clip_ids:
            continue
        clip = db.query(ProcessedClip).filter(ProcessedClip.clip_id == clip_id).first()
        if clip:
            results.append((clip, similarity))
        if len(results) >= top_k:
            break
    return results


def apply_dedup(candidates: list[ProcessedClip], used_clip_ids: set[str]) -> list[ProcessedClip]:
    """Loại clip ĐÃ DÙNG trong CHÍNH project này — §5 "Trong cùng 1 project: không dùng 1
    clip_id quá 1 lần". `used_clip_ids` do caller (`render.py`) tự thu thập từ
    `linked_clip_id` của các shot khác trong render.json — module này KHÔNG đọc
    render.json trực tiếp (tránh phụ thuộc ngược `app/render/`, giữ `asset_vault/` độc
    lập theo đúng ranh giới module đã có trong app)."""
    return [c for c in candidates if c.clip_id not in used_clip_ids]


def rank_by_usage(candidates: list[ProcessedClip]) -> list[ProcessedClip]:
    """§5 "Giữa các project: ưu tiên clip có usage_count thấp hơn / last_used_at xa
    nhất" — dùng khi nhiều candidate cùng điểm similarity (caller gọi SAU khi đã sort
    theo similarity, hàm này chỉ áp dụng cho phần tie-break, KHÔNG tự sort lại theo
    similarity — truyền vào 1 nhóm nhỏ đã cùng điểm)."""
    return sorted(candidates, key=lambda c: (c.usage_count, c.last_used_at or ""))


def fallback_neutral_broll(db: Session, channel_id: str, limit: int = 3, *, media_kind: str | None = None) -> list[ProcessedClip]:
    """§5 fallback bước 2 — B-roll trung tính (tag `"ambient"`) khi hết candidate đạt
    ngưỡng. Trả rỗng nếu kênh không gắn clip nào có tag này — caller tự rơi tiếp về
    fallback ảnh tĩnh + Ken Burns (KHÔNG đổi gì ở render engine, đã có sẵn). `media_kind`
    — xem `_clips_for_channel`."""
    clips = _clips_for_channel(db, channel_id, media_kind).all()
    return [c for c in clips if "ambient" in (c.tags or "").lower()][:limit]
