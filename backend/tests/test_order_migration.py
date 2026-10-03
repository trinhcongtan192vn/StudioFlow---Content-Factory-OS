"""Migration `order_index` cho `channel`/`project` (2026-09-19) — xem docstring
`app/order_migration.py`. Test THUẦN trên schema SQLite tự dựng (không qua `client`/DB
chung của session) — cùng pattern `test_visual_studio_vault.py::
test_add_missing_columns_backfills_media_kind_default_video`."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from app.order_migration import migrate_order_columns


def _make_old_schema_db() -> Path:
    """Mô phỏng DB CŨ (thiếu `order_index`) với 3 channel/project tạo theo thứ tự
    `created_at` KHÁC thứ tự chèn vào bảng — xác nhận backfill đọc ĐÚNG theo `created_at`,
    không phải theo thứ tự vật lý ngẫu nhiên của câu INSERT."""
    tmp_db = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript(
        """
        CREATE TABLE channel (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT);
        CREATE TABLE project (id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT);
        INSERT INTO channel (id, name, created_at) VALUES ('ch_c', 'C', '2026-01-03T00:00:00');
        INSERT INTO channel (id, name, created_at) VALUES ('ch_a', 'A', '2026-01-01T00:00:00');
        INSERT INTO channel (id, name, created_at) VALUES ('ch_b', 'B', '2026-01-02T00:00:00');
        INSERT INTO project (id, channel_id, title, created_at) VALUES ('prj_y', 'ch_a', 'Y', '2026-01-02T00:00:00');
        INSERT INTO project (id, channel_id, title, created_at) VALUES ('prj_x', 'ch_a', 'X', '2026-01-01T00:00:00');
        """
    )
    conn.commit()
    conn.close()
    return tmp_db


def test_migrate_order_columns_backfills_by_created_at_ascending():
    tmp_db = _make_old_schema_db()
    engine = create_engine(f"sqlite:///{tmp_db}")
    migrate_order_columns(engine)

    with engine.connect() as c:
        rows = c.execute(text("SELECT id, order_index FROM channel ORDER BY order_index")).fetchall()
        assert [r[0] for r in rows] == ["ch_a", "ch_b", "ch_c"]  # theo created_at TĂNG DẦN, không phải thứ tự INSERT

        prow = c.execute(text("SELECT id, order_index FROM project ORDER BY order_index")).fetchall()
        assert [r[0] for r in prow] == ["prj_x", "prj_y"]


def test_migrate_order_columns_is_idempotent_and_does_not_reset_user_order():
    tmp_db = _make_old_schema_db()
    engine = create_engine(f"sqlite:///{tmp_db}")
    migrate_order_columns(engine)

    # Người dùng tự kéo thả đổi thứ tự SAU lần migrate đầu — mô phỏng bằng UPDATE trực tiếp.
    with engine.begin() as conn:
        conn.execute(text("UPDATE channel SET order_index = 99 WHERE id = 'ch_c'"))

    migrate_order_columns(engine)  # chạy lại lần 2 — không được ALTER TABLE lỗi (cột đã có), KHÔNG được backfill đè lại
    with engine.connect() as c:
        row = c.execute(text("SELECT order_index FROM channel WHERE id = 'ch_c'")).fetchone()
        assert row[0] == 99  # thứ tự người dùng tự sắp KHÔNG bị ghi đè


def test_migrate_order_columns_skips_missing_tables():
    """DB mới tinh (chưa `create_all()` gọi trước, bảng chưa tồn tại) — không lỗi, bỏ qua
    thầm lặng (đúng nguyên tắc `youtube_migration.py`/`asset_vault/migration.py`)."""
    tmp_db = Path(tempfile.mktemp(suffix=".db"))
    engine = create_engine(f"sqlite:///{tmp_db}")
    migrate_order_columns(engine)  # không có bảng channel/project nào — phải chạy xong không lỗi
