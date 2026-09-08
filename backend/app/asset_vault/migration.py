"""Migration 1 lần khi Kho Tài Nguyên đổi từ channel-scoped sang TOÀN CỤC (2026-08-27,
theo yêu cầu người dùng: 1 màn riêng, 1 video gắn được nhiều kênh dạng tag). Dự án KHÔNG
dùng Alembic (`main.py` chỉ gọi `Base.metadata.create_all()`, tự tạo bảng CÒN THIẾU
nhưng KHÔNG tự ALTER bảng đã tồn tại/thêm cột mới cho bảng cũ) — module này bù đúng phần
đó bằng `ALTER TABLE`/`INSERT`/di chuyển file thô, chạy 1 lần lúc backend khởi động
(`main.py`, ngay sau `create_all()`). Idempotent — an toàn chạy lại nhiều lần (kiểm tra
tồn tại trước khi ALTER, `INSERT OR IGNORE` trước khi ghi association, kiểm tra file đích
đã có trước khi move).

**Không di trú vector Chroma cũ** (mỗi kênh trước đây có 1 Chroma DB RIÊNG, giờ gộp về 1
DB toàn cục — gộp nhiều PersistentClient thành 1 collection không đơn giản/không đáng
công cho dữ liệu TEST hiện có). Clip cũ vẫn dùng được (khớp từ khoá/gán tay bình thường),
chỉ mất khớp NGỮ NGHĨA cho tới khi người dùng bấm "Gắn nhãn" lại cho raw video đó (tự
upsert vào Chroma toàn cục mới, ghi đè `vector_id` cũ)."""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.config import CHANNELS_DIR, asset_vault_clips_dir, asset_vault_raw_dir


def migrate_asset_vault_to_global(engine: Engine) -> None:
    inspector = inspect(engine)
    if "raw_video" not in inspector.get_table_names():
        return  # DB mới tinh — create_all() đã tự tạo đủ bảng/cột, không có gì để di trú
    _add_missing_columns(engine, inspector)
    _migrate_legacy_channel_id(engine, inspector)
    _move_legacy_files(engine)
    _backfill_processed_clip_channel(engine, inspector)


def _add_missing_columns(engine: Engine, inspector) -> None:
    tables_and_cols = {
        "raw_video": {
            "progress_current": "INTEGER",
            "progress_total": "INTEGER",
            "progress_label": "VARCHAR",
            "original_filename": "VARCHAR",
        },
        # `caption_error` — mới (2026-08-27, bulk gắn nhãn theo lựa chọn tự do ở Kho Tài
        # Nguyên) — xem docstring `models.py::ProcessedClip.caption_error`.
        "processed_clip": {
            "caption_error": "TEXT",
        },
    }
    with engine.begin() as conn:
        for table, new_cols in tables_and_cols.items():
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            for col, col_type in new_cols.items():
                if col not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))


