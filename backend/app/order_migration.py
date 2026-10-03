"""Migration 1 lần cho cột `order_index` MỚI trên `channel`/`project` — mới (2026-09-19),
theo yêu cầu người dùng "cho phép kéo thả để sắp xếp lại thứ tự dự án/kênh trên sidebar".
Dự án KHÔNG dùng Alembic (`main.py` chỉ gọi `Base.metadata.create_all()`, tự tạo bảng CÒN
THIẾU nhưng KHÔNG tự ALTER bảng đã tồn tại) — module này bù đúng phần đó, cùng nguyên tắc
`asset_vault/migration.py::_add_missing_columns`/`youtube_migration.py` (ALTER TABLE ADD
COLUMN thô, idempotent, gọi ngay sau `create_all()` trong `main.py`).

**Backfill CHỈ chạy đúng 1 lần** (khi cột VỪA được thêm ở CHÍNH lượt chạy này) — gán
`order_index` tuần tự 0,1,2... theo `created_at` TĂNG DẦN, giữ NGUYÊN thứ tự người dùng
đang thấy hiện tại (thay vì tất cả `order_index=0` sẽ làm thứ tự trở nên bất định). Lượt
chạy SAU (cột đã tồn tại từ trước) KHÔNG backfill lại — tránh ghi đè thứ tự người dùng đã
tự kéo thả sắp xếp."""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

_TABLES = ("channel", "project")


def migrate_order_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in _TABLES:
            if table not in existing_tables:
                continue  # DB mới tinh — create_all() đã tự tạo đủ cột, không có gì để di trú
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            if "order_index" in existing_cols:
                continue  # đã có từ trước (kể cả do create_all() tạo bảng mới) — không backfill lại
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN order_index INTEGER DEFAULT 0"))
            rows = conn.execute(text(f"SELECT id FROM {table} ORDER BY created_at ASC")).fetchall()
            for idx, (row_id,) in enumerate(rows):
                conn.execute(text(f"UPDATE {table} SET order_index = :idx WHERE id = :id"), {"idx": idx, "id": row_id})
