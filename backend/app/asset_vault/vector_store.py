"""Wrapper Chroma cho Kho Tài Nguyên — CHANGE_Semantic_BRoll_Asset_Vault.md §2/§3.

**Đổi thành 1 collection TOÀN CỤC (2026-08-27)** — trước đây mỗi kênh có 1
`PersistentClient` RIÊNG (scoping-theo-kênh đạt được bằng cách tách VẬT LÝ 2 DB Chroma
khác nhau); giờ Kho Tài Nguyên là kho toàn cục (1 video gắn được nhiều kênh dạng tag,
xem `models.py::raw_video_channel`) nên KHÔNG còn khái niệm "DB Chroma của riêng 1 kênh"
— lọc theo kênh chuyển hẳn sang tầng SQL (JOIN qua `raw_video_channel`, xem
`matching.py::match_semantic`), Chroma chỉ còn làm đúng 1 việc: xếp hạng độ tương đồng.

Embedded/file-based (`PersistentClient`), KHÔNG chạy service riêng — khớp triết lý
SQLite/file hiện có của toàn hệ thống.

`hnsw:space="cosine"` — Chroma trả DISTANCE (không phải similarity) khi query;
`similarity = 1 - distance` cho cosine space — đã verify thật bằng tay (query vector gần
1 điểm known-similar ra distance ~0.006, gần 1 điểm known-dissimilar ra ~0.89, khớp công
thức cosine distance = 1 - cosine_similarity)."""
from __future__ import annotations

import chromadb

from app.config import asset_vault_chroma_dir

_client: "chromadb.ClientAPI | None" = None

_COLLECTION_NAME = "clips"


def _get_collection():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(asset_vault_chroma_dir()))
    return _client.get_or_create_collection(_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def upsert_clip_vector(clip_id: str, embedding: list[float], document: str) -> None:
    collection = _get_collection()
    collection.upsert(ids=[clip_id], embeddings=[embedding], documents=[document], metadatas=[{"clip_id": clip_id}])


def query_similar_clips(embedding: list[float], top_k: int = 3) -> list[tuple[str, float]]:
    """Trả list `(clip_id, similarity)` sắp theo similarity giảm dần — rỗng nếu kho
    chưa index clip nào (tránh lỗi `n_results > collection size` của Chroma). `top_k` nên
    truyền LỚN HƠN số candidate cuối cùng cần (caller tự lọc thêm theo kênh ở tầng SQL
    sau khi có kết quả — xem `matching.py::match_semantic`)."""
    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []
    result = collection.query(query_embeddings=[embedding], n_results=min(top_k, count))
    ids = result["ids"][0]
    distances = result["distances"][0]
    return [(clip_id, 1.0 - dist) for clip_id, dist in zip(ids, distances)]


def delete_clip_vector(clip_id: str) -> None:
    collection = _get_collection()
    try:
        collection.delete(ids=[clip_id])
    except Exception:  # noqa: BLE001
        pass  # xoá vector không tồn tại/lỗi Chroma nội bộ — không nên chặn xoá clip khỏi SQL