def _migrate_legacy_channel_id(engine: Engine, inspector) -> None:
    """Bản schema CŨ có cột `raw_video.channel_id`/`processed_clip.channel_id` (FK đơn,
    `NOT NULL`) — nếu CÒN TỒN TẠI trong file DB thật (chưa từng chạy migration này), đọc
    dữ liệu qua đó rồi ghi sang bảng m2m `raw_video_channel` mới, RỒI XOÁ HẲN cột cũ.

    **Bug thật phát hiện lúc verify (2 lượt liên tiếp)**:
    1. Ban đầu định GIỮ LẠI cột cũ ("vô hại vì ORM không đọc nữa") — SAI: cột vẫn
       `NOT NULL` ở tầng SQLite THẬT SỰ, mọi INSERT hàng mới sau đó lỗi ngay
       `IntegrityError: NOT NULL constraint failed`.
    2. Thử `ALTER TABLE ... DROP COLUMN channel_id` (SQLite ≥3.35 hỗ trợ DROP COLUMN,
       verify version 3.45.3 trên máy dev) — vẫn lỗi thật:
       `unknown column "channel_id" in foreign key definition` — SQLite từ chối DROP
       COLUMN với cột đang có ràng buộc FOREIGN KEY (giới hạn đã biết của SQLite, không
       phải bug ở đây). Fix THẬT: dùng pattern "12-step" chuẩn của SQLite cho trường hợp
       này — đổi tên bảng cũ, để `Base.metadata.create_all()` (đã import `Base` sẵn có
       schema ORM ĐÚNG, không cần tự map kiểu cột) tạo lại bảng mới đúng schema, copy dữ
       liệu qua bằng danh sách cột tường minh (không có `channel_id`), rồi xoá bảng cũ."""
    needs_rebuild = any("channel_id" in {c["name"] for c in inspector.get_columns(t)} for t in ("raw_video", "processed_clip"))
    if not needs_rebuild:
        return

    from app.db import Base  # import trễ — tránh vòng import ở module level

    with engine.begin() as conn:
        raw_rows = conn.execute(text("SELECT id, channel_id FROM raw_video WHERE channel_id IS NOT NULL")).fetchall()
        conn.execute(text("ALTER TABLE raw_video RENAME TO raw_video_legacy"))
        conn.execute(text("ALTER TABLE processed_clip RENAME TO processed_clip_legacy"))

    Base.metadata.create_all(bind=engine)  # tạo lại raw_video/processed_clip ĐÚNG schema mới (không channel_id)

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO raw_video (id, file_path, source_url, import_note, status, error_message, created_at, progress_current, progress_total, progress_label, original_filename)
            SELECT id, file_path, source_url, import_note, status, error_message, created_at, progress_current, progress_total, progress_label, original_filename FROM raw_video_legacy
        """))
        conn.execute(text("""
            INSERT INTO processed_clip (clip_id, raw_video_id, storage_url, duration_sec, resolution, caption, tags, mood_tone, vector_id, usage_count, last_used_at, active, rights_status, rights_note, created_at, caption_error)
            SELECT clip_id, raw_video_id, storage_url, duration_sec, resolution, caption, tags, mood_tone, vector_id, usage_count, last_used_at, active, rights_status, rights_note, created_at, caption_error FROM processed_clip_legacy
        """))
        for raw_id, channel_id in raw_rows:
            conn.execute(
                text("INSERT OR IGNORE INTO raw_video_channel (raw_video_id, channel_id) VALUES (:r, :c)"),
                {"r": raw_id, "c": channel_id},
            )
        conn.execute(text("DROP TABLE raw_video_legacy"))
        conn.execute(text("DROP TABLE processed_clip_legacy"))


def _backfill_processed_clip_channel(engine: Engine, inspector) -> None:
    """Bug thật (2026-08-28) — `ProcessedClip` TỪNG không có tag kênh riêng (chỉ suy ra
    qua JOIN `raw_video_id`), nên xoá `raw_video` cha làm clip mất sạch kênh + biến mất
    khỏi mọi kết quả matching (xem docstring `models.py::processed_clip_channel`). Bảng
    `processed_clip_channel` là bảng MỚI HOÀN TOÀN nên `create_all()` đã tự tạo — hàm này
    chỉ BACKFILL dữ liệu: với clip nào CHƯA có dòng nào trong bảng mới (idempotent, an
    toàn chạy lại nhiều lần, không ghi đè tag đã sửa tay sau lần chạy đầu) VÀ raw_video
    cha CÒN TỒN TẠI, sao chép nguyên `raw_video.channels` hiện tại của nó sang cho clip.
    Clip đã MỒ CÔI từ trước (raw_video cha đã bị xoá trước khi bản vá này chạy) — dữ liệu
    kênh gốc của nó đã THẬT SỰ MẤT (không có nguồn nào khác để khôi phục), không backfill
    được, cần người dùng tự gắn lại tay (UI có nút gắn kênh riêng cho từng clip)."""
    if "processed_clip_channel" not in inspector.get_table_names():
        return  # create_all() lẽ ra đã tạo bảng này — phòng hờ thứ tự gọi khác dự kiến
    with engine.begin() as conn:
        clip_rows = conn.execute(text(
            "SELECT clip_id, raw_video_id FROM processed_clip "
            "WHERE clip_id NOT IN (SELECT DISTINCT clip_id FROM processed_clip_channel)"
        )).fetchall()
        for clip_id, raw_video_id in clip_rows:
            channel_ids = conn.execute(
                text("SELECT channel_id FROM raw_video_channel WHERE raw_video_id = :r"), {"r": raw_video_id}
            ).fetchall()
            for (channel_id,) in channel_ids:
                conn.execute(
                    text("INSERT OR IGNORE INTO processed_clip_channel (clip_id, channel_id) VALUES (:cl, :ch)"),
                    {"cl": clip_id, "ch": channel_id},
                )


def _move_legacy_files(engine: Engine) -> None:
    """Di chuyển file THẬT từ vị trí cũ `channels/<channel_id>/asset_vault/{raw,clips}/`
    sang vị trí toàn cục mới, cập nhật lại `file_path`/`storage_url` trong DB — best-effort
    (bỏ qua nếu file nguồn đã mất/file đích đã tồn tại, dữ liệu test không cần xử lý lỗi
    phức tạp)."""
    new_raw_dir = asset_vault_raw_dir()
    new_clips_dir = asset_vault_clips_dir()
    channels_dir_str = str(CHANNELS_DIR)

    with engine.begin() as conn:
        for col, table, id_col, target_dir in (
            ("file_path", "raw_video", "id", new_raw_dir),
            ("storage_url", "processed_clip", "clip_id", new_clips_dir),
        ):
            rows = conn.execute(text(f"SELECT {id_col}, {col} FROM {table}")).fetchall()
            for row_pk, old_path_str in rows:
                if not old_path_str or not str(old_path_str).startswith(channels_dir_str):
                    continue  # đã ở vị trí mới, hoặc đường dẫn không thuộc kiểu cũ — bỏ qua
                old_path = Path(old_path_str)
                new_path = target_dir / old_path.name
                if old_path.exists() and not new_path.exists():
                    shutil.move(str(old_path), str(new_path))
                if new_path.exists():
                    conn.execute(text(f"UPDATE {table} SET {col} = :p WHERE {id_col} = :pk"), {"p": str(new_path), "pk": row_pk})
