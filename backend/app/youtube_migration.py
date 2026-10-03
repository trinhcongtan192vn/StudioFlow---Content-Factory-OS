"""Migration 1 lần cho các cột MỚI thêm vào bảng CŨ (`channel`/`project`/
`retention_entry`) phục vụ tính năng chỉ số YouTube — mới (2026-09-12). Dự án KHÔNG dùng
Alembic (`main.py` chỉ gọi `Base.metadata.create_all()`, tự tạo bảng CÒN THIẾU nhưng
KHÔNG tự ALTER bảng đã tồn tại/thêm cột mới cho bảng cũ) — module này bù đúng phần đó,
cùng nguyên tắc `asset_vault/migration.py::_add_missing_columns` (ALTER TABLE ADD COLUMN
thô, idempotent, gọi ngay sau `create_all()` trong `main.py`). Tách RIÊNG module (không
gộp vào `asset_vault/migration.py`) vì đây là mối quan tâm ĐỘC LẬP, không liên quan Kho
Tài Nguyên.

2 bảng MỚI HOÀN TOÀN (`youtube_channel_metrics_snapshot`, `youtube_video_metrics_
snapshot`, xem `models.py`) KHÔNG cần migration ở đây — `create_all()` tự tạo."""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import AppSetting, Channel

_TABLES_AND_COLUMNS: dict[str, dict[str, str]] = {
    "channel": {
        "youtube_channel_id": "VARCHAR",
        "youtube_channel_title": "VARCHAR",
        "youtube_connected_at": "VARCHAR",
    },
    "project": {
        "youtube_video_id": "VARCHAR",
    },
    "retention_entry": {
        "rpm": "FLOAT",
    },
}


def migrate_youtube_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, new_cols in _TABLES_AND_COLUMNS.items():
            if table not in existing_tables:
                continue  # DB mới tinh — create_all() đã tự tạo đủ cột, không có gì để di trú
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            for col, col_type in new_cols.items():
                if col not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))


_LEGACY_GLOBAL_TOKEN_KEY = "youtube_oauth"


def migrate_youtube_token_to_per_channel(db: Session) -> None:
    """Di trú dữ liệu (KHÔNG phải schema) — mục 154 (2026-09-19), sửa lỗ hổng "1 token
    OAuth dùng chung toàn app" (Phase 1) sang "token RIÊNG theo từng kênh" (xem docstring
    `app/youtube_analytics.py`). Nếu còn token CHUNG cũ (`AppSetting["youtube_oauth"]`) và
    có kênh ĐÃ từng kết nối (`Channel.youtube_channel_id` không rỗng) nhưng CHƯA có token
    riêng của chính nó (`AppSetting["youtube_oauth:{channel_id}"]`) — copy giá trị token
    cũ sang cho kênh đó, để người dùng đã kết nối thật trước bản sửa này (kênh "Người kể
    sử", xem mục 153) không bị bắt làm lại OAuth ngay sau khi cập nhật. Idempotent tự
    nhiên (chỉ copy khi key riêng CHƯA tồn tại, không xoá/động vào key cũ) — an toàn gọi
    lại mỗi lần khởi động, không cần cờ đánh dấu đã chạy.

    LƯU Ý: đây chỉ là cầu nối 1 chiều cho kênh đã kết nối SẴN — nếu người dùng có ≥2 kênh
    đã "kết nối" trước bản sửa này (tức đang bị dính đúng lỗ hổng đang sửa — cả 2 cùng
    trỏ 1 `youtube_channel_id` do dùng chung token), CẢ 2 đều nhận được BẢN COPY của cùng
    1 token cũ (vẫn đúng dữ liệu hiện có, không làm hỏng gì thêm) — nhưng vì token đó thật
    ra chỉ đại diện đúng cho 1 kênh YouTube, kênh nào bị gán nhầm vẫn cần bấm "Kết nối lại"
    để chọn đúng kênh của mình qua bộ chọn kênh của Google."""
    legacy_row = db.query(AppSetting).filter(AppSetting.key == _LEGACY_GLOBAL_TOKEN_KEY).first()
    if not legacy_row:
        return
    channels_needing_token = db.query(Channel).filter(Channel.youtube_channel_id.isnot(None)).all()
    for ch in channels_needing_token:
        per_channel_key = f"{_LEGACY_GLOBAL_TOKEN_KEY}:{ch.id}"
        if db.query(AppSetting).filter(AppSetting.key == per_channel_key).first():
            continue
        db.add(AppSetting(key=per_channel_key, value=legacy_row.value))
    db.commit()
